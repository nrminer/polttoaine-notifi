"""Shared day-ahead forecast target and tracker-row semantics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    HELSINKI = ZoneInfo("Europe/Helsinki")
except ZoneInfoNotFoundError:
    try:
        from dateutil import tz

        HELSINKI = tz.gettz("Europe/Helsinki")
        if HELSINKI is None:
            raise RuntimeError
    except Exception:
        raise RuntimeError("Europe/Helsinki timezone data is required")


TARGET_HOUR = 21
MODEL_VERSION = "persistence-v1"


def helsinki_now(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(HELSINKI)


def target_date(now: datetime | None = None) -> date:
    return helsinki_now(now).date() + timedelta(days=1)


def canonical_age_hours(date_text: str, now: datetime | None = None) -> float:
    try:
        captured = datetime.fromisoformat(f"{date_text[:10]}T{TARGET_HOUR:02d}:00:00").replace(
            tzinfo=HELSINKI
        )
    except (TypeError, ValueError):
        return float("inf")
    return (helsinki_now(now) - captured).total_seconds() / 3600


def actual_price(row: dict, region: str) -> float | None:
    if region == "Suomi":
        value = row.get("actual_cheapest")
    else:
        city = (row.get("by_city") or {}).get(region) or {}
        value = city.get("cheapest", city.get("min"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def is_observed_actual(row: dict, region: str) -> bool:
    if actual_price(row, region) is None:
        return False
    if row.get("capture_canonical") is False:
        return False
    if region != "Suomi":
        city = (row.get("by_city") or {}).get(region) or {}
        return city.get("observed", True) is True

    status = row.get("actual_status")
    if status is not None:
        return status in {"observed", "corrected"}
    return not row.get("verification_override") and not row.get("verification_failed")


def daily_series(rows: list[dict], region: str) -> list[tuple[str, float]]:
    """Return one verified canonical 21:00 value per date."""
    points: dict[str, float] = {}
    for row in sorted(rows, key=lambda item: (item.get("date", ""), item.get("hour", -1))):
        row_date = row.get("date")
        if row_date and row.get("hour") == TARGET_HOUR and is_observed_actual(row, region):
            points[row_date] = actual_price(row, region)
    return sorted(points.items())
