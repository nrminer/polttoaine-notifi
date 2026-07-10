import asyncio
from datetime import datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

import accuracy_utils
from forecast_contract import HELSINKI


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args):
        return self

    async def to_list(self, length):
        return self.rows[:length]


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, projection):
        rows = self.rows
        for key, expected in query.items():
            if isinstance(expected, dict) and "$gte" in expected:
                rows = [row for row in rows if row.get(key, "") >= expected["$gte"]]
            else:
                rows = [row for row in rows if row.get(key) == expected]
        return _Cursor(rows)


class _Db:
    def __init__(self, tracker_rows):
        self.daily_tracker = _Collection(tracker_rows)
        self.predictions = _Collection([])


def test_city_persistence_backtest_uses_previous_verified_21_capture(monkeypatch):
    monkeypatch.setattr(
        accuracy_utils,
        "helsinki_now",
        lambda: datetime(2026, 7, 10, 12, tzinfo=HELSINKI),
    )
    db = _Db([
        {
            "date": "2026-07-08", "hour": 21, "fuel": "95E10", "region": "Suomi",
            "actual_status": "observed",
            "by_city": {"Turku": {"cheapest": 1.70, "observed": True}},
        },
        {
            "date": "2026-07-09", "hour": 21, "fuel": "95E10", "region": "Suomi",
            "actual_status": "observed",
            "by_city": {"Turku": {"cheapest": 1.72, "observed": True}},
        },
    ])

    rows = asyncio.run(accuracy_utils.realized_prediction_rows(
        db, "95E10", "Turku", days=7,
    ))

    assert rows == [{
        "target_date": "2026-07-09",
        "actual": 1.72,
        "methods": {"persistence": 1.7, "ensemble": 1.7},
        "source": "daily_tracker",
    }]


def test_national_champion_score_does_not_reuse_legacy_ensemble(monkeypatch):
    monkeypatch.setattr(
        accuracy_utils,
        "helsinki_now",
        lambda: datetime(2026, 7, 10, 12, tzinfo=HELSINKI),
    )
    db = _Db([
        {
            "date": "2026-07-08", "hour": 21, "fuel": "95E10", "region": "Suomi",
            "actual_cheapest": 1.70, "actual_status": "observed",
            "prediction_for_tomorrow_cheapest": 1.50,
            "prediction_full": {
                "methods": {"moving_average": {"value": 1.71}},
                "ensemble": {"value": 1.50},
            },
        },
        {
            "date": "2026-07-09", "hour": 21, "fuel": "95E10", "region": "Suomi",
            "actual_cheapest": 1.72, "actual_status": "observed",
        },
    ])

    rows = asyncio.run(accuracy_utils.realized_prediction_rows(
        db, "95E10", "Suomi", days=7,
    ))

    assert "moving_average" not in rows[0]["methods"]
    assert rows[0]["methods"]["persistence"] == 1.70
    assert rows[0]["methods"]["ensemble"] == 1.70
