"""api.v1.mask_router
FastAPI router exposing POST /api/v1/mask which enqueues background masking jobs
and returns a 202 Accepted with a job_id for tracking.

Uses DB models to record an AuditLog with status PENDING, and attempts to
invoke api.background_worker.process_file(job_id, input_path) as a background task.

Defensive and fail-fast: validates inputs, logs errors, and updates audit status on failures.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from db import models as db_models

logger = logging.getLogger(__name__)

# Ensure DB tables exist on import for simple deployments/tests
try:
    db_models.create_tables()
except Exception as exc:  # pragma: no cover - defensive
    logger.exception("Failed to create DB tables at import: %s", exc)

router = APIRouter()


class MaskRequest(BaseModel):
    input_path: str


async def _start_background(job_id: str, input_path: str) -> None:
    """Start the real background worker if available, otherwise mark job FAILED.

    This function is executed by FastAPI BackgroundTasks after the response is sent.
    """
    try:
        # Import the background worker module lazily to avoid circular imports
        from api import background_worker as bw

        # Expect the background_worker to expose an async function `process_file(job_id, input_path)`
        if not hasattr(bw, "process_file"):
            raise ImportError("background_worker.process_file not found")

        await bw.process_file(job_id, input_path)
    except Exception as exc:
        logger.exception("Background worker failed for job %s: %s", job_id, exc)
        # Update audit record to FAILED
        try:
            with db_models.SessionLocal() as session:
                record = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                if record:
                    record.status = "FAILED"
                    record.processing_notes = (record.processing_notes or "") + f"\nBackground failure: {exc}"
                    session.add(record)
                    session.commit()
        except Exception:
            logger.exception("Failed updating audit record for failed job %s", job_id)


@router.post("/mask", status_code=status.HTTP_202_ACCEPTED)
async def submit_mask(request: MaskRequest, background_tasks: BackgroundTasks) -> Any:
    # Basic validation of input path
    input_path = Path(request.input_path)
    if not input_path.exists():
        logger.warning("Received mask request for non-existent path: %s", input_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_path does not exist")

    # Create a job id and initial audit record
    job_id = str(uuid.uuid4())
    try:
        with db_models.SessionLocal() as session:
            audit = db_models.AuditLog(
                job_id=job_id,
                created_at=datetime.utcnow(),
                rows_processed=0,
                leaked_rows=0,
                status="PENDING",
                processing_notes=f"input_path={str(input_path)}",
            )
            session.add(audit)
            session.commit()
    except Exception as exc:
        logger.exception("Failed creating audit record for job %s: %s", job_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enqueue job")

    # Enqueue background processing; BackgroundTasks will run after response is sent
    background_tasks.add_task(_start_background, job_id, str(input_path))

    return {"job_id": job_id, "status": "accepted"}


__all__ = ["router", "MaskRequest"]
