"""Realized prediction-vs-actual helpers.

All comparisons use real daily_tracker captures as the actual price. The
predictions collection is preferred when available, but daily_tracker is used
as a durable fallback because reboot keeps captures and may clear predictions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from forecast_contract import (
    TARGET_HOUR,
    actual_price,
    daily_series,
    helsinki_now,
    is_observed_actual,
)


DEFAULT_METHODS = (
    "persistence",
    "moving_average",
    "linear_regression",
    "exp_smoothing",
    "fundamental_anchor",
    "ai_llm",
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
    tracker_region = "Suomi" if region != "Suomi" else region
    rows = await db.daily_tracker.find(
        {
            "fuel": fuel,
            "region": tracker_region,
            "date": {"$gte": cutoff},
            "hour": TARGET_HOUR,
        },
        {"_id": 0, "date": 1, "hour": 1, "actual_cheapest": 1,
         "actual_status": 1, "verification_override": 1,
         "verification_failed": 1, "capture_canonical": 1, "by_city": 1},
    ).sort([("date", 1), ("hour", 1)]).to_list(length=800)

    return {
        row_date: {"actual_cheapest": price}
        for row_date, price in daily_series(rows, region)
    }


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
            "target_hour": 1,
            "evaluation_eligible": 1,
            "canonical": 1,
        },
    ).sort("target_date", 1).to_list(length=260)

    out: list[dict] = []
    for pred in preds:
        scored = pred.get("canonical") or pred
        if scored.get("target_hour") != TARGET_HOUR or scored.get("evaluation_eligible") is not True:
            continue
        target = pred.get("target_date")
        actual_doc = actuals.get(target)
        actual = _as_float((actual_doc or {}).get("actual_cheapest"))
        if not target or actual is None:
            continue

        values: dict[str, float] = {}
        raw_methods = scored.get("methods") or {}
        raw_methods_full = scored.get("methods_full") or {}
        for method in methods:
            value = _as_float(raw_methods.get(method))
            if value is None:
                value = _as_float(raw_methods_full.get(method))
            if value is not None:
                values[method] = round(value, 4)

        ensemble = _as_float(scored.get("ensemble"))
        if ensemble is None:
            ensemble = _as_float(scored.get("ensemble_full"))
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
    tracker_region = "Suomi" if region != "Suomi" else region
    rows = await db.daily_tracker.find(
        {"fuel": fuel, "region": tracker_region, "date": {"$gte": source_cutoff},
         "hour": TARGET_HOUR},
        {
            "_id": 0,
            "date": 1,
            "hour": 1,
            "actual_cheapest": 1,
            "prediction_for_tomorrow_cheapest": 1,
            "prediction_full": 1,
            "prediction_target_date": 1,
            "prediction_target_hour": 1,
            "prediction_evaluation_eligible": 1,
            "actual_status": 1,
            "verification_override": 1,
            "verification_failed": 1,
            "capture_canonical": 1,
            "by_city": 1,
        },
    ).sort([("date", 1), ("hour", 1)]).to_list(length=900)

    actual_by_date: dict[str, dict] = {}
    prediction_by_date: dict[str, dict] = {}
    for row in rows:
        row_date = row.get("date")
        if not row_date:
            continue
        if row_date >= cutoff and is_observed_actual(row, region):
            actual_by_date[row_date] = row
        city_prediction = ((row.get("by_city") or {}).get(region) or {}).get(
            "prediction_for_tomorrow_cheapest"
        ) if region != "Suomi" else None
        has_prediction = (
            (city_prediction is not None or actual_price(row, region) is not None) if region != "Suomi"
            else row.get("prediction_for_tomorrow_cheapest") is not None or row.get("prediction_full")
        )
        if has_prediction and is_observed_actual(row, region):
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

        actual = actual_price(actual_by_date[target], region)
        if actual is None:
            continue

        if region == "Suomi":
            values = (
                _method_values_from_prediction_full(source.get("prediction_full"), methods)
                if source.get("prediction_evaluation_eligible") is True else {}
            )
            persistence = actual_price(source, region)
            if persistence is not None:
                values["persistence"] = round(persistence, 4)
            ensemble = persistence
        else:
            ensemble = _as_float(
                ((source.get("by_city") or {}).get(region) or {}).get(
                    "prediction_for_tomorrow_cheapest"
                )
            )
            if ensemble is None:
                ensemble = actual_price(source, region)
            values = {"persistence": ensemble} if ensemble is not None else {}
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
    cutoff = (helsinki_now().date() - timedelta(days=days)).isoformat()
    collection_rows = await _rows_from_predictions_collection(
        db, fuel, region, cutoff, methods
    )
    tracker_rows = await _rows_from_daily_tracker(db, fuel, region, cutoff, methods)

    by_date = {row["target_date"]: row for row in tracker_rows}
    by_date.update({row["target_date"]: row for row in collection_rows})
    return [by_date[key] for key in sorted(by_date)]
