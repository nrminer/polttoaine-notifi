"""
Vaikuttavat tekijät: Brent-raakaöljy, EUR/USD-kurssi ja JALOSTETTUJEN
TUOTTEIDEN spot-hinnat (RBOB-bensiini / NY Harbor ULSD ≈ gasoil).

Brent on raakaöljy → näkyy pumpulla 1–2 viikon viiveellä.
Jalostettu tuotespotti (gasoline futures, gasoil futures) on suora
tukkuhintasignaali → näkyy 3–7 päivän viiveellä, eli tarkalleen
day-ahead-ennusteen ikkunassa. Käytämme tätä päätarjoajaksi
"fundamental_anchorissa" ja Brentiä kontekstina + fallbackina.

Käytämme Yahoo Finance v8 chart -API:a (ilmainen, ei avainta).
- Brent:        BZ=F   (USD/bbl)
- EUR/USD:      EURUSD=X
- RBOB (95E10): RB=F   (USD/gallona, NYMEX RBOB Gasoline)
- ULSD/gasoil:  HO=F   (USD/gallona, NYMEX NY Harbor ULSD ≈ diesel-proxy)

Jos verkko ei ole käytettävissä, palautetaan None / tyhjä lista.
"""
from __future__ import annotations
import requests
from datetime import datetime, timezone

HEADERS = {"User-Agent": "Mozilla/5.0 (BensaVahti/2.0)"}
TIMEOUT = 12

# litres per US gallon (RBOB ja HO -futuurit hinnoitellaan USD/gallona)
_LITRES_PER_GAL = 3.785411784
# litres per oil barrel (Brent USD/bbl)
_LITRES_PER_BBL = 159.0

# Yahoo-symbolit polttoainekohtaiselle jalostetulle tuotteelle
_PRODUCT_SYMBOL = {
    "95E10":  ("RB=F", "RBOB-bensiini"),
    "diesel": ("HO=F", "NY Harbor ULSD (gasoil-proxy)"),
}


def _yahoo_chart(symbol: str, days: int = 60):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": f"{days}d", "interval": "1d"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    res = data["chart"]["result"][0]
    ts = res.get("timestamp", []) or []
    closes = res["indicators"]["quote"][0].get("close", []) or []
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        out.append({"date": d, "value": float(c)})
    return out


def fetch_brent(days: int = 60):
    try:
        return _yahoo_chart("BZ=F", days)
    except Exception:
        return []


def fetch_eur_usd(days: int = 60):
    try:
        return _yahoo_chart("EURUSD=X", days)
    except Exception:
        return []


def fetch_product_for_fuel(fuel: str, days: int = 60):
    """Hae jalostetun tuotteen futuurihinta (USD/gallona) annetulle
    polttoaineelle. Palauttaa (series, label). Tyhjä series jos symbolia
    ei ole tai verkko pettää — kutsujan on käsiteltävä None-tilanne."""
    sym_label = _PRODUCT_SYMBOL.get(fuel)
    if not sym_label:
        return [], None
    sym, label = sym_label
    try:
        return _yahoo_chart(sym, days), label
    except Exception:
        return [], label


def product_eur_per_l(usd_per_gal: float | None,
                      eur_usd: float | None) -> float | None:
    """Muunna jalostetun tuotteen USD/gallona → EUR/L. None jos puuttuu."""
    if usd_per_gal is None or eur_usd in (None, 0):
        return None
    return (float(usd_per_gal) / _LITRES_PER_GAL) / float(eur_usd)


def brent_eur_per_l(usd_per_bbl: float | None,
                    eur_usd: float | None) -> float | None:
    """Muunna Brent USD/bbl → EUR/L (tukkuraakaöljy)."""
    if usd_per_bbl is None or eur_usd in (None, 0):
        return None
    return (float(usd_per_bbl) / _LITRES_PER_BBL) / float(eur_usd)


def crack_spread_eur_per_l(product_usd_per_gal: float | None,
                           brent_usd_per_bbl: float | None,
                           eur_usd: float | None) -> float | None:
    """Yksinkertainen crack-spread: jalostettu tuote − Brent, EUR/L.

    Positiivinen lukema = jalostusmarginaali laajenee → pumppupaine
    nousee Brentin yli; negatiivinen = marginaali kapenee."""
    a = product_eur_per_l(product_usd_per_gal, eur_usd)
    b = brent_eur_per_l(brent_usd_per_bbl, eur_usd)
    if a is None or b is None:
        return None
    return a - b


def latest_value(series):
    if not series:
        return None
    return series[-1]["value"]


def delta_pct(series):
    if not series or len(series) < 2:
        return None
    return (series[-1]["value"] - series[-2]["value"]) / series[-2]["value"] * 100.0


def change_frac(series, lookback: int = 5):
    """Fractional change over the last `lookback` samples (≈ trading days).

    Returns e.g. 0.03 for a +3 % move. Robust to short series and Nones.
    Used by the prediction model for Brent / EUR-USD pass-through."""
    if not series or len(series) < 2:
        return None
    ref_idx = max(0, len(series) - 1 - lookback)
    ref = series[ref_idx].get("value")
    cur = series[-1].get("value")
    if not ref:
        return None
    return (cur - ref) / ref
