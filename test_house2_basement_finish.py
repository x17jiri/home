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

    def test_finish_uses_the_same_polygons_as_the_basement_floors(self):
        v = self.v
        for floor in v["basement_room_floors"]:
            expected = self.footprint(floor)
            for layers in (v["basement_ceiling_insulation"], v["basement_ceiling_wood"]):
                finish = next(part for part in layers if f"{floor.room_id}." in part.Name)
                actual = self.footprint(finish)
                self.assertLess(actual.symmetric_difference(expected).area, 1e-9)
                self.assertAlmostEqual(finish.area, floor.area)

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

    def test_ceiling_layout_bounds_follow_physical_wall_centres(self):
        v = self.v
        for identifier, names in (
            ("S.01", ("east", "garden_rooms", "s01_s02", "back")),
            ("S.02", ("s01_s02", "garden_rooms", "west", "back")),
            ("S.03", ("east", "front", "s03_s04", "garden_rooms")),
            ("S.04", ("s03_s04", "front", "s04_s05", "garden_rooms")),
            ("S.05", ("s04_s05", "front", "west", "garden_rooms")),
        ):
            expected = []
            for index, name in enumerate(names):
                lo, hi = self.bounds(v[f"wall_basement_{name}"])
                axis = index % 2
                expected.append((lo[axis]+hi[axis])/2)
            np.testing.assert_allclose(v["basement_ceiling_layout_bounds"][identifier], expected)

    def test_garden_rooms_use_wall_centre_layouts_and_actual_face_bearings(self):
        v = self.v
        for identifier, edge_gaps in (("S.01", (.02, .045)), ("S.02", (.045, .02))):
            slab, = v["basement_ceilings_by_room"][identifier]
            x0, y0, x1, y1 = v["basement_rooms_by_id"][identifier].bounds
            cx0, cy0, cx1, cy1 = v["basement_ceiling_layout_bounds"][identifier]
            self.assertEqual(slab.structure, tuple(["beam"]+["space", "wide", "space", "beam"]*6))
            self.assertEqual(len(slab.beams), 7)
            self.assertAlmostEqual(slab.length, 3.75)
            self.assertAlmostEqual(slab.width, 3.91)
            self.assertAlmostEqual(slab.start[0]+slab.width/2, (cx0+cx1)/2)
            self.assertAlmostEqual(cy0-slab.start[1], .0625)
            self.assertAlmostEqual(slab.end[1]-cy1, .0625)
            self.assertAlmostEqual(y0-slab.start[1], .1875)
            self.assertAlmostEqual(slab.end[1]-y1, .2125)
            self.assertAlmostEqual(slab.block_start_offset, y0-slab.start[1])
            self.assertAlmostEqual(slab.block_end_offset, slab.end[1]-y1)
            self.assertAlmostEqual(slab.start[0]-x0, edge_gaps[0])
            self.assertAlmostEqual(x1-(slab.start[0]+slab.width), edge_gaps[1])
        middle_lo, middle_hi = self.bounds(v["wall_basement_s03_s04"])
        stair_lo, stair_hi = self.bounds(v["wall_basement_s04_s05"])
        slab = v["basement_ceiling_s04"]
        self.assertAlmostEqual(slab.start[0], (middle_lo[0]+middle_hi[0])/2)
        self.assertAlmostEqual(slab.end[0], (stair_lo[0]+stair_hi[0])/2)

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

    def test_miako_omissions_do_not_trim_the_room_finish_polygons(self):
        v = self.v
        for identifier in ("S.04", "S.05"):
            coverage = unary_union([Polygon(slab.footprint)
                                    for slab in v["basement_ceilings_by_room"][identifier]])
            for layers in (v["basement_ceiling_insulation"], v["basement_ceiling_wood"]):
                layer = next(part for part in layers if f"{identifier}." in part.Name)
                self.assertGreater(self.footprint(layer).difference(coverage).area, 1e-6)

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

    def test_s05_has_an_independent_editable_specification(self):
        v = self.v
        slab = v["basement_ceiling_s05"]
        self.assertEqual(len(slab.beams), 4)
        self.assertAlmostEqual(slab.length, 2.5)
        self.assertAlmostEqual(v["basement_s05_x0"]-slab.start[0], .125)
        self.assertAlmostEqual(slab.end[0]-v["basement_s05_x1"], .15)
        self.assertAlmostEqual(slab.start[1]-v["basement_s05_y1"], .015)

        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "basement_ceiling_s05"
                                  for target in node.targets))
        structure = next(keyword.value for keyword in assignment.value.keywords if keyword.arg == "structure")
        structure.elts.extend(ast.Constant(value=item) for item in ("space", "wide", "space", "beam"))
        ast.fix_missing_locations(tree)
        modified = {"__file__": str(source)}
        with patch.object(sys, "argv", [str(source)]), patch.object(House, "write"), \
             patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            exec(compile(tree, str(source), "exec"), modified)
        changed = modified["basement_ceiling_s05"]
        self.assertEqual(len(changed.beams), len(slab.beams)+1)
        self.assertAlmostEqual(changed.width-slab.width, .625)
        np.testing.assert_allclose(changed.beam_centerlines[:-1], slab.beam_centerlines)
        for key in ("ceiling_stairway", "basement_ceiling_s03", "basement_ceiling_s04"):
            self.assertEqual(modified[key].structure, v[key].structure)
            np.testing.assert_allclose(modified[key].beam_centerlines, v[key].beam_centerlines)

    def test_s05_front_section_can_reach_the_wall_without_a_stair_opening(self):
        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "basement_ceiling_s05_front"
                                  for target in node.targets))
        structure = next(keyword for keyword in assignment.value.keywords if keyword.arg == "structure")

        def build(rows):
            structure.value = ast.List(elts=[ast.Constant(value=item) for item in rows], ctx=ast.Load())
            ast.fix_missing_locations(tree)
            result = {"__file__": str(source)}
            with patch.object(sys, "argv", [str(source), "basement_ceiling2"]), patch.object(House, "write"), \
                 patch.object(Drawing, "render"), redirect_stdout(StringIO()):
                exec(compile(tree, str(source), "exec"), result)
            return result

        v = build(["beam", "space", "axis", "beam"]+["space", "wide", "space", "beam"]*4)
        street_edge = min(y for x, y in v["basement_ceiling_s05_front"].footprint)
        self.assertLess(street_edge, v["basement_s05_y0"])
        self.assertEqual(v["basement_stair_opening_length"], 0)
        self.assertEqual(v["basement_stair_opening_end_y"], v["basement_s05_y0"])
        self.assertFalse(any(a.Name == "S.05 clear ceiling opening from inside street wall"
                             for a in v["house"].model.by_type("IfcAnnotation")))

        # Shortening only the editable section must restore the opening and dimension.
        modified = build(["beam", "space", "wide", "space", "beam"])
        edge = min(y for x, y in modified["basement_ceiling_s05_front"].footprint)
        self.assertGreater(modified["basement_stair_opening_length"], 0)
        self.assertAlmostEqual(modified["basement_stair_opening_length"], edge-modified["basement_s05_y0"])
        self.assertTrue(any(a.Name == "S.05 clear ceiling opening from inside street wall"
                            for a in modified["house"].model.by_type("IfcAnnotation")))

    def test_basement_beam_shells_do_not_overlap_each_other(self):
        shells = [self.bounds(shell) for slab in self.v["basement_ceiling_slabs"] for shell in slab.beam_shells]
        self.assertTrue(shells)
        for index, (first_lo, first_hi) in enumerate(shells):
            for second_lo, second_hi in shells[index+1:]:
                overlap = np.minimum(first_hi, second_hi)-np.maximum(first_lo, second_lo)
                self.assertFalse(np.all(overlap > 1e-6), overlap)


if __name__ == "__main__":
    unittest.main()
