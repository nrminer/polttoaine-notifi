# Deploying the BensaVahti backend to Railway

The FastAPI backend (in `/backend`) is now Railway-ready. Pair it with the
Vercel frontend by setting `REACT_APP_BACKEND_URL` in Vercel to the public URL
Railway gives you (e.g. `https://your-service.up.railway.app`).

---

## 1. Files added for Railway

| File | Purpose |
| --- | --- |
| `backend/Procfile` | Tells Railpack the start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`. Fixes the "No start command detected" error. |
| `backend/railway.json` | Explicit Railway config: pip install + start command + healthcheck at `/api/factors`. |
| `backend/.python-version` | Pins Python 3.11 (matches local). |

---

## 2. Railway project setup (one-time)

1. Go to **https://railway.com** → **New Project** → **Deploy from GitHub repo**.
2. Pick your repo.
3. After import, open the service → **Settings** tab.
4. **Root Directory** → set to **`backend`** ⚠️ critical (otherwise Railway looks at the repo root and finds the frontend instead).
5. **Build** → should auto-detect Railpack + Python. The `Procfile` and `railway.json` will be picked up automatically.
6. **Networking** → click **Generate Domain**. You'll get something like
   `https://bensavahti-backend-production.up.railway.app`. Copy this URL.

---

## 3. Environment variables to add on Railway

Open the service → **Variables** tab → add these:

| Key | Value | Required? |
| --- | --- | --- |
| `MONGO_URL` | Your MongoDB Atlas connection string (see step 4) | ✅ yes |
| `DB_NAME` | `bensavahti` (or any name you choose) | ✅ yes |
| `ANTHROPIC_BASE_URL` | `https://cc-vibe.com` | ✅ yes (AI predictions use the proxy) |
| `ANTHROPIC_AUTH_TOKEN` | Your proxy auth token | ✅ yes (AI predictions need it) |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | `1` | recommended for the proxy |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | optional (default) |
| `ANTHROPIC_NEWS_MODEL` | `claude-opus-4-8` | optional (defaults to `ANTHROPIC_MODEL`) |
| `CORS_ORIGINS` | `https://your-app.vercel.app` (or `*` for everything) | optional |
| `PORT` | (Railway sets this automatically — don't override) | n/a |

---

## 4. MongoDB on Railway

Your backend uses MongoDB. Two easy options:

### Option A — MongoDB Atlas (recommended, free 512 MB)
1. Sign up at https://www.mongodb.com/atlas.
2. Create a free **M0** cluster.
3. **Database Access** → add a user (`bensavahti` / strong password).
4. **Network Access** → "Allow access from anywhere" (`0.0.0.0/0`) — Railway IPs are dynamic.
5. **Connect** → **Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://bensavahti:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
6. Paste it into Railway's `MONGO_URL` variable (replace `<password>`).

### Option B — Railway MongoDB plugin
1. In your Railway project → **+ New** → **Database** → **Add MongoDB**.
2. Railway exposes a `MONGO_URL` variable on the DB service. Reference it from the backend service:
   - In backend → Variables → click **+ New Variable** → **Reference** → pick `MongoDB.MONGO_URL`.

---

## 5. Connect the Vercel frontend

Once Railway gives you the backend URL:

1. In **Vercel** → your frontend project → **Settings → Environment Variables**.
2. Edit `REACT_APP_BACKEND_URL` → set to your Railway URL (no trailing slash):
   ```
   https://bensavahti-backend-production.up.railway.app
   ```
3. **Deployments** tab → ⋯ → **Redeploy** (uncheck build cache).

---

## 6. Verify

Once the Railway build is green:

```bash
# Health check
curl https://<your-railway-url>/api/factors

# Real data
curl "https://<your-railway-url>/api/prices/current?fuel=95E10"
```

Both should return JSON with `HTTP 200`. If `/api/factors` is slow on first
call (cold start), that's normal — Railway free tier sleeps services.

---

## 7. Common Railway gotchas

| Error | Fix |
| --- | --- |
| `No start command detected` | Procfile is now in `backend/Procfile`. Make sure **Root Directory = `backend`** in Railway settings. |
| `KeyError: 'MONGO_URL'` | Add `MONGO_URL` and `DB_NAME` env vars on Railway (see step 3). |
| AI prediction says token is missing | Add `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` env vars on Railway, then redeploy. |
| Frontend can't reach backend (CORS) | Backend has `allow_origins=["*"]` so it shouldn't, but if you tighten it, add your Vercel domain. |
| 502 from Railway | Check Logs tab → usually missing env var or backend startup error. |

---

## Cost note

- **Vercel** (frontend): free Hobby tier covers this easily.
- **Railway** (backend): $5/month minimum on the Hobby plan after the free trial.
- **MongoDB Atlas**: free M0 tier is enough for this app.
- **LLM proxy**: billed/limited by the proxy account behind `ANTHROPIC_AUTH_TOKEN`.
