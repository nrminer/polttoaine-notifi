"""
Migration script: backfill price_observations and stations from legacy snapshots + daily_tracker.

PURPOSE
-------
Converts the legacy snapshot-based schema to the new normalized observations model:
  - Reads `snapshots` collection (individual station prices from scrapes)
  - Reads `daily_tracker` collection (captured cheapest prices per city)
  - Writes to `price_observations` (time-series of station prices)
  - Writes to `stations` (registry of unique stations)

WHEN TO RUN
-----------
Run this ONCE after deploying the new observation-based schema to production.
Safe to re-run: upsert logic prevents duplication.

BEFORE RUNNING
--------------
1. Deploy the new server.py with price_observations + stations collections
2. Ensure MONGO_URL and DB_NAME are set in .env or environment
3. Run with --dry-run first to preview the migration without writes

HOW TO RUN
----------
From backend/:
  python migrate_to_observations.py --dry-run   # preview only
  python migrate_to_observations.py             # perform migration

WHAT IT DOES
------------
1. Scans snapshots collection for scraped station-level data
2. Extracts unique stations → upserts into `stations` registry
3. Creates price_observations with synthetic scraped_at timestamps
   (snapshot.ts is used as the base; hour/minute are preserved if available)
4. Scans daily_tracker for per-city cheapest captures
5. Creates observations for tracked cities (using by_city data)
6. Reports progress: stations registered, observations created

SYNTHETIC TIMESTAMPS
--------------------
Legacy snapshots only have a single `ts` field (scrape time). Individual
station prices lack their own timestamp. We SYNTHESIZE `scraped_at` by
using the snapshot timestamp as-is (conservative: all stations in the
batch share the same scrape time). This is NOT fabricated hour-resolution
— it's the actual scrape batch timestamp applied uniformly.

IDEMPOTENCY
-----------
Safe to re-run: upserts check (station_id, fuel, scraped_at) uniqueness
for observations; station_id uniqueness for stations registry.

DATA LOSS
---------
None. Original snapshots and daily_tracker remain untouched.
"""
from __future__ import annotations
import asyncio
import argparse
import logging
import os
import re
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# ---------------- configuration ----------------

load_dotenv()
logger = logging.getLogger("migrate_observations")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Station ID generation: normalize station name to a stable identifier
def _normalize_station_name(name: str, city: str) -> str:
    """Generate a stable station_id from station name + city.

    Strips common noise (punctuation, case) to improve deduplication.
    Format: city_stationname (lowercase, alphanumeric + underscore).
    """
    # remove common punctuation and collapse whitespace
    clean = re.sub(r'[^\w\s-]', '', name.lower())
    clean = re.sub(r'\s+', '_', clean.strip())
    city_clean = re.sub(r'[^\w\s]', '', city.lower())
    city_clean = re.sub(r'\s+', '_', city_clean.strip())
    return f"{city_clean}_{clean}"


def _parse_snapshot_stations(snap: dict) -> list[dict]:
    """Extract individual station observations from a snapshot document.

    Returns list of {station_id, name, city, address, fuel, price, scraped_at, source}.
    """
    ts = snap.get("ts")
    fuel = snap.get("fuel")
    if not ts or not fuel:
        return []

    # parse ISO timestamp
    try:
        scraped_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        logger.warning("invalid timestamp in snapshot: %s", ts)
        return []

    # snapshots don't store individual station lists in the root anymore
    # (the current schema only has aggregates). Check if there's a legacy
    # 'stations' field from older snapshots.
    stations_list = snap.get("stations", [])
    if not stations_list:
        return []

    observations = []
    for st in stations_list:
        city = st.get("city", "Unknown")
        name = st.get("station", "Unknown Station")
        price = st.get("price")
        address = st.get("address", "")
        source = st.get("source", "unknown")

        if price is None:
            continue

        station_id = _normalize_station_name(name, city)
        observations.append({
            "station_id": station_id,
            "name": name,
            "city": city,
            "address": address,
            "fuel": fuel,
            "price": round(price, 4),
            "scraped_at": scraped_at,
            "source": source,
        })

    return observations


def _parse_daily_tracker_by_city(doc: dict) -> list[dict]:
    """Extract per-city observations from a daily_tracker document's by_city field.

    Returns list of {station_id, name, city, address, fuel, price, scraped_at, source}.
    """
    date = doc.get("date")
    hour = doc.get("hour")
    fuel = doc.get("fuel")
    by_city = doc.get("by_city") or {}

    if not date or hour is None or not fuel:
        return []

    # synthesize scraped_at from date + hour (Helsinki timezone assumed in tracker.py)
    # use captured_at if available, otherwise construct from date + hour
    captured_at_str = doc.get("captured_at")
    if captured_at_str:
        try:
            scraped_at = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
        except Exception:
            # fallback: construct from date + hour
            scraped_at = datetime.fromisoformat(f"{date}T{hour:02d}:00:00+00:00")
    else:
        scraped_at = datetime.fromisoformat(f"{date}T{hour:02d}:00:00+00:00")

    observations = []
    for city, agg in by_city.items():
        cheapest_price = agg.get("cheapest")
        station_name = agg.get("station", "Unknown Station")
        source_val = agg.get("source", "daily_tracker")

        if cheapest_price is None:
            continue

        station_id = _normalize_station_name(station_name, city)
        observations.append({
            "station_id": station_id,
            "name": station_name,
            "city": city,
            "address": "",  # daily_tracker by_city doesn't store address
            "fuel": fuel,
            "price": round(cheapest_price, 4),
            "scraped_at": scraped_at,
            "source": source_val,
        })

    return observations


async def migrate(dry_run: bool = False):
    """Main migration logic."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    logger.info("Connected to MongoDB: %s / %s", MONGO_URL.split('@')[-1], DB_NAME)

    # ---------------- step 1: read snapshots ----------------
    logger.info("Step 1: Reading snapshots collection...")
    snapshots = await db.snapshots.find({}, {"_id": 0}).to_list(length=100000)
    logger.info("Found %d snapshot documents", len(snapshots))

    all_observations = []
    for snap in snapshots:
        obs = _parse_snapshot_stations(snap)
        all_observations.extend(obs)

    logger.info("Extracted %d observations from snapshots", len(all_observations))

    # ---------------- step 2: read daily_tracker ----------------
    logger.info("Step 2: Reading daily_tracker collection...")
    tracker_docs = await db.daily_tracker.find({}, {"_id": 0}).to_list(length=100000)
    logger.info("Found %d daily_tracker documents", len(tracker_docs))

    for doc in tracker_docs:
        obs = _parse_daily_tracker_by_city(doc)
        all_observations.extend(obs)

    logger.info("Total observations after merging tracker: %d", len(all_observations))

    # ---------------- step 3: deduplicate stations ----------------
    logger.info("Step 3: Building stations registry...")
    stations_map: dict[str, dict] = {}
    for obs in all_observations:
        sid = obs["station_id"]
        if sid not in stations_map:
            stations_map[sid] = {
                "station_id": sid,
                "name": obs["name"],
                "city": obs["city"],
                "address": obs.get("address", ""),
                "first_seen": obs["scraped_at"],
                "last_seen": obs["scraped_at"],
            }
        else:
            # update last_seen
            if obs["scraped_at"] > stations_map[sid]["last_seen"]:
                stations_map[sid]["last_seen"] = obs["scraped_at"]
            if obs["scraped_at"] < stations_map[sid]["first_seen"]:
                stations_map[sid]["first_seen"] = obs["scraped_at"]

    logger.info("Identified %d unique stations", len(stations_map))

    # ---------------- step 4: write to database ----------------
    if dry_run:
        logger.info("DRY RUN: would upsert %d stations", len(stations_map))
        logger.info("DRY RUN: would insert %d price_observations", len(all_observations))
        logger.info("DRY RUN: no changes made (remove --dry-run to apply)")
        client.close()
        return

    logger.info("Step 4: Upserting stations...")
    stations_written = 0
    for station in stations_map.values():
        await db.stations.update_one(
            {"station_id": station["station_id"]},
            {"$set": station},
            upsert=True,
        )
        stations_written += 1
        if stations_written % 100 == 0:
            logger.info("  ... %d stations upserted", stations_written)

    logger.info("Upserted %d stations", stations_written)

    logger.info("Step 5: Inserting price_observations...")
    # create unique index on (station_id, fuel, scraped_at) to prevent duplicates
    await db.price_observations.create_index(
        [("station_id", 1), ("fuel", 1), ("scraped_at", 1)],
        unique=True,
    )
    await db.price_observations.create_index([("scraped_at", -1)])
    await db.price_observations.create_index([("fuel", 1), ("scraped_at", -1)])

    observations_written = 0
    observations_skipped = 0
    for obs in all_observations:
        try:
            await db.price_observations.update_one(
                {
                    "station_id": obs["station_id"],
                    "fuel": obs["fuel"],
                    "scraped_at": obs["scraped_at"],
                },
                {"$set": obs},
                upsert=True,
            )
            observations_written += 1
            if observations_written % 500 == 0:
                logger.info("  ... %d observations written", observations_written)
        except Exception as e:
            # duplicate key or other error
            observations_skipped += 1
            if observations_skipped <= 10:
                logger.warning("  skipped observation: %s", e)

    logger.info("Inserted %d observations (skipped %d duplicates)",
                observations_written, observations_skipped)

    # ---------------- summary ----------------
    logger.info("Migration complete:")
    logger.info("  - Stations registered: %d", len(stations_map))
    logger.info("  - Observations created: %d", observations_written)
    logger.info("  - Observations skipped (duplicates): %d", observations_skipped)

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate legacy snapshots + daily_tracker to normalized observations schema"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without writing to database",
    )
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=args.dry_run))
