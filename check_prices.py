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

TOP_N = 3
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


def top_cheapest(rows: list[dict], cities: set[str], n: int) -> list[dict]:
    if cities:
        rows = [r for r in rows if r["city"].lower() in cities]
    # Deduplicate by (city, station, address) — same station can be reported
    # multiple times by different sources. Keep the cheapest report per station.
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["city"].lower(), r["station"].lower(), r["address"].lower())
        if key not in best or r["price"] < best[key]["price"]:
            best[key] = r
    return sorted(best.values(), key=lambda r: r["price"])[:n]


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
    title = f"Halvin 95E10: {cheapest['price']:.3f} EUR/L"
    lines = []
    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}. {r['price']:.3f} EUR  {r['city']}  {r['station']}\n"
            f"   {r['address']}"
        )
    body = "\n".join(lines)

    url = f"{NTFY_SERVER}/{topic}"
    headers = {
        "Title": title.encode("utf-8"),
        "Content-Type": "text/plain; charset=utf-8",
        "Priority": "default",
        "Tags": "fuelpump",
    }
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()


def main() -> int:
    cfg = load_config()
    state = load_state()

    rows = gather_all_prices()
    if not rows:
        print("[info] no price data fetched")
        return 1

    top = top_cheapest(rows, cfg["cities"], TOP_N)
    if not top:
        print(f"[info] no stations in cities={cfg['cities']}")
        return 0

    for i, r in enumerate(top, 1):
        print(f"[info] {i}. {r['price']:.3f} EUR  {r['city']}  {r['station']} ({r['source']})")

    send_ntfy(cfg["topic"], top)
    print(f"[info] sent digest of {len(top)} stations")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["last_top"] = [
        {"price": r["price"], "city": r["city"], "station": r["station"], "address": r["address"]}
        for r in top
    ]
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
