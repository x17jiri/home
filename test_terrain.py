"""Terrain projection, export persistence and masking order in elevations."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np

from drawing_terrain import add_terrain_overlay
from ifc_utils import House


SVG = '''<svg xmlns="http://www.w3.org/2000/svg"
    width="100mm" height="100mm" viewBox="0 0 100 100">
  <defs><pattern id="earth" width="6" height="6" patternUnits="userSpaceOnUse"/></defs>
  <g class="section target-view-ELEVATIONVIEW"><path id="basement" d="M0,0 L100,100"/></g>
  <g id="annotation" transform="translate(2,3)"><text x="1" y="90">Below ground label</text></g>
  <g class="section-outlines"><path id="outline" d="M0,0 L100,100"/></g>
  <polyline class="drawing-terrain-source" points="0,0 1,1"/>
</svg>'''
NS = {"s": "http://www.w3.org/2000/svg"}


class TerrainTests(unittest.TestCase):
    def test_profile_projects_after_ifc_reload_in_all_views_and_mirroring(self):
        source = [(0, 417), (3, 418), (6, 417.5)]
        for mirror in (False, True):
            for direction in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Terrain", mirror_x=mirror)
                    drawing = house.add_drawing("Elevation", 1, 1.5, 4, 5,
                                                view="elevation", direction=direction)
                    convert = Mock(side_effect=lambda z: z - 417)
                    terrain = drawing.add_terrain(source, earth_to_z=convert)
                    self.assertEqual(convert.call_count, 3)
                    props = ifcopenshell.util.element.get_pset(terrain, "BBIM_DrawingTerrain")
                    self.assertEqual(json.loads(props["Profile"]), [list(p) for p in source])
                    self.assertEqual(json.loads(props["ModelProfile"]), [[0, 0], [3, 1], [6, .5]])
                    # The converter is no longer available after writing/reopening.
                    model = ifcopenshell.file.from_string(house._export_model().to_string())
                    exported_drawing = model.by_guid(drawing.element.GlobalId)
                    world_to_camera = np.linalg.inv(ifcopenshell.util.placement.get_local_placement(
                        exported_drawing.ObjectPlacement))
                    expected = []
                    for horizontal, height in source:
                        world = np.array((1, horizontal, height-417, 1.) if direction[0]
                                         else (horizontal, 1.5, height-417, 1.))
                        if mirror:
                            world[0] *= -1
                        camera = world_to_camera @ world
                        expected.append((50 + camera[0]*10, 50 - camera[1]*10))
                    with TemporaryDirectory() as directory:
                        path = Path(directory) / "elevation.svg"
                        path.write_text(SVG)
                        add_terrain_overlay(path, exported_drawing, width_mm=100, view_box=(0, 0, 100, 100))
                        root = ET.fromstring(path.read_text())
                        line = root.find('.//s:polyline[@class="terrain-line"]', NS)
                        points = [tuple(map(float, p.split(","))) for p in line.get("points").split()]
                        np.testing.assert_allclose(points, sorted(expected), atol=1e-9)
                        self.assertIn("stroke-width:0.35", line.get("style"))
                        hatch = root.find('.//s:polygon[@class="terrain-hatch"]', NS)
                        hatch_points = [tuple(map(float, p.split(","))) for p in hatch.get("points").split()]
                        np.testing.assert_allclose(hatch_points[:3], points)
                        np.testing.assert_allclose(hatch_points[3:], [(x, y+4) for x, y in reversed(points)])
                        self.assertEqual(convert.call_count, 3)

    def test_model_overlays_are_masked_and_transformed_annotations_stay_above(self):
        house = House("Mask order")
        drawing = house.add_drawing("Elevation", 0, -1, 4, 5, view="elevation", direction=(0, 1, 0))
        drawing.add_terrain([(0, 0), (3, 1), (6, .5)])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "elevation.svg"
            path.write_text(SVG)
            add_terrain_overlay(path, drawing.element, width_mm=100, view_box=(0, 0, 100, 100))
            first = path.read_text()
            root = ET.fromstring(first)
            children = list(root)
            model = root.find('s:g[@class="terrain-model"]', NS)
            overlay = root.find('s:g[@class="terrain-overlays"]', NS)
            annotation = root.find('s:g[@id="annotation"]', NS)
            self.assertLess(children.index(model), children.index(overlay))
            self.assertLess(children.index(overlay), children.index(annotation))
            self.assertEqual(annotation.get("transform"), "translate(2,3)")
            self.assertIsNotNone(model.find('s:g[@class="section-outlines"]', NS))
            mask = overlay.find('s:polygon[@class="terrain-mask"]', NS)
            self.assertIn("fill:white", mask.get("style"))
            self.assertTrue(mask.get("points").endswith("0,100"))
            add_terrain_overlay(path, drawing.element, width_mm=100, view_box=(0, 0, 100, 100))
            self.assertEqual(path.read_text(), first)

    def test_terrain_is_drawing_scoped_and_other_drawings_are_untouched(self):
        house = House("Drawing scope")
        drawing = house.add_drawing("Exterior", 0, -1, 4, 5, view="elevation", direction=(0, 1, 0))
        other = house.add_drawing("Section", 0, 0, 4, 5, view="elevation", direction=(0, 1, 0))
        terrain = drawing.add_terrain([(0, 0), (6, 0)])
        self.assertIn(terrain, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertFalse(terrain.ContainedInStructure)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text(SVG)
            add_terrain_overlay(path, other.element, width_mm=100, view_box=(0, 0, 100, 100))
            self.assertEqual(path.read_text(), SVG)

    def test_invalid_profiles_do_not_create_partial_annotations(self):
        house = House("Validation")
        drawing = house.add_drawing("Elevation", 0, -1, 4, 5, view="elevation", direction=(0, 1, 0))
        original_members = drawing.group.IsGroupedBy[0].RelatedObjects
        for profile, options in (([(0, 0)], {}), ([(0, 0), (0, 1)], {}),
                                 ([(0, 0), (2, 0), (1, 0)], {}),
                                 ([(0, 0), (1, 0)], {"earth_to_z": lambda z: float("nan")}),
                                 ([(0, 0), (1, 0)], {"hatch_depth": -1}),
                                 ([(0, 0), (1, 0)], {"line_width": 0}),
                                 ([(0, 0), (1, 0)], {"hatch": "unknown"})):
            with self.subTest(profile=profile, options=options), self.assertRaises(ValueError):
                drawing.add_terrain(profile, **options)
        self.assertEqual(drawing.group.IsGroupedBy[0].RelatedObjects, original_members)
        plan = house.add_drawing("Plan", 0, 0, 1, 5)
        with self.assertRaisesRegex(ValueError, "elevation"):
            plan.add_terrain([(0, 0), (1, 0)])


if __name__ == "__main__":
    unittest.main()
