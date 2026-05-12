"""
Scraper for tankille.fi per-city public pages, e.g. www.tankille.fi/helsinki/

The page has three tab panes:
    #fuel-95   -> 95E10
    #fuel-98   -> 98E (not used here)
    #fuel-dsl  -> diesel

Each pane contains a table with rows: [#, Asema, Hinta, Päivitetty].
The "Asema" cell looks like "Neste Helsinki Konala" — the city name is
embedded in the station name (no separate column).
"""
from __future__ import annotations
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.tankille.fi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PolttoaineNotifi/1.0; personal use)"
}
TIMEOUT = 30

# Cities we know how to scrape. URL slug = lowercase city name (no umlauts needed).
CITIES = ["Helsinki", "Vantaa", "Espoo"]

# Our fuel name -> Tankille's tab id
FUEL_TAB = {
    "95E10":  "fuel-95",
    "diesel": "fuel-dsl",
}


def _parse_price(text: str) -> float | None:
    text = text.strip()
    m = re.search(r"(\d+[.,]\d{2,3})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _scrape_city(city: str, fuel: str) -> list[dict]:
    slug = city.lower()
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

    rows: list[dict] = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 4:
            continue
        station = cells[1]
        price = _parse_price(cells[2])
        if price is None or not station:
            continue
        rows.append({
            "city": city,
            "station": station,
            "address": "",         # Tankille public page doesn't expose street address
            "price": price,
            "date": cells[3],      # e.g. "juuri nyt", "tunti sitten"
            "fuel": fuel,
            "source": "tankille.fi",
        })
    return rows


def fetch_prices(fuel: str = "95E10") -> list[dict]:
    if fuel not in FUEL_TAB:
        return []
    out: list[dict] = []
    for city in CITIES:
        try:
            out.extend(_scrape_city(city, fuel))
        except Exception as e:
            # Don't let one city break the others
            import sys
            print(f"[warn] tankille {city}/{fuel}: {e}", file=sys.stderr)
    return out


if __name__ == "__main__":
    for kind in ("95E10", "diesel"):
        print(f"=== {kind} ===")
        for r in fetch_prices(kind):
            print(f"{r['price']:.3f} EUR  {r['city']:<10} {r['station']}  ({r['date']})")
