# Origin 科研绘图 Skill

在 Windows 上通过 Codex、Claude Code 或 OpenCode 调用本机 Origin/OriginPro。发行包包含 **95 套官方图模板、20 套自制绘图配方及 40 份合成示例数据**，支持 Nature、Science、Cell 主刊与 PLOS One 四种期刊配置。自制配方的参考预览由 Matplotlib 生成；Origin 的成图、工程、模板与实机核验记录由本机生成。

## 安装

将 [Windows x64 离线安装包](dist/origin-plot-0.1.0-windows-x64.zip) 下载并解压到本地。在解压目录运行以下命令，把 Skill 和 MCP 注册到实际使用的**项目目录**。需要 Windows x64 和 64 位 Python 3.13。执行绘图另需本机已授权并可正常打开的 Origin，及随 Origin 使用的嵌入式 Python 与 `originpro`。发行包自带 Windows MCP 运行库及锁定的 wheels，安装无需联网。

```powershell
py -3.13 .\install.py --project "D:\研究项目\论文图" --clients all
```

在该项目目录重新打开客户端，按客户端提示信任本地项目或项目 MCP 配置。支持单独选择 `--clients codex`、`claude` 或 `opencode`。默认安装到该项目的 `.origin-plot`，并写入相应的 Skills 目录与 MCP 配置。安装后可以移走原始 ZIP 和解压目录。已有同名且内容不同的手工配置会被明确指出。

## 从第一张图开始

在客户端输入“用 Origin 绘制示例 A 的直方图，保留原始观测，交付 OPJU 和 PNG”。下一轮可指定“把这张图的箱宽改为 2，另存一个副本”。若要编辑当前可见窗口，请明确写“我当前打开的 Origin 工程”，并指明图页或曲线。查看 [工作流说明](skill/origin-plot/references/workflow.md) 了解列映射、工程副本、期刊规则和模板复用。

在安装目标项目中也可以运行以下命令。

```powershell
py -3.13 .\.origin-plot\launch.py isolated doctor
py -3.13 .\.origin-plot\launch.py catalog search 箱线 --source official
py -3.13 .\.origin-plot\launch.py catalog show likert --source original
py -3.13 .\.origin-plot\launch.py journal show nature
py -3.13 .\.origin-plot\launch.py journal prompt nature
py -3.13 .\.origin-plot\launch.py qualify offline
py -3.13 .\.origin-plot\launch.py qualify live --ids histogram likert xrd-stack
```

`qualify live` 默认在项目的 `.origin-plot/native-library` 逐项运行。先试上面三种图型；去掉 `--ids` 可处理 20 套。也可用 `--output` 写入独立目录。每套先画 A/B 两份数据，保存模板，实际尝试以 A 的模板绑定 B，再进行局部改图、重开和读回。失败会保留具体项目和原因。通过自动检查后仍需查看真实 Origin 导出图，核对最终尺寸下的轴、图例和裁切。项目中无 Origin 时，命令生成阻塞记录。

## 模板、期刊和授权

- **官方库**含全部 95 个原生 `.otpu`、96 个示例 `.opju`、360 个 PNG 及上游配套文件，保留原目录、许可和 SHA-256。可按官方分类或中文名称检索。[中文目录](resources/official/INDEX.md) · [官方模板离线包](dist/originlab-templates-a328793-offline.zip)
- **原创库**包含 12 个通用图型，以及文科、经管、生物、材料化学各两个实例。每个目录有输入角色、单位/统计约定及 A/B 样例，参考图供选型时查看。[20 套模板与参考图](skill/origin-plot/assets/GALLERY.md)
- **期刊配置**在绘图前提供目标规则，绘图后校验实际导出。来源、稿件阶段和仍需人工检查的字段随配置提供。不同期刊切换时重用原始数据与分析结果。[期刊配置目录](skill/origin-plot/references/journals)
- 自有代码、提示词和自制模板保留权利。第三方组件按随附许可使用。[自有内容许可](LICENSE.txt) · [第三方来源](THIRD_PARTY.md)

继续扩库时，可把数据与配方制作分给不同子代理，再把原生绘制、改图与重开验收排入单个 Origin 执行器。采集来源、工作分工、工单命令及交付样例见[模板制作说明](skill/origin-plot/references/template-production.md)。

## 从源码复核

使用 64 位 Python 3.13 可直接运行 `py -3.13 tools/sync_official.py verify` 与 `py -3.13 tools/qualify.py offline`。Windows 后端位于 `backend/`，跨客户端 Skill 位于 `skill/origin-plot/`。构建 backend wheel 后用 `py -3.13 tools/build_release.py --wheel-cache <wheel缓存目录>` 重新生成两个 ZIP。
