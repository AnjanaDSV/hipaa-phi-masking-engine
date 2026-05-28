from __future__ import annotations

from pathlib import Path
import uuid
import pytest
import os
import time
import csv

from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="session")
def sample_csv_path() -> Path:
    sample = Path(__file__).resolve().parents[1] / "ingestion" / "samples" / "patients.csv"
    if not sample.exists():
        raise FileNotFoundError(f"Sample patients.csv not found at expected path: {sample}")
    return sample


def test_api_mask_endpoint(sample_csv_path, monkeypatch):
    # Ensure test HMAC key and DB URL are set for the app
    monkeypatch.setenv("HMAC_KEY", "test-hmac-key-123")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./audit.db")

    with TestClient(app) as client:
        # Health check
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

        # Submit mask job
        payload = {"input_path": str(sample_csv_path)}
        r2 = client.post("/api/v1/mask", json=payload)
        assert r2.status_code == 202
        data = r2.json()
        assert "job_id" in data

        # Validate job_id is a UUID
        try:
            uuid.UUID(data["job_id"])
        except Exception:
            pytest.fail("Returned job_id is not a valid UUID")


def test_background_job_completion(sample_csv_path, monkeypatch):
    # Ensure test HMAC key and DB URL are set for the app
    monkeypatch.setenv("HMAC_KEY", "test-hmac-key-123")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./audit.db")

    # Count expected rows in the sample CSV (excluding header)
    with sample_csv_path.open(newline="", encoding="utf-8") as fh:
        expected_rows = sum(1 for _ in csv.reader(fh)) - 1

    with TestClient(app) as client:
        payload = {"input_path": str(sample_csv_path)}
        r = client.post("/api/v1/mask", json=payload)
        assert r.status_code == 202
        job_id = r.json().get("job_id")
        assert job_id

        # Poll the database AuditLog for job completion
        from db import models as db_models

        record = None
        timeout = 15.0
        interval = 0.5
        start = time.time()
        while time.time() - start < timeout:
            with db_models.SessionLocal() as session:
                record = session.query(db_models.AuditLog).filter_by(job_id=job_id).one_or_none()
                if record and record.status == "COMPLETED":
                    break
            time.sleep(interval)

        assert record is not None, "AuditLog record not found for job"
        assert record.status == "COMPLETED", f"Job did not complete successfully: {record.status}"
        assert record.rows_processed == expected_rows, f"rows_processed mismatch: {record.rows_processed} != {expected_rows}"
        assert record.leaked_rows == 0, f"leaked_rows should be 0, got {record.leaked_rows}"

        # Check masked output file exists
        out_path = sample_csv_path.with_name(f"{sample_csv_path.stem}.masked{sample_csv_path.suffix}")
        assert out_path.exists(), f"Masked output file not found at {out_path}"
