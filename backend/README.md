# Origin Plot 后端

后台使用固定上游提交 `1e9741af96c45bcac9e619c3ba32264bac6950e7` 的 Windows COM 会话池。外部运行环境为 Windows x64、Python 3.13。绘图还需要本机已注册且已获授权的 Origin、其内置解释器和可在该进程内加载的 `originpro`。热图使用内置解释器中的 NumPy。

## 安装及诊断

从项目根目录执行以下 PowerShell 命令。依赖锁覆盖 Windows CPython 3.13，包内提供两只本地 wheel。首次安装第三方依赖需要可使用的 PyPI 镜像，或安装时通过 `--find-links` 提供同版本的完整 wheel 缓存。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --find-links backend\dist -r backend\requirements-win-py313.lock
.\.venv\Scripts\python.exe -m pip install --no-deps backend\dist\origin_plot_backend-0.1.3-py3-none-any.whl
$env:ORIGIN_PLOT_SKILL_ROOT = (Resolve-Path skill\origin-plot).Path
.\.venv\Scripts\python.exe -m origin_plot_backend doctor
.\.venv\Scripts\python.exe -m origin_plot_backend doctor --json '{"live":true}'
```

最后一条命令通过上游 MCP 请求 Origin，并验证执行 COM 请求及执行内置 Python 的两个端点属于同一个进程。只有获得 PID、版本和随机会话标记的实时回读才会报告已验证。若使用的 Origin 把 `originpro` 导入为外部模式，后端会停在探测阶段，避免误开或修改第二个实例。

## 两种会话

- `ORIGIN_PLOT_SESSION=isolated` 是默认值。每个持久 MCP 客户端获得独立 Origin 进程，独立模式池默认有三个席位。从磁盘读取已有工程时始终加载私有工作副本。输出在调用者指定目录的独占 `run-*` 子目录中。
- `ORIGIN_PLOT_SESSION=attach` 用于修改已经打开的窗口。若同时有多个可见 Origin，设置 `ORIGIN_PLOT_TARGET_PID`。在同一 MCP 客户端上先调用 `origin_plot_inspect(graph_name=...)` 获取 `session_token`，再把 token 交给 `origin_plot_edit`。后端核对进程、工程和图形状态，修改前用 Project Explorer 的 `pe_save` 导出恢复副本，修改后再导出图与工程树。用户的窗口继续关联原文件。该模式不会自动重开用户工程，重开验收使用隔离会话。

## MCP 与 CLI

MCP 客户端运行 `python -m origin_plot_backend`。所有工具也接受同名 CLI 子命令，经 `--json-file request.json` 提交 UTF-8 JSON 参数。CLI 每次运行各有一份会话，适合用明确的 `project_path` 加载磁盘工程。

| MCP 工具 | CLI | 原生产物或证据 |
| --- | --- | --- |
| origin_plot_doctor | doctor | 配置状态，可选 Origin 实时探测 |
| origin_plot_render | render | 配方、CSV/TSV/XLSX、OPJU、光栅/矢量输出和重开回读 |
| origin_plot_render_template | render-template | 原生 OTP/OTPU 按图层、曲线和列重绑定，可同时改样式 |
| origin_plot_inspect | inspect | 页面、各图层、坐标轴、图例、底层数据集、图型 ID、直方图分箱 |
| origin_plot_edit | edit | 对指定图层或曲线改样式、替换数据并另存独立副本 |
| origin_plot_export | export | PNG/JPG/TIF/BMP、PDF/EPS/EMF 与文件证据 |
| origin_plot_save_template | save-template | 原生 OTPU 或旧版 OTP |
| origin_plot_reopen | reopen | 在隔离会话打开工程副本后的图页读回 |

`origin_plot_render` 的 `template_path` 用于 20 种配方从实际模板绑定新数据。箱线图和小提琴图使用 Origin 2021b 起提供的索引分组命令。`origin_plot_render_template` 可以用 `ORIGIN_PLOT_OFFICIAL_DIR` 解析相对路径，沿用单序列的 `x`、`y` 参数，也可提供多条 `bindings`。`origin_plot_edit` 在指定工程副本中使用同一种绑定结构。每条映射给出 `layer`、`plot`、`columns`，并可指定 `sheet`、`units`、`plot_type` 和图型 `options`。支持 XY、XY 加对称 Y 误差、直方观测列及热图长表。已有误差棒的曲线须连同误差列一起替换。

`changes` 可设置 `layer`、`plot`（从 1 计数）、`x_title/y_title`、`x_range/y_range`、`x_scale/y_scale`、`x_title_size/y_title_size`、`color`、`line_width`、`line_style`、`symbol_size`、`symbol_kind`、`fill_color`、`legend_text`、`long_name`、`width_mm/height_mm`。原生直方图支持 `bin_begin`、`bin_end`，以及二选一的 `bin_width` 或 `bin_count`。原生热图支持 `palette` 和 `color_levels`。重开验收比较图层、坐标轴、图例、面板标签和数据绑定，原生数据列及矩阵的内容指纹能检测同名数据源的值变化。

期刊预设使用对应配置中的正式输出格式，并另出 PNG 预览。PLOS One 默认形成单页扁平 LZW TIFF，根据实际原生页面宽度计算输出尺度。出版物检查分别记录已测指标、缺失证据和人工复核项。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend\tests -v
```

离线测试覆盖数据读取、会话目标保护、原生属性操作的测试替身、实际 TIFF 编码及工具注册。原生图产生与重开需在拥有目标 Origin 的 Windows 主机运行。
