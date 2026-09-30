"""
TelecomAI Rate Limiter Module
Built with slowapi for lightweight, production-ready endpoint protection.
Provides configurable limits on authentication, OTP, and state-changing actions.
"""

import os
from starlette.requests import Request
from starlette.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Environment Configuration for Limits
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1")
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "10/minute")
OTP_RATE_LIMIT = os.getenv("OTP_RATE_LIMIT", "5/minute")
STATE_CHANGE_RATE_LIMIT = os.getenv("STATE_CHANGE_RATE_LIMIT", "10/minute")
DEFAULT_RATE_LIMIT = os.getenv("DEFAULT_RATE_LIMIT", "60/minute")


def get_client_identifier(request: Request) -> str:
    """
    Get client IP or authenticated username/customer_id for rate limiting.
    """
    # Check if request has authenticated user in state
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "username") and user.username:
        return f"user:{user.username}"

    # Fallback to remote IP address
    return get_remote_address(request) or "127.0.0.1"


# Initialize Limiter
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=[DEFAULT_RATE_LIMIT] if RATE_LIMIT_ENABLED else [],
    enabled=RATE_LIMIT_ENABLED,
)


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Return clean, user-friendly 429 JSON response without leaking internal limiter details.
    """
    req_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "status_code": 429,
            "request_id": req_id,
        },
        headers={
            "Retry-After": "60",
            "X-Request-ID": req_id,
        },
    )
