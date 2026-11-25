"""Build the complete native-Windows bundle and the separate official-template ZIP."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.3"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def tree(directory):
    for p in sorted(directory.rglob("*")):
        if p.is_file() and not {".git","__pycache__",".pytest_cache"}.intersection(p.parts) and p.suffix != ".pyc":
            yield p


def archive(output, pairs):
    output.parent.mkdir(parents=True,exist_ok=True)
    staging = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(staging,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name, path in sorted(pairs):
            meta = zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
            meta.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(meta,path.read_bytes())
    with zipfile.ZipFile(staging) as z:
        if z.testzip():
            raise ValueError("ZIP 校验失败")
    staging.replace(output)


def build(cache, output, no_download):
    cache.mkdir(parents=True,exist_ok=True)
    lock = ROOT/"backend/requirements-win-py313.lock"
    if not no_download:
        subprocess.run([sys.executable,"-m","pip","--disable-pip-version-check","download","--only-binary=:all:",
                        "--require-hashes","--find-links",str(ROOT/"backend/dist"),"-r",str(lock),"--dest",str(cache)],check=True)
    # Incorporate only wheels named by the runtime's actual lock, including the local upstream wheel.
    requirements = dict(re.findall(r"^([a-zA-Z0-9_.-]+)==([^\s\\]+)",lock.read_text("utf-8"),re.M))
    backend_wheels = list((ROOT/"backend/dist").glob(f"origin_plot_backend-{VERSION}-*.whl"))
    if len(backend_wheels) != 1:
        raise ValueError("请先构建 backend 的唯一发行 wheel")
    wrapper = backend_wheels[0]
    requirements["origin-plot-backend"] = wrapper.name.split("-")[1]
    candidates = {p.name:p for p in [*cache.glob("*.whl"),*(ROOT/"backend/dist").glob("*.whl")]}
    files = {}
    locks = []
    for package, version in sorted(requirements.items()):
        pattern = package.replace("-","_").lower()+"-"+version+"-"
        found = [v for k,v in candidates.items() if k.lower().startswith(pattern.lower())]
        if len(found)!=1:
            raise ValueError(f"{package} {version}: 预期一个 Windows 3.13 wheel，实得 {len(found)}")
        wheel=found[0]
        files["wheels/"+wheel.name] = wheel
        sha = digest(wheel)
        if package != "origin-plot-backend" and sha not in lock.read_text("utf-8"):
            raise ValueError("wheel 不符合源码锁定的哈希："+wheel.name)
        locks.append(f"{package}=={version} --hash=sha256:{sha}")
    for dirname in ["skill/origin-plot","resources/official"]:
        for p in tree(ROOT/dirname):
            files[p.relative_to(ROOT).as_posix()]=p
    for name in ("LICENSE.txt","THIRD_PARTY.md","README.md"):
        files[name]=ROOT/name
    for name in ("install.py","launch.py"):
        files[name]=ROOT/"tools"/name
    files["qa/qualify.py"]=ROOT/"tools/qualify.py"
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        locked=folder/"install.lock"
        locked.write_text("\n".join(locks)+"\n",encoding="utf-8")
        files["wheels/install.lock"]=locked
        manifest=folder/"manifest.json"
        manifest.write_text(json.dumps({"version":VERSION,"platform":"win_amd64-cp313",
                            "upstream_commit":"1e9741af96c45bcac9e619c3ba32264bac6950e7",
                            "files":{name:digest(p) for name,p in sorted(files.items())}},
                            ensure_ascii=False,indent=2),encoding="utf-8")
        files["manifest.json"]=manifest
        archive(output/f"origin-plot-{VERSION}-windows-x64.zip",files.items())
        official=ROOT/"resources/official"
        archive(output/"originlab-templates-a328793-offline.zip",[(p.relative_to(official).as_posix(),p) for p in tree(official)])
    print(json.dumps({p.name:{"bytes":p.stat().st_size,"sha256":digest(p)} for p in sorted(output.glob("*.zip"))},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-cache",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"dist")
    parser.add_argument("--no-download",action="store_true")
    args=parser.parse_args()
    build(args.wheel_cache.resolve(),args.output.resolve(),args.no_download)
