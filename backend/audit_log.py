"""
Audit logging system for admin actions.
Tracks who did what, when, and from where for security forensics.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase


def hash_token(token: str) -> str:
    """Hash admin token for audit log (never store plaintext)."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


async def log_admin_action(
    db: AsyncIOMotorDatabase,
    action: str,
    token: str,
    client_ip: str,
    params: dict,
    result: str,
    error: Optional[str] = None
):
    """
    Log an admin action to the audit_log collection.
    
    Args:
        db: MongoDB database instance
        action: Action name (e.g., "fix_capture", "trigger_predict")
        token: Admin token (will be hashed)
        client_ip: Client IP address
        params: Action parameters (sanitized)
        result: "success" or "failure"
        error: Error message if failed
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc),
        "action": action,
        "token_hash": hash_token(token),  # Never store plaintext token
        "client_ip": client_ip,
        "params": _sanitize_params(params),
        "result": result,
        "error": error
    }
    
    try:
        await db.audit_log.insert_one(log_entry)
    except Exception as e:
        # Log to stderr if audit logging fails, but don't block the action
        print(f"AUDIT LOG FAILURE: {e}")


async def log_failed_auth(
    db: AsyncIOMotorDatabase,
    client_ip: str,
    endpoint: str
):
    """
    Track failed authentication attempts for rate limiting/lockout.
    
    Args:
        db: MongoDB database instance
        client_ip: Client IP address
        endpoint: Endpoint that was accessed
    """
    try:
        await db.failed_auth.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "client_ip": client_ip,
            "endpoint": endpoint
        })
    except Exception:
        pass  # Silent failure - don't block on logging


async def get_failed_auth_count(
    db: AsyncIOMotorDatabase,
    client_ip: str,
    window_minutes: int = 10
) -> int:
    """
    Count failed auth attempts from an IP in the last N minutes.
    
    Args:
        db: MongoDB database instance
        client_ip: Client IP address
        window_minutes: Time window to check
        
    Returns:
        Number of failed attempts
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    
    try:
        count = await db.failed_auth.count_documents({
            "client_ip": client_ip,
            "timestamp": {"$gte": cutoff}
        })
        return count
    except Exception:
        return 0  # Fail open - don't lock out on DB errors


async def clear_failed_auth(
    db: AsyncIOMotorDatabase,
    client_ip: str
):
    """Clear failed auth attempts after successful login."""
    try:
        await db.failed_auth.delete_many({"client_ip": client_ip})
    except Exception:
        pass


def _sanitize_params(params: dict) -> dict:
    """Remove sensitive data from audit log parameters."""
    sanitized = params.copy()
    
    # Remove password/token fields
    for key in ["password", "token", "admin_token", "x_admin_token"]:
        if key in sanitized:
            sanitized[key] = "***REDACTED***"
    
    return sanitized
