# BensaVahti Engineering Guide

## Product

BensaVahti is a Finnish fuel-price dashboard. It:

1. Scrapes live 95E10 and diesel prices from `tankille.fi` and
   `polttoaine.net`.
2. Predicts tomorrow's national minimum with five methods: moving average,
   weighted linear regression, Holt smoothing, a fundamental anchor, and an
   LLM news estimate.
3. Captures actual prices at 14:00 and 21:00 Helsinki time.
4. Publishes optional ntfy summaries and tracks realized forecast accuracy.

Only live-scraped prices are valid model input. Do not add synthetic or
Statfin history.

## Architecture

```text
frontend/                         React dashboard, deployed on Vercel
  src/App.js                      Page orchestration and data loading
  src/components/                 Rendered dashboard components
  src/lib/api.js                  Backend GET contract wrappers

backend/                          FastAPI service, deployed on Railway
  server.py                       Public reads and authenticated admin routes
  tracker.py                      14:00/21:00 scheduler and news watcher
  predict.py                      Five prediction methods and ensemble
  accuracy_utils.py / learn.py    Realized-error and calibration helpers
  factors.py                      Brent, EUR/USD, and refined products
  news.py                         Direct publisher RSS aggregation
  notify.py                       ntfy publisher
  validation.py                  Shared scrape validation
  scrapers/                       Production scraper implementations
  tests/                          Collected pytest suite
```

MongoDB collections:

- `daily_tracker`: scheduled actuals and their next-day predictions
- `predictions`: latest persisted prediction returned to the dashboard
- `snapshots`: latest live scrape fallback
- `history`: daily chart points
- `admin_audit_log` and `failed_auth_attempts`: admin security records

## API

Public reads:

- `GET /api/health`
- `GET /api/prices/current?fuel=95E10`
- `GET /api/prices/history?fuel=95E10&region=Suomi&days=90`
- `GET /api/factors`
- `GET /api/news`
- `GET /api/predict/latest?fuel=95E10&region=Suomi`
- `GET /api/regional?fuel=95E10`
- `GET /api/accuracy?fuel=95E10&region=Suomi&days=30`
- `GET /api/track/history?fuel=95E10&days=90`

Authenticated operations:

- `POST /api/admin/run` with `X-Admin-Token`
- `POST /api/admin/fix-capture` with `X-Admin-Token`

`/api/admin/run` actions are `ping`, `capture`, `predict`, `all`, and
`notify`. Keep expensive or mutating operations behind this route.

## Prediction Rules

- Target: tomorrow's national cheapest station price.
- Truth source: latest daily `actual_cheapest` capture.
- Live anchor: latest snapshot `national_min`.
- Ensemble inputs: MA, LR, Holt, fundamental anchor, AI.
- Calibration: realized MAE and signed bias from `daily_tracker` and
  `predictions`.
- Deterministic events: Finnish holidays and known tax changes.
- Breaking-news severity may widen the normal daily movement clamp.

Do not add unmeasured hourly offsets, weather/traffic coefficients, or another
prediction method without a measured accuracy improvement.

## Scheduler

`tracker.scheduler_loop` runs at `SCHEDULED_HOURS = (14, 21)` in
`Europe/Helsinki`. Each run:

1. Scrapes both sources.
2. Validates the national minimum.
3. Stores one `daily_tracker` row per fuel and slot.
4. Runs the next-day prediction.
5. Publishes one ntfy summary when configured.

`news_watch_loop` can rerun persisted predictions when relevant headlines
change. Disable it with `NEWS_WATCH_SECONDS=0`.

## Environment

Backend required:

- `MONGO_URL`
- `DB_NAME`

Backend optional:

- `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `ADMIN_TOKEN`
- `CORS_ORIGINS`
- `NTFY_SERVER`, `NTFY_TOPIC`, `NTFY_TOKEN`, `NTFY_CLICK_URL`
- `NEWS_WATCH_SECONDS`
- `ENABLE_HINTATUTKA_EXPERIMENTAL`

Frontend:

- `REACT_APP_BACKEND_URL`

Never commit environment files or credentials.

## Commands

Backend:

```bash
cd backend
python -m pytest -q
uvicorn server:app --reload --port 8000
```

Frontend:

```bash
cd frontend
yarn test --watchAll=false
yarn build
yarn start
```

Manual authenticated run:

```bash
curl -X POST "$BACKEND/api/admin/run" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"all","fuel":"all","region":"Suomi","notify":true}'
```

## Change Rules

- Preserve the `95E10` and lowercase `diesel` identifiers.
- Keep public GET routes free of new destructive behavior.
- Reuse `validation.validate_scraped_data` for scrape filtering.
- Update backend and frontend contracts together.
- Add one focused test for non-trivial prediction, validation, scheduler, or
  money/security changes.
- Do not commit generated builds, test output, local agent state, or dependency
  caches.
