"""Remove projected material seams of ring beams inserted into their walls."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import ifcopenshell.util.element
import numpy as np
from shapely.geometry import LineString
from shapely.ops import unary_union

from section_outlines import _line_parts, _projected_regions, _segments, _transform

_IFC = "{http://www.ifcopenshell.org/ns}"
_SVG = "{http://www.w3.org/2000/svg}"
_MARKER = "data-ring-beam-seams-cleaned"


def remove_projected_ring_beam_seams(svg_path, model):
    """Edit projection strokes only; preserve fills, cuts and unrelated objects.

    Only beams marked ReplacesWallBand participate. Match visible linework
    against the linked source wall, never against an unrelated nearby wall.
    Call after geometry-dependent passes, before annotation overlays/export.
    """
    path = Path(svg_path)
    root = ET.fromstring(path.read_text(encoding="utf-8"),
                         parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if _MARKER in root.attrib:
        return 0
    pairs = {}
    for beam in model.by_type("IfcBeam"):
        properties = ifcopenshell.util.element.get_pset(beam, "BBIM_RingBeam") or {}
        if properties.get("ReplacesWallBand") and properties.get("SourceWall"):
            pairs[beam.GlobalId] = properties["SourceWall"]
    wanted = set(pairs) | set(pairs.values())
    if not wanted:
        return 0
    aliases = defaultdict(set)
    for guid in wanted:
        for alias in (guid, guid.replace("$", "").replace("_", "")):
            aliases[alias].add(guid)
    view_box = [float(v) for v in re.split(r"[,\s]+", root.get("viewBox", "")) if v]
    width = re.fullmatch(r"([\d.]+)mm", root.get("width", ""))
    if len(view_box) != 4 or width is None:
        return 0
    grid = .001*view_box[2]/float(width[1])  # One micron on paper.
    records, segments, axes = [], defaultdict(list), {}

    def walk(element, parent=None, matrix=np.eye(3), owner=None, kind=None, hidden=False):
        if not isinstance(element.tag, str):
            return
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"defs", "symbol", "clipPath", "mask"}:
            return
        style = element.get("style", "")
        hidden = hidden or bool(re.search(r"(?:^|;)\s*display\s*:\s*none\b", style))
        if hidden:
            return
        matrix = matrix @ _transform(element.get("transform", ""))
        classes = set(element.get("class", "").split())
        candidates = set()
        for token in (element.get(_IFC+"guid", ""), *classes):
            candidates.update(aliases.get(token.removeprefix("GlobalId-"), ()))
        if candidates:
            owner = next(iter(candidates)) if len(candidates) == 1 else None
        elif element.get(_IFC+"guid") or any(c.startswith("GlobalId-") for c in classes):
            owner = None
        if "cut" in classes:
            kind = "cut"
        elif "surface" in classes:
            kind = "surface"
        elif "projection" in classes:
            kind = "projection"
        if kind == "projection" and owner in wanted and tag in {"path", "polyline", "polygon", "line", "rect"} \
                and not re.search(r"(?:^|;)\s*stroke\s*:\s*none\b", style):
            try:
                edges = _segments(element, matrix, grid)
            except ValueError:
                edges = []  # Never approximate curved/unsupported paths.
            if edges:
                records.append((parent, element, matrix, owner, edges))
                segments[owner].extend(edges)
                axes[owner] = matrix[:2, 0]/np.linalg.norm(matrix[:2, 0])
        for child in element:
            walk(child, element, matrix, owner, kind, hidden)

    walk(root)
    networks = {guid: unary_union([LineString(e) for e in edges]) for guid, edges in segments.items()}
    removals = defaultdict(list)
    for beam, wall in pairs.items():
        if beam not in networks or wall not in networks:
            continue
        shared = networks[beam].intersection(networks[wall])
        # Vertical ends remain visible: they may be window jambs or silhouettes.
        level_edges = []
        normal = np.array((-axes[beam][1], axes[beam][0]))
        for line in _line_parts(shared):
            for a, b in zip(line.coords, list(line.coords)[1:]):
                if abs(np.dot(np.subtract(b, a), normal)) <= grid*2:
                    level_edges.append(LineString((a, b)))
        shared = unary_union(level_edges)
        wall_region = _projected_regions(segments[wall])
        beam_region = _projected_regions(segments[beam])
        if not wall_region.is_empty and not beam_region.is_empty:
            silhouette = wall_region.union(beam_region).boundary
            shared = shared.difference(silhouette.buffer(grid*2))
        # Occlusion often leaves open contours. Use only their actual shared
        # level edges; do not manufacture missing polygons or closing lines.
        if not shared.is_empty:
            removals[beam].append(shared)
            removals[wall].append(shared)
    masks = {guid: unary_union(parts) for guid, parts in removals.items()}
    count = 0
    for parent, element, matrix, owner, edges in records:
        mask = masks.get(owner)
        if mask is None:
            continue
        original = unary_union([LineString(e) for e in edges])
        axis = matrix[:2, 0]/np.linalg.norm(matrix[:2, 0])
        normal = np.array((-axis[1], axis[0]))
        # A very small tolerance handles rotated floating-point coordinates.
        # Apply it only along level edges, preserving jambs at their endpoints.
        buffered = mask.buffer(grid/10, cap_style=2, join_style=2)
        remaining = unary_union([
            LineString((a, b)).difference(buffered)
            if abs(np.dot(np.subtract(b, a), normal)) <= grid*2 else LineString((a, b))
            for a, b in edges
        ])
        if original.length-remaining.length <= grid/2:
            continue
        # Keep the original fill geometry, replacing only its strokes. This
        # also preserves closed projection faces and any material styling.
        fill = deepcopy(element)
        fill.set("style", fill.get("style", "").rstrip("; ")+";stroke:none!important")
        inverse = np.linalg.inv(matrix)
        data = []
        for line in _line_parts(remaining):
            if len(line.coords) < 2:
                continue
            points = [(inverse @ (*p, 1))[:2] for p in line.coords]
            data.append("M"+" L".join(f"{x:.12g},{y:.12g}" for x, y in points))
        index = list(parent).index(element)
        parent.remove(element)
        parent.insert(index, fill)
        if data:
            stroke = deepcopy(element)
            stroke.tag = _SVG+"path" if element.tag.startswith(_SVG) else "path"
            for key in ("id", "points", "x1", "y1", "x2", "y2", "x", "y", "width", "height"):
                stroke.attrib.pop(key, None)
            stroke.set("d", " ".join(data))
            stroke.set("style", stroke.get("style", "").rstrip("; ")+";fill:none!important")
            parent.insert(index+1, stroke)
        count += 1
    if count:
        root.set(_MARKER, str(count))
        ET.register_namespace("", _SVG[1:-1])
        ET.register_namespace("ifc", _IFC[1:-1])
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    return count
