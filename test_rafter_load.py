import unittest
from contextlib import redirect_stdout
from io import StringIO
from math import cos, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory
from rafter_load import (
    GRAVITY_M_S2,
    ROOF_LAYERS_KG_M2,
    SNOW_LOAD_KN_M2,
    _status,
    _status_cz,
    calculate_continuous_beam_response,
    calculate_rafter_load,
    calculate_purlin_check,
    check_continuous_purlin,
    calculate_roof_check,
    calculation_report,
    check_purlin,
    check_rafter,
)


class RafterLoadTests(unittest.TestCase):
    def test_utilization_must_be_strictly_below_one(self) -> None:
        self.assertEqual(_status(0.999), "PASS")
        self.assertEqual(_status(1.0), "FAIL")
        self.assertEqual(_status(1.001), "FAIL")
        self.assertEqual(_status_cz(0.999), "VYHOVUJE")
        self.assertEqual(_status_cz(1.0), "NEVYHOVUJE")
        self.assertEqual(_status_cz(1.001), "NEVYHOVUJE")

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
        bearing_angle = radians(90 - 36.65)
        compression_parallel_pa = (
            21.0 * 1e6 * 0.8 / 1.3
        )
        compression_perpendicular_pa = (
            2.5 * 1e6 * 0.8 / 1.3
        )
        expected_bearing_strength_pa = compression_parallel_pa / (
            compression_parallel_pa / compression_perpendicular_pa
            * sin(bearing_angle) ** 2
            + cos(bearing_angle) ** 2
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
        self.assertAlmostEqual(check.bearing_angle_degrees, 90 - 36.65)
        self.assertAlmostEqual(
            check.design_support_reaction_n,
            check.design_shear_force_n / cosine,
        )
        self.assertAlmostEqual(
            check.design_bearing_strength_pa,
            expected_bearing_strength_pa,
        )
        self.assertAlmostEqual(
            check.bearing_area_m2,
            0.08 * 50 / 1000,
        )
        self.assertAlmostEqual(
            check.bearing_resistance_n,
            expected_bearing_strength_pa * check.bearing_area_m2,
        )
        self.assertAlmostEqual(
            check.bearing_utilization,
            check.design_support_reaction_n / check.bearing_resistance_n,
        )
        self.assertGreater(check.bearing_resistance_n, 0)

    def test_rafter_bearing_length_is_configurable(self) -> None:
        shared_arguments = {
            "width_mm": 80,
            "height_mm": 180,
            "support_span_m": 3.75,
            "deflection_ratio": 300,
            "elastic_modulus_gpa": 11,
            "roof_angle_degrees": 36.65,
            "rafter_spacing_m": 0.8,
            "snow_load_kn_m2": 1.5,
            "roof_layers_kg_m2": {"Layers": 70},
        }
        default_check = calculate_roof_check(**shared_arguments)
        double_bearing_check = calculate_roof_check(
            **shared_arguments,
            bearing_length_mm=2 * 50,
        )

        self.assertAlmostEqual(
            double_bearing_check.bearing_resistance_n,
            2 * default_check.bearing_resistance_n,
        )
        self.assertAlmostEqual(
            double_bearing_check.bearing_utilization,
            default_check.bearing_utilization / 2,
        )

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


    def test_simple_purlin_is_one_simply_supported_span(self) -> None:
        span = 4.75
        check = calculate_purlin_check(
            width_mm=160,
            height_mm=280,
            support_spans_m=(span,),
            upper_rafter_length_m=1.08,
            lower_rafter_span_m=3.7,
            roof_angle_degrees=35.84,
            rafter_width_mm=100,
            rafter_height_mm=180,
            rafter_spacing_m=0.82,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            snow_load_kn_m2=1.7,
            roof_layers_kg_m2={"Layers": 100},
            additional_permanent_load_kn_m=0.2,
            timber_density_kg_m3=450,
            bearing_length_mm=120,
        )

        design_line_load_n_m = (
            1.35 * check.permanent_line_load_kn_m
            + 1.5 * check.roof_snow_line_load_kn_m
        ) * 1000
        second_moment_m4 = 0.16 * 0.28**3 / 12
        expected_immediate_deflection = (
            5
            * (
                check.permanent_line_load_kn_m
                + check.roof_snow_line_load_kn_m
            )
            * 1000
            * span**4
            / (384 * 11e9 * second_moment_m4)
        )

        self.assertEqual(check.span_lengths_m, (span,))
        self.assertEqual(check.design_response.support_moments_nm, (0.0, 0.0))
        self.assertAlmostEqual(
            check.immediate_response.span_max_abs_deflections_m[0],
            expected_immediate_deflection,
        )
        self.assertAlmostEqual(
            check.design_response.span_positive_moments_nm[0],
            design_line_load_n_m * span**2 / 8,
        )
        self.assertAlmostEqual(
            max(check.design_response.support_reactions_n),
            design_line_load_n_m * span / 2,
        )

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

    def test_check_calls_print_and_append_the_same_results(self) -> None:
        output = StringIO()
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "roof.pdf"
            with redirect_stdout(output):
                with calculation_report(report_path):
                    c22_rafter = check_rafter(
                        title="Krokve C22",
                        material="c22",
                        width=0.08,
                        height=0.20,
                        span=3.85,
                        spacing=0.75,
                        roof_angle=35.83,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                    )
                    c24_rafter = check_rafter(
                        title="Krokve C24",
                        material="c24",
                        width=0.08,
                        height=0.20,
                        span=3.85,
                        spacing=0.75,
                        roof_angle=35.83,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                    )
                    purlin = check_purlin(
                        title="Vaznice C22",
                        material="c22",
                        width=0.24,
                        height=0.32,
                        span=4.80,
                        rafter_length_above=1.05,
                        lower_rafter_span=3.85,
                        roof_angle=35.83,
                        rafter_width=0.08,
                        rafter_height=0.20,
                        rafter_spacing=0.75,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                        bearing_length=0.12,
                    )
                    continuous_purlin = check_continuous_purlin(
                        title="Souvislá vaznice C22",
                        material="c22",
                        width=0.24,
                        height=0.32,
                        spans=(3.74, 4.80, 2.75),
                        rafter_length_above=1.05,
                        lower_rafter_span=3.85,
                        roof_angle=35.83,
                        rafter_width=0.08,
                        rafter_height=0.20,
                        rafter_spacing=0.75,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                        bearing_length=0.24,
                    )

            terminal = output.getvalue()
            self.assertIn("Krokve C22:", terminal)
            self.assertIn("Krokve C24:", terminal)
            self.assertIn("Vaznice C22:", terminal)
            self.assertIn("Souvislá vaznice C22:", terminal)
            self.assertIn("Final deflection with k_def=0.8", terminal)
            self.assertNotIn("Independent purlin pieces:", terminal)
            self.assertIn("OVERALL RESULT:", terminal)
            self.assertIn("PDF REPORT:", terminal)
            self.assertTrue(report_path.read_bytes().startswith(b"%PDF-"))
            self.assertGreater(report_path.stat().st_size, 10_000)

        self.assertAlmostEqual(c22_rafter.rafter.self_mass_kg_per_m, 7.2)
        self.assertGreater(
            c24_rafter.bending_resistance_nm,
            c22_rafter.bending_resistance_nm,
        )
        self.assertLess(
            c24_rafter.characteristic_deflection_m,
            c22_rafter.characteristic_deflection_m,
        )
        self.assertAlmostEqual(
            purlin.roof_snow_line_load_kn_m,
            1.5 * purlin.tributary_horizontal_width_m,
        )
        self.assertEqual(purlin.span_lengths_m, (4.8,))
        self.assertEqual(
            continuous_purlin.span_lengths_m,
            (3.74, 4.8, 2.75),
        )

    def test_checks_require_one_consistent_report_context(self) -> None:
        arguments = {
            "title": "Krokve",
            "material": "c22",
            "width": 0.08,
            "height": 0.20,
            "span": 3.85,
            "spacing": 0.75,
            "roof_angle": 35.83,
            "max_deflection": 300,
            "snow_load": 1.5,
            "roof_layers": {"Layers": 130},
        }
        with self.assertRaisesRegex(RuntimeError, "calculation_report"):
            check_rafter(**arguments)

        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "roof.pdf"
            with redirect_stdout(StringIO()):
                with calculation_report(report_path):
                    check_rafter(**arguments)
                    with self.assertRaisesRegex(
                        ValueError,
                        "same snow_load",
                    ):
                        check_rafter(
                            **{
                                **arguments,
                                "title": "Jiná krokev",
                                "snow_load": 1.6,
                            }
                        )
                    with self.assertRaisesRegex(
                        ValueError,
                        "unknown timber material",
                    ):
                        check_rafter(
                            **{
                                **arguments,
                                "title": "Neznámý materiál",
                                "material": "c99",
                            }
                        )

    def test_project_uses_one_snow_load(self) -> None:
        self.assertEqual(SNOW_LOAD_KN_M2, 1.5)
if __name__ == "__main__":


    unittest.main()
