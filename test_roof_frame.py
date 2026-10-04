import ast
from contextlib import redirect_stdout
from io import StringIO
from math import cos, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from matplotlib.figure import Figure

from rafter_load import CalculationReport, calculate_continuous_beam_response
from roof_frame import (Frame, Section, RoofGeometry, LoadCase, _HouseConstants,
                        build_roof_frame, roof_loads, check_roof_frame, comparison_rows)


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.section = Section(.08, .20, 10e9)

    def simple_beam(self, angle=0):
        frame = Frame()
        a = frame.add_node("A", 0, 0)
        b = frame.add_node("B", 4*cos(angle), 4*sin(angle))
        frame.add_element("beam", a, b, self.section)
        frame.fix_node(a)
        frame.fix_node(b, horizontal=False)
        return frame

    def test_single_element_simple_beam_exact_solution(self):
        frame = self.simple_beam()
        result = frame.solve({0: (0, -1000)})
        response = result.elements[0]
        expected = 5*1000*4**4/(384*self.section.elastic_modulus*self.section.inertia)
        self.assertAlmostEqual(response.displacement(2)[1], -expected)
        self.assertAlmostEqual(response.force_extrema()["moment"], 1000*4**2/8)
        self.assertAlmostEqual(response.force_extrema()["shear"], 1000*4/2)
        self.assertAlmostEqual(response.end_forces[2], 0)
        self.assertAlmostEqual(response.end_forces[5], 0)
        self.assertAlmostEqual(result.reactions[0][1], 2000)
        self.assertAlmostEqual(result.reactions[1][1], 2000)

    def test_sloped_cantilever_axial_transverse_and_global_reactions(self):
        angle, length, q = radians(35), 3., 800.
        frame = Frame()
        a = frame.add_node("A", 0, 0)
        b = frame.add_node("B", length*cos(angle), length*sin(angle))
        frame.add_element("beam", a, b, self.section)
        frame.fix_node(a)
        frame.fix_rotation(a)
        result = frame.solve({0: (0, -q)})
        response = result.elements[0]
        self.assertAlmostEqual(response.displacement(length)[0],
                               -q*sin(angle)*length**2/(2*self.section.elastic_modulus*self.section.area))
        self.assertAlmostEqual(response.displacement(length)[1],
                               -q*cos(angle)*length**4/(8*self.section.elastic_modulus*self.section.inertia))
        self.assertAlmostEqual(response.force_extrema()["moment"], q*cos(angle)*length**2/2)
        self.assertAlmostEqual(result.reactions[a][0], 0.)
        self.assertAlmostEqual(result.reactions[a][1], q*length)
        self.assertAlmostEqual(result.residual[result.rotation_dofs[a, "continuous"]],
                               q*length**2*cos(angle)/2)

    def test_continuous_beam_matches_independent_solver(self):
        spans, loads = (3.74, 4.8, 2.75), (1500., 2300., 900.)
        frame = Frame()
        x, nodes = 0., [frame.add_node("0", 0, 0)]
        for span in spans:
            x += span
            nodes.append(frame.add_node(str(len(nodes)), x, 0))
        for a, b in zip(nodes, nodes[1:]):
            frame.add_element("beam", a, b, self.section)
        for node in nodes:
            frame.fix_node(node, horizontal=node == 0)
        result = frame.solve({i: (0, -q) for i, q in enumerate(loads)})
        reference = calculate_continuous_beam_response(
            span_lengths_m=spans, uniform_loads_n_per_m=loads,
            elastic_modulus_pa=self.section.elastic_modulus, second_moment_m4=self.section.inertia)
        np.testing.assert_allclose([result.reactions[node][1] for node in nodes],
                                   reference.support_reactions_n, rtol=1e-10)
        np.testing.assert_allclose([-response.end_forces[2] for response in result.elements],
                                   reference.support_moments_nm[:-1], atol=1e-8)

    def test_mechanism_is_rejected(self):
        frame = Frame()
        a = frame.add_node("A", 0, 0)
        b = frame.add_node("B", 4, 0)
        frame.add_element("beam", a, b, self.section)
        with self.assertRaisesRegex(ValueError, "unstable"):
            frame.solve({0: (0, -1000)})

    def test_invalid_input_is_rejected(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Section(value, .2, 10e9)
        for pieces in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                Section(.05, .2, 10e9, pieces)
        frame = self.simple_beam()
        with self.assertRaises(ValueError):
            frame.solve({0: (0, float("nan"))})


class RoofFrameTests(unittest.TestCase):
    def setUp(self):
        self.house_path = Path(__file__).with_name("house_ifc.py")
        self.geometry = RoofGeometry.from_house(self.house_path, rafter_height=.2)
        self.rafter = Section(.08, .2, 10e9)
        self.collar = Section(.05, .2, 10e9, 2)

    def solve(self, restrained=False, snow=(1., .5), mesh=.35):
        model = build_roof_frame(self.geometry, self.rafter, self.collar,
                                 restrain_purlins=restrained, maximum_element_length=mesh)
        loads = roof_loads(model, self.geometry, spacing=.75, roof_mass=80, ceiling_mass=45,
                           snow_load=1.5, case=LoadCase("test", 1.35, 1.5, *snow))
        return model, loads, model.solve(loads)

    def test_house_geometry_and_collar_lowering(self):
        self.assertAlmostEqual(self.geometry.angle, 35.84, delta=.03)
        values = _HouseConstants(self.house_path)
        lower = RoofGeometry.from_house(self.house_path, rafter_height=.2, lowered=True)
        self.assertAlmostEqual(lower.collar_z, self.geometry.collar_z-values.get("VAZNICE_EXTRA_HEIGHT"))
        self.assertGreater(lower.collar_y[1]-lower.collar_y[0],
                           self.geometry.collar_y[1]-self.geometry.collar_y[0])

    def test_constant_reader_does_not_execute_calls(self):
        reader = _HouseConstants(self.house_path)
        with self.assertRaisesRegex(ValueError, "unsupported expression Call"):
            reader.evaluate(ast.parse("__import__('os').system('false')", mode="eval").body, set())

    def test_ridge_and_collar_have_zero_end_moments(self):
        model, _, result = self.solve()
        for element, response in zip(model.elements, result.elements):
            if model.nodes[element.start].name == "Hřeben" or element.member == "collar":
                self.assertAlmostEqual(response.end_forces[2], 0, places=6)
            if model.nodes[element.end].name == "Hřeben" or element.member == "collar":
                self.assertAlmostEqual(response.end_forces[5], 0, places=6)
        ridge = next(i for i, node in enumerate(model.nodes) if node.name == "Hřeben")
        self.assertNotEqual(result.rotation_dofs[ridge, "rafter_left"],
                            result.rotation_dofs[ridge, "rafter_right"])

    def test_element_force_end_equilibrium(self):
        _, _, result = self.solve()
        for response in result.elements:
            n, v, m = response.forces(response.length)
            np.testing.assert_allclose((n, v, m),
                                       (response.end_forces[3], -response.end_forces[4], response.end_forces[5]),
                                       atol=1e-7)

    def test_collar_pin_does_not_break_rafter_continuity(self):
        model, _, result = self.solve()
        collar = model.elements[-1]
        for node in (collar.start, collar.end):
            self.assertIn((node, "continuous"), result.rotation_dofs)
            self.assertNotEqual(result.rotation_dofs[node, "continuous"],
                                result.rotation_dofs[node, "collar_pin"])

    def test_global_force_and_moment_equilibrium_both_variants(self):
        for restrained in (False, True):
            model, loads, result = self.solve(restrained)
            applied = np.zeros(3)
            for index, (qy, qz) in loads.items():
                a, b = model.nodes[model.elements[index].start], model.nodes[model.elements[index].end]
                length = result.elements[index].length
                applied += (qy*length, qz*length,
                            ((a.y+b.y)/2*qz-(a.z+b.z)/2*qy)*length)
            for node, (h, v) in result.reactions.items():
                a = model.nodes[node]
                applied += (h, v, a.y*v-a.z*h)
            np.testing.assert_allclose(applied, 0, atol=1e-6)
            for node, (h, _) in result.reactions.items():
                if model.nodes[node].name.startswith("Vaznice"):
                    if restrained:
                        self.assertAlmostEqual(result.displacements[2*node], 0)
                    else:
                        self.assertAlmostEqual(h, 0, places=6)

    def test_mirrored_snow_mirrors_support_forces(self):
        for restraint in (False, True):
            model, _, result = self.solve(restraint, snow=(1., .5))
            _, _, mirror = self.solve(restraint, snow=(.5, 1.))
            supports = sorted(result.reactions, key=lambda node: model.nodes[node].y)
            for first, second in zip(supports, reversed(supports)):
                self.assertAlmostEqual(result.reactions[first][0], -mirror.reactions[second][0], places=6)
                self.assertAlmostEqual(result.reactions[first][1], mirror.reactions[second][1], places=6)

    def test_mesh_convergence_and_load_scaling(self):
        for restrained in (False, True):
            model, loads, result = self.solve(restrained, mesh=.5)
            fine, _, refined = self.solve(restrained, mesh=.15)
            for first, second in zip(result.reactions.values(), refined.reactions.values()):
                np.testing.assert_allclose(first, second, rtol=1e-8, atol=1e-6)
            self.assertAlmostEqual(result.member_extrema(model, "collar")["compression"],
                                   refined.member_extrema(fine, "collar")["compression"], places=5)
            self.assertAlmostEqual(result.maximum_displacement(model, "collar"),
                                   refined.maximum_displacement(fine, "collar"), places=9)
            scaled = model.solve({index: (2*qy, 2*qz) for index, (qy, qz) in loads.items()})
            np.testing.assert_allclose(scaled.displacements, 2*result.displacements, atol=1e-10)

    def test_snow_projection_and_no_ceiling_double_counting(self):
        model = build_roof_frame(self.geometry, self.rafter, self.collar, restrain_purlins=False)
        case = LoadCase("snow only", 0, 1, 1, 1)
        loads = roof_loads(model, self.geometry, spacing=.75, roof_mass=0, ceiling_mass=0,
                           snow_load=1.5, case=case)
        total = sum(-q[1]*model.element_matrices(model.elements[index])[0] for index, q in loads.items())
        self.assertAlmostEqual(total, 1500*.75*(self.geometry.right_eave-self.geometry.left_eave))
        base = roof_loads(model, self.geometry, spacing=.75, roof_mass=0, ceiling_mass=0,
                          snow_load=0, case=LoadCase("G", 1, 0, 0, 0))
        finishes = roof_loads(model, self.geometry, spacing=.75, roof_mass=0, ceiling_mass=45,
                              snow_load=0, case=LoadCase("G", 1, 0, 0, 0))
        total_finishes = sum((base[i][1]-finishes[i][1])*model.element_matrices(element)[0]
                             for i, element in enumerate(model.elements))
        length = ((self.geometry.collar_y[0]-self.geometry.left_wall)*2/cos(radians(self.geometry.angle))
                  + self.geometry.collar_y[1]-self.geometry.collar_y[0])
        self.assertAlmostEqual(total_finishes, 45*10*.75*length)

    def test_wrapper_generates_pdf_without_ifc_import(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()) as terminal:
            path = Path(directory)/"frame.pdf"
            with CalculationReport(path) as report:
                report.add_figure(Figure(figsize=(8.27, 11.69)))
                check = check_roof_frame(
                    title="Zkušební řez", geometry=self.geometry, material="c22",
                    width=.08, height=.2, spacing=.75, collar_material="c24",
                    collar_width=.05, collar_height=.2, collar_pieces=2,
                    roof_mass=80, ceiling_mass=45, snow_load=1.5,
                    restrain_purlins=False, report=report)
                self.assertGreaterEqual(report.page_count, 5)
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))
            self.assertEqual(len(check.results), 6)
            self.assertEqual(check.collar_grade, "C24")
            self.assertEqual(check.rafter_grade, "C22")
            rows = comparison_rows([check])
            self.assertEqual(rows[0][:2], ("Běžné", "H volné"))
            self.assertEqual(rows[0][3], "0,000")
            self.assertGreater(float(rows[0][4].replace(",", ".")), 0)
            self.assertIn("HORIZONTAL restraint at purlins: NO", terminal.getvalue())
            self.assertIn("no overall PASS/FAIL", terminal.getvalue())


if __name__ == "__main__":
    unittest.main()
