"""
Polttoaine Notifi — digest with change detection.

Each run:
  - Scrapes 95E10 and diesel prices from polttoaine.net.
  - Picks the cheapest station per city for both fuels (Helsinki/Vantaa/Espoo).
  - Also picks the cheapest diesel station anywhere in Finland.
  - Sends a single ntfy notification — but only if the result differs from the
    last sent snapshot (stored in state.json).

Environment variables:
    NTFY_TOPIC   (required) ntfy.sh topic
    NTFY_TOKEN   (required) ntfy bearer token
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

from scrapers import polttoaine, tankille

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))


def load_config() -> dict:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        sys.exit("error: NTFY_TOPIC env var is required")
    cities_raw = os.environ.get("CITIES", "Helsinki,Vantaa,Espoo").strip()
    cities = [c.strip() for c in cities_raw.split(",") if c.strip()]
    return {"topic": topic, "cities": cities}


def gather(fuel: str) -> list[dict]:
    rows: list[dict] = []
    for name, mod in [("polttoaine", polttoaine),
                      ("tankille", tankille)]:
        try:
            rows.extend(mod.fetch_prices(fuel))
        except Exception as e:
            print(f"[warn] {name} ({fuel}) failed: {e}", file=sys.stderr)
    return rows


def cheapest_in(rows: list[dict], city: str) -> dict | None:
    pick = [r for r in rows if r["city"].lower() == city.lower()]
    return min(pick, key=lambda r: r["price"]) if pick else None


def cheapest_any(rows: list[dict]) -> dict | None:
    return min(rows, key=lambda r: r["price"]) if rows else None


def per_source_cheapest(rows: list[dict], city: str) -> dict[str, dict]:
    """Returns {source_name: cheapest_row_in_city} — used for cross-source validation."""
    best: dict[str, dict] = {}
    for r in rows:
        if r["city"].lower() != city.lower():
            continue
        s = r["source"]
        if s not in best or r["price"] < best[s]["price"]:
            best[s] = r
    return best


# If sources disagree by more than this many euros on the cheapest in a city,
# include a note in the notification body.
SOURCE_TOLERANCE = 0.005  # half a cent


def discrepancy_note(by_src: dict[str, dict]) -> str | None:
    if len(by_src) < 2:
        return None
    prices = [r["price"] for r in by_src.values()]
    if max(prices) - min(prices) <= SOURCE_TOLERANCE:
        return None
    parts = sorted(by_src.items(), key=lambda kv: kv[1]["price"])
    return "  Lähteet: " + " | ".join(f"{s} {r['price']:.3f}" for s, r in parts)


def fmt_station(r: dict | None) -> str:
    if not r:
        return "ei tietoa"
    return f"{r['price']:.3f} EUR  {r['city']} - {r['station']}"


def build_digest(cities: list[str]) -> dict:
    e10 = gather("95E10")
    diesel = gather("diesel")

    return {
        "95E10": {c: cheapest_in(e10, c) for c in cities},
        "diesel": {c: cheapest_in(diesel, c) for c in cities},
        "diesel_any": cheapest_any(diesel),
        "_per_source": {
            "95E10":  {c: per_source_cheapest(e10, c)    for c in cities},
            "diesel": {c: per_source_cheapest(diesel, c) for c in cities},
        },
    }


def fingerprint(digest: dict) -> list:
    """Only the cheapest *price* per slot — station identity is ignored."""
    def price(r):
        return None if not r else round(r["price"], 3)
    out = []
    for fuel in ("95E10", "diesel"):
        for city, r in digest[fuel].items():
            out.append([fuel, city, price(r)])
    out.append(["diesel_any", None, price(digest["diesel_any"])])
    return out


def render_body(digest: dict, cities: list[str]) -> tuple[str, str]:
    # Title = cheapest 95E10 across the configured cities
    e10_picks = [r for r in digest["95E10"].values() if r]
    if e10_picks:
        top_e10 = min(e10_picks, key=lambda r: r["price"])
        title = f"95E10 alkaen {top_e10['price']:.3f} EUR ({top_e10['city']})"
    else:
        title = "Polttoaine-paivitys"

    per_src = digest.get("_per_source", {"95E10": {}, "diesel": {}})

    def render_city(fuel: str, c: str) -> list[str]:
        r = digest[fuel].get(c)
        if not r:
            return [f"{c}: ei tietoa"]
        out = [f"{c}: {r['price']:.3f} EUR",
               f"  {r['station']} - {r['address']}".rstrip(" -")]
        note = discrepancy_note(per_src.get(fuel, {}).get(c, {}))
        if note:
            out.append(note)
        return out

    lines = ["=== 95E10 ==="]
    for c in cities:
        lines.extend(render_city("95E10", c))

    lines.append("")
    lines.append("=== Diesel ===")
    any_d = digest["diesel_any"]
    if any_d:
        lines.append(f"Halvin koko Suomessa: {any_d['price']:.3f} EUR")
        lines.append(f"  {any_d['city']} - {any_d['station']} - {any_d['address']}".rstrip(" -"))
    for c in cities:
        lines.extend(render_city("diesel", c))

    return title, "\n".join(lines)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def send_ntfy(topic: str, title: str, body: str) -> None:
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

    digest = build_digest(cfg["cities"])
    title, body = render_body(digest, cfg["cities"])
    print(f"[info] title: {title}")
    for line in body.splitlines():
        print(f"  {line}")

    fp = fingerprint(digest)
    if state.get("last_sent") == fp:
        print("[info] unchanged since last alert — skipping notification")
    else:
        send_ntfy(cfg["topic"], title, body)
        state["last_sent"] = fp
        print("[info] sent")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
