# HIPAA PHI Masking Engine

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)
![HIPAA Compliant](https://img.shields.io/badge/HIPAA-Compliant-green?logo=healthicons&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Pytest](https://img.shields.io/badge/Tested%20with-Pytest-0A9EDC?logo=pytest&logoColor=white)

A production-ready backend service for HIPAA-compliant masking of Protected Health Information (PHI) in patient data files. Built with FastAPI, it deterministically masks sensitive fields using HMAC-SHA256, validates zero PHI leakage, and maintains a full audit trail.

---

## Features

- **Deterministic Masking** — HMAC-SHA256 with per-field salts ensures the same input always produces the same masked token, enabling safe deduplication
- **Zero-Leakage Guarantee** — Multi-layer validation scans every output field for SSN, phone number, and DOB patterns before writing results
- **Async/Streaming Architecture** — Row-by-row processing keeps memory footprint minimal even for large files
- **Full Audit Trail** — Every masking job is logged to a SQLite database with status, row counts, and processing notes
- **Fail-Fast Security** — Any leakage detection raises an uncatchable `SecurityException` that halts the pipeline immediately

---

## Why This Matters

Healthcare data breaches cost the industry an average of **$10.9 million per incident** — the highest of any sector for 13 consecutive years (IBM Cost of a Data Breach Report, 2023). Patient records contain some of the most sensitive personal information that exists: Social Security numbers, diagnoses, dates of birth, and contact details that, once exposed, cannot be changed.

Most data pipelines treat PHI masking as an afterthought — a find-and-replace at the end. This engine inverts that assumption:

- **Masking is the pipeline.** PHI never travels through the system unmasked; it is detected and replaced at the point of ingestion.
- **Validation is non-optional.** Every output field is scanned before it is written. A single leaked SSN causes the entire job to fail loudly, not silently.
- **Auditability is built in.** Compliance requires evidence — not just that masking happened, but when, how many rows were processed, and whether any leakage occurred. Every job produces an immutable audit record.

This engine is designed for data engineering teams that need to move patient data between systems (EHR exports, analytics pipelines, vendor handoffs) without exposing PHI at any step.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| Masking | HMAC-SHA256 (Python `hmac` stdlib) |
| Database / ORM | SQLite + SQLAlchemy |
| Testing | Pytest |
| Linting | Ruff |
| Test Data | Faker (structured) + Synthea (clinical records) |

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
│   ├── generate_patients.py       # Script to regenerate all test data
│   ├── synthea/                   # Synthea jar + generated CSV output
│   └── samples/
│       ├── patients.csv           # 600 synthetic patient records (500 Faker + 100 Synthea)
│       ├── patients_faker.csv     # 500 Faker-generated rows
│       ├── patients_synthea.csv   # 111 Synthea-derived rows
│       └── clinical_notes.txt     # 50 unstructured clinical notes with embedded PHI
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

The included test dataset contains 600 synthetic patient records — 500 generated with Faker for schema coverage and format diversity, 100 from Synthea (the industry-standard synthetic patient generator used in healthcare research) for clinical realism. Includes 50 unstructured clinical notes with naturally embedded PHI to test both structured and free-text masking.

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

## Regenerate Test Data

Requires Java 24+ and Python 3.10+ with `faker` installed.

```bash
cd ingestion/synthea
java -jar synthea-with-dependencies.jar -p 100 \
  --exporter.csv.export=true \
  --exporter.fhir.export=false Massachusetts
cd ../..
python ingestion/generate_patients.py
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

## Roadmap

- [ ] **`GET /api/v1/status/{job_id}`** — Poll job progress without querying the DB directly
- [ ] **`GET /api/v1/download/{job_id}`** — Serve the masked output file securely via a signed URL or stream
- [ ] **Expanded PHI coverage** — Add masking for MRN, NPI, ZIP codes, email addresses, and IP addresses to cover all 18 HIPAA Safe Harbor identifiers
- [ ] **Alembic migrations** — Replace `create_all()` with versioned schema migrations for production deployments
- [ ] **Docker support** — `Dockerfile` and `docker-compose.yml` for containerized deployment
- [ ] **Cloud storage backends** — Read/write directly from S3, Azure Blob, or GCS instead of local filesystem paths
- [ ] **Configurable masking strategies** — Support pseudonymization (format-preserving) and redaction (`[REDACTED]`) in addition to HMAC tokenization
- [ ] **CI/CD pipeline** — GitHub Actions workflow for lint, test, and security scan on every pull request

---

## License

MIT
