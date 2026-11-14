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

    def test_only_the_ground_partition_ring_beam_is_removed(self):
        v = self.v
        ground_hosts = {beam.source_wall for beam in v["ground_ring_beams"]}
        self.assertNotIn(v["wall_garden_partition_g"], ground_hosts)
        self.assertEqual(ground_hosts, set(v["ground_load_bearing_walls"]))
        basement_host = v["wall_basement_s01_s02"]
        self.assertTrue(any(beam.source_wall == basement_host for beam in v["basement_ring_beams"]))
        self.assertTrue(ifcopenshell.util.element.get_pset(basement_host, "Pset_WallCommon", "LoadBearing"))

    def test_basement_support_keeps_its_original_width_and_endpoints(self):
        v = self.v
        wall = v["wall_basement_s01_s02"]
        np.testing.assert_allclose(wall.start, (v["HOUSE_WIDTH"]/2, v["GARDEN_ROOMS_WALL_Y"]+v["INNER_BWT"]))
        np.testing.assert_allclose(wall.end, (v["HOUSE_WIDTH"]/2, v["HOUSE_DEPTH"]-v["BWT"]))
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .30)
        self.assertAlmostEqual(lo[2], v["BASEMENT_FLOOR_START"])
        self.assertAlmostEqual(hi[2], v["BASEMENT_WALL_TOP_Z"])

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
        garden_rows = [row for row in v["ceiling_schedule_rows"] if "Pokoj 1" in row["location"] or "Pokoj 2" in row["location"]]
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
        row = next(row for row in v["ceiling_schedule_rows"] if row["location"] == "Chodba")
        self.assertEqual(row["slab"], slab)
        self.assertAlmostEqual(slab.start[1], v["GARDEN_ROOMS_WALL_Y"]-v["STAIRWAY_CEILING_GARDEN_WALL_CLEARANCE"])

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
        for key in ("ceiling_room3", "ceiling_room3_front", "ceiling_room3_hallway_beam"):
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

    def test_bathroom_ceiling_has_120mm_bearing_each_end_and_separate_schedule(self):
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
        self.assertEqual(rows["0.03 - Pokoj 3"], (v["ceiling_room3"], v["ceiling_room3_front"], v["ceiling_room3_hallway_beam"]))
        self.assertEqual(rows["0.05 - Koupelna a chodba"], (v["ceiling_bathroom"], v["ceiling_bathroom_front"], v["ceiling_bathroom_hallway_beam"]))

    def test_chimney_side_beams_match_each_room_span_and_keep_chimney_clearance(self):
        v = self.v
        self.assertNotIn("ceiling_hallway_beam", v)
        for short, main in ((v["ceiling_room3_hallway_beam"], v["ceiling_room3"]),
                            (v["ceiling_bathroom_hallway_beam"], v["ceiling_bathroom"])):
            self.assertEqual(len(short.beams), v["HALLWAY_MIAKO_BEAM_COUNT"])
            self.assertAlmostEqual(short.start[0], main.start[0])
            self.assertAlmostEqual(short.end[0], main.end[0])
            self.assertAlmostEqual(short.start[1], v["hallway_miako_beam_y"])
            for beam in short.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(lo[0], main.start[0])
                self.assertAlmostEqual(hi[0], main.end[0])
        hallway = v["ceiling_bathroom_hallway_beam"]
        chimney_edge = v["CHIMNEY_CENTER"][0]-v["CHIMNEY_SIZE"]/2
        block_bounds = [self.bounds(block) for block in hallway.blocks]
        self.assertAlmostEqual(min(lo[0] for lo, hi in block_bounds), v["bathroom_ceiling_middle_face_x"])
        self.assertAlmostEqual(chimney_edge-max(hi[0] for lo, hi in block_bounds), .05)
        self.assertEqual(v["hallway_chimney_opening"].VoidsElements[0].RelatingBuildingElement, hallway.topping_element)
        self.assertFalse(any(row["location"] == "Pokoj 3 + Koupelna, zkrácený nosník" for row in v["ceiling_schedule_rows"]))

    def test_split_heb_and_concrete_have_100mm_bearing_on_every_support(self):
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
            for element in (girder, girder.steel):
                lo, hi = self.bounds(element)
                self.assertAlmostEqual(left-lo[0], .10)
                self.assertAlmostEqual(hi[0]-right, .10)
            self.assertAlmostEqual(girder.length, right-left+.20)
            lo, hi = self.bounds(girder)
            self.assertAlmostEqual(lo[2], v["ground_floor_height"])
            self.assertAlmostEqual(hi[2], v["UPPER_FLOOR_START"])
        for y in rows:
            left, right = sorted((girder for girder in girders if girder.start[1] == y), key=lambda girder: girder.start[0])
            self.assertAlmostEqual(right.start[0]-left.end[0], .04)
        for post in v["purlin_supports"]:
            self.assertEqual(sum(g.start[1] == post.start[1] and g.start[0] <= post.start[0] <= g.end[0]
                                 for g in girders), 1)


if __name__ == "__main__":
    unittest.main()
