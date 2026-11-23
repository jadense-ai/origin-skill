# 期刊终稿图配置

按目标刊名加载 JSON。每份配置记录核验日、适用阶段、规则来源、排版默认值和人工复核事项。`defaults` 给出本工具在允许范围内选择的起点；`rules` 保存用于核对图件的条件。适用对象是包含科研图表的主文图。初稿、Extended Data、补充图与图形摘要应查看各自的说明。

| 主刊 | 成品宽度 | 普通标注 | 面板号 | 常用终稿导出 |
|---|---|---|---|---|
| [Nature](nature.json) | 89 / 183 mm；中间宽度 120–136 mm | 5–7 pt，偏好无衬线 | 小写、正体、加粗、8 pt | 可编辑 PDF、AI 或 EPS |
| [Science](science.json) | 90 / 183 mm | 6–9 pt，偏好无衬线 | 大写、加粗、10 pt | 可编辑 AI、EPS 或 PDF |
| [Cell](cell.json) | 1、1.5、2 栏分别最大 85、114、174 mm | Arial，约 6–8 pt | 大写 | 单页 PDF 或 TIFF |
| [PLOS One](plos-one.json) | 66.8–190.5 mm；132 mm 适合正文栏 | Arial、Times 或 Symbol，8–12 pt | 可按图注用大写或小写 | 单页 LZW TIFF 或 EPS |

Nature 的制图网页给出 170 mm 图高，终稿说明的 247 mm 为全页深度。Science 的 300–500 dpi 对应摄影图片，在矢量绘图中嵌入的光栅图像至少 300 ppi。PLOS One 在 provisional Editorial Accept 后执行主图格式要求。Cell 的主图格式从终稿 PDF 直接核实，栏宽、字体和线宽等来自同一 PDF 引用的出版社制图指南存档。投稿时复核当前 Cell 作者门户。完整链接在各 JSON 的 `sources`。

## 加载与核验

从本 Skill 的 `scripts` 目录运行 `python -m journals show science` 或 `python -m journals check science path/to/measurements.json`。Python 可导入 `load_profile(name)`、`apply_journal_style(op, graph, journal, ...)` 和 `validate_figure(name, metadata)`。

`check` 只接受实测字段。主图宽高单位为 mm，字号和线宽单位为 pt，混合图的 dpi 为其中对应位图元素在最终尺寸下的有效分辨率。纯矢量图设置 `image_kind="vector"`。混合用 `mixed`，Cell 再按嵌入图像给出 `raster_kind`，选 `color`、`grayscale`、`black_white` 或 `line_art`。单独摄影图片用 `photo`。逐一核查了所有字体、字号、线宽后再向函数提交代表值。存在多个规格时分别校验边界值。

示例为一组假设的实测数据，供识别字段和单位。终稿生产中由实际文件及 Origin 图对象提供数值。

```json
{
  "output_format": "PDF", "image_kind": "vector", "color_mode": "RGB",
  "width_mm": 90, "height_mm": 65, "font_family": "Arial", "font_pt": 8,
  "stroke_pt": 0.6, "panel_count": 2, "panel_label": ["A", "B"],
  "panel_font_pt": 10, "panel_bold": true, "editable_text": true
}
```

返回的 `errors` 列出超限值，`warnings` 列出建议或来源需确认的项目，`missing` 列出适用但缺少的实测值。退出码分别为 0（已覆盖规则通过）、1（有待核字段或建议）、2（存在错误）。来源不一致或尚未审阅的规则保留人工复核。即使所有数值通过，仍须目视核对内容、排布、误差定义、颜色可辨性与导出对象的编辑能力。

后端调用 `check_export(journal, path, graph_result)` 直接测量本次成品。PDF 按可见页面、旋转角度和 UserUnit 换算毫米，检查有实际绘制操作的文本、线宽与嵌入图像分辨率，并逐个核对检测到的字号与线宽。即使能抽取部分文本，仍需核对有无其他标注被转曲。TIFF 从 X/Y 分辨率及单位标签计算物理尺寸，并核对位深、压缩、页数与透明通道。光栅图中文字字号无法从像素可靠还原。报告的 `native_measurements` 记录原生数据，`evidence_sources` 逐项列明来源。EPS、EMF 的深层属性在当前实现中保留人工复核。

## 原生样式

`apply_journal_style` 接受可选的 `width_mm`、`font_pt`、`stroke_pt`、`panel_label`。多面板用按图层顺序列出的字母列表。多层可能共用一个面板，例如双 Y 轴，因而面板标记由调用方指明。函数用页面自身的打印分辨率换算成品宽度，按原纵横比调整高度，然后为各层轴线、已存在的轴标题和图例、适用的数据线设置样式并读取属性。输出的 `applied` 记录对象读回，`needs_review` 保留本机版本未确认的属性，导出文件另行核验。检查旧版本的刻度字号时留意 `layer.axis.label.pt` 的版本支持。[Origin 页面尺寸](https://docs.originlab.com/labtalk/ref/page-obj/) · [刻度标签](https://docs.originlab.com/labtalk/ref/layer-axis-label-obj/) · [曲线属性](https://docs.originlab.com/labtalk/ref/layer-plotn-obj/)
