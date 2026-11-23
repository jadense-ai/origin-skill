"""Read tabular data without reordering rows or inventing missing values."""
import csv
import math
from datetime import date, datetime
from pathlib import Path


def _records(rows):
    rows = iter(rows)
    header = next(rows, None)
    if not header:
        raise ValueError("The table is empty.")
    names = [str(v).strip() if v is not None else "" for v in header]
    if not all(names) or len(names) != len(set(names)):
        raise ValueError("Column names must be nonempty and unique.")
    result = []
    for index, row in enumerate(rows, start=2):
        if not any(value is not None and value != "" for value in row):
            continue
        if len(row) != len(names):
            raise ValueError(f"Row {index} has {len(row)} cells, expected {len(names)}.")
        converted = {}
        for name, value in zip(names, row):
            if isinstance(value, (datetime, date)):
                value = value.isoformat()
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"Row {index}, column {name} has a nonfinite value.")
            converted[name] = value
        result.append(converted)
    if not result:
        raise ValueError("The table has no data rows.")
    return result


def read_table(path, sheet=None):
    src = Path(path).expanduser().resolve(strict=True)
    suffix = src.suffix.lower()
    if suffix in (".csv", ".tsv"):
        if sheet:
            raise ValueError("sheet is only available for XLSX inputs.")
        with src.open(encoding="utf-8-sig", newline="") as handle:
            return _records(csv.reader(handle, delimiter="\t" if suffix == ".tsv" else ","))
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(src, read_only=True, data_only=True)
        try:
            worksheet = book[sheet] if sheet else book.active
            return _records(worksheet.values)
        finally:
            book.close()
    raise ValueError("Supported inputs are UTF-8 CSV/TSV and XLSX.")
