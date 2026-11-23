"""Boundary, unknown-evidence and native object read-back tests. No Origin required."""

import math
import unittest

from journals import apply_journal_style, load_profile, validate_figure


def measured(journal, **changes):
    profile = load_profile(journal)
    d = profile["defaults"]
    metadata = {k: d[k] for k in ("width_mm", "font_family", "font_pt", "stroke_pt", "output_format")}
    metadata.update(height_mm=70, image_kind="vector", color_mode="RGB", editable_text=True,
                    fonts_embedded=True, panel_count=1, column="single", single_page=True)
    metadata.update(changes)
    return metadata


class ProfileChecks(unittest.TestCase):
    def test_only_supported_main_journals(self):
        for name in ("nature", "Science", "Cell", "PLOS ONE"):
            self.assertTrue(load_profile(name)["sources"][0]["url"].startswith("https://"))
        for name in ("Science Advances", "Cell Reports", "../../test"):
            with self.assertRaises(ValueError):
                load_profile(name)

    def test_missing_evidence_is_not_a_pass(self):
        for name in ("nature", "science", "cell", "plos-one"):
            report = validate_figure(name, {})
            self.assertEqual(report["status"], "review")
            self.assertIn("font_pt", report["missing"])
            self.assertIn("output_format", report["missing"])

    def test_nature_panel_width_and_vector_fonts(self):
        data = measured("nature", panel_count=2, panel_label=["a", "b"], panel_bold=True, panel_italic=False,
                        panel_font_pt=8, width_mm=130)
        self.assertEqual(validate_figure("nature", data)["status"], "pass")
        data.update(panel_label=["A", "B"], editable_text=False, stroke_pt=0.24)
        self.assertEqual(len(validate_figure("nature", data)["errors"]), 3)
        self.assertEqual(validate_figure("nature", measured("nature", image_kind="photo",
            output_format="TIFF", dpi=300))["status"], "review")

    def test_science_line_and_raster_rules(self):
        self.assertEqual(validate_figure("science", measured("science", stroke_pt=0.28))["status"], "pass")
        for key, val in (("font_pt", 5.9), ("stroke_pt", 0.27)):
            self.assertEqual(validate_figure("science", measured("science", **{key: val}))["status"], "fail")
        for kind, expected in (("photo", "fail"), ("mixed", "pass")):
            self.assertEqual(validate_figure("science", measured("science",
                dpi=600, image_kind=kind))["status"], expected)
        data = measured("science", panel_count=2, panel_label=["A", "B"], panel_font_pt=10, panel_bold=True)
        self.assertEqual(validate_figure("science", data)["status"], "pass")

    def test_cell_archive_width_and_dpi(self):
        self.assertEqual(validate_figure("cell", measured("cell"))["status"], "review")
        meta = measured("cell", width_mm=114, column="intermediate", cell_current_rules_confirmed=True)
        self.assertEqual(validate_figure("cell", meta)["status"], "pass")
        self.assertEqual(validate_figure("cell", {**meta, "column": "single"})["status"], "fail")
        meta.update(image_kind="mixed", raster_kind="line_art", dpi=500)
        self.assertEqual(validate_figure("cell", meta)["status"], "fail")
        meta.update(raster_kind="black_white")
        self.assertEqual(validate_figure("cell", meta)["status"], "pass")
        meta.update(font_pt=9)
        self.assertEqual(validate_figure("cell", meta)["status"], "review")

    def test_plos_tiff_and_eps(self):
        tiff = measured("PLOS One", width_mm=66.8, height_mm=222.3, image_kind="line_art",
                        dpi=600, compression="LZW", has_alpha=False, flattened=True,
                        file_bytes=3_000_000, bits_per_channel=8)
        self.assertEqual(validate_figure("plos-one", tiff)["status"], "pass")
        for key, val in (("width_mm", 66.79), ("height_mm", 223), ("dpi", 601),
                         ("compression", "deflate"), ("has_alpha", True), ("flattened", False),
                         ("font_family", "Helvetica"), ("file_bytes", 10_000_001)):
            self.assertEqual(validate_figure("plos-one", {**tiff, key: val})["status"], "fail", key)
        eps = {**tiff, "output_format": "EPS", "image_kind": "vector", "eps_fonts_safe": True,
               "editable_text": False}
        del eps["dpi"]
        self.assertEqual(validate_figure("plos-one", eps)["status"], "pass")

    def test_invalid_measurements(self):
        for bad in (True, math.nan, math.inf, "7", -1, 0):
            self.assertEqual(validate_figure("nature", measured("nature", font_pt=bad))["status"], "fail")


class OriginObject:
    def __init__(self, **props):
        self.props = props

    def get_float(self, key):
        return self.props.get(key, 0)

    def set_float(self, key, val):
        self.props[key] = val


class Layer(OriginObject):
    def __init__(self):
        super().__init__(**{"plot1.line.width": 2.0, "x.to": 10, "y.to": 10})
        self.objects = {"XB": OriginObject()}

    def label(self, k):
        return self.objects.get(k)

    def add_label(self, text, x, y):
        obj = self.objects["OriginPlotPanel"] = OriginObject()
        obj.text = text
        return obj

    def plot_list(self):
        return [object()]


class Graph(OriginObject):
    def __init__(self):
        super().__init__(width=2000, height=1400, resx=600, resy=600)
        self.layers = [Layer(), Layer()]

    def __iter__(self):
        return iter(self.layers)

    def __len__(self):
        return len(self.layers)


class NativeChecks(unittest.TestCase):
    def test_native_readback_and_repeated_panel_writes(self):
        graph = Graph()
        op = type("Origin", (), {"lt_int": lambda _, value: 2})()
        for _ in range(2):
            result = apply_journal_style(op, graph, "nature", panel_label=["A", "B"])
        self.assertFalse(result["needs_review"])
        self.assertAlmostEqual(result["applied"]["width_mm"], 89, delta=0.05)
        self.assertAlmostEqual(result["applied"]["height_mm"], 89 * 0.7, delta=0.05)
        self.assertEqual(result["applied"]["layer2.panel.text"], r"\b(b)")
        self.assertEqual(graph.layers[0].get_float("plot1.line.width"), 0.6)
        self.assertEqual(len(graph.layers[0].objects), 2)
        switched = apply_journal_style(op, graph, "science")
        self.assertEqual(switched["applied"]["layer2.panel.text"], r"\b(B)")
        self.assertEqual(switched["applied"]["layer2.panel.fsize"], 10)
        self.assertEqual(len(graph.layers[0].objects), 2)

    def test_failed_write_is_not_reported_as_verified(self):
        graph = Graph()
        graph.layers[0].set_float = lambda k, v: None
        op = type("Origin", (), {"lt_int": lambda _, value: 2})()
        result = apply_journal_style(op, graph, "science")
        self.assertTrue(any("layer1.x.label.pt" in item for item in result["needs_review"]))
        self.assertNotIn("layer1.x.label.pt", result["applied"])
        with self.assertRaises(ValueError):
            apply_journal_style(op, graph, "science", width_mm=math.nan)


if __name__ == "__main__":
    unittest.main()
