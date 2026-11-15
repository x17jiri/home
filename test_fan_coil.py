import tempfile
from pathlib import Path
import unittest

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import numpy as np

from ifc_utils import House


class FanCoilTests(unittest.TestCase):
    def test_body_has_requested_size_and_real_mounting_height_after_export(self):
        house = House("Fan coil")
        floor = house.storey("Upper", elevation=3)
        unit = floor.fan_coil("FCU 1", center=(2, 4), size=(1.0, .25, .32),
                              start_height=2.2, rotation=90)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"unit.ifc"
            house.write(path)
            saved = ifcopenshell.open(path).by_guid(unit.GlobalId)
            self.assertEqual(saved.is_a(), "IfcUnitaryEquipment")
            self.assertEqual(saved.ObjectType, "WALL_MOUNTED_FAN_COIL")
            self.assertEqual(saved.PredefinedType, "USERDEFINED")
            self.assertEqual(ifcopenshell.util.element.get_container(saved).Name, "Upper")
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            shape = ifcopenshell.geom.create_shape(settings, saved)
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
            np.testing.assert_allclose(vertices.min(axis=0), (1.875, 3.5, 5.2), atol=1e-8)
            np.testing.assert_allclose(vertices.max(axis=0), (2.125, 4.5, 5.52), atol=1e-8)

    def test_overhead_plan_and_label_stay_below_the_cut_without_lowering_the_unit(self):
        house = House("Overhead unit")
        floor = house.storey("Ground", elevation=.25)
        for height in (2.1, 2.5):
            unit = floor.fan_coil(f"FCU {height}", center=(0, 0), start_height=height)
            placement = ifcopenshell.util.placement.get_local_placement(unit.ObjectPlacement)
            self.assertAlmostEqual(placement[2, 3], .25+height)
            plan = ifcopenshell.util.representation.get_representation(unit, "Plan", "Body", "PLAN_VIEW")
            mapping = ifcopenshell.util.placement.get_mappeditem_transformation(plan.Items[0])
            self.assertAlmostEqual((placement @ mapping)[2, 3], .27)
            label = next(o for o in house.model.by_type("IfcAnnotation") if o.Name == unit.Name+" Label")
            self.assertAlmostEqual(ifcopenshell.util.placement.get_local_placement(label.ObjectPlacement)[2, 3], .27)

    def test_plan_symbol_clears_the_local_floor_finish(self):
        house = House("Finished floor")
        floor = house.storey("Ground", elevation=.25)
        floor.floor_layer("Room floor", outline=((0, 0), (4, 0), (4, 4), (0, 4)), thickness=.15,
                          insulation_thickness=.08, insulation_material="Insulation")
        floor.floor_layer("Higher adjacent floor", outline=((5, 0), (8, 0), (8, 4), (5, 4)), thickness=.4)
        unit = floor.fan_coil("FCU", center=(2, 2), start_height=2.1)
        placement = ifcopenshell.util.placement.get_local_placement(unit.ObjectPlacement)
        plan = ifcopenshell.util.representation.get_representation(unit, "Plan", "Body", "PLAN_VIEW")
        mapping = ifcopenshell.util.placement.get_mappeditem_transformation(plan.Items[0])
        self.assertAlmostEqual((placement @ mapping)[2, 3], .25+.15+.02)
        self.assertAlmostEqual(placement[2, 3], .25+2.1)
        label = next(o for o in house.model.by_type("IfcAnnotation") if o.Name == "FCU Label")
        self.assertAlmostEqual(ifcopenshell.util.placement.get_local_placement(label.ObjectPlacement)[2, 3], .42)

    def test_floor_console_has_feet_top_grille_and_rotates_parallel_to_the_wall(self):
        house = House("Console")
        floor = house.storey("Ground", elevation=0)
        unit = floor.fan_coil("Bathroom FCU", center=(2, 3), size=(.8, .15, .6),
                              start_height=.15, rotation=90, form="console")
        self.assertEqual(unit.ObjectType, "FLOOR_MOUNTED_FAN_COIL")
        self.assertEqual(ifcopenshell.util.element.get_pset(unit, "BBIM_FanCoil", "Form"), "console")
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, unit)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        np.testing.assert_allclose(vertices.min(axis=0), (1.925, 2.6, .15), atol=1e-8)
        np.testing.assert_allclose(vertices.max(axis=0), (2.075, 3.4, .75), atol=1e-8)
        body = ifcopenshell.util.representation.get_representation(unit, "Model", "Body", "MODEL_VIEW")
        # Grille points upward; feet start on the requested finished floor.
        self.assertAlmostEqual(body.Items[1].Position.Location.Coordinates[2], .594)
        for foot in body.Items[-2:]:
            self.assertAlmostEqual(foot.Position.Location.Coordinates[2], 0)

    def test_invalid_arguments_leave_no_equipment(self):
        house = House("Validation")
        floor = house.storey("Ground", elevation=0)
        for options in ({"size": (0, .2, .3)}, {"size": (1, .2)},
                        {"size": (1, float("nan"), .3)}, {"start_height": -1},
                        {"rotation": float("inf")}, {"color": "invalid"}, {"form": "invalid"}):
            with self.subTest(options=options), self.assertRaises((ValueError, TypeError)):
                floor.fan_coil("Invalid", center=(0, 0), **options)
        self.assertFalse(house.model.by_type("IfcUnitaryEquipment"))


if __name__ == "__main__":
    unittest.main()
