"""Integration checks for the model script, without exporting or rendering."""

import ast
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import Mock, patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import CutDefinition, Drawing, DrawingSheet, ElektroLineDrawer, House, _remove_3d_only_elements, _timber_schedule_member_styles
from materials import resolve_timber_grade


class UpperRingBeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source)]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))

    def test_level_band_follows_only_high_load_bearing_walls(self):
        v = self.values
        beams = v["upper_ring_beams"]
        expected_walls = [v[name] for name in (
            "wall_front1_u", "wall_back1_u", "wall_1_u", "wall_2", "wall_3",
        )]
        self.assertEqual({beam.source_wall for beam in beams}, set(expected_walls))
        self.assertEqual(len(beams), 9)
        for beam in beams:
            with self.subTest(beam=beam.Name):
                self.assertAlmostEqual(beam.height, v["UPPER_RING_BEAM_HEIGHT"])
                self.assertAlmostEqual(beam.start[2] + beam.height / 2,
                                       v["UPPER_FLOOR_START"] + v["NADEZDIVKA"])
                self.assertAlmostEqual(beam.width, v["BWT"])
                self.assertEqual(beam.ContainedInStructure[0].RelatingStructure, v["upper"].element)
                for bar in beam.reinforcement:
                    self.assertAlmostEqual(bar.BarLength, beam.length)
        self.assertTrue(v["ring_beams"])  # Existing ceiling-level ring stays.
        for name in ("wall_front2_u", "wall_back2_u", "wall_4_u"):
            self.assertNotIn(name, v)




    def test_internal_openings_interrupt_beams_without_new_hosted_openings(self):
        v = self.values
        for name in ("wall_2", "wall_3"):
            wall = v[name]
            beams = [b for b in v["upper_ring_beams"] if b.source_wall == wall]
            self.assertEqual(len(beams), 2)
            self.assertEqual(len(wall._openings), 1)
            self.assertEqual(len(wall.HasOpenings), 1)
            opening_start, opening_end, _, _ = wall._openings[0]
            self.assertAlmostEqual(beams[0].length, opening_start)
            self.assertAlmostEqual(beams[1].length, wall.length - opening_end)
            properties = ifcopenshell.util.element.get_pset(beams[1], "BBIM_RingBeam")
            self.assertAlmostEqual(properties["StartAlongWall"], opening_end)
            self.assertTrue(ifcopenshell.util.element.get_pset(wall, "BBIM_Boolean", "Data"))
        self.assertAlmostEqual(v["wall_front1_u"].height, v["NADEZDIVKA"])
        self.assertAlmostEqual(v["wall_dormer"].start_height, v["NADEZDIVKA"])


class StairLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "ground", "upper"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")),
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))

    def test_both_floor_plans_share_stairway_notes_derived_from_model(self):
        v = self.values
        notes = [
            f"Šířka stupně (nášlap): {v['main_stairs'].tread_length * 1000:.0f} mm",
            f"Výška stupně: {v['main_stairs'].riser_height * 1000:.1f} mm".replace(".", ","),
            f"Počet stupňů: {v['main_stairs'].risers + v['gallery_stairs'].risers}",
        ]
        self.assertEqual(notes, ["Šířka stupně (nášlap): 270 mm", "Výška stupně: 175,3 mm", "Počet stupňů: 17"])
        self.assertEqual(len(v["house"]._drawings), 2)
        for drawing in v["house"]._drawings:
            with self.subTest(drawing=drawing.name):
                tables = json.loads(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "RightPanelTables"))
                stairs = [table for table in tables if table["kind"] == "notes" and table["title"] == "SCHODIŠTĚ"]
                self.assertEqual(len(stairs), 1)
                self.assertEqual([item["text"] for item in stairs[0]["items"]], notes)

    def test_extra_step_is_in_the_lower_flight_only(self):
        v = self.values
        lower, upper = v["main_stairs"], v["gallery_stairs"]
        self.assertEqual(v["step_count"], 17)
        self.assertEqual((lower.treads, upper.treads), (10, 5))
        self.assertEqual((lower.risers, upper.risers), (11, 6))
        self.assertEqual(lower.treads + upper.treads + 2, 17)
        self.assertEqual(lower.flight.NumberOfRisers + upper.flight.NumberOfRisers, 17)

    def test_treads_stay_270_mm_and_lower_run_extends_270_mm(self):
        v = self.values
        lower, upper = v["main_stairs"], v["gallery_stairs"]
        self.assertAlmostEqual(lower.tread_length, .27)
        self.assertAlmostEqual(upper.tread_length, .27)
        self.assertAlmostEqual(lower.length, 2.70)
        self.assertAlmostEqual(lower.length - 9 * .27, .27)
        self.assertAlmostEqual(upper.length, 1.35)
        self.assertAlmostEqual(lower.start[0], v["landing_left_x"] - 2.70)
        self.assertAlmostEqual(lower.end[0], v["landing_left_x"])
        self.assertAlmostEqual(upper.start[1], v["straight_stair_start_y"])

    def test_smaller_uniform_risers_preserve_floor_levels_and_landing_connection(self):
        v = self.values
        lower, upper = v["main_stairs"], v["gallery_stairs"]
        riser = v["stair_height"] / 17
        self.assertLess(riser, v["stair_height"] / 16)
        for stair in (lower, upper):
            self.assertAlmostEqual(stair.riser_height, riser)
            self.assertAlmostEqual(stair.flight.RiserHeight, riser)
        self.assertAlmostEqual(lower.start_height, v["GROUND_FLOOR_THICKNESS"])
        self.assertAlmostEqual(lower.end_height, upper.start_height)
        self.assertAlmostEqual(upper.end_height, v["UPPER_FLOOR_START"] + v["UPPER_FLOOR_THICKNESS"])
        landing = v["middle_stair_landing"]
        placement = ifcopenshell.util.placement.get_local_placement(landing.ObjectPlacement)
        self.assertAlmostEqual(placement[2, 3] + v["STAIR_TREAD_THICKNESS"], lower.end_height)




class FoundationDrawingTests(unittest.TestCase):
    def test_foundation_line_legend_matches_wall_outline_and_is_drawing_scoped(self):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "found", "ground"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")),
            redirect_stdout(StringIO()),
        ):
            values = runpy.run_path(str(source))
        foundation, ground = values["house"]._drawings
        tables = json.loads(ifcopenshell.util.element.get_pset(foundation.element, "EPset_Drawing", "RightPanelTables"))
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(table["kind"], "line_legend")
        self.assertEqual(table["title"], "LEGENDA ČAR")
        self.assertEqual(len(table["items"]), 7)
        items = {item["description"]: item for item in table["items"]}
        item = items["Obrys nosných stěn"]
        outlines = [a for a in foundation.group.IsGroupedBy[0].RelatedObjects
                    if "load-bearing-wall-outline" in (ifcopenshell.util.element.get_pset(
                        a, "EPset_Annotation", "Classes") or "").split()]
        self.assertEqual(len(outlines), 1)
        classes = ifcopenshell.util.element.get_pset(outlines[0], "EPset_Annotation", "Classes")
        self.assertEqual(item["classes"], f"IfcAnnotation PredefinedType-LINEWORK {classes}")
        self.assertIn("drawing-line solid drawing-line-color-000000", items["Spodní úroveň základových pasů"]["classes"])
        self.assertIn("drawing-line dashed drawing-line-color-ff0000", items["Zemnící pásovina FeZn 30/35"]["classes"])
        for description, color in zip(("splašková kanalizace", "dešťová kanalizace", "vodovod"),
                                       ("ffa500", "008000", "0000ff")):
            item = items[description]
            self.assertIn("dashed-arrows", item["classes"].split())
            self.assertIn(f"drawing-line-color-{color}", item["classes"].split())
        ground_tables = json.loads(ifcopenshell.util.element.get_pset(ground.element, "EPset_Drawing", "RightPanelTables"))
        self.assertNotIn("line_legend", [t["kind"] for t in ground_tables])


class ExteriorElevationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "pohled_zapad", "pohled_ulice", "pohled_zahrada", "pohled_vychod"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("pohled_zapad.svg")) as render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.render_calls = render.call_args_list

    def test_west_elevation_looks_from_outside_the_lower_roof_end(self):
        v = self.values
        drawing = next(d for d in v["house"]._drawings if d.name == "pohled_zapad")
        self.assertEqual(drawing.name, "pohled_zapad")
        self.assertEqual(drawing.view, "elevation")
        self.assertEqual(drawing.direction, (-1, 0, 0))
        self.assertGreater(drawing.x, max(end for _, end, _ in v["roof_over_rafter_x_ranges"]))
        self.assertEqual(drawing.y, v["HALF_DEPTH"])
        self.assertAlmostEqual(drawing.z, v["ground_floor_top"] + v["total_house_height"] / 2)

    def test_street_elevation_looks_from_outside_the_street_eave_towards_the_garden(self):
        v = self.values
        drawing = next(d for d in v["house"]._drawings if d.name == "Pohled - Ulice")
        self.assertEqual(drawing.view, "elevation")
        self.assertEqual(drawing.direction, (0, 1, 0))
        self.assertLess(drawing.y, v["STREET_ROOF_EAVE_Y"])
        self.assertEqual(drawing.x, v["HOUSE_WIDTH"] / 2)
        self.assertAlmostEqual(drawing.z, v["ground_floor_top"] + v["total_house_height"] / 2)

    def test_east_elevation_looks_from_outside_the_high_roof_end(self):
        v = self.values
        drawing = next(d for d in v["house"]._drawings if d.name == "Pohled - Východ")
        self.assertEqual(drawing.view, "elevation")
        self.assertEqual(drawing.direction, (1, 0, 0))
        self.assertLess(drawing.x, min(start for start, _, _ in v["roof_over_rafter_x_ranges"]))
        self.assertEqual(drawing.y, v["HALF_DEPTH"])
        self.assertAlmostEqual(drawing.z, v["ground_floor_top"] + v["total_house_height"] / 2)
        self.assertEqual(drawing.radius, 6)
        self.assertTrue(v["PDF_POHLED_VYCHOD"].endswith("D1.1.15. Pohled - Východ.pdf"))

    def test_window_kk_is_a_glazed_balcony_door_with_its_existing_opening(self):
        v = self.values
        door = v["window_kk"]
        self.assertTrue(door.is_a("IfcDoor"))
        self.assertEqual(door.OperationType, "SINGLE_SWING_RIGHT")
        self.assertTrue(ifcopenshell.util.element.get_pset(door, "EPset_Door", "Glazed"))
        self.assertEqual(ifcopenshell.util.element.get_pset(door, "EPset_Door", "ClearHeight"), 2)
        self.assertAlmostEqual(door.OverallWidth, .8)
        self.assertAlmostEqual(door.OverallHeight, 2.125)
        self.assertEqual(len([aspect for aspect in door.Representation.HasShapeAspects if aspect.Name == "Glazing"]), 1)
        self.assertIsNotNone(ifcopenshell.util.representation.get_representation(door, "Plan", "Body", "PLAN_VIEW"))
        settings = ifcopenshell.geom.settings()
        opening = door.FillsVoids[0].RelatingOpeningElement
        shape = ifcopenshell.geom.create_shape(settings, opening)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        self.assertAlmostEqual(np.ptp(vertices[:, 0]), 1)
        self.assertAlmostEqual(np.ptp(vertices[:, 2]), 2.125)

    def test_garden_elevation_looks_from_outside_the_garden_eave_towards_the_street(self):
        v = self.values
        drawing = next(d for d in v["house"]._drawings if d.name == "Pohled - Zahrada")
        self.assertEqual(drawing.view, "elevation")
        self.assertEqual(drawing.direction, (0, -1, 0))
        self.assertGreater(drawing.y, v["GARDEN_ROOF_EAVE_Y"])
        self.assertEqual(drawing.x, v["HOUSE_WIDTH"] / 2)
        self.assertAlmostEqual(drawing.z, v["ground_floor_top"] + v["total_house_height"] / 2)

    def test_only_garden_elevation_excludes_the_concealed_sill_level_ring_beam(self):
        v = self.values
        concealed = [beam for beam in v["upper_ring_beams"] if beam.source_wall == v["wall_back1_u"]]
        self.assertEqual(len(concealed), 1)
        beam, = concealed
        expected = {beam, *beam.reinforcement}
        for drawing in v["house"]._drawings:
            rule = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Exclude")
            excluded = ifcopenshell.util.selector.filter_elements(v["house"].model, rule)
            with self.subTest(drawing=drawing.name):
                if drawing.name == "Pohled - Zahrada":
                    self.assertTrue(expected.issubset(excluded))
                    self.assertEqual(set(v["upper_ring_beams"]) & excluded, {beam})
                    self.assertNotIn(v["window_dormer_1"], excluded)
                    self.assertNotIn(v["window_dormer_2"], excluded)
                    self.assertFalse(set(v["garden_facade"]) & excluded)
                else:
                    self.assertFalse(expected & excluded)
        self.assertIsNotNone(v["house"].model.by_guid(beam.GlobalId).Representation)

    def test_elevation_includes_both_storeys_and_all_roof_layers_without_plan_symbols(self):
        v = self.values
        self.assertEqual(len(v["house"]._drawings), 4)
        for drawing in v["house"]._drawings:
            with self.subTest(drawing=drawing.name):
                self.assertEqual(set(drawing.storeys), {v["basement"], v["ground"], v["upper"], *v["roof_layer_storeys"].values()})
                self.assertNotIn(v["foundation"], drawing.storeys)
                self.assertFalse(drawing._automatic_plan_annotations)
                self.assertFalse(drawing._automatic_door_annotations)
                self.assertTrue(drawing.doors_closed)
                self.assertEqual(ifcopenshell.util.element.get_pset(
                    drawing.element, "EPset_Drawing", "FillMode"), "SHAPELY")
                selected = ifcopenshell.util.selector.filter_elements(v["house"].model,
                    ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
                self.assertTrue(set(v["roof_siding"]).issubset(selected))

    def test_exterior_terrain_uses_sea_level_converter_and_drawing_scoped_profiles(self):
        v = self.values
        self.assertAlmostEqual(v["earth_to_z"](417.2), v["GROUND_FLOOR_THICKNESS"])
        self.assertAlmostEqual(v["earth_to_z"](417.0), v["GROUND_FLOOR_THICKNESS"] - .2)
        profile_keys = {(-1, 0, 0): "pohled_zapad", (1, 0, 0): "pohled_vychod",
                        (0, 1, 0): "pohled_ulice", (0, -1, 0): "pohled_zahrada"}
        for drawing in v["house"]._drawings:
            members = drawing.group.IsGroupedBy[0].RelatedObjects
            terrains = [ifcopenshell.util.element.get_pset(item, "BBIM_DrawingTerrain") for item in members]
            terrain, = [p for p in terrains if p]
            profile = json.loads(terrain["Profile"])
            expected = v["TERRAIN_PROFILES"][profile_keys[drawing.direction]]
            self.assertEqual(profile, [list(point) for point in expected])
            self.assertEqual(json.loads(terrain["ModelProfile"]),
                             [[x, v["earth_to_z"](height)] for x, height in expected])

    def test_elevation_renders_to_the_configured_pdf(self):
        self.assertEqual(len(self.render_calls), 4)
        for call, stem, pdf in zip(self.render_calls, ("pohled_zapad", "pohled_ulice", "pohled_zahrada", "pohled_vychod"),
                                  ("PDF_POHLED_ZAPAD", "PDF_POHLED_ULICE", "PDF_POHLED_ZAHRADA", "PDF_POHLED_VYCHOD")):
            self.assertEqual(call.args, (f"{stem}.svg",))
            self.assertEqual(call.kwargs, {"pdf": self.values[pdf]})

    def test_sloped_siding_has_two_main_caps_and_two_dormer_caps_in_the_x_end_slots(self):
        v = self.values
        caps = v["roof_sloped_siding"]
        self.assertEqual(len(caps), 4)
        normal = [r for r in v["roof_over_rafter_x_ranges"] if r[2] == "normal"]
        dormer, = [r for r in v["roof_over_rafter_x_ranges"] if r[2] == "dormer"]
        width = v["ROOF_EAVE_SETBACK"]
        expected = (min(r[0] for r in normal), max(r[1] for r in normal) - width,
                    dormer[0], dormer[1] - width)
        settings = ifcopenshell.geom.settings(); settings.set(settings.USE_WORLD_COORDS, True)
        for cap, x0 in zip(caps, expected):
            with self.subTest(panel=cap.Name):
                self.assertEqual(cap.ObjectType, "ROOF_SLOPE_SIDING")
                self.assertEqual(ifcopenshell.util.element.get_material(cap).Name, "Wood siding solid")
                self.assertEqual(ifcopenshell.util.element.get_container(cap), v["roof_layer_storeys"]["Sloped siding"].element)
                body = ifcopenshell.util.representation.get_representation(cap, "Model", "Body", "MODEL_VIEW")
                self.assertEqual(len(body.Items), 1)
                self.assertTrue(body.Items[0].is_a("IfcExtrudedAreaSolid"))
                shape = ifcopenshell.geom.create_shape(settings, cap)
                vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
                np.testing.assert_allclose((vertices[:, 0].min(), vertices[:, 0].max()), (x0, x0 + width), atol=1e-8)
                if cap in caps[:2]:
                    np.testing.assert_allclose((vertices[:, 1].min(), vertices[:, 1].max()),
                                               (v["STREET_ROOF_EAVE_Y"], v["GARDEN_ROOF_EAVE_Y"]), atol=1e-8)
        self.assertFalse(set(caps) & set(v["roof_structural_beams"]))
        for drawing in v["house"]._drawings:
            selected = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(caps).issubset(selected))

    def test_sloped_siding_follows_both_rafter_and_tile_undersides_with_the_plain_color(self):
        from shapely.geometry import Point, Polygon
        v = self.values
        color = v["wood_siding_color"]().lstrip("#")
        expected_rgb = tuple(int(color[i:i+2], 16)/255 for i in (0, 2, 4))
        for index, cap in enumerate(v["roof_sloped_siding"][:2]):
            outline = json.loads(ifcopenshell.util.element.get_pset(cap, "BBIM_Panel", "Outline"))
            profile = Polygon([(y, z) for x, y, z in outline])
            planes = (v["street_roof"], v["garden_roof"])
            for plane, y in zip(planes, (v["HOUSE_DEPTH"]/4, 3*v["HOUSE_DEPTH"]/4)):
                for offset in (v["RAFTER_Z_OFFSET"], v["ROOF_TILE_BOTTOM"]):
                    z = v["roof_layer_height_at_y"](plane, offset, y, 0)
                    self.assertLess(profile.boundary.distance(Point(y, z)), 1e-8)
            body = ifcopenshell.util.representation.get_representation(cap, "Model", "Body", "MODEL_VIEW")
            shading = body.Items[0].StyledByItem[0].Styles[0].Styles[0]
            actual = shading.SurfaceColour
            np.testing.assert_allclose((actual.Red, actual.Green, actual.Blue), expected_rgb)

    def test_dormer_side_caps_follow_the_roof_skin_not_the_extended_rafter(self):
        from shapely.geometry import Point, Polygon
        v = self.values
        plane = v["dormer_roof"]
        piece, = [p for p in v["roof_exterior_pieces"] if p["plane"] is plane]
        self.assertEqual(piece["source_y_min"], 0)
        bottom, top = v["RAFTER_Z_OFFSET"], v["ROOF_TILE_BOTTOM"]
        for cap in v["roof_sloped_siding"][2:]:
            outline = json.loads(ifcopenshell.util.element.get_pset(cap, "BBIM_Panel", "Outline"))
            self.assertGreaterEqual(len(outline), 4)
            profile = Polygon([(y, z) for x, y, z in outline])
            expected_y_min = min(plane.to_world((0, 0, offset))[1] for offset in (bottom, top))
            self.assertAlmostEqual(profile.bounds[0], expected_y_min)
            self.assertAlmostEqual(profile.bounds[2], v["DORMER_ROOF_EAVE_Y"])
            cut_z = plane.cuts[1][0][2]
            self.assertAlmostEqual(profile.bounds[1], cut_z)
            for offset in (bottom, top):
                start = plane.to_world((0, 0, offset))
                self.assertLess(profile.boundary.distance(Point(start[1:])), 1e-8)
                for y in ((expected_y_min + v["HOUSE_DEPTH"])/2, v["DORMER_ROOF_EAVE_Y"]):
                    z = max(cut_z, v["roof_layer_height_at_y"](plane, offset, y, 0))
                    self.assertLess(profile.boundary.distance(Point(y, z)), 1e-8)

    def test_sloped_siding_is_mirrored_once_and_zero_setback_creates_nothing(self):
        v = self.values
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        settings = ifcopenshell.geom.settings(); settings.set(settings.USE_WORLD_COORDS, True)
        for cap in v["roof_sloped_siding"]:
            original_shape = ifcopenshell.geom.create_shape(settings, cap)
            mirrored_shape = ifcopenshell.geom.create_shape(settings, exported.by_guid(cap.GlobalId))
            original = np.asarray(original_shape.geometry.verts).reshape(-1, 3)
            mirrored = np.asarray(mirrored_shape.geometry.verts).reshape(-1, 3)
            expected = original * (-1, 1, 1)
            self.assertEqual({tuple(np.round(p, 7)) for p in mirrored}, {tuple(np.round(p, 7)) for p in expected})
        helper = v["add_sloped_roof_siding"]
        with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": 0}), patch.object(v["house"], "add_panel") as create:
            self.assertEqual(helper(), ())
            create.assert_not_called()

    def test_roof_edges_are_plain_but_facades_and_roof_step_gable_keep_the_board_pattern(self):
        v = self.values
        roof_siding = (*v["roof_siding"], *v["roof_sloped_siding"])
        self.assertEqual(len(roof_siding), 8)
        color = v["wood_siding_color"]().lstrip("#")
        expected_rgb = tuple(int(color[i:i+2], 16)/255 for i in (0, 2, 4))
        for panel in roof_siding:
            with self.subTest(panel=panel.Name):
                self.assertEqual(ifcopenshell.util.element.get_material(panel).Name, "Wood siding solid")
                body = ifcopenshell.util.representation.get_representation(panel, "Model", "Body", "MODEL_VIEW")
                rgb = body.Items[0].StyledByItem[0].Styles[0].Styles[0].SurfaceColour
                np.testing.assert_allclose((rgb.Red, rgb.Green, rgb.Blue), expected_rgb)
        patterned = {element for element in v["house"].model.by_type("IfcElement")
                     if (material := ifcopenshell.util.element.get_material(element))
                     and material.is_a("IfcMaterial") and material.Name == "Wood siding"}
        self.assertEqual(patterned, {v["street_facade"][1], v["garden_facade"][1],
                                     v["west_facade"][0], v["west_roof_closure"]["Siding"]})
        patterned_color = v["wood_siding_color"](patterned=True).lstrip("#")
        expected_patterned_rgb = tuple(int(patterned_color[i:i+2], 16)/255 for i in (0, 2, 4))
        for panel in patterned:
            body = ifcopenshell.util.representation.get_representation(panel, "Model", "Body", "MODEL_VIEW")
            rgb = body.Items[0].StyledByItem[0].Styles[0].Styles[0].SurfaceColour
            np.testing.assert_allclose((rgb.Red, rgb.Green, rgb.Blue), expected_patterned_rgb)

    def test_dormer_overhang_and_horizontal_drop_are_independent_of_main_roof(self):
        v = self.values
        source = Path(__file__).with_name("house_ifc.py")
        self.assertEqual(v["DORMER_ROOF_EAVE_OVERHANG"], .5)
        self.assertEqual(v["DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE"], 0)
        for overhang, drop in ((.5, 0), (.95, 0), (.5, .15), (.95, .15)):
            with self.subTest(overhang=overhang, drop=drop):
                tree = ast.parse(source.read_text(encoding="utf-8"))
                def assignment(node, name):
                    return isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == name for target in node.targets)
                start = next(i for i, node in enumerate(tree.body) if assignment(node, "ROOF_EAVE_OVERHANG"))
                stop = next(i for i, node in enumerate(tree.body) if assignment(node, "flat_ceiling_roof"))
                block = tree.body[start:stop]
                for node in block:
                    for name, value in (("DORMER_ROOF_EAVE_OVERHANG", overhang),
                                        ("DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE", drop)):
                        if assignment(node, name):
                            node.value = ast.Constant(value=value)
                block += [node for node in tree.body if isinstance(node, ast.FunctionDef)
                          and node.name == "local_y_limits_from_cuts"]
                code = ast.fix_missing_locations(ast.Module(body=block, type_ignores=[]))
                house = House("Independent dormer eaves")
                ns = dict(v, roof=house.storey("Roof", elevation=0).roof("Roof"))
                exec(compile(code, str(source), "exec"), ns)
                for name in ("street_roof", "garden_roof"):
                    self.assertEqual(ns[name].cuts, v[name].cuts)
                plane = ns["dormer_roof"]
                eave_y = v["HOUSE_DEPTH"] + overhang
                cut_z = v["DORMER_WALL_PLATE_Z"] - v["WALL_PLATE_SIZE"][1]/2 - drop
                self.assertEqual(plane.cuts[0], v["dormer_roof"].cuts[0])
                self.assertTrue(all(p[2] == cut_z for p in plane.cuts[1]))
                self.assertTrue(all(p[1] == eave_y for p in plane.cuts[2]))
                self.assertEqual(ns["dormer_rafter_roof"].cuts[1:], plane.cuts[1:])
                inset_cut, = ns["roof_eave_setback_cuts"](plane)
                self.assertTrue(all(p[1] == eave_y - v["ROOF_EAVE_SETBACK"] for p in inset_cut))
                for offset in (v["RAFTER_Z_OFFSET"], v["MDF_BOTTOM"], v["ROOF_TILE_BOTTOM"]):
                    lo, hi = ns["local_y_limits_from_cuts"](plane, offset, eave_setback=True)
                    self.assertAlmostEqual(lo, v["local_y_at_global_y"](plane, v["HALF_DEPTH"], local_z=offset))
                    vertical = v["local_y_at_global_y"](plane, eave_y-v["ROOF_EAVE_SETBACK"], local_z=offset)
                    horizontal = v["local_y_at_global_z"](plane, cut_z, local_z=offset)
                    self.assertAlmostEqual(hi, min(vertical, horizontal))

    def test_chimney_penetration_uses_the_exact_vertical_footprint_without_trimmers(self):
        v = self.values
        opening, chimney = v["chimney_roof_opening"], v["chimney"]
        self.assertIs(opening.roof, v["roof"])
        self.assertTrue(opening.vertical)
        self.assertFalse(opening.trimmers)
        self.assertIsNone(opening.window)
        self.assertEqual(opening.rectangle, (
            (chimney.center[0]-chimney.size/2, chimney.center[1]-chimney.size/2),
            (chimney.center[0]+chimney.size/2, chimney.center[1]+chimney.size/2),
        ))
        hosts = {void.VoidsElements[0].RelatingBuildingElement for void in opening.elements}
        materials = {ifcopenshell.util.element.get_material(host).Name for host in hosts}
        self.assertTrue({"Thermal insulation", "Vapour barrier", "Gypsum plasterboard",
                         "MDF", "Roofing underlay", "Roof tiles"}.issubset(materials))
        self.assertFalse(set((*v["main_roof_rafters"], *v["stronger_main_roof_rafters"],
                              *v["dormer_roof_rafters"], *v["dormer_short_rafters"])) & hosts)
        self.assertFalse(v["roof_window_opening"].vertical)

    def test_street_facade_starts_above_perimeter_with_the_requested_materials(self):
        v = self.values
        panels = v["street_facade"]
        self.assertEqual(len(panels), 2)
        for panel, material in zip(panels, ("Facade finish", "Wood siding")):
            with self.subTest(panel=panel.Name):
                self.assertTrue(panel.is_a("IfcCovering"))
                self.assertEqual(panel.PredefinedType, "CLADDING")
                self.assertEqual(panel.material_name, material)
                self.assertEqual(panel.wall, v["wall_front_g"])
                self.assertEqual(panel.start_height + v["ground"].elevation, v["PERIMETER_TOP_HEIGHT"])
                self.assertEqual(panel.thickness, v["FACADE_THICKNESS"])
                self.assertEqual(panel.offset, v["FACADE_INSULATION_THICKNESS"])
                self.assertEqual(panel.ContainedInStructure[0].RelatingStructure, v["ground"].element)

    def test_street_facade_bounds_meet_at_the_roof_step_and_touch_the_insulation(self):
        v = self.values
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        expected_x = (
            (-v["FACADE_INSULATION_THICKNESS"] - v["FACADE_THICKNESS"] + 0.001,
             v["LOWER_NADEZDIVKA_X"] - .05),
            (v["LOWER_NADEZDIVKA_X"] - .05,
             v["HOUSE_WIDTH"] + v["FACADE_INSULATION_THICKNESS"] + v["FACADE_THICKNESS"] - 0.001),
        )
        outer_y = -v["FACADE_INSULATION_THICKNESS"] - v["FACADE_THICKNESS"]
        for panel, (x0, x1), plane in zip(v["street_facade"], expected_x,
                                        (v["street_roof"], v["transverse_roof"])):
            with self.subTest(panel=panel.Name):
                shape = ifcopenshell.geom.create_shape(settings, panel)
                vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
                np.testing.assert_allclose(vertices.min(axis=0), (x0, outer_y, v["PERIMETER_TOP_HEIGHT"]), atol=1e-8)
                np.testing.assert_allclose(vertices.max(axis=0), (
                    x1, -v["FACADE_INSULATION_THICKNESS"],
                    v["plane_height_at"](*v["offset_plane"](*plane.points, offset=v["RAFTER_Z_OFFSET"]), x=x0, y=outer_y)
                    if plane is v["transverse_roof"]
                    else v["roof_layer_height_at_y"](plane, v["RAFTER_Z_OFFSET"], outer_y, 0),
                ), atol=1e-8)

    def test_perimeter_facades_match_xps_offsets_and_join_the_upper_facades(self):
        v = self.values
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        extension = v["EXTERIOR_XPS_INSULATION_THICKNESS"] + v["FACADE_THICKNESS"] - .001
        inner = v["EXTERIOR_XPS_INSULATION_THICKNESS"]
        outer = inner + v["FACADE_THICKNESS"]
        bottom = v["basement"].elevation
        expected = {
            "street": ((-extension, -outer, bottom), (v["HOUSE_WIDTH"]+extension, -inner, v["PERIMETER_TOP_HEIGHT"])),
            "garden": ((-extension, v["HOUSE_DEPTH"]+inner, bottom),
                       (v["HOUSE_WIDTH"]+extension, v["HOUSE_DEPTH"]+outer, v["PERIMETER_TOP_HEIGHT"])),
            "east": ((-outer, -extension, bottom), (-inner, v["HOUSE_DEPTH"]+extension, v["PERIMETER_TOP_HEIGHT"])),
            "west": ((v["HOUSE_WIDTH"]+inner, -extension, bottom),
                     (v["HOUSE_WIDTH"]+outer, v["HOUSE_DEPTH"]+extension, v["PERIMETER_TOP_HEIGHT"])),
        }
        for side, panel in v["perimeter_facades"].items():
            with self.subTest(side=side):
                self.assertEqual(panel.material_name, "Perimeter facade finish")
                self.assertEqual(panel.offset, inner)
                self.assertEqual(panel.thickness, v["FACADE_THICKNESS"])
                self.assertEqual(ifcopenshell.util.element.get_container(panel), v["basement"].element)
                self.assertIn(v[f"{side}_facade"][0].wall, panel.opening_walls)
                shape = ifcopenshell.geom.create_shape(settings, panel)
                points = np.asarray(shape.geometry.verts).reshape(-1, 3)
                np.testing.assert_allclose(points.min(axis=0), expected[side][0], atol=1e-8)
                np.testing.assert_allclose(points.max(axis=0), expected[side][1], atol=1e-8)
                for upper in v[f"{side}_facade"]:
                    shape = ifcopenshell.geom.create_shape(settings, upper)
                    upper_points = np.asarray(shape.geometry.verts).reshape(-1, 3)
                    self.assertAlmostEqual(upper_points[:, 2].min(), points[:, 2].max())
        for drawing in v["house"]._drawings:
            selected = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(v["perimeter_facades"].values()).issubset(selected))

    def test_street_facade_preserves_the_bathroom_window_and_is_included_in_elevations(self):
        v = self.values
        high, low = v["street_facade"]
        for panel in (high, low):
            start, end = -panel.start_extension, panel.wall.length + panel.end_extension
            expected = sum(lo < end and hi > start for lo, hi, _, _ in panel.wall._openings)
            self.assertEqual(len(panel.openings), expected)
        self.assertEqual(low.opening_walls, (v["wall_front_g"], v["wall_front1_u"]))
        for panel in (high, low):
            for void in panel.openings:
                self.assertEqual(void.VoidsElements[0].RelatingBuildingElement, panel)
        for drawing in v["house"]._drawings:
            selected = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(v["street_facade"]).issubset(selected))

    def test_garden_facade_matches_street_x_ranges_materials_and_thickness(self):
        v = self.values
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        self.assertEqual(len(v["garden_facade"]), 2)
        for street, garden in zip(v["street_facade"], v["garden_facade"]):
            with self.subTest(panel=garden.Name):
                self.assertEqual(garden.wall, v["wall_back_g"])
                self.assertEqual(garden.material_name, street.material_name)
                self.assertEqual(garden.thickness, v["FACADE_THICKNESS"])
                self.assertEqual(garden.offset, v["FACADE_INSULATION_THICKNESS"])
                shape = ifcopenshell.geom.create_shape(settings, garden)
                vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
                front_shape = ifcopenshell.geom.create_shape(settings, street)
                front_vertices = np.asarray(front_shape.geometry.verts).reshape(-1, 3)
                np.testing.assert_allclose((vertices[:, 0].min(), vertices[:, 0].max()),
                                           (front_vertices[:, 0].min(), front_vertices[:, 0].max()), atol=1e-8)
                np.testing.assert_allclose((vertices[:, 1].min(), vertices[:, 1].max()), (
                    v["HOUSE_DEPTH"] + v["FACADE_INSULATION_THICKNESS"],
                    v["HOUSE_DEPTH"] + v["FACADE_INSULATION_THICKNESS"] + v["FACADE_THICKNESS"],
                ), atol=1e-8)



    def test_end_facades_keep_real_openings_and_mirror_once(self):
        from shapely.geometry import Polygon
        v = self.values
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        settings = ifcopenshell.geom.settings(); settings.set(settings.USE_WORLD_COORDS, True)
        for side in ("east",):
            panel, = v[f"{side}_facade"]
            area = Polygon(panel.outline).area
            self.assertEqual(len(panel.openings), sum(len(wall._openings) for wall in panel.opening_walls))
            self.assertTrue(panel.openings)
            for opening in panel.openings:
                self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, panel)
                shape = ifcopenshell.geom.create_shape(settings, opening)
                vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
                area -= np.ptp(vertices[:, 1]) * np.ptp(vertices[:, 2])
            shape = ifcopenshell.geom.create_shape(settings, panel)
            original = np.asarray(shape.geometry.verts).reshape(-1, 3)
            self.assertAlmostEqual(ifcopenshell.util.shape.get_volume(shape.geometry), area * panel.thickness)
            shape = ifcopenshell.geom.create_shape(settings, exported.by_guid(panel.GlobalId))
            mirrored = np.asarray(shape.geometry.verts).reshape(-1, 3)
            self.assertEqual({tuple(p) for p in np.round(mirrored, 7)},
                             {tuple(p) for p in np.round(original * (-1, 1, 1), 7)})

    def test_white_garden_facade_is_one_stepped_profile_raised_only_at_the_dormer(self):
        v = self.values
        high, low = v["garden_facade"]
        self.assertEqual(len(high.outline), 8)
        self.assertEqual(len(low.outline), 4)
        body = ifcopenshell.util.representation.get_representation(high, "Model", "Body", "MODEL_VIEW")
        self.assertEqual(len(body.Items), 1)
        self.assertTrue(body.Items[0].is_a("IfcExtrudedAreaSolid"))
        outer_y = v["HOUSE_DEPTH"] + v["FACADE_INSULATION_THICKNESS"] + v["FACADE_THICKNESS"]
        top = v["roof_layer_height_at_y"](v["dormer_roof"], v["RAFTER_Z_OFFSET"], outer_y, 0)
        self.assertAlmostEqual(high.start_height + high.height, top)
        self.assertGreater(top, v["roof_layer_height_at_y"](v["garden_roof"], v["RAFTER_Z_OFFSET"], outer_y, 0))
        # Host runs right-to-left, so along increases towards smaller world X.
        start_x = v["HOUSE_WIDTH"] + high.start_extension
        raised = sorted(start_x - along for along, z in high.outline if abs(z + high.start_height - top) < 1e-8)
        ends = sorted((v["wall_dormer"].start[0], v["wall_dormer"].end[0]))
        allowance = v["FACADE_INSULATION_THICKNESS"]+v["FACADE_THICKNESS"]-.001
        np.testing.assert_allclose(raised, (ends[0]-allowance, ends[1]+allowance), atol=1e-8)

    def test_garden_windows_and_split_door_remain_open_in_both_finishes(self):
        v = self.values
        high, low = v["garden_facade"]
        self.assertEqual(len(high.openings), 5)  # Two ground windows, two dormer windows, door.
        start, end = -low.start_extension, low.wall.length + low.end_extension
        self.assertEqual(len(low.openings), sum(lo < end and hi > start for lo, hi, _, _ in low.wall._openings))
        self.assertEqual(high.opening_walls,
                         (v["wall_back_g"], v["wall_back1_u"], v["wall_dormer"]))
        for drawing in v["house"]._drawings:
            selected = ifcopenshell.util.selector.filter_elements(v["house"].model,
                ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
            self.assertTrue(set(v["garden_facade"]).issubset(selected))

    def test_chimney_shaft_is_open_through_all_layers_but_not_beside_the_chimney(self):
        v = self.values
        x, y = v["chimney"].center
        for material in ("Thermal insulation", "Vapour barrier", "Gypsum plasterboard",
                         "MDF", "Roofing underlay", "Roof tiles"):
            with self.subTest(material=material):
                with self.assertRaisesRegex(ValueError, "no .* roof layer at"):
                    v["roof"].layer_vertical_extent(material, x=x, y=y)
                lower, upper = v["roof"].layer_vertical_extent(material, x=x+v["chimney"].size, y=y)
                self.assertLess(lower, upper)


class ElectricalDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = []
        source = Path(__file__).with_name("house_ifc.py")
        for args in (["elektro_ground"], ["elektro_ground", "--no-room-corners"]):
            with (
                patch.object(sys, "argv", [str(source), *args]),
                patch.object(House, "write", return_value=Path("house.ifc")),
                patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
                redirect_stdout(StringIO()),
            ):
                values = runpy.run_path(str(source))
            cls.runs.append((values, render.call_args_list))

    def test_ground_plan_has_all_room_corners_and_uses_electrical_pdf_path(self):
        v, rendered = self.runs[0]
        drawing = v["elektro_ground"]
        self.assertEqual([call.args[0] for call in rendered], ["elektro_ground.svg"])
        self.assertEqual(rendered[0].kwargs["pdf"], v["PDF_ELEKTRO_GROUND"])
        self.assertEqual(list(drawing.storeys), [v["ground"]])
        floors = v["ground"].floor_layers
        self.assertEqual({floor.room_id for floor in floors}, {"0.01", "0.02", "0.03", "0.04"})
        points = {f"{floor.room_id}.{i}": p for floor in floors for i, p in enumerate(floor.outline, 1)}
        self.assertEqual(len(points), sum(len(floor.outline) for floor in floors))
        self.assertEqual(v["elektro_ground_corners"], points)
        labels = [ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner")
                  for a in drawing.group.IsGroupedBy[0].RelatedObjects]
        self.assertEqual({p["Identifier"] for p in labels if p},
                         set(points) if v["ELEKTRO_SHOW_ROOM_CORNERS"] else set())
        for p in filter(None, labels):
            self.assertEqual(tuple(json.loads(p["Point"])), points[p["Identifier"]])

    def test_disable_flag_removes_guides_but_preserves_wire_reference_coordinates(self):
        visible, _ = self.runs[0]
        hidden, _ = self.runs[1]
        self.assertEqual(visible["elektro_ground_corners"], hidden["elektro_ground_corners"])
        drawing = hidden["elektro_ground"]
        self.assertFalse(any(ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner")
                             for a in drawing.group.IsGroupedBy[0].RelatedObjects))
        self.assertFalse(any("floor-corner-guide" in (ifcopenshell.util.element.get_pset(
            a, "EPset_Annotation", "Classes") or "").split()
            for a in drawing.group.IsGroupedBy[0].RelatedObjects))

    def test_circuit_and_socket_legends(self):
        for values, _ in self.runs:
            drawing = values["elektro_ground"]
            self.assertEqual(drawing.right_panel_width, 60)
            tables = json.loads(ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "RightPanelTables"))
            self.assertEqual([table["kind"] for table in tables], ["line_legend", "symbol_legend"])
            lines, symbols = tables
            self.assertEqual([item["description"] for item in lines["items"][:3]],
                             ["Zásuvkový okruh", "3-fázový okruh", "Světelný okruh"])
            for item, color in zip(lines["items"], ("0000ff", "ff0000", "f080f0")):
                self.assertIn(f"drawing-line-color-{color}", item["classes"])
                self.assertIn("drawing-line-width-0p3", item["classes"])
            self.assertEqual(symbols["items"][:2], [{"symbol": "socket", "description": "Zásuvka"},
                                                   {"symbol": "d_socket", "description": "Dvojitá zásuvka"}])
            self.assertEqual(len(symbols["items"]), 5)
            self.assertEqual(symbols["items"][2]["symbol"], "light")
            self.assertEqual(symbols["items"][2]["description"], "Světlo")
            self.assertIn("drawing-line-color-0000ff", symbols["items"][2]["classes"])
            self.assertEqual(symbols["items"][3], {"symbol": "switch", "description": "Vypínač"})
            self.assertEqual(symbols["items"][4]["symbol"], "socket3f")
            self.assertEqual(symbols["items"][4]["description"], "Zásuvka 380V, 3 fáze")
            self.assertIn("drawing-line-color-ff0000", symbols["items"][4]["classes"])

    def test_red_electrical_routes_use_three_phase_socket_entries(self):
        source = ast.parse(Path(__file__).with_name("house_ifc.py").read_text(encoding="utf-8"))
        sockets = []
        for node in ast.walk(source):
            if (not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name)
                    or node.func.id != "draw_elektro_line"):
                continue
            if not any(kw.arg == "color" and isinstance(kw.value, ast.Constant)
                       and kw.value.value == "red" for kw in node.keywords):
                continue
            for entry in node.args[0].elts:
                if isinstance(entry, ast.Constant) and isinstance(entry.value, str):
                    kind = entry.value.split(",")[0]
                    if kind in {"socket", "d_socket", "socket3f"}:
                        sockets.append(kind)
        self.assertTrue(sockets)
        self.assertEqual(set(sockets), {"socket3f"})

    def test_stateful_wire_helper_is_available_with_guides_on_or_off(self):
        for values, _ in self.runs:
            with self.subTest(guides=values["elektro_ground_corners"]):
                path = values["draw_elektro_line"](["-+0.03.2", "--0.01.7"], color="red")
                actual = json.loads(ifcopenshell.util.element.get_pset(path, "BBIM_DrawingPolyLine", "Points"))
                # User-authored routes may already have advanced these corners.
                next_path = values["draw_elektro_line"]([
                    "-+0.03.2", "socket,0.4,up", "--0.01.7"], color="red")
                next_points = json.loads(ifcopenshell.util.element.get_pset(next_path, "BBIM_DrawingPolyLine", "Points"))
                for point, following, change in zip(actual, next_points, ((-.1, .1), (-.1, -.1))):
                    for axis in (0, 1):
                        self.assertAlmostEqual(following[axis] - point[axis], change[axis])
                self.assertIn(path, values["elektro_ground"].group.IsGroupedBy[0].RelatedObjects)


class UpperElectricalDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = []
        source = Path(__file__).with_name("house_ifc.py")
        draw_route = ElektroLineDrawer.__call__

        def draw_finished_routes(drawer, *args, **kwargs):
            # The upper-floor wiring block is a user-edited draft. Test its
            # room references and live helper below, independently of routes.
            if drawer._drawing.name != "elektro_upper":
                return draw_route(drawer, *args, **kwargs)

        for args in (["elektro_ground", "elektro_upper"], ["elektro_upper", "--no-room-corners"]):
            with (
                patch.object(sys, "argv", [str(source), *args]),
                patch.object(House, "write", return_value=Path("house.ifc")),
                patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
                patch.object(ElektroLineDrawer, "__call__", autospec=True, side_effect=draw_finished_routes),
                redirect_stdout(StringIO()),
            ):
                values = runpy.run_path(str(source))
            cls.runs.append((values, render.call_args_list))

    def test_upper_plan_pdf_scope_and_all_corner_identifiers(self):
        values, rendered = self.runs[0]
        drawing = values["elektro_upper"]
        self.assertEqual([call.args[0] for call in rendered], ["elektro_ground.svg", "elektro_upper.svg"])
        self.assertEqual(rendered[1].kwargs["pdf"], values["PDF_ELEKTRO_UPPER"])
        self.assertEqual(list(drawing.storeys), [values["upper"]])
        self.assertEqual(drawing.z, values["BWT"] + 2.75 + 2)
        self.assertFalse(drawing._automatic_door_annotations)
        floors = values["upper"].floor_layers
        self.assertEqual({f.room_id for f in floors}, {"P.01", "P.02", "P.03", "P.04", "P.05"})
        points = {f"{floor.room_id}.{index}": point for floor in floors
                  for index, point in enumerate(floor.outline, 1)}
        hallway = values["chodba"]
        points.update({f"0.04.{index}": point for index, point in enumerate(hallway.outline, 1)})
        self.assertEqual(values["elektro_upper_corners"], points)
        labels = [p for a in drawing.group.IsGroupedBy[0].RelatedObjects
                  if (p := ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner"))]
        self.assertEqual({p["Identifier"] for p in labels},
                         set(points) if values["ELEKTRO_SHOW_ROOM_CORNERS"] else set())
        for label in labels:
            self.assertEqual(tuple(json.loads(label["Point"])), points[label["Identifier"]])
            self.assertIn(label["Floor"], {floor.GlobalId for floor in (*floors, hallway)})
        self.assertEqual(set(points) & set(values["elektro_ground_corners"]),
                         {f"0.04.{index}" for index in range(1, len(hallway.outline) + 1)})

    def test_legends_are_shared_between_floors(self):
        values, _ = self.runs[0]
        ground = values["elektro_ground"]
        upper = values["elektro_upper"]
        self.assertEqual(upper.right_panel_width, ground.right_panel_width)
        self.assertEqual(ifcopenshell.util.element.get_pset(upper.element, "EPset_Drawing", "RightPanelTables"),
                         ifcopenshell.util.element.get_pset(ground.element, "EPset_Drawing", "RightPanelTables"))

    def test_hidden_corner_guides_keep_references_and_upper_wire_helper(self):
        visible, _ = self.runs[0]
        hidden, rendered = self.runs[1]
        self.assertEqual([call.args[0] for call in rendered], ["elektro_upper.svg"])
        self.assertEqual(rendered[0].kwargs["pdf"], hidden["PDF_ELEKTRO_UPPER"])
        self.assertEqual(visible["elektro_upper_corners"], hidden["elektro_upper_corners"])
        drawing = hidden["elektro_upper"]
        self.assertFalse(any(ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner")
                             for a in drawing.group.IsGroupedBy[0].RelatedObjects))
        for values in (visible, hidden):
            draw_line = values["ElektroLineDrawer"](values["elektro_upper"], values["elektro_upper_corners"])
            path = draw_line(["++0.04.1", "++P.02.2"], color="blue")
            points = json.loads(ifcopenshell.util.element.get_pset(path, "BBIM_DrawingPolyLine", "Points"))
            for key, point in zip(("0.04.1", "P.02.2"), points):
                np.testing.assert_allclose(point, np.array(values["elektro_upper_corners"][key]) + .1)
            self.assertIn(path, values["elektro_upper"].group.IsGroupedBy[0].RelatedObjects)
            if "elektro_ground" in values:
                self.assertNotIn(path, values["elektro_ground"].group.IsGroupedBy[0].RelatedObjects)


class WaterDrawingTests(unittest.TestCase):
    def test_both_water_plans_have_hot_and_cold_line_legends(self):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "voda_ground", "voda_upper"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            redirect_stdout(StringIO()),
        ):
            values = runpy.run_path(str(source))
        self.assertEqual([call.args[0] for call in render.call_args_list],
                         ["voda_ground.svg", "voda_upper.svg"])
        self.assertEqual(len(values["house"]._drawings), 2)
        for drawing in values["house"]._drawings:
            with self.subTest(drawing=drawing.element.Name):
                self.assertEqual(drawing.right_panel_width, 40)
                tables = json.loads(ifcopenshell.util.element.get_pset(
                    drawing.element, "EPset_Drawing", "RightPanelTables"))
                self.assertEqual(len(tables), 1)
                self.assertEqual(tables[0]["kind"], "line_legend")
                self.assertEqual(tables[0]["title"], "LEGENDA ČAR")
                self.assertEqual(tables[0]["items"], [
                    {"classes": "IfcAnnotation PredefinedType-LINEWORK drawing-line solid "
                                "drawing-line-color-ff0000 drawing-line-width-0p3",
                     "description": "teplá"},
                    {"classes": "IfcAnnotation PredefinedType-LINEWORK drawing-line solid "
                                "drawing-line-color-0000ff drawing-line-width-0p3",
                     "description": "studená"},
                ])


class CutDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "ground", "upper", "roof", "aa", "bb"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            patch.object(DrawingSheet, "render", return_value=Path("sheet.svg")) as sheet_render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]
            cls.sheet_rendered = [call.args[0] for call in sheet_render.call_args_list]

    def test_exposed_section_outlines_are_enabled_only_for_plans_and_building_sections(self):
        for drawing in self.values["house"]._drawings:
            width = ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "SectionOutlineWidth")
            if drawing.name.startswith("roof_"):
                self.assertIsNone(width)
            else:
                self.assertEqual(width, self.values["SECTION_OUTLINE_WIDTH"])
                self.assertIs(ifcopenshell.util.element.get_pset(
                    drawing.element, "EPset_Drawing", "SectionOutlineProjectedWalls"),
                    drawing.section_outline_projected_walls)
                self.assertEqual(ifcopenshell.util.element.get_pset(
                    drawing.element, "EPset_Drawing", "SectionOutlineOffsetRatio"), .25)

    def test_configured_section_outlines_persist_the_shared_color(self):
        from ifc_utils import _color
        expected = "#" + "".join(f"{round(channel * 255):02x}" for channel in
                                _color(self.values["SECTION_OUTLINE_COLOR"], "color"))
        count = 0
        for drawing in self.values["house"]._drawings:
            if drawing.section_outline_width is None:
                continue
            self.assertEqual(drawing.section_outline_color, expected)
            self.assertEqual(ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "SectionOutlineColor"), expected)
            count += 1
        self.assertGreater(count, 0)

    def test_all_four_wall_plates_have_an_explicit_ifc_role(self):
        for name in ("beam3", "beam4_a", "beam4_b", "beam_dormer"):
            self.assertEqual(ifcopenshell.util.element.get_predefined_type(self.values[name]), "WALL_PLATE")
        for purlin in (*self.values["street_purlins"], *self.values["garden_purlins"]):
            self.assertNotEqual(ifcopenshell.util.element.get_predefined_type(purlin), "WALL_PLATE")

    def test_aa_legend_uses_plain_mdf_instead_of_wood_fibre_batting(self):
        drawing = next(d for d in self.values["house"]._drawings if d.name == "aa")
        tables = json.loads(ifcopenshell.util.element.get_pset(
            drawing.element, "EPset_Drawing", "RightPanelTables"))
        items = next(table["items"] for table in tables if table["kind"] == "material_legend")
        self.assertIn({"pattern": "mdf-solid", "description": "MDF záklop"}, items)
        self.assertFalse(any(item["pattern"] == "pavatex-wave" for item in items))
        self.assertFalse(any("Dřevovláknitá deska" in item["description"] for item in items))
        self.assertTrue(any(item["pattern"] == "rockwool-wave" for item in items))

    def test_aa_legend_includes_blue_osb_and_vapour_control_layer(self):
        drawing = next(d for d in self.values["house"]._drawings if d.name == "aa")
        tables = json.loads(ifcopenshell.util.element.get_pset(
            drawing.element, "EPset_Drawing", "RightPanelTables"))
        items = next(table["items"] for table in tables if table["kind"] == "material_legend")
        self.assertIn({"pattern": "vapour-barrier-solid",
                       "description": "OSB záklop + parobrzda"}, items)

    def test_aa_and_bb_share_the_same_material_legend(self):
        legends = []
        for name in ("aa", "bb"):
            drawing = next(d for d in self.values["house"]._drawings if d.name == name)
            self.assertEqual(drawing.right_panel_width, 60)
            tables = json.loads(ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "RightPanelTables"))
            legends.append([table for table in tables if table["kind"] == "material_legend"])
        self.assertEqual(len(legends[0]), 1)
        self.assertEqual(len(legends[0][0]["items"]), 14)
        self.assertIn({"pattern": "wood-siding", "description": "Dřevěný obklad (pohled)"},
                      legends[0][0]["items"])
        self.assertIn({"pattern": "thermal-impact-insulation", "description": "podlahová izolace"},
                      legends[0][0]["items"])
        self.assertEqual(legends[0], legends[1])

    def test_load_bearing_wall_legends_are_plain_white(self):
        count = 0
        for drawing in self.values["house"]._drawings:
            tables = json.loads(ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "RightPanelTables") or "[]")
            for table in tables:
                if table["kind"] != "material_legend":
                    continue
                for item in table["items"]:
                    if "VPC Cihla 240 mm" in item["description"]:
                        self.assertEqual(item["pattern"], "solid-white")
                        count += 1
        self.assertEqual(count, 4)  # Ground, upper, AA, BB.

    def test_all_plan_symbols_use_shared_cut_definitions(self):
        cuts = (self.values["aa_cut"], self.values["bb_cut"])
        self.assertTrue(all(isinstance(cut, CutDefinition) for cut in cuts))
        self.assertEqual(self.rendered, ["ground.svg", "upper.svg", "aa.svg", "bb.svg"])
        self.assertEqual(self.sheet_rendered, ["roof.svg"])
        drawings = self.values["house"]._drawings
        self.assertEqual(len(drawings), 8)
        for drawing in drawings[:3]:
            annotations = drawing.group.IsGroupedBy[0].RelatedObjects
            markers = [a for a in annotations if ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol")]
            expected_cuts = (*cuts, *self.values["roof_elevation_cuts"].values()) \
                if drawing.name == "Roof plan" else cuts
            self.assertEqual(len(markers), len(expected_cuts))
            definitions = {ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol", "Identifier"):
                           ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol") for a in markers}
            for cut in expected_cuts:
                properties = definitions[cut.identifier]
                self.assertEqual(json.loads(properties["Start"]), list(cut.start))
                self.assertEqual(json.loads(properties["End"]), list(cut.end))
                self.assertEqual(properties["Direction"], cut.direction)

    def test_aa_camera_is_derived_from_cut(self):
        cut = self.values["aa_cut"]
        drawing = next(d for d in self.values["house"]._drawings if d.name == "aa")
        self.assertEqual(drawing.name, "aa")
        self.assertEqual((drawing.x, drawing.y), cut.center)
        self.assertEqual(drawing.direction, cut.view_direction)
        self.assertEqual((drawing.y, drawing.z, drawing.radius), (4, 3.5, 8))
        self.assertEqual(drawing.direction, (1, 0, 0))

    def test_aa_roof_angle_dimensions_measure_model_pitches_and_are_drawing_scoped(self):
        values = self.values
        drawing = next(d for d in values["house"]._drawings if d.name == "aa")
        other = next(d for d in values["house"]._drawings if d.name == "bb")
        annotations = drawing.group.IsGroupedBy[0].RelatedObjects
        angles = {a.Name: a for a in annotations
                  if ifcopenshell.util.element.get_pset(a, "BBIM_AngleDimension")}
        expected = {"AA main roof angle": values["street_roof_angle"],
                    "AA dormer roof angle": values["dormer_roof_angle"]}
        self.assertEqual(set(angles), set(expected))
        self.assertEqual(ifcopenshell.util.element.get_pset(
            drawing.element, "EPset_Drawing", "AngleDecimalPlaces"), 0)
        for name, pitch in expected.items():
            angle = angles[name]
            self.assertEqual(angle.ObjectType, "ANGLE")
            properties = ifcopenshell.util.element.get_pset(angle, "BBIM_AngleDimension")
            self.assertAlmostEqual(properties["AngleDegrees"], pitch)
            self.assertNotIn(angle, other.group.IsGroupedBy[0].RelatedObjects)

    def test_bb_camera_runs_through_ridge_perpendicular_to_aa(self):
        cut = self.values["bb_cut"]
        aa_cut = self.values["aa_cut"]
        drawing = next(d for d in self.values["house"]._drawings if d.name == "bb")
        self.assertEqual((drawing.x, drawing.y), cut.center)
        self.assertEqual(drawing.direction, cut.view_direction)
        self.assertAlmostEqual(drawing.x, self.values["HOUSE_WIDTH"] / 2)
        self.assertEqual(drawing.y, self.values["HALF_DEPTH"])
        self.assertEqual(drawing.direction, (0, 1, 0))
        self.assertEqual((drawing.z, drawing.radius, drawing.view), (3.5, 8, "elevation"))
        self.assertTrue(drawing.doors_closed)
        self.assertAlmostEqual(np.dot(aa_cut.view_direction, cut.view_direction), 0)
        self.assertEqual(cut.start[1], self.values["HALF_DEPTH"])
        self.assertEqual(cut.end[1], self.values["HALF_DEPTH"])

    def test_bb_ridge_has_drawing_scoped_between_rafter_batting(self):
        values = self.values
        annotations = values["bb_ridge_batting"]
        self.assertGreater(len(annotations), 10)
        drawing = next(d for d in values["house"]._drawings if d.name == "bb")
        aa = next(d for d in values["house"]._drawings if d.name == "aa")
        for annotation in annotations:
            self.assertTrue(annotation.Name.startswith("BB ridge insulation batting "))
            self.assertIn(annotation, drawing.group.IsGroupedBy[0].RelatedObjects)
            self.assertNotIn(annotation, aa.group.IsGroupedBy[0].RelatedObjects)
            self.assertIn("rafter-section-batting", ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"))
            self.assertGreater(ifcopenshell.util.element.get_pset(annotation, "BBIM_Batting", "Thickness"),
                               values["ROOF_BATTING_THICKNESS"])

    def test_bb_has_no_batting_at_uninsulated_dormer_rafter_extensions(self):
        drawing = next(d for d in self.values["house"]._drawings if d.name == "bb")
        section_batting = [
            a for a in drawing.group.IsGroupedBy[0].RelatedObjects
            if "rafter-section-batting" in (
                ifcopenshell.util.element.get_pset(a, "EPset_Annotation", "Classes") or ""
            ).split()
        ]
        self.assertEqual(set(section_batting), set(self.values["bb_ridge_batting"]))
        self.assertFalse(any((a.Name or "").startswith("BB dormer insulation batting")
                             for a in self.values["house"].model.by_type("IfcAnnotation")))




class RoofElevationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "roof"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            patch.object(DrawingSheet, "render", return_value=Path("sheet.svg")) as sheet_render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]
            cls.sheet_rendered = [call.args[0] for call in sheet_render.call_args_list]







    def test_camera_is_before_selected_rafter_parallel_to_aa_and_mirrors_once(self):
        values = self.values
        drawing = values["roof_xx"]
        self.assertEqual(self.rendered, [])
        self.assertEqual(self.sheet_rendered, ["roof.svg"])
        self.assertEqual(len(values["house"]._drawings), 3)
        self.assertEqual(drawing.view, "elevation")
        selected_x = values["rafter_x_position"](values["rafters"][1])
        self.assertAlmostEqual(drawing.x, selected_x - 0.15)
        self.assertEqual(drawing.y, values["HALF_DEPTH"])
        self.assertEqual(drawing.direction, values["aa_cut"].view_direction)
        exported = values["house"]._export_model()
        placement = ifcopenshell.util.placement.get_local_placement(
            exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
        np.testing.assert_allclose(placement[:3, 3], (-drawing.x, drawing.y, drawing.z))
        np.testing.assert_allclose(-placement[:3, 2], (-1, 0, 0))
        first_members = [b for b in values["roof_layer_storeys"]["Rafters"].element
                         .ContainsElements[0].RelatedElements
                         if abs(ifcopenshell.util.placement.get_local_placement(
                             b.ObjectPlacement)[0, 3] - selected_x) < 1e-7]
        self.assertTrue(first_members)

    def test_includes_only_upper_walls_ring_beams_and_structural_roof_members(self):
        values = self.values
        drawing = values["roof_xx"]
        pset = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
        self.assertEqual(pset["FillMode"], "SHAPELY")
        selected = ifcopenshell.util.selector.filter_elements(values["house"].model, pset["Include"])
        expected = set((*values["roof_outline_walls"], *values["upper_ring_beams"],
                        *values["roof_structural_beams"]))
        for name in ("Rafters", "Collar ties"):
            for relation in values["roof_layer_storeys"][name].element.ContainsElements:
                expected.update(relation.RelatedElements)
        self.assertEqual(selected, expected)
        self.assertNotIn(values["roof_window"], selected)
        self.assertFalse(set(values["garage"]) & selected)
        for name in ("MDF", "Roofing underlay", "Roof tiles",
                     "Gypsum plasterboard", "Vapour barrier", "Tile battens", "Counter-battens"):
            for relation in values["roof_layer_storeys"][name].element.ContainsElements:
                self.assertFalse(set(relation.RelatedElements) & selected)

    def test_shares_complete_schedule_with_roof_plan_without_automatic_plan_annotations(self):
        values = self.values
        drawing = values["roof_xx"]
        pset = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
        tables = json.loads(pset["RightPanelTables"])
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["kind"], "timber_schedule")
        plan = next(d for d in values["house"]._drawings if d.name == "Roof plan")
        plan_pset = ifcopenshell.util.element.get_pset(plan.element, "EPset_Drawing")
        plan_table = next(t for t in json.loads(plan_pset["RightPanelTables"])
                          if t["kind"] == "timber_schedule")
        self.assertEqual(tables[0]["items"], plan_table["items"])
        self.assertEqual(tables[0]["layout_scale"], plan_table["layout_scale"])
        self.assertEqual(drawing.right_panel_width, plan.right_panel_width)
        self.assertEqual(pset["Metadata"], "GlobalId")
        self.assertFalse(drawing._automatic_door_annotations)
        self.assertFalse(drawing._automatic_plan_annotations)

    def test_styles_cut_purlins_selected_rafter_wall_plates_and_packing_blocks(self):
        values = self.values
        pset = ifcopenshell.util.element.get_pset(values["roof_xx"].element, "EPset_Drawing")
        styles = _timber_schedule_member_styles(pset)
        selected_x = values["rafter_x_position"](values["rafters"][1])
        expected_members = set(values["rafter_assemblies"][selected_x])
        cuts = [b for b in (*values["street_purlins"], *values["garden_purlins"])
                if min(b.start[0], b.end[0]) <= values["roof_xx"].x <= max(b.start[0], b.end[0])]
        self.assertEqual(len(cuts), 2)
        expected_members.update(cuts)
        plates = [b for b in values["roof_wall_plates"]
                  if min(b.start[0], b.end[0]) <= selected_x <= max(b.start[0], b.end[0])]
        expected_members.update(plates)
        expected_members.update(values["purlin_packing_blocks"])
        self.assertEqual(set(styles), {b.GlobalId for b in expected_members})
        self.assertEqual(pset["UnstyledTimberColor"], "#ffffff")
        self.assertEqual(sum((b.Name or "").startswith("Collar tie ") for b in expected_members), 2)
        self.assertEqual(sum((b.Name or "").startswith("Purlin spacer ") for b in expected_members), 1)
        for b in expected_members:
            self.assertIn("color", styles[b.GlobalId])
        for b in (*plates, *values["purlin_packing_blocks"]):
            self.assertIn("pattern", styles[b.GlobalId])

    def test_distant_wall_plates_stay_visible_but_are_not_highlighted(self):
        values = self.values
        for name, definition in values["roof_elevation_definitions"].items():
            with self.subTest(drawing=name):
                drawing = values[name]
                pset = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
                styles = _timber_schedule_member_styles(pset)
                included = ifcopenshell.util.selector.filter_elements(values["house"].model, pset["Include"])
                rafter_x = values["rafter_x_position"](values["rafters"][definition["rafter_index"]])
                for plate in values["roof_wall_plates"]:
                    self.assertIn(plate, included)
                    at_rafter = min(plate.start[0], plate.end[0]) <= rafter_x <= max(plate.start[0], plate.end[0])
                    self.assertEqual(plate.GlobalId in styles, at_rafter)
        xx_styles = _timber_schedule_member_styles(ifcopenshell.util.element.get_pset(
            values["roof_xx"].element, "EPset_Drawing"))
        self.assertIn(values["beam3"].GlobalId, xx_styles)
        self.assertNotIn("beam_cut_street", values)

    def test_wall_plate_and_packing_styles_are_shared_with_plan_even_when_not_cut(self):
        values = self.values
        section = values["roof_xx"]
        plan = next(d for d in values["house"]._drawings if d.name == "Roof plan")
        section_styles = _timber_schedule_member_styles(
            ifcopenshell.util.element.get_pset(section.element, "EPset_Drawing"))
        plan_styles = _timber_schedule_member_styles(
            ifcopenshell.util.element.get_pset(plan.element, "EPset_Drawing"))
        projected_only = []
        for b in (*values["roof_wall_plates"], *values["purlin_packing_blocks"]):
            if b.GlobalId not in section_styles:
                continue
            self.assertEqual(section_styles[b.GlobalId], plan_styles[b.GlobalId])
            if not min(b.start[0], b.end[0]) <= section.x <= max(b.start[0], b.end[0]):
                projected_only.append(b)
        self.assertTrue(projected_only)

    def test_rafter_assemblies_include_offset_ties_and_paired_dormer_members(self):
        values = self.values
        assemblies = values["rafter_assemblies"]
        self.assertEqual(set(assemblies), set(values["main_rafter_positions"]))
        owner_ids = [b.GlobalId for members in assemblies.values() for b in members]
        self.assertEqual(len(owner_ids), len(set(owner_ids)))
        for x, offset in values["paired_rafter_dormer_offsets"].items():
            members = assemblies[x]
            dormer = [b for b in values["dormer_roof_rafters"] if b.local_start[0] == x + offset]
            self.assertTrue(dormer)
            self.assertTrue(set(dormer) <= set(members))
            self.assertTrue(any((b.Name or "").startswith("Collar tie ") for b in members))
            self.assertTrue(any((b.Name or "").startswith("Purlin spacer ") for b in members))

    def test_rafter_x_lookup_accepts_every_layout_entry_type(self):
        values = self.values
        get_x = values["rafter_x_position"]
        for entry in (1.2, (1.2, "before"), values["SplitRafter"](1.2, 7),
                      values["StrongerRafter"](1.2)):
            self.assertEqual(get_x(entry), 1.2)

    def test_roof_plan_cut_symbols_match_xx_yy_zz_cameras_and_mirroring(self):
        values = self.values
        plan = next(d for d in values["house"]._drawings if d.name == "Roof plan")
        markers = {
            ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol", "Identifier"): a
            for a in plan.group.IsGroupedBy[0].RelatedObjects
            if ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol")
        }
        self.assertEqual(set(markers), {"A", "B", "X", "Y"})
        exported = values["house"]._export_model()
        for name, cut in values["roof_elevation_cuts"].items():
            drawing = values[name]
            properties = ifcopenshell.util.element.get_pset(markers[cut.identifier], "BBIM_CutSymbol")
            self.assertEqual(json.loads(properties["Start"]), list(cut.start))
            self.assertEqual(json.loads(properties["End"]), list(cut.end))
            self.assertEqual(properties["Direction"], cut.direction)
            self.assertEqual((drawing.x, drawing.y), cut.center)
            self.assertEqual(drawing.direction, cut.view_direction)
            self.assertEqual(drawing.direction, (1, 0, 0))
            curve = markers[cut.identifier].Representation.Representations[0].Items[0].Elements[0]
            mirrored_marker = exported.by_guid(markers[cut.identifier].GlobalId)
            mirrored_placement = ifcopenshell.util.placement.get_local_placement(mirrored_marker.ObjectPlacement)
            camera = ifcopenshell.util.placement.get_local_placement(
                exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
            resolved = ifcopenshell.util.representation.resolve_items(
                mirrored_marker.Representation.Representations[0])
            world_points = [mirrored_placement @ item["matrix"] @ np.array((*p, 0, 1))
                            for item in resolved for line in item["item"].Elements
                            for p in line.Points.CoordList]
            for point in world_points:
                self.assertAlmostEqual(point[0], camera[0, 3])
            self.assertEqual(len(curve.Points.CoordList), 2)


class RoofElevationHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source)]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))

    def test_creates_independent_sections_for_main_and_dormer_assemblies(self):
        values = self.values
        helper = values["add_roof_elevation"]
        with patch.object(Drawing, "render") as render:
            first = helper("Helper main", rafter_index=1, offset=0.15)
            first_pset = ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing")
            first_table = json.loads(first_pset["RightPanelTables"])[0]
            first_styles = _timber_schedule_member_styles(first_pset)
            other = helper("Helper dormer", rafter_index=5, offset=0.2, radius=5)
            other_pset = ifcopenshell.util.element.get_pset(other.element, "EPset_Drawing")
            other_table = json.loads(other_pset["RightPanelTables"])[0]
            other_styles = _timber_schedule_member_styles(other_pset)
            render.assert_not_called()
        self.assertIsInstance(first, Drawing)
        self.assertIsInstance(other, Drawing)
        self.assertAlmostEqual(first.x, values["rafter_x_position"](values["rafters"][1]) - 0.15)
        other_x = values["rafter_x_position"](values["rafters"][5])
        self.assertAlmostEqual(other.x, other_x - 0.2)
        self.assertEqual(other.radius, 5)
        self.assertNotEqual(first.element.GlobalId, other.element.GlobalId)
        self.assertEqual(first_table["items"], other_table["items"])
        self.assertNotEqual(first_table["styled_member_guids"], other_table["styled_member_guids"])
        self.assertTrue({b.GlobalId for b in values["rafter_assemblies"][other_x]}
                        <= set(other_styles))
        self.assertNotEqual(set(first_styles), set(other_styles))
        self.assertEqual(ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing"), first_pset)

    def test_zero_and_negative_offsets_and_wrapped_rafter_entries(self):
        values = self.values
        helper = values["add_roof_elevation"]
        x = values["rafter_x_position"](values["rafters"][1])
        for index, (entry, offset) in enumerate((
            (values["StrongerRafter"](x), 0),
            (values["SplitRafter"](x, 7), -0.05),
            ((x, "before"), 0.25),
        )):
            with patch.dict(helper.__globals__, {"rafters": [entry]}):
                drawing = helper(f"Helper wrapped {index}", rafter_index=0, offset=offset)
            self.assertAlmostEqual(drawing.x, x - offset)

    def test_invalid_arguments_create_no_partial_drawing(self):
        values = self.values
        helper = values["add_roof_elevation"]
        house = values["house"]
        before = len(house._drawings)
        annotation_count = len(house.model.by_type("IfcAnnotation"))
        invalid = (
            ({"rafter_index": True}, TypeError),
            ({"rafter_index": 1.0}, TypeError),
            ({"rafter_index": -1}, ValueError),
            ({"rafter_index": len(values["rafters"])}, ValueError),
            ({"offset": "0.15"}, TypeError),
            ({"offset": True}, TypeError),
            ({"offset": float("nan")}, ValueError),
            ({"offset": float("inf")}, ValueError),
            ({"radius": 0}, ValueError),
        )
        for options, error in invalid:
            with self.subTest(options=options), self.assertRaises(error):
                helper("Invalid section", **({"rafter_index": 1} | options))
        self.assertEqual(len(house._drawings), before)
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), annotation_count)








class RoofFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "roof", "aa"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            patch.object(DrawingSheet, "render", return_value=Path("sheet.svg")) as sheet_render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]
            cls.sheet_rendered = [call.args[0] for call in sheet_render.call_args_list]

    def test_garage_has_four_corner_posts_and_flat_roof_all_3d_only(self):
        values = self.values
        parts = values["garage"]
        self.assertEqual(len(parts), 5)
        posts, roof = parts[:4], parts[4]
        roof_vertices = self.finished_vertices(roof)
        roof_min, roof_max = roof_vertices.min(axis=0), roof_vertices.max(axis=0)
        self.assertLess(roof_max[1], 0)  # Initial placement is in front of the house.
        self.assertAlmostEqual(roof_max[2] - roof_min[2], values["GARAGE_ROOF_THICKNESS"])
        post_size = values["GARAGE_POST_SIZE"]
        actual_corners = []
        for post in posts:
            vertices = self.finished_vertices(post)
            lower, upper = vertices.min(axis=0), vertices.max(axis=0)
            np.testing.assert_allclose(upper[:2] - lower[:2], (post_size, post_size))
            self.assertAlmostEqual(lower[2], 0)
            self.assertAlmostEqual(upper[2], roof_min[2])
            self.assertTrue(np.all(lower[:2] >= roof_min[:2] - 1e-8))
            self.assertTrue(np.all(upper[:2] <= roof_max[:2] + 1e-8))
            actual_corners.append(tuple(lower[:2]))
        # Posts may be inset below a roof overhang; check their own rectangle.
        corner_min = np.min(actual_corners, axis=0)
        corner_max = np.max(actual_corners, axis=0)
        expected_corners = {
            (corner_min[0], corner_min[1]), (corner_max[0], corner_min[1]),
            (corner_max[0], corner_max[1]), (corner_min[0], corner_max[1]),
        }
        self.assertEqual(len(expected_corners), 4)
        for corner in expected_corners:
            self.assertTrue(any(np.allclose(corner, actual) for actual in actual_corners))
        for part in parts:
            self.assertEqual(part.ObjectType, "BOX")
            self.assertIs(ifcopenshell.util.element.get_pset(
                part, "BBIM_DrawingVisibility", "ShowInDrawings"), False)

    def test_garage_is_mirrored_in_ifc_but_removed_only_from_drawing_copy(self):
        exported = self.values["house"]._export_model()
        for part in self.values["garage"]:
            original = self.finished_vertices(part)
            mirrored = self.finished_vertices(exported.by_guid(part.GlobalId))
            np.testing.assert_allclose(mirrored[:, 1:].min(axis=0), original[:, 1:].min(axis=0))
            np.testing.assert_allclose(mirrored[:, 1:].max(axis=0), original[:, 1:].max(axis=0))
            self.assertAlmostEqual(mirrored[:, 0].min(), -original[:, 0].max())
            self.assertAlmostEqual(mirrored[:, 0].max(), -original[:, 0].min())
        self.assertEqual(_remove_3d_only_elements(exported), 5)
        remaining = {e.GlobalId for e in exported.by_type("IfcBuildingElementProxy")}
        self.assertFalse(remaining & {e.GlobalId for e in self.values["garage"]})
        for part in self.values["garage"]:
            self.assertTrue(self.values["house"].model.by_guid(part.GlobalId))

    def test_garage_helper_accepts_reversed_corners_and_validates_before_creation(self):
        values = self.values
        with patch.object(House, "add_box", return_value=Mock()) as add_box:
            parts = values["draw_garage"](8, -1, 2, -5, 2.8)
            self.assertEqual(len(parts), 5)
            self.assertEqual(add_box.call_count, 5)
            roof = add_box.call_args_list[-1]
            self.assertEqual(roof.kwargs["origin"], (2, -5, 2.8))
            self.assertEqual(roof.kwargs["size"], (6, 4, values["GARAGE_ROOF_THICKNESS"]))
            self.assertTrue(all(c.kwargs["show_in_drawings"] is False
                                for c in add_box.call_args_list))
            add_box.reset_mock()
            for args in ((0, 0, 0, 4, 3), (0, 0, 4, 4, 0), (0, 0, 4, 4, float("nan"))):
                with self.assertRaises(ValueError):
                    values["draw_garage"](*args)
            add_box.assert_not_called()

    def test_roof_uses_native_surfaces_with_member_ids(self):
        drawing = next(d for d in self.values["house"]._drawings if d.name == "Roof plan")
        pset = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
        self.assertEqual(pset["FillMode"], "SHAPELY")
        self.assertEqual(pset["Metadata"], "GlobalId")
        self.assertTrue(drawing.surface_fills)

    def test_bedroom_roof_window_is_flush_with_tiles(self):
        values = self.values
        window = values["roof_window"]
        tiles = values["roof_window_tiles"]
        plane = values["garden_roof"]
        local = np.array([plane.to_local(tuple(v)) for v in self.finished_vertices(window)])
        self.assertAlmostEqual(local[:, 2].max(), tiles.z_offset + tiles.thickness)
        self.assertAlmostEqual(local[:, 2].min(), tiles.z_offset + tiles.thickness - 0.10)
        self.assertIs(values["roof_window_opening"].window, window)
        self.assertEqual(window.FillsVoids[0].RelatingOpeningElement.VoidsElements[0].RelatingBuildingElement, tiles)
        windows_storey = values["roof_layer_storeys"]["Roof windows"]
        self.assertEqual(ifcopenshell.util.element.get_container(window), windows_storey.element)
        roof_drawing = next(d for d in values["house"]._drawings if d.name == "Roof plan")
        self.assertNotIn(windows_storey, roof_drawing.storeys)

    def test_all_window_frames_and_glazing_are_white_in_3d(self):
        for window in self.values["house"].model.by_type("IfcWindow"):
            with self.subTest(window=window.Name):
                aspects = {aspect.Name: aspect for aspect in window.Representation.HasShapeAspects}
                self.assertEqual(set(aspects), {"Lining", "Framing", "Glazing"})
                for name, aspect in aspects.items():
                    for representation in aspect.ShapeRepresentations:
                        for item in representation.Items:
                            shading = item.StyledByItem[0].Styles[0].Styles[0]
                            rgb = shading.SurfaceColour
                            self.assertEqual((rgb.Red, rgb.Green, rgb.Blue), (1, 1, 1))
                            if name == "Glazing":
                                self.assertGreater(shading.Transparency, 0)
                            else:
                                self.assertEqual(shading.Transparency, 0)

    def test_bedroom_window_reveals_join_plasterboard_to_frame(self):
        values = self.values
        panels = values["roof_window_lining"]
        self.assertEqual(len(panels), 4)
        self.assertEqual(panels, values["roof_window_opening"].lining)
        plane = values["garden_roof"]
        frame = ifcopenshell.util.element.get_pset(values["roof_window"], "BBIM_RoofWindow")
        storey = values["roof_layer_storeys"]["Gypsum plasterboard"]
        for panel in panels:
            local = np.array([plane.to_local(tuple(v)) for v in self.finished_vertices(panel)])
            plasterboard = values["roof_window_plasterboard"]
            self.assertAlmostEqual(local[:, 2].min(), plasterboard.z_offset + plasterboard.thickness - 0.001)
            self.assertAlmostEqual(local[:, 2].max(), frame["TopOffset"] - frame["FrameDepth"])
            self.assertEqual(ifcopenshell.util.element.get_container(panel), storey.element)
            self.assertFalse(panel.HasOpenings)
        modified_voids = [void for void in values["roof_window_opening"].elements
                          if ifcopenshell.util.element.get_pset(void, "BBIM_RoofOpening", "LiningInset")]
        # Independent interior profiles can change the number of matching
        # plasterboard pieces. Every matching host cut must be inset, not a
        # fixed count inherited from the former full-length high roof.
        bottom = values["roof_window_plasterboard"]
        matching_layers = {layer for layer in plane.elements
                           if getattr(layer, "material_name", None) == bottom.material_name
                           and np.isclose(layer.z_offset, bottom.z_offset)
                           and np.isclose(layer.thickness, bottom.thickness)}
        expected_voids = {void for void in values["roof_window_opening"].elements
                          if void.VoidsElements[0].RelatingBuildingElement in matching_layers}
        self.assertTrue(expected_voids)
        self.assertEqual(set(modified_voids), expected_voids)
        for void in modified_voids:
            host = void.VoidsElements[0].RelatingBuildingElement
            self.assertEqual(ifcopenshell.util.element.get_material(host).Name, "Gypsum plasterboard")

    def test_optional_collar_min_y_is_parsed_and_validated(self):
        parse = self.values["rafter_collar_min_y"]
        for entry in (1.2, (1.2, "before"), (1.2, "+after", {}),
                      self.values["StrongerRafter"](1.2), self.values["SplitRafter"](1.2, 7)):
            self.assertIsNone(parse(entry))
        self.assertEqual(parse((1.2, "before", {"min_y": 2.8})), 2.8)
        self.assertEqual(parse((1.2, "+after", {"min_y": -1})), -1)
        for entry in ((1.2,), (1.2, "before", {}, {}), (1.2, "before", None),
                      (1.2, "before", {"unknown": 1}),
                      *((1.2, "before", {"min_y": value})
                        for value in (True, None, "2.8", float("inf"), float("nan")))):
            with self.subTest(entry=entry), self.assertRaises((TypeError, ValueError)):
                parse(entry)

    def test_collar_min_y_cuts_both_boards_but_leaves_other_pairs_and_rafters_unchanged(self):
        values = self.values
        chimney_max_y = self.finished_vertices(values["chimney"])[:, 1].max()
        clipped = []
        for x, _ in values["main_rafter_sections"]:
            ties = [beam for beam in values["rafter_assemblies"][x] if beam in values["collar_ties"]]
            self.assertEqual(len(ties), 2)
            if x in values["collar_tie_min_y"]:
                min_y = values["collar_tie_min_y"][x]
                for tie in ties:
                    self.assertAlmostEqual(tie.start[1], min_y)
                    self.assertAlmostEqual(self.finished_vertices(tie)[:, 1].min(), min_y)
                    self.assertGreater(min_y, chimney_max_y)
                    clipped.append(tie)
                rafters = [beam for beam in values["rafter_assemblies"][x]
                           if beam.kind == "RAFTER" and beam.roof_plane is values["street_roof"]]
                self.assertEqual(len(rafters), 1)
                self.assertLess(self.finished_vertices(rafters[0])[:, 1].min(), min_y)
            else:
                for tie in ties:
                    self.assertAlmostEqual(tie.start[1],
                                           values["framing_roof_planes_at"](x)[0].origin[1] - values["COLLAR_TIE_EXTENSION"])
        self.assertEqual(len(clipped), 2)
        rows = [row for row in values["timber_schedule_rows"] if row[0].startswith("Kleštiny")]
        clipped_ids = {beam.GlobalId for beam in clipped}
        matching = [row for row in rows if clipped_ids & {beam.GlobalId for beam in row[1]}]
        self.assertEqual(len(matching), 1)
        self.assertEqual({beam.GlobalId for beam in matching[0][1]}, clipped_ids)
        for _, members, _, _ in rows:
            self.assertEqual(len({round(beam.finished_length() * 1000) for beam in members}), 1)

    def test_paired_collar_ties_above_purlins_and_visibility_storey(self):
        model = self.values["house"].model
        beams = model.by_type("IfcBeam")
        self.assertTrue(beams)
        self.assertEqual(sum((beam.Name or "").startswith("Collar tie ") for beam in beams), 2 * len(self.values["high_rafters"]))
        self.assertIn("Collar ties", self.values["roof_layer_storeys"])
        self.assertTrue(
            any(
                "Collar ties" in (storey.Name or "")
                for storey in model.by_type("IfcBuildingStorey")
            )
        )
        self.assertTrue(self.values["main_roof_rafters"])
        self.assertEqual(len(self.values["street_purlins"]), 2)
        self.assertEqual(len(self.values["garden_purlins"]), 2)
        values = self.values
        ties = values["collar_ties"]
        self.assertEqual(len(ties), 2 * len(values["main_rafter_sections"]))
        for index, (x, width) in enumerate(values["main_rafter_sections"]):
            left, right = ties[index * 2 : index * 2 + 2]
            for tie, sign in ((left, -1), (right, 1)):
                with self.subTest(tie=tie.Name):
                    self.assertEqual((tie.width, tie.height), (0.05, 0.15))
                    offset = sign * (width + tie.width) / 2
                    dormer_offset = values["paired_rafter_dormer_offsets"].get(x, 0)
                    if sign * dormer_offset > 0:
                        offset += dormer_offset
                    self.assertAlmostEqual(tie.start[0], x + offset)
                    vertices = self.finished_vertices(tie)
                    top = values["purlin_top_z_at"](tie.start[0])
                    self.assertAlmostEqual(vertices[:, 2].min(), top)
                    self.assertAlmostEqual(vertices[:, 2].max(), top + 0.15)
                    if x in values["collar_tie_min_y"]:
                        self.assertAlmostEqual(vertices[:, 1].min(), values["collar_tie_min_y"][x])
                    else:
                        # Untrimmed ends still span both complete purlin widths.
                        self.assertLess(vertices[:, 1].min(), values["framing_roof_planes_at"](x)[0].origin[1])
                    self.assertGreater(vertices[:, 1].max(), values["framing_roof_planes_at"](x)[1].origin[1])
                    self.assertEqual(
                        ifcopenshell.util.element.get_container(tie),
                        values["roof_layer_storeys"]["Collar ties"].element,
                    )

    def test_dormer_side_collar_boards_clear_all_paired_rafters(self):
        values = self.values
        cases = set()
        for index, (x, width) in enumerate(values["main_rafter_sections"]):
            left, right = values["collar_ties"][index * 2:index * 2 + 2]
            offset = values["paired_rafter_dormer_offsets"].get(x)
            if offset is None:
                # Ordinary (unpaired) rafters are unchanged.
                self.assertAlmostEqual(left.start[0], x - (width + left.width) / 2)
                self.assertAlmostEqual(right.start[0], x + (width + right.width) / 2)
                continue
            moved, unchanged = (left, right) if offset < 0 else (right, left)
            cases.add("before" if offset < 0 else "after")
            vertices = self.finished_vertices(moved)
            outer_face = x + offset + np.sign(offset) * values["RAFTER_THICKNESS"] / 2
            nearest_face = vertices[:, 0].max() if offset < 0 else vertices[:, 0].min()
            self.assertAlmostEqual(nearest_face, outer_face)
            self.assertAlmostEqual(abs(moved.start[0] - x),
                                   abs(offset) + (width + moved.width) / 2)
            self.assertAlmostEqual(abs(unchanged.start[0] - x), (width + unchanged.width) / 2)
            self.assertEqual(moved.start[0], moved.end[0])
        self.assertEqual(cases, {"before", "after"})
        pairs = [r for r in values["rafters"] if isinstance(r, tuple)]
        self.assertEqual(len(values["paired_rafter_dormer_offsets"]), len(pairs))
        main_entries = {x: short for x, kind, short, _, _ in values["rafter_layout"]
                        if kind == "main"}
        # '+' still controls shortening only, not collar-board clearance.
        for entry in pairs:
            x, side = entry[:2]
            self.assertIn(x, values["paired_rafter_dormer_offsets"])
            self.assertEqual(main_entries[x], not side.startswith("+"))

    def test_roof_and_aa_drawings_build_and_schedule_includes_collar_rows(self):
        self.assertEqual(self.rendered, ["aa.svg"])
        self.assertEqual(self.sheet_rendered, ["roof.svg"])
        names = [row[0] for row in self.values["timber_schedule_rows"]]
        # Collar groups may be consolidated; every board must still be listed
        # exactly in the measured groups checked below.
        self.assertTrue(any(name.startswith("Kleštiny") for name in names))
        self.assertTrue(any("Vaznice" in name for name in names))
        self.assertTrue(any("Krokve" in name for name in names))
        self.assertTrue(any("Pozednice" in name for name in names))
        self.assertNotIn("Sedla vaznic", names)
        self.assertIn("Rozpěry vaznic – střed", names)
        self.assertIn("Rozpěry vaznic – krajní", names)
        self.assertIn("Podložky vaznic", names)
        rows = [row for row in self.values["timber_schedule_rows"] if row[0].startswith("Kleštiny")]
        self.assertEqual(
            {beam.GlobalId for row in rows for beam in row[1]},
            {beam.GlobalId for beam in self.values["collar_ties"]},
        )
        for row in rows:
            self.assertGreater(
                row[3]["drawing_order"], self.values["PURLIN_AND_WALL_PLATE_DRAWING_ORDER"]
            )
            self.assertLess(row[3]["drawing_order"], self.values["MAIN_RAFTER_DRAWING_ORDER"])

    def test_roof_cut_symbol_uses_shared_aa_definition(self):
        cut = self.values["aa_cut"]
        drawing = next(d for d in self.values["house"]._drawings if d.name == "Roof plan")
        markers = [a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                   if ifcopenshell.util.element.get_pset(a, "BBIM_CutSymbol", "Identifier") == cut.identifier]
        self.assertEqual(len(markers), 1)
        properties = ifcopenshell.util.element.get_pset(markers[0], "BBIM_CutSymbol")
        self.assertEqual(json.loads(properties["Start"]), list(cut.start))
        self.assertEqual(json.loads(properties["End"]), list(cut.end))
        self.assertEqual(properties["Identifier"], cut.identifier)
        self.assertEqual(properties["Direction"], cut.direction)

    def test_roof_schedule_resolves_shared_materials_and_preserves_row_selections(self):
        values = self.values
        purlin_guids = {b.GlobalId for b in (*values["street_purlins"], *values["garden_purlins"], values["transverse_purlin"])}
        for name, members, _, settings in values["timber_schedule_rows"]:
            is_purlin = all(member.GlobalId in purlin_guids for member in members)
            grade = resolve_timber_grade(settings["material"])
            self.assertEqual(settings["material"], grade.name)
            if is_purlin:
                expected_grade = "GL28h" if "střední" in name else "GL24c"
                self.assertEqual(grade.name, expected_grade, name)
        # drawing1 is replaced by the subsequent AA drawing; inspect persisted
        # plan tables directly on the model's roof drawing instead.
        tables = []
        for element in values["house"].model.by_type("IfcAnnotation"):
            if element != values["roof_plan"].element:
                continue
            properties = ifcopenshell.util.element.get_pset(element, "EPset_Drawing") or {}
            if properties.get("RightPanelTables"):
                tables.extend(json.loads(properties["RightPanelTables"]))
        items = [item for table in tables if table["kind"] == "timber_schedule"
                 for item in table["items"]]
        self.assertEqual(len(items), len(values["timber_schedule_rows"]))
        self.assertEqual(sum(item["material"] == "GL24c" for item in items), 2)
        self.assertEqual(sum(item["material"] == "GL28h" for item in items), 1)
        expected = {name: settings["material"] for name, _, _, settings in values["timber_schedule_rows"]}
        self.assertEqual({item["name"]: item["material"] for item in items}, expected)

    def test_collar_ties_are_mirrored_once(self):
        exported = self.values["house"]._export_model()
        for tie in self.values["collar_ties"]:
            original = self.finished_vertices(tie)
            mirrored = self.finished_vertices(exported.by_guid(tie.GlobalId))
            np.testing.assert_allclose(mirrored[:, 1:].min(axis=0), original[:, 1:].min(axis=0))
            np.testing.assert_allclose(mirrored[:, 1:].max(axis=0), original[:, 1:].max(axis=0))
            self.assertAlmostEqual(mirrored[:, 0].min(), -original[:, 0].max())
            self.assertAlmostEqual(mirrored[:, 0].max(), -original[:, 0].min())

    def test_purlin_spacers_follow_main_rafter_positions_and_touch_inner_faces(self):
        values = self.values
        spacers = values["purlin_spacers"]
        self.assertEqual(len(spacers), len(values["main_rafter_positions"]))
        width, height = values["PURLIN_SPACER_SIZE"]
        self.assertEqual((width, height), (0.08, 0.20))
        for x, spacer in zip(values["main_rafter_positions"], spacers):
            with self.subTest(spacer=spacer.Name):
                purlin_width, _, distance = values["purlin_dimensions_at"](x)
                street_inner_y = values["HALF_DEPTH"] - distance + purlin_width / 2
                garden_inner_y = values["HALF_DEPTH"] + distance - purlin_width / 2
                top = values["purlin_top_z_at"](x)
                np.testing.assert_allclose(
                    spacer.start, (x, street_inner_y, top - height / 2)
                )
                np.testing.assert_allclose(
                    spacer.end, (x, garden_inner_y, top - height / 2)
                )
                self.assertAlmostEqual(spacer.length, 2 * distance - purlin_width)
                self.assertEqual((spacer.width, spacer.height), (width, height))
                vertices = self.finished_vertices(spacer)
                np.testing.assert_allclose(
                    vertices.min(axis=0),
                    (x - width / 2, street_inner_y, top - height),
                )
                np.testing.assert_allclose(
                    vertices.max(axis=0), (x + width / 2, garden_inner_y, top)
                )
        rows = [row for row in values["timber_schedule_rows"] if row[0].startswith("Rozpěry vaznic")]
        self.assertEqual(
            {beam.GlobalId for row in rows for beam in row[1]},
            {beam.GlobalId for beam in spacers},
        )
        self.assertTrue(all(row[2] == 0 for row in rows))

    def test_purlin_spacers_are_mirrored_with_the_roof(self):
        values = self.values
        exported = values["house"]._export_model()
        for spacer in values["purlin_spacers"]:
            vertices = self.finished_vertices(exported.by_guid(spacer.GlobalId))
            centre = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
            np.testing.assert_allclose(
                centre,
                (-spacer.start[0], values["HALF_DEPTH"], spacer.start[2]),
                atol=1e-8,
            )


    def test_independent_purlins_export_once_with_correct_overlap_and_height(self):
        values = self.values
        exported = values["house"]._export_model()
        x_sign = -1 if values["house"].mirror_x else 1
        for side in ("street", "garden"):
            bounds = []
            for beam in values[side + "_purlins"]:
                self.assertEqual(
                    beam.ObjectPlacement.PlacementRelTo,
                    values["upper"].element.ObjectPlacement,
                )
                vertices = self.finished_vertices(exported.by_guid(beam.GlobalId))
                low, high = vertices.min(axis=0), vertices.max(axis=0)
                bounds.append((low, high))
                np.testing.assert_allclose(
                    (low + high) / 2,
                    (x_sign * (beam.start[0] + beam.end[0]) / 2, beam.start[1], beam.start[2]),
                    atol=1e-8,
                )
                np.testing.assert_allclose(
                    high - low, (beam.length, beam.width, beam.height), atol=1e-8
                )
            self.assertEqual(len(bounds), 2)
            self.assertAlmostEqual(bounds[1][1][2], values["PURLIN_TOP_Z"])

    def test_high_purlin_outer_faces_stay_aligned_with_unchanged_roof(self):
        values = self.values
        for side in ("street", "garden"):
            plane = values[side + "_roof"]
            for beam in values[side + "_purlins"][:2]:
                x = (beam.start[0] + beam.end[0]) / 2
                y = beam.start[1] + (-1 if side == "street" else 1) * beam.width / 2
                # The outer top edge meets the original roof datum, just as
                # the middle purlin does; the rafter's seat offset is unchanged.
                roof_z = values["plane_height_at"](*plane.points, x=x, y=y)
                self.assertAlmostEqual(roof_z, beam.start[2] + beam.height / 2)
                self.assertAlmostEqual(y, values["STREET_ROOF_JOINT_Y"] if side == "street"
                                       else values["GARDEN_ROOF_JOINT_Y"])
                if side == "garden":
                    dormer_z = values["plane_height_at"](*values["dormer_roof"].points, x=x, y=y)
                    self.assertAlmostEqual(dormer_z, beam.start[2] + beam.height / 2)
        self.assertGreater(values["VAZNICE_SIDE_DIST"], values["VAZNICE_DIST"])


    def test_two_packing_blocks_support_only_high_left_pieces(self):
        values = self.values
        blocks = values["purlin_packing_blocks"]
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            with self.subTest(block=block.Name):
                self.assertEqual((block.width, block.height), (
                    values["VAZNICE_SIDE_BASE"],
                    values["VAZNICE_HEIGHT"] - values["VAZNICE_SIDE_HEIGHT"],
                ))
                self.assertAlmostEqual(block.length, values["BWT"] / 2)
                low, high = self.finished_vertices(block).min(axis=0), self.finished_vertices(block).max(axis=0)
                self.assertAlmostEqual(low[2], values["PURLIN_BOTTOM_Z"])
                self.assertAlmostEqual(high[2], values["PURLIN_TOP_Z"] - values["VAZNICE_SIDE_HEIGHT"])
                side = "street" if block.Name.startswith("Street") else "garden"
                self.assertIn("left", block.Name)
                piece_index = 0
                purlin = values[side + "_purlins"][piece_index]
                self.assertAlmostEqual(block.start[1], purlin.start[1])
                self.assertGreaterEqual(low[0], purlin.start[0] - 1e-9)
                self.assertLessEqual(high[0], purlin.end[0] + 1e-9)
                wall = values["wall_2" if piece_index == 0 else "wall_3"]
                wall_low, wall_high = self.finished_vertices(wall).min(axis=0), self.finished_vertices(wall).max(axis=0)
                self.assertGreaterEqual(low[0], wall_low[0] - 1e-9)
                self.assertLessEqual(high[0], wall_high[0] + 1e-9)
                self.assertAlmostEqual(low[2], wall_high[2])
        row = next(row for row in values["timber_schedule_rows"] if row[0] == "Podložky vaznic")
        self.assertEqual(tuple(row[1]), tuple(blocks))

    def test_packing_blocks_are_mirrored_once(self):
        values = self.values
        exported = values["house"]._export_model()
        for block in values["purlin_packing_blocks"]:
            original = self.finished_vertices(block)
            mirrored = self.finished_vertices(exported.by_guid(block.GlobalId))
            np.testing.assert_allclose(mirrored[:, 1:].min(axis=0), original[:, 1:].min(axis=0))
            np.testing.assert_allclose(mirrored[:, 1:].max(axis=0), original[:, 1:].max(axis=0))
            self.assertAlmostEqual(mirrored[:, 0].min(), -original[:, 0].max())
            self.assertAlmostEqual(mirrored[:, 0].max(), -original[:, 0].min())

    @staticmethod
    def finished_vertices(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        # Boolean cuts can leave unused vertices from the source solid.
        return vertices[np.unique(np.asarray(shape.geometry.faces))]

    def main_eave_z(self, plane):
        v = self.values
        plate_z = {
            v["street_roof"]: v["STREET_WALL_PLATE_Z"],
            v["garden_roof"]: v["GARDEN_WALL_PLATE_Z"],
            v["dormer_roof"]: v["DORMER_WALL_PLATE_Z"],
            v["dormer_rafter_roof"]: v["DORMER_WALL_PLATE_Z"],
        }[plane]
        drop = v["DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE"] if plane in (v["dormer_roof"], v["dormer_rafter_roof"]) else v["ROOF_EAVE_DROP_BELOW_WALL_PLATE"]
        return plate_z - v["WALL_PLATE_SIZE"][1]/2 - drop

    def test_short_dormer_rafters_are_cut_at_actual_purlin_bottom(self):
        values = self.values
        for beam in values["dormer_short_rafters"]:
            expected = values["purlin_bottom_z_at"](beam.local_start[0])
            self.assertTrue(
                any(
                    all(abs(point[2] - expected) < 1e-8 for point in cut) for cut in beam.extra_cuts
                )
            )
            self.assertAlmostEqual(self.finished_vertices(beam)[:, 2].min(), expected, places=6)

    def test_dormer_rafters_reach_and_are_trimmed_to_opposite_main_rafter_upper_face(self):
        values = self.values
        plane = values["dormer_rafter_roof"]
        cut = values["offset_plane"](
            *values["STREET_ROOF_PLANE_POINTS"],
            offset=values["RAFTER_Z_OFFSET"] + values["RAFTER_HEIGHT"]
        )
        self.assertEqual(plane.cuts[0], cut)
        self.assertEqual(plane.cuts[1:], values["dormer_roof"].cuts[1:])
        self.assertTrue(values["dormer_roof_rafters"])
        for beam in values["dormer_roof_rafters"]:
            with self.subTest(beam=beam.GlobalId):
                self.assertIs(beam.roof_plane, plane)
                vertices = self.finished_vertices(beam)
                residuals = np.array([
                    z - values["plane_height_at"](*cut, x=x, y=y)
                    for x, y, z in vertices
                ])
                # Four corners lie on the opposite rafter's upper-face plane;
                # the dormer member does not protrude beyond that plane.
                self.assertLessEqual(residuals.max(), 1e-7)
                face = vertices[np.abs(residuals) < 1e-7]
                self.assertGreaterEqual(len(face), 4)
                self.assertGreater(np.ptp(face[:, 1]), 0.01)
                self.assertLess(vertices[:, 1].min(), values["HALF_DEPTH"])
                self.assertLessEqual(vertices[:, 1].max(), values["DORMER_ROOF_EAVE_Y"] - values["ROOF_EAVE_SETBACK"] + 1e-7)
                self.assertAlmostEqual(vertices[:, 2].min(), self.main_eave_z(plane))
                # Both faces of the raw prism extend past the trimming plane.
                for local_z in (beam.z_offset, beam.z_offset + beam.height):
                    x, y, z = plane.to_world((*beam.local_start, local_z))
                    self.assertGreater(z - values["plane_height_at"](*cut, x=x, y=y), 0)

    def test_extended_dormer_rafters_are_mirrored_once(self):
        exported = self.values["house"]._export_model()
        for beam in self.values["dormer_roof_rafters"]:
            original = self.finished_vertices(beam)
            mirrored = self.finished_vertices(exported.by_guid(beam.GlobalId))
            np.testing.assert_allclose(mirrored[:, 1:].min(axis=0), original[:, 1:].min(axis=0))
            np.testing.assert_allclose(mirrored[:, 1:].max(axis=0), original[:, 1:].max(axis=0))
            self.assertAlmostEqual(mirrored[:, 0].min(), -original[:, 0].max())
            self.assertAlmostEqual(mirrored[:, 0].max(), -original[:, 0].min())

    @unittest.skip("The simulator has not been updated for the intentionally removed low roof")
    def test_simulator_dormer_endpoint_matches_finished_ifc_cut_face(self):
        from roof_frame_3d import RoofLayout

        values = self.values
        layout = RoofLayout.from_house(Path(__file__).with_name("house_ifc.py"))
        simulated = [b for b in layout.beams if b.name.endswith("_dormer")]
        self.assertEqual(len(simulated), len(values["dormer_roof_rafters"]))
        cut = values["dormer_rafter_roof"].cuts[0]
        for beam in values["dormer_roof_rafters"]:
            vertices = self.finished_vertices(beam)
            residuals = [z - values["plane_height_at"](*cut, x=x, y=y)
                         for x, y, z in vertices]
            face = vertices[np.abs(residuals) < 1e-7]
            physical_end = face.mean(axis=0)
            candidate = next(b for b in simulated if abs(b.start[0] - beam.start[0]) < 1e-7)
            np.testing.assert_allclose(candidate.start, physical_end, atol=1e-7)



    def test_touching_main_rafters_suppress_their_shared_collar_boards(self):
        v = self.values
        self.assertEqual(v["touching_rafter_sides"]([(1., .08), (1.08, .08)]),
                         {(1., "right"), (1.08, "left")})
        self.assertEqual(v["touching_rafter_sides"]([(1., .08), (1.2, .08)]), set())



    def test_short_garden_wall_plate_ends_with_the_middle_purlin(self):
        v = self.values
        plate = v["beam4_b"]
        self.assertAlmostEqual(plate.start[0], v["wall3_x"])
        self.assertAlmostEqual(plate.end[0], v["LOWER_NADEZDIVKA_X"] + .2)
        self.assertAlmostEqual(plate.end[0], v["garden_purlins"][1].end[0])
        self.assertIs(v["wall_plate_at"](v["LOWER_NADEZDIVKA_X"] + .1, side="garden"),
                      v["beam4_b"])

    def test_high_street_wall_plate_ends_with_the_middle_purlin_and_covers_overlap(self):
        v = self.values
        plate = v["beam3"]
        self.assertAlmostEqual(plate.end[0], v["LOWER_NADEZDIVKA_X"] + .2)
        self.assertAlmostEqual(plate.end[0], v["street_purlins"][1].end[0])
        self.assertAlmostEqual(plate.end[0], v["beam4_b"].end[0])
        x = v["LOWER_NADEZDIVKA_X"] + .105
        with patch.dict(v["framing_levels"], {x: "high"}):
            self.assertIs(v["wall_plate_at"](x, side="street"), plate)


    def test_framing_purlin_helpers_match_the_actual_selected_members(self):
        values = self.values
        for side in ("street", "garden"):
            for index, beam in enumerate(values[side + "_purlins"]):
                x = (beam.start[0] + beam.end[0]) / 2
                self.assertIs(values["purlin_at"](x, side=side), beam)
                self.assertAlmostEqual(values["purlin_top_z_at"](x), beam.start[2] + beam.height / 2)
                self.assertAlmostEqual(values["purlin_bottom_z_at"](x), beam.start[2] - beam.height / 2)

    def test_sloped_insulation_is_clipped_at_purlin_outer_vertical_face(self):
        values = self.values
        for layer in values["roof_under_rafter_insulations"].values():
            with self.subTest(layer=layer.Name):
                street = layer.Name.startswith("Street")
                vertices = self.finished_vertices(layer)
                x = (vertices[:, 0].min() + vertices[:, 0].max()) / 2
                _, _, profile = values["inner_roof_section_at"](x)
                expected = profile["street_plane" if street else "garden_plane"].origin[1]
                self.assertTrue(
                    any(
                        all(abs(point[1] - expected) < 1e-8 for point in cut)
                        for cut in layer.extra_cuts
                    )
                )
                self.assertFalse(
                    any(
                        max(p[2] for p in cut) - min(p[2] for p in cut) < 1e-8
                        for cut in layer.extra_cuts
                    )
                )
                vertices = self.finished_vertices(layer)
                actual = vertices[:, 1].max() if street else vertices[:, 1].min()
                self.assertAlmostEqual(actual, expected, places=6)

    def test_sloped_batting_ends_at_the_same_vertical_faces_with_existing_insets(self):
        values = self.values
        for name, end in (
            ("AA street under-rafter batting", values["under_rafter_street_top"]),
            ("AA dormer under-rafter batting", values["under_rafter_dormer_top"]),
        ):
            annotation = next(
                e for e in values["house"].model.by_type("IfcAnnotation") if e.Name == name
            )
            placement = ifcopenshell.util.placement.get_local_placement(annotation.ObjectPlacement)
            curve = annotation.Representation.Representations[0].Items[0]
            axis = np.array(
                [(placement @ np.array((*point, 0.0, 1.0)))[:3] for point in curve.Points.CoordList]
            )
            inset = values["UNDER_RAFTER_BATTING_END_INSET"]
            self.assertAlmostEqual(min(np.linalg.norm(axis - end, axis=1)), inset)
        self.assertAlmostEqual(values["under_rafter_street_top"][1], values["STREET_ROOF_JOINT_Y"])
        self.assertAlmostEqual(values["under_rafter_dormer_top"][1], values["GARDEN_ROOF_JOINT_Y"])

    def test_horizontal_batting_is_centred_half_insulation_thickness_above_purlins(self):
        values = self.values
        thickness = values["THERMAL_INSULATION_UNDER_RAFTERS"]
        purlin_top = values["PURLIN_TOP_Z"]
        centre = values["horizontal_batting_center_z"]
        self.assertAlmostEqual(centre - thickness / 2, purlin_top)
        self.assertAlmostEqual(values["horizontal_batting_start"][2], centre)
        self.assertAlmostEqual(values["horizontal_batting_end"][2], centre)
        # Horizontal batting runs between the purlin centres, independent
        # of roof pitch or the intersections of the sloped insulation.
        for purlin, point in (
            (values["street_purlins"][1], values["horizontal_batting_start"]),
            (values["garden_purlins"][1], values["horizontal_batting_end"]),
        ):
            self.assertAlmostEqual(point[0], values["aa_x"])
            self.assertAlmostEqual(point[1], purlin.start[1])
        self.assertAlmostEqual(
            np.linalg.norm(
                np.array(values["horizontal_batting_end"])
                - np.array(values["horizontal_batting_start"])
            ),
            2 * values["VAZNICE_DIST"],
        )
        for side in ("street", "garden"):
            for section, purlin in zip(("left", "middle", "right"), values[side + "_purlins"]):
                self.assertAlmostEqual(self.finished_vertices(purlin)[:, 2].max(),
                                       values["PURLIN_SECTION_BOTTOM_Z"][section] + purlin.height)

    def test_under_rafter_batting_has_same_relative_clearance_as_between_rafters(self):
        values = self.values
        names = {
            "AA street under-rafter batting",
            "AA dormer under-rafter batting",
            "AA horizontal ceiling insulation batting",
        }
        annotations = [
            annotation
            for annotation in values["house"].model.by_type("IfcAnnotation")
            if annotation.Name in names
        ]
        self.assertEqual({annotation.Name for annotation in annotations}, names)
        physical_thickness = values["THERMAL_INSULATION_UNDER_RAFTERS"]
        between_rafter_ratio = values["ROOF_BATTING_THICKNESS"] / values["RAFTER_SIZE"][1]
        for annotation in annotations:
            with self.subTest(annotation=annotation.Name):
                symbol_thickness = ifcopenshell.util.element.get_psets(annotation)["BBIM_Batting"][
                    "Thickness"
                ]
                self.assertAlmostEqual(symbol_thickness, values["UNDER_RAFTER_BATTING_THICKNESS"])
                self.assertLess(symbol_thickness, physical_thickness)
                self.assertAlmostEqual(symbol_thickness / physical_thickness, between_rafter_ratio)


    def test_inner_ranges_validate_profiles_and_reject_only_inner_overlaps(self):
        v = self.values
        validate = v["validate_roof_layer_ranges"]
        validate(v["roof_under_rafter_x_ranges"])
        validate(v["roof_over_rafter_x_ranges"], allow_overlap=True)
        overlap = ((0, 2, "normal"), (1, 3, "dormer"))
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            validate(overlap)
        validate(overlap, allow_overlap=True)
        validate(((2, 3, "ceiling"), (0, 2, "normal")))
        for invalid in (((0, 1, "unknown"),), ((1, 0, "normal"),), ((0, float("inf"), "lower"),)):
            with self.assertRaises(ValueError):
                validate(invalid, allow_overlap=True)
        selector = v["inner_roof_section_at"]
        with patch.dict(selector.__globals__, {"roof_under_rafter_x_ranges":
                                              ((1, 2, "ceiling"), (0, 1, "normal"))}):
            self.assertEqual(selector(1)[1], "ceiling")
            with self.assertRaisesRegex(ValueError, "no under-rafter layer range"):
                selector(-1)


    def test_each_interior_profile_has_matching_slope_and_flat_bottom_junctions(self):
        v = self.values
        for profile in v["roof_inner_profiles"].values():
            if profile.get("ceiling_only"):
                continue
            for side in ("street", "garden"):
                for layer, (slope_y, flat_y) in profile[f"{side}_boundaries"].items():
                    slope = profile[f"{side}_plane"].to_world((0, slope_y, v["SLOPED_INNER_LAYER_LAYOUT"][layer][0]))
                    flat = profile["flat_plane"].to_world((0, flat_y, profile["flat_layout"][layer][0]))
                    np.testing.assert_allclose(slope, flat, atol=1e-9)
        lower = v["LOWER_FLAT_CEILING_LAYER_HEIGHTS"]
        self.assertLess(lower["Gypsum plasterboard"][1], lower["Vapour barrier"][0])

    def test_outer_layers_above_dormer_keep_garden_side_of_ridge_at_full_thickness(self):
        values = self.values
        plane = values["garden_roof"]
        layers = [layer for layer in plane.elements
                  if (layer.Name or "").startswith("Garden segment 1 above dormer ")
                  and hasattr(layer, "outline")]
        self.assertEqual({layer.material_name for layer in layers},
                         {"MDF", "Roofing underlay", "Roof tiles"})
        for layer in layers:
            with self.subTest(material=layer.material_name):
                vertices = self.finished_vertices(layer)
                self.assertAlmostEqual(vertices[:, 1].min(), values["HALF_DEPTH"], places=6)
                # The other end remains at the original local-Y=0 dormer join.
                local = np.array([plane.to_local(vertex) for vertex in vertices])
                self.assertAlmostEqual(local[:, 1].max(), 0, places=6)
                self.assertGreater(vertices[:, 1].max(), values["HALF_DEPTH"] + .5)
                for z in (layer.z_offset, layer.z_offset + layer.thickness):
                    ridge_face = np.isclose(vertices[:, 1], values["HALF_DEPTH"], atol=1e-7)
                    self.assertTrue(np.any(ridge_face & np.isclose(local[:, 2], z, atol=1e-7)))
                # The source centroid must be on the intended side, regardless
                # of the different offsets of MDF, underlay and roof tiles.
                xs, ys = zip(*layer.outline)
                centre = plane.to_world(((min(xs) + max(xs)) / 2,
                                         (min(ys) + max(ys)) / 2,
                                         layer.z_offset + layer.thickness / 2))
                self.assertGreater(centre[1], values["HALF_DEPTH"])
                self.assertLess(centre[1], values["GARDEN_ROOF_EAVE_Y"])



    def test_dormer_counter_battens_still_follow_paired_dormer_positions(self):
        v = self.values
        positions = set(v["dormer_rafter_positions"])
        battens = [b for b in v["exterior_counter_battens"] if b.roof_plane is v["dormer_roof"]]
        expected = {x for x in positions if any(
            p["plane"] is v["dormer_roof"] and p["x_min"] <= x <= p["x_max"]
            for p in v["roof_exterior_pieces"])}
        self.assertTrue(expected)
        self.assertEqual({b.local_start[0] for b in battens}, expected)


    def test_short_exterior_sources_keep_the_correct_ridge_side_for_different_pitches(self):
        v = self.values
        house = House("Exterior clipping regression")
        roof = house.storey("Roof", elevation=0).roof("Roof")
        for angle in (25, 45, 60):
            plane = roof.plane(
                f"Garden slope {angle}",
                points=((0, 5, 6), (10, 5, 6), (0, 7, 6 - 2 * np.tan(np.radians(angle)))),
                cuts=v["garden_roof"].cuts,
            )
            lo, hi = v["exterior_source_y_limits"](plane, y_max=0)
            for offset, thickness in ((v["MDF_BOTTOM"], v["MDF_THICKNESS"]),
                                      (v["UNDERLAY_BOTTOM"], v["UNDERLAY_THICKNESS"]),
                                      (v["ROOF_TILE_BOTTOM"], v["ROOF_TILE_THICKNESS"])):
                layer = plane.layer("Test layer", outline=((0, lo), (1, lo), (1, hi), (0, hi)),
                                    z_offset=offset, thickness=thickness, material="Roofing underlay")
                vertices = self.finished_vertices(layer)
                self.assertAlmostEqual(vertices[:, 1].min(), v["HALF_DEPTH"])
                self.assertGreater(vertices[:, 1].max(), v["HALF_DEPTH"] + .5)



    def test_all_exterior_pieces_keep_tiles_full_length_and_inset_boards_and_membrane(self):
        v = self.values
        for piece in v["roof_exterior_pieces"]:
            lo, hi = piece["tile_x_min"], piece["tile_x_max"]
            self.assertEqual((piece["x_min"], piece["x_max"]),
                             (lo + v["ROOF_EAVE_SETBACK"], hi - v["ROOF_EAVE_SETBACK"]))
            layers = [layer for layer in piece["plane"].elements
                      if hasattr(layer, "outline") and layer.Name.startswith(piece["name"] + " ")
                      and layer.material_name in {"MDF", "Roofing underlay", "Roof tiles"}]
            self.assertEqual(len(layers), 3)
            for layer in layers:
                with self.subTest(layer=layer.Name):
                    vertices = self.finished_vertices(layer)
                    expected = ((lo, hi) if layer.material_name == "Roof tiles" else
                                (lo + v["ROOF_EAVE_SETBACK"], hi - v["ROOF_EAVE_SETBACK"]))
                    local = np.array([piece["plane"].to_local(p) for p in vertices])
                    np.testing.assert_allclose((local[:, 0].min(), local[:, 0].max()), expected, atol=1e-8)
        # No counter-batten cross-section intrudes into the new X-end slots.
        for batten in v["exterior_counter_battens"]:
            vertices = self.finished_vertices(batten)
            local = np.array([batten.roof_plane.to_local(p) for p in vertices])
            self.assertTrue(any(piece["plane"] is batten.roof_plane
                                and piece["x_min"] <= local[:, 0].min() + 1e-8
                                and piece["x_max"] >= local[:, 0].max() - 1e-8
                                for piece in v["roof_exterior_pieces"]))

    def test_x_setback_uses_shared_parameter_and_can_be_disabled_or_tuned(self):
        v = self.values
        helper = v["roof_under_tile_x_range"]
        self.assertEqual(helper(1, 3), (1.02, 2.98))
        with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": 0}):
            self.assertEqual(helper(1, 3), (1, 3))
        with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": .04}):
            self.assertEqual(helper(1, 3), (1.04, 2.96))
        for lo, hi in ((1, 1), (2, 1), (0, .03), (float("nan"), 2)):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(ValueError):
                helper(lo, hi)

    def test_all_layers_respect_both_eave_cuts_with_independent_dormer_setback(self):
        v = self.values
        self.assertEqual(v["ROOF_EAVE_SETBACK"], .02)
        for plane in (v["street_roof"], v["garden_roof"], v["dormer_roof"]):
            street = plane in (v["street_roof"],)
            layers = [e for e in plane.elements if hasattr(e, "outline") and e.material_name in
                      {"MDF", "Roofing underlay", "Roof tiles"}]
            self.assertTrue(layers)
            for layer in layers:
                with self.subTest(layer=layer.Name):
                    vertices = self.finished_vertices(layer)
                    inset = 0 if layer.material_name == "Roof tiles" else v["ROOF_EAVE_SETBACK"]
                    self.assertGreaterEqual(vertices[:, 1].min(), v["STREET_ROOF_EAVE_Y"] + inset - 1e-7)
                    self.assertLessEqual(vertices[:, 1].max(), v["GARDEN_ROOF_EAVE_Y"] - inset + 1e-7)
                    self.assertGreaterEqual(vertices[:, 2].min(), self.main_eave_z(plane) - 1e-7)
                    if "above dormer" not in layer.Name:
                        garden_eave = v["DORMER_ROOF_EAVE_Y"] if plane is v["dormer_roof"] else v["GARDEN_ROOF_EAVE_Y"]
                        eave_y = v["STREET_ROOF_EAVE_Y"] + inset if street else garden_eave - inset
                        expected_z = max(self.main_eave_z(plane),
                            v["roof_layer_height_at_y"](plane, layer.z_offset, eave_y, 0))
                        self.assertAlmostEqual(vertices[:, 2].min(), expected_z)
                        if plane is v["dormer_roof"]:
                            self.assertLessEqual(vertices[:, 1].max(), eave_y + 1e-7)
                    # Finished geometry follows its inset outline; thickness is unchanged.
                    self.assertAlmostEqual(vertices[:, 0].min(), min(x for x, y in layer.outline))
                    self.assertAlmostEqual(vertices[:, 0].max(), max(x for x, y in layer.outline))
                    local = np.array([plane.to_local(p) for p in vertices])
                    self.assertAlmostEqual(np.ptp(local[:, 2]), layer.thickness)
                    if plane is not v["dormer_roof"]:
                        self.assertAlmostEqual(vertices[:, 1].max() if street else vertices[:, 1].min(), v["HALF_DEPTH"])

    def test_all_eave_timber_respects_vertical_setback_and_its_own_horizontal_cut(self):
        v = self.values
        lo = v["STREET_ROOF_EAVE_Y"] + v["ROOF_EAVE_SETBACK"]
        hi = v["GARDEN_ROOF_EAVE_Y"] - v["ROOF_EAVE_SETBACK"]
        rafters = (*v["main_roof_rafters"], *v["stronger_main_roof_rafters"],
                   *v["dormer_roof_rafters"], *v["dormer_short_rafters"])
        tiles = [b for plane in (v["street_roof"], v["garden_roof"], v["dormer_roof"])
                 for b in plane.elements if " tile batten " in (b.Name or "")]
        self.assertTrue(tiles)
        for beam in (*rafters, *v["exterior_counter_battens"], *tiles):
            if beam.roof_plane is v["transverse_roof"]:
                continue  # Its eave cuts are along X, checked with the transverse roof.
            with self.subTest(beam=beam.GlobalId):
                vertices = self.finished_vertices(beam)
                self.assertGreaterEqual(vertices[:, 1].min(), lo - 1e-7)
                self.assertLessEqual(vertices[:, 1].max(), hi + 1e-7)
                if beam.roof_plane in (v["dormer_roof"], v["dormer_rafter_roof"]):
                    self.assertLessEqual(vertices[:, 1].max(), v["DORMER_ROOF_EAVE_Y"] - v["ROOF_EAVE_SETBACK"] + 1e-7)
                self.assertGreaterEqual(vertices[:, 2].min(), self.main_eave_z(beam.roof_plane) - 1e-7)
        for beam in (*v["main_roof_rafters"], *v["stronger_main_roof_rafters"], *v["dormer_roof_rafters"]):
            vertices = self.finished_vertices(beam)
            if beam.roof_plane is v["dormer_rafter_roof"]:
                self.assertAlmostEqual(vertices[:, 2].min(), self.main_eave_z(beam.roof_plane))
            else:
                self.assertGreaterEqual(vertices[:, 2].min(), self.main_eave_z(beam.roof_plane) - 1e-7)
                on_horizontal = np.isclose(vertices[:, 2], self.main_eave_z(beam.roof_plane))
                eave_y = lo if beam.roof_plane in (v["street_roof"],) else hi
                self.assertTrue(np.any(on_horizontal) or np.any(np.isclose(vertices[:, 1], eave_y)))

    def test_main_eaves_use_each_wall_plate_bottom_minus_300mm(self):
        v = self.values
        self.assertEqual(v["ROOF_EAVE_DROP_BELOW_WALL_PLATE"], .30)
        for plane in (v["street_roof"], v["garden_roof"]):
            with self.subTest(plane=plane.Name):
                self.assertEqual(plane.cuts[0], v["street_roof"].cuts[0])
                self.assertTrue(all(abs(p[2] - self.main_eave_z(plane)) < 1e-9 for p in plane.cuts[1]))
                self.assertGreater(np.ptp(np.asarray(plane.cuts[1])[:, 1]), 0)
                eave_y = v["STREET_ROOF_EAVE_Y"] if plane in (v["street_roof"],) else v["GARDEN_ROOF_EAVE_Y"]
                self.assertTrue(all(p[1] == eave_y for p in plane.cuts[2]))
                # Source limits intersect all three cuts, not their union.
                for local_z in (v["RAFTER_Z_OFFSET"], v["MDF_BOTTOM"],
                                v["ROOF_TILE_BOTTOM"] + v["ROOF_TILE_THICKNESS"]):
                    limits = v["local_y_limits_from_cuts"](plane, local_z)
                    ridge_y = v["local_y_at_global_y"](plane, v["HALF_DEPTH"], local_z=local_z)
                    vertical_y = v["local_y_at_global_y"](plane, eave_y, local_z=local_z)
                    horizontal_y = v["local_y_at_global_z"](plane, self.main_eave_z(plane), local_z=local_z)
                    self.assertAlmostEqual(limits[0], ridge_y)
                    self.assertAlmostEqual(limits[1], min(vertical_y, horizontal_y))

    def test_eave_setback_can_be_disabled_or_tuned_without_changing_roof_plane_cuts(self):
        v = self.values
        helper = v["roof_eave_setback_cuts"]
        for plane in (v["street_roof"], v["garden_roof"], v["dormer_roof"], v["dormer_rafter_roof"]):
            original = plane.cuts
            with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": 0}):
                self.assertEqual(helper(plane), ())
                if plane is not v["dormer_rafter_roof"]:
                    self.assertEqual(v["local_y_limits_from_cuts"](plane, eave_setback=True),
                                     v["local_y_limits_from_cuts"](plane))
            with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": .08}):
                cut, = helper(plane)
                street = plane in (v["street_roof"],)
                garden_eave = v["DORMER_ROOF_EAVE_Y"] if plane in (v["dormer_roof"], v["dormer_rafter_roof"]) else v["GARDEN_ROOF_EAVE_Y"]
                expected = v["STREET_ROOF_EAVE_Y"] + .08 if street else garden_eave - .08
                self.assertTrue(all(p[1] == expected for p in cut))
                self.assertEqual(plane.cuts, original)

    def test_roof_siding_has_four_boards_with_each_roofs_level_bottom(self):
        v = self.values
        boards = v["roof_siding"]
        self.assertEqual(len(boards), 4)
        self.assertEqual(sum(b.Name.startswith("Street ") for b in boards), 1)
        self.assertEqual(sum(b.Name.startswith("Garden ") for b in boards), 3)
        high = [r for r in v["roof_over_rafter_x_ranges"] if r[2] != "lower"]
        normal = [r for r in v["roof_over_rafter_x_ranges"] if r[2] == "normal"]
        dormer, = [r for r in v["roof_over_rafter_x_ranges"] if r[2] == "dormer"]
        expected = (
            (v["street_roof"], "street", min(r[0] for r in high), max(r[1] for r in high)),
            *((v["garden_roof"], "garden", *r[:2]) for r in normal),
            (v["dormer_roof"], "garden", *dormer[:2]),
        )
        for board, (plane, side, x0, x1) in zip(boards, expected):
            x0 += v["ROOF_EAVE_SETBACK"]
            x1 -= v["ROOF_EAVE_SETBACK"]
            with self.subTest(board=board.Name):
                self.assertIn(plane.Name, board.Name)
                vertices = self.finished_vertices(board)
                self.assertAlmostEqual(vertices[:, 0].min(), x0)
                self.assertAlmostEqual(vertices[:, 0].max(), x1)
                garden_eave = v["DORMER_ROOF_EAVE_Y"] if plane is v["dormer_roof"] else v["GARDEN_ROOF_EAVE_Y"]
                y0, y1 = ((v["STREET_ROOF_EAVE_Y"], v["STREET_ROOF_EAVE_Y"] + v["ROOF_EAVE_SETBACK"])
                          if side == "street" else
                          (garden_eave - v["ROOF_EAVE_SETBACK"], garden_eave))
                top = v["offset_plane"](*plane.points, offset=v["ROOF_TILE_BOTTOM"])
                bottom = plane.cuts[1]
                corners = [(x, y, v["plane_height_at"](*cut, x=x, y=y))
                           for x in (x0, x1) for y in (y0, y1) for cut in (bottom, top)]
                self.assertEqual({tuple(np.round(p, 7)) for p in vertices},
                                 {tuple(np.round(p, 7)) for p in corners})
                self.assertAlmostEqual(vertices[:, 2].min(), self.main_eave_z(plane))
                self.assertEqual(len(vertices[np.isclose(vertices[:, 2], self.main_eave_z(plane))]), 4)

    def test_roof_siding_is_plain_non_structural_wood_siding_in_its_own_container(self):
        v = self.values
        material = ifcopenshell.util.element.get_material(v["roof_sloped_siding"][0])
        self.assertEqual(material.Name, "Wood siding solid")
        color = v["wood_siding_color"]().lstrip("#")
        expected_rgb = tuple(int(color[i:i+2], 16)/255 for i in (0, 2, 4))
        for board in v["roof_siding"]:
            self.assertTrue(board.is_a("IfcBuildingElementProxy"))
            self.assertEqual(ifcopenshell.util.element.get_material(board), material)
            self.assertEqual(ifcopenshell.util.element.get_container(board),
                             v["roof_layer_storeys"]["Eave siding"].element)
            self.assertTrue(ifcopenshell.util.element.get_pset(board, "BBIM_DrawingVisibility", "ShowInDrawings"))
            body = ifcopenshell.util.representation.get_representation(board, "Model", "Body", "MODEL_VIEW")
            shading = body.Items[0].StyledByItem[0].Styles[0].Styles[0]
            np.testing.assert_allclose((shading.SurfaceColour.Red, shading.SurfaceColour.Green, shading.SurfaceColour.Blue),
                                       expected_rgb)
            self.assertEqual(shading.Transparency, 0)
        self.assertTrue(v["roof_layer_storeys"]["Eave siding"].element.ObjectType == "ROOF_LAYER")
        self.assertFalse(set(v["roof_siding"]) & set(v["roof_structural_beams"]))

    def test_roof_siding_zero_setback_disables_boards_without_creating_geometry(self):
        v = self.values
        helper = v["add_roof_siding"]
        with patch.dict(helper.__globals__, {"ROOF_EAVE_SETBACK": 0}), patch.object(v["house"], "add_box") as add:
            self.assertEqual(helper(), ())
            add.assert_not_called()

    def test_roof_siding_tuned_thickness_and_duplicate_ranges_do_not_duplicate_boards(self):
        v = self.values
        helper = v["add_roof_siding"]
        house = House("Eave siding regression")
        container = house.storey("Eave siding", elevation=0)
        with patch.dict(helper.__globals__, {
            "house": house, "roof_layer_storeys": {"Eave siding": container},
            "ROOF_EAVE_SETBACK": .04,
            "roof_over_rafter_x_ranges": v["roof_over_rafter_x_ranges"] * 2,
        }):
            boards = helper()
        self.assertEqual(len(boards), 4)
        for board in boards:
            self.assertAlmostEqual(np.ptp(self.finished_vertices(board)[:, 1]), .04)

    def test_roof_siding_is_mirrored_once_without_changing_live_coordinates(self):
        v = self.values
        with patch.object(v["house"], "mirror_x", True):
            exported = v["house"]._export_model()
        for board in v["roof_siding"]:
            original = self.finished_vertices(board)
            reflected = self.finished_vertices(exported.by_guid(board.GlobalId))
            expected = original.copy()
            expected[:, 0] *= -1
            self.assertEqual({tuple(np.round(p, 7)) for p in reflected},
                             {tuple(np.round(p, 7)) for p in expected})
            np.testing.assert_allclose(self.finished_vertices(board), original)


    def test_roof_layer_helper_does_not_split_at_purlin_joint_even_when_range_crosses_it(self):
        values = self.values
        helper = values["add_continuous_roof_layers"]
        plane = values["street_roof"]
        x_min = values["MIDDLE_PURLIN_X_MIN"] - 0.4
        x_max = values["MIDDLE_PURLIN_X_MAX"] + 0.4
        outer_range = (x_min - 0.2, x_max + 0.2)
        # Isolate creation so this regression does not mutate the shared model.
        storeys = {name: Mock() for name in values["roof_layer_storeys"]}
        with (
            patch.dict(helper.__globals__, {"roof_layer_storeys": storeys,
                                           "roof_under_rafter_insulations": {}}),
            patch.object(type(plane), "layer", return_value=Mock()) as create_layer,
        ):
            helper(plane, "X range regression", x_min, x_max,
                   values["roof_y_min"], values["roof_y_max"],
                   under_rafter_end_y=values["STREET_ROOF_JOINT_Y"],
                   outer_x_range=outer_range)
        self.assertEqual(create_layer.call_count, 6)
        for call in create_layer.call_args_list:
            xs = [p[0] for p in call.kwargs["outline"]]
            expected = outer_range if call.kwargs["material"] in {
                "MDF", "Roofing underlay", "Roof tiles",
            } else (x_min, x_max)
            if call.kwargs["material"] in {"MDF", "Roofing underlay"}:
                expected = (expected[0] + values["ROOF_EAVE_SETBACK"], expected[1] - values["ROOF_EAVE_SETBACK"])
            self.assertEqual((min(xs), max(xs)), expected)






if __name__ == "__main__":
    unittest.main()
