import ast
from contextlib import redirect_stdout
from dataclasses import replace
import importlib.util
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from roof_frame_3d import (
    HouseInputs,
    RoofLayout,
    Settings,
    Timber,
    CollarTieParameters,
    add_collar_ties,
    build_roof_model,
    check_equilibrium,
    chord_result_columns,
    deformed_member_point,
    horizontal_stiffness_argument,
    main,
    maximum_chord_departure,
    member_rows,
    orient_section,
    plot_model,
    plot_plan_report,
    plan_deflection_status,
    plan_force_arrow,
    plan_collar_force_arrows,
    plan_member_polygon,
    print_summary,
    print_ring_beam_rafter_forces,
    purlin_chord,
    rafter_chord,
    solve_roof_model,
    support_rows,
    tributary_intervals,
    wall_plate_connection_rows,
)

HOUSE = Path(__file__).with_name("house_ifc.py")
HAS_PYNITE = importlib.util.find_spec("Pynite") is not None


class PolynomialMember:
    """Analytical member with prescribed local displacements, independent of PyNite."""

    def __init__(self, displacement, length=4.0, angle=0.0):
        self.displacement = displacement
        self.length = length
        c, s = np.cos(angle), np.sin(angle)
        self.rotation = np.array(((c, 0, s), (-s, 0, c), (0, -1, 0)))
        self.i_node = SimpleNamespace(X=0.0, Y=0.0, Z=0.0)
        self.j_node = SimpleNamespace(X=length * c, Y=0.0, Z=length * s)

    def L(self):
        return self.length

    def T(self):
        matrix = np.eye(12)
        matrix[:3, :3] = self.rotation
        return matrix

    def deflection(self, direction, station, combo):
        return self.displacement(station)[("dx", "dy", "dz").index(direction)]


class ChordTests(unittest.TestCase):
    def test_uniform_load_exact_peak_on_horizontal_and_sloping_beam(self):
        length, q, ei = 4.0, 1000.0, 11e9 * Timber(0.08, 0.2).properties[2]
        member_displacement = lambda x: (
            0.0,
            -q * x * (length**3 - 2 * length * x * x + x**3) / (24 * ei),
            0.0,
        )
        expected = 5 * q * length**4 / (384 * ei)
        for angle in (0.0, 0.63):
            distance, station = maximum_chord_departure(
                PolynomialMember(member_displacement, length, angle), "SLS_test", 0.0, length
            )
            self.assertAlmostEqual(distance, expected, places=10)
            self.assertAlmostEqual(station, length / 2, places=7)

    def test_rigid_translation_and_rotation_are_removed(self):
        for displacement in (
            lambda x: (0.013, -0.008, 0.005),
            lambda x: (0.013 - 0.001 * x, -0.008 + 0.002 * x, 0.005 + 0.003 * x),
        ):
            distance, _ = maximum_chord_departure(
                PolynomialMember(displacement, angle=0.7), "SLS_test", 0.3, 3.6
            )
            self.assertLess(distance, 1e-12)

    def test_asymmetric_peak_is_not_limited_to_sampling_grid(self):
        length = 4.0
        member = PolynomialMember(lambda x: (0.0, 0.002 * x * (length - x) ** 2, 0.0))
        distance, station = maximum_chord_departure(member, "SLS_test", 0.0, length)
        self.assertAlmostEqual(station, length / 3, places=7)
        self.assertAlmostEqual(distance, 0.002 * 4 * length**3 / 27, places=10)

    def test_combines_both_transverse_components(self):
        member = PolynomialMember(
            lambda x: (0.0, 0.001 * x * (4 - x), 0.002 * x * (4 - x)), angle=0.5
        )
        distance, station = maximum_chord_departure(member, "SLS_test", 0.0, 4.0)
        self.assertAlmostEqual(distance, np.sqrt(5) * 0.004, places=10)
        self.assertAlmostEqual(station, 2.0, places=7)

    def test_displaced_endpoint_axis_and_eave_exclusion(self):
        member = PolynomialMember(lambda x: (0.001 * x, -0.01 + 0.003 * x, 0.0))
        with self.assertRaises(ValueError):
            maximum_chord_departure(member, "SLS_test", -1.0, 3.0)
        with self.assertRaises(ValueError):
            maximum_chord_departure(member, "SLS_test", 2.0, 2.0)
        # A free overhang bends outside the requested 1..3 m interval only.
        member.displacement = lambda x: (
            0.0,
            0.001 * (max(1 - x, 0) ** 2 + max(x - 3, 0) ** 2),
            0.0,
        )
        with patch("roof_frame_3d.displacement_breakpoints", return_value={0.0, 1.0, 3.0, 4.0}):
            distance, _ = maximum_chord_departure(member, "SLS_test", 1.0, 3.0)
        self.assertLess(distance, 1e-12)

    def test_piecewise_polynomial_peak_at_interior_boundary(self):
        peak = 1.37
        member = PolynomialMember(
            lambda x: (0.0, 0.01 * x / peak if x <= peak else 0.01 * (4 - x) / (4 - peak), 0.0)
        )
        with patch("roof_frame_3d.displacement_breakpoints", return_value={0.0, peak, 4.0}):
            distance, station = maximum_chord_departure(member, "SLS_test", 0.0, 4.0)
        self.assertAlmostEqual(distance, 0.01, places=10)
        self.assertAlmostEqual(station, peak, places=8)

    def test_intermediate_support_sag_remains_in_whole_rafter_measure(self):
        # Both endpoints settle 10 mm, while the purlin at midspan settles
        # another 6 mm. Only the common settlement disappears from the result.
        member = PolynomialMember(lambda x: (0.0, -0.01 - 0.0015 * x * (4 - x), 0.0))
        distance, station = maximum_chord_departure(member, "SLS_test", 0.0, 4.0)
        self.assertAlmostEqual(distance, 0.006, places=10)
        self.assertAlmostEqual(station, 2.0, places=7)

    def test_nonpolynomial_solver_is_not_silently_approximated(self):
        member = PolynomialMember(lambda x: (0.0, 0.01 * np.sin(5 * x), 0.0))
        with self.assertRaisesRegex(ValueError, "first-order polynomial"):
            maximum_chord_departure(member, "SLS_test", 0.0, 4.0)


class InputTests(unittest.TestCase):
    def test_reader_never_executes_house(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            path.write_text(
                'raise RuntimeError("must not execute")\na = 2\nb = (a + 3)/2\n', encoding="utf-8"
            )
            data = HouseInputs(path)
            self.assertEqual(data.get("b"), 2.5)
            with self.assertRaises(ValueError):
                data.evaluate(ast.parse('__import__("os").system("false")', mode="eval").body)

    def test_layout_matches_current_inputs(self):
        layout = RoofLayout.from_house(HOUSE)
        inputs = HouseInputs(HOUSE)
        paired = sum(isinstance(entry, tuple) for entry in inputs.get("rafters"))
        categories = [b.category for b in layout.beams]
        self.assertEqual(categories.count("rafter"), 2 * len(inputs.get("rafters")) + paired)
        self.assertEqual(categories.count("purlin"), 6)
        self.assertEqual(categories.count("wall_plate"), 5)
        self.assertNotIn("collar", categories)
        for beam in layout.beams:
            self.assertGreater(beam.length, 0)
        for p in (b for b in layout.beams if b.category == "purlin"):
            self.assertAlmostEqual(p.start[2] + p.timber.height / 2, inputs.get("PURLIN_TOP_Z"))
            self.assertTrue(all(p.start[0] <= x <= p.end[0] for x in p.bearings))
            wall_centres = (
                inputs.get("BWT") / 2,
                inputs.get("wall2_x") - inputs.get("BWT") / 2,
                inputs.get("wall3_x") - inputs.get("BWT") / 2,
                inputs.get("HOUSE_WIDTH") - inputs.get("BWT") / 2,
            )
            segment = p.name.rsplit("_", 1)[1]
            index = ("left", "middle", "right").index(segment)
            np.testing.assert_allclose(p.bearings, wall_centres[index : index + 2])

    def test_default_material_is_c22_for_all_timber(self):
        self.assertEqual(Timber(0.08, 0.2).material, "C22")
        self.assertTrue(all(b.timber.material == "C22" for b in RoofLayout.from_house(HOUSE).beams))
        mixed = RoofLayout.from_house(HOUSE, rafter_material="C24", beam_material="C22")
        for beam in mixed.beams:
            self.assertEqual(beam.timber.material, "C24" if beam.category == "rafter" else "C22")

    def test_stronger_rafter_and_split_guard(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            source = HOUSE.read_text(encoding="utf-8")
            path.write_text(
                source.replace("\t8.55+0.67,", "\tStrongerRafter(8.55+0.67),"), encoding="utf-8"
            )
            layout = RoofLayout.from_house(path)
            beam = next(b for b in layout.beams if b.name == "rafter_13_street")
            self.assertEqual(beam.timber.width, HouseInputs(path).get("STRONGER_RAFTER_THICKNESS"))
            path.write_text(
                source.replace("\t1.62+0.93,", "\tSplitRafter(1.62+0.93, 7),"), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "SplitRafter"):
                RoofLayout.from_house(path)

    def test_roof_opening_must_not_bridge_rafter(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            source = HOUSE.read_text(encoding="utf-8").replace(
                "roof_window_x = (rafters[2] + rafters[3]) / 2.0", "roof_window_x = rafters[2]"
            )
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "opening cuts"):
                RoofLayout.from_house(path)

    def test_invalid_sections_and_loads(self):
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Timber(bad, 0.2)
            with self.assertRaises(ValueError):
                Settings(joint_stiffness_factor=bad)
            with self.assertRaises(ValueError):
                Settings(horizontal_stiffness_kn_mm=bad)
        with self.assertRaises(ValueError):
            Settings(snow_load=-1)
        area, iy, iz, j = Timber(0.08, 0.2).properties
        self.assertAlmostEqual(area, 0.016)
        self.assertAlmostEqual(iz, 0.08 * 0.2**3 / 12)
        self.assertAlmostEqual(iy, 0.2 * 0.08**3 / 12)
        self.assertGreater(j, 0)

    def test_horizontal_stiffness_defaults_and_cli_units(self):
        self.assertGreater(Settings().roof_mass, 0)
        self.assertTrue(Settings().purlin_lateral_restraint)
        self.assertGreater(Settings().horizontal_stiffness_kn_mm, 0)
        self.assertEqual(horizontal_stiffness_argument("0.12"), 0.12)
        self.assertIsNone(horizontal_stiffness_argument("rigid"))
        import argparse

        for bad in ("0", "-1", "nan", "inf", "wrong"):
            with self.assertRaises(argparse.ArgumentTypeError):
                horizontal_stiffness_argument(bad)


class PlanReportTests(unittest.TestCase):
    @staticmethod
    def row(combo, l300, l500):
        return dict(combination=combo, chord_L300_status=l300, chord_L500_status=l500)

    def test_colours_use_worst_sls_and_ignore_uls(self):
        row = self.row
        self.assertEqual(
            plan_deflection_status(
                [row("SLS_symmetric", "PASS", "PASS"), row("ULS_symmetric", "FAIL", "FAIL")]
            ),
            "L500",
        )
        self.assertEqual(
            plan_deflection_status(
                [row("SLS_symmetric", "PASS", "PASS"), row("SLS_street", "PASS", "FAIL")]
            ),
            "L300",
        )
        self.assertEqual(
            plan_deflection_status(
                [row("SLS_symmetric", "PASS", "PASS"), row("SLS_garden", "FAIL", "FAIL")]
            ),
            "fail",
        )
        for rows in (
            [],
            [row("ULS_symmetric", "PASS", "PASS")],
            [row("SLS_symmetric", "", "")],
            [row("SLS_symmetric", "N/A", "N/A")],
        ):
            self.assertEqual(plan_deflection_status(rows), "not_assessed")

    def test_arrow_direction_and_sign_for_both_sides(self):
        for side in (-1, 1):
            for force in (-2.0, 0.0, 2.0):
                row = dict(x_m=3.2, y_m=5.0, outward_kN=force, outward_direction=side)
                start, end = plan_force_arrow(row)
                np.testing.assert_allclose(start, (3.2, 5.0))
                np.testing.assert_allclose(end - start, (0, side * np.sign(force) * 0.55))
        with self.assertRaises(ValueError):
            plan_force_arrow(row, length=0)

    def test_projected_member_width_and_original_endpoints(self):
        for beam in RoofLayout.from_house(HOUSE).beams:
            polygon = plan_member_polygon(beam)
            self.assertEqual(polygon.shape, (4, 2))
            np.testing.assert_allclose((polygon[0] + polygon[3]) / 2, beam.start[:2])
            np.testing.assert_allclose((polygon[1] + polygon[2]) / 2, beam.end[:2])
            self.assertAlmostEqual(np.linalg.norm(polygon[3] - polygon[0]), beam.timber.width)

    def test_collar_arrows_point_inward_for_compression_outward_for_tension(self):
        beam = SimpleNamespace(start=(2.0, 1.0, 4.0), end=(2.0, 5.0, 4.0))
        for force in (-3.0, 3.0):
            centre, arrows = plan_collar_force_arrows(beam, force)
            np.testing.assert_allclose(centre, (2.2, 3.0))
            self.assertEqual(len(arrows), 2)
            for tail, head in arrows:
                self.assertGreater(np.dot(head - tail, tail - centre) * np.sign(force), 0)
                self.assertAlmostEqual(np.linalg.norm(head - tail), 0.55)
                self.assertGreaterEqual(
                    min(abs(tail[1] - centre[1]), abs(head[1] - centre[1])), 0.5
                )
            np.testing.assert_allclose(
                centre, np.mean([point for arrow in arrows for point in arrow], axis=0)
            )
        self.assertEqual(plan_collar_force_arrows(beam, 0)[1], [])
        with self.assertRaises(ValueError):
            plan_collar_force_arrows(beam, float("nan"))
        for parameter in ("offset", "length", "gap"):
            with self.assertRaises(ValueError):
                plan_collar_force_arrows(beam, 1, **{parameter: 0})


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = RoofLayout.from_house(HOUSE)
        cls.free = build_roof_model(
            cls.layout, Settings(purlin_lateral_restraint=False, horizontal_stiffness_kn_mm=None)
        )
        cls.free_residuals = solve_roof_model(cls.free)
        cls.fixed = build_roof_model(cls.layout, Settings(horizontal_stiffness_kn_mm=None))
        solve_roof_model(cls.fixed)

    def test_simple_beam_matches_hand_calculation(self):
        from Pynite import FEModel3D

        model = FEModel3D()
        model.add_node("a", 0, 0, 0)
        model.add_node("b", 4, 0, 0)
        model.add_material("wood", 11e9, 0.69e9, 0.3, 4500)
        timber = Timber(0.08, 0.2)
        model.add_section("section", *timber.properties)
        model.add_member("beam", "a", "b", "wood", "section")
        member = model.members["beam"]
        orient_section(member)
        model.def_support("a", True, True, True, True, False, False)
        model.def_support("b", False, True, True, False, False, False)
        model.add_member_dist_load("beam", "FZ", -1000, -1000, case="G")
        model.add_load_combo("test", {"G": 1})
        model.analyze_linear()
        self.assertAlmostEqual(model.nodes["a"].RxnFZ["test"], 2000, places=7)
        self.assertAlmostEqual(model.nodes["b"].RxnFZ["test"], 2000, places=7)
        self.assertAlmostEqual(abs(member.moment("Mz", 2, "test")), 1000 * 4**2 / 8, places=7)
        expected = 5 * 1000 * 4**4 / (384 * 11e9 * timber.properties[2])
        displacement = member.T()[:3, :3].T @ np.array(
            [member.deflection(d, 2, "test") for d in ("dx", "dy", "dz")]
        )
        self.assertAlmostEqual(displacement[2], -expected, places=10)
        distance, station = maximum_chord_departure(member, "test", 0.0, member.L())
        self.assertAlmostEqual(distance, expected, places=10)
        self.assertAlmostEqual(station, 2.0, places=7)

    def test_rafter_reference_pairs_and_explicit_fallback(self):
        counts = {"wall_plate_to_ridge": 0, "wall_plate_to_purlin": 0, "purlin_to_ridge": 0}
        missing = 0
        for beam in (b for b in self.layout.beams if b.category == "rafter"):
            chord = rafter_chord(self.free, beam, fallback="na")
            fallback = rafter_chord(self.free, beam, fallback="supports")
            self.assertEqual(rafter_chord(self.free, beam), fallback)
            self.assertIsNotNone(fallback)
            counts[fallback.kind] += 1
            if chord is None:
                missing += 1
                self.assertNotEqual(fallback.kind, "wall_plate_to_ridge")
            else:
                self.assertEqual(chord, fallback)
                self.assertLessEqual(chord.end_m - chord.start_m, beam.length)
                plates = [s for s in self.free.rafter_seats[beam.name] if s[1] == "wall_plate"]
                ridge = (
                    self.free.model.members[beam.name].L() if beam.name.endswith("_street") else 0.0
                )
                expected = max(plates, key=lambda s: abs(s[2] - ridge))
                self.assertIn(expected[0], (chord.start_label, chord.end_label))
                self.assertIn("ridge", (chord.start_label, chord.end_label))
        self.assertEqual(
            counts, {"wall_plate_to_ridge": 26, "wall_plate_to_purlin": 8, "purlin_to_ridge": 6}
        )
        self.assertEqual(missing, 14)
        with self.assertRaises(ValueError):
            rafter_chord(self.free, self.layout.beams[0], fallback="invent")

    def test_purlin_chord_uses_actual_bearings_and_excludes_end_overhangs(self):
        for roof in (self.free, self.fixed):
            for beam in (b for b in self.layout.beams if b.category == "purlin"):
                chord = purlin_chord(roof, beam)
                self.assertEqual(chord.kind, "bearing_to_bearing")
                self.assertGreaterEqual(chord.start_m, 0)
                self.assertLessEqual(chord.end_m, beam.length)
                self.assertAlmostEqual(
                    chord.end_m - chord.start_m, max(beam.bearings) - min(beam.bearings)
                )
                for label, station, x in zip(
                    (chord.start_label, chord.end_label),
                    (chord.start_m, chord.end_m),
                    sorted(beam.bearings),
                ):
                    self.assertEqual(roof.supports[label], beam.name)
                    self.assertAlmostEqual(roof.model.nodes[label].X, x)
                    self.assertAlmostEqual(station, x - beam.start[0])
                if beam.name.endswith("_middle"):
                    self.assertAlmostEqual(chord.start_m, 0)
                    self.assertAlmostEqual(chord.end_m, beam.length)
                    inputs = HouseInputs(HOUSE)
                    self.assertAlmostEqual(
                        chord.end_m - chord.start_m, inputs.get("wall3_x") - inputs.get("wall2_x")
                    )

    def test_adjacent_purlins_have_independent_end_and_bearing_nodes(self):
        for roof in (self.free, self.fixed):
            for side in ("street", "garden"):
                members = [
                    roof.model.members[f"{side}_purlin_{part}"]
                    for part in ("left", "middle", "right")
                ]
                for left, right in zip(members, members[1:]):
                    self.assertIsNot(left.j_node, right.i_node)
                    self.assertAlmostEqual(left.j_node.X, right.i_node.X)
                    self.assertEqual(roof.supports[left.j_node.name], left.name)
                    self.assertEqual(roof.supports[right.i_node.name], right.name)
                for member in members:
                    self.assertTrue(all(sub.L() > 1e-8 for sub in member.sub_members.values()))
                    for combo in roof.model.load_combos:
                        # Coincident ends must not transfer bending moments.
                        for end in (0.0, member.L()):
                            self.assertAlmostEqual(member.moment("My", end, combo), 0.0, places=5)
                            self.assertAlmostEqual(member.moment("Mz", end, combo), 0.0, places=5)

    def test_purlin_node_isolation_with_equal_and_unequal_heights(self):
        for extra_height in (0.0, 0.08):
            beams = []
            for beam in self.layout.beams:
                if beam.category == "purlin":
                    height = 0.24 + (extra_height if beam.name.endswith("_middle") else 0.0)
                    z = beam.start[2] + beam.timber.height / 2 - height / 2
                    beam = replace(
                        beam,
                        start=(*beam.start[:2], z),
                        end=(*beam.end[:2], z),
                        timber=replace(beam.timber, height=height),
                    )
                beams.append(beam)
            layout = replace(self.layout, beams=tuple(beams))
            roof = build_roof_model(layout, Settings())
            self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
            self.assertEqual(sum("purlin" in b for b in roof.supports.values()), 12)
            for side in ("street", "garden"):
                members = [
                    roof.model.members[f"{side}_purlin_{part}"]
                    for part in ("left", "middle", "right")
                ]
                for left, right in zip(members, members[1:]):
                    self.assertIsNot(left.j_node, right.i_node)
                    self.assertAlmostEqual(left.j_node.X, right.i_node.X)
                    if extra_height == 0:
                        self.assertAlmostEqual(left.j_node.Z, right.i_node.Z)
                    else:
                        self.assertNotAlmostEqual(left.j_node.Z, right.i_node.Z)
                for member in members:
                    self.assertAlmostEqual(member.moment("Mz", 0.0, "SLS_symmetric"), 0.0, places=5)
                    self.assertAlmostEqual(
                        member.moment("Mz", member.L(), "SLS_symmetric"), 0.0, places=5
                    )

    def test_purlin_chord_rejects_missing_or_extra_bearing(self):
        beam = next(b for b in self.layout.beams if b.category == "purlin")
        chord = purlin_chord(self.free, beam)
        supports = self.free.supports.copy()
        del supports[chord.start_label]
        with self.assertRaisesRegex(ValueError, "exactly two bearings"):
            purlin_chord(SimpleNamespace(model=self.free.model, supports=supports), beam)
        supports = self.free.supports.copy()
        extra = next(name for name, b in supports.items() if b != beam.name)
        supports[extra] = beam.name
        with self.assertRaisesRegex(ValueError, "exactly two bearings"):
            purlin_chord(SimpleNamespace(model=self.free.model, supports=supports), beam)

    def test_deflection_status_is_strict_and_sls_only(self):
        for name in ("rafter_04_street", "street_purlin_middle"):
            beam = next(b for b in self.layout.beams if b.name == name)
            chord = (
                rafter_chord(self.free, beam)
                if beam.category == "rafter"
                else purlin_chord(self.free, beam)
            )
            span = chord.end_m - chord.start_m
            with patch(
                "roof_frame_3d.maximum_chord_departure", return_value=(span / 300, chord.start_m)
            ):
                row = chord_result_columns(self.free, beam, "SLS_symmetric")
                self.assertEqual(row["chord_L300_status"], "FAIL")
                self.assertEqual(row["chord_L500_status"], "FAIL")
                self.assertEqual(
                    chord_result_columns(self.free, beam, "ULS_symmetric")["chord_L300_status"],
                    "NOT_CHECKED_ULS",
                )
            with patch(
                "roof_frame_3d.maximum_chord_departure", return_value=(span / 500, chord.start_m)
            ):
                row = chord_result_columns(self.free, beam, "SLS_symmetric")
                self.assertEqual(row["chord_L300_status"], "PASS")
                self.assertEqual(row["chord_L500_status"], "FAIL")

    def test_actual_chord_maximum_matches_dense_sampling(self):
        beams = [next(b for b in self.layout.beams if b.name == "rafter_04_street")]
        beams.extend(
            next(
                b
                for b in self.layout.beams
                if b.category == "rafter"
                and rafter_chord(self.free, b, fallback="supports").kind == kind
            )
            for kind in ("purlin_to_ridge", "wall_plate_to_purlin")
        )
        beams.extend(b for b in self.layout.beams if b.category == "purlin")
        for beam in beams:
            name, fallback = beam.name, "supports"
            chord = (
                rafter_chord(self.free, beam, fallback=fallback)
                if beam.category == "rafter"
                else purlin_chord(self.free, beam)
            )
            member = self.free.model.members[name]
            # Select a real asymmetric combination without assuming its label.
            combo = next(
                c
                for c in self.free.model.load_combos
                if c.startswith("SLS_") and c != "SLS_symmetric"
            )
            distance, at = maximum_chord_departure(member, combo, chord.start_m, chord.end_m)
            a = deformed_member_point(member, chord.start_m, combo)
            axis = deformed_member_point(member, chord.end_m, combo) - a
            axis /= np.linalg.norm(axis)
            sampled = []
            for station in np.linspace(chord.start_m, chord.end_m, 1001):
                delta = deformed_member_point(member, station, combo) - a
                sampled.append(np.linalg.norm(delta - delta.dot(axis) * axis))
            self.assertGreaterEqual(distance + 1e-12, max(sampled))
            self.assertAlmostEqual(distance, max(sampled), delta=1e-8)
            self.assertTrue(chord.start_m <= at <= chord.end_m)

    def test_strong_section_axis_follows_global_up(self):
        for beam in self.layout.beams:
            member = self.free.model.members[beam.name]
            local_x, local_y, _ = member.T()[:3, :3]
            expected = np.array((0.0, 0.0, 1.0)) - local_x[2] * local_x
            expected /= np.linalg.norm(expected)
            np.testing.assert_allclose(local_y, expected, atol=1e-10)

    def test_force_and_moment_equilibrium(self):
        self.assertLess(max(self.free_residuals.values()), 1e-8)
        self.assertLess(max(check_equilibrium(self.fixed).values()), 1e-8)

    def test_snow_covers_roof_projection_once_with_one_cosine(self):
        expected_area = sum((p.x_max - p.x_min) * (p.y_max - p.y_min) for p in self.layout.patches)
        actual_force = -sum(
            q * (b - a) for _, case, q, a, b in self.free.loads if case.startswith("S_")
        )
        self.assertAlmostEqual(
            actual_force, expected_area * self.free.settings.snow_load * 1000, places=6
        )

    def test_roof_mass_and_member_weight_no_joint_or_ceiling_weight(self):
        rafters = {b.name: b for b in self.layout.beams}
        area = 0.0
        for patch in self.layout.patches:
            beams = [rafters[name] for name in patch.rafters]
            intervals = tributary_intervals(beams, -2, 20)
            for beam in beams:
                lo, hi = intervals[beam.name]
                width = max(0, min(hi, patch.x_max) - max(lo, patch.x_min))
                cosine = abs(beam.end[1] - beam.start[1]) / beam.length
                area += width * (patch.y_max - patch.y_min) / cosine
        actual = -sum(q * (b - a) for _, case, q, a, b in self.free.loads if case == "G")
        timber = sum(b.length * b.timber.properties[0] for b in self.layout.beams) * 450 * 10
        self.assertAlmostEqual(actual, area * self.free.settings.roof_mass * 10 + timber, places=6)
        self.assertFalse(any(name.startswith("seat_") for name, case, q, a, b in self.free.loads))

    def test_seats_do_not_transfer_rafter_plane_end_moment(self):
        for name in self.free.connections:
            member = self.free.model.members[name]
            # Both bending rotations released at the UPPER (rafter) end.
            self.assertTrue(member.Releases[10] and member.Releases[11])
            for combo in self.free.model.load_combos:
                self.assertAlmostEqual(member.moment("My", member.L(), combo), 0, places=6)
                self.assertAlmostEqual(member.moment("Mz", member.L(), combo), 0, places=6)
        # Rafters remain continuous through their purlin seat.
        member = self.free.model.members["rafter_04_street"]
        self.assertGreater(len(member.sub_members), 1)
        self.assertTrue(
            any(
                abs(sub.moment("Mz", sub.L(), "ULS_symmetric")) > 10
                for sub in list(member.sub_members.values())[:-1]
            )
        )

    def test_purlins_are_not_vertically_fixed_at_each_rafter(self):
        free = self.free
        purlin = free.model.members["garden_purlin_middle"]
        self.assertLess(purlin.deflection("dy", purlin.L() / 2, "SLS_symmetric"), -0.001)
        supports = [n for n, b in free.supports.items() if "purlin" in b]
        self.assertEqual(len(supports), 12)
        for name in supports:
            self.assertFalse(free.model.nodes[name].support_DY)
            self.assertAlmostEqual(free.model.nodes[name].RxnFY["ULS_symmetric"], 0, places=6)

    def test_stiff_joint_convergence(self):
        roof = build_roof_model(
            self.layout,
            Settings(
                joint_stiffness_factor=100,
                purlin_lateral_restraint=False,
                horizontal_stiffness_kn_mm=None,
            ),
        )
        solve_roof_model(roof)

        def outward(model):
            return sum(
                row["outward_kN"]
                for row in support_rows(model)
                if row["combination"] == "ULS_symmetric"
                and "street" in row["member"]
                and "wall_plate" in row["member"]
            )

        self.assertAlmostEqual(outward(roof) / outward(self.free), 1, delta=0.002)

    def test_csv_results_and_plot(self):
        members, supports = member_rows(self.free), support_rows(self.free)
        self.assertEqual(len(members), len(self.layout.beams) * 6)
        self.assertEqual(len(supports), len(self.free.supports) * 6)
        self.assertTrue(all(isfinite_number(row["Mz_max_kNm"]) for row in members))
        self.assertFalse(any(row["chord_L300_status"] == "N/A" for row in members))
        self.assertEqual(
            sum(row["chord_reference"] == "bearing_to_bearing" for row in members), 6 * 6
        )
        for row in members:
            self.assertEqual(row["material"], "C22")
            if row["category"] == "wall_plate":
                self.assertEqual(row["chord_reference"], "")
        for row in members:
            if row["chord_span_m"] != "":
                self.assertGreater(row["chord_span_m"], 0)
                self.assertTrue(isfinite_number(row["chord_max_departure_mm"]))
                self.assertTrue(isfinite_number(row["vertical_min_mm"]))
        for row in members:
            member = self.free.model.members[row["member"]]
            self.assertAlmostEqual(row["N_min_kN"], -member.max_axial(row["combination"]) / 1000)
            self.assertAlmostEqual(row["N_max_kN"], -member.min_axial(row["combination"]) / 1000)
        output = StringIO()
        with redirect_stdout(output):
            print_summary(self.free, members, supports, self.free_residuals)
        text = output.getvalue()
        self.assertIn("Purlin departure from displaced bearing chord", text)
        self.assertIn("rafter: C22; purlin: C22; wall_plate: C22", text)
        for beam in (b for b in self.layout.beams if b.category == "purlin"):
            self.assertIn(f"{beam.name} [bearing_to_bearing]", text)
        short = next(b for b in self.layout.beams if b.name.endswith("_dormer"))
        self.assertEqual(
            chord_result_columns(self.free, short, "SLS_symmetric", fallback="na")[
                "chord_L300_status"
            ],
            "N/A",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.png"
            plot_model(self.free, path)
            self.assertGreater(path.stat().st_size, 10000)


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class SpringSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = RoofLayout.from_house(HOUSE)
        # Use a deliberately flexible case, independent of the user's chosen
        # default stiffness for subsequent roof experiments.
        cls.roof = build_roof_model(cls.layout, Settings(horizontal_stiffness_kn_mm=0.12))
        cls.residuals = solve_roof_model(cls.roof)

    def test_all_horizontal_bearings_share_stiffness_vertical_and_roll_unchanged(self):
        roof = self.roof
        expected = roof.settings.horizontal_stiffness_kn_mm * 1e6
        for name in roof.supports:
            node = roof.model.nodes[name]
            self.assertFalse(node.support_DX)
            self.assertFalse(node.support_DY)
            self.assertTrue(node.support_DZ)
            self.assertTrue(node.support_RX)
            self.assertFalse(node.support_RY)
            self.assertFalse(node.support_RZ)
            for axis in ("DX", "DY"):
                self.assertEqual(getattr(node, "spring_" + axis), [expected, None, True])
                for combo in roof.model.load_combos:
                    # Reaction ON timber is -k * movement; exported load TO
                    # the support has the opposite sign.
                    self.assertAlmostEqual(
                        getattr(node, "RxnF" + axis[-1])[combo],
                        -expected * getattr(node, axis)[combo],
                        places=6,
                    )
        self.assertLess(max(self.residuals.values()), 1e-8)

    def test_free_purlin_option_keeps_y_free_but_still_springs_x(self):
        roof = build_roof_model(self.layout, Settings(purlin_lateral_restraint=False))
        for name, beam in roof.supports.items():
            node = roof.model.nodes[name]
            self.assertIsNotNone(node.spring_DX[0])
            if "purlin" in beam:
                self.assertFalse(node.support_DY)
                self.assertIsNone(node.spring_DY[0])
            else:
                self.assertIsNotNone(node.spring_DY[0])

    def test_stiff_springs_converge_to_rigid_and_flexible_supports_change_load_path(self):
        rigid = build_roof_model(self.layout, Settings(horizontal_stiffness_kn_mm=None))
        stiff = build_roof_model(self.layout, Settings(horizontal_stiffness_kn_mm=1e4))
        for roof in (rigid, stiff):
            self.assertLess(max(solve_roof_model(roof).values()), 1e-8)

        def purlin_load(roof):
            return sum(
                roof.model.nodes[n].RxnFZ["SLS_symmetric"]
                for n, b in roof.supports.items()
                if b == "street_purlin_middle"
            )

        self.assertAlmostEqual(purlin_load(stiff) / purlin_load(rigid), 1, delta=0.001)
        self.assertGreater(purlin_load(self.roof), 1.2 * purlin_load(rigid))
        for name in ("street_purlin_middle", "rafter_08_street"):
            beam = next(b for b in self.layout.beams if b.name == name)
            baseline = chord_result_columns(rigid, beam, "SLS_symmetric")["chord_max_departure_mm"]
            near_rigid = chord_result_columns(stiff, beam, "SLS_symmetric")[
                "chord_max_departure_mm"
            ]
            flexible = chord_result_columns(self.roof, beam, "SLS_symmetric")[
                "chord_max_departure_mm"
            ]
            self.assertAlmostEqual(near_rigid, baseline, delta=0.01)
            self.assertGreater(abs(flexible - baseline), 0.1)

    def test_support_export_contains_spring_stiffness_and_displacements(self):
        roof = self.roof
        rows = support_rows(roof)
        for row in rows:
            node = roof.model.nodes[row["support"]]
            for axis in ("X", "Y"):
                self.assertEqual(
                    row[f"horizontal_{axis}_stiffness_kn_mm"],
                    roof.settings.horizontal_stiffness_kn_mm,
                )
                # kN/mm * mm = kN, using force delivered TO the support.
                self.assertAlmostEqual(
                    row[f"F{axis.lower()}_kN"],
                    roof.settings.horizontal_stiffness_kn_mm * row[f"D{axis.lower()}_mm"],
                    places=9,
                )
            self.assertEqual(row["Dz_mm"], 0.0)

    def test_per_rafter_ring_beam_print_uses_support_reactions_and_labels_missing_bearings(self):
        roof = self.roof
        supports = support_rows(roof)
        output = StringIO()
        with redirect_stdout(output):
            print_ring_beam_rafter_forces(roof, supports)
        lines = output.getvalue().splitlines()
        for beam in (b for b in roof.layout.beams if b.category == "rafter"):
            self.assertTrue(any(beam.name + " x=" in line for line in lines))
            plates = [
                p
                for p, category, _ in roof.rafter_seats.get(beam.name, [])
                if category == "wall_plate"
            ]
            if not plates:
                line = next(line for line in lines if beam.name + " x=" in line)
                self.assertIn("no wall-plate seat", line)
            for plate in plates:
                line = next(
                    line
                    for line in lines
                    if beam.name + " x=" in line and "-> " + plate + ":" in line
                )
                rows = [
                    r
                    for r in supports
                    if r["member"] == plate and abs(r["x_m"] - beam.start[0]) < 1e-8
                ]
                if not rows:
                    self.assertIn("load redistributed", line)
                    self.assertNotIn("Hout=", line)
                    continue
                symmetric = next(r for r in rows if r["combination"] == "SLS_symmetric")
                self.assertIn(f"SLS symmetric Hout={symmetric['outward_kN']:+.3f}", line)
                ultimate = max(
                    (r for r in rows if r["combination"].startswith("ULS_")),
                    key=lambda r: r["outward_kN"],
                )
                self.assertIn(f"ULS max Hout={ultimate['outward_kN']:+.3f}", line)
                self.assertIn(f"({ultimate['combination']}, Fx={ultimate['Fx_kN']:+.3f})", line)

    def test_per_rafter_max_outward_is_not_largest_absolute_inward_force(self):
        beam = SimpleNamespace(name="example_street", category="rafter", start=(2.0, 0.0, 0.0))
        roof = SimpleNamespace(
            layout=SimpleNamespace(beams=[beam]),
            rafter_seats={beam.name: [("street_wall_plate", "wall_plate", 0.0)]},
        )
        supports = [
            dict(
                member="street_wall_plate", x_m=2.0, combination=combo, outward_kN=force, Fx_kN=0.25
            )
            for combo, force in (
                ("SLS_symmetric", 1.0),
                ("SLS_street", -3.0),
                ("ULS_symmetric", -5.0),
                ("ULS_street", 2.0),
            )
        ]
        output = StringIO()
        with redirect_stdout(output):
            print_ring_beam_rafter_forces(roof, supports)
        self.assertIn("ULS max Hout=+2.000 (ULS_street, Fx=+0.250)", output.getvalue())
        self.assertIn("SLS max Hout=+1.000 (SLS_symmetric)", output.getvalue())

    def test_cli_defaults_use_configured_model_and_export_basis(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "roof")
            output = StringIO()
            with redirect_stdout(output):
                main(["--house", str(HOUSE), "--output", prefix, "--no-plot"])
            basis = json.loads(Path(prefix + "_restrained_basis.json").read_text())
            self.assertEqual(basis["settings"]["roof_mass"], Settings().roof_mass)
            self.assertEqual(basis["settings"]["snow_load"], Settings().snow_load)
            self.assertEqual(
                basis["settings"]["horizontal_stiffness_kn_mm"],
                Settings().horizontal_stiffness_kn_mm,
            )
            self.assertTrue(basis["settings"]["purlin_lateral_restraint"])
            self.assertIn("NOT verified", output.getvalue())
            self.assertIn("vertical load to wall bearings", output.getvalue())
            self.assertFalse(Path(prefix + "_free_basis.json").exists())
            self.assertEqual(basis["plan_report"]["force_combination"], "ULS_symmetric")
            self.assertFalse(Path(prefix + "_restrained_plan.png").exists())

    def test_wall_plate_connection_forces_include_all_seats_and_balance_bearing_reactions(self):
        roof = self.roof
        expected = sum(
            category == "wall_plate"
            for seats in roof.rafter_seats.values()
            for _, category, _ in seats
        )
        for combo in roof.model.load_combos:
            rows = wall_plate_connection_rows(roof, combo)
            self.assertEqual(len(rows), expected)
            for row in rows:
                arm = roof.model.members[row["seat"]]
                np.testing.assert_allclose(
                    (row["x_m"], row["y_m"], row["z_m"]), (arm.i_node.X, arm.i_node.Y, arm.i_node.Z)
                )
                self.assertAlmostEqual(row["outward_kN"], row["outward_direction"] * row["Fy_kN"])
            for plate in (b for b in roof.layout.beams if b.category == "wall_plate"):
                for axis in ("X", "Y"):
                    seat_total = sum(
                        row[f"F{axis.lower()}_kN"]
                        for row in rows
                        if row["wall_plate"] == plate.name
                    )
                    bearing_total = -sum(
                        getattr(roof.model.nodes[n], "RxnF" + axis)[combo] / 1000
                        for n, p in roof.supports.items()
                        if p == plate.name
                    )
                    self.assertAlmostEqual(seat_total, bearing_total, places=6)
        with self.assertRaisesRegex(ValueError, "unknown connection-force combination"):
            wall_plate_connection_rows(roof, "not_a_case")

    def test_plan_image_draws_all_members_and_connection_arrows(self):
        roof = self.roof
        rows = member_rows(roof)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.png"
            figure = plot_plan_report(roof, rows, path)
            self.assertGreater(path.stat().st_size, 20000)
            axes = figure.axes[0]
            gids = {p.get_gid() for p in axes.patches}
            self.assertEqual(gids, {b.name for b in roof.layout.beams})
            arrows = {a.get_gid() for a in axes.texts if a.get_gid()}
            forces = wall_plate_connection_rows(roof, "ULS_symmetric")
            self.assertEqual(arrows, {r["seat"] for r in forces if abs(r["outward_kN"]) > 1e-9})
            self.assertTrue(any("ULS_symmetric" in t.get_text() for t in figure.texts))


class CollarGeometryTests(unittest.TestCase):
    def test_script_parameters_work_even_when_ifc_collar_constants_are_removed(self):
        tree = ast.parse(HOUSE.read_text())
        tree.body = [
            statement
            for statement in tree.body
            if not (
                isinstance(statement, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id.startswith("COLLAR_TIE_")
                    for t in statement.targets
                )
            )
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            path.write_text(ast.unparse(tree))
            without = RoofLayout.from_house(path)
            self.assertFalse(any(b.category == "collar" for b in without.beams))
            with_ties = RoofLayout.from_house(path, collar_ties=CollarTieParameters())
            self.assertTrue(any(b.category == "collar" for b in with_ties.beams))
            self.assertEqual(
                [b for b in with_ties.beams if b.category != "collar"], list(without.beams)
            )

    def test_dimensions_height_grade_and_board_count_are_configurable(self):
        parameters = CollarTieParameters(
            width=0.07,
            height=0.18,
            boards_per_pair=1,
            material="C24",
            top_height=3.35,
            middle_lowering=0.05,
        )
        layout = RoofLayout.from_house(HOUSE, collar_ties=parameters)
        ties = [b for b in layout.beams if b.category == "collar"]
        self.assertTrue(ties)
        self.assertTrue(all(b.timber == Timber(0.07, 0.18, "C24") and b.pieces == 1 for b in ties))
        floor = HouseInputs(HOUSE).get("UPPER_FLOOR_START")
        for tie in ties:
            self.assertEqual(tie.start[2], tie.end[2])
            self.assertTrue(
                any(
                    abs(tie.start[2] - z) < 1e-8
                    for z in (floor + 3.35 - 0.09, floor + 3.35 - 0.09 - 0.05)
                )
            )

    def test_touching_main_rafters_omit_only_inward_boards_not_dormer_pairs(self):
        base = RoofLayout.from_house(HOUSE)
        beams = tuple(
            (
                replace(b, start=(2.63, *b.start[1:]), end=(2.63, *b.end[1:]))
                if b.name in {"rafter_05_street", "rafter_05_garden"}
                else b
            )
            for b in base.beams
        )
        floor = HouseInputs(HOUSE).get("UPPER_FLOOR_START")
        layout = add_collar_ties(
            replace(base, beams=beams), CollarTieParameters(), upper_floor_z=floor
        )
        for name in ("rafter_04_street", "rafter_05_street"):
            self.assertEqual(sum(b.pieces for b in layout.beams if name in b.attached_rafters), 1)
        # Original main/dormer touching offsets do not suppress either board.
        original = RoofLayout.from_house(HOUSE, collar_ties=CollarTieParameters())
        for b in base.beams:
            if b.name.endswith("_dormer"):
                main = b.name.removesuffix("dormer") + "street"
                self.assertEqual(
                    sum(t.pieces for t in original.beams if main in t.attached_rafters), 2
                )

    def test_height_step_keeps_two_boards_at_distinct_heights(self):
        base = RoofLayout.from_house(HOUSE)
        middle = next(b for b in base.beams if b.name == "street_purlin_middle")
        x = middle.bearings[0]
        beams = tuple(
            (
                replace(b, start=(x, *b.start[1:]), end=(x, *b.end[1:]))
                if b.name in {"rafter_05_street", "rafter_05_garden"}
                else b
            )
            for b in base.beams
        )
        layout = add_collar_ties(
            replace(base, beams=beams),
            CollarTieParameters(),
            upper_floor_z=HouseInputs(HOUSE).get("UPPER_FLOOR_START"),
        )
        ties = [b for b in layout.beams if "rafter_05_street" in b.attached_rafters]
        self.assertEqual([b.pieces for b in ties], [1, 1])
        self.assertAlmostEqual(
            abs(ties[0].start[2] - ties[1].start[2]), CollarTieParameters().middle_lowering
        )

    def test_bad_parameters_and_unsupported_height_fail_explicitly(self):
        for params in (
            dict(width=0),
            dict(height=-1),
            dict(boards_per_pair=3),
            dict(boards_per_pair=True),
            dict(material="C99"),
            dict(middle_lowering=-0.1),
            dict(top_height=0.1),
        ):
            with self.assertRaises(ValueError):
                CollarTieParameters(**params)
        with self.assertRaisesRegex(ValueError, "does not intersect"):
            RoofLayout.from_house(HOUSE, collar_ties=CollarTieParameters(top_height=10))


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class CollarSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = build_roof_model(RoofLayout.from_house(HOUSE), Settings())
        solve_roof_model(cls.base)
        cls.roof = build_roof_model(
            RoofLayout.from_house(HOUSE, collar_ties=CollarTieParameters()), Settings()
        )
        cls.residuals = solve_roof_model(cls.roof)

    def test_axial_stiffness_connections_and_force_sign(self):
        roof = self.roof
        self.assertLess(max(self.residuals.values()), 1e-8)
        for tie in (b for b in roof.layout.beams if b.category == "collar"):
            spring = roof.model.springs[tie.name]
            expected = (
                roof.model.materials[tie.timber.material].E
                * tie.timber.properties[0]
                * tie.pieces
                / tie.length
            )
            self.assertAlmostEqual(spring.ks, expected)
            for node, rafter_name in zip((spring.i_node, spring.j_node), tie.attached_rafters):
                member = roof.model.members[rafter_name]
                nodes = {
                    n.name for sub in member.sub_members.values() for n in (sub.i_node, sub.j_node)
                }
                self.assertIn(node.name, nodes)
                self.assertNotIn(node.name, roof.supports)
            for combo in roof.model.load_combos:
                # Global Y is the axial direction: positive extension=tension.
                extension = spring.j_node.DY[combo] - spring.i_node.DY[combo]
                self.assertAlmostEqual(-spring.axial(combo), expected * extension, places=6)

    def test_roof_loads_unchanged_and_only_collar_self_weight_added(self):
        self.assertEqual(self.base.loads, self.roof.loads)
        self.assertEqual(self.base.nodal_loads, [])
        expected = sum(
            b.length * b.timber.properties[0] * b.pieces
            for b in self.roof.layout.beams
            if b.category == "collar"
        )
        expected *= self.roof.settings.timber_density * self.roof.settings.gravity
        self.assertAlmostEqual(-sum(v[2] for _, _, v in self.roof.nodal_loads), expected)
        self.assertTrue(all(case == "G" for _, case, _ in self.roof.nodal_loads))

    def test_export_terminal_and_images_include_ties_without_invented_bending_checks(self):
        roof = self.roof
        members, supports = member_rows(roof), support_rows(roof)
        ties = [r for r in members if r["category"] == "collar"]
        self.assertEqual(len(ties), len(roof.model.springs) * 6)
        for row in ties:
            self.assertEqual(row["Mz_min_kNm"], "")
            self.assertEqual(row["chord_L500_status"], "")
            self.assertEqual(plan_deflection_status([row]), "not_assessed")
            self.assertAlmostEqual(
                row["N_min_kN"], -roof.model.springs[row["member"]].axial(row["combination"]) / 1000
            )
        output = StringIO()
        with redirect_stdout(output):
            print_summary(roof, members, supports, self.residuals)
        self.assertIn("OPTIONAL kleštiny", output.getvalue())
        self.assertIn("Collar axial-force envelope", output.getvalue())
        for name in roof.model.springs:
            self.assertIn(name, output.getvalue())
        with TemporaryDirectory() as directory:
            for name, fn in (
                ("3d", lambda path: plot_model(roof, path)),
                ("plan", lambda path: plot_plan_report(roof, members, path)),
            ):
                path = Path(directory) / (name + ".png")
                fn(path)
                self.assertGreater(path.stat().st_size, 20000)

    def test_collars_change_coupled_deflections_and_ring_beam_forces(self):
        def street_load(roof):
            return sum(
                r["outward_kN"]
                for r in support_rows(roof)
                if r["combination"] == "SLS_symmetric" and "street_wall_plate" in r["member"]
            )

        self.assertGreater(abs(street_load(self.base) - street_load(self.roof)), 0.01)
        for name in ("rafter_08_street", "street_purlin_middle"):
            values = []
            for roof in (self.base, self.roof):
                beam = next(b for b in roof.layout.beams if b.name == name)
                values.append(
                    chord_result_columns(roof, beam, "SLS_symmetric")["chord_max_departure_mm"]
                )
            self.assertGreater(abs(values[0] - values[1]), 0.001)

    def test_plan_ties_are_visible_magenta_with_two_arrows_and_selected_force_between_them(self):
        from matplotlib.colors import to_rgba

        roof = self.roof
        members = member_rows(roof)
        combo = "SLS_street"
        with TemporaryDirectory() as directory:
            figure = plot_plan_report(
                roof, members, Path(directory) / "ties.png", force_combo=combo
            )
        axes = figure.axes[0]
        patches = {p.get_gid(): p for p in axes.patches}
        annotations = {t.get_gid(): t for t in axes.texts if t.get_gid()}
        for beam in (b for b in roof.layout.beams if b.category == "collar"):
            collar = patches[beam.name]
            self.assertEqual(collar.get_edgecolor(), to_rgba("#d000d0"))
            self.assertEqual(collar.get_facecolor()[-1], 0)
            self.assertGreater(collar.get_zorder(), patches[beam.attached_rafters[0]].get_zorder())
            row = next(r for r in members if r["member"] == beam.name and r["combination"] == combo)
            force = row["N_min_kN"]
            centre, arrows = plan_collar_force_arrows(beam, force)
            label = annotations[f"{beam.name}_axial_force"]
            self.assertEqual(label.get_text(), f"{force:+.2f} kN")
            np.testing.assert_allclose(label.get_position(), centre)
            for number, (tail, head) in enumerate(arrows, 1):
                arrow = annotations[f"{beam.name}_axial_arrow_{number}"]
                np.testing.assert_allclose(arrow.xy, head)
                np.testing.assert_allclose(arrow.xyann, tail)
        self.assertTrue(any("Magenta" in text.get_text() for text in figure.legends[0].texts))

    def test_cli_switch_records_independent_configuration_and_separate_output_prefix(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "roof")
            with redirect_stdout(StringIO()):
                main(["--house", str(HOUSE), "--output", prefix, "--no-plot", "--collar-ties"])
            basis = json.loads(Path(prefix + "_collars_restrained_basis.json").read_text())
            self.assertTrue(basis["collar_ties"]["enabled"])
            self.assertEqual(
                basis["collar_ties"]["parameters"]["width"], CollarTieParameters().width
            )
            self.assertNotIn("kleštiny", basis["omitted"])
            self.assertFalse(Path(prefix + "_restrained_basis.json").exists())


def isfinite_number(value):
    return bool(np.isfinite(value))


if __name__ == "__main__":
    unittest.main()
