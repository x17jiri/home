"""Integration checks for the model script, without exporting or rendering."""

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

from ifc_utils import CutDefinition, Drawing, House, _remove_3d_only_elements, _timber_schedule_member_styles
from materials import resolve_timber_grade


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
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]

    def test_all_plan_symbols_use_shared_cut_definitions(self):
        cuts = (self.values["aa_cut"], self.values["bb_cut"])
        self.assertTrue(all(isinstance(cut, CutDefinition) for cut in cuts))
        self.assertEqual(self.rendered, ["ground.svg", "upper.svg", "roof.svg", "aa.svg", "bb.svg"])
        drawings = self.values["house"]._drawings
        self.assertEqual(len(drawings), 5)
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

    def test_bb_facade_insulation_leaves_upper_window_clear(self):
        values = self.values
        drawing = next(d for d in values["house"]._drawings if d.name == "bb")
        wall = values["wall_4_u"]
        self.assertEqual(len(wall._openings), 1)
        _, _, bottom, top = wall._openings[0]
        bottom += wall.storey.elevation
        top += wall.storey.elevation
        annotations = drawing.group.IsGroupedBy[0].RelatedObjects
        strips = [ifcopenshell.util.element.get_pset(a, "BBIM_WallInsulation") for a in annotations]
        strips = [p for p in strips if p and p["HostWall"] == wall.GlobalId
                  and p["Material"] == "polystyrene"]
        self.assertEqual(len(strips), 1)
        segments = json.loads(strips[0]["Segments"])
        self.assertTrue(segments)
        for start, end in segments:
            self.assertTrue(end <= bottom or start >= top)


class RoofElevationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "roof", "roof_xx", "roof_yy", "roof_zz"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]

    def test_camera_is_before_selected_rafter_parallel_to_aa_and_mirrors_once(self):
        values = self.values
        drawing = values["roof_xx"]
        self.assertEqual(self.rendered, ["roof_xx.svg", "roof_yy.svg", "roof_zz.svg", "roof.svg"])
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

    def test_includes_only_upper_walls_and_structural_roof_members(self):
        values = self.values
        drawing = values["roof_xx"]
        pset = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
        self.assertEqual(pset["FillMode"], "SHAPELY")
        selected = ifcopenshell.util.selector.filter_elements(values["house"].model, pset["Include"])
        expected = set((*values["roof_outline_walls"], *values["roof_structural_beams"]))
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
        self.assertNotIn(values["beam3"].GlobalId, xx_styles)
        self.assertIn(values["beam_cut_street"].GlobalId, xx_styles)

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


class RoofFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with (
            patch.object(sys, "argv", [str(source), "roof", "aa"]),
            patch.object(House, "write", return_value=Path("house.ifc")),
            patch.object(Drawing, "render", return_value=Path("drawing.svg")) as render,
            redirect_stdout(StringIO()),
        ):
            cls.values = runpy.run_path(str(source))
            cls.rendered = [call.args[0] for call in render.call_args_list]

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
        self.assertEqual(len(modified_voids), 2)
        for void in modified_voids:
            host = void.VoidsElements[0].RelatingBuildingElement
            self.assertEqual(ifcopenshell.util.element.get_material(host).Name, "Gypsum plasterboard")

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
                    # The sloped finished ends span both complete purlin widths.
                    self.assertLess(vertices[:, 1].min(), values["STREET_ROOF_JOINT_Y"])
                    self.assertGreater(vertices[:, 1].max(), values["GARDEN_ROOF_JOINT_Y"])
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
        for x, side in pairs:
            self.assertIn(x, values["paired_rafter_dormer_offsets"])
            self.assertEqual(main_entries[x], not side.startswith("+"))

    def test_roof_and_aa_drawings_build_and_schedule_includes_collar_rows(self):
        self.assertEqual(self.rendered, ["roof.svg", "aa.svg"])
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

    def test_independent_purlins_have_aligned_tops_and_no_gerber_joints(self):
        values = self.values
        self.assertNotIn("GERBER_JOINT_1", values)
        self.assertNotIn("GERBER_JOINT_2", values)
        self.assertNotIn("VAZNICE_EXTRA_HEIGHT", values)
        self.assertNotIn("add_purlin_wall_recess", values)
        self.assertFalse(values["wall_2"]._recesses)
        self.assertFalse(values["wall_3"]._recesses)
        for beam in (*values["street_purlins"], *values["garden_purlins"]):
            width, height, distance = values["purlin_dimensions_at"]((beam.start[0] + beam.end[0]) / 2)
            self.assertEqual(
                (beam.width, beam.height), (width, height)
            )
            self.assertAlmostEqual(beam.start[2] + beam.height / 2, values["PURLIN_TOP_Z"])
            self.assertAlmostEqual(abs(beam.start[1] - values["HALF_DEPTH"]), distance)
        for side in ("street", "garden"):
            beams = values[side + "_purlins"]
            self.assertEqual(len(beams), 3)
            left, middle, right = beams
            self.assertAlmostEqual(left.end[0], middle.start[0])
            self.assertAlmostEqual(middle.end[0], right.start[0])
            self.assertAlmostEqual(middle.start[0], values["wall2_x"] - values["BWT"] / 2)
            self.assertAlmostEqual(middle.end[0], values["wall3_x"] - values["BWT"] / 2)
            self.assertAlmostEqual(
                middle.length, values["wall3_x"] - values["wall2_x"]
            )
            self.assertAlmostEqual(left.start[0], -0.2)
            self.assertAlmostEqual(right.end[0], values["HOUSE_WIDTH"] + 0.2)
            self.assertAlmostEqual(left.length, values["MIDDLE_PURLIN_X_MIN"] + 0.2)
            self.assertAlmostEqual(
                right.length, values["HOUSE_WIDTH"] + 0.2 - values["MIDDLE_PURLIN_X_MAX"]
            )
        self.assertNotIn("add_purlin_sedla", values)
        self.assertNotIn("street_sedla", values)
        self.assertNotIn("garden_sedla", values)
        self.assertFalse(
            any("sedlo" in (beam.Name or "").lower() for beam in values["house"].model.by_type("IfcBeam"))
        )

    def test_independent_purlins_are_mirrored_once_and_meet_at_wall_centres_in_x(self):
        values = self.values
        exported = values["house"]._export_model()
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
                    (-(beam.start[0] + beam.end[0]) / 2, beam.start[1], beam.start[2]),
                    atol=1e-8,
                )
                np.testing.assert_allclose(
                    high - low, (beam.length, beam.width, beam.height), atol=1e-8
                )
            for (left_low, _), (_, right_high) in zip(bounds, bounds[1:]):
                self.assertAlmostEqual(left_low[0], right_high[0])

    def test_side_purlins_follow_both_main_and_dormer_roof_angles(self):
        values = self.values
        for side in ("street", "garden"):
            plane = values[side + "_roof"]
            for beam in values[side + "_purlins"]:
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
        self.assertAlmostEqual(
            values["PURLIN_WALL_TOP_HEIGHT"],
            values["UNDER_HOLE"] + values["HOLE_HEIGHT"] + values["ABOVE_HOLE"],
        )
        self.assertGreater(values["VAZNICE_SIDE_DIST"], values["VAZNICE_DIST"])

    def test_only_outer_purlin_support_walls_are_raised(self):
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
        for name in ("wall_1a_u", "wall_4_u"):
            self.assertAlmostEqual(
                self.finished_vertices(values[name])[:, 2].max(),
                values["PURLIN_TOP_Z"] - values["VAZNICE_SIDE_HEIGHT"],
            )

    def test_four_packing_blocks_fill_only_side_piece_half_of_inner_walls(self):
        values = self.values
        blocks = values["purlin_packing_blocks"]
        self.assertEqual(len(blocks), 4)
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
                piece_index = 0 if "left" in block.Name else 2
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

    def test_purlin_bottom_helper_matches_actual_normal_and_middle_members(self):
        values = self.values
        for beam in (*values["street_purlins"], *values["garden_purlins"]):
            x = (beam.start[0] + beam.end[0]) / 2
            expected = beam.start[2] - beam.height / 2
            self.assertAlmostEqual(values["purlin_bottom_z_at"](x), expected)

    def test_sloped_insulation_is_clipped_at_purlin_outer_vertical_face(self):
        values = self.values
        for layer in values["roof_under_rafter_insulations"].values():
            with self.subTest(layer=layer.Name):
                street = layer.Name.startswith("Street")
                vertices = self.finished_vertices(layer)
                x = (vertices[:, 0].min() + vertices[:, 0].max()) / 2
                expected = values["purlin_outer_face_y_at"](x, side="street" if street else "garden")
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
        for purlin in (*values["street_purlins"], *values["garden_purlins"]):
            x = (purlin.start[0] + purlin.end[0]) / 2
            self.assertAlmostEqual(
                self.finished_vertices(purlin)[:, 2].max(), values["purlin_top_z_at"](x)
            )

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

    def test_horizontal_vapour_barrier_top_matches_inner_wall_top_in_all_sections(self):
        values = self.values
        plane = values["flat_ceiling_roof"]
        layers = [
            e for e in plane.elements if getattr(e, "material_name", None) == "Vapour barrier"
        ]
        self.assertEqual(len(layers), len(values["roof_under_rafter_x_ranges"]))
        expected_top = values["UPPER_FLOOR_START"] + values["INNER_SUPPORT_WALL_HEIGHT"]
        self.assertAlmostEqual(expected_top, values["PURLIN_BOTTOM_Z"])
        for layer in layers:
            self.assertAlmostEqual(values["FLAT_VAPOUR_BARRIER_TOP_Z"], expected_top)
            vertices = self.finished_vertices(layer)
            self.assertAlmostEqual(vertices[:, 2].max(), expected_top, places=6)
            self.assertAlmostEqual(
                vertices[:, 2].min(), expected_top - values["VAPOUR_BARRIER_THICKNESS"], places=6
            )
        # Moving the vapour barrier does not move the plasterboard ceiling.
        self.assertAlmostEqual(
            values["FLAT_CEILING_LAYER_HEIGHTS"]["Gypsum plasterboard"][0],
            values["UPPER_FLOOR_THICKNESS"] + 2.635,
        )

    def test_all_roof_layers_use_supplied_x_ranges_without_purlin_splits(self):
        values = self.values
        inner_materials = {
            "Thermal insulation", "Vapour barrier", "Gypsum plasterboard",
        }
        outer_materials = {"Wood fiberboard", "Roofing underlay", "Roof tiles"}
        pieces = [
            (values["cut_street_roof"], "Street segment 0", 0, inner_materials | outer_materials),
            *[(values["street_roof"], f"Street segment {i}", i, inner_materials | outer_materials)
              for i in (1, 2, 3)],
            *[(values["garden_roof"], f"Garden segment {i}", i, inner_materials | outer_materials)
              for i in (0, 1, 3)],
            (values["garden_roof"], "Garden segment 2 above dormer", 2, outer_materials),
            (values["dormer_roof"], "Dormer segment 2", 2, inner_materials | outer_materials),
            *[(values["flat_ceiling_roof"], f"Flat ceiling segment {i}", i,
               {"Vapour barrier", "Gypsum plasterboard"}) for i in range(4)],
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
                    expected_min, expected_max = ranges[index]
                    xs = [p[0] for p in layer.outline]
                    self.assertAlmostEqual(min(xs), expected_min)
                    self.assertAlmostEqual(max(xs), expected_max)
                    vertices = self.finished_vertices(layer)
                    self.assertAlmostEqual(vertices[:, 0].min(), expected_min, places=6)
                    self.assertAlmostEqual(vertices[:, 0].max(), expected_max, places=6)

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


if __name__ == "__main__":
    unittest.main()
