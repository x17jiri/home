"""Load-path, equilibrium and input-reader regressions for the House 2 roof."""

import math
import argparse
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from roof_frame_3d_house2 import (
    House2Inputs, Layout, Settings, build_roof_model, member_rows,
    PLAN_CHECK_COLORS, horizontal_stiffness, plan_check_statuses, plot_plan_report,
    parse_arguments, purlin_configuration_description, solve_roof_model, spring_axial_gap,
    support_rows, tributary_widths, purlin_support_load_envelopes,
    purlin_deflection_failure_messages,
)

HOUSE = Path(__file__).with_name("house2.py")


def layout_with_supports(positions, **overrides):
    inputs = House2Inputs(HOUSE)
    px = inputs.get("PURLIN_X_POSITIONS")
    inputs.cache["PURLIN_X_POSITIONS"] = ((px[0], inputs.get("HOUSE_WIDTH")/2, px[-1])
                                         if len(positions) == 3 else (px[0], px[-1]))
    inputs.cache["PURLIN_SUPPORT_Y_POSITIONS"] = positions
    inputs.cache.update(overrides)
    with patch("roof_frame_3d_house2.House2Inputs", return_value=inputs):
        return Layout.from_house(HOUSE)


class InputTests(unittest.TestCase):
    def test_purlin_failure_messages_show_worst_case_and_keep_separate_spans(self):
        beams = [SimpleNamespace(name="P1.1", category="purlin"),
                 SimpleNamespace(name="P2.1", category="purlin"),
                 SimpleNamespace(name="R01E", category="rafter")]
        def check(member, combo, actual, start=0, end=3):
            l300, l500 = (end-start)*1000/300, (end-start)*1000/500
            return dict(member=member, combination=combo, departure_mm=actual,
                        start_m=start, end_m=end, L300_limit_mm=l300, L500_limit_mm=l500,
                        L300_status="FAIL" if actual>l300 else "PASS",
                        L500_status="FAIL" if actual>l500 else "PASS")
        chords = [check("P1.1", "SLS_dead", 5), check("P1.1", "SLS_east", 8),
                  check("P1.1", "SLS_symmetric", 12), check("P1.1", "ULS_symmetric", 99),
                  check("P1.1", "SLS_west", 4, 3, 4.5),
                  check("P2.1", "SLS_symmetric", 6), check("R01E", "SLS_symmetric", 30)]
        messages = purlin_deflection_failure_messages(beams, chords)
        self.assertEqual(len(messages), 3)
        self.assertIn("P1.1, SLS_symmetric: L/300 failed; maximum allowed 10.000 mm, actual 12.000 mm", messages[0])
        self.assertIn("P1.1, SLS_symmetric: L/500 failed; maximum allowed 6.000 mm, actual 12.000 mm", messages[1])
        self.assertIn("P1.1, SLS_west: L/500 failed; maximum allowed 3.000 mm, actual 4.000 mm", messages[2])
        self.assertIn("span 3.000–4.500 m along member", messages[2])

    def test_purlin_failure_messages_are_empty_when_all_spans_pass(self):
        beam = SimpleNamespace(name="P1", category="purlin")
        row = dict(member="P1", combination="SLS_symmetric", start_m=0, end_m=3,
                   departure_mm=6, L300_limit_mm=10, L500_limit_mm=6,
                   L300_status="PASS", L500_status="PASS")
        self.assertEqual(purlin_deflection_failure_messages([beam], [row]), [])

    def test_post_load_envelopes_separate_limit_states_and_ignore_uplift_extremes(self):
        def reaction(post, combo, force, kind="post_base"):
            return dict(member=post, combination=combo, Fz_kN=force, kind=kind,
                        x_m=2, y_m=3, z_m=0)
        rows = [reaction("POST1.1", "SLS_dead", -10),
                reaction("POST1.1", "SLS_east", -15),
                reaction("POST1.1", "SLS_west", 25),
                reaction("POST1.1", "ULS_symmetric", -22),
                reaction("POST1.1", "ULS_dead", -14),
                reaction("POST2.1", "SLS_symmetric", 3),
                reaction("POST2.1", "SLS_west", 5),
                reaction("P1", "SLS_symmetric", -100, "gable_bearing")]
        envelopes = {(r["post"], r["limit_state"]): r
                     for r in purlin_support_load_envelopes(rows)}
        self.assertEqual(len(envelopes), 3)
        sls = envelopes["POST1.1", "SLS"]
        self.assertEqual((sls["downward_kN"], sls["combination"]), (15, "SLS_east"))
        self.assertEqual(envelopes["POST1.1", "ULS"]["downward_kN"], 22)
        self.assertEqual(envelopes["POST2.1", "SLS"]["downward_kN"], -3)
        self.assertEqual((sls["x_m"], sls["y_m"], sls["z_m"]), (2, 3, 0))

    def test_purlin_height_keeps_top_and_roof_fixed_and_shortens_posts(self):
        width, height = House2Inputs(HOUSE).get("PURLIN_SIZE")
        layouts = []
        for section_height in (height, height+.10):
            inputs = House2Inputs(HOUSE)
            inputs.cache["PURLIN_SIZE"] = (width, section_height)
            g = inputs.get
            top = g("UPPER_FLOOR_START")+g("PURLIN_CENTER_HEIGHT")
            self.assertAlmostEqual(g("PURLIN_Z")+section_height/2, top)
            with patch("roof_frame_3d_house2.House2Inputs", return_value=inputs):
                layout = Layout.from_house(HOUSE)
            bottoms = {b.start[0]: b.start[2]-section_height/2 for b in layout.beams if b.category == "purlin"}
            for beam in layout.beams:
                if beam.category == "post":
                    self.assertAlmostEqual(beam.end[2], bottoms[beam.start[0]])
            layouts.append(layout)
        self.assertAlmostEqual(layouts[0].slope, layouts[1].slope)
        for original, taller in zip(layouts[0].beams, layouts[1].beams):
            self.assertEqual(original.name, taller.name)
            if original.category == "post":
                self.assertAlmostEqual(original.length-taller.length, .10)
            elif original.category == "rafter":
                np.testing.assert_allclose(original.start, taller.start)
                np.testing.assert_allclose(original.end, taller.end)

    def test_horizontal_restraint_accepts_exactly_free_rigid_or_positive_springs(self):
        self.assertEqual(Settings().horizontal_stiffness_kn_mm, 0)
        self.assertEqual(horizontal_stiffness("free"), 0)
        self.assertEqual(horizontal_stiffness("0"), 0)
        self.assertIsNone(horizontal_stiffness("rigid"))
        self.assertEqual(horizontal_stiffness("0.12"), .12)
        for value in ("-1", "nan", "inf"):
            with self.assertRaises(argparse.ArgumentTypeError):
                horizontal_stiffness(value)
            with self.assertRaises(ValueError):
                Settings(horizontal_stiffness_kn_mm=float(value))

    def test_plan_colours_use_worst_sls_span_and_ignore_uls(self):
        beams = [SimpleNamespace(name=name) for name in ("green", "orange", "red", "grey")]
        def row(member, combo, l300="PASS", l500="PASS"):
            return dict(member=member, combination=combo, L300_status=l300, L500_status=l500)
        chords = [row("green", "SLS_dead"), row("green", "ULS_symmetric", "FAIL", "FAIL"),
                  row("orange", "SLS_dead"), row("orange", "SLS_west", l500="FAIL"),
                  row("red", "SLS_dead"), row("red", "SLS_east", "FAIL", "FAIL"),
                  row("grey", "ULS_dead")]
        self.assertEqual(plan_check_statuses(beams, chords),
                         dict(green="L500", orange="L300", red="fail", grey="not_assessed"))

    def test_reads_spacing_without_executing_house(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"house.py"
            path.write_text("import nonexistent_ifc\nraise RuntimeError('must not execute')\n"
                            "step = .67\nn = math.floor(9/step)\n"
                            "positions = tuple(i*step + (.1 if i > n//2 else 0) for i in range(n+1))\n"
                            "layers: dict[str, float | None] = {'missing': None}\n"
                            "rows = ((3.04,), (4.5,))\n"
                            "connectors = (*sorted({y for row in rows for y in row}), .4, 8.6)\n"
                            "bad = __import__('os').getcwd()\n")
            data = House2Inputs(path)
            values = data.get("positions")
            self.assertEqual(len(values), 14)
            self.assertAlmostEqual(values[7]-values[6], .77)
            self.assertIsNone(data.get("layers")["missing"])
            self.assertEqual(data.get("connectors"), (3.04, 4.5, .4, 8.6))
            with self.assertRaisesRegex(ValueError, "unsupported"):
                data.get("bad")

    def test_geometry_follows_live_house_dimensions(self):
        g = House2Inputs(HOUSE).get
        layout = Layout.from_house(HOUSE)
        post_count = sum(map(len, g("PURLIN_SUPPORT_Y_POSITIONS")))
        self.assertLessEqual(sum(b.category == "brace" for b in layout.beams), 3*post_count)
        self.assertEqual(sum(b.category == "brace" and b.name.endswith(".cross")
                             for b in layout.beams), len(g("PURLIN_SUPPORT_Y_POSITIONS")[0])
                         + len(g("PURLIN_SUPPORT_Y_POSITIONS")[-1]))
        self.assertEqual(sum(b.category == "post" for b in layout.beams), post_count)
        crosses = [b for b in layout.beams if b.category == "cross_beam"]
        self.assertEqual(len(crosses), len(g("PURLIN_CONNECTION_Y_POSITIONS")))
        self.assertEqual(tuple(b.start[1] for b in crosses), g("PURLIN_CONNECTION_Y_POSITIONS"))
        clearance = g("PURLIN_CONNECTION_WALL_CLEARANCE")
        half_width = g("PURLIN_CONNECTION_BEAM_SIZE")[0]/2
        self.assertAlmostEqual(min(b.start[1] for b in crosses)-half_width-g("BWT"), clearance)
        self.assertAlmostEqual(g("HOUSE_DEPTH")-g("BWT")-max(b.start[1] for b in crosses)-half_width, clearance)
        self.assertEqual(len([p for p in layout.pins if p.name.startswith("purlin_cross_")]), 2*len(crosses))
        self.assertEqual(sum(b.category == "rafter" for b in layout.beams), 2*len(g("RAFTER_Y_POSITIONS")))
        collars = [b for b in layout.beams if b.category == "collar"]
        self.assertEqual(len(collars), len(layout.rafter_y))
        for tie in collars:
            self.assertEqual(tie.pieces, 2)
            self.assertEqual((tie.timber.width, tie.timber.height), g("COLLAR_TIE_SIZE"))
            self.assertAlmostEqual(tie.start[2]-tie.timber.height/2, g("PURLIN_Z")+g("PURLIN_SIZE")[1]/2)
            self.assertAlmostEqual(tie.start[2], tie.end[2])
            self.assertGreater(tie.weight_length, tie.length)
        bottoms = {b.start[0]: b.start[2]-b.timber.height/2 for b in layout.beams if b.category == "purlin"}
        for beam in layout.beams:
            if beam.category == "post":
                self.assertAlmostEqual(beam.end[2], bottoms[beam.start[0]])
                self.assertAlmostEqual(beam.start[2], g("UPPER_FLOOR_START"))
            if beam.category == "cross_beam":
                self.assertEqual((beam.timber.width, beam.timber.height), g("PURLIN_CONNECTION_BEAM_SIZE"))
                self.assertAlmostEqual(beam.start[2], g("PURLIN_Z"))
                self.assertAlmostEqual(beam.end[2], g("PURLIN_Z"))
                self.assertAlmostEqual(beam.start[0], g("PURLIN_X_POSITIONS")[0]+g("PURLIN_SIZE")[0]/2)
                self.assertAlmostEqual(beam.end[0], g("PURLIN_X_POSITIONS")[-1]-g("PURLIN_SIZE")[0]/2)
            if beam.category == "brace":
                dx, dy, dz = np.array(beam.end)-beam.start
                self.assertAlmostEqual(math.hypot(dx, dy), dz)
        self.assertEqual(layout.rafter_y, g("RAFTER_Y_POSITIONS"))
        direct_bearings = [pin for pin in layout.pins if pin.name.startswith("purlin_post_")]
        self.assertEqual(len(direct_bearings), post_count)
        for pin in direct_bearings:
            self.assertAlmostEqual(pin.contact[2], bottoms[pin.contact[0]])
            self.assertEqual(pin.axes[1], pin.contact)
        self.assertFalse(any(pin.name.startswith("cross_post_") for pin in layout.pins))

    def test_independent_post_rows_follow_each_purlin(self):
        positions = ((3.04,), (4.5, 6))
        layout = layout_with_supports(positions)
        px = tuple(b.start[0] for b in layout.beams if b.category == "purlin")
        for x, ys in zip(px, positions):
            posts = [b.start[1] for b in layout.beams if b.category == "post" and b.start[0] == x]
            self.assertEqual(tuple(posts), ys)
        crosses = [b.start[1] for b in layout.beams if b.category == "cross_beam"]
        for ys in positions:
            for y in ys:
                self.assertEqual(crosses.count(y), 1)

    def test_empty_duplicate_nonfinite_and_outside_posts_rejected(self):
        for positions in (((), (4.5,)), ((3, 3), (4.5,)), ((3,), (float("nan"),)),
                          ((3,), (0,)), ((3,), (100,)), ((3,),)):
            with self.subTest(positions=positions), self.assertRaises(ValueError):
                layout_with_supports(positions)

    def test_braces_beyond_purlin_ends_are_skipped_individually(self):
        g = House2Inputs(HOUSE).get
        ys = (g("BWT")+.3, g("HOUSE_DEPTH")-g("BWT")-.3)
        layout = layout_with_supports((ys, ys), PURLIN_BRACE_DROP=.8)
        names = {b.name for b in layout.beams if b.category == "brace"}
        self.assertEqual(names, {f"BRACE{i}.{j}.{side}" for i in (1, 2)
                                for j, sides in ((1, ("back", "cross")), (2, ("front", "cross")))
                                for side in sides})
        for pin in (p for p in layout.pins if p.name.startswith("BRACE")):
            self.assertIn(pin.name.rsplit("_", 1)[0], names)

    def test_cli_uses_local_settings_without_reading_external_load_files(self):
        with patch("roof_frame_3d_house2.House2Inputs", side_effect=AssertionError("no file reads")):
            _, settings = parse_arguments([])
        self.assertEqual(settings, Settings())

    def test_edited_local_defaults_reach_cli_and_only_explicit_flags_override_them(self):
        defaults = Settings(roof_mass=166, snow_load=2.35, rafter_material="C24", beam_material="GL24c",
                            timber_density=510, gravity=9.81, gable_bearings=False, braces=True,
                            continuous_purlins=True, brace_action="both", horizontal_stiffness_kn_mm=.14,
                            joint_stiffness_factor=2000)
        with patch("roof_frame_3d_house2.Settings", return_value=defaults):
            _, unchanged = parse_arguments([])
            _, overridden = parse_arguments(["--snow", "1.1", "--no-braces", "--no-continuous-purlins"])
        self.assertEqual(unchanged, defaults)
        self.assertEqual(overridden, replace(defaults, snow_load=1.1, braces=False, continuous_purlins=False))


class ThreePurlinTests(unittest.TestCase):
    def test_middle_purlin_must_be_at_the_ridge_and_have_its_own_post_row(self):
        for positions, rows in (((2, 4, 7), ((4.5,),)*3),
                                ((2, float("nan"), 7), ((4.5,),)*3),
                                ((2, 4.375, 7), ((4.5,),)*2)):
            inputs = House2Inputs(HOUSE)
            inputs.cache.update(PURLIN_X_POSITIONS=positions, PURLIN_SUPPORT_Y_POSITIONS=rows)
            with self.subTest(positions=positions), patch("roof_frame_3d_house2.House2Inputs", return_value=inputs):
                with self.assertRaises(ValueError):
                    Layout.from_house(HOUSE)

    def test_ridge_support_preserves_rafters_and_bears_at_both_outer_faces(self):
        two = layout_with_supports(((4.5,), (4.5,)))
        three = layout_with_supports(((4.5,), (4.5,), (4.5,)))
        self.assertAlmostEqual(two.slope, three.slope)
        two_rafters = {b.name: b for b in two.beams if b.category == "rafter"}
        for rafter in (b for b in three.beams if b.category == "rafter"):
            np.testing.assert_allclose(rafter.start, two_rafters[rafter.name].start)
            np.testing.assert_allclose(rafter.end, two_rafters[rafter.name].end)
        purlins = [b for b in three.beams if b.category == "purlin"]
        self.assertEqual(len(purlins), 3)
        middle = purlins[1]
        self.assertGreater(middle.start[2], purlins[0].start[2])
        ridge_pins = [p for p in three.pins if p.name.endswith("_ridge_purlin")]
        self.assertEqual(len(ridge_pins), len(two_rafters))
        for pin in ridge_pins:
            self.assertAlmostEqual(abs(pin.contact[0]-three.width/2), middle.timber.width/2)
            self.assertAlmostEqual(pin.contact[2], middle.start[2]+middle.timber.height/2)
            self.assertAlmostEqual(pin.axes[1][0], three.width/2)
            self.assertAlmostEqual(pin.axes[1][2], middle.start[2])
            rafter_name = pin.name.removesuffix("_ridge_purlin")
            self.assertEqual(len(three.chords[rafter_name]), 4)
        self.assertFalse(any(b.name.startswith("BRACE2.") and b.name.endswith(".cross") for b in three.beams))

    def test_three_purlins_solve_and_conserve_roof_loading_with_all_options(self):
        layout = layout_with_supports(((4.5,), (4.5,), (4.5,)))
        baseline = build_roof_model(layout_with_supports(((4.5,), (4.5,))))
        roof_loads = [(name, case, q, a, b) for name, case, q, a, b in baseline.loads if name.startswith("R")]
        for continuous in (False, True):
            for braces in (False, True):
                with self.subTest(continuous=continuous, braces=braces):
                    roof = build_roof_model(layout, Settings(continuous_purlins=continuous, braces=braces))
                    self.assertEqual(roof_loads, [row for row in roof.loads if row[0].startswith("R")])
                    self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
                    self.assertEqual(len(roof.layout.purlin_joints), 0 if continuous else 3)
                    reactions = [r for r in support_rows(roof)
                                 if r["combination"] == "SLS_symmetric" and r["kind"] == "post_base"]
                    self.assertEqual(len(reactions), 3)
                    middle = next(r for r in reactions if r["member"] == "POST2.1")
                    self.assertGreater(abs(middle["Fz_kN"]), 1)
                    self.assertEqual(sum(kind == "gable_bearing" for kind in roof.support_kinds.values()), 6)


class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Preserve the two-post regression fixture independently of live edits.
        cls.layout = layout_with_supports(((3, 6), (3, 6)))
        cls.roof = build_roof_model(cls.layout)
        cls.residuals = solve_roof_model(cls.roof)

    def test_post_base_load_envelope_matches_solved_axial_force(self):
        envelopes = purlin_support_load_envelopes(support_rows(self.roof))
        self.assertEqual(len(envelopes), 2*len(self.layout.bases))
        for row in envelopes:
            post = self.roof.model.members[row["post"]]
            # Local X runs upward along each post. Base compression includes
            # the post's own weight and must match the downward base reaction.
            compression = post.axial(0, row["combination"])/1000
            self.assertAlmostEqual(row["downward_kN"], compression, places=6)

    def test_near_wall_posts_solve_with_only_the_fitting_braces(self):
        g = House2Inputs(HOUSE).get
        ys = (g("BWT")+.3, g("HOUSE_DEPTH")/2, g("HOUSE_DEPTH")-g("BWT")-.3)
        roof = build_roof_model(layout_with_supports((ys, ys), PURLIN_BRACE_DROP=.8), Settings(braces=True))
        self.assertEqual(len(roof.brace_springs), 14)
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)

    def test_single_posts_solve_with_hinges_continuity_and_optional_braces(self):
        for positions, settings in (
            (((4.5,), (4.5,)), Settings()),
            (((3.04,), (4.5,)), Settings()),
            (((3.04,), (4.5,)), Settings(continuous_purlins=True)),
            (((3.04,), (4.5,)), Settings(braces=True)),
        ):
            with self.subTest(positions=positions, settings=settings):
                roof = build_roof_model(layout_with_supports(positions), settings)
                self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
                purlins = [b for b in roof.layout.beams if b.category == "purlin"]
                self.assertEqual(len(purlins), 2 if settings.continuous_purlins else 4)
                self.assertEqual(len(roof.layout.purlin_joints), 0 if settings.continuous_purlins else 2)
                self.assertEqual(purlin_configuration_description(roof),
                                 "continuous" if settings.continuous_purlins else "2 pieces each")
                self.assertEqual(len(roof.brace_springs), 6 if settings.braces else 0)
                reactions = [r for r in support_rows(roof)
                             if r["kind"] == "post_base" and r["combination"] == "SLS_dead"]
                self.assertEqual(len(reactions), 2)
                for left, right, point in roof.layout.purlin_joints:
                    self.assertTrue(any(math.isclose(point[1], y) for ys in positions for y in ys))
                    member = roof.model.members[left]
                    for combo in roof.model.load_combos:
                        for direction in ("My", "Mz"):
                            self.assertLess(abs(member.moment(direction, member.L(), combo)), 1e-4)

    def test_braces_are_omitted_by_default_with_their_weight_and_connections(self):
        self.assertFalse(Settings().braces)
        self.assertEqual(sum(b.category == "brace" for b in self.layout.beams), 12)
        self.assertFalse(any(b.category == "brace" for b in self.roof.layout.beams))
        self.assertFalse(any(pin.name.startswith("BRACE") for pin in self.roof.layout.pins))
        self.assertFalse(self.roof.brace_springs)
        self.assertFalse(any(name.startswith("BRACE") for name in self.roof.model.springs))
        self.assertEqual(len(self.roof.nodal_loads), 2*len(self.roof.collar_springs))

    def test_purlins_have_three_pieces_with_bending_releases_at_both_posts(self):
        self.assertFalse(Settings().continuous_purlins)
        original = [b for b in self.layout.beams if b.category == "purlin"]
        pieces = [b for b in self.roof.layout.beams if b.category == "purlin"]
        self.assertEqual(len(original), 2)
        self.assertEqual(len(pieces), 6)
        self.assertAlmostEqual(sum(b.length for b in pieces), sum(b.length for b in original))
        self.assertEqual(len(self.roof.layout.purlin_joints), 4)
        for left, right, point in self.roof.layout.purlin_joints:
            first, second = self.roof.model.members[left], self.roof.model.members[right]
            self.assertEqual(first.j_node.name, second.i_node.name)
            np.testing.assert_allclose((first.j_node.X, first.j_node.Y, first.j_node.Z), point)
            self.assertTrue(any(math.isclose(point[0], p[0]) and math.isclose(point[1], p[1])
                                for _, p in self.layout.bases))
            for combo in self.roof.model.load_combos:
                for direction in ("My", "Mz"):
                    self.assertLess(abs(first.moment(direction, first.L(), combo)), 1e-4)

    def test_continuous_purlin_option_restores_bending_continuity_without_changing_weight(self):
        roof = build_roof_model(self.layout, Settings(continuous_purlins=True))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        self.assertEqual(sum(b.category == "purlin" for b in roof.layout.beams), 2)
        self.assertFalse(roof.layout.purlin_joints)
        def weight(model):
            return -sum(q*(b-a) for _, case, q, a, b in model.loads if case == "G") \
                   -sum(force[2] for _, case, force in model.nodal_loads if case == "G")
        self.assertAlmostEqual(weight(roof), weight(self.roof), places=6)
        moments = []
        for beam in (b for b in self.layout.beams if b.category == "purlin"):
            member = roof.model.members[beam.name]
            for _, point in self.layout.bases:
                if math.isclose(point[0], beam.start[0]):
                    moments.append(abs(member.moment("Mz", point[1]-beam.start[1], "SLS_symmetric")))
        self.assertGreater(max(moments), 1)

    def test_roof_area_and_snow_are_conserved(self):
        widths = tributary_widths(self.layout.rafter_y, *self.layout.roof_y)
        self.assertAlmostEqual(sum(widths), self.layout.roof_y[1]-self.layout.roof_y[0])
        expected = sum(b.length*abs(b.end[0]-b.start[0])/b.length
                       *self.roof.tributary_widths[b.name]*self.roof.settings.snow_load*1000
                       for b in self.layout.beams if b.category == "rafter")
        actual = -sum(q*(b-a) for _, case, q, a, b in self.roof.loads if case.startswith("S_"))
        self.assertAlmostEqual(actual, expected, places=6)
        for combo, relative in self.residuals.items():
            self.assertLess(relative, 1e-6, combo)

    def test_seats_and_post_ports_split_their_continuous_members(self):
        # A rounded sloping port could otherwise float beside its physical
        # rafter: PyNite uses a tight collinearity tolerance when splitting.
        for name, seat in self.roof.seat_nodes.items():
            member = self.roof.model.members[name]
            ends = {n.name for sub in member.sub_members.values() for n in (sub.i_node, sub.j_node)}
            self.assertIn(seat, ends)

    def test_collar_ties_attach_to_both_continuous_rafters_and_carry_force(self):
        for tie in (b for b in self.layout.beams if b.category == "collar"):
            spring = self.roof.model.springs[tie.name]
            self.assertFalse(spring.comp_only)
            self.assertAlmostEqual(
                spring.ks,
                self.roof.model.materials[tie.timber.material].E
                *tie.timber.width*tie.timber.height*tie.pieces/tie.length,
            )
            for side, node in zip(("E", "W"), (spring.i_node, spring.j_node)):
                rafter = self.roof.model.members[f"R{tie.name[2:]}{side}"]
                split_nodes = {n.name for sub in rafter.sub_members.values() for n in (sub.i_node, sub.j_node)}
                self.assertIn(node.name, split_nodes)
            self.assertTrue(all(spring.active[combo] for combo in self.roof.model.load_combos))
        forces = [abs(spring.ks*spring_axial_gap(spring, "SLS_symmetric"))
                  for name, spring in self.roof.model.springs.items() if name in self.roof.collar_springs]
        self.assertGreater(max(forces), 1)

    def test_collar_weight_includes_two_boards_and_no_direct_roof_load(self):
        for tie in (b for b in self.layout.beams if b.category == "collar"):
            spring = self.roof.model.springs[tie.name]
            ends = {spring.i_node.name, spring.j_node.name}
            weight = -sum(vector[2] for name, case, vector in self.roof.nodal_loads
                          if name in ends and case == "G")
            expected = (self.roof.settings.timber_density*self.roof.settings.gravity
                        *tie.timber.width*tie.timber.height*tie.pieces*tie.weight_length)
            self.assertAlmostEqual(weight, expected)
            self.assertFalse(any(name == tie.name for name, *_ in self.roof.loads))

    def test_no_ground_reactions_at_internal_pins(self):
        for node in self.roof.model.nodes.values():
            if node.name in self.roof.supports:
                continue
            for combo in self.roof.model.load_combos:
                self.assertLess(abs(node.RxnFX[combo])+abs(node.RxnFY[combo])+abs(node.RxnFZ[combo]), 1e-4)
                self.assertLess(abs(node.RxnMX[combo])+abs(node.RxnMY[combo])+abs(node.RxnMZ[combo]), 1e-4)

    def test_connector_orientation_constraints_add_no_force_or_moment_support(self):
        for beam in (b for b in self.layout.beams if b.category == "cross_beam"):
            node = self.roof.model.members[beam.name].i_node
            self.assertTrue(node.support_RX)
            self.assertFalse(node.support_DX or node.support_DY or node.support_DZ)
            self.assertFalse(node.support_RY or node.support_RZ)
            for combo in self.roof.model.load_combos:
                self.assertLess(abs(node.RxnMX[combo]), 1e-4)

    def test_post_orientation_constraints_add_no_force_or_moment_support(self):
        for beam in (b for b in self.layout.beams if b.category == "post"):
            node = self.roof.model.members[beam.name].j_node
            self.assertTrue(node.support_RZ)
            self.assertFalse(node.support_DX or node.support_DY or node.support_DZ)
            self.assertFalse(node.support_RX or node.support_RY)
            for combo in self.roof.model.load_combos:
                self.assertLess(abs(node.RxnMZ[combo]), 1e-4)

    def test_compression_braces_open_and_reclose_without_tension(self):
        roof = build_roof_model(self.layout, Settings(braces=True))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        self.assertEqual(len(roof.brace_springs), 12)
        self.assertEqual(sum(b.category == "brace" for b in roof.layout.beams), 12)
        self.assertEqual(len(roof.nodal_loads), 2*(len(roof.collar_springs)+12))
        for combo in roof.model.load_combos:
            for name in roof.brace_springs:
                spring = roof.model.springs[name]
                trial = -spring.ks*spring_axial_gap(spring, combo)
                if spring.active[combo]:
                    self.assertGreaterEqual(trial, -1e-5)
                else:
                    self.assertLessEqual(trial, 1e-5)

    def test_symmetric_load_has_mirrored_reactions(self):
        rows = [r for r in support_rows(self.roof) if r["combination"] == "SLS_symmetric"]
        for row in rows:
            opposite = min(rows, key=lambda r: abs(r["x_m"]-(self.layout.width-row["x_m"]))
                           +abs(r["y_m"]-row["y_m"])+abs(r["z_m"]-row["z_m"]))
            self.assertAlmostEqual(row["Fz_kN"], opposite["Fz_kN"], places=5)
            self.assertAlmostEqual(row["Fx_kN"], -opposite["Fx_kN"], places=5)

    def test_posts_and_gable_walls_both_take_load(self):
        rows = support_rows(self.roof)
        for kind in ("post_base", "gable_bearing"):
            self.assertTrue(any(r["kind"] == kind and r["Fz_kN"] < -.1 for r in rows))
        self.assertEqual(sum(r["kind"] == "post_base" and r["combination"] == "SLS_dead" for r in rows), 4)
        self.assertEqual(sum(r["kind"] == "gable_bearing" and r["combination"] == "SLS_dead" for r in rows), 4)

    def test_soft_wall_plate_seats_move_and_balance(self):
        roof = build_roof_model(self.layout, Settings(horizontal_stiffness_kn_mm=.12))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        self.assertGreater(max(r["horizontal_mm"] for r in support_rows(roof)), 1)

    def test_wall_plate_seats_slide_in_x_without_force_and_remain_fixed_in_y(self):
        for name in self.roof.seat_nodes.values():
            node = self.roof.model.nodes[name]
            self.assertFalse(node.support_DX)
            self.assertTrue(node.support_DY)
            self.assertTrue(node.support_DZ)
            self.assertFalse(node.spring_DX[0])
            self.assertFalse(node.spring_DY[0])
        rows = [r for r in support_rows(self.roof) if r["kind"] == "wall_plate_seat"]
        self.assertGreater(max(r["horizontal_mm"] for r in rows), 1)
        self.assertLess(max(abs(r["Fx_kN"]) for r in rows), 1e-7)
        self.assertTrue(all(r["Dy_mm"] == 0 for r in rows))
        for row in rows:
            self.assertAlmostEqual(row["horizontal_mm"], abs(row["Dx_mm"]))
        self.assertTrue(any(abs(r["Fz_kN"]) > .1 for r in rows))

    def test_rigid_wall_plate_comparison_remains_available(self):
        roof = build_roof_model(self.layout, Settings(horizontal_stiffness_kn_mm=None))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        rows = [r for r in support_rows(roof) if r["kind"] == "wall_plate_seat"]
        self.assertLess(max(r["horizontal_mm"] for r in rows), 1e-8)
        self.assertGreater(max(math.hypot(r["Fx_kN"], r["Fy_kN"]) for r in rows), .1)

    def test_forces_and_seat_movements_converge_with_numerical_arm_stiffness(self):
        roof = build_roof_model(self.layout, Settings(joint_stiffness_factor=10000))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        reference = {(r["support"], r["combination"]): r for r in support_rows(self.roof)}
        for row in support_rows(roof):
            self.assertLess(abs(row["Fz_kN"]-reference[row["support"], row["combination"]]["Fz_kN"]), .005)
            self.assertLess(abs(row["Dx_mm"]-reference[row["support"], row["combination"]]["Dx_mm"]), .01)
            self.assertLess(abs(row["Dy_mm"]-reference[row["support"], row["combination"]]["Dy_mm"]), .01)

    def test_post_only_and_bilateral_brace_options_solve(self):
        for settings in (Settings(gable_bearings=False, braces=True), Settings(braces=True, brace_action="both")):
            with self.subTest(settings=settings):
                roof = build_roof_model(self.layout, settings)
                self.assertLess(max(solve_roof_model(roof).values()), 1e-6)

    def test_deflection_reference_spans_follow_real_supports(self):
        _, rows = member_rows(self.roof)
        self.assertTrue(rows)
        for row in rows:
            self.assertGreater(row["span_m"], 0)
            self.assertAlmostEqual(row["L300_limit_mm"], row["span_m"]*1000/300)
            self.assertAlmostEqual(row["L500_limit_mm"], row["span_m"]*1000/500)
            self.assertTrue(math.isfinite(row["departure_mm"]))

    def test_plan_renders_member_status_fills_and_unassessed_tie_outlines(self):
        from matplotlib.colors import to_rgba
        chords = [dict(member=name, combination="SLS_dead", L300_status=l300, L500_status=l500)
                  for name, l300, l500 in (("R01E", "PASS", "PASS"),
                                           ("R02E", "PASS", "FAIL"),
                                           ("R03E", "FAIL", "FAIL"))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"plan.png"
            figure = plot_plan_report(self.roof, chords, path)
            self.assertGreater(path.stat().st_size, 1000)
            patches = {patch.get_gid(): patch for patch in figure.axes[0].patches if patch.get_gid()}
            for member, status in (("R01E", "L500"), ("R02E", "L300"), ("R03E", "fail"),
                                   ("PLATE_E", "not_assessed"), ("POST1.1", "not_assessed")):
                np.testing.assert_allclose(patches[member].get_facecolor(), to_rgba(PLAN_CHECK_COLORS[status]))
            self.assertEqual(patches["CT01"].get_facecolor()[3], 0)
            np.testing.assert_allclose(patches["CT01"].get_edgecolor(), to_rgba("#d000d0"))
            figure.clear()


if __name__ == "__main__":
    unittest.main()
