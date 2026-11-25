"""Draw and verify the README gallery in an isolated Origin session."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import origin_plot_backend.bridge as backend_bridge
from origin_plot_backend.runtime import Runtime, output_run

from showcase_advanced import ADVANCED, VALUE_RGB, interpolate_color, write_advanced_inputs
from showcase_data import AXIS_TITLES, write_inputs
from showcase_layout import compose


ROOT = Path(__file__).resolve().parents[1]
TITLES = {
    "shap-summary": "SHAP feature attribution",
    "xps-components": "XPS C 1s components",
    "heatmap": "30 × 30 response matrix",
    "box-raw": "Grouped box plots with observations",
    "multi-panel": "Pulse and recovery",
    "xrd-stack": "X-ray diffraction",
    "eis-nyquist": "Nyquist impedance",
    "violin": "Response distributions",
    "histogram": "Latency modes",
    "ecdf": "Recovery-time ECDF",
    "dose-response": "Dose–response curves",
    "grouped-column": "Yield by material",
    "event-study": "Changes around an event",
    "coefficient-interval": "Model coefficients",
    "multi-line": "Spectral components",
    "scatter": "Leaf morphology",
    "dual-y": "Temperature and humidity",
    "likert": "Survey responses",
}
OPTIONS = {"histogram": {"bins": 21}, "xrd-stack": {"offset": 0.75}}
PALETTES = {"heatmap": "Showcase Balance.pal", "shap-summary": "Showcase Feature Values.pal"}
BALANCE = ((29, 79, 125), (103, 170, 202), (249, 248, 244), (213, 139, 98), (134, 50, 46))
PREVIEW_WIDTH = 1800


def write_palette(path, stops):
    # Origin accepts a RIFF PAL with one RGBA entry per table index.
    entries = bytearray()
    for i in range(256):
        entries.extend(interpolate_color(stops, i / 255))
        entries.append(0)
    payload = struct.pack("<HH", 0x300, 256) + entries
    path.write_bytes(b"RIFF" + struct.pack("<I", len(payload) + 12) + b"PAL data"
                     + struct.pack("<I", len(payload)) + payload)


class ShowcaseBridge(backend_bridge.Bridge):
    """Apply repository-only presentation styling before the normal save and readback."""

    def __init__(self, inputs):
        super().__init__(mode="isolated")
        self.inputs = inputs

    async def embedded(self, action, **params):
        info = await super().embedded(action, **params)
        if action != "render":
            return info
        recipe = params["recipe_id"]
        await self.showcase_job(recipe, graph=info["graph"], axes=AXIS_TITLES[recipe])
        return {**info, **await super().embedded("inspect", graph_name=info["graph"])}

    async def showcase_job(self, recipe, **params):
        with TemporaryDirectory(prefix="origin-showcase-style-", ignore_cleanup_errors=True) as temp:
            directory = Path(temp)
            job = {"pid": self.pid, "recipe": recipe, "source": str(self.inputs / f"{recipe}.csv"),
                   "embedded": str(Path(backend_bridge.__file__).with_name("embedded.py")),
                   "scripts": str(ROOT / "skill/origin-plot/scripts"), **params}
            if recipe in PALETTES:
                job["palette"] = str(self.inputs.parent / PALETTES[recipe])

            path = directory / "style-job.json"
            path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            launcher = directory / "launch.py"
            style = Path(__file__).with_name("showcase_origin.py")
            launcher.write_text(f"import runpy, sys\nsys.path.insert(0, {str(style.parent)!r})\n"
                                f"runpy.run_path({str(style)!r})['run']({str(path)!r})\n", encoding="utf-8")
            await self.call("run_labtalk", script=f'run -pyf "{launcher.as_posix()}";', confirm=True)
            reply = directory / "style-reply.json"
            for _ in range(40):
                if reply.is_file():
                    break
                await asyncio.sleep(0.1)
            if not reply.is_file():
                raise RuntimeError(f"Origin did not report showcase styling for {recipe}")
            result = json.loads(reply.read_text(encoding="utf-8"))
            if not result["ok"]:
                raise RuntimeError(result["error"])
            return result


async def render(work, ids=TITLES):
    inputs = work / "inputs"
    write_inputs(inputs)
    write_advanced_inputs(inputs)
    write_palette(work / PALETTES["heatmap"], BALANCE)
    write_palette(work / PALETTES["shap-summary"], VALUE_RGB)
    os.environ["ORIGIN_PLOT_SKILL_ROOT"] = str(ROOT / "skill/origin-plot")
    runtime = Runtime(bridge=ShowcaseBridge(inputs))
    reports = {}
    try:
        live = await runtime.doctor(live=True)
        if not live.get("live_verified"):
            raise RuntimeError(f"Origin failed its live probe: {live.get('reasons')}")
        print(f"Origin {live['origin']['origin_version']} live probe passed", flush=True)
        for recipe in ids:
            target = work / "runs" / recipe
            if recipe in ADVANCED:
                with output_run(target) as run:
                    await runtime._new_project()
                    native = await runtime.bridge.showcase_job(recipe, title=TITLES[recipe])
                    graph = await runtime.bridge.embedded("inspect", graph_name=native["graph"])
                    result = await runtime._finish(run, graph, ["png"], PREVIEW_WIDTH, None, reopen=True)
            else:
                result = await runtime.render(
                    recipe, inputs / f"{recipe}.csv", target, title=TITLES[recipe],
                    options=OPTIONS.get(recipe), formats=["png"], width=PREVIEW_WIDTH,
                )
            reports[recipe] = result
            print(f"{recipe}: {result['reopen']['status']} ({result['inspection']['layer_count']} layers)", flush=True)
    finally:
        await runtime.close()
    return reports


def publish(output, work, reports):
    plots = output / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    verification = {}
    with ZipFile(output / "projects.zip", "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for palette in PALETTES.values():
            archive.write(work / palette, f"palettes/{palette}")
        for recipe, report in reports.items():
            export = report["exports"]["png"]
            project = report["project"]
            inspection = report["inspection"]
            preview = plots / f"{recipe}.png"
            project_name = f"projects/{recipe}.opju"
            input_name = f"inputs/{recipe}.csv"
            shutil.copyfile(export["path"], preview)
            archive.write(project["path"], project_name)
            archive.write(work / input_name, input_name)
            verification[recipe] = {
                "project": project_name, "project_sha256": project["sha256"], "input": input_name,
                "preview": f"plots/{recipe}.png", "preview_sha256": export["sha256"],
                "native_plot_types": [[p["plot_type_id"] for p in layer["plots"]] for layer in inspection["layers"]],
                "axis_titles": [[layer["axes"][axis]["title"] for axis in ("x", "y")]
                                for layer in inspection["layers"]],
                "origin_version": inspection["origin"]["origin_version"],
                "reopen": report["reopen"]["status"],
                "preview_export": "standalone Origin",
            }
        archive.writestr("verification.json", json.dumps(verification, ensure_ascii=False, indent=2) + "\n")
    compose([(TITLES[key], plots / f"{key}.png") for key in TITLES],
            output / "preview.webp", featured_output=output / "featured.webp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/showcase")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="origin-showcase-") as temp:
        work = Path(temp)
        reports = asyncio.run(render(work))
        publish(args.output.resolve(), work, reports)


if __name__ == "__main__":
    main()
