"""Read Czech S-JTSK/Bpv survey lists and draw a measured plan of the points.

Input order is point number, Y (westing), X (southing), Z (Bpv), optional note.
Blank lines separate groups; an optional #color header connects a group's
points in file order. Add ", closed" to connect the last point to the first.
Name a polyline with e.g. #0000ff: street. The street's best-fit line becomes
the drawing's x axis (orthogonal least squares); distances remain in metres.
Point IDs may repeat in groups when their coordinates match. Notes are descriptive only.
Without street, local axes are east = Y0-Y and grid north = X0-X. No house
placement is inferred; the original coordinates remain available.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from html import escape
import json
from math import atan, atan2, copysign, cos, degrees, floor, hypot, isfinite, pi, radians, sin, sqrt, tan
import os
from pathlib import Path
import re
from tempfile import gettempdir


@dataclass(frozen=True)
class SurveyPoint:
    number: str
    y: float
    x: float
    z: float
    note: str = ""


@dataclass(frozen=True)
class SurveyGroup:
    color: str | None
    points: tuple[SurveyPoint, ...]
    closed: bool = False
    name: str | None = None


@dataclass(frozen=True)
class SurveyFrame:
    """Rigid plan transform; x-axis angle is measured from grid east toward north."""

    origin_y: float
    origin_x: float
    rotation_radians: float = 0.0

    def to_local(self, y: float, x: float) -> tuple[float, float]:
        east, north = self.origin_y-y, self.origin_x-x
        c, s = cos(self.rotation_radians), sin(self.rotation_radians)
        return c*east+s*north, -s*east+c*north

    def to_survey(self, local_x: float, local_y: float) -> tuple[float, float]:
        c, s = cos(self.rotation_radians), sin(self.rotation_radians)
        return self.origin_y-(c*local_x-s*local_y), self.origin_x-(s*local_x+c*local_y)

    @classmethod
    def for_polyline(cls, group: SurveyGroup):
        """Fit a line minimizing squared perpendicular distances to unique points.

        Its centroid is the origin, so the fitted line is exactly local y=0.
        Choose the direction toward grid east (north for a vertical line),
        independent of the order of the polyline's vertices.
        """
        points = _unique_points((group,))
        if len(points) < 2:
            raise ValueError(f"polyline {group.name!r} needs at least two distinct plan positions to fit a line")
        base_y, base_x = points[0].y, points[0].x
        origin_y = base_y+sum(p.y-base_y for p in points)/len(points)
        origin_x = base_x+sum(p.x-base_x for p in points)/len(points)
        centered = [(origin_y-p.y, origin_x-p.x) for p in points]
        ee = sum(e*e for e, n in centered)
        nn = sum(n*n for e, n in centered)
        en = sum(e*n for e, n in centered)
        if ee+nn == 0:
            raise ValueError(f"polyline {group.name!r} needs at least two distinct plan positions to fit a line")
        if hypot(ee-nn, 2*en) <= 1e-12*(ee+nn):
            raise ValueError(f"polyline {group.name!r} has no unique best-fit line")
        return cls(origin_y, origin_x, .5*atan2(2*en, ee-nn))

    @classmethod
    def for_points(cls, points):
        if not points:
            raise ValueError("survey must contain points")
        return cls(*(floor((min(values)+max(values))/200+.5)*100.0
                     for values in ([p.y for p in points], [p.x for p in points])))


@dataclass(frozen=True)
class SurveyAxes:
    """Oblique metre coordinates: street points right, neighbour points upward.

    The frame is Cartesian for drawing; only placement coordinates use the
    oblique basis. Its origin is the intersection of the two fitted lines.
    """

    frame: SurveyFrame
    neighbour_direction: tuple[float, float]

    @classmethod
    def from_polylines(cls, street: SurveyGroup, neighbour: SurveyGroup):
        street_fit = SurveyFrame.for_polyline(street)
        frame = replace(street_fit, rotation_radians=street_fit.rotation_radians-pi)
        neighbour_fit = SurveyFrame.for_polyline(neighbour)
        angle = neighbour_fit.rotation_radians-frame.rotation_radians
        nx, ny = cos(angle), sin(angle)
        if abs(ny) < 1e-10:
            raise ValueError("street and neighbour fitted lines are parallel; no unique intersection")
        if ny < 0:
            nx, ny = -nx, -ny
        x, y = frame.to_local(neighbour_fit.origin_y, neighbour_fit.origin_x)
        origin_y, origin_x = frame.to_survey(x-y*nx/ny, 0)
        return cls(replace(frame, origin_y=origin_y, origin_x=origin_x), (nx, ny))

    def to_local(self, x: float, y: float) -> tuple[float, float]:
        """Travel x metres along street plus y metres along neighbour."""
        nx, ny = self.neighbour_direction
        return x+y*nx, y*ny

    def from_local(self, x: float, y: float) -> tuple[float, float]:
        nx, ny = self.neighbour_direction
        along_neighbour = y/ny
        return x-along_neighbour*nx, along_neighbour


@dataclass(frozen=True)
class SurveyHouse:
    center: tuple[float, float] = (-8.0, 7.0)
    angle_degrees: float = 0.0
    width: float = 11.5
    depth: float = 8.4

    def __post_init__(self):
        if len(self.center) != 2 or not all(isfinite(v) for v in (*self.center, self.angle_degrees, self.width, self.depth)):
            raise ValueError("house center, rotation and dimensions must be finite")
        if self.width <= 0 or self.depth <= 0:
            raise ValueError("house dimensions must be positive")

    def corners(self, axes: SurveyAxes) -> tuple[tuple[float, float], ...]:
        """Rigid rectangle, rotated about its obliquely positioned center."""
        cx, cy = axes.to_local(*self.center)
        c, s = cos(radians(self.angle_degrees)), sin(radians(self.angle_degrees))
        return tuple((cx+c*x-s*y, cy+s*x+c*y)
                     for x, y in ((-self.width/2, -self.depth/2), (self.width/2, -self.depth/2),
                                  (self.width/2, self.depth/2), (-self.width/2, self.depth/2)))

    def line_distances(self, axes: SurveyAxes) -> dict[str, float]:
        """Shortest perpendicular distances to the infinite fitted lines, in metres.

        If corner projections span zero, the line crosses or touches the
        rectangle and the distance is zero. Otherwise the nearest corner
        gives the distance (including an entire parallel edge when tied).
        """
        corners = self.corners(axes)
        nx, ny = axes.neighbour_direction
        distances = {}
        for name, normal in (("street", (0.0, 1.0)), ("neighbour", (-ny, nx))):
            projections = [x*normal[0]+y*normal[1] for x, y in corners]
            distances[name] = (0.0 if min(projections) <= 0 <= max(projections)
                               else min(abs(value) for value in projections))
        return distances


@dataclass(frozen=True)
class RoofSlope:
    """Infinite two-sided roof profile, descending along start/end's direction.

    Points use oblique street/neighbour coordinates. Elevation is metres Bpv
    at their midpoint; the slope angle is measured above the horizontal.
    Height is constant perpendicular to the start/end direction.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    elevation: float
    angle_degrees: float

    def __post_init__(self):
        if (len(self.start) != 2 or len(self.end) != 2
                or not all(isfinite(v) for v in (*self.start, *self.end, self.elevation, self.angle_degrees))):
            raise ValueError("roof points, midpoint elevation and angle must be finite")
        if self.start == self.end:
            raise ValueError("roof slope requires two distinct points")
        if not 0 <= self.angle_degrees < 90:
            raise ValueError("roof slope angle must be at least 0 and less than 90 degrees")

    def geometry(self, axes: SurveyAxes):
        """Cartesian midpoint, unit downhill direction, and half drawing length."""
        a, b = axes.to_local(*self.start), axes.to_local(*self.end)
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = hypot(dx, dy)
        if length == 0:
            raise ValueError("roof slope requires two distinct plan positions")
        return ((a[0]+b[0])/2, (a[1]+b[1])/2), (dx/length, dy/length), length/2

    @classmethod
    def from_house_right_edge(cls, house: SurveyHouse, axes: SurveyAxes, *,
                             total_house_height: float, main_roof_angle: float,
                             ground_elevation: float = 417.0):
        corners = house.corners(axes)
        return cls(start=axes.from_local(*corners[1]), end=axes.from_local(*corners[2]),
                   elevation=ground_elevation+total_house_height, angle_degrees=main_roof_angle)

    def elevation_at(self, point: tuple[float, float], axes: SurveyAxes) -> float:
        """Height at any oblique plan position, including beyond both endpoints."""
        midpoint, direction, _ = self.geometry(axes)
        x, y = axes.to_local(*point)
        distance = (x-midpoint[0])*direction[0]+(y-midpoint[1])*direction[1]
        return self.elevation-abs(distance)*tan(radians(self.angle_degrees))

    def parallel_offset(self, axes: SurveyAxes, distance: float):
        """Move perpendicular to start→end, positive to its left, in plan metres."""
        if not isfinite(distance):
            raise ValueError("roof profile offset must be finite")
        _, (dx, dy), _ = self.geometry(axes)
        def shifted(point):
            x, y = axes.to_local(*point)
            return axes.from_local(x-distance*dy, y+distance*dx)
        return replace(self, start=shifted(self.start), end=shifted(self.end))

    def drawing_endpoints(self, axes: SurveyAxes, overhang: float = 2.0):
        """Finite preview only; overhang does not affect elevation_at()."""
        if not isfinite(overhang) or overhang < 0:
            raise ValueError("roof drawing overhang must be finite and nonnegative")
        midpoint, direction, half_length = self.geometry(axes)
        return tuple((midpoint[0]+sign*(half_length+overhang)*direction[0],
                      midpoint[1]+sign*(half_length+overhang)*direction[1]) for sign in (-1, 1))


# Tune these for both the standalone command and `house_ifc.py points`.
# Center coordinates are metres along street/neighbour; rotation is CCW from street.
HOUSE_PLACEMENT = SurveyHouse(center=(-9.900, 10.700), angle_degrees=-6.5)
NEIGHBOUR_WINDOW_DISTANCE = 7.75  # Metres from the fitted intersection along +y.
NEIGHBOUR_WINDOW_ELEVATION = 417.60  # Metres above sea level (Bpv).
ROOF_SLOPES: tuple[RoofSlope, ...] = (
    # RoofSlope(start=(-10.0, 5.0), end=(-10.0, 14.0), elevation=423.0, angle_degrees=35.0),
)
ROOF_SLOPE_OVERHANG = 2.0  # Extra metres at each end of the drawn preview only.
HOUSE_ROOF_ENABLED = True
HOUSE_ROOF_GROUND_ELEVATION = 417.0  # Explicit survey placement datum, metres Bpv.
HOUSE_ROOF_EDGE_DROP = 0.875
HOUSE_ROOF_PROFILE_SPACING = 2.25  # Perpendicular plan distance, away from neighbour.


def house_roof_profiles(house: SurveyHouse, axes: SurveyAxes, *, total_house_height: float,
                        main_roof_angle: float, ground_elevation: float = 417.0,
                        edge_drop: float = 0.875, spacing: float = 2.25) -> tuple[RoofSlope, RoofSlope]:
    """Lower edge profile and original-height parallel profile away from neighbour."""
    if not all(isfinite(v) and v >= 0 for v in (edge_drop, spacing)):
        raise ValueError("roof edge drop and profile spacing must be finite and nonnegative")
    original = RoofSlope.from_house_right_edge(
        house, axes, total_house_height=total_house_height, main_roof_angle=main_roof_angle,
        ground_elevation=ground_elevation)
    (mx, my), (dx, dy), _ = original.geometry(axes)
    nx, ny = axes.neighbour_direction
    # Choose the perpendicular direction that moves the midpoint farther
    # from neighbour, regardless of the house's rotation or side of the line.
    signed_gap = -ny*mx+nx*my
    gap_change = ny*dy+nx*dx  # Neighbour normal dotted with the profile's left normal.
    side = 1 if signed_gap*gap_change >= 0 else -1
    return (replace(original, elevation=original.elevation-edge_drop),
            original.parallel_offset(axes, side*spacing))


def read_house_roof_metrics(source: str | Path) -> tuple[float, float]:
    """Read current roof geometry without executing IFC construction or the solver.

    Use the existing restricted arithmetic reader and normal-offset plane
    geometry. The house's exterior ridge pairs are its two main roof planes.
    Height is measured from the ground-storey finished floor to top of tiles,
    matching total_house_height; the separate ridge cap is excluded there too.
    """
    from roof_frame_3d import HouseInputs, RoofPlane

    data = HouseInputs(source)
    planes = [RoofPlane.from_points(data.get(name))
              for name in ("STREET_ROOF_PLANE_POINTS", "GARDEN_ROOF_PLANE_POINTS")]
    offset = data.get("ROOF_TILE_BOTTOM")+data.get("ROOF_TILE_THICKNESS")
    height = max(plane.z(data.get("HALF_DEPTH"), offset) for plane in planes)-data.get("GROUND_FLOOR_THICKNESS")
    return height, degrees(atan(abs(planes[0].slope)))


def neighbour_window_point(axes: SurveyAxes) -> SurveyPoint:
    """A derived reference point; it never participates in the surveyed line fit."""
    y, x = axes.frame.to_survey(*axes.to_local(0, NEIGHBOUR_WINDOW_DISTANCE))
    return SurveyPoint("neighbour-window", y, x, NEIGHBOUR_WINDOW_ELEVATION, "neighbour window")


@dataclass(frozen=True)
class RoofSightHit:
    clockwise_degrees: float
    roof_index: int  # One-based, matching the printed roof slope numbers.
    point: tuple[float, float]  # Oblique street/neighbour coordinates.
    elevation: float
    plan_distance: float
    elevation_difference: float
    vertical_angle_degrees: float


def _quadratic_roots(a, b, c):
    """Real roots, retaining tangencies and the linear case (45-degree roof)."""
    if abs(a) <= 1e-14:
        return (-c/b,) if abs(b) > 1e-14 else ()
    discriminant = b*b-4*a*c
    tolerance = 1e-12*max(b*b, abs(4*a*c), 1.0)
    if discriminant < -tolerance:
        return ()
    q = -.5*(b+copysign(sqrt(max(0.0, discriminant)), b))
    return (q/a, c/q) if q != 0 else (-b/(2*a),)


def first_roof_45_degree_hit(roof_slopes, axes: SurveyAxes, observer: SurveyPoint) -> RoofSightHit | None:
    """First clockwise ray from observer→origin that reaches a roof at >=45°.

    A profile point is M+s*u, at height H-k*abs(s). Qualifying points satisfy
    |M+s*u-W| <= H-k*abs(s)-window_height. Squaring on each signed half gives
    a quadratic. Its admissible roots bound the visible angular interval;
    also check the starting ray and the peak. No angular sampling, endpoints
    or drawing overhang are involved. All distances are Cartesian metres.
    """
    wx, wy = axes.frame.to_local(observer.y, observer.x)
    origin_distance = hypot(wx, wy)
    if origin_distance <= 1e-10:
        raise ValueError("cannot orient toward origin when observer is at the origin")
    start_direction = (-wx/origin_distance, -wy/origin_distance)
    start_angle = atan2(start_direction[1], start_direction[0])
    hits = []
    for index, roof in enumerate(roof_slopes, 1):
        (mx, my), (ux, uy), _ = roof.geometry(axes)
        dx, dy = mx-wx, my-wy
        rise = roof.elevation-observer.z
        if rise < 0:
            continue
        k = tan(radians(roof.angle_degrees))
        along = dx*ux+dy*uy
        candidates = [0.0]  # Peak, including a hit that exists only at the peak.
        for side in (-1, 1):
            for s in _quadratic_roots(1-k*k, 2*(along+side*rise*k), dx*dx+dy*dy-rise*rise):
                if side*s >= -1e-9 and rise-k*abs(s) >= -1e-9:
                    candidates.append(s)
        # An interval may already cover the initial bearing, even when neither
        # boundary nor the peak is on that bearing.
        rx, ry = start_direction
        denominator = rx*uy-ry*ux
        if abs(denominator) > 1e-12:
            ray_distance = (dx*uy-dy*ux)/denominator
            if ray_distance >= 0:
                candidates.append((dx*ry-dy*rx)/denominator)
        for s in candidates:
            px, py = mx+s*ux, my+s*uy
            vx, vy = px-wx, py-wy
            distance = hypot(vx, vy)
            difference = rise-k*abs(s)
            if difference < -1e-9 or distance > difference+1e-9:
                continue
            clockwise = (start_angle-atan2(vy, vx)) % (2*pi) if distance > 1e-10 else 0.0
            if 2*pi-clockwise < 1e-10:
                clockwise = 0.0
            hits.append(RoofSightHit(
                clockwise_degrees=degrees(clockwise), roof_index=index,
                point=axes.from_local(px, py), elevation=observer.z+difference,
                plan_distance=distance, elevation_difference=difference,
                vertical_angle_degrees=degrees(atan2(max(0.0, difference), distance))))
    return min(hits, key=lambda hit: (hit.clockwise_degrees, hit.roof_index)) if hits else None


def read_survey_groups(source: str | Path) -> tuple[SurveyGroup, ...]:
    """Read blank-line-separated groups, preserving file order and optional colors.

    Rows use ID/Y/X/Z/note order, with or without the original geodet header.
    A blank line resets color, closure and name; notes never determine connections.
    A header may name its polyline: #0000ff, closed: boundary. Names are unique.
    Repeated IDs retain every polyline occurrence but must agree in Y/X/Z.
    """
    lines = Path(source).read_text(encoding="utf-8-sig").splitlines()
    start = 0
    if lines and lines[0].startswith("Seznam souřadnic"):
        if "S-JTSK" not in lines[0] or "Bpv" not in lines[0]:
            raise ValueError("expected an S-JTSK/Bpv survey list header")
        if len(lines) < 2 or lines[1].split()[1:4] != ["Y", "X", "Z"]:
            raise ValueError("expected survey columns: point number, Y, X, Z, optional note")
        start = 2
    groups, points, seen = [], [], {}
    color = None
    closed = False
    name = None
    for line_number, raw_line in enumerate(lines[start:], start+1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if points:
                groups.append(SurveyGroup(color, tuple(points), closed, name))
                points = []
            color = None
            closed = False
            name = None
            if line:
                os.environ.setdefault("MPLCONFIGDIR", str(Path(gettempdir())/"house-survey-matplotlib"))
                from matplotlib.colors import is_color_like

                style, separator, label = line.partition(":")
                if separator:
                    name = label.strip()
                    if not name:
                        raise ValueError(f"empty survey polyline name on line {line_number}")
                color_header, *options = (part.strip() for part in style.split(","))
                if any(option.casefold() != "closed" for option in options):
                    raise ValueError(f"invalid survey group option on line {line_number}: {line!r}")
                closed = bool(options)
                # Hex colors retain their #; named colors may use e.g. #red.
                color = color_header if is_color_like(color_header) else color_header[1:].strip()
                if not color or not is_color_like(color):
                    raise ValueError(f"invalid survey group color on line {line_number}: {line!r}")
            continue
        fields = line.split(maxsplit=4)
        if len(fields) < 4 or not fields[0].isdigit():
            raise ValueError(f"invalid survey point on line {line_number}: {line!r}")
        try:
            y, x, z = (float(value.replace(",", ".")) for value in fields[1:4])
        except ValueError:
            raise ValueError(f"invalid survey coordinates on line {line_number}") from None
        if not all(isfinite(v) for v in (y, x, z)) or min(y, x) <= 0:
            raise ValueError(f"expected finite coordinates and positive S-JTSK Y/X on line {line_number}")
        number = fields[0]
        coordinates, first_line = seen.setdefault(number, ((y, x, z), line_number))
        if coordinates != (y, x, z):
            raise ValueError(f"conflicting coordinates for survey point number {number!r} "
                             f"on line {line_number}; first defined on line {first_line}")
        points.append(SurveyPoint(number, y, x, z, fields[4] if len(fields) == 5 else ""))
    if points:
        groups.append(SurveyGroup(color, tuple(points), closed, name))
    if not groups:
        raise ValueError("survey must contain points")
    named_survey_groups(groups)  # Reject ambiguous names for downstream lookup.
    return tuple(groups)


def named_survey_groups(groups) -> dict[str, SurveyGroup]:
    """Index named polylines by their exact, case-sensitive header names."""
    named = {}
    for group in groups:
        if group.name is not None:
            if group.name in named:
                raise ValueError(f"duplicate survey polyline name {group.name!r}")
            named[group.name] = group
    return named


def read_survey_points(source: str | Path) -> tuple[SurveyPoint, ...]:
    """Read unique points in first-occurrence order, retaining their first note."""
    return _unique_points(read_survey_groups(source))


def _unique_points(groups):
    points = {}
    for group in groups:
        for point in group.points:
            points.setdefault(point.number, point)
    return tuple(points.values())


def _place_labels(ax, points, positions, font_size, show_ids):
    """Put each spot height directly below its measured cross, without leaders."""
    for point, position in zip(points, positions):
        label = f"{point.number}: {point.z:.2f}" if show_ids else f"{point.z:.2f}"
        named = not point.number.isdigit()
        if named:
            label = f"{point.note or point.number}\n{point.z:.2f}"
        ax.annotate(label, xy=position, xytext=(5, 0) if named else (0, -3), textcoords="offset points",
                    fontsize=font_size, color="#75b9dc", ha="left" if named else "center", va="top",
                    zorder=4, gid=f"survey-label-{point.number}")


def _draw_roof_slope(ax, roof, axes, index, overhang):
    """Vector gradient along the profile, fading away from its highest point."""
    import numpy as np
    from matplotlib.collections import LineCollection

    midpoint, direction, half_length = roof.geometry(axes)
    extent = half_length+overhang
    distances = np.linspace(-extent, extent, 257)
    vertices = np.array(midpoint)+distances[:, None]*np.array(direction)
    centers = (distances[1:]+distances[:-1])/2
    intensity = 1-np.abs(centers)/extent if roof.angle_degrees > 0 else np.ones_like(centers)
    light, red = np.array((1.0, .95, .95)), np.array((.80, .0, .0))
    colors = light+intensity[:, None]*(red-light)
    collection = LineCollection(np.stack((vertices[:-1], vertices[1:]), axis=1),
                                colors=colors, linewidths=3, zorder=1.8)
    collection.set_gid(f"survey-roof-slope-{index}")
    ax.add_collection(collection)
    ax.plot(*midpoint, marker="o", markersize=3, color=red, zorder=3,
            gid=f"survey-roof-peak-{index}")
    ax.annotate(f"{roof.elevation:.2f} m · {round(roof.angle_degrees, 2):g}°", xy=midpoint,
                xytext=(6, 6+14*index), textcoords="offset points", ha="left", fontsize=6,
                color="#a00000", zorder=4, gid=f"survey-roof-label-{index}")


def render_survey_points(
    source: str | Path,
    output: str | Path = "points.svg",
    *,
    pdf: str | Path | None = None,
    png: str | Path | None = None,
    paper: str = "A4",
    orientation: str = "landscape",
    scale: int | None = None,
    title: str | None = None,
    show_ids: bool = False,
    house: SurveyHouse | None = None,
    roof_slopes: tuple[RoofSlope, ...] = (),
    roof_overhang: float = 2.0,
    house_roof: bool = False,
    total_house_height: float | None = None,
    main_roof_angle: float | None = None,
) -> Path:
    """Create an equal-scale SVG and optional PDF/PNG, with selectable labels.

    Defaults to A4 landscape, automatically choosing a printed scale that
    fits. SVG point tooltips/metadata preserve full survey coordinates and
    notes. PDF and PNG show two-decimal Bpv elevations; show_ids also prints IDs.
    A named street polyline supplies the fitted x axis; otherwise use grid north.
    """
    # Keep Matplotlib's font/config cache inside a writable temporary directory.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(gettempdir())/"house-survey-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator
    import numpy as np

    groups = read_survey_groups(source)
    polylines = named_survey_groups(groups)
    points = _unique_points(groups)
    if not isinstance(show_ids, bool):
        raise TypeError("show_ids must be a boolean")
    street = polylines.get("street")
    frame = SurveyFrame.for_polyline(street) if street is not None else SurveyFrame.for_points(points)
    if street is not None:
        # Reverse the fitted view to match the plans, with the street below the plot.
        frame = replace(frame, rotation_radians=frame.rotation_radians-pi)
    axes = (SurveyAxes.from_polylines(street, polylines["neighbour"])
            if street is not None and "neighbour" in polylines else None)
    roof_slopes = tuple(roof_slopes)
    if house is not None:
        if axes is None:
            raise ValueError("house placement requires named street and neighbour polylines")
        frame = axes.frame
    if house_roof:
        if house is None:
            raise ValueError("house roof slope requires a placed house")
        if total_house_height is None or main_roof_angle is None:
            model_height, model_angle = read_house_roof_metrics(Path(__file__).with_name("house_ifc.py"))
            total_house_height = model_height if total_house_height is None else total_house_height
            main_roof_angle = model_angle if main_roof_angle is None else main_roof_angle
        roof_slopes = (*house_roof_profiles(
            house, axes, total_house_height=total_house_height, main_roof_angle=main_roof_angle,
            ground_elevation=HOUSE_ROOF_GROUND_ELEVATION, edge_drop=HOUSE_ROOF_EDGE_DROP,
            spacing=HOUSE_ROOF_PROFILE_SPACING), *roof_slopes)
    if roof_slopes:
        if axes is None:
            raise ValueError("roof slopes require named street and neighbour polylines")
        frame = axes.frame
    if axes is not None:
        points = (*points, neighbour_window_point(axes))
    house_corners = house.corners(axes) if house is not None else ()
    positions = np.array([frame.to_local(p.y, p.x) for p in points])
    extent_positions = np.vstack((positions, house_corners, (0, 0))) if house is not None else positions
    for roof in roof_slopes:
        extent_positions = np.vstack((extent_positions, roof.drawing_endpoints(axes, roof_overhang)))
    sizes = {"A4": (210, 297), "A3": (297, 420)}
    if paper not in sizes or orientation not in {"landscape", "portrait"}:
        raise ValueError("paper must be A4/A3 and orientation landscape/portrait")
    page_w, page_h = sizes[paper]
    if orientation == "landscape":
        page_w, page_h = page_h, page_w
    map_w, map_h = page_w-32, page_h-47
    span = np.ptp(extent_positions, axis=0)+10  # Room for labels beyond the measured extent.
    required = max(span/np.array((map_w, map_h))*1000)
    if scale is None:
        scale = next((s for s in (50, 100, 200, 250, 500, 1000, 2000, 5000, 10000) if s >= required), None)
    if scale is None or isinstance(scale, bool) or not isfinite(scale) or scale < required:
        raise ValueError("drawing scale does not fit the survey and label margin on this paper")
    output = Path(output)
    paths = [(output, ".svg"), *([(Path(pdf), ".pdf")] if pdf is not None else []),
             *([(Path(png), ".png")] if png is not None else [])]
    for path, suffix in paths:
        if path.suffix.lower() != suffix:
            raise ValueError(f"output must end in {suffix}: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    center = (extent_positions.min(axis=0)+extent_positions.max(axis=0))/2
    half = np.array((map_w, map_h))*scale/2000
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none", "pdf.fonttype": 42}):
        figure = plt.figure(figsize=(page_w/25.4, page_h/25.4), dpi=120)
        try:
            ax = figure.add_axes((20/page_w, 26/page_h, map_w/page_w, map_h/page_h))
            ax.set(xlim=(center[0]-half[0], center[0]+half[0]),
                   ylim=(center[1]-half[1], center[1]+half[1]), aspect="equal")
            ax.set_xlabel("x podél ulice [m od počátku]" if street is not None else "Východ sítě [m od počátku]", fontsize=7)
            ax.set_ylabel("y kolmo k ulici [m od počátku]" if street is not None else "Sever sítě [m od počátku]", fontsize=7)
            for axis in (ax.xaxis, ax.yaxis):
                axis.set_major_locator(MultipleLocator(10))
                axis.set_minor_locator(MultipleLocator(5))
            ax.tick_params(labelsize=6, width=.4)
            ax.grid(which="major", color="#dddddd", linewidth=.4)
            ax.grid(which="minor", color="#eeeeee", linewidth=.25)
            for spine in ax.spines.values():
                spine.set_linewidth(.4)
            for index, roof in enumerate(roof_slopes):
                _draw_roof_slope(ax, roof, axes, index, roof_overhang)
            for index, group in enumerate(groups):
                if group.color is None or len(group.points) < 2:
                    continue
                vertices = np.array([frame.to_local(p.y, p.x) for p in group.points])
                if group.closed:
                    vertices = np.vstack((vertices, vertices[0]))
                ax.plot(vertices[:, 0], vertices[:, 1], color=group.color, linewidth=.6,
                        zorder=2, gid=f"survey-group-{index}")
            for point, (east, north) in zip(points, positions):
                ax.plot(east, north, marker="+", markersize=3.5, markeredgewidth=.65,
                        color="black", zorder=3, gid=f"survey-point-{point.number}")
            _place_labels(ax, points, positions, font_size=6, show_ids=show_ids)
            if house is not None:
                vertices = np.array((*house_corners, house_corners[0]))
                ax.plot(vertices[:, 0], vertices[:, 1], color="#333333", linewidth=1.1,
                        zorder=5, gid="survey-house-footprint")
                cx, cy = axes.to_local(*house.center)
                ax.plot(cx, cy, marker="+", markersize=5, color="#333333", zorder=5,
                        gid="survey-house-center")
                ax.annotate(f"Dům {house.width:g} × {house.depth:g} m", xy=(cx, cy),
                            xytext=(0, 5), textcoords="offset points", ha="center", fontsize=7,
                            zorder=5, gid="survey-house-label")
                ax.annotate("(0, 0)", xy=(0, 0), xytext=(4, -10), textcoords="offset points",
                            fontsize=6, zorder=5, gid="survey-placement-origin")
                for name, endpoint in (("x", axes.to_local(3, 0)), ("y", axes.to_local(0, 3))):
                    ax.annotate("", xy=endpoint, xytext=(0, 0), zorder=5,
                                arrowprops={"arrowstyle": "->", "lw": .6, "color": "#555555"})
                    ax.annotate(name, xy=endpoint, xytext=(3, 3), textcoords="offset points",
                                fontsize=7, color="#555555", zorder=5)
            north_center = np.array((.90, .85))
            north_half = .065*np.array((sin(frame.rotation_radians), cos(frame.rotation_radians)*map_w/map_h))
            ax.annotate("−X\nsever sítě", xy=north_center+north_half, xytext=north_center-north_half,
                        xycoords="axes fraction", ha="center", va="center", fontsize=6,
                        arrowprops={"arrowstyle": "-|>", "color": "black", "lw": .7})
            bar_x, bar_y = center-half+np.array((5, 5))
            ax.plot((bar_x, bar_x+10), (bar_y, bar_y), color="black", linewidth=1.3)
            ax.text(bar_x+5, bar_y+1, "10 m", ha="center", fontsize=6)
            resolved_title = title if title is not None else Path(pdf if pdf is not None else output).stem
            figure.text(.5, 1-10/page_h, f"{resolved_title}  1:{scale:g}",
                        ha="center", va="center", fontsize=12, weight="bold")
            figure.text(20/page_w, 8/page_h,
                        f"S-JTSK / Bpv [m]  ·  {len(points)} bodů  ·  popisek: "
                        + ("číslo bodu : výška Z" if show_ids else "výška Z"), fontsize=7)
            figure.text(20/page_w, 3.5/page_h,
                        f"Počátek: Y₀ = {frame.origin_y:.2f}, X₀ = {frame.origin_x:.2f} m; "
                        + (f"osa x: proložená přímka street; otočení obrazu { -degrees(frame.rotation_radians):.2f}°"
                           if street is not None else "východ = Y₀ − Y, sever sítě = X₀ − X"),
                        fontsize=6, color="#555555")
            for path, suffix in paths:
                figure.savefig(path, format=suffix[1:], dpi=200, facecolor="white")
        finally:
            plt.close(figure)
    svg = output.read_text(encoding="utf-8")
    metadata = {"coordinate_system": "S-JTSK", "height_system": "Bpv", "units": "metres",
                "column_order": ["number", "Y", "X", "Z", "note"], "scale": scale,
                "frame": asdict(frame), "points": [asdict(p) for p in points],
                "groups": [{"color": group.color, "closed": group.closed, "name": group.name,
                            "point_ids": [p.number for p in group.points]}
                           for group in groups]}
    if roof_slopes:
        metadata["roof_slopes"] = [{**asdict(roof), "unbounded": True,
                                    "local_midpoint": roof.geometry(axes)[0],
                                    "local_direction": roof.geometry(axes)[1],
                                    "drawing_overhang": roof_overhang}
                                   for roof in roof_slopes]
    if axes is not None:
        metadata["derived_points"] = {"neighbour-window": {
            "name": "neighbour window", "axes_coordinates": [0.0, NEIGHBOUR_WINDOW_DISTANCE],
            "origin": "intersection of fitted street and neighbour lines",
            "elevation_bpv": NEIGHBOUR_WINDOW_ELEVATION}}
    if house is not None:
        metadata["placement_axes"] = {"origin": "intersection of fitted street and neighbour lines",
                                      "x_direction": [1.0, 0.0],
                                      "y_direction": axes.neighbour_direction}
        metadata["house"] = {**asdict(house), "local_center": axes.to_local(*house.center),
                             "local_corners": house_corners,
                             "survey_corners": [frame.to_survey(*p) for p in house_corners]}
    root = re.search(r"<svg\b[^>]*>", svg)
    svg = svg[:root.end()] + '<metadata id="survey-data">' + escape(json.dumps(metadata, ensure_ascii=False)) + '</metadata>' + svg[root.end():]
    for point in points:
        opening = f'<g id="survey-point-{point.number}">'
        tooltip = f"Bod {point.number}: Y={point.y:.2f}, X={point.x:.2f}, Z={point.z:.2f} m; {point.note}"
        svg = svg.replace(opening, opening+f"<title>{escape(tooltip)}</title>")
    for index, group in enumerate(groups):
        opening = f'<g id="survey-group-{index}">'
        tooltip = f"Barva: {group.color}; body: " + ", ".join(p.number for p in group.points)
        if group.name is not None:
            tooltip = f"{group.name}; " + tooltip
        if group.closed:
            tooltip += "; uzavřeno"
        svg = svg.replace(opening, opening+f"<title>{escape(tooltip)}</title>")
    output.write_text(svg, encoding="utf-8")
    print(f"Survey: {len(points)} points, Y span {np.ptp([p.y for p in points]):.2f} m, "
          f"X span {np.ptp([p.x for p in points]):.2f} m, Z {min(p.z for p in points):.2f}–{max(p.z for p in points):.2f} m Bpv")
    print(f"Survey drawing: {output} ({paper} {orientation}, 1:{scale:g})")
    if street is not None:
        residuals = [frame.to_local(p.y, p.x)[1] for p in _unique_points((street,))]
        print(f"Street fit: picture rotation {-degrees(frame.rotation_radians):.3f}°, "
              f"RMS perpendicular distance {(sum(r*r for r in residuals)/len(residuals))**.5:.3f} m")
    if house is not None:
        print(f"House: {house.width:g} × {house.depth:g} m, center {house.center}, "
              f"rotation {house.angle_degrees:g}° counterclockwise from street")
        print(f"Placement origin: Y={frame.origin_y:.3f}, X={frame.origin_x:.3f}; "
              f"axis angle {degrees(atan2(axes.neighbour_direction[1], axes.neighbour_direction[0])):.3f}°")
        for name, distance in house.line_distances(axes).items():
            print(f"Shortest house distance to {name}: {distance:.3f} m")
    for index, roof in enumerate(roof_slopes, 1):
        print(f"Roof slope {index}: midpoint elevation {roof.elevation:.2f} m Bpv, "
              f"angle {roof.angle_degrees:g}°, unbounded in both directions")
    if roof_slopes:
        hit = first_roof_45_degree_hit(roof_slopes, axes, neighbour_window_point(axes))
        if hit is None:
            print("Roof visibility from neighbour window: no roof profile reaches 45° in a full clockwise turn")
        else:
            print(f"Roof visibility from neighbour window: first >=45° at {hit.clockwise_degrees:.3f}° "
                  f"clockwise from window→origin (roof slope {hit.roof_index})")
            print(f"  Intersection: x={hit.point[0]:.3f}, y={hit.point[1]:.3f} m along street/neighbour; "
                  f"elevation={hit.elevation:.3f} m Bpv")
            print(f"  Plan distance={hit.plan_distance:.3f} m; elevation difference={hit.elevation_difference:.3f} m; "
                  f"vertical angle={hit.vertical_angle_degrees:.3f}°")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path("points.txt"))
    parser.add_argument("--svg", type=Path, default=Path("points.svg"))
    parser.add_argument("--pdf", type=Path, default=Path("projekt/Zaměření pozemku.pdf"))
    parser.add_argument("--png", type=Path, default=Path("points.png"))
    parser.add_argument("--paper", choices=("A4", "A3"), default="A4")
    parser.add_argument("--orientation", choices=("landscape", "portrait"), default="landscape")
    parser.add_argument("--scale", type=int)
    parser.add_argument("--point-ids", action="store_true", help="also print point IDs next to elevations")
    parser.add_argument("--house-center", type=float, nargs=2, metavar=("X", "Y"), default=HOUSE_PLACEMENT.center,
                        help="house center in metres along street and neighbour from their fitted intersection")
    parser.add_argument("--house-angle", type=float, default=HOUSE_PLACEMENT.angle_degrees,
                        help="house rotation counterclockwise from street, in degrees")
    parser.add_argument("--no-house", action="store_true", help="omit house placement overlay")
    args = parser.parse_args()
    render_survey_points(args.source, args.svg, pdf=args.pdf, png=args.png,
                         paper=args.paper, orientation=args.orientation, scale=args.scale,
                         title="Zaměření pozemku – výškové body", show_ids=args.point_ids,
                         house=None if args.no_house else replace(HOUSE_PLACEMENT, center=tuple(args.house_center),
                                                                  angle_degrees=args.house_angle),
                         roof_slopes=ROOF_SLOPES, roof_overhang=ROOF_SLOPE_OVERHANG,
                         house_roof=HOUSE_ROOF_ENABLED and not args.no_house)


if __name__ == "__main__":
    main()
