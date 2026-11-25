"""Draw a north-up cadastral situation without building the IFC house model."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from html import escape
import json
from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from pyproj import CRS, Transformer
from pyproj.enums import TransformDirection
import shapefile
from shapely.geometry import LineString, Point, Polygon, shape as geometry_shape
from shapely.ops import linemerge, polygonize, split, substring, transform, unary_union

from drawing_title_block import load_title_block, title_block_svg
from pdf_utils import save_drawing_svg
from project_documents import DRAWINGS, document_path
from site_plan_annotations import (SITE_PARCELS, SETBACK_PARCELS, METER_SURVEY_POINT,
    SITE_BOUNDARY_COLOR, NN_CONNECTION_COLOR, house_site_data, boundary_setbacks, annotations_svg,
    FOREST_PARCEL, FOREST_REFERENCE_POINTS, forest_reference_edge)
from survey_points import (
    HOUSE_PLACEMENT, SurveyAxes, named_survey_groups, read_survey_groups, read_survey_points,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_CADASTRE = ROOT / "katastr/679453"
DEFAULT_SVG = ROOT / "projekt2/situace.svg"
DEFAULT_PDF = ROOT / document_path("situace")
DRAWING_NUMBER = DRAWINGS["situace"].number
DRAWING_TITLE = DRAWINGS["situace"].title
SURVEY_COLOR = "#2989ad"
HOUSE_COLOR = "#d32222"
HOUSE_FILL = "#f8d2d2"
STREET_BAND_FILL = "#d5edff"
STREET_BAND_WIDTH = 7.0
STREET_BAND_SOUTHWEST_WIDTH = 5.5
LAWN_FILL = "#dcefd5"
LAWN_COLOR = "#75a06a"
LAWN_PARCEL_NUMBERS = ("105", "106/1")
GARDEN_PARCEL_NUMBERS = ("106/1", "103/2")
GARDEN_FILL = "#ead7bb"
GARDEN_COLOR = "#b99b73"
FENCE_LINE_WIDTH = .65  # Millimetres on paper.
WIRE_FENCE_COLOR = "#800080"
MASONRY_FENCE_DESCRIPTION = "Zděné oplocení z cihel ztraceného bednění. Výška 120cm"
STREET_FENCE_END_GAP = 4.0  # Metres along the street frontage at each end.
RETAINING_WALL_COLOR = "#238b35"
RETAINING_WALL_LINE_WIDTH = .65  # Millimetres on paper.
CAR_ASSET = ROOT / "drawings/assets/car-top.svg"
CAR_STREET_CLEARANCE = .20  # Metres from the street edge to each parked car.
CAR_LINE_WIDTH = .12  # Opaque car outlines, millimetres on paper.
PARCEL_LABEL_SIZE = 2.0  # Millimetres on paper.
SURVEY_POINT_LABEL_SIZE = PARCEL_LABEL_SIZE / 2
SURVEY_POINT_LABEL_COLOR = "#d94c9b"
WATER_ROUTES_FILE = ROOT / "situation_water.json"
WATER_LINE_COLOR = "#0066cc"
WATER_LINE_WIDTH = .45  # Millimetres on paper.
WATER_ADJUSTMENT_COLOR = "#66bbee"
WATER_ADJUSTMENT_DESCRIPTION = "Vodovod - tato část vedení bude upravena"
GAS_ROUTES_FILE = ROOT / "situation_gas.json"
GAS_LINE_COLOR = "#d69a00"
GAS_LINE_WIDTH = .45  # Millimetres on paper.
CETIN_ROUTES_FILE = ROOT / "situation_cetin.json"
CETIN_LINE_COLOR = "#cc6600"
CETIN_LINE_WIDTH = .45  # Millimetres on paper.
CETIN_LINE_DASH = "2.4,1,.5,1"
CETIN_DESCRIPTION = "Nadzemní sdělovací vedení, CETIN"
ELECTRIC_SOURCE = ROOT / "katastr/139202/VYJ-ELE/Elektro.dgn"
ELECTRIC_LINE_COLOR = "#e02020"
ELECTRIC_LINE_WIDTH = .45  # Millimetres on paper.
ELECTRIC_OVERHEAD_DASH = "2.4,1.2"
ELECTRIC_DESCRIPTIONS = {"underground": "Podzemní vedení NN", "overhead": "Nadzemní vedení NN"}


@dataclass(frozen=True)
class NorthUpFrame:
    """Rigid metre frame whose positive y follows geographic north at its origin."""

    east: float
    north: float
    north_angle: float

    @classmethod
    def at(cls, east: float, north: float, crs: CRS) -> NorthUpFrame:
        to_geographic = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = to_geographic.transform(east, north, errcheck=True)
        # Invert the same datum operation: an independently selected reverse
        # transformer can choose a different available datum transformation.
        operation = to_geographic.get_last_used_operation()
        south = operation.transform(lon, lat - .0001, direction=TransformDirection.INVERSE, errcheck=True)
        north_point = operation.transform(lon, lat + .0001, direction=TransformDirection.INVERSE, errcheck=True)
        return cls(east, north, atan2(north_point[0] - south[0], north_point[1] - south[1]))

    def to_local(self, east: float, north: float) -> tuple[float, float]:
        dx, dy = east - self.east, north - self.north
        c, s = cos(self.north_angle), sin(self.north_angle)
        return c * dx - s * dy, s * dx + c * dy

    def to_grid(self, x: float, y: float) -> tuple[float, float]:
        c, s = cos(self.north_angle), sin(self.north_angle)
        return self.east + c * x + s * y, self.north - s * x + c * y


def layer_features(directory: Path, name: str, bbox=None):
    """Use each layer's declared encoding, including Czech Windows-1250 labels."""
    with shapefile.Reader(str(directory / f"{name}.shp")) as reader:
        for feature in reader.iterShapeRecords(bbox=bbox):
            yield feature.record.as_dict(), feature.shape


def cadastral_parcel_area(directory, numbers, frame):
    """Join the requested cadastral polygons in the local map frame."""
    ids = {str(record["ID_2"]): record["TEXT_KM"]
           for record, _ in layer_features(directory, "PARCELY_KN_DEF")
           if record["TEXT_KM"] in numbers}
    missing = set(numbers) - set(ids.values())
    if missing:
        raise ValueError(f"Parcels missing from the cadastral data: {sorted(missing)}")
    polygons = [transform(frame.to_local, geometry_shape(feature.__geo_interface__))
                for record, feature in layer_features(directory, "PARCELY_KN_P")
                if str(record["ID_2"]) in ids]
    if not polygons:
        raise ValueError("Requested parcel polygons are missing from the cadastral data")
    return unary_union(polygons)


def load_utility_routes(source, crs):
    """Use saved S-JTSK positions so future picker sessions cannot move the pipes."""
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    if data["crs"] != crs:
        raise ValueError("Utility-route coordinates must use the same CRS as the cadastral map")
    points = {p["id"]: (-p["Y"], -p["X"]) for p in data["points"]}
    if len(points) != len(data["points"]) or not all(isfinite(v) for p in points.values() for v in p):
        raise ValueError("Utility points must have unique IDs and finite survey coordinates")
    adjusted_routes = data.get("adjusted_routes", [])
    if any(ids not in data["routes"] for ids in adjusted_routes):
        raise ValueError("Adjusted utility routes must reference an existing route")
    routes, neighbours = [], {}
    for ids in data["routes"]:
        if len(ids) < 2 or any(i not in points for i in ids):
            raise ValueError("Each utility route must reference at least two saved points")
        routes.append({"point_ids": ids, "grid_points_m": [points[i] for i in ids]})
        if ids in adjusted_routes:
            routes[-1]["to_be_adjusted"] = True
        for a, b in zip(ids, ids[1:]):
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
    junctions = {i: points[i] for i, adjacent in neighbours.items() if len(adjacent) > 2}
    return routes, junctions


def load_electric_routes(source):
    """Read active NN linework from DGN v8 in its native S-JTSK metre coordinates.

    The supplier's DATA-INFO/data_info_ele.pdf identifies levels 21–26 as NN,
    with solid underground lines and dashed overhead lines. Levels 21 and 22
    carry those routes; level 23 is decommissioned and 24–26 contain symbols.
    """
    import ezdgn

    routes = []
    for model in ezdgn.open_document(source).models:
        for entity in model.entities:
            if entity.level not in (21, 22):
                continue
            if entity.dxftype() != "LINE_STRING":
                raise ValueError(f"Unsupported electrical-route geometry: {entity.dxftype()}")
            points = [tuple(vertex.master[:2]) for vertex in entity.data.vertices]
            if len(points) < 2 or not all(isfinite(v) for p in points for v in p):
                raise ValueError("Electrical routes must have at least two finite metre coordinates")
            routes.append({"source_element_id": entity.common.element_id,
                           "source_level": entity.level,
                           "installation": "underground" if entity.level == 21 else "overhead",
                           "grid_points_m": points})
    if not routes:
        raise ValueError(f"No active electrical routes found in {source}")
    return routes


def parcel_arrow_paths(position, rotation, size_factor=1):
    """ČÚZK marker 1033, anchored at bottom centre and rotated CCW from grid north.

    Official QGIS style uses a 3 m square times MERITKO. Marker coordinates
    are from CUZK/1033.svg (310-unit viewport, 300-unit shaft).
    """
    angle = radians(rotation)
    unit = 3 * size_factor / 310

    def point(x, y):
        return (position[0] + unit * (x * cos(angle) - y * sin(angle)),
                position[1] + unit * (x * sin(angle) + y * cos(angle)))

    return ((point(0, 5), point(0, 305)),
            (point(-50, 205), point(0, 305), point(50, 205)))


def survey_point_labels(points, paper_position):
    """Keep small Bpv elevation labels nearby without overlapping other labels."""
    positions = [(p, paper_position(-p.y, -p.x)) for p in points]
    occupied = [Polygon([(x-.45, y-.45), (x+.45, y-.45), (x+.45, y+.45), (x-.45, y+.45)])
                for _, (x, y) in positions]
    for p, (x, y) in positions:
        elevation = f"{p.z:.2f}"
        width = .64 * SURVEY_POINT_LABEL_SIZE * len(elevation)
        candidates = []
        for extra in (0, .6, 1.2, 1.8):
            for dx, dy in ((.6+extra, -.5-extra), (.6+extra, 1.15+extra),
                           (-width-.6-extra, -.5-extra), (-width-.6-extra, 1.15+extra),
                           (-width/2, -.7-extra), (-width/2, 1.4+extra)):
                xx, yy = x+dx, y+dy
                bounds = Polygon([(xx-.1, yy-.85), (xx+width+.1, yy-.85),
                                  (xx+width+.1, yy+.2), (xx-.1, yy+.2)])
                overlap = sum(bounds.intersection(other).area for other in occupied)
                candidates.append((overlap, hypot(dx+width/2, dy-.35), xx, yy, bounds))
        _, _, xx, yy, bounds = min(candidates, key=lambda c: c[:2])
        occupied.append(bounds)
        yield p.number, elevation, xx, yy


def street_band(street, garden_wall, neighbour, house, *, width=STREET_BAND_WIDTH,
                southwest_width=None):
    """Find the house-side enclosure and clip a true parallel street offset.

    Coordinates are local metres, with geographic north along positive y.
    Retain each measured segment and extend only the terminal segments.
    A distant enclosure formed by the extended lines is excluded by requiring
    the selected face to contain the placed house's centre.
    With southwest_width, join the neighbour-side and garden-wall-side offset
    intersections with a straight taper, retaining the other site boundaries.
    """
    if not isfinite(width) or width <= 0:
        raise ValueError("Street band width must be positive and finite")
    if southwest_width is not None and (not isfinite(southwest_width) or southwest_width <= 0):
        raise ValueError("Southwest street band width must be positive and finite")
    vertices = [*street, *garden_wall, *neighbour]
    span = hypot(max(p[0] for p in vertices) - min(p[0] for p in vertices),
                 max(p[1] for p in vertices) - min(p[1] for p in vertices))
    extension = 100 * max(span, width, southwest_width or width)

    def extended(points):
        # Consecutive duplicates do not define a terminal ray.
        points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
        if len(points) < 2:
            raise ValueError("Each site boundary needs at least two distinct points")

        def end(a, b):
            length = hypot(a[0] - b[0], a[1] - b[1])
            return (a[0] + extension * (a[0] - b[0]) / length,
                    a[1] + extension * (a[1] - b[1]) / length)

        return LineString([end(points[0], points[1]), *points, end(points[-1], points[-2])])

    street_line = extended(street)
    garden_line, neighbour_line = extended(garden_wall), extended(neighbour)
    faces = list(polygonize(unary_union([street_line, garden_line, neighbour_line])))
    enclosures = [p for p in faces if p.covers(house.centroid)]
    if len(enclosures) != 1:
        raise ValueError("The extended street, garden wall and neighbour lines must enclose the house centre")
    enclosure = enclosures[0]
    # Positive offset is left of the directed street; choose the south side.
    dx = street[-1][0] - street[0][0]
    if abs(dx) < 1e-9:
        raise ValueError("A north–south street needs an explicit east/west band direction")
    distance = -width if dx > 0 else width
    if southwest_width is None:
        band = enclosure.intersection(street_line.buffer(distance, single_sided=True, join_style="mitre"))
    else:
        def anchor(side, depth):
            offset = street_line.offset_curve(-depth if dx > 0 else depth, join_style="mitre")
            hits = offset.intersection(side)
            candidates = list(hits.geoms) if hasattr(hits, "geoms") else [hits]
            candidates = [p for p in candidates if p.geom_type == "Point"
                          and enclosure.buffer(1e-7).covers(p)]
            if len(candidates) != 1:
                raise ValueError("Each tapered band endpoint must meet its site boundary once")
            return candidates[0].coords[0]

        a, b = anchor(neighbour_line, southwest_width), anchor(garden_line, width)
        length = hypot(b[0] - a[0], b[1] - a[1])
        tx, ty = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = -ty, tx
        # Keep the side of this line containing the street frontage.
        frontage = street_line.intersection(enclosure).representative_point()
        if (frontage.x - a[0]) * nx + (frontage.y - a[1]) * ny < 0:
            nx, ny = -nx, -ny
        left = (a[0] - extension * tx, a[1] - extension * ty)
        right = (b[0] + extension * tx, b[1] + extension * ty)
        north_half = Polygon([left, right,
                              (right[0] + extension * nx, right[1] + extension * ny),
                              (left[0] + extension * nx, left[1] + extension * ny)])
        band = enclosure.intersection(north_half)
    if band.geom_type != "Polygon" or band.is_empty or not band.is_valid:
        raise ValueError("The street offset must form one valid band inside the site enclosure")
    return enclosure, band


def parked_cars(frontage, paved, neighbour, side_fence, *, length, width, gap=STREET_FENCE_END_GAP):
    """Centre the two car axes on the openings and move their bodies inside."""
    if Point(frontage.coords[-1]).distance(neighbour) < Point(frontage.coords[0]).distance(neighbour):
        frontage = LineString(list(frontage.coords)[::-1])
    cars = []
    for index, station in enumerate((gap / 2, frontage.length - gap / 2)):
        opening = frontage.interpolate(station)
        a, b = frontage.interpolate(station - .01), frontage.interpolate(station + .01)
        tangent_length = a.distance(b)
        inward = ((b.y - a.y) / tangent_length, -(b.x - a.x) / tangent_length)
        if not paved.covers(Point(opening.x + .01 * inward[0], opening.y + .01 * inward[1])):
            inward = (-inward[0], -inward[1])
        if index == 0:
            forward = inward
        else:
            a, b = side_fence.coords[0], side_fence.coords[-1]
            forward = ((b[0] - a[0]) / side_fence.length, (b[1] - a[1]) / side_fence.length)
            if sum(u * v for u, v in zip(forward, inward)) < 0:
                forward = (-forward[0], -forward[1])
        right = (forward[1], -forward[0])
        normal_component = sum(u * v for u, v in zip(forward, inward))
        lateral_component = abs(sum(u * v for u, v in zip(right, inward)))
        depth = length / 2 + (width / 2 * lateral_component + CAR_STREET_CLEARANCE) / normal_component
        centre = (opening.x + forward[0] * depth, opening.y + forward[1] * depth)
        footprint = Polygon([(centre[0] + x * right[0] + y * forward[0],
                              centre[1] + x * right[1] + y * forward[1])
                             for x, y in ((-width/2, -length/2), (width/2, -length/2),
                                          (width/2, length/2), (-width/2, length/2))])
        if not paved.covers(footprint):
            raise ValueError(f"Car {index + 1} must fit fully within the paved area")
        cars.append({"centre_local_m": centre, "forward": forward,
                     "opening_centre_local_m": (opening.x, opening.y),
                     "length_m": length, "width_including_mirrors_m": width,
                     "footprint_local_m": footprint.__geo_interface__})
    return cars


def render_situation(*, cadastre=DEFAULT_CADASTRE, points=ROOT / "points.txt",
                     output=DEFAULT_SVG, pdf=DEFAULT_PDF, scale=200):
    cadastre, points, output, pdf = map(Path, (cadastre, points, output, pdf))
    if not isfinite(scale) or scale <= 0:
        raise ValueError("Scale denominator must be positive and finite")
    if output.suffix.lower() != ".svg" or pdf.suffix.lower() != ".pdf":
        raise ValueError("Output paths must end in .svg and .pdf")
    inkscape = shutil.which("inkscape")
    if inkscape is None:
        raise FileNotFoundError("Inkscape is required to export the situation PDF")
    survey = read_survey_points(points)
    groups = read_survey_groups(points)
    from matplotlib.colors import to_hex

    polylines = named_survey_groups(groups)
    if not {"street", "neighbour"} <= polylines.keys():
        raise ValueError("House placement requires named street and neighbour survey polylines")
    house_axes = SurveyAxes.from_polylines(polylines["street"], polylines["neighbour"])
    house_survey_corners = [house_axes.frame.to_survey(*p) for p in HOUSE_PLACEMENT.corners(house_axes)]
    house_grid_corners = [(-y, -x) for y, x in house_survey_corners]
    short_edge = 0 if HOUSE_PLACEMENT.width <= HOUSE_PLACEMENT.depth else 1
    ridge_grid_endpoints = [tuple((house_grid_corners[i][j] + house_grid_corners[(i + 1) % 4][j]) / 2
                                  for j in (0, 1)) for i in (short_edge, short_edge + 2)]
    crs = CRS.from_wkt((cadastre / "PARCELY_KN_P.prj").read_text())
    # Survey Y/X are positive westing/southing; SHP uses negative east/north.
    east = -(min(p.y for p in survey) + max(p.y for p in survey)) / 2
    north = -(min(p.x for p in survey) + max(p.x for p in survey)) / 2
    frame = NorthUpFrame.at(east, north, crs)
    water_routes, water_junctions = load_utility_routes(WATER_ROUTES_FILE, crs.to_string())
    gas_routes, _ = load_utility_routes(GAS_ROUTES_FILE, crs.to_string())
    cetin_routes, _ = load_utility_routes(CETIN_ROUTES_FILE, crs.to_string())
    electric_routes = load_electric_routes(ELECTRIC_SOURCE)
    garden_walls = [g for g in groups if g.color is not None and to_hex(g.color) == "#00ff00"]
    garden_wall = polylines.get("garden_wall")
    if garden_wall is None:
        if len(garden_walls) != 1:
            raise ValueError("Use one green survey polyline or name the stone-wall group garden_wall")
        garden_wall = garden_walls[0]

    def local_line(group):
        return [frame.to_local(-p.y, -p.x) for p in group.points]

    house_polygon = Polygon([frame.to_local(*p) for p in house_grid_corners])
    site = cadastral_parcel_area(cadastre, SITE_PARCELS, frame)
    levels = house_site_data(house_axes, frame)
    neighbouring_boundaries = {number: site.boundary.intersection(
        cadastral_parcel_area(cadastre, (number,), frame).boundary) for number in SETBACK_PARCELS}
    setbacks = boundary_setbacks(house_polygon, neighbouring_boundaries)
    street_corner = Point(list(house_polygon.exterior.coords)[1])  # B, beside parcel 107.
    street_setback = boundary_setbacks(street_corner, {'107': neighbouring_boundaries['107']})[0]
    street_setback.update(corner='B', identifier='setback-107-street', dimension_offset_mm=-8)
    setbacks.append(street_setback)
    survey_by_number = {p.number:p for p in survey}
    forest_points = [Point(frame.to_local(-survey_by_number[n].y,-survey_by_number[n].x))
                     for n in FOREST_REFERENCE_POINTS]
    forest_edge = forest_reference_edge(
        cadastral_parcel_area(cadastre,(FOREST_PARCEL,),frame),forest_points)
    forest_setback = boundary_setbacks(house_polygon,{FOREST_PARCEL:forest_edge})[0]
    forest_setback['identifier']='setback-forest'
    setbacks.append(forest_setback)
    meter_point = next(p for p in survey if p.number == METER_SURVEY_POINT)
    meter = frame.to_local(-meter_point.y, -meter_point.x)
    corners_table = [dict(name=chr(65+i), Y=y, X=x) for i,(y,x) in enumerate(house_survey_corners)]
    enclosure, band = street_band(
        local_line(polylines["street"]), local_line(garden_wall), local_line(polylines["neighbour"]),
        house_polygon, southwest_width=STREET_BAND_SOUTHWEST_WIDTH,
    )
    paved = band.difference(house_polygon)
    lawn = enclosure.difference(unary_union([band, house_polygon]))
    point1 = next((p for p in survey if p.number == "1"), None)
    if point1 is None:
        raise ValueError("The paving/lawn divider requires survey point 1")
    divider_start = frame.to_local(-point1.y, -point1.x)
    divider_end = min(house_polygon.exterior.coords[:-1],
                      key=lambda p: Point(p).distance(Point(divider_start)))
    paving_lawn_divider = LineString([divider_start, divider_end])
    paving_parts = sorted(split(paved, paving_lawn_divider).geoms, key=lambda p: p.area)
    if len(paving_parts) != 2:
        raise ValueError("Point 1 to the nearest house corner must split the paving into two parts")
    converted_lawn, paved = paving_parts
    lawn = unary_union([lawn, converted_lawn])
    # Fences follow the planned surface division; parcel clipping only trims fill.
    wire_fence = paved.boundary.intersection(lawn.boundary)
    lawn = lawn.intersection(cadastral_parcel_area(cadastre, LAWN_PARCEL_NUMBERS, frame))
    garden_parcel = cadastral_parcel_area(cadastre, GARDEN_PARCEL_NUMBERS, frame)
    garden = garden_parcel.difference(unary_union([paved, lawn, house_polygon]))
    retaining_wall = LineString(local_line(garden_wall))
    wire_wall_connector = LineString([divider_start, retaining_wall.coords[0]])
    wire_fence = unary_union([wire_fence, wire_wall_connector])
    street_frontage = paved.boundary.intersection(LineString(local_line(polylines["street"])))
    if street_frontage.geom_type == "MultiLineString":
        street_frontage = linemerge(street_frontage)
    if street_frontage.geom_type != "LineString" or street_frontage.length <= 2 * STREET_FENCE_END_GAP:
        raise ValueError("The paved street frontage must leave room for the fence and both end gaps")
    street_fence = substring(street_frontage, STREET_FENCE_END_GAP,
                             street_frontage.length - STREET_FENCE_END_GAP)
    fence = unary_union([wire_fence, street_fence])
    wire_fence_lines = list(wire_fence.geoms) if wire_fence.geom_type == "MultiLineString" else [wire_fence]
    car_asset = ET.parse(CAR_ASSET).getroot()
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    car_group = car_asset.find('{http://www.w3.org/2000/svg}g')
    car_group.set("stroke-width", f'{CAR_LINE_WIDTH * float(car_asset.get("data-units-per-metre")) * scale / 1000:g}')
    car_symbol = ET.tostring(car_group, encoding="unicode")
    cars = parked_cars(street_frontage, paved, LineString(local_line(polylines["neighbour"])),
                       paving_lawn_divider, length=float(car_asset.get("data-body-length-m")),
                       width=float(car_asset.get("data-maximum-width-m")))
    # Surveyed frontage and cadastral edges differ slightly. Keep proposed
    # paving and fencing within the confirmed extent of the investor's land.
    paved = paved.intersection(site)
    wire_fence = wire_fence.intersection(site)
    wire_fence_lines = [line for line in getattr(wire_fence, "geoms", (wire_fence,))
                        if line.geom_type == "LineString"]
    fence = unary_union([wire_fence, street_fence])
    # C.3 shows the site and immediate neighbours at 1:200. Distant surveyed
    # points remain in the dataset and the wider-context sheet, outside this viewport.
    extent_points = [*site.envelope.exterior.coords, *house_polygon.exterior.coords]
    centre = ((site.bounds[0]+site.bounds[2])/2, (site.bounds[1]+site.bounds[3])/2)

    # Physical A3 landscape layout. Keep the shared project title block clear.
    page_w, page_h = 420, 297
    map_x, map_y, map_w, map_h = 10, 25, 306, 257
    mm_per_m = 1000 / scale
    half_w, half_h = map_w / mm_per_m / 2, map_h / mm_per_m / 2
    bounds = (centre[0] - half_w, centre[1] - half_h,
              centre[0] + half_w, centre[1] + half_h)
    if any(not (bounds[0] + 5 <= x <= bounds[2] - 5 and
                bounds[1] + 5 <= y <= bounds[3] - 5) for x, y in extent_points):
        raise ValueError("The site needs 5 m of map margin; use a larger sheet rather than reducing the coordination scale")
    corners = [frame.to_grid(x, y) for x in (bounds[0], bounds[2])
               for y in (bounds[1], bounds[3])]
    grid_bbox = (min(p[0] for p in corners), min(p[1] for p in corners),
                 max(p[0] for p in corners), max(p[1] for p in corners))

    def paper_position(east, north):
        x, y = frame.to_local(east, north)
        return map_x + (x - bounds[0]) * mm_per_m, map_y + (bounds[3] - y) * mm_per_m

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{page_w}mm" '
           f'height="{page_h}mm" viewBox="0 0 {page_w} {page_h}">',
           '<rect width="420" height="297" fill="white"/>',
           '<style>text{font-family:DejaVu Sans,sans-serif;fill:#222;stroke:none}'
           '.map-label{paint-order:stroke;stroke:white;stroke-width:.65;stroke-linejoin:round}'
           f'.survey-point-label{{fill:{SURVEY_POINT_LABEL_COLOR};paint-order:stroke;stroke:white;stroke-width:.15}}'
           'path{stroke-linejoin:round;stroke-linecap:round}</style>',
           f'<defs><clipPath id="map-clip"><rect x="{map_x}" y="{map_y}" '
           f'width="{map_w}" height="{map_h}"/></clipPath>{car_symbol}'
           '<marker id="site-arrow" markerUnits="userSpaceOnUse" viewBox="0 0 4 3" refX="4" refY="1.5" markerWidth="4" markerHeight="3" orient="auto"><path d="M0,0L4,1.5L0,3Z" fill="#222"/></marker></defs>']

    def text(x, y, value, size=2.3, *, anchor="start", bold=False, css="", attrs=""):
        svg.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" '
                   f'text-anchor="{anchor}" font-weight="{"bold" if bold else "normal"}" '
                   f'class="{css}" {attrs}>{escape(str(value))}</text>')

    def path(vertices, *, close=False):
        positions = [paper_position(*p) for p in vertices]
        if not positions:
            return ""
        return "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in positions) + (" Z" if close else "")

    def cross(x, y, radius=.42):
        return f"M{x-radius:.3f},{y:.3f}h{2*radius:g} M{x:.3f},{y-radius:.3f}v{2*radius:g}"

    def polygon_path(geometry):
        polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else (geometry,)
        return " ".join(path([frame.to_grid(*p) for p in ring.coords], close=True)
                        for polygon in polygons if not polygon.is_empty
                        for ring in (polygon.exterior, *polygon.interiors))

    text(210, 14, f"{DRAWING_NUMBER} {DRAWING_TITLE}  1:{scale:g}", 4.3,
         anchor="middle", bold=True, css="drawing-title")
    svg.append('<g clip-path="url(#map-clip)">')
    counts = {}
    demolition = []
    for name, fill, stroke, width in (
        ("PARCELY_KN_P", "none", "#454545", .18),
        ("DALSI_PRVKY_MAPY_L", "none", "#909090", .13),
        ("BUDOVY_P", "#e5e5e5", "#202020", .25),
    ):
        count = 0
        svg.append(f'<g id="{name}" fill="{fill}" stroke="{stroke}" stroke-width="{width}">')
        for record, shape in layer_features(cadastre, name, grid_bbox):
            if not shape.points:
                continue
            closed = shape.shapeType == shapefile.POLYGON
            if name == "BUDOVY_P":
                building = transform(frame.to_local, geometry_shape(shape.__geo_interface__))
                if building.intersection(house_polygon).area > 1:
                    demolition.append(building)
            indices = [*shape.parts, len(shape.points)]
            d = " ".join(path(shape.points[a:b], close=closed) for a, b in zip(indices, indices[1:]))
            svg.append(f'<path d="{d}" fill-rule="evenodd"><title>'
                       f'{escape({"PARCELY_KN_P": "Hranice parcely", "DALSI_PRVKY_MAPY_L": "Katastrální detail", "BUDOVY_P": "Stávající stavba"}[name])}</title></path>')
            count += 1
        svg.append('</g>')
        counts[name] = count
    svg.append(f'<path id="garden" d="{polygon_path(garden)}" fill-rule="evenodd" '
               f'fill="{GARDEN_FILL}" fill-opacity=".8" stroke="{GARDEN_COLOR}" stroke-width=".2">'
               f'<title>Zahrada – nezbarvené části parcel {", ".join(GARDEN_PARCEL_NUMBERS)}</title></path>')
    svg.append(f'<path id="lawn" d="{polygon_path(lawn)}" fill-rule="evenodd" '
               f'fill="{LAWN_FILL}" fill-opacity=".8" stroke="{LAWN_COLOR}" stroke-width=".2">'
               '<title>Trávník</title></path>')
    svg.append(f'<path id="street-band" d="{polygon_path(paved)}" fill-rule="evenodd" '
               f'fill="{STREET_BAND_FILL}" fill-opacity=".8" stroke="{SURVEY_COLOR}" stroke-width=".2">'
               f'<title>Zpevněné plochy: pás {STREET_BAND_SOUTHWEST_WIDTH:g}–{STREET_BAND_WIDTH:g} m '
               'od ulice mimo půdorys domu</title></path>')
    for i,building in enumerate(demolition):
        svg.append(f'<path id="existing-house-for-removal-{i}" d="{polygon_path(building)}" fill="none" stroke="#666" stroke-width=".35" stroke-dasharray="1,.6"/>')
        x0,y0,x1,y1=building.bounds
        for start,end in (((x0,y0),(x1,y1)),((x0,y1),(x1,y0))):
            mark=LineString([start,end]).intersection(building)
            segments=list(mark.geoms) if mark.geom_type=='MultiLineString' else [mark]
            for segment in segments:
                svg.append(f'<path d="{path([frame.to_grid(*p) for p in segment.coords])}" fill="none" stroke="#666" stroke-width=".2"/>')
    svg.append(f'<path id="survey-house-fill" d="{path(house_grid_corners, close=True)}" '
               f'fill="{HOUSE_FILL}" fill-opacity=".8" stroke="none"/>')
    svg.append('<g id="parcel-label-leaders" fill="none" stroke="#202020" stroke-width=".13">')
    leader_count = 0
    for record, shape in layer_features(cadastre, "PARCELY_KN_L", grid_bbox):
        if str(record["TYPPPD_KOD"]) != "1032":
            continue
        indices = [*shape.parts, len(shape.points)]
        d = " ".join(path(shape.points[a:b]) for a, b in zip(indices, indices[1:]))
        svg.append(f'<path id="parcel-leader-{record["ID"]}" d="{d}">'
                   '<title>Vynášecí čára parcelního čísla</title></path>')
        leader_count += 1
    svg.append('</g>')
    counts["PARCELY_KN_L"] = leader_count
    svg.append('<g id="parcel-label-arrows" fill="none" stroke="#202020" stroke-width=".13">')
    parcel_arrows = []
    for record, shape in layer_features(cadastre, "PARCELY_KN_B", grid_bbox):
        if str(record["TYPPPD_KOD"]) != "1033" or not shape.points:
            continue
        shaft, head = parcel_arrow_paths(shape.points[0], float(record["ROTACE"] or 0),
                                         float(record["MERITKO"] or 1))
        svg.append(f'<path id="parcel-arrow-{record["ID"]}" d="{path(shaft)} {path(head)}">'
                   '<title>Šipka parcelního čísla</title></path>')
        parcel_arrows.append({"parcel_id": str(record["ID_2"]), "source_id": str(record["ID"]),
                              "rotation_degrees": record["ROTACE"],
                              "shaft_grid_m": shaft, "head_grid_m": head})
    svg.append('</g>')
    counts["PARCELY_KN_B_arrows"] = len(parcel_arrows)
    for name, size in (("PARCELY_KN_T", PARCEL_LABEL_SIZE), ("BUDOVY_DEF", 1.75), ("DALSI_PRVKY_MAPY_T", 2.1)):
        svg.append(f'<g id="{name}">')
        for record, shape in layer_features(cadastre, name, grid_bbox):
            if not shape.points:
                continue
            x, y = paper_position(*shape.points[0])
            if map_x + 3 < x < map_x + map_w - 3 and map_y + 3 < y < map_y + map_h - 3:
                if name == "PARCELY_KN_T":
                    reference = record.get("VZ_BOD") or "BC"
                    anchor = {"L": "start", "C": "middle", "R": "end"}[reference[1]]
                    baseline = {"T": "text-before-edge", "C": "central", "B": "text-after-edge"}[reference[0]]
                    angle = -float(record.get("ROTACE") or 0) - degrees(frame.north_angle)
                    text(x, y, record["TEXT_KM"], size, anchor=anchor, css="map-label",
                         attrs=f'id="parcel-label-{record["ID"]}" dominant-baseline="{baseline}" '
                               f'transform="rotate({angle:g} {x:g} {y:g})"')
                else:
                    text(x, y, record["TEXT_KM"], size, anchor="middle", css="map-label")
        svg.append('</g>')
    svg.append(f'<g id="survey-points" stroke="{SURVEY_COLOR}" stroke-width=".2" fill="none">')
    for p in survey:
        x, y = paper_position(-p.y, -p.x)
        svg.append(f'<path id="survey-point-{p.number}" d="{cross(x,y)}"><title>'
                   f'{escape(f"Zaměřená výška {p.z:.2f} m Bpv; S-JTSK: Y={p.y:.2f}, X={p.x:.2f}")}'
                   '</title></path>')
    svg.append('</g>')
    svg.append(f'<g id="survey-house-footprint" fill="none" stroke="{HOUSE_COLOR}" stroke-width=".55">'
               f'<path d="{path(house_grid_corners, close=True)}"><title>'
               f'{escape(f"Navrhovaný dům {HOUSE_PLACEMENT.width:g} × {HOUSE_PLACEMENT.depth:g} m")}'
               '</title></path></g>')
    svg.append(f'<path id="house-ridge" d="{path(ridge_grid_endpoints)}" fill="none" '
               f'stroke="{HOUSE_COLOR}" stroke-width=".35"><title>Hřeben střechy</title></path>')
    wire_fence_path = " ".join(path([frame.to_grid(*p) for p in line.coords]) for line in wire_fence_lines)
    svg.append(f'<path id="wire-fence" d="{wire_fence_path}" fill="none" stroke="{WIRE_FENCE_COLOR}" '
               f'stroke-width="{FENCE_LINE_WIDTH:g}"><title>Drátěný plot</title></path>')
    svg.append(f'<path id="street-fence" d="{path([frame.to_grid(*p) for p in street_fence.coords])}" '
               f'fill="none" stroke="black" stroke-width="{FENCE_LINE_WIDTH:g}">'
               f'<title>{escape(MASONRY_FENCE_DESCRIPTION)}</title></path>')
    svg.append(f'<path id="existing-retaining-wall" '
               f'd="{path([frame.to_grid(*p) for p in retaining_wall.coords])}" '
               f'fill="none" stroke="{RETAINING_WALL_COLOR}" stroke-width="{RETAINING_WALL_LINE_WIDTH:g}">'
               '<title>Stávající opěrná stěna</title></path>')
    for i, car in enumerate(cars, 1):
        x, y = paper_position(*frame.to_grid(*car["centre_local_m"]))
        ux, uy = car["forward"]
        k = mm_per_m / float(car_asset.get("data-units-per-metre"))
        svg.append(f'<use id="parked-car-{i}" xlink:href="#car-top" '
                   f'transform="matrix({uy*k:.12g} {ux*k:.12g} {-ux*k:.12g} {uy*k:.12g} {x:.12g} {y:.12g})">'
                   f'<title>Osobní automobil {i}, délka {car["length_m"]:g} m</title></use>')
    svg.append(f'<g id="water-routes" fill="none" stroke="{WATER_LINE_COLOR}" '
               f'stroke-width="{WATER_LINE_WIDTH:g}">')
    for route in water_routes:
        ids = "-".join(str(i) for i in route["point_ids"])
        adjusted = route.get("to_be_adjusted", False)
        color = WATER_ADJUSTMENT_COLOR if adjusted else WATER_LINE_COLOR
        description = WATER_ADJUSTMENT_DESCRIPTION if adjusted else "Vodovod"
        svg.append(f'<path id="water-route-{ids}" d="{path(route["grid_points_m"])}" stroke="{color}">'
                   f'<title>{escape(description)}</title></path>')
    for number, position in water_junctions.items():
        x, y = paper_position(*position)
        svg.append(f'<circle id="water-junction-{number}" cx="{x:g}" cy="{y:g}" '
                   f'r=".5" fill="{WATER_LINE_COLOR}" stroke="none"/>')
    svg.append('</g>')
    svg.append(f'<g id="gas-routes" fill="none" stroke="{GAS_LINE_COLOR}" '
               f'stroke-width="{GAS_LINE_WIDTH:g}">')
    for route in gas_routes:
        ids = "-".join(str(i) for i in route["point_ids"])
        svg.append(f'<path id="gas-route-{ids}" d="{path(route["grid_points_m"])}">'
                   '<title>Plynovod</title></path>')
    svg.append('</g>')
    svg.append(f'<g id="cetin-routes" fill="none" stroke="{CETIN_LINE_COLOR}" '
               f'stroke-width="{CETIN_LINE_WIDTH:g}" stroke-dasharray="{CETIN_LINE_DASH}">')
    for route in cetin_routes:
        ids = "-".join(str(i) for i in route["point_ids"])
        svg.append(f'<path id="cetin-route-{ids}" d="{path(route["grid_points_m"])}">'
                   f'<title>{escape(CETIN_DESCRIPTION)}</title></path>')
    svg.append('</g>')
    svg.append(f'<g id="electric-routes" fill="none" stroke="{ELECTRIC_LINE_COLOR}" '
               f'stroke-width="{ELECTRIC_LINE_WIDTH:g}">')
    for installation, description in ELECTRIC_DESCRIPTIONS.items():
        pattern = f' stroke-dasharray="{ELECTRIC_OVERHEAD_DASH}"' if installation == "overhead" else ""
        svg.append(f'<g id="electric-{installation}"{pattern}>')
        for route in electric_routes:
            if route["installation"] != installation:
                continue
            svg.append(f'<path id="electric-route-{route["source_element_id"]}" '
                       f'd="{path(route["grid_points_m"])}"><title>{escape(description)}</title></path>')
        svg.append('</g>')
    svg.append('</g>')
    svg.append('<g id="survey-point-numbers">')
    for number, elevation, x, y in survey_point_labels(survey, paper_position):
        text(x, y, elevation, SURVEY_POINT_LABEL_SIZE, css="survey-point-label",
             attrs=f'id="survey-point-number-{number}"')
    svg.append('</g>')
    def paper_local(x, y):
        return map_x+(x-bounds[0])*mm_per_m, map_y+(bounds[3]-y)*mm_per_m

    annotations, site_design = annotations_svg(
        house=house_polygon, site=site, setbacks=setbacks, retaining_wall=retaining_wall,
        levels=levels, corners=corners_table, meter=meter, paper_local=paper_local,
        cars=cars, street_frontage=street_frontage, forest_edge=forest_edge,
    )
    svg.append(annotations)
    svg.append('</g>')
    svg.append(f'<rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" '
               'fill="none" stroke="#333" stroke-width=".25"/>')

    # Compact right-hand column leaves room for setting-out data and the title block.
    territory = next(layer_features(cadastre, "KATASTRALNI_UZEMI_DEF"))[0]
    text(328, 28, f'k. ú. {territory["TEXT_KM"]}', 2.1, bold=True)
    text(328, 33, f'{territory["KOD"]} | S-JTSK / Bpv', 1.8)
    text(403, 28, "S", 3, anchor="middle", bold=True)
    svg.append('<path d="M403,43V32 M403,32L401,37L403,35L405,37Z" fill="black" stroke="black" stroke-width=".25"/>')
    text(328, 41, "LEGENDA", 2.3, bold=True)
    legend_y = 47

    def legend_row(label, *, fill=None, stroke="#202020", width=.2, sample=None, sample_id=None, dasharray=None):
        nonlocal legend_y
        identifier = f' id="{sample_id}"' if sample_id else ""
        if sample == "point":
            svg.append(f'<path d="{cross(333,legend_y)}" stroke="{stroke}" stroke-width="{width:g}"/>')
        elif sample == "access":
            svg.append(f'<path d="M329,{legend_y:g}H338" fill="none" stroke="{stroke}" stroke-width="{width:g}" marker-end="url(#site-arrow)"/>')
        elif fill is not None:
            svg.append(f'<rect{identifier} x="329" y="{legend_y-1.5:g}" width="9" height="3" fill="{fill}" stroke="{stroke}" stroke-width="{width:g}"/>')
        else:
            pattern = f' stroke-dasharray="{dasharray}"' if dasharray else ""
            svg.append(f'<path{identifier} d="M329,{legend_y:g}H338" fill="none" stroke="{stroke}" stroke-width="{width:g}"{pattern}/>')
        lines = (label,) if isinstance(label, str) else label
        for i,line in enumerate(lines):
            text(341, legend_y+.7+2.7*i, line, 1.8)
        legend_y += 4.3+2.7*(len(lines)-1)

    legend_row("Hranice parcel", stroke="#454545", width=.18)
    legend_row("Stávající budovy", fill="#e5e5e5", width=.25)
    legend_row("Zaměřené body / výšky Bpv", sample="point", stroke=SURVEY_COLOR)
    house_area_text = f"{house_polygon.area:.2f}".replace(".", ",")
    legend_row(f"Navržený RD, plocha {house_area_text} m²", fill=HOUSE_FILL, stroke=HOUSE_COLOR, width=.55)
    paved_area_text = f"{paved.area:.2f}".replace(".", ",")
    legend_row(f"Zpevněné plochy, {paved_area_text} m²", fill=STREET_BAND_FILL, stroke=SURVEY_COLOR)
    legend_row("Trávník", fill=LAWN_FILL, stroke=LAWN_COLOR)
    legend_row("Zahrada", fill=GARDEN_FILL, stroke=GARDEN_COLOR)
    legend_row(("Zděné oplocení z cihel ztraceného bednění", "Výška 1,20 m"), stroke="black", width=FENCE_LINE_WIDTH, sample_id="street-fence-legend")
    legend_row("Drátěný plot", stroke=WIRE_FENCE_COLOR, width=FENCE_LINE_WIDTH, sample_id="wire-fence-legend")
    legend_row("Stávající opěrná stěna", stroke=RETAINING_WALL_COLOR, width=RETAINING_WALL_LINE_WIDTH, sample_id="retaining-wall-legend")
    legend_row("Vodovod – stávající vedení", stroke=WATER_LINE_COLOR, width=WATER_LINE_WIDTH, sample_id="water-legend")
    if any(route.get("to_be_adjusted") for route in water_routes):
        legend_row("Vodovod – upravovaná část", stroke=WATER_ADJUSTMENT_COLOR, width=WATER_LINE_WIDTH, sample_id="water-adjustment-legend")
    legend_row("Plynovod – stávající vedení", stroke=GAS_LINE_COLOR, width=GAS_LINE_WIDTH, sample_id="gas-legend")
    legend_row("CETIN – nadzemní vedení", stroke=CETIN_LINE_COLOR, width=CETIN_LINE_WIDTH, sample_id="cetin-legend", dasharray=CETIN_LINE_DASH)
    for installation,description in ELECTRIC_DESCRIPTIONS.items():
        legend_row(description+" – stávající", stroke=ELECTRIC_LINE_COLOR, width=ELECTRIC_LINE_WIDTH, sample_id=f"electric-{installation}-legend", dasharray=ELECTRIC_OVERHEAD_DASH if installation=="overhead" else None)
    legend_row("NN od ER – schematická trasa", stroke=NN_CONNECTION_COLOR, width=.5, sample_id="nn-connection-legend", dasharray="2,.8")
    legend_row("Hranice řešeného území / staveniště", stroke=SITE_BOUNDARY_COLOR, width=.45, dasharray="2,.8")
    legend_row("Stavba k odstranění – samostatné povolení", stroke="#666", width=.35, dasharray="1,.6")
    legend_row("Stávající sjezdy – zachovány", stroke="#222", width=.4, sample="access")
    if legend_y > 137:
        raise ValueError("The coordination legend overlaps the setting-out data")
    text(328, 143, "VÝŠKOVÉ OSAZENÍ", 2.1, bold=True)
    text(328, 148, f"±0,000 = {levels['floor_elevation_bpv']:.3f} m Bpv", 2.1)
    text(328, 152, f"Hřeben: {levels['ridge_elevation_bpv']:.3f} m Bpv", 1.9)
    text(328, 156, f"Nejvyšší bod – komín: {levels['chimney_elevation_bpv']:.3f} m Bpv", 1.9)
    text(328, 164, "ROHY FASÁDY – S-JTSK [m]", 2.1, bold=True)
    for i,row in enumerate(corners_table):
        text(328, 169+4*i, f"{row['name']}  Y {row['Y']:.3f}   X {row['X']:.3f}", 1.8)
    text(328, 188, "Kóty v metrech. ÚT dle architektonických řezů.", 1.65)
    text(328, 193, "Staveniště bez záboru cizích pozemků.", 1.65)
    text(328, 198, "ČOV a dešťové hospodářství: samostatný návrh.", 1.65)
    text(328, 203, "Požární řešení a odstupy: viz samostatné PBŘ.", 1.65)
    text(328, 208, "Plynová přípojka se nenavrhuje.", 1.65)
    text(328, 213, "Přívody médií dle podmínek správců sítí.", 1.65)
    for a,b in ((0,2),(2,5),(5,10)):
        svg.append(f'<rect x="{328+a*mm_per_m:g}" y="218" width="{(b-a)*mm_per_m:g}" height="2" fill="{"black" if a!=2 else "white"}" stroke="black" stroke-width=".18"/>')
    for distance in (0,2,5,10):
        text(328+distance*mm_per_m,225,str(distance),1.8,anchor="middle")
    text(332+10*mm_per_m,225,"m",1.8)

    settings = load_title_block(output)
    if settings is not None:
        svg.append(title_block_svg(settings, filename=f"{DRAWING_NUMBER}. {DRAWING_TITLE}.pdf",
                                   scale=f"1:{scale:g}", paper="A3", x=330, y=228))
    metadata = {"coordinate_system": crs.to_string(), "north": "geographic",
                "frame": asdict(frame), "scale": scale, "paper_mm": [page_w, page_h],
                "map_bounds_local_m": bounds, "map_rect_mm": [map_x, map_y, map_w, map_h],
                "cadastre": str(cadastre), "survey": str(points), "feature_counts": counts,
                "site_design": site_design, "site_parcels": SITE_PARCELS,
                "demolition_buildings_local_m": [p.__geo_interface__ for p in demolition],
                "site_boundary_local_m": site.__geo_interface__,
                "deferred_design": ["ČOV", "dešťové hospodářství"],
                "external_reports": {"PBŘ": "externí zpracovatel", "PENB": "externí zpracovatel"},
                "house": {**asdict(HOUSE_PLACEMENT), "survey_corners": house_survey_corners,
                          "area_m2": house_polygon.area,
                          "ridge_geometry_local_m": LineString([frame.to_local(*p) for p in ridge_grid_endpoints]).__geo_interface__,
                          "placement_source": "survey_points.HOUSE_PLACEMENT"},
                "street_band": {"southwest_width_m": STREET_BAND_SOUTHWEST_WIDTH,
                                "northeast_width_m": STREET_BAND_WIDTH, "taper": "straight", "side": "south",
                                "area_m2": band.area, "local_corners": list(band.exterior.coords),
                                "enclosure_local_corners": list(enclosure.exterior.coords)},
                "surfaces": {"paved": {"area_m2": paved.area, "geometry_local_m": paved.__geo_interface__},
                             "lawn": {"area_m2": lawn.area, "geometry_local_m": lawn.__geo_interface__,
                                      "parcel_numbers": LAWN_PARCEL_NUMBERS},
                             "garden": {"area_m2": garden.area, "geometry_local_m": garden.__geo_interface__,
                                        "parcel_numbers": GARDEN_PARCEL_NUMBERS}},
                "paving_lawn_divider": {"survey_point": "1", "local_endpoints": list(paving_lawn_divider.coords),
                                        "converted_to_lawn_m2": converted_lawn.area},
                "fence": {"geometry_local_m": fence.__geo_interface__, "length_m": fence.length,
                          "wire_geometry_local_m": wire_fence.__geo_interface__,
                          "wall_connector_local_m": wire_wall_connector.__geo_interface__,
                          "street_geometry_local_m": street_fence.__geo_interface__,
                          "street_frontage_local_m": street_frontage.__geo_interface__,
                          "street_end_gap_m": STREET_FENCE_END_GAP},
                "retaining_wall": {"geometry_local_m": retaining_wall.__geo_interface__},
                "cars": cars,
                "parcel_arrows": parcel_arrows,
                "water_routes": water_routes,
                "gas_routes": gas_routes,
                "cetin_routes": cetin_routes,
                "electric_source": str(ELECTRIC_SOURCE),
                "electric_routes": electric_routes,
                "points": [asdict(p) for p in survey]}
    svg.append('<metadata id="situation-data">' + escape(json.dumps(metadata, ensure_ascii=False)) + '</metadata>')
    svg.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(svg) + "\n", encoding="utf-8")
    sheet_path = save_drawing_svg(output, pdf)
    with TemporaryDirectory(prefix=".situace-pdf-", dir=pdf.parent) as directory:
        temporary_pdf = Path(directory) / pdf.name
        subprocess.run([inkscape, str(sheet_path), f"--export-filename={temporary_pdf}",
                        "--export-type=pdf", "--export-area-page", "--batch-process"], check=True)
        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise RuntimeError("Inkscape did not create the situation PDF")
        temporary_pdf.replace(pdf)
    print(f"Situation: {pdf} (A3 landscape, 1:{scale:g})")
    print(f"Map area: {map_w/mm_per_m:g} × {map_h/mm_per_m:g} m; {len(survey)} survey points")
    print(f"Geographic north: {degrees(frame.north_angle):.6f}° east of grid north")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cadastre", type=Path, default=DEFAULT_CADASTRE)
    parser.add_argument("--points", type=Path, default=ROOT / "points.txt")
    parser.add_argument("--output", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--scale", type=float, default=200, help="Scale denominator; default 200 (C.3)")
    render_situation(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
