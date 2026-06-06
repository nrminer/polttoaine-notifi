# Code Cleanup Report - 2026-06-06

## Dead Code / Unused Files Analysis

### Files to KEEP (Active/Experimental/Utilities)

#### Core Production Files (KEEP)
- ✅ `server.py` - Main API server
- ✅ `predict.py` - Prediction engine (5 methods + ensemble)
- ✅ `tracker.py` - Scheduled capture system
- ✅ `notify.py` - ntfy.sh notifications
- ✅ `factors.py` - Brent/EUR-USD/refined products
- ✅ `news.py` - RSS aggregator
- ✅ `price_verification.py` - Price validation system
- ✅ `tax_events.py` - Tax change detection
- ✅ `weekly_cycle.py` - Weekly price pattern detection

#### Scrapers (KEEP)
- ✅ `scrapers/polttoaine.py` - Active (secondary source)
- ✅ `scrapers/tankille.py` - Active (primary source)
- ✅ `scrapers/hintatutka.py` - Experimental (opt-in via `ENABLE_HINTATUTKA_EXPERIMENTAL`)

#### Utility Scripts (KEEP)
- ✅ `capture_now.py` - Manual capture tool
- ✅ `purge_captures.py` - Cleanup utility
- ✅ `fix_diesel_via_api.py` - Manual fix helper
- ✅ `check_captures.py` - Debugging tool
- ✅ `reboot.py` - System reset utility

#### Migration Scripts (KEEP - for historical data migration)
- ✅ `migrate_observations.py` - Schema migration utility
- ✅ `migrate_to_observations.py` - Legacy data converter

#### Experimental/Future Features (KEEP)
- ✅ `traffic.py` - **Status: Not integrated, but documented as experimental**
- ✅ `weather.py` - **Status: Not integrated, but documented as experimental**
- ✅ `learn.py` - Learning/calibration system

#### Test Files (KEEP)
- ✅ `test_verification.py` - Price verification tests

---

## Files to REMOVE (Truly Dead Code)

### 🗑️ None Found
All files serve a purpose:
- Production code is actively used
- Experimental code is clearly marked and may be activated
- Migration scripts needed for data transitions
- Utility scripts useful for operations

---

## Code Quality Issues Found

### 1. Unused Imports in server.py
**Location**: `backend/server.py`
**Issue**: Some imports may not be used after code evolution

Let me check for unused imports...

### 2. Duplicate Logic - Scraper Sanity Filters
**Location**: `server.py` and `notify.py`
**Issue**: Both have similar `_sanity_filter()` functions

**Current**:
- `server.py:110-130` - IQR-based outlier detection
- `notify.py` has similar price filtering logic

**Recommendation**: Extract to shared utility module `scrapers/validation.py`

### 3. Inconsistent Error Handling
**Location**: Multiple files
**Issue**: Mix of `logger.warning()`, `logger.exception()`, and silent failures

**Examples**:
- `server.py:182` - warning on hintatutka import failure
- `tracker.py:493` - exception on capture failure
- Some scrapers return empty list on failure without logging

**Recommendation**: Standardize error handling pattern:
```python
# For expected/recoverable errors
logger.warning("Operation failed (expected): %s", e)
# For unexpected errors that should be investigated
logger.exception("Unexpected error in operation: %s", e)
```

### 4. Magic Numbers / Hardcoded Constants
**Location**: Multiple files
**Issue**: Some constants defined inline rather than at module level

**Examples**:
- `server.py:318` - cache max_age 300s (5 minutes)
- `server.py:788` - length=400 for tracker rows
- Various timeout values scattered across scrapers

**Recommendation**: Define at module level with comments explaining rationale

### 5. Inconsistent Date Handling
**Location**: Multiple files
**Issue**: Mix of `datetime.utcnow()` (deprecated) and `datetime.now(timezone.utc)`

**Status**: Mostly fixed, but should audit all files

### 6. Missing Type Hints
**Location**: Some utility functions
**Issue**: Not all functions have complete type hints

**Examples** (from quick scan):
- Some helper functions in `factors.py`
- Some scraper parsing functions

**Recommendation**: Add type hints for better IDE support and error detection

---

## Duplicate Code / Consolidation Opportunities

### 1. Scraper Result Validation (HIGH PRIORITY)
**Locations**: `server.py`, `notify.py`, potentially others
**Duplication**: Both implement price sanity checking

**Proposed Refactor**:
```python
# scrapers/validation.py
def validate_scraped_prices(
    rows: list[dict],
    source: str,
    min_price: float = 1.10,
    max_price: float = 3.50,
    outlier_threshold: float = 0.25
) -> list[dict]:
    """Validate and filter scraped price data."""
    # Consolidated logic here
    pass
```

### 2. Database Query Patterns
**Issue**: Similar query patterns repeated

**Example** - Finding latest capture:
```python
# Pattern appears in multiple places
await db.daily_tracker.find(
    {"fuel": fuel, "region": region},
    {"_id": 0, ...}
).sort([("date", -1), ("hour", -1)]).limit(1)
```

**Recommendation**: Create database query helper module

### 3. Price Formatting
**Locations**: Frontend and some backend logging
**Issue**: Price formatting logic duplicated

**Recommendation**: Already mostly handled by `frontend/src/lib/utils.js:fmtPrice()`

---

## Security Cleanup Issues

### 1. Remove `from __future__ import annotations` Where Not Needed
**Location**: `traffic.py:21`, `weather.py:27`
**Issue**: Python 3.11 doesn't need this, and it can cause Pydantic issues
**Action**: Remove from all files (already fixed in server.py)

### 2. Unused Environment Variables
**Status**: Need to audit which env vars are actually used vs documented

---

## Documentation Issues

### 1. Outdated Comments
**Example**: Some files reference old data sources (Tilastokeskus) that were removed

**Action**: Audit comments for accuracy

### 2. Missing Docstrings
**Issue**: Some helper functions lack docstrings

**Example**: Various `_parse_*` functions in scrapers

---

## Performance Issues

### 1. Inefficient Date Parsing
**Location**: `predict.py:_parse_date()`
**Issue**: Uses `strptime` repeatedly in tight loops

**Current**:
```python
def _parse_date(s: str):
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
```

**Recommendation**: Cache or use ISO 8601 parser for better performance

### 2. No Connection Pooling Limits
**Location**: MongoDB Motor client
**Issue**: No explicit connection pool size limits

**Recommendation**: Set reasonable limits in production

---

## Cleanup Action Plan

### Immediate (Do Now)
1. ✅ Add rate limiting to admin endpoints (DONE)
2. ✅ Add price validation to backfill (DONE)
3. ✅ Reject CORS wildcard in production (DONE)
4. Remove `from __future__ import annotations` from traffic.py and weather.py
5. Check for unused imports

### Short Term (This Week)
6. Consolidate scraper validation logic
7. Standardize error handling patterns
8. Extract magic numbers to named constants
9. Add missing type hints to key functions

### Medium Term (Next Sprint)
10. Create database query helper module
11. Add comprehensive logging audit
12. Performance profiling of hot paths
13. Add more inline documentation

---

## Files That Look Messy But Are Actually Fine

### `server.py` (1645 lines)
**Verdict**: ACCEPTABLE
- Large file but serves as single API surface
- Well-organized into sections
- Breaking it up would add complexity
- Recommendation: Add more section comments

### `predict.py` (1242 lines)
**Verdict**: ACCEPTABLE
- Contains 5+ prediction methods + ensemble
- Each method is self-contained
- Breaking up would obscure the prediction flow
- Recommendation: None needed

---

## Overall Cleanliness Grade: B+ (Good)

**Strengths**:
- No dead code (all files serve purpose)
- Good separation of concerns
- Well-documented experimental features
- Reasonable file sizes

**Weaknesses**:
- Some code duplication (scraper validation)
- Inconsistent error handling
- Magic numbers not all named
- Missing some type hints

**Priority**: Focus on security fixes (completed) and consolidating scraper validation logic
