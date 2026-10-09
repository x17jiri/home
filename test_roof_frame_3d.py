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
    RoofPatch,
    Settings,
    Timber,
    BeamSpec,
    gerber_joint_rows,
    TIMBER_E90_MEAN_PA,
    TIMBER_MEAN_DENSITY_KG_M3,
    CollarTieParameters,
    SaddleParameters,
    SaddleBoltParameters,
    saddle_bolt_stiffness,
    saddle_bolt_rows,
    bolt_face_terms,
    bolt_face_slip,
    bolt_shear_assembly,
    solve_saddle_contact,
    add_purlin_saddles,
    saddle_contact_stiffness,
    saddle_contact_rows,
    add_collar_ties,
    add_purlin_spacers,
    spacer_rows,
    build_roof_model,
    check_equilibrium,
    chord_result_columns,
    deformed_member_point,
    horizontal_stiffness_argument,
    dormer_horizontal_stiffness_argument,
    main,
    maximum_chord_departure,
    purlin_wall_chord_result_columns,
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
    print_wall_plate_connection_movements,
    purlin_chord,
    rafter_chord,
    solve_roof_model,
    support_rows,
    support_reaction_node,
    uplift_locations,
    lift_off_locations,
    tributary_intervals,
    wall_plate_connection_rows,
)

HOUSE = Path(__file__).with_name("house_ifc.py")
HAS_PYNITE = importlib.util.find_spec("Pynite") is not None


def legacy_roof_layout(*args, **kwargs):
    """Keep legacy geometry/mechanics regressions on their original C22 fixture."""
    kwargs.setdefault("rafter_material", "C22")
    kwargs.setdefault("beam_material", "C22")
    return RoofLayout.from_house(*args, purlin_system="simple", **kwargs)


def build_anchored_roof_model(layout, settings=Settings()):
    """Explicit bilateral fixture for pre-lift-off connection regressions."""
    return build_roof_model(layout, replace(settings, purlin_bearing_uplift=False))


def gerber_roof_layout(*, joints="middle", **kwargs):
    """Explicit joint fixtures, independent of the currently edited IFC values."""
    data = HouseInputs(HOUSE)
    lo = data.get("wall2_x") - data.get("BWT") / 2
    hi = data.get("wall3_x") - data.get("BWT") / 2
    coordinates = {
        "middle": (lo + .75, hi - .75),
        "sides": (lo - .75, hi + .75),
        "mixed": (lo - .75, hi - .75),
        "walls": (lo, hi),
    }[joints]
    data.cache.update(GERBER_JOINT_1=coordinates[0], GERBER_JOINT_2=coordinates[1])
    with patch("roof_frame_3d.HouseInputs", return_value=data):
        return RoofLayout.from_house(HOUSE, **kwargs)


class GerberGeometryTests(unittest.TestCase):
    def test_default_layout_matches_ifc_joints_but_walls_stay_at_wall_centres(self):
        data = HouseInputs(HOUSE)
        layout = RoofLayout.from_house(HOUSE)
        self.assertEqual(layout.purlin_system, "gerber")
        self.assertEqual(len(layout.gerber_joints), 4)
        self.assertIsNone(layout.saddle_parameters)
        walls = (data.get("BWT") / 2, data.get("wall2_x") - data.get("BWT") / 2,
                 data.get("wall3_x") - data.get("BWT") / 2,
                 data.get("HOUSE_WIDTH") - data.get("BWT") / 2)
        for side in ("street", "garden"):
            pieces = [b for b in layout.beams if b.name.startswith(side + "_purlin_")]
            for beam, (_, lo, hi, _) in zip(pieces, data.get("PURLIN_X_SEGMENTS")):
                self.assertAlmostEqual(beam.start[0], lo)
                self.assertAlmostEqual(beam.end[0], hi)
            self.assertEqual(sorted(x for b in pieces for x in b.bearings), list(walls))
            for b in pieces:
                self.assertTrue(all(b.start[0] <= x <= b.end[0] for x in b.bearings))
            first, second = data.get("GERBER_JOINT_1"), data.get("GERBER_JOINT_2")
            self.assertAlmostEqual(pieces[1].start[0], first)
            self.assertAlmostEqual(pieces[1].end[0], second)
            self.assertAlmostEqual(pieces[1].length, second - first)
            self.assertAlmostEqual(pieces[0].end[0], first)
            self.assertAlmostEqual(pieces[2].start[0], second)
        with self.assertRaisesRegex(ValueError, "cannot add sedla"):
            add_purlin_saddles(layout)

    def test_wall_bearings_follow_both_joint_arrangements_and_exact_wall_joints(self):
        expected = {"middle": (2, 0, 2), "sides": (1, 2, 1),
                    "mixed": (1, 1, 2), "walls": (2, 0, 2)}
        for variant, counts in expected.items():
            with self.subTest(variant=variant):
                layout = gerber_roof_layout(joints=variant, collar_ties=CollarTieParameters())
                for side in ("street", "garden"):
                    pieces = [b for b in layout.beams if b.name.startswith(side + "_purlin_")]
                    self.assertEqual(tuple(len(b.bearings) for b in pieces), counts)
                    self.assertEqual(sum(len(b.bearings) for b in pieces), 4)

    def test_two_hinges_in_one_side_span_are_rejected_as_unstable(self):
        data = HouseInputs(HOUSE)
        data.cache.update(GERBER_JOINT_1=1., GERBER_JOINT_2=2.)
        with patch("roof_frame_3d.HouseInputs", return_value=data):
            with self.assertRaisesRegex(ValueError, "Gerber"):
                RoofLayout.from_house(HOUSE)

    def test_legacy_comparisons_put_joints_back_on_the_walls(self):
        for mode in ("simple", "saddles"):
            layout = RoofLayout.from_house(HOUSE, purlin_system=mode)
            self.assertFalse(layout.gerber_joints)
            for side in ("street", "garden"):
                middle = next(b for b in layout.beams if b.name == side + "_purlin_middle")
                self.assertAlmostEqual(middle.length, 4.72)
                self.assertEqual(middle.bearings, (middle.start[0], middle.end[0]))
            if mode == "saddles":
                self.assertEqual(sum(b.category == "saddle" for b in add_purlin_saddles(layout).beams), 4)
        with self.assertRaisesRegex(ValueError, "purlin_system"):
            RoofLayout.from_house(HOUSE, purlin_system="unknown")


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class GerberSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layout = add_purlin_spacers(gerber_roof_layout(collar_ties=CollarTieParameters()))
        cls.roof = build_roof_model(layout)
        cls.residuals = solve_roof_model(cls.roof)

    def test_hinges_share_translations_release_moments_and_have_no_ground_support(self):
        roof = self.roof
        self.assertLess(max(self.residuals.values()), 1e-5)
        self.assertEqual(len(roof.gerber_connections), 4)
        self.assertFalse(roof.saddle_contacts)
        self.assertFalse(roof.saddle_bolts)
        for joint in roof.gerber_connections:
            left, right = (roof.model.members[joint[key]] for key in ("left", "right"))
            self.assertIs(left.j_node, right.i_node)
            node = roof.model.nodes[joint["node"]]
            self.assertNotIn(node.name, roof.supports)
            for axis in ("DX", "DY", "DZ", "RX", "RY", "RZ"):
                self.assertFalse(getattr(node, "support_" + axis))
            member = roof.model.members[joint["suspended"]]
            offset = 0 if joint["suspended_end"] == "i" else 6
            self.assertTrue(member.Releases[offset + 4])
            self.assertTrue(member.Releases[offset + 5])
            self.assertFalse(member.Releases[offset + 3])
        rows = gerber_joint_rows(roof)
        self.assertEqual(len(rows), 4 * len(roof.model.load_combos))
        self.assertTrue(any(abs(row["Dz_mm"]) > 0.1 for row in rows))
        self.assertTrue(any(abs(row["Fz_to_outer_kN"]) > 1 for row in rows))
        for row in rows:
            self.assertAlmostEqual(row["My_to_outer_kNm"], 0.0, places=7)
            self.assertAlmostEqual(row["Mz_to_outer_kNm"], 0.0, places=7)

    def test_middle_chord_uses_moving_hinges_outer_chords_use_walls(self):
        roof = self.roof
        rows = member_rows(roof)
        for beam in (b for b in roof.layout.beams if b.category == "purlin"):
            chord = purlin_chord(roof, beam)
            if beam.name.endswith("middle"):
                self.assertEqual(chord.kind, "gerber_hinge_to_hinge")
                self.assertAlmostEqual(chord.end_m - chord.start_m, beam.length)
                self.assertNotIn(chord.start_label, roof.supports)
                self.assertNotIn(chord.end_label, roof.supports)
            else:
                self.assertEqual(chord.kind, "bearing_to_bearing")
                self.assertAlmostEqual(chord.end_m - chord.start_m, beam.bearings[1] - beam.bearings[0])
            self.assertTrue(any(r["member"] == beam.name for r in rows))

    def test_rafter_at_gerber_joint_has_one_seat_and_one_spacer_endpoint(self):
        layout = gerber_roof_layout()
        joint_x = next(b.end[0] for b in layout.beams if b.name == "street_purlin_left")
        names = {"rafter_06_street", "rafter_06_garden"}
        layout = replace(layout, beams=tuple(
            replace(b, start=(joint_x, *b.start[1:]), end=(joint_x, *b.end[1:]))
            if b.name in names else b for b in layout.beams
        ))
        roof = build_roof_model(add_purlin_spacers(layout))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-5)
        for side in ("street", "garden"):
            rafter = "rafter_06_" + side
            first = roof.seat_members[(rafter, side + "_purlin_left")]
            second = roof.seat_members[(rafter, side + "_purlin_middle")]
            self.assertEqual(first, second)
        spring = roof.model.springs["spacer_06"]
        self.assertIs(spring.i_node, roof.model.members["street_purlin_middle"].i_node)
        self.assertIs(spring.j_node, roof.model.members["garden_purlin_middle"].i_node)

    def test_plot_identifies_hinges_separately_from_supports(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "gerber.png"
            figure = plot_plan_report(self.roof, member_rows(self.roof), path)
            markers = {line.get_gid() for line in figure.axes[0].lines}
            for joint in self.roof.gerber_connections:
                self.assertIn(joint["joint"], markers)
            self.assertGreater(path.stat().st_size, 10000)

    def test_matches_hand_calculation_for_loaded_suspended_span_and_cantilevers(self):
        timber = Timber(0.24, 0.24, "C22")
        beams = (
            BeamSpec("left", "purlin", (0., 0., 4.), (3.5, 0., 4.), timber, bearings=(0., 3.)),
            BeamSpec("middle", "purlin", (3.5, 0., 4.), (7.5, 0., 4.), timber),
            BeamSpec("right", "purlin", (7.5, 0., 4.), (11., 0., 4.), timber, bearings=(8., 11.)),
        )
        layout = RoofLayout(beams, (), HOUSE, purlin_system="gerber",
                            gerber_joints=(("left", "middle"), ("middle", "right")))
        # This isolated analytical example requires tensile outer-wall anchors.
        roof = build_roof_model(layout, Settings(purlin_bearing_uplift=False))
        # Isolate a 1 kN/m UDL on the 4 m middle piece; cancel timber self-weight.
        self_weight = roof.settings.timber_density * roof.settings.gravity * timber.properties[0]
        for beam in beams:
            roof.add_load(beam.name, "G", self_weight)
        roof.add_load("middle", "G", -1000.)
        self.assertLess(max(solve_roof_model(roof).values()), 1e-5)
        ei = 10e9 * timber.properties[2]
        tip_deflection = -2000. * 0.5**2 * (3. + 0.5) / (3 * ei)
        middle = roof.model.members["middle"]
        self.assertAlmostEqual(middle.i_node.DZ["SLS_symmetric"], tip_deflection, places=10)
        self.assertAlmostEqual(middle.j_node.DZ["SLS_symmetric"], tip_deflection, places=10)
        chord = purlin_chord(roof, beams[1])
        departure, _ = maximum_chord_departure(middle, "SLS_symmetric", chord.start_m, chord.end_m)
        self.assertAlmostEqual(departure, 5 * 1000. * 4.**4 / (384 * ei), places=9)
        wall = purlin_wall_chord_result_columns(roof, beams[1], "SLS_symmetric")
        self.assertAlmostEqual(wall["wall_chord_span_m"], 5.)
        self.assertAlmostEqual(wall["wall_chord_max_departure_mm"],
                               (5 * 1000. * 4.**4 / (384 * ei) - tip_deflection) * 1000,
                               places=6)
        self.assertAlmostEqual(wall["wall_chord_max_at_s_m"], 2.5, places=6)
        self.assertEqual(wall["wall_chord_max_member"], "middle")
        self.assertGreater(wall["wall_chord_max_departure_mm"], departure * 1000)
        expected_reactions = {0.: -2000. * 0.5 / 3., 3.: 2000. * 3.5 / 3.,
                              8.: 2000. * 3.5 / 3., 11.: -2000. * 0.5 / 3.}
        for name in roof.supports:
            node = roof.model.nodes[name]
            self.assertAlmostEqual(node.RxnFZ["SLS_symmetric"], expected_reactions[node.X], places=7)
        for row in gerber_joint_rows(roof):
            if row["combination"] == "SLS_symmetric":
                self.assertAlmostEqual(row["Fz_to_outer_kN"], -2.0, places=8)
                self.assertAlmostEqual(row["My_to_outer_kNm"], 0.0, places=8)
                self.assertAlmostEqual(row["Mz_to_outer_kNm"], 0.0, places=8)

    def test_soft_outer_pieces_fail_wall_bay_even_when_stiff_middle_passes(self):
        outer, middle = Timber(.05, .09, "C22"), Timber(.24, .24, "C22")
        beams = (
            BeamSpec("left", "purlin", (0., 0., 4.), (3.5, 0., 4.), outer, bearings=(0., 3.)),
            BeamSpec("middle", "purlin", (3.5, 0., 4.), (7.5, 0., 4.), middle),
            BeamSpec("right", "purlin", (7.5, 0., 4.), (11., 0., 4.), outer, bearings=(8., 11.)),
        )
        layout = RoofLayout(beams, (), HOUSE, purlin_system="gerber",
                            gerber_joints=(("left", "middle"), ("middle", "right")))
        roof = build_roof_model(layout)
        for beam in beams:
            roof.add_load(beam.name, "G", roof.settings.timber_density * roof.settings.gravity
                          * beam.timber.properties[0])  # cancel self-weight
        roof.add_load("middle", "G", -1000.)
        self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
        result = chord_result_columns(roof, beams[1], "SLS_symmetric")
        self.assertEqual(result["chord_L500_status"], "PASS")
        self.assertEqual(result["wall_chord_L300_status"], "FAIL")
        self.assertEqual(result["wall_chord_L500_status"], "FAIL")
        expected = (5 * 1000. * 4.**4 / (384 * 10e9 * middle.properties[2])
                    + 2000. * .5**2 * 3.5 / (3 * 10e9 * outer.properties[2])) * 1000
        self.assertAlmostEqual(result["wall_chord_max_departure_mm"], expected, places=6)
        self.assertEqual(plan_deflection_status([dict(result, combination="SLS_symmetric")]), "fail")
        with TemporaryDirectory() as directory:
            figure = plot_plan_report(roof, member_rows(roof), Path(directory) / "failed-bay.png")
            middle_patch = next(p for p in figure.axes[0].patches if p.get_gid() == "middle")
            from matplotlib.colors import to_rgb
            np.testing.assert_allclose(middle_patch.get_facecolor()[:3], to_rgb("#d9534f"))


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class GerberSideJointSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layout = add_purlin_spacers(gerber_roof_layout(
            joints="sides", collar_ties=CollarTieParameters()
        ))
        cls.roof = build_roof_model(layout, Settings(middle_snow=True))
        cls.residuals = solve_roof_model(cls.roof)

    def test_middle_has_two_walls_and_only_side_hinge_ends_release_moments(self):
        roof = self.roof
        self.assertLess(max(self.residuals.values()), 1e-5)
        for side in ("street", "garden"):
            middle = roof.model.members[side + "_purlin_middle"]
            self.assertFalse(any(middle.Releases))
        for joint in roof.gerber_connections:
            self.assertTrue(joint["carrier"].endswith("middle"))
            member = roof.model.members[joint["supported"]]
            offset = 0 if joint["supported_end"] == "i" else 6
            self.assertTrue(member.Releases[offset + 4])
            self.assertTrue(member.Releases[offset + 5])
            self.assertFalse(any(member.Releases[6-offset:12-offset]))
            self.assertNotIn(joint["node"], roof.supports)
        for row in gerber_joint_rows(roof):
            self.assertAlmostEqual(row["My_to_carrier_kNm"], 0., places=7)
            self.assertAlmostEqual(row["Mz_to_carrier_kNm"], 0., places=7)

    def test_checks_use_wall_hinge_for_sides_and_wall_wall_for_middle(self):
        roof = self.roof
        for beam in (b for b in roof.layout.beams if b.category == "purlin"):
            chord = purlin_chord(roof, beam)
            result = chord_result_columns(roof, beam, "SLS_middle")
            if beam.name.endswith("middle"):
                self.assertEqual(chord.kind, "bearing_to_bearing")
                self.assertAlmostEqual(result["chord_span_m"], 4.72)
                self.assertAlmostEqual(result["wall_chord_span_m"], 4.72)
                self.assertAlmostEqual(result["wall_chord_max_departure_mm"],
                                       result["chord_max_departure_mm"], places=7)
                self.assertIn(chord.start_label, roof.supports)
                self.assertIn(chord.end_label, roof.supports)
            else:
                self.assertEqual(chord.kind, "gerber_wall_to_hinge")
                self.assertEqual(sum(n in roof.supports for n in
                                     (chord.start_label, chord.end_label)), 1)
                self.assertFalse(result["wall_chord_reference"])
        uls = chord_result_columns(roof, next(b for b in roof.layout.beams
                                             if b.name == "street_purlin_middle"), "ULS_middle")
        self.assertEqual(uls["wall_chord_L300_status"], "NOT_CHECKED_ULS")

    def test_rafter_and_spacer_at_side_hinge_have_only_one_attachment(self):
        layout = gerber_roof_layout(joints="sides")
        joint_x = next(b.end[0] for b in layout.beams if b.name == "street_purlin_left")
        names = {"rafter_04_street", "rafter_04_garden"}
        layout = replace(layout, beams=tuple(
            replace(b, start=(joint_x, *b.start[1:]), end=(joint_x, *b.end[1:]))
            if b.name in names else b for b in layout.beams
        ))
        roof = build_roof_model(add_purlin_spacers(layout))
        for side in ("street", "garden"):
            first = roof.seat_members[("rafter_04_" + side, side + "_purlin_left")]
            second = roof.seat_members[("rafter_04_" + side, side + "_purlin_middle")]
            self.assertEqual(first, second)
        spring = roof.model.springs["spacer_04"]
        self.assertIs(spring.i_node, roof.model.members["street_purlin_middle"].i_node)
        self.assertIs(spring.j_node, roof.model.members["garden_purlin_middle"].i_node)

    def test_asymmetric_and_exact_wall_hinges_solve_with_correct_chords(self):
        timber = Timber(.24, .24, "C22")
        for first, second, bearings in (
            (2.5, 7.5, ((0.,), (3.,), (8., 11.))),
            (3., 8., ((0., 3.), (), (8., 11.))),
        ):
            with self.subTest(joints=(first, second)):
                beams = (
                    BeamSpec("left", "purlin", (0., 0., 4.), (first, 0., 4.), timber, bearings=bearings[0]),
                    BeamSpec("middle", "purlin", (first, 0., 4.), (second, 0., 4.), timber, bearings=bearings[1]),
                    BeamSpec("right", "purlin", (second, 0., 4.), (11., 0., 4.), timber, bearings=bearings[2]),
                )
                layout = RoofLayout(beams, (), HOUSE, purlin_system="gerber",
                                    gerber_joints=(("left", "middle"), ("middle", "right")))
                roof = build_roof_model(layout)
                self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
                result = chord_result_columns(roof, beams[1], "SLS_symmetric")
                self.assertAlmostEqual(result["wall_chord_span_m"], 5.)
                self.assertEqual(result["chord_reference"], "gerber_wall_to_hinge"
                                 if bearings[1] else "gerber_hinge_to_hinge")

    def test_plots_and_terminal_identify_the_actual_carriers(self):
        roof = self.roof
        rows = member_rows(roof)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "side-joints.png"
            figure = plot_plan_report(roof, rows, path, force_combo="ULS_middle")
            markers = {line.get_gid() for line in figure.axes[0].lines}
            for joint in roof.gerber_connections:
                self.assertIn(joint["joint"], markers)
            self.assertGreater(path.stat().st_size, 10000)
        output = StringIO()
        with redirect_stdout(output):
            print_summary(roof, rows, support_rows(roof), self.residuals)
        self.assertIn("street_purlin_middle carries street_purlin_left", output.getvalue())
        self.assertIn("ADDITIONAL wall-to-wall: L=4.720 m", output.getvalue())

    def test_matches_hand_calculations_for_side_and_middle_only_loading(self):
        timber = Timber(.24, .24, "C22")
        beams = (
            BeamSpec("left", "purlin", (0., 0., 4.), (2.5, 0., 4.), timber, bearings=(0.,)),
            BeamSpec("middle", "purlin", (2.5, 0., 4.), (8.5, 0., 4.), timber, bearings=(3., 8.)),
            BeamSpec("right", "purlin", (8.5, 0., 4.), (11., 0., 4.), timber, bearings=(11.,)),
        )
        layout = RoofLayout(beams, (), HOUSE, purlin_system="gerber",
                            gerber_joints=(("left", "middle"), ("middle", "right")))
        ei = 10e9 * timber.properties[2]
        for loading in ("sides", "middle"):
            with self.subTest(loading=loading):
                roof = build_roof_model(layout)
                for beam in beams:
                    roof.add_load(beam.name, "G", roof.settings.timber_density
                                  * roof.settings.gravity * timber.properties[0])
                if loading == "sides":
                    roof.add_load("left", "G", -1000.)
                    roof.add_load("right", "G", -1000.)
                    reactions = {0.: 1250., 3.: 1250., 8.: 1250., 11.: 1250.}
                    expected_midpoint_dz = 1250. * .5 * 5.**2 / (8 * ei)
                else:
                    roof.add_load("middle", "G", -1000., .5, 5.5)
                    reactions = {0.: 0., 3.: 2500., 8.: 2500., 11.: 0.}
                    expected_midpoint_dz = -5 * 1000. * 5.**4 / (384 * ei)
                self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
                for name in roof.supports:
                    node = roof.model.nodes[name]
                    self.assertAlmostEqual(node.RxnFZ["SLS_symmetric"], reactions[node.X], places=7)
                midpoint = deformed_member_point(roof.model.members["middle"], 3., "SLS_symmetric")
                self.assertAlmostEqual(midpoint[2] - 4., expected_midpoint_dz, places=10)
                for row in gerber_joint_rows(roof):
                    if row["combination"] == "SLS_symmetric":
                        self.assertAlmostEqual(row["Fz_to_carrier_kN"],
                                               -1.25 if loading == "sides" else 0., places=8)


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class MiddleSnowTests(unittest.TestCase):
    def test_boundaries_follow_inner_walls_not_shortened_gerber_piece(self):
        data = HouseInputs(HOUSE)
        layout = gerber_roof_layout()
        expected = (data.get("wall2_x") - data.get("BWT") / 2,
                    data.get("wall3_x") - data.get("BWT") / 2)
        self.assertEqual(layout.middle_snow_bounds, expected)
        self.assertEqual(add_purlin_spacers(layout).middle_snow_bounds, expected)
        middle = next(b for b in layout.beams if b.name == "street_purlin_middle")
        self.assertGreater(middle.start[0], expected[0])
        self.assertLess(middle.end[0], expected[1])

    def test_partial_tributary_strips_and_separate_combinations(self):
        beams = tuple(BeamSpec(f"rafter_{i+1:02d}_street", "rafter", (float(i), 0., 4.),
                               (float(i), 1., 4.), Timber(.08, .2)) for i in range(3))
        patch = RoofPatch("test", -.5, 2.5, 0., 1., tuple(b.name for b in beams), "street")
        layout = RoofLayout(beams, (patch,), HOUSE, middle_snow_bounds=(.25, 1.25))
        baseline = build_roof_model(layout, Settings(snow_load=2.))
        roof = build_roof_model(layout, Settings(middle_snow=True, snow_load=2.))
        snow = {n: q for n, c, q, a, b in roof.loads if c == "S_middle"}
        self.assertEqual(snow, {beams[0].name: -500., beams[1].name: -1500.})
        self.assertAlmostEqual(sum(-q * (b-a) for n, c, q, a, b in roof.loads
                                   if c == "S_middle"), 2000.)
        self.assertEqual([load for load in roof.loads if load[1] != "S_middle"], baseline.loads)
        self.assertEqual(len(baseline.model.load_combos), 6)
        self.assertEqual(len(roof.model.load_combos), 8)
        self.assertEqual(roof.model.load_combos["SLS_middle"].factors, {"G": 1., "S_middle": 1.})
        self.assertEqual(roof.model.load_combos["ULS_middle"].factors, {"G": 1.35, "S_middle": 1.5})
        self.assertNotIn("S_middle", roof.model.load_combos["SLS_symmetric"].factors)

    def test_missing_or_invalid_middle_bounds_are_rejected(self):
        beam = BeamSpec("test", "purlin", (0., 0., 4.), (5., 0., 4.), Timber(.24, .24))
        with self.assertRaisesRegex(ValueError, "middle_snow_bounds"):
            build_roof_model(RoofLayout((beam,), (), HOUSE), Settings(middle_snow=True))
        for bounds in ((2., 1.), (1., 1.), (float("nan"), 2.), (1., float("inf"))):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, "middle snow bounds"):
                RoofLayout((beam,), (), HOUSE, middle_snow_bounds=bounds)

    def test_house_middle_snow_force_matches_clipped_horizontal_roof_area(self):
        layout = RoofLayout.from_house(HOUSE)
        roof = build_roof_model(layout, Settings(middle_snow=True, snow_load=2.))
        lo, hi = layout.middle_snow_bounds
        area = sum(max(0., min(p.x_max, hi) - max(p.x_min, lo)) * (p.y_max - p.y_min)
                   for p in layout.patches)
        force = sum(-q * (b-a) for n, case, q, a, b in roof.loads if case == "S_middle")
        self.assertAlmostEqual(force, 2000. * area, places=7)

    def test_cli_records_middle_pattern_and_selects_its_force_arrows(self):
        import json
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            prefix = str(Path(directory) / "roof")
            main(["--middle-snow", "--no-plot", "--output", prefix])
            basis = json.loads(Path(prefix + "_middle_snow_restrained_basis.json").read_text())
        self.assertTrue(basis["middle_snow"]["enabled"])
        self.assertTrue(basis["settings"]["middle_snow"])
        self.assertEqual(basis["plan_report"]["force_combination"], "ULS_middle")
        self.assertEqual(basis["combinations"]["SLS_middle"], {"G": 1., "S_middle": 1.})
        self.assertLess(max(basis["equilibrium_relative_residual"].values()), 1e-8)


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class PurlinLiftOffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A continuous beam with three wall bearings and a loaded cantilever.
        # The middle bearing opens while the end bearings keep it stable.
        beam = BeamSpec("test_purlin", "purlin", (0., 0., 4.), (5., 0., 4.),
                        Timber(0.24, 0.24, "C22"), bearings=(0., 2., 4.))
        cls.layout = RoofLayout((beam,), (), HOUSE)
        cls.roof = roof = build_roof_model(cls.layout, Settings(purlin_bearing_uplift=True))
        cls.nodes = {roof.model.nodes[n].X: n for n in roof.supports}
        for name, forces in ((cls.nodes[0.], (0., 0., -10000.)),
                             (cls.nodes[2.], (1000., 2000., 0.)),
                             (roof.model.members[beam.name].j_node.name, (0., 0., -10000.))):
            for direction, force in zip(("FX", "FY", "FZ"), forces):
                if force:
                    roof.model.add_node_load(name, direction, force, case="G")
            roof.nodal_loads.append((name, "G", forces))
        # Downward snow load closes that same contact in a different combination.
        roof.model.add_node_load(cls.nodes[2.], "FZ", -10000., case="S_street")
        roof.nodal_loads.append((cls.nodes[2.], "S_street", (0., 0., -10000.)))
        cls.residuals = solve_roof_model(roof)

    def test_contacts_only_release_vertical_support_and_preserve_equilibrium(self):
        self.assertFalse(Settings().purlin_bearing_uplift)
        self.assertEqual(len(self.roof.purlin_wall_bearings), 3)
        self.assertLess(max(self.residuals.values()), 1e-8)
        for name, contact in self.roof.purlin_wall_bearings.items():
            node = self.roof.model.nodes[name]
            self.assertFalse(node.support_DZ)
            self.assertTrue(node.support_DX)
            self.assertTrue(node.support_DY)
            self.assertTrue(node.support_RX)
            self.assertFalse(node.support_RY)
            spring = self.roof.model.springs[contact]
            self.assertTrue(spring.comp_only)
            self.assertIs(spring.j_node, node)
            self.assertTrue(spring.i_node.support_DZ)

    def test_open_bearing_transmits_no_vertical_force_but_keeps_horizontal_reactions(self):
        rows = support_rows(self.roof)
        opened = next(r for r in rows if r["support"] == self.nodes[2.]
                      and r["combination"] == "SLS_garden")
        self.assertEqual(opened["support_kind"], "purlin_bearing_only")
        self.assertFalse(opened["vertical_contact_active"])
        self.assertGreater(opened["Dz_mm"], 0.1)
        self.assertAlmostEqual(opened["Fz_kN"], 0., places=9)
        self.assertAlmostEqual(opened["Fx_kN"], 1., places=9)
        self.assertAlmostEqual(opened["Fy_kN"], 2., places=9)
        closed = next(r for r in rows if r["support"] == self.nodes[2.]
                      and r["combination"] == "SLS_street")
        self.assertTrue(closed["vertical_contact_active"])
        self.assertLess(closed["Dz_mm"], 0.)
        self.assertLess(closed["Fz_kN"], 0.)
        for row in rows:
            self.assertLessEqual(row["Fz_kN"], 1e-8)

    def test_fixed_bearing_comparison_retains_previous_bilateral_restraints(self):
        roof = build_roof_model(self.layout, Settings(purlin_bearing_uplift=False))
        self.assertFalse(roof.purlin_wall_bearings)
        self.assertTrue(all(roof.model.nodes[n].support_DZ for n in roof.supports))

    def test_default_attached_purlin_has_zero_movement_and_circled_upward_force(self):
        roof = build_roof_model(self.layout)
        nodes_by_point = {(n.X, n.Y, n.Z): name for name, n in roof.model.nodes.items()}
        for name, case, forces in self.roof.nodal_loads:
            original = self.roof.model.nodes[name]
            target = nodes_by_point[(original.X, original.Y, original.Z)]
            for direction, force in zip(("FX", "FY", "FZ"), forces):
                if force:
                    roof.model.add_node_load(target, direction, force, case=case)
            roof.nodal_loads.append((target, case, forces))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
        rows = support_rows(roof)
        for row in rows:
            self.assertEqual(row["support_kind"], "purlin_bearing")
            self.assertEqual(row["Dz_mm"], 0.)
        uplift = uplift_locations(rows)
        self.assertEqual(len(uplift), 1)
        self.assertEqual(uplift[0]["x_m"], 2.)
        self.assertGreater(uplift[0]["Fz_kN"], .1)
        self.assertFalse(lift_off_locations(rows))
        with TemporaryDirectory() as directory:
            for figure in (
                plot_plan_report(roof, [], Path(directory) / "plan.png", force_combo="SLS_street"),
                plot_model(roof, Path(directory) / "model.png", combo="SLS_street"),
            ):
                markers = [c.get_gid() for c in figure.axes[0].collections
                           if (c.get_gid() or "").startswith("uplift_")]
                self.assertEqual(markers, ["uplift_" + uplift[0]["support"]])
                self.assertTrue(any(f"uplift {uplift[0]['Fz_kN']:.3f} kN" in t.get_text()
                                    for t in figure.axes[0].texts))
                self.assertFalse(any("lift-off" in t.get_text() for t in figure.axes[0].texts))

    def test_legacy_saddle_wall_contacts_do_not_bypass_saddle_contact(self):
        roof = build_roof_model(add_purlin_saddles(legacy_roof_layout(HOUSE)),
                                Settings(purlin_bearing_uplift=True))
        contacts = roof.purlin_wall_bearings
        self.assertEqual(len(contacts), 8)  # four outer walls + four saddle centres
        self.assertEqual(sum("saddle" in roof.supports[n] for n in contacts), 4)
        internal_x = {b.bearings[0] for b in roof.layout.beams if b.category == "saddle"}
        for name, beam in roof.supports.items():
            if "purlin" in beam and roof.model.nodes[name].X in internal_x:
                self.assertNotIn(name, contacts)  # load still passes through sedlo
                self.assertFalse(roof.model.nodes[name].support_DZ)

    def test_real_lift_off_is_circled_in_both_pngs_independently_of_selected_case(self):
        with TemporaryDirectory() as directory:
            # Select a case where the middle contact is closed; the markers
            # must still show its opening in the other analysed combinations.
            figures = (
                plot_plan_report(self.roof, [], Path(directory) / "plan.png",
                                 force_combo="SLS_street"),
                plot_model(self.roof, Path(directory) / "model.png", combo="SLS_street"),
            )
            for figure in figures:
                markers = [c for c in figure.axes[0].collections
                           if (c.get_gid() or "").startswith("lift_off_")]
                self.assertEqual(len(markers), 1)
                self.assertEqual(markers[0].get_gid(), "lift_off_" + self.nodes[2.])
                self.assertTrue(any("lift-off" in t.get_text() and "mm" in t.get_text()
                                    for t in figure.axes[0].texts))


class ConnectionMovementTests(unittest.TestCase):
    def setUp(self):
        combinations = {"SLS_symmetric": None, "ULS_symmetric": None}

        def node(x, movements):
            return SimpleNamespace(
                X=x,
                Y=0.0,
                Z=4.0,
                DX={case: dx for case, (dx, dy) in movements.items()},
                DY={case: dy for case, (dx, dy) in movements.items()},
                RxnFX={case: 0.0 for case in combinations},
                RxnFY={case: 0.0 for case in combinations},
                RxnFZ={case: 0.0 for case in combinations},
            )

        self.roof = SimpleNamespace(
            model=SimpleNamespace(
                load_combos=combinations,
                nodes={
                    "A": node(
                        1.0, {"SLS_symmetric": (-0.003, -0.004), "ULS_symmetric": (-0.006, 0.008)}
                    ),
                    "B": node(
                        2.0, {"SLS_symmetric": (0.006, 0.0), "ULS_symmetric": (0.008, -0.015)}
                    ),
                    "purlin": node(3.0, {case: (1.0, 1.0) for case in combinations}),
                },
            ),
            wall_plate_connections={
                ("rafter_A", "street_wall_plate"): "A",
                ("rafter_B", "garden_wall_plate"): "B",
            },
        )

    def test_each_connection_uses_resultant_xy_movement_in_mm(self):
        service = wall_plate_connection_rows(self.roof, "SLS_symmetric")
        self.assertEqual(len(service), 2)
        self.assertEqual(service[0]["Dx_mm"], -3.0)
        self.assertEqual(service[0]["Dy_mm"], -4.0)
        self.assertAlmostEqual(service[0]["horizontal_movement_mm"], 5.0)
        self.assertAlmostEqual(service[1]["horizontal_movement_mm"], 6.0)
        ultimate = wall_plate_connection_rows(self.roof, "ULS_symmetric")
        self.assertAlmostEqual(ultimate[1]["horizontal_movement_mm"], 17.0)

    def test_terminal_maximum_covers_all_connections_and_cases_but_not_purlins(self):
        output = StringIO()
        with redirect_stdout(output):
            print_wall_plate_connection_movements(self.roof)
        text = output.getvalue()
        self.assertIn("Max SLS horizontal rafter-to-wall-plate movement: 6.000 mm", text)
        self.assertIn("Max horizontal rafter-to-wall-plate movement: 17.000 mm", text)
        self.assertIn("rafter_B -> garden_wall_plate, ULS_symmetric, x=2.000 m", text)
        self.assertIn("Dx=+8.000, Dy=-15.000 mm", text)
        self.assertNotIn("purlin", text)

    def test_rigid_connections_report_zero(self):
        for name in self.roof.wall_plate_connections.values():
            for combo in self.roof.model.load_combos:
                self.roof.model.nodes[name].DX[combo] = 0.0
                self.roof.model.nodes[name].DY[combo] = 0.0
        output = StringIO()
        with redirect_stdout(output):
            print_wall_plate_connection_movements(self.roof)
        self.assertIn("Max horizontal rafter-to-wall-plate movement: 0.000 mm", output.getvalue())

    def test_no_wall_plate_connections_report_na(self):
        self.roof.wall_plate_connections.clear()
        output = StringIO()
        with redirect_stdout(output):
            print_wall_plate_connection_movements(self.roof)
        self.assertIn("N/A (no connections)", output.getvalue())


class UpliftLocationTests(unittest.TestCase):
    def test_one_marker_per_support_uses_worst_case_and_warning_threshold(self):
        rows = [
            dict(support="A", Fz_kN=0.1, combination="SLS_symmetric"),
            dict(support="A", Fz_kN=0.3, combination="ULS_garden"),
            dict(support="B", Fz_kN=-5.0, combination="ULS_street"),
            dict(support="C", Fz_kN=1e-6, combination="ULS_garden"),
            dict(support="D", Fz_kN=1.1e-6, combination="ULS_garden"),
        ]
        self.assertEqual(uplift_locations(rows), [rows[1], rows[4]])

    def test_no_uplift_has_no_markers(self):
        self.assertEqual(uplift_locations([]), [])
        self.assertEqual(uplift_locations([dict(support="A", Fz_kN=0)]), [])

    def test_lift_off_uses_largest_gap_not_force_or_selected_case(self):
        def seat(name, gap, **extra):
            return dict(support=name, support_kind="rafter_bearing_only", Dz_mm=gap,
                        Fz_kN=0, **extra)
        rows = [
            seat("A", 0.1, combination="SLS_symmetric"),
            seat("A", 0.3, combination="ULS_garden"),
            seat("B", -0.01),
            seat("C", 1e-6),
            dict(support="D", support_kind="purlin_bearing", Dz_mm=2),
            dict(support="E", support_kind="rafter_connection", Dz_mm=2),
            dict(support="F", support_kind="purlin_bearing_only", Dz_mm=2),
            dict(support="G", support_kind="saddle_bearing_only", Dz_mm=1),
        ]
        self.assertEqual(lift_off_locations(rows), [rows[1], rows[6], rows[7]])

    def test_no_lift_off_has_no_markers(self):
        self.assertEqual(lift_off_locations([]), [])
        self.assertEqual(lift_off_locations([
            dict(support="A", support_kind="rafter_bearing_only", Dz_mm=0),
        ]), [])


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
    def test_wall_bay_peak_can_be_on_a_supporting_cantilever(self):
        timber = Timber(.24, .24)
        beams = (
            BeamSpec("left", "purlin", (0., 0., 4.), (3.5, 0., 4.), timber, bearings=(0., 3.)),
            BeamSpec("middle", "purlin", (3.5, 0., 4.), (7.5, 0., 4.), timber),
            BeamSpec("right", "purlin", (7.5, 0., 4.), (11., 0., 4.), timber, bearings=(8., 11.)),
        )
        members = {}
        displacements = (
            lambda x: (0., .56 * (x-3.)**2 - .32 * (x-3.), 0.),
            lambda x: (0., -.02, 0.),
            lambda x: (0., -.02 + .04 * x, 0.),
        )
        for beam, displacement in zip(beams, displacements):
            member = PolynomialMember(displacement, beam.length)
            member.i_node = SimpleNamespace(X=beam.start[0], Y=0., Z=4.)
            member.j_node = SimpleNamespace(X=beam.end[0], Y=0., Z=4.)
            members[beam.name] = member
        nodes = {str(x): SimpleNamespace(X=x, Y=0., Z=4.) for x in (0., 3., 8., 11.)}
        roof = SimpleNamespace(
            layout=RoofLayout(beams, (), HOUSE, purlin_system="gerber",
                              gerber_joints=(("left", "middle"), ("middle", "right"))),
            model=SimpleNamespace(nodes=nodes, members=members),
            supports={"0.0": "left", "3.0": "left", "8.0": "right", "11.0": "right"},
        )
        result = purlin_wall_chord_result_columns(roof, beams[1], "SLS_test")
        self.assertEqual(result["wall_chord_max_member"], "left")
        self.assertAlmostEqual(result["wall_chord_max_at_s_m"], .32 / (2 * .56), places=7)
        self.assertAlmostEqual(result["wall_chord_max_departure_mm"], .32**2 / (4 * .56) * 1000, places=7)
        self.assertEqual(result["wall_chord_L300_status"], "FAIL")

    def test_external_wall_chord_keeps_hinge_sag_when_member_is_straight(self):
        member = PolynomialMember(lambda x: (0., -0.02, 0.))
        local, _ = maximum_chord_departure(member, "SLS_test", 0., member.L())
        global_bay, _ = maximum_chord_departure(
            member, "SLS_test", 0., member.L(),
            reference_points=(np.array((-1., 0., 0.)), np.array((5., 0., 0.))),
        )
        self.assertLess(local, 1e-12)
        self.assertAlmostEqual(global_bay, .02, places=10)

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
    def test_c18_can_be_selected_independently_or_for_all_timber(self):
        self.assertEqual(Timber(0.08, 0.20, "C18").material, "C18")
        layout = legacy_roof_layout(
            HOUSE, rafter_material="C18", beam_material="C18",
            collar_ties=CollarTieParameters(material="C18"),
        )
        layout = add_purlin_saddles(add_purlin_spacers(layout), SaddleParameters())
        self.assertTrue(all(b.timber.material == "C18" for b in layout.beams))
        mixed = legacy_roof_layout(HOUSE, rafter_material="C18", beam_material="C24")
        for beam in mixed.beams:
            self.assertEqual(beam.timber.material, "C18" if beam.category == "rafter" else "C24")

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
        layout = legacy_roof_layout(HOUSE)
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

    def test_default_material_is_c18_for_all_timber(self):
        self.assertEqual(Timber(0.08, 0.2).material, "C18")
        self.assertTrue(all(b.timber.material == "C18" for b in RoofLayout.from_house(HOUSE).beams))
        mixed = legacy_roof_layout(HOUSE, rafter_material="C24", beam_material="C22")
        for beam in mixed.beams:
            self.assertEqual(beam.timber.material, "C24" if beam.category == "rafter" else "C22")

    def test_stronger_rafter_and_split_guard(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            source = HOUSE.read_text(encoding="utf-8")
            path.write_text(
                source.replace("\t8.55+0.67,", "\tStrongerRafter(8.55+0.67),"), encoding="utf-8"
            )
            layout = legacy_roof_layout(path)
            beam = next(b for b in layout.beams if b.name == "rafter_13_street")
            self.assertEqual(beam.timber.width, HouseInputs(path).get("STRONGER_RAFTER_THICKNESS"))
            path.write_text(
                source.replace("\t1.62+0.93,", "\tSplitRafter(1.62+0.93, 7),"), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "SplitRafter"):
                legacy_roof_layout(path)

    def test_roof_opening_must_not_bridge_rafter(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "house.py"
            source = HOUSE.read_text(encoding="utf-8").replace(
                "roof_window_x = (rafters[2] + rafters[3]) / 2.0", "roof_window_x = rafters[2]"
            )
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "opening cuts"):
                legacy_roof_layout(path)

    def test_invalid_sections_and_loads(self):
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Timber(bad, 0.2)
            with self.assertRaises(ValueError):
                Settings(joint_stiffness_factor=bad)
            with self.assertRaises(ValueError):
                Settings(horizontal_stiffness_kn_mm=bad)
            with self.assertRaises(ValueError):
                Settings(dormer_horizontal_stiffness_kn_mm=bad)
        for bad in ("wrong", "rigid", "0.12"):
            with self.assertRaises(ValueError):
                Settings(dormer_horizontal_stiffness_kn_mm=bad)
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
            with self.assertRaises(argparse.ArgumentTypeError):
                dormer_horizontal_stiffness_argument(bad)

    def test_dormer_stiffness_inheritance_and_explicit_rigid(self):
        self.assertEqual(dormer_horizontal_stiffness_argument("inherit"), "inherit")
        self.assertEqual(dormer_horizontal_stiffness_argument("0.015"), 0.015)
        self.assertIsNone(dormer_horizontal_stiffness_argument("rigid"))
        for general in (0.12, None):
            settings = Settings(
                horizontal_stiffness_kn_mm=general, dormer_horizontal_stiffness_kn_mm="inherit"
            )
            self.assertEqual(settings.wall_plate_stiffness("dormer_wall_plate"), general)
            for dormer in (0.015, None):
                settings = replace(settings, dormer_horizontal_stiffness_kn_mm=dormer)
                self.assertEqual(settings.wall_plate_stiffness("dormer_wall_plate"), dormer)
                for plate in (
                    "street_wall_plate",
                    "cut_street_wall_plate",
                    "garden_wall_plate_left",
                    "garden_wall_plate_right",
                ):
                    self.assertEqual(settings.wall_plate_stiffness(plate), general)


@unittest.skipUnless(HAS_PYNITE, "optional PyNite dependency")
class C18SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layout = legacy_roof_layout(
            HOUSE, rafter_material="C18", beam_material="C18",
            collar_ties=CollarTieParameters(material="C18"),
        )
        cls.layout = add_purlin_saddles(
            add_purlin_spacers(layout),
            SaddleParameters(length=layout.saddle_length_m, bolts=SaddleBoltParameters()),
        )
        cls.roof = build_roof_model(cls.layout)
        cls.residuals = solve_roof_model(cls.roof)

    def test_c18_stiffness_is_used_in_beams_spacers_collars_and_contacts(self):
        roof = self.roof
        material = roof.model.materials["C18"]
        self.assertEqual(material.E, 9e9)
        self.assertEqual(material.G, 0.56e9)
        self.assertEqual(TIMBER_E90_MEAN_PA["C18"], 300e6)
        self.assertEqual(TIMBER_MEAN_DENSITY_KG_M3["C18"], 380.0)
        for beam in self.layout.beams:
            if beam.category not in {"collar", "spacer"}:
                continue
            spring = roof.model.springs[beam.name]
            self.assertAlmostEqual(
                spring.ks, 9e9 * beam.timber.properties[0] * beam.pieces / beam.length
            )
        for contact in roof.saddle_contacts:
            spring = roof.model.springs[contact["contact"]]
            timber = next(
                b.timber for b in self.layout.beams if b.name == contact["purlin"]
            )
            saddle = next(b.timber for b in self.layout.beams if b.name == contact["saddle"])
            self.assertAlmostEqual(
                spring.ks, contact["area_m2"] / ((timber.height + saddle.height) / 300e6)
            )
        for bolt in roof.saddle_bolts:
            self.assertAlmostEqual(bolt["Kser_N_m"], 380**1.5 * 12 / 23 * 1000)

    def test_c18_solver_and_exports(self):
        self.assertLess(max(self.residuals.values()), 1e-5)
        self.assertTrue(all(r["material"] == "C18" for r in member_rows(self.roof)))
        self.assertTrue(saddle_contact_rows(self.roof))
        self.assertTrue(saddle_bolt_rows(self.roof))
        self.assertTrue(spacer_rows(self.roof))

    def test_cli_accepts_c18_for_rafters_and_beams(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "c18")
            output = StringIO()
            with redirect_stdout(output):
                main([
                    "--house", str(HOUSE), "--output", prefix, "--no-plot",
                    "--rafter-material", "C18", "--beam-material", "C18",
                ])
            basis = json.loads(Path(prefix + "_restrained_basis.json").read_text())
            for category in ("rafter", "purlin", "wall_plate", "spacer"):
                self.assertEqual(basis["timber_materials"][category], ["C18"])
            self.assertIn("rafter: C18; purlin: C18; wall_plate: C18", output.getvalue())


class PlanReportTests(unittest.TestCase):
    @staticmethod
    def row(combo, l300, l500):
        return dict(combination=combo, chord_L300_status=l300, chord_L500_status=l500)

    def test_middle_purlin_colour_requires_both_chords_to_pass(self):
        local = self.row("SLS_symmetric", "PASS", "PASS")
        wall = dict(wall_chord_reference="gerber_wall_to_wall",
                    wall_chord_L300_status="PASS", wall_chord_L500_status="FAIL")
        self.assertEqual(plan_deflection_status([dict(local, **wall)]), "L300")
        wall["wall_chord_L300_status"] = "FAIL"
        self.assertEqual(plan_deflection_status([dict(local, **wall)]), "fail")
        wall.update(wall_chord_L300_status="PASS", wall_chord_L500_status="PASS")
        self.assertEqual(plan_deflection_status([dict(local, **wall)]), "L500")
        # Passing the wall bay cannot hide a failed local hinge-to-hinge check.
        local["chord_L300_status"] = "FAIL"
        self.assertEqual(plan_deflection_status([dict(local, **wall)]), "fail")
        # A failing ULS displacement never changes an SLS colour.
        local["chord_L300_status"] = "PASS"
        uls = dict(local, **wall)
        uls.update(combination="ULS_middle", wall_chord_L300_status="FAIL")
        self.assertEqual(plan_deflection_status([dict(local, **wall), uls]), "L500")

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
        for beam in legacy_roof_layout(HOUSE).beams:
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
        cls.layout = legacy_roof_layout(HOUSE)
        cls.free = build_roof_model(
            cls.layout,
            Settings(
                purlin_lateral_restraint=False,
                horizontal_stiffness_kn_mm=None,
                dormer_horizontal_stiffness_kn_mm="inherit",
            ),
        )
        cls.free_residuals = solve_roof_model(cls.free)
        cls.fixed = build_roof_model(
            cls.layout,
            Settings(horizontal_stiffness_kn_mm=None, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
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
            if beam.category == "wall_plate":
                continue
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
        timber = (
            sum(
                b.length * b.timber.properties[0]
                for b in self.layout.beams
                if b.category != "wall_plate"
            )
            * 450
            * 10
        )
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
                dormer_horizontal_stiffness_kn_mm="inherit",
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
        self.assertEqual(
            len(members), sum(b.category != "wall_plate" for b in self.layout.beams) * 6
        )
        self.assertFalse(any(row["category"] == "wall_plate" for row in members))
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
        cls.layout = legacy_roof_layout(HOUSE)
        # Use a deliberately flexible case, independent of the user's chosen
        # default stiffness for subsequent roof experiments.
        cls.roof = build_anchored_roof_model(
            cls.layout,
            Settings(horizontal_stiffness_kn_mm=0.12, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
        cls.residuals = solve_roof_model(cls.roof)

    def test_intermediate_plates_are_unconnected_but_single_seats_stay_connected(self):
        roof = self.roof
        self.assertEqual(len(roof.wall_plate_bearings), 3)
        for rafter, seats in roof.rafter_seats.items():
            plates = [seat for seat in seats if seat[1] == "wall_plate"]
            if not plates:
                continue
            member = roof.model.members[rafter]
            outer = min(
                plates,
                key=lambda seat: roof.model.nodes[
                    roof.wall_plate_connections[(rafter, seat[0])]
                ].Z,
            )
            for plate, _, _ in plates:
                name = roof.wall_plate_connections[(rafter, plate)]
                node = roof.model.nodes[name]
                if plate == outer[0]:
                    self.assertNotIn(name, roof.wall_plate_bearings)
                    self.assertTrue(node.support_DZ)
                else:
                    self.assertIn(name, roof.wall_plate_bearings)
                    self.assertFalse(
                        any(getattr(node, "support_" + d)
                            for d in ("DX", "DY", "DZ", "RX", "RY", "RZ"))
                    )
                    self.assertIsNone(node.spring_DX[0])
                    self.assertIsNone(node.spring_DY[0])
                    contact = roof.model.springs[roof.wall_plate_bearings[name]]
                    self.assertTrue(contact.comp_only)
                    self.assertEqual(contact.j_node.name, name)
                    self.assertTrue(contact.i_node.support_DZ)
                self.assertIn(
                    name,
                    {n.name for sub in member.sub_members.values()
                     for n in (sub.i_node, sub.j_node)},
                )

    def test_intermediate_bearings_cannot_pull_or_transfer_horizontal_force(self):
        # Flexible saddles and loose eave connections reproduce the real
        # mixed-contact example: two intermediate seats bear, one opens.
        layout = legacy_roof_layout(
            HOUSE, beam_material="C24", collar_ties=CollarTieParameters()
        )
        roof = build_anchored_roof_model(
            add_purlin_saddles(
                add_purlin_spacers(layout),
                SaddleParameters(length=layout.saddle_length_m, bolts=SaddleBoltParameters()),
            ),
            Settings(horizontal_stiffness_kn_mm=0.0012, dormer_horizontal_stiffness_kn_mm=0.01),
        )
        self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
        opened, compressed = False, False
        for row in support_rows(roof):
            if row["support_kind"] != "rafter_bearing_only":
                continue
            self.assertEqual(row["Fx_kN"], 0)
            self.assertEqual(row["Fy_kN"], 0)
            self.assertEqual(row["horizontal_X_stiffness_kn_mm"], 0)
            self.assertEqual(row["horizontal_Y_stiffness_kn_mm"], 0)
            self.assertLessEqual(row["Fz_kN"], 1e-8)
            if row["vertical_contact_active"]:
                compressed |= row["Fz_kN"] < -0.01
                self.assertAlmostEqual(row["Fz_kN"], row["Dz_mm"] * 1000, places=6)
            else:
                opened = True
                self.assertEqual(row["Fz_kN"], 0)
                self.assertGreaterEqual(row["Dz_mm"], -1e-8)
        self.assertTrue(opened)
        self.assertTrue(compressed)

    def test_bearing_classification_does_not_depend_on_beam_order(self):
        roof = build_anchored_roof_model(replace(self.layout, beams=tuple(reversed(self.layout.beams))))

        def bearing_pairs(model):
            return {
                pair for pair, node in model.wall_plate_connections.items()
                if node in model.wall_plate_bearings
            }

        self.assertEqual(bearing_pairs(roof), bearing_pairs(self.roof))

    def test_configurable_stiffness_only_at_rafter_connections_purlin_bearings_rigid(self):
        roof = self.roof
        expected = roof.settings.horizontal_stiffness_kn_mm * 1e6
        for name, beam in roof.supports.items():
            node = roof.model.nodes[name]
            if name in roof.wall_plate_bearings:
                self.assertFalse(
                    any(getattr(node, "support_" + d)
                        for d in ("DX", "DY", "DZ", "RX", "RY", "RZ"))
                )
                self.assertIsNone(node.spring_DX[0])
                self.assertIsNone(node.spring_DY[0])
                continue
            purlin = "purlin" in beam
            self.assertEqual(node.support_DX, purlin)
            self.assertEqual(node.support_DY, purlin)
            self.assertTrue(node.support_DZ)
            self.assertEqual(node.support_RX, "purlin" in beam)
            self.assertFalse(node.support_RY)
            self.assertEqual(node.support_RZ, "wall_plate" in beam)
            for axis in ("DX", "DY"):
                if purlin:
                    self.assertIsNone(getattr(node, "spring_" + axis)[0])
                    for combo in roof.model.load_combos:
                        self.assertEqual(getattr(node, axis)[combo], 0)
                    continue
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

    def test_free_purlin_option_only_frees_y_and_keeps_x_rigid(self):
        roof = build_anchored_roof_model(
            self.layout,
            Settings(purlin_lateral_restraint=False, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
        for name, beam in roof.supports.items():
            node = roof.model.nodes[name]
            if name in roof.wall_plate_bearings:
                self.assertIsNone(node.spring_DX[0])
                self.assertIsNone(node.spring_DY[0])
                continue
            if "purlin" in beam:
                self.assertTrue(node.support_DX)
                self.assertTrue(node.support_DZ)
                self.assertIsNone(node.spring_DX[0])
                self.assertFalse(node.support_DY)
                self.assertIsNone(node.spring_DY[0])
            else:
                self.assertIsNotNone(node.spring_DX[0])
                self.assertIsNotNone(node.spring_DY[0])

    def test_dormer_override_changes_only_dormer_connection_dofs(self):
        for general, dormer in ((120.0, 0.015), (None, 0.015), (0.12, None)):
            with self.subTest(general=general, dormer=dormer):
                roof = build_anchored_roof_model(
                    self.layout,
                    Settings(
                        horizontal_stiffness_kn_mm=general, dormer_horizontal_stiffness_kn_mm=dormer
                    ),
                )
                dormer_nodes = []
                for name, plate in roof.supports.items():
                    node = roof.model.nodes[name]
                    if name in roof.wall_plate_bearings:
                        for axis in ("DX", "DY", "DZ"):
                            self.assertFalse(getattr(node, "support_" + axis))
                            self.assertIsNone(getattr(node, "spring_" + axis)[0])
                        continue
                    if "purlin" in plate:
                        expected = None  # purlin translations always rigid
                    elif plate == "dormer_wall_plate":
                        expected = dormer
                        dormer_nodes.append(name)
                    else:
                        expected = general
                    for axis in ("DX", "DY"):
                        self.assertEqual(getattr(node, "support_" + axis), expected is None)
                        self.assertEqual(
                            getattr(node, "spring_" + axis)[0],
                            None if expected is None else expected * 1e6,
                        )
                    self.assertTrue(node.support_DZ)
                    self.assertFalse(node.support_RY)
                self.assertTrue(dormer_nodes)
                self.assertEqual(roof.connections, self.roof.connections)
                self.assertEqual(roof.loads, self.roof.loads)

    def test_soft_dormer_connections_export_actual_stiffness_and_reduce_thrust(self):
        roof = build_anchored_roof_model(
            self.layout,
            Settings(horizontal_stiffness_kn_mm=0.12, dormer_horizontal_stiffness_kn_mm=1.2e-6),
        )
        residuals = solve_roof_model(roof)
        self.assertLess(max(residuals.values()), 1e-8)
        rows = support_rows(roof)
        baseline = support_rows(self.roof)
        dormer_rows = [r for r in rows if r["member"] == "dormer_wall_plate"]
        self.assertTrue(dormer_rows)
        self.assertLess(
            max(abs(r["outward_kN"]) for r in dormer_rows),
            0.01
            * max(abs(r["outward_kN"]) for r in baseline if r["member"] == "dormer_wall_plate"),
        )
        for row in rows:
            if row["support_kind"] == "purlin_bearing":
                self.assertEqual(row["horizontal_X_stiffness_kn_mm"], "rigid")
                self.assertEqual(row["horizontal_Y_stiffness_kn_mm"], "rigid")
                continue
            expected = 1.2e-6 if row["member"] == "dormer_wall_plate" else 0.12
            if row["support_kind"] == "rafter_bearing_only":
                expected = 0.0
            for axis in ("X", "Y"):
                self.assertEqual(row[f"horizontal_{axis}_stiffness_kn_mm"], expected)
                self.assertAlmostEqual(
                    row[f"F{axis.lower()}_kN"], expected * row[f"D{axis.lower()}_mm"], places=8
                )
        output = StringIO()
        with redirect_stdout(output):
            print_summary(roof, member_rows(roof), rows, residuals)
        self.assertIn("other=0.12 kN/mm; dormer=1.2e-06 kN/mm", output.getvalue())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.png"
            figure = plot_plan_report(roof, member_rows(roof), path)
            self.assertGreater(path.stat().st_size, 20000)
            self.assertTrue(
                any(
                    "other 0.12 kN/mm, dormer 1.2e-06 kN/mm" in text.get_text()
                    for text in figure.texts
                )
            )

    def test_stiff_springs_converge_to_rigid_and_flexible_supports_change_load_path(self):
        rigid = build_anchored_roof_model(
            self.layout,
            Settings(horizontal_stiffness_kn_mm=None, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
        stiff = build_anchored_roof_model(
            self.layout,
            Settings(horizontal_stiffness_kn_mm=1e4, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
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
            if row["support_kind"] == "rafter_bearing_only":
                self.assertEqual(row["horizontal_X_stiffness_kn_mm"], 0)
                self.assertEqual(row["horizontal_Y_stiffness_kn_mm"], 0)
                self.assertEqual(row["Fx_kN"], 0)
                self.assertEqual(row["Fy_kN"], 0)
                continue
            for axis in ("X", "Y"):
                if row["support_kind"] == "purlin_bearing":
                    self.assertEqual(row[f"horizontal_{axis}_stiffness_kn_mm"], "rigid")
                    self.assertEqual(row[f"D{axis.lower()}_mm"], 0)
                    continue
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

    def test_per_rafter_ring_beam_print_uses_direct_connection_reactions(self):
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
                self.assertTrue(rows)
                if rows[0]["support_kind"] == "rafter_bearing_only":
                    self.assertIn("bearing only; no horizontal force or hold-down", line)
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
            self.assertEqual(
                basis["settings"]["dormer_horizontal_stiffness_kn_mm"],
                Settings().dormer_horizontal_stiffness_kn_mm,
            )
            self.assertEqual(
                basis["wall_plate_connection_stiffness_kn_mm"]["dormer_wall_plate"],
                Settings().wall_plate_stiffness("dormer_wall_plate"),
            )
            self.assertTrue(basis["settings"]["purlin_lateral_restraint"])
            self.assertFalse(basis["settings"]["purlin_bearing_uplift"])
            self.assertEqual(basis["purlin_wall_bearings"]["count"], 0)
            self.assertIn("bilateral", basis["purlin_vertical_restraint"]["model"])
            self.assertIn("purlin", basis["plan_report"]["lift_off_markers"])
            self.assertFalse(basis["saddles"]["enabled"])
            self.assertFalse(basis["saddles"]["bolt_model"]["enabled"])
            self.assertFalse(Path(prefix + "_restrained_saddle_contacts.csv").exists())
            self.assertEqual(basis["purlin_system"], "gerber")
            self.assertTrue(basis["gerber"]["enabled"])
            self.assertEqual(basis["gerber"]["count"], 4)
            self.assertTrue(Path(prefix + "_restrained_gerber_joints.csv").exists())
            self.assertTrue(basis["spacers"]["enabled"])
            self.assertEqual(basis["spacers"]["count"], 16)
            self.assertTrue(Path(prefix + "_restrained_spacers.csv").exists())
            self.assertTrue(basis["collar_ties"]["enabled"])
            self.assertEqual(basis["collar_ties"]["parameters"]["height"], 0.15)
            self.assertEqual(basis["collar_ties"]["parameters"]["boards_per_pair"], 2)
            self.assertFalse(Path(prefix + "_restrained_saddle_bolts.csv").exists())
            self.assertIn("NOT verified", output.getvalue())
            self.assertIn("vertical load to wall bearings", output.getvalue())
            self.assertFalse(Path(prefix + "_free_basis.json").exists())
            self.assertEqual(basis["plan_report"]["force_combination"], "ULS_symmetric")
            self.assertFalse(Path(prefix + "_restrained_plan.png").exists())

    def test_cli_dormer_override_is_recorded_in_basis_and_support_csv(self):
        import csv
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "roof")
            output = StringIO()
            with redirect_stdout(output):
                main(
                    [
                        "--house",
                        str(HOUSE),
                        "--output",
                        prefix,
                        "--no-plot",
                        "--horizontal-stiffness",
                        "rigid",
                        "--dormer-horizontal-stiffness",
                        "0.015",
                    ]
                )
            basis = json.loads(Path(prefix + "_restrained_basis.json").read_text())
            self.assertIsNone(basis["settings"]["horizontal_stiffness_kn_mm"])
            self.assertEqual(basis["settings"]["dormer_horizontal_stiffness_kn_mm"], 0.015)
            self.assertEqual(
                basis["wall_plate_connection_stiffness_kn_mm"]["dormer_wall_plate"], 0.015
            )
            self.assertIsNone(
                basis["wall_plate_connection_stiffness_kn_mm"]["cut_street_wall_plate"]
            )
            with Path(prefix + "_restrained_supports.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                expected = "0.015" if row["member"] == "dormer_wall_plate" else "rigid"
                if row["support_kind"] == "rafter_bearing_only":
                    expected = "0.0"
                for axis in ("X", "Y"):
                    self.assertEqual(row[f"horizontal_{axis}_stiffness_kn_mm"], expected)
            self.assertIn("other=rigid; dormer=0.015 kN/mm", output.getvalue())

    def test_wall_plate_connection_forces_match_support_reactions_point_by_point(self):
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
                node = roof.model.nodes[row["seat"]]
                np.testing.assert_allclose(
                    (row["x_m"], row["y_m"], row["z_m"]), (node.X, node.Y, node.Z)
                )
                self.assertAlmostEqual(row["outward_kN"], row["outward_direction"] * row["Fy_kN"])
                reaction = next(
                    r
                    for r in support_rows(roof)
                    if r["support"] == row["seat"] and r["combination"] == combo
                )
                for field in (
                    "Fx_kN",
                    "Fy_kN",
                    "Fz_kN",
                    "outward_kN",
                    "Dx_mm",
                    "Dy_mm",
                    "horizontal_movement_mm",
                ):
                    self.assertEqual(row[field], reaction[field])
                self.assertAlmostEqual(
                    row["horizontal_movement_mm"],
                    np.hypot(node.DX[combo], node.DY[combo]) * 1000,
                )
            for plate in (b for b in roof.layout.beams if b.category == "wall_plate"):
                for axis in ("X", "Y"):
                    seat_total = sum(
                        row[f"F{axis.lower()}_kN"]
                        for row in rows
                        if row["wall_plate"] == plate.name
                    )
                    bearing_total = -sum(
                        getattr(support_reaction_node(roof, n), "RxnF" + axis)[combo] / 1000
                        for n, p in roof.supports.items()
                        if p == plate.name
                    )
                    self.assertAlmostEqual(seat_total, bearing_total, places=6)
        with self.assertRaisesRegex(ValueError, "unknown connection-force combination"):
            wall_plate_connection_rows(roof, "not_a_case")

    def test_wall_plate_is_rigid_reference_not_a_second_elastic_structure(self):
        roof = self.roof
        for beam in roof.layout.beams:
            if beam.category == "wall_plate":
                self.assertNotIn(beam.name, roof.model.members)
        self.assertTrue(roof.wall_plate_connections)
        for (rafter, plate), name in roof.wall_plate_connections.items():
            self.assertNotIn((rafter, plate), roof.seat_members)
            node = roof.model.nodes[name]
            member = roof.model.members[rafter]
            rafter_nodes = {
                n.name for sub in member.sub_members.values() for n in (sub.i_node, sub.j_node)
            }
            self.assertIn(name, rafter_nodes)
            self.assertFalse(node.support_RX)
            self.assertFalse(node.support_RY)
            for combo in roof.model.load_combos:
                self.assertAlmostEqual(node.RxnMX[combo], 0)
                self.assertAlmostEqual(node.RxnMY[combo], 0)

    def test_very_soft_connections_have_no_hidden_wall_plate_thrust(self):
        roof = build_anchored_roof_model(
            self.layout,
            Settings(
                horizontal_stiffness_kn_mm=1.2e-6, dormer_horizontal_stiffness_kn_mm="inherit"
            ),
        )
        self.assertLess(max(solve_roof_model(roof).values()), 1e-8)
        for combo in roof.model.load_combos:
            rows = wall_plate_connection_rows(roof, combo)
            self.assertTrue(rows)
            self.assertLess(max(abs(row["outward_kN"]) for row in rows), 0.0001)
            for row in rows:
                node = roof.model.nodes[row["seat"]]
                if row["support_kind"] == "rafter_bearing_only":
                    self.assertEqual(row["Fy_kN"], 0)
                    continue
                self.assertAlmostEqual(
                    row["Fy_kN"],
                    roof.settings.horizontal_stiffness_kn_mm * node.DY[combo] * 1000,
                    places=12,
                )

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

    def test_lift_off_circles_show_zero_force_seats_in_both_pngs(self):
        roof = self.roof
        members = member_rows(roof)
        supports = [dict(r, Fz_kN=-1.0, Dz_mm=0) for r in support_rows(roof)]
        candidate = next(r for r in supports if r["support_kind"] == "rafter_bearing_only"
                         and r["combination"] == "ULS_garden")
        candidate["Fz_kN"] = 0
        with TemporaryDirectory() as directory:
            for enabled in (False, True):
                candidate["Dz_mm"] = 0.24 if enabled else 0
                with patch("roof_frame_3d.support_rows", return_value=supports):
                    plan = plot_plan_report(roof, members, Path(directory) / "plan.png",
                                            force_combo="SLS_symmetric")
                    model = plot_model(roof, Path(directory) / "model.png")
                for figure in (plan, model):
                    markers = [c for c in figure.axes[0].collections
                               if (c.get_gid() or "").startswith("lift_off_")]
                    self.assertEqual(len(markers), int(enabled))
                    if enabled:
                        self.assertEqual(markers[0].get_gid(), "lift_off_" + candidate["support"])
                        self.assertTrue(any("lift-off 0.240 mm" in t.get_text()
                                            and "ULS_garden" in t.get_text()
                                            for t in figure.axes[0].texts))
                if enabled:
                    marker = next(c for c in plan.axes[0].collections
                                  if c.get_gid() == "lift_off_" + candidate["support"])
                    np.testing.assert_allclose(marker.get_offsets()[0],
                                               (candidate["x_m"], candidate["y_m"]))
                    marker3d = next(c for c in model.axes[0].collections
                                    if c.get_gid() == "lift_off_" + candidate["support"])
                    np.testing.assert_allclose([coords[0] for coords in marker3d._offsets3d],
                                               (candidate["x_m"], candidate["y_m"], candidate["z_m"]))

    def test_uplift_circles_show_all_cases_in_both_pngs_and_are_absent_without_uplift(self):
        from matplotlib.colors import to_rgba

        roof = self.roof
        members = member_rows(roof)
        # Isolate one lift-off case, different from both images' selected case.
        supports = [dict(r, Fz_kN=-1.0) for r in support_rows(roof)]
        candidate = next(r for r in supports if r["combination"] == "ULS_garden")
        with TemporaryDirectory() as directory:
            for enabled in (False, True):
                candidate["Fz_kN"] = 0.123 if enabled else -1.0
                with patch("roof_frame_3d.support_rows", return_value=supports):
                    plan = plot_plan_report(
                        roof,
                        members,
                        Path(directory) / f"plan_{enabled}.png",
                        force_combo="SLS_symmetric",
                    )
                    model = plot_model(roof, Path(directory) / f"model_{enabled}.png")
                for figure in (plan, model):
                    markers = [
                        c
                        for c in figure.axes[0].collections
                        if (c.get_gid() or "").startswith("uplift_")
                    ]
                    self.assertEqual(len(markers), int(enabled))
                    if enabled:
                        self.assertEqual(markers[0].get_gid(), "uplift_" + candidate["support"])
                        np.testing.assert_allclose(
                            markers[0].get_edgecolors()[0], to_rgba("#e00000")
                        )
                if enabled:
                    marker = next(
                        c
                        for c in plan.axes[0].collections
                        if c.get_gid() == "uplift_" + candidate["support"]
                    )
                    np.testing.assert_allclose(
                        marker.get_offsets()[0], (candidate["x_m"], candidate["y_m"])
                    )
                    self.assertTrue(
                        any(
                            "uplift 0.123 kN\nULS_garden" in t.get_text()
                            for t in plan.axes[0].texts
                        )
                    )
                    marker3d = next(
                        c
                        for c in model.axes[0].collections
                        if c.get_gid() == "uplift_" + candidate["support"]
                    )
                    np.testing.assert_allclose(
                        [coords[0] for coords in marker3d._offsets3d],
                        (candidate["x_m"], candidate["y_m"], candidate["z_m"]),
                    )


class CollarGeometryTests(unittest.TestCase):
    def test_default_paired_boards_sit_above_purlins(self):
        layout = legacy_roof_layout(HOUSE, collar_ties=CollarTieParameters())
        ties = [b for b in layout.beams if b.category == "collar"]
        purlin_top = HouseInputs(HOUSE).get("PURLIN_TOP_Z")
        self.assertEqual(len(ties), 16)
        self.assertEqual(sum(t.pieces for t in ties), 32)
        for tie in ties:
            self.assertEqual((tie.timber.width, tie.timber.height), (0.05, 0.15))
            self.assertEqual(tie.pieces, 2)
            self.assertAlmostEqual(tie.start[2] - tie.timber.height / 2, purlin_top)
            self.assertEqual(tie.start[2], tie.end[2])
        floor = HouseInputs(HOUSE).get("UPPER_FLOOR_START")
        self.assertAlmostEqual(layout.collar_parameters.top_height, purlin_top + 0.15 - floor)

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
            without = legacy_roof_layout(path)
            self.assertFalse(any(b.category == "collar" for b in without.beams))
            with_ties = legacy_roof_layout(path, collar_ties=CollarTieParameters())
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
        layout = legacy_roof_layout(HOUSE, collar_ties=parameters)
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
        base = legacy_roof_layout(HOUSE)
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
        original = legacy_roof_layout(HOUSE, collar_ties=CollarTieParameters())
        for b in base.beams:
            if b.name.endswith("_dormer"):
                main = b.name.removesuffix("dormer") + "street"
                self.assertEqual(
                    sum(t.pieces for t in original.beams if main in t.attached_rafters), 2
                )

    def test_height_step_keeps_two_boards_at_distinct_heights(self):
        base = legacy_roof_layout(HOUSE)
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
            CollarTieParameters(middle_lowering=0.08),
            upper_floor_z=HouseInputs(HOUSE).get("UPPER_FLOOR_START"),
        )
        ties = [b for b in layout.beams if "rafter_05_street" in b.attached_rafters]
        self.assertEqual([b.pieces for b in ties], [1, 1])
        self.assertAlmostEqual(abs(ties[0].start[2] - ties[1].start[2]), 0.08)

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
            legacy_roof_layout(HOUSE, collar_ties=CollarTieParameters(top_height=10))


@unittest.skipUnless(HAS_PYNITE, "install requirements-roof3d.txt to test the solver")
class CollarSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings(
            horizontal_stiffness_kn_mm=0.12, dormer_horizontal_stiffness_kn_mm="inherit"
        )
        cls.base = build_roof_model(legacy_roof_layout(HOUSE), settings)
        solve_roof_model(cls.base)
        cls.roof = build_roof_model(
            legacy_roof_layout(HOUSE, collar_ties=CollarTieParameters()), settings
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
        self.assertEqual(
            len(ties), sum(b.category == "collar" for b in roof.layout.beams) * 6
        )
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
        for name in (b.name for b in roof.layout.beams if b.category == "collar"):
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

    def test_cli_switch_records_independent_configuration_and_no_tie_comparison_prefix(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "roof")
            with redirect_stdout(StringIO()):
                main(["--house", str(HOUSE), "--output", prefix, "--no-plot", "--collar-ties"])
            basis = json.loads(Path(prefix + "_restrained_basis.json").read_text())
            self.assertTrue(basis["collar_ties"]["enabled"])
            self.assertEqual(
                basis["collar_ties"]["parameters"]["width"], CollarTieParameters().width
            )
            self.assertNotIn("kleštiny", basis["omitted"])
            with redirect_stdout(StringIO()):
                main(["--house", str(HOUSE), "--output", prefix, "--no-plot", "--no-collar-ties"])
            comparison = json.loads(Path(prefix + "_no_collars_restrained_basis.json").read_text())
            self.assertFalse(comparison["collar_ties"]["enabled"])
            self.assertIn("kleštiny", comparison["omitted"])
            self.assertTrue(Path(prefix + "_restrained_basis.json").exists())


class SaddleGeometryTests(unittest.TestCase):
    def test_saddle_length_follows_the_ifc_source(self):
        original = legacy_roof_layout(HOUSE)
        source = HouseInputs(HOUSE)
        self.assertAlmostEqual(original.saddle_length_m, source.get("SEDLO_LENGTH"))
        for beam in add_purlin_saddles(replace(original, saddle_length_m=1.8)).beams:
            if beam.category == "saddle":
                self.assertAlmostEqual(beam.length, 1.8)

    def test_four_same_section_bolsters_below_the_internal_joints(self):
        original = legacy_roof_layout(HOUSE)
        layout = add_purlin_saddles(original)
        saddles = [b for b in layout.beams if b.category == "saddle"]
        self.assertEqual(len(saddles), 4)
        self.assertEqual(layout.beams[:-4], original.beams)
        by_name = {b.name: b for b in layout.beams}
        for saddle in saddles:
            self.assertAlmostEqual(saddle.length, original.saddle_length_m)
            self.assertAlmostEqual(sum((saddle.start[0], saddle.end[0])) / 2, saddle.bearings[0])
            for name in saddle.supported_purlins:
                purlin = by_name[name]
                self.assertEqual(saddle.timber, purlin.timber)
                self.assertAlmostEqual(
                    saddle.start[2] + saddle.timber.height / 2,
                    purlin.start[2] - purlin.timber.height / 2,
                )
        with self.assertRaisesRegex(ValueError, "already present"):
            add_purlin_saddles(layout)

    def test_unequal_purlin_sections_are_rejected(self):
        original = legacy_roof_layout(HOUSE)
        for dimension in ("width", "height"):
            beams = list(original.beams)
            index = next(i for i, b in enumerate(beams) if b.category == "purlin")
            beams[index] = replace(
                beams[index],
                timber=replace(
                    beams[index].timber,
                    **{dimension: getattr(beams[index].timber, dimension) + 0.01},
                ),
            )
            with self.assertRaisesRegex(AssertionError, "same width and height"):
                add_purlin_saddles(replace(original, beams=tuple(beams)))

    def test_contact_stiffness_series_compression_and_parameter_validation(self):
        timber = Timber(0.24, 0.24, "C22")
        self.assertAlmostEqual(saddle_contact_stiffness(timber, timber, 0.024), 16.5e6)
        self.assertAlmostEqual(saddle_contact_stiffness(timber, timber, 0.024, 0.1), 1.65e6)
        mixed = Timber(0.24, 0.24, "C24")
        self.assertAlmostEqual(
            saddle_contact_stiffness(timber, mixed, 0.024), 0.024 / (0.24 / 330e6 + 0.24 / 370e6)
        )
        for name in ("length", "contact_spacing", "contact_stiffness_factor"):
            for value in (0, -1, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    SaddleParameters(**{name: value})


@unittest.skipUnless(HAS_PYNITE, "optional PyNite environment")
class SaddleSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roof = build_anchored_roof_model(
            add_purlin_saddles(legacy_roof_layout(HOUSE)),
            Settings(horizontal_stiffness_kn_mm=0.12, dormer_horizontal_stiffness_kn_mm="inherit"),
        )
        cls.residuals = solve_roof_model(cls.roof)
        cls.contacts = saddle_contact_rows(cls.roof)

    def test_contacts_cover_area_once_and_internal_bearings_do_not_bypass_saddles(self):
        roof = self.roof
        for saddle in (b for b in roof.layout.beams if b.category == "saddle"):
            contacts = [c for c in roof.saddle_contacts if c["saddle"] == saddle.name]
            self.assertAlmostEqual(
                sum(c["area_m2"] for c in contacts), saddle.length * saddle.timber.width
            )
            for name, beam_name in roof.supports.items():
                node = roof.model.nodes[name]
                if (
                    beam_name in saddle.supported_purlins
                    and abs(node.X - saddle.bearings[0]) < 1e-9
                ):
                    self.assertFalse(node.support_DZ)
                    self.assertTrue(node.support_DX)
            self.assertAlmostEqual(roof.model.members[saddle.name].L(), 1.5)
        guides = [r for r in support_rows(roof) if r["support_kind"] == "purlin_horizontal_guide"]
        self.assertEqual(len(guides), 8 * 6)
        self.assertTrue(all(abs(r["Fz_kN"]) < 1e-7 for r in guides))

    def test_equilibrium_compression_only_contact_and_fixed_chord_span(self):
        self.assertLess(max(self.residuals.values()), 1e-5)
        self.assertTrue(all(r["compression_kN"] >= -1e-8 for r in self.contacts))
        self.assertTrue(any(not r["active"] for r in self.contacts))
        self.assertTrue(
            all(
                r["compression_kN"] == 0 and r["gap_mm"] >= -1e-5
                for r in self.contacts
                if not r["active"]
            )
        )
        for r in self.contacts:
            if r["active"]:
                self.assertAlmostEqual(
                    r["compression_kN"], -r["gap_mm"] * r["stiffness_kN_mm"], places=7
                )
        middle = next(b for b in self.roof.layout.beams if b.name == "street_purlin_middle")
        chord = purlin_chord(self.roof, middle)
        self.assertAlmostEqual(chord.end_m - chord.start_m, 4.72)
        for combo in self.roof.model.load_combos:
            for saddle in (b for b in self.roof.layout.beams if b.category == "saddle"):
                weight = (
                    self.roof.settings.timber_density
                    * self.roof.settings.gravity
                    * (saddle.timber.properties[0] * saddle.length)
                    * self.roof.model.load_combos[combo].factors["G"]
                )
                reaction = sum(
                    self.roof.model.nodes[n].RxnFZ[combo]
                    for n, owner in self.roof.supports.items()
                    if owner == saddle.name
                )
                contact_force = sum(
                    r["compression_kN"] * 1000
                    for r in self.contacts
                    if r["saddle"] == saddle.name and r["combination"] == combo
                )
                self.assertAlmostEqual(reaction, weight + contact_force, places=3)

    def test_finer_mesh_recloses_contact_and_has_converged_purlin_deflection(self):
        # This geometry/material combination exposes PyNite 3.2's missing
        # reactivation: a deactivated spring penetrates again by ~0.02 mm.
        layout = legacy_roof_layout(HOUSE, beam_material="C24")
        departures = []
        for spacing in (0.1, 0.05):
            roof = build_anchored_roof_model(
                add_purlin_saddles(layout, SaddleParameters(contact_spacing=spacing)),
                Settings(horizontal_stiffness_kn_mm=120, dormer_horizontal_stiffness_kn_mm=0.01),
            )
            residuals = solve_roof_model(roof)
            rows = saddle_contact_rows(roof)
            self.assertLess(max(residuals.values()), 1e-5)
            self.assertTrue(all(r["gap_mm"] >= -1e-5 for r in rows if not r["active"]))
            middle = next(b for b in layout.beams if b.name == "street_purlin_middle")
            departures.append(
                chord_result_columns(roof, middle, "SLS_symmetric", fallback="supports")[
                    "chord_max_departure_mm"
                ]
            )
        self.assertLess(abs(departures[1] / departures[0] - 1), 0.01)


class SaddleBoltTests(unittest.TestCase):
    def test_ec5_stiffness_per_bolt_one_shear_plane_and_uls_reduction(self):
        timber = Timber(0.24, 0.24, "C24")
        k = saddle_bolt_stiffness(timber, timber, 12.0, "SLS_symmetric")
        self.assertAlmostEqual(k / 1e6, 4.490837553081424)
        self.assertAlmostEqual(
            saddle_bolt_stiffness(timber, timber, 12.0, "ULS_symmetric"), k * 2 / 3
        )
        mixed = Timber(0.24, 0.24, "C22")
        self.assertAlmostEqual(
            saddle_bolt_stiffness(timber, mixed, 12.0, "SLS_symmetric"),
            (420 * 410) ** 0.75 * 12 / 23 * 1000,
        )

    def test_trial_parameter_validation(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                SaddleBoltParameters(diameter_mm=value)
        for value in (0, -1, True, 2.5):
            with self.assertRaises(ValueError):
                SaddleBoltParameters(count_per_end=value)
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                SaddleBoltParameters(slip_gap_mm=value)
        with self.assertRaises(ValueError):
            SaddleBoltParameters(hold_down="rigid")

    def test_face_slip_includes_rotation_but_rejects_rigid_body_movement(self):
        bolt = dict(
            upper_node="upper", lower_node="lower", purlin_height_m=0.24, saddle_height_m=0.24
        )
        upper = SimpleNamespace(
            DX={"SLS": 0.003 + 0.001 * 0.24},
            DY={"SLS": 0.004 - 0.002 * 0.24},
            RY={"SLS": 0.001},
            RX={"SLS": 0.002},
        )
        lower = SimpleNamespace(
            DX={"SLS": 0.003}, DY={"SLS": 0.004}, RY={"SLS": 0.001}, RX={"SLS": 0.002}
        )
        model = SimpleNamespace(nodes={"upper": upper, "lower": lower})
        for direction in ("X", "Y"):
            self.assertAlmostEqual(bolt_face_slip(model, bolt, direction, "SLS"), 0.0)
        upper.RY["SLS"] += 0.01
        self.assertAlmostEqual(bolt_face_slip(model, bolt, "X", "SLS"), -0.0012)
        upper.RX["SLS"] += 0.01
        self.assertAlmostEqual(bolt_face_slip(model, bolt, "Y", "SLS"), 0.0012)


@unittest.skipUnless(HAS_PYNITE, "optional PyNite environment")
class SaddleBoltSolverTests(unittest.TestCase):
    def test_deadband_matches_hand_solution_and_recovers_fixed_node_reactions(self):
        from Pynite import FEModel3D

        for gap_mm in (0.0, 1.0):
            model = FEModel3D()
            model.add_node("lower", 0.0, 0.0, 0.0)
            model.add_node("upper", 0.0, 0.0, 0.24)
            model.add_node("anchor", -1.0, 0.0, 0.24)
            model.def_support("lower", True, True, True, True, True, True)
            model.def_support("anchor", True, True, True, True, True, True)
            model.def_support("upper", False, True, True, True, True, True)
            base_k, bolt_k = 1e6, 4.490837553081424e6
            model.add_spring("base", "anchor", "upper", base_k)
            for combo, force in (
                ("SLS_small", 500.0),
                ("SLS_large", 5000.0),
                ("SLS_negative", -5000.0),
            ):
                model.add_node_load("upper", "FX", force, case=combo)
                model.add_load_combo(combo, {combo: 1})
            bolt = dict(
                bolt="bolt",
                saddle="saddle",
                purlin="purlin",
                x_m=0.0,
                y_m=0.0,
                upper_node="upper",
                lower_node="lower",
                purlin_height_m=0.24,
                saddle_height_m=0.24,
                Kser_N_m=bolt_k,
                slip_gap_m=gap_mm / 1000,
                hold_down_spring=None,
            )
            roof = SimpleNamespace(model=model, saddle_contacts=[], saddle_bolts=[bolt])
            solve_saddle_contact(roof)
            for combo, force in (
                ("SLS_small", 500.0),
                ("SLS_large", 5000.0),
                ("SLS_negative", -5000.0),
            ):
                if abs(force) / base_k <= gap_mm / 1000:
                    expected = force / base_k
                else:
                    expected = (
                        np.sign(force) * (abs(force) + bolt_k * gap_mm / 1000) / (base_k + bolt_k)
                    )
                self.assertAlmostEqual(model.nodes["upper"].DX[combo], expected, places=12)
                reaction = sum(n.RxnFX[combo] for n in model.nodes.values())
                self.assertAlmostEqual(reaction, -force, places=6)
                moment = sum(
                    n.RxnMY[combo] + n.Z * n.RxnFX[combo] - n.X * n.RxnFZ[combo]
                    for n in model.nodes.values()
                )
                self.assertAlmostEqual(moment, -0.24 * force, places=6)

    @classmethod
    def setUpClass(cls):
        cls.layout = legacy_roof_layout(HOUSE, beam_material="C24")
        cls.roof = build_roof_model(
            add_purlin_saddles(cls.layout, SaddleParameters(bolts=SaddleBoltParameters())),
            Settings(horizontal_stiffness_kn_mm=120, dormer_horizontal_stiffness_kn_mm=0.01),
        )
        cls.residuals = solve_roof_model(cls.roof)

    def test_two_per_purlin_end_four_per_saddle_and_face_force_equilibrium(self):
        roof = self.roof
        self.assertEqual(len(roof.saddle_bolts), 16)
        saddles = [b for b in roof.layout.beams if b.category == "saddle"]
        for saddle in saddles:
            bolts = [b for b in roof.saddle_bolts if b["saddle"] == saddle.name]
            self.assertEqual(len(bolts), 4)
            for purlin in saddle.supported_purlins:
                side = [b for b in bolts if b["purlin"] == purlin]
                self.assertEqual(len(side), 2)
                distances = sorted(abs(b["x_m"] - saddle.bearings[0]) for b in side)
                np.testing.assert_allclose(distances, [0.25, 0.5])
        self.assertLess(max(self.residuals.values()), 1e-5)
        rows = saddle_bolt_rows(roof)
        self.assertTrue(all(r["hold_down_tension_kN"] == 0 for r in rows))
        self.assertTrue(any(r["shear_resultant_kN"] > 0.01 for r in rows))
        for r in rows:
            self.assertAlmostEqual(
                r["Fx_to_purlin_kN"], -r["shear_stiffness_kN_mm"] * r["slip_X_mm"]
            )
            self.assertAlmostEqual(
                r["Fy_to_purlin_kN"], -r["shear_stiffness_kN_mm"] * r["slip_Y_mm"]
            )

    def test_generalised_connector_matrix_is_symmetric_and_balances_internal_moments(self):
        roof = self.roof
        states = {(b["bolt"], d): 1 for b in roof.saddle_bolts for d in ("X", "Y")}
        matrix, offset = bolt_shear_assembly(roof, "SLS_symmetric", states)
        self.assertLess(np.linalg.norm((matrix - matrix.T).data), 1e-8)
        np.testing.assert_array_equal(offset, 0)
        for bolt in roof.saddle_bolts:
            for direction in ("X", "Y"):
                force, moment = np.zeros(3), np.zeros(3)
                for node_name, dof, coefficient in bolt_face_terms(bolt, direction):
                    node = roof.model.nodes[node_name]
                    if dof.startswith("D"):
                        vector = np.eye(3)[("DX", "DY", "DZ").index(dof)] * coefficient
                        force += vector
                        moment += np.cross((node.X, node.Y, node.Z), vector)
                    else:
                        moment += np.eye(3)[("RX", "RY", "RZ").index(dof)] * coefficient
                np.testing.assert_allclose(force, 0, atol=1e-12)
                np.testing.assert_allclose(moment, 0, atol=1e-12)

    def test_clearance_and_ideal_hold_down_are_separate_and_stable(self):
        for gap, hold in ((1.0, "free"), (0.0, "ideal")):
            roof = build_roof_model(
                add_purlin_saddles(
                    self.layout,
                    SaddleParameters(bolts=SaddleBoltParameters(slip_gap_mm=gap, hold_down=hold)),
                ),
                Settings(
                    purlin_lateral_restraint=False,
                    horizontal_stiffness_kn_mm=120,
                    dormer_horizontal_stiffness_kn_mm=0.01,
                ),
            )
            self.assertLess(max(solve_roof_model(roof).values()), 1e-5)
            for row in saddle_bolt_rows(roof):
                for d in ("X", "Y"):
                    slip = row[f"slip_{d}_mm"]
                    expected = (
                        -row["shear_stiffness_kN_mm"] * np.sign(slip) * max(abs(slip) - gap, 0)
                    )
                    self.assertAlmostEqual(row[f"F{d.lower()}_to_purlin_kN"], expected)
                if hold == "free":
                    self.assertEqual(row["hold_down_tension_kN"], 0)
                else:
                    self.assertGreaterEqual(row["hold_down_tension_kN"], -1e-8)
                    # Ideal bound is engaged in tension only, never compression.
                    self.assertAlmostEqual(
                        row["hold_down_tension_kN"], 1000 * max(row["separation_mm"], 0), places=5
                    )

    def test_bearing_only_switch_export_and_plot_bolt_markers(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "bearing")
            with redirect_stdout(StringIO()):
                main(["--house", str(HOUSE), "--output", prefix, "--no-plot",
                      "--purlin-system", "saddles", "--no-saddle-bolts"])
            basis = json.loads(Path(prefix + "_restrained_basis.json").read_text())
            self.assertFalse(basis["saddles"]["bolt_model"]["enabled"])
            self.assertIsNone(basis["saddles"]["parameters"]["bolts"])
            self.assertFalse(Path(prefix + "_restrained_saddle_bolts.csv").exists())
            rows = member_rows(self.roof)
            figure = plot_plan_report(self.roof, rows, Path(directory) / "bolts.png")
            markers = [line.get_gid() for line in figure.axes[0].lines]
            self.assertTrue(all(b["bolt"] in markers for b in self.roof.saddle_bolts))


class SpacerGeometryTests(unittest.TestCase):
    def test_matches_ifc_dimensions_and_main_rafter_positions(self):
        original = legacy_roof_layout(HOUSE, beam_material="C24")
        layout = add_purlin_spacers(original)
        spacers = [b for b in layout.beams if b.category == "spacer"]
        main = [b for b in original.beams if b.category == "rafter" and b.name.endswith("_street")]
        data = HouseInputs(HOUSE)
        self.assertEqual(len(spacers), len(main))
        self.assertEqual(len(spacers), 16)
        self.assertEqual([b.start[0] for b in spacers], [b.start[0] for b in main])
        for beam in spacers:
            self.assertEqual(
                (beam.timber.width, beam.timber.height), data.get("PURLIN_SPACER_SIZE")
            )
            self.assertEqual(beam.timber.material, "C24")
            self.assertAlmostEqual(beam.length, data.get("PURLIN_SPACER_LENGTH"))
            self.assertAlmostEqual(beam.start[2] + beam.timber.height / 2, data.get("PURLIN_TOP_Z"))
        with self.assertRaisesRegex(ValueError, "already present"):
            add_purlin_spacers(layout)


@unittest.skipUnless(HAS_PYNITE, "optional PyNite dependency")
class SpacerSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = add_purlin_spacers(legacy_roof_layout(HOUSE))
        cls.roof = build_roof_model(
            add_purlin_saddles(cls.layout, SaddleParameters(bolts=SaddleBoltParameters())),
            Settings(purlin_lateral_restraint=False),
        )
        cls.residuals = solve_roof_model(cls.roof)

    def test_physical_length_stiffness_weight_and_purlin_attachments(self):
        roof = build_roof_model(self.layout)
        by_name = {b.name: b for b in self.layout.beams}
        expected_weight = 0
        for link in roof.spacer_links:
            beam = by_name[link["spacer"]]
            spring = roof.model.springs[beam.name]
            self.assertTrue(spring.comp_only)
            self.assertAlmostEqual(spring.ks, 10e9 * 0.08 * 0.20 / beam.length)
            self.assertNotAlmostEqual(spring.L(), beam.length)
            for endpoint, purlin_name in zip(
                (spring.i_node, spring.j_node), beam.supported_purlins
            ):
                purlin = by_name[purlin_name]
                self.assertAlmostEqual(endpoint.X, beam.start[0])
                self.assertAlmostEqual(endpoint.Y, purlin.start[1])
                self.assertAlmostEqual(endpoint.Z, purlin.start[2])
                self.assertFalse(endpoint.support_DZ)
            expected_weight += (
                roof.settings.timber_density * roof.settings.gravity * 0.08 * 0.20 * beam.length
            )
        self.assertAlmostEqual(
            -sum(force[2] for _, case, force in roof.nodal_loads if case == "G"), expected_weight
        )

    def test_free_purlin_model_equilibrium_and_compression_only_forces(self):
        self.assertLess(max(self.residuals.values()), 1e-5)
        rows = spacer_rows(self.roof)
        self.assertEqual(len(rows), 16 * len(self.roof.model.load_combos))
        for row in rows:
            self.assertGreaterEqual(row["compression_kN"], 0)
            if row["active"]:
                self.assertAlmostEqual(
                    row["compression_kN"], -row["stiffness_N_m"] * row["opening_mm"] / 1e6, places=7
                )
            else:
                self.assertEqual(row["compression_kN"], 0)
                self.assertGreaterEqual(row["opening_mm"], -1e-8)
        for row in member_rows(self.roof):
            if row["category"] == "spacer":
                self.assertLessEqual(row["N_min_kN"], 1e-8)
                self.assertEqual(row["chord_L300_status"], "")

    def test_axial_opening_and_closing_match_hand_solution(self):
        from Pynite import FEModel3D

        # X and Y orientations catch inactive-spring displacement/force bugs
        # in the pinned library; the active-set solver must use raw movement.
        for direction, point in (("X", (2.0, 0.0, 0.0)), ("Y", (0.0, 2.0, 0.0))):
            model = FEModel3D()
            model.add_node("a", 0.0, 0.0, 0.0)
            model.add_node("b", *point)
            model.def_support("a", True, True, True, True, True, True)
            model.def_support("b", direction != "X", direction != "Y", True, True, True, True)
            model.def_support_spring("b", "D" + direction, 1000.0)
            model.add_spring("spacer", "a", "b", 4000.0, comp_only=True)
            for combo, force in (("close", -100.0), ("open", 100.0)):
                model.add_node_load("b", "F" + direction, force, case=combo)
                model.add_load_combo(combo, {combo: 1})
            roof = SimpleNamespace(
                model=model,
                saddle_contacts=[],
                saddle_bolts=[],
                spacer_links=[dict(spacer="spacer", stiffness_N_m=4000.0)],
            )
            solve_saddle_contact(roof)
            self.assertAlmostEqual(getattr(model.nodes["b"], "D" + direction)["close"], -0.02)
            self.assertAlmostEqual(getattr(model.nodes["b"], "D" + direction)["open"], 0.1)
            rows = {r["combination"]: r for r in spacer_rows(roof)}
            self.assertAlmostEqual(rows["close"]["compression_kN"], 0.08)
            self.assertEqual(rows["open"]["compression_kN"], 0)
            self.assertFalse(rows["open"]["active"])

    def test_report_and_plots_include_spacers_without_deflection_pass_claim(self):
        with TemporaryDirectory() as directory:
            rows = member_rows(self.roof)
            figure = plot_plan_report(self.roof, rows, Path(directory) / "plan.png")
            identifiers = {artist.get_gid() for artist in figure.axes[0].get_children()}
            self.assertTrue(all(link["spacer"] in identifiers for link in self.roof.spacer_links))
            self.assertTrue(
                all(
                    link["spacer"] + "_axial_force" in identifiers
                    for link in self.roof.spacer_links
                )
            )
            plot_model(self.roof, Path(directory) / "model.png")
            output = StringIO()
            with redirect_stdout(output):
                print_summary(self.roof, rows, support_rows(self.roof), self.residuals)
            self.assertIn("16 purlin spacers", output.getvalue())
            self.assertIn("spacer_01", output.getvalue())

    def test_no_spacers_cli_comparison_is_separate(self):
        import json

        with TemporaryDirectory() as directory:
            prefix = str(Path(directory) / "comparison")
            with redirect_stdout(StringIO()):
                main(
                    [
                        "--house",
                        str(HOUSE),
                        "--output",
                        prefix,
                        "--no-plot",
                        "--no-spacers",
                        "--no-saddles",
                    ]
                )
            basis = json.loads(Path(prefix + "_no_spacers_restrained_basis.json").read_text())
            self.assertFalse(basis["spacers"]["enabled"])
            self.assertEqual(basis["spacers"]["count"], 0)
            self.assertFalse(Path(prefix + "_restrained_basis.json").exists())


def isfinite_number(value):
    return bool(np.isfinite(value))


if __name__ == "__main__":
    unittest.main()
