"""Normalize original records into explicit worksheet columns and Origin marks."""

import math
from collections import Counter
from itertools import islice
from statistics import mean, median

from .model import Layer, Plan, RecipeError, distinct, finite, normalize, partition, specification, unique_rows


def _xy(plan, layer, label, xs, ys, kind, *, error=None, color=None):
    number, table = plan.table(label)
    xcol = table.column(layer.x_title, xs, "X")
    ycol = table.column(label, ys)
    errcol = table.column("Error half-width", error, "E") if error is not None else None
    layer.mark(number, xcol, ycol, kind, error=errcol, label=label, color_index=color)


def _labels(plan, layer, labels, axis):
    number, table = plan.table("Category labels")
    index = table.column("Category", labels, "L")
    setattr(layer, axis + "_labels", (number, index, list(labels)))
    setattr(layer, axis + "lim", (0.5, len(labels) + 0.5, 1))


def _curves(plan, rows, group_key, xkey, ykey, *, kind="line", sort=True, reverse=False, layer=None):
    layer = layer or plan.layers[0]
    if kind != "scatter":
        unique_rows(rows, group_key, xkey)
    groups = partition(rows, group_key)
    for color, (name, points) in enumerate(groups.items()):
        if sort:
            points = sorted(points, key=lambda r: r[xkey], reverse=reverse)
        if len(points) < 2 and kind != "scatter":
            raise RecipeError(f"{name!r} needs at least two coordinates")
        _xy(plan, layer, name, [p[xkey] for p in points], [p[ykey] for p in points], kind, color=color)
    layer.min_plots = len(groups)
    layer.legend = len(groups) > 1


def _regular(plan, options):
    id = plan.recipe_id
    layer = plan.layers[0]
    if id == "point-error":
        unique_rows(plan.rows, "series", "x")
        for i, (name, rows) in enumerate(partition(plan.rows, "series").items()):
            rows = sorted(rows, key=lambda r: r["x"])
            _xy(plan, layer, name, [r["x"] for r in rows], [r["estimate"] for r in rows],
                "scatter", error=[r["error"] for r in rows], color=i)
        layer.min_plots = len(layer.marks)
    elif id == "multi-panel":
        panels = partition(plan.rows, "panel")
        if len(panels) != 2:
            raise RecipeError("multi-panel expects exactly two distinct panels")
        plan.template = "PAN2VERT"
        plan.layers.append(Layer(layer.x_title, layer.y_title))
        plan.science["panels"] = list(panels)
        for current, (panel, points) in zip(plan.layers, panels.items()):
            current.y_title = f"{panel} · {current.y_title}"
            _curves(plan, points, "series", "x", "y", layer=current)
    elif id == "dual-y":
        unique_rows(plan.rows, "x")
        rows = sorted(plan.rows, key=lambda r: r["x"])
        if len(rows) < 2:
            raise RecipeError("dual-y needs two or more x values")
        plan.template = "DoubleY"
        right = Layer(layer.x_title, specification(id)["axes"][2], legend=False)
        plan.layers.append(right)
        for i, (current, key) in enumerate(zip(plan.layers, ("left", "right"))):
            _xy(plan, current, key, [r["x"] for r in rows], [r[key] for r in rows], "line-symbol", color=i)
            current.legend = False
    else:
        kind = "scatter" if id == "scatter" else "line"
        _curves(plan, plan.rows, "series", "x", "y", kind=kind, sort=kind != "scatter")


def _crossed(plan, options):
    rows, layer = plan.rows, plan.layers[0]
    if plan.recipe_id == "likert":
        unique_rows(rows, "item", "rating")
        cats = distinct(r["item"] for r in rows)
        groups = ["Neutral (−½)", "Disagree", "Strongly disagree", "Neutral (+½)", "Agree", "Strongly agree"]
        values = [[] for _ in groups]
        totals = {}
        for item, rs in partition(rows, "item").items():
            votes = {int(r["rating"]): r["count"] for r in rs}
            if set(votes) != set(range(1, 6)) or sum(votes.values()) <= 0:
                raise RecipeError(f"{item}: include all five rating counts and at least one response")
            totals[item] = sum(votes.values())
            percentages = {i: 100 * n / totals[item] for i, n in votes.items()}
            half = percentages[3] / 2
            for data, val in zip(values, [-half, -percentages[2], -percentages[1], half, percentages[4], percentages[5]]):
                data.append(val)
        plan.science.update(totals=totals, neutral_split="half", signed_percentages=dict(zip(groups, values)))
        plan.template = "Bar"
        plan.native["bar_mode"] = "diverging"
    else:
        unique_rows(rows, "category", "series")
        cats = distinct(r["category"] for r in rows)
        groups = distinct(r["series"] for r in rows)
        indexed = {(r["category"], r["series"]): r["value"] for r in rows}
        if len(indexed) != len(groups) * len(cats):
            raise RecipeError("Missing category/series combination; supply zero explicitly if intended")
        values = [[indexed[c, g] for c in cats] for g in groups]
        if plan.recipe_id == "percent-stack":
            totals = {c: sum(indexed[c, g] for g in groups) for c in cats}
            if min(totals.values()) <= 0:
                raise RecipeError("Cannot normalize a category with zero total")
            values = [[100 * indexed[c, g] / totals[c] for c in cats] for g in groups]
            plan.science.update(totals=totals, percentages=dict(zip(groups, values)))
            plan.template = "StackColumn"
            plan.native["bar_mode"] = "stacked"
            layer.ylim = (0, 100, 20)
        else:
            plan.template = "Column"
            plan.native["bar_mode"] = "grouped"
    number, table = plan.table("Category series")
    category_column = table.column("Category index", range(1, len(cats) + 1), "X")
    for name, vals in zip(groups, values):
        y = table.column(name, vals)
        layer.mark(number, category_column, y, "template", label=name)
    _labels(plan, layer, cats, "x")
    layer.min_plots = len(groups)


def _quantile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    low = math.floor(position)
    return sorted_values[low] + (sorted_values[math.ceil(position)] - sorted_values[low]) * (position - low)


def _histogram(plan, options):
    values = sorted(r["value"] for r in plan.rows)
    low, high = values[0], values[-1]
    if high == low:
        pad = max(0.5, 0.005 * abs(low))
        low, high = low - pad, high + pad
    if "bins" in options and "bin_width" in options:
        raise RecipeError("Supply either bins or bin_width")
    span = high - low
    if "bin_width" in options:
        width = finite(options["bin_width"], "bin_width")
        if width <= 0:
            raise RecipeError("bin_width must be positive")
        count = max(1, math.floor(span / width) + 1)
    else:
        if "bins" in options:
            bins = finite(options["bins"], "bins")
            if bins != int(bins) or bins < 1:
                raise RecipeError("bins must be a positive integer")
            count = int(bins)
        else:
            iqr = _quantile(values, .75) - _quantile(values, .25)
            fd = 2.0 * iqr / len(values) ** (1.0 / 3)
            count = max(1, math.ceil(span / fd)) if fd > 0 else math.ceil(math.log2(len(values)) + 1)
        # Origin bins are [lower, upper). Pad the outside edges so the maximum
        # remains an observation in the last bin, including for integer inputs.
        padding = max(span * 1e-8, max(abs(low), abs(high), 1.0) * 1e-12)
        low, high = low - padding, high + padding
        width = (high - low) / count
    if count > 10000:
        raise RecipeError("Choose a bin width/count producing at most 10000 bins")
    counts = [0] * count
    for val in values:
        b = min(count - 1, max(0, math.floor((val - low) / width)))
        counts[b] += 1
    number, table = plan.table("Histogram values")
    table.column("Observed value", [r["value"] for r in plan.rows])
    plan.native.update(special="histogram", table=number)
    plan.science.update(bin_begin=low, bin_end=low + count * width, bin_size=width, bin_counts=counts,
                        boundary="left-closed, right-open; upper limit above maximum")
    plan.layers[0].legend = False


def _distribution(plan, options):
    layer = plan.layers[0]
    groups = partition(plan.rows, "group")
    plan.science["group_sizes"] = {k: len(v) for k, v in groups.items()}
    if plan.recipe_id == "ecdf":
        for i, (key, rows) in enumerate(groups.items()):
            freq = Counter(r["value"] for r in rows)
            xs, ys, prior = [], [], 0
            for val in sorted(freq):
                fraction = prior + freq[val] / len(rows)
                xs.extend((val, val))
                ys.extend((prior, fraction))
                prior = fraction
            ys[-1] = 1.0
            _xy(plan, layer, key, xs, ys, "line", color=i)
        layer.ylim = (0, 1, .2)
    else:
        number, table = plan.table("Group observations")
        plan.native.update(special=plan.recipe_id, table=number, groups=list(groups))
        plan.science["median"] = {}
        for i, (key, rows) in enumerate(groups.items()):
            obs = [r["value"] for r in rows]
            if len(obs) < 2 or (plan.recipe_id == "violin" and len(set(obs)) < 2):
                raise RecipeError(f"{key}: distribution needs at least two observations; violin needs variation")
            table.column(key, obs)
            plan.science["median"][key] = median(obs)
            if plan.recipe_id == "box-raw":
                # Symmetric deterministic horizontal offsets; no change to observed Y.
                jitter_x = [i + 1 + .19 * (j / (len(obs) - 1) - .5) for j in range(len(obs))]
                _xy(plan, layer, key, jitter_x, obs, "scatter", color=i)
        _labels(plan, layer, list(groups), "x")
        layer.legend = False
    layer.min_plots = len(groups) if plan.recipe_id == "ecdf" else 1 + len(layer.marks)


def _heatmap(plan, options):
    unique_rows(plan.rows, "row", "column")
    rs = distinct(r["row"] for r in plan.rows)
    cs = distinct(r["column"] for r in plan.rows)
    if min(len(rs), len(cs)) < 2:
        raise RecipeError("A heatmap needs at least two rows and two columns")
    indexed = {(r["row"], r["column"]): r["value"] for r in plan.rows}
    missing_count = len(rs) * len(cs) - len(indexed)
    if missing_count:
        sample = islice(((r, c) for r in rs for c in cs if (r, c) not in indexed), 5)
        locations = ", ".join(f"row {r!r}, column {c!r}" for r, c in sample)
        raise RecipeError(f"Incomplete heatmap grid ({missing_count} missing): {locations}")
    matrix = [[indexed[r, c] for c in cs] for r in rs]
    plan.native.update(special="heatmap", matrix=matrix)
    plan.science.update(rows=rs, columns=cs, matrix=matrix)
    plan.template = "Heat_Map"
    _labels(plan, plan.layers[0], cs, "x")
    _labels(plan, plan.layers[0], rs, "y")
    plan.layers[0].legend = False


def _interval(plan, options):
    horizontal = plan.recipe_id == "coefficient-interval"
    layer = plan.layers[0]
    key = "term" if horizontal else "period"
    unique_rows(plan.rows, key)
    rows = plan.rows if horizontal else sorted(plan.rows, key=lambda r: r[key])
    for r in rows:
        if not r["lower"] <= r["estimate"] <= r["upper"]:
            raise RecipeError(f"Interval must enclose estimate for {r[key]!r}")
    pos = list(range(1, len(rows) + 1)) if horizontal else [r[key] for r in rows]
    for p, r in zip(pos, rows):
        bounds = [r["lower"], r["upper"]]
        xs, ys = (bounds, [p, p]) if horizontal else ([p, p], bounds)
        _xy(plan, layer, str(r[key]) + " interval", xs, ys, "line", color=0)
    est = [r["estimate"] for r in rows]
    _xy(plan, layer, "Estimate", est if horizontal else pos, pos if horizontal else est, "scatter", color=0)
    guide = [min(pos) - .4, max(pos) + .4]
    _xy(plan, layer, "Zero", [0, 0] if horizontal else guide, guide if horizontal else [0, 0], "reference", color=1)
    if horizontal:
        _labels(plan, layer, [r[key] for r in rows], "y")
    layer.min_plots, layer.legend = len(layer.marks), False
    plan.science.update(intervals=[[r[key], r["lower"], r["estimate"], r["upper"]] for r in rows])


def _subject(plan, options):
    id, rows, layer = plan.recipe_id, plan.rows, plan.layers[0]
    if id == "corpus-frequency":
        unique_rows(rows, "term", "period")
        processed = []
        for r in rows:
            if r["tokens"] <= 0 or r["count"] > r["tokens"]:
                raise RecipeError("Require 0 <= hits <= tokens and tokens > 0")
            processed.append({**r, "per_million": r["count"] / r["tokens"] * 1e6})
        _curves(plan, processed, "term", "period", "per_million", kind="line-symbol")
        plan.science["per_million"] = [r["per_million"] for r in processed]
    elif id == "dose-response":
        for i, (key, sub) in enumerate(partition(rows, "series").items()):
            by_dose = partition(sub, "dose")
            if len(by_dose) < 2:
                raise RecipeError("Dose series requires at least two distinct doses")
            doses = sorted(by_dose)
            means = [mean(r["response"] for r in by_dose[d]) for d in doses]
            _xy(plan, layer, key + " observations", [r["dose"] for r in sub], [r["response"] for r in sub], "scatter", color=i)
            _xy(plan, layer, key + " mean", doses, means, "line", color=i)
            plan.science.setdefault("means", {})[key] = [[d, m] for d, m in zip(doses, means)]
        layer.min_plots = len(layer.marks)
    elif id == "paired-sample":
        unique_rows(rows, "subject")
        for i, r in enumerate(rows):
            _xy(plan, layer, r["subject"], [1, 2], [r["before"], r["after"]], "line-symbol", color=i)
        _labels(plan, layer, ["Before", "After"], "x")
        layer.legend, layer.min_plots = False, len(rows)
        plan.science["paired_differences"] = {r["subject"]: r["after"] - r["before"] for r in rows}
    elif id == "xrd-stack":
        unique_rows(rows, "sample", "two_theta")
        groups = partition(rows, "sample")
        extent = max(r["intensity"] for r in rows) - min(r["intensity"] for r in rows)
        step = finite(options.get("offset", extent * 1.1 if extent else 1), "offset")
        if step < 0:
            raise RecipeError("offset must be nonnegative")
        plan.science["offsets"] = {}
        for i, (sample, sub) in enumerate(groups.items()):
            ordered = sorted(sub, key=lambda r: r["two_theta"])
            if len(ordered) < 2:
                raise RecipeError("Each XRD spectrum needs at least two points")
            _xy(plan, layer, sample, [r["two_theta"] for r in ordered],
                [r["intensity"] + i * step for r in ordered], "line", color=i)
            plan.science["offsets"][sample] = i * step
        layer.min_plots = len(groups)
    else:
        unique_rows(rows, "sample", "frequency")
        if min(r["frequency"] for r in rows) <= 0:
            raise RecipeError("Impedance frequencies must be positive")
        for i, (sample, sub) in enumerate(partition(rows, "sample").items()):
            ordered = sorted(sub, key=lambda r: -r["frequency"])
            if len(ordered) < 2:
                raise RecipeError("A Nyquist curve needs at least two frequencies")
            _xy(plan, layer, sample, [r["z_real"] for r in ordered],
                [-r["z_imag"] for r in ordered], "line-symbol", color=i)
            plan.science.setdefault("ordered_frequencies", {})[sample] = [r["frequency"] for r in ordered]
        layer.min_plots = len(layer.marks)


def prepare(recipe_id, records, *, title=None, columns=None, options=None):
    spec = specification(recipe_id)
    rows = normalize(spec, records, columns)
    options = options or {}
    allowed = {"histogram": {"bins", "bin_width"}, "xrd-stack": {"offset"}}.get(recipe_id, set())
    unknown = set(options) - allowed
    if unknown:
        raise RecipeError(f"Unknown scientific options for {recipe_id}: {sorted(unknown)}")
    layer = Layer(*spec["axes"][:2])
    plan = Plan(recipe_id, str(title or spec["name"]), "Origin", rows, [layer])
    if recipe_id in {"multi-line", "scatter", "point-error", "dual-y", "multi-panel"}:
        _regular(plan, options)
    elif recipe_id in {"grouped-column", "percent-stack", "likert"}:
        _crossed(plan, options)
    elif recipe_id in {"box-raw", "violin", "ecdf"}:
        _distribution(plan, options)
    elif recipe_id == "histogram":
        _histogram(plan, options)
    elif recipe_id == "heatmap":
        _heatmap(plan, options)
    elif recipe_id in {"coefficient-interval", "event-study"}:
        _interval(plan, options)
    else:
        _subject(plan, options)
    return plan
