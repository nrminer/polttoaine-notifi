"""Quick script to check latest diesel captures."""
import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    docs = await db.daily_tracker.find(
        {'fuel': 'diesel'},
        {'_id': 0, 'date': 1, 'hour': 1, 'actual_cheapest': 1, 
         'prediction_for_tomorrow_cheapest': 1, 'actual_cheapest_city': 1}
    ).sort([('date', -1), ('hour', -1)]).limit(10).to_list(10)
    
    print("Latest 10 diesel captures:")
    for d in docs:
        date = d.get('date', '?')
        hour = d.get('hour', 0)
        actual = d.get('actual_cheapest')
        pred = d.get('prediction_for_tomorrow_cheapest')
        city = d.get('actual_cheapest_city', '?')
        print(f"{date} @{hour:02d}h: {actual} EUR in {city} (predicted: {pred})")
    
    client.close()

if __name__ == '__main__':
    asyncio.run(main())
