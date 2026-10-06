#!/usr/bin/env python3
"""Preliminary PyNite roof frame; no IFC generation and no kleštiny.

Geometry is read from the arithmetic/data definitions in house_ifc.py without
executing that module. Units: m, N, Pa. Global Z is up, X along the house.
See roof_frame_3d.md for the important connection/support/load assumptions.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import dataclass, field
from importlib.metadata import version
from math import atan2, degrees, isfinite, sqrt
from pathlib import Path

import numpy as np

# Sensitivity-model calibration, NOT a measured connection stiffness. Applied
# independently to every formerly fixed horizontal support DOF (X and Y).
HORIZONTAL_SUPPORT_STIFFNESS_KN_MM = 0.12 * 1000


def positive(value, name):
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


@dataclass(frozen=True)
class RafterEntry:
    x: float
    stronger: bool = False
    split_y: float | None = None


class HouseInputs:
    """A small, deliberately restricted AST data reader, not Python eval."""

    def __init__(self, path):
        self.path = Path(path)
        self.tree = ast.parse(self.path.read_text(encoding="utf-8"))
        self.expressions = {}
        self.cache = {}
        for statement in self.tree.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        self.expressions[target.id] = statement.value

    def get(self, name, visiting=frozenset()):
        if name in visiting:
            raise ValueError(f"cyclic house input: {name}")
        if name not in self.cache:
            if name not in self.expressions:
                raise ValueError(f"missing house input: {name}")
            self.cache[name] = self.evaluate(self.expressions[name], visiting | {name})
        return self.cache[name]

    def evaluate(self, node, visiting=frozenset()):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str, bool):
            return node.value
        if isinstance(node, ast.Name):
            return self.get(node.id, visiting)
        if isinstance(node, (ast.Tuple, ast.List)):
            return tuple(self.evaluate(item, visiting) for item in node.elts)
        if isinstance(node, ast.Subscript):
            return self.evaluate(node.value, visiting)[self.evaluate(node.slice, visiting)]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self.evaluate(node.operand, visiting)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            a, b = self.evaluate(node.left, visiting), self.evaluate(node.right, visiting)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
        # Decode only these two data wrappers; never call a function from IFC.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            args = tuple(self.evaluate(arg, visiting) for arg in node.args)
            if node.func.id == "StrongerRafter" and len(args) == 1:
                return RafterEntry(args[0], stronger=True)
            if node.func.id == "SplitRafter" and len(args) == 2:
                return RafterEntry(args[0], split_y=args[1])
        raise ValueError(f"unsupported house expression: {ast.dump(node)}")


@dataclass(frozen=True)
class RoofPlane:
    reference_y: float
    reference_z: float
    slope: float

    @classmethod
    def from_points(cls, points):
        first, along, other = points
        if abs(along[1] - first[1]) > 1e-9 or abs(along[2] - first[2]) > 1e-9:
            raise ValueError("roof planes must run along global X")
        return cls(first[1], first[2], (other[2] - first[2]) / (other[1] - first[1]))

    def z(self, y, normal_offset=0.0):
        return (
            self.reference_z
            + self.slope * (y - self.reference_y)
            + normal_offset * sqrt(1 + self.slope**2)
        )

    def y_at_z(self, z, normal_offset=0.0):
        return self.reference_y + (z - self.z(self.reference_y, normal_offset)) / self.slope


@dataclass(frozen=True)
class Timber:
    width: float
    height: float
    material: str = "C22"

    def __post_init__(self):
        positive(self.width, "timber width")
        positive(self.height, "timber height")
        if self.material not in {"C22", "C24"}:
            raise ValueError("material must be C22 or C24")

    @property
    def properties(self):
        b, h = self.width, self.height
        # Local y is section height; local z is section width.
        a, small = max(b, h), min(b, h)
        torsion = a * small**3 * (1 / 3 - 0.21 * (small / a) * (1 - small**4 / (12 * a**4)))
        return b * h, h * b**3 / 12, b * h**3 / 12, torsion


@dataclass(frozen=True)
class BeamSpec:
    name: str
    category: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    timber: Timber
    bearings: tuple[float, ...] = ()  # global X along longitudinal beams
    wall_extent: tuple[float, float] | None = None

    @property
    def length(self):
        return float(np.linalg.norm(np.subtract(self.end, self.start)))

    def z(self, y):
        return self.start[2] + (self.end[2] - self.start[2]) * (y - self.start[1]) / (
            self.end[1] - self.start[1]
        )


@dataclass(frozen=True)
class RoofPatch:
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    rafters: tuple[str, ...]
    snow_side: str


@dataclass(frozen=True)
class RoofLayout:
    beams: tuple[BeamSpec, ...]
    patches: tuple[RoofPatch, ...]
    source: Path

    def __post_init__(self):
        if not self.beams or len({b.name for b in self.beams}) != len(self.beams):
            raise ValueError("roof must have uniquely named members")
        names = {b.name for b in self.beams}
        for beam in self.beams:
            if not all(isfinite(c) for c in (*beam.start, *beam.end)):
                raise ValueError(f"non-finite coordinates: {beam.name}")
            positive(beam.length, f"length of {beam.name}")
            if beam.category == "rafter" and beam.start[1] >= beam.end[1]:
                raise ValueError(f"rafter must run in positive Y: {beam.name}")
            if beam.category not in {"rafter", "purlin", "wall_plate"}:
                raise ValueError(f"unsupported physical member: {beam.category}")
            if any(not beam.start[0] <= x <= beam.end[0] for x in beam.bearings):
                raise ValueError(f"bearing outside {beam.name}")
        for patch in self.patches:
            if patch.x_min >= patch.x_max or patch.y_min >= patch.y_max:
                raise ValueError(f"invalid roof patch: {patch.name}")
            if not set(patch.rafters) <= names:
                raise ValueError(f"unknown rafter in {patch.name}")

    @classmethod
    def from_house(cls, path, *, rafter_material="C22", beam_material="C22"):
        data = HouseInputs(path)
        g = data.get
        street = RoofPlane.from_points(g("STREET_ROOF_PLANE_POINTS"))
        garden = RoofPlane.from_points(g("GARDEN_ROOF_PLANE_POINTS"))
        dormer = RoofPlane.from_points(g("DORMER_ROOF_PLANE_POINTS"))
        ridge = g("HALF_DEPTH")
        width = g("HOUSE_WIDTH")
        bwt = g("BWT")
        offset = g("RAFTER_Z_OFFSET") + g("RAFTER_HEIGHT") / 2
        if abs(street.z(ridge, offset) - garden.z(ridge, offset)) > 1e-8:
            raise ValueError("main rafter axes do not meet at ridge")
        beams = []
        for side, y in (
            ("street", ridge - g("VAZNICE_DIST")),
            ("garden", ridge + g("VAZNICE_DIST")),
        ):
            for segment, lo, hi, height in g("PURLIN_X_SEGMENTS"):
                # Use wall centre lines for the analysis span of every piece.
                supports = {
                    "left": (bwt / 2, hi),
                    "middle": (lo, hi),
                    "right": (lo, width - bwt / 2),
                }
                if segment not in supports:
                    raise ValueError(f"unsupported purlin segment: {segment}")
                z = g("PURLIN_TOP_Z") - height / 2
                beams.append(
                    BeamSpec(
                        f"{side}_purlin_{segment}",
                        "purlin",
                        (lo, y, z),
                        (hi, y, z),
                        Timber(g("VAZNICE_BASE"), height, beam_material),
                        supports[segment],
                    )
                )

        wp_width, wp_height = g("WALL_PLATE_SIZE")
        wall_timber = Timber(wp_width, wp_height, beam_material)

        def wall_plate(name, lo, hi, y, plane, outside, wall_extent):
            z = plane.z(y + outside * wp_width / 2) - wp_height / 2
            beams.append(
                BeamSpec(
                    name, "wall_plate", (lo, y, z), (hi, y, z), wall_timber, wall_extent=wall_extent
                )
            )

        wall_plate(
            "street_wall_plate",
            g("CUT_WIDTH") - 0.2,
            width + 0.2,
            g("STREET_WALL_PLATE_Y"),
            street,
            -1,
            (g("CUT_WIDTH"), width),
        )
        wall_plate(
            "cut_street_wall_plate",
            -0.2,
            g("wall2_x") - bwt,
            g("CUT_STREET_WALL_PLATE_Y"),
            street,
            -1,
            (0, g("wall2_x") - bwt),
        )
        wall_plate(
            "garden_wall_plate_left",
            -0.2,
            g("wall2_x") - bwt,
            g("GARDEN_WALL_PLATE_Y"),
            garden,
            1,
            (0, g("wall2_x") - bwt),
        )
        wall_plate(
            "garden_wall_plate_right",
            g("wall3_x"),
            width + 0.2,
            g("GARDEN_WALL_PLATE_Y"),
            garden,
            1,
            (g("wall3_x"), width),
        )
        wall_plate(
            "dormer_wall_plate",
            g("wall2_x") - bwt - 0.3,
            g("wall3_x") + 0.3,
            g("GARDEN_WALL_PLATE_Y"),
            dormer,
            1,
            (g("wall2_x") - bwt, g("wall3_x")),
        )

        main, full_garden, dormer_names = [], [], []
        for index, entry in enumerate(g("rafters"), 1):
            pair = None
            if isinstance(entry, tuple):
                x, pair = entry
                if pair not in {"before", "after", "+before", "+after"}:
                    raise ValueError("invalid paired rafter side")
                entry = RafterEntry(x)
            elif not isinstance(entry, RafterEntry):
                entry = RafterEntry(entry)
            if entry.split_y is not None:
                raise ValueError(
                    "SplitRafter is not supported in this first 3D model; model its trimmers/joints first"
                )
            size = g("STRONGER_RAFTER_SIZE") if entry.stronger else g("RAFTER_SIZE")
            if abs(size[1] - g("RAFTER_HEIGHT")) > 1e-9:
                raise ValueError("stronger rafters must have the same height")
            timber = Timber(*size, rafter_material)
            corner = entry.x < g("CUT_WIDTH") - g("ROOF_X_OVERHANG")
            low_y = g("CUT_STREET_EAVE_Y") if corner else g("STREET_ROOF_EAVE_Y")
            street_name, garden_name = f"rafter_{index:02d}_street", f"rafter_{index:02d}_garden"
            beams.append(
                BeamSpec(
                    street_name,
                    "rafter",
                    (entry.x, low_y, street.z(low_y, offset)),
                    (entry.x, ridge, street.z(ridge, offset)),
                    timber,
                )
            )
            short = pair is not None and not pair.startswith("+")
            high_y = g("GARDEN_ROOF_EAVE_Y")
            if short:
                lowering = (
                    g("VAZNICE_EXTRA_HEIGHT")
                    if g("MIDDLE_PURLIN_X_MIN") <= entry.x <= g("MIDDLE_PURLIN_X_MAX")
                    else 0.0
                )
                cut_z = (
                    g("UPPER_FLOOR_START")
                    + g("COLLAR_TIE_TOP_HEIGHT")
                    - g("COLLAR_TIE_SIZE")[1]
                    - lowering
                )
                high_y = garden.y_at_z(cut_z, offset)
            beams.append(
                BeamSpec(
                    garden_name,
                    "rafter",
                    (entry.x, ridge, garden.z(ridge, offset)),
                    (entry.x, high_y, garden.z(high_y, offset)),
                    timber,
                )
            )
            main.append((street_name, garden_name))
            if not short:
                full_garden.append(garden_name)
            if pair is not None:
                x = entry.x + (
                    -g("RAFTER_THICKNESS") if pair.endswith("before") else g("RAFTER_THICKNESS")
                )
                # IFC dormer source starts at local Y=-0.5, not at the ridge.
                low_y = (
                    dormer.reference_y
                    - 0.5 / sqrt(1 + dormer.slope**2)
                    - offset * dormer.slope / sqrt(1 + dormer.slope**2)
                )
                high_y = g("GARDEN_ROOF_EAVE_Y")
                name = f"rafter_{index:02d}_dormer"
                beams.append(
                    BeamSpec(
                        name,
                        "rafter",
                        (x, low_y, dormer.z(low_y, offset)),
                        (x, high_y, dormer.z(high_y, offset)),
                        Timber(*g("RAFTER_SIZE"), rafter_material),
                    )
                )
                dormer_names.append(name)

        left, right = -g("ROOF_X_OVERHANG"), width + g("ROOF_X_OVERHANG")
        corner_edge = g("CUT_WIDTH") - g("ROOF_X_OVERHANG")
        joint = g("GARDEN_ROOF_JOINT_Y")
        patches = [
            RoofPatch(
                "street corner",
                left,
                corner_edge,
                g("CUT_STREET_EAVE_Y"),
                ridge,
                tuple(a for a, b in main),
                "street",
            ),
            RoofPatch(
                "street normal",
                corner_edge,
                right,
                g("STREET_ROOF_EAVE_Y"),
                ridge,
                tuple(a for a, b in main),
                "street",
            ),
            RoofPatch(
                "garden upper", left, right, ridge, joint, tuple(b for a, b in main), "garden"
            ),
        ]
        if dormer_names:
            patches.extend(
                (
                    RoofPatch(
                        "garden left",
                        left,
                        g("wall2_x") - bwt,
                        joint,
                        g("GARDEN_ROOF_EAVE_Y"),
                        tuple(full_garden),
                        "garden",
                    ),
                    RoofPatch(
                        "garden right",
                        g("wall3_x"),
                        right,
                        joint,
                        g("GARDEN_ROOF_EAVE_Y"),
                        tuple(full_garden),
                        "garden",
                    ),
                    RoofPatch(
                        "dormer",
                        g("wall2_x") - bwt,
                        g("wall3_x"),
                        joint,
                        g("GARDEN_ROOF_EAVE_Y"),
                        tuple(dormer_names),
                        "garden",
                    ),
                )
            )
        else:
            patches.append(
                RoofPatch(
                    "garden lower",
                    left,
                    right,
                    joint,
                    g("GARDEN_ROOF_EAVE_Y"),
                    tuple(full_garden),
                    "garden",
                )
            )
        # An opening may be neglected as roof area (conservative for gravity),
        # but never silently bridge an opening that actually cuts a rafter.
        by_name = {beam.name: beam for beam in beams}
        for node in ast.walk(data.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_opening"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "roof"
            ):
                rectangle = next((k.value for k in node.keywords if k.arg == "rectangle"), None)
                if rectangle is None:
                    raise ValueError("roof opening requires explicit rectangle")
                (x1, y1), (x2, y2) = data.evaluate(rectangle)
                for name in (*full_garden, *dormer_names, *(b for a, b in main)):
                    beam = by_name[name]
                    if (
                        min(x1, x2) < beam.start[0] + beam.timber.width / 2
                        and max(x1, x2) > beam.start[0] - beam.timber.width / 2
                        and min(y1, y2) < beam.end[1]
                        and max(y1, y2) > beam.start[1]
                    ):
                        raise ValueError(
                            f"roof opening cuts {name}; trimmer/split modelling is required"
                        )
        return cls(tuple(beams), tuple(patches), Path(path))


@dataclass(frozen=True)
class Settings:
    roof_mass: float = 135.0  # kg/m² actual slope; excludes suspended ceiling
    snow_load: float = 1.5  # kN/m² horizontal roof projection, NOT ground sk
    timber_density: float = 450.0
    gravity: float = 10.0
    purlin_lateral_restraint: bool = True
    horizontal_stiffness_kn_mm: float | None = HORIZONTAL_SUPPORT_STIFFNESS_KN_MM
    joint_stiffness_factor: float = 1000.0

    def __post_init__(self):
        for name in ("timber_density", "gravity", "joint_stiffness_factor"):
            positive(getattr(self, name), name)
        if self.horizontal_stiffness_kn_mm is not None:
            positive(self.horizontal_stiffness_kn_mm, "horizontal_stiffness_kn_mm")
        for name in ("roof_mass", "snow_load"):
            if not isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass
class RoofModel:
    model: object
    layout: RoofLayout
    settings: Settings
    supports: dict[str, str] = field(default_factory=dict)
    connections: list[str] = field(default_factory=list)
    # Actual seats: longitudinal member, category, station on the rafter.
    rafter_seats: dict[str, list[tuple[str, str, float]]] = field(default_factory=dict)
    # member name, load case, global vertical q, interval along member
    loads: list[tuple[str, str, float, float, float]] = field(default_factory=list)

    def add_load(self, name, case, q, start=0.0, end=None):
        member = self.model.members[name]
        end = member.L() if end is None else end
        if end - start <= 1e-9 or q == 0:
            return
        self.model.add_member_dist_load(name, "FZ", q, q, start, end, case=case)
        self.loads.append((name, case, q, start, end))


def orient_section(member):
    """PyNite assumes global Y up; rotate section height toward GLOBAL Z."""
    transform = member.T()[:3, :3]
    axis, y, z = transform
    target = np.array((0.0, 0.0, 1.0))
    target -= target.dot(axis) * axis
    target /= np.linalg.norm(target)
    member.rotation = degrees(atan2(target.dot(z), target.dot(y)))


def tributary_intervals(beams, x_min, x_max):
    ordered = sorted(beams, key=lambda b: b.start[0])
    if not ordered or any(
        abs(a.start[0] - b.start[0]) < 1e-9 for a, b in zip(ordered, ordered[1:])
    ):
        raise ValueError("patch requires unique rafter positions")
    edges = [x_min, *((a.start[0] + b.start[0]) / 2 for a, b in zip(ordered, ordered[1:])), x_max]
    return {
        beam.name: (max(x_min, lo), min(x_max, hi))
        for beam, lo, hi in zip(ordered, edges, edges[1:])
    }


def build_roof_model(layout: RoofLayout, settings=Settings()):
    try:
        from Pynite import FEModel3D
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional dependencies: python -m pip install -r requirements-roof3d.txt"
        ) from exc
    model = FEModel3D()
    result = RoofModel(model, layout, settings)
    # Effective along-grain beam properties; G is specified separately, NOT
    # inferred from an isotropic Poisson ratio for this orthotropic material.
    for name, e, g in (("C22", 10e9, 0.63e9), ("C24", 11e9, 0.69e9)):
        model.add_material(name, e, g, 0.3, settings.timber_density * settings.gravity)
    model.add_material(
        "JOINT",
        10e9 * settings.joint_stiffness_factor,
        0.63e9 * settings.joint_stiffness_factor,
        0.3,
        0.0,
    )
    model.add_section("JOINT", 0.16 * 0.12, 0.12 * 0.16**3 / 12, 0.16 * 0.12**3 / 12, 0.00005)
    nodes = {}

    def bearing_support(name, *, lateral):
        rigid = settings.horizontal_stiffness_kn_mm is None
        model.def_support(name, rigid, lateral and rigid, True, True, False, False)
        if not rigid:
            # kN/mm -> N/m. Keep vertical support and roll restraint unchanged.
            stiffness = settings.horizontal_stiffness_kn_mm * 1e6
            model.def_support_spring(name, "DX", stiffness)
            if lateral:
                model.def_support_spring(name, "DY", stiffness)

    def node(point, *, owner=None):
        # Independent purlin pieces may meet at identical coordinates. Keep
        # their translations/rotations separate, even at a shared wall centre.
        key = (owner, *(round(float(c), 10) for c in point))
        if key not in nodes:
            name = f"N{len(nodes):04d}"
            model.add_node(name, *point)
            nodes[key] = name
        return nodes[key]

    for beam in layout.beams:
        owner = beam.name if beam.category == "purlin" else None
        section_name = f"{beam.timber.width:.9g}x{beam.timber.height:.9g}"
        if section_name not in model.sections:
            model.add_section(section_name, *beam.timber.properties)
        model.add_member(
            beam.name,
            node(beam.start, owner=owner),
            node(beam.end, owner=owner),
            beam.timber.material,
            section_name,
        )
        orient_section(model.members[beam.name])
        result.add_load(
            beam.name, "G", -settings.timber_density * settings.gravity * beam.timber.properties[0]
        )

    rafters = [b for b in layout.beams if b.category == "rafter"]
    longitudinal = [b for b in layout.beams if b.category != "rafter"]
    for beam in longitudinal:
        owner = beam.name if beam.category == "purlin" else None
        xs = list(beam.bearings)
        if beam.wall_extent:
            xs.extend(beam.wall_extent)
        for rafter in rafters:
            x, y = rafter.start[:2]
            bearing_y = beam.start[1]
            if not (
                beam.start[0] - 1e-9 <= x <= beam.end[0] + 1e-9
                and min(rafter.start[1], rafter.end[1]) - 1e-9
                <= bearing_y
                <= max(rafter.start[1], rafter.end[1]) + 1e-9
            ):
                continue
            rafter_z = rafter.z(bearing_y)
            # Two wall plates at the garden side are at different heights.
            # Reject plates belonging to the other roof slope.
            separation = rafter_z - beam.start[2]
            if beam.category == "wall_plate" and not 0 < separation < 0.4:
                continue
            if beam.category == "purlin" and not 0 < separation < 0.6:
                raise ValueError(f"unexpected seat offset at {rafter.name}/{beam.name}")
            xs.append(x)
            lower = node((x, bearing_y, beam.start[2]), owner=owner)
            upper = node((x, bearing_y, rafter_z))
            name = f"seat_{len(result.connections):03d}"
            model.add_member(name, lower, upper, "JOINT", "JOINT")
            # Vertical offset arm: hinged for GLOBAL X/Y rotations at the
            # rafter. Local x is vertical, so retaining Rxj restrains yaw.
            # No rafter bending moment is transferred in its roof plane.
            model.def_releases(name, Ryj=True, Rzj=True)
            result.connections.append(name)
            station = (
                (bearing_y - rafter.start[1]) / (rafter.end[1] - rafter.start[1]) * rafter.length
            )
            result.rafter_seats.setdefault(rafter.name, []).append(
                (beam.name, beam.category, station)
            )
        for x in sorted(set(xs)):
            name = node((x, beam.start[1], beam.start[2]), owner=owner)
            if beam.wall_extent and beam.wall_extent[0] - 1e-9 <= x <= beam.wall_extent[1] + 1e-9:
                bearing_support(name, lateral=True)
                result.supports[name] = beam.name
            elif any(abs(x - bearing) < 1e-9 for bearing in beam.bearings):
                bearing_support(name, lateral=settings.purlin_lateral_restraint)
                result.supports[name] = beam.name

    # The ridge is a translation-only joint, NOT a ridge beam. Its unused
    # node rotations are fixed only because all incident ends release them.
    for beam in rafters:
        if beam.name.endswith("_street"):
            model.def_releases(beam.name, Rxj=True, Ryj=True, Rzj=True)
            model.def_support(
                model.members[beam.name].j_node.name, False, False, False, True, True, True
            )
        elif beam.name.endswith("_garden"):
            model.def_releases(beam.name, Rxi=True, Ryi=True, Rzi=True)

    by_name = {b.name: b for b in layout.beams}
    all_x = [b.start[0] for b in rafters]
    for patch in layout.patches:
        patch_beams = [by_name[name] for name in patch.rafters]
        # Establish neighbour midpoints globally, then intersect the patch.
        intervals = tributary_intervals(patch_beams, min(all_x) - 1, max(all_x) + 1)
        assigned_area = 0.0
        for beam in patch_beams:
            lo, hi = intervals[beam.name]
            width = max(0.0, min(hi, patch.x_max) - max(lo, patch.x_min))
            if width <= 1e-9:
                continue
            y1, y2 = max(patch.y_min, beam.start[1]), min(patch.y_max, beam.end[1])
            if abs(y1 - patch.y_min) > 1e-8 or abs(y2 - patch.y_max) > 1e-8:
                raise ValueError(
                    f"{beam.name} cannot carry its entire tributary area in {patch.name}"
                )
            cosine = abs(beam.end[1] - beam.start[1]) / beam.length
            a, b = (y1 - beam.start[1]) / cosine, (y2 - beam.start[1]) / cosine
            result.add_load(beam.name, "G", -settings.roof_mass * settings.gravity * width, a, b)
            result.add_load(
                beam.name,
                "S_street" if patch.snow_side == "street" else "S_garden",
                -settings.snow_load * 1000 * width * cosine,
                a,
                b,
            )
            assigned_area += width * (y2 - y1)
        if not np.isclose(
            assigned_area,
            (patch.x_max - patch.x_min) * (patch.y_max - patch.y_min),
            rtol=1e-9,
            atol=1e-8,
        ):
            raise ValueError(f"unassigned roof area: {patch.name}")
    for limit, g, s in (("SLS", 1.0, 1.0), ("ULS", 1.35, 1.5)):
        for label, left, right in (
            ("symmetric", 1.0, 1.0),
            ("street", 1.0, 0.5),
            ("garden", 0.5, 1.0),
        ):
            model.add_load_combo(
                f"{limit}_{label}", {"G": g, "S_street": s * left, "S_garden": s * right}
            )
    return result


def check_equilibrium(roof: RoofModel):
    """Independent global force AND moment balance, including bearing torque."""
    residuals = {}
    for combo_name, combo in roof.model.load_combos.items():
        force, moment = np.zeros(3), np.zeros(3)
        magnitude = 0.0
        for name, case, q, a, b in roof.loads:
            member = roof.model.members[name]
            start = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
            end = np.array((member.j_node.X, member.j_node.Y, member.j_node.Z))
            location = start + (end - start) * (a + b) / (2 * member.L())
            load = np.array((0.0, 0.0, q * (b - a) * combo.factors.get(case, 0.0)))
            force += load
            moment += np.cross(location, load)
            magnitude += abs(load[2])
        for n in roof.model.nodes.values():
            reaction = np.array((n.RxnFX[combo_name], n.RxnFY[combo_name], n.RxnFZ[combo_name]))
            force += reaction
            moment += np.cross((n.X, n.Y, n.Z), reaction)
            moment += (n.RxnMX[combo_name], n.RxnMY[combo_name], n.RxnMZ[combo_name])
        span = max(b.length for b in roof.layout.beams)
        relative = max(np.linalg.norm(force), np.linalg.norm(moment) / max(1.0, span)) / max(
            1.0, magnitude
        )
        if not isfinite(relative) or relative > 1e-5:
            raise ValueError(f"global equilibrium failed for {combo_name}: {relative:g}")
        residuals[combo_name] = float(relative)
    return residuals


def solve_roof_model(roof):
    # Start with verified first-order equilibrium. Second-order behaviour,
    # instability and nonlinear connection slip need a validated extension.
    roof.model.analyze_linear(check_stability=True, log=False)
    return check_equilibrium(roof)


@dataclass(frozen=True)
class MemberChord:
    start_m: float
    end_m: float
    kind: str
    start_label: str
    end_label: str


def rafter_chord(roof, beam, *, fallback="supports"):
    """Choose actual end references; never invent a wall plate or ridge."""
    if fallback not in {"na", "supports"}:
        raise ValueError("rafter chord fallback must be 'na' or 'supports'")
    seats = roof.rafter_seats.get(beam.name, [])
    plates = [seat for seat in seats if seat[1] == "wall_plate"]
    purlins = [seat for seat in seats if seat[1] == "purlin"]
    member = roof.model.members[beam.name]
    if beam.name.endswith("_street"):
        ridge = member.L()
    elif beam.name.endswith("_garden"):
        ridge = 0.0
    else:
        ridge = None
    if ridge is not None and plates:
        # If a street rafter crosses two plates, use the outer/eave-side one.
        plate = max(plates, key=lambda seat: abs(seat[2] - ridge))
        endpoints = sorted(((plate[2], plate[0]), (ridge, "ridge")))
        kind = "wall_plate_to_ridge"
    elif fallback == "supports" and purlins and (plates or ridge is not None):
        if plates:
            plate = max(plates, key=lambda seat: seat[2])
            purlin = min(purlins, key=lambda seat: seat[2])
            endpoints = sorted(((plate[2], plate[0]), (purlin[2], purlin[0])))
            kind = "wall_plate_to_purlin"
        else:
            purlin = max(purlins, key=lambda seat: abs(seat[2] - ridge))
            endpoints = sorted(((ridge, "ridge"), (purlin[2], purlin[0])))
            kind = "purlin_to_ridge"
    else:
        return None
    (a, first), (b, last) = endpoints
    positive(b - a, f"reference span of {beam.name}")
    return MemberChord(a, b, kind, first, last)


def purlin_chord(roof, beam):
    """Reference the two actual wall-bearing nodes, not the timber's free ends."""
    member = roof.model.members[beam.name]
    start = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
    axis = member.T()[0, :3]
    bearings = []
    for name, supported_beam in roof.supports.items():
        if supported_beam == beam.name:
            node = roof.model.nodes[name]
            station = float((np.array((node.X, node.Y, node.Z)) - start).dot(axis))
            bearings.append((station, name))
    if len(bearings) != 2:
        raise ValueError(f"purlin chord requires exactly two bearings: {beam.name}")
    (a, first), (b, last) = sorted(bearings)
    positive(b - a, f"reference span of {beam.name}")
    return MemberChord(a, b, "bearing_to_bearing", first, last)


def deformed_member_point(member, station, combo):
    """World centre-line position, including all three displacement components."""
    start = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
    end = np.array((member.j_node.X, member.j_node.Y, member.j_node.Z))
    displacement = member.T()[:3, :3].T @ np.array(
        [member.deflection(direction, float(station), combo) for direction in ("dx", "dy", "dz")]
    )
    return start + (end - start) * station / member.L() + displacement


def displacement_breakpoints(member, combo):
    """Every FE boundary and load-polynomial boundary, not a sampling mesh."""
    start = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
    axis = member.T()[0, :3]
    points = {0.0, member.L()}
    for sub in getattr(member, "sub_members", {}).values():
        offset = float((np.array((sub.i_node.X, sub.i_node.Y, sub.i_node.Z)) - start).dot(axis))
        sub.deflection("dy", 0.0, combo)  # populate this combination's segments
        points.update((offset, offset + sub.L()))
        for field_name in ("SegmentsX", "SegmentsY", "SegmentsZ"):
            for segment in getattr(sub, field_name, []):
                points.update((offset + segment.x1, offset + segment.x2))
    return points


def maximum_chord_departure(member, combo, start_m, end_m):
    """Maximum 3D perpendicular distance to the DEFORMED endpoint chord.

    This first-order beam solution is piecewise polynomial (degree <= 5).
    On each load/FE interval, find all stationary points of squared distance
    as well as the boundaries. This avoids missing the peak on a sample grid.
    L for the limits is the original reference length, excluding overhangs.
    """
    if not 0 <= start_m < end_m <= member.L() + 1e-8:
        raise ValueError("chord references must be inside the member")
    a = deformed_member_point(member, start_m, combo)
    b = deformed_member_point(member, end_m, combo)
    axis = b - a
    positive(float(np.linalg.norm(axis)), "deformed chord length")
    axis /= np.linalg.norm(axis)

    def perpendicular(station):
        delta = deformed_member_point(member, station, combo) - a
        return delta - delta.dot(axis) * axis

    knots = sorted(
        {
            start_m,
            end_m,
            *(p for p in displacement_breakpoints(member, combo) if start_m < p < end_m),
        }
    )
    max_distance, at = 0.0, start_m
    samples = np.cos(np.arange(6) * np.pi / 5)
    from numpy.polynomial import Polynomial

    for lo, hi in zip(knots, knots[1:]):
        if hi - lo <= 1e-10:
            continue
        centre, half = (lo + hi) / 2, (hi - lo) / 2
        offsets = np.array([perpendicular(centre + half * t) for t in samples])
        polynomials = [
            Polynomial(np.polynomial.polynomial.polyfit(samples, offsets[:, i], 5))
            for i in range(3)
        ]
        # Fail explicitly if a future non-polynomial solver is substituted.
        for t in (-0.7, -0.2, 0.35, 0.8):
            expected = perpendicular(centre + half * t)
            fitted = np.array([p(t) for p in polynomials])
            if not np.allclose(expected, fitted, rtol=1e-7, atol=1e-9):
                raise ValueError("chord extrema require the first-order polynomial beam solution")
        squared = sum((p * p for p in polynomials), Polynomial([0.0]))
        candidates = [-1.0, 1.0]
        for root in squared.deriv().roots():
            if abs(root.imag) < 1e-7 and -1.0 - 1e-9 <= root.real <= 1.0 + 1e-9:
                candidates.append(float(np.clip(root.real, -1.0, 1.0)))
        for t in candidates:
            station = centre + half * t
            distance = float(np.linalg.norm(perpendicular(station)))
            if distance > max_distance:
                max_distance, at = distance, station
    return max_distance, at


def chord_result_columns(roof, beam, combo, *, fallback="supports"):
    """Additional CSV fields, with limits assessed only for SLS combinations."""
    result = dict(
        chord_reference="",
        chord_start_support="",
        chord_end_support="",
        chord_start_s_m="",
        chord_end_s_m="",
        chord_span_m="",
        chord_max_departure_mm="",
        chord_max_at_s_m="",
        chord_L300_limit_mm="",
        chord_L300_status="",
        chord_L500_limit_mm="",
        chord_L500_status="",
    )
    if beam.category == "rafter":
        chord = rafter_chord(roof, beam, fallback=fallback)
    elif beam.category == "purlin":
        chord = purlin_chord(roof, beam)
    else:
        return result
    if chord is None:
        result.update(
            chord_reference="N/A: no wall-plate/ridge pair",
            chord_L300_status="N/A",
            chord_L500_status="N/A",
        )
        return result
    span = chord.end_m - chord.start_m
    distance, at = maximum_chord_departure(
        roof.model.members[beam.name], combo, chord.start_m, chord.end_m
    )
    result.update(
        chord_reference=chord.kind,
        chord_start_support=chord.start_label,
        chord_end_support=chord.end_label,
        chord_start_s_m=chord.start_m,
        chord_end_s_m=chord.end_m,
        chord_span_m=span,
        chord_max_departure_mm=distance * 1000,
        chord_max_at_s_m=at,
        chord_L300_limit_mm=span * 1000 / 300,
        chord_L500_limit_mm=span * 1000 / 500,
    )
    for ratio in (300, 500):
        result[f"chord_L{ratio}_status"] = (
            ("PASS" if distance < span / ratio else "FAIL")
            if combo.startswith("SLS_")
            else "NOT_CHECKED_ULS"
        )
    return result


def member_rows(roof, *, chord_fallback="supports"):
    rows = []
    for beam in roof.layout.beams:
        m = roof.model.members[beam.name]
        for combo in roof.model.load_combos:
            # Resolve exact local extrema; sample absolute GLOBAL Z movement.
            points = np.linspace(0, m.L(), 41)
            transform = m.T()[:3, :3]
            vertical = [
                float(
                    (
                        transform.T
                        @ np.array([m.deflection(d, float(x), combo) for d in ("dx", "dy", "dz")])
                    )[2]
                )
                for x in points
            ]
            rows.append(
                dict(
                    member=beam.name,
                    category=beam.category,
                    combination=combo,
                    width_mm=beam.timber.width * 1000,
                    height_mm=beam.timber.height * 1000,
                    length_m=m.L(),
                    material=beam.timber.material,
                    My_min_kNm=m.min_moment("My", combo) / 1000,
                    My_max_kNm=m.max_moment("My", combo) / 1000,
                    Mz_min_kNm=m.min_moment("Mz", combo) / 1000,
                    Mz_max_kNm=m.max_moment("Mz", combo) / 1000,
                    # Match the 2D script: tension positive, compression
                    # negative. PyNite's native convention is the opposite.
                    N_min_kN=-m.max_axial(combo) / 1000,
                    N_max_kN=-m.min_axial(combo) / 1000,
                    torque_max_abs_kNm=max(abs(m.min_torque(combo)), abs(m.max_torque(combo)))
                    / 1000,
                    Fy_max_abs_kN=max(abs(m.min_shear("Fy", combo)), abs(m.max_shear("Fy", combo)))
                    / 1000,
                    Fz_max_abs_kN=max(abs(m.min_shear("Fz", combo)), abs(m.max_shear("Fz", combo)))
                    / 1000,
                    vertical_min_mm=min(vertical) * 1000,
                    vertical_max_mm=max(vertical) * 1000,
                    **chord_result_columns(roof, beam, combo, fallback=chord_fallback),
                )
            )
    return rows


def support_rows(roof):
    rows = []
    for name, beam in roof.supports.items():
        n = roof.model.nodes[name]
        outward = -1 if "street" in beam else 1
        for combo in roof.model.load_combos:
            # Negate solver reactions: these are forces delivered TO supports.
            rows.append(
                dict(
                    support=name,
                    member=beam,
                    combination=combo,
                    x_m=n.X,
                    y_m=n.Y,
                    z_m=n.Z,
                    Dx_mm=n.DX[combo] * 1000,
                    Dy_mm=n.DY[combo] * 1000,
                    Dz_mm=n.DZ[combo] * 1000,
                    horizontal_X_stiffness_kn_mm=(
                        "rigid" if n.support_DX else (n.spring_DX[0] or 0.0) / 1e6
                    ),
                    horizontal_Y_stiffness_kn_mm=(
                        "rigid" if n.support_DY else (n.spring_DY[0] or 0.0) / 1e6
                    ),
                    Fx_kN=-n.RxnFX[combo] / 1000,
                    Fy_kN=-n.RxnFY[combo] / 1000,
                    Fz_kN=-n.RxnFZ[combo] / 1000,
                    outward_kN=-outward * n.RxnFY[combo] / 1000,
                    Mx_kNm=-n.RxnMX[combo] / 1000,
                    My_kNm=-n.RxnMY[combo] / 1000,
                    Mz_kNm=-n.RxnMZ[combo] / 1000,
                )
            )
    return rows


def print_ring_beam_rafter_forces(roof, supports):
    """Ring-beam reactions at rafter-aligned bearings, not rafter seat forces."""
    print("  Ring-beam horizontal loads at each rafter (kN; +outward, -inward):")
    print("    Wall-plate redistribution included; values are loads TO ring-beam supports.")
    print("    Fx is signed along the house, shown for the governing ULS outward case.")
    for beam in (b for b in roof.layout.beams if b.category == "rafter"):
        x = beam.start[0]
        plates = [
            p for p, category, _ in roof.rafter_seats.get(beam.name, []) if category == "wall_plate"
        ]
        if not plates:
            print(f"    {beam.name} x={x:.3f} m: no wall-plate seat; no direct ring-beam load.")
        for plate in plates:
            rows = [r for r in supports if r["member"] == plate and abs(r["x_m"] - x) < 1e-8]
            label = f"    {beam.name} x={x:.3f} m -> {plate}"
            if not rows:
                print(label + ": no bearing here; load redistributed through wall plate.")
                continue
            symmetric = next(r for r in rows if r["combination"] == "SLS_symmetric")
            service = max(
                (r for r in rows if r["combination"].startswith("SLS_")),
                key=lambda r: r["outward_kN"],
            )
            ultimate = max(
                (r for r in rows if r["combination"].startswith("ULS_")),
                key=lambda r: r["outward_kN"],
            )
            print(
                label + f": SLS symmetric Hout={symmetric['outward_kN']:+.3f}; "
                f"SLS max Hout={service['outward_kN']:+.3f} ({service['combination']}); "
                f"ULS max Hout={ultimate['outward_kN']:+.3f} ({ultimate['combination']}, "
                f"Fx={ultimate['Fx_kN']:+.3f})."
            )
    print("    Per-rafter maxima are not simultaneous; totals also include wall-end bearings.")


def print_summary(roof, members, supports, residuals):
    print(
        f"\n3D roof: purlin bearings laterally {'RESTRAINED' if roof.settings.purlin_lateral_restraint else 'FREE'}"
    )
    print(
        f"  {len(roof.layout.beams)} timbers; {len(roof.connections)} idealized seats; {len(roof.model.nodes)} nodes"
    )
    print("  NO kleštiny. Roof layers + timber self-weight + snow only.")
    print(
        f"  Roof layers {roof.settings.roof_mass:g} kg/m² actual slope; "
        f"roof snow {roof.settings.snow_load:g} kN/m² horizontal projection."
    )
    print("  NO suspended ceiling/OSB/SDK load; its replacement support is not designed.")
    print("  Snow is vertical per horizontal ROOF area, not ground sk; drift/wind omitted.")
    if roof.settings.horizontal_stiffness_kn_mm is None:
        print("  Horizontal supports RIGID (comparison model).")
    else:
        print(
            f"  Horizontal support springs: k={roof.settings.horizontal_stiffness_kn_mm:g} kN/mm "
            "per restrained X/Y direction, per bearing node."
        )
        print("  Calibrated sensitivity parameter, NOT verified anchorage/ring-beam stiffness.")
    print("  Vertical supports rigid; purlin roll restrained at bearings; seat yaw restrained.")
    print("  Purlin supports at wall centre lines; adjacent pieces remain independent.")
    print("  Outward positive = load delivered to support, not reaction on timber.")
    print("  Member N: positive=tension; negative=compression.")
    sls_supports = [r for r in supports if r["combination"].startswith("SLS_")]
    moving = max(sls_supports, key=lambda r: max(abs(r["Dx_mm"]), abs(r["Dy_mm"])))
    print(
        f"  Max SLS horizontal support movement: "
        f"{max(abs(moving['Dx_mm']), abs(moving['Dy_mm'])):.3f} mm "
        f"({moving['member']}, {moving['combination']}, x={moving['x_m']:.3f} m)."
    )
    for beam in (b for b in roof.layout.beams if b.category == "purlin"):
        load = -sum(
            r["Fz_kN"]
            for r in supports
            if r["member"] == beam.name and r["combination"] == "SLS_symmetric"
        )
        print(f"  {beam.name}: SLS_symmetric vertical load to wall bearings={load:.3f} kN.")
    print(
        "  Timber grades: "
        + "; ".join(
            f"{category}: {', '.join(sorted({b.timber.material for b in roof.layout.beams if b.category == category}))}"
            for category in ("rafter", "purlin", "wall_plate")
        )
    )
    for combo in roof.model.load_combos:
        support_group = [
            r for r in supports if r["combination"] == combo and "wall_plate" in r["member"]
        ]
        totals = {
            side: sum(
                r["outward_kN"]
                for r in support_group
                if ("street" in r["member"]) == (side == "street")
            )
            for side in ("street", "garden")
        }
        print(
            f"  {combo}: ring-beam NET outward totals: street {totals['street']:+.3f} kN; garden {totals['garden']:+.3f} kN"
        )
    print_ring_beam_rafter_forces(roof, supports)
    uplift = [r for r in supports if r["Fz_kN"] > 1e-6]
    if uplift:
        govern = max(uplift, key=lambda r: r["Fz_kN"])
        print(
            f"  WARNING: uplift {govern['Fz_kN']:.3f} kN at {govern['member']} "
            f"({govern['combination']}, x={govern['x_m']:.3f} m); gravity contact alone cannot carry it."
        )
    for category in ("rafter", "purlin", "wall_plate"):
        rows = [
            r for r in members if r["category"] == category and r["combination"].startswith("ULS")
        ]
        govern = max(rows, key=lambda r: max(abs(r["Mz_min_kNm"]), abs(r["Mz_max_kNm"])))
        moment = max(abs(govern["Mz_min_kNm"]), abs(govern["Mz_max_kNm"]))
        weak = max(rows, key=lambda r: max(abs(r["My_min_kNm"]), abs(r["My_max_kNm"])))
        weak_moment = max(abs(weak["My_min_kNm"]), abs(weak["My_max_kNm"]))
        service = [
            r for r in members if r["category"] == category and r["combination"].startswith("SLS")
        ]
        displacement = max(
            service, key=lambda r: max(abs(r["vertical_min_mm"]), abs(r["vertical_max_mm"]))
        )
        movement = max(abs(displacement["vertical_min_mm"]), abs(displacement["vertical_max_mm"]))
        print(
            f"  {category}: max |Mz| {moment:.3f} kNm ({govern['member']}, {govern['combination']}); "
            f"max |My| {weak_moment:.3f} kNm ({weak['member']}, {weak['combination']}); "
            f"max absolute vertical movement {movement:.2f} mm ({displacement['member']})"
        )
    print(f"  Global force/moment balance relative residual: {max(residuals.values()):.2e}")
    for category, reference in (("rafter", "endpoint"), ("purlin", "bearing")):
        print(
            f"  {category.capitalize()} departure from displaced {reference} chord "
            "(3D, SLS envelope; strict < limits):"
        )
        for beam in roof.layout.beams:
            if beam.category != category:
                continue
            service = [
                r
                for r in members
                if r["member"] == beam.name and r["combination"].startswith("SLS_")
            ]
            if service[0]["chord_span_m"] == "":
                print(f"    {beam.name}: {service[0]['chord_reference']}; L/300 and L/500 N/A")
                continue
            worst = max(service, key=lambda r: r["chord_max_departure_mm"])
            vertical = max(
                service, key=lambda r: max(abs(r["vertical_min_mm"]), abs(r["vertical_max_mm"]))
            )
            absolute = max(abs(vertical["vertical_min_mm"]), abs(vertical["vertical_max_mm"]))
            detail = f"; max absolute vertical={absolute:.3f} mm ({vertical['combination']})"
            print(
                f"    {beam.name} [{worst['chord_reference']}]: "
                f"L={worst['chord_span_m']:.3f} m; departure={worst['chord_max_departure_mm']:.3f} mm "
                f"({worst['combination']}); L/300={worst['chord_L300_limit_mm']:.3f} mm "
                f"{worst['chord_L300_status']}; L/500={worst['chord_L500_limit_mm']:.3f} mm "
                f"{worst['chord_L500_status']}{detail}"
            )
    print("  Forces/displacements only, NOT an EC5/connection/ring-beam safety assessment.")


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def horizontal_stiffness_argument(value):
    """CLI stiffness in kN/mm; 'rigid' restores the previous ideal supports."""
    if value.lower() == "rigid":
        return None
    try:
        return positive(float(value), "horizontal stiffness")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use a positive stiffness in kN/mm, or 'rigid'") from exc


def plot_model(roof, path, *, combo="SLS_symmetric", scale=20.0):
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 8), layout="constrained")
    axes = figure.add_subplot(projection="3d")
    colors = {"rafter": "#d9a51a", "purlin": "#d44936", "wall_plate": "#2789b0"}
    labelled = set()
    for beam in roof.layout.beams:
        member = roof.model.members[beam.name]
        points = np.linspace(0, member.L(), 31)
        start, end = np.array(beam.start), np.array(beam.end)
        original = np.array([start + (end - start) * x / member.L() for x in points])
        transform = member.T()[:3, :3]
        disp = np.array(
            [
                transform.T
                @ np.array([member.deflection(d, float(x), combo) for d in ("dx", "dy", "dz")])
                for x in points
            ]
        )
        axes.plot(*original.T, color=colors[beam.category], alpha=0.25, lw=1)
        label = beam.category if beam.category not in labelled else None
        axes.plot(*(original + scale * disp).T, color=colors[beam.category], lw=1.5, label=label)
        labelled.add(beam.category)
    supported = np.array(
        [
            (roof.model.nodes[n].X, roof.model.nodes[n].Y, roof.model.nodes[n].Z)
            for n in roof.supports
        ]
    )
    axes.scatter(*supported.T, color="black", s=10, label="bearings")
    axes.set(
        xlabel="X [m]",
        ylabel="Y [m]",
        zlabel="Z [m]",
        title=f"{combo}: deformation ×{scale:g}; no kleštiny",
    )
    axes.set_box_aspect((12, 9, 3))
    axes.view_init(elev=25, azim=-60)
    axes.legend(loc="upper left")
    figure.savefig(path, dpi=160)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house", type=Path, default=Path(__file__).with_name("house_ifc.py"))
    parser.add_argument("--output", type=Path, default=Path("roof_frame_3d"))
    parser.add_argument(
        "--purlin-lateral",
        choices=("free", "restrained", "both"),
        default="restrained",
        help="restrained uses the common spring (default); free omits purlin Y restraint",
    )
    parser.add_argument(
        "--horizontal-stiffness",
        type=horizontal_stiffness_argument,
        default=HORIZONTAL_SUPPORT_STIFFNESS_KN_MM,
        help="kN/mm per formerly fixed horizontal support DOF; use 'rigid' for comparison",
    )
    parser.add_argument(
        "--snow",
        type=float,
        help="kN/m² horizontal roof area, NOT ground sk; default from rafter_load.py",
    )
    parser.add_argument(
        "--roof-mass",
        type=float,
        default=Settings().roof_mass,
        help="kg/m² actual roof slope, EXCLUDING suspended ceiling; default 135",
    )
    parser.add_argument("--rafter-material", choices=("C22", "C24"), default="C22")
    parser.add_argument("--beam-material", choices=("C22", "C24"), default="C22")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument(
        "--rafter-chord-fallback",
        choices=("na", "supports"),
        default="supports",
        help="missing wall-plate/ridge pair: explicitly labelled actual support pair (default), or N/A",
    )
    args = parser.parse_args(argv)
    from rafter_load import SNOW_LOAD_KN_M2

    if args.snow is None:
        args.snow = SNOW_LOAD_KN_M2
    layout = RoofLayout.from_house(
        args.house, rafter_material=args.rafter_material, beam_material=args.beam_material
    )
    variants = (
        (False, True) if args.purlin_lateral == "both" else (args.purlin_lateral == "restrained",)
    )
    for restrained in variants:
        roof = build_roof_model(
            layout,
            Settings(
                roof_mass=args.roof_mass,
                snow_load=args.snow,
                purlin_lateral_restraint=restrained,
                horizontal_stiffness_kn_mm=args.horizontal_stiffness,
            ),
        )
        residuals = solve_roof_model(roof)
        members = member_rows(roof, chord_fallback=args.rafter_chord_fallback)
        supports = support_rows(roof)
        print_summary(roof, members, supports, residuals)
        prefix = str(args.output) + ("_restrained" if restrained else "_free")
        write_csv(prefix + "_members.csv", members)
        write_csv(prefix + "_supports.csv", supports)
        metadata = dict(
            source=str(layout.source),
            versions={
                "PyniteFEA": version("PyniteFEA"),
                "numpy": np.__version__,
                "matplotlib": version("matplotlib"),
            },
            settings=roof.settings.__dict__,
            timber_materials={
                category: sorted(
                    {b.timber.material for b in roof.layout.beams if b.category == category}
                )
                for category in ("rafter", "purlin", "wall_plate")
            },
            analysis="first-order elastic",
            rafter_chord=dict(
                reference="line through displaced rafter-centreline reference points",
                measure="maximum 3D perpendicular distance between reference points",
                length="original sloping chord length; eave overhangs excluded",
                fallback=args.rafter_chord_fallback,
                ratios=[300, 500],
                comparison="strict <, SLS combinations only",
                excludes_creep=True,
                not_complete_EC5_check=True,
            ),
            purlin_chord=dict(
                reference="line through displaced purlin-centreline points at the two wall bearings",
                support_locations="wall centre lines; independent nodes for adjacent pieces",
                measure="maximum 3D perpendicular distance between bearings; includes lateral bending",
                length="original bearing-to-bearing length; timber end overhangs excluded",
                ratios=[300, 500],
                comparison="strict <, SLS combinations only",
                excludes_creep=True,
                not_complete_EC5_check=True,
            ),
            equilibrium_relative_residual=residuals,
            combinations={name: combo.factors for name, combo in roof.model.load_combos.items()},
            omitted=[
                "kleštiny",
                "suspended ceiling",
                "wind",
                "snow drift",
                "EC5 strength/stability checks",
                "concrete/anchors",
            ],
            assumptions=[
                (
                    "rigid horizontal support (comparison model)"
                    if args.horizontal_stiffness is None
                    else "independent equal horizontal X/Y bearing springs; calibrated sensitivity, not verified stiffness"
                ),
                "vertical supports rigid; wall-plate spring locations follow existing analysis nodes, not actual anchor spacing",
                "purlin bearings at wall centre lines; adjacent pieces have separate end nodes",
                "purlin rolling restrained at bearings",
                "seat yaw restrained; roof-plane rafter bending released",
                "linear effective timber/support stiffness; no creep or nonlinear slip",
                "roof window area retained conservatively; no timber may bridge opening",
            ],
        )
        Path(prefix + "_basis.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not args.no_plot:
            plot_model(roof, prefix + "_model.png")
        print(
            f"  Output: {prefix}_members.csv, _supports.csv, _basis.json"
            + (", _model.png" if not args.no_plot else "")
        )


if __name__ == "__main__":
    main()
