"""Read Czech S-JTSK/Bpv survey lists and draw a measured plan of the points.

Input order is point number, Y (westing), X (southing), Z (Bpv), optional note.
Blank lines separate groups; an optional #color header connects a group's
points in file order. Add ", closed" to connect the last point to the first.
Notes are descriptive only.
Local plan axes are east = Y0-Y and grid north = X0-X. No geographic transform
or house placement is inferred; the original coordinates remain available.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from html import escape
import json
from math import floor, isfinite
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


@dataclass(frozen=True)
class SurveyFrame:
    """Translation and axis orientation only; all distances remain in metres."""

    origin_y: float
    origin_x: float

    def to_local(self, y: float, x: float) -> tuple[float, float]:
        return self.origin_y-y, self.origin_x-x

    def to_survey(self, east: float, north: float) -> tuple[float, float]:
        return self.origin_y-east, self.origin_x-north

    @classmethod
    def for_points(cls, points):
        if not points:
            raise ValueError("survey must contain points")
        return cls(*(floor((min(values)+max(values))/200+.5)*100.0
                     for values in ([p.y for p in points], [p.x for p in points])))


def read_survey_groups(source: str | Path) -> tuple[SurveyGroup, ...]:
    """Read blank-line-separated groups, preserving file order and optional colors.

    Rows use ID/Y/X/Z/note order, with or without the original geodet header.
    A blank line resets the color and closure; notes never determine connections.
    """
    lines = Path(source).read_text(encoding="utf-8-sig").splitlines()
    start = 0
    if lines and lines[0].startswith("Seznam souřadnic"):
        if "S-JTSK" not in lines[0] or "Bpv" not in lines[0]:
            raise ValueError("expected an S-JTSK/Bpv survey list header")
        if len(lines) < 2 or lines[1].split()[1:4] != ["Y", "X", "Z"]:
            raise ValueError("expected survey columns: point number, Y, X, Z, optional note")
        start = 2
    groups, points, seen = [], [], set()
    color = None
    closed = False
    for line_number, raw_line in enumerate(lines[start:], start+1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if points:
                groups.append(SurveyGroup(color, tuple(points), closed))
                points = []
            color = None
            closed = False
            if line:
                os.environ.setdefault("MPLCONFIGDIR", str(Path(gettempdir())/"house-survey-matplotlib"))
                from matplotlib.colors import is_color_like

                color_header, *options = (part.strip() for part in line.split(","))
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
        if number in seen:
            raise ValueError(f"duplicate survey point number {number!r} on line {line_number}")
        seen.add(number)
        points.append(SurveyPoint(number, y, x, z, fields[4] if len(fields) == 5 else ""))
    if points:
        groups.append(SurveyGroup(color, tuple(points), closed))
    if not groups:
        raise ValueError("survey must contain points")
    return tuple(groups)


def read_survey_points(source: str | Path) -> tuple[SurveyPoint, ...]:
    """Read all points in file order, preserving IDs, heights and survey notes."""
    return tuple(point for group in read_survey_groups(source) for point in group.points)


def _place_labels(ax, points, positions, font_size, show_ids):
    """Put each spot height directly below its measured cross, without leaders."""
    for point, position in zip(points, positions):
        label = f"{point.number}: {point.z:.2f}" if show_ids else f"{point.z:.2f}"
        ax.annotate(label, xy=position, xytext=(0, -3), textcoords="offset points",
                    fontsize=font_size, color="#75b9dc", ha="center", va="top",
                    zorder=4, gid=f"survey-label-{point.number}")


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
) -> Path:
    """Create an equal-scale SVG and optional PDF/PNG, with selectable labels.

    Defaults to A4 landscape, automatically choosing a printed scale that
    fits. SVG point tooltips/metadata preserve full survey coordinates and
    notes. PDF and PNG show two-decimal Bpv elevations; show_ids also prints IDs.
    """
    # Keep Matplotlib's font/config cache inside a writable temporary directory.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(gettempdir())/"house-survey-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator
    import numpy as np

    groups = read_survey_groups(source)
    points = tuple(point for group in groups for point in group.points)
    if not isinstance(show_ids, bool):
        raise TypeError("show_ids must be a boolean")
    frame = SurveyFrame.for_points(points)
    positions = np.array([frame.to_local(p.y, p.x) for p in points])
    sizes = {"A4": (210, 297), "A3": (297, 420)}
    if paper not in sizes or orientation not in {"landscape", "portrait"}:
        raise ValueError("paper must be A4/A3 and orientation landscape/portrait")
    page_w, page_h = sizes[paper]
    if orientation == "landscape":
        page_w, page_h = page_h, page_w
    map_w, map_h = page_w-32, page_h-47
    span = np.ptp(positions, axis=0)+10  # Room for labels beyond the measured extent.
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
    center = (positions.min(axis=0)+positions.max(axis=0))/2
    half = np.array((map_w, map_h))*scale/2000
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none", "pdf.fonttype": 42}):
        figure = plt.figure(figsize=(page_w/25.4, page_h/25.4), dpi=120)
        try:
            ax = figure.add_axes((20/page_w, 26/page_h, map_w/page_w, map_h/page_h))
            ax.set(xlim=(center[0]-half[0], center[0]+half[0]),
                   ylim=(center[1]-half[1], center[1]+half[1]), aspect="equal")
            ax.set_xlabel("Východ sítě [m od počátku]", fontsize=7)
            ax.set_ylabel("Sever sítě [m od počátku]", fontsize=7)
            for axis in (ax.xaxis, ax.yaxis):
                axis.set_major_locator(MultipleLocator(10))
                axis.set_minor_locator(MultipleLocator(5))
            ax.tick_params(labelsize=6, width=.4)
            ax.grid(which="major", color="#dddddd", linewidth=.4)
            ax.grid(which="minor", color="#eeeeee", linewidth=.25)
            for spine in ax.spines.values():
                spine.set_linewidth(.4)
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
            ax.annotate("−X\nsever sítě", xy=(.96, .94), xytext=(.96, .80),
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
                        "východ = Y₀ − Y, sever sítě = X₀ − X", fontsize=6, color="#555555")
            for path, suffix in paths:
                figure.savefig(path, format=suffix[1:], dpi=200, facecolor="white")
        finally:
            plt.close(figure)
    svg = output.read_text(encoding="utf-8")
    metadata = {"coordinate_system": "S-JTSK", "height_system": "Bpv", "units": "metres",
                "column_order": ["number", "Y", "X", "Z", "note"], "scale": scale,
                "frame": asdict(frame), "points": [asdict(p) for p in points],
                "groups": [{"color": group.color, "closed": group.closed,
                            "point_ids": [p.number for p in group.points]}
                           for group in groups]}
    root = re.search(r"<svg\b[^>]*>", svg)
    svg = svg[:root.end()] + '<metadata id="survey-data">' + escape(json.dumps(metadata, ensure_ascii=False)) + '</metadata>' + svg[root.end():]
    for point in points:
        opening = f'<g id="survey-point-{point.number}">'
        tooltip = f"Bod {point.number}: Y={point.y:.2f}, X={point.x:.2f}, Z={point.z:.2f} m; {point.note}"
        svg = svg.replace(opening, opening+f"<title>{escape(tooltip)}</title>")
    for index, group in enumerate(groups):
        opening = f'<g id="survey-group-{index}">'
        tooltip = f"Barva: {group.color}; body: " + ", ".join(p.number for p in group.points)
        if group.closed:
            tooltip += "; uzavřeno"
        svg = svg.replace(opening, opening+f"<title>{escape(tooltip)}</title>")
    output.write_text(svg, encoding="utf-8")
    print(f"Survey: {len(points)} points, Y span {np.ptp([p.y for p in points]):.2f} m, "
          f"X span {np.ptp([p.x for p in points]):.2f} m, Z {min(p.z for p in points):.2f}–{max(p.z for p in points):.2f} m Bpv")
    print(f"Survey drawing: {output} ({paper} {orientation}, 1:{scale:g})")
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
    args = parser.parse_args()
    render_survey_points(args.source, args.svg, pdf=args.pdf, png=args.png,
                         paper=args.paper, orientation=args.orientation, scale=args.scale,
                         title="Zaměření pozemku – výškové body", show_ids=args.point_ids)


if __name__ == "__main__":
    main()
