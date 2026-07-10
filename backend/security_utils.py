"""Input validation shared by the public and admin API routes."""
import re

from fastapi import HTTPException


ALLOWED_FUELS = {"95E10", "diesel"}
ALLOWED_REGIONS = {
    "Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti", "Suomi",
}


def validate_fuel(fuel: str) -> None:
    if fuel not in ALLOWED_FUELS:
        raise HTTPException(400, "Invalid fuel type")


def validate_region(region: str) -> None:
    if region not in ALLOWED_REGIONS:
        raise HTTPException(400, "Invalid region")


def validate_fuel_and_region(fuel: str, region: str) -> None:
    validate_fuel(fuel)
    validate_region(region)


def sanitize_string(text: str, max_length: int = 200) -> str:
    return re.sub(r"<[^>]+>", "", text or "")[:max_length].strip()


def validate_price_bounds(
    price: float, min_price: float = 1.10, max_price: float = 3.50,
) -> None:
    if not min_price <= price <= max_price:
        raise HTTPException(400, "Price validation failed")


def validate_date_format(date_str: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise HTTPException(400, "Invalid date format (expected YYYY-MM-DD)")
