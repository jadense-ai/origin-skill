# 20 款原生 Origin 配方

每个目录含 `recipe.json` 及两份独立的合成 CSV。注册表为 [catalog.json](catalog.json)。12 款通用图之外，文科、经管、生物、材料化学各有两款。每份示例的 `expected` 给出离线计算的行数、最少图层/绘图对象数量与适用的统计结果。

## 输入与修改

字段名及单位见每款的 `fields`、`axes`、`method`。任意 CSV 表头可通过 `columns={"x":"时间","y":"读数"}` 映射。多系列一般使用长表，每行一个观测。分组柱、堆叠和热图要求显式填全交叉单元；需要统计原始分布时提供逐条观测。区间、回归系数与事件研究的输入是已经计算好的结果，区间水平由作者提供。

生成的工作簿包含 Source 和若干 Data 工作表。图形绑定到 Data 列或矩阵。可在 Origin 中编辑绑定数据和图形属性。频率标准化、经验分布、剂量均值等派生表由配方计算，更新原始 CSV 后重新执行配方可重算所有派生值。XRD 的强度及阻抗虚部保留在源表。

## 原生模板复用

首次出图调用已获授权的本机 Origin，在新工程中执行配方。直方使用 Origin Histogram，箱线/小提琴使用分组统计图，热图使用矩阵图，双轴/双面板分别建立两个原生图层。真机可将合格图页另存为 OTPU。

以另存的 OTPU 作第二组数据的模板时，执行器在新图页上匹配原有槽、替换源数据或增减曲线，记录模板 SHA-256 和实测绑定。失败时返回具体错误。直方需要读取原生分箱表，热图检查矩阵对象，分组箱线/小提琴要求支持指定图模板的 Origin 2021b 或更高版本。分组统计在不同版本可能输出不同的分组表结构，无法确认 B 的观测值和归属时，执行器会报告未通过。

单独的图模板通常保存外观与图层结构，计算公式、源数据和可编辑图页由工程及配方共同保留。查看 `template_binding`、独立重开 OPJU 的证据和原生导出预览，才能决定当前机器是否适合交付。这里的源码和例数据不包含 OriginLab 软件或其系统模板。

## 官方实现依据

- Origin 绘图对象类型及工作表绑定。 [Plot Type IDs](https://docs.originlab.com/labtalk/ref/plot-type-ids/) · [Range Notation](https://docs.originlab.com/labtalk/guide/range-notation/)
- 原始直方图的频数与 Binn 工作表。 [Creating Histograms](https://docs.originlab.com/origin-help/create-histogram/)
- 箱图与小提琴用原始观测和统计主题，已有模板须用支持模板参数的索引输入函数。 [plotgboxraw](https://docs.originlab.com/x-function/ref/plotgboxraw/) · [plot_gboxindexed](https://docs.originlab.com/x-function/ref/plot_gboxindexed/)
- 原生堆叠柱、矩阵热图、双面板的可运行示例。 [OriginLab Python Samples](https://github.com/originlab/Python-Samples/tree/main/4.%20Graphing)
