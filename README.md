# HIPAA PHI Masking Engine

A production-ready backend service for HIPAA-compliant masking of Protected Health Information (PHI) in patient data files. Built with FastAPI, it deterministically masks sensitive fields using HMAC-SHA256, validates zero PHI leakage, and maintains a full audit trail.

---

## Features

- **Deterministic Masking** — HMAC-SHA256 with per-field salts ensures the same input always produces the same masked token, enabling safe deduplication
- **Zero-Leakage Guarantee** — Multi-layer validation scans every output field for SSN, phone number, and DOB patterns before writing results
- **Async/Streaming Architecture** — Row-by-row processing keeps memory footprint minimal even for large files
- **Full Audit Trail** — Every masking job is logged to a SQLite database with status, row counts, and processing notes
- **Fail-Fast Security** — Any leakage detection raises an uncatchable `SecurityException` that halts the pipeline immediately

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| Masking | HMAC-SHA256 (Python `hmac` stdlib) |
| Database / ORM | SQLite + SQLAlchemy |
| Testing | Pytest |
| Linting | Ruff |

---

## Project Structure

```
safe-sync-backend/
├── api/
│   ├── background_worker.py   # Async job processor (CSV/JSONL masking pipeline)
│   └── v1/
│       └── mask_router.py     # POST /api/v1/mask endpoint
├── core/
│   ├── masker.py              # HMAC-SHA256 masking engine with per-field salts
│   └── patterns.py            # Compiled regex patterns for PHI detection
├── db/
│   └── models.py              # AuditLog ORM model and DB session utilities
├── validators/
│   └── checker.py             # Post-masking PHI leakage scanner
├── ingestion/
│   └── samples/
│       ├── patients.csv           # Mock patient data for testing
│       └── patients.masked.csv    # Example masked output
├── tests/
│   ├── test_api.py
│   └── test_masking.py        # End-to-end masking pipeline tests
├── main.py                    # FastAPI app entrypoint
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- A secret HMAC key (never commit this)

### Installation

```bash
python -m venv .venv
.venv\Scripts\Activate     # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### Environment Variables

| Variable | Description | Required |
|---|---|---|
| `HMAC_KEY` | Secret key used for HMAC-SHA256 masking | Yes |
| `DATABASE_URL` | SQLAlchemy DB URL (defaults to `sqlite:///audit.db`) | No |

```bash
export HMAC_KEY="your-secret-key-here"
```

### Run the Server

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

---

## API Usage

### `POST /api/v1/mask`

Submit a file for PHI masking. Processing runs asynchronously in the background.

**Request**

```json
{
  "input_path": "ingestion/samples/patients.csv"
}
```

**Response** — `202 Accepted`

```json
{
  "job_id": "3f7a1c2e-...",
  "status": "PENDING"
}
```

The masked output is written to `<original_filename>.masked.<ext>` alongside the input file. Use the `job_id` to query the `audit.db` for job status.

### Supported Formats

- CSV (`.csv`)
- Newline-delimited JSON (`.jsonl` / `.ndjson`)

---

## PHI Fields Masked

The engine detects and masks the following field types:

| Field | Detection Pattern |
|---|---|
| SSN | `\d{3}-\d{2}-\d{4}` |
| Phone Number | `\d{3}-\d{3}-\d{4}` |
| Date of Birth | Multiple date formats (MM/DD/YYYY, YYYY-MM-DD, etc.) |
| Patient Name | Capitalized word sequences |

All sensitive fields are replaced with truncated hex digests, e.g. `a3f1b2c4d5e6...`

---

## How It Works

```
Input File (CSV/JSONL)
        │
        ▼
 Background Worker
  ┌─────────────────────────────────────┐
  │  1. Stream rows one-by-one          │
  │  2. Normalize field names           │
  │  3. Mask PHI fields (HMAC-SHA256)   │
  │  4. Validate each masked field      │  ← SecurityException on leakage
  │  5. Write row to .masked output     │
  │  6. Update audit log every 50 rows  │
  └─────────────────────────────────────┘
        │
        ▼
  Masked Output File + Audit Log Entry
```

If any masked value accidentally matches a PHI pattern, the pipeline raises `SecurityException` (a `BaseException` subclass — uncatchable by normal `except Exception` handlers) and marks the job as `FAILED`.

---

## Audit Trail

All jobs are recorded in the `audit.db` SQLite database:

| Column | Description |
|---|---|
| `job_id` | UUID4 identifier |
| `created_at` | Job submission timestamp |
| `status` | `PENDING` → `IN_PROGRESS` → `COMPLETED` / `FAILED` |
| `rows_processed` | Running count, updated every 50 rows |
| `leaked_rows` | Count of rows where leakage was detected |
| `processing_notes` | Human-readable log of pipeline events |

Inspect the audit DB directly:

```bash
python check_db.py
```

---

## Running Tests

```bash
pytest -q
```

The test suite includes:
- End-to-end masking pipeline against the sample patient CSV
- Determinism checks (same input → same masked token)
- PHI leakage detection on masked output

---

## Linting

```bash
ruff check .
```

---

## Security Notes

- The `HMAC_KEY` must never be committed to source control. Use environment variables or a secrets manager.
- Masking is **irreversible** — there is no decryption path by design.
- Per-field salts prevent cross-field correlation (masking the same SSN under "ssn" vs "phone" yields different tokens).
- The `SecurityException` design intentionally bypasses normal exception handling to guarantee pipeline halt on any leakage event.

---

## HIPAA Compliance Considerations

This engine is designed to support HIPAA Safe Harbor de-identification (45 CFR §164.514(b)) by masking the 18 PHI identifiers. It is a technical control — proper HIPAA compliance also requires organizational policies, access controls, and a BAA with any service providers.

---

## License

MIT
