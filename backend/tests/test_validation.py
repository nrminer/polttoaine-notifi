from pathlib import Path
import importlib
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from validation import validate_scraped_data


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
