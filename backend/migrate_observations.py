#!/usr/bin/env python3
"""
migrate_observations.py — Backfill price_observations and stations from legacy data

This script reads existing `snapshots` and `daily_tracker` collections and migrates
them into the new unified schema:
- `price_observations`: per-station price measurements with scraped_at timestamps
- `stations`: deduplicated station registry with metadata

USAGE:
    # Dry-run (no writes, shows what would happen)
    python migrate_observations.py --dry-run

    # Execute migration
    python migrate_observations.py

    # Clear target collections first, then migrate
    python migrate_observations.py --clear

    # Migrate only specific fuel type
    python migrate_observations.py --fuel 95E10

REQUIREMENTS:
    - .env file with MONGO_URL and DB_NAME
    - Motor async MongoDB client
    - Existing snapshots and/or daily_tracker collections

STRATEGY:
    1. Read all snapshots (cheapest samples per city)
    2. Read all daily_tracker rows (per-city captures)
    3. Deduplicate stations by (name, city, address) → stations collection
    4. Transform each price point → price_observations with synthetic scraped_at
    5. Synthetic scraped_at:
       - snapshots: use snapshot.ts as scraped_at
       - daily_tracker: construct datetime(date, hour, 0, 0, tzinfo=Helsinki)

OUTPUT:
    - price_observations: {station_id, fuel, price_eur, scraped_at, source}
    - stations: {name, city, address, first_seen, last_seen, source}

AUTHOR: AI agent, 2026-06-05
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
    HELSINKI_TZ = ZoneInfo("Europe/Helsinki")
except (ImportError, Exception):
    # Fallback for Windows without tzdata: use fixed UTC+2/UTC+3 offset
    # This is approximate; real Helsinki timezone has DST transitions
    import pytz
    HELSINKI_TZ = pytz.timezone("Europe/Helsinki")
FUELS = ("95E10", "Diesel")
REGIONS = ("Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti", "Suomi")

# Station identity is (name, city, address)
StationKey = Tuple[str, str, str]


class MigrationStats:
    """Track migration progress and results."""

    def __init__(self):
        self.snapshots_read = 0
        self.tracker_read = 0
        self.stations_created = 0
        self.observations_created = 0
        self.skipped_invalid = 0
        self.errors: List[str] = []
        self.station_registry: Dict[StationKey, str] = {}  # key → station_id

    def report(self):
        """Print migration summary."""
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"Snapshots read:          {self.snapshots_read:>8}")
        print(f"Tracker rows read:       {self.tracker_read:>8}")
        print(f"Stations created:        {self.stations_created:>8}")
        print(f"Observations created:    {self.observations_created:>8}")
        print(f"Skipped (invalid):       {self.skipped_invalid:>8}")

        if self.errors:
            print(f"\nERRORS ({len(self.errors)}):")
            for err in self.errors[:10]:  # Show first 10
                print(f"  - {err}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more")
        else:
            print("\n✓ No errors")
        print("=" * 70)


async def migrate_observations(
    dry_run: bool = True,
    clear: bool = False,
    fuel_filter: Optional[str] = None
) -> MigrationStats:
    """
    Main migration logic.

    Args:
        dry_run: If True, read data but don't write to DB
        clear: If True, drop target collections before migrating
        fuel_filter: If set, only migrate this fuel type

    Returns:
        MigrationStats with results
    """
    load_dotenv()

    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "bensavahti")

    if not mongo_url:
        print("ERROR: MONGO_URL not set in environment", file=sys.stderr)
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    stats = MigrationStats()

    try:
        print(f"Connected to MongoDB: {db_name}")
        print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
        if fuel_filter:
            print(f"Fuel filter: {fuel_filter}")
        if clear and not dry_run:
            print("WARNING: --clear will drop target collections")
        print()

        # Clear target collections if requested
        if clear and not dry_run:
            print("Dropping target collections...")
            await db.price_observations.drop()
            await db.stations.drop()
            print("✓ Collections dropped")

        # Station registry: key → station document
        station_docs: Dict[StationKey, dict] = {}

        # Observations to insert
        observations: List[dict] = []

        # --- Phase 1: Process snapshots ---
        print("\n[1/3] Reading snapshots...")

        query = {}
        if fuel_filter:
            query["fuel"] = fuel_filter

        async for snap in db.snapshots.find(query):
            stats.snapshots_read += 1
            fuel = snap.get("fuel")
            ts = snap.get("ts")  # datetime with tzinfo
            by_city = snap.get("by_city", {})

            if not fuel or not ts:
                stats.skipped_invalid += 1
                continue

            # Convert ts to Helsinki timezone if needed
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc).astimezone(HELSINKI_TZ)
            else:
                ts = ts.astimezone(HELSINKI_TZ)

            # Process each city's cheapest sample
            for city, city_data in by_city.items():
                if not isinstance(city_data, dict):
                    continue

                station_name = city_data.get("station", "").strip()
                address = city_data.get("address", "").strip()
                price = city_data.get("price")
                source = city_data.get("source", "unknown")

                if not station_name or price is None:
                    stats.skipped_invalid += 1
                    continue

                # Sanity check price
                if not (1.0 <= price <= 4.0):
                    stats.skipped_invalid += 1
                    stats.errors.append(
                        f"Invalid price {price} for {station_name} in {city}"
                    )
                    continue

                # Build station key
                station_key = (station_name, city, address)

                # Register station
                if station_key not in station_docs:
                    station_docs[station_key] = {
                        "name": station_name,
                        "city": city,
                        "address": address,
                        "first_seen": ts,
                        "last_seen": ts,
                        "source": source,
                        "observation_count": 0
                    }
                else:
                    # Update last_seen
                    if ts > station_docs[station_key]["last_seen"]:
                        station_docs[station_key]["last_seen"] = ts
                    if ts < station_docs[station_key]["first_seen"]:
                        station_docs[station_key]["first_seen"] = ts

                station_docs[station_key]["observation_count"] += 1

                # Create observation (station_id assigned later)
                observations.append({
                    "_station_key": station_key,
                    "fuel": fuel,
                    "price_eur": round(price, 4),
                    "scraped_at": ts,
                    "source": source
                })

        print(f"  ✓ Processed {stats.snapshots_read} snapshots")

        # --- Phase 2: Process daily_tracker ---
        print("\n[2/3] Reading daily_tracker...")

        query = {}
        if fuel_filter:
            query["fuel"] = fuel_filter

        async for tracker in db.daily_tracker.find(query):
            stats.tracker_read += 1
            fuel = tracker.get("fuel")
            date = tracker.get("date")  # YYYY-MM-DD string
            hour = tracker.get("hour", 14)  # default to 14
            by_city = tracker.get("by_city", {})

            if not fuel or not date:
                stats.skipped_invalid += 1
                continue

            # Construct scraped_at from date + hour
            try:
                year, month, day = map(int, date.split("-"))
                scraped_at = datetime(year, month, day, hour, 0, 0, tzinfo=HELSINKI_TZ)
            except Exception as e:
                stats.skipped_invalid += 1
                stats.errors.append(f"Invalid date '{date}': {e}")
                continue

            # Process each city
            for city, city_data in by_city.items():
                if not isinstance(city_data, dict):
                    continue

                # Extract cheapest
                station_name = city_data.get("station", "").strip()
                address = city_data.get("address", "").strip()
                price = city_data.get("cheapest")
                source = city_data.get("source", "scraped")

                if not station_name or price is None:
                    stats.skipped_invalid += 1
                    continue

                # Sanity check
                if not (1.0 <= price <= 4.0):
                    stats.skipped_invalid += 1
                    stats.errors.append(
                        f"Invalid price {price} for {station_name} in {city} on {date}"
                    )
                    continue

                station_key = (station_name, city, address)

                # Register station
                if station_key not in station_docs:
                    station_docs[station_key] = {
                        "name": station_name,
                        "city": city,
                        "address": address,
                        "first_seen": scraped_at,
                        "last_seen": scraped_at,
                        "source": source,
                        "observation_count": 0
                    }
                else:
                    if scraped_at > station_docs[station_key]["last_seen"]:
                        station_docs[station_key]["last_seen"] = scraped_at
                    if scraped_at < station_docs[station_key]["first_seen"]:
                        station_docs[station_key]["first_seen"] = scraped_at

                station_docs[station_key]["observation_count"] += 1

                # Create observation
                observations.append({
                    "_station_key": station_key,
                    "fuel": fuel,
                    "price_eur": round(price, 4),
                    "scraped_at": scraped_at,
                    "source": source
                })

        print(f"  ✓ Processed {stats.tracker_read} tracker rows")

        # --- Phase 3: Write to database ---
        print("\n[3/3] Writing to database...")

        if dry_run:
            print("  [DRY-RUN] Would create:")
            print(f"    - {len(station_docs)} stations")
            print(f"    - {len(observations)} observations")
        else:
            # Insert stations first and build key → station_id mapping
            if station_docs:
                station_list = []
                for key, doc in station_docs.items():
                    station_list.append(doc)

                result = await db.stations.insert_many(station_list, ordered=False)
                stats.stations_created = len(result.inserted_ids)

                # Build mapping: station_key → ObjectId
                inserted_stations = await db.stations.find(
                    {},
                    {"_id": 1, "name": 1, "city": 1, "address": 1}
                ).to_list(length=None)

                for station in inserted_stations:
                    key = (station["name"], station["city"], station["address"])
                    stats.station_registry[key] = str(station["_id"])

                print(f"  ✓ Created {stats.stations_created} stations")

            # Insert observations with station_id
            if observations:
                obs_to_insert = []
                for obs in observations:
                    station_key = obs.pop("_station_key")
                    station_id = stats.station_registry.get(station_key)

                    if not station_id:
                        stats.errors.append(
                            f"Station not found for key {station_key}"
                        )
                        stats.skipped_invalid += 1
                        continue

                    obs["station_id"] = station_id
                    obs_to_insert.append(obs)

                if obs_to_insert:
                    # Insert in batches to avoid memory issues
                    batch_size = 5000
                    for i in range(0, len(obs_to_insert), batch_size):
                        batch = obs_to_insert[i:i + batch_size]
                        await db.price_observations.insert_many(batch, ordered=False)
                        stats.observations_created += len(batch)
                        print(f"    Inserted batch {i//batch_size + 1} "
                              f"({len(batch)} observations)")

                print(f"  ✓ Created {stats.observations_created} observations")

            # Create indexes
            print("\n  Creating indexes...")
            await db.stations.create_index(
                [("name", 1), ("city", 1), ("address", 1)],
                unique=True,
                name="station_identity"
            )
            await db.price_observations.create_index(
                [("station_id", 1), ("fuel", 1), ("scraped_at", -1)],
                name="station_fuel_time"
            )
            await db.price_observations.create_index(
                [("fuel", 1), ("scraped_at", -1)],
                name="fuel_time"
            )
            print("  ✓ Indexes created")

        return stats

    finally:
        client.close()


async def main():
    """Parse args and run migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate legacy data to price_observations + stations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read data but don't write to database"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Drop target collections before migrating (DESTRUCTIVE)"
    )
    parser.add_argument(
        "--fuel",
        choices=FUELS,
        help="Only migrate this fuel type"
    )

    args = parser.parse_args()

    # Safety check for --clear
    if args.clear and not args.dry_run:
        print("WARNING: --clear will DELETE all data in price_observations and stations")
        print("Type 'yes' to continue: ", end="")
        confirm = input().strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    stats = await migrate_observations(
        dry_run=args.dry_run,
        clear=args.clear,
        fuel_filter=args.fuel
    )

    stats.report()

    if args.dry_run:
        print("\n→ Run without --dry-run to execute migration")


if __name__ == "__main__":
    asyncio.run(main())
