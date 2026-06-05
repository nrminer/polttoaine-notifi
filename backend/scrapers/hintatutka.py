"""
Experimental scraper for hintatutka.fi - Finnish fuel price comparison site.

Site-specific notes:
- hintatutka.fi aggregates station prices with city/region filtering
- Prices are displayed in a sortable table or card layout
- Timestamps are typically shown as relative time ("X tuntia sitten")
- Station names often include chain prefix (e.g., "ABC Express", "Neste Oil")
- The site may use JavaScript rendering; check if requests.get yields prices or if selenium/API endpoint is needed

This scraper is not part of the production scrape path unless
ENABLE_HINTATUTKA_EXPERIMENTAL=1 is set. It still needs verification against
live hintatutka.fi HTML before it can be promoted to a production data source.
Key unknowns (to be filled after manual site inspection):
- Exact URL patterns for fuel types and cities
- HTML structure (table rows vs div cards)
- CSS selectors for price, station, address, timestamp
- Whether server-side rendered or requires JS execution
- Fuel type identifiers/URL params
"""
from __future__ import annotations
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Optional

BASE_URL = "https://hintatutka.fi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0; personal use)"
}
TIMEOUT = 30

# Fuel mappings for the table headers seen in local fixtures.
FUEL_MAP = {
    "95E10": "95 E10",
    "diesel": "Diesel",
}

# Cities supported (initially match tankille.py coverage)
CITIES = [
    "Helsinki", "Vantaa", "Espoo",
    "Tampere", "Turku", "Oulu",
    "Jyväskylä", "Kuopio", "Lahti",
]


def _parse_price(text: str) -> Optional[float]:
    """Extract price from text like '1.857 €/l' or '1,857'."""
    text = (text or "").strip()
    # Match 1-2 digits, decimal separator, 2-3 decimals
    m = re.search(r"(\d{1,2}[.,]\d{2,3})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _freshness_hours(date_text: str) -> float:
    """
    Parse timestamp from hintatutka.fi format.

    Examples:
      "19 h sitten"                -> 19.0
      "2 päivää sitten"            -> 48.0
      "Päivitetty: 19.05.2026 klo 23.59" -> calculated
      "19.05.2026"                 -> calculated from date
      unknown/empty                -> 999.0
    """
    t = (date_text or "").strip()
    if not t:
        return 999.0

    t_lower = t.lower()

    if t_lower in {"juuri nyt", "äsken", "asken"}:
        return 0.0
    if "eilen" in t_lower:
        return 24.0

    # "19 h sitten" format
    m = re.search(r"(\d+)\s*h\s", t_lower)
    if m:
        return float(m.group(1))

    # Minutes
    m = re.search(r"(\d+)\s*minuut", t_lower)
    if m:
        return int(m.group(1)) / 60.0

    # Hours
    m = re.search(r"(\d+)\s*tunti", t_lower)
    if m:
        return float(m.group(1))
    if "tunti" in t_lower:
        return 1.0

    # Days
    m = re.search(r"(\d+)\s*p[äa]iv", t_lower)
    if m:
        return int(m.group(1)) * 24.0
    m = re.search(r"(\d+)\s*viikko", t_lower)
    if m:
        return int(m.group(1)) * 7.0 * 24.0
    if "viikko" in t_lower:
        return 7.0 * 24.0

    # Full timestamp: "Päivitetty: 19.05.2026 klo 23.59" or just "19.05.2026"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", t)
    if m:
        day, month, year = map(int, m.groups())
        try:
            # Extract time if present
            time_match = re.search(r"klo\s+(\d{1,2})[:.](\d{2})", t)
            if time_match:
                hour, minute = map(int, time_match.groups())
                update_time = datetime(year, month, day, hour, minute)
            else:
                update_time = datetime(year, month, day, 12, 0)  # Assume noon

            now = datetime.now()
            delta = now - update_time
            return max(0, delta.total_seconds() / 3600.0)
        except ValueError:
            return 999.0

    return 999.0


def _extract_chain(station_name: str) -> str:
    """Extract chain name from station name."""
    name_upper = station_name.upper()
    chains = ["NESTE", "ABC", "ST1", "SHELL", "TEBOIL", "SEO", "ESSO", "CIRCLE K"]
    for chain in chains:
        if chain in name_upper:
            return chain.capitalize() if chain not in ["ABC", "SEO"] else chain
    return ""


def _scrape_city(city: str, fuel: str) -> List[Dict]:
    """Scrape hintatutka.fi national page and filter for target city."""

    fuel_display = FUEL_MAP.get(fuel)
    if not fuel_display:
        return []

    url = f"{BASE_URL}/suomi"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] hintatutka {city}/{fuel}: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the main table
    table = soup.find("table")
    if not table:
        return []

    # Get column headers to find fuel column index
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    try:
        fuel_col_idx = headers.index(fuel_display)
        timestamp_col_idx = headers.index("Päivitetty")
    except ValueError:
        print(f"[warn] hintatutka: fuel column '{fuel_display}' not found", file=sys.stderr)
        return []

    results = []
    for tr in table.find_all("tr")[1:]:  # Skip header
        cells = tr.find_all("td")
        if len(cells) <= max(fuel_col_idx, timestamp_col_idx):
            continue

        # Column 0: Station name
        station_cell = cells[0].get_text(" ", strip=True)

        # Filter by city (case-insensitive match)
        if city.lower() not in station_cell.lower():
            continue

        # Fuel price column
        price_text = cells[fuel_col_idx].get_text(strip=True)
        price = _parse_price(price_text)
        if price is None:
            continue

        # Timestamp column
        timestamp_text = cells[timestamp_col_idx].get_text(strip=True)

        results.append({
            "city": city,
            "station": station_cell,
            "address": "",
            "price": price,
            "date": timestamp_text,
            "age_hours": _freshness_hours(timestamp_text),
            "fuel": fuel,
            "source": "hintatutka.fi",
            "chain": _extract_chain(station_cell),
            "raw_name": station_cell,
        })

    return results


def fetch_prices(fuel: str = "95E10", cities: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetch fuel prices from hintatutka.fi for specified cities.

    Args:
        fuel: Fuel type ("95E10" or "diesel")
        cities: List of city names to scrape. Defaults to CITIES constant.

    Returns:
        List of price records matching scraper contract:
        {
            "city": str,
            "station": str,
            "address": str,
            "price": float,
            "date": str,
            "age_hours": float,
            "fuel": str,
            "source": "hintatutka.fi",
            "chain": str,          # Additional field
            "raw_name": str,       # Additional field
        }

    Returns empty list on errors (never raises).
    """
    if fuel not in FUEL_MAP:
        print(f"[warn] hintatutka: unsupported fuel {fuel!r}", file=sys.stderr)
        return []

    target_cities = cities or CITIES
    results = []

    for city in target_cities:
        try:
            city_results = _scrape_city(city, fuel)
            results.extend(city_results)
        except Exception as e:
            print(f"[warn] hintatutka {city}/{fuel}: {e}", file=sys.stderr)
            continue

    return results


# Standalone test harness
if __name__ == "__main__":
    import json
    fuel = sys.argv[1] if len(sys.argv) > 1 else "95E10"
    cities = sys.argv[2:] if len(sys.argv) > 2 else ["Helsinki", "Espoo"]

    print(f"# Scraping hintatutka.fi for {fuel} in {cities}", file=sys.stderr)
    data = fetch_prices(fuel, cities)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"# Found {len(data)} stations", file=sys.stderr)
