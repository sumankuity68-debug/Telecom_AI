import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session
from slowapi.errors import RateLimitExceeded

from backend.database import init_db, get_db
from backend.monitoring import (
    RequestMonitoringMiddleware,
    check_database_health,
    logger,
)
from backend.rate_limiter import (
    limiter,
    custom_rate_limit_exceeded_handler,
)
from backend.api import (
    auth,
    customers,
    plans,
    usage,
    billing,
    network,
    tickets,
    mock,
    recharge,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and seed data if needed
    init_db()
    yield


app = FastAPI(
    title="TelecomAI • Real Telecom Backend",
    description="Production-grade RESTful API service supporting PostgreSQL, JWT Authentication, and Telecom Microservices",
    version="2.0.0",
    lifespan=lifespan,
)

# Attach rate limiter to application state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)

# Structured Request Monitoring Middleware (Request ID, execution timing, logging)
app.add_middleware(RequestMonitoringMiddleware)

# Configurable Production CORS
raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501,http://localhost:3000")
if raw_cors.strip() == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = [orig.strip() for orig in raw_cors.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Unhandled Exception Handler (Never expose stack traces to clients)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"request_id": req_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Sorry, TelecomAI could not complete that request. Please try again.",
            "status_code": 500,
            "request_id": req_id,
        },
        headers={"X-Request-ID": req_id},
    )


# Include Routers
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(plans.router)
app.include_router(usage.router)
app.include_router(billing.router)
app.include_router(network.router)
app.include_router(tickets.router)
app.include_router(mock.router)
app.include_router(recharge.router)


@app.get("/")
def root():
    return {
        "service": "TelecomAI Backend",
        "status": "ONLINE",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Step 27.3 & 27.4: Health check with safe database connectivity probe.
    Returns 200 if healthy, or 503 if database is unreachable.
    Never exposes database credentials or connection strings.
    """
    db_healthy, db_status = check_database_health(db)
    status_code = 200 if db_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_healthy else "degraded",
            "database": db_status,
            "service": "TelecomAI Backend",
            "version": "2.0.0",
        },
    )
