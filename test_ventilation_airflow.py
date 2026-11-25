"""Analytical checks of ventilation volumes under finished ceiling profiles."""

import unittest

from shapely.geometry import Polygon, box

from ventilation_airflow import volume_under_ceiling


class CeilingVolumeTests(unittest.TestCase):
    def test_flat_ceiling_excludes_floor_build_up_and_hole(self):
        footprint = box(0, 0, 4, 3).difference(box(1, 1, 2, 2))
        self.assertAlmostEqual(volume_under_ceiling(footprint, .2, [(0, 2.8), (4, 2.8)]), 11*2.6)

    def test_sloping_and_flat_ceiling_over_multiple_room_parts(self):
        footprint = box(0, 0, 4, 3).union(box(5, 0, 6, 2))
        profile = [(0, 1), (2, 3), (4, 3), (6, 1)]
        self.assertAlmostEqual(volume_under_ceiling(footprint, 0, profile), 12+18+3)

    def test_asymmetric_floor_uses_area_centroid_and_clips_at_floor(self):
        triangle = Polygon([(0, 0), (3, 0), (3, 3)])
        self.assertAlmostEqual(volume_under_ceiling(triangle, 0, [(0, 0), (3, 3)]), 9)
        self.assertAlmostEqual(volume_under_ceiling(box(0, 0, 4, 2), 1, [(0, 0), (4, 4)]), 9)


if __name__ == "__main__":
    unittest.main()
