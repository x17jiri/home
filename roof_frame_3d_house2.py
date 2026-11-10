#!/usr/bin/env python3
"""House 2 timber roof frame, in m/N/Pa; X across the house, Y along the ridge.

Read house2.py as data, without importing IFC or executing the house generator.
See roof_frame_3d_house2.md for loads, joints and support assumptions.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from dataclasses import asdict, dataclass, field, replace
from importlib.metadata import version
from pathlib import Path

import numpy as np

from materials import resolve_timber_grade
from roof_frame_3d import (
    HouseInputs, Timber, check_equilibrium, deformed_member_point,
    maximum_chord_departure, orient_section, plan_collar_force_arrows,
    plan_deflection_status, plan_member_polygon, positive, spring_axial_gap,
)


# USER INPUTS: edit simulation defaults here. Geometry still follows house2.py;
# no loads or simulation settings are read from rafter_load.py.
HOUSE_FILE = Path(__file__).with_name("house2.py")
OUTPUT_PREFIX = Path("roof_frame_3d_house2")
PLOT_COMBINATION = "SLS_symmetric"
DEFORMATION_SCALE = 30.0


@dataclass(frozen=True)
class Settings:
    roof_mass: float = 150.0  # kg/m² of actual slope, including interior finish, excluding modelled timber.
    snow_load: float = 1.5  # Vertical kN/m² of horizontal roof area, already a roof snow load.
    rafter_material: str = "C22"
    beam_material: str = "C22"  # Purlins, posts, connectors, braces and collar ties.
    timber_density: float = 450.0  # kg/m³
    gravity: float = 10.0  # m/s²
    gable_bearings: bool = True
    braces: bool = False
    continuous_purlins: bool = False
    brace_action: str = "compression"
    horizontal_stiffness_kn_mm: float | None = 0.0  # X: 0 free; None rigid; positive spring stiffness. Y fixed.
    joint_stiffness_factor: float = 1000.0  # Numerical rigid-arm multiplier, not joint slip stiffness.

    def __post_init__(self):
        for name in ("roof_mass", "snow_load"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name in ("timber_density", "gravity", "joint_stiffness_factor"):
            positive(getattr(self, name), name)
        for grade in (self.rafter_material, self.beam_material):
            resolve_timber_grade(grade)
        if self.horizontal_stiffness_kn_mm is not None:
            if not math.isfinite(self.horizontal_stiffness_kn_mm) or self.horizontal_stiffness_kn_mm < 0:
                raise ValueError("horizontal stiffness must be finite and non-negative, or None for rigid")
        if self.brace_action not in {"compression", "both"}:
            raise ValueError("brace_action must be compression or both")


class House2Inputs(HouseInputs):
    """Extend the restricted data reader for House 2's rafter comprehensions."""

    def __init__(self, path):
        super().__init__(path)
        self.local_values = {}
        for statement in self.tree.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                self.expressions[statement.target.id] = statement.value

    def evaluate(self, node, visiting=frozenset()):
        if isinstance(node, ast.Constant) and node.value is None:
            return None
        if isinstance(node, ast.Name) and node.id in self.local_values:
            return self.local_values[node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            result = []
            for item in node.elts:
                if isinstance(item, ast.Starred):
                    result.extend(self.evaluate(item.value, visiting))
                else:
                    result.append(self.evaluate(item, visiting))
            return tuple(result)
        if isinstance(node, ast.Set):
            return {self.evaluate(item, visiting) for item in node.elts}
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.FloorDiv, ast.Mod)):
            a, b = self.evaluate(node.left, visiting), self.evaluate(node.right, visiting)
            return a//b if isinstance(node.op, ast.FloorDiv) else a % b
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            a, b = self.evaluate(node.left, visiting), self.evaluate(node.comparators[0], visiting)
            if isinstance(node.ops[0], ast.Gt):
                return a > b
            if isinstance(node.ops[0], ast.Lt):
                return a < b
        if isinstance(node, ast.IfExp):
            return self.evaluate(node.body if self.evaluate(node.test, visiting) else node.orelse, visiting)
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            if any(not isinstance(generator.target, ast.Name) or generator.is_async or generator.ifs
                   for generator in node.generators):
                raise ValueError("only simple numeric house comprehensions are supported")
            previous = self.local_values.copy()
            try:
                result = []

                def collect(index):
                    if index == len(node.generators):
                        result.append(self.evaluate(node.elt, visiting))
                        return
                    generator = node.generators[index]
                    for value in self.evaluate(generator.iter, visiting):
                        self.local_values[generator.target.id] = value
                        collect(index+1)

                collect(0)
                return set(result) if isinstance(node, ast.SetComp) else tuple(result)
            finally:
                self.local_values = previous
        if isinstance(node, ast.Call) and not node.keywords:
            allowed = {"tuple": tuple, "list": tuple, "set": set, "sorted": sorted,
                       "range": range, "max": max, "min": min}
            function = allowed.get(node.func.id) if isinstance(node.func, ast.Name) else None
            if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "math" and node.func.attr in {"floor", "ceil"}):
                function = getattr(math, node.func.attr)
            if function is not None:
                return function(*(self.evaluate(arg, visiting) for arg in node.args))
        return super().evaluate(node, visiting)


@dataclass(frozen=True)
class Beam:
    name: str
    category: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    timber: Timber
    pieces: int = 1
    weight_length: float | None = None  # Physical cut-board length when the axial span is shorter.

    @property
    def length(self):
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class Pin:
    name: str
    axes: tuple[tuple[float, float, float], ...]
    contact: tuple[float, float, float]


@dataclass
class Layout:
    source: Path
    beams: list[Beam] = field(default_factory=list)
    plates: list[Beam] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    seats: dict = field(default_factory=dict)
    bases: list = field(default_factory=list)
    gables: list = field(default_factory=list)
    chords: dict = field(default_factory=dict)
    slope: float = 0.0
    width: float = 0.0
    depth: float = 0.0
    roof_y: tuple = ()
    rafter_y: tuple = ()
    purlin_joints: list = field(default_factory=list)

    @classmethod
    def from_house(cls, path, rafter_material=None, beam_material=None):
        defaults = Settings()
        rafter_material = defaults.rafter_material if rafter_material is None else rafter_material
        beam_material = defaults.beam_material if beam_material is None else beam_material
        data = House2Inputs(path)
        g = data.get
        result = cls(Path(path).resolve())
        width, depth, wall = g("HOUSE_WIDTH"), g("HOUSE_DEPTH"), g("BWT")
        result.width, result.depth = width, depth
        px = tuple(g("PURLIN_X_POSITIONS"))
        rows = tuple(tuple(sorted(row)) for row in g("PURLIN_SUPPORT_Y_POSITIONS"))
        if len(px) not in (2, 3) or len(rows) != len(px) or any(not row for row in rows):
            raise ValueError("House 2 needs two or three purlins and at least one post row per purlin")
        if (any(not math.isfinite(x) for x in px) or
                any(b <= a for a, b in zip(px, px[1:])) or
                not 0 < px[0] < width/2 < px[-1] < width or
                (len(px) == 3 and not math.isclose(px[1], width/2, abs_tol=1e-8))):
            raise ValueError("outer purlins must straddle the ridge; an optional third purlin must be at the ridge")
        if len(px) == 3:
            px = (px[0], width/2, px[-1])
        pwidth, pheight = g("PURLIN_SIZE")
        cwidth, cheight = g("PURLIN_CONNECTION_BEAM_SIZE")
        post_x, post_y = g("PURLIN_SUPPORT_SIZE")
        brace_size, drop = g("PURLIN_BRACE_SIZE"), positive(g("PURLIN_BRACE_DROP"), "brace drop")
        z, base = g("PURLIN_Z"), g("UPPER_FLOOR_START")
        post_top = z-pheight/2
        anchor = post_top-drop
        cross_brace_rise = z-cheight/2-anchor
        if anchor <= base or cross_brace_rise <= 0 or 2*cross_brace_rise >= px[-1]-px[0]-post_x:
            raise ValueError("braces do not fit between the posts or above the floor")
        plate_width, plate_height = g("WALL_PLATE_SIZE")
        top = g("WALL_PLATE_Z")+plate_height/2
        ridge, rafter_size = width/2, g("RAFTER_SIZE")
        # Only the two outer purlins define the slopes. The ridge purlin's
        # flat top meets the same reference planes at its two outside faces.
        ridge_tops = []
        for i, direction in ((0, 1), (len(px)-1, -1)):
            plate_x = wall/2 if direction == 1 else width-wall/2
            seat_x = plate_x-direction*plate_width/2
            contact_x = px[i]-direction*pwidth/2
            slope = (z+pheight/2-top)/(contact_x-seat_x)
            ridge_tops.append(top+slope*(ridge-direction*pwidth/2-seat_x))
        if not math.isclose(*ridge_tops, abs_tol=1e-8):
            raise ValueError("east and west roof planes do not meet symmetrically at the ridge")
        purlin_z = [z]*len(px)
        if len(px) == 3:
            purlin_z[1] = ridge_tops[0]-pheight/2
            if purlin_z[1] <= z:
                raise ValueError("ridge purlin must sit above the outer purlins")
            if px[1]-px[0] <= pwidth or px[2]-px[1] <= pwidth:
                raise ValueError("ridge and outer purlin sections must not overlap")
        overhang = g("WALL_PLATE_OVERHANG")
        if any(any(not math.isfinite(y) or not wall/2 < y < depth-wall/2 for y in row)
               or any(b-a <= 1e-8 for a, b in zip(row, row[1:])) for row in rows):
            raise ValueError("post Y coordinates must be finite, distinct per purlin and inside the gable walls")

        def beam(name, category, start, end, size):
            member = Beam(name, category, tuple(start), tuple(end), Timber(*size, beam_material))
            result.beams.append(member)
            return member

        for i, x in enumerate(px):
            member_z = purlin_z[i]
            post_top = member_z-pheight/2
            anchor = post_top-drop
            name = f"P{i+1}"
            beam(name, "purlin", (x, -overhang, member_z), (x, depth+overhang, member_z), (pwidth, pheight))
            result.gables.extend((name, (x, y, member_z)) for y in (wall/2, depth-wall/2))
            result.chords[name] = tuple(sorted((wall/2, *rows[i], depth-wall/2)))
            for j, y in enumerate(rows[i]):
                name = f"POST{i+1}.{j+1}"
                beam(name, "post", (x, y, base), (x, y, post_top), (post_x, post_y))
                result.bases.append((name, (x, y, base)))
                result.pins.append(Pin(f"purlin_post_{i}_{j}", ((x, y, member_z), (x, y, post_top)), (x, y, post_top)))
                for sign, label in ((-1, "front"), (1, "back")):
                    first = (x, y+sign*post_y/2, anchor)
                    last = (x, first[1]+sign*drop, post_top)
                    if not -overhang <= last[1] <= depth+overhang:
                        continue
                    name = f"BRACE{i+1}.{j+1}.{label}"
                    beam(name, "brace", first, last, brace_size)
                    result.pins.extend((Pin(name+"_lower", ((x, y, anchor),), first),
                                        Pin(name+"_upper", ((x, last[1], member_z),), last)))
                if i not in (0, len(px)-1):
                    # Existing transverse connectors stay at the outer-purlin
                    # height, below the ridge-post brace anchors.
                    continue
                sign = 1 if i == 0 else -1
                first = (x+sign*post_x/2, y, anchor)
                last = (first[0]+sign*cross_brace_rise, y, z-cheight/2)
                name = f"BRACE{i+1}.{j+1}.cross"
                beam(name, "brace", first, last, brace_size)
                result.pins.extend((Pin(name+"_lower", ((x, y, anchor),), first),
                                    Pin(name+"_upper", ((last[0], y, z),), last)))
        cross_rows = tuple(g("PURLIN_CONNECTION_Y_POSITIONS"))
        if len(set(cross_rows)) != len(cross_rows):
            raise ValueError("purlin connector Y positions must be distinct")
        for j, y in enumerate(cross_rows):
            cross = beam(f"CROSS{j+1}", "cross_beam", (px[0]+pwidth/2, y, z),
                         (px[-1]-pwidth/2, y, z), (cwidth, cheight))
            result.chords[cross.name] = (cross.start[0], cross.end[0])
            for i, endpoint in ((0, cross.start), (len(px)-1, cross.end)):
                result.pins.append(Pin(f"purlin_cross_{i}_{j}", ((px[i], y, z), endpoint), endpoint))

        result.rafter_y = tuple(g("RAFTER_Y_POSITIONS"))
        if len(result.rafter_y) < 2 or any(b <= a for a, b in zip(result.rafter_y, result.rafter_y[1:])):
            raise ValueError("rafter Y coordinates must be strictly increasing")
        result.roof_y = (-g("ROOF_GABLE_OVERHANG"), depth+g("ROOF_GABLE_OVERHANG"))
        ridge_heights = []
        for i, side in enumerate(("E", "W")):
            plate_x = wall/2 if i == 0 else width-wall/2
            direction = 1 if i == 0 else -1
            seat_x = plate_x-direction*plate_width/2
            outer_index = 0 if i == 0 else len(px)-1
            purlin_x = px[outer_index]-direction*pwidth/2
            slope = (z+pheight/2-top)/(purlin_x-seat_x)
            cosine = 1/math.sqrt(1+slope*slope)
            centre_offset = (g("RAFTER_Z_OFFSET")+rafter_size[1]/2)/cosine

            def point(x, y):
                return (x, y, top+slope*(x-seat_x)+centre_offset)

            ridge_heights.append(point(ridge, 0)[2])
            result.slope = abs(slope)
            result.plates.append(Beam(f"PLATE_{side}", "wall_plate",
                                      (plate_x, -overhang, g("WALL_PLATE_Z")),
                                      (plate_x, depth+overhang, g("WALL_PLATE_Z")),
                                      Timber(plate_width, plate_height, beam_material)))
            for j, y in enumerate(result.rafter_y):
                name = f"R{j+1:02d}{side}"
                eave = -g("ROOF_EAVE_OVERHANG") if i == 0 else width+g("ROOF_EAVE_OVERHANG")
                member = Beam(name, "rafter", point(eave, y), point(ridge, y), Timber(*rafter_size, rafter_material))
                result.beams.append(member)
                seat, purlin_seat = point(seat_x, y), point(purlin_x, y)
                result.seats[name] = (seat, purlin_seat, side, y)
                result.chords[name] = tuple(sorted((math.dist(member.start, seat), math.dist(member.start, purlin_seat), member.length)))
                result.pins.append(Pin(name+"_purlin", (purlin_seat, (px[outer_index], y, z)),
                                       (purlin_x, y, z+pheight/2)))
                if len(px) == 3:
                    ridge_face_x = ridge-direction*pwidth/2
                    ridge_seat = point(ridge_face_x, y)
                    result.pins.append(Pin(name+"_ridge_purlin", (ridge_seat, (ridge, y, purlin_z[1])),
                                           (ridge_face_x, y, purlin_z[1]+pheight/2)))
                    result.chords[name] = tuple(sorted((*result.chords[name], math.dist(member.start, ridge_seat))))
        if not math.isclose(*ridge_heights, abs_tol=1e-8):
            raise ValueError("east and west rafter axes do not meet at the ridge")
        tie_size = tuple(positive(value, "collar tie dimension") for value in g("COLLAR_TIE_SIZE"))
        tie_z = z+pheight/2+tie_size[1]/2
        rafters = {b.name: b for b in result.beams if b.category == "rafter"}
        for j, y in enumerate(result.rafter_y, 1):
            ends, cut_ends = [], []
            for side in ("E", "W"):
                rafter = rafters[f"R{j:02d}{side}"]
                first, delta = np.array(rafter.start), np.array(rafter.end)-rafter.start
                fraction = (tie_z-first[2])/delta[2]
                if not 0 < fraction < 1:
                    raise ValueError(f"collar height must intersect {rafter.name} below the ridge")
                ends.append(tuple(first+fraction*delta))
                # Physical boards extend past the bolts to the upper rafter
                # faces. Integrating the sloped end cuts gives this mean length.
                cosine = abs(delta[0])/rafter.length
                cut_fraction = (tie_z-first[2]-rafter_size[1]/(2*cosine))/delta[2]
                cut_ends.append(first+cut_fraction*delta)
            result.beams.append(Beam(
                f"CT{j:02d}", "collar", *ends, Timber(*tie_size, beam_material),
                pieces=2, weight_length=float(cut_ends[1][0]-cut_ends[0][0]),
            ))
        return result


@dataclass
class RoofModel:
    model: object
    layout: Layout
    settings: Settings
    supports: dict = field(default_factory=dict)
    support_kinds: dict = field(default_factory=dict)
    loads: list = field(default_factory=list)
    nodal_loads: list = field(default_factory=list)
    brace_springs: dict = field(default_factory=dict)
    collar_springs: dict = field(default_factory=dict)
    seat_nodes: dict = field(default_factory=dict)
    joint_members: list = field(default_factory=list)
    tributary_widths: dict = field(default_factory=dict)


def tributary_widths(stations, low, high):
    if low >= high or stations[0] < low or stations[-1] > high:
        raise ValueError("roof bounds must enclose all rafter stations")
    edges = (low, *((a+b)/2 for a, b in zip(stations, stations[1:])), high)
    return tuple(b-a for a, b in zip(edges, edges[1:]))


def split_purlins_at_posts(layout):
    """Split at every post, with shared translations at each post axis."""
    if layout.purlin_joints:
        return layout
    beams, joints = [], []
    chords, gables = dict(layout.chords), []
    for beam in layout.beams:
        if beam.category != "purlin":
            beams.append(beam)
            continue
        cuts = sorted(point[1] for _, point in layout.bases
                      if math.isclose(point[0], beam.start[0], abs_tol=1e-8))
        if (not cuts or not beam.start[1] < cuts[0] <= cuts[-1] < beam.end[1]
                or any(b-a <= 1e-8 for a, b in zip(cuts, cuts[1:]))):
            raise ValueError(f"{beam.name} requires distinct post cuts inside its length")
        x, _, z = beam.start
        points = (beam.start, *((x, y, z) for y in cuts), beam.end)
        references = chords.pop(beam.name)
        pieces = []
        for index, (start, end) in enumerate(zip(points, points[1:]), 1):
            piece = replace(beam, name=f"{beam.name}.{index}", start=start, end=end)
            beams.append(piece)
            pieces.append(piece)
            chords[piece.name] = tuple(y for y in references if start[1]-1e-8 <= y <= end[1]+1e-8)
        joints.extend((left.name, right.name, left.end) for left, right in zip(pieces, pieces[1:]))
        for label, point in layout.gables:
            if label == beam.name:
                owner = next(piece for piece in pieces if piece.start[1] <= point[1] <= piece.end[1])
                gables.append((owner.name, point))
    return replace(layout, beams=beams, chords=chords, gables=gables, purlin_joints=joints)


def build_roof_model(layout, settings=Settings()):
    from Pynite import FEModel3D
    if not settings.continuous_purlins:
        layout = split_purlins_at_posts(layout)
    if not settings.braces:
        excluded = {b.name for b in layout.beams if b.category == "brace"}
        excluded_pins = {name+suffix for name in excluded for suffix in ("_lower", "_upper")}
        layout = replace(layout,
                         beams=[b for b in layout.beams if b.name not in excluded],
                         pins=[pin for pin in layout.pins if pin.name not in excluded_pins])
    model = FEModel3D()
    result = RoofModel(model, layout, settings)
    nodes, structural = {}, set()

    def node(point, physical=False):
        key = tuple(round(float(v), 10) for v in point)
        if key not in nodes:
            name = f"N{len(nodes):04d}"
            nodes[key] = name
            # Round only the lookup key. PyNite's collinearity tolerance is
            # tighter than 1e-10 m on short arms, so retain exact coordinates.
            model.add_node(name, *(float(v) for v in point))
        name = nodes[key]
        if physical:
            structural.add(name)
        return name

    for grade_name in {b.timber.material for b in layout.beams}:
        grade = resolve_timber_grade(grade_name)
        model.add_material(grade.name, grade.elastic_modulus_pa, grade.shear_modulus_pa, .3, 0)
    model.add_material("JOINT", 10e9*settings.joint_stiffness_factor, .63e9*settings.joint_stiffness_factor, .3, 0)
    model.add_section("JOINT", .02, .0001, .0001, .0001)
    for beam in layout.beams:
        if beam.category in {"brace", "collar"}:
            is_collar = beam.category == "collar"
            first, last = node(beam.start, is_collar), node(beam.end, is_collar)
            model.add_spring(beam.name, first, last,
                             resolve_timber_grade(beam.timber.material).elastic_modulus_pa
                             *beam.timber.width*beam.timber.height*beam.pieces/beam.length,
                             comp_only=not is_collar and settings.brace_action == "compression")
            (result.collar_springs if is_collar else result.brace_springs)[beam.name] = beam.name
            weight = (settings.gravity*settings.timber_density*beam.timber.width*beam.timber.height
                      *beam.pieces*(beam.length if beam.weight_length is None else beam.weight_length))
            for end in (first, last):
                model.add_node_load(end, "FZ", -weight/2, case="G")
                result.nodal_loads.append((end, "G", (0, 0, -weight/2)))
            continue
        model.add_section(beam.name, *beam.timber.properties)
        model.add_member(beam.name, node(beam.start, True), node(beam.end, True), beam.timber.material, beam.name)
        member = model.members[beam.name]
        if beam.category == "cross_beam":
            # An X-aligned connector with ideal pin ends can spin rigidly
            # about X. Choose its section orientation without adding a
            # translational support or restraining its bending rotations.
            model.def_support(member.i_node.name, False, False, False, True, False, False)
        elif beam.category == "post":
            # The pinned vertical post has an unloaded spin about its Z
            # axis. Set only that orientation, leaving both bending axes free.
            model.def_support(member.j_node.name, False, False, False, False, False, True)
        if math.hypot(member.j_node.X-member.i_node.X, member.j_node.Y-member.i_node.Y) > 1e-8:
            orient_section(member)
        q = -settings.timber_density*settings.gravity*beam.timber.width*beam.timber.height
        model.add_member_dist_load(beam.name, "FZ", q, q, case="G")
        result.loads.append((beam.name, "G", q, 0, beam.length))
    for left, right, point in layout.purlin_joints:
        # Release both bending rotations on one side of the common node.
        # Axial/shear translations and roll compatibility remain connected.
        model.def_releases(left, Ryj=True, Rzj=True)
    for pin in layout.pins:
        contact = node(pin.contact)
        for point in pin.axes:
            root = node(point, True)
            if root == contact:
                continue
            name = f"JOINT{len(result.joint_members):03d}"
            model.add_member(name, root, contact, "JOINT", "JOINT")
            model.def_releases(name, Rxj=True, Ryj=True, Rzj=True)
            result.joint_members.append(name)
    for name in model.nodes:
        if name not in structural:
            # Only massless pin-node rotations: every incident arm releases them.
            model.def_support(name, False, False, False, True, True, True)
    for label, point in layout.bases:
        name = node(point, True)
        model.def_support(name, True, True, True)
        result.supports[name], result.support_kinds[name] = label, "post_base"
    if settings.gable_bearings:
        for label, point in layout.gables:
            name = node(point, True)
            model.def_support(name, True, True, True, False, True, False)
            result.supports[name], result.support_kinds[name] = label, "gable_bearing"
    for name, (seat, _, side, _) in layout.seats.items():
        n = node(seat, True)
        rigid = settings.horizontal_stiffness_kn_mm is None
        model.def_support(n, rigid, True, True, False, False, True)
        if not rigid and settings.horizontal_stiffness_kn_mm > 0:
            model.def_support_spring(n, "DX", settings.horizontal_stiffness_kn_mm*1e6)
        result.supports[n], result.support_kinds[n] = f"{name}/PLATE_{side}", "wall_plate_seat"
        result.seat_nodes[name] = n
        model.def_releases(name, Rxj=True, Ryj=True, Rzj=True)
        ridge = model.members[name].j_node.name
        model.def_support(ridge, False, False, False, True, True, True)
    widths = tributary_widths(layout.rafter_y, *layout.roof_y)
    for beam in (b for b in layout.beams if b.category == "rafter"):
        seat, _, side, y = layout.seats[beam.name]
        width = widths[layout.rafter_y.index(y)]
        result.tributary_widths[beam.name] = width
        cosine = abs(beam.end[0]-beam.start[0])/beam.length
        for case, q in (("G", -settings.roof_mass*settings.gravity*width),
                        (f"S_{side}", -settings.snow_load*1000*width*cosine)):
            model.add_member_dist_load(beam.name, "FZ", q, q, case=case)
            result.loads.append((beam.name, case, q, 0, beam.length))
    for limit, g, s in (("SLS", 1.0, 1.0), ("ULS", 1.35, 1.5)):
        model.add_load_combo(f"{limit}_dead", {"G": g})
        for pattern, east, west in (("symmetric", 1, 1), ("east", 1, .5), ("west", .5, 1)):
            model.add_load_combo(f"{limit}_{pattern}", {"G": g, "S_E": s*east, "S_W": s*west})
    return result


def solve_roof_model(roof):
    if not roof.brace_springs or roof.settings.brace_action == "both":
        roof.model.analyze_linear(check_stability=True)
    else:
        # First-order opening/reclosing active set, using the pinned solver version.
        from Pynite import Analysis
        model = roof.model
        Analysis._prepare_model(model)
        free, fixed, known = Analysis._partition_D(model)
        for combo in model.load_combos.values():
            p, _ = Analysis._partition(model, model.P(combo.name), free, fixed)
            fer, _ = Analysis._partition(model, model.FER(combo.name), free, fixed)
            for iteration in range(100):
                k11, k12, _, _ = Analysis._partition(model, model.Ke(combo.name, check_stability=False, sparse=True), free, fixed)
                d = Analysis._solve_unknown_disp(k11, p-fer-k12@known, sparse=True, check_stability=True)
                Analysis._store_displacements(model, d, known, free, fixed, combo)
                changes = []
                for name in roof.brace_springs:
                    spring = model.springs[name]
                    compression = -spring.ks*spring_axial_gap(spring, combo.name)
                    if spring.active[combo.name] and compression < -1e-5:
                        changes.append((spring, False))
                    elif not spring.active[combo.name] and compression > 1e-5:
                        changes.append((spring, True))
                if not changes:
                    break
                for spring, active in changes:
                    spring.active[combo.name] = active
            else:
                raise ValueError(f"brace contact did not converge: {combo.name}")
        Analysis._calc_reactions(model, log=False)
        model.solution = "Nonlinear TC"
    return check_equilibrium(roof)


def support_rows(roof):
    rows = []
    for name, label in roof.supports.items():
        n = roof.model.nodes[name]
        for combo in roof.model.load_combos:
            rows.append(dict(support=name, member=label, kind=roof.support_kinds[name], combination=combo,
                             x_m=n.X, y_m=n.Y, z_m=n.Z,
                             Dx_mm=n.DX[combo]*1000, Dy_mm=n.DY[combo]*1000, Dz_mm=n.DZ[combo]*1000,
                             horizontal_mm=math.hypot(n.DX[combo], n.DY[combo])*1000,
                             # Force delivered TO the foundation/wall; positive Z means uplift.
                             Fx_kN=-n.RxnFX[combo]/1000, Fy_kN=-n.RxnFY[combo]/1000,
                             Fz_kN=-n.RxnFZ[combo]/1000))
    return rows


def purlin_support_load_envelopes(supports):
    """Worst downward base load for each post and limit state (kN, +down)."""
    worst = {}
    for row in supports:
        if row["kind"] != "post_base":
            continue
        limit = row["combination"].split("_", 1)[0]
        if limit not in {"SLS", "ULS"}:
            continue
        key = (row["member"], limit)
        # The support CSV uses +Z upward, i.e. downward loading is negative.
        if key not in worst or row["Fz_kN"] < worst[key]["Fz_kN"]:
            worst[key] = row
    return [dict(post=post, limit_state=limit, combination=row["combination"],
                 x_m=row["x_m"], y_m=row["y_m"], z_m=row["z_m"],
                 downward_kN=-row["Fz_kN"])
            for (post, limit), row in worst.items()]


def member_rows(roof):
    rows, chord_rows = [], []
    for beam in roof.layout.beams:
        for combo in roof.model.load_combos:
            row = dict(member=beam.name, category=beam.category, material=beam.timber.material,
                       combination=combo, width_mm=beam.timber.width*1000, height_mm=beam.timber.height*1000,
                       length_m=beam.length, pieces=beam.pieces,
                       weight_length_m=beam.length if beam.weight_length is None else beam.weight_length)
            if beam.category in {"brace", "collar"}:
                spring = roof.model.springs[beam.name]
                compression = -spring.ks*spring_axial_gap(spring, combo) if spring.active[combo] else 0.0
                if beam.category == "collar":
                    row.update(axial_min_kN=compression/1000, axial_max_kN=compression/1000,
                               axial_stiffness_kN_per_m=spring.ks/1000)
                else:
                    row.update(compression_kN=compression/1000, active=spring.active[combo])
                    if roof.settings.brace_action == "compression" and compression < -1e-5:
                        raise ValueError("a compression-only brace carries tension")
            else:
                member = roof.model.members[beam.name]
                row.update(axial_min_kN=member.min_axial(combo)/1000, axial_max_kN=member.max_axial(combo)/1000,
                           My_abs_kNm=max(abs(member.min_moment("My", combo)), abs(member.max_moment("My", combo)))/1000,
                           Mz_abs_kNm=max(abs(member.min_moment("Mz", combo)), abs(member.max_moment("Mz", combo)))/1000,
                           shear_y_abs_kN=max(abs(member.min_shear("Fy", combo)), abs(member.max_shear("Fy", combo)))/1000,
                           shear_z_abs_kN=max(abs(member.min_shear("Fz", combo)), abs(member.max_shear("Fz", combo)))/1000)
                points = np.linspace(0, member.L(), 41)
                displacement = [deformed_member_point(member, x, combo)[2]
                                -(beam.start[2]+(beam.end[2]-beam.start[2])*x/member.L()) for x in points]
                row["max_sampled_vertical_mm"] = max(abs(d) for d in displacement)*1000
                if combo.startswith("SLS") and beam.name in roof.layout.chords:
                    references = roof.layout.chords[beam.name]
                    if beam.category == "purlin" and not roof.settings.gable_bearings:
                        gable_y = [point[1] for label, point in roof.layout.gables if label == beam.name]
                        references = tuple(y for y in references
                                           if not any(math.isclose(y, wall_y, abs_tol=1e-8) for wall_y in gable_y))
                    if beam.category in {"purlin", "cross_beam"}:
                        references = tuple(x-(beam.start[1] if beam.category == "purlin" else beam.start[0]) for x in references)
                    for a, b in zip(references, references[1:]):
                        delta, station = maximum_chord_departure(member, combo, a, b)
                        span = b-a
                        chord_rows.append(dict(member=beam.name, combination=combo, start_m=a, end_m=b,
                                               span_m=span, departure_mm=delta*1000, at_m=station,
                                               L300_limit_mm=span/300*1000, L300_status="PASS" if delta <= span/300 else "FAIL",
                                               L500_limit_mm=span/500*1000, L500_status="PASS" if delta <= span/500 else "FAIL"))
            rows.append(row)
    return rows, chord_rows


def purlin_deflection_failure_messages(beams, chords):
    """Explain failed purlin limits, keeping the worst SLS case per span."""
    purlins = {beam.name for beam in beams if beam.category == "purlin"}
    worst = {}
    for row in chords:
        if row["member"] not in purlins or not row["combination"].startswith("SLS_"):
            continue
        key = (row["member"], row["start_m"], row["end_m"])
        if key not in worst or row["departure_mm"] > worst[key]["departure_mm"]:
            worst[key] = row
    messages = []
    for key in sorted(worst):
        row = worst[key]
        for ratio in (300, 500):
            if row[f"L{ratio}_status"] == "FAIL":
                messages.append(
                    f"  {row['member']}, {row['combination']}: L/{ratio} failed; "
                    f"maximum allowed {row[f'L{ratio}_limit_mm']:.3f} mm, "
                    f"actual {row['departure_mm']:.3f} mm "
                    f"(span {row['start_m']:.3f}–{row['end_m']:.3f} m along member)"
                )
    return messages


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)


COLORS = {"rafter": "#98652f", "purlin": "#2477a8", "cross_beam": "#af4f8b", "post": "#307a48", "brace": "#dc9a22", "collar": "#d000d0"}
PLAN_CHECK_COLORS = {"L500": "#39a852", "L300": "#f4a340", "fail": "#d9534f", "not_assessed": "#c8ccd0"}


def horizontal_restraint_description(stiffness):
    if stiffness is None:
        return "X fixed; Y fixed"
    if stiffness == 0:
        return "X free (zero X restraint force); Y fixed"
    return f"X spring {stiffness:g} kN/mm; Y fixed"


def purlin_configuration_description(roof):
    if roof.settings.continuous_purlins:
        return "continuous"
    counts = {}
    for beam in roof.layout.beams:
        if beam.category == "purlin":
            name = beam.name.split(".")[0]
            counts[name] = counts.get(name, 0)+1
    if len(set(counts.values())) == 1:
        return f"{next(iter(counts.values()))} pieces each"
    return "; ".join(f"{name}: {count} pieces" for name, count in counts.items())


def plan_check_statuses(beams, chords):
    """Use the old plan's worst-SLS classification with House 2's chord rows."""
    grouped = {}
    for row in chords:
        grouped.setdefault(row["member"], []).append(dict(
            combination=row["combination"],
            chord_L300_status=row["L300_status"], chord_L500_status=row["L500_status"],
        ))
    return {beam.name: plan_deflection_status(grouped.get(beam.name, [])) for beam in beams}


def plot_plan_report(roof, chords, path, *, combination="SLS_symmetric"):
    """Undeformed member footprints coloured by chord checks over all SLS cases."""
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon

    if combination not in roof.model.load_combos:
        raise ValueError(f"unknown force combination: {combination}")
    figure = Figure(figsize=(14, 12))
    ax = figure.add_subplot()
    figure.subplots_adjust(left=.08, right=.96, bottom=.22, top=.88)
    beams = (*roof.layout.beams, *roof.layout.plates)
    statuses = plan_check_statuses(beams, chords)
    order = {"wall_plate": 0, "brace": 1, "purlin": 2, "cross_beam": 3,
             "rafter": 4, "post": 5, "collar": 6}
    for beam in sorted(beams, key=lambda b: order[b.category]):
        start, end = np.asarray(beam.start[:2]), np.asarray(beam.end[:2])
        if np.linalg.norm(end-start) < 1e-9:
            x, y = start
            w, h = beam.timber.width/2, beam.timber.height/2
            footprint = np.array(((x-w,y-h), (x+w,y-h), (x+w,y+h), (x-w,y+h)))
        else:
            footprint = plan_member_polygon(beam)
        is_collar = beam.category == "collar"
        patch = Polygon(
            footprint, closed=True,
            facecolor="none" if is_collar else PLAN_CHECK_COLORS[statuses[beam.name]],
            edgecolor=COLORS["collar"] if is_collar else "#333333",
            linewidth=1.2 if is_collar else .6,
            zorder=order[beam.category]+2,
        )
        patch.set_gid(beam.name)
        ax.add_patch(patch)
        middle = (start+end)/2
        if beam.category == "rafter":
            ax.text(*middle, beam.name, ha="center", va="center", fontsize=6.5, zorder=12,
                    bbox=dict(facecolor="white", alpha=.8, edgecolor="none", pad=.5))
        elif beam.category == "collar":
            spring = roof.model.springs[beam.name]
            tension = spring.ks*spring_axial_gap(spring, combination)/1000
            centre, arrows = plan_collar_force_arrows(beam, tension, offset=.16, length=.35, gap=1.1)
            for tail, head in arrows:
                ax.annotate("", xy=head, xytext=tail, zorder=14,
                            arrowprops=dict(arrowstyle="-|>", color=COLORS["collar"], lw=1))
            ax.text(*centre, f"{beam.name} {tension:+.2f} kN", fontsize=6,
                    color=COLORS["collar"], ha="center", va="center", zorder=15,
                    bbox=dict(facecolor="white", alpha=.9, edgecolor="none", pad=.5))
        elif beam.category in {"purlin", "cross_beam", "wall_plate"}:
            ax.annotate(beam.name, middle, xytext=(4, 5), textcoords="offset points",
                        fontsize=7, zorder=12,
                        bbox=dict(facecolor="white", alpha=.85, edgecolor="none", pad=.5))

    reactions = support_rows(roof)
    worst_uplift = {}
    for row in reactions:
        if row["support"] not in worst_uplift or row["Fz_kN"] > worst_uplift[row["support"]]["Fz_kN"]:
            worst_uplift[row["support"]] = row
        if row["combination"] != combination or row["kind"] != "wall_plate_seat":
            continue
        force = np.array((row["Fx_kN"], row["Fy_kN"]))
        magnitude = np.linalg.norm(force)
        origin = np.array((row["x_m"], row["y_m"]))
        if magnitude > 1e-5:
            ax.annotate("", xy=origin+.45*force/magnitude, xytext=origin, zorder=16,
                        arrowprops=dict(arrowstyle="-|>", color="#182d55", lw=1))
        side = -1 if row["x_m"] < roof.layout.width/2 else 1
        ax.text(row["x_m"]+side*.6, row["y_m"], f"{side*row['Fx_kN']:+.2f}",
                fontsize=6.5, ha="right" if side < 0 else "left", va="center",
                color="#182d55", zorder=17,
                bbox=dict(facecolor="white", alpha=.95, edgecolor="none", pad=.5))
    for row in worst_uplift.values():
        ax.scatter(row["x_m"], row["y_m"], facecolors="white", edgecolors="#333333",
                   s=14, linewidths=.5, zorder=13)
        if row["Fz_kN"] > 1e-5:
            ax.scatter(row["x_m"], row["y_m"], s=200, facecolors="none", edgecolors="red",
                       linewidths=1.6, zorder=18)
            ax.annotate(f"{row['Fz_kN']:.2f} kN uplift", (row["x_m"], row["y_m"]),
                        xytext=(10, 12), textcoords="offset points", color="red", fontsize=7, zorder=18)
    for left, right, point in roof.layout.purlin_joints:
        ax.plot(*point[:2], marker="D", markerfacecolor="white", markeredgecolor="#1565c0",
                markersize=5, linestyle="none", zorder=19)
    ax.set(xlabel="X — east to west [m]", ylabel="Y — street to garden [m]")
    ax.set_aspect("equal")
    ax.margins(x=.15, y=.05)
    ax.grid(alpha=.15, linewidth=.5)
    figure.suptitle("House 2 roof deflection checks — top view", fontsize=15, y=.97)
    figure.text(.5, .935, "Worst instantaneous chord checks over ALL SLS combinations; undeformed member positions\n"
                f"Force arrows: {combination}; red circles: uplift envelope over all combinations\n"
                f"Wall-plate X/Y restraint: {horizontal_restraint_description(roof.settings.horizontal_stiffness_kn_mm)}; "
                f"braces: {roof.settings.brace_action if roof.settings.braces else 'off'}; "
                f"purlins: {purlin_configuration_description(roof)}",
                ha="center", va="top", fontsize=9)
    descriptions = {
        "L500": "Green: L/300 and L/500 pass",
        "L300": "Orange: L/500 fails, L/300 passes",
        "fail": "Red: L/300 fails",
        "not_assessed": "Grey: no chord check / rigid support",
    }
    handles = [Patch(facecolor=PLAN_CHECK_COLORS[key], edgecolor="#333333", label=description)
               for key, description in descriptions.items()]
    handles.append(Patch(facecolor="none", edgecolor=COLORS["collar"],
                         label="Magenta: axial collar ties, unassessed"))
    handles.append(Line2D([], [], color="#182d55", label="Blue: force delivered to wall plate"))
    if roof.layout.purlin_joints:
        handles.append(Line2D([], [], marker="D", markerfacecolor="white", markeredgecolor="#1565c0",
                              linestyle="none", label="Blue diamonds: purlin bending hinges above posts"))
    figure.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .09), ncol=2,
                  fontsize=9, frameon=False)
    figure.text(.5, .065,
                "Wall-plate labels: + outward / − inward [kN]. Collar labels: + tension / − compression [kN per board pair].",
                ha="center", fontsize=8)
    figure.text(.5, .04,
                "Colours show deflection checks only; strength, buckling, creep and connections are not checked.",
                ha="center", fontsize=8)
    figure.savefig(path, dpi=180)
    return figure


def draw_results(roof, path, *, plan=False, combination="SLS_symmetric", scale=30, chords=None):
    if plan:
        return plot_plan_report(roof, member_rows(roof)[1] if chords is None else chords,
                                path, combination=combination)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure = plt.figure(figsize=(13, 9))
    ax = figure.add_subplot(projection="3d")
    labelled = set()
    for beam in (*roof.layout.beams, *roof.layout.plates):
        original = np.linspace(beam.start, beam.end, 25)
        category = beam.category
        if category == "wall_plate":
            moved = original
        elif category in {"brace", "collar"}:
            spring = roof.model.springs[beam.name]
            d = np.array([[getattr(n, dof)[combination] for dof in ("DX", "DY", "DZ")]
                          for n in (spring.i_node, spring.j_node)])
            moved = original+scale*np.linspace(*d, 25)
        else:
            member = roof.model.members[beam.name]
            moved = np.array([deformed_member_point(member, x, combination) for x in np.linspace(0, member.L(), 25)])
            moved = original+scale*(moved-original)
        color = COLORS.get(category, "#555555")
        coordinates = lambda p: tuple(p.T)
        ax.plot(*coordinates(original), color=color, alpha=.25, lw=1)
        inactive = category == "brace" and not roof.model.springs[beam.name].active[combination]
        ax.plot(*coordinates(moved), color=color, lw=1.3, ls="--" if inactive else "-",
                label=category if category not in labelled else None)
        labelled.add(category)
    reactions = support_rows(roof)
    worst = {}
    for row in reactions:
        if row["support"] not in worst or row["Fz_kN"] > worst[row["support"]]["Fz_kN"]:
            worst[row["support"]] = row
    for row in worst.values():
        coordinates = (row["x_m"], row["y_m"], row["z_m"])
        ax.scatter(*coordinates, color="black", s=9)
        if row["Fz_kN"] > 1e-5:
            ax.scatter(*coordinates, s=180, facecolors="none", edgecolors="red", linewidths=1.6)
            ax.text(*coordinates, f"  {row['Fz_kN']:.2f} kN uplift", color="red", fontsize=7)
    for left, right, point in roof.layout.purlin_joints:
        ax.scatter(*point, marker="D", s=28, facecolors="white", edgecolors="#1565c0")
    ax.set(xlabel="X — east to west [m]", ylabel="Y — street to garden [m]")
    figure.suptitle(f"House 2 roof: {combination}; deformation ×{scale:g}\n"
                   "red circles: support uplift envelope over all combinations\n"
                   f"Wall-plate X/Y restraint: {horizontal_restraint_description(roof.settings.horizontal_stiffness_kn_mm)}; "
                   f"braces: {roof.settings.brace_action if roof.settings.braces else 'off'}; "
                   f"purlins: {purlin_configuration_description(roof)}",
                   fontsize=12)
    ax.set_zlabel("Z [m]")
    ax.set_box_aspect((roof.layout.width, roof.layout.depth, 4))
    ax.view_init(elev=23, azim=-55)
    ax.legend(loc="upper left", fontsize=8)
    figure.tight_layout(rect=(0, 0, 1, .92))
    figure.savefig(path, dpi=170)
    plt.close(figure)


def horizontal_stiffness(value):
    if value.lower() == "rigid":
        return None
    stiffness = 0.0 if value.lower() == "free" else float(value)
    if not math.isfinite(stiffness) or stiffness < 0:
        raise argparse.ArgumentTypeError("use free, rigid, or a non-negative stiffness in kN/mm")
    return stiffness


def parse_arguments(argv=None):
    defaults = Settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house", type=Path, default=HOUSE_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT_PREFIX)
    parser.add_argument("--rafter-material", default=defaults.rafter_material, type=lambda x: resolve_timber_grade(x).name)
    parser.add_argument("--beam-material", default=defaults.beam_material, type=lambda x: resolve_timber_grade(x).name)
    parser.add_argument("--roof-mass", type=float, default=defaults.roof_mass, help="kg/m² actual sloped area")
    parser.add_argument("--snow", type=float, default=defaults.snow_load, help="kN/m² horizontal roof area")
    parser.add_argument("--timber-density", type=float, default=defaults.timber_density, help="kg/m³")
    parser.add_argument("--gravity", type=float, default=defaults.gravity, help="m/s²")
    parser.add_argument("--gable-bearings", choices=("on", "off"), default="on" if defaults.gable_bearings else "off")
    parser.add_argument("--braces", action=argparse.BooleanOptionalAction, default=defaults.braces,
                        help="include the tesařské pásky")
    parser.add_argument("--continuous-purlins", action=argparse.BooleanOptionalAction, default=defaults.continuous_purlins,
                        help="use continuous purlins instead of splitting at each post with bending hinges")
    parser.add_argument("--brace-action", choices=("compression", "both"), default=defaults.brace_action,
                        help="when braces are enabled: compression only or tension/compression")
    parser.add_argument("--horizontal-stiffness", type=horizontal_stiffness, default=defaults.horizontal_stiffness_kn_mm,
                        help="X restraint at each wall-plate seat: free, rigid, or kN/mm; Y always fixed")
    parser.add_argument("--joint-stiffness-factor", type=float, default=defaults.joint_stiffness_factor)
    parser.add_argument("--plot-combination", default=PLOT_COMBINATION)
    parser.add_argument("--deformation-scale", type=float, default=DEFORMATION_SCALE)
    args = parser.parse_args(argv)
    positive(args.deformation_scale, "deformation scale")
    settings = replace(defaults, roof_mass=args.roof_mass, snow_load=args.snow,
                       rafter_material=args.rafter_material, beam_material=args.beam_material,
                       timber_density=args.timber_density, gravity=args.gravity,
                       gable_bearings=args.gable_bearings == "on", braces=args.braces, brace_action=args.brace_action,
                       continuous_purlins=args.continuous_purlins,
                       horizontal_stiffness_kn_mm=args.horizontal_stiffness,
                       joint_stiffness_factor=args.joint_stiffness_factor)
    return args, settings


def main(argv=None):
    args, settings = parse_arguments(argv)
    layout = Layout.from_house(args.house, settings.rafter_material, settings.beam_material)
    roof = build_roof_model(layout, settings)
    layout = roof.layout
    print(f"Roof angle: {math.degrees(math.atan(layout.slope)):.2f}° ({layout.slope*100:.2f}%)")
    print(f"Loads: roof layers {settings.roof_mass:g} kg/m² slope; snow {settings.snow_load:g} kN/m² plan; timber {settings.timber_density:g} kg/m³; g={settings.gravity:g}")
    print(f"Members: {len(layout.beams)}; gable bearings {'on' if settings.gable_bearings else 'off'}; "
          f"braces {settings.brace_action if settings.braces else 'off'}")
    print(f"Purlins: {purlin_configuration_description(roof)}"
          + ("" if settings.continuous_purlins else ", bending hinges above each post"))
    purlin_levels = {b.name.split(".")[0]: (b.start[0], b.start[2]+b.timber.height/2)
                     for b in layout.beams if b.category == "purlin"}
    for name, (x, top_z) in purlin_levels.items():
        print(f"  {name}: X={x:.3f} m, top Z={top_z:.3f} m "
              f"({top_z-layout.bases[0][1][2]:.3f} m above ceiling top)")
    print(f"Collar ties: {sum(b.category == 'collar' for b in layout.beams)} axial pairs, "
          f"{sum(b.pieces for b in layout.beams if b.category == 'collar')} boards; ideal pinned connections")
    print(f"Materials: rafters {settings.rafter_material}, other timber {settings.beam_material}")
    restraint = horizontal_restraint_description(settings.horizontal_stiffness_kn_mm)
    print(f"Rafter-to-wall-plate horizontal restraint: {restraint}")
    if args.plot_combination not in roof.model.load_combos:
        raise ValueError(f"unknown plot combination; choose {', '.join(roof.model.load_combos)}")
    equilibrium = solve_roof_model(roof)
    rows, chords = member_rows(roof)
    supports = support_rows(roof)
    post_loads = purlin_support_load_envelopes(supports)
    stem = args.output
    stem.parent.mkdir(parents=True, exist_ok=True)
    write_csv(f"{stem}_members.csv", rows)
    write_csv(f"{stem}_supports.csv", supports)
    write_csv(f"{stem}_purlin_support_loads.csv", post_loads)
    write_csv(f"{stem}_deflections.csv", chords)
    metadata = dict(source=str(layout.source), settings=asdict(settings),
                    purlin_joints=[dict(left=left, right=right, point=point) for left, right, point in layout.purlin_joints],
                    members=[asdict(member) for member in layout.beams],
                    materials=dict(rafter=settings.rafter_material, other=settings.beam_material),
                    versions={name: version(name) for name in ("PyniteFEA", "numpy", "matplotlib")},
                    equilibrium_residuals=equilibrium, combinations={k: v.factors for k, v in roof.model.load_combos.items()},
                    tributary_widths_m=roof.tributary_widths,
                    assumptions=["First-order elastic; no buckling, strength, creep or fastener-capacity verification.",
                                 "Ideal pins with massless stiff eccentric arms; enabled braces are axial, without connection slip.",
                                 "Post bases and wall/gable bearings anchored; uplift is force delivered upward to the support.",
                                 "Wall plates/ring beams and supporting slab immovable; slab and walls not designed here.",
                                 "Prismatic rafter axes end at vertical eaves; local horizontal end cuts/notches omitted.",
                                 "No roof diaphragm, wind, chimney load, or wall-plate self-weight in roof-frame reactions."])
    metadata["assumptions"].extend([
        f"Tesařské pásky {'included as '+settings.brace_action+' axial springs' if settings.braces else 'excluded, including their self-weight and attachment arms'}.",
        "Purlins continuous." if settings.continuous_purlins else
        f"Purlins split at every post ({purlin_configuration_description(roof)}); both bending rotations released at each cut, with axial/shear and roll compatibility retained.",
        "Purlins bear directly on posts; connector ends are pinned to the purlin inner faces at purlin centre height.",
        "One connector X rotation is fixed only to remove unloaded axial spin; no translational support or bending fixity is added.",
        "One post Z rotation is fixed only to remove unloaded axial spin; no translational support or bending fixity is added.",
        f"Rafter-to-wall-plate translation restraint: {restraint}; vertical support and yaw restraint retained.",
        "Each collar spring represents two boards, axial stiffness 2EA/L, connected to the rafter axes at tie-centre height.",
        "Collar self-weight includes sloped board ends and is shared between its two rafter joints; no direct roof/snow load.",
        "Collar joints have no slip; no collar bending, buckling, fastener or chimney-clearance verification.",
    ])
    if len(purlin_levels) == 3:
        metadata["assumptions"].extend([
            "Ridge purlin height follows the roof reference planes at its two outer top corners; outer purlins define both slopes.",
            "Both rafter halves bear on the ridge purlin through ideal pins at its outer faces; roof/snow loads are unchanged.",
            "Ridge posts extend directly to the ceiling; lower transverse connectors remain between outer purlins, with no joint to the crossing ridge posts.",
            "Ridge posts have optional longitudinal braces only; no transverse brace to the lower connectors is added.",
            "Enabled gable bearings apply to all three purlins, including the raised ridge purlin; masonry bearing geometry is not verified.",
        ])
    Path(f"{stem}_basis.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
    for plan, suffix in ((False, "model"), (True, "plan")):
        draw_results(roof, f"{stem}_{suffix}.png", plan=plan, combination=args.plot_combination,
                     scale=args.deformation_scale, chords=chords)
    movement = max((r for r in supports if r["kind"] == "wall_plate_seat"), key=lambda r: r["horizontal_mm"])
    print(f"Maximum wall-plate seat horizontal movement: {movement['horizontal_mm']:.4f} mm ({movement['member']}, {movement['combination']})")
    for limit in ("SLS", "ULS"):
        worst_move = max((r for r in supports if r["kind"] == "wall_plate_seat"
                          and r["combination"].startswith(limit+"_")), key=lambda r: r["horizontal_mm"])
        print(f"  {limit} maximum: {worst_move['horizontal_mm']:.4f} mm "
              f"(Dx={worst_move['Dx_mm']:+.4f}, Dy={worst_move['Dy_mm']:+.4f} mm; "
              f"{worst_move['member']}, {worst_move['combination']})")
    for axis in ("x", "y"):
        maximum_force = max(abs(r[f"F{axis}_kN"]) for r in supports if r["kind"] == "wall_plate_seat")
        print(f"Maximum wall-plate {axis.upper()} restraint force: {maximum_force:.6f} kN")
    print("Purlin post base loads: maximum downward force per post and limit state; "
          "includes post self-weight (+ down, - uplift)")
    for row in post_loads:
        equivalent_kg = row["downward_kN"]*1000/settings.gravity
        print(f"  {row['post']} (X={row['x_m']:.3f}, Y={row['y_m']:.3f} m), "
              f"{row['limit_state']}: {row['downward_kN']:.3f} kN "
              f"(~{equivalent_kg:.0f} kg at g={settings.gravity:g}); {row['combination']}")
    uplift = [r for r in supports if r["Fz_kN"] > 1e-5]
    print(f"Maximum support uplift: {max((r['Fz_kN'] for r in uplift), default=0):.3f} kN; {len({r['support'] for r in uplift})} marked locations")
    print(f"Instantaneous chord checks: {sum(r['L300_status']=='FAIL' for r in chords)} L/300 failures; {sum(r['L500_status']=='FAIL' for r in chords)} L/500 failures")
    failures = purlin_deflection_failure_messages(layout.beams, chords)
    if failures:
        print("Purlin deflection failures (worst SLS combination per support span):")
        print("\n".join(failures))
    else:
        print("Purlin deflection checks: all support spans pass L/300 and L/500.")
    worst = max(chords, key=lambda row: row["departure_mm"]/row["L300_limit_mm"])
    print(f"Governing L/300 chord: {worst['member']}, {worst['combination']}: {worst['departure_mm']:.3f} / {worst['L300_limit_mm']:.3f} mm")
    print(f"Maximum relative equilibrium residual: {max(equilibrium.values()):.3g}")
    print(f"Saved {stem}_{{model,plan}}.png, CSV results and _basis.json")


if __name__ == "__main__":
    main()
