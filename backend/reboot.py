"""
Reboot command - clears all collections except graph data and restarts the system.

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
    """Clear all collections except graphify data and restart."""
    
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME', 'bensavahti')
    
    if not mongo_url:
        print("Error: MONGO_URL not set")
        sys.exit(1)
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Collections to clear (everything except graphify)
    collections_to_clear = [
        'snapshots',
        'history',
        'daily_tracker',
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
    
    if dry_run:
        print("[DRY RUN MODE - No changes will be made]")
        print()
    
    print("Collections to CLEAR:")
    total_docs = 0
    for coll_name in collections_to_clear:
        count = await db[coll_name].count_documents({})
        total_docs += count
        print(f"  - {coll_name}: {count} documents")
    
    print()
    print("Collections to PRESERVE (graph data):")
    for coll_name in preserved_collections:
        count = await db[coll_name].count_documents({})
        print(f"  - {coll_name}: {count} documents (KEPT)")
    
    print()
    print(f"Total documents to delete: {total_docs}")
    print()
    
    if dry_run:
        print("Run with --yes to actually clear the data")
        client.close()
        return
    
    # Confirm
    print("="*70)
    print("WARNING: This will delete all data except graph collections!")
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
    
    print()
    print("="*70)
    print("REBOOT COMPLETE")
    print("="*70)
    print()
    print("Summary:")
    print(f"  Total cleared: {sum(cleared_counts.values())} documents")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()
    print("Next steps:")
    print("  1. Restart Railway backend (it will recreate indexes)")
    print("  2. Wait for next scheduled capture (14:00 or 21:00 Helsinki)")
    print("  3. Or trigger manual capture via /api/track/run-all")
    print()
    print("Graph data preserved - no need to rebuild graphify")
    
    client.close()


if __name__ == '__main__':
    dry_run = '--yes' not in sys.argv
    asyncio.run(reboot_system(dry_run))
