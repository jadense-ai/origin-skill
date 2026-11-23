"""Load publisher profiles, apply an Origin style, and check measured figure metadata."""

import json
import math
from pathlib import Path
import re

from .native import apply_journal_style
from .export import check_export


PROFILES = Path(__file__).resolve().parents[2] / "references" / "journals"
NAMES = ("nature", "science", "cell", "plos-one")


def load_profile(name):
    key = str(name).lower().strip().replace("_", "-").replace(" ", "-")
    if key in ("plos", "plosone"):
        key = "plos-one"
    if key not in NAMES:
        raise ValueError("Unknown main journal. Choose " + ", ".join(NAMES))
    return json.loads((PROFILES / (key + ".json")).read_text(encoding="utf-8"))


def validate_figure(name, metadata):
    """Check only submitted measurements. Unmeasured applicable properties need review."""
    p = load_profile(name)
    r = p["rules"]
    errors, warnings, missing = [], [], []

    def value(key):
        result = metadata.get(key)
        if result is None or result == "":
            if key not in missing:
                missing.append(key)
            return None
        return result

    def numeric(key, bounds=(None, None), approximate=False):
        raw = value(key)
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw <= 0:
            errors.append(f"{key}: 需要实测的有限正数")
            return None
        low, high = bounds
        if (low is not None and raw < low) or (high is not None and raw > high):
            (warnings if approximate else errors).append(f"{key}: {raw} 超出 {bounds}")
        return raw

    def require_bool(key, wanted):
        seen = value(key)
        if seen is not None and (type(seen) is not bool or seen != wanted):
            errors.append(f"{key}: 要求 {wanted!r}，实际 {seen!r}")

    def allowed(key, choices, preferred=False):
        seen = value(key)
        if seen is not None and str(seen).upper() not in {str(x).upper() for x in choices}:
            (warnings if preferred else errors).append(f"{key}: {seen} 不在 {choices} 中")
        return seen

    fmt = value("output_format")
    fmt = str(fmt or "").upper().lstrip(".")
    fmt = {"TIF": "TIFF", "JPG": "JPEG"}.get(fmt, fmt)
    kind = value("image_kind")
    kinds = {"vector", "color", "grayscale", "black_white", "line_art", "photo", "mixed"}
    if kind is not None and kind not in kinds:
        errors.append("image_kind: 无法识别图像类型")
    if fmt and fmt not in r["formats"]:
        hard = r["format_policy"] == "only" or fmt in r.get("formats_rejected", [])
        (errors if hard else warnings).append(f"output_format: {fmt} 未列作此类终稿格式")
    vector_container = fmt in ("AI", "EPS", "PDF", "SVG", "PS", "PSD", "XLS", "XLSX")
    if kind == "vector" and fmt in ("TIFF", "JPEG", "GIF", "PNG"):
        errors.append("image_kind: 位图文件不能标为纯矢量")
    if p["id"] == "science":
        if kind in ("vector", "mixed") and fmt and fmt not in r["vector_formats"]:
            errors.append("output_format: Science 图表与混合主图使用可编辑矢量格式")
        if fmt == "SVG" and str(metadata.get("creator", "")).casefold() != "r":
            warnings.append("output_format: Science 对 R 绘图明确列出 SVG，其他矢量图优先 AI、EPS 或 PDF")
    if p["id"] == "cell" and metadata.get("cell_current_rules_confirmed") is not True:
        warnings.append("Cell 的数值规范来自出版社网页存档，请在当前作者门户复核")
    width = numeric("width_mm", r.get("width_range_mm", (None, None)))
    if r["width_policy"] == "typesetting_targets" and width is not None:
        intermediate = r.get("intermediate_range_mm", ())
        in_between = intermediate and intermediate[0] <= width <= intermediate[1]
        if not in_between and not any(abs(width - w) <= 0.2 for w in r["width_targets_mm"]):
            warnings.append(f"width_mm: {width}，常见排版栏宽为 {r['width_targets_mm']}")
    if r["width_policy"] == "column_maxima":
        maxima = r["width_by_column_max_mm"]
        column = allowed("column", list(maxima))
        limit = maxima.get(str(column).lower(), max(maxima.values()))
        if width is not None and width > limit:
            errors.append(f"width_mm: {width}，该栏位上限为 {limit}")
    if "height_max_mm" in r:
        numeric("height_mm", (None, r["height_max_mm"]))
    allowed("font_family", r["fonts"], preferred=r["font_policy"] == "preferred")
    numeric("font_pt", r["font_range_pt"], approximate=r.get("font_size_policy") == "approximate")
    if "stroke_range_pt" in r and metadata.get("has_strokes", True):
        numeric("stroke_pt", r["stroke_range_pt"])
    panel_count = numeric("panel_count")
    if panel_count is not None and not float(panel_count).is_integer():
        errors.append("panel_count: 需要整数")
    if metadata.get("panel_label") is not None or (panel_count or 0) > 1:
        labels = value("panel_label")
        if labels is not None:
            labels = labels if isinstance(labels, (list, tuple)) else [labels]
            pattern = {"lower": "[a-z]+", "upper": "[A-Z]+", "either": "[A-Za-z]+"}[r["panel_case"]]
            if not labels or any(not re.fullmatch(pattern, str(s)) for s in labels):
                errors.append(f"panel_label: 需要 {r['panel_case']} 字母面板号")
            if panel_count is not None and panel_count > 1 and len(labels) != panel_count:
                warnings.append("panel_label: 尚未逐一核对所有面板号")
        if "panel_font_pt" in r:
            n = r["panel_font_pt"]
            numeric("panel_font_pt", (n, n))
        if "panel_bold" in r:
            require_bool("panel_bold", r["panel_bold"])
        if "panel_italic" in r:
            require_bool("panel_italic", r["panel_italic"])
    if vector_container and kind in ("vector", "mixed"):
        if r.get("editable_vector_text"):
            require_bool("editable_text", True)
        if r.get("embedded_vector_fonts"):
            require_bool("fonts_embedded", True)
    raster = (kind in kinds - {"vector"} or fmt in ("TIFF", "PNG", "JPEG", "GIF"))
    if raster:
        # In a mixed page the weakest raster element determines its effective DPI.
        raster_kind = value("raster_kind") if kind == "mixed" and "default" not in r["raster_dpi"] else kind
        bounds = r["raster_dpi"].get(raster_kind, r["raster_dpi"].get("default"))
        if bounds:
            numeric("dpi", bounds)
        elif raster_kind:
            warnings.append(f"dpi: 需确认 {raster_kind} 的原始有效分辨率")
    color = value("color_mode")
    if color is not None:
        modes = r["color_modes"]
        bw = str(color).upper() in ("GRAYSCALE", "BLACK_WHITE", "MONOCHROME", "1")
        if not (bw and r["color_policy"] in ("full_color", "preferred")):
            allowed("color_mode", modes, preferred=r["color_policy"] == "preferred")
        if str(color).upper() == "RGB" and "rgb_bits_per_channel" in r:
            bit = r["rgb_bits_per_channel"]
            numeric("bits_per_channel", (bit, bit))
    if r.get("single_page"):
        require_bool("single_page", True)
    if "file_bytes_max" in r:
        numeric("file_bytes", (None, r["file_bytes_max"]))
    if fmt == "TIFF" and "tiff" in r:
        allowed("compression", [r["tiff"]["compression"]])
        for key in ("has_alpha", "flattened"):
            require_bool(key, r["tiff"][key])
    if fmt == "EPS" and r.get("eps_fonts_safe"):
        require_bool("eps_fonts_safe", True)
    return {"journal": p["id"], "stage": p["stage"],
            "status": "fail" if errors else "review" if warnings or missing else "pass",
            "errors": errors, "warnings": warnings, "missing": missing}
