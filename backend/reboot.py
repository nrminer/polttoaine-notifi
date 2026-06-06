"""
Reboot command - clears all collections except graph data and restarts the system.

Also removes any captures AFTER the reboot timestamp (prevents future data from corrupting fresh start).

Usage:
  python reboot.py [--yes]

Without --yes, runs in dry-run mode.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def reboot_system(dry_run=True):
    """Clear all collections except graphify data, remove future captures, and restart."""
    
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME', 'bensavahti')
    
    if not mongo_url:
        print("Error: MONGO_URL not set")
        sys.exit(1)
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Get current timestamp for "reboot time"
    reboot_time = datetime.now(timezone.utc)
    reboot_date = reboot_time.date().isoformat()
    
    # Collections to clear (everything except graphify)
    collections_to_clear = [
        'snapshots',
        'history',
        'predictions',
        'price_observations',
    ]
    
    # Collections to preserve (graph data)
    preserved_collections = [
        'graph_nodes',
        'graph_edges',
        'graph_metadata',
    ]
    
    print("="*70)
    print("REBOOT SYSTEM")
    print("="*70)
    print()
    print(f"Reboot timestamp: {reboot_time.isoformat()}")
    print(f"Reboot date: {reboot_date}")
    print()
    
    if dry_run:
        print("[DRY RUN MODE - No changes will be made]")
        print()
    
    print("Collections to CLEAR:")
    total_docs = 0
    for coll_name in collections_to_clear:
        count = await db[coll_name].count_documents({})
        total_docs += count
        print(f"  - {coll_name}: {count} documents")
    
    # Check for future captures (after reboot date)
    future_captures = await db.daily_tracker.count_documents({"date": {"$gt": reboot_date}})
    print(f"  - daily_tracker (ALL): {await db.daily_tracker.count_documents({})}")
    print(f"    -> Captures AFTER {reboot_date}: {future_captures} (will be removed)")
    print(f"    -> Captures UP TO {reboot_date}: {await db.daily_tracker.count_documents({'date': {'$lte': reboot_date}})} (will be kept)")
    
    print()
    print("Collections to PRESERVE (graph data):")
    for coll_name in preserved_collections:
        count = await db[coll_name].count_documents({})
        print(f"  - {coll_name}: {count} documents (KEPT)")
    
    print()
    print(f"Total documents to delete: {total_docs + future_captures}")
    print()
    
    if dry_run:
        print("Run with --yes to actually clear the data")
        client.close()
        return
    
    # Confirm
    print("="*70)
    print("WARNING: This will:")
    print("  1. Delete all data except graph collections")
    print("  2. Remove all captures AFTER the reboot date")
    print("  3. Keep captures up to and including the reboot date")
    print("="*70)
    confirm = input("Type 'REBOOT' to confirm: ").strip()
    
    if confirm != 'REBOOT':
        print("Aborted.")
        client.close()
        return
    
    print()
    print("Clearing collections...")
    
    cleared_counts = {}
    for coll_name in collections_to_clear:
        result = await db[coll_name].delete_many({})
        cleared_counts[coll_name] = result.deleted_count
        print(f"  - Cleared {coll_name}: {result.deleted_count} documents")
    
    # Remove future captures from daily_tracker
    print()
    print(f"Removing captures after {reboot_date}...")
    future_result = await db.daily_tracker.delete_many({"date": {"$gt": reboot_date}})
    cleared_counts['daily_tracker_future'] = future_result.deleted_count
    print(f"  - Removed {future_result.deleted_count} future captures")
    
    # Count remaining captures
    remaining_captures = await db.daily_tracker.count_documents({})
    print(f"  - Remaining captures: {remaining_captures}")
    
    print()
    print("="*70)
    print("REBOOT COMPLETE")
    print("="*70)
    print()
    print("Summary:")
    print(f"  Total cleared: {sum(cleared_counts.values())} documents")
    print(f"  Remaining captures: {remaining_captures} (up to {reboot_date})")
    print(f"  Reboot timestamp: {reboot_time.isoformat()}")
    print()
    print("Next steps:")
    print("  1. Restart Railway backend (it will recreate indexes)")
    print("  2. Predictions will recalculate from remaining captures")
    print("  3. Wait for next scheduled capture (14:00 or 21:00 Helsinki)")
    print("  4. Or trigger manual capture via /api/track/run-all")
    print()
    print("Graph data preserved - no need to rebuild graphify")
    
    client.close()


if __name__ == '__main__':
    dry_run = '--yes' not in sys.argv
    asyncio.run(reboot_system(dry_run))
