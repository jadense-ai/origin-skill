"""Actions run inside Origin's embedded Python, on the graph's owning GUI thread."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

XY_TEMPLATE_TYPES = {"line": 200, "scatter": 201, "line+symbol": 202, "column": 203}
BAR_PLOTS = {203, 213, 215, 216, 219}
LINE_PLOTS = {200, 201, 202, 231}
DATASET_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:@\d+)?")


def _probe(fn):
    try:
        value = fn()
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    except Exception:
        return None


def _bin_info(layer, index):
    fields = {"bin_begin":"binBegin", "bin_end":"binEnd", "bin_width":"binSize"}
    data = {k:_probe(lambda v=v: layer.get_float("plot%d.boxchart.%s" % (index, v))) for k, v in fields.items()}
    lo, hi, width = (data[k] for k in fields)
    data["bin_count"] = None
    if None not in (lo, hi, width) and hi > lo and width > 0:
        count = (hi - lo) / width
        data["bin_count"] = int(round(count)) if math.isclose(count, round(count), abs_tol=1e-6) else None
    return data


def _page_size(graph, field, res):
    dots = graph.get_float(field)
    dpi = graph.get_float(res)
    return dots * 25.4 / dpi if dots > 0 and dpi > 0 else None


def _hex_color(value):
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return "#%02x%02x%02x" % tuple(value)
    return str(value).casefold()


def _fill_color(op, layer, plot, value=None):
    from originpro.utils import ocolor, to_rgb

    name = str(plot.obj.GetDatasetName())
    if not DATASET_NAME.fullmatch(name):
        raise ValueError("Origin did not expose a fill-color plot reference.")
    matches = [p.index() for p in layer.plot_list() if str(p.obj.GetDatasetName()) == name]
    if len(matches) > 1:
        name = f"{name}:{matches.index(plot.index()) + 1}"
    if value is not None and not layer.obj.LT_execute(f"set {name} -pfb {ocolor(value)};"):
        raise RuntimeError("Origin rejected the fill color.")
    if not layer.obj.LT_execute(f"opbFillColor=-1;get {name} -pfb opbFillColor;"):
        raise RuntimeError("Origin could not read back the fill color.")
    actual = op.lt_int("opbFillColor")
    if actual == -1:
        raise RuntimeError("Origin did not report a fill color.")
    return _hex_color(to_rgb(actual))


def data_fingerprint(rows):
    def normalize(value):
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        if value in (None, "", "--") or isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(normalize(row), ensure_ascii=True, separators=(",", ":"), default=str).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _bound_data(op, layer, plot, role, cache):
    """Read the actual designated source and fingerprint its worksheet column or matrix object."""
    if role == "error":
        # Origin 2024 resolves range -wy on an error plot to the parent Y column.
        source = str(plot.obj.GetDatasetName())
        key = ("error", source.casefold())
        if key not in cache:
            cache[key] = _error_column(op, source)
        return cache[key]
    command = (
        'string opbDataName$="";string opbDataSheet$="";'
        f'range -w{role} opbDataRange={plot.lt_range()};'
        'opbDataName$=nameof(opbDataRange)$;opbDataSheet$=opbDataRange.GetLayer()$;'
    )
    if not layer.obj.LT_execute(command):
        return None
    name, sheet_ref = (op.get_lt_str(k) for k in ("opbDataName", "opbDataSheet"))
    if not name:
        return None
    key = (name, sheet_ref)
    if key in cache:
        return cache[key]
    info = {"name": name, "sheet": sheet_ref or None, "content_sha256": None}
    if not sheet_ref:
        return info
    matrix = role == "z"
    sheet = _probe(lambda: op.find_sheet("m" if matrix else "w", sheet_ref))
    if sheet is None:
        return info
    for index in range(sheet.depth if matrix else sheet.cols):
        if str(_probe(lambda: sheet.obj[index].GetDatasetName())).casefold() != str(name).casefold():
            continue
        if matrix:
            values = sheet.to_np2d(index)
            info["shape"] = list(values.shape)
            rows = values.tolist()
        else:
            rows = sheet.to_list(index)
            info["rows"] = len(rows)
        info["content_sha256"] = data_fingerprint(rows)
        break
    cache[key] = info
    return info


def _worksheet_column(op, source):
    folded = source.casefold()
    for book in op.pages("w"):
        if not folded.startswith(book.name.casefold() + "_"):
            continue
        for sheet in book:
            for index in range(sheet.cols):
                if str(sheet.obj[index].GetDatasetName()).casefold() == folded:
                    return sheet, index


def _error_column(op, source):
    column = _worksheet_column(op, source)
    if column is not None:
        sheet, index = column
        values = sheet.to_list(index)
        return {"name": source, "sheet": sheet.lt_range(False) + "!", "rows": len(values),
                "content_sha256": data_fingerprint(values)}


def _axis_tick_labels(op, layer, axis):
    if layer.get_int(f"{axis}.label.type") not in {2, 8}:
        return None
    command = (f"string opbTickSource$=layer.{axis}.label.dataset$; string opbTickName$=\"\";"
               "range opbTickRange=%(opbTickSource$); opbTickName$=nameof(opbTickRange)$;")
    if not layer.obj.LT_execute(command):
        return None
    column = _worksheet_column(op, op.get_lt_str("opbTickName") or "")
    if column is not None:
        sheet, index = column
        return [str(label) for label in sheet.to_list(index)]


def inspect_graph(op, graph, *, verify_histograms=False):
    layers = []
    data_cache = {}
    for li, layer in enumerate(graph):
        plots = []
        for pi, plot in enumerate(layer.plot_list(), 1):
            source = _probe(lambda: plot.obj.GetDatasetName())
            pt = _probe(lambda: layer.get_int("plot%d.pid" % pi))
            item = {"index": pi, "data_source": source or None, "plot_type_id": pt or None,
                    "object_range": _probe(plot.lt_range), "color": _probe(lambda: plot.color),
                    "line_width": _probe(lambda: layer.get_float(f"plot{pi}.line.width")) if pt in LINE_PLOTS else None,
                    "symbol_size": _probe(lambda: plot.symbol_size) if pt in (201, 202) else None}
            if pt in LINE_PLOTS:
                item["line_style"] = _probe(lambda: layer.get_int(f"plot{pi}.line.type"))
            if pt in (201, 202):
                item["symbol_kind"] = _probe(lambda: plot.symbol_kind)
            if pt in BAR_PLOTS:
                item["fill_color"] = _probe(lambda: _fill_color(op, layer, plot))
            if pt == 105:
                item["palette"] = _probe(lambda: plot.colormap)
                item["color_levels"] = _probe(lambda: plot.zlevels)
            roles = ("z",) if pt == 105 else (("y",) if pt in (206, 219, 231) else ("x", "y"))
            item["data_roles"] = {role: _probe(lambda: _bound_data(op, layer, plot, "error" if pt == 231 else role, data_cache))
                                  for role in roles}
            if pt == 219:
                item["histogram"] = _bin_info(layer, pi)
                if verify_histograms:
                    from recipes.native import histogram_counts

                    item["histogram_counts"] = histogram_counts(op, item["data_roles"]["y"]["name"], layer, pi)
            plots.append(item)
        axes = {}
        for key in ("x", "y"):
            ax = layer.axis(key)
            axes[key] = {"title": _probe(lambda: ax.title), "from": _probe(lambda: ax.sfrom),
                         "to": _probe(lambda: ax.sto), "scale": _probe(lambda: ax.scale),
                         "major_ticks": _probe(lambda: layer.get_int(f"{key}.majorTicks")),
                         "title_size": _probe(lambda: _axis_label(layer, key).get_float("fsize"))}
            if any(plot["plot_type_id"] == 105 for plot in plots):
                axes[key]["tick_labels"] = _probe(lambda: _axis_tick_labels(op, layer, key))
        legend = _probe(lambda: layer.label("legend"))
        panel = _probe(lambda: layer.label("OriginPlotPanel"))
        layers.append({"index": li + 1, "axes": axes, "plots": plots,
                       "panel": {"text": _probe(lambda: panel.text),
                                 "fsize": _probe(lambda: panel.get_float("fsize"))} if panel is not None else None,
                       "legend_text": _probe(lambda: legend.text) if legend else None})
    return {"graph": graph.name, "long_name": graph.lname, "layers": layers,
            "layer_count": len(layers), "plot_counts": [len(item["plots"]) for item in layers],
            "page":{"width_mm":_probe(lambda: _page_size(graph,"width","resx")),
                    "height_mm":_probe(lambda: _page_size(graph,"height","resy"))}}


def _graph(op, name):
    g = op.find_graph(name)
    if not g or (name and g.name != name):
        raise ValueError("Origin graph not found: %r" % name)
    return g


def _template(op, job):
    from recipes.bindings import template_evidence, template_file

    if job.get("binding_job") is not None:
        path, digest = template_file(job["template_path"])
        g = op.new_graph(template=str(path))
        if not g:
            raise ValueError("Origin could not open the specified graph template.")
        source = template_evidence(op, g, path, digest, "origin-new-graph")
        proof = _bind_graph(op, g, job["binding_job"], new=True)
        if job.get("title"):
            g.lname = job["title"]
        return {"graph": g, "template_binding": {**source, **proof}}

    rows, x, y = job["records"], job["x"], job["y"]
    xs = [float(row[x]) for row in rows]
    ys = [float(row[y]) for row in rows]
    if not all(math.isfinite(v) for v in xs + ys):
        raise ValueError("Native XY template binding requires finite numeric columns.")
    path, digest = template_file(job["template_path"])
    g = op.new_graph(template=str(path))
    if not g or len(g) != 1:
        raise ValueError("This binder supports a single-layer native XY template.")
    source = template_evidence(op, g, path, digest, "origin-new-graph")
    layer = g[0]
    plots = layer.plot_list()
    if len(plots) > 1:
        raise ValueError("Template has multiple plot slots and requires an explicit binding map.")
    requested = job.get("plot_type") or "auto"
    def check_type():
        pid = layer.get_int("plot1.pid")
        if pid not in XY_TEMPLATE_TYPES.values():
            raise ValueError("Native template plot ID %s cannot be represented by one XY series." % pid)
        if requested != "auto" and pid != XY_TEMPLATE_TYPES.get(requested):
            raise ValueError("Requested %s, but the native template produces plot ID %s." % (requested, pid))
        return pid
    if plots:
        check_type()
    w = op.new_sheet('w', lname="Template input")
    w.from_list(0, xs, x, axis='X')
    w.from_list(1, ys, y, axis='Y')
    if plots:
        plots[0].change_data(w, x=0, y=1)
    else:
        layer.add_plot(w, coly=1, colx=0, type="?")
    layer.rescale()
    if len(layer.plot_list()) != 1:
        raise RuntimeError("Origin did not produce the requested XY plot.")
    pid = check_type()
    bound = {}
    for index, role in enumerate(("x", "y")):
        data = _bound_data(op, layer, layer.plot_list()[0], role, {})
        expected_source = w.obj[index].GetDatasetName()
        if not data or not expected_source or str(data["name"]).casefold() != str(expected_source).casefold():
            raise RuntimeError("Origin could not confirm the template plot's %s source." % role.upper())
        bound[role] = data
    if job.get("title"):
        g.lname = job["title"]
    return {"graph": g, "datasets": [w], "expected": {"layer_count": 1, "min_plots": [1]},
            "template_binding": {"method":"native-template-xy", "passed":True, "bindings":bound,
                                 **source, "plot_type_id":pid}}


def _numeric_column(records, row_numbers, name, *, missing=False, nonnegative=False):
    values = []
    for index, row in zip(row_numbers, records, strict=True):
        value = row[name]
        if missing and (value is None or isinstance(value, str) and not value.strip()):
            values.append(None)
            continue
        try:
            number = float(value)
            if isinstance(value, bool) or not math.isfinite(number) or nonnegative and number < 0:
                raise ValueError
        except (ValueError, TypeError) as exc:
            required = "nonnegative finite number" if nonnegative else "finite number"
            raise ValueError(f"Row {index}, column {name!r}: expected a {required}.") from exc
        values.append(number)
    if not any(value is not None for value in values):
        raise ValueError(f"Column {name!r} has no numeric observations.")
    return values


def _read_binding(op, layer, plot, role, sheet, index, values):
    found = _bound_data(op, layer, plot, role, {})
    expected = str(sheet.obj[index].GetDatasetName())
    if (not found or found["name"].casefold() != expected.casefold()
            or found.get("content_sha256") != data_fingerprint(values)):
        raise RuntimeError(f"Origin did not bind the expected {role.upper()} data to {plot.lt_range()} "
                           f"from {expected} (reported {(found or {}).get('name')}).")
    return found


def _replace_error_plot(layer, error, working):
    names = [str(working.obj[i].GetDatasetName()) for i in (1, 2)]
    if not all(DATASET_NAME.fullmatch(name) for name in names):
        raise RuntimeError("Origin did not report valid replacement dataset names.")
    main_name, error_name = names
    index = error.index() + 1
    color = error.color
    width = layer.get_float(f"plot{index}.line.width")
    style = layer.get_int(f"plot{index}.line.type")
    error.remove()
    if not layer.obj.LT_execute(f"layer -i {error_name};set {error_name} -o {main_name};"):
        raise RuntimeError("Origin rejected attachment of the replacement error bar.")
    plots = layer.plot_list()
    if (index > len(plots) or layer.get_int(f"plot{index}.pid") != 231
            or str(plots[index - 1].obj.GetDatasetName()).casefold() != error_name.casefold()):
        raise RuntimeError("Origin did not attach the replacement error bar in the original slot.")
    replacement = plots[index - 1]
    replacement.color = color
    layer.set_float(f"plot{index}.line.width", width)
    layer.set_int(f"plot{index}.line.type", style)
    return replacement


def _bind_graph(op, graph, job, *, new=False):
    from recipes.bindings import plot_id
    from recipes.model import RecipeError
    from recipes.native import _bind_ticks, _fill, histogram_counts
    from recipes.prepare import prepare

    tables = {entry["sheet"]: entry for entry in job["tables"]}
    types = {**XY_TEMPLATE_TYPES, "bar": 215, "histogram": 219, "heatmap": 105}
    slots = [list(layer.plot_list()) for layer in graph]
    expected_existing = {(i, j) for i, layer in enumerate(graph, 1)
                         for j, p in enumerate(slots[i - 1], 1) if plot_id(layer, p) != 231}
    targets = {(b["layer"], b["plot"]) for b in job["bindings"]}
    if new and not expected_existing <= targets:
        raise ValueError(f"Template is missing bindings for existing layer/plot targets: {sorted(expected_existing - targets)}")
    original = inspect_graph(op, graph) if not new else None
    expected_appends = [len(items) + 1 for items in slots]
    plans = []
    covered_error_slots = set()
    grouped_layers = set()
    for spec in job["bindings"]:
        li, pi = spec["layer"], spec["plot"]
        if li > len(graph):
            raise ValueError(f"Layer {li} does not exist in the selected graph.")
        layer = graph[li - 1]
        existing = slots[li - 1]
        plot = existing[pi - 1] if pi <= len(existing) else None
        if plot is None:
            if not new or pi != expected_appends[li - 1]:
                raise ValueError(f"Layer {li}, plot {pi}: use an existing plot or consecutive slots in an empty template.")
            expected_appends[li - 1] += 1
        requested = spec.get("plot_type", "auto")
        if requested not in (*types, "auto"):
            raise ValueError(f"Unsupported plot type {requested!r}.")
        columns = spec["columns"]
        table = tables[spec["sheet"]]
        records = table["records"]
        requested_pid = types.get(requested)
        pid = plot_id(layer, plot) if plot is not None else requested_pid
        if requested_pid is not None and pid != requested_pid:
            raise ValueError(f"Layer {li}, plot {pi} has native type {pid}, expected {requested_pid}.")
        error = existing[pi] if plot is not None and pi < len(existing) and plot_id(layer, existing[pi]) == 231 else None
        if error is not None:
            if "y_error" not in columns or pi + 1 in targets:
                raise ValueError(f"Map the error column on its parent plot at layer {li}, plot {pi}.")
            if pi + 1 < len(existing) and plot_id(layer, existing[pi + 1]) == 231:
                raise ValueError("Multiple error bars on one plot require a dedicated recipe.")
            covered_error_slots.add((li, pi + 1))
        if "x" in columns:
            options = spec.get("options", {})
            if options == {"group": True} and new:
                grouped_layers.add(li)
            elif options:
                raise ValueError("XY bindings only support options.group=true for a new template graph.")
            if pid not in {None, *XY_TEMPLATE_TYPES.values(), 215, 216}:
                raise ValueError(f"Layer {li}, plot {pi}: native type {pid} does not accept these XY roles/options.")
            if not new and "y_error" in columns and error is None:
                raise ValueError(f"Layer {li}, plot {pi} has no Y-error bar to replace.")
            values = {role: _numeric_column(records, table["row_numbers"], column,
                                            missing=role == "y", nonnegative=role == "y_error")
                      for role, column in columns.items()}
            plans.append((spec, records, layer, plot, error, pid, values, None))
        else:
            kind = "heatmap" if "row" in columns else "histogram"
            native_id = types[kind]
            if pid not in (None, native_id):
                raise ValueError(f"Layer {li}, plot {pi}: these columns require native {kind}.")
            try:
                plan = prepare(kind, records, columns=columns, options=spec.get("options"))
            except RecipeError as exc:
                fields = ", ".join(f"{role}={name!r}" for role, name in columns.items())
                raise ValueError(f"Layer {li}, plot {pi}, {fields}: {exc}") from exc
            plans.append((spec, records, layer, plot, error, native_id, None, plan))
    if new:
        all_errors = {(i, j) for i, layer in enumerate(graph, 1)
                      for j, p in enumerate(slots[i - 1], 1) if plot_id(layer, p) == 231}
        if all_errors != covered_error_slots:
            raise ValueError("The template contains error bars whose parent/data mapping is unknown.")

    book = op.new_book("w", lname="Replacement data")
    if book is None:
        raise RuntimeError("Origin could not allocate the replacement data workbook.")
    saved_tables = set()
    results = []
    for number, (spec, records, layer, plot, error, pid, values, plan) in enumerate(plans, 1):
        columns = spec["columns"]
        units = spec.get("units", {})
        if spec["sheet"] not in saved_tables:
            raw = book[0] if not saved_tables else book.add_sheet(f"Source{number}")
            raw.name = f"Source{number}"
            _fill(raw, [(name, ["" if r[name] is None else str(r[name]) for r in records], "N")
                        for name in records[0]])
            saved_tables.add(spec["sheet"])
        working = book.add_sheet(f"Binding{number}")
        result = {"layer": spec["layer"], "plot": spec["plot"], "columns": columns,
                  "input_sheet": spec["sheet"]}
        if values is not None:
            names = ("x", "y", "y_error") if "y_error" in values else ("x", "y")
            working.cols = len(names)
            for index, role in enumerate(names):
                working.from_list(index, [float("nan") if v is None else v for v in values[role]],
                                  lname=columns[role], units=units.get(role, ""), axis=("X", "Y", "E")[index])
            if plot is None:
                plot = layer.add_plot(working, colx=0, coly=1, colyerr=2 if len(names) == 3 else -1, type="?")
                if plot is not None and len(names) == 3:
                    following = layer.plot_list()[plot.index() + 1:]
                    error = following[0] if following and plot_id(layer, following[0]) == 231 else None
            else:
                plot.change_data(working, x=0, y=1)
                if error is not None:
                    error = _replace_error_plot(layer, error, working)
            if plot is None or plot_id(layer, plot) not in ({pid} if pid else {*XY_TEMPLATE_TYPES.values(), 215, 216}):
                raise RuntimeError("Origin did not create the requested native XY plot.")
            result["data_roles"] = {role: _read_binding(op, layer, plot, role, working, i, values[role])
                                    for i, role in enumerate(("x", "y"))}
            if len(names) == 3:
                if error is None:
                    raise RuntimeError("Origin did not attach the requested error bar to the plot.")
                result["data_roles"]["y_error"] = _read_binding(op, layer, error, "error", working, 2, values["y_error"])
                result["error_plot"] = error.index() + 1
        elif pid == 219:
            observations = [r["value"] for r in plan.rows]
            working.from_list(0, observations, lname=columns["value"], units=units.get("value", ""), axis="Y")
            if plot is None:
                plot = layer.add_plot(working, coly=0, type=219)
            else:
                plot.change_data(working, y=0)
            if plot is None or plot_id(layer, plot) != pid:
                raise RuntimeError("Origin did not produce a native histogram.")
            index = plot.index() + 1
            for native, field in (("binBegin", "bin_begin"), ("binEnd", "bin_end"), ("binSize", "bin_size")):
                layer.set_float(f"plot{index}.boxchart.{native}", plan.science[field])
            if not layer.obj.LT_execute("doc -uw;"):
                raise RuntimeError("Could not recalculate the histogram.")
            result["data_roles"] = {"y": _read_binding(op, layer, plot, "y", working, 0, observations)}
            counts = histogram_counts(op, result["data_roles"]["y"]["name"], layer, index)
            if counts != plan.science["bin_counts"]:
                raise RuntimeError("Histogram counts disagree with the replacement observations.")
            result["bin_counts"] = counts
        else:
            import numpy as np

            matrix = op.new_sheet("m", lname="Replacement heatmap")
            matrix.from_np(np.asarray(plan.native["matrix"], dtype=float))
            rows, cols = np.shape(plan.native["matrix"])
            matrix.xymap = (1, cols, 1, rows)
            matrix.set_label(0, columns["value"])
            if plot is None:
                plot = layer.add_mplot(matrix, 0, type=105)
            else:
                native_name = str(matrix.obj[0].GetDatasetName())
                if not DATASET_NAME.fullmatch(native_name) or not layer.obj.LT_execute(f"layer -cy {native_name} {plot.index() + 1};"):
                    raise RuntimeError("Origin could not replace the matrix source of the heatmap.")
            if plot is None or plot_id(layer, plot) != pid:
                raise RuntimeError("Origin did not produce a native heatmap.")
            result["data_roles"] = {"z": _read_binding(op, layer, plot, "z", matrix, 0, plan.native["matrix"])}
            descriptor = plan.layers[0]
            ticks = [working, *(book.add_sheet(f"Labels{number}_{i}") for i in range(1, len(plan.tables)))]
            for tick_sheet, table in zip(ticks, plan.tables, strict=True):
                _fill(tick_sheet, table.columns)
            _bind_ticks(layer, "x", descriptor.x_labels, ticks)
            _bind_ticks(layer, "y", descriptor.y_labels, ticks)
            result["row_labels"], result["column_labels"] = plan.science["rows"], plan.science["columns"]
        result["native_plot"] = plot.index() + 1
        result["plot_type_id"] = plot_id(layer, plot)
        results.append(result)
    for li in {result["layer"] for result in results}:
        layer = graph[li - 1]
        if li in grouped_layers:
            if len(layer.plot_list()) < 2 or any(plot_id(layer, plot) == 231 for plot in layer.plot_list()):
                raise ValueError("Grouping requires two or more series without attached error bars.")
            layer.group(True, 0, len(layer.plot_list()) - 1)
        layer.rescale()
        legend = layer.label("legend")
        if (new and legend is not None and all(line.startswith(r"\l(") and "%" in line
                                               for line in legend.text.splitlines())):
            if not layer.obj.LT_execute("legend -r;"):
                raise RuntimeError("Origin could not update the legend for the mapped series.")
            if li in grouped_layers:
                # Some stock templates define the legend by points in one curve.
                legend = layer.label("legend")
                legend.text = "\n".join(rf"\l({i}) %({i})" for i in range(1, len(layer.plot_list()) + 1))
    if original is not None:
        actual = inspect_graph(op, graph)
        for i, (before_layer, after_layer) in enumerate(zip(original["layers"], actual["layers"], strict=True), 1):
            for j, (before, after) in enumerate(zip(before_layer["plots"], after_layer["plots"], strict=True), 1):
                if ((i, j) not in targets | covered_error_slots
                        and (before["plot_type_id"], before["data_roles"]) != (after["plot_type_id"], after["data_roles"])):
                    raise RuntimeError(f"Unselected data at layer {i}, plot {j} changed.")
    return {"method": "native-plot-bindings", "passed": True, "bindings": results,
            "automatic_group_layers": sorted(grouped_layers)}


def _axis_label(layer, direction):
    if direction == "x":
        return layer.label("xb") or layer.label("xt")
    return layer.label("yl") or layer.label("yr")


def _apply_changes(graph, changes, op=None):
    allowed = {"layer", "plot", "x_title", "y_title", "x_range", "y_range", "color",
               "line_width", "symbol_size", "legend_text", "long_name", "width_mm", "height_mm",
               "bin_width", "bin_count", "bin_begin", "bin_end", "x_scale", "y_scale",
               "x_major_ticks", "y_major_ticks",
               "line_style", "symbol_kind", "fill_color", "x_title_size", "y_title_size", "palette", "color_levels"}
    unknown = set(changes) - allowed
    if unknown or not set(changes) - {"layer", "plot"}:
        raise ValueError("Specify at least one supported edit; unknown keys: %s" % sorted(unknown))
    li, pi = int(changes.get("layer", 1)), int(changes.get("plot", 1))
    if li < 1 or li > len(graph):
        raise ValueError("Layer index is outside the graph.")
    layer = graph[li - 1]
    plots = layer.plot_list()
    plot_keys = {"color", "line_width", "symbol_size", "line_style", "symbol_kind", "fill_color", "palette", "color_levels"}
    if set(changes) & plot_keys and not 1 <= pi <= len(plots):
        raise ValueError("Plot index is outside the layer.")
    pid = layer.get_int(f"plot{pi}.pid") if set(changes) & plot_keys else None
    checks = {}
    if set(changes) & {"bin_width", "bin_count", "bin_begin", "bin_end"}:
        if not 1 <= pi <= len(plots) or layer.get_int("plot%d.pid" % pi) != 219:
            raise ValueError("Bin edits require a native histogram (plot ID 219).")
        current = _bin_info(layer, pi)
        lo = float(changes.get("bin_begin", current["bin_begin"]))
        hi = float(changes.get("bin_end", current["bin_end"]))
        count = changes.get("bin_count")
        if count is not None and ("bin_width" in changes or type(count) is not int or count <= 0):
            raise ValueError("Specify either a positive integer bin_count or a positive bin_width.")
        width = (hi-lo)/count if count is not None else float(changes.get("bin_width", current["bin_width"]))
        if not all(math.isfinite(x) for x in (lo, hi, width)) or hi <= lo or width <= 0:
            raise ValueError("Invalid histogram interval or bin width.")
        for prop, val in (("binBegin", lo), ("binEnd", hi), ("binSize", width)):
            layer.set_float("plot%d.boxchart.%s" % (pi, prop), val)
        if not layer.obj.LT_execute("doc -uw;"):
            raise RuntimeError("Origin rejected histogram dependency recalculation.")
        bins = _bin_info(layer, pi)
        if any(bins[k] is None or not math.isclose(bins[k], v, abs_tol=1e-8) for k,v in
               (("bin_begin", lo), ("bin_end", hi), ("bin_width", width))) or (count and bins["bin_count"] != count):
            raise RuntimeError("Histogram settings did not survive native readback: %r" % bins)
        checks["histogram"] = bins
    dimensions = (("width_mm", "width", "resx"), ("height_mm", "height", "resy"))
    previous_dimensions = {key: _page_size(graph, field, res) for key, field, res in dimensions if key in changes}
    locked = graph.get_int("kar") if {"width_mm", "height_mm"} <= changes.keys() else None
    if locked:
        graph.set_int("kar", 0)
    try:
        for key, field, res in dimensions:
            if key in changes:
                mm = float(changes[key])
                dots_per_inch = graph.get_float(res)
                if not math.isfinite(mm) or mm <= 0 or dots_per_inch <= 0:
                    raise ValueError("Provide a positive page dimension and valid native resolution.")
                graph.set_float(field, round(mm * dots_per_inch / 25.4))
    finally:
        if locked:
            graph.set_int("kar", locked)
    for key, field, res in dimensions:
        if key in changes:
            measured = _page_size(graph, field, res)
            if measured is None or not math.isclose(measured, float(changes[key]), abs_tol=25.4 / graph.get_float(res)):
                raise RuntimeError("Page dimension failed native readback.")
            checks[key] = measured
    if any(previous and checks[key] < previous * 0.95 for key, previous in previous_dimensions.items()):
        # Origin retains absolute label and legend sizes when the canvas shrinks.
        if not graph.obj.LT_execute("page -fls -m 0.08 -u;"):
            raise RuntimeError("Origin could not fit the layers and labels to the smaller page.")

    def set_attr(target, field, value, key):
        setattr(target, field, value)
        actual = getattr(target, field)
        matching = (math.isclose(actual, value, rel_tol=1e-5, abs_tol=1e-6)
                    if isinstance(value, (int, float)) else str(actual).casefold() == str(value).casefold())
        if not matching:
            raise RuntimeError("%s did not take: requested %r, read back %r" % (key, value, actual))
        checks[key] = actual

    for key in ("x", "y"):
        axis = layer.axis(key)
        if key + "_scale" in changes:
            scale = changes[key + "_scale"]
            if scale not in ("linear", "log10"):
                raise ValueError("Axis scale must be linear or log10.")
            set_attr(axis, "scale", {"linear": 1, "log10": 2}[scale], key + "_scale")
        if key + "_title" in changes:
            set_attr(axis, "title", str(changes[key + "_title"]), key + "_title")
        if key + "_title_size" in changes:
            size = float(changes[key + "_title_size"])
            label = _axis_label(layer, key)
            if label is None or not math.isfinite(size) or size <= 0:
                raise ValueError("A positive point size and an existing axis title are required.")
            label.set_float("fsize", size)
            actual = label.get_float("fsize")
            if not math.isclose(actual, size, abs_tol=0.01):
                raise RuntimeError("Origin did not retain the axis title size.")
            checks[key + "_title_size"] = actual
        if key + "_range" in changes:
            lo, hi = [float(v) for v in changes[key + "_range"]]
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi) or axis.scale == 2 and lo <= 0:
                raise ValueError("Axis bounds must be finite and strictly increasing.")
            axis.set_limits(lo, hi)
            if not (math.isclose(axis.sfrom, lo, abs_tol=1e-7) and math.isclose(axis.sto, hi, abs_tol=1e-7)):
                raise RuntimeError("Origin did not retain %s range." % key)
            checks[key + "_range"] = [axis.sfrom, axis.sto]
        edits_key = key + "_major_ticks"
        if edits_key in changes:
            count = changes[edits_key]
            if type(count) is not int or count < 2:
                raise ValueError("Major tick count must be an integer of at least two.")
            native = f"{key}.majorTicks"
            layer.set_int(native, count)
            actual = layer.get_int(native)
            if actual != count:
                raise RuntimeError("Origin did not retain the requested major tick count.")
            checks[edits_key] = actual
    if "long_name" in changes:
        set_attr(graph, "lname", str(changes["long_name"]), "long_name")
    if "legend_text" in changes:
        legend = layer.label("legend")
        if not legend:
            raise ValueError("This layer does not have a legend object.")
        set_attr(legend, "text", str(changes["legend_text"]), "legend_text")
    if "color" in changes:
        value = str(changes["color"])
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("color must be a #RRGGBB value.")
        plot = plots[pi - 1]
        plot.color = value
        checks["color"] = _hex_color(plot.color)
        if checks["color"] != value.casefold():
            raise RuntimeError("Origin did not retain the requested color.")
    if "fill_color" in changes:
        value = changes["fill_color"]
        if pid not in BAR_PLOTS or not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("fill_color requires a bar, column or histogram and a #RRGGBB value.")
        checks["fill_color"] = _fill_color(op, layer, plots[pi - 1], value)
        if checks["fill_color"] != value.casefold():
            raise RuntimeError("Origin did not retain the requested fill color.")
    if "line_style" in changes:
        styles = {"solid": 1, "dash": 2, "dot": 3}
        style = styles.get(changes["line_style"])
        if pid not in LINE_PLOTS or style is None:
            raise ValueError("line_style requires a line-capable plot and solid, dash or dot.")
        prop = f"plot{pi}.line.type"
        layer.set_int(prop, style)
        checks["line_style"] = layer.get_int(prop)
        if checks["line_style"] != style:
            raise RuntimeError("Origin did not retain the line style.")
    if "symbol_kind" in changes:
        kind = changes["symbol_kind"]
        if pid not in (201, 202) or type(kind) is not int or kind < 1:
            raise ValueError("symbol_kind requires a scatter/line-symbol plot and a positive Origin symbol index.")
        set_attr(plots[pi - 1], "symbol_kind", kind, "symbol_kind")
    if "symbol_size" in changes:
        size = float(changes["symbol_size"])
        if not math.isfinite(size) or size <= 0:
            raise ValueError("Symbol size must be positive.")
        set_attr(plots[pi - 1], "symbol_size", size, "symbol_size")
    if "line_width" in changes:
        width = float(changes["line_width"])
        if not math.isfinite(width) or width <= 0:
            raise ValueError("Line width must be positive.")
        prop = "plot%d.line.width" % pi
        layer.set_float(prop, width)
        read = layer.get_float(prop)
        if not math.isclose(read, width, abs_tol=1e-5):
            raise RuntimeError("Could not verify plot line width.")
        checks["line_width"] = read
    if {"palette", "color_levels"} & changes.keys():
        if pid != 105:
            raise ValueError("Palette and color levels require a native heatmap.")
        plot = plots[pi - 1]
        if "palette" in changes:
            palette = changes["palette"]
            if not isinstance(palette, str) or not palette.strip():
                raise ValueError("Specify the name of an installed Origin palette or color list.")
            plot.colormap = palette
            checks["palette"] = plot.colormap
            if Path(checks["palette"]).stem.casefold() != Path(palette).stem.casefold():
                raise RuntimeError("Origin did not retain the requested palette.")
        if "color_levels" in changes:
            levels = [float(v) for v in changes["color_levels"]]
            if len(levels) < 2 or not all(map(math.isfinite, levels)) or any(a >= b for a, b in zip(levels, levels[1:])):
                raise ValueError("Color levels must be finite and strictly increasing.")
            plot.zlevels = {"minors": 0, "levels": levels}
            actual = plot.zlevels["levels"]
            if len(actual) != len(levels) or any(not math.isclose(a, b, abs_tol=1e-8) for a, b in zip(actual, levels)):
                raise RuntimeError("Origin did not retain the requested color levels.")
            checks["color_levels"] = plot.zlevels
    return checks


def perform(op, job):
    action = job["action"]
    origin = {"pid": os.getpid(), "origin_version": _probe(op.org_ver),
              "project_folder":_probe(lambda: op.path("p")), "project_name":_probe(lambda: op.get_lt_str("%G")),
              "embedded_python": sys.version.split()[0]}
    if action == "doctor":
        return {"origin": origin, "graphs": [g.name for g in op.graph_list('p')]}
    if action == "snapshot":
        # pe_save exports the Project Explorer tree; save/SaveAs would rebind the user's window.
        op.set_lt_str("opbSnapshotPath", job["output_path"])
        if op.get_lt_str("opbSnapshotPath") != job["output_path"]:
            raise RuntimeError("Origin could not confirm the project snapshot destination.")
        if not op.lt_exec("pe_save path:=/ sub:=1 fname:=opbSnapshotPath$;"):
            raise RuntimeError("Origin could not export the Project Explorer tree.")
        if origin["project_folder"] != op.path("p") or origin["project_name"] != op.get_lt_str("%G"):
            raise RuntimeError("The attached project association changed during snapshot.")
        return {"origin":origin, "method":"pe_save", "path":job["output_path"]}
    if action == "inspect":
        if not job.get("graph_name"):
            return {"origin": origin, "graphs": [inspect_graph(op, g) for g in op.graph_list('p')]}
        return {"origin": origin, **inspect_graph(op, _graph(op, job["graph_name"]),
                                                  verify_histograms=job.get("verify_histograms", False))}
    if action == "inspect-template":
        from recipes.bindings import template_evidence, template_file
        path, digest = template_file(job["template_path"])
        graph = op.new_graph(template=str(path))
        if not graph:
            raise ValueError("Origin could not open the specified template.")
        try:
            return {"origin": origin, **inspect_graph(op, graph),
                    "template_source": template_evidence(op, graph, path, digest, "origin-new-graph")}
        finally:
            graph.destroy()
    if action in ("render", "template"):
        if action == "render":
            from recipes import build_graph
            kwargs = {"title":job.get("title"), "columns":job.get("columns"), "options":job.get("options")}
            if job.get("template_path"):
                kwargs["template_path"] = job["template_path"]
            result = build_graph(op, job["recipe_id"], job["records"], **kwargs)
        else:
            result = _template(op, job)
        graph = result["graph"]
        if isinstance(graph, str):
            graph = _graph(op, graph)
        expected = result.get("expected", {})
        extra = {"expected": expected, "warnings": result.get("warnings", []),
                 "datasets": [s if isinstance(s, str) else s.lt_range() for s in result.get("datasets", [])]}
        extra["automatic_group_layers"] = result.get("automatic_group_layers", [])
        if action == "render":
            extra["recipe_id"] = job["recipe_id"]
        if job.get("template_path"):
            binding = result.get("template_binding")
            if not binding or binding.get("passed") is not True:
                raise RuntimeError("Requested template binding has no native evidence.")
            extra["template_binding"] = binding
            extra["automatic_group_layers"] = binding.get("automatic_group_layers", extra["automatic_group_layers"])
        if job.get("changes"):
            extra["changes_verified"] = _apply_changes(graph, job["changes"], op)
    elif action == "edit":
        graph = _graph(op, job["graph_name"])
        if job.get("expected_state") is not None:
            now = {"origin":origin, **inspect_graph(op, graph)}
            if now != job["expected_state"]:
                raise RuntimeError("The project or graph changed since inspection. Inspect again before editing.")
        extra = {}
        if job.get("binding_job"):
            extra["data_binding"] = _bind_graph(op, graph, job["binding_job"])
        extra["changes_verified"] = _apply_changes(graph, job["changes"], op) if job.get("changes") else {}
    else:
        raise ValueError("Unknown embedded action")
    if job.get("journal"):
        from journals import apply_journal_style
        journal_options = dict(job.get("journal_options") or {})
        if action == "render" and job["recipe_id"] == "multi-panel":
            journal_options.setdefault("panel_label", [chr(65 + i) for i in range(len(graph))])
        extra["journal_style"] = apply_journal_style(op, graph, job["journal"], **journal_options)
    info = inspect_graph(op, graph)
    binding = extra.get("data_binding") or extra.get("template_binding") or {}
    heatmaps = [(mapped["layer"], mapped["column_labels"], mapped["row_labels"])
                for mapped in binding.get("bindings", ()) if isinstance(mapped, dict) and "row_labels" in mapped]
    if extra.get("recipe_id") == "heatmap":
        science = expected["science"]
        heatmaps.append((1, science["columns"], science["rows"]))
    for layer_index, columns, rows in heatmaps:
        axes = info["layers"][layer_index - 1]["axes"]
        if axes["x"]["tick_labels"] != columns or axes["y"]["tick_labels"] != rows:
            raise RuntimeError(f"Layer {layer_index}: native heatmap row/column labels do not match the input.")
    count = extra.get("expected", {}).get("layer_count")
    minimums = extra.get("expected", {}).get("min_plots", [])
    if count is not None and count != info["layer_count"]:
        raise RuntimeError("Origin layer count disagrees with recipe.")
    if isinstance(minimums, int):
        minimums = [minimums]
    if len(minimums) > info["layer_count"] or any(n > m for n, m in zip(minimums, info["plot_counts"])):
        raise RuntimeError("Origin plot counts disagree with the recipe.")
    if job.get("changes"):
        extra["changes_target"] = {key: int(job["changes"].get(key, 1)) for key in ("layer", "plot")}
        if "histogram" in extra.get("changes_verified", {}):
            from recipes.native import histogram_counts

            target = extra["changes_target"]
            binding = extra.get("data_binding") or extra.get("template_binding") or {}
            for mapped in binding.get("bindings", ()):  # explicit native bindings
                if (isinstance(mapped, dict) and mapped.get("layer") == target["layer"]
                        and mapped.get("native_plot") == target["plot"] and "bin_counts" in mapped):
                    mapped["bin_counts"] = histogram_counts(op, mapped["data_roles"]["y"]["name"],
                                                           graph[target["layer"] - 1], target["plot"])
    return {"origin": origin, **info, **extra}


def run_job(job_path):
    import traceback
    p = Path(job_path)
    job = json.loads(p.read_text(encoding="utf-8"))
    added_path = job["scripts"]
    try:
        if job.get("expected_pid") and os.getpid() != job["expected_pid"]:
            raise RuntimeError("The Origin process changed. Reconnect and inspect the intended session.")
        # External originpro would silently launch a second Origin; reject it before accessing COM.
        import originpro as op
        if op.oext:
            raise RuntimeError("originpro is in external mode inside Origin. Embedded originpro/PyOrigin is required.")
        if op.lt_int(job["cookie_name"]) != job["cookie_value"]:
            raise RuntimeError("The embedded Python interpreter belongs to a different Origin session.")
        sys.path.insert(0, added_path)
        data = {"ok": True, "result": perform(op, job)}
    except Exception as exc:
        data = {"ok": False, "error": type(exc).__name__ + ": " + str(exc),
                "trace": traceback.format_exc(limit=4)}
    finally:
        if sys.path and sys.path[0] == added_path:
            sys.path.pop(0)
    out = p.with_name("reply.json")
    temp = p.with_name("reply.tmp")
    try:
        body = json.dumps(data, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        body = json.dumps({"ok": False, "error": "Non-serializable Origin evidence: " + str(exc)})
    temp.write_text(body, encoding="utf-8")
    os.replace(str(temp), str(out))
