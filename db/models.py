"""db.models
SQLAlchemy models and database utilities for the audit trail.

Provides:
- AuditLog model (job_id, created_at, rows_processed, leaked_rows, status, processing_notes)
- Engine, SessionLocal, Base
- create_tables() helper

Defensive: validates DATABASE_URL env var and exposes helpers for use by API and background workers.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./audit.db")
if not DATABASE_URL:
    logger.critical("DATABASE_URL is not set or empty")
    raise RuntimeError("DATABASE_URL environment variable must be set")

# Create engine and session factory
try:
    engine = create_engine(DATABASE_URL, echo=False, future=True)
except Exception as exc:  # defensive
    logger.exception("Failed creating database engine: %s", exc)
    raise

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
Base = declarative_base()


class AuditLog(Base):
    """Audit log for masking jobs."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    rows_processed = Column(Integer, default=0, nullable=False)
    leaked_rows = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False)
    processing_notes = Column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<AuditLog job_id={self.job_id} status={self.status} rows={self.rows_processed} leaked={self.leaked_rows}>"


def create_tables() -> None:
    """Create database tables. Safe to call repeatedly."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # defensive
        logger.exception("Failed creating database tables: %s", exc)
        raise


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


__all__ = ["engine", "SessionLocal", "Base", "AuditLog", "create_tables", "get_session"]
