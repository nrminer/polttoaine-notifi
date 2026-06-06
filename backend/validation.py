"""
Shared validation utilities for scraped fuel price data.

This module provides common validation and filtering functions used across
the backend to ensure scraped price data is realistic and consistent.
"""
from typing import Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Realistic Finnish fuel price bounds (€/L). Anything outside is almost certainly
# a parsing error or stale junk from a scraper.
PRICE_MIN_SANITY = 1.10
PRICE_MAX_SANITY = 3.50

# Per-batch outlier threshold: drop rows whose price deviates more than this
# from the median (as a fraction of the median).
OUTLIER_THRESHOLD_FRACTION = 0.25


def validate_price_bounds(price: float, min_price: float = PRICE_MIN_SANITY, 
                         max_price: float = PRICE_MAX_SANITY) -> bool:
    """Check if a price is within realistic bounds.
    
    Args:
        price: Price in EUR/L
        min_price: Minimum realistic price (default 1.10)
        max_price: Maximum realistic price (default 3.50)
        
    Returns:
        True if price is within bounds, False otherwise
    """
    if price is None:
        return False
    return min_price <= price <= max_price


def filter_price_outliers(prices: list[float], threshold: float = OUTLIER_THRESHOLD_FRACTION) -> list[bool]:
    """Identify outliers using IQR method.
    
    Args:
        prices: List of prices in EUR/L
        threshold: IQR multiplier for outlier detection (default 0.25)
        
    Returns:
        List of booleans indicating which prices are valid (True = keep, False = outlier)
    """
    if not prices or len(prices) < 3:
        return [True] * len(prices)
    
    arr = np.array(prices)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    
    if iqr == 0:
        # All prices the same, no outliers
        return [True] * len(prices)
    
    lower_bound = q1 - threshold * iqr
    upper_bound = q3 + threshold * iqr
    
    return [lower_bound <= p <= upper_bound for p in prices]


def validate_scraped_data(
    rows: list[dict],
    source: str,
    min_price: float = PRICE_MIN_SANITY,
    max_price: float = PRICE_MAX_SANITY,
    outlier_threshold: float = OUTLIER_THRESHOLD_FRACTION
) -> list[dict]:
    """Validate and filter scraped price data.
    
    Applies multiple validation layers:
    1. Hard bounds check (min_price to max_price)
    2. IQR-based outlier detection within batch
    
    Args:
        rows: List of dicts with 'price' field
        source: Name of scraper source (for logging)
        min_price: Minimum realistic price
        max_price: Maximum realistic price
        outlier_threshold: IQR multiplier for outlier detection
        
    Returns:
        Filtered list containing only valid rows
    """
    if not rows:
        return []
    
    # Step 1: Hard bounds filter
    bounded = []
    bounds_rejected = 0
    for r in rows:
        price = r.get("price")
        if price is None:
            continue
        if not validate_price_bounds(price, min_price, max_price):
            bounds_rejected += 1
            continue
        bounded.append(r)
    
    if bounds_rejected > 0:
        logger.warning(
            "%s: rejected %d/%d rows for price bounds violation",
            source, bounds_rejected, len(rows)
        )
    
    if not bounded:
        return []
    
    # Step 2: IQR outlier filter
    prices = [r["price"] for r in bounded]
    valid_mask = filter_price_outliers(prices, outlier_threshold)
    
    filtered = [r for r, valid in zip(bounded, valid_mask) if valid]
    outliers_rejected = len(bounded) - len(filtered)
    
    if outliers_rejected > 0:
        logger.warning(
            "%s: rejected %d/%d rows as statistical outliers (IQR threshold %.2f)",
            source, outliers_rejected, len(bounded), outlier_threshold
        )
    
    logger.info(
        "%s: validated %d/%d rows (%.1f%% pass rate)",
        source, len(filtered), len(rows), 
        100 * len(filtered) / len(rows) if rows else 0
    )
    
    return filtered


def validate_cross_fuel_prices(diesel_price: Optional[float], 
                               gasoline_price: Optional[float],
                               min_diff: float = -0.30,
                               max_diff: float = 0.30) -> tuple[bool, str]:
    """Validate diesel vs gasoline price relationship.
    
    In Finland, diesel is typically within ±30 cents of 95E10.
    
    Args:
        diesel_price: Diesel price in EUR/L
        gasoline_price: 95E10 price in EUR/L
        min_diff: Minimum expected difference (diesel - gasoline)
        max_diff: Maximum expected difference (diesel - gasoline)
        
    Returns:
        Tuple of (is_valid, reason)
    """
    if diesel_price is None or gasoline_price is None:
        return True, "Insufficient data"
    
    diff = diesel_price - gasoline_price
    
    if diff < min_diff:
        return False, f"Diesel too cheap vs gasoline (diff {diff:.3f}, min {min_diff})"
    
    if diff > max_diff:
        return False, f"Diesel too expensive vs gasoline (diff {diff:.3f}, max {max_diff})"
    
    return True, f"Cross-fuel check passed (diff {diff:.3f})"
