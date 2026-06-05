# Scraping Cadence Configuration

BensaVahti currently has two scraping modes:

1. **Scheduled captures** at 14:00 and 21:00 Helsinki time: full scrape, prediction, `daily_tracker` write, and optional ntfy notification.
2. **Silent scrapes** at configurable hours: aggregate price observation only, no prediction and no notification.

Silent scrapes do **not** store station-level observations today. They write one aggregate `price_observations` document per `(date, hour, fuel)`.

---

## Environment Variables

### `SILENT_SCRAPE_HOURS`

Comma-separated list of Helsinki-time hours, 0-23, when silent scrapes run.

Default:

```bash
SILENT_SCRAPE_HOURS="6,8,10,12,16,18,20,22"
```

Examples:

```bash
# Default: 8 silent events/day
SILENT_SCRAPE_HOURS="6,8,10,12,16,18,20,22"

# Business hours
SILENT_SCRAPE_HOURS="9,10,11,12,13,15,16,17"

# Disabled: only scheduled captures run
SILENT_SCRAPE_HOURS=""
```

### `SCHEDULED_HOURS`

Hardcoded in `backend/tracker.py` as `(14, 21)`. These are the canonical truth timestamps for prediction evaluation and are not environment-configurable.

### `ENABLE_HINTATUTKA_EXPERIMENTAL`

Optional. Hintatutka is experimental and disabled from production scrapes by default. Set `ENABLE_HINTATUTKA_EXPERIMENTAL=1` only when explicitly verifying that scraper against current live HTML.

---

## Hour Behavior

| Hour | Scheduled? | Silent? | Behavior |
|------|------------|---------|----------|
| 14 | yes | no | Full capture, prediction, notification |
| 21 | yes | no | Full capture, prediction, notification |
| 10 | no | yes | Silent aggregate observation |
| 14 | yes | yes | Full capture wins; silent scrape skipped |

If an hour appears in both sets, scheduled capture takes precedence to avoid duplicate work.

---

## Runtime Write Shape

### `daily_tracker`

Written by scheduled captures only. Stores real capture truth rows with:

- `date`, `hour`, `fuel`, `region`
- `actual_cheapest`, `actual_cheapest_station`, `actual_cheapest_city`, `actual_cheapest_source`
- `stations_scanned`, `by_city`
- prediction fields for tomorrow and prediction-vs-actual tracking

### `price_observations`

Written by silent scrapes only. Stores aggregate docs:

```json
{
  "date": "2026-06-05",
  "hour": 10,
  "fuel": "95E10",
  "scraped_at": "2026-06-05T07:00:00+00:00",
  "cheapest": 1.922,
  "cheapest_station": "Neste Express Viikki",
  "cheapest_city": "Helsinki",
  "cheapest_source": "tankille.fi",
  "stations_scanned": 42,
  "by_city": {
    "Helsinki": {
      "cheapest": 1.922,
      "average": 1.977,
      "count": 12,
      "station": "Neste Express Viikki",
      "source": "tankille.fi"
    }
  }
}
```

No station-level fields such as `station_id` or per-station `price` are written by `tracker.silent_scrape`.

---

## Resource Impact

### Scrape Count

| Mode | Before | Default now | Multiplier |
|------|--------|-------------|------------|
| Price scrape events/day | 2 | 10 | 5x |

Default now means 8 silent events plus 2 scheduled capture events.

### MongoDB Storage

`price_observations` grows by default at:

- 2 aggregate docs per silent event, one for each fuel
- 8 silent events/day x 2 fuels = **16 aggregate docs/day**
- About 480 aggregate docs/month
- About 5,840 aggregate docs/year

Scheduled captures write `daily_tracker`, not `price_observations`.

### Network Requests

Production price scrapes use:

- `polttoaine.net`: 2 requests per both-fuels event
- `tankille.fi`: 12 requests per both-fuels event, 6 cities x 2 fuels

Total default production volume is about **14 HTTP requests per price-scrape event** and **140 requests/day** across 10 events. Hintatutka is excluded unless explicitly enabled as experimental.

---

## Monitoring

Startup log:

```text
unified scheduler started - notification: 14:00, 21:00, silent: 06:00, 08:00, 10:00, 12:00, 16:00, 18:00, 20:00, 22:00
```

Silent scrape log:

```text
silent scrape 95E10 @10h: cheapest=1.922 (Helsinki)
```

Scheduled capture log:

```text
notification capture 95E10 @14h: actual=1.857 predicted_tomorrow=1.862
```

Healthy metrics:

| Metric | Healthy Range | Alert Threshold |
|--------|---------------|-----------------|
| `price_observations` growth | about 16 aggregate docs/day | under 8/day |
| Failure rate | 0-1 `silent scrape failed` logs/day | over 3/day |
| Scrape duration | 5-15 seconds typical | over 60 seconds |
| Memory | under 200 MB RSS typical | over 400 MB sustained |

MongoDB checks:

```javascript
// Count aggregate observations by day.
db.price_observations.aggregate([
  { $group: { _id: "$date", count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])

// Inspect latest aggregate docs.
db.price_observations.find(
  {},
  { _id: 0, date: 1, hour: 1, fuel: 1, cheapest: 1, cheapest_city: 1, stations_scanned: 1 }
).sort({ date: -1, hour: -1 }).limit(10)

// Check duplicate aggregate docs.
db.price_observations.aggregate([
  { $group: { _id: { date: "$date", hour: "$hour", fuel: "$fuel" }, count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }
])
```

Alert conditions:

1. All production scrapers fail for a fuel three times in a row.
2. `price_observations` has no new aggregate docs in 6 hours while silent scrapes are enabled.
3. Backend memory is over 400 MB sustained.
4. API 5xx rate is over 10%.

---

## Deployment Notes

Set `SILENT_SCRAPE_HOURS` in Railway service variables. Railway redeploys the backend after variable changes.

Complete backend variable list:

| Variable | Required | Notes |
|----------|----------|-------|
| `MONGO_URL` | yes | MongoDB Atlas connection string |
| `DB_NAME` | yes | Usually `bensavahti` |
| `EMERGENT_LLM_KEY` | yes | Claude prediction calls |
| `PIP_EXTRA_INDEX_URL` | yes | Required for `emergentintegrations` |
| `ADMIN_TOKEN` | optional | Enables `/api/admin/run` |
| `NTFY_TOPIC` | optional | Notifications no-op without it |
| `NTFY_TOKEN` | optional | Bearer token for ntfy.sh |
| `NEWS_WATCH_SECONDS` | optional | Default `1800`; `0` disables news watcher |
| `SILENT_SCRAPE_HOURS` | optional | Default `6,8,10,12,16,18,20,22` |
| `ENABLE_HINTATUTKA_EXPERIMENTAL` | optional | Disabled by default |
| `CORS_ORIGINS` | optional | Defaults to production Vercel origin |

---

## Future Work

Station-level `price_observations` would be useful for intraday calibration, source freshness scoring, and station stability analysis. That is future work and should come with explicit schema, indexes, storage estimates, and tests before docs claim station-level runtime storage.
