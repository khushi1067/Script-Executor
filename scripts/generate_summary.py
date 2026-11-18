from collections import Counter, defaultdict
from statistics import median

from scripts.dataset import MAX_AGE, MIN_AGE, dataset_rows

AGE_RANGES = [
    ("0–17", 0, 17),
    ("18–24", 18, 24),
    ("25–34", 25, 34),
    ("35–44", 35, 44),
    ("45–54", 45, 54),
    ("55–64", 55, 64),
    ("65+", 65, MAX_AGE),
]
CITY_RECORD_COLUMNS = {"record_id": "Record ID", "name": "Name", "age": "Age"}


def generate_summary(dataset=None):
    """Summarize unique IDs, explore records by city, and report valid age ranges."""
    unique_ids = set()
    by_city = defaultdict(list)
    legacy_counts = Counter()
    ages = []
    missing_ages = 0
    invalid_ages = 0

    with dataset_rows(dataset) as reader:
        columns = set(reader.fieldnames or [])
        fields = {column: label for column, label in CITY_RECORD_COLUMNS.items() if column in columns}
        for number, record in enumerate(reader, start=2):
            record_id = record.get("record_id", "").strip()
            if record_id:
                unique_ids.add(record_id)
            city = record["city"].strip() or None
            legacy_counts[city or "Unknown"] += 1
            by_city[city].append({"CSV row": number, **{label: record[column] for column, label in fields.items()}})
            if "age" in fields:
                age = record["age"].strip()
                if not age:
                    missing_ages += 1
                    continue
                try:
                    value = int(age)
                except ValueError:
                    invalid_ages += 1
                else:
                    if MIN_AGE <= value <= MAX_AGE:
                        ages.append(value)
                    else:
                        invalid_ages += 1

    age_summary = None
    if "age" in fields:
        counts = Counter(ages)
        age_summary = {
            "valid_count": len(ages),
            "missing_count": missing_ages,
            "invalid_count": invalid_ages,
            "median": median(ages) if ages else None,
            "ranges": [
                {"range": label, "count": sum(counts[age] for age in range(low, high + 1))}
                for label, low, high in AGE_RANGES
            ],
        }

    groups = sorted(by_city.items(), key=lambda item: (-len(item[1]), item[0] is None, (item[0] or "").casefold()))
    return {
        "message": "Dataset summary generated.",
        "total_records": sum(legacy_counts.values()),
        "unique_record_ids": len(unique_ids) if "record_id" in fields else None,
        "city_count": len(by_city) - (None in by_city),
        "records_by_city": dict(legacy_counts),
        "city_groups": [{"city": city, "records": records} for city, records in groups],
        "age_summary": age_summary,
    }
