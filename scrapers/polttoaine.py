"""
Scraper for polttoaine.net - the 20 cheapest 95E10 stations page.
This site is latin1-encoded and uses a simple HTML table — easy to parse.
"""
import re
import requests
from bs4 import BeautifulSoup

URL = "https://polttoaine.net/index.php?cmd=20halvinta&bensa95E10=1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GasPriceAlert/1.0; personal use)"
}
TIMEOUT = 30


def _parse_price(text: str) -> float | None:
    """Parse a price cell like '1.937' or '-' into a float, or None."""
    text = text.strip()
    if not text or text == "-":
        return None
    # strip non-numeric except dot/comma
    m = re.search(r"(\d+[.,]\d+)", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def fetch_prices() -> list[dict]:
    """
    Returns the 20 cheapest 95E10 stations as a list of dicts:
        {city, station, address, price, date, source}
    """
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "latin1"  # site declares latin1
    soup = BeautifulSoup(resp.text, "html.parser")

    results: list[dict] = []

    # Find the table that contains the "20 Halvinta" header
    target_table = None
    for table in soup.find_all("table"):
        header_text = table.get_text()
        if "20 Halvinta" in header_text or "Halvinta" in header_text:
            target_table = table
            break
    if target_table is None:
        return results

    for row in target_table.find_all("tr"):
        cells = row.find_all("td")
        # We need at least 5 cells: location, date, 95E10, 98E, Di
        if len(cells) < 5:
            continue

        loc_cell = cells[0].get_text(" ", strip=True)
        date_cell = cells[1].get_text(strip=True)
        price_95 = _parse_price(cells[2].get_text(strip=True))

        # Skip header row and empty rows
        if price_95 is None or not loc_cell:
            continue

        # loc_cell looks like: "Vantaa, Neste Oil Express, Kuninkaanmäki Kankikuja 2"
        parts = [p.strip() for p in loc_cell.split(",", 2)]
        city = parts[0] if parts else ""
        station = parts[1] if len(parts) > 1 else ""
        address = parts[2] if len(parts) > 2 else ""

        results.append({
            "city": city,
            "station": station,
            "address": address,
            "price": price_95,
            "date": date_cell,
            "source": "polttoaine.net",
        })

    return results


if __name__ == "__main__":
    # Quick local test
    for row in fetch_prices():
        print(f"{row['price']:.3f} €  {row['city']:<15} {row['station']:<25} {row['address']}")
