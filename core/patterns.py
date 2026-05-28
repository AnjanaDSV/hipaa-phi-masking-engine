"""core.patterns
Compiled PHI-detection regular expressions used across the pipeline.
Contains: SSN, Phone, DOB, and a simple Name heuristic.
Defensive and deterministic — suitable for validator checks.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Compiled regexes for PHI detection
try:
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")  # 123-45-6789
    PHONE_RE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")  # 800-555-1212
    DOB_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b")  # 1980-01-31 or 01/31/1980
    # Simple name heuristic: two or more capitalized words (First Last [Middle])
    NAME_HEURISTIC_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")

    PATTERNS: Dict[str, re.Pattern] = {
        "ssn": SSN_RE,
        "phone": PHONE_RE,
        "dob": DOB_RE,
        "name": NAME_HEURISTIC_RE,
    }
except re.error as exc:
    logger.exception("Failed compiling PHI regex patterns: %s", exc)
    raise


def detect_phi(text: str) -> Dict[str, List[str]]:
    """Scan text and return any PHI matches grouped by pattern key.

    Defensive: validates inputs and never swallows regex errors.
    """
    if not isinstance(text, str):
        raise ValueError("detect_phi expects a string")

    matches: Dict[str, List[str]] = {}
    try:
        for key, pattern in PATTERNS.items():
            found = pattern.findall(text)
            if found:
                matches[key] = found
    except re.error as exc:
        logger.exception("Regex scanning failed: %s", exc)
        raise
    return matches


__all__ = ["SSN_RE", "PHONE_RE", "DOB_RE", "NAME_HEURISTIC_RE", "PATTERNS", "detect_phi"]
