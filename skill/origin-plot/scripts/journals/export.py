"""Inspect final physical artwork. Never substitute an Origin page size for file dimensions."""

import math
from pathlib import Path
import re


def _raster(path):
    from PIL import Image

    with Image.open(path) as im:
        facts = {"output_format": im.format, "single_page": im.n_frames == 1}
        if im.mode in ("1", "L", "I", "I;16", "LA"):
            facts.update(color_mode="GRAYSCALE", image_kind="black_white" if im.mode == "1" else "grayscale")
        elif im.mode in ("RGB", "RGBA", "CMYK"):
            facts.update(color_mode="RGB" if im.mode.startswith("RGB") else "CMYK", image_kind="color")
        if im.format == "TIFF":
            tags = im.tag_v2
            # Pillow may synthesize a default DPI. Physical TIFF dimensions require actual tags.
            factor = {2: 1.0, 3: 2.54}.get(tags.get(296, 2))
            dpi = [float(tags[k]) * factor for k in (282, 283)] if factor and 282 in tags and 283 in tags else []
            bits = tags.get(258, (1,))
            bits = bits if isinstance(bits, tuple) else (bits,)
            if len(set(bits)) == 1:
                facts["bits_per_channel"] = int(bits[0])
            facts["compression"] = {1: "NONE", 5: "LZW", 8: "DEFLATE", 32773: "PACKBITS",
                                    32946: "DEFLATE"}.get(tags.get(259, 1), str(tags.get(259)))
            extra = tags.get(338, ())
            extra = extra if isinstance(extra, tuple) else (extra,)
            if 1 in extra or 2 in extra or "A" in im.getbands():
                facts["has_alpha"] = True
            elif not extra:
                facts["has_alpha"] = False
            # ImageSourceData may carry Photoshop layers. Presence alone does not prove they exist.
            if 37724 not in tags and im.n_frames == 1:
                facts["flattened"] = True
            elif 37724 in tags and any(k in bytes(tags[37724]) for k in (b"Layr", b"Lr16", b"Lr32")):
                facts["flattened"] = False
        else:
            dpi = im.info.get("dpi") or []
            facts["has_alpha"] = "A" in im.getbands() or "transparency" in im.info
        if len(dpi) == 2 and all(math.isfinite(float(n)) and n > 0 for n in dpi):
            facts["dpi_axes"] = list(dpi)
            facts["dpi"] = min(dpi)
            facts["width_mm"] = im.width / dpi[0] * 25.4
            facts["height_mm"] = im.height / dpi[1] * 25.4
        facts["pixels"] = [im.width, im.height]
        im.load()  # report truncated or unreadable compressed image data
        return facts


def _multiply(m, n):
    # PDF affine linear component, row-vector convention. Translation cannot change size.
    a,b,c,d = m
    e,f,g,h = n
    return (a*e+b*g, a*f+b*h, c*e+d*g, c*f+d*h)


def _font_info(resources, key):
    obj = resources["/Font"].get_object()[key].get_object()
    name = str(obj.get("/BaseFont", "")).lstrip("/")
    if re.match(r"^[A-Z]{6}\+", name):
        name = name[7:]
    fonts = [x.get_object() for x in obj["/DescendantFonts"]] if "/DescendantFonts" in obj else [obj]
    descriptors = [(x.get("/FontDescriptor") or {}).get_object() if x.get("/FontDescriptor") else {} for x in fonts]
    embedded = all(any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")) for desc in descriptors)
    return {"name": name, "embedded": embedded, "type3": obj.get("/Subtype") == "/Type3"}


def _text_label(token):
    if isinstance(token, bytes):
        return ""
    return str(token).strip()


def _pdf(path):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream

    reader = PdfReader(str(path), strict=True)
    page = reader.pages[0]
    unit = float(page.get("/UserUnit", 1))
    # CropBox defaults to MediaBox. Clip to the actual PDF medium's visible area.
    box, media = page.cropbox, page.mediabox
    w = min(box.right, media.right) - max(box.left, media.left)
    h = min(box.top, media.top) - max(box.bottom, media.bottom)
    if page.rotation % 180:
        w, h = h, w
    facts = {"output_format": "PDF", "single_page": len(reader.pages) == 1,
             "width_mm": float(w) * unit * 25.4/72, "height_mm": float(h) * unit * 25.4/72}
    spans, lines, placements, warnings = [], [], [], set()
    colors = set()
    mark_count = 0
    identity = (1.,0.,0.,1.)

    def walk(stream, resources, state, trail):
        nonlocal mark_count
        stack = []
        tm = identity
        for args, operator in ContentStream(stream, reader).operations:
            if operator == b"q":
                stack.append(state.copy())
            elif operator == b"Q":
                if stack:
                    state = stack.pop()
            elif operator == b"cm":
                state["ctm"] = _multiply(tuple(map(float, args[:4])), state["ctm"])
            elif operator in (b"rg", b"RG", b"g", b"G", b"k", b"K", b"cs", b"CS"):
                color = {b"rg":"RGB", b"RG":"RGB", b"g":"GRAYSCALE", b"G":"GRAYSCALE",
                         b"k":"CMYK", b"K":"CMYK"}.get(operator)
                if color is None:
                    color = {"/DeviceRGB":"RGB","/DeviceGray":"GRAYSCALE","/DeviceCMYK":"CMYK"}.get(str(args[0]), "UNKNOWN")
                state["color_stroke" if operator.isupper() else "color_fill"] = color
            elif operator == b"w":
                state["line_width"] = float(args[0])
            elif operator in (b"S", b"s", b"B", b"B*", b"b", b"b*"):
                mark_count += 1
                colors.add(state["color_stroke"])
                if operator not in (b"S", b"s"):
                    colors.add(state["color_fill"])
                a,b,c,d = state["ctm"]
                # Anisotropic/sheared strokes have two extreme normal scales.
                tr = a*a+b*b+c*c+d*d
                discr = math.sqrt(max(0., tr*tr-4*(a*d-b*c)**2))
                lines.extend(state["line_width"] * unit * math.sqrt(max(0., (tr+s*discr)/2)) for s in (-1,1))
            elif operator in (b"f", b"f*", b"F", b"sh"):
                mark_count += 1
                colors.add(state["color_fill"])
            elif operator == b"BT":
                tm = identity
            elif operator == b"Tm":
                tm = tuple(map(float, args[:4]))
            elif operator == b"Tf":
                state["font"], state["font_size"] = _font_info(resources, args[0]), float(args[1])
            elif operator == b"Tr":
                state["text_render"] = int(args[0])
            elif operator in (b"Tj", b"TJ", b"'", b'"') and state["text_render"] not in (3,7):
                parts = args[-1] if operator == b"TJ" else [args[-1]]
                label = "".join(_text_label(x) for x in parts if isinstance(x, (str, bytes)))
                if not any(len(x) for x in parts if isinstance(x, (str, bytes))):
                    continue
                mark_count += 1
                colors.add(state["color_fill"])
                combined = _multiply(tm, state["ctm"])
                size = abs(state["font_size"]) * math.hypot(*combined[2:]) * unit
                spans.append({**state["font"], "size": size, "text": label})
            elif operator in (b"Do", b"INLINE IMAGE"):
                if operator == b"INLINE IMAGE":
                    image = args["settings"]
                else:
                    ref = resources["/XObject"].get_object()[args[0]]
                    image = ref.get_object()
                    if image.get("/Subtype") == "/Form":
                        marker = id(image)
                        if marker in trail or len(trail) > 24:
                            warnings.add("嵌套表单无法完整检查")
                            continue
                        nested = state.copy()
                        nested["ctm"] = _multiply(tuple(map(float, image.get("/Matrix", identity)[:4])), state["ctm"])
                        res = image["/Resources"].get_object() if "/Resources" in image else resources
                        walk(image, res, nested, trail | {marker})
                        continue
                a,b,c,d = state["ctm"]
                image_w = int(image.get("/Width") or image.get("/W") or 0)
                image_h = int(image.get("/Height") or image.get("/H") or 0)
                xdim, ydim = math.hypot(a,b)*unit, math.hypot(c,d)*unit
                if image_w and image_h and xdim > 0 and ydim > 0:
                    placements.extend([72*image_w/xdim, 72*image_h/ydim])
                space = str(image.get("/ColorSpace", image.get("/CS", "")))
                colors.add({"/DeviceRGB":"RGB","/RGB":"RGB","/DeviceGray":"GRAYSCALE","/G":"GRAYSCALE",
                            "/DeviceCMYK":"CMYK","/CMYK":"CMYK"}.get(space, "UNKNOWN"))
            elif operator == b"gs":
                # An external graphics state may contain line width, transforms of text via fonts, masks etc.
                ext = resources["/ExtGState"].get_object()[args[0]].get_object()
                if "/LW" in ext:
                    state["line_width"] = float(ext["/LW"])
                if "/Font" in ext or ("/SMask" in ext and str(ext["/SMask"]) != "/None"):
                    warnings.add("外部图形状态含字体或蒙版，需人工核对")

    resources = page["/Resources"].get_object() if "/Resources" in page else {}
    state = {"ctm": identity, "font": {}, "font_size": 0, "text_render": 0,
             "line_width": 1.0, "color_stroke":"GRAYSCALE", "color_fill":"GRAYSCALE"}
    if page.get_contents() is not None:
        try:
            walk(page.get_contents(), resources, state, set())
        except (KeyError, AttributeError, TypeError, ValueError, IndexError, ArithmeticError) as error:
            warnings.add("PDF 指令流有未识别的属性：" + str(error))
    if "UNKNOWN" not in colors and colors:
        facts["color_mode"] = "CMYK" if "CMYK" in colors else "RGB" if "RGB" in colors else "GRAYSCALE"
    if placements:
        facts.update(image_kind="mixed" if mark_count else "color", dpi=min(placements), dpi_axes=placements)
    elif mark_count and not warnings:
        facts["image_kind"] = "vector"
    if spans:
        facts["fonts_embedded"] = all(s.get("embedded") is True for s in spans)
        # Live text operators alone cannot establish that all labels remain editable.
        facts["has_live_text"] = any(not s.get("type3") for s in spans)
    elif not warnings:
        facts["has_live_text"] = False
    facts["text_spans"], facts["stroke_pts"] = spans, sorted(set(round(v, 5) for v in lines))
    facts["inspection_notes"] = sorted(warnings)
    return facts


def _family(pdfname):
    """Normalize common PostScript face names while preserving distinct font families."""
    s = pdfname.strip().lstrip("/")
    s = re.sub(r"[-,](?:BoldItalic|BoldOblique|Bold|Italic|Oblique|Regular|Roman)(?:MT|PSMT)?$", "", s, flags=re.I)
    s = re.sub(r"(?:PSMT|MT)$", "", s, flags=re.I)
    return {"timesnewroman":"Times New Roman", "times":"Times", "arial":"Arial", "helvetica":"Helvetica",
            "symbol":"Symbol"}.get(s.replace(" ", "").casefold(), s)


def check_export(journal, path, graph_result):
    """Inspect one generated file, check all observed sizes, and return attributable measurements."""
    from . import load_profile, validate_figure

    path = Path(path)
    profile = load_profile(journal)
    style = graph_result.get("journal_style") or {}
    ap = style.get("applied") or {}
    recipe = graph_result.get("recipe_id")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        facts = _pdf(path)
    elif suffix in (".png",".jpg",".jpeg",".tif",".tiff",".bmp"):
        facts = _raster(path)
    else:
        facts = {"output_format": suffix[1:].upper()}
    facts["file_bytes"] = path.stat().st_size
    notes = facts.get("inspection_notes", []).copy()
    if facts.get("single_page") is False:
        notes.append("导出有多页，第一页的元数据不能代表其余页面。")
    numbered_labels = []
    for key, val in ap.items():
        match = re.fullmatch(r"layer(\d+)\.panel\.letter", key)
        if match:
            numbered_labels.append((int(match[1]), str(val)))
    labels = [label for _, label in sorted(numbered_labels)]
    expected = len((graph_result.get("layers") or [])) if recipe == "multi-panel" else None
    if expected:
        facts["panel_count"] = expected
    elif labels:
        facts["panel_count"] = len(labels)
        if len(labels) != len(graph_result.get("layers") or []):
            notes.append("已识别的面板数与图层数不同，需确认页面布局。")
    elif recipe:
        facts["panel_count"] = 1
    if labels:
        facts["panel_label"] = labels
    native_font_sizes = [float(v) for k,v in ap.items()
                         if k.endswith((".label.pt", ".fsize")) and ".panel." not in k]
    native_strokes = [float(v) for k,v in ap.items() if k.endswith((".line.width",".thickness"))]
    native_fonts = [style.get("font_lookup", {}).get(str(int(v))) for k,v in ap.items() if k.endswith(".font")]
    native_fonts = [n for n in native_fonts if n]
    native_panel_sizes = [float(v) for k,v in ap.items() if k.endswith(".panel.fsize")]
    native_panel_bold = [v for k,v in ap.items() if k.endswith(".panel.bold")]

    spans = facts.pop("text_spans", [])
    families = sorted({_family(s["name"]) for s in spans if s.get("name")})
    regular, panels = [], []
    for span in spans:
        if span.get("text") in labels and span.get("text"):
            panels.append(span)
        else:
            regular.append(span)
    font_sizes = sorted({round(s["size"], 4) for s in regular})
    panel_sizes = sorted({round(s["size"], 4) for s in panels})
    page_strokes = facts.get("stroke_pts", [])
    if spans:
        if labels and set(labels) != {s["text"] for s in panels}:
            notes.append("导出文本中未能逐一识别全部面板号。")
        if any(not s.get("text") or s.get("type3") for s in spans):
            notes.append("有字体编码或 Type 3 字形需要人工检查。")
    if suffix == ".pdf" and facts.get("has_live_text") is False:
        facts["editable_text"] = False
        if profile["rules"].get("editable_vector_text") and graph_result.get("layers"):
            notes.append("导出 PDF 未检出可编辑科研标注。")
    file_dimensions = facts.get("width_mm"), facts.get("height_mm")
    native_dimensions = ap.get("width_mm"), ap.get("height_mm")
    scale = None
    if all(isinstance(n, (int,float)) and n > 0 for n in (*file_dimensions, *native_dimensions)):
        sx, sy = [actual / model for actual, model in zip(file_dimensions, native_dimensions)]
        if math.isclose(sx, sy, rel_tol=0.015, abs_tol=0.005):
            scale = (sx+sy)/2
        else:
            notes.append("导出图的长宽比与 Origin 图页不同，须在成品上核对字体与线宽。")
    if style.get("needs_review"):
        notes.extend("Origin 对象待核：" + item for item in style["needs_review"])
    # Rendered pixels do not independently encode font families or text sizes. Native
    # measurements are useful in a side-by-side comparison but not a file-level pass.
    if suffix != ".pdf" and (native_font_sizes or native_strokes):
        notes.append("成品中的字形和线宽须目视复核，Origin 对象读回另列。")
    is_raster = suffix in (".tif",".tiff",".png",".jpg",".jpeg",".bmp")
    # For Cell, a TIFF's pixel mode cannot by itself distinguish a line-art chart
    # from a photograph. These original recipes draw only native curves and shapes.
    line_recipes = {"scatter", "multi-line", "point-error", "dual-y", "multi-panel",
                    "box-raw", "histogram", "paired-sample", "coefficient-interval",
                    "ecdf", "xrd-stack", "eis-nyquist", "event-study", "dose-response",
                    "grouped-column", "percent-stack", "corpus-frequency", "likert", "violin"}
    if is_raster and profile["id"] == "cell":
        if recipe in line_recipes:
            facts["image_kind"] = "line_art"
        else:
            notes.append("TIFF 的像素色彩模式不能确定是否属线稿，请复核 Cell 的线稿分辨率。")
    if profile["id"] == "cell" and not profile["rules"].get("width_range_mm"):
        # Column intent cannot be inferred just from the width of the exported artwork.
        if facts.get("width_mm", 0) > 174:
            notes.append("成品宽度超过存档指南中的最大双栏宽度。")

    if font_sizes:
        facts["font_pt"] = font_sizes[0]
    if families:
        facts["font_family"] = families[0]
    if panel_sizes:
        facts["panel_font_pt"] = panel_sizes[0]
    if panels:
        facts["panel_bold"] = all("bold" in s.get("name","").lower() for s in panels)
        facts["panel_italic"] = any(re.search("italic|oblique", s.get("name", ""), re.I) for s in panels)
    if page_strokes:
        facts["stroke_pt"] = min(page_strokes)
    base = validate_figure(journal, facts)
    for key, vals in (("font_pt", font_sizes), ("font_family", families), ("stroke_pt", page_strokes),
                      ("panel_font_pt", panel_sizes), ("dpi", facts.get("dpi_axes", []))):
        for actual in set(vals):
            comparison = validate_figure(journal, {**facts, key: actual})
            for error_group in ("errors", "warnings"):
                base[error_group].extend(x for x in comparison[error_group] if x not in base[error_group])
    for key, vals in (("font_pt", native_font_sizes), ("stroke_pt", native_strokes),
                      ("panel_font_pt", native_panel_sizes), ("font_family", native_fonts)):
        for actual in set(vals):
            if key != "font_family":
                if scale is None:
                    continue
                actual *= scale
            comparison = validate_figure(journal, {**facts, key: actual})
            for detail in comparison["errors"] + comparison["warnings"]:
                warning = "按原生样式与成品比例推算需复核：" + detail
                if detail.startswith(key + ":") and warning not in notes:
                    notes.append(warning)
    if profile["rules"].get("editable_vector_text") and suffix == ".pdf" and facts.get("has_live_text") is False and graph_result.get("layers"):
        base["errors"].append("editable_text: 原生图有科研标注，但导出文件没有可编辑的文字。")
    if profile["id"] == "science" and is_raster and recipe:
        base["errors"].append("output_format: 此科研配方生成图表，Science 要求可编辑的矢量终稿。")
    base["warnings"].extend(x for x in notes if x not in base["warnings"])
    base["status"] = "fail" if base["errors"] else "review" if base["warnings"] or base["missing"] else "pass"
    base["file_measurements"] = {**facts, "observed_font_families": families, "observed_font_pt": font_sizes,
                                 "observed_panel_font_pt": panel_sizes}
    base["native_measurements"] = {"font_families": sorted(set(native_fonts)), "font_pt": sorted(set(native_font_sizes)),
                                   "stroke_pt": sorted(set(native_strokes)), "panel_font_pt": sorted(set(native_panel_sizes)),
                                   "panel_bold": native_panel_bold, "page_width_mm": native_dimensions[0],
                                   "page_height_mm": native_dimensions[1], "uniform_export_scale": scale}
    base["evidence_sources"] = {k: "exported_file" for k in facts}
    if "panel_count" in facts:
        base["evidence_sources"]["panel_count"] = "recipe_or_native_panel_objects"
    if "panel_label" in facts:
        base["evidence_sources"]["panel_label"] = "native_panel_objects"
    if is_raster and profile["id"] == "cell" and recipe in line_recipes:
        base["evidence_sources"]["image_kind"] = "native_recipe_artwork_type"
    return base
