# Security Audit Summary - BensaVahti

**Date**: 2026-06-10  
**Status**: Critical vulnerabilities fixed

## Critical Fixes Implemented (HIGH Priority)

### ✅ HIGH-001: NoSQL Injection Prevention
**Issue**: User-controlled parameters (fuel, region) were directly interpolated into MongoDB queries without whitelist validation.

**Fix Applied**:
- Created `security_utils.py` with whitelist validation functions
- Added `validate_fuel()`, `validate_region()`, and `validate_fuel_and_region()` helpers
- Applied validation to ALL API endpoints:
  - `/api/prices/history`
  - `/api/prices/current`
  - `/api/regional`
  - `/api/predict/run`
  - `/api/track/run`
  - `/api/track/history`
  - `/api/track/backfill`
  - `/api/admin/fix-capture`
  - `/api/admin/run`

**Files Modified**: `server.py`, `security_utils.py` (new)

---

### ✅ HIGH-003: Admin Authentication Security
**Issue**: Admin password was transmitted in request body (JSON), visible in logs and proxy history.

**Fix Applied**:
- Removed `password` field from `AdminRequest` body
- Changed authentication to **X-Admin-Token header only**
- Modified `_check_admin()` to return 404 (stealth mode) instead of 503 when token is unset
- Updated error messages to generic "Unauthorized" instead of verbose details
- Updated documentation to reflect header-only authentication

**Files Modified**: `server.py`

**Breaking Change**: Clients must update to use `X-Admin-Token` header instead of body password.

---

### ✅ HIGH-005: Secret Redaction in Error Messages
**Issue**: API error responses could leak authentication tokens, MongoDB credentials, or API keys in logs.

**Fix Applied**:
- Added `redact_secrets()` function in `security_utils.py`
- Wrapped MongoDB client initialization with try/except to prevent credential leakage
- Updated `llm_client.py` to redact secrets from Anthropic API error messages
- Redacts patterns: `api_key`, `token`, `secret`, `authorization`, `password`, `bearer`, MongoDB connection strings

**Files Modified**: `server.py`, `llm_client.py`, `security_utils.py`

---

### ✅ HIGH-006: Rate Limiting on Expensive Operations
**Issue**: No rate limits on endpoints that scrape external sites or make expensive API calls, allowing DoS attacks.

**Fix Applied**:
- Added rate limit to `/api/prices/current`: 20/minute (scrapes 2 sites)
- Added rate limit to `/api/news`: 10/minute (scrapes ~25 RSS feeds)
- Added rate limit to `/api/factors`: 30/minute (Yahoo Finance API calls)
- Existing limits maintained on prediction/tracking endpoints

**Files Modified**: `server.py`

---

### ✅ HIGH-007: SSRF Protection in Scrapers
**Issue**: Scraper functions could be exploited to make requests to internal network if city/URL parameters were ever sourced from user input or database.

**Fix Applied**:
- Added whitelist validation to `tankille._scrape_city()` - validates city against `CITIES` list
- Added alphanumeric-only check for city slug to prevent path traversal
- Added URL validation to `news._fetch_one()` - blocks localhost, 127.0.0.1, ::1, 0.0.0.0
- Added scheme validation (only http/https allowed)

**Files Modified**: `scrapers/tankille.py`, `news.py`

---

### ✅ HIGH: Security Headers Middleware
**Issue**: No security headers configured, exposing app to clickjacking, MIME sniffing, XSS attacks.

**Fix Applied**:
- Created `SecurityHeadersMiddleware` in `server.py`
- Added headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (production only)

**Files Modified**: `server.py`

---

## Medium Priority Fixes Recommended

### MEDIUM: Input Sanitization
**Recommendation**: Sanitize station names, addresses, and city names before storage to prevent XSS.

**Implementation**: Use `sanitize_string()` from `security_utils.py` in tracker capture logic.

**Status**: ⏳ Pending

---

### MEDIUM: Race Condition in Concurrent Captures
**Issue**: Two concurrent `capture_daily()` calls for the same (date, hour, fuel) can race and produce different predictions.

**Recommendation**: Implement optimistic locking with `captured_at` version field or use MongoDB transactions.

**Status**: ⏳ Pending

---

### MEDIUM: Missing Database Indexes
**Issue**: `price_observations` collection lacks indexes, causing slow upserts.

**Recommendation**: Add index on `(date, hour, fuel)` in startup routine.

**Status**: ⏳ Pending

---

### MEDIUM: Database Write Retry Logic
**Issue**: Critical DB writes in `tracker.capture_daily()` have no retry mechanism.

**Recommendation**: Wrap DB operations in retry loop (3 attempts with exponential backoff).

**Status**: ⏳ Pending

---

## Testing Checklist

- [ ] Test NoSQL injection with payload: `?fuel[$ne]=95E10&region[$regex]=.*`
- [ ] Verify admin endpoints reject body password (should return 401)
- [ ] Verify admin endpoints accept X-Admin-Token header
- [ ] Test rate limits by sending 25 requests to `/api/prices/current` (should get 429)
- [ ] Check response headers for X-Frame-Options, X-Content-Type-Options
- [ ] Verify error messages don't leak MongoDB connection string
- [ ] Test SSRF protection by adding `localhost` to CITIES (should be rejected)

---

## Deployment Notes

1. **Railway Environment Variables** - Ensure `ADMIN_TOKEN` is set
2. **Breaking Change**: Update any scripts/tools that use `/api/admin/run` to send `X-Admin-Token` header instead of body password
3. **No frontend changes required** - all fixes are backend-only

---

## Security Posture: Before vs After

| Attack Vector | Before | After |
|---|---|---|
| NoSQL Injection | ❌ Vulnerable | ✅ Protected |
| Admin Auth Interception | ❌ Password in body | ✅ Header-only |
| Secret Leakage | ⚠️ Possible in errors | ✅ Redacted |
| Scraping DoS | ❌ No limits | ✅ Rate limited |
| SSRF via Scrapers | ⚠️ Possible | ✅ Blocked |
| Clickjacking | ❌ No headers | ✅ Protected |
| XSS via Headers | ❌ No headers | ✅ Protected |

---

**Next Steps**: Test in staging, then deploy to production. Monitor logs for rejected requests (may indicate attack attempts or misconfiguration).
