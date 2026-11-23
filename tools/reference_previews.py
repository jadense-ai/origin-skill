"""Build design previews from example A. These PNGs are never native-run evidence."""
import csv
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill/origin-plot"
sys.path.insert(0,str(SKILL/"scripts"))
from recipes.prepare import prepare

COLORS = ("#166B83","#D36A43","#6A6C9C","#58906E","#9A576E","#99864E")


def plot_layer(ax, plan, layer, index):
    key = plan.recipe_id
    for j, mark in enumerate(layer.marks):
        vals=plan.tables[mark["table"]].columns
        xs,ys=vals[mark["x"]][1],vals[mark["y"]][1]
        c=COLORS[(j if mark["color_index"] is None else mark["color_index"]) % len(COLORS)]
        if mark["kind"]=="template":
            continue
        if mark["error"] is not None:
            ax.errorbar(xs,ys,yerr=vals[mark["error"]][1],fmt="o",capsize=3,ms=4,color=c,label=mark["label"])
        elif mark["kind"]=="scatter":
            ax.scatter(xs,ys,s=17,color=c,alpha=.8,label=mark["label"],zorder=3)
        else:
            ax.plot(xs,ys,color=c,lw=1.35,ls="--" if mark["kind"]=="reference" else "-",
                    marker="o" if mark["kind"]=="line-symbol" else None,ms=3,label=mark["label"])
    if key in ("grouped-column","percent-stack","likert"):
        marks=layer.marks
        labels=layer.x_labels[2]
        base_pos=[0.0]*len(labels)
        base_neg=[0.0]*len(labels)
        for j,m in enumerate(marks):
            ys=plan.tables[m["table"]].columns[m["y"]][1]
            cats=list(range(1,len(ys)+1))
            c=COLORS[j%len(COLORS)]
            if key=="grouped-column":
                w=.75/len(marks)
                ax.bar([x+(j-(len(marks)-1)/2)*w for x in cats],ys,w,color=c,label=m["label"])
            elif key=="percent-stack":
                ax.bar(cats,ys,.6,bottom=base_pos,color=c,label=m["label"])
                base_pos=[x+y for x,y in zip(base_pos,ys)]
            else:
                palette=("#CCD0D2","#78ABB7","#22738A","#CCD0D2","#DB9774","#B75530")
                base=base_neg if j<3 else base_pos
                ax.barh(cats,ys,.55,left=base,color=palette[j],label=m["label"] if j!=3 else "_neutral")
                for i,y in enumerate(ys):
                    base[i]+=y
        if key=="likert":
            ax.set_yticks(cats,labels);ax.axvline(0,c="#55636A",lw=.7)
    if key=="histogram":
        s=plan.science; w=s["bin_size"]
        ax.bar([s["bin_begin"]+i*w for i in range(len(s["bin_counts"]))],s["bin_counts"],
               width=w,align="edge",color=COLORS[0],edgecolor="white",linewidth=.9)
    if key in ("box-raw","violin"):
        raw=[c[1] for c in plan.tables[plan.native["table"]].columns]
        if key=="violin":
            v=ax.violinplot(raw,showmedians=True)
            for i,patch in enumerate(v["bodies"]):
                patch.set_facecolor(COLORS[i%len(COLORS)]);patch.set_alpha(.6)
        else:
            ax.boxplot(raw,widths=.45,showfliers=False,medianprops={"color":"#303B44"},zorder=2)
    if key=="heatmap":
        im=ax.imshow(plan.science["matrix"],interpolation="nearest",aspect="auto",cmap="viridis",
                     origin="lower",extent=(.5,len(plan.science["columns"])+.5,.5,len(plan.science["rows"])+.5))
        ax.figure.colorbar(im,ax=ax,pad=.02,shrink=.85)
    if key!="likert":
        for axis,lab,limits in [("x",layer.x_labels,layer.xlim),("y",layer.y_labels,layer.ylim)]:
            if lab:
                getattr(ax,"set_"+axis+"ticks")(range(1,len(lab[2])+1),lab[2])
            if limits:
                getattr(ax,"set_"+axis+"lim")(limits[:2])
        ax.set_xlabel(layer.x_title);ax.set_ylabel(layer.y_title)
    else:
        ax.set_xlabel("占有效应答的百分比");ax.set_ylabel("条目")
    if layer.legend and len(ax.get_legend_handles_labels()[0])>1:
        ax.legend(frameon=False,fontsize=7,ncols=2,loc="best")
    if key=="dual-y":
        ax.yaxis.label.set_color(COLORS[index])
    if key=="eis-nyquist":
        ax.set_aspect("equal",adjustable="datalim")
    if key in ("event-study","coefficient-interval"):
        ax.grid(False)


def main():
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.spines.top":False,"axes.spines.right":False,"axes.labelsize":9,
                         "axes.edgecolor":"#596B73","axes.labelcolor":"#354650","xtick.labelsize":8,
                         "ytick.labelsize":8,"axes.unicode_minus":False,"savefig.facecolor":"white"})
    folder=SKILL/"assets/previews"
    folder.mkdir(parents=True,exist_ok=True)
    items=json.loads((SKILL/"assets/recipes/catalog.json").read_text("utf-8"))["recipes"]
    gallery=["# 自制模板参考图","",
             "这 20 张参考图使用精简的配方示例 A，便于对照输入列和基本图型。通过实机验收时另存 Origin 原生预览。","",
             "更复杂的演示成图、可编辑 OPJU 和输入 CSV 收录在项目的 "
             "[Origin 原生绘图图集](https://github.com/jadense-ai/origin-skill/blob/main/docs/showcase/README.md)。","",
             "![20 种图型](preview-index.png)","","| 图型 | 预览 | 数据与绘图说明 |","|---|---|---|"]
    sheet=Image.new("RGB",(4*375,5*265),"#e4e9ea")
    for pos,info in enumerate(items):
        key=info["id"]; source=SKILL/"assets/recipes"/key
        with (source/"example-a.csv").open(encoding="utf-8-sig",newline="") as f:
            plan=prepare(key,list(csv.DictReader(f)))
        panel=key=="multi-panel"
        fig, axes=plt.subplots(2 if panel else 1,1,figsize=(6.0,4.1),layout="constrained",squeeze=False)
        axs=list(axes.flat)
        if key=="dual-y":
            axs.append(axs[0].twinx());axs[1].spines["right"].set_visible(True)
        for i,(ax,layer) in enumerate(zip(axs,plan.layers)):
            plot_layer(ax,plan,layer,i)
        fig.suptitle(plan.title,fontsize=13,weight="bold",color="#223640")
        fig.supxlabel("示例 A  ·  配方参考预览（Matplotlib）",fontsize=8,color="#526B74")
        fig.savefig(folder/(key+".png"),dpi=135)
        plt.close(fig)
        with Image.open(folder/(key+".png")) as pic:
            thumb=ImageOps.contain(pic.convert("RGB"),(368,257))
            sheet.paste(thumb,((pos%4)*375+3,(pos//4)*265+4))
        gallery.append(f"| {info['name']} | [参考图](previews/{key}.png) | [配方](recipes/{key}/recipe.json) · [示例 A](recipes/{key}/example-a.csv) · [示例 B](recipes/{key}/example-b.csv) |")
    sheet.save(SKILL/"assets/preview-index.png",optimize=True)
    (SKILL/"assets/GALLERY.md").write_text("\n".join(gallery)+"\n",encoding="utf-8")
    print(f"{len(list(folder.glob('*.png')))} reference previews")


if __name__=="__main__":
    main()
