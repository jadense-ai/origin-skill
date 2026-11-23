import asyncio
import csv
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from openpyxl import Workbook
from PIL import Image

from origin_plot_backend.data import read_table
from origin_plot_backend.bridge import skill_root
from origin_plot_backend.embedded import _apply_changes, _bin_info, _bound_data, _template, inspect_graph
from origin_plot_backend.runtime import Runtime, _compare_readback, _submission_tiff, artifact, formats_list
from origin_plot_backend.server import application


class HistogramLayer:
    def __init__(self):
        self.values = {"plot1.boxchart.binBegin":0.0, "plot1.boxchart.binEnd":10.0,
                       "plot1.boxchart.binSize":2.0, "plot1.pid":219}
        self.obj = self
    def LT_execute(self, command):
        return command == "doc -uw;"
    def plot_list(self):
        return [object()]
    def get_int(self, p):
        return self.values[p]
    def get_float(self, p):
        return self.values[p]
    def set_float(self, p, v):
        self.values[p] = v
    def axis(self, _):
        return object()


class BackendChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_tabular_sources_and_quoted_headers(self):
        rows = [["id","a,b"], ["0007","5"], ["0008","7"]]
        csvfile = self.root / "in.csv"
        with csvfile.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
        self.assertEqual(read_table(csvfile)[0], {"id":"0007", "a,b":"5"})
        tsv = self.root / "in.tsv"
        tsv.write_text("id\tx\n0007\t5\n", encoding="utf-8")
        self.assertEqual(read_table(tsv), [{"id":"0007","x":"5"}])
        xlsx = self.root / "in.xlsx"
        book = Workbook()
        sheet = book.active
        for row in rows:
            sheet.append(row)
        book.save(xlsx)
        book.close()
        self.assertEqual(read_table(csvfile), read_table(xlsx, sheet.title))
        tsv.write_text("x\tx\n1\t2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique"):
            read_table(tsv)

    def test_histogram_read_and_targeted_write(self):
        layer = HistogramLayer()
        self.assertEqual(_bin_info(layer,1)["bin_count"],5)
        self.assertEqual(_apply_changes([layer], {"bin_count":10})["histogram"]["bin_width"],1)
        self.assertEqual(_apply_changes([layer], {"bin_width":2})["histogram"]["bin_count"],5)
        layer.values["plot1.pid"] = 203
        with self.assertRaisesRegex(ValueError,"219"):
            _apply_changes([layer], {"bin_width":4})

    def test_unavailable_or_changed_readback_is_not_verified(self):
        _compare_readback({"value":2.0},{"value":2.000000001})
        with self.assertRaisesRegex(RuntimeError,"changed"):
            _compare_readback({"bin_width":1.0},{"bin_width":0.0})
        with self.assertRaisesRegex(RuntimeError,"Missing"):
            _compare_readback({"data_source":"Book1_B"}, {})

    def test_reopened_panel_and_different_values_in_same_named_source(self):
        source = SimpleNamespace(GetDatasetName=lambda: "Book1_B")
        values = [13., 21., 34.]
        sheet = SimpleNamespace(cols=1, obj=[source], to_list=lambda i: values)
        plot = SimpleNamespace(lt_range=lambda:"[Graph1]1!1", obj=source)
        op = SimpleNamespace(get_lt_str=lambda k: "Book1_B" if k == "opbDataName" else "[Book1]Sheet1!",
                             find_sheet=lambda kind, rg:sheet)
        label = SimpleNamespace(text=r"\b(A)", get_float=lambda prop:10)
        layer = HistogramLayer()
        layer.plot_list = lambda:[plot]
        layer.LT_execute = lambda _:True
        layer.label = lambda name: label if name == "OriginPlotPanel" else None
        class Graph(list):
            name = "Graph1"
            lname = "Sample"
        graph = Graph([layer])
        info = inspect_graph(op, graph)["layers"][0]
        self.assertEqual(info["panel"], {"text":r"\b(A)", "fsize":10})
        a = info["plots"][0]["data_roles"]["y"]
        self.assertEqual(a["rows"], 3)
        values[1] += 1
        b = _bound_data(op, layer, plot, "y", {})
        self.assertEqual(a["name"], b["name"])
        self.assertNotEqual(a["content_sha256"], b["content_sha256"])

    def test_official_template_preserves_native_type_and_provenance(self):
        template = self.root / "official.otpu"
        job = {"records":[{"x":1,"y":2}], "x":"x", "y":"y", "template_path":str(template)}
        graph_type = 201
        for reported, native, required, error in (
            ("other.otpu", graph_type, None, "reports template"),
            (str(template), 213, None, "one XY series"),
            (str(template), graph_type, "line", "Requested line"),
            (str(template), graph_type, None, None),
            (str(template), graph_type, "scatter", None),
        ):
            with self.subTest(reported=reported, pid=native, requested=required):
                layer, plot, op, sheet = Mock(), Mock(), Mock(), Mock()
                slots = []
                layer.plot_list.side_effect = lambda:list(slots)
                layer.add_plot.side_effect = lambda *args, **kw: slots.append(plot)
                layer.get_int.return_value = native
                class Graph(list):
                    activate = Mock()
                op.new_graph.return_value = Graph([layer])
                op.get_lt_str.return_value = reported
                op.new_sheet.return_value = sheet
                sheet.obj = [SimpleNamespace(GetDatasetName=lambda:"X"),
                             SimpleNamespace(GetDatasetName=lambda:"Y")]
                with patch.object(sys, "path", [str(skill_root() / "scripts"), *sys.path]), patch(
                    "origin_plot_backend.embedded._bound_data",
                    side_effect=lambda op, layer, plot, role, cache: {"name":role.upper()},
                ):
                    if error:
                        with self.assertRaisesRegex((ValueError, RuntimeError), error):
                            _template(op, {**job, "plot_type":required})
                    else:
                        proof = _template(op, {**job, "plot_type":required})["template_binding"]
                        self.assertEqual(proof["plot_type_id"], graph_type)
                        self.assertEqual(proof["native_template_source"], str(template))
                if reported == str(template):
                    layer.add_plot.assert_called_once_with(sheet, coly=1, colx=0, type="?")
                else:
                    op.new_sheet.assert_not_called()

    def test_published_tiff_encodes_measured_width_without_resampling(self):
        p = self.root / "Fig1.tif"
        Image.new("RGBA",(600,300),(22,33,44,127)).save(p)
        _submission_tiff(p, 25.4)
        self.assertEqual(artifact(p)["pixels"],[600,300])
        with Image.open(p) as im:
            self.assertEqual(im.mode,"RGB")
            self.assertEqual(im.info["compression"],"tiff_lzw")
            self.assertAlmostEqual(im.info["dpi"][0],600)
        self.assertEqual(formats_list(["TIFF","tif","pdf"]),["tif","pdf"])


class RuntimeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_attach_writes_snapshots_without_saveas_or_reopen(self):
        b = AsyncMock()
        b.mode = "attach"
        state = {"origin":{"pid":9,"project_name":"UserProject"}, "graph":"Graph1", "layers":[]}
        async def embedded(action, **args):
            if action == "snapshot":
                Path(args["output_path"]).write_bytes(b"fixture")
            if action == "edit":
                self.assertEqual(args["expected_state"], state)
            return state
        async def upstream(action, **args):
            self.assertEqual(action, "export_graph")
            Image.new("RGB", (20, 10)).save(args["file_path"])
        b.embedded.side_effect = embedded
        b.call.side_effect = upstream
        rt = Runtime(bridge=b)
        try:
            inspected = await rt.inspect("Graph1")
            with tempfile.TemporaryDirectory() as out:
                result = await rt.edit("Graph1", out, {"x_title":"seconds"}, formats=["png"],
                                       session_token=inspected["session_token"])
                folder = Path(result["run_dir"])
                self.assertTrue((folder/"before-edit.opju").exists())
                self.assertTrue((folder/"figure.opju").exists())
                self.assertEqual(result["reopen"]["status"],"not_requested")
        finally:
            await rt.close()

    async def test_attach_edits_require_named_fresh_inspection(self):
        b = AsyncMock()
        b.mode = "attach"
        b.embedded.return_value = {"graph":"Graph1","layers":[],"origin":{"pid":42}}
        rt = Runtime(bridge=b)
        try:
            with self.assertRaisesRegex(ValueError,"Inspect"):
                await rt.edit("Graph1", ".", changes={"x_title":"t"})
            result = await rt.inspect("Graph1")
            self.assertEqual(rt._attach_write(result["session_token"], "Graph1")["origin"]["pid"], 42)
            with self.assertRaises(ValueError):
                rt._attach_write(result["session_token"], "Graph2")
            with self.assertRaises(ValueError):
                await rt._open_copy("x.opju")
        finally:
            await rt.close()

    async def test_server_exposes_real_schemas_and_dispatches_calls(self):
        rt = Runtime()
        try:
            app = application(rt)
            tools = {tool.name:tool for tool in await app.list_tools()}
            self.assertIn("origin_plot_render_template", tools)
            self.assertIn("template_path", tools["origin_plot_render"].inputSchema["properties"])
            self.assertEqual(len(tools), 8)
            result = await app.call_tool("origin_plot_doctor", {"live":False})
            self.assertIn("origin_com_registered", str(result))
        finally:
            await rt.close()
