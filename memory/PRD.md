# BensaVahti — Product Requirements Document

## Original problem statement
"make this app vercel compatible" → expanded into a full split-stack deployment:
React frontend on **Vercel**, FastAPI backend on **Railway**, MongoDB on
**MongoDB Atlas**.

## Architecture
| Layer | Host | URL |
| --- | --- | --- |
| Frontend (CRA) | Vercel | `https://polttoaine-notifi.vercel.app` |
| Backend (FastAPI) | Railway | `https://polttoaine-notifi-production.up.railway.app` |
| Database | MongoDB Atlas (free M0) | mongodb+srv://… |

## Tech stack
- Frontend: React 18, Create React App, Tailwind CSS, Framer Motion, Recharts, axios
- Backend: FastAPI 0.110, Uvicorn, Motor (async MongoDB), Pydantic 2.6
- AI: Claude Fable 5 with extended thinking (10k token reasoning budget) via an Anthropic-compatible proxy (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`), fallback chain to Claude Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.5, and Haiku 4.5
- Scrapers: polttoaine.net + tankille.fi (live, ≤24h)
- Market data: Yahoo Finance (Brent, EUR/USD)

## Core requirements (locked)
1. Show today's cheapest 95E10 / diesel price across Finland
2. Predict tomorrow's price using 5 parallel methods + ensemble
3. Track prediction-vs-actual over time (capture at 14:00 + 21:00 Helsinki)
4. Display regional prices (Helsinki, Espoo, Vantaa, Tampere, Turku, Lahti)
5. News feed about fuel price drivers
6. Brent + EUR/USD as context factors

## What's been implemented (2026-05-16)
- ✅ Split-stack deployment to Vercel + Railway + Atlas — all green
- ✅ Frontend Vercel config: `frontend/vercel.json`, `.vercelignore`, `.env.example`
- ✅ Backend Railway config: `backend/Procfile`, `backend/railway.json`, `backend/.python-version`
- ✅ Documented in `/app/VERCEL_DEPLOYMENT.md` and `/app/RAILWAY_DEPLOYMENT.md`
- ✅ Fixed `pydantic_core==2.16.3` pin to match `pydantic==2.6.4`
- ✅ Bootstrapped fresh MongoDB on Atlas:
  - Seeded 3,595 history rows (180 days × 2 fuels)
  - Generated initial predictions for 95E10 and diesel
  - Captured first tracking data point (2026-05-16)
- ✅ Verified end-to-end: 9 API calls returning 200, dashboard renders with real numbers
  (Today 1.857 €/L, Tomorrow 1.858 €/L)

## Required environment variables
### Vercel (frontend)
- `REACT_APP_BACKEND_URL` = Railway public URL (no trailing slash)

### Railway (backend)
- `MONGO_URL` = Atlas connection string
- `DB_NAME` = bensavahti
- `ANTHROPIC_BASE_URL` = Anthropic-compatible proxy URL (for example `https://cc-vibe.com`)
- `ANTHROPIC_AUTH_TOKEN` = proxy auth token (for Claude Fable 5 fallback chain)
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` = `1` (recommended with the proxy)

## Prioritized backlog
### P0 (next session if needed)
- None — production is fully working.

### P1 (recommended polish)
- Add custom domain on Vercel (e.g. `bensavahti.fi`) → update CORS allow-list
  on backend (tighten from `*` to specific origin)
- Schedule the 06:00 + 20:00 capture as a real cron (Railway has cron jobs via
  separate worker service, or use GitHub Actions / Upstash QStash)
- Add a `/api/health` endpoint distinct from `/api/factors` for healthchecks
- Persist Vercel preview URLs in CORS allow-list (currently wildcard)

### P2 (nice to have)
- Migrate from CRA to Vite (smaller bundle, faster local dev)
- Add monitoring / error tracking (Sentry on both ends)
- Server-side cache (Redis) for the regional aggregate endpoint
- Email/SMS alerts when tomorrow's predicted price drops below a user's
  threshold (would require auth — see "monetization" below)

## Monetization / engagement enhancement idea
The app is genuinely useful (Finnish drivers care about fuel prices), but
right now it's purely read-only. Possible upgrade paths:
1. **Free SMS / email alert when price drops** — capture a thresholds list,
   send a daily push when tomorrow's prediction < threshold. Brings users back
   daily and creates an email list.
2. **Premium feature: per-station alerts** — power users would happily pay
   €2/month to get alerts for their commuting route's specific stations.
3. **Affiliate links to ABC / Neste / St1 fuel apps** — small commission per
   install.
