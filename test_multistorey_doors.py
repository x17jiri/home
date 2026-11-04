"""One continuous door, with real openings in each affected wall and floor."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import House


class MultiStoreyDoorTests(unittest.TestCase):
    def fixture(self, *, reverse=False):
        house = House("Continuous doorway")
        basement = house.storey("Basement", elevation=-2.5)
        ground = house.storey("Ground", elevation=0)
        lower = basement.wall((0, 0), (5, 0), thickness=.3, height=2.25)
        ends = ((5, 0), (0, 0)) if reverse else ((0, 0), (5, 0))
        upper = ground.wall(*ends, thickness=.2, height=3)
        floor = ground.floor_layer("Floor", outline=((0, .1), (5, .1), (5, 4), (0, 4)), thickness=.25)
        return house, basement, ground, lower, upper, floor

    @staticmethod
    def shape(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        return ifcopenshell.geom.create_shape(settings, element)

    @classmethod
    def volume(cls, element):
        shape = cls.shape(element)
        return ifcopenshell.util.shape.get_volume(shape.geometry)

    @staticmethod
    def selected(drawing):
        rule = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include")
        return (ifcopenshell.util.selector.filter_elements(drawing.house.model, rule)
                if rule else set(drawing.house.model.by_type("IfcElement")))

    def add_door(self, lower, upper, floor=None, **kwargs):
        return lower.add_door(at=2, width=.9, opening_width=1,
                              sill_height=1.25, height=3.25, clear_height=2,
                              through_walls=[upper],
                              through_elements=[] if floor is None else [floor], **kwargs)

    def test_one_full_height_door_cuts_different_wall_thicknesses_and_floor(self):
        house, basement, ground, lower, upper, floor = self.fixture()
        before = [self.volume(e) for e in (lower, upper, floor)]
        door = self.add_door(lower, upper, floor)
        self.assertEqual(house.model.by_type("IfcDoor"), [door])
        self.assertEqual(ifcopenshell.util.element.get_container(door), basement.element)
        self.assertAlmostEqual(door.OverallHeight, 2)
        self.assertAlmostEqual(door.OverallWidth, .9)
        self.assertEqual(len(door.FillsVoids), 1)
        primary = door.FillsVoids[0].RelatingOpeningElement
        self.assertEqual(primary.VoidsElements[0].RelatingBuildingElement, lower)
        placement = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
        np.testing.assert_allclose(placement[:3, 3], (2.05, 0, -1.25))
        self.assertEqual(lower._openings, [(2, 3, 1.25, 3.25)])
        self.assertEqual(upper._openings, [(2, 3, 0, .75)])
        after = [self.volume(e) for e in (lower, upper, floor)]
        np.testing.assert_allclose(np.subtract(before, after), (.3, .15, .0125), atol=1e-8)
        for element in (upper, floor):
            opening, = [r.RelatedOpeningElement for r in element.HasOpenings]
            self.assertEqual(ifcopenshell.util.element.get_pset(opening, "BBIM_DoorOpening", "Door"), door.GlobalId)
        plan = ifcopenshell.util.representation.get_representation(door, "Plan", "Body", "PLAN_VIEW")
        plan_z = placement[2, 3]+plan.Items[0].MappingTarget.LocalOrigin.Coordinates[2]
        self.assertGreater(plan_z, .25)
        self.assertLess(plan_z, .75)
        with TemporaryDirectory() as directory:
            exported = ifcopenshell.open(str(house.write(Path(directory)/"door.ifc")))
            self.assertEqual(len(exported.by_type("IfcDoor")), 1)
            self.assertEqual(len(exported.by_guid(door.GlobalId).FillsVoids), 1)

    def test_reversed_wall_direction_projects_opening_and_keeps_world_position(self):
        _, _, _, lower, upper, _ = self.fixture(reverse=True)
        door = self.add_door(lower, upper)
        self.assertEqual(upper._openings, [(2, 3, 0, .75)])
        shape = self.shape(upper.HasOpenings[0].RelatedOpeningElement)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max()), (2, 3), atol=1e-8)
        self.assertAlmostEqual(ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)[2, 3], -1.25)

    def test_upper_wall_can_host_door_with_negative_sill(self):
        _, _, ground, lower, upper, _ = self.fixture()
        door = upper.add_door(at=2, width=.9, sill_height=-1.25, height=.75, through_walls=[lower])
        self.assertEqual(ifcopenshell.util.element.get_container(door), ground.element)
        self.assertAlmostEqual(door.OverallHeight, 2)
        self.assertEqual(lower._openings, [(2, 2.9, 1.25, 2.25)])

    def test_drawings_before_and_after_door_include_it_only_with_affected_storeys(self):
        house, basement, ground, lower, upper, _ = self.fixture()
        unrelated = house.storey("Upper", elevation=3)
        before = house.add_drawing("Ground before", x=2.5, y=0, z=.5, radius=5, storeys=[ground])
        door = self.add_door(lower, upper)
        self.assertIn(door, self.selected(before))
        self.assertIn(door.id(), before._annotated_doors)
        for name, storeys, expected in (("Basement", [basement], True), ("Ground", [ground], True),
                                       ("Other", [unrelated], False), ("Empty", [], False)):
            with self.subTest(name=name):
                drawing = house.add_drawing(name, x=2.5, y=0, z=.5, radius=5, storeys=storeys)
                self.assertEqual(door in self.selected(drawing), expected)
                self.assertEqual(door.id() in drawing._annotated_doors, expected)
        walls = json.loads(ifcopenshell.util.element.get_pset(door, "EPset_Door", "OpeningWalls"))
        self.assertEqual(walls, [lower.GlobalId, upper.GlobalId])

    def test_facade_layers_copy_the_continuous_doorway_across_the_storey_gap(self):
        house, _, _, lower, upper, _ = self.fixture()
        self.add_door(lower, upper)
        for wall, other, start, height in ((lower, upper, 0, 2.75), (upper, lower, .25, 2.75)):
            with self.subTest(host=wall.storey.name):
                facade = house.add_facade_layer(wall, offset=.2, thickness=.005,
                                               start_height=start, height=height, opening_walls=[other])
                uncut = wall.length*height*.005
                overlap = ((.25-(-1.25)) if wall is lower else (.75-.25))
                self.assertAlmostEqual(uncut-self.volume(facade), overlap*.005, places=8)

    def test_invalid_additional_walls_fail_before_creating_any_openings(self):
        for kind in ("parallel", "aligned", "height", "duplicate", "foreign", "overlap", "too tall"):
            with self.subTest(kind=kind):
                house, _, ground, lower, upper, _ = self.fixture()
                kwargs = dict(at=2, width=.9, opening_width=1, sill_height=1.25, height=3.25)
                walls = [upper]
                if kind == "parallel":
                    walls = [ground.wall((2, 0), (2, 5), thickness=.2, height=3)]
                elif kind == "aligned":
                    walls = [ground.wall((0, 1), (5, 1), thickness=.2, height=3)]
                elif kind == "height":
                    storey = house.storey("Far above", elevation=10)
                    walls = [storey.wall((0, 0), (5, 0), thickness=.2, height=3)]
                elif kind == "duplicate":
                    walls = [upper, upper]
                elif kind == "foreign":
                    foreign = House("Foreign").storey("Ground", elevation=0)
                    walls = [foreign.wall((0, 0), (5, 0), thickness=.2, height=3)]
                elif kind == "overlap":
                    upper.add_opening(at=2, width=1, height=1)
                elif kind == "too tall":
                    kwargs["height"] = 7
                old_elements = len(house.model.by_type("IfcElement"))
                with self.assertRaises(ValueError):
                    lower.add_door(**kwargs, through_walls=walls)
                self.assertFalse(lower.HasOpenings)
                self.assertEqual(len(house.model.by_type("IfcElement")), old_elements)

    def test_single_wall_height_validation_is_preserved(self):
        _, _, _, lower, _, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, "fit within the wall height"):
            lower.add_door(at=2, width=.9, sill_height=1.25, height=3.25)


if __name__ == "__main__":
    unittest.main()
