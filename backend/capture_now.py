"""
Manuaalinen capture NYT — skrapaa tämänhetkiset hinnat ja TALLENTAA ne
pysyvästi MongoDB:n `daily_tracker`-kokoelmaan tämän päivän päivämäärälle.

Käyttää samaa testattua putkea kuin ajastettu capture (tracker.capture_daily):
  1. Skrapaa halvin asema + kaupunkikohtainen halvin/keskihinta (by_city)
  2. Lukee eilisen ennusteen tälle päivälle (accuracy-trackaus)
  3. Ajaa tuoreen ennusteen huomiselle (predict_tomorrow: MA/LR/ES/
     fundamental_anchor/AI + ensemble)
  4. UPSERT yksi rivi per (date, hour, fuel, region) — idempotentti, "jää
     pysyvästi"

Rivi tallennetaan TÄHÄN hetkeen Helsinki-aikaa (oma `hour`), joten se ei
ylikirjoita ajastettuja 14:00 / 21:00 -slotteja vaan jää omaksi pisteekseen.

Käyttö (backend-hakemistosta, sama .env kuin palvelimella):

    python capture_now.py                 # molemmat polttoaineet, nykyhetki
    python capture_now.py --fuel 95E10    # vain 95E10
    python capture_now.py --hour 21       # pakota tietty slot
    python capture_now.py --notify        # lähetä myös ntfy-ilmoitus
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

import tracker as tracker_mod
import notify as notify_mod

FUELS = ("95E10", "diesel")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Manuaalinen capture nyt")
    parser.add_argument(
        "--fuel", choices=[*FUELS, "all"], default="all",
        help="Mikä polttoaine (oletus: kaikki)",
    )
    parser.add_argument(
        "--region", default="Suomi",
        help="Alue (oletus: Suomi — sama kuin ajastettu capture)",
    )
    parser.add_argument(
        "--hour", type=int, default=None,
        help="Pakota tietty tunti (0-23). Oletus: nykyinen Helsinki-tunti.",
    )
    parser.add_argument(
        "--notify", action="store_true",
        help="Lähetä ntfy-ilmoitus capturen jälkeen",
    )
    args = parser.parse_args()

    load_dotenv()  # lukee backend/.env (MONGO_URL, DB_NAME, EMERGENT_LLM_KEY…)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("VIRHE: MONGO_URL ja DB_NAME puuttuvat ympäristöstä (.env).",
              file=sys.stderr)
        return 2

    now_hel = datetime.now(tracker_mod.HELSINKI)
    hour = args.hour if args.hour is not None else now_hel.hour
    fuels = FUELS if args.fuel == "all" else (args.fuel,)

    print(f"Capture NYT  ·  {now_hel:%Y-%m-%d %H:%M:%S} Helsinki  ·  "
          f"hour={hour:02d}  ·  region={args.region}  ·  "
          f"fuels={', '.join(fuels)}")
    print("-" * 72)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    executor = ThreadPoolExecutor(max_workers=8)
    captured: list[dict] = []
    rc = 0

    try:
        # daily_tracker -indeksi (sama kuin server.py:n startupissa) — varmistaa
        # ettei skripti kaadu jos kokoelma on tyhjä eikä indeksiä vielä ole
        try:
            await db.daily_tracker.create_index(
                [("fuel", 1), ("region", 1), ("date", 1), ("hour", 1)],
                unique=True,
            )
        except Exception:
            pass

        for fuel in fuels:
            try:
                doc = await tracker_mod.capture_daily(
                    db, executor, fuel, region=args.region, hour=hour,
                )
                captured.append(doc)
                ac = doc.get("actual_cheapest")
                city = doc.get("actual_cheapest_city") or "?"
                stn = doc.get("actual_cheapest_station") or "?"
                pred = doc.get("prediction_for_tomorrow_cheapest")
                bc = doc.get("by_city") or {}
                print(f"[{fuel}] TALLENNETTU  date={doc['date']} "
                      f"hour={doc['hour']:02d}")
                print(f"  halvin Suomessa : "
                      f"{ac if ac is not None else '—'} €/L  ({city} — {stn})")
                print(f"  huom. ennuste   : "
                      f"{pred if pred is not None else '—'} €/L")
                if bc:
                    cities = ", ".join(
                        f"{c} {v.get('cheapest')}/{v.get('average')}"
                        for c, v in bc.items()
                        if v.get("cheapest") is not None
                    )
                    print(f"  kaupungit (halvin/ka): {cities or '—'}")
                print()
            except Exception as e:  # älä keskeytä muita polttoaineita
                rc = 1
                print(f"[{fuel}] VIRHE: {type(e).__name__}: {e}",
                      file=sys.stderr)

        if args.notify and captured:
            try:
                ok = notify_mod.send_daily_summary(captured)
                status = ("lähetetty" if ok else
                          "ei lähetetty (NTFY_TOPIC/NTFY_TOKEN puuttuu?)")
                print(f"ntfy: {status}")
            except Exception as e:
                print(f"ntfy VIRHE: {e}", file=sys.stderr)
    finally:
        client.close()
        executor.shutdown(wait=False)

    if captured:
        print("-" * 72)
        print(f"Valmis. {len(captured)} capture-riviä tallennettu pysyvästi "
              f"daily_tracker-kokoelmaan (idempotentti per date+hour+fuel).")
    return rc


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
