"""Shared CSV input for the approved workflows."""

import csv
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

MAX_DATASET_MB = 5
MAX_DATASET_BYTES = MAX_DATASET_MB * 1024 * 1024
MIN_AGE = 0
MAX_AGE = 120
SAMPLE_DATASET = Path(__file__).resolve().parent.parent / "sample_data" / "records.csv"
REQUIRED_COLUMNS = {
    "validate_dataset": ("record_id", "name", "age", "city", "email"),
    "detect_duplicates": ("record_id",),
    "generate_summary": ("city",),
}


@contextmanager
def dataset_rows(dataset=None):
    """Use request-local CSV text or the bundled sample for legacy runs."""
    source = (
        SAMPLE_DATASET.open(newline="", encoding="utf-8-sig")
        if dataset is None
        else StringIO(dataset, newline="")
    )
    with source:
        yield csv.DictReader(source, restval="", strict=True)


def validate_upload(data, script_name):
    """Check encoding, required headers, and CSV structure before starting a run."""
    try:
        dataset = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Upload a UTF-8 encoded CSV file.") from None
    if not dataset.strip() or "\x00" in dataset:
        raise ValueError("Upload a non-empty CSV file containing text.")

    try:
        with dataset_rows(dataset) as rows:
            columns = rows.fieldnames or []
            if len(columns) != len(set(columns)) or "" in columns:
                raise ValueError("CSV headers must be unique and non-empty.")
            missing = [column for column in REQUIRED_COLUMNS[script_name] if column not in columns]
            if missing:
                raise ValueError(f"Missing required CSV columns: {', '.join(missing)}.")
            if any(None in row for row in rows):
                raise ValueError("A CSV row contains more fields than the header.")
    except csv.Error:
        raise ValueError("The CSV is malformed or contains an oversized field.") from None
    return dataset
