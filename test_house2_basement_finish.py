"""Basement ceiling finish geometry, openings and finished-height dimensions."""

from contextlib import redirect_stdout
from io import StringIO
import ast
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
from shapely.ops import unary_union

from ifc_utils import Drawing, House


class BasementCeilingFinishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house2.py")
        with patch.object(sys, "argv", [str(source), "aa", "bb", "basement_ceiling", "basement_ceiling2"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))

    @staticmethod
    def bounds(obj):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, obj)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return points.min(axis=0), points.max(axis=0)

    @staticmethod
    def footprint(obj):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, obj)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        faces = np.asarray(shape.geometry.faces).reshape(-1, 3)
        triangles = [Polygon(vertices[face, :2]) for face in faces]
        return unary_union([triangle for triangle in triangles if triangle.area > 1e-10])

    def test_configured_insulation_then_wood_are_below_the_structural_ceiling(self):
        v = self.v
        self.assertEqual(len(v["basement_ceiling_insulation"]), 5)
        self.assertEqual(len(v["basement_ceiling_wood"]), 5)
        for insulation, wood in zip(v["basement_ceiling_insulation"], v["basement_ceiling_wood"]):
            ilo, ihi = self.bounds(insulation)
            wlo, whi = self.bounds(wood)
            self.assertAlmostEqual(ihi[2], v["BASEMENT_WALL_TOP_Z"])
            self.assertAlmostEqual(ihi[2]-ilo[2], v["BASEMENT_CEILING_INSULATION_THICKNESS"])
            self.assertAlmostEqual(ilo[2], whi[2])
            self.assertAlmostEqual(whi[2]-wlo[2], v["BASEMENT_CEILING_WOOD_THICKNESS"])
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
        for identifier, insulation in zip(v["basement_ceilings_by_room"], v["basement_ceiling_insulation"]):
            actual = self.footprint(insulation)
            expected = v["basement_rooms_by_id"][identifier].intersection(v["basement_ceiling_coverage_by_room"][identifier])
            self.assertLess(actual.symmetric_difference(expected).area, 1e-9)
            self.assertAlmostEqual(insulation.area, expected.area)
        stair_opening = box(v["basement_s05_x0"], v["basement_s05_y0"],
                            v["basement_s05_x1"], v["basement_stair_opening_end_y"])
        cx, cy = v["CHIMNEY_CENTER"]
        half = v["CHIMNEY_SIZE"]/2
        chimney = box(cx-half, cy-half, cx+half, cy+half)
        for finish in v["basement_ceiling_finishes"]:
            region = self.footprint(finish)
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
            self.assertAlmostEqual(json.loads(props["End"])[1], v["basement_ceiling_storey"].elevation-v["BASEMENT_CEILING_FINISH_THICKNESS"])
            self.assertAlmostEqual(props["Length"], v["BASEMENT_WALL_HEIGHT"]-v["BASEMENT_FLOOR_THICKNESS"]-v["BASEMENT_CEILING_FINISH_THICKNESS"])
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

    def test_garden_rooms_have_centred_seven_beam_six_wide_layouts_and_equal_bearings(self):
        v = self.v
        for identifier in ("S.01", "S.02"):
            slab, = v["basement_ceilings_by_room"][identifier]
            x0, y0, x1, y1 = v["basement_rooms_by_id"][identifier].bounds
            self.assertEqual(slab.structure, tuple(["beam"]+["space", "wide", "space", "beam"]*6))
            self.assertEqual(len(slab.beams), 7)
            self.assertAlmostEqual(slab.length, 3.75)
            self.assertAlmostEqual(slab.width, 3.91)
            self.assertAlmostEqual(y0-slab.start[1], .2125)
            self.assertAlmostEqual(slab.end[1]-y1, .2125)
            self.assertAlmostEqual(slab.start[0]-x0, .02)
            self.assertAlmostEqual(x1-(slab.start[0]+slab.width), .02)

    def test_s03_s04_have_one_continuous_specification_and_keep_the_first_rows(self):
        v = self.v
        for identifier, first_row in (
            ("S.03", v["ceiling_room3"]),
            ("S.04", v["ceiling_bathroom"]),
        ):
            x0, _, x1, _ = v["basement_rooms_by_id"][identifier].bounds
            slab, = v["basement_ceilings_by_room"][identifier]
            self.assertGreater(len(slab.beams), 1)
            self.assertEqual(slab.structure[:4], ("beam", "space", "wide", "space"))
            np.testing.assert_allclose(slab.beam_centerlines[0], first_row.beam_centerlines[0])
            self.assertGreaterEqual(x0-slab.start[0], .125-1e-9)
            self.assertGreaterEqual(slab.end[0]-x1, .125-1e-9)
        self.assertEqual(v["basement_chimney_opening"].VoidsElements[0].RelatingBuildingElement,
                         v["basement_ceiling_s04"].topping_element)

    def test_chimney_notch_trims_only_s04_first_block_row_with_blocks_on_both_sides(self):
        v = self.v
        slab = v["basement_ceiling_s04"]
        first = [block for block in slab.blocks if " Block 1." in block.Name]
        rest = [block for block in slab.blocks if " Block 1." not in block.Name]
        xmin, _, xmax, _ = v["basement_chimney_clearance_region"].bounds
        self.assertAlmostEqual(xmin, v["CHIMNEY_CENTER"][0]-v["CHIMNEY_SIZE"]/2-.05)
        self.assertAlmostEqual(xmax, v["CHIMNEY_CENTER"][0]+v["CHIMNEY_SIZE"]/2+.05)
        bounds = [self.bounds(block) for block in first]
        left = [(lo, hi) for lo, hi in bounds if hi[0] <= xmin+1e-8]
        right = [(lo, hi) for lo, hi in bounds if lo[0] >= xmax-1e-8]
        self.assertTrue(left)
        self.assertTrue(right)
        self.assertEqual(len(left)+len(right), len(bounds))
        self.assertAlmostEqual(max(hi[0] for lo, hi in left), xmin)
        self.assertAlmostEqual(min(lo[0] for lo, hi in right), xmax)
        self.assertAlmostEqual(max(hi[0] for lo, hi in right), v["basement_s04_x1"])
        self.assertAlmostEqual(max(self.bounds(block)[1][0] for block in rest), v["basement_s04_x1"])
        self.assertAlmostEqual(min(self.bounds(block)[0][0] for block in first), v["basement_s04_x0"])

    def test_bounded_chimney_opening_is_kept_through_insulation_and_wood(self):
        v = self.v
        for layers in (v["basement_ceiling_insulation"], v["basement_ceiling_wood"]):
            layer = next(part for part in layers if "S.04." in part.Name)
            self.assertTrue(layer.HasOpenings)
            actual = self.footprint(layer)
            self.assertLess(actual.intersection(v["basement_chimney_clearance_region"]).area, 1e-9)
            self.assertEqual(len(actual.interiors), 1)

    def test_appending_a_basement_row_does_not_change_upstairs_or_the_other_room(self):
        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text(), filename=str(source))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "basement_ceiling_s03"
                                  for target in node.targets))
        structure = next(kw.value for kw in assignment.value.keywords if kw.arg == "structure")
        self.assertIsInstance(structure, ast.List)
        structure.elts.extend(ast.Constant(value) for value in ("space", "wide", "space", "beam"))
        ast.fix_missing_locations(tree)
        modified = {"__file__": str(source), "__name__": "basement_extension_test"}
        with patch.object(sys, "argv", [str(source)]), patch.object(House, "write"), redirect_stdout(StringIO()):
            exec(compile(tree, str(source), "exec"), modified)
        original, changed = self.v["basement_ceiling_s03"], modified["basement_ceiling_s03"]
        self.assertEqual(len(changed.beams), len(original.beams)+1)
        self.assertAlmostEqual(changed.width-original.width, .625)
        np.testing.assert_allclose(changed.beam_centerlines[0], original.beam_centerlines[0])
        self.assertAlmostEqual(min(y for x, y in original.footprint)-min(y for x, y in changed.footprint), .625)
        for key in ("ceiling_room3", "ceiling_bathroom", "basement_ceiling_s04"):
            self.assertEqual(modified[key].structure, self.v[key].structure)
            np.testing.assert_allclose(modified[key].beam_centerlines, self.v[key].beam_centerlines)

    def test_s05_reuses_upstairs_stairway_pattern_without_shrinking_the_opening(self):
        v = self.v
        slab = v["basement_ceiling_s05"]
        source = v["ceiling_stairway"]
        self.assertEqual(slab.structure, source.structure)
        self.assertEqual(len(slab.beams), 6)
        self.assertAlmostEqual(slab.length, source.length)
        self.assertAlmostEqual(slab.start[0], source.start[0])
        self.assertAlmostEqual(slab.end[0], source.end[0])
        self.assertAlmostEqual(v["basement_s05_ceiling_shift_y"], .03)
        self.assertAlmostEqual(min(y for x, y in slab.footprint), v["basement_s05_y0"]+3.0)

    def test_basement_beam_shells_do_not_overlap_each_other(self):
        shells = [self.bounds(shell) for slab in self.v["basement_ceiling_slabs"] for shell in slab.beam_shells]
        self.assertTrue(shells)
        for index, (first_lo, first_hi) in enumerate(shells):
            for second_lo, second_hi in shells[index+1:]:
                overlap = np.minimum(first_hi, second_hi)-np.maximum(first_lo, second_lo)
                self.assertFalse(np.all(overlap > 1e-6), overlap)


if __name__ == "__main__":
    unittest.main()
