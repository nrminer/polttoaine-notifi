"""
Daily prediction-vs-actual tracker.

Every day at 14:00 and 21:00 Helsinki time we:
  1. Scrape today's CHEAPEST gas station price across Finland (95E10 + diesel)
  2. Read yesterday's prediction (if any) for today's cheapest
  3. Run a fresh prediction for tomorrow's cheapest
  4. Store one row per (date, fuel) in MongoDB collection `daily_tracker`

The frontend graph plots these rows over time:
  - actual_cheapest (solid)
  - predicted_cheapest_for_today (dot — yesterday's call for today)
  - prediction_for_tomorrow (next-day forecast)
"""
from __future__ import annotations
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import predict as predict_mod
import factors as factors_mod
import news as news_mod
import notify as notify_mod
from scrapers import polttoaine, tankille

logger = logging.getLogger("bensavahti.tracker")

HELSINKI = ZoneInfo("Europe/Helsinki")

# Päivittäiset ajastetut captureajat (Helsinki-aika)
SCHEDULED_HOURS = (14, 21)

# Kaupungit joista kerätään halvin + keskihinta jokaisessa capturessa
TRACKED_CITIES = ("Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti")

# Järkevät rajat Suomen polttoainehinnoille (€/L) — pudota parsintavirheet
_PRICE_MIN = 1.10
_PRICE_MAX = 3.50


def helsinki_today() -> date:
    return datetime.now(HELSINKI).date()


def next_scheduled_run(now_utc: datetime | None = None) -> datetime:
    """Return UTC datetime of the next scheduled capture (14:00 or 21:00 Helsinki)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_hel = now_utc.astimezone(HELSINKI)
    candidates = []
    for offset in range(2):  # tänään + huomenna
        day = (now_hel + timedelta(days=offset)).date()
        for hour in SCHEDULED_HOURS:
            t = datetime.combine(day, datetime.min.time(), tzinfo=HELSINKI).replace(hour=hour)
            if t > now_hel:
                candidates.append(t)
    if not candidates:
        # fallback: huomenna ensimmäinen ajastettu tunti (SCHEDULED_HOURS[0])
        d = (now_hel + timedelta(days=1)).date()
        candidates.append(datetime.combine(
            d, datetime.min.time(), tzinfo=HELSINKI
        ).replace(hour=SCHEDULED_HOURS[0]))
    return min(candidates).astimezone(timezone.utc)


def next_18_helsinki(now_utc: datetime | None = None) -> datetime:
    """Compat alias - now returns next_scheduled_run."""
    return next_scheduled_run(now_utc)


def _sane(rows: list) -> list:
    """Pudota selvät parsintavirheet (hinta rajojen ulkopuolella)."""
    return [
        r for r in rows
        if isinstance(r.get("price"), (int, float))
        and _PRICE_MIN <= r["price"] <= _PRICE_MAX
    ]


def _city_breakdown(rows: list) -> dict:
    """{ city: { cheapest, average, count, station, source } } TRACKED_CITIES:lle."""
    by_city: dict[str, list] = {}
    for r in rows:
        c = r.get("city") or ""
        if c in TRACKED_CITIES:
            by_city.setdefault(c, []).append(r)
    out: dict[str, dict] = {}
    for city in TRACKED_CITIES:
        lst = by_city.get(city)
        if not lst:
            out[city] = {"cheapest": None, "average": None, "count": 0,
                         "station": None, "source": None}
            continue
        prices = [x["price"] for x in lst]
        cheapest = min(lst, key=lambda x: x["price"])
        out[city] = {
            "cheapest": round(min(prices), 3),
            "average": round(sum(prices) / len(prices), 3),
            "count": len(lst),
            "station": cheapest.get("station"),
            "source": cheapest.get("source"),
        }
    return out


async def _scrape_cheapest(fuel: str, executor) -> dict:
    """Run both scrapers in parallel. Returns national cheapest station info
    plus a per-city breakdown (cheapest + average) for TRACKED_CITIES."""
    loop = asyncio.get_event_loop()
    poltt_task = loop.run_in_executor(executor, polttoaine.fetch_prices, fuel)
    tank_tasks = [
        loop.run_in_executor(executor, tankille._scrape_city, c, fuel)
        for c in TRACKED_CITIES
    ]
    poltt, *tanks = await asyncio.gather(
        poltt_task, *tank_tasks, return_exceptions=True
    )
    all_stations = []
    if isinstance(poltt, list):
        all_stations.extend(poltt)
    for t in tanks:
        if isinstance(t, list):
            all_stations.extend(t)
    all_stations = _sane(all_stations)
    if not all_stations:
        return {"price": None, "station": None, "city": None,
                "source": None, "count": 0, "by_city": _city_breakdown([])}
    cheapest = min(all_stations, key=lambda r: r["price"])
    return {
        "price": round(cheapest["price"], 3),
        "station": cheapest.get("station"),
        "city": cheapest.get("city"),
        "address": cheapest.get("address", ""),
        "source": cheapest.get("source"),
        "count": len(all_stations),
        "by_city": _city_breakdown(all_stations),
    }


async def capture_daily(db, executor, fuel: str, region: str = "Suomi",
                        hour: int | None = None) -> dict:
    """One scheduled capture (14:00 or 21:00 Helsinki). Idempotent on
    (date, fuel, region, hour) — re-running the same slot overwrites it."""
    now_hel = datetime.now(HELSINKI)
    today = now_hel.date()
    if hour is None:
        # Snap current Helsinki hour to nearest scheduled slot
        cur_h = now_hel.hour
        hour = min(SCHEDULED_HOURS, key=lambda h: abs(h - cur_h))
    today_iso = today.isoformat()

    # 1) skraapaa
    cheapest = await _scrape_cheapest(fuel, executor)

    # 2) load chronological tracker history (one row per slot)
    tracker_hist = await db.daily_tracker.find(
        {"fuel": fuel, "region": region},
        {"_id": 0},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=600)

    # the "predicted_cheapest_for_today" line on the chart compares the latest
    # prior prediction to this slot's actual. We pick the most recent doc whose
    # (date, hour) is strictly before this one and that has a tomorrow_prediction.
    predicted_for_now = None
    for r in reversed(tracker_hist):
        r_date = r.get("date")
        r_hour = r.get("hour", 20)  # legacy rows treated as evening
        if (r_date, r_hour) < (today_iso, hour):
            predicted_for_now = r.get("prediction_for_tomorrow_cheapest")
            if predicted_for_now is not None:
                break

    # 3) build series for prediction
    series = [(r["date"], r["actual_cheapest"]) for r in tracker_hist
              if r.get("actual_cheapest") is not None]
    if cheapest["price"] is not None:
        series.append((today_iso, cheapest["price"]))

    prediction_tomorrow = None
    prediction_full = None
    if cheapest["price"] is not None and len(series) >= 1:
        dates = [d for d, _ in series]
        prices = [p for _, p in series]
        loop = asyncio.get_event_loop()
        brent_task = loop.run_in_executor(executor, factors_mod.fetch_brent, 30)
        fx_task = loop.run_in_executor(executor, factors_mod.fetch_eur_usd, 30)
        news_task = loop.run_in_executor(executor, news_mod.fetch_news, None, 14, 6)
        brent_series, fx_series, headlines = await asyncio.gather(
            brent_task, fx_task, news_task
        )
        brent_val = factors_mod.latest_value(brent_series)
        fx_val = factors_mod.latest_value(fx_series)
        brent_chg = factors_mod.change_frac(brent_series, 5)
        fx_chg = factors_mod.change_frac(fx_series, 5)

        # Aja AINA koko ennusteputki (predict_tomorrow). Se degradoituu
        # hallitusti vähäisellä datalla: fundamental_anchor toimii live-
        # ankkurista, MA/LR/ES palauttavat None siististi, ja ensemble
        # yhdistää saatavilla olevat. Vanha "<7 pistettä → vain AI" -haara
        # jätti fundamental_anchorin (ja MA/LR/ES:n) kokonaan pois juuri
        # cold-startissa, jolloin niitä eniten tarvitaan.
        full = await predict_mod.predict_tomorrow(
            fuel, dates, prices, brent_val, fx_val,
            live_today_price=cheapest["price"],
            news_headlines=headlines,
            region=region,
            brent_chg=brent_chg,
            eur_usd_chg=fx_chg,
        )
        prediction_tomorrow = full["ensemble"].get("value") or cheapest["price"]
        prediction_full = full

    doc = {
        "date": today_iso,
        "hour": hour,
        "fuel": fuel,
        "region": region,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "actual_cheapest": cheapest["price"],
        "actual_cheapest_station": cheapest.get("station"),
        "actual_cheapest_city": cheapest.get("city"),
        "actual_cheapest_source": cheapest.get("source"),
        "stations_scanned": cheapest.get("count", 0),
        "by_city": cheapest.get("by_city", {}),
        "predicted_cheapest_for_today": predicted_for_now,
        "prediction_for_tomorrow_cheapest": (
            round(prediction_tomorrow, 3) if prediction_tomorrow else None
        ),
        "prediction_full": prediction_full,
    }
    await db.daily_tracker.update_one(
        {"date": today_iso, "hour": hour, "fuel": fuel, "region": region},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def scheduler_loop(db, executor, fuels=("95E10", "diesel")):
    """Background task: sleep until next scheduled run (14:00 / 21:00 Helsinki),
    capture, repeat."""
    logger.info("tracker scheduler started (%s Helsinki)",
                " + ".join(f"{h:02d}:00" for h in SCHEDULED_HOURS))
    while True:
        try:
            now = datetime.now(timezone.utc)
            target = next_scheduled_run(now)
            wait = (target - now).total_seconds()
            target_hel = target.astimezone(HELSINKI)
            logger.info(
                "tracker: sleeping %.0fs until %s Helsinki",
                wait, target_hel.strftime("%Y-%m-%d %H:%M")
            )
            await asyncio.sleep(wait)
            run_hour = target_hel.hour  # 6 or 20
            captured_docs: list[dict] = []
            for fuel in fuels:
                try:
                    doc = await capture_daily(db, executor, fuel, hour=run_hour)
                    captured_docs.append(doc)
                    logger.info(
                        "tracker captured %s @%02dh: actual=%s predicted_tomorrow=%s",
                        fuel, run_hour, doc.get("actual_cheapest"),
                        doc.get("prediction_for_tomorrow_cheapest")
                    )
                except Exception as e:
                    logger.exception("tracker capture failed for %s: %s", fuel, e)
            # send one consolidated push notification per scheduled run
            try:
                notify_mod.send_daily_summary(captured_docs)
            except Exception as e:
                logger.exception("ntfy send failed: %s", e)
        except asyncio.CancelledError:
            logger.info("tracker scheduler stopped")
            return
        except Exception as e:
            logger.exception("scheduler loop error: %s", e)
            await asyncio.sleep(300)
