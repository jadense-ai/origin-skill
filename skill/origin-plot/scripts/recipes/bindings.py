"""Evidence for the actual Origin plot, beyond a successful save or export."""

from hashlib import sha256
import os
from pathlib import Path

from .model import RecipeError


def template_file(path):
    if path is None:
        return None, None
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file() or resolved.suffix.lower() not in {".otp", ".otpu"} or not resolved.stat().st_size:
        raise RecipeError("Expected a non-empty native .otp or .otpu file")
    return resolved, sha256(resolved.read_bytes()).hexdigest()


def template_origin(op, graph, supplied):
    graph.activate()
    if not op.lt_exec('string __oprec_template_source$=page.info.system.source.template$;'):
        raise RuntimeError("Origin did not identify the source template of the new graph page")
    reported = str(op.get_lt_str("__oprec_template_source") or "").strip()
    if not reported or os.path.normcase(os.path.normpath(reported)) != os.path.normcase(str(supplied)):
        raise RuntimeError(f"New graph reports template {reported!r}, expected {str(supplied)!r}")
    return reported


def plot_id(layer, plot):
    return int(layer.get_int(f"plot{plot.index() + 1}.pid"))


def dataset_name(op, layer, graph_range, role, expected_range):
    """Compare the native worksheet/matrix range identity of an actual plot."""
    if role not in {"x", "y", "z"}:
        raise ValueError("Unsupported range designation")
    command = (
        'string __oprec_actual$="";string __oprec_expected$="";'
        f"range -w{role} __oprec_data={graph_range};"
        f"range __oprec_source={expected_range};"
        "__oprec_actual$=nameof(__oprec_data)$;"
        "__oprec_expected$=nameof(__oprec_source)$;"
    )
    if not layer.obj.LT_execute(command):
        raise RuntimeError(f"Origin could not inspect the {role.upper()} source")
    actual = str(op.get_lt_str("__oprec_actual") or "")
    expected = str(op.get_lt_str("__oprec_expected") or "")
    if not actual or not expected or actual != expected:
        raise RuntimeError(f"Origin {role.upper()} source mismatch: {actual!r} / {expected!r}")
    return actual


def check_xy(op, layer, plot, mark, sheet, recipe_id):
    expected_pids = {
        "line": (200,), "reference": (200,), "line-symbol": (202,), "scatter": (201,),
        "template": ((215, 216) if recipe_id == "likert" else (203, 213)),
    }
    pid = plot_id(layer, plot)
    if pid not in expected_pids[mark["kind"]]:
        raise RuntimeError(f"Unexpected native plot type {pid} for {mark['kind']}")
    rg = plot.lt_range()
    result = {"plot_range": rg, "pid": pid}
    for axis in ("x", "y"):
        expected = f"{sheet.lt_range(False)}!col({mark[axis] + 1})"
        result[axis] = dataset_name(op, layer, rg, axis, expected)
    return result
