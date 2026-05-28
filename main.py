"""main
FastAPI application entrypoint for SafeSync.

- Initializes FastAPI app
- Ensures DB tables are created on startup
- Includes API router under /api/v1
- Exposes a simple health check
"""

from __future__ import annotations

import logging
from fastapi import FastAPI

from db import models as db_models
from api.v1.mask_router import router as mask_router

logger = logging.getLogger("safesync.main")

app = FastAPI(title="SafeSync API")


@app.on_event("startup")
def startup_event() -> None:
    """Startup tasks: ensure database tables exist.

    Fail-fast: log and re-raise unexpected errors to avoid running with a bad DB state.
    """
    try:
        db_models.create_tables()
        logger.info("Database tables ensured on startup")
    except Exception as exc:
        logger.exception("Failed to ensure database tables on startup: %s", exc)
        raise


# Include API routers
app.include_router(mask_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok"}
