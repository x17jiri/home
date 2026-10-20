"""Optional exposed-section outlines, independent of the IFC/SVG generator.

Use Bonsai's actual cut polygons and closed projected wall contours (never
convex hulls), with IFC metadata to select wall, floor and ceiling assemblies.
Wall plates join the wall assemblies; other roof members and non-wall
projections are not outlined. Existing SVG geometry/styles are left intact.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape
from math import isfinite
from pathlib import Path
import re
import warnings
import xml.etree.ElementTree as ET
from xml.parsers import expat

import ifcopenshell.util.element
import numpy as np
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import polygonize, unary_union

_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(rf"[A-Za-z]|{_NUMBER}")
_GUID = re.compile(r"[0-3][0-9A-Za-z_$]{21}")
_IFC = "{http://www.ifcopenshell.org/ns}"
_LAYER = re.compile(r'\n?<g\b[^>]*\bid="section-outlines"[^>]*>.*?</g>\n?', re.DOTALL)
_CATEGORIES = {"walls", "floors", "ceilings"}


def _transform(value):
    matrix = np.eye(3)
    remainder = re.sub(r"([A-Za-z]+)\s*\(([^)]*)\)", "", value)
    if remainder.strip(" ,\t\r\n"):
        raise ValueError("unsupported SVG transform")
    for name, args in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value):
        values = [float(v) for v in re.findall(_NUMBER, args)]
        current = np.eye(3)
        if name == "matrix" and len(values) == 6:
            a, b, c, d, e, f = values
            current = np.array(((a, c, e), (b, d, f), (0, 0, 1)))
        elif name == "translate" and len(values) in (1, 2):
            current[:2, 2] = (values[0], values[1] if len(values) == 2 else 0)
        elif name == "scale" and len(values) in (1, 2):
            current[0, 0], current[1, 1] = values[0], values[-1]
        elif name == "rotate" and len(values) in (1, 3):
            angle = np.radians(values[0])
            current[:2, :2] = ((np.cos(angle), -np.sin(angle)), (np.sin(angle), np.cos(angle)))
            if len(values) == 3:
                center = np.array(values[1:])
                current[:2, 2] = center - current[:2, :2] @ center
        else:
            raise ValueError(f"unsupported SVG transform {name}")
        matrix = matrix @ current
    return matrix


def _paths(element):
    """Read straight SVG subpaths, retaining whether their ends meet."""
    tag = element.tag.rsplit("}", 1)[-1]
    if tag == "line":
        return [[(float(element.get(x, 0)), float(element.get(y, 0)))
                 for x, y in (("x1", "y1"), ("x2", "y2"))]]
    if tag == "rect":
        if float(element.get("rx", 0)) or float(element.get("ry", 0)):
            raise ValueError("rounded rectangle")
        x, y, w, h = (float(element.get(k, 0)) for k in ("x", "y", "width", "height"))
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
    if tag in {"polygon", "polyline"}:
        values = [float(v) for v in re.findall(_NUMBER, element.get("points", ""))]
        if len(values) % 2:
            raise ValueError("odd SVG coordinate count")
        points = list(zip(values[::2], values[1::2]))
        if points and tag == "polygon" and points[0] != points[-1]:
            points.append(points[0])
        return [points] if len(points) >= 2 else []
    if tag != "path":
        return []
    data = element.get("d", "")
    if _TOKEN.sub("", data).strip(" ,\t\r\n"):
        raise ValueError("invalid SVG path")
    tokens = _TOKEN.findall(data)
    rings, points, command = [], [], None
    cursor = np.zeros(2)
    index = 0
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command in "Zz":
                if points:
                    points.append(points[0])
                    rings.append(points)
                    cursor = np.array(points[0])
                points, command = [], None
                continue
        if command not in {"M", "m", "L", "l", "H", "h", "V", "v"}:
            raise ValueError(f"unsupported SVG path command {command}")
        count = 1 if command in "HhVv" else 2
        values = tokens[index:index + count]
        if len(values) != count or any(v.isalpha() for v in values):
            raise ValueError("incomplete SVG path")
        values = [float(v) for v in values]
        if command in "Mm":
            if len(points) >= 2:
                rings.append(points)
            points = []
        point = cursor.copy()
        if command in "Hh":
            point[0] = values[0] + (cursor[0] if command == "h" else 0)
        elif command in "Vv":
            point[1] = values[0] + (cursor[1] if command == "v" else 0)
        else:
            point = np.array(values) + (cursor if command.islower() else 0)
        cursor = point
        points.append(tuple(point))
        if command in "Mm":
            command = "l" if command == "m" else "L"
        index += count
    if len(points) >= 2:
        rings.append(points)
    return rings


def _rings(element):
    """Read closed outlines only, including compound-path holes."""
    return [points for points in _paths(element)
            if len(points) >= 4 and points[0] == points[-1]]


def _segments(element, matrix, grid):
    result = []
    for path in _paths(element):
        points = [tuple(np.round((matrix @ (*point, 1))[:2] / grid) * grid) for point in path]
        result.extend((a, b) for a, b in zip(points, points[1:]) if a != b)
    return result


def _polygon(element, matrix, grid):
    result = GeometryCollection()
    for ring in _rings(element):
        points = [tuple(np.round((matrix @ (*point, 1))[:2] / grid) * grid) for point in ring]
        if len(set(points)) < 3:
            continue
        polygon = Polygon(points)
        if not polygon.is_valid:
            raise ValueError("invalid closed cut polygon")
        # Bonsai cut fills use even-odd winding; nested loops are holes.
        result = result.symmetric_difference(polygon)
    return result


def _opening_exclusion(element, matrix, grid, inset):
    """Restore the jamb ends trimmed off a rendered opening's white mask.

    The mask generator insets each end by min(25 mm, opening_width / 4).
    Its four points follow the two wall faces. Extend only along that axis,
    before applying SVG transforms, so rotations/mirroring/scaling also work.
    """
    rings = _rings(element)
    if len(rings) != 1 or len(rings[0]) != 5:
        return GeometryCollection()
    points = np.array(rings[0][:-1], dtype=float)
    axis = points[1] - points[0]
    length = np.linalg.norm(axis)
    if length <= grid:
        return GeometryCollection()
    extension = axis / length * min(inset, length / 2)
    points += np.array((-extension, extension, extension, -extension))
    points = [tuple(np.round((matrix @ (*p, 1))[:2] / grid) * grid) for p in points]
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= grid * grid:
        return GeometryCollection()
    return polygon.buffer(grid * 2, join_style=2)


def _category(element):
    """Return a category and assembly key, following decomposed slab parts."""
    current = element
    seen, ancestors = set(), []
    while current is not None and current.id() not in seen:
        seen.add(current.id())
        ancestors.append(current)
        current = ifcopenshell.util.element.get_aggregate(current)
    # Wall plates close the wall assembly's exposed outline even though they
    # are timber roof members. Other rafters/purlins/beams remain excluded.
    for owner in ancestors:
        if owner.is_a("IfcBeam") and ifcopenshell.util.element.get_predefined_type(owner) == "WALL_PLATE":
            return "walls", owner.GlobalId, False
    if any(e.is_a("IfcRoof") or e.is_a("IfcSlab")
           and ifcopenshell.util.element.get_predefined_type(e) == "ROOF" for e in ancestors):
        return None, element.GlobalId, False
    # Foundation concrete keeps its native thin strokes in every view. Still
    # retain its cut geometry as a contact mask for adjoining outlined solids.
    if any(owner.is_a("IfcSlab")
           and ifcopenshell.util.element.get_predefined_type(owner) == "BASESLAB"
           or owner.is_a("IfcWall") and any(
               material.Name.casefold().replace(" ", "-")
               in {"ztracene-bedneni", "ztracené-bednění"}
               for material in ifcopenshell.util.element.get_materials(owner))
           for owner in ancestors):
        return None, element.GlobalId, False
    for owner in ancestors:
        if ifcopenshell.util.element.get_pset(owner, "BBIM_MiakoSlab"):
            return "ceilings", owner.GlobalId, not bool(owner.HasOpenings)
        if owner.is_a("IfcWall") or ifcopenshell.util.element.get_pset(owner, "BBIM_RingBeam"):
            return "walls", owner.GlobalId, False
        if owner.is_a("IfcCovering") and ifcopenshell.util.element.get_predefined_type(owner) == "CEILING":
            return "ceilings", owner.GlobalId, False
        if owner.is_a("IfcSlab") and ifcopenshell.util.element.get_predefined_type(owner) == "FLOOR":
            return "floors", owner.GlobalId, False
    return None, element.GlobalId, False


def _closed_segments(segments):
    """Recover only exact, unambiguous closed loops from annotation lines.

    Bonsai exports each side of a wool outline as a separate line. Deduplicate
    repeated edges, but never bridge a gap or infer a hull from open linework.
    """
    edges = {tuple(sorted((a, b))) for a, b in segments if a != b}
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return GeometryCollection()
    geometry = GeometryCollection()
    while edges:
        start, point = min(edges)
        edges.remove(tuple(sorted((start, point))))
        ring = [start, point]
        while point != start:
            following = [p for p in adjacency[point] if tuple(sorted((point, p))) in edges]
            if len(following) != 1:
                return GeometryCollection()
            next_point = following[0]
            edges.remove(tuple(sorted((point, next_point))))
            ring.append(next_point)
            point = next_point
        polygon = Polygon(ring)
        if not polygon.is_valid:
            return GeometryCollection()
        geometry = geometry.symmetric_difference(polygon)
    return geometry


def _projected_regions(segments):
    """Polygonize visible wall linework without bridging missing edges.

    Shared edges and internal face divisions may create branching graphs, so
    polygonize each connected component and merge its faces. Separate nested
    loops retain even-odd holes instead of filling rooms/window openings.
    """
    network = unary_union([LineString(edge) for edge in segments])
    adjacency = defaultdict(set)
    for line in _line_parts(network):
        for a, b in zip(line.coords, list(line.coords)[1:]):
            adjacency[a].add(b)
            adjacency[b].add(a)
    remaining = set(adjacency)
    result = GeometryCollection()
    while remaining:
        pending = [min(remaining)]
        vertices = set()
        while pending:
            vertex = pending.pop()
            if vertex in vertices:
                continue
            vertices.add(vertex)
            pending.extend(adjacency[vertex] - vertices)
        remaining.difference_update(vertices)
        edges = {tuple(sorted((a, b))) for a in vertices for b in adjacency[a]}
        faces = unary_union(list(polygonize([LineString(edge) for edge in sorted(edges)])))
        result = result.symmetric_difference(faces)
    return result


def _complete_projected_regions(segments, supporting, grid):
    """Complete fragmented projections with touching, already-rendered solids.

    A capping ring beam can have open contours where cut members obscure its
    returns. Use those actual cut/closed-wall boundaries, not invented links.
    Reject faces outside the original visible extent or inside an occluder.
    """
    source = unary_union([LineString(edge) for edge in segments])
    if source.is_empty:
        return GeometryCollection()
    nearby = [g for g in supporting if g.distance(source) <= grid * 2]
    if not nearby:
        return GeometryCollection()
    occupied = unary_union(nearby)
    network = unary_union([source, *(g.boundary for g in nearby)])
    x_min, y_min, x_max, y_max = source.bounds
    faces = []
    for face in polygonize(network):
        a, b, c, d = face.bounds
        if a < x_min - grid * 2 or b < y_min - grid * 2 \
                or c > x_max + grid * 2 or d > y_max + grid * 2:
            continue
        if face.boundary.intersection(source).length <= grid * 2:
            continue
        if not occupied.covers(face.representative_point()):
            faces.append(face)
    return unary_union(faces)


def _without_internal_cells(geometry):
    if geometry.geom_type == "Polygon":
        return Polygon(geometry.exterior)
    return unary_union([_without_internal_cells(part) for part in geometry.geoms])


def _line_parts(geometry):
    if geometry.geom_type in {"LineString", "LinearRing"}:
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _line_parts(part)


def _insert_layer(svg, layer):
    """Insert before overlays, compensating any enclosing SVG transforms."""
    data = svg.encode("utf-8")
    parser = expat.ParserCreate()
    stack = [np.eye(3)]
    insertion = None

    def start(name, attrs):
        nonlocal insertion
        parent = stack[-1]
        classes = attrs.get("class", "").split()
        if insertion is None and name.rsplit(":", 1)[-1] == "g" and any(c.endswith("-overlays") for c in classes):
            insertion = (parser.CurrentByteIndex, parent)
        stack.append(parent @ _transform(attrs.get("transform", "")))

    def end(name):
        stack.pop()

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.Parse(data, True)
    offset, matrix = insertion or (data.rfind(b"</svg>"), np.eye(3))
    if offset < 0:
        raise ValueError("SVG root must have an explicit closing tag")
    inverse = np.linalg.inv(matrix)
    if not np.allclose(inverse, np.eye(3)):
        a, c, e = inverse[0]
        b, d, f = inverse[1]
        layer = layer.replace('id="section-outlines"',
                              f'id="section-outlines" transform="matrix({a:g} {b:g} {c:g} {d:g} {e:g} {f:g})"', 1)
    return (data[:offset] + layer.encode("utf-8") + data[offset:]).decode("utf-8")


def add_section_outlines(svg_path, model, drawing=None, *, width_mm=0.20,
                         categories=("walls", "floors", "ceilings"),
                         projected_walls=True, offset_ratio=0.25):
    """Append exposed assembly boundaries; return the number of polylines.

    Geometry comes from the rendered closed cut polygons; IFC supplies assembly
    ownership, roof exclusions and the host of facade-insulation annotations.
    By default, closed visible projected wall contours and their insulation join
    the cut regions. Set projected_walls=False to retain cut-only boundaries.
    Rendered door/unfilled-opening masks keep projected walls out of the gaps;
    their 25 mm endpoint insets are restored before subtracting the openings.
    Explicit WALL_PLATE members are included as part of the wall assemblies.
    The centreline is offset toward air by offset_ratio times the printed line
    width (default 0.25). Zero restores a centred stroke; 0.5 puts it outside.
    Other cut solids suppress contact edges but never receive thick outlines
    themselves. Internal MIAKO cells are not treated as room openings.
    With projected_walls enabled, all closed visible projected beam regions
    also suppress contact edges, without receiving new outlines themselves.
    Foundation slabs and permanent-formwork walls keep their original thin
    strokes in all views, but still suppress contact edges of adjacent solids.

    The only file changed is svg_path. Re-running replaces our own group. The
    normal renderer calls this before annotation overlays and PDF/PNG export.
    Polygon coordinates are snapped to 0.001 printed mm to absorb tessellation
    noise; the pass never constructs convex hulls or closes open SVG linework.
    """
    if isinstance(width_mm, bool) or not isinstance(width_mm, (int, float)) or not isfinite(width_mm) or width_mm <= 0:
        raise ValueError("section outline width must be positive and finite")
    if not isinstance(projected_walls, bool):
        raise TypeError("projected_walls must be a boolean")
    if isinstance(offset_ratio, bool) or not isinstance(offset_ratio, (int, float)) \
            or not isfinite(offset_ratio) or offset_ratio < 0:
        raise ValueError("section outline offset ratio must be non-negative and finite")
    if isinstance(categories, str):
        raise TypeError("categories must be a sequence of category names")
    categories = frozenset(categories)
    if not categories or not categories <= _CATEGORIES:
        raise ValueError("categories must contain walls, floors and/or ceilings")
    path = Path(svg_path)
    original = path.read_text(encoding="utf-8")
    svg = _LAYER.sub("", original)
    root = ET.fromstring(svg)
    physical_width = re.fullmatch(rf"\s*({_NUMBER})mm\s*", root.get("width", ""))
    view_box = [float(v) for v in re.split(r"[,\s]+", root.get("viewBox", "").strip())]
    if physical_width is None or len(view_box) != 4 or min(view_box[2:]) <= 0 or float(physical_width[1]) <= 0:
        raise ValueError("section outlines require a positive mm SVG width and viewBox")
    units_per_mm = view_box[2] / float(physical_width[1])
    grid = .001 * units_per_mm
    offset = width_mm * offset_ratio * units_per_mm
    scale = re.fullmatch(rf"\s*({_NUMBER})\s*[:/]\s*({_NUMBER})\s*",
                         root.get("data-scale", ""))
    opening_inset = (25 * float(scale[1]) / float(scale[2]) * units_per_mm
                     if scale and float(scale[1]) > 0 and float(scale[2]) > 0 else 0)
    # SHAPELY surface paths identify products only through CSS-safe classes,
    # which drop '$' and '_' from IFC GUIDs. Native product groups retain the exact
    # ifc:guid; collect aliases up front, since surfaces can precede them.
    guid_aliases = defaultdict(set)
    for element in root.iter():
        guid = element.get(_IFC + "guid", "")
        if not _GUID.fullmatch(guid):
            continue
        normalized_guid = guid.replace("$", "").replace("_", "")
        for token in element.get("class", "").split():
            if token in {f"GlobalId-{guid}", f"GlobalId-{normalized_guid}"}:
                guid_aliases[token.removeprefix("GlobalId-")].add(guid)
    sources, included_walls, cache, category_cache = [], set(), {}, {}
    opening_masks = []
    host_cache = {}
    insulation_segments, insulation_hosts = defaultdict(list), {}
    projection_segments, projection_aliases = defaultdict(list), defaultdict(set)
    covering_segments = defaultdict(list)

    def product(element, classes, inherited, is_cut, is_projected):
        candidates = [element.get(_IFC + "guid", "")]
        for token in sorted(classes):
            guid = token.removeprefix("GlobalId-")
            aliases = guid_aliases.get(guid)
            if aliases:
                # Sanitization can collide; never guess a product in that case.
                if len(aliases) != 1:
                    continue
                guid = next(iter(aliases))
            candidates.append(guid)
        first = None
        walls = set()
        for guid in candidates:
            if not _GUID.fullmatch(guid):
                continue
            if guid not in cache:
                try:
                    cache[guid] = model.by_guid(guid)
                except RuntimeError:
                    cache[guid] = None
            if cache[guid] is not None:
                # Bonsai may merge adjoining cuts into one polygon carrying
                # several product IDs. Every wall still owns its insulation;
                # choosing only one ID makes other hosts disappear at random.
                if guid not in host_cache:
                    hosts = set()
                    if cache[guid].is_a("IfcWall"):
                        hosts.add(guid)
                    elif cache[guid].is_a("IfcBeam"):
                        source_wall = ifcopenshell.util.element.get_pset(
                            cache[guid], "BBIM_RingBeam", "SourceWall")
                        if source_wall:
                            hosts.add(source_wall)
                    host_cache[guid] = hosts
                walls.update(host_cache[guid])
                if first is None:
                    first = cache[guid]
        if is_cut:
            included_walls.update(walls)
        if first is not None and is_projected:
            projection_aliases[first.GlobalId].update(walls)
        return first if first is not None else inherited

    def walk(element, matrix, owner=None, is_cut=False, is_projected=False,
             inherited_classes=frozenset()):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"defs", "symbol", "clipPath", "mask"}:
            return
        own_classes = set(element.get("class", "").split())
        classes = inherited_classes | own_classes
        if own_classes & {"projection", "surface"}:
            is_cut = False
            is_projected = True
        elif "cut" in own_classes:
            is_cut = True
            is_projected = False
        matrix = matrix @ _transform(element.get("transform", ""))
        if projected_walls and "door-overhead-mask" in own_classes:
            geometry = _opening_exclusion(element, matrix, grid, opening_inset)
            if not geometry.is_empty:
                opening_masks.append(geometry)
        owner = product(element, own_classes, owner, is_cut, is_projected)
        if owner is not None and is_cut and owner.is_a("IfcWall"):
            included_walls.add(owner.GlobalId)
        insulation = "wall-insulation" in classes and owner is not None and owner.is_a("IfcAnnotation")
        if insulation and tag == "line" and "wall-insulation-rockwool-boundary" in classes:
            host = ifcopenshell.util.element.get_pset(owner, "BBIM_WallInsulationBoundary", "HostWall")
            if host:
                points = [tuple(np.round((matrix @ (float(element.get(x, 0)),
                                                     float(element.get(y, 0)), 1))[:2] / grid) * grid)
                          for x, y in (("x1", "y1"), ("x2", "y2"))]
                insulation_segments[owner.GlobalId].append(tuple(points))
                insulation_hosts[owner.GlobalId] = host
        if owner is not None and (is_cut or insulation or projected_walls and is_projected) \
                and tag in {"path", "polygon", "polyline", "rect", "line"}:
            if owner.id() not in category_cache:
                category_cache[owner.id()] = _category(owner)
            category, assembly, fill_cells = category_cache[owner.id()]
            if projected_walls and is_projected and category == "walls":
                try:
                    projection_segments[assembly].extend(_segments(element, matrix, grid))
                except ValueError as error:
                    warnings.warn(f"Section outline skipped projected {owner.Name}: {error}", stacklevel=2)
            elif projected_walls and is_projected and owner.is_a("IfcBeam"):
                # Visible timber masks wall contact edges, even when no wall
                # contour needs completion. Its closed contour can also supply
                # missing returns without becoming an outlined assembly.
                try:
                    covering_segments[owner.GlobalId].extend(_segments(element, matrix, grid))
                except ValueError:
                    pass
            elif is_cut or insulation:
                try:
                    geometry = _polygon(element, matrix, grid)
                except ValueError as error:
                    if category in categories:
                        warnings.warn(f"Section outline skipped {owner.Name}: {error}", stacklevel=2)
                else:
                    if not geometry.is_empty:
                        host = ifcopenshell.util.element.get_pset(owner, "BBIM_WallInsulation", "HostWall") if insulation else None
                        sources.append((category, assembly, fill_cells, geometry, host, insulation))
        for child in element:
            walk(child, matrix, owner, is_cut, is_projected, classes)

    walk(root, np.eye(3))
    cut_source_count = len(sources)
    incomplete = []
    for guid, segments in projection_segments.items():
        geometry = _projected_regions(segments)
        if not geometry.is_empty:
            sources.append(("walls", guid, False, geometry, None, False))
            included_walls.update(projection_aliases.get(guid, (guid,)))
        else:
            incomplete.append((guid, segments))
    covering = [_projected_regions(segments) for segments in covering_segments.values()]
    covering = [geometry for geometry in covering if not geometry.is_empty]
    supporting = [geometry for _, _, _, geometry, _, insulation in sources if not insulation] + covering
    # A plate can itself need a neighbouring wall to close its contour, then
    # supply the missing boundary of the ring beam beneath it. Repeat until no
    # new faces are found; occupied supporting faces cannot be added twice.
    while incomplete:
        changed = False
        for guid, segments in incomplete:
            geometry = _complete_projected_regions(segments, supporting, grid)
            if geometry.area <= grid * grid:
                continue
            sources.append(("walls", guid, False, geometry, None, False))
            included_walls.update(projection_aliases.get(guid, (guid,)))
            supporting.append(geometry)
            changed = True
        if not changed:
            break
    if opening_masks:
        # Do this after contour completion (which could otherwise close the
        # gaps again), but before merging/offsetting. Cut jambs stay untouched.
        exclusions = unary_union(opening_masks)
        sources[cut_source_count:] = [
            (category, assembly, cells, geometry.difference(exclusions), host, insulation)
            for category, assembly, cells, geometry, host, insulation in sources[cut_source_count:]
        ]
    for guid, segments in insulation_segments.items():
        geometry = _closed_segments(segments)
        if not geometry.is_empty:
            sources.append(("walls", guid, False, geometry, insulation_hosts[guid], True))
    selected, other, fill_cells = defaultdict(list), list(covering), set()
    for category, assembly, cells, geometry, host, insulation in sources:
        if insulation:
            if host not in included_walls:
                continue
            category, assembly = "walls", host
        if category in categories:
            selected[assembly].append(geometry)
            if cells:
                fill_cells.add(assembly)
        elif not insulation:
            other.append(geometry)
    assemblies = []
    for key, parts in selected.items():
        assembly = unary_union(parts)
        assemblies.append(_without_internal_cells(assembly) if key in fill_cells else assembly)
    solid = unary_union(assemblies)
    # Buffer the merged solid, not individual elements or open boundary pieces.
    # This expands external contours and shrinks room/opening holes toward air,
    # independent of winding, mirroring or view orientation, without seams.
    contour = solid.buffer(offset, join_style=2) if offset else solid
    boundaries = contour.boundary if not contour.is_empty else GeometryCollection()
    if other and not boundaries.is_empty:
        # Carry the contact mask outward too, so hidden contact edges and their
        # corner returns cannot reappear merely because the stroke moved.
        boundaries = boundaries.difference(unary_union(other).buffer(offset + grid * 2, join_style=2))
    parts = sorted(_line_parts(boundaries), key=lambda line: (*line.bounds, line.length))
    paths = []
    for part in parts:
        d = "M" + " L".join(f"{x:.9g},{y:.9g}" for x, y in part.coords)
        paths.append(f'<path class="section-outline" d="{escape(d, quote=True)}"/>')
    if paths:
        layer = ('\n<g id="section-outlines" class="section-outlines" '
                 f'data-width-mm="{width_mm:g}" data-offset-ratio="{offset_ratio:g}" '
                 f'data-offset-mm="{width_mm * offset_ratio:g}" '
                 f'style="fill:none;stroke:black;stroke-width:{width_mm * units_per_mm:g};'
                 'stroke-linejoin:round;stroke-linecap:round">\n'
                 + "\n".join(paths) + '\n</g>\n')
        svg = _insert_layer(svg, layer)
    if svg != original:
        path.write_text(svg, encoding="utf-8")
    return len(paths)
