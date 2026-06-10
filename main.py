"""main
FastAPI application entrypoint for SafeSync.

- Initializes FastAPI app
- Ensures DB tables are created on startup
- Includes API router under /api/v1
- Exposes a simple health check
"""

from __future__ import annotations

import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI

# Load environment variables from .env before any module reads os.getenv(...).
# Use an explicit path anchored to this file so it resolves regardless of the
# process working directory (e.g. under `uvicorn --reload`).
load_dotenv(Path(__file__).resolve().parent / ".env")

# Surface application INFO logs (e.g. Sentinel client init / event sent),
# which are otherwise hidden by the default WARNING root level.
logging.basicConfig(level=logging.INFO)

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
