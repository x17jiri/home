"""North-up cadastral diagram of the neighbour-window shading clearance."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from html import escape
import json
from math import atan2, cos, degrees, hypot, radians, sin, sqrt
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from textwrap import wrap

from pyproj import CRS
import shapefile

from cadastral_situation import DEFAULT_CADASTRE, NorthUpFrame, ROOT, layer_features, parcel_arrow_paths
from drawing_title_block import load_title_block, title_block_svg
from pdf_utils import save_drawing_svg
from project_documents import DRAWINGS, document_path
from roof_frame_3d import HouseInputs
from survey_points import (
    HOUSE_PLACEMENT, SurveyAxes, named_survey_groups, neighbour_window_point, read_survey_groups,
)


TITLE = DRAWINGS["zastineni"].title
NUMBER = DRAWINGS["zastineni"].number
DEFAULT_SVG = ROOT / "projekt2/zastineni.svg"
DEFAULT_PDF = ROOT / document_path("zastineni")
GREEN = "#16713a"
ORANGE = "#b65610"
NOTE = (
    "Odstupový úhel stínění podle § 20, odst. 4, Přílohy č. 4 vyhlášky č. 146/2024 Sb. "
    "o požadavcích na výstavbu ve znění novely č. 97/2026 Sb., účinné od 1. července 2026 "
    "je splněn. Žádná navrhovaná překážka nezasahuje do vertikálního úhlu 45°."
)


def maximum_segment_angle(observer, start, end):
    """Exact maximum elevation on a straight 3D segment, including its interior."""
    x, y, h = (start[i]-observer[i] for i in range(3))
    dx, dy, dh = (end[i]-start[i] for i in range(3))
    a, b, c = x*x+y*y, x*dx+y*dy, dx*dx+dy*dy
    candidates = [0.0, 1.0]
    denominator = dh*b-h*c
    if abs(denominator) > 1e-14:
        t = (h*b-dh*a)/denominator
        if 0 < t < 1:
            candidates.append(t)
    if c > 0 and 0 < -b/c < 1:
        candidates.append(-b/c)  # Includes a possible vertical line of sight.
    results = []
    for t in candidates:
        point = tuple(start[i]+t*(end[i]-start[i]) for i in range(3))
        distance = hypot(point[0]-observer[0], point[1]-observer[1])
        rise = point[2]-observer[2]
        results.append(dict(angle_degrees=degrees(atan2(rise, distance)), point=point,
                            plan_distance_m=distance, rise_m=rise, margin_45_m=distance-rise))
    return max(results, key=lambda result: result["angle_degrees"])


def viewing_geometry(axes, house=HOUSE_PLACEMENT):
    """The façade tangent and its outward normal toward the proposed house."""
    observer = neighbour_window_point(axes)
    origin = axes.frame.to_local(observer.y, observer.x)
    tx, ty = axes.neighbour_direction
    normal = (-ty, tx)
    centre = axes.to_local(*house.center)
    if sum((centre[i]-origin[i])*normal[i] for i in range(2)) < 0:
        normal = (-normal[0], -normal[1])
    return observer, origin, (tx, ty), normal


def roof_and_chimney_checks(axes, *, house=HOUSE_PLACEMENT, source=ROOT / "house2.py"):
    """Read the new roof as arithmetic data; no IFC generation or saved results.

    Each pitched top surface is affine over a rectangular half-footprint.
    With the observer outside the footprint, its maximum elevation angle
    occurs on an edge (including an edge interior). The chimney is checked
    over the four edges of its top. Lower walls have smaller sight angles.
    """
    g = HouseInputs(source).get
    width, depth = g("HOUSE_WIDTH"), g("HOUSE_DEPTH")
    floor, datum = g("GROUND_FINISHED_FLOOR_ELEVATION"), g("GROUND_FLOOR_THICKNESS")
    cx, cy = axes.to_local(*house.center)
    c, s = cos(radians(house.angle_degrees)), sin(radians(house.angle_degrees))

    def placed(x, y, model_z):
        dx, dy = x-width/2, y-depth/2
        return cx+c*dx-s*dy, cy+s*dx+c*dy, floor+model_z-datum

    window = neighbour_window_point(axes)
    observer = (*axes.frame.to_local(window.y, window.x), window.z)
    roofs, gutters, ridge_levels = [], [], []
    pwidth, pheight = g("PURLIN_SIZE")
    plate_width, plate_height = g("WALL_PLATE_SIZE")
    offset = g("ROOF_TILE_BOTTOM")+g("ROOF_TILE_THICKNESS")
    tile_y0, tile_y1 = -g("ROOF_GABLE_OVERHANG"), depth+g("ROOF_GABLE_OVERHANG")
    # Include the outer faces of the red gable-edge trim in the roof bound.
    y0, y1 = tile_y0-g("ROOF_EDGE_TRIM_THICKNESS"), tile_y1+g("ROOF_EDGE_TRIM_THICKNESS")
    for index, direction in ((0, 1), (-1, -1)):
        plate_x = g("BWT")/2 if direction == 1 else width-g("BWT")/2
        seat_x = plate_x-direction*plate_width/2
        purlin_x = g("PURLIN_X_POSITIONS")[index]-direction*pwidth/2
        plate_top = g("WALL_PLATE_Z")+plate_height/2
        slope = (g("PURLIN_Z")+pheight/2-plate_top)/(purlin_x-seat_x)

        def z(x):
            return plate_top+slope*(x-seat_x)+offset*sqrt(1+slope*slope)

        eave_x = -g("ROOF_EAVE_OVERHANG") if direction == 1 else width+g("ROOF_EAVE_OVERHANG")
        if z(eave_x) < g("ROOF_EAVE_CUT_Z"):
            raise ValueError("Roof clipping changed: update the shading footprint calculation")
        corners = [placed(x, y, z(x)) for x, y in
                   ((eave_x, y0), (width/2, y0), (width/2, y1), (eave_x, y1))]
        roofs.append(corners)
        ridge_levels.append(z(width/2))
        rim_z = max(g("ROOF_EAVE_CUT_Z"),
                    z(eave_x)-g("ROOF_TILE_THICKNESS")*sqrt(1+slope*slope))-g("GUTTER_DROP_BELOW_TILES")
        inner_x = eave_x-direction*g("GUTTER_EDGE_GAP")
        outer_x = eave_x-direction*(g("GUTTER_DIAMETER")+g("GUTTER_EDGE_GAP"))
        # The entire gutter lies at or below this rim-height rectangular bound.
        gutters.append([placed(x,y,rim_z) for x,y in
                        ((inner_x,tile_y0),(outer_x,tile_y0),(outer_x,tile_y1),(inner_x,tile_y1))])
    roof = max((maximum_segment_angle(observer, p, q) for corners in roofs
                for p, q in zip(corners, [*corners[1:], corners[0]])),
               key=lambda result: result["angle_degrees"])
    gutter = max((maximum_segment_angle(observer,p,q) for corners in gutters
                  for p,q in zip(corners,[*corners[1:],corners[0]])),
                 key=lambda result: result["angle_degrees"])
    chimney_z = max(ridge_levels)+g("CHIMNEY_ABOVE_ROOF")
    x, y = g("CHIMNEY_CENTER")
    half = g("CHIMNEY_SIZE")/2
    chimney_corners = [placed(x+dx, y+dy, chimney_z)
                       for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half))]
    chimney = max((maximum_segment_angle(observer, p, q)
                   for p, q in zip(chimney_corners, [*chimney_corners[1:], chimney_corners[0]])),
                  key=lambda result: result["angle_degrees"])
    return dict(floor_elevation_bpv=floor, observer=asdict(window), roof=roof, gutters=gutter, chimney=chimney,
                roof_top_polygons=roofs, chimney_top_polygon=chimney_corners)


def render_shading(*, cadastre=DEFAULT_CADASTRE, points=ROOT / "points.txt",
                   output=DEFAULT_SVG, pdf=DEFAULT_PDF):
    inkscape = shutil.which("inkscape")
    if inkscape is None:
        raise FileNotFoundError("Inkscape is required to export the shading PDF")
    groups = named_survey_groups(read_survey_groups(points))
    axes = SurveyAxes.from_polylines(groups["street"], groups["neighbour"])
    observer, origin, tangent, normal = viewing_geometry(axes)
    checks = roof_and_chimney_checks(axes)
    if max(checks[name]["angle_degrees"] for name in ("roof", "gutters", "chimney")) >= 45-1e-8:
        raise ValueError("Current roof/chimney geometry reaches 45°; the requested compliance note needs revision")
    crs = CRS.from_wkt((cadastre / "PARCELY_KN_P.prj").read_text())
    grid_origin = (-observer.y, -observer.x)
    frame = NorthUpFrame.at(*grid_origin, crs)

    def local_to_grid(p):
        y, x = axes.frame.to_survey(*p)
        return -y, -x

    radius = 18

    def polar(angle, distance=radius):
        c, s = cos(radians(angle)), sin(radians(angle))
        return tuple(origin[i]+distance*(c*normal[i]+s*tangent[i]) for i in range(2))

    def arc(lo, hi, distance=radius):
        steps = max(1, round((hi-lo)/2))
        return [polar(lo+(hi-lo)*i/steps, distance) for i in range(steps+1)]

    house_corners = HOUSE_PLACEMENT.corners(axes)
    extent = [frame.to_local(*local_to_grid(p)) for p in [*arc(-90, 90), *house_corners, origin]]
    centre = tuple((min(p[i] for p in extent)+max(p[i] for p in extent))/2 for i in (0, 1))
    map_x, map_y, map_w, map_h = 10, 26, 295, 198
    scale, mm_per_m = 250, 4
    bounds = (centre[0]-map_w/mm_per_m/2, centre[1]-map_h/mm_per_m/2,
              centre[0]+map_w/mm_per_m/2, centre[1]+map_h/mm_per_m/2)
    corners = [frame.to_grid(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
    bbox = (min(p[0] for p in corners), min(p[1] for p in corners),
            max(p[0] for p in corners), max(p[1] for p in corners))

    def position(east, north):
        x, y = frame.to_local(east, north)
        return map_x+(x-bounds[0])*mm_per_m, map_y+(bounds[3]-y)*mm_per_m

    def path(vertices, close=False):
        return "M"+" L".join(f"{x:.3f},{y:.3f}" for x, y in (position(*p) for p in vertices))+(" Z" if close else "")

    def local_path(vertices, close=False):
        return path([local_to_grid(p) for p in vertices], close)

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">',
           '<rect width="420" height="297" fill="white"/>',
           '<style>text{font-family:DejaVu Sans,sans-serif;fill:#222;stroke:none}'
           '.halo{paint-order:stroke;stroke:white;stroke-width:.8;stroke-linejoin:round}'
           'path{stroke-linejoin:round;stroke-linecap:round}</style>',
           f'<defs><clipPath id="map-clip"><rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}"/></clipPath></defs>']

    def text(x, y, value, size=2.5, *, bold=False, anchor="start", attrs=""):
        svg.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" font-weight="{"bold" if bold else "normal"}" '
                   f'text-anchor="{anchor}" {attrs}>{escape(str(value))}</text>')

    text(210, 15, f"{NUMBER}. {TITLE}  1:{scale}", 4.3, anchor="middle", bold=True)
    svg.append('<g id="cadastral-map" clip-path="url(#map-clip)">')
    for name, fill, stroke, width in (("BUDOVY_P", "#eaeaea", "#666", .18),
                                      ("DALSI_PRVKY_MAPY_L", "none", "#aaa", .12)):
        svg.append(f'<g id="{name}" fill="{fill}" stroke="{stroke}" stroke-width="{width}">')
        for _, feature in layer_features(cadastre, name, bbox):
            if not feature.points:
                continue
            indices = [*feature.parts, len(feature.points)]
            d = " ".join(path(feature.points[a:b], feature.shapeType == shapefile.POLYGON)
                         for a, b in zip(indices, indices[1:]))
            svg.append(f'<path d="{d}" fill-rule="evenodd"/>')
        svg.append('</g>')
    svg.append('<g id="parcel-boundaries" fill="none" stroke="#555" stroke-width=".16">')
    for _, feature in layer_features(cadastre, "PARCELY_KN_P", bbox):
        indices = [*feature.parts, len(feature.points)]
        svg.append(f'<path d="{" ".join(path(feature.points[a:b], True) for a, b in zip(indices, indices[1:]))}"/>')
    svg.append('</g>')
    for lo, hi, fill, name in ((-90, -65, "#ffe8d5", "excluded-left-25"),
                                (-65, 65, "#c9efd4", "usable-130"),
                                (65, 90, "#ffe8d5", "excluded-right-25")):
        svg.append(f'<path id="{name}" d="{local_path([origin,*arc(lo,hi)],True)}" '
                   f'fill="{fill}" fill-opacity=".48" stroke="none"/>')
    svg.append('<g id="parcel-leaders" fill="none" stroke="#555" stroke-width=".12">')
    for record, feature in layer_features(cadastre, "PARCELY_KN_L", bbox):
        if str(record["TYPPPD_KOD"]) == "1032":
            indices = [*feature.parts, len(feature.points)]
            svg.append(f'<path d="{" ".join(path(feature.points[a:b]) for a, b in zip(indices, indices[1:]))}"/>')
    for record, feature in layer_features(cadastre, "PARCELY_KN_B", bbox):
        if str(record["TYPPPD_KOD"]) == "1033" and feature.points:
            shaft, head = parcel_arrow_paths(feature.points[0], float(record["ROTACE"] or 0), float(record["MERITKO"] or 1))
            svg.append(f'<path d="{path(shaft)} {path(head)}"/>')
    svg.append('</g>')
    for name, size in (("PARCELY_KN_T", 2.1), ("BUDOVY_DEF", 1.7)):
        for record, feature in layer_features(cadastre, name, bbox):
            if not feature.points:
                continue
            x, y = position(*feature.points[0])
            if not (map_x+2 < x < map_x+map_w-2 and map_y+2 < y < map_y+map_h-2):
                continue
            if name == "PARCELY_KN_T":
                reference = record.get("VZ_BOD") or "BC"
                anchor = {"L":"start", "C":"middle", "R":"end"}[reference[1]]
                baseline = {"T":"text-before-edge", "C":"central", "B":"text-after-edge"}[reference[0]]
                angle = -float(record.get("ROTACE") or 0)-degrees(frame.north_angle)
                text(x, y, record["TEXT_KM"], size, anchor=anchor,
                     attrs=f'class="halo" dominant-baseline="{baseline}" transform="rotate({angle:g} {x:g} {y:g})"')
            else:
                text(x, y, record["TEXT_KM"], size, anchor="middle", attrs='class="halo"')
    svg.append(f'<path id="new-house" d="{local_path(house_corners, True)}" '
               'fill="none" stroke="black" stroke-width=".85"/>')
    hx, hy = position(*local_to_grid(axes.to_local(*HOUSE_PLACEMENT.center)))
    text(hx, hy, "Navrhovaný RD", 2.6, anchor="middle", bold=True, attrs='class="halo"')
    text(hx, hy+4, f"{HOUSE_PLACEMENT.width:g} × {HOUSE_PLACEMENT.depth:g} m", 2.3, anchor="middle", attrs='class="halo"')
    svg.append(f'<path id="facade-plane" d="{local_path([polar(-90),polar(90)])}" '
               'fill="none" stroke="#333" stroke-width=".35" stroke-dasharray="2,1"/>')
    for angle in (-65, 65):
        svg.append(f'<path d="{local_path([origin,polar(angle)])}" fill="none" stroke="{GREEN}" stroke-width=".45"/>')
    for lo, hi, distance, color in ((-65,65,7,GREEN), (-90,-65,5.5,ORANGE), (65,90,5.5,ORANGE)):
        svg.append(f'<path d="{local_path(arc(lo,hi,distance))}" fill="none" stroke="{color}" stroke-width=".45"/>')
        label_radius = 5.0 if hi-lo == 130 else distance+1.2
        x, y = position(*local_to_grid(polar((lo+hi)/2,label_radius)))
        text(x, y, f"{hi-lo}°", 4 if hi-lo==130 else 3.1, anchor="middle", bold=True,
             attrs=f'class="halo" style="fill:{color}"')
    wx, wy = position(*grid_origin)
    svg.append(f'<circle id="neighbour-window" cx="{wx:g}" cy="{wy:g}" r="1.3" fill="white" stroke="{ORANGE}" stroke-width=".6"/>')
    text(wx+2, wy-2, "Posuzované okno", 2.8, bold=True, attrs=f'class="halo" style="fill:{ORANGE}"')
    text(map_x+map_w-9, map_y+9, "S", 3, anchor="middle", bold=True, attrs='class="halo"')
    svg.append(f'<path d="M{map_x+map_w-9},{map_y+26}v-12l-2,4l2,-2l2,2" fill="none" stroke="black" stroke-width=".35"/>')
    svg.append('</g>')
    svg.append(f'<rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" fill="none" stroke="#333" stroke-width=".25"/>')
    text(315, 31, "LEGENDA", 3, bold=True)
    for y, label, fill, stroke, width in ((41,"Navrhovaný RD","none","black",.85),
                                        (51,"Započitatelná výseč 130°","#c9efd4",GREEN,.2),
                                        (61,"Nezapočitatelné pásmo 25°","#ffe8d5",ORANGE,.2)):
        svg.append(f'<rect x="315" y="{y-3}" width="10" height="5" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
        text(329, y, label, 2.4)
    svg.append(f'<circle cx="320" cy="70" r="1.3" fill="white" stroke="{ORANGE}" stroke-width=".6"/>')
    text(329, 71, "Kontrolní bod v okně", 2.4)
    text(315, 87, "KONTROLNÍ BOD", 2.8, bold=True)
    for y, label in ((95,f"Y = {observer.y:.3f} m"), (101,f"X = {observer.x:.3f} m"),
                     (107,f"Z = {observer.z:.3f} m Bpv"), (115,"Střed okna v rovině fasády")):
        text(315, y, label, 2.5)
    text(315, 131, "VÝSLEDEK POSOUZENÍ", 2.8, bold=True)
    text(315, 140, "Volný horizontální úhel: 130°", 2.6, bold=True, attrs=f'style="fill:{GREEN}"')
    text(315, 148, "180° − 25° − 25° = 130°", 2.6)
    text(315, 158, f"Podlaha 1.NP: {checks['floor_elevation_bpv']:.3f} m Bpv", 2.4)
    text(315, 170, f"Střecha: max. {checks['roof']['angle_degrees']:.3f}° < 45°", 2.6)
    text(315, 178, f"Žlaby: max. {checks['gutters']['angle_degrees']:.3f}° < 45°", 2.6)
    text(315, 186, f"Komín: max. {checks['chimney']['angle_degrees']:.3f}° < 45°", 2.6)
    text(315, 199, "Rovina fasády dle zaměření.", 2.3)
    text(315, 205, "Orientace: geografický sever nahoře.", 2.1)
    text(10, 235, "POZNÁMKA", 2.8, bold=True)
    for index, line in enumerate(wrap(NOTE, width=103)):
        text(10, 242+4.5*index, line, 2.7)
    text(10, 275, "Katastrální území Lažánky u Blanska (679453).", 2.2)
    settings = load_title_block(output)
    if settings is not None:
        svg.append(title_block_svg(settings, filename=pdf.name, scale="1:250", paper="A3", x=330, y=228))
    info = dict(drawing_number=NUMBER, frame=asdict(frame), scale=scale, house=asdict(HOUSE_PLACEMENT),
                house_survey_corners=[axes.frame.to_survey(*p) for p in house_corners],
                observer=asdict(observer), facade_tangent=tangent, view_normal=normal,
                horizontal_sector_degrees=130, excluded_each_side_degrees=25, checks=checks,
                sector_grid_points=[local_to_grid(p) for p in [origin,*arc(-65,65)]], note=NOTE)
    svg.append('<metadata id="shading-data">'+escape(json.dumps(info,ensure_ascii=False))+'</metadata></svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(svg)+"\n",encoding="utf-8")
    sheet_path = save_drawing_svg(output, pdf)
    with TemporaryDirectory(prefix=".shading-pdf-",dir=pdf.parent) as directory:
        target = Path(directory)/pdf.name
        subprocess.run([inkscape,str(sheet_path),f"--export-filename={target}","--export-type=pdf",
                        "--export-area-page","--batch-process"],check=True)
        if not target.is_file() or target.stat().st_size==0:
            raise RuntimeError("Inkscape did not create the shading PDF")
        target.replace(pdf)
    print(f"Shading diagram: {pdf} (A3 landscape, 1:{scale}); usable sector 130°")
    print(f"Maximum vertical angles: roof {checks['roof']['angle_degrees']:.3f}°; chimney {checks['chimney']['angle_degrees']:.3f}°")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cadastre",type=Path,default=DEFAULT_CADASTRE)
    parser.add_argument("--points",type=Path,default=ROOT/"points.txt")
    parser.add_argument("--output",type=Path,default=DEFAULT_SVG)
    parser.add_argument("--pdf",type=Path,default=DEFAULT_PDF)
    render_shading(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
