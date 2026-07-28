import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")

from matplotlib.colors import to_rgba

from house_drawing import Beam, Drawing, Narrow, Wide


class DrawingTests(unittest.TestCase):
    def test_wall_uses_millimetre_coordinates_and_default_pattern(self) -> None:
        drawing = Drawing(-100, -100, 800, 1400)
        wall = drawing.add_wall(10, 10, 30, 200)

        self.assertEqual(wall.get_xy(), (10, 10))
        self.assertEqual(wall.get_width(), 20)
        self.assertEqual(wall.get_height(), 190)
        self.assertEqual(wall.get_hatch(), "///")
        self.assertEqual(drawing.ax.get_ylim(), (1400, -100))
        drawing.close()

    def test_reversed_wall_corners_are_normalised(self) -> None:
        drawing = Drawing(0, 0, 100, 100)
        wall = drawing.add_wall(40, 80, 10, 20)

        self.assertEqual(wall.get_xy(), (10, 20))
        self.assertEqual(wall.get_width(), 30)
        self.assertEqual(wall.get_height(), 60)
        drawing.close()

    def test_ellipse_is_inscribed_in_normalised_box(self) -> None:
        drawing = Drawing(0, 0, 100, 100)
        ellipse = drawing.add_ellipse(
            80,
            70,
            20,
            10,
            facecolor="lightblue",
            hatch="xx",
        )

        self.assertEqual(ellipse.center, (50, 40))
        self.assertEqual(ellipse.width, 60)
        self.assertEqual(ellipse.height, 60)
        self.assertEqual(ellipse.get_hatch(), "xx")
        self.assertEqual(ellipse.get_facecolor(), to_rgba("lightblue"))
        drawing.close()

    def test_out_of_bounds_ellipse_is_rejected(self) -> None:
        drawing = Drawing(0, 0, 100, 100)

        with self.assertRaisesRegex(ValueError, "outside the drawing area"):
            drawing.add_ellipse(10, 10, 101, 90)

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_out_of_bounds_wall_is_rejected(self) -> None:
        drawing = Drawing(0, 0, 100, 100)
        with self.assertRaisesRegex(ValueError, "outside the drawing area"):
            drawing.add_wall(-1, 10, 30, 20)
        drawing.close()

    def test_horizontal_dimension_and_export(self) -> None:
        drawing = Drawing(-50, -50, 400, 400)
        drawing.add_dimension(10, 20, 310, 20, offset=40)

        labels = [item.get_text() for item in drawing.ax.texts]
        self.assertIn("300 mm", labels)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "plan.svg"
            self.assertEqual(drawing.save(output), output)
            self.assertTrue(output.read_text().startswith("<?xml"))
        drawing.close()

    def test_ceiling_draws_objects_left_to_right(self) -> None:
        drawing = Drawing(0, 0, 2000, 2000)
        sections = drawing.add_ceiling(
            100,
            200,
            1000,
            [Beam(), Wide(), Beam(), Narrow()],
        )

        self.assertEqual(
            [(section.get_x(), section.get_width()) for section in sections],
            [(100, 125), (225, 500), (725, 125), (850, 375)],
        )
        self.assertEqual(
            [(section.get_y(), section.get_height()) for section in sections],
            [(200, 1000), (600, 200), (200, 1000), (600, 200)],
        )
        self.assertEqual(
            [section.get_facecolor() for section in sections],
            [
                to_rgba("#f4cccc"),
                to_rgba("#cfe2f3"),
                to_rgba("#f4cccc"),
                to_rgba("#d9ead3"),
            ],
        )
        self.assertTrue(all(section.get_hatch() is None for section in sections))
        drawing.close()

    def test_ceiling_object_offsets_can_be_overridden(self) -> None:
        drawing = Drawing(0, 0, 1000, 2000)
        sections = drawing.add_ceiling(
            0,
            100,
            1000,
            [
                Beam(top_offset=50, bottom_offset=-100),
                Wide(top_offset=0, bottom_offset=0),
            ],
        )

        self.assertEqual(
            [(section.get_y(), section.get_height()) for section in sections],
            [(150, 850), (100, 1000)],
        )
        drawing.close()

    def test_invisible_ceiling_object_leaves_space(self) -> None:
        drawing = Drawing(0, 0, 2000, 2000)
        sections = drawing.add_ceiling(
            100,
            200,
            1000,
            [Beam(), Wide(visible=False), Narrow()],
        )

        self.assertEqual(len(sections), 2)
        self.assertEqual(len(drawing.ax.patches), 2)
        self.assertEqual(
            [(section.get_x(), section.get_width()) for section in sections],
            [(100, 125), (725, 375)],
        )
        drawing.close()

    def test_ceiling_prints_each_beam_x_coordinate(self) -> None:
        drawing = Drawing(0, 0, 2000, 2000)
        output = StringIO()

        with redirect_stdout(output):
            drawing.add_ceiling(
                100,
                200,
                1000,
                [Beam(), Wide(), Beam(visible=False), Narrow(), Beam()],
            )

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Beam x-coordinate: 100 mm",
                "Beam x-coordinate: 725 mm",
                "Beam x-coordinate: 1225 mm",
            ],
        )
        drawing.close()

    def test_invisible_object_does_not_require_visible_vertical_space(self) -> None:
        drawing = Drawing(0, 0, 1000, 1000)
        sections = drawing.add_ceiling(
            0,
            0,
            100,
            [Wide(visible=False), Beam()],
        )

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].get_x(), 500)
        drawing.close()

    def test_ceiling_visible_must_be_boolean(self) -> None:
        drawing = Drawing(0, 0, 1000, 1000)

        with self.assertRaisesRegex(TypeError, "visible must be a bool"):
            drawing.add_ceiling(0, 0, 100, [Beam(visible=1)])

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_ceiling_rejects_offsets_that_invert_an_object(self) -> None:
        drawing = Drawing(0, 0, 1000, 1000)

        with self.assertRaisesRegex(ValueError, "top coordinate"):
            drawing.add_ceiling(0, 0, 600, [Beam(), Wide()])

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_ceiling_rejects_unknown_object_before_drawing(self) -> None:
        drawing = Drawing(0, 0, 1000, 1000)

        with self.assertRaisesRegex(TypeError, "must be Beam, Wide, or Narrow"):
            drawing.add_ceiling(0, 0, 100, [Beam(), object()])

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()

    def test_ceiling_rejects_out_of_bounds_row_before_drawing(self) -> None:
        drawing = Drawing(0, 0, 1000, 1000)

        with self.assertRaisesRegex(ValueError, "outside the drawing area"):
            drawing.add_ceiling(900, 0, 100, [Beam()])

        self.assertEqual(len(drawing.ax.patches), 0)
        drawing.close()


if __name__ == "__main__":
    unittest.main()
