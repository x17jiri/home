import unittest
from contextlib import redirect_stdout
from io import StringIO
from math import cos, radians
from unittest.mock import patch

from rafter_load import (
    DORMER_ROOF_ANGLE_DEGREES,
    DORMER_SUPPORT_SPAN_M,
    GRAVITY_M_S2,
    PURLIN_HEIGHT_MM,
    PURLIN_SPANS_M,
    PURLIN_SUPPORT_SPAN_M,
    PURLIN_WIDTH_MM,
    calculate_continuous_beam_response,
    calculate_rafter_load,
    calculate_purlin_check,
    calculate_roof_check,
    main,
)


class RafterLoadTests(unittest.TestCase):
    def test_calculates_deflection_limited_uniform_load(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=200,
            support_span_m=3.7,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            timber_density_kg_m3=450,
        )

        self.assertAlmostEqual(result.second_moment_m4, 0.0000533333333333)
        self.assertAlmostEqual(result.maximum_deflection_m, 3.7 / 300)
        self.assertAlmostEqual(result.self_mass_kg_per_m, 7.2)
        expected_total_n_per_m = (
            (3.7 / 300)
            * 384
            * 11e9
            * (0.08 * 0.2**3 / 12)
            / (5 * 3.7**4)
        )
        self.assertAlmostEqual(
            result.deflection_total_n_per_m,
            expected_total_n_per_m,
        )
        self.assertAlmostEqual(
            result.deflection_payload_kg_per_m,
            expected_total_n_per_m / GRAVITY_M_S2 - 7.2,
        )
        self.assertEqual(result.governing_limit, "deflection")

    def test_uses_optional_allowable_bending_stress(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=200,
            support_span_m=3.7,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            allowable_bending_stress_mpa=5,
        )

        self.assertIsNotNone(result.bending_payload_kg_per_m)
        self.assertEqual(result.governing_limit, "bending")
        self.assertEqual(
            result.governing_payload_kg_per_m,
            result.bending_payload_kg_per_m,
        )

    def test_converts_plan_snow_load_using_angle_and_spacing(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
        )

        roof_cosine = cos(radians(36.65))
        self.assertAlmostEqual(result.roof_cosine, roof_cosine)
        self.assertAlmostEqual(
            result.snow_vertical_n_per_m,
            1500 * 0.8 * roof_cosine,
        )
        self.assertAlmostEqual(
            result.snow_transverse_n_per_m,
            1500 * 0.8 * roof_cosine**2,
        )
        self.assertAlmostEqual(
            result.snow_deflection_m,
            result.maximum_deflection_m
            * (
                result.self_transverse_n_per_m
                + result.snow_transverse_n_per_m
            )
            / result.deflection_total_n_per_m,
        )

    def test_rejects_non_positive_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "width_mm"):
            calculate_rafter_load(
                width_mm=0,
                height_mm=200,
                support_span_m=3.7,
                deflection_ratio=300,
                elastic_modulus_gpa=11,
            )
        with self.assertRaisesRegex(ValueError, "roof_angle_degrees"):
            calculate_rafter_load(
                width_mm=80,
                height_mm=200,
                support_span_m=3.7,
                deflection_ratio=300,
                elastic_modulus_gpa=11,
                roof_angle_degrees=90,
            )

    def test_checks_roof_layers_snow_creep_and_design_strength(self) -> None:
        check = calculate_roof_check(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Tiles": 50, "Insulation": 20},
        )

        cosine = cos(radians(36.65))
        layer_transverse = 70 * GRAVITY_M_S2 * 0.8 * cosine
        expected_permanent = (
            check.rafter.self_transverse_n_per_m + layer_transverse
        )
        self.assertEqual(check.roof_layer_mass_kg_m2, 70)
        self.assertEqual(check.missing_roof_layers, ())
        self.assertAlmostEqual(
            check.permanent_transverse_n_per_m,
            expected_permanent,
        )
        self.assertAlmostEqual(
            check.design_transverse_n_per_m,
            1.35 * expected_permanent
            + 1.5 * check.rafter.snow_transverse_n_per_m,
        )
        self.assertAlmostEqual(
            check.final_deflection_m,
            check.permanent_immediate_deflection_m * 1.8
            + check.snow_immediate_deflection_m,
        )
        self.assertGreater(check.bending_resistance_nm, 0)
        self.assertGreater(check.shear_resistance_n, 0)
        self.assertGreater(check.bearing_resistance_n, 0)

    def test_marks_unentered_roof_layers_as_missing(self) -> None:
        check = calculate_roof_check(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Tiles": 50, "Unknown": None},
        )

        self.assertEqual(check.roof_layer_mass_kg_m2, 50)
        self.assertEqual(check.missing_roof_layers, ("Unknown",))

    def test_purlin_uses_sloping_dead_and_horizontal_snow_tributaries(
        self,
    ) -> None:
        check = calculate_purlin_check(
            width_mm=160,
            height_mm=280,
            support_spans_m=(3.7, 4.75, 2.75),
            upper_rafter_length_m=1.08,
            lower_rafter_span_m=3.7,
            roof_angle_degrees=35.84,
            rafter_width_mm=100,
            rafter_height_mm=180,
            rafter_spacing_m=0.82,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            snow_load_kn_m2=1.7,
            roof_layers_kg_m2={"Layers": 100, "Unknown": None},
            additional_permanent_load_kn_m=0.2,
            timber_density_kg_m3=450,
            bearing_length_mm=240,
        )

        expected_slope_width = 1.08 + 3.7 / 2
        expected_horizontal_width = expected_slope_width * cos(
            radians(35.84)
        )
        expected_rafter_mass = (
            450 * 0.1 * 0.18 * expected_slope_width / 0.82
        )
        expected_transferred_mass = (
            100 * expected_slope_width
            + expected_rafter_mass
            + 0.2 * 1000 / GRAVITY_M_S2
        )

        self.assertAlmostEqual(
            check.tributary_slope_width_m,
            expected_slope_width,
        )
        self.assertAlmostEqual(
            check.tributary_horizontal_width_m,
            expected_horizontal_width,
        )
        self.assertAlmostEqual(
            check.rafter_line_mass_kg_m,
            expected_rafter_mass,
        )
        self.assertAlmostEqual(
            check.roof_snow_line_load_kn_m,
            1.7 * expected_horizontal_width,
        )
        self.assertAlmostEqual(
            check.permanent_line_load_kn_m,
            (450 * 0.16 * 0.28 + expected_transferred_mass)
            * GRAVITY_M_S2
            / 1000,
        )
        self.assertLess(min(check.design_response.support_moments_nm), 0)
        self.assertEqual(len(check.final_deflection_utilizations), 3)
        self.assertEqual(check.missing_roof_layers, ("Unknown",))

    def test_continuous_beam_matches_two_equal_span_solution(self) -> None:
        span = 4.0
        load = 1000.0
        response = calculate_continuous_beam_response(
            span_lengths_m=(span, span),
            uniform_loads_n_per_m=(load, load),
            elastic_modulus_pa=11e9,
            second_moment_m4=0.0001,
        )

        self.assertAlmostEqual(
            response.support_moments_nm[1],
            -load * span**2 / 8,
        )
        self.assertAlmostEqual(
            response.span_positive_moments_nm[0],
            9 * load * span**2 / 128,
        )
        self.assertAlmostEqual(
            response.support_reactions_n[0],
            3 * load * span / 8,
        )
        self.assertAlmostEqual(
            response.support_reactions_n[1],
            5 * load * span / 4,
        )

    def test_main_checks_main_and_dormer_with_shared_parameters(self) -> None:
        output = StringIO()
        arguments = [
            "rafter_load.py",
            "--width",
            "100",
            "--height",
            "180",
            "--span",
            "3.75",
            "--angle",
            "36.65",
            "--dormer-span",
            "3.1",
            "--dormer-angle",
            "17.03",
        ]
        with patch("sys.argv", arguments), redirect_stdout(output):
            main()

        report = output.getvalue()
        self.assertIn("Shared rafter: 100 × 180 mm", report)
        self.assertIn("Main roof:\n  Support span: 3.75 m", report)
        self.assertIn(
            "Dormer roof:\n  Support span: 3.1 m; roof angle: 17.03°",
            report,
        )
        self.assertIn("Governing rafter cases:", report)
        self.assertIn(
            f"Shared purlin: {PURLIN_WIDTH_MM:g} × "
            f"{PURLIN_HEIGHT_MM:g} mm",
            report,
        )
        self.assertIn("Street-side continuous purlin:", report)
        self.assertNotIn("Dormer roof onto purlin:", report)
        self.assertIn("Support moments:", report)
        self.assertIn(
            "OVERALL RESULT FOR CHECKS ABOVE:\n  EVERYTHING PASSED.",
            report,
        )

    def test_main_reports_failures_in_overall_result(self) -> None:
        output = StringIO()
        arguments = [
            "rafter_load.py",
            "--width",
            "40",
            "--height",
            "80",
            "--purlin-width",
            "60",
            "--purlin-height",
            "100",
        ]
        with patch("sys.argv", arguments), redirect_stdout(output):
            main()

        report = output.getvalue()
        self.assertIn("FAIL", report)
        self.assertIn(
            "OVERALL RESULT FOR CHECKS ABOVE:\n"
            "  THERE ARE FAILURES. Review the checks marked FAIL above.",
            report,
        )

    def test_roof_defaults_are_valid_inputs(self) -> None:
        self.assertGreater(DORMER_SUPPORT_SPAN_M, 0)
        self.assertGreater(DORMER_ROOF_ANGLE_DEGREES, 0)

    def test_purlin_defaults_match_the_modeled_beam(self) -> None:
        self.assertGreater(PURLIN_WIDTH_MM, 0)
        self.assertGreater(PURLIN_HEIGHT_MM, 0)
        self.assertEqual(PURLIN_SPANS_M[1], PURLIN_SUPPORT_SPAN_M)
        self.assertEqual(len(PURLIN_SPANS_M), 3)
        self.assertTrue(all(span > 0 for span in PURLIN_SPANS_M))


if __name__ == "__main__":
    unittest.main()
