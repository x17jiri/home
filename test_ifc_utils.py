import unittest
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.shape

from ifc_utils import House, Wall, generate_plan


class HouseTests(unittest.TestCase):
    def test_connects_and_mitres_two_layered_walls(self) -> None:
        house = House("My house")
        wall_type = house.wall_type(
            "Brick and rock wool",
            layers=[
                ("Brick", 0.12),
                "axis",
                ("Rock wool", 0.10),
            ],
        )
        ground = house.storey("Ground floor", elevation=0)
        wall_1 = ground.wall(
            (4, 0), (4, 5), wall_type=wall_type, height=2.8
        )
        wall_2 = ground.wall(
            (4, 5), (-11, 5), wall_type=wall_type, height=2.8
        )

        connection = ground.connect_wall(wall_1, wall_2)

        self.assertTrue(connection.is_a("IfcRelConnectsPathElements"))
        self.assertEqual(connection.RelatingElement, wall_1)
        self.assertEqual(connection.RelatedElement, wall_2)
        self.assertEqual(connection.RelatingConnectionType, "ATEND")
        self.assertEqual(connection.RelatedConnectionType, "ATSTART")

        profiles = []
        for wall in (wall_1, wall_2):
            body = ifcopenshell.util.representation.get_representation(
                wall, "Model", "Body", "MODEL_VIEW"
            )
            self.assertEqual(body.RepresentationType, "SweptSolid")
            profiles.append(body.Items[0].SweptArea.OuterCurve.Points.CoordList)

        wall_1_profile, wall_2_profile = profiles
        self.assertNotAlmostEqual(wall_1_profile[-2][0], wall_1_profile[-1][0])
        self.assertNotAlmostEqual(wall_2_profile[0][0], wall_2_profile[1][0])
        for profile in profiles:
            ordinates = {round(point[1], 8) for point in profile}
            self.assertEqual(ordinates, {-0.10, 0.12})

    def test_creates_reusable_layered_wall_type(self) -> None:
        house = House("My house")
        exterior_wall = house.wall_type(
            "Brick and rock wool",
            layers=[
                ("Brick", 0.12),
                "axis",
                ("Rock wool", 0.10),
            ],
        )
        ground = house.storey("Ground floor", elevation=0)
        wall_1 = ground.wall(
            (0, 0), (4, 0), wall_type=exterior_wall, height=2.8
        )
        wall_2 = ground.wall(
            (4, 0), (4, 5), wall_type=exterior_wall, height=2.8
        )

        self.assertTrue(exterior_wall.is_a("IfcWallType"))
        layer_set = ifcopenshell.util.element.get_material(exterior_wall)
        self.assertTrue(layer_set.is_a("IfcMaterialLayerSet"))
        self.assertEqual(
            [layer.Material.Name for layer in layer_set.MaterialLayers],
            ["Brick", "Rock wool"],
        )
        self.assertEqual(
            [layer.LayerThickness for layer in layer_set.MaterialLayers],
            [0.12, 0.10],
        )
        self.assertEqual(len(house.model.by_type("IfcMaterial")), 2)

        for wall in (wall_1, wall_2):
            self.assertEqual(ifcopenshell.util.element.get_type(wall), exterior_wall)
            usage = ifcopenshell.util.element.get_material(wall)
            self.assertTrue(usage.is_a("IfcMaterialLayerSetUsage"))
            self.assertEqual(usage.ForLayerSet, layer_set)
            self.assertEqual(usage.LayerSetDirection, "AXIS2")
            self.assertEqual(usage.DirectionSense, "NEGATIVE")
            self.assertAlmostEqual(usage.OffsetFromReferenceLine, 0.12)

    def test_connects_wall_end_to_another_wall_path(self) -> None:
        house = House("My house")
        wall_type = house.wall_type("Brick", layers=[("Brick", 0.12)])
        ground = house.storey("Ground floor", elevation=0)
        branch_wall = ground.wall(
            (2, -2), (2, 0), wall_type=wall_type, height=2.8
        )
        main_wall = ground.wall(
            (0, 0), (4, 0), wall_type=wall_type, height=2.8
        )

        connection = ground.connect_wall(
            branch_wall, main_wall, is_atpath=True
        )

        self.assertEqual(connection.RelatingConnectionType, "ATEND")
        self.assertEqual(connection.RelatedConnectionType, "ATPATH")
        usage = ifcopenshell.util.element.get_material(branch_wall)
        self.assertEqual(usage.DirectionSense, "NEGATIVE")
        self.assertAlmostEqual(usage.OffsetFromReferenceLine, 0.06)

    def test_creates_spatial_hierarchy_and_wall(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=1.5)
        wall = ground.wall((4, 0), (4, 5), thickness=0.12, height=2.8)

        self.assertEqual(house.project.Name, "My house")
        self.assertEqual(house.building.Name, "My house")
        self.assertEqual(ground.element.Name, "Ground floor")
        self.assertEqual(ground.element.Elevation, 1.5)
        self.assertTrue(wall.is_a("IfcWall"))
        self.assertIsInstance(wall, Wall)
        self.assertIs(wall.element, wall)
        self.assertEqual(wall.ContainedInStructure[0].RelatingStructure, ground.element)

        placement = ifcopenshell.util.placement.get_local_placement(
            wall.ObjectPlacement
        )
        self.assertAlmostEqual(placement[0, 3], 4)
        self.assertAlmostEqual(placement[1, 3], 0)
        self.assertAlmostEqual(placement[2, 3], 1.5)

        representations = wall.Representation.Representations
        self.assertEqual(
            {
                representation.RepresentationIdentifier
                for representation in representations
            },
            {"Axis", "Body"},
        )

    def test_adds_doors_and_windows_as_semantic_wall_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((1, 2), (1, 7), thickness=0.25, height=3)

        door = wall.add_door(
            at=0.5,
            width=0.9,
            height=2.1,
            opening_width=1.1,
            opening_height=2.2,
            operation="SINGLE_SWING_RIGHT",
        )
        window = wall.add_window(
            at=3,
            width=1.2,
            height=2,
            sill_height=1,
            partition="SINGLE_PANEL",
        )

        self.assertTrue(door.is_a("IfcDoor"))
        self.assertEqual(door.OverallWidth, 0.9)
        self.assertEqual(door.OverallHeight, 2.1)
        self.assertEqual(door.OperationType, "SINGLE_SWING_RIGHT")
        self.assertTrue(window.is_a("IfcWindow"))
        self.assertEqual(window.OverallWidth, 1.2)
        self.assertEqual(window.OverallHeight, 1)
        self.assertEqual(window.PartitioningType, "SINGLE_PANEL")

        for filling in (door, window):
            opening = filling.FillsVoids[0].RelatingOpeningElement
            self.assertTrue(opening.is_a("IfcOpeningElement"))
            self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, wall)
            self.assertEqual(
                filling.ContainedInStructure[0].RelatingStructure,
                ground.element,
            )
            contexts = {
                (
                    representation.ContextOfItems.ContextType,
                    representation.ContextOfItems.ContextIdentifier,
                    representation.ContextOfItems.TargetView,
                )
                for representation in filling.Representation.Representations
            }
            self.assertEqual(
                contexts,
                {
                    ("Model", "Body", "MODEL_VIEW"),
                    ("Plan", "Body", "PLAN_VIEW"),
                },
            )

        door_opening = door.FillsVoids[0].RelatingOpeningElement
        opening_placement = ifcopenshell.util.placement.get_local_placement(
            door_opening.ObjectPlacement
        )
        self.assertAlmostEqual(opening_placement[0, 3], 1)
        self.assertAlmostEqual(opening_placement[1, 3], 2.5)
        opening_body = ifcopenshell.util.representation.get_representation(
            door_opening, "Model", "Body", "MODEL_VIEW"
        )
        self.assertAlmostEqual(opening_body.Items[0].Depth, 2.2)

        overhead = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.ObjectType == "LINEWORK"
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "Classes"
            ),
            "dashed",
        )
        overhead_representation = ifcopenshell.util.representation.get_representation(
            overhead, "Plan", "Annotation", "PLAN_VIEW"
        )
        overhead_coordinates = overhead_representation.Items[0].Points.CoordList
        self.assertEqual(overhead_coordinates, ((0.0, 0.0), (1.1, 0.0)))
        drawing = house.add_drawing("Ground plan", 1, 4.5, 1.5, 4)
        self.assertIn(overhead, drawing.group.IsGroupedBy[0].RelatedObjects)

        framing = next(
            aspect
            for aspect in door.Representation.HasShapeAspects
            if aspect.Name == "Framing"
        )
        framing_body = next(
            representation
            for representation in framing.ShapeRepresentations
            if representation.ContextOfItems.ContextType == "Model"
        )
        door_panel_placement = ifcopenshell.util.placement.get_axis2placement(
            framing_body.Items[0].Position
        )
        self.assertAlmostEqual(door_panel_placement[0, 0], 2**-0.5)
        self.assertAlmostEqual(door_panel_placement[1, 0], -(2**-0.5))

        plan = ifcopenshell.util.representation.get_representation(
            door, "Plan", "Body", "PLAN_VIEW"
        )
        plan_coordinates = [
            coordinate
            for item in plan.Items
            if item.is_a("IfcIndexedPolyCurve")
            for coordinate in item.Points.CoordList
        ]
        self.assertGreater(max(coordinate[1] for coordinate in plan_coordinates), 0.9)

        door_placement = ifcopenshell.util.placement.get_local_placement(
            door.ObjectPlacement
        )
        self.assertAlmostEqual(door_placement[0, 3], 1)
        self.assertAlmostEqual(door_placement[1, 3], 2.6)
        self.assertAlmostEqual(door_placement[2, 3], 0)
        window_placement = ifcopenshell.util.placement.get_local_placement(
            window.ObjectPlacement
        )
        self.assertAlmostEqual(window_placement[0, 3], 1)
        self.assertAlmostEqual(window_placement[1, 3], 5)
        self.assertAlmostEqual(window_placement[2, 3], 1)

        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), wall)
        expected_volume = 5 * 0.25 * 3 - 1.1 * 0.25 * 2.2 - 1.2 * 0.25 * 1
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            expected_volume,
        )

    def test_rejects_invalid_or_overlapping_wall_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.25, height=3)

        with self.assertRaisesRegex(ValueError, "wall length"):
            wall.add_door(at=4.2, width=0.9, height=2.1)
        with self.assertRaisesRegex(ValueError, "wall height"):
            wall.add_window(
                at=2,
                width=1,
                height=3.5,
                sill_height=2,
            )
        with self.assertRaisesRegex(ValueError, "operation must be one of"):
            wall.add_door(at=1, width=0.9, height=2.1, operation="REVOLVING")
        with self.assertRaisesRegex(ValueError, "between 0 and 180"):
            wall.add_door(at=1, width=0.9, height=2.1, open_angle=181)
        with self.assertRaisesRegex(ValueError, "opening_width"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                opening_width=0.8,
            )
        with self.assertRaisesRegex(ValueError, "opening_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                opening_height=2,
            )
        with self.assertRaisesRegex(TypeError, "show_overhead"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                show_overhead="yes",
            )
        with self.assertRaisesRegex(ValueError, "partition must be one of"):
            wall.add_window(
                at=3,
                width=1,
                height=2,
                sill_height=1,
                partition="ROUND",
            )

        with self.assertRaisesRegex(ValueError, "greater than sill_height"):
            wall.add_window(
                at=3,
                width=1,
                height=1,
                sill_height=1,
            )

        wall.add_door(at=1, width=0.9, height=2.1)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            wall.add_window(
                at=1,
                width=1,
                height=2,
                sill_height=1,
            )

    def test_writes_a_file_that_ifcopenshell_can_reopen(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0).wall(
            (4, 0), (4, 5), thickness=0.12, height=2.8
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "house.ifc"
            self.assertEqual(house.write(output), output)

            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcWall")), 1)
            self.assertEqual(reopened.by_type("IfcProject")[0].Name, "My house")

    def test_stores_batting_annotation_and_thickness_in_ifc(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        batting = ground.batting(
            (0, 0.1),
            (4, 0.1),
            thickness=0.2,
            name="Rockwool batting",
        )

        self.assertEqual(batting.is_a(), "IfcAnnotation")
        self.assertEqual(batting.ObjectType, "BATTING")
        self.assertEqual(batting.Name, "Rockwool batting")
        representation = batting.Representation.Representations[0]
        self.assertEqual(representation.RepresentationIdentifier, "Annotation")
        self.assertEqual(representation.ContextOfItems.TargetView, "PLAN_VIEW")
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                batting, "BBIM_Batting", "Thickness"
            ),
            0.2,
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "house.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            annotations = reopened.by_type("IfcAnnotation")
            self.assertEqual(len(annotations), 1)
            self.assertEqual(annotations[0].ObjectType, "BATTING")

    def test_stores_drawing_camera_and_scoped_batting_in_ifc(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing("Ground plan", 2, 3, 1.6, 5)
        other_drawing = house.add_drawing("Other plan", 2, 3, 1.6, 5)

        batting = drawing.add_batting(
            (0, 0.1),
            (4, 0.1),
            thickness=0.2,
        )

        self.assertEqual(drawing.element.ObjectType, "DRAWING")
        self.assertEqual(drawing.element.Name, "Ground plan")
        placement = ifcopenshell.util.placement.get_local_placement(
            drawing.element.ObjectPlacement
        )
        self.assertEqual(tuple(placement[:3, 3]), (2, 3, 1.6))
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), drawing.element
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 10)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 10)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "TargetView"
            ),
            "PLAN_VIEW",
        )
        self.assertEqual(drawing.document.Location, "drawings/Ground plan.svg")

        drawing_members = set(drawing.group.IsGroupedBy[0].RelatedObjects)
        other_members = set(other_drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertEqual(drawing_members, {drawing.element, batting})
        self.assertEqual(other_members, {other_drawing.element})

        with TemporaryDirectory() as directory:
            output = Path(directory) / "house.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            drawings = [
                annotation
                for annotation in reopened.by_type("IfcAnnotation")
                if annotation.ObjectType == "DRAWING"
            ]
            self.assertEqual({drawing.Name for drawing in drawings}, {"Ground plan", "Other plan"})

    def test_renders_a_persisted_drawing_by_global_id(self) -> None:
        house = House("My house")
        drawing = house.add_drawing("Ground plan", 2, 3, 1.6, 5)

        with self.assertRaisesRegex(RuntimeError, "write the house"):
            drawing.render("ground-plan.svg")

        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            house.write(directory_path / "house.ifc")
            output = directory_path / "ground-plan.svg"
            commands: list[list[str]] = []

            def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
                self.assertTrue(check)
                commands.append(command)
                if "--output" in command:
                    output_index = command.index("--output") + 1
                    Path(command[output_index]).write_text("<svg/>", encoding="utf-8")
                else:
                    png_argument = next(
                        argument
                        for argument in command
                        if argument.startswith("--export-filename=")
                    )
                    Path(png_argument.split("=", 1)[1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0)

            with (
                patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"),
                patch("ifc_utils.subprocess.run", side_effect=run),
            ):
                result = drawing.render(output, png=True, png_dpi=600)

            self.assertEqual(result, output)
            self.assertEqual(len(commands), 2)
            blender_command = commands[0]
            self.assertTrue(
                blender_command[blender_command.index("--python") + 1].endswith(
                    "render_drawing.py"
                )
            )
            self.assertEqual(
                blender_command[blender_command.index("--drawing-guid") + 1],
                drawing.element.GlobalId,
            )
            self.assertNotIn("--x", blender_command)
            self.assertIn("--export-dpi=600", commands[1])
            self.assertTrue(output.with_suffix(".png").is_file())
            reopened = ifcopenshell.open(directory_path / "house.ifc")
            persisted = reopened.by_guid(drawing.element.GlobalId)
            document = next(
                association.RelatingDocument
                for association in persisted.HasAssociations
                if association.is_a("IfcRelAssociatesDocument")
            )
            self.assertEqual(Path(document.Location), output.resolve())

    def test_generates_svg_and_optional_png_from_an_ifc_file(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0).wall(
            (0, 0), (4, 0), thickness=0.12, height=2.8
        )

        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            house.write(directory_path / "house.ifc")
            svg_output = directory_path / "house.svg"
            commands: list[list[str]] = []

            def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
                self.assertTrue(check)
                commands.append(command)
                if "--output" in command:
                    output_index = command.index("--output") + 1
                    Path(command[output_index]).write_text("<svg/>", encoding="utf-8")
                else:
                    png_argument = next(
                        argument
                        for argument in command
                        if argument.startswith("--export-filename=")
                    )
                    Path(png_argument.split("=", 1)[1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0)

            with (
                patch(
                    "ifc_utils.shutil.which",
                    side_effect=lambda command: f"/usr/bin/{command}",
                ),
                patch("ifc_utils.subprocess.run", side_effect=run),
            ):
                result = generate_plan(
                    directory_path / "house.ifc",
                    svg_output,
                    x=1,
                    y=2,
                    z=1.6,
                    radius=5,
                    png=True,
                )

            self.assertEqual(result, svg_output)
            self.assertTrue(svg_output.is_file())
            self.assertTrue(svg_output.with_suffix(".png").is_file())
            self.assertEqual(len(commands), 2)
            blender_command = commands[0]
            self.assertNotIn("--background", blender_command)
            self.assertIn("--python-exit-code", blender_command)
            self.assertEqual(
                Path(blender_command[blender_command.index("--ifc") + 1]),
                (directory_path / "house.ifc").resolve(),
            )
            stylesheet = Path(
                blender_command[blender_command.index("--stylesheet") + 1]
            )
            self.assertEqual(stylesheet.name, "plan.css")
            self.assertTrue(stylesheet.is_file())
            self.assertEqual(blender_command[blender_command.index("--x") + 1], "1.0")
            self.assertEqual(blender_command[blender_command.index("--y") + 1], "2.0")
            self.assertEqual(blender_command[blender_command.index("--z") + 1], "1.6")
            self.assertEqual(blender_command[blender_command.index("--radius") + 1], "5.0")

    def test_requires_an_existing_ifc_file_for_plan_generation(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "IFC file not found"):
            generate_plan(
                "missing.ifc",
                "house.svg",
                x=0,
                y=0,
                z=1.6,
                radius=5,
            )

    def test_requires_written_ifc_before_generating_plan(self) -> None:
        house = House("My house")

        with self.assertRaisesRegex(RuntimeError, "write the IFC"):
            house.generate_plan("house.svg", x=0, y=0, z=1.6, radius=5)

    def test_rejects_invalid_plan_parameters(self) -> None:
        house = House("My house")
        with TemporaryDirectory() as directory:
            house.write(Path(directory) / "house.ifc")

            with self.assertRaisesRegex(ValueError, ".svg extension"):
                house.generate_plan("house.pdf", x=0, y=0, z=1.6, radius=5)
            with self.assertRaisesRegex(ValueError, "greater than zero"):
                house.generate_plan("house.svg", x=0, y=0, z=1.6, radius=0)
            with self.assertRaisesRegex(TypeError, "png must be a boolean"):
                house.generate_plan(
                    "house.svg", x=0, y=0, z=1.6, radius=5, png=1
                )

    def test_rejects_invalid_wall_dimensions(self) -> None:
        ground = House("My house").storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(ValueError, "different points"):
            ground.wall((1, 1), (1, 1), thickness=0.12, height=2.8)
        with self.assertRaisesRegex(ValueError, "thickness"):
            ground.wall((0, 0), (1, 0), thickness=0, height=2.8)
        with self.assertRaisesRegex(ValueError, "height"):
            ground.wall((0, 0), (1, 0), thickness=0.12, height=-1)

    def test_rejects_invalid_wall_layers_and_type_usage(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(ValueError, "at least one"):
            house.wall_type("Empty", layers=[])
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            house.wall_type("Invalid", layers=[("Brick", 0)])
        with self.assertRaisesRegex(ValueError, "at most one axis"):
            house.wall_type(
                "Duplicate axis",
                layers=["axis", ("Brick", 0.12), "axis"],
            )
        with self.assertRaisesRegex(ValueError, 'must be "axis"'):
            house.wall_type("Unknown marker", layers=[("Brick", 0.12), "centre"])
        with self.assertRaisesRegex(ValueError, "material layer"):
            house.wall_type("No materials", layers=["axis"])
        with self.assertRaisesRegex(ValueError, "either thickness or wall_type"):
            ground.wall((0, 0), (1, 0), height=2.8)

        wall_type = house.wall_type("Brick", layers=[("Brick", 0.12)])
        with self.assertRaisesRegex(ValueError, "must not both"):
            ground.wall(
                (0, 0),
                (1, 0),
                thickness=0.12,
                wall_type=wall_type,
                height=2.8,
            )

        foreign_type = House("Other house").wall_type(
            "Other wall", layers=[("Brick", 0.12)]
        )
        with self.assertRaisesRegex(ValueError, "belong to this house"):
            ground.wall((0, 0), (1, 0), wall_type=foreign_type, height=2.8)

    def test_rejects_invalid_wall_connections(self) -> None:
        house = House("My house")
        wall_type = house.wall_type("Brick", layers=[("Brick", 0.12)])
        ground = house.storey("Ground floor", elevation=0)
        wall_1 = ground.wall(
            (0, 0), (1, 0), wall_type=wall_type, height=2.8
        )
        parallel_wall = ground.wall(
            (0, 1), (1, 1), wall_type=wall_type, height=2.8
        )

        with self.assertRaisesRegex(ValueError, "itself"):
            ground.connect_wall(wall_1, wall_1)
        with self.assertRaisesRegex(ValueError, "intersect"):
            ground.connect_wall(wall_1, parallel_wall)

        plain_wall = ground.wall((1, 0), (1, 1), thickness=0.12, height=2.8)
        with self.assertRaisesRegex(ValueError, "IfcMaterialLayerSetUsage"):
            ground.connect_wall(wall_1, plain_wall)


if __name__ == "__main__":
    unittest.main()
