"""Actions run inside Origin's embedded Python, on the graph's owning GUI thread."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys

XY_TEMPLATE_TYPES = {"line": 200, "scatter": 201, "line+symbol": 202, "column": 203}


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


def _bound_data(op, layer, plot, role, cache):
    """Read the actual designated source and fingerprint its worksheet column or matrix object."""
    command = (
        'string opbDataName$="";string opbDataSheet$="";'
        'range -w%s opbDataRange=%s;'
        'opbDataName$=nameof(opbDataRange)$;opbDataSheet$=opbDataRange.GetLayer()$;'
        % (role, plot.lt_range())
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
        digest = hashlib.sha256()
        for row in rows:
            digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":"), default=str).encode("ascii"))
            digest.update(b"\n")
        info["content_sha256"] = digest.hexdigest()
        break
    cache[key] = info
    return info


def inspect_graph(op, graph):
    layers = []
    data_cache = {}
    for li, layer in enumerate(graph):
        plots = []
        for pi, plot in enumerate(layer.plot_list(), 1):
            source = _probe(lambda: plot.obj.GetDatasetName())
            pt = _probe(lambda: layer.get_int("plot%d.pid" % pi))
            item = {"index": pi, "data_source": source or None, "plot_type_id": pt or None,
                    "object_range": _probe(plot.lt_range), "color": _probe(lambda: plot.color),
                    "line_width":_probe(lambda: layer.get_float("plot%d.line.width" % pi)),
                    "symbol_size":_probe(lambda: plot.symbol_size)}
            roles = ("z",) if pt == 105 else (("y",) if pt in (206, 219, 231) else ("x", "y"))
            item["data_roles"] = {role: _probe(lambda: _bound_data(op, layer, plot, role, data_cache))
                                  for role in roles}
            if pt == 219:
                item["histogram"] = _bin_info(layer, pi)
            plots.append(item)
        axes = {}
        for key in ("x", "y"):
            ax = layer.axis(key)
            axes[key] = {"title": _probe(lambda: ax.title), "from": _probe(lambda: ax.sfrom),
                         "to": _probe(lambda: ax.sto), "scale": _probe(lambda: ax.scale)}
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
    from recipes.bindings import template_origin

    rows, x, y = job["records"], job["x"], job["y"]
    xs = [float(row[x]) for row in rows]
    ys = [float(row[y]) for row in rows]
    if not all(math.isfinite(v) for v in xs + ys):
        raise ValueError("Native XY template binding requires finite numeric columns.")
    g = op.new_graph(template=str(job["template_path"]))
    if not g or len(g) != 1:
        raise ValueError("This binder supports a single-layer native XY template.")
    reported_template = template_origin(op, g, Path(job["template_path"]))
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
                                 "native_template_source":reported_template, "plot_type_id":pid}}


def _apply_changes(graph, changes):
    allowed = {"layer", "plot", "x_title", "y_title", "x_range", "y_range", "color",
               "line_width", "symbol_size", "legend_text", "long_name", "width_mm", "height_mm",
               "bin_width", "bin_count", "bin_begin", "bin_end"}
    unknown = set(changes) - allowed
    if unknown or not set(changes) - {"layer", "plot"}:
        raise ValueError("Specify at least one supported edit; unknown keys: %s" % sorted(unknown))
    li, pi = int(changes.get("layer", 1)), int(changes.get("plot", 1))
    if li < 1 or li > len(graph):
        raise ValueError("Layer index is outside the graph.")
    layer = graph[li - 1]
    plots = layer.plot_list()
    if set(changes) & {"color", "line_width", "symbol_size"} and not 1 <= pi <= len(plots):
        raise ValueError("Plot index is outside the layer.")
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
    for key, field, res in (("width_mm","width","resx"), ("height_mm","height","resy")):
        if key in changes:
            mm = float(changes[key])
            dots_per_inch = graph.get_float(res)
            if not math.isfinite(mm) or mm <= 0 or dots_per_inch <= 0:
                raise ValueError("Provide a positive page dimension and valid native resolution.")
            graph.set_float(field, round(mm * dots_per_inch / 25.4))
            measured = _page_size(graph, field, res)
            if measured is None or not math.isclose(measured, mm, abs_tol=25.4 / dots_per_inch):
                raise RuntimeError("Page dimension failed native readback.")
            checks[key] = measured

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
        if key + "_title" in changes:
            set_attr(axis, "title", str(changes[key + "_title"]), key + "_title")
        if key + "_range" in changes:
            lo, hi = [float(v) for v in changes[key + "_range"]]
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                raise ValueError("Axis bounds must be finite and strictly increasing.")
            axis.set_limits(lo, hi)
            if not (math.isclose(axis.sfrom, lo, abs_tol=1e-7) and math.isclose(axis.sto, hi, abs_tol=1e-7)):
                raise RuntimeError("Origin did not retain %s range." % key)
            checks[key + "_range"] = [axis.sfrom, axis.sto]
    if "long_name" in changes:
        set_attr(graph, "lname", str(changes["long_name"]), "long_name")
    if "legend_text" in changes:
        legend = layer.label("legend")
        if not legend:
            raise ValueError("This layer does not have a legend object.")
        set_attr(legend, "text", str(changes["legend_text"]), "legend_text")
    if "color" in changes:
        value = str(changes["color"])
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("color must be a #RRGGBB value.")
        set_attr(plots[pi - 1], "color", value, "color")
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
        return {"origin": origin, **inspect_graph(op, _graph(op, job["graph_name"]))}
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
        if action == "render":
            extra["recipe_id"] = job["recipe_id"]
        if job.get("template_path"):
            binding = result.get("template_binding")
            if not binding or binding.get("passed") is not True:
                raise RuntimeError("Requested template binding has no native evidence.")
            extra["template_binding"] = binding
    elif action == "edit":
        graph = _graph(op, job["graph_name"])
        if job.get("expected_state") is not None:
            now = {"origin":origin, **inspect_graph(op, graph)}
            if now != job["expected_state"]:
                raise RuntimeError("The project or graph changed since inspection. Inspect again before editing.")
        extra = {"changes_verified": _apply_changes(graph, job["changes"]) if job.get("changes") else {}}
    else:
        raise ValueError("Unknown embedded action")
    if job.get("journal"):
        from journals import apply_journal_style
        journal_options = dict(job.get("journal_options") or {})
        if action == "render" and job["recipe_id"] == "multi-panel":
            journal_options.setdefault("panel_label", [chr(65 + i) for i in range(len(graph))])
        extra["journal_style"] = apply_journal_style(op, graph, job["journal"], **journal_options)
    info = inspect_graph(op, graph)
    count = extra.get("expected", {}).get("layer_count")
    minimums = extra.get("expected", {}).get("min_plots", [])
    if count is not None and count != info["layer_count"]:
        raise RuntimeError("Origin layer count disagrees with recipe.")
    if isinstance(minimums, int):
        minimums = [minimums]
    if len(minimums) > info["layer_count"] or any(n > m for n, m in zip(minimums, info["plot_counts"])):
        raise RuntimeError("Origin plot counts disagree with the recipe.")
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
