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
import os
from datetime import date, datetime, timedelta, timezone

import predict as predict_mod
import factors as factors_mod
import news as news_mod
import notify as notify_mod
import tax_events as tax_events_mod
import learn as learn_mod
import price_verification as verification_mod
from pymongo.errors import DuplicateKeyError
from forecast_contract import (
    HELSINKI,
    MODEL_VERSION,
    TARGET_HOUR,
    daily_series,
    target_date,
)
from scrapers import polttoaine, tankille
from validation import filter_fresh_rows, validate_scraped_data

logger = logging.getLogger("bensavahti.tracker")

# Päivittäiset ajastetut captureajat (Helsinki-aika) — ennuste + ilmoitus
SCHEDULED_HOURS = (14, 21)

# Kaupungit joista kerätään halvin + keskihinta jokaisessa capturessa
TRACKED_CITIES = ("Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti")

def helsinki_today() -> date:
    return datetime.now(HELSINKI).date()


def next_scheduled_run(now_utc: datetime | None = None) -> datetime:
    """Return the next scheduled capture in UTC."""
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
        # fallback: huomenna ensimmäinen tunti
        d = (now_hel + timedelta(days=1)).date()
        first_hour = SCHEDULED_HOURS[0]
        candidates.append(datetime.combine(
            d, datetime.min.time(), tzinfo=HELSINKI
        ).replace(hour=first_hour))
    return min(candidates).astimezone(timezone.utc)

def _sane(rows: list) -> list:
    """Drop stale observations, parse errors, and statistical outliers."""
    return filter_fresh_rows(validate_scraped_data(rows, source="tracker"))


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
                         "station": None, "source": None, "observed": False}
            continue
        prices = [x["price"] for x in lst]
        cheapest = min(lst, key=lambda x: x["price"])
        source_mins = {}
        for row in lst:
            source = row.get("source") or "unknown"
            source_mins[source] = min(source_mins.get(source, row["price"]), row["price"])
        out[city] = {
            "cheapest": round(min(prices), 3),
            "average": round(sum(prices) / len(prices), 3),
            "count": len(lst),
            "station": cheapest.get("station"),
            "source": cheapest.get("source"),
            "chain": cheapest.get("chain"),
            "age_hours": cheapest.get("age_hours"),
            "sources_count": len(source_mins),
            "source_spread": round(max(source_mins.values()) - min(source_mins.values()), 3),
            "observed": True,
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
                        hour: int | None = None, canonical: bool = False) -> dict:
    """One scheduled capture (14:00 or 21:00 Helsinki). Idempotent on
    (date, fuel, region, hour) - re-running the same slot overwrites it."""
    now_hel = datetime.now(HELSINKI)
    today = now_hel.date()
    if hour is None:
        # Snap current Helsinki hour to nearest scheduled slot
        cur_h = now_hel.hour
        hour = min(SCHEDULED_HOURS, key=lambda h: abs(h - cur_h))
    today_iso = today.isoformat()
    capture_key = {"date": today_iso, "hour": hour, "fuel": fuel, "region": region}

    if not canonical:
        existing = await db.daily_tracker.find_one(capture_key, {"_id": 0})
        if existing and existing.get("capture_canonical") is True:
            return existing

    # 1) skraapaa
    cheapest = await _scrape_cheapest(fuel, executor)
    
    # 1b) SAFETY: Verify the scraped price before accepting it
    if cheapest["price"] is not None:
        verification = await verification_mod.verify_price(
            cheapest["price"], fuel, db, region, date_iso=today_iso
        )
        
        if not verification.is_valid:
            original_scraped_price = cheapest["price"]
            logger.error(
                "⚠️  PRICE VERIFICATION FAILED for %s on %s @%02dh: %s",
                fuel, today_iso, hour, verification.reason
            )
            logger.error("   Scraped price: %.3f EUR/L", cheapest["price"])
            logger.error("   Station: %s (%s)", 
                        cheapest.get("station"), cheapest.get("city"))
            
            # Get historical context for logging
            context = await verification_mod.get_verification_context(db, fuel, region)
            logger.error("   Historical context: recent_avg=%.3f, last=%.3f, count=%d",
                        context.get("recent_avg") or 0,
                        context.get("last_price") or 0,
                        context.get("capture_count", 0))
            
            # Use suggested alternative if available, otherwise use last known good price
            if verification.suggested_alternative:
                logger.warning("   → Using suggested alternative: %.3f EUR/L", 
                              verification.suggested_alternative)
                cheapest["price"] = verification.suggested_alternative
                cheapest["verification_override"] = True
                cheapest["original_scraped_price"] = original_scraped_price
            elif context.get("last_price"):
                logger.warning("   → Using last known good price: %.3f EUR/L", 
                              context["last_price"])
                cheapest["price"] = context["last_price"]
                cheapest["verification_override"] = True
                cheapest["original_scraped_price"] = original_scraped_price
            else:
                logger.error("   → No fallback available, setting price to None")
                cheapest["price"] = None
                cheapest["original_scraped_price"] = original_scraped_price
                cheapest["verification_failed"] = True
        else:
            logger.info("✓ Price verification passed for %s: %.3f EUR/L", 
                       fuel, cheapest["price"])

    # 2) load chronological tracker history (one row per slot)
    tracker_hist = await db.daily_tracker.find(
        {"fuel": fuel, "region": region},
        {"_id": 0},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=600)

    # Compare only yesterday's canonical 21:00 forecast with today's 21:00 actual.
    predicted_for_now = None
    source_date = (today - timedelta(days=1)).isoformat()
    if hour == TARGET_HOUR:
        source = next(
            (row for row in reversed(tracker_hist)
             if row.get("date") == source_date and row.get("hour") == TARGET_HOUR),
            None,
        )
        predicted_for_now = (source or {}).get("prediction_for_tomorrow_cheapest")

    actual_status = (
        "missing" if cheapest["price"] is None
        else "imputed" if cheapest.get("verification_override")
        else "observed"
    )

    # 3) build series for prediction
    series = daily_series(tracker_hist, region)
    if cheapest["price"] is not None and actual_status == "observed":
        series = sorted({**dict(series), today_iso: cheapest["price"]}.items())

    prediction_tomorrow = None
    prediction_full = None
    
    if cheapest["price"] is not None and actual_status == "observed" and len(series) >= 1:
        dates = [d for d, _ in series]
        prices = [p for _, p in series]
        loop = asyncio.get_event_loop()
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

        # Tunnetut veromuutokset: huomenna voimaan tuleva askel + 30 pv ikkuna
        today_iso_dt = today_iso
        target_iso = target_date(now_hel).isoformat()
        tax_step = tax_events_mod.applicable_step(fuel, today_iso_dt, target_iso)
        tax_step_eur_l = tax_step["delta_eur_per_l"] if tax_step else None
        tax_upcoming = tax_events_mod.upcoming(today_iso_dt, lookahead_days=30, fuel=fuel)

        track_rec = await learn_mod.track_record(db, fuel, region, days=30)
        mae = {
            method: {"n": stats.get("n", 0), "mae": stats.get("mae")}
            for method, stats in track_rec["stats"].items()
        }
        
        # Check for breaking news severity (within last 6 hours)
        breaking_severity = news_mod.get_max_severity(headlines, max_age_hours=6.0)
        if breaking_severity > 0:
            logger.warning("⚠️  BREAKING NEWS detected (severity=%d) - adjusting price clamp", breaking_severity)
            breaking_items = news_mod.get_breaking_news_items(headlines, max_age_hours=6.0)
            for item in breaking_items:
                logger.warning("   • [%d] %s (%s, %.1fh ago)", 
                              item.get("severity", 0),
                              item.get("title", "")[:80], 
                              item.get("source", ""),
                              item.get("age_hours", 0))
        
        full = await predict_mod.predict_tomorrow(
            fuel, dates, prices,
            brent=brent_val,
            eur_usd=fx_val,
            live_today_price=cheapest["price"],
            news_headlines=headlines,
            region=region,
            brent_chg=brent_chg,
            eur_usd_chg=fx_chg,
            method_mae=mae,
            product_usd_gal=product_val,
            product_chg=product_chg,
            product_label=product_label,
            crack_eur_l=crack_val,
            tax_events=tax_upcoming,
            tax_step_eur_l=tax_step_eur_l,
            track_record=track_rec,
            breaking_news_severity=breaking_severity,
            target_date_iso=target_iso,
        )
        prediction_tomorrow = full["ensemble"].get("value")
        prediction_full = full

    target_iso = target_date(now_hel).isoformat()
    captured_at = datetime.now(timezone.utc).isoformat()
    by_city = cheapest.get("by_city", {})
    for city in TRACKED_CITIES:
        city_row = by_city.get(city) or {}
        value = city_row.get("cheapest")
        city_row["prediction_for_tomorrow_cheapest"] = value
        city_row["prediction_target_date"] = target_iso
        city_row["prediction_target_hour"] = TARGET_HOUR

    doc = {
        "date": today_iso,
        "hour": hour,
        "fuel": fuel,
        "region": region,
        "captured_at": captured_at,
        "actual_cheapest": cheapest["price"],
        "actual_cheapest_station": cheapest.get("station"),
        "actual_cheapest_city": cheapest.get("city"),
        "actual_cheapest_source": cheapest.get("source"),
        "stations_scanned": cheapest.get("count", 0),
        "by_city": by_city,
        "predicted_cheapest_for_today": predicted_for_now,
        "prediction_for_tomorrow_cheapest": (
            round(prediction_tomorrow, 3) if prediction_tomorrow else None
        ),
        "prediction_full": prediction_full,
        "prediction_target_date": target_iso,
        "prediction_target_hour": TARGET_HOUR,
        "prediction_issued_hour": hour,
        "prediction_model_version": MODEL_VERSION,
        "prediction_evaluation_eligible": canonical and hour == TARGET_HOUR,
        "capture_canonical": canonical,
        # Verification metadata (if price was overridden)
        "verification_override": cheapest.get("verification_override", False),
        "original_scraped_price": cheapest.get("original_scraped_price"),
        "verification_failed": cheapest.get("verification_failed", False),
        "actual_status": actual_status,
    }
    write_filter = capture_key if canonical else {
        **capture_key,
        "capture_canonical": {"$ne": True},
    }
    try:
        await db.daily_tracker.update_one(write_filter, {"$set": doc}, upsert=True)
    except DuplicateKeyError:
        existing = await db.daily_tracker.find_one(capture_key, {"_id": 0})
        if existing and existing.get("capture_canonical") is True:
            return existing
        raise
    for city, city_row in by_city.items():
        value = city_row.get("prediction_for_tomorrow_cheapest")
        if value is None:
            continue
        persistence = predict_mod.persistence_forecast(value)
        canonical_prediction = {
            "target_hour": TARGET_HOUR,
            "issued_at": captured_at,
            "issued_hour": hour,
            "model_version": MODEL_VERSION,
            "evaluation_eligible": canonical and hour == TARGET_HOUR,
            "methods": {"persistence": value},
            "methods_full": {"persistence": persistence},
            "ensemble": value,
            "ensemble_full": persistence,
        }
        prediction_doc = {
            "target_date": target_iso,
            "target_hour": TARGET_HOUR,
            "fuel": fuel,
            "region": city,
            "generated_at": captured_at,
            "issued_at": captured_at,
            "issued_hour": hour,
            "model_version": MODEL_VERSION,
            "evaluation_eligible": canonical and hour == TARGET_HOUR,
            "methods": {"persistence": value},
            "methods_full": {"persistence": persistence},
            "ensemble": value,
            "ensemble_full": persistence,
            "current_price": value,
            "live_anchor": value,
            "data_sources": {
                "source": "daily_tracker_city_capture",
                "combined_points": len(daily_series(tracker_hist + [doc], city)),
                "sources_count": city_row.get("sources_count"),
                "stations_count": city_row.get("count"),
                "most_recent_scrape": captured_at,
            },
        }
        if canonical and hour == TARGET_HOUR:
            prediction_doc["canonical"] = canonical_prediction
        await db.predictions.update_one(
            {"target_date": target_iso, "fuel": fuel, "region": city},
            {"$set": prediction_doc},
            upsert=True,
        )
    return doc


async def scheduler_loop(db, executor, fuels=("95E10", "diesel")):
    """Run full captures and notifications at the scheduled Helsinki hours."""
    logger.info(
        "scheduler started: %s Helsinki time",
        ", ".join(f"{h:02d}:00" for h in SCHEDULED_HOURS),
    )

    while True:
        try:
            now = datetime.now(timezone.utc)
            target = next_scheduled_run(now)
            wait = (target - now).total_seconds()
            target_hel = target.astimezone(HELSINKI)
            run_hour = target_hel.hour

            logger.info(
                "scheduler: sleeping %.0fs until %s Helsinki",
                wait, target_hel.strftime("%Y-%m-%d %H:%M")
            )
            await asyncio.sleep(wait)

            for fuel in fuels:
                try:
                    doc = await capture_daily(
                        db, executor, fuel, hour=run_hour, canonical=True
                    )
                    logger.info(
                        "capture %s @%02dh: actual=%s predicted_tomorrow=%s",
                        fuel, run_hour, doc.get("actual_cheapest"),
                        doc.get("prediction_for_tomorrow_cheapest")
                    )
                except Exception as e:
                    logger.exception("capture failed for %s: %s", fuel, e)

            try:
                notify_mod.send_daily_summary()
            except Exception as e:
                logger.exception("ntfy send failed: %s", e)

        except asyncio.CancelledError:
            logger.info("scheduler stopped")
            return
        except Exception as e:
            logger.exception("scheduler loop error: %s", e)
            await asyncio.sleep(300)

def _news_signature(items) -> frozenset:
    """Vakaakuvaus suodatetuista uutisotsikoista (news_mod suodattaa jo
    polttoaine/öljy-avainsanoilla). Muutos = uutta relevanttia uutista."""
    return frozenset(
        (it.get("title") or "").strip().lower()
        for it in (items or [])
        if (it.get("title") or "").strip()
    )


async def news_watch_loop(db, executor, fuels, predict_fn,
                          poll_seconds: int | None = None,
                          min_rerun_seconds: int = 900):
    """Tarkkaile polttoaine-/öljyuutisia ja aja AI-analyysi (ennuste)
    uudelleen kun suodatettu otsikkojoukko MUUTTUU.

    - `predict_fn(fuel)` : async-callable joka ajaa tuoreen ennusteen,
      tallentaa sen `predictions`-kokoelmaan ja päivittää UI:n lukeman.
    - Poll-väli `NEWS_WATCH_SECONDS` (oletus 1800 s); 0 = pois käytöstä.
    - `min_rerun_seconds` rajoittaa LLM-kustannusta: ennustetta ei aja
      uudelleen useammin kuin tämän välein vaikka uutisia tulisi tiuhaan.
    - Vaatii ANTHROPIC_AUTH_TOKEN:n (muuten AI-osa ei päivity → ei mieltä ajaa).
    """
    if not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        logger.info("news-watch disabled (ANTHROPIC_AUTH_TOKEN missing)")
        return
    if poll_seconds is None:
        try:
            poll_seconds = int(os.environ.get("NEWS_WATCH_SECONDS", "1800"))
        except ValueError:
            poll_seconds = 1800
    if poll_seconds <= 0:
        logger.info("news-watch disabled (NEWS_WATCH_SECONDS<=0)")
        return

    logger.info("news-watch started (poll %ds, min rerun gap %ds)",
                poll_seconds, min_rerun_seconds)
    loop = asyncio.get_event_loop()
    applied_sig: frozenset | None = None
    last_rerun = 0.0
    last_breaking_sig: frozenset | None = None

    while True:
        try:
            items = await loop.run_in_executor(
                executor, news_mod.fetch_news, None, 14, 12
            )
            sig = _news_signature(items)
            
            # Check for breaking news (separate from regular news changes)
            has_breaking = news_mod.has_breaking_news(items, max_age_hours=6.0)
            breaking_items = news_mod.get_breaking_news_items(items, max_age_hours=6.0)
            breaking_sig = frozenset(
                (it.get("title") or "").strip().lower()
                for it in breaking_items
            ) if breaking_items else frozenset()

            # Ensimmäinen kierros: aseta perustaso, ÄLÄ aja uudelleen
            # (vältetään rerun-ryöppy joka uudelleenkäynnistyksessä).
            if applied_sig is None:
                applied_sig = sig
                last_breaking_sig = breaking_sig
                logger.info("news-watch baseline set (%d headlines, %d breaking)", 
                           len(sig), len(breaking_sig))
                await asyncio.sleep(poll_seconds)
                continue

            now = asyncio.get_event_loop().time()
            
            # PRIORITY 1: Breaking news triggers immediate rerun (ignores throttle)
            if has_breaking and breaking_sig != last_breaking_sig:
                new_breaking = len(breaking_sig - (last_breaking_sig or frozenset()))
                logger.warning("🚨 BREAKING NEWS detected (%d new) → immediate prediction rerun!", 
                              new_breaking)
                for item in breaking_items:
                    if (item.get("title") or "").strip().lower() not in (last_breaking_sig or frozenset()):
                        logger.warning("   • %s (%s)", 
                                      item.get("title", "")[:100], 
                                      item.get("source", ""))
                
                for fuel in fuels:
                    try:
                        await predict_fn(fuel)
                        logger.info("news-watch reran prediction for %s (BREAKING NEWS)", fuel)
                    except Exception as e:
                        logger.warning("news-watch predict failed for %s: %s", fuel, e)
                
                applied_sig = sig
                last_breaking_sig = breaking_sig
                last_rerun = now
                
            # PRIORITY 2: Regular news change (throttled)
            elif sig != applied_sig and (now - last_rerun) >= min_rerun_seconds:
                new_n = len(sig - applied_sig)
                logger.info("news changed (%d new headlines) → rerun AI/predict",
                            new_n)
                for fuel in fuels:
                    try:
                        await predict_fn(fuel)
                        logger.info("news-watch reran prediction for %s", fuel)
                    except Exception as e:
                        logger.warning("news-watch predict failed for %s: %s",
                                        fuel, e)
                applied_sig = sig
                last_breaking_sig = breaking_sig
                last_rerun = now
            elif sig != applied_sig:
                logger.info("news changed but throttled (min %ds gap) — "
                            "will rerun on a later tick", min_rerun_seconds)

            await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            logger.info("news-watch stopped")
            return
        except Exception as e:
            logger.exception("news-watch loop error: %s", e)
            await asyncio.sleep(300)
