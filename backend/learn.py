"""Self-training layer for realized prediction performance.

The comparison target is always real `daily_tracker.actual_cheapest` data.
Historical rows come through `accuracy_utils`, which can recover comparisons
from preserved daily_tracker captures even after the predictions collection has
been cleared by a reboot.
"""
from __future__ import annotations

import accuracy_utils as accuracy_mod


_METHODS = (
    "moving_average",
    "linear_regression",
    "exp_smoothing",
    "fundamental_anchor",
    "ai_llm",
)


def _stats(signed_errors: list[float]) -> dict:
    """Return n, MAE, signed bias, and RMSE for pred - actual errors."""
    if not signed_errors:
        return {"n": 0, "mae": None, "bias": None, "rmse": None}
    n = len(signed_errors)
    abs_sum = sum(abs(x) for x in signed_errors)
    sq_sum = sum(x * x for x in signed_errors)
    return {
        "n": n,
        "mae": round(abs_sum / n, 5),
        "bias": round(sum(signed_errors) / n, 5),
        "rmse": round((sq_sum / n) ** 0.5, 5),
    }


async def track_record(
    db,
    fuel: str,
    region: str = "Suomi",
    days: int = 30,
    methods: tuple[str, ...] = _METHODS,
) -> dict:
    """Build method-level realized errors for self-calibration."""
    keys = list(methods) + ["ensemble"]
    signed: dict[str, list[float]] = {k: [] for k in keys}
    rows: list[dict] = []

    realized_rows = await accuracy_mod.realized_prediction_rows(
        db, fuel, region, days=days, methods=methods
    )
    for realized in realized_rows:
        actual = float(realized["actual"])
        row = {
            "date": realized.get("target_date"),
            "actual": actual,
            "methods": {},
            "signed": {},
        }

        for method, value in (realized.get("methods") or {}).items():
            if method not in signed or value is None:
                continue
            pred = float(value)
            err = pred - actual
            row["methods"][method] = round(pred, 4)
            row["signed"][method] = round(err, 5)
            signed[method].append(err)

        rows.append(row)

    return {
        "rows": rows,
        "stats": {k: _stats(v) for k, v in signed.items()},
        "n_total": len(rows),
        "days_window": days,
    }
