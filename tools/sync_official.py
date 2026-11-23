"""Fetch, verify or search the frozen OriginLab graph-template collection."""

import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile


COMMIT = "a3287931e1a58366f2eca63551ab0d3fd34c60f9"
REPO = "https://github.com/originlab/Templates"
ARCHIVE = f"https://codeload.github.com/originlab/Templates/zip/{COMMIT}"
# SHA-256 over the sorted GitHub API pairs "Git blob OID<TAB>upstream path<LF>".
# Pins every filename and original byte sequence, independently of the local manifests.
PIN = "6e0ab48578ab4981463a649c9b40de56462c81f9f376bc2cd1bba5f3fced3de8"
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "resources" / "official"
CATEGORIES = {
    "3D": "三维图",
    "Bar, Pie, Area": "柱形、饼图与面积图",
    "Basic 2D": "基础二维图",
    "Categorical": "分类与分组图",
    "Contour, Heatmap": "等高线与热图",
    "Multi-Panel, Multi-Axis": "多面板与多轴图",
    "Specialized": "专业图",
    "Statistical": "统计图",
}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_if_changed(path, data):
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            tmp.write(data)
            tmp.close()
            os.replace(tmp_path, path)
        finally:
            tmp.close()
            tmp_path.unlink(missing_ok=True)


def from_archive():
    req = Request(ARCHIVE, headers={"User-Agent": "OriginPlot-Template-Library/1.0"})
    prefix = f"Templates-{COMMIT}/"
    with urlopen(req, timeout=90) as response, ZipFile(io.BytesIO(response.read())) as z:
        files = {}
        for member in z.infolist():
            if member.is_dir() or not member.filename.startswith(prefix):
                continue
            path = member.filename[len(prefix):]
            if path != "LICENSE" and not path.startswith("Graph Templates/"):
                continue
            if path in files:
                raise ValueError(f"Duplicate archive member: {path}")
            files[path] = z.read(member)
    return files


def file_hashes(files):
    rows = []
    anchor = hashlib.sha256()
    for name, data in sorted(files.items()):
        oid = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        anchor.update(f"{oid}\t{name}\n".encode("utf-8"))
        rows.append({"path": "upstream/" + name, "bytes": len(data),
                     "git_blob": oid, "sha256": hashlib.sha256(data).hexdigest()})
    if anchor.hexdigest() != PIN:
        raise ValueError("Upstream file inventory or contents differ from the frozen GitHub tree")
    return rows


def make_entry(template, files):
    parent = template.parent
    folder = str(parent)
    adjacent = sorted(p for p in files if str(PurePosixPath(p).parent) == folder)
    ini_path = str(parent / "package.ini")
    ini = configparser.ConfigParser(allow_no_value=True, interpolation=None, strict=False)
    ini.read_string(files[ini_path].decode("utf-16"))
    pkg, origin = ini["Package"], ini["Origin"]
    prefix = "upstream/"
    category = template.parts[1]
    projects = [prefix + p for p in adjacent if p.lower().endswith(".opju")]
    previews = [prefix + p for p in adjacent if p.lower().endswith(".png")]
    # The regular preview is more useful than the icon or dark-mode preview.
    previews.sort(key=lambda p: ("icon" in PurePosixPath(p).stem.lower(),
                                 "dark" in PurePosixPath(p).stem.lower(), p))
    return {
        "id": pkg["ID"].strip(), "name": pkg["Name"].strip(),
        "name_zh": pkg["Name_cn"].strip(), "category": category,
        "category_zh": CATEGORIES[category], "package_category": pkg["Category"],
        "description_zh": pkg["Description_cn"].replace("\\n", "\n").strip(),
        "description": pkg["Description"].replace("\\n", "\n").strip(),
        "package_version": pkg["Version"], "origin_version": origin["Version"],
        "requires_pro": origin.get("Pro", "").strip() == "1",
        "author": pkg["Author"], "template_path": prefix + str(template),
        "project_paths": projects, "preview_paths": previews,
        "package_ini": prefix + ini_path,
        "companion_paths": [prefix + p for p in adjacent if not p.lower().endswith(
            (".ini", ".otpu", ".opju", ".png"))],
        "source_url": f"{REPO}/tree/{COMMIT}/{quote(folder)}",
        "sha256": hashlib.sha256(files[str(template)]).hexdigest(),
    }


def outputs(files):
    rows = file_hashes(files)
    entries = [make_entry(PurePosixPath(p), files) for p in sorted(files)
               if p.lower().endswith(".otpu")]
    if len(entries) != 95 or len({e["id"] for e in entries}) != 95:
        raise ValueError("Expected 95 distinct official template IDs")
    catalog = {"schema_version": 1, "repository": REPO, "commit": COMMIT,
               "license": "MIT", "license_path": "upstream/LICENSE",
               "template_count": len(entries), "templates": entries}
    manifest = {"schema_version": 1, "repository": REPO, "commit": COMMIT,
                "upstream_tree_url": f"https://api.github.com/repos/originlab/Templates/git/trees/{COMMIT}?recursive=1",
                "inventory_sha256": PIN, "file_count": len(rows), "files": rows}
    index = ["# OriginLab 官方图模板索引", "", f"固定提交 `{COMMIT}`。共 {len(entries)} 套图模板。每组列出来源包中的 Origin 版本字段，实际兼容性以本机测试为准。", "",
             "单击中文名称打开本地模板目录。原始工程、预览图及随附脚本均保留在对应目录。", ""]
    for category, localized in CATEGORIES.items():
        group = [e for e in entries if e["category"] == category]
        index.extend([f"## {localized}（{len(group)} 套）", "",
                      "| ID | 图模板 | Origin 版本字段 | 用法 |", "|---|---|---|---|"])
        for e in group:
            name = e["name_zh"].replace("|", "／")
            desc = " ".join(e["description_zh"].split()).replace("|", "／")
            url = quote(str(PurePosixPath(e["template_path"]).parent))
            index.append(f'| {e["id"]} | [{name}]({url}) | {e["origin_version"]} | {desc} |')
        index.append("")
    return {"catalog.json": json_bytes(catalog), "manifest.json": json_bytes(manifest),
            "INDEX.md": ("\n".join(index) + "\n").encode("utf-8")}


def verify(directory):
    upstream = directory / "upstream"
    files = {p.relative_to(upstream).as_posix(): p.read_bytes() for p in upstream.rglob("*")
             if p.is_file()}
    generated = outputs(files)
    for name, value in generated.items():
        path = directory / name
        if not path.is_file() or path.read_bytes() != value:
            raise ValueError(f"Generated file differs from verified upstream: {name}")
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "verify", "search"))
    parser.add_argument("words", nargs="*", help="Search terms (all must match)")
    parser.add_argument("--root", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    if args.command == "search":
        catalog = json.loads((args.root / "catalog.json").read_text("utf-8"))
        for item in catalog["templates"]:
            searchable = " ".join(str(item[k]) for k in (
                "id", "name", "name_zh", "category", "category_zh",
                "description", "description_zh", "template_path")).casefold()
            if all(term.casefold() in searchable for term in args.words):
                print(f'{item["id"]}\t{item["name_zh"]}\t{item["category_zh"]}\t{item["template_path"]}')
        return
    if args.command == "fetch":
        files = from_archive()
        generated = outputs(files)
        for name, value in files.items():
            write_if_changed(args.root / "upstream" / name, value)
        for name, value in generated.items():
            write_if_changed(args.root / name, value)
    total = verify(args.root)
    print(f"Verified {total} upstream files and 95 graph templates at {COMMIT}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(str(error))
