"""Quick script to fix the bad June 21 21:00 capture."""
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def fix_capture():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("DB_NAME", "bensavahti")]
    
    # Find the bad capture
    existing = await db.daily_tracker.find_one({
        "date": "2026-06-21",
        "hour": 21,
        "fuel": "95E10",
        "region": "Suomi"
    })
    
    if not existing:
        print("Capture not found!")
        return
    
    print(f"Found capture: {existing.get('actual_cheapest')} EUR")
    print(f"Station: {existing.get('actual_cheapest_station')}")
    
    # Update with corrected price
    result = await db.daily_tracker.update_one(
        {
            "date": "2026-06-21",
            "hour": 21,
            "fuel": "95E10",
            "region": "Suomi"
        },
        {
            "$set": {
                "actual_cheapest": 1.878,
                "actual_cheapest_city": "Nurmijärvi",
                "actual_cheapest_station": "Neste Oil Express",
                "fixed_at": datetime.now(timezone.utc).isoformat(),
                "original_scraped_price": existing.get("actual_cheapest"),
                "fix_reason": "Bad scrape (1.444) - corrected to national minimum trend",
                "manually_corrected": True
            }
        }
    )
    
    print(f"Updated: {result.modified_count} document(s)")
    print("Fixed price: 1.878 EUR (Nurmijärvi - Neste Oil Express)")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_capture())
