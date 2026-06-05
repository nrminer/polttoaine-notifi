"""Tests for runtime aggregate observation behavior."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import tracker


def sample_rows():
    return [
        {
            "city": "Helsinki",
            "station": "Neste Express Viikki",
            "price": 1.922,
            "source": "tankille.fi",
        },
        {
            "city": "Helsinki",
            "station": "ABC Automaattiasema",
            "price": 1.935,
            "source": "polttoaine.net",
        },
        {
            "city": "Espoo",
            "station": "Neste Express Espoo",
            "price": 1.899,
            "source": "tankille.fi",
        },
        {
            "city": "Oulu",
            "station": "Outside tracked city",
            "price": 1.777,
            "source": "tankille.fi",
        },
    ]


def test_sane_filters_out_parse_outliers():
    rows = [
        {"price": 1.922},
        {"price": 0.42},
        {"price": 4.20},
        {"price": "1.922"},
        {},
    ]

    assert tracker._sane(rows) == [{"price": 1.922}]


def test_city_breakdown_is_aggregate_not_station_level():
    breakdown = tracker._city_breakdown(sample_rows())

    assert breakdown["Helsinki"] == {
        "cheapest": 1.922,
        "average": 1.929,
        "count": 2,
        "station": "Neste Express Viikki",
        "source": "tankille.fi",
    }
    assert breakdown["Espoo"]["cheapest"] == 1.899
    assert breakdown["Vantaa"] == {
        "cheapest": None,
        "average": None,
        "count": 0,
        "station": None,
        "source": None,
    }
    assert "Oulu" not in breakdown


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.price_observations = AsyncMock()
    db.daily_tracker = AsyncMock()
    db.stations = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_price_observation_upsert_key_is_date_hour_fuel(monkeypatch, mock_db):
    monkeypatch.setattr(
        tracker,
        "_scrape_cheapest",
        AsyncMock(
            return_value={
                "price": 1.899,
                "station": "Neste Express Espoo",
                "city": "Espoo",
                "source": "tankille.fi",
                "count": 3,
                "by_city": tracker._city_breakdown(sample_rows()),
            }
        ),
    )

    doc = await tracker.silent_scrape(mock_db, executor=object(), fuel="diesel", hour=18)

    filter_doc, update_doc = mock_db.price_observations.update_one.call_args.args[:2]
    assert filter_doc == {"date": doc["date"], "hour": 18, "fuel": "diesel"}
    assert update_doc["$set"]["cheapest"] == 1.899
    assert update_doc["$set"]["by_city"]["Helsinki"]["count"] == 2
    assert update_doc["$set"]["stations_scanned"] == 3


@pytest.mark.asyncio
async def test_price_observation_does_not_create_station_registry(monkeypatch, mock_db):
    monkeypatch.setattr(
        tracker,
        "_scrape_cheapest",
        AsyncMock(
            return_value={
                "price": 1.899,
                "station": "Neste Express Espoo",
                "city": "Espoo",
                "source": "tankille.fi",
                "count": 3,
                "by_city": tracker._city_breakdown(sample_rows()),
            }
        ),
    )

    await tracker.silent_scrape(mock_db, executor=object(), fuel="diesel", hour=18)

    mock_db.stations.update_one.assert_not_called()
    mock_db.daily_tracker.update_one.assert_not_called()
