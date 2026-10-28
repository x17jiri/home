"""Projected tile pitch, clipping, metadata and export-only mirroring."""

import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from shapely.geometry import LineString, Polygon

from ifc_utils import House
from roof_tile_patterns import add_roof_tile_patterns


SVG = "{http://www.w3.org/2000/svg}"


class RoofTilePatternTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Tile projection")
        self.roof = self.house.storey("Roof", elevation=0).roof("Roof")
        assets = (Path(__file__).parent / "drawings/assets/patterns.svg").read_text(encoding="utf-8")
        self.template = re.search(r'<pattern id="roof-tiles".*?</pattern>', assets, re.DOTALL)[0]
        self.camera = np.array(((-1., 0, 0, 0), (0, 0, 1, 5), (0, 1, 0, 0), (0, 0, 0, 1)))

    def layer(self, pitch=35, x=0):
        plane = self.roof.plane(f"Slope {len(self.roof.file.by_type('IfcSlab'))}",
            points=((x, 0, 4), (x+4, 0, 4), (x, 4, 4-4*np.tan(np.radians(pitch)))))
        return plane.layer("Tiles", outline=((0, 0), (2, 0), (2, 3), (0, 3)),
            z_offset=.2, thickness=.03, material="Roof tiles").set_tile_pattern(width=.3, course_length=.32)

    @staticmethod
    def token(layer):
        return "GlobalId-" + re.sub("[^0-9a-zA-Z]+", "", layer.GlobalId)

    def document(self, layers, scale=10, units=1, camera=None, mirrored=False):
        camera = self.camera if camera is None else camera
        matrix = np.array(((scale*units, 0, 60*units), (0, scale*units, 60*units), (0, 0, 1)))
        faces = []
        for layer in layers:
            rings = []
            for coordinates in (((0, 0), (2, 0), (2, 3), (0, 3)),
                                ((.5, .8), (.5, 1.2), (.9, 1.2), (.9, .8))):
                points = []
                for x, y in coordinates:
                    world = np.array((*layer.plane.to_world((x, y, layer.z_offset + layer.thickness)), 1))
                    if mirrored:
                        world[0] *= -1
                    local = np.linalg.inv(camera) @ world
                    point = matrix @ (local[0], -local[1], 1)
                    points.append(f"{point[0]:.9g},{point[1]:.9g}")
                rings.append("M" + " L".join(points) + " Z")
            faces.append(f'<path class="IfcSlab material-Rooftiles {self.token(layer)} surface" '
                         f'd="{" ".join(rings)}"/>')
        faces = "".join(faces)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" '
                f'width="100mm" height="100mm" viewBox="0 0 {100*units} {100*units}">'
                f'<defs>{self.template}</defs><g class="section" '
                f"ifc:plane='{json.dumps(camera.tolist())}' ifc:matrix3='{json.dumps(matrix.tolist())}'>"
                f'{faces}<g class="IfcSlab material-Rooftiles cut" id="cut"><path d="M1,1 L2,1 L2,2 Z"/></g>'
                '<g class="IfcSlab material-Rooftiles projection" id="edge"><path d="M1,1 L2,1"/></g>'
                '<path class="IfcBeam material-Wood surface" d="M0,0 L1,0 L1,1 Z"/>'
                '</g></svg>')

    def process(self, text, model=None):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roof.svg"
            path.write_text(text, encoding="utf-8")
            count = add_roof_tile_patterns(path, self.house.model if model is None else model)
            result = path.read_text(encoding="utf-8")
            self.assertEqual(add_roof_tile_patterns(path, self.house.model if model is None else model), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), result)
        return count, ET.fromstring(result), result

    @staticmethod
    def patterns(root):
        return [e for e in root.iter(SVG + "pattern") if e.get("id").startswith("roof-tiles-")]

    @staticmethod
    def matrix(pattern):
        values = [float(v) for v in re.findall(r"[-+0-9.eE]+", pattern.get("patternTransform")[7:-1])]
        return np.array(((values[0], values[2], values[4]), (values[1], values[3], values[5]), (0, 0, 1)))

    def test_main_dormer_and_lower_roof_rows_are_foreshortened_independently(self):
        pitches = (35, 15, 37)
        layers = [self.layer(pitch, x=i*3) for i, pitch in enumerate(pitches)]
        count, root, _ = self.process(self.document(layers))
        self.assertEqual(count, 3)
        patterns = self.patterns(root)
        self.assertEqual(len(patterns), 3)
        for pattern, pitch in zip(patterns, pitches):
            matrix = self.matrix(pattern)
            self.assertAlmostEqual(np.linalg.norm(matrix[:2, 0]), 3)
            self.assertAlmostEqual(np.linalg.norm(matrix[:2, 1]), 3.2*np.sin(np.radians(pitch)))
            self.assertEqual(pattern.get("data-tile-width-mm"), "300")
            self.assertEqual(pattern.get("data-course-mm"), "320")

    def test_pattern_has_a_configurable_color_and_black_curved_outlines(self):
        pattern = ET.fromstring(self.template)
        self.assertEqual(len(pattern), 2)
        self.assertEqual(pattern[0].tag, "rect")
        self.assertRegex(pattern[0].get("fill"), r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(pattern[1].tag, "path")
        self.assertEqual(pattern[1].get("fill"), "none")
        self.assertEqual(pattern[1].get("stroke"), "black")
        self.assertIn(" C ", pattern[1].get("d"))

    def test_projected_patterns_preserve_the_configured_background_color(self):
        layer = self.layer()
        document = self.document([layer])
        original_color = ET.fromstring(self.template).find("rect").get("fill")
        for color in ("#a64b35", "#ddeeff", "white"):
            with self.subTest(color=color):
                _, root, _ = self.process(document.replace(original_color, color))
                pattern, = self.patterns(root)
                self.assertEqual(pattern.find(SVG + "rect").get("fill"), color)
                self.assertEqual(pattern.find(SVG + "path").get("fill"), "black")

    def test_exposed_tile_edge_has_the_background_color_without_a_pattern(self):
        layer = self.layer()
        text = self.document([layer])
        edge = (f'<path id="tile-side" class="IfcSlab material-Rooftiles {self.token(layer)} surface" '
                'style="stroke:none;" d="M1,1 L9,1 L9,1.4 L1,1.4 Z"/>')
        text = text.replace('<g class="IfcSlab material-Rooftiles cut"', edge + '<g class="IfcSlab material-Rooftiles cut"')
        original_color = ET.fromstring(self.template).find("rect").get("fill")
        for color in ("#f17130", "#ddeeff", "white"):
            with self.subTest(color=color):
                count, root, _ = self.process(text.replace(original_color, color))
                self.assertEqual(count, 1)  # Top only, never the narrow edge.
                side = next(e for e in root.iter() if e.get("id") == "tile-side")
                self.assertIn(f"fill:{color} !important;", side.get("style"))
                self.assertIn("stroke:none;", side.get("style"))
                self.assertNotIn("url(", side.get("style"))
                self.assertFalse(any(e.get("class") == "roof-tile-hatch" and e.get("d") == side.get("d")
                                     for e in root.iter()))

    def test_one_merged_material_surface_gets_both_main_and_dormer_patterns(self):
        main, dormer = self.layer(35), self.layer(15)
        text = self.document([main, dormer])
        faces = [e for e in ET.fromstring(text).iter(SVG + "path")
                 if "surface" in e.get("class", "").split()]
        points = np.concatenate([
            np.asarray([float(v) for v in re.findall(r"[-+0-9.eE]+", e.get("d").split("Z")[0].replace("M", "").replace("L", ""))]).reshape(-1, 2)
            for e in faces])
        lo, hi = points.min(axis=0), points.max(axis=0)
        data = f"M{lo[0]},{lo[1]} L{hi[0]},{lo[1]} L{hi[0]},{hi[1]} L{lo[0]},{hi[1]} Z"
        # Bonsai assigns only the main slab's raycast ID to the merged region.
        composite = f'<path class="IfcSlab material-Rooftiles {self.token(main)} surface" d="{data}"/>'
        text = re.sub(r'<path class="IfcSlab material-Rooftiles [^"]* surface" d="[^"]*"/>', '', text)
        marker = '<g class="IfcSlab material-Rooftiles cut"'
        text = text.replace(marker, composite + marker)
        count, root, _ = self.process(text)
        self.assertEqual(count, 2)
        patterns = self.patterns(root)
        self.assertEqual(len(patterns), 2)
        row_heights = sorted(np.linalg.norm(self.matrix(p)[:2, 1]) for p in patterns)
        np.testing.assert_allclose(row_heights, sorted(3.2*np.sin(np.radians(p)) for p in (35, 15)))
        regions = []
        for clip in root.iter(SVG + "clipPath"):
            region = None
            for ring in re.findall(r"M (.*?) Z", clip[0].get("d")):
                values = [float(v) for v in re.findall(r"[-+0-9.eE]+", ring.replace("L", ""))]
                polygon = Polygon(np.asarray(values).reshape(-1, 2))
                region = polygon if region is None else region.symmetric_difference(polygon)
            self.assertGreater(region.area, 1)
            regions.append(region)
        self.assertLess(regions[0].intersection(regions[1]).area, 1e-4)

    def test_plan_rows_follow_cosine_not_elevation_sine(self):
        layer = self.layer(35)
        camera = np.eye(4)
        camera[2, 3] = 10
        _, root, _ = self.process(self.document([layer], camera=camera))
        pattern, = self.patterns(root)
        self.assertAlmostEqual(np.linalg.norm(self.matrix(pattern)[:2, 1]), 3.2*np.cos(np.radians(35)))

    def test_drawing_scale_and_non_mm_viewbox_scale_geometry_but_not_printed_stroke(self):
        layer = self.layer(15)  # Strong foreshortening must not thin course edges.
        for scale in (10, 20):
            for units in (1, 2):
                with self.subTest(scale=scale, units=units):
                    _, root, _ = self.process(self.document([layer], scale=scale, units=units))
                    pattern, = self.patterns(root)
                    self.assertAlmostEqual(np.linalg.norm(self.matrix(pattern)[:2, 0]), .3*scale*units)
                    line = pattern.find(SVG + "path")
                    self.assertEqual(pattern.get("data-line-width-mm"), "0.06")
                    self.assertEqual(line.get("fill"), "black")
                    self.assertEqual(line.get("stroke"), "none")
                    outline = None
                    transform = self.matrix(pattern)
                    for ring in re.findall(r"M (.*?) Z", line.get("d")):
                        coords = np.asarray([float(v) for v in re.findall(r"[-+0-9.eE]+", ring.replace("L", ""))]).reshape(-1, 2)
                        coords = (transform @ np.column_stack((coords, np.ones(len(coords)))).T).T[:, :2]
                        polygon = Polygon(coords)
                        outline = polygon if outline is None else outline.symmetric_difference(polygon)
                    centre = (transform @ (.5, .05, 1))[:2]
                    probe = LineString((centre + (0, -.15*units), centre + (0, .15*units)))
                    self.assertAlmostEqual(outline.intersection(probe).length, .06*units, places=6)

    def test_oblique_camera_projects_both_tile_axes_with_shear(self):
        layer = self.layer(35)
        camera = np.eye(4)
        camera[:3, 2] = np.array((-1, 1, 0)) / np.sqrt(2)
        camera[:3, 1] = (0, 0, 1)
        camera[:3, 0] = np.cross(camera[:3, 1], camera[:3, 2])
        camera[:3, 3] = (-5, 5, 0)
        _, root, _ = self.process(self.document([layer], camera=camera))
        pattern, = self.patterns(root)
        matrix = self.matrix(pattern)
        self.assertAlmostEqual(np.linalg.norm(matrix[:2, 0]), 3/np.sqrt(2))
        axis = layer.plane.y_axis
        expected = 3.2*np.sqrt(1 - np.dot(axis, camera[:3, 2])**2)
        self.assertAlmostEqual(np.linalg.norm(matrix[:2, 1]), expected)
        self.assertGreater(abs(float(matrix[:2, 0] @ matrix[:2, 1])), .1)

    def test_geometry_before_the_section_camera_does_not_occlude_the_retained_roof(self):
        layer = self.layer(35)
        camera = self.camera.copy()
        camera[1, 3] = 1  # Camera now cuts through this roof instead of seeing it whole.
        _, root, _ = self.process(self.document([layer], camera=camera))
        clip, = list(root.iter(SVG + "clipPath"))
        region = None
        for ring in re.findall(r"M (.*?) Z", clip[0].get("d")):
            values = [float(v) for v in re.findall(r"[-+0-9.eE]+", ring.replace("L", ""))]
            polygon = Polygon(np.asarray(values).reshape(-1, 2))
            region = polygon if region is None else region.symmetric_difference(polygon)
        self.assertGreater(region.area, 1)
        self.assertLess(region.area, 200)  # The original full projected top exceeds 340.

    def test_pattern_clips_to_real_top_faces_not_slab_thickness_or_window_holes(self):
        self.roof.add_opening("Window", rectangle=((.6, .5), (1.1, 1.3)), trimmers=False)
        layer = self.layer(35)
        _, root, _ = self.process(self.document([layer]))
        clip, = list(root.iter(SVG + "clipPath"))
        data = clip.find(SVG + "path").get("d")
        area_region = None
        for ring in re.findall(r"M (.*?) Z", data):
            coords = [float(v) for v in re.findall(r"[-+0-9.eE]+", ring.replace("L", ""))]
            polygon = Polygon(np.array(coords).reshape(-1, 2))
            area_region = polygon if area_region is None else area_region.symmetric_difference(polygon)
        area = area_region.area
        expected = (6 - (.5*.8)/np.cos(np.radians(35))) * np.sin(np.radians(35)) * 100
        self.assertAlmostEqual(area, expected, places=5)
        # Even-odd surface contours are copied verbatim; cuts and native edges stay unchanged.
        hatch, = [p for p in root.iter(SVG + "path") if p.get("class") == "roof-tile-hatch"]
        source = next(e for e in ET.fromstring(self.document([layer])).iter(SVG + "path")
                      if "surface" in e.get("class", "").split())
        self.assertEqual(hatch.get("d"), source.get("d"))
        self.assertEqual(hatch.get("d").count("M"), 2)

    def test_cut_and_projection_linework_remain_unmodified(self):
        layer = self.layer()
        text = self.document([layer])
        _, root, result = self.process(text)
        for name in ("cut", "edge"):
            before = next(e for e in ET.fromstring(text).iter() if e.get("id") == name)
            after = next(e for e in root.iter() if e.get("id") == name)
            self.assertEqual(ET.tostring(before), ET.tostring(after))
        face, = [e for e in root.iter(SVG + "path") if "surface" in e.get("class", "").split()
                  and "material-Rooftiles" in e.get("class", "").split()]
        self.assertLess(result.index(face.get("d")), result.index('class="roof-tile-hatch"'))
        self.assertLess(result.index('class="roof-tile-hatch"'), result.index('id="cut"'))
        stylesheet = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text(encoding="utf-8")
        self.assertIn("fill: #a64b35 !important", stylesheet.split(".material-Rooftiles.cut {", 1)[1].split("}", 1)[0])

    def test_roofs_seen_edge_on_or_from_underneath_are_not_hatched(self):
        layer = self.layer()
        for edge_on, camera in (
            (True, np.array(((0., 0, 1, 5), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))),
            (False, np.array(((1., 0, 0, 0), (0, 0, -1, -5), (0, 1, 0, 0), (0, 0, 0, 1)))),
        ):
            text = self.document([layer], camera=camera)
            count, root, result = self.process(text)
            self.assertEqual(count, 0)
            self.assertFalse(any(e.get("class") == "roof-tile-hatch" for e in root.iter()))
            if edge_on:
                self.assertEqual(result, text)  # No closed face area to color.
                continue
            face = next(e for e in root.iter() if "surface" in e.get("class", "").split()
                        and "material-Rooftiles" in e.get("class", "").split())
            color = ET.fromstring(self.template).find("rect").get("fill")
            self.assertIn(f"fill:{color} !important;", face.get("style"))

    def test_missing_surface_metadata_or_template_leaves_svg_untouched(self):
        layer = self.layer()
        for text in (self.document([layer]).replace(self.token(layer), "GlobalId-unknown"),
                     self.document([layer]).replace('id="roof-tiles"', 'id="other-pattern"')):
            count, _, result = self.process(text)
            self.assertEqual(count, 0)
            self.assertEqual(result, text)

    def test_tile_pattern_metadata_updates_without_changing_geometry(self):
        layer = self.layer()
        representation = layer.Representation.to_string()
        self.assertIs(layer.set_tile_pattern(width=.25, course_length=.28), layer)
        properties = ifcopenshell.util.element.get_pset(layer, "BBIM_RoofTilePattern")
        self.assertEqual(properties["TileWidth"], .25)
        self.assertEqual(properties["CourseLength"], .28)
        self.assertEqual(layer.Representation.to_string(), representation)
        _, root, _ = self.process(self.document([layer]))
        pattern, = self.patterns(root)
        self.assertEqual(pattern.get("data-tile-width-mm"), "250")
        self.assertEqual(pattern.get("data-course-mm"), "280")
        for width, course in ((0, .32), (-1, .32), (.3, 0), (.3, float("nan"))):
            with self.subTest(width=width, course=course), self.assertRaises(ValueError):
                layer.set_tile_pattern(width=width, course_length=course)

    def test_mirrored_export_uses_exported_placements_not_unmirrored_roof_metadata(self):
        layer = self.layer(35, x=2)
        original_placement = ifcopenshell.util.placement.get_local_placement(layer.ObjectPlacement)
        _, before, _ = self.process(self.document([layer]))
        self.house.mirror_x = True
        model = self.house._export_model()
        _, after, _ = self.process(self.document([layer], mirrored=True), model=model)
        a = self.matrix(self.patterns(before)[0])
        b = self.matrix(self.patterns(after)[0])
        self.assertAlmostEqual(a[0, 2] + b[0, 2], 120)
        self.assertAlmostEqual(a[1, 2], b[1, 2])
        np.testing.assert_allclose(ifcopenshell.util.placement.get_local_placement(layer.ObjectPlacement), original_placement)

    def test_normal_drawing_render_runs_the_pass_and_preserves_surface_metadata(self):
        layer = self.layer()
        drawing = self.house.add_drawing("Elevation", x=0, y=5, z=3, radius=5,
                                        view="elevation", direction=(0, -1, 0))
        self.assertEqual(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Metadata"), "GlobalId")
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            self.house.write(directory / "roof.ifc")

            def render(command, **kwargs):
                Path(command[command.index("--output") + 1]).write_text(self.document([layer]), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                 patch("ifc_utils.subprocess.run", side_effect=render):
                output = drawing.render(directory / "elevation.svg")
            self.assertIn('class="roof-tile-hatch"', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
