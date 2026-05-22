"""
BensaVahti - polttoaineen hintaennustaja Suomeen.

FastAPI-palvelin, joka:
  - Skrapeerää nykyhinnat (polttoaine.net + tankille.fi)
  - Tallentaa havaintoja MongoDB:hen
  - Generoi simuloidun historian seed-vaiheessa
  - Laskee 4 ennustetta + ensemble (MA, LR, Holt, Claude Sonnet 4.5)
  - Hakee Brent + EUR/USD Yahoo Financelta
  - Tarjoaa REST-rajapinnan dashboardille
"""
from __future__ import annotations
import asyncio
import hmac
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

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

app = FastAPI(title="BensaVahti API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    2. > 25% deviation from the batch median
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
    sorted_p = sorted(r["price"] for r in kept_hard)
    median = sorted_p[len(sorted_p) // 2]
    kept = []
    for r in kept_hard:
        dev = abs(r["price"] - median) / median if median else 0
        if dev > PRICE_MEDIAN_DEV:
            logger.warning("sanity[%s] drop median %.3f vs median %.3f at %s",
                           label, r["price"], median, r.get("station"))
            continue
        kept.append(r)
    return kept


async def _scrape_all(fuel: str) -> list[dict]:
    """Hae nykyhinnat molemmista skrapereista taustasäikeessä.

    tankille.fi on PRIMÄÄRINEN lähde (käyttäjäkokemuksen perusteella tarkempi
    ja tuoreempi). polttoaine.net toimii vertailu/täydennyslähteenä. Molemmista
    suodatetaan järjettömät hinnat (out-of-range tai >25% medianista poikkeavat)
    ennen yhdistämistä."""
    loop = asyncio.get_event_loop()
    t_task = loop.run_in_executor(executor, tankille.fetch_prices, fuel)
    p_task = loop.run_in_executor(executor, polttoaine.fetch_prices, fuel)
    try:
        t_rows, p_rows = await asyncio.gather(t_task, p_task, return_exceptions=True)
    except Exception as e:
        logger.warning("scrape error: %s", e)
        return []
    # filter each source independently against its own median first
    t_clean = _sanity_filter(t_rows if isinstance(t_rows, list) else [], "tankille")
    p_clean = _sanity_filter(p_rows if isinstance(p_rows, list) else [], "polttoaine")
    if not isinstance(t_rows, list):
        logger.warning("tankille failed: %s", t_rows)
    if not isinstance(p_rows, list):
        logger.warning("polttoaine failed: %s", p_rows)
    # tankille first → its rows are preferred when downstream picks "first match"
    return t_clean + p_clean


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
async def seed_history(days: int = 365, force: bool = False):
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
            }
        raise HTTPException(503, "no data: scrapers returned empty and no cache")

    by_city = _city_aggregate(rows)
    cheap_avg = _national_average(rows)
    nat_min = min(r["price"] for r in rows)

    ts = datetime.now(timezone.utc).isoformat()
    snap = {
        "ts": ts,
        "fuel": fuel,
        "region": "Suomi",
        "cheap_sample_avg": cheap_avg,
        "national_min": nat_min,
        "by_city": by_city,
        "stations_count": len(rows),
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
    for city, agg in by_city.items():
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
        "by_city": by_city,
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
async def run_prediction(req: PredictionRequest):
    fuel = req.fuel
    region = req.region
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
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
    live_anchor = latest_snap.get("cheap_sample_avg") if latest_snap else None

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
        "ensemble": doc.get("ensemble_full") or {"value": doc.get("ensemble")},
        "brent": doc.get("brent"),
        "eur_usd": doc.get("eur_usd"),
        "news_headlines": doc.get("news_headlines", []),
        "data_sources": doc.get("data_sources"),
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
            # within 3 cents
            within3c = sum(1 for e in errs if e <= 0.03) / len(errs) * 100
            summary[m] = {
                "n": len(errs),
                "mae": round(mae, 4),
                "within_3c_pct": round(within3c, 1),
            }
        else:
            summary[m] = {"n": 0, "mae": None, "within_3c_pct": None}

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
async def track_run(fuel: str = Query("95E10")):
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
async def track_run_all(notify: bool = Query(True)):
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
async def notify_test():
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
async def track_backfill(points: list[TrackBackfillPoint], clear: bool = Query(False)):
    """Bulk-upsert historical daily_tracker rows from external sources
    (e.g. previous version's notification archive). Idempotent on
    (date, hour, fuel, region).
    If clear=true, wipe daily_tracker first (use to reset bad / fake data)."""
    cleared = 0
    if clear:
        res = await db.daily_tracker.delete_many({})
        cleared = res.deleted_count
    inserted = 0
    updated = 0
    skipped = []
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
    return {"cleared": cleared, "inserted": inserted, "updated": updated,
            "skipped": skipped, "total": len(points)}


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
        "within_3c_pct": (round(sum(1 for e in errs if e <= 0.03) / len(errs) * 100, 1)
                          if errs else None),
        "tomorrow_prediction": rows[-1].get("prediction_for_tomorrow_cheapest") if rows else None,
        "today_actual": rows[-1].get("actual_cheapest") if rows else None,
        "today_date": rows[-1].get("date") if rows else None,
        "today_hour": rows[-1].get("hour") if rows else None,
        "today_captured_at": rows[-1].get("captured_at") if rows else None,
        "today_by_city": rows[-1].get("by_city") if rows else None,
    }
    return {"fuel": fuel, "days": days, "rows": rows, "summary": summary}


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
    logger.info("BensaVahti up - MONGO_URL=%s DB=%s", MONGO_URL, DB_NAME)


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
