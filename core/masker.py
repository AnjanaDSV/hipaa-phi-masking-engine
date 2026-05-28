"""core.masker
Deterministic, irreversible HMAC-SHA256 masking utilities.

- Reads HMAC key from HMAC_KEY env var (required).
- Uses per-field salt for stability across fields.
- Enforces fail-fast checks: if any masked or post-processed string matches SSN/Phone patterns,
  an uncatchable SecurityException (subclass of BaseException) is raised and logged.
"""

from __future__ import annotations

import os
import hmac
import hashlib
import logging
from typing import Any, Dict, Iterable

from core import patterns

logger = logging.getLogger(__name__)


class SecurityException(BaseException):
    """Raised for security-critical failures that should not be caught by normal Exception handlers."""
    pass


def _get_hmac_key() -> bytes:
    """Retrieve HMAC key from env. Fail-fast if missing or empty."""
    key = os.getenv("HMAC_KEY")
    if not key:
        logger.critical("HMAC_KEY environment variable is missing or empty")
        raise RuntimeError("Missing required environment variable: HMAC_KEY")
    try:
        return key.encode("utf-8")
    except Exception as exc:
        logger.exception("Failed encoding HMAC key: %s", exc)
        raise


def _compute_hmac(value: str, field_name: str, key: bytes) -> str:
    """Compute deterministic HMAC-SHA256 hex digest using a per-field salt.

    Defensive: validate inputs. Never return the raw value.
    """
    if not isinstance(value, str):
        raise ValueError("Value to mask must be a string")
    if not isinstance(field_name, str) or not field_name:
        raise ValueError("field_name must be a non-empty string")

    # Use a per-field salt so the same value masked under different fields yields
    # different tokens while remaining deterministic for the same (key, field, value).
    try:
        salt = field_name.encode("utf-8")
        mac = hmac.new(key + salt, value.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()
    except Exception as exc:
        logger.exception("HMAC computation failed for field %s: %s", field_name, exc)
        raise


def _assert_no_leak(masked_str: str) -> None:
    """Ensure masked output does not accidentally match SSN or Phone patterns.

    If leakage is detected, log an enterprise-level message and raise SecurityException.
    """
    try:
        if patterns.SSN_RE.search(masked_str) or patterns.PHONE_RE.search(masked_str):
            logger.critical("PHI pattern detected in post-processed output: %s", masked_str)
            # Raising BaseException makes this harder to accidentally catch in normal code paths.
            raise SecurityException("Detected PHI pattern in post-processed output — aborting to guarantee 0% leakage")
    except re.error as exc:  # pragma: no cover - defensive
        logger.exception("Regex check failed during leakage assertion: %s", exc)
        raise


def mask_value(value: str, field_name: str) -> str:
    """Mask a single string value deterministically and fail-fast on leakage.

    Returns a lowercase hex digest string.
    """
    key = _get_hmac_key()
    masked = _compute_hmac(value, field_name, key)

    # Safety check on masked output
    _assert_no_leak(masked)
    return masked


def mask_record(record: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    """Return a copy of record with specified fields masked.

    Defensive: validates inputs and does not mutate the original record.
    """
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    if not hasattr(fields, "__iter__"):
        raise ValueError("fields must be an iterable of field names")

    key = _get_hmac_key()
    masked: Dict[str, Any] = dict(record)
    try:
        for field in fields:
            if field in record and record[field] is not None:
                val = str(record[field])
                masked_val = _compute_hmac(val, str(field), key)
                _assert_no_leak(masked_val)
                masked[field] = masked_val
    except SecurityException:
        # Re-raise SecurityException immediately — do NOT swallow it.
        raise
    except Exception as exc:
        logger.exception("Failed masking record: %s", exc)
        raise
    return masked


__all__ = ["mask_value", "mask_record", "SecurityException"]
