"""Title-block metadata and sheet layout without rerendering CAD geometry."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from drawing_title_block import drawing_scale, load_title_block, title_block_svg
from ifc_utils import _drawing_pdf_sheet, _export_drawing_pdf


SVG_NS = "{http://www.w3.org/2000/svg}"
SETTINGS = {"author": "Ing. Jiří Bobek", "investor": "Ing. Jiří Bobek",
            "project": "RD Lažánky", "stage": "DSP", "date": "11/2026"}
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="150mm" '
       'viewBox="10 20 400 300"><text class="drawing-title">Půdorys 1:100</text>'
       '<path id="geometry" d="M10 20L20 40"/></svg>')


class DrawingTitleBlockTests(unittest.TestCase):
    def test_metadata_unicode_escaping_number_and_long_drawing_title(self):
        block = title_block_svg(SETTINGS | {"author": "Ing. <Jiří> & Bobek"},
                                filename="D1.6.2. Řízené větrání - Půdorys podkroví.pdf",
                                scale="1:100", paper="A4", x=207, y=147)
        root = ET.fromstring(block)
        text = " ".join(root.itertext())
        for value in ("Ing. <Jiří> & Bobek", "RD Lažánky", "DSP", "D1.6.2", "1:100", "11/2026", "A4"):
            self.assertIn(value, text)
        self.assertIn("Řízené větrání - Půdorys podkroví", text)
        self.assertIn("HL. ING. PROJEKTU:", text)
        self.assertIn("ZOD. PROJEKTANT:", text)
        self.assertFalse(root.find('g[@class="title-block-logo"]').findall("*"))
        self.assertNotIn("image", block)
        self.assertEqual(root.get("transform"), "translate(207, 147)")

    def test_opt_in_configuration_is_shared_by_svgs_in_project_folder(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/"upper.svg"
            self.assertIsNone(load_title_block(path))
            config = path.with_name("title_block.json")
            config.write_text(json.dumps(SETTINGS), encoding="utf-8")
            self.assertEqual(load_title_block(path), SETTINGS)
            for settings in (["wrong"], {"author": False}, {"unsupported": "field"}):
                config.write_text(json.dumps(settings), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_title_block(path)

    def test_a4_plan_moves_left_without_resizing_and_clears_title_block(self):
        result = ET.fromstring(_drawing_pdf_sheet(
            SVG, width=297, height=210, margin=10, title_block=SETTINGS,
            filename="D1.1.3. Půdorys podkroví.pdf"))
        drawing = result.find(SVG_NS+"svg")
        block = result.find(SVG_NS+"g")
        self.assertEqual((drawing.get("width"), drawing.get("height")), ("200", "150"))
        self.assertEqual(drawing.get("viewBox"), "10 20 400 300")
        self.assertEqual(drawing.get("x"), "5")
        self.assertEqual(drawing.find(SVG_NS+"path").get("d"), "M10 20L20 40")
        self.assertEqual(block.get("transform"), "translate(207, 141)")
        self.assertLessEqual(float(drawing.get("x"))+float(drawing.get("width"))+2, 207)

    def test_full_a3_sheet_keeps_its_layout_and_uses_bottom_right_corner(self):
        for width, height, position in ((297, 420, "translate(207, 351)"),
                                         (420, 297, "translate(330, 228)")):
            svg = SVG.replace('width="200mm"', f'width="{width}mm"').replace(
                'height="150mm"', f'height="{height}mm"')
            result = ET.fromstring(_drawing_pdf_sheet(
                svg, width=width, height=height, margin=0, title_block=SETTINGS,
                filename="D1.1.11. Řez AA.pdf", paper="A3"))
            drawing = result.find(SVG_NS+"svg")
            self.assertEqual((drawing.get("x"), drawing.get("y")), ("0", "0"))
            self.assertEqual(result.find(SVG_NS+"g").get("transform"), position)
            self.assertIn("A3", " ".join(result.itertext()))

    def test_scale_comes_from_drawing_headers_and_supports_mixed_sheets(self):
        self.assertEqual(drawing_scale(SVG), "1:100")
        mixed = SVG.replace('</svg>', '<text class="drawing-title">Řez 1:50</text>'
                            '<text class="drawing-title">Jiný řez 1:100</text></svg>')
        self.assertEqual(drawing_scale(mixed), "1:100, 1:50")
        self.assertEqual(drawing_scale(SVG.replace("drawing-title", "dimension")), "—")

    def test_shared_pdf_export_loads_metadata_without_modifying_cached_svg(self):
        with TemporaryDirectory() as directory:
            svg = Path(directory)/"upper.svg"
            svg.write_text(SVG, encoding="utf-8")
            svg.with_name("title_block.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
            pdf = Path(directory)/"D1.1.3. Půdorys podkroví.pdf"

            def export(command, *, check):
                self.assertEqual(Path(command[1]), pdf.parent / "src" / pdf.with_suffix(".svg").name)
                root = ET.parse(command[1]).getroot()
                self.assertEqual(root.get("width"), "297mm")
                self.assertEqual(root.get("height"), "210mm")
                self.assertIsNotNone(root.find(f'{SVG_NS}g[@class="drawing-title-block"]'))
                self.assertIn("D1.1.3", " ".join(root.itertext()))
                destination = next(value.split("=", 1)[1] for value in command
                                   if value.startswith("--export-filename="))
                Path(destination).write_bytes(b"%PDF-title-block")

            with patch("ifc_utils.shutil.which", return_value="inkscape"), \
                 patch("ifc_utils.subprocess.run", side_effect=export):
                _export_drawing_pdf(svg, pdf)
            self.assertEqual(svg.read_text(encoding="utf-8"), SVG)
            self.assertEqual(pdf.read_bytes(), b"%PDF-title-block")
            self.assertTrue((pdf.parent / "src" / pdf.with_suffix(".svg").name).is_file())


if __name__ == "__main__":
    unittest.main()
