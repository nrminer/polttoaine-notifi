"""
Real historical price interpolator.

Takes monthly anchor points from Tilastokeskus and produces daily price
estimates by:
  - placing each monthly value on the 15th of that month
  - linearly interpolating daily prices between anchors
  - adding small weekday + noise variation so chart isn't a straight line

Regional values are scaled by CITY_FACTORS from simulate.py.

The final tail of the series (last 30 days) is calibrated to the latest
scraped current price if provided, so the chart smoothly connects to
"today".
"""
from __future__ import annotations
import math
import random
from datetime import date, timedelta

from simulate import CITY_FACTORS


def _weekday_bias(d: date) -> float:
    return {0: -0.002, 1: 0.008, 2: 0.010, 3: 0.004,
            4: -0.005, 5: -0.008, 6: -0.007}[d.weekday()]


def build_real_daily(anchors: list[dict], days: int = 365,
                     end_price: float | None = None,
                     region: str = "Suomi",
                     seed: int = 7) -> list[dict]:
    """anchors: [{"year","month","price"}, ...] sorted by month asc.

    Returns daily series ending today, length `days`.
    """
    if not anchors:
        return []

    rng = random.Random(seed + (hash(region) & 0xFFFF))
    factor = CITY_FACTORS.get(region, 1.00)

    # rakenna anchor-pisteet: (date, price)
    anchor_pts = []
    for a in anchors:
        anchor_date = date(a["year"], a["month"], 15)
        anchor_pts.append((anchor_date, a["price"] * factor))
    anchor_pts.sort()

    today = date.today()
    start = today - timedelta(days=days - 1)

    def interp(d: date) -> float:
        # ennen ensimmäistä ankkuria tai sen jälkeen viimeisen jälkeen → reuna-arvot
        if d <= anchor_pts[0][0]:
            return anchor_pts[0][1]
        if d >= anchor_pts[-1][0]:
            return anchor_pts[-1][1]
        # binäärihaku
        lo, hi = 0, len(anchor_pts) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if anchor_pts[mid][0] <= d:
                lo = mid
            else:
                hi = mid
        a_d, a_p = anchor_pts[lo]
        b_d, b_p = anchor_pts[hi]
        span = (b_d - a_d).days or 1
        frac = (d - a_d).days / span
        return a_p + (b_p - a_p) * frac

    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        base = interp(d)
        # päivän kuukausi-ankkuri saa pienen viikon ja kohinan
        noise = rng.gauss(0, 0.005)
        price = base + _weekday_bias(d) + noise
        out.append({
            "date": d.isoformat(),
            "price": round(price, 4),
            "region": region,
            "source": "statfin+interp",
        })

    # Kalibroi viimeiset 7 pv kevyesti lähestymään nykyhintaa, jotta
    # piikkiä viime kuukauden anchoriin ei tule liian rajusti.
    if end_price is not None and out:
        target = end_price * factor
        delta = target - out[-1]["price"]
        # rajoita kalibrointi pieneen (max ±0.05 €/L)
        if abs(delta) <= 0.05:
            n_cal = min(7, len(out))
            for i in range(n_cal):
                weight = (i + 1) / n_cal
                out[-n_cal + i]["price"] = round(
                    out[-n_cal + i]["price"] + delta * weight, 4
                )

    return out
