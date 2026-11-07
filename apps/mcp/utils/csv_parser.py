import csv
import io


def parse_students_csv(csv_text: str):
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        raise ValueError("Empty CSV")

    required = {"email", "first_name", "last_name", "registration_id"}
    lower_fields = {h.lower().strip() for h in reader.fieldnames}
    if not required.issubset(lower_fields):
        raise ValueError(f"CSV must have headers: {', '.join(sorted(required))}")

    normalized = []
    for row in reader:
        normalized.append(
            {k.lower().strip(): (v.strip() if isinstance(v, str) else "") for k, v in row.items()}
        )
    return normalized
