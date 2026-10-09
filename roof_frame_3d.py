#!/usr/bin/env python3
"""Preliminary PyNite roof frame; compression spacers and optional collar ties.

Geometry is read from the arithmetic/data definitions in house_ifc.py without
executing that module. Units: m, N, Pa. Global Z is up, X along the house.
See roof_frame_3d.md for the important connection/support/load assumptions.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import dataclass, field, replace, asdict
from importlib.metadata import version
from math import atan2, ceil, degrees, hypot, isfinite, sqrt
from pathlib import Path
from typing import Literal

import numpy as np

# Sensitivity parameter, NOT a measured connection stiffness. Applied per X/Y
# direction ONLY to rafter connections to the rigid wall plate/ring beam.
# Purlin wall guides are rigid (Y can be explicitly freed for comparison).
# Gerber wall bearings follow the joint positions; either the middle or the
# outer pieces can provide the cantilevers supporting adjacent pieces.
HORIZONTAL_SUPPORT_STIFFNESS_KN_MM = 0.12 * 00.01  ################
# Dormer seats only: positive kN/mm, None for rigid, or "inherit" to use the
# general value above. Does not change the house-cut or normal-roof seats.
DORMER_HORIZONTAL_SUPPORT_STIFFNESS_KN_MM = 0.01

# Four longitudinal bolsters under the internal purlin joints. The factor is
# for sensitivity studies, NOT a measured connection or bolt stiffness.
SADDLE_LENGTH_M = 1.5  # fallback for synthetic layouts; IFC uses SEDLO_LENGTH
SADDLE_CONTACT_SPACING_M = 0.10
SADDLE_CONTACT_STIFFNESS_FACTOR = 1.0
TIMBER_E90_MEAN_PA = {"C18": 300e6, "C22": 330e6, "C24": 370e6}
TIMBER_MEAN_DENSITY_KG_M3 = {"C18": 380.0, "C22": 410.0, "C24": 420.0}
# Trial fastening, NOT a bolt specification/capacity check. Each end has two
# bolts at 1/3 and 2/3 of its overlap with the saddle (four per saddle).
SADDLE_BOLT_DIAMETER_MM = 12.0
SADDLE_BOLTS_PER_PURLIN_END = 2
SADDLE_BOLT_SLIP_GAP_MM = 0.0  # assumed relative slip before engagement
SADDLE_BOLT_HOLD_DOWN = "free"  # or "ideal", a tension-only rigid-limit trial
IDEAL_BOLT_HOLD_DOWN_N_M = 1e9  # numerical penalty, NOT physical axial stiffness
# Rigid-limit unilateral seating, NOT a calibrated timber contact stiffness.
IDEAL_WALL_PLATE_BEARING_N_M = 1e9
IDEAL_PURLIN_BEARING_N_M = 1e9  # near-rigid compression; no tensile anchorage

# Independent trial parameters; never read collar-tie dimensions from the IFC.
COLLAR_TIE_WIDTH_M = 0.05  # width of ONE board
COLLAR_TIE_HEIGHT_M = 0.15
COLLAR_TIE_BOARDS_PER_PAIR = 2
COLLAR_TIE_MATERIAL = "C18"
COLLAR_TIE_TOP_HEIGHT_M = None  # default bottom on purlin top; optional top above upper floor
COLLAR_TIE_MIDDLE_LOWERING_M = 0.0
COLLAR_TIE_OMIT_TOUCHING_SIDES = True

# Existing shortened garden-rafter geometry must also survive removal of the
# IFC collar constants. This cut is separate from the optional tie height.
SHORT_GARDEN_RAFTER_CUT_HEIGHT_M = 3.05  # above upper-storey floor


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
    material: str = "C18"

    def __post_init__(self):
        positive(self.width, "timber width")
        positive(self.height, "timber height")
        if self.material not in {"C18", "C22", "C24"}:
            raise ValueError("material must be C18, C22 or C24")

    @property
    def properties(self):
        b, h = self.width, self.height
        # Local y is section height; local z is section width.
        a, small = max(b, h), min(b, h)
        torsion = a * small**3 * (1 / 3 - 0.21 * (small / a) * (1 - small**4 / (12 * a**4)))
        return b * h, h * b**3 / 12, b * h**3 / 12, torsion


@dataclass(frozen=True)
class CollarTieParameters:
    width: float = COLLAR_TIE_WIDTH_M
    height: float = COLLAR_TIE_HEIGHT_M
    boards_per_pair: int = COLLAR_TIE_BOARDS_PER_PAIR
    material: str = COLLAR_TIE_MATERIAL
    top_height: float | None = COLLAR_TIE_TOP_HEIGHT_M
    middle_lowering: float = COLLAR_TIE_MIDDLE_LOWERING_M
    omit_touching_sides: bool = COLLAR_TIE_OMIT_TOUCHING_SIDES

    def __post_init__(self):
        Timber(self.width, self.height, self.material)
        if self.top_height is not None:
            positive(self.top_height, "collar top height")
        if type(self.boards_per_pair) is not int or self.boards_per_pair not in (1, 2):
            raise ValueError("collar boards_per_pair must be 1 or 2")
        if not isfinite(self.middle_lowering) or self.middle_lowering < 0:
            raise ValueError("collar middle lowering must be finite and non-negative")
        if self.top_height is not None and self.top_height - self.middle_lowering <= self.height:
            raise ValueError("collar bottom must remain above the upper floor")


@dataclass(frozen=True)
class BeamSpec:
    name: str
    category: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    timber: Timber
    bearings: tuple[float, ...] = ()  # global X along longitudinal beams
    wall_extent: tuple[float, float] | None = None
    pieces: int = 1  # separate boards represented by one axial collar member
    attached_rafters: tuple[str, ...] = ()
    supported_purlins: tuple[str, ...] = ()

    @property
    def length(self):
        return float(np.linalg.norm(np.subtract(self.end, self.start)))

    def z(self, y):
        return self.start[2] + (self.end[2] - self.start[2]) * (y - self.start[1]) / (
            self.end[1] - self.start[1]
        )


def gerber_load_paths(beams, joints):
    """Identify the supported end of each hinge using the determinate load path.

    A piece with two available supports (walls and/or hinges) is evaluated
    first. Its hinge reactions then load the neighbouring carrying piece.
    This covers suspended middles, a double-cantilever middle carrying sides,
    and asymmetric arrangements without inventing restraints at the hinges.
    """
    by_name = {b.name: b for b in beams}
    remaining = set(joints)
    pending = {name for pair in joints for name in pair}
    paths = {}
    while remaining:
        for name in sorted(pending):
            incident = sorted(pair for pair in remaining if name in pair)
            if incident and len(by_name[name].bearings) + len(incident) == 2:
                points = [*by_name[name].bearings, *(
                    by_name[left].end[0] for left, _ in incident
                )]
                if abs(points[1] - points[0]) <= 1e-9:
                    continue  # Coincident supports cannot stabilise this piece.
                for left, right in incident:
                    paths[(left, right)] = (
                        name, "j" if name == left else "i", right if name == left else left
                    )
                    remaining.remove((left, right))
                pending.remove(name)
                break
        else:
            raise ValueError("Gerber arrangement has no stable determinate support path")
    if any(len(by_name[name].bearings) != 2 for name in pending):
        raise ValueError("Gerber carrying pieces require two wall supports")
    return paths


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
    collar_parameters: CollarTieParameters | None = None
    saddle_parameters: SaddleParameters | None = None
    saddle_length_m: float = SADDLE_LENGTH_M
    purlin_system: str = "simple"
    gerber_joints: tuple[tuple[str, str], ...] = ()
    # Roof strip between inner-wall centres, not between Gerber hinges.
    middle_snow_bounds: tuple[float, float] | None = None

    def __post_init__(self):
        positive(self.saddle_length_m, "IFC saddle length")
        if self.middle_snow_bounds is not None:
            lo, hi = self.middle_snow_bounds
            if not all(isfinite(x) for x in (lo, hi)) or hi <= lo:
                raise ValueError("middle snow bounds must be finite and increasing")
        if not self.beams or len({b.name for b in self.beams}) != len(self.beams):
            raise ValueError("roof must have uniquely named members")
        names = {b.name for b in self.beams}
        if self.purlin_system not in {"simple", "saddles", "gerber"}:
            raise ValueError("purlin_system must be simple, saddles or gerber")
        if self.gerber_joints and self.purlin_system != "gerber":
            raise ValueError("Gerber joints require the Gerber purlin system")
        if self.purlin_system == "gerber" and self.saddle_parameters:
            raise ValueError("Gerber hinges cannot be combined with sedla")
        by_name = {b.name: b for b in self.beams}
        hinged_ends = set()
        for left_name, right_name in self.gerber_joints:
            if left_name not in names or right_name not in names:
                raise ValueError("unknown member in Gerber joint")
            left, right = by_name[left_name], by_name[right_name]
            if left.category != "purlin" or right.category != "purlin" or not np.allclose(
                left.end, right.start, rtol=0, atol=1e-9
            ):
                raise ValueError("Gerber purlin ends must meet")
            for end in ((left_name, "j"), (right_name, "i")):
                if end in hinged_ends:
                    raise ValueError("duplicate Gerber joint at a member end")
                hinged_ends.add(end)
        for beam in self.beams:
            if not all(isfinite(c) for c in (*beam.start, *beam.end)):
                raise ValueError(f"non-finite coordinates: {beam.name}")
            positive(beam.length, f"length of {beam.name}")
            if beam.category == "rafter" and beam.start[1] >= beam.end[1]:
                raise ValueError(f"rafter must run in positive Y: {beam.name}")
            if beam.category not in {
                "rafter",
                "purlin",
                "wall_plate",
                "collar",
                "saddle",
                "spacer",
            }:
                raise ValueError(f"unsupported physical member: {beam.category}")
            if beam.category == "spacer" and (
                len(beam.supported_purlins) != 2 or not set(beam.supported_purlins) <= names
            ):
                raise ValueError(f"invalid spacer attachments: {beam.name}")
            if beam.category == "collar" and (
                len(beam.attached_rafters) != 2
                or not set(beam.attached_rafters) <= names
                or beam.pieces not in (1, 2)
            ):
                raise ValueError(f"invalid collar attachments/board count: {beam.name}")
            if any(not beam.start[0] <= x <= beam.end[0] for x in beam.bearings):
                raise ValueError(f"bearing outside {beam.name}")
            if beam.category == "saddle" and (
                len(beam.bearings) != 1
                or len(beam.supported_purlins) != 2
                or not set(beam.supported_purlins) <= names
            ):
                raise ValueError(f"invalid saddle attachments: {beam.name}")
        if self.purlin_system == "gerber":
            gerber_load_paths(self.beams, self.gerber_joints)
        for patch in self.patches:
            if patch.x_min >= patch.x_max or patch.y_min >= patch.y_max:
                raise ValueError(f"invalid roof patch: {patch.name}")
            if not set(patch.rafters) <= names:
                raise ValueError(f"unknown rafter in {patch.name}")

    @classmethod
    def from_house(cls, path, *, rafter_material="C18", beam_material="C18", collar_ties=None,
                   purlin_system="gerber"):
        if purlin_system not in {"simple", "saddles", "gerber"}:
            raise ValueError("purlin_system must be simple, saddles or gerber")
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
        wall_centres = (bwt / 2, g("wall2_x") - bwt / 2,
                        g("wall3_x") - bwt / 2, width - bwt / 2)
        segments = g("PURLIN_X_SEGMENTS")
        if purlin_system != "gerber":
            # Legacy comparisons retain their original joints over the walls,
            # not wall supports incorrectly moved to the new Gerber hinges.
            segments = tuple(
                (name, lo if index == 0 else wall_centres[index],
                 hi if index == 2 else wall_centres[index + 1], height)
                for index, (name, lo, hi, height) in enumerate(segments)
            )
        gerber_joints = []
        if tuple(segment[0] for segment in segments) != ("left", "middle", "right"):
            raise ValueError("purlin segments must be ordered left, middle, right")
        supports = {name: [] for name, *_ in segments}
        for index, x in enumerate(wall_centres):
            matches = [name for name, lo, hi, _ in segments if lo <= x <= hi]
            if not matches:
                raise ValueError(f"no purlin piece contains wall centre x={x:g}")
            # A joint exactly above an inner wall retains the legacy outer
            # bearing assignment; never add two restraints at a shared hinge.
            name = matches[0] if index < 2 else matches[-1]
            if purlin_system != "gerber":
                # Legacy independent pieces each bear on their common wall.
                for name in matches:
                    supports[name].append(x)
            else:
                supports[name].append(x)
        for side, y in (
            ("street", ridge - g("VAZNICE_DIST")),
            ("garden", ridge + g("VAZNICE_DIST")),
        ):
            for segment, lo, hi, height in segments:
                z = g("PURLIN_TOP_Z") - height / 2
                beams.append(
                    BeamSpec(
                        f"{side}_purlin_{segment}",
                        "purlin",
                        (lo, y, z),
                        (hi, y, z),
                        Timber(g("VAZNICE_BASE"), height, beam_material),
                        tuple(supports[segment]),
                    )
                )
            if purlin_system == "gerber":
                gerber_joints.extend((
                    (f"{side}_purlin_left", f"{side}_purlin_middle"),
                    (f"{side}_purlin_middle", f"{side}_purlin_right"),
                ))

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
                cut_z = g("UPPER_FLOOR_START") + SHORT_GARDEN_RAFTER_CUT_HEIGHT_M
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
        layout = cls(tuple(beams), tuple(patches), Path(path), saddle_length_m=g("SEDLO_LENGTH"),
                     purlin_system=purlin_system, gerber_joints=tuple(gerber_joints),
                     middle_snow_bounds=wall_centres[1:3])
        return (
            layout
            if collar_ties is None
            else add_collar_ties(layout, collar_ties, upper_floor_z=g("UPPER_FLOOR_START"))
        )


def add_purlin_spacers(layout):
    """Snug, unbolted compression struts at the IFC main-rafter stations.

    Physical length is face-to-face; numerical attachments are at the purlin
    axes. End eccentricity and end-bearing compliance are not modelled.
    """
    if any(b.category == "spacer" for b in layout.beams):
        raise ValueError("purlin spacers already present")
    width, height = HouseInputs(layout.source).get("PURLIN_SPACER_SIZE")
    purlins = [b for b in layout.beams if b.category == "purlin"]
    spacers = []
    for rafter in layout.beams:
        if rafter.category != "rafter" or not rafter.name.endswith("_street"):
            continue
        x = rafter.start[0]
        ends = []
        for side in ("street", "garden"):
            matches = [
                b
                for b in purlins
                if b.name.startswith(side + "_") and b.start[0] - 1e-9 <= x <= b.end[0] + 1e-9
            ]
            if len(matches) == 2 and any(
                (a.name, b.name) in layout.gerber_joints
                for a in matches for b in matches if a is not b
            ):
                # Both physical pieces share one numerical hinge node.
                matches = [max(matches, key=lambda b: len(b.bearings))]
            if len(matches) != 1:
                raise ValueError(f"spacer at x={x:g} needs one {side} purlin, got {len(matches)}")
            ends.append(matches[0])
        street, garden = ends
        tops = [b.start[2] + b.timber.height / 2 for b in ends]
        if abs(tops[0] - tops[1]) > 1e-9 or any(height > b.timber.height for b in ends):
            raise ValueError("spacer requires aligned purlin tops and must fit their height")
        if street.timber.material != garden.timber.material:
            raise ValueError("specify a common purlin/spacer timber grade")
        z = tops[0] - height / 2
        spacers.append(
            BeamSpec(
                "spacer_" + rafter.name.split("_")[1],
                "spacer",
                (x, street.start[1] + street.timber.width / 2, z),
                (x, garden.start[1] - garden.timber.width / 2, z),
                Timber(width, height, street.timber.material),
                supported_purlins=(street.name, garden.name),
            )
        )
        if spacers[-1].start[1] >= spacers[-1].end[1]:
            raise ValueError("no face-to-face space for purlin spacer")
    if not spacers:
        raise ValueError("no main-rafter stations for purlin spacers")
    return replace(layout, beams=(*layout.beams, *spacers))


def add_collar_ties(layout, parameters, *, upper_floor_z):
    """Equivalent axial members on MAIN rafter axes, not dormer duplicates.

    Offset board positions determine omissions and middle/outer height groups;
    their eccentric connections and timber bending are deliberately omitted.
    """
    if layout.collar_parameters is not None or any(b.category == "collar" for b in layout.beams):
        raise ValueError("collar ties already present")
    if not isfinite(upper_floor_z):
        raise ValueError("upper floor elevation must be finite")
    main = sorted(
        (b for b in layout.beams if b.category == "rafter" and b.name.endswith("_street")),
        key=lambda b: b.start[0],
    )
    by_name = {b.name: b for b in layout.beams}
    middle = next(b for b in layout.beams if b.name == "street_purlin_middle")
    if parameters.top_height is None:
        # Follow the actual purlin datum, not the obsolete removed-tie height.
        tops = [b.start[2] + b.timber.height / 2 for b in layout.beams if b.category == "purlin"]
        if max(tops) - min(tops) > 1e-9:
            raise ValueError("automatic collar height requires aligned purlin tops")
        parameters = replace(parameters, top_height=tops[0] + parameters.height - upper_floor_z)
    lo, hi = (middle.bearings if len(middle.bearings) == 2
              else (middle.start[0], middle.end[0]))
    blocked = set()
    if parameters.omit_touching_sides:
        for left, right in zip(main, main[1:]):
            if (
                abs(right.start[0] - left.start[0] - (left.timber.width + right.timber.width) / 2)
                < 1e-9
            ):
                blocked.update(((left.name, 1), (right.name, -1)))
    collars = []
    for street in main:
        garden = by_name[street.name.removesuffix("street") + "garden"]
        available = [side for side in (-1, 1) if (street.name, side) not in blocked]
        groups = {}
        for side in available[: parameters.boards_per_pair]:
            board_x = street.start[0] + side * (street.timber.width + parameters.width) / 2
            lowering = parameters.middle_lowering if lo <= board_x <= hi else 0.0
            z = upper_floor_z + parameters.top_height - parameters.height / 2 - lowering
            groups[z] = groups.get(z, 0) + 1
        for group, (z, pieces) in enumerate(sorted(groups.items()), 1):
            ends = []
            for rafter in (street, garden):
                fraction = (z - rafter.start[2]) / (rafter.end[2] - rafter.start[2])
                if not 1e-8 < fraction < 1 - 1e-8:
                    raise ValueError(
                        f"collar height does not intersect {rafter.name}; "
                        "adjust script tie height or shortened-rafter cut"
                    )
                y = rafter.start[1] + fraction * (rafter.end[1] - rafter.start[1])
                ends.append((rafter.start[0], y, z))
            collars.append(
                BeamSpec(
                    f"collar_{street.name.split('_')[1]}_{group}",
                    "collar",
                    *ends,
                    Timber(parameters.width, parameters.height, parameters.material),
                    pieces=pieces,
                    attached_rafters=(street.name, garden.name),
                )
            )
    if not collars:
        raise ValueError("no collar ties can be placed")
    return replace(layout, beams=(*layout.beams, *collars), collar_parameters=parameters)


@dataclass(frozen=True)
class SaddleBoltParameters:
    diameter_mm: float = SADDLE_BOLT_DIAMETER_MM
    count_per_end: int = SADDLE_BOLTS_PER_PURLIN_END
    slip_gap_mm: float = SADDLE_BOLT_SLIP_GAP_MM
    hold_down: Literal["free", "ideal"] = SADDLE_BOLT_HOLD_DOWN

    def __post_init__(self):
        positive(self.diameter_mm, "bolt diameter")
        if type(self.count_per_end) is not int or self.count_per_end < 1:
            raise ValueError("bolts per end must be a positive integer")
        if not isfinite(self.slip_gap_mm) or self.slip_gap_mm < 0:
            raise ValueError("bolt slip gap must be finite and non-negative")
        if self.hold_down not in ("free", "ideal"):
            raise ValueError("bolt hold-down must be 'free' or 'ideal'")


def saddle_bolt_stiffness(purlin, saddle, diameter_mm, combination):
    """EC5 approximate lateral slip modulus per bolt, ONE shear plane, N/m.

    Mean density (not characteristic or the conservative self-weight density).
    Geometric mean for dissimilar timbers. Ku=2/3 Kser in ULS. Does NOT
    describe axial hold-down, friction, capacity or a tested fastening detail.
    """
    positive(diameter_mm, "bolt diameter")
    density = sqrt(
        TIMBER_MEAN_DENSITY_KG_M3[purlin.material] * TIMBER_MEAN_DENSITY_KG_M3[saddle.material]
    )
    return density**1.5 * diameter_mm / 23 * 1000 * (2 / 3 if combination.startswith("ULS_") else 1)


def bolt_face_terms(bolt, direction):
    """Relative displacement at the actual contacting faces, including rotation."""
    upper, lower = bolt["upper_node"], bolt["lower_node"]
    if direction == "X":
        return (
            (upper, "DX", 1.0),
            (lower, "DX", -1.0),
            (upper, "RY", -bolt["purlin_height_m"] / 2),
            (lower, "RY", -bolt["saddle_height_m"] / 2),
        )
    if direction == "Y":
        return (
            (upper, "DY", 1.0),
            (lower, "DY", -1.0),
            (upper, "RX", bolt["purlin_height_m"] / 2),
            (lower, "RX", bolt["saddle_height_m"] / 2),
        )
    raise ValueError("bolt shear direction must be X or Y")


def bolt_face_slip(model, bolt, direction, combo):
    return sum(
        c * getattr(model.nodes[node], dof)[combo]
        for node, dof, c in bolt_face_terms(bolt, direction)
    )


@dataclass(frozen=True)
class SaddleParameters:
    length: float = SADDLE_LENGTH_M
    contact_spacing: float = SADDLE_CONTACT_SPACING_M
    contact_stiffness_factor: float = SADDLE_CONTACT_STIFFNESS_FACTOR
    bolts: SaddleBoltParameters | None = None  # API can still request bearing-only

    def __post_init__(self):
        for name in ("length", "contact_spacing", "contact_stiffness_factor"):
            positive(getattr(self, name), "saddle " + name)


def add_purlin_saddles(layout, parameters=None):
    """Four bolsters centred under the two internal joints on each roof side."""
    if layout.purlin_system == "gerber":
        raise ValueError("cannot add sedla to Gerber hinges; select purlin_system='saddles'")
    if parameters is None:
        parameters = SaddleParameters(length=layout.saddle_length_m)
    if layout.saddle_parameters or any(b.category == "saddle" for b in layout.beams):
        raise ValueError("saddles already present")
    purlins = [b for b in layout.beams if b.category == "purlin"]
    assert len(purlins) == 6, "expected three purlin pieces on each of two sides"
    reference = purlins[0].timber
    assert all(
        np.allclose(
            (b.timber.width, b.timber.height),
            (reference.width, reference.height),
            rtol=0,
            atol=1e-9,
        )
        for b in purlins
    ), "all purlins must have the same width and height to add saddles"
    saddles = []
    for side in ("street", "garden"):
        pieces = sorted(
            (b for b in purlins if b.name.startswith(side + "_")), key=lambda b: b.start[0]
        )
        assert len(pieces) == 3, f"expected three {side} purlin pieces"
        for wall, (left, right) in enumerate(zip(pieces, pieces[1:]), 2):
            assert np.allclose(left.end, right.start, rtol=0, atol=1e-9), "purlin joint must meet"
            x, y, z = left.end
            assert all(
                any(abs(x - bearing) < 1e-9 for bearing in b.bearings) for b in (left, right)
            ), "joint must be over a wall bearing"
            half = parameters.length / 2
            if x - half < left.start[0] or x + half > right.end[0]:
                raise ValueError("saddle extends past its adjacent purlins")
            saddles.append(
                BeamSpec(
                    f"{side}_saddle_wall{wall}",
                    "saddle",
                    (x - half, y, z - reference.height),
                    (x + half, y, z - reference.height),
                    left.timber,
                    bearings=(x,),
                    supported_purlins=(left.name, right.name),
                )
            )
    return replace(layout, beams=(*layout.beams, *saddles), saddle_parameters=parameters,
                   purlin_system="saddles")


def saddle_contact_stiffness(purlin, saddle, area, factor=1.0):
    """N/m: two nominal full-depth E90 compression layers in series.

    An elastic starting estimate only: stress spreading, real contact area,
    gaps, fasteners and long-term compression are not calibrated here.
    """
    positive(area, "contact area")
    positive(factor, "contact stiffness factor")
    return (
        factor
        * area
        / (
            purlin.height / TIMBER_E90_MEAN_PA[purlin.material]
            + saddle.height / TIMBER_E90_MEAN_PA[saddle.material]
        )
    )


@dataclass(frozen=True)
class Settings:
    roof_mass: float = 50.0  # kg/m² actual slope; excludes suspended ceiling
    snow_load: float = 5.0  # kN/m² horizontal roof projection, NOT ground sk
    timber_density: float = 450.0
    gravity: float = 10.0
    purlin_lateral_restraint: bool = True
    purlin_bearing_uplift: bool = False  # anchored by default; report hold-down force
    middle_snow: bool = False  # optional additional middle-only snow combinations
    # Rafter -> wall plate/ring beam connections only, NOT purlin bearings.
    horizontal_stiffness_kn_mm: float | None = HORIZONTAL_SUPPORT_STIFFNESS_KN_MM
    dormer_horizontal_stiffness_kn_mm: float | None | Literal["inherit"] = (
        DORMER_HORIZONTAL_SUPPORT_STIFFNESS_KN_MM
    )
    joint_stiffness_factor: float = 1000.0

    def __post_init__(self):
        for name in ("timber_density", "gravity", "joint_stiffness_factor"):
            positive(getattr(self, name), name)
        if self.horizontal_stiffness_kn_mm is not None:
            positive(self.horizontal_stiffness_kn_mm, "horizontal_stiffness_kn_mm")
        dormer_stiffness = self.dormer_horizontal_stiffness_kn_mm
        if dormer_stiffness is not None and dormer_stiffness != "inherit":
            if isinstance(dormer_stiffness, str):
                raise ValueError(
                    "dormer_horizontal_stiffness_kn_mm must be positive, None or 'inherit'"
                )
            positive(dormer_stiffness, "dormer_horizontal_stiffness_kn_mm")
        for name in ("roof_mass", "snow_load"):
            if not isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and non-negative")

    def wall_plate_stiffness(self, plate_name):
        """Effective X/Y stiffness per rafter seat; None means rigid."""
        if (
            plate_name == "dormer_wall_plate"
            and self.dormer_horizontal_stiffness_kn_mm != "inherit"
        ):
            return self.dormer_horizontal_stiffness_kn_mm
        return self.horizontal_stiffness_kn_mm


@dataclass
class RoofModel:
    model: object
    layout: RoofLayout
    settings: Settings
    supports: dict[str, str] = field(default_factory=dict)
    connections: list[str] = field(default_factory=list)
    # Actual seats: longitudinal member, category, station on the rafter.
    rafter_seats: dict[str, list[tuple[str, str, float]]] = field(default_factory=dict)
    # Physical rafter/purlin pair -> numerical offset arm.
    seat_members: dict[tuple[str, str], str] = field(default_factory=dict)
    # Rafter -> rigid wall plate/ring beam: direct nodal support, no offset arm
    # or deformable wall-plate member in the FE model.
    wall_plate_connections: dict[tuple[str, str], str] = field(default_factory=dict)
    # Intermediate seats have only a vertical compression link to rigid ground.
    # Key = rafter seat node, value = compression-only spring name.
    wall_plate_bearings: dict[str, str] = field(default_factory=dict)
    # Timber node -> compression-only wall contact. Horizontal/roll reactions
    # remain at the timber node; only the vertical reaction is at its anchor.
    purlin_wall_bearings: dict[str, str] = field(default_factory=dict)
    # member name, load case, global vertical q, interval along member
    loads: list[tuple[str, str, float, float, float]] = field(default_factory=list)
    # Nodal collar self-weight (halved between its two rafter connections).
    nodal_loads: list[tuple[str, str, tuple[float, float, float]]] = field(default_factory=list)
    saddle_contacts: list[dict] = field(default_factory=list)
    saddle_bolts: list[dict] = field(default_factory=list)
    spacer_links: list[dict] = field(default_factory=list)
    gerber_connections: list[dict] = field(default_factory=list)

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
    if settings.middle_snow and layout.middle_snow_bounds is None:
        raise ValueError("middle snow requires middle_snow_bounds in the roof layout")
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
    for name, e, g in (
        ("C18", 9e9, 0.56e9), ("C22", 10e9, 0.63e9), ("C24", 11e9, 0.69e9)
    ):
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
    gerber_owners = {}
    by_name = {b.name: b for b in layout.beams}
    for index, (left_name, right_name) in enumerate(layout.gerber_joints):
        point = by_name[left_name].end
        for owner, end in ((left_name, by_name[left_name].end),
                           (right_name, by_name[right_name].start)):
            coordinates = tuple(round(float(c), 10) for c in end)
            gerber_owners[(owner, *coordinates)] = (f"gerber:{index}", point)

    def bearing_support(name, *, lateral, rafter_connection=False, connection_stiffness=None):
        rigid = not rafter_connection or connection_stiffness is None
        model.def_support(
            name,
            rigid,
            lateral and rigid,
            True,
            not rafter_connection,
            False,
            rafter_connection,
        )
        if not rigid:
            # kN/mm -> N/m. Vertical seating and rotational DOFs are independent.
            stiffness = connection_stiffness * 1e6
            model.def_support_spring(name, "DX", stiffness)
            if lateral:
                model.def_support_spring(name, "DY", stiffness)

    def node(point, *, owner=None):
        # Independent purlin pieces may meet at identical coordinates. Keep
        # their translations/rotations separate, even at a shared wall centre.
        coordinates = tuple(round(float(c), 10) for c in point)
        owner, point = gerber_owners.get((owner, *coordinates), (owner, point))
        coordinates = tuple(round(float(c), 10) for c in point)
        key = (owner, *coordinates)
        if key not in nodes:
            name = f"N{len(nodes):04d}"
            model.add_node(name, *point)
            nodes[key] = name
        return nodes[key]

    def purlin_wall_bearing(name, beam):
        """Release DZ only; retain the original horizontal/rotational guides."""
        if not settings.purlin_bearing_uplift:
            return
        timber_node = model.nodes[name]
        model.nodes[name].support_DZ = False
        ground = node(
            (timber_node.X, timber_node.Y, timber_node.Z - beam.timber.height / 2),
            owner=f"purlin-wall-bearing:{name}",
        )
        model.def_support(ground, True, True, True, True, True, True)
        contact = f"purlin_wall_bearing_{len(result.purlin_wall_bearings):03d}"
        model.add_spring(contact, ground, name, IDEAL_PURLIN_BEARING_N_M, comp_only=True)
        result.purlin_wall_bearings[name] = contact

    for beam in layout.beams:
        if beam.category == "spacer":
            continue  # Attach to separately owned purlin axes below.
        if beam.category == "wall_plate":
            # The wall plate/ring beam is one exactly rigid support structure.
            # Keep its outline for the drawings, not as a second elastic beam.
            # Its own weight acts directly on that structure, not the rafters.
            continue
        if beam.category == "collar":
            a, b = node(beam.start), node(beam.end)
            area = beam.timber.properties[0] * beam.pieces
            stiffness = model.materials[beam.timber.material].E * area / beam.length
            model.add_spring(beam.name, a, b, stiffness)
            # Bilateral axial link: no rotational/transverse stiffness, no
            # purlin support. Lumping its own weight avoids inventing bending.
            weight = settings.timber_density * settings.gravity * area * beam.length
            for end in (a, b):
                model.add_node_load(end, "FZ", -weight / 2, case="G")
                result.nodal_loads.append((end, "G", (0.0, 0.0, -weight / 2)))
            continue
        owner = beam.name if beam.category in {"purlin", "saddle"} else None
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

    paths = gerber_load_paths(layout.beams, layout.gerber_joints)
    hinge_releases = {}
    for left_name, right_name in layout.gerber_joints:
        left, right = by_name[left_name], by_name[right_name]
        supported, end, carrier = paths[(left_name, right_name)]
        # Shared translations, but independent rotations about both bending
        # axes. Retain torsion continuity/roll restraint as an explicit model
        # assumption; releasing torsion at both ends would be unstable.
        releases = hinge_releases.setdefault(supported, {})
        releases.update({"Ry" + end: True, "Rz" + end: True})
        hinge = node(left.end, owner=left.name)
        result.gerber_connections.append(dict(
            joint=f"gerber_{len(result.gerber_connections):02d}", node=hinge,
            left=left_name, right=right_name,
            supported=supported, supported_end=end, carrier=carrier,
            # Compatibility names for previous CSV consumers: these no longer
            # imply that the supported piece has zero direct wall bearings.
            suspended=supported, suspended_end=end,
            x_m=left.end[0], y_m=left.end[1],
        ))
    for name, releases in hinge_releases.items():
        model.def_releases(name, **releases)

    saddles = [b for b in layout.beams if b.category == "saddle"]
    by_name = {b.name: b for b in layout.beams}
    for beam in (b for b in layout.beams if b.category == "spacer"):
        ends = [by_name[name] for name in beam.supported_purlins]
        a, b = [node((beam.start[0], *p.start[1:]), owner=p.name) for p in ends]
        area = beam.timber.properties[0]
        stiffness = model.materials[beam.timber.material].E * area / beam.length
        model.add_spring(beam.name, a, b, stiffness, comp_only=True)
        result.spacer_links.append(dict(spacer=beam.name, stiffness_N_m=stiffness))
        weight = settings.timber_density * settings.gravity * area * beam.length
        for end in (a, b):
            model.add_node_load(end, "FZ", -weight / 2, case="G")
            result.nodal_loads.append((end, "G", (0.0, 0.0, -weight / 2)))
    saddle_bearings = {
        (purlin, saddle.bearings[0]) for saddle in saddles for purlin in saddle.supported_purlins
    }
    for saddle in saddles:
        parameters = layout.saddle_parameters
        centre = node((saddle.bearings[0], *saddle.start[1:]), owner=saddle.name)
        # A pinned vertical-plane bolster, not a clamped or composite beam.
        # Out-of-plane rigid-body DOFs are restrained on the bolster. They
        # stabilise the bearing-only model; with bolts they are an explicit
        # assumed saddle wall restraint, and can resist lateral bolt forces.
        # Vertical-only bearing contacts cannot restrain purlin Y motion.
        model.def_support(centre, True, True, True, True, False, True)
        purlin_wall_bearing(centre, saddle)
        result.supports[centre] = saddle.name
        for purlin_name in saddle.supported_purlins:
            purlin = by_name[purlin_name]
            lo, hi = max(saddle.start[0], purlin.start[0]), min(saddle.end[0], purlin.end[0])
            stations = np.linspace(lo, hi, max(1, ceil((hi - lo) / parameters.contact_spacing)) + 1)
            edges = np.array((lo, *((stations[:-1] + stations[1:]) / 2), hi))
            for x, width in zip(stations, np.diff(edges)):
                lower = node((x, *saddle.start[1:]), owner=saddle.name)
                upper = node((x, *purlin.start[1:]), owner=purlin.name)
                area = min(purlin.timber.width, saddle.timber.width) * width
                stiffness = saddle_contact_stiffness(
                    purlin.timber, saddle.timber, area, parameters.contact_stiffness_factor
                )
                name = f"saddle_contact_{len(result.saddle_contacts):03d}"
                model.add_spring(name, lower, upper, stiffness, comp_only=True)
                result.saddle_contacts.append(
                    dict(
                        contact=name,
                        saddle=saddle.name,
                        purlin=purlin.name,
                        x_m=float(x),
                        area_m2=float(area),
                        stiffness_N_m=float(stiffness),
                    )
                )
            if parameters.bolts:
                bolt_parameters = parameters.bolts
                for x in np.linspace(lo, hi, bolt_parameters.count_per_end + 2)[1:-1]:
                    lower = node((x, *saddle.start[1:]), owner=saddle.name)
                    upper = node((x, *purlin.start[1:]), owner=purlin.name)
                    name = f"saddle_bolt_{len(result.saddle_bolts):02d}"
                    hold_down = None
                    if bolt_parameters.hold_down == "ideal":
                        hold_down = name + "_hold_down"
                        model.add_spring(
                            hold_down, lower, upper, IDEAL_BOLT_HOLD_DOWN_N_M, tension_only=True
                        )
                    result.saddle_bolts.append(
                        dict(
                            bolt=name,
                            saddle=saddle.name,
                            purlin=purlin.name,
                            x_m=float(x),
                            y_m=saddle.start[1],
                            upper_node=upper,
                            lower_node=lower,
                            purlin_height_m=purlin.timber.height,
                            saddle_height_m=saddle.timber.height,
                            Kser_N_m=saddle_bolt_stiffness(
                                purlin.timber,
                                saddle.timber,
                                bolt_parameters.diameter_mm,
                                "SLS_symmetric",
                            ),
                            slip_gap_m=bolt_parameters.slip_gap_mm / 1000,
                            hold_down_spring=hold_down,
                        )
                    )

    rafters = [b for b in layout.beams if b.category == "rafter"]
    longitudinal = [b for b in layout.beams if b.category in {"purlin", "wall_plate"}]
    # A full rafter can cross the raised cut-wall plate after its eave seat.
    # Attach it only at the lowest/eave-side plate; any higher plate is bearing
    # only. Use the same geometry/height filter as actual seat creation below.
    attached_plate = {}
    for rafter in rafters:
        plates = [
            b
            for b in longitudinal
            if b.category == "wall_plate"
            and b.start[0] - 1e-9 <= rafter.start[0] <= b.end[0] + 1e-9
            and min(rafter.start[1], rafter.end[1]) - 1e-9
            <= b.start[1]
            <= max(rafter.start[1], rafter.end[1]) + 1e-9
            and 0 < rafter.z(b.start[1]) - b.start[2] < 0.4
        ]
        if plates:
            attached_plate[rafter.name] = min(
                plates, key=lambda b: rafter.z(b.start[1])
            ).name
    shared_gerber_seats = {}
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
            upper = node((x, bearing_y, rafter_z))
            if beam.category == "wall_plate":
                if beam.name != attached_plate[rafter.name]:
                    lower = node(
                        (x, bearing_y, beam.start[2]),
                        owner=f"bearing:{rafter.name}:{beam.name}",
                    )
                    model.def_support(lower, True, True, True, True, True, True)
                    contact = f"wall_plate_bearing_{len(result.wall_plate_bearings):03d}"
                    model.add_spring(
                        contact, lower, upper, IDEAL_WALL_PLATE_BEARING_N_M, comp_only=True
                    )
                    result.wall_plate_bearings[upper] = contact
                    # No horizontal springs, rotational restraint or hold-down.
                else:
                    # Connected eave seat: horizontal slip springs, bilateral
                    # vertical support and the existing seat-yaw restraint.
                    bearing_support(
                        upper,
                        lateral=True,
                        rafter_connection=True,
                        connection_stiffness=settings.wall_plate_stiffness(beam.name),
                    )
                result.supports[upper] = beam.name
                result.wall_plate_connections[(rafter.name, beam.name)] = upper
            else:
                xs.append(x)
                lower = node((x, bearing_y, beam.start[2]), owner=owner)
                if (rafter.name, lower) in shared_gerber_seats:
                    result.seat_members[(rafter.name, beam.name)] = shared_gerber_seats[(rafter.name, lower)]
                    continue
                name = f"seat_{len(result.connections):03d}"
                model.add_member(name, lower, upper, "JOINT", "JOINT")
                # Purlin offset arms retain their existing hinged rafter end.
                model.def_releases(name, Ryj=True, Rzj=True)
                result.connections.append(name)
                result.seat_members[(rafter.name, beam.name)] = name
                if layout.purlin_system == "gerber":
                    shared_gerber_seats[(rafter.name, lower)] = name
            station = (
                (bearing_y - rafter.start[1]) / (rafter.end[1] - rafter.start[1]) * rafter.length
            )
            result.rafter_seats.setdefault(rafter.name, []).append(
                (beam.name, beam.category, station)
            )
        if beam.category == "wall_plate":
            continue
        for x in sorted(set(xs)):
            name = node((x, beam.start[1], beam.start[2]), owner=owner)
            if any(abs(x - bearing) < 1e-9 for bearing in beam.bearings):
                bearing_support(name, lateral=settings.purlin_lateral_restraint)
                if (beam.name, x) in saddle_bearings:
                    # Keep the original rigid horizontal guides and roll
                    # restraint, but vertical load MUST pass through the saddle.
                    model.nodes[name].support_DZ = False
                else:
                    purlin_wall_bearing(name, beam)
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
            if settings.middle_snow:
                middle_lo, middle_hi = layout.middle_snow_bounds
                # Clip tributary strips, not the rafter centre positions: a
                # boundary rafter may also carry some snow from the middle.
                middle_width = max(
                    0.0, min(hi, patch.x_max, middle_hi) - max(lo, patch.x_min, middle_lo)
                )
                result.add_load(
                    beam.name, "S_middle",
                    -settings.snow_load * 1000 * middle_width * cosine, a, b,
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
        if settings.middle_snow:
            model.add_load_combo(f"{limit}_middle", {"G": g, "S_middle": s})
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
        for name, case, vector in roof.nodal_loads:
            n = roof.model.nodes[name]
            load = np.array(vector) * combo.factors.get(case, 0.0)
            force += load
            moment += np.cross((n.X, n.Y, n.Z), load)
            magnitude += np.linalg.norm(load)
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


def bolt_shear_assembly(roof, combo, states):
    """Face-slip connector stiffness and deadband offset, in GLOBAL DOFs.

    Each direction has an independent symmetric slip deadband (not an exact
    circular bolt-hole model). Generalised forces include the face-offset
    moments, so internal forces AND moments balance without rigid offset arms.
    """
    from scipy.sparse import coo_matrix

    size = 6 * len(roof.model.nodes)
    rows, columns, values = [], [], []
    offset = np.zeros((size, 1))
    dofs = {name: index for index, name in enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ"))}
    for bolt in roof.saddle_bolts:
        stiffness = bolt["Kser_N_m"] * (2 / 3 if combo.startswith("ULS_") else 1)
        for direction in ("X", "Y"):
            state = states[(bolt["bolt"], direction)]
            if not state:
                continue
            terms = [
                (6 * roof.model.nodes[node].ID + dofs[dof], coefficient)
                for node, dof, coefficient in bolt_face_terms(bolt, direction)
            ]
            for i, a in terms:
                offset[i, 0] += stiffness * state * bolt["slip_gap_m"] * a
                for j, b in terms:
                    rows.append(i)
                    columns.append(j)
                    values.append(stiffness * a * b)
    return coo_matrix((values, (rows, columns)), shape=(size, size)).tocsr(), offset


def spring_axial_gap(spring, combo):
    # Read raw nodal movement: PyNite Spring.D zeros global DX when inactive,
    # which is inappropriate for testing reclosure of an arbitrary-axis link.
    delta = np.array(
        [
            getattr(spring.j_node, d)[combo] - getattr(spring.i_node, d)[combo]
            for d in ("DX", "DY", "DZ")
        ]
    )
    return float(spring.T()[0, :3] @ delta)


def solve_saddle_contact(roof):
    """First-order active-set solve, including reopening AND reclosing contact.

    PyNite 3.2's two-node TC springs only deactivate, never reactivate. A
    previously opened contact can close after redistribution, so its built-in
    solve is insufficient here. Use its stiffness assembly, displacement solve
    and reaction recovery unchanged, with an opening/reclosing active-set update.
    These Analysis helpers are covered by the pinned-version regression tests.
    """
    from Pynite import Analysis

    model = roof.model
    Analysis._prepare_model(model)
    free, fixed, known = Analysis._partition_D(model)
    contacts = [model.springs[c["contact"]] for c in roof.saddle_contacts]
    contacts += [
        model.springs[name] for name in getattr(roof, "wall_plate_bearings", {}).values()
    ]
    contacts += [
        model.springs[name] for name in getattr(roof, "purlin_wall_bearings", {}).values()
    ]
    contacts += [model.springs[c["spacer"]] for c in getattr(roof, "spacer_links", [])]
    contacts += [
        model.springs[b["hold_down_spring"]] for b in roof.saddle_bolts if b["hold_down_spring"]
    ]
    for combo in model.load_combos.values():
        force, _ = Analysis._partition(model, model.P(combo.name), free, fixed)
        fer, _ = Analysis._partition(model, model.FER(combo.name), free, fixed)
        bolt_states = {
            (b["bolt"], direction): 1 if not b["slip_gap_m"] else 0
            for b in roof.saddle_bolts
            for direction in ("X", "Y")
        }
        for iteration in range(100):
            bolt_k, bolt_offset = bolt_shear_assembly(roof, combo.name, bolt_states)
            offset, _ = Analysis._partition(model, bolt_offset, free, fixed)
            k11, k12, _, _ = Analysis._partition(
                model,
                # Check stability after adding connector stiffness, not before.
                model.Ke(combo.name, check_stability=False, sparse=True).tocsr() + bolt_k,
                free,
                fixed,
            )
            displacement = Analysis._solve_unknown_disp(
                k11, force - fer + offset - k12 @ known, sparse=True, check_stability=True
            )
            Analysis._store_displacements(model, displacement, known, free, fixed, combo)
            changes = []
            for spring in contacts:
                gap = spring_axial_gap(spring, combo.name)
                # Small force deadband avoids numerical chatter at zero force.
                trial_force = -spring.ks * gap
                # Native spring axial force is positive in compression.
                allowed_force = trial_force if spring.comp_only else -trial_force
                if spring.active[combo.name] and allowed_force < -1e-5:
                    changes.append((spring, False))
                elif not spring.active[combo.name] and allowed_force > 1e-5:
                    changes.append((spring, True))
            bolt_changes = {}
            for bolt in roof.saddle_bolts:
                if not bolt["slip_gap_m"]:
                    continue
                for direction in ("X", "Y"):
                    slip = bolt_face_slip(model, bolt, direction, combo.name)
                    state = (
                        1
                        if slip > bolt["slip_gap_m"]
                        else (-1 if slip < -bolt["slip_gap_m"] else 0)
                    )
                    key = (bolt["bolt"], direction)
                    if bolt_states[key] != state:
                        bolt_changes[key] = state
            if not changes and not bolt_changes:
                break
            for spring, active in changes:
                spring.active[combo.name] = active
            bolt_states.update(bolt_changes)
        else:
            raise ValueError(f"unilateral roof contact did not converge: {combo.name}")
    Analysis._calc_reactions(model, log=False)
    # The shear connectors are assembled locally rather than registered as
    # PyNite springs. Recover their fixed-DOF reactions too (usually zero:
    # trial bolt stations lie away from wall bearings). Elastic support-spring
    # reactions are already recovered from node movement by PyNite.
    for bolt in roof.saddle_bolts:
        for combo in model.load_combos:
            stiffness = bolt["Kser_N_m"] * (2 / 3 if combo.startswith("ULS_") else 1)
            for direction in ("X", "Y"):
                slip = bolt_face_slip(model, bolt, direction, combo)
                force = stiffness * np.sign(slip) * max(abs(slip) - bolt["slip_gap_m"], 0.0)
                for name, dof, coefficient in bolt_face_terms(bolt, direction):
                    node = model.nodes[name]
                    if getattr(node, "support_" + dof):
                        reaction = "Rxn" + ("F" if dof.startswith("D") else "M") + dof[-1]
                        getattr(node, reaction)[combo] += force * coefficient
    model.solution = "Nonlinear TC"
    saddle_contact_rows(roof)  # check the final contact complementarity
    saddle_bolt_rows(roof)
    spacer_rows(roof)


def solve_roof_model(roof):
    # Start with verified first-order equilibrium. Second-order behaviour,
    # instability and nonlinear connection slip need a validated extension.
    if (
        roof.saddle_contacts or roof.spacer_links or roof.wall_plate_bearings
        or roof.purlin_wall_bearings
    ):
        # First-order contact active-set solve: separation is permitted,
        # tension is not. This is not P-delta or nonlinear timber analysis.
        solve_saddle_contact(roof)
    else:
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
    """Use the actual support pair: walls, hinges, or one of each."""
    member = roof.model.members[beam.name]
    if getattr(getattr(roof, "layout", None), "purlin_system", "simple") == "gerber" and not beam.bearings:
        return MemberChord(0.0, member.L(), "gerber_hinge_to_hinge",
                           member.i_node.name, member.j_node.name)
    start = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
    axis = member.T()[0, :3]
    bearings = []
    for name, supported_beam in roof.supports.items():
        if supported_beam == beam.name:
            node = roof.model.nodes[name]
            station = float((np.array((node.X, node.Y, node.Z)) - start).dot(axis))
            bearings.append((station, name))
    if getattr(getattr(roof, "layout", None), "purlin_system", "simple") == "gerber":
        for joint in getattr(roof, "gerber_connections", ()):
            if joint["supported"] == beam.name:
                at_start = joint["supported_end"] == "i"
                node = member.i_node if at_start else member.j_node
                bearings.append((0.0 if at_start else member.L(), node.name))
    if len(bearings) != 2:
        raise ValueError(f"purlin chord requires exactly two bearings: {beam.name}")
    (a, first), (b, last) = sorted(bearings)
    positive(b - a, f"reference span of {beam.name}")
    kind = "gerber_wall_to_hinge" if len(beam.bearings) == 1 else "bearing_to_bearing"
    return MemberChord(a, b, kind, first, last)


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


def maximum_chord_departure(member, combo, start_m, end_m, *, reference_points=None):
    """Maximum 3D perpendicular distance to the DEFORMED endpoint chord.

    This first-order beam solution is piecewise polynomial (degree <= 5).
    On each load/FE interval, find all stationary points of squared distance
    as well as the boundaries. This avoids missing the peak on a sample grid.
    L for the limits is the original reference length, excluding overhangs.
    Optional world reference points allow checking one piece against a chord
    whose endpoints lie on other members (e.g. a complete Gerber wall bay).
    """
    if not 0 <= start_m < end_m <= member.L() + 1e-8:
        raise ValueError("chord references must be inside the member")
    if reference_points is None:
        a = deformed_member_point(member, start_m, combo)
        b = deformed_member_point(member, end_m, combo)
    else:
        a, b = (np.asarray(point, dtype=float) for point in reference_points)
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


def purlin_wall_chord_result_columns(roof, beam, combo):
    """Additional inner-wall bay check for either Gerber arrangement."""
    result = dict(
        wall_chord_reference="", wall_chord_start_support="", wall_chord_end_support="",
        wall_chord_span_m="", wall_chord_max_departure_mm="", wall_chord_max_member="",
        wall_chord_max_at_s_m="", wall_chord_L300_limit_mm="", wall_chord_L300_status="",
        wall_chord_L500_limit_mm="", wall_chord_L500_status="",
    )
    if (beam.category != "purlin"
            or getattr(getattr(roof, "layout", None), "purlin_system", "simple") != "gerber"):
        return result
    joints = roof.layout.gerber_joints
    if not (any(right == beam.name for _, right in joints)
            and any(left == beam.name for left, _ in joints)):
        return result  # Only the central piece receives the complete bay check.
    left_name = next(left for left, right in roof.layout.gerber_joints if right == beam.name)
    right_name = next(right for left, right in roof.layout.gerber_joints if left == beam.name)
    names = (left_name, beam.name, right_name)
    wall_supports = sorted(
        (roof.model.nodes[node].X, node, owner)
        for node, owner in roof.supports.items() if owner in names
    )
    if len(wall_supports) != 4:
        raise ValueError("Gerber wall-bay check requires four actual wall bearings")
    (_, start_label, start_owner), (_, end_label, end_owner) = wall_supports[1:3]
    start_node, end_node = (roof.model.nodes[n] for n in (start_label, end_label))
    start = np.array((start_node.X, start_node.Y, start_node.Z))
    end = np.array((end_node.X, end_node.Y, end_node.Z))
    span = positive(float(np.linalg.norm(end - start)), f"wall bay of {beam.name}")
    wall_axis = (end - start) / span

    def station(member, point):
        origin = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
        return float((point - origin).dot(member.T()[0, :3]))

    reference = tuple(
        deformed_member_point(roof.model.members[owner],
                              station(roof.model.members[owner], point), combo)
        for owner, point in ((start_owner, start), (end_owner, end))
    )
    peak, at_wall, peak_member = -1.0, 0.0, ""
    for name in names:
        member = roof.model.members[name]
        lo, hi = max(0.0, station(member, start)), min(member.L(), station(member, end))
        if hi - lo <= 1e-10:
            continue  # zero-length cantilever when joints coincide with walls
        distance, at = maximum_chord_departure(
            member, combo, lo, hi, reference_points=reference
        )
        if distance > peak:
            peak, peak_member = distance, name
            original_point = np.array((member.i_node.X, member.i_node.Y, member.i_node.Z))
            original_point += member.T()[0, :3] * at
            at_wall = float((original_point - start).dot(wall_axis))
    result.update(
        wall_chord_reference="gerber_wall_to_wall",
        wall_chord_start_support=start_label, wall_chord_end_support=end_label,
        wall_chord_span_m=span, wall_chord_max_departure_mm=peak * 1000,
        wall_chord_max_member=peak_member, wall_chord_max_at_s_m=at_wall,
        wall_chord_L300_limit_mm=span * 1000 / 300,
        wall_chord_L500_limit_mm=span * 1000 / 500,
    )
    for ratio in (300, 500):
        result[f"wall_chord_L{ratio}_status"] = (
            ("PASS" if peak < span / ratio else "FAIL")
            if combo.startswith("SLS_") else "NOT_CHECKED_ULS"
        )
    return result


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
        **purlin_wall_chord_result_columns(roof, beam, combo),
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
        if beam.category == "wall_plate":
            continue  # rigid support outline, not an analysed elastic timber
        if beam.category in {"collar", "spacer"}:
            spring = roof.model.springs[beam.name]
            for combo in roof.model.load_combos:
                axial = -float(spring.axial(combo)) / 1000 if spring.active[combo] else 0.0
                vertical = [n.DZ[combo] * 1000 for n in (spring.i_node, spring.j_node)]
                rows.append(
                    dict(
                        member=beam.name,
                        category=beam.category,
                        combination=combo,
                        pieces=beam.pieces,
                        width_mm=beam.timber.width * 1000,
                        height_mm=beam.timber.height * 1000,
                        length_m=beam.length,
                        material=beam.timber.material,
                        My_min_kNm="",
                        My_max_kNm="",
                        Mz_min_kNm="",
                        Mz_max_kNm="",
                        N_min_kN=axial,
                        N_max_kN=axial,
                        torque_max_abs_kNm="",
                        Fy_max_abs_kN="",
                        Fz_max_abs_kN="",
                        vertical_min_mm=min(vertical),
                        vertical_max_mm=max(vertical),
                        **chord_result_columns(roof, beam, combo, fallback=chord_fallback),
                    )
                )
            continue
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
                    pieces=beam.pieces,
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


def support_reaction_node(roof, name):
    """Bearing-only reactions live at ground; movements live at the rafter."""
    contact = getattr(roof, "wall_plate_bearings", {}).get(name)
    return roof.model.springs[contact].i_node if contact else roof.model.nodes[name]


def support_rows(roof):
    rows = []
    for name, beam in roof.supports.items():
        n = roof.model.nodes[name]
        reaction = support_reaction_node(roof, name)
        bearing_only = name in roof.wall_plate_bearings
        purlin_contact = roof.purlin_wall_bearings.get(name)
        vertical_reaction = roof.model.springs[purlin_contact].i_node if purlin_contact else reaction
        contact = purlin_contact or roof.wall_plate_bearings.get(name)
        outward = -1 if "street" in beam else 1
        for combo in roof.model.load_combos:
            # Negate solver reactions: these are forces delivered TO supports.
            rows.append(
                dict(
                    support=name,
                    member=beam,
                    support_kind=(
                        ("rafter_bearing_only" if bearing_only else "rafter_connection")
                        if "wall_plate" in beam
                        else (
                            ("saddle_bearing_only" if purlin_contact else "saddle_bearing")
                            if "saddle" in beam
                            else "purlin_bearing_only" if purlin_contact
                            else "purlin_horizontal_guide" if not n.support_DZ else "purlin_bearing"
                        )
                    ),
                    combination=combo,
                    x_m=n.X,
                    y_m=n.Y,
                    z_m=n.Z,
                    Dx_mm=n.DX[combo] * 1000,
                    Dy_mm=n.DY[combo] * 1000,
                    horizontal_movement_mm=hypot(n.DX[combo], n.DY[combo]) * 1000,
                    Dz_mm=n.DZ[combo] * 1000,
                    vertical_contact_active=(
                        roof.model.springs[contact].active[combo]
                        if contact
                        else ""
                    ),
                    horizontal_X_stiffness_kn_mm=(
                        "rigid" if n.support_DX else (n.spring_DX[0] or 0.0) / 1e6
                    ),
                    horizontal_Y_stiffness_kn_mm=(
                        "rigid" if n.support_DY else (n.spring_DY[0] or 0.0) / 1e6
                    ),
                    Fx_kN=-reaction.RxnFX[combo] / 1000,
                    Fy_kN=-reaction.RxnFY[combo] / 1000,
                    Fz_kN=-vertical_reaction.RxnFZ[combo] / 1000,
                    outward_kN=-outward * reaction.RxnFY[combo] / 1000,
                    Mx_kNm=-reaction.RxnMX[combo] / 1000,
                    My_kNm=-reaction.RxnMY[combo] / 1000,
                    Mz_kNm=-reaction.RxnMZ[combo] / 1000,
                )
            )
    return rows


def uplift_locations(supports):
    """Worst upward support load per node, over every analysed combination."""
    locations = {}
    for row in supports:
        if row["Fz_kN"] > 1e-6 and (
            row["support"] not in locations
            or row["Fz_kN"] > locations[row["support"]]["Fz_kN"]
        ):
            locations[row["support"]] = row
    return list(locations.values())


def lift_off_locations(supports):
    """Worst actual opening at a unilateral rafter or purlin wall bearing, in mm."""
    locations = {}
    for row in supports:
        if (
            row.get("support_kind") in (
                "rafter_bearing_only", "purlin_bearing_only", "saddle_bearing_only"
            )
            and row["Dz_mm"] > 1e-6
            and (
                row["support"] not in locations
                or row["Dz_mm"] > locations[row["support"]]["Dz_mm"]
            )
        ):
            locations[row["support"]] = row
    return list(locations.values())


def print_ring_beam_rafter_forces(roof, supports):
    """Direct connection loads delivered to the rigid wall plate/ring beam."""
    print("  Ring-beam horizontal loads at each rafter (kN; +outward, -inward):")
    print(
        "    Direct connection forces TO the single rigid wall plate/ring beam; no redistribution."
    )
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
                print(label + ": no modelled connection here.")
                continue
            if rows[0].get("support_kind") == "rafter_bearing_only":
                print(label + ": bearing only; no horizontal force or hold-down.")
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
    print("    Per-rafter maxima are not simultaneous; totals sum all rafter connections.")


def saddle_contact_rows(roof):
    """Compression positive; gap positive means separation of contact faces."""
    rows = []
    for contact in roof.saddle_contacts:
        spring = roof.model.springs[contact["contact"]]
        for combo in roof.model.load_combos:
            active = spring.active[combo]
            force = float(spring.axial(combo)) if active else 0.0
            gap = spring.j_node.DZ[combo] - spring.i_node.DZ[combo]
            if force < -1e-5 or (not active and gap < -1e-8):
                raise ValueError(f"invalid compression contact: {contact['contact']}/{combo}")
            rows.append(
                dict(
                    **contact,
                    combination=combo,
                    active=bool(active),
                    stiffness_kN_mm=contact["stiffness_N_m"] / 1e6,
                    compression_kN=force / 1000,
                    pressure_MPa=force / contact["area_m2"] / 1e6,
                    gap_mm=float(gap * 1000),
                )
            )
    return rows


def saddle_bolt_rows(roof):
    """Forces delivered to purlin faces; shear and hold-down are separate."""
    rows = []
    for bolt in roof.saddle_bolts:
        for combo in roof.model.load_combos:
            stiffness = bolt["Kser_N_m"] * (2 / 3 if combo.startswith("ULS_") else 1)
            slips = {d: bolt_face_slip(roof.model, bolt, d, combo) for d in ("X", "Y")}
            force = {
                d: -stiffness * np.sign(slip) * max(abs(slip) - bolt["slip_gap_m"], 0.0)
                for d, slip in slips.items()
            }
            upper, lower = (roof.model.nodes[bolt[n]] for n in ("upper_node", "lower_node"))
            gap = upper.DZ[combo] - lower.DZ[combo]
            tension = 0.0
            if bolt["hold_down_spring"]:
                spring = roof.model.springs[bolt["hold_down_spring"]]
                tension = -float(spring.axial(combo)) if spring.active[combo] else 0.0
                if tension < -1e-5 or (not spring.active[combo] and gap > 1e-8):
                    raise ValueError(f"invalid bolt hold-down: {bolt['bolt']}/{combo}")
            rows.append(
                dict(
                    bolt=bolt["bolt"],
                    saddle=bolt["saddle"],
                    purlin=bolt["purlin"],
                    x_m=bolt["x_m"],
                    y_m=bolt["y_m"],
                    combination=combo,
                    shear_stiffness_kN_mm=stiffness / 1e6,
                    slip_gap_mm=bolt["slip_gap_m"] * 1000,
                    slip_X_mm=slips["X"] * 1000,
                    slip_Y_mm=slips["Y"] * 1000,
                    Fx_to_purlin_kN=force["X"] / 1000,
                    Fy_to_purlin_kN=force["Y"] / 1000,
                    shear_resultant_kN=float(np.hypot(force["X"], force["Y"]) / 1000),
                    separation_mm=float(gap * 1000),
                    hold_down_tension_kN=tension / 1000,
                    hold_down="ideal" if bolt["hold_down_spring"] else "free",
                )
            )
    return rows


def spacer_rows(roof):
    """Compression-positive strut forces; opening is positive axial end slip."""
    rows = []
    for link in getattr(roof, "spacer_links", []):
        spring = roof.model.springs[link["spacer"]]
        for combo in roof.model.load_combos:
            gap = spring_axial_gap(spring, combo)
            force = -spring.ks * gap if spring.active[combo] else 0.0
            if force < -1e-5 or (not spring.active[combo] and gap < -1e-5 / spring.ks):
                raise ValueError(f"invalid spacer contact: {link['spacer']}, {combo}")
            rows.append(
                dict(
                    **link,
                    combination=combo,
                    active=spring.active[combo],
                    compression_kN=max(force, 0.0) / 1000,
                    opening_mm=gap * 1000,
                )
            )
    return rows


def timber_categories(layout):
    return tuple(
        category
        for category in ("rafter", "purlin", "wall_plate", "collar", "saddle", "spacer")
        if any(b.category == category for b in layout.beams)
    )


def gerber_joint_rows(roof):
    """Forces delivered by a hinge-supported piece to its carrying neighbour."""
    rows = []
    for joint in roof.gerber_connections:
        node = roof.model.nodes[joint["node"]]
        member = roof.model.members[joint["supported"]]
        at_start = joint["supported_end"] == "i"
        submember, _ = member.find_member(0.0 if at_start else member.L())
        offset = 0 if at_start else 6
        for combo in roof.model.load_combos:
            force = -submember.F(combo).ravel()[offset:offset + 6]
            rows.append(dict(
                **joint, combination=combo,
                Fx_to_carrier_kN=force[0] / 1000, Fy_to_carrier_kN=force[1] / 1000,
                Fz_to_carrier_kN=force[2] / 1000, Mx_to_carrier_kNm=force[3] / 1000,
                My_to_carrier_kNm=force[4] / 1000, Mz_to_carrier_kNm=force[5] / 1000,
                # Legacy aliases; the carrier can now be the middle piece.
                Fx_to_outer_kN=force[0] / 1000, Fy_to_outer_kN=force[1] / 1000,
                Fz_to_outer_kN=force[2] / 1000, Mx_to_outer_kNm=force[3] / 1000,
                My_to_outer_kNm=force[4] / 1000, Mz_to_outer_kNm=force[5] / 1000,
                Dx_mm=node.DX[combo] * 1000, Dy_mm=node.DY[combo] * 1000,
                Dz_mm=node.DZ[combo] * 1000,
            ))
    return rows


def print_summary(roof, members, supports, residuals):
    print(
        f"\n3D roof: direct purlin Y guides {'RESTRAINED' if roof.settings.purlin_lateral_restraint else 'FREE'}"
    )
    print(
        f"  {sum(b.category != 'wall_plate' for b in roof.layout.beams)} analysed timbers; "
        f"{len(roof.connections)} purlin seats; "
        f"{len(roof.wall_plate_connections)} rafter-to-rigid-ring-beam seats; "
        f"{len(roof.model.nodes)} nodes"
    )
    collars = [b for b in roof.layout.beams if b.category == "collar"]
    if roof.spacer_links:
        print(
            f"  {len(roof.spacer_links)} purlin spacers: compression-only EA/L, physical face-to-face length."
        )
        print("  Spacer self-weight included; NO buckling, bearing or joint-capacity check.")
        rows = spacer_rows(roof)
        for link in roof.spacer_links:
            worst = max(
                (r for r in rows if r["spacer"] == link["spacer"]),
                key=lambda r: r["compression_kN"],
            )
            print(
                f"    {link['spacer']}: max compression {worst['compression_kN']:.3f} kN ({worst['combination']})"
            )
    if collars:
        parameters = roof.layout.collar_parameters
        print(
            f"  OPTIONAL kleštiny: {len(collars)} equivalent axial members, "
            f"{sum(b.pieces for b in collars)} boards, "
            f"{parameters.width * 1000:g}×{parameters.height * 1000:g} mm "
            f"{parameters.material}; top height {parameters.top_height:g} m above upper floor; "
            f"middle lowering {parameters.middle_lowering:g} m."
        )
        print(
            "  Collar connections ideal pinned axial links to MAIN rafters, not supported by purlins."
        )
        print("  Collar self-weight included; NO collar bending, buckling or joint-capacity check.")
    else:
        print("  NO kleštiny. Roof layers + timber self-weight + snow only.")
    print(
        f"  Roof layers {roof.settings.roof_mass:g} kg/m² actual slope; "
        f"roof snow {roof.settings.snow_load:g} kN/m² horizontal projection."
    )
    print("  NO suspended ceiling/OSB/SDK load; its replacement support is not designed.")
    print("  Snow is vertical per horizontal ROOF area, not ground sk; drift/wind omitted.")
    if roof.settings.middle_snow:
        lo, hi = roof.layout.middle_snow_bounds
        print(f"  Additional SLS_middle/ULS_middle: snow only at x={lo:.3f}..{hi:.3f} m "
              "(inner-wall centres), both roof sides; permanent load remains everywhere.")
        print("  Artificial snow-pattern sensitivity case, NOT a code-prescribed drift/uplift check.")
    print(
        "  Rafter-to-wall-plate/ring-beam connection stiffness per X/Y direction: "
        f"other={format_horizontal_stiffness(roof.settings.horizontal_stiffness_kn_mm)}; "
        f"dormer={format_horizontal_stiffness(roof.settings.wall_plate_stiffness('dormer_wall_plate'))}."
    )
    print("  Sensitivity parameters, NOT verified connection/anchorage stiffness.")
    print(
        "  Purlin wall bearings compression-only, upward lift-off allowed."
        if roof.settings.purlin_bearing_uplift
        else "  Purlin wall bearings vertically attached; no lift-off; upward force is hold-down demand."
    )
    print("  Purlin horizontal guides/roll restraints unchanged, including at opened bearings.")
    for row in lift_off_locations(supports):
        if row["support_kind"] in ("purlin_bearing_only", "saddle_bearing_only"):
            print(f"  WARNING: purlin wall bearing lift-off {row['Dz_mm']:.3f} mm at "
                  f"{row['member']} ({row['combination']}, x={row['x_m']:.3f} m); circled in PNGs.")
    for row in uplift_locations(supports):
        if row["support_kind"] in ("purlin_bearing", "saddle_bearing"):
            print(f"  WARNING: purlin support upward force {row['Fz_kN']:.3f} kN at "
                  f"{row['member']} ({row['combination']}, x={row['x_m']:.3f} m); "
                  "required hold-down, anchorage capacity NOT checked; circled in PNGs.")
    print(
        f"  {len(roof.wall_plate_bearings)} intermediate wall-plate seats: compression-only "
        "vertical bearing; no horizontal restraint, rotation restraint or hold-down."
    )
    print("  Wall plate/ring beam is one immovable rigid structure, not an elastic timber member.")
    print("  Wall-plate spring movements are rafter connection slip, not ring-beam movement.")
    contacts = saddle_contact_rows(roof)
    bolts = saddle_bolt_rows(roof)
    if contacts:
        parameters = roof.layout.saddle_parameters
        print(
            f"  Four {parameters.length:g} m sedla, same section as purlins; flexible timber beams."
        )
        print("  Internal purlin vertical loads pass through compression-only saddle contact.")
        print("  Pieces have separate end rotations; saddles couple them through bearing contact.")
        print("  Contact k = factor × A / (h_p/E90,p + h_s/E90,s), nominal full-depth compression.")
        print(
            f"  Contact stiffness factor={parameters.contact_stiffness_factor:g}; "
            f"maximum mesh spacing={parameters.contact_spacing:g} m; elastic ESTIMATE, not calibrated."
        )
        print("  No friction or glued/full-composite constraint; saddle centre vertically pinned.")
        if bolts:
            parameters = roof.layout.saddle_parameters.bolts
            print(
                f"  Trial bolts: {parameters.count_per_end} per purlin end, "
                f"{len(roof.saddle_bolts)} total; diameter {parameters.diameter_mm:g} mm; "
                f"assumed relative slip gap {parameters.slip_gap_mm:g} mm; "
                f"vertical hold-down={parameters.hold_down}."
            )
            print(
                "  Face-slip springs include timber rotations; partial composite action, NOT rigid bonding."
            )
            print("  Kser=rho_mean^1.5 × d / 23 N/mm per bolt/shear plane; ULS Ku=2/3 Kser.")
            print(
                "  Bolts can also transfer lateral Y load into saddle wall supports, even with direct Y guides free."
            )
            print(
                "  Saddle wall support assumes fixed DX/DY/roll/yaw, free vertical-plane bending rotation."
            )
            if parameters.hold_down == "ideal":
                print(
                    "  Ideal hold-down is a tension-only numerical rigid-limit bound, NOT calibrated bolt stiffness."
                )
            worst = max(bolts, key=lambda r: r["shear_resultant_kN"])
            print(
                f"  Max trial bolt shear={worst['shear_resultant_kN']:.3f} kN "
                f"({worst['bolt']}, {worst['combination']}); NO bolt capacity/spacing check."
            )
        else:
            print("  NO bolt action (bearing-only comparison).")
        for saddle in (b for b in roof.layout.beams if b.category == "saddle"):
            group = [r for r in contacts if r["saddle"] == saddle.name]
            worst = max(group, key=lambda r: r["pressure_MPa"])
            print(
                f"    {saddle.name}: max contact pressure {worst['pressure_MPa']:.3f} MPa "
                f"({worst['combination']}); NOT a bearing-capacity check."
            )
    else:
        if roof.gerber_connections:
            print("  GERBER purlins: wall-centre bearings assigned to the pieces containing them.")
            print("  Hinges transfer axial/shear forces, release both bending moments; no added support under cantilever tips.")
            print("  Torsion continuity retained; wall bearings restrain roll. Joint strength/slip NOT verified.")
            for joint in roof.gerber_connections:
                node = roof.model.nodes[joint['node']]
                print(f"    {joint['joint']}: x={node.X:.3f} m, y={node.Y:.3f} m; "
                      f"{joint['carrier']} carries {joint['supported']}; "
                      f"SLS hinge Dz={node.DZ['SLS_symmetric'] * 1000:+.3f} mm")
        else:
            print("  Purlin supports at wall centre lines; adjacent pieces remain independent.")
    print("  Purlin X translation rigid; Y rigid unless --purlin-lateral free.")
    print("  Outward positive = load delivered to support, not reaction on timber.")
    print("  Member N: positive=tension; negative=compression.")
    print_wall_plate_connection_movements(roof)
    hinge_rows = gerber_joint_rows(roof)
    for beam in (b for b in roof.layout.beams if b.category == "purlin"):
        hinge_load = -sum(row["Fz_to_carrier_kN"] for row in hinge_rows
                          if row["supported"] == beam.name and row["combination"] == "SLS_symmetric")
        if any(j["supported"] == beam.name for j in roof.gerber_connections):
            print(f"  {beam.name}: SLS_symmetric vertical load to Gerber hinges={hinge_load:.3f} kN.")
        if not beam.bearings:
            continue
        load = -sum(
            r["Fz_kN"]
            for r in supports
            if r["member"] == beam.name and r["combination"] == "SLS_symmetric"
        )
        load += sum(
            r["compression_kN"]
            for r in contacts
            if r["purlin"] == beam.name and r["combination"] == "SLS_symmetric"
        )
        load -= sum(
            r["hold_down_tension_kN"]
            for r in bolts
            if r["purlin"] == beam.name and r["combination"] == "SLS_symmetric"
        )
        print(f"  {beam.name}: SLS_symmetric vertical load to wall bearings={load:.3f} kN.")
    print(
        "  Timber grades: "
        + "; ".join(
            f"{category}: {', '.join(sorted({b.timber.material for b in roof.layout.beams if b.category == category}))}"
            for category in timber_categories(roof.layout)
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
    if collars:
        print("  Collar axial-force envelope: +tension, -compression (total for grouped boards):")
        for beam in collars:
            service = [
                r
                for r in members
                if r["member"] == beam.name and r["combination"].startswith("SLS_")
            ]
            ultimate = [
                r
                for r in members
                if r["member"] == beam.name and r["combination"].startswith("ULS_")
            ]
            worst_s = max(service, key=lambda r: abs(r["N_min_kN"]))
            worst_u = max(ultimate, key=lambda r: abs(r["N_min_kN"]))
            print(
                f"    {beam.name} x={beam.start[0]:.3f} m, {beam.pieces} board(s), L={beam.length:.3f} m: "
                f"SLS N={worst_s['N_min_kN']:+.3f} kN ({worst_s['combination']}); "
                f"ULS N={worst_u['N_min_kN']:+.3f} kN ({worst_u['combination']})."
            )
    uplift = uplift_locations(supports)
    if uplift:
        govern = max(uplift, key=lambda r: r["Fz_kN"])
        print(
            f"  WARNING: uplift {govern['Fz_kN']:.3f} kN at {govern['member']} "
            f"({govern['combination']}, x={govern['x_m']:.3f} m); gravity contact alone cannot carry it."
        )
    for category in ("rafter", "purlin", *(("saddle",) if contacts else ())):
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
            wall_rows = [r for r in service if r["wall_chord_reference"]]
            if wall_rows:
                wall = max(wall_rows, key=lambda r: r["wall_chord_max_departure_mm"])
                print(
                    f"      ADDITIONAL wall-to-wall: L={wall['wall_chord_span_m']:.3f} m; "
                    f"departure={wall['wall_chord_max_departure_mm']:.3f} mm "
                    f"({wall['combination']}, on {wall['wall_chord_max_member']}, "
                    f"s={wall['wall_chord_max_at_s_m']:.3f} m from left wall); "
                    f"L/300={wall['wall_chord_L300_limit_mm']:.3f} mm {wall['wall_chord_L300_status']}; "
                    f"L/500={wall['wall_chord_L500_limit_mm']:.3f} mm {wall['wall_chord_L500_status']}"
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


def dormer_horizontal_stiffness_argument(value):
    """Dormer override, or explicit inheritance of the general connection setting."""
    if value.lower() == "inherit":
        return "inherit"
    return horizontal_stiffness_argument(value)


def format_horizontal_stiffness(value):
    return "rigid" if value is None else f"{value:g} kN/mm"


def plan_deflection_status(rows):
    """Both local and additional wall-bay checks over ALL SLS cases, never ULS."""
    service = [r for r in rows if r["combination"].startswith("SLS_")]
    if not service or any(r["chord_L300_status"] not in {"PASS", "FAIL"} for r in service):
        return "not_assessed"
    wall_checks = [r for r in service if r.get("wall_chord_reference")]
    if any(r["wall_chord_L300_status"] not in {"PASS", "FAIL"} for r in wall_checks):
        return "not_assessed"
    if not (all(r["chord_L300_status"] == "PASS" for r in service)
            and all(r["wall_chord_L300_status"] == "PASS" for r in wall_checks)):
        return "fail"
    if (all(r["chord_L500_status"] == "PASS" for r in service)
            and all(r["wall_chord_L500_status"] == "PASS" for r in wall_checks)):
        return "L500"
    return "L300"


def wall_plate_connection_rows(roof, combo):
    """Rafter connection/bearing forces TO the rigid wall plate/ring beam.

    These are the same support reactions used by the terminal and support CSV.
    Bearing-only seats use ground-end contact reactions and cannot transfer
    horizontal forces. Movements always belong to the rafter, not the structure.
    """
    if combo not in roof.model.load_combos:
        raise ValueError(f"unknown connection-force combination: {combo}")
    rows = []
    for (rafter, plate), node_name in roof.wall_plate_connections.items():
        node = roof.model.nodes[node_name]
        reaction = support_reaction_node(roof, node_name)
        force = -np.array([getattr(reaction, "RxnF" + axis)[combo] for axis in ("X", "Y", "Z")]) / 1000
        outward_direction = -1 if "street" in plate else 1
        rows.append(
            dict(
                rafter=rafter,
                wall_plate=plate,
                seat=node_name,
                support_kind=(
                    "rafter_bearing_only"
                    if node_name in getattr(roof, "wall_plate_bearings", {})
                    else "rafter_connection"
                ),
                combination=combo,
                x_m=node.X,
                y_m=node.Y,
                z_m=node.Z,
                Dx_mm=node.DX[combo] * 1000,
                Dy_mm=node.DY[combo] * 1000,
                horizontal_movement_mm=hypot(node.DX[combo], node.DY[combo]) * 1000,
                Fx_kN=float(force[0]),
                Fy_kN=float(force[1]),
                Fz_kN=float(force[2]),
                outward_kN=float(outward_direction * force[1]),
                outward_direction=outward_direction,
            )
        )
    return rows


def print_wall_plate_connection_movements(roof):
    """Maximum XY slip of rafter seats relative to the immovable wall plate."""
    rows = [
        row
        for combo in roof.model.load_combos
        for row in wall_plate_connection_rows(roof, combo)
        if row["support_kind"] == "rafter_connection"
    ]
    if not rows:
        print("  Max horizontal rafter-to-wall-plate movement: N/A (no connections).")
        return
    service = [r for r in rows if r["combination"].startswith("SLS_")]
    for label, candidates in (("Max SLS", service), ("Max", rows)):
        if not candidates:
            continue
        moving = max(candidates, key=lambda r: r["horizontal_movement_mm"])
        print(
            f"  {label} horizontal rafter-to-wall-plate movement: "
            f"{moving['horizontal_movement_mm']:.3f} mm "
            f"({moving['rafter']} -> {moving['wall_plate']}, {moving['combination']}, "
            f"x={moving['x_m']:.3f} m; Dx={moving['Dx_mm']:+.3f}, "
            f"Dy={moving['Dy_mm']:+.3f} mm)."
        )
    print("  Horizontal movement = sqrt(Dx² + Dy²); connection slip, not ring-beam movement.")


def plan_member_polygon(beam):
    """Undeformed XY member strip, using the actual section width."""
    start, end = np.array(beam.start[:2]), np.array(beam.end[:2])
    delta = end - start
    length = positive(float(np.linalg.norm(delta)), "projected member length")
    normal = np.array((-delta[1], delta[0])) / length * beam.timber.width * beam.pieces / 2
    return np.array((start - normal, end - normal, end + normal, start + normal))


def plan_force_arrow(row, *, length=0.55):
    """Fixed-length arrow for the signed OUTWARD component, not full Fx/Fy."""
    positive(length, "force-arrow length")
    start = np.array((row["x_m"], row["y_m"]))
    sign = np.sign(row["outward_kN"])
    end = start + np.array((0.0, row["outward_direction"] * sign * length))
    return start, end


def plan_collar_force_arrows(beam, axial_kN, *, offset=0.20, length=0.55, gap=1.0):
    """Two axial arrows beside a tie, with a gap for its signed force label.

    Positive tension points away from the centre; negative compression points
    towards it. Arrow lengths are diagrammatic, not proportional to force.
    """
    for value, name in (
        (offset, "collar arrow offset"),
        (length, "arrow length"),
        (gap, "label gap"),
    ):
        positive(value, name)
    if not isfinite(axial_kN):
        raise ValueError("collar axial force must be finite")
    start, end = np.array(beam.start[:2]), np.array(beam.end[:2])
    direction = end - start
    direction /= positive(float(np.linalg.norm(direction)), "projected collar length")
    normal = np.array((direction[1], -direction[0]))
    centre = (start + end) / 2 + normal * offset
    arrows = []
    if abs(axial_kN) > 1e-9:
        for side in (-1, 1):
            near = centre + side * direction * gap / 2
            far = near + side * direction * length
            arrows.append((near, far) if axial_kN > 0 else (far, near))
    return centre, arrows


def plot_plan_report(roof, members, path, *, force_combo="ULS_symmetric"):
    """Colour-coded top-view report; no new strength/deflection criteria."""
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon

    palette = {"L500": "#39a852", "L300": "#f4a340", "fail": "#d9534f", "not_assessed": "#c8ccd0"}
    collar_colour = "#d000d0"
    spacer_colour = "#008080"
    has_collars = any(b.category == "collar" for b in roof.layout.beams)
    has_spacers = bool(roof.spacer_links)
    figure = Figure(figsize=(15, 12))
    axes = figure.add_subplot()
    figure.subplots_adjust(left=0.065, right=0.98, bottom=0.19, top=0.90)
    classifications = {}
    # Draw all physical timbers. Offset arms are numerical joints, not timber.
    order = {"collar": 0, "wall_plate": 1, "purlin": 2, "rafter": 3, "saddle": 4, "spacer": 5}
    for beam in sorted(roof.layout.beams, key=lambda b: order[b.category]):
        rows = [r for r in members if r["member"] == beam.name]
        status = classifications[beam.name] = plan_deflection_status(rows)
        is_collar = beam.category == "collar"
        is_saddle = beam.category == "saddle"
        is_spacer = beam.category == "spacer"
        axial_colour = spacer_colour if is_spacer else collar_colour
        outline = is_collar or is_saddle or is_spacer
        artist = Polygon(
            plan_member_polygon(beam),
            closed=True,
            # Outline-only overlay preserves the rafter deflection colour
            # underneath these coincident equivalent axial links.
            facecolor="none" if outline else palette[status],
            edgecolor=(
                axial_colour if is_collar or is_spacer else "#1678d2" if is_saddle else "#333333"
            ),
            linewidth=1.5 if outline else 0.6,
            alpha=1.0 if outline else 0.88,
            zorder=6 if is_collar else order[beam.category] + 2,
        )
        artist.set_gid(beam.name)
        axes.add_patch(artist)
        # Compact IDs keep nearby main/dormer rafters distinguishable.
        if beam.category == "rafter":
            _, number, side = beam.name.split("_")
            label = f"R{number}{side[0]}"
            # Stagger labels of touching main/dormer pairs along their axes.
            fraction = 0.65 if side == "dormer" else 0.5
            centre = np.array(beam.start[:2]) * (1 - fraction) + np.array(beam.end[:2]) * fraction
            axes.text(
                *centre,
                label,
                fontsize=6.5,
                rotation=90,
                ha="center",
                va="center",
                zorder=10,
                bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=0.5),
            )
        elif beam.category in {"collar", "spacer"}:
            centre = (np.array(beam.start[:2]) + np.array(beam.end[:2])) / 2
            if has_collars and has_spacers:
                centre[1] += -0.18 if is_spacer else 0.18
            axes.text(
                *centre,
                beam.name.replace("collar_", "C").replace("spacer_", "P"),
                fontsize=6,
                ha="center",
                va="center",
                rotation=90,
                color=axial_colour,
                zorder=10,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=0.5),
            )
            selected = [r for r in rows if r["combination"] == force_combo]
            if len(selected) != 1:
                raise ValueError(f"missing or duplicate axial force for {beam.name}: {force_combo}")
            axial = float(selected[0]["N_min_kN"])
            label_position, arrows = plan_collar_force_arrows(beam, axial)
            if is_spacer and has_collars:
                # Keep coincident projected tie/spacer forces on opposite sides.
                midpoint = (np.array(beam.start[:2]) + np.array(beam.end[:2])) / 2
                shift = 2 * (midpoint - label_position)
                label_position += shift
                arrows = [(tail + shift, head + shift) for tail, head in arrows]
            for number, (tail, head) in enumerate(arrows, 1):
                arrow = axes.annotate(
                    "",
                    xy=head,
                    xytext=tail,
                    arrowprops=dict(arrowstyle="-|>", color=axial_colour, lw=1.2),
                    zorder=12,
                )
                arrow.set_gid(f"{beam.name}_axial_arrow_{number}")
            angle = degrees(atan2(beam.end[1] - beam.start[1], beam.end[0] - beam.start[0]))
            label = axes.text(
                *label_position,
                f"{axial:+.2f} kN",
                color=axial_colour,
                fontsize=7,
                rotation=angle,
                ha="center",
                va="center",
                zorder=13,
                bbox=dict(facecolor="white", alpha=0.95, edgecolor="none", pad=1.0),
            )
            label.set_gid(f"{beam.name}_axial_force")
        else:
            label = beam.name.replace("_", " ")
            x = (beam.start[0] + beam.end[0]) / 2
            axes.text(
                x,
                beam.start[1] + beam.timber.width / 2 + 0.10,
                label,
                fontsize=7,
                ha="center",
                va="bottom",
                zorder=10,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=0.5),
            )

    for bolt in roof.saddle_bolts:
        (marker,) = axes.plot(
            bolt["x_m"],
            bolt["y_m"],
            marker="o",
            markersize=3.2,
            color="#123a68",
            linestyle="none",
            zorder=11,
        )
        marker.set_gid(bolt["bolt"])

    for joint in roof.gerber_connections:
        (marker,) = axes.plot(joint["x_m"], joint["y_m"], marker="D", markersize=6,
                             markerfacecolor="white", markeredgecolor="#1565c0",
                             linestyle="none", zorder=15)
        marker.set_gid(joint["joint"])

    forces = wall_plate_connection_rows(roof, force_combo)
    for row in forces:
        start, end = plan_force_arrow(row)
        axes.plot(*start, marker="o", markersize=2.5, color="#182d55", zorder=12)
        if abs(row["outward_kN"]) > 1e-9:
            arrow = axes.annotate(
                "",
                xy=end,
                xytext=start,
                arrowprops=dict(arrowstyle="-|>", color="#182d55", lw=1.0),
                zorder=12,
            )
            arrow.set_gid(row["seat"])
        direction = row["outward_direction"] * (1 if row["outward_kN"] >= 0 else -1)
        axes.text(
            end[0],
            end[1] + direction * 0.07,
            f"{row['outward_kN']:+.2f}",
            fontsize=7,
            ha="center",
            va="bottom" if direction > 0 else "top",
            color="#182d55",
            zorder=13,
            bbox=dict(facecolor="white", alpha=0.95, edgecolor="none", pad=1.0),
        )

    supported = np.array([(roof.model.nodes[n].X, roof.model.nodes[n].Y) for n in roof.supports])
    axes.scatter(*supported.T, facecolor="white", edgecolor="#333333", s=14, lw=0.5, zorder=11)
    supports = support_rows(roof)
    uplift = uplift_locations(supports)
    lift_off = lift_off_locations(supports)
    marked = [("uplift", r) for r in uplift] + [("lift_off", r) for r in lift_off]
    for kind, row in marked:
        marker = axes.scatter(
            row["x_m"],
            row["y_m"],
            marker="o",
            s=230,
            facecolors="none",
            edgecolors="#e00000",
            linewidths=1.8,
            zorder=20,
        )
        marker.set_gid(kind + "_" + row["support"])
        label = (
            f"lift-off {row['Dz_mm']:.3f} mm"
            if kind == "lift_off" else f"uplift {row['Fz_kN']:.3f} kN"
        )
        axes.annotate(
            label + "\n" + row["combination"],
            xy=(row["x_m"], row["y_m"]),
            xytext=(13, -20),
            textcoords="offset points",
            color="#e00000",
            fontsize=7,
            ha="left",
            va="top",
            zorder=21,
            bbox=dict(facecolor="white", alpha=0.9, edgecolor="none", pad=1),
        )
    vertices = np.concatenate([plan_member_polygon(b) for b in roof.layout.beams])
    axes.set_xlim(vertices[:, 0].min() - 0.6, vertices[:, 0].max() + 0.6)
    axes.set_ylim(vertices[:, 1].min() - 1.0, vertices[:, 1].max() + 1.0)
    axes.set_aspect("equal")
    axes.set(xlabel="X along house [m]", ylabel="Y: street (bottom) to garden (top) [m]")
    axes.grid(alpha=0.15, lw=0.5)
    figure.suptitle(
        "Roof deflection report — top view (undeformed XY projection)", fontsize=15, y=0.975
    )
    grades = "/".join(sorted({b.timber.material for b in roof.layout.beams}))
    restraint = (
        "wall-plate connection k: "
        f"other {format_horizontal_stiffness(roof.settings.horizontal_stiffness_kn_mm)}, "
        f"dormer {format_horizontal_stiffness(roof.settings.wall_plate_stiffness('dormer_wall_plate'))}"
    )
    subtitle = (
        f"Purlins: {roof.layout.purlin_system} | timber {grades} | roof layers {roof.settings.roof_mass:g} kg/m² | "
        f"roof snow {roof.settings.snow_load:g} kN/m² | {restraint}"
    )
    if roof.settings.middle_snow:
        lo, hi = roof.layout.middle_snow_bounds
        subtitle += f"\nIncludes middle-only snow at x={lo:.3f}..{hi:.3f} m; other snow cases retained"
    if roof.saddle_bolts:
        parameters = roof.layout.saddle_parameters.bolts
        subtitle += (
            f"\nTrial bolts: {parameters.count_per_end}/end × {parameters.diameter_mm:g} mm; "
            f"slip gap {parameters.slip_gap_mm:g} mm; hold-down {parameters.hold_down} "
            "(capacity not checked)"
        )
    figure.text(0.5, 0.945, subtitle, ha="center", va="top", fontsize=9)
    descriptions = {
        "L500": "Green: all SLS cases < L/500",
        "L300": "Orange: all SLS cases < L/300, but not L/500",
        "fail": "Red: at least one SLS case ≥ L/300",
        "not_assessed": "Grey: rigid wall plate/ring beam / missing chord",
    }
    handles = [
        Patch(facecolor=palette[key], edgecolor="#333333", label=descriptions[key])
        for key in palette
    ]
    if roof.gerber_connections:
        handles.append(Line2D([], [], marker="D", markerfacecolor="white",
                              markeredgecolor="#1565c0", linestyle="none",
                              label="Blue diamonds: Gerber hinges (not wall supports)"))
    if has_spacers:
        handles.append(
            Patch(
                facecolor="none",
                edgecolor=spacer_colour,
                label="Teal: compression-only spacers (unassessed); − compression",
            )
        )
    if has_collars:
        handles.append(
            Patch(
                facecolor="none",
                edgecolor=collar_colour,
                label="Magenta: axial ties (unassessed); + tension / − compression",
            )
        )
    if roof.layout.saddle_parameters:
        handles.append(
            Patch(
                facecolor="none",
                edgecolor="#1678d2",
                label=(
                    "Blue: sedla; dots: trial bolts (strength not assessed)"
                    if roof.saddle_bolts
                    else "Blue outline: sedla (strength not assessed)"
                ),
            )
        )
    if marked:
        handles.append(
            Line2D(
                [], [], marker="o", markersize=9, markerfacecolor="none",
                markeredgecolor="#e00000", markeredgewidth=1.8, linestyle="none",
                label="Red circles: uplift force / bearing lift-off (any load case)",
            )
        )
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.087 if has_collars and has_spacers else 0.095),
        ncol=2,
        fontsize=9,
        frameon=False,
    )
    counts = {key: sum(s == key for s in classifications.values()) for key in palette}
    figure.text(
        0.5,
        0.080,
        "Members: " + "; ".join(f"{key}={count}" for key, count in counts.items()),
        ha="center",
        fontsize=9,
    )
    figure.text(
        0.5,
        0.055,
        f"Arrows: force TO rigid wall plate/ring beam, Hout [kN], {force_combo}. "
        "+ outward / − inward; fixed-length arrows show direction only.\n"
        "Direct connection reactions; identical to the terminal/support CSV for the same load combination.",
        ha="center",
        fontsize=8,
    )
    figure.text(
        0.5,
        0.022,
        "Colours screen immediate 3D chord departure; Gerber middle pieces must also pass the full wall-to-wall bay check. "
        "No creep/strength/stability/anchor checks; NOT a complete safety assessment.\n"
        "R01s / R01g / R01d = rafter_01_street / garden / dormer. White circles = wall bearings. Overlaps are diagrammatic.",
        ha="center",
        fontsize=8,
    )
    figure.savefig(path, dpi=200)
    return figure


def plot_model(roof, path, *, combo="SLS_symmetric", scale=20.0):
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 8), layout="constrained")
    axes = figure.add_subplot(projection="3d")
    colors = {
        "rafter": "#d9a51a",
        "purlin": "#d44936",
        "wall_plate": "#2789b0",
        "collar": "#8d5aa9",
        "saddle": "#1678d2",
        "spacer": "#008080",
    }
    labelled = set()
    for beam in roof.layout.beams:
        if beam.category == "wall_plate":
            label = "rigid wall plate/ring beam" if "wall_plate" not in labelled else None
            axes.plot(
                *np.array((beam.start, beam.end)).T, color=colors[beam.category], lw=2, label=label
            )
            labelled.add(beam.category)
            continue
        member = (
            roof.model.springs[beam.name]
            if beam.category in {"collar", "spacer"}
            else roof.model.members[beam.name]
        )
        points = np.linspace(0, member.L(), 31)
        start, end = np.array(beam.start), np.array(beam.end)
        original = np.array([start + (end - start) * x / member.L() for x in points])
        transform = member.T()[:3, :3]
        if beam.category in {"collar", "spacer"}:
            first = np.array([getattr(member.i_node, axis)[combo] for axis in ("DX", "DY", "DZ")])
            last = np.array([getattr(member.j_node, axis)[combo] for axis in ("DX", "DY", "DZ")])
            disp = np.array([first + (last - first) * x / member.L() for x in points])
        else:
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
    if roof.gerber_connections:
        hinges = np.array([(roof.model.nodes[j["node"]].X,
                            roof.model.nodes[j["node"]].Y,
                            roof.model.nodes[j["node"]].Z) for j in roof.gerber_connections])
        axes.scatter(*hinges.T, marker="D", facecolors="white", edgecolors="#1565c0",
                     s=35, depthshade=False, label="Gerber hinges (not ground supports)")
    supports = support_rows(roof)
    marked = [("uplift", r) for r in uplift_locations(supports)] + [
        ("lift_off", r) for r in lift_off_locations(supports)
    ]
    for index, (kind, row) in enumerate(marked):
        marker = axes.scatter(
            row["x_m"],
            row["y_m"],
            row["z_m"],
            marker="o",
            s=160,
            facecolors="none",
            edgecolors="#e00000",
            linewidths=1.8,
            depthshade=False,
            label="uplift / bearing lift-off (any load case)" if index == 0 else None,
        )
        marker.set_gid(kind + "_" + row["support"])
        label = (
            f"lift-off {row['Dz_mm']:.3f} mm"
            if kind == "lift_off" else f"uplift {row['Fz_kN']:.3f} kN"
        )
        axes.text(
            row["x_m"], row["y_m"], row["z_m"],
            f"  {label}\n  {row['combination']}",
            color="#e00000", fontsize=7, zorder=21,
        )
    axes.set(
        xlabel="X [m]",
        ylabel="Y [m]",
        zlabel="Z [m]",
        title=f"{combo}: deformation ×{scale:g}; {roof.layout.purlin_system} purlins; "
        + ("axial kleštiny" if roof.layout.collar_parameters else "no kleštiny"),
    )
    axes.set_box_aspect((12, 9, 3))
    axes.view_init(elev=25, azim=-60)
    axes.legend(loc="upper left")
    figure.savefig(path, dpi=160)
    return figure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house", type=Path, default=Path(__file__).with_name("house_ifc.py"))
    parser.add_argument("--output", type=Path, default=Path("roof_frame_3d"))
    parser.add_argument(
        "--purlin-system", choices=("gerber", "saddles", "simple"),
        help="gerber (default): IFC joint locations, wall bearings follow each piece; saddles/simple: legacy joints over wall centres",
    )
    parser.add_argument(
        "--purlin-lateral",
        choices=("free", "restrained", "both"),
        default="restrained",
        help="purlin Y guides at actual wall bearings: restrained (default) or free; legacy saddle bolts can also transfer Y load",
    )
    purlin_bearing_options = parser.add_mutually_exclusive_group()
    purlin_bearing_options.add_argument(
        "--allow-purlin-lift-off", dest="purlin_bearing_uplift", action="store_true",
        help="comparison only: compression-only purlin wall bearings, allowing upward lift-off",
    )
    purlin_bearing_options.add_argument(
        "--fixed-purlin-bearings", dest="purlin_bearing_uplift", action="store_false",
        help="bilateral vertical attachment (default): prevent purlin lift-off and report upward force",
    )
    parser.set_defaults(purlin_bearing_uplift=Settings().purlin_bearing_uplift)
    parser.add_argument(
        "--horizontal-stiffness",
        type=horizontal_stiffness_argument,
        default=HORIZONTAL_SUPPORT_STIFFNESS_KN_MM,
        help="kN/mm per wall-plate/rafter X/Y connection DOF only; purlin horizontal guides rigid; use 'rigid' for comparison",
    )
    parser.add_argument(
        "--dormer-horizontal-stiffness",
        type=dormer_horizontal_stiffness_argument,
        default=DORMER_HORIZONTAL_SUPPORT_STIFFNESS_KN_MM,
        help="override dormer rafter-to-wall-plate X/Y stiffness only: positive kN/mm, 'rigid', or 'inherit' to use the general value",
    )
    parser.add_argument(
        "--snow",
        type=float,
        help="kN/m² horizontal roof area, NOT ground sk; default from rafter_load.py",
    )
    parser.add_argument(
        "--middle-snow", action="store_true", default=Settings().middle_snow,
        help="add SLS_middle/ULS_middle: snow between inner-wall centres only, both slopes; keep other cases and permanent load everywhere",
    )
    parser.add_argument(
        "--roof-mass",
        type=float,
        default=Settings().roof_mass,
        help="kg/m² actual roof slope, EXCLUDING suspended ceiling; default 135",
    )
    parser.add_argument("--rafter-material", choices=("C18", "C22", "C24"), default="C18")
    parser.add_argument("--beam-material", choices=("C18", "C22", "C24"), default="C24")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument(
        "--no-spacers",
        action="store_true",
        help="omit the compression-only purlin spacers for comparison",
    )
    parser.add_argument(
        "--no-saddles",
        action="store_true",
        help="legacy alias for --purlin-system simple (independent pieces supported directly on walls)",
    )
    parser.add_argument(
        "--saddle-contact-factor",
        type=float,
        default=SADDLE_CONTACT_STIFFNESS_FACTOR,
        help="sensitivity multiplier on estimated E90 bearing stiffness; not bolt stiffness",
    )
    parser.add_argument(
        "--saddle-contact-spacing",
        type=float,
        default=SADDLE_CONTACT_SPACING_M,
        help="maximum bearing contact discretisation spacing in m",
    )
    parser.add_argument(
        "--no-saddle-bolts",
        action="store_true",
        help="bearing-only saddles, without trial bolt shear/hold-down",
    )
    parser.add_argument(
        "--saddle-bolt-slip-gap",
        type=float,
        default=SADDLE_BOLT_SLIP_GAP_MM,
        help="assumed relative slip before engagement in mm (not literal hole diameter clearance)",
    )
    parser.add_argument(
        "--saddle-bolt-hold-down",
        choices=("free", "ideal"),
        default=SADDLE_BOLT_HOLD_DOWN,
        help="free omits axial clamping; ideal adds a tension-only numerical rigid-limit bound",
    )
    collar_options = parser.add_mutually_exclusive_group()
    collar_options.add_argument(
        "--collar-ties",
        dest="collar_ties",
        action="store_true",
        help="include pinned axial collar ties (default), configured by COLLAR_TIE_* parameters",
    )
    collar_options.add_argument(
        "--no-collar-ties",
        dest="collar_ties",
        action="store_false",
        help="omit collar ties for comparison; adds _no_collars to report filenames",
    )
    parser.set_defaults(collar_ties=True)
    parser.add_argument(
        "--plan-force-combination",
        choices=tuple(
            f"{limit}_{pattern}"
            for limit in ("SLS", "ULS")
            for pattern in ("symmetric", "street", "garden", "middle")
        ),
        default=None,
        help="single case for top-view force arrows (default ULS_middle with --middle-snow, otherwise ULS_symmetric)",
    )
    parser.add_argument(
        "--rafter-chord-fallback",
        choices=("na", "supports"),
        default="supports",
        help="missing wall-plate/ridge pair: explicitly labelled actual support pair (default), or N/A",
    )
    args = parser.parse_args(argv)
    if (
        args.plan_force_combination and args.plan_force_combination.endswith("_middle")
        and not args.middle_snow
    ):
        parser.error("middle force combinations require --middle-snow")
    args.plan_force_combination = args.plan_force_combination or (
        "ULS_middle" if args.middle_snow else "ULS_symmetric"
    )
    if args.no_saddles and args.purlin_system not in {None, "simple"}:
        parser.error("--no-saddles cannot be combined with Gerber or saddle systems")
    purlin_system = "simple" if args.no_saddles else (args.purlin_system or "gerber")
    #    from rafter_load import SNOW_LOAD_KN_M2
    #
    #    if args.snow is None:
    #        args.snow = SNOW_LOAD_KN_M2
    layout = RoofLayout.from_house(
        args.house,
        rafter_material=args.rafter_material,
        beam_material=args.beam_material,
        collar_ties=CollarTieParameters() if args.collar_ties else None,
        purlin_system=purlin_system,
    )
    if not args.no_spacers:
        layout = add_purlin_spacers(layout)
    if purlin_system == "saddles":
        layout = add_purlin_saddles(
            layout,
            SaddleParameters(
                length=layout.saddle_length_m,
                contact_spacing=args.saddle_contact_spacing,
                contact_stiffness_factor=args.saddle_contact_factor,
                bolts=(
                    None
                    if args.no_saddle_bolts
                    else SaddleBoltParameters(
                        slip_gap_mm=args.saddle_bolt_slip_gap,
                        hold_down=args.saddle_bolt_hold_down,
                    )
                ),
            ),
        )
    variants = (
        (False, True) if args.purlin_lateral == "both" else (args.purlin_lateral == "restrained",)
    )
    for restrained in variants:
        roof = build_roof_model(
            layout,
            Settings(
                #                roof_mass=args.roof_mass,
                #                snow_load=args.snow,
                purlin_lateral_restraint=restrained,
                purlin_bearing_uplift=args.purlin_bearing_uplift,
                middle_snow=args.middle_snow,
                horizontal_stiffness_kn_mm=args.horizontal_stiffness,
                dormer_horizontal_stiffness_kn_mm=args.dormer_horizontal_stiffness,
            ),
        )
        residuals = solve_roof_model(roof)
        members = member_rows(roof, chord_fallback=args.rafter_chord_fallback)
        supports = support_rows(roof)
        print_summary(roof, members, supports, residuals)
        prefix = (
            str(args.output)
            + ("_middle_snow" if args.middle_snow else "")
            + ("_no_collars" if not args.collar_ties else "")
            + ("_no_spacers" if args.no_spacers else "")
            + ("_restrained" if restrained else "_free")
        )
        write_csv(prefix + "_members.csv", members)
        write_csv(prefix + "_supports.csv", supports)
        if roof.spacer_links:
            write_csv(prefix + "_spacers.csv", spacer_rows(roof))
        if roof.saddle_contacts:
            write_csv(prefix + "_saddle_contacts.csv", saddle_contact_rows(roof))
        if roof.saddle_bolts:
            write_csv(prefix + "_saddle_bolts.csv", saddle_bolt_rows(roof))
        if roof.gerber_connections:
            write_csv(prefix + "_gerber_joints.csv", gerber_joint_rows(roof))
        metadata = dict(
            source=str(layout.source),
            versions={
                "PyniteFEA": version("PyniteFEA"),
                "numpy": np.__version__,
                "matplotlib": version("matplotlib"),
            },
            settings=roof.settings.__dict__,
            wall_plate_connection_stiffness_kn_mm={
                beam.name: roof.settings.wall_plate_stiffness(beam.name)
                for beam in layout.beams
                if beam.category == "wall_plate"
            },
            timber_materials={
                category: sorted(
                    {b.timber.material for b in roof.layout.beams if b.category == category}
                )
                for category in timber_categories(layout)
            },
            analysis=(
                "first-order elastic with compression-only saddle contact"
                + (" and trial bolt face-slip" if roof.saddle_bolts else "")
                if roof.saddle_contacts
                else "first-order elastic"
            )
            + (" with Gerber bending hinges" if roof.gerber_connections else "")
            + (" with compression-only purlin spacers" if roof.spacer_links else "")
            + (" with compression-only intermediate wall-plate seats" if roof.wall_plate_bearings else "")
            + (" with compression-only purlin wall bearings" if roof.purlin_wall_bearings else ""),
            purlin_wall_bearings=dict(
                enabled=bool(roof.purlin_wall_bearings),
                count=len(roof.purlin_wall_bearings),
                stiffness_N_m=IDEAL_PURLIN_BEARING_N_M,
                model="zero-gap compression-only rigid-limit vertical contact; horizontal guides/roll restraints unchanged even when open",
                nodes=list(roof.purlin_wall_bearings),
            ),
            purlin_vertical_restraint=dict(
                model=("compression-only, lift-off allowed" if roof.settings.purlin_bearing_uplift
                       else "bilateral rigid vertical attachment, no lift-off"),
                upward_force="positive Fz_kN delivered TO wall support; equal downward hold-down required on timber",
                anchorage_capacity_checked=False,
            ),
            intermediate_wall_plate_bearings=dict(
                count=len(roof.wall_plate_bearings),
                stiffness_N_m=IDEAL_WALL_PLATE_BEARING_N_M,
                model="vertical compression-only rigid-limit contact; no friction, hold-down or rotation restraint",
                seats=[
                    dict(rafter=r, wall_plate=p, node=n)
                    for (r, p), n in roof.wall_plate_connections.items()
                    if n in roof.wall_plate_bearings
                ],
            ),
            purlin_system=purlin_system,
            gerber=dict(
                enabled=bool(roof.gerber_connections),
                count=len(roof.gerber_connections),
                joints=roof.gerber_connections,
                connection="shared translations; both bending rotations released only at the hinge-supported member ends",
                torsion="continuity retained; wall bearings restrain roll",
                supports="actual wall centres on the containing piece; no added ground restraint at hinges away from walls",
                excluded=["joint strength", "connection slip", "fastener capacity", "uplift separation at Gerber connections"],
            ),
            spacers=dict(
                enabled=bool(roof.spacer_links),
                count=len(roof.spacer_links),
                members=[
                    dict(
                        name=b.name,
                        width_m=b.timber.width,
                        height_m=b.timber.height,
                        length_m=b.length,
                        material=b.timber.material,
                        purlins=b.supported_purlins,
                    )
                    for b in layout.beams
                    if b.category == "spacer"
                ],
                stiffness="E_parallel * A / physical face-to-face timber length",
                model="compression-only axial links on purlin axes; snug fit, no tension connection",
                self_weight="shared equally between purlin endpoints; included once",
                not_modelled=[
                    "end eccentricity",
                    "end-bearing compliance",
                    "gap/preload",
                    "bending",
                ],
                not_checked=[
                    "compression strength",
                    "buckling",
                    "end bearing",
                    "fastening capacity",
                ],
            ),
            saddles=dict(
                enabled=bool(layout.saddle_parameters),
                parameters=asdict(layout.saddle_parameters) if layout.saddle_parameters else None,
                stiffness="factor * A / (h_p/E90,p + h_s/E90,s); two full-depth compression layers",
                E90_mean_Pa=TIMBER_E90_MEAN_PA,
                model="flexible longitudinal timber; central vertical pin; compression-only vertical contact",
                purlin_guides="original rigid X/roll, optional Y restraint retained; internal DZ released",
                not_modelled=[
                    "bolt capacity/spacing/group effects",
                    "friction",
                    "glued/full-composite constraint",
                    "contact gaps/preload",
                    "wall contact width/rotation",
                    "bearing creep",
                ],
                stiffness_status="elastic estimate, not calibrated to this joint",
                bolt_model=dict(
                    enabled=bool(roof.saddle_bolts),
                    count=len(roof.saddle_bolts),
                    shear="two independent face-slip springs per bolt, including rotational offsets; one shear plane",
                    Kser="rho_mean^1.5 * diameter_mm / 23 N/mm; geometric mean for dissimilar timbers",
                    mean_density_kg_m3=TIMBER_MEAN_DENSITY_KG_M3,
                    ULS_stiffness="Ku = 2/3 Kser",
                    clearance="independent symmetric X/Y slip deadbands; not an exact circular hole model",
                    positions="equally spaced within each purlin end's saddle overlap",
                    hold_down="free, or ideal tension-only bound; NOT a physical axial stiffness estimate",
                    ideal_hold_down_penalty_N_m=IDEAL_BOLT_HOLD_DOWN_N_M,
                    lateral_path="Y load can pass to rigid saddle wall support even when direct purlin Y guides are free",
                    saddle_wall_restraint="DX/DY/DZ/RX/RZ fixed, RY free; assumed, not a verified support detail",
                ),
            ),
            collar_ties=dict(
                enabled=args.collar_ties,
                parameters=asdict(layout.collar_parameters) if layout.collar_parameters else None,
                model="bilateral axial EA/L spring links on main rafter axes; pinned, no purlin support",
                self_weight="lumped equally to the two rafter connections; included once",
                omissions="touching MAIN rafter sides only; main/dormer pairs not suppressed",
                not_checked=[
                    "bending",
                    "compression buckling",
                    "joint capacity",
                    "connection slip/eccentricity",
                ],
            ),
            plan_report=dict(
                colours="existing chord checks over all SLS cases: L/500 green, L/300 orange, otherwise red; unassessed grey; axial ties magenta, saddles blue and compression-only spacers teal outline (unassessed)",
                force_combination=args.plan_force_combination,
                gerber_hinge_markers="blue diamonds at the four free Gerber joint nodes; not wall supports",
                uplift_markers="red circles at undeformed support nodes with Fz_kN > 1e-6 in any load combination; one marker per node, worst upward load",
                lift_off_markers="red circles at compression-only rafter seats and purlin/saddle wall bearings with Dz_mm > 1e-6 in any load combination; one marker per node, worst gap labelled in mm",
                arrows="direct reaction delivered TO rigid wall plate/ring beam in kN; same as support CSV",
                arrow_length="constant; direction only, not proportional to magnitude",
                collar_arrows="same selected combination; inward compression, outward tension; signed axial kN between arrows, total for grouped boards",
                gerber_middle_colours="must pass BOTH local hinge-to-hinge and additional complete wall-to-wall bay checks for each ratio in all SLS cases",
            ),
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
                reference="line through displaced support points: two walls, two hinges, or one of each",
                support_locations="actual wall centres and supporting cantilever-tip hinges according to the joint configuration",
                internal_vertical_support=(
                    "Gerber hinges moving with the carrying pieces' cantilever tips"
                    if roof.gerber_connections else "flexible compression-only saddle contact"
                    if roof.saddle_contacts
                    else "compression-only wall bearing" if roof.purlin_wall_bearings
                    else "direct rigid bearing"
                ),
                measure="maximum 3D perpendicular distance between bearings; includes lateral bending",
                length="original distance between the actual support pair; overhangs excluded",
                ratios=[300, 500],
                comparison="strict <, SLS combinations only",
                excludes_creep=True,
                not_complete_EC5_check=True,
                additional_gerber_middle_check=dict(
                    enabled=bool(roof.gerber_connections),
                    reference="line through displaced inner-wall bearing points on whichever pieces contain them",
                    scope="all portions of the three purlin pieces lying between the inner walls",
                    includes="bending and carrying-piece cantilever/hinge sag in the inner bay, including lateral displacement",
                    length="original inner-wall centre distance, not hinge spacing",
                    peak_position="station from left inner wall; peak member named separately",
                    output="wall_chord_* CSV fields; separate terminal line; both checks govern PNG colour",
                    ratios=[300, 500], comparison="strict <, SLS only; immediate, no creep",
                ),
            ),
            equilibrium_relative_residual=residuals,
            combinations={name: combo.factors for name, combo in roof.model.load_combos.items()},
            middle_snow=dict(
                enabled=roof.settings.middle_snow,
                bounds_x_m=layout.middle_snow_bounds,
                boundary="inner-wall centres, not Gerber hinges",
                scope="both roof sides including dormer; snow zero outside strip in SLS_middle/ULS_middle only",
                permanent_load="unchanged everywhere; usual snow cases retained",
                purpose="artificial sensitivity case, not a code-prescribed snow distribution",
            ),
            omitted=[
                *([] if args.collar_ties else ["kleštiny"]),
                *(["purlin spacers"] if args.no_spacers else []),
                "suspended ceiling",
                "wind",
                "snow drift",
                "EC5 strength/stability checks",
                "concrete/anchors",
            ],
            assumptions=[
                "horizontal X/Y stiffness at rafter-to-wall-plate/ring-beam connections ONLY; separate dormer override; None means rigid; sensitivity, not verified stiffness",
                "one immovable rigid wall plate/ring beam; no elastic wall-plate member or wall-plate offset arms",
                "connected eave wall-plate seats have bilateral vertical support; intermediate wall plates are compression-only vertical bearings, free in X/Y and rotation",
                "intermediate contact uses a numerical rigid-limit stiffness, not calibrated timber stiffness; zero initial gap",
                ("Gerber hinges share translations and release both bending moments; no added ground supports at cantilever tips"
                 if roof.gerber_connections else "purlin bearings at wall centre lines; adjacent pieces have separate end nodes"),
                "purlin bearing X translation rigid; Y rigid in restrained variant, free in free variant; vertical attachment bilateral by default, compression-only with --allow-purlin-lift-off",
                "purlin wall contact stiffness is a numerical rigid-limit penalty, not calibrated timber compression; opened bearings retain horizontal/roll restraints",
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
            plot_model(roof, prefix + "_model.png", combo=(
                "SLS_middle" if args.middle_snow else "SLS_symmetric"
            ))
            plot_plan_report(
                roof, members, prefix + "_plan.png", force_combo=args.plan_force_combination
            )
        print(
            f"  Output: {prefix}_members.csv, _supports.csv, _basis.json"
            + (", _saddle_contacts.csv" if roof.saddle_contacts else "")
            + (", _saddle_bolts.csv" if roof.saddle_bolts else "")
            + (", _gerber_joints.csv" if roof.gerber_connections else "")
            + (", _spacers.csv" if roof.spacer_links else "")
            + (", _model.png, _plan.png" if not args.no_plot else "")
        )


if __name__ == "__main__":
    main()
