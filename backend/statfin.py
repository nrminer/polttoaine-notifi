"""
Statistics Finland (Tilastokeskus) PxWeb API client.

Fetches REAL monthly Finnish fuel consumer prices (incl. VAT) since 1988.
Table: statfin_ehi_pxt_12ge.px (Polttonesteiden kuluttajahinnat).

Prices are returned in EUR/L (converted from snt/L).
"""
from __future__ import annotations
import requests
from datetime import date

STATFIN_URL = (
    "https://statfin.stat.fi/PxWeb/api/v1/fi/StatFin/ehi/statfin_ehi_pxt_12ge.px"
)
HEADERS = {"User-Agent": "BensaVahti/2.0 (real-history-loader)",
           "Content-Type": "application/json"}
TIMEOUT = 25

# Polttoaine-koodit Tilastokeskuksessa
FUEL_CODE = {
    "95E10": "A",   # Moottoribensiini 95 E 10, snt/l
    "diesel": "B",  # Dieselöljy, snt/l
}


def fetch_monthly(fuel: str = "95E10", since_year: int = 2020) -> list[dict]:
    """Hae kuukausihinnat Tilastokeskuksesta.

    Palauttaa listan: [{"month":"2025-08", "price": 1.69}, ...]  (€/L)
    Vain since_year ja sitä uudemmat.
    """
    if fuel not in FUEL_CODE:
        raise ValueError(f"unknown fuel {fuel}")

    payload = {
        "query": [
            {"code": "Polttoneste", "selection": {"filter": "item",
                                                  "values": [FUEL_CODE[fuel]]}},
            {"code": "Tiedot", "selection": {"filter": "item",
                                             "values": ["hinta"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    resp = requests.post(STATFIN_URL, json=payload, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    months_idx = data["dimension"]["Kuukausi"]["category"]["index"]
    values = data["value"]

    # Tiedot ja Polttoneste ovat valittu yhden arvon mukaisesti -> indeksi on suoraan kuukausi
    out = []
    for month_code, i in sorted(months_idx.items(), key=lambda x: x[1]):
        # month_code esim. "2025M08"
        year = int(month_code[:4])
        if year < since_year:
            continue
        month = int(month_code[5:7])
        v = values[i]
        if v is None:
            continue
        # snt/L -> €/L
        out.append({
            "year": year,
            "month": month,
            "month_iso": f"{year}-{month:02d}",
            "price": round(v / 100.0, 4),
        })
    return out


def latest_price(fuel: str = "95E10") -> float | None:
    rows = fetch_monthly(fuel, since_year=2024)
    return rows[-1]["price"] if rows else None
