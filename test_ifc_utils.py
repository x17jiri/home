import json
import unittest
from math import hypot
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import (
    Beam,
    Chimney,
    House,
    MiakoSlab,
    Roof,
    RoofLayer,
    RoofPlane,
    Stair,
    Wall,
    _close_door_bodies,
    _overhead_mask_global_ids,
    _postprocess_door_overheads,
    _postprocess_elevation_opening_overlays,
    _postprocess_projected_wood_fills,
    _postprocess_vapour_barrier_overlays,
    generate_plan,
    offset_plane,
)


class HouseTests(unittest.TestCase):
    def test_offsets_plane_along_upward_normal_independent_of_point_order(
        self,
    ) -> None:
        points = (
            (0, 0, 0),
            (1, 0, 0),
            (0, 1, 1),
        )
        distance = 2**0.5
        expected_shift = np.array((0, -1, 1), dtype=float)

        shifted = offset_plane(*points, offset=distance)
        reversed_shifted = offset_plane(
            points[0], points[2], points[1], offset=distance
        )

        np.testing.assert_allclose(
            np.array(shifted),
            np.array(points, dtype=float) + expected_shift,
        )
        np.testing.assert_allclose(
            np.array(reversed_shifted),
            np.array((points[0], points[2], points[1]), dtype=float)
            + expected_shift,
        )

    def test_validates_plane_offset_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be collinear"):
            offset_plane((0, 0, 0), (1, 0, 0), (2, 0, 0), offset=1)
        with self.assertRaisesRegex(ValueError, "must not be vertical"):
            offset_plane((0, 0, 0), (0, 1, 0), (0, 0, 1), offset=1)
        with self.assertRaisesRegex(TypeError, "offset must be a number"):
            offset_plane((0, 0, 0), (1, 0, 0), (0, 1, 1), offset=True)

    def write_asset_library(self, path: Path) -> None:
        library = ifcopenshell.api.project.create_file(version="IFC4")
        project = ifcopenshell.api.root.create_entity(
            library, ifc_class="IfcProject", name="Test asset library"
        )
        project_library = ifcopenshell.api.root.create_entity(
            library, ifc_class="IfcProjectLibrary", name="Test asset library"
        )
        ifcopenshell.api.aggregate.assign_object(
            library, products=[project_library], relating_object=project
        )
        units = [
            ifcopenshell.api.unit.add_si_unit(library, unit_type="LENGTHUNIT")
        ]
        ifcopenshell.api.unit.assign_unit(library, units=units)
        model_context = ifcopenshell.api.context.add_context(
            library, context_type="Model"
        )
        body_context = ifcopenshell.api.context.add_context(
            library,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_context,
        )
        plan_context = ifcopenshell.api.context.add_context(
            library, context_type="Plan"
        )
        plan_body_context = ifcopenshell.api.context.add_context(
            library,
            context_type="Plan",
            context_identifier="Body",
            target_view="PLAN_VIEW",
            parent=plan_context,
        )

        def add_type(ifc_class: str, name: str) -> None:
            asset_type = ifcopenshell.api.root.create_entity(
                library,
                ifc_class=ifc_class,
                name=name,
                predefined_type="NOTDEFINED",
            )
            footprint = [(0.0, -0.6), (0.4, -0.6), (0.4, 0.0), (0.0, 0.0)]
            body = ifcopenshell.api.geometry.add_slab_representation(
                library,
                context=body_context,
                depth=0.8,
                polyline=footprint,
            )
            ifcopenshell.api.geometry.assign_representation(
                library, product=asset_type, representation=body
            )
            plan = ifcopenshell.api.geometry.add_axis_representation(
                library,
                context=plan_body_context,
                axis=[*footprint, footprint[0]],
            )
            ifcopenshell.api.geometry.assign_representation(
                library, product=asset_type, representation=plan
            )
            ifcopenshell.api.project.assign_declaration(
                library,
                definitions=[asset_type],
                relating_context=project_library,
            )

        add_type("IfcSanitaryTerminalType", "Neufert Toilet with Cistern")
        add_type("IfcElectricApplianceType", "Neufert Cooktop 58x51")
        library.write(path)

    def assert_surface_style(
        self,
        product: ifcopenshell.entity_instance,
        expected_rgb: tuple[float, float, float],
        expected_transparency: float = 0,
    ) -> None:
        body = ifcopenshell.util.representation.get_representation(
            product, "Model", "Body", "MODEL_VIEW"
        )
        self.assertIsNotNone(body)
        for item in body.Items:
            self.assertEqual(len(item.StyledByItem), 1)
            surface_style = item.StyledByItem[0].Styles[0]
            self.assertTrue(surface_style.is_a("IfcSurfaceStyle"))
            shading = next(
                style
                for style in surface_style.Styles
                if style.is_a("IfcSurfaceStyleShading")
            )
            actual_rgb = (
                shading.SurfaceColour.Red,
                shading.SurfaceColour.Green,
                shading.SurfaceColour.Blue,
            )
            for actual, expected in zip(actual_rgb, expected_rgb):
                self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(shading.Transparency, expected_transparency)

    def assert_shape_aspect_surface_style(
        self,
        product: ifcopenshell.entity_instance,
        aspect_name: str,
        expected_rgb: tuple[float, float, float],
        expected_transparency: float,
    ) -> None:
        aspect = next(
            aspect
            for aspect in product.Representation.HasShapeAspects
            if aspect.Name == aspect_name
        )
        representation = next(
            representation
            for representation in aspect.ShapeRepresentations
            if representation.ContextOfItems.ContextType == "Model"
        )
        for item in representation.Items:
            self.assertEqual(len(item.StyledByItem), 1)
            surface_style = item.StyledByItem[0].Styles[0]
            shading = next(
                style
                for style in surface_style.Styles
                if style.is_a("IfcSurfaceStyleShading")
            )
            actual_rgb = (
                shading.SurfaceColour.Red,
                shading.SurfaceColour.Green,
                shading.SurfaceColour.Blue,
            )
            for actual, expected in zip(actual_rgb, expected_rgb):
                self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(shading.Transparency, expected_transparency)

    def test_creates_a_sloping_wooden_roof_beam_between_3d_points(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        rafter = upper.beam(
            "Roof rafter",
            start=(1, 2, 4),
            end=(5, 2, 7),
            size=(0.12, 0.2),
            kind="RAFTER",
        )

        self.assertIsInstance(rafter, Beam)
        self.assertTrue(rafter.is_a("IfcBeam"))
        self.assertIs(rafter.element, rafter)
        self.assertEqual(rafter.PredefinedType, "USERDEFINED")
        self.assertEqual(
            ifcopenshell.util.element.get_predefined_type(rafter), "RAFTER"
        )
        self.assertEqual(rafter.start, (1, 2, 4))
        self.assertEqual(rafter.end, (5, 2, 7))
        self.assertEqual(rafter.size, (0.12, 0.2))
        self.assertEqual(rafter.material_name, "Wood")
        self.assertEqual(rafter.length, 5)
        self.assertEqual(
            rafter.ContainedInStructure[0].RelatingStructure,
            upper.element,
        )

        placement = ifcopenshell.util.placement.get_local_placement(
            rafter.ObjectPlacement
        )
        np.testing.assert_allclose(placement[:3, 3], (1, 2, 4), atol=1e-9)
        np.testing.assert_allclose(placement[:3, 0], (0.8, 0, 0.6), atol=1e-9)
        np.testing.assert_allclose(placement[:3, 1], (0, 1, 0), atol=1e-9)
        np.testing.assert_allclose(placement[:3, 2], (-0.6, 0, 0.8), atol=1e-9)
        self.assertAlmostEqual(np.linalg.det(placement[:3, :3]), 1)

        body = ifcopenshell.util.representation.get_representation(
            rafter, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "SweptSolid")
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), rafter)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            5 * 0.12 * 0.2,
        )
        self.assertEqual(ifcopenshell.util.element.get_material(rafter).Name, "Wood")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                rafter, "Pset_BeamCommon", "LoadBearing"
            ),
            True,
        )
        self.assert_surface_style(rafter, (139 / 255, 90 / 255, 43 / 255))

        with TemporaryDirectory() as directory:
            output = Path(directory) / "roof-beam.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcBeam")), 1)
            self.assertEqual(
                ifcopenshell.util.element.get_predefined_type(
                    reopened.by_type("IfcBeam")[0]
                ),
                "RAFTER",
            )

    def test_rolls_and_validates_generic_beams(self) -> None:
        house = House("My house", colors={"beam": "blue"})
        upper = house.storey("Upper floor", elevation=3)
        purlin = upper.beam(
            "Purlin",
            start=(0, 0, 5),
            end=(4, 0, 5),
            size=(0.1, 0.2),
            kind="PURLIN",
            rotation=90,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            purlin.ObjectPlacement
        )
        np.testing.assert_allclose(placement[:3, 1], (0, 0, 1), atol=1e-9)
        np.testing.assert_allclose(placement[:3, 2], (0, -1, 0), atol=1e-9)
        self.assert_surface_style(purlin, (0, 0, 1))

        arguments = {
            "start": (0, 0, 4),
            "end": (1, 0, 4),
            "size": (0.1, 0.2),
        }
        with self.assertRaisesRegex(ValueError, "different points"):
            upper.beam("Invalid", **(arguments | {"end": (0, 0, 4)}))
        with self.assertRaisesRegex(TypeError, "exactly two"):
            upper.beam("Invalid", **(arguments | {"size": (0.1, 0.2, 0.3)}))
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            upper.beam("Invalid", **(arguments | {"size": (0, 0.2)}))
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            upper.beam("Invalid", **arguments, kind="COLUMN")

    def test_creates_a_cut_roof_plane_with_local_beams_and_layers(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        cuts = [
            ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
            ((6, 0, 0), (6, 1, 0), (6, 0, 1)),
        ]
        south = roof.plane(
            "South slope",
            points=((0, 0, 4), (6, 0, 4), (0, 4, 6)),
            cuts=cuts,
        )

        self.assertIsInstance(roof, Roof)
        self.assertTrue(roof.is_a("IfcRoof"))
        self.assertEqual(
            roof.ContainedInStructure[0].RelatingStructure,
            upper.element,
        )
        self.assertIsInstance(south, RoofPlane)
        self.assertTrue(south.is_a("IfcElementAssembly"))
        self.assertEqual(south.ObjectType, "ROOF_PLANE")
        self.assertEqual(south.Decomposes[0].RelatingObject, roof)
        self.assertEqual(roof.planes, (south,))
        self.assertEqual(south.cuts, tuple(cuts))
        np.testing.assert_allclose(south.x_axis, (1, 0, 0), atol=1e-9)
        np.testing.assert_allclose(
            south.y_axis,
            (0, 2 / np.sqrt(5), 1 / np.sqrt(5)),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            south.z_axis,
            (0, -1 / np.sqrt(5), 2 / np.sqrt(5)),
            atol=1e-9,
        )
        world_point = south.to_world((1, 2, 0.3))
        np.testing.assert_allclose(
            south.to_local(world_point),
            (1, 2, 0.3),
            atol=1e-9,
        )
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    south, "BBIM_RoofPlane", "Cuts"
                )
            ),
            [[list(point) for point in cut] for cut in cuts],
        )

        purlin = south.beam(
            "Purlin",
            start=(-1, 2),
            end=(7, 2),
            z_offset=0.2,
            size=(0.1, 0.2),
            kind="PURLIN",
        )
        self.assertEqual(purlin.local_start, (-1, 2))
        self.assertEqual(purlin.local_end, (7, 2))
        self.assertEqual(purlin.z_offset, 0.2)
        self.assertAlmostEqual(purlin.centerline_z_offset, 0.3)
        self.assertAlmostEqual(south.to_local(purlin.start)[2], 0.3)
        self.assertIs(purlin.roof_plane, south)
        self.assertFalse(purlin.ContainedInStructure)
        self.assertEqual(purlin.Decomposes[0].RelatingObject, south)
        np.testing.assert_allclose(
            purlin.placement[:3, 2], south.z_axis, atol=1e-9
        )
        beam_body = ifcopenshell.util.representation.get_representation(
            purlin, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(beam_body.RepresentationType, "Clipping")
        beam_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), purlin
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(beam_shape.geometry),
            6 * 0.1 * 0.2,
        )
        rolled_rafter = south.beam(
            "Rolled rafter",
            start=(1, 0),
            end=(1, 4),
            z_offset=0.4,
            size=(0.1, 0.2),
            kind="RAFTER",
            rotation=90,
        )
        self.assertAlmostEqual(rolled_rafter.centerline_z_offset, 0.45)
        self.assertAlmostEqual(south.to_local(rolled_rafter.start)[2], 0.45)

        deck = south.layer(
            "Roof decking",
            outline=((-1, 0), (7, 0), (7, 4), (-1, 4)),
            z_offset=0.3,
            thickness=0.1,
            material="Wood",
        )
        self.assertIsInstance(deck, RoofLayer)
        self.assertTrue(deck.is_a("IfcSlab"))
        self.assertEqual(deck.PredefinedType, "ROOF")
        self.assertEqual(deck.Decomposes[0].RelatingObject, south)
        self.assertFalse(deck.ContainedInStructure)
        self.assertEqual(deck.z_offset, 0.3)
        self.assertEqual(deck.thickness, 0.1)
        self.assertEqual(deck.cuts, tuple(cuts))
        self.assertEqual(deck.extra_cuts, ())
        self.assertEqual(ifcopenshell.util.element.get_material(deck).Name, "Wood")
        layer_body = ifcopenshell.util.representation.get_representation(
            deck, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(layer_body.RepresentationType, "Clipping")
        layer_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), deck
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(layer_shape.geometry),
            6 * 4 * 0.1,
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "roof.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            reopened_roof = reopened.by_type("IfcRoof")[0]
            reopened_plane = reopened.by_type("IfcElementAssembly")[0]
            self.assertEqual(reopened_plane.Decomposes[0].RelatingObject, reopened_roof)
            self.assertEqual(
                {part.is_a() for part in reopened_plane.IsDecomposedBy[0].RelatedObjects},
                {"IfcBeam", "IfcSlab"},
            )

    def test_appends_layer_specific_cuts_to_roof_plane_cuts(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        plane_cuts = [
            ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
            ((6, 0, 0), (6, 1, 0), (6, 0, 1)),
        ]
        extra_cut = ((0, 3, 0), (6, 3, 0), (0, 3, 10))
        plane = roof.plane(
            "Flat roof",
            points=((0, 0, 4), (6, 0, 4), (0, 4, 4)),
            cuts=plane_cuts,
        )

        layer = plane.layer(
            "Trimmed plasterboard",
            outline=((-1, 0), (7, 0), (7, 4), (-1, 4)),
            thickness=0.1,
            material="Gypsum plasterboard",
            extra_cuts=[extra_cut],
        )

        self.assertEqual(layer.extra_cuts, (extra_cut,))
        self.assertEqual(layer.cuts, (*plane_cuts, extra_cut))
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    layer, "BBIM_RoofLayer", "ExtraCuts"
                )
            ),
            [[list(point) for point in extra_cut]],
        )
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    layer, "BBIM_RoofLayer", "Cuts"
                )
            ),
            [[list(point) for point in cut] for cut in (*plane_cuts, extra_cut)],
        )
        body = ifcopenshell.util.representation.get_representation(
            layer, "Model", "Body", "MODEL_VIEW"
        )
        item = body.Items[0]
        clipping_count = 0
        while item.is_a("IfcBooleanClippingResult"):
            clipping_count += 1
            item = item.FirstOperand
        self.assertEqual(clipping_count, 3)
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), layer)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            6 * 3 * 0.1,
        )

        with self.assertRaisesRegex(ValueError, "cut 1 points"):
            plane.layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1), (0, 1)),
                thickness=0.1,
                material="Wood",
                extra_cuts=[((0, 0, 0), (1, 0, 0), (2, 0, 0))],
            )

    def test_adds_existing_elements_to_a_roof_and_validates_planes(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        dormer_wall = upper.wall(
            (1, 1),
            (2, 1),
            thickness=0.2,
            start_height=2,
            height=1,
        )
        dormer_side = upper.wall(
            (2, 1),
            (2, 2),
            thickness=0.2,
            start_height=2,
            height=1,
        )
        # Direct-thickness walls cannot be connected, so use a layered pair
        # to verify connections after roof aggregation separately below.
        roof.add(dormer_wall, dormer_side)
        self.assertFalse(dormer_wall.ContainedInStructure)
        self.assertEqual(dormer_wall.Decomposes[0].RelatingObject, roof)

        wall_type = house.wall_type("Dormer wall", layers=[("Brick", 0.2)])
        connected_front = upper.wall(
            (3, 1),
            (4, 1),
            wall_type=wall_type,
            start_height=2,
            height=1,
        )
        connected_side = upper.wall(
            (4, 1),
            (4, 2),
            wall_type=wall_type,
            start_height=2,
            height=1,
        )
        roof.add(connected_front, connected_side)
        upper.connect_wall(connected_front, connected_side)
        self.assertEqual(
            ifcopenshell.util.element.get_container(
                connected_front, ifc_class="IfcBuildingStorey"
            ),
            upper.element,
        )

        valid_points = ((0, 0, 4), (4, 0, 4), (0, 3, 6))
        roof.plane("South", points=valid_points)
        with self.assertRaisesRegex(ValueError, "name already exists"):
            roof.plane("South", points=valid_points)
        with self.assertRaisesRegex(TypeError, "exactly three points"):
            roof.plane("Invalid", points=valid_points[:2])
        with self.assertRaisesRegex(ValueError, "first and second"):
            roof.plane(
                "Invalid",
                points=((0, 0, 4), (0, 0, 4), (0, 3, 6)),
            )
        with self.assertRaisesRegex(ValueError, "must not be collinear"):
            roof.plane(
                "Invalid",
                points=((0, 0, 4), (1, 0, 4), (2, 0, 4)),
            )
        with self.assertRaisesRegex(ValueError, "non-zero global Z"):
            roof.plane(
                "Invalid",
                points=((0, 0, 4), (1, 0, 4), (0, 0, 5)),
            )
        with self.assertRaisesRegex(ValueError, "cut 1 points"):
            roof.plane(
                "Invalid",
                points=valid_points,
                cuts=[((0, 0, 0), (1, 0, 0), (2, 0, 0))],
            )

    def test_reassigns_roof_parts_to_visibility_storeys(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        south = roof.plane(
            "South slope",
            points=((0, 0, 4), (6, 0, 4), (0, 4, 6)),
        )

        rafter = south.beam(
            "Rafter",
            start=(1, 0),
            end=(1, 4),
            size=(0.1, 0.2),
            kind="RAFTER",
        )
        sheathing = south.layer(
            "Sheathing",
            outline=((0, 0), (6, 0), (6, 4), (0, 4)),
            thickness=0.025,
            material="Wood",
        )
        rafter_storey = house.storey("Roof - Rafters", elevation=3)
        sheathing_storey = house.storey("Roof - Sheathing", elevation=3)
        rafter_storey.add(rafter)
        sheathing_storey.add(sheathing)

        self.assertFalse(rafter.Decomposes)
        self.assertFalse(sheathing.Decomposes)
        self.assertEqual(
            rafter.ContainedInStructure[0].RelatingStructure,
            rafter_storey.element,
        )
        self.assertEqual(
            sheathing.ContainedInStructure[0].RelatingStructure,
            sheathing_storey.element,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_container(rafter),
            rafter_storey.element,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_container(sheathing),
            sheathing_storey.element,
        )

        rafter_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), rafter
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(rafter_shape.geometry),
            4 * 0.1 * 0.2,
        )
        sheathing_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), sheathing
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(sheathing_shape.geometry),
            6 * 4 * 0.025,
        )

        with self.assertRaisesRegex(ValueError, "at least one element"):
            rafter_storey.add()
        with self.assertRaisesRegex(TypeError, "must be an IfcElement"):
            rafter_storey.add(upper.element)
        other_house = House("Other house")
        other_beam = other_house.storey("Ground", elevation=0).beam(
            "Other beam",
            start=(0, 0, 1),
            end=(1, 0, 1),
            size=(0.1, 0.2),
        )
        with self.assertRaisesRegex(ValueError, "must belong to this house"):
            rafter_storey.add(other_beam)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "roof-storeys.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(
                {
                    storey.Name
                    for storey in reopened.by_type("IfcBuildingStorey")
                },
                {"Upper floor", "Roof - Rafters", "Roof - Sheathing"},
            )
            reopened_rafter = reopened.by_type("IfcBeam")[0]
            self.assertEqual(
                reopened_rafter.ContainedInStructure[0].RelatingStructure.Name,
                "Roof - Rafters",
            )

    def test_flips_only_the_offset_normal_for_a_mirrored_roof_slope(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        points = ((0, 8, 4), (6, 8, 4), (0, 4, 6))
        garden = roof.plane(
            "Garden slope",
            points=points,
            cuts=[((0, 4, 0), (10, 4, 0), (0, 4, 10))],
        )

        self.assertEqual(garden.points, points)
        self.assertEqual(garden.origin, points[0])
        self.assertTrue(garden.normal_flipped)
        np.testing.assert_allclose(garden.x_axis, (1, 0, 0), atol=1e-9)
        np.testing.assert_allclose(
            garden.y_axis,
            (0, -2 / np.sqrt(5), 1 / np.sqrt(5)),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            garden.z_axis,
            (0, 1 / np.sqrt(5), 2 / np.sqrt(5)),
            atol=1e-9,
        )
        self.assertGreater(garden.to_world((0, 0, 1))[2], garden.origin[2])
        np.testing.assert_allclose(
            garden.to_world((0, np.sqrt(20), 0)),
            points[2],
            atol=1e-9,
        )
        np.testing.assert_allclose(
            garden.to_local(points[2]),
            (0, np.sqrt(20), 0),
            atol=1e-9,
        )
        ifc_placement = ifcopenshell.util.placement.get_local_placement(
            garden.ObjectPlacement
        )
        self.assertAlmostEqual(np.linalg.det(ifc_placement[:3, :3]), 1)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                garden, "BBIM_RoofPlane", "NormalFlipped"
            ),
            True,
        )

        rafter = garden.beam(
            "Garden rafter",
            start=(1, -1),
            end=(1, 6),
            z_offset=0,
            size=(0.12, 0.2),
            kind="RAFTER",
        )
        self.assertAlmostEqual(garden.to_local(rafter.start)[2], 0.1)
        self.assertGreater(rafter.start[2], garden.to_world((1, -1, 0))[2])
        rafter_body = ifcopenshell.util.representation.get_representation(
            rafter, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(rafter_body.RepresentationType, "Clipping")
        rafter_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), rafter
        )
        self.assertGreater(
            ifcopenshell.util.shape.get_volume(rafter_shape.geometry),
            0,
        )

        layer = garden.layer(
            "Garden decking",
            outline=((0, 0), (6, 0), (6, 6), (0, 6)),
            z_offset=0.2,
            thickness=0.025,
            material="Wood",
        )
        layer_placement = ifcopenshell.util.placement.get_local_placement(
            layer.ObjectPlacement
        )
        self.assertAlmostEqual(np.linalg.det(layer_placement[:3, :3]), 1)
        np.testing.assert_allclose(
            layer_placement[:3, 2], garden.z_axis, atol=1e-9
        )
        layer_body = ifcopenshell.util.representation.get_representation(
            layer, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(layer_body.RepresentationType, "Clipping")
        layer_item = layer_body.Items[0]
        while layer_item.is_a("IfcBooleanClippingResult"):
            layer_item = layer_item.FirstOperand
        profile_points = layer_item.SweptArea.OuterCurve.Points.CoordList
        self.assertEqual(
            {round(point[1], 9) for point in profile_points},
            {-6.0, 0.0},
        )
        layer_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), layer
        )
        self.assertGreater(
            ifcopenshell.util.shape.get_volume(layer_shape.geometry),
            0,
        )

    def test_assigns_3d_colors_with_defaults_and_element_overrides(self) -> None:
        house = House(
            "Colored house",
            colors={
                "wall": "#F5F5F5",
                "door": "#8B5A2B",
                "window": "#4A90E2",
            },
        )
        wall_type = house.wall_type("Brick wall", layers=[("Brick", 0.2)])
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall(
            (0, 0), (5, 0), wall_type=wall_type, height=3
        )
        adjoining_wall = ground.wall(
            (5, 0), (5, 4), wall_type=wall_type, height=3, color="red"
        )

        ground.connect_wall(wall, adjoining_wall)
        door = wall.add_door(
            at=0.5,
            width=0.9,
            height=2.1,
            show_overhead=False,
        )
        window = wall.add_window(
            at=2.5,
            width=1,
            sill_height=1,
            height=2,
            color="#369",
            transparency=0.25,
        )

        self.assert_surface_style(wall, (245 / 255, 245 / 255, 245 / 255))
        self.assert_surface_style(adjoining_wall, (1, 0, 0))
        self.assert_surface_style(door, (139 / 255, 90 / 255, 43 / 255))
        self.assert_shape_aspect_surface_style(
            window, "Lining", (0.2, 0.4, 0.6), 0.25
        )
        self.assert_shape_aspect_surface_style(
            window, "Framing", (0.2, 0.4, 0.6), 0.25
        )
        self.assert_shape_aspect_surface_style(
            window, "Glazing", (0.2, 0.4, 0.6), 0.75
        )

        for filling in (door, window):
            plan = ifcopenshell.util.representation.get_representation(
                filling, "Plan", "Body", "PLAN_VIEW"
            )
            self.assertTrue(all(not item.StyledByItem for item in plan.Items))

    def test_rejects_invalid_3d_colors_and_transparency(self) -> None:
        with self.assertRaisesRegex(TypeError, "colors must be a mapping"):
            House("Invalid", colors=[("wall", "white")])
        with self.assertRaisesRegex(ValueError, "wall, window"):
            House("Invalid", colors={"roof": "red"})
        with self.assertRaisesRegex(ValueError, "named color"):
            House("Invalid", colors={"wall": "not-a-color"})

        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=3)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            wall.add_window(
                at=1,
                width=1,
                sill_height=1,
                height=2,
                color="blue",
                transparency=1.1,
            )

    def test_discovers_and_places_plan_ready_library_assets(self) -> None:
        with TemporaryDirectory() as directory:
            library_path = Path(directory) / "fixtures.ifc"
            self.write_asset_library(library_path)
            house = House("My house", asset_library=library_path)

            self.assertEqual(house.assets.path, library_path.resolve())
            self.assertEqual(
                [entry.alias for entry in house.assets.list(category="sanitary")],
                ["toilet_with_cistern"],
            )
            self.assertEqual(
                [entry.alias for entry in house.assets.search("WC")],
                ["toilet_with_cistern"],
            )
            self.assertEqual(
                [entry.alias for entry in house.assets.search("cooker")],
                ["cooktop_58x51"],
            )

            ground = house.storey("Ground floor", elevation=0.25)
            toilet = ground.asset(
                "WC",
                asset="toilet_with_cistern",
                center=(2, 3),
                rotation=90,
                start_height=0.1,
                label="WC",
            )
            second_toilet = ground.asset(
                "Guest WC",
                asset="wc",
                center=(3, 3),
            )

            self.assertTrue(toilet.is_a("IfcSanitaryTerminal"))
            self.assertEqual(
                ifcopenshell.util.element.get_type(toilet).Name,
                "Neufert Toilet with Cistern",
            )
            self.assertEqual(
                toilet.ContainedInStructure[0].RelatingStructure,
                ground.element,
            )
            self.assertEqual(
                len(house.model.by_type("IfcSanitaryTerminalType")), 1
            )
            self.assertEqual(
                ifcopenshell.util.element.get_type(second_toilet),
                ifcopenshell.util.element.get_type(toilet),
            )
            representations = {
                (
                    representation.ContextOfItems.ContextType,
                    representation.ContextOfItems.ContextIdentifier,
                    representation.ContextOfItems.TargetView,
                ): representation.RepresentationType
                for representation in toilet.Representation.Representations
            }
            self.assertEqual(
                representations[("Model", "Body", "MODEL_VIEW")],
                "MappedRepresentation",
            )
            self.assertEqual(
                representations[("Plan", "Body", "PLAN_VIEW")],
                "MappedRepresentation",
            )

            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            shape = ifcopenshell.geom.create_shape(settings, toilet)
            vertices = shape.geometry.verts
            points = tuple(zip(vertices[::3], vertices[1::3], vertices[2::3]))
            self.assertAlmostEqual(
                (min(point[0] for point in points) + max(point[0] for point in points))
                / 2,
                2,
            )
            self.assertAlmostEqual(
                (min(point[1] for point in points) + max(point[1] for point in points))
                / 2,
                3,
            )
            self.assertAlmostEqual(min(point[2] for point in points), 0.35)
            label = house.model.by_type("IfcTextLiteralWithExtent")[0]
            self.assertEqual(label.Literal, "WC")

    def test_validates_library_asset_selection_and_placement(self) -> None:
        with TemporaryDirectory() as directory:
            library_path = Path(directory) / "fixtures.ifc"
            self.write_asset_library(library_path)
            house = House("My house", asset_library=library_path)
            ground = house.storey("Ground floor", elevation=0)

            cooktop = ground.asset(
                "Cooktop",
                type_name="Neufert Cooktop 58x51",
                center=(1, 1),
            )
            self.assertTrue(cooktop.is_a("IfcElectricAppliance"))

            with self.assertRaisesRegex(TypeError, "exactly one"):
                ground.asset("Missing", center=(0, 0))
            with self.assertRaisesRegex(TypeError, "exactly one"):
                ground.asset(
                    "Ambiguous",
                    asset="cooker",
                    type_name="Neufert Cooktop 58x51",
                    center=(0, 0),
                )
            with self.assertRaisesRegex(ValueError, "toilet_with_cistern"):
                ground.asset(
                    "Typo", asset="toilet_with_cisterm", center=(0, 0)
                )
            with self.assertRaisesRegex(ValueError, "zero or greater"):
                ground.asset(
                    "Too low",
                    asset="toilet_with_cistern",
                    center=(0, 0),
                    start_height=-0.1,
                )

    def test_creates_semantic_box_furniture_with_a_labeled_plan_symbol(
        self,
    ) -> None:
        house = House("My house", colors={"furniture": "#8B5A2B"})
        ground = house.storey("Ground floor", elevation=0.25)
        drawing = house.add_drawing("Ground plan", 5, 3, 1.6, 4)
        table = ground.furniture(
            "Dining table",
            kind="TABLE",
            size=(1.8, 0.9, 0.75),
            center=(5, 3),
            rotation=90,
            start_height=0.1,
        )

        self.assertTrue(table.is_a("IfcFurniture"))
        self.assertEqual(table.PredefinedType, "TABLE")
        self.assertIsNone(table.ObjectType)
        self.assertEqual(
            table.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            table.ObjectPlacement
        )
        self.assertAlmostEqual(placement[0, 0], 0)
        self.assertAlmostEqual(placement[0, 1], -1)
        self.assertAlmostEqual(placement[1, 0], 1)
        self.assertAlmostEqual(placement[1, 1], 0)
        self.assertEqual(tuple(placement[:2, 3]), (5, 3))
        self.assertAlmostEqual(placement[2, 3], 0.35)

        body = ifcopenshell.util.representation.get_representation(
            table, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "SweptSolid")
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), table
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 1.8)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 0.9)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 0.75)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            1.8 * 0.9 * 0.75,
        )
        self.assert_surface_style(
            table, (139 / 255, 90 / 255, 43 / 255)
        )

        plan = ifcopenshell.util.representation.get_representation(
            table, "Plan", "Body", "PLAN_VIEW"
        )
        self.assertEqual(plan.RepresentationType, "Curve2D")
        self.assertEqual(
            plan.Items[0].Points.CoordList,
            (
                (-0.9, -0.45),
                (0.9, -0.45),
                (0.9, 0.45),
                (-0.9, 0.45),
                (-0.9, -0.45),
            ),
        )
        self.assertFalse(plan.Items[0].StyledByItem)

        label = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.ObjectType == "TEXT"
        )
        self.assertEqual(
            label.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        literal = label.Representation.Representations[0].Items[0]
        self.assertTrue(literal.is_a("IfcTextLiteralWithExtent"))
        self.assertEqual(literal.Literal, "Dining table")
        self.assertEqual(literal.BoxAlignment, "center")
        self.assertAlmostEqual(literal.Extent.SizeInX, 1.8)
        self.assertAlmostEqual(literal.Extent.SizeInY, 0.9)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                label, "EPset_Annotation", "Classes"
            ),
            "furniture-label small",
        )
        assignment = next(
            relation
            for relation in label.HasAssignments
            if relation.is_a("IfcRelAssignsToProduct")
        )
        self.assertEqual(assignment.RelatingProduct, table)
        self.assertIn(
            label,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "furniture.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcFurniture")), 1)
            self.assertEqual(
                reopened.by_type("IfcTextLiteralWithExtent")[0].Literal,
                "Dining table",
            )

    def test_validates_furniture_and_marks_custom_kinds(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        custom = ground.furniture(
            "Kitchen island",
            kind="USERDEFINED",
            size=(1.2, 0.6, 0.9),
            center=(2, 1),
            label="ISLAND",
        )
        self.assertEqual(custom.PredefinedType, "USERDEFINED")
        self.assertEqual(custom.ObjectType, "Kitchen island")
        label = house.model.by_type("IfcTextLiteralWithExtent")[0]
        self.assertEqual(label.Literal, "ISLAND")

        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            ground.furniture(
                "Stool", kind="STOOL", size=(0.4, 0.4, 0.5), center=(0, 0)
            )
        with self.assertRaisesRegex(TypeError, "exactly three dimensions"):
            ground.furniture(
                "Table", kind="TABLE", size=(1, 1), center=(0, 0)
            )
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            ground.furniture(
                "Table", kind="TABLE", size=(1, 1, 0), center=(0, 0)
            )
        with self.assertRaisesRegex(ValueError, "zero or greater"):
            ground.furniture(
                "Table",
                kind="TABLE",
                size=(1, 1, 1),
                center=(0, 0),
                start_height=-0.1,
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            ground.furniture(
                "Table",
                kind="TABLE",
                size=(1, 1, 1),
                center=(0, 0),
                transparency=1.1,
            )
        with self.assertRaisesRegex(ValueError, "label must not be empty"):
            ground.furniture(
                "Table",
                kind="TABLE",
                size=(1, 1, 1),
                center=(0, 0),
                label=" ",
            )

    def test_aligns_transparent_window_glazing_on_the_wall_axis(self) -> None:
        house = House("My house", colors={"window": "#369"})
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.25, height=3)
        axis_window = wall.add_window(
            at=0.5,
            width=1,
            height=2,
            sill_height=1,
        )
        inside_window = wall.add_window(
            at=2.5,
            width=1,
            height=2,
            sill_height=1,
            align="inside",
        )

        def glass_center_y(window: ifcopenshell.entity_instance) -> float:
            glazing = next(
                aspect
                for aspect in window.Representation.HasShapeAspects
                if aspect.Name == "Glazing"
            )
            representation = next(
                representation
                for representation in glazing.ShapeRepresentations
                if representation.ContextOfItems.ContextType == "Model"
            )
            glass = representation.Items[0]
            placement = ifcopenshell.util.placement.get_axis2placement(
                glass.Position
            )
            direction = np.array(glass.ExtrudedDirection.DirectionRatios)
            centre = placement[:3, 3] + (
                placement[:3, :3] @ direction * float(glass.Depth) / 2
            )
            return float(centre[1])

        self.assertAlmostEqual(glass_center_y(axis_window), 0)
        self.assertNotAlmostEqual(glass_center_y(inside_window), 0)
        self.assert_shape_aspect_surface_style(
            axis_window, "Lining", (0.2, 0.4, 0.6), 0
        )
        self.assert_shape_aspect_surface_style(
            axis_window, "Framing", (0.2, 0.4, 0.6), 0
        )
        self.assert_shape_aspect_surface_style(
            axis_window, "Glazing", (0.2, 0.4, 0.6), 0.75
        )
        plan = ifcopenshell.util.representation.get_representation(
            axis_window, "Plan", "Body", "PLAN_VIEW"
        )
        inside_plan = ifcopenshell.util.representation.get_representation(
            inside_window, "Plan", "Body", "PLAN_VIEW"
        )
        self.assertTrue(
            all(
                abs(coordinate[1]) < 1e-9
                for coordinate in plan.Items[-1].Points.CoordList
            )
        )
        self.assertTrue(
            any(
                abs(coordinate[1]) > 1e-9
                for coordinate in inside_plan.Items[-1].Points.CoordList
            )
        )
        frame_coordinates = plan.Items[3].Points.CoordList
        self.assertLess(min(point[1] for point in frame_coordinates), 0)
        self.assertGreater(max(point[1] for point in frame_coordinates), 0)
        for axis_item, inside_item in zip(
            plan.Items[:3], inside_plan.Items[:3]
        ):
            self.assertEqual(
                axis_item.Points.CoordList,
                inside_item.Points.CoordList,
            )
        self.assertTrue(all(not item.StyledByItem for item in plan.Items))

    def test_creates_semantic_straight_stair_and_scoped_plan_symbol(self) -> None:
        house = House("My house", colors={"stair": "#C8B090"})
        ground = house.storey("Ground floor", elevation=0)
        stair = ground.stair(
            (2, 1),
            (5, 1),
            width=0.9,
            height=2.75,
            risers=16,
            name="Main stair",
        )

        self.assertIsInstance(stair, Stair)
        self.assertTrue(stair.is_a("IfcStair"))
        self.assertIs(stair.element, stair)
        self.assertEqual(stair.PredefinedType, "STRAIGHT_RUN_STAIR")
        self.assertIsNone(stair.Representation)
        self.assertEqual(
            stair.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )

        flight = stair.flight
        self.assertTrue(flight.is_a("IfcStairFlight"))
        self.assertEqual(flight.PredefinedType, "STRAIGHT")
        self.assertEqual(flight.Decomposes[0].RelatingObject, stair)
        self.assertFalse(flight.ContainedInStructure)
        self.assertEqual(flight.NumberOfRisers, 16)
        self.assertEqual(flight.NumberOfTreads, 15)
        self.assertAlmostEqual(flight.RiserHeight, 2.75 / 16)
        self.assertAlmostEqual(flight.TreadLength, 3 / 15)
        common = ifcopenshell.util.element.get_pset(
            flight, "Pset_StairFlightCommon"
        )
        self.assertEqual(common["NumberOfRiser"], 16)
        self.assertEqual(common["NumberOfTreads"], 15)

        placement = ifcopenshell.util.placement.get_local_placement(
            flight.ObjectPlacement
        )
        self.assertEqual(tuple(placement[:3, 3]), (2, 1, 0))
        body = ifcopenshell.util.representation.get_representation(
            flight, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "Tessellation")
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), flight
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 3)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 0.9)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 2.75)
        self.assert_surface_style(flight, (200 / 255, 176 / 255, 144 / 255))

        drawing = house.add_drawing("Ground plan", 3.5, 1, 1.6, 5)
        other_drawing = house.add_drawing("Other plan", 3.5, 1, 1.6, 5)
        annotation = drawing.add_stair_annotation(stair)

        self.assertEqual(annotation.ObjectType, "LINEWORK")
        annotation_representation = annotation.Representation.Representations[0]
        self.assertEqual(
            annotation_representation.RepresentationType,
            "GeometricCurveSet",
        )
        curve_set = annotation_representation.Items[0]
        # Outline + one line per internal tread + shaft + arrowhead. There is
        # deliberately no zigzag stair break symbol.
        self.assertEqual(len(curve_set.Elements), stair.treads + 2)
        drawing_members = set(drawing.group.IsGroupedBy[0].RelatedObjects)
        other_members = set(other_drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(annotation, drawing_members)
        self.assertFalse(
            any(
                member.is_a("IfcAnnotation") and member.ObjectType == "TEXT"
                for member in drawing_members
            )
        )
        self.assertEqual(other_members, {other_drawing.element})

        with TemporaryDirectory() as directory:
            output = Path(directory) / "stairs.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcStair")), 1)
            self.assertEqual(len(reopened.by_type("IfcStairFlight")), 1)

    def test_creates_chimney_with_flue_and_scoped_plan_symbol(self) -> None:
        house = House("My house", colors={"chimney": "#B8A99A"})
        ground = house.storey("Ground floor", elevation=0.25)
        chimney = ground.chimney(
            (2, 3),
            size=0.5,
            height=6.5,
            flue_diameter=0.18,
            start_height=0.1,
            name="Main chimney",
        )

        self.assertIsInstance(chimney, Chimney)
        self.assertTrue(chimney.is_a("IfcChimney"))
        self.assertIs(chimney.element, chimney)
        self.assertEqual(chimney.PredefinedType, "NOTDEFINED")
        self.assertEqual(chimney.center, (2, 3))
        self.assertEqual(chimney.end_height, 6.6)
        self.assertEqual(
            chimney.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            chimney.ObjectPlacement
        )
        self.assertEqual(tuple(placement[:2, 3]), (2, 3))
        self.assertAlmostEqual(placement[2, 3], 0.35)

        body = ifcopenshell.util.representation.get_representation(
            chimney, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "SweptSolid")
        profile = body.Items[0].SweptArea
        self.assertTrue(profile.is_a("IfcArbitraryProfileDefWithVoids"))
        self.assertEqual(len(profile.InnerCurves), 1)
        self.assertTrue(profile.InnerCurves[0].is_a("IfcCircle"))
        self.assertAlmostEqual(profile.InnerCurves[0].Radius, 0.09)
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), chimney
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 0.5)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 0.5)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 6.5)
        expected_volume = (0.5**2 - 3.141592653589793 * 0.09**2) * 6.5
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            expected_volume,
            delta=0.002,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                chimney, "Pset_ChimneyCommon", "NumberOfDrafts"
            ),
            1,
        )
        self.assert_surface_style(
            chimney, (184 / 255, 169 / 255, 154 / 255)
        )

        drawing = house.add_drawing("Ground plan", 2, 3, 1.6, 3)
        other_drawing = house.add_drawing("Other plan", 2, 3, 1.6, 3)
        outline = drawing.add_chimney_annotation(chimney)
        drawing_members = set(drawing.group.IsGroupedBy[0].RelatedObjects)
        fill = next(
            member
            for member in drawing_members
            if member.is_a("IfcAnnotation")
            and ifcopenshell.util.element.get_pset(
                member, "EPset_Annotation", "Classes"
            )
            == "chimney-flue-fill"
        )
        self.assertEqual(outline.ObjectType, "LINEWORK")
        outline_curve = (
            outline.Representation.Representations[0].Items[0].Elements[0]
        )
        self.assertTrue(outline_curve.is_a("IfcIndexedPolyCurve"))
        self.assertEqual(len(outline_curve.Points.CoordList), 33)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                fill, "EPset_Annotation", "Classes"
            ),
            "chimney-flue-fill",
        )
        self.assertEqual(
            set(other_drawing.group.IsGroupedBy[0].RelatedObjects),
            {other_drawing.element},
        )

        upper = house.storey("Upper floor", elevation=3.25)
        upper_wall = upper.wall((0, 0), (1, 0), thickness=0.2, height=2.8)
        upper_drawing = house.add_drawing(
            "Upper plan", 2, 3, 4.25, 3, storeys=[upper]
        )
        upper_drawing.add_chimney_annotation(chimney)
        upper_include = ifcopenshell.util.element.get_pset(
            upper_drawing.element,
            "EPset_Drawing",
            "Include",
        )
        self.assertEqual(
            upper_include,
            f'location="{upper.element.GlobalId}"+{chimney.GlobalId}',
        )
        selected_elements = ifcopenshell.util.selector.filter_elements(
            house.model,
            upper_include,
        )
        self.assertIn(chimney, selected_elements)
        self.assertIn(upper_wall, selected_elements)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "chimney.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcChimney")), 1)

    def test_rejects_invalid_chimneys_and_duplicate_symbols(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(ValueError, "size"):
            ground.chimney((0, 0), size=0, height=5, flue_diameter=0.18)
        with self.assertRaisesRegex(ValueError, "height"):
            ground.chimney((0, 0), size=0.5, height=0, flue_diameter=0.18)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            ground.chimney((0, 0), size=0.5, height=5, flue_diameter=0)
        with self.assertRaisesRegex(ValueError, "smaller than size"):
            ground.chimney((0, 0), size=0.5, height=5, flue_diameter=0.5)

        chimney = ground.chimney(
            (0, 0), size=0.5, height=5, flue_diameter=0.18
        )
        drawing = house.add_drawing("Ground plan", 0, 0, 1.6, 3)
        drawing.add_chimney_annotation(chimney)
        with self.assertRaisesRegex(ValueError, "already has"):
            drawing.add_chimney_annotation(chimney)

    def test_rejects_invalid_straight_stairs_and_duplicate_symbols(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(ValueError, "different points"):
            ground.stair((1, 1), (1, 1), width=0.9, height=2.75, risers=16)
        with self.assertRaisesRegex(ValueError, "width"):
            ground.stair((0, 0), (3, 0), width=0, height=2.75, risers=16)
        with self.assertRaisesRegex(TypeError, "integer"):
            ground.stair((0, 0), (3, 0), width=0.9, height=2.75, risers=15.5)
        with self.assertRaisesRegex(ValueError, "at least 2"):
            ground.stair((0, 0), (3, 0), width=0.9, height=2.75, risers=1)
        with self.assertRaisesRegex(TypeError, "underside"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                underside=True,
            )
        with self.assertRaisesRegex(ValueError, "underside"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                underside="curved",
            )
        with self.assertRaisesRegex(ValueError, "waist_thickness"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                underside="sloped",
                waist_thickness=0,
            )
        with self.assertRaisesRegex(ValueError, "too large"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                underside="sloped",
                waist_thickness=3,
            )
        with self.assertRaisesRegex(ValueError, "define a rectangle"):
            ground.stair_landing(
                (0, 0), (2, 0), height=1.5, thickness=0.2
            )
        with self.assertRaisesRegex(ValueError, "thickness"):
            ground.stair_landing(
                (0, 0), (2, 1), height=1.5, thickness=0
            )

        stair = ground.stair(
            (0, 0), (3, 0), width=0.9, height=2.75, risers=16
        )
        drawing = house.add_drawing("Ground plan", 1.5, 0, 1.6, 5)
        drawing.add_stair_annotation(stair)
        with self.assertRaisesRegex(ValueError, "already has"):
            drawing.add_stair_annotation(stair)

    def test_cuts_open_space_below_a_sloped_stair_underside(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        stair = ground.stair(
            (0, 0),
            (3, 0),
            width=0.9,
            height=2.75,
            risers=16,
            underside="sloped",
            waist_thickness=0.15,
        )
        solid_stair = ground.stair(
            (0, 2),
            (3, 2),
            width=0.9,
            height=2.75,
            risers=16,
        )

        self.assertEqual(stair.underside, "sloped")
        self.assertAlmostEqual(stair.waist_thickness, 0.15)
        self.assertEqual(solid_stair.underside, "solid")
        self.assertIsNone(solid_stair.waist_thickness)
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                stair.flight,
                "Pset_StairFlightCommon",
                "WaistThickness",
            ),
            0.15,
        )

        body = ifcopenshell.util.representation.get_representation(
            stair.flight, "Model", "Body", "MODEL_VIEW"
        )
        coordinates = body.Items[0].Coordinates.CoordList
        stepped_rise = stair.treads * stair.riser_height
        pitch_cosine = stair.length / hypot(stair.length, stepped_rise)
        vertical_offset = stair.waist_thickness / pitch_cosine
        expected_start_x = vertical_offset * stair.length / stepped_rise
        self.assertAlmostEqual(coordinates[1][0], expected_start_x)
        self.assertAlmostEqual(coordinates[1][2], 0)
        self.assertAlmostEqual(coordinates[2][0], stair.length)
        self.assertAlmostEqual(
            coordinates[2][2],
            stepped_rise - vertical_offset,
        )

        settings = ifcopenshell.geom.settings()
        open_shape = ifcopenshell.geom.create_shape(settings, stair.flight)
        solid_shape = ifcopenshell.geom.create_shape(
            settings, solid_stair.flight
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(open_shape.geometry), stair.length
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(open_shape.geometry), stair.height
        )
        self.assertLess(
            ifcopenshell.util.shape.get_volume(open_shape.geometry),
            ifcopenshell.util.shape.get_volume(solid_shape.geometry),
        )

    def test_chains_an_elevated_stair_flight_from_the_previous_flight(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        lower = ground.stair(
            (0, 3),
            (0, 0),
            width=1,
            height=1.5,
            risers=9,
            name="Lower flight",
        )
        upper = ground.stair(
            (-1, 0),
            (-1, 3),
            width=1,
            height=1.5,
            risers=9,
            start_height=lower.end_height,
            name="Upper flight",
        )
        landing = ground.stair_landing(
            (-1.5, -1),
            (0.5, 0),
            height=lower.end_height,
            thickness=0.2,
            name="Half landing",
            color="#C8B090",
        )

        self.assertEqual(lower.start_height, 0)
        self.assertEqual(lower.end_height, 1.5)
        self.assertEqual(upper.start_height, lower.end_height)
        self.assertEqual(upper.end_height, 3)
        upper_placement = ifcopenshell.util.placement.get_local_placement(
            upper.flight.ObjectPlacement
        )
        self.assertAlmostEqual(upper_placement[2, 3], 1.75)
        self.assertTrue(landing.is_a("IfcSlab"))
        self.assertEqual(landing.PredefinedType, "LANDING")
        self.assertEqual(
            landing.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        landing_placement = ifcopenshell.util.placement.get_local_placement(
            landing.ObjectPlacement
        )
        self.assertEqual(tuple(landing_placement[:2, 3]), (-1.5, -1))
        self.assertAlmostEqual(landing_placement[2, 3], 1.55)
        landing_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), landing
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(landing_shape.geometry), 2
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(landing_shape.geometry), 1
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(landing_shape.geometry), 0.2
        )
        self.assert_surface_style(landing, (200 / 255, 176 / 255, 144 / 255))

    def test_creates_a_decomposed_miako_slab_from_a_mixed_layout(self) -> None:
        house = House(
            "My house",
            colors={"slab": "#AAAAAA"},
        )
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Ground-floor ceiling",
            start=(0, 0),
            end=(0, 8),
            top=0,
            direction=(1, 0),
            structure=["wide", "beam", "narrow", "beam"],
        )

        self.assertIsInstance(slab, MiakoSlab)
        self.assertTrue(slab.is_a("IfcSlab"))
        self.assertIs(slab.element, slab)
        self.assertEqual(slab.PredefinedType, "FLOOR")
        self.assertEqual(slab.start, (0, 0))
        self.assertEqual(slab.end, (0, 8))
        self.assertEqual(slab.direction, (1, 0))
        self.assertEqual(
            slab.structure,
            ("wide", "beam", "narrow", "beam"),
        )
        self.assertEqual(slab.length, 8)
        self.assertAlmostEqual(slab.width, 1.125)
        self.assertEqual(
            slab.footprint,
            ((0, 0), (0, 8), (1.125, 8.0), (1.125, 0.0)),
        )
        self.assertAlmostEqual(slab.height, 0.25)
        self.assertAlmostEqual(slab.bottom, -0.25)
        self.assertEqual(
            slab.ContainedInStructure[0].RelatingStructure,
            upper.element,
        )
        slab_placement = ifcopenshell.util.placement.get_local_placement(
            slab.ObjectPlacement
        )
        self.assertEqual(tuple(slab_placement[:2, 3]), (0, 0))
        self.assertAlmostEqual(slab_placement[2, 3], 2.75)
        self.assertAlmostEqual(np.linalg.det(slab_placement[:3, :3]), 1)

        plan = ifcopenshell.util.representation.get_representation(
            slab, "Plan", "Body", "PLAN_VIEW"
        )
        self.assertEqual(plan.RepresentationType, "Curve2D")
        self.assertEqual(
            plan.Items[0].Points.CoordList,
            (
                (0.0, 0.0),
                (8.0, 0.0),
                (8.0, -1.125),
                (0.0, -1.125),
                (0.0, 0.0),
            ),
        )

        self.assertEqual(len(slab.beams), 2)
        self.assertEqual(len(slab.beam_shells), 2)
        self.assertEqual(len(slab.reinforcements), 2)
        self.assertEqual(len(slab.blocks), 64)
        self.assertEqual(len(slab.components), 71)
        decomposition = slab.IsDecomposedBy[0]
        self.assertTrue(decomposition.is_a("IfcRelAggregates"))
        self.assertEqual(set(decomposition.RelatedObjects), set(slab.components))
        self.assertTrue(
            all(not component.ContainedInStructure for component in slab.components)
        )

        first_beam, second_beam = slab.beams
        self.assertEqual(
            ifcopenshell.util.element.get_predefined_type(first_beam),
            "JOIST",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_type(first_beam),
            ifcopenshell.util.element.get_type(second_beam),
        )
        first_beam_placement = ifcopenshell.util.placement.get_local_placement(
            first_beam.ObjectPlacement
        )
        second_beam_placement = ifcopenshell.util.placement.get_local_placement(
            second_beam.ObjectPlacement
        )
        self.assertEqual(tuple(first_beam_placement[:2, 3]), (0.455, 0))
        self.assertAlmostEqual(second_beam_placement[0, 3], 0.955)
        self.assertAlmostEqual(second_beam_placement[1, 3], 0)
        beam_body = ifcopenshell.util.representation.get_representation(
            first_beam, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(beam_body.RepresentationType, "MappedRepresentation")
        beam_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), first_beam
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(beam_shape.geometry), 8
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(beam_shape.geometry), 0.13
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(beam_shape.geometry), 0.06 - 0.02
        )

        def mapped_rgb(
            product: ifcopenshell.entity_instance,
        ) -> tuple[float, float, float]:
            representation = ifcopenshell.util.representation.get_representation(
                product, "Model", "Body", "MODEL_VIEW"
            )
            mapped_representation = (
                representation.Items[0].MappingSource.MappedRepresentation
            )
            surface_style = mapped_representation.Items[0].StyledByItem[0].Styles[0]
            shading = next(
                style
                for style in surface_style.Styles
                if style.is_a("IfcSurfaceStyleShading")
            )
            return (
                shading.SurfaceColour.Red,
                shading.SurfaceColour.Green,
                shading.SurfaceColour.Blue,
            )

        self.assertEqual(
            mapped_rgb(first_beam),
            (191 / 255, 195 / 255, 197 / 255),
        )

        first_shell = slab.beam_shells[0]
        first_reinforcement = slab.reinforcements[0]
        shell_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), first_shell
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(shell_shape.geometry), 0.17
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(shell_shape.geometry), 0.06
        )
        self.assertEqual(
            mapped_rgb(first_shell),
            (217 / 255, 130 / 255, 69 / 255),
        )
        self.assertEqual(
            ifcopenshell.util.element.get_material(first_shell).Name,
            "MIAKO beam ceramic",
        )
        self.assertEqual(mapped_rgb(first_reinforcement), (0.2, 0.2, 0.2))
        reinforcement_type = ifcopenshell.util.element.get_type(
            first_reinforcement
        )
        reinforcement_body = ifcopenshell.util.representation.get_representation(
            reinforcement_type, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(len(reinforcement_body.Items), 3)
        wire_profile = (
            reinforcement_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        )
        self.assertIn((-0.082, 0.175), wire_profile)
        self.assertIn((-0.08800000000000001, 0.175), wire_profile)
        reinforcement_dots = [
            item.SweptArea.OuterCurve
            for item in reinforcement_body.Items[1:]
        ]
        self.assertTrue(
            all(dot.is_a("IfcCircle") for dot in reinforcement_dots)
        )
        for dot, expected_y in zip(reinforcement_dots, (-0.055, -0.115)):
            dot_y, dot_z = dot.Position.Location.Coordinates
            self.assertAlmostEqual(dot_y, expected_y)
            self.assertAlmostEqual(dot_z, 0.04)
            self.assertAlmostEqual(dot.Radius, 0.006)

        wide_blocks = [
            block
            for block in slab.blocks
            if ifcopenshell.util.element.get_predefined_type(block)
            == "MIAKO wide block"
        ]
        narrow_blocks = [
            block
            for block in slab.blocks
            if ifcopenshell.util.element.get_predefined_type(block)
            == "MIAKO narrow block"
        ]
        self.assertEqual(len(wide_blocks), 32)
        self.assertEqual(len(narrow_blocks), 32)
        self.assertEqual(
            len({ifcopenshell.util.element.get_type(block) for block in wide_blocks}),
            1,
        )
        self.assertEqual(
            len(
                {
                    ifcopenshell.util.element.get_type(block)
                    for block in narrow_blocks
                }
            ),
            1,
        )
        wide_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), wide_blocks[0]
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(wide_shape.geometry), 0.25
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(wide_shape.geometry), 0.525
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(wide_shape.geometry), 0.19
        )
        wide_type = ifcopenshell.util.element.get_type(wide_blocks[0])
        wide_type_body = ifcopenshell.util.representation.get_representation(
            wide_type, "Model", "Body", "MODEL_VIEW"
        )
        wide_profile = wide_type_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        self.assertEqual(
            wide_profile[:3],
            ((0.0, 0.0), (-0.455, 0.0), (-0.455, 0.06)),
        )
        self.assertIn((-0.49, 0.06), wide_profile)
        self.assertIn((-0.49, 0.19), wide_profile)
        self.assertIn((0.035, 0.06), wide_profile)
        self.assertIn((0.035, 0.19), wide_profile)
        beam_type = ifcopenshell.util.element.get_type(first_beam)
        beam_type_body = ifcopenshell.util.representation.get_representation(
            beam_type, "Model", "Body", "MODEL_VIEW"
        )
        beam_profile = beam_type_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        self.assertEqual(
            tuple(
                tuple(round(coordinate, 9) for coordinate in point)
                for point in beam_profile[:4]
            ),
            ((-0.02, 0.02), (-0.15, 0.02), (-0.15, 0.06), (-0.02, 0.06)),
        )
        self.assertTrue(
            beam_type_body.Items[0].SweptArea.is_a(
                "IfcArbitraryClosedProfileDef"
            )
        )
        self.assertEqual(mapped_rgb(wide_blocks[0]), (0, 0, 1))
        self.assertEqual(mapped_rgb(narrow_blocks[0]), (0, 128 / 255, 0))
        self.assertEqual(
            ifcopenshell.util.element.get_material(wide_blocks[0]).Name,
            "MIAKO block ceramic",
        )
        self.assertNotEqual(
            ifcopenshell.util.element.get_material(first_shell),
            ifcopenshell.util.element.get_material(wide_blocks[0]),
        )

        topping_placement = ifcopenshell.util.placement.get_local_placement(
            slab.topping_element.ObjectPlacement
        )
        self.assertAlmostEqual(topping_placement[2, 3], 2.75)
        topping_body = ifcopenshell.util.representation.get_representation(
            slab.topping_element, "Model", "Body", "MODEL_VIEW"
        )
        topping_profile = (
            topping_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        )
        self.assertIn((-0.49, 0.19), topping_profile)
        self.assertIn((-0.49, 0.06), topping_profile)
        self.assertIn((-0.59, 0.06), topping_profile)
        self.assertIn((-0.59, 0.19), topping_profile)
        self.assertIn((-1.125, 0.25), topping_profile)
        topping_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), slab.topping_element
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(topping_shape.geometry), 8
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(topping_shape.geometry), 1.125
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(topping_shape.geometry), 0.19
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                slab, "Pset_SlabCommon", "LoadBearing"
            ),
            True,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                slab, "BBIM_MiakoSlab", "Structure"
            ),
            "wide,beam,narrow,beam",
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                slab, "BBIM_MiakoSlab", "ConcreteCoverRibDepth"
            ),
            0.19,
        )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "miako.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcSlab")), 1)
            self.assertEqual(len(reopened.by_type("IfcBeam")), 2)
            self.assertEqual(len(reopened.by_type("IfcBuildingElementPart")), 69)
            self.assertEqual(len(reopened.by_type("IfcBeamType")), 1)
            self.assertEqual(
                len(reopened.by_type("IfcBuildingElementPartType")), 4
            )

    def test_handles_partial_miako_blocks_and_validates_the_layout(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Short ceiling",
            start=(0, 0),
            end=(0, 0.6),
            top=-0.1,
            direction=(-1, 0),
            structure=["wide", "beam", "narrow", "beam"],
            block_height=0.15,
            beam_height=0.06,
            topping=0.06,
        )

        self.assertEqual(len(slab.blocks), 6)
        block_lengths = sorted(
            {
                round(
                    ifcopenshell.util.shape.get_x(
                        ifcopenshell.geom.create_shape(
                            ifcopenshell.geom.settings(), block
                        ).geometry
                    ),
                    9,
                )
                for block in slab.blocks
            }
        )
        self.assertEqual(block_lengths, [0.1, 0.25])
        plan = ifcopenshell.util.representation.get_representation(
            slab, "Plan", "Body", "PLAN_VIEW"
        )
        self.assertEqual(plan.Items[0].Points.CoordList[2], (0.6, 1.125))
        first_beam_placement = ifcopenshell.util.placement.get_local_placement(
            slab.beams[0].ObjectPlacement
        )
        self.assertAlmostEqual(first_beam_placement[0, 3], -0.455)
        self.assertAlmostEqual(first_beam_placement[2, 3], 2.69)
        self.assertAlmostEqual(slab.height, 0.21)
        self.assertAlmostEqual(slab.beam_height, 0.06)
        short_beam_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), slab.beams[0]
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(short_beam_shape.geometry), 0.04
        )
        short_shell_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), slab.beam_shells[0]
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(short_shell_shape.geometry), 0.06
        )
        short_reinforcement_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), slab.reinforcements[0]
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(short_reinforcement_shape.geometry),
            0.175 - (0.04 - 0.006),
            places=4,
        )
        self.assertGreater(0.175, slab.block_height)
        short_cover_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), slab.topping_element
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(short_cover_shape.geometry), 0.15
        )

        valid_arguments = {
            "start": (0, 0),
            "end": (0, 2),
            "top": 0,
            "direction": (1, 0),
            "structure": ["wide", "beam"],
        }
        with self.assertRaisesRegex(ValueError, "different points"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"end": (0, 0)})
            )
        with self.assertRaisesRegex(ValueError, "zero vector"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"direction": (0, 0)})
            )
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"direction": (1, 1)})
            )
        with self.assertRaisesRegex(TypeError, "sequence"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"structure": "wide"})
            )
        with self.assertRaisesRegex(ValueError, "at least one item"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"structure": []})
            )
        with self.assertRaisesRegex(ValueError, "must be one of"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"structure": ["wide", "rib"]})
            )
        with self.assertRaisesRegex(ValueError, "separated by a beam"):
            upper.miako_slab(
                "Invalid",
                **(valid_arguments | {"structure": ["wide", "narrow", "beam"]}),
            )
        with self.assertRaisesRegex(ValueError, "at least one beam"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"structure": ["wide"]})
            )
        with self.assertRaisesRegex(ValueError, "at least one block bay"):
            upper.miako_slab(
                "Invalid", **(valid_arguments | {"structure": ["beam"]})
            )
        with self.assertRaisesRegex(ValueError, "block_length"):
            upper.miako_slab(
                "Invalid", **valid_arguments, block_length=0
            )
        with self.assertRaisesRegex(ValueError, "beam_height"):
            upper.miako_slab(
                "Invalid", **valid_arguments, beam_height=0.2
            )
        with self.assertRaisesRegex(ValueError, "reinforcement apex"):
            upper.miako_slab(
                "Invalid",
                **valid_arguments,
                block_height=0.1,
                topping=0.07,
                beam_height=0.06,
            )

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

    def test_adds_a_simplified_floor_layer_above_a_storey(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3.21)
        floor = upper.floor_layer(
            "Upper-floor build-up",
            outline=((0.25, 0.25), (11.75, 0.25), (11.75, 7.75), (0.25, 7.75)),
            thickness=0.11,
            material="Floor build-up",
            color="#ffffff",
        )

        self.assertTrue(floor.is_a("IfcSlab"))
        self.assertEqual(floor.PredefinedType, "FLOOR")
        self.assertEqual(
            floor.ContainedInStructure[0].RelatingStructure,
            upper.element,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            floor.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 3.21)
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), floor
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 11.5)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 7.5)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 0.11)
        self.assertEqual(ifcopenshell.util.element.get_material(floor).Name, "Floor build-up")
        self.assertFalse(
            ifcopenshell.util.element.get_pset(
                floor, "Pset_SlabCommon", "LoadBearing"
            )
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                floor, "BBIM_FloorLayer", "Thickness"
            ),
            0.11,
        )

        with self.assertRaisesRegex(ValueError, "thickness"):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0,
            )
        with self.assertRaisesRegex(ValueError, "non-zero area"):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (2, 0)),
                thickness=0.1,
            )

    def test_stacks_an_elevated_wall_part_above_a_lower_wall(self) -> None:
        house = House("My house")
        wall_type = house.wall_type("Brick", layers=[("Brick", 0.2)])
        upper = house.storey("Upper floor", elevation=3)
        lower = upper.wall(
            (0, 0),
            (6, 0),
            wall_type=wall_type,
            height=2.4,
        )
        raised = upper.wall(
            (2, 0),
            (4, 0),
            wall_type=wall_type,
            start_height=lower.end_height,
            height=1.2,
        )

        self.assertEqual(lower.start_height, 0)
        self.assertEqual(lower.end_height, 2.4)
        self.assertEqual(raised.start_height, 2.4)
        self.assertAlmostEqual(raised.end_height, 3.6)
        placement = ifcopenshell.util.placement.get_local_placement(
            raised.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 5.4)
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), raised
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 2)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 0.2)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 1.2)

        window = raised.add_window(
            at=0.5,
            width=1,
            sill_height=2.5,
            height=3.3,
        )
        window_placement = ifcopenshell.util.placement.get_local_placement(
            window.ObjectPlacement
        )
        self.assertAlmostEqual(window_placement[2, 3], 5.5)
        with self.assertRaisesRegex(ValueError, "below the wall"):
            raised.add_opening(
                at=0,
                width=0.25,
                sill_height=2.3,
                height=2.4,
            )
        with self.assertRaisesRegex(ValueError, "within the wall height"):
            raised.add_opening(
                at=1.75,
                width=0.25,
                sill_height=3.5,
                height=3.7,
            )

        adjoining = upper.wall(
            (4, 0),
            (4, 2),
            wall_type=wall_type,
            start_height=2.4,
            height=1.2,
        )
        upper.connect_wall(raised, adjoining)
        regenerated_placement = ifcopenshell.util.placement.get_local_placement(
            raised.ObjectPlacement
        )
        self.assertAlmostEqual(regenerated_placement[2, 3], 5.4)

    def test_clips_a_wall_with_three_world_coordinate_planes(self) -> None:
        house = House("My house", colors={"wall": "white"})
        upper = house.storey("Upper floor", elevation=3)
        cuts = [
            ((0, 0, 4), (0, 1, 4), (5, 0, 9)),
            ((5, 0, 9), (5, 1, 9), (10, 0, 4)),
            ((0, 0, 8.5), (1, 0, 8.5), (0, 1, 8.5)),
        ]
        wall = upper.wall(
            (0, 0),
            (10, 0),
            thickness=0.2,
            height=6,
            cuts=cuts,
        )

        self.assertEqual(wall.cuts, tuple(cuts))
        body = ifcopenshell.util.representation.get_representation(
            wall, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "Clipping")
        item = body.Items[0]
        clipping_results = []
        while item.is_a("IfcBooleanClippingResult"):
            clipping_results.append(item)
            item = item.FirstOperand
        self.assertEqual(len(clipping_results), 3)
        self.assertTrue(item.is_a("IfcExtrudedAreaSolid"))
        boolean_ids = json.loads(
            ifcopenshell.util.element.get_pset(
                wall, "BBIM_Boolean", "Data"
            )
        )
        self.assertEqual(
            boolean_ids,
            [result.id() for result in reversed(clipping_results)],
        )

        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), wall
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 10)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(shape.geometry), 0.2
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(shape.geometry), 5.5
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry), 6.95
        )
        vertices = ifcopenshell.util.shape.get_vertices(shape.geometry)
        self.assertAlmostEqual(min(vertex[0] for vertex in vertices), 0)
        self.assertAlmostEqual(max(vertex[0] for vertex in vertices), 10)
        self.assertAlmostEqual(max(vertex[2] for vertex in vertices), 5.5)
        self.assert_surface_style(wall, (1, 1, 1))

        with TemporaryDirectory() as directory:
            output = Path(directory) / "cut-wall.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            reopened_wall = reopened.by_type("IfcWall")[0]
            reopened_body = ifcopenshell.util.representation.get_representation(
                reopened_wall, "Model", "Body", "MODEL_VIEW"
            )
            self.assertEqual(reopened_body.RepresentationType, "Clipping")

    def test_preserves_wall_plane_cuts_when_connecting_layered_walls(
        self,
    ) -> None:
        house = House("My house")
        wall_type = house.wall_type("Brick", layers=[("Brick", 0.2)])
        ground = house.storey("Ground floor", elevation=0)
        cut_wall = ground.wall(
            (0, 0),
            (5, 0),
            wall_type=wall_type,
            height=3,
            cuts=[((0, 0, 2.5), (1, 0, 2.5), (0, 1, 2.5))],
        )
        adjoining_wall = ground.wall(
            (5, 0),
            (5, 3),
            wall_type=wall_type,
            height=3,
        )

        ground.connect_wall(cut_wall, adjoining_wall)

        body = ifcopenshell.util.representation.get_representation(
            cut_wall, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "Clipping")
        self.assertTrue(body.Items[0].is_a("IfcBooleanClippingResult"))
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), cut_wall
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 2.5)
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    cut_wall, "BBIM_Boolean", "Data"
                )
            ),
            [body.Items[0].id()],
        )

    def test_adds_doors_and_windows_as_semantic_wall_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((1, 2), (1, 7), thickness=0.25, height=3)

        door = wall.add_door(
            at=0.5,
            width=0.9,
            height=2.3,
            clear_height=1.97,
            sill_height=0.2,
            opening_width=1.1,
            opening_height=2.4,
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
        self.assertAlmostEqual(door.OverallHeight, 2.1)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "ClearHeight"
            ),
            1.97,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "OpenAngle"
            ),
            45,
        )
        self.assertFalse(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "ReverseSwing"
            )
        )
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
        self.assertAlmostEqual(opening_placement[2, 3], 0.2)
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
            "door-overhead dashed",
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "OpeningBottom"
            ),
            0.2,
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "OpeningTop"
            ),
            2.4,
        )
        self.assertNotIn(
            overhead.GlobalId,
            _overhead_mask_global_ids(house.model, 0.1),
        )
        self.assertIn(
            overhead.GlobalId,
            _overhead_mask_global_ids(house.model, 1.5),
        )
        overhead_representation = ifcopenshell.util.representation.get_representation(
            overhead, "Plan", "Annotation", "PLAN_VIEW"
        )
        self.assertEqual(overhead_representation.RepresentationType, "GeometricCurveSet")
        overhead_coordinates = [
            curve.Points.CoordList
            for curve in overhead_representation.Items[0].Elements
        ]
        self.assertEqual(
            overhead_coordinates,
            [
                ((0.025, -0.125), (1.0750000000000002, -0.125)),
                ((0.025, 0.125), (1.0750000000000002, 0.125)),
            ],
        )
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
        self.assertEqual(_close_door_bodies(house.model), 1)
        closed_panel_placement = ifcopenshell.util.placement.get_axis2placement(
            framing_body.Items[0].Position
        )
        self.assertAlmostEqual(closed_panel_placement[0, 0], 1)
        self.assertAlmostEqual(closed_panel_placement[1, 0], 0)

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
        self.assertAlmostEqual(door_placement[2, 3], 0.2)
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
        with self.assertRaisesRegex(TypeError, "reverse_swing"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                reverse_swing="yes",
            )
        with self.assertRaisesRegex(ValueError, "sliding doors"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                operation="SLIDING_TO_LEFT",
                reverse_swing=True,
            )
        with self.assertRaisesRegex(ValueError, "sill_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                sill_height=-0.1,
            )
        with self.assertRaisesRegex(ValueError, "wall height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=3.1,
                sill_height=1,
            )
        with self.assertRaisesRegex(ValueError, "greater than sill_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=1,
                sill_height=1,
            )
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
        with self.assertRaisesRegex(ValueError, "opening_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                sill_height=1,
                opening_height=1,
            )
        with self.assertRaisesRegex(ValueError, "clear_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                clear_height=0,
            )
        with self.assertRaisesRegex(ValueError, "clear_height"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                clear_height=2.2,
            )
        with self.assertRaisesRegex(TypeError, "show_overhead"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                show_overhead="yes",
            )
        with self.assertRaisesRegex(TypeError, "show_overhead"):
            wall.add_opening(
                at=1,
                width=1,
                height=2,
                show_overhead="yes",
            )
        with self.assertRaisesRegex(ValueError, "greater than sill_height"):
            wall.add_opening(
                at=1,
                width=1,
                height=1,
                sill_height=1,
            )
        with self.assertRaisesRegex(ValueError, "partition must be one of"):
            wall.add_window(
                at=3,
                width=1,
                height=2,
                sill_height=1,
                partition="ROUND",
            )
        with self.assertRaisesRegex(ValueError, "align must be one of"):
            wall.add_window(
                at=3,
                width=1,
                height=2,
                sill_height=1,
                align="outside",
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            wall.add_window(
                at=3,
                width=1,
                height=2,
                sill_height=1,
                glass_transparency=1.1,
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
            wall.add_opening(at=1, width=1, height=2)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            wall.add_window(
                at=1,
                width=1,
                height=2,
                sill_height=1,
            )

    def test_reverses_door_swing_without_changing_the_hinge_side(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.25, height=3)
        normal = wall.add_door(
            at=0.25,
            width=0.9,
            height=2.1,
            operation="SINGLE_SWING_LEFT",
            open_angle=45,
            show_overhead=False,
        )
        reversed_door = wall.add_door(
            at=2,
            width=0.9,
            height=2.1,
            operation="SINGLE_SWING_LEFT",
            open_angle=45,
            reverse_swing=True,
            show_overhead=False,
        )

        self.assertEqual(normal.OperationType, "SINGLE_SWING_LEFT")
        self.assertEqual(reversed_door.OperationType, normal.OperationType)

        def first_framing_placement(
            door: ifcopenshell.entity_instance,
        ) -> np.ndarray:
            framing = next(
                aspect
                for aspect in door.Representation.HasShapeAspects
                if aspect.Name == "Framing"
            )
            representation = next(
                representation
                for representation in framing.ShapeRepresentations
                if representation.ContextOfItems.ContextType == "Model"
            )
            return ifcopenshell.util.placement.get_axis2placement(
                representation.Items[0].Position
            )

        normal_placement = first_framing_placement(normal)
        reversed_placement = first_framing_placement(reversed_door)
        self.assertAlmostEqual(normal_placement[0, 3], reversed_placement[0, 3])
        self.assertAlmostEqual(normal_placement[1, 3], reversed_placement[1, 3])
        self.assertAlmostEqual(normal_placement[0, 0], reversed_placement[0, 0])
        self.assertAlmostEqual(normal_placement[1, 0], -reversed_placement[1, 0])

        normal_plan = ifcopenshell.util.representation.get_representation(
            normal, "Plan", "Body", "PLAN_VIEW"
        )
        reversed_plan = ifcopenshell.util.representation.get_representation(
            reversed_door, "Plan", "Body", "PLAN_VIEW"
        )
        for normal_lining, reversed_lining in zip(
            normal_plan.Items[:2], reversed_plan.Items[:2]
        ):
            self.assertEqual(
                normal_lining.Points.CoordList,
                reversed_lining.Points.CoordList,
            )

        positive_wall_face_y = wall.body_offset + wall.thickness
        negative_wall_face_y = wall.body_offset
        normal_leaf = normal_plan.Items[-1]
        reversed_leaf = reversed_plan.Items[-1]
        self.assertEqual(
            tuple(point[0] for point in normal_leaf.Points.CoordList),
            tuple(point[0] for point in reversed_leaf.Points.CoordList),
        )
        self.assertGreater(
            max(point[1] for point in normal_leaf.Points.CoordList),
            positive_wall_face_y,
        )
        self.assertLess(
            min(point[1] for point in reversed_leaf.Points.CoordList),
            negative_wall_face_y,
        )
        self.assertAlmostEqual(
            max(point[1] for point in normal_leaf.Points.CoordList)
            - positive_wall_face_y,
            negative_wall_face_y
            - min(point[1] for point in reversed_leaf.Points.CoordList),
        )
        normal_arc = normal_plan.Items[-2]
        reversed_arc = reversed_plan.Items[-2]
        self.assertAlmostEqual(
            normal_arc.BasisCurve.Position.Location.Coordinates[0],
            reversed_arc.BasisCurve.Position.Location.Coordinates[0],
        )
        self.assertAlmostEqual(
            normal_arc.BasisCurve.Position.Location.Coordinates[1],
            positive_wall_face_y,
        )
        self.assertAlmostEqual(
            reversed_arc.BasisCurve.Position.Location.Coordinates[1],
            negative_wall_face_y,
        )

    def test_adds_an_unfilled_semantic_wall_opening(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        wall = ground.wall((1, 2), (1, 7), thickness=0.25, height=3)
        opening = wall.add_opening(
            at=0.5,
            width=1.2,
            height=2.2,
            sill_height=0.2,
            name="Kitchen passage",
        )

        self.assertTrue(opening.is_a("IfcOpeningElement"))
        self.assertEqual(opening.Name, "Kitchen passage")
        self.assertEqual(opening.PredefinedType, "OPENING")
        self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement, wall)
        self.assertFalse(opening.HasFillings)
        placement = ifcopenshell.util.placement.get_local_placement(
            opening.ObjectPlacement
        )
        self.assertAlmostEqual(placement[0, 3], 1)
        self.assertAlmostEqual(placement[1, 3], 2.5)
        self.assertAlmostEqual(placement[2, 3], 0.45)
        body = ifcopenshell.util.representation.get_representation(
            opening, "Model", "Body", "MODEL_VIEW"
        )
        self.assertAlmostEqual(body.Items[0].Depth, 2)

        wall_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), wall
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(wall_shape.geometry),
            5 * 0.25 * 3 - 1.2 * 0.25 * 2,
        )
        overhead = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.ObjectType == "LINEWORK"
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "Classes"
            ),
            "door-overhead dashed",
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "OpeningBottom"
            ),
            0.2,
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                overhead, "EPset_Annotation", "OpeningTop"
            ),
            2.2,
        )
        self.assertNotIn(
            overhead.GlobalId,
            _overhead_mask_global_ids(house.model, 0.3),
        )
        self.assertIn(
            overhead.GlobalId,
            _overhead_mask_global_ids(house.model, 1.5),
        )
        overhead_representation = ifcopenshell.util.representation.get_representation(
            overhead, "Plan", "Annotation", "PLAN_VIEW"
        )
        self.assertEqual(
            [
                curve.Points.CoordList
                for curve in overhead_representation.Items[0].Elements
            ],
            [
                ((0.025, -0.125), (1.175, -0.125)),
                ((0.025, 0.125), (1.175, 0.125)),
            ],
        )
        drawing = house.add_drawing("Ground plan", 1, 4.5, 1.5, 4)
        self.assertIn(overhead, drawing.group.IsGroupedBy[0].RelatedObjects)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "opening.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcOpeningElement")), 1)
            self.assertEqual(len(reopened.by_type("IfcDoor")), 0)

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

    def test_adds_a_scoped_linear_dimension_with_extension_lines(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        drawing = house.add_drawing(
            "Ground plan", 2, 3, 1.6, 5, storeys=[ground]
        )
        other_drawing = house.add_drawing(
            "Other plan", 2, 3, 1.6, 5, storeys=[ground]
        )

        dimension = drawing.add_dimension(
            (1, 2),
            (4, 6),
            offset=0.5,
            name="Overall width",
        )

        self.assertEqual(dimension.is_a(), "IfcAnnotation")
        self.assertEqual(
            ifcopenshell.util.element.get_predefined_type(dimension),
            "DIMENSION",
        )
        self.assertEqual(dimension.Name, "Overall width")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                dimension, "BBIM_Dimension", "CustomUnit"
            ),
            ["Millimeters"],
        )
        representation = ifcopenshell.util.representation.get_representation(
            dimension, "Plan", "Annotation", "PLAN_VIEW"
        )
        self.assertEqual(representation.RepresentationType, "Curve2D")
        np.testing.assert_allclose(
            representation.Items[0].Points.CoordList,
            ((0.6, 2.3), (3.6, 6.3)),
            atol=1e-9,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            dimension.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], ground.elevation)

        extension = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.Name == "Overall width Extension Lines"
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                extension, "EPset_Annotation", "Classes"
            ),
            "dimension-extension fine",
        )
        extension_representation = ifcopenshell.util.representation.get_representation(
            extension, "Plan", "Annotation", "PLAN_VIEW"
        )
        extension_curves = extension_representation.Items[0].Elements
        self.assertEqual(len(extension_curves), 2)
        np.testing.assert_allclose(
            extension_curves[0].Points.CoordList,
            ((1, 2), (0.52, 2.36)),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            extension_curves[1].Points.CoordList,
            ((4, 6), (3.52, 6.36)),
            atol=1e-9,
        )

        drawing_members = set(drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(dimension, drawing_members)
        self.assertIn(extension, drawing_members)
        self.assertEqual(
            set(other_drawing.group.IsGroupedBy[0].RelatedObjects),
            {other_drawing.element},
        )

        dimension_without_extensions = drawing.add_dimension((0, 0), (2, 0))
        self.assertNotIn(
            f"{dimension_without_extensions.Name} Extension Lines",
            {annotation.Name for annotation in house.model.by_type("IfcAnnotation")},
        )

        with self.assertRaisesRegex(ValueError, "must be different points"):
            drawing.add_dimension((1, 1), (1, 1))
        with self.assertRaisesRegex(TypeError, "offset must be a number"):
            drawing.add_dimension((0, 0), (1, 0), offset="outside")

        with TemporaryDirectory() as directory:
            output = Path(directory) / "dimension.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            reopened_dimension = next(
                annotation
                for annotation in reopened.by_type("IfcAnnotation")
                if annotation.Name == "Overall width"
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    reopened_dimension, "BBIM_Dimension", "CustomUnit"
                ),
                ["Millimeters"],
            )

    def test_adds_a_manual_room_identifier_and_area_annotation(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        drawing = house.add_drawing(
            "Ground plan", 2, 3, 1.6, 5, storeys=[ground]
        )
        other_drawing = house.add_drawing(
            "Other plan", 2, 3, 1.6, 5, storeys=[ground]
        )

        identifier = drawing.add_room_annotation(
            (4.5, 3.2),
            identifier="P.01",
            area=8.3,
        )

        self.assertEqual(identifier.Name, "Ground plan Room P.01")
        self.assertEqual(identifier.ObjectType, "TEXT")
        self.assertEqual(
            identifier.Representation.Representations[0].Items[0].Literal,
            "P.01",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                identifier, "EPset_Annotation", "Classes"
            ),
            "room-annotation room-identifier",
        )
        metadata = ifcopenshell.util.element.get_pset(
            identifier, "EPset_RoomAnnotation"
        )
        self.assertEqual(metadata["Identifier"], "P.01")
        self.assertAlmostEqual(metadata["Area"], 8.3)

        members = set(drawing.group.IsGroupedBy[0].RelatedObjects)
        area = next(member for member in members if member.Name.endswith(" Area"))
        self.assertEqual(
            area.Representation.Representations[0].Items[0].Literal,
            "8,30 m²",
        )
        separator = next(
            member for member in members if member.Name.endswith(" Separator")
        )
        self.assertEqual(separator.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                separator, "EPset_Annotation", "Classes"
            ),
            "room-annotation-separator",
        )
        np.testing.assert_allclose(
            separator.Representation.Representations[0].Items[0].Points.CoordList,
            ((4.125, 3.2), (4.875, 3.2)),
            atol=1e-9,
        )
        self.assertEqual(
            set(other_drawing.group.IsGroupedBy[0].RelatedObjects),
            {other_drawing.element},
        )

        with self.assertRaisesRegex(ValueError, "area must be greater than zero"):
            drawing.add_room_annotation((1, 1), identifier="P.02", area=0)
        with self.assertRaisesRegex(ValueError, "identifier must not be empty"):
            drawing.add_room_annotation((1, 1), identifier=" ", area=5)

    def test_adds_a_rotated_drawing_scoped_entrance_arrow(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        drawing = house.add_drawing(
            "Ground plan", 2, 3, 1.6, 5, storeys=[ground]
        )
        other_drawing = house.add_drawing(
            "Other plan", 2, 3, 1.6, 5, storeys=[ground]
        )

        arrow = drawing.add_entrance_arrow(
            (4.5, 3.2),
            rotation=180,
            size=0.8,
            name="Main entrance",
        )

        self.assertEqual(arrow.Name, "Main entrance")
        self.assertEqual(arrow.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                arrow, "EPset_Annotation", "Classes"
            ),
            "entrance-arrow",
        )
        representation = ifcopenshell.util.representation.get_representation(
            arrow, "Plan", "Annotation", "PLAN_VIEW"
        )
        self.assertEqual(representation.RepresentationType, "GeometricCurveSet")
        curves = representation.Items[0].Elements
        np.testing.assert_allclose(
            curves[0].Points.CoordList,
            ((-0.4, 0.0), (0.4, 0.0)),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            curves[1].Points.CoordList,
            ((0.12, -0.28), (0.4, 0.0), (0.12, 0.28)),
            atol=1e-9,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            arrow.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement[:3, 3],
            (4.5, 3.2, ground.elevation),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            placement[:2, 0],
            (-1.0, 0.0),
            atol=1e-9,
        )
        self.assertIn(arrow, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(arrow, other_drawing.group.IsGroupedBy[0].RelatedObjects)

        with self.assertRaisesRegex(ValueError, "size must be greater than zero"):
            drawing.add_entrance_arrow((1, 1), size=0)
        with self.assertRaisesRegex(TypeError, "rotation must be a number"):
            drawing.add_entrance_arrow((1, 1), rotation="left")

    def test_automatically_adds_door_dimensions_to_included_drawings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        ground_wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=2.8)
        upper_wall = upper.wall((0, 0), (5, 0), thickness=0.2, height=2.8)
        first_door = ground_wall.add_door(
            at=0.5,
            width=0.8,
            height=2.1,
            clear_height=1.97,
        )
        upper_wall.add_door(at=0.5, width=0.9, height=2.1)

        drawing = house.add_drawing(
            "Ground plan",
            2.5,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotation_offset=0.05,
        )
        second_door = ground_wall.add_door(at=2, width=0.9, height=2.1)

        labels = [
            annotation
            for annotation in drawing.group.IsGroupedBy[0].RelatedObjects
            if "door-dimension"
            in (
                ifcopenshell.util.element.get_pset(
                    annotation, "EPset_Annotation", "Classes"
                )
                or ""
            ).split()
        ]
        values_by_door = {}
        for label in labels:
            related_door = next(
                relation.RelatingProduct
                for relation in label.HasAssignments
                if relation.is_a("IfcRelAssignsToProduct")
            )
            values_by_door.setdefault(related_door, set()).add(
                label.Representation.Representations[0].Items[0].Literal
            )
        self.assertEqual(
            values_by_door,
            {
                first_door: {"800", "1970"},
                second_door: {"900", "2100"},
            },
        )
        separators = [
            annotation
            for annotation in drawing.group.IsGroupedBy[0].RelatedObjects
            if ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            )
            == "door-dimension-separator"
        ]
        self.assertEqual(len(separators), 2)

        manual_drawing = house.add_drawing(
            "Manual plan",
            2.5,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotations=False,
        )
        self.assertFalse(
            any(
                "door-dimension"
                in (
                    ifcopenshell.util.element.get_pset(
                        annotation, "EPset_Annotation", "Classes"
                    )
                    or ""
                ).split()
                for annotation in manual_drawing.group.IsGroupedBy[0].RelatedObjects
            )
        )
        with self.assertRaisesRegex(TypeError, "door_annotations must be a boolean"):
            house.add_drawing(
                "Invalid plan",
                2.5,
                2,
                1.6,
                4,
                door_annotations="yes",
            )

    def test_adds_a_scoped_door_width_height_annotation(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        upper = house.storey("Upper floor", elevation=3)
        wall = ground.wall((1, 2), (5, 2), thickness=0.25, height=3)
        door = wall.add_door(
            at=1,
            width=0.9,
            height=2.1,
            opening_width=1.1,
            operation="SINGLE_SWING_RIGHT",
        )
        upper_door = upper.wall(
            (1, 2), (5, 2), thickness=0.25, height=3
        ).add_door(at=1, width=0.8, height=1.97)
        drawing = house.add_drawing(
            "Ground plan",
            3,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotations=False,
        )
        other_drawing = house.add_drawing(
            "Other plan",
            3,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotations=False,
        )

        annotation = drawing.add_door_annotation(
            door,
            offset=0.05,
            name="Kitchen door dimensions",
        )

        self.assertEqual(annotation.ObjectType, "TEXT")
        self.assertEqual(annotation.Name, "Kitchen door dimensions")
        width_literal = annotation.Representation.Representations[0].Items[0]
        self.assertTrue(width_literal.is_a("IfcTextLiteralWithExtent"))
        self.assertEqual(width_literal.Literal, "900")
        self.assertEqual(width_literal.BoxAlignment, "center")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            ),
            "door-dimension door-dimension-width small",
        )
        assignment = next(
            relation
            for relation in annotation.HasAssignments
            if relation.is_a("IfcRelAssignsToProduct")
        )
        self.assertEqual(assignment.RelatingProduct, door)

        annotation_placement = ifcopenshell.util.placement.get_local_placement(
            annotation.ObjectPlacement
        )
        door_placement = ifcopenshell.util.placement.get_local_placement(
            door.ObjectPlacement
        )
        local_annotation_point = np.linalg.inv(door_placement) @ np.append(
            annotation_placement[:3, 3], 1
        )
        self.assertAlmostEqual(abs(local_annotation_point[0] - 0.45), 0.12)
        self.assertGreater(abs(local_annotation_point[1]), 0.2)
        self.assertAlmostEqual(
            abs(np.dot(annotation_placement[:3, 0], door_placement[:3, 1])),
            1,
        )
        self.assertTrue(
            annotation_placement[0, 0] > -1e-9
            and (
                abs(annotation_placement[0, 0]) > 1e-9
                or annotation_placement[1, 0] >= 0
            )
        )
        self.assertIn(annotation, drawing.group.IsGroupedBy[0].RelatedObjects)
        height_annotation = next(
            candidate
            for candidate in drawing.group.IsGroupedBy[0].RelatedObjects
            if candidate.Name == "Kitchen door dimensions Height"
        )
        height_literal = height_annotation.Representation.Representations[0].Items[0]
        self.assertEqual(height_literal.Literal, "2100")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                height_annotation, "EPset_Annotation", "Classes"
            ),
            "door-dimension door-dimension-height small",
        )
        separator = next(
            candidate
            for candidate in drawing.group.IsGroupedBy[0].RelatedObjects
            if candidate.Name == "Kitchen door dimensions Separator"
        )
        self.assertEqual(separator.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                separator, "EPset_Annotation", "Classes"
            ),
            "door-dimension-separator",
        )
        separator_representation = ifcopenshell.util.representation.get_representation(
            separator, "Plan", "Annotation", "PLAN_VIEW"
        )
        np.testing.assert_allclose(
            separator_representation.Items[0].Points.CoordList,
            ((-0.71125, 0.0), (0.38875, 0.0)),
            atol=1e-9,
        )
        separator_placement = ifcopenshell.util.placement.get_local_placement(
            separator.ObjectPlacement
        )
        local_separator_point = np.linalg.inv(door_placement) @ np.append(
            separator_placement[:3, 3], 1
        )
        self.assertAlmostEqual(local_separator_point[0], 0.45)
        height_placement = ifcopenshell.util.placement.get_local_placement(
            height_annotation.ObjectPlacement
        )
        self.assertAlmostEqual(
            np.dot(
                annotation_placement[:2, 3] - separator_placement[:2, 3],
                annotation_placement[:2, 1],
            ),
            0.12,
        )
        self.assertAlmostEqual(
            np.dot(
                height_placement[:2, 3] - separator_placement[:2, 3],
                annotation_placement[:2, 1],
            ),
            -0.15,
        )
        self.assertNotIn(
            annotation,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )

        with self.assertRaisesRegex(ValueError, "already has"):
            drawing.add_door_annotation(door)
        with self.assertRaisesRegex(TypeError, "must be an IfcDoor"):
            drawing.add_door_annotation(wall)
        with self.assertRaisesRegex(ValueError, "not included"):
            drawing.add_door_annotation(upper_door)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "door-annotation.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            reopened_literals = [
                literal
                for literal in reopened.by_type("IfcTextLiteralWithExtent")
                if literal.Literal in {"900", "2100"}
            ]
            self.assertEqual(
                {literal.Literal for literal in reopened_literals},
                {"900", "2100"},
            )

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

    def test_stores_a_basic_elevation_camera_without_plan_annotations(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=2.8)
        wall.add_door(at=0.5, width=0.9, height=2.1)
        ground.furniture(
            "Table",
            kind="TABLE",
            size=(1, 1, 0.75),
            center=(2, 2),
        )

        drawing = house.add_drawing(
            "South elevation",
            2.5,
            -1,
            2,
            5,
            view="elevation",
            direction=(0, 2, 0),
            storeys=[ground],
            doors_closed=True,
        )

        self.assertEqual(drawing.view, "elevation")
        self.assertEqual(drawing.direction, (0.0, 1.0, 0.0))
        placement = ifcopenshell.util.placement.get_local_placement(
            drawing.element.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement,
            np.array(
                (
                    (1, 0, 0, 2.5),
                    (0, 0, -1, -1),
                    (0, 1, 0, 2),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-12,
        )
        drawing_pset = ifcopenshell.util.element.get_pset(
            drawing.element, "EPset_Drawing"
        )
        self.assertEqual(drawing_pset["TargetView"], "ELEVATION_VIEW")
        self.assertEqual(drawing_pset["FillMode"], "SHAPELY")
        self.assertEqual(drawing_pset["HasAnnotation"], False)
        self.assertEqual(drawing_pset["DoorsClosed"], True)
        self.assertEqual(
            set(drawing.group.IsGroupedBy[0].RelatedObjects),
            {drawing.element},
        )
        self.assertFalse(drawing._automatic_door_annotations)
        with self.assertRaisesRegex(ValueError, "only supported for plan"):
            drawing.add_dimension((0, 0), (1, 0))

        with self.assertRaisesRegex(ValueError, "direction is required"):
            house.add_drawing("Missing direction", 0, 0, 0, 1, view="elevation")
        with self.assertRaisesRegex(ValueError, "must be horizontal"):
            house.add_drawing(
                "Sloped direction",
                0,
                0,
                0,
                1,
                view="elevation",
                direction=(0, 1, 1),
            )
        with self.assertRaisesRegex(ValueError, "must not be zero"):
            house.add_drawing(
                "Zero direction",
                0,
                0,
                0,
                1,
                view="elevation",
                direction=(0, 0, 0),
            )
        with self.assertRaisesRegex(ValueError, "only supported for elevation"):
            house.add_drawing(
                "Directed plan",
                0,
                0,
                1,
                1,
                direction=(0, 1, 0),
            )
        with self.assertRaisesRegex(ValueError, "only supported for elevation"):
            house.add_drawing(
                "Closed plan",
                0,
                0,
                1,
                1,
                doors_closed=True,
            )
        with self.assertRaisesRegex(TypeError, "doors_closed must be a boolean"):
            house.add_drawing(
                "Invalid closed doors",
                0,
                0,
                1,
                1,
                view="elevation",
                direction=(0, 1, 0),
                doors_closed="yes",
            )

    def test_scopes_drawing_geometry_and_automatic_annotations_by_storey(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        ground_wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=2.8)
        upper_wall = upper.wall((0, 0), (5, 0), thickness=0.2, height=2.8)

        # Exercise annotations created after their drawings.
        ground_drawing = house.add_drawing(
            "Ground plan",
            2.5,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotations=False,
        )
        all_storeys_drawing = house.add_drawing(
            "All storeys", 2.5, 2, 1.6, 4, door_annotations=False
        )
        empty_drawing = house.add_drawing(
            "No storeys",
            2.5,
            2,
            1.6,
            4,
            storeys=[],
            door_annotations=False,
        )
        ground_wall.add_door(at=0.5, width=0.9, height=2.1)
        upper_wall.add_door(at=2, width=0.9, height=2.1)
        ground.furniture(
            "Ground table",
            kind="TABLE",
            size=(1, 1, 0.75),
            center=(1, 2),
        )
        upper.furniture(
            "Upper table",
            kind="TABLE",
            size=(1, 1, 0.75),
            center=(3, 2),
        )

        automatic_annotations = {
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.ObjectType in {"LINEWORK", "TEXT"}
        }
        ground_annotations = {
            annotation
            for annotation in automatic_annotations
            if ifcopenshell.util.element.get_container(annotation) == ground.element
        }
        upper_annotations = automatic_annotations - ground_annotations

        def automatic_members(drawing):
            return (
                set(drawing.group.IsGroupedBy[0].RelatedObjects)
                & automatic_annotations
            )

        self.assertEqual(automatic_members(ground_drawing), ground_annotations)
        self.assertEqual(
            automatic_members(all_storeys_drawing), automatic_annotations
        )
        self.assertEqual(automatic_members(empty_drawing), set())
        self.assertEqual(ground_drawing.storeys, (ground,))
        self.assertEqual(all_storeys_drawing.storeys, (ground, upper))
        self.assertFalse(ground_drawing.includes_all_storeys)
        self.assertTrue(all_storeys_drawing.includes_all_storeys)

        ground_include = ifcopenshell.util.element.get_pset(
            ground_drawing.element, "EPset_Drawing", "Include"
        )
        self.assertEqual(ground_include, f'location="{ground.element.GlobalId}"')
        self.assertIsNone(
            ifcopenshell.util.element.get_pset(
                all_storeys_drawing.element, "EPset_Drawing", "Include"
            )
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                empty_drawing.element, "EPset_Drawing", "Include"
            ),
            "0000000000000000000000",
        )

        # Exercise annotations which already exist when their drawing is made.
        upper_drawing = house.add_drawing(
            "Upper plan", 2.5, 2, 4.6, 4, storeys=[upper]
        )
        self.assertEqual(automatic_members(upper_drawing), upper_annotations)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "scoped-drawings.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            reopened_ground = next(
                drawing
                for drawing in reopened.by_type("IfcAnnotation")
                if drawing.ObjectType == "DRAWING" and drawing.Name == "Ground plan"
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    reopened_ground, "EPset_Drawing", "Include"
                ),
                f'location="{ground.element.GlobalId}"',
            )

    def test_rejects_invalid_drawing_storeys(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        other_storey = House("Other house").storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(TypeError, "sequence of Storey"):
            house.add_drawing(
                "String", 0, 0, 1.6, 3, storeys="Ground floor"
            )
        with self.assertRaisesRegex(TypeError, "storey 1 must be a Storey"):
            house.add_drawing("Entity", 0, 0, 1.6, 3, storeys=[ground.element])
        with self.assertRaisesRegex(ValueError, "belong to this house"):
            house.add_drawing("Foreign", 0, 0, 1.6, 3, storeys=[other_storey])
        with self.assertRaisesRegex(ValueError, "duplicated"):
            house.add_drawing("Duplicate", 0, 0, 1.6, 3, storeys=[ground, ground])

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
            self.assertIn("--export-area-page", commands[1])
            self.assertIn("--batch-process", commands[1])
            exported_png = Path(
                next(
                    argument.split("=", 1)[1]
                    for argument in commands[1]
                    if argument.startswith("--export-filename=")
                )
            )
            self.assertNotEqual(exported_png, output.with_suffix(".png"))
            self.assertTrue(output.with_suffix(".png").is_file())
            reopened = ifcopenshell.open(directory_path / "house.ifc")
            persisted = reopened.by_guid(drawing.element.GlobalId)
            document = next(
                association.RelatingDocument
                for association in persisted.HasAssociations
                if association.is_a("IfcRelAssociatesDocument")
            )
            self.assertEqual(Path(document.Location), output.resolve())

    def test_layers_door_and_furniture_symbols_above_plan_linework(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg>
  <g id="product-door" class="IfcDoor material-null projection"><path/></g>
  <g id="product-table" class="IfcFurniture material-null projection"><path/></g>
  <g id="product-basin" class="IfcSanitaryTerminal material-null cut"><path/></g>
  <g id="product-cooker" class="IfcElectricAppliance material-null projection"><path/></g>
  <g id="product-reinforcement-projection" ifc:guid="reinforcement" class="IfcBuildingElementPart material-MIAKOreinforcement projection"><path/></g>
  <g ifc:guid="reinforcement" class="IfcBuildingElementPart material-MIAKOreinforcement cut"><path/></g>
  <g id="product-cover" class="IfcBuildingElementPart material-Concretetopping cut"><path/></g>
  <line class="GlobalId-dimension IfcAnnotation PredefinedType-LINEWORK door-dimension-separator" x1="5" x2="20" y1="31" y2="31"/>
  <line class="GlobalId-door IfcAnnotation PredefinedType-LINEWORK door-overhead dashed" x1="10" x2="20" y1="30" y2="30"/>
  <text>unrelated annotation</text>
  <line class="GlobalId-door IfcAnnotation PredefinedType-LINEWORK door-overhead dashed" x1="10" x2="20" y1="32" y2="32"/>
  <text><tspan class="IfcAnnotation furniture-label">TABLE</tspan></text>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_door_overheads(svg_path)
            _postprocess_door_overheads(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            polygon = (
                '<polygon class="door-overhead-mask" '
                'points="10,30 20,30 20,32 10,32"/>'
            )
            self.assertEqual(svg.count(polygon), 1)
            self.assertLess(svg.index(polygon), svg.index("door-overhead dashed"))
            overlay = (
                '<use href="#product-door" '
                'xlink:href="#product-door"/>'
            )
            self.assertEqual(svg.count(overlay), 1)
            self.assertGreater(svg.index(overlay), svg.rindex("door-overhead dashed"))
            dimension_overlay = '<g class="door-dimension-overlays">'
            separator = (
                '<line class="GlobalId-dimension IfcAnnotation '
                'PredefinedType-LINEWORK door-dimension-separator" '
                'x1="5" x2="20" y1="31" y2="31"/>'
            )
            self.assertEqual(svg.count(dimension_overlay), 1)
            self.assertEqual(svg.count(separator), 2)
            self.assertGreater(svg.index(dimension_overlay), svg.index(polygon))
            self.assertLess(svg.index(dimension_overlay), svg.index(overlay))
            furniture_overlay = '<g class="furniture-symbol-overlays">'
            self.assertEqual(svg.count(furniture_overlay), 1)
            for product_id in (
                "product-table",
                "product-basin",
                "product-cooker",
            ):
                use = (
                    f'<use href="#{product_id}" '
                    f'xlink:href="#{product_id}"/>'
                )
                self.assertEqual(svg.count(use), 1)
                self.assertGreater(svg.index(use), svg.index(overlay))
            self.assertNotIn(
                '<use href="#product-door" xlink:href="#product-door"/>',
                svg[svg.index(furniture_overlay) :],
            )
            label_overlay = '<g class="furniture-label-overlays">'
            self.assertEqual(svg.count(label_overlay), 1)
            self.assertGreater(svg.index(label_overlay), svg.index(furniture_overlay))
            self.assertEqual(svg.count("TABLE"), 2)
            reinforcement_overlay = (
                '<g class="miako-reinforcement-overlays '
                'target-view-ELEVATIONVIEW">'
            )
            reinforcement_source = "miako-reinforcement-overlay-source-1"
            reinforcement_use = (
                f'<use href="#{reinforcement_source}" '
                f'xlink:href="#{reinforcement_source}"/>'
            )
            self.assertEqual(svg.count(reinforcement_overlay), 1)
            self.assertEqual(svg.count(f'id="{reinforcement_source}"'), 1)
            self.assertEqual(svg.count(reinforcement_use), 1)
            self.assertNotIn(
                '<use href="#product-reinforcement-projection"',
                svg,
            )
            self.assertGreater(
                svg.index(reinforcement_overlay),
                svg.index('id="product-cover"'),
            )
            self.assertLess(
                svg.index(reinforcement_overlay),
                svg.index(dimension_overlay),
            )

    def test_restores_openings_in_walls_cut_by_an_elevation(self) -> None:
        house = House("Section openings")
        storey = house.storey("Ground", elevation=0)
        wall = storey.wall(
            (0, 0),
            (4, 0),
            thickness=0.2,
            height=3,
        )
        opening = wall.add_opening(
            at=1,
            width=1,
            height=2,
            show_overhead=False,
            name='Hall & "door" opening',
        )
        section = house.add_drawing(
            "Section",
            x=2,
            y=0,
            z=1.5,
            radius=3,
            view="elevation",
            direction=(0, 1, 0),
        )

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "section.svg"
            svg_path.write_text(
                '<svg data-scale="1:100" viewBox="0 0 60 60" '
                'xmlns:ifc="http://www.ifcopenshell.org/ns"></svg>',
                encoding="utf-8",
            )

            _postprocess_elevation_opening_overlays(
                svg_path,
                house.model,
                section.element,
            )
            _postprocess_elevation_opening_overlays(
                svg_path,
                house.model,
                section.element,
            )

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="section-opening-mask"'), 1)
            self.assertIn(f'ifc:guid="{opening.GlobalId}"', svg)
            self.assertIn('ifc:name="Hall &amp; &quot;door&quot; opening"', svg)
            self.assertIn('points="20,45 30,45 30,25 20,25"', svg)

    def test_does_not_mask_openings_in_projected_walls(self) -> None:
        house = House("Projected openings")
        storey = house.storey("Ground", elevation=0)
        wall = storey.wall(
            (0, 0),
            (4, 0),
            thickness=0.2,
            height=3,
        )
        wall.add_opening(
            at=1,
            width=1,
            height=2,
            show_overhead=False,
        )
        elevation = house.add_drawing(
            "Elevation",
            x=2,
            y=-0.5,
            z=1.5,
            radius=3,
            view="elevation",
            direction=(0, 1, 0),
        )

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "elevation.svg"
            svg_path.write_text(
                '<svg data-scale="1:100" viewBox="0 0 60 60"></svg>',
                encoding="utf-8",
            )

            _postprocess_elevation_opening_overlays(
                svg_path,
                house.model,
                elevation.element,
            )

            svg = svg_path.read_text(encoding="utf-8")
            self.assertNotIn("section-opening-overlays", svg)

    def test_does_not_mask_openings_in_walls_seen_edge_on(self) -> None:
        house = House("Edge-on openings")
        storey = house.storey("Ground", elevation=0)
        wall = storey.wall(
            (0, 0),
            (4, 0),
            thickness=0.2,
            height=3,
        )
        wall.add_opening(
            at=1,
            width=2,
            height=2,
            show_overhead=False,
        )
        section = house.add_drawing(
            "Edge-on section",
            x=2,
            y=0,
            z=1.5,
            radius=3,
            view="elevation",
            direction=(1, 0, 0),
        )

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "section.svg"
            svg_path.write_text(
                '<svg data-scale="1:100" viewBox="0 0 60 60"></svg>',
                encoding="utf-8",
            )

            _postprocess_elevation_opening_overlays(
                svg_path,
                house.model,
                section.element,
            )

            svg = svg_path.read_text(encoding="utf-8")
            self.assertNotIn("section-opening-overlays", svg)

    def test_layers_cut_vapour_barriers_above_insulation_edges(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "elevation.svg"
            svg_path.write_text(
                """<svg>
  <g id="vapour-projection" class="IfcSlab material-Vapourbarrier projection"><path/></g>
  <g class="IfcSlab material-Vapourbarrier cut"><path/></g>
  <g class="IfcSlab cut material-Vapourbarrier"><path/></g>
  <g id="insulation" class="IfcSlab material-Thermalinsulation cut"><path/></g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_vapour_barrier_overlays(svg_path)
            _postprocess_vapour_barrier_overlays(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            overlay = (
                '<g class="vapour-barrier-overlays '
                'target-view-ELEVATIONVIEW">'
            )
            self.assertEqual(svg.count(overlay), 1)
            for index in (1, 2):
                source = f"vapour-barrier-overlay-source-{index}"
                self.assertEqual(svg.count(f'id="{source}"'), 1)
                self.assertEqual(
                    svg.count(
                        f'<use href="#{source}" xlink:href="#{source}"/>'
                    ),
                    1,
                )
            self.assertNotIn(
                '<use href="#vapour-projection"',
                svg,
            )
            self.assertGreater(svg.index(overlay), svg.index('id="insulation"'))

    def test_fills_open_projected_wood_edges_in_plan(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg>
  <g class="IfcBeam material-Wood projection">
    <path d="M0,0 L1,0"/>
    <path d="M3,0 L4,0"/>
    <path d="M4,0 L4,1"/>
    <path d="M4,1 L0,1"/>
    <path d="M0,1 L0,0"/>
  </g>
  <g class="IfcBeam material-Steel projection">
    <path d="M5,0 L6,0 L6,1 L5,1"/>
  </g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_projected_wood_fills(svg_path)
            _postprocess_projected_wood_fills(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            polygon = (
                '<polygon class="projected-wood-fill" '
                'points="0,0 4,0 4,1 0,1"/>'
            )
            self.assertEqual(svg.count(polygon), 1)
            self.assertLess(svg.index(polygon), svg.index('<path d="M0,0 L1,0"'))
            self.assertNotIn('points="5,0 6,0 6,1 5,1"', svg)

    def test_centers_short_dimension_labels_during_svg_postprocessing(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg>
  <line class="GlobalId-short IfcAnnotation PredefinedType-DIMENSION" x1="92.5" x2="92.5" y1="81.25" y2="76.25"/>
  <text dominant-baseline="baseline" text-anchor="middle" transform="translate(91.5, 73.25) rotate(-90.0)">
    <tspan class="DIMENSION">500</tspan>
  </text>
  <line class="GlobalId-long IfcAnnotation PredefinedType-DIMENSION" x1="92.5" x2="92.5" y1="101.25" y2="91.25"/>
  <text dominant-baseline="baseline" text-anchor="middle" transform="translate(91.5, 96.25) rotate(-90.0)">
    <tspan class="DIMENSION">1000</tspan>
  </text>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_door_overheads(svg_path)
            _postprocess_door_overheads(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn(
                'transform="translate(91.5, 78.75) rotate(-90.0)"',
                svg,
            )
            self.assertIn(
                'transform="translate(91.5, 96.25) rotate(-90.0)"',
                svg,
            )

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
        with self.assertRaisesRegex(ValueError, "start_height"):
            ground.wall(
                (0, 0),
                (1, 0),
                thickness=0.12,
                height=2.8,
                start_height=-0.1,
            )
        wall_arguments = {
            "start": (0, 0),
            "end": (2, 0),
            "thickness": 0.2,
            "height": 2,
        }
        with self.assertRaisesRegex(TypeError, "cuts must be a sequence"):
            ground.wall(**wall_arguments, cuts="plane")
        with self.assertRaisesRegex(TypeError, "exactly three points"):
            ground.wall(
                **wall_arguments,
                cuts=[((0, 0, 1), (1, 0, 1))],
            )
        with self.assertRaisesRegex(TypeError, "exactly three coordinates"):
            ground.wall(
                **wall_arguments,
                cuts=[((0, 0), (1, 0, 1), (0, 1, 1))],
            )
        with self.assertRaisesRegex(ValueError, "must not be collinear"):
            ground.wall(
                **wall_arguments,
                cuts=[((0, 0, 1), (1, 0, 1), (2, 0, 1))],
            )
        with self.assertRaisesRegex(ValueError, "retained side is ambiguous"):
            ground.wall(
                **wall_arguments,
                cuts=[((0, 0, 1), (1, 0, 1), (0, 1, 1))],
            )

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
