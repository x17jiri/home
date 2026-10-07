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

    def test_sloped_insulation_is_clipped_at_actual_purlin_bottom(self):
        values = self.values
        for layer in values["roof_under_rafter_insulations"].values():
            xs = [point[0] for point in layer.outline]
            expected = values["purlin_bottom_z_at"]((min(xs) + max(xs)) / 2)
            self.assertTrue(
                any(
                    all(abs(point[2] - expected) < 1e-8 for point in cut)
                    for cut in layer.extra_cuts
                )
            )
            self.assertLessEqual(self.finished_vertices(layer)[:, 2].max(), expected + 1e-6)

    def test_horizontal_batting_fits_between_purlin_and_vapour_barrier(self):
        values = self.values
        thickness = values["THERMAL_INSULATION_UNDER_RAFTERS"]
        purlin_bottom = values["purlin_bottom_z_at"](values["aa_x"])
        centre = values["horizontal_batting_center_z"]
        self.assertAlmostEqual(centre + thickness / 2, purlin_bottom)
        self.assertAlmostEqual(values["horizontal_batting_start"][2], centre)
        self.assertAlmostEqual(values["horizontal_batting_end"][2], centre)
        barrier_bottom, barrier_thickness = values["MIDDLE_FLAT_CEILING_INNER_LAYER_LAYOUT"][
            "Vapour barrier"
        ]
        barrier_top = values["flat_ceiling_roof"].to_world(
            (0, 0, barrier_bottom + barrier_thickness)
        )[2]
        self.assertAlmostEqual(centre - thickness / 2, barrier_top)

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
                symbol_thickness = ifcopenshell.util.element.get_psets(annotation)[
                    "BBIM_Batting"
                ]["Thickness"]
                self.assertAlmostEqual(
                    symbol_thickness, values["UNDER_RAFTER_BATTING_THICKNESS"]
                )
                self.assertLess(symbol_thickness, physical_thickness)
                self.assertAlmostEqual(
                    symbol_thickness / physical_thickness, between_rafter_ratio
                )

    def test_horizontal_vapour_barrier_is_one_insulation_thickness_below_purlins(self):
        values = self.values
        plane = values["flat_ceiling_roof"]
        layers = [
            e for e in plane.elements if getattr(e, "material_name", None) == "Vapour barrier"
        ]
        self.assertTrue(layers)
        for layer in layers:
            xs = [point[0] for point in layer.outline]
            expected_top = (
                values["purlin_bottom_z_at"]((min(xs) + max(xs)) / 2)
                - values["THERMAL_INSULATION_UNDER_RAFTERS"]
            )
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
