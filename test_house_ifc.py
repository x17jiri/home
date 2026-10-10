"""Integration checks for the model script, without exporting or rendering."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np

from ifc_utils import Drawing, House
from materials import resolve_timber_grade


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

    def test_roof_schedule_resolves_shared_materials_and_preserves_row_selections(self):
        values = self.values
        purlin_guids = {b.GlobalId for b in (*values["street_purlins"], *values["garden_purlins"])}
        for name, members, _, settings in values["timber_schedule_rows"]:
            is_purlin = all(member.GlobalId in purlin_guids for member in members)
            grade = resolve_timber_grade(settings["material"])
            self.assertEqual(settings["material"], grade.name)
            if is_purlin:
                self.assertEqual(grade.name, "GL24c", name)
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
        self.assertEqual(sum(item["material"] == "GL24c" for item in items), 3)
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

    def test_horizontal_vapour_barrier_keeps_its_height_without_sedla(self):
        values = self.values
        plane = values["flat_ceiling_roof"]
        layers = [
            e for e in plane.elements if getattr(e, "material_name", None) == "Vapour barrier"
        ]
        self.assertTrue(layers)
        for layer in layers:
            expected_top = values["PURLIN_BOTTOM_Z"] - values["VAZNICE_HEIGHT"]
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


if __name__ == "__main__":
    unittest.main()
