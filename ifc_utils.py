"""Minimal helpers for describing a house as an IFC model.

The public API uses metres and a conventional right-handed coordinate system:
X and Y lie in the floor plane and Z points upwards.  A wall's axis follows the
line between its two supplied points, and its construction is positioned
relative to that axis.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from math import atan2, cos, hypot, isfinite, radians, sin
from os import PathLike
from pathlib import Path
import re
import shutil
import subprocess
from typing import Literal, Sequence, TypeAlias

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.document
import ifcopenshell.api.drawing
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.group
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.type
import ifcopenshell.api.unit
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
from ifcopenshell.util.shape_builder import ShapeBuilder
import numpy as np


__all__ = [
    "Beam",
    "Chimney",
    "Drawing",
    "House",
    "MiakoSlab",
    "Roof",
    "RoofLayer",
    "RoofPlane",
    "Stair",
    "Storey",
    "Wall",
    "generate_plan",
]

Number: TypeAlias = int | float
Point: TypeAlias = tuple[Number, Number]
Point3D: TypeAlias = tuple[Number, Number, Number]
PlaneCut: TypeAlias = tuple[Point3D, Point3D, Point3D]
WallCut: TypeAlias = PlaneCut
Layer: TypeAlias = tuple[str, Number]
LayerItem: TypeAlias = Layer | Literal["axis"]
DoorOperation: TypeAlias = Literal[
    "SINGLE_SWING_LEFT",
    "SINGLE_SWING_RIGHT",
    "DOUBLE_SWING_RIGHT",
    "DOUBLE_SWING_LEFT",
    "DOUBLE_DOOR_SINGLE_SWING",
    "DOUBLE_DOOR_DOUBLE_SWING",
    "SLIDING_TO_LEFT",
    "SLIDING_TO_RIGHT",
    "DOUBLE_DOOR_SLIDING",
]
WindowPartition: TypeAlias = Literal[
    "SINGLE_PANEL",
    "DOUBLE_PANEL_HORIZONTAL",
    "DOUBLE_PANEL_VERTICAL",
    "TRIPLE_PANEL_BOTTOM",
    "TRIPLE_PANEL_TOP",
    "TRIPLE_PANEL_LEFT",
    "TRIPLE_PANEL_RIGHT",
    "TRIPLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_VERTICAL",
]
WindowAlignment: TypeAlias = Literal["axis", "inside"]
FurnitureKind: TypeAlias = Literal[
    "CHAIR",
    "TABLE",
    "DESK",
    "BED",
    "FILECABINET",
    "SHELF",
    "SOFA",
    "USERDEFINED",
    "NOTDEFINED",
]


_DOOR_OVERHEAD_LINE = re.compile(
    r'(?P<indent>^[ \t]*)<line\b(?P<attrs>[^>\n]*\bdoor-overhead\b[^>\n]*)/>[ \t]*$',
    re.MULTILINE,
)


def _postprocess_door_overheads(svg_path: Path) -> None:
    """Mask solid wall lines, add dashes, then repaint door symbols on top."""
    svg = svg_path.read_text(encoding="utf-8")
    changed = False

    if '<polygon class="door-overhead-mask"' not in svg:
        line_groups: dict[str, list[re.Match[str]]] = {}
        for match in _DOOR_OVERHEAD_LINE.finditer(svg):
            attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
            global_id = next(
                (
                    token
                    for token in attributes.get("class", "").split()
                    if token.startswith("GlobalId-")
                ),
                None,
            )
            if global_id is not None:
                line_groups.setdefault(global_id, []).append(match)

        insertions = []
        for lines in line_groups.values():
            if len(lines) != 2:
                continue
            first = dict(re.findall(r'([\w:-]+)="([^"]*)"', lines[0]["attrs"]))
            second = dict(re.findall(r'([\w:-]+)="([^"]*)"', lines[1]["attrs"]))
            coordinate_names = ("x1", "y1", "x2", "y2")
            if any(
                name not in first or name not in second
                for name in coordinate_names
            ):
                continue
            points = " ".join(
                (
                    f'{first["x1"]},{first["y1"]}',
                    f'{first["x2"]},{first["y2"]}',
                    f'{second["x2"]},{second["y2"]}',
                    f'{second["x1"]},{second["y1"]}',
                )
            )
            polygon = (
                f'{lines[0]["indent"]}<polygon class="door-overhead-mask" '
                f'points="{points}"/>\n'
            )
            insertions.append((lines[0].start(), polygon))

        for offset, polygon in reversed(insertions):
            svg = f"{svg[:offset]}{polygon}{svg[offset:]}"
        changed = bool(insertions)

    if '<g class="door-symbol-overlays">' not in svg:
        door_ids = []
        for match in re.finditer(r'<g\b(?P<attrs>[^>\n]*)>', svg):
            attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', match["attrs"]))
            classes = set(attributes.get("class", "").split())
            element_id = attributes.get("id")
            if element_id and {"IfcDoor", "projection"} <= classes:
                door_ids.append(element_id)
        closing_svg = svg.rfind("</svg>")
        if door_ids and closing_svg >= 0:
            uses = "\n".join(
                f'    <use href="#{element_id}" xlink:href="#{element_id}"/>'
                for element_id in door_ids
            )
            overlays = (
                '  <g class="door-symbol-overlays">\n'
                f"{uses}\n"
                "  </g>\n"
            )
            svg = f"{svg[:closing_svg]}{overlays}{svg[closing_svg:]}"
            changed = True

    if changed:
        svg_path.write_text(svg, encoding="utf-8")


BeamKind: TypeAlias = Literal[
    "BEAM",
    "JOIST",
    "HOLLOWCORE",
    "LINTEL",
    "SPANDREL",
    "T_BEAM",
    "RAFTER",
    "PURLIN",
    "USERDEFINED",
    "NOTDEFINED",
]
MiakoStructureItem: TypeAlias = Literal["beam", "wide", "narrow"]

_COLOR_NAMES = {
    "black": "#000000",
    "blue": "#0000FF",
    "brown": "#A52A2A",
    "gray": "#808080",
    "grey": "#808080",
    "green": "#008000",
    "orange": "#FFA500",
    "red": "#FF0000",
    "white": "#FFFFFF",
    "yellow": "#FFFF00",
}

_DOOR_OPERATIONS = {
    "SINGLE_SWING_LEFT",
    "SINGLE_SWING_RIGHT",
    "DOUBLE_SWING_RIGHT",
    "DOUBLE_SWING_LEFT",
    "DOUBLE_DOOR_SINGLE_SWING",
    "DOUBLE_DOOR_DOUBLE_SWING",
    "SLIDING_TO_LEFT",
    "SLIDING_TO_RIGHT",
    "DOUBLE_DOOR_SLIDING",
}
_WINDOW_PARTITIONS = {
    "SINGLE_PANEL",
    "DOUBLE_PANEL_HORIZONTAL",
    "DOUBLE_PANEL_VERTICAL",
    "TRIPLE_PANEL_BOTTOM",
    "TRIPLE_PANEL_TOP",
    "TRIPLE_PANEL_LEFT",
    "TRIPLE_PANEL_RIGHT",
    "TRIPLE_PANEL_HORIZONTAL",
    "TRIPLE_PANEL_VERTICAL",
}
_WINDOW_ALIGNMENTS = {"AXIS", "INSIDE"}
_FURNITURE_KINDS = {
    "CHAIR",
    "TABLE",
    "DESK",
    "BED",
    "FILECABINET",
    "SHELF",
    "SOFA",
    "USERDEFINED",
    "NOTDEFINED",
}
_BEAM_KINDS = {
    "BEAM",
    "JOIST",
    "HOLLOWCORE",
    "LINTEL",
    "SPANDREL",
    "T_BEAM",
    "RAFTER",
    "PURLIN",
    "USERDEFINED",
    "NOTDEFINED",
}
_MIAKO_WIDTHS = {
    "beam": 0.17,
    "wide": 0.455,
    "narrow": 0.33,
}


def _name(value: str, argument: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{argument} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{argument} must not be empty")
    return value


def _number(value: Number, argument: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{argument} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{argument} must be a number") from error
    if not isfinite(result):
        raise ValueError(f"{argument} must be finite")
    return result


def _point(value: Point, argument: str) -> tuple[float, float]:
    try:
        x, y = value
    except (TypeError, ValueError) as error:
        raise TypeError(f"{argument} must contain exactly two coordinates") from error
    return _number(x, f"{argument} x"), _number(y, f"{argument} y")


def _point_3d(value: Point3D, argument: str) -> tuple[float, float, float]:
    try:
        x, y, z = value
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{argument} must contain exactly three coordinates"
        ) from error
    return (
        _number(x, f"{argument} x"),
        _number(y, f"{argument} y"),
        _number(z, f"{argument} z"),
    )


def _plane_cuts(
    value: Sequence[PlaneCut] | None,
    argument: str = "cuts",
) -> tuple[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
    ...,
]:
    """Validate global three-point clipping planes without choosing a side."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{argument} must be a sequence of three-point planes")
    try:
        supplied_cuts = list(value)
    except TypeError as error:
        raise TypeError(
            f"{argument} must be a sequence of three-point planes"
        ) from error

    result = []
    for cut_index, supplied_cut in enumerate(supplied_cuts, start=1):
        if isinstance(supplied_cut, (str, bytes)):
            raise TypeError(f"cut {cut_index} must contain exactly three points")
        try:
            supplied_points = list(supplied_cut)
        except TypeError as error:
            raise TypeError(
                f"cut {cut_index} must contain exactly three points"
            ) from error
        if len(supplied_points) != 3:
            raise TypeError(f"cut {cut_index} must contain exactly three points")
        points = tuple(
            _point_3d(point, f"cut {cut_index} point {point_index}")
            for point_index, point in enumerate(supplied_points, start=1)
        )
        normal = np.cross(
            np.array(points[1], dtype=float) - np.array(points[0], dtype=float),
            np.array(points[2], dtype=float) - np.array(points[0], dtype=float),
        )
        if float(np.linalg.norm(normal)) <= 1e-9:
            raise ValueError(f"cut {cut_index} points must not be collinear")
        result.append(points)
    return tuple(result)


def _local_clippings(
    cuts: Sequence[PlaneCut],
    placement: np.ndarray,
    retained_point: Sequence[Number],
) -> list[dict[str, tuple[float, float, float]]]:
    """Convert global planes to a product frame, retaining its centre side."""
    world_to_local = np.linalg.inv(placement)
    retained_point_vector = np.array(retained_point, dtype=float)
    result = []
    for cut_index, cut in enumerate(cuts, start=1):
        local_points = [
            (world_to_local @ np.array((*point, 1.0), dtype=float))[:3]
            for point in cut
        ]
        normal = np.cross(
            local_points[1] - local_points[0],
            local_points[2] - local_points[0],
        )
        normal /= np.linalg.norm(normal)
        centre_side = float(
            np.dot(normal, retained_point_vector - local_points[0])
        )
        if abs(centre_side) <= 1e-9:
            raise ValueError(
                f"cut {cut_index} passes through the element centre; "
                "the retained side is ambiguous"
            )
        if centre_side > 0:
            normal *= -1
        result.append(
            {
                "location": tuple(float(value) for value in local_points[0]),
                "normal": tuple(float(value) for value in normal),
            }
        )
    return result


def _clip_body_representation(
    model: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    body: ifcopenshell.entity_instance,
    clippings: Sequence[dict[str, tuple[float, float, float]]],
) -> None:
    """Apply ordered half-space cuts and persist their boolean identifiers."""
    if not clippings:
        return
    item = body.Items[0]
    clipping_ids = []
    for clipping in clippings:
        item = ifcopenshell.api.geometry.clip_solid(
            model,
            item=item,
            location=clipping["location"],
            normal=clipping["normal"],
        )
        clipping_ids.append(item.id())
    body.Items = [item]
    body.RepresentationType = "Clipping"
    boolean_pset = ifcopenshell.api.pset.add_pset(
        model,
        product=element,
        name="BBIM_Boolean",
    )
    ifcopenshell.api.pset.edit_pset(
        model,
        pset=boolean_pset,
        properties={"Data": json.dumps(clipping_ids)},
    )


def _enum(value: str, argument: str, allowed: set[str]) -> str:
    value = _name(value, argument).upper()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{argument} must be one of: {choices}")
    return value


def _color(value: str, argument: str) -> tuple[float, float, float]:
    value = _name(value, argument)
    value = _COLOR_NAMES.get(value.lower(), value)
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError(f"{argument} must be a named color or #RGB/#RRGGBB")
    try:
        channels = tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    except ValueError as error:
        raise ValueError(
            f"{argument} must be a named color or #RGB/#RRGGBB"
        ) from error
    return channels


def _rotate_items_about_z(
    model: ifcopenshell.file,
    items: Sequence[ifcopenshell.entity_instance],
    *,
    angle: float,
    pivot: tuple[float, float],
) -> None:
    """Rigidly rotate positioned representation items in their local XY plane."""
    angle = radians(angle)
    rotation = np.eye(4)
    rotation[0, 0] = cos(angle)
    rotation[0, 1] = -sin(angle)
    rotation[1, 0] = sin(angle)
    rotation[1, 1] = cos(angle)
    to_pivot = np.eye(4)
    to_pivot[0, 3], to_pivot[1, 3] = pivot
    from_pivot = np.eye(4)
    from_pivot[0, 3], from_pivot[1, 3] = -pivot[0], -pivot[1]
    transform = to_pivot @ rotation @ from_pivot

    for item in items:
        position = getattr(item, "Position", None)
        if position is None or not position.is_a("IfcAxis2Placement3D"):
            raise TypeError(f"cannot rotate unpositioned {item.is_a()} door geometry")
        placement = transform @ ifcopenshell.util.placement.get_axis2placement(position)
        position.Location.Coordinates = tuple(float(value) for value in placement[:3, 3])
        position.Axis = model.createIfcDirection(
            tuple(float(value) for value in placement[:3, 2])
        )
        position.RefDirection = model.createIfcDirection(
            tuple(float(value) for value in placement[:3, 0])
        )


def generate_plan(
    ifc: str | PathLike[str],
    output: str | PathLike[str],
    *,
    x: Number,
    y: Number,
    z: Number,
    radius: Number,
    png: bool = False,
    blender: str | PathLike[str] = "blender",
    inkscape: str | PathLike[str] = "inkscape",
    stylesheet: str | PathLike[str] | None = None,
) -> Path:
    """Generate a square Bonsai plan from an IFC file.

    ``z`` is the horizontal cut-plane elevation.  The orthographic camera is
    centred on ``(x, y, z)`` and covers ``2 * radius`` metres in both X and Y.
    Set ``png=True`` to rasterise the resulting SVG with Inkscape as a second
    output.

    Bonsai's drawing operators currently require a live 3D viewport.  Blender
    therefore runs with its normal interface, performs the drawing unattended,
    and closes itself when finished.
    """
    ifc_path = Path(ifc).resolve()
    if not ifc_path.exists():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")
    if not ifc_path.is_file():
        raise IsADirectoryError(f"IFC input is not a file: {ifc_path}")

    output_path = Path(output)
    if output_path.suffix.lower() != ".svg":
        raise ValueError("plan output must use the .svg extension")
    x = _number(x, "x")
    y = _number(y, "y")
    z = _number(z, "z")
    radius = _number(radius, "radius")
    if radius <= 0:
        raise ValueError("radius must be greater than zero")
    if not isinstance(png, bool):
        raise TypeError("png must be a boolean")

    blender_command = shutil.which(str(blender))
    if blender_command is None:
        raise FileNotFoundError(f"Blender executable not found: {blender}")

    script_path = Path(__file__).resolve().parent / "bonsai_scripts" / "generate_plan.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Bonsai plan script not found: {script_path}")
    stylesheet_path = (
        Path(stylesheet)
        if stylesheet is not None
        else script_path.parent / "assets" / "plan.css"
    ).resolve()
    if not stylesheet_path.is_file():
        raise FileNotFoundError(f"plan stylesheet not found: {stylesheet_path}")

    absolute_output = output_path.resolve()
    absolute_output.parent.mkdir(parents=True, exist_ok=True)
    if absolute_output.exists():
        if not absolute_output.is_file():
            raise IsADirectoryError(f"plan output is not a file: {absolute_output}")
        absolute_output.unlink()

    command = [
        blender_command,
        "--python-exit-code",
        "1",
        "--python",
        str(script_path),
        "--",
        "--ifc",
        str(ifc_path),
        "--output",
        str(absolute_output),
        "--stylesheet",
        str(stylesheet_path),
        "--x",
        str(x),
        "--y",
        str(y),
        "--z",
        str(z),
        "--radius",
        str(radius),
    ]
    subprocess.run(command, check=True)

    if not absolute_output.is_file() or absolute_output.stat().st_size == 0:
        raise RuntimeError(f"Bonsai did not create the SVG plan: {absolute_output}")
    _postprocess_door_overheads(absolute_output)

    if png:
        inkscape_command = shutil.which(str(inkscape))
        if inkscape_command is None:
            raise FileNotFoundError(f"Inkscape executable not found: {inkscape}")
        png_output = absolute_output.with_suffix(".png")
        if png_output.exists():
            if not png_output.is_file():
                raise IsADirectoryError(f"PNG output is not a file: {png_output}")
            png_output.unlink()
        subprocess.run(
            [
                inkscape_command,
                str(absolute_output),
                f"--export-filename={png_output}",
                "--export-dpi=200",
                "--export-background=white",
                "--export-background-opacity=255",
            ],
            check=True,
        )
        if not png_output.is_file() or png_output.stat().st_size == 0:
            raise RuntimeError(f"Inkscape did not create the PNG plan: {png_output}")

    return output_path


def _render_existing_drawing(
    ifc: Path,
    drawing_guid: str,
    output: str | PathLike[str],
    *,
    png: bool,
    png_dpi: Number,
    blender: str | PathLike[str],
    inkscape: str | PathLike[str],
) -> Path:
    """Render a persisted Bonsai drawing from an IFC file."""
    output_path = Path(output)
    if output_path.suffix.lower() != ".svg":
        raise ValueError("drawing output must use the .svg extension")
    if not isinstance(png, bool):
        raise TypeError("png must be a boolean")
    png_dpi = _number(png_dpi, "png_dpi")
    if png_dpi <= 0:
        raise ValueError("png_dpi must be greater than zero")

    blender_command = shutil.which(str(blender))
    if blender_command is None:
        raise FileNotFoundError(f"Blender executable not found: {blender}")
    script_path = Path(__file__).resolve().parent / "bonsai_scripts" / "render_drawing.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"Bonsai drawing script not found: {script_path}")

    absolute_output = output_path.resolve()
    absolute_output.parent.mkdir(parents=True, exist_ok=True)
    if absolute_output.exists():
        if not absolute_output.is_file():
            raise IsADirectoryError(f"drawing output is not a file: {absolute_output}")
        absolute_output.unlink()

    subprocess.run(
        [
            blender_command,
            "--python-exit-code",
            "1",
            "--python",
            str(script_path),
            "--",
            "--ifc",
            str(ifc),
            "--drawing-guid",
            drawing_guid,
            "--output",
            str(absolute_output),
        ],
        check=True,
    )
    if not absolute_output.is_file() or absolute_output.stat().st_size == 0:
        raise RuntimeError(f"Bonsai did not create the SVG drawing: {absolute_output}")
    _postprocess_door_overheads(absolute_output)

    if png:
        inkscape_command = shutil.which(str(inkscape))
        if inkscape_command is None:
            raise FileNotFoundError(f"Inkscape executable not found: {inkscape}")
        png_output = absolute_output.with_suffix(".png")
        if png_output.exists():
            if not png_output.is_file():
                raise IsADirectoryError(f"PNG output is not a file: {png_output}")
            png_output.unlink()
        subprocess.run(
            [
                inkscape_command,
                str(absolute_output),
                f"--export-filename={png_output}",
                f"--export-dpi={png_dpi:g}",
                "--export-background=white",
                "--export-background-opacity=255",
            ],
            check=True,
        )
        if not png_output.is_file() or png_output.stat().st_size == 0:
            raise RuntimeError(f"Inkscape did not create the PNG drawing: {png_output}")

    return output_path


class House:
    """An IFC project containing one site and one building.

    All public coordinates and dimensions are expressed in metres.  The
    underlying IFC file also uses metres, which keeps generated values easy to
    inspect while remaining compatible with IFC viewers such as Bonsai.
    ``colors`` may define default 3D colors for ``"beam"``, ``"block"``,
    ``"chimney"``, ``"wall"``, ``"door"``, ``"furniture"`, ``"slab"``,
    ``"stair"``, and ``"window"`` elements using named colors or
    ``#RGB``/``#RRGGBB`` values.
    """

    def __init__(
        self,
        name: str,
        *,
        colors: Mapping[str, str] | None = None,
    ) -> None:
        self.name = _name(name, "name")
        if colors is None:
            colors = {}
        elif not isinstance(colors, Mapping):
            raise TypeError("colors must be a mapping")
        allowed_colors = {
            "beam",
            "block",
            "chimney",
            "wall",
            "door",
            "furniture",
            "slab",
            "stair",
            "window",
        }
        self._default_colors: dict[str, tuple[float, float, float]] = {}
        for category, color in colors.items():
            if not isinstance(category, str):
                raise TypeError("color category names must be strings")
            category = category.strip().lower()
            if category not in allowed_colors:
                choices = ", ".join(sorted(allowed_colors))
                raise ValueError(f"color category must be one of: {choices}")
            self._default_colors[category] = _color(color, f"{category} color")
        self.model = ifcopenshell.api.project.create_file(version="IFC4")

        self.project = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcProject", name=self.name
        )
        units = [
            ifcopenshell.api.unit.add_si_unit(
                self.model, unit_type="LENGTHUNIT"
            ),
            ifcopenshell.api.unit.add_si_unit(self.model, unit_type="AREAUNIT"),
            ifcopenshell.api.unit.add_si_unit(self.model, unit_type="VOLUMEUNIT"),
        ]
        ifcopenshell.api.unit.assign_unit(self.model, units=units)

        model_context = ifcopenshell.api.context.add_context(
            self.model, context_type="Model"
        )
        self._body_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_context,
        )
        plan_context = ifcopenshell.api.context.add_context(
            self.model, context_type="Plan"
        )
        self._axis_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=plan_context,
        )
        self._plan_body_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Body",
            target_view="PLAN_VIEW",
            parent=plan_context,
        )
        self._annotation_context = ifcopenshell.api.context.add_context(
            self.model,
            context_type="Plan",
            context_identifier="Annotation",
            target_view="PLAN_VIEW",
            parent=plan_context,
        )

        self.site = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcSite", name="Site"
        )
        self.building = ifcopenshell.api.root.create_entity(
            self.model, ifc_class="IfcBuilding", name=self.name
        )
        ifcopenshell.api.aggregate.assign_object(
            self.model, products=[self.site], relating_object=self.project
        )
        ifcopenshell.api.aggregate.assign_object(
            self.model, products=[self.building], relating_object=self.site
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.model, product=self.site
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.model, product=self.building
        )

        self._storeys: list[Storey] = []
        self._drawings: list[Drawing] = []
        self._plan_annotations: list[ifcopenshell.entity_instance] = []
        self._materials: dict[str, ifcopenshell.entity_instance] = {}
        self._wall_type_layouts: dict[int, tuple[float, float]] = {}
        self._wall_type_styles: dict[int, ifcopenshell.entity_instance | None] = {}
        self._surface_styles: dict[
            tuple[tuple[float, float, float], float],
            ifcopenshell.entity_instance,
        ] = {}
        self._miako_component_types: dict[
            tuple[object, ...], ifcopenshell.entity_instance
        ] = {}
        self._ifc_path: Path | None = None

    def _surface_style(
        self,
        category: Literal[
            "beam",
            "block",
            "chimney",
            "wall",
            "door",
            "furniture",
            "slab",
            "stair",
            "window",
        ],
        *,
        color: str | None,
        transparency: Number,
    ) -> ifcopenshell.entity_instance | None:
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")
        rgb = self._default_colors.get(category) if color is None else _color(
            color, "color"
        )
        if rgb is None:
            return None
        key = (rgb, transparency)
        style = self._surface_styles.get(key)
        if style is not None:
            return style
        style = ifcopenshell.api.style.add_style(
            self.model,
            name=(
                f"3D {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} "
                f"alpha {1 - transparency:.3f}"
            ),
        )
        ifcopenshell.api.style.add_surface_style(
            self.model,
            style=style,
            ifc_class="IfcSurfaceStyleShading",
            attributes={
                "SurfaceColour": {
                    "Name": None,
                    "Red": rgb[0],
                    "Green": rgb[1],
                    "Blue": rgb[2],
                },
                "Transparency": transparency,
            },
        )
        self._surface_styles[key] = style
        return style

    def wall_type(
        self,
        name: str,
        *,
        layers: Sequence[LayerItem],
        color: str | None = None,
        transparency: Number = 0,
    ) -> ifcopenshell.entity_instance:
        """Create a reusable wall type from ordered material layers.

        Each layer is a ``(material_name, thickness)`` pair.  Thicknesses are
        expressed in metres and their sum defines the thickness of every wall
        occurrence using this type.  Looking from ``start`` towards ``end``,
        layers are ordered from left to right (local positive Y to negative Y).
        An optional ``"axis"`` item places the wall's reference line at that
        boundary.  Without it, the construction is centred on the reference
        line.  ``color`` and ``transparency`` set the default 3D appearance of
        wall occurrences using this type.
        """
        type_name = _name(name, "name")
        if isinstance(layers, (str, bytes)):
            raise TypeError("layers must be a sequence of layer pairs")
        try:
            supplied_layers = list(layers)
        except TypeError as error:
            raise TypeError("layers must be a sequence of layer pairs") from error
        if not supplied_layers:
            raise ValueError("layers must contain at least one layer")

        normalised_layers: list[tuple[str, float]] = []
        axis_distance: float | None = None
        for index, supplied_layer in enumerate(supplied_layers, start=1):
            if isinstance(supplied_layer, str):
                if supplied_layer.strip().lower() != "axis":
                    raise ValueError(f'layer {index} string item must be "axis"')
                if axis_distance is not None:
                    raise ValueError("layers must contain at most one axis")
                axis_distance = sum(thickness for _, thickness in normalised_layers)
                continue
            try:
                material_name, thickness = supplied_layer
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"layer {index} must contain a material name and thickness"
                ) from error
            material_name = _name(material_name, f"layer {index} material name")
            thickness = _number(thickness, f"layer {index} thickness")
            if thickness <= 0:
                raise ValueError(f"layer {index} thickness must be greater than zero")
            normalised_layers.append((material_name, thickness))
        if not normalised_layers:
            raise ValueError("layers must contain at least one material layer")

        wall_type = ifcopenshell.api.root.create_entity(
            self.model,
            ifc_class="IfcWallType",
            name=type_name,
        )
        layer_set = ifcopenshell.api.material.add_material_set(
            self.model,
            name=type_name,
            set_type="IfcMaterialLayerSet",
        )
        for material_name, thickness in normalised_layers:
            material = self._materials.get(material_name)
            if material is None:
                material = ifcopenshell.api.material.add_material(
                    self.model,
                    name=material_name,
                )
                self._materials[material_name] = material
            layer = ifcopenshell.api.material.add_layer(
                self.model,
                layer_set=layer_set,
                material=material,
                name=material_name,
            )
            ifcopenshell.api.material.edit_layer(
                self.model,
                layer=layer,
                attributes={"LayerThickness": thickness},
            )
        ifcopenshell.api.material.assign_material(
            self.model,
            products=[wall_type],
            type="IfcMaterialLayerSet",
            material=layer_set,
        )
        total_thickness = sum(thickness for _, thickness in normalised_layers)
        left_thickness = (
            axis_distance if axis_distance is not None else total_thickness / 2
        )
        right_thickness = total_thickness - left_thickness
        self._wall_type_layouts[wall_type.id()] = (
            -right_thickness,
            left_thickness,
        )
        self._wall_type_styles[wall_type.id()] = self._surface_style(
            "wall",
            color=color,
            transparency=transparency,
        )
        return wall_type

    def storey(self, name: str, *, elevation: Number) -> Storey:
        """Create and return a building storey at ``elevation`` metres."""
        storey = Storey(self, _name(name, "name"), _number(elevation, "elevation"))
        self._storeys.append(storey)
        return storey

    def add_drawing(
        self,
        name: str,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        *,
        storeys: Sequence[Storey] | None = None,
    ) -> Drawing:
        """Add a persisted square plan drawing to this IFC model.

        ``storeys`` limits both model geometry and automatic plan annotations
        to the supplied building storeys.  When omitted, all storeys are
        included.  Drawing-specific annotations are always included.
        """
        drawing_name = _name(name, "name")
        if any(drawing.name == drawing_name for drawing in self._drawings):
            raise ValueError(f'drawing name already exists: "{drawing_name}"')
        drawing = Drawing(
            self,
            drawing_name,
            x=x,
            y=y,
            z=z,
            radius=radius,
            storeys=storeys,
        )
        self._drawings.append(drawing)
        return drawing

    def write(self, path: str | PathLike[str]) -> Path:
        """Write the IFC model and return the output path."""
        output = Path(path)
        self.model.write(str(output))
        self._ifc_path = output.resolve()
        return output

    def generate_plan(
        self,
        output: str | PathLike[str],
        *,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        png: bool = False,
        blender: str | PathLike[str] = "blender",
        inkscape: str | PathLike[str] = "inkscape",
        stylesheet: str | PathLike[str] | None = None,
    ) -> Path:
        """Generate a plan from this house's most recently written IFC path.

        This compatibility wrapper synchronises the live model to disk before
        delegating to the module-level :func:`generate_plan`.  New code may
        instead call ``generate_plan("house.ifc", "house.svg", ...)`` directly.
        """
        if self._ifc_path is None:
            raise RuntimeError("write the IFC model before generating a plan")
        self.model.write(str(self._ifc_path))
        return generate_plan(
            self._ifc_path,
            output,
            x=x,
            y=y,
            z=z,
            radius=radius,
            png=png,
            blender=blender,
            inkscape=inkscape,
            stylesheet=stylesheet,
        )


class Drawing:
    """A persisted Bonsai plan drawing belonging to a :class:`House`."""

    def __init__(
        self,
        house: House,
        name: str,
        *,
        x: Number,
        y: Number,
        z: Number,
        radius: Number,
        storeys: Sequence[Storey] | None,
    ) -> None:
        self.house = house
        self.name = name
        self.x = _number(x, "x")
        self.y = _number(y, "y")
        self.z = _number(z, "z")
        self.radius = _number(radius, "radius")
        if self.radius <= 0:
            raise ValueError("radius must be greater than zero")
        self._batting_count = 0
        self._dimension_count = 0
        self._annotated_stairs: set[int] = set()
        self._annotated_chimneys: set[int] = set()
        self._annotated_doors: set[int] = set()
        self._includes_all_storeys = storeys is None
        if storeys is None:
            self._storeys: tuple[Storey, ...] = ()
        else:
            if isinstance(storeys, (str, bytes)):
                raise TypeError("storeys must be a sequence of Storey objects")
            try:
                supplied_storeys = list(storeys)
            except TypeError as error:
                raise TypeError(
                    "storeys must be a sequence of Storey objects"
                ) from error
            normalised_storeys = []
            seen_storeys: set[int] = set()
            for index, storey in enumerate(supplied_storeys, start=1):
                if not isinstance(storey, Storey):
                    raise TypeError(f"storey {index} must be a Storey")
                if storey.house is not house:
                    raise ValueError(f"storey {index} must belong to this house")
                if storey.element.id() in seen_storeys:
                    raise ValueError(f"storey {index} is duplicated")
                seen_storeys.add(storey.element.id())
                normalised_storeys.append(storey)
            self._storeys = tuple(normalised_storeys)

        model = house.model
        self.element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=name,
            predefined_type="DRAWING",
        )

        placement = np.eye(4)
        placement[0, 3] = self.x
        placement[1, 3] = self.y
        placement[2, 3] = self.z
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=self.element,
            matrix=placement,
            is_si=True,
        )

        # Bonsai persists an orthographic camera as a rectangular viewing box:
        # the local X/Y extents are its frame and local negative Z is its view
        # depth.  Loader.create_camera reconstructs the Blender camera from it.
        r = self.radius
        depth = max(10.0, abs(self.z) + 10.0)
        vertices = [
            (-r, -r, -depth),
            (-r, -r, 0.0),
            (-r, r, -depth),
            (-r, r, 0.0),
            (r, -r, -depth),
            (r, -r, 0.0),
            (r, r, -depth),
            (r, r, 0.0),
        ]
        faces = [
            (0, 1, 3, 2),
            (2, 3, 7, 6),
            (6, 7, 5, 4),
            (4, 5, 1, 0),
            (2, 6, 4, 0),
            (7, 3, 1, 5),
        ]
        representation = ifcopenshell.api.geometry.add_mesh_representation(
            model,
            context=house._body_context,
            vertices=[vertices],
            faces=[faces],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=self.element,
            representation=representation,
        )

        self.group = ifcopenshell.api.group.add_group(model, name=name)
        ifcopenshell.api.group.edit_group(
            model,
            group=self.group,
            attributes={"Name": name, "ObjectType": "DRAWING"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[self.element],
        )
        plan_annotations = [
            annotation
            for annotation in house._plan_annotations
            if self._includes_storey_element(
                ifcopenshell.util.element.get_container(annotation)
            )
        ]
        if plan_annotations:
            ifcopenshell.api.group.assign_group(
                model,
                group=self.group,
                products=plan_annotations,
            )

        project_dir = Path(__file__).resolve().parent
        drawing_assets = project_dir / "drawings" / "assets"
        self._drawing_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=self.element,
            name="EPset_Drawing",
        )
        drawing_properties = {
            "TargetView": "PLAN_VIEW",
            "Scale": "1/100",
            "HumanScale": "1:100",
            "HasUnderlay": False,
            "HasLinework": True,
            "HasAnnotation": True,
            "GlobalReferencing": True,
            "DPI": 96,
            "LineworkMode": "OPENCASCADE",
            "FillMode": "NONE",
            "CutMode": "BISECT",
            "Stylesheet": str(project_dir / "bonsai_scripts" / "assets" / "plan.css"),
            "Markers": str(drawing_assets / "markers.svg"),
            "Symbols": str(drawing_assets / "symbols.svg"),
            "Patterns": str(drawing_assets / "patterns.svg"),
            "ShadingStyles": str(drawing_assets / "shading_styles.json"),
            "CurrentShadingStyle": "Technical",
        }
        if not self._includes_all_storeys:
            drawing_properties["Include"] = (
                "+".join(
                    f'location="{storey.element.GlobalId}"'
                    for storey in self._storeys
                )
                # A deliberately nonexistent IFC GUID makes an explicitly
                # empty storey list select no model elements in Bonsai.
                or "0000000000000000000000"
            )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=self._drawing_pset,
            properties=drawing_properties,
        )

        self.information = ifcopenshell.api.document.add_information(model)
        ifcopenshell.api.document.edit_information(
            model,
            information=self.information,
            attributes={
                "Identification": "X",
                "Name": name,
                "Scope": "DRAWING",
            },
        )
        self.document = ifcopenshell.api.document.add_reference(
            model,
            information=self.information,
        )
        safe_name = "".join(character for character in name if character.isalnum() or character in "._- ")
        ifcopenshell.api.document.edit_reference(
            model,
            reference=self.document,
            attributes={"Location": f"drawings/{safe_name}.svg"},
        )
        ifcopenshell.api.document.assign_document(
            model,
            products=[self.element],
            document=self.document,
        )

    @property
    def storeys(self) -> tuple[Storey, ...]:
        """Return the explicitly selected storeys, or all current storeys."""
        if self._includes_all_storeys:
            return tuple(self.house._storeys)
        return self._storeys

    @property
    def includes_all_storeys(self) -> bool:
        """Return whether this drawing uses the default all-storeys scope."""
        return self._includes_all_storeys

    def _includes_storey(self, storey: Storey) -> bool:
        return self._includes_all_storeys or storey in self._storeys

    def _includes_storey_element(
        self,
        storey: ifcopenshell.entity_instance | None,
    ) -> bool:
        return self._includes_all_storeys or any(
            selected.element == storey for selected in self._storeys
        )

    def add_dimension(
        self,
        start: Point,
        end: Point,
        *,
        offset: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add one linear plan dimension scoped only to this drawing.

        ``start`` and ``end`` are the measured points in global model XY
        coordinates.  ``offset`` moves the dimension line to its left when
        positive and to its right when negative, looking from ``start`` to
        ``end``.  Coordinates and offset are metres; Bonsai displays the
        measured value in millimetres.  A non-zero offset adds extension lines
        from the measured points to 1 mm beyond the dimension line at 1:100.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        offset = _number(offset, "offset")
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("dimension start and end must be different points")

        self._dimension_count += 1
        dimension_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} Dimension {self._dimension_count}"
        )
        normal_x = -delta_y / length
        normal_y = delta_x / length
        offset_x = normal_x * offset
        offset_y = normal_y * offset
        dimension_start = (start_x + offset_x, start_y + offset_y)
        dimension_end = (end_x + offset_x, end_y + offset_y)

        selected_storeys_below = [
            storey for storey in self.storeys if storey.elevation <= self.z
        ]
        annotation_z = (
            max(
                selected_storeys_below,
                key=lambda storey: storey.elevation,
            ).elevation
            if selected_storeys_below
            else 0.0
        )
        placement = np.eye(4)
        placement[2, 3] = annotation_z

        model = self.house.model
        dimension = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=dimension_name,
            predefined_type="DIMENSION",
        )
        dimension_representation = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._annotation_context,
            axis=[dimension_start, dimension_end],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=dimension,
            representation=dimension_representation,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=dimension,
            matrix=placement,
            is_si=True,
        )

        dimension_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=dimension,
            name="BBIM_Dimension",
        )
        unit_choices = (
            "Feet and Inches - Fractional",
            "Feet - Decimal",
            "Inches - Fractional",
            "Inches - Decimal",
            "Meters",
            "Decimeters",
            "Centimeters",
            "Millimeters",
        )
        unit_enumeration = model.createIfcPropertyEnumeration(
            "CustomUnit",
            [model.createIfcText(unit) for unit in unit_choices],
            None,
        )
        custom_unit = model.createIfcPropertyEnumeratedValue(
            "CustomUnit",
            None,
            [model.createIfcText("Millimeters")],
            unit_enumeration,
        )
        dimension_pset.HasProperties = (
            *(dimension_pset.HasProperties or ()),
            custom_unit,
        )

        drawing_products = [dimension]
        if offset != 0:
            extension_direction = 1.0 if offset > 0 else -1.0
            # Model-space equivalent of 1 mm on this fixed 1:100 drawing.
            extension_length = 0.1
            beyond_x = normal_x * extension_direction * extension_length
            beyond_y = normal_y * extension_direction * extension_length
            extension_curves = []
            for measured_point, dimension_point in (
                ((start_x, start_y), dimension_start),
                ((end_x, end_y), dimension_end),
            ):
                point_list = model.createIfcCartesianPointList2D(
                    [
                        measured_point,
                        (
                            dimension_point[0] + beyond_x,
                            dimension_point[1] + beyond_y,
                        ),
                    ]
                )
                extension_curves.append(
                    model.createIfcIndexedPolyCurve(point_list, None, False)
                )
            extension = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcAnnotation",
                name=f"{dimension_name} Extension Lines",
                predefined_type="LINEWORK",
            )
            extension_representation = model.createIfcShapeRepresentation(
                self.house._annotation_context,
                "Annotation",
                "GeometricCurveSet",
                [model.createIfcGeometricCurveSet(extension_curves)],
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=extension,
                representation=extension_representation,
            )
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=extension,
                matrix=placement.copy(),
                is_si=True,
            )
            extension_pset = ifcopenshell.api.pset.add_pset(
                model,
                product=extension,
                name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                model,
                pset=extension_pset,
                properties={"Classes": "dimension-extension fine"},
            )
            drawing_products.append(extension)

        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=drawing_products,
        )
        return dimension

    def add_door_annotation(
        self,
        door: ifcopenshell.entity_instance,
        *,
        offset: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a drawing-specific ``width/height`` label for ``door``.

        The values come from ``IfcDoor.OverallWidth`` and ``OverallHeight``
        and are displayed in millimetres on two lines.  The label is placed
        inside the plan swing and oriented across the wall.  ``offset`` moves
        it farther into the swing, in model metres; a negative value moves it
        toward the wall.
        """
        if not isinstance(door, ifcopenshell.entity_instance) or not door.is_a(
            "IfcDoor"
        ):
            raise TypeError("door must be an IfcDoor created by Wall.add_door")
        if door.file is not self.house.model:
            raise ValueError("door must belong to this house")
        if door.id() in self._annotated_doors:
            raise ValueError("door already has an annotation in this drawing")

        storey = ifcopenshell.util.element.get_container(door)
        if storey is None or not storey.is_a("IfcBuildingStorey"):
            raise ValueError("door must belong to a building storey")
        if not self._includes_storey_element(storey):
            raise ValueError("door storey is not included in this drawing")
        if door.OverallWidth is None or door.OverallHeight is None:
            raise ValueError("door must define OverallWidth and OverallHeight")
        width = float(door.OverallWidth)
        height = float(door.OverallHeight)
        offset = _number(offset, "offset")

        plan = ifcopenshell.util.representation.get_representation(
            door,
            "Plan",
            "Body",
            "PLAN_VIEW",
        )
        if plan is None:
            raise ValueError("door has no plan representation")
        y_coordinates = [
            float(point[1])
            for item in plan.Items
            if item.is_a("IfcIndexedPolyCurve")
            for point in item.Points.CoordList
        ]
        if not y_coordinates:
            raise ValueError("door plan representation has no swing geometry")
        swing_y = max(y_coordinates, key=abs)
        swing_sign = 1.0 if swing_y >= 0 else -1.0
        # Swinging leaves reach approximately one door width into the room.
        # Sliding-door plan geometry does not, so ensure that its label still
        # clears the wall lining.
        label_y = swing_y * 0.55 + swing_sign * offset
        if abs(label_y) < 0.2:
            label_y = swing_sign * (0.2 + offset)

        door_placement = ifcopenshell.util.placement.get_local_placement(
            door.ObjectPlacement
        )
        label_point = door_placement @ np.array(
            (width / 2, label_y, 0.0, 1.0),
            dtype=float,
        )
        placement = np.eye(4)
        placement[:3, 0] = swing_sign * door_placement[:3, 1]
        placement[:3, 1] = -swing_sign * door_placement[:3, 0]
        placement[:3, 2] = door_placement[:3, 2]
        placement[:3, 3] = label_point[:3]

        model = self.house.model
        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {door.Name or 'Door'} Dimensions"
        )
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="TEXT",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )
        literal_origin = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0)),
        )
        literal = model.createIfcTextLiteralWithExtent(
            f"{round(width * 1000)}\n{round(height * 1000)}",
            literal_origin,
            "RIGHT",
            model.createIfcPlanarExtent(max(width, 0.5), max(width, 0.5)),
            "center",
        )
        representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "Annotation2D",
            [literal],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"Classes": "door-dimension small"},
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=door,
            related_object=annotation,
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[annotation],
        )
        self._annotated_doors.add(door.id())
        return annotation

    def add_batting(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a batting annotation scoped only to this drawing."""
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("batting start and end must be different points")

        self._batting_count += 1
        annotation = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcAnnotation",
            name=(
                _name(name, "name")
                if name is not None
                else f"{self.name} Batting {self._batting_count}"
            ),
            predefined_type="BATTING",
        )

        storeys_below = [storey for storey in self.house._storeys if storey.elevation <= self.z]
        annotation_z = (
            max(storeys_below, key=lambda storey: storey.elevation).elevation
            if storeys_below
            else 0.0
        )
        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = annotation_z
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )

        representation = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._annotation_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model,
            product=annotation,
            representation=representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.house.model,
            product=annotation,
            name="BBIM_Batting",
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=pset,
            properties={"Thickness": thickness},
        )
        ifcopenshell.api.group.assign_group(
            self.house.model,
            group=self.group,
            products=[annotation],
        )
        return annotation

    def add_chimney_annotation(
        self,
        chimney: Chimney,
        *,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a circle with a diagonal half-fill for ``chimney`` to this drawing."""
        if not isinstance(chimney, Chimney):
            raise TypeError("chimney must be a Chimney created by Storey.chimney")
        if chimney.file is not self.house.model:
            raise ValueError("chimney must belong to this house")
        if chimney.id() in self._annotated_chimneys:
            raise ValueError("chimney already has an annotation in this drawing")

        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {chimney.Name} Flue Symbol"
        )
        model = self.house.model
        radius = chimney.flue_diameter / 2
        circle_points = [
            (
                radius * cos(radians(index * 360 / 32)),
                radius * sin(radians(index * 360 / 32)),
            )
            for index in range(33)
        ]

        fill = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{annotation_name} Fill",
            predefined_type="FILLAREA",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=fill,
            matrix=chimney.placement.copy(),
            is_si=True,
        )
        fill_points = [
            (
                radius * cos(radians(45 + index * 180 / 16)),
                radius * sin(radians(45 + index * 180 / 16)),
            )
            for index in range(17)
        ]
        fill_points.append(fill_points[0])
        fill_curve = model.createIfcIndexedPolyCurve(
            model.createIfcCartesianPointList2D(fill_points),
            None,
            False,
        )
        fill_area = model.createIfcAnnotationFillArea(fill_curve, None)
        fill_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "Annotation2D",
            [fill_area],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=fill,
            representation=fill_representation,
        )
        fill_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=fill,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=fill_pset,
            properties={"Classes": "chimney-flue-fill"},
        )

        outline = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=outline,
            matrix=chimney.placement.copy(),
            is_si=True,
        )
        outline_curve = model.createIfcIndexedPolyCurve(
            model.createIfcCartesianPointList2D(circle_points),
            None,
            False,
        )
        outline_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "GeometricCurveSet",
            [model.createIfcGeometricCurveSet([outline_curve])],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=outline,
            representation=outline_representation,
        )
        outline_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=outline,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=outline_pset,
            properties={"Classes": "chimney-flue"},
        )
        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[fill, outline],
        )
        self._annotated_chimneys.add(chimney.id())
        return outline

    def add_stair_annotation(
        self,
        stair: Stair,
        *,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a conventional plan symbol for ``stair`` to this drawing only.

        The annotation contains the stair outline, tread lines, an upward
        walking-direction arrow, and a break line at this drawing's cut
        elevation.  It does not alter the stair's 3D representation.
        """
        if not isinstance(stair, Stair):
            raise TypeError("stair must be a Stair created by Storey.stair")
        if stair.file is not self.house.model:
            raise ValueError("stair must belong to this house")
        if stair.id() in self._annotated_stairs:
            raise ValueError("stair already has an annotation in this drawing")

        annotation_name = (
            _name(name, "name")
            if name is not None
            else f"{self.name} {stair.Name} Plan Symbol"
        )
        model = self.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=annotation_name,
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=stair.placement.copy(),
            is_si=True,
        )

        half_width = stair.width / 2
        tread_length = stair.tread_length
        polylines: list[list[tuple[float, float]]] = [
            [
                (0.0, -half_width),
                (stair.length, -half_width),
                (stair.length, half_width),
                (0.0, half_width),
                (0.0, -half_width),
            ]
        ]
        for tread in range(1, stair.treads):
            x = tread * tread_length
            polylines.append([(x, -half_width), (x, half_width)])

        arrow_start = min(tread_length / 2, stair.length * 0.1)
        arrow_end = stair.length * 0.85
        arrow_size = min(stair.width * 0.18, stair.length * 0.06)
        polylines.extend(
            [
                [(arrow_start, 0.0), (arrow_end, 0.0)],
                [
                    (arrow_end - arrow_size, -arrow_size),
                    (arrow_end, 0.0),
                    (arrow_end - arrow_size, arrow_size),
                ],
            ]
        )

        relative_cut_height = self.z - (
            stair.storey.elevation + stair.start_height
        )
        if 0 < relative_cut_height < stair.height:
            break_x = stair.length * relative_cut_height / stair.height
        else:
            break_x = stair.length * 0.55
        break_x = min(max(break_x, stair.length * 0.2), stair.length * 0.8)
        break_offset = min(stair.width * 0.12, stair.length * 0.04)
        polylines.append(
            [
                (break_x - break_offset, -half_width),
                (break_x + break_offset, -half_width / 3),
                (break_x - break_offset, half_width / 3),
                (break_x + break_offset, half_width),
            ]
        )

        curves = []
        for points in polylines:
            point_list = model.createIfcCartesianPointList2D(points)
            curves.append(model.createIfcIndexedPolyCurve(point_list, None, False))
        representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "GeometricCurveSet",
            [model.createIfcGeometricCurveSet(curves)],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        annotation_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=annotation_pset,
            properties={"Classes": "stair"},
        )

        ifcopenshell.api.group.assign_group(
            model,
            group=self.group,
            products=[annotation],
        )
        self._annotated_stairs.add(stair.id())
        return annotation

    def render(
        self,
        output: str | PathLike[str],
        *,
        png: bool = False,
        png_dpi: Number = 200,
        blender: str | PathLike[str] = "blender",
        inkscape: str | PathLike[str] = "inkscape",
        stylesheet: str | PathLike[str] | None = None,
    ) -> Path:
        """Render through Blender/Bonsai; ``png_dpi`` controls optional PNG resolution."""
        if self.house._ifc_path is None:
            raise RuntimeError("write the house before rendering a drawing")

        output_path = Path(output)
        absolute_output = output_path.resolve()
        stylesheet_path = (
            Path(stylesheet)
            if stylesheet is not None
            else Path(__file__).resolve().parent / "bonsai_scripts" / "assets" / "plan.css"
        ).resolve()
        if not stylesheet_path.is_file():
            raise FileNotFoundError(f"drawing stylesheet not found: {stylesheet_path}")

        ifcopenshell.api.document.edit_reference(
            self.house.model,
            reference=self.document,
            attributes={"Location": str(absolute_output)},
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=self._drawing_pset,
            properties={"Stylesheet": str(stylesheet_path)},
        )
        self.house.model.write(str(self.house._ifc_path))
        return _render_existing_drawing(
            self.house._ifc_path,
            self.element.GlobalId,
            output_path,
            png=png,
            png_dpi=png_dpi,
            blender=blender,
            inkscape=inkscape,
        )


class Beam(ifcopenshell.entity_instance):
    """A rectangular ``IfcBeam`` spanning two world-coordinate points."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        size: tuple[float, float],
        length: float,
        kind: str,
        material_name: str,
        rotation: float,
        height_axis: tuple[float, float, float],
        cuts: tuple[PlaneCut, ...],
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "width", size[0])
        object.__setattr__(self, "height", size[1])
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "material_name", material_name)
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "height_axis", height_axis)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this beam as its underlying IFC entity."""
        return self


class Roof(ifcopenshell.entity_instance):
    """An ``IfcRoof`` aggregate containing planes and other roof elements."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "_planes", [])

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof as its underlying IFC entity."""
        return self

    @property
    def planes(self) -> tuple[RoofPlane, ...]:
        """Return the coordinate planes created beneath this roof."""
        return tuple(self._planes)

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Aggregate existing IFC elements beneath this roof."""
        if not elements:
            raise ValueError("roof.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.file:
                raise ValueError(f"element {index} must belong to this house")
            if element == self:
                raise ValueError("a roof cannot aggregate itself")
            normalised.append(element)
        return ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=normalised,
            relating_object=self,
        )

    def plane(
        self,
        name: str,
        *,
        points: Sequence[Point3D],
        cuts: Sequence[PlaneCut] | None = None,
    ) -> RoofPlane:
        """Create a roof-local frame from three global points.

        The first point is the origin, the second defines local positive X,
        and the third defines the roof plane and approximate positive Y.  Y is
        orthogonalised against X.  The perpendicular offset axis is flipped
        when necessary so positive local Z always has a positive global Z
        component, without changing the supplied X or Y directions.  ``cuts``
        are global three-point planes inherited by elements created through
        the returned plane.
        """
        plane_name = _name(name, "name")
        if any(plane.Name == plane_name for plane in self._planes):
            raise ValueError(f'roof plane name already exists: "{plane_name}"')
        if isinstance(points, (str, bytes)):
            raise TypeError("points must contain exactly three points")
        try:
            supplied_points = list(points)
        except TypeError as error:
            raise TypeError("points must contain exactly three points") from error
        if len(supplied_points) != 3:
            raise TypeError("points must contain exactly three points")
        origin, x_point, y_point = (
            _point_3d(point, f"point {index}")
            for index, point in enumerate(supplied_points, start=1)
        )
        origin_vector = np.array(origin, dtype=float)
        x_direction = np.array(x_point, dtype=float) - origin_vector
        x_length = float(np.linalg.norm(x_direction))
        if x_length <= 1e-9:
            raise ValueError("the first and second roof plane points must differ")
        x_axis = x_direction / x_length
        y_hint = np.array(y_point, dtype=float) - origin_vector
        raw_z_axis = np.cross(x_axis, y_hint)
        z_length = float(np.linalg.norm(raw_z_axis))
        if z_length <= 1e-9:
            raise ValueError("roof plane points must not be collinear")
        raw_z_axis /= z_length
        y_axis = np.cross(raw_z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)
        if abs(float(raw_z_axis[2])) <= 1e-9:
            raise ValueError(
                "roof plane must have a normal with a non-zero global Z component"
            )
        normal_flipped = bool(raw_z_axis[2] < 0)
        z_axis = -raw_z_axis if normal_flipped else raw_z_axis
        geometry_y_sign = -1.0 if normal_flipped else 1.0

        # IFC placements must remain right-handed.  If the user-defined
        # X/Y directions yield a downward normal, reflect geometry's local Y
        # while preserving the user coordinate transform separately.
        placement = np.eye(4)
        placement[:3, 0] = x_axis
        placement[:3, 1] = geometry_y_sign * y_axis
        placement[:3, 2] = z_axis
        placement[:3, 3] = origin_vector
        coordinate_matrix = np.eye(4)
        coordinate_matrix[:3, 0] = x_axis
        coordinate_matrix[:3, 1] = y_axis
        coordinate_matrix[:3, 2] = z_axis
        coordinate_matrix[:3, 3] = origin_vector
        normalised_cuts = _plane_cuts(cuts)

        assembly = ifcopenshell.api.root.create_entity(
            self.file,
            ifc_class="IfcElementAssembly",
            name=plane_name,
            predefined_type="USERDEFINED",
        )
        assembly.ObjectType = "ROOF_PLANE"
        assembly.AssemblyPlace = "SITE"
        ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=[assembly],
            relating_object=self,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.file,
            product=assembly,
            matrix=placement,
            is_si=True,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.file,
            product=assembly,
            name="BBIM_RoofPlane",
        )
        ifcopenshell.api.pset.edit_pset(
            self.file,
            pset=pset,
            properties={
                "Points": json.dumps((origin, x_point, y_point)),
                "Cuts": json.dumps(normalised_cuts),
                "NormalFlipped": normal_flipped,
            },
        )
        plane = RoofPlane(
            assembly,
            self,
            points=(origin, x_point, y_point),
            cuts=normalised_cuts,
            placement=placement,
            coordinate_matrix=coordinate_matrix,
            normal_flipped=normal_flipped,
        )
        self._planes.append(plane)
        return plane


class RoofPlane(ifcopenshell.entity_instance):
    """An IFC assembly providing a local coordinate frame for one roof slope."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        roof: Roof,
        *,
        points: tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ],
        cuts: tuple[PlaneCut, ...],
        placement: np.ndarray,
        coordinate_matrix: np.ndarray,
        normal_flipped: bool,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "roof", roof)
        object.__setattr__(self, "storey", roof.storey)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "origin", points[0])
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "coordinate_matrix", coordinate_matrix)
        object.__setattr__(self, "normal_flipped", normal_flipped)
        object.__setattr__(self, "geometry_y_sign", -1.0 if normal_flipped else 1.0)
        object.__setattr__(
            self,
            "x_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 0]),
        )
        object.__setattr__(
            self,
            "y_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 1]),
        )
        object.__setattr__(
            self,
            "z_axis",
            tuple(float(v) for v in coordinate_matrix[:3, 2]),
        )

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof plane as its underlying IFC assembly."""
        return self

    def to_world(self, point: Point3D) -> tuple[float, float, float]:
        """Transform a local XYZ point into global coordinates."""
        local = _point_3d(point, "point")
        world = self.coordinate_matrix @ np.array((*local, 1.0), dtype=float)
        return tuple(float(value) for value in world[:3])

    def to_local(self, point: Point3D) -> tuple[float, float, float]:
        """Transform a global XYZ point into this plane's coordinates."""
        world = _point_3d(point, "point")
        local = np.linalg.inv(self.coordinate_matrix) @ np.array(
            (*world, 1.0), dtype=float
        )
        return tuple(float(value) for value in local[:3])

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Aggregate existing IFC elements beneath this roof plane."""
        if not elements:
            raise ValueError("roof_plane.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.file:
                raise ValueError(f"element {index} must belong to this house")
            if element in {self, self.roof}:
                raise ValueError("a roof plane cannot aggregate itself or its roof")
            normalised.append(element)
        return ifcopenshell.api.aggregate.assign_object(
            self.file,
            products=normalised,
            relating_object=self,
        )

    def beam(
        self,
        name: str,
        *,
        start: Point,
        end: Point,
        size: Sequence[Number],
        z_offset: Number = 0,
        material: str = "Wood",
        kind: BeamKind = "BEAM",
        rotation: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Beam:
        """Create a plane-local beam with its bottom at ``z_offset``.

        The unrotated section height follows the roof plane's local Z.  When
        ``rotation`` rolls the section, the centreline is raised as necessary
        so its lowest point along local Z remains at ``z_offset``.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        z_offset = _number(z_offset, "z_offset")
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly two dimensions")
        try:
            width, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly two dimensions"
            ) from error
        width = _number(width, "size width")
        height = _number(height, "size height")
        if width <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        rotation = _number(rotation, "rotation")
        roll = radians(rotation)
        section_extent_below_centre = (
            abs(sin(roll)) * width / 2
            + abs(cos(roll)) * height / 2
        )
        centreline_z_offset = z_offset + section_extent_below_centre
        beam = self.storey.beam(
            name,
            start=self.to_world((start_x, start_y, centreline_z_offset)),
            end=self.to_world((end_x, end_y, centreline_z_offset)),
            size=(width, height),
            material=material,
            kind=kind,
            rotation=rotation,
            color=color,
            transparency=transparency,
            height_axis=self.z_axis,
            cuts=self.cuts,
        )
        self.add(beam)
        object.__setattr__(beam, "roof_plane", self)
        object.__setattr__(beam, "local_start", (start_x, start_y))
        object.__setattr__(beam, "local_end", (end_x, end_y))
        object.__setattr__(beam, "z_offset", z_offset)
        object.__setattr__(beam, "centerline_z_offset", centreline_z_offset)
        return beam

    def layer(
        self,
        name: str,
        *,
        outline: Sequence[Point],
        z_offset: Number = 0,
        thickness: Number,
        material: str,
        color: str | None = None,
        transparency: Number = 0,
        extra_cuts: Sequence[PlaneCut] | None = None,
    ) -> RoofLayer:
        """Create a roof layer, optionally appending global clipping planes."""
        layer_name = _name(name, "name")
        material_name = _name(material, "material")
        z_offset = _number(z_offset, "z_offset")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if isinstance(outline, (str, bytes)):
            raise TypeError("outline must contain at least three points")
        try:
            supplied_outline = list(outline)
        except TypeError as error:
            raise TypeError("outline must contain at least three points") from error
        if len(supplied_outline) < 3:
            raise ValueError("outline must contain at least three points")
        points = tuple(
            _point(point, f"outline point {index}")
            for index, point in enumerate(supplied_outline, start=1)
        )
        twice_area = 0.0
        centroid_x_sum = 0.0
        centroid_y_sum = 0.0
        for point, next_point in zip(points, (*points[1:], points[0])):
            cross = point[0] * next_point[1] - next_point[0] * point[1]
            twice_area += cross
            centroid_x_sum += (point[0] + next_point[0]) * cross
            centroid_y_sum += (point[1] + next_point[1]) * cross
        if abs(twice_area) <= 1e-9:
            raise ValueError("outline must enclose a non-zero area")
        centroid = (
            centroid_x_sum / (3 * twice_area),
            centroid_y_sum / (3 * twice_area),
        )
        geometry_points = tuple(
            (x, self.geometry_y_sign * y) for x, y in points
        )
        geometry_centroid = (
            centroid[0],
            self.geometry_y_sign * centroid[1],
        )
        normalised_extra_cuts = _plane_cuts(extra_cuts)
        effective_cuts = (*self.cuts, *normalised_extra_cuts)

        placement = self.placement.copy()
        placement[:3, 3] = np.array(self.to_world((0, 0, z_offset)))
        clippings = _local_clippings(
            effective_cuts,
            placement,
            (geometry_centroid[0], geometry_centroid[1], thickness / 2),
        )
        model = self.file
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=layer_name,
            predefined_type="ROOF",
        )
        layer = RoofLayer(
            element,
            self,
            outline=points,
            z_offset=z_offset,
            thickness=thickness,
            material_name=material_name,
            placement=placement,
            cuts=effective_cuts,
            extra_cuts=normalised_extra_cuts,
        )
        self.add(layer)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=layer,
            matrix=placement,
            is_si=True,
        )
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.storey.house._body_context,
            depth=thickness,
            polyline=geometry_points,
        )
        _clip_body_representation(model, layer, body, clippings)
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=layer,
            representation=body,
        )
        surface_style = self.storey.house._surface_style(
            "slab",
            color=color,
            transparency=transparency,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        ifc_material = self.storey.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self.storey.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[layer],
            type="IfcMaterial",
            material=ifc_material,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=layer,
            name="BBIM_RoofLayer",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "RoofPlane": self.GlobalId,
                "Outline": json.dumps(points),
                "ZOffset": z_offset,
                "Thickness": thickness,
                "Cuts": json.dumps(effective_cuts),
                "ExtraCuts": json.dumps(normalised_extra_cuts),
            },
        )
        return layer


class RoofLayer(ifcopenshell.entity_instance):
    """A physical ``IfcSlab/ROOF`` layer created in a roof-plane frame."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        plane: RoofPlane,
        *,
        outline: tuple[tuple[float, float], ...],
        z_offset: float,
        thickness: float,
        material_name: str,
        placement: np.ndarray,
        cuts: tuple[PlaneCut, ...],
        extra_cuts: tuple[PlaneCut, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "plane", plane)
        object.__setattr__(self, "roof", plane.roof)
        object.__setattr__(self, "storey", plane.storey)
        object.__setattr__(self, "outline", outline)
        object.__setattr__(self, "z_offset", z_offset)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "material_name", material_name)
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "extra_cuts", extra_cuts)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this roof layer as its underlying IFC entity."""
        return self


class Chimney(ifcopenshell.entity_instance):
    """An ``IfcChimney`` with a square stack and central circular flue."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        center: tuple[float, float],
        size: float,
        height: float,
        flue_diameter: float,
        start_height: float,
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "flue_diameter", flue_diameter)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this chimney as its underlying IFC entity."""
        return self


class MiakoSlab(ifcopenshell.entity_instance):
    """A decomposed ``IfcSlab`` made from MIAKO beams, blocks, and topping."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        direction: tuple[float, float],
        structure: tuple[str, ...],
        length: float,
        width: float,
        top: float,
        block_length: float,
        block_height: float,
        beam_height: float,
        topping: float,
        placement: np.ndarray,
        beams: tuple[ifcopenshell.entity_instance, ...],
        blocks: tuple[ifcopenshell.entity_instance, ...],
        topping_element: ifcopenshell.entity_instance,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "structure", structure)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "top", top)
        object.__setattr__(self, "block_length", block_length)
        object.__setattr__(self, "block_height", block_height)
        object.__setattr__(self, "beam_height", beam_height)
        object.__setattr__(self, "topping", topping)
        object.__setattr__(self, "height", block_height + topping)
        object.__setattr__(self, "bottom", top - (block_height + topping))
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "beams", beams)
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "topping_element", topping_element)
        object.__setattr__(
            self,
            "components",
            (*beams, *blocks, topping_element),
        )

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this MIAKO slab as its underlying IFC entity."""
        return self


class Stair(ifcopenshell.entity_instance):
    """An ``IfcStair`` containing one straight ``IfcStairFlight``."""

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        flight: ifcopenshell.entity_instance,
        start: tuple[float, float],
        end: tuple[float, float],
        length: float,
        width: float,
        height: float,
        start_height: float,
        risers: int,
        treads: int,
        riser_height: float,
        tread_length: float,
        underside: Literal["solid", "sloped"],
        waist_thickness: float | None,
        placement: np.ndarray,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "flight", flight)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "risers", risers)
        object.__setattr__(self, "treads", treads)
        object.__setattr__(self, "riser_height", riser_height)
        object.__setattr__(self, "tread_length", tread_length)
        object.__setattr__(self, "underside", underside)
        object.__setattr__(self, "waist_thickness", waist_thickness)
        object.__setattr__(self, "placement", placement)

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this stair as its underlying IFC entity."""
        return self


class Wall(ifcopenshell.entity_instance):
    """An ``IfcWall`` with convenience methods for hosted elements.

    The class is an IfcOpenShell entity instance, so it can be passed directly
    to IfcOpenShell APIs.  Door and window ``at`` distances locate the start
    of their wall opening from the wall's supplied start point.
    """

    def __init__(
        self,
        element: ifcopenshell.entity_instance,
        storey: Storey,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        length: float,
        height: float,
        start_height: float,
        thickness: float,
        body_offset: float,
        surface_style: ifcopenshell.entity_instance | None,
        cuts: tuple[WallCut, ...],
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "start_height", start_height)
        object.__setattr__(self, "end_height", start_height + height)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "body_offset", body_offset)
        object.__setattr__(self, "surface_style", surface_style)
        object.__setattr__(self, "cuts", cuts)
        object.__setattr__(self, "_openings", [])

    @property
    def element(self) -> ifcopenshell.entity_instance:
        """Return this wall as its underlying IFC entity."""
        return self

    def _validate_opening(
        self,
        *,
        opening_start: Number,
        width: Number,
        height: Number,
        sill_height: Number,
    ) -> tuple[float, float, float, float]:
        opening_start = _number(opening_start, "opening start")
        width = _number(width, "width")
        height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if sill_height < 0:
            raise ValueError("sill_height must not be negative")
        if sill_height < self.start_height:
            raise ValueError("opening must not start below the wall")

        opening_end = opening_start + width
        opening_top = sill_height + height
        tolerance = 1e-9
        if opening_start < -tolerance or opening_end > self.length + tolerance:
            raise ValueError("opening must fit within the wall length")
        if opening_top > self.end_height + tolerance:
            raise ValueError("opening must fit within the wall height")

        for existing_start, existing_end, existing_bottom, existing_top in self._openings:
            overlaps_horizontally = (
                opening_start < existing_end - tolerance
                and existing_start < opening_end - tolerance
            )
            overlaps_vertically = (
                sill_height < existing_top - tolerance
                and existing_bottom < opening_top - tolerance
            )
            if overlaps_horizontally and overlaps_vertically:
                raise ValueError("opening overlaps another opening in this wall")

        return opening_start, width, height, sill_height

    def _placement(self, along: float, elevation: float) -> np.ndarray:
        direction_x = (self.end[0] - self.start[0]) / self.length
        direction_y = (self.end[1] - self.start[1]) / self.length
        placement = np.eye(4)
        placement[0, 0] = direction_x
        placement[0, 1] = -direction_y
        placement[1, 0] = direction_y
        placement[1, 1] = direction_x
        placement[0, 3] = self.start[0] + along * direction_x
        placement[1, 3] = self.start[1] + along * direction_y
        placement[2, 3] = self.storey.elevation + elevation
        return placement

    def _create_opening(
        self,
        *,
        name: str,
        opening_start: float,
        width: float,
        height: float,
        sill_height: float,
    ) -> ifcopenshell.entity_instance:
        model = self.storey.house.model
        opening = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcOpeningElement",
            name=name,
            predefined_type="OPENING",
        )
        overlap = 0.05
        representation = ifcopenshell.api.geometry.add_wall_representation(
            model,
            context=self.storey.house._body_context,
            length=width,
            height=height,
            thickness=self.thickness + 2 * overlap,
            offset=self.body_offset - overlap,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=opening,
            representation=representation,
        )
        ifcopenshell.api.feature.add_feature(
            model,
            feature=opening,
            element=self,
        )
        placement = self._placement(opening_start, sill_height)
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=opening,
            matrix=placement,
            is_si=True,
        )
        return opening

    def _add_dashed_overhead_line(
        self,
        *,
        name: str,
        opening_start: float,
        opening_width: float,
        wall_faces: bool = False,
    ) -> ifcopenshell.entity_instance:
        """Add plan-only dashed linework for the wall above an opening."""
        model = self.storey.house.model
        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{name} Overhead",
            predefined_type="LINEWORK",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[annotation],
            relating_structure=self.storey.element,
        )
        if wall_faces:
            inset = min(0.025, opening_width / 4)
            curves = []
            for y in (self.body_offset, self.body_offset + self.thickness):
                point_list = model.createIfcCartesianPointList2D(
                    [(inset, y), (opening_width - inset, y)]
                )
                curves.append(
                    model.createIfcIndexedPolyCurve(point_list, None, False)
                )
            representation = model.createIfcShapeRepresentation(
                self.storey.house._annotation_context,
                "Annotation",
                "GeometricCurveSet",
                [model.createIfcGeometricCurveSet(curves)],
            )
            classes = "door-overhead dashed"
        else:
            wall_centre = self.body_offset + self.thickness / 2
            representation = ifcopenshell.api.geometry.add_axis_representation(
                model,
                context=self.storey.house._annotation_context,
                axis=[(0.0, wall_centre), (opening_width, wall_centre)],
            )
            classes = "dashed"
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=representation,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=self._placement(opening_start, 0),
            is_si=True,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"Classes": classes},
        )
        house = self.storey.house
        house._plan_annotations.append(annotation)
        for drawing in house._drawings:
            if drawing._includes_storey(self.storey):
                ifcopenshell.api.group.assign_group(
                    model,
                    group=drawing.group,
                    products=[annotation],
                )
        return annotation

    def _place_filling(
        self,
        filling: ifcopenshell.entity_instance,
        opening: ifcopenshell.entity_instance,
        placement: np.ndarray,
    ) -> None:
        model = self.storey.house.model
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[filling],
            relating_structure=self.storey.element,
        )
        ifcopenshell.api.feature.add_filling(
            model,
            opening=opening,
            element=filling,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=filling,
            matrix=placement,
            is_si=True,
        )

    def _set_door_open_angle(
        self,
        door: ifcopenshell.entity_instance,
        *,
        operation: str,
        open_angle: float,
        reverse_swing: bool,
        width: float,
        panel_offset_x: float,
        panel_offset_y: float,
    ) -> None:
        """Rotate only the movable items in a door's 3D body representation."""
        if open_angle == 0 or "SLIDING" in operation:
            return

        framing = next(
            aspect
            for aspect in door.Representation.HasShapeAspects
            if aspect.Name == "Framing"
        )
        items = [
            item
            for representation in framing.ShapeRepresentations
            if representation.ContextOfItems == self.storey.house._body_context
            for item in representation.Items
        ]
        pivot_y = self.body_offset + panel_offset_y
        model = self.storey.house.model
        swing_sign = -1 if reverse_swing else 1
        if operation.startswith("DOUBLE_DOOR"):
            half = len(items) // 2
            _rotate_items_about_z(
                model,
                items[:half],
                angle=swing_sign * open_angle,
                pivot=(panel_offset_x, pivot_y),
            )
            _rotate_items_about_z(
                model,
                items[half:],
                angle=-swing_sign * open_angle,
                pivot=(width - panel_offset_x, pivot_y),
            )
        else:
            is_left_hinged = operation.endswith("LEFT")
            _rotate_items_about_z(
                model,
                items,
                angle=(
                    swing_sign * open_angle
                    if is_left_hinged
                    else -swing_sign * open_angle
                ),
                pivot=(
                    panel_offset_x if is_left_hinged else width - panel_offset_x,
                    pivot_y,
                ),
            )

    def _reverse_door_plan_swing(
        self,
        representation: ifcopenshell.entity_instance,
    ) -> None:
        """Mirror plan-only leaf and arc geometry across the closed leaf."""
        items = list(representation.Items)
        if len(items) < 3:
            raise RuntimeError("unexpected door plan representation structure")
        ShapeBuilder(self.storey.house.model).mirror(
            items[2:],
            mirror_axes=(0.0, 1.0),
            mirror_point=(0.0, self.body_offset + self.thickness),
        )

    def add_opening(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number = 0,
        show_overhead: bool = True,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut an unfilled rectangular opening in this wall.

        ``at`` locates the start of the opening along the wall and
        ``sill_height`` locates its bottom above the storey elevation.
        ``height`` is the vertical size of the opening.  ``show_overhead``
        adds dashed plan-only wall linework across it.
        """
        if not isinstance(show_overhead, bool):
            raise TypeError("show_overhead must be a boolean")
        opening_start, width, height, sill_height = self._validate_opening(
            opening_start=at,
            width=width,
            height=height,
            sill_height=sill_height,
        )

        self.storey._opening_count += 1
        opening_name = (
            _name(name, "name")
            if name is not None
            else f"Wall Opening {self.storey._opening_count}"
        )
        opening = self._create_opening(
            name=opening_name,
            opening_start=opening_start,
            width=width,
            height=height,
            sill_height=sill_height,
        )
        self._openings.append(
            (
                opening_start,
                opening_start + width,
                sill_height,
                sill_height + height,
            )
        )
        if show_overhead:
            self._add_dashed_overhead_line(
                name=opening_name,
                opening_start=opening_start,
                opening_width=width,
                wall_faces=True,
            )
        return opening

    def add_door(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number = 0,
        opening_width: Number | None = None,
        opening_height: Number | None = None,
        operation: DoorOperation = "SINGLE_SWING_LEFT",
        open_angle: Number = 45,
        reverse_swing: bool = False,
        show_overhead: bool = True,
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a door opening in this wall.

        ``at`` is the start of the rough opening measured from the wall start.
        The actual door is centred horizontally in ``opening_width`` and its
        bottom is ``sill_height`` metres above the storey elevation.  Opening
        dimensions default to the door dimensions.  ``open_angle`` rotates
        only the 3D leaf.  ``reverse_swing`` opens the leaf on the opposite
        side of the wall without changing its hinge end, in both 3D and plan.
        ``show_overhead`` adds dashed plan-only wall linework across the rough
        opening.  ``color`` and ``transparency`` affect only the 3D body.
        """
        operation = _enum(operation, "operation", _DOOR_OPERATIONS)
        open_angle = _number(open_angle, "open_angle")
        if not 0 <= open_angle <= 180:
            raise ValueError("open_angle must be between 0 and 180 degrees")
        if not isinstance(reverse_swing, bool):
            raise TypeError("reverse_swing must be a boolean")
        if reverse_swing and "SLIDING" in operation:
            raise ValueError("reverse_swing is not supported for sliding doors")
        if not isinstance(show_overhead, bool):
            raise TypeError("show_overhead must be a boolean")
        surface_style = self.storey.house._surface_style(
            "door",
            color=color,
            transparency=transparency,
        )
        at = _number(at, "at")
        width = _number(width, "width")
        height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        opening_width = (
            width
            if opening_width is None
            else _number(opening_width, "opening_width")
        )
        opening_height = (
            height
            if opening_height is None
            else _number(opening_height, "opening_height")
        )
        tolerance = 1e-9
        if opening_width < width - tolerance:
            raise ValueError("opening_width must not be smaller than width")
        if opening_height < height - tolerance:
            raise ValueError("opening_height must not be smaller than height")
        opening_start, opening_width, opening_height, sill_height = (
            self._validate_opening(
                opening_start=at,
                width=opening_width,
                height=opening_height,
                sill_height=sill_height,
            )
        )
        door_start = opening_start + (opening_width - width) / 2
        filling_placement = self._placement(door_start, sill_height)
        self.storey._door_count += 1
        door_name = (
            _name(name, "name")
            if name is not None
            else f"Door {self.storey._door_count}"
        )
        opening = self._create_opening(
            name=f"{door_name} Opening",
            opening_start=opening_start,
            width=opening_width,
            height=opening_height,
            sill_height=sill_height,
        )

        model = self.storey.house.model
        door = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcDoor",
            name=door_name,
            predefined_type="DOOR",
        )
        door.OverallWidth = width
        door.OverallHeight = height
        door.OperationType = operation
        panel_offset_x = min(0.025, width / 4)
        panel_offset_y = min(0.025, self.thickness / 4)
        lining_properties = {
            "LiningDepth": self.thickness,
            "LiningOffset": self.body_offset,
            "LiningToPanelOffsetX": panel_offset_x,
            "LiningToPanelOffsetY": panel_offset_y,
        }
        door.Representation = model.createIfcProductDefinitionShape()
        body_representation = ifcopenshell.api.geometry.add_door_representation(
            model,
            context=self.storey.house._body_context,
            overall_height=height,
            overall_width=width,
            operation_type=operation,
            lining_properties=lining_properties,
            part_of_product=door.Representation,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=door,
            representation=body_representation,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body_representation,
                styles=[surface_style],
            )
        self._set_door_open_angle(
            door,
            operation=operation,
            open_angle=open_angle,
            reverse_swing=reverse_swing,
            width=width,
            panel_offset_x=panel_offset_x,
            panel_offset_y=panel_offset_y,
        )

        plan_representation = ifcopenshell.api.geometry.add_door_representation(
            model,
            context=self.storey.house._plan_body_context,
            overall_height=height,
            overall_width=width,
            operation_type=operation,
            lining_properties=lining_properties,
        )
        if plan_representation is not None:
            if reverse_swing:
                self._reverse_door_plan_swing(plan_representation)
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=door,
                representation=plan_representation,
            )
        self._place_filling(door, opening, filling_placement)
        self._openings.append(
            (
                opening_start,
                opening_start + opening_width,
                sill_height,
                sill_height + opening_height,
            )
        )
        if show_overhead:
            self._add_dashed_overhead_line(
                name=door_name,
                opening_start=opening_start,
                opening_width=opening_width,
                wall_faces=True,
            )
        return door

    def _align_window_panel_to_axis(
        self,
        window: ifcopenshell.entity_instance,
    ) -> None:
        """Move the generated 3D frame and glazing onto the wall axis."""
        aspects = {
            aspect.Name: aspect
            for aspect in window.Representation.HasShapeAspects
        }
        glazing = aspects.get("Glazing")
        if glazing is None:
            raise RuntimeError("window representation has no glazing aspect")
        glazing_representation = next(
            representation
            for representation in glazing.ShapeRepresentations
            if representation.ContextOfItems == self.storey.house._body_context
        )
        glass = glazing_representation.Items[0]
        glass_placement = ifcopenshell.util.placement.get_axis2placement(
            glass.Position
        )
        extrusion_direction = np.array(
            tuple(glass.ExtrudedDirection.DirectionRatios),
            dtype=float,
        )
        glass_center = glass_placement[:3, 3] + (
            glass_placement[:3, :3]
            @ extrusion_direction
            * float(glass.Depth)
            / 2
        )
        offset_y = -float(glass_center[1])

        for aspect_name in ("Framing", "Glazing"):
            aspect = aspects.get(aspect_name)
            if aspect is None:
                raise RuntimeError(
                    f"window representation has no {aspect_name.lower()} aspect"
                )
            for representation in aspect.ShapeRepresentations:
                if representation.ContextOfItems != self.storey.house._body_context:
                    continue
                for item in representation.Items:
                    coordinates = list(item.Position.Location.Coordinates)
                    coordinates[1] += offset_y
                    item.Position.Location.Coordinates = tuple(coordinates)

    def _align_window_plan_to_axis(
        self,
        representation: ifcopenshell.entity_instance,
    ) -> None:
        """Move each generated 2D frame and glass group onto the wall axis."""
        items = list(representation.Items)
        items_per_panel = 8
        if not items or len(items) % items_per_panel:
            raise RuntimeError("unexpected window plan representation structure")

        for start in range(0, len(items), items_per_panel):
            panel_items = items[start : start + items_per_panel]
            glass_line = panel_items[-1]
            glass_coordinates = glass_line.Points.CoordList
            offset_y = -float(glass_coordinates[0][1])
            for item in panel_items[3:]:
                item.Points.CoordList = tuple(
                    (float(x), float(y) + offset_y)
                    for x, y in item.Points.CoordList
                )

    def add_window(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number,
        partition: WindowPartition = "SINGLE_PANEL",
        align: WindowAlignment = "axis",
        glass_transparency: Number = 0.75,
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a window opening in this wall.

        ``at`` is the opening start measured from the wall start and
        ``sill_height`` and ``height`` are the bottom and top coordinates
        measured above the storey elevation.  ``align="axis"`` centres the
        frame and glazing on the wall reference axis in both the 3D and plan
        representations; ``align="inside"`` keeps IfcOpenShell's legacy panel
        position.  ``color`` applies to the whole 3D window, ``transparency``
        controls its lining and frame, and ``glass_transparency`` independently
        controls the glazing.
        """
        partition = _enum(partition, "partition", _WINDOW_PARTITIONS)
        align = _enum(align, "align", _WINDOW_ALIGNMENTS)
        surface_style = self.storey.house._surface_style(
            "window",
            color=color,
            transparency=transparency,
        )
        glass_color = color
        if (
            glass_color is None
            and "window" not in self.storey.house._default_colors
        ):
            glass_color = "#B7D9E8"
        glass_surface_style = self.storey.house._surface_style(
            "window",
            color=glass_color,
            transparency=glass_transparency,
        )
        at = _number(at, "at")
        width = _number(width, "width")
        top_height = _number(height, "height")
        sill_height = _number(sill_height, "sill_height")
        if top_height <= sill_height:
            raise ValueError("height must be greater than sill_height")
        window_height = top_height - sill_height
        opening_start, width, window_height, sill_height = self._validate_opening(
            opening_start=at,
            width=width,
            height=window_height,
            sill_height=sill_height,
        )
        self.storey._window_count += 1
        window_name = (
            _name(name, "name")
            if name is not None
            else f"Window {self.storey._window_count}"
        )
        opening = self._create_opening(
            name=f"{window_name} Opening",
            opening_start=opening_start,
            width=width,
            height=window_height,
            sill_height=sill_height,
        )
        placement = self._placement(opening_start, sill_height)

        model = self.storey.house.model
        window = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcWindow",
            name=window_name,
            predefined_type="WINDOW",
        )
        window.OverallWidth = width
        window.OverallHeight = window_height
        window.PartitioningType = partition
        window.Representation = model.createIfcProductDefinitionShape()
        lining_properties = {
            "LiningDepth": self.thickness,
            "LiningOffset": self.body_offset,
        }
        body_representation = None
        plan_representation = None
        for context in (
            self.storey.house._body_context,
            self.storey.house._plan_body_context,
        ):
            representation = ifcopenshell.api.geometry.add_window_representation(
                model,
                context=context,
                overall_height=window_height,
                overall_width=width,
                partition_type=partition,
                lining_properties=lining_properties,
                part_of_product=(
                    window.Representation
                    if context == self.storey.house._body_context
                    else None
                ),
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=window,
                representation=representation,
            )
            if context == self.storey.house._body_context:
                body_representation = representation
            else:
                plan_representation = representation
        if body_representation is None:
            raise RuntimeError("window has no 3D body representation")
        if plan_representation is None:
            raise RuntimeError("window has no plan representation")
        if align == "AXIS":
            self._align_window_panel_to_axis(window)
            self._align_window_plan_to_axis(plan_representation)
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body_representation,
                styles=[surface_style],
            )
        glazing = next(
            aspect
            for aspect in window.Representation.HasShapeAspects
            if aspect.Name == "Glazing"
        )
        for representation in glazing.ShapeRepresentations:
            if representation.ContextOfItems != self.storey.house._body_context:
                continue
            for item in representation.Items:
                ifcopenshell.api.style.assign_item_style(
                    model,
                    item=item,
                    style=glass_surface_style,
                )
        self._place_filling(window, opening, placement)
        self._openings.append(
            (opening_start, opening_start + width, sill_height, top_height)
        )
        return window


class Storey:
    """A building storey belonging to a :class:`House`."""

    def __init__(self, house: House, name: str, elevation: float) -> None:
        self.house = house
        self.name = name
        self.elevation = elevation
        self.element = ifcopenshell.api.root.create_entity(
            house.model, ifc_class="IfcBuildingStorey", name=name
        )
        self.element.Elevation = elevation
        ifcopenshell.api.aggregate.assign_object(
            house.model, products=[self.element], relating_object=house.building
        )

        placement = np.eye(4)
        placement[2, 3] = elevation
        ifcopenshell.api.geometry.edit_object_placement(
            house.model,
            product=self.element,
            matrix=placement,
            is_si=True,
        )
        self._wall_count = 0
        self._batting_count = 0
        self._opening_count = 0
        self._door_count = 0
        self._window_count = 0
        self._stair_count = 0
        self._landing_count = 0
        self._chimney_count = 0

    def add(
        self,
        *elements: ifcopenshell.entity_instance,
    ) -> ifcopenshell.entity_instance:
        """Spatially contain existing IFC elements in this storey."""
        if not elements:
            raise ValueError("storey.add requires at least one element")
        normalised = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, ifcopenshell.entity_instance) or not element.is_a(
                "IfcElement"
            ):
                raise TypeError(f"element {index} must be an IfcElement")
            if element.file is not self.house.model:
                raise ValueError(f"element {index} must belong to this house")
            normalised.append(element)
        return ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=normalised,
            relating_structure=self.element,
        )

    def roof(self, name: str) -> Roof:
        """Create an ``IfcRoof`` aggregate contained by this storey."""
        roof_name = _name(name, "name")
        element = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcRoof",
            name=roof_name,
            predefined_type="NOTDEFINED",
        )
        roof = Roof(element, self)
        ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=[roof],
            relating_structure=self.element,
        )
        placement = np.eye(4)
        placement[2, 3] = self.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=roof,
            matrix=placement,
            is_si=True,
        )
        return roof

    def batting(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a classic batt-insulation annotation along a plan line.

        The annotation and its line geometry are stored in the IFC.  Bonsai
        uses the ``BBIM_Batting.Thickness`` property, expressed in metres, to
        size the loops when producing a drawing.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("batting start and end must be different points")

        self._batting_count += 1
        annotation = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcAnnotation",
            name=(
                _name(name, "name")
                if name is not None
                else f"Batting {self._batting_count}"
            ),
            predefined_type="BATTING",
        )
        ifcopenshell.api.spatial.assign_container(
            self.house.model,
            products=[annotation],
            relating_structure=self.element,
        )

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation
        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=annotation,
            matrix=placement,
            is_si=True,
        )

        representation = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._annotation_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model,
            product=annotation,
            representation=representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            self.house.model,
            product=annotation,
            name="BBIM_Batting",
        )
        ifcopenshell.api.pset.edit_pset(
            self.house.model,
            pset=pset,
            properties={"Thickness": thickness},
        )
        return annotation

    def beam(
        self,
        name: str,
        *,
        start: Point3D,
        end: Point3D,
        size: Sequence[Number],
        material: str = "Wood",
        kind: BeamKind = "BEAM",
        rotation: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
        height_axis: Point3D | None = None,
        cuts: Sequence[PlaneCut] | None = None,
    ) -> Beam:
        """Create a rectangular beam between two world-coordinate points.

        ``start`` and ``end`` are the beam centreline endpoints in global XYZ
        coordinates.  ``size`` is ``(width, height)`` perpendicular to that
        centreline.  The height axis stays as vertical as the beam direction
        permits, while ``rotation`` applies a right-hand roll in degrees about
        the start-to-end axis.  ``height_axis`` may supply another global
        reference direction, such as a roof-plane normal.  Global three-point
        ``cuts`` retain the side containing the uncut beam centre.

        IFC4 has no dedicated rafter or purlin enum, so ``"RAFTER"`` and
        ``"PURLIN"`` are stored as user-defined ``IfcBeam`` types.  Wood is
        shown brown by default unless the house has a default beam color or an
        explicit ``color`` is supplied.
        """
        beam_name = _name(name, "name")
        start_point = _point_3d(start, "start")
        end_point = _point_3d(end, "end")
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly two dimensions")
        try:
            width, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly two dimensions"
            ) from error
        width = _number(width, "size width")
        height = _number(height, "size height")
        if width <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        material_name = _name(material, "material")
        kind = _enum(kind, "kind", _BEAM_KINDS)
        rotation = _number(rotation, "rotation")

        start_vector = np.array(start_point, dtype=float)
        end_vector = np.array(end_point, dtype=float)
        direction = end_vector - start_vector
        length = float(np.linalg.norm(direction))
        if length == 0:
            raise ValueError("beam start and end must be different points")
        local_x = direction / length

        # Project the requested height reference into the plane normal to the
        # beam.  The default keeps ordinary beam sections as upright as their
        # direction permits; roof planes supply their own normal instead.
        supplied_height_axis = height_axis
        reference_height = np.array(
            (0.0, 0.0, 1.0)
            if supplied_height_axis is None
            else _point_3d(supplied_height_axis, "height_axis"),
            dtype=float,
        )
        reference_length = float(np.linalg.norm(reference_height))
        if reference_length <= 1e-9:
            raise ValueError("height_axis must not be a zero vector")
        reference_height /= reference_length
        local_z = reference_height - np.dot(reference_height, local_x) * local_x
        local_z_length = float(np.linalg.norm(local_z))
        if local_z_length < 1e-9:
            if supplied_height_axis is not None:
                raise ValueError("height_axis must not be parallel to the beam")
            fallback = np.array((0.0, 1.0, 0.0), dtype=float)
            local_z = fallback - np.dot(fallback, local_x) * local_x
            local_z_length = float(np.linalg.norm(local_z))
        local_z /= local_z_length
        local_y = np.cross(local_z, local_x)
        local_y /= np.linalg.norm(local_y)

        roll = radians(rotation)
        rolled_y = cos(roll) * local_y + sin(roll) * local_z
        rolled_z = -sin(roll) * local_y + cos(roll) * local_z
        placement = np.eye(4)
        placement[:3, 0] = local_x
        placement[:3, 1] = rolled_y
        placement[:3, 2] = rolled_z
        placement[:3, 3] = start_vector
        normalised_cuts = _plane_cuts(cuts)
        clippings = _local_clippings(
            normalised_cuts,
            placement,
            (length / 2, 0.0, 0.0),
        )

        predefined_type = (
            "USERDEFINED" if kind in {"RAFTER", "PURLIN"} else kind
        )
        model = self.house.model
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcBeam",
            name=beam_name,
            predefined_type=predefined_type,
        )
        if kind in {"RAFTER", "PURLIN"}:
            element.ObjectType = kind
        elif kind == "USERDEFINED":
            element.ObjectType = beam_name
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[element],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=element,
            matrix=placement,
            is_si=True,
        )

        profile = model.createIfcRectangleProfileDef(
            "AREA",
            f"{beam_name} Profile",
            None,
            width,
            height,
        )
        body = ifcopenshell.api.geometry.add_profile_representation(
            model,
            context=self.house._body_context,
            profile=profile,
            depth=length,
            cardinal_point="mid-depth centre",
            placement_zx_axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        )
        _clip_body_representation(model, element, body, clippings)
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=element,
            representation=body,
        )

        resolved_color = color
        if (
            resolved_color is None
            and "beam" not in self.house._default_colors
            and material_name.casefold() == "wood"
        ):
            resolved_color = "#8B5A2B"
        surface_style = self.house._surface_style(
            "beam",
            color=resolved_color,
            transparency=transparency,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        ifc_material = self.house._materials.get(material_name)
        if ifc_material is None:
            ifc_material = ifcopenshell.api.material.add_material(
                model,
                name=material_name,
                category=material_name.casefold(),
            )
            self.house._materials[material_name] = ifc_material
        ifcopenshell.api.material.assign_material(
            model,
            products=[element],
            type="IfcMaterial",
            material=ifc_material,
        )
        common_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=element,
            name="Pset_BeamCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=common_pset,
            properties={"LoadBearing": True},
        )

        return Beam(
            element,
            self,
            start=start_point,
            end=end_point,
            size=(width, height),
            length=length,
            kind=kind,
            material_name=material_name,
            rotation=rotation,
            height_axis=tuple(float(value) for value in reference_height),
            cuts=normalised_cuts,
            placement=placement,
        )

    def furniture(
        self,
        name: str,
        *,
        kind: FurnitureKind,
        size: Sequence[Number],
        center: Point,
        rotation: Number = 0,
        start_height: Number = 0,
        color: str | None = None,
        transparency: Number = 0,
        label: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Add a semantic piece of furniture represented by a simple box.

        ``size`` is ``(width, depth, height)`` in the furniture's local axes.
        ``center`` locates the middle of the box in plan, ``rotation`` is
        counter-clockwise in degrees from global X, and ``start_height`` is
        measured above this storey's elevation.  The plan representation is a
        dashed rectangle with ``label`` centred inside; when omitted, the
        furniture name is used as the label.
        """
        furniture_name = _name(name, "name")
        kind = _enum(kind, "kind", _FURNITURE_KINDS)
        if isinstance(size, (str, bytes)):
            raise TypeError("size must contain exactly three dimensions")
        try:
            width, depth, height = size
        except (TypeError, ValueError) as error:
            raise TypeError(
                "size must contain exactly three dimensions"
            ) from error
        width = _number(width, "size width")
        depth = _number(depth, "size depth")
        height = _number(height, "size height")
        if width <= 0 or depth <= 0 or height <= 0:
            raise ValueError("size dimensions must be greater than zero")
        center_x, center_y = _point(center, "center")
        rotation = _number(rotation, "rotation")
        start_height = _number(start_height, "start_height")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        label_text = furniture_name if label is None else _name(label, "label")
        surface_style = self.house._surface_style(
            "furniture",
            color=color,
            transparency=transparency,
        )

        model = self.house.model
        furniture = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcFurniture",
            name=furniture_name,
            predefined_type=kind,
        )
        if kind == "USERDEFINED":
            furniture.ObjectType = furniture_name
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[furniture],
            relating_structure=self.element,
        )

        angle = radians(rotation)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = center_x
        placement[1, 3] = center_y
        placement[2, 3] = self.elevation + start_height
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=furniture,
            matrix=placement,
            is_si=True,
        )

        half_width = width / 2
        half_depth = depth / 2
        footprint = [
            (-half_width, -half_depth),
            (half_width, -half_depth),
            (half_width, half_depth),
            (-half_width, half_depth),
        ]
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=height,
            polyline=footprint,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=furniture,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        plan = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._plan_body_context,
            axis=[*footprint, footprint[0]],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=furniture,
            representation=plan,
        )

        annotation = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcAnnotation",
            name=f"{furniture_name} Label",
            predefined_type="TEXT",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[annotation],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=annotation,
            matrix=placement.copy(),
            is_si=True,
        )
        literal_origin = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0)),
        )
        literal = model.createIfcTextLiteralWithExtent(
            label_text,
            literal_origin,
            "RIGHT",
            model.createIfcPlanarExtent(width, depth),
            "center",
        )
        label_representation = model.createIfcShapeRepresentation(
            self.house._annotation_context,
            "Annotation",
            "Annotation2D",
            [literal],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=annotation,
            representation=label_representation,
        )
        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=annotation,
            name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"Classes": "furniture-label small"},
        )
        ifcopenshell.api.drawing.assign_product(
            model,
            relating_product=furniture,
            related_object=annotation,
        )
        self.house._plan_annotations.append(annotation)
        for drawing in self.house._drawings:
            if drawing._includes_storey(self):
                ifcopenshell.api.group.assign_group(
                    model,
                    group=drawing.group,
                    products=[annotation],
                )
        return furniture

    def miako_slab(
        self,
        name: str,
        *,
        start: Point,
        end: Point,
        top: Number,
        direction: Point,
        structure: Sequence[MiakoStructureItem],
        block_length: Number = 0.25,
        block_height: Number = 0.19,
        topping: Number = 0.06,
        beam_height: Number | None = None,
        beam_color: str | None = "red",
        wide_color: str | None = "blue",
        narrow_color: str | None = "green",
        concrete_color: str | None = None,
        transparency: Number = 0,
    ) -> MiakoSlab:
        """Create a detailed MIAKO floor slab from a crosswise strip layout.

        ``start`` and ``end`` define the joist span.  ``direction`` must be
        perpendicular to that line and selects the side on which the slab is
        constructed.  Items in ``structure`` are inserted successively in
        that direction: ``"beam"`` is 0.17 m wide, ``"wide"`` is a 0.455 m
        block bay, and ``"narrow"`` is a 0.33 m block bay.  Consequently a
        wide bay plus a beam forms a 0.625 m module and a narrow bay plus a
        beam forms a 0.5 m module.

        ``top`` is measured from this storey's elevation.  Blocks and beams
        terminate beneath the concrete topping, so the whole assembly extends
        downward by ``block_height + topping``.  Repeated components use
        mapped type geometry and are decomposed beneath one semantic
        ``IfcSlab`` contained by this storey.  Beams are red, wide blocks are
        blue, and narrow blocks are green by default; their respective color
        arguments may override these 3D styles.
        """
        slab_name = _name(name, "name")
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        direction_x, direction_y = _point(direction, "direction")
        top = _number(top, "top")
        block_length = _number(block_length, "block_length")
        block_height = _number(block_height, "block_height")
        topping = _number(topping, "topping")
        if beam_height is None:
            beam_height = block_height
        else:
            beam_height = _number(beam_height, "beam_height")
        for value, argument in (
            (block_length, "block_length"),
            (block_height, "block_height"),
            (topping, "topping"),
            (beam_height, "beam_height"),
        ):
            if value <= 0:
                raise ValueError(f"{argument} must be greater than zero")
        if beam_height > block_height:
            raise ValueError("beam_height must not be greater than block_height")

        span_x = end_x - start_x
        span_y = end_y - start_y
        length = hypot(span_x, span_y)
        if length == 0:
            raise ValueError("slab start and end must be different points")
        direction_length = hypot(direction_x, direction_y)
        if direction_length == 0:
            raise ValueError("direction must not be a zero vector")
        span_x /= length
        span_y /= length
        direction_x /= direction_length
        direction_y /= direction_length
        if abs(span_x * direction_x + span_y * direction_y) > 1e-6:
            raise ValueError("direction must be perpendicular to start-end line")

        if isinstance(structure, (str, bytes)):
            raise TypeError("structure must be a sequence of layout items")
        try:
            supplied_structure = list(structure)
        except TypeError as error:
            raise TypeError(
                "structure must be a sequence of layout items"
            ) from error
        if not supplied_structure:
            raise ValueError("structure must contain at least one item")
        normalised_structure: list[str] = []
        previous_was_block = False
        for index, supplied_item in enumerate(supplied_structure, start=1):
            item = _name(supplied_item, f"structure item {index}").lower()
            if item not in _MIAKO_WIDTHS:
                choices = ", ".join(_MIAKO_WIDTHS)
                raise ValueError(
                    f"structure item {index} must be one of: {choices}"
                )
            is_block = item in {"wide", "narrow"}
            if is_block and previous_was_block:
                raise ValueError("MIAKO block bays must be separated by a beam")
            normalised_structure.append(item)
            previous_was_block = is_block
        if "beam" not in normalised_structure:
            raise ValueError("structure must contain at least one beam")
        if not any(item in {"wide", "narrow"} for item in normalised_structure):
            raise ValueError("structure must contain at least one block bay")
        structure_tuple = tuple(normalised_structure)
        width = sum(_MIAKO_WIDTHS[item] for item in structure_tuple)

        beam_style = self.house._surface_style(
            "beam", color=beam_color, transparency=transparency
        )
        wide_style = self.house._surface_style(
            "block", color=wide_color, transparency=transparency
        )
        narrow_style = self.house._surface_style(
            "block", color=narrow_color, transparency=transparency
        )
        concrete_style = self.house._surface_style(
            "slab", color=concrete_color, transparency=transparency
        )

        # Keep +Z upward and the placement right-handed.  The requested
        # direction is represented as a sign along the placement's local Y.
        local_y_x = -span_y
        local_y_y = span_x
        layout_sign = (
            1.0
            if direction_x * local_y_x + direction_y * local_y_y > 0
            else -1.0
        )
        bottom_elevation = self.elevation + top - block_height - topping
        placement = np.eye(4)
        placement[0, 0] = span_x
        placement[1, 0] = span_y
        placement[0, 1] = local_y_x
        placement[1, 1] = local_y_y
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = bottom_elevation

        model = self.house.model
        slab_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=slab_name,
            predefined_type="FLOOR",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[slab_element],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=slab_element,
            matrix=placement,
            is_si=True,
        )

        signed_width = layout_sign * width
        plan = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.house._plan_body_context,
            axis=[
                (0.0, 0.0),
                (length, 0.0),
                (length, signed_width),
                (0.0, signed_width),
                (0.0, 0.0),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=slab_element,
            representation=plan,
        )

        common_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=slab_element,
            name="Pset_SlabCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=common_pset,
            properties={"LoadBearing": True},
        )
        miako_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=slab_element,
            name="BBIM_MiakoSlab",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=miako_pset,
            properties={
                "Structure": ",".join(structure_tuple),
                "SpanLength": length,
                "OverallWidth": width,
                "BlockLength": block_length,
                "BlockHeight": block_height,
                "BeamHeight": beam_height,
                "ToppingThickness": topping,
            },
        )

        def get_material(
            material_name: str,
            category: str,
        ) -> ifcopenshell.entity_instance:
            material = self.house._materials.get(material_name)
            if material is None:
                material = ifcopenshell.api.material.add_material(
                    model,
                    name=material_name,
                    category=category,
                )
                self.house._materials[material_name] = material
            return material

        beam_material = get_material("MIAKO ceramic concrete", "concrete")
        block_material = get_material("MIAKO ceramic", "ceramic")
        concrete_material = get_material("Concrete topping", "concrete")

        def get_component_type(
            *,
            component: Literal["beam", "wide", "narrow"],
            component_length: float,
            component_width: float,
            component_height: float,
            style: ifcopenshell.entity_instance | None,
            material: ifcopenshell.entity_instance,
        ) -> ifcopenshell.entity_instance:
            style_id = style.id() if style is not None else None
            key = (
                component,
                round(component_length, 9),
                round(component_width, 9),
                round(component_height, 9),
                int(layout_sign),
                style_id,
            )
            component_type = self.house._miako_component_types.get(key)
            if component_type is not None:
                return component_type

            if component == "beam":
                type_class = "IfcBeamType"
                predefined_type = "JOIST"
                type_name = (
                    f"MIAKO beam {component_width * 1000:.0f}x"
                    f"{component_height * 1000:.0f}, L={component_length:.3f} m"
                )
            else:
                type_class = "IfcBuildingElementPartType"
                predefined_type = "USERDEFINED"
                type_name = (
                    f"MIAKO {component} block "
                    f"{component_length * 1000:.0f}x"
                    f"{component_width * 1000:.0f}x"
                    f"{component_height * 1000:.0f}"
                )
            component_type = ifcopenshell.api.root.create_entity(
                model,
                ifc_class=type_class,
                name=type_name,
                predefined_type=predefined_type,
            )
            if component != "beam":
                component_type.ElementType = f"MIAKO {component} block"
            signed_component_width = layout_sign * component_width
            representation = ifcopenshell.api.geometry.add_slab_representation(
                model,
                context=self.house._body_context,
                depth=component_height,
                polyline=[
                    (0.0, 0.0),
                    (component_length, 0.0),
                    (component_length, signed_component_width),
                    (0.0, signed_component_width),
                ],
            )
            if style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    model,
                    shape_representation=representation,
                    styles=[style],
                )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=component_type,
                representation=representation,
            )
            ifcopenshell.api.material.assign_material(
                model,
                products=[component_type],
                type="IfcMaterial",
                material=material,
            )
            self.house._miako_component_types[key] = component_type
            return component_type

        def component_placement(
            local_x: float,
            local_y: float,
            local_z: float,
        ) -> np.ndarray:
            result = placement.copy()
            result[:3, 3] = (
                placement
                @ np.array((local_x, local_y, local_z, 1.0), dtype=float)
            )[:3]
            return result

        components: list[ifcopenshell.entity_instance] = []
        component_placements: list[np.ndarray] = []
        beams: list[ifcopenshell.entity_instance] = []
        blocks: list[ifcopenshell.entity_instance] = []
        offset = 0.0
        beam_number = 0
        bay_number = 0
        tolerance = 1e-9
        full_block_count = int(length / block_length)
        remainder = length - full_block_count * block_length
        if remainder < tolerance:
            remainder = 0.0
        elif block_length - remainder < tolerance:
            full_block_count += 1
            remainder = 0.0

        for item in structure_tuple:
            item_width = _MIAKO_WIDTHS[item]
            signed_offset = layout_sign * offset
            if item == "beam":
                beam_number += 1
                beam = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcBeam",
                    name=f"{slab_name} Beam {beam_number}",
                    predefined_type="JOIST",
                )
                beam_type = get_component_type(
                    component="beam",
                    component_length=length,
                    component_width=item_width,
                    component_height=beam_height,
                    style=beam_style,
                    material=beam_material,
                )
                ifcopenshell.api.type.assign_type(
                    model,
                    related_objects=[beam],
                    relating_type=beam_type,
                )
                beams.append(beam)
                components.append(beam)
                component_placements.append(
                    component_placement(
                        0.0,
                        signed_offset,
                        block_height - beam_height,
                    )
                )
            else:
                bay_number += 1
                block_lengths = [block_length] * full_block_count
                if remainder:
                    block_lengths.append(remainder)
                along = 0.0
                for block_number, current_length in enumerate(
                    block_lengths,
                    start=1,
                ):
                    block = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcBuildingElementPart",
                        name=(
                            f"{slab_name} {item.title()} Block "
                            f"{bay_number}.{block_number}"
                        ),
                        predefined_type="USERDEFINED",
                    )
                    block.ObjectType = f"MIAKO {item} block"
                    block_type = get_component_type(
                        component=item,
                        component_length=current_length,
                        component_width=item_width,
                        component_height=block_height,
                        style=wide_style if item == "wide" else narrow_style,
                        material=block_material,
                    )
                    ifcopenshell.api.type.assign_type(
                        model,
                        related_objects=[block],
                        relating_type=block_type,
                    )
                    blocks.append(block)
                    components.append(block)
                    component_placements.append(
                        component_placement(along, signed_offset, 0.0)
                    )
                    along += current_length
            offset += item_width

        topping_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcBuildingElementPart",
            name=f"{slab_name} Concrete Topping",
            predefined_type="USERDEFINED",
        )
        topping_element.ObjectType = "Concrete topping"
        topping_representation = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=topping,
            polyline=[
                (0.0, 0.0),
                (length, 0.0),
                (length, signed_width),
                (0.0, signed_width),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=topping_element,
            representation=topping_representation,
        )
        if concrete_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=topping_representation,
                styles=[concrete_style],
            )
        ifcopenshell.api.material.assign_material(
            model,
            products=[topping_element],
            type="IfcMaterial",
            material=concrete_material,
        )
        components.append(topping_element)
        component_placements.append(
            component_placement(0.0, 0.0, block_height)
        )

        ifcopenshell.api.aggregate.assign_object(
            model,
            products=components,
            relating_object=slab_element,
        )
        for component, component_matrix in zip(
            components,
            component_placements,
        ):
            ifcopenshell.api.geometry.edit_object_placement(
                model,
                product=component,
                matrix=component_matrix,
                is_si=True,
            )

        return MiakoSlab(
            slab_element,
            self,
            start=(start_x, start_y),
            end=(end_x, end_y),
            direction=(direction_x, direction_y),
            structure=structure_tuple,
            length=length,
            width=width,
            top=top,
            block_length=block_length,
            block_height=block_height,
            beam_height=beam_height,
            topping=topping,
            placement=placement,
            beams=tuple(beams),
            blocks=tuple(blocks),
            topping_element=topping_element,
        )

    def chimney(
        self,
        center: Point,
        *,
        size: Number,
        height: Number,
        flue_diameter: Number,
        start_height: Number = 0,
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Chimney:
        """Create a square chimney with a central circular flue void.

        ``center`` locates the stack in plan, ``size`` is its outside side
        length, and ``height`` is its vertical extent.  ``start_height`` is
        measured above this storey's elevation.  ``color`` and
        ``transparency`` affect only the 3D body.
        """
        center_x, center_y = _point(center, "center")
        size = _number(size, "size")
        height = _number(height, "height")
        flue_diameter = _number(flue_diameter, "flue_diameter")
        start_height = _number(start_height, "start_height")
        if size <= 0:
            raise ValueError("size must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if flue_diameter <= 0:
            raise ValueError("flue_diameter must be greater than zero")
        if flue_diameter >= size:
            raise ValueError("flue_diameter must be smaller than size")
        surface_style = self.house._surface_style(
            "chimney",
            color=color,
            transparency=transparency,
        )

        self._chimney_count += 1
        chimney_name = (
            _name(name, "name")
            if name is not None
            else f"Chimney {self._chimney_count}"
        )
        model = self.house.model
        chimney_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcChimney",
            name=chimney_name,
            predefined_type="NOTDEFINED",
        )
        placement = np.eye(4)
        placement[0, 3] = center_x
        placement[1, 3] = center_y
        placement[2, 3] = self.elevation + start_height
        chimney = Chimney(
            chimney_element,
            self,
            center=(center_x, center_y),
            size=size,
            height=height,
            flue_diameter=flue_diameter,
            start_height=start_height,
            placement=placement,
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[chimney],
            relating_structure=self.element,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=chimney,
            matrix=placement,
            is_si=True,
        )

        half_size = size / 2
        outer_points = model.createIfcCartesianPointList2D(
            [
                (-half_size, -half_size),
                (half_size, -half_size),
                (half_size, half_size),
                (-half_size, half_size),
                (-half_size, -half_size),
            ]
        )
        outer_curve = model.createIfcIndexedPolyCurve(
            outer_points,
            None,
            False,
        )
        flue_position = model.createIfcAxis2Placement2D(
            model.createIfcCartesianPoint((0.0, 0.0)),
            model.createIfcDirection((1.0, 0.0)),
        )
        flue_curve = model.createIfcCircle(flue_position, flue_diameter / 2)
        profile = model.createIfcArbitraryProfileDefWithVoids(
            "AREA",
            f"{chimney_name} Profile",
            outer_curve,
            [flue_curve],
        )
        body = ifcopenshell.api.geometry.add_profile_representation(
            model,
            context=self.house._body_context,
            profile=profile,
            depth=height,
            cardinal_point=None,
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=chimney,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=chimney,
            name="Pset_ChimneyCommon",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={"NumberOfDrafts": 1},
        )
        return chimney

    def stair_landing(
        self,
        start: Point,
        end: Point,
        *,
        height: Number,
        thickness: Number,
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> ifcopenshell.entity_instance:
        """Create a rectangular stair landing between two opposite corners.

        ``height`` is the coordinate of the landing's top surface measured
        above this storey's elevation.  The slab extends downward by
        ``thickness``.  ``color`` and ``transparency`` affect only its 3D body.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        height = _number(height, "height")
        thickness = _number(thickness, "thickness")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        min_x, max_x = sorted((start_x, end_x))
        min_y, max_y = sorted((start_y, end_y))
        width = max_x - min_x
        depth = max_y - min_y
        if width == 0 or depth == 0:
            raise ValueError("landing corners must define a rectangle")
        surface_style = self.house._surface_style(
            "stair",
            color=color,
            transparency=transparency,
        )

        self._landing_count += 1
        landing_name = (
            _name(name, "name")
            if name is not None
            else f"Stair Landing {self._landing_count}"
        )
        model = self.house.model
        landing = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcSlab",
            name=landing_name,
            predefined_type="LANDING",
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[landing],
            relating_structure=self.element,
        )
        placement = np.eye(4)
        placement[0, 3] = min_x
        placement[1, 3] = min_y
        placement[2, 3] = self.elevation + height - thickness
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=landing,
            matrix=placement,
            is_si=True,
        )
        body = ifcopenshell.api.geometry.add_slab_representation(
            model,
            context=self.house._body_context,
            depth=thickness,
            polyline=[
                (0.0, 0.0),
                (width, 0.0),
                (width, depth),
                (0.0, depth),
            ],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=landing,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )
        return landing

    def stair(
        self,
        start: Point,
        end: Point,
        *,
        width: Number,
        height: Number,
        risers: int,
        start_height: Number = 0,
        underside: Literal["solid", "sloped"] = "solid",
        waist_thickness: Number = 0.15,
        name: str | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Stair:
        """Create a semantic straight stair rising from ``start`` to ``end``.

        The points define the centre line of the horizontal run, with ``start``
        at the bottom and ``end`` at the upper landing edge.  ``start_height``
        is measured above this storey's elevation and defaults to zero.  The
        stair is centred on its plan line.  Its tread count is one less than
        ``risers``; riser height and tread length are calculated from the total
        rise ``height`` and horizontal run.  The returned stair exposes its
        calculated ``end_height`` for chaining another flight.  ``color`` and
        ``transparency`` affect only its 3D flight body.  Set ``underside`` to
        ``"sloped"`` to leave the space beneath the flight open;
        ``waist_thickness`` is the perpendicular structural thickness between
        the stair pitch line and its planar underside.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        width = _number(width, "width")
        height = _number(height, "height")
        start_height = _number(start_height, "start_height")
        if not isinstance(underside, str):
            raise TypeError("underside must be 'solid' or 'sloped'")
        if underside not in {"solid", "sloped"}:
            raise ValueError("underside must be 'solid' or 'sloped'")
        waist_thickness = _number(waist_thickness, "waist_thickness")
        if width <= 0:
            raise ValueError("width must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if waist_thickness <= 0:
            raise ValueError("waist_thickness must be greater than zero")
        if isinstance(risers, bool) or not isinstance(risers, int):
            raise TypeError("risers must be an integer")
        if risers < 2:
            raise ValueError("risers must be at least 2")

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("stair start and end must be different points")
        treads = risers - 1
        riser_height = height / risers
        tread_length = length / treads
        stepped_rise = treads * riser_height
        pitch_cosine = length / hypot(length, stepped_rise)
        underside_vertical_offset = waist_thickness / pitch_cosine
        if underside == "sloped" and underside_vertical_offset >= stepped_rise:
            raise ValueError("waist_thickness is too large for the stair flight")
        surface_style = self.house._surface_style(
            "stair",
            color=color,
            transparency=transparency,
        )

        self._stair_count += 1
        stair_name = (
            _name(name, "name")
            if name is not None
            else f"Stair {self._stair_count}"
        )
        model = self.house.model
        stair_element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcStair",
            name=stair_name,
            predefined_type="STRAIGHT_RUN_STAIR",
        )
        flight = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcStairFlight",
            name=f"{stair_name} Flight",
            predefined_type="STRAIGHT",
        )
        flight.NumberOfRisers = risers
        flight.NumberOfTreads = treads
        flight.RiserHeight = riser_height
        flight.TreadLength = tread_length

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation + start_height
        stair = Stair(
            stair_element,
            self,
            flight=flight,
            start=(start_x, start_y),
            end=(end_x, end_y),
            length=length,
            width=width,
            height=height,
            start_height=start_height,
            risers=risers,
            treads=treads,
            riser_height=riser_height,
            tread_length=tread_length,
            underside=underside,
            waist_thickness=(
                waist_thickness if underside == "sloped" else None
            ),
            placement=placement,
        )
        ifcopenshell.api.spatial.assign_container(
            model,
            products=[stair],
            relating_structure=self.element,
        )
        ifcopenshell.api.aggregate.assign_object(
            model,
            products=[flight],
            relating_object=stair,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=stair,
            matrix=placement,
            is_si=True,
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model,
            product=flight,
            matrix=placement,
            is_si=True,
        )

        # Build one closed stepped solid.  A sloped underside is parallel to
        # the stair pitch line and clipped at the flight's starting elevation,
        # leaving a short solid bearing at the bottom.  The final riser is a
        # separate face: the upper storey floor acts as the landing instead of
        # another tread.
        profile: list[tuple[float, float]] = [(0.0, 0.0)]
        if underside == "sloped":
            underside_end_z = stepped_rise - underside_vertical_offset
            underside_start_x = (
                underside_vertical_offset * length / stepped_rise
            )
            profile.extend(
                [
                    (underside_start_x, 0.0),
                    (length, underside_end_z),
                ]
            )
        else:
            profile.append((length, 0.0))
        profile.append((length, stepped_rise))
        for tread in range(treads, 0, -1):
            x = (tread - 1) * tread_length
            profile.append((x, tread * riser_height))
            if tread > 1:
                profile.append((x, (tread - 1) * riser_height))

        half_width = width / 2
        vertices = [
            (x, -half_width, z)
            for x, z in profile
        ] + [
            (x, half_width, z)
            for x, z in profile
        ]
        profile_size = len(profile)
        faces: list[tuple[int, ...]] = [
            tuple(reversed(range(profile_size))),
            tuple(range(profile_size, 2 * profile_size)),
        ]
        for index in range(profile_size):
            next_index = (index + 1) % profile_size
            faces.append(
                (
                    index,
                    next_index,
                    next_index + profile_size,
                    index + profile_size,
                )
            )
        final_riser_depth = min(tread_length * 0.025, 0.005)
        final_riser_x = length - final_riser_depth
        final_riser_z = treads * riser_height
        final_riser_vertices = [
            (final_riser_x, -half_width, final_riser_z),
            (length, -half_width, final_riser_z),
            (length, half_width, final_riser_z),
            (final_riser_x, half_width, final_riser_z),
            (final_riser_x, -half_width, height),
            (length, -half_width, height),
            (length, half_width, height),
            (final_riser_x, half_width, height),
        ]
        final_riser_start = len(vertices)
        vertices.extend(final_riser_vertices)
        faces.extend(
            [
                tuple(final_riser_start + index for index in (1, 2, 3, 0)),
                tuple(final_riser_start + index for index in (7, 6, 5, 4)),
                tuple(final_riser_start + index for index in (4, 5, 1, 0)),
                tuple(final_riser_start + index for index in (5, 6, 2, 1)),
                tuple(final_riser_start + index for index in (6, 7, 3, 2)),
                tuple(final_riser_start + index for index in (7, 4, 0, 3)),
            ]
        )
        body = ifcopenshell.api.geometry.add_mesh_representation(
            model,
            context=self.house._body_context,
            vertices=[vertices],
            faces=[faces],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=flight,
            representation=body,
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=body,
                styles=[surface_style],
            )

        pset = ifcopenshell.api.pset.add_pset(
            model,
            product=flight,
            name="Pset_StairFlightCommon",
        )
        pset_properties = {
            "NumberOfRiser": risers,
            "NumberOfTreads": treads,
            "RiserHeight": riser_height,
            "TreadLength": tread_length,
        }
        if underside == "sloped":
            pset_properties["WaistThickness"] = waist_thickness
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties=pset_properties,
        )
        return stair

    def wall(
        self,
        start: Point,
        end: Point,
        *,
        thickness: Number | None = None,
        height: Number,
        start_height: Number = 0,
        wall_type: ifcopenshell.entity_instance | None = None,
        cuts: Sequence[WallCut] | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Wall:
        """Create a straight wall whose axis runs from ``start`` to ``end``.

        Points, thickness and height are in metres.  ``start_height`` is the
        wall bottom above this storey's elevation and ``height`` is its
        vertical extent.  Supply either a direct ``thickness`` or a reusable
        ``wall_type`` created by :meth:`House.wall_type`.  Direct-thickness
        walls are centred on their axis; layered walls use their type's
        optional ``"axis"`` marker.
        Each item in ``cuts`` contains three world-coordinate points defining
        an infinite clipping plane.  Point order does not matter: the side
        containing the original wall centre is retained and the opposite
        half-space is removed.  Multiple planes are applied cumulatively.
        ``color`` and ``transparency`` affect only the 3D body.
        """
        start_x, start_y = _point(start, "start")
        end_x, end_y = _point(end, "end")
        if thickness is None and wall_type is None:
            raise ValueError("either thickness or wall_type must be supplied")
        if thickness is not None and wall_type is not None:
            raise ValueError("thickness and wall_type must not both be supplied")
        body_offset: float
        usage_offset: float
        if wall_type is not None:
            is_wall_type = isinstance(
                wall_type, ifcopenshell.entity_instance
            ) and wall_type.is_a("IfcWallType")
            if not is_wall_type:
                raise TypeError("wall_type must be an IfcWallType")
            if wall_type.file is not self.house.model:
                raise ValueError("wall_type must belong to this house")
            layer_set = ifcopenshell.util.element.get_material(wall_type)
            if not layer_set or not layer_set.is_a("IfcMaterialLayerSet"):
                raise ValueError("wall_type must have an IfcMaterialLayerSet")
            thickness = sum(layer.LayerThickness for layer in layer_set.MaterialLayers)
            body_offset, usage_offset = self.house._wall_type_layouts.get(
                wall_type.id(), (-thickness / 2, thickness / 2)
            )
        else:
            thickness = _number(thickness, "thickness")
            body_offset = -thickness / 2
            usage_offset = thickness / 2
        height = _number(height, "height")
        start_height = _number(start_height, "start_height")
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
        if start_height < 0:
            raise ValueError("start_height must be zero or greater")
        transparency = _number(transparency, "transparency")
        if not 0 <= transparency <= 1:
            raise ValueError("transparency must be between 0 and 1")

        if color is None and transparency == 0 and wall_type is not None:
            surface_style = self.house._wall_type_styles.get(wall_type.id())
        else:
            surface_style = self.house._surface_style(
                "wall",
                color=color,
                transparency=transparency,
            )

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("wall start and end must be different points")

        angle = atan2(delta_y, delta_x)
        placement = np.eye(4)
        placement[0, 0] = cos(angle)
        placement[0, 1] = -sin(angle)
        placement[1, 0] = sin(angle)
        placement[1, 1] = cos(angle)
        placement[0, 3] = start_x
        placement[1, 3] = start_y
        placement[2, 3] = self.elevation + start_height

        if cuts is None:
            supplied_cuts: list[WallCut] = []
        else:
            if isinstance(cuts, (str, bytes)):
                raise TypeError("cuts must be a sequence of three-point planes")
            try:
                supplied_cuts = list(cuts)
            except TypeError as error:
                raise TypeError(
                    "cuts must be a sequence of three-point planes"
                ) from error

        normalised_cuts: list[WallCut] = []
        clippings: list[dict[str, tuple[float, float, float]]] = []
        world_to_local = np.linalg.inv(placement)
        wall_centre = np.array(
            (length / 2, body_offset + thickness / 2, height / 2),
            dtype=float,
        )
        for cut_index, supplied_cut in enumerate(supplied_cuts, start=1):
            if isinstance(supplied_cut, (str, bytes)):
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                )
            try:
                supplied_points = list(supplied_cut)
            except TypeError as error:
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                ) from error
            if len(supplied_points) != 3:
                raise TypeError(
                    f"cut {cut_index} must contain exactly three points"
                )
            world_points = tuple(
                _point_3d(point, f"cut {cut_index} point {point_index}")
                for point_index, point in enumerate(supplied_points, start=1)
            )
            local_points = [
                (
                    world_to_local
                    @ np.array((*point, 1.0), dtype=float)
                )[:3]
                for point in world_points
            ]
            normal = np.cross(
                local_points[1] - local_points[0],
                local_points[2] - local_points[0],
            )
            normal_length = float(np.linalg.norm(normal))
            if normal_length <= 1e-9:
                raise ValueError(f"cut {cut_index} points must not be collinear")
            normal /= normal_length
            centre_side = float(
                np.dot(normal, wall_centre - local_points[0])
            )
            if abs(centre_side) <= 1e-9:
                raise ValueError(
                    f"cut {cut_index} passes through the wall centre; "
                    "the retained side is ambiguous"
                )
            # If the normal points at the centre, reverse it.  IfcOpenShell's
            # clipping normal points into removed rather than retained matter.
            if centre_side > 0:
                normal *= -1
            normalised_cuts.append(world_points)
            clippings.append(
                {
                    "location": tuple(float(value) for value in local_points[0]),
                    "normal": tuple(float(value) for value in normal),
                }
            )

        self._wall_count += 1
        wall_element = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcWall",
            name=f"Wall {self._wall_count}",
        )
        wall = Wall(
            wall_element,
            self,
            start=(start_x, start_y),
            end=(end_x, end_y),
            length=length,
            height=height,
            start_height=start_height,
            thickness=thickness,
            body_offset=body_offset,
            surface_style=surface_style,
            cuts=tuple(normalised_cuts),
        )
        ifcopenshell.api.spatial.assign_container(
            self.house.model, products=[wall], relating_structure=self.element
        )
        if wall_type is not None:
            ifcopenshell.api.type.assign_type(
                self.house.model,
                related_objects=[wall],
                relating_type=wall_type,
            )
            material_relationship = ifcopenshell.api.material.assign_material(
                self.house.model,
                products=[wall],
                type="IfcMaterialLayerSetUsage",
            )
            usage = material_relationship.RelatingMaterial
            ifcopenshell.api.material.edit_layer_usage(
                self.house.model,
                usage=usage,
                attributes={
                    "DirectionSense": "NEGATIVE",
                    "OffsetFromReferenceLine": usage_offset,
                },
            )

        ifcopenshell.api.geometry.edit_object_placement(
            self.house.model,
            product=wall,
            matrix=placement,
            is_si=True,
        )

        body = ifcopenshell.api.geometry.add_wall_representation(
            self.house.model,
            context=self.house._body_context,
            length=length,
            height=height,
            thickness=thickness,
            offset=body_offset,
        )
        if clippings:
            item = body.Items[0]
            clipping_ids: list[int] = []
            for clipping in clippings:
                item = ifcopenshell.api.geometry.clip_solid(
                    self.house.model,
                    item=item,
                    location=clipping["location"],
                    normal=clipping["normal"],
                )
                clipping_ids.append(item.id())
            body.Items = [item]
            body.RepresentationType = "Clipping"
            boolean_pset = ifcopenshell.api.pset.add_pset(
                self.house.model,
                product=wall,
                name="BBIM_Boolean",
            )
            ifcopenshell.api.pset.edit_pset(
                self.house.model,
                pset=boolean_pset,
                properties={"Data": json.dumps(clipping_ids)},
            )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model, product=wall, representation=body
        )
        if surface_style is not None:
            ifcopenshell.api.style.assign_representation_styles(
                self.house.model,
                shape_representation=body,
                styles=[surface_style],
            )

        axis = ifcopenshell.api.geometry.add_axis_representation(
            self.house.model,
            context=self.house._axis_context,
            axis=[(0.0, 0.0), (length, 0.0)],
        )
        ifcopenshell.api.geometry.assign_representation(
            self.house.model, product=wall, representation=axis
        )
        return wall

    def connect_wall(
        self,
        wall_1: ifcopenshell.entity_instance,
        wall_2: ifcopenshell.entity_instance,
        *,
        is_atpath: bool = False,
    ) -> ifcopenshell.entity_instance:
        """Connect two layered walls and regenerate their joined bodies.

        By default, the nearest end of each wall is joined, which produces an
        L-shaped mitre for two equally prioritised layers.  Set ``is_atpath``
        to true when the end of ``wall_1`` should terminate along the path of
        ``wall_2``, such as at a T-junction.
        """
        if wall_1 == wall_2:
            raise ValueError("a wall cannot be connected to itself")
        if not isinstance(is_atpath, bool):
            raise TypeError("is_atpath must be a boolean")

        for wall, argument in ((wall_1, "wall_1"), (wall_2, "wall_2")):
            is_wall = isinstance(
                wall, ifcopenshell.entity_instance
            ) and wall.is_a("IfcWall")
            if not is_wall:
                raise TypeError(f"{argument} must be an IfcWall")
            if wall.file is not self.house.model:
                raise ValueError(f"{argument} must belong to this house")
            container = ifcopenshell.util.element.get_container(
                wall,
                ifc_class="IfcBuildingStorey",
            )
            if container != self.element:
                raise ValueError(f"{argument} must belong to this storey")
            usage = ifcopenshell.util.element.get_material(wall)
            if not usage or not usage.is_a("IfcMaterialLayerSetUsage"):
                raise ValueError(
                    f"{argument} must use an IfcMaterialLayerSetUsage"
                )

        connection = ifcopenshell.api.geometry.connect_wall(
            self.house.model,
            wall_1,
            wall_2,
            is_atpath=is_atpath,
        )
        if connection is None:
            raise ValueError("wall axes must intersect")

        for wall in (wall_1, wall_2):
            representation = (
                ifcopenshell.api.geometry.regenerate_wall_representation(
                    self.house.model,
                    wall,
                )
            )
            if representation is None:
                raise ValueError("wall body could not be regenerated")
            surface_style = wall.surface_style if isinstance(wall, Wall) else None
            if surface_style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    self.house.model,
                    shape_representation=representation,
                    styles=[surface_style],
                )
        return connection
