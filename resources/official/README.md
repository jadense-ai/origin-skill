# OriginLab 官方原生图模板

收录 OriginLab 公开仓库 `Graph Templates/` 在 2026-11-23 核验的固定版本。当前副本含 95 个原生 `.otpu`、同目录的示例工程、预览和资源，以及上游 MIT 许可证。95 个模板的中文名称、说明和版本字段均取自各自包内的 `package.ini`。[固定版本](https://github.com/originlab/Templates/tree/a3287931e1a58366f2eca63551ab0d3fd34c60f9) · [原始 MIT 声明](upstream/LICENSE)

打开[中文分类索引](INDEX.md)可按类别浏览图形，跟随名称找到模板、示例工程及预览。`catalog.json` 供程序按模板 ID、图形中英文名称、类别及描述检索。`manifest.json` 列出每个上游文件的相对路径、字节数、SHA-256 与 Git blob ID。

在源码根目录运行以下命令。

```powershell
python -X utf8 tools/sync_official.py verify
python -X utf8 tools/sync_official.py search 箱线
python -X utf8 tools/sync_official.py search histogram
python -X utf8 tools/sync_official.py fetch
```

`verify` 离线核对整个目录与已固定的远端树摘要，再重新生成三份索引进行逐字节比对。`fetch` 从相同提交下载、先验证清单与内容，再按需恢复本地文件。附带项目和辅助文件保持上游字节，检索和验证只读取它们。

MIT 声明随复制品保留，范围是此固定版本的仓库内容。Origin 客户端、作者门户图件和官网图库中的其他资源各自遵守对应条款。[OriginLab 官方仓库](https://github.com/originlab/Templates)
