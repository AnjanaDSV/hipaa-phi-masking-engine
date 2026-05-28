# Copilot instructions — HIPAA data-masking backend (FastAPI)

Purpose
- FastAPI-based backend to ingest mock patient JSON/CSV, mask PHI, validate 0% leakage, and record an audit trail.

Detected state
- No build/test/lint scripts or CI detected in repo root. Project skeleton expected (ingestion/, core/, validators/, api/, db/, tests/).

Build, test, and lint (expected / recommended)
- Install: python -m venv .venv && .venv\Scripts\Activate && pip install -r requirements.txt
- Run full test suite: pytest -q
- Run a single test: pytest tests/test_masking.py::test_masking_example -q
- Linting (if added): ruff check .  or flake8 .

High-level architecture (what assistants need to know)
- ingestion/: reads CSV/JSON into async row streams. Keep raw files isolated (ingestion/samples/).
- core/: masker.py provides irreversible HMAC-SHA256-based masking and patterns.py holds compiled regexes for PHI (SSN, DOB, Phone, Name heuristics).
- validators/: checker.py scans masked output line-by-line; any PHI regex match must fail the job and be audited.
- api/v1/: mask_router.py exposes POST /api/v1/mask. Endpoint should enqueue an async background worker and return a job id. Background worker orchestrates ingestion → masking → validation → export and writes an audit record.
- db/: SQLAlchemy models for audit trail (AuditLog: job_id, timestamp, operator, input_path, output_path, rows_processed, leaked_rows, status, notes). DATABASE_URL via env (default: sqlite:///./audit.db).
- scripts/: lightweight CLI helper for local runs (run_masking.py).

Key conventions and patterns
- Secrets: HMAC key must come from HMAC_KEY (env). Never commit keys; use rotation-friendly design.
- Masking policy: irreversible hashing (HMAC-SHA256) with per-field salts for stability when deduping required. Deterministic outputs are allowed but reversible tokenization is NOT used in this repo.
- Regex standards: use anchored, compiled regex objects stored in core/patterns.py. Validator relies on the same patterns to detect leakage.
- I/O: stream rows (async generator) and write masked output incrementally to avoid keeping PHI in memory.
- Job/ID: use UUID4 for job ids. All audit records indexed by job_id.
- Fail-fast validation: pipeline must never write a final "clean" output unless validators report zero matches.
- DB auditing: all pipeline steps (start, completed, failure) log structured messages and metrics to the audit DB.
- Tests: tests/ should include unit tests for masker, integration tests for end-to-end pipeline, and a test fixture with small sample files in ingestion/samples/.

Files AI should edit/create first
- pyproject.toml or requirements.txt (explicit deps: fastapi, uvicorn, sqlalchemy, alembic (optional), pytest, ruff)
- core/patterns.py and core/masker.py
- validators/checker.py
- api/v1/mask_router.py and api/background_worker.py
- db/models.py
- tests/test_masking.py and ingestion/samples/patients.csv

Assistant guidance (how to generate code here)
- Produce async implementations where I/O is involved (FastAPI endpoints, file streaming).
- Use environment variables for secrets and DB connection strings; add sensible defaults for local dev.
- Add small, focused unit tests first. Provide a simple CLI runner for manual verification.
- Avoid committing real PHI or secrets in tests/samples; use anonymized mock data.

If this file exists, suggest small additions only (new commands, detected CI files, or updated conventions).

Summary
- Created concise instructions covering detected state, recommended commands, architecture, and repo-specific conventions. Ask if further adjustments or more granular examples are desired.


ROLE & QUALITY STANDARDS:
You act as a strict Senior HIPAA Compliance Officer and Lead Data Architect.

MANDATORY EXECUTION RULES:
1. Every Python file generated must contain explicit defensive exceptions.
2. If any post-processed string or final pipeline output matches standard patterns for Social Security Numbers (SSN: \d{3}-\d{2}-\d{4}) or Phone Numbers (\d{3}-\d{3}-\d{4}), the application must immediately halt execution, trigger an enterprise error log, and raise an uncatchable security exception to guarantee 0% data leakage.
