"""Integration checks for the model script, without exporting or rendering."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

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

    def test_ceiling_and_short_rafter_reference_levels_are_retained(self):
        values = self.values
        self.assertAlmostEqual(values["COLLAR_TIE_TOP_HEIGHT"], 3.25)
        self.assertAlmostEqual(values["COLLAR_TIE_BOTTOM_HEIGHT"], 3.05)
        middle = (values["MIDDLE_PURLIN_X_MIN"] + values["MIDDLE_PURLIN_X_MAX"]) / 2
        self.assertAlmostEqual(
            values["collar_tie_top_height_at"](middle), 3.25 - values["VAZNICE_EXTRA_HEIGHT"]
        )
        self.assertAlmostEqual(values["FLAT_CEILING_LAYER_HEIGHTS"]["Vapour barrier"][1], 3.05)


if __name__ == "__main__":
    unittest.main()
