import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from .runtime import Runtime


def main():
    commands = ["doctor", "render", "render-template", "inspect", "edit", "export", "save-template", "reopen"]
    cli = argparse.ArgumentParser(description="Origin Plot Windows MCP server and evidence-producing CLI")
    cli.add_argument("command", nargs="?", choices=commands)
    cli.add_argument("--mode", choices=["isolated", "attach"], default=os.getenv("ORIGIN_PLOT_SESSION", "isolated"))
    cli.add_argument("--target-pid", type=int, default=os.getenv("ORIGIN_PLOT_TARGET_PID"))
    payload = cli.add_mutually_exclusive_group()
    payload.add_argument("--json", default="{}")
    payload.add_argument("--json-file", type=Path)
    args = cli.parse_args()
    runtime = Runtime(args.mode, args.target_pid)
    if not args.command:
        from .server import application
        application(runtime).run(transport="stdio")
        return

    async def invoke():
        try:
            data = args.json_file.read_text(encoding="utf-8-sig") if args.json_file else args.json
            values = json.loads(data)
            if not isinstance(values, dict):
                raise ValueError("Expected a JSON object.")
            return await getattr(runtime, args.command.replace("-", "_"))(**values)
        finally:
            await runtime.close()

    try:
        result = asyncio.run(invoke())
    except Exception as exc:
        print(json.dumps({"status":"error", "error":str(exc)}, ensure_ascii=True))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
