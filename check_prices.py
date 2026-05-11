"""
Polttoaine Notifi — digest mode.

Every run, fetches current 95E10 prices, filters to the configured cities,
and sends a single ntfy.sh push notification listing the 3 cheapest stations.

Environment variables:
    NTFY_TOPIC   (required) ntfy.sh topic
    NTFY_TOKEN   (optional) ntfy bearer token, if topic requires auth
    CITIES       (optional) comma-separated, default "Helsinki,Vantaa,Espoo"
    NTFY_SERVER  (optional) default https://ntfy.sh
    STATE_PATH   (optional) default ./state.json
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from scrapers import polttoaine, tankille, bensahinta

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))


def load_config() -> dict:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        sys.exit("error: NTFY_TOPIC env var is required")

    cities_raw = os.environ.get("CITIES", "Helsinki,Vantaa,Espoo").strip()
    cities = {c.strip().lower() for c in cities_raw.split(",") if c.strip()}

    return {"topic": topic, "cities": cities}


def gather_all_prices() -> list[dict]:
    all_rows: list[dict] = []
    for name, mod in [("polttoaine", polttoaine),
                      ("tankille", tankille),
                      ("bensahinta", bensahinta)]:
        try:
            all_rows.extend(mod.fetch_prices())
        except Exception as e:
            print(f"[warn] {name} failed: {e}", file=sys.stderr)
    return all_rows


def cheapest_per_city(rows: list[dict], cities: set[str]) -> list[dict]:
    """One cheapest station per configured city, sorted by price ascending."""
    best: dict[str, dict] = {}
    for r in rows:
        city = r["city"].lower()
        if cities and city not in cities:
            continue
        if city not in best or r["price"] < best[city]["price"]:
            best[city] = r
    return sorted(best.values(), key=lambda r: r["price"])


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def send_ntfy(topic: str, top: list[dict]) -> None:
    cheapest = top[0]
    title = f"Halvin 95E10: {cheapest['price']:.3f} EUR/L ({cheapest['city']})"
    lines = []
    for r in top:
        lines.append(
            f"{r['city']}: {r['price']:.3f} EUR\n"
            f"  {r['station']} - {r['address']}"
        )
    body = "\n\n".join(lines)

    url = f"{NTFY_SERVER}/{topic}"
    if not url.startswith("https://"):
        sys.exit(f"error: refusing to POST credentials over non-HTTPS URL {url!r}")
    token = os.environ.get("NTFY_TOKEN")
    if not token:
        sys.exit("error: NTFY_TOKEN env var is required (auth-protected topic)")
    headers = {
        "Title": title.encode("utf-8"),
        "Content-Type": "text/plain; charset=utf-8",
        "Priority": "default",
        "Tags": "fuelpump",
        "Authorization": f"Bearer {token}",
    }
    resp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()


def main() -> int:
    cfg = load_config()
    state = load_state()

    rows = gather_all_prices()
    if not rows:
        print("[info] no price data fetched")
        return 1

    top = cheapest_per_city(rows, cfg["cities"])
    if not top:
        print(f"[info] no stations in cities={cfg['cities']}")
        return 0

    for r in top:
        print(f"[info] {r['price']:.3f} EUR  {r['city']}  {r['station']} ({r['source']})")

    fingerprint = [
        {"city": r["city"], "price": round(r["price"], 3),
         "station": r["station"], "address": r["address"]}
        for r in top
    ]
    last_sent = state.get("last_sent")
    if last_sent == fingerprint:
        print("[info] cheapest unchanged since last alert — skipping notification")
    else:
        send_ntfy(cfg["topic"], top)
        state["last_sent"] = fingerprint
        print(f"[info] sent digest ({len(top)} cities)")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
