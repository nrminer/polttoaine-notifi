"""
Scraper for polttoaine.net - the "20 cheapest" page, per fuel kind.
The site is latin1-encoded with a simple HTML table.
"""
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://polttoaine.net/index.php?cmd=20halvinta"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0; personal use)"
}
TIMEOUT = 30

# Fuel kind -> (URL query param, table column index for price)
FUELS = {
    "95E10":  ("bensa95E10=1", 2),
    "diesel": ("diesel=1",     4),
}


def _parse_price(text: str):
    text = text.strip()
    if not text or text == "-":
        return None
    # FIXED: Require 2-3 decimals for consistency with tankille.py
    m = re.search(r"(\d+[.,]\d{2,3})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def fetch_prices(fuel: str = "95E10") -> list:
    if fuel not in FUELS:
        raise ValueError(f"unknown fuel {fuel!r}; choose from {list(FUELS)}")
    query, price_col = FUELS[fuel]
    url = f"{BASE_URL}&{query}"

    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "latin1"
    soup = BeautifulSoup(resp.text, "html.parser")

    target_table = None
    for table in soup.find_all("table"):
        if "Halvinta" in table.get_text():
            target_table = table
            break
    if target_table is None:
        return []

    results = []
    for row in target_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        loc_cell = cells[0].get_text(" ", strip=True)
        date_cell = cells[1].get_text(strip=True)
        price = _parse_price(cells[price_col].get_text(strip=True))
        if price is None or not loc_cell:
            continue

        parts = [p.strip() for p in loc_cell.split(",", 2)]
        city = parts[0] if parts else ""
        station = parts[1] if len(parts) > 1 else ""
        address = parts[2] if len(parts) > 2 else ""

        results.append({
            "city": city,
            "station": station,
            "address": address,
            "price": price,
            "date": date_cell,
            "fuel": fuel,
            "source": "polttoaine.net",
        })
    return results
