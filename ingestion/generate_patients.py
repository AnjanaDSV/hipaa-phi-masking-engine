"""
Generate synthetic patient test data for the HIPAA PHI masking engine.

Produces:
  ingestion/samples/patients_faker.csv    – 500 Faker rows
  ingestion/samples/patients_synthea.csv  – 100 Synthea-derived rows
  ingestion/samples/clinical_notes.txt    – 50 clinical notes with embedded PHI
  ingestion/samples/patients.csv          – 600-row merged file (source column added)
"""

import csv
import os
import random
import textwrap
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# ── paths ────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
SAMPLES = BASE / "samples"
SYNTHEA_CSV = BASE / "synthea" / "output" / "csv"
SAMPLES.mkdir(exist_ok=True)

fake = Faker(["en_US", "es_MX", "zh_CN", "de_DE", "hi_IN", "ar_AA"])
Faker.seed(42)
random.seed(42)

DIAGNOSES = [
    "Hypertension", "Type 2 Diabetes Mellitus", "Hyperlipidemia",
    "Asthma", "Chronic Kidney Disease", "Coronary Artery Disease",
    "Congestive Heart Failure", "Atrial Fibrillation", "COPD",
    "Obstructive Sleep Apnea", "Major Depressive Disorder",
    "Generalized Anxiety Disorder", "Hypothyroidism", "Osteoarthritis",
    "Rheumatoid Arthritis", "Gastroesophageal Reflux Disease",
    "Irritable Bowel Syndrome", "Chronic Migraine", "Anemia",
    "Peripheral Neuropathy", "Psoriasis", "Fibromyalgia",
    "Non-alcoholic Fatty Liver Disease", "Chronic Low Back Pain",
]

FIELDS = ["name", "ssn", "dob", "phone", "email", "address",
          "mrn", "diagnosis", "insurance_id"]


# ── helpers ──────────────────────────────────────────────────────────────────

def _ssn():
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"


def _dob_mixed():
    """60% MM/DD/YYYY, 40% YYYY-MM-DD to stress-test masking regexes."""
    d = fake.date_of_birth(minimum_age=18, maximum_age=90)
    if random.random() < 0.6:
        return d.strftime("%m/%d/%Y")
    return d.strftime("%Y-%m-%d")


def _phone():
    return f"{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"


def _mrn():
    return f"MRN-{random.randint(100000,999999)}"


def _ins():
    return f"INS-{random.randint(100000000,999999999)}"


# ── PART A: Faker rows ───────────────────────────────────────────────────────

def generate_faker_rows(n: int = 500) -> list[dict]:
    rows = []
    for _ in range(n):
        rows.append({
            "name": fake.name(),
            "ssn": _ssn(),
            "dob": _dob_mixed(),
            "phone": _phone(),
            "email": fake.email(),
            "address": fake.address().replace("\n", ", "),
            "mrn": _mrn(),
            "diagnosis": random.choice(DIAGNOSES),
            "insurance_id": _ins(),
            "source": "faker",
        })
    return rows


def write_faker_csv(rows: list[dict]) -> None:
    out = SAMPLES / "patients_faker.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + ["source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] patients_faker.csv  – {len(rows)} rows ->{out}")


# ── PART B: Synthea rows ─────────────────────────────────────────────────────

def load_synthea_patients() -> dict[str, dict]:
    """Return dict keyed by patient Id."""
    path = SYNTHEA_CSV / "patients.csv"
    if not path.exists():
        raise FileNotFoundError(f"Synthea patients.csv not found at {path}")
    patients = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            patients[row["Id"]] = row
    return patients


def load_synthea_conditions() -> dict[str, str]:
    """Return first condition description keyed by patient Id."""
    path = SYNTHEA_CSV / "conditions.csv"
    first: dict[str, str] = {}
    if not path.exists():
        return first
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = row["PATIENT"]
            if pid not in first:
                first[pid] = row.get("DESCRIPTION", "")
    return first


def synthea_to_schema(patients: dict[str, dict],
                      conditions: dict[str, str]) -> list[dict]:
    rows = []
    for pid, p in patients.items():
        first = p.get("FIRST", "")
        middle = p.get("MAIDEN", "") or p.get("MIDDLE", "")
        last = p.get("LAST", "")
        name_parts = [x for x in [first, middle, last] if x]
        name = " ".join(name_parts)

        city = p.get("CITY", "")
        state = p.get("STATE", "")
        zip_ = p.get("ZIP", "")
        address = f"{p.get('ADDRESS', '')}, {city}, {state} {zip_}".strip(", ")

        dob_raw = p.get("BIRTHDATE", "")
        # Synthea uses YYYY-MM-DD; keep as-is (already valid)

        rows.append({
            "name": name,
            "ssn": p.get("SSN", _ssn()),
            "dob": dob_raw,
            "phone": p.get("PHONE", _phone()),
            "email": p.get("EMAIL") or fake.email(),
            "address": address,
            "mrn": f"MRN-{pid[:6].upper()}",
            "diagnosis": conditions.get(pid) or random.choice(DIAGNOSES),
            "insurance_id": _ins(),
            "source": "synthea",
        })
    return rows


def write_synthea_csv(rows: list[dict]) -> None:
    out = SAMPLES / "patients_synthea.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + ["source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] patients_synthea.csv – {len(rows)} rows ->{out}")


# ── PART B2: Clinical notes ──────────────────────────────────────────────────

NOTE_TEMPLATES = [
    # Formal SOAP-style
    lambda p: textwrap.dedent(f"""\
        CLINIC NOTE — {fake.date_this_year().strftime('%B %d, %Y')}
        Patient: {p['name']}
        DOB: {p['dob']}  |  MRN: {p['mrn']}  |  SSN: {p['ssn']}
        Phone: {p['phone']}  |  Email: {p['email']}
        Address: {p['address']}

        Chief Complaint: Patient presents with symptoms consistent with {p['diagnosis']}.
        The patient denies fever, chills, or recent travel. Vital signs are within
        normal limits. Assessment and plan discussed at length with patient.
        Follow-up scheduled in 4 weeks.
        Attending: {fake.name()}, MD
        Insurance ID: {p['insurance_id']}
    """),

    # Abbreviated ED triage note
    lambda p: textwrap.dedent(f"""\
        ED TRIAGE NOTE
        Pt: {p['name']} (DOB: {p['dob']}, SSN: {p['ssn']})
        MRN: {p['mrn']}  Arrived: {fake.time()}
        CC: c/o symptoms r/t {p['diagnosis']} x {random.randint(1,14)} days
        Hx: {fake.sentence(nb_words=10)}
        Contact: {p['phone']} | {p['email']}
        Plan: labs, imaging per protocol. Discussed w/ attending.
    """),

    # Discharge summary
    lambda p: textwrap.dedent(f"""\
        DISCHARGE SUMMARY
        Patient Name: {p['name']}
        Medical Record #: {p['mrn']}
        Date of Birth: {p['dob']}
        Admission Diagnosis: {p['diagnosis']}
        Insurance: {p['insurance_id']}
        SSN on file: {p['ssn']}

        Hospital Course:
        {p['name']} is a patient admitted for management of {p['diagnosis']}.
        {fake.paragraph(nb_sentences=2)}
        Patient was discharged in stable condition with prescriptions and
        follow-up instructions. Next appointment arranged.
        Discharge address: {p['address']}
        Callback number: {p['phone']}
    """),

    # Progress note (informal)
    lambda p: textwrap.dedent(f"""\
        Progress Note — Provider: {fake.name()}, NP
        {fake.date_this_year().strftime('%m/%d/%Y')} {fake.time()}

        Seeing {p['name']} today (MRN {p['mrn']}, DOB {p['dob']}) for follow-up
        on {p['diagnosis']}. Pt reports {fake.sentence(nb_words=8).lower()}
        BP and labs reviewed. Medication regimen discussed.
        Pt reachable at {p['phone']} or {p['email']}.
        Ins: {p['insurance_id']}  Address: {p['address']}
    """),

    # Referral letter
    lambda p: textwrap.dedent(f"""\
        REFERRAL LETTER
        To: {fake.name()}, MD — Specialist
        Re: {p['name']}, DOB {p['dob']}, SSN {p['ssn']}
        MRN: {p['mrn']}  Insurance ID: {p['insurance_id']}

        Dear Colleague,

        I am referring {p['name']} for specialist evaluation regarding {p['diagnosis']}.
        {fake.paragraph(nb_sentences=2)}
        Please contact our office at {p['phone']} with any questions.
        Patient's current address: {p['address']}

        Sincerely,
        {fake.name()}, MD
    """),
]


def generate_clinical_notes(synthea_rows: list[dict], n: int = 50) -> str:
    notes = []
    pool = synthea_rows if len(synthea_rows) >= n else synthea_rows * (n // len(synthea_rows) + 1)
    selected = random.sample(pool, n)
    for i, patient in enumerate(selected, 1):
        template = random.choice(NOTE_TEMPLATES)
        note_text = template(patient)
        notes.append(f"{'='*70}\nNOTE #{i:02d}\n{'='*70}\n{note_text}")
    return "\n\n".join(notes)


def write_clinical_notes(notes: str) -> None:
    out = SAMPLES / "clinical_notes.txt"
    out.write_text(notes, encoding="utf-8")
    count = notes.count("NOTE #")
    print(f"[OK] clinical_notes.txt   – {count} notes ->{out}")


# ── PART C: Merge ────────────────────────────────────────────────────────────

def write_merged(faker_rows: list[dict], synthea_rows: list[dict]) -> None:
    all_rows = faker_rows + synthea_rows
    random.shuffle(all_rows)
    out = SAMPLES / "patients.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + ["source"])
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"[OK] patients.csv (merged) – {len(all_rows)} rows ->{out}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n-- Generating Faker rows --")
    faker_rows = generate_faker_rows(500)
    write_faker_csv(faker_rows)

    print("\n-- Processing Synthea output --")
    patients = load_synthea_patients()
    conditions = load_synthea_conditions()
    synthea_rows = synthea_to_schema(patients, conditions)
    write_synthea_csv(synthea_rows)

    print("\n-- Generating clinical notes --")
    notes = generate_clinical_notes(synthea_rows, n=50)
    write_clinical_notes(notes)

    print("\n-- Merging datasets --")
    write_merged(faker_rows, synthea_rows)

    print("\nDone.")


if __name__ == "__main__":
    main()
