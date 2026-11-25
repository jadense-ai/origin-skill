"""Style and export the showcase inside Origin's embedded Python."""

from collections import Counter, defaultdict
import csv
import json
from math import ceil, fsum
import os
from pathlib import Path
import sys
import traceback

from showcase_advanced import ADVANCED, FEATURE_GROUPS, VALUE_RGB, XPS_PEAKS, interpolate_color


COLORS = ("#146984", "#B04E35", "#268065", "#75549B")
INK = "#243744"


def _execute(layer, script):
    if not layer.obj.LT_execute(script):
        raise RuntimeError(f"Origin could not execute {script}")


def _axes(layer, font, x_title, y_title):
    layer.activate()
    for axis, title in (("x", x_title), ("y", y_title)):
        layer.set_float(axis + ".label.pt", 13)
        layer.set_int(axis + ".label.font", font)
        layer.set_float(axis + ".thickness", 1.05)
        layer.set_int(axis + ".minorTicks", 0)
        layer.axis(axis).title = title
    for name in ("XB", "YL"):
        label = layer.label(name)
        if label is not None:
            label.set_float("fsize", 15)
            label.set_int("font", font)
    legend = layer.label("Legend")
    if legend is not None:
        legend.remove()


def _position(layer, left, top, width, height):
    layer.activate()
    _execute(layer, f"layer.unit=1; layer {width} {height} {left} {top};")
    actual = tuple(layer.get_float(prop) for prop in ("left", "top", "width", "height"))
    if any(abs(a - b) > 0.1 for a, b in zip(actual, (left, top, width, height))):
        raise RuntimeError(f"Origin layer position could not be set: {actual}")


def _label(layer, name, text, x, y, size, color, *, attach=2):
    _execute(layer, f"label -j 1 -n {name} Text; {name}.attach={attach};")
    label = layer.label(name)
    label.text = text
    label.set_float("fsize", size)
    label.set_int("color", color)
    if attach == 2:
        label.set_float("x", x)
        label.set_float("y", y)
    else:
        label.set_float("left", x)
        label.set_float("top", y)
    return label


def _plot(layer, sheet, x, y, kind, color=None, width=1.4):
    plot = layer.add_plot(sheet, colx=x, coly=y, type=kind)
    if plot is None:
        raise RuntimeError(f"Origin could not plot {sheet.name} column {y + 1}")
    if color is not None:
        plot.color = color
    if kind == "l":
        layer.set_float(f"plot{len(layer.plot_list())}.line.width", width)
    return plot


def _hide_axes(layer):
    for axis in ("x", "y"):
        layer.set_int(axis + ".showAxes", 0)
        layer.set_int(axis + ".showLabels", 0)


def _feature_key(graph, book, bees, font, ink, fill):
    layer = graph.add_layer()
    sheet = book.add_sheet("FeatureScale")
    levels = 32
    columns = []
    for i in range(levels):
        bottom, top = i / levels, (i + 1) / levels
        columns += [("Key position", [0.2, 0.2], "X"), ("Scaled feature value", [bottom, top], "Y")]
    fill(sheet, columns)
    _axes(layer, font, "", "")
    for i in range(levels):
        color = "#%02x%02x%02x" % interpolate_color(VALUE_RGB, (i + 0.5) / levels)
        _plot(layer, sheet, 2 * i, 2 * i + 1, "l", color, 23)
    _position(layer, 90, 22, 8, 45)
    layer.set_xlim(0, 1)
    layer.set_ylim(0, 1)
    _hide_axes(layer)
    bees.activate()
    page_w, page_h = graph.get_float("width"), graph.get_float("height")
    for label, level in (("Low", 0), ("Mid", 0.5), ("High", 1)):
        _label(bees, label, f"{level:.1f}", 0.932 * page_w, (0.66 - 0.45 * level) * page_h, 12, ink, attach=0)
    _label(bees, "ScaleTitle", "Feature\nvalue", 0.900 * page_w, 0.168 * page_h, 12, ink, attach=0)


def _read_columns(path, convert):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [tuple(fn(value) for fn, value in zip(convert, row, strict=True))
                for row in list(csv.reader(handle))[1:]]


def _shap(op, job, ocolor, fill_color):
    from recipes.native import _fill

    samples = _read_columns(job["source"], (int, str, str, float, float))
    book = op.new_book("w", lname="SHAP attribution · Data")
    source = book[0]
    source.name = "Source"
    _fill(source, [(name, list(values), "N") for name, values in zip(
        ("Sample", "Feature", "Feature group", "Scaled feature value", "SHAP value"), zip(*samples))])

    features = defaultdict(list)
    feature_groups = {}
    for _, feature, group, value, effect in samples:
        features[feature].append((effect, value))
        feature_groups[feature] = group
    magnitudes = {feature: fsum(abs(effect) for effect, _ in pairs) / len(pairs)
                  for feature, pairs in features.items()}
    names = sorted(features, key=magnitudes.get)
    count = len(names)
    group_names = list(FEATURE_GROUPS)
    importance = book.add_sheet("Importance")
    _fill(importance, [("Rank", list(range(1, count + 1)), "X"), ("Feature", names, "N"),
                       *[(group, [magnitudes[name] if feature_groups[name] == group else "" for name in names], "Y")
                         for group in group_names]])

    points = []
    for rank, feature in enumerate(names, 1):
        buckets = defaultdict(list)
        for effect, value in sorted(features[feature]):
            buckets[round(effect / 0.08)].append((effect, value))
        for pairs in buckets.values():
            spacing = min(0.12, 0.72 / len(pairs))
            for i, (effect, value) in enumerate(pairs):
                points.append((effect, rank + (i - (len(pairs) - 1) / 2) * spacing, value))
    swarm = book.add_sheet("Swarm")
    _fill(swarm, [(name, list(values), role) for name, values, role in zip(
        ("SHAP value", "Feature rank", "Scaled feature value"), zip(*points), ("X", "Y", "N"))])

    total = fsum(magnitudes.values())
    shares = [100 * fsum(magnitudes[name] for name in names if feature_groups[name] == group) / total
              for group in group_names]
    contribution = book.add_sheet("GroupShares")
    _fill(contribution, [("Group", group_names, "N"), ("Share (%)", shares, "Y")])
    share_marks = book.add_sheet("ShareSegments")
    start = 0
    segments = []
    for group, share in zip(group_names, shares):
        stop = start + share
        segments += [("Share position (%)", [start + 0.24, stop - 0.24], "X"), (group, [0.55, 0.55], "Y")]
        start = stop
    _fill(share_marks, segments)

    graph = op.new_graph(lname=job["title"], template="Bar")
    graph.set_float("height", round(graph.get_float("width") * 0.64))
    bars = graph[0]
    bees = graph.add_layer()
    key = graph.add_layer()
    font = op.lt_int("font(Arial)")
    for i, group in enumerate(group_names, 2):
        plot = _plot(bars, importance, 0, i, 215)
        fill_color(op, bars, plot, FEATURE_GROUPS[group])
    bars.rescale()
    _axes(bars, font, "", "Mean |SHAP value|")
    _position(bars, 17, 12, 26, 61)
    bars.set_xlim(0.5, count + 0.5, 1)
    bars.set_ylim(0, 1.25, 0.25)
    _execute(bars, f"range demoFeatureLabels={importance.lt_range(False)}!col(2); axis -ps X T demoFeatureLabels;")
    _execute(bars, 'layer.x.ticksbydata$="' + " ".join(map(str, range(1, count + 1))) + '";')
    bars.set_int("x.ticks", 0)
    bars.set_int("y.showGrids", 1)

    bees.activate()
    zero = book.add_sheet("ZeroLine")
    _fill(zero, [("SHAP zero", [0, 0], "X"), ("Feature rank", [0.5, count + 0.5], "Y")])
    _plot(bees, zero, 0, 1, "l", "#A1ADB2", 1)
    cloud = _plot(bees, swarm, 0, 1, "s")
    cloud.symbol_kind = 2
    cloud.symbol_interior = 1
    cloud.symbol_size = 3.7
    cloud.color = op.color_col(1, "m")
    cloud.set_cmd(f"-csfm {swarm.obj[2].GetDatasetName()}")
    cloud.colormap = job["palette"]
    cloud.zlevels = {"minors": 15, "levels": [0, 0.25, 0.5, 0.75, 1]}
    _axes(bees, font, "SHAP value (model output)", "")
    _position(bees, 48, 12, 39, 61)
    extent = ceil(max(abs(effect) for effect, _, _ in points))
    bees.set_xlim(-extent, extent, 1)
    bees.set_ylim(0.5, count + 0.5, 1)
    bees.set_int("y.showLabels", 0)
    bees.set_int("y.ticks", 0)

    _axes(key, font, "", "")
    for i, group in enumerate(group_names):
        _plot(key, share_marks, 2 * i, 2 * i + 1, "l", FEATURE_GROUPS[group], 11)
    _position(key, 17, 86, 70, 8)
    key.set_xlim(0, 100)
    key.set_ylim(0, 1)
    _hide_axes(key)
    ink = ocolor(INK)
    start = 0
    for i, (group, share) in enumerate(zip(group_names, shares), 1):
        label = _label(key, f"Group{i}", f"{group} {share:.1f}%", start + share / 2, 0.03, 10.5, ink)
        label.set_int("justify", 1)
        start += share
    _label(key, "OriginPlotPanel", r"\b(c)  Share of total mean |SHAP|", graph.get_float("width") * 0.17,
           graph.get_float("height") * 0.814, 13, ink, attach=0)

    for layer, title, x in ((bars, r"\b(a)  Global importance", 0.17),
                            (bees, r"\b(b)  Effects across 140 simulated samples", 0.48)):
        layer.activate()
        _label(layer, "OriginPlotPanel", title, graph.get_float("width") * x,
               graph.get_float("height") * 0.062, 13, ink, attach=0)
    _feature_key(graph, book, bees, font, ink, _fill)
    return graph


def _xps(op, job, ocolor):
    from recipes.native import _fill

    rows = _read_columns(job["source"], (float, int, float, float, float, float, float, float, float))
    book = op.new_book("w", lname="XPS C 1s · Data")
    source = book[0]
    source.name = "Source"
    names = ("Binding energy (eV)", "Raw counts", "Background", *(name for name, *_ in XPS_PEAKS), "Model envelope", "Residual")
    _fill(source, [(name, list(values), "X" if i == 0 else "Y")
                   for i, (name, values) in enumerate(zip(names, zip(*rows)))])
    components = book.add_sheet("OnBackground")
    _fill(components, [(names[0], [row[0] for row in rows], "X"),
                       *[(peak[0], [row[2] + row[i + 3] for row in rows], "Y") for i, peak in enumerate(XPS_PEAKS)]])
    zero = book.add_sheet("ZeroLine")
    _fill(zero, [("Binding energy (eV)", [282, 292], "X"), ("Zero", [0, 0], "Y")])

    graph = op.new_graph(lname=job["title"], template="Line")
    graph.set_float("height", round(graph.get_float("width") * 0.65))
    spectrum, residual = graph[0], graph.add_layer()
    font = op.lt_int("font(Arial)")
    spectrum.activate()
    for i, (_, _, _, _, _, color, fill) in enumerate(XPS_PEAKS, 1):
        peak = _plot(spectrum, components, 0, i, "l", color, 1.8)
        _plot(spectrum, source, 0, 2, "l", "#687982", 0.7)
        peak.set_fill_area(ocolor(fill), 9, ocolor(fill))
    _plot(spectrum, source, 0, 7, "l", "#3C464F", 2.5)
    raw = _plot(spectrum, source, 0, 1, "s", "#235B87")
    raw.symbol_kind = 2
    raw.symbol_interior = 1
    raw.symbol_size = 3.2
    _axes(spectrum, font, "", "Intensity (counts)")
    _position(spectrum, 13, 12, 82, 51)
    spectrum.set_ylim(900, 6200, 1000)
    spectrum.set_int("x.showLabels", 0)
    script = r"\l(10) Raw counts    \l(9) Model envelope    \l(8) Background" + "\n" + \
        r"\l(1) C–C / C–H    \l(3) C–O    \l(5) C=O    \l(7) O–C=O"
    ink = ocolor(INK)
    legend = _label(spectrum, "Legend", script, 0.17 * graph.get_float("width"),
                    0.16 * graph.get_float("height"), 12, ink, attach=0)
    legend.set_int("background", 0)

    residual.activate()
    _plot(residual, zero, 0, 1, "l", "#87949C", 1)
    _plot(residual, source, 0, 8, "l", "#235B87", 1)
    _axes(residual, font, "Binding energy (eV)", "Residual (counts)")
    _position(residual, 13, 69, 82, 17)
    residual.set_ylim(-100, 100, 50)
    residual.set_int("y.showGrids", 1)
    for axis in ("x", "y"):
        residual.set_float(axis + ".label.pt", 17)
    for name in ("XB", "YL"):
        residual.label(name).set_float("fsize", 20)
    for layer, top, size, title in ((spectrum, 0.052, 14, r"\b(a)  Simulated C 1s spectrum"),
                                    (residual, 0.656, 20, r"\b(b)  Observed − model")):
        layer.activate()
        layer.set_xlim(292, 282, 2)
        _execute(layer, 'layer.x.ticksbydata$="282 284 286 288 290 292";')
        _label(layer, "OriginPlotPanel", title, 0.13 * graph.get_float("width"),
               top * graph.get_float("height"), size, ink, attach=0)
    return graph


def style(op, job, ocolor, fill_color):
    graph = op.find_graph(job["graph"])
    if not graph:
        raise ValueError("Showcase graph is missing from its originating project")
    graph.activate()
    recipe = job["recipe"]
    x_title, y_title, *right = job["axes"]
    font = op.lt_int("font(Arial)")
    box_groups = {}
    if recipe == "box-raw":
        with Path(job["source"]).open(encoding="utf-8", newline="") as source:
            box_groups = Counter(row["group"] for row in csv.DictReader(source))
    for i, layer in enumerate(graph):
        layer.activate()
        for axis in ("x", "y"):
            layer.set_float(axis + ".label.pt", 14)
            layer.set_int(axis + ".label.font", font)
            layer.set_float(axis + ".thickness", 1.1)
        if recipe == "multi-panel":
            y_text = ("Response" if i == 0 else "Drive") + " (a.u.)"
        else:
            y_text = right[0] if i == 1 and right else y_title
        y_name = "YR" if recipe == "dual-y" and i == 1 else "YL"
        for name, value in (("XB", x_title), (y_name, y_text)):
            label = layer.label(name)
            if label is not None:
                label.text = value
                label.set_float("fsize", 16)
        legend = layer.label("Legend")
        if legend is not None:
            legend.set_float("fsize", 12.5)
            legend.set_int("background", 0)
            if recipe == "multi-panel" and i == 0:
                legend.remove()
            if recipe == "ecdf":
                legend.set_int("attach", 2)
                legend.set_float("x", 64)
                legend.set_float("y", 0.3)
        plots = layer.plot_list()
        for j, plot in enumerate(plots, 1):
            kind = layer.get_int(f"plot{j}.pid")
            if kind in (200, 202):
                layer.set_float(f"plot{j}.line.width", 2.2)
            if kind in (201, 202):
                plot.symbol_size = 3 if recipe in ("box-raw", "dose-response", "eis-nyquist") else 6
            if kind == 201 and recipe == "box-raw":
                plot.color = (COLORS[0], COLORS[1])[(j - len(box_groups) - 1) % 2]
                plot.symbol_kind = 2
                plot.transparency = 10
            if recipe in ("coefficient-interval", "event-study"):
                reference = j == len(plots)
                plot.color = "#8996A0" if reference else COLORS[0]
                if reference:
                    layer.set_float(f"plot{j}.line.width", 1.1)
            elif recipe == "multi-line":
                plot.color = ("#167C85", "#6F57A1", "#BC6547", "#69935B", "#65717A", "#A03B3D", "#172F48")[j - 1]
                if j <= 4:
                    plot.set_fill_area(ocolor(("#D0E9E8", "#E1D9EF", "#F4DFD3", "#DDEACF")[j - 1]), 0)
                if j == 5:
                    layer.set_int(f"plot{j}.line.type", 2)
                if j == 7:
                    layer.set_float(f"plot{j}.line.width", 1.05)
            elif kind in (200, 201, 202) and recipe != "box-raw":
                color_index = j - 1
                if recipe == "dose-response":
                    color_index //= 2
                if recipe == "dual-y":
                    color_index = i
                plot.color = COLORS[color_index % len(COLORS)]
            if kind == 219:
                fill_color(op, layer, plot, COLORS[0])
        if recipe == "heatmap":
            plots[0].colormap = job["palette"]
            plots[0].zlevels = {"minors": 6, "levels": [-2.5, -2, -1, 0, 1, 2, 2.5]}
            for axis in ("x", "y"):
                layer.set_float(axis + ".label.pt", 9.5)
        if recipe == "box-raw":
            layer.set_ylim(0.65, 1.85, 0.25)
            first = len(box_groups) + 1
            legend = _label(layer, "Legend", fr"\l({first}) Cohort A    \l({first + 1}) Cohort B", 2.25, 1.79,
                            13, ocolor(INK))
            legend.set_int("background", 0)
            for index, count in enumerate(box_groups.values(), 1):
                _label(layer, f"SampleCount{index}", f"n={count}", index - 0.10, 0.72, 10, ocolor("#536571"))
    graph.activate()


def run(job_path):
    path = Path(job_path)
    job = json.loads(path.read_text(encoding="utf-8"))
    try:
        if os.getpid() != job["pid"]:
            raise RuntimeError("Origin process changed during showcase rendering")
        import originpro as op
        from originpro.utils import ocolor
        from runpy import run_path

        if op.oext:
            raise RuntimeError("Showcase styling requires Origin's embedded Python")
        sys.path.insert(0, job["scripts"])
        try:
            backend = run_path(job["embedded"])
            recipe = job["recipe"]
            if recipe in ADVANCED:
                graph = (_shap(op, job, ocolor, backend["_fill_color"]) if recipe == "shap-summary"
                         else _xps(op, job, ocolor))
                graph.activate()
                report = {"ok": True, "graph": graph.name}
            else:
                style(op, job, ocolor, backend["_fill_color"])
                report = {"ok": True}
        finally:
            sys.path.remove(job["scripts"])
    except Exception:
        report = {"ok": False, "error": traceback.format_exc(limit=5)}
    reply = path.with_name("style-reply.json")
    temporary = reply.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    temporary.replace(reply)
