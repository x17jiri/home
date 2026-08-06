"""Minimal helpers for describing a house as an IFC model.

The public API uses metres and a conventional right-handed coordinate system:
X and Y lie in the floor plane and Z points upwards.  A wall's axis follows the
line between its two supplied points, and its construction is positioned
relative to that axis.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import atan2, cos, hypot, isfinite, radians, sin
from os import PathLike
from pathlib import Path
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
from ifcopenshell.util.shape_builder import ShapeBuilder
import numpy as np


__all__ = [
    "Chimney",
    "Drawing",
    "House",
    "MiakoSlab",
    "Stair",
    "Storey",
    "Wall",
    "generate_plan",
]

Number: TypeAlias = int | float
Point: TypeAlias = tuple[Number, Number]
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
    ) -> Drawing:
        """Add a persisted square plan drawing to this IFC model."""
        drawing_name = _name(name, "name")
        if any(drawing.name == drawing_name for drawing in self._drawings):
            raise ValueError(f'drawing name already exists: "{drawing_name}"')
        drawing = Drawing(self, drawing_name, x=x, y=y, z=z, radius=radius)
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
        self._annotated_stairs: set[int] = set()
        self._annotated_chimneys: set[int] = set()

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
        if house._plan_annotations:
            ifcopenshell.api.group.assign_group(
                model,
                group=self.group,
                products=house._plan_annotations,
            )

        project_dir = Path(__file__).resolve().parent
        drawing_assets = project_dir / "drawings" / "assets"
        self._drawing_pset = ifcopenshell.api.pset.add_pset(
            model,
            product=self.element,
            name="EPset_Drawing",
        )
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=self._drawing_pset,
            properties={
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
            },
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
        thickness: float,
        body_offset: float,
        surface_style: ifcopenshell.entity_instance | None,
    ) -> None:
        super().__init__(element.wrapped_data, element.file)
        object.__setattr__(self, "storey", storey)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "body_offset", body_offset)
        object.__setattr__(self, "surface_style", surface_style)
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

        opening_end = opening_start + width
        opening_top = sill_height + height
        tolerance = 1e-9
        if opening_start < -tolerance or opening_end > self.length + tolerance:
            raise ValueError("opening must fit within the wall length")
        if opening_top > self.height + tolerance:
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
    ) -> ifcopenshell.entity_instance:
        """Add plan-only dashed linework for the wall above a door opening."""
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
        wall_centre = self.body_offset + self.thickness / 2
        representation = ifcopenshell.api.geometry.add_axis_representation(
            model,
            context=self.storey.house._annotation_context,
            axis=[(0.0, wall_centre), (opening_width, wall_centre)],
        )
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
            properties={"Classes": "dashed"},
        )
        house = self.storey.house
        house._plan_annotations.append(annotation)
        for drawing in house._drawings:
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
        wall_type: ifcopenshell.entity_instance | None = None,
        color: str | None = None,
        transparency: Number = 0,
    ) -> Wall:
        """Create a straight wall whose axis runs from ``start`` to ``end``.

        Points, thickness and height are in metres.  The wall starts at this
        storey's elevation and extends upwards.  Supply either a direct
        ``thickness`` or a reusable ``wall_type`` created by
        :meth:`House.wall_type`.  Direct-thickness walls are centred on their
        axis; layered walls use their type's optional ``"axis"`` marker.
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
        if thickness <= 0:
            raise ValueError("thickness must be greater than zero")
        if height <= 0:
            raise ValueError("height must be greater than zero")
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
            thickness=thickness,
            body_offset=body_offset,
            surface_style=surface_style,
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
            containers = wall.ContainedInStructure
            if not containers or containers[0].RelatingStructure != self.element:
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
