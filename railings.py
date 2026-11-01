"""Path-based IFC railings. All path coordinates are world XYZ, in metres."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from math import ceil, isfinite

import ifcopenshell
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import numpy as np


@dataclass(frozen=True)
class RailingPath(Sequence):
    """A pitch-line path with an optional actual support-surface height resolver.

    Stair helpers retain the tread profile here, so posts and balusters stand
    on treads rather than floating on the sloping line between their nosings.
    Ordinary lists/tuples are also accepted by the railing factory.
    """

    points: tuple
    support_height: Callable | None = None

    def __len__(self):
        return len(self.points)

    def __getitem__(self, index):
        return self.points[index]

    def extended(self, points):
        """Return a longer path, preserving its stair/landing support resolver."""
        return RailingPath((*self.points, *points), self.support_height)


class Railing(ifcopenshell.entity_instance):
    """One IfcRailing with a continuous handrail, posts and optional balusters."""

    def __init__(self, element, storey, *, path, height, post_positions, baluster_positions):
        super().__init__(element.wrapped_data, element.file)
        for name, value in dict(storey=storey, path=path, height=height,
                                post_positions=post_positions,
                                baluster_positions=baluster_positions).items():
            object.__setattr__(self, name, value)

    @property
    def element(self):
        return self


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return float(value)


def _size(value, name):
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must contain two dimensions")
    try:
        width, depth = value
    except (TypeError, ValueError):
        raise TypeError(f"{name} must contain two dimensions") from None
    return _positive(width, f"{name} width"), _positive(depth, f"{name} depth")


def create_railing(storey, name, *, path, height=1.0, post_spacing=.9,
                   infill="vertical", material="Wood", color=None,
                   post_size=(.06, .06), handrail_size=(.06, .04),
                   baluster_size=(.025, .025), baluster_spacing=.12):
    """Create a railing along a world-coordinate base/pitch-line polyline.

    Height is vertical to the handrail top; section heights are vertical too.
    Spacings are maximum horizontal centre distances. Corner posts are shared.
    Repeating the first point closes a railing; consecutive duplicates are
    ignored. Members retain one material and one semantic IfcRailing body.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("railing name must be a nonempty string")
    if not isinstance(material, str) or not material.strip():
        raise ValueError("railing material must be a nonempty string")
    height, post_spacing = _positive(height, "height"), _positive(post_spacing, "post_spacing")
    baluster_spacing = _positive(baluster_spacing, "baluster_spacing")
    post_w, post_d = _size(post_size, "post_size")
    rail_w, rail_h = _size(handrail_size, "handrail_size")
    baluster_w, baluster_d = _size(baluster_size, "baluster_size")
    if height <= rail_h:
        raise ValueError("height must exceed the handrail height")
    if infill not in {"vertical", "none"}:
        raise ValueError("infill must be 'vertical' or 'none'")
    if isinstance(path, (str, bytes)):
        raise TypeError("path must be a sequence of XYZ points")
    try:
        supplied = list(path)
    except TypeError:
        raise TypeError("path must be a sequence of XYZ points") from None
    points = []
    for point in supplied:
        if isinstance(point, (str, bytes)):
            raise TypeError("path points must contain three finite coordinates")
        try:
            x, y, z = point
        except (TypeError, ValueError):
            raise TypeError("path points must contain three finite coordinates") from None
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (x, y, z)):
            raise ValueError("path coordinates must be finite numbers")
        p = np.array((x, y, z), dtype=float)
        if not points or np.linalg.norm(p-points[-1]) > 1e-9:
            points.append(p)
    if len(points) < 2:
        raise ValueError("path must contain at least two distinct points")
    closed = np.linalg.norm(points[0]-points[-1]) <= 1e-9
    if closed and len(points) < 4:
        raise ValueError("a closed railing needs at least three corners")
    deltas = np.diff(points, axis=0)
    lengths = np.linalg.norm(deltas[:, :2], axis=1)
    if np.any(lengths <= 1e-9):
        raise ValueError("railing segments must have a horizontal run")
    tangents = deltas[:, :2] / lengths[:, None]
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0]))
    slopes = deltas[:, 2] / lengths
    offsets = []
    for i in range(len(points)):
        if not closed and i == 0:
            offset = normals[0]
        elif not closed and i == len(points)-1:
            offset = normals[-1]
        else:
            previous, following = normals[(i-1) % len(normals)], normals[i % len(normals)]
            denominator = 1+np.dot(previous, following)
            if denominator <= 1e-8:
                raise ValueError("railing path must not reverse direction at a corner")
            offset = (previous+following)/denominator
        offsets.append(offset)

    support_height = path.support_height if isinstance(path, RailingPath) else None
    vertices, faces = [], []
    # One continuous rectangular handrail, including shared mitered corner rings.
    rail_points = [p.copy() for p in points]
    if not closed:
        for index, segment, sign in ((0, 0, -1), (-1, -1, 1)):
            extension = post_d/2
            rail_points[index][:2] += sign*extension*tangents[segment]
            rail_points[index][2] += sign*extension*slopes[segment]
    rail_vertices = []
    for p, offset in zip(rail_points, offsets):
        for side, dz in ((-1, -rail_h), (1, -rail_h), (1, 0), (-1, 0)):
            xy = p[:2]+side*offset*rail_w/2
            rail_vertices.append((float(xy[0]), float(xy[1]), float(p[2]+height+dz)))
    rail_faces = [] if closed else [(3, 2, 1, 0)]
    for i in range(len(points)-1):
        for j in range(4):
            a, b, c, d = 4*i+j, 4*i+(j+1)%4, 4*(i+1)+(j+1)%4, 4*(i+1)+j
            rail_faces.extend(((a, b, c), (a, c, d)))
    if not closed:
        rail_faces.append(tuple(4*(len(points)-1)+j for j in range(4)))
    vertices.append(rail_vertices)
    faces.append(rail_faces)

    posts, cells = {}, []
    for i, length in enumerate(lengths):
        divisions = max(1, ceil(float(length)/post_spacing))
        for j in range(divisions+1):
            p = points[i]+deltas[i]*(j/divisions)
            key = tuple(np.round(p, 9))
            posts.setdefault(key, (p, i, []))[2].append(i)
        for j in range(divisions):
            cells.append((i, j/divisions, (j+1)/divisions))

    def vertical_member(p, segment, width, depth, adjacent):
        bottom = float(support_height(tuple(p))) if support_height is not None else float(p[2])
        if not isfinite(bottom):
            raise ValueError("railing support heights must be finite")
        tangent, normal = tangents[segment], normals[segment]
        xy = [p[:2]+along*tangent*depth/2+across*normal*width/2
              for along, across in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        tops = [min(float(points[k][2]+np.dot(q-points[k][:2], tangents[k])*slopes[k])
                    for k in adjacent)+height-rail_h for q in xy]
        if min(tops) <= bottom:
            raise ValueError("railing height does not leave room above its support")
        vertices.append([*(tuple(q)+(bottom,) for q in xy),
                         *(tuple(q)+(z,) for q, z in zip(xy, tops))])
        faces.append([(3, 2, 1, 0), (4, 5, 6), (4, 6, 7), (0, 1, 5, 4),
                      (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
        return (float(p[0]), float(p[1]), bottom)

    post_positions = tuple(vertical_member(p, i, post_w, post_d, adjacent)
                           for p, i, adjacent in posts.values())
    baluster_positions = []
    if infill == "vertical":
        for i, lo, hi in cells:
            count = max(0, ceil(float(lengths[i]*(hi-lo))/baluster_spacing)-1)
            for j in range(1, count+1):
                fraction = lo+(hi-lo)*j/(count+1)
                p = points[i]+deltas[i]*fraction
                baluster_positions.append(vertical_member(p, i, baluster_w, baluster_d, (i,)))

    house, model = storey.house, storey.house.model
    style = house._surface_style("beam", transparency=0.0, color=color if color is not None else
                                "#8B5A2B" if material.casefold() == "wood" else None)
    element = ifcopenshell.api.root.create_entity(model, ifc_class="IfcRailing", name=name,
                                                 predefined_type="GUARDRAIL")
    ifcopenshell.api.spatial.assign_container(model, products=[element], relating_structure=storey.element)
    ifcopenshell.api.geometry.edit_object_placement(model, product=element, matrix=np.eye(4), is_si=True)
    # The mesh API converts its vertex batches to a rectangular NumPy array.
    # Keep the variable-length handrail separate from the eight-vertex posts.
    body = ifcopenshell.api.geometry.add_mesh_representation(model, context=house._body_context,
                                                            vertices=vertices[:1], faces=faces[:1])
    members = ifcopenshell.api.geometry.add_mesh_representation(model, context=house._body_context,
                                                               vertices=vertices[1:], faces=faces[1:])
    body.Items = (*body.Items, *members.Items)
    model.remove(members)
    ifcopenshell.api.geometry.assign_representation(model, product=element, representation=body)
    if style is not None:
        ifcopenshell.api.style.assign_representation_styles(model, shape_representation=body, styles=[style])
    if material not in house._materials:
        house._materials[material] = ifcopenshell.api.material.add_material(model, name=material)
    ifcopenshell.api.material.assign_material(model, products=[element], type="IfcMaterial",
                                             material=house._materials[material])
    pset = ifcopenshell.api.pset.add_pset(model, product=element, name="BBIM_Railing")
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties={
        "Path": json.dumps([p.tolist() for p in points]), "Height": height,
        "PostSpacing": post_spacing, "PostSize": json.dumps((post_w, post_d)),
        "HandrailSize": json.dumps((rail_w, rail_h)), "Infill": infill,
        "BalusterSize": json.dumps((baluster_w, baluster_d)), "BalusterSpacing": baluster_spacing,
        "PostCount": len(post_positions), "BalusterCount": len(baluster_positions),
    })
    return Railing(element, storey, path=tuple(tuple(p) for p in points), height=height,
                   post_positions=post_positions, baluster_positions=tuple(baluster_positions))
