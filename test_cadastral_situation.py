"""Check street offsets against independently specified site geometry."""

import unittest
from math import hypot

from shapely.geometry import Point, box

from cadastral_situation import street_band


class StreetBandTests(unittest.TestCase):
    def test_terminal_rays_close_the_site_and_clip_the_band(self):
        # None of these measured ends reaches the required site corners.
        street = [(-1, 0), (2, 0), (3, 0)]
        garden = [(10, -1), (10, -4), (10, -10), (9, -10)]
        neighbour = [(0, -8), (0, -2)]
        house = box(4, -9, 6, -7)
        enclosure, band = street_band(street, garden, neighbour, house, width=5)
        self.assertLess(enclosure.symmetric_difference(box(0, -10, 10, 0)).area, 1e-9)
        self.assertLess(band.symmetric_difference(box(0, -5, 10, 0)).area, 1e-9)

    def test_reversing_all_boundaries_keeps_the_south_band(self):
        boundaries = ([(-1, 0), (2, 0), (3, 0)],
                      [(10, -1), (10, -4), (10, -10), (9, -10)],
                      [(0, -8), (0, -2)])
        house = box(4, -9, 6, -7)
        _, forward = street_band(*boundaries, house)
        _, reverse = street_band(*(list(reversed(p)) for p in boundaries), house)
        self.assertLess(forward.symmetric_difference(reverse).area, 1e-9)

    def test_bent_street_has_seven_metre_perpendicular_offsets(self):
        street = [(0, 0), (5, 0), (10, 1)]
        garden = [(12, -1), (12, -12), (11, -12)]
        neighbour = [(-1, -10), (-1, -1)]
        _, band = street_band(street, garden, neighbour, box(3, -10, 5, -8))
        for a, b in zip(street, street[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dy)
            midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            edge = Point(midpoint[0] + 7 * dy / length, midpoint[1] - 7 * dx / length)
            outside = Point(midpoint[0] + 7.1 * dy / length, midpoint[1] - 7.1 * dx / length)
            self.assertLess(band.boundary.distance(edge), 1e-9)
            self.assertFalse(band.covers(outside))

    def test_taper_joins_five_point_five_and_seven_metre_end_widths(self):
        boundaries = ([(-1, 0), (2, 0), (3, 0)],
                      [(10, -1), (10, -4), (10, -10), (9, -10)],
                      [(0, -8), (0, -2)])
        house = box(4, -9, 6, -7)
        _, band = street_band(*boundaries, house, width=7, southwest_width=5.5)
        self.assertAlmostEqual(band.area, 62.5)
        self.assertLess(band.boundary.distance(Point(0, -5.5)), 1e-9)
        self.assertLess(band.boundary.distance(Point(10, -7)), 1e-9)
        self.assertLess(band.boundary.distance(Point(5, -6.25)), 1e-9)
        _, reversed_band = street_band(*(list(reversed(p)) for p in boundaries), house,
                                       width=7, southwest_width=5.5)
        self.assertLess(band.symmetric_difference(reversed_band).area, 1e-9)


if __name__ == "__main__":
    unittest.main()
