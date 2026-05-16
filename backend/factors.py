"""
Vaikuttavat tekijät: Brent-raakaöljy ja EUR/USD-kurssi.

Käytämme Yahoo Finance v8 chart -API:a (ilmainen, ei avainta).
- Brent: BZ=F
- EUR/USD: EURUSD=X

Jos verkko ei ole käytettävissä, palautetaan None-arvot.
"""
from __future__ import annotations
import requests
from datetime import datetime, timezone

HEADERS = {"User-Agent": "Mozilla/5.0 (BensaVahti/2.0)"}
TIMEOUT = 12


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
