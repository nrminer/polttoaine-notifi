"""
ntfy.sh push notifications for BensaVahti daily summaries.

Sends one summary per scheduled run (06:00 + 20:00 Helsinki) covering both
95E10 and diesel — today's cheapest + tomorrow's prediction + delta.

Env vars (read at call time):
  NTFY_SERVER  : default https://ntfy.sh
  NTFY_TOPIC   : required, e.g. "polttoaine"
  NTFY_TOKEN   : required, paid ntfy.sh bearer token
  NTFY_CLICK_URL : optional, link target when notification is tapped
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger("bensavahti.notify")

HELSINKI = ZoneInfo("Europe/Helsinki")


def _config() -> tuple[str, str, str, str] | None:
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    token = os.environ.get("NTFY_TOKEN", "").strip()
    click = os.environ.get("NTFY_CLICK_URL", "https://polttoaine-notifi.vercel.app").strip()
    if not topic or not token:
        logger.info("ntfy disabled (NTFY_TOPIC or NTFY_TOKEN missing)")
        return None
    return server, topic, token, click


def _arrow(delta: float | None) -> str:
    if delta is None:
        return "→"
    if delta > 0.0005:
        return f"↑ +{delta:.3f}"
    if delta < -0.0005:
        return f"↓ {delta:.3f}"
    return "→ tasainen"


def _format_summary(captures: list[dict]) -> tuple[str, str]:
    """Returns (title, body) for the notification.
    captures: list of daily_tracker doc dicts (one per fuel)."""
    now_hel = datetime.now(HELSINKI)
    # Title must be ASCII-only (HTTP header constraint)
    title = f"BensaVahti {now_hel:%H:%M} - polttoaine {now_hel:%-d.%-m.}"

    lines: list[str] = []
    for doc in captures:
        fuel = doc.get("fuel", "?")
        actual = doc.get("actual_cheapest")
        tomorrow = doc.get("prediction_for_tomorrow_cheapest")
        city = doc.get("actual_cheapest_city") or "?"
        station = doc.get("actual_cheapest_station") or ""
        delta = (tomorrow - actual) if (tomorrow is not None and actual is not None) else None

        line1 = f"⛽ {fuel}: {actual:.3f} €/L" if actual is not None else f"⛽ {fuel}: —"
        line1 += f" ({city})" if city else ""
        lines.append(line1)
        if station:
            lines.append(f"   {station}")
        if tomorrow is not None:
            lines.append(f"   → huomenna {tomorrow:.3f} €/L  {_arrow(delta)}")
        lines.append("")  # blank between fuels

    return title, "\n".join(lines).strip()


def send_daily_summary(captures: list[dict]) -> bool:
    """Send one consolidated ntfy notification. Returns True on success.
    Never raises — failures are logged so the scheduler keeps running."""
    cfg = _config()
    if cfg is None:
        return False
    server, topic, token, click = cfg

    if not captures:
        logger.info("ntfy: no captures, skipping")
        return False

    title, body = _format_summary(captures)
    url = f"{server}/{topic}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Title": title,
        "Priority": "3",
        "Tags": "fuelpump,car,euro",
        "Click": click,
    }
    try:
        r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=10)
        if not r.ok:
            logger.error("ntfy publish failed %s: %s", r.status_code, r.text[:200])
            return False
        logger.info("ntfy summary sent to %s (%d chars body)", topic, len(body))
        return True
    except Exception as e:
        logger.exception("ntfy publish exception: %s", e)
        return False
