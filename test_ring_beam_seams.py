from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

import ifcopenshell
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.util.element
import numpy as np
from shapely.geometry import LineString
from shapely.ops import unary_union

from ring_beam_seams import remove_projected_ring_beam_seams
from section_outlines import _segments, _transform


class RingBeamSeamTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/"section.svg"
        self.model = ifcopenshell.file(schema="IFC4")
        self.wall = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcWall")
        self.other_wall = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcWall")
        self.beam = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcBeam")
        self.pset = ifcopenshell.api.pset.add_pset(self.model, product=self.beam, name="BBIM_RingBeam")
        ifcopenshell.api.pset.edit_pset(self.model, pset=self.pset, properties={
            "SourceWall": self.wall.GlobalId, "ReplacesWallBand": True,
        })

    def svg(self, wall, beam, transform="", extra="", sanitized=False):
        def guid(product):
            value = product.GlobalId
            return value.replace("$", "").replace("_", "") if sanitized else value
        self.path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
            '<defs><pattern id="hatch"><path d="M0 4H10"/></pattern></defs>'
            f'<g transform="{transform}">'
            f'<g class="IfcWall projection GlobalId-{guid(self.wall)}">{wall}</g>'
            f'<g class="IfcBeam projection GlobalId-{guid(self.beam)}">{beam}</g>'
            f'{extra}</g></svg>', encoding="utf-8",
        )

    def strokes(self, guid=None):
        segments = []

        def walk(element, matrix=np.eye(3), owner=None):
            if element.tag.rsplit("}", 1)[-1] == "defs":
                return
            matrix = matrix @ _transform(element.get("transform", ""))
            for token in element.get("class", "").split():
                if token.startswith("GlobalId-"):
                    owner = token.removeprefix("GlobalId-")
            if "stroke:none" not in element.get("style", "") and (guid is None or owner == guid):
                segments.extend(_segments(element, matrix, .001))
            for child in element:
                walk(child, matrix, owner)

        walk(ET.parse(self.path).getroot())
        return unary_union([LineString(edge) for edge in segments])

    def test_open_visible_seams_are_removed_from_both_products_but_jambs_and_cuts_remain(self):
        wall = '<path id="wall" d="M0 4H3 M4 4H10 M0 6H3 M4 6H10"/>'
        beam = ('<path id="beam" d="M0 4H3 M4 4H10 M0 6H3 M4 6H10 M0 4V6 M3 4V6 M4 4V6 M10 4V6"/>'
                f'<g class="projection GlobalId-{self.other_wall.GlobalId}"><path id="nested-other" d="M0 4H10"/></g>')
        extra = (f'<g class="cut GlobalId-{self.beam.GlobalId}"><path id="cut" d="M20 4H25V6H20Z"/></g>'
                 f'<g class="projection GlobalId-{self.other_wall.GlobalId}"><path id="other" d="M0 4H10"/></g>')
        self.svg(wall, beam, extra=extra)
        self.assertEqual(remove_projected_ring_beam_seams(self.path, self.model), 2)
        for product in (self.wall, self.beam):
            strokes = self.strokes(product.GlobalId)
            self.assertEqual(strokes.intersection(LineString(((.1, 4), (2.9, 4)))).length, 0)
        strokes = self.strokes(self.beam.GlobalId)
        for x in (0, 3, 4, 10):
            self.assertAlmostEqual(strokes.intersection(LineString(((x, 4), (x, 6)))).length, 2)
        root = ET.parse(self.path).getroot()
        self.assertEqual(root.find('.//*[@id="cut"]').get("d"), "M20 4H25V6H20Z")
        self.assertEqual(root.find('.//*[@id="other"]').get("d"), "M0 4H10")
        self.assertEqual(root.find('.//*[@id="nested-other"]').get("d"), "M0 4H10")
        self.assertEqual(root.find('.//*[@id="hatch"]/*').get("d"), "M0 4H10")
        before = self.path.read_bytes()
        self.assertEqual(remove_projected_ring_beam_seams(self.path, self.model), 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_closed_faces_keep_fills_and_outer_silhouette_under_mirroring_and_rotation(self):
        self.beam.GlobalId = "0"+"_"*10+"$"+"A"*10
        for transform in ("", "translate(30,4) scale(-2,2)", "translate(30,4) rotate(15)"):
            with self.subTest(transform=transform):
                wall = '<path d="M0 0H10V4H0Z M0 6H10V10H0Z"/>'
                beam = '<path id="original-face" style="fill:url(#hatch);stroke:black" d="M0 4H10V6H0Z"/>'
                self.svg(wall, beam, transform=transform, sanitized=True)
                self.assertEqual(remove_projected_ring_beam_seams(self.path, self.model), 2)
                root = ET.parse(self.path).getroot()
                fill = root.find('.//*[@id="original-face"]')
                self.assertEqual(fill.get("d"), "M0 4H10V6H0Z")
                self.assertIn("fill:url(#hatch)", fill.get("style"))
                self.assertIn("stroke:none!important", fill.get("style"))
                matrix = _transform(transform)
                strokes = self.strokes()
                def line(a, b):
                    return LineString([(matrix @ (*p, 1))[:2] for p in (a, b)])
                self.assertLess(strokes.distance(line((0, 4.5), (0, 5.5))), .002)
                self.assertGreater(strokes.distance(line((2, 4), (8, 4))), .1)

    def test_unlinked_and_noninserted_beams_do_not_change_the_svg(self):
        for properties in ({"ReplacesWallBand": False}, {"SourceWall": self.other_wall.GlobalId}):
            with self.subTest(properties=properties):
                ifcopenshell.api.pset.edit_pset(self.model, pset=self.pset, properties={
                    "SourceWall": self.wall.GlobalId, "ReplacesWallBand": True, **properties,
                })
                self.svg('<path d="M0 4H10"/>', '<path d="M0 4H10"/>')
                before = self.path.read_bytes()
                self.assertEqual(remove_projected_ring_beam_seams(self.path, self.model), 0)
                self.assertEqual(self.path.read_bytes(), before)

    def test_cleanup_is_an_explicit_drawing_option_and_off_for_plans_and_views(self):
        from ifc_utils import House
        house = House("Seams")
        house.storey("Ground", elevation=0)
        section = house.add_drawing("Section", 0, 0, 2, 5, view="elevation", direction=(0, 1, 0),
                                    hide_projected_ring_beam_seams=True)
        exterior = house.add_drawing("Exterior", 0, -10, 2, 5, view="elevation", direction=(0, 1, 0))
        plan = house.add_drawing("Plan", 0, 0, 2, 5)
        self.assertTrue(ifcopenshell.util.element.get_pset(section.element, "EPset_Drawing", "HideProjectedRingBeamSeams"))
        for drawing in (exterior, plan):
            self.assertIsNone(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "HideProjectedRingBeamSeams"))


if __name__ == "__main__":
    unittest.main()
