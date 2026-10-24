from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import numpy as np

from ifc_utils import House, _postprocess_dimension_overlays


def world_curves(annotation):
    placement = ifcopenshell.util.placement.get_local_placement(annotation.ObjectPlacement)
    curves = []
    for representation in annotation.Representation.Representations:
        for item in ifcopenshell.util.representation.resolve_items(representation):
            for curve in item["item"].Elements:
                curves.append(np.array([(placement @ item["matrix"] @ np.array((*p, 0, 1)))[:3]
                                        for p in curve.Points.CoordList]))
    return curves


class ElevationDimensionTests(unittest.TestCase):
    def test_default_font_size_matches_other_dimensions(self):
        house = House("Levels")
        drawing = house.add_drawing("Section", 0, 0, 2, 4, view="elevation", direction=(1, 0, 0))
        dimension = drawing.add_elevation_dimension(0, 2, 0, 1.5)
        size = ifcopenshell.util.element.get_pset(dimension, "BBIM_ElevationDimension", "FontSize")
        css = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text()
        match = re.search(r'text\.DIMENSION,\s*tspan\.DIMENSION\s*\{\s*font-size:\s*([\d.]+)px', css)
        self.assertIsNotNone(match)
        self.assertEqual(size, float(match[1]))
        label = next(a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                     if (a.Name or "").endswith("Label"))
        self.assertEqual(ifcopenshell.util.element.get_pset(label, "BBIM_DrawingText", "FontSize"), size)

    def test_endpoints_arrow_and_label_across_views_and_mirroring(self):
        for mirror in (False, True):
            for direction in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                for endpoints in ((2, 4), (4, 2)):
                    with self.subTest(mirror=mirror, direction=direction, endpoints=endpoints):
                        house = House("Levels", mirror_x=mirror)
                        drawing = house.add_drawing("Section", 1, 1.5, 2, 5,
                                                    view="elevation", direction=direction)
                        other = house.add_drawing("Other", 1, 1.5, 2, 5)
                        symbol = drawing.add_elevation_dimension(*endpoints, 1, 2.5)
                        label = next(a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                                     if (a.Name or "").endswith("Label"))
                        self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                        self.assertNotIn(label, other.group.IsGroupedBy[0].RelatedObjects)
                        props = ifcopenshell.util.element.get_pset(symbol, "BBIM_ElevationDimension")
                        self.assertEqual((props["Height"], props["Label"]), (1.5, "+1500"))
                        self.assertEqual(label.Representation.Representations[0].Items[0].Literal, "+1500")
                        exported = house._export_model()
                        curves = world_curves(exported.by_guid(symbol.GlobalId))
                        reflection = np.array((-1 if mirror else 1, 1, 1))
                        expected = ([(1, h, 2.5) for h in endpoints] if direction[0]
                                    else [(h, 1.5, 2.5) for h in endpoints])
                        np.testing.assert_allclose(curves[0], np.array(expected) * reflection)
                        camera = ifcopenshell.util.placement.get_local_placement(
                            exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
                        inverse = np.linalg.inv(camera)
                        local = [np.array([(inverse @ np.array((*p, 1)))[:3] for p in c]) for c in curves]
                        # A 2.5 paper mm stem at 1:100 = 0.25 model metres.
                        np.testing.assert_allclose(local[1][1] - local[1][0], (0, .25, 0), atol=1e-12)
                        np.testing.assert_allclose(local[2][:, 1] - local[1][0][1], (.075, 0, .075), atol=1e-12)
                        self.assertAlmostEqual(abs(local[2][2][0] - local[2][0][0]), .15)
                        self.assertGreater(local[1][2][0], local[1][1][0])
                        text_frame = ifcopenshell.util.placement.get_local_placement(
                            exported.by_guid(label.GlobalId).ObjectPlacement)
                        text_origin = (inverse @ text_frame[:, 3])[:3]
                        self.assertGreater(text_origin[0], local[1][0][0])
                        self.assertGreater(text_origin[1], local[1][1][1])

    def test_signed_values_zero_and_paper_sizes_follow_drawing_scale(self):
        house = House("Levels")
        drawing = house.add_drawing("Section", 0, 0, 2, 4, view="elevation", direction=(1, 0, 0))
        for z0, z1, expected in ((0, 1.5, "+1500"), (1, .75, "-250"),
                                  (1, 1, "±0"), (1, .9999, "±0"), (0, 12.345, "+12345"),
                                  (0, .0014, "+1"), (0, -.0014, "-1")):
            dimension = drawing.add_elevation_dimension(0, 2, z0, z1)
            self.assertEqual(ifcopenshell.util.element.get_pset(dimension, "BBIM_ElevationDimension", "Label"), expected)
        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": "1/50"})
        dimension = drawing.add_elevation_dimension(0, 2, 0, 1.5, font_size=2.5, line_width=.2, color="blue", name="Datum")
        self.assertEqual(dimension.Name, "Datum")
        self.assertAlmostEqual(np.linalg.norm(world_curves(dimension)[1][1] - world_curves(dimension)[1][0]), .125)
        props = ifcopenshell.util.element.get_pset(dimension, "BBIM_ElevationDimension")
        self.assertEqual((props["FontSize"], props["LineWidth"], props["Color"]), (2.5, .2, "#0000ff"))

    def test_invalid_input_leaves_no_partial_annotations(self):
        house = House("Levels")
        drawing = house.add_drawing("Section", 0, 0, 2, 4, view="elevation", direction=(1, 0, 0))
        invalid = [((0, 0, 0, 1), {}), ((True, 1, 0, 1), {}), ((0, 1, 0, float("inf")), {}),
                   ((0, 1, 0, 1), {"font_size": 0}), ((0, 1, 0, 1), {"line_width": -1}),
                   ((0, 1, 0, 1), {"color": "bad-color"}), ((0, 1, 0, 1), {"name": " "})]
        for args, kwargs in invalid:
            before = len(house.model.by_type("IfcAnnotation"))
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                drawing.add_elevation_dimension(*args, **kwargs)
            self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)
        plan = house.add_drawing("Plan", 0, 0, 2, 4)
        diagonal = house.add_drawing("Diagonal", 0, 0, 2, 4, view="elevation", direction=(1, 1, 0))
        for view in (plan, diagonal):
            before = len(house.model.by_type("IfcAnnotation"))
            with self.assertRaises(ValueError):
                view.add_elevation_dimension(0, 1, 0, 1)
            self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)
        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": "0"})
        before = len(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "positive drawing scale"):
            drawing.add_elevation_dimension(0, 1, 0, 1)
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)

    def test_line_arrow_and_label_stay_above_fills(self):
        source = ('<svg><path id="level" class="elevation-dimension" d="M0 0H1"/>'
                  '<text id="label" class="drawing-text elevation-dimension"><tspan>+1500</tspan></text>'
                  '<path id="floor" d="M0 0H2V2H0Z" fill="white"/></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text(source)
            _postprocess_dimension_overlays(path)
            root = ET.parse(path).getroot()
            self.assertEqual(root[-1].get("class"), "dimension-overlays")
            self.assertEqual([e.get("id") for e in root[-1]], ["level", "label"])
            first = path.read_text()
            _postprocess_dimension_overlays(path)
            self.assertEqual(path.read_text(), first)


if __name__ == "__main__":
    unittest.main()
