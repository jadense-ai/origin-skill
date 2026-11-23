"""Qualify the offline recipe library or run serial, native Origin acceptance jobs."""
import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(os.getenv("ORIGIN_PLOT_SKILL_ROOT",ROOT/"skill/origin-plot"))
OFFICIAL = Path(os.getenv("ORIGIN_PLOT_OFFICIAL_DIR",ROOT/"resources/official"))
sys.path.insert(0,str(SKILL/"scripts"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def store(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False) as tmp:
        json.dump(value,tmp,ensure_ascii=False,indent=2,allow_nan=False)
    os.replace(tmp.name,path)


def clock():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def offline(ids):
    from recipes.prepare import prepare
    catalog=load(OFFICIAL/"catalog.json")["templates"]
    inventory=load(OFFICIAL/"manifest.json")
    if len(catalog)!=95 or len({r["id"] for r in catalog})!=95:
        raise ValueError("官方目录项数或 ID 不符")
    for entry in inventory["files"]:
        path=(OFFICIAL/entry["path"]).resolve()
        if not path.is_relative_to(OFFICIAL.resolve()) or digest(path)!=entry["sha256"]:
            raise ValueError("官方资源校验失败："+entry["path"])
    specimens={}
    for key in ids:
        source=SKILL/"assets/recipes"/key
        spec=load(source/"recipe.json")
        examples={}
        for variant in ("a","b"):
            path=source/f"example-{variant}.csv"
            with path.open(encoding="utf-8-sig",newline="") as f:
                records=list(csv.DictReader(f))
            plan=prepare(key,records)
            declared = next(row["expected"] for row in spec["examples"] if row["id"]==variant)
            if json.loads(json.dumps(plan.expected)) != declared:
                raise ValueError(f"{key}/{variant} 与配方随附的科学验算值不符")
            examples[variant]={"rows":len(records),"input_sha256":digest(path),
                               "expect":plan.expected}
        if examples["a"]["input_sha256"]==examples["b"]["input_sha256"]:
            raise ValueError("两份示例数据相同："+key)
        image=SKILL/"assets/previews"/(key+".png")
        if not image.is_file() or image.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":
            raise ValueError("缺少配方参考预览："+key)
        specimens[key]={"name":spec["name"],"examples":examples,"reference_png":image.name}
    journals=[load(SKILL/"references/journals"/(j+".json")) for j in ("nature","science","cell","plos-one")]
    return {"status":"offline_verified","checked_at":clock(),"official_templates":len(catalog),
            "official_files":len(inventory["files"]),"journals":len(journals),"recipes":specimens,
            "native_status":"requires_separate_origin_run"}


def work_order(key):
    location=SKILL/"assets/recipes"/key
    return {"recipe_id":key,"name":load(location/"recipe.json")["name"],
            "inputs":[str(location/f"example-{c}.csv") for c in ("a","b")],
            "reference_preview":str(SKILL/"assets/previews"/(key+".png")),
            "deliver":["OTPU","OPJU A/B","Origin PNG A/B","修改后另存的 OPJU","回读记录"],
            "review":["核对数据绑定与配方专属指标","在最终尺寸下检查轴、单位、图例与裁切","用另一组数据复绘"]}


def checked_artifact(record, suffix):
    path=Path(record["path"])
    if path.suffix.lower()!=suffix or not path.is_file() or path.stat().st_size==0 or digest(path)!=record["sha256"]:
        raise ValueError(f"产物校验失败：{path}")
    return record


def verify_render(result, expected):
    checked_artifact(result["project"],".opju")
    checked_artifact(result["exports"]["png"],".png")
    if result["reopen"]["status"]!="verified":
        raise ValueError("重开工程未通过")
    info=result["reopen"]["readback"]
    if info["layer_count"]!=expected["layer_count"] or any(
        count<minimum for count,minimum in zip(info["plot_counts"],expected["min_plots"],strict=True)):
        raise ValueError("重开工程图层或曲线数量与绘图配方不符")
    return info


def plot_sources(graph):
    sources = []
    for layer in graph["layers"]:
        row = []
        for plot in layer["plots"]:
            roles = plot["data_roles"]
            if not roles or any(not (source or {}).get("content_sha256") for source in roles.values()):
                raise ValueError(f"图层 {layer['index']} 曲线 {plot['index']} 缺少实际数据的指纹")
            row.append({"pid": plot["plot_type_id"], "roles": {role: source["content_sha256"] for role, source in roles.items()}})
        sources.append(row)
    return sources


def verify_template_reopen(result, template, expected_sources):
    info = result["reopen"]["readback"]
    proof = result["inspection"]["template_binding"]
    if (result["reopen"]["status"] != "verified" or proof["passed"] is not True
            or proof["sha256"] != template["template"]["sha256"]):
        raise ValueError("模板文件或换数据工程重开验证失败")
    for key in ("height_mm", "width_mm"):
        if not math.isclose(info["page"][key], template["inspection"]["page"][key], abs_tol=0.1):
            raise ValueError(f"换数据后图页没有保留 A 组模板属性 {key}")
    actual = plot_sources(info)
    if expected_sources is not None and actual != expected_sources:
        raise ValueError("换数据工程重开后原生绑定与独立 B 组不一致")
    return {"status": "verified", "evidence": proof, "run_dir": result["run_dir"],
            "project": checked_artifact(result["project"], ".opju"),
            "preview": checked_artifact(result["exports"]["png"], ".png"),
            "reopened_page": info["page"], "reopened_data": actual}


def verify_replacement(result, baseline):
    if result["reopen"]["status"] != "verified":
        raise ValueError("替换后的工程未通过重开校验")
    read = result["reopen"]["readback"]
    before, after = plot_sources(baseline), plot_sources(read)
    expected = json.loads(json.dumps(before))
    bindings = result["inspection"]["data_binding"]["bindings"]
    for binding in bindings:
        layer, index = binding["layer"] - 1, binding["native_plot"] - 1
        roles = binding["data_roles"]
        expected[layer][index] = {"pid": binding["plot_type_id"],
                                  "roles": {k: v["content_sha256"] for k, v in roles.items() if k != "y_error"}}
        if "y_error" in roles:
            expected[layer][binding["error_plot"] - 1] = {"pid": 231, "roles": {"y": roles["y_error"]["content_sha256"]}}
    if after != expected or before == after:
        raise ValueError("重开后选中曲线的数据不正确，或其他曲线的数据发生变化")
    info = {"status": "verified", "graph": read["graph"], "bindings": bindings, "source_data": before, "reopened_data": after,
            "styles": result["inspection"]["changes_verified"], "project": checked_artifact(result["project"], ".opju"),
            "preview": checked_artifact(result["exports"]["png"], ".png")}
    return info


def workflow_fixture(root):
    from openpyxl import Workbook

    root.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    first = workbook.active
    first.title = "仪器 记录"
    first.append(["样品编号", "时间_s", "浓度", "复测值", "标准误"])
    for row in (("001", 1, 0.18, 0.21, 0.03), ("002", 2, None, 0.28, 0.03),
                ("003", 3, 0.33, 0.36, 0.04), ("004", 4, 0.44, 0.56, 0.05)):
        first.append(row)
    second = workbook.create_sheet("复测")
    second.append(["时间_s", "浓度", "标准误", "复测值"])
    for row in ((10, 1.18, 0.13, 1.35), (20, 1.45, 0.19, 1.62), (30, 1.83, 0.24, 2.10), (40, 2.44, 0.25, 2.75)):
        second.append(row)
    path = root / "合成仪器数据.xlsx"
    workbook.save(path)
    workbook.close()
    return path


async def workflow_checks(call, output, report):
    """Library and project cases using explicitly mapped synthetic input tables."""
    output = output / "workflows"
    workbook = workflow_fixture(output)
    entries = {str(item["id"]): item for item in load(OFFICIAL/"catalog.json")["templates"]}
    official, projects = report["official_workflows"], report["project_workflows"]

    def xy(layer=1, plot=1, y="浓度", sheet="仪器 记录", **extra):
        return {"layer": layer, "plot": plot, "sheet": sheet, "columns": {"x": "时间_s", "y": y},
                "units": {"x": "s"}, **extra}

    cases = {"765": [xy(), xy(plot=2, y="复测值")], "774": [xy()], "752": [xy()],
             "802": [xy(options={"group": True}), xy(plot=2, y="复测值", options={"group": True})],
             "973": [xy(layer=1), xy(layer=2, y="复测值"), xy(layer=3, sheet="复测")]}
    for key in (*cases, "754"):
        folder = output / "official" / key
        entry = entries[key]
        template_path = str(OFFICIAL / entry["template_path"])
        try:
            if key == "754":
                async def render(variant, template, destination):
                    source = SKILL/"assets/recipes/box-raw"/f"example-{variant}.csv"
                    return await call("render", recipe_id="box-raw", data_path=str(source),
                                      template_path=template, output_dir=str(destination), formats=["png"], reopen=True)
            else:
                async def render(variant, template, destination):
                    mappings = cases[key]
                    if variant == "b":
                        mappings = [
                            {**item, "columns": {**item["columns"], "y": "浓度" if item["columns"]["y"] == "复测值" else "复测值"}}
                            for item in mappings
                        ]
                    return await call("render_template", data_path=str(workbook), bindings=mappings,
                                      changes={"layer": 3, "x_major_ticks": 4} if key == "973" else None,
                                      template_path=template, output_dir=str(destination), formats=["png"], reopen=True)
            a = await render("a", template_path, folder/"a")
            b = await render("b", template_path, folder/"b")
            name = a["inspection"]["graph"]
            marked = await call("edit", graph_name=name, project_path=a["project"]["path"],
                                output_dir=str(folder/"template-source"),
                                changes={"height_mm": a["inspection"]["page"]["height_mm"] * 1.15}, formats=["png"])
            template = await call("save_template", graph_name=name, project_path=marked["project"]["path"],
                                  output_dir=str(folder/"template"))
            rebound = await render("b", template["template"]["path"], folder/"rebind-b")
            signature = plot_sources(b["reopen"]["readback"])
            if signature == plot_sources(a["reopen"]["readback"]):
                raise ValueError("官方模板 A/B 原生数据指纹相同")
            official[key] = {"name": entry["name"], "status": "verified", "template": template["template"],
                             "official_template": a["inspection"]["template_source"],
                             "template_rebind_b": verify_template_reopen(rebound, template, signature)}
            if key == "802":
                legend = rebound["reopen"]["readback"]["layers"][0]["legend_text"]
                if legend.splitlines() != [r"\l(1) %(1)", r"\l(2) %(2)"]:
                    raise ValueError("分组折线图的原生图例与 B 组曲线不一致")
            if key == "752":
                style = await call("edit", graph_name=a["inspection"]["graph"], project_path=a["project"]["path"],
                                   output_dir=str(folder/"fill"), changes={"fill_color": "#4373a2"}, formats=["png"], reopen=True)
                official[key]["fill_style"] = {"project": style["project"], "preview": style["exports"]["png"],
                                               "color": style["reopen"]["readback"]["layers"][0]["plots"][0]["fill_color"]}
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            official[key] = {"name": entry["name"], "status": "failed", "reason": str(exc)}
        store(output/"official"/key/"verification.json", official[key])

    error = xy(sheet="复测")
    error["columns"]["y_error"] = "标准误"
    heatmap = output/"热图复测.tsv"
    with (SKILL/"assets/recipes/heatmap/example-b.csv").open(encoding="utf-8-sig", newline="") as source:
        with heatmap.open("w", encoding="utf-8", newline="") as target:
            csv.writer(target, delimiter="\t").writerows(csv.reader(source))
    inputs = {
        "multi-line": (workbook, xy(plot=2), {"plot": 2, "line_style": "dash", "color": "#2370a2", "line_width": 2.0}),
        "point-error": (workbook, error, {"symbol_kind": 2, "symbol_size": 8}),
        "multi-panel": (workbook, xy(layer=2, sheet="复测"), {"layer": 2, "x_title": "复测时间", "x_title_size": 13,
                                                               "width_mm": 113, "height_mm": 77, "x_scale": "log10"}),
        "histogram": (SKILL/"assets/recipes/histogram/example-b.csv", {"layer": 1, "plot": 1, "columns": {"value": "value"}},
                      {"bin_count": 4}),
        "heatmap": (heatmap, {"layer": 1, "plot": 1, "columns": {"row": "row", "column": "column", "value": "value"}},
                    {"palette": "Viridis.pal", "color_levels": [-3, -1, 0, 1, 3]}),
    }
    for key, (data, binding, changes) in inputs.items():
        folder = output/"projects"/key
        try:
            a = await call("render", recipe_id=key, data_path=str(SKILL/"assets/recipes"/key/"example-a.csv"),
                           output_dir=str(folder/"a"), formats=["png"], reopen=True)
            project = checked_artifact(a["project"], ".opju")
            result = await call("edit", graph_name=a["inspection"]["graph"], data_path=str(data), bindings=[binding],
                                project_path=project["path"], output_dir=str(folder/"b"), changes=changes, formats=["png"], reopen=True)
            projects[key] = verify_replacement(result, a["reopen"]["readback"])
            projects[key]["source_project"] = checked_artifact(project, ".opju")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            projects[key] = {"status": "failed", "reason": str(exc)}
        store(folder/"verification.json", projects[key])

    invalid = xy()
    invalid["columns"]["y"] = "不存在的列"
    try:
        await call("render_template", template_path=str(OFFICIAL/entries["765"]["template_path"]),
                   data_path=str(workbook), bindings=[invalid], output_dir=str(output/"invalid"), formats=["png"])
    except ValueError as exc:
        report["invalid_mapping"] = {"status": "verified" if "不存在的列" in str(exc) else "failed", "message": str(exc)}
    else:
        report["invalid_mapping"] = {"status": "failed", "message": "错误列名未被拒绝"}

    heatmap_project = projects["heatmap"].get("source_project")
    if heatmap_project:
        with heatmap.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        missing_cell = output / "缺格热图.tsv"
        with missing_cell.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, delimiter="\t").writerows([rows[0], *rows[2:]])
        try:
            await call("edit", graph_name=projects["heatmap"]["graph"], project_path=heatmap_project["path"],
                       data_path=str(missing_cell), bindings=[inputs["heatmap"][1]],
                       output_dir=str(output / "invalid-matrix"), formats=["png"])
        except ValueError as exc:
            checked_artifact(heatmap_project, ".opju")
            message = str(exc)
            row, column = rows[1][:2]
            status = "verified" if "Layer 1, plot 1" in message and repr(row) in message and repr(column) in message else "failed"
            report["invalid_matrix"] = {"status": status, "message": message}
        else:
            report["invalid_matrix"] = {"status": "failed", "message": "未拒绝缺少一个单元的热图矩阵"}
    else:
        report["invalid_matrix"] = {"status": "failed", "message": "缺少通过验证的热图工程"}

    histogram = projects["histogram"].get("source_project")
    if histogram:
        try:
            await call("edit", graph_name=projects["histogram"]["graph"], project_path=histogram["path"],
                       changes={"symbol_kind": 2}, output_dir=str(output / "invalid-style"), formats=["png"])
        except ValueError as exc:
            checked_artifact(histogram, ".opju")
            report["invalid_style"] = {"status": "verified" if "symbol_kind requires" in str(exc) else "failed",
                                       "message": str(exc)}
        else:
            report["invalid_style"] = {"status": "failed", "message": "直方图接受了不支持的散点符号"}
    else:
        report["invalid_style"] = {"status": "failed", "message": "缺少通过验证的直方图工程"}


@contextmanager
def one_worker(output):
    import msvcrt
    output.mkdir(parents=True,exist_ok=True)
    with (Path(tempfile.gettempdir())/"origin-plot-native-worker.lock").open("a+b") as f:
        if not f.tell():
            f.write(b"0"); f.flush()
        f.seek(0)
        msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        try:
            yield
        finally:
            f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


def data_bindings(info):
    sources=[[p["data_roles"] for p in layer["plots"]] for layer in info["layers"]]
    if not all(group and all((roles.get(k) or {}).get("content_sha256")
                             for roles in group for k in ("x","y")) for group in sources):
        raise ValueError("多面板数据来源读回不完整")
    return sources


async def journal_switch(call, original, folder, expected):
    project=original["project"]["path"]
    sources=data_bindings(original["reopen"]["readback"])
    evidence={}
    for journal, letters, size in (("nature", "ab", 8), ("science", "AB", 10)):
        changed=await call("edit",graph_name=original["inspection"]["graph"],project_path=project,
                           output_dir=str(folder/journal),journal=journal,
                           journal_options={"panel_label":list("ab")},reopen=True)
        info=verify_render(changed,expected)
        if data_bindings(info)!=sources:
            raise ValueError("期刊切换改变了原始曲线绑定")
        for layer, letter in zip(info["layers"], letters, strict=True):
            panel=layer.get("panel") or {}
            if panel.get("text")!=rf"\b({letter})" or panel.get("fsize")!=size:
                raise ValueError(f"{journal} 面板号或字号未在工程重开后保留")
        pdf=checked_artifact(changed["exports"]["pdf"],".pdf")
        check=changed["journal_check"]["pdf"]
        if check["status"]=="fail":
            raise ValueError(f"{journal} PDF 质检失败：{check['errors']}")
        evidence[journal]={"project":changed["project"],"pdf":pdf,"journal_check":check,
                           "panel_labels":list(letters),"panel_size_pt":size}
        project=changed["project"]["path"]
    return evidence


async def native(ids, output, evidence, *, workflows=False):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,ORIGIN_PLOT_SKILL_ROOT=str(SKILL),ORIGIN_PLOT_OFFICIAL_DIR=str(OFFICIAL),
             ORIGIN_PLOT_SESSION="isolated",PYTHONUTF8="1")
    server=StdioServerParameters(command=sys.executable,args=["-m","origin_plot_backend"],env=env)
    async with stdio_client(server) as (rx,tx), ClientSession(rx,tx) as client:
        await client.initialize()

        async def call(name, **kwargs):
            response=await client.call_tool("origin_plot_"+name,kwargs)
            if response.isError:
                raise ValueError(" ".join(c.text for c in response.content if hasattr(c,"text")))
            obj=response.structuredContent
            if obj is None:
                obj=json.loads(response.content[0].text)
            if set(obj)=={"result"} and isinstance(obj["result"],dict):
                obj=obj["result"]
            if obj.get("status")=="error" or obj.get("ok") is False:
                raise ValueError(str(obj))
            return obj

        health=await call("doctor",live=True)
        report={"started_at":clock(),"environment":health,"recipes":{}}
        if not health.get("live_verified"):
            report["status"]="blocked_origin_unavailable"
            store(output/"qualification.json",report)
            print(json.dumps(report,ensure_ascii=False))
            return 2
        for key in ids:
            folder=output/key
            try:
                builds={}
                for v in ("a","b"):
                    src=SKILL/"assets/recipes"/key/f"example-{v}.csv"
                    builds[v]=await call("render",recipe_id=key,data_path=str(src),output_dir=str(folder/v),
                                         formats=["png"],reopen=True)
                    verify_render(builds[v],evidence["recipes"][key]["examples"][v]["expect"])
                original=builds["a"]
                page=original["inspection"]["graph"]
                project=original["project"]["path"]
                marked=await call("edit", graph_name=page, project_path=project, output_dir=str(folder/"template-source"),
                                  changes={"height_mm": original["inspection"]["page"]["height_mm"] * 1.15},
                                  formats=["png"], reopen=True)
                template=await call("save_template",graph_name=page,project_path=marked["project"]["path"],
                                    output_dir=str(folder/"template"))
                checked_artifact(template["template"],".otpu")
                binding={"status":"pending"}
                try:
                    rebound=await call("render",recipe_id=key,data_path=str(SKILL/"assets/recipes"/key/"example-b.csv"),
                                       template_path=template["template"]["path"],output_dir=str(folder/"rebind-b"),
                                       formats=["png"],reopen=True)
                    verify_render(rebound,evidence["recipes"][key]["examples"]["b"]["expect"])
                    expected_sources=plot_sources(builds["b"]["reopen"]["readback"])
                    if expected_sources == plot_sources(original["reopen"]["readback"]):
                        raise ValueError("A/B 原生数据指纹相同")
                    binding=verify_template_reopen(rebound,template,expected_sources)
                except (KeyError,TypeError,ValueError,RuntimeError) as exc:
                    binding={"status":"not_verified","reason":str(exc)}
                # An axis-title change works across all 20 graph types and is visible after reopen.
                title=f"Readback {key}"
                edit=await call("edit",graph_name=page,project_path=project,output_dir=str(folder/"edit"),
                                changes={"layer":1,"x_title":title},formats=["png"],reopen=True)
                reopened=verify_render(edit,evidence["recipes"][key]["examples"]["a"]["expect"])
                if reopened["layers"][0]["axes"]["x"]["title"]!=title:
                    raise ValueError("修改后的坐标轴标题未持久化")
                if key=="histogram":
                    stats=evidence["recipes"][key]["examples"]["a"]["expect"]["science"]
                    width=(stats["bin_end"]-stats["bin_begin"])/3
                    changed=await call("edit",graph_name=page,project_path=project,output_dir=str(folder/"bin-width"),
                                       changes={"layer":1,"plot":1,"bin_begin":stats["bin_begin"],
                                                "bin_end":stats["bin_end"],"bin_width":width},formats=["png"],reopen=True)
                    bins=changed["reopen"]["readback"]["layers"][0]["plots"][0]["histogram"]
                    if abs(bins["bin_width"]-width)>max(abs(width)*1e-6,1e-9):
                        raise ValueError("重开后直方图的箱宽不符")
                checked_artifact(original["project"],".opju")
                journal_evidence = {}
                if key == "multi-panel":
                    try:
                        journal_evidence = await journal_switch(call, original, folder, evidence["recipes"][key]["examples"]["a"]["expect"])
                    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                        journal_evidence = {"status": "failed", "reason": str(exc)}
                record={"status":"native_automated_pass" if binding["status"]=="verified" else "native_render_only",
                        "template_rebind_b":binding,"visual_review":"pending",
                        "recipe":key,"finished_at":clock(),"template":template["template"],
                        "project":original["project"],"preview":original["exports"]["png"],
                        "second_project":builds["b"]["project"],"second_preview":builds["b"]["exports"]["png"],
                        "modified_project":edit["project"],"journal_switch":journal_evidence,
                        "audits":[builds[v]["run_dir"] for v in ("a","b")]}
                store(folder/"native.json",record)
                report["recipes"][key]=record
            except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
                report["recipes"][key]={"status":"failed","message":str(exc)}
            store(output/"qualification.json",report)
        passed = all(r["status"] == "native_automated_pass" for r in report["recipes"].values())
        if "multi-panel" in report["recipes"]:
            report["journal_pdf_status"] = report["recipes"]["multi-panel"].get("journal_switch", {}).get("status", "recorded")
        if workflows:
            report.update(official_workflows={}, project_workflows={}, fixture_source="synthetic")
            await workflow_checks(call, output, report)
            passed = (passed and len(report["official_workflows"]) == 6 and len(report["project_workflows"]) == 5
                      and all(r["status"] == "verified" for r in report["official_workflows"].values())
                      and all(r["status"] == "verified" for r in report["project_workflows"].values())
                      and all(report[key]["status"] == "verified"
                              for key in ("invalid_mapping", "invalid_matrix", "invalid_style")))
        report["status"] = "native_checks_passed_pending_visual_review" if passed else "failed"
        store(output/"qualification.json",report)
        print(json.dumps({"status":report["status"],"report":str(output/"qualification.json")},ensure_ascii=False))
        return int(report["status"]=="failed")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=["offline","work-orders","live","workflows"],nargs="?",default="offline")
    p.add_argument("--ids",nargs="+")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    all_ids=[r["id"] for r in load(SKILL/"assets/recipes/catalog.json")["recipes"]]
    if len(all_ids)!=20 or len(set(all_ids))!=20:
        p.error("自制配方清单与发行范围不匹配")
    ids = [] if args.mode == "workflows" else args.ids or all_ids
    if not set(ids)<=set(all_ids):
        p.error("未知配方："+str(set(ids)-set(all_ids)))
    if args.mode=="work-orders":
        result=[work_order(i) for i in ids]
        if args.output:
            store(args.output/"work-orders.json",result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    checks=offline(ids)
    if args.mode=="offline":
        if args.output:
            store(args.output/"offline.json",checks)
        print(json.dumps({"status":checks["status"],"recipes":len(ids),"datasets":2*len(ids),
                          "official":checks["official_templates"],"journals":checks["journals"]},ensure_ascii=False))
        return 0
    out=args.output or (Path(os.environ["ORIGIN_PLOT_GENERATED"]) if os.getenv("ORIGIN_PLOT_GENERATED") else None)
    if not out:
        p.error("原生验收需指定 --output 作为独立交付目录")
    with one_worker(out.resolve()):
        return asyncio.run(native(ids,out.resolve(),checks, workflows=args.mode == "workflows"))


if __name__=="__main__":
    raise SystemExit(main())
