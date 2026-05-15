"""BensaVahti backend API tests.

Covers all endpoints in /app/backend/server.py:
- health, meta, seed
- prices/current, prices/history
- factors
- predict/run, predict/latest
- regional, accuracy
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://serverless-app-2.preview.emergentagent.com").rstrip("/")

EXPECTED_FUELS = {"95E10", "diesel"}
EXPECTED_REGIONS = {"Helsinki", "Espoo", "Vantaa", "Tampere", "Turku",
                    "Oulu", "Jyväskylä", "Kuopio", "Lahti", "Suomi"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ----------- health & meta -----------

def test_health(s):
    r = s.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("service") == "bensavahti"


def test_meta(s):
    r = s.get(f"{BASE_URL}/api/meta", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert set(data["fuels"]) == EXPECTED_FUELS
    assert EXPECTED_REGIONS.issubset(set(data["regions"]))
    assert "city_factors" in data
    assert "baseline" in data


# ----------- seed -----------

def test_seed_idempotent(s):
    # Should return seeded=false because DB already has data
    r = s.post(f"{BASE_URL}/api/seed?days=180&force=false", timeout=60)
    assert r.status_code == 200
    data = r.json()
    # Either seeded=false (already populated) OR seeded=true with rows count
    assert "seeded" in data
    if data["seeded"] is False:
        assert "reason" in data
    else:
        assert data.get("rows", 0) > 0


# ----------- history -----------

def test_history_95E10_30days(s):
    r = s.get(f"{BASE_URL}/api/prices/history?fuel=95E10&region=Suomi&days=30", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["fuel"] == "95E10"
    assert data["region"] == "Suomi"
    rows = data["rows"]
    assert len(rows) >= 20, f"Expected ~30 rows, got {len(rows)}"
    # Validate fields & sorted ascending
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates), "rows must be sorted by date ascending"
    for row in rows[:3]:
        assert set(["date", "price", "fuel", "region", "source"]).issubset(row.keys())
        assert isinstance(row["price"], (int, float))


def test_history_diesel_90days(s):
    r = s.get(f"{BASE_URL}/api/prices/history?fuel=diesel&region=Suomi&days=90", timeout=20)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) >= 60


def test_history_invalid_fuel(s):
    r = s.get(f"{BASE_URL}/api/prices/history?fuel=BOGUS&region=Suomi&days=30", timeout=15)
    assert r.status_code == 400


# ----------- factors -----------

def test_factors(s):
    r = s.get(f"{BASE_URL}/api/factors", timeout=30)
    assert r.status_code == 200
    data = r.json()
    for key in ("brent", "eur_usd"):
        assert key in data
        obj = data[key]
        assert "series" in obj
        assert "latest" in obj
        assert "delta_pct" in obj
        assert "unit" in obj
        assert isinstance(obj["series"], list)


# ----------- predict/latest (should exist already per problem statement) -----------

def test_predict_latest_95E10(s):
    r = s.get(f"{BASE_URL}/api/predict/latest?fuel=95E10&region=Suomi", timeout=15)
    assert r.status_code == 200
    data = r.json()
    if not data.get("available"):
        pytest.skip("No prediction stored yet; run prediction first")
    assert data["fuel"] == "95E10"
    assert data["region"] == "Suomi"
    assert "target_date" in data
    assert "methods" in data
    assert "ensemble" in data
    # ensemble value
    assert data["ensemble"].get("value") is not None


def test_predict_latest_diesel(s):
    r = s.get(f"{BASE_URL}/api/predict/latest?fuel=diesel&region=Suomi", timeout=15)
    assert r.status_code == 200


# ----------- regional -----------

def test_regional_95E10(s):
    r = s.get(f"{BASE_URL}/api/regional?fuel=95E10", timeout=20)
    assert r.status_code == 200
    data = r.json()
    rows = data["rows"]
    assert len(rows) >= 8  # 9 cities expected (excluding Suomi)
    regions_in_rows = {row["region"] for row in rows}
    assert "Suomi" not in regions_in_rows
    # Sorted cheapest first
    prices = [row["price"] for row in rows]
    assert prices == sorted(prices), "regional must be sorted ascending"
    for row in rows[:3]:
        assert set(["region", "price", "date", "delta", "source"]).issubset(row.keys())


def test_regional_diesel(s):
    r = s.get(f"{BASE_URL}/api/regional?fuel=diesel", timeout=20)
    assert r.status_code == 200
    assert len(r.json()["rows"]) >= 8


# ----------- accuracy -----------

def test_accuracy(s):
    r = s.get(f"{BASE_URL}/api/accuracy?fuel=95E10&region=Suomi&days=30", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert "summary" in data
    # summary has expected method keys
    for method in ("moving_average", "linear_regression", "exp_smoothing", "ai_llm", "ensemble"):
        assert method in data["summary"]


# ----------- prices/current (slow - scrapes external) -----------

def test_current_prices_95E10(s):
    """May take 15-30s due to scraping; allow long timeout."""
    r = s.get(f"{BASE_URL}/api/prices/current?fuel=95E10", timeout=60)
    assert r.status_code == 200, f"current returned {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert data["fuel"] == "95E10"
    assert "national_avg" in data
    assert "national_min" in data
    assert "stations_count" in data
    assert "by_city" in data
    assert "stations" in data
    if not data.get("stale"):
        # Live scrape should have >0 stations
        assert data["stations_count"] > 0
        assert isinstance(data["national_avg"], (int, float))


# ----------- predict/run (slow - includes LLM) -----------

def test_predict_run_95E10(s):
    """Runs all 4 algorithms + ensemble; can take 5-30s due to AI call."""
    r = s.post(f"{BASE_URL}/api/predict/run",
               json={"fuel": "95E10", "region": "Suomi"}, timeout=120)
    assert r.status_code == 200, f"predict/run failed: {r.text[:300]}"
    data = r.json()
    assert data["fuel"] == "95E10"
    assert "methods" in data
    for m in ("moving_average", "linear_regression", "exp_smoothing", "ai_llm"):
        assert m in data["methods"], f"missing method {m}"
        # value can be None for ai_llm if LLM fails; statistical ones must produce value
        if m != "ai_llm":
            assert data["methods"][m].get("value") is not None, f"{m} returned no value"
    assert "ensemble" in data
    assert data["ensemble"].get("value") is not None
    assert "target_date" in data


def test_predict_latest_after_run(s):
    """Verify the prediction we just ran is now in /predict/latest."""
    # tiny delay to allow upsert
    time.sleep(1)
    r = s.get(f"{BASE_URL}/api/predict/latest?fuel=95E10&region=Suomi", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("available") is True
    assert "ai_llm" in data.get("methods", {})
    # ai_llm should have explanation if available
    ai = data["methods"]["ai_llm"]
    assert "explanation" in ai


def test_predict_run_invalid_fuel(s):
    r = s.post(f"{BASE_URL}/api/predict/run",
               json={"fuel": "BOGUS", "region": "Suomi"}, timeout=20)
    assert r.status_code == 400
