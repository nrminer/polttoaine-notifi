# Deploying the BensaVahti frontend to Vercel

The React frontend (located in `/frontend`) is now Vercel-ready.
The Python FastAPI backend is **not** deployed to Vercel — it must stay on a
Python-capable host (Emergent, Render, Railway, Fly.io, etc.). The frontend
talks to that backend through the `REACT_APP_BACKEND_URL` environment variable.

---

## 1. Files that were added

| File | Purpose |
| --- | --- |
| `frontend/vercel.json` | Tells Vercel how to build the CRA app, sets SPA rewrites and asset caching headers. |
| `frontend/.vercelignore` | Keeps `node_modules`, local builds and local `.env` files out of the upload. |
| `frontend/.env.example` | Documents the only env var the frontend needs at build time. |

No application code was changed. All API calls already go through
`process.env.REACT_APP_BACKEND_URL` (see `frontend/src/lib/api.js`).

---

## 2. One-time setup on Vercel

1. Push your repo to GitHub / GitLab / Bitbucket (use Emergent's **Save to GitHub**
   button in the chat input).
2. In Vercel, click **Add New → Project** and import the repository.
3. **Root Directory**: set this to **`frontend`** (very important — the React app
   lives in the `frontend/` subfolder, not at the repo root).
4. Framework Preset: Vercel will auto-detect **Create React App**. Leave the
   build/install commands at their defaults — `vercel.json` already specifies:
   - Install: `yarn install`
   - Build: `yarn build`
   - Output: `build`
5. **Environment Variables** → add:
   - `REACT_APP_BACKEND_URL` = `https://<your-backend-public-url>`
     (no trailing slash). The frontend appends `/api/...` to this URL.
6. Click **Deploy**.

---

## 3. Backend requirements

Your backend is still required for the app to function. It must:

- Be reachable on the public URL you set in `REACT_APP_BACKEND_URL`.
- Serve all routes under the `/api` prefix (this is how the frontend calls it).
- Allow CORS from your Vercel domain
  (e.g. `https://your-app.vercel.app` and any custom domain you add).

Example FastAPI CORS snippet (already present in most Emergent backends):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-app.vercel.app",
        "https://your-custom-domain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

If you want the backend to stay on Emergent, keep using the
`https://<your-app>.preview.emergentagent.com` URL (or the production URL after
you deploy via Emergent) as `REACT_APP_BACKEND_URL` in Vercel.

---

## 4. Redeploys & previews

- Pushing to the default branch → production deploy.
- Pushing to any other branch / PR → automatic preview deploy with its own URL.
- Environment variables can be scoped per environment (Production / Preview /
  Development) inside the Vercel dashboard.

---

## 5. Local sanity check (optional)

```bash
cd frontend
yarn install
REACT_APP_BACKEND_URL=https://<your-backend-public-url> yarn build
npx serve -s build
```

If `yarn build` succeeds locally, the Vercel build will succeed too.

---

## 6. Notes / gotchas

- **Do not** put the backend `/api` routes in `vercel.json` rewrites — the
  backend is hosted elsewhere; the frontend calls it directly over HTTPS.
- `WDS_SOCKET_PORT=443` in `.env` only affects the dev server; Vercel ignores
  it for production builds. You can leave it in or remove it.
- Vercel injects env vars at **build time** for CRA, so any change to
  `REACT_APP_BACKEND_URL` requires a redeploy (click **Redeploy** in Vercel).
- Emergent's native one-click deploy still works for the full stack
  (frontend + backend + MongoDB). Choose Vercel only if you specifically want
  frontend hosting there.
