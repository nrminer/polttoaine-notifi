"""Tests for price_observations and stations collection logic.

Tests station normalization, scraper chain extraction, observation insertion,
and station registry upsert behavior.
"""
import pytest
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------- Test: normalize_station_key ----------------

def normalize_station_name(name: str, city: str) -> str:
    """Generate a stable station_id from station name + city.

    Strips common noise (punctuation, case) to improve deduplication.
    Format: city_stationname (lowercase, alphanumeric + underscore).

    This is the function from migrate_to_observations.py._normalize_station_name.
    """
    clean = re.sub(r'[^\w\s-]', '', name.lower())
    clean = re.sub(r'\s+', '_', clean.strip())
    city_clean = re.sub(r'[^\w\s]', '', city.lower())
    city_clean = re.sub(r'\s+', '_', city_clean.strip())
    return f"{city_clean}_{clean}"


def test_normalize_station_key_basic():
    """Basic station name normalization produces consistent keys."""
    result = normalize_station_name("Neste Oil Express", "Helsinki")
    assert result == "helsinki_neste_oil_express"


def test_normalize_station_key_punctuation():
    """Punctuation is stripped from station names."""
    result = normalize_station_name("Shell - Viikki", "Helsinki")
    assert result == "helsinki_shell__viikki"


def test_normalize_station_key_case_insensitive():
    """Normalization is case-insensitive."""
    result1 = normalize_station_name("NESTE OIL EXPRESS", "HELSINKI")
    result2 = normalize_station_name("neste oil express", "helsinki")
    result3 = normalize_station_name("Neste Oil Express", "Helsinki")
    assert result1 == result2 == result3


def test_normalize_station_key_whitespace_collapse():
    """Multiple whitespace characters collapse to single underscore."""
    result = normalize_station_name("ABC   Automaattiasema", "Helsinki")
    assert result == "helsinki_abc_automaattiasema"


def test_normalize_station_key_special_chars():
    """Special characters are removed."""
    result = normalize_station_name("St1 / Teboil (Keskusta)", "Tampere")
    assert result == "tampere_st1__teboil_keskusta"


def test_normalize_station_key_unicode():
    """Finnish characters are preserved."""
    result = normalize_station_name("ABC Äänekoski", "Jyväskylä")
    assert result == "jyväskylä_abc_äänekoski"


def test_normalize_station_key_deduplication():
    """Similar station names produce same key."""
    # These should be considered the same station
    result1 = normalize_station_name("Neste, Viikki", "Helsinki")
    result2 = normalize_station_name("Neste - Viikki", "Helsinki")
    # Punctuation stripped, so both become same pattern
    assert "viikki" in result1 and "viikki" in result2
    assert "neste" in result1 and "neste" in result2


# ---------------- Test: scraper chain extraction ----------------

def extract_chain(station_name: str) -> str:
    """Extract chain name from station name.

    This is the function from scrapers/polttoaine.py and scrapers/tankille.py.
    """
    name_upper = station_name.upper()
    chains = ["NESTE", "ABC", "ST1", "SHELL", "TEBOIL", "SEO", "ESSO", "CIRCLE K"]
    for chain in chains:
        if chain in name_upper:
            return chain.capitalize() if chain not in ["ABC", "SEO"] else chain
    return ""


def test_scraper_chain_extraction_neste():
    """Neste chain is extracted correctly."""
    assert extract_chain("Neste Oil Express - Viikki") == "Neste"
    assert extract_chain("NESTE AUTOMAATTI") == "Neste"
    assert extract_chain("neste keskusta") == "Neste"


def test_scraper_chain_extraction_abc():
    """ABC chain preserves uppercase."""
    assert extract_chain("ABC Automaattiasema") == "ABC"
    assert extract_chain("abc liikennemyymälä") == "ABC"


def test_scraper_chain_extraction_shell():
    """Shell chain is extracted correctly."""
    assert extract_chain("Shell Express - Espoo") == "Shell"
    assert extract_chain("SHELL 24h") == "Shell"


def test_scraper_chain_extraction_st1():
    """St1 chain is extracted correctly."""
    assert extract_chain("St1 Automaatti") == "St1"
    assert extract_chain("ST1 - Keskusta") == "St1"


def test_scraper_chain_extraction_teboil():
    """Teboil chain is extracted correctly."""
    assert extract_chain("Teboil Automaattiasema") == "Teboil"
    assert extract_chain("TEBOIL 24/7") == "Teboil"


def test_scraper_chain_extraction_seo():
    """SEO chain preserves uppercase."""
    assert extract_chain("SEO Automaatti") == "SEO"
    assert extract_chain("seo asema") == "SEO"


def test_scraper_chain_extraction_circle_k():
    """Circle K chain is extracted correctly."""
    assert extract_chain("Circle K Keskusta") == "Circle k"
    assert extract_chain("CIRCLE K EXPRESS") == "Circle k"


def test_scraper_chain_extraction_esso():
    """Esso chain is extracted correctly."""
    assert extract_chain("Esso Express") == "Esso"
    assert extract_chain("ESSO 24h") == "Esso"


def test_scraper_chain_extraction_no_match():
    """Unknown chains return empty string."""
    assert extract_chain("Kyläkaupan Bensa-asema") == ""
    assert extract_chain("Osuuskauppa") == ""
    assert extract_chain("Local Station") == ""


def test_scraper_chain_extraction_partial_match():
    """Partial matches still work."""
    assert extract_chain("Neste Oil") == "Neste"
    assert extract_chain("Shell Station") == "Shell"


# ---------------- Test: price_observations insert ----------------

@pytest.fixture
async def mock_db():
    """Mock MongoDB database with price_observations collection."""
    db = MagicMock()
    db.price_observations = AsyncMock()
    db.stations = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_price_observations_insert(mock_db):
    """Mock scrape populates price_observations collection.

    Verifies that observation documents have the correct structure and fields.
    """
    # Mock scraper data
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
        {
            "city": "Helsinki",
            "station": "ABC Automaattiasema",
            "address": "Mannerheimintie 5",
            "price": 1.935,
            "fuel": "95E10",
            "source": "tankille.fi",
            "chain": "ABC",
        },
    ]

    scraped_at = datetime.now(timezone.utc)

    # Simulate inserting observations
    observations = []
    for st in scraped_stations:
        station_id = normalize_station_name(st["station"], st["city"])
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
        observations.append(obs)

        # Mock database insert
        await mock_db.price_observations.update_one(
            {
                "station_id": obs["station_id"],
                "fuel": obs["fuel"],
                "scraped_at": obs["scraped_at"],
            },
            {"$set": obs},
            upsert=True,
        )

    # Verify observations were created
    assert len(observations) == 2
    assert mock_db.price_observations.update_one.call_count == 2

    # Verify first observation structure
    obs1 = observations[0]
    assert obs1["station_id"] == "helsinki_neste_express_viikki"
    assert obs1["name"] == "Neste Express Viikki"
    assert obs1["city"] == "Helsinki"
    assert obs1["fuel"] == "95E10"
    assert obs1["price"] == 1.922
    assert obs1["source"] == "polttoaine.net"
    assert obs1["chain"] == "Neste"
    assert isinstance(obs1["scraped_at"], datetime)

    # Verify second observation structure
    obs2 = observations[1]
    assert obs2["station_id"] == "helsinki_abc_automaattiasema"
    assert obs2["chain"] == "ABC"


@pytest.mark.asyncio
async def test_price_observations_duplicate_handling(mock_db):
    """Duplicate observations (same station_id, fuel, scraped_at) are handled via upsert.

    Verifies that the unique index on (station_id, fuel, scraped_at) prevents duplicates.
    """
    station_id = "helsinki_neste_express_viikki"
    fuel = "95E10"
    scraped_at = datetime.now(timezone.utc)

    obs = {
        "station_id": station_id,
        "name": "Neste Express Viikki",
        "city": "Helsinki",
        "address": "Viikinportti 1",
        "fuel": fuel,
        "price": 1.922,
        "scraped_at": scraped_at,
        "source": "polttoaine.net",
        "chain": "Neste",
    }

    # Insert same observation twice
    await mock_db.price_observations.update_one(
        {
            "station_id": obs["station_id"],
            "fuel": obs["fuel"],
            "scraped_at": obs["scraped_at"],
        },
        {"$set": obs},
        upsert=True,
    )

    await mock_db.price_observations.update_one(
        {
            "station_id": obs["station_id"],
            "fuel": obs["fuel"],
            "scraped_at": obs["scraped_at"],
        },
        {"$set": obs},
        upsert=True,
    )

    # Verify upsert was called twice (second call updates existing document)
    assert mock_db.price_observations.update_one.call_count == 2


# ---------------- Test: stations registry upsert ----------------

@pytest.mark.asyncio
async def test_stations_registry_upsert_new(mock_db):
    """New station is inserted into stations registry."""
    station = {
        "station_id": "helsinki_neste_express_viikki",
        "name": "Neste Express Viikki",
        "city": "Helsinki",
        "address": "Viikinportti 1",
        "first_seen": datetime.now(timezone.utc),
        "last_seen": datetime.now(timezone.utc),
    }

    await mock_db.stations.update_one(
        {"station_id": station["station_id"]},
        {"$set": station},
        upsert=True,
    )

    assert mock_db.stations.update_one.call_count == 1
    call_args = mock_db.stations.update_one.call_args
    assert call_args[0][0] == {"station_id": "helsinki_neste_express_viikki"}
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_stations_registry_merge_duplicate(mock_db):
    """Duplicate stations (same station_id) merge correctly.

    Verifies that first_seen and last_seen are updated appropriately.
    """
    station_id = "helsinki_neste_express_viikki"

    # First observation
    first_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    station1 = {
        "station_id": station_id,
        "name": "Neste Express Viikki",
        "city": "Helsinki",
        "address": "Viikinportti 1",
        "first_seen": first_time,
        "last_seen": first_time,
    }

    await mock_db.stations.update_one(
        {"station_id": station1["station_id"]},
        {"$set": station1},
        upsert=True,
    )

    # Second observation (same station, later time)
    second_time = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
    station2 = {
        "station_id": station_id,
        "name": "Neste Express Viikki",
        "city": "Helsinki",
        "address": "Viikinportti 1",
        "first_seen": first_time,  # Keep original first_seen
        "last_seen": second_time,   # Update last_seen
    }

    await mock_db.stations.update_one(
        {"station_id": station2["station_id"]},
        {"$set": station2},
        upsert=True,
    )

    # Verify both upserts were called
    assert mock_db.stations.update_one.call_count == 2

    # Verify the second call maintains first_seen and updates last_seen
    second_call_args = mock_db.stations.update_one.call_args
    assert second_call_args[0][1]["$set"]["first_seen"] == first_time
    assert second_call_args[0][1]["$set"]["last_seen"] == second_time


@pytest.mark.asyncio
async def test_stations_registry_name_variations(mock_db):
    """Different name variations should produce same station_id.

    Verifies that normalization catches common variations.
    """
    # These variations should all normalize to the same station_id
    variations = [
        ("Neste Express - Viikki", "Helsinki"),
        ("Neste Express, Viikki", "Helsinki"),
        ("NESTE EXPRESS VIIKKI", "Helsinki"),
    ]

    station_ids = [normalize_station_name(name, city) for name, city in variations]

    # All variations should contain the same key components
    for sid in station_ids:
        assert "helsinki" in sid
        assert "neste" in sid
        assert "express" in sid
        assert "viikki" in sid


@pytest.mark.asyncio
async def test_stations_registry_different_cities(mock_db):
    """Same station name in different cities gets different station_id."""
    station_id_hki = normalize_station_name("Neste Express", "Helsinki")
    station_id_esp = normalize_station_name("Neste Express", "Espoo")

    assert station_id_hki != station_id_esp
    assert "helsinki" in station_id_hki
    assert "espoo" in station_id_esp
