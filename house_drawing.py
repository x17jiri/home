"""Small helpers for drawing dimensioned house plans with Matplotlib.

All coordinates and distances passed to this module are in millimetres.
The coordinate system follows the usual page convention: x increases to the
right and y increases downwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite
from os import PathLike
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse, Polygon, Rectangle


Number = int | float
Point = tuple[Number, Number]


@dataclass
class Beam:
    """A beam in a ceiling layout."""

    top_offset: Number = 0
    bottom_offset: Number = 0
    visible: bool = True


@dataclass
class Wide:
    """A wide ceiling section."""

    top_offset: Number = 400
    bottom_offset: Number = -400
    visible: bool = True


@dataclass
class Narrow:
    """A narrow ceiling section."""

    top_offset: Number = 400
    bottom_offset: Number = -400
    visible: bool = True


_CEILING_STYLES: dict[type[object], tuple[float, str]] = {
    Beam: (170.0, "#f4cccc"),
    Wide: (625.0-170.0, "#cfe2f3"),
    Narrow: (500.0-170.0, "#d9ead3"),
}


class Drawing:
    """A two-dimensional drawing whose coordinates are measured in mm.

    ``left``, ``top``, ``right`` and ``bottom`` describe the visible drawing
    area.  Since this is a page-like coordinate system, ``top`` must be less
    than ``bottom`` and increasing y coordinates move down the page.
    """

    def __init__(
        self,
        left: Number,
        top: Number,
        right: Number,
        bottom: Number,
        *,
        figsize: tuple[Number, Number] | None = None,
    ) -> None:
        self.left = self._number(left, "left")
        self.top = self._number(top, "top")
        self.right = self._number(right, "right")
        self.bottom = self._number(bottom, "bottom")

        if self.left >= self.right:
            raise ValueError("left must be less than right")
        if self.top >= self.bottom:
            raise ValueError("top must be less than bottom")

        if figsize is None:
            figsize = self._default_figsize()

        self.figure, self.axes = plt.subplots(figsize=figsize)
        self.axes.set_xlim(self.left, self.right)
        # Reversed limits make y increase downwards.
        self.axes.set_ylim(self.bottom, self.top)
        self.axes.set_aspect("equal", adjustable="box")
        self.axes.axis("off")
        # Use the whole canvas. This also makes exported margins predictable.
        self.axes.set_position((0, 0, 1, 1))

    @staticmethod
    def _number(value: Number, name: str) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be a number") from error
        if not isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    def _default_figsize(self) -> tuple[float, float]:
        """Choose a reasonably sized canvas while preserving its aspect."""
        width = self.right - self.left
        height = self.bottom - self.top
        longest_side = 12.0
        scale = longest_side / max(width, height)
        return width * scale, height * scale

    def _point(self, x: Number, y: Number, name: str = "point") -> tuple[float, float]:
        x = self._number(x, f"{name} x")
        y = self._number(y, f"{name} y")
        if not self.left <= x <= self.right or not self.top <= y <= self.bottom:
            raise ValueError(
                f"{name} ({x:g}, {y:g}) is outside the drawing area "
                f"[{self.left:g}, {self.top:g}] to "
                f"[{self.right:g}, {self.bottom:g}]"
            )
        return x, y

    def add_line(
        self,
        x1: Number,
        y1: Number,
        x2: Number,
        y2: Number,
        *,
        color: str = "black",
        linewidth: Number = 1.0,
        linestyle: str | tuple[Any, ...] = "solid",
        **kwargs: Any,
    ) -> Any:
        """Draw a line; ``linestyle`` may be solid, dashed, dotted, etc."""
        x1, y1 = self._point(x1, y1, "line start")
        x2, y2 = self._point(x2, y2, "line end")
        (line,) = self.axes.plot(
            [x1, x2],
            [y1, y2],
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
            **kwargs,
        )
        return line

    def add_box(
        self,
        x1: Number,
        y1: Number,
        x2: Number,
        y2: Number,
        *,
        facecolor: str = "white",
        edgecolor: str = "black",
        linewidth: Number = 1.0,
        linestyle: str | tuple[Any, ...] = "solid",
        hatch: str | None = None,
        **kwargs: Any,
    ) -> Rectangle:
        """Draw a rectangle given any two opposite corners."""
        x1, y1 = self._point(x1, y1, "box corner 1")
        x2, y2 = self._point(x2, y2, "box corner 2")
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        box = Rectangle(
            (left, top),
            right - left,
            bottom - top,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            linestyle=linestyle,
            hatch=hatch,
            **kwargs,
        )
        self.axes.add_patch(box)
        return box

    def add_polygon(
        self,
        points: Sequence[Point],
        *,
        facecolor: str = "white",
        edgecolor: str = "black",
        linewidth: Number = 1.0,
        linestyle: str | tuple[Any, ...] = "solid",
        hatch: str | None = None,
        **kwargs: Any,
    ) -> Polygon:
        """Draw a closed polygon through at least three points."""
        try:
            raw_points = list(points)
        except TypeError as error:
            raise TypeError("points must be a sequence of (x, y) points") from error

        if len(raw_points) < 3:
            raise ValueError("polygon must contain at least three points")

        polygon_points: list[tuple[float, float]] = []
        for index, point in enumerate(raw_points):
            try:
                point_x, point_y = point
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"polygon point {index} must contain exactly two coordinates"
                ) from error
            polygon_points.append(
                self._point(point_x, point_y, f"polygon point {index}")
            )

        polygon = Polygon(
            polygon_points,
            closed=True,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            linestyle=linestyle,
            hatch=hatch,
            **kwargs,
        )
        self.axes.add_patch(polygon)
        return polygon

    def add_ellipse(
        self,
        x1: Number,
        y1: Number,
        x2: Number,
        y2: Number,
        *,
        facecolor: str = "white",
        edgecolor: str = "black",
        linewidth: Number = 1.0,
        linestyle: str | tuple[Any, ...] = "solid",
        hatch: str | None = None,
        **kwargs: Any,
    ) -> Ellipse:
        """Draw an ellipse inscribed in the box between two opposite corners."""
        x1, y1 = self._point(x1, y1, "ellipse box corner 1")
        x2, y2 = self._point(x2, y2, "ellipse box corner 2")
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        ellipse = Ellipse(
            ((left + right) / 2, (top + bottom) / 2),
            right - left,
            bottom - top,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            linestyle=linestyle,
            hatch=hatch,
            **kwargs,
        )
        self.axes.add_patch(ellipse)
        return ellipse

    def add_wall(
        self,
        x1: Number,
        y1: Number,
        x2: Number,
        y2: Number,
        *,
        facecolor: str = "white",
        edgecolor: str = "black",
        linewidth: Number = 1,
        hatch: str | None = "///",
        **kwargs: Any,
    ) -> Rectangle:
        """Draw a patterned rectangular wall between two opposite corners.

        For example, ``add_wall(10, 10, 30, 200)`` makes a 20 mm wide,
        190 mm long wall. Reversing either pair of coordinates is allowed.
        """
        return self.add_box(
            x1,
            y1,
            x2,
            y2,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            hatch=hatch,
            **kwargs,
        )

    def add_brick_wall(
        self,
        polygon: Sequence[Point],
        *,
        brick_width: Number = 250,
        brick_height: Number = 250,
        start_x: Number | None = None,
        start_y: Number | None = None,
        facecolor: str = "white",
        edgecolor: str = "#7f5539",
        linewidth: Number = 0.6,
        outline_color: str = "#303030",
        outline_width: Number = 1.2,
        half_rows: Iterable[int] | None = None,
    ) -> list[Rectangle]:
        """Draw a staggered brick grid clipped to ``polygon``.

        The pattern anchor is the bottom-left corner of row 0, which extends
        upward from ``start_y``. Row 1 is above row 0, while row -1 is directly
        below it. Rows listed in ``half_rows`` use half of ``brick_height``;
        their indexes still alternate the horizontal half-brick shift.

        If a starting coordinate is omitted, the corresponding coordinate of
        the polygon's first point is used.
        """
        brick_width = self._number(brick_width, "brick_width")
        brick_height = self._number(brick_height, "brick_height")
        linewidth = self._number(linewidth, "linewidth")
        outline_width = self._number(outline_width, "outline_width")

        if brick_width <= 0:
            raise ValueError("brick_width must be greater than zero")
        if brick_height <= 0:
            raise ValueError("brick_height must be greater than zero")
        if linewidth < 0:
            raise ValueError("linewidth cannot be negative")
        if outline_width < 0:
            raise ValueError("outline_width cannot be negative")

        try:
            raw_points = list(polygon)
        except TypeError as error:
            raise TypeError("polygon must be a sequence of (x, y) points") from error

        points: list[tuple[float, float]] = []
        for index, point in enumerate(raw_points):
            try:
                point_x, point_y = point
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"polygon point {index} must contain exactly two coordinates"
                ) from error
            points.append(
                (
                    self._number(point_x, f"polygon point {index} x"),
                    self._number(point_y, f"polygon point {index} y"),
                )
            )

        if len(points) < 3:
            raise ValueError("polygon must contain at least three points")

        if start_x is None:
            start_x = points[0][0]
        else:
            start_x = self._number(start_x, "start_x")
        if start_y is None:
            start_y = points[0][1]
        else:
            start_y = self._number(start_y, "start_y")

        if half_rows is None:
            half_row_indexes: set[int] = set()
        else:
            try:
                requested_half_rows = list(half_rows)
            except TypeError as error:
                raise TypeError("half_rows must be an iterable of integer row indexes") from error
            for index in requested_half_rows:
                if isinstance(index, bool) or not isinstance(index, int):
                    raise TypeError("half_rows must contain only integer row indexes")
            half_row_indexes = set(requested_half_rows)

        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        if min_x == max_x or min_y == max_y:
            raise ValueError("polygon must have a non-zero width and height")

        def row_height(row_index: int) -> float:
            if row_index in half_row_indexes:
                return brick_height / 2
            return brick_height

        # Build rows independently in each direction from the anchor because
        # half-height rows change the positions of every subsequent row.
        rows: list[tuple[int, float, float]] = []

        row_index = 0
        row_bottom = start_y
        while row_bottom > min_y:
            height = row_height(row_index)
            row_top = row_bottom - height
            if row_top < max_y:
                rows.append((row_index, row_top, height))
            row_bottom = row_top
            row_index += 1

        row_index = -1
        row_top = start_y
        while row_top < max_y:
            height = row_height(row_index)
            row_bottom = row_top + height
            if row_bottom > min_y:
                rows.append((row_index, row_top, height))
            row_top = row_bottom
            row_index -= 1

        clip_polygon = Polygon(
            points,
            closed=True,
            transform=self.ax.transData,
        )

        bricks: list[Rectangle] = []
        for row_index, brick_y, height in rows:
            row_x = start_x + (brick_width / 2 if row_index % 2 else 0)
            first_column = floor((min_x - row_x) / brick_width)
            last_column = ceil((max_x - row_x) / brick_width)

            for column in range(first_column, last_column):
                brick_x = row_x + column * brick_width
                brick = Rectangle(
                    (brick_x, brick_y),
                    brick_width,
                    height,
                    facecolor=facecolor,
                    edgecolor=edgecolor,
                    linewidth=linewidth,
                )
                brick.set_clip_path(clip_polygon)
                self.ax.add_patch(brick)
                bricks.append(brick)

        # Keep the wall boundary visible over clipped brick edges.
        self.ax.add_patch(
            Polygon(
                points,
                closed=True,
                facecolor="none",
                edgecolor=outline_color,
                linewidth=outline_width,
            )
        )
        return bricks

    def add_ceiling(
        self,
        x: Number,
        y: Number,
        height: Number,
        objects: list[Beam | Wide | Narrow],
    ) -> list[Rectangle]:
        """Draw a row of ceiling objects from left to right.

        Beams are 125 mm wide, wide sections are 500 mm wide, and narrow
        sections are 375 mm wide. Each object's offsets are added to its top
        and bottom coordinates. All sections use solid fills. The x-coordinate
        of every beam is printed in millimetres.
        """
        x, y = self._point(x, y, "ceiling start")
        height = self._number(height, "height")
        if height <= 0:
            raise ValueError("height must be greater than zero")

        try:
            ceiling_objects = list(objects)
        except TypeError as error:
            raise TypeError("objects must be an iterable of Beam, Wide, or Narrow") from error

        specifications: list[tuple[float, str, float | None, float | None, bool]] = []
        beam_x_coordinates: list[float] = []
        current_x = x
        for index, ceiling_object in enumerate(ceiling_objects):
            try:
                width, color = _CEILING_STYLES[type(ceiling_object)]
            except KeyError as error:
                raise TypeError(
                    f"ceiling object at index {index} must be Beam, Wide, or Narrow; "
                    f"got {type(ceiling_object).__name__}"
                ) from error

            if not isinstance(ceiling_object.visible, bool):
                raise TypeError(f"ceiling object at index {index} visible must be a bool")

            if isinstance(ceiling_object, Beam):
                beam_x_coordinates.append(current_x)

            if not ceiling_object.visible:
                # A hidden object still consumes its full horizontal width.
                self._point(
                    current_x + width,
                    y,
                    f"ceiling object at index {index} space end",
                )
                specifications.append((width, color, None, None, False))
                current_x += width
                continue

            top_offset = self._number(
                ceiling_object.top_offset,
                f"ceiling object at index {index} top_offset",
            )
            bottom_offset = self._number(
                ceiling_object.bottom_offset,
                f"ceiling object at index {index} bottom_offset",
            )
            object_top = y + top_offset
            object_bottom = y + height + bottom_offset
            if object_top >= object_bottom:
                raise ValueError(
                    f"ceiling object at index {index} has top coordinate "
                    f"{object_top:g}, which must be less than its bottom "
                    f"coordinate {object_bottom:g}"
                )

            # Validate every rectangle before adding any patches, so invalid
            # input cannot leave a partially drawn ceiling.
            self._point(current_x, object_top, f"ceiling object at index {index} top-left")
            self._point(
                current_x + width,
                object_bottom,
                f"ceiling object at index {index} bottom-right",
            )
            specifications.append((width, color, object_top, object_bottom, True))
            current_x += width

        if not specifications:
            self._point(x, y + height, "ceiling end")

        for beam_x_coordinate in beam_x_coordinates:
            print(f"Beam x-coordinate: {beam_x_coordinate:g} mm")

        sections: list[Rectangle] = []
        current_x = x
        for width, color, object_top, object_bottom, visible in specifications:
            if visible:
                # Visible entries always have validated numeric coordinates.
                assert object_top is not None and object_bottom is not None
                sections.append(
                    self.add_box(
                        current_x,
                        object_top,
                        current_x + width,
                        object_bottom,
                        facecolor=color,
                        edgecolor="#666666",
                        linewidth=0.8,
                        hatch=None,
                    )
                )
            current_x += width
        return sections

    def add_text(
        self,
        x: Number,
        y: Number,
        text: str,
        *,
        size: Number = 10,
        horizontal_alignment: str = "center",
        vertical_alignment: str = "center",
        **kwargs: Any,
    ) -> Any:
        """Add text at a position measured in mm."""
        x, y = self._point(x, y, "text position")
        return self.axes.text(
            x,
            y,
            text,
            fontsize=size,
            ha=horizontal_alignment,
            va=vertical_alignment,
            **kwargs,
        )

    def add_dimension(
        self,
        x1: Number,
        y1: Number,
        x2: Number,
        y2: Number,
        *,
        offset: Number = 0,
        text: str | None = None,
        decimals: int = 0,
        color: str = "black",
        linewidth: Number = 0.8,
        tick_size: Number = 8,
        text_size: Number = 9,
    ) -> None:
        """Add a horizontal or vertical dimension between two points.

        A positive offset places a horizontal dimension lower on the page or a
        vertical dimension farther to the right. The automatically generated
        label is the distance in millimetres.
        """
        x1, y1 = self._point(x1, y1, "dimension start")
        x2, y2 = self._point(x2, y2, "dimension end")
        offset = self._number(offset, "offset")
        tick_size = self._number(tick_size, "tick_size")

        if y1 == y2 and x1 != x2:
            dimension_y = y1 + offset
            self._point(x1, dimension_y, "dimension line start")
            self._point(x2, dimension_y, "dimension line end")
            self.add_line(x1, y1, x1, dimension_y, color=color, linewidth=linewidth)
            self.add_line(x2, y2, x2, dimension_y, color=color, linewidth=linewidth)
            self.add_line(x1, dimension_y, x2, dimension_y, color=color, linewidth=linewidth)
            self.add_line(
                x1, dimension_y - tick_size / 2, x1, dimension_y + tick_size / 2,
                color=color, linewidth=linewidth,
            )
            self.add_line(
                x2, dimension_y - tick_size / 2, x2, dimension_y + tick_size / 2,
                color=color, linewidth=linewidth,
            )
            label = text if text is not None else f"{abs(x2 - x1):.{decimals}f} mm"
            self.add_text(
                (x1 + x2) / 2,
                dimension_y,
                label,
                size=text_size,
                color=color,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
            )
            return

        if x1 == x2 and y1 != y2:
            dimension_x = x1 + offset
            self._point(dimension_x, y1, "dimension line start")
            self._point(dimension_x, y2, "dimension line end")
            self.add_line(x1, y1, dimension_x, y1, color=color, linewidth=linewidth)
            self.add_line(x2, y2, dimension_x, y2, color=color, linewidth=linewidth)
            self.add_line(dimension_x, y1, dimension_x, y2, color=color, linewidth=linewidth)
            self.add_line(
                dimension_x - tick_size / 2, y1, dimension_x + tick_size / 2, y1,
                color=color, linewidth=linewidth,
            )
            self.add_line(
                dimension_x - tick_size / 2, y2, dimension_x + tick_size / 2, y2,
                color=color, linewidth=linewidth,
            )
            label = text if text is not None else f"{abs(y2 - y1):.{decimals}f} mm"
            self.add_text(
                dimension_x,
                (y1 + y2) / 2,
                label,
                size=text_size,
                color=color,
                rotation=90,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
            )
            return

        raise ValueError("dimension points must form a non-zero horizontal or vertical line")

    def save(
        self,
        filename: str | PathLike[str],
        *,
        dpi: Number = 150,
        transparent: bool = False,
        **kwargs: Any,
    ) -> Path:
        """Save the drawing; the filename extension selects SVG, PDF, PNG, etc."""
        path = Path(filename)
        self.figure.savefig(path, dpi=dpi, transparent=transparent, **kwargs)
        return path

    def show(self) -> None:
        """Open Matplotlib's interactive drawing window."""
        plt.show()

    def close(self) -> None:
        """Release the Matplotlib figure when the drawing is no longer needed."""
        plt.close(self.figure)

    @property
    def fig(self) -> Figure:
        """Expose the Matplotlib figure for advanced customisation."""
        return self.figure

    @property
    def ax(self) -> Axes:
        """Expose the Matplotlib axes for advanced customisation."""
        return self.axes
