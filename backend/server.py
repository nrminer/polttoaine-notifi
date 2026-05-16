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
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from scrapers import polttoaine, tankille
import factors as factors_mod
import statfin
import news as news_mod
import tracker as tracker_mod
import notify as notify_mod
from simulate import simulate_history, BASELINE, CITY_FACTORS
from real_history import build_history
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

async def _scrape_all(fuel: str) -> list[dict]:
    """Hae nykyhinnat molemmista skrapereista taustasäikeessä."""
    loop = asyncio.get_event_loop()
    p_task = loop.run_in_executor(executor, polttoaine.fetch_prices, fuel)
    t_task = loop.run_in_executor(executor, tankille.fetch_prices, fuel)
    try:
        p_rows, t_rows = await asyncio.gather(p_task, t_task, return_exceptions=True)
    except Exception as e:
        logger.warning("scrape error: %s", e)
        return []
    rows = []
    for r in (p_rows, t_rows):
        if isinstance(r, list):
            rows.extend(r)
        else:
            logger.warning("scraper failed: %s", r)
    return rows


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
        "city_factors": CITY_FACTORS,
        "baseline": BASELINE,
    }


@app.post("/api/seed")
async def seed_history(days: int = 365, force: bool = False):
    """Rakenna historia kannan history-kokoelmaan.

    Käyttää AINOASTAAN oikeaa dataa:
      - Tilastokeskuksen (Statfin) kuukausiarvot 2020 → uusin julkaistu
        kuukausi (interpoloidaan päivätasolle ainoastaan PERÄKKÄISTEN
        kuukausi-ankkureiden välillä — ei satunnaista kohinaa)
      - Statfin-datan ja tämän päivän välinen aukko ekstrapoloidaan
        Brent-raakaöljyn liukuvalla muutoksella tai live-skrapatulla
        nykyhinnalla.
      - Tämän päivän piste = live-skrapaus (jos saatavilla).

    Tämä on rehellinen ja tarkistettavissa.
    """
    coll = db.history
    if not force:
        n = await coll.count_documents({})
        if n > 0:
            return {"seeded": False,
                    "reason": f"history not empty ({n} docs); use force=true"}
    else:
        await coll.delete_many({"source": {
            "$in": ["simulated", "statfin+interp", "statfin", "statfin+extrap"]
        }})

    inserted = 0
    summaries: dict = {}

    # rinnakkain: hae Brent series 90 päivää
    loop = asyncio.get_event_loop()
    brent_series = await loop.run_in_executor(executor, factors_mod.fetch_brent, 90)

    for fuel in FUELS:
        # live-anchor: katso uusin snapshot
        latest_doc = await db.snapshots.find_one(
            {"fuel": fuel, "region": "Suomi"},
            sort=[("ts", -1)],
        )
        # käytä halvimpien otoksen keskiarvoa tämän päivän ankkurina
        live_today = None
        if latest_doc:
            live_today = (latest_doc.get("cheap_sample_avg")
                          or latest_doc.get("national_avg"))

        # hae Statfin kuukausi-ankkurit
        try:
            anchors = await loop.run_in_executor(
                executor, statfin.fetch_monthly, fuel, 2020
            )
            logger.info("statfin anchors for %s: %d months", fuel, len(anchors))
        except Exception as e:
            logger.warning("statfin fetch failed for %s: %s", fuel, e)
            anchors = []

        if not anchors:
            continue

        # rakenna pää-historia ("Suomi" alue)
        suomi_series = build_history(anchors, brent_series,
                                     live_today_price=live_today,
                                     days=days)
        for r in suomi_series:
            r["fuel"] = fuel
            r["region"] = "Suomi"

        # alue-vähennys: skaalataan kaupunkikertoimella
        all_rows = list(suomi_series)
        for region, factor in CITY_FACTORS.items():
            if region == "Suomi":
                continue
            for r in suomi_series:
                all_rows.append({
                    "date": r["date"],
                    "price": round(r["price"] * factor, 4),
                    "fuel": fuel,
                    "region": region,
                    "source": r["source"],
                })

        if not all_rows:
            continue
        try:
            from pymongo.errors import BulkWriteError
            try:
                res = await coll.insert_many(all_rows, ordered=False)
                inserted += len(res.inserted_ids)
            except BulkWriteError as bwe:
                inserted += bwe.details.get("nInserted", 0)
        except Exception:
            pass

        summaries[fuel] = {
            "anchors": len(anchors),
            "first_month": anchors[0]["month_iso"],
            "last_month": anchors[-1]["month_iso"],
            "live_anchor": live_today,
        }

    return {"seeded": True, "rows": inserted, "days": days,
            "source": "statfin+extrap+live",
            "details": summaries}


@app.get("/api/prices/current")
async def current_prices(fuel: str = Query("95E10")):
    """Skrapaa nykyhinnat (live, halvimmat asemat) + hae Tilastokeskuksen
    viimeisin virallinen kuukausiarvo.

    Palauttaa:
      official_avg     - Tilastokeskuksen viimeisin kuukausiarvo (€/L)
      official_month   - "2025-12" jne.
      cheap_sample_avg - skrapatun otoksen (~80 halvinta) keskiarvo
      national_min     - skrapatun otoksen halvin
    """
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")

    # rinnakkaiset: scrape + statfin
    loop = asyncio.get_event_loop()
    scrape_task = _scrape_all(fuel)
    statfin_task = loop.run_in_executor(executor, statfin.fetch_monthly, fuel, 2024)
    rows, statfin_rows = await asyncio.gather(scrape_task, statfin_task,
                                              return_exceptions=True)
    if isinstance(rows, Exception):
        rows = []
    official_month = None
    official_avg = None
    if isinstance(statfin_rows, list) and statfin_rows:
        latest = statfin_rows[-1]
        official_month = latest["month_iso"]
        official_avg = latest["price"]

    if not rows:
        last = await db.snapshots.find_one({"fuel": fuel, "region": "Suomi"},
                                           sort=[("ts", -1)])
        if last:
            return {
                "fuel": fuel,
                "fetched_at": last.get("ts"),
                "stations_count": last.get("stations_count", 0),
                "cheap_sample_avg": last.get("cheap_sample_avg")
                                    or last.get("national_avg"),
                "national_min": last.get("national_min"),
                "official_avg": official_avg,
                "official_month": official_month,
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
        "national_avg": official_avg,   # virallinen, jos saatavilla
        "national_min": nat_min,
        "official_month": official_month,
        "by_city": by_city,
        "stations_count": len(rows),
    }
    await db.snapshots.insert_one(snap.copy())

    # päivitä history-piste tämän päivän osalta käyttäen *virallista* arvoa
    # jos saatavilla, muuten halvinta keskiarvoa
    history_price = official_avg if official_avg is not None else cheap_avg
    today = datetime.now(timezone.utc).date().isoformat()
    await db.history.update_one(
        {"date": today, "fuel": fuel, "region": "Suomi"},
        {"$set": {
            "date": today, "fuel": fuel, "region": "Suomi",
            "price": history_price,
            "source": "statfin" if official_avg is not None else "scraped",
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
        "official_avg": official_avg,
        "official_month": official_month,
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

    # historia
    cur = db.history.find(
        {"fuel": fuel, "region": region},
        {"_id": 0},
    ).sort("date", 1)
    hist = await cur.to_list(length=400)
    if len(hist) < 7:
        raise HTTPException(400, "ei riittävästi historiaa, kutsu /api/seed ensin")
    dates = [r["date"] for r in hist]
    prices = [r["price"] for r in hist]

    # rinnakkain: Brent + FX + uusin live-skrapaus + uutiset
    loop = asyncio.get_event_loop()
    brent_task = loop.run_in_executor(executor, factors_mod.fetch_brent, 30)
    fx_task = loop.run_in_executor(executor, factors_mod.fetch_eur_usd, 30)
    news_task = loop.run_in_executor(executor, news_mod.fetch_news, None, 14, 6)

    # live-ankkuri: uusin snapshot (jos olemassa)
    latest_snap = await db.snapshots.find_one(
        {"fuel": fuel, "region": "Suomi"},
        sort=[("ts", -1)],
    )
    # ankkurina käytetään halvimpien otoksen keskiarvoa (top-80) - tämä on lähinnä
    # sitä mitä käyttäjä voi todella maksaa tankatessaan halvalla
    live_anchor = None
    if latest_snap:
        live_anchor = (latest_snap.get("cheap_sample_avg")
                       or latest_snap.get("national_avg"))

    brent_series, fx_series, headlines = await asyncio.gather(
        brent_task, fx_task, news_task
    )
    brent_val = factors_mod.latest_value(brent_series)
    fx_val = factors_mod.latest_value(fx_series)

    result = await predict_tomorrow(
        fuel, dates, prices, brent_val, fx_val,
        live_today_price=live_anchor,
        news_headlines=headlines,
        region=region,
    )

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

    # polttoaine.net: date-kenttä = "16.05." → tämä päivä = 0h, eilen = 24h
    if isinstance(poltt_rows, list):
        for r in poltt_rows:
            date_text = (r.get("date") or "").strip()
            if date_text == today_short:
                age = 2.0  # arvio: päivityksiä tehdään pitkin päivää
            elif date_text == yesterday_short:
                age = 26.0
            else:
                age = 999.0
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
        "ai_llm": [], "ensemble": [],
    }
    rows = []
    for p in preds:
        actual_doc = await db.history.find_one(
            {"fuel": fuel, "region": region, "date": p["target_date"]},
            {"_id": 0},
        )
        actual = actual_doc.get("price") if actual_doc else None
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
            # within 1 cent
            within1c = sum(1 for e in errs if e <= 0.01) / len(errs) * 100
            summary[m] = {
                "n": len(errs),
                "mae": round(mae, 4),
                "within_1c_pct": round(within1c, 1),
            }
        else:
            summary[m] = {"n": 0, "mae": None, "within_1c_pct": None}

    return {"fuel": fuel, "region": region, "days": days,
            "rows": rows, "summary": summary}


# ---------------- daily prediction-vs-actual tracker ----------------

@app.post("/api/track/run")
async def track_run(fuel: str = Query("95E10")):
    """Aja päivän capture nyt (skraapaa halvin + ennusta huominen).
    Idempotentti: saman päivän uusinta-ajo korvaa rivin.
    Vain support fuels.
    """
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    doc = await tracker_mod.capture_daily(db, executor, fuel)
    doc.pop("prediction_full", None)  # iso, jätetään pois yhdestä endpointista
    return doc


@app.post("/api/track/run-all")
async def track_run_all(notify: bool = Query(False)):
    out = []
    for fuel in FUELS:
        doc = await tracker_mod.capture_daily(db, executor, fuel)
        out.append(doc)
    pushed = False
    if notify:
        pushed = notify_mod.send_daily_summary(out)
    # strip large field from response
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


class TrackBackfillPoint(BaseModel):
    date: str  # ISO date YYYY-MM-DD
    fuel: str
    actual_cheapest: float
    actual_cheapest_station: Optional[str] = None
    actual_cheapest_city: Optional[str] = None
    actual_cheapest_source: Optional[str] = None
    region: str = "Suomi"


@app.post("/api/track/backfill")
async def track_backfill(points: list[TrackBackfillPoint]):
    """Bulk-upsert historical daily_tracker rows from external sources
    (e.g. previous version's notification archive). Idempotent."""
    inserted = 0
    updated = 0
    skipped = []
    for p in points:
        if p.fuel not in FUELS:
            skipped.append({"date": p.date, "fuel": p.fuel, "reason": "unknown fuel"})
            continue
        doc = {
            "date": p.date,
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
            {"date": p.date, "fuel": p.fuel, "region": p.region},
            {"$set": doc},
            upsert=True,
        )
        if res.upserted_id is not None:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped,
            "total": len(points)}


@app.get("/api/track/history")
async def track_history(fuel: str = Query("95E10"), days: int = Query(60, ge=1, le=365)):
    if fuel not in FUELS:
        raise HTTPException(400, f"unknown fuel {fuel}")
    cutoff = (tracker_mod.helsinki_today() - timedelta(days=days)).isoformat()
    cur = db.daily_tracker.find(
        {"fuel": fuel, "date": {"$gte": cutoff}},
        {"_id": 0, "prediction_full": 0},
    ).sort("date", 1)
    rows = await cur.to_list(length=days + 5)
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
        "within_1c_pct": (round(sum(1 for e in errs if e <= 0.01) / len(errs) * 100, 1)
                          if errs else None),
        "tomorrow_prediction": rows[-1].get("prediction_for_tomorrow_cheapest") if rows else None,
        "today_actual": rows[-1].get("actual_cheapest") if rows else None,
        "today_date": rows[-1].get("date") if rows else None,
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
        [("fuel", 1), ("region", 1), ("date", 1)], unique=True)
    # taustaprosessi: 18:00 Helsinki-aika
    app.state.tracker_task = asyncio.create_task(
        tracker_mod.scheduler_loop(db, executor, FUELS)
    )
    logger.info("BensaVahti up - MONGO_URL=%s DB=%s", MONGO_URL, DB_NAME)


@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "tracker_task", None)
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
    client.close()
    executor.shutdown(wait=False)
