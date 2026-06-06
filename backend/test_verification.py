"""
Test script for price verification system.

Run this to verify the verification logic works correctly before deploying.
"""
import asyncio
from datetime import datetime, timezone
from price_verification import (
    verify_price, 
    VerificationResult,
    PRICE_MIN_HARD,
    PRICE_MAX_HARD,
    MAX_DAILY_CHANGE,
    HISTORICAL_DEVIATION_THRESHOLD
)


class MockDB:
    """Mock database for testing without real MongoDB connection."""
    
    def __init__(self):
        self.daily_tracker_data = [
            {"date": "2026-06-01", "actual_cheapest": 1.920, "fuel": "diesel"},
            {"date": "2026-06-02", "actual_cheapest": 1.925, "fuel": "diesel"},
            {"date": "2026-06-03", "actual_cheapest": 1.930, "fuel": "diesel"},
            {"date": "2026-06-04", "actual_cheapest": 1.935, "fuel": "diesel"},
            {"date": "2026-06-05", "actual_cheapest": 1.940, "fuel": "diesel"},
        ]
    
    class MockCollection:
        def __init__(self, data):
            self.data = data
        
        def find(self, query, projection=None):
            return self
        
        def sort(self, sort_params):
            return self
        
        def limit(self, n):
            return self
        
        async def to_list(self, length):
            return self.data
    
    @property
    def daily_tracker(self):
        return self.MockCollection(self.daily_tracker_data)


async def test_verification():
    """Run test cases for price verification."""
    
    db = MockDB()
    
    print("="*70)
    print("PRICE VERIFICATION SYSTEM TEST")
    print("="*70)
    print()
    
    test_cases = [
        # (price, fuel, expected_valid, description)
        (1.940, "diesel", True, "Normal price within recent range"),
        (0.543, "diesel", False, "Way too low - below minimum bound"),
        (4.500, "diesel", False, "Way too high - above maximum bound"),
        (2.500, "diesel", False, "Too high - deviates >20% from recent avg 1.930"),
        (1.400, "diesel", False, "Too low - deviates >20% from recent avg 1.930"),
        (2.200, "diesel", False, "Daily jump >0.15 EUR/L from yesterday 1.940"),
        (1.950, "diesel", True, "Small increase - within daily change limit"),
    ]
    
    print(f"Hard bounds: {PRICE_MIN_HARD} - {PRICE_MAX_HARD} EUR/L")
    print(f"Max daily change: {MAX_DAILY_CHANGE} EUR/L")
    print(f"Historical deviation threshold: {HISTORICAL_DEVIATION_THRESHOLD*100}%")
    print()
    print(f"Mock historical data (last 5 days):")
    for d in db.daily_tracker_data:
        print(f"  {d['date']}: {d['actual_cheapest']} EUR")
    print()
    
    passed = 0
    failed = 0
    
    for price, fuel, expected_valid, description in test_cases:
        result = await verify_price(price, fuel, db, date_iso="2026-06-06")
        
        status = "[PASS]" if result.is_valid == expected_valid else "[FAIL]"
        if result.is_valid == expected_valid:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | {description}")
        print(f"       Price: {price:.3f} EUR/L")
        print(f"       Expected: {'VALID' if expected_valid else 'INVALID'}")
        print(f"       Got: {'VALID' if result.is_valid else 'INVALID'}")
        if not result.is_valid:
            # Remove special characters that might cause encoding issues
            reason_clean = result.reason.replace('\u2192', '->').replace('\u2713', '[OK]').replace('\u2717', '[X]')
            print(f"       Reason: {reason_clean[:100]}...")
            if result.suggested_alternative:
                print(f"       Suggested: {result.suggested_alternative:.3f} EUR/L")
        print()
    
    print("="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    if failed == 0:
        print("[OK] All tests passed! Verification system is working correctly.")
        return True
    else:
        print("[ERROR] Some tests failed. Review the verification logic.")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_verification())
    exit(0 if success else 1)
