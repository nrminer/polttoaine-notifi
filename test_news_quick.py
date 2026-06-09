"""Quick test to see what news items are being fetched."""
import sys
sys.path.insert(0, 'backend')

from news import fetch_news

items = fetch_news(max_age_days=14, limit=15)
print(f'\n=== Found {len(items)} items ===\n')

for i, item in enumerate(items, 1):
    age = int(item.get('age_hours', 0))
    print(f"{i}. [{item['source']}] ({age}h ago)")
    print(f"   {item['title']}")
    print()

if len(items) == 0:
    print("WARNING: No items found! Checking feeds...")
    from news import FEEDS
    print(f"\nTotal feeds configured: {len(FEEDS)}")
    print("\nFirst 5 feeds:")
    for url, label in FEEDS[:5]:
        print(f"  - {label}: {url}")
