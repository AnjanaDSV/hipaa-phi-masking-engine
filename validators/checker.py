"""validators.checker
Line-by-line validation scanner that enforces 0% leakage by raising SecurityException
on any detected SSN or Phone pattern in post-processed strings.

Defensive: validates inputs and never swallows regex errors.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from core import patterns
from core.masker import SecurityException

logger = logging.getLogger(__name__)


def validate_line(line: str, line_num: Optional[int] = None) -> None:
    """Validate a single line/string for leaked SSN or phone patterns.

    Raises SecurityException (uncatchable BaseException) immediately on detection.
    """
    if not isinstance(line, str):
        raise ValueError("line must be a string")

    try:
        if patterns.SSN_RE.search(line):
            msg = f"SSN pattern detected in output{f' at line {line_num}' if line_num is not None else ''}: {line}"
            logger.critical(msg)
            raise SecurityException(msg)
        if patterns.PHONE_RE.search(line):
            msg = f"Phone pattern detected in output{f' at line {line_num}' if line_num is not None else ''}: {line}"
            logger.critical(msg)
            raise SecurityException(msg)
    except re.error as exc:  # defensive: regex engine failure
        logger.exception("Regex error while validating line: %s", exc)
        raise


def validate_stream(lines: Iterable[str]) -> None:
    """Validate an iterable stream of strings line-by-line.

    Raises SecurityException on first detection.
    """
    if lines is None:
        raise ValueError("lines iterable is required")

    for idx, line in enumerate(lines, start=1):
        validate_line(line, line_num=idx)


__all__ = ["validate_line", "validate_stream"]
