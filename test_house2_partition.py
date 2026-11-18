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
from shapely.geometry import Polygon, box

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

    def test_garden_room_wall_is_centred_300mm_load_bearing_ytong(self):
        v = self.v
        wall = v["wall_garden_partition_g"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .30)
        self.assertAlmostEqual((hi[0]+lo[0])/2, v["HOUSE_WIDTH"]/2)
        self.assertTrue(ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing"))
        material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                         [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Ytong Klasik"])
        self.assertIn("load bearing wall - Ytong Klasik 300 mm", ifcopenshell.util.element.get_type(wall).Name)
        room1 = Polygon(v["pokoj1"].outline)
        room2 = Polygon(v["pokoj2"].outline)
        self.assertAlmostEqual(room1.bounds[2], lo[0])
        self.assertAlmostEqual(room2.bounds[0], hi[0])
        self.assertAlmostEqual(room1.area, room2.area)

    def test_garden_dividers_are_aligned_300mm_ytong_on_both_floors(self):
        v = self.v
        for wall, thickness in ((v["wall_back_g"], .24), (v["wall_back_u"], .175)):
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(hi[1]-lo[1], thickness)
            self.assertAlmostEqual(hi[1], v["HOUSE_DEPTH"])
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[-1].Material.Name, "Brick")
        wall = v["wall_garden_rooms_g"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[1]-lo[1], .30)
        basement_lo, basement_hi = self.bounds(v["wall_basement_garden_rooms"])
        self.assertAlmostEqual((lo[1]+hi[1])/2, (basement_lo[1]+basement_hi[1])/2)
        material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                         [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Ytong Klasik"])
        upper_wall = v["wall_living_room_back_u"]
        upper_lo, upper_hi = self.bounds(upper_wall)
        self.assertAlmostEqual(upper_hi[1]-upper_lo[1], .30)
        self.assertAlmostEqual((upper_lo[1]+upper_hi[1])/2, (lo[1]+hi[1])/2)
        self.assertAlmostEqual((lo[1]+hi[1])/2, v["GARDEN_ROOMS_WALL_CENTER_Y"])
        upper_material = ifcopenshell.util.element.get_material(upper_wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in upper_material.MaterialLayers], ["Ytong Klasik"])
        self.assertIn("Ytong Klasik 300 mm", ifcopenshell.util.element.get_type(upper_wall).Name)
        for room in (v["pokoj1"], v["pokoj2"]):
            bounds = Polygon(room.outline).bounds
            self.assertAlmostEqual(bounds[1], hi[1])
            self.assertAlmostEqual(bounds[3], v["HOUSE_DEPTH"]-.24)

    def test_ground_mid_walls_are_300mm_ytong_on_the_original_centrelines(self):
        v = self.v
        for key, expected_x in (("wall_third_room_g", 3.62), ("wall_stairway_g", 6.13)):
            wall = v[key]
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(hi[0]-lo[0], .30)
            self.assertAlmostEqual((lo[0]+hi[0])/2, expected_x)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                             [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Ytong Klasik"])
            support = next(w for w in v["basement_walls"] if w.source_wall == wall)
            blo, bhi = self.bounds(support)
            self.assertAlmostEqual((blo[0]+bhi[0])/2, expected_x)
            self.assertAlmostEqual(bhi[0]-blo[0], .25)
        left_lo, left_hi = self.bounds(v["wall_third_room_g"])
        right_lo, right_hi = self.bounds(v["wall_stairway_g"])
        self.assertAlmostEqual(Polygon(v["pokoj3"].outline).bounds[2], left_lo[0])
        bathroom_bounds = Polygon(v["koupelna"].outline).bounds
        self.assertAlmostEqual(bathroom_bounds[0], left_hi[0])
        self.assertAlmostEqual(bathroom_bounds[2], right_lo[0])
        upper_lo, upper_hi = self.bounds(v["upper_stairs"].flight)
        lower_lo, lower_hi = self.bounds(v["lower_stairs"].flight)
        self.assertAlmostEqual(upper_lo[0], right_hi[0])
        self.assertAlmostEqual(upper_hi[0]-upper_lo[0], 1.0)
        self.assertAlmostEqual(lower_hi[0]-lower_lo[0], 1.15)
        self.assertAlmostEqual(lower_lo[0]-upper_hi[0], .08)
        for post in v["stair_landing_posts"]:
            post_lo, _ = self.bounds(post)
            self.assertGreaterEqual(post_lo[0]+1e-9, right_hi[0])

    def test_ground_front_back_walls_are_240mm_with_specification_and_upper_stays_175mm(self):
        v = self.v
        for wall, thickness in ((v["wall_front_g"], .24), (v["wall_front_u"], .175)):
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(lo[1], 0)
            self.assertAlmostEqual(hi[1], thickness)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[-1].Material.Name, "Brick")
        for room in (v["pokoj3"], v["koupelna"]):
            self.assertAlmostEqual(Polygon(room.outline).bounds[1], .24)
        self.assertAlmostEqual(v["living_room_outline"].bounds[1], .175)
        landing_lo, _ = self.bounds(v["middle_stair_landing"])
        self.assertAlmostEqual(landing_lo[1], .24)
        for wall in (v["wall_front_g"], v["wall_back_g"], v["wall_east_g"], v["wall_west_g"]):
            self.assertEqual(wall.Description, "VPC Cihla 240 mm (20-2,0)")
        for wall in (v["wall_east_g"], v["wall_west_g"]):
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(lo[1], 0)
            self.assertAlmostEqual(hi[1], v["HOUSE_DEPTH"])
        girder = v["ceiling_stairway_edge_heb"]
        self.assertAlmostEqual(girder.start[1]-girder.width/2, 3.24)
        self.assertGreater(girder.start[1]-girder.width/2, v["upper_stairs"].end[1])

    def test_exterior_corner_joints_keep_side_walls_continuous_on_both_floors(self):
        v = self.v
        for suffix in ("g", "u"):
            front_thickness = v["FRONT_WALL_THICKNESS" if suffix == "g" else "UPPER_FRONT_WALL_THICKNESS"]
            back_thickness = v["BACK_WALL_THICKNESS" if suffix == "g" else "UPPER_BACK_WALL_THICKNESS"]
            rectangles = []
            for side in ("front", "back", "east", "west"):
                wall = v[f"wall_{side}_{suffix}"]
                lo, hi = self.bounds(wall)
                if side in ("front", "back"):
                    self.assertAlmostEqual(lo[0], v["BWT"])
                    self.assertAlmostEqual(hi[0], v["HOUSE_WIDTH"]-v["BWT"])
                else:
                    self.assertAlmostEqual(lo[1], 0)
                    self.assertAlmostEqual(hi[1], v["HOUSE_DEPTH"])
                rectangle = box(*lo[:2], *hi[:2])
                for previous in rectangles:
                    self.assertLess(previous.intersection(rectangle).area, 1e-9)
                rectangles.append(rectangle)
            actual = rectangles[0].union(rectangles[1]).union(rectangles[2]).union(rectangles[3])
            expected = box(0, 0, v["HOUSE_WIDTH"], v["HOUSE_DEPTH"]).difference(box(
                v["BWT"], front_thickness,
                v["HOUSE_WIDTH"]-v["BWT"], v["HOUSE_DEPTH"]-back_thickness,
            ))
            self.assertLess(actual.symmetric_difference(expected).area, 1e-9)

    def test_upper_stairway_wall_split_joins_the_front_ring_beam(self):
        v = self.v
        masonry = v["wall_kitchen_stairway_u"]
        drywall = v["wall_technical_stairway_u"]
        mlo, mhi = self.bounds(masonry)
        dlo, dhi = self.bounds(drywall)
        self.assertAlmostEqual(mhi[0]-mlo[0], .24)
        self.assertAlmostEqual(dhi[0]-dlo[0], .10)
        self.assertAlmostEqual(mhi[0], v["STAIR_LEFT_X"])
        self.assertAlmostEqual(dhi[0], v["STAIR_LEFT_X"])
        self.assertAlmostEqual(mlo[1], v["UPPER_FRONT_WALL_THICKNESS"])
        self.assertAlmostEqual(mhi[1], v["upper_technical_cross_front_y"])
        self.assertAlmostEqual(dlo[1], mhi[1])
        self.assertTrue(ifcopenshell.util.element.get_pset(masonry, "Pset_WallCommon", "LoadBearing"))
        self.assertFalse(ifcopenshell.util.element.get_pset(drywall, "Pset_WallCommon", "LoadBearing"))
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

    def test_restored_bathroom_return_and_outward_door_match_the_enclosure(self):
        v = self.v
        _, return_hi = self.bounds(v["wall_living_room_return_u"])
        vpc_lo, _ = self.bounds(v["wall_living_room_back_u"])
        self.assertAlmostEqual(vpc_lo[1]-return_hi[1], .70)
        self.assertEqual(v["upper_toilet_door"].OperationType, "SINGLE_SWING_LEFT")
        self.assertAlmostEqual(v["upper_toilet_door"].OverallWidth, .70)
        bathroom = v["upper_toilet_outline"]
        self.assertAlmostEqual(bathroom.bounds[3]-bathroom.bounds[1], v["UPPER_TOILET_DEPTH"])
        lo, hi = self.bounds(v["upper_toilet"])
        self.assertTrue(bathroom.covers(box(lo[0], lo[1], hi[0], hi[1])))
        rooms = (v["living_room_outline"], bathroom, v["upper_hallway_outline"])
        for i, region in enumerate(rooms):
            self.assertTrue(region.is_valid)
            for other in rooms[i+1:]:
                self.assertLess(region.intersection(other).area, 1e-9)

    def test_restored_kitchen_sink_follows_the_vertical_partition(self):
        v = self.v
        cooker_lo, cooker_hi = self.bounds(v["kitchen_cooker"])
        sink_lo, sink_hi = self.bounds(v["kitchen_sink"])
        side_lo, _ = self.bounds(v["wall_living_room_side_u"])
        self.assertAlmostEqual(side_lo[0]-cooker_hi[0], v["KITCHEN_WALL_GAP"])
        np.testing.assert_allclose(sink_lo[[0, 2]], cooker_lo[[0, 2]])
        np.testing.assert_allclose(sink_hi[[0, 2]], cooker_hi[[0, 2]])
        self.assertAlmostEqual(sink_hi[1], cooker_lo[1])
        self.assertAlmostEqual(sink_lo[1], v["upper_technical_cross_front_y"])
        for room in v["living_room_floor_parts"]:
            if Polygon(room.outline).covers(box(*sink_lo[:2], *sink_hi[:2])):
                break
        else:
            self.fail("The restored sink must fit within the kitchen floor")

    def test_garden_room_load_bearing_wall_has_a_centred_ring_beam(self):
        v = self.v
        ground_hosts = {beam.source_wall for beam in v["ground_ring_beams"]}
        wall = v["wall_garden_partition_g"]
        self.assertIn(wall, ground_hosts)
        self.assertEqual(ground_hosts, set(v["ground_load_bearing_walls"]))
        rings = [beam for beam in v["ground_ring_beams"] if beam.source_wall == wall]
        self.assertEqual(len(rings), 1)
        lo, hi = self.bounds(rings[0])
        self.assertAlmostEqual(hi[0]-lo[0], .30)
        self.assertAlmostEqual((hi[0]+lo[0])/2, v["HOUSE_WIDTH"]/2)
        self.assertAlmostEqual(lo[1], wall.start[1])
        self.assertAlmostEqual(hi[1], wall.end[1])
        self.assertAlmostEqual(hi[2]-lo[2], v["CEILING_THICKNESS"])
        basement_host = v["wall_basement_s01_s02"]
        self.assertTrue(any(beam.source_wall == basement_host for beam in v["basement_ring_beams"]))
        self.assertTrue(ifcopenshell.util.element.get_pset(basement_host, "Pset_WallCommon", "LoadBearing"))

    def test_basement_support_uses_250mm_type_and_keeps_its_endpoints(self):
        v = self.v
        wall = v["wall_basement_s01_s02"]
        np.testing.assert_allclose(wall.start, (v["HOUSE_WIDTH"]/2, v["GARDEN_ROOMS_WALL_CENTER_Y"]+v["INNER_BWT"]/2))
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
            expected_offset = ((v["BWT"]-v["BACK_WALL_THICKNESS"])/2
                               if wall.source_wall in (v["wall_front_g"], v["wall_back_g"]) else 0)
            self.assertAlmostEqual(float((new_centre-old_centre)@normal), expected_offset)

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
        _, divider_hi = self.bounds(v["wall_garden_rooms_g"])
        back_lo, _ = self.bounds(v["wall_back_g"])
        room_front, room_back = divider_hi[1], back_lo[1]
        np.testing.assert_allclose((lo+hi)/2, (v["HOUSE_WIDTH"]/2, (room_front+room_back)/2))
        self.assertAlmostEqual(slab.length, 3.75)
        self.assertAlmostEqual(room_front-lo[1], .165)
        self.assertAlmostEqual(hi[1]-room_back, .165)
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
        row = next(row for row in v["ceiling_schedule_rows"] if row["location"] == "0.04")
        self.assertEqual(slab, row["slab"])
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
        self.assertAlmostEqual(stairway_face-slab.start[0], .14)
        self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, stairway_face)
        self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, west_face)
        for beam in slab.beams:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(hi[0]-west_face, .13)
            self.assertAlmostEqual(stairway_face-lo[0], .14)

    def test_room3_ceiling_uses_130mm_outside_and_remaining_middle_bearing(self):
        v = self.v
        _, outer_hi = self.bounds(v["wall_east_g"])
        middle_lo, _ = self.bounds(v["wall_third_room_g"])
        for key in ("ceiling_room3", "ceiling_room3_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, 3.5)
            self.assertAlmostEqual(outer_hi[0]-slab.start[0], .13)
            self.assertAlmostEqual(slab.end[0]-middle_lo[0], .14)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, outer_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, middle_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(outer_hi[0]-lo[0], .13)
                self.assertAlmostEqual(hi[0]-middle_lo[0], .14)

    def test_bathroom_ceiling_has_120mm_bearing_and_its_own_shorter_schedule_row(self):
        v = self.v
        _, middle_hi = self.bounds(v["wall_third_room_g"])
        stairway_lo, _ = self.bounds(v["wall_stairway_g"])
        for key in ("ceiling_bathroom", "ceiling_bathroom_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, 2.45)
            self.assertAlmostEqual(middle_hi[0]-slab.start[0], .12)
            self.assertAlmostEqual(slab.end[0]-stairway_lo[0], .12)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, middle_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, stairway_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(middle_hi[0]-lo[0], .12)
                self.assertAlmostEqual(hi[0]-stairway_lo[0], .12)
        self.assertAlmostEqual(v["ceiling_bathroom"].start[0]-v["ceiling_room3"].end[0], .04)
        self.assertNotIn("ceiling_room3_hallway", v)
        self.assertNotIn("ceiling_front", v)
        rows = {row["location"]: row["slab"] for row in v["ceiling_schedule_rows"]}
        self.assertEqual(rows["0.03"], (v["ceiling_room3"], v["ceiling_room3_front"]))
        self.assertEqual(rows["0.04"], v["ceiling_stairway"])
        self.assertEqual(rows["0.05"], (v["ceiling_bathroom"], v["ceiling_bathroom_front"]))
        self.assertAlmostEqual(rows["0.04"].length, 2.5)
        self.assertTrue(all(abs(slab.length-2.45) < 1e-9 for slab in rows["0.05"]))

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
