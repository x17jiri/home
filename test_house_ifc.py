"""Integration checks for the model script, without exporting or rendering."""

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
                    self.assertAlmostEqual(tie.start[0], x + sign * (width + tie.width) / 2)
                    vertices = self.finished_vertices(tie)
                    self.assertAlmostEqual(vertices[:, 2].min(), values["PURLIN_TOP_Z"])
                    self.assertAlmostEqual(vertices[:, 2].max(), values["PURLIN_TOP_Z"] + 0.15)
                    # The sloped finished ends span both complete purlin widths.
                    self.assertLess(vertices[:, 1].min(), values["STREET_ROOF_JOINT_Y"])
                    self.assertGreater(vertices[:, 1].max(), values["GARDEN_ROOF_JOINT_Y"])
                    self.assertEqual(
                        ifcopenshell.util.element.get_container(tie),
                        values["roof_layer_storeys"]["Collar ties"].element,
                    )

    def test_roof_and_aa_drawings_build_and_schedule_includes_collar_rows(self):
        self.assertEqual(self.rendered, ["roof.svg", "aa.svg"])
        names = [row[0] for row in self.values["timber_schedule_rows"]]
        self.assertIn("Kleštiny", names)
        self.assertTrue(any("Vaznice" in name for name in names))
        self.assertTrue(any("Krokve" in name for name in names))
        self.assertTrue(any("Pozednice" in name for name in names))
        self.assertNotIn("Sedla vaznic", names)
        self.assertIn("Rozpěry vaznic", names)
        row = next(row for row in self.values["timber_schedule_rows"] if row[0] == "Kleštiny")
        self.assertEqual(tuple(row[1]), self.values["collar_ties"])
        self.assertGreater(
            row[3]["drawing_order"], self.values["PURLIN_AND_WALL_PLATE_DRAWING_ORDER"]
        )
        self.assertLess(row[3]["drawing_order"], self.values["MAIN_RAFTER_DRAWING_ORDER"])

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
        street_inner_y = values["street_purlins"][1].start[1] + values["VAZNICE_HALF_BASE"]
        garden_inner_y = values["garden_purlins"][1].start[1] - values["VAZNICE_HALF_BASE"]
        for x, spacer in zip(values["main_rafter_positions"], spacers):
            with self.subTest(spacer=spacer.Name):
                np.testing.assert_allclose(
                    spacer.start, (x, street_inner_y, values["PURLIN_TOP_Z"] - height / 2)
                )
                np.testing.assert_allclose(
                    spacer.end, (x, garden_inner_y, values["PURLIN_TOP_Z"] - height / 2)
                )
                self.assertAlmostEqual(spacer.length, values["PURLIN_SPACER_LENGTH"])
                self.assertEqual((spacer.width, spacer.height), (width, height))
                vertices = self.finished_vertices(spacer)
                np.testing.assert_allclose(
                    vertices.min(axis=0),
                    (x - width / 2, street_inner_y, values["PURLIN_TOP_Z"] - height),
                )
                np.testing.assert_allclose(
                    vertices.max(axis=0), (x + width / 2, garden_inner_y, values["PURLIN_TOP_Z"])
                )
        row = next(row for row in values["timber_schedule_rows"] if row[0] == "Rozpěry vaznic")
        self.assertEqual(tuple(row[1]), spacers)
        self.assertEqual(row[2], 0)

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

    def test_uniform_purlins_have_inset_gerber_joints_and_no_sedla(self):
        values = self.values
        self.assertNotIn("VAZNICE_EXTRA_HEIGHT", values)
        self.assertNotIn("add_purlin_wall_recess", values)
        self.assertFalse(values["wall_2"]._recesses)
        self.assertFalse(values["wall_3"]._recesses)
        for beam in (*values["street_purlins"], *values["garden_purlins"]):
            self.assertEqual(
                (beam.width, beam.height), (values["VAZNICE_BASE"], values["VAZNICE_HEIGHT"])
            )
            self.assertAlmostEqual(beam.start[2] + beam.height / 2, values["PURLIN_TOP_Z"])
        for side in ("street", "garden"):
            beams = values[side + "_purlins"]
            self.assertEqual(len(beams), 3)
            left, middle, right = beams
            self.assertEqual(left.end, middle.start)
            self.assertEqual(middle.end, right.start)
            self.assertAlmostEqual(middle.start[0], values["GERBER_JOINT_1"])
            self.assertAlmostEqual(middle.end[0], values["GERBER_JOINT_2"])
            self.assertAlmostEqual(
                middle.length, values["GERBER_JOINT_2"] - values["GERBER_JOINT_1"]
            )
            self.assertAlmostEqual(left.start[0], -0.2)
            self.assertAlmostEqual(right.end[0], values["HOUSE_WIDTH"] + 0.2)
            self.assertAlmostEqual(left.length, values["GERBER_JOINT_1"] + 0.2)
            self.assertAlmostEqual(
                right.length, values["HOUSE_WIDTH"] + 0.2 - values["GERBER_JOINT_2"]
            )
        self.assertNotIn("add_purlin_sedla", values)
        self.assertNotIn("street_sedla", values)
        self.assertNotIn("garden_sedla", values)
        self.assertFalse(
            any("sedlo" in (beam.Name or "").lower() for beam in values["house"].model.by_type("IfcBeam"))
        )

    def test_gerber_purlins_are_mirrored_once_and_have_no_joint_gaps(self):
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

    def test_inner_walls_reach_outer_wall_height_without_sedlo_openings_or_recesses(self):
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
        # Both inner and outer/gable walls reach the unchanged purlin bottom.
        self.assertAlmostEqual(
            self.finished_vertices(values["wall_4_u"])[:, 2].max(), values["PURLIN_BOTTOM_Z"]
        )

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
                expected = values["STREET_ROOF_JOINT_Y" if street else "GARDEN_ROOF_JOINT_Y"]
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
            self.assertAlmostEqual(self.finished_vertices(purlin)[:, 2].max(), purlin_top)

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
