import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import ifcopenshell.util.element
import ifcopenshell.api.pset

from dimension_index import read_dimension_rows, write_dimension_index
from ifc_utils import House


class DimensionIndexTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Dimension index", mirror_x=False)
        self.ground = self.house.storey("Ground", elevation=0)
        self.drawing = self.house.add_drawing("ground", 2, 3, 2, 5, storeys=[self.ground])

    def test_captures_external_callsite_original_coordinates_and_helper_callers(self):
        def add_width(name):
            expected_line = inspect.currentframe().f_lineno+1
            dimension = self.drawing.add_dimension((0, 1), (3.3775, 1), offset=.25, name=name)
            return dimension, expected_line

        dimensions = [add_width(name) for name in ("First width", "Second width")]
        for dimension, expected_line in dimensions:
            props = ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource")
            self.assertEqual(props["SourceFile"], str(Path(__file__).resolve()))
            self.assertEqual(props["SourceLine"], expected_line)
            self.assertEqual(props["SourceFunction"], "add_width")
            self.assertIn("self.drawing.add_dimension", props["SourceCode"])
            self.assertEqual(json.loads(props["Start"]), [0, 1])
            self.assertEqual(json.loads(props["End"]), [3.3775, 1])
            self.assertEqual(props["Offset"], .25)
            self.assertAlmostEqual(props["Length"], 3.3775)
            callers = json.loads(props["Callers"])
            self.assertTrue(any(caller["function"] == self._testMethodName for caller in callers))

    def test_opening_dimension_points_to_the_user_call_not_the_internal_helper(self):
        wall = self.ground.wall((0, 0), (5, 0), thickness=.24, height=3)
        door = wall.add_door(at=1, width=.9, opening_width=1, height=2.2)
        expected_line = inspect.currentframe().f_lineno+1
        dimension = self.drawing.add_opening_dimension(door, offset=-.5, finished_floor_height=0)
        props = ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource")
        self.assertEqual(props["SourceFile"], str(Path(__file__).resolve()))
        self.assertEqual(props["SourceLine"], expected_line)
        self.assertAlmostEqual(props["Length"], 1)

    def test_index_uses_exact_svg_labels_keeps_duplicates_and_opening_captions(self):
        first = self.drawing.add_dimension((0, 0), (3.3775, 0), name="Repeated A")
        second = self.drawing.add_dimension((0, 1), (3.3775, 1), name="Repeated B")
        hidden = self.drawing.add_dimension((0, 2), (10, 2), name="Not visible")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg"><defs><text><tspan class="DIMENSION">9999</tspan></text></defs>'
            '<g class="dimension-overlays">'
            f'<line class="GlobalId-{first.GlobalId} PredefinedType-DIMENSION"/>'
            '<text><tspan class="DIMENSION">3377</tspan></text>'
            '<text><tspan class="DIMENSION">2130 + 245</tspan></text>'
            f'<line class="GlobalId-{second.GlobalId} PredefinedType-DIMENSION"/>'
            '<text><tspan class="DIMENSION">3377</tspan></text>'
            '<text class="room-identifier">S.01</text>'
            '</g></svg>'
        )
        with TemporaryDirectory() as directory:
            path = Path(directory)/"plan.svg"
            path.write_text(svg)
            self.house.write(Path(directory)/"house.ifc")
            reopened = ifcopenshell.open(Path(directory)/"house.ifc")
            output = write_dimension_index(path, reopened, reopened.by_guid(self.drawing.element.GlobalId))
            self.assertEqual(output, Path(directory)/"plan.dimensions.tsv")
            rows = read_dimension_rows(path)
            self.assertEqual(len(rows), 3)
            self.assertEqual([row["dimension"] for row in rows if row["value"] == "3377"],
                             ["Repeated A", "Repeated B"])
            self.assertTrue(all(row["length_mm"] == "3377.5" for row in rows))
            caption = next(row for row in rows if row["label"] == "description")
            self.assertEqual((caption["value"], caption["guid"]), ("2130 + 245", first.GlobalId))
            self.assertTrue(all("test_dimension_index.py:" in row["source"] for row in rows))
            self.assertFalse(any(row["guid"] == hidden.GlobalId for row in rows))
            self.assertEqual(path.read_text(), svg)
            # A later rendering with no dimensions must clear the previous index.
            path.write_text('<svg/>')
            write_dimension_index(path, reopened, reopened.by_guid(self.drawing.element.GlobalId))
            self.assertEqual(read_dimension_rows(path), [])

    def test_legacy_dimensions_without_provenance_leave_source_blank(self):
        dimension = self.drawing.add_dimension((0, 0), (1, 0))
        pset = ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource")
        ifcopenshell.api.pset.remove_pset(self.house.model, product=dimension,
                                         pset=self.house.model.by_id(pset["id"]))
        with TemporaryDirectory() as directory:
            path = Path(directory)/"legacy.svg"
            path.write_text(f'<svg><line class="GlobalId-{dimension.GlobalId} PredefinedType-DIMENSION"/>'
                            '<text><tspan class="DIMENSION">1 000</tspan></text></svg>')
            write_dimension_index(path, self.house.model, self.drawing.element)
            row, = read_dimension_rows(path)
            self.assertEqual((row["value"], row["source"]), ("1 000", ""))


if __name__ == "__main__":
    unittest.main()
