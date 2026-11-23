# Origin 绘图操作

## 数据与图型

在 `assets/recipes/catalog.json` 选取图型，再读取对应 `recipe.json`。两份 CSV 是独立合成数据，适合复测；`assets/previews` 中为示例 A 的参考布局。把角色映射到用户的真实列名，如直方图可传 `columns={"value":"粒径_nm"}`。XLSX 多工作表时指定 `sheet`。保留原始观测与单位，源表仅含汇总量时选用能表达这些汇总量的图型。

独立会话中向 `origin_plot_render` 传入 `recipe_id`、`data_path`、`output_dir`，按需传 `columns`、`options`、`journal`、`journal_options`、`formats`。例如直方图的 `options={"bin_width":2}` 指定箱宽。查看返回的工程路径、实际图名、图层/曲线计数、PNG 路径和重开状态。

## 官方图模板

在 `catalog show <ID> --source official` 查 `native_template`、`input_roles`、`workflow` 和 `verification`。用 `origin_plot_inspect(template_path=...)` 查看模板图层和现有曲线。`origin_plot_render_template` 可接单条 `x`、`y`，也可每条曲线明确提供 `bindings`。图层与曲线从 1 开始，已有曲线使用检查结果的编号。空模板按每层从 1 连续映射。

```json
{
  "template_path": "D:/figures/kinetics.otpu",
  "data_path": "D:/measurements/实验数据.xlsx",
  "output_dir": "D:/figures/replacement",
  "bindings": [
    {"layer": 1, "plot": 1, "sheet": "实验 A", "columns": {"x": "时间_s", "y": "浓度"}, "units": {"x": "s"}},
    {"layer": 1, "plot": 2, "sheet": "实验 B", "columns": {"x": "时间_s", "y": "浓度", "y_error": "标准误"}}
  ],
  "changes": {"layer": 1, "plot": 2, "line_width": 2, "color": "#2370a2"},
  "formats": ["png"],
  "reopen": true
}
```

普通 XY 的空 Y 单元格作为缺测保留。对称 Y 误差用 `y_error`。直方图用 `columns={"value":"观测列"}`，热图用 `columns={"row":"行标签","column":"列标签","value":"观测值"}`。已有误差棒须在其主曲线的映射里提供误差列。同层若需按模板生成原生分组系列，提供各组各自的 X/Y 列并设 `options={"group":true}`。

## 修改与另存

1. 用独立会话 `origin_plot_inspect` 打开已有工程的副本，或在 current 服务查看用户当前图。使用返回的图页短名、图层、曲线编号和会话标识；当前实例无法唯一定位时先确认。
2. 用 `origin_plot_edit` 指定 `graph_name`、`project_path` 和 `output_dir`。换数据再给 `data_path`、`bindings`，可同时给 `changes`。该操作在已有工程的独立副本导入新的工作表，保留其他曲线对原数据列的引用。当前窗口的样式操作传入上一次 `inspect` 的 `session_token`。
3. 样式修改以同一曲线为目标，例如 `{"layer":1,"plot":2,"line_style":"dash","line_width":2.5}`。比例尺用 `x_scale`、`y_scale`，可选 `linear` 或 `log10`。多面板换数后刻度过密时，在指定图层设置 `x_major_ticks` 或 `y_major_ticks`。配色用十六进制 `color` 或条柱 `fill_color`。热图可设 `palette` 和升序 `color_levels`，符号用 Origin 的正整数 `symbol_kind`。
4. 从结构化读回和导出 PNG 双重核验。用 `origin_plot_reopen` 复核输出，用 `origin_plot_save_template` 保存图模板。一次处理多个配方时按工单隔离目录；共享同一工程时串行写入。

## 目标期刊与最终图件

在本 Skill 的 `scripts` 目录执行 `python -m journals prompt nature`（替换为目标期刊）。将输出加入当前绘图上下文；其中的项目默认值、出版方范围和投稿阶段分别标明。终稿导出后用 `python -m journals check nature figure.json` 核查实测属性；切换期刊时重新加载对应提示词。

四个配置键为 `nature`、`science`、`cell`、`plos-one`。按具体稿件阶段使用。在多面板图中可传 `journal_options={"panel_label":["a","b"]}`；根据配置格式化字号和大小写。Nature → Science 时从原工程副本重设样式并另存。研究者提供的实验设计、区间口径和数据映射不随刊名改动。

逐一查看原生样式的实测字段、需人工检查项及导出图件的规则结果。含有未测量字段时不能声称全部符合投稿规范。把用于验证、复现或继续修改的 OPJU 与最终图件一并交付。
