# BensaVahti — Suomen polttoainehintojen ennustaja

## Original Problem Statement
> "Make an algorithm for finnish gas prizes octane 95 and diesel try to analyze everything to predict tomorrows gas prices"

Full-stack dashboard, in Finnish, that predicts tomorrow's 95E10 and diesel prices in Finland using 4 algorithms in parallel + AI commentary.

## User Choices (Iteration 1)
- **Data sources**: web scraping (polttoaine.net + tankille.fi) + simulated historical data (since real historical data isn't available)
- **Variables**: historical prices + Brent crude oil (USD/bbl) + EUR/USD exchange rate + weekday/seasonal trends + AI analysis
- **Prediction methods**: all four in parallel + ensemble comparison
- **UI**: full dashboard with regional comparison
- **AI**: Emergent LLM key — Claude Sonnet 4.5 (with claude-haiku-4-5 fallback)

## Architecture
- **Backend**: FastAPI (Python 3.11) on :8001
  - `server.py` — REST API (10 endpoints under `/api`)
  - `predict.py` — 4 algorithms: moving average, linear regression, Holt exponential smoothing, AI/LLM
  - `factors.py` — Yahoo Finance fetcher (no key) for Brent + EUR/USD
  - `simulate.py` — generates 180-day plausible Finnish history (calibrated to current scrape if available)
  - `scrapers/polttoaine.py`, `scrapers/tankille.py`, `scrapers/bensahinta.py` — reused from original CLI app
- **Frontend**: React 18 + Tailwind + recharts + framer-motion on :3000
  - Single-page dashboard (`App.js`) with composable cards
  - Design: Nordic Industrial Tech (Cabinet Grotesk + IBM Plex Sans + JetBrains Mono, IKB blue + Marimekko yellow accent)
- **DB**: MongoDB
  - `history` (fuel, region, date, price, source) — unique on (fuel, region, date)
  - `predictions` (target_date, fuel, region, methods, ensemble, current_price, brent, eur_usd)
  - `snapshots` (timestamped scrape results)

## API Surface (all under `/api`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/meta` | Static config (fuels, regions, baseline) |
| POST | `/seed?days=180` | Seed simulated history (idempotent) |
| GET | `/prices/current?fuel=` | Scrape + return today's national avg/min + by-city + sample stations |
| GET | `/prices/history?fuel=&region=&days=` | Historical price series |
| GET | `/factors` | Brent + EUR/USD (60-day series) |
| POST | `/predict/run` | Run all 4 algorithms + AI, save prediction |
| GET | `/predict/latest` | Last saved prediction (full structure) |
| GET | `/regional?fuel=` | Latest price per region, sorted cheapest first |
| GET | `/accuracy?fuel=&region=&days=` | MAE + ≤1¢ accuracy per method |

## What's Been Implemented (Iteration 1 · 2026-05-15)
- ✅ Backend with 10 endpoints, MongoDB persistence, unique indexes
- ✅ 4 prediction algorithms + weighted ensemble
- ✅ AI/LLM prediction (Claude Sonnet 4.5 with Haiku fallback, 3 retries each)
- ✅ Yahoo Finance Brent + EUR/USD live fetcher
- ✅ Simulated 180-day history seeder (auto-calibrates to current scrape)
- ✅ Frontend dashboard with: hero today's price, large tomorrow's prediction card, history chart with recharts, method comparison table, AI analysis panel (dark with grain overlay), regional grid (9 cities), influencing factors card, accuracy tracker
- ✅ Finnish-language UI throughout
- ✅ Cohesive "Nordic Industrial Tech" design (Cabinet Grotesk + IBM Plex Sans + JetBrains Mono, sharp corners, no purple gradients)
- ✅ data-testid on every interactive/data element
- ✅ 100% pass rate on backend + frontend tests (testing_agent_v3 iteration 1)

## Backlog / Future Enhancements
### P1
- [ ] Background scheduler that runs `/predict/run` daily at 06:00 EET and stores predictions automatically
- [ ] Email/ntfy notifications when tomorrow's prediction crosses a user-set threshold
- [ ] Region-level predictions (per-city ensemble, not just "Suomi")
- [ ] Cache `/api/prices/current` results for 60s to reduce scraping load

### P2
- [ ] Historical accuracy chart (line chart of MAE over time per method)
- [ ] Brand-station comparison (Neste vs ABC vs Teboil vs Shell)
- [ ] Save user "home city" in localStorage and surface its prediction in hero
- [ ] Export predictions as ICS calendar so user gets a reminder when prices are predicted to drop
- [ ] Add Bayesian/state-space model as 5th algorithm

### P3
- [ ] Dark mode toggle
- [ ] Mobile-optimized regional grid (2-column)
- [ ] Public sharable prediction snapshot URLs (e.g. /share/2026-05-16)

## Personas
- **Power-commuting Finn** — drives daily, wants to know if they should fill up today or tomorrow
- **Logistics operator** — needs MAE/accuracy stats to evaluate algorithm trust
- **Energy market hobbyist** — appreciates seeing 4 algorithms head-to-head with AI commentary

## Known Limitations
- "National average" is biased toward the top-20 cheapest stations (only data source available)
- Historical data is simulated for the regions where scraping didn't happen today (Tampere/Turku/Oulu/Jyväskylä/Kuopio/Lahti) — the simulated values calibrate to current scrape but aren't actual market history
- AI key (Emergent Universal LLM Key) has a budget; persistent failures will fall back to Haiku and then return a null AI prediction (other 3 algorithms still produce ensemble)
