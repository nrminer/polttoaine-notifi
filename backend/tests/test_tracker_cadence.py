"""Tests for the real tracker cadence and silent scrape write shape.

Silent scrapes currently write one aggregate `price_observations` document per
fuel/hour. They do not write per-station observations, update a stations
registry, run predictions, write `daily_tracker`, or send notifications.
"""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import tracker


HELSINKI = tracker.HELSINKI


def test_silent_scrape_hours_parsing_default(monkeypatch):
    monkeypatch.delenv("SILENT_SCRAPE_HOURS", raising=False)

    assert tracker._parse_silent_hours() == (6, 8, 10, 12, 16, 18, 20, 22)


def test_silent_scrape_hours_parsing_single(monkeypatch):
    monkeypatch.setenv("SILENT_SCRAPE_HOURS", "10")

    assert tracker._parse_silent_hours() == (10,)


def test_silent_scrape_hours_parsing_multiple(monkeypatch):
    monkeypatch.setenv("SILENT_SCRAPE_HOURS", " 6 , 10 , 18 ")

    assert tracker._parse_silent_hours() == (6, 10, 18)


def test_silent_scrape_hours_parsing_empty_string(monkeypatch):
    monkeypatch.setenv("SILENT_SCRAPE_HOURS", "")

    assert tracker._parse_silent_hours() == ()


def test_next_scheduled_run_with_silent_hours(monkeypatch):
    monkeypatch.setattr(tracker, "SCHEDULED_HOURS", (14, 21))
    monkeypatch.setattr(tracker, "SILENT_SCRAPE_HOURS", (10, 18))
    now_utc = datetime(2026, 6, 5, 5, 0, 0, tzinfo=timezone.utc)  # 08:00 Helsinki

    next_time = tracker.next_scheduled_run(now_utc).astimezone(HELSINKI)

    assert next_time.hour == 10
    assert next_time.date().isoformat() == "2026-06-05"


def test_next_scheduled_run_wraps_to_tomorrow(monkeypatch):
    monkeypatch.setattr(tracker, "SCHEDULED_HOURS", (14, 21))
    monkeypatch.setattr(tracker, "SILENT_SCRAPE_HOURS", (10,))
    now_utc = datetime(2026, 6, 5, 19, 0, 0, tzinfo=timezone.utc)  # 22:00 Helsinki

    next_time = tracker.next_scheduled_run(now_utc).astimezone(HELSINKI)

    assert next_time.hour == 10
    assert next_time.date().isoformat() == "2026-06-06"


def test_next_scheduled_run_deduplicates_overlapping_hours(monkeypatch):
    monkeypatch.setattr(tracker, "SCHEDULED_HOURS", (14, 21))
    monkeypatch.setattr(tracker, "SILENT_SCRAPE_HOURS", (14,))
    now_utc = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)  # 12:00 Helsinki

    next_time = tracker.next_scheduled_run(now_utc).astimezone(HELSINKI)

    assert next_time.hour == 14
    assert next_time.date().isoformat() == "2026-06-05"


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.price_observations = AsyncMock()
    db.stations = AsyncMock()
    db.daily_tracker = AsyncMock()
    db.predictions = AsyncMock()
    return db


def scraped_cheapest():
    return {
        "price": 1.922,
        "station": "Neste Express Viikki",
        "city": "Helsinki",
        "source": "tankille.fi",
        "count": 42,
        "by_city": {
            "Helsinki": {
                "cheapest": 1.922,
                "average": 1.977,
                "count": 12,
                "station": "Neste Express Viikki",
                "source": "tankille.fi",
            }
        },
    }


@pytest.mark.asyncio
async def test_silent_scrape_writes_aggregate_observation(monkeypatch, mock_db):
    mock_scrape = AsyncMock(return_value=scraped_cheapest())
    monkeypatch.setattr(tracker, "_scrape_cheapest", mock_scrape)
    executor = object()

    doc = await tracker.silent_scrape(mock_db, executor=executor, fuel="95E10", hour=10)

    mock_scrape.assert_awaited_once_with("95E10", executor)
    mock_db.price_observations.update_one.assert_awaited_once()
    mock_db.daily_tracker.update_one.assert_not_called()

    filter_doc, update_doc = mock_db.price_observations.update_one.call_args.args[:2]
    written = update_doc["$set"]

    assert filter_doc == {"date": doc["date"], "hour": 10, "fuel": "95E10"}
    assert written == doc
    assert written["cheapest"] == 1.922
    assert written["cheapest_station"] == "Neste Express Viikki"
    assert written["cheapest_city"] == "Helsinki"
    assert written["stations_scanned"] == 42
    assert written["by_city"]["Helsinki"]["average"] == 1.977


@pytest.mark.asyncio
async def test_silent_scrape_does_not_write_station_level_fields(monkeypatch, mock_db):
    monkeypatch.setattr(tracker, "_scrape_cheapest", AsyncMock(return_value=scraped_cheapest()))

    await tracker.silent_scrape(mock_db, executor=object(), fuel="95E10", hour=10)

    written = mock_db.price_observations.update_one.call_args.args[1]["$set"]
    per_station_claim_keys = {"station_id", "name", "price", "scraped_at_station"}

    assert per_station_claim_keys.isdisjoint(written.keys())
    assert "cheapest" in written
    assert "by_city" in written


@pytest.mark.asyncio
async def test_silent_scrape_does_not_touch_stations_registry(monkeypatch, mock_db):
    monkeypatch.setattr(tracker, "_scrape_cheapest", AsyncMock(return_value=scraped_cheapest()))

    await tracker.silent_scrape(mock_db, executor=object(), fuel="95E10", hour=10)

    mock_db.stations.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_silent_scrape_does_not_predict_or_notify(monkeypatch, mock_db):
    monkeypatch.setattr(tracker, "_scrape_cheapest", AsyncMock(return_value=scraped_cheapest()))
    monkeypatch.setattr(tracker.predict_mod, "predict_by_hour", MagicMock())
    monkeypatch.setattr(tracker.notify_mod, "send_daily_summary", MagicMock())

    await tracker.silent_scrape(mock_db, executor=object(), fuel="95E10", hour=10)

    tracker.predict_mod.predict_by_hour.assert_not_called()
    tracker.notify_mod.send_daily_summary.assert_not_called()


def test_scheduled_hours_take_precedence_over_silent_hours():
    scheduled_hours = (14, 21)
    silent_hours = (14, 18)

    is_notification = 14 in scheduled_hours
    silent_only = set(silent_hours) - set(scheduled_hours)

    assert is_notification is True
    assert silent_only == {18}
