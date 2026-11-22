"""Coordinate and file-safety checks for the map picker."""

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pick_points import DEFAULT_MAP, MapCoordinates, PointSelection


class MapCoordinatesTests(unittest.TestCase):
    def test_known_quarter_turn_and_image_corners(self):
        frame = MapCoordinates(-600000, -1100000, pi/2, (-30, -20, 70, 60), (10, 25, 100, 80), "EPSG:5514")
        y, x = frame.to_survey(10, 20)
        self.assertAlmostEqual(y, 599980)
        self.assertAlmostEqual(x, 1100010)
        self.assertEqual(frame.image_to_local(0, 0, 1000, 800), (-30, 60))
        self.assertEqual(frame.image_to_local(1000, 800, 1000, 800), (70, -20))
        self.assertEqual(frame.local_to_image(-30, 60, 1000, 800), (0, 0))

    def test_existing_map_keeps_known_survey_positions(self):
        import xml.etree.ElementTree as ET

        frame = MapCoordinates.from_svg(DEFAULT_MAP)
        data = json.loads(ET.parse(DEFAULT_MAP).getroot().find('{http://www.w3.org/2000/svg}metadata').text)
        for p in data["points"]:
            local = frame.to_local(p["y"], p["x"])
            pixel = frame.local_to_image(*local, 3600, 3024)
            reconstructed = frame.to_survey(*frame.image_to_local(*pixel, 3600, 3024))
            self.assertAlmostEqual(reconstructed[0], p["y"], places=7)
            self.assertAlmostEqual(reconstructed[1], p["x"], places=7)


class PointSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/"selected.json"
        self.frame = MapCoordinates(-600000, -1100000, 0, (-50, -50, 50, 50), (10, 25, 100, 100), "EPSG:5514")
        self.source = Path(self.directory.name)/"map.svg"
        self.selection = PointSelection(self.frame, self.path, self.source)
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_add_nudge_and_resume_in_a_regenerated_map_frame(self):
        self.assertTrue(self.selection.add(10, 20))
        self.assertTrue(self.selection.move(.1, 1))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["points"], [{"id": 1, "x": 10.1, "y": 21,
                                           "Y": 599989.9, "X": 1099979, "Z": None}])
        new_frame = replace(self.frame, east=-599900, angle=pi/2)
        resumed = PointSelection(new_frame, self.path, self.source)
        self.assertEqual(resumed.points[0]["Y"], 599989.9)
        self.assertEqual(resumed.points[0]["X"], 1099979)
        self.assertNotEqual(resumed.local(resumed.points[0]), (10.1, 21))

    def test_delete_and_undo_are_persisted(self):
        self.selection.add(0, 0)
        self.selection.add(10, 10)
        self.selection.delete()
        self.assertEqual([p["id"] for p in json.loads(self.path.read_text())["points"]], [1])
        self.selection.undo()
        self.assertEqual([p["id"] for p in json.loads(self.path.read_text())["points"]], [1, 2])
        self.selection.undo()
        self.assertEqual([p["id"] for p in json.loads(self.path.read_text())["points"]], [1])

    def test_outside_click_and_nudge_do_not_change_the_file(self):
        self.selection.add(49, 49)
        original = self.path.read_bytes()
        self.assertFalse(self.selection.add(51, 0))
        self.assertFalse(self.selection.move(2, 0))
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_existing_file_is_never_overwritten(self):
        for content in ("[]", '{"version":1,"crs":"other","points":[]}',
                        '{"version":1,"crs":"EPSG:5514","points":[{"id":1,"Y":NaN,"X":1}]}'):
            self.path.write_text(content)
            with self.assertRaises(ValueError):
                PointSelection(self.frame, self.path, self.source)
            self.assertEqual(self.path.read_text(), content)

    def test_failed_atomic_save_keeps_the_previous_file_and_points(self):
        self.selection.add(0, 0)
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.selection.add(10, 10)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual([p["id"] for p in self.selection.points], [1])
        self.assertEqual(len(list(Path(self.directory.name).iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
