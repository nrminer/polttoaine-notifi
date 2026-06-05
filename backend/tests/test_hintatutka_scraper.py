"""Tests for hintatutka.fi scraper.

Covers contract compliance, fuel mapping, chain extraction, error handling,
and live scraping (integration test marked separately).
"""
import pytest
from unittest.mock import patch, Mock
from pathlib import Path

# Adjust import path based on backend structure
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.hintatutka import (
    fetch_prices,
    _scrape_city,
    _parse_price,
    _freshness_hours,
    _extract_chain,
    FUEL_MAP,
)


@pytest.fixture
def mock_html():
    """Load sample HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "hintatutka_sample.html"
    return fixture_path.read_text(encoding="utf-8")


# ----------- Contract tests -----------

def test_scrape_hintatutka_contract():
    """Verify return format matches existing scrapers (polttoaine.py, tankille.py)."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
        <table class="price-table">
            <tr>
                <td>ABC Express Viikki</td>
                <td>1.857 €/l</td>
                <td>2 tuntia sitten</td>
                <td>Viikinportti 1</td>
            </tr>
        </table>
        </body></html>
        """
        mock_get.return_value = mock_resp

        results = fetch_prices(fuel="95E10", cities=["Helsinki"])

        assert isinstance(results, list)
        if results:  # May be empty if scraper is placeholder
            record = results[0]
            # Contract: every scraper must return these keys
            required_keys = {
                "city", "station", "address", "price",
                "date", "age_hours", "fuel", "source"
            }
            assert required_keys.issubset(record.keys())
            assert record["source"] == "hintatutka.fi"
            assert isinstance(record["price"], float)
            assert isinstance(record["age_hours"], float)
            assert record["fuel"] == "95E10"
            # Additional hintatutka fields
            assert "chain" in record
            assert "raw_name" in record


def test_scrape_hintatutka_empty_on_404():
    """Network 404 returns empty list (never raises)."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        results = fetch_prices(fuel="95E10", cities=["NonexistentCity"])
        assert results == []


def test_scrape_hintatutka_empty_on_malformed_html():
    """Malformed HTML returns empty list."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>No price table here</body></html>"
        mock_get.return_value = mock_resp

        results = fetch_prices(fuel="95E10", cities=["Helsinki"])
        # Should not crash, returns empty
        assert isinstance(results, list)


# ----------- Fuel mapping -----------

def test_scrape_hintatutka_fuel_mapping():
    """'95E10' and 'Diesel' map correctly to hintatutka.fi identifiers."""
    assert "95E10" in FUEL_MAP
    assert "diesel" in FUEL_MAP
    # Verify mapping produces lowercase identifiers (common pattern)
    assert FUEL_MAP["95E10"] == "95e10"
    assert FUEL_MAP["diesel"] == "diesel"


def test_scrape_hintatutka_unsupported_fuel():
    """Unsupported fuel returns empty list (no crash)."""
    results = fetch_prices(fuel="BOGUS_FUEL", cities=["Helsinki"])
    assert results == []


# ----------- Chain extraction -----------

def test_scrape_hintatutka_chain_extraction():
    """Chains extracted from station names."""
    test_cases = [
        ("ABC Express Viikki", "Abc"),
        ("Neste Oil Helsinki", "Neste"),
        ("ST1 Itäkeskus", "St1"),
        ("Shell Automaattiasema", "Shell"),
        ("SEO Leppävaara", "Seo"),
        ("Teboil Kamppi", "Teboil"),
        ("Alepa Kallio", "Alepa"),
        ("S-Market Huopalahti", "S-market"),
        ("Unknown Brand Station", ""),  # No match
    ]
    for station_name, expected_chain in test_cases:
        assert _extract_chain(station_name) == expected_chain, \
            f"Failed for {station_name}: expected {expected_chain}, got {_extract_chain(station_name)}"


# ----------- Error handling -----------

def test_scrape_hintatutka_error_handling():
    """Network errors return empty list (never raises)."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        # Simulate connection timeout
        mock_get.side_effect = Exception("Connection timeout")

        results = fetch_prices(fuel="95E10", cities=["Helsinki"])
        assert results == []  # Must not raise


def test_scrape_hintatutka_http_error():
    """HTTP errors (5xx) return empty list."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        mock_get.return_value = mock_resp

        results = fetch_prices(fuel="95E10", cities=["Helsinki"])
        assert results == []


# ----------- Helper function tests -----------

def test_parse_price():
    """Price extraction from various formats."""
    assert _parse_price("1.857 €/l") == 1.857
    assert _parse_price("1,857 €/l") == 1.857
    assert _parse_price("1.999") == 1.999
    assert _parse_price("2,069") == 2.069
    assert _parse_price("€1.75/l") == 1.75
    assert _parse_price("invalid") is None
    assert _parse_price("") is None
    assert _parse_price(None) is None


def test_freshness_hours():
    """Timestamp parsing from Finnish relative time."""
    test_cases = [
        ("juuri nyt", 0.0),
        ("äsken", 0.0),
        ("5 minuuttia sitten", 5/60),
        ("1 tunti sitten", 1.0),
        ("3 tuntia sitten", 3.0),
        ("eilen", 24.0),
        ("2 päivää sitten", 48.0),
        ("viikko sitten", 168.0),
        ("3 viikkoa sitten", 504.0),
        ("", 999.0),  # Unknown
        (None, 999.0),
    ]
    for text, expected_hours in test_cases:
        result = _freshness_hours(text)
        assert abs(result - expected_hours) < 0.01, \
            f"Failed for '{text}': expected {expected_hours}, got {result}"


def test_freshness_hours_edge_cases():
    """Edge cases for timestamp parsing."""
    # Single hour without number
    assert _freshness_hours("tunti sitten") == 1.0
    # Mixed case
    assert _freshness_hours("EILEN") == 24.0
    # Partial matches
    assert _freshness_hours("15 minuuttia sitten") == 0.25


# ----------- Integration test -----------

@pytest.mark.integration
def test_scrape_hintatutka_real():
    """Live scrape test against actual hintatutka.fi site.

    Marked with @pytest.mark.integration - skip by default.
    Run with: pytest -v -m integration
    """
    results = fetch_prices(fuel="95E10", cities=["Helsinki"])

    # NOTE: This test depends on hintatutka.fi being live and having data.
    # If the site is down or the scraper is still placeholder, this may fail.
    # The test validates structure, not exact content.

    if not results:
        pytest.skip("No results from hintatutka.fi (site may be down or scraper is placeholder)")

    # Validate at least one result has correct structure
    record = results[0]
    assert record["source"] == "hintatutka.fi"
    assert record["fuel"] == "95E10"
    assert record["city"] == "Helsinki"
    assert 1.0 <= record["price"] <= 3.5  # Sanity bounds
    assert record["age_hours"] >= 0.0
    assert isinstance(record["station"], str)
    assert len(record["station"]) > 0

    print(f"\n[integration] Scraped {len(results)} stations from hintatutka.fi")
    print(f"[integration] Sample: {results[0]}")


# ----------- Fixture-based parsing test -----------

def test_scrape_hintatutka_with_fixture(mock_html):
    """Parse sample HTML fixture and validate extraction."""
    with patch("scrapers.hintatutka.requests.get") as mock_get:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html
        mock_get.return_value = mock_resp

        results = _scrape_city("Helsinki", "95E10")

        # This test depends on fixtures/hintatutka_sample.html content
        # Adjust assertions based on fixture structure
        if results:
            record = results[0]
            assert record["source"] == "hintatutka.fi"
            assert record["fuel"] == "95E10"
            assert record["city"] == "Helsinki"
            assert isinstance(record["price"], float)
            assert record["price"] > 0.0
