"""Qualify the offline recipe library or run serial, native Origin acceptance jobs."""
import argparse
import asyncio
import csv
import hashlib
import json
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


async def native(ids, output, evidence):
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
                template=await call("save_template",graph_name=page,project_path=project,output_dir=str(folder/"template"))
                checked_artifact(template["template"],".otpu")
                binding={"status":"pending"}
                try:
                    rebound=await call("render",recipe_id=key,data_path=str(SKILL/"assets/recipes"/key/"example-b.csv"),
                                       template_path=template["template"]["path"],output_dir=str(folder/"rebind-b"),
                                       formats=["png"],reopen=True)
                    verify_render(rebound,evidence["recipes"][key]["examples"]["b"]["expect"])
                    proof=rebound["inspection"].get("template_binding")
                    if (not proof or proof.get("passed") is not True
                            or proof.get("sha256")!=template["template"]["sha256"]):
                        raise ValueError("缺少模板在第二组数据上的绑定读回")
                    binding={"status":"verified","evidence":proof,"run_dir":rebound["run_dir"]}
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
                journal_evidence = (await journal_switch(call,original,folder,
                                    evidence["recipes"][key]["examples"]["a"]["expect"])) if key=="multi-panel" else {}
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
        report["status"]=("native_checks_passed_pending_visual_review" if
                          all(r["status"]=="native_automated_pass" for r in report["recipes"].values()) else "failed")
        store(output/"qualification.json",report)
        print(json.dumps({"status":report["status"],"report":str(output/"qualification.json")},ensure_ascii=False))
        return int(report["status"]=="failed")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=["offline","work-orders","live"],nargs="?",default="offline")
    p.add_argument("--ids",nargs="+")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    all_ids=[r["id"] for r in load(SKILL/"assets/recipes/catalog.json")["recipes"]]
    if len(all_ids)!=20 or len(set(all_ids))!=20:
        p.error("自制配方清单与发行范围不匹配")
    ids=args.ids or all_ids
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
        return asyncio.run(native(ids,out.resolve(),checks))


if __name__=="__main__":
    raise SystemExit(main())
