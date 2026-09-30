"""
Structured Monitoring & Logging Module
Provides:
- Request ID correlation middleware
- High-resolution execution timing
- Redaction filter preventing passwords, tokens, and keys from entering logs
- Database health probe
"""

import time
import uuid
import logging
import re
from typing import Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text


# ============================================================
# SECRET REDACTION LOG FILTER
# ============================================================

class SensitiveDataFilter(logging.Filter):
    """
    Log filter that scrubs credentials, passwords, JWTs, and API keys
    from all log records before output.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            # Redact bearer tokens
            msg = re.sub(r"(?i)bearer\s+[A-Za-z0-9\-_\.]+", "Bearer [REDACTED]", msg)
            # Redact passwords
            msg = re.sub(r"(?i)(password|secret|pwd)[:=]\s*\S+", r"\1=[REDACTED]", msg)
            # Redact API keys
            msg = re.sub(r"(?i)\b(gsk_|sk_)[A-Za-z0-9_]{10,}\b", "[API_KEY_REDACTED]", msg)
            # Redact database connection strings with passwords
            msg = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED]@", msg)
            record.msg = msg
        return True


# Setup structured logger
logger = logging.getLogger("telecom_ai")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [req=%(request_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ============================================================
# REQUEST ID & LOGGING MIDDLEWARE
# ============================================================

class RequestMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique Request-ID to every incoming HTTP request,
    times request execution, and emits structured access logs.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate request ID
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = req_id

        start_time = time.perf_counter()

        # Log incoming request at debug level
        method = request.method
        path = request.url.path

        try:
            response: Response = await call_next(request)
            duration = time.perf_counter() - start_time
            status_code = response.status_code

            # Attach X-Request-ID header to response
            response.headers["X-Request-ID"] = req_id

            # Emit structured request log
            extra = {"request_id": req_id}
            logger.info(
                f"{method} {path} status={status_code} duration={duration:.4f}s",
                extra=extra,
            )
            return response

        except Exception as exc:
            duration = time.perf_counter() - start_time
            extra = {"request_id": req_id}
            logger.error(
                f"{method} {path} FAILED with {exc.__class__.__name__} after {duration:.4f}s: {exc}",
                extra=extra,
            )
            raise exc


# ============================================================
# DATABASE HEALTH PROBE
# ============================================================

def check_database_health(db: Session) -> Tuple[bool, str]:
    """
    Safely probe database connectivity using a lightweight query.
    Never exposes internal database credentials or connection strings.
    """
    try:
        db.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}", extra={"request_id": "health-check"})
        return False, "unavailable"
