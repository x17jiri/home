"""Low-roof removal and replacement perpendicular roof geometry."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import Drawing, DrawingSheet, House


class LowRoofRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        targets = ("ground", "upper", "roof", "aa", "bb", "kanal",
                   "pohled_zapad", "pohled_vychod", "pohled_ulice", "pohled_zahrada")
        with patch.object(sys, "argv", [str(source), *targets]), \
             patch.object(House, "write"), patch.object(Drawing, "render") as render, \
             patch.object(DrawingSheet, "render") as sheet_render, redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]
            cls.sheets = [call.args[0] for call in sheet_render.call_args_list]

    @staticmethod
    def vertices(element, *, world=True):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, world)
        shape = ifcopenshell.geom.create_shape(settings, element)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return points[np.unique(np.asarray(shape.geometry.faces))]

    def test_removed_roof_walls_supports_and_closure_are_not_created(self):
        v = self.v
        for name in ("LOWER_NADEZDIVKA", "lower_rafters", "VAZNICE_LOWER_HEIGHT",
                     "VAZNICE_LOWER_BASE", "VAZNICE_LOWER_DIST", "PURLIN_LOWER_WALL_TOP_HEIGHT",
                     "lower_street_roof", "lower_garden_roof", "wall_front2_u", "wall_back2_u",
                     "wall_4_u", "beam3_lower", "beam4_lower", "roof_step_closure"):
            self.assertNotIn(name, v)
        facade, = v["west_facade"]
        self.assertEqual(facade.material_name, "Wood siding")
        points = self.vertices(facade)
        self.assertAlmostEqual(points[:, 2].max(),
                               v["transverse_wall_plate"].start[2] - v["transverse_wall_plate"].height/2)
        self.assertAlmostEqual(points[:, 1].min(),
                               -v["FACADE_INSULATION_THICKNESS"]-v["FACADE_THICKNESS"]+.001)
        self.assertAlmostEqual(points[:, 1].max(),
                               v["HOUSE_DEPTH"]+v["FACADE_INSULATION_THICKNESS"]+v["FACADE_THICKNESS"]-.001)
        self.assertEqual(tuple(name for name, *_ in v["PURLIN_X_SEGMENTS"]), ("left", "middle"))
        self.assertEqual(len(v["street_purlins"]), 2)
        self.assertEqual(len(v["garden_purlins"]), 2)
        self.assertEqual(len(v["roof_wall_plates"]), 5)  # Four original plates plus the new transverse plate.
        self.assertNotIn("Gable closure", v["roof_layer_storeys"])
        for element in v["house"].model.by_type("IfcElement"):
            self.assertNotIn("roof-step", (element.Name or "").lower())
            self.assertNotIn("lower street", (element.Name or "").lower())
            self.assertNotIn("lower garden", (element.Name or "").lower())

    def test_only_high_and_dormer_exterior_roof_parts_and_framing_remain(self):
        v = self.v
        self.assertEqual(v["rafters"], v["high_rafters"])
        self.assertEqual(len(v["rafters"]), 13)
        self.assertEqual({level for level in v["framing_levels"].values()}, {"high"})
        self.assertEqual([profile for _, _, profile in v["roof_over_rafter_x_ranges"]],
                         ["normal", "dormer", "normal"])
        self.assertEqual(len(v["roof_siding"]), 4)
        self.assertEqual(len(v["roof_sloped_siding"]), 4)
        maximum_x = max(hi for _, hi, _ in v["roof_over_rafter_x_ranges"])
        for material in ("MDF", "Roofing underlay", "Roof tiles"):
            layers = [element for plane in (v["street_roof"], v["garden_roof"], v["dormer_roof"])
                      for element in plane.elements if getattr(element, "material_name", None) == material]
            self.assertTrue(layers)
            for layer in layers:
                self.assertLessEqual(self.vertices(layer)[:, 0].max(), maximum_x + 1e-7)
        for member in (*v["main_roof_rafters"], *v["stronger_main_roof_rafters"],
                       *v["collar_ties"], *v["purlin_spacers"], *v["exterior_counter_battens"]):
            if getattr(member, "roof_plane", None) is v["transverse_roof"]:
                continue
            self.assertLess(self.vertices(member)[:, 0].max(), v["LOWER_NADEZDIVKA_X"] + .3)

    def test_high_roof_boundary_and_support_endpoints_meet_the_closure(self):
        v = self.v
        self.assertTrue(v["wall3_x"] < v["LOWER_NADEZDIVKA_X"] < v["HOUSE_WIDTH"])
        for beam in (v["street_purlins"][1], v["garden_purlins"][1], v["beam3"], v["beam4_b"]):
            end_x = max(beam.start[0], beam.end[0])
            inner, outer = v["west_roof_closure_x_ranges"]["Wall"]
            self.assertGreater(end_x, inner)
            self.assertLess(end_x, outer)
        x = v["HOUSE_WIDTH"] - .5
        self.assertEqual(v["exterior_roof_sections_at"](x), ())
        self.assertEqual(v["exterior_roof_planes_at"](x, side="street"), ())
        self.assertEqual(v["exterior_roof_planes_at"](x, side="garden"), ())
        self.assertEqual(v["exterior_ridge_planes_at"](x), ())

    def test_west_elevation_camera_is_outside_the_house_not_the_shortened_roof(self):
        v = self.v
        drawing = next(d for d in v["house"]._drawings if d.name == "pohled_zapad")
        self.assertGreater(drawing.x, v["HOUSE_WIDTH"] + v["FACADE_INSULATION_THICKNESS"])

    def test_east_upper_window_pair_has_requested_spacing_and_storey_relative_heights(self):
        v = self.v
        self.assertEqual(len(v["east_upper_windows"]), 2)
        spans = []
        for window in v["east_upper_windows"]:
            self.assertAlmostEqual(window.OverallWidth, 1.0)
            self.assertAlmostEqual(window.OverallHeight, 1.375)
            opening = window.FillsVoids[0].RelatingOpeningElement
            self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, v["wall_1_u"])
            points = self.vertices(opening)
            self.assertAlmostEqual(points[:, 2].min(), v["UPPER_FLOOR_START"]+1.0)
            self.assertAlmostEqual(points[:, 2].max(), v["UPPER_FLOOR_START"]+2.375)
            self.assertAlmostEqual(np.ptp(points[:, 1]), 1.0)
            spans.append((points[:, 1].min(), points[:, 1].max()))
        spans.sort()
        self.assertAlmostEqual(spans[1][0]-spans[0][1], 1.0)
        self.assertAlmostEqual((spans[0][0]+spans[1][1])/2, v["HALF_DEPTH"])

    def test_east_upper_windows_cut_the_facade_and_interrupt_the_ring_beam(self):
        v = self.v
        facade, = v["east_facade"]
        self.assertIn(v["wall_1_u"], facade.opening_walls)
        facade_openings = [self.vertices(opening) for opening in facade.openings]
        beams = [beam for beam in v["upper_ring_beams"] if beam.source_wall == v["wall_1_u"]]
        self.assertTrue(beams)
        for window in v["east_upper_windows"]:
            points = self.vertices(window.FillsVoids[0].RelatingOpeningElement)
            lo, hi = points[:, 1].min(), points[:, 1].max()
            self.assertTrue(any(np.allclose((hole[:, 1].min(), hole[:, 1].max(), hole[:, 2].min(), hole[:, 2].max()),
                                           (lo, hi, points[:, 2].min(), points[:, 2].max()))
                                for hole in facade_openings))
            for beam in beams:
                y0, y1 = sorted((beam.start[1], beam.end[1]))
                self.assertTrue(y1 <= lo+1e-7 or y0 >= hi-1e-7)
        self.assertAlmostEqual(v["window_area"](*v["east_upper_windows"]), 2.75)

    def test_dormer_side_facades_join_roof_surfaces_outside_the_wall_insulation(self):
        v = self.v
        self.assertEqual(len(v["dormer_side_facades"]), 2)
        bottom = v["offset_plane"](*v["garden_roof"].points, offset=v["ROOF_TILE_BOTTOM"]+v["ROOF_TILE_THICKNESS"])
        top = v["offset_plane"](*v["dormer_roof"].points, offset=v["RAFTER_Z_OFFSET"])
        for panel, wall, side in zip(v["dormer_side_facades"], (v["wall_2"], v["wall_3"]), ("left", "right")):
            with self.subTest(panel=panel.Name):
                self.assertEqual(panel.wall, wall)
                self.assertEqual(panel.side, side)
                self.assertEqual(panel.material_name, "Facade finish")
                self.assertEqual(len(panel.openings), 0)
                points = self.vertices(panel)
                host = self.vertices(wall)
                expected_x = ((host[:, 0].min()-v["FACADE_INSULATION_THICKNESS"]-v["FACADE_THICKNESS"],
                               host[:, 0].min()-v["FACADE_INSULATION_THICKNESS"])
                              if side == "left" else
                              (host[:, 0].max()+v["FACADE_INSULATION_THICKNESS"],
                               host[:, 0].max()+v["FACADE_INSULATION_THICKNESS"]+v["FACADE_THICKNESS"]))
                np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max()), expected_x, atol=1e-8)
                self.assertAlmostEqual(points[:, 1].max(),
                    v["HOUSE_DEPTH"]+v["FACADE_INSULATION_THICKNESS"]+v["FACADE_THICKNESS"]-.001)
                for x, y, z in points:
                    self.assertGreaterEqual(z, v["plane_height_at"](*bottom, x=x, y=y)-1e-7)
                    self.assertLessEqual(z, v["plane_height_at"](*top, x=x, y=y)+1e-7)
                ridge_edge = points[np.isclose(points[:, 1], points[:, 1].min())]
                for x, y, z in ridge_edge:
                    self.assertAlmostEqual(z, v["plane_height_at"](*bottom, x=x, y=y))
                    self.assertAlmostEqual(z, v["plane_height_at"](*top, x=x, y=y))
        for drawing in v["house"]._drawings:
            if drawing.name not in {"pohled_zapad", "Pohled - Východ"}:
                continue
            included = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(v["dormer_side_facades"]).issubset(included))

    def test_bb_does_not_draw_insulation_above_the_removed_west_gable(self):
        v = self.v
        drawing = next(d for d in v["house"]._drawings if d.name == "bb")
        records = [ifcopenshell.util.element.get_pset(element, "BBIM_WallInsulation")
                   for relation in drawing.group.IsGroupedBy for element in relation.RelatedObjects]
        west = [record for record in records if record and record.get("HostWall") == v["wall_4_g"].GlobalId]
        self.assertTrue(west)
        for record in west:
            self.assertLessEqual(record["EndZ"], v["ground_floor_height"])

    def test_wooden_street_and_garden_facades_follow_transverse_rafter_underside(self):
        v = self.v
        bottom = v["offset_plane"](*v["transverse_roof"].points, offset=v["RAFTER_Z_OFFSET"])
        for side in ("street", "garden"):
            panel = v[f"{side}_facade"][1]
            self.assertEqual(panel.material_name, "Wood siding")
            self.assertEqual(len(panel.outline), 4)
            points = self.vertices(panel)
            x0 = self.vertices(v[f"{side}_facade"][0])[:, 0].max()
            x1 = v["HOUSE_WIDTH"] + v["FACADE_INSULATION_THICKNESS"] + v["FACADE_THICKNESS"] - .001
            self.assertAlmostEqual(points[:, 0].min(), x0)
            self.assertAlmostEqual(points[:, 0].max(), x1)
            self.assertAlmostEqual(points[:, 2].min(), v["PERIMETER_TOP_HEIGHT"])
            for x in (x0, x1):
                edge = points[np.isclose(points[:, 0], x)]
                self.assertAlmostEqual(edge[:, 2].max(), v["plane_height_at"](*bottom, x=x, y=edge[0, 1]))
            for x, y, z in points:
                self.assertLessEqual(z, v["plane_height_at"](*bottom, x=x, y=y) + 1e-7)
            self.assertAlmostEqual(panel.start_height + panel.height + v["ground"].elevation,
                                   points[:, 2].max())

    def test_ceiling_only_layers_follow_configured_interior_ranges(self):
        v = self.v
        ranges = [(lo, hi) for lo, hi, profile in v["roof_under_rafter_x_ranges"] if profile == "ceiling"]
        if not ranges:
            self.assertEqual(v["lower_flat_ceiling_roof"].elements, ())
            return
        profile = v["inner_roof_section_at"](sum(ranges[0])/2)[2]
        self.assertTrue(profile["ceiling_only"])
        self.assertNotIn("street_plane", profile)
        ceilings = v["lower_flat_ceiling_roof"].elements
        self.assertEqual(len(ceilings), 2)
        expected = {
            "Vapour barrier": (2.9987331551100527, 4.991266844889948, 5.635, 5.65),
            "Gypsum plasterboard": (2.9849997996193562, 5.005000200380645, 5.545, 5.57),
        }
        for layer in ceilings:
            y0, y1, z0, z1 = expected[layer.material_name]
            points = self.vertices(layer)
            np.testing.assert_allclose(points.min(axis=0), (v["wall3_x"], y0, z0), atol=1e-8)
            np.testing.assert_allclose(points.max(axis=0), (v["wall4_start"], y1, z1), atol=1e-8)
        self.assertAlmostEqual(v["interior_ceiling_bottom_z_at"](v["HOUSE_WIDTH"]-1), 5.545)

    def test_miako_slabs_floors_internal_walls_and_fixtures_are_retained(self):
        v = self.v
        for name in ("ceiling1", "ceiling2", "ceiling3", "upper_sklad", "zachod_nahore",
                     "upper_pokoj_1", "upper_pokoj_2", "galerie", "wall_zachod_nahore",
                     "wall_pokoj2", "wall_2", "wall_3", "wall_4_g", "window_kk1"):
            self.assertIsNotNone(v[name].Representation, name)
        names = {element.Name for element in v["house"].model.by_type("IfcElement")}
        self.assertTrue({"WC", "Umyv", "Pračka", "Rekuperace"}.issubset(names))
        self.assertTrue(v["house"].model.by_type("IfcStair"))

    def test_upper_service_partitions_keep_the_first_y_and_end_at_finished_closure(self):
        v = self.v
        first, second = v["wall_zachod_nahore"], v["wall_za_umyvadlem"]
        inner = self.vertices(v["west_closure_wall"])[:, 0].min()
        self.assertAlmostEqual(v["WEST_CLOSURE_INNER_X"], inner)
        self.assertAlmostEqual(first.start[1], v["wall_zachod_nahore_y"])
        self.assertAlmostEqual(second.start[1], first.start[1]+2)
        for wall in (first, second):
            with self.subTest(wall=wall.GlobalId):
                points = self.vertices(wall)
                np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max()),
                                           (v["wall3_x"], inner), atol=1e-8)
                np.testing.assert_allclose((points[:, 1].min(), points[:, 1].max()),
                                           (wall.start[1]-wall.thickness, wall.start[1]), atol=1e-8)
                self.assertAlmostEqual(wall.height, 2.0)
                self.assertAlmostEqual(wall.thickness, .1)

    def test_shortened_upper_service_floors_meet_partition_faces_and_contain_fixtures(self):
        v = self.v
        first = self.vertices(v["wall_zachod_nahore"])
        second = self.vertices(v["wall_za_umyvadlem"])
        for room, y0, y1, fixture_name in (
            (v["upper_sklad"], first[:, 1].max(), second[:, 1].min(), "Umyv"),
            (v["zachod_nahore"], v["BWTy"], first[:, 1].min(), "WC"),
        ):
            with self.subTest(room=room.room_id):
                points = self.vertices(room)
                np.testing.assert_allclose(points.min(axis=0)[:2], (v["wall3_x"], y0), atol=1e-8)
                np.testing.assert_allclose(points.max(axis=0)[:2], (v["WEST_CLOSURE_INNER_X"], y1), atol=1e-8)
                self.assertAlmostEqual(room.area, (v["WEST_CLOSURE_INNER_X"]-v["wall3_x"])*(y1-y0))
                fixture, = [element for element in v["house"].model.by_type("IfcElement")
                    if element.Name == fixture_name
                    and ifcopenshell.util.element.get_container(element) == v["upper"].element]
                bounds = self.vertices(fixture)
                self.assertTrue(np.all(bounds[:, :2].min(axis=0) >= points[:, :2].min(axis=0)-1e-7))
                self.assertTrue(np.all(bounds[:, :2].max(axis=0) <= points[:, :2].max(axis=0)+1e-7))

    def test_schedules_and_composite_roof_sheet_have_no_deleted_members_or_zz_cut(self):
        v = self.v
        self.assertEqual(set(v["roof_elevation_definitions"]), {"roof_xx", "roof_yy"})
        self.assertEqual(self.sheets, ["roof.svg"])
        for stem in ("ground.svg", "upper.svg", "aa.svg", "bb.svg", "kanal.svg",
                     "pohled_zapad.svg", "pohled_vychod.svg", "pohled_ulice.svg", "pohled_zahrada.svg"):
            self.assertIn(stem, self.rendered)
        self.assertNotIn("roof_zz.svg", self.rendered)
        scheduled = [member for _, members, _, _ in v["timber_schedule_rows"] for member in members]
        self.assertEqual(len({member.GlobalId for member in scheduled}), len(scheduled))
        for member in (*v["roof_structural_beams"], *v["main_roof_rafters"], *v["dormer_roof_rafters"], *v["collar_ties"]):
            self.assertIn(member, scheduled)

    def test_transverse_purlin_has_the_requested_top_position_section_and_direction(self):
        v = self.v
        beam = v["transverse_purlin"]
        top = v["UPPER_FLOOR_START"] + v["TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR"]
        x = v["LOWER_NADEZDIVKA_X"] + .125
        self.assertEqual((beam.width, beam.height), (v["VAZNICE_SIDE_BASE"], v["VAZNICE_SIDE_HEIGHT"]))
        self.assertEqual(beam.kind, "BEAM")
        self.assertAlmostEqual(beam.start[0], x)
        self.assertAlmostEqual(beam.end[0], x)
        self.assertAlmostEqual(beam.start[2], top - beam.height/2)
        self.assertAlmostEqual(beam.end[2], beam.start[2])
        self.assertAlmostEqual(beam.length, v["HOUSE_DEPTH"])
        points = self.vertices(beam)
        np.testing.assert_allclose(points.min(axis=0), (x-beam.width/2, 0, top-beam.height), atol=1e-8)
        np.testing.assert_allclose(points.max(axis=0), (x+beam.width/2, v["HOUSE_DEPTH"], top), atol=1e-8)
        body = ifcopenshell.util.representation.get_representation(beam, "Model", "Body", "MODEL_VIEW")
        self.assertEqual(len(body.Items), 1)

    def test_transverse_wall_plate_is_centred_and_seated_directly_on_wall4_ring_beam(self):
        v = self.v
        beam = v["transverse_wall_plate"]
        bearings = [b for b in v["ring_beams"] if b.source_wall == v["wall_4_g"]]
        self.assertTrue(bearings)
        self.assertEqual((beam.width, beam.height), v["WALL_PLATE_SIZE"])
        self.assertEqual(beam.kind, "WALL_PLATE")
        points = self.vertices(beam)
        for bearing in bearings:
            self.assertAlmostEqual(beam.start[0], bearing.start[0])
            self.assertAlmostEqual(beam.end[0], bearing.end[0])
            self.assertAlmostEqual(points[:, 2].min(), bearing.start[2] + bearing.height/2)
            self.assertLessEqual(beam.width, bearing.width)
        self.assertAlmostEqual(points[:, 1].min(), 0)
        self.assertAlmostEqual(points[:, 1].max(), v["HOUSE_DEPTH"])

    def test_transverse_supports_follow_height_boundary_and_side_section_changes(self):
        v = self.v
        helper = v["add_transverse_roof_supports"]
        house = House("Tuned transverse members")
        upper = house.storey("Upper", elevation=v["UPPER_FLOOR_START"])
        with patch.dict(helper.__globals__, {
            "upper": upper, "LOWER_NADEZDIVKA_X": v["LOWER_NADEZDIVKA_X"]+.2,
            "TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR": 1.8, "VAZNICE_SIDE_HEIGHT": .3, "VAZNICE_SIDE_BASE": .18,
        }):
            purlin, plate = helper()
        self.assertEqual((purlin.width, purlin.height), (.18, .3))
        self.assertAlmostEqual(purlin.start[0], v["LOWER_NADEZDIVKA_X"]+.2+.125)
        self.assertAlmostEqual(self.vertices(purlin)[:, 2].max(), v["UPPER_FLOOR_START"]+1.8)
        np.testing.assert_allclose(plate.start, v["transverse_wall_plate"].start)
        np.testing.assert_allclose(plate.end, v["transverse_wall_plate"].end)
        self.assertAlmostEqual(v["transverse_purlin"].start[0], v["LOWER_NADEZDIVKA_X"]+.125)

    def test_transverse_support_validation_happens_before_creating_beams(self):
        v = self.v
        helper = v["add_transverse_roof_supports"]
        for height in (0, -1, float("nan"), float("inf")):
            with self.subTest(height=height), patch.dict(helper.__globals__, {"TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR": height}), \
                 patch.object(v["upper"], "beam") as create, self.assertRaisesRegex(ValueError, "positive and finite"):
                helper()
            create.assert_not_called()
        with patch.dict(helper.__globals__, {"ring_beams": ()}), patch.object(v["upper"], "beam") as create, \
             self.assertRaisesRegex(ValueError, "ring beam on wall 4"):
            helper()
        create.assert_not_called()

    def test_transverse_supports_are_in_the_roof_plan_elevations_and_schedule_once(self):
        v = self.v
        members = (v["transverse_purlin"], v["transverse_wall_plate"],
                   v["transverse_outer_support"], *v["transverse_support_posts"])
        for member in members:
            self.assertEqual(v["roof_structural_beams"].count(member), 1)
            rows = [row for row in v["timber_schedule_rows"] if member in row[1]]
            self.assertEqual(len(rows), 1)
            expected_material = ("GL24c" if member in (v["transverse_purlin"], v["transverse_outer_support"])
                                 else "C16" if member == v["transverse_wall_plate"] else "C22")
            self.assertEqual(rows[0][3]["material"], expected_material)
        drawings = [d for d in v["house"]._drawings if d.name == "Roof plan" or d.name.lower().startswith("pohled")]
        self.assertEqual(len(drawings), 5)
        for drawing in drawings:
            included = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include") or "IfcElement")
            self.assertTrue(set(members).issubset(included), drawing.name)

    def test_transverse_members_mirror_once_without_moving_the_live_model(self):
        v = self.v
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        for member in (v["transverse_purlin"], v["transverse_wall_plate"],
                       v["transverse_outer_support"], *v["transverse_support_posts"]):
            original = self.vertices(member)
            mirrored = self.vertices(exported.by_guid(member.GlobalId))
            self.assertEqual({tuple(p) for p in np.round(mirrored, 7)},
                             {tuple(p) for p in np.round(original * (-1, 1, 1), 7)})
            np.testing.assert_allclose(self.vertices(member), original)

    def test_transverse_canopy_reaches_eave_and_four_posts_meet_terrain_and_beam(self):
        v = self.v
        beam = v["transverse_outer_support"]
        posts = v["transverse_support_posts"]
        self.assertEqual(len(posts), 4)
        self.assertAlmostEqual(beam.start[0], v["HOUSE_WIDTH"]+1.75)
        self.assertEqual(beam.start[0], beam.end[0])
        self.assertEqual(beam.start[2], beam.end[2])
        np.testing.assert_allclose((beam.width, beam.height), (.16, .24))
        spacing = np.diff([post.start[1] for post in posts])
        np.testing.assert_allclose(spacing, [spacing[0]]*3)
        beam_points = self.vertices(beam)
        for post in posts:
            points = self.vertices(post)
            self.assertEqual(post.start[:2], post.end[:2])
            self.assertEqual(post.start[0], beam.start[0])
            self.assertAlmostEqual(points[:, 2].max(), beam_points[:, 2].min())
            self.assertAlmostEqual(points[:, 2].min(), v["earth_to_z"](v["y_to_earth"](post.start[1])))
            np.testing.assert_allclose(np.ptp(points[:, :2], axis=0), (.16, .16))
        for rafter in v["transverse_rafters"]:
            points = self.vertices(rafter)
            self.assertLess(points[:, 0].min(), beam.start[0]-beam.width/2)
            self.assertAlmostEqual(points[:, 0].max(), v["HOUSE_WIDTH"]+2.25-v["ROOF_EAVE_SETBACK"])
        tiles, = [layer for layer in v["transverse_roof"].elements
                  if getattr(layer, "material_name", None) == "Roof tiles"]
        self.assertAlmostEqual(self.vertices(tiles)[:, 0].max(), v["HOUSE_WIDTH"]+2.25)
        west = next(d for d in v["house"]._drawings if d.name == "pohled_zapad")
        self.assertGreater(west.x, v["HOUSE_WIDTH"]+2.25)

    def test_transverse_rafter_centres_are_wall_aligned_and_integer_metres_inside(self):
        v = self.v
        expected = (.04, 1., 2., 3., 4., 5., 6., 7., v["HOUSE_DEPTH"]-.04)
        self.assertEqual(v["transverse_rafter_y_positions"](), expected)
        self.assertEqual(len(v["transverse_rafters"]), len(expected))
        for rafter, y in zip(v["transverse_rafters"], expected):
            self.assertEqual((rafter.width, rafter.height), v["TRANSVERSE_RAFTER_SIZE"])
            self.assertEqual(rafter.height, .14)
            self.assertEqual(rafter.kind, "RAFTER")
            self.assertIs(rafter.roof_plane, v["transverse_roof"])
            self.assertAlmostEqual(rafter.start[1], y)
            self.assertAlmostEqual(rafter.end[1], y)
            self.assertEqual(ifcopenshell.util.element.get_container(rafter), v["roof_layer_storeys"]["Rafters"].element)
        self.assertAlmostEqual(self.vertices(v["transverse_rafters"][0])[:, 1].min(), 0)
        self.assertAlmostEqual(self.vertices(v["transverse_rafters"][-1])[:, 1].max(), v["HOUSE_DEPTH"])

    def test_transverse_rafter_positions_follow_depth_and_avoid_duplicate_end_centres(self):
        helper = self.v["transverse_rafter_y_positions"]
        for depth, thickness, expected in ((8., .12, (.06, 1., 2., 3., 4., 5., 6., 7., 7.94)),
                                            (7.04, .08, (.04, 1., 2., 3., 4., 5., 6., 7.)),
                                            (.8, .08, (.04, .76))):
            with self.subTest(depth=depth), patch.dict(helper.__globals__, {
                "HOUSE_DEPTH": depth, "TRANSVERSE_RAFTER_SIZE": (thickness, .14),
            }):
                np.testing.assert_allclose(helper(), expected)
                self.assertEqual(len(helper()), len(set(helper())))
        for depth in (.08, .05, float("nan"), float("inf")):
            with self.subTest(depth=depth), patch.dict(helper.__globals__, {"HOUSE_DEPTH": depth}), self.assertRaisesRegex(ValueError, "house depth"):
                helper()

    def test_transverse_roof_plane_passes_through_outer_top_support_edges(self):
        v = self.v
        plane = v["transverse_roof"]
        for support in (v["transverse_purlin"], v["transverse_wall_plate"], v["transverse_outer_support"]):
            x = support.start[0] + support.width/2
            z = support.start[2] + support.height/2
            self.assertAlmostEqual(v["plane_height_at"](*plane.points, x=x, y=v["HALF_DEPTH"]), z)
        np.testing.assert_allclose(plane.x_axis, (0, 1, 0), atol=1e-9)
        self.assertGreater(plane.y_axis[0], 0)
        self.assertLess(plane.y_axis[2], 0)
        self.assertGreater(plane.z_axis[2], 0)

    def test_transverse_rafters_have_exact_high_cut_and_both_shared_eave_cuts(self):
        v = self.v
        plane = v["transverse_roof"]
        high_x = v["LOWER_NADEZDIVKA_X"]
        eave_x = v["TRANSVERSE_ROOF_EAVE_X"] - v["ROOF_EAVE_SETBACK"]
        support = v["transverse_outer_support"]
        cut_z = support.start[2] - support.height/2 - v["ROOF_EAVE_DROP_BELOW_WALL_PLATE"]
        self.assertTrue(all(p[0] == high_x for p in plane.cuts[0]))
        self.assertTrue(all(p[2] == cut_z for p in plane.cuts[1]))
        self.assertTrue(all(p[0] == v["HOUSE_WIDTH"]+v["TRANSVERSE_ROOF_EAVE_OVERHANG"] for p in plane.cuts[2]))
        top_offset = v["RAFTER_Z_OFFSET"] + v["TRANSVERSE_RAFTER_SIZE"][1]
        horizontal_top_y = v["local_y_at_global_z"](plane, cut_z, local_z=top_offset)
        farthest_x = min(eave_x, plane.to_world((0, horizontal_top_y, top_offset))[0])
        for rafter in v["transverse_rafters"]:
            with self.subTest(rafter=rafter.Name):
                points = self.vertices(rafter)
                self.assertAlmostEqual(points[:, 0].min(), high_x)
                self.assertAlmostEqual(points[:, 0].max(), farthest_x)
                self.assertGreaterEqual(points[:, 2].min(), cut_z-1e-7)
                bottom_plane = v["offset_plane"](*plane.points, offset=v["RAFTER_Z_OFFSET"])
                expected_bottom = max(cut_z, v["plane_height_at"](*bottom_plane, x=eave_x, y=rafter.start[1]))
                self.assertAlmostEqual(points[:, 2].min(), expected_bottom)
                self.assertGreaterEqual(np.count_nonzero(np.isclose(points[:, 0], high_x)), 4)
                cut, = rafter.extra_cuts
                self.assertTrue(all(abs(p[0]-eave_x) < 1e-9 for p in cut))
                local = np.asarray([plane.to_local(point) for point in points])
                self.assertAlmostEqual(local[:, 2].min(), v["RAFTER_Z_OFFSET"])
                self.assertAlmostEqual(local[:, 2].max(), top_offset)

    def test_transverse_rafter_limits_and_setback_can_be_changed_independently(self):
        v = self.v
        plane = v["transverse_roof"]
        helper = v["local_y_limits_from_cuts"]
        for offset in (v["RAFTER_Z_OFFSET"], v["RAFTER_Z_OFFSET"]+v["TRANSVERSE_RAFTER_SIZE"][1]):
            for inset in (0, .02, .08):
                with self.subTest(offset=offset, inset=inset), patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": inset}):
                    lo, hi = helper(plane, offset, eave_setback=True)
                    first = plane.to_world((0, lo, offset))
                    last = plane.to_world((0, hi, offset))
                    self.assertAlmostEqual(first[0], v["LOWER_NADEZDIVKA_X"])
                    self.assertLessEqual(last[0], v["TRANSVERSE_ROOF_EAVE_X"]-inset+1e-7)
                    self.assertGreaterEqual(last[2], plane.cuts[1][0][2]-1e-7)
                    self.assertTrue(abs(last[0]-(v["TRANSVERSE_ROOF_EAVE_X"]-inset)) < 1e-7
                                    or abs(last[2]-plane.cuts[1][0][2]) < 1e-7)
                    cuts = v["roof_eave_setback_cuts"](plane)
                    self.assertEqual(len(cuts), 0 if inset == 0 else 1)

    def test_transverse_outer_layers_follow_y_overhang_and_x_eave_cuts(self):
        v = self.v
        plane = v["transverse_roof"]
        layers = [layer for layer in plane.elements if hasattr(layer, "outline")]
        self.assertEqual({layer.material_name for layer in layers},
                         {"MDF", "Roofing underlay", "Roof tiles"})
        expected_bottoms = {
            "MDF": v["RAFTER_Z_OFFSET"] + v["TRANSVERSE_RAFTER_SIZE"][1],
            "Roofing underlay": v["RAFTER_Z_OFFSET"] + v["TRANSVERSE_RAFTER_SIZE"][1] + v["MDF_THICKNESS"],
            "Roof tiles": (v["RAFTER_Z_OFFSET"] + v["TRANSVERSE_RAFTER_SIZE"][1] + v["MDF_THICKNESS"]
                           + v["UNDERLAY_THICKNESS"] + v["COUNTER_BATTEN_SIZE"][1] + v["TILE_BATTEN_SIZE"][1]),
        }
        for layer in layers:
            with self.subTest(material=layer.material_name):
                self.assertAlmostEqual(layer.z_offset, expected_bottoms[layer.material_name])
                points = self.vertices(layer)
                inset = 0 if layer.material_name == "Roof tiles" else v["ROOF_EAVE_SETBACK"]
                np.testing.assert_allclose((points[:, 1].min(), points[:, 1].max()),
                    (-v["TRANSVERSE_ROOF_Y_OVERHANG"] + inset,
                     v["HOUSE_DEPTH"] + v["TRANSVERSE_ROOF_Y_OVERHANG"] - inset), atol=1e-8)
                self.assertAlmostEqual(points[:, 0].min(), v["LOWER_NADEZDIVKA_X"])
                self.assertLessEqual(points[:, 0].max(), v["TRANSVERSE_ROOF_EAVE_X"]-inset+1e-7)
                self.assertGreaterEqual(points[:, 2].min(), plane.cuts[1][0][2]-1e-7)
                local = np.asarray([plane.to_local(point) for point in points])
                self.assertAlmostEqual(local[:, 2].min(), layer.z_offset)
                self.assertAlmostEqual(np.ptp(local[:, 2]), layer.thickness)
        tiles, = [layer for layer in layers if layer.material_name == "Roof tiles"]
        self.assertIsNotNone(ifcopenshell.util.element.get_pset(tiles, "BBIM_RoofTilePattern"))

    def test_transverse_battens_follow_new_rafters_and_cross_the_slope(self):
        v = self.v
        plane = v["transverse_roof"]
        counters = [beam for beam in v["exterior_counter_battens"] if beam.roof_plane is plane]
        self.assertEqual([beam.local_start[0] for beam in counters], list(v["transverse_rafter_y_positions"]()))
        tiles = [beam for beam in plane.elements if " tile batten " in (beam.Name or "")]
        self.assertGreater(len(tiles), 1)
        underlay, = [layer for layer in plane.elements
                     if hasattr(layer, "material_name") and layer.material_name == "Roofing underlay"]
        roof_tiles, = [layer for layer in plane.elements
                      if hasattr(layer, "material_name") and layer.material_name == "Roof tiles"]
        for beam in counters:
            self.assertAlmostEqual(beam.z_offset, underlay.z_offset + underlay.thickness)
        for beam in tiles:
            self.assertAlmostEqual(beam.z_offset + beam.height, roof_tiles.z_offset)
        for beam in (*counters, *tiles):
            with self.subTest(beam=beam.Name):
                points = self.vertices(beam)
                self.assertGreaterEqual(points[:, 0].min(), v["LOWER_NADEZDIVKA_X"]-1e-7)
                self.assertLessEqual(points[:, 0].max(), v["TRANSVERSE_ROOF_EAVE_X"]-v["ROOF_EAVE_SETBACK"]+1e-7)
                self.assertGreaterEqual(points[:, 2].min(), plane.cuts[1][0][2]-1e-7)
        for batten in tiles:
            self.assertAlmostEqual(batten.local_start[1], batten.local_end[1])
            points = self.vertices(batten)
            self.assertAlmostEqual(points[:, 1].min(), -v["TRANSVERSE_ROOF_Y_OVERHANG"]+v["ROOF_EAVE_SETBACK"])
            self.assertAlmostEqual(points[:, 1].max(), v["HOUSE_DEPTH"]+v["TRANSVERSE_ROOF_Y_OVERHANG"]-v["ROOF_EAVE_SETBACK"])

    def test_transverse_roof_siding_closes_three_edge_slots_under_the_tiles(self):
        v = self.v
        street, garden, west = v["transverse_roof_siding"]
        plane = v["transverse_roof"]
        inset = v["ROOF_EAVE_SETBACK"]
        y0, y1 = -v["TRANSVERSE_ROOF_Y_OVERHANG"], v["HOUSE_DEPTH"]+v["TRANSVERSE_ROOF_Y_OVERHANG"]
        x0, x1 = v["LOWER_NADEZDIVKA_X"], v["TRANSVERSE_ROOF_EAVE_X"]
        tiles, = [layer for layer in plane.elements
                  if hasattr(layer, "material_name") and layer.material_name == "Roof tiles"]
        top = v["offset_plane"](*plane.points, offset=tiles.z_offset)
        bottom = v["offset_plane"](*plane.points, offset=v["RAFTER_Z_OFFSET"])
        for board, bounds, container in (
            (street, (x0, x1-inset, y0, y0+inset), "Sloped siding"),
            (garden, (x0, x1-inset, y1-inset, y1), "Sloped siding"),
            (west, (x1-inset, x1, y0, y1), "Eave siding"),
        ):
            with self.subTest(board=board.Name):
                points = self.vertices(board)
                np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max(),
                                            points[:, 1].min(), points[:, 1].max()), bounds, atol=1e-8)
                self.assertEqual(ifcopenshell.util.element.get_material(board).Name, "Wood siding solid")
                self.assertEqual(ifcopenshell.util.element.get_container(board), v["roof_layer_storeys"][container].element)
                for x, y, z in points:
                    self.assertLessEqual(z, v["plane_height_at"](*top, x=x, y=y)+1e-7)
                    self.assertGreaterEqual(z, plane.cuts[1][0][2]-1e-7)
                    self.assertGreaterEqual(z, v["plane_height_at"](*bottom, x=x, y=y)-1e-7)
                expected_bottom = max(plane.cuts[1][0][2],
                    v["plane_height_at"](*bottom, x=bounds[1], y=bounds[2]))
                self.assertAlmostEqual(points[:, 2].min(), expected_bottom)
        helper = v["add_transverse_roof_siding"]
        with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": 0}), patch.object(v["house"], "add_box") as create:
            self.assertEqual(helper(), ())
            create.assert_not_called()

    def test_west_roof_closure_has_only_siding_and_a_300mm_wall(self):
        v = self.v
        ranges = v["west_roof_closure_x_ranges"]
        expected_widths = {
            "Siding": v["FACADE_THICKNESS"], "Wall": .30,
        }
        self.assertEqual(set(ranges), set(expected_widths))
        np.testing.assert_allclose(ranges["Siding"],
                                   (v["LOWER_NADEZDIVKA_X"]-.03-v["FACADE_THICKNESS"], v["LOWER_NADEZDIVKA_X"]-.03))
        edge = ranges["Siding"][1]
        for name, thickness in expected_widths.items():
            lo, hi = ranges[name]
            self.assertAlmostEqual(hi, edge)
            self.assertAlmostEqual(hi-lo, thickness)
            edge = lo
            panel = v["west_closure_wall"] if name == "Wall" else v["west_roof_closure"][name]
            points = self.vertices(panel)
            np.testing.assert_allclose((points[:, 0].min(), points[:, 0].max()), (lo, hi), atol=1e-8)
            if name == "Wall":
                self.assertTrue(panel.is_a("IfcWall"))
                material = ifcopenshell.util.element.get_material(panel, should_skip_usage=True)
                self.assertEqual(material.MaterialLayers[0].Material.Name, "West closure wall")
            else:
                self.assertTrue(panel.is_a("IfcCovering"))
                self.assertEqual(ifcopenshell.util.element.get_material(panel).Name,
                                 "Wood siding" if name == "Siding" else name)
            self.assertEqual(ifcopenshell.util.element.get_container(panel),
                             v["upper"].element)
        self.assertEqual(set(v["west_roof_closure"]), {"Siding"})
        self.assertAlmostEqual(v["WEST_CLOSURE_INNER_X"], ranges["Wall"][0])
        self.assertFalse(any(material.Name == "Wood fiberboard" for material in v["house"].model.by_type("IfcMaterial")))

    def test_west_roof_closure_wall_and_siding_meet_roof_profile(self):
        v = self.v
        for name, panel in (
            ("Siding", v["west_roof_closure"]["Siding"]),
            ("Wall", v["west_closure_wall"]),
        ):
            with self.subTest(layer=name):
                points = self.vertices(panel)
                self.assertAlmostEqual(points[:, 2].min(), v["UPPER_FLOOR_START"])
                for x, y, z in points:
                    plane = v["street_roof"] if y <= v["HALF_DEPTH"] else v["garden_roof"]
                    top = v["offset_plane"](*plane.points, offset=v["MDF_BOTTOM"])
                    self.assertLessEqual(z, v["plane_height_at"](*top, x=x, y=y)+1e-7)
                for y in (points[:, 1].min(), points[:, 1].max()):
                    edge = points[np.isclose(points[:, 1], y)]
                    plane = v["street_roof"] if y < v["HALF_DEPTH"] else v["garden_roof"]
                    top = v["offset_plane"](*plane.points, offset=v["MDF_BOTTOM"])
                    self.assertAlmostEqual(edge[:, 2].max(),
                        v["plane_height_at"](*top, x=edge[0, 0], y=y))

    def test_west_roof_closure_is_visible_and_mirrors_once(self):
        v = self.v
        panels = {*v["west_roof_closure"].values(), v["west_closure_wall"], v["west_closure_window"]}
        for drawing in v["house"]._drawings:
            if drawing.name not in {"Drawing 2", "bb", "pohled_zapad", "Pohled - Ulice", "Pohled - Zahrada"}:
                continue
            included = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include") or "IfcElement")
            self.assertTrue(panels.issubset(included), drawing.name)
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        for panel in panels:
            original = self.vertices(panel)
            mirrored = self.vertices(exported.by_guid(panel.GlobalId))
            self.assertEqual({tuple(p) for p in np.round(mirrored, 7)},
                             {tuple(p) for p in np.round(original*(-1, 1, 1), 7)})

    def test_west_closure_window_cuts_the_wall_and_siding(self):
        v = self.v
        wall, window = v["west_closure_wall"], v["west_closure_window"]
        self.assertAlmostEqual(window.OverallWidth, v["WEST_CLOSURE_WINDOW_WIDTH"])
        self.assertAlmostEqual(window.OverallHeight, v["WEST_CLOSURE_WINDOW_HEIGHT"])
        self.assertEqual(len(wall.HasOpenings), 1)
        opening = window.FillsVoids[0].RelatingOpeningElement
        self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, wall)
        points = self.vertices(opening)
        self.assertAlmostEqual((points[:, 1].min()+points[:, 1].max())/2, v["WEST_CLOSURE_WINDOW_CENTER_Y"])
        self.assertAlmostEqual(points[:, 2].min(),
            v["UPPER_FLOOR_START"]+v["UPPER_FLOOR_THICKNESS"]+v["WEST_CLOSURE_WINDOW_SILL_HEIGHT"])
        tiles, = [layer for layer in v["transverse_roof"].elements
                  if getattr(layer, "material_name", None) == "Roof tiles"]
        self.assertGreater(points[:, 2].min(), self.vertices(tiles)[:, 2].max())
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        uncut = ifcopenshell.geom.settings()
        uncut.set(uncut.USE_WORLD_COORDS, True)
        uncut.set(uncut.DISABLE_OPENING_SUBTRACTIONS, True)
        for host in (wall, *v["west_roof_closure"].values()):
            with self.subTest(host=host.Name):
                self.assertEqual(len(host.HasOpenings), 1)
                before = ifcopenshell.geom.create_shape(uncut, host)
                after = ifcopenshell.geom.create_shape(settings, host)
                removed = ifcopenshell.util.shape.get_volume(before.geometry)-ifcopenshell.util.shape.get_volume(after.geometry)
                self.assertAlmostEqual(removed,
                    v["WEST_CLOSURE_WINDOW_WIDTH"]*v["WEST_CLOSURE_WINDOW_HEIGHT"]*host.thickness)
                if host is not wall:
                    self.assertEqual(host.wall, wall)
                    self.assertEqual(host.opening_walls, (wall,))
        interior = self.vertices(wall)
        self.assertAlmostEqual(interior[:, 0].min(), v["WEST_CLOSURE_INNER_X"])

    def test_transverse_rafters_are_scheduled_once_visible_and_mirrored_correctly(self):
        v = self.v
        rows = [row for row in v["timber_schedule_rows"] if row[0].startswith("Krokve – příčné")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0][1]), set(v["transverse_rafters"]))
        self.assertEqual(rows[0][3]["material"], "C22")
        self.assertEqual(len({round(beam.finished_length(), 7) for beam in rows[0][1]}), 1)
        drawings = [d for d in v["house"]._drawings if d.name == "Roof plan" or d.name.lower().startswith("pohled")]
        for drawing in drawings:
            included = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(v["transverse_rafters"]).issubset(included), drawing.name)
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        for rafter in v["transverse_rafters"]:
            original = self.vertices(rafter)
            mirrored = self.vertices(exported.by_guid(rafter.GlobalId))
            self.assertEqual({tuple(p) for p in np.round(mirrored, 7)},
                             {tuple(p) for p in np.round(original*(-1, 1, 1), 7)})


if __name__ == "__main__":
    unittest.main()
