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
        self.assertEqual(len(beams), 7)
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
            self.assertFalse(any(beam.source_wall == v[name] for beam in beams))
            self.assertFalse(ifcopenshell.util.element.get_pset(v[name], "BBIM_Boolean", "Data"))

    def test_front_and_back_are_split_at_the_configured_x_with_low_right_side(self):
        v = self.values
        x, width, depth = v["LOWER_NADEZDIVKA_X"], v["HOUSE_WIDTH"], v["HOUSE_DEPTH"]
        self.assertTrue(v["wall3_x"] < x < width)
        self.assertNotIn("wall_front_u", v)
        self.assertNotIn("wall_back_u", v)
        for name, start, end, height in (
            ("wall_front1_u", (0, 0), (x, 0), v["NADEZDIVKA"]),
            ("wall_front2_u", (x, 0), (width, 0), v["LOWER_NADEZDIVKA"]),
            ("wall_back1_u", (x, depth), (0, depth), v["NADEZDIVKA"]),
            ("wall_back2_u", (width, depth), (x, depth), v["LOWER_NADEZDIVKA"]),
        ):
            wall = v[name]
            with self.subTest(wall=name):
                self.assertEqual(wall.start, start)
                self.assertEqual(wall.end, end)
                self.assertAlmostEqual(wall.height, height)
                self.assertAlmostEqual(wall.start_height, 0)
        self.assertAlmostEqual(v["wall_4_u"].height, v["LOWER_NADEZDIVKA"])
        settings = ifcopenshell.geom.settings()
        for name in ("wall_front2_u", "wall_back2_u", "wall_4_u"):
            shape = ifcopenshell.geom.create_shape(settings, v[name])
            vertices = np.array(shape.geometry.verts).reshape(-1, 3)
            self.assertAlmostEqual(np.ptp(vertices[:, 2]), v["LOWER_NADEZDIVKA"])

    def test_storage_window_removed_but_roof_planes_and_plate_levels_stay_high(self):
        v = self.values
        self.assertNotIn("window_sklad", v)
        self.assertFalse(v["wall_4_u"].HasOpenings)
        self.assertFalse(v["wall_4_u"]._openings)
        expected_bottom = v["UPPER_FLOOR_START"] + v["NADEZDIVKA"]
        for plate in (v["beam3"], v["beam4_a"], v["beam4_b"]):
            self.assertAlmostEqual(plate.start[2] - plate.height / 2, expected_bottom)
        self.assertAlmostEqual(v["STREET_ROOF_PLANE_POINTS"][2][2], expected_bottom + .12)
        self.assertAlmostEqual(v["GARDEN_ROOF_PLANE_POINTS"][2][2], expected_bottom + .12)

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


class FacadeCornerTests(unittest.TestCase):
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

    def test_full_front_and_side_facades_meet_with_front_polystyrene_extended(self):
        v = self.values
        self.assertEqual(len(v["house"]._drawings), 2)
        for drawing in v["house"]._drawings:
            ground_plan = drawing.name == "Drawing 1"
            fronts, side = (((v["wall_front_g"],), v["wall_1_g"]) if ground_plan
                            else ((v["wall_front1_u"], v["wall_front2_u"]), v["wall_1_u"]))
            strips = [ifcopenshell.util.element.get_pset(a, "BBIM_WallInsulation")
                      for a in drawing.group.IsGroupedBy[0].RelatedObjects]
            strips = [p for p in strips if p]
            for wall, material in (*((front, "polystyrene") for front in fronts), (side, "rockwool")):
                with self.subTest(drawing=drawing.name, material=material):
                    matching = [p for p in strips if p["HostWall"] == wall.GlobalId and p["Material"] == material]
                    self.assertTrue(matching)
                    tangent = (np.array(wall.end) - wall.start) / wall.length
                    for properties in matching:
                        start = np.array(wall.start) - tangent * properties["StartExtension"]
                        end = np.array(wall.end) + tangent * properties["EndExtension"]
                        if material == "polystyrene":
                            minimum = (-v["ROCKWOOL_INSULATION_THICKNESS"] if wall == fronts[0]
                                       else v["LOWER_NADEZDIVKA_X"])
                            maximum = (v["HOUSE_WIDTH"] + v["POLYSTYRENE_INSULATION_THICKNESS"] if wall == fronts[-1]
                                       else v["LOWER_NADEZDIVKA_X"])
                            self.assertAlmostEqual(min(start[0], end[0]), minimum)
                            self.assertAlmostEqual(max(start[0], end[0]), maximum)
                            self.assertAlmostEqual(start[1], 0)
                            self.assertAlmostEqual(end[1], 0)
                        else:
                            # The wool stops at y=0: no gap or double-thickness
                            # overlap with the front strip at the outside corner.
                            self.assertAlmostEqual(min(start[1], end[1]), 0)
                            self.assertAlmostEqual(max(start[1], end[1]), v["HOUSE_DEPTH"] + .01)
                            self.assertAlmostEqual(start[0], 0)
                            self.assertAlmostEqual(end[0], 0)


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
        self.assertEqual(len(table["items"]), 6)
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
        self.assertEqual(len(legends[0][0]["items"]), 13)
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

    def test_bb_outside_wall_insulation_matches_facade_materials(self):
        values = self.values
        drawing = next(d for d in values["house"]._drawings if d.name == "bb")
        annotations = drawing.group.IsGroupedBy[0].RelatedObjects
        insulation = [
            (a, ifcopenshell.util.element.get_pset(a, "BBIM_WallInsulation"))
            for a in annotations
            if ifcopenshell.util.element.get_pset(a, "BBIM_WallInsulation")
        ]
        self.assertEqual(len(insulation), 4)
        expected = {
            (values["wall_1a_g"].GlobalId, "rockwool"): values["ROCKWOOL_INSULATION_THICKNESS"],
            (values["wall_4_u"].GlobalId, "polystyrene"): values["POLYSTYRENE_INSULATION_THICKNESS"],
            (values["wall_1a_g"].GlobalId, "xps"): values["EXTERIOR_XPS_INSULATION_THICKNESS"],
            (values["wall_4_u"].GlobalId, "xps"): values["EXTERIOR_XPS_INSULATION_THICKNESS"],
        }
        self.assertEqual({(p["HostWall"], p["Material"]) for _, p in insulation}, set(expected))
        for annotation, properties in insulation:
            key = (properties["HostWall"], properties["Material"])
            self.assertAlmostEqual(properties["Thickness"], expected[key])
            self.assertEqual(properties["Side"], "right")
            if properties["Material"] == "xps":
                self.assertEqual((properties["StartZ"], properties["EndZ"]), (-1, 0.3))
            else:
                self.assertEqual(properties["StartZ"], 0.3)
                self.assertGreater(properties["EndZ"],
                                   values["UPPER_FLOOR_START"] + values["OUTER_SUPPORT_WALL_HEIGHT"])
            if properties["Material"] == "rockwool":
                self.assertEqual(annotation.ObjectType, "BATTING")
                self.assertLess(properties["BattingThickness"], properties["Thickness"])

    def test_bb_facade_insulation_has_no_gap_for_removed_storage_window(self):
        values = self.values
        drawing = next(d for d in values["house"]._drawings if d.name == "bb")
        wall = values["wall_4_u"]
        self.assertFalse(wall._openings)
        annotations = drawing.group.IsGroupedBy[0].RelatedObjects
        strips = [ifcopenshell.util.element.get_pset(a, "BBIM_WallInsulation") for a in annotations]
        strips = [p for p in strips if p and p["HostWall"] == wall.GlobalId
                  and p["Material"] == "polystyrene"]
        self.assertEqual(len(strips), 1)
        segments = json.loads(strips[0]["Segments"])
        self.assertTrue(segments)
        self.assertEqual(len(segments), 1)


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

    def test_roof_target_composes_one_a3_sheet_with_manual_centres_and_one_visible_schedule(self):
        v = self.values
        sheet = v["roof_sheet"]
        self.assertEqual((sheet.paper, sheet.orientation, sheet.width, sheet.height), ("A3", "portrait", 297, 420))
        items = sheet._drawings
        self.assertEqual([item.drawing for item in items], [v["roof_plan"], v["roof_xx"], v["roof_yy"], v["roof_zz"]])
        self.assertEqual([(item.x, item.y) for item in items], [(.5, .25), (.25, .64), (.74, .75), (.25, .87)])
        self.assertEqual([item.tables for item in items], [True, False, False, False])
        self.assertEqual([item.crop for item in items], [False, True, True, True])
        self.assertEqual(self.sheet_rendered, ["roof.svg"])
        self.assertEqual(self.rendered, [])

    def test_yy_includes_chimney_without_including_the_ground_storey_or_other_sections(self):
        values = self.values
        for name in ("roof_xx", "roof_yy", "roof_zz"):
            with self.subTest(drawing=name):
                pset = ifcopenshell.util.element.get_pset(values[name].element, "EPset_Drawing")
                selected = ifcopenshell.util.selector.filter_elements(values["house"].model, pset["Include"])
                self.assertEqual(values["chimney"] in selected, name == "roof_yy")
                self.assertNotIn(values["wall_front_g"], selected)
        self.assertEqual(ifcopenshell.util.element.get_container(values["chimney"]), values["ground"].element)

    def test_rafter_span_dimensions_are_scoped_and_suppress_symmetric_duplicate(self):
        for name, count in (("roof_xx", 2), ("roof_yy", 3), ("roof_zz", 2)):
            with self.subTest(drawing=name):
                drawing = self.values[name]
                dimensions = [a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                              if a.ObjectType == "DIMENSION" and " rafter " in a.Name]
                self.assertEqual(len(dimensions), count)
                self.assertTrue(all(a.Name.startswith(name + " ") for a in dimensions))
                self.assertTrue(any(a.Name.endswith("purlin to ridge") for a in dimensions))
                self.assertEqual(sum(a.Name.endswith("wall plate to purlin") for a in dimensions), count - 1)
                self.assertTrue(all(ifcopenshell.util.element.get_pset(
                    a, "BBIM_Dimension", "CustomUnit") == ["Millimeters"] for a in dimensions))

    def test_rafter_span_dimensions_use_outer_top_support_corners_and_keep_ridge(self):
        v = self.values
        for name, street_plate, garden_plate, distance, width in (
            ("roof_xx", v["beam3"], v["beam4_a"], v["VAZNICE_SIDE_DIST"], v["VAZNICE_SIDE_BASE"]),
            ("roof_yy", v["beam3"], v["beam_dormer"], v["VAZNICE_DIST"], v["VAZNICE_BASE"]),
            ("roof_zz", v["beam3_lower"], v["beam4_lower"], v["VAZNICE_LOWER_DIST"], v["VAZNICE_LOWER_BASE"]),
        ):
            drawing = v[name]
            products = drawing.group.IsGroupedBy[0].RelatedObjects
            street_seat = (street_plate.start[1] - street_plate.width / 2,
                           street_plate.start[2] + street_plate.height / 2)
            garden_seat = (garden_plate.start[1] + garden_plate.width / 2,
                           garden_plate.start[2] + garden_plate.height / 2)
            rafter_x = v["rafter_x_position"](v["rafters"][v["roof_elevation_definitions"][name]["rafter_index"]])
            top = v["purlin_top_z_at"](rafter_x)
            street_support = (v["HALF_DEPTH"] - distance - width / 2, top)
            garden_support = (v["HALF_DEPTH"] + distance + width / 2, top)
            # Preserve the user's existing 60 mm ridge-point adjustment.
            axis_plane = v["offset_plane"](*v["framing_roof_planes_at"](rafter_x)[0].points,
                                           offset=v["ROOF_BATTING_CENTER_OFFSET"])
            ridge_y = v["HALF_DEPTH"] + 0.06
            ridge = (ridge_y, v["plane_height_at"](*axis_plane, x=0, y=ridge_y))
            expected = {
                "street rafter purlin to ridge": (street_support, ridge),
                "street rafter wall plate to purlin": (street_seat, street_support),
            }
            if name == "roof_yy":
                expected["garden rafter wall plate to purlin"] = (garden_seat, garden_support)
            for suffix, (first_point, second_point) in expected.items():
                with self.subTest(drawing=name, span=suffix):
                    dimension = next(a for a in products if a.Name == f"{name} {suffix}")
                    curve = dimension.Representation.Representations[0].Items[0]
                    first, second = np.asarray(curve.Points.CoordList)
                    length = np.linalg.norm(second - first)
                    expected_length = np.linalg.norm(np.subtract(second_point, first_point))
                    self.assertAlmostEqual(length, expected_length)
                    self.assertGreater(length, abs(second_point[0] - first_point[0]))
                    extension = next(a for a in products if a.Name == dimension.Name + " Extension Lines")
                    placement = ifcopenshell.util.placement.get_local_placement(extension.ObjectPlacement)
                    segments = extension.Representation.Representations[0].Items[0].Elements
                    for segment, expected_point in zip(segments, (first_point, second_point)):
                        local = segment.Points.CoordList[0]
                        point = placement @ np.array((*local, 0, 1))
                        np.testing.assert_allclose(point[:3], (drawing.x, *expected_point), atol=1e-9)

    def test_purlin_centre_spacing_dimensions_use_local_sections_and_sit_below_beams(self):
        v = self.values
        for name, distance, height in (
            ("roof_xx", v["VAZNICE_SIDE_DIST"], v["VAZNICE_SIDE_HEIGHT"]),
            ("roof_yy", v["VAZNICE_DIST"], v["VAZNICE_HEIGHT"]),
            ("roof_zz", v["VAZNICE_LOWER_DIST"], v["VAZNICE_LOWER_HEIGHT"]),
        ):
            with self.subTest(drawing=name):
                drawing = v[name]
                products = drawing.group.IsGroupedBy[0].RelatedObjects
                dimensions = [a for a in products if a.Name == f"{name} purlin centre spacing"]
                self.assertEqual(len(dimensions), 1)
                dimension = dimensions[0]
                self.assertEqual(dimension.ObjectType, "DIMENSION")
                curve = dimension.Representation.Representations[0].Items[0]
                points = np.asarray(curve.Points.CoordList)
                self.assertAlmostEqual(np.linalg.norm(points[1] - points[0]), 2 * distance)
                placement = ifcopenshell.util.placement.get_local_placement(dimension.ObjectPlacement)
                rafter_x = v["rafter_x_position"](v["rafters"][v["roof_elevation_definitions"][name]["rafter_index"]])
                centre_z = v["purlin_top_z_at"](rafter_x) - height / 2
                for point, y in zip(points, (v["HALF_DEPTH"] - distance, v["HALF_DEPTH"] + distance)):
                    world = placement @ np.array((*point, 0, 1))
                    np.testing.assert_allclose(world[:3], (drawing.x, y, centre_z - 0.5), atol=1e-9)
                extension = next(a for a in products if a.Name == dimension.Name + " Extension Lines")
                placement = ifcopenshell.util.placement.get_local_placement(extension.ObjectPlacement)
                curves = extension.Representation.Representations[0].Items[0].Elements
                for curve, y in zip(curves, (v["HALF_DEPTH"] - distance, v["HALF_DEPTH"] + distance)):
                    start = curve.Points.CoordList[0]
                    world = placement @ np.array((*start, 0, 1))
                    np.testing.assert_allclose(world[:3], (drawing.x, y, centre_z), atol=1e-9)

    def test_rafter_dimensions_mirror_with_the_section_camera(self):
        v = self.values
        exported = v["house"]._export_model()
        for name in ("roof_xx", "roof_yy", "roof_zz"):
            for dimension in v[name].group.IsGroupedBy[0].RelatedObjects:
                if dimension.ObjectType != "DIMENSION":
                    continue
                original = ifcopenshell.util.placement.get_local_placement(dimension.ObjectPlacement)
                mirrored = ifcopenshell.util.placement.get_local_placement(
                    exported.by_guid(dimension.GlobalId).ObjectPlacement)
                np.testing.assert_allclose(mirrored[:3, 3], original[:3, 3] * (-1, 1, 1), atol=1e-9)
                self.assertAlmostEqual(mirrored[0, 3], -v[name].x)

    def test_camera_is_before_selected_rafter_parallel_to_aa_and_mirrors_once(self):
        values = self.values
        drawing = values["roof_xx"]
        self.assertEqual(self.rendered, [])
        self.assertEqual(self.sheet_rendered, ["roof.svg"])
        self.assertEqual(len(values["house"]._drawings), 4)
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
        for name in ("Wood fiberboard", "Roofing underlay", "Roof tiles",
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
        self.assertEqual(set(markers), {"A", "B", "X", "Y", "Z"})
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


class LowerPurlinConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        cls.overrides = {
            "PURLIN_LOWER_WALL_TOP_HEIGHT": 2.60,
            "VAZNICE_LOWER_HEIGHT": .30,
            "VAZNICE_LOWER_BASE": .22,
            "VAZNICE_LOWER_DIST": .65,
        }
        cls.runs = []
        for overrides in ({}, cls.overrides):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id in overrides:
                        node.value = ast.Constant(overrides[target.id])
            ast.fix_missing_locations(tree)
            values = {"__file__": str(source), "__name__": "__main__"}
            with (
                patch.object(sys, "argv", [str(source)]),
                patch.object(House, "write", return_value=Path("house.ifc")),
                redirect_stdout(StringIO()) as output,
            ):
                exec(compile(tree, str(source), "exec"), values)
            cls.runs.append((values, output.getvalue()))

    def test_all_four_lower_parameters_position_both_right_purlins_independently(self):
        values = self.runs[1][0]
        for name, expected in self.overrides.items():
            self.assertEqual(values[name], expected)
        for side, sign in (("street", -1), ("garden", 1)):
            beam = values[side + "_purlins"][2]
            self.assertAlmostEqual(beam.start[0], values["wall3_x"] - values["BWT"])
            self.assertAlmostEqual(beam.end[0], values["HOUSE_WIDTH"] + .2)
            self.assertEqual((beam.width, beam.height), (.22, .30))
            self.assertAlmostEqual(beam.start[1], values["HALF_DEPTH"] + sign * .65)
            self.assertAlmostEqual(beam.start[2] - beam.height / 2,
                                   values["UPPER_FLOOR_START"] + 2.60)
            vertices = RoofFramingTests.finished_vertices(beam)
            self.assertAlmostEqual(vertices[:, 2].min(), values["UPPER_FLOOR_START"] + 2.60)
            self.assertAlmostEqual(vertices[:, 2].max(), values["UPPER_FLOOR_START"] + 2.90)

    def test_lower_angle_uses_outer_top_contacts_and_is_printed_for_each_configuration(self):
        for values, output in self.runs:
            beam = values["street_purlins"][2]
            contact_y = values["STREET_WALL_PLATE_Y"] - values["WALL_PLATE_SIZE"][0] / 2
            contact_z = values["UPPER_FLOOR_START"] + values["LOWER_NADEZDIVKA"] + values["WALL_PLATE_SIZE"][1]
            run = beam.start[1] - beam.width / 2 - contact_y
            rise = beam.start[2] + beam.height / 2 - contact_z
            expected = np.degrees(np.arctan2(rise, run))
            self.assertAlmostEqual(values["lower_roof_angle"], expected)
            self.assertIn(f"Lower roof angle: {expected:.2f}°", output)
        self.assertNotAlmostEqual(self.runs[0][0]["lower_roof_angle"], self.runs[1][0]["lower_roof_angle"])

    def test_lower_tuning_leaves_high_purlins_walls_and_existing_roof_unchanged(self):
        original, tuned = (run[0] for run in self.runs)
        for name in ("STREET_ROOF_PLANE_POINTS", "GARDEN_ROOF_PLANE_POINTS", "DORMER_ROOF_PLANE_POINTS"):
            self.assertEqual(original[name], tuned[name])
        for side in ("street", "garden"):
            for before, after in zip(original[side + "_purlins"][:2], tuned[side + "_purlins"][:2]):
                self.assertEqual((before.start, before.end, before.width, before.height),
                                 (after.start, after.end, after.width, after.height))
        for name in ("wall_2", "wall_3", "wall_4_u"):
            self.assertEqual(original[name].height, tuned[name].height)
            self.assertEqual(original[name]._recesses, tuned[name]._recesses)
            self.assertEqual(original[name]._openings, tuned[name]._openings)
        for name in ("beam3", "beam4_a", "beam4_b", "beam_dormer"):
            self.assertEqual(original[name].start, tuned[name].start)
            self.assertEqual(original[name].end, tuned[name].end)
        for before, after in zip(original["collar_ties"], tuned["collar_ties"]):
            if before.start[0] < original["LOWER_NADEZDIVKA_X"]:
                self.assertEqual((before.start, before.end), (after.start, after.end))


class IndependentInteriorRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if name == "roof_under_rafter_x_ranges":
                node.value.elts = [node.value.elts[i] for i in (2, 0, 1)]
            elif name == "roof_over_rafter_x_ranges":
                node.value.elts.append(ast.parse('(HOUSE_WIDTH-.50, HOUSE_WIDTH-.25, "normal")', mode="eval").body)
            elif name == "LOWER_CEILING_CLEAR_HEIGHT":
                node.value = ast.Constant(2.25)
            elif name == "aa_cut":
                for keyword in node.value.keywords:
                    if keyword.arg in ("start", "end"):
                        keyword.value.elts[0] = ast.parse('(wall3_x + HOUSE_WIDTH - BWT) / 2', mode="eval").body
        ast.fix_missing_locations(tree)
        values = {"__file__": str(source), "__name__": "__main__"}
        with (
            patch.object(sys, "argv", [str(source), "aa"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")),
            redirect_stdout(StringIO()),
        ):
            exec(compile(tree, str(source), "exec"), values)
        cls.values = values

    def test_reordered_inner_profiles_and_different_outer_count_are_independent(self):
        v = self.values
        self.assertEqual(len(v["roof_under_rafter_x_ranges"]), 3)
        self.assertEqual(len(v["roof_over_rafter_x_ranges"]), 5)
        self.assertEqual([profile for _, _, profile in v["roof_under_rafter_x_ranges"]],
                         ["lower", "normal", "dormer"])
        for segment, (lo, hi, name) in enumerate(v["roof_under_rafter_x_ranges"]):
            profile = v["roof_inner_profiles"][name]
            for key in ("street_plane", "garden_plane", "flat_plane"):
                layers = [e for e in profile[key].elements if hasattr(e, "outline")
                          and e.Name.endswith(f"segment {segment} vapour barrier")]
                self.assertEqual(len(layers), 1)
                vertices = RoofFramingTests.finished_vertices(layers[0])
                self.assertAlmostEqual(vertices[:, 0].min(), lo)
                self.assertAlmostEqual(vertices[:, 0].max(), hi)
        self.assertEqual(len([e for e in v["street_roof"].elements
                              if getattr(e, "material_name", None) == "Roofing underlay"]), 4)

    def test_aa_under_rafter_symbols_use_lower_profile_and_lower_layer_owners(self):
        v = self.values
        self.assertEqual(v["aa_inner_segment"], 0)
        self.assertEqual(v["aa_inner_profile_name"], "lower")
        self.assertAlmostEqual(v["horizontal_batting_center_z"],
                               v["LOWER_ROOF_JOINT_Z"] + v["THERMAL_INSULATION_UNDER_RAFTERS"] / 2)
        self.assertAlmostEqual(v["aa_purlin_distance"], v["VAZNICE_LOWER_DIST"])
        for side in ("street", "garden"):
            label = side.title()
            annotation = next(a for a in v["house"].model.by_type("IfcAnnotation")
                              if a.Name == f"AA {side} under-rafter batting")
            classes = ifcopenshell.util.element.get_pset(annotation, "EPset_Annotation", "Classes")
            owner = v["roof_under_rafter_insulations"][f"{label} segment 0"]
            self.assertIn(f"under-rafter-owner-{owner.GlobalId}", classes)
        lower_gypsum = next(e for e in v["lower_flat_ceiling_roof"].elements
                            if getattr(e, "material_name", None) == "Gypsum plasterboard")
        self.assertAlmostEqual(RoofFramingTests.finished_vertices(lower_gypsum)[:, 2].min(),
                               v["UPPER_FLOOR_START"] + v["UPPER_FLOOR_THICKNESS"] + 2.25)
        self.assertAlmostEqual(v["interior_ceiling_bottom_z_at"](v["aa_x"]),
                               v["UPPER_FLOOR_START"] + v["UPPER_FLOOR_THICKNESS"] + 2.25)


class ExteriorOverlapDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "aa_cut":
                for keyword in node.value.keywords:
                    if keyword.arg in ("start", "end"):
                        keyword.value.elts[0] = ast.parse('LOWER_NADEZDIVKA_X + .1', mode="eval").body
        ast.fix_missing_locations(tree)
        values = {"__file__": str(source), "__name__": "__main__"}
        with (
            patch.object(sys, "argv", [str(source), "aa"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")),
            redirect_stdout(StringIO()),
        ):
            exec(compile(tree, str(source), "exec"), values)
        cls.values = values

    def test_all_overlap_profiles_and_planes_are_returned_independent_of_list_order(self):
        v = self.values
        x = v["aa_x"]
        self.assertEqual({name for _, name in v["exterior_roof_sections_at"](x)}, {"normal", "lower"})
        self.assertEqual(set(v["exterior_roof_planes_at"](x, side="street")),
                         {v["street_roof"], v["lower_street_roof"]})
        self.assertEqual(set(v["exterior_roof_planes_at"](x, side="garden")),
                         {v["garden_roof"], v["lower_garden_roof"]})
        selector = v["exterior_roof_sections_at"]
        with patch.dict(selector.__globals__, {"roof_over_rafter_x_ranges": tuple(reversed(v["roof_over_rafter_x_ranges"]))}):
            self.assertEqual({name for _, name in selector(x)}, {"normal", "lower"})
            self.assertEqual(len(v["exterior_ridge_planes_at"](x)), 2)
        with self.assertRaisesRegex(ValueError, "roof side"):
            v["exterior_roof_planes_at"](x, side="wrong")

    def test_overlap_view_has_both_roof_angles_composition_markers_and_ridge_caps(self):
        v = self.values
        annotations = v["house"].model.by_type("IfcAnnotation")
        angles = {a.Name: ifcopenshell.util.element.get_pset(a, "BBIM_AngleDimension")
                  for a in annotations if ifcopenshell.util.element.get_pset(a, "BBIM_AngleDimension")}
        self.assertEqual(set(angles), {"AA main roof angle", "AA lower roof angle"})
        self.assertAlmostEqual(angles["AA main roof angle"]["AngleDegrees"], v["street_roof_angle"])
        self.assertAlmostEqual(angles["AA lower roof angle"]["AngleDegrees"], v["lower_roof_angle"])
        names = {a.Name for a in annotations}
        self.assertTrue({"AA roof composition SK3", "AA lower roof composition SK3",
                         "AA ridge tile", "AA lower ridge tile"}.issubset(names))
        self.assertEqual(len(v["aa_ridge_tiles"]), 2)
        self.assertEqual(v["aa_inner_profile_name"], "lower")
        self.assertAlmostEqual(v["interior_ceiling_bottom_z_at"](v["aa_x"]),
                               v["UPPER_FLOOR_START"] + v["UPPER_FLOOR_THICKNESS"] + v["LOWER_CEILING_CLEAR_HEIGHT"])


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
        self.assertEqual(sum((beam.Name or "").startswith("Collar tie ") for beam in beams), 32)
        self.assertIn("Collar ties", self.values["roof_layer_storeys"])
        self.assertTrue(
            any(
                "Collar ties" in (storey.Name or "")
                for storey in model.by_type("IfcBuildingStorey")
            )
        )
        self.assertTrue(self.values["main_roof_rafters"])
        self.assertEqual(len(self.values["street_purlins"]), 3)
        self.assertEqual(len(self.values["garden_purlins"]), 3)
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
        purlin_guids = {b.GlobalId for b in (*values["street_purlins"], *values["garden_purlins"])}
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

    def test_independent_purlins_overlap_with_lowered_right_pieces_and_no_gerber_joints(self):
        values = self.values
        self.assertNotIn("GERBER_JOINT_1", values)
        self.assertNotIn("GERBER_JOINT_2", values)
        self.assertNotIn("VAZNICE_EXTRA_HEIGHT", values)
        self.assertNotIn("add_purlin_wall_recess", values)
        self.assertFalse(values["wall_2"]._recesses)
        self.assertFalse(values["wall_3"]._recesses)
        for side in ("street", "garden"):
            beams = values[side + "_purlins"]
            self.assertEqual(len(beams), 3)
            for segment, beam in zip(("left", "middle", "right"), beams):
                width, height, distance = values["PURLIN_SECTION_DIMENSIONS"][segment]
                self.assertEqual((beam.width, beam.height), (width, height))
                top = (values["UPPER_FLOOR_START"] + values["PURLIN_LOWER_WALL_TOP_HEIGHT"] + height
                       if segment == "right" else values["PURLIN_TOP_Z"])
                self.assertAlmostEqual(beam.start[2] + beam.height / 2, top)
                self.assertAlmostEqual(beam.end[2], beam.start[2])
                self.assertAlmostEqual(abs(beam.start[1] - values["HALF_DEPTH"]), distance)
            left, middle, right = beams
            self.assertAlmostEqual(left.end[0], middle.start[0])
            self.assertGreater(middle.end[0], right.start[0])
            self.assertAlmostEqual(middle.start[0], values["wall2_x"] - values["BWT"] / 2)
            self.assertAlmostEqual(middle.end[0], values["LOWER_NADEZDIVKA_X"] + .2)
            self.assertAlmostEqual(right.start[0], values["wall3_x"] - values["BWT"])
            self.assertAlmostEqual(
                middle.length, values["LOWER_NADEZDIVKA_X"] + .2 - values["MIDDLE_PURLIN_X_MIN"]
            )
            self.assertAlmostEqual(left.start[0], -0.2)
            self.assertAlmostEqual(right.end[0], values["HOUSE_WIDTH"] + 0.2)
            self.assertAlmostEqual(left.length, values["MIDDLE_PURLIN_X_MIN"] + 0.2)
            self.assertAlmostEqual(
                right.length, values["HOUSE_WIDTH"] + 0.2 - (values["wall3_x"] - values["BWT"])
            )
            self.assertLess(right.start[2] + right.height / 2,
                            middle.start[2] - middle.height / 2)
        self.assertNotIn("add_purlin_sedla", values)
        self.assertNotIn("street_sedla", values)
        self.assertNotIn("garden_sedla", values)
        self.assertFalse(
            any("sedlo" in (beam.Name or "").lower() for beam in values["house"].model.by_type("IfcBeam"))
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
            middle_low, middle_high = bounds[1]
            right_low, right_high = bounds[2]
            overlap = min(middle_high[0], right_high[0]) - max(middle_low[0], right_low[0])
            self.assertAlmostEqual(overlap, values["LOWER_NADEZDIVKA_X"] + .2
                                   - (values["wall3_x"] - values["BWT"]))
            self.assertLess(right_high[2], middle_low[2])

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

    def test_left_gable_is_raised_but_right_outer_wall_is_low(self):
        values = self.values
        expected = values["PURLIN_WALL_TOP_HEIGHT"]
        for name in ("wall_2", "wall_3"):
            wall = values[name]
            self.assertAlmostEqual(wall.height, expected)
            self.assertFalse(wall._recesses)
            self.assertAlmostEqual(
                self.finished_vertices(wall)[:, 2].max(),
                values["UPPER_FLOOR_START"] + expected,
            )
        openings = values["house"].model.by_type("IfcOpeningElement")
        self.assertFalse(any("sedlo" in (opening.Name or "").lower() for opening in openings))
        self.assertIn(values["sklad_opening"], openings)
        self.assertEqual(len(values["wall_cuts_2_3"]), 2)
        self.assertAlmostEqual(
            self.finished_vertices(values["wall_1_u"])[:, 2].max(),
            values["PURLIN_TOP_Z"] - values["VAZNICE_SIDE_HEIGHT"],
        )
        self.assertAlmostEqual(
            self.finished_vertices(values["wall_4_u"])[:, 2].max(),
            values["UPPER_FLOOR_START"] + values["LOWER_NADEZDIVKA"],
        )

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
                self.assertAlmostEqual(vertices[:, 1].max(), values["GARDEN_ROOF_EAVE_Y"])
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

    def test_framing_level_selects_the_right_support_in_the_purlin_overlap(self):
        v = self.values
        step = v["LOWER_NADEZDIVKA_X"]
        for x, index, lower in ((step-.01, 1, False), (step, 2, True), (step+.01, 2, True)):
            self.assertEqual(v["framing_is_lower"](x), lower)
            for side in ("street", "garden"):
                self.assertIs(v["purlin_at"](x, side=side), v[side+"_purlins"][index])
            self.assertIs(v["wall_plate_at"](x, side="street"), v["beam3_lower"] if lower else v["beam3"])
        self.assertEqual(v["purlin_segment_at"](v["wall3_x"] + .1), "middle")
        with patch.dict(v["framing_is_lower"].__globals__, {"roof_under_rafter_x_ranges": (), "roof_over_rafter_x_ranges": ()}):
            self.assertTrue(v["framing_is_lower"](step+.1))
            self.assertIs(v["purlin_at"](step+.1, side="garden"), v["garden_purlins"][2])
        with patch.dict(v["framing_levels"], {step-.01: "lower", step+.01: "high"}):
            for x, index, lower in ((step-.01, 2, True), (step+.01, 1, False)):
                self.assertEqual(v["framing_is_lower"](x), lower)
                for side in ("street", "garden"):
                    self.assertIs(v["purlin_at"](x, side=side), v[side+"_purlins"][index])

    def test_explicit_framing_arrays_validate_unique_finite_main_positions(self):
        v = self.values
        build = v["framing_levels_from_arrays"]
        self.assertEqual(build([1, (2, "before"), v["StrongerRafter"](3)],
                               [1.5, v["SplitRafter"](4, 7)]),
                         {1: "high", 2: "high", 3: "high", 1.5: "lower", 4: "lower"})
        self.assertEqual(v["rafters"], v["high_rafters"] + v["lower_rafters"])
        for high, lower in (([1], [1]), ([1, (1, "before")], []),
                            ([True], []), ([], [float("nan")]), ([float("inf")], [])):
            with self.subTest(high=high, lower=lower), self.assertRaises(ValueError):
                build(high, lower)

    def test_touching_main_rafters_are_checked_separately_at_each_level(self):
        v = self.values
        with patch.dict(v["framing_levels"], {1.: "high", 1.04: "lower", 1.08: "high"}):
            self.assertEqual(v["touching_rafter_sides"]([(1., .08), (1.04, .08), (1.08, .08)]),
                             {(1., "right"), (1.08, "left")})
        with patch.dict(v["framing_levels"], {1.: "high", 1.08: "lower"}):
            self.assertEqual(v["touching_rafter_sides"]([(1., .08), (1.08, .08)]), set())

    def test_lower_assemblies_follow_the_lower_planes_and_support_contacts(self):
        v = self.values
        self.assertEqual(set(v["rafter_assemblies"]), set(v["main_rafter_positions"]))
        lower_xs = [x for x in v["main_rafter_positions"] if v["framing_is_lower"](x)]
        self.assertTrue(lower_xs)
        for x in lower_xs:
            assembly = v["rafter_assemblies"][x]
            rafters = [beam for beam in assembly if beam.kind == "RAFTER"]
            self.assertEqual(len(rafters), 2)
            self.assertEqual(len(assembly), 5)  # two rafters, two ties, one spacer
            for side in ("street", "garden"):
                plane = v["lower_"+side+"_roof"]
                rafter = next(beam for beam in rafters if beam.roof_plane is plane)
                vertices = self.finished_vertices(rafter)
                local = np.array([plane.to_local(vertex) for vertex in vertices])
                self.assertAlmostEqual(local[:, 2].min(), v["RAFTER_Z_OFFSET"])
                self.assertAlmostEqual(local[:, 2].max(), v["RAFTER_Z_OFFSET"] + rafter.height)
                if side == "street":
                    self.assertAlmostEqual(vertices[:, 1].min(), v["STREET_ROOF_EAVE_Y"])
                    self.assertAlmostEqual(vertices[:, 1].max(), v["HALF_DEPTH"])
                else:
                    self.assertAlmostEqual(vertices[:, 1].min(), v["HALF_DEPTH"])
                    self.assertAlmostEqual(vertices[:, 1].max(), v["GARDEN_ROOF_EAVE_Y"])
                for support in (v["purlin_at"](x, side=side), v["wall_plate_at"](x, side=side)):
                    contact = (x, support.start[1] + (-1 if side == "street" else 1) * support.width/2,
                               support.start[2] + support.height/2)
                    point = plane.to_local(contact)
                    self.assertAlmostEqual(point[2], 0)
                    self.assertGreaterEqual(point[1], local[:, 1].min()-1e-8)
                    self.assertLessEqual(point[1], local[:, 1].max()+1e-8)
            for tie in (beam for beam in assembly if (beam.Name or "").startswith("Collar tie")):
                self.assertAlmostEqual(self.finished_vertices(tie)[:, 2].min(), v["LOWER_ROOF_JOINT_Z"])
                self.assertEqual((tie.width, tie.height), v["COLLAR_TIE_SIZE"])
            spacer = next(beam for beam in assembly if (beam.Name or "").startswith("Purlin spacer"))
            self.assertAlmostEqual(spacer.length, 2 * (v["VAZNICE_LOWER_DIST"] - v["VAZNICE_LOWER_BASE"]/2))
            self.assertAlmostEqual(self.finished_vertices(spacer)[:, 2].max(), v["LOWER_ROOF_JOINT_Z"])

    def test_split_wall_plates_sit_on_their_wall_levels_and_cover_both_roof_sides(self):
        v = self.values
        self.assertEqual(len(v["roof_wall_plates"]), 6)
        for high, low, plane in ((v["beam3"], v["beam3_lower"], v["lower_street_roof"]),
                                  (v["beam4_b"], v["beam4_lower"], v["lower_garden_roof"])):
            self.assertAlmostEqual(high.end[0], v["LOWER_NADEZDIVKA_X"] + .2)
            self.assertAlmostEqual(low.start[0], v["LOWER_NADEZDIVKA_X"])
            self.assertAlmostEqual(low.end[0], v["HOUSE_WIDTH"] + .2)
            self.assertAlmostEqual(low.start[2] - low.height/2, v["UPPER_FLOOR_START"] + v["LOWER_NADEZDIVKA"])
            self.assertAlmostEqual(high.start[2] - high.height/2, v["UPPER_FLOOR_START"] + v["NADEZDIVKA"])
        for x in v["main_rafter_positions"]:
            plates = v["assembly_wall_plates"](x)
            self.assertIn(v["wall_plate_at"](x, side="street"), plates)
            if v["framing_is_lower"](x):
                self.assertEqual(set(plates), {v["beam3_lower"], v["beam4_lower"]})

    def test_short_garden_wall_plate_ends_with_the_middle_purlin(self):
        v = self.values
        plate = v["beam4_b"]
        self.assertAlmostEqual(plate.start[0], v["wall3_x"])
        self.assertAlmostEqual(plate.end[0], v["LOWER_NADEZDIVKA_X"] + .2)
        self.assertAlmostEqual(plate.end[0], v["garden_purlins"][1].end[0])
        self.assertIs(v["wall_plate_at"](v["LOWER_NADEZDIVKA_X"] + .1, side="garden"),
                      v["beam4_lower"])

    def test_high_street_wall_plate_ends_with_the_middle_purlin_and_covers_overlap(self):
        v = self.values
        plate = v["beam3"]
        self.assertAlmostEqual(plate.end[0], v["LOWER_NADEZDIVKA_X"] + .2)
        self.assertAlmostEqual(plate.end[0], v["street_purlins"][1].end[0])
        self.assertAlmostEqual(plate.end[0], v["beam4_b"].end[0])
        x = v["LOWER_NADEZDIVKA_X"] + .105
        with patch.dict(v["framing_levels"], {x: "high"}):
            self.assertIs(v["wall_plate_at"](x, side="street"), plate)

    def test_measured_schedule_lists_each_split_plate_and_framing_member_once(self):
        v = self.values
        rows = v["timber_schedule_rows"]
        scheduled = [member.GlobalId for _, members, _, _ in rows for member in members]
        self.assertEqual(len(scheduled), len(set(scheduled)))
        for _, members, _, _ in rows:
            self.assertEqual(len({(round(m.width*1000), round(m.height*1000), round(m.finished_length()*1000)) for m in members}), 1)
        for member in (*v["roof_wall_plates"], *v["collar_ties"], *v["purlin_spacers"],
                       *v["main_roof_rafters"], *v["stronger_main_roof_rafters"]):
            self.assertIn(member.GlobalId, scheduled)
        for plate in (v["beam3_lower"], v["beam4_lower"]):
            settings = next(settings for _, members, _, settings in rows if plate in members)
            self.assertEqual(settings["material"], "C16")

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

    def test_horizontal_vapour_barrier_top_matches_the_selected_support_level(self):
        values = self.values
        layers = [e for name in ("flat_ceiling_roof", "lower_flat_ceiling_roof")
                  for e in values[name].elements if getattr(e, "material_name", None) == "Vapour barrier"]
        self.assertEqual(len(layers), len(values["roof_under_rafter_x_ranges"]))
        for layer in layers:
            lower = layer.plane is values["lower_flat_ceiling_roof"]
            expected_top = values["UPPER_FLOOR_START"] + values[
                "PURLIN_LOWER_WALL_TOP_HEIGHT" if lower else "INNER_SUPPORT_WALL_HEIGHT"]
            vertices = self.finished_vertices(layer)
            self.assertAlmostEqual(vertices[:, 2].max(), expected_top, places=6)
            self.assertAlmostEqual(
                vertices[:, 2].min(), expected_top - values["VAPOUR_BARRIER_THICKNESS"], places=6
            )
        for name, expected in (("flat_ceiling_roof", 2.6),
                               ("lower_flat_ceiling_roof", values["LOWER_CEILING_CLEAR_HEIGHT"])):
            for layer in values[name].elements:
                if getattr(layer, "material_name", None) == "Gypsum plasterboard":
                    self.assertAlmostEqual(self.finished_vertices(layer)[:, 2].min(),
                                           values["UPPER_FLOOR_START"] + values["UPPER_FLOOR_THICKNESS"] + expected)

    def test_inner_ranges_validate_profiles_and_reject_only_inner_overlaps(self):
        v = self.values
        validate = v["validate_roof_layer_ranges"]
        validate(v["roof_under_rafter_x_ranges"])
        validate(v["roof_over_rafter_x_ranges"], allow_overlap=True)
        overlap = ((0, 2, "normal"), (1, 3, "lower"))
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            validate(overlap)
        validate(overlap, allow_overlap=True)
        validate(((2, 3, "lower"), (0, 2, "normal")))
        for invalid in (((0, 1, "unknown"),), ((1, 0, "normal"),), ((0, float("inf"), "lower"),)):
            with self.assertRaises(ValueError):
                validate(invalid, allow_overlap=True)
        selector = v["inner_roof_section_at"]
        with patch.dict(selector.__globals__, {"roof_under_rafter_x_ranges":
                                              ((1, 2, "lower"), (0, 1, "normal"))}):
            self.assertEqual(selector(1)[1], "lower")
            with self.assertRaisesRegex(ValueError, "no under-rafter layer range"):
                selector(-1)

    def test_lower_interior_layers_cover_whole_last_bay_without_an_exterior_step_split(self):
        v = self.values
        lo, hi, profile = v["roof_under_rafter_x_ranges"][2]
        self.assertEqual(profile, "lower")
        self.assertEqual(lo, v["wall3_x"])
        self.assertLess(lo, v["LOWER_NADEZDIVKA_X"])
        self.assertEqual(hi, v["HOUSE_WIDTH"] - v["BWT"])
        for name, expected in (("lower_street_roof", 3), ("lower_garden_roof", 3),
                               ("lower_flat_ceiling_roof", 2)):
            layers = [e for e in v[name].elements if getattr(e, "material_name", None)
                      in {"Thermal insulation", "Vapour barrier", "Gypsum plasterboard"}]
            self.assertEqual(len(layers), expected)
            self.assertTrue(all(e.material_name in {"Thermal insulation", "Vapour barrier", "Gypsum plasterboard"}
                                for e in layers))
            for layer in layers:
                vertices = self.finished_vertices(layer)
                self.assertAlmostEqual(vertices[:, 0].min(), lo)
                self.assertAlmostEqual(vertices[:, 0].max(), hi)
                local = np.array([v[name].to_local(vertex) for vertex in vertices])
                self.assertAlmostEqual(np.ptp(local[:, 2]), layer.thickness)
        self.assertAlmostEqual(v["roof_angle_degrees"](v["lower_street_roof"]), v["lower_roof_angle"])
        self.assertAlmostEqual(v["roof_angle_degrees"](v["lower_garden_roof"]), v["lower_roof_angle"])

    def test_each_interior_profile_has_matching_slope_and_flat_bottom_junctions(self):
        v = self.values
        for profile in v["roof_inner_profiles"].values():
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
                         {"Wood fiberboard", "Roofing underlay", "Roof tiles"})
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

    def test_exterior_high_and_low_ranges_keep_the_full_explicit_overlap(self):
        v = self.values
        high, low = v["roof_over_rafter_x_ranges"][2:]
        self.assertEqual(high, (v["wall3_x"], v["LOWER_NADEZDIVKA_X"] + v["ROOF_X_OVERHANG"], "normal"))
        self.assertEqual(low, (v["LOWER_NADEZDIVKA_X"], v["HOUSE_WIDTH"] + v["ROOF_X_OVERHANG"], "lower"))
        self.assertAlmostEqual(high[1] - low[0], v["ROOF_X_OVERHANG"])
        for plane, prefix, bounds in (
            (v["street_roof"], "Street segment 2", high),
            (v["garden_roof"], "Garden segment 2", high),
            (v["lower_street_roof"], "Street segment 3", low),
            (v["lower_garden_roof"], "Garden segment 3", low),
        ):
            layers = [e for e in plane.elements if hasattr(e, "outline") and e.Name.startswith(prefix + " ")]
            self.assertEqual(len(layers), 3)
            for layer in layers:
                vertices = self.finished_vertices(layer)
                self.assertAlmostEqual(vertices[:, 0].min(), bounds[0])
                self.assertAlmostEqual(vertices[:, 0].max(), bounds[1])
                local = np.array([plane.to_local(vertex) for vertex in vertices])
                self.assertAlmostEqual(local[:, 2].min(), layer.z_offset)
                self.assertAlmostEqual(np.ptp(local[:, 2]), layer.thickness)
                if plane in (v["street_roof"], v["lower_street_roof"]):
                    self.assertAlmostEqual(vertices[:, 1].max(), v["HALF_DEPTH"])
                    self.assertAlmostEqual(vertices[:, 1].min(), v["STREET_ROOF_EAVE_Y"])
                else:
                    self.assertAlmostEqual(vertices[:, 1].min(), v["HALF_DEPTH"])
                    self.assertAlmostEqual(vertices[:, 1].max(), v["GARDEN_ROOF_EAVE_Y"])
        for side in ("street", "garden"):
            high_plane, low_plane = v[side + "_roof"], v["lower_" + side + "_roof"]
            self.assertGreater(v["roof_batting_point"](high_plane, x=high[1], y=2 if side == "street" else 6)[2],
                               v["roof_batting_point"](low_plane, x=high[1], y=2 if side == "street" else 6)[2])

    def test_counter_battens_follow_exterior_planes_without_coincident_duplicates(self):
        v = self.values
        battens = v["exterior_counter_battens"]
        planes = {b.roof_plane for b in battens}
        self.assertTrue({v["lower_street_roof"], v["lower_garden_roof"]}.issubset(planes))
        intervals = {}
        for batten in battens:
            plane = batten.roof_plane
            x = batten.local_start[0]
            pieces = [p for p in v["roof_exterior_pieces"] if p["plane"] is plane and p["x_min"] <= x <= p["x_max"]]
            self.assertTrue(pieces)
            self.assertAlmostEqual(batten.z_offset, v["COUNTER_BATTEN_BOTTOM"])
            vertices = self.finished_vertices(batten)
            self.assertGreaterEqual(vertices[:, 1].min(), min(v["STREET_ROOF_EAVE_Y"], v["HALF_DEPTH"]) - 1e-7)
            self.assertLessEqual(vertices[:, 1].max(), v["GARDEN_ROOF_EAVE_Y"] + 1e-7)
            intervals.setdefault((plane.GlobalId, x), []).append((batten.local_start[1], batten.local_end[1]))
        for spans in intervals.values():
            spans.sort()
            self.assertTrue(all(a[1] < b[0] for a, b in zip(spans, spans[1:])))
        # Repeating the ranges must not repeat wood on coincident planes;
        # different high/low planes at the same X must both remain present.
        helper = v["add_exterior_counter_battens"]
        x = v["LOWER_NADEZDIVKA_X"] + .1
        with (
            patch.dict(helper.__globals__, {"roof_layer_storeys": {"Counter-battens": Mock()},
                                           "main_rafter_positions": (x,), "dormer_rafter_positions": ()}),
            patch.object(type(v["street_roof"]), "beam", autospec=True, return_value=Mock()) as create,
        ):
            helper(v["roof_exterior_pieces"] * 2)
        self.assertEqual(create.call_count, 4)
        self.assertEqual({call.args[0] for call in create.call_args_list},
                         {v["street_roof"], v["garden_roof"], v["lower_street_roof"], v["lower_garden_roof"]})

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
            for offset, thickness in ((v["WOOD_FIBERBOARD_BOTTOM"], v["WOOD_FIBERBOARD_THICKNESS"]),
                                      (v["UNDERLAY_BOTTOM"], v["UNDERLAY_THICKNESS"]),
                                      (v["ROOF_TILE_BOTTOM"], v["ROOF_TILE_THICKNESS"])):
                layer = plane.layer("Test layer", outline=((0, lo), (1, lo), (1, hi), (0, hi)),
                                    z_offset=offset, thickness=thickness, material="Roofing underlay")
                vertices = self.finished_vertices(layer)
                self.assertAlmostEqual(vertices[:, 1].min(), v["HALF_DEPTH"])
                self.assertGreater(vertices[:, 1].max(), v["HALF_DEPTH"] + .5)

    def test_all_roof_layers_use_supplied_x_ranges_without_purlin_splits(self):
        values = self.values
        inner_materials = {
            "Thermal insulation", "Vapour barrier", "Gypsum plasterboard",
        }
        outer_materials = {"Wood fiberboard", "Roofing underlay", "Roof tiles"}
        pieces = [
            *[(values["street_roof"], f"Street segment {i}", i, inner_materials | outer_materials)
              for i in (0, 1)],
            (values["street_roof"], "Street segment 2", 2, outer_materials),
            (values["lower_street_roof"], "Street segment 2", 2, inner_materials),
            (values["garden_roof"], "Garden segment 0", 0, inner_materials | outer_materials),
            (values["garden_roof"], "Garden segment 2", 2, outer_materials),
            (values["lower_garden_roof"], "Garden segment 2", 2, inner_materials),
            (values["lower_street_roof"], "Street segment 3", 3, outer_materials),
            (values["lower_garden_roof"], "Garden segment 3", 3, outer_materials),
            (values["garden_roof"], "Garden segment 1 above dormer", 1, outer_materials),
            (values["dormer_roof"], "Dormer segment 1", 1, inner_materials | outer_materials),
            *[(values["flat_ceiling_roof"], f"Flat ceiling segment {i}", i,
               {"Vapour barrier", "Gypsum plasterboard"}) for i in (0, 1)],
            (values["lower_flat_ceiling_roof"], "Flat ceiling segment 2", 2,
             {"Vapour barrier", "Gypsum plasterboard"}),
        ]
        for plane, prefix, index, materials in pieces:
            layers = [e for e in plane.elements
                      if hasattr(e, "outline") and (e.Name or "").startswith(prefix + " ")]
            with self.subTest(piece=prefix):
                self.assertEqual(len(layers), len(materials))
                self.assertEqual({e.material_name for e in layers}, materials)
                for layer in layers:
                    ranges = values["roof_over_rafter_x_ranges"] if layer.material_name in outer_materials \
                        else values["roof_under_rafter_x_ranges"]
                    expected_min, expected_max = ranges[index][:2]
                    xs = [p[0] for p in layer.outline]
                    self.assertAlmostEqual(min(xs), expected_min)
                    self.assertAlmostEqual(max(xs), expected_max)
                    vertices = self.finished_vertices(layer)
                    self.assertAlmostEqual(vertices[:, 0].min(), expected_min, places=6)
                    self.assertAlmostEqual(vertices[:, 0].max(), expected_max, places=6)

    def test_tile_battens_follow_all_outer_ranges_on_the_correct_slopes(self):
        v = self.values
        for plane, prefix, indices in (
            (v["street_roof"], "Street segments 0 to 2", (0, 1, 2)),
            (v["garden_roof"], "Garden segments 0 and 2", (0, 2)),
            (v["garden_roof"], "Garden segment 1 above dormer", (1,)),
            (v["dormer_roof"], "Dormer segment 1", (1,)),
            (v["lower_street_roof"], "Lower street exterior", (3,)),
            (v["lower_garden_roof"], "Lower garden exterior", (3,)),
        ):
            with self.subTest(prefix=prefix):
                battens = [b for b in plane.elements if (b.Name or "").startswith(prefix + " tile batten ")]
                self.assertTrue(battens)
                self.assertEqual({(b.local_start[0], b.local_end[0]) for b in battens},
                                 {v["roof_over_rafter_x_ranges"][i][:2] for i in indices})

    def test_removed_house_cut_has_no_short_street_rafters_plate_or_schedule_rows(self):
        v = self.values
        self.assertNotIn("cut_street_roof", v)
        self.assertNotIn("beam_cut_street", v)
        self.assertEqual(len(v["roof_wall_plates"]), 6)
        self.assertEqual(set(v["roof_under_rafter_insulations"]), {
            "Street segment 0", "Street segment 1", "Street segment 2",
            "Garden segment 0", "Garden segment 2", "Dormer segment 1",
        })
        names = [row[0] for row in v["timber_schedule_rows"]]
        self.assertFalse(any("roh" in name or "krátká - ulice" in name for name in names))
        street_rafters = [b for b in (*v["main_roof_rafters"], *v["stronger_main_roof_rafters"])
                          if b.roof_plane in (v["street_roof"], v["lower_street_roof"])]
        self.assertEqual(len(street_rafters), len(v["main_rafter_positions"]))
        for rafter in street_rafters:
            self.assertAlmostEqual(self.finished_vertices(rafter)[:, 1].min(), v["STREET_ROOF_EAVE_Y"], places=6)
        for batten in v["street_roof"].elements:
            if (batten.Name or "").startswith("Street counter-batten"):
                self.assertIs(batten.roof_plane, v["street_roof"])

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
                "Wood fiberboard", "Roofing underlay", "Roof tiles",
            } else (x_min, x_max)
            self.assertEqual((min(xs), max(xs)), expected)


class ExplicitFramingLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        cls.runs = {}
        for case in ("moved", "overlap"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    continue
                name = node.targets[0].id
                if name == "LOWER_NADEZDIVKA_X":
                    expression = "wall3_x + .12" if case == "moved" else "wall3_x + .4"
                    node.value = ast.parse(expression, mode="eval").body
                elif case == "overlap":
                    if name == "high_rafters":
                        node.value.elts.extend(ast.parse(expression, mode="eval").body for expression in (
                            "LOWER_NADEZDIVKA_X + .1",
                            "StrongerRafter(LOWER_NADEZDIVKA_X - .045)",
                        ))
                    elif name == "lower_rafters":
                        node.value.elts.extend(ast.parse(expression, mode="eval").body for expression in (
                            "LOWER_NADEZDIVKA_X - .1",
                            "LOWER_NADEZDIVKA_X + .045",
                        ))
                    elif name in ("beam3", "beam3_lower", "beam4_lower"):
                        # Explicitly extend the seats as well as adding framing.
                        # Production support coverage must not be bypassed.
                        keyword_name = "end" if name == "beam3" else "start"
                        expression = "LOWER_NADEZDIVKA_X + .2" if name == "beam3" else "LOWER_NADEZDIVKA_X - .2"
                        keyword = next(k for k in node.value.keywords if k.arg == keyword_name)
                        keyword.value.elts[0] = ast.parse(expression, mode="eval").body
            ast.fix_missing_locations(tree)
            values = {"__file__": str(source), "__name__": "__main__"}
            with (
                patch.object(sys, "argv", [str(source)]),
                patch.object(House, "write", return_value=Path("house.ifc")),
                redirect_stdout(StringIO()),
            ):
                exec(compile(tree, str(source), "exec"), values)
            cls.runs[case] = values

    def test_moving_step_through_a_dormer_assembly_keeps_its_explicit_high_level(self):
        v = self.runs["moved"]
        x = v["vk_to"]
        step = v["LOWER_NADEZDIVKA_X"]
        self.assertGreater(x + v["RAFTER_THICKNESS"] / 2, step)
        dormer_x = x + v["paired_rafter_dormer_offsets"][x]
        self.assertGreater(dormer_x, step)
        self.assertFalse(v["framing_is_lower"](x))
        self.assertFalse(v["framing_is_lower"](dormer_x))
        members = v["rafter_assemblies"][x]
        ties = [b for b in members if b in v["collar_ties"]]
        self.assertEqual(len(ties), 2)
        self.assertTrue(any(tie.start[0] - tie.width/2 > step for tie in ties))
        for tie in ties:
            self.assertAlmostEqual(tie.start[2] - tie.height/2, v["PURLIN_TOP_Z"])
        dormer = next(b for b in members if b in v["dormer_roof_rafters"])
        self.assertIs(dormer.roof_plane, v["dormer_rafter_roof"])
        street = next(b for b in members if getattr(b, "roof_plane", None) is v["street_roof"])
        self.assertIn(street, v["main_roof_rafters"])

    def test_overlapping_arrays_select_their_own_planes_supports_ties_and_spacers(self):
        v = self.runs["overlap"]
        step = v["LOWER_NADEZDIVKA_X"]
        for x, lower in ((step+.1, False), (step-.1, True)):
            with self.subTest(x=x, lower=lower):
                self.assertEqual(v["framing_is_lower"](x), lower)
                members = v["rafter_assemblies"][x]
                planes = (v["lower_street_roof"], v["lower_garden_roof"]) if lower else (v["street_roof"], v["garden_roof"])
                rafters = [b for b in members if b.kind == "RAFTER"]
                self.assertEqual({b.roof_plane for b in rafters}, set(planes))
                self.assertEqual(len(rafters), 2)
                for side in ("street", "garden"):
                    self.assertIs(v["purlin_at"](x, side=side), v[side+"_purlins"][2 if lower else 1])
                support_top = v["LOWER_ROOF_JOINT_Z"] if lower else v["PURLIN_TOP_Z"]
                ties = [b for b in members if b in v["collar_ties"]]
                self.assertEqual(len(ties), 2)
                for tie in ties:
                    self.assertAlmostEqual(tie.start[2] - tie.height/2, support_top)
                spacer = next(b for b in members if b in v["purlin_spacers"])
                self.assertAlmostEqual(spacer.start[2] + spacer.height/2, support_top)
                width, _, distance = v["purlin_dimensions_at"](x)
                self.assertAlmostEqual(spacer.length, 2 * distance - width)
                expected_plates = {v["beam3_lower"], v["beam4_lower"]} if lower else {v["beam3"], v["beam4_b"]}
                self.assertEqual(set(v["assembly_wall_plates"](x)), expected_plates)
                index = next(i for i, entry in enumerate(v["rafters"])
                             if v["rafter_x_position"](entry) == x)
                drawing = v["add_roof_elevation"](
                    f"overlap_{'lower' if lower else 'high'}", rafter_index=index, offset=.01)
                self.assertTrue(drawing)

    def test_touching_rafters_at_different_levels_keep_both_flanking_boards(self):
        v = self.runs["overlap"]
        step = v["LOWER_NADEZDIVKA_X"]
        high_x, lower_x = step-.045, step+.045
        self.assertAlmostEqual(lower_x-high_x,
                               (v["STRONGER_RAFTER_THICKNESS"] + v["RAFTER_THICKNESS"])/2)
        for x in (high_x, lower_x):
            self.assertEqual(len([b for b in v["rafter_assemblies"][x] if b in v["collar_ties"]]), 2)
        stronger = [b for b in v["rafter_assemblies"][high_x] if b.kind == "RAFTER"]
        self.assertEqual(len(stronger), 2)
        self.assertTrue(all(b in v["stronger_main_roof_rafters"] for b in stronger))


if __name__ == "__main__":
    unittest.main()
