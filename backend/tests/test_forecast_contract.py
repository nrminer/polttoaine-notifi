from datetime import datetime, timezone
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

from forecast_contract import canonical_age_hours, daily_series, target_date


def test_target_date_uses_helsinki_calendar_day():
    before_midnight_utc = datetime(2026, 7, 10, 22, 30, tzinfo=timezone.utc)

    assert target_date(before_midnight_utc).isoformat() == "2026-07-12"
    assert canonical_age_hours("2026-07-10", before_midnight_utc) == 4.5


def test_daily_series_uses_verified_21_capture_and_city_values():
    rows = [
        {
            "date": "2026-07-09", "hour": 21, "actual_cheapest": 1.61,
            "actual_status": "observed",
            "by_city": {"Turku": {"cheapest": 1.70, "observed": True}},
        },
        {
            "date": "2026-07-10", "hour": 14, "actual_cheapest": 1.58,
            "actual_status": "observed",
            "by_city": {"Turku": {"cheapest": 1.68, "observed": True}},
        },
        {
            "date": "2026-07-10", "hour": 21, "actual_cheapest": 1.59,
            "actual_status": "imputed", "verification_override": True,
            "by_city": {"Turku": {"cheapest": 1.69, "observed": True}},
        },
        {
            "date": "2026-07-11", "hour": 21, "actual_cheapest": 1.60,
            "actual_status": "observed", "capture_canonical": False,
            "by_city": {"Turku": {"cheapest": 1.71, "observed": True}},
        },
    ]

    assert daily_series(rows, "Suomi") == [("2026-07-09", 1.61)]
    assert daily_series(rows, "Turku") == [
        ("2026-07-09", 1.70),
        ("2026-07-10", 1.69),
    ]
