"""
Scraper for tankille.fi per-city public pages, e.g. www.tankille.fi/helsinki/
"""
from __future__ import annotations
import re
import sys
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.tankille.fi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0; personal use)"
}
TIMEOUT = 30

# Cities we know how to scrape. URL slug = lowercase city name (ascii).
CITIES = [
    "Helsinki", "Vantaa", "Espoo",
    "Tampere", "Turku", "Oulu",
    "Jyvaskyla", "Kuopio", "Lahti",
]

# Display name overrides for slug -> proper city name
CITY_DISPLAY = {
    "Jyvaskyla": "Jyväskylä",
}

FUEL_TAB = {
    "95E10":  "fuel-95",
    "diesel": "fuel-dsl",
}


def _parse_price(text: str):
    text = text.strip()
    m = re.search(r"(\d+[.,]\d{2,3})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _extract_chain(station_name: str) -> str:
    """Extract chain name from station name."""
    name_upper = station_name.upper()
    chains = ["NESTE", "ABC", "ST1", "SHELL", "TEBOIL", "SEO", "ESSO", "CIRCLE K"]
    for chain in chains:
        if chain in name_upper:
            return chain.capitalize() if chain not in ["ABC", "SEO"] else chain
    return ""


def _freshness_hours(date_text: str) -> float:
    """Arvioi tankille.fi:n päivitystekstistä iän tunteina.

    Esimerkkejä:
      "juuri nyt"     -> 0.0
      "5 minuuttia sitten" -> 0.08
      "tunti sitten"  -> 1.0
      "3 tuntia sitten" -> 3.0
      "eilen"         -> 24.0
      "2 päivää sitten" -> 48.0
      tuntematon      -> 999.0
    """
    t = (date_text or "").lower().strip()
    if not t:
        return 999.0
    if "juuri nyt" in t or "äsken" in t:
        return 0.0
    m = re.search(r"(\d+)\s*minuut", t)
    if m:
        return int(m.group(1)) / 60.0
    # FIXED: Check plural hours BEFORE singular to avoid "2 tuntia" returning 1.0
    m = re.search(r"(\d+)\s*tunti", t)
    if m:
        return float(m.group(1))
    if re.search(r"\btunti(?:\b|\s|sitten)", t):
        return 1.0
    if "eilen" in t:
        return 24.0
    m = re.search(r"(\d+)\s*p[äa]iv", t)
    if m:
        return int(m.group(1)) * 24.0
    m = re.search(r"(\d+)\s*viikko", t)
    if m:
        return int(m.group(1)) * 24.0 * 7
    return 999.0


def _scrape_city(city: str, fuel: str) -> list:
    """Scrape fuel prices for a specific city.
    
    SECURITY: Validates city against whitelist to prevent SSRF attacks.
    """
    # SECURITY: Validate city against whitelist
    if city not in CITIES:
        raise ValueError(f"Invalid city: {city}")
    
    slug = city.lower()
    # SECURITY: Ensure slug is alphanumeric only
    if not slug.replace('-', '').isalpha():
        raise ValueError(f"Invalid city format: {city}")
    
    url = f"{BASE_URL}/{slug}/"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    pane = soup.find("div", id=FUEL_TAB[fuel])
    if pane is None:
        return []
    table = pane.find("table")
    if table is None:
        return []

    display_city = CITY_DISPLAY.get(city, city)
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 4:
            continue
        station = cells[1]
        price = _parse_price(cells[2])
        if price is None or not station:
            continue
        rows.append({
            "city": display_city,
            "station": station,
            "address": "",
            "price": price,
            "date": cells[3],
            "age_hours": _freshness_hours(cells[3]),
            "fuel": fuel,
            "source": "tankille.fi",
            "chain": _extract_chain(station),
            "raw_name": station,
        })
    return rows


def fetch_prices(fuel: str = "95E10", cities=None) -> list:
    if fuel not in FUEL_TAB:
        return []
    target_cities = cities or CITIES
    out = []
    for city in target_cities:
        try:
            out.extend(_scrape_city(city, fuel))
        except Exception as e:
            print(f"[warn] tankille {city}/{fuel}: {e}", file=sys.stderr)
    return out
