# README.ai.md — BensaVahti for AI Agents

> **Audience**: This file is written for an AI coding agent picking up this repo
> with little context. It's deliberately dense, explicit, and skips marketing
> language. Skim the table of contents, then jump to the section you need.

## 0. TL;DR (60-second orientation)

- **What**: A Finnish fuel-price dashboard + tomorrow-price-predictor + ntfy
  push-notifier. UI in Finnish.
- **Stack**: React (CRA) on Vercel · FastAPI + Motor (async MongoDB) on Railway
  · MongoDB Atlas (free M0).
- **AI**: Claude Opus 4.7 via `emergentintegrations` SDK (Anthropic) — invoked
  from `backend/predict.py` for the AI-prediction method.
- **Data inputs**: Live scrapes of `polttoaine.net` + `tankille.fi`; Statistics
  Finland (Tilastokeskus) PxWeb API for the long-term real history; Yahoo
  Finance for Brent + EUR/USD; RSS news from a handful of Finnish sources.
- **Current production URLs**
  - Frontend: `https://polttoaine-notifi.vercel.app`
  - Backend: `https://polttoaine-notifi-production.up.railway.app`
  - Notifications: ntfy.sh topic `polttoaine`

## 1. Why this app exists

Finnish drivers care about pump prices because diesel/95E10 swings ±5 ¢/L per
week. The app:

1. Shows today's cheapest station nationally + per-city (Helsinki, Vantaa, Espoo, Tampere, Turku, …).
2. Predicts **tomorrow's** cheapest using 4 parallel methods (MA, LR, Holt
   exp.smoothing, Claude Opus 4.7) and a weighted ensemble.
3. Captures actuals at 06:00 and 20:00 Helsinki time and tracks
   prediction-vs-actual accuracy over time.
4. Sends a push notification (ntfy.sh) at each capture with a multi-fuel
   summary, formatted to match the user's previous-version messages.

## 2. Architecture (3-service split-stack)

```
┌──────────────────────────┐    fetch    ┌──────────────────────────────┐    motor    ┌────────────────────┐
│  Vercel                  │ ─────────▶ │  Railway                      │ ─────────▶ │  MongoDB Atlas      │
│  React CRA frontend      │   HTTPS    │  FastAPI + uvicorn            │            │  free M0 cluster    │
│  polttoaine-notifi       │            │  polttoaine-notifi-production │            │  db = bensavahti    │
│  .vercel.app             │            │  .up.railway.app              │            │                     │
└──────────────────────────┘            └─────────────┬─────────────────┘            └────────────────────┘
                                                     │
                                                     │ scheduled (06:00 / 20:00 Helsinki)
                                                     ▼
                                          ┌──────────────────────┐         ┌──────────────────────┐
                                          │  ntfy.sh             │         │  Anthropic Claude     │
                                          │  topic: polttoaine   │         │  via emergentintegr.  │
                                          │  bearer token auth   │         │  Opus 4.7 → Sonnet… │
                                          └──────────────────────┘         └──────────────────────┘
```

The frontend ONLY uses `REACT_APP_BACKEND_URL` (no other endpoints).
The backend has NO frontend assets — pure API.

## 3. Repository layout

```
/app/
├── README.md              … original README (sparse)
├── README.ai.md           … THIS file
├── VERCEL_DEPLOYMENT.md   … step-by-step Vercel setup
├── RAILWAY_DEPLOYMENT.md  … step-by-step Railway setup
├── memory/PRD.md          … living product requirements (single source of truth for backlog)
├── backend/               … FastAPI app (Railway root directory = backend)
│   ├── server.py          … ALL routes; ~990 lines, single file
│   ├── predict.py         … 4 prediction methods incl. Claude Opus 4.7
│   ├── tracker.py         … 06:00 / 20:00 capture loop + capture_daily()
│   ├── notify.py          … ntfy.sh publisher (multi-fuel summary)
│   ├── factors.py         … Brent + EUR/USD via Yahoo Finance
│   ├── news.py            … RSS aggregator (Talouselämä, Iltalehti, etc.)
│   ├── statfin.py         … Statistics Finland PxWeb client (REAL monthly data)
│   ├── simulate.py        … LEGACY synthetic history (do not use, kept for /api/seed compat)
│   ├── real_history.py    … (legacy stub, mostly unused)
│   ├── scrapers/
│   │   ├── polttoaine.py  … polttoaine.net scraper (top-N cheapest)
│   │   └── tankille.py    … tankille.fi scraper (per-city pages) — PRIMARY source
│   ├── requirements.txt   … pinned deps (fastapi, motor, numpy, emergentintegrations)
│   ├── Procfile           … `web: uvicorn server:app --host 0.0.0.0 --port $PORT`
│   ├── railway.json       … explicit Railway build/deploy config
│   ├── .python-version    … `3.11`
│   ├── .env               … local-only secrets (NOT in git)
│   └── tests/             … pytest
└── frontend/              … React CRA app (Vercel root directory = frontend)
    ├── vercel.json        … SPA rewrites + caching headers
    ├── .vercelignore
    ├── .env.example       … REACT_APP_BACKEND_URL placeholder
    ├── package.json       … react 18, recharts, framer-motion, lucide-react, axios, tailwind
    ├── public/index.html
    └── src/
        ├── App.js         … main page; ~665 lines, single component tree
        ├── App.css
        ├── index.js / index.css
        ├── lib/
        │   ├── api.js     … axios wrappers for every backend route
        │   ├── utils.js   … fmtPrice, fmtDelta, fmtDateFi…
        │   └── modelName.js … converts "claude-opus-4-7" → "Claude Opus 4.7"
        └── components/
            ├── Card.jsx        … design-system primitives (Card, CardLabel, StatNumber, DeltaBadge)
            ├── FuelToggle.jsx  … 95E10 / Diesel toggle
            ├── RangeToggle.jsx … 30/90/365 day toggle (currently UNUSED — chart removed)
            ├── TrackingChart.jsx … prediction-vs-actual line chart (REAL DATA ONLY)
            ├── HistoryChart.jsx  … LEGACY long-history area chart (NOT rendered in App.js)
            ├── MethodTable.jsx  … 4-method comparison + ensemble
            ├── AiAnalysis.jsx   … Claude analysis card
            ├── FactorsCard.jsx  … Brent + EUR/USD sparklines
            ├── NewsCard.jsx     … RSS news list
            ├── RegionalGrid.jsx … city-by-city cheapest grid
            └── AccuracyTracker.jsx … historical prediction accuracy MAE
```

## 4. MongoDB collections

| Collection         | Schema (key fields)                                                | Purpose                                        |
| ------------------ | ------------------------------------------------------------------ | ---------------------------------------------- |
| `snapshots`        | `fuel, ts, national_min, by_city, cheap_sample_avg, rows[]`        | Cached scrape result, ~5min TTL via app cache  |
| `history`          | `fuel, region, date, price, source`                                | **Synthetic seed** — LEGACY, do not rely on    |
| `history_snapshots`| same                                                               | LEGACY simulate output                         |
| `daily_tracker`    | `fuel, region, date, hour, actual_cheapest, prediction_for_*, …`   | **The truth**: real captures at 06h + 20h      |
| `predictions`      | `target_date, fuel, region, methods_full, ensemble_full, data_sources` | Latest /api/predict/run output, one per fuel+region+target_date |

**Unique index** on `daily_tracker` is `(fuel, region, date, hour)` — was `(fuel, region, date)` before. Migration in `server.py` startup drops the legacy index.

## 5. Backend route map (`server.py`)

Grouped logically. All routes are prefixed `/api`.

### Prices (live)
| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/prices/current?fuel=95E10` | Scrape + aggregate; cached 5 min |
| GET  | `/api/prices/history?fuel=95E10&days=90` | Read `history_snapshots` — **synthetic, LEGACY** |
| GET  | `/api/regional?fuel=95E10&max_age_hours=24` | Live per-city cheapest, cached 90s |

### Factors
| GET | `/api/factors` | Brent + EUR/USD time series (Yahoo Finance, cached 15 min) |

### News
| GET | `/api/news?max_age_days=14&limit=8` | RSS-aggregated Finnish fuel news |

### Predictions
| POST | `/api/predict/run` | **Runs all 4 methods** using Statfin real monthly + daily_tracker captures (NO synthetic). Persists into `predictions` collection. |
| GET  | `/api/predict/latest?fuel=95E10` | Returns last stored prediction |

### Tracking (real captures)
| POST | `/api/track/run`     | Capture one fuel manually |
| POST | `/api/track/run-all?notify=true` | Capture both fuels + optionally fire ntfy |
| POST | `/api/track/backfill?clear=true` | Bulk-upsert historical points (from notification archive); `clear=true` wipes the collection first |
| GET  | `/api/track/history?fuel=95E10&days=60` | Read all captures sorted by (date, hour); includes summary (MAE, hit-rate ≤1¢, tomorrow_prediction, today_actual) |

### Notifications
| POST | `/api/notify/test` | Build summary from latest captures + publish to ntfy. Smoke-test endpoint. |

### Seed (DO NOT USE)
| POST | `/api/seed?days=180&force=true` | Generates SYNTHETIC history via `simulate.py`. **Deprecated** — user explicitly rejected synthetic data. Kept only for backward compat. |

## 6. Data flow — how a prediction happens

```
┌────────────────────────┐
│  /api/predict/run      │  ← called either by user "Päivitä" button OR by tracker.capture_daily()
└──────────┬─────────────┘
           │
           ▼ build real data series (NO synthetic)
   ┌────────────────────────────────────────────────────────┐
   │ statfin.fetch_monthly(fuel, since_year=2023)            │  REAL monthly EUR/L from Tilastokeskus
   │  → 36 points, one per month at YYYY-MM-15               │
   │ + db.daily_tracker.find({fuel, region}).sort(date,hour) │  REAL daily captures
   │  → ~N points (3 backfilled + 2/day going forward)       │
   │ de-dup by date, sort                                    │
   └──────────────────────┬─────────────────────────────────┘
                          │ ≥7 points required
                          ▼
   ┌─────────────────────────────────────────┐    parallel I/O
   │  predict_tomorrow(fuel, dates, prices,  │ ◀───────────────┐
   │      brent, eur_usd,                    │  factors.fetch_*  │
   │      live_today_price=cheap_sample_avg, │                  │
   │      news_headlines=[...])              │  news.fetch_news  │
   └────────────────┬────────────────────────┘                  │
                    │                                            │
                    ├─▶ moving_average(7)                        │
                    ├─▶ linear_regression(30)                    │
                    ├─▶ exp_smoothing(α=0.4, β=0.2)              │
                    └─▶ ai_llm_predict()                         │
                          │                                      │
                          ▼                                      │
                  LlmChat (emergentintegrations)                 │
                  models_to_try = [                              │
                    ("anthropic","claude-opus-4-7"),             │
                    ("anthropic","claude-opus-4-6"),             │
                    ("anthropic","claude-sonnet-4-5-20250929"),  │
                    ("anthropic","claude-haiku-4-5-20251001"),   │
                  ]
                  → JSON {predicted_price, confidence_*, direction,
                          explanation, key_drivers}

         ensemble = weighted avg (MA 0.20 / LR 0.25 / Holt 0.30 / AI 0.25)

         persist into db.predictions with target_date = today+1
```

## 7. The Claude prompt (`predict.py` → `ai_llm_predict`)

The system message is the **"Mikko" persona** — a Finnish fuel-pricing analyst
with 6 numbered principles (anchor / tax constant / Brent lag / EUR-USD beta /
weekday effect / momentum). The user message has 5 labeled sections:

```
=== HINTA-ANKKURI ===      live pump price as the anchor
=== MOMENTUMSIGNAALI ===   explicit 7-day slope in m€/L/day
=== 21 PÄIVÄN HISTORIA === recent prices day-by-day
=== MAKROINPUTTEJA ===     Brent + EUR/USD + 6 latest news headlines
=== TEHTÄVÄSI ===          numbered 4-step recipe
```

Model returns strict JSON; the function strips markdown fences, finds the first
`{` and last `}`, parses, and returns a `dict` with `value`, `confidence_low/high`,
`direction`, `explanation`, `key_drivers`, `model`.

If Opus 4.7 fails (rate-limit / budget / network), it falls through to 4.6,
then Sonnet 4.5, then Haiku 4.5. Each gets 3 attempts.

## 8. Scrapers

Both scrapers return a list of dicts with the same shape:
```py
{"city": "Helsinki", "station": "Neste Oil Express - Viikki",
 "address": "Viikinportti 1", "price": 1.922, "fuel": "95E10",
 "source": "polttoaine.net" | "tankille.fi", "age_hours": 9.0, ...}
```

**Sanity filter** (in `server.py` `_sanity_filter` and `notify.py`):
- Hard bounds: 1.10 €/L ≤ price ≤ 3.50 €/L (handles parsing errors)
- Median deviation: drop rows where `|price - median| / median > 0.25`
- Applied independently to each scraper batch before merging

**Source priority** (`server.py:_scrape_all`, `notify.py:_format_city_block`):
- `tankille.fi` is PRIMARY (user preference; tested as more accurate/fresh)
- `polttoaine.net` is SECONDARY (cross-check; shown in "Lähteet:" line)
- If tankille >10% higher than polttoaine for the same city → fall back to polttoaine

## 9. Notification format (`notify.py`)

Matches the user's previous version exactly:

```
⛽ 95E10 alkaen 1.999 EUR (Helsinki)

=== 95E10 ===
Helsinki: 1.999 EUR
Neste Helsinki Viikki - Viikinportti 1
Lähteet: polttoaine.net 1.922 | tankille.fi 1.999
Vantaa: …

=== Diesel ===
Halvin koko Suomessa: 2.069 EUR
Alavus - Kyläkaupan Bensa-asema …
Helsinki: …
```

Title is **ASCII-only** (HTTP header constraint — em-dashes etc. fail with
`UnicodeEncodeError: latin-1`). Body is UTF-8.

Triggered from:
- `tracker.scheduler_loop` at each 06:00 / 20:00 Helsinki tick
- `POST /api/track/run-all?notify=true` (manual)
- `POST /api/notify/test` (smoke-test using latest DB captures, no fresh scrape)

## 10. Environment variables

### Vercel (frontend)
| Var                      | Required | Example |
|--------------------------|----------|---------|
| `REACT_APP_BACKEND_URL`  | yes      | `https://polttoaine-notifi-production.up.railway.app` (no trailing slash) |

CRA bakes env vars at build time → changing this requires a redeploy.

### Railway (backend)
| Var                  | Required | Notes |
|----------------------|----------|-------|
| `MONGO_URL`          | yes      | MongoDB Atlas connection string |
| `DB_NAME`            | yes      | `bensavahti` |
| `EMERGENT_LLM_KEY`   | yes      | Universal LLM key (`sk-emergent-…`) for Claude via emergentintegrations |
| `PIP_EXTRA_INDEX_URL`| yes      | `https://d33sy5i8bnduwe.cloudfront.net/simple/` — emergentintegrations lives on Emergent's private PyPI, not on public PyPI |
| `CORS_ORIGINS`       | no       | defaults to `*` |
| `NTFY_TOPIC`         | optional | `polttoaine` (without it, notifications silently no-op) |
| `NTFY_TOKEN`         | optional | bearer token from ntfy.sh paid account |
| `NTFY_SERVER`        | optional | default `https://ntfy.sh` |
| `NTFY_CLICK_URL`     | optional | URL opened when notification is tapped |
| `PORT`               | auto     | Set by Railway, do NOT override |

## 11. Deployment

User-side actions are mandatory — the AI agent CANNOT push to GitHub.

```
Save to GitHub (button in Emergent chat input)
        │
        ├──▶ GitHub receives commits
        │
        ├──▶ Vercel autodeploys frontend     (~90 s)
        │     Reads frontend/vercel.json
        │     Builds with yarn build
        │
        └──▶ Railway autodeploys backend     (~120 s)
              Reads backend/railway.json + Procfile
              Installs requirements.txt (needs PIP_EXTRA_INDEX_URL!)
              Starts: uvicorn server:app --host 0.0.0.0 --port $PORT
```

Vercel root directory: `frontend`. Railway root directory: `backend`. Both **MUST** be set correctly in the platform dashboards or builds fail.

## 12. Frontend ↔ Backend contract

`frontend/src/lib/api.js` is the single source of truth for the HTTP contract.
Every backend route is wrapped there. If you add a route, add an axios wrapper
here, otherwise nothing in the UI can call it.

Critical contract details:
- All routes prefixed `/api`
- Numeric fields are JSON floats (e.g. `1.857`), NOT strings
- Timestamps are ISO-8601 with timezone
- `data_sources` field is `null | {statfin_monthly_points, tracker_captures, combined_points}`
- `methods.ai_llm.model` is the actual model id string (`claude-opus-4-7`) — `lib/modelName.js` converts it to display label

## 13. UI conventions

- **Finnish language UI** (do NOT translate to English in any code path)
- Tailwind utility classes, design tokens in `App.css`
- Data-testid on every interactive element + every user-facing data field
- Dark hero card (#0F172A-ish background) for tomorrow's prediction
- Light cards for everything else
- Color tokens (`text-brand`, `text-accent`, `text-secondary`, `text-muted`, `text-ink`, `bg-line`) defined in tailwind.config.js / App.css
- Charts use **Recharts**, monospace numbers use `tnum` utility class

## 14. Recurring gotchas

| Gotcha                                                | Where it bit                                                          |
|-------------------------------------------------------|-----------------------------------------------------------------------|
| `emergentintegrations` not on public PyPI             | Add `PIP_EXTRA_INDEX_URL` to Railway → otherwise build fails          |
| `pydantic_core` version mismatch with `pydantic`      | requirements.txt pins both (`pydantic==2.6.4`, `pydantic_core==2.16.3`) |
| Non-ASCII chars in `Title:` HTTP header               | ntfy publish would 500 with UnicodeEncodeError; use ASCII-only title  |
| CRA bakes env vars at **build** time                  | Changing REACT_APP_BACKEND_URL needs a Vercel redeploy, not a refresh |
| `simulate.py` produces synthetic data                 | User rejected this; `/api/predict/run` now uses Statfin instead       |
| `_id` field is `ObjectId` — not JSON serializable     | Always `.find(..., {"_id": 0})` or strip it                           |
| `datetime.utcnow()`                                   | Use `datetime.now(timezone.utc)` instead                              |
| Synthetic data still in `history_snapshots`           | Predict path no longer reads it; chart no longer plots it             |
| `daily_tracker` legacy unique index `(fuel,region,date)` | startup explicitly drops it before adding the hour-aware one        |
| Vercel framework auto-detected as "services"          | Override to "Create React App" in Project Settings; root = `frontend` |

## 15. How to do common things

### Add a new fuel
1. `server.py` — add to `FUELS` tuple
2. `scrapers/polttoaine.py` + `scrapers/tankille.py` — add mapping
3. `simulate.py:BASELINE` — only if you keep synthetic path alive (not needed)
4. `statfin.py:FUEL_CODE` — add Tilastokeskus item code
5. `frontend/src/components/FuelToggle.jsx` — add button
6. `frontend/src/App.js` — adjust hero & fuel-list rendering

### Add a new region/city
1. `server.py:SUPPORTED_REGIONS` — add
2. `scrapers/tankille.py` — add per-city URL slug
3. `simulate.py:CITY_FACTORS` — add factor (only if synthetic kept)
4. `frontend/src/components/RegionalGrid.jsx` — auto-renders from API

### Tune the prediction
1. `predict.py:ensemble.weights` — change MA/LR/Holt/AI weights
2. `predict.py:moving_average(window=…)` — change MA window
3. `predict.py:ai_llm_predict.system_message` — change Mikko principles
4. `predict.py:ai_llm_predict.models_to_try` — reorder fallback chain

### Trigger a capture manually
```bash
curl -X POST "$BACKEND_URL/api/track/run-all?notify=true"
```

### Backfill historical data
```bash
curl -X POST "$BACKEND_URL/api/track/backfill?clear=true" \
  -H "Content-Type: application/json" \
  -d '[{"date":"2026-05-11","hour":20,"fuel":"95E10","actual_cheapest":1.937,
        "actual_cheapest_city":"Vantaa","actual_cheapest_station":"…"}]'
```
`clear=true` wipes `daily_tracker` first. Omit for additive insert.

### Run linters
```bash
# Python
ruff check /app/backend
# JS
yarn --cwd /app/frontend lint   # via eslint
```

### Check service health
```bash
# Backend (Railway)
curl https://polttoaine-notifi-production.up.railway.app/api/factors
# Frontend (Vercel) — open the URL, check DevTools Network for 200s
```

## 16. Current state (2026-05-16)

**Working in production**:
- ✅ End-to-end Vercel + Railway + Atlas
- ✅ Claude Opus 4.7 verified live in `methods.ai_llm.model`
- ✅ Tankille-primary + sanity filter merged
- ✅ Backfill endpoint deployed
- ✅ 6 real historical points in `daily_tracker`
- ✅ Notification topic + token configured (token in user's hands)

**Latest commits NOT yet deployed** (user needs to push):
- ⏳ Mikko prompt in `predict.py`
- ⏳ Statfin real-data path in `/api/predict/run`
- ⏳ Hour-aware capture in `tracker.py` (06:00 / 20:00 as separate rows)
- ⏳ Updated tankille-primary picker in `notify.py`

**Pending user action**:
1. Click "Save to GitHub" to push the queued commits
2. Add 4 `NTFY_*` env vars on Railway

## 17. Useful one-liners for debugging

```bash
# What model did the latest prediction actually use?
curl -s "$BACKEND_URL/api/predict/latest?fuel=95E10" | jq '.methods.ai_llm.model'

# How many real data points feed the prediction?
curl -s -X POST "$BACKEND_URL/api/predict/run" \
  -H "Content-Type: application/json" \
  -d '{"fuel":"95E10","region":"Suomi"}' | jq '.data_sources'

# Verify ntfy works without scraping
curl -s -X POST "$BACKEND_URL/api/notify/test" | jq

# Inspect a single capture
curl -s "$BACKEND_URL/api/track/history?fuel=95E10&days=60" | jq '.rows[-1]'

# Hit ntfy directly (sanity-check token)
curl -X POST "https://ntfy.sh/polttoaine" \
  -H "Authorization: Bearer $NTFY_TOKEN" \
  -H "Title: Sanity check" \
  -d "If this lands, ntfy + token are fine"
```

## 18. Files an AI agent should NOT touch without strong reason

- `frontend/.env` — read-only; managed via Vercel UI in production
- `backend/.env` — local-only secrets; do NOT commit
- `.git`, `.emergent`, `node_modules`, `__pycache__`, `yarn.lock`
- `requirements.txt` — update only via `pip install X && pip freeze` (per platform rules)
- `package.json` — update only via `yarn add X` (per platform rules)

## 19. Where to learn more (in this repo)

- **What was built and when**: `/app/memory/PRD.md`
- **How to deploy frontend**: `/app/VERCEL_DEPLOYMENT.md`
- **How to deploy backend**: `/app/RAILWAY_DEPLOYMENT.md`
- **Original problem statement & user history**: chat conversation log
