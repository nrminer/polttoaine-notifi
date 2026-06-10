"""
Security utilities for BensaVahti backend.

Contains validation helpers, input sanitization, and security-related functions.
"""
import re
from typing import Any
from fastapi import HTTPException


# Whitelist validation constants
ALLOWED_FUELS = {"95E10", "diesel"}
ALLOWED_REGIONS = {"Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti", "Suomi"}


def validate_fuel(fuel: str) -> None:
    """Validate fuel parameter against whitelist to prevent NoSQL injection.
    
    Args:
        fuel: User-provided fuel type
        
    Raises:
        HTTPException: If fuel is not in whitelist
    """
    if fuel not in ALLOWED_FUELS:
        raise HTTPException(400, "Invalid fuel type")


def validate_region(region: str) -> None:
    """Validate region parameter against whitelist to prevent NoSQL injection.
    
    Args:
        region: User-provided region name
        
    Raises:
        HTTPException: If region is not in whitelist
    """
    if region not in ALLOWED_REGIONS:
        raise HTTPException(400, "Invalid region")


def validate_fuel_and_region(fuel: str, region: str) -> None:
    """Validate both fuel and region parameters.
    
    Args:
        fuel: User-provided fuel type
        region: User-provided region name
        
    Raises:
        HTTPException: If either parameter is invalid
    """
    validate_fuel(fuel)
    validate_region(region)


def sanitize_string(text: str, max_length: int = 200) -> str:
    """Sanitize user input to prevent XSS and injection attacks.
    
    Removes HTML tags, limits length, and strips dangerous characters.
    
    Args:
        text: Input string to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized string
    """
    if not text:
        return ""
    
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Limit length
    text = text[:max_length]
    
    return text.strip()


def redact_secrets(text: str) -> str:
    """Redact common secret patterns from text (for logging).
    
    Args:
        text: Text that may contain secrets
        
    Returns:
        Text with secrets redacted
    """
    if not text:
        return text
    
    # Redact common secret patterns
    patterns = [
        (r'(api[_-]?key|token|secret|authorization|password|bearer)[\"\s:=]+[^\s\"]+', r'\1=REDACTED'),
        (r'mongodb(\+srv)?://[^:]+:[^@]+@', r'mongodb://REDACTED:REDACTED@'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def validate_price_bounds(price: float, min_price: float = 1.10, max_price: float = 3.50) -> None:
    """Validate that a price is within realistic bounds.
    
    Args:
        price: Price value to validate
        min_price: Minimum allowed price
        max_price: Maximum allowed price
        
    Raises:
        HTTPException: If price is outside bounds
    """
    if not (min_price <= price <= max_price):
        raise HTTPException(400, "Price validation failed")


def validate_date_format(date_str: str) -> None:
    """Validate ISO date format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to validate
        
    Raises:
        HTTPException: If date format is invalid
    """
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise HTTPException(400, "Invalid date format (expected YYYY-MM-DD)")
