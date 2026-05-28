"""Tests for the masking pipeline (end-to-end using ingestion/samples/patients.csv)

Uses pytest. Fixtures: sample_csv_path reads the mock CSV. Tests:
- test_masking_pipeline: reads rows, masks sensitive fields, validates masked output contains no PHI, and asserts deterministic masking.

Defensive: raises informative exceptions on misconfiguration (missing HMAC_KEY).
"""

from __future__ import annotations

import csv
from pathlib import Path
import pytest

from core import patterns
import core.masker as masker
import validators.checker as checker


@pytest.fixture(scope="session")
def sample_csv_path() -> Path:
    cwd = Path(__file__).resolve().parents[1]
    sample = cwd / "ingestion" / "samples" / "patients.csv"
    if not sample.exists():
        raise FileNotFoundError(f"Sample patients.csv not found at expected path: {sample}")
    return sample


def test_masking_pipeline(sample_csv_path, monkeypatch):
    # Use a test HMAC key (non-secret test value)
    monkeypatch.setenv("HMAC_KEY", "test-hmac-key-123")

    with sample_csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert rows, "Sample CSV should contain at least one row"

    sensitive_candidates = ["ssn", "phone", "dob", "first_name", "last_name"]

    for row in rows:
        # Determine which sensitive fields actually exist in the CSV
        fields_to_mask = [f for f in sensitive_candidates if f in row and row.get(f)]

        # Mask the record
        masked = masker.mask_record(row, fields_to_mask)

        # Masked values should not equal raw values and must not leak PHI per validator
        for f in fields_to_mask:
            raw_val = str(row.get(f, ""))
            masked_val = str(masked.get(f, ""))
            assert masked_val != raw_val, f"Field {f} was not masked"

            # Deterministic: same inputs produce same masked output
            assert masker.mask_value(raw_val, f) == masked_val

            # Validator should accept the masked value (no SecurityException)
            checker.validate_line(masked_val)

    # Also assert that at least one raw row contained SSN or phone to exercise detection
    any_phi = any((patterns.SSN_RE.search(",".join(row.values())) or patterns.PHONE_RE.search(",".join(row.values()))) for row in rows)
    assert any_phi, "Test samples should include at least one SSN or phone-like value to validate detection"
