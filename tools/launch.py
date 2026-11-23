"""Project-local STDIO bootstrap, shared by all supported clients."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    state = json.loads(Path(__file__).with_name("state.json").read_text("utf-8"))
    payload = Path(state["payload"])
    skill = payload / "skill/origin-plot"
    args = sys.argv[1:]
    mode = args.pop(0) if args else "isolated"
    env = dict(os.environ, ORIGIN_PLOT_SKILL_ROOT=str(skill),
               ORIGIN_PLOT_OFFICIAL_DIR=str(payload/"resources/official"),
               ORIGIN_PLOT_GENERATED=os.getenv("ORIGIN_PLOT_GENERATED",str(Path(__file__).parent/"native-library")),
               PYTHONUTF8="1")
    if mode in {"isolated","attach"}:
        env["ORIGIN_PLOT_SESSION"] = mode
        command = ["-m","origin_plot_backend",*args]
    elif mode == "catalog":
        command = [str(skill/"scripts/catalog.py"),*args]
    elif mode == "qualify":
        command = [str(payload/"qa/qualify.py"),*args]
    elif mode == "journal":
        command = ["-m","journals",*args]
        env["PYTHONPATH"]=str(skill/"scripts")
    else:
        raise SystemExit("首个参数为 isolated、attach、catalog、journal 或 qualify")
    return subprocess.call([state["python"],*command],env=env)


if __name__ == "__main__":
    raise SystemExit(main())
