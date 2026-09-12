"""Draw the initial shadow geometry and save it as a PNG."""

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.axes import Axes


X_MIN, X_MAX = -20, 3
Y_MIN, Y_MAX = -3, 20
DX_PER_DY = 0.119
DISTANCE_ALONG_LINE = 7.75
SECOND_LINE_ANGLE = 70
CENTER_HEIGHT = 8.25
SLOPE = 0.7359
WINDOW_HEIGHT = 1.5 + 0.75

# Move the entire polygon by changing only this point.
POLYGON_ORIGIN = (-3.45, 4.5+8.5/2)

# Polygon vertices are measured from POLYGON_ORIGIN, in metres.
POLYGON_POINTS: tuple[tuple[float, float], ...] = (
    (-12, -9.5/2),
	(-2, -9.5/2),
	(-2, -9.5/2 + 2),
	(0, -9.5/2 + 2),
	(0, +9.5/2),
	(-12, +9.5/2)
)

OUTPUT_FILE = Path(__file__).with_name("shadow.png")


def absolute_polygon_points(
    origin: tuple[float, float],
    points: tuple[tuple[float, float], ...],
) -> list[tuple[float, float]]:
    """Translate polygon points from local to drawing coordinates."""
    origin_x, origin_y = origin
    return [
        (origin_x + relative_x, origin_y + relative_y)
        for relative_x, relative_y in points
    ]


def draw_relative_polygon(
    ax: Axes,
    origin: tuple[float, float],
    points: tuple[tuple[float, float], ...],
) -> None:
    """Draw a polygon whose vertices are offsets from a movable origin."""
    if not points:
        return
    if len(points) < 3:
        raise ValueError("A polygon needs at least three points")

    polygon = plt.Polygon(
        absolute_polygon_points(origin, points),
        closed=True,
        facecolor="#bcd7f0",
        edgecolor="black",
        linewidth=2,
        alpha=0.75,
    )
    ax.add_patch(polygon)


def cross_product(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    return first[0] * second[1] - first[1] * second[0]


def polygon_intersection_on_ray(
    ray_origin: tuple[float, float],
    ray_direction: tuple[float, float],
    polygon_points: list[tuple[float, float]],
) -> tuple[float, tuple[float, float]] | None:
    """Return the nearest forward ray/polygon intersection."""
    intersections: list[tuple[float, tuple[float, float]]] = []
    for segment_start, segment_end in zip(
        polygon_points,
        polygon_points[1:] + polygon_points[:1],
    ):
        segment = (
            segment_end[0] - segment_start[0],
            segment_end[1] - segment_start[1],
        )
        denominator = cross_product(ray_direction, segment)
        if math.isclose(denominator, 0.0, abs_tol=1e-12):
            continue

        origin_to_segment = (
            segment_start[0] - ray_origin[0],
            segment_start[1] - ray_origin[1],
        )
        ray_distance = cross_product(origin_to_segment, segment) / denominator
        segment_fraction = (
            cross_product(origin_to_segment, ray_direction) / denominator
        )
        if ray_distance >= 0 and 0 <= segment_fraction <= 1:
            intersection = (
                ray_origin[0] + ray_distance * ray_direction[0],
                ray_origin[1] + ray_distance * ray_direction[1],
            )
            intersections.append((ray_distance, intersection))

    return min(intersections, key=lambda item: item[0]) if intersections else None


def main() -> None:
    fig, ax = plt.subplots(figsize=(9, 9))

    # The line rises from the origin, moving 0.11 m right for every 1 m up.
    line_y = [0, Y_MAX]
    line_x = [DX_PER_DY * y for y in line_y]
    ax.plot(line_x, line_y, color="black", linewidth=2)

    # Locate the configured point along the first line.
    first_length = math.hypot(DX_PER_DY, 1)
    first_angle = math.atan2(1, DX_PER_DY)
    branch_x = DISTANCE_ALONG_LINE * DX_PER_DY / first_length
    branch_y = DISTANCE_ALONG_LINE / first_length

    # Turning 70 degrees counterclockwise produces an up-and-left line.
    second_angle = first_angle + math.radians(SECOND_LINE_ANGLE)
    second_dx = math.cos(second_angle)
    second_dy = math.sin(second_angle)
    distance_to_left_edge = (X_MIN - branch_x) / second_dx
    second_x = branch_x + distance_to_left_edge * second_dx
    second_y = branch_y + distance_to_left_edge * second_dy
    ax.plot(
        [branch_x, second_x],
        [branch_y, second_y],
        color="black",
        linewidth=2,
    )

    # The opposite end of a 70-degree clockwise line goes down and left.
    third_angle = first_angle - math.radians(SECOND_LINE_ANGLE) + math.pi
    third_dx = math.cos(third_angle)
    third_dy = math.sin(third_angle)
    third_distance_to_left_edge = (X_MIN - branch_x) / third_dx
    third_x = branch_x + third_distance_to_left_edge * third_dx
    third_y = branch_y + third_distance_to_left_edge * third_dy
    ax.plot(
        [branch_x, third_x],
        [branch_y, third_y],
        color="black",
        linewidth=2,
    )

    # Rotate 90 degrees counterclockwise for the left-pointing perpendicular.
    perpendicular_angle = first_angle + math.pi / 2
    perpendicular_dx = math.cos(perpendicular_angle)
    perpendicular_dy = math.sin(perpendicular_angle)
    perpendicular_distance_to_left_edge = (
        X_MIN - branch_x
    ) / perpendicular_dx
    perpendicular_x = (
        branch_x + perpendicular_distance_to_left_edge * perpendicular_dx
    )
    perpendicular_y = (
        branch_y + perpendicular_distance_to_left_edge * perpendicular_dy
    )
    ax.plot(
        [branch_x, perpendicular_x],
        [branch_y, perpendicular_y],
        color="black",
        linewidth=2,
    )

    polygon_points = absolute_polygon_points(POLYGON_ORIGIN, POLYGON_POINTS)
    perpendicular_intersection = polygon_intersection_on_ray(
        (branch_x, branch_y),
        (perpendicular_dx, perpendicular_dy),
        polygon_points,
    )
    if perpendicular_intersection is None:
        print("The perpendicular line does not intersect the polygon.")
    else:
        perpendicular_distance, _ = perpendicular_intersection
        print(f"Perpendicular distance to polygon: {perpendicular_distance:.3f} m")

    # Angle 0 points down along the original slope. Increasing the angle turns
    # clockwise toward the polygon, one tenth of a degree at a time.
    downward_angle = first_angle + math.pi
    final_result: tuple[
        float,
        float,
        tuple[float, float],
        float,
    ] | None = None
    for angle_tenths in range(1801):
        angle_degrees = angle_tenths / 10
        test_angle = downward_angle - math.radians(angle_degrees)
        test_direction = (math.cos(test_angle), math.sin(test_angle))
        intersection_result = polygon_intersection_on_ray(
            (branch_x, branch_y),
            test_direction,
            polygon_points,
        )
        if intersection_result is None:
            continue

        intersection_distance, intersection_point = intersection_result
        local_y = intersection_point[1] - POLYGON_ORIGIN[1]
        polygon_height = CENTER_HEIGHT - SLOPE * abs(local_y)
        if polygon_height > WINDOW_HEIGHT + intersection_distance:
            final_result = (
                angle_degrees,
                intersection_distance,
                intersection_point,
                polygon_height,
            )
            break

    if final_result is None:
        print("No angle from 0 to 180 degrees satisfies the height condition.")
    else:
        (
            final_angle,
            final_distance,
            final_intersection,
            final_polygon_height,
        ) = final_result
        ax.plot(
            [branch_x, final_intersection[0]],
            [branch_y, final_intersection[1]],
            color="red",
            linewidth=3,
            zorder=4,
        )
        print(f"Final angle: {final_angle:.1f} degrees")
        print(f"Final intersection distance: {final_distance:.3f} m")
        print(f"Polygon height at intersection: {final_polygon_height:.3f} m")

    draw_relative_polygon(ax, POLYGON_ORIGIN, POLYGON_POINTS)

    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(Y_MIN, Y_MAX)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_xticks(range(X_MIN, X_MAX + 1))
    ax.set_yticks(range(Y_MIN, Y_MAX + 1))
    ax.grid(True, color="#d9d9d9", linewidth=0.6)

    # Make the coordinate axes easy to distinguish from the grid.
    ax.axhline(0, color="#666666", linewidth=1)
    ax.axvline(0, color="#666666", linewidth=1)

    fig.tight_layout()
    fig.savefig(OUTPUT_FILE, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
