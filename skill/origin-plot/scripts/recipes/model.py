"""Scientific input contract shared by the offline checker and embedded Origin."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[2] / "assets" / "recipes"


class RecipeError(ValueError):
    """An input or declared plotting rule is unsuitable for this recipe."""


def specification(recipe_id):
    if not isinstance(recipe_id, str) or not recipe_id.isascii() or not all(
        char.isalnum() or char == "-" for char in recipe_id
    ):
        raise RecipeError("Invalid recipe ID")
    path = ASSETS / recipe_id / "recipe.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe {recipe_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value, field_name):
    try:
        v = float(value)
    except (ValueError, TypeError) as exc:
        raise RecipeError(f"{field_name} must be numeric") from exc
    if not math.isfinite(v):
        raise RecipeError(f"{field_name} must be finite")
    return v


def normalize(spec, records, mapping):
    """Map role -> source column name; never guess the meaning of a column."""
    fields = spec["fields"]
    mapping = mapping or {}
    known = {f["role"] for f in fields}
    if set(mapping) - known:
        raise RecipeError(f"Unknown mapped roles: {sorted(set(mapping) - known)}")
    if not isinstance(records, (list, tuple)) or not records:
        raise RecipeError("Expected non-empty input records")
    rows = []
    for i, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise RecipeError(f"Row {i} must be a mapping of column names to values")
        row = {}
        for f in fields:
            key = f["role"]
            source = mapping.get(key, key)
            value = record.get(source)
            if value is None or str(value).strip() == "":
                if "default" in f:
                    value = f["default"]
                else:
                    raise RecipeError(f"Row {i}: missing {key!r} (source {source!r})")
            if f["type"] in ("number", "integer"):
                value = finite(value, f"Row {i}, {source}")
                if f["type"] == "integer" and not value.is_integer():
                    raise RecipeError(f"Row {i}: {key} must be an integer")
                if "minimum" in f and value < f["minimum"]:
                    raise RecipeError(f"Row {i}: {key} is below {f['minimum']}")
            else:
                value = str(value).strip()
            row[key] = value
        rows.append(row)
    return rows


def partition(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    return groups


def distinct(values):
    return list(dict.fromkeys(values))


def unique_rows(rows, *keys):
    indices = set()
    for row in rows:
        k = tuple(row[i] for i in keys)
        if k in indices:
            raise RecipeError(f"Duplicate {', '.join(keys)}: {k!r}")
        indices.add(k)


@dataclass
class Table:
    name: str
    columns: list = field(default_factory=list)

    def column(self, label, values, axis="Y"):
        self.columns.append((str(label), list(values), axis))
        return len(self.columns) - 1


@dataclass
class Layer:
    x_title: str = ""
    y_title: str = ""
    marks: list = field(default_factory=list)
    x_labels: tuple | None = None
    y_labels: tuple | None = None
    xlim: tuple | None = None
    ylim: tuple | None = None
    legend: bool = True
    min_plots: int = 1

    def mark(self, table, x, y, kind, *, error=None, label=None, color_index=None):
        self.marks.append(dict(table=table, x=x, y=y, kind=kind, error=error,
                               label=label, color_index=color_index))


@dataclass
class Plan:
    recipe_id: str
    title: str
    template: str
    rows: list
    layers: list
    tables: list = field(default_factory=list)
    native: dict = field(default_factory=dict)
    science: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def table(self, label):
        self.tables.append(Table(label))
        return len(self.tables) - 1, self.tables[-1]

    @property
    def expected(self):
        return {"layer_count": len(self.layers), "min_plots": [l.min_plots for l in self.layers],
                "source_row_count": len(self.rows), "science": self.science}
