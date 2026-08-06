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
import numpy as np


__all__ = ["Drawing", "House", "Storey", "Wall", "generate_plan"]

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
        allowed_colors = {"wall", "door", "window"}
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
        self._ifc_path: Path | None = None

    def _surface_style(
        self,
        category: Literal["wall", "door", "window"],
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
        line.
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
            name=f"{name} Opening",
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
        if operation.startswith("DOUBLE_DOOR"):
            half = len(items) // 2
            _rotate_items_about_z(
                model,
                items[:half],
                angle=open_angle,
                pivot=(panel_offset_x, pivot_y),
            )
            _rotate_items_about_z(
                model,
                items[half:],
                angle=-open_angle,
                pivot=(width - panel_offset_x, pivot_y),
            )
        else:
            is_left_hinged = operation.endswith("LEFT")
            _rotate_items_about_z(
                model,
                items,
                angle=open_angle if is_left_hinged else -open_angle,
                pivot=(
                    panel_offset_x if is_left_hinged else width - panel_offset_x,
                    pivot_y,
                ),
            )

    def add_door(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        opening_width: Number | None = None,
        opening_height: Number | None = None,
        operation: DoorOperation = "SINGLE_SWING_LEFT",
        open_angle: Number = 45,
        show_overhead: bool = True,
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a door opening in this wall.

        ``at`` is the start of the rough opening measured from the wall start.
        The actual door is centred horizontally in ``opening_width`` and its
        bottom remains at the storey elevation.  Opening dimensions default
        to the door dimensions.  ``open_angle`` rotates only the 3D leaf;
        ``show_overhead`` adds dashed plan-only wall linework across the rough
        opening.  ``color`` and ``transparency`` affect only the 3D body.
        """
        operation = _enum(operation, "operation", _DOOR_OPERATIONS)
        open_angle = _number(open_angle, "open_angle")
        if not 0 <= open_angle <= 180:
            raise ValueError("open_angle must be between 0 and 180 degrees")
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
                sill_height=0,
            )
        )
        door_start = opening_start + (opening_width - width) / 2
        filling_placement = self._placement(door_start, 0)
        self.storey._door_count += 1
        door_name = (
            _name(name, "name")
            if name is not None
            else f"Door {self.storey._door_count}"
        )
        opening = self._create_opening(
            name=door_name,
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
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=door,
                representation=plan_representation,
            )
        self._place_filling(door, opening, filling_placement)
        self._openings.append(
            (opening_start, opening_start + opening_width, 0.0, opening_height)
        )
        if show_overhead:
            self._add_dashed_overhead_line(
                name=door_name,
                opening_start=opening_start,
                opening_width=opening_width,
            )
        return door

    def add_window(
        self,
        *,
        at: Number,
        width: Number,
        height: Number,
        sill_height: Number,
        partition: WindowPartition = "SINGLE_PANEL",
        color: str | None = None,
        transparency: Number = 0,
        name: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cut and fill a window opening in this wall.

        ``at`` is the opening start measured from the wall start and
        ``sill_height`` and ``height`` are the bottom and top coordinates
        measured above the storey elevation.  ``color`` and ``transparency``
        affect only the 3D body.
        """
        partition = _enum(partition, "partition", _WINDOW_PARTITIONS)
        surface_style = self.storey.house._surface_style(
            "window",
            color=color,
            transparency=transparency,
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
            name=window_name,
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
        lining_properties = {
            "LiningDepth": self.thickness,
            "LiningOffset": self.body_offset,
        }
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
            )
            ifcopenshell.api.geometry.assign_representation(
                model,
                product=window,
                representation=representation,
            )
            if context == self.storey.house._body_context and surface_style is not None:
                ifcopenshell.api.style.assign_representation_styles(
                    model,
                    shape_representation=representation,
                    styles=[surface_style],
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
        self._door_count = 0
        self._window_count = 0

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
