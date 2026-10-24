from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ifcopenshell.util.element

from ifc_utils import DrawingSheet, House

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"


def source(width=20, height=20, color="red"):
    return (f'<svg xmlns="{SVG}" xmlns:xlink="{XLINK}" id="root" width="{width}mm" '
            f'height="{height}mm" viewBox="0 0 {width} {height}">'
            '<defs><style>.projection {fill:' + color + ';} '
            '.projection, path {stroke:black;} marker[id^="batting-"] path {stroke-width:.1;} '
            '#root .projection {clip-path:url(#clip);} '
            '@media print {.projection {stroke:green;}}</style>'
            '<pattern id="hatch" width="1" height="1"><path d="M0 0L1 1"/></pattern>'
            '<marker id="batting-test"><path d="M0 0L1 1"/></marker>'
            '<clipPath id="clip"><rect width="20" height="20"/></clipPath>'
            '<g id="symbol"><path d="M0 0L1 1"/></g></defs>'
            '<path id="beam" class="projection" fill="#ff0000" style="stroke:url(#hatch)" '
            'marker-end="url(#batting-test)" d="M1 1H10V10H1Z"/>'
            '<use xlink:href="#symbol"/></svg>')


class DrawingSheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.house = House("Sheet tests", mirror_x=False)
        self.first = self.house.add_drawing("Roof", 0, 0, 2, 4, right_panel_width=65)
        self.second = self.house.add_drawing("Section", 0, 0, 2, 4, right_panel_width=65)
        self.house.write(self.directory / "house.ifc")
        self.output = self.directory / "sheet.svg"
        self.calls = []

    def renderer(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        drawing = args[1]
        text = self.sources[drawing] if isinstance(self.sources, dict) else self.sources
        Path(args[2]).write_text(text)
        return Path(args[2])

    def render(self, sheet, **kwargs):
        with patch("ifc_utils._render_existing_drawing", side_effect=self.renderer):
            return sheet.render(self.output, **kwargs)

    def test_normalized_centres_use_the_whole_page_and_keep_the_original_a4_top_half(self):
        self.sources = {self.first.element.GlobalId: source(235, 180), self.second.element.GlobalId: source(40, 20)}
        sheet = DrawingSheet(paper="A3", orientation="portrait")
        sheet.add(self.first, x=.5, y=.25, crop=False, title="D1.1.5. Krov")
        sheet.add(self.second, x=.75, y=.75, crop=False, tables=False)
        before = [(d.document.Location, ifcopenshell.util.element.get_pset(d.element, "EPset_Drawing"))
                  for d in (self.first, self.second)]
        self.assertEqual(self.render(sheet), self.output)
        root = ET.parse(self.output).getroot()
        self.assertEqual((root.get("width"), root.get("height")), ("297mm", "420mm"))
        first, second = [group[0] for group in root if group.tag == f"{{{SVG}}}g"]
        self.assertEqual((first.get("x"), first.get("y")), ("31", "15"))
        self.assertEqual((first.get("width"), first.get("height")), ("235", "180"))
        self.assertEqual((second.get("x"), second.get("y")), ("202.75", "305"))
        self.assertEqual(second.get("viewBox"), "0 0 40 20")
        self.assertFalse(self.calls[1][1]["tables"])
        self.assertEqual(self.calls[0][1]["title"], "D1.1.5. Krov")
        self.assertEqual(self.calls[1][1]["title"], "Section")
        self.assertEqual(before, [(d.document.Location, ifcopenshell.util.element.get_pset(d.element, "EPset_Drawing"))
                                  for d in (self.first, self.second)])
        self.assertFalse(any(e.tag == f"{{{SVG}}}image" for e in root.iter()))

    def test_section_cameras_do_not_automatically_add_markers_to_other_views(self):
        marker = self.first.add_cut_symbol((0, 0), (1, 0), "XX")
        sections = [self.house.add_drawing(
            f"Section {index}", index, 0, 2, 4,
            view="elevation", direction=(1, 0, 0),
        ) for index in range(3)]
        self.house.write(self.directory / "house.ifc")
        persisted = ifcopenshell.open(str(self.directory / "house.ifc"))
        for drawing in (self.first, *sections):
            self.assertFalse(ifcopenshell.util.element.get_pset(
                persisted.by_guid(drawing.element.GlobalId), "EPset_Drawing", "GlobalReferencing",
            ))
        members = {element.GlobalId for relation in persisted.by_guid(self.first.group.GlobalId).IsGroupedBy
                   for element in relation.RelatedObjects}
        self.assertIn(marker.GlobalId, members)

    def test_styles_marker_ids_patterns_and_use_references_are_isolated(self):
        self.sources = {self.first.element.GlobalId: source(color="red"), self.second.element.GlobalId: source(color="blue")}
        sheet = DrawingSheet()
        sheet.add(self.first, x=.25, y=.5, crop=False)
        sheet.add(self.second, x=.75, y=.5, crop=False)
        self.render(sheet)
        root = ET.parse(self.output).getroot()
        ids = [e.get("id") for e in root.iter() if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        for index, color in ((1, "red"), (2, "blue")):
            group = root.find(f".//{{{SVG}}}g[@id='sheet-drawing-{index}']")
            css = group.find(f".//{{{SVG}}}style").text
            self.assertIn(f"#sheet-drawing-{index} .projection {{fill:{color};}}", css)
            self.assertIn(f'marker[id^="sheet-{index}-batting-"]', css)
            self.assertIn(f"#sheet-{index}-root", css)
            self.assertIn(f"url(#sheet-{index}-clip)", css)
            self.assertIn("@media print", css)
            beam = group.find(f".//{{{SVG}}}path[@id='sheet-{index}-beam']")
            self.assertEqual(beam.get("fill"), "#ff0000")
            self.assertEqual(beam.get("marker-end"), f"url(#sheet-{index}-batting-test)")
            self.assertEqual(group.find(f".//{{{SVG}}}use").get(f"{{{XLINK}}}href"), f"#sheet-{index}-symbol")

    def test_cropping_moves_title_near_geometry_without_scaling_the_contents(self):
        self.sources = (f'<svg xmlns="{SVG}" id="root" width="100mm" height="100mm" viewBox="0 0 100 100">'
                        '<text class="drawing-title" x="50" y="6.5" style="font-size:4px">Section 1:100</text>'
                        '<rect id="body" x="20" y="60" width="30" height="20"/></svg>')
        sheet = DrawingSheet(paper="A3", orientation="portrait")
        sheet.add(self.second, x=.5, y=.75, tables=False)
        queries = []

        def run(command, **kwargs):
            root = ET.parse(command[1]).getroot()
            queries.append(root)
            bounds = (20, 60, 30, 20) if len(queries) == 1 else (18, 53, 34, 27)
            return subprocess.CompletedProcess(command, 0, stdout="\n".join(str(v * 96 / 25.4) for v in bounds))

        with patch("drawing_sheet.shutil.which", return_value="/usr/bin/inkscape"), \
                patch("drawing_sheet.subprocess.run", side_effect=run):
            self.render(sheet)
        self.assertIsNone(queries[0].find(f".//{{{SVG}}}text"))
        root = ET.parse(self.output).getroot()
        drawing = root.find(f"{{{SVG}}}g/{{{SVG}}}svg")
        self.assertEqual(drawing.get("viewBox"), "16 51 38 31")
        self.assertEqual((drawing.get("width"), drawing.get("height")), ("38", "31"))
        self.assertEqual((drawing.get("x"), drawing.get("y")), ("129.5", "299.5"))
        title = drawing.find(f"{{{SVG}}}text")
        self.assertEqual((title.get("x"), title.get("y")), ("35", "56.5"))
        body = drawing.find(f"{{{SVG}}}rect")
        self.assertEqual((body.get("x"), body.get("y"), body.get("width")), ("20", "60", "30"))

    def test_overflow_is_rejected_without_overwriting_the_old_sheet(self):
        self.sources = source(200, 200)
        self.output.write_text("Original sheet")
        sheet = DrawingSheet()
        sheet.add(self.first, x=.5, y=.5, crop=False)
        with self.assertRaisesRegex(ValueError, "will not be scaled"):
            self.render(sheet)
        self.assertEqual(self.output.read_text(), "Original sheet")

    def test_pdf_exports_one_full_sized_sheet_without_an_extra_margin(self):
        self.sources = source()
        sheet = DrawingSheet(paper="A3", orientation="portrait")
        sheet.add(self.first, x=.5, y=.25, crop=False)
        pdf = self.directory / "roof.pdf"
        with patch("ifc_utils._export_drawing_pdf") as export:
            self.render(sheet, pdf=pdf)
        export.assert_called_once_with(self.output, pdf, paper="A3", orientation="portrait", margin=0, inkscape="inkscape")

    def test_configuration_and_inputs_are_validated(self):
        sheet = DrawingSheet()
        for kwargs in ({"x": -.1, "y": .5}, {"x": 1.1, "y": .5}, {"x": True, "y": .5},
                       {"x": .5, "y": float("nan")}, {"x": .5, "y": .5, "tables": 0},
                       {"x": .5, "y": .5, "crop": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                sheet.add(self.first, **kwargs)
        self.assertEqual(len(sheet._drawings), 0)
        with self.assertRaisesRegex(ValueError, "at least one"):
            sheet.render(self.output)
        with self.assertRaises(TypeError):
            sheet.add("roof.svg", x=.5, y=.5)
        with self.assertRaises(ValueError):
            DrawingSheet(padding=-1)

    def test_tables_false_keeps_timber_styling_metadata_and_does_not_draw_the_panel(self):
        ground = self.house.storey("Upper", elevation=0)
        beam = ground.beam("Tie", start=(0, 0, 1), end=(1, 0, 1), size=(.05, .15))
        drawing = self.house.add_drawing("Framing", 0, 0, 2, 4, view="elevation", direction=(1, 0, 0), right_panel_width=65)
        drawing.add_timber_schedule([("Tie", [beam], 0, {"color": "#516fe7"})], styled_members=[beam])
        before = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")

        def run(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_text(source())
            return subprocess.CompletedProcess(command, 0)

        with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                patch("ifc_utils.subprocess.run", side_effect=run), \
                patch("ifc_utils._postprocess_right_panel") as panel, \
                patch("ifc_utils._postprocess_projected_wood_surface_styles") as styles:
            drawing.render(self.output, tables=False)
        panel.assert_not_called()
        self.assertEqual(styles.call_args.kwargs["styles"][beam.GlobalId]["color"], "#516fe7")
        self.assertEqual(before, ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing"))


if __name__ == "__main__":
    unittest.main()
