"""Load-path, equilibrium and input-reader regressions for the House 2 roof."""

import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from roof_frame_3d_house2 import (
    House2Inputs, Layout, Settings, build_roof_model, member_rows,
    project_loads, solve_roof_model, spring_axial_gap, support_rows, tributary_widths,
)

HOUSE = Path(__file__).with_name("house2.py")


class InputTests(unittest.TestCase):
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
        self.assertEqual(sum(b.category == "cross_beam" for b in layout.beams), 2)
        self.assertEqual(sum(b.category == "rafter" for b in layout.beams), 2*len(g("RAFTER_Y_POSITIONS")))
        purlin_bottom = g("PURLIN_Z")-g("PURLIN_SIZE")[1]/2
        for beam in layout.beams:
            if beam.category == "post":
                self.assertAlmostEqual(beam.end[2], purlin_bottom-g("PURLIN_CONNECTION_BEAM_SIZE")[1])
                self.assertAlmostEqual(beam.start[2], g("UPPER_FLOOR_START"))
            if beam.category == "brace":
                dx, dy, dz = np.array(beam.end)-beam.start
                self.assertAlmostEqual(math.hypot(dx, dy), dz)
        self.assertEqual(layout.rafter_y, g("RAFTER_Y_POSITIONS"))

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

    def test_no_ground_reactions_at_internal_pins(self):
        for node in self.roof.model.nodes.values():
            if node.name in self.roof.supports:
                continue
            for combo in self.roof.model.load_combos:
                self.assertLess(abs(node.RxnFX[combo])+abs(node.RxnFY[combo])+abs(node.RxnFZ[combo]), 1e-4)
                self.assertLess(abs(node.RxnMX[combo])+abs(node.RxnMY[combo])+abs(node.RxnMZ[combo]), 1e-4)

    def test_compression_braces_open_and_reclose_without_tension(self):
        for combo in self.roof.model.load_combos:
            for spring in self.roof.model.springs.values():
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

    def test_numeric_arm_stiffness_is_converged(self):
        roof = build_roof_model(self.layout, Settings(joint_stiffness_factor=10000))
        self.assertLess(max(solve_roof_model(roof).values()), 1e-6)
        reference = {(r["support"], r["combination"]): r for r in support_rows(self.roof)}
        for row in support_rows(roof):
            self.assertLess(abs(row["Fz_kN"]-reference[row["support"], row["combination"]]["Fz_kN"]), .005)

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


if __name__ == "__main__":
    unittest.main()
