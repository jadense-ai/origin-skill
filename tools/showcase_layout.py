"""Compose the Origin showcase poster from the verified exports."""

from io import BytesIO
from math import cos, radians, sin
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


POSTER_WIDTH = 4096
POSTER_HEIGHT = POSTER_WIDTH * 3 // 4
MARGIN = 48
GAP = 22
BACKGROUND = "#edf3f6"
FEATURED = ("shap-summary", "xps-components")
TILT = 7
ROWS = (
    ("histogram", "dual-y", "grouped-column", "scatter"),
    ("point-error", "heatmap", "box-raw", "xrd-stack"),
    ("eis-nyquist", *FEATURED, "multi-panel"),
    ("dose-response", "violin", "ecdf", "paired-sample"),
    ("multi-line", "coefficient-interval", "event-study", "likert"),
)
PERIMETER_PLOTS = {"point-error": "Estimates with error bars", "paired-sample": "Paired observations"}
VERIFY_ARCHIVE = Path(__file__).resolve().parents[1] / "dist" / "origin-plot-0.1.2-native-verification.zip"
LABELS = {
    "shap-summary": "SHAP 重要性与样本贡献",
    "xps-components": "XPS 分峰与残差",
    "heatmap": "高密度热图",
    "box-raw": "分组箱线与原始点",
    "xrd-stack": "XRD 堆叠图",
    "eis-nyquist": "EIS 阻抗图",
    "multi-panel": "双面板时序",
    "multi-line": "光谱分量",
    "dose-response": "剂量响应",
    "violin": "响应分布",
    "scatter": "分组散点",
    "ecdf": "经验累积分布",
    "coefficient-interval": "模型系数区间",
    "event-study": "事件研究",
    "grouped-column": "分组柱状图",
    "dual-y": "双 Y 轴时序",
    "histogram": "混合延迟分布",
    "likert": "李克特量表",
    "point-error": "点估计与误差棒",
    "paired-sample": "配对观测",
}


def _native_plot(path):
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
    paper = Image.new("RGB", rgba.size, "white")
    paper.paste(rgba, mask=rgba.getchannel("A"))
    ink = ImageChops.invert(paper).point(lambda value: 255 if value > 8 else 0)
    bounds = ink.getbbox()
    if bounds is None:
        raise ValueError(f"Blank Origin export: {path}")
    return paper.crop(bounds)


def _chinese_font():
    for filename in ("msyhbd.ttc", "Dengb.ttf"):
        try:
            return ImageFont.truetype(filename, 35)
        except OSError:
            continue
    return None


def _card(sheet, draw, bounds, recipe, tile, fonts, *, standalone=False):
    x, y, width, height = bounds
    title, path = tile
    chinese, english = fonts
    pad = 44 if standalone else 24
    draw.rounded_rectangle(
        (x, y, x + width - 1, y + height - 1), radius=22, fill="white",
        outline="#b3c9d6" if standalone else "#d7e2e8", width=2,
    )
    label_x, label_y = x + pad, y + pad + 1
    if chinese:
        label = LABELS[recipe]
        draw.text((label_x, label_y), label, font=chinese, fill="#153447", anchor="lt")
        label_x += round(draw.textlength(label, font=chinese)) + pad // 2
    draw.text((label_x, label_y + 2), title, font=english, fill="#4b6273", anchor="lt")

    plot_top = 140 if standalone else 76
    plot_height = height - plot_top - pad
    plot = ImageOps.contain(_native_plot(path), (width - 2 * pad, plot_height), Image.Resampling.LANCZOS)
    position = (x + (width - plot.width) // 2, y + plot_top + (plot_height - plot.height) // 2)
    sheet.paste(plot, position)


def _save_png(image, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def _draw_row(sheet, y, height, recipes, widths, plots, fonts, *, standalone=False):
    left = (sheet.width - sum(widths) - GAP * (len(recipes) - 1)) // 2
    draw = ImageDraw.Draw(sheet)
    for recipe, width in zip(recipes, widths, strict=True):
        _card(sheet, draw, (left, y, width, height), recipe, plots[recipe], fonts, standalone=standalone)
        left += width + GAP


def _soften_perimeter(sheet, focus_top, focus_bottom):
    # The middle two cards stay within the plane of focus as the other cards
    # fade toward the four sides of the poster.
    mask_width, mask_height = sheet.width // 20, sheet.height // 20
    mask = Image.new("L", (mask_width, mask_height))
    alpha = []
    for row in range(mask_height):
        y = sheet.height * row / (mask_height - 1)
        vertical = max((focus_top - y) / focus_top, (y - focus_bottom) / (sheet.height - focus_bottom), 0)
        for col in range(mask_width):
            horizontal = max(0, (abs(2 * col / (mask_width - 1) - 1) - 0.53) / 0.47)
            distance = 1 - (1 - vertical) * (1 - 0.64 * horizontal)
            alpha.append(round(248 * distance**2 * (3 - 2 * distance)))
    mask.putdata(alpha)
    mask = mask.resize(sheet.size, Image.Resampling.BICUBIC)
    blur = sheet.filter(ImageFilter.GaussianBlur(21))
    haze = Image.new("RGB", sheet.size, "#e4f1f7")
    soft = Image.blend(blur, haze, 0.19)
    return Image.composite(soft, sheet, mask)


def _tilted_view(sheet, cosine, sine, grid_width, grid_height):
    # The upright viewport is inscribed in the tilted grid. Its corners meet
    # the grid's top, right, bottom and left edges in clockwise order.
    sx = sheet.width / grid_width
    sy = sheet.height / grid_height
    return sheet.transform(
        (POSTER_WIDTH, POSTER_HEIGHT), Image.Transform.AFFINE,
        (cosine * sx, -sine * sx, POSTER_HEIGHT * sine * sx, sine * sy, cosine * sy, 0),
        resample=Image.Resampling.BICUBIC, fillcolor=BACKGROUND,
    )


def _featured_preview(plots, chinese, english):
    row_height = 1600
    sheet = Image.new("RGB", (POSTER_WIDTH, row_height + 2 * MARGIN), BACKGROUND)
    row_width = POSTER_WIDTH - 2 * MARGIN - GAP
    left_width = round(row_width * 0.54)
    fonts = (chinese and chinese.font_variant(size=56), english.font_variant(size=43))
    _draw_row(sheet, MARGIN, row_height, FEATURED, (left_width, row_width - left_width),
              plots, fonts, standalone=True)
    return sheet


def compose(tiles, output, *, featured_output=None):
    """Compose the tilted poster and optionally export the two featured plots upright."""
    tiles = list(tiles)
    plots = {Path(path).stem: (title, path) for title, path in tiles}
    expected = {recipe for recipes in ROWS for recipe in recipes} - PERIMETER_PLOTS.keys()
    if len(tiles) != len(expected) or set(plots) != expected:
        raise ValueError(f"The poster requires one native export for each of its {len(expected)} examples")
    with ZipFile(VERIFY_ARCHIVE) as archive:
        for recipe, title in PERIMETER_PLOTS.items():
            plots[recipe] = title, BytesIO(archive.read(f"recipes/{recipe}/rebound-B.png"))

    angle = radians(TILT)
    cosine, sine = cos(angle), sin(angle)
    grid_width = POSTER_WIDTH * cosine + POSTER_HEIGHT * sine
    grid_height = POSTER_WIDTH * sine + POSTER_HEIGHT * cosine
    columns = len(ROWS[0])
    card_width = round((grid_width - (columns - 1) * GAP) / columns)
    card_height = round((grid_height - (len(ROWS) - 1) * GAP) / len(ROWS))
    width = card_width * columns + GAP * (columns - 1)
    height = card_height * len(ROWS) + GAP * (len(ROWS) - 1)
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    chinese = _chinese_font()
    english = ImageFont.truetype("segoeui.ttf", 31)
    for row, recipes in enumerate(ROWS):
        top = row * (card_height + GAP)
        _draw_row(sheet, top, card_height, recipes, (card_width,) * columns, plots, (chinese, english))

    focus_top = (len(ROWS) // 2) * (card_height + GAP)
    scene = _soften_perimeter(sheet, focus_top, focus_top + card_height)
    _save_png(_tilted_view(scene, cosine, sine, grid_width, grid_height), output)
    if featured_output is not None:
        _save_png(_featured_preview(plots, chinese, english), featured_output)
