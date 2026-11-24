"""Garden partition, shared ceiling and independent basement support."""

from contextlib import redirect_stdout
from io import StringIO
import ast
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

    def test_garden_room_wall_is_centred_300mm_load_bearing_porfix(self):
        v = self.v
        wall = v["wall_garden_partition_g"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .30)
        self.assertAlmostEqual((hi[0]+lo[0])/2, v["HOUSE_WIDTH"]/2)
        self.assertTrue(ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing"))
        material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                         [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Porfix P2-440 PDK 300 mm"])
        self.assertIn("load bearing wall - Porfix P2-440 PDK 300 mm", ifcopenshell.util.element.get_type(wall).Name)
        self.assertEqual(wall.Description, "Porfix P2-440 PDK 300 mm")
        basement_lo, basement_hi = self.bounds(v["wall_basement_s01_s02"])
        self.assertAlmostEqual((lo[0]+hi[0])/2, (basement_lo[0]+basement_hi[0])/2)
        room1 = Polygon(v["pokoj1"].outline)
        room2 = Polygon(v["pokoj2"].outline)
        self.assertAlmostEqual(room1.bounds[2], lo[0])
        self.assertAlmostEqual(room2.bounds[0], hi[0])
        self.assertAlmostEqual(room1.area, room2.area)

    def test_garden_dividers_use_centred_300mm_porfix_with_3230mm_clear_depth(self):
        v = self.v
        for wall, thickness, expected_material in (
            (v["wall_back_g"], .24, "Brick"),
            (v["wall_back_u"], .24, v["UPPER_EXTERIOR_WALL_MATERIAL"]),
        ):
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(hi[1]-lo[1], thickness)
            self.assertAlmostEqual(hi[1], v["HOUSE_DEPTH"])
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[-1].Material.Name, expected_material)
        wall = v["wall_garden_rooms_g"]
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[1]-lo[1], .30)
        basement_lo, basement_hi = self.bounds(v["wall_basement_garden_rooms"])
        self.assertAlmostEqual((lo[1]+hi[1])/2, (basement_lo[1]+basement_hi[1])/2)
        material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers],
                         [v["GROUND_WALL_BASE_COURSE_MATERIAL"], "Porfix P2-440 PDK 300 mm"])
        self.assertEqual(wall.Description, "Porfix P2-440 PDK 300 mm")
        ring = next(beam for beam in v["ground_ring_beams"] if beam.source_wall == wall)
        ring_lo, ring_hi = self.bounds(ring)
        self.assertAlmostEqual(ring_hi[1]-ring_lo[1], .30)
        self.assertAlmostEqual((ring_hi[1]+ring_lo[1])/2, v["GARDEN_ROOMS_WALL_CENTER_Y"])
        upper_wall = v["wall_living_room_back_u"]
        upper_lo, upper_hi = self.bounds(upper_wall)
        self.assertAlmostEqual(upper_hi[1]-upper_lo[1], .30)
        self.assertAlmostEqual((upper_lo[1]+upper_hi[1])/2, (lo[1]+hi[1])/2)
        self.assertAlmostEqual((lo[1]+hi[1])/2, v["GARDEN_ROOMS_WALL_CENTER_Y"])
        upper_material = ifcopenshell.util.element.get_material(upper_wall, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in upper_material.MaterialLayers],
                         ["Porfix P2-440 PDK 300 mm"])
        self.assertIn("Porfix P2-440 PDK 300 mm", ifcopenshell.util.element.get_type(upper_wall).Name)
        self.assertEqual(upper_wall.Description, "Porfix P2-440 PDK 300 mm")
        for room in (v["pokoj1"], v["pokoj2"]):
            bounds = Polygon(room.outline).bounds
            self.assertAlmostEqual(bounds[1], hi[1])
            self.assertAlmostEqual(bounds[3], v["HOUSE_DEPTH"]-.24)
            self.assertAlmostEqual(bounds[3]-bounds[1], 3.23)
        self.assertAlmostEqual(v["GARDEN_ROOMS_DEPTH"], 3.23)
        self.assertAlmostEqual(v["GARDEN_ROOMS_WALL_CENTER_Y"], 5.37)

    def test_room3_door_opening_is_50mm_from_the_garden_room_wall(self):
        opening = self.v["pokoj3_door"].FillsVoids[0].RelatingOpeningElement
        lo, hi = self.bounds(opening)
        wall_lo, _ = self.bounds(self.v["wall_garden_rooms_g"])
        self.assertAlmostEqual(wall_lo[1]-hi[1], .05)
        self.assertAlmostEqual(hi[1]-lo[1], self.v["ROOM_DOOR_OPENING_WIDTH"])

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

    def test_outer_walls_are_240mm_vpc_ground_and_liapor_upper(self):
        v = self.v
        for wall, thickness, expected_material in (
            (v["wall_front_g"], .24, "Brick"),
            (v["wall_front_u"], .24, "Liapor KM 240 AKU"),
        ):
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(lo[1], 0)
            self.assertAlmostEqual(hi[1], thickness)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[-1].Material.Name, expected_material)
        for room in (v["pokoj3"], v["koupelna"]):
            self.assertAlmostEqual(Polygon(room.outline).bounds[1], .24)
        self.assertAlmostEqual(v["living_room_outline"].bounds[1], .24)
        self.assertAlmostEqual(v["living_room_outline"].bounds[3], v["HOUSE_DEPTH"]-.24)
        for wall in v["upper_exterior_walls"]:
            self.assertAlmostEqual(wall.thickness, .24)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual([layer.Material.Name for layer in material.MaterialLayers], ["Liapor KM 240 AKU"])
            self.assertEqual(wall.Description, "Liapor KM 240 AKU")
            self.assertTrue(ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing"))
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
        self.assertAlmostEqual(mhi[0]-mlo[0], .30)
        material = ifcopenshell.util.element.get_material(masonry, should_skip_usage=True)
        self.assertEqual([layer.Material.Name for layer in material.MaterialLayers], ["Ytong Klasik"])
        ground_lo, ground_hi = self.bounds(v["wall_stairway_g"])
        self.assertAlmostEqual((mlo[0]+mhi[0])/2, (ground_lo[0]+ground_hi[0])/2)
        self.assertAlmostEqual(dhi[0]-dlo[0], .10)
        self.assertAlmostEqual(mhi[0], v["UPPER_STAIRWAY_WALL_X"])
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
        self.assertAlmostEqual(rhi[0]-rlo[0], .30)
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
        self.assertAlmostEqual(bathroom.bounds[2]-bathroom.bounds[0], v["UPPER_BATHROOM_WIDTH"])
        self.assertAlmostEqual(v["UPPER_BATHROOM_WIDTH"], 1.0)
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
        self.assertAlmostEqual(hi[0]-lo[0], .24)
        self.assertAlmostEqual((hi[0]+lo[0])/2, v["HOUSE_WIDTH"]/2)
        self.assertAlmostEqual(lo[1], wall.start[1])
        self.assertAlmostEqual(hi[1], wall.end[1])
        self.assertAlmostEqual(hi[2]-lo[2], v["CEILING_THICKNESS"])
        basement_host = v["wall_basement_s01_s02"]
        self.assertTrue(any(beam.source_wall == basement_host for beam in v["basement_ring_beams"]))
        self.assertTrue(ifcopenshell.util.element.get_pset(basement_host, "Pset_WallCommon", "LoadBearing"))

    def test_basement_support_uses_300mm_type_and_keeps_its_endpoints(self):
        v = self.v
        wall = v["wall_basement_s01_s02"]
        np.testing.assert_allclose(wall.start, (v["HOUSE_WIDTH"]/2, v["GARDEN_ROOMS_WALL_CENTER_Y"]+v["INNER_BWT"]/2))
        np.testing.assert_allclose(wall.end, (v["HOUSE_WIDTH"]/2, v["HOUSE_DEPTH"]-v["BWT"]))
        lo, hi = self.bounds(wall)
        self.assertAlmostEqual(hi[0]-lo[0], .30)
        self.assertAlmostEqual(lo[2], v["BASEMENT_FLOOR_START"])
        self.assertAlmostEqual(hi[2], v["BASEMENT_WALL_TOP_Z"])

    def test_east_west_wall_stacks_and_1100mm_stepped_footings_are_centred(self):
        v = self.v
        for side, centre_x in (("east", v["BWT"]/2), ("west", v["HOUSE_WIDTH"]-v["BWT"]/2)):
            centres = []
            basement_wall = v[f"wall_basement_{side}"]
            for wall in (basement_wall, v[f"wall_{side}_g"], v[f"wall_{side}_u"]):
                lo, hi = self.bounds(wall)
                centres.append((lo[0]+hi[0])/2)
            np.testing.assert_allclose(centres, centre_x, rtol=0, atol=1e-9)
            self.assertAlmostEqual(basement_wall.thickness, .30)
            footing = v[f"{side}_footing"]
            properties = ifcopenshell.util.element.get_pset(footing, "BBIM_StripFooting")
            self.assertEqual(properties["SourceWall"], basement_wall.GlobalId)
            self.assertAlmostEqual(properties["Width"], 1.1)
            self.assertAlmostEqual(properties["Height"], .5)
            lo, hi = self.bounds(footing)
            self.assertAlmostEqual(hi[0]-lo[0], 1.1)
            self.assertAlmostEqual((lo[0]+hi[0])/2, centre_x)
            self.assertAlmostEqual(lo[2], v["FOUNDATION_FOOTING_BOTTOM_Z"]-v["FOUNDATION_STREET_STEP_DROP"])
            self.assertAlmostEqual(hi[2], v["BASEMENT_SLAB_BOTTOM_Z"])
        for footing in v["foundation_footings"]:
            source = v["house"].model.by_guid(ifcopenshell.util.element.get_pset(
                footing, "BBIM_StripFooting", "SourceWall",
            ))
            if source not in v["foundation_footing_dimensions"]:
                self.assertAlmostEqual(ifcopenshell.util.element.get_pset(
                    footing, "BBIM_StripFooting", "Width",
                ), v["FOUNDATION_FOOTING_WIDTH"])

    def test_middle_300mm_walls_and_1100mm_footings_share_ground_wall_centres(self):
        v = self.v
        for key, ground_key in (("wall_basement_s03_s04", "wall_third_room_g"),
                                ("wall_basement_s04_s05", "wall_stairway_g")):
            wall = v[key]
            ground_lo, ground_hi = self.bounds(v[ground_key])
            centre_x = (ground_lo[0]+ground_hi[0])/2
            self.assertEqual(ifcopenshell.util.element.get_type(wall), v["basement_wall_type"])
            self.assertAlmostEqual(wall.thickness, .30)
            ring = next(beam for beam in v["basement_ring_beams"] if beam.source_wall == wall)
            infill = next(w for w in v["foundation_walls_below_base_plate"]
                          if ifcopenshell.util.element.get_pset(w, "BBIM_FoundationWall", "SourceWall")
                          == wall.GlobalId)
            for element in (wall, ring, infill):
                lo, hi = self.bounds(element)
                self.assertAlmostEqual(hi[0]-lo[0], .30)
                self.assertAlmostEqual((lo[0]+hi[0])/2, centre_x)
            footing = v["footings_by_source_wall"][wall.GlobalId]
            properties = ifcopenshell.util.element.get_pset(footing, "BBIM_StripFooting")
            self.assertAlmostEqual(properties["Width"], 1.1)
            self.assertAlmostEqual(properties["Height"], .5)
            lo, hi = self.bounds(footing)
            self.assertAlmostEqual(hi[0]-lo[0], 1.1)
            self.assertAlmostEqual((lo[0]+hi[0])/2, centre_x)
            self.assertAlmostEqual(lo[2], v["FOUNDATION_FOOTING_BOTTOM_Z"]-v["FOUNDATION_STREET_STEP_DROP"])
            self.assertAlmostEqual(hi[2], v["BASEMENT_SLAB_BOTTOM_Z"])
        upper_lo, upper_hi = self.bounds(v["wall_kitchen_stairway_u"])
        ground_lo, ground_hi = self.bounds(v["wall_stairway_g"])
        self.assertAlmostEqual((upper_lo[0]+upper_hi[0])/2, (ground_lo[0]+ground_hi[0])/2)

    def test_front_wall_stack_and_800mm_footing_are_centred(self):
        v = self.v
        for key in ("wall_basement_front", "wall_front_g", "wall_front_u"):
            lo, hi = self.bounds(v[key])
            self.assertAlmostEqual((lo[1]+hi[1])/2, v["BWT"]/2)
        self.assertAlmostEqual(v["wall_basement_front"].thickness, .30)
        properties = ifcopenshell.util.element.get_pset(v["front_footing"], "BBIM_StripFooting")
        self.assertEqual(properties["SourceWall"], v["wall_basement_front"].GlobalId)
        self.assertAlmostEqual(properties["Width"], .8)
        self.assertAlmostEqual(properties["Height"], .5)
        lo, hi = self.bounds(v["front_footing"])
        self.assertAlmostEqual(hi[1]-lo[1], .8)
        self.assertAlmostEqual((lo[1]+hi[1])/2, v["BWT"]/2)
        self.assertAlmostEqual(hi[2]-lo[2], .5)

    def test_outer_footing_ends_form_square_corners_at_both_ends(self):
        v = self.v
        front_lo, front_hi = self.bounds(v["front_footing"])
        back_footing = v["footings_by_source_wall"][v["wall_basement_back"].GlobalId]
        back_lo, back_hi = self.bounds(back_footing)
        east_lo, east_hi = self.bounds(v["east_footing"])
        west_lo, west_hi = self.bounds(v["west_footing"])
        self.assertAlmostEqual(front_lo[0], east_lo[0])
        self.assertAlmostEqual(front_hi[0], west_hi[0])
        self.assertAlmostEqual(front_lo[1], east_lo[1])
        self.assertAlmostEqual(front_lo[1], west_lo[1])
        self.assertAlmostEqual(front_lo[2], east_lo[2])
        self.assertAlmostEqual(front_lo[2], west_lo[2])
        self.assertAlmostEqual(back_lo[0], east_lo[0])
        self.assertAlmostEqual(back_hi[0], west_hi[0])
        self.assertAlmostEqual(back_hi[1], east_hi[1])
        self.assertAlmostEqual(back_hi[1], west_hi[1])
        self.assertAlmostEqual(back_hi[2], east_hi[2])
        self.assertAlmostEqual(back_hi[2], west_hi[2])
        for footing, axis in ((v["front_footing"], 0), (back_footing, 0),
                              (v["east_footing"], 1), (v["west_footing"], 1)):
            lo, hi = self.bounds(footing)
            data = ifcopenshell.util.element.get_pset(footing, "BBIM_StripFooting")
            self.assertAlmostEqual(data["Length"], hi[axis]-lo[axis])
            polygon = v["strip_footing_footprint"](footing)
            np.testing.assert_allclose(polygon.bounds, (*lo[:2], *hi[:2]), atol=1e-9)
        # All four outside corners are filled by the side and transverse strips.
        for wall_key, x in (("east_footing", front_lo[0]+.01),
                            ("west_footing", front_hi[0]-.01)):
            polygon = v["strip_footing_footprint"](v[wall_key])
            for y in (front_lo[1]+.01, back_hi[1]-.02):
                corner = box(x, y, x+.01, y+.01)
                self.assertTrue(polygon.covers(corner))
                transverse = v["front_footing"] if y < front_hi[1] else back_footing
                self.assertTrue(v["strip_footing_footprint"](transverse).covers(corner))

    def test_footing_heights_extend_down_from_the_base_plate_and_lowered_top(self):
        v = self.v
        for footing in v["foundation_footings"]:
            data = ifcopenshell.util.element.get_pset(footing, "BBIM_StripFooting")
            wall = v["house"].model.by_guid(data["SourceWall"])
            lo, hi = self.bounds(footing)
            expected_top = v["BASEMENT_SLAB_BOTTOM_Z"]
            if wall == v["wall_basement_front"]:
                expected_top -= v["FOUNDATION_STREET_STEP_DROP"]
            self.assertAlmostEqual(hi[2], expected_top)
            self.assertLessEqual(hi[2], v["BASEMENT_SLAB_BOTTOM_Z"]+1e-9)
            width, height = v["foundation_footing_dimensions"][wall]
            self.assertAlmostEqual(data["Width"], width)
            self.assertAlmostEqual(data["Height"], height)
            footprint = v["strip_footing_footprint"](footing)
            is_lowered = footprint.bounds[1] < v["FOUNDATION_STREET_STEP_Y"]
            expected_bottom = v["BASEMENT_SLAB_BOTTOM_Z"]-height
            if is_lowered:
                expected_bottom -= v["FOUNDATION_STREET_STEP_DROP"]
            self.assertAlmostEqual(lo[2], expected_bottom)
            self.assertAlmostEqual(data["MinimumBottomZ"], expected_bottom)

    def test_formwork_fills_all_five_street_step_gaps_below_the_base_plate(self):
        v = self.v
        sources = (v["wall_basement_front"], v["wall_basement_east"], v["wall_basement_west"],
                   v["wall_basement_s03_s04"], v["wall_basement_s04_s05"])
        walls = v["foundation_walls_below_base_plate"]
        self.assertEqual(len(walls), 5)
        expected, actual = Polygon(), Polygon()
        footprints = []
        for source in sources:
            lo, hi = self.bounds(source)
            expected = expected.union(box(*lo[:2], *hi[:2]).intersection(box(
                -1, -1, v["HOUSE_WIDTH"]+1, v["FOUNDATION_STREET_STEP_Y"],
            )))
        self.assertEqual({ifcopenshell.util.element.get_pset(w, "BBIM_FoundationWall", "SourceWall")
                          for w in walls}, {source.GlobalId for source in sources})
        for wall in walls:
            properties = ifcopenshell.util.element.get_pset(wall, "BBIM_FoundationWall")
            source = v["house"].model.by_guid(properties["SourceWall"])
            self.assertEqual(ifcopenshell.util.element.get_type(wall),
                             ifcopenshell.util.element.get_type(source))
            lo, hi = self.bounds(wall)
            self.assertAlmostEqual(lo[2], v["front_footing_top_z"])
            self.assertAlmostEqual(hi[2], v["BASEMENT_SLAB_BOTTOM_Z"])
            self.assertAlmostEqual(hi[2]-lo[2], v["FOUNDATION_STREET_STEP_DROP"])
            self.assertTrue(ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing"))
            if wall != v["foundation_front_wall"]:
                self.assertAlmostEqual(lo[1], v["front_foundation_inside_y"])
                self.assertAlmostEqual(hi[1], v["FOUNDATION_STREET_STEP_Y"])
            footprint = box(*lo[:2], *hi[:2])
            for previous in footprints:
                self.assertLess(footprint.intersection(previous).area, 1e-9)
            footprints.append(footprint)
            actual = actual.union(footprint)
        self.assertLess(actual.symmetric_difference(expected).area, 1e-9)

    def test_all_basement_and_under_slab_walls_use_the_300mm_type(self):
        v = self.v
        self.assertEqual(len(v["basement_rooms"]), 5)
        for wall in v["basement_walls"]:
            self.assertEqual(ifcopenshell.util.element.get_type(wall), v["basement_wall_type"])
            self.assertAlmostEqual(wall.thickness, .30)
            material = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
            self.assertEqual(material.MaterialLayers[0].Material.Name,
                             "ztracene bedneni")
            tangent = (np.asarray(wall.source_wall.end)-wall.source_wall.start)/wall.source_wall.length
            normal = np.array((-tangent[1], tangent[0]))
            old_centre = np.asarray(wall.source_wall.start)+normal*(wall.source_wall.body_offset+wall.source_wall.thickness/2)
            new_centre = v["wall_body_centreline_point"](wall)
            expected_offset = ((v["BWT"]-v["BACK_WALL_THICKNESS"])/2
                               if wall.source_wall in (v["wall_front_g"], v["wall_back_g"]) else 0)
            self.assertAlmostEqual(float((new_centre-old_centre)@normal), expected_offset)
        for wall in v["foundation_walls_below_base_plate"]:
            self.assertEqual(ifcopenshell.util.element.get_type(wall), v["basement_wall_type"])
            self.assertAlmostEqual(wall.thickness, .30)

    def test_s04_and_s05_reference_the_chimney_and_heb_independently(self):
        v = self.v
        garden_lo, _ = self.bounds(v["basement_ceiling_s05"].beam_shells[-1])
        _, street_hi = self.bounds(v["basement_ceiling_s05_front"].beam_shells[0])
        heb_lo, heb_hi = self.bounds(v["basement_s05_edge_heb"])
        self.assertAlmostEqual(garden_lo[1]-heb_hi[1], .05)
        self.assertAlmostEqual(heb_lo[1]-street_hi[1], .05)
        first_lo, _ = self.bounds(v["basement_ceiling_s04"].beam_shells[0])
        _, chimney_hi = self.bounds(v["chimney"])
        self.assertAlmostEqual(first_lo[1]-chimney_hi[1], .03)

    def test_chimney_clearance_follows_the_300mm_wall_and_configured_setout(self):
        v = self.v
        wall_lo, wall_hi = self.bounds(v["wall_basement_garden_rooms"])
        _, chimney_hi = self.bounds(v["chimney"])
        offset = v["CHIMNEY_BASEMENT_WALL_CENTER_OFFSET"]
        self.assertAlmostEqual((wall_lo[1]+wall_hi[1])/2-chimney_hi[1], offset)
        self.assertAlmostEqual(wall_lo[1]-chimney_hi[1], offset-.15)
        self.assertGreaterEqual(wall_lo[1]-chimney_hi[1]+1e-9, v["CHIMNEY_CEILING_INFILL_CLEARANCE"])

    def test_basement_room3_bearings_are_150mm_and_room5_keeps_125mm_internal_bearing(self):
        v = self.v
        room3, room4 = v["basement_ceiling_s03"], v["basement_ceiling_s04"]
        r3 = v["basement_rooms_by_id"]["S.03"].bounds
        r5 = v["basement_rooms_by_id"]["S.05"].bounds
        for beam in room3.beam_shells:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(hi[0]-r3[2], .15)
            self.assertAlmostEqual(r3[0]-lo[0], .15)
            self.assertLessEqual(hi[0], room4.start[0]+1e-9)
        self.assertAlmostEqual(room3.length, 3.5)
        for slab in (v["basement_ceiling_s05"], v["basement_ceiling_s05_front"]):
            self.assertAlmostEqual(slab.length, 2.5)
            for beam in slab.beam_shells:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(r5[0]-lo[0], .125)
                self.assertAlmostEqual(hi[0]-r5[2], .175)
                self.assertGreaterEqual(lo[0], room4.end[0]-1e-9)

    def test_room_floor_boundaries_follow_new_partition_faces(self):
        v = self.v
        wall_lo, wall_hi = self.bounds(v["wall_garden_partition_g"])
        left_lo, left_hi = self.bounds(v["pokoj1"])
        right_lo, right_hi = self.bounds(v["pokoj2"])
        self.assertAlmostEqual(left_hi[0], wall_lo[0])
        self.assertAlmostEqual(right_lo[0], wall_hi[0])
        self.assertAlmostEqual(left_hi[0]-left_lo[0], right_hi[0]-right_lo[0])

    def test_garden_rooms_have_two_independent_ceiling_assemblies_and_one_schedule_row(self):
        v = self.v
        slabs = (v["ceiling_pokoj1"], v["ceiling_pokoj2"])
        self.assertEqual(v["ceiling_garden_rooms"], slabs)
        self.assertNotEqual(slabs[0], slabs[1])
        for slab in slabs:
            self.assertEqual(len(slab.beams), 7)
            self.assertEqual(slab.structure, tuple(["beam"]+["space", "wide", "space", "beam"]*6))
            self.assertAlmostEqual(slab.width, 3.91)
            self.assertEqual(v["ceiling_slabs"].count(slab), 1)
        row = next(row for row in v["ceiling_schedule_rows"] if slabs[0] in row["slab"])
        self.assertTrue(all(slab in row["slab"] for slab in slabs))
        self.assertTrue({"0.01", "0.02"}.issubset(row["location"].split(", ")))
        self.assertEqual(sum(len(slab.beams) for slab in row["slab"] if slab in slabs), 14)
        self.assertFalse(any(obj.Name == "Ceiling - Pokoj 1 + Pokoj 2"
                             for obj in v["house"].model.by_type("IfcSlab")))

    def test_garden_ceiling_layouts_are_centred_between_actual_faces_and_clear_the_mid_ring(self):
        v = self.v
        ring, = [beam for beam in v["ground_ring_beams"]
                 if beam.source_wall == v["wall_garden_partition_g"]]
        ring_lo, ring_hi = self.bounds(ring)
        for index, (slab, room) in enumerate(zip(v["ceiling_garden_rooms"], (v["pokoj1"], v["pokoj2"]))):
            footprint = Polygon(slab.footprint)
            x0, y0, x1, y1 = Polygon(room.outline).bounds
            lo, hi = np.array(footprint.bounds[:2]), np.array(footprint.bounds[2:])
            np.testing.assert_allclose(footprint.centroid.coords[0], ((x0+x1)/2, (y0+y1)/2))
            self.assertAlmostEqual(slab.length, 3.5)
            self.assertAlmostEqual(y0-lo[1], .135)
            self.assertAlmostEqual(hi[1]-y1, .135)
            self.assertAlmostEqual(slab.block_start_offset, y0-lo[1])
            self.assertAlmostEqual(slab.block_end_offset, hi[1]-y1)
            self.assertAlmostEqual(lo[0]-x0, .05)
            self.assertAlmostEqual(x1-hi[0], .05)
            if index == 0:
                self.assertLess(hi[0], ring_lo[0])
            else:
                self.assertGreater(lo[0], ring_hi[0])
            centres = []
            for shell in slab.beam_shells:
                beam_lo, beam_hi = self.bounds(shell)
                self.assertAlmostEqual(beam_hi[1]-beam_lo[1], slab.length)
                self.assertLessEqual(beam_hi[0]-beam_lo[0], .16+1e-9)
                centres.append((beam_hi[0]+beam_lo[0])/2)
            np.testing.assert_allclose(np.diff(centres), .625)

    def test_editing_room1_ceiling_does_not_change_room2_or_basement(self):
        source = Path(__file__).with_name("house2.py")
        tree = ast.parse(source.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "ceiling_pokoj1"
                                  for target in node.targets))
        structure = next(keyword.value for keyword in assignment.value.keywords if keyword.arg == "structure")
        next(item for item in structure.elts if item.value == "wide").value = "narrow"
        ast.fix_missing_locations(tree)
        modified = {"__file__": str(source)}
        with patch.object(sys, "argv", [str(source)]), patch.object(House, "write"), redirect_stdout(StringIO()):
            exec(compile(tree, str(source), "exec"), modified)
        self.assertAlmostEqual(self.v["ceiling_pokoj1"].width-modified["ceiling_pokoj1"].width, .125)
        for key in ("ceiling_pokoj2", "ceiling_room3", "ceiling_bathroom", "ceiling_stairway",
                    "basement_ceiling_s01", "basement_ceiling_s02", "basement_ceiling_s03",
                    "basement_ceiling_s04", "basement_ceiling_s05", "basement_ceiling_s05_front"):
            self.assertEqual(modified[key].structure, self.v[key].structure)
            np.testing.assert_allclose(modified[key].beam_centerlines, self.v[key].beam_centerlines)

    def test_separate_stairway_beam_is_removed_from_model_and_schedule(self):
        v = self.v
        self.assertNotIn("ceiling_stairway_first_beam", v)
        self.assertFalse(any(slab.Name == "Ceiling - Schodiště krajní nosník"
                             for slab in v["house"].model.by_type("IfcSlab")))
        slab = v["ceiling_stairway"]
        row = next(row for row in v["ceiling_schedule_rows"] if slab in row["slab"])
        self.assertIn(slab, row["slab"])
        self.assertAlmostEqual(min(y for x,y in slab.footprint)
                               -v["ceiling_stairway_heb_front_y"]-v["ceiling_stairway_edge_heb"].width, .05)

    def test_stairway_ceiling_bearings_and_blocks_follow_physical_wall_faces(self):
        v = self.v
        slab = v["ceiling_stairway"]
        _, stairway_wall_hi = self.bounds(v["wall_stairway_g"])
        west_wall_lo, _ = self.bounds(v["wall_west_g"])
        stairway_face, west_face = stairway_wall_hi[0], west_wall_lo[0]
        self.assertAlmostEqual(slab.length, 2.5)
        self.assertAlmostEqual(slab.end[0]-west_face, .135)
        self.assertAlmostEqual(stairway_face-slab.start[0], .135)
        self.assertAlmostEqual((slab.start[0]+slab.end[0])/2, (stairway_face+west_face)/2)
        self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, stairway_face)
        self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, west_face)
        for beam in slab.beams:
            lo, hi = self.bounds(beam)
            self.assertAlmostEqual(hi[0]-west_face, .135)
            self.assertAlmostEqual(stairway_face-lo[0], .135)

    def test_room3_ceilings_are_centred_with_135mm_bearing_on_both_sides(self):
        v = self.v
        _, outer_hi = self.bounds(v["wall_east_g"])
        middle_lo, _ = self.bounds(v["wall_third_room_g"])
        for key in ("ceiling_room3", "ceiling_room3_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, 3.5)
            self.assertAlmostEqual(outer_hi[0]-slab.start[0], .135)
            self.assertAlmostEqual(slab.end[0]-middle_lo[0], .135)
            self.assertAlmostEqual((slab.start[0]+slab.end[0])/2, (outer_hi[0]+middle_lo[0])/2)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, outer_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, middle_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(outer_hi[0]-lo[0], .135)
                self.assertAlmostEqual(hi[0]-middle_lo[0], .135)

    def test_room3_sections_have_50mm_heb_gaps_and_standard_wide_narrow_bays(self):
        v = self.v
        garden, street = v["ceiling_room3"], v["ceiling_room3_front"]
        heb, = [beam for beam in v["purlin_support_girders"] if beam.Name.endswith(" - 0.03")]
        heb_lo, heb_hi = self.bounds(heb)
        for slab, is_garden in ((garden, True), (street, False)):
            self.assertEqual(len(slab.beams), 5)
            self.assertEqual([item for item in slab.structure if item in ("wide", "narrow")],
                             ["wide", "narrow", "narrow", "wide"])
            self.assertAlmostEqual(slab.length, 3.5)
            for part in slab.components:
                lo, hi = self.bounds(part)
                self.assertGreaterEqual(lo[1]-heb_hi[1] if is_garden else heb_lo[1]-hi[1], .05-1e-8)
        self.assertAlmostEqual(min(y for x,y in garden.footprint)-heb_hi[1], .05)
        self.assertAlmostEqual(heb_lo[1]-max(y for x,y in street.footprint), .05)
        self.assertAlmostEqual(max(y for x,y in garden.footprint)-v["GARDEN_ROOMS_WALL_Y"], .01)
        self.assertAlmostEqual(v["FRONT_WALL_THICKNESS"]-min(y for x,y in street.footprint), .05)
        # New room-3 rows clear the unchanged Y-spanning garden-room beams.
        self.assertLess(max(y for x,y in garden.footprint), v["ceiling_pokoj1"].start[1])
        drawing = next(d for d in v["house"]._drawings if d.name == "ceiling")
        annotations = [obj for rel in drawing.group.IsGroupedBy for obj in rel.RelatedObjects]
        dimension = next(obj for obj in annotations if obj.Name == f"{garden.Name} Last Beam to Wall")
        self.assertAlmostEqual(ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource", "Length"), .13)

    def test_stairway_ceiling_has_50mm_heb_gap_and_keeps_the_3m_stair_opening(self):
        v = self.v
        slab = v["ceiling_stairway"]
        heb_lo, heb_hi = self.bounds(v["ceiling_stairway_edge_heb"])
        self.assertEqual(len(slab.beams), 4)
        self.assertEqual([item for item in slab.structure if item in ("wide", "narrow")],
                         ["wide", "narrow", "wide"])
        for part in slab.components:
            lo, hi = self.bounds(part)
            self.assertGreaterEqual(lo[1]-heb_hi[1], .05-1e-8)
        self.assertAlmostEqual(min(y for x,y in slab.footprint)-heb_hi[1], .05)
        self.assertAlmostEqual(v["ceiling_stair_opening_end_y"]-v["ground_front_wall_inner_y"], 3.)
        self.assertAlmostEqual(v["ceiling_pokoj2"].start[1]-max(y for x,y in slab.footprint), .005)
        self.assertNotIn("ceiling_stairway_front", v)
        for name in ("ceiling", "ceiling2"):
            drawing = next(d for d in v["house"]._drawings if d.name == name)
            annotations = [obj for rel in drawing.group.IsGroupedBy for obj in rel.RelatedObjects]
            for label in ("0.03 Garden ceiling to HEB clearance", "0.03 Street ceiling to HEB clearance",
                          "Stairway ceiling to HEB clearance"):
                dimension = next(obj for obj in annotations if obj.Name == label)
                self.assertAlmostEqual(ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource", "Length"), .05)
            if name == "ceiling":
                dimension = next(obj for obj in annotations if obj.Name == f"{slab.Name} Last Beam to Wall")
                self.assertAlmostEqual(ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource", "Length"), .13)

    def test_bathroom_ceilings_have_150mm_bearings_and_a_matching_schedule_row(self):
        v = self.v
        _, middle_hi = self.bounds(v["wall_third_room_g"])
        stairway_lo, _ = self.bounds(v["wall_stairway_g"])
        for key in ("ceiling_bathroom", "ceiling_bathroom_front"):
            slab = v[key]
            self.assertAlmostEqual(slab.length, stairway_lo[0]-middle_hi[0]+.30)
            self.assertAlmostEqual(middle_hi[0]-slab.start[0], .15)
            self.assertAlmostEqual(slab.end[0]-stairway_lo[0], .15)
            self.assertAlmostEqual(slab.start[0]+slab.block_start_offset, middle_hi[0])
            self.assertAlmostEqual(slab.end[0]-slab.block_end_offset, stairway_lo[0])
            for beam in slab.beams:
                lo, hi = self.bounds(beam)
                self.assertAlmostEqual(middle_hi[0]-lo[0], .15)
                self.assertAlmostEqual(hi[0]-stairway_lo[0], .15)
        self.assertAlmostEqual(v["ceiling_bathroom"].start[0]-v["ceiling_room3"].end[0],
                               v["wall_third_room_g"].thickness-v["ROOM3_CEILING_MIDDLE_BEARING"]-.15)
        self.assertNotIn("ceiling_room3_hallway", v)
        self.assertNotIn("ceiling_front", v)
        for location in ("0.03", "0.04", "0.05"):
            for slab in v["ground_ceilings_by_room"][location]:
                row = next(row for row in v["ceiling_schedule_rows"] if slab in row["slab"])
                self.assertIn(location, row["location"].split(", "))
                self.assertTrue(all(round(part.length*1000) == round(slab.length*1000)
                                    for part in row["slab"]))

    def test_schedule_merges_matching_lengths_across_rooms_and_splits_mixed_rooms(self):
        house = House("Ceiling schedule regrouping")
        storey = house.storey("Ceiling", elevation=3)
        lengths = (3.5, 2.25, 3.5, 2.25, 2.5, 3.0)
        counts = (2, 2, 3, 4, 2, 3)
        slabs = [storey.miako_slab(
            f"Part {index}", start=(0, index*3), end=(length, index*3),
            top=0, direction=(0, 1), structure=["beam"]+["wide", "beam"]*(count-1),
        ) for index, (length, count) in enumerate(zip(lengths, counts))]
        rooms = {"A": (slabs[0], slabs[1]), "B": (slabs[2],), "C": (slabs[3], slabs[4])}
        drawing = house.add_drawing("Schedule", 2, 8, 4, 10, right_panel_width=60)

        def schedule():
            drawing.add_miako_beam_schedule(self.v["miako_schedule_rows_by_length"](rooms))
            return [(item["location"], item["length"], item["count"])
                    for item in drawing._right_panel_tables[-1]["items"]]

        self.assertEqual(schedule(), [("A, B", 3500, 5), ("A, C", 2250, 6), ("C", 2500, 2)])
        # A changed span must move B to its own row without retaining its old label.
        rooms["B"] = (slabs[5],)
        self.assertEqual(schedule(), [("A", 3500, 2), ("A, C", 2250, 6),
                                      ("B", 3000, 3), ("C", 2500, 2)])

    def test_bathroom_ceilings_straddle_the_heb_and_reach_the_front_wall(self):
        v = self.v
        garden, street = v["ceiling_bathroom"], v["ceiling_bathroom_front"]
        heb, = [beam for beam in v["purlin_support_girders"] if beam.Name.endswith(" - 0.05")]
        heb_lo, heb_hi = self.bounds(heb)
        self.assertEqual((len(garden.beams), len(street.beams)), (5, 5))
        self.assertEqual([item for item in garden.structure if item in ("wide", "narrow")],
                         ["wide", "narrow", "wide", "wide"])
        self.assertEqual([item for item in street.structure if item in ("wide", "narrow")],
                         ["wide", "narrow", "narrow", "wide"])
        for slab, is_garden, expected in ((garden, True, .025), (street, False, .05)):
            for part in slab.components:
                lo, hi = self.bounds(part)
                gap = lo[1]-heb_hi[1] if is_garden else heb_lo[1]-hi[1]
                self.assertGreaterEqual(gap, expected-1e-8)
            edge = min(y for x,y in slab.footprint) if is_garden else max(y for x,y in slab.footprint)
            self.assertAlmostEqual(edge-heb_hi[1] if is_garden else heb_lo[1]-edge, expected)
        front_lo, front_hi = self.bounds(v["wall_front_g"])
        street_edge = min(y for x,y in street.footprint)
        self.assertGreater(street_edge, front_lo[1])
        self.assertAlmostEqual(front_hi[1]-street_edge, .05)
        # The previously agreed 5 mm clash is intentionally retained in the model.
        _, first_hi = self.bounds(garden.beam_shells[0])
        for slab in v["ceiling_garden_rooms"]:
            self.assertAlmostEqual(slab.start[1], 5.385)
            self.assertAlmostEqual(first_hi[1]-slab.start[1], .005)

    def test_bathroom_chimney_opening_trims_only_the_first_wide_bay_without_infill(self):
        v = self.v
        slab = v["ceiling_bathroom"]
        chimney_lo, chimney_hi = self.bounds(v["chimney"])
        first_lo, _ = self.bounds(slab.beam_shells[0])
        _, second_hi = self.bounds(slab.beam_shells[1])
        self.assertAlmostEqual(first_lo[1]-chimney_hi[1], .03)
        self.assertAlmostEqual(chimney_lo[1]-second_hi[1], .035)
        opening = v["upper_bathroom_chimney_opening"]
        self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, slab.topping_element)
        region = v["chimney_ceiling_opening_region"]
        first_blocks = [block for block in slab.blocks if " Block 1." in block.Name]
        left, right = [], []
        for block in first_blocks:
            lo, hi = self.bounds(block)
            if hi[0] <= region.bounds[0]+1e-9:
                left.append(hi[0])
            elif lo[0] >= region.bounds[2]-1e-9:
                right.append(lo[0])
            else:
                self.fail("First-bay block still crosses the chimney opening")
        self.assertTrue(left)
        self.assertTrue(right)
        self.assertAlmostEqual(max(left), region.bounds[0])
        self.assertAlmostEqual(min(right), region.bounds[2])
        self.assertFalse(any(block.HasOpenings for block in slab.blocks if " Block 1." not in block.Name))
        self.assertFalse(any(ifcopenshell.util.element.get_pset(obj, "BBIM_CeilingInfill")
                             for obj in v["house"].model.by_type("IfcBuildingElementPart")))

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
