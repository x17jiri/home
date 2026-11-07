"""Load-path, equilibrium and input-reader regressions for the House 2 roof."""

import math
import argparse
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from roof_frame_3d_house2 import (
    House2Inputs, Layout, Settings, build_roof_model, member_rows,
    PLAN_CHECK_COLORS, horizontal_stiffness, plan_check_statuses, plot_plan_report,
    project_loads, solve_roof_model, spring_axial_gap, support_rows, tributary_widths,
)

HOUSE = Path(__file__).with_name("house2.py")


class InputTests(unittest.TestCase):
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
                            "bad = __import__('os').getcwd()\n")
            data = House2Inputs(path)
            values = data.get("positions")
            self.assertEqual(len(values), 14)
            self.assertAlmostEqual(values[7]-values[6], .77)
            self.assertIsNone(data.get("layers")["missing"])
            with self.assertRaisesRegex(ValueError, "unsupported"):
                data.get("bad")

    def test_geometry_follows_live_house_dimensions(self):
        g = House2Inputs(HOUSE).get
        layout = Layout.from_house(HOUSE)
        self.assertEqual(sum(b.category == "brace" for b in layout.beams), 12)
        self.assertEqual(sum(b.category == "post" for b in layout.beams), 4)
        crosses = [b for b in layout.beams if b.category == "cross_beam"]
        self.assertEqual(len(crosses), 4)
        self.assertEqual(tuple(b.start[1] for b in crosses), g("PURLIN_CONNECTION_Y_POSITIONS"))
        clearance = g("PURLIN_CONNECTION_WALL_CLEARANCE")
        half_width = g("PURLIN_CONNECTION_BEAM_SIZE")[0]/2
        self.assertAlmostEqual(min(b.start[1] for b in crosses)-half_width-g("BWT"), clearance)
        self.assertAlmostEqual(g("HOUSE_DEPTH")-g("BWT")-max(b.start[1] for b in crosses)-half_width, clearance)
        self.assertEqual(len([p for p in layout.pins if p.name.startswith("purlin_cross_")]), 8)
        self.assertEqual(sum(b.category == "rafter" for b in layout.beams), 2*len(g("RAFTER_Y_POSITIONS")))
        collars = [b for b in layout.beams if b.category == "collar"]
        self.assertEqual(len(collars), len(layout.rafter_y))
        for tie in collars:
            self.assertEqual(tie.pieces, 2)
            self.assertEqual((tie.timber.width, tie.timber.height), g("COLLAR_TIE_SIZE"))
            self.assertAlmostEqual(tie.start[2]-tie.timber.height/2, g("PURLIN_Z")+g("PURLIN_SIZE")[1]/2)
            self.assertAlmostEqual(tie.start[2], tie.end[2])
            self.assertGreater(tie.weight_length, tie.length)
        purlin_bottom = g("PURLIN_Z")-g("PURLIN_SIZE")[1]/2
        for beam in layout.beams:
            if beam.category == "post":
                self.assertAlmostEqual(beam.end[2], purlin_bottom)
                self.assertAlmostEqual(beam.start[2], g("UPPER_FLOOR_START"))
            if beam.category == "cross_beam":
                self.assertEqual((beam.timber.width, beam.timber.height), g("PURLIN_CONNECTION_BEAM_SIZE"))
                self.assertAlmostEqual(beam.start[2], g("PURLIN_Z"))
                self.assertAlmostEqual(beam.end[2], g("PURLIN_Z"))
                self.assertAlmostEqual(beam.start[0], g("PURLIN_X_POSITIONS")[0]+g("PURLIN_SIZE")[0]/2)
                self.assertAlmostEqual(beam.end[0], g("PURLIN_X_POSITIONS")[1]-g("PURLIN_SIZE")[0]/2)
            if beam.category == "brace":
                dx, dy, dz = np.array(beam.end)-beam.start
                self.assertAlmostEqual(math.hypot(dx, dy), dz)
        self.assertEqual(layout.rafter_y, g("RAFTER_Y_POSITIONS"))
        direct_bearings = [pin for pin in layout.pins if pin.name.startswith("purlin_post_")]
        self.assertEqual(len(direct_bearings), 4)
        for pin in direct_bearings:
            self.assertAlmostEqual(pin.contact[2], purlin_bottom)
            self.assertEqual(pin.axes[1], pin.contact)
        self.assertFalse(any(pin.name.startswith("cross_post_") for pin in layout.pins))

    def test_non_aligned_posts_rejected(self):
        inputs = House2Inputs(HOUSE)
        inputs.cache["PURLIN_SUPPORT_Y_POSITIONS"] = ((3, 6), (3.1, 6))
        with patch("roof_frame_3d_house2.House2Inputs", return_value=inputs):
            with self.assertRaisesRegex(ValueError, "align"):
                Layout.from_house(HOUSE)

    def test_shared_load_basis_includes_interior_finish(self):
        mass, snow = project_loads()
        layers = House2Inputs(HOUSE.with_name("rafter_load.py")).get("ROOF_LAYERS_KG_M2")
        self.assertGreater(layers["Gypsum plasterboard"], 0)
        self.assertEqual(mass, sum(layers.values()))
        self.assertGreater(snow, 0)


class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = Layout.from_house(HOUSE)
        cls.roof = build_roof_model(cls.layout)
        cls.residuals = solve_roof_model(cls.roof)

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

    def test_compression_braces_open_and_reclose_without_tension(self):
        for combo in self.roof.model.load_combos:
            for name in self.roof.brace_springs:
                spring = self.roof.model.springs[name]
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
        for settings in (Settings(gable_bearings=False), Settings(brace_action="both")):
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
