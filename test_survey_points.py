"""Survey column order, metre-preserving axes and exported point information."""

from contextlib import redirect_stdout
from io import StringIO
import json
from math import hypot
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from survey_points import SurveyFrame, read_survey_groups, read_survey_points, render_survey_points


HEADER = "Seznam souřadnic (S-JTSK, Bpv.)\nč.b. Y X Z poznámka\n"


class SurveyPointsTests(unittest.TestCase):
    def test_explicit_groups_preserve_file_order_and_reset_color_at_blank_lines(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            original = ("\ufeff#ff0000, closed\n"
                        "10 588800 1144300 417 B\n2 588801 1144301 418 other\n"
                        "\n  \n9 588802 1144302 419 B\n1 588803 1144303 420 B\n"
                        "\n#00ff00\n4 588804 1144304 421\n3 588805 1144305 422\n"
                        "\n#ff0000\n6 588806 1144306 423 B\n5 588807 1144307 424 B"
                        ).replace("\n", "\r\n").encode("utf-8")
            source.write_bytes(original)
            groups = read_survey_groups(source)
            self.assertEqual([(g.color, [p.number for p in g.points]) for g in groups],
                             [("#ff0000", ["10", "2"]), (None, ["9", "1"]),
                              ("#00ff00", ["4", "3"]), ("#ff0000", ["6", "5"])])
            self.assertEqual([g.closed for g in groups], [True, False, False, False])
            self.assertEqual([p.number for p in read_survey_points(source)],
                             ["10", "2", "9", "1", "4", "3", "6", "5"])
            self.assertEqual(source.read_bytes(), original)

    def test_reader_preserves_y_x_order_notes_and_centimetres(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            original = ("\ufeff"+HEADER+"1 600002.23 1100003.39 415.73 B\n"
                        "10 600002.24 1100003.40 415.74 práh\n"
                        "293 600010.00 1100010.00 421.97 s-z\n").replace("\n", "\r\n").encode("utf-8")
            source.write_bytes(original)
            points = read_survey_points(source)
            self.assertEqual(len(points), 3)
            self.assertEqual((points[0].number, points[0].y, points[0].x, points[0].z, points[0].note),
                             ("1", 600002.23, 1100003.39, 415.73, "B"))
            self.assertEqual(points[-1].number, "293")
            self.assertAlmostEqual(points[1].y-points[0].y, .01)
            self.assertAlmostEqual(points[1].x-points[0].x, .01)
            self.assertEqual(points[1].note, "práh")
            self.assertEqual(source.read_bytes(), original)

    def test_grid_east_north_orientation_roundtrip_and_distances(self):
        frame = SurveyFrame(588800, 1144300)
        self.assertEqual(frame.to_local(588799, 1144298), (1, 2))
        self.assertEqual(frame.to_survey(1, 2), (588799, 1144298))
        a, b = (588802.23, 1144303.39), (588822.94, 1144314.43)
        u, v = frame.to_local(*a), frame.to_local(*b)
        self.assertAlmostEqual(hypot(a[0]-b[0], a[1]-b[1]), hypot(u[0]-v[0], u[1]-v[1]))

    def test_rejects_swapped_columns_duplicate_ids_and_bad_rows(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            for contents in (
                HEADER.replace("Y X Z", "X Y Z")+"1 588800 1144300 417\n",
                HEADER+"1 588800 1144300 417\n1 588801 1144301 418\n",
                HEADER+"1 588800 1144300 nan\n",
                HEADER+"1 588800 missing 417\n",
                HEADER+"1 588800 1144300\n",
                "#not-a-color\n1 588800 1144300 417\n",
                "#\n1 588800 1144300 417\n",
                "#ff0000\n\n",
                "#ff0000, unknown\n1 588800 1144300 417\n",
            ):
                with self.subTest(contents=contents):
                    source.write_text(contents, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_survey_points(source)

    def test_svg_has_exact_points_heights_tooltips_and_original_coordinates(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"source.txt"
            source.write_text("#ff0000\n10 588808.0 1144310.0 418.00 B\n"
                              "1 588802.23 1144303.39 415.73 other\n\n"
                              "2 588802.24 1144303.40 415.74 práh\n"
                              "9 588805.0 1144308.0 417.20 práh\n", encoding="utf-8")
            output, pdf = Path(directory)/"points.svg", Path(directory)/"points.pdf"
            with redirect_stdout(StringIO()):
                render_survey_points(source, output, pdf=pdf, title="Zaměření", show_ids=True)
            root = ET.parse(output).getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
            self.assertEqual(data["units"], "metres")
            self.assertEqual(data["column_order"], ["number", "Y", "X", "Z", "note"])
            self.assertEqual(data["points"][2]["y"], 588802.24)
            self.assertEqual(data["points"][2]["note"], "práh")
            self.assertEqual(data["groups"], [{"color": "#ff0000", "closed": False,
                                               "point_ids": ["10", "1"]},
                                              {"color": None, "closed": False,
                                               "point_ids": ["2", "9"]}])
            for number, height in (("1", "415.73"), ("2", "415.74"), ("9", "417.20")):
                cross = root.find(f'.//s:g[@id="survey-point-{number}"]', ns)
                self.assertIsNotNone(cross)
                self.assertIn(height, cross.find("s:title", ns).text)
                label = root.find(f'.//s:g[@id="survey-label-{number}"]', ns)
                self.assertIn(f"{number}: {height}", "".join(label.itertext()))
            groups = [element for element in root.iter()
                      if element.get("id", "").startswith("survey-group-")]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].find("s:title", ns).text, "Barva: #ff0000; body: 10, 1")
            self.assertIn("stroke: #ff0000", groups[0].find("s:path", ns).get("style"))
            self.assertFalse(any(e.get("id", "").startswith("survey-leader-") for e in root.iter()))
            width, height = (float(root.get(name).removesuffix("pt")) for name in ("width", "height"))
            self.assertAlmostEqual(width*25.4/72, 297, places=4)
            self.assertAlmostEqual(height*25.4/72, 210, places=4)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

    def test_closed_group_adds_only_last_to_first_segment_to_export(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"source.txt", Path(directory)/"points.svg"
            vertices = []
            for closed in (False, True):
                with self.subTest(closed=closed):
                    source.write_text("#ff0000" + (", closed" if closed else "") + "\n"
                                      "10 588800 1144300 417\n2 588805 1144300 418\n"
                                      "1 588805 1144305 419\n", encoding="utf-8")
                    with redirect_stdout(StringIO()):
                        render_survey_points(source, output)
                    root = ET.parse(output).getroot()
                    ns = {"s": "http://www.w3.org/2000/svg"}
                    path = root.find('.//s:g[@id="survey-group-0"]/s:path', ns)
                    coords = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?",
                                                           path.get("d"))]
                    points = list(zip(coords[::2], coords[1::2]))
                    self.assertEqual(len(points), 4 if closed else 3)
                    self.assertEqual(points[0] == points[-1], closed)
                    vertices.append(points)
                    data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
                    self.assertEqual(data["groups"][0]["closed"], closed)
                    self.assertEqual(data["groups"][0]["point_ids"], ["10", "2", "1"])
            self.assertEqual(vertices[0], vertices[1][:-1])


if __name__ == "__main__":
    unittest.main()
