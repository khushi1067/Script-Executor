"""Build a dataset health report and apply explicit duplicate-review decisions."""

import csv
from io import StringIO

from scripts.dataset import MAX_DATASET_BYTES, MAX_DATASET_MB, dataset_rows, validate_upload
from scripts.detect_duplicates import duplicate_groups
from scripts.validate_dataset import record_findings


def check_dataset(data):
    if len(data) > MAX_DATASET_BYTES:
        raise ValueError(f"Choose a CSV file that is {MAX_DATASET_MB} MB or smaller.")
    dataset = validate_upload(data, "validate_dataset")
    with dataset_rows(dataset) as reader:
        columns = reader.fieldnames
        rows = [tuple(record[column] for column in columns) for record in reader]

    return dataset_report(columns, rows)


def field_label(field):
    return "Record ID" if field == "record_id" else field.replace("_", " ").capitalize()


def dataset_report(columns, rows):
    findings = {"missing": [], "invalid": []}
    for row, values in enumerate(rows, start=2):
        for field, category, message in record_findings(dict(zip(columns, values))):
            findings[category].append({
                "CSV row": row,
                "Field": field_label(field),
                "What to review": f"{field_label(field)} is blank." if category == "missing" else message,
            })

    return {
        "columns": columns,
        "rows": rows,
        **findings,
        "duplicates": duplicate_groups(columns, rows),
    }


def correct_row(report, decisions, row, updates):
    columns = report["columns"]
    values = dict(zip(columns, report["rows"][row - 2]))
    changed = {field: value for field, value in updates.items() if value != values[field]}
    if not changed:
        raise ValueError("Enter a new value in at least one field.")
    if any("\x00" in value or len(value) > csv.field_size_limit() for value in changed.values()):
        raise ValueError("Enter a shorter value using ordinary text.")
    values.update(changed)
    for field, category, message in record_findings(values):
        if field in changed:
            raise ValueError(f"Enter a value for {field_label(field)}." if category == "missing" else message)

    rows = report["rows"].copy()
    rows[row - 2] = tuple(values[column] for column in columns)
    updated = dataset_report(columns, rows)
    retained = {
        record_id: kept_row for record_id, kept_row in decisions.items()
        if record_id in updated["duplicates"]
        and updated["duplicates"][record_id]["row_numbers"] == report["duplicates"][record_id]["row_numbers"]
    }
    return updated, retained


def matching_groups(report):
    """Identify exact row matches within each repeated ID."""
    return {
        record_id: group["row_numbers"][0]
        for record_id, group in report["duplicates"].items()
        if all(values == group["record_values"][0] for values in group["record_values"])
    }


def rows_to_remove(report, decisions):
    removed = set()
    for record_id, kept_row in decisions.items():
        group = report["duplicates"].get(record_id)
        if group and kept_row in group["row_numbers"]:
            removed.update(row for row in group["row_numbers"] if row != kept_row)
    return removed


def build_cleaned_csv(report, removed):
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(report["columns"])
    writer.writerows(row for number, row in enumerate(report["rows"], start=2) if number not in removed)
    return output.getvalue().encode("utf-8")
