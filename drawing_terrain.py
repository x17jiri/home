"""Drawing-only terrain masks, projected from persisted IFC annotations.

Run after model postprocessing and before annotation/table/title layout. Bonsai
puts its model in ``section`` groups and native annotations outside them. The
additional model layers below are produced by our elevation postprocessing.
Keeping those layers together lets annotations retain their own transforms and
stay above the terrain without changing the underlying model or section views.
"""

from fractions import Fraction
from io import StringIO
from pathlib import Path
import xml.etree.ElementTree as ET

import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np


_MODEL_LAYERS = {
    "section", "section-outlines", "miako-reinforcement-overlays",
    "ring-beam-stirrups", "vapour-barrier-overlays", "section-opening-overlays",
    "wall-insulation-depth-layer", "wall-insulation-foreground",
}


def add_terrain_overlay(svg_path: Path, drawing, *, width_mm, view_box):
    """Mask building geometry below each terrain profile, leaving labels above."""
    terrains = []
    for relation in drawing.HasAssignments or ():
        if relation.is_a("IfcRelAssignsToGroup") and relation.RelatingGroup.ObjectType == "DRAWING":
            for grouped in relation.RelatingGroup.IsGroupedBy or ():
                for item in grouped.RelatedObjects:
                    properties = ifcopenshell.util.element.get_pset(item, "BBIM_DrawingTerrain")
                    if properties:
                        terrains.append((item, properties))
    if not terrains:
        return
    svg = svg_path.read_text(encoding="utf-8")
    # Retain Bonsai's namespace prefixes: subsequent SVG passes also use them.
    for _, (prefix, uri) in ET.iterparse(StringIO(svg), events=("start-ns",)):
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(svg)
    if any(item.get("class") == "terrain-overlays" for item in root):
        return
    ns = root.tag.removesuffix("svg")
    tag = lambda name: ns + name
    view_x, view_y, view_width, view_height = view_box
    units_per_mm = view_width / width_mm
    scale = float(Fraction(str(ifcopenshell.util.element.get_pset(drawing, "EPset_Drawing", "Scale"))))
    units_per_metre = 1000 * scale * units_per_mm
    world_to_camera = np.linalg.inv(ifcopenshell.util.placement.get_local_placement(drawing.ObjectPlacement))
    overlay = ET.Element(tag("g"), {"class": "terrain-overlays"})

    def polygon(points, **attributes):
        return ET.SubElement(overlay, tag("polygon"), {
            "points": " ".join(f"{x:.12g},{y:.12g}" for x, y in points), **attributes,
        })

    for item, properties in terrains:
        placement = ifcopenshell.util.placement.get_local_placement(item.ObjectPlacement)
        geometry = item.Representation.Representations[0].Items[0]
        while geometry.is_a("IfcMappedItem"):
            placement = placement @ ifcopenshell.util.placement.get_mappeditem_transformation(geometry)
            geometry = geometry.MappingSource.MappedRepresentation.Items[0]
        curve = geometry.Elements[0]
        # Use exported geometry, not source-coordinate metadata, so X mirroring
        # is applied exactly once, just as for native drawing annotations.
        points = []
        for x, y in curve.Points.CoordList:
            camera = world_to_camera @ placement @ np.array((x, y, 0., 1.))
            points.append((view_x + view_width / 2 + camera[0] * units_per_metre,
                           view_y + view_height / 2 - camera[1] * units_per_metre))
        points.sort()
        bottom = max(view_y + view_height, max(y for _, y in points))
        polygon([*points, (points[-1][0], bottom), (points[0][0], bottom)],
                **{"class": "terrain-mask", "style": "fill:white !important;stroke:none !important"})
        depth = float(properties["HatchDepth"]) * units_per_metre
        if depth:
            polygon([*points, *((x, min(y + depth, bottom)) for x, y in reversed(points))],
                    **{"class": "terrain-hatch", "style":
                       f"fill:url(#{properties['Hatch']}) !important;stroke:none !important"})
        ET.SubElement(overlay, tag("polyline"), {
            "class": "terrain-line",
            "points": " ".join(f"{x:.12g},{y:.12g}" for x, y in points),
            "style": "fill:none !important;stroke:black !important;"
                     f"stroke-width:{float(properties['LineWidth']) * units_per_mm:g} !important;"
                     "stroke-linejoin:round",
        })

    resources, model_layers, annotations = [], [], []
    for child in list(root):
        if child.tag in {tag(name) for name in ("defs", "style", "metadata", "title", "desc")}:
            resources.append(child)
        elif set(child.get("class", "").split()) & _MODEL_LAYERS:
            model_layers.append(child)
        else:
            annotations.append(child)
    # A source polyline persists the profile in IFC, but its native SVG strokes
    # are replaced by the exact projected profile above.
    style = ET.Element(tag("style"), {"type": "text/css"})
    style.text = ".drawing-terrain-source { display:none !important; }"
    model_group = ET.Element(tag("g"), {"class": "terrain-model"})
    model_group.extend(model_layers)
    root[:] = [*resources, style, model_group, overlay, *annotations]
    svg_path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
