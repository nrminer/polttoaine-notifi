"""Tests for the day-ahead tuning of linear_regression and fundamental_anchor.

Both methods showed the weakest realized accuracy in daily_tracker
comparisons. The fixes under test:
  - linear_regression: recent-window cap + exponential recency weighting,
    self-training bias correction, clamp to ±_MAX_DAILY_MOVE of the last
    observation
  - fundamental_anchor: noise-damped anchor (live blended with 3-day
    median), momentum shrinkage, RMSE-calibrated confidence band
"""
import asyncio
from datetime import date, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import predict


def _daily_series(values, end="2026-06-10"):
    """Consecutive daily (dates, prices) ending at `end`."""
    end_d = date.fromisoformat(end)
    n = len(values)
    dates = [(end_d - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    return dates, list(values)


# ---------------- linear_regression ----------------

def test_lr_recent_regime_dominates_over_old_trend():
    # 20 days of steep climb, then 10 flat days at 1.700. An equal-weight
    # fit over all 30 points projects the old climb into tomorrow; the
    # recency-weighted recent window must stay near the flat level.
    old = [1.50 + 0.01 * i for i in range(20)]   # ends 1.69
    recent = [1.700] * 10
    dates, prices = _daily_series(old + recent)

    out = predict.linear_regression(prices, 30, dates=dates)

    assert out["value"] is not None
    assert abs(out["value"] - 1.700) < 0.012


def test_lr_clamped_to_daily_move_budget():
    # Implausibly steep tail (+5 snt/day): extrapolation must not exceed
    # the physical daily move budget from the last observation.
    vals = [1.50 + 0.05 * i for i in range(10)]  # ends 1.95
    dates, prices = _daily_series(vals)

    out = predict.linear_regression(prices, 30, dates=dates)

    assert out["value"] <= vals[-1] + predict._MAX_DAILY_MOVE + 1e-9


def test_lr_bias_correction_applied_with_sufficient_n():
    vals = [1.700] * 12
    dates, prices = _daily_series(vals)
    stats = {"linear_regression": {"n": 25, "bias": 0.015, "mae": 0.02}}

    base = predict.linear_regression(prices, 30, dates=dates)
    corrected = predict.linear_regression(prices, 30, dates=dates,
                                          track_stats=stats)

    # full positive bias subtracted at n >= _BIAS_FULL_N
    assert abs((base["value"] - corrected["value"]) - 0.015) < 1e-6


def test_lr_bias_correction_skipped_with_small_n():
    vals = [1.700] * 12
    dates, prices = _daily_series(vals)
    stats = {"linear_regression": {"n": 3, "bias": 0.015, "mae": 0.02}}

    base = predict.linear_regression(prices, 30, dates=dates)
    corrected = predict.linear_regression(prices, 30, dates=dates,
                                          track_stats=stats)

    assert base["value"] == corrected["value"]


def test_lr_too_little_data_returns_none():
    out = predict.linear_regression([1.7, 1.71], 30)
    assert out["value"] is None


# ---------------- fundamental_anchor ----------------

def _fa(dates, prices, live, **kw):
    kw.setdefault("tomorrow_weekday", 3)  # torstai → ei viikonpäivpriora
    return predict.fundamental_anchor(
        dates, prices, live,
        brent=None, eur_usd=None, brent_chg=None, eur_usd_chg=None, **kw
    )


def test_fa_damps_single_scrape_spike():
    # Flat 1.700 history; today's live scrape spikes to 1.760. The damped
    # anchor must pull the base below the raw live value.
    vals = [1.700] * 9 + [1.760]  # last = live (predict_tomorrow semantics)
    dates, prices = _daily_series(vals)

    out = _fa(dates, prices, 1.760)

    assert out["value"] is not None
    assert out["value"] < 1.755
    assert out["value"] >= 1.700


def test_fa_momentum_is_shrunk():
    # Clean +1 snt/day trend → raw 7-day slope = 0.010. With shrinkage the
    # momentum term is _MOM_SHRINK * 0.010. Base equals live here because
    # the 3-day median sits on the same trend line midpoint... compute
    # expected explicitly instead.
    vals = [1.700 + 0.010 * i for i in range(10)]  # ends 1.790
    dates, prices = _daily_series(vals)
    live = vals[-1]

    out = _fa(dates, prices, live)

    med3 = sorted(vals[-3:])[1]
    base = predict._ANCHOR_LIVE_W * live + (1 - predict._ANCHOR_LIVE_W) * med3
    expected = base + predict._MOM_SHRINK * 0.010
    assert abs(out["value"] - expected) < 1e-4
    # unshrunk momentum would land a clear 0.5 snt higher
    assert out["value"] < base + 0.010 - 0.004


def test_fa_band_calibrated_from_realized_rmse():
    vals = [1.700] * 10
    dates, prices = _daily_series(vals)
    stats = {"fundamental_anchor": {"n": 20, "rmse": 0.030, "bias": 0.0,
                                    "mae": 0.025}}

    out = _fa(dates, prices, 1.700, track_stats=stats)

    band = out["confidence_high"] - out["value"]
    assert abs(band - 0.030) < 1e-6


def test_fa_band_prior_without_track_record():
    vals = [1.700] * 10
    dates, prices = _daily_series(vals)

    out = _fa(dates, prices, 1.700)

    band = out["confidence_high"] - out["value"]
    assert abs(band - 0.012) < 1e-6


def test_fa_band_capped():
    vals = [1.700] * 10
    dates, prices = _daily_series(vals)
    stats = {"fundamental_anchor": {"n": 20, "rmse": 0.090, "bias": 0.0,
                                    "mae": 0.080}}

    out = _fa(dates, prices, 1.700, track_stats=stats)

    band = out["confidence_high"] - out["value"]
    assert abs(band - predict._FA_BAND_MAX) < 1e-6


def test_persistence_is_production_champion(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    dates, prices = _daily_series([1.70, 1.71, 1.69, 1.68])

    result = asyncio.run(predict.predict_tomorrow(
        "95E10", dates, prices, brent=None, eur_usd=None,
        live_today_price=1.68,
        target_date_iso="2026-06-11",
    ))

    assert result["methods"]["persistence"]["value"] == 1.68
    assert result["ensemble"]["value"] == 1.68
    assert result["challenger_ensemble"]["value"] is not None
