"""Survey column order, metre-preserving axes and exported point information."""

from contextlib import redirect_stdout
from io import StringIO
import json
from math import atan2, cos, degrees, hypot, pi, radians, sin, sqrt, tan
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from survey_points import (RoofSlope, SurveyAxes, SurveyFrame, SurveyGroup, SurveyHouse, SurveyPoint, named_survey_groups,
                           first_roof_45_degree_hit, house_roof_profiles, neighbour_window_point,
                           read_house_roof_metrics, read_survey_groups, read_survey_points,
                           render_survey_points)


HEADER = "Seznam souřadnic (S-JTSK, Bpv.)\nč.b. Y X Z poznámka\n"


class SurveyPointsTests(unittest.TestCase):
    def visibility_setup(self):
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (0, 1))
        sy, sx = axes.frame.to_survey(0, 2)
        return axes, SurveyPoint("window", sy, sx, 10)

    def test_first_clockwise_roof_hit_uses_infinite_line_and_exact_45_degree_boundary(self):
        axes, observer = self.visibility_setup()
        # A short preview around y=2; the first visible point is far past its end.
        roof = RoofSlope((-3, 1.9), (-3, 2.1), 15, 0)
        hit = first_roof_45_degree_hit((roof,), axes, observer)
        self.assertAlmostEqual(hit.clockwise_degrees, degrees(atan2(3, 4)))
        self.assertAlmostEqual(hit.point[0], -3)
        self.assertAlmostEqual(hit.point[1], -2)
        self.assertAlmostEqual(hit.plan_distance, 5)
        self.assertAlmostEqual(hit.elevation_difference, 5)
        self.assertAlmostEqual(hit.vertical_angle_degrees, 45)

    def test_sloping_roof_threshold_matches_independent_distance_solution_including_45_and_60_pitch(self):
        axes, observer = self.visibility_setup()
        for angle in (26, 45, 60):
            with self.subTest(angle=angle):
                roof = RoofSlope((-3, 1), (-3, 3), 15, angle)
                # Monotonic independent solution: hypot(3, s)+tan(angle)*s=5.
                low, high = 0, 5
                for _ in range(70):
                    mid = (low+high)/2
                    if hypot(3, mid)+tan(radians(angle))*mid < 5:
                        low = mid
                    else:
                        high = mid
                expected = degrees(atan2(3, (low+high)/2))
                hit = first_roof_45_degree_hit((roof,), axes, observer)
                self.assertAlmostEqual(hit.clockwise_degrees, expected, places=8)
                self.assertAlmostEqual(hit.plan_distance, hit.elevation_difference)
                self.assertAlmostEqual(roof.elevation_at(hit.point, axes), hit.elevation)

    def test_first_roof_hit_can_be_inside_initial_ray_interval(self):
        axes, observer = self.visibility_setup()
        roof = RoofSlope((.9, -2), (1.1, -2), 15, 0)
        hit = first_roof_45_degree_hit((roof,), axes, observer)
        self.assertAlmostEqual(hit.clockwise_degrees, 0)
        self.assertAlmostEqual(hit.point[0], 0)
        self.assertAlmostEqual(hit.point[1], -2)
        self.assertAlmostEqual(hit.plan_distance, 4)
        self.assertGreater(hit.vertical_angle_degrees, 45)

    def test_visibility_handles_no_hit_tangency_and_clockwise_wrap(self):
        axes, observer = self.visibility_setup()
        for roof in (RoofSlope((-6, 1), (-6, 3), 15, 0), RoofSlope((-3, 1), (-3, 3), 9, 35)):
            self.assertIsNone(first_roof_45_degree_hit((roof,), axes, observer))
        self.assertIsNone(first_roof_45_degree_hit((), axes, observer))
        tangent = first_roof_45_degree_hit((RoofSlope((-5, 1), (-5, 3), 15, 0),), axes, observer)
        self.assertAlmostEqual(tangent.clockwise_degrees, 90)
        self.assertAlmostEqual(tangent.vertical_angle_degrees, 45)
        wrapped = first_roof_45_degree_hit((RoofSlope((3, 1), (3, 3), 15, 0),), axes, observer)
        self.assertAlmostEqual(wrapped.clockwise_degrees, 180+degrees(atan2(3, 4)))

    def test_visibility_selects_earliest_roof_not_first_in_list_and_supports_oblique_axes(self):
        axes, observer = self.visibility_setup()
        later = RoofSlope((-4, 1), (-4, 3), 15, 0)
        earlier = RoofSlope((-3, 1), (-3, 3), 15, 0)
        hit = first_roof_45_degree_hit((later, earlier), axes, observer)
        self.assertEqual(hit.roof_index, 2)
        oblique = SurveyAxes(axes.frame, (.6, .8))
        roof = RoofSlope(oblique.from_local(-3, 1), oblique.from_local(-3, 3), 15, 0)
        other = first_roof_45_degree_hit((roof,), oblique, observer)
        self.assertAlmostEqual(hit.clockwise_degrees, other.clockwise_degrees)
        for actual, expected in zip(oblique.to_local(*other.point), hit.point):
            self.assertAlmostEqual(actual, expected)

    def test_default_roof_tracks_both_right_corners_after_house_movement_and_rotation(self):
        axes = SurveyAxes.from_polylines(*self.placement_groups())
        for center, angle in (((-10, 9.7), -5), ((3, 6), 40)):
            house = SurveyHouse(center=center, angle_degrees=angle)
            roof = RoofSlope.from_house_right_edge(house, axes, total_house_height=7.5, main_roof_angle=35)
            corners = house.corners(axes)
            for point, corner in zip((roof.start, roof.end), (corners[1], corners[2])):
                for actual, expected in zip(axes.to_local(*point), corner):
                    self.assertAlmostEqual(actual, expected)
            self.assertEqual(roof.elevation, 424.5)
            self.assertEqual(roof.angle_degrees, 35)
            midpoint = ((roof.start[0]+roof.end[0])/2, (roof.start[1]+roof.end[1])/2)
            self.assertAlmostEqual(roof.elevation_at(midpoint, axes), 424.5)

    def test_reads_current_house_roof_metrics_without_executing_house_code(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"house_ifc.py"
            source.write_text("raise RuntimeError('must not execute')\n"
                              "STREET_ROOF_PLANE_POINTS=((0,0,3),(1,0,3),(0,2,5))\n"
                              "GARDEN_ROOF_PLANE_POINTS=((0,4,3),(1,4,3),(0,2,5))\n"
                              "ROOF_TILE_BOTTOM=0.2\nROOF_TILE_THICKNESS=0.1\n"
                              "GROUND_FLOOR_THICKNESS=0.25\nHALF_DEPTH=2\n")
            height, angle = read_house_roof_metrics(source)
            self.assertAlmostEqual(height, 5+.3*sqrt(2)-.25)
            self.assertAlmostEqual(angle, 45)

    def test_two_house_roof_profiles_have_correct_heights_spacing_and_away_direction(self):
        axes = SurveyAxes.from_polylines(*self.placement_groups())
        for center, rotation in (((-10, 9.7), -5), ((15, 9), 30), ((-10, 9), -25)):
            with self.subTest(center=center, rotation=rotation):
                house = SurveyHouse(center=center, angle_degrees=rotation)
                low, high = house_roof_profiles(house, axes, total_house_height=7.5, main_roof_angle=35)
                original = RoofSlope.from_house_right_edge(house, axes, total_house_height=7.5, main_roof_angle=35)
                self.assertEqual((low.start, low.end), (original.start, original.end))
                self.assertEqual(low.elevation, 424.5-.875)
                self.assertEqual(high.elevation, 424.5)
                low_mid, direction, half_length = low.geometry(axes)
                high_mid, high_direction, high_half_length = high.geometry(axes)
                shift = tuple(b-a for a, b in zip(low_mid, high_mid))
                self.assertAlmostEqual(hypot(*shift), 2.25)
                self.assertAlmostEqual(sum(a*b for a, b in zip(shift, direction)), 0)
                for a, b in zip(direction, high_direction):
                    self.assertAlmostEqual(a, b)
                self.assertAlmostEqual(half_length, high_half_length)
                nx, ny = axes.neighbour_direction
                gap = lambda p: abs(-ny*p[0]+nx*p[1])
                self.assertGreater(gap(high_mid), gap(low_mid))
                # The profiles retain the same pitch and fall beyond both endpoints.
                self.assertEqual(high.angle_degrees, low.angle_degrees)
                self.assertLess(high.elevation_at((high.end[0]*2-high.start[0], high.end[1]*2-high.start[1]), axes),
                                high.elevation_at(high.end, axes))

    def test_render_uses_actual_runtime_house_height_and_angle_for_default_roof(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            source.write_text("\n\n".join(f"#{g.color}: {g.name}\n"+"\n".join(
                f"{p.number} {p.y} {p.x} {p.z}" for p in g.points) for g in self.placement_groups()))
            with redirect_stdout(StringIO()):
                render_survey_points(source, output, house=SurveyHouse(), house_roof=True,
                                     total_house_height=7.5, main_roof_angle=35)
            root = ET.parse(output).getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
            roof, inner_roof = data["roof_slopes"]
            self.assertEqual(roof["elevation"], 424.5-.875)
            self.assertEqual(inner_roof["elevation"], 424.5)
            self.assertEqual(roof["angle_degrees"], 35)
            axes = SurveyAxes.from_polylines(*self.placement_groups())
            for point, corner in zip((roof["start"], roof["end"]), data["house"]["local_corners"][1:3]):
                for actual, expected in zip(axes.to_local(*point), corner):
                    self.assertAlmostEqual(actual, expected)

    def test_roof_height_falls_both_ways_without_end_limits_and_is_constant_across(self):
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (.6, .8))
        roof = RoofSlope(start=(1, 2), end=(1, 12), elevation=423, angle_degrees=45)
        for point, height in (((1, 7), 423), ((1, 5), 421), ((1, 9), 421),
                              ((1, 2), 418), ((1, 12), 418), ((1, 22), 408), ((1, -8), 408)):
            self.assertAlmostEqual(roof.elevation_at(point, axes), height)
            reverse = RoofSlope(roof.end, roof.start, roof.elevation, roof.angle_degrees)
            self.assertAlmostEqual(reverse.elevation_at(point, axes), height)
        mx, my = axes.to_local(1, 7)
        across = axes.from_local(mx-.8*3, my+.6*3)
        self.assertAlmostEqual(roof.elevation_at(across, axes), 423)

    def test_roof_slope_uses_actual_plan_distance_and_overhang_only_affects_preview(self):
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (.6, .8))
        roof = RoofSlope(start=(0, 0), end=(4, 3), elevation=423, angle_degrees=45)
        # Endpoint Cartesian position is (5.8, 2.4), not (4, 3).
        length = hypot(5.8, 2.4)
        self.assertAlmostEqual(roof.elevation_at((2, 1.5), axes), 423)
        self.assertAlmostEqual(roof.elevation_at((4, 3), axes), 423-length/2)
        for overhang in (0, 2, 5):
            a, b = roof.drawing_endpoints(axes, overhang)
            self.assertAlmostEqual(hypot(b[0]-a[0], b[1]-a[1]), length+2*overhang)
            for point in (a, b):
                self.assertAlmostEqual(roof.elevation_at(axes.from_local(*point), axes), 423-length/2-overhang)
        self.assertAlmostEqual(roof.elevation_at((40, 30), axes), 423-9.5*length)

    def test_roof_rejects_undefined_geometry_and_flat_roof_stays_at_peak(self):
        for args in (((0, 0), (0, 0), 423, 35), ((0, 0), (1, 0), 423, -1),
                     ((0, 0), (1, 0), 423, 90), ((0, 0), (1, 0), float("nan"), 35),
                     ((0, 0), (float("inf"), 0), 423, 35)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                RoofSlope(*args)
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (.6, .8))
        roof = RoofSlope((0, 0), (1, 1), 423, 0)
        self.assertEqual(roof.elevation_at((100, -100), axes), 423)
        with self.assertRaisesRegex(ValueError, "overhang"):
            roof.drawing_endpoints(axes, -1)

    def test_roof_export_has_gradient_peak_label_metadata_and_works_without_house(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            source.write_text("\n\n".join(f"#{g.color}: {g.name}\n"+"\n".join(
                f"{p.number} {p.y} {p.x} {p.z}" for p in g.points) for g in self.placement_groups()))
            roof = RoofSlope((-10, 5), (-10, 14), 423, 35)
            for house in (None, SurveyHouse()):
                with self.subTest(house=house), redirect_stdout(StringIO()):
                    render_survey_points(source, output, house=house, roof_slopes=(roof,), roof_overhang=3)
                    root = ET.parse(output).getroot()
                    ns = {"s": "http://www.w3.org/2000/svg"}
                    data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
                    self.assertTrue(data["roof_slopes"][0]["unbounded"])
                    self.assertEqual(data["roof_slopes"][0]["drawing_overhang"], 3)
                    paths = root.findall('.//s:g[@id="survey-roof-slope-0"]/s:path', ns)
                    self.assertEqual(len(paths), 256)
                    colors = [re.search(r"stroke: (#\w+)", p.get("style")).group(1) for p in paths]
                    # The red peak has much less green than the pale endpoints.
                    self.assertLess(int(colors[127][3:5], 16), int(colors[0][3:5], 16))
                    self.assertEqual(colors[0], colors[-1])
                    label = root.find('.//s:g[@id="survey-roof-label-0"]', ns)
                    self.assertIn("423.00 m", "".join(label.itertext()))
                    self.assertIn("35°", "".join(label.itertext()))

    def placement_groups(self):
        frame = SurveyFrame(588800, 1144300, -pi)
        def point(number, x, y):
            sy, sx = frame.to_survey(x, y)
            return SurveyPoint(str(number), sy, sx, 417)
        return (SurveyGroup("blue", (point(1, -5, 0), point(2, 5, 0)), name="street"),
                SurveyGroup("red", (point(3, 0, 0), point(4, 2, 4), point(5, 4, 8)), name="neighbour"))

    def test_oblique_axes_use_line_intersection_and_unit_distances(self):
        street, neighbour = self.placement_groups()
        axes = SurveyAxes.from_polylines(street, neighbour)
        self.assertAlmostEqual(axes.frame.origin_y, 588800)
        self.assertAlmostEqual(axes.frame.origin_x, 1144300)
        self.assertEqual(axes.to_local(0, 0), (0, 0))
        nx, ny = axes.neighbour_direction
        self.assertAlmostEqual(nx, 1/sqrt(5), places=8)
        self.assertAlmostEqual(ny, 2/sqrt(5), places=8)
        self.assertAlmostEqual(hypot(*axes.to_local(0, 1)), 1)
        self.assertEqual(axes.to_local(1, 0), (1, 0))
        for x, y in ((3, 4), (-8, 7), (0, -5)):
            local = axes.to_local(x, y)
            self.assertAlmostEqual(local[0], x+y/sqrt(5), places=8)
            self.assertAlmostEqual(local[1], y*2/sqrt(5), places=8)
            for actual, expected in zip(axes.from_local(*local), (x, y)):
                self.assertAlmostEqual(actual, expected)
        # Both fitted lines must pass through the calculated origin.
        for group in (street, neighbour):
            fit = SurveyFrame.for_polyline(group)
            self.assertAlmostEqual(fit.to_local(axes.frame.origin_y, axes.frame.origin_x)[1], 0, places=8)
        reversed_neighbour = SurveyGroup("red", neighbour.points[::-1])
        reversed_axes = SurveyAxes.from_polylines(street, reversed_neighbour)
        for a, b in zip(reversed_axes.neighbour_direction, axes.neighbour_direction):
            self.assertAlmostEqual(a, b, places=8)

    def test_house_stays_rectangular_and_rotates_about_its_oblique_center(self):
        axes = SurveyAxes.from_polylines(*self.placement_groups())
        center = axes.to_local(-8, 7)
        for angle in (0, 30, 90, -25):
            with self.subTest(angle=angle):
                house = SurveyHouse(center=(-8, 7), angle_degrees=angle, width=11.6, depth=8.4)
                corners = house.corners(axes)
                for i in range(2):
                    self.assertAlmostEqual(sum(p[i] for p in corners)/4, center[i])
                edges = [(corners[(i+1)%4][0]-corners[i][0], corners[(i+1)%4][1]-corners[i][1])
                         for i in range(4)]
                for edge, length in zip(edges, (11.6, 8.4, 11.6, 8.4)):
                    self.assertAlmostEqual(hypot(*edge), length)
                self.assertAlmostEqual(sum(a*b for a, b in zip(edges[0], edges[1])), 0)
                self.assertAlmostEqual(edges[0][0], 11.6*cos(radians(angle)))
                self.assertAlmostEqual(edges[0][1], 11.6*sin(radians(angle)))

    def test_neighbour_window_lies_on_fitted_line_at_775_metres_with_requested_elevation(self):
        street, neighbour = self.placement_groups()
        axes = SurveyAxes.from_polylines(street, neighbour)
        point = neighbour_window_point(axes)
        local = axes.frame.to_local(point.y, point.x)
        self.assertAlmostEqual(hypot(*local), 7.75, places=8)
        for actual, expected in zip(axes.from_local(*local), (0, 7.75)):
            self.assertAlmostEqual(actual, expected, places=8)
        self.assertAlmostEqual(SurveyFrame.for_polyline(neighbour).to_local(point.y, point.x)[1], 0, places=8)
        self.assertEqual((point.number, point.note, point.z), ("neighbour-window", "neighbour window", 417.60))

    def test_neighbour_window_is_exported_with_label_independently_of_house(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            source.write_text("\n\n".join(f"#{g.color}: {g.name}\n"+"\n".join(
                f"{p.number} {p.y} {p.x} {p.z}" for p in g.points) for g in self.placement_groups()))
            original = source.read_bytes()
            for house in (None, SurveyHouse()):
                with self.subTest(house=house), redirect_stdout(StringIO()):
                    render_survey_points(source, output, house=house)
                    root = ET.parse(output).getroot()
                    ns = {"s": "http://www.w3.org/2000/svg"}
                    data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
                    derived = [p for p in data["points"] if p["number"] == "neighbour-window"]
                    self.assertEqual(len(derived), 1)
                    self.assertEqual(derived[0]["z"], 417.60)
                    self.assertEqual(data["derived_points"]["neighbour-window"]["axes_coordinates"], [0.0, 7.75])
                    self.assertFalse(any("neighbour-window" in g["point_ids"] for g in data["groups"]))
                    label = root.find('.//s:g[@id="survey-label-neighbour-window"]', ns)
                    text = "".join(label.itertext())
                    self.assertIn("neighbour window", text)
                    self.assertIn("417.60", text)
            self.assertEqual(source.read_bytes(), original)

    def test_placement_rejects_parallel_lines_missing_names_and_bad_dimensions(self):
        street, neighbour = self.placement_groups()
        with self.assertRaisesRegex(ValueError, "parallel"):
            SurveyAxes.from_polylines(street, street)
        for kwargs in ({"width": 0}, {"depth": -1}, {"angle_degrees": float("nan")},
                       {"center": (float("inf"), 0)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SurveyHouse(**kwargs)
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            source.write_text("#blue: street\n1 588800 1144300 417\n2 588803 1144304 418\n")
            with self.assertRaisesRegex(ValueError, "requires named street and neighbour"):
                render_survey_points(source, Path(directory)/"points.svg", house=SurveyHouse())

    def test_shortest_house_distances_use_perpendicular_gaps_on_both_sides_and_rotation(self):
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (.6, .8))
        for center in ((-5, 5), (5, -5)):
            for angle, street, neighbour in ((0, 3.0, 1.8), (90, 2.0, 2.0)):
                with self.subTest(center=center, angle=angle):
                    house = SurveyHouse(center=center, width=4, depth=2, angle_degrees=angle)
                    distances = house.line_distances(axes)
                    self.assertAlmostEqual(distances["street"], street)
                    self.assertAlmostEqual(distances["neighbour"], neighbour)

    def test_shortest_house_distances_are_zero_for_crossing_or_touching_lines(self):
        axes = SurveyAxes(SurveyFrame(588800, 1144300), (.6, .8))
        for angle in (0, 25, 90):
            house = SurveyHouse(center=(0, 0), width=4, depth=2, angle_degrees=angle)
            self.assertEqual(house.line_distances(axes), {"street": 0.0, "neighbour": 0.0})
        touching_street = SurveyHouse(center=(-10, 1.25), width=4, depth=2)
        self.assertAlmostEqual(touching_street.line_distances(axes)["street"], 0)
        touching_neighbour = SurveyHouse(center=(-2.75, 4), width=4, depth=2)
        self.assertAlmostEqual(touching_neighbour.line_distances(axes)["neighbour"], 0)

    def test_house_export_preserves_rectangle_scale_and_oblique_coordinates(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            source.write_text("\n\n".join(f"#{g.color}: {g.name}\n"+"\n".join(
                f"{p.number} {p.y} {p.x} {p.z}" for p in g.points) for g in self.placement_groups()))
            house = SurveyHouse(center=(-8, 7), angle_degrees=25, width=11.6, depth=8.4)
            terminal = StringIO()
            with redirect_stdout(terminal):
                render_survey_points(source, output, house=house)
            for name in ("street", "neighbour"):
                self.assertRegex(terminal.getvalue(), rf"Shortest house distance to {name}: \d+\.\d{{3}} m")
            root = ET.parse(output).getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
            self.assertEqual(data["house"]["center"], [-8, 7])
            self.assertEqual(data["house"]["angle_degrees"], 25)
            self.assertAlmostEqual(hypot(*data["placement_axes"]["y_direction"]), 1)
            path = root.find('.//s:g[@id="survey-house-footprint"]/s:path', ns)
            coords = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.get("d"))]
            vertices = list(zip(coords[::2], coords[1::2]))
            self.assertEqual(len(vertices), 5)
            self.assertEqual(vertices[0], vertices[-1])
            self.assertAlmostEqual(hypot(vertices[1][0]-vertices[0][0], vertices[1][1]-vertices[0][1]),
                                   11.6*1000/data["scale"]*72/25.4, places=5)
            frame = SurveyFrame(**data["frame"])
            for local, survey in zip(data["house"]["local_corners"], data["house"]["survey_corners"]):
                for actual, expected in zip(frame.to_local(*survey), local):
                    self.assertAlmostEqual(actual, expected, places=8)

    def test_named_polylines_are_indexed_and_blank_lines_reset_names(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            source.write_text("#0000ff: street\n1 588800 1144300 417\n2 588803 1144304 418\n"
                              "\n#red, closed: boundary\n2 588803 1144304 418\n"
                              "3 588810 1144310 420\n\n4 588811 1144311 421\n")
            groups = read_survey_groups(source)
            polylines = named_survey_groups(groups)
            self.assertEqual(list(polylines), ["street", "boundary"])
            self.assertIs(polylines["street"], groups[0])
            self.assertEqual(groups[0].color, "#0000ff")
            self.assertTrue(polylines["boundary"].closed)
            self.assertIsNone(groups[-1].name)
            for bad_header in ("#blue: street", "#blue:   "):
                source.write_text("#blue: street\n1 588800 1144300 417\n\n"
                                  +bad_header+"\n2 588803 1144304 418\n")
                with self.assertRaisesRegex(ValueError, "duplicate survey polyline name|empty survey polyline name"):
                    read_survey_groups(source)

    def test_orthogonal_fit_handles_noise_reordering_and_repeated_vertices(self):
        # Along-line (3/5, 4/5) coordinates and symmetric perpendicular noise:
        # covariance along/across is zero, so the best-fit angle is known.
        points = tuple(SurveyPoint(str(i), 588800-(.6*t-.8*d), 1144300-(.8*t+.6*d), 417+i)
                       for i, (t, d) in enumerate(zip((-10, -5, 0, 5, 10), (.2, -.4, .4, -.4, .2))))
        frame = SurveyFrame.for_polyline(SurveyGroup("blue", points, name="street"))
        self.assertAlmostEqual(frame.rotation_radians, atan2(4, 3), places=9)
        self.assertAlmostEqual(frame.origin_y, 588800)
        self.assertAlmostEqual(frame.origin_x, 1144300)
        residuals = [frame.to_local(p.y, p.x)[1] for p in points]
        for actual, expected in zip(residuals, (.2, -.4, .4, -.4, .2)):
            self.assertAlmostEqual(actual, expected, places=8)
        for reordered in (points[::-1], points+(points[0],)):
            self.assertEqual(frame, SurveyFrame.for_polyline(SurveyGroup("blue", reordered)))
        for point in (*points, SurveyPoint("other", 588825, 1144280, 430)):
            self.assertEqual(frame.to_survey(*frame.to_local(point.y, point.x)), (point.y, point.x))
        a, b = frame.to_local(points[0].y, points[0].x), frame.to_local(points[-1].y, points[-1].x)
        self.assertAlmostEqual(hypot(a[0]-b[0], a[1]-b[1]),
                               hypot(points[0].y-points[-1].y, points[0].x-points[-1].x))

    def test_vertical_street_and_undefined_fits(self):
        a = SurveyPoint("1", 588800, 1144300, 417)
        b = SurveyPoint("2", 588800, 1144290, 418)
        frame = SurveyFrame.for_polyline(SurveyGroup("blue", (a, b)))
        self.assertAlmostEqual(frame.rotation_radians, pi/2)
        self.assertAlmostEqual(frame.to_local(a.y, a.x)[1], 0)
        self.assertAlmostEqual(frame.to_local(b.y, b.x)[1], 0)
        coincident = SurveyPoint("3", a.y, a.x, 420)
        square = tuple(SurveyPoint(str(i), 588800+y, 1144300+x, 417)
                       for i, (y, x) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))))
        for points in ((a,), (a, coincident), square):
            with self.subTest(points=points), self.assertRaises(ValueError):
                SurveyFrame.for_polyline(SurveyGroup("blue", points, name="street"))

    def test_street_export_is_horizontal_preserves_source_and_other_named_groups(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            contents = ("#blue: street\n1 588800 1144300 417\n2 588803 1144304 418\n"
                        "3 588806 1144308 419\n\n#red: neighbour\n"
                        "2 588803 1144304 418\n4 588810 1144300 420\n")
            source.write_text(contents)
            with redirect_stdout(StringIO()):
                render_survey_points(source, output)
            root = ET.parse(output).getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
            self.assertEqual([g["name"] for g in data["groups"]], ["street", "neighbour"])
            self.assertEqual(data["points"][1]["z"], 418)
            frame = SurveyFrame(**data["frame"])
            fitted = SurveyFrame.for_polyline(named_survey_groups(read_survey_groups(source))["street"])
            self.assertAlmostEqual(frame.rotation_radians, fitted.rotation_radians-pi)
            for point in data["points"]:
                before = fitted.to_local(point["y"], point["x"])
                after = frame.to_local(point["y"], point["x"])
                for old, new in zip(before, after):
                    self.assertAlmostEqual(new, -old)
            for point in data["points"][:3]:
                self.assertAlmostEqual(frame.to_local(point["y"], point["x"])[1], 0, places=8)
            path = root.find('.//s:g[@id="survey-group-0"]/s:path', ns)
            coords = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.get("d"))]
            self.assertAlmostEqual(max(coords[1::2]), min(coords[1::2]), places=5)
            text = "".join(root.itertext())
            self.assertIn("x podél ulice", text)
            self.assertEqual(source.read_text(), contents)

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

    def test_rejects_swapped_columns_conflicting_ids_and_bad_rows(self):
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

    def test_repeated_point_can_be_shared_by_groups_and_drawn_once(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            contents = ("#red\n1 588805 1144300 417 A\n26 588800 1144300 418 shared\n"
                        "\n#blue\n26 588800 1144300 418 other note\n"
                        "2 588800 1144305 419 B\n26 588800 1144300 418 other note\n")
            source.write_text(contents, encoding="utf-8")
            groups = read_survey_groups(source)
            self.assertEqual([[p.number for p in group.points] for group in groups],
                             [["1", "26"], ["26", "2", "26"]])
            unique = read_survey_points(source)
            self.assertEqual([p.number for p in unique], ["1", "26", "2"])
            self.assertEqual(unique[1].note, "shared")
            self.assertEqual(source.read_text(), contents)

    def test_repeated_id_with_different_coordinates_identifies_both_lines(self):
        with TemporaryDirectory() as directory:
            source = Path(directory)/"points.txt"
            for values in ((588801, 1144300, 418), (588800, 1144301, 418), (588800, 1144300, 419)):
                with self.subTest(values=values):
                    source.write_text("#red\n26 588800 1144300 418\n\n#blue\n"
                                      +"26 "+" ".join(str(v) for v in values)+"\n")
                    with self.assertRaisesRegex(ValueError, "conflicting coordinates.*'26'.*line 5.*line 2"):
                        read_survey_groups(source)

    def test_export_keeps_both_polylines_and_one_marker_label_and_record_for_shared_point(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/"points.txt", Path(directory)/"points.svg"
            source.write_text("#red\n26 588800 1144300 418 shared\n1 588805 1144300 417 A\n"
                              "\n#blue\n2 588800 1144305 419 B\n26 588800 1144300 418 shared\n")
            with redirect_stdout(StringIO()):
                render_survey_points(source, output, show_ids=True)
            root = ET.parse(output).getroot()
            ns = {"s": "http://www.w3.org/2000/svg"}
            data = json.loads(root.find('s:metadata[@id="survey-data"]', ns).text)
            self.assertEqual([p["number"] for p in data["points"]], ["26", "1", "2"])
            self.assertEqual([g["point_ids"] for g in data["groups"]], [["26", "1"], ["2", "26"]])
            for kind in ("point", "label"):
                self.assertEqual(len(root.findall(f'.//s:g[@id="survey-{kind}-26"]', ns)), 1)
            ids = [e.get("id") for e in root.iter() if e.get("id")]
            self.assertEqual(len(ids), len(set(ids)))
            paths = [root.find(f'.//s:g[@id="survey-group-{i}"]/s:path', ns) for i in range(2)]
            coordinates = [[float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", p.get("d"))]
                           for p in paths]
            self.assertEqual(coordinates[0][:2], coordinates[1][-2:])

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
            self.assertEqual(data["groups"], [{"color": "#ff0000", "closed": False, "name": None,
                                               "point_ids": ["10", "1"]},
                                              {"color": None, "closed": False, "name": None,
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
