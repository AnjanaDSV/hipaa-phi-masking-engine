"""api.background_worker
Background worker orchestration for masking jobs.

Responsibilities:
- Stream input file (CSV/JSONL) with minimal memory use (falls back to a simple CSV reader if ingestion layer is absent).
- Mask specified sensitive fields using core.masker.mask_record.
- Validate post-processed output using validators.checker to guarantee zero leakage.
- Write masked output incrementally to an output file.
- Update AuditLog at key stages and on failure.

Defensive: all IO and DB operations are guarded. SecurityException (BaseException subclass)
from core.masker is treated as fatal and updates the audit record accordingly.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import stat
from pathlib import Path
from typing import Dict, Iterable, List
import asyncio

from core import masker
from core.sentinel_client import sentinel
from validators import checker
from db import models as db_models

logger = logging.getLogger(__name__)

# Fields that are considered sensitive by default
DEFAULT_SENSITIVE_FIELDS = ["ssn", "phone", "dob", "first_name", "last_name"]

# Ensure DB tables exist
try:
    db_models.create_tables()
except Exception as exc:  # pragma: no cover - defensive
    logger.exception("Failed ensuring DB tables exist during background worker import: %s", exc)


async def process_file(job_id: str, input_path: str, sensitive_fields: Iterable[str] | None = None) -> None:
    """Process the input file identified by input_path and update the AuditLog for job_id.

    - Streams rows from CSV or JSONL inputs.
    - Masks configured sensitive fields.
    - Validates masked outputs to guarantee zero leakage.
    - Writes masked rows to an output file next to the input with suffix `.masked`.

    Raises: exceptions are caught and recorded to the audit log. SecurityException is treated as fatal.
    """
    sensitive = [str(s).lower().strip() for s in sensitive_fields] if sensitive_fields else DEFAULT_SENSITIVE_FIELDS
    input_p = Path(input_path)

    if not input_p.exists():
        msg = f"Input path does not exist: {input_path}"
        logger.error(msg)
        # Update audit record to FAILED
        try:
            with db_models.SessionLocal() as session:
                rec = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                if rec:
                    rec.status = "FAILED"
                    rec.processing_notes = (rec.processing_notes or "") + "\n" + msg
                    session.add(rec)
                    session.commit()
        except Exception:
            logger.exception("Failed updating audit record for missing input path %s", job_id)
        return

    out_path = input_p.with_name(f"{input_p.stem}.masked{input_p.suffix}")

    # If the output file already exists, attempt to make it writable (best-effort on Windows)
    try:
        if out_path.exists():
            os.chmod(out_path, stat.S_IWRITE)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not change permissions for output file %s: %s", out_path, exc)

    rows_processed = 0
    leaked_rows = 0

    try:
        # Mark job as processing
        with db_models.SessionLocal() as session:
            rec = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
            if rec:
                rec.status = "IN_PROGRESS"
                session.add(rec)
                session.commit()

        # Decide reader based on file type
        if input_p.suffix.lower() in {".json", ".jsonl", ".ndjson"}:
            reader = _jsonl_reader(input_p)
            is_csv = False
        else:
            reader = _csv_reader(input_p)
            is_csv = True

        # Open output and stream
        first_row = True
        fieldnames: List[str] = []

        with out_path.open("w", newline="", encoding="utf-8") as out_fh:
            writer = None

            for row in reader:
                # 1. Normalize keys to lowercase and strip spaces to prevent mismatches
                clean_row = {k.lower().strip(): v for k, v in row.items()}

                # 2. Mask the record using the cleaned row
                masked = masker.mask_record(clean_row, sensitive)

                # Validate masked fields individually to detect leakage
                for f in sensitive:
                    if f in masked and masked.get(f) is not None:
                        checker.validate_line(str(masked.get(f)))

                # Initialize CSV writer lazily if needed (with semicolon delimiter!)
                if first_row:
                    fieldnames = list(masked.keys())
                    writer = csv.DictWriter(out_fh, fieldnames=fieldnames, delimiter=',')
                    writer.writeheader()
                    first_row = False

                # Write masked row
                if writer is None:
                    raise RuntimeError("CSV writer was not initialized")
                writer.writerow(masked)

                rows_processed += 1

                # Periodically update audit record
                if rows_processed % 50 == 0:
                    try:
                        with db_models.SessionLocal() as session:
                            rec = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                            if rec:
                                rec.rows_processed = rows_processed
                                session.add(rec)
                                session.commit()
                    except Exception:
                        logger.exception("Failed to update audit progress for job %s", job_id)

            # Completed successfully
            with db_models.SessionLocal() as session:
                rec = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                if rec:
                    rec.rows_processed = rows_processed
                    rec.leaked_rows = leaked_rows
                    rec.status = "COMPLETED"
                    rec.processing_notes = (rec.processing_notes or "") + f"\nOutput written to {str(out_path)}"
                    session.add(rec)
                    session.commit()

            sentinel.send_job_event(
                job_id=str(job_id),
                status="COMPLETED",
                rows_processed=rows_processed,
                leaked_rows=leaked_rows,
                source_file=input_path,
            )
            logger.info("Job %s completed: rows=%d out=%s", job_id, rows_processed, out_path)

    except BaseException as exc:
        # Catch BaseException to ensure SecurityException (which subclasses BaseException)
        logger.critical("Fatal error processing job %s: %s", job_id, exc, exc_info=True)
        try:
            with db_models.SessionLocal() as session:
                rec = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                if rec:
                    rec.rows_processed = rows_processed
                    rec.leaked_rows = leaked_rows
                    rec.status = "FAILED"
                    rec.processing_notes = (rec.processing_notes or "") + f"\nFatal error: {exc}"
                    session.add(rec)
                    session.commit()
        except Exception:
            logger.exception("Failed to update audit log after fatal error for job %s", job_id)
        sentinel.send_job_event(
            job_id=str(job_id),
            status="FAILED",
            rows_processed=rows_processed,
            leaked_rows=leaked_rows,
            source_file=input_path,
        )

        # Reraise SecurityException so calling contexts are aware (BackgroundTasks will log)
        if isinstance(exc, masker.SecurityException):
            raise
        # For other BaseExceptions, raise as RuntimeError to avoid silent failures
        raise


def _csv_reader(path: Path) -> Iterable[Dict[str, str]]:
    """Simple CSV row generator yielding dicts. Defensive and streaming."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            # Added delimiter=',' to handle standard CSV exports
            reader = csv.DictReader(fh, delimiter=',')
            for r in reader:
                yield r
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed reading CSV file %s: %s", path, exc)
        raise


def _jsonl_reader(path: Path) -> Iterable[Dict[str, str]]:
    """Simple JSONL/NDJSON generator yielding parsed objects per line."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        yield {k: (v if isinstance(v, str) else str(v)) for k, v in obj.items()}
                    else:
                        # Skip non-dict lines defensively
                        logger.warning("Skipping non-object JSONL line in %s: %s", path, line)
                except json.JSONDecodeError:
                    logger.exception("Invalid JSON line in %s: %s", path, line)
                    raise
    except Exception as exc:
        logger.exception("Failed reading JSONL file %s: %s", path, exc)
        raise
