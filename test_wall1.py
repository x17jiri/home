import unittest

import matplotlib

matplotlib.use("Agg")

from house_drawing import Drawing


class BrickWallTests(unittest.TestCase):
    def test_grid_extends_around_anchor_and_alternates_rows(self) -> None:
        drawing = Drawing(-50, -50, 50, 50)
        bricks = drawing.add_brick_wall(
            brick_width=10,
            brick_height=10,
            polygon=[(-15, -15), (25, -15), (25, 25), (-15, 25)],
            start_x=0,
            start_y=0,
        )

        positions = {(brick.get_x(), brick.get_y()) for brick in bricks}
        self.assertIn((-20, -10), positions)
        self.assertIn((20, -10), positions)
        self.assertIn((-15, 0), positions)
        self.assertIn((15, 0), positions)
        self.assertTrue(all(brick.get_clip_path() is not None for brick in bricks))
        drawing.close()

    def test_starting_point_may_be_outside_polygon(self) -> None:
        drawing = Drawing(0, 0, 100, 100)
        bricks = drawing.add_brick_wall(
            brick_width=20,
            brick_height=10,
            polygon=[(10, 10), (90, 10), (90, 90), (10, 90)],
            start_x=-100,
            start_y=-100,
        )

        self.assertGreater(len(bricks), 0)
        self.assertEqual(len(drawing.ax.patches), len(bricks) + 1)
        drawing.close()

    def test_invalid_brick_size_is_rejected_before_drawing(self) -> None:
        drawing = Drawing(0, 0, 100, 100)

        with self.assertRaisesRegex(ValueError, "brick_width"):
            drawing.add_brick_wall(
                [(0, 0), (100, 0), (100, 100)],
                brick_width=0,
                brick_height=10,
                start_x=0,
                start_y=0,
            )

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_polygon_needs_three_points(self) -> None:
        drawing = Drawing(0, 0, 100, 100)

        with self.assertRaisesRegex(ValueError, "at least three"):
            drawing.add_brick_wall(
                [(0, 0), (100, 0)],
                brick_width=10,
                brick_height=10,
                start_x=0,
                start_y=0,
            )

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_start_defaults_to_first_polygon_point(self) -> None:
        drawing = Drawing(0, 0, 100, 100)
        bricks = drawing.add_brick_wall(
            brick_width=10,
            brick_height=10,
            polygon=[(13, 37), (13, 17), (43, 17), (43, 37)],
        )

        positions = {(brick.get_x(), brick.get_y()) for brick in bricks}
        self.assertIn((13, 27), positions)
        self.assertIn((18, 17), positions)
        drawing.close()

    def test_bottom_left_anchor_has_a_full_brick(self) -> None:
        drawing = Drawing(-100, 6900, 6600, 10100)
        bricks = drawing.add_brick_wall(
            brick_width=250,
            brick_height=250,
            polygon=[(0, 10000), (0, 7000), (6500, 7000), (6500, 10000)],
        )

        positions = {(brick.get_x(), brick.get_y()) for brick in bricks}
        self.assertIn((0, 9750), positions)
        self.assertNotIn((-125, 9750), positions)
        drawing.close()

    def test_half_rows_use_signed_anchor_relative_indexes(self) -> None:
        drawing = Drawing(-30, -40, 40, 40)
        bricks = drawing.add_brick_wall(
            [(-20, 30), (-20, -30), (30, -30), (30, 30)],
            brick_width=10,
            brick_height=10,
            start_x=0,
            start_y=0,
            half_rows=[0, 2, -1],
        )

        row_shapes = {(brick.get_y(), brick.get_height()) for brick in bricks}
        self.assertIn((-5, 5), row_shapes)   # row 0
        self.assertIn((-15, 10), row_shapes)  # row 1
        self.assertIn((-20, 5), row_shapes)  # row 2
        self.assertIn((0, 5), row_shapes)    # row -1
        self.assertIn((5, 10), row_shapes)   # row -2

        positions = {(brick.get_x(), brick.get_y()) for brick in bricks}
        self.assertIn((0, -5), positions)    # row 0 is unshifted
        self.assertIn((5, -15), positions)   # row 1 is shifted
        self.assertIn((5, 0), positions)     # row -1 is shifted
        drawing.close()

    def test_half_rows_reject_non_integer_indexes_before_drawing(self) -> None:
        drawing = Drawing(0, 0, 100, 100)

        with self.assertRaisesRegex(TypeError, "integer row indexes"):
            drawing.add_brick_wall(
                [(0, 100), (0, 0), (100, 0), (100, 100)],
                half_rows=[0, 1.5],
            )

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()


if __name__ == "__main__":
    unittest.main()
