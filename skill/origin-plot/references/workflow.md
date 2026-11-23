# Origin 绘图操作

## 数据与图型

在 `assets/recipes/catalog.json` 选取图型，再读取对应 `recipe.json`。两份 CSV 是独立合成数据，适合复测；`assets/previews` 中为示例 A 的参考布局。把角色映射到用户的真实列名，如直方图可传 `columns={"value":"粒径_nm"}`。XLSX 多工作表时指定 `sheet`。保留原始观测与单位，源表仅含汇总量时选用能表达这些汇总量的图型。

独立会话中向 `origin_plot_render` 传入 `recipe_id`、`data_path`、`output_dir`，按需传 `columns`、`options`、`journal`、`journal_options`、`formats`。例如直方图的 `options={"bin_width":2}` 指定箱宽。查看返回的工程路径、实际图名、图层/曲线计数、PNG 路径和重开状态。

## 官方图模板

在 catalog 的 `official` 结果中取 `native_template`、`project_paths` 和版本要求。查看对应示例工程和输入说明后再匹配用户的列结构。单层单曲线原生 XY 模板可向 `origin_plot_render_template` 提供模板路径、输入数据和 X、Y 列名。复杂统计、矩阵、多面板或需要配套脚本的模板按其自身入口操作；见到绑定失败时保留具体差异，并继续提供原模板、示例工程和预览。

## 修改与另存

1. 用独立会话 `origin_plot_inspect` 打开已有工程的副本，或在 current 服务查看用户当前图。使用返回的图页短名、图层、曲线编号和会话标识；当前实例无法唯一定位时先确认。
2. 向 `origin_plot_edit` 提供目标图和变更，例如 `{"layer":1,"plot":2,"line_width":2.5}`。当前窗口的操作传入上一读取结果的 `session_token`。在指定目录交付版本化副本。
3. 从结构化读回和导出 PNG 双重核验。可用 `origin_plot_reopen` 复核输出工程，用 `origin_plot_save_template` 单独保存当前图模板。一次处理多个配方时按工单隔离目录；共享同一项目文件时串行写入。

## 目标期刊与最终图件

在本 Skill 的 `scripts` 目录执行 `python -m journals prompt nature`（替换为目标期刊）。将输出加入当前绘图上下文；其中的项目默认值、出版方范围和投稿阶段分别标明。终稿导出后用 `python -m journals check nature figure.json` 核查实测属性；切换期刊时重新加载对应提示词。

四个配置键为 `nature`、`science`、`cell`、`plos-one`。按具体稿件阶段使用。在多面板图中可传 `journal_options={"panel_label":["a","b"]}`；根据配置格式化字号和大小写。Nature → Science 时从原工程副本重设样式并另存。研究者提供的实验设计、区间口径和数据映射不随刊名改动。

逐一查看原生样式的实测字段、需人工检查项及导出图件的规则结果。含有未测量字段时不能声称全部符合投稿规范。把用于验证、复现或继续修改的 OPJU 与最终图件一并交付。
