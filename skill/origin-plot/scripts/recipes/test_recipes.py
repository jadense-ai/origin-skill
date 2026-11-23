"""Offline scientific tests. These tests never start Origin or create graphical artifacts."""

import csv
import json
import math
import unittest
from pathlib import Path
from unittest.mock import Mock

from .bindings import check_xy, dataset_name, template_origin
from .model import ASSETS, RecipeError
from .prepare import prepare


def demo(recipe_id, sample="a"):
    with (ASSETS / recipe_id / f"example-{sample}.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class RecipeContracts(unittest.TestCase):
    def test_all_registered_demos(self):
        registry = json.loads((ASSETS / "catalog.json").read_text(encoding="utf-8"))["recipes"]
        self.assertEqual(len(registry), 20)
        self.assertEqual(len({r["id"] for r in registry}), 20)
        self.assertEqual(sum(item["domain"] == "通用" for item in registry), 12)
        for registration in registry:
            recipe_id = registration["id"]
            info = json.loads((ASSETS / registration["file"]).read_text(encoding="utf-8"))
            self.assertEqual(len(info["examples"]), 2)
            for example in info["examples"]:
                with self.subTest(recipe=recipe_id, example=example["id"]):
                    rows = demo(recipe_id, example["id"])
                    p = prepare(recipe_id, rows)
                    self.assertEqual(len(rows), p.expected["source_row_count"])
                    self.assertEqual(example["expected"], p.expected)
                    self.assertGreater(sum(p.expected["min_plots"]), 0)
                    self.assertEqual(len(p.layers), 2 if recipe_id in ("multi-panel", "dual-y") else 1)
                    for layer in p.layers:
                        for mark in layer.marks:
                            data = p.tables[mark["table"]]
                            xs = data.columns[mark["x"]][1]
                            ys = data.columns[mark["y"]][1]
                            self.assertEqual(len(xs), len(ys))
                            self.assertTrue(all(math.isfinite(v) for v in xs + ys))

    def test_spreadsheet_header_mapping(self):
        p = prepare("multi-line", [{"Measure": "12", "Day": "3"}, {"Measure": "9", "Day": "1"}],
                    columns={"x": "Day", "y": "Measure"})
        self.assertEqual(p.tables[0].columns[0][1], [1., 3.])
        self.assertEqual(p.tables[0].columns[1][1], [9., 12.])

    def test_percent_and_diverging_stack(self):
        p = prepare("percent-stack", demo("percent-stack"))
        self.assertEqual(p.science["percentages"]["Mineral"], [50, 30, 45])
        lk = prepare("likert", demo("likert"))
        for i, total in enumerate(lk.science["totals"].values()):
            self.assertGreater(total, 0)
            parts = [s[i] for s in lk.science["signed_percentages"].values()]
            self.assertAlmostEqual(sum(map(abs, parts)), 100)
            self.assertEqual(parts[0], -parts[3])
        self.assertAlmostEqual(lk.science["signed_percentages"]["Strongly agree"][0], 100 * 14 / 60)

    def test_histogram_grouped_order_statistics(self):
        p = prepare("histogram", [{"value": v} for v in [0., .5, 1., 1.5, 2.]], options={"bins": 2})
        self.assertEqual(p.science["bin_counts"], [2, 3])
        self.assertGreater(p.science["bin_end"], 2.)
        p = prepare("histogram", [{"value": 1}] * 8)
        self.assertEqual(sum(p.science["bin_counts"]), 8)
        self.assertLess(p.science["bin_begin"], 1)
        self.assertGreater(p.science["bin_end"], 1)
        for id in ("box-raw", "violin"):
            p = prepare(id, demo(id))
            self.assertEqual(p.science["median"]["Batch A"], 9.5)
            self.assertEqual(p.science["group_sizes"]["Batch A"], 8)
        p = prepare("ecdf", [{"group":"A","value":v} for v in [2, 1, 1, 3]])
        self.assertEqual(p.tables[0].columns[0][1], [1, 1, 2, 2, 3, 3])
        self.assertEqual(p.tables[0].columns[1][1], [0, .5, .5, .75, .75, 1])

    def test_categorical_matrix_and_intervals(self):
        p = prepare("heatmap", demo("heatmap", "b"))
        self.assertEqual(p.native["matrix"], [[-2.5, -.5, .4, 1.7], [1.2, .1, -1., -1.9]])
        self.assertEqual(p.science["rows"], ["West", "East"])
        p = prepare("coefficient-interval", demo("coefficient-interval"))
        self.assertEqual(p.science["intervals"][0], ["Training", .07, .18, .33])
        self.assertEqual(p.tables[0].columns[0][1], [.07, .33])
        p = prepare("event-study", demo("event-study"))
        self.assertNotIn(-1, [v[0] for v in p.science["intervals"]])
        self.assertEqual(p.tables[0].columns[1][1], [-.12, .15])
        p = prepare("point-error", demo("point-error"))
        self.assertEqual(p.tables[0].columns[2][2], "E")
        self.assertEqual(p.tables[0].columns[2][1], [.4, .3, .6, .5])

    def test_subject_formulas(self):
        p = prepare("corpus-frequency", demo("corpus-frequency"))
        self.assertEqual(p.science["per_million"][:3], [210., 250., 300.])
        p = prepare("dose-response", demo("dose-response", "b"))
        self.assertEqual(p.science["means"]["Receptor"][:3], [[0., 2.5], [.3, 8.], [1., 18.5]])
        p = prepare("paired-sample", demo("paired-sample"))
        self.assertEqual(p.science["paired_differences"]["P01"], -55)
        p = prepare("xrd-stack", demo("xrd-stack"), options={"offset": 10})
        self.assertEqual(p.science["offsets"], {"Phase A":0., "Phase B":10.})
        self.assertEqual(p.tables[1].columns[1][1][0], float(demo("xrd-stack")[27]["intensity"]) + 10.)
        p = prepare("eis-nyquist", demo("eis-nyquist", "b")[::-1])
        self.assertEqual(p.science["ordered_frequencies"]["Solution"], [5000,1000,300,100,10])
        self.assertEqual(p.tables[0].columns[1][1], [.2,.7,1.1,.6,.2])

    def test_input_errors_do_not_coerce_missing_science_to_zero(self):
        bad = [
            ("histogram", [{"value":"nan"}], {}),
            ("histogram", [{"value":3}], {"bins":-2}),
            ("histogram", [{"value":3}], {"bin_width":0}),
            ("histogram", [{"value":3}], {"bin_width":1,"bins":2}),
            ("scatter", [{"x":"", "y":4}], {}),
            ("violin", [{"group":"A","value":1}]*4, {}),
            ("grouped-column", demo("grouped-column")[1:], {}),
            ("grouped-column", demo("grouped-column") * 2, {}),
            ("likert", demo("likert")[1:], {}),
            ("likert", [dict(r,count=0) for r in demo("likert")], {}),
            ("percent-stack", [dict(r,value=0) for r in demo("percent-stack")], {}),
            ("point-error", [dict(demo("point-error")[0],error=-1)], {}),
            ("heatmap", demo("heatmap")[1:], {}),
            ("dual-y", demo("dual-y")*2, {}),
            ("multi-panel", [demo("multi-panel")[0]], {}),
            ("corpus-frequency", [dict(demo("corpus-frequency")[0],tokens=0)], {}),
            ("corpus-frequency", [dict(demo("corpus-frequency")[0],count=1.3)], {}),
            ("event-study", [dict(demo("event-study")[0],lower=5)], {}),
            ("paired-sample", demo("paired-sample")*2, {}),
            ("xrd-stack", demo("xrd-stack"), {"offset":-1}),
            ("eis-nyquist", [dict(demo("eis-nyquist")[0],frequency=0)], {}),
            ("scatter", demo("scatter"), {"bins":4}),
        ]
        for id, rows, options in bad:
            with self.subTest(recipe=id, options=options), self.assertRaises(RecipeError):
                prepare(id,rows,options=options)

    def test_template_requires_actual_source_and_the_replacement_dataset(self):
        # Test only the refusal conditions in the adapter; no native run is implied.
        graph, op, gl, plot, sheet = (Mock() for _ in range(5))
        target = (Path.cwd() / "research-figure.otpu").resolve()
        op.get_lt_str.return_value = str(target)
        self.assertEqual(template_origin(op, graph, target), str(target))
        op.get_lt_str.return_value = str(target.with_name("Default.otpu"))
        with self.assertRaisesRegex(RuntimeError, "reports template"):
            template_origin(op, graph, target)
        op.get_lt_str.side_effect = ["OldBook_A", "NewBook_A"]
        with self.assertRaisesRegex(RuntimeError, "source mismatch"):
            dataset_name(op, gl, "[Graph1]1!1", "x", "[Book2]1!col(1)")
        plot.index.return_value = 0
        gl.get_int.return_value = 201
        with self.assertRaisesRegex(RuntimeError, "plot type"):
            check_xy(op, gl, plot, {"kind":"line"}, sheet, "multi-line")


if __name__ == "__main__":
    unittest.main()
