"""Install an extracted, verified Origin Plot bundle into one project (Windows x64)."""
import argparse
import contextlib
import hashlib
import json
import os
import platform
import struct
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path

CLIENTS = ("codex", "claude", "opencode")
NAMES = {"origin-plot": "isolated", "origin-plot-current": "attach"}
LEX = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/|[{}\[\]:,]|[^\s{}\[\]:,/"]+')


def read(path):
    return path.read_text(encoding="utf-8-sig")


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(content.encode("utf-8"))
    temp_path = Path(temp.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def jsonc_value(source):
    tokens = [m.group() for m in LEX.finditer(source) if not m.group().startswith(("//", "/*"))]
    return json.loads("".join(t for i, t in enumerate(tokens)
                              if not (t == "," and tokens[i+1:i+2] in (["]"], ["}"]))))


def json_put(source, path, value):
    """Insert a property without discarding comments, trailing commas, or unrelated properties."""
    tokens = [m for m in LEX.finditer(source) if not m.group().startswith(("//", "/*"))]

    def parse(index):
        start = index
        token = tokens[index].group()
        children = {}
        if token in ("{", "["):
            index += 1
            end = "}" if token == "{" else "]"
            while tokens[index].group() != end:
                if token == "{":
                    key = json.loads(tokens[index].group())
                    if key in children or tokens[index + 1].group() != ":":
                        raise ValueError("JSON 配置存在重复键或无效结构")
                    index += 2
                else:
                    key = len(children)
                child, index = parse(index)
                children[key] = child
                if tokens[index].group() == ",":
                    index += 1
                elif tokens[index].group() != end:
                    raise ValueError("JSON 配置分隔符无效")
        return (start, index, children), index + 1

    node, consumed = parse(0)
    if consumed != len(tokens):
        raise ValueError("JSON 配置包含多余内容")
    for n, key in enumerate(path):
        start, end, children = node
        if tokens[start].group() != "{":
            raise ValueError("配置键需要 JSON 对象：" + ".".join(path[:n]))
        if key not in children:
            nested = value
            for rest in reversed(path[n + 1:]):
                nested = {rest: nested}
            comma = "," if children and tokens[end - 1].group() != "," else ""
            prop = json.dumps(key) + ": " + json.dumps(nested, ensure_ascii=False)
            return source[:tokens[end].start()] + comma + "\n  " + prop + "\n" + source[tokens[end].start():]
        node = children[key]
    start, end, _ = node
    raw = "".join(t.group() for i, t in enumerate(tokens[start:end + 1])
                  if not (t.group() == "," and tokens[start+i+1].group() in ("]", "}")))
    if json.loads(raw) != value:
        raise ValueError("项目已有不同的同名 MCP 配置：" + ".".join(path))
    return source


def host_configs(project, clients, launcher):
    planned = {}
    for client in clients:
        if client == "codex":
            path = project / ".codex/config.toml"
            original = read(path) if path.exists() else ""
            parsed = tomllib.loads(original).get("mcp_servers", {})
            result = original
            for name, mode in NAMES.items():
                spec = {"command": sys.executable, "args": [str(launcher), mode]}
                if name in parsed and parsed[name] != spec:
                    raise ValueError("Codex 项目已有不同的同名服务 " + name)
                if name not in parsed:
                    result += (f'\n[mcp_servers."{name}"]\ncommand = {json.dumps(sys.executable)}\n'
                               f'args = {json.dumps(spec["args"],ensure_ascii=False)}\n')
            tomllib.loads(result)
        else:
            if client == "claude":
                path = project / ".mcp.json"
            else:
                paths = [project / n for n in ("opencode.jsonc", "opencode.json")]
                existing = [p for p in paths if p.is_file()]
                if len(existing) > 1:
                    raise ValueError("项目同时有 opencode.json 和 opencode.jsonc，请保留使用中的配置")
                path = existing[0] if existing else paths[1]
            original = read(path) if path.exists() else "{}\n"
            result = original
            for name, mode in NAMES.items():
                if client == "claude":
                    result = json_put(result, ["mcpServers", name],
                                      {"type":"stdio","command":sys.executable,"args":[str(launcher),mode]})
                else:
                    # 1.x accepts flat settings; continue an existing nested v2 settings object when present.
                    existing_mcp = jsonc_value(original).get("mcp", {})
                    servers = existing_mcp.get("servers") if isinstance(existing_mcp, dict) else None
                    nested = isinstance(servers, dict) and servers.get("type") not in ("local", "remote")
                    prefix = ["mcp", "servers"] if nested else ["mcp"]
                    result = json_put(result, prefix+[name],
                                      {"type":"local","command":[sys.executable,str(launcher),mode]})
        if result != original or not path.is_file():
            planned[path] = result
    return planned


def check_bundle(bundle):
    manifest = json.loads(read(bundle / "manifest.json"))
    for name, checksum in manifest["files"].items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()) or not path.is_file() or sha(path) != checksum:
            raise ValueError("资源包文件缺失或校验失败：" + name)
    return manifest


@contextlib.contextmanager
def installation_lock(folder):
    # The OS releases this byte-range lock after a crash. The stable file is not the lock state.
    import msvcrt
    path = folder / "install.lock"
    with path.open("a+b") as f:
        if not f.tell():
            f.write(b"0")
            f.flush()
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def install(bundle, project, clients):
    if (sys.platform != "win32" or sys.version_info[:2] != (3, 13) or struct.calcsize("P") != 8
            or platform.machine().lower() not in ("amd64","x86_64")):
        raise ValueError("离线发行包需要 Windows x64 和 64 位 CPython 3.13，请用 py -3.13 install.py")
    manifest = check_bundle(bundle)
    runtime = project / ".origin-plot"
    identity = sha(bundle / "manifest.json")[:16]
    payload = runtime / "releases" / identity
    if runtime.exists() and not (runtime / "origin-plot-install").is_file():
        raise ValueError("已有同名目录未标识为本安装器管理：" + str(runtime))
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "origin-plot-install").touch()
    with installation_lock(runtime):
        install_locked(bundle, project, clients, manifest, runtime, payload)


def install_locked(bundle, project, clients, manifest, runtime, payload):
    state_path = runtime / "state.json"
    prior = json.loads(read(state_path)) if state_path.exists() else {}
    progress_path = runtime / "install-pending.json"
    pending = json.loads(read(progress_path)) if progress_path.exists() else {}
    if pending and pending["payload"] != str(payload):
        raise ValueError("前一次安装中断，请用同一发行包重试后升级")
    clients = set(clients) | set(pending.get("clients", [])) | set(prior.get("clients", []))
    launcher = runtime / "launch.py"
    configs = host_configs(project, clients, launcher)
    skill_dirs = set()
    if {"codex","opencode"}.intersection(clients):
        skill_dirs.add(project / ".agents/skills/origin-plot")
    if "claude" in clients:
        skill_dirs.add(project / ".claude/skills/origin-plot")
    # Recovery accepts old and atomically installed new files only in owned mirrors.
    mirrors = dict(prior.get("mirrors", {}))
    prefix = "skill/origin-plot/"
    new = {name[len(prefix):]:h for name, h in manifest["files"].items() if name.startswith(prefix)}
    for directory in skill_dirs:
        if directory.exists():
            known = mirrors.get(str(directory))
            recovering = str(directory) in pending.get("mirrors", [])
            if not known and not recovering:
                raise ValueError("已有同名 Skill 并非由本安装器创建：" + str(directory))
            actual = {p.relative_to(directory).as_posix():sha(p) for p in directory.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts}
            known = known or {}
            valid = (all(h in (known.get(k), new.get(k)) for k,h in actual.items()) and
                     all(k in actual for k in known.keys() & new.keys())) if recovering else actual == known
            if not valid:
                raise ValueError("检测到本地修改，请先保存该 Skill 的自定义内容：" + str(directory))
    write_atomic(progress_path, json.dumps({"payload":str(payload), "clients":sorted(clients),
                                             "mirrors":[str(p) for p in sorted(skill_dirs)]},ensure_ascii=False))
    payload.mkdir(parents=True, exist_ok=True)
    for name, checksum in manifest["files"].items():
        if name.startswith(("skill/", "resources/", "qa/")) or name in {"LICENSE.txt", "THIRD_PARTY.md"}:
            dest = payload / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file() or sha(dest) != checksum:
                shutil.copy2(bundle / name, dest)
    env_dir = payload / "venv"
    python = env_dir / "Scripts/python.exe"
    if not (payload / "ready").exists():
        venv.EnvBuilder(with_pip=True).create(env_dir)
        subprocess.run([str(python), "-m", "pip", "--disable-pip-version-check", "install", "--no-index",
                        "--no-input", "--find-links", str(bundle/"wheels"), "--require-hashes",
                        "-r", str(bundle/"wheels/install.lock")], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        (payload / "ready").touch()
    for directory in skill_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        for name, checksum in new.items():
            dest = directory / name
            if not dest.is_file() or sha(dest) != checksum:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Stage outside the mirror so an interrupted copy never looks like a user edit.
                staged = runtime / "mirror-file.tmp"
                shutil.copy2(payload / prefix / name, staged)
                os.replace(staged, dest)
        for stale in set(mirrors.get(str(directory), {})) - new.keys():
            path = (directory / stale).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError("Invalid prior mirror path")
            path.unlink(missing_ok=True)
        mirrors[str(directory)] = new
    write_atomic(launcher, read(bundle / "launch.py"))
    state = {"version":manifest["version"], "payload":str(payload), "python":str(python),
             "clients":sorted(set(prior.get("clients", [])) | clients), "mirrors":mirrors}
    write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2))
    for path, content in configs.items():
        write_atomic(path, content)
    progress_path.unlink(missing_ok=True)
    print(json.dumps({"project":str(project),"clients":sorted(clients),"launcher":str(launcher),
                      "runtime":str(payload)},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,required=True)
    parser.add_argument("--clients",nargs="+",choices=(*CLIENTS,"all"),default=["all"])
    args = parser.parse_args()
    install(Path(__file__).resolve().parent,args.project.resolve(),
            set(CLIENTS if "all" in args.clients else args.clients))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError) as exc:
        print("安装失败："+str(exc),file=sys.stderr)
        raise SystemExit(1)
