"""Render inside the caller's existing Origin Python session. No attach, save or exit."""

import math
import re

from .bindings import check_xy, dataset_name, mark_types, plot_id, template_evidence, template_file
from .model import RecipeError
from .prepare import prepare


COLORS = ("#17678A", "#BD5B39", "#389071", "#8664A1", "#AC762F", "#617786")
TYPES = {"line": "l", "line-symbol": "y", "scatter": "s", "template": "?", "reference": "l"}


def _read_matching(sheet, column, values):
    """Origin pads unequal columns; compare the part we actually supplied."""
    actual = sheet.to_list(column)[:len(values)]
    if len(actual) < len(values) and all(v == "" for v in values[len(actual):]):
        actual += [""] * (len(values) - len(actual))
    if len(actual) != len(values):
        raise RuntimeError(f"Origin returned incomplete worksheet column {column + 1}")
    for observed, wanted in zip(actual, values):
        if isinstance(wanted, (int, float)):
            try:
                ok = math.isclose(float(observed), wanted, rel_tol=1e-10, abs_tol=1e-10)
            except (ValueError, TypeError):
                ok = False
        else:
            ok = str(observed) == wanted
        if not ok:
            raise RuntimeError(f"Origin changed a value in worksheet column {column + 1}")


def _fill(sheet, columns):
    sheet.cols = len(columns)
    for i, (name, values, axis) in enumerate(columns):
        if values and all(isinstance(v, str) for v in values):
            # Origin's default numeric/text format may parse a subject code "001"
            # as 1. DF_TEXT is the same native format used by originpro.from_df.
            from originpro.config import po
            sheet.obj[i].SetDataFormat(po.DF_TEXT)
        sheet.from_list(i, values, lname=name, axis=axis)
        _read_matching(sheet, i, values)


def _execute(layer, command):
    # WSheet/GLayer.lt_exec intentionally discards the Origin success flag.
    if not layer.obj.LT_execute(command):
        raise RuntimeError(f"Origin rejected the recipe operation: {command}")


def _histogram_bins(op, plan, gl):
    for field, key in (("binBegin", "bin_begin"), ("binEnd", "bin_end"), ("binSize", "bin_size")):
        gl.set_float("plot1.boxchart." + field, plan.science[key])
    if not op.lt_exec("doc -uw;"):
        raise RuntimeError("Origin could not update histogram dependencies")
    for field, key in (("binBegin", "bin_begin"), ("binEnd", "bin_end"), ("binSize", "bin_size")):
        if not math.isclose(gl.get_float("plot1.boxchart." + field), plan.science[key], rel_tol=1e-7, abs_tol=1e-9):
            raise RuntimeError(f"Native histogram {field} does not match the requested bins")


def _check_histogram(op, graph, sheet, plan):
    gl = graph[0]
    plots = gl.plot_list()
    if len(plots) != 1 or plot_id(gl, plots[0]) != 219:
        raise RuntimeError("The saved template did not produce one native histogram")
    plot = plots[0]
    name = dataset_name(op, gl, plot.lt_range(), "y", f"{sheet.lt_range(False)}!col(1)")
    counts = histogram_counts(op, name, gl, 1)
    if counts != plan.science["bin_counts"]:
        raise RuntimeError("Origin bin counts disagree with the distribution of the replacement observations")
    return {"pid": 219, "y": name, "bin_count_method": "origin-histogram", "bin_counts": counts}


def histogram_counts(op, dataset, layer, index):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:@\d+)?", dataset):
        raise RuntimeError("Cannot compute counts for the reported histogram dataset name")
    lo, hi, width = (layer.get_float(f"plot{index}.boxchart.{key}")
                     for key in ("binBegin", "binEnd", "binSize"))
    if not all(map(math.isfinite, (lo, hi, width))) or width <= 0 or hi <= lo:
        raise RuntimeError("Invalid native histogram limits")
    scratch = op.new_sheet("w", hidden=True)
    if scratch is None:
        raise RuntimeError("Origin could not create a temporary histogram worksheet")
    try:
        _execute(scratch, f"col(1)=histogram({dataset},{width:.17g},{lo:.17g},{hi:.17g});")
        counts = scratch.to_list(0)
        if not counts or any(not math.isfinite(v) or v < 0 or int(v) != v for v in counts):
            raise RuntimeError("Origin returned incomplete histogram counts")
        return [int(v) for v in counts]
    finally:
        scratch.get_book().destroy()


def _indexed_distribution(op, plan, original, template, created, proof):
    """Rebuild the native statistical objects using the Origin 2021b+ X-Function."""
    book = original.get_book()
    indexed = book.add_sheet("IndexedB")
    group_ids = {g: i + 1 for i, g in enumerate(plan.native["groups"])}
    values = [r["value"] for r in plan.rows]
    _fill(indexed, [("Group index", [group_ids[r["group"]] for r in plan.rows], "X"),
                    ("Observed value", values, "Y")])
    before = {g.name for g in op.pages("g")}
    indexed.activate()
    op.set_lt_str("__oprec_template", str(template))
    if str(op.get_lt_str("__oprec_template")) != str(template):
        raise RuntimeError("Origin could not retain the requested template path")
    rg = indexed.lt_range(False)
    theme = ' theme:="Box_Violin"' if plan.recipe_id == "violin" else ""
    command = (f"plot_gboxindexed irng:={rg}!col(2) group:={rg}!col(1) "
               "template:=__oprec_template$" + theme + ";")
    try:
        if not op.lt_exec(command):
            raise RuntimeError("Origin rejected grouped statistical template binding (requires 2021b+)")
    finally:
        op.set_lt_str("__oprec_template", "")
    graph = op.find_graph()
    if graph is None or graph.name in before:
        raise RuntimeError("No new grouped statistical graph was created")
    created.append(graph)
    if len(graph) != 1:
        raise RuntimeError("Expected a one-layer grouped distribution graph")
    gl = graph[0]
    gl.activate()
    # Remove only optional overlays in the newly created copy. B's own
    # per-observation scatter plots are subsequently bound by _style_layer.
    for p in reversed(gl.plot_list()):
        if plan.recipe_id == "box-raw" and plot_id(gl, p) == 201:
            p.remove()
    plots = gl.plot_list()
    groups = plan.native["groups"]
    if len(plots) != len(groups) or any(plot_id(gl, p) != 206 for p in plots):
        raise RuntimeError("Unable to verify one native distribution plot for each new group")
    # Locate the native plot source inside B's new book (the X-Function may
    # append an unstacked output sheet). Never accept an identically named A.
    actual_columns = {}
    for ws in book:
        for c in range(ws.cols):
            _execute(gl, f"range __oprec_c={ws.lt_range(False)}!col({c+1});"
                         "string __oprec_cname$=nameof(__oprec_c)$;")
            actual_columns[str(op.get_lt_str("__oprec_cname"))] = (ws, c)
    seen, binding = set(), []
    for name, plot in zip(groups, plots):
        _execute(gl, f"range -wy __oprec_boxdata={plot.lt_range()};"
                     "string __oprec_boxname$=nameof(__oprec_boxdata)$;")
        source = str(op.get_lt_str("__oprec_boxname") or "")
        if not source or source in seen or source not in actual_columns:
            raise RuntimeError(f"Cannot locate a distinct replacement column for group {name!r}")
        seen.add(source)
        ws, c = actual_columns[source]
        expected = [r["value"] for r in plan.rows if r["group"] == name]
        numbers = []
        for v in ws.to_list(c):
            if v is None or str(v).strip() in {"", "--"}:
                continue
            n = float(v)
            if math.isfinite(n):
                numbers.append(n)
        if len(numbers) != len(expected) or any(not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
                                                for a, b in zip(sorted(numbers), sorted(expected))):
            raise RuntimeError(f"Bound observations do not reproduce group {name!r}")
        binding.append({"group":name,"dataset":source,"n":len(numbers),"pid":206})
    proof["statistics"] = {"source_workbook": book.name, "groups": binding,
                           "requested_theme": "Box_Violin" if plan.recipe_id == "violin" else "template"}
    return graph


def _native_statistics(op, plan, sheet, created, template, proof):
    before = {graph.name for graph in op.pages("g")}
    sheet.activate()
    rg = sheet.lt_range(False)
    kind = plan.native["special"]
    if template and kind in {"box-raw", "violin"}:
        return _indexed_distribution(op, plan, sheet, template, created, proof)
    if template and kind == "histogram":
        graph = op.new_graph(lname=plan.title, template=str(template))
        if graph is None:
            raise RuntimeError("Could not open the native histogram template")
        created.append(graph)
        if len(graph) != 1:
            raise RecipeError("Histogram OTPU must contain exactly one layer")
        gl = graph[0]
        plots = gl.plot_list()
        if not plots:
            if gl.add_plot(sheet, coly=0, type=219) is None:
                raise RuntimeError("Origin could not add a native histogram to the template")
        elif len(plots) == 1 and plot_id(gl, plots[0]) == 219:
            plots[0].change_data(sheet, y=0)
        else:
            raise RecipeError("Template plot slots do not describe a single histogram")
        _histogram_bins(op, plan, gl)
        proof["statistics"] = _check_histogram(op, graph, sheet, plan)
        return graph
    if kind == "histogram":
        command = f"plotxy iy:={rg}!1 plot:=219 ogl:=<new template:=HISTGM>;"
    else:
        ncols = len(plan.native["groups"])
        theme = ' theme:="Box_Violin"' if kind == "violin" else ""
        command = f'plotgboxraw irng:={rg}!1:{ncols} num:=1 g1:="Long Name" sort:=0{theme};'
    if not op.lt_exec(command):
        raise RuntimeError(f"Origin could not create the {kind} statistical graph")
    graph = op.find_graph()
    if graph is None or graph.name in before:
        raise RuntimeError("No new statistical graph appeared after the Origin command")
    created.append(graph)
    if kind == "histogram":
        _histogram_bins(op, plan, graph[0])
    return graph


def _plot_heatmap(op, plan, created, template, proof):
    import numpy as np  # Origin's Python matrix bridge accepts a NumPy ndarray.

    matbook = op.new_book("m", lname="Heatmap values")
    if matbook is None:
        raise RuntimeError("Origin could not create the matrix book")
    created.append(matbook)
    matrix = matbook[0]
    values = np.asarray(plan.native["matrix"], dtype=float)
    rows, cols = values.shape
    matrix.from_np(values)
    matrix.xymap = (1, cols, 1, rows)
    matrix.set_label(0, "Value")
    if not np.allclose(matrix.to_np2d(), values, rtol=1e-10, atol=1e-10):
        raise RuntimeError("Origin matrix readback disagrees with input values")
    graph = op.new_graph(lname=plan.title, template=str(template or "Heat_Map"))
    if graph is None:
        raise RuntimeError("The Origin Heat_Map graph template is unavailable")
    created.append(graph)
    if len(graph) != 1:
        raise RuntimeError("A heatmap requires a single graph layer")
    gl = graph[0]
    existing = gl.plot_list()
    if existing:
        if not template or len(existing) != 1 or plot_id(gl, existing[0]) != 105:
            raise RuntimeError("Existing graph plots do not match the heatmap contract")
        native_name = str(matrix.obj[0].GetDatasetName())
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:@\d+)?", native_name):
            raise RuntimeError("Origin did not provide a replacement matrix dataset name")
        _execute(gl, f"layer -cy {native_name} 1;")
        plot = existing[0]
    else:
        plot = gl.add_mplot(matrix, 0, type=105)
    if plot is None or len(gl.plot_list()) != 1:
        raise RuntimeError("Origin could not bind exactly one heatmap")
    if template:
        if plot_id(gl, plot) != 105:
            raise RuntimeError("Expected native heatmap PID 105")
        z = dataset_name(op, gl, plot.lt_range(), "z", matrix.lt_range(False) + "!1")
        proof["matrix"] = {"pid": 105, "z": z, "shape": [rows, cols], "matrix_readback": True}
    return graph, matrix


def _bind_ticks(layer, direction, descriptor, sheets):
    if descriptor:
        sheet_num, column, labels = descriptor
        dataset = f"{sheets[sheet_num].lt_range(False)}!col({column + 1})"
        _execute(layer, f"range __recipe_tick_labels={dataset};axis -ps {direction.upper()} T __recipe_tick_labels;")
        layer.set_int(direction + ".minorTicks", 0)


def _axis_title(layer, label_id, text):
    label = layer.label(label_id)
    if label is None:
        # Only fixed object identifiers appear in commands. A user's panel name
        # may contain punctuation, so assign it through the text object.
        _execute(layer, f"label -{label_id} Axis;")
        label = layer.label(label_id)
    if label is None:
        raise RuntimeError(f"Missing Origin axis title object {label_id!r}")
    label.text = text


def _keep_legend_on_page(op, layer):
    _execute(layer, "string __recipe_legend_rect$=legend.pageRect$;")
    bounds = (op.get_lt_str("__recipe_legend_rect") or "").split()
    if len(bounds) == 4:
        left, _, right, _ = map(float, bounds)
        margin = 0.98 * op.lt_float("page.width")
        if right > margin and 0 < right - left < margin:
            _execute(layer, f"legend.left={max(0, left - (right - margin)):.12g};")


def _style_layer(op, plan, idx, layer, descriptor, sheets, template, proof):
    layer.activate()
    reuse_marks = bool(template and not plan.native.get("special"))
    original_slots = list(layer.plot_list()) if reuse_marks else []
    slots = [p for p in original_slots if plot_id(layer, p) != 231]
    pending = []
    for i, m in enumerate(descriptor.marks):
        kwargs = {} if m["error"] is None else {"colyerr": m["error"]}
        sheet = sheets[m["table"]]
        allowed = mark_types(m["kind"], plan.recipe_id)
        slot = next((p for p in slots if plot_id(layer, p) in allowed), None)
        if slot is None:
            plot = layer.add_plot(sheet, coly=m["y"], colx=m["x"], type=TYPES[m["kind"]], **kwargs)
        else:
            slots.remove(slot)
            data = {"x": m["x"], "y": m["y"]}
            slot.change_data(sheet, **data)
            plot = slot
        if plot is None:
            raise RuntimeError(f"Origin could not add {m['kind']} on layer {idx + 1}")
        pending.append((plot, m, sheet))
        if not template and not plan.native.get("bar_mode"):
            color = m["color_index"] if m["color_index"] is not None else i
            plot.color = COLORS[color % len(COLORS)]
            if m["kind"] in ("scatter", "line-symbol"):
                plot.symbol_size = 5
    for slot in reversed(slots):
        slot.remove()  # only the freshly loaded copy, never the source file
    mode = plan.native.get("bar_mode")
    if mode:
        if len(descriptor.marks) > 1:
            layer.group(True, 0, len(descriptor.marks) - 1)
        if mode in ("stacked", "diverging"):
            # Origin's cumulative stacking groups positive and negative bars about zero.
            _execute(layer, "layer -b s 1;")
    layer.rescale()
    _bind_ticks(layer, "x", descriptor.x_labels, sheets)
    _bind_ticks(layer, "y", descriptor.y_labels, sheets)
    if descriptor.xlim:
        layer.axis("x").set_limits(*descriptor.xlim)
    if descriptor.ylim:
        layer.axis("y").set_limits(*descriptor.ylim)
    if plan.recipe_id != "dual-y" or idx == 0:
        _axis_title(layer, "xb", descriptor.x_title)
    ylabel = "yr" if idx == 1 and plan.recipe_id == "dual-y" else "yl"
    _axis_title(layer, ylabel, descriptor.y_title)
    if descriptor.legend and len(descriptor.marks) > 1:
        _execute(layer, "legend -r;")
        _keep_legend_on_page(op, layer)
    elif layer.label("Legend") is not None:
        layer.label("Legend").remove()
    observed = len(layer.plot_list())
    if observed < descriptor.min_plots:
        raise RuntimeError(f"Layer {idx+1} retained {observed} native plots, expected at least {descriptor.min_plots}")
    if reuse_marks:
        bound = [check_xy(op, layer, plot, m, sheet, plan.recipe_id) for plot, m, sheet in pending]
        actual = layer.plot_list()
        errors = [p for p in actual if plot_id(layer, p) == 231]
        if len(actual) - len(errors) != len(bound):
            raise RuntimeError("Template contains unexpected or stale data plots")
        error_columns = [(sheet, m["error"]) for _, m, sheet in pending if m["error"] is not None]
        if len(errors) != len(error_columns):
            raise RuntimeError("Cannot verify the source of every attached Origin error bar")
        for plot, (sheet, col) in zip(errors, error_columns):
            name = str(plot.obj.GetDatasetName())
            if name.casefold() != str(sheet.obj[col].GetDatasetName()).casefold():
                raise RuntimeError("Origin attached the error bar to the wrong data column")
            bound.append({"pid": 231, "error": name})
        proof["layers"].append({"layer": idx + 1, "bindings": bound})
    elif template and plan.native.get("special") == "box-raw":
        overlay = [check_xy(op, layer, plot, m, sheet, plan.recipe_id) for plot, m, sheet in pending]
        if observed != len(proof["statistics"]["groups"]) + len(overlay):
            raise RuntimeError("Unexpected native plots remain in the replacement box graph")
        proof["layers"].append({"layer": idx + 1, "bindings": overlay})
    return observed


def build_graph(op, recipe_id, records, *, title=None, columns=None, options=None, template_path=None):
    """Return the graph and source/working sheets. The caller owns persistence."""
    plan = prepare(recipe_id, records, title=title, columns=columns, options=options)
    template, digest = template_file(template_path)
    proof = {"mode": "native-graph-template", "path": str(template), "sha256": digest, "layers": []} if template else {}
    # Keep every input field. Use normalized numeric types for mapped number roles and
    # preserve the source spelling of text identifiers, including leading zeroes.
    raw_names = list(dict.fromkeys(k for row in records for k in row))
    mapped = {(columns or {}).get(role, role): role for role in plan.rows[0]}
    raw_columns = []
    for name in raw_names:
        values = [r[mapped[name]] for r in plan.rows] if name in mapped else [
            "" if r.get(name) is None else str(r[name]) for r in records
        ]
        raw_columns.append((name, values, "N"))
    created = []
    try:
        book = op.new_book("w", lname=plan.title + " · Data")
        if book is None:
            raise RuntimeError("Origin could not allocate a worksheet book")
        created.append(book)
        source = book[0]
        source.name = "Source"
        _fill(source, raw_columns)
        sheets = []
        for i, table in enumerate(plan.tables, 1):
            sheet = book.add_sheet("Data" + str(i))
            if sheet is None:
                raise RuntimeError("Origin could not allocate a working sheet")
            _fill(sheet, table.columns)
            sheets.append(sheet)
        special = plan.native.get("special")
        extras = []
        if special == "heatmap":
            graph, matrix = _plot_heatmap(op, plan, created, template, proof)
            extras.append(matrix)
        elif special:
            graph = _native_statistics(op, plan, sheets[plan.native["table"]], created, template, proof)
            graph.lname = plan.title
        else:
            graph = op.new_graph(lname=plan.title, template=str(template or plan.template))
            if graph is None:
                raise RuntimeError(f"Origin graph template {plan.template!r} was not found")
            created.append(graph)
        if len(graph) != len(plan.layers):
            raise RuntimeError(f"Template created {len(graph)} layers; expected {len(plan.layers)}")
        if template:
            loader = "origin-indexed-distribution" if special in {"box-raw", "violin"} else "origin-new-graph"
            proof.update(template_evidence(op, graph, template, digest, loader))
        counts = [_style_layer(op, plan, i, graph[i], d, sheets, template, proof) for i, d in enumerate(plan.layers)]
        graph.activate()
        if template:
            proof["passed"] = True
            proof["status"] = "native-bindings-read-back"
        return {"graph": graph, "datasets": [source, *sheets, *extras], "expected": plan.expected,
                "observed": {"layer_count": len(graph), "plot_counts": counts}, "warnings": plan.warnings,
                "template_binding": proof,
                "automatic_group_layers": [i for i, count in enumerate(counts, 1)
                                           if plan.native.get("bar_mode") and count > 1]}
    except Exception:
        # Never close or reset the caller's project. Only clean up pages allocated here.
        for page in reversed(created):
            try:
                page.destroy()
            except Exception:
                pass
        raise
