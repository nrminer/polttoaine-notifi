# Scraping Cadence Configuration

BensaVahti now supports **two parallel scraping modes** to build a richer dataset for prediction calibration:

1. **Scheduled captures** (14:00 + 21:00 Helsinki) — full capture + prediction + notification
2. **Silent scrapes** (configurable hours) — price observation only, no notifications

This document covers configuration, deployment, resource impact, and monitoring.

---

## 1. Environment Variables

### `SILENT_SCRAPE_HOURS`

**Purpose**: Comma-separated list of hours (Helsinki time, 0–23) when silent scrapes run.

**Default**: `"6,8,10,12,16,18,20,22"` (8 scrapes/day)

**Format**: String, integers separated by commas (no spaces).

**Examples**:
```bash
# Default: 8 scrapes/day
SILENT_SCRAPE_HOURS="6,8,10,12,16,18,20,22"

# Minimal: hourly business hours
SILENT_SCRAPE_HOURS="9,10,11,12,13,14,15,16,17"

# Aggressive: every 2 hours
SILENT_SCRAPE_HOURS="0,2,4,6,8,10,12,14,16,18,20,22"

# Disabled: empty string (only scheduled captures run)
SILENT_SCRAPE_HOURS=""
```

**Where to set**:
- **Railway**: Project → Service → Variables tab → Add `SILENT_SCRAPE_HOURS`
- **Local dev**: `backend/.env` file

---

### `SCHEDULED_HOURS` (hardcoded in code)

**Purpose**: Hours when full captures run (scrape + prediction + notification).

**Current value**: `(14, 21)` — hardcoded in `backend/tracker.py`

**Not configurable** via environment variable (by design — these are the canonical "truth" timestamps for prediction evaluation).

---

### Interaction Between the Two

| Hour | In `SCHEDULED_HOURS`? | In `SILENT_SCRAPE_HOURS`? | Behavior |
|------|----------------------|---------------------------|----------|
| 14   | ✅ yes               | ❌ no                     | Full capture (prediction + ntfy) |
| 21   | ✅ yes               | ❌ no                     | Full capture (prediction + ntfy) |
| 10   | ❌ no                | ✅ yes                    | Silent scrape (price_observations only) |
| 14   | ✅ yes               | ✅ yes (overlap)          | **Full capture wins** — silent scrape skipped for this hour |

**Rule**: If an hour appears in both sets, the scheduled capture (with notification) takes precedence. The silent scrape loop detects this and skips that hour to avoid duplicate work.

---

## 2. Railway Deployment

### Add the Environment Variable

1. Open your Railway project → backend service → **Variables** tab.
2. Click **+ New Variable**.
3. Key: `SILENT_SCRAPE_HOURS`
4. Value: `6,8,10,12,16,18,20,22` (or your preferred schedule).
5. **Save** → Railway auto-redeploys (takes ~2 minutes).

### Verify It's Running

After deploy:
```bash
# Check Railway logs
# You should see:
# "silent scrape scheduler started (8 hours: 06:00, 08:00, ...)"

curl https://<your-railway-url>/api/admin/run \
  -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_TOKEN>","action":"ping"}'
# Response should confirm silent scrape is active
```

### Environment Variable Summary (Complete List)

| Variable                | Required | Notes |
|-------------------------|----------|-------|
| `MONGO_URL`             | ✅ yes   | MongoDB Atlas connection string |
| `DB_NAME`               | ✅ yes   | `bensavahti` |
| `EMERGENT_LLM_KEY`      | ✅ yes   | AI predictions require this |
| `PIP_EXTRA_INDEX_URL`   | ✅ yes   | `https://d33sy5i8bnduwe.cloudfront.net/simple/` |
| `ADMIN_TOKEN`           | optional | Enables `/api/admin/run` (unset → 503) |
| `NTFY_TOPIC`            | optional | `polttoaine` (notifications silently no-op without it) |
| `NTFY_TOKEN`            | optional | Bearer token for ntfy.sh |
| `NEWS_WATCH_SECONDS`    | optional | News-watcher poll interval (default 1800; 0 = disabled) |
| `SILENT_SCRAPE_HOURS`   | optional | **NEW** — Default `6,8,10,12,16,18,20,22` |
| `CORS_ORIGINS`          | optional | Default `https://polttoaine-notifi.vercel.app` |

---

## 3. Resource Impact Estimate

### Scrape Count

| Mode | Before (2/day) | After (default 8 silent + 2 scheduled) | Multiplier |
|------|----------------|----------------------------------------|------------|
| Total scrapes/day | 2 | 10 | **5×** |

### MongoDB Storage

**Collection: `price_observations`**

- **Row size**: ~300 bytes/observation (fuel, region, timestamp, price, station, city, source)
- **Rows per scrape**: ~50–100 stations × 2 fuels = **100–200 rows**
- **Daily growth**: 10 scrapes × 150 rows = **1,500 rows/day** (~450 KB/day)
- **Monthly growth**: ~45,000 rows (~13.5 MB/month)
- **Annual growth**: ~550,000 rows (~165 MB/year)

**Atlas free M0 tier** (512 MB storage) can handle **~3 years** of silent scrapes before hitting limit.

### Memory Impact

**Railway container memory**:
- Baseline (no silent scrapes): ~150 MB RSS
- Per scrape: +20 MB spike (HTTP requests + parsing), returns to baseline after
- **Concurrent scrapes**: Silent scrape loop and scheduled capture never overlap (by design), so no additive spike

**Estimated steady-state**: 150–180 MB RSS (well within Railway's 512 MB free tier limit).

### Network Requests

**Per scrape** (both fuels):
- `polttoaine.net`: 2 requests (95E10 + diesel top-N pages)
- `tankille.fi`: 12 requests (6 cities × 2 fuels)
- `hintatutka.fi`: 12 requests (6 cities × 2 fuels) — **NEW** third scraper
- **Total**: ~26 HTTP requests/scrape

**Daily total**: 10 scrapes × 26 = **260 requests/day**

**Target site impact**: 260 requests spread across 24 hours = **~11 requests/hour** to external sites (negligible; well below any reasonable rate limit).

### CPU Impact

- Scraping is I/O-bound (HTTP requests), not CPU-bound
- Parsing HTML: <50 ms CPU time per scraper
- **Per scrape**: ~200 ms total CPU time
- **Daily CPU budget**: 10 scrapes × 0.2s = **2 seconds/day** (trivial on Railway)

---

## 4. Monitoring

### Log Messages to Watch

**Startup**:
```
silent scrape scheduler started (8 hours: 06:00, 08:00, 10:00, 12:00, 16:00, 18:00, 20:00, 22:00)
```

**Per silent scrape**:
```
silent scrape: sleeping 1234s until 2026-06-05 10:00 Helsinki
silent scrape completed @10h: 95E10 152 obs, diesel 148 obs
```

**Per scheduled capture** (unchanged):
```
tracker captured 95E10 @14h: actual=1.857 predicted_tomorrow=1.862
```

**Errors to watch**:
```
silent scrape failed for 95E10: <exception>
all scrapers failed for diesel (0 observations)
```

### Key Metrics

| Metric | Where | Healthy Range | Alert Threshold |
|--------|-------|---------------|-----------------|
| **Observations inserted/scrape** | Logs: `"X obs"` | 100–200 per fuel | <50 (scrapers degraded) |
| **Scrape duration** | Logs: timestamp delta | 5–15 seconds | >60s (network issues) |
| **Failure rate** | Count of `"silent scrape failed"` | 0–1/day | >3/day (investigate) |
| **`price_observations` growth** | MongoDB Atlas UI | ~1,500 rows/day | <500/day (silent loop stopped) |
| **Storage usage** | Atlas → Metrics | Linear growth ~13 MB/month | Sudden spike (investigate duplicate inserts) |

### MongoDB Queries for Verification

```javascript
// Count observations per day (should be ~1,500 with default config)
db.price_observations.aggregate([
  { $match: { captured_at: { $gte: new Date("2026-06-05T00:00:00Z") } } },
  { $group: { _id: { $dateToString: { format: "%Y-%m-%d", date: "$captured_at" } }, count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])

// Check for gaps in scrape times (should see hourly clusters at 6,8,10,12,14,16,18,20,21,22)
db.price_observations.aggregate([
  { $match: { fuel: "95E10" } },
  { $group: { _id: { $hour: "$captured_at" }, count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])

// Verify no duplicate inserts (count should equal total rows)
db.price_observations.aggregate([
  { $group: { _id: { fuel: "$fuel", region: "$region", ts: "$captured_at", station: "$station" }, count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }
])
```

### Railway Dashboard

**Metrics to monitor** (Railway → Service → Metrics tab):

- **Memory usage**: Should stay <200 MB RSS
- **CPU usage**: Spikes to ~5% during scrapes, baseline ~1%
- **Network egress**: ~1 MB/scrape × 10 = **10 MB/day** (negligible on free tier)

**Logs to tail** (Railway → Service → Logs tab):
```bash
# Real-time log tail (Railway CLI)
railway logs --tail

# Filter for silent scrape events
railway logs | grep "silent scrape"
```

### Alert Conditions

Set up alerts (via Railway webhooks or external monitoring) for:

1. **All scrapers fail for a fuel** (3 consecutive failures) → indicates scraper breakage (site HTML changed)
2. **`price_observations` not growing** (no new rows in 6 hours) → silent loop crashed
3. **Memory >400 MB sustained** → potential memory leak
4. **HTTP 5xx rate >10%** on `/api/*` → backend degraded

---

## 5. Disabling Silent Scrapes

To disable silent scrapes (fall back to scheduled captures only):

**Option A — Empty string**:
```bash
SILENT_SCRAPE_HOURS=""
```

**Option B — Remove the variable**:
Delete `SILENT_SCRAPE_HOURS` from Railway Variables → defaults to `""` (disabled).

**Verification**:
```bash
# Check Railway logs — you should NOT see:
# "silent scrape scheduler started"
```

---

## 6. Tuning the Schedule

### Conservative (minimize cost/load)

```bash
# 4 scrapes/day (mid-morning, lunch, afternoon, evening)
SILENT_SCRAPE_HOURS="9,12,16,20"
```

### Balanced (default)

```bash
# 8 scrapes/day (every 2–4 hours during waking hours)
SILENT_SCRAPE_HOURS="6,8,10,12,16,18,20,22"
```

### Aggressive (maximum data density)

```bash
# 12 scrapes/day (every 2 hours)
SILENT_SCRAPE_HOURS="0,2,4,6,8,10,12,14,16,18,20,22"
```

**Tradeoff**:
- More scrapes → better intraday price movement data → tighter prediction calibration
- More scrapes → higher MongoDB write load → faster storage growth (still negligible on M0 tier)

**Recommendation**: Start with default (8/day), monitor for 1 week, tune up/down based on observed price volatility patterns.

---

## 7. Common Issues

### Silent scrapes not running

**Symptom**: No `"silent scrape completed"` in logs.

**Causes**:
1. `SILENT_SCRAPE_HOURS=""` (disabled by design)
2. All hours in `SILENT_SCRAPE_HOURS` overlap with `SCHEDULED_HOURS` (14, 21) → skipped
3. Scheduler loop crashed (check logs for exception)

**Fix**:
```bash
# Verify env var is set
railway variables | grep SILENT_SCRAPE_HOURS

# Check logs for startup message
railway logs | grep "silent scrape scheduler"

# Manual test via admin endpoint
curl -X POST https://<railway-url>/api/admin/run \
  -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_TOKEN>","action":"silent_scrape","fuel":"95E10"}'
```

### Duplicate observations

**Symptom**: MongoDB `price_observations` growing faster than expected.

**Cause**: Unique index on `(fuel, region, captured_at, station)` missing → same scrape inserted twice.

**Fix**: Index is created at startup (`server.py:@app.on_event("startup")`). Check logs for index creation confirmation.

### Scraper failures

**Symptom**: `"all scrapers failed for <fuel> (0 observations)"` in logs.

**Causes**:
1. Target sites changed HTML structure → scraper regex/selector broken
2. Network timeout (Railway → target site)
3. Rate limiting (unlikely at 11 requests/hour/site)

**Fix**:
1. Check scraper health manually:
   ```bash
   curl "https://<railway-url>/api/prices/current?fuel=95E10"
   ```
2. If scrapers are broken, update `backend/scrapers/*.py` (check CLAUDE.md § 8 for scraper contract).

---

## 8. Impact on Prediction Accuracy

**Expected improvement** (after 30 days of silent scrapes):

| Metric | Before (2 captures/day) | After (10 observations/day) | Improvement |
|--------|------------------------|-----------------------------|-------------|
| **Data points for MA(7)** | 14 | 70 | 5× denser |
| **Intraday volatility visibility** | None (only 14h + 21h) | 8 samples across day | Morning dips, evening spikes visible |
| **Fundamental anchor calibration** | Brent passthrough uncalibrated (0.25 prior) | Can fit actual lag/passthrough from data | Tighter ±0.06 €/L clamp |
| **Method MAE** (self-calibration) | Evaluated on 2 daily points | Evaluated on 10 daily points | 5× faster convergence |

**Key unlock**: With hourly price snapshots, `learn.py` can fit **actual intraday patterns** (e.g., "prices typically drop 0.5¢ between 6h and 14h on weekdays") → `fundamental_anchor` can incorporate this as a learned prior instead of relying on the current uncalibrated weekday±0.004 €/L guess.

---

## 9. Future: Dynamic Scheduling

**Idea**: Adjust `SILENT_SCRAPE_HOURS` based on observed price volatility.

**Implementation** (not yet built):
1. Track intraday price variance per hour (from `price_observations`)
2. If variance(6h–12h) > threshold → increase morning scrape density
3. If variance(20h–22h) < threshold → reduce evening scrape density

**Config**:
```bash
# Hypothetical future env var
SILENT_SCRAPE_MODE="adaptive"  # vs. "fixed"
SILENT_SCRAPE_MIN_HOURS="6,14,21"  # always scrape these
SILENT_SCRAPE_MAX_HOURS="0,2,4,6,8,10,12,14,16,18,20,22"  # pool to choose from
```

**Effort**: ~200 lines (variance analysis + scheduler reconfig logic). Not prioritized yet — default fixed schedule likely sufficient for v1.

---

## 10. Related Files

| File | Relevant Section |
|------|------------------|
| `backend/tracker.py` | `silent_scrape_loop()` — the scheduler; `_scrape_cheapest()` — scraper orchestration |
| `backend/server.py` | `@app.on_event("startup")` — spawns `silent_scrape_loop` as background task |
| `CLAUDE.md` | § 8 (Scrapers), § 10 (Environment variables) |
| `RAILWAY_DEPLOYMENT.md` | § 3 (Environment variables — add `SILENT_SCRAPE_HOURS` here) |

---

## Summary

**TL;DR**:
- Add `SILENT_SCRAPE_HOURS="6,8,10,12,16,18,20,22"` to Railway env vars for 8 silent scrapes/day (default).
- Scheduled captures (14h + 21h) unchanged — still run full prediction + notification.
- Resource impact: 5× more scrapes, ~13 MB/month MongoDB growth (negligible on Atlas M0 free tier).
- Monitor: `"silent scrape completed"` in logs, `price_observations` collection growing ~1,500 rows/day.
- Disable: Set `SILENT_SCRAPE_HOURS=""` to fall back to scheduled captures only.
