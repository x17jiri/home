"""Project a roof-local SVG tile pattern onto Bonsai's visible roof surfaces.

Only existing SHAPELY surface paths receive hatching. Tessellated top faces
provide a clip, never a hull or replacement fill, so side faces, roof openings
and Bonsai's occlusion/depth ordering remain intact.
"""

from pathlib import Path
from math import isfinite
from html import escape
import json
import re
import xml.etree.ElementTree as ET

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


_IFC = "{http://www.ifcopenshell.org/ns}"
_ATTRS = re.compile(r'([\w:-]+)="([^"]*)"')
_DEFS_ID = "roof-tile-pattern-defs"
_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"


def _positive(value, name):
    value = float(value)
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def _front_part(region, difference):
    """Clip an overlap to the half-plane where another face is nearer."""
    a, b, c = difference
    if abs(a) + abs(b) < 1e-10:
        return region if c > 1e-7 else None
    x0, y0, x1, y1 = region.bounds
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    clipped = []
    for p, q in zip(corners, (*corners[1:], corners[0])):
        p, q = np.array(p), np.array(q)
        fp, fq = a*p[0] + b*p[1] + c - 1e-7, a*q[0] + b*q[1] + c - 1e-7
        if fp >= 0:
            clipped.append(p)
        if (fp >= 0) != (fq >= 0):
            clipped.append(p + fp/(fp-fq)*(q-p))
    if len(clipped) < 3:
        return None
    return region.intersection(Polygon(clipped))


def _contours(region):
    """SVG contours for a real projected face, including openings."""
    polygons = [region] if region.geom_type == "Polygon" else region.geoms
    return " ".join(
        "M " + " L ".join(f"{x:.9g},{y:.9g}" for x, y in ring.coords) + " Z"
        for polygon in polygons if polygon.geom_type == "Polygon"
        for ring in (polygon.exterior, *polygon.interiors)
    )


def _surface_region(data):
    """Read Bonsai's absolute polygon contours, respecting even-odd holes."""
    if re.sub(_NUMBER, "", data).strip(" MLZ,\t\r\n"):
        return None
    region = None
    for ring in re.findall(r"M([^MZ]*)Z", data):
        values = [float(v) for v in re.findall(_NUMBER, ring)]
        if len(values) < 6 or len(values) % 2:
            return None
        polygon = Polygon(np.asarray(values).reshape(-1, 2))
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        region = polygon if region is None else region.symmetric_difference(polygon)
    return region


def _glyph_lines(body):
    """Flatten the outline template's absolute M/L/C/Z paths in tile units."""
    lines = []
    for match in re.finditer(r'<path\b(?P<attrs>[^>]*)/>', body):
        data = dict(_ATTRS.findall(match["attrs"]))["d"]
        if re.sub(_NUMBER, "", data).strip(" MLCZ,\t\r\n"):
            raise ValueError("roof tile glyph supports absolute M, L, C and Z commands")
        tokens = re.findall(rf"[MLCZ]|{_NUMBER}", data)
        points, command, index = [], None, 0
        while index < len(tokens):
            if tokens[index] in {"M", "L", "C", "Z"}:
                command = tokens[index]
                index += 1
            if command == "Z":
                if points:
                    points.append(points[0])
                    lines.append(np.asarray(points))
                points, command = [], None
                continue
            count = 6 if command == "C" else 2
            values = np.asarray([float(v) for v in tokens[index:index+count]]).reshape(-1, 2)
            if command == "M":
                if len(points) >= 2:
                    lines.append(np.asarray(points))
                points = [values[0]]
                command = "L"
            elif command == "L":
                points.append(values[0])
            elif command == "C":
                start, a, b, end = points[-1], *values
                for t in np.linspace(0, 1, 25)[1:]:
                    points.append((1-t)**3*start + 3*(1-t)**2*t*a + 3*(1-t)*t*t*b + t**3*end)
            index += count
        if len(points) >= 2:
            lines.append(np.asarray(points))
    if not lines:
        raise ValueError("roof tile pattern requires outline paths")
    return lines


def _printed_outline(lines, u, v, stroke, background):
    """Bake a fixed paper-width stroke before mapping back to pattern units.

    SVG vector-effect inside transformed patterns differs between Inkscape's
    raster and PDF backends. Filled stroke outlines avoid that discrepancy.
    """
    basis = np.column_stack((u, v))
    outlines = unary_union([LineString(points @ basis.T).buffer(stroke / 2, cap_style=2)
                            for points in lines])
    inverse = np.linalg.inv(basis)
    local = affine_transform(outlines, (*inverse[0], *inverse[1], 0, 0))
    return (f'<rect width="1" height="1" fill="{escape(background, quote=True)}"/>'
            f'<path d="{_contours(local)}" fill="black" stroke="none"/>')


def add_roof_tile_patterns(svg_path, model):
    """Hatch projected tile top faces in roof coordinates; return surface count.

    Requires GlobalId surface metadata and the ``roof-tiles`` SVG pattern.
    Tile dimensions use model metres (BBIM_RoofTilePattern); the asset's
    defaults and printed line width use millimetres. Work on the exported IFC
    placements/meshes, not cached roof-plane points, to respect X mirroring.
    Closed tile surfaces use the template background as a solid base; only
    top faces receive the pattern. Re-running is a no-op. Section cuts and
    open projection paths are untouched.
    """
    path = Path(svg_path)
    svg = path.read_text(encoding="utf-8")
    if f'id="{_DEFS_ID}"' in svg:
        return 0
    template = re.search(r'<pattern\b(?P<attrs>[^>]*\bid="roof-tiles"[^>]*)>(?P<body>.*?)</pattern>',
                         svg, re.DOTALL)
    if template is None:
        return 0
    root = ET.fromstring(svg)
    sections = [e for e in root.iter() if e.get(_IFC + "plane") and e.get(_IFC + "matrix3")]
    # The pass runs before sheet composition: a render has exactly one camera.
    if len(sections) != 1:
        return 0
    section = sections[0]
    plane = np.array(json.loads(section.get(_IFC + "plane")), dtype=float)
    matrix = np.array(json.loads(section.get(_IFC + "matrix3")), dtype=float)
    if plane.shape != (4, 4) or matrix.shape != (3, 3) or not np.isfinite(plane).all() or not np.isfinite(matrix).all():
        raise ValueError("roof tile patterns require finite SVG camera matrices")
    to_camera = np.linalg.inv(plane)
    to_svg = matrix @ np.diag((1., -1., 1.)) @ to_camera[[0, 1, 3], :]
    camera_normal = plane[:3, 2] / np.linalg.norm(plane[:3, 2])
    frame_width = re.fullmatch(r"\s*([0-9.eE+-]+)mm\s*", root.get("width", ""))
    if frame_width is None:
        raise ValueError("roof tile patterns require an SVG width in millimetres")
    view_box = [float(v) for v in re.split(r"[,\s]+", root.get("viewBox", "").strip())]
    if len(view_box) != 4:
        raise ValueError("roof tile patterns require an SVG viewBox")
    units_per_mm = _positive(view_box[2], "viewBox width") / _positive(frame_width[1], "SVG width")
    attrs = dict(_ATTRS.findall(template["attrs"]))
    default_width = _positive(attrs.get("data-tile-width-mm", 300), "tile width") / 1000
    default_course = _positive(attrs.get("data-course-mm", 320), "tile course") / 1000
    stroke = _positive(attrs.get("data-line-width-mm", .06), "tile line width") * units_per_mm
    glyph_lines = _glyph_lines(template["body"])
    background_rect = re.search(r'<rect\b([^>]*)>', template["body"])
    background_attrs = dict(_ATTRS.findall(background_rect[1])) if background_rect else {}
    background = background_attrs.get("fill", "white")

    products = {}
    for product in model.by_type("IfcSlab"):
        material = ifcopenshell.util.element.get_material(product)
        if getattr(material, "Name", None) != "Roof tiles":
            continue
        if not ifcopenshell.util.element.get_pset(product, "BBIM_RoofLayer"):
            continue
        token = "GlobalId-" + re.sub("[^0-9a-zA-Z]+", "", product.GlobalId)
        products.setdefault(token, []).append(product)
    if not products:
        return 0

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    definitions, frames, faces = [], {}, []

    def project(points):
        points = np.atleast_2d(points)
        return (to_svg @ np.column_stack((points, np.ones(len(points)))).T).T[:, :2]

    # SHAPELY may merge touching faces with the same material across different
    # slopes, then attach only one raycast GlobalId to that composite surface.
    # Recover top-face visibility independently, including tile side faces as
    # occluders. Native material paths still supply the final visibility mask.
    for token, aliases in products.items():
        if len(aliases) != 1:
            continue  # CSS-safe GUID sanitisation must never pick an alias.
        product = aliases[0]
        placement = ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
        normal = placement[:3, 2]
        layer = ifcopenshell.util.element.get_pset(product, "BBIM_RoofLayer")
        thickness = _positive(layer["Thickness"], "roof tile layer thickness")
        shape = ifcopenshell.geom.create_shape(settings, product)
        vertices = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        triangles = np.asarray(shape.geometry.faces, dtype=int).reshape(-1, 3)
        homogeneous = np.column_stack((vertices, np.ones(len(vertices))))
        local = (np.linalg.inv(placement) @ homogeneous.T).T
        top = np.all(np.isclose(local[triangles, 2], thickness, atol=1e-7, rtol=0), axis=1)
        projected = project(vertices)
        depth = (to_camera @ homogeneous.T).T[:, 2]
        groups = {}
        top_visible = float(normal @ camera_normal) > 1e-7
        for triangle, is_top in zip(triangles, top):
            points = projected[triangle]
            coordinates = np.column_stack((points, np.ones(3)))
            if abs(float(np.linalg.det(coordinates))) < 1e-9:
                continue  # An edge-on face has no projected area.
            coefficients = np.linalg.solve(coordinates, depth[triangle])
            key = (bool(is_top and top_visible), *np.round(coefficients, 7))
            polygon = _front_part(Polygon(points), -coefficients)
            if polygon is not None and not polygon.is_empty and polygon.area > 1e-9:
                groups.setdefault(key, (coefficients, []))[1].append(polygon)
        for key, (coefficients, polygons) in groups.items():
            faces.append((token, key[0], coefficients, unary_union(polygons)))
        frames[token] = product, placement, thickness

    visible = {}
    for token, is_top, coefficients, region in faces:
        if not is_top:
            continue
        for other, _, other_coefficients, occluder in faces:
            if other == token or not region.intersects(occluder):
                continue
            overlap = region.intersection(occluder)
            if overlap.area < 1e-9:
                continue
            difference = other_coefficients - coefficients
            if np.max(np.abs(difference)) < 1e-6:
                # Coincident roof pieces must not double-hatch their overlap.
                mask = overlap if other < token else None
            else:
                mask = _front_part(overlap, difference)
            if mask is not None and not mask.is_empty:
                region = region.difference(mask)
                if region.is_empty:
                    break
        if not region.is_empty and region.area > 1e-9:
            visible.setdefault(token, []).append(region)

    patterns = []
    for token, regions in visible.items():
        region = unary_union(regions)
        product, placement, thickness = frames[token]
        properties = ifcopenshell.util.element.get_pset(product, "BBIM_RoofTilePattern") or {}
        width = _positive(properties.get("TileWidth", default_width), "tile width")
        course = _positive(properties.get("CourseLength", default_course), "tile course")
        origin = placement[:3, 3] + placement[:3, 2] * thickness
        across = placement[:3, 0]
        downhill = placement[:3, 1].copy()
        if downhill[2] > 0:
            downhill *= -1
        base, x, y = project((origin, origin + across * width, origin + downhill * course))
        u, v = x - base, y - base
        pattern_body = _printed_outline(glyph_lines, u, v, stroke, background)
        identifier = token.removeprefix("GlobalId-")
        pattern_id, clip_id = f"roof-tiles-{identifier}", f"roof-tiles-top-{identifier}"
        transform = " ".join(f"{value:.12g}" for value in (*u, *v, *base))
        definitions.append(
            f'<pattern id="{pattern_id}" patternUnits="userSpaceOnUse" width="1" height="1" '
            f'data-tile-width-mm="{width*1000:g}" data-course-mm="{course*1000:g}" '
            f'data-line-width-mm="{stroke/units_per_mm:g}" '
            f'patternTransform="matrix({transform})">{pattern_body}</pattern>\n'
            f'<clipPath id="{clip_id}" clipPathUnits="userSpaceOnUse">'
            f'<path d="{_contours(region)}" clip-rule="evenodd"/></clipPath>\n'
        )
        patterns.append((token, pattern_id, clip_id, region))

    count = 0
    colored = 0

    def hatch(match):
        nonlocal count, colored
        attributes = dict(_ATTRS.findall(match["attrs"]))
        classes = set(attributes.get("class", "").split())
        if not {"material-Rooftiles", "surface"} <= classes or "cut" in classes:
            return match[0]
        tokens = classes & products.keys()
        if len(tokens) != 1:
            return match[0]
        data = attributes.get("d", "")
        surface = _surface_region(data)
        if surface is None or surface.is_empty:
            return match[0]
        # Side/end faces stay unhatched but share the top pattern's color.
        # An inline important fill overrides the legacy white material rule.
        style = attributes.get("style", "").rstrip("; ")
        style = (style + ";" if style else "") + f"fill:{background} !important;"
        base_attrs = re.sub(r'\s+style="[^"]*"', '', match["attrs"])
        base = f'<path{base_attrs} style="{escape(style, quote=True)}"/>'
        colored += 1
        # Bonsai's compound path retains every visible contour and opening.
        # Overlay directly after its own solid face, never at the drawing top.
        overlays = []
        for token, pattern_id, clip_id, region in patterns:
            if not surface.intersects(region) or surface.intersection(region).area < 1e-8:
                continue
            overlays.append(f'<path class="roof-tile-hatch" data-owner="{token}" d="{data}" '
                            f'clip-path="url(#{clip_id})" '
                            f'style="fill:url(#{pattern_id}) !important;fill-rule:evenodd;stroke:none !important;"/>')
        count += len(overlays)
        return base + "".join(overlays)

    updated = re.sub(r'<path\b(?P<attrs>[^>]*)/>', hatch, svg)
    if colored:
        definitions = f'<defs id="{_DEFS_ID}">\n' + "".join(definitions) + '</defs>\n'
        closing = updated.rfind("</svg>")
        updated = updated[:closing] + definitions + updated[closing:]
        path.write_text(updated, encoding="utf-8")
    return count
