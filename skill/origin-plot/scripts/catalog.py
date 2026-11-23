"""Search the bundled Origin catalog without Origin, networking, or external packages."""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ORIGIN_2024 = Decimal("10.10")
OFFICIAL_WORKFLOWS = {
    "765": ("origin_plot_render_template", "每条折线的 X、Y，可复用 X 列"),
    "774": ("origin_plot_render_template", "散点 X、Y"),
    "752": ("origin_plot_render_template", "横轴 X、柱或条的 Y"),
    "802": ("origin_plot_render_template", "每个组的 X、Y，可先将长表按组转为多列，启用 options.group"),
    "754": ("origin_plot_render (box-raw)", "group 分组、value 原始观测"),
    "973": ("origin_plot_render_template", "每个面板独立映射 X、Y，可复用 Y 列"),
}


def official_root():
    if os.environ.get("ORIGIN_PLOT_OFFICIAL_DIR"):
        return Path(os.environ["ORIGIN_PLOT_OFFICIAL_DIR"]).resolve()
    for parent in SKILL.parents:
        direct = parent / "resources" / "official"
        if (direct / "catalog.json").is_file():
            return direct
        state = parent / ".origin-plot" / "state.json"
        if state.is_file():
            return Path(json.loads(state.read_text("utf-8"))["payload"]) / "resources" / "official"
    raise FileNotFoundError("官方资源包尚未安装，找不到 resources/official/catalog.json")


def generated_root():
    if os.getenv("ORIGIN_PLOT_GENERATED"):
        return Path(os.environ["ORIGIN_PLOT_GENERATED"])
    for parent in SKILL.parents:
        local = parent / ".origin-plot"
        if (local / "state.json").is_file():
            return local / "native-library"
    return None


def official_compatibility(item, native, generated):
    key = str(item["id"])
    route, roles = OFFICIAL_WORKFLOWS.get(key, ("检查示例工程和模板结构", item["description"].strip()))
    scripts = [name for name in item["companion_paths"] if Path(name).suffix.lower() in {".ogs", ".txt", ".py", ".c"}]
    try:
        too_new = Decimal(item["origin_version"]) > ORIGIN_2024
    except (InvalidOperation, TypeError):
        too_new = False
    status = "version_blocked" if too_new else "not_verified"
    if not too_new and scripts and key not in OFFICIAL_WORKFLOWS:
        status, route = "requires_template_workflow", "打开示例 OPJU 并检查随附脚本或使用说明"
    if not too_new and generated and key in OFFICIAL_WORKFLOWS:
        proof = generated / "workflows" / "official" / key / "verification.json"
        if proof.is_file():
            result = json.loads(proof.read_text("utf-8"))
            if result.get("status") == "verified" and native.is_file():
                with native.open("rb") as file:
                    if hashlib.file_digest(file, "sha256").hexdigest() == result["official_template"]["sha256"]:
                        status = "verified_OriginPro_2024"
    return {"input_roles": roles or "上游目录未标注输入角色，需检查示例工程",
            "workflow": route, "verification": status, "companion_scripts": scripts}


def records(source="all"):
    result = []
    generated = generated_root()
    if source in {"all", "official"}:
        root = official_root()
        for item in json.loads((root / "catalog.json").read_text("utf-8-sig"))["templates"]:
            native = (root / item["template_path"]).resolve()
            if not native.is_relative_to(root.resolve()):
                raise ValueError("模板路径越出资源目录")
            result.append({**item, "source": "official", "id": str(item["id"]),
                           "native_template": str(native), "has_native_file": native.is_file(),
                           **official_compatibility(item, native, generated)})
    if source in {"all", "original"}:
        for path in sorted((SKILL / "assets" / "recipes").glob("*/recipe.json")):
            item = json.loads(path.read_text("utf-8-sig"))
            preview=SKILL/"assets/previews"/(path.parent.name+".png")
            native={}
            if generated:
                witness=Path(generated)/path.parent.name/"native.json"
                if witness.is_file():
                    check=json.loads(witness.read_text("utf-8"))
                    target=Path(check["template"]["path"])
                    if (target.is_file() and target.suffix.lower()==".otpu"
                            and target.resolve().is_relative_to(witness.parent.resolve())
                            and target.stat().st_size==check["template"]["bytes"]):
                        with target.open("rb") as file:
                            actual=hashlib.file_digest(file,"sha256").hexdigest()
                        if actual==check["template"]["sha256"]:
                            native={"native_template":str(target),"verification":check["status"],
                                    "visual_review":check["visual_review"]}
            result.append({**item, "source": "original", "id": path.parent.name,
                           "has_native_file":bool(native),"verification":"awaiting_native_run",
                           "reference_preview":str(preview) if preview.is_file() else None,**native,
                           "recipe": str(path), "examples": [str(f) for f in sorted(path.parent.glob("*.csv"))]})
    return result


def search(query="", source="all"):
    tokens = query.casefold().split()
    return [r for r in records(source) if all(t in json.dumps(r, ensure_ascii=False).casefold() for t in tokens)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "search", "show"))
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--source", choices=("official", "original", "all"), default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = search(args.query, args.source)
    if args.action == "show":
        results = [r for r in results if r["id"] == args.query]
    if args.json or args.action == "show":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"{r['source']:8} {r['id']:22} {r.get('name_zh') or r.get('title_zh') or r.get('title') or r.get('name') or r['id']}")
    return 0 if results else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
