"""A long-lived stdio client for the pinned upstream server; one owner per session."""
import asyncio
from contextlib import AsyncExitStack
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from . import UPSTREAM_SHA


def skill_root():
    if env := os.getenv("ORIGIN_PLOT_SKILL_ROOT"):
        return Path(env).expanduser().resolve()
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "skill" / "origin-plot"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Set ORIGIN_PLOT_SKILL_ROOT to the installed origin-plot skill.")


def registered_origin():
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Origin.Application\CLSID") as key:
            return bool(winreg.QueryValueEx(key, None)[0])
    except OSError:
        return False


def visible_origin_pids():
    import win32api
    import win32con
    import win32gui
    import win32process

    found = set()

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                                               False, pid)
                try:
                    name = Path(win32process.GetModuleFileNameEx(handle, 0)).name.lower()
                finally:
                    handle.Close()
                if name in {"origin.exe", "origin64.exe"}:
                    found.add(pid)
            except OSError:
                pass
        return True

    win32gui.EnumWindows(visit, None)
    return found


class Bridge:
    def __init__(self, mode="isolated", target_pid=None):
        if mode not in {"isolated", "attach"}:
            raise ValueError("Session mode must be isolated or attach.")
        self.mode = mode
        self.requested_pid = target_pid
        self.pid = None
        self.origin_executable = None
        self.automation_mode = False
        self.token = secrets.token_hex(12)
        self.notes = []
        self.task = None
        self.ready = None
        self.stop = None
        self.client = None

    def diagnostics(self):
        try:
            v = version("origin-pro-mcp")
        except PackageNotFoundError:
            v = None
        try:
            root = skill_root()
        except FileNotFoundError:
            root = None
        available = registered_origin()
        reasons = []
        if sys.platform != "win32" or sys.maxsize <= 2**32:
            reasons.append("Windows x64 is required.")
        if v != "0.3.1":
            reasons.append("Install the bundled pinned upstream wheel.")
        if not available:
            reasons.append("Origin.Application COM class is not registered in this Windows environment.")
        if root is None or not (root / "scripts" / "recipes" / "__init__.py").is_file():
            reasons.append("The origin-plot skill recipe directory was not found.")
        return {"ready_for_live_probe": not reasons, "origin_com_registered": available,
                "live_verified": False, "upstream_version": v, "upstream_commit": UPSTREAM_SHA,
                "session_mode": self.mode, "python": sys.version.split()[0],
                "skill_root": str(root) if root else None, "reasons": reasons}

    async def _lifetime(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        try:
            env = os.environ.copy()
            env["ORIGIN_PLOT_SESSION"] = self.mode
            command = StdioServerParameters(command=sys.executable, args=["-m", "origin_plot_backend.upstream"],
                                             env=env)
            async with AsyncExitStack() as stack:
                rx, tx = await stack.enter_async_context(stdio_client(command))
                self.client = await stack.enter_async_context(ClientSession(rx, tx, read_timeout_seconds=timedelta(minutes=4)))
                await self.client.initialize()
                names = {t.name for t in (await self.client.list_tools()).tools}
                required = {"run_labtalk", "save_project", "load_project", "export_graph", "save_graph_template"}
                if not required <= names:
                    raise RuntimeError("The installed upstream MCP tool registry does not match the pinned runtime.")
                self.ready.set_result(None)
                await self.stop.wait()
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            else:
                raise
        finally:
            self.client = None

    async def start(self):
        if self.task is not None:
            if self.task.done():
                raise RuntimeError("The upstream MCP session ended. Reconnect this client.")
            await self.ready
            return
        health = self.diagnostics()
        if not health["ready_for_live_probe"]:
            raise RuntimeError(" ".join(health["reasons"]))
        if self.mode == "attach":
            candidates = visible_origin_pids()
            if self.requested_pid is None and len(candidates) == 1:
                self.requested_pid = next(iter(candidates))
            if self.requested_pid not in candidates:
                raise ValueError("Attach requires one visible Origin or an explicit ORIGIN_PLOT_TARGET_PID. Visible PIDs: "
                                 + str(sorted(candidates)))
        self.ready = asyncio.get_running_loop().create_future()
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(self._lifetime())
        await self.ready

    async def close(self):
        if self.task is not None:
            self.stop.set()
            await self.task

    async def call(self, name, **args):
        await self.start()
        result = await self.client.call_tool(name, args)
        content = "\n".join(c.text for c in result.content if c.type == "text")
        if "[origin-mcp]" in content:
            content, notice = content.split("[origin-mcp]", 1)
            self.notes.append(notice.strip())
        if result.isError or content.startswith(("Export failed", "NOT EXECUTED", "Executed with errors")):
            raise RuntimeError(f"{name}: {content.strip()}")
        return content.strip()

    async def embedded(self, action, **params):
        if self.pid is None and action != "doctor":
            await self.embedded("doctor")
        script = Path(__file__).with_name("embedded.py")
        cookie_name = "opb" + self.token[:10]
        cookie_value = secrets.randbelow(20_000_000) + 1
        with tempfile.TemporaryDirectory(prefix="origin-plot-") as temp:
            directory = Path(temp)
            job = directory / "job.json"
            reply = directory / "reply.json"
            job.write_text(json.dumps({**params, "action": action, "scripts": str(skill_root() / "scripts"),
                                       "expected_pid": self.pid or (self.requested_pid if self.mode == "attach" else None),
                                       "cookie_name": cookie_name, "cookie_value": cookie_value}, allow_nan=False),
                           encoding="utf-8")
            launcher = directory / "launch.py"
            launcher.write_text("import runpy\nrunpy.run_path(%r)['run_job'](%r)\n" % (str(script), str(job)),
                                encoding="utf-8")
            await self.call("run_labtalk", script=f"{cookie_name}={cookie_value};")
            await self.call("run_labtalk", script=f'run -pyf "{launcher.as_posix()}";', confirm=True)
            for _ in range(40):
                if reply.exists():
                    break
                await asyncio.sleep(0.1)
            if not reply.is_file():
                raise RuntimeError("Origin did not return embedded Python evidence. Check the Origin Python installation.")
            envelope = json.loads(reply.read_text(encoding="utf-8"))
            if not envelope["ok"]:
                raise RuntimeError(envelope["error"])
            info = envelope["result"]
            live_pid = info["origin"]["pid"]
            if self.mode == "attach" and live_pid != self.requested_pid:
                raise RuntimeError("Attached Origin PID differs from the requested visible window. Edit was refused.")
            if self.pid is not None and live_pid != self.pid:
                raise RuntimeError("Origin restarted during the session. Reconnect and inspect again.")
            self.pid = live_pid
            self.origin_executable = info["origin"].get("executable")
            self.automation_mode = bool(info["origin"].get("automation_mode"))
            return info

    async def standalone_export(self, project_path, graph_name, exports, timeout=180):
        if not self.origin_executable or not Path(self.origin_executable).is_file():
            raise RuntimeError("Origin executable path is unavailable for standalone export.")
        executable = Path(self.origin_executable)
        script = Path(__file__).with_name("embedded.py")
        with tempfile.TemporaryDirectory(prefix="origin-plot-export-", ignore_cleanup_errors=True) as temp:
            directory = Path(temp)
            job = directory / "export-job.json"
            reply = directory / "export-reply.json"
            job.write_text(json.dumps({"project_path": str(project_path), "graph_name": graph_name,
                                       "exports": exports}, allow_nan=False, ensure_ascii=False),
                           encoding="utf-8")
            launcher = directory / "launch.py"
            launcher.write_text("import runpy\nrunpy.run_path(%r)['export_standalone'](%r)\n" % (str(script), str(job)),
                                encoding="utf-8")
            command = f'"{executable}" -hs -rs run -pyf "{launcher.as_posix()}";'
            kwargs = {"executable": str(executable), "cwd": str(executable.parent), "timeout": timeout, "check": True}
            if sys.platform == "win32":
                kwargs["startupinfo"] = subprocess.STARTUPINFO(
                    dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=subprocess.SW_HIDE
                )
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            await asyncio.to_thread(subprocess.run, command, **kwargs)
            if not reply.is_file():
                raise RuntimeError("Standalone Origin did not return an export report.")
            envelope = json.loads(reply.read_text(encoding="utf-8"))
            if not envelope["ok"]:
                raise RuntimeError(f"standalone_export: {envelope['error']}")
            return envelope["result"]
