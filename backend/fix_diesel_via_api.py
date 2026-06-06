#!/usr/bin/env python3
"""
Fix bad diesel capture via Railway API.

Usage:
  python fix_diesel_via_api.py <BACKEND_URL> <ADMIN_TOKEN> <date> <hour> <corrected_price>

Example:
  python fix_diesel_via_api.py https://polttoaine-notifi-production.up.railway.app mysecret123 2026-06-06 14 2.000
"""
import sys
import requests

def main():
    if len(sys.argv) < 6:
        print("Usage: python fix_diesel_via_api.py <BACKEND_URL> <ADMIN_TOKEN> <date> <hour> <corrected_price>")
        print("Example: python fix_diesel_via_api.py https://backend.railway.app secret 2026-06-06 14 2.000")
        sys.exit(1)
    
    backend_url = sys.argv[1].rstrip('/')
    admin_token = sys.argv[2]
    date = sys.argv[3]
    hour = int(sys.argv[4])
    corrected_price = float(sys.argv[5])
    
    # First, check the latest diesel captures
    print(f"Fetching latest diesel captures from {backend_url}...")
    try:
        resp = requests.get(f"{backend_url}/api/track/history?fuel=diesel&days=10", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows", [])
        
        print(f"\nLatest 5 diesel captures:")
        for i, row in enumerate(rows[-5:], 1):
            d = row.get("date")
            h = row.get("hour", 0)
            price = row.get("actual_cheapest")
            city = row.get("actual_cheapest_city", "?")
            print(f"  {i}. {d} @{h:02d}h: {price} EUR in {city}")
        
        print(f"\nSummary: {data.get('summary', {})}")
    except Exception as e:
        print(f"Error fetching history: {e}")
    
    # Confirm the fix
    print(f"\n{'='*60}")
    print(f"FIX DIESEL CAPTURE:")
    print(f"  Date: {date}")
    print(f"  Hour: {hour:02d}h")
    print(f"  New Price: {corrected_price} EUR")
    print(f"{'='*60}")
    confirm = input("Proceed? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Aborted.")
        sys.exit(0)
    
    # Send the fix request
    print(f"\nSending fix request to {backend_url}/api/admin/fix-capture...")
    try:
        resp = requests.post(
            f"{backend_url}/api/admin/fix-capture",
            headers={
                "X-Admin-Token": admin_token,
                "Content-Type": "application/json"
            },
            json={
                "date": date,
                "hour": hour,
                "fuel": "diesel",
                "region": "Suomi",
                "corrected_price": corrected_price,
                "reason": "Manual correction: outlier price replaced"
            },
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("ok"):
            print(f"\n✓ Successfully fixed diesel capture!")
            print(f"  Original price: {result.get('original_price')} EUR")
            print(f"  Corrected price: {result.get('corrected_price')} EUR")
        else:
            print(f"\n⚠️  Fix failed: {result}")
    
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        print(f"Response: {e.response.text if e.response else 'N/A'}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    main()
