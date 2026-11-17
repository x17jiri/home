"""Garden partition, shared ceiling and independent basement support."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from ifc_utils import Drawing, House


class GardenPartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house2.py")
        with patch.object(sys, "argv", [str(source), "ceiling", "ceiling2"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))

    @staticmethod
    def bounds(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return vertices.min(axis=0), vertices.max(axis=0)

    def test_ground_wall_is_centred_115mm_vpc_partition(self):
        v = self.v
        wall = v["wall_garden_partition_g"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .115)
        self.assertAlmostEqual((hi[0]+lo[0])/2, v["HOUSE_WIDTH"]/2)
        self.assertFalse(ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing"))
        material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                         [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Brick"])
        self.assertIn("partition wall - VPC 115 mm", ifcopenshell.util.element.get_type(wall).Name)

    def test_upper_stairway_masonry_reaches_the_chimney_return_and_ring_beam(self):
        v = self.v
        masonry = v["wall_kitchen_stairway_u"]
        mlo, mhi = self.bounds(masonry)
        self.assertAlmostEqual(mhi[0]-mlo[0], .24)
        self.assertAlmostEqual(mhi[0], v["STAIR_LEFT_X"])
        self.assertAlmostEqual(mlo[1], v["BWT"])
        self.assertAlmostEqual(mhi[1], v["living_room_return_back_y"])
        self.assertTrue(ifcopenshell.util.element.get_pset(masonry, "Pset_WallCommon", "LoadBearing"))
        rings = v["upper_ring_beams"]
        self.assertEqual({beam.source_wall for beam in rings},
                         {*v["upper_exterior_walls"], masonry})
        new_rings = [beam for beam in rings if beam.source_wall == masonry]
        self.assertEqual(len(new_rings), 1)
        ring = new_rings[0]
        rlo, rhi = self.bounds(ring)
        self.assertAlmostEqual(rhi[0]-rlo[0], .24)
        self.assertAlmostEqual(rhi[2]-rlo[2], v["UPPER_RING_BEAM_HEIGHT"])
        np.testing.assert_allclose(rlo[:2], mlo[:2])
        np.testing.assert_allclose(rhi[:2], mhi[:2])
        self.assertTrue(ifcopenshell.util.element.get_pset(ring, "BBIM_RingBeam", "ReplacesWallBand"))
        front_bounds = [self.bounds(beam) for beam in rings if beam.source_wall == v["wall_front_u"]]
        self.assertTrue(any(
            abs(hi[1]-rlo[1]) < 1e-9
            and min(hi[0], rhi[0])-max(lo[0], rlo[0]) > 1e-9
            and min(hi[2], rhi[2])-max(lo[2], rlo[2]) > 1e-9
            for lo, hi in front_bounds
        ))

    def test_removed_upper_bathroom_walls_and_door_leave_a_connected_drywall_return(self):
        v = self.v
        removed = {"Living room - side partition", "Technika - stairway partition",
                   "Toilet - end partition", "Technika - toilet cross partition", "Upper toilet door"}
        self.assertFalse(removed.intersection(e.Name for e in v["house"].model.by_type("IfcElement")))
        horizontal = v["wall_living_room_return_u"]
        chimney_wall = v["wall_living_room_chimney_front_u"]
        masonry = v["wall_kitchen_stairway_u"]
        np.testing.assert_allclose(horizontal.start, (v["STAIR_LEFT_X"], 3.575))
        np.testing.assert_allclose(horizontal.end, (v["living_room_chimney_wall_x"], 3.575))
        np.testing.assert_allclose(chimney_wall.start, horizontal.end)
        self.assertAlmostEqual(masonry.end[1], v["living_room_return_back_y"])
        connections = [{c.RelatingElement, c.RelatedElement}
                       for c in v["house"].model.by_type("IfcRelConnectsPathElements")]
        self.assertIn({horizontal, chimney_wall}, connections)
        self.assertIn({horizontal, masonry}, connections)
        _, return_hi = self.bounds(horizontal)
        chimney_lo, _ = self.bounds(v["chimney"])
        self.assertAlmostEqual(chimney_lo[1]-return_hi[1], 1.025)
        self.assertAlmostEqual(v["living_room_right_wall_front_y"]-return_hi[1], 1.5)

    def test_upper_bathroom_side_wall_has_150mm_jamb_gap_and_joins_both_walls(self):
        v = self.v
        wall = v["wall_upper_bathroom_side_u"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .10)
        self.assertAlmostEqual(v["living_room_door_opening_x"]-hi[0], .15)
        self.assertAlmostEqual(lo[1], v["living_room_return_back_y"])
        self.assertAlmostEqual(hi[1], v["living_room_right_wall_front_y"])
        chimney_lo, chimney_hi = self.bounds(v["chimney"])
        _, parallel_hi = self.bounds(v["wall_living_room_chimney_front_u"])
        _, horizontal_hi = self.bounds(v["wall_living_room_return_u"])
        self.assertAlmostEqual(lo[0]-chimney_hi[0], .925)
        self.assertAlmostEqual(lo[0]-parallel_hi[0], 1.225)
        self.assertAlmostEqual(chimney_lo[1]-horizontal_hi[1], 1.025)
        connections = [{c.RelatingElement, c.RelatedElement}
                       for c in v["house"].model.by_type("IfcRelConnectsPathElements")]
        self.assertIn({wall, v["wall_living_room_return_u"]}, connections)
        self.assertIn({wall, v["wall_living_room_back_u"]}, connections)

    def test_upper_room_polygons_follow_the_new_bathroom_without_gaps_or_overlaps(self):
        v = self.v
        living, bathroom, hallway = (v[k] for k in
                                    ("living_room_outline", "upper_toilet_outline", "upper_hallway_outline"))
        for region in (living, bathroom, hallway):
            self.assertTrue(region.is_valid)
            self.assertEqual(len(region.interiors), 0)
        for a, b in ((living, bathroom), (living, hallway), (bathroom, hallway)):
            self.assertLess(a.intersection(b).area, 1e-9)
        self.assertTrue(bathroom.contains(Point(*v["upper_bathroom_label_position"])))
        self.assertTrue(bathroom.contains(Point(5., 4.5)))
        self.assertTrue(living.contains(Point(5.5, 3.1)))  # Former WC is now kitchen floor.
        self.assertTrue(hallway.contains(Point(5.85, 4.5)))
        self.assertTrue(hallway.covers(v["upper_living_door_threshold"]))
        self.assertEqual(v["upper_toilet_room"].Name, "Koupelna")

        chimney = box(v["CHIMNEY_CENTER"][0]-.2, v["CHIMNEY_CENTER"][1]-.2,
                      v["CHIMNEY_CENTER"][0]+.2, v["CHIMNEY_CENTER"][1]+.2)
        walls = unary_union((
            v["upper_bearing_wall_region"], chimney,
            box(v["upper_kitchen_right_x"], v["BWT"], v["STAIR_LEFT_X"], v["living_room_return_back_y"]),
            box(v["living_room_chimney_face_x"], v["living_room_return_front_y"],
                v["STAIR_LEFT_X"], v["living_room_return_back_y"]),
            box(v["living_room_chimney_face_x"], v["living_room_return_back_y"],
                v["upper_hallway_living_wall_x"], v["CHIMNEY_CENTER"][1]-.2),
            box(v["upper_bathroom_side_wall_left_x"], v["living_room_return_back_y"],
                v["upper_bathroom_side_wall_right_x"], v["living_room_right_wall_front_y"]),
            Polygon((tuple(v["living_room_diagonal_start"]), tuple(v["living_room_diagonal_end"]),
                     (v["LIVING_ROOM_OPENING_END_X"], v["living_room_diagonal_hall_end_y"]),
                     (v["living_room_diagonal_hall_x"](v["living_room_diagonal_start"][1]),
                      v["living_room_diagonal_start"][1]))),
        ))
        stair_void = box(v["STAIR_LEFT_X"], v["BWT"], v["HOUSE_WIDTH"]-v["BWT"], v["STAIR_UPPER_END_Y"])
        expected = box(v["BWT"], v["BWT"], v["HOUSE_WIDTH"]-v["BWT"],
                       v["HOUSE_DEPTH"]-v["BWT"]).difference(walls).difference(stair_void)
        self.assertLess(unary_union((living, bathroom, hallway)).symmetric_difference(expected).area, 1e-9)
        for room, polygon in ((v["living_room"], living), (v["upper_toilet_room"], bathroom),
                              (v["upper_hallway"], hallway)):
            self.assertAlmostEqual(room.area, polygon.area)

    def test_only_the_ground_partition_ring_beam_is_removed(self):
        v = self.v
        ground_hosts = {beam.source_wall for beam in v["ground_ring_beams"]}
        self.assertNotIn(v["wall_garden_partition_g"], ground_hosts)
        self.assertEqual(ground_hosts, set(v["ground_load_bearing_walls"]))
        basement_host = v["wall_basement_s01_s02"]
        self.assertTrue(any(beam.source_wall == basement_host for beam in v["basement_ring_beams"]))
        self.assertTrue(ifcopenshell.util.element.get_pset(basement_host, "Pset_WallCommon", "LoadBearing"))

    def test_basement_support_uses_250mm_type_and_keeps_its_endpoints(self):
        v = self.v
        wall = v["wall_basement_s01_s02"]
        np.testing.assert_allclose(wall.start, (v["HOUSE_WIDTH"]/2, v["GARDEN_ROOMS_WALL_Y"]+v["INNER_BWT"]))
        np.testing.assert_allclose(wall.end, (v["HOUSE_WIDTH"]/2, v["HOUSE_DEPTH"]-v["BWT"]))
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .25)
        self.assertAlmostEqual(lo[2], v["BASEMENT_FLOOR_START"])
        self.assertAlmostEqual(hi[2], v["BASEMENT_WALL_TOP_Z"])

    def test_basement_front_and_internal_walls_use_250mm_green_type(self):
        v = self.v
        exterior_300 = {v["wall_east_g"], v["wall_west_g"], v["wall_back_g"]}
        self.assertEqual(len(v["basement_rooms"]), 5)
        for wall in v["basement_walls"]:
            thick = wall.source_wall in exterior_300
            expected_type = v["basement_wall_type"] if thick else v["basement_thin_wall_type"]
            self.assertEqual(ifcopenshell.util.element.get_type(wall), expected_type)
            self.assertAlmostEqual(wall.thickness, .30 if thick else .25)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[0].Material.Name,
                             "ztracene bedneni" if thick else "ztracene bedneni 250")
            tangent = (np.asarray(wall.source_wall.end)-wall.source_wall.start)/wall.source_wall.length
            normal = np.array((-tangent[1], tangent[0]))
            old_centre = np.asarray(wall.source_wall.start)+normal*(wall.source_wall.body_offset+wall.source_wall.thickness/2)
            new_centre = v["wall_body_centreline_point"](wall)
            self.assertAlmostEqual(float((new_centre-old_centre)@normal), 0)

    def test_basement_beam_grid_uses_configured_distance_from_garden_wall_centre(self):
        v = self.v
        wall_lo, wall_hi = self.bounds(v["wall_basement_garden_rooms"])
        wall_y = (wall_lo[1]+wall_hi[1])/2
        row_centres = {}
        for key in ("basement_ceiling_s03", "basement_ceiling_s04", "basement_ceiling_s05"):
            row_centres[key] = []
            for shell in v[key].beam_shells:
                lo, hi = self.bounds(shell)
                row_centres[key].append((lo[1]+hi[1])/2)
        self.assertAlmostEqual(wall_y-row_centres["basement_ceiling_s03"][0], v["BASEMENT_CEILING_FIRST_BEAM_CENTER_DISTANCE"])
        self.assertAlmostEqual(wall_y-row_centres["basement_ceiling_s05"][0], v["BASEMENT_CEILING_FIRST_BEAM_CENTER_DISTANCE"])
        self.assertAlmostEqual(row_centres["basement_ceiling_s04"][0], row_centres["basement_ceiling_s03"][1])
        self.assertAlmostEqual(row_centres["basement_ceiling_s04"][0], row_centres["basement_ceiling_s05"][1])
        _, first_hi = self.bounds(v["basement_ceiling_s04"].beam_shells[0])
        chimney_lo, _ = self.bounds(v["chimney"])
        self.assertGreaterEqual(chimney_lo[1]-first_hi[1], 0)

    def test_chimney_has_70mm_clearance_from_250mm_wall_using_centreline_offset(self):
        v = self.v
        wall_lo, wall_hi = self.bounds(v["wall_basement_garden_rooms"])
        _, chimney_hi = self.bounds(v["chimney"])
        self.assertAlmostEqual((wall_lo[1]+wall_hi[1])/2-chimney_hi[1], .125+.07)
        self.assertAlmostEqual(wall_lo[1]-chimney_hi[1], .07)

    def test_basement_room3_and_room5_internal_bearings_are_125mm(self):
        v = self.v
        room3, room4 = v["basement_ceiling_s03"], v["basement_ceiling_s04"]
        r3 = v["basement_rooms_by_id"]["S.03"].bounds
        r5 = v["basement_rooms_by_id"]["S.05"].bounds
        for beam in room3.beam_shells:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(hi[0]-r3[2], .125)
            self.assertAlmostEqual(r3[0]-lo[0], .15)
            self.assertLessEqual(hi[0], room4.start[0]+1e-9)
        self.assertAlmostEqual(room3.length, 3.5)
        for slab in (v["basement_ceiling_s05"], v["basement_ceiling_s05_front"]):
            self.assertAlmostEqual(slab.length, 2.5)
            for beam in slab.beam_shells:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(r5[0]-lo[0], .125)
                self.assertAlmostEqual(hi[0]-r5[2], .15)
                self.assertGreaterEqual(lo[0], room4.end[0]-1e-9)

    def test_room_floor_boundaries_follow_new_partition_faces(self):
        v = self.v
        wall_lo, wall_hi = self.bounds(v["wall_garden_partition_g"])
        left_lo, left_hi = self.bounds(v["pokoj1"])
        right_lo, right_hi = self.bounds(v["pokoj2"])
        self.assertAlmostEqual(left_hi[0], wall_lo[0])
        self.assertAlmostEqual(right_lo[0], wall_hi[0])
        self.assertAlmostEqual(left_hi[0]-left_lo[0], right_hi[0]-right_lo[0])

    def test_shared_ceiling_has_14_beams_and_13_wide_bays_with_spaces(self):
        v = self.v
        slab = v["ceiling_garden_rooms"]
        self.assertEqual(len(slab.beams), 14)
        self.assertEqual(slab.structure, tuple(["beam"]+["space", "wide", "space", "beam"]*13))
        self.assertAlmostEqual(slab.width, 8.285)
        self.assertEqual(v["ceiling_slabs"].count(slab), 1)
        garden_rows = [row for row in v["ceiling_schedule_rows"] if row["slab"] == slab]
        self.assertEqual(len(garden_rows), 1)
        self.assertEqual(garden_rows[0]["slab"], slab)
        self.assertNotIn("ceiling_pokoj1", v)
        self.assertNotIn("ceiling_pokoj2", v)

    def test_shared_ceiling_is_centred_and_spans_between_bearing_walls(self):
        v = self.v
        slab = v["ceiling_garden_rooms"]
        outline = np.asarray(slab.footprint)
        lo, hi = outline.min(axis=0), outline.max(axis=0)
        room_front = v["GARDEN_ROOMS_WALL_Y"]+v["INNER_BWT"]
        room_back = v["HOUSE_DEPTH"]-v["BWT"]
        np.testing.assert_allclose((lo+hi)/2, (v["HOUSE_WIDTH"]/2, (room_front+room_back)/2))
        self.assertAlmostEqual(slab.length, 3.75)
        self.assertAlmostEqual(room_front-lo[1], .1825)
        self.assertAlmostEqual(hi[1]-room_back, .1825)
        self.assertAlmostEqual(slab.block_start_offset, room_front-lo[1])
        self.assertAlmostEqual(slab.block_end_offset, hi[1]-room_back)
        centres = []
        for beam in slab.beams:
            beam_lo, beam_hi = self.bounds(beam)
            self.assertAlmostEqual(beam_hi[1]-beam_lo[1], slab.length)
            centres.append((beam_hi[0]+beam_lo[0])/2)
        np.testing.assert_allclose(np.diff(centres), .625)

    def test_separate_stairway_beam_is_removed_from_model_and_schedule(self):
        v = self.v
        self.assertNotIn("ceiling_stairway_first_beam", v)
        self.assertFalse(any(slab.Name == "Ceiling - Schodiště krajní nosník"
                             for slab in v["house"].model.by_type("IfcSlab")))
        slab = v["ceiling_stairway"]
        row = next(row for row in v["ceiling_schedule_rows"] if row["location"] == "0.04, 0.05")
        self.assertIn(slab, row["slab"])
        self.assertAlmostEqual(slab.start[1], v["upper_ceiling_garden_y"])

    def test_stairway_ceiling_bearings_and_blocks_follow_physical_wall_faces(self):
        v = self.v
        slab = v["ceiling_stairway"]
        _, stairway_wall_hi = self.bounds(v["wall_stairway_g"])
        west_wall_lo, _ = self.bounds(v["wall_west_g"])
        stairway_face, west_face = stairway_wall_hi[0], west_wall_lo[0]
        self.assertAlmostEqual(slab.length, 2.5)
        self.assertAlmostEqual(slab.end[0]-west_face, .13)
        self.assertAlmostEqual(stairway_face-slab.start[0], 2.5-(west_face-stairway_face)-.13)
        self.assertAlmostEqual(stairway_face-slab.start[0], .11)
        self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, stairway_face)
        self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, west_face)
        for beam in slab.beams:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(hi[0]-west_face, .13)
            self.assertAlmostEqual(stairway_face-lo[0], .11)

    def test_room3_ceiling_uses_130mm_outside_and_remaining_middle_bearing(self):
        v = self.v
        _, outer_hi = self.bounds(v["wall_east_g"])
        middle_lo, _ = self.bounds(v["wall_third_room_g"])
        for key in ("ceiling_room3", "ceiling_room3_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, 3.5)
            self.assertAlmostEqual(outer_hi[0]-slab.start[0], .13)
            self.assertAlmostEqual(slab.end[0]-middle_lo[0], .11)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, outer_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, middle_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(outer_hi[0]-lo[0], .13)
                self.assertAlmostEqual(hi[0]-middle_lo[0], .11)

    def test_bathroom_ceiling_has_120mm_bearing_and_shares_schedule_with_hallway(self):
        v = self.v
        _, middle_hi = self.bounds(v["wall_third_room_g"])
        stairway_lo, _ = self.bounds(v["wall_stairway_g"])
        for key in ("ceiling_bathroom", "ceiling_bathroom_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, 2.5)
            self.assertAlmostEqual(middle_hi[0]-slab.start[0], .12)
            self.assertAlmostEqual(slab.end[0]-stairway_lo[0], .12)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, middle_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, stairway_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(middle_hi[0]-lo[0], .12)
                self.assertAlmostEqual(hi[0]-stairway_lo[0], .12)
        self.assertAlmostEqual(v["ceiling_bathroom"].start[0]-v["ceiling_room3"].end[0], .01)
        self.assertNotIn("ceiling_room3_hallway", v)
        self.assertNotIn("ceiling_front", v)
        rows = {row["location"]: row["slab"] for row in v["ceiling_schedule_rows"]}
        self.assertEqual(rows["0.03"], (v["ceiling_room3"], v["ceiling_room3_front"]))
        merged = rows["0.04, 0.05"]
        self.assertEqual(merged, (v["ceiling_stairway"], v["ceiling_bathroom"], v["ceiling_bathroom_front"]))
        self.assertTrue(all(abs(slab.length-2.5) < 1e-9 for slab in merged))
        self.assertEqual(sum(len(slab.beams) for slab in merged), 14)

    def test_upper_garden_ceilings_share_basement_grid_and_omit_bathroom_first_bay(self):
        v = self.v
        self.assertNotIn("ceiling_hallway_beam", v)
        self.assertNotIn("ceiling_room3_hallway_beam", v)
        self.assertNotIn("ceiling_bathroom_hallway_beam", v)
        room3, bathroom = v["ceiling_room3"], v["ceiling_bathroom"]
        wall_lo, wall_hi = self.bounds(v["wall_garden_rooms_g"])
        self.assertEqual(len(room3.beams), 6)
        self.assertEqual(len(bathroom.beams), 5)
        wall_center_y = (wall_lo[1]+wall_hi[1])/2
        for upper_key, basement_key in (
            ("ceiling_room3", "basement_ceiling_s03"),
            ("ceiling_stairway", "basement_ceiling_s05"),
        ):
            first_lo, first_hi = self.bounds(v[upper_key].beam_shells[0])
            first_center = (first_lo[1]+first_hi[1])/2
            self.assertAlmostEqual(wall_center_y-first_center,
                                   v["BASEMENT_CEILING_FIRST_BEAM_CENTER_DISTANCE"])
            lower_lo, lower_hi = self.bounds(v[basement_key].beam_shells[0])
            self.assertAlmostEqual(first_center, (lower_lo[1]+lower_hi[1])/2)
        self.assertAlmostEqual(room3.start[1]-bathroom.start[1], .500)
        upper_lo, upper_hi = self.bounds(bathroom.beam_shells[0])
        lower_lo, lower_hi = self.bounds(v["basement_ceiling_s04"].beam_shells[0])
        np.testing.assert_allclose(upper_lo[1], lower_lo[1])
        np.testing.assert_allclose(upper_hi[1], lower_hi[1])
        np.testing.assert_allclose(
            [start[1] for start, end in bathroom.beam_centerlines],
            [start[1] for start, end in room3.beam_centerlines[1:]],
        )
        for main in (room3, bathroom):
            self.assertAlmostEqual(min(y for x, y in main.footprint), 2.88)
            for beam in main.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(lo[0], main.start[0])
                self.assertAlmostEqual(hi[0], main.end[0])
        self.assertFalse(bathroom.topping_element.HasOpenings)
        self.assertFalse(any(row["location"] == "Pokoj 3 + Koupelna, zkrácený nosník" for row in v["ceiling_schedule_rows"]))

    def test_bathroom_omitted_bay_clears_chimney_and_keeps_later_rows_full_width(self):
        v = self.v
        slab = v["ceiling_bathroom"]
        _, cover_hi = self.bounds(slab.topping_element)
        chimney_lo, _ = self.bounds(v["chimney"])
        self.assertLess(cover_hi[1], chimney_lo[1])
        for beam in slab.beam_shells:
            _, hi = self.bounds(beam)
            self.assertLess(hi[1], chimney_lo[1])
        self.assertTrue(slab.blocks)
        self.assertTrue(all(not block.HasOpenings for block in slab.blocks))
        block_bounds = [self.bounds(block) for block in slab.blocks]
        self.assertAlmostEqual(min(lo[0] for lo, hi in block_bounds), v["bathroom_ceiling_middle_face_x"])
        self.assertAlmostEqual(max(hi[0] for lo, hi in block_bounds), v["bathroom_ceiling_stairway_face_x"])
        bathroom_rows = sorted({(round(lo[1], 8), round(hi[1], 8)) for lo, hi in block_bounds})
        room3_rows = sorted({(round(lo[1], 8), round(hi[1], 8))
                            for lo, hi in (self.bounds(block) for block in v["ceiling_room3"].blocks
                                           if " Block 1." not in block.Name)})
        self.assertEqual(bathroom_rows, room3_rows)

    def test_bare_split_hebs_have_100mm_bearings_and_are_centered_in_the_ceiling(self):
        v = self.v
        _, east_hi = self.bounds(v["wall_east_g"])
        middle_lo, middle_hi = self.bounds(v["wall_third_room_g"])
        stairway_lo, _ = self.bounds(v["wall_stairway_g"])
        rows = {post.start[1] for post in v["purlin_supports"]}
        girders = v["purlin_support_girders"]
        self.assertEqual(len(girders), 2*len(rows))
        for girder in girders:
            left, right = ((east_hi[0], middle_lo[0]) if girder.Name.endswith("0.03")
                           else (middle_hi[0], stairway_lo[0]))
            lo, hi = self.bounds(girder)
            self.assertAlmostEqual(left-lo[0], .10)
            self.assertAlmostEqual(hi[0]-right, .10)
            self.assertAlmostEqual(girder.length, right-left+.20)
            lo, hi = self.bounds(girder)
            self.assertAlmostEqual(lo[2], v["ground_floor_height"]+.015)
            self.assertAlmostEqual(hi[2], v["UPPER_FLOOR_START"]-.015)
            self.assertEqual(ifcopenshell.util.element.get_material(girder).Name, "Structural steel")
            self.assertEqual(girder.ObjectType, "HEB180")
        for y in rows:
            left, right = sorted((girder for girder in girders if girder.start[1] == y), key=lambda girder: girder.start[0])
            self.assertAlmostEqual(right.start[0]-left.end[0], .04)
        for post in v["purlin_supports"]:
            self.assertEqual(sum(g.start[1] == post.start[1] and g.start[0] <= post.start[0] <= g.end[0]
                                 for g in girders), 1)


if __name__ == "__main__":
    unittest.main()
