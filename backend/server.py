"""
BensaVahti - polttoaineen hintaennustaja Suomeen.

FastAPI-palvelin, joka:
  - Skrapeerää nykyhinnat (polttoaine.net + tankille.fi)
  - Tallentaa havaintoja MongoDB:hen
  - Laskee 5 ennustetta + ensemble (MA, LR, Holt, fundamenttiankkuri, Claude Fable 5)
  - Hakee Brent + EUR/USD Yahoo Financelta
  - Tarjoaa REST-rajapinnan dashboardille
  - Sisältää admin-työkalut virheellisten hintojen korjaamiseen
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
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from scrapers import polttoaine, tankille
import factors as factors_mod
import news as news_mod
import tracker as tracker_mod
import notify as notify_mod
import tax_events as tax_events_mod
import learn as learn_mod
import accuracy_utils as accuracy_mod
from forecast_contract import (
    MODEL_VERSION,
    TARGET_HOUR,
    canonical_age_hours,
    daily_series,
    helsinki_now,
    target_date,
)
from predict import predict_tomorrow
from validation import (
    PRICE_MAX_SANITY,
    PRICE_MIN_SANITY,
    filter_fresh_rows,
    validate_scraped_data,
)
from security_utils import (
    validate_fuel, validate_region, validate_fuel_and_region,
    sanitize_string, validate_price_bounds, validate_date_format,
)
from audit_log import (
    log_admin_action, log_failed_auth, get_failed_auth_count, clear_failed_auth
)

# ---------------- konfiguraatio ----------------

load_dotenv()
logger = logging.getLogger("bensavahti")
logging.basicConfig(level=logging.INFO)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# SECURITY: Wrap MongoDB initialization with error handling to prevent credential leakage
try:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
except Exception as e:
    logger.error("Database initialization failed (credentials redacted)")
    raise SystemExit(1)

FUELS = ("95E10", "diesel")
# Käyttäjän valitsemat "alueelliset" kaupungit — vain näistä näytetään hinnat
SUPPORTED_REGIONS = [
    "Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti", "Suomi",
]
# Set jotka kuuluvat suodatukseen (ei Suomi-aggregaatti)
ALLOWED_CITIES = {r for r in SUPPORTED_REGIONS if r != "Suomi"}

# API Configuration Constants
CACHE_TTL_REGIONAL_SECONDS = 90  # Regional prices cache duration
MAX_TRACKER_ROWS = 400  # Maximum historical tracker rows to fetch
FACTOR_CHANGE_DAYS = 5  # Days for Brent/FX percentage change calculation
HISTORY_BUFFER_DAYS = 5  # Extra days buffer when fetching history

executor = ThreadPoolExecutor(max_workers=12)

# in-memory cache for the /api/regional endpoint (90s TTL)
_regional_cache: dict = {}

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="BensaVahti API", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# SECURITY: Add security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if os.environ.get("ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS - tightened to Vercel origin (can be overridden via env)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "https://polttoaine-notifi.vercel.app").split(",")

# SECURITY: Reject wildcard CORS in production
if "*" in CORS_ORIGINS and os.environ.get("ENV", "production") == "production":
    raise ValueError("CORS wildcard (*) not allowed in production environment")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


# ---------------- skrapaus-apurit ----------------

def _regional_tankille_cities() -> list[str]:
    """Tankille city slugs matching the regions this app actually displays."""
    scrapeable = set(tankille.CITIES)
    return [
        region for region in SUPPORTED_REGIONS
        if region != "Suomi" and region in scrapeable
    ]


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
        clean_by_source[name] = filter_fresh_rows(
            validate_scraped_data(rows, source=name)
        )
    # tankille first (PRIMARY), optional experimental Hintatutka second,
    # polttoaine last; downstream keeps first match in city/source merges.
    return (
        clean_by_source.get("tankille", [])
        + clean_by_source.get("hintatutka", [])
        + clean_by_source.get("polttoaine", [])
    )


def _national_average(rows: list[dict]) -> Optional[float]:
    """Calculate national average price from allowed cities only.
    
    Args:
        rows: List of scraped price records
        
    Returns:
        Average price across all allowed cities, or None if no valid prices
    """
    rows = [r for r in rows if (r.get("city") or "") in ALLOWED_CITIES]
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


def _snapshot_anchor(snapshot: dict | None, region: str,
                     now: datetime | None = None) -> float | None:
    """Return a price only from a snapshot and source no older than 24 hours."""
    if not snapshot or not snapshot.get("ts"):
        return None
    try:
        captured = datetime.fromisoformat(str(snapshot["ts"]).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        snapshot_age = ((now or datetime.now(timezone.utc)) - captured).total_seconds() / 3600
    except (TypeError, ValueError):
        return None
    if snapshot_age < 0 or snapshot_age > 24:
        return None

    if region == "Suomi":
        source_age = snapshot.get("national_min_age_hours")
        if not isinstance(source_age, (int, float)) or source_age + snapshot_age > 24:
            return None
        value = snapshot.get("national_min")
    else:
        city = (snapshot.get("by_city") or {}).get(region) or {}
        fresh_sources = [
            source for source in (city.get("sources") or [])
            if source.get("price") is not None
            and isinstance(source.get("age_hours"), (int, float))
            and 0 <= source["age_hours"] + snapshot_age <= 24
        ]
        value = min((source["price"] for source in fresh_sources), default=None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------- skeemat ----------------

class PredictionRequest(BaseModel):
    fuel: str = "95E10"
    region: str = "Suomi"


# ---------------- reitit ----------------

@app.get("/api/health")
async def health():
    """Health check endpoint with database connectivity test."""
    health_status = {
        "ok": True,
        "service": "bensavahti",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": "unknown"
    }
    
    # Test database connection
    try:
        await db.command("ping")
        health_status["database"] = "connected"
    except Exception as e:
        health_status["ok"] = False
        health_status["database"] = "disconnected"
        health_status["error"] = str(e)[:100]
    
    return health_status


@app.get("/api/prices/current")
@limiter.limit("20/minute")  # SECURITY: Rate limit expensive scraping operation
async def current_prices(fuel: str = Query("95E10"), request: Request = None):
    """Skrapaa nykyhinnat (live, halvimmat asemat). KAIKKI data on live-
    skrapattua — ei Tilastokeskus-kuukausihistoriaa.

    Palauttaa:
      cheap_sample_avg - skrapatun otoksen (~80 halvinta) keskiarvo
      national_min     - skrapatun otoksen halvin
      confidence_data  - lähdetietokäsitys (lähdejako, tuoreus, hintaleveys)
      by_city          - per-kaupunki halvin + keskiarvo + lähteet
    """
    # SECURITY: Validate fuel parameter immediately
    validate_fuel(fuel)

    rows = await _scrape_all(fuel)
    if isinstance(rows, Exception):
        rows = []

    if not rows:
        last = await db.snapshots.find_one({"fuel": fuel, "region": "Suomi"},
                                           sort=[("ts", -1)])
        fallback_min = _snapshot_anchor(last, "Suomi")
        if fallback_min is not None:
            return {
                "fuel": fuel,
                "fetched_at": last.get("ts"),
                "stations_count": 0,
                "cheap_sample_avg": None,
                "national_min": fallback_min,
                "by_city": {},
                "stations": [],
                "stale": True,
                "confidence_data": None,
            }
        raise HTTPException(503, "Service temporarily unavailable")

    cheap_avg = _national_average(rows)
    national_cheapest = min(rows, key=lambda row: row["price"])
    nat_min = national_cheapest["price"]

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
            src_cheapest = min(src_rows, key=lambda row: row["price"])
            sources.append({
                "source": src,
                "price": round(src_cheapest["price"], 3),
                "age_hours": round(src_cheapest["age_hours"], 1),
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
        "national_min_age_hours": national_cheapest.get("age_hours"),
        "by_city": by_city_enhanced,
        "stations_count": len(rows),
        "confidence_data": confidence_data,
    }
    await db.snapshots.insert_one(snap.copy())

    # Päivän history-piste = AITO live-skrapattu otoskeskiarvo (source
    # "scraped"). Kaikki hintahistoria on live-kerättyä tästä päivästä
    # alkaen — ei Tilastokeskus-dataa.
    today = helsinki_now().date().isoformat()
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
    # SECURITY: Validate against whitelist to prevent NoSQL injection
    validate_fuel_and_region(fuel, region)
    
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    cur = db.history.find(
        {"fuel": fuel, "region": region, "date": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("date", 1)
    rows = await cur.to_list(length=days + HISTORY_BUFFER_DAYS)
    return {"fuel": fuel, "region": region, "days": days, "rows": rows}


@app.get("/api/factors")
@limiter.limit("30/minute")  # SECURITY: Rate limit external API calls
async def get_factors(request: Request = None):
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


async def _run_prediction_impl(req: PredictionRequest):
    fuel = req.fuel
    region = req.region
    issued_hel = helsinki_now()
    target_iso = target_date(issued_hel).isoformat()
    
    # SECURITY: Validate against whitelist to prevent NoSQL injection
    validate_fuel_and_region(fuel, region)
    
    # --- Build the price series from LIVE-GATHERED data ONLY ---
    # Ainoa lähde: daily_tracker — aidot 14:00 / 21:00 live-capturet.
    # EI Tilastokeskusta (vanhaa) eikä mitään synteettistä. Historia
    # karttuu vasta tästä päivästä eteenpäin.
    loop = asyncio.get_event_loop()

    tracker_rows = await db.daily_tracker.find(
        {"fuel": fuel, "region": "Suomi"},
        {"_id": 0, "date": 1, "hour": 1, "actual_cheapest": 1,
         "actual_status": 1, "verification_override": 1,
         "verification_failed": 1, "capture_canonical": 1, "by_city": 1},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=MAX_TRACKER_ROWS)
    series_pairs = daily_series(tracker_rows, region)

    # live-ankkuri: uusin skrapaus-snapshot (jos olemassa)
    latest_snap = await db.snapshots.find_one(
        {"fuel": fuel, "region": "Suomi"},
        sort=[("ts", -1)],
    )
    live_anchor = _snapshot_anchor(latest_snap, region)
    if live_anchor is None and series_pairs:
        age_hours = canonical_age_hours(series_pairs[-1][0])
        if age_hours < 0 or age_hours > 24:
            series_pairs = []
    if live_anchor is not None:
        series_pairs = sorted({
            **dict(series_pairs),
            issued_hel.date().isoformat(): live_anchor,
        }.items())

    # Tarvitsemme vähintään YHDEN live-pisteen (capture tai snapshot).
    # Vähäiselläkin datalla predict_tomorrow ankkuroi fundamental_anchoriin
    # + AI:hin; MA/LR/ES degradoituvat hallitusti.
    if not series_pairs and live_anchor is None:
        raise HTTPException(
            400,
            "ei vielä live-dataa - ennuste tarvitsee vähintään yhden "
            "skrapauksen tai daily_tracker-capturen.",
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
    brent_chg = factors_mod.change_frac(brent_series, FACTOR_CHANGE_DAYS)
    fx_chg = factors_mod.change_frac(fx_series, FACTOR_CHANGE_DAYS)

    product_series, product_label = product_pair
    product_val = factors_mod.latest_value(product_series)
    product_chg = factors_mod.change_frac(product_series, FACTOR_CHANGE_DAYS)
    crack_val = factors_mod.crack_spread_eur_per_l(product_val, brent_val, fx_val)

    # Tunnetut veromuutokset — askel huomiselle (jos osuu väliin), plus
    # AI:lle näytettävä lista 30 pv eteenpäin.
    today_iso = issued_hel.date().isoformat()
    tax_step = tax_events_mod.applicable_step(fuel, today_iso, target_iso)
    tax_step_eur_l = tax_step["delta_eur_per_l"] if tax_step else None
    tax_upcoming = tax_events_mod.upcoming(today_iso, lookahead_days=30, fuel=fuel)

    track_record = await learn_mod.track_record(db, fuel, region, days=30)
    method_mae = {
        method: {"n": stats.get("n", 0), "mae": stats.get("mae")}
        for method, stats in track_record["stats"].items()
    }

    # Check for breaking news severity (within last 6 hours)
    breaking_severity = news_mod.get_max_severity(headlines, max_age_hours=6.0)
    if breaking_severity > 0:
        logger.warning("⚠️  BREAKING NEWS detected (severity=%d) - adjusting price clamp", breaking_severity)

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
        breaking_news_severity=breaking_severity,
        target_date_iso=target_iso,
    )

    # data source provenance — vain live-kerätty data
    result["data_sources"] = {
        "tracker_captures": len(tracker_rows),
        "combined_points": len(series_pairs),
        "source": "live_scrape_only",
        "most_recent_scrape": latest_snap.get("ts") if live_anchor is not None else None,
        "sources_count": ((latest_snap or {}).get("confidence_data") or {}).get("sources_count"),
        "stations_count": (latest_snap or {}).get("stations_count"),
    }

    # tallenna ennuste tulevan päivän accuracy-trackausta varten
    doc = {
        "target_date": target_iso,
        "target_hour": TARGET_HOUR,
        "fuel": fuel,
        "region": region,
        "generated_at": result["generated_at"],
        "issued_at": result["generated_at"],
        "issued_hour": issued_hel.hour,
        "model_version": result.get("model_version", MODEL_VERSION),
        "evaluation_eligible": False,
        "methods": {k: v.get("value") for k, v in result["methods"].items()},
        "methods_full": result["methods"],
        "ensemble": result["ensemble"].get("value"),
        "ensemble_full": result["ensemble"],
        "challenger_ensemble": (result.get("challenger_ensemble") or {}).get("value"),
        "challenger_ensemble_full": result.get("challenger_ensemble"),
        "current_price": result["current_price"],
        "live_anchor": live_anchor,
        "brent": brent_val,
        "eur_usd": fx_val,
        "news_headlines": headlines,
        "data_sources": result.get("data_sources"),
        # rikkaampi konteksti UI:lle (näytetään prediction-kortissa)
        "conflict_signal": result.get("conflict_signal"),
        "calendar_event": result.get("calendar_event"),
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
        {"target_date": target_iso, "fuel": fuel, "region": region},
        {"$set": doc},
        upsert=True,
    )

    result["target_date"] = target_iso
    result["target_hour"] = TARGET_HOUR
    result["brent"] = brent_val
    result["eur_usd"] = fx_val
    result["news_headlines"] = headlines
    return result


@app.get("/api/news")
@limiter.limit("10/minute")  # SECURITY: Rate limit expensive RSS scraping (~25 feeds)
async def get_news(max_age_days: int = 14, limit: int = 15, request: Request = None):
    """Hae viimeisimmät polttoaine- ja öljymarkkinauutiset."""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(
        executor, news_mod.fetch_news, None, max_age_days, limit
    )
    health = news_mod.feed_health()
    failed = sorted(label for label, h in health.items() if not h.get("ok"))
    return {
        "items": items,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "max_age_days": max_age_days,
        "feed_health": {
            "ok": sum(1 for h in health.values() if h.get("ok")),
            "failed": failed,
        },
    }


@app.get("/api/predict/latest")
async def latest_prediction(fuel: str = Query("95E10"), region: str = Query("Suomi")):
    validate_fuel_and_region(fuel, region)
    now_hel = helsinki_now()
    min_target = (now_hel.date() + timedelta(days=now_hel.hour >= TARGET_HOUR)).isoformat()
    doc = await db.predictions.find_one(
        {"fuel": fuel, "region": region,
         "target_date": {"$gte": min_target}},
        {"_id": 0},
        sort=[("generated_at", -1)],
    )
    if not doc:
        return {"available": False}

    track_record = await learn_mod.track_record(db, fuel, region, days=30)
    ensemble_mae = track_record["stats"].get("ensemble")

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

    return {
        "available": True,
        "fuel": doc.get("fuel"),
        "region": doc.get("region"),
        "generated_at": doc.get("generated_at"),
        "target_date": doc.get("target_date"),
        "target_hour": doc.get("target_hour", TARGET_HOUR),
        "issued_at": doc.get("issued_at", doc.get("generated_at")),
        "issued_hour": doc.get("issued_hour"),
        "model_version": doc.get("model_version"),
        "current_price": doc.get("current_price"),
        "live_anchor": doc.get("live_anchor"),
        "methods": doc.get("methods_full") or {
            k: {"value": v} for k, v in (doc.get("methods") or {}).items()
        },
        "ensemble": ensemble_full,
        "challenger_ensemble": doc.get("challenger_ensemble_full"),
        "prediction_confidence": prediction_confidence,
        "brent": doc.get("brent"),
        "eur_usd": doc.get("eur_usd"),
        "news_headlines": doc.get("news_headlines", []),
        "data_sources": data_sources,
        # rikkaampi konteksti — taustamuuttujat & self-training (näytetään UI:ssa)
        "conflict_signal": doc.get("conflict_signal"),
        "calendar_event": doc.get("calendar_event"),
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
async def regional(fuel: str = Query("95E10"), max_age_hours: float = Query(24.0, ge=0.1, le=168.0)):
    """Live-scrape both polttoaine.net (top 20 cheapest nationally) and
    tankille.fi (per-city pages) for ALL supported regions.

    Returns ONLY entries that are ≤ `max_age_hours` old (default 24h).
    For each region we return the cheapest fresh station.
    Cached for 90 seconds.
    """
    # SECURITY: Validate fuel parameter
    validate_fuel(fuel)

    cache_key = f"regional:{fuel}:{int(max_age_hours)}"
    now_ts = datetime.now(timezone.utc)
    today_str = now_ts.astimezone(tracker_mod.HELSINKI).date().isoformat()
    cached = _regional_cache.get(cache_key)
    if cached and (now_ts - cached["ts"]).total_seconds() < CACHE_TTL_REGIONAL_SECONDS:
        return cached["payload"]

    tankille_cities = _regional_tankille_cities()

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
        poltt_rows = validate_scraped_data(poltt_rows, source="regional-polttoaine")
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
        res = validate_scraped_data(res, source=f"regional-tankille-{city}")
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
    validate_fuel_and_region(fuel, region)
    realized_rows = await accuracy_mod.realized_prediction_rows(
        db, fuel, region, days=days
    )
    method_errors: dict[str, list[float]] = {
        "persistence": [],
        "moving_average": [], "linear_regression": [], "exp_smoothing": [],
        "fundamental_anchor": [], "ai_llm": [],
        "ensemble": [],
    }
    rows = []
    for realized in realized_rows:
        actual = realized.get("actual")
        row = {
            "target_date": realized.get("target_date"),
            "actual": actual,
            "ensemble": (realized.get("methods") or {}).get("ensemble"),
            "methods": realized.get("methods", {}),
            "source": realized.get("source"),
        }
        rows.append(row)
        if actual is None:
            continue
        for m, v in (realized.get("methods") or {}).items():
            if v is not None and m in method_errors:
                method_errors[m].append(abs(v - actual))

    summary = {}
    for m, errs in method_errors.items():
        if errs:
            mae = sum(errs) / len(errs)
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


# ---------------- password-protected manual trigger (Postman) ----------------

class AdminRequest(BaseModel):
    # SECURITY: Password removed from body - use X-Admin-Token header only
    action: str = "all"          # ping | capture | predict | all | notify
    fuel: str = "all"            # all | 95E10 | diesel
    region: str = "Suomi"
    hour: Optional[int] = None   # pakota capture-slot; oletus nykyhetki
    notify: bool = False


async def _check_admin(token: str, client_ip: str, endpoint: str) -> None:
    """Verify admin token with constant-time comparison and failed auth tracking.
    
    SECURITY: 
    - Constant-time comparison prevents timing attacks
    - Tracks failed attempts and locks out after 5 failures in 10 minutes
    - Logs failed attempts for forensics
    """
    env_token = os.environ.get("ADMIN_TOKEN")
    if not env_token:
        raise HTTPException(404, "Not found")  # Stealth mode when disabled
    
    # Check if IP is locked out
    failed_count = await get_failed_auth_count(db, client_ip, window_minutes=10)
    if failed_count >= 5:
        await log_failed_auth(db, client_ip, endpoint)
        raise HTTPException(429, "Too many failed attempts. Try again later.")
    
    # Verify token
    if not hmac.compare_digest(str(token or ""), str(env_token)):
        await log_failed_auth(db, client_ip, endpoint)
        raise HTTPException(401, "Unauthorized")
    
    # Clear failed attempts on success
    await clear_failed_auth(db, client_ip)


@app.post("/api/admin/run")
@limiter.limit("10/minute")  # Rate limit: max 10 admin operations per minute
async def admin_run(req: AdminRequest,
                    request: Request,
                    x_admin_token: Optional[str] = Header(default=None)):
    """Salasanasuojattu manuaalinen liipaisin (Postman/curl).

    SECURITY: Authentication via X-Admin-Token header ONLY (no body password).
    Compares against ADMIN_TOKEN env variable using constant-time comparison.
    
    Esimerkki (curl):
        curl -X POST "$BACKEND/api/admin/run" \
          -H "X-Admin-Token: $ADMIN_TOKEN" \
          -H "Content-Type: application/json" \
          -d '{"action": "all", "fuel": "all", "notify": true}'

    action:
      "ping"    - vain auth-testi (ei sivuvaikutuksia)
      "capture" - skrapaa + tallenna daily_tracker (per fuel) NYT
      "predict" - tuore ennuste → kirjoittaa `predictions`-kokoelman
                  (tämä on se mitä UI näyttää /predict/latest -kautta)
      "all"     - capture + predict (+ ntfy jos notify=true)
      "notify"  - lähetä ntfy uusimmista captureista
    """
    client_ip = get_remote_address(request)
    await _check_admin(x_admin_token or "", client_ip, "/api/admin/run")
    
    # SECURITY: Validate parameters against whitelist
    action = (req.action or "all").lower()
    if action not in ("ping", "capture", "predict", "all", "notify"):
        raise HTTPException(400, "Invalid action")
    if req.fuel != "all":
        validate_fuel(req.fuel)
    validate_region(req.region)

    fuels = list(FUELS) if req.fuel == "all" else [req.fuel]
    out: dict = {
        "action": action,
        "fuels": fuels,
        "region": req.region,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if action == "ping":
        out["ok"] = True
        # Audit log
        await log_admin_action(db, "ping", x_admin_token or "", client_ip, 
                              {"action": action}, "success")
        return out

    if action in ("capture", "all"):
        results = []
        for f in fuels:
            try:
                doc = await tracker_mod.capture_daily(
                    db, executor, f, region="Suomi", hour=req.hour)
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
                res = await _run_prediction_impl(
                    PredictionRequest(fuel=f, region=req.region))
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
            ok = notify_mod.send_daily_summary()
            out["ntfy_sent"] = ok
        except Exception as e:
            out["ntfy_sent"] = False
            out["ntfy_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    # Audit log successful action
    await log_admin_action(db, f"admin_run_{action}", x_admin_token or "", client_ip,
                          {"action": action, "fuel": req.fuel, "notify": req.notify}, "success")

    return out


@app.get("/api/track/history")
async def track_history(fuel: str = Query("95E10"), days: int = Query(60, ge=1, le=365)):
    # SECURITY: Validate fuel parameter
    validate_fuel(fuel)
    cutoff = (tracker_mod.helsinki_today() - timedelta(days=days)).isoformat()
    cur = db.daily_tracker.find(
        {"fuel": fuel, "region": "Suomi", "date": {"$gte": cutoff}},
        {"_id": 0, "prediction_full": 0},
    ).sort([("date", 1), ("hour", 1)])
    rows = await cur.to_list(length=days * 2 + HISTORY_BUFFER_DAYS)
    # tarkkuusyhteenveto: use the same realized comparison engine as /api/accuracy.
    # This survives reboots because it can recover from preserved daily_tracker rows.
    realized_rows = await accuracy_mod.realized_prediction_rows(
        db, fuel, "Suomi", days=days
    )
    errs = [
        abs((r.get("methods") or {}).get("ensemble") - r["actual"])
        for r in realized_rows
        if (r.get("methods") or {}).get("ensemble") is not None
        and r.get("actual") is not None
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
@limiter.limit("20/minute")  # Rate limit: max 20 fixes per minute
async def fix_capture(req: FixCaptureRequest,
                     request: Request,
                     rerun_prediction: bool = Query(True),
                     x_admin_token: Optional[str] = Header(default=None)):
    """Fix a bad capture by replacing the price with a corrected value.
    Stores the original scraped price for audit trail.
    If rerun_prediction=true (default), automatically reruns prediction for the affected fuel."""
    client_ip = get_remote_address(request)
    await _check_admin(x_admin_token or "", client_ip, "/api/admin/fix-capture")
    
    # SECURITY: Validate inputs
    validate_fuel_and_region(req.fuel, req.region)
    validate_date_format(req.date)
    validate_price_bounds(req.corrected_price, PRICE_MIN_SANITY, PRICE_MAX_SANITY)
    
    # SECURITY: Sanitize reason field to prevent XSS
    sanitized_reason = sanitize_string(req.reason)
    
    # Find the existing capture
    existing = await db.daily_tracker.find_one({
        "date": req.date,
        "hour": req.hour,
        "fuel": req.fuel,
        "region": req.region
    })
    
    if not existing:
        await log_admin_action(db, "fix_capture", x_admin_token or "", client_ip,
                              {"date": req.date, "hour": req.hour, "fuel": req.fuel}, 
                              "failure", error="Capture not found")
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
                "fix_reason": sanitized_reason,
                "manually_corrected": True,
                "actual_status": "corrected"
            }
        }
    )
    
    # Automatically rerun prediction
    prediction_result = None
    if rerun_prediction and result.modified_count > 0:
        try:
            pred = await _run_prediction_impl(PredictionRequest(fuel=req.fuel, region=req.region))
            prediction_result = {
                "target_date": pred.get("target_date"),
                "ensemble": (pred.get("ensemble") or {}).get("value"),
            }
            logger.info("Auto-reran prediction for %s/%s after fixing capture", req.fuel, req.region)
        except Exception as e:
            prediction_result = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            logger.warning("Failed to rerun prediction for %s/%s: %s", req.fuel, req.region, e)
    
    response = {
        "ok": result.modified_count > 0,
        "date": req.date,
        "hour": req.hour,
        "fuel": req.fuel,
        "original_price": original_price,
        "corrected_price": req.corrected_price,
        "reason": sanitized_reason,
        "prediction_rerun": prediction_result if rerun_prediction else None
    }
    
    # Audit log successful fix
    await log_admin_action(db, "fix_capture", x_admin_token or "", client_ip,
                          {"date": req.date, "hour": req.hour, "fuel": req.fuel, 
                           "original_price": original_price, "corrected_price": req.corrected_price},
                          "success")
    
    return response


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
        return await _run_prediction_impl(PredictionRequest(fuel=fuel, region="Suomi"))

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
