import tempfile
from pathlib import Path
import unittest

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import House, _close_door_bodies


def vertices(element):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, element)
    return np.asarray(shape.geometry.verts).reshape(-1, 3).copy()


class GarageDoorTests(unittest.TestCase):
    def test_fills_existing_opening_with_sections_and_a_plan_without_arcs(self):
        house = House("Garage", mirror_x=False)
        storey = house.storey("Basement", elevation=-2.5)
        wall = storey.wall((2, 3), (2, 9), thickness=.25, height=2.5)
        opening = wall.add_opening(at=1, width=3, sill_height=.065, height=2.165)
        original_openings = tuple(wall._openings)
        door = wall.add_garage_door(opening, color="#ffffff")
        self.assertEqual(len(house.model.by_type("IfcOpeningElement")), 1)
        self.assertEqual(tuple(wall._openings), original_openings)
        self.assertEqual(door.FillsVoids[0].RelatingOpeningElement, opening)
        self.assertEqual(ifcopenshell.util.element.get_container(door), storey.element)
        self.assertEqual(door.OperationType, "USERDEFINED")
        self.assertEqual(door.UserDefinedOperationType, "SECTIONAL_OVERHEAD")
        self.assertAlmostEqual(door.OverallWidth, 3)
        self.assertAlmostEqual(door.OverallHeight, 2.1)
        props = ifcopenshell.util.element.get_pset(door, "EPset_Door")
        self.assertEqual(props["SectionCount"], 5)
        self.assertLessEqual(props["SectionHeight"], .5)
        body = ifcopenshell.util.representation.get_representation(door, "Model", "Body", "MODEL_VIEW")
        self.assertEqual(len(body.Items), 9)
        backing = body.Items[3]
        self.assertAlmostEqual(backing.Depth, 2.04)
        self.assertAlmostEqual(backing.SweptArea.OuterCurve.Points.CoordList[2][1], .002)
        points = vertices(door)
        self.assertAlmostEqual(points[:, 1].min(), 4)
        self.assertAlmostEqual(points[:, 1].max(), 7)
        self.assertAlmostEqual(points[:, 2].min(), -2.435)
        self.assertAlmostEqual(points[:, 2].max(), -.335)
        plan = ifcopenshell.util.representation.get_representation(door, "Plan", "Body", "PLAN_VIEW")
        resolved = ifcopenshell.util.representation.resolve_representation(plan)
        self.assertEqual(len(resolved.Items), 3)
        self.assertTrue(all(item.is_a("IfcIndexedPolyCurve")
                            and all(segment.is_a("IfcLineIndex") for segment in item.Segments or ())
                            for item in resolved.Items))
        self.assertTrue(all(len(item.Points.CoordList) in (4, 5) for item in resolved.Items))
        self.assertEqual(_close_door_bodies(house.model), 0)
        np.testing.assert_allclose(vertices(door), points)

    def test_integrates_with_annotations_and_mirrored_export(self):
        for mirror_x in (False, True):
            with self.subTest(mirror_x=mirror_x), tempfile.TemporaryDirectory() as tmp:
                house = House("Garage", mirror_x=mirror_x)
                storey = house.storey("Ground", elevation=0)
                wall = storey.wall((0, 0), (6, 0), thickness=.25, height=3)
                opening = wall.add_opening(at=1, width=3, height=2.2)
                drawing = house.add_drawing("Plan", x=3, y=1, z=1.5, radius=4,
                                            storeys=[storey], right_panel_width=60)
                door = wall.add_garage_door(opening)
                self.assertIn(door.id(), drawing._annotated_doors)
                dimension = drawing.add_opening_dimension(door, finished_floor_height=0)
                self.assertEqual(ifcopenshell.util.element.get_pset(dimension, "BBIM_OpeningDimension", "Opening"), opening.GlobalId)
                drawing.add_lintel(door, 1)
                drawing.add_lintel_legend()
                self.assertEqual(drawing._right_panel_tables[-1]["items"][0]["count"], 1)
                original = vertices(door)
                path = Path(tmp)/"garage.ifc"
                house.write(path)
                saved = ifcopenshell.open(path).by_guid(door.GlobalId)
                points = vertices(saved)
                expected_x = (-4, -1) if mirror_x else (1, 4)
                np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max()), expected_x)
                np.testing.assert_allclose(vertices(door), original)

    def test_rejects_wrong_or_filled_openings_and_invalid_sizes_before_creating_a_door(self):
        house = House("Garage", mirror_x=False)
        storey = house.storey("Ground", elevation=0)
        wall = storey.wall((0, 0), (6, 0), thickness=.25, height=3)
        other = storey.wall((0, 4), (6, 4), thickness=.25, height=3)
        opening = wall.add_opening(at=1, width=3, height=2.2)
        with self.assertRaisesRegex(ValueError, "this wall"):
            other.add_garage_door(opening)
        for options in ({"section_height": 0}, {"frame_width": 1.5}, {"panel_thickness": .3}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                wall.add_garage_door(opening, **options)
        self.assertEqual(len(house.model.by_type("IfcDoor")), 0)
        wall.add_garage_door(opening)
        with self.assertRaisesRegex(ValueError, "already has a filling"):
            wall.add_garage_door(opening)
        self.assertEqual(len(house.model.by_type("IfcDoor")), 1)


if __name__ == "__main__":
    unittest.main()
