"""
ntfy.sh push notifications for BensaVahti daily summaries.

Format (matches user's previous-version notifications exactly):

  ⛽ 95E10 alkaen 1.922 EUR (Helsinki)
  === 95E10 ===
  Helsinki: 1.922 EUR
  Neste Oil Express - Viikki Viikinportti 1 (Pihlajamäentie 4 )
  Lähteet: polttoaine.net 1.922 | tankille.fi 1.999
  ...
  === Diesel ===
  Halvin koko Suomessa: 2.069 EUR
  Alavus - Kyläkaupan Bensa-asema - Tuuri Aspinmäentie 6
  ...

Env vars (read each call):
  NTFY_SERVER     default https://ntfy.sh
  NTFY_TOPIC      required (e.g. "polttoaine")
  NTFY_TOKEN      required
  NTFY_CLICK_URL  optional click target
"""
from __future__ import annotations
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests

from scrapers import polttoaine, tankille

logger = logging.getLogger("bensavahti.notify")

WATCHED_CITIES = ("Helsinki", "Vantaa", "Espoo")
FUEL_LABELS = {"95E10": "95E10", "diesel": "Diesel"}


def _config() -> tuple[str, str, str, str] | None:
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    token = (os.environ.get("NTFY_TOKEN") or "").strip()
    click = (os.environ.get("NTFY_CLICK_URL") or "https://polttoaine-notifi.vercel.app").strip()
    if not topic or not token:
        logger.info("ntfy disabled (NTFY_TOPIC or NTFY_TOKEN missing)")
        return None
    return server, topic, token, click


def _brand_of(name: str) -> str:
    """First-word brand prefix for cross-source matching.
    'Neste Oil Express' → 'Neste'; 'Neste Helsinki Viikki' → 'Neste'."""
    if not name:
        return ""
    first = name.split()[0]
    # normalize a couple of known multi-word brand families
    return first


def _cheapest_in_city(rows: list[dict], city: str) -> dict | None:
    matches = [r for r in rows if (r.get("city") or "") == city and r.get("price")]
    if not matches:
        return None
    return min(matches, key=lambda r: r["price"])


def _cheapest_by_brand_in_city(rows: list[dict], city: str, brand: str) -> dict | None:
    if not brand:
        return None
    matches = [r for r in rows
               if (r.get("city") or "") == city
               and (r.get("station") or "").startswith(brand)
               and r.get("price")]
    if not matches:
        # looser fallback: brand substring anywhere in station name
        matches = [r for r in rows
                   if (r.get("city") or "") == city
                   and brand.lower() in (r.get("station") or "").lower()
                   and r.get("price")]
    if not matches:
        return None
    return min(matches, key=lambda r: r["price"])


def _format_city_block(city: str, polttoaine_rows: list[dict],
                      tankille_rows: list[dict]) -> list[str]:
    out: list[str] = []
    p_pick = _cheapest_in_city(polttoaine_rows, city)
    t_pick = _cheapest_in_city(tankille_rows, city)
    # display price = cheapest of the two sources for that city
    best = None
    if p_pick and t_pick:
        best = p_pick if p_pick["price"] <= t_pick["price"] else t_pick
    else:
        best = p_pick or t_pick
    if not best:
        out.append(f"{city}: ei tietoa")
        return out

    out.append(f"{city}: {best['price']:.3f} EUR")
    name = best.get("station") or ""
    addr = best.get("address") or ""
    if addr:
        out.append(f"{name} - {addr}")
    else:
        out.append(name)

    # source comparison row — try to look up same-brand price in the OTHER source
    brand = _brand_of(name)
    if best.get("source") == "polttoaine.net":
        p_price = best["price"]
        t_match = _cheapest_by_brand_in_city(tankille_rows, city, brand)
        t_price = t_match["price"] if t_match else None
    else:
        t_price = best["price"]
        p_match = _cheapest_by_brand_in_city(polttoaine_rows, city, brand)
        p_price = p_match["price"] if p_match else None

    parts = []
    if p_price is not None:
        parts.append(f"polttoaine.net {p_price:.3f}")
    if t_price is not None:
        parts.append(f"tankille.fi {t_price:.3f}")
    if parts:
        out.append("Lähteet: " + " | ".join(parts))
    return out


def _format_fuel_section(fuel: str, polttoaine_rows: list[dict],
                         tankille_rows: list[dict]) -> list[str]:
    label = FUEL_LABELS.get(fuel, fuel)
    out: list[str] = [f"=== {label} ==="]

    # "Halvin koko Suomessa" line — only added for diesel (matches user's format)
    if fuel == "diesel":
        all_rows = (polttoaine_rows or []) + (tankille_rows or [])
        if all_rows:
            nat = min(all_rows, key=lambda r: r["price"])
            out.append(f"Halvin koko Suomessa: {nat['price']:.3f} EUR")
            city = nat.get("city") or "?"
            name = nat.get("station") or ""
            addr = nat.get("address") or ""
            tail = " - ".join(filter(None, [city, name, addr]))
            out.append(tail)

    for city in WATCHED_CITIES:
        out.extend(_format_city_block(city, polttoaine_rows, tankille_rows))
    return out


def build_detailed_message() -> tuple[str, str]:
    """Scrape both sources for both fuels and build the multi-fuel summary
    matching the user's preferred format. Returns (title, body)."""
    # Parallel scrape: 4 calls (2 sources × 2 fuels)
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_p95 = ex.submit(polttoaine.fetch_prices, "95E10")
        f_pd = ex.submit(polttoaine.fetch_prices, "diesel")
        f_t95 = ex.submit(tankille.fetch_prices, "95E10")
        f_td = ex.submit(tankille.fetch_prices, "diesel")
        p95 = _safe(f_p95.result)
        pd = _safe(f_pd.result)
        t95 = _safe(f_t95.result)
        td = _safe(f_td.result)

    # Header: cheapest 95E10 among WATCHED_CITIES
    cheapest_watched = None
    for c in WATCHED_CITIES:
        cand = []
        cp = _cheapest_in_city(p95, c)
        ct = _cheapest_in_city(t95, c)
        if cp:
            cand.append(cp)
        if ct:
            cand.append(ct)
        if not cand:
            continue
        best = min(cand, key=lambda r: r["price"])
        if cheapest_watched is None or best["price"] < cheapest_watched["price"]:
            cheapest_watched = best

    if cheapest_watched:
        header = (f"⛽ 95E10 alkaen {cheapest_watched['price']:.3f} EUR "
                  f"({cheapest_watched.get('city','?')})")
    else:
        header = "⛽ 95E10: ei tietoa"

    lines: list[str] = [header, ""]
    lines.extend(_format_fuel_section("95E10", p95, t95))
    lines.append("")
    lines.extend(_format_fuel_section("diesel", pd, td))

    title = f"Polttoaine - alkaen {cheapest_watched['price']:.3f} EUR" if cheapest_watched else "Polttoaine"
    return title, "\n".join(lines)


def _safe(call) -> list[dict]:
    try:
        out = call()
        return out if isinstance(out, list) else []
    except Exception as e:
        logger.warning("scrape failed in notify: %s", e)
        return []


def send_daily_summary(captures: list[dict] | None = None) -> bool:
    """Build and publish today's notification.
    `captures` is accepted for backwards compatibility but ignored — we always
    do a fresh scrape so the message includes per-city + per-source detail."""
    cfg = _config()
    if cfg is None:
        return False
    server, topic, token, click = cfg

    try:
        title, body = build_detailed_message()
    except Exception as e:
        logger.exception("notify message build failed: %s", e)
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Title": title,  # must be ASCII-safe; we use plain text
        "Priority": "3",
        "Tags": "fuelpump,car,euro",
        "Click": click,
    }
    try:
        r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"),
                          headers=headers, timeout=15)
        if not r.ok:
            logger.error("ntfy publish failed %s: %s", r.status_code, r.text[:200])
            return False
        logger.info("ntfy summary sent to %s (%d chars)", topic, len(body))
        return True
    except Exception as e:
        logger.exception("ntfy publish exception: %s", e)
        return False
