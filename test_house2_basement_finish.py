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

from ifc_utils import Drawing, DrawingSheet, House


class BasementCeilingFinishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house2.py")
        with patch.object(sys, "argv", [str(source), "aa", "bb", "cc", "basement_ceiling", "basement_ceiling2"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), \
             patch.object(DrawingSheet, "render"), redirect_stdout(StringIO()):
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

    def test_insulation_reserves_15mm_for_plaster_below_the_structural_ceiling(self):
        v = self.v
        self.assertAlmostEqual(v["BASEMENT_CEILING_PLASTER_ALLOWANCE"], .015)
        self.assertEqual(len(v["basement_ceiling_insulation"]), 5)
        self.assertEqual(v["basement_ceiling_finishes"], v["basement_ceiling_insulation"])
        for insulation in v["basement_ceiling_insulation"]:
            ilo, ihi = self.bounds(insulation)
            self.assertAlmostEqual(ihi[2], v["BASEMENT_WALL_TOP_Z"]-.015)
            self.assertAlmostEqual(ihi[2]-ilo[2], v["BASEMENT_CEILING_INSULATION_THICKNESS"])
            self.assertAlmostEqual(ilo[2], v["BASEMENT_FINISHED_CEILING_Z"])
            self.assertEqual(element.get_material(insulation).Name, v["FLOOR_INSULATION_MATERIAL"])
            self.assertEqual(element.get_container(insulation), v["basement_ceiling_storey"].element)
            self.assertFalse(element.get_pset(insulation, "Pset_SlabCommon", "LoadBearing"))
        self.assertFalse(any((obj.Name or "").startswith("Basement ceiling plasterboard")
                             for obj in v["house"].model.by_type("IfcElement")))

    def test_stair_opening_has_50mm_floor_and_wool_without_a_lower_panel(self):
        v = self.v
        upper = v["ground_stair_opening_board"]
        upper_lo, upper_hi = self.bounds(upper)
        self.assertEqual(element.get_material(upper).Name, "Wood")
        self.assertAlmostEqual(upper_hi[2]-upper_lo[2], .05)
        self.assertAlmostEqual(upper_hi[2], v["ground"].elevation+v["GROUND_FLOOR_THICKNESS"])
        gap = (upper_lo[2]-v["BASEMENT_FINISHED_CEILING_Z"]-v["GROUND_STAIR_OPENING_INSULATION_THICKNESS"])/2
        self.assertAlmostEqual(gap, v["GROUND_STAIR_OPENING_AIR_GAP_THICKNESS"])
        batting = next(e for e in v["house"].model.by_type("IfcAnnotation")
                       if e.Name == "CC rockwool below stair-opening timber board")
        placement = ifcopenshell.util.placement.get_local_placement(batting.ObjectPlacement)
        self.assertAlmostEqual(placement[2, 3], (upper_lo[2]+v["BASEMENT_FINISHED_CEILING_Z"])/2)
        self.assertAlmostEqual(element.get_pset(batting, "BBIM_Batting", "Thickness"), .20)

    def test_sk7_is_shared_in_the_list_and_marked_only_on_cc(self):
        v = self.v
        self.assertEqual(v["CONSTRUCTION_ASSEMBLIES"][7]["layers"], (
            "Dřevo | 50 mm", "Minerální vata | 200 mm",
        ))
        markers = [e for e in v["house"].model.by_type("IfcAnnotation")
                   if element.get_pset(e, "BBIM_HexagonMarker", "Identifier") == "SK7"]
        self.assertEqual(len(markers), 1)
        marker, = markers
        self.assertEqual(marker.Name, "cc Skladba 7 marker")
        placement = ifcopenshell.util.placement.get_local_placement(marker.ObjectPlacement)
        self.assertAlmostEqual(placement[2, 3]-element.get_pset(marker, "BBIM_HexagonMarker", "LineLength"),
                               v["BASEMENT_FINISHED_CEILING_Z"]-.1)

    def test_sk3_preserves_plaster_allowance_and_crosses_the_insulation(self):
        v = self.v
        self.assertEqual(len(v["CONSTRUCTION_ASSEMBLIES"][3]["layers"]), 7)
        self.assertIn("Omítka | 15 mm", v["CONSTRUCTION_ASSEMBLIES"][3]["layers"])
        self.assertFalse(any("Sádrokarton" in layer for layer in v["CONSTRUCTION_ASSEMBLIES"][3]["layers"]))
        for name in ("aa", "bb"):
            marker = next(e for e in v["house"].model.by_type("IfcAnnotation")
                          if e.Name == f"{name} Skladba 3 marker")
            properties = element.get_pset(marker, "BBIM_HexagonMarker")
            self.assertEqual(properties["Identifier"], "SK3")
            placement = ifcopenshell.util.placement.get_local_placement(marker.ObjectPlacement)
            self.assertAlmostEqual(placement[2, 3]-properties["LineLength"],
                                   v["BASEMENT_FINISHED_CEILING_Z"]-.1)

    def test_finish_uses_floor_polygons_except_at_stairs_and_chimney(self):
        v = self.v
        for floor in v["basement_room_floors"]:
            expected = self.footprint(floor)
            if floor.room_id == "S.05" and v["ground_stair_opening_region"] is not None:
                expected = expected.difference(v["ground_stair_opening_region"])
            if floor.room_id == "S.04":
                expected = expected.difference(v["chimney_ceiling_opening_region"])
            for layers in (v["basement_ceiling_insulation"],):
                finish = next(part for part in layers if f"{floor.room_id}." in part.Name)
                actual = self.footprint(finish)
                self.assertLess(actual.symmetric_difference(expected).area, 1e-9)
                self.assertAlmostEqual(finish.area, expected.area)

    def test_chimney_opening_continues_through_both_sides_of_the_slab(self):
        v = self.v
        cx, cy = v["CHIMNEY_CENTER"]
        half = v["CHIMNEY_SIZE"]/2 + .03
        opening_region = box(cx-half, cy-half, cx+half, cy+half)
        self.assertTrue(v["chimney_ceiling_opening_region"].equals(opening_region))
        layers = [v["chodba"], *(part for part in v["basement_ceiling_insulation"]
                                if "S.04." in part.Name)]
        self.assertEqual(len(layers), 2)
        for layer in layers:
            expected = Polygon(layer.outline).difference(opening_region)
            self.assertLess(self.footprint(layer).symmetric_difference(expected).area, 1e-9)
            self.assertAlmostEqual(layer.area, expected.area)
            self.assertAlmostEqual(element.get_pset(layer, "BBIM_FloorLayer", "Area"), expected.area)
            self.assertEqual(len(layer.HasOpenings), 1)
            opening = layer.HasOpenings[0].RelatedOpeningElement
            lo, hi = self.bounds(opening)
            np.testing.assert_allclose(lo[:2], (cx-half, cy-half))
            np.testing.assert_allclose(hi[:2], (cx+half, cy+half))
            layer_lo, layer_hi = self.bounds(layer)
            self.assertLess(lo[2], layer_lo[2])
            self.assertGreater(hi[2], layer_hi[2])

    def test_sections_measure_to_insulation_including_the_plaster_allowance_once(self):
        v = self.v
        for name in ("aa", "bb", "cc"):
            drawing = next(d for d in v["house"]._drawings if d.name == name)
            annotations = [obj for rel in drawing.group.IsGroupedBy for obj in rel.RelatedObjects]
            dimensions = [obj for obj in annotations if obj.Name == "Basement finished floor to insulation underside"]
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
        for identifier in ("S.01", "S.02"):
            slab, = v["basement_ceilings_by_room"][identifier]
            x0, y0, x1, y1 = v["basement_rooms_by_id"][identifier].bounds
            cx0, cy0, cx1, cy1 = v["basement_ceiling_layout_bounds"][identifier]
            self.assertEqual(slab.structure, tuple(["beam"]
                +[item for bay in ("wide", "narrow", "wide", "narrow", "wide")
                  for item in ("space", bay, "space", "beam")]))
            self.assertEqual(len(slab.beams), 6)
            self.assertAlmostEqual(slab.length, 4.25)
            self.assertAlmostEqual(slab.width, 3.035)
            self.assertEqual(slab.direction, (0., 1.))
            self.assertAlmostEqual((slab.start[0]+slab.end[0])/2, (cx0+cx1)/2)
            self.assertAlmostEqual(slab.start[1]+slab.width/2, (cy0+cy1)/2)
            self.assertAlmostEqual(slab.start[0], cx0)
            self.assertAlmostEqual(slab.end[0], cx1)
            self.assertAlmostEqual(x0-slab.start[0], .15)
            self.assertAlmostEqual(slab.end[0]-x1, .15)
            self.assertAlmostEqual(slab.block_start_offset, x0-slab.start[0])
            self.assertAlmostEqual(slab.block_end_offset, slab.end[0]-x1)
            self.assertAlmostEqual(slab.start[1]-y0, .0675)
            self.assertAlmostEqual(y1-(slab.start[1]+slab.width), .0675)
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(hi[0]-lo[0], slab.length)
                self.assertLessEqual(hi[1]-lo[1], .16+1e-9)
                self.assertGreater(lo[1], y0)
                self.assertLess(hi[1], y1)
        first, second = v["basement_ceiling_s01"], v["basement_ceiling_s02"]
        np.testing.assert_allclose([end for start, end in first.beam_centerlines],
                                   [start for start, end in second.beam_centerlines])
        middle_lo, middle_hi = self.bounds(v["wall_basement_s03_s04"])
        stair_lo, stair_hi = self.bounds(v["wall_basement_s04_s05"])
        slab = v["basement_ceiling_s04"]
        self.assertAlmostEqual(slab.start[0], (middle_lo[0]+middle_hi[0])/2)
        self.assertAlmostEqual(slab.end[0], (stair_lo[0]+stair_hi[0])/2)

    def test_s03_is_centred_with_150mm_bearings_and_narrow_bays_near_both_edges(self):
        v = self.v
        slab, = v["basement_ceilings_by_room"]["S.03"]
        x0, y0, x1, y1 = v["basement_rooms_by_id"]["S.03"].bounds
        footprint = Polygon(slab.footprint)
        np.testing.assert_allclose(footprint.centroid.coords[0], ((x0+x1)/2, (y0+y1)/2))
        self.assertEqual(slab.direction, (0., -1.))
        self.assertAlmostEqual(slab.length, 3.5)
        self.assertAlmostEqual(slab.width, 4.91)
        self.assertEqual(len(slab.beams), 9)
        self.assertEqual([item for item in slab.structure if item in ("wide", "narrow")],
                         ["wide", "narrow", "wide", "wide", "wide", "wide", "narrow", "wide"])
        centres = np.array([start[1] for start, end in slab.beam_centerlines])
        np.testing.assert_allclose(-np.diff(centres), (.625, .5, .625, .625, .625, .625, .5, .625))
        self.assertAlmostEqual(footprint.bounds[1]-y0, .035)
        self.assertAlmostEqual(y1-footprint.bounds[3], .035)
        self.assertAlmostEqual(slab.block_start_offset, .15)
        self.assertAlmostEqual(slab.block_end_offset, .15)
        for beam in slab.beam_shells:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(x0-lo[0], .15)
            self.assertAlmostEqual(hi[0]-x1, .15)
            self.assertGreater(lo[1], y0)
            self.assertLess(hi[1], y1)

    def test_s04_straddles_chimney_and_trims_its_first_wide_bay(self):
        v = self.v
        slab = v["basement_ceiling_s04"]
        chimney_lo, chimney_hi = self.bounds(v["chimney"])
        first_lo, first_hi = self.bounds(slab.beam_shells[0])
        _, second_hi = self.bounds(slab.beam_shells[1])
        garden_lo, garden_hi = self.bounds(v["wall_basement_garden_rooms"])
        last_lo, _ = self.bounds(slab.beam_shells[-1])
        front_lo, front_hi = self.bounds(v["wall_basement_front"])
        self.assertAlmostEqual(first_lo[1]-chimney_hi[1], .03)
        self.assertAlmostEqual(chimney_lo[1]-second_hi[1], .035)
        self.assertGreaterEqual(min(first_hi[1], garden_hi[1])-max(first_lo[1], garden_lo[1]), .128)
        self.assertEqual(slab.structure[:5], ("beam", "space", "wide", "space", "beam"))
        for spacing in -np.diff([start[1] for start, end in slab.beam_centerlines]):
            self.assertTrue(np.isclose(spacing, .5) or np.isclose(spacing, .625))
        self.assertGreater(last_lo[1], front_lo[1])
        self.assertLess(last_lo[1], front_hi[1])
        self.assertAlmostEqual(slab.block_start_offset, .15)
        self.assertAlmostEqual(slab.block_end_offset, .15)
        self.assertEqual(len(slab.topping_element.HasOpenings), 1)
        self.assertEqual(v["basement_chimney_opening"].VoidsElements[0].RelatingBuildingElement,
                         slab.topping_element)
        region = v["chimney_ceiling_opening_region"]
        self.assertLess(self.footprint(slab.topping_element).intersection(region).area, 1e-9)
        first_blocks = [block for block in slab.blocks if " Block 1." in block.Name]
        left, right = [], []
        for block in first_blocks:
            lo, hi = self.bounds(block)
            self.assertLess(self.footprint(block).intersection(region).area, 1e-9)
            if hi[0] <= region.bounds[0]+1e-9:
                left.append(hi[0])
            elif lo[0] >= region.bounds[2]-1e-9:
                right.append(lo[0])
            else:
                self.fail("First-bay block still spans the chimney opening")
        self.assertTrue(left)
        self.assertTrue(right)
        self.assertAlmostEqual(max(left), region.bounds[0])
        self.assertAlmostEqual(min(right), region.bounds[2])
        self.assertFalse(any(block.HasOpenings for block in slab.blocks if " Block 1." not in block.Name))
        infills = [obj for obj in v["house"].model.by_type("IfcBuildingElementPart")
                   if element.get_pset(obj, "BBIM_CeilingInfill")]
        self.assertFalse(infills)
        self.assertNotIn("basement_ceiling_s04_chimney_infill", v)

    def test_miako_omissions_do_not_trim_the_room_finish_polygons(self):
        v = self.v
        for identifier in ("S.04", "S.05"):
            coverage = unary_union([Polygon(slab.footprint)
                                    for slab in v["basement_ceilings_by_room"][identifier]])
            for layers in (v["basement_ceiling_insulation"],):
                layer = next(part for part in layers if f"{identifier}." in part.Name)
                self.assertGreater(self.footprint(layer).difference(coverage).area, 1e-6)

    def test_appending_a_basement_row_does_not_change_upstairs_or_the_other_room(self):
        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text(), filename=str(source))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "basement_s03_ceiling_structure"
                                  for target in node.targets))
        structure = assignment.value
        self.assertIsInstance(structure, ast.List)
        structure.elts.extend(ast.Constant(value) for value in ("space", "wide", "space", "beam"))
        ast.fix_missing_locations(tree)
        modified = {"__file__": str(source), "__name__": "basement_extension_test"}
        with patch.object(sys, "argv", [str(source)]), patch.object(House, "write"), redirect_stdout(StringIO()):
            exec(compile(tree, str(source), "exec"), modified)
        original, changed = self.v["basement_ceiling_s03"], modified["basement_ceiling_s03"]
        self.assertEqual(len(changed.beams), len(original.beams)+1)
        self.assertAlmostEqual(changed.width-original.width, .625)
        np.testing.assert_allclose(np.array(changed.beam_centerlines[0])-original.beam_centerlines[0],
                                   ((0, .3125), (0, .3125)))
        np.testing.assert_allclose(Polygon(changed.footprint).centroid.coords,
                                   Polygon(original.footprint).centroid.coords)
        for key in ("ceiling_room3", "ceiling_bathroom", "basement_ceiling_s01", "basement_ceiling_s02",
                    "basement_ceiling_s04", "basement_ceiling_s05", "basement_ceiling_s05_front"):
            self.assertEqual(modified[key].structure, self.v[key].structure)
            np.testing.assert_allclose(modified[key].beam_centerlines, self.v[key].beam_centerlines)

    def test_s05_has_an_independent_editable_specification(self):
        v = self.v
        slab = v["basement_ceiling_s05"]
        self.assertEqual(len(slab.beams), 4)
        self.assertAlmostEqual(slab.length, 2.5)
        self.assertAlmostEqual(v["basement_s05_x0"]-slab.start[0], .125)
        self.assertAlmostEqual(slab.end[0]-v["basement_s05_x1"], .175)
        self.assertAlmostEqual(slab.start[1]-v["basement_s05_y1"], .015)

        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "basement_s05_garden_structure"
                                  for target in node.targets))
        structure = assignment.value
        structure.elts.extend(ast.Constant(value=item) for item in ("space", "wide", "space", "beam"))
        ast.fix_missing_locations(tree)
        modified = {"__file__": str(source)}
        with patch.object(sys, "argv", [str(source)]), patch.object(House, "write"), \
             patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            exec(compile(tree, str(source), "exec"), modified)
        changed = modified["basement_ceiling_s05"]
        self.assertEqual(len(changed.beams), len(slab.beams)+1)
        self.assertAlmostEqual(changed.width-slab.width, .625)
        np.testing.assert_allclose(changed.beam_centerlines[1:], slab.beam_centerlines)
        for key in ("ceiling_stairway", "basement_ceiling_s03", "basement_ceiling_s04", "basement_ceiling_s05_front"):
            self.assertEqual(modified[key].structure, v[key].structure)
            np.testing.assert_allclose(modified[key].beam_centerlines, v[key].beam_centerlines)

    def test_s05_sections_clear_heb_and_leave_1200mm_stair_opening(self):
        v = self.v
        garden, street = v["basement_ceilings_by_room"]["S.05"]
        heb_lo, heb_hi = self.bounds(v["basement_s05_edge_heb"])
        self.assertEqual((len(garden.beams), len(street.beams)), (4, 3))
        self.assertEqual(garden.structure.count("wide"), 3)
        self.assertEqual(street.structure.count("wide"), 2)
        self.assertAlmostEqual(min(y for x, y in garden.footprint)-heb_hi[1], .05)
        self.assertAlmostEqual(heb_lo[1]-max(y for x, y in street.footprint), .05)
        self.assertAlmostEqual(max(y for x, y in garden.footprint)-v["basement_s05_y1"], .015)
        self.assertAlmostEqual(v["basement_stair_opening_length"], 1.27)
        self.assertGreaterEqual(v["basement_stair_opening_length"], v["BASEMENT_S05_MIN_STAIR_OPENING"])
        for slab, is_garden in ((garden, True), (street, False)):
            for part in slab.components:
                lo, hi = self.bounds(part)
                gap = lo[1]-heb_hi[1] if is_garden else heb_lo[1]-hi[1]
                self.assertGreaterEqual(gap, .05-1e-8)
        for name in ("basement_ceiling", "basement_ceiling2"):
            drawing = next(d for d in v["house"]._drawings if d.name == name)
            annotations = [obj for rel in drawing.group.IsGroupedBy for obj in rel.RelatedObjects]
            for side in ("Garden", "Street"):
                dimension = next(obj for obj in annotations if obj.Name == f"S.05 {side} ceiling to HEB clearance")
                self.assertAlmostEqual(element.get_pset(dimension, "BBIM_DimensionSource", "Length"), .05)

    def test_s05_street_section_rejects_insufficient_stair_opening(self):
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

        with self.assertRaisesRegex(ValueError, "at least 1.20 m"):
            build(["beam"]+["space", "wide", "space", "beam"]*3)

        # Shortening only the editable section must restore the opening and dimension.
        modified = build(["beam", "space", "wide", "space", "beam"])
        edge = min(y for x, y in modified["basement_ceiling_s05_front"].footprint)
        self.assertGreaterEqual(modified["basement_stair_opening_length"], 1.2)
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
