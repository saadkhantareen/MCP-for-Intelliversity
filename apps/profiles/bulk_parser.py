"""
Reads an uploaded CSV or XLSX file and returns a list[dict].
"""

import csv
import io

import openpyxl


def parse_uploaded_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return _parse_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        return _parse_xlsx(uploaded_file)
    return [], "Unsupported file type. Please upload a .csv or .xlsx file."


def _parse_csv(uploaded_file):
    try:
        decoded = uploaded_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded))
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        rows = [dict(row) for row in reader]
        return rows, None
    except Exception as exc:
        return [], f"Failed to read CSV: {exc}"


def _parse_xlsx(uploaded_file):
    try:
        wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        raw_headers = next(rows_iter)
        headers = [
            str(h).strip().lower() if h else f"col_{i}"
            for i, h in enumerate(raw_headers)
        ]
        rows = []
        for row_values in rows_iter:
            if all(v is None for v in row_values):
                continue
            row_dict = {}
            for header, value in zip(headers, row_values):
                row_dict[header] = str(value).strip() if value is not None else ""
            rows.append(row_dict)
        wb.close()
        return rows, None
    except Exception as exc:
        return [], f"Failed to read Excel file: {exc}"
