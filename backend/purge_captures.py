"""
Poista tiettyjä daily_tracker capture-rivejä (date + hour).

Oletuksena pyytäjän tapaus: 2026-05-16 tunnit 6 ja 20 (vanhat slotit ennen
14/21-aikataulua). TURVALLINEN: oletuksena DRY-RUN — näyttää mitä poistettaisiin
mutta EI poista. Lisää --yes poistaaksesi oikeasti.

Käyttö (backend-hakemistosta, sama .env kuin palvelimella):

    python purge_captures.py                       # dry-run: 2026-05-16 h6,h20
    python purge_captures.py --yes                 # poista oikeasti
    python purge_captures.py --date 2026-05-16 --hours 6,20 --yes
    python purge_captures.py --date 2026-05-16 --hours 6,20 --fuel 95E10 --yes
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

FUELS = ("95E10", "diesel")


async def main() -> int:
    p = argparse.ArgumentParser(description="Poista daily_tracker capture-rivejä")
    p.add_argument("--date", default="2026-05-16",
                   help="Päivä YYYY-MM-DD (oletus 2026-05-16)")
    p.add_argument("--hours", default="6,20",
                   help="Pilkuilla erotellut tunnit (oletus 6,20)")
    p.add_argument("--fuel", choices=[*FUELS, "all"], default="all",
                   help="Polttoaine (oletus: kaikki)")
    p.add_argument("--region", default="Suomi", help="Alue (oletus Suomi)")
    p.add_argument("--yes", action="store_true",
                   help="Poista OIKEASTI (muuten vain dry-run)")
    args = p.parse_args()

    try:
        hours = sorted({int(h) for h in args.hours.split(",") if h.strip() != ""})
    except ValueError:
        print(f"VIRHE: epäkelpo --hours arvo {args.hours!r}", file=sys.stderr)
        return 2
    if not hours:
        print("VIRHE: --hours tyhjä", file=sys.stderr)
        return 2

    load_dotenv()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("VIRHE: MONGO_URL ja DB_NAME puuttuvat (.env).", file=sys.stderr)
        return 2

    query: dict = {"date": args.date, "hour": {"$in": hours},
                   "region": args.region}
    if args.fuel != "all":
        query["fuel"] = args.fuel

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    rc = 0
    try:
        cur = db.daily_tracker.find(
            query, {"_id": 0, "prediction_full": 0}
        ).sort([("date", 1), ("hour", 1)])
        rows = await cur.to_list(length=1000)

        print(f"Kysely: {query}")
        print(f"Osumia: {len(rows)}")
        print("-" * 64)
        for r in rows:
            print(f"  {r.get('date')} h{r.get('hour'):>2}  {r.get('fuel'):<6} "
                  f"region={r.get('region')}  "
                  f"actual_cheapest={r.get('actual_cheapest')}")
        print("-" * 64)

        if not rows:
            print("Ei poistettavaa. Valmis.")
            return 0

        if not args.yes:
            print(f"DRY-RUN: {len(rows)} riviä TÄSMÄÄ mutta EI poistettu.")
            print("Aja sama komento --yes -lipulla poistaaksesi oikeasti.")
            return 0

        res = await db.daily_tracker.delete_many(query)
        print(f"POISTETTU: {res.deleted_count} riviä daily_tracker-kokoelmasta.")
        if res.deleted_count != len(rows):
            print(f"HUOM: löydettiin {len(rows)} mutta poistettiin "
                  f"{res.deleted_count} (kanta muuttui ajon aikana?).")
            rc = 1
    finally:
        client.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
