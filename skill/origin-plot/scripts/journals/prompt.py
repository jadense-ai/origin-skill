"""Turn the local publisher profile into instructions for one target journal."""

from . import load_profile


def _limits(pair, unit):
    low, high = pair
    if low is None:
        return f"至多 {high:g} {unit}"
    if high is None:
        return f"至少 {low:g} {unit}"
    return f"{low:g}–{high:g} {unit}"


def _geometry(r):
    column_names = {"single": "单栏", "intermediate": "中间栏宽", "double": "双栏"}
    if r["width_policy"] == "typesetting_targets":
        widths = "、".join(f"{v:g}" for v in r["width_targets_mm"])
        msg = f"按稿件选常用排版目标 {widths} mm"
        if "intermediate_range_mm" in r:
            msg += "，中间栏宽 " + _limits(r["intermediate_range_mm"], "mm")
    elif r["width_policy"] == "column_maxima":
        widths = "、".join(f"{column_names[k]} {v:g} mm" for k, v in r["width_by_column_max_mm"].items())
        msg = "按选定栏位核对宽度上限，" + widths
    else:
        msg = "成图宽度须在 " + _limits(r["width_range_mm"], "mm") + " 内"
    if "height_max_mm" in r:
        msg += f"，高度至多 {r['height_max_mm']:g} mm"
    return msg + "。"


def journal_prompt(name):
    profile = load_profile(name)
    r, d = profile["rules"], profile["defaults"]
    text = [f"为 {profile['title']} 制作 Origin 图。配置适用于{profile['stage']}，"
            f"来源核对日期 {profile['checked']}。先核对稿件阶段、栏位、多面板与图像类型。"]
    text.append("可从项目绘图默认值开始：" +
                f"宽 {d['width_mm']:g} mm，{d['font_family']} {d['font_pt']:g} pt，"
                f"线宽 {d['stroke_pt']:g} pt，优先导出 {d['output_format']}。"
                "根据图件内容和下列期刊条件调整。")
    fonts = "、".join(r["fonts"])
    family = "优先选用" if r["font_policy"] == "preferred" else "使用"
    size = "建议约 " if r.get("font_size_policy") == "approximate" else "控制在 "
    style = f"{family} {fonts}，最终印刷尺寸下普通标注字号{size}{_limits(r['font_range_pt'], 'pt')}。"
    if "stroke_range_pt" in r:
        style += "有线条时核对线宽：" + _limits(r["stroke_range_pt"], "pt") + "。"
    case = {"upper": "大写字母", "lower": "小写字母", "either": "大写或小写字母"}[r["panel_case"]]
    style += f"多面板用{case}"
    if "panel_font_pt" in r:
        style += f"、{r['panel_font_pt']:g} pt"
    if r.get("panel_bold"):
        style += "、加粗"
    if r.get("panel_italic") is False:
        style += "、正体"
    text += [_geometry(r), style + "。"]
    formats = "、".join(r.get("vector_formats", r["formats"]))
    if r["format_policy"] == "only":
        text.append("主图可用格式：" + formats + "。")
    elif r["format_policy"] == "by_artwork":
        text.append("按素材选择输出格式；矢量图按下列格式与后文条件核对：" + formats + "。")
    else:
        text.append("按编辑部所列主图类型核对格式：" + formats + "。")
    if r.get("editable_vector_text") or r.get("embedded_vector_fonts"):
        conditions = []
        if r.get("editable_vector_text"):
            conditions.append("文字可编辑")
        if r.get("embedded_vector_fonts"):
            conditions.append("字体已嵌入")
        text.append("有矢量文字时核对" + "、".join(conditions) + "。")
    image_types = {"default": "一般栅格素材", "photo": "照片", "color": "彩色图像",
                   "grayscale": "灰度图", "line_art": "线稿", "black_white": "黑白图"}
    densities = "，".join(f"{image_types[k]}{_limits(bounds, 'dpi')}" for k, bounds in r["raster_dpi"].items())
    if densities:
        text.append("按最终放置尺寸核对有效分辨率，" + densities + "。")
    color_rule = {"preferred": "优先使用", "required": "使用", "full_color": "彩色图使用"}[r["color_policy"]]
    colors = f"{color_rule} {'、'.join(r['color_modes'])}"
    if "rgb_bits_per_channel" in r:
        colors += f"，RGB 每通道 {r['rgb_bits_per_channel']} 位"
    if "file_bytes_max" in r:
        colors += f"，单文件至多 {r['file_bytes_max']:,} 字节"
    text.append(colors + "。")
    text.extend(profile["notes"])
    text.append("交付可编辑 OPJU 和目标格式图件。用成品和 Origin 读回数据运行 "
                f"python -m journals check {profile['id']} figure.json，并在最终尺寸下查看实际导出。"
                "有缺失或需人工确认的项目时，逐项列出。")
    text.append("来源：" + "；".join(f"{src['title']} {src['url']}" for src in profile["sources"]))
    return "\n".join(text)
