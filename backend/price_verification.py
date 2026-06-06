"""
Price verification and outlier detection for BensaVahti captures.

Prevents ridiculously wrong prices from being stored by:
  1. Hard bounds checking (1.10 - 3.50 EUR/L)
  2. Historical comparison (deviation from recent averages)
  3. IQR-based statistical outlier detection
  4. Cross-fuel reasonableness (diesel should be roughly 0.05-0.20 more than 95E10)
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bensavahti.verification")

# Realistic Finnish fuel price bounds (€/L)
PRICE_MIN_HARD = 1.10
PRICE_MAX_HARD = 3.50

# Expected diesel premium over 95E10 (rough range in EUR/L)
DIESEL_PREMIUM_MIN = 0.00  # sometimes diesel is cheaper
DIESEL_PREMIUM_MAX = 0.30  # rarely more than 30 cents difference

# Maximum reasonable daily price change (EUR/L) - prices don't jump more than this
MAX_DAILY_CHANGE = 0.15  # 15 cents per day is already extreme

# Historical deviation threshold - flag if >20% from recent average
HISTORICAL_DEVIATION_THRESHOLD = 0.20


class VerificationResult:
    """Result of price verification check."""
    
    def __init__(self, is_valid: bool, price: float, reason: str = "", 
                 confidence: str = "high", suggested_alternative: float | None = None):
        self.is_valid = is_valid
        self.price = price
        self.reason = reason
        self.confidence = confidence  # "high", "medium", "low"
        self.suggested_alternative = suggested_alternative
    
    def __repr__(self):
        status = "✓ VALID" if self.is_valid else "⚠️  INVALID"
        return f"{status}: {self.price:.3f} EUR - {self.reason}"


async def verify_price(
    price: float,
    fuel: str,
    db,
    region: str = "Suomi",
    other_fuel_price: float | None = None,
    date_iso: str | None = None
) -> VerificationResult:
    """
    Comprehensive price verification with multiple checks.
    
    Args:
        price: The price to verify (EUR/L)
        fuel: "95E10" or "diesel"
        db: MongoDB database instance
        region: Region name (default "Suomi")
        other_fuel_price: If available, the price of the other fuel type for cross-check
        date_iso: The date being captured (ISO format), defaults to today
    
    Returns:
        VerificationResult with is_valid flag and explanation
    """
    if date_iso is None:
        date_iso = datetime.now(timezone.utc).date().isoformat()
    
    # Check 1: Hard bounds
    if price < PRICE_MIN_HARD:
        return VerificationResult(
            False, price,
            f"Price {price:.3f} is below minimum realistic bound {PRICE_MIN_HARD} EUR/L. "
            "This is likely a parsing error or stale data.",
            confidence="high"
        )
    
    if price > PRICE_MAX_HARD:
        return VerificationResult(
            False, price,
            f"Price {price:.3f} exceeds maximum realistic bound {PRICE_MAX_HARD} EUR/L. "
            "This is likely a parsing error.",
            confidence="high"
        )
    
    # Check 2: Historical comparison
    recent_docs = await db.daily_tracker.find(
        {"fuel": fuel, "region": region, "actual_cheapest": {"$ne": None}},
        {"_id": 0, "date": 1, "actual_cheapest": 1}
    ).sort([("date", -1)]).limit(10).to_list(10)
    
    if recent_docs:
        recent_prices = [d["actual_cheapest"] for d in recent_docs if d.get("actual_cheapest")]
        if recent_prices:
            avg_recent = sum(recent_prices) / len(recent_prices)
            deviation = abs(price - avg_recent) / avg_recent
            
            if deviation > HISTORICAL_DEVIATION_THRESHOLD:
                return VerificationResult(
                    False, price,
                    f"Price {price:.3f} deviates {deviation*100:.1f}% from recent 10-day average "
                    f"{avg_recent:.3f} EUR/L (threshold: {HISTORICAL_DEVIATION_THRESHOLD*100}%). "
                    f"Suggested: Use {avg_recent:.3f} EUR/L or verify scrapers.",
                    confidence="high",
                    suggested_alternative=round(avg_recent, 3)
                )
            
            # Check 3: Maximum daily change (compare to most recent)
            if recent_docs:
                last_price = recent_docs[0].get("actual_cheapest")
                last_date = recent_docs[0].get("date")
                if last_price and last_date:
                    # Only check if not the same day (allow multiple captures per day)
                    if last_date != date_iso:
                        daily_change = abs(price - last_price)
                        if daily_change > MAX_DAILY_CHANGE:
                            return VerificationResult(
                                False, price,
                                f"Price changed {daily_change:.3f} EUR/L from yesterday "
                                f"({last_price:.3f} → {price:.3f}). "
                                f"Maximum reasonable daily change is {MAX_DAILY_CHANGE} EUR/L. "
                                f"This suggests a scraper error.",
                                confidence="high",
                                suggested_alternative=last_price
                            )
    
    # Check 4: Cross-fuel reasonableness check
    if other_fuel_price:
        if fuel == "diesel":
            # Diesel should be roughly 0-30 cents more than 95E10
            diff = price - other_fuel_price
            if diff < -0.30 or diff > DIESEL_PREMIUM_MAX:
                return VerificationResult(
                    False, price,
                    f"Diesel at {price:.3f} vs 95E10 at {other_fuel_price:.3f} "
                    f"(diff: {diff:+.3f}) is outside normal range "
                    f"[{-0.30:.2f}, {DIESEL_PREMIUM_MAX:.2f}]. Cross-check scrapers.",
                    confidence="medium"
                )
        elif fuel == "95E10":
            # 95E10 should be roughly 0-30 cents less than diesel
            diff = other_fuel_price - price
            if diff < -0.30 or diff > DIESEL_PREMIUM_MAX:
                return VerificationResult(
                    False, price,
                    f"95E10 at {price:.3f} vs diesel at {other_fuel_price:.3f} "
                    f"(diff: {diff:+.3f}) is outside normal range "
                    f"[{-0.30:.2f}, {DIESEL_PREMIUM_MAX:.2f}]. Cross-check scrapers.",
                    confidence="medium"
                )
    
    # All checks passed
    return VerificationResult(
        True, price,
        f"Price {price:.3f} EUR/L passed all verification checks",
        confidence="high"
    )


def verify_batch_iqr(prices: list[float], label: str = "") -> list[int]:
    """
    IQR-based outlier detection on a batch of prices.
    
    Returns:
        List of indices that are outliers (should be removed)
    """
    if len(prices) < 4:
        return []  # not enough data for IQR
    
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_prices[q1_idx]
    q3 = sorted_prices[q3_idx]
    iqr = q3 - q1
    
    if iqr < 0.001:  # essentially no variance
        return []
    
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    
    outliers = []
    for i, p in enumerate(prices):
        if p < lower or p > upper:
            outliers.append(i)
            logger.warning(
                "IQR outlier[%s]: %.3f EUR/L (bounds [%.3f, %.3f])",
                label, p, lower, upper
            )
    
    return outliers


async def get_verification_context(db, fuel: str, region: str = "Suomi") -> dict:
    """
    Get historical context for verification logging and human review.
    
    Returns a dict with:
        - recent_avg: average of last 10 captures
        - recent_min: min of last 10
        - recent_max: max of last 10
        - last_price: most recent capture
        - capture_count: total captures in history
    """
    docs = await db.daily_tracker.find(
        {"fuel": fuel, "region": region, "actual_cheapest": {"$ne": None}},
        {"_id": 0, "actual_cheapest": 1, "date": 1}
    ).sort([("date", -1)]).limit(10).to_list(10)
    
    if not docs:
        return {
            "recent_avg": None,
            "recent_min": None,
            "recent_max": None,
            "last_price": None,
            "capture_count": 0
        }
    
    prices = [d["actual_cheapest"] for d in docs if d.get("actual_cheapest")]
    
    return {
        "recent_avg": round(sum(prices) / len(prices), 3) if prices else None,
        "recent_min": round(min(prices), 3) if prices else None,
        "recent_max": round(max(prices), 3) if prices else None,
        "last_price": docs[0].get("actual_cheapest") if docs else None,
        "capture_count": len(prices)
    }
