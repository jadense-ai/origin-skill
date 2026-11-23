"""Origin graph styling. Every successful write is scoped to a graph and read back."""

import math
import re


def _positive(raw, key):
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw <= 0:
        raise ValueError(key + " must be a finite positive number")
    return float(raw)


def apply_journal_style(op, graph, journal, width_mm=None, font_pt=None, stroke_pt=None,
                        panel_label=None):
    from . import load_profile

    profile = load_profile(journal)
    requested = profile["defaults"].copy()
    for key, raw in (("width_mm", width_mm), ("font_pt", font_pt), ("stroke_pt", stroke_pt)):
        if raw is not None:
            requested[key] = _positive(raw, key)
    labels = panel_label if isinstance(panel_label, (list, tuple)) else [panel_label] if panel_label else []
    if labels and (len(labels) > len(graph) or any(not re.fullmatch("[A-Za-z]{1,3}", str(x)) for x in labels)):
        raise ValueError("Supply up to one lettered panel label per graph layer")
    panel_case = profile["rules"]["panel_case"]
    applied, needs_review = {}, []

    def write_num(obj, prop, expected, key, tolerance=0.02):
        try:
            obj.set_float(prop, expected)
            readback = float(obj.get_float(prop))
            if not math.isclose(readback, expected, abs_tol=tolerance):
                raise ValueError("read back %s, expected %s" % (readback, expected))
            applied[key] = readback
            return readback
        except Exception as exc:
            needs_review.append("%s: %s" % (key, exc))
        return None

    # Page resolution is the Origin page printer resolution, distinct from export DPI.
    try:
        ox = _positive(graph.get_float("width"), "page.width")
        oy = _positive(graph.get_float("height"), "page.height")
        resx = _positive(graph.get_float("resx"), "page.resx")
        resy = _positive(graph.get_float("resy"), "page.resy")
        dots = round(requested["width_mm"] * resx / 25.4)
        write_num(graph, "width", dots, "page.width_dots", 1)
        write_num(graph, "height", round(oy * dots / ox), "page.height_dots", 1)
        final_width = _positive(graph.get_float("width"), "page.width")
        final_height = _positive(graph.get_float("height"), "page.height")
        applied["width_mm"] = final_width * 25.4 / resx
        applied["height_mm"] = final_height * 25.4 / resy
    except Exception as exc:
        needs_review.append("page dimensions: %s" % exc)
    try:
        # All distributed profiles currently select Arial; the expression is fixed.
        font_id = _positive(op.lt_int("font(Arial)"), "font(Arial)")
    except Exception as exc:
        needs_review.append("font lookup: %s" % exc)
        font_id = None

    for i, layer in enumerate(graph):
        prefix = "layer%d." % (i + 1)
        for axis in ("x", "y"):
            field = axis + ".label.pt"
            write_num(layer, field, requested["font_pt"], prefix + field)
            if font_id is not None:
                field = axis + ".label.font"
                write_num(layer, field, font_id, prefix + field)
            field = axis + ".thickness"
            write_num(layer, field, requested["stroke_pt"], prefix + field)
        for name in ("XB", "YL", "XT", "YR", "Legend", "Title"):
            obj = layer.label(name)
            if obj is None:
                continue
            if font_id is not None:
                write_num(obj, "font", font_id, prefix + name + ".font")
            write_num(obj, "fsize", requested["font_pt"], prefix + name + ".fsize")
        for j, _ in enumerate(layer.plot_list(), 1):
            field = "plot%d.line.width" % j
            # Unsupported plot types may report no line property (e.g. point-only plots).
            try:
                existing = layer.get_float(field)
                if not isinstance(existing, (int, float)) or not math.isfinite(existing) or existing <= 0:
                    continue
            except Exception:
                continue
            write_num(layer, field, requested["stroke_pt"], prefix + field)
        panel = layer.label("OriginPlotPanel")
        letter = labels[i] if i < len(labels) else None
        if letter is None and panel is not None:
            match = re.fullmatch(r"(?:\\b\(([a-zA-Z]+)\)|([a-zA-Z]+))", panel.text)
            if match:
                letter = match.group(1) or match.group(2)
            else:
                needs_review.append(prefix + "panel: existing label text could not be decoded")
        if letter is not None:
            key = prefix + "panel"
            try:
                # A stable object name makes retries idempotent. Avoid duplicating a user's labels
                # by creating our own only when the caller requests them.
                letter = str(letter)
                if panel_case == "lower":
                    letter = letter.lower()
                elif panel_case == "upper":
                    letter = letter.upper()
                obj = panel
                if obj is None:
                    xlo, xhi = layer.get_float("x.from"), layer.get_float("x.to")
                    ylo, yhi = layer.get_float("y.from"), layer.get_float("y.to")
                    obj = layer.add_label(letter, xlo + (xhi-xlo)*0.02, yhi - (yhi-ylo)*0.02)
                    obj.name = "OriginPlotPanel"
                styled = r"\b(" + letter + ")" if requested["panel_bold"] else letter
                obj.text = styled
                if obj.text != styled:
                    raise ValueError("panel text did not read back")
                applied[key + ".text"] = obj.text
                applied[key + ".letter"] = letter
                applied[key + ".bold"] = obj.text == r"\b(" + letter + ")"
                if font_id is not None:
                    write_num(obj, "font", font_id, key + ".font")
                write_num(obj, "fsize", requested["panel_font_pt"], key + ".fsize")
            except Exception as exc:
                needs_review.append("%s: %s" % (key, exc))
    return {"journal": profile["id"], "requested": requested, "applied": applied,
            "font_lookup": {str(int(font_id)): "Arial"} if font_id is not None else {},
            "needs_review": needs_review}
