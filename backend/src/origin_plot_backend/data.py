"""Read tabular data without reordering rows or inventing missing values."""
import csv
import math
from datetime import date, datetime
from pathlib import Path


def _records(rows, row_numbers=None):
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
        if row_numbers is not None:
            row_numbers.append(index)
    if not result:
        raise ValueError("The table has no data rows.")
    return result


def read_table(path, sheet=None, *, row_numbers=None):
    src = Path(path).expanduser().resolve(strict=True)
    suffix = src.suffix.lower()
    if suffix in (".csv", ".tsv"):
        if sheet:
            raise ValueError("sheet is only available for XLSX inputs.")
        with src.open(encoding="utf-8-sig", newline="") as handle:
            return _records(csv.reader(handle, delimiter="\t" if suffix == ".tsv" else ","), row_numbers)
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(src, read_only=True, data_only=True)
        try:
            if sheet and sheet not in book.sheetnames:
                raise ValueError(f"Worksheet {sheet!r} not found. Choices: {', '.join(book.sheetnames)}")
            worksheet = book[sheet] if sheet else book.active
            return _records(worksheet.values, row_numbers)
        finally:
            book.close()
    raise ValueError("Supported inputs are UTF-8 CSV/TSV and XLSX.")


def read_bindings(path, sheet, bindings):
    if not path or not isinstance(bindings, list) or not bindings:
        raise ValueError("Provide data_path and at least one binding with layer, plot and columns.")
    tables, numbers, targets, selections = {}, {}, set(), []
    required = ({"x", "y"}, {"x", "y", "y_error"}, {"value"}, {"row", "column", "value"})
    for spec in bindings:
        if not isinstance(spec, dict) or set(spec) - {"layer", "plot", "columns", "sheet", "plot_type", "units", "options"}:
            raise ValueError("Binding fields are layer, plot, columns, sheet, plot_type, units and options.")
        layer, plot = spec.get("layer"), spec.get("plot")
        if any(type(i) is not int or i < 1 for i in (layer, plot)) or (layer, plot) in targets:
            raise ValueError("Each binding needs a distinct positive layer and plot number.")
        targets.add((layer, plot))
        columns = spec.get("columns")
        if (not isinstance(columns, dict) or set(columns) not in required
                or any(not isinstance(value, str) or not value for value in columns.values())
                or len(set(columns.values())) != len(columns)):
            raise ValueError(f"Layer {layer}, plot {plot}: map distinct X/Y, X/Y/Y-error, value, or row/column/value columns.")
        selected = spec.get("sheet", sheet)
        if selected is not None and (not isinstance(selected, str) or not selected):
            raise ValueError("Specify the Excel worksheet by its name.")
        if selected not in tables:
            numbers[selected] = []
            tables[selected] = read_table(path, selected, row_numbers=numbers[selected])
        missing = set(columns.values()) - tables[selected][0].keys()
        if missing:
            raise ValueError(f"Layer {layer}, plot {plot}: missing column(s) {', '.join(sorted(missing))}. "
                             f"Available: {', '.join(tables[selected][0])}")
        units = spec.get("units", {})
        if (not isinstance(units, dict) or set(units) - columns.keys()
                or any(not isinstance(value, str) for value in units.values())):
            raise ValueError("Units must be text keyed by mapped column roles.")
        if "options" in spec and not isinstance(spec["options"], dict):
            raise ValueError("Binding options must be an object.")
        selections.append({**spec, "sheet": selected})
    return {"bindings": sorted(selections, key=lambda item: (item["layer"], item["plot"])),
            "tables": [{"sheet": name, "records": rows, "row_numbers": numbers[name]} for name, rows in tables.items()]}
