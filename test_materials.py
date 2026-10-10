"""Regression checks for the dependency-free, shared timber registry."""

from dataclasses import FrozenInstanceError
import subprocess
import sys
import unittest
from pathlib import Path

from materials import TIMBER_GRADES, TIMBER_GRADE_NAMES, TimberGrade, resolve_timber_grade


class MaterialTests(unittest.TestCase):
    def test_grade_names_and_case_insensitive_lookup(self):
        self.assertEqual(TIMBER_GRADE_NAMES,
                         ("C16", "C18", "C20", "C22", "C24", "GL24c", "GL24h", "GL28c", "GL28h"))
        for key, grade in TIMBER_GRADES.items():
            self.assertIs(resolve_timber_grade(key), grade)
            self.assertIs(resolve_timber_grade(" " + grade.name.upper() + " "), grade)

    def test_existing_strength_and_stiffness_values_are_preserved(self):
        expected = {
            # E, fm, fv, fc0, fc90, gammaM, G, E90, rho_mean.
            "c16": (8, 16, 3.2, 17, 2.2, 1.3, .50, 270, 370),
            "c18": (9, 18, 3.4, 18, 2.2, 1.3, .56, 300, 380),
            "c20": (9.5, 20, 3.6, 19, 2.3, 1.3, .59, 320, 400),
            "c22": (10, 22, 3.8, 20, 2.4, 1.3, .63, 330, 410),
            "c24": (11, 24, 4, 21, 2.5, 1.3, .69, 370, 420),
            "gl24c": (11, 24, 3.5, 21.5, 2.5, 1.25, .65, 300, 400),
            "gl24h": (11.5, 24, 3.5, 24, 2.5, 1.25, .65, 300, 420),
            "gl28c": (12.5, 28, 3.5, 24, 2.5, 1.25, .65, 300, 420),
            "gl28h": (12.6, 28, 3.5, 28, 2.5, 1.25, .65, 300, 460),
        }
        for key, values in expected.items():
            grade = TIMBER_GRADES[key]
            self.assertEqual((grade.elastic_modulus_gpa, grade.bending_strength_mpa,
                              grade.shear_strength_mpa, grade.compression_parallel_mpa,
                              grade.compression_perpendicular_mpa, grade.material_partial_factor,
                              grade.shear_modulus_gpa, grade.perpendicular_modulus_mpa,
                              grade.mean_density_kg_m3), values)
            self.assertEqual(grade.elastic_modulus_pa, values[0] * 1e9)
            self.assertEqual(grade.shear_modulus_pa, values[6] * 1e9)
            self.assertEqual(grade.perpendicular_modulus_pa, values[7] * 1e6)

    def test_registry_and_grades_are_immutable(self):
        with self.assertRaises(TypeError):
            TIMBER_GRADES["c16"] = TIMBER_GRADES["c24"]
        with self.assertRaises(FrozenInstanceError):
            TIMBER_GRADES["c16"].elastic_modulus_gpa = 20

    def test_custom_2d_grade_constructor_is_backwards_compatible(self):
        grade = TimberGrade("Custom", 9, 18, 3.4, 18, 2.2, 1.3)
        self.assertIs(resolve_timber_grade(grade), grade)
        with self.assertRaisesRegex(ValueError, "shear modulus is not defined"):
            _ = grade.shear_modulus_pa

    def test_lookup_rejects_bad_type_and_unknown_grade(self):
        with self.assertRaisesRegex(TypeError, "material must be"):
            resolve_timber_grade(None)
        with self.assertRaisesRegex(ValueError, "unknown timber material"):
            resolve_timber_grade("c14")

    def test_import_has_no_ifc_plotting_or_solver_dependencies(self):
        subprocess.run([
            sys.executable, "-c",
            "import materials, sys; "
            "assert not {'ifcopenshell', 'matplotlib', 'Pynite', 'numpy'} & sys.modules.keys()",
        ], check=True, cwd=Path(__file__).parent)

    def test_calculation_scripts_use_the_same_grade_class_and_registry(self):
        import rafter_load
        import roof_frame
        import roof_frame_3d

        self.assertIs(rafter_load.TimberGrade, TimberGrade)
        self.assertIs(rafter_load._TIMBER_GRADES, TIMBER_GRADES)
        self.assertIs(rafter_load._resolve_timber_grade, resolve_timber_grade)
        self.assertIs(roof_frame._resolve_timber_grade, resolve_timber_grade)
        for grade in TIMBER_GRADES.values():
            self.assertEqual(roof_frame_3d.Timber(.08, .20, grade.name.lower()).material, grade.name)
            self.assertEqual(roof_frame_3d.TIMBER_E90_MEAN_PA[grade.name], grade.perpendicular_modulus_pa)
            self.assertEqual(roof_frame_3d.TIMBER_MEAN_DENSITY_KG_M3[grade.name], grade.mean_density_kg_m3)


if __name__ == "__main__":
    unittest.main()
