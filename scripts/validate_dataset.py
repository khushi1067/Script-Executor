import re

from scripts.dataset import MAX_AGE, MIN_AGE, REQUIRED_COLUMNS, dataset_rows


def record_findings(record):
    """Identify each invalid field and the reason it needs attention."""
    findings = [
        (field, "missing", f"Missing required field: {field}")
        for field in REQUIRED_COLUMNS["validate_dataset"]
        if not record[field].strip()
    ]

    age = record["age"].strip()
    if age:
        try:
            age_value = int(age)
        except ValueError:
            findings.append(("age", "invalid", "Age must be a whole number"))
        else:
            if not MIN_AGE <= age_value <= MAX_AGE:
                findings.append(("age", "invalid", f"Age must be between {MIN_AGE} and {MAX_AGE}"))

    email = record["email"].strip()
    if email and not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
        findings.append(("email", "invalid", "Email must have a format like name@example.com"))
    return findings


def validate_dataset(dataset=None):
    """Check required fields, whole-number ages (0–120), and basic email format."""
    issues = []
    total_records = 0

    with dataset_rows(dataset) as reader:
        for row_number, record in enumerate(reader, start=2):
            total_records += 1
            errors = [message for _, _, message in record_findings(record)]
            if errors:
                issues.append({"row_number": row_number, "errors": errors})

    return {
        "message": "Dataset validation completed.",
        "total_records": total_records,
        "valid_records": total_records - len(issues),
        "invalid_records": len(issues),
        "issues": issues,
    }
