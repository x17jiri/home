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


class CollarRemovalTests(unittest.TestCase):
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

    def test_no_collar_tie_beams_or_visibility_storey(self):
        model = self.values["house"].model
        beams = model.by_type("IfcBeam")
        self.assertTrue(beams)
        self.assertFalse(any((beam.Name or "").startswith("Collar tie ") for beam in beams))
        self.assertNotIn("Collar ties", self.values["roof_layer_storeys"])
        self.assertFalse(
            any(
                "Collar ties" in (storey.Name or "")
                for storey in model.by_type("IfcBuildingStorey")
            )
        )
        self.assertTrue(self.values["main_roof_rafters"])
        self.assertEqual(len(self.values["street_purlins"]), 3)
        self.assertEqual(len(self.values["garden_purlins"]), 3)

    def test_roof_and_aa_drawings_build_and_schedule_omits_collar_rows(self):
        self.assertEqual(self.rendered, ["roof.svg", "aa.svg"])
        names = [row[0] for row in self.values["timber_schedule_rows"]]
        self.assertFalse(any("Kleštiny" in name for name in names))
        self.assertTrue(any("Vaznice" in name for name in names))
        self.assertTrue(any("Krokve" in name for name in names))
        self.assertTrue(any("Pozednice" in name for name in names))
        self.assertIn("Sedla vaznic", names)
        self.assertIn("Rozpěry vaznic", names)

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

    def test_uniform_purlins_and_four_sedla_rest_on_shortened_walls(self):
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
            sedla = values[side + "_sedla"]
            self.assertEqual(len(sedla), 2)
            for wall, left, right, sedlo in zip(
                (values["wall_2"], values["wall_3"]), beams, beams[1:], sedla
            ):
                self.assertEqual((sedlo.width, sedlo.height), (left.width, left.height))
                self.assertEqual(left.end, right.start)
                self.assertAlmostEqual((sedlo.start[0] + sedlo.end[0]) / 2, left.end[0])
                self.assertAlmostEqual(sedlo.end[0] - sedlo.start[0], values["SEDLO_LENGTH"])
                self.assertAlmostEqual(sedlo.start[2] + sedlo.height / 2, values["PURLIN_BOTTOM_Z"])
                self.assertFalse(sedlo.FillsVoids)
                self.assertAlmostEqual(
                    self.finished_vertices(wall)[:, 2].max(),
                    sedlo.start[2] - sedlo.height / 2,
                )
        schedule = next(row for row in values["timber_schedule_rows"] if row[0] == "Sedla vaznic")
        self.assertEqual(len(schedule[1]), 4)

    def test_sedla_are_mirrored_once_and_stay_under_their_purlin_joints(self):
        values = self.values
        exported = values["house"]._export_model()
        for side in ("street", "garden"):
            for left, sedlo in zip(
                values[side + "_purlins"],
                values[side + "_sedla"],
            ):
                self.assertEqual(
                    sedlo.ObjectPlacement.PlacementRelTo,
                    values["upper"].element.ObjectPlacement,
                )
                vertices = self.finished_vertices(exported.by_guid(sedlo.GlobalId))
                low, high = vertices.min(axis=0), vertices.max(axis=0)
                np.testing.assert_allclose(
                    (low + high) / 2,
                    (-left.end[0], left.end[1], values["PURLIN_BOTTOM_Z"] - sedlo.height / 2),
                    atol=1e-8,
                )
                np.testing.assert_allclose(
                    high - low, (values["SEDLO_LENGTH"], sedlo.width, sedlo.height), atol=1e-8
                )

    def test_inner_walls_have_lower_top_without_sedlo_openings_or_recesses(self):
        values = self.values
        expected = values["PURLIN_WALL_TOP_HEIGHT"] - values["VAZNICE_HEIGHT"]
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
        # Outer/gable walls and the roof datum are not lowered.
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

    def test_horizontal_vapour_barrier_is_directly_below_sedla(self):
        values = self.values
        plane = values["flat_ceiling_roof"]
        layers = [
            e for e in plane.elements if getattr(e, "material_name", None) == "Vapour barrier"
        ]
        self.assertTrue(layers)
        for layer in layers:
            expected_top = values["SEDLO_BOTTOM_Z"]
            vertices = self.finished_vertices(layer)
            self.assertAlmostEqual(vertices[:, 2].max(), expected_top, places=6)
            self.assertAlmostEqual(
                vertices[:, 2].min(), expected_top - values["VAPOUR_BARRIER_THICKNESS"], places=6
            )
        for sedlo in (*values["street_sedla"], *values["garden_sedla"]):
            self.assertAlmostEqual(
                self.finished_vertices(sedlo)[:, 2].min(), values["SEDLO_BOTTOM_Z"]
            )
        # Moving the vapour barrier does not move the plasterboard ceiling.
        self.assertAlmostEqual(
            values["FLAT_CEILING_LAYER_HEIGHTS"]["Gypsum plasterboard"][0],
            values["UPPER_FLOOR_THICKNESS"] + 2.635,
        )


if __name__ == "__main__":
    unittest.main()
