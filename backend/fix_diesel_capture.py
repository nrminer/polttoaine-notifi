"""Fix ridiculously wrong diesel capture and replace with 2.0 EUR/L."""
import os
import sys
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME', 'bensavahti')
    
    if not mongo_url:
        print("Error: MONGO_URL not set. Please provide it as env var.")
        sys.exit(1)
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Find latest diesel captures
    print("=== Latest 10 diesel captures ===")
    docs = await db.daily_tracker.find(
        {'fuel': 'diesel'},
        {'_id': 0, 'date': 1, 'hour': 1, 'actual_cheapest': 1, 
         'prediction_for_tomorrow_cheapest': 1, 'actual_cheapest_city': 1,
         'actual_cheapest_station': 1}
    ).sort([('date', -1), ('hour', -1)]).limit(10).to_list(10)
    
    for i, d in enumerate(docs, 1):
        date = d.get('date', '?')
        hour = d.get('hour', 0)
        actual = d.get('actual_cheapest')
        pred = d.get('prediction_for_tomorrow_cheapest')
        city = d.get('actual_cheapest_city', '?')
        station = d.get('actual_cheapest_station', '?')
        print(f"{i}. {date} @{hour:02d}h: {actual} EUR in {city}")
        print(f"   Station: {station}")
        print(f"   Predicted: {pred}")
        print()
    
    if not docs:
        print("No diesel captures found.")
        client.close()
        return
    
    # Find the most recent capture
    latest = docs[0]
    latest_price = latest.get('actual_cheapest')
    
    # Check if it's ridiculously wrong (outside 1.50-2.50 range or way off from neighbors)
    is_outlier = False
    if latest_price and (latest_price < 1.50 or latest_price > 2.50):
        is_outlier = True
        print(f"⚠️  OUTLIER DETECTED: {latest_price} EUR is outside normal range [1.50, 2.50]")
    elif latest_price and len(docs) > 1:
        # Check against recent history
        recent_prices = [d.get('actual_cheapest') for d in docs[1:6] 
                        if d.get('actual_cheapest') is not None]
        if recent_prices:
            avg = sum(recent_prices) / len(recent_prices)
            diff_pct = abs(latest_price - avg) / avg
            if diff_pct > 0.15:  # more than 15% deviation
                is_outlier = True
                print(f"⚠️  OUTLIER DETECTED: {latest_price} EUR deviates {diff_pct*100:.1f}% from recent avg {avg:.3f}")
    
    if not is_outlier:
        print("✓ Latest capture looks reasonable. No action needed.")
        client.close()
        return
    
    # Ask for confirmation
    print("\n" + "="*60)
    print(f"REPLACE {latest.get('date')} @{latest.get('hour',0):02d}h diesel capture:")
    print(f"  FROM: {latest_price} EUR")
    print(f"  TO:   2.000 EUR")
    print("="*60)
    
    confirm = input("Proceed? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        client.close()
        return
    
    # Update the document
    result = await db.daily_tracker.update_one(
        {
            'fuel': 'diesel',
            'region': latest.get('region', 'Suomi'),
            'date': latest.get('date'),
            'hour': latest.get('hour', 20)
        },
        {
            '$set': {
                'actual_cheapest': 2.000,
                'fixed_at': datetime.now(timezone.utc).isoformat(),
                'original_price': latest_price,
                'fix_reason': 'Manual correction: outlier price replaced with 2.0 EUR/L'
            }
        }
    )
    
    if result.modified_count > 0:
        print(f"✓ Successfully updated {latest.get('date')} @{latest.get('hour',0):02d}h to 2.000 EUR")
    else:
        print("⚠️  No document was modified. Check the query.")
    
    client.close()

if __name__ == '__main__':
    asyncio.run(main())
