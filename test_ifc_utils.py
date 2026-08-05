import unittest
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation

from ifc_utils import House, generate_plan


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
