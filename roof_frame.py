#!/usr/bin/env python3
"""Preliminary, first-order 2D analysis of a normal roof cross-section.

Run ``python3 roof_frame.py``. Edit the explicit check calls in main() for
sections/materials/spacing. IFC geometry is read as arithmetic constants, NOT
by importing house_ifc (which would generate the building). No IFC is changed.

This is a force/displacement model, not a complete EC5 verification: connections,
notches, instability, wind, ring beams and the dormer need separate checks.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from math import atan, ceil, cos, degrees, hypot, isfinite
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from rafter_load import (
    CalculationReport,
    GRAVITY_M_S2,
    PERMANENT_LOAD_FACTOR,
    ROOF_LAYERS_KG_M2,
    SNOW_LOAD_FACTOR,
    SNOW_LOAD_KN_M2,
    TIMBER_DENSITY_KG_M3,
    _resolve_timber_grade,
)


def _positive(value: float, name: str) -> float:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


@dataclass(frozen=True)
class Section:
    width: float
    height: float
    elastic_modulus: float  # Pa
    pieces: int = 1

    def __post_init__(self):
        for name in ("width", "height", "elastic_modulus"):
            _positive(getattr(self, name), name)
        if isinstance(self.pieces, bool) or not isinstance(self.pieces, int) or self.pieces < 1:
            raise ValueError("pieces must be a positive integer")

    @property
    def area(self):
        return self.pieces * self.width * self.height

    @property
    def inertia(self):
        # Separate side-by-side collar boards: sum EI, no composite action.
        return self.pieces * self.width * self.height**3 / 12

    @property
    def modulus(self):
        return self.pieces * self.width * self.height**2 / 6


@dataclass(frozen=True)
class Node:
    name: str
    y: float
    z: float


@dataclass(frozen=True)
class Element:
    name: str
    start: int
    end: int
    section: Section
    member: str
    start_rotation: str
    end_rotation: str


@dataclass(frozen=True)
class ElementResponse:
    length: float
    local_displacements: np.ndarray
    end_forces: np.ndarray
    q_axial: float
    q_transverse: float
    section: Section

    def forces(self, x):
        """N tension-positive, V and sagging M in local axes; N/Nm units."""
        a, v, m = self.end_forces[:3]
        return (-a - self.q_axial * x,
                v + self.q_transverse * x,
                -m + v * x + self.q_transverse * x**2 / 2)

    def displacement(self, x):
        """Exact within a uniformly loaded Euler-Bernoulli element.

        Hermite nodal interpolation alone omits the load's interior bubble;
        retaining it also makes a single element reproduce simple-beam sag.
        """
        t = x / self.length
        u1, v1, r1, u2, v2, r2 = self.local_displacements
        axial = ((1-t)*u1 + t*u2 + self.q_axial*x*(self.length-x)
                 / (2*self.section.elastic_modulus*self.section.area))
        transverse = ((1-3*t**2+2*t**3)*v1
                      + self.length*(t-2*t**2+t**3)*r1
                      + (3*t**2-2*t**3)*v2
                      + self.length*(-t**2+t**3)*r2
                      + self.q_transverse*x**2*(self.length-x)**2
                      / (24*self.section.elastic_modulus*self.section.inertia))
        return axial, transverse

    def force_extrema(self):
        points = [0.0, self.length]
        if self.q_transverse:
            stationary = -self.end_forces[1] / self.q_transverse
            if 0 < stationary < self.length:
                points.append(stationary)
        values = np.array([self.forces(x) for x in points])
        return dict(tension=max(0.0, values[:, 0].max()),
                    compression=max(0.0, -values[:, 0].min()),
                    shear=max(abs(values[:, 1])),
                    moment=max(abs(values[:, 2])))


@dataclass(frozen=True)
class FrameResult:
    displacements: np.ndarray
    reactions: Mapping[int, tuple[float, float]]
    elements: tuple[ElementResponse, ...]
    rotation_dofs: Mapping[tuple[int, str], int]
    load_vector: np.ndarray
    residual: np.ndarray

    def member_extrema(self, model: "Frame", member: str):
        responses = [response for element, response in zip(model.elements, self.elements)
                     if element.member == member]
        if not responses:
            raise ValueError(f"unknown member {member!r}")
        extrema = [response.force_extrema() for response in responses]
        return {name: max(value[name] for value in extrema) for name in extrema[0]}

    def maximum_displacement(self, model: "Frame", member: str, *, vertical=True):
        maximum = 0.0
        for element, response in zip(model.elements, self.elements):
            if element.member != member:
                continue
            start, end = model.nodes[element.start], model.nodes[element.end]
            c = (end.y-start.y)/response.length
            s = (end.z-start.z)/response.length
            for x in np.linspace(0, response.length, 81):
                u, v = response.displacement(x)
                maximum = max(maximum, abs(s*u+c*v) if vertical else hypot(u, v))
        return maximum


class Frame:
    """Small linear plane-frame solver, SI units, independent pin rotations.

    Elements at a joint share translations. Only equal rotation-group names
    share rotations: the collar ends and the two ridge rafters are thus pins,
    while the rafter remains continuous at its collar and purlin nodes.
    """

    def __init__(self):
        self.nodes: list[Node] = []
        self.elements: list[Element] = []
        self.supports: dict[int, tuple[bool, bool]] = {}
        self.fixed_rotations: set[tuple[int, str]] = set()

    def add_node(self, name, y, z):
        if not isfinite(y) or not isfinite(z):
            raise ValueError("node coordinates must be finite")
        self.nodes.append(Node(name, y, z))
        return len(self.nodes)-1

    def add_element(self, name, start, end, section, *, member="beam",
                    start_rotation="continuous", end_rotation="continuous"):
        if not 0 <= start < len(self.nodes) or not 0 <= end < len(self.nodes):
            raise ValueError("invalid element node")
        if hypot(self.nodes[end].y-self.nodes[start].y,
                 self.nodes[end].z-self.nodes[start].z) <= 1e-9:
            raise ValueError("element length must be positive")
        self.elements.append(Element(name, start, end, section, member,
                                     start_rotation, end_rotation))
        return len(self.elements)-1

    def fix_node(self, node, *, horizontal=True, vertical=True):
        if not 0 <= node < len(self.nodes):
            raise ValueError("invalid support node")
        self.supports[node] = horizontal, vertical

    def fix_rotation(self, node, group="continuous"):
        self.fixed_rotations.add((node, group))

    def element_matrices(self, element):
        a, b = self.nodes[element.start], self.nodes[element.end]
        length = hypot(b.y-a.y, b.z-a.z)
        c, s = (b.y-a.y)/length, (b.z-a.z)/length
        transform = np.array([[c, s, 0, 0, 0, 0], [-s, c, 0, 0, 0, 0],
                              [0, 0, 1, 0, 0, 0], [0, 0, 0, c, s, 0],
                              [0, 0, 0, -s, c, 0], [0, 0, 0, 0, 0, 1.]])
        ea = element.section.elastic_modulus*element.section.area/length
        ei = element.section.elastic_modulus*element.section.inertia
        b12, b6, b4, b2 = 12*ei/length**3, 6*ei/length**2, 4*ei/length, 2*ei/length
        stiffness = np.array([
            [ea, 0, 0, -ea, 0, 0], [0, b12, b6, 0, -b12, b6],
            [0, b6, b4, 0, -b6, b2], [-ea, 0, 0, ea, 0, 0],
            [0, -b12, -b6, 0, b12, -b6], [0, b6, b2, 0, -b6, b4]])
        return length, transform, stiffness

    def solve(self, uniform_loads: Mapping[int, tuple[float, float]], *,
              nodal_loads: Mapping[int, tuple[float, float]] | None = None):
        """Distributed global (horizontal, vertical) loads in N/m of member."""
        if not self.elements:
            raise ValueError("frame needs elements")
        if any(index not in range(len(self.elements)) for index in uniform_loads):
            raise ValueError("unknown loaded element")
        rotations = {}
        for element in self.elements:
            for key in ((element.start, element.start_rotation),
                        (element.end, element.end_rotation)):
                if key not in rotations:
                    rotations[key] = 2*len(self.nodes)+len(rotations)
        size = 2*len(self.nodes)+len(rotations)
        stiffness, force = np.zeros((size, size)), np.zeros(size)
        data = []
        for index, element in enumerate(self.elements):
            length, transform, local_stiffness = self.element_matrices(element)
            qy, qz = uniform_loads.get(index, (0., 0.))
            if not isfinite(qy) or not isfinite(qz):
                raise ValueError("loads must be finite")
            axial, transverse = transform[:2, :2] @ [qy, qz]
            local_force = np.array([axial*length/2, transverse*length/2,
                                    transverse*length**2/12, axial*length/2,
                                    transverse*length/2, -transverse*length**2/12])
            dofs = np.array([2*element.start, 2*element.start+1,
                             rotations[element.start, element.start_rotation],
                             2*element.end, 2*element.end+1,
                             rotations[element.end, element.end_rotation]])
            stiffness[np.ix_(dofs, dofs)] += transform.T @ local_stiffness @ transform
            force[dofs] += transform.T @ local_force
            data.append((length, transform, local_stiffness, local_force, dofs, axial, transverse))
        for node, loads in (nodal_loads or {}).items():
            if node not in range(len(self.nodes)) or not all(isfinite(q) for q in loads):
                raise ValueError("invalid nodal load")
            force[2*node:2*node+2] += loads
        fixed = set()
        for node, constraints in self.supports.items():
            fixed.update(2*node+direction for direction, constrained in enumerate(constraints)
                         if constrained)
        for key in self.fixed_rotations:
            if key not in rotations:
                raise ValueError("unknown fixed rotation")
            fixed.add(rotations[key])
        free = np.array([i for i in range(size) if i not in fixed], dtype=int)
        displacements = np.zeros(size)
        reduced = stiffness[np.ix_(free, free)]
        # Diagonal scaling avoids mistaking mixed translation/rotation units for
        # instability. Cholesky rejects unrestrained/mechanism models.
        diagonal = np.diag(reduced)
        if np.any(diagonal <= 0):
            raise ValueError("unstable frame: an unrestrained degree of freedom")
        scale = np.sqrt(diagonal)
        scaled = reduced / np.outer(scale, scale)
        if free.size:
            try:
                if np.linalg.eigvalsh(scaled)[0] <= 1e-12:
                    raise np.linalg.LinAlgError("mechanism")
                lower = np.linalg.cholesky(scaled)
                solution = np.linalg.solve(lower.T, np.linalg.solve(lower, force[free]/scale))
            except np.linalg.LinAlgError as exc:
                raise ValueError("unstable frame: check supports and releases") from exc
            displacements[free] = solution/scale
        residual = stiffness @ displacements - force
        if free.size and max(abs(residual[free])) > 1e-6*max(1., max(abs(force))):
            raise ArithmeticError("frame equilibrium residual is too large")
        responses = []
        for element, values in zip(self.elements, data):
            length, transform, k, f, dofs, axial, transverse = values
            local_u = transform @ displacements[dofs]
            responses.append(ElementResponse(length, local_u, k @ local_u-f,
                                              axial, transverse, element.section))
        reactions = {node: tuple(residual[2*node:2*node+2]) for node in self.supports}
        return FrameResult(displacements, reactions, tuple(responses), rotations, force, residual)


class _HouseConstants:
    """Read only named arithmetic/tuple constants; never execute IFC code."""

    def __init__(self, path):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        self.expressions = {}
        self.cache = {}
        for statement in tree.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        self.expressions[target.id] = statement.value

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        if name not in self.expressions:
            raise ValueError(f"missing house geometry constant {name}")
        try:
            result = self.evaluate(self.expressions[name], {name})
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            raise ValueError(f"cannot read {name} without executing house_ifc: {exc}") from exc
        self.cache[name] = result
        return result

    def evaluate(self, expression, visiting):
        if isinstance(expression, ast.Constant) and type(expression.value) in (int, float):
            return expression.value
        if isinstance(expression, (ast.Tuple, ast.List)):
            return tuple(self.evaluate(value, visiting) for value in expression.elts)
        if isinstance(expression, ast.Name):
            if expression.id in visiting:
                raise ValueError("cyclic geometry expression")
            if expression.id not in self.expressions:
                raise ValueError(f"unknown constant {expression.id}")
            return self.evaluate(self.expressions[expression.id], visiting | {expression.id})
        if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, (ast.UAdd, ast.USub)):
            value = self.evaluate(expression.operand, visiting)
            return value if isinstance(expression.op, ast.UAdd) else -value
        if isinstance(expression, ast.Subscript):
            return self.evaluate(expression.value, visiting)[self.evaluate(expression.slice, visiting)]
        if isinstance(expression, ast.BinOp):
            left, right = self.evaluate(expression.left, visiting), self.evaluate(expression.right, visiting)
            if isinstance(expression.op, ast.Add):
                return left+right
            if isinstance(expression.op, ast.Sub):
                return left-right
            if isinstance(expression.op, ast.Mult):
                return left*right
            if isinstance(expression.op, ast.Div):
                return left/right
        raise ValueError(f"unsupported expression {type(expression).__name__}; use numeric constants")


@dataclass(frozen=True)
class RoofGeometry:
    left_wall: float
    right_wall: float
    left_purlin: float
    right_purlin: float
    ridge: float
    left_eave: float
    right_eave: float
    slope: float
    left_axis_z: float
    collar_z: float
    floor_z: float
    collar_lowering: float

    def __post_init__(self):
        if not all(isfinite(value) for value in self.__dict__.values()):
            raise ValueError("roof coordinates must be finite")
        if not (self.left_eave <= self.left_wall < self.left_purlin < self.ridge
                < self.right_purlin < self.right_wall <= self.right_eave):
            raise ValueError("invalid roof support order")
        _positive(self.slope, "slope")
        if abs(self.right_wall-(2*self.ridge-self.left_wall)) > 1e-8:
            raise ValueError("this model requires symmetric normal-roof geometry")
        if not 0 < self.collar_z-self.left_axis_z < self.slope*(self.ridge-self.left_wall):
            raise ValueError("collar must lie above wall plate and below ridge")

    @classmethod
    def from_house(cls, path: str | Path, *, rafter_height: float, lowered=False):
        """Centre-line geometry of the symmetric NORMAL roof, not the dormer."""
        _positive(rafter_height, "rafter_height")
        values = _HouseConstants(path)
        p1, _, p2 = values.get("STREET_ROOF_PLANE_POINTS")
        garden_points = values.get("GARDEN_ROOF_PLANE_POINTS")
        ridge = values.get("HALF_DEPTH")
        if any(abs(a-b) > 1e-8
               for street, garden in zip(values.get("STREET_ROOF_PLANE_POINTS"), garden_points)
               for a, b in zip((street[0], 2*ridge-street[1], street[2]), garden)):
            raise ValueError("normal garden roof is not a mirror of street roof; extend the model")
        slope = (p1[2]-p2[2])/(p1[1]-p2[1])
        left_wall = values.get("STREET_WALL_PLATE_Y")
        right_wall = values.get("GARDEN_WALL_PLATE_Y")
        angle = atan(slope)
        axis_z = (p2[2]+slope*(left_wall-p2[1])
                  + (values.get("RAFTER_Z_OFFSET")+rafter_height/2)/cos(angle))
        floor_z = values.get("UPPER_FLOOR_START")
        lowering = values.get("VAZNICE_EXTRA_HEIGHT") if lowered else 0.
        collar_z = (floor_z+values.get("COLLAR_TIE_TOP_HEIGHT")
                    - values.get("COLLAR_TIE_SIZE")[1]/2 - lowering)
        return cls(left_wall, right_wall,
                   values.get("HALF_DEPTH")-values.get("VAZNICE_DIST"),
                   values.get("HALF_DEPTH")+values.get("VAZNICE_DIST"),
                   values.get("HALF_DEPTH"), values.get("STREET_ROOF_EAVE_Y"),
                   values.get("GARDEN_ROOF_EAVE_Y"), slope, axis_z, collar_z,
                   floor_z, lowering)

    @property
    def angle(self):
        return degrees(atan(self.slope))

    def z(self, y):
        return self.left_axis_z + self.slope * (min(y, 2*self.ridge-y)-self.left_wall)

    @property
    def collar_y(self):
        left = self.left_wall+(self.collar_z-self.left_axis_z)/self.slope
        return left, 2*self.ridge-left


@dataclass(frozen=True)
class HouseRoofSection:
    """An actual normal main-rafter line and its tributary roof strip."""

    x: float
    spacing: float
    width: float
    height: float
    collar_width: float
    collar_height: float
    collar_pieces: int
    geometry: RoofGeometry

    @classmethod
    def from_house(cls, path: str | Path, *, rafter_x: float | None = None):
        values = _HouseConstants(path)
        entries = values.expressions.get("rafters")
        if not isinstance(entries, (ast.List, ast.Tuple)):
            raise ValueError("rafters must be an explicit list for the section reader")
        normal_width, height = values.get("RAFTER_SIZE")
        collar_width, collar_height = values.get("COLLAR_TIE_SIZE")
        for value, name in ((normal_width, "rafter width"), (height, "rafter height"),
                            (collar_width, "collar width"), (collar_height, "collar height")):
            _positive(value, name)
        layout = []
        paired_positions = []
        for entry in entries.elts:
            width, paired, split = normal_width, False, False
            position = entry
            if isinstance(entry, ast.Tuple):
                if (len(entry.elts) != 2 or not isinstance(entry.elts[1], ast.Constant)
                        or entry.elts[1].value not in {"before", "after", "+before", "+after"}):
                    raise ValueError("unsupported paired rafter definition")
                position, paired = entry.elts[0], True
            elif isinstance(entry, ast.Call):
                # Recognise data wrappers, never execute them or arbitrary calls.
                if not isinstance(entry.func, ast.Name) or entry.keywords:
                    raise ValueError("unsupported rafter wrapper")
                if entry.func.id == "StrongerRafter" and len(entry.args) == 1:
                    position = entry.args[0]
                    width, stronger_height = values.get("STRONGER_RAFTER_SIZE")
                    if stronger_height != height:
                        raise ValueError("stronger rafter height must match the normal height")
                elif entry.func.id == "SplitRafter" and len(entry.args) == 2:
                    position, split = entry.args[0], True
                else:
                    raise ValueError("unsupported rafter wrapper")
            x = values.evaluate(position, {"rafters"})
            if not isfinite(x):
                raise ValueError("rafter x must be finite")
            layout.append((x, width, paired, split))
            if paired:
                paired_positions.append(x)
        layout.sort()
        if any(a[0] == b[0] for a, b in zip(layout, layout[1:])):
            raise ValueError("duplicate main rafter positions")
        candidates = []
        for index, (x, width, paired, split) in enumerate(layout):
            if index == 0 or index == len(layout)-1:
                continue  # Roof-edge tributary widths require a separate model.
            if x < values.get("CUT_WIDTH") or x > values.get("HOUSE_WIDTH"):
                continue
            if paired or split or (paired_positions and min(paired_positions) < x < max(paired_positions)):
                continue  # No cut-corner/window/dormer geometry in this normal section.
            left, right = layout[index-1], layout[index+1]
            spacing = (right[0]-left[0])/2
            pieces = sum(abs(neighbour[0]-x-(width+neighbour[1])/2*sign) > 1e-9
                         for neighbour, sign in ((left, -1), (right, 1)))
            board_xs = [x+sign*(width+collar_width)/2
                        for neighbour, sign in ((left, -1), (right, 1))
                        if abs(neighbour[0]-x-(width+neighbour[1])/2*sign) > 1e-9]
            lowered = [values.get("MIDDLE_PURLIN_X_MIN") <= board_x <= values.get("MIDDLE_PURLIN_X_MAX")
                       for board_x in board_xs]
            if not lowered or len(set(lowered)) != 1:
                continue  # Two different collar elevations need two actual members.
            geometry = RoofGeometry.from_house(path, rafter_height=height, lowered=lowered[0])
            candidates.append(cls(x, spacing, width, height, collar_width, collar_height, pieces, geometry))
        if rafter_x is not None:
            for candidate in candidates:
                if abs(candidate.x-rafter_x) < 1e-9:
                    return candidate
            raise ValueError("selected rafter is not an interior, uncut normal roof section")
        if not candidates:
            raise ValueError("no supported normal roof section in the current rafters layout")
        # Largest tributary width among eligible actual lines, not a fictitious
        # 750 mm spacing. This is not an envelope of the dormer/corner sections.
        return max(candidates, key=lambda item: item.spacing)


def build_roof_frame(geometry: RoofGeometry, rafter: Section, collar: Section | None, *,
                     restrain_purlins: bool, maximum_element_length=0.35):
    """Physical continuous rafters + pinned collar boards + hinged ridge.

    Purlins are ideal vertical supports here, NOT beams in the cross-section.
    restrain_purlins means in-plane horizontal translation restraint; it does
    not mean torsional or out-of-plane buckling restraint of the purlin itself.
    """
    _positive(maximum_element_length, "maximum_element_length")
    model = Frame()
    names = {geometry.left_eave: "Levý přesah", geometry.left_wall: "Pozednice L",
             geometry.left_purlin: "Vaznice L", geometry.collar_y[0]: "Kleština L",
             geometry.ridge: "Hřeben", geometry.collar_y[1]: "Kleština P",
             geometry.right_purlin: "Vaznice P", geometry.right_wall: "Pozednice P",
             geometry.right_eave: "Pravý přesah"}
    # Merge coincident physical nodes (a collar may be exactly at a purlin).
    positions = sorted(set(names))
    physical = {y: model.add_node(names[y], y, geometry.z(y)) for y in positions}
    for first, last in zip(positions, positions[1:]):
        length = hypot(last-first, geometry.z(last)-geometry.z(first))
        steps = max(1, ceil(length/maximum_element_length))
        nodes = [physical[first]]
        for step in range(1, steps):
            y = first+(last-first)*step/steps
            nodes.append(model.add_node(f"Krokev {len(model.nodes)}", y, geometry.z(y)))
        nodes.append(physical[last])
        side = "rafter_left" if last <= geometry.ridge else "rafter_right"
        for start, end in zip(nodes, nodes[1:]):
            model.add_element(f"{side} {len(model.elements)}", start, end, rafter, member=side,
                              start_rotation=side if model.nodes[start].y == geometry.ridge else "continuous",
                              end_rotation=side if model.nodes[end].y == geometry.ridge else "continuous")
    if collar is not None:
        model.add_element("Kleštiny", physical[geometry.collar_y[0]], physical[geometry.collar_y[1]],
                          collar, member="collar", start_rotation="collar_pin", end_rotation="collar_pin")
    for y in (geometry.left_wall, geometry.right_wall):
        model.fix_node(physical[y])
    for y in (geometry.left_purlin, geometry.right_purlin):
        model.fix_node(physical[y], horizontal=restrain_purlins)
    return model


@dataclass(frozen=True)
class LoadCase:
    title: str
    permanent_factor: float
    snow_factor: float
    snow_left: float
    snow_right: float


@dataclass(frozen=True)
class RoofFrameCheck:
    title: str
    geometry: RoofGeometry
    model: Frame
    results: tuple[tuple[LoadCase, FrameResult], ...]
    spacing: float
    roof_mass: float
    ceiling_mass: float
    snow_load: float
    restrain_purlins: bool
    rafter_grade: str
    collar_grade: str
    include_collar_ties: bool = True
    ceiling_support_without_collars: str | None = None


def roof_loads(model: Frame, geometry: RoofGeometry, *, spacing: float, roof_mass: float,
               ceiling_mass: float, snow_load: float, case: LoadCase):
    """Global vertical gravity, roof kg/m² slope, snow kN/m² horizontal.

    Interior finishes act on the horizontal collar AND sloping ceiling below
    it, inside the wall plates; they are not repeated on the upper roof.
    """
    _positive(spacing, "spacing")
    for name, value in (("roof_mass", roof_mass), ("ceiling_mass", ceiling_mass),
                        ("snow_load", snow_load), ("permanent_factor", case.permanent_factor),
                        ("snow_factor", case.snow_factor), ("snow_left", case.snow_left),
                        ("snow_right", case.snow_right)):
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")
    result = {}
    for index, element in enumerate(model.elements):
        self_weight = TIMBER_DENSITY_KG_M3*element.section.area*GRAVITY_M_S2
        if element.member == "collar":
            dead = ceiling_mass*GRAVITY_M_S2*spacing+self_weight
            snow = 0.
        else:
            start, end = model.nodes[element.start], model.nodes[element.end]
            midpoint = (start.y+end.y)/2
            dead = roof_mass*GRAVITY_M_S2*spacing+self_weight
            if (geometry.left_wall < midpoint < geometry.collar_y[0]
                    or geometry.collar_y[1] < midpoint < geometry.right_wall):
                dead += ceiling_mass*GRAVITY_M_S2*spacing
            length = hypot(end.y-start.y, end.z-start.z)
            cosine = abs(end.y-start.y)/length
            snow_multiplier = case.snow_left if element.member == "rafter_left" else case.snow_right
            # One cosine for converting horizontal-area snow to slope length;
            # local transverse projection is done by the frame transformation.
            snow = snow_load*1000*spacing*cosine*snow_multiplier
        result[index] = (0., -case.permanent_factor*dead-case.snow_factor*snow)
    return result


def ceiling_nodal_loads(model: Frame, geometry: RoofGeometry, *, spacing: float,
                       ceiling_mass: float, case: LoadCase, ceiling_support: str):
    """Optional no-collar ceiling load path, WITHOUT a horizontal tie.

    ``rafter_end_reactions`` represents an unspecified alternative ceiling
    spanning to the same rafter points, but transmitting only vertical loads.
    ``independent_support`` transfers the flat-ceiling load elsewhere, outside
    this frame. Sloping finishes remain on rafters in either mode.
    The absent collar timber's own weight is not retained.
    """
    if ceiling_support not in {"rafter_end_reactions", "independent_support"}:
        raise ValueError("choose ceiling_support_without_collars: rafter_end_reactions or independent_support")
    if any(element.member == "collar" for element in model.elements):
        raise ValueError("ceiling nodal loads would double-count the present collar load")
    _positive(spacing, "spacing")
    if not isfinite(ceiling_mass) or ceiling_mass < 0 or not isfinite(case.permanent_factor) or case.permanent_factor < 0:
        raise ValueError("ceiling mass and permanent factor must be finite and non-negative")
    if ceiling_support == "independent_support":
        return {}
    force = -case.permanent_factor*ceiling_mass*GRAVITY_M_S2*spacing*(geometry.collar_y[1]-geometry.collar_y[0])/2
    nodes = [next(i for i, node in enumerate(model.nodes) if abs(node.y-y) < 1e-9)
             for y in geometry.collar_y]
    return {node: (0., force) for node in nodes}


def check_roof_frame(*, title: str, geometry: RoofGeometry, material: str,
                     width: float, height: float, spacing: float, collar_material: str,
                     collar_width: float, collar_height: float, collar_pieces: int,
                     roof_mass: float, ceiling_mass: float, snow_load: float,
                     restrain_purlins: bool, report: CalculationReport | None = None,
                     maximum_element_length=0.35, include_collar_ties=True,
                     ceiling_support_without_collars: str | None = None):
    rafter_grade = _resolve_timber_grade(material)
    collar_grade = _resolve_timber_grade(collar_material)
    rafter = Section(width, height, rafter_grade.elastic_modulus_gpa*1e9)
    collar = Section(collar_width, collar_height, collar_grade.elastic_modulus_gpa*1e9,
                     collar_pieces)
    if include_collar_ties and ceiling_support_without_collars is not None:
        raise ValueError("ceiling_support_without_collars applies only when collars are absent")
    if not include_collar_ties and ceiling_support_without_collars is None:
        raise ValueError("removing collars requires an explicit alternative ceiling load path")
    model = build_roof_frame(geometry, rafter, collar if include_collar_ties else None,
                             restrain_purlins=restrain_purlins,
                             maximum_element_length=maximum_element_length)
    results = []
    # Symmetric and two uneven snow screens. These are NOT a complete EC1/NA
    # snow-case generator; the input is roof load, not ground sk.
    for label, factors in (("MSP", (1., 1.)),
                            ("MSÚ", (PERMANENT_LOAD_FACTOR, SNOW_LOAD_FACTOR))):
        for name, left, right in (("sníh 1/1", 1., 1.), ("sníh 1/0,5", 1., .5),
                                  ("sníh 0,5/1", .5, 1.)):
            case = LoadCase(f"{label}, {name}", *factors, left, right)
            loads = roof_loads(model, geometry, spacing=spacing, roof_mass=roof_mass,
                               ceiling_mass=ceiling_mass, snow_load=snow_load, case=case)
            nodal_loads = {} if include_collar_ties else ceiling_nodal_loads(
                model, geometry, spacing=spacing, ceiling_mass=ceiling_mass, case=case,
                ceiling_support=ceiling_support_without_collars)
            results.append((case, model.solve(loads, nodal_loads=nodal_loads)))
    check = RoofFrameCheck(title, geometry, model, tuple(results), spacing, roof_mass,
                           ceiling_mass, snow_load, restrain_purlins,
                           rafter_grade.name, collar_grade.name, include_collar_ties,
                           ceiling_support_without_collars)
    print_diagnostics(check)
    if report is not None:
        add_frame_report(report, check)
    return check


def print_diagnostics(check: RoofFrameCheck):
    print(f"\n{check.title}")
    print(f"  Normal roof: angle {check.geometry.angle:.3f}°, collar span "
          f"{check.geometry.collar_y[1]-check.geometry.collar_y[0]:.3f} m")
    print("  HORIZONTAL restraint at purlins: " + ("YES" if check.restrain_purlins else "NO"))
    if not check.include_collar_ties:
        print("  NO COLLAR TIES. Alternative flat-ceiling load path: "
              + check.ceiling_support_without_collars + " (sensitivity assumption, not a design).")
    print("  N: positive=tension; negative=compression. Reactions: forces ON timber.")
    for case, result in check.results:
        if check.include_collar_ties:
            collar = result.member_extrema(check.model, "collar")
            print(f"  {case.title}: collar N = {-collar['compression']/1000:.3f} .. "
                  f"{collar['tension']/1000:.3f} kN; |M| = {collar['moment']/1000:.3f} kNm; "
                  f"max vertical movement = {result.maximum_displacement(check.model, 'collar')*1000:.2f} mm")
        else:
            movement = max(result.maximum_displacement(check.model, member)
                           for member in ("rafter_left", "rafter_right"))
            print(f"  {case.title}: NO COLLARS; max rafter vertical movement = {movement*1000:.2f} mm")
        for node, (horizontal, vertical) in result.reactions.items():
            print(f"    {check.model.nodes[node].name}: H={horizontal/1000:+.3f} kN, "
                  f"V={vertical/1000:+.3f} kN; "
                  f"on support: H/spacing={-horizontal/check.spacing/1000:+.3f} kN/m, "
                  f"V/spacing={-vertical/check.spacing/1000:+.3f} kN/m")
            if check.model.nodes[node].y in (check.geometry.left_purlin, check.geometry.right_purlin):
                print(f"      Purlin horizontal movement = {result.displacements[2*node]*1000:+.3f} mm")
            if vertical < -1e-5:
                print("      WARNING: uplift; gravity contact alone cannot supply this reaction")
    print("  Analysis only: no overall PASS/FAIL (connections, stability, wind etc. unchecked).")


def _cz(value, digits=3):
    if round(value, digits) == 0:
        value = 0.
    return f"{value:.{digits}f}".replace(".", ",")


def add_frame_report(report, check):
    geometry, model = check.geometry, check.model
    rafter = model.elements[0].section
    collar = next((element.section for element in model.elements if element.member == "collar"), None)
    collar_lines = ([
        "Kleštiny: klouby pouze na krokvích; žádná přímá podpora na vaznicích. Spoje bez prokluzu.",
        "Součet EA a EI jednotlivých prken, rovnoměrné rozdělení sil. Žádné spřažení pro příčnou stabilitu.",
        f"Kleštiny: {check.collar_grade}, {collar.pieces} × {_cz(collar.width*1000, 0)} × "
        f"{_cz(collar.height*1000, 0)} mm; E = {_cz(collar.elastic_modulus/1e9, 2)} GPa.",
    ] if collar is not None else [
        "BEZ KLEŠTIN: žádný vodorovný spoj mezi krokvemi v původní výšce kleštin.",
        "Vlastní tíha odstraněných kleštin se nezapočítává. Náhradní nosná konstrukce stropu není navržena.",
        ("Vodorovný strop: tíha OSB, SDK a instalační vrstvy rozdělena napůl do původních konců kleštin; "
         "náhradní nosník nepřenáší vodorovné síly. Jde pouze o citlivostní předpoklad."
         if check.ceiling_support_without_collars == "rafter_end_reactions" else
         "Vodorovný strop je předpokládán na samostatných podporách mimo tento rám. Jeho tíha zde nepůsobí."),
    ])
    report.add_sections(check.title, [
        ("Model a okrajové podmínky", [
            "Normální příčný řez bez vikýře. Přímé pružné pruty, malé deformace, teorie 1. řádu.",
            ("Snížení kleštin je jen citlivostní varianta normálního řezu, nikoliv posouzení vikýře."
             if geometry.collar_lowering else "Běžná výška kleštin podle geometrie IFC."),
            "Hřeben: společné posuny, nezávislá natočení (kloub); bez hřebenové vaznice.",
            "Krokve jsou průběžné přes vaznice i uzly kleštin. Pozednice: pevné posuny H a V, volné natočení.",
            "Vaznice: pevný posun V; posun H " + ("pevný." if check.restrain_purlins else "volný."),
            "Vaznice jsou zde podpory, nikoliv podélné nosníky; jejich průhyb se neuvažuje.",
            *collar_lines,
            f"Krokve: {check.rafter_grade}, {_cz(rafter.width*1000, 0)} × {_cz(rafter.height*1000, 0)} mm; "
            f"E = {_cz(rafter.elastic_modulus/1e9, 2)} GPa; rozteč a = {_cz(check.spacing)} m.",
            f"Sklon α = {_cz(geometry.angle, 3)}°; rozpětí kleštin = "
            f"{_cz(geometry.collar_y[1]-geometry.collar_y[0])} m; osa kleštin nad podlahou patra "
            f"= {_cz(geometry.collar_z-geometry.floor_z)} m.",
        ]),
        ("Zatížení a kombinace", [
            f"Střešní vrstvy bez vnitřních povrchů: {_cz(check.roof_mass, 1)} kg/m² skutečné šikmé plochy.",
            f"Vnitřní povrchy: {_cz(check.ceiling_mass, 1)} kg/m², šikmé plochy pod úrovní kleštin "
            "a vodorovný strop dle popsaného uložení; jen mezi pozednicemi, bez dvojího započtení.",
            "Střešní vrstvy jsou pro jednoduchost rovnoměrné i na přesazích. Vlastní tíha dřeva se přičítá.",
            f"g = {GRAVITY_M_S2:g} m/s²; hustota dřeva = {TIMBER_DENSITY_KG_M3:g} kg/m³.",
            f"Sníh s = {_cz(check.snow_load, 2)} kN/m² vodorovného půdorysu (střešní vstup, nikoliv sk).",
            f"Svislé zatížení qS = s × a × cos α = {_cz(check.snow_load, 2)} × "
            f"{_cz(check.spacing)} × cos {_cz(geometry.angle, 3)}° = "
            f"{_cz(check.snow_load*check.spacing*cos(atan(geometry.slope)))} kN/m délky krokve.",
            "Převod do os prutu řeší matice transformace; kosinus se zde nezapočítává podruhé.",
            f"MSP: G + S. MSÚ: {PERMANENT_LOAD_FACTOR:g} G + {SNOW_LOAD_FACTOR:g} S.",
            "Sníh: poměry L/P = 1/1, 1/0,5 a 0,5/1. Pouze srovnávací případy, nikoliv všechny normové kombinace.",
        ]),
        ("Omezení – není doklad úplného statického posouzení", [
            "Není posouzena kombinace N + M, vzpěr, klopení, oslabení zářezy, spoje, prokluz ani dotvarování.",
            "Chybí vítr/sání, lokální sněhové návěje, úplné normové kombinace, prostorové ztužení a vikýř.",
            "Vodorovné reakce musí přenést skutečné kotvení, věnce a navazující konstrukce; zde jsou pouze předpokladem.",
            "Pevné H ve vaznici znamená zajištění jejího posunu napříč střechou, ne zajištění klopení či vzpěru.",
            "Reakce jsou síly působící NA dřevo. Pro návrh podpory je obrácené znaménko; liniové zatížení = −R/a.",
        ]),
    ], page_label="Strana")
    rows = []
    for case, result in check.results:
        members = [("rafter_left", "Krokev L"), ("rafter_right", "Krokev P")]
        if check.include_collar_ties:
            members.append(("collar", "Kleštiny"))
        for member, label in members:
            ext = result.member_extrema(model, member)
            rows.append((case.title, label, _cz(ext["tension"]/1000), _cz(ext["compression"]/1000),
                         _cz(ext["moment"]/1000), _cz(ext["shear"]/1000),
                         _cz(result.maximum_displacement(model, member)*1000, 2)))
    report.add_table(check.title + " – vnitřní síly", column_labels=("Případ", "Prvek", "N tah\nkN", "N tlak\nkN", "|M|\nkNm", "|V|\nkN", "|wz|\nmm"),
                     rows=rows, column_widths=(.25, .17, .115, .115, .115, .115, .12),
                     intro_lines=["Nezávislé extrémy (nejsou současně v jednom místě). Posuny absolutní, okamžité.",
                                  "Výsledky nejsou posouzení únosnosti. N > 0 tah, N < 0 tlak; tabulka uvádí velikosti."],
                     page_label="Strana")
    rows = []
    for case, result in check.results:
        for node, (horizontal, vertical) in result.reactions.items():
            rows.append((case.title, model.nodes[node].name, _cz(horizontal/1000), _cz(vertical/1000),
                         _cz(-horizontal/check.spacing/1000), _cz(-vertical/check.spacing/1000)))
    report.add_table(check.title + " – reakce", column_labels=("Případ", "Podpora", "H\nkN", "V\nkN", "−H/a\nkN/m", "−V/a\nkN/m"),
                     rows=rows, column_widths=(.28, .2, .13, .13, .13, .13),
                     intro_lines=["H kladně doprava, V kladně nahoru. Reakce NA dřevo; opačné síly NA podporu.",
                                  "V < 0 vyžaduje kotvení proti nadzvednutí; běžné uložení nemůže táhnout."], page_label="Strana")
    add_frame_diagram(report, check)


def add_frame_diagram(report, check):
    """Diagrams for largest collar force, or purlin H if collars are absent."""
    candidates = [(case, result) for case, result in check.results if case.title.startswith("MSÚ")]
    if check.include_collar_ties:
        case, result = max(candidates, key=lambda item: max(
            item[1].member_extrema(check.model, "collar")[name] for name in ("tension", "compression")))
        selection = "největší |N| kleštin"
    else:
        case, result = max(candidates, key=lambda item: max(
            abs(horizontal) for node, (horizontal, _) in item[1].reactions.items()
            if check.model.nodes[node].y in (check.geometry.left_purlin, check.geometry.right_purlin)))
        selection = "největší |H| ve vaznicích"
    model = check.model
    figure = Figure(figsize=(8.27, 11.69))
    figure.text(.075, .96, check.title, fontsize=13, fontweight="bold", va="top")
    figure.text(.075, .926, f"Schéma a vnitřní síly: {case.title} ({selection})", fontsize=9)
    axes = [figure.add_axes((.10, bottom, .82, .21)) for bottom in (.68, .385, .09)]
    for ax, (title, quantity, divisor) in zip(axes, (("Model; deformace zvětšeny 25×", None, 1),
                                                   ("N [kN], kladně tah", 0, 1000),
                                                   ("M [kNm], kladně průhybový moment", 2, 1000))):
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("y [m]", fontsize=8)
        ax.set_ylabel("z [m]", fontsize=8)
        ax.tick_params(labelsize=7)
        force_max = max((abs(response.forces(x)[quantity])
                         for response in result.elements
                         for x in np.linspace(0, response.length, 21)), default=1) if quantity is not None else 1
        diagram_scale = .5 / max(force_max, 1.)
        for element, response in zip(model.elements, result.elements):
            a, b = model.nodes[element.start], model.nodes[element.end]
            c, s = (b.y-a.y)/response.length, (b.z-a.z)/response.length
            xs = np.linspace(0, response.length, 41)
            ys, zs = a.y+c*xs, a.z+s*xs
            ax.plot(ys, zs, color="#555555", lw=.8)
            if quantity is None:
                uv = np.array([response.displacement(x) for x in xs])
                ax.plot(ys+25*(c*uv[:, 0]-s*uv[:, 1]), zs+25*(s*uv[:, 0]+c*uv[:, 1]),
                        color="#e76f51", lw=.9)
            else:
                offsets = np.array([response.forces(x)[quantity] for x in xs])*diagram_scale
                ax.plot(ys-s*offsets, zs+c*offsets, color="#2874a6", lw=.9)
                if element.member == "collar":
                    extremum = max((response.forces(x)[quantity] for x in xs), key=abs)
                    ax.text((a.y+b.y)/2, a.z-.18, _cz(extremum/divisor), fontsize=8, ha="center")
        for node, (hfixed, vfixed) in model.supports.items():
            point = model.nodes[node]
            ax.plot(point.y, point.z-.05, "^" if hfixed else "o", ms=6,
                    color="#222222", markerfacecolor="#ffffff")
        ridge = next(node for node in model.nodes if node.name == "Hřeben")
        ax.plot(ridge.y, ridge.z, "o", ms=4, color="black", markerfacecolor="white")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=.15)
    figure.text(.075, .03, "Předběžný model; bez úplného posouzení únosnosti a stability.", fontsize=7)
    report.add_figure(figure)


def comparison_rows(checks):
    """Independent design-force envelopes, not concurrent force combinations."""
    rows = []
    for check in checks:
        wall_h = purlin_h = tension = compression = 0.
        for case, result in check.results:
            if not case.title.startswith("MSÚ"):
                continue
            for node, (horizontal, _) in result.reactions.items():
                y = check.model.nodes[node].y
                if y in (check.geometry.left_wall, check.geometry.right_wall):
                    wall_h = max(wall_h, abs(horizontal))
                else:
                    purlin_h = max(purlin_h, abs(horizontal))
            if check.include_collar_ties:
                ext = result.member_extrema(check.model, "collar")
                tension, compression = max(tension, ext["tension"]), max(compression, ext["compression"])
        rows.append((("Snížené" if check.geometry.collar_lowering else "Běžné") if check.include_collar_ties else "Bez kleštin",
                     "H pevné" if check.restrain_purlins else "H volné",
                     _cz(wall_h/1000), _cz(purlin_h/1000),
                     _cz(compression/1000) if check.include_collar_ties else "—",
                     _cz(tension/1000) if check.include_collar_ties else "—"))
    return rows


def add_comparison(report, checks):
    labels = ("Kleštiny", "Vaznice", "|H| pozednice\nkN", "|H| vaznice\nkN", "N tlak kleštin\nkN", "N tah kleštin\nkN")
    rows = comparison_rows(checks)
    print("\nCOMPARISON: design-force envelopes per rafter pair (kN)")
    print("  Collar / purlin H restraint / wall-plate |H| / purlin |H| / collar compression / tension")
    for row in rows:
        print("  " + " / ".join(row))
    report.add_table("Srovnání vodorovného zajištění vaznic", column_labels=labels, rows=rows,
                     column_widths=(.14, .14, .18, .18, .18, .18), intro_lines=[
                         "Předběžný normální příčný řez bez vikýře. Nezávislé extrémy z kombinací MSÚ.",
                         "H = vodorovná síla v rovině řezu. U kleštin jsou síly celkem za obě prkna.",
                         "Síly na jednu dvojici krokví; pro liniové zatížení podpory dělit osovou roztečí.",
                         "Pevná podpora vaznice nezajišťuje automaticky její stabilitu proti klopení.",
                         "Bez kleštin je nutné určit náhradní uložení stropu; použité uložení je popsáno u každé varianty.",
                         "Toto není úplné normové posouzení; výsledky závisejí na reálné tuhosti podpor a spojů.",
                     ], page_label="Strana")


def purlin_envelopes(check: RoofFrameCheck):
    """Signed loads ON each purlin, in global +y, from design cases only."""
    results = [result for case, result in check.results if case.title.startswith("MSÚ")]
    envelopes = []
    for node in check.model.supports:
        if check.model.nodes[node].y not in (check.geometry.left_purlin, check.geometry.right_purlin):
            continue
        forces = [-result.reactions[node][0] for result in results]
        # Numerical residue at an unrestrained DOF is not a physical reaction.
        forces = [0. if abs(force) < 1e-6 else force for force in forces]
        envelopes.append(dict(
            support=check.model.nodes[node].name,
            minimum_n=min(forces), maximum_n=max(forces),
            maximum_abs_n=max(abs(force) for force in forces),
            maximum_abs_n_per_m=max(abs(force) for force in forces)/check.spacing,
            maximum_abs_movement_m=max(abs(result.displacements[2*node]) for result in results),
        ))
    return envelopes


def add_purlin_comparison(report, checks):
    rows = []
    print("\nPURLIN HORIZONTAL LOADS: signed forces ON purlins, +y toward garden")
    for check in checks:
        label = ("S kleštinami" if check.include_collar_ties else "Bez kleštin")
        label += "; H " + ("pevné" if check.restrain_purlins else "volné")
        for value in purlin_envelopes(check):
            print(f"  {label}; {value['support']}: H = {value['minimum_n']/1000:+.3f} .. "
                  f"{value['maximum_n']/1000:+.3f} kN; |H|/a = {value['maximum_abs_n_per_m']/1000:.3f} kN/m; "
                  f"|uy| = {value['maximum_abs_movement_m']*1000:.3f} mm")
            rows.append((label, value["support"], _cz(value["minimum_n"]/1000),
                         _cz(value["maximum_n"]/1000), _cz(value["maximum_abs_n_per_m"]/1000),
                         _cz(value["maximum_abs_movement_m"]*1000)))
    report.add_table("Kleštiny a vodorovné zatížení vaznic", column_labels=(
        "Varianta", "Podpora", "H min\nkN", "H max\nkN", "max |H|/a\nkN/m", "max |uy|\nmm"),
        rows=rows, column_widths=(.30, .15, .12, .12, .16, .15), intro_lines=[
            "Síly NA vaznice (opačné znaménko než reakce podpory NA krokve). Obálky případů MSÚ.",
            "+H: směrem do zahrady (+y). Na levé vaznici +H míří dovnitř domu; na pravé vaznici −H míří dovnitř.",
            "H volné: reakce je nulová z definice modelu, nikoliv důkaz bezpečnosti či dostatečného ztužení.",
            "Posuny jsou posuny uzlů krokví; nesimulují podélný průhyb ani skutečný příčný ohyb vaznice.",
            "Bez kleštin je zatížení vodorovného stropu ponecháno jako svislé síly v původních koncích kleštin.",
            "Alternativní stropní konstrukce a její vlastní tíha nejsou navrženy; výsledky jsou pouze srovnávací.",
        ], page_label="Strana")


def main():
    house_path = Path(__file__).with_name("house_ifc.py")
    report_path = Path(__file__).with_name("roof_frame_report.pdf")
    # Move finishes from the common roof-layer inputs to their actual ceiling
    # path (slopes below collars + horizontal collar), rather than count twice.
    ceiling_names = {"OSB", "Gypsum plasterboard", "Installation battens/services"}
    if not ceiling_names <= ROOF_LAYERS_KG_M2.keys():
        raise ValueError("update the ceiling layer names in roof_frame.main()")
    if any(value is None or not isfinite(value) or value < 0 for value in ROOF_LAYERS_KG_M2.values()):
        raise ValueError("roof-layer masses must all be specified, finite and non-negative")
    roof_mass = sum(value for name, value in ROOF_LAYERS_KG_M2.items() if name not in ceiling_names)
    ceiling_mass = sum(ROOF_LAYERS_KG_M2[name] for name in ceiling_names)
    print(f"Roof frame, geometry read from {house_path.name}; no IFC generation.")
    print(f"Roof layers {roof_mass:g} kg/m² slope; ceiling finishes {ceiling_mass:g} kg/m².")
    print(f"Snow input {SNOW_LOAD_KN_M2:g} kN/m² horizontal roof area, not ground sk.")
    section = HouseRoofSection.from_house(house_path)
    print(f"Selected actual normal main rafter x={section.x:.3f} m, tributary width={section.spacing:.3f} m.")
    print(f"IFC input sizes: rafters {section.width*1000:g} × {section.height*1000:g} mm; "
          f"collars {section.collar_pieces} × {section.collar_width*1000:g} × {section.collar_height*1000:g} mm.")
    print(f"Purlin axes y={section.geometry.left_purlin:.3f}/{section.geometry.right_purlin:.3f} m; "
          f"collar axis z={section.geometry.collar_z:.3f} m.")
    checks = []
    for include_collars, collar_label in ((True, "s kleštinami"), (False, "bez kleštin")):
        for restraint, support_label in ((False, "H volné"), (True, "H pevné")):
            checks.append(check_roof_frame(
                title=f"Řez x={section.x:g}; {collar_label}; vaznice {support_label}",
                # Grades remain explicit: IFC inputs do not contain strength
                # grades. C24 matches the current drawing note for this wider
                # main-rafter tributary strip; collar boards are assumed C22.
                geometry=section.geometry, material="c24", width=section.width,
                height=section.height, spacing=section.spacing,
                collar_material="c22", collar_width=section.collar_width,
                collar_height=section.collar_height, collar_pieces=section.collar_pieces,
                roof_mass=roof_mass, ceiling_mass=ceiling_mass, snow_load=SNOW_LOAD_KN_M2,
                restrain_purlins=restraint,
                include_collar_ties=include_collars,
                ceiling_support_without_collars=None if include_collars else "rafter_end_reactions",
            ))
    with CalculationReport(report_path, document_title="Předběžný 2D model krovu") as report:
        add_comparison(report, checks)
        add_purlin_comparison(report, checks)
        for check in checks:
            add_frame_report(report, check)
    print(f"\nPDF: {report_path}")
    print("Normal roof section only; NOT a dormer/corner or ring-beam analysis.")


if __name__ == "__main__":
    main()
