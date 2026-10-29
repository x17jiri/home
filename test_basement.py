"""Basement stack, storey ownership and dependent drawing references."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.selector
import numpy as np

from ifc_utils import Drawing, House


class BasementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with patch.object(sys, "argv", [str(source), "found", "aa", "bb", "kanal"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))

    @staticmethod
    def bounds(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return points.min(axis=0), points.max(axis=0)

    def test_footers_plate_and_walls_meet_with_ceiling_space_below_fixed_ground_floor(self):
        v = self.v
        self.assertEqual(v["ground"].elevation, 0)
        self.assertEqual(v["upper"].elevation, v["ground_floor_height"]+v["CEILING_THICKNESS"])
        self.assertAlmostEqual(v["basement"].elevation, -2.5)
        lo, hi = self.bounds(v["foundation_base_plate"])
        self.assertAlmostEqual(lo[2], -2.65)
        self.assertAlmostEqual(hi[2], -2.5)
        for wall in v["foundation_walls"]:
            bottom, top = self.bounds(wall)
            self.assertAlmostEqual(bottom[2], hi[2])
            self.assertAlmostEqual(top[2], -.25)
            self.assertAlmostEqual(top[2]-bottom[2], 2.25)
            self.assertAlmostEqual(v["ground"].elevation-top[2], .25)
        for footer in v["foundation_footers"]:
            bottom, top = self.bounds(footer)
            self.assertAlmostEqual(bottom[2], -3.15)
            self.assertAlmostEqual(top[2], lo[2])

    def test_slab_and_walls_belong_to_basement_and_ceiling_space_has_no_slab(self):
        v = self.v
        self.assertEqual(v["basement"].name, "Basement")
        for element in (v["foundation_base_plate"], *v["foundation_walls"]):
            self.assertEqual(ifcopenshell.util.element.get_container(element), v["basement"].element)
        for footer in v["foundation_footers"]:
            self.assertEqual(ifcopenshell.util.element.get_container(footer), v["foundation"].element)
        self.assertEqual(v["basement"].floor_layers, (v["foundation_base_plate"],))
        self.assertEqual(v["foundation_base_plate"].PredefinedType, "BASESLAB")
        self.assertEqual(v["foundation"].elevation, v["FOUNDATION_FOOTER_BOTTOM_Z"])

    def test_foundation_plan_cuts_footers_and_only_annotates_basement_wall_footprints(self):
        v = self.v
        drawing = next(d for d in v["house"]._drawings if d.name == "Foundation")
        self.assertGreater(drawing.z, v["FOUNDATION_FOOTER_BOTTOM_Z"])
        self.assertLess(drawing.z, v["FOUNDATION_FOOTER_TOP_Z"])
        included = ifcopenshell.util.selector.filter_elements(v["house"].model,
            ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
        self.assertTrue(set(v["foundation_footers"]).issubset(included))
        self.assertTrue(set(v["foundation_walls"]).isdisjoint(included))
        self.assertNotIn(v["foundation_base_plate"], included)
        outlines = [e for rel in drawing.group.IsGroupedBy for e in rel.RelatedObjects
                    if "load-bearing-wall-outline" in (ifcopenshell.util.element.get_pset(e, "EPset_Annotation", "Classes") or "")]
        self.assertEqual(len(outlines), 1)

    def test_insulation_helper_tracks_basement_plate_in_its_new_storey(self):
        v = self.v
        house = House("Basement insulation")
        basement = house.storey("Basement", elevation=v["basement"].elevation)
        plate = basement.floor_layer("Plate", outline=((0, 0), (3, 0), (3, 3), (0, 3)),
                                     thickness=.15, start_height=-.15)
        helper = v["add_foundation_insulation"]
        with patch.dict(helper.__globals__, {"house": house, "basement": basement,
                "foundation_base_plate": plate, "_foundation_insulation_sets": [],
                "_foundation_insulation_wall_types": {}}):
            horizontal, vertical = helper(((0, 0), (3, 0), (3, 3), (0, 3)), thickness=.1, height=.4)
        bottom, top = self.bounds(horizontal)
        self.assertAlmostEqual(bottom[2], -2.75)
        self.assertAlmostEqual(top[2], -2.65)
        for wall in vertical:
            bottom, top = self.bounds(wall)
            self.assertAlmostEqual(bottom[2], -3.05)
            self.assertAlmostEqual(top[2], -2.65)
            self.assertEqual(ifcopenshell.util.element.get_container(wall), basement.element)


if __name__ == "__main__":
    unittest.main()
