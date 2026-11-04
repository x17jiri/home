"""Per-wall foundation dimensions and horizontal foundation steps along global Y."""

from dataclasses import dataclass
from itertools import combinations
import json
from math import isfinite
from typing import Sequence

import ifcopenshell
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.util.element
import ifcopenshell.util.representation
from ifcopenshell.util.shape_builder import ShapeBuilder
import numpy as np
from shapely.geometry import Polygon, box

from ifc_utils import Storey, Wall, _local_clippings, _clip_body_representation


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


@dataclass(frozen=True)
class FoundationSpec:
    wall: Wall
    wall_thickness: float | None = None
    footer_width: float | None = None
    footer_height: float | None = None


@dataclass(frozen=True)
class FoundationHeightMap:
    """Ordered (Y, nominal footer-bottom Z) breakpoints.

    A level applies from its Y coordinate up to the next breakpoint. The first
    and last levels extend beyond the listed range, including footing returns
    outside the house. All coordinates are absolute, unmirrored model metres.
    Tops follow these stepped levels plus footer height; undersides use 1:1
    transitions on the shallower side, without reducing minimum thickness.
    """

    steps: Sequence[tuple[float, float]]

    def __post_init__(self):
        points = tuple((_number(y, "step Y"), _number(z, "footer bottom Z")) for y, z in self.steps)
        if not points:
            raise ValueError("foundation height map must contain at least one level")
        if any(a[0] >= b[0] for a, b in zip(points, points[1:])):
            raise ValueError("foundation height map Y coordinates must be strictly increasing")
        # Equal adjacent levels form one band and do not create false joints.
        merged = tuple(p for i, p in enumerate(points) if i == 0 or p[1] != points[i-1][1])
        object.__setattr__(self, "steps", merged)

    def bands(self, minimum_y, maximum_y):
        for index, (_, z) in enumerate(self.steps):
            lo = minimum_y if index == 0 else max(minimum_y, self.steps[index][0])
            hi = maximum_y if index+1 == len(self.steps) else min(maximum_y, self.steps[index+1][0])
            if hi > lo+1e-9:
                yield lo, hi, z

    def bottom_profile(self, minimum_y, maximum_y):
        """Return exact (Y, Z) underside vertices with slopes 0, +1 or -1.

        This is the greatest continuous 1-Lipschitz profile below all nominal
        levels: min(level + distance to that level's Y interval). Nearby ramps
        combine naturally, including rises, falls and changes of direction.
        """
        minimum_y = _number(minimum_y, "minimum_y")
        maximum_y = _number(maximum_y, "maximum_y")
        if maximum_y <= minimum_y:
            raise ValueError("bottom profile Y range must have positive length")
        breaks = sorted({minimum_y, maximum_y,
                         *(y for y, _ in self.steps[1:] if minimum_y < y < maximum_y)})
        profile = []
        for left, right in zip(breaks, breaks[1:]):
            middle = (left+right)/2
            lines = {}
            for index, (y, level) in enumerate(self.steps):
                lo = float("-inf") if index == 0 else y
                hi = float("inf") if index+1 == len(self.steps) else self.steps[index+1][0]
                slope, intercept = ((-1, level+lo) if middle < lo else
                                    (1, level-hi) if middle > hi else (0, level))
                lines[slope] = min(lines.get(slope, float("inf")), intercept)
            points = {left, right}
            for (a, b), (c, d) in combinations(lines.items(), 2):
                crossing = (d-b)/(a-c)
                if left < crossing < right:
                    points.add(crossing)
            for y in sorted(points):
                z = min(slope*y+intercept for slope, intercept in lines.items())
                if profile and abs(y-profile[-1][0]) < 1e-9:
                    profile[-1] = (y, z)
                else:
                    profile.append((y, z))
                while len(profile) >= 3:
                    a, b, c = profile[-3:]
                    area = (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
                    if abs(area) > 1e-9:
                        break
                    profile.pop(-2)
        return tuple(profile)


def build_foundations(
    specs: Sequence[FoundationSpec],
    *,
    wall_storey: Storey,
    footer_storey: Storey,
    height_map: FoundationHeightMap,
    wall_top_z: float,
    wall_type: ifcopenshell.entity_instance,
    default_wall_thickness: float,
    default_footer_width: float,
    default_footer_height: float,
    slab_thickness: float = 0,
    wall_color: str | None = None,
    footer_material: str = "Concrete",
    footer_color: str = "#969696",
):
    """Build foundations from an explicit list of supported source walls.

    ``wall_type`` is a single-layer type with its axis on the outside face
    (``layers=[(material, thickness), "axis"]``).
    ``wall_top_z`` is the common absolute wall top. Each wall starts above its
    footer plus ``slab_thickness`` (the existing slab between footers and walls).
    Wall reference paths and their outside faces are retained. Each footing is
    centred below the foundation wall, with matching returns at true wall ends.
    Both wall bodies and full footing footprints are clipped at Y steps, so
    an artificial step does not receive an extra end return. Slabs and basement
    footprints are independent of this foundation profile. Footer tops step
    immediately; undersides transition at 45 degrees on the shallower side.
    """
    if wall_storey.house is not footer_storey.house:
        raise ValueError("foundation storeys must belong to the same house")
    house = wall_storey.house
    if not isinstance(height_map, FoundationHeightMap):
        raise TypeError("height_map must be a FoundationHeightMap")
    if (not isinstance(wall_type, ifcopenshell.entity_instance)
            or wall_type.file is not house.model or not wall_type.is_a("IfcWallType")):
        raise ValueError("foundation wall type must belong to this house")
    layout = house._wall_type_layouts.get(wall_type.id())
    if layout is None or abs(layout[0]) > 1e-9:
        raise ValueError('foundation wall type must put "axis" after its material layer')
    material = ifcopenshell.util.element.get_material(wall_type)
    if not material or not material.is_a("IfcMaterialLayerSet") or len(material.MaterialLayers) != 1:
        raise ValueError("foundation wall type must have one material layer")
    wall_material = material.MaterialLayers[0].Material.Name
    wall_top_z = _number(wall_top_z, "wall_top_z")
    slab_thickness = _number(slab_thickness, "slab_thickness")
    if slab_thickness < 0:
        raise ValueError("slab_thickness must not be negative")
    defaults = tuple(_number(n, name, positive=True) for n, name in (
        (default_wall_thickness, "default wall thickness"),
        (default_footer_width, "default footer width"),
        (default_footer_height, "default footer height"),
    ))
    # Resolve and validate every job before creating any IFC products.
    jobs, seen = [], set()
    for spec in specs:
        if not isinstance(spec, FoundationSpec) or not isinstance(spec.wall, Wall):
            raise TypeError("specs must contain FoundationSpec objects with source walls")
        source = spec.wall
        if source.file is not house.model or source.storey.house is not house:
            raise ValueError("foundation source walls must belong to this house")
        if source.id() in seen:
            raise ValueError("foundation source walls must be distinct")
        seen.add(source.id())
        thickness, width, height = tuple(
            default if supplied is None else _number(supplied, name, positive=True)
            for supplied, default, name in zip(
                (spec.wall_thickness, spec.footer_width, spec.footer_height), defaults,
                ("wall thickness", "footer width", "footer height"),
            )
        )
        if width < thickness:
            raise ValueError("footer width must not be smaller than foundation wall thickness")
        tangent = (np.asarray(source.end)-source.start)/source.length
        normal = np.array((-tangent[1], tangent[0]))

        def rectangle(start, end, near, far):
            return Polygon([tuple(np.asarray(source.start)+tangent*a+normal*b)
                            for a, b in ((start, near), (end, near), (end, far), (start, far))])

        wall_outline = rectangle(0, source.length, 0, thickness)
        extension = (width-thickness)/2
        footer_outline = rectangle(-extension, source.length+extension,
                                   thickness/2-width/2, thickness/2+width/2)
        x0, y0, x1, y1 = footer_outline.bounds
        for lo, hi, bottom in height_map.bands(y0, y1):
            clip = box(x0-1, lo, x1+1, hi)
            footer_polygon = footer_outline.intersection(clip)
            if footer_polygon.area <= 1e-10:
                continue
            wall_bottom = bottom+height+slab_thickness
            if wall_bottom >= wall_top_z-1e-9:
                raise ValueError("foundation wall bottom must be below wall_top_z")
            wall_polygon = wall_outline.intersection(clip)
            bottom_profile = height_map.bottom_profile(footer_polygon.bounds[1], footer_polygon.bounds[3])
            jobs.append((source, thickness, width, height, bottom, wall_bottom,
                         lo, hi, wall_polygon, footer_polygon, bottom_profile))

    if not jobs:
        return (), ()
    model = house.model
    wall_types = {material.MaterialLayers[0].LayerThickness: wall_type}
    if footer_material not in house._materials:
        house._materials[footer_material] = ifcopenshell.api.material.add_material(
            model, name=footer_material, category="foundation")
    footer_style = house._surface_style("slab", color=footer_color, transparency=0)
    walls, footers = [], []
    builder = ShapeBuilder(model)
    for source, thickness, width, height, bottom, wall_bottom, lo, hi, wall_polygon, polygon, bottom_profile in jobs:
        if wall_polygon.area > 1e-10:
            if thickness not in wall_types:
                wall_types[thickness] = house.wall_type(
                    f"Foundation wall - {wall_material} {thickness*1000:g} mm",
                    layers=[(wall_material, thickness), "axis"], color=wall_color,
                )
            cuts = []
            # The source path stays available for doors and continuous facades;
            # the native body alone is split at the global Y boundaries.
            if wall_polygon.bounds[1] > wall_outline_bounds(source, thickness)[1]+1e-8:
                cuts.append(((0, lo, 0), (1, lo, 0), (0, lo, 1)))
            if wall_polygon.bounds[3] < wall_outline_bounds(source, thickness)[3]-1e-8:
                cuts.append(((0, hi, 0), (1, hi, 0), (0, hi, 1)))
            wall = wall_storey.wall(
                source.start, source.end, wall_type=wall_types[thickness],
                height=wall_top_z-wall_bottom,
                start_height=wall_bottom-wall_storey.elevation,
                color=wall_color,
            )
            # Wall's standard cut helper keeps the centre side, which is
            # ambiguous for Y bands away from the centre. Use an interior point.
            if cuts:
                body = ifcopenshell.util.representation.get_representation(wall, "Model", "Body", "MODEL_VIEW")
                inside = wall_polygon.representative_point()
                world = np.array((inside.x, inside.y, (wall_bottom+wall_top_z)/2, 1))
                placement = wall._placement(0, wall.start_height)
                retained = (np.linalg.inv(placement) @ world)[:3]
                _clip_body_representation(model, wall, body, _local_clippings(cuts, placement, retained))
                object.__setattr__(wall, "cuts", tuple(cuts))
            object.__setattr__(wall, "source_wall", source)
            _metadata(model, wall, "BBIM_FoundationWall", {
                "SourceWall": source.GlobalId, "Thickness": thickness,
                "BottomZ": wall_bottom, "TopZ": wall_top_z, "YMin": lo, "YMax": hi,
            })
            walls.append(wall)

        footer_storey._footing_count += 1
        footer = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcFooting", name=f"Strip footing {footer_storey._footing_count}",
            predefined_type="STRIP_FOOTING",
        )
        ifcopenshell.api.spatial.assign_container(model, products=[footer], relating_structure=footer_storey.element)
        placement = np.eye(4)
        placement[2, 3] = bottom
        ifcopenshell.api.geometry.edit_object_placement(model, product=footer, matrix=placement, is_si=True)
        solid = _footer_solid(model, builder, polygon, bottom, height, bottom_profile)
        body = builder.get_representation(house._body_context, solid)
        ifcopenshell.api.geometry.assign_representation(model, product=footer, representation=body)
        if footer_style is not None:
            ifcopenshell.api.style.assign_representation_styles(model, shape_representation=body, styles=[footer_style])
        ifcopenshell.api.material.assign_material(
            model, products=[footer], type="IfcMaterial", material=house._materials[footer_material])
        _metadata(model, footer, "Pset_FootingCommon", {"LoadBearing": True})
        _metadata(model, footer, "BBIM_StripFooting", {
            "SourceWall": source.GlobalId, "Width": width, "Height": height,
            "Length": source.length+width-thickness, "StartHeight": bottom-footer_storey.elevation,
            "StructuralWidth": thickness, "StructuralCenterOffset": thickness/2,
            "BottomZ": bottom, "YMin": lo, "YMax": hi,
            "TopZ": bottom+height, "MinimumBottomZ": min(z for _, z in bottom_profile),
            "BottomProfile": json.dumps(bottom_profile),
        })
        footers.append(footer)
    return tuple(walls), tuple(footers)


def _footer_solid(model, builder, polygon, bottom, height, bottom_profile):
    points = list(polygon.exterior.coords)[:-1]
    if not polygon.exterior.is_ccw:
        points.reverse()
    if all(abs(z-bottom) < 1e-9 for _, z in bottom_profile):
        return builder.extrude(builder.polyline(points, closed=True), magnitude=height)
    x0, y0, x1, y1 = polygon.bounds
    # A Y/Z section extruded along X keeps the top horizontal while the
    # underside can contain several flat and 45-degree segments.
    section = [(y0, height), (y1, height),
               *((y, z-bottom) for y, z in reversed(bottom_profile))]
    section.reverse()  # Counterclockwise outer profile.
    prism = builder.extrude(builder.polyline(section, closed=True), magnitude=x1-x0,
                            position=(x0, 0, 0), **builder.extrude_kwargs("X"))
    if polygon.equals(box(x0, y0, x1, y1)):
        return prism
    # Rotated wall strips can have nonrectangular clipped footprints.
    minimum = min(z for _, z in bottom_profile)-bottom
    footprint = builder.extrude(builder.polyline(points, closed=True), magnitude=height-minimum,
                                position=(0, 0, minimum))
    return ifcopenshell.api.geometry.add_boolean(
        model, first_item=prism, second_items=[footprint], operator="INTERSECTION",
    )[0]


def wall_outline_bounds(wall, thickness):
    tangent = (np.asarray(wall.end)-wall.start)/wall.length
    normal = np.array((-tangent[1], tangent[0]))
    return Polygon([wall.start, wall.end, tuple(np.asarray(wall.end)+normal*thickness),
                    tuple(np.asarray(wall.start)+normal*thickness)]).bounds


def _metadata(model, element, name, properties):
    pset = ifcopenshell.api.pset.add_pset(model, product=element, name=name)
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=properties)
