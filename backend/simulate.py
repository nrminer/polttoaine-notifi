"""
Simuloitu historiallinen polttoainehintadata Suomeen.

Koska scrapereista saadaan vain nykyhetki, simuloidaan 180 päivän historia
realistisilla suomalaisilla polttoainehintamalleilla:

- Pohjataso (lähellä todellista nykyhintaa)
- Hidas trendi (Brent-raakaöljyn vaikutus)
- Viikonpäivätrendi (tiistait/keskiviikot kalliimpia)
- Satunnaisvaihtelu (säätietoa, paikallinen markkinakilpailu)
- Kausivaihtelu (kesä = korkeammat hinnat)
"""
from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone


# Suomalaiset polttoainehinnat keväällä 2026 (€/L)
BASELINE = {
    "95E10": 1.92,
    "diesel": 2.07,
}

# Alueellinen kerroin (suhde valtakunnan keskiarvoon)
CITY_FACTORS = {
    "Helsinki":   1.00,
    "Espoo":      1.02,
    "Vantaa":     0.99,
    "Tampere":    0.97,
    "Turku":      0.98,
    "Oulu":       0.96,
    "Jyväskylä":  0.97,
    "Kuopio":     0.97,
    "Lahti":      0.98,
    "Suomi":      1.00,  # valtakunnan keskiarvo
}


def simulate_history(fuel: str, region: str = "Suomi", days: int = 180,
                     end_price: float | None = None,
                     seed: int = 42) -> list[dict]:
    """Tuottaa `days`-pituisen päivittäisen historian päättyen tähän päivään.

    Jos `end_price` annetaan, simuloitu sarja kalibroidaan päättymään lähelle sitä.
    """
    if fuel not in BASELINE:
        raise ValueError(f"unknown fuel {fuel}")

    rng = random.Random(seed + hash(region) % 10_000)

    factor = CITY_FACTORS.get(region, 1.00)
    base = (end_price or BASELINE[fuel]) * factor
    # aloitustaso vähän alempana, jotta trendi näkyy
    start = base * rng.uniform(0.93, 0.99)

    today = datetime.now(timezone.utc).date()
    series = []

    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        progress = i / max(1, days - 1)

        # päätrendi: lineaarinen alusta loppuun
        trend = start + (base - start) * progress

        # kausivaihtelu: kesä korkeampi (heinäkuun puolivälissä huippu)
        day_of_year = d.timetuple().tm_yday
        seasonal = 0.020 * math.sin(2 * math.pi * (day_of_year - 105) / 365.0)

        # viikkokuvio: ma=0 ... su=6
        weekday = d.weekday()
        weekly = {0: -0.002, 1: 0.008, 2: 0.010, 3: 0.004, 4: -0.005, 5: -0.008, 6: -0.007}[weekday]

        # satunnaisuus
        noise = rng.gauss(0, 0.006)

        price = trend + seasonal + weekly + noise
        series.append({
            "date": d.isoformat(),
            "price": round(price, 4),
            "fuel": fuel,
            "region": region,
            "source": "simulated",
        })

    # kalibroi tarvittaessa
    if end_price is not None and series:
        delta = end_price * factor - series[-1]["price"]
        # jaa pieni kalibrointi viim. 14 päivälle painottaen loppupäätä
        n_cal = min(14, len(series))
        for i in range(n_cal):
            weight = (i + 1) / n_cal
            series[-n_cal + i]["price"] = round(series[-n_cal + i]["price"] + delta * weight, 4)

    return series
