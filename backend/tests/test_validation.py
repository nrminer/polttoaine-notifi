from pathlib import Path
from datetime import datetime, timezone
import importlib
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from validation import filter_fresh_rows, validate_scraped_data


def test_validate_scraped_data_rejects_non_numeric_and_bounds():
    rows = [
        {"price": 1.922},
        {"price": "1.922"},
        {"price": 0.42},
        {"price": 4.2},
        {},
    ]

    assert validate_scraped_data(rows, source="test") == [{"price": 1.922}]


def test_validate_scraped_data_drops_city_batch_outliers():
    rows = [
        {"price": p}
        for p in [1.444, 1.522, 1.919, 2.012, 2.031, 2.082, 2.099, 2.099, 2.099, 2.1]
    ]

    clean = validate_scraped_data(rows, source="tankille-espoo")
    prices = [row["price"] for row in clean]

    assert min(prices) == 1.919
    assert 1.444 not in prices
    assert 1.522 not in prices


def test_validate_scraped_data_rejects_source_lows_that_break_city_batch():
    rows = [
        {"price": p}
        for p in [1.611, 1.755, 1.912, 2.055, 2.088, 2.155, 2.158, 2.169, 2.169, 2.188]
    ]

    clean = validate_scraped_data(rows, source="tankille-espoo-diesel")
    prices = [row["price"] for row in clean]

    assert min(prices) == 1.912
    assert 1.611 not in prices
    assert 1.755 not in prices


def test_filter_fresh_rows_rejects_stale_and_unknown_observations():
    rows = [
        {"price": 1.7, "age_hours": 2},
        {"price": 1.8, "age_hours": 25},
        {"price": 1.9},
    ]

    assert filter_fresh_rows(rows) == [{"price": 1.7, "age_hours": 2}]


def test_regional_tankille_cities_match_displayed_regions(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("DB_NAME", "bensavahti_test")

    server = importlib.import_module("server")

    assert server._regional_tankille_cities() == [
        "Helsinki",
        "Espoo",
        "Vantaa",
        "Tampere",
        "Turku",
        "Lahti",
    ]


def test_snapshot_anchor_counts_snapshot_and_source_age(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("DB_NAME", "bensavahti_test")
    server = importlib.import_module("server")
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    snapshot = {
        "ts": "2026-07-10T00:00:00+00:00",
        "national_min": 1.7,
        "national_min_age_hours": 13,
        "by_city": {"Turku": {"sources": [
            {"price": 1.71, "age_hours": 13},
            {"price": 1.72, "age_hours": 4},
        ]}},
    }

    assert server._snapshot_anchor(snapshot, "Suomi", now) is None
    assert server._snapshot_anchor(snapshot, "Turku", now) == 1.72
