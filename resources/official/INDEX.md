# OriginLab 官方图模板索引

固定提交 `a3287931e1a58366f2eca63551ab0d3fd34c60f9`。共 95 套图模板。每组列出来源包中的 Origin 版本字段，实际兼容性以本机测试为准。

单击中文名称打开本地模板目录。原始工程、预览图及随附脚本均保留在对应目录。

## 三维图（15 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 746 | [双平面的 3D 条状图](upstream/Graph%20Templates/3D/3D%20Bar%20in%202%20Planes) | 9.85 | 将 XYY 或 XYZ 数据绘制为不同平面中的条状图，也称为3d瀑布图。 |
| 747 | [带连接线的 3D 条状图](upstream/Graph%20Templates/3D/3D%20Bars%20with%20Connected%20Line) | 9.8 | 绘制带有连接线的 3D XYY 条状图。 至少需要一组 Y 列数据。 |
| 748 | [3D 圆柱体图](upstream/Graph%20Templates/3D/3D%20Cylinder) | 9.80 | 使用 XYY 数据绘制 3D 圆柱体图。 至少需要一组 Y 列数据。 |
| 1022 | [3D水平浮动条状图](upstream/Graph%20Templates/3D/3D%20Horizontal%20Floating%20Bar) | 10.15 | 选择 XYZZ 列以创建 3D 水平浮动条状图 |
| 967 | [3D堆叠点线图](upstream/Graph%20Templates/3D/3D%20Stacked%20Line%26Symbol) | 10.05 | 在堆叠的 3D 平面上绘制点线图。至少需要一个 Y 列。将定义线条位置的 Z 值放在注释标签行中。 |
| 895 | [3D曲面地图](upstream/Graph%20Templates/3D/3D%20Surface%20Map) | 10.20 | 为数字高程模型（DEM）或二维图像创建 3D 曲面图。 需要矩阵窗口中的 DEM 数据或图像窗口中的 2D 图像。 |
| 750 | [3D XRD 黑白瀑布图](upstream/Graph%20Templates/3D/3D%20XRD%20Watefall%20in%20B%26W) | 9.80 | 使用 XRD 数据绘制黑白的 3D 瀑布图。 支持 (xy) 和 X(Y) 列设置。 Z 值请放入名为 “Z” 的用户自定义的标签行中。 |
| 749 | [3D XRD 瀑布图](upstream/Graph%20Templates/3D/3D%20XRD%20Waterfall) | 9.80 | 使用 XRD 数据绘制使用 Z 值进行颜色映射的 3D 瀑布图。 支持 (xy) 和 X(Y) 列设置。Z 值请放入名为 “Z” 的用户自定义的标签行中。 |
| 779 | [填充颜色映射瀑布图](upstream/Graph%20Templates/3D/Colormap%20Filled%20Waterfall) | 9.80 | 选择至少 2 个 Y 列以绘制瀑布图，并将填充颜色映射到 Y 值。 |
| 974 | [双Y轴瀑布图](upstream/Graph%20Templates/3D/Double-Y%20Waterfall) | 10.05 | 选择至少两个 Y 列以创建具有两个不同 Y 轴的瀑布图。关于左/右轴的分配信息放在注释标签行 |
| 975 | [双Z轴3D条状图](upstream/Graph%20Templates/3D/Double-Z%203D%20Bars) | 10.05 | 选择至少两个 Z 列以创建具有两个不同 Z 轴的 XYZ 3D 并排堆积条状图。数据画到左/右轴的信息放在注释标签行 |
| 925 | [渐变填充的3D颜色映射条状图](upstream/Graph%20Templates/3D/Gradient%20Filled%203D%20Colormap%20Bars) | 10.00 | 绘制带有渐变填充的3D颜色映射条形图。 需要XYZ 列 |
| 968 | [分组3D堆积条状图](upstream/Graph%20Templates/3D/Grouped%203D%20Stacked%20Bars) | 10.05 | 将分组数据绘制为并排的 3D 堆积条状图。 XYZZZZ 列是必需的。分组信息放在注释标签行。 |
| 939 | [立体地形图](upstream/Graph%20Templates/3D/Raised%20Relief%20Map) | 10.00 | 创建立体地形图 |
| 874 | [带插图的瀑布图](upstream/Graph%20Templates/3D/Waterfall%20with%20Inset) | 9.80 | 创建带有插图的瀑布图。 插图是由每条瀑布曲线最大值所绘制的图。XYYYY 列是必需的。 |

## 柱形、饼图与面积图（12 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 971 | [百分比堆积条形地图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/100%25%20Stacked%20Bar%20Map) | 10.05 | 选择 X，再加上至少 3 个 Y 列以创建百分比堆积条形地图，XY 坐标确定每个百分比堆积条的位置。 |
| 752 | [较浅填充色的条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Bar%20Style%20with%20Lighter%20Fill) | 9.8 | 选择至少一个 Y 列来创建条形图。 此图形将使用相同的颜色方案作为边框颜色和填充颜色。填充颜色比边框颜色浅。 |
| 798 | [带有连接线的条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Bar%20with%20Connected%20Line) | 9.80 | 绘制带连接线的 2D 条形图。 支持 X(Y) 和 X(YYerr) 列设置。 |
| 969 | [带棒的条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Bar%20with%20Stick) | 10.05 | 选择至少一列以创建条形图且在每个数据点处显示棒状。 |
| 918 | [前后条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Before-After%20Bar%20Chart) | 10.00 | 选择 XYY列来创建前后对比条形图 |
| 917 | [渐变填充的颜色映射条状图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Gradient%20Filled%20Colormap%20Bars) | 10.00 | 绘制带有渐变填充颜色映射的2D条形图,支持X(Y) 和 X(YYerr) 列 |
| 916 | [来自类别数据的饼图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Pie%20Chart%20from%20Categorical%20Data) | 10.00 | 从类别数据创建饼图。 选择包含类别数据的列来创建图。 |
| 772 | [正负值条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Positive%20Negative%20Bars) | 9.85 | 对于气候数据，人们称此类图形为“Anomaly 图”。 选择要进行绘制的 XY 数据。 |
| 809 | [并排堆积条形图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Side-by-side%20Stacked%20Columns) | 9.80 | 绘制分组数据为并排的条形图。 至少需要 XYY 列数据。支持多个分组。分组信息请放在 “注释” 标签行中。 |
| 771 | [Y 偏移堆积面积图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Stacked%20Area%20by%20Y%20Offset) | 9.80 | 绘制一个 Y 偏移堆积线图然后使用调色板填充线之间的区域。 至少需要一组 Y 列数据。 |
| 970 | [堆积条形地图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Stacked%20Bar%20Map) | 10.05 | 选择 X，再加上至少 3 个 Y 列以创建堆积条形地图，XY 坐标确定每个堆积条的位置。 |
| 1027 | [多面板堆积柱状图](upstream/Graph%20Templates/Bar%2C%20Pie%2C%20Area/Stacked%20Columns%20with%20Multiple%20Panels) | 10.20 | 将分组数据绘制为具有多个面板的堆积柱状图。 按 X／Y／分组／颜色（可选）的顺序选择 3 或 4 列来创建绘图。第 3 列是用于定义面板的分组信息。 |

## 基础二维图（11 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 751 | [箭头图](upstream/Graph%20Templates/Basic%202D/Arrow%20Plot) | 9.85 | 箭头图显示了数据更改的数量和方向。 请选择进行绘制用的 XYY 数据。 |
| 964 | [颜色映射线图](upstream/Graph%20Templates/Basic%202D/Color%20Mapped%20Line) | 10.05 | 选择 XYY 列以绘制颜色映射线图。第二个 Y 代表颜色映射信息。 |
| 759 | [矩形误差棒图](upstream/Graph%20Templates/Basic%202D/Error%20Rectangle) | 9.85 | 绘制带有 X 误差和 Y 误差信息的矩形图。 数据格式应为 XYYY 列, 第二个 Y 列为 X 误差数据， 第三个 Y 列为 Y 误差数据。 |
| 765 | [带网格线的折线图](upstream/Graph%20Templates/Basic%202D/Line%20with%20Grid%20Lines) | 9.8 | 带有网格线和较小边距的折线图。 请选择 XY 或 XYY 或多个 XY 进行绘制。 |
| 766 | [对数轴图](upstream/Graph%20Templates/Basic%202D/Log-log%20Plot) | 9.80 | 轴刻度类型为对数的折线图。 至少需要一组 Y 列数据。 |
| 767 | [气泡矩阵图](upstream/Graph%20Templates/Basic%202D/Matrix%20Bubble) | 9.85 | 气泡矩阵图是通过散点的大小和颜色表示不同的数据。 必须使用虚拟矩阵绘图：工作表中的第一列作为 X 值，长名称作为 Y 值，其余数据为 Z 值的数据。并且按 Z 值设置气泡的大小和颜色。 |
| 769 | [均值线图](upstream/Graph%20Templates/Basic%202D/Mean%20Line%20on%20Graph) | 9.8 | 以均值为参考线的折线图。 至少需要一组 Y 列数据。 |
| 966 | [多个X单个Y绘图](upstream/Graph%20Templates/Basic%202D/Multiple%20Plots%20from%20XXXY%20Data) | 10.05 | 选择 XXXXY 或 YXXXX 列以创建点线图。 |
| 774 | [带平滑线的散点图](upstream/Graph%20Templates/Basic%202D/Scatter%20with%20Smoothed%20Lines) | 9.8 | 绘制散点图并使用平滑曲线连接数据点。 至少需要一组 Y 列数据。 |
| 965 | [带端点的线图](upstream/Graph%20Templates/Basic%202D/Sparkline%20Chart) | 10.05 | 选择至少一个 Y 列以创建两端带点的线图 |
| 1010 | [X偏移散点图](upstream/Graph%20Templates/Basic%202D/X%20Offset%20Scatter) | 10.10 | 如果具有相同的X值，则将散点图创建为并排数据点。 XYYY 或 XYYerrYErr 列是必需的。 |

## 分类与分组图（7 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 876 | [颜色映射旭日图](upstream/Graph%20Templates/Categorical/Colormap%20Sunburst) | 9.90 | 创建颜色映射旭日图。楔形的颜色映射到它们的值。 至少需要 3 列：最后一列应该是数据值（设置为 Y），所有其他列应该是类别和子类别列（设置为 X） |
| 972 | [颜色渐变的旭日图](upstream/Graph%20Templates/Categorical/Gradient%20Sunburst%20Chart) | 10.05 | 按级别渐变颜色的旭日图。类别及其子类别的颜色相似。 至少需要 3 列：最后一列应为数据值（设置为 Y），其他所有列为类别和子类别（设置为 X） |
| 800 | [分组圆条图](upstream/Graph%20Templates/Categorical/Grouped%20Circular%20Bars) | 9.90 | 沿圆圈显示分组条形图。 需要三列，x、分组和 y。x 和分组列应设置为类别列 |
| 801 | [分组线图](upstream/Graph%20Templates/Categorical/Grouped%20Line%20Plots) | 9.90 | 创建每个分组都具有不同线型的线图。 XYY 列是必需的，第二个 Y 是分组列。选择 XY 列以创建绘图。 |
| 802 | [分组点线图](upstream/Graph%20Templates/Categorical/Grouped%20Line%20and%20Symbol) | 9.9 | 创建每个分组都具有不同线型和符号形状的点线图。 XYY 列是必需的，第二个 Y 是分组列。选择 XY 列以创建绘图。 |
| 803 | [分组金字塔图](upstream/Graph%20Templates/Categorical/Grouped%20Pyramid%20Plot) | 9.90 | 创建分组金字塔图以跨组比较两个数据集。 数据应按X、分组、Y1、Y2的顺序排列在列中 |
| 761 | [分组堆积线图](upstream/Graph%20Templates/Categorical/Grouped%20Stacked%20Lines) | 9.80 | 将组数据绘制成折线图，并按 Y 偏移进行堆积。 需要 XYYYY 列数据进行绘图。分组信息请放入 “注释” 标签行。 |

## 等高线与热图（6 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 755 | [气候图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Climate) | 9.85 | 世界经度范围为从 -180 至 180，纬度范围为从 90 至 -90 |
| 886 | [不带等高线的等高线颜色填充图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Contour%20without%20Contour%20Lines) | 9.95 | 绘制不带等高线的等高线颜色填充图. 需要XYZ列 |
| 1057 | [分组热图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Heatmap%20with%20Group) | 10.25 | 创建手动分组的热图。 需要一个工作表（虚拟矩阵）：第一列里是 X 标签，第二列里是 X 分组信息，Y 标签位于“长名称”标签行中，Y 分组信息位于“注释”标签行中。 |
| 812 | [带显著性标记的热图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Heatmap%20with%20Significant%20Mark) | 9.80 | 绘图一个热图并使用显著性标记作为标签。 需要两个工作表（虚拟矩阵）进行绘图：第一个工作表是绘图数据，第二个工作表是显著性标记。两个表的行列数和结构必须一样。 |
| 1008 | [极坐标热图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Polar%20Heatmap) | 10.10 | 根据工作表中的数据创建极坐标热图 需要虚拟矩阵数据：工作表的第一列中包含X值，长名称中包含Y值，其余数据单元格为Z值 |
| 762 | [三角形热图](upstream/Graph%20Templates/Contour%2C%20Heatmap/Triangle%20Heatmap) | 9.80 | 绘图一个下三角形的热图，并用 Z 值作为标签。 需要使用虚拟矩阵进行绘图。 |

## 多面板与多轴图（8 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 1009 | [双Y轴堆积柱状+线图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/2Ys%20StackedColumn-Line) | 10.10 | 将组数据绘制为左侧Y轴中的堆积柱状图，并在右侧Y轴中绘制叠加线图 将堆积柱状数据放在第一个工作表中（组信息放在注释标签行中），将线图数据放在第二个工作表中 |
| 920 | [多面板桥图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Bridge%20Charts%20in%20Multiple%20Panels) | 10.00 | 创建多组桥图以观察原始数据的数据变化。 选择X和至少两个Y列以在多个面板中创建桥图 |
| 927 | [双Y前后图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Double%20Y%20Before-After%20Plot) | 10.00 | 选择两列来创建具有2个不同Y轴的前后对比图 |
| 745 | [双Y轴的堆积柱状图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Double%20Y%20Stackd%20Columns) | 10.05 | 将两组数据绘制成并排的柱状图，每个分组有自己的 Y 轴。 XYYYY 列是必需的。分组信息放在注释标签行。 |
| 973 | [多个X单个Y绘制的多面板图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Multiple%20Panels%20with%20XXXY%20Data) | 10.05 | 选择 XXXXY 或 YXXXX 列以创建多面板图。在单独的面板中绘制各组 XY。 |
| 1015 | [时间序列浏览](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Time%20Series%20Explorer) | 10.15 | 至少选择一个 Y 列以创建带缩放 ROI 的折线图。 X 可以是日期或时间列。 使用范围按钮切换到适当的范围，移动 ROI 或使用按钮浏览时间序列数据。 |
| 795 | [三方图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Tripartite%20Plot) | 10.25 | 三方图由 4 个对数刻度轴， X、Y 和从 X Y 派生的两个轴组成。另​​外两个轴与 X 轴成 45 度和 135 度。 选择至少一对 xy 列来创建三方图。使用右上角的按钮更改单位 |
| 905 | [共享Y轴的双X图](upstream/Graph%20Templates/Multi-Panel%2C%20Multi-Axis/Y-Shared%20Double-X%20Plot) | 10.00 | 绘制双X点线图，底轴为X1，顶轴为X2 选择XXY列来创建共享Y轴的双X图。 |

## 专业图（17 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 1045 | [圆形雷达图](upstream/Graph%20Templates/Specialized/Circular%20Radar%20Chart) | 10.20 | 选择至少一列来创建具有圆形角度轴的雷达图 |
| 879 | [Delaunay三角剖分](upstream/Graph%20Templates/Specialized/Delaunay%20Triangulation) | 9.95 | 选择XY列绘制Delaunay三角剖分图。 |
| 758 | [椭圆图](upstream/Graph%20Templates/Specialized/Ellipse) | 9.8 | 以 X 中心，Y 中心，半长轴，半短轴和旋转角度（可选）绘制椭圆图。 |
| 883 | [能级图](upstream/Graph%20Templates/Specialized/Energy%20Diagram) | 9.95 | 创建简单能级图。 需要两列数据(XY)。第三列是可选的，将用作标签。 |
| 887 | [甘特图](upstream/Graph%20Templates/Specialized/Gantt%20Chart) | 9.95 | 创建甘特图。 需要4列数据。前两列分别是类别和项目。后两列是开始日期和结束日期，因此必须正确设置为日期类型。 |
| 1007 | [元素周期表](upstream/Graph%20Templates/Specialized/Periodic%20Table) | 10.10 | 生成带元素值的颜色映射的元素周期表。 选择工作表中的任意列以生成元素周期表 |
| 804 | [极坐标颜色映射线图](upstream/Graph%20Templates/Specialized/Polar%20Colormapped%20Line) | 9.90 | 绘制极坐标中的颜色映射线图。 选择 (theta, r) 数据进行绘图。 |
| 921 | [径向气泡图](upstream/Graph%20Templates/Specialized/Radial%20Bubble) | 10.00 | 径向气泡通过散点大小和颜色表示数据。 需要虚拟矩阵：工作表的第一列中包含X值，长名称中包含Y值，其余数据单元格是决定气泡大小和颜色的Z值。 |
| 775 | [Schoeller 图](upstream/Graph%20Templates/Specialized/Schoeller%20Diagrams) | 9.8 | Schoeller 图是一种或多种水化学样本组成的图形。在水化学学科中很流行。 选择离子列以绘制图形，并在选择的列之前放置样品的 ID。 |
| 884 | [仪表图](upstream/Graph%20Templates/Specialized/Speedometer%20Chart) | 9.95 | 创建仪表图。 需要3列数据，第1列和第2列是速度计的级别和百分比，第3列是指针的值 |
| 922 | [三元密度点图](upstream/Graph%20Templates/Specialized/Ternary%20Density%20Dots) | 10.00 | 三元坐标中的密度点图。 选择一组 XYZ 列来创建图表 |
| 777 | [三元相图](upstream/Graph%20Templates/Specialized/Ternary%20Phase%20Diagram) | 9.95 | 三元相图在材料科学界很流行。此坐标中，Y 和 Z 轴的刻度均于同一角（X）从零开始。 请使用 XYZ 数据列进行绘图。 |
| 1043 | [晶圆图](upstream/Graph%20Templates/Specialized/Wafer%20Map) | 10.20 | 选择矩阵表来创建晶圆图。 |
| 1044 | [风向矢量杆图](upstream/Graph%20Templates/Specialized/Wind%20Vectors%20Stick%20Diagram) | 10.20 | 选择 XYY 列创建风向矢量杆图。X 列是时间序列数据，第一个 Y 代表风向（以度为单位），第二个Y列代表风速。 |
| 805 | [XPS 面积图](upstream/Graph%20Templates/Specialized/XPS%20Area) | 9.90 | 创建 XPS 峰的面积图。 数据应应排列到列中，且列为 BE、Raw、Sum、BG、Peak1、Peak2 等。 |
| 806 | [XPS 线图](upstream/Graph%20Templates/Specialized/XPS%20Line) | 9.80 | 为 XPS 峰创建折线图。 数据应排列到列中，且列顺序为 BE、Raw、Sum、BG、Peak1、Peak2 等。 |
| 929 | [XRD-PDF堆叠图](upstream/Graph%20Templates/Specialized/XRD%20with%20PDF) | 10.00 | 用于显示X射线衍射 (XRD) 和相应PDF卡片标准模型的图表 将XRD数据作为XY列放在第一个工作表中，将PDF数据作为XY列放在第二个工作表中 |

## 统计图（19 套）

| ID | 图模板 | Origin 版本字段 | 用法 |
|---|---|---|---|
| 796 | [3D 直方图](upstream/Graph%20Templates/Statistical/3D%20Histogram) | 9.80 | 绘制 3D 直方图。 (XY) 列是必需的。 |
| 753 | [带直方图的箱线图](upstream/Graph%20Templates/Statistical/Box%20Chart%20with%20Histogram) | 9.80 | 绘制箱线图及其相应的直方图。 需要一列数据。 |
| 754 | [较浅填充色的箱线图](upstream/Graph%20Templates/Statistical/Box%20Style%20with%20Lighter%20Fill) | 9.80 | 选择至少一个 Y 列来创建箱线图。 此图形将使用相同的颜色方案作为边框颜色和填充颜色。填充颜色比边框颜色浅。 |
| 1046 | [宽度与样本量成正比的箱线图](upstream/Graph%20Templates/Statistical/Box%20Width%20by%20Sample%20Size) | 10.25 | 绘制宽度与样本大小成比例的分组数据箱线图。 按分组列／Y 列的顺序选择 1 个分组列和至少 1 个 Y 列来生成图。选择多个 Y 列将同步生成多个图。 |
| 768 | [连接均值点的箱线图](upstream/Graph%20Templates/Statistical/Box%20with%20Mean%20Connected) | 9.80 | 绘制一个连接均值点的箱线图。 至少需要两列数据。 |
| 856 | [带置信椭圆的聚类图](upstream/Graph%20Templates/Statistical/Cluster%20Plot%20wth%20Confidence%20Ellipse) | 9.90 | 创建带置信椭圆的聚类图。 选择 XYY 列以创建图形，第二个 Y 是分组信息 |
| 1023 | [聚类散点图](upstream/Graph%20Templates/Statistical/Clustered%20Scatter%20Plot) | 10.15 | 选择XYY创建聚类散点图，第二个Y是分组信息 |
| 756 | [角落差值直方图](upstream/Graph%20Templates/Statistical/Corner%20Difference%20Histogram) | 9.85 | 角差直方图会比较不同组中两个变量的差值。 请选择进行绘图用的 XY 列，注意第3列是类别列。 |
| 924 | [相关性和弦图](upstream/Graph%20Templates/Statistical/Correlation%20Chord%20Diagram) | 10.00 | 相关性的和弦图 选择多列并绘制和弦图来观察它们之间的相关性 |
| 888 | [相关性网络图](upstream/Graph%20Templates/Statistical/Correlation%20Network%20Plot) | 9.95 | 用相关系数信息绘制网络图。您可以先运行【统计: 描述统计: 相关系数】以获得 Pearson/Spearman/Kendall 表。 选择长名称作为节点行第一列作为节点列的虚拟矩阵绘制网络图。 |
| 1021 | [分布+箱线+数据](upstream/Graph%20Templates/Statistical/Distribution%20%2B%20Box%20%2B%20Data) | 10.15 | 至少选择一个Y列来创建分布+箱线+数据图 |
| 757 | [分布面积图](upstream/Graph%20Templates/Statistical/Distribution%20Area) | 9.8 | 绘制正态分布曲线并在填充曲线下方的区域，也称为密度图。 至少需要一列数据。 |
| 978 | [带部分X刻度标签的直方图](upstream/Graph%20Templates/Statistical/Histogram%20with%20Range%20X%20Tick%20Labels) | 10.05 | 选择一列数据创建带部分X刻度标签的直方图。 画图后请点击绿锁并选择更改参数以指定区间设置。 |
| 763 | [水平箱线图](upstream/Graph%20Templates/Statistical/Horizontal%20Box) | 9.80 | 绘制水平箱线图，并显示其异常值。 至少需要一列数据。 |
| 764 | [I 型箱线图](upstream/Graph%20Templates/Statistical/I-Shape%20Box) | 9.8 | 绘制箱体样式为 I 型的箱线图。 至少需要一列数据。 |
| 770 | [Notch 箱线图](upstream/Graph%20Templates/Statistical/Notched%20Box%20Plot) | 9.85 | 绘制箱体样式为凹口( Notch) 型的箱线图。 至少需要一列数据。 |
| 773 | [雨云图](upstream/Graph%20Templates/Statistical/Raincloud%20Plot) | 9.80 | 绘制一个水平的小提琴图，其一半图形为小提琴样式，另一半图形为按区间划分的点图。它可以可视化数据分布和概率密度。 至少需要一列数据。 |
| 923 | [分边小提琴图(带单独置信区间)](upstream/Graph%20Templates/Statistical/Split%20Violin%20with%20Separate%20Interval) | 10.00 | 具有单独置信区间的分边小提琴图\选择至少两列。最后一列只需包含 2 个类别。 |
| 885 | [可变宽度直方图](upstream/Graph%20Templates/Statistical/Variable%20Bin%20Width%20Histogram) | 9.95 | 创建具有不同分格宽度的直方图 需要2列数据，第1列是直方图的原始数据，第2列是分格的边界 |

