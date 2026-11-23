"""Guarded plot workflows and evidence from actually written files."""
import asyncio
from contextlib import contextmanager
import hashlib
import importlib
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
import secrets

from .bridge import Bridge, skill_root
from .data import read_bindings, read_table
from .embedded import XY_TEMPLATE_TYPES, _hex_color

RASTER = {"png", "jpg", "tif", "bmp"}
VECTOR = {"pdf", "eps", "emf"}
LOGGER = logging.getLogger(__name__)


def artifact(path):
    p = Path(path)
    if not p.is_file() or not p.stat().st_size:
        raise RuntimeError(f"Missing or empty artifact: {p}")
    with p.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    info = {"path": str(p.resolve()), "bytes": p.stat().st_size, "sha256": digest}
    ext = p.suffix.lower()[1:]
    if ext in RASTER:
        from PIL import Image
        with p.open("rb") as handle, Image.open(handle) as image:
            if image.format != {"jpg":"JPEG", "tif":"TIFF"}.get(ext, ext.upper()):
                raise RuntimeError(f"Unexpected raster file signature: {p}")
            info["pixels"] = list(image.size)
            dpi = image.info.get("dpi")
            if dpi and all(float(n) > 0 for n in dpi):
                info["dpi"] = list(map(float, dpi))
            image.verify()
    elif ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p), strict=True)
        if not len(reader.pages):
            raise RuntimeError("Empty PDF.")
        page = reader.pages[0]
        info["page_text_detected"] = bool((page.extract_text() or "").strip())
        info["single_page"] = len(reader.pages) == 1
    elif ext in {"eps", "emf"}:
        with p.open("rb") as handle:
            prefix = handle.read(44)
        if (ext == "eps" and not (prefix.startswith(b"%!PS") or prefix.startswith(bytes.fromhex("c5d0d3c6")))) or (
            ext == "emf" and not (prefix[:4] == bytes.fromhex("01000000") and prefix[40:44] == b" EMF")
        ):
            raise RuntimeError(f"Unexpected vector file signature: {p}")
    return info


def formats_list(formats):
    aliases = {"tiff":"tif", "jpeg":"jpg"}
    items = list(dict.fromkeys(aliases.get(k.lower(), k.lower()) for k in (formats if formats is not None else ["png", "pdf"])))
    if not items or any(k not in RASTER | VECTOR for k in items):
        raise ValueError("Use png, jpg, tif, bmp, pdf, eps or emf.")
    return items


@contextmanager
def output_run(output_dir):
    # Each request gets an exclusive run directory, so agent retries never replace a previous figure.
    parent = Path(output_dir).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    run = parent / ("run-" + uuid.uuid4().hex)
    run.mkdir()
    try:
        yield run
    except BaseException:
        if not any(run.iterdir()):
            run.rmdir()
        raise


def _journal_function(method, *args):
    scripts = str(skill_root() / "scripts")
    sys.path.insert(0, scripts)
    try:
        return getattr(importlib.import_module("journals"), method)(*args)
    finally:
        sys.path.remove(scripts)


def _journal_validate(journal, graph_result, exports):
    return ({key: _journal_function("check_export", journal, item["path"], graph_result)
             for key, item in exports.items() if item["purpose"] != "preview"} if journal else None)


def _submission_tiff(path, mm):
    """Encode the actual exported pixels losslessly at their measured Origin paper width."""
    from PIL import Image
    if not mm or not math.isfinite(mm) or mm <= 0:
        raise RuntimeError("A measured native page width is required for a submission TIFF.")
    tmp = path.with_suffix(".tmp.tif")
    with path.open("rb") as handle, Image.open(handle) as im:
        if im.n_frames != 1:
            raise ValueError("Expected a single-page Origin TIFF.")
        dpi = im.width * 25.4 / mm
        if im.mode in ("1", "L"):
            output = im.convert("L")
        else:
            rgba = im.convert("RGBA")
            output = Image.new("RGB", im.size, "white")
            output.paste(rgba, mask=rgba.getchannel("A"))
            rgba.close()
        output.save(tmp, format="TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
        output.close()
    os.replace(tmp, path)


def _compare_readback(before, after, path="graph"):
    if isinstance(before, dict) and isinstance(after, dict):
        for k in before:
            if k in after:
                _compare_readback(before[k], after[k], path + "." + k)
            else:
                raise RuntimeError(f"Missing native property after reopening: {path}.{k}")
        return
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for i, (a, b) in enumerate(zip(before, after)):
            _compare_readback(a, b, f"{path}[{i}]")
        return
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if math.isclose(before, after, rel_tol=1e-6, abs_tol=1e-7):
            return
    elif before == after:
        return
    raise RuntimeError(f"Origin property changed after reopening: {path}, {before!r} -> {after!r}")


def _compare_graph(before, after):
    for field in ("graph", "long_name", "layer_count", "plot_counts", "page"):
        _compare_readback(before[field], after[field], field)
    grouped = set(before.get("automatic_group_layers", []))
    for index, (old, new) in enumerate(zip(before["layers"], after["layers"], strict=True), 1):
        if index in grouped:
            # Origin resolves the increment lists for newly grouped plots on load.
            # Verify the data/topology and check any explicit style edits separately.
            calculated = {"color", "fill_color", "line_style", "symbol_kind"}
            old = {**old, "plots": [{k: v for k, v in p.items() if k not in calculated} for p in old["plots"]]}
        _compare_readback(old, new, f"layers[{index - 1}]")

    changes = before.get("changes_verified")
    if not changes:
        return
    target = before["changes_target"]
    layer = after["layers"][target["layer"] - 1]
    for key, expected in changes.items():
        if key in after["page"]:
            actual = after["page"][key]
        elif key == "long_name":
            actual = after["long_name"]
        elif key == "legend_text":
            actual = layer[key]
        elif key[:2] in ("x_", "y_"):
            axis = layer["axes"][key[0]]
            actual = [axis["from"], axis["to"]] if key.endswith("_range") else axis[key[2:]]
        else:
            plot = layer["plots"][target["plot"] - 1]
            actual = plot.get(key)
            if key == "color":
                actual = _hex_color(actual)
        _compare_readback(expected, actual, f"changes.{key}")


class Runtime:
    def __init__(self, mode="isolated", target_pid=None, bridge=None):
        self.bridge = bridge if bridge is not None else Bridge(mode, target_pid)
        self.lock = asyncio.Lock()
        self.private = tempfile.TemporaryDirectory(prefix="origin-plot-projects-")
        self._private_project = False
        self.inspected = {}

    async def close(self):
        try:
            if self._private_project:
                try:
                    async with asyncio.timeout(5):
                        await self._new_project()
                except Exception as exc:
                    LOGGER.warning("Could not release the isolated Origin project before disconnecting: %s", exc)
        finally:
            try:
                await self.bridge.close()
            finally:
                await self._cleanup_private()

    async def _cleanup_private(self):
        for delay in (0, 0.1, 0.4, 1.5, 3):
            if delay:
                await asyncio.sleep(delay)
            try:
                self.private.cleanup()
                return
            except PermissionError as exc:
                if getattr(exc, "winerror", None) not in {32, 33}:
                    raise
        LOGGER.warning("Origin still holds temporary project files in %s", self.private.name)

    async def doctor(self, live=False):
        health = self.bridge.diagnostics()
        if live:
            if not health["ready_for_live_probe"]:
                return {**health, "status": "blocked"}
            probe = await self.bridge.embedded("doctor")
            return {**health, **probe, "live_verified": True, "status":"verified",
                    "session_token": self.bridge.token}
        return {**health, "status": "configured" if health["ready_for_live_probe"] else "blocked"}

    def _isolate(self):
        if self.bridge.mode != "isolated":
            raise ValueError("This operation creates or loads a project and requires an isolated session.")

    async def _replace_isolated_project(self, operation, **arguments):
        self._isolate()
        # Recalculation can mark a saved graph as modified between two COM calls.
        await self.bridge.call("run_labtalk", script="doc -ss 1; doc -s;", confirm=True)
        try:
            return await self.bridge.call(operation, **arguments)
        finally:
            await self.bridge.call("run_labtalk", script="doc -ss 0;", confirm=True)

    async def _new_project(self):
        await self._replace_isolated_project("new_project")
        self._private_project = False

    def _attach_write(self, token, graph_name):
        if self.bridge.mode == "attach":
            saved = self.inspected.get(token)
            if not saved or saved.get("graph") != graph_name:
                raise ValueError("Inspect the named live graph first. Pass the session_token from that exact inspection.")
            return saved
        return None

    async def _open_copy(self, path):
        if not path:
            return
        self._isolate()
        source = Path(path).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".opj", ".opju"}:
            raise ValueError("Choose an existing Origin OPJ/OPJU project.")
        copy = Path(self.private.name) / (uuid.uuid4().hex + source.suffix)
        shutil.copy2(source, copy)
        await self.bridge.embedded("doctor")
        self._private_project = True
        await self._replace_isolated_project("load_project", file_path=str(copy))

    async def inspect(self, graph_name="", project_path=None, template_path=None):
        if template_path is not None:
            self._isolate()
            if project_path or graph_name:
                raise ValueError("Inspect a template separately from a project or named graph.")
            return await self.bridge.embedded("inspect-template", template_path=str(self._template_path(template_path)))
        await self._open_copy(project_path)
        data = await self.bridge.embedded("inspect", graph_name=graph_name)
        token = secrets.token_hex(16)
        if self.bridge.mode == "attach" and graph_name:
            self.inspected = {token: data}
        return {**data, "session_token": token, "mode": self.bridge.mode}

    async def _exports(self, run, graph_name, formats, width, journal=None, graph=None):
        profile = _journal_function("load_profile", journal) if journal else {}
        use_plos = profile.get("id") == "plos-one"
        is_default = formats is None
        if width is None:
            mm = (graph or {}).get("page", {}).get("width_mm")
            width = math.floor(mm * profile["defaults"]["dpi"] / 25.4) if use_plos and mm else 1800
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise ValueError("width must be a positive pixel count.")
        if is_default and journal:
            formats = ["png", profile["defaults"]["output_format"].lower()]
        out = {}
        for fmt in formats_list(formats):
            target = run / (f"Fig1.{fmt}" if use_plos and fmt == "tif" else f"figure.{fmt}")
            await self.bridge.call("export_graph", graph_name=graph_name, file_path=str(target),
                                   format=fmt, width=width if fmt in RASTER else 0)
            if use_plos and fmt == "tif":
                _submission_tiff(target, graph["page"]["width_mm"])
            out[fmt] = artifact(target)
            out[fmt]["purpose"] = "preview" if is_default and fmt == "png" else "figure"
        return out

    async def _finish(self, run, graph, formats, width, journal, reopen):
        graph_name = graph["graph"]
        project = run / "figure.opju"
        if self.bridge.mode == "attach":
            await self.bridge.embedded("snapshot", output_path=str(project))
        else:
            await self.bridge.call("save_project", file_path=str(project))
        project_evidence = artifact(project)
        check = {"status": "not_requested"}
        if reopen:
            self._isolate()
            await self._open_copy(project)
            read = await self.bridge.embedded("inspect", graph_name=graph_name, verify_histograms=True)
            if not read["layers"]:
                raise RuntimeError("Reopened OPJU has no native graph layers.")
            _compare_graph(graph, read)
            binding = graph.get("data_binding") or graph.get("template_binding") or {}
            for mapped in binding.get("bindings", ()):
                if isinstance(mapped, dict) and "bin_counts" in mapped:
                    counts = read["layers"][mapped["layer"] - 1]["plots"][mapped["native_plot"] - 1]["histogram_counts"]
                    _compare_readback(mapped["bin_counts"], counts, "histogram_counts")
            if graph.get("recipe_id") == "histogram":
                _compare_readback(graph["expected"]["science"]["bin_counts"],
                                  read["layers"][0]["plots"][0]["histogram_counts"], "histogram_counts")
            check = {"status": "verified", "readback":read}
        outputs = await self._exports(run, graph_name, formats, width, journal, check.get("readback", graph))
        evidence = {"status":"rendered", "run_dir":str(run), "project":project_evidence, "exports":outputs,
                    "inspection":graph, "reopen":check, "journal_check":_journal_validate(journal, graph, outputs)}
        (run / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        return evidence

    async def render(self, recipe_id, data_path, output_dir, columns=None, options=None, title=None,
                     sheet=None, journal=None, journal_options=None, formats=None, width=None, reopen=True,
                     template_path=None):
        self._isolate()
        formats_list(formats)
        if not isinstance(recipe_id, str) or not recipe_id.isascii() or not recipe_id.replace("-","").isalnum():
            raise ValueError("Invalid recipe ID.")
        recipe = skill_root() / "assets" / "recipes" / recipe_id / "recipe.json"
        if not recipe.is_file():
            raise ValueError(f"Unknown recipe: {recipe_id}")
        rows = read_table(data_path, sheet)
        template = None
        if template_path:
            template = Path(template_path).expanduser().resolve(strict=True)
            if template.suffix.lower() not in {".otp", ".otpu"}:
                raise ValueError("Recipe template reuse requires an OTP/OTPU file.")
        with output_run(output_dir) as run:
            await self.bridge.embedded("doctor")
            await self._new_project()
            graph = await self.bridge.embedded("render", recipe_id=recipe_id, records=rows, columns=columns,
                                              options=options, title=title, journal=journal,
                                              journal_options=journal_options, template_path=str(template) if template else None)
            if template:
                graph["template_source"] = artifact(template)
            return await self._finish(run, graph, formats, width, journal, reopen)

    def _template_path(self, template_path):
        template = Path(template_path).expanduser()
        if not template.is_absolute() and os.getenv("ORIGIN_PLOT_OFFICIAL_DIR"):
            template = Path(os.environ["ORIGIN_PLOT_OFFICIAL_DIR"]) / template
        template = template.resolve(strict=True)
        if template.suffix.lower() not in {".otp",".otpu"}:
            raise ValueError("Template binding requires an OTP/OTPU file. Inspect an OPJU as a project.")
        return template

    async def render_template(self, template_path, data_path, output_dir, x=None, y=None, plot_type=None, title=None,
                              sheet=None, journal=None, journal_options=None, formats=None, width=None, reopen=True,
                              bindings=None, changes=None):
        self._isolate()
        template = self._template_path(template_path)
        job = {}
        if bindings is None:
            if (plot_type not in (None, "auto") and plot_type not in XY_TEMPLATE_TYPES) or not x or not y or x == y:
                raise ValueError("Choose distinct X/Y columns and a supported single-layer XY template plot type.")
            job.update(records=read_table(data_path, sheet), x=x, y=y, plot_type=plot_type)
        else:
            if x is not None or y is not None or plot_type is not None:
                raise ValueError("Specify either bindings or legacy X/Y arguments.")
            job["binding_job"] = read_bindings(data_path, sheet, bindings)
        formats_list(formats)
        with output_run(output_dir) as run:
            await self.bridge.embedded("doctor")
            await self._new_project()
            graph = await self.bridge.embedded("template", template_path=str(template), title=title,
                                              journal=journal, journal_options=journal_options, changes=changes, **job)
            graph["template_source"] = artifact(template)
            return await self._finish(run, graph, formats, width, journal, reopen)

    async def edit(self, graph_name, output_dir, changes=None, project_path=None, journal=None,
                   journal_options=None, formats=None, width=None, session_token=None, reopen=None,
                   bindings=None, data_path=None, sheet=None):
        binding_job = None
        if bindings is not None:
            self._isolate()
            if not project_path:
                raise ValueError("Data replacement requires the path of an existing OPJ/OPJU.")
            binding_job = read_bindings(data_path, sheet, bindings)
        elif data_path is not None or sheet is not None:
            raise ValueError("Provide bindings to select the plots and data columns to replace.")
        expected_state = self._attach_write(session_token, graph_name)
        if not graph_name or (not changes and not journal and binding_job is None):
            raise ValueError("Specify a graph name and changes, a journal profile, or data bindings.")
        if reopen is None:
            reopen = self.bridge.mode == "isolated"
        if reopen:
            self._isolate()
        formats_list(formats)
        await self._open_copy(project_path)
        with output_run(output_dir) as run:
            before = None
            if self.bridge.mode == "attach":
                before = run / "before-edit.opju"
                await self.bridge.embedded("snapshot", output_path=str(before))
                artifact(before)
            try:
                graph = await self.bridge.embedded("edit", graph_name=graph_name, changes=changes,
                                                  journal=journal, journal_options=journal_options,
                                                  expected_state=expected_state, binding_job=binding_job)
                return await self._finish(run, graph, formats, width, journal, reopen)
            except Exception as exc:
                if before:
                    raise RuntimeError(f"Live edit did not complete. Pre-edit project snapshot: {before}. {exc}") from exc
                raise

    async def export(self, graph_name, output_dir, project_path=None, formats=None, width=1800):
        if not graph_name:
            raise ValueError("An explicit graph name is required.")
        info = await self.inspect(graph_name, project_path)
        with output_run(output_dir) as run:
            out = await self._exports(run, graph_name, formats, width)
            return {"status":"exported", "run_dir":str(run), "inspection":info, "exports":out}

    async def save_template(self, graph_name, output_dir, project_path=None, old_format=False):
        if not graph_name:
            raise ValueError("An explicit graph name is required.")
        info = await self.inspect(graph_name, project_path)
        with output_run(output_dir) as run:
            path = run / ("graph.otp" if old_format else "graph.otpu")
            await self.bridge.call("save_graph_template", graph_name=graph_name, file_path=str(path), old_format=old_format)
            return {"status":"saved_template", "template":artifact(path), "inspection":info}

    async def reopen(self, project_path, graph_name=""):
        if not project_path:
            raise ValueError("Provide an OPJU/OPJ file to reopen.")
        return {"status":"reopened", "inspection":await self.inspect(graph_name, project_path)}
