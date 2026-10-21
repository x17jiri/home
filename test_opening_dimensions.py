from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

import ifcopenshell
import ifcopenshell.util.element as element
import ifcopenshell.util.placement as placement
import ifcopenshell.util.representation as representation
import numpy as np

from ifc_utils import House, _postprocess_dimension_overlays, _postprocess_door_overheads


class OpeningDimensionTests(unittest.TestCase):
    def scene(self, *, floors=True, mirror=False, wall_start=0):
        house = House("Opening dimensions", mirror_x=mirror)
        storey = house.storey("Upper", elevation=3)
        if floors:
            storey.floor_layer("Finished floor", outline=((-1, -2), (9, -2), (9, 3), (-1, 3)),
                                thickness=.2)
        wall = storey.wall((0, 0), (8, 0), thickness=.24, height=3, start_height=wall_start)
        drawing = house.add_drawing("Plan", 4, 0, 4.5, 6, storeys=[storey], door_annotations=False)
        return house, storey, wall, drawing

    def data(self, dimension):
        return element.get_pset(dimension, "BBIM_OpeningDimension")

    def axis(self, dimension):
        rep = representation.get_representation(dimension, "Plan", "Annotation", "PLAN_VIEW")
        resolved = representation.resolve_items(rep)[0]
        matrix = placement.get_local_placement(dimension.ObjectPlacement) @ resolved["matrix"]
        return [tuple((matrix @ (*point, 0, 1))[:3]) for point in resolved["item"].Points.CoordList]

    def test_measures_construction_opening_not_leaf_and_height_not_top_coordinate(self):
        house, storey, wall, drawing = self.scene(wall_start=.4)
        door = wall.add_door(at=1, width=.9, opening_width=1.1, sill_height=.6,
                             height=2.6, opening_height=2.7, clear_height=1.9)
        other = house.add_drawing("Other", 4, 0, 4.5, 6, storeys=[storey], door_annotations=False)
        dimension = drawing.add_opening_dimension(door, offset=-1)
        self.assertEqual(dimension.Description, "2100 (400)")
        data = self.data(dimension)
        self.assertAlmostEqual(data["Width"], 1.1)
        self.assertAlmostEqual(data["Height"], 2.1)
        self.assertAlmostEqual(data["SillHeight"], .4)
        self.assertAlmostEqual(data["FinishedFloorHeight"], .2)
        self.assertEqual(data["Opening"], door.FillsVoids[0].RelatingOpeningElement.GlobalId)
        self.assertEqual(data["Product"], door.GlobalId)
        np.testing.assert_allclose(self.axis(dimension), [(1, -1, 3), (2.1, -1, 3)], atol=1e-8)
        self.assertIn(dimension, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(dimension, other.group.IsGroupedBy[0].RelatedObjects)
        self.assertEqual(element.get_pset(dimension, "BBIM_Dimension", "CustomUnit"), ["Millimeters"])

    def test_window_and_unfilled_opening(self):
        _, _, wall, drawing = self.scene()
        window = wall.add_window(at=1, width=1.5, sill_height=1.2, height=2.4)
        passage = wall.add_opening(at=4, width=1.2, sill_height=.2, height=2.3)
        self.assertEqual(drawing.add_opening_dimension(window).Description, "1200 (1000)")
        self.assertEqual(drawing.add_opening_dimension(passage).Description, "2100 (0)")
        self.assertEqual(drawing.add_opening_dimension(
            window.FillsVoids[0].RelatingOpeningElement).Description, "1200 (1000)")

    def test_explicit_floor_constant_works_without_floor_geometry(self):
        _, _, wall, drawing = self.scene(floors=False)
        opening = wall.add_opening(at=1, width=1, sill_height=.3, height=2.3)
        dimension = drawing.add_opening_dimension(
            opening, offset=-1, finished_floor_height=.3, name="Passage")
        self.assertEqual(dimension.Description, "2000 (0)")
        self.assertEqual(dimension.Name, "Passage")
        self.assertAlmostEqual(self.data(dimension)["FinishedFloorHeight"], .3)

    def test_negative_sill_splits_height_above_and_below_finished_floor(self):
        _, _, wall, drawing = self.scene()
        opening = wall.add_opening(at=1, width=1, sill_height=.1, height=2.3)
        dimension = drawing.add_opening_dimension(opening)
        self.assertEqual(dimension.Description, "2100 + 100")
        self.assertAlmostEqual(self.data(dimension)["Height"], 2.2)
        self.assertAlmostEqual(self.data(dimension)["SillHeight"], -.1)
        explicit = drawing.add_opening_dimension(opening, finished_floor_height=.4)
        self.assertEqual(explicit.Description, "1900 + 300")

    def test_door_plan_is_above_floor_without_moving_door_or_opening(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house, storey, wall, drawing = self.scene(mirror=mirror)
                door = wall.add_door(at=1, width=.9, opening_width=1,
                                     sill_height=0, height=2.3, reverse_swing=True)
                dimension = drawing.add_opening_dimension(door)
                self.assertEqual(dimension.Description, "2100 + 200")
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "door.ifc"
                    house.write(path)
                    exported = ifcopenshell.open(path).by_guid(door.GlobalId)
                    door_matrix = placement.get_local_placement(exported.ObjectPlacement)
                    self.assertAlmostEqual(door_matrix[2, 3], storey.elevation)
                    self.assertAlmostEqual(exported.OverallHeight, 2.3)
                    opening = exported.FillsVoids[0].RelatingOpeningElement
                    self.assertAlmostEqual(placement.get_local_placement(
                        opening.ObjectPlacement)[2, 3], storey.elevation)
                    plan = representation.get_representation(exported, "Plan", "Body", "PLAN_VIEW")
                    parts = representation.resolve_items(plan)
                    self.assertEqual(len(parts), 4)  # Two jambs, swing arc, leaf.
                    for part in parts:
                        symbol_matrix = door_matrix @ part["matrix"]
                        self.assertAlmostEqual(symbol_matrix[2, 3], storey.elevation + 1.15)
                        self.assertGreater(symbol_matrix[2, 3], storey.elevation + .2)
                    body = representation.get_representation(exported, "Model", "Body", "MODEL_VIEW")
                    for part in representation.resolve_items(body):
                        self.assertAlmostEqual((door_matrix @ part["matrix"])[2, 3], storey.elevation)

    def test_common_floor_level_ignores_base_slabs_and_handles_different_buildups(self):
        _, storey, wall, drawing = self.scene()
        outline = ((0, 0), (8, 0), (8, 4), (0, 4))
        storey.floor_layer("Second room", outline=outline, start_height=-.1, thickness=.3)
        storey.floor_layer("Structural base", outline=outline, start_height=-.5, thickness=.1, kind="BASESLAB")
        opening = wall.add_opening(at=1, width=1, sill_height=.2, height=2.3)
        self.assertEqual(drawing.add_opening_dimension(opening).Description, "2100 (0)")

    def test_absent_or_ambiguous_floor_level_requires_explicit_reference(self):
        for floors in (False, True):
            with self.subTest(floors=floors):
                house, storey, wall, drawing = self.scene(floors=floors)
                if floors:
                    storey.floor_layer("Step", outline=((0, 0), (8, 0), (8, 4), (0, 4)), thickness=.4)
                opening = wall.add_opening(at=1, width=1, sill_height=.2, height=2.3)
                count = len(house.model.by_type("IfcAnnotation"))
                with self.assertRaisesRegex(ValueError, "finished_floor_height"):
                    drawing.add_opening_dimension(opening)
                self.assertEqual(len(house.model.by_type("IfcAnnotation")), count)
                self.assertEqual(drawing.add_opening_dimension(
                    opening, finished_floor_height=.2).Description, "2100 (0)")

    def test_invalid_input_fails_before_adding_annotations(self):
        house, storey, wall, drawing = self.scene()
        opening = wall.add_opening(at=1, width=1, sill_height=.2, height=2.3)
        _, _, foreign_wall, _ = self.scene()
        foreign = foreign_wall.add_opening(at=1, width=1, height=2)
        recess = wall.add_recess(at=4, width=1, depth=.1, height=.2, sill_height=2.5)
        excluded = house.add_drawing("Empty", 4, 0, 4.5, 6, storeys=[])
        elevation = house.add_drawing("Elevation", 4, 0, 4.5, 6, view="elevation", direction=(1, 0, 0))
        cases = [(drawing, "opening", {}, TypeError), (drawing, foreign, {}, ValueError),
                 (drawing, recess, {}, ValueError), (excluded, opening, {}, ValueError),
                 (elevation, opening, {}, ValueError),
                 (drawing, opening, {"offset": float("nan")}, ValueError),
                 (drawing, opening, {"finished_floor_height": True}, TypeError)]
        for target, obj, kwargs, exception in cases:
            with self.subTest(kwargs=kwargs, target=target.name):
                count = len(house.model.by_type("IfcAnnotation"))
                with self.assertRaises(exception):
                    target.add_opening_dimension(obj, **kwargs)
                self.assertEqual(len(house.model.by_type("IfcAnnotation")), count)

    def test_rotated_wall_uses_actual_jamb_coordinates(self):
        house, storey, _, drawing = self.scene()
        wall = storey.wall((1, 1), (5, 5), thickness=.24, height=3)
        opening = wall.add_opening(at=1, width=1.5, sill_height=.2, height=2.3)
        dimension = drawing.add_opening_dimension(opening, offset=-.5)
        points = np.array(self.axis(dimension))
        axis = np.array((1, 1)) / np.sqrt(2)
        normal = np.array((-axis[1], axis[0]))
        np.testing.assert_allclose(points[0][:2], (1, 1) + axis - .5 * normal)
        np.testing.assert_allclose(points[1][:2], (1, 1) + 2.5 * axis - .5 * normal)

    def test_mirrored_export_preserves_description_and_readable_dimension_direction(self):
        house, _, wall, drawing = self.scene(mirror=True)
        opening = wall.add_opening(at=1, width=1.5, sill_height=1.2, height=2.4)
        dimension = drawing.add_opening_dimension(opening, offset=-1)
        with TemporaryDirectory() as directory:
            house.write(Path(directory) / "openings.ifc")
            exported = ifcopenshell.open(Path(directory) / "openings.ifc").by_guid(dimension.GlobalId)
            self.assertEqual(exported.Description, "1200 (1000)")
            points = self.axis(exported)
            np.testing.assert_allclose(points, [(-2.5, -1, 3), (-1, -1, 3)], atol=1e-8)

    def test_centres_both_labels_of_short_dimensions_and_keeps_them_above_fills(self):
        source = ('<svg><line class="PredefinedType-DIMENSION" x1="0" y1="0" x2="4" y2="0"/>'
                  '<text id="width" transform="translate(7, -1) rotate(0)"><tspan class="DIMENSION">400</tspan></text>'
                  '<text id="height" transform="translate(7, 1) rotate(0)"><tspan class="DIMENSION">1200 (1000)</tspan></text>'
                  '<text id="note" transform="translate(9,9) rotate(0)"><tspan class="TEXT">Note</tspan></text>'
                  '<path id="floor" fill="white" d="M0 0H10V10Z"/></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dimension.svg"
            path.write_text(source)
            _postprocess_door_overheads(path)
            _postprocess_dimension_overlays(path)
            result = path.read_text()
            root = ET.fromstring(result)
            self.assertEqual(root.find(".//text[@id='width']").get("transform"), "translate(2, -1) rotate(0)")
            self.assertEqual(root.find(".//text[@id='height']").get("transform"), "translate(2, 1) rotate(0)")
            self.assertEqual(root.find(".//text[@id='note']").get("transform"), "translate(9,9) rotate(0)")
            self.assertLess(result.index('id="floor"'), result.index('id="height"'))
            _postprocess_door_overheads(path)
            _postprocess_dimension_overlays(path)
            self.assertEqual(path.read_text(), result)


if __name__ == "__main__":
    unittest.main()
