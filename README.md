# BensaVahti

Live Finnish 95E10 and diesel prices, next-day forecasts, regional comparison,
and realized accuracy tracking.

## Development

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# frontend
cd frontend
yarn install
yarn start
```

Set `MONGO_URL` and `DB_NAME` for the backend, and
`REACT_APP_BACKEND_URL=http://localhost:8000` for the frontend.

Run checks with `python -m pytest -q` in `backend/` and
`yarn test --watchAll=false && yarn build` in `frontend/`.
