#!/usr/bin/env python3
"""Diagnostic helper: print all AuditLog rows from the audit DB.

Usage: python check_db.py
"""
from __future__ import annotations

import logging
import sys

from db import models as db_models


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("check_db")

    try:
        with db_models.SessionLocal() as session:
            rows = session.query(db_models.AuditLog).order_by(db_models.AuditLog.created_at.desc()).all()
            if not rows:
                print("No AuditLog entries found.")
                return 0

            for r in rows:
                print(f"job_id={r.job_id} | created_at={r.created_at} | status={r.status} | rows_processed={r.rows_processed} | leaked_rows={r.leaked_rows}")
                print("processing_notes:")
                if r.processing_notes:
                    print(r.processing_notes)
                else:
                    print("<none>")
                print("-" * 60)

    except Exception as exc:
        logger.exception("Failed querying AuditLog: %s", exc)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
