"""
Gas price alert: checks 95E10 prices across Finnish sources, finds the
cheapest one (optionally filtered to nearby cities), and sends an ntfy.sh
push notification when it crosses below a user-defined threshold.

Configuration via environment variables:
    NTFY_TOPIC        (required) ntfy.sh topic name, e.g. "my-secret-gas-alerts-xyz123"
    PRICE_THRESHOLD   (required) trigger when cheapest price is at or below this, e.g. "1.85"
    CITIES            (optional) comma-separated whitelist, e.g. "Espoo,Helsinki,Vantaa,Kauniainen"
                                 leave unset to scan all of Finland
    NTFY_SERVER       (optional) default https://ntfy.sh — change if self-hosting
    STATE_PATH        (optional) default ./state.json

State file tracks the last alerted price so you don't get spammed. A new
alert only fires when the price *re-crosses* below the threshold after
going back above it (configurable via RE_ALERT_DELTA below).
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from scrapers import polttoaine, tankille, bensahinta

# If price drops further by this much after an alert, send another one.
# e.g. alerted at 1.84 with threshold 1.85, and price falls to 1.79 → re-alert.
RE_ALERT_DELTA = 0.03

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))


def load_config() -> dict:
    topic = os.environ.get("NTFY_TOPIC")
    threshold = os.environ.get("PRICE_THRESHOLD")
    if not topic:
        sys.exit("error: NTFY_TOPIC env var is required")
    if not threshold:
        sys.exit("error: PRICE_THRESHOLD env var is required")
    try:
        threshold_f = float(threshold)
    except ValueError:
        sys.exit(f"error: PRICE_THRESHOLD must be a number, got {threshold!r}")

    cities_raw = os.environ.get("CITIES", "Helsinki,Vantaa,Espoo").strip()
    cities = {c.strip().lower() for c in cities_raw.split(",") if c.strip()}

    return {"topic": topic, "threshold": threshold_f, "cities": cities}


def gather_all_prices() -> list[dict]:
    """Run every scraper, merge results. Failures in one source are ignored."""
    all_rows: list[dict] = []
    for name, mod in [("polttoaine", polttoaine),
                      ("tankille", tankille),
                      ("bensahinta", bensahinta)]:
        try:
            rows = mod.fetch_prices()
            all_rows.extend(rows)
        except Exception as e:
            # Don't let one broken source kill the run
            print(f"[warn] {name} failed: {e}", file=sys.stderr)
    return all_rows


def filter_and_pick_cheapest(rows: list[dict], cities: set[str]) -> dict | None:
    if cities:
        rows = [r for r in rows if r["city"].lower() in cities]
    if not rows:
        return None
    return min(rows, key=lambda r: r["price"])


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_alerted_price": None, "last_run": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def should_alert(cheapest_price: float, threshold: float, state: dict) -> bool:
    """
    Alert if:
      - price is at or below threshold, AND
      - either we haven't alerted before, OR
      - price has dropped at least RE_ALERT_DELTA below the last alerted price
    """
    if cheapest_price > threshold:
        return False
    last = state.get("last_alerted_price")
    if last is None:
        return True
    return cheapest_price <= last - RE_ALERT_DELTA


def send_ntfy(topic: str, cheapest: dict, threshold: float) -> None:
    price = cheapest["price"]
    title = f"⛽ 95E10 @ {price:.3f} € — below {threshold:.2f}"
    body = (
        f"{cheapest['city']} · {cheapest['station']}\n"
        f"{cheapest['address']}\n"
        f"Updated {cheapest['date']} · via {cheapest['source']}"
    )
    url = f"{NTFY_SERVER}/{topic}"
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": "default",
        "Tags": "fuelpump",
    }
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(
        url,
        data=body.encode("utf-8"),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    cfg = load_config()
    state = load_state()

    rows = gather_all_prices()
    if not rows:
        print("[info] no price data fetched (all sources empty/failed)")
        return 1

    cheapest = filter_and_pick_cheapest(rows, cfg["cities"])
    if cheapest is None:
        print(f"[info] no matching stations in cities={cfg['cities']}")
        return 0

    print(f"[info] cheapest 95E10: {cheapest['price']:.3f} € at "
          f"{cheapest['city']} {cheapest['station']} ({cheapest['source']})")
    print(f"[info] threshold: {cfg['threshold']:.3f} €  "
          f"last alerted: {state.get('last_alerted_price')}")

    if should_alert(cheapest["price"], cfg["threshold"], state):
        send_ntfy(cfg["topic"], cheapest, cfg["threshold"])
        state["last_alerted_price"] = cheapest["price"]
        print(f"[info] ALERT sent: {cheapest['price']:.3f} €")
    else:
        # Reset alert state if price has climbed back above threshold,
        # so a future dip triggers a fresh alert.
        if cheapest["price"] > cfg["threshold"] and state.get("last_alerted_price"):
            state["last_alerted_price"] = None
            print("[info] price back above threshold, alert state cleared")
        else:
            print("[info] no alert (either above threshold or already alerted)")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
