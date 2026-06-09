"""Realized prediction-vs-actual helpers.

All comparisons use real daily_tracker captures as the actual price. The
predictions collection is preferred when available, but daily_tracker is used
as a durable fallback because reboot keeps captures and may clear predictions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_METHODS = (
    "moving_average",
    "linear_regression",
    "exp_smoothing",
    "fundamental_anchor",
    "ai_llm",
    "weekly_cycle",
)


def _parse_date(value: str):
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _method_values_from_prediction_full(
    prediction_full: dict | None,
    methods: tuple[str, ...],
) -> dict[str, float]:
    if not isinstance(prediction_full, dict):
        return {}
    out: dict[str, float] = {}
    raw_methods = prediction_full.get("methods") or {}
    if isinstance(raw_methods, dict):
        for method in methods:
            value = _as_float(raw_methods.get(method))
            if value is not None:
                out[method] = round(value, 4)

    ensemble = _as_float(prediction_full.get("ensemble"))
    if ensemble is not None:
        out["ensemble"] = round(ensemble, 4)
    return out


async def _latest_actuals_by_date(db, fuel: str, region: str, cutoff: str) -> dict[str, dict]:
    rows = await db.daily_tracker.find(
        {
            "fuel": fuel,
            "region": region,
            "date": {"$gte": cutoff},
            "actual_cheapest": {"$ne": None},
        },
        {"_id": 0, "date": 1, "hour": 1, "actual_cheapest": 1},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=800)

    by_date: dict[str, dict] = {}
    for row in rows:
        date = row.get("date")
        if date:
            by_date[date] = row
    return by_date


async def _rows_from_predictions_collection(
    db,
    fuel: str,
    region: str,
    cutoff: str,
    methods: tuple[str, ...],
) -> list[dict]:
    actuals = await _latest_actuals_by_date(db, fuel, region, cutoff)
    preds = await db.predictions.find(
        {"fuel": fuel, "region": region, "target_date": {"$gte": cutoff}},
        {
            "_id": 0,
            "target_date": 1,
            "methods": 1,
            "methods_full": 1,
            "ensemble": 1,
            "ensemble_full": 1,
        },
    ).sort("target_date", 1).to_list(length=260)

    out: list[dict] = []
    for pred in preds:
        target = pred.get("target_date")
        actual_doc = actuals.get(target)
        actual = _as_float((actual_doc or {}).get("actual_cheapest"))
        if not target or actual is None:
            continue

        values: dict[str, float] = {}
        raw_methods = pred.get("methods") or {}
        raw_methods_full = pred.get("methods_full") or {}
        for method in methods:
            value = _as_float(raw_methods.get(method))
            if value is None:
                value = _as_float(raw_methods_full.get(method))
            if value is not None:
                values[method] = round(value, 4)

        ensemble = _as_float(pred.get("ensemble"))
        if ensemble is None:
            ensemble = _as_float(pred.get("ensemble_full"))
        if ensemble is not None:
            values["ensemble"] = round(ensemble, 4)

        if values:
            out.append({
                "target_date": target,
                "actual": round(actual, 4),
                "methods": values,
                "source": "predictions",
            })
    return out


async def _rows_from_daily_tracker(
    db,
    fuel: str,
    region: str,
    cutoff: str,
    methods: tuple[str, ...],
) -> list[dict]:
    source_cutoff = (_parse_date(cutoff) - timedelta(days=1)).isoformat()
    rows = await db.daily_tracker.find(
        {"fuel": fuel, "region": region, "date": {"$gte": source_cutoff}},
        {
            "_id": 0,
            "date": 1,
            "hour": 1,
            "actual_cheapest": 1,
            "prediction_for_tomorrow_cheapest": 1,
            "prediction_full": 1,
        },
    ).sort([("date", 1), ("hour", 1)]).to_list(length=900)

    actual_by_date: dict[str, dict] = {}
    prediction_by_date: dict[str, dict] = {}
    for row in rows:
        row_date = row.get("date")
        if not row_date:
            continue
        if row.get("actual_cheapest") is not None and row_date >= cutoff:
            actual_by_date[row_date] = row
        if row.get("prediction_for_tomorrow_cheapest") is not None or row.get("prediction_full"):
            prediction_by_date[row_date] = row

    out: list[dict] = []
    for target in sorted(actual_by_date):
        try:
            source_date = (_parse_date(target) - timedelta(days=1)).isoformat()
        except ValueError:
            continue
        source = prediction_by_date.get(source_date)
        if not source:
            continue

        actual = _as_float(actual_by_date[target].get("actual_cheapest"))
        if actual is None:
            continue

        values = _method_values_from_prediction_full(source.get("prediction_full"), methods)
        ensemble = values.get("ensemble")
        if ensemble is None:
            ensemble = _as_float(source.get("prediction_for_tomorrow_cheapest"))
        if ensemble is not None:
            values["ensemble"] = round(ensemble, 4)

        if values:
            out.append({
                "target_date": target,
                "actual": round(actual, 4),
                "methods": values,
                "source": "daily_tracker",
            })
    return out


async def realized_prediction_rows(
    db,
    fuel: str,
    region: str = "Suomi",
    days: int = 30,
    methods: tuple[str, ...] = DEFAULT_METHODS,
) -> list[dict]:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    collection_rows = await _rows_from_predictions_collection(
        db, fuel, region, cutoff, methods
    )
    tracker_rows = await _rows_from_daily_tracker(db, fuel, region, cutoff, methods)

    by_date = {row["target_date"]: row for row in tracker_rows}
    by_date.update({row["target_date"]: row for row in collection_rows})
    return [by_date[key] for key in sorted(by_date)]

