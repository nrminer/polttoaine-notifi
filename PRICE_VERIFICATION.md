# Price Verification Safety System

## Overview

BensaVahti now includes a comprehensive price verification system to prevent ridiculously wrong prices from being stored in the database. This system runs automatically on every capture and can detect:

- Prices outside realistic bounds (1.10 - 3.50 EUR/L)
- Prices that deviate significantly from recent history (>20% deviation)
- Prices with unrealistic day-to-day changes (>0.15 EUR/L per day)
- Cross-fuel inconsistencies (diesel vs 95E10 relationship)

## How It Works

### Automatic Verification (tracker.py)

Every time a scheduled capture runs (14:00 or 21:00 Helsinki), the scraped price is verified before being stored:

1. **Hard Bounds Check**: Price must be between 1.10 and 3.50 EUR/L
2. **Historical Deviation**: Price is compared to the average of the last 10 captures
3. **Daily Change Limit**: Price cannot change more than 0.15 EUR/L from the previous day
4. **Cross-Fuel Check**: Diesel and 95E10 prices must have a reasonable relationship (0-30 cent difference)

### When Verification Fails

If a price fails verification:

1. **Error is logged** with full context (scraped price, station, historical averages)
2. **Suggested alternative** is used if available (from historical context)
3. **Last known good price** is used as fallback
4. **Verification metadata** is stored in the database for audit trail:
   - `verification_override`: true if price was replaced
   - `original_scraped_price`: the original bad price that was scraped
   - `verification_failed`: true if no fallback was available

### Database Fields

Captures now include verification metadata:

```json
{
  "date": "2026-06-06",
  "hour": 14,
  "fuel": "diesel",
  "actual_cheapest": 2.000,
  "verification_override": true,
  "original_scraped_price": 0.543,
  "verification_failed": false
}
```

## Manual Fixes

### Fix a Bad Capture via API

If a bad price slips through or needs manual correction:

```bash
curl -X POST "$BACKEND_URL/api/admin/fix-capture" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-06-06",
    "hour": 14,
    "fuel": "diesel",
    "region": "Suomi",
    "corrected_price": 2.000,
    "reason": "Manual correction: outlier detected"
  }'
```

## Verification Module

The core verification logic lives in `backend/price_verification.py`:

### Key Functions

- `verify_price(price, fuel, db, ...)`: Main verification function, returns `VerificationResult`
- `get_verification_context(db, fuel, region)`: Get historical context for logging

### VerificationResult

```python
class VerificationResult:
    is_valid: bool              # True if price passes all checks
    price: float                # The price being verified
    reason: str                 # Explanation of why it failed/passed
    confidence: str             # "high", "medium", "low"
    suggested_alternative: float | None  # Suggested replacement price
```

## Thresholds & Constants

Can be tuned in `price_verification.py`:

```python
PRICE_MIN_HARD = 1.10           # Minimum realistic price
PRICE_MAX_HARD = 3.50           # Maximum realistic price
MAX_DAILY_CHANGE = 0.15         # Maximum EUR/L change per day
HISTORICAL_DEVIATION_THRESHOLD = 0.20  # 20% deviation from recent avg
DIESEL_PREMIUM_MAX = 0.30       # Max diesel premium over 95E10
```

## Examples

### Valid Price
```
✓ VALID: 1.937 EUR - Price 1.937 EUR/L passed all verification checks
```

### Invalid Price (Hard Bound)
```
⚠️  INVALID: 0.543 EUR - Price 0.543 is below minimum realistic bound 1.10 EUR/L. This is likely a parsing error or stale data.
```

### Invalid Price (Historical Deviation)
```
⚠️  INVALID: 2.500 EUR - Price 2.500 deviates 28.1% from recent 10-day average 1.937 EUR/L (threshold: 20%). Suggested: Use 1.937 EUR/L or verify scrapers.
```

### Invalid Price (Daily Jump)
```
⚠️  INVALID: 2.200 EUR - Price changed 0.263 EUR/L from yesterday (1.937 → 2.200). Maximum reasonable daily change is 0.15 EUR/L. This suggests a scraper error.
```

## Integration Points

The verification system is integrated at:

1. **tracker.py**: `capture_daily()` validates scheduled captures
2. **server.py**: Admin endpoint `/api/admin/fix-capture`
3. **price_verification.py**: Core verification logic

## Monitoring

Check logs for verification warnings:

```
⚠️  PRICE VERIFICATION FAILED for diesel on 2026-06-06 @14h: Price 0.543 is below minimum...
   Scraped price: 0.543 EUR/L
   Station: Shell Helsinki
   Historical context: recent_avg=1.937, last=1.945, count=8
   → Using suggested alternative: 1.937 EUR/L
```

## Future Improvements

Potential enhancements:

1. Machine learning-based anomaly detection
2. Scraper-specific reliability scoring
3. Automatic re-scraping when outliers are detected
4. SMS/email alerts for verification failures
5. Per-city verification (city-level historical averages)
