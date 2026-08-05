"""Minimal helpers for describing a house as an IFC model.

The public API uses metres and a conventional right-handed coordinate system:
X and Y lie in the floor plane and Z points upwards.  A wall's axis follows the
line between its two supplied points, and its construction is positioned
relative to that axis.
"""

from __future__ import annotations

from math import atan2, cos, hypot, isfinite, sin
from os import PathLike
from pathlib import Path
import shutil
import subprocess
from typing import Literal, Sequence, TypeAlias

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.type
import ifcopenshell.api.unit
import ifcopenshell.util.element
import numpy as np


__all__ = ["House", "Storey", "generate_plan"]

Number: TypeAlias = int | float
Point: TypeAlias = tuple[Number, Number]
Layer: TypeAlias = tuple[str, Number]
LayerItem: TypeAlias = Layer | Literal["axis"]


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


class House:
    """An IFC project containing one site and one building.

    All public coordinates and dimensions are expressed in metres.  The
    underlying IFC file also uses metres, which keeps generated values easy to
    inspect while remaining compatible with IFC viewers such as Bonsai.
    """

    def __init__(self, name: str) -> None:
        self.name = _name(name, "name")
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
        self._materials: dict[str, ifcopenshell.entity_instance] = {}
        self._wall_type_layouts: dict[int, tuple[float, float]] = {}
        self._ifc_path: Path | None = None

    def wall_type(
        self,
        name: str,
        *,
        layers: Sequence[LayerItem],
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
        return wall_type

    def storey(self, name: str, *, elevation: Number) -> Storey:
        """Create and return a building storey at ``elevation`` metres."""
        storey = Storey(self, _name(name, "name"), _number(elevation, "elevation"))
        self._storeys.append(storey)
        return storey

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
    ) -> ifcopenshell.entity_instance:
        """Create a straight wall whose axis runs from ``start`` to ``end``.

        Points, thickness and height are in metres.  The wall starts at this
        storey's elevation and extends upwards.  Supply either a direct
        ``thickness`` or a reusable ``wall_type`` created by
        :meth:`House.wall_type`.  Direct-thickness walls are centred on their
        axis; layered walls use their type's optional ``"axis"`` marker.
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

        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = hypot(delta_x, delta_y)
        if length == 0:
            raise ValueError("wall start and end must be different points")

        self._wall_count += 1
        wall = ifcopenshell.api.root.create_entity(
            self.house.model,
            ifc_class="IfcWall",
            name=f"Wall {self._wall_count}",
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
        return connection
