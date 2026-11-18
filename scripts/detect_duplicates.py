from scripts.dataset import dataset_rows


def duplicate_groups(columns, rows):
    """Group matching IDs while retaining source row numbers and column values."""
    if not rows:
        return {}
    id_index = columns.index("record_id")
    by_id = {}
    for row_number, values in enumerate(rows, start=2):
        record_id = values[id_index].strip()
        if record_id:
            by_id.setdefault(record_id, []).append((row_number, values))

    return {
        record_id: {
            "record_id": record_id,
            "row_numbers": [row for row, _ in records],
            "record_values": [list(values) for _, values in records],
        }
        for record_id, records in by_id.items()
        if len(records) > 1
    }


def detect_duplicates(dataset=None):
    """Find nonempty record IDs that appear more than once."""
    with dataset_rows(dataset) as reader:
        columns = reader.fieldnames or []
        rows = [tuple(record[column] for column in columns) for record in reader]

    duplicates = list(duplicate_groups(columns, rows).values())
    return {
        "message": "Duplicate detection completed.",
        "total_records": len(rows),
        "duplicate_id_count": len(duplicates),
        "duplicate_rows": sum(len(group["row_numbers"]) - 1 for group in duplicates),
        "record_columns": columns,
        "duplicates": duplicates,
    }
