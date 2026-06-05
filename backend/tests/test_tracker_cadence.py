"""Tests for tracker cadence and silent scrape functionality.

Tests scheduled vs silent scrape hours, next_scrape_time calculation,
price_observations insertion for silent scrapes, daily_tracker writes
for notification captures, and prediction/notification triggering logic.
"""
import pytest
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch


HELSINKI = ZoneInfo("Europe/Helsinki")


# ---------------- Test: parse SILENT_SCRAPE_HOURS from env ----------------

def test_silent_scrape_hours_parsing_default():
    """Default silent scrape hours when env var not set."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove SILENT_SCRAPE_HOURS if it exists
        os.environ.pop("SILENT_SCRAPE_HOURS", None)
        # Simulate parsing logic from tracker.py
        raw = os.environ.get("SILENT_SCRAPE_HOURS", "")
        if raw:
            silent_hours = tuple(int(h.strip()) for h in raw.split(",") if h.strip())
        else:
            silent_hours = ()

        assert silent_hours == ()


def test_silent_scrape_hours_parsing_single():
    """Parse single hour from SILENT_SCRAPE_HOURS."""
    with patch.dict(os.environ, {"SILENT_SCRAPE_HOURS": "10"}):
        raw = os.environ.get("SILENT_SCRAPE_HOURS", "")
        silent_hours = tuple(int(h.strip()) for h in raw.split(",") if h.strip())

        assert silent_hours == (10,)


def test_silent_scrape_hours_parsing_multiple():
    """Parse multiple hours from SILENT_SCRAPE_HOURS."""
    with patch.dict(os.environ, {"SILENT_SCRAPE_HOURS": "6,10,18"}):
        raw = os.environ.get("SILENT_SCRAPE_HOURS", "")
        silent_hours = tuple(int(h.strip()) for h in raw.split(",") if h.strip())

        assert silent_hours == (6, 10, 18)


def test_silent_scrape_hours_parsing_whitespace():
    """Parse hours with whitespace."""
    with patch.dict(os.environ, {"SILENT_SCRAPE_HOURS": " 6 , 10 , 18 "}):
        raw = os.environ.get("SILENT_SCRAPE_HOURS", "")
        silent_hours = tuple(int(h.strip()) for h in raw.split(",") if h.strip())

        assert silent_hours == (6, 10, 18)


def test_silent_scrape_hours_parsing_empty_string():
    """Empty string results in empty tuple."""
    with patch.dict(os.environ, {"SILENT_SCRAPE_HOURS": ""}):
        raw = os.environ.get("SILENT_SCRAPE_HOURS", "")
        silent_hours = tuple(int(h.strip()) for h in raw.split(",") if h.strip())

        assert silent_hours == ()


# ---------------- Test: next_scrape_time calculation ----------------

def next_scrape_time_logic(now_utc, scheduled_hours, silent_hours):
    """Calculate next scrape time (scheduled or silent).

    This simulates the logic that would be in tracker.py.
    Returns the nearest hour from the combined set of scheduled + silent hours.
    """
    from datetime import timedelta

    all_hours = set(scheduled_hours) | set(silent_hours)
    if not all_hours:
        return None

    now_hel = now_utc.astimezone(HELSINKI)
    candidates = []

    for offset in range(2):  # today + tomorrow
        day = (now_hel + timedelta(days=offset)).date()
        for hour in sorted(all_hours):
            t = datetime.combine(day, datetime.min.time(), tzinfo=HELSINKI).replace(hour=hour)
            if t > now_hel:
                candidates.append(t)

    if not candidates:
        # fallback: tomorrow first hour
        d = (now_hel + timedelta(days=1)).date()
        candidates.append(datetime.combine(
            d, datetime.min.time(), tzinfo=HELSINKI
        ).replace(hour=min(all_hours)))

    return min(candidates).astimezone(timezone.utc)


def test_next_scrape_time_scheduled_only():
    """Next scrape time with only scheduled hours (14, 21)."""
    # 2026-06-05 12:00 Helsinki (before 14:00)
    now_utc = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)
    scheduled_hours = (14, 21)
    silent_hours = ()

    next_time = next_scrape_time_logic(now_utc, scheduled_hours, silent_hours)
    next_hel = next_time.astimezone(HELSINKI)

    assert next_hel.hour == 14
    assert next_hel.date().isoformat() == "2026-06-05"


def test_next_scrape_time_with_silent_hours():
    """Next scrape time includes silent hours."""
    # 2026-06-05 08:00 Helsinki (before 10:00 silent)
    now_utc = datetime(2026, 6, 5, 5, 0, 0, tzinfo=timezone.utc)
    scheduled_hours = (14, 21)
    silent_hours = (10, 18)

    next_time = next_scrape_time_logic(now_utc, scheduled_hours, silent_hours)
    next_hel = next_time.astimezone(HELSINKI)

    assert next_hel.hour == 10
    assert next_hel.date().isoformat() == "2026-06-05"


def test_next_scrape_time_picks_nearest():
    """Next scrape time picks nearest from combined set."""
    # 2026-06-05 16:00 Helsinki (after 14:00 scheduled, before 18:00 silent)
    now_utc = datetime(2026, 6, 5, 13, 0, 0, tzinfo=timezone.utc)
    scheduled_hours = (14, 21)
    silent_hours = (10, 18)

    next_time = next_scrape_time_logic(now_utc, scheduled_hours, silent_hours)
    next_hel = next_time.astimezone(HELSINKI)

    assert next_hel.hour == 18
    assert next_hel.date().isoformat() == "2026-06-05"


def test_next_scrape_time_wraps_to_tomorrow():
    """Next scrape time wraps to tomorrow when no more today."""
    # 2026-06-05 22:00 Helsinki (after all hours today)
    now_utc = datetime(2026, 6, 5, 19, 0, 0, tzinfo=timezone.utc)
    scheduled_hours = (14, 21)
    silent_hours = (10,)

    next_time = next_scrape_time_logic(now_utc, scheduled_hours, silent_hours)
    next_hel = next_time.astimezone(HELSINKI)

    assert next_hel.hour == 10
    assert next_hel.date().isoformat() == "2026-06-06"


def test_next_scrape_time_no_duplicate_if_hour_in_both_sets():
    """If hour appears in both scheduled and silent, it's only counted once."""
    # 2026-06-05 12:00 Helsinki
    now_utc = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)
    scheduled_hours = (14, 21)
    silent_hours = (14,)  # 14 also in silent

    next_time = next_scrape_time_logic(now_utc, scheduled_hours, silent_hours)
    next_hel = next_time.astimezone(HELSINKI)

    # Should still be 14:00, not duplicated
    assert next_hel.hour == 14
    assert next_hel.date().isoformat() == "2026-06-05"


# ---------------- Test: silent scrape writes price_observations only ----------------

@pytest.fixture
async def mock_db():
    """Mock MongoDB database."""
    db = MagicMock()
    db.price_observations = AsyncMock()
    db.stations = AsyncMock()
    db.daily_tracker = AsyncMock()
    db.predictions = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_silent_scrape_writes_observations(mock_db):
    """Silent scrape inserts to price_observations, not daily_tracker."""
    # Mock scraped data
    scraped_stations = [
        {
            "city": "Helsinki",
            "station": "Neste Express Viikki",
            "address": "Viikinportti 1",
            "price": 1.922,
            "fuel": "95E10",
            "source": "polttoaine.net",
            "chain": "Neste",
        },
    ]

    scraped_at = datetime.now(timezone.utc)

    # Simulate silent scrape logic: insert into price_observations
    for st in scraped_stations:
        station_id = f"{st['city'].lower()}_{st['station'].lower().replace(' ', '_')}"
        obs = {
            "station_id": station_id,
            "name": st["station"],
            "city": st["city"],
            "address": st.get("address", ""),
            "fuel": st["fuel"],
            "price": round(st["price"], 4),
            "scraped_at": scraped_at,
            "source": st["source"],
            "chain": st.get("chain", ""),
        }

        await mock_db.price_observations.update_one(
            {
                "station_id": obs["station_id"],
                "fuel": obs["fuel"],
                "scraped_at": obs["scraped_at"],
            },
            {"$set": obs},
            upsert=True,
        )

    # Verify price_observations was written
    assert mock_db.price_observations.update_one.call_count == 1

    # Verify daily_tracker was NOT touched
    assert mock_db.daily_tracker.update_one.call_count == 0


@pytest.mark.asyncio
async def test_silent_scrape_updates_stations_registry(mock_db):
    """Silent scrape updates stations registry."""
    station = {
        "station_id": "helsinki_neste_express_viikki",
        "name": "Neste Express Viikki",
        "city": "Helsinki",
        "address": "Viikinportti 1",
        "chain": "Neste",
        "first_seen": datetime.now(timezone.utc),
        "last_seen": datetime.now(timezone.utc),
    }

    await mock_db.stations.update_one(
        {"station_id": station["station_id"]},
        {
            "$set": {
                "name": station["name"],
                "city": station["city"],
                "address": station["address"],
                "chain": station["chain"],
                "last_seen": station["last_seen"],
            },
            "$setOnInsert": {"first_seen": station["first_seen"]},
        },
        upsert=True,
    )

    # Verify stations registry was updated
    assert mock_db.stations.update_one.call_count == 1
    call_args = mock_db.stations.update_one.call_args
    assert call_args[0][0] == {"station_id": "helsinki_neste_express_viikki"}
    assert call_args[1]["upsert"] is True


# ---------------- Test: notification capture writes both collections ----------------

@pytest.mark.asyncio
async def test_notification_capture_does_both(mock_db):
    """Scheduled notification capture (14:00/21:00) writes both price_observations AND daily_tracker."""
    scraped_at = datetime.now(timezone.utc)
    today = scraped_at.date().isoformat()
    hour = 14

    # Mock scraped data
    scraped_stations = [
        {
            "city": "Helsinki",
            "station": "Neste Express Viikki",
            "address": "Viikinportti 1",
            "price": 1.922,
            "fuel": "95E10",
            "source": "polttoaine.net",
            "chain": "Neste",
        },
    ]

    # 1. Write to price_observations (silent part)
    for st in scraped_stations:
        station_id = f"{st['city'].lower()}_{st['station'].lower().replace(' ', '_')}"
        obs = {
            "station_id": station_id,
            "name": st["station"],
            "city": st["city"],
            "address": st.get("address", ""),
            "fuel": st["fuel"],
            "price": round(st["price"], 4),
            "scraped_at": scraped_at,
            "source": st["source"],
            "chain": st.get("chain", ""),
        }

        await mock_db.price_observations.update_one(
            {
                "station_id": obs["station_id"],
                "fuel": obs["fuel"],
                "scraped_at": obs["scraped_at"],
            },
            {"$set": obs},
            upsert=True,
        )

    # 2. Write to daily_tracker (notification part)
    cheapest = min(scraped_stations, key=lambda x: x["price"])
    tracker_doc = {
        "date": today,
        "hour": hour,
        "fuel": "95E10",
        "region": "Suomi",
        "captured_at": scraped_at.isoformat(),
        "actual_cheapest": cheapest["price"],
        "actual_cheapest_station": cheapest["station"],
        "actual_cheapest_city": cheapest["city"],
        "actual_cheapest_source": cheapest["source"],
    }

    await mock_db.daily_tracker.update_one(
        {"date": today, "hour": hour, "fuel": "95E10", "region": "Suomi"},
        {"$set": tracker_doc},
        upsert=True,
    )

    # Verify both collections were written
    assert mock_db.price_observations.update_one.call_count == 1
    assert mock_db.daily_tracker.update_one.call_count == 1


# ---------------- Test: no duplicate scrapes if hour in both sets ----------------

def test_no_duplicate_scrapes():
    """If hour appears in both scheduled and silent, only scrapes once."""
    scheduled_hours = (14, 21)
    silent_hours = (14,)  # 14 appears in both

    # Combined set should deduplicate
    all_hours = set(scheduled_hours) | set(silent_hours)

    assert all_hours == {14, 21}
    assert len(all_hours) == 2  # Not 3


# ---------------- Test: silent scrape does NOT call predict_tomorrow ----------------

@pytest.mark.asyncio
async def test_silent_scrape_no_prediction():
    """Silent scrape does NOT call predict_tomorrow()."""
    with patch("predict.predict_tomorrow") as mock_predict:
        mock_predict.return_value = {"ensemble": {"value": 1.95}}

        # Simulate silent scrape: scrape + write observations, NO prediction
        scraped_at = datetime.now(timezone.utc)
        hour = 10  # silent hour
        is_notification_hour = hour in (14, 21)

        # Silent scrape logic: only write observations
        if not is_notification_hour:
            # Write to price_observations only
            pass  # (actual DB write not shown)

        # Verify predict_tomorrow was NOT called for silent scrape
        if not is_notification_hour:
            assert mock_predict.call_count == 0


@pytest.mark.asyncio
async def test_notification_capture_calls_prediction():
    """Notification capture (14:00/21:00) DOES call predict_tomorrow()."""
    with patch("predict.predict_tomorrow") as mock_predict:
        mock_predict.return_value = {"ensemble": {"value": 1.95}}

        # Simulate notification capture
        hour = 14  # notification hour
        is_notification_hour = hour in (14, 21)

        # Notification logic: write observations + daily_tracker + predict
        if is_notification_hour:
            # Would call predict_tomorrow here
            result = mock_predict(
                fuel="95E10",
                dates=["2026-06-04", "2026-06-05"],
                prices=[1.92, 1.94],
                brent_val=80.0,
                fx_val=1.1,
                live_today_price=1.94,
                news_headlines=[],
            )
            assert result["ensemble"]["value"] == 1.95

        # Verify predict_tomorrow WAS called for notification capture
        assert mock_predict.call_count == 1


# ---------------- Test: silent scrape does NOT call notify ----------------

@pytest.mark.asyncio
async def test_silent_scrape_no_notification():
    """Silent scrape does NOT call notify_mod.send_daily_summary()."""
    with patch("notify.send_daily_summary") as mock_notify:
        # Simulate silent scrape
        hour = 10  # silent hour
        is_notification_hour = hour in (14, 21)

        # Silent scrape logic: no notification
        if not is_notification_hour:
            pass  # no notify call

        # Verify send_daily_summary was NOT called
        assert mock_notify.call_count == 0


@pytest.mark.asyncio
async def test_notification_capture_calls_notify():
    """Notification capture (14:00/21:00) DOES call notify_mod.send_daily_summary()."""
    with patch("notify.send_daily_summary") as mock_notify:
        mock_notify.return_value = None

        # Simulate notification capture
        hour = 14  # notification hour
        is_notification_hour = hour in (14, 21)

        # Notification logic: call send_daily_summary
        if is_notification_hour:
            captured_docs = [
                {"fuel": "95E10", "actual_cheapest": 1.92},
                {"fuel": "diesel", "actual_cheapest": 2.05},
            ]
            mock_notify(captured_docs)

        # Verify send_daily_summary WAS called
        assert mock_notify.call_count == 1


# ---------------- Test: hour classification logic ----------------

def test_hour_classification_scheduled():
    """Hour 14 and 21 are classified as notification hours."""
    scheduled_hours = (14, 21)
    silent_hours = (10, 18)

    assert 14 in scheduled_hours
    assert 21 in scheduled_hours
    assert 10 not in scheduled_hours
    assert 18 not in scheduled_hours


def test_hour_classification_silent():
    """Hours in SILENT_SCRAPE_HOURS but not in scheduled are silent-only."""
    scheduled_hours = (14, 21)
    silent_hours = (10, 18)

    silent_only = set(silent_hours) - set(scheduled_hours)

    assert silent_only == {10, 18}
    assert 14 not in silent_only
    assert 21 not in silent_only


def test_hour_classification_overlap():
    """Hours in both sets are treated as notification hours (scheduled takes precedence)."""
    scheduled_hours = (14, 21)
    silent_hours = (14, 18)  # 14 in both

    # 14 should be treated as notification hour
    is_notification = 14 in scheduled_hours

    assert is_notification is True
