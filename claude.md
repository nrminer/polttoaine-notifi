# claude.md — BensaVahti for AI Agents

> **Audience**: This file is written for an AI coding agent picking up this repo
> with little context. It's deliberately dense, explicit, and skips marketing
> language. Skim the table of contents, then jump to the section you need.

## 0. TL;DR (60-second orientation)

- **What**: A Finnish fuel-price dashboard + tomorrow-price-predictor + ntfy
  push-notifier. UI in Finnish.
- **Stack**: React (CRA) on Vercel · FastAPI + Motor (async MongoDB) on Railway
  · MongoDB Atlas (free M0).
- **AI**: Claude Opus 4.8 via Anthropic-compatible proxy
  (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`) — invoked from
  `backend/predict.py` for the AI-prediction method.
- **Data inputs**: **LIVE-GATHERED ONLY** — scrapes of `polttoaine.net` +
  `tankille.fi` captured into `daily_tracker` from today onward; Yahoo Finance
  for Brent + EUR/USD; RSS news from Finnish sources. **Tilastokeskus (Statfin)
  was REMOVED — data too old; `statfin.py`, `simulate.py`, `real_history.py`
  are deleted. No synthetic / interpolated / extrapolated data anywhere.**
- **UI theme**: light + dark, **dark is the default** (toggle in header,
  persisted to `localStorage`, no-FOUC script in `index.html`).
- **Current production URLs**
  - Frontend: `https://polttoaine-notifi.vercel.app`
  - Backend: `https://polttoaine-notifi-production.up.railway.app`
  - Notifications: ntfy.sh topic `polttoaine`

## 1. Why this app exists

Finnish drivers care about pump prices because retail diesel/95E10 moves
visibly week-to-week (concrete magnitude is what the captured data will
tell us — no hard-coded ±N ¢/L claim). The app:

1. Shows today's cheapest station nationally + per-city (Helsinki, Espoo,
   Vantaa, Tampere, Turku, Lahti) with cheapest **and average** per city.
2. Predicts **tomorrow's** cheapest using **5 parallel methods** (MA, LR, Holt
   exp.smoothing, **fundamental_anchor** = live + Brent-EUR pass-through +
   weekday + momentum, and Claude Opus 4.8 with geopolitical-risk handling) →
   a **data-quality-aware ensemble clamped to ±0.06 €/L of the live price**.
3. Captures actuals at **14:00 and 21:00 Helsinki** (`SCHEDULED_HOURS` in
   `tracker.py`) and tracks prediction-vs-actual accuracy against **real
   captures only**.
4. Sends a push notification (ntfy.sh) at each capture.
5. Re-runs the AI analysis automatically when new fuel-relevant news appears
   (backend `news_watch_loop`, rate-limited).
6. All-cities-average chart with a market-move projection, below the
   cheapest-station chart.

## 2. Architecture (3-service split-stack)

```
┌──────────────────────────┐    fetch    ┌──────────────────────────────┐    motor    ┌────────────────────┐
│  Vercel                  │ ─────────▶ │  Railway                      │ ─────────▶ │  MongoDB Atlas      │
│  React CRA frontend      │   HTTPS    │  FastAPI + uvicorn            │            │  free M0 cluster    │
│  polttoaine-notifi       │            │  polttoaine-notifi-production │            │  db = bensavahti    │
│  .vercel.app             │            │  .up.railway.app              │            │                     │
└──────────────────────────┘            └─────────────┬─────────────────┘            └────────────────────┘
                                                     │
                                                     │ scheduled (14:00 / 21:00 Helsinki) + news-watcher
                                                     ▼
                                          ┌──────────────────────┐         ┌──────────────────────┐
                                          │  ntfy.sh             │         │  Anthropic Claude     │
                                          │  topic: polttoaine   │         │  via proxy endpoint  │
                                          │  bearer token auth   │         │  Opus 4.8 → Opus… │
                                          └──────────────────────┘         └──────────────────────┘
```

The frontend ONLY uses `REACT_APP_BACKEND_URL` (no other endpoints).
The backend has NO frontend assets — pure API.

## 3. Repository layout

```
/app/
├── README.md              … original README (sparse)
├── claude.md               … THIS file (was README.ai.md, now deleted)
├── VERCEL_DEPLOYMENT.md   … step-by-step Vercel setup
├── RAILWAY_DEPLOYMENT.md  … step-by-step Railway setup
├── memory/PRD.md          … living product requirements (single source of truth for backlog)
├── backend/               … FastAPI app (Railway root directory = backend)
│   ├── server.py          … ALL routes incl. /api/admin/run; single file
│   ├── predict.py         … 5 methods (MA/LR/ES/fundamental_anchor/AI) + ensemble
│   ├── tracker.py         … 14:00/21:00 capture loop + capture_daily() + news_watch_loop()
│   ├── notify.py          … ntfy.sh publisher (multi-fuel summary)
│   ├── factors.py         … Brent + EUR/USD via Yahoo Finance (+ change_frac)
│   ├── news.py            … RSS aggregator (Iltalehti, HS, IS, MTV)
│   ├── capture_now.py     … standalone: manual capture NOW → daily_tracker
│   ├── purge_captures.py  … standalone: delete daily_tracker rows (dry-run unless --yes)
│   ├── scrapers/
│   │   ├── polttoaine.py  … polttoaine.net scraper (top-N cheapest)
│   │   └── tankille.py    … tankille.fi scraper (per-city pages) — PRIMARY source
│   ├── requirements.txt   … pinned deps (fastapi, motor, numpy, requests)
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
        │   └── modelName.js … converts "claude-opus-4-8" → "Claude Opus 4.8"
        └── components/
            ├── Card.jsx        … design-system primitives (Card, CardLabel, StatNumber, DeltaBadge)
            ├── FuelToggle.jsx  … 95E10 / Diesel toggle
            ├── RangeToggle.jsx … 30/90/365 day toggle (currently UNUSED — chart removed)
            ├── TrackingChart.jsx … prediction-vs-actual line chart; city mode (cheapest+avg), filters
            ├── CityAverageChart.jsx … all-cities average + market-move projection
            ├── MethodTable.jsx  … 5-method comparison + ensemble (incl. fundamenttiankkuri)
            ├── AiAnalysis.jsx   … Claude analysis card
            ├── FactorsCard.jsx  … Brent + EUR/USD sparklines
            ├── NewsCard.jsx     … RSS news list
            ├── RegionalGrid.jsx … city-by-city cheapest grid
            └── AccuracyTracker.jsx … historical prediction accuracy MAE
```

## 4. MongoDB collections

| Collection         | Schema (key fields)                                                | Purpose                                        |
| ------------------ | ------------------------------------------------------------------ | ---------------------------------------------- |
| `snapshots`        | `fuel, ts, national_min, by_city, cheap_sample_avg`               | Latest live scrape (live anchor source)        |
| `history`          | `fuel, region, date, price, source`                                | **REAL only** now: only `source:"scraped"` (live daily). No synthetic/statfin/interp rows (purged) |
| `daily_tracker`    | `fuel, region, date, hour, actual_cheapest, by_city, prediction_for_*, prediction_full` | **The truth**: real captures at 14h + 21h; `by_city` = {cheapest, average, count, station, source} |
| `predictions`      | `target_date, fuel, region, methods_full, ensemble_full, data_sources` | Last /api/predict/run output (what UI shows via /predict/latest) |

**Unique index** on `daily_tracker` is `(fuel, region, date, hour)` — was `(fuel, region, date)` before. Migration in `server.py` startup drops the legacy index.

## 5. Backend route map (`server.py`)

Grouped logically. All routes are prefixed `/api`.

### Prices (live)
| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/prices/current?fuel=95E10` | Scrape + aggregate; cached 5 min |
| GET  | `/api/prices/history?fuel=95E10&days=90` | Read `history` — **real live `scraped` points only** |
| GET  | `/api/regional?fuel=95E10&max_age_hours=24` | Live per-city cheapest, cached 90s; polttoaine.net age = real elapsed since report-date Helsinki midnight (no fabricated hour) |

### Factors
| GET | `/api/factors` | Brent + EUR/USD time series (Yahoo Finance, cached 15 min) |

### News
| GET | `/api/news?max_age_days=14&limit=8` | RSS-aggregated Finnish fuel news |

### Predictions
| POST | `/api/predict/run` | Runs **all 5 methods** from **daily_tracker captures ONLY** + live anchor (NO Statfin). Cold-start tolerant: 400 only if there is literally no live data. Persists into `predictions`. |
| GET  | `/api/predict/latest?fuel=95E10` | Returns last stored prediction (this is what the UI renders — never triggers a fresh run itself) |

### Tracking (real captures)
| POST | `/api/track/run`     | Capture one fuel manually |
| POST | `/api/track/run-all?notify=true` | Capture both fuels + optionally fire ntfy |
| POST | `/api/track/backfill?clear=true` | Bulk-upsert historical points (from notification archive); `clear=true` wipes the collection first |
| GET  | `/api/track/history?fuel=95E10&days=60` | Read all captures sorted by (date, hour); includes summary (MAE, hit-rate ≤2¢, tomorrow_prediction, today_actual) |

### Notifications
| POST | `/api/notify/test` | Build summary from latest captures + publish to ntfy. Smoke-test endpoint. |

### Admin (password-protected — Postman/curl)
| POST | `/api/admin/run` | Body `{password, action, fuel, region, hour, notify}` (or `X-Admin-Token` header). Auth = env `ADMIN_TOKEN` (constant-time; 503 if unset, 401 on mismatch). `action`: `ping`/`capture`/`predict`/`all`/`notify`. `predict`/`all` write `predictions` → fixes a stale UI. |

### Seed (DISABLED — no-op)
| POST | `/api/seed` | Historical/synthetic seeding **disabled** (Tilastokeskus removed: too old). Now only **purges** legacy modeled rows from `history`; never writes data. `days`/`force` are no-ops. |
| GET  | `/api/accuracy` | Scores predictions **only against real `daily_tracker` captures** (never modeled history). |

## 6. Data flow — how a prediction happens

```
┌────────────────────────┐
│  /api/predict/run      │  ← called either by user "Päivitä" button OR by tracker.capture_daily()
└──────────┬─────────────┘
           │
           ▼ build LIVE-ONLY series (NO Statfin, NO synthetic)
   ┌────────────────────────────────────────────────────────┐
   │ db.daily_tracker.find({fuel,region}).sort(date,hour)    │  REAL captures only
   │  → one point/day (latest hour wins)                     │
   │ live_anchor = latest snapshots.cheap_sample_avg         │
   │  → 400 only if NO series AND no live anchor              │
   └──────────────────────┬─────────────────────────────────┘
                          │ (cold-start tolerant: works at 0–N points)
                          ▼
   ┌─────────────────────────────────────────┐    parallel I/O
   │  predict_tomorrow(dates, prices,        │ ◀───────────────┐
   │     brent, eur_usd, brent_chg, fx_chg,  │  factors.fetch_* │
   │     live_today_price, news_headlines)   │  + change_frac   │
   └────────────────┬────────────────────────┘  news.fetch_news │
                    │ (all date-aware: +1 calendar day)         │
                    ├─▶ moving_average(7)        date-aware tail │
                    ├─▶ linear_regression(30)    date-aware      │
                    ├─▶ exp_smoothing(α0.4,β0.2) date-aware tail │
                    ├─▶ fundamental_anchor()  live + Brent-EUR    │
                    │      pass-through + weekday + momentum,     │
                    │      clamped ±0.06 €/L                      │
                    └─▶ ai_llm_predict()  Claude + geo-risk       │
                          │  (Anthropic proxy, Opus 4.8 →         │
                          │   Opus 4.7 → 4.6 → Sonnet/Haiku 4.5)  │
                          ▼
   ensemble = data-quality-aware weights (thin daily data → lean on
   fundamental_anchor 0.48 + AI 0.30); result CLAMPED ±0.06 €/L of live
   persist into db.predictions (target_date = today+1)

   Re-runs also fire from tracker.news_watch_loop when the filtered
   fuel-news headline set changes (rate-limited, ≥15 min gap).
```

## 7. The Claude prompt (`predict.py` → `ai_llm_predict`)

The system message frames the model as a quantitative analyst for Finnish
retail fuel pricing and lists **9 numbered principles** that are explicitly
labelled as **uncalibrated priors** (to be tightened from captured data,
not blindly trusted): live-anchor / tax-as-known-step / refined product as
day-ahead lead signal / crack-spread direction / EUR-USD direction / weak
weekday prior / explicit lag-pikes (t-1, t-2, t-3, t-7) / momentum /
geopolitics (don't double-count Brent-priced risk). Specific Finland-
unmeasured day-counts, c/L bands, and threshold numbers have been removed —
the prompt uses directional language and lets the data decide magnitudes.
The user message sections:

```
=== HINTA-ANKKURI ===                 live pump price as the anchor
=== LAG-PIIKIT ===                    t-1, t-2, t-3, t-7 prices from daily tail
=== MOMENTUMSIGNAALI ===              real daily-tail slope (m€/L/day)
=== LIVE-SKRAPATTU PÄIVÄHISTORIA ===  recent live captures day-by-day
=== DATALAATU ===                     n real daily points; flags THIN data
=== JALOSTETTU TUOTE ===              RBOB / HO spot USD/gal + ≈EUR/L + crack
=== MAKROINPUTTEJA ===                Brent + EUR/USD (+ ~5d % change) + news
=== VEROMUUTOKSET ===                 upcoming excise/VAT step events (if any)
=== GEOPOLIITTINEN RISKI ===          conflict headlines (keyword-scanned)
=== TEHTÄVÄSI ===                     numbered recipe (geo premium only if escalating)
```

Brent/EUR-USD ~5-day % change and the refined-product 5-day change are
threaded in via `factors.change_frac`. Geopolitical/conflict risk is split:
*already-priced* risk flows through Brent → `fundamental_anchor`; *forward*
risk is the AI's job (no double-count).

Model returns strict JSON; the function strips markdown fences, finds the first
`{` and last `}`, parses, and returns a `dict` with `value`, `confidence_low/high`,
`direction`, `explanation`, `key_drivers`, `model`.

If Opus 4.8 fails (rate-limit / budget / network), it falls through to Opus
4.7, 4.6, Sonnet 4.5, then Haiku 4.5. Each gets 3 attempts.

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
- `tracker.scheduler_loop` at each 14:00 / 21:00 Helsinki tick
- `POST /api/track/run-all?notify=true` (manual)
- `POST /api/admin/run` with `notify:true` (password-protected)
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
| `ANTHROPIC_BASE_URL` | yes      | Anthropic-compatible proxy URL, e.g. `https://cc-vibe.com` |
| `ANTHROPIC_AUTH_TOKEN`| yes     | Proxy bearer token for Claude Opus 4.8 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | no | `1` recommended with the proxy |
| `ANTHROPIC_MODEL`    | no       | Defaults to `claude-opus-4-8` |
| `ANTHROPIC_NEWS_MODEL` | no     | Defaults to `ANTHROPIC_MODEL` |
| `CORS_ORIGINS`       | no       | defaults to `*` |
| `ADMIN_TOKEN`        | optional | enables `POST /api/admin/run` (unset → 503). Constant-time compared to body `password` / `X-Admin-Token` header |
| `NEWS_WATCH_SECONDS` | optional | news-watcher poll interval, default `1800`; `0` disables auto AI re-run on new news |
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
              Installs requirements.txt
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
- `data_sources` field is `null | {tracker_captures, combined_points, source:"live_scrape_only"}`
- `methods.ai_llm.model` is the actual model id string (`claude-opus-4-8`) — `lib/modelName.js` converts it to display label

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
| Anthropic proxy env missing                           | Add `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` to Railway          |
| `pydantic_core` version mismatch with `pydantic`      | requirements.txt pins both (`pydantic==2.6.4`, `pydantic_core==2.16.3`) |
| Non-ASCII chars in `Title:` HTTP header               | ntfy publish would 500 with UnicodeEncodeError; use ASCII-only title  |
| CRA bakes env vars at **build** time                  | Changing REACT_APP_BACKEND_URL needs a Vercel redeploy, not a refresh |
| **NO synthetic/Statfin data** — all removed            | Use only live `daily_tracker` captures + live snapshot; never reintroduce interpolation/extrapolation/factor-scaling |
| `_id` field is `ObjectId` — not JSON serializable     | Always `.find(..., {"_id": 0})` or strip it                           |
| `datetime.utcnow()`                                   | Use `datetime.now(timezone.utc)` instead                              |
| UI shows stale prediction / `fundamenttiankkuri —`    | UI only reads `/predict/latest`; force a fresh run (`/api/admin/run` action `all`, or a 14:00/21:00 capture) |
| Cold start: <few daily points                          | `predict_tomorrow` degrades gracefully (fundamental_anchor off live anchor); do NOT add a points-gate that hides methods |
| `daily_tracker` legacy unique index `(fuel,region,date)` | startup explicitly drops it before adding the hour-aware one        |
| Vercel framework auto-detected as "services"          | Override to "Create React App" in Project Settings; root = `frontend` |

## 15. How to do common things

### Add a new fuel
1. `server.py` — add to `FUELS` tuple
2. `scrapers/polttoaine.py` + `scrapers/tankille.py` — add mapping
3. `frontend/src/components/FuelToggle.jsx` — add button
4. `frontend/src/App.js` — adjust hero & fuel-list rendering
   (no statfin/simulate steps — those modules are gone)

### Add a new region/city
1. `server.py:SUPPORTED_REGIONS` — add
2. `scrapers/tankille.py:CITIES` — add per-city URL slug
3. `tracker.py:TRACKED_CITIES` + `CityAverageChart.jsx:CITIES` — add for
   per-city capture (`by_city`) and the all-cities chart line
4. `frontend/src/components/RegionalGrid.jsx` — auto-renders from API

### Tune the prediction
1. `predict.py:ensemble()` weights (two regimes: ≥14 daily pts vs thin)
2. `predict.py:fundamental_anchor()` — uncalibrated priors (see module
   constants `_BRENT_PASSTHROUGH_FRAC = 0.25`, `_REFINED_PASSTHROUGH_FRAC =
   0.30`, hard-coded weekday-prior ±0.004), momentum/crude clamps,
   `_MAX_DAILY_MOVE` (0.06 €/L; expanded by tax step when applicable).
   None of these are Finland-measured — replace with data-calibrated
   coefficients once captures accumulate.
3. `predict.py:moving_average(window=…)` / `linear_regression(lookback=…)`
4. `predict.py:ai_llm_predict.system_message` — 9 numbered priors (all
   explicitly labelled as uncalibrated; no fabricated tenure / specific
   Finland-unmeasured day-counts or c/L bands)
5. `predict.py:ai_llm_predict.models_to_try` — fallback chain
6. `tracker.py:SCHEDULED_HOURS` — capture times; `NEWS_WATCH_SECONDS` env

### Trigger a capture / fresh prediction manually
```bash
# scheduled-style capture (both fuels) + ntfy
curl -X POST "$BACKEND_URL/api/track/run-all?notify=true"
# password-protected admin trigger (capture + fresh predict + notify)
curl -X POST "$BACKEND_URL/api/admin/run" -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_TOKEN>","action":"all","fuel":"all","notify":true}'
# standalone script (from backend/, needs .env)
python capture_now.py            # or: python purge_captures.py --yes
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

## 16. Current state (updated 2026-05-16, post-overhaul)

**Architecture / data**:
- ✅ Tilastokeskus (Statfin) **removed**; `statfin.py`, `simulate.py`,
  `real_history.py` **deleted**. No synthetic/interpolated/extrapolated data.
- ✅ All data live-gathered from today onward (`daily_tracker` captures + live
  snapshots). `history` purged of modeled rows. `/api/seed` is a no-op purge.
- ✅ `/api/accuracy` scores only vs real `daily_tracker` captures.
- ✅ Per-city cheapest **+ average** persisted in `daily_tracker.by_city`.

**Prediction**:
- ✅ Date-aware MA/LR/ES (project +1 calendar day, daily-tail), new
  `fundamental_anchor` (live + Brent-EUR pass-through + weekday + momentum),
  data-quality-aware ensemble clamped ±0.06 €/L, Brent/FX `change_frac`.
- ✅ Geopolitics principle in the AI system message; conflict keyword scan; AI handles
  forward risk, Brent handles already-priced risk.
- ✅ `tracker.capture_daily` always runs full `predict_tomorrow` (the old
  `<7 pts → AI-only` cold-start branch that hid `fundamental_anchor` is gone).
- ✅ News-watcher (`news_watch_loop`) auto-reruns AI/prediction on new
  fuel-news (rate-limited; `NEWS_WATCH_SECONDS`, needs `ANTHROPIC_AUTH_TOKEN`).

**Ops / UI**:
- ✅ Capture times **14:00 + 21:00 Helsinki** (`SCHEDULED_HOURS`).
- ✅ `POST /api/admin/run` password-protected manual trigger (`ADMIN_TOKEN`).
- ✅ Standalone `capture_now.py` (manual capture) + `purge_captures.py`
  (delete rows, dry-run unless `--yes`).
- ✅ Dark theme, **default dark**, header toggle, no-FOUC; `CityAverageChart`
  (all-cities avg + market-move projection) below the cheapest chart.

**Pending user action** (agent cannot push):
1. "Save to GitHub" → Vercel + Railway redeploy (all above is code-complete
   locally; production still runs the old code until then).
2. Set Railway env: `ADMIN_TOKEN` (+ optional `NEWS_WATCH_SECONDS`); confirm
   `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `NTFY_*` still set.
3. After deploy, trigger one fresh prediction (`/api/admin/run` action
   `all`, or wait for 14:00/21:00) so the UI shows `fundamental_anchor`.

**Known cold-start note**: per-city `by_city` and the all-cities chart only
populate from captures taken AFTER deploy; there is NO real backed source for
historical per-city data and none is fabricated.

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
