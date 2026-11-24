"""Independent edge-angle and façade-sector geometry checks."""

from math import acos, atan2, cos, degrees, hypot, radians, sin
import unittest

from cadastral_shading import maximum_segment_angle, viewing_geometry
from survey_points import SurveyAxes, SurveyFrame, SurveyHouse


class ShadingGeometryTests(unittest.TestCase):
    def test_highest_viewing_angle_can_occur_between_edge_corners(self):
        check = maximum_segment_angle((0, 0, 0), (3, -2, 3), (3, 2, 3))
        self.assertEqual(check["point"], (3, 0, 3))
        self.assertAlmostEqual(check["angle_degrees"], 45)
        sloped = maximum_segment_angle((0, 0, 0), (3, -2, 3), (3, 2, 5))
        for actual, expected in zip(sloped["point"], (3, 1.125, 4.5625)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(sloped["angle_degrees"], degrees(atan2(4.5625, hypot(3, 1.125))))

    def test_original_xyz_translation_does_not_change_the_angle(self):
        check = maximum_segment_angle((588800, 1144300, 417.6),
                                      (588803, 1144298, 420.6), (588803, 1144302, 422.6))
        reference = maximum_segment_angle((0, 0, 0), (3, -2, 3), (3, 2, 5))
        self.assertAlmostEqual(check["angle_degrees"], reference["angle_degrees"])
        self.assertAlmostEqual(check["plan_distance_m"], reference["plan_distance_m"])

    def test_130_degree_sector_faces_house_and_excludes_25_degrees_from_facade(self):
        axes = SurveyAxes(SurveyFrame(100, 200), (.6, .8))
        for centre in ((-10, 10), (10, 10)):
            with self.subTest(centre=centre):
                house = SurveyHouse(center=centre)
                _, origin, tangent, normal = viewing_geometry(axes, house)
                self.assertAlmostEqual(sum(t*n for t, n in zip(tangent, normal)), 0)
                self.assertAlmostEqual(hypot(*normal), 1)
                self.assertGreater(sum((c-o)*n for c, o, n in zip(axes.to_local(*centre), origin, normal)), 0)
                rays = [tuple(cos(radians(a))*n+sin(radians(a))*t for n, t in zip(normal, tangent))
                        for a in (-65, 65)]
                self.assertAlmostEqual(degrees(acos(sum(a*b for a, b in zip(*rays)))), 130)
                for ray in rays:
                    self.assertAlmostEqual(degrees(acos(abs(sum(r*t for r, t in zip(ray, tangent))))), 25)


if __name__ == "__main__":
    unittest.main()
