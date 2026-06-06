"""
BensaVahti - polttoaineen hintaennustaja Suomeen.

FastAPI-palvelin, joka:
  - Skrapeerää nykyhinnat (polttoaine.net + tankille.fi)
  - Tallentaa havaintoja MongoDB:hen
  - Laskee 5 ennustetta + ensemble (MA, LR, Holt, fundamenttiankkuri, Claude Opus 4.7)
  - Hakee Brent + EUR/USD Yahoo Financelta
  - Tarjoaa REST-rajapinnan dashboardille
"""
import asyncio
import hmac
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import json

from scrapers import polttoaine, tankille
import factors as factors_mod
import news as news_mod
import tracker as tracker_mod
import notify as notify_mod
import tax_events as tax_events_mod
import learn as learn_mod
from predict import predict_tomorrow

# ---------------- konfiguraatio ----------------

load_dotenv()
logger = logging.getLogger("bensavahti")
logging.basicConfig(level=logging.INFO)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

FUELS = ("95E10", "diesel")
# Käyttäjän valitsemat "alueelliset" kaupungit — vain näistä näytetään hinnat
SUPPORTED_REGIONS = [
    "Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti", "Suomi",
]
# Set jotka kuuluvat suodatukseen (ei Suomi-aggregaatti)
ALLOWED_CITIES = {r for r in SUPPORTED_REGIONS if r != "Suomi"}

executor = ThreadPoolExecutor(max_workers=12)

# in-memory cache for the /api/regional endpoint (90s TTL)
_regional_cache: dict = {}

# Real-time update notification system
_update_subscribers: set = set()

async def notify_update(event_type: str, data: dict):
    """Notify all SSE subscribers of a data update."""
    if not _update_subscribers:
        return
    
    message = json.dumps({"type": event_type, "data": data})
    dead_subscribers = set()
    
    for queue in _update_subscribers:
        try:
            await queue.put(message)
        except Exception:
            dead_subscribers.add(queue)
    
    # Clean up dead connections
    _update_subscribers.difference_update(dead_subscribers)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="BensaVahti API", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - tightened to Vercel origin (can be overridden via env)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "https://polttoaine-notifi.vercel.app").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


# ---------------- skrapaus-apurit ----------------

# Realistic Finnish fuel price bounds (€/L). Anything outside is almost certainly
# a parsing error or stale junk from a scraper.
PRICE_MIN_SANITY = 1.10
PRICE_MAX_SANITY = 3.50
# Per-batch outlier threshold: drop rows whose price deviates more than this
# fraction from the batch median.
PRICE_MEDIAN_DEV = 0.25


def _sanity_filter(rows: list[dict], label: str = "") -> list[dict]:
    """Drop obviously-wrong prices.
    1. Hard bounds (1.10 .. 3.50 EUR/L)
    2. IQR-based outlier detection (1.5×IQR rule)
    """
    if not rows:
        return rows
    kept_hard: list[dict] = []
    for r in rows:
        p = r.get("price")
        if not isinstance(p, (int, float)):
            continue
        if p < PRICE_MIN_SANITY or p > PRICE_MAX_SANITY:
            logger.warning("sanity[%s] drop hard %.3f at %s/%s",
                           label, p, r.get("city"), r.get("station"))
            continue
        kept_hard.append(r)
    if len(kept_hard) < 3:
        return kept_hard
    # IQR-based outlier detection
    prices = sorted(r["price"] for r in kept_hard)
    n = len(prices)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = prices[q1_idx]
    q3 = prices[q3_idx]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    kept = []
    for r in kept_hard:
        if lower <= r["price"] <= upper:
            kept.append(r)
        else:
            logger.warning("sanity[%s] drop IQR %.3f (bounds [%.3f, %.3f]) at %s",
                           label, r["price"], lower, upper, r.get("station"))
    return kept


async def _scrape_all(fuel: str) -> list[dict]:
    """Fetch current prices from production-validated scrapers.

    tankille.fi is the primary source and polttoaine.net is the cross-check.
    Hintatutka is experimental and skipped unless
    ENABLE_HINTATUTKA_EXPERIMENTAL=1 is set. Each source is sanity-filtered
    independently before results are merged.
    """
    loop = asyncio.get_event_loop()
    tasks = [
        ("tankille", loop.run_in_executor(executor, tankille.fetch_prices, fuel)),
        ("polttoaine", loop.run_in_executor(executor, polttoaine.fetch_prices, fuel)),
    ]
    enable_hintatutka = os.environ.get("ENABLE_HINTATUTKA_EXPERIMENTAL", "").lower() in {
        "1", "true", "yes", "on"
    }
    if enable_hintatutka:
        try:
            from scrapers import hintatutka
            tasks.insert(
                1,
                ("hintatutka", loop.run_in_executor(executor, hintatutka.fetch_prices, fuel)),
            )
        except Exception as e:
            logger.warning("hintatutka experimental import failed: %s", e)
    try:
        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    except Exception as e:
        logger.warning("scrape error: %s", e)
        return []
    clean_by_source: dict[str, list[dict]] = {}
    for (name, _), rows in zip(tasks, results):
        if not isinstance(rows, list):
            logger.warning("%s failed: %s", name, rows)
            rows = []
        clean_by_source[name] = _sanity_filter(rows, name)
    # tankille first (PRIMARY), optional experimental Hintatutka second,
    # polttoaine last; downstream keeps first match in city/source merges.
    return (
        clean_by_source.get("tankille", [])
        + clean_by_source.get("hintatutka", [])
        + clean_by_source.get("polttoaine", [])
    )


def _city_aggregate(rows: list[dict]) -> dict[str, dict]:
    """{ city: { count, min, mean, station_min } } — vain ALLOWED_CITIES."""
    by_city: dict[str, list[dict]] = {}
    for r in rows:
        c = r.get("city") or "?"
        if c not in ALLOWED_CITIES:
            continue
        by_city.setdefault(c, []).append(r)
    out = {}
    for c, lst in by_city.items():
        prices = [x["price"] for x in lst]
        cheapest = min(lst, key=lambda x: x["price"])
        out[c] = {
            "count": len(lst),
            "min": round(min(prices), 4),
            "mean": round(sum(prices) / len(prices), 4),
            "station_min": cheapest.get("station", ""),
            "address_min": cheapest.get("address", ""),
        }
    return out


def _filter_to_allowed(rows: list[dict]) -> list[dict]:
    """Suodata kaikki rivit ALLOWED_CITIES -joukkoon."""
    return [r for r in rows if (r.get("city") or "") in ALLOWED_CITIES]


def _national_average(rows: list[dict]) -> Optional[float]:
    """Otoskeskiarvo, suodatettu ALLOWED_CITIES -kaupunkeihin."""
    rows = _filter_to_allowed(rows)
    prices = [r["price"] for r in rows if r.get("price")]
    if not prices:
        return None
    s = sorted(prices)
    lo = s[len(s) // 10] if len(s) >= 10 else s[0]
    hi = s[-(len(s) // 10 + 1)] if len(s) >= 10 else s[-1]
    filtered = [p for p in prices if lo <= p <= hi]
    if not filtered:
        return round(sum(prices) / len(prices), 4)
    return round(sum(filtered) / len(filtered), 4)


# ---------------- skeemat ----------------

class HistoryPoint(BaseModel):
    date: str
    price: float
    fuel: str
    region: str
    source: str


class PredictionRequest(BaseModel):
    fuel: str = "95E10"
    region: str = "Suomi"


# ---------------- reitit ----------------

@app.get("/api/health")
async def health():
    return {"ok": True, "service": "bensavahti", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/meta")
async def meta():
    return {
        "fuels": list(FUELS),
        "regions": SUPPORTED_REGIONS,
    }


@app.post("/api/seed")
async def seed_history(days: int = 365, force: bool = False,
                       x_admin_token: Optional[str] = Header(default=None)):
    _check_admin(x_admin_token or "")
    """Historiallinen seedaus on POISTETTU KÄYTÖSTÄ.

    Tilastokeskuksen (Statfin) data on vanhaa eikä sitä enää käytetä.
    Kaikki hintahistoria kerätään live-skrapauksista tästä päivästä alkaen
    (/api/prices/current ja /api/regional kirjoittavat "scraped"-rivit;
    daily_tracker tallentaa 14:00/21:00 capturet).

    Endpoint säilytetään yhteensopivuuden vuoksi. Se EI tuota mitään dataa,
    mutta siivoaa kannasta kaikki vanhat MALLINNETUT/TILASTO-rivit niin että
    jäljelle jää vain aito live-skrapattu data.

    `days` ja `force` ovat no-op.
    """
    purged = await db.history.delete_many({"source": {
        "$in": ["simulated", "statfin+interp", "statfin",
                "statfin+extrap", "statfin_monthly"]
    }})
    return {
        "seeded": False,
        "reason": "historical seeding disabled — live-gathered data only "
                  "(Tilastokeskus removed: data too old)",
        "purged_legacy_rows": purged.deleted_count,
    }


@app.get("/api/prices/current")
async def current_prices(fuel: str = Query("95E10")):
    """Skrapaa nykyhinnat (live, halvimmat asemat). KAIKKI data on live-
    skrapattua — ei Tilastokeskus-kuukausihistoriaa.

    Palauttaa:
      cheap_sample_avg - skrapatun otoksen (~80 halvinta) keskiarvo
      national_min     - skrapatun otoksen halvin
      confidence_data  - lähdetietokäsitys (lähdejako, tuoreus, hintaleveys)
      by_city          - per-kaupunki halvin + keskiarvo + lähteet
    """
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")

    rows = await _scrape_all(fuel)
    if isinstance(rows, Exception):
        rows = []

    if not rows:
        last = await db.snapshots.find_one({"fuel": fuel, "region": "Suomi"},
                                           sort=[("ts", -1)])
        if last:
            return {
                "fuel": fuel,
                "fetched_at": last.get("ts"),
                "stations_count": last.get("stations_count", 0),
                "cheap_sample_avg": last.get("cheap_sample_avg"),
                "national_min": last.get("national_min"),
                "by_city": last.get("by_city", {}),
                "stations": [],
                "stale": True,
                "confidence_data": last.get("confidence_data"),
            }
        raise HTTPException(503, "no data: scrapers returned empty and no cache")

    by_city = _city_aggregate(rows)
    cheap_avg = _national_average(rows)
    nat_min = min(r["price"] for r in rows)

    # --- luottamustietojen laskenta ---
    # ryhmittele lähteittäin
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        src = r.get("source", "unknown")
        by_source.setdefault(src, []).append(r)

    source_breakdown = []
    source_prices = []
    for src, src_rows in by_source.items():
        prices = [r["price"] for r in src_rows]
        ages = [r.get("age_hours", 999) for r in src_rows]
        avg_price = sum(prices) / len(prices) if prices else None
        avg_age = sum(ages) / len(ages) if ages else None
        source_breakdown.append({
            "source": src,
            "price": round(avg_price, 3) if avg_price is not None else None,
            "age_hours": round(avg_age, 1) if avg_age is not None else None,
            "station_count": len(src_rows),
        })
        if avg_price is not None:
            source_prices.append(avg_price)

    # hintaleveys = max - min lähteiden keskiarvoista
    price_spread = (round(max(source_prices) - min(source_prices), 3)
                    if len(source_prices) >= 2 else 0.0)

    # yksimielisyystaso: <1.5 ¢/L = high, 1.5–3.5 = medium, >3.5 = low
    if price_spread < 0.015:
        agreement_level = "high"
    elif price_spread < 0.035:
        agreement_level = "medium"
    else:
        agreement_level = "low"

    # tuorein scrape-aika = nyt (live-scrape juuri tehty)
    ts = datetime.now(timezone.utc).isoformat()
    most_recent_scrape = ts

    confidence_data = {
        "most_recent_scrape": most_recent_scrape,
        "sources_count": len(by_source),
        "stations_count": len(rows),
        "source_breakdown": sorted(source_breakdown,
                                   key=lambda x: x.get("price") or 999),
        "price_spread": price_spread,
        "agreement_level": agreement_level,
    }

    # --- per-city: lisää source_details ---
    by_city_enhanced = {}
    for city in ALLOWED_CITIES:
        city_rows = [r for r in rows if r.get("city") == city]
        if not city_rows:
            continue
        prices = [r["price"] for r in city_rows]
        cheapest = min(city_rows, key=lambda x: x["price"])

        # lähdejako kaupungissa
        city_by_source: dict[str, list[dict]] = {}
        for r in city_rows:
            src = r.get("source", "unknown")
            city_by_source.setdefault(src, []).append(r)

        sources = []
        for src, src_rows in city_by_source.items():
            src_prices = [r["price"] for r in src_rows]
            src_ages = [r.get("age_hours", 999) for r in src_rows]
            sources.append({
                "source": src,
                "price": round(min(src_prices), 3),
                "age_hours": round(sum(src_ages) / len(src_ages), 1) if src_ages else None,
            })

        by_city_enhanced[city] = {
            "count": len(city_rows),
            "min": round(min(prices), 4),
            "mean": round(sum(prices) / len(prices), 4),
            "station_min": cheapest.get("station", ""),
            "address_min": cheapest.get("address", ""),
            "sources": sorted(sources, key=lambda x: x["price"]),
        }

    snap = {
        "ts": ts,
        "fuel": fuel,
        "region": "Suomi",
        "cheap_sample_avg": cheap_avg,
        "national_min": nat_min,
        "by_city": by_city_enhanced,
        "stations_count": len(rows),
        "confidence_data": confidence_data,
    }
    await db.snapshots.insert_one(snap.copy())

    # Päivän history-piste = AITO live-skrapattu otoskeskiarvo (source
    # "scraped"). Kaikki hintahistoria on live-kerättyä tästä päivästä
    # alkaen — ei Tilastokeskus-dataa.
    today = datetime.now(timezone.utc).date().isoformat()
    if cheap_avg is not None:
        await db.history.update_one(
            {"date": today, "fuel": fuel, "region": "Suomi"},
            {"$set": {
                "date": today, "fuel": fuel, "region": "Suomi",
                "price": cheap_avg, "source": "scraped",
            }},
            upsert=True,
        )
    for city, agg in by_city_enhanced.items():
        if city in SUPPORTED_REGIONS:
            await db.history.update_one(
                {"date": today, "fuel": fuel, "region": city},
                {"$set": {
                    "date": today, "fuel": fuel, "region": city,
                    "price": agg["mean"], "source": "scraped",
                }},
                upsert=True,
            )

    return {
        "fuel": fuel,
        "fetched_at": ts,
        "stations_count": len(rows),
        "cheap_sample_avg": cheap_avg,
        "national_min": nat_min,
        "by_city": by_city_enhanced,
        "confidence_data": confidence_data,
        "stations": [
            {"city": r["city"], "station": r["station"], "address": r.get("address", ""),
             "price": r["price"], "source": r["source"]}
            for r in sorted(rows, key=lambda x: x["price"])[:40]
        ],
        "stale": False,
    }


@app.get("/api/prices/history")
async def history(fuel: str = Query("95E10"),
                  region: str = Query("Suomi"),
                  days: int = Query(180, ge=7, le=730)):
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    cur = db.history.find(
        {"fuel": fuel, "region": region, "date": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("date", 1)
    rows = await cur.to_list(length=days + 5)
    return {"fuel": fuel, "region": region, "days": days, "rows": rows}


@app.get("/api/updates/stream")
async def updates_stream(request: Request):
    """Server-Sent Events endpoint for real-time data updates.
    
    Streams events when:
    - New captures are stored
    - Predictions are updated
    - Prices are fixed/corrected
    
    Event format: {"type": "capture|prediction|correction", "data": {...}}
    """
    async def event_generator():
        queue = asyncio.Queue()
        _update_subscribers.add(queue)
        
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connected', 'data': {'timestamp': datetime.now(timezone.utc).isoformat()}})}\n\n"
            
            # Keep connection alive and send updates
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                try:
                    # Wait for updates with timeout for keep-alive
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive ping every 30 seconds
                    yield f": ping\n\n"
        finally:
            _update_subscribers.discard(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.get("/api/factors")
async def get_factors():
    """Brent + EUR/USD (60 päivän sarja + nykyarvo + delta)."""
    loop = asyncio.get_event_loop()
    brent_task = loop.run_in_executor(executor, factors_mod.fetch_brent, 60)
    fx_task = loop.run_in_executor(executor, factors_mod.fetch_eur_usd, 60)
    brent, eur_usd = await asyncio.gather(brent_task, fx_task)

    return {
        "brent": {
            "series": brent,
            "latest": factors_mod.latest_value(brent),
            "delta_pct": factors_mod.delta_pct(brent),
            "unit": "USD/bbl",
        },
        "eur_usd": {
            "series": eur_usd,
            "latest": factors_mod.latest_value(eur_usd),
            "delta_pct": factors_mod.delta_pct(eur_usd),
            "unit": "EUR/USD",
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/predict/run")
@limiter.limit("10/minute")
async def run_prediction(req: PredictionRequest, request: Request):
    fuel = req.fuel
    region = req.region
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    # CRITICAL FIX: Only "Suomi" region supported - data collection and training
    # only happens for national aggregate. Per-city predictions would need
    # separate per-city capture in tracker.py
    if region != "Suomi":
        raise HTTPException(400, f"only region='Suomi' supported (national aggregate)")
    if region not in SUPPORTED_REGIONS:
        raise HTTPException(400, f"unknown region {region}")

    # --- Build the price series from LIVE-GATHERED data ONLY ---
    # Ainoa lähde: daily_tracker — aidot 14:00 / 21:00 live-capturet.
    # EI Tilastokeskusta (vanhaa) eikä mitään synteettistä. Historia
    # karttuu vasta tästä päivästä eteenpäin.
    loop = asyncio.get_event_loop()

    tracker_rows = await db.daily_tracker.find(
        {"fuel": fuel, "region": "Suomi"},
        {"_id": 0, "date": 1, "hour": 1, "actual_cheapest": 1},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=400)
    by_date: dict[str, float] = {}
    for r in tracker_rows:
        if r.get("actual_cheapest") is None:
            continue
        # yksi piste per päivä — myöhäisin capture (10h/20h) voittaa
        by_date[r["date"]] = r["actual_cheapest"]
    series_pairs = sorted(by_date.items())

    # live-ankkuri: uusin skrapaus-snapshot (jos olemassa)
    latest_snap = await db.snapshots.find_one(
        {"fuel": fuel, "region": "Suomi"},
        sort=[("ts", -1)],
    )
    # CRITICAL FIX: Use national_min (cheapest station) instead of cheap_sample_avg
    # to align anchor with target (actual_cheapest in daily_tracker)
    live_anchor = latest_snap.get("national_min") if latest_snap else None

    # Tarvitsemme vähintään YHDEN live-pisteen (capture tai snapshot).
    # Vähäiselläkin datalla predict_tomorrow ankkuroi fundamental_anchoriin
    # + AI:hin; MA/LR/ES degradoituvat hallitusti.
    if not series_pairs and live_anchor is None:
        raise HTTPException(
            400,
            "ei vielä live-dataa - ennuste tarvitsee vähintään yhden "
            "skrapauksen tai daily_tracker-capturen. Aja "
            "POST /api/track/run-all.",
        )
    dates = [d for d, _ in series_pairs]
    prices = [p for _, p in series_pairs]

    # rinnakkain: Brent + FX + refined-tuote + uutiset
    brent_task = loop.run_in_executor(executor, factors_mod.fetch_brent, 30)
    fx_task = loop.run_in_executor(executor, factors_mod.fetch_eur_usd, 30)
    product_task = loop.run_in_executor(
        executor, factors_mod.fetch_product_for_fuel, fuel, 30
    )
    news_task = loop.run_in_executor(executor, news_mod.fetch_news, None, 14, 6)

    brent_series, fx_series, product_pair, headlines = await asyncio.gather(
        brent_task, fx_task, product_task, news_task
    )
    brent_val = factors_mod.latest_value(brent_series)
    fx_val = factors_mod.latest_value(fx_series)
    brent_chg = factors_mod.change_frac(brent_series, 5)
    fx_chg = factors_mod.change_frac(fx_series, 5)

    product_series, product_label = product_pair
    product_val = factors_mod.latest_value(product_series)
    product_chg = factors_mod.change_frac(product_series, 5)
    crack_val = factors_mod.crack_spread_eur_per_l(product_val, brent_val, fx_val)

    # Tunnetut veromuutokset — askel huomiselle (jos osuu väliin), plus
    # AI:lle näytettävä lista 30 pv eteenpäin.
    today_iso = datetime.now(timezone.utc).date().isoformat()
    target_iso = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    tax_step = tax_events_mod.applicable_step(fuel, today_iso, target_iso)
    tax_step_eur_l = tax_step["delta_eur_per_l"] if tax_step else None
    tax_upcoming = tax_events_mod.upcoming(today_iso, lookahead_days=30, fuel=fuel)

    # itsekalibrointi: menetelmien toteutunut MAE aidoista daily_tracker-
    # captureista (sama totuuslähde kuin /api/accuracy)
    method_mae = await tracker_mod.realized_method_mae(db, fuel, region)

    # Self-training: aiempien ennusteiden vs. toteumien track record
    # (signed bias per menetelmä, viim. rivit AI:n näkyväksi).
    track_record = await learn_mod.track_record(db, fuel, region, days=30)

    result = await predict_tomorrow(
        fuel, dates, prices, brent_val, fx_val,
        live_today_price=live_anchor,
        news_headlines=headlines,
        region=region,
        brent_chg=brent_chg,
        eur_usd_chg=fx_chg,
        method_mae=method_mae,
        product_usd_gal=product_val,
        product_chg=product_chg,
        product_label=product_label,
        crack_eur_l=crack_val,
        tax_events=tax_upcoming,
        tax_step_eur_l=tax_step_eur_l,
        track_record=track_record,
    )

    # data source provenance — vain live-kerätty data
    result["data_sources"] = {
        "tracker_captures": len(tracker_rows),
        "combined_points": len(series_pairs),
        "source": "live_scrape_only",
    }

    # tallenna ennuste tulevan päivän accuracy-trackausta varten
    target_date = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    doc = {
        "target_date": target_date,
        "fuel": fuel,
        "region": region,
        "generated_at": result["generated_at"],
        "methods": {k: v.get("value") for k, v in result["methods"].items()},
        "methods_full": result["methods"],
        "ensemble": result["ensemble"].get("value"),
        "ensemble_full": result["ensemble"],
        "current_price": result["current_price"],
        "live_anchor": live_anchor,
        "brent": brent_val,
        "eur_usd": fx_val,
        "news_headlines": headlines,
        "data_sources": result.get("data_sources"),
        # rikkaampi konteksti UI:lle (näytetään prediction-kortissa)
        "conflict_signal": result.get("conflict_signal"),
        "n_daily_points": result.get("n_daily_points"),
        "product_label": result.get("product_label"),
        "product_usd_gal": result.get("product_usd_gal"),
        "product_chg": result.get("product_chg"),
        "crack_eur_l": result.get("crack_eur_l"),
        "tax_events": result.get("tax_events"),
        "tax_step_eur_l": result.get("tax_step_eur_l"),
        "self_training": result.get("self_training"),
    }
    await db.predictions.update_one(
        {"target_date": target_date, "fuel": fuel, "region": region},
        {"$set": doc},
        upsert=True,
    )

    result["target_date"] = target_date
    result["brent"] = brent_val
    result["eur_usd"] = fx_val
    result["news_headlines"] = headlines
    return result


@app.get("/api/news")
async def get_news(max_age_days: int = 14, limit: int = 8):
    """Hae viimeisimmät polttoaine- ja öljymarkkinauutiset."""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(
        executor, news_mod.fetch_news, None, max_age_days, limit
    )
    return {
        "items": items,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "max_age_days": max_age_days,
    }


@app.get("/api/predict/latest")
async def latest_prediction(fuel: str = Query("95E10"), region: str = Query("Suomi")):
    doc = await db.predictions.find_one(
        {"fuel": fuel, "region": region},
        {"_id": 0},
        sort=[("generated_at", -1)],
    )
    if not doc:
        return {"available": False}

    # Calculate historical MAE from realized method performance
    method_mae = await tracker_mod.realized_method_mae(db, fuel, region)
    ensemble_mae = method_mae.get("ensemble")

    # Determine data quality based on point count
    data_sources = doc.get("data_sources") or {}
    combined_points = data_sources.get("combined_points", 0)
    if combined_points < 7:
        data_quality = "thin"
    elif combined_points <= 20:
        data_quality = "sufficient"
    else:
        data_quality = "rich"

    # Add data_quality to data_sources
    if data_sources:
        data_sources["data_quality"] = data_quality

    # Build prediction_confidence object
    ensemble_full = doc.get("ensemble_full") or {"value": doc.get("ensemble")}
    prediction_mae = None
    if isinstance(ensemble_mae, dict):
        prediction_mae = ensemble_mae.get("mae")
    elif isinstance(ensemble_mae, (int, float)):
        prediction_mae = ensemble_mae
    prediction_confidence = {
        "historical_mae": ensemble_mae,
        "prediction_mae": prediction_mae,
        "confidence_range": {
            "low": ensemble_full.get("confidence_low"),
            "high": ensemble_full.get("confidence_high"),
        },
        "data_quality": data_quality,
        "last_updated": doc.get("generated_at"),
        "most_recent_scrape": data_sources.get("most_recent_scrape") or doc.get("generated_at"),
        "sources_count": data_sources.get("sources_count"),
        "stations_count": data_sources.get("stations_count"),
    }


    # Fetch hourly predictions from daily_tracker
    today_iso = datetime.now(timezone.utc).date().isoformat()
    
    hourly_predictions = {}
    best_window = None
    
    # Get today's captures with predictions for tomorrow
    tracker_docs = await db.daily_tracker.find(
        {"fuel": fuel, "region": region, "date": today_iso},
        {"_id": 0, "hour": 1, "hourly_predictions": 1, "best_window": 1},
    ).sort("hour", -1).to_list(length=10)
    
    if tracker_docs:
        # Use most recent capture's hourly predictions
        latest_capture = tracker_docs[0]
        hourly_predictions = latest_capture.get("hourly_predictions") or {}
        best_window = latest_capture.get("best_window")

    return {
        "available": True,
        "fuel": doc.get("fuel"),
        "region": doc.get("region"),
        "generated_at": doc.get("generated_at"),
        "target_date": doc.get("target_date"),
        "current_price": doc.get("current_price"),
        "live_anchor": doc.get("live_anchor"),
        "methods": doc.get("methods_full") or {
            k: {"value": v} for k, v in (doc.get("methods") or {}).items()
        },
        "ensemble": ensemble_full,
        "prediction_confidence": prediction_confidence,
        "hourly_predictions": hourly_predictions,
        "best_window": best_window,
        "brent": doc.get("brent"),
        "eur_usd": doc.get("eur_usd"),
        "news_headlines": doc.get("news_headlines", []),
        "data_sources": data_sources,
        # rikkaampi konteksti — taustamuuttujat & self-training (näytetään UI:ssa)
        "conflict_signal": doc.get("conflict_signal"),
        "n_daily_points": doc.get("n_daily_points"),
        "product_label": doc.get("product_label"),
        "product_usd_gal": doc.get("product_usd_gal"),
        "product_chg": doc.get("product_chg"),
        "crack_eur_l": doc.get("crack_eur_l"),
        "tax_events": doc.get("tax_events") or [],
        "tax_step_eur_l": doc.get("tax_step_eur_l"),
        "self_training": doc.get("self_training"),
    }


@app.get("/api/regional")
async def regional(fuel: str = Query("95E10"), max_age_hours: float = Query(24.0)):
    """Live-scrape both polttoaine.net (top 20 cheapest nationally) and
    tankille.fi (per-city pages) for ALL supported regions.

    Returns ONLY entries that are ≤ `max_age_hours` old (default 24h).
    For each region we return the cheapest fresh station.
    Cached for 90 seconds.
    """
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")

    cache_key = f"regional:{fuel}:{int(max_age_hours)}"
    now_ts = datetime.now(timezone.utc)
    today_str = now_ts.date().isoformat()
    today_d = now_ts.date()
    # polttoaine.net käyttää muotoa "16.05." (DD.MM.) — vertaillaan tähän
    today_short = f"{today_d.day}.{today_d.month:02d}."
    yesterday_short = f"{(today_d - timedelta(days=1)).day}.{(today_d - timedelta(days=1)).month:02d}."
    cached = _regional_cache.get(cache_key)
    if cached and (now_ts - cached["ts"]).total_seconds() < 90:
        return cached["payload"]

    # tankille.fi tarjoaa per-kaupunki sivut vain näille
    tankille_cities = ["Helsinki", "Espoo", "Vantaa", "Tampere", "Oulu"]

    loop = asyncio.get_event_loop()
    # rinnakkaiset skrapaukset
    poltt_task = loop.run_in_executor(executor, polttoaine.fetch_prices, fuel)
    tank_tasks = [
        loop.run_in_executor(executor, tankille._scrape_city, c, fuel)
        for c in tankille_cities
    ]
    poltt_rows, *tank_results = await asyncio.gather(
        poltt_task, *tank_tasks, return_exceptions=True
    )

    # kerää kaikki "tuoreet" havainnot
    all_obs: list[dict] = []

    # polttoaine.net antaa vain päivämäärän "16.05." (ei kellonaikaa). Emme
    # KEKSI tuntilukemaa: ikä = todellinen aika, joka on kulunut kyseisen
    # raportointipäivän Helsinki-keskiyöstä (konservatiivinen yläraja, ei
    # fabrikoitu arvo). Tuntiresoluutiota ei väitetä olevan.
    now_hel = now_ts.astimezone(tracker_mod.HELSINKI)

    def _poltt_age_hours(date_text: str) -> float:
        m = re.match(r"^\s*(\d{1,2})\.(\d{1,2})\.?\s*$", date_text or "")
        if not m:
            return 999.0
        day, month = int(m.group(1)), int(m.group(2))
        year = now_hel.year
        try:
            report_mid = datetime(year, month, day,
                                  tzinfo=tracker_mod.HELSINKI)
        except ValueError:
            return 999.0
        # vuodenvaihteen kierto: jos päivä on tulevaisuudessa, edellinen vuosi
        if report_mid.date() > now_hel.date() + timedelta(days=2):
            try:
                report_mid = datetime(year - 1, month, day,
                                      tzinfo=tracker_mod.HELSINKI)
            except ValueError:
                return 999.0
        delta_h = (now_hel - report_mid).total_seconds() / 3600.0
        return delta_h if delta_h >= 0 else 999.0

    if isinstance(poltt_rows, list):
        for r in poltt_rows:
            date_text = (r.get("date") or "").strip()
            age = round(_poltt_age_hours(date_text), 1)
            if age <= max_age_hours:
                all_obs.append({
                    "region": r["city"],
                    "price": r["price"],
                    "station": r["station"],
                    "address": r.get("address", ""),
                    "date_text": date_text,
                    "age_hours": age,
                    "source": "polttoaine.net",
                })

    # tankille.fi
    for city, res in zip(tankille_cities, tank_results):
        if isinstance(res, Exception) or not res:
            continue
        for r in res:
            age = r.get("age_hours", 999)
            if age <= max_age_hours:
                all_obs.append({
                    "region": tankille.CITY_DISPLAY.get(city, city),
                    "price": r["price"],
                    "station": r["station"],
                    "address": "",
                    "date_text": r.get("date", ""),
                    "age_hours": age,
                    "source": "tankille.fi",
                })

    # ryhmittele kaupungittain, valitse halvin
    by_region: dict[str, dict] = {}
    for obs in all_obs:
        key = obs["region"]
        if key not in by_region or obs["price"] < by_region[key]["price"]:
            by_region[key] = obs

    # rakenna tulos kaikille SUPPORTED_REGIONS-listan kaupungeille
    rows = []
    for region in SUPPORTED_REGIONS:
        if region == "Suomi":
            continue
        cheap = by_region.get(region)
        if cheap:
            rows.append({
                "region": region,
                "price": round(cheap["price"], 3),
                "station": cheap["station"],
                "address": cheap.get("address", ""),
                "date_text": cheap["date_text"],
                "age_hours": round(cheap["age_hours"], 1),
                "fresh": True,
                "source": cheap["source"],
            })

            # päivitä history
            await db.history.update_one(
                {"date": today_str, "fuel": fuel, "region": region},
                {"$set": {
                    "date": today_str, "fuel": fuel, "region": region,
                    "price": round(cheap["price"], 3), "source": "scraped",
                }},
                upsert=True,
            )
        else:
            rows.append({
                "region": region,
                "price": None,
                "station": None,
                "address": "",
                "date_text": None,
                "age_hours": None,
                "fresh": False,
                "source": None,
            })

    # järjestä halvimmasta kalleimpaan; "ei dataa" -rivit loppuun
    rows.sort(key=lambda r: (r["price"] is None, r["price"] or 999))

    payload = {
        "fuel": fuel,
        "fetched_at": now_ts.isoformat(),
        "max_age_hours": max_age_hours,
        "rows": rows,
    }
    _regional_cache[cache_key] = {"ts": now_ts, "payload": payload}
    return payload


@app.get("/api/accuracy")
async def accuracy(fuel: str = Query("95E10"), region: str = Query("Suomi"),
                   days: int = Query(30, ge=7, le=180)):
    """Vertaa menneitä ennusteita toteutuneisiin hintoihin."""
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    cur = db.predictions.find(
        {"fuel": fuel, "region": region, "target_date": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("target_date", 1)
    preds = await cur.to_list(length=days + 5)

    # hae toteutuneet
    method_errors: dict[str, list[float]] = {
        "moving_average": [], "linear_regression": [], "exp_smoothing": [],
        "fundamental_anchor": [], "ai_llm": [], "ensemble": [],
    }
    rows = []
    for p in preds:
        # "Toteutunut" = AITO skrapattu halvin kyseiseltä päivältä
        # (daily_tracker), EI mallinnettu/kuukausi-Statfin-arvo. Jos päivältä
        # on useampi capture (14:00/21:00), käytetään myöhäisintä.
        actual_doc = await db.daily_tracker.find_one(
            {"fuel": fuel, "region": region, "date": p["target_date"],
             "actual_cheapest": {"$ne": None}},
            {"_id": 0, "actual_cheapest": 1},
            sort=[("hour", -1)],
        )
        actual = actual_doc.get("actual_cheapest") if actual_doc else None
        row = {
            "target_date": p["target_date"],
            "actual": actual,
            "ensemble": p.get("ensemble"),
            "methods": p.get("methods", {}),
        }
        rows.append(row)
        if actual is None:
            continue
        for m, v in (p.get("methods") or {}).items():
            if v is not None and m in method_errors:
                method_errors[m].append(abs(v - actual))
        if p.get("ensemble") is not None:
            method_errors["ensemble"].append(abs(p["ensemble"] - actual))

    summary = {}
    for m, errs in method_errors.items():
        if errs:
            mae = sum(errs) / len(errs)
            # within 2 cents
            within2c = sum(1 for e in errs if e <= 0.02) / len(errs) * 100
            summary[m] = {
                "n": len(errs),
                "mae": round(mae, 4),
                "within_2c_pct": round(within2c, 1),
            }
        else:
            summary[m] = {"n": 0, "mae": None, "within_2c_pct": None}

    return {"fuel": fuel, "region": region, "days": days,
            "rows": rows, "summary": summary}


# ---------------- daily prediction-vs-actual tracker ----------------

async def _notify_async(captures: list[dict]) -> None:
    """Send ntfy notification in a thread so it doesn't block the response."""
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(executor, notify_mod.send_daily_summary, captures)
    except Exception as e:
        logger.warning("background ntfy failed: %s", e)


@app.post("/api/track/run")
@limiter.limit("20/minute")
async def track_run(fuel: str = Query("95E10"), request: Request = None):
    """Aja päivän capture nyt (skraapaa halvin + ennusta huominen).
    Idempotentti: saman päivän uusinta-ajo korvaa rivin.
    Lähettää ntfy-ilmoituksen jokaisen capturen jälkeen.
    """
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    doc = await tracker_mod.capture_daily(db, executor, fuel)
    doc.pop("prediction_full", None)
    asyncio.create_task(_notify_async([doc]))
    return doc


@app.post("/api/track/run-all")
@limiter.limit("10/minute")
async def track_run_all(notify: bool = Query(True), request: Request = None):
    out = []
    for fuel in FUELS:
        doc = await tracker_mod.capture_daily(db, executor, fuel)
        out.append(doc)
    pushed = False
    if notify:
        pushed = notify_mod.send_daily_summary(out)
    for d in out:
        d.pop("prediction_full", None)
    return {"captured": out, "ntfy_sent": pushed}


@app.post("/api/notify/test")
async def notify_test(x_admin_token: Optional[str] = Header(default=None)):
    _check_admin(x_admin_token or "")
    """Send a test ntfy notification using the latest captures from the DB
    (no scraping). Useful for verifying the notification format end-to-end."""
    cur = db.daily_tracker.find(
        {"region": "Suomi"},
        {"_id": 0, "prediction_full": 0},
    ).sort("date", -1).limit(10)
    rows = await cur.to_list(length=10)
    # take latest doc per fuel
    latest_by_fuel: dict[str, dict] = {}
    for r in rows:
        f = r.get("fuel")
        if f and f not in latest_by_fuel:
            latest_by_fuel[f] = r
    captures = [latest_by_fuel[f] for f in FUELS if f in latest_by_fuel]
    if not captures:
        raise HTTPException(404, "no captures in db yet; run /api/track/run-all first")
    ok = notify_mod.send_daily_summary(captures)
    return {"sent": ok, "fuels": [c["fuel"] for c in captures]}


# ---------------- password-protected manual trigger (Postman) ----------------

class AdminRequest(BaseModel):
    password: str = ""           # tai lähetä X-Admin-Token -header
    action: str = "all"          # ping | capture | predict | all | notify
    fuel: str = "all"            # all | 95E10 | diesel
    region: str = "Suomi"
    hour: Optional[int] = None   # pakota capture-slot; oletus nykyhetki
    notify: bool = False


def _check_admin(password: str) -> None:
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise HTTPException(503, "admin endpoint disabled (set ADMIN_TOKEN)")
    if not hmac.compare_digest(str(password or ""), str(token)):
        raise HTTPException(401, "invalid admin password")


@app.post("/api/admin/run")
async def admin_run(req: AdminRequest,
                    request: Request,
                    x_admin_token: Optional[str] = Header(default=None)):
    """Salasanasuojattu manuaalinen liipaisin (Postman/curl).

    Auth: body-kenttä `password` TAI header `X-Admin-Token`. Vertaa
    ympäristömuuttujaan `ADMIN_TOKEN` (vakioaikainen vertailu). Jos
    `ADMIN_TOKEN` puuttuu → 503 (endpoint pois käytöstä).

    Esimerkki (Postman → POST {BACKEND}/api/admin/run, Body=raw JSON):
        {
          "password": "<ADMIN_TOKEN>",
          "action": "all",
          "fuel": "all",
          "notify": true
        }

    action:
      "ping"    - vain auth-testi (ei sivuvaikutuksia)
      "capture" - skrapaa + tallenna daily_tracker (per fuel) NYT
      "predict" - tuore ennuste → kirjoittaa `predictions`-kokoelman
                  (tämä on se mitä UI näyttää /predict/latest -kautta)
      "all"     - capture + predict (+ ntfy jos notify=true)
      "notify"  - lähetä ntfy uusimmista captureista
    """
    _check_admin(req.password or x_admin_token or "")

    action = (req.action or "all").lower()
    if action not in ("ping", "capture", "predict", "all", "notify"):
        raise HTTPException(400, f"unknown action {action!r}")
    if req.fuel != "all" and req.fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {req.fuel}")
    if req.region not in SUPPORTED_REGIONS:
        raise HTTPException(400, f"unknown region {req.region}")

    fuels = list(FUELS) if req.fuel == "all" else [req.fuel]
    out: dict = {
        "action": action,
        "fuels": fuels,
        "region": req.region,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if action == "ping":
        out["ok"] = True
        return out

    captured: list[dict] = []
    if action in ("capture", "all"):
        results = []
        for f in fuels:
            try:
                doc = await tracker_mod.capture_daily(
                    db, executor, f, region=req.region, hour=req.hour)
                captured.append(doc)
                results.append({
                    "fuel": f, "date": doc["date"], "hour": doc["hour"],
                    "actual_cheapest": doc.get("actual_cheapest"),
                    "actual_cheapest_city": doc.get("actual_cheapest_city"),
                    "prediction_for_tomorrow_cheapest":
                        doc.get("prediction_for_tomorrow_cheapest"),
                })
            except Exception as e:
                results.append({"fuel": f, "error":
                                f"{type(e).__name__}: {str(e)[:200]}"})
        out["captured"] = results

    if action in ("predict", "all"):
        preds = []
        for f in fuels:
            try:
                res = await run_prediction(
                    PredictionRequest(fuel=f, region=req.region), request)
                preds.append({
                    "fuel": f,
                    "target_date": res.get("target_date"),
                    "ensemble": (res.get("ensemble") or {}).get("value"),
                    "methods": {k: v.get("value")
                                for k, v in (res.get("methods") or {}).items()},
                    "data_sources": res.get("data_sources"),
                })
            except HTTPException as he:
                preds.append({"fuel": f, "error": he.detail})
            except Exception as e:
                preds.append({"fuel": f, "error":
                              f"{type(e).__name__}: {str(e)[:200]}"})
        out["predicted"] = preds

    if action == "notify" or (req.notify and action in ("capture", "all",
                                                        "predict")):
        try:
            ok = notify_mod.send_daily_summary(captured or None)
            out["ntfy_sent"] = ok
        except Exception as e:
            out["ntfy_sent"] = False
            out["ntfy_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    return out


class TrackBackfillPoint(BaseModel):
    date: str  # ISO date YYYY-MM-DD
    fuel: str
    actual_cheapest: float
    actual_cheapest_station: Optional[str] = None
    actual_cheapest_city: Optional[str] = None
    actual_cheapest_source: Optional[str] = None
    region: str = "Suomi"
    hour: int = 20  # default to evening slot for historical archive entries


@app.post("/api/track/backfill")
async def track_backfill(points: list[TrackBackfillPoint], clear: bool = Query(False),
                         rerun_prediction: bool = Query(True),
                         x_admin_token: Optional[str] = Header(default=None)):
    """Bulk-upsert historical daily_tracker rows from external sources
    (e.g. previous version's notification archive). Idempotent on
    (date, hour, fuel, region).
    If clear=true, wipe daily_tracker first (use to reset bad / fake data).
    If rerun_prediction=true (default), automatically rerun predictions for affected fuels."""
    _check_admin(x_admin_token or "")
    if len(points) > 1000:
        raise HTTPException(400, "max 1000 points per request")
    cleared = 0
    if clear:
        res = await db.daily_tracker.delete_many({})
        cleared = res.deleted_count
    inserted = 0
    updated = 0
    skipped = []
    affected_fuels = set()
    for p in points:
        if p.fuel not in FUELS:
            skipped.append({"date": p.date, "fuel": p.fuel, "reason": "unknown fuel"})
            continue
        doc = {
            "date": p.date,
            "hour": p.hour,
            "fuel": p.fuel,
            "region": p.region,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "actual_cheapest": round(p.actual_cheapest, 3),
            "actual_cheapest_station": p.actual_cheapest_station,
            "actual_cheapest_city": p.actual_cheapest_city,
            "actual_cheapest_source": p.actual_cheapest_source or "notification_archive",
            "stations_scanned": 0,
            "predicted_cheapest_for_today": None,
            "prediction_for_tomorrow_cheapest": None,
        }
        res = await db.daily_tracker.update_one(
            {"date": p.date, "hour": p.hour, "fuel": p.fuel, "region": p.region},
            {"$set": doc},
            upsert=True,
        )
        if res.upserted_id is not None:
            inserted += 1
        else:
            updated += 1
        affected_fuels.add((p.fuel, p.region))
    
    # Automatically rerun predictions for affected fuels
    predictions_rerun = []
    if rerun_prediction and (inserted > 0 or updated > 0):
        for fuel, region in affected_fuels:
            try:
                pred_result = await run_prediction(
                    PredictionRequest(fuel=fuel, region=region)
                )
                predictions_rerun.append({
                    "fuel": fuel,
                    "region": region,
                    "target_date": pred_result.get("target_date"),
                    "ensemble": (pred_result.get("ensemble") or {}).get("value"),
                })
                logger.info("Auto-reran prediction for %s/%s after backfill", fuel, region)
                
                # Notify real-time subscribers
                await notify_update("prediction", {
                    "fuel": fuel,
                    "region": region,
                    "target_date": pred_result.get("target_date"),
                    "ensemble": (pred_result.get("ensemble") or {}).get("value"),
                })
            except Exception as e:
                predictions_rerun.append({
                    "fuel": fuel,
                    "region": region,
                    "error": f"{type(e).__name__}: {str(e)[:200]}"
                })
                logger.warning("Failed to rerun prediction for %s/%s: %s", fuel, region, e)
    
    # Notify about the correction
    if updated > 0 or inserted > 0:
        await notify_update("correction", {
            "inserted": inserted,
            "updated": updated,
            "fuels": [{"fuel": f, "region": r} for f, r in affected_fuels]
        })
    
    return {"cleared": cleared, "inserted": inserted, "updated": updated,
            "skipped": skipped, "total": len(points),
            "predictions_rerun": predictions_rerun if rerun_prediction else None}


@app.get("/api/track/history")
async def track_history(fuel: str = Query("95E10"), days: int = Query(60, ge=1, le=365)):
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    cutoff = (tracker_mod.helsinki_today() - timedelta(days=days)).isoformat()
    cur = db.daily_tracker.find(
        {"fuel": fuel, "date": {"$gte": cutoff}},
        {"_id": 0, "prediction_full": 0},
    ).sort([("date", 1), ("hour", 1)])
    rows = await cur.to_list(length=days * 2 + 5)
    # tarkkuusyhteenveto
    errs = [
        abs(r["predicted_cheapest_for_today"] - r["actual_cheapest"])
        for r in rows
        if r.get("predicted_cheapest_for_today") is not None
        and r.get("actual_cheapest") is not None
    ]
    summary = {
        "n_compared": len(errs),
        "mae": round(sum(errs) / len(errs), 4) if errs else None,
        "within_2c_pct": (round(sum(1 for e in errs if e <= 0.02) / len(errs) * 100, 1)
                          if errs else None),
        "tomorrow_prediction": rows[-1].get("prediction_for_tomorrow_cheapest") if rows else None,
        "today_actual": rows[-1].get("actual_cheapest") if rows else None,
        "today_date": rows[-1].get("date") if rows else None,
        "today_hour": rows[-1].get("hour") if rows else None,
        "today_captured_at": rows[-1].get("captured_at") if rows else None,
        "today_by_city": rows[-1].get("by_city") if rows else None,
    }
    return {"fuel": fuel, "days": days, "rows": rows, "summary": summary}


class FixCaptureRequest(BaseModel):
    date: str  # ISO date YYYY-MM-DD
    hour: int
    fuel: str
    region: str = "Suomi"
    corrected_price: float
    reason: str = "Manual correction"


@app.post("/api/admin/fix-capture")
async def fix_capture(req: FixCaptureRequest,
                     rerun_prediction: bool = Query(True),
                     x_admin_token: Optional[str] = Header(default=None)):
    """Fix a bad capture by replacing the price with a corrected value.
    Stores the original scraped price for audit trail.
    If rerun_prediction=true (default), automatically reruns prediction for the affected fuel."""
    _check_admin(x_admin_token or "")
    
    if req.fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {req.fuel}")
    if req.region not in SUPPORTED_REGIONS:
        raise HTTPException(400, f"unknown region {req.region}")
    
    # Find the existing capture
    existing = await db.daily_tracker.find_one({
        "date": req.date,
        "hour": req.hour,
        "fuel": req.fuel,
        "region": req.region
    })
    
    if not existing:
        raise HTTPException(404, f"No capture found for {req.fuel} on {req.date} @{req.hour:02d}h")
    
    original_price = existing.get("actual_cheapest")
    
    # Update with corrected price
    result = await db.daily_tracker.update_one(
        {
            "date": req.date,
            "hour": req.hour,
            "fuel": req.fuel,
            "region": req.region
        },
        {
            "$set": {
                "actual_cheapest": round(req.corrected_price, 3),
                "fixed_at": datetime.now(timezone.utc).isoformat(),
                "original_scraped_price": original_price,
                "fix_reason": req.reason,
                "manually_corrected": True
            }
        }
    )
    
    # Automatically rerun prediction
    prediction_result = None
    if rerun_prediction and result.modified_count > 0:
        try:
            pred = await run_prediction(PredictionRequest(fuel=req.fuel, region=req.region))
            prediction_result = {
                "target_date": pred.get("target_date"),
                "ensemble": (pred.get("ensemble") or {}).get("value"),
            }
            logger.info("Auto-reran prediction for %s/%s after fixing capture", req.fuel, req.region)
            
            # Notify real-time subscribers
            await notify_update("prediction", {
                "fuel": req.fuel,
                "region": req.region,
                "target_date": pred.get("target_date"),
                "ensemble": (pred.get("ensemble") or {}).get("value"),
            })
        except Exception as e:
            prediction_result = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            logger.warning("Failed to rerun prediction for %s/%s: %s", req.fuel, req.region, e)
    
    # Notify about the correction
    if result.modified_count > 0:
        await notify_update("correction", {
            "date": req.date,
            "hour": req.hour,
            "fuel": req.fuel,
            "region": req.region,
            "original_price": original_price,
            "corrected_price": req.corrected_price,
        })
    
    return {
        "ok": result.modified_count > 0,
        "date": req.date,
        "hour": req.hour,
        "fuel": req.fuel,
        "original_price": original_price,
        "corrected_price": req.corrected_price,
        "reason": req.reason,
        "prediction_rerun": prediction_result if rerun_prediction else None
    }


@app.post("/api/admin/reboot")
async def reboot_system(recalculate: bool = Query(True),
                       x_admin_token: Optional[str] = Header(default=None)):
    """Reboot system - clear all collections except graph data.
    
    Clears:
    - snapshots
    - history
    - predictions
    - price_observations
    - daily_tracker captures AFTER reboot date
    
    Preserves:
    - graph_nodes, graph_edges, graph_metadata
    - daily_tracker captures UP TO reboot date
    
    If recalculate=true (default), reruns predictions for all fuels from remaining captures.
    """
    _check_admin(x_admin_token or "")
    
    # Get reboot timestamp
    reboot_time = datetime.now(timezone.utc)
    reboot_date = reboot_time.date().isoformat()
    
    collections_to_clear = [
        'snapshots',
        'history',
        'predictions',
        'price_observations',
    ]
    
    # Get counts before clearing
    before_counts = {}
    for coll_name in collections_to_clear:
        before_counts[coll_name] = await db[coll_name].count_documents({})
    
    # Count daily_tracker splits
    before_counts['daily_tracker_total'] = await db.daily_tracker.count_documents({})
    before_counts['daily_tracker_future'] = await db.daily_tracker.count_documents(
        {"date": {"$gt": reboot_date}}
    )
    before_counts['daily_tracker_kept'] = await db.daily_tracker.count_documents(
        {"date": {"$lte": reboot_date}}
    )
    
    # Clear collections
    cleared_counts = {}
    for coll_name in collections_to_clear:
        result = await db[coll_name].delete_many({})
        cleared_counts[coll_name] = result.deleted_count
        logger.warning("REBOOT: Cleared %s - %d documents", coll_name, result.deleted_count)
    
    # Remove future captures from daily_tracker
    future_result = await db.daily_tracker.delete_many({"date": {"$gt": reboot_date}})
    cleared_counts['daily_tracker_future'] = future_result.deleted_count
    logger.warning("REBOOT: Removed %d future captures (after %s)", 
                   future_result.deleted_count, reboot_date)
    
    # Count remaining captures
    remaining_captures = await db.daily_tracker.count_documents({})
    
    # Recalculate predictions from remaining captures
    recalculated = []
    if recalculate and remaining_captures > 0:
        logger.info("REBOOT: Recalculating predictions from %d remaining captures", 
                   remaining_captures)
        for fuel in FUELS:
            try:
                pred_result = await run_prediction(
                    PredictionRequest(fuel=fuel, region="Suomi")
                )
                recalculated.append({
                    "fuel": fuel,
                    "target_date": pred_result.get("target_date"),
                    "ensemble": (pred_result.get("ensemble") or {}).get("value"),
                    "data_points": pred_result.get("n_daily_points"),
                })
                logger.info("REBOOT: Recalculated prediction for %s", fuel)
            except Exception as e:
                recalculated.append({
                    "fuel": fuel,
                    "error": f"{type(e).__name__}: {str(e)[:200]}"
                })
                logger.warning("REBOOT: Failed to recalculate %s: %s", fuel, e)
    
    # Notify subscribers
    await notify_update("reboot", {
        "cleared": cleared_counts,
        "remaining_captures": remaining_captures,
        "reboot_date": reboot_date,
        "timestamp": reboot_time.isoformat(),
    })
    
    return {
        "ok": True,
        "reboot_date": reboot_date,
        "reboot_timestamp": reboot_time.isoformat(),
        "before_counts": before_counts,
        "cleared_counts": cleared_counts,
        "total_cleared": sum(cleared_counts.values()),
        "remaining_captures": remaining_captures,
        "recalculated_predictions": recalculated if recalculate else None,
        "preserved": [
            "graph_nodes", 
            "graph_edges", 
            "graph_metadata",
            f"daily_tracker (up to {reboot_date})"
        ],
        "message": f"System rebooted. Data cleared. {remaining_captures} captures preserved up to {reboot_date}. Graph intact."
    }


@app.on_event("startup")
async def on_startup():
    # indeksit
    await db.history.create_index([("fuel", 1), ("region", 1), ("date", 1)], unique=True)
    await db.predictions.create_index(
        [("fuel", 1), ("region", 1), ("target_date", 1)], unique=True)
    await db.snapshots.create_index([("fuel", 1), ("ts", -1)])
    await db.daily_tracker.create_index(
        [("fuel", 1), ("region", 1), ("date", 1), ("hour", 1)], unique=True)
    # legacy index cleanup: old unique (fuel,region,date) blocks the new schema
    try:
        await db.daily_tracker.drop_index("fuel_1_region_1_date_1")
    except Exception:
        pass
    # taustaprosessi: ajastettu capture (14:00 / 21:00 Helsinki)
    app.state.tracker_task = asyncio.create_task(
        tracker_mod.scheduler_loop(db, executor, FUELS)
    )

    # taustaprosessi: aja AI-analyysi uudelleen kun uusia uutisia ilmestyy
    async def _news_predict(fuel: str):
        return await run_prediction(PredictionRequest(fuel=fuel, region="Suomi"))

    app.state.news_task = asyncio.create_task(
        tracker_mod.news_watch_loop(db, executor, FUELS, _news_predict)
    )
    logger.info("BensaVahti up - DB=%s (MongoDB connected)", DB_NAME)


@app.on_event("shutdown")
async def on_shutdown():
    for attr in ("tracker_task", "news_task"):
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()
            try:
                await task
            except Exception:
                pass
    client.close()
    executor.shutdown(wait=False)
