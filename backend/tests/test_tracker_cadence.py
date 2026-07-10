"""Tests for the 14:00 and 21:00 Helsinki capture cadence."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import sys
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(Path(__file__).parent.parent))

import tracker


class _DailyTracker:
    async def find_one(self, key, projection):
        return {**key, "capture_canonical": True, "actual_cheapest": 1.7}


class _Db:
    daily_tracker = _DailyTracker()


class _RacingDailyTracker:
    def __init__(self):
        self.reads = 0

    async def find_one(self, key, projection):
        self.reads += 1
        if self.reads == 1:
            return None
        return {**key, "capture_canonical": True, "actual_cheapest": 1.7}

    async def update_one(self, *args, **kwargs):
        raise DuplicateKeyError("canonical capture won the race")

    def find(self, *args, **kwargs):
        return _EmptyCursor()


class _EmptyCursor:
    def sort(self, *args):
        return self

    async def to_list(self, length):
        return []


class _RacingDb:
    daily_tracker = _RacingDailyTracker()


def test_next_scheduled_run_uses_same_day_slot(monkeypatch):
    monkeypatch.setattr(tracker, "SCHEDULED_HOURS", (14, 21))
    now_utc = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)  # 12:00 Helsinki

    next_time = tracker.next_scheduled_run(now_utc).astimezone(tracker.HELSINKI)

    assert next_time.date().isoformat() == "2026-06-05"
    assert next_time.hour == 14


def test_next_scheduled_run_wraps_to_tomorrow(monkeypatch):
    monkeypatch.setattr(tracker, "SCHEDULED_HOURS", (14, 21))
    now_utc = datetime(2026, 6, 5, 19, 0, tzinfo=timezone.utc)  # 22:00 Helsinki

    next_time = tracker.next_scheduled_run(now_utc).astimezone(tracker.HELSINKI)

    assert next_time.date().isoformat() == "2026-06-06"
    assert next_time.hour == 14


def test_manual_capture_does_not_overwrite_canonical_slot():
    row = asyncio.run(tracker.capture_daily(
        _Db(), executor=None, fuel="95E10", hour=21, canonical=False,
    ))

    assert row["capture_canonical"] is True
    assert row["actual_cheapest"] == 1.7


def test_manual_capture_loses_race_to_canonical_slot(monkeypatch):
    async def scrape(*args):
        return {"price": None, "by_city": {}, "count": 0}

    monkeypatch.setattr(tracker, "_scrape_cheapest", scrape)
    row = asyncio.run(tracker.capture_daily(
        _RacingDb(), executor=None, fuel="95E10", hour=21, canonical=False,
    ))

    assert row["capture_canonical"] is True
