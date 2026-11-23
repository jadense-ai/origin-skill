"""Real PDF operators and TIFF tag fixtures for export postflight; no Origin process."""

from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from journals import check_export


def pdf_fixture(path, stream, image=False, rotated=False):
    from pypdf import PdfWriter
    from pypdf.generic import (DecodedStreamObject, DictionaryObject, FloatObject,
                               NameObject, NumberObject, RectangleObject)

    writer = PdfWriter()
    page = writer.add_blank_page(400, 300)
    font = DictionaryObject({NameObject("/Type"):NameObject("/Font"),
                             NameObject("/Subtype"):NameObject("/Type1"),
                             NameObject("/BaseFont"):NameObject("/Helvetica")})
    res = DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F"):font})})
    if image:
        obj = DecodedStreamObject()
        obj.set_data(bytes(600 * 6 * 3))
        obj.update({NameObject("/Type"):NameObject("/XObject"), NameObject("/Subtype"):NameObject("/Image"),
                    NameObject("/Width"):NumberObject(600), NameObject("/Height"):NumberObject(6),
                    NameObject("/BitsPerComponent"):NumberObject(8), NameObject("/ColorSpace"):NameObject("/DeviceRGB")})
        res[NameObject("/XObject")] = DictionaryObject({NameObject("/Im"):writer._add_object(obj)})
    content = DecodedStreamObject()
    content.set_data(stream)
    page[NameObject("/Resources")] = res
    page[NameObject("/Contents")] = writer._add_object(content)
    if rotated:
        page[NameObject("/CropBox")] = RectangleObject([10,20,110,170])
        page[NameObject("/UserUnit")] = FloatObject(2)
        page.rotate(90)
    writer.write(path)


@unittest.skipUnless(find_spec("pypdf"), "pypdf inspector dependency")
class PDFTests(unittest.TestCase):
    def test_visible_dimensions_and_userunit(self):
        with TemporaryDirectory() as temp:
            p = Path(temp)/"graph.pdf"
            pdf_fixture(p, b"BT /F 4 Tf (X axis) Tj ET", rotated=True)
            result = check_export("science", p, {"recipe_id":"scatter","layers":[{}]})
        facts = result["file_measurements"]
        self.assertAlmostEqual(facts["width_mm"], 150*2*25.4/72)
        self.assertAlmostEqual(facts["height_mm"], 100*2*25.4/72)
        self.assertEqual(facts["observed_font_pt"], [8.0])
        self.assertTrue(facts["has_live_text"])
        self.assertFalse(facts["fonts_embedded"])
        self.assertIn("editable_text", result["missing"])

    def test_every_painted_width_and_font(self):
        with TemporaryDirectory() as temp:
            p = Path(temp)/"graph.pdf"
            pdf_fixture(p, b"0.6 w 0 0 m 40 40 l S 0.1 w 0 0 m 5 5 l S "
                        b"q 2 0 0 2 0 0 cm 1 w 0 0 m 10 10 l S Q "
                        b"BT /F 7 Tf (X axis) Tj /F 11 Tf (Y axis) Tj ET")
            result = check_export("nature", p, {"recipe_id":"scatter","layers":[{}]})
        self.assertEqual(result["file_measurements"]["stroke_pts"], [0.1,0.6,2.0])
        self.assertEqual(result["file_measurements"]["observed_font_pt"], [7.0,11.0])
        self.assertTrue(any("font_pt: 11.0" in v for v in result["errors"]))
        self.assertTrue(any("stroke_pt: 2.0" in v for v in result["errors"]))

    def test_effective_embedded_image_dpi_and_rasterized_labels(self):
        with TemporaryDirectory() as temp:
            p = Path(temp)/"graph.pdf"
            pdf_fixture(p, b"q 288 0 0 2.88 0 0 cm /Im Do Q", image=True)
            result = check_export("science", p, {"recipe_id":"scatter","layers":[{}]})
        self.assertAlmostEqual(result["file_measurements"]["dpi"], 150)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(e.startswith("editable_text:") for e in result["errors"]))


@unittest.skipUnless(find_spec("PIL"), "Pillow inspector dependency")
class TIFFTests(unittest.TestCase):
    def test_actual_lzw_dpi_axes_and_dimensions(self):
        from PIL import Image
        with TemporaryDirectory() as temp:
            p = Path(temp)/"Fig1.tif"
            Image.new("RGB", (1800, 600)).save(p, dpi=(300,600), compression="tiff_lzw")
            result = check_export("PLOS One", p, {"recipe_id":"multi-line","layers":[{}],
                "journal_style":{"applied":{"width_mm":132, "height_mm":80}}})
        f = result["file_measurements"]
        self.assertEqual((f["dpi_axes"], f["compression"], f["has_alpha"], f["flattened"]),
                         ([300,600], "LZW", False, True))
        self.assertAlmostEqual(f["width_mm"], 152.4)
        self.assertAlmostEqual(f["height_mm"], 25.4)
        self.assertEqual(f["bits_per_channel"], 8)
        self.assertIn("font_pt", result["missing"])

    def test_no_default_dpi_or_silent_lax_max(self):
        from PIL import Image
        with TemporaryDirectory() as temp:
            p = Path(temp)/"Fig1.tif"
            Image.new("RGBA", (32,32)).save(p)
            r = check_export("PLOS One", p, {"journal_style":{"applied":{"width_mm":132}}})
            self.assertIn("dpi", r["missing"])
            self.assertIn("width_mm", r["missing"])
            self.assertTrue(r["file_measurements"]["has_alpha"])
            Image.new("RGB",(128,128)).save(p,dpi=(300,900),compression="tiff_lzw")
            r = check_export("PLOS One", p, {})
            self.assertTrue(any("dpi: 900" in e for e in r["errors"]))


if __name__ == "__main__":
    unittest.main()
