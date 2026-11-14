"""Basement ceiling finish geometry, openings and finished-height dimensions."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element as element
import ifcopenshell.util.selector
import numpy as np
from shapely.geometry import Polygon, box

from ifc_utils import Drawing, House


class BasementCeilingFinishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house2.py")
        with patch.object(sys, "argv", [str(source), "aa", "bb", "basement_ceiling2"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))

    @staticmethod
    def bounds(obj):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, obj)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return points.min(axis=0), points.max(axis=0)

    def test_50mm_insulation_then_20mm_wood_are_below_the_structural_ceiling(self):
        v = self.v
        self.assertEqual(len(v["basement_ceiling_insulation"]), 5)
        self.assertEqual(len(v["basement_ceiling_wood"]), 5)
        for insulation, wood in zip(v["basement_ceiling_insulation"], v["basement_ceiling_wood"]):
            ilo, ihi = self.bounds(insulation)
            wlo, whi = self.bounds(wood)
            self.assertAlmostEqual(ihi[2], v["BASEMENT_WALL_TOP_Z"])
            self.assertAlmostEqual(ihi[2]-ilo[2], .05)
            self.assertAlmostEqual(ilo[2], whi[2])
            self.assertAlmostEqual(whi[2]-wlo[2], .02)
            self.assertAlmostEqual(wlo[2], v["BASEMENT_FINISHED_CEILING_Z"])
            np.testing.assert_allclose(ilo[:2], wlo[:2])
            np.testing.assert_allclose(ihi[:2], whi[:2])
            self.assertEqual(element.get_material(insulation).Name, v["FLOOR_INSULATION_MATERIAL"])
            self.assertEqual(element.get_material(wood).Name, "Wood")
            for obj in (insulation, wood):
                self.assertEqual(element.get_container(obj), v["basement_ceiling_storey"].element)
                self.assertFalse(element.get_pset(obj, "Pset_SlabCommon", "LoadBearing"))

    def test_finish_follows_ceiling_coverage_and_keeps_stair_and_chimney_openings(self):
        v = self.v
        for index, (insulation, slab) in enumerate(zip(v["basement_ceiling_insulation"], v["basement_ceiling_slabs"]), 1):
            actual = Polygon(insulation.outline)
            expected = v["basement_rooms_by_id"][f"S.{index:02d}"].intersection(Polygon(slab.footprint))
            self.assertLess(actual.symmetric_difference(expected).area, 1e-9)
        stair_opening = box(v["basement_s05_x0"], v["basement_s05_y0"],
                            v["basement_s05_x1"], v["basement_stair_opening_end_y"])
        cx, cy = v["CHIMNEY_CENTER"]
        half = v["CHIMNEY_SIZE"]/2
        chimney = box(cx-half, cy-half, cx+half, cy+half)
        for finish in v["basement_ceiling_finishes"]:
            region = Polygon(finish.outline)
            self.assertLess(region.intersection(stair_opening).area, 1e-9)
            self.assertLess(region.intersection(chimney).area, 1e-9)

    def test_aa_and_bb_measure_to_wood_without_an_extra_plaster_allowance(self):
        v = self.v
        for name in ("aa", "bb"):
            drawing = next(d for d in v["house"]._drawings if d.name == name)
            annotations = [obj for rel in drawing.group.IsGroupedBy for obj in rel.RelatedObjects]
            dimensions = [obj for obj in annotations if obj.Name == "Basement finished floor to wood ceiling"]
            self.assertEqual(len(dimensions), 1)
            props = element.get_pset(dimensions[0], "BBIM_DimensionSource")
            self.assertAlmostEqual(json.loads(props["End"])[1], v["basement_ceiling_storey"].elevation-.07)
            self.assertAlmostEqual(props["Length"], v["BASEMENT_WALL_HEIGHT"]-v["BASEMENT_FLOOR_THICKNESS"]-.07)
            self.assertFalse(any(obj.Name == "Basement finished floor to plastered ceiling" for obj in annotations))
        ground = next(obj for obj in v["house"].model.by_type("IfcAnnotation")
                      if obj.Name == "Ground finished floor to plastered ceiling")
        end = json.loads(element.get_pset(ground, "BBIM_DimensionSource", "End"))
        self.assertAlmostEqual(end[1], v["ceiling_storey"].elevation-.015)

    def test_structural_basement_ceiling_plan_excludes_the_new_finishes(self):
        v = self.v
        drawing = next(d for d in v["house"]._drawings if d.name == "basement_ceiling2")
        excluded = ifcopenshell.util.selector.filter_elements(v["house"].model,
            element.get_pset(drawing.element, "EPset_Drawing", "Exclude"))
        self.assertTrue(set(v["basement_ceiling_finishes"]).issubset(excluded))


if __name__ == "__main__":
    unittest.main()
