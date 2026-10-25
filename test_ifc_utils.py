import json
import unittest
import xml.etree.ElementTree as ET
from math import hypot
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import call, patch

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
    CeilingLayer,
    Chimney,
    CutDefinition,
    CustomStair,
    ElektroLineDrawer,
    FacadeLayer,
    FloorLayer,
    House,
    HorizontalFrame,
    MiakoSlab,
    Roof,
    RoofLayer,
    RoofOpening,
    RoofPlane,
    RoofUValueResult,
    Stair,
    VerticalFrame,
    Wall,
    _BATTING_MARKER_PATH,
    _close_door_bodies,
    _drawing_pdf_options,
    _drawing_pdf_sheet,
    _export_drawing_pdf,
    _remove_3d_only_elements,
    _timber_schedule_member_styles,
    _overhead_mask_global_ids,
    _postprocess_angle_labels,
    _postprocess_drawing_title,
    _postprocess_drawing_line_colors,
    _postprocess_drawing_circles,
    _dashed_arrow_segments,
    _postprocess_door_overheads,
    _postprocess_elevation_furniture_labels,
    _postprocess_hexagon_marker_overlays,
    _postprocess_miako_beam_shell_shared_edges,
    _postprocess_miako_slab_end_faces,
    _postprocess_model_line_width,
    _postprocess_note_overlays,
    _postprocess_cut_symbol_overlays,
    _postprocess_change_floor_symbol_overlays,
    _postprocess_dimension_overlays,
    _postprocess_floor_corner_overlays,
    _postprocess_elevation_wall_insulation_depth,
    _postprocess_elevation_opening_overlays,
    _postprocess_projected_wood_fills,
    _postprocess_projected_wood_surface_styles,
    _postprocess_roof_opening_masks,
    _postprocess_pavatex_batting,
    _postprocess_ring_beam_stirrups,
    _postprocess_roof_batting,
    _postprocess_under_rafter_batting_depth,
    _postprocess_right_panel,
    _postprocess_vapour_barrier_overlays,
    _postprocess_wall_insulation_backdrop,
    _postprocess_wall_insulation_batting,
    calculate_roof_u_value,
    elliptic_stairs,
    generate_plan,
    offset_plane,
    plane_height_at,
    window_area,
)


class ReferenceBoxTests(unittest.TestCase):
    @staticmethod
    def bounds(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return vertices.min(axis=0), vertices.max(axis=0)

    def test_box_geometry_material_style_and_export_mirroring(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Boxes", mirror_x=mirror, colors={"box": "#80c0ff"})
                box = house.add_box("Reference", origin=(2, -3, -0.5),
                                    size=(1, 2, 2.5), material="Wood",
                                    transparency=0.5, show_in_drawings=False)
                self.assertEqual(box.ObjectType, "BOX")
                self.assertTrue(box.is_a("IfcBuildingElementProxy"))
                self.assertEqual(ifcopenshell.util.element.get_container(box), house.building)
                self.assertEqual(ifcopenshell.util.element.get_material(box).Name, "Wood")
                lower, upper = self.bounds(box)
                np.testing.assert_allclose(lower, (2, -3, -0.5))
                np.testing.assert_allclose(upper, (3, -1, 2))
                body = ifcopenshell.util.representation.get_representation(
                    box, "Model", "Body", "MODEL_VIEW")
                shading = body.Items[0].StyledByItem[0].Styles[0].Styles[0]
                rgb = shading.SurfaceColour
                np.testing.assert_allclose((rgb.Red, rgb.Green, rgb.Blue), (128 / 255, 192 / 255, 1))
                self.assertEqual(shading.Transparency, 0.5)
                exported = house._export_model().by_guid(box.GlobalId)
                lower, upper = self.bounds(exported)
                np.testing.assert_allclose(lower, (-3 if mirror else 2, -3, -0.5))
                np.testing.assert_allclose(upper, (-2 if mirror else 3, -1, 2))
                # Export reflection must not change the live helper coordinates.
                np.testing.assert_allclose(self.bounds(box)[0], (2, -3, -0.5))

    def test_validates_box_arguments_before_creating_elements(self):
        house = House("Boxes")
        defaults = dict(name="Box", origin=(0, 0, 0), size=(1, 2, 3))
        invalid = [
            ({"size": (0, 2, 3)}, ValueError),
            ({"size": (1, -2, 3)}, ValueError),
            ({"size": (1, 2, float("nan"))}, ValueError),
            ({"size": (1, 2)}, TypeError),
            ({"size": "123"}, TypeError),
            ({"origin": (0, 0)}, TypeError),
            ({"show_in_drawings": 0}, TypeError),
            ({"transparency": 1.1}, ValueError),
            ({"color": "not-a-color"}, ValueError),
        ]
        for overrides, error in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(error):
                house.add_box(**(defaults | overrides))
        self.assertFalse(house.model.by_type("IfcBuildingElementProxy"))

    def test_persisted_rule_excludes_only_3d_only_boxes_created_before_or_after_drawings(self):
        house = House("Boxes")
        before = house.add_box("Before", origin=(0, 0, 0), size=(1, 1, 1),
                               show_in_drawings=False)
        storey = house.storey("Ground", elevation=0)
        drawings = (
            house.add_drawing("Plan", 0, 0, 1, 4),
            house.add_drawing("Section", 0, 0, 1, 4, view="elevation", direction=(1, 0, 0)),
            house.add_drawing("Filtered", 0, 0, 1, 4, storeys=[storey]),
        )
        after = house.add_box("After", origin=(2, 0, 0), size=(1, 1, 1),
                              show_in_drawings=False)
        visible = house.add_box("Visible", origin=(4, 0, 0), size=(1, 1, 1))
        for drawing in drawings:
            query = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Exclude")
            self.assertEqual(ifcopenshell.util.selector.filter_elements(house.model, query),
                             {before, after})
        model = ifcopenshell.file.from_string(house.model.to_string())
        self.assertEqual(_remove_3d_only_elements(model), 2)
        self.assertEqual(_remove_3d_only_elements(model), 0)
        self.assertEqual(model.by_guid(visible.GlobalId).Name, "Visible")
        self.assertEqual(len(house.model.by_type("IfcBuildingElementProxy")), 3)

    def test_every_render_entry_point_uses_disposable_model_and_preserves_source(self):
        house = House("Boxes", mirror_x=True)
        ground = house.storey("Ground", elevation=0)
        wall = ground.wall((0, 0), (4, 0), thickness=0.12, height=2.8)
        hidden = house.add_box("Hidden", origin=(0, -1, 0), size=(5, 5, 3),
                               show_in_drawings=False)
        visible = house.add_box("Visible", origin=(4, 4, 0), size=(1, 1, 1))
        drawings = (
            house.add_drawing("Plan", 2, 2, 1.6, 5),
            house.add_drawing("Section", 2, 2, 1.6, 5, view="elevation", direction=(1, 0, 0),
                              doors_closed=True),
        )
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "house.ifc"
            house.write(source)
            paths = []

            def run(command, *, check):
                render_path = Path(command[command.index("--ifc") + 1])
                paths.append(render_path)
                self.assertNotEqual(render_path, source)
                rendered = ifcopenshell.open(render_path)
                self.assertEqual({e.GlobalId for e in rendered.by_type("IfcBuildingElementProxy")},
                                 {visible.GlobalId})
                self.assertTrue(rendered.by_guid(wall.GlobalId))
                self.assertEqual(len(ifcopenshell.open(source).by_type("IfcBuildingElementProxy")), 2)
                lower, upper = self.bounds(rendered.by_guid(visible.GlobalId))
                np.testing.assert_allclose(lower, (-5, 4, 0))
                np.testing.assert_allclose(upper, (-4, 5, 1))
                Path(command[command.index("--output") + 1]).write_text(
                    '<svg width="100mm" height="100mm" viewBox="0 0 100 100"></svg>',
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0)

            with (patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"),
                  patch("ifc_utils.subprocess.run", side_effect=run)):
                for drawing in drawings:
                    drawing.render(directory / f"{drawing.name}.svg")
                source_before_legacy = source.read_bytes()
                generate_plan(source, directory / "legacy.svg", x=0, y=0, z=1.6, radius=5)
                self.assertEqual(source.read_bytes(), source_before_legacy)
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(not path.exists() for path in paths))
            self.assertTrue(ifcopenshell.open(source).by_guid(hidden.GlobalId))
            self.assertEqual(len(house.model.by_type("IfcBuildingElementProxy")), 2)

    def test_temporary_model_is_cleaned_up_if_renderer_fails(self):
        house = House("Boxes")
        hidden = house.add_box("Hidden", origin=(0, 0, 0), size=(1, 1, 1),
                               show_in_drawings=False)
        drawing = house.add_drawing("Plan", 0, 0, 1, 4)
        paths = []

        def fail(command, *, check):
            paths.append(Path(command[command.index("--ifc") + 1]))
            raise subprocess.CalledProcessError(1, command)

        with TemporaryDirectory() as directory:
            directory = Path(directory)
            house.write(directory / "house.ifc")
            with (patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"),
                  patch("ifc_utils.subprocess.run", side_effect=fail)):
                with self.assertRaises(subprocess.CalledProcessError):
                    drawing.render(directory / "plan.svg")
                with self.assertRaises(subprocess.CalledProcessError):
                    generate_plan(directory / "house.ifc", directory / "legacy.svg",
                                  x=0, y=0, z=1, radius=4)
            self.assertTrue(ifcopenshell.open(directory / "house.ifc").by_guid(hidden.GlobalId))
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(not path.exists() for path in paths))


class AngleDimensionTests(unittest.TestCase):
    @staticmethod
    def world_curves(annotation):
        placement = ifcopenshell.util.placement.get_local_placement(annotation.ObjectPlacement)
        result = []
        for representation in annotation.Representation.Representations:
            for resolved in ifcopenshell.util.representation.resolve_items(representation):
                item = resolved["item"]
                curves = item.Elements if item.is_a("IfcGeometricCurveSet") else (item,)
                for curve in curves:
                    if curve.is_a("IfcIndexedPolyCurve"):
                        coordinates = curve.Points.CoordList
                    else:
                        coordinates = [p.Coordinates for p in curve.Points]
                    result.append(np.asarray([
                        (placement @ resolved["matrix"] @ np.array((*p[:2], 0, 1)))[:3]
                        for p in coordinates
                    ]))
        return result

    def test_native_angle_and_reference_geometry_in_plans_and_all_axis_aligned_elevations(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Angles", mirror_x=mirror)
                    house.storey("Floor", elevation=0.25)
                    drawing = house.add_drawing("View", x=1, y=1.5, z=4, radius=5,
                                                view=view, direction=direction)
                    angle = drawing.add_angle(vertex=(2, 3), start=(4, 3), end=(3, 4), radius=0.65)
                    self.assertEqual(angle.ObjectType, "ANGLE")
                    properties = ifcopenshell.util.element.get_pset(angle, "BBIM_AngleDimension")
                    self.assertAlmostEqual(properties["AngleDegrees"], 45)
                    self.assertEqual(json.loads(properties["Vertex"]), [2, 3])
                    self.assertEqual(properties["Radius"], 0.65)
                    points = self.world_curves(angle)[0]
                    if view == "plan":
                        centre = (2, 3, 0.25)
                        first = (2.65, 3, 0.25)
                    elif direction[0]:
                        centre = (1, 2, 3)
                        first = (1, 2.65, 3)
                    else:
                        centre = (2, 1.5, 3)
                        first = (2.65, 1.5, 3)
                    np.testing.assert_allclose(points[1], centre)
                    np.testing.assert_allclose(points[0], first)
                    for point in (points[0], points[2]):
                        self.assertAlmostEqual(np.linalg.norm(point - points[1]), 0.65)
                    annotations = drawing.group.IsGroupedBy[0].RelatedObjects
                    references = next(a for a in annotations if (a.Name or "").endswith("Reference Lines"))
                    for line in self.world_curves(references):
                        np.testing.assert_allclose(line[0], centre)
                        self.assertAlmostEqual(np.linalg.norm(line[1] - line[0]), 0.75)
                    exported = house._export_model()
                    mirrored_points = self.world_curves(exported.by_guid(angle.GlobalId))[0]
                    expected = points * np.array((-1 if mirror else 1, 1, 1))
                    np.testing.assert_allclose(mirrored_points, expected)
                    a, b = mirrored_points[0] - mirrored_points[1], mirrored_points[2] - mirrored_points[1]
                    measured = np.degrees(np.arccos(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))
                    self.assertAlmostEqual(measured, 45)

    def test_angles_are_drawing_scoped_and_preserve_explicit_decimal_setting(self):
        house = House("Angles")
        first = house.add_drawing("First", 0, 0, 2, 4)
        other = house.add_drawing("Other", 0, 0, 2, 4)
        angle = first.add_angle((0, 0), (1, 0), (1, -1), name="Roof pitch")
        self.assertEqual(angle.Name, "Roof pitch")
        self.assertEqual(len([a for a in first.group.IsGroupedBy[0].RelatedObjects
                              if a.ObjectType != "DRAWING"]), 2)
        self.assertNotIn(angle, other.group.IsGroupedBy[0].RelatedObjects)
        self.assertEqual(ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing", "AngleDecimalPlaces"), 0)
        pset = ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing")
        ifcopenshell.api.pset.edit_pset(house.model, pset=house.model.by_id(pset["id"]),
                                       properties={"AngleDecimalPlaces": 1})
        first.add_angle((0, 0), (1, 0), (1, 1))
        self.assertEqual(ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing", "AngleDecimalPlaces"), 1)
        self.assertTrue(ifcopenshell.util.element.get_pset(first.element, "EPset_Drawing", "HasAnnotation"))

    def test_whole_degree_labels_drop_float_suffix_only_for_angles(self):
        svg = '''<svg xmlns="http://www.w3.org/2000/svg">
<text class="ANGLE" x="1" y="2">36.0°</text>
<text class="fine ANGLE">15.0°</text>
<text><tspan class='ANGLE'>90.0°</tspan></text>
<text class="DIMENSION">36.0</text>
<text class="NOTE">36.0°</text>
<text class="NOT-ANGLE">15.0°</text>
<text class="ANGLE">15.5°</text>
</svg>'''
        with TemporaryDirectory() as directory:
            path = Path(directory) / "angles.svg"
            path.write_text(svg, encoding="utf-8")
            _postprocess_angle_labels(path, {"AngleDecimalPlaces": 0})
            expected = svg.replace('>36.0°</text>', '>36°</text>', 1)
            expected = expected.replace('>15.0°</text>', '>15°</text>', 1)
            expected = expected.replace('>90.0°</tspan>', '>90°</tspan>')
            self.assertEqual(path.read_text(encoding="utf-8"), expected)
            _postprocess_angle_labels(path, {"AngleDecimalPlaces": 0})
            self.assertEqual(path.read_text(encoding="utf-8"), expected)
            ET.fromstring(expected)

    def test_angle_labels_preserve_explicit_decimal_precision_and_unspecified_settings(self):
        svg = '<svg><text class="ANGLE">36.0°</text></svg>'
        with TemporaryDirectory() as directory:
            path = Path(directory) / "angles.svg"
            path.write_text(svg, encoding="utf-8")
            for properties in ({}, {"AngleDecimalPlaces": 1}, {"AngleDecimalPlaces": 2}):
                with self.subTest(properties=properties):
                    _postprocess_angle_labels(path, properties)
                    self.assertEqual(path.read_text(encoding="utf-8"), svg)

    def test_invalid_angles_leave_no_partial_annotations(self):
        house = House("Angles")
        drawing = house.add_drawing("View", 0, 0, 2, 4)
        arguments = dict(vertex=(0, 0), start=(1, 0), end=(1, 1))
        before = len(house.model.by_type("IfcAnnotation"))
        invalid = (
            ({"start": (0, 0)}, ValueError), ({"end": (0, 0)}, ValueError),
            ({"end": (2, 0)}, ValueError), ({"end": (-1, 0)}, ValueError),
            ({"vertex": (0, 0, 0)}, TypeError), ({"start": (float("nan"), 0)}, ValueError),
            ({"radius": 0}, ValueError), ({"radius": -1}, ValueError),
            ({"radius": True}, TypeError), ({"radius": "not-a-number"}, TypeError),
            ({"name": ""}, ValueError),
        )
        for overrides, error in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(error):
                drawing.add_angle(**(arguments | overrides))
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)
        diagonal = house.add_drawing("Diagonal", 0, 0, 2, 4, view="elevation", direction=(1, 1, 0))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            diagonal.add_angle(**arguments)


class DrawingPdfTests(unittest.TestCase):
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="235mm" height="170mm" '
           'viewBox="0 0 235 170" data-scale="1:100">'
           '<defs><pattern id="hatch" width="2" height="2" patternUnits="userSpaceOnUse">'
           '<path d="M0 0 L2 2"/></pattern></defs>'
           '<rect x="10" y="20" width="100" height="50" fill="url(#hatch)"/>'
           '<text class="ANGLE">36.0°</text></svg>')

    def test_defaults_and_alternative_papers(self):
        path, width, height, margin = _drawing_pdf_options(Path("roof.pdf"), "A4", "landscape", 10)
        self.assertEqual(path, Path("roof.pdf").resolve())
        self.assertEqual((width, height, margin), (297, 210, 10))
        for paper, size in (("A4", (210, 297)), ("A3", (297, 420)),
                            ("A2", (420, 594)), ("A1", (594, 841)), ("A0", (841, 1189))):
            self.assertEqual(_drawing_pdf_options(None, paper, "portrait", 0), (None, *size, 0))

    def test_sheet_centres_drawing_without_scaling_or_changing_geometry(self):
        sheet = _drawing_pdf_sheet(self.SVG, width=297, height=210, margin=10)
        root = ET.fromstring(sheet)
        self.assertEqual((root.get("width"), root.get("height")), ("297mm", "210mm"))
        self.assertEqual(root.get("viewBox"), "0 0 297 210")
        inner = root.find("{http://www.w3.org/2000/svg}svg")
        self.assertEqual((inner.get("width"), inner.get("height")), ("235", "170"))
        self.assertEqual((inner.get("x"), inner.get("y")), ("31", "20"))
        self.assertEqual(inner.get("viewBox"), "0 0 235 170")
        self.assertEqual(inner.get("data-scale"), "1:100")
        self.assertIn(self.SVG.split(">", 1)[1], sheet)
        with self.assertRaisesRegex(ValueError, "does not fit"):
            _drawing_pdf_sheet(self.SVG, width=210, height=297, margin=10)

    def test_invalid_options_are_rejected_before_persisting_or_launching_renderer(self):
        house = House("PDF options")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        with TemporaryDirectory() as directory:
            house.write(Path(directory) / "house.ifc")
            invalid = (({"pdf": True}, TypeError), ({"pdf": False}, TypeError),
                       ({"pdf": "roof.png"}, ValueError), ({"paper": "A5"}, ValueError),
                       ({"orientation": "diagonal"}, ValueError), ({"margin": -1}, ValueError),
                       ({"margin": 105}, ValueError), ({"margin": float("nan")}, ValueError),
                       ({"margin": True}, TypeError), ({"title": True}, TypeError),
                       ({"title": "   "}, ValueError))
            with patch.object(house, "_write_model") as write, patch("ifc_utils.subprocess.run") as run:
                for options, error in invalid:
                    with self.subTest(options=options), self.assertRaises(error):
                        drawing.render(Path(directory) / "plan.svg", **options)
                write.assert_not_called()
                run.assert_not_called()

    def test_sheet_preserves_non_mm_viewbox_units_and_handles_xml_declaration(self):
        svg = '<?xml version="1.0"?>' + self.SVG.replace('viewBox="0 0 235 170"',
                                                                     'viewBox="10 20 470 340"')
        root = ET.fromstring(_drawing_pdf_sheet(svg, width=297, height=420, margin=20))
        inner = root.find("{http://www.w3.org/2000/svg}svg")
        self.assertEqual(inner.get("viewBox"), "10 20 470 340")
        self.assertEqual((inner.get("width"), inner.get("height")), ("235", "170"))
        self.assertEqual((inner.get("x"), inner.get("y")), ("31", "125"))

    def test_svg_physical_dimensions_are_required_for_scale_preserving_export(self):
        for svg in ("<html/>", self.SVG.replace('width="235mm"', 'width="235px"'),
                    self.SVG.replace('height="170mm"', 'height="0mm"'),
                    self.SVG.replace('viewBox="0 0 235 170"', '')):
            with self.subTest(svg=svg), self.assertRaises(ValueError):
                _drawing_pdf_sheet(svg, width=297, height=210, margin=10)

    def test_pdf_is_exported_after_postprocessing_and_before_returning(self):
        house = House("PDF render")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        drawing.add_angle((0, 0), (1, 0), (1, 1))
        commands, temporary_paths = [], []
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            house.write(directory / "house.ifc")
            svg_path, pdf_path = directory / "roof.svg", directory / "reports" / "D1.1.5. Krov.pdf"

            def run(command, *, check):
                self.assertTrue(check)
                commands.append(command)
                if "--output" in command:
                    Path(command[command.index("--output") + 1]).write_text(self.SVG, encoding="utf-8")
                elif "--export-type=pdf" in command:
                    temporary_svg = Path(command[1])
                    temporary_pdf = Path(next(a.split("=", 1)[1] for a in command
                                              if a.startswith("--export-filename=")))
                    temporary_paths.extend((temporary_svg, temporary_pdf))
                    root = ET.parse(temporary_svg).getroot()
                    self.assertEqual(root.get("width"), "297mm")
                    self.assertEqual(root.get("height"), "210mm")
                    self.assertIn(">36°</text>", temporary_svg.read_text(encoding="utf-8"))
                    self.assertIn(">D1.1.5. Krov 1:100</text>", temporary_svg.read_text(encoding="utf-8"))
                    self.assertEqual(temporary_svg.parent, svg_path.parent)
                    self.assertIn("--export-type=pdf", command)
                    self.assertNotIn("--export-text-to-path", command)
                    temporary_pdf.write_bytes(b"%PDF-test")
                else:
                    root = ET.parse(command[1]).getroot()
                    self.assertEqual(root.get("width"), "235mm")
                    temporary_png = Path(next(a.split("=", 1)[1] for a in command
                                              if a.startswith("--export-filename=")))
                    temporary_paths.append(temporary_png)
                    temporary_png.write_bytes(b"PNG-test")
                return subprocess.CompletedProcess(command, 0)

            with patch("ifc_utils.shutil.which", return_value="/usr/bin/tool"), \
                    patch("ifc_utils.subprocess.run", side_effect=run):
                self.assertEqual(drawing.render(svg_path, png=True, pdf=pdf_path), svg_path)
            self.assertEqual(len(commands), 3)
            self.assertEqual(pdf_path.read_bytes(), b"%PDF-test")
            self.assertEqual(svg_path.with_suffix(".png").read_bytes(), b"PNG-test")
            svg = ET.parse(svg_path).getroot()
            self.assertEqual((svg.get("width"), svg.get("height")), ("235mm", "180mm"))
            self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_oversized_drawing_preserves_previous_pdf_without_launching_exporter(self):
        with TemporaryDirectory() as directory:
            svg, pdf = Path(directory) / "roof.svg", Path(directory) / "roof.pdf"
            svg.write_text(self.SVG, encoding="utf-8")
            pdf.write_bytes(b"previous PDF")
            with patch("ifc_utils.subprocess.run") as run:
                with self.assertRaisesRegex(ValueError, "does not fit"):
                    _export_drawing_pdf(svg, pdf, orientation="portrait")
                run.assert_not_called()
            self.assertEqual(pdf.read_bytes(), b"previous PDF")

    def test_failed_or_empty_exports_preserve_previous_pdf_and_clean_temporary_files(self):
        with TemporaryDirectory() as directory:
            svg, pdf = Path(directory) / "roof.svg", Path(directory) / "roof.pdf"
            svg.write_text(self.SVG, encoding="utf-8")
            pdf.write_bytes(b"previous PDF")
            for failure in (subprocess.CalledProcessError(1, "inkscape"), None):
                with self.subTest(failure=failure), \
                        patch("ifc_utils.shutil.which", return_value="/usr/bin/inkscape"), \
                        patch("ifc_utils.subprocess.run", side_effect=failure):
                    error = subprocess.CalledProcessError if failure else RuntimeError
                    with self.assertRaises(error):
                        _export_drawing_pdf(svg, pdf)
                self.assertEqual(pdf.read_bytes(), b"previous PDF")
                self.assertEqual(set(Path(directory).iterdir()), {svg, pdf})


class DrawingTitleTests(unittest.TestCase):
    def test_title_has_compact_header_and_escapes_text_without_resizing_geometry(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roof.svg"
            path.write_text(DrawingPdfTests.SVG, encoding="utf-8")
            _postprocess_drawing_title(path, "Krov – řez <AA> & BB")
            svg = path.read_text(encoding="utf-8")
            root = ET.fromstring(svg)
            self.assertEqual((root.get("width"), root.get("height")), ("235mm", "180mm"))
            self.assertEqual(root.get("viewBox"), "0 0 235 180")
            title = root.find("{http://www.w3.org/2000/svg}text")
            self.assertEqual(title.text, "Krov – řez <AA> & BB")
            self.assertEqual((title.get("x"), title.get("y")), ("117.5", "6.5"))
            self.assertIn("font-size: 4px", title.get("style"))
            content = root.find("{http://www.w3.org/2000/svg}g")
            self.assertEqual(content.get("transform"), "translate(0, 10)")
            self.assertNotIn("scale", content.get("transform"))
            source = ET.fromstring(DrawingPdfTests.SVG)
            self.assertEqual([ET.tostring(c) for c in content], [ET.tostring(c) for c in source])
            _postprocess_drawing_title(path, "Krov – řez <AA> & BB")
            self.assertEqual(path.read_text(encoding="utf-8"), svg)

    def test_title_handles_nonzero_viewbox_and_different_units_per_mm(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roof.svg"
            path.write_text(DrawingPdfTests.SVG.replace('viewBox="0 0 235 170"',
                                                        'viewBox="10 20 470 340"'), encoding="utf-8")
            _postprocess_drawing_title(path, "Roof")
            root = ET.parse(path).getroot()
            self.assertEqual(root.get("viewBox"), "10 20 470 360")
            title = root.find("{http://www.w3.org/2000/svg}text")
            self.assertEqual((title.get("x"), title.get("y")), ("245", "33"))
            self.assertIn("font-size: 8px", title.get("style"))
            self.assertEqual(root.find("{http://www.w3.org/2000/svg}g").get("transform"),
                             "translate(0, 20)")

    def test_render_uses_pdf_stem_svg_stem_or_explicit_title_in_all_outputs(self):
        house = House("Titles")
        drawing = house.add_drawing("Different IFC name", 0, 0, 2, 4)
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            house.write(directory / "house.ifc")
            svg = directory / "source.svg"
            pdf = directory / "reports" / "D1.1.6. Krov – řez XX.pdf"

            def render(command, *, check):
                Path(command[command.index("--output") + 1]).write_text(DrawingPdfTests.SVG, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                    patch("ifc_utils.subprocess.run", side_effect=render), \
                    patch("ifc_utils._export_drawing_pdf") as export:
                for options, expected in (({}, "source 1:100"), ({"pdf": pdf}, f"{pdf.stem} 1:100"),
                                          ({"pdf": pdf, "title": "Příčný řez"}, "Příčný řez 1:100"),
                                          ({"title": "Custom SVG title"}, "Custom SVG title 1:100"),
                                          ({"title": "Roof 1:100"}, "Roof 1:100")):
                    with self.subTest(options=options):
                        export.reset_mock()
                        drawing.render(svg, **options)
                        root = ET.parse(svg).getroot()
                        self.assertEqual(root.find("{http://www.w3.org/2000/svg}text").text, expected)
                        self.assertEqual(root.get("height"), "180mm")
                        if "pdf" in options:
                            export.assert_called_once()
                        else:
                            export.assert_not_called()

    def test_title_uses_actual_scale_and_handles_legacy_scale_metadata(self):
        house = House("Scale titles")
        drawing = house.add_drawing("Roof", 0, 0, 2, 4)
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            house.write(directory / "house.ifc")
            svg = directory / "roof.svg"

            def render(command, *, check):
                Path(command[command.index("--output") + 1]).write_text(DrawingPdfTests.SVG, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                    patch("ifc_utils.subprocess.run", side_effect=render):
                for scale, human_scale, expected in (("1/50", "1:100", "Roof 1:50"),
                                                      ("2/100", "1:50", "Roof 1:50"),
                                                      (None, "1:75", "Roof 1:75"),
                                                      (None, None, "Roof")):
                    with self.subTest(scale=scale, human_scale=human_scale):
                        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset,
                                                        properties={"Scale": scale, "HumanScale": human_scale})
                        drawing.render(svg, title="Roof")
                        root = ET.parse(svg).getroot()
                        self.assertEqual(root.find("{http://www.w3.org/2000/svg}text").text, expected)

    def test_title_height_is_included_in_pdf_fit_check(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roof.svg"
            svg = DrawingPdfTests.SVG.replace('height="170mm"', 'height="185mm"').replace(
                'viewBox="0 0 235 170"', 'viewBox="0 0 235 185"')
            path.write_text(svg, encoding="utf-8")
            _drawing_pdf_sheet(svg, width=297, height=210, margin=10)
            _postprocess_drawing_title(path, "Roof")
            with self.assertRaisesRegex(ValueError, "does not fit"):
                _drawing_pdf_sheet(path.read_text(encoding="utf-8"), width=297, height=210, margin=10)


class DrawingPrimitiveTests(unittest.TestCase):
    def test_circle_export_uses_exact_parameters_and_only_current_drawing(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1,0,0)),
                                    ("elevation", (-1,0,0)), ("elevation", (0,1,0)),
                                    ("elevation", (0,-1,0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Exact circles", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction)
                    circle = drawing.add_circle((2,3), 0.5)
                    other = house.add_drawing("Other", 1, 1.5, 4, 5, view=view, direction=direction)
                    other.add_circle((20,30), 5)
                    model = house._export_model()
                    svg = ('<svg width="100mm" height="100mm" viewBox="0 0 100 100">'
                           '<line class="drawing-line drawing-circle-1" x1="1" y1="2" x2="2" y2="3"/>'
                           '<line class="drawing-line drawing-circle-1" x1="2" y1="3" x2="3" y2="4"/>'
                           '<line class="unrelated" x1="5" y1="6" x2="7" y2="8"/></svg>')
                    with TemporaryDirectory() as directory:
                        path = Path(directory) / "circles.svg"
                        path.write_text(svg, encoding="utf-8")
                        _postprocess_drawing_circles(path, model, model.by_guid(drawing.element.GlobalId))
                        result = path.read_text(encoding="utf-8")
                        root = ET.fromstring(result)
                        circles = list(root.iter("circle"))
                        self.assertEqual(len(circles), 1)
                        self.assertEqual(float(circles[0].get("r")), 5)
                        camera = ifcopenshell.util.placement.get_local_placement(model.by_guid(drawing.element.GlobalId).ObjectPlacement)
                        position = ifcopenshell.util.placement.get_local_placement(model.by_guid(circle.GlobalId).ObjectPlacement)
                        local = np.linalg.inv(camera) @ position[:,3]
                        self.assertAlmostEqual(float(circles[0].get("cx")), 50 + local[0]*10)
                        self.assertAlmostEqual(float(circles[0].get("cy")), 50 - local[1]*10)
                        self.assertIn('class="unrelated"', result)
                        _postprocess_drawing_circles(path, model, model.by_guid(drawing.element.GlobalId))
                        self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_circle_rectangle_and_text_positions_in_all_views_and_export_mirroring(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Primitives", mirror_x=mirror)
                    house.storey("Floor", elevation=0.25)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction)
                    other = house.add_drawing("Other", 1, 1.5, 4, 5)
                    circle = drawing.add_circle((2, 3), 0.5, color="blue")
                    rectangle = drawing.add_rectangle((4, 5), (2, 3), style="dashed")
                    text = drawing.add_text((2, 3), "ČOV", font_size=3.25, color="red")
                    for item in (circle, rectangle, text):
                        self.assertIn(item, drawing.group.IsGroupedBy[0].RelatedObjects)
                        self.assertNotIn(item, other.group.IsGroupedBy[0].RelatedObjects)
                    literal = text.Representation.Representations[0].Items[0]
                    self.assertEqual((literal.Literal, literal.BoxAlignment), ("ČOV", "center"))
                    self.assertEqual(circle.Representation.Representations[0].Items[0].Elements[0].Radius, 0.5)
                    if view == "plan":
                        centre = np.array((2, 3, 0.25))
                        corners = np.array([(2,3,.25), (4,3,.25), (4,5,.25), (2,5,.25), (2,3,.25)])
                    elif direction[0]:
                        centre = np.array((1, 2, 3))
                        corners = np.array([(1,2,3), (1,4,3), (1,4,5), (1,2,5), (1,2,3)])
                    else:
                        centre = np.array((2, 1.5, 3))
                        corners = np.array([(2,1.5,3), (4,1.5,3), (4,1.5,5), (2,1.5,5), (2,1.5,3)])
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(rectangle)[0], corners)
                    for item in (circle, text):
                        placement = ifcopenshell.util.placement.get_local_placement(item.ObjectPlacement)
                        np.testing.assert_allclose(placement[:3, 3], centre)
                    exported = house._export_model()
                    reflection = np.array((-1 if mirror else 1, 1, 1))
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(exported.by_guid(rectangle.GlobalId))[0], corners * reflection)
                    for item in (circle, text):
                        placement = ifcopenshell.util.placement.get_local_placement(exported.by_guid(item.GlobalId).ObjectPlacement)
                        np.testing.assert_allclose(placement[:3, 3], centre * reflection)
                    props = ifcopenshell.util.element.get_pset(exported.by_guid(text.GlobalId), "BBIM_DrawingText")
                    self.assertEqual((props["Text"], props["FontSize"], props["Color"]), ("ČOV", 3.25, "#ff0000"))

    def test_text_alignment_and_styles_are_configurable(self):
        house = House("Primitives")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        for alignment, box in (("center", "center"), ("left", "middle-left"), ("right", "middle-right")):
            text = drawing.add_text((1, 2), "Žluťoučký text", alignment=alignment)
            self.assertEqual(text.Representation.Representations[0].Items[0].BoxAlignment, box)
            props = ifcopenshell.util.element.get_pset(text, "BBIM_DrawingText")
            self.assertEqual((props["FontSize"], props["Color"]), (3, "#000000"))
        circle = drawing.add_circle((1, 2), 0.5, style="dashed", color="#aBc", name="Tank")
        self.assertEqual(circle.Name, "Tank")
        props = ifcopenshell.util.element.get_pset(circle, "BBIM_DrawingCircle")
        self.assertEqual((props["Style"], props["Color"]), ("dashed", "#aabbcc"))

    def test_invalid_primitives_leave_no_partial_annotations(self):
        house = House("Primitives")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        invalid = (
            (lambda: drawing.add_circle((0,0), 0), ValueError),
            (lambda: drawing.add_circle((0,0), -1), ValueError),
            (lambda: drawing.add_circle((0,0), True), TypeError),
            (lambda: drawing.add_circle((0,0), float("inf")), ValueError),
            (lambda: drawing.add_circle((0,0), 1, style="dashed-arrows"), ValueError),
            (lambda: drawing.add_rectangle((0,0), (0,1)), ValueError),
            (lambda: drawing.add_rectangle((0,0), (1,0)), ValueError),
            (lambda: drawing.add_rectangle((0,0,0), (1,1)), TypeError),
            (lambda: drawing.add_text((0,0), " "), ValueError),
            (lambda: drawing.add_text((0,0), "Text", font_size=0), ValueError),
            (lambda: drawing.add_text((0,0), "Text", font_size=True), TypeError),
            (lambda: drawing.add_text((0,0), "Text", alignment="unknown"), ValueError),
            (lambda: drawing.add_text((0,0), "Text", color="bad-color"), ValueError),
        )
        before = len(house.model.by_type("IfcAnnotation"))
        for call, error in invalid:
            with self.assertRaises(error):
                call()
            self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)
        diagonal = house.add_drawing("Diagonal", 0, 0, 2, 4, view="elevation", direction=(1,1,0))
        before = len(house.model.by_type("IfcAnnotation"))
        for call in (lambda: diagonal.add_circle((0,0), 1),
                     lambda: diagonal.add_rectangle((0,0), (1,1)), lambda: diagonal.add_text((0,0), "Text")):
            with self.assertRaisesRegex(ValueError, "axis-aligned"):
                call()
            self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)

    def test_text_color_and_paper_font_size_css_are_defined_before_geometry(self):
        svg = ('<svg width="100mm" height="100mm" viewBox="0 0 200 200">'
               '<text class="drawing-text drawing-text-size-3p25 drawing-text-color-ff0000">'
               '<tspan>ČOV</tspan></text></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "text.svg"
            path.write_text(svg, encoding="utf-8")
            _postprocess_drawing_line_colors(path)
            result = path.read_text(encoding="utf-8")
            self.assertIn(".drawing-text-color-ff0000 tspan", result)
            self.assertIn("fill: #ff0000 !important", result)
            self.assertIn(".drawing-text-size-3p25 tspan", result)
            self.assertIn("font-size: 6.5px !important", result)
            self.assertLess(result.index('<style'), result.index('<text'))
            _postprocess_drawing_line_colors(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)


class SanitarySymbolTests(unittest.TestCase):
    def test_roof_vent_is_upward_triangle_with_identifier_in_all_views(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Roof vent", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 2, 3, 5, view=view, direction=direction, storeys=[])
                    other = house.add_drawing("Other", 1, 2, 3, 5, storeys=[])
                    before = set(house.model.by_type("IfcAnnotation"))
                    symbol = drawing.add_roof_vent(x=2, z=6)
                    label = self.assert_symbol_annotations(house, before, symbol)
                    self.assertIn(label, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(label, other.group.IsGroupedBy[0].RelatedObjects)
                    corners = ((1.8, 6), (2.2, 6), (2, 6.2), (1.8, 6))
                    if view == "plan":
                        expected = np.array([(x, z, 0) for x, z in corners])
                    elif direction[0]:
                        expected = np.array([(1, x, z) for x, z in corners])
                    else:
                        expected = np.array([(x, 2, z) for x, z in corners])
                    curves = AngleDimensionTests.world_curves(symbol)
                    self.assertEqual(len(curves), 1)
                    np.testing.assert_allclose(curves[0], expected)
                    props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
                    self.assertEqual((props["Kind"], props["Identifier"], props["OutletLength"]), ("roof_vent", "Odvětrání", 0))
                    exported = house._export_model()
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(exported.by_guid(symbol.GlobalId))[0],
                                               expected * (-1 if mirror else 1, 1, 1))
                    self.assertFalse(house.model.by_type("IfcPipeSegment"))
                    before = set(house.model.by_type("IfcAnnotation"))
                    for kwargs in ({"width": 0}, {"height": -1}, {"height": float("inf")},
                                   {"width": True}, {"color": "bad-color"}):
                        with self.assertRaises((ValueError, TypeError)):
                            drawing.add_roof_vent(2, 6, **kwargs)
                        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)

    def test_washing_machine_connector_has_box_and_socket_not_an_appliance(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Connector", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 2, 3, 5, view=view, direction=direction, storeys=[])
                    other = house.add_drawing("Other", 1, 2, 3, 5, storeys=[])
                    before = set(house.model.by_type("IfcAnnotation"))
                    symbol = drawing.add_washing_machine_connection(x=2, z=.6)
                    label = self.assert_symbol_annotations(house, before, symbol)
                    self.assertIn(symbol, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertIn(label, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                    curves = AngleDimensionTests.world_curves(symbol)
                    self.assertEqual([len(c) for c in curves], [5, 33])
                    # Compare in diagram coordinates, independently of the view's
                    # horizontal axis direction. Both paths must be closed.
                    def diagram(curve):
                        if view == "plan":
                            return curve[:, :2]
                        if direction[0]:
                            return curve[:, 1:]
                        return curve[:, (0, 2)]
                    box, circle = map(diagram, curves)
                    np.testing.assert_allclose(np.min(box, axis=0), (1.92, .6))
                    np.testing.assert_allclose(np.max(box, axis=0), (2.08, .84))
                    np.testing.assert_allclose(box[0], box[-1])
                    np.testing.assert_allclose(circle[0], circle[-1])
                    np.testing.assert_allclose(np.linalg.norm(circle - (2, .76), axis=1), .16 / 6)
                    props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
                    self.assertEqual((props["Kind"], props["Identifier"], props["OutletLength"]),
                                     ("washing_machine_connection", "Pračka", 0))
                    exported = house._export_model()
                    for curve, reflected in zip(curves, AngleDimensionTests.world_curves(exported.by_guid(symbol.GlobalId))):
                        np.testing.assert_allclose(reflected, curve * (-1 if mirror else 1, 1, 1))
                    self.assertFalse(house.model.by_type("IfcSanitaryTerminal"))
                    self.assertFalse(house.model.by_type("IfcPipeSegment"))

    def test_washing_machine_connector_custom_size_color_and_invalid_inputs(self):
        house = House("Connector")
        drawing = house.add_drawing("kanal", 0, 0, 1, 5, storeys=[])
        symbol = drawing.add_washing_machine_connection(1, .5, width=.2, height=.3,
                                                       identifier="P1", color="orange", name="Waste outlet")
        self.assertEqual(symbol.Name, "Waste outlet")
        props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
        self.assertEqual((props["Identifier"], props["Color"], props["Width"], props["Height"]),
                         ("P1", "#ffa500", .2, .3))
        label = house.model.by_guid(props["IdentifierAnnotation"])
        np.testing.assert_allclose(json.loads(ifcopenshell.util.element.get_pset(label, "BBIM_DrawingText", "Point")), (1, 1.1))
        before = set(house.model.by_type("IfcAnnotation"))
        for kwargs in ({"width": 0}, {"height": -1}, {"width": float("inf")}, {"height": True},
                       {"x": float("nan")}, {"z": None}, {"identifier": " "},
                       {"color": "bad-color"}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                drawing.add_washing_machine_connection(**({"x": 1, "z": .5} | kwargs))
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        oblique = house.add_drawing("Oblique", 0, 0, 1, 5, view="elevation", direction=(1, 1, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            oblique.add_washing_machine_connection(1, .5)
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)

    def assert_symbol_annotations(self, house, before, symbol):
        props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
        label = house.model.by_guid(props["IdentifierAnnotation"])
        self.assertEqual(set(house.model.by_type("IfcAnnotation")) - before, {symbol, label})
        self.assertEqual(label.ObjectType, "TEXT")
        self.assertEqual(label.Representation.Representations[0].Items[0].Literal, props["Identifier"])
        return label

    def test_identifiers_default_by_type_are_centred_above_actual_top_at_any_scale(self):
        for mirror in (False, True):
            for scale, factor in (("1/100", .01), ("1/50", .02)):
                for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                        ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                        ("elevation", (0, -1, 0))):
                    with self.subTest(mirror=mirror, scale=scale, direction=direction):
                        house = House("Identifiers", mirror_x=mirror)
                        drawing = house.add_drawing("View", 1, 2, 3, 5, view=view, direction=direction, storeys=[])
                        other = house.add_drawing("Other", 1, 2, 3, 5, storeys=[])
                        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": scale})
                        for method, default in ((drawing.add_basin, "Umyvadlo"), (drawing.add_sink, "Dřez"),
                                                (drawing.add_toilet, "WC"), (drawing.add_shower, "Sprcha"),
                                                (drawing.add_washing_machine_connection, "Pračka"),
                                                (drawing.add_roof_vent, "Odvětrání")):
                            before = set(house.model.by_type("IfcAnnotation"))
                            symbol = method(2, 4, width=.8, height=.3, color="orange", name="Internal name")
                            label = self.assert_symbol_annotations(house, before, symbol)
                            props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
                            self.assertEqual(props["Identifier"], default)
                            self.assertEqual(symbol.Name, "Internal name")
                            self.assertIn(label, drawing.group.IsGroupedBy[0].RelatedObjects)
                            self.assertNotIn(label, other.group.IsGroupedBy[0].RelatedObjects)
                            text = ifcopenshell.util.element.get_pset(label, "BBIM_DrawingText")
                            expected_x = 1.6 if method == drawing.add_shower else 2
                            expected_z = 4.3 + props.get("RimThickness", 0) + .003 / factor
                            np.testing.assert_allclose(json.loads(text["Point"]), (expected_x, expected_z))
                            self.assertEqual((text["Color"], text["FontSize"], text["Alignment"]), ("#ffa500", 2.5, "center"))
                            self.assertEqual(ifcopenshell.util.element.get_pset(label, "BBIM_SanitaryIdentifier", "Symbol"), symbol.GlobalId)
                            exported = house._export_model()
                            original = ifcopenshell.util.placement.get_local_placement(label.ObjectPlacement)[:3, 3]
                            position = ifcopenshell.util.placement.get_local_placement(exported.by_guid(label.GlobalId).ObjectPlacement)[:3, 3]
                            np.testing.assert_allclose(position, original * (-1 if mirror else 1, 1, 1))
                            self.assertEqual(ifcopenshell.util.element.get_pset(exported.by_guid(symbol.GlobalId), "BBIM_SanitarySymbol", "Identifier"), default)

    def test_custom_identifiers_and_invalid_identifiers_are_validated_before_geometry(self):
        house = House("Identifiers")
        drawing = house.add_drawing("kanal", 0, 0, 1, 5, storeys=[])
        for method in (drawing.add_basin, drawing.add_sink, drawing.add_toilet, drawing.add_shower,
                       drawing.add_washing_machine_connection, drawing.add_roof_vent):
            symbol = method(2, 3, identifier="  U1 – přízemí  ")
            props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
            self.assertEqual(props["Identifier"], "U1 – přízemí")
            for identifier in ("", "  ", True, 123):
                before = set(house.model.by_type("IfcAnnotation"))
                with self.subTest(method=method.__name__, identifier=identifier), self.assertRaises((ValueError, TypeError)):
                    method(2, 3, identifier=identifier)
                self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
            for scale in ("0", "1/0", "invalid"):
                ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": scale})
                before = set(house.model.by_type("IfcAnnotation"))
                with self.assertRaisesRegex(ValueError, "positive drawing scale"):
                    method(2, 3)
                self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
            ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": "1/100"})

    def test_shower_is_one_rectangle_anchored_at_bottom_left_in_all_views(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Shower", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 2, 3, 5, view=view, direction=direction, storeys=[])
                    other = house.add_drawing("Other", 1, 2, 3, 5, storeys=[])
                    before = set(house.model.by_type("IfcAnnotation"))
                    shower = drawing.add_shower(x=2, z=4)
                    self.assert_symbol_annotations(house, before, shower)
                    self.assertIn(shower, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(shower, other.group.IsGroupedBy[0].RelatedObjects)
                    self.assertEqual(shower.ObjectType, "LINEWORK")
                    corners = ((1.1, 4), (2, 4), (2, 4.3), (1.1, 4.3), (1.1, 4))
                    if view == "plan":
                        expected = np.array([(x, z, 0) for x, z in corners])
                    elif direction[0]:
                        expected = np.array([(1, x, z) for x, z in corners])
                    else:
                        expected = np.array([(x, 2, z) for x, z in corners])
                    curves = AngleDimensionTests.world_curves(shower)
                    self.assertEqual(len(curves), 1)
                    np.testing.assert_allclose(curves[0], expected)
                    props = ifcopenshell.util.element.get_pset(shower, "BBIM_SanitarySymbol")
                    self.assertEqual((props["Kind"], props["X"], props["BottomZ"], props["Width"], props["Height"],
                                      props["PositionReference"], props["OutletLength"], props["Color"]),
                                     ("shower", 2, 4, .9, .3, "bottom-left", 0, "#000000"))
                    exported = house._export_model().by_guid(shower.GlobalId)
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(exported)[0], expected * (-1 if mirror else 1, 1, 1))
                    self.assertIn("sanitary-shower", ifcopenshell.util.element.get_pset(exported, "EPset_Annotation", "Classes"))
                    self.assertFalse(house.model.by_type("IfcSanitaryTerminal"))

    def test_shower_custom_size_and_invalid_inputs_leave_no_partial_geometry(self):
        house = House("Shower")
        drawing = house.add_drawing("kanal", 0, 0, 1, 5, storeys=[])
        shower = drawing.add_shower(1, .2, width=1.2, height=.4, color="orange", name="Sprcha")
        self.assertEqual(shower.Name, "Sprcha")
        points = AngleDimensionTests.world_curves(shower)[0]
        np.testing.assert_allclose(np.min(points[:, :2], axis=0), (-.2, .2))
        np.testing.assert_allclose(np.max(points[:, :2], axis=0), (1, .6))
        self.assertEqual(ifcopenshell.util.element.get_pset(shower, "BBIM_SanitarySymbol", "Color"), "#ffa500")
        before = set(house.model.by_type("IfcAnnotation"))
        for kwargs in ({"width": 0}, {"width": -1}, {"height": 0}, {"height": -1},
                       {"width": float("inf")}, {"height": True}, {"x": float("nan")},
                       {"z": None}, {"color": "bad-color"}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                drawing.add_shower(**({"x": 1, "z": .2} | kwargs))
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        self.assertEqual((drawing._sanitary_symbol_count, drawing._rectangle_count), (1, 1))
        oblique = house.add_drawing("Oblique", 0, 0, 1, 5, view="elevation", direction=(1, 1, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            oblique.add_shower(1, .2)
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)

    def test_toilet_is_semicircle_with_closed_double_rim_and_no_default_outlet(self):
        house = House("Toilet icon")
        drawing = house.add_drawing("kanal", 2, 2, 1, 5, storeys=[])
        other = house.add_drawing("Other", 2, 2, 1, 5, storeys=[])
        before = set(house.model.by_type("IfcAnnotation"))
        toilet = drawing.add_toilet(x=2, z=.2, name="WC")
        self.assert_symbol_annotations(house, before, toilet)
        self.assertIn(toilet, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(toilet, other.group.IsGroupedBy[0].RelatedObjects)
        self.assertEqual((toilet.Name, toilet.ObjectType), ("WC", "LINEWORK"))
        curves = AngleDimensionTests.world_curves(toilet)
        self.assertEqual(len(curves), 2)
        bowl, rim = curves
        self.assertEqual(len(bowl), 33)
        np.testing.assert_allclose(np.linalg.norm(bowl[:, :2] - (2, .4), axis=1), .2)
        np.testing.assert_allclose(bowl[16], (2, .2, 0))
        np.testing.assert_allclose(rim, ((1.8, .4, 0), (1.8, .425, 0),
                                       (2.2, .425, 0), (2.2, .4, 0), (1.8, .4, 0)))
        props = ifcopenshell.util.element.get_pset(toilet, "BBIM_SanitarySymbol")
        self.assertEqual((props["Kind"], props["RimThickness"], props["OutletLength"]), ("toilet", .025, 0))
        self.assertIn("sanitary-toilet", ifcopenshell.util.element.get_pset(toilet, "EPset_Annotation", "Classes"))
        self.assertFalse(house.model.by_type("IfcSanitaryTerminal"))
        for thickness in (0, -.1, float("inf"), float("nan"), True, None):
            before = set(house.model.by_type("IfcAnnotation"))
            with self.subTest(thickness=thickness), self.assertRaises((TypeError, ValueError)):
                drawing.add_toilet(2, .2, rim_thickness=thickness)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)

    def test_basin_and_sink_geometry_share_rim_and_outlet_and_bottom_datum(self):
        house = House("Sanitary icons")
        drawing = house.add_drawing("kanal", 2, 2, 1, 5, storeys=[])
        other = house.add_drawing("Other", 2, 2, 1, 5, storeys=[])
        for method, kind in ((drawing.add_basin, "basin"), (drawing.add_sink, "sink")):
            with self.subTest(kind=kind):
                before = set(house.model.by_type("IfcAnnotation"))
                symbol = method(x=2, z=0.65, name=f"Symbol {kind}")
                self.assert_symbol_annotations(house, before, symbol)
                self.assertEqual(symbol.ObjectType, "LINEWORK")
                self.assertEqual(symbol.Name, f"Symbol {kind}")
                self.assertIn(symbol, drawing.group.IsGroupedBy[0].RelatedObjects)
                self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                curves = AngleDimensionTests.world_curves(symbol)
                self.assertEqual(len(curves), 3)
                bowl, rim, outlet = curves
                np.testing.assert_allclose(np.min(bowl[:, :2], axis=0), (1.7, .65))
                np.testing.assert_allclose(np.max(bowl[:, :2], axis=0), (2.3, .85))
                np.testing.assert_allclose(rim, ((1.65, .85, 0), (2.35, .85, 0)))
                np.testing.assert_allclose(outlet, ((2, .65, 0), (2, .55, 0)))
                if kind == "basin":
                    self.assertEqual(len(bowl), 33)
                    np.testing.assert_allclose(((bowl[:, 0] - 2) / .3)**2 + ((bowl[:, 1] - .85) / .2)**2, 1)
                else:
                    np.testing.assert_allclose(bowl, ((1.7, .85, 0), (1.7, .65, 0),
                                                      (2.3, .65, 0), (2.3, .85, 0)))
                props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SanitarySymbol")
                self.assertEqual(props["Kind"], kind)
                self.assertEqual((props["X"], props["BottomZ"], props["Width"], props["Height"],
                                  props["OutletLength"], props["Color"]), (2, .65, .6, .2, .1, "#000000"))
        self.assertFalse(house.model.by_type("IfcSanitaryTerminal"))

    def test_positions_in_all_views_and_export_mirroring(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Icons", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 2, 3, 5, view=view, direction=direction, storeys=[])
                    for method in (drawing.add_basin, drawing.add_sink, drawing.add_toilet):
                        symbol = method(2, 4, width=.8, height=.3, outlet_length=.15, color="orange")
                        curves = AngleDimensionTests.world_curves(symbol)
                        if view == "plan":
                            expected = ((2, 4, 0), (2, 3.85, 0))
                        elif direction[0]:
                            expected = ((1, 2, 4), (1, 2, 3.85))
                        else:
                            expected = ((2, 2, 4), (2, 2, 3.85))
                        np.testing.assert_allclose(curves[-1], expected)
                        exported = house._export_model().by_guid(symbol.GlobalId)
                        for original, mirrored in zip(curves, AngleDimensionTests.world_curves(exported)):
                            np.testing.assert_allclose(mirrored, original * (-1 if mirror else 1, 1, 1))
                        self.assertEqual(ifcopenshell.util.element.get_pset(exported, "BBIM_SanitarySymbol", "Color"), "#ffa500")

    def test_optional_outlet_semicircle_and_invalid_arguments(self):
        house = House("Icons")
        drawing = house.add_drawing("kanal", 0, 0, 1, 5, storeys=[])
        symbol = drawing.add_basin(0, 0, width=.6, height=.3, outlet_length=0, color="#123456")
        curves = AngleDimensionTests.world_curves(symbol)
        self.assertEqual(len(curves), 2)
        np.testing.assert_allclose(np.linalg.norm(curves[0][:, :2] - (0, .3), axis=1), .3)
        for method in (drawing.add_basin, drawing.add_sink, drawing.add_toilet):
            for kwargs in ({"width": 0}, {"height": -1}, {"outlet_length": -.1}, {"color": "bad-color"},
                           {"width": float("inf")}, {"height": True}, {"name": " "}):
                before = set(house.model.by_type("IfcAnnotation"))
                with self.assertRaises((ValueError, TypeError)):
                    method(2, 3, **kwargs)
                self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
            for x, z in ((True, 0), (0, float("nan"))):
                with self.assertRaises((ValueError, TypeError)):
                    method(x, z)
        diagonal = house.add_drawing("Oblique", 0, 0, 1, 5, view="elevation", direction=(1, 1, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        for method in (diagonal.add_basin, diagonal.add_sink, diagonal.add_toilet):
            with self.assertRaisesRegex(ValueError, "axis-aligned"):
                method(2, 3)
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)


class RoofLayerLevelTests(unittest.TestCase):
    def test_queries_sloping_faces_at_xy_with_normal_thickness(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Levels", mirror_x=mirror)
                roof = house.storey("Upper", elevation=3).roof("Roof")
                plane = roof.plane("Slope", points=((0, 0, 3), (4, 0, 3), (0, 4, 6)))
                plane.layer("Tiles", outline=((0, 0), (4, 0), (4, 5), (0, 5)),
                            z_offset=0.2, thickness=0.1, material="Roof tiles")
                bottom, top = roof.layer_vertical_extent("Roof tiles", x=2, y=2)
                # Base slope is z=3+0.75y, normal.z=0.8. At fixed XY,
                # perpendicular layer offsets become vertical offset / 0.8.
                self.assertAlmostEqual(bottom, 4.5 + 0.2 / 0.8)
                self.assertAlmostEqual(top, 4.5 + 0.3 / 0.8)
                with self.assertRaisesRegex(ValueError, "no .*roof layer at"):
                    roof.layer_vertical_extent("Roof tiles", x=20, y=2)

    def test_uses_horizontal_ceiling_and_respects_roof_openings(self):
        house = House("Levels")
        roof = house.storey("Floor", elevation=0).roof("Roof")
        plane = roof.plane("Flat", points=((0, 0, -3), (4, 0, -3), (0, 4, -3)))
        plane.layer("Ceiling", outline=((0, 0), (4, 0), (4, 4), (0, 4)),
                    z_offset=0.2, thickness=0.025, material="Gypsum plasterboard")
        np.testing.assert_allclose(
            roof.layer_vertical_extent("Gypsum plasterboard", x=1, y=1), (-2.8, -2.775),
        )
        roof.add_opening(rectangle=((0.5, 0.5), (1.5, 1.5)), trimmers=False)
        with self.assertRaisesRegex(ValueError, "no .*roof layer at"):
            roof.layer_vertical_extent("Gypsum plasterboard", x=1, y=1)
        np.testing.assert_allclose(
            roof.layer_vertical_extent("Gypsum plasterboard", x=3, y=3), (-2.8, -2.775),
        )

    def test_respects_actual_clipping_planes_and_material_filter(self):
        house = House("Levels")
        roof = house.storey("Floor", elevation=0).roof("Roof")
        plane = roof.plane("Flat", points=((0, 0, 3), (4, 0, 3), (0, 4, 3)))
        plane.layer("Clipped tiles", outline=((0, 0), (4, 0), (4, 4), (0, 4)),
                    z_offset=0, thickness=0.1, material="Roof tiles",
                    extra_cuts=[((3, 0, 0), (3, 1, 0), (3, 0, 1))])
        np.testing.assert_allclose(roof.layer_vertical_extent("Roof tiles", x=1, y=2), (3, 3.1))
        with self.assertRaisesRegex(ValueError, "no .*roof layer at"):
            roof.layer_vertical_extent("Roof tiles", x=3.5, y=2)
        with self.assertRaisesRegex(ValueError, "no layers of material"):
            roof.layer_vertical_extent("Missing", x=1, y=1)
        with self.assertRaises(ValueError):
            roof.layer_vertical_extent("Roof tiles", x=float("nan"), y=1)


class DrainageStackTests(unittest.TestCase):
    def test_symbol_has_two_filled_halves_circle_and_diagonal_only(self):
        house = House("Drainage")
        floor = house.storey("Ground", elevation=0.25)
        drawing = house.add_drawing("Ground", 2, 3, 1.6, 4, storeys=[floor])
        other = house.add_drawing("Other", 2, 3, 1.6, 4)
        before = set(house.model.by_type("IfcAnnotation"))
        outline = drawing.add_drainage_stack((2, 3), name="Stoupačka kanalizace")
        created = set(house.model.by_type("IfcAnnotation")) - before
        self.assertEqual(len(created), 4)
        self.assertEqual(outline.Name, "Stoupačka kanalizace")
        self.assertEqual(outline.ObjectType, "LINEWORK")
        self.assertTrue(created <= set(drawing.group.IsGroupedBy[0].RelatedObjects))
        self.assertTrue(created.isdisjoint(other.group.IsGroupedBy[0].RelatedObjects))
        self.assertFalse(house.model.by_type("IfcPipeSegment"))
        self.assertFalse(house.model.by_type("IfcOpeningElement"))
        props = ifcopenshell.util.element.get_pset(outline, "BBIM_DrainageStack")
        self.assertEqual(json.loads(props["Center"]), [2, 3])
        self.assertEqual(props["Diameter"], 0.11)
        circle = outline.Representation.Representations[0].Items[0].Elements[0]
        self.assertTrue(circle.is_a("IfcCircle"))
        self.assertAlmostEqual(circle.Radius, 0.055)
        parts = {}
        for item in created:
            placement = ifcopenshell.util.placement.get_local_placement(item.ObjectPlacement)
            np.testing.assert_allclose(placement[:3, 3], (2, 3, 0.25))
            part = ifcopenshell.util.element.get_pset(item, "BBIM_DrainageStackPart", "Part")
            if part:
                parts[part] = item
        self.assertEqual(set(parts), {"white", "orange", "divider"})
        halves = []
        for color in ("white", "orange"):
            item = parts[color]
            representation = item.Representation.Representations[0]
            self.assertEqual((item.ObjectType, representation.RepresentationType), ("FILLAREA", "Annotation2D"))
            fill = representation.Items[0]
            self.assertTrue(fill.is_a("IfcAnnotationFillArea"))
            points = np.array(fill.OuterBoundary.Points.CoordList)
            np.testing.assert_allclose(np.linalg.norm(points, axis=1), circle.Radius)
            np.testing.assert_allclose(points[0], points[-1])
            np.testing.assert_allclose(points[0], -points[-2], atol=1e-12)
            classes = ifcopenshell.util.element.get_pset(item, "EPset_Annotation", "Classes")
            self.assertIn(f"drainage-stack-{color}", classes.split())
            halves.append(points)
        np.testing.assert_allclose(halves[0], -halves[1], atol=1e-12)
        divider = parts["divider"].Representation.Representations[0].Items[0].Elements[0]
        self.assertEqual(len(divider.Points.CoordList), 2)
        np.testing.assert_allclose(divider.Points.CoordList, [halves[1][-2], halves[1][0]])
        self.assertTrue(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "HasAnnotation"))

    def test_floor_plans_share_position_and_mirror_once_and_persist(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Drainage", mirror_x=mirror)
                ground = house.storey("Ground", elevation=0)
                upper = house.storey("Upper", elevation=3)
                drawings = [house.add_drawing(name, 2, 3, z, 4, storeys=[storey])
                            for name, z, storey in (("Ground", 1.5, ground), ("Upper", 4.5, upper))]
                outlines = [drawing.add_drainage_stack((2, 3), diameter=0.16) for drawing in drawings]
                model = house._export_model()
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "drainage.ifc"
                    model.write(str(path))
                    reopened = ifcopenshell.open(path)
                    for outline, z in zip(outlines, (0, 3)):
                        item = reopened.by_guid(outline.GlobalId)
                        placement = ifcopenshell.util.placement.get_local_placement(item.ObjectPlacement)
                        np.testing.assert_allclose(placement[:3, 3], (-2 if mirror else 2, 3, z))
                        props = ifcopenshell.util.element.get_pset(item, "BBIM_DrainageStack")
                        self.assertEqual(props["Diameter"], 0.16)
                        self.assertEqual(json.loads(props["Center"]), [2, 3])

    def test_invalid_symbols_do_not_create_partial_annotations(self):
        house = House("Drainage")
        drawing = house.add_drawing("Ground", 0, 0, 1.5, 4)
        before = set(house.model.by_type("IfcAnnotation"))
        for diameter, error in ((0, ValueError), (-1, ValueError), (float("inf"), ValueError), (True, TypeError)):
            with self.assertRaises(error):
                drawing.add_drainage_stack((2, 3), diameter=diameter)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        with self.assertRaises(ValueError):
            drawing.add_drainage_stack((2, 3), name=" ")
        with self.assertRaises(TypeError):
            drawing.add_drainage_stack((2, 3, 4))
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        elevation = house.add_drawing("Section", 0, 0, 1.5, 4, view="elevation", direction=(1, 0, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "plan"):
            elevation.add_drainage_stack((2, 3))
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)

    def test_fill_styles_are_opaque_and_have_no_box_outline(self):
        stylesheet = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text(encoding="utf-8")
        for selector, rule in (("drainage-stack-fill", "stroke: none !important"),
                               ("drainage-stack-white", "fill: white !important"),
                               ("drainage-stack-orange", "fill: #ffa500 !important")):
            body = stylesheet.split(f".PredefinedType-FILLAREA.{selector} {{", 1)[1].split("}", 1)[0]
            self.assertIn(rule, body)


class FloorCornerTests(unittest.TestCase):
    def test_selected_other_storey_room_corners_are_included_without_its_geometry(self):
        house = House("Corner references", mirror_x=True)
        ground = house.storey("Ground", elevation=0)
        upper = house.storey("Upper", elevation=3)
        outline = [(1, 1), (4, 1), (4, 3), (1, 3)]
        hallway = ground.floor_layer("Hallway", room_id="0.04", outline=outline, thickness=.1)
        ground.floor_layer("Kitchen", room_id="0.01", outline=outline, thickness=.1)
        room = upper.floor_layer("Room", room_id="P.01", outline=outline, thickness=.1)
        drawing = house.add_drawing("Upper electrical", 0, 0, 5, 6, storeys=[upper])
        expected = {f"{floor.room_id}.{i}": p for floor in (room, hallway)
                    for i, p in enumerate(floor.outline, 1)}
        before = len(list(house.model))
        self.assertEqual(drawing.add_floor_corner_labels(upper, extra_floors=[hallway], show=False), expected)
        self.assertEqual(len(list(house.model)), before)
        self.assertEqual(drawing.add_floor_corner_labels(upper, extra_floors=[hallway]), expected)
        self.assertEqual(list(drawing.storeys), [upper])
        labels = [p for a in drawing.group.IsGroupedBy[0].RelatedObjects
                  if (p := ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner"))]
        self.assertEqual({p["Identifier"] for p in labels}, set(expected))
        for p in labels:
            self.assertEqual(p["Floor"], hallway.GlobalId if p["Identifier"].startswith("0.04.") else room.GlobalId)
        exported = house._export_model()
        for annotation in drawing.group.IsGroupedBy[0].RelatedObjects:
            props = ifcopenshell.util.element.get_pset(annotation, "BBIM_DrawingCircle")
            if props:
                x, y = json.loads(props["Center"])
                matrix = ifcopenshell.util.placement.get_local_placement(exported.by_guid(annotation.GlobalId).ObjectPlacement)
                np.testing.assert_allclose(matrix[:3, 3], (-x, y, 3))

    def test_invalid_extra_floors_do_not_add_partial_guides(self):
        house = House("Corners")
        upper = house.storey("Upper", elevation=3)
        outline = [(0, 0), (3, 0), (3, 3), (0, 3)]
        floor = upper.floor_layer("Room", room_id="P.01", outline=outline, thickness=.1)
        drawing = house.add_drawing("Upper electrical", 0, 0, 5, 6, storeys=[upper])
        foreign = House("Other").storey("Other", elevation=0).floor_layer("Other", outline=outline, thickness=.1)
        before = len(list(house.model))
        for extras in (None, "0.04", [123], [foreign], [floor]):
            with self.subTest(extras=extras), self.assertRaises((TypeError, ValueError)):
                drawing.add_floor_corner_labels(upper, extra_floors=extras)
            self.assertEqual(len(list(house.model)), before)

    def test_floor_collection_ids_scope_and_hidden_coordinate_map(self):
        house = House("Corner references")
        ground = house.storey("Ground", elevation=0.2)
        upper = house.storey("Upper", elevation=3)
        floor = ground.floor_layer("Kitchen", room_id="0.01", outline=[(1, 1), (5, 1), (5, 4), (1, 4)], thickness=.1)
        upper.floor_layer("Upper room", room_id="1.01", outline=floor.outline, thickness=.1)
        ground.floor_layer("Structural slab", outline=floor.outline, thickness=.2, kind="BASESLAB")
        drawing = house.add_drawing("Elektro", 3, 2.5, 2, 5, storeys=[ground])
        # Discover floors added after the drawing too; room names are a fallback ID.
        other = ground.floor_layer("Other", outline=[(6, 1), (9, 1), (9, 4), (6, 4)], thickness=.1)
        self.assertEqual(ground.floor_layers, (floor, ground.floor_layers[1], other))
        expected = {f"0.01.{i}": p for i, p in enumerate(floor.outline, 1)}
        expected.update({f"Other.{i}": p for i, p in enumerate(other.outline, 1)})
        before = len(list(house.model))
        self.assertEqual(drawing.add_floor_corner_labels(ground, show=False), expected)
        self.assertEqual(len(list(house.model)), before)
        self.assertEqual(drawing.add_floor_corner_labels(ground), expected)
        annotations = drawing.group.IsGroupedBy[0].RelatedObjects
        labels = [ifcopenshell.util.element.get_pset(a, "BBIM_FloorCorner") for a in annotations]
        labels = [p for p in labels if p]
        self.assertEqual({p["Identifier"] for p in labels}, set(expected))
        for p in labels:
            self.assertEqual(tuple(json.loads(p["Point"])), expected[p["Identifier"]])
        self.assertEqual(ifcopenshell.util.element.get_pset(floor, "BBIM_FloorLayer", "RoomIdentifier"), "0.01")
        reopened = ifcopenshell.file.from_string(house.model.to_string())
        self.assertEqual(ifcopenshell.util.element.get_pset(
            reopened.by_guid(floor.GlobalId), "BBIM_FloorLayer", "RoomIdentifier"), "0.01")

    def test_corner_circles_follow_mirrored_model_without_changing_source_points(self):
        for mirror in (False, True):
            house = House("Corners", mirror_x=mirror)
            storey = house.storey("Ground", elevation=0.2)
            floor = storey.floor_layer("Room", room_id="0.01", outline=[(1, 1), (5, 1), (5, 4), (1, 4)], thickness=.1)
            drawing = house.add_drawing("Elektro", 3, 2.5, 2, 5, storeys=[storey])
            points = drawing.add_floor_corner_labels(storey)
            exported = house._export_model()
            markers = [a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                       if ifcopenshell.util.element.get_pset(a, "BBIM_DrawingCircle")]
            self.assertEqual(len(markers), 4)
            centres = set()
            for marker in markers:
                point = tuple(json.loads(ifcopenshell.util.element.get_pset(marker, "BBIM_DrawingCircle", "Center")))
                centres.add(point)
                placement = ifcopenshell.util.placement.get_local_placement(
                    exported.by_guid(marker.GlobalId).ObjectPlacement)
                np.testing.assert_allclose(placement[:3, 3], (point[0] * (-1 if mirror else 1), point[1], 0.2))
            self.assertEqual(centres, set(floor.outline))
            self.assertEqual(points["0.01.1"], (1, 1))

    def test_rejects_invalid_options_and_duplicate_ids_before_adding_guides(self):
        house = House("Corners")
        storey = house.storey("Ground", elevation=0)
        drawing = house.add_drawing("Elektro", 0, 0, 2, 5, storeys=[storey])
        for kwargs, error in (({"show": 1}, TypeError), ({"font_size": 0}, ValueError),
                              ({"color": "invalid"}, ValueError)):
            before = len(list(house.model))
            with self.assertRaises(error):
                drawing.add_floor_corner_labels(storey, **kwargs)
            self.assertEqual(len(list(house.model)), before)
        outline = [(0, 0), (3, 0), (3, 3), (0, 3)]
        before = len(list(house.model))
        with self.assertRaises(ValueError):
            storey.floor_layer("Invalid", room_id=" ", outline=outline, thickness=.1)
        self.assertEqual(len(list(house.model)), before)
        for name in ("First", "Second"):
            storey.floor_layer(name, room_id="0.01", outline=outline, thickness=.1)
        before = len(list(house.model))
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            drawing.add_floor_corner_labels(storey)
        self.assertEqual(len(list(house.model)), before)

    def test_corner_guides_move_above_fills_without_duplication_or_template_damage(self):
        source = ('<svg><defs><text data-type="text-template"/></defs>'
                  '<line id="leader" class="drawing-line floor-corner-guide" x1="0" y1="0" x2="1" y2="1"/>'
                  '<circle id="point" class="floor-corner-guide" cx="0" cy="0" r=".03"/>'
                  '<text id="label"><tspan class="floor-corner-guide">0.01.1</tspan></text>'
                  '<path id="floor" fill="white" d="M0 0L2 0L2 2Z"/></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "drawing.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_floor_corner_overlays(path)
            result = path.read_text(encoding="utf-8")
            root = ET.fromstring(result)
            self.assertEqual(root[-1].get("class"), "floor-corner-overlays")
            self.assertEqual([n.get("id") for n in root[-1]], ["leader", "point", "label"])
            self.assertIsNotNone(root.find("defs/text"))
            for identifier in ("leader", "point", "label", "floor"):
                self.assertEqual(result.count(f'id="{identifier}"'), 1)
            _postprocess_floor_corner_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)
            source = '<svg><text><tspan>Unrelated</tspan></text></svg>'
            path.write_text(source, encoding="utf-8")
            _postprocess_floor_corner_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), source)


class DimensionOverlayTests(unittest.TestCase):
    def test_reversed_dimensions_keep_text_upright_and_width_before_height(self):
        cases = (
            ("left", (10, 10, 0, 10), "180.000005", (13, 11), (13, 9),
             "translate(5, 9) rotate(0)", "translate(5, 11) rotate(0)"),
            ("left-negative-angle", (10, 10, 0, 10), "-180", (5, 11), (5, 9),
             "translate(5, 9) rotate(0)", "translate(5, 11) rotate(0)"),
            ("down", (10, 0, 10, 10), "90.0000025", (11, 5), (9, 5),
             "translate(9, 5) rotate(-90)", "translate(11, 5) rotate(-90)"),
            ("diagonal-up-left", (10, 10, 0, 0), "-135", (4, 6), (6, 4),
             "translate(6, 4) rotate(45)", "translate(4, 6) rotate(45)"),
            ("diagonal-down-left", (10, 0, 0, 10), "135", (6, 6), (4, 4),
             "translate(4, 4) rotate(-45)", "translate(6, 6) rotate(-45)"),
            ("upright-horizontal", (0, 10, 10, 10), "0", (5, 9), (5, 11),
             "translate(5, 9) rotate(0)", "translate(5, 11) rotate(0)"),
            ("upright-vertical", (10, 10, 10, 0), "-90.0000025", (9, 5), (11, 5),
             "translate(9, 5) rotate(-90)", "translate(11, 5) rotate(-90)"),
        )
        for name, (x1, y1, x2, y2), angle, width, height, expected_width, expected_height in cases:
            for with_description in (False, True):
                with self.subTest(case=name, description=with_description), TemporaryDirectory() as directory:
                    source = (f'<svg><line id="dim" class="PredefinedType-DIMENSION" '
                              f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-start="url(#tick)"/>'
                              f'<text id="width" dominant-baseline="baseline" '
                              f'transform="translate({width[0]}, {width[1]}) rotate({angle})">'
                              '<tspan class="DIMENSION">1000</tspan></text>')
                    if with_description:
                        source += (f'<text id="height" dominant-baseline="hanging" '
                                   f'transform="translate({height[0]}, {height[1]}) rotate({angle})">'
                                   '<tspan class="DIMENSION">2100 (900)</tspan></text>')
                    source += '<text id="note" transform="translate(1, 2) rotate(180)">Note</text></svg>'
                    path = Path(directory) / "dimension.svg"
                    path.write_text(source)
                    _postprocess_dimension_overlays(path)
                    result = path.read_text()
                    root = ET.fromstring(result)
                    width_text = root.find('.//text[@id="width"]')
                    self.assertEqual(width_text.get("transform"), expected_width)
                    self.assertEqual(width_text.get("dominant-baseline"), "baseline")
                    self.assertEqual(width_text.find("tspan").text, "1000")
                    if with_description:
                        height_text = root.find('.//text[@id="height"]')
                        self.assertEqual(height_text.get("transform"), expected_height)
                        self.assertEqual(height_text.get("dominant-baseline"), "hanging")
                        self.assertEqual(height_text.find("tspan").text, "2100 (900)")
                    self.assertEqual(root.find('.//text[@id="note"]').get("transform"), "translate(1, 2) rotate(180)")
                    self.assertEqual(root.find('.//line[@id="dim"]').get("marker-start"), "url(#tick)")
                    _postprocess_dimension_overlays(path)
                    self.assertEqual(path.read_text(), result)

    def test_short_labels_are_centred_in_plan_and_elevation_rendering(self):
        source = ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
                  '<g class="section">'
                  '<line class="PredefinedType-DIMENSION" x1="0" y1="10" x2="1" y2="10"/>'
                  '<text id="width" transform="translate(4, 9) rotate(0)"><tspan class="DIMENSION">80</tspan></text>'
                  '<text id="height" transform="translate(4, 11) rotate(0)"><tspan class="DIMENSION">2100 (0)</tspan></text>'
                  '<line class="PredefinedType-DIMENSION" x1="10" y1="10" x2="10" y2="9"/>'
                  '<text id="vertical" transform="translate(9, 6) rotate(-90)"><tspan class="DIMENSION">100</tspan></text>'
                  '<line class="PredefinedType-DIMENSION" x1="20" y1="20" x2="21" y2="21"/>'
                  '<text id="diagonal" transform="translate(24, 22) rotate(45)"><tspan class="DIMENSION">141</tspan></text>'
                  '<text id="note" transform="translate(9, 5) rotate(0)"><tspan class="TEXT">Note</tspan></text>'
                  '<path id="fill" fill="white" d="M0 0H30V30H0Z"/></g></svg>')
        for view in ("plan", "elevation"):
            with self.subTest(view=view), TemporaryDirectory() as directory:
                directory = Path(directory)
                house = House("Centre dimensions")
                drawing = house.add_drawing("View", 0, 0, 2, 4, view=view,
                                            direction=(1, 0, 0) if view == "elevation" else None)
                house.write(directory / "house.ifc")
                path = directory / "drawing.svg"

                def render(command, *, check):
                    Path(command[command.index("--output") + 1]).write_text(source)
                    return subprocess.CompletedProcess(command, 0)

                with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                        patch("ifc_utils.subprocess.run", side_effect=render):
                    drawing.render(path)
                root = ET.parse(path).getroot()
                ns = {"s": "http://www.w3.org/2000/svg"}
                for identifier, expected in {
                    "width": "translate(0.5, 9) rotate(0)",
                    "height": "translate(0.5, 11) rotate(0)",
                    "vertical": "translate(9, 9.5) rotate(-90)",
                    "diagonal": "translate(21.5, 19.5) rotate(45)",
                    "note": "translate(9, 5) rotate(0)",
                }.items():
                    self.assertEqual(root.find(f".//s:text[@id='{identifier}']", ns).get("transform"), expected)
                result = path.read_text()
                _postprocess_dimension_overlays(path)
                self.assertEqual(path.read_text(), result)

    def test_moves_complete_dimensions_after_fills_without_duplicates(self):
        source = ('<svg xmlns="http://www.w3.org/2000/svg">'
                  '<defs><g id="template"><text data-type="text-template"/></g>'
                  '<marker id="dimension-marker-start"><path d="M0 0L1 1"/></marker></defs>'
                  '<line id="dimension" class="IfcAnnotation PredefinedType-DIMENSION" '
                  'x1="0" y1="0" x2="0" y2="2" marker-start="url(#dimension-marker-start)"/>'
                  '<text id="label" transform="translate(1,2) rotate(-90)">'
                  '<tspan class="DIMENSION" x="0" y="0">100</tspan></text>'
                  '<line id="extension" class="PredefinedType-LINEWORK dimension-extension fine" '
                  'x1="0" y1="0" x2="1" y2="0"/>'
                  '<path id="arc" class="PredefinedType-ANGLE angle-dimension" d="M0 0L1 1"/>'
                  '<text id="angle-label"><tspan class="ANGLE">36°</tspan></text>'
                  '<polyline id="reference" class="PredefinedType-LINEWORK angle-reference fine" '
                  'points="0,0 1,0 1,1"/>'
                  '<g id="floor" class="IfcSlab cut"><path fill="white" d="M0 0L3 0L3 3Z"/></g>'
                  '<g class="right-side-panel"><text id="legend">Legend</text></g>'
                  '<g class="change-floor-symbol-overlays"><path id="arrow" d="M0 0L1 1"/></g>'
                  '</svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_dimension_overlays(path)
            result = path.read_text(encoding="utf-8")
            root = ET.fromstring(result)
            ns = {"s": "http://www.w3.org/2000/svg"}
            overlay = root.find("s:g[@class='dimension-overlays']", ns)
            self.assertIsNotNone(overlay)
            self.assertEqual(list(root)[-1], overlay)
            identifiers = ["dimension", "label", "extension", "arc", "angle-label", "reference"]
            self.assertEqual([element.get("id") for element in overlay], identifiers)
            self.assertEqual(overlay[1].get("transform"), "translate(1, 1) rotate(-90)")
            self.assertEqual(overlay[0].get("marker-start"), "url(#dimension-marker-start)")
            for identifier in identifiers + ["floor", "legend", "arrow", "template", "dimension-marker-start"]:
                self.assertEqual(result.count(f'id="{identifier}"'), 1)
            self.assertLess(result.index('id="floor"'), result.index('id="dimension"'))
            self.assertLess(result.index('id="arrow"'), result.index('id="dimension"'))
            _postprocess_dimension_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_leaves_svg_without_dimensions_unchanged(self):
        source = ('<svg><defs><text data-type="text-template"/></defs>'
                  '<text><tspan class="TEXT">100</tspan></text>'
                  '<line class="drawing-line" x1="0" y1="0" x2="1" y2="1"/></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_dimension_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), source)


class ChangeFloorSymbolTests(unittest.TestCase):
    def test_moves_whole_arrow_and_anchor_circle_above_masks_without_duplication(self):
        source = ('<svg xmlns="http://www.w3.org/2000/svg">'
                  '<defs><g id="template"><text data-type="text-template"/></g></defs>'
                  '<g class="section"><line class="change-floor-symbol drawing-line drawing-line-width-0p1" '
                  'id="shaft" x1="0" y1="0" x2="1" y2="1"/>'
                  '<polyline class="change-floor-symbol" id="head" points="0,1 1,1 1,0"/>'
                  '<path class="change-floor-symbol" id="sampled-circle" d="M0 0L1 1"/>'
                  '<circle class="change-floor-symbol" id="circle" cx="0" cy="0" r=".05"/>'
                  '<polygon class="door-overhead-mask" id="mask" points="0,0 2,0 2,2"/>'
                  '<path id="wall" d="M0 0L2 0"/></g>'
                  '<g class="door-symbol-overlays"><path id="door" d="M0 0L2 2"/></g></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_change_floor_symbol_overlays(path)
            result = path.read_text(encoding="utf-8")
            root = ET.fromstring(result)
            ns = {"s": "http://www.w3.org/2000/svg"}
            overlay = root.find("s:g[@class='change-floor-symbol-overlays']", ns)
            self.assertIsNotNone(overlay)
            self.assertEqual(list(root)[-1], overlay)
            self.assertEqual([e.get("id") for e in overlay], ["shaft", "head", "sampled-circle", "circle"])
            self.assertLess(result.index('id="mask"'), result.index('id="shaft"'))
            self.assertLess(result.index('id="door"'), result.index('id="shaft"'))
            self.assertIn('drawing-line-width-0p1', overlay[0].get("class"))
            for identifier in ("shaft", "head", "sampled-circle", "circle", "mask", "wall", "door", "template"):
                self.assertEqual(result.count(f'id="{identifier}"'), 1)
            _postprocess_change_floor_symbol_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_overlay_leaves_drawings_without_floor_change_symbols_unchanged(self):
        source = '<svg><defs/><path class="drawing-line" d="M0 0L1 1"/></svg>'
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_change_floor_symbol_overlays(path)
            self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_all_four_arrows_keep_screen_directions_in_every_view_and_mirrored_export(self):
        offset = .6 / 2**.5
        expected = {
            "to up": ((0, 0), (offset, offset)),
            "to down": ((0, 0), (-offset, -offset)),
            "from up": ((offset, offset), (0, 0)),
            "from down": ((-offset, -offset), (0, 0)),
        }
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Floor changes", mirror_x=mirror)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction, storeys=[])
                    other = house.add_drawing("Other", 1, 1.5, 4, 5, storeys=[])
                    for kind, shaft in expected.items():
                        before = set(house.model.by_type("IfcAnnotation"))
                        arrow = drawing.add_change_floor_symbol(2, 3, kind)
                        self.assertEqual(set(house.model.by_type("IfcAnnotation")) - before, {arrow})
                        self.assertIn(arrow, drawing.group.IsGroupedBy[0].RelatedObjects)
                        self.assertNotIn(arrow, other.group.IsGroupedBy[0].RelatedObjects)
                        self.assertEqual(arrow.ObjectType, "LINEWORK")
                        exported = house._export_model()
                        camera = ifcopenshell.util.placement.get_local_placement(exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
                        world_to_camera = np.linalg.inv(camera)
                        if view == "plan":
                            anchor = np.array((2, 3, 0))
                        elif direction[0]:
                            anchor = np.array((1, 2, 3))
                        else:
                            anchor = np.array((2, 1.5, 3))
                        anchor *= (-1 if mirror else 1, 1, 1)
                        anchor_camera = world_to_camera @ np.append(anchor, 1)
                        curves = AngleDimensionTests.world_curves(exported.by_guid(arrow.GlobalId))
                        self.assertEqual([len(c) for c in curves], [2, 3, 33])
                        screen = [(world_to_camera @ np.column_stack((c, np.ones(len(c)))).T).T[:, :2]
                                  - anchor_camera[:2] for c in curves]
                        np.testing.assert_allclose(screen[0], shaft, atol=1e-12)
                        np.testing.assert_allclose(screen[1][1], shaft[1], atol=1e-12)
                        np.testing.assert_allclose(np.linalg.norm(screen[2], axis=1), .6 / 12, atol=1e-12)
                        np.testing.assert_allclose(screen[2][0], screen[2][-1], atol=1e-12)
                        np.testing.assert_allclose(np.mean(screen[2][:-1], axis=0), (0, 0), atol=1e-12)
                        tangent = (np.array(shaft[1]) - shaft[0]) / .6
                        for wing in (screen[1][0], screen[1][2]):
                            self.assertAlmostEqual(float(np.dot(wing - shaft[1], tangent)), -.15)
                        props = ifcopenshell.util.element.get_pset(exported.by_guid(arrow.GlobalId), "BBIM_ChangeFloorSymbol")
                        self.assertAlmostEqual(props["AnchorRadius"], .6 / 12)
                        self.assertEqual((json.loads(props["Point"]), props["Type"], props["Size"], props["LineWidth"]),
                                         ([2, 3], kind, .6, .1))

    def test_custom_appearance_persistence_and_invalid_arguments(self):
        house = House("Floor changes", mirror_x=True)
        drawing = house.add_drawing("View", 0, 0, 2, 5, storeys=[])
        arrow = drawing.add_change_floor_symbol(2, 3, type=" FROM UP ", size=.8, color="orange", line_width=.3, name="Riser")
        self.assertEqual(arrow.Name, "Riser")
        self.assertAlmostEqual(np.linalg.norm(np.diff(AngleDimensionTests.world_curves(arrow)[0], axis=0)), .8)
        classes = ifcopenshell.util.element.get_pset(arrow, "EPset_Annotation", "Classes").split()
        self.assertIn("drawing-line-color-ffa500", classes)
        self.assertIn("drawing-line-width-0p3", classes)
        self.assertIn("change-floor-symbol", classes)
        with TemporaryDirectory() as directory:
            path = house.write(Path(directory) / "arrows.ifc")
            reopened = ifcopenshell.open(str(path))
            props = ifcopenshell.util.element.get_pset(reopened.by_guid(arrow.GlobalId), "BBIM_ChangeFloorSymbol")
            self.assertEqual((props["Type"], props["Color"], props["LineWidth"]), ("from up", "#ffa500", .3))
            self.assertAlmostEqual(props["AnchorRadius"], .8 / 12)
        before = set(house.model.by_type("IfcAnnotation"))
        for kwargs in ({"type": "up"}, {"type": True}, {"type": None}, {"size": 0}, {"size": -1},
                       {"size": float("inf")}, {"line_width": 0}, {"color": "bad-color"},
                       {"x": float("nan")}, {"y": True}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                drawing.add_change_floor_symbol(**({"x": 2, "y": 3, "type": "to up"} | kwargs))
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        self.assertEqual(drawing._change_floor_symbol_count, 1)
        oblique = house.add_drawing("Oblique", 0, 0, 2, 5, view="elevation", direction=(1, 1, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            oblique.add_change_floor_symbol(2, 3, "to up")
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)


class ElektroLineDrawerTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Electrical routes", mirror_x=True)
        self.drawing = self.house.add_drawing("Electrical", 0, 0, 2, 5, storeys=[])
        self.corners = {"0.03.2": (2, 3), "0.01.7": (4, 5)}
        self.draw = ElektroLineDrawer(self.drawing, self.corners)

    def points(self, annotation):
        return json.loads(ifcopenshell.util.element.get_pset(annotation, "BBIM_DrawingPolyLine", "Points"))

    def test_requested_api_accumulates_and_forwards_appearance(self):
        references = ["-+0.03.2", "--0.01.7"]
        for n in (1, 2):
            path = self.draw(references, style="dashed", color="red", line_width=.3, name="Wire")
            expected = [(2 - n * .1, 3 + n * .1), (4 - n * .1, 5 - n * .1)]
            np.testing.assert_allclose(self.points(path), expected)
            props = ifcopenshell.util.element.get_pset(path, "BBIM_DrawingPolyLine")
            self.assertEqual((props["Style"], props["Color"], props["LineWidth"]), ("dashed", "#ff0000", .3))
            self.assertEqual(path.Name, "Wire")
            self.assertIn(path, self.drawing.group.IsGroupedBy[0].RelatedObjects)
            exported = self.house._export_model().by_guid(path.GlobalId)
            np.testing.assert_allclose(AngleDimensionTests.world_curves(exported)[0],
                                       [(-x, y, 0) for x, y in expected])
        self.assertEqual(self.corners, {"0.03.2": (2, 3), "0.01.7": (4, 5)})

    def test_repeated_corner_and_mixed_signs_share_state(self):
        first = self.draw(["++0.03.2", "++0.03.2", "--0.03.2", "+-0.01.7"])
        np.testing.assert_allclose(self.points(first), [(2.1, 3.1), (2.2, 3.2), (2.1, 3.1), (4.1, 4.9)])
        second = self.draw(["--0.03.2", "-+0.01.7"])
        np.testing.assert_allclose(self.points(second), [(2, 3), (4, 5)])

    def test_helpers_are_isolated_and_copy_the_source_map(self):
        other_drawing = self.house.add_drawing("Other", 0, 0, 2, 5, storeys=[])
        other = ElektroLineDrawer(other_drawing, self.corners, step=.2)
        self.corners["0.03.2"] = (100, 100)
        np.testing.assert_allclose(self.points(self.draw(["++0.03.2", "++0.01.7"])), [(2.1, 3.1), (4.1, 5.1)])
        path = other(["++0.03.2", "++0.01.7"])
        np.testing.assert_allclose(self.points(path), [(2.2, 3.2), (4.2, 5.2)])
        self.assertNotIn(path, self.drawing.group.IsGroupedBy[0].RelatedObjects)

    def test_spaces_preserve_each_axis_accumulated_value(self):
        changes = {"+": .1, "-": -.1, " ": 0}
        for x_sign, x_change in changes.items():
            for y_sign, y_change in changes.items():
                with self.subTest(x_sign=x_sign, y_sign=y_sign):
                    draw = ElektroLineDrawer(self.drawing, self.corners)
                    initial = draw(["  0.03.2", "  0.01.7"])
                    np.testing.assert_allclose(self.points(initial), [(2, 3), (4, 5)])
                    draw(["++0.03.2", "--0.01.7"])
                    path = draw([f"{x_sign}{y_sign}0.03.2", "  0.01.7"])
                    expected = [(2.1 + x_change, 3.1 + y_change), (3.9, 4.9)]
                    np.testing.assert_allclose(self.points(path), expected)
                    repeated = draw(["  0.03.2", "  0.01.7"])
                    np.testing.assert_allclose(self.points(repeated), expected)

    def test_spaces_work_with_one_time_shifts_and_sockets(self):
        self.draw(["++0.03.2", "--0.01.7"])
        path = self.draw(["  0.03.2;1,-1", "socket,0.4,up", "  0.01.7;-1,1"])
        np.testing.assert_allclose(self.points(path), [(3.1, 2.1), (2.9, 5.9)])
        symbol = next(a for a in self.house.model.by_type("IfcAnnotation")
                      if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol"))
        props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SocketSymbol")
        np.testing.assert_allclose(json.loads(props["Point"]), (3.02, 3.62))
        next_path = self.draw(["  0.03.2", "  0.01.7"])
        np.testing.assert_allclose(self.points(next_path), [(2.1, 3.1), (3.9, 4.9)])

    def test_one_time_corner_shifts_do_not_accumulate(self):
        path = self.draw(["++0.03.2;0.25,-0.05", "++0.03.2", "--0.01.7; -0.3, +0.4"])
        expected = [(2.35, 3.05), (2.2, 3.2), (3.6, 5.3)]
        np.testing.assert_allclose(self.points(path), expected)
        exported = self.house._export_model().by_guid(path.GlobalId)
        np.testing.assert_allclose(AngleDimensionTests.world_curves(exported)[0],
                                   [(-x, y, 0) for x, y in expected])
        next_path = self.draw(["++0.03.2;0.25,-0.05", "--0.01.7"])
        np.testing.assert_allclose(self.points(next_path), [(2.55, 3.25), (3.8, 4.8)])
        last_path = self.draw(["--0.03.2;0,0", "++0.01.7"])
        np.testing.assert_allclose(self.points(last_path), [(2.2, 3.2), (3.9, 4.9)])
        self.assertEqual(self.corners, {"0.03.2": (2, 3), "0.01.7": (4, 5)})

    def test_socket_interpolation_includes_one_time_corner_shifts(self):
        path = self.draw(["++0.03.2;1,-1", "socket,0.4,up", "--0.01.7;-1,1"])
        np.testing.assert_allclose(self.points(path), [(3.1, 2.1), (2.9, 5.9)])
        symbol = next(a for a in self.house.model.by_type("IfcAnnotation")
                      if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol"))
        props = ifcopenshell.util.element.get_pset(symbol, "BBIM_SocketSymbol")
        np.testing.assert_allclose(json.loads(props["Point"]), (3.02, 3.62))

    def test_invalid_shifts_do_not_create_annotations_or_consume_offsets(self):
        before = set(self.house.model.by_type("IfcAnnotation"))
        for suffix in ("", "1", "1,2,3", "1,", ",2", "a,2", "1;2,3", "1,2;3,4",
                       "nan,0", "0,inf", "-inf,0"):
            with self.subTest(suffix=suffix), self.assertRaises((TypeError, ValueError)):
                self.draw(["++0.03.2;1,2", f"--0.01.7;{suffix}"])
            self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        with self.assertRaises(ValueError):
            self.draw(["++0.03.2", "socket,0.4,up;1,2", "--0.01.7"])
        self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        # These shifted endpoints coincide, so the polyline must reject them.
        with self.assertRaisesRegex(ValueError, "consecutive points"):
            self.draw(["++0.03.2;2,2", "++0.01.7"])
        self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        path = self.draw(["++0.03.2", "--0.01.7"])
        np.testing.assert_allclose(self.points(path), [(2.1, 3.1), (3.9, 4.9)])

    def test_bad_references_or_styles_do_not_consume_offsets_or_create_annotations(self):
        before = set(self.house.model.by_type("IfcAnnotation"))
        for references in (None, 123, "++0.03.2", [], ["++0.03.2"],
                           ["++0.03.2", "--missing"], ["++0.03.2", "0.01.7"],
                           ["++0.03.2", "++"], ["++0.03.2", "x+0.01.7"], ["++0.03.2", 42]):
            with self.subTest(references=references), self.assertRaises((TypeError, ValueError)):
                self.draw(references)
            self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        for kwargs in ({"style": "bad"}, {"color": "bad-color"}, {"line_width": 0}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                self.draw(["++0.03.2", "--0.01.7"], **kwargs)
            self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        np.testing.assert_allclose(self.points(self.draw(["++0.03.2", "--0.01.7"])), [(2.1, 3.1), (3.9, 4.9)])

    def test_degenerate_route_does_not_consume_offsets(self):
        draw = ElektroLineDrawer(self.drawing, {"a": (0, 0), "b": (.2, .2)})
        before = set(self.house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "consecutive points"):
            draw(["++a", "--b"])
        self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        np.testing.assert_allclose(self.points(draw(["++a", "++b"])), [(.1, .1), (.3, .3)])

    def test_constructor_validation(self):
        for step in (0, -.1, True, float("nan"), float("inf")):
            with self.subTest(step=step), self.assertRaises((TypeError, ValueError)):
                ElektroLineDrawer(self.drawing, self.corners, step=step)
        for corners in (None, [], {"": (0, 0)}, {1: (0, 0)}, {"a": (1, 2, 3)}, {"a": (float("nan"), 0)}):
            with self.subTest(corners=corners), self.assertRaises((TypeError, ValueError)):
                ElektroLineDrawer(self.drawing, corners)
        with self.assertRaisesRegex(TypeError, "Drawing"):
            ElektroLineDrawer(None, self.corners)
        elevation = self.house.add_drawing("Section", 0, 0, 2, 5, view="elevation", direction=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "plan drawing"):
            ElektroLineDrawer(elevation, self.corners)

    def test_sockets_interpolate_each_segment_without_changing_route_or_offsets(self):
        path = self.draw(["++0.03.2", "socket,0.4,up", "socket,0.8,left", "--0.01.7",
                          "socket,0,down", "socket,1,right", "+-0.03.2"],
                         style="dashed", color="blue", line_width=.3)
        points = [(2.1, 3.1), (3.9, 4.9), (2.2, 3)]
        np.testing.assert_allclose(self.points(path), points)
        symbols = {ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol", "Direction"): a
                   for a in self.house.model.by_type("IfcAnnotation")
                   if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol")}
        self.assertEqual(set(symbols), {"up", "down", "left", "right"})
        for direction, point in (("up", (2.82, 3.82)), ("left", (3.54, 4.54)),
                                 ("down", points[1]), ("right", points[2])):
            props = ifcopenshell.util.element.get_pset(symbols[direction], "BBIM_SocketSymbol")
            np.testing.assert_allclose(json.loads(props["Point"]), point)
            self.assertEqual((props["Color"], props["LineWidth"]), ("#008000", .3))
        np.testing.assert_allclose(self.points(self.draw(["--0.03.2", "++0.01.7"])), [(2.1, 2.9), (4, 5)])

    def test_double_sockets_mix_with_single_sockets_and_shifted_corners(self):
        path = self.draw(["  0.03.2;1,-1", "socket,0.2,up", "d_socket,0.4,right",
                          "d_socket,0.8,left", "  0.01.7"])
        np.testing.assert_allclose(self.points(path), [(3, 2), (4, 5)])
        symbols = [ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol")
                   for a in self.house.model.by_type("IfcAnnotation")
                   if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol")]
        self.assertEqual(len(symbols), 3)
        for props in symbols:
            fraction = {"up": .2, "right": .4, "left": .8}[props["Direction"]]
            np.testing.assert_allclose(json.loads(props["Point"]), (3 + fraction, 2 + 3 * fraction))
            self.assertEqual(props["Double"], props["Direction"] != "up")
            self.assertEqual((props["BranchLength"], props["Radius"], props["Color"]),
                             (.225, .1125, "#008000"))
        np.testing.assert_allclose(self.points(self.draw(["  0.03.2", "  0.01.7"])), [(2, 3), (4, 5)])

    def test_three_phase_socket_is_a_red_single_socket_with_all_page_directions(self):
        for mirror in (False, True):
            house = House("Three-phase sockets", mirror_x=mirror)
            drawing = house.add_drawing("Plan", 0, 0, 2, 5)
            draw = ElektroLineDrawer(drawing, {"a": (0, 0), "b": (4, 2)})
            for direction in ("up", "down", "left", "right"):
                with self.subTest(mirror=mirror, direction=direction):
                    before = set(house.model.by_type("IfcAnnotation"))
                    draw(["  a;1,0", f"socket3f,0.4,{direction}", "  b"], color="blue", line_width=.3)
                    socket = next(a for a in set(house.model.by_type("IfcAnnotation")) - before
                                  if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol"))
                    props = ifcopenshell.util.element.get_pset(socket, "BBIM_SocketSymbol")
                    np.testing.assert_allclose(json.loads(props["Point"]), (2.2, .8))
                    self.assertEqual((props["Color"], props["Double"], props["Direction"], props["LineWidth"]),
                                     ("#ff0000", False, direction, .3))
                    reference = drawing.add_socket_symbol((2.2, .8), direction)
                    exported = house._export_model()
                    actual = AngleDimensionTests.world_curves(exported.by_guid(socket.GlobalId))
                    expected = AngleDimensionTests.world_curves(exported.by_guid(reference.GlobalId))
                    self.assertEqual(len(actual), 2)
                    for a, b in zip(actual, expected):
                        np.testing.assert_allclose(a, b, atol=1e-12)
            before = set(house.model.by_type("IfcAnnotation"))
            path = draw(["  a", "socket,0.4,up", "  b"], color="red")
            np.testing.assert_allclose(self.points(path), [(0, 0), (4, 2)])
            # Explicit symbol kinds remain independent of the circuit color.
            green = next(a for a in set(house.model.by_type("IfcAnnotation")) - before
                         if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol"))
            self.assertEqual(ifcopenshell.util.element.get_pset(green, "BBIM_SocketSymbol", "Color"), "#008000")

    def test_invalid_socket_entries_leave_route_and_offsets_unchanged(self):
        before = set(self.house.model.by_type("IfcAnnotation"))
        invalid = ["socket", "socket,0.4", "socket,0.4,up,extra", "socket,no,up",
                   "socket,nan,up", "socket,inf,up", "socket,-0.1,up", "socket,1.1,up",
                   "socket,0.4,diagonal", "unknown,0.4,up", "d_socket", "d_socket,0.4",
                   "d_socket,0.4,diagonal", "d_socket,nan,up", "d_socket,1.1,up",
                   "socket3f", "socket3f,0.4", "socket3f,nan,up", "socket3f,1.1,up",
                   "socket3f,0.4,diagonal", "socket3f,0.4,up;1,2"]
        routes = [["++0.03.2", entry, "--0.01.7"] for entry in invalid]
        routes += [["socket,0.4,up", "++0.03.2", "--0.01.7"],
                   ["++0.03.2", "--0.01.7", "socket,0.4,up"],
                   ["++0.03.2", "socket,0.4,up"],
                   ["d_socket,0.4,up", "++0.03.2", "--0.01.7"],
                   ["++0.03.2", "--0.01.7", "d_socket,0.4,up"],
                   ["socket3f,0.4,up", "++0.03.2", "--0.01.7"],
                   ["++0.03.2", "--0.01.7", "socket3f,0.4,up"],
                   ["++0.03.2", "socket,0.4,up", "--missing"]]
        for route in routes:
            with self.subTest(route=route), self.assertRaises((TypeError, ValueError)):
                self.draw(route)
            self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        with self.assertRaises(ValueError):
            self.draw(["++0.03.2", "socket,0.4,up", "--0.01.7"], color="bad-color")
        self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        path = self.draw(["++0.03.2", "socket,0.4,up", "--0.01.7"])
        np.testing.assert_allclose(self.points(path), [(2.1, 3.1), (3.9, 4.9)])


class SwitchSymbolTests(unittest.TestCase):
    def test_green_switch_geometry_and_page_directions_survive_mirroring(self):
        for mirror in (False, True):
            house = House("Switches", mirror_x=mirror)
            drawing = house.add_drawing("Plan", 0, 0, 2, 5, storeys=[])
            other = house.add_drawing("Other", 0, 0, 2, 5, storeys=[])
            for direction, vector in (("up", (0, 1)), ("down", (0, -1)),
                                      ("left", (-1, 0)), ("right", (1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    switch = drawing.add_switch_symbol((2, 3), direction, line_width=.3)
                    self.assertIn(switch, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(switch, other.group.IsGroupedBy[0].RelatedObjects)
                    exported = house._export_model()
                    paths = AngleDimensionTests.world_curves(exported.by_guid(switch.GlobalId))
                    camera = ifcopenshell.util.placement.get_local_placement(
                        exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
                    screen = [(path - paths[0][0]) @ camera[:3, :3] for path in paths]
                    along = np.array((*vector, 0))
                    across = np.array((along[1], -along[0], 0))
                    self.assertEqual([len(path) for path in screen], [2, 65, 3])
                    np.testing.assert_allclose(screen[0], [np.zeros(3), along * .225], atol=1e-12)
                    center = along * .3
                    np.testing.assert_allclose(np.linalg.norm(screen[1] - center, axis=1), .075, atol=1e-12)
                    np.testing.assert_allclose(screen[1][0], screen[1][-1])
                    self.assertAlmostEqual(float(np.linalg.norm(screen[2][0] - center)), .075)
                    self.assertAlmostEqual(float(np.linalg.norm(screen[2][1] - screen[2][0])), .15)
                    self.assertAlmostEqual(float(np.linalg.norm(screen[2][2] - screen[2][1])), .075 * .75)
                    np.testing.assert_allclose(screen[2][0], center + across * .0375 + along * (.075 * 3**.5 / 2), atol=1e-12)
                    props = ifcopenshell.util.element.get_pset(exported.by_guid(switch.GlobalId), "BBIM_SwitchSymbol")
                    self.assertEqual((props["Direction"], props["Color"], props["LineWidth"]), (direction, "#008000", .3))

    def test_route_switches_share_socket_placement_rules_without_advancing_state(self):
        house = House("Switches")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        draw = ElektroLineDrawer(drawing, {"a": (0, 0), "b": (4, 2)})
        route = draw(["  a;1,0", "switch,0,up", "switch,0.4,left", "switch,1,down",
                      "socket,0.8,right", "light,0.6", "  b"], color="#f080f0", line_width=.3)
        self.assertEqual(json.loads(ifcopenshell.util.element.get_pset(route, "BBIM_DrawingPolyLine", "Points")),
                         [[1, 0], [4, 2]])
        symbols = {p["Direction"]: p for a in house.model.by_type("IfcAnnotation")
                   if (p := ifcopenshell.util.element.get_pset(a, "BBIM_SwitchSymbol"))}
        self.assertEqual(set(symbols), {"up", "left", "down"})
        for direction, point in (("up", (1, 0)), ("left", (2.2, .8)), ("down", (4, 2))):
            np.testing.assert_allclose(json.loads(symbols[direction]["Point"]), point)
            self.assertEqual((symbols[direction]["Color"], symbols[direction]["LineWidth"]), ("#008000", .3))
        unchanged = draw(["  a", "  b"])
        self.assertEqual(json.loads(ifcopenshell.util.element.get_pset(unchanged, "BBIM_DrawingPolyLine", "Points")),
                         [[0, 0], [4, 2]])

    def test_invalid_switches_do_not_create_geometry_or_consume_corner_offsets(self):
        house = House("Switches")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        draw = ElektroLineDrawer(drawing, {"a": (0, 0), "b": (4, 2)})
        before = set(house.model.by_type("IfcAnnotation"))
        for entry in ("switch", "switch,0.4", "switch,nan,up", "switch,0.4,diagonal", "switch,1.1,up",
                      "switch,-.1,up", "switch,0.4,up;1,2"):
            with self.subTest(entry=entry), self.assertRaises((TypeError, ValueError)):
                draw(["++a", entry, "++b"])
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for refs in (["switch,0.4,up", "++a", "++b"], ["++a", "++b", "switch,0.4,up"]):
            with self.assertRaises(ValueError):
                draw(refs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for kwargs in ({"radius": 0}, {"branch_length": -1}, {"radius": float("nan")},
                       {"direction": "diagonal"}, {"color": "bad-color"}, {"line_width": 0}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                drawing.add_switch_symbol((0, 0), **kwargs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        route = draw(["++a", "switch,0.4,up", "++b"])
        np.testing.assert_allclose(json.loads(ifcopenshell.util.element.get_pset(route, "BBIM_DrawingPolyLine", "Points")),
                                   [(.1, .1), (4.1, 2.1)])
        elevation = house.add_drawing("Section", 0, 0, 2, 5, view="elevation", direction=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "plan"):
            elevation.add_switch_symbol((1, 2))


class LightSymbolTests(unittest.TestCase):
    def test_blue_crossed_circle_geometry_scope_and_mirroring(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Lights", mirror_x=mirror)
                house.storey("Floor", elevation=.4)
                drawing = house.add_drawing("Plan", 0, 0, 2, 5)
                other = house.add_drawing("Other", 0, 0, 2, 5)
                symbol = drawing.add_light_symbol((2, 3), line_width=.3, name="Ceiling light")
                self.assertEqual(symbol.Name, "Ceiling light")
                self.assertIn(symbol, drawing.group.IsGroupedBy[0].RelatedObjects)
                self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                exported = house._export_model()
                paths = AngleDimensionTests.world_curves(exported.by_guid(symbol.GlobalId))
                self.assertEqual([len(p) for p in paths], [65, 2, 2])
                center = np.array((-2 if mirror else 2, 3, .4))
                for path in paths:
                    np.testing.assert_allclose(np.linalg.norm(path - center, axis=1), .15, atol=1e-12)
                np.testing.assert_allclose(paths[0][0], paths[0][-1])
                for diagonal in paths[1:]:
                    np.testing.assert_allclose(np.mean(diagonal, axis=0), center)
                first, second = paths[1][1] - paths[1][0], paths[2][1] - paths[2][0]
                self.assertAlmostEqual(float(np.dot(first, second)), 0)
                props = ifcopenshell.util.element.get_pset(exported.by_guid(symbol.GlobalId), "BBIM_LightSymbol")
                self.assertEqual(json.loads(props["Center"]), [2, 3])
                self.assertEqual((props["Color"], props["LineWidth"], props["Radius"]), ("#0000ff", .3, .15))

    def test_route_lights_use_shifted_endpoints_without_advancing_corners(self):
        house = House("Lights")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        draw = ElektroLineDrawer(drawing, {"a": (0, 0), "b": (4, 2)})
        route = draw(["  a;1,0", "light,0.4", "d_socket,0.8,up", "  b"], color="#f080f0", line_width=.3)
        self.assertEqual(json.loads(ifcopenshell.util.element.get_pset(route, "BBIM_DrawingPolyLine", "Points")),
                         [[1, 0], [4, 2]])
        light = next(a for a in house.model.by_type("IfcAnnotation")
                     if ifcopenshell.util.element.get_pset(a, "BBIM_LightSymbol"))
        props = ifcopenshell.util.element.get_pset(light, "BBIM_LightSymbol")
        np.testing.assert_allclose(json.loads(props["Center"]), (2.2, .8))
        self.assertEqual((props["Color"], props["LineWidth"]), ("#0000ff", .3))
        self.assertEqual(len([a for a in house.model.by_type("IfcAnnotation")
                             if ifcopenshell.util.element.get_pset(a, "BBIM_SocketSymbol")]), 1)
        route = draw(["  a", "  b"])
        self.assertEqual(json.loads(ifcopenshell.util.element.get_pset(route, "BBIM_DrawingPolyLine", "Points")),
                         [[0, 0], [4, 2]])

    def test_invalid_lights_leave_geometry_and_corner_offsets_unchanged(self):
        house = House("Lights")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        draw = ElektroLineDrawer(drawing, {"a": (0, 0), "b": (4, 2)})
        before = set(house.model.by_type("IfcAnnotation"))
        for entry in ("light", "light,up", "light,nan", "light,-1", "light,1.1", "light,0.4,up", "light,0.4;1,2"):
            with self.subTest(entry=entry), self.assertRaises((TypeError, ValueError)):
                draw(["++a", entry, "++b"])
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for route in (["light,0.4", "++a", "++b"], ["++a", "++b", "light,0.4"]):
            with self.assertRaises(ValueError):
                draw(route)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for kwargs in ({"radius": 0}, {"radius": float("inf")}, {"color": "bad-color"},
                       {"line_width": 0}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                drawing.add_light_symbol((0, 0), **kwargs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        route = draw(["++a", "light,0", "light,1", "++b"])
        np.testing.assert_allclose(json.loads(ifcopenshell.util.element.get_pset(route, "BBIM_DrawingPolyLine", "Points")),
                                   [(.1, .1), (4.1, 2.1)])
        elevation = house.add_drawing("Section", 0, 0, 2, 5, view="elevation", direction=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "plan"):
            elevation.add_light_symbol((1, 2))


class SocketSymbolTests(unittest.TestCase):
    def test_semicircle_stem_orientation_mirroring_and_drawing_scope(self):
        branch_length, radius = .225, .1125
        for mirror in (False, True):
            house = House("Sockets", mirror_x=mirror)
            drawing = house.add_drawing("Plan", 0, 0, 2, 5, storeys=[])
            other = house.add_drawing("Other", 0, 0, 2, 5, storeys=[])
            for direction, along in (("up", (0, 1)), ("down", (0, -1)),
                                     ("left", (-1, 0)), ("right", (1, 0))):
                for double in (False, True):
                    with self.subTest(mirror=mirror, direction=direction, double=double):
                        symbol = drawing.add_socket_symbol((2, 3), direction, double=double, line_width=.3)
                        self.assertIn(symbol, drawing.group.IsGroupedBy[0].RelatedObjects)
                        self.assertNotIn(symbol, other.group.IsGroupedBy[0].RelatedObjects)
                        exported = house._export_model()
                        paths = AngleDimensionTests.world_curves(exported.by_guid(symbol.GlobalId))
                        camera = ifcopenshell.util.placement.get_local_placement(
                            exported.by_guid(drawing.element.GlobalId).ObjectPlacement)
                        screen = [(p - paths[0][0]) @ camera[:3, :3] for p in paths]
                        along_vector = np.array((*along, 0))
                        across = np.array((along_vector[1], -along_vector[0], 0))
                        np.testing.assert_allclose(screen[0], [np.zeros(3), along_vector * branch_length], atol=1e-12)
                        self.assertEqual(len(screen), 3 if double else 2)
                        for arc_index, arc in enumerate(screen[1:]):
                            self.assertEqual(len(arc), 33)
                            arc_radius = radius if arc_index == 0 else radius * 2 / 3
                            center = along_vector * (branch_length + radius)
                            np.testing.assert_allclose(arc[0], center + across * arc_radius, atol=1e-12)
                            np.testing.assert_allclose(arc[16], center - along_vector * arc_radius, atol=1e-12)
                            np.testing.assert_allclose(arc[-1], center - across * arc_radius, atol=1e-12)
                        props = ifcopenshell.util.element.get_pset(exported.by_guid(symbol.GlobalId), "BBIM_SocketSymbol")
                        self.assertEqual((props["Direction"], props["Color"], props["LineWidth"], props["Double"]),
                                         (direction, "#008000", .3, double))
                        self.assertEqual((props["BranchLength"], props["Radius"]), (branch_length, radius))
                        classes = ifcopenshell.util.element.get_pset(symbol, "EPset_Annotation", "Classes")
                        self.assertIn("drawing-line-color-008000", classes)
                        self.assertIn("drawing-line-width-0p3", classes)

    def test_explicit_socket_dimensions_are_not_scaled_again(self):
        house = House("Sockets")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        symbol = drawing.add_socket_symbol((0, 0), double=True, branch_length=.6, radius=.3)
        paths = AngleDimensionTests.world_curves(symbol)
        np.testing.assert_allclose(paths[0], [(0, 0, 0), (0, .6, 0)])
        np.testing.assert_allclose(paths[1][0], (.3, .9, 0))
        np.testing.assert_allclose(paths[2][0], (.2, .9, 0))

    def test_invalid_socket_parameters_do_not_create_partial_annotations(self):
        house = House("Sockets")
        drawing = house.add_drawing("Plan", 0, 0, 2, 5)
        before = set(house.model.by_type("IfcAnnotation"))
        for kwargs in ({"direction": "diagonal"}, {"branch_length": 0}, {"radius": -.1},
                       {"radius": float("nan")}, {"branch_length": True}, {"color": "bad-color"},
                       {"line_width": 0}, {"name": " "}, {"double": "yes"}, {"double": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                drawing.add_socket_symbol((1, 2), **kwargs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        elevation = house.add_drawing("Section", 0, 0, 2, 5, view="elevation", direction=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "plan"):
            elevation.add_socket_symbol((1, 2))


class DrawingPolyLineTests(unittest.TestCase):
    def test_endpoint_symbols_follow_last_segment_and_first_point_in_all_views(self):
        points = ((2, 3), (4, 3), (5, 5))
        for mirror in (False, True):
            for scale in ("1/100", "1/50"):
                for direction in (None, (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                    with self.subTest(mirror=mirror, scale=scale, direction=direction):
                        house = House("Route ends", mirror_x=mirror)
                        drawing = house.add_drawing("View", 1, 1.5, 4, 5,
                                                    view="plan" if direction is None else "elevation", direction=direction)
                        other = house.add_drawing("Other", 0, 0, 2, 5)
                        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": scale})
                        path = drawing.add_poly_line(points, style="dashed", color="blue", line_width=.2,
                                                     arrow_end=True, circle_start=True)
                        symbols = next(a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                                       if ifcopenshell.util.element.get_pset(a, "BBIM_DrawingPolyLineSymbols", "Polyline") == path.GlobalId)
                        self.assertNotIn(symbols, other.group.IsGroupedBy[0].RelatedObjects)
                        props = ifcopenshell.util.element.get_pset(path, "BBIM_DrawingPolyLine")
                        self.assertEqual((props["ArrowEnd"], props["CircleStart"]), (True, True))
                        classes = ifcopenshell.util.element.get_pset(symbols, "EPset_Annotation", "Classes").split()
                        self.assertIn("solid", classes)
                        self.assertNotIn("dashed", classes)
                        self.assertIn("drawing-line-color-0000ff", classes)
                        self.assertIn("drawing-line-width-0p2", classes)
                        exported = house._export_model()
                        route = AngleDimensionTests.world_curves(exported.by_guid(path.GlobalId))[0]
                        head, circle = AngleDimensionTests.world_curves(exported.by_guid(symbols.GlobalId))
                        self.assertEqual(len(head), 3)
                        self.assertEqual(len(circle), 33)
                        np.testing.assert_allclose(head[1], route[-1], atol=1e-12)
                        tangent = (route[-1] - route[-2]) / np.linalg.norm(route[-1] - route[-2])
                        base = (head[0] + head[2]) / 2
                        units = .1 if scale == "1/100" else .05
                        np.testing.assert_allclose(route[-1] - base, tangent * 2 * units, atol=1e-12)
                        self.assertAlmostEqual(np.linalg.norm(head[0] - head[2]), 1.5 * units)
                        np.testing.assert_allclose(np.linalg.norm(circle - route[0], axis=1), .5 * units, atol=1e-12)
                        np.testing.assert_array_equal(circle[0], circle[-1])

    def test_endpoint_options_are_independent_and_persist_with_all_styles(self):
        for style in ("solid", "dashed", "dashed-arrows"):
            for arrow, circle in ((False, False), (True, False), (False, True), (True, True)):
                with self.subTest(style=style, arrow=arrow, circle=circle):
                    house = House("Route ends")
                    drawing = house.add_drawing("Plan", 0, 0, 2, 5)
                    path = drawing.add_poly_line([(0, 0), (1, 0), (1, 2)], style=style,
                                                 arrow_end=arrow, circle_start=circle)
                    symbols = [a for a in drawing.group.IsGroupedBy[0].RelatedObjects
                               if ifcopenshell.util.element.get_pset(a, "BBIM_DrawingPolyLineSymbols", "Polyline") == path.GlobalId]
                    self.assertEqual(len(symbols), int(arrow or circle))
                    if symbols:
                        self.assertEqual(len(AngleDimensionTests.world_curves(symbols[0])), int(arrow) + int(circle))
                    with TemporaryDirectory() as directory:
                        reopened = ifcopenshell.open(str(house.write(Path(directory) / "route.ifc")))
                        props = ifcopenshell.util.element.get_pset(reopened.by_guid(path.GlobalId), "BBIM_DrawingPolyLine")
                        self.assertEqual((props["ArrowEnd"], props["CircleStart"]), (arrow, circle))
                        if symbols:
                            self.assertEqual(ifcopenshell.util.element.get_pset(reopened.by_guid(symbols[0].GlobalId),
                                                                              "BBIM_DrawingPolyLineSymbols", "Polyline"), path.GlobalId)

    def test_poly_line_coordinates_in_plans_elevations_and_mirrored_exports(self):
        points = ((2, 3), (4, 3), (4, 5), (2, 3))
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Paths", mirror_x=mirror)
                    house.storey("Floor", elevation=.25)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction)
                    other = house.add_drawing("Other", 1, 1.5, 4, 5)
                    before = set(house.model.by_type("IfcAnnotation"))
                    path = drawing.add_poly_line(points, style="dashed", color="orange", line_width=.3)
                    self.assertEqual(set(house.model.by_type("IfcAnnotation")) - before, {path})
                    self.assertEqual((path.Name, path.ObjectType), ("View Poly Line 1", "LINEWORK"))
                    self.assertIn(path, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(path, other.group.IsGroupedBy[0].RelatedObjects)
                    if view == "plan":
                        expected = np.array([(*p, .25) for p in points])
                    elif direction[0]:
                        expected = np.array([(1, *p) for p in points])
                    else:
                        expected = np.array([(p[0], 1.5, p[1]) for p in points])
                    curves = AngleDimensionTests.world_curves(path)
                    self.assertEqual(len(curves), 1)
                    np.testing.assert_allclose(curves[0], expected)
                    exported = house._export_model().by_guid(path.GlobalId)
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(exported)[0],
                                               expected * (-1 if mirror else 1, 1, 1))
                    props = ifcopenshell.util.element.get_pset(exported, "BBIM_DrawingPolyLine")
                    self.assertEqual(json.loads(props["Points"]), [list(p) for p in points])
                    self.assertEqual((props["Style"], props["Color"], props["LineWidth"]), ("dashed", "#ffa500", .3))

    def test_arrow_poly_line_matches_individual_arrow_segments_at_each_scale(self):
        points = ((0, 0), (2, 0), (2, 2), (1, 3))
        for scale in ("1/100", "1/50"):
            for direction in (None, (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                with self.subTest(scale=scale, direction=direction):
                    house = House("Arrow paths", mirror_x=True)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5,
                                                view="plan" if direction is None else "elevation", direction=direction)
                    ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": scale})
                    path = drawing.add_poly_line(points, style="dashed-arrows", color="blue", line_width=.4)
                    expected = []
                    for start, end in zip(points, points[1:]):
                        expected.extend(AngleDimensionTests.world_curves(drawing.add_line(start, end, style="dashed-arrows")))
                    actual = AngleDimensionTests.world_curves(path)
                    self.assertEqual(len(actual), len(expected))
                    for first, second in zip(actual, expected):
                        np.testing.assert_allclose(first, second, atol=1e-12)
                    classes = ifcopenshell.util.element.get_pset(path, "EPset_Annotation", "Classes").split()
                    self.assertIn("dashed-arrows", classes)
                    self.assertNotIn("dashed", classes)
                    self.assertIn("drawing-line-width-0p4", classes)

    def test_two_point_defaults_persistence_and_legend_appearance(self):
        house = House("Paths")
        drawing = house.add_drawing("View", 0, 0, 2, 5, right_panel_width=40, storeys=[])
        path = drawing.add_poly_line([(1, 2), (3, 4)], name="Waste route")
        line = drawing.add_line((1, 2), (3, 4))
        np.testing.assert_allclose(AngleDimensionTests.world_curves(path)[0], AngleDimensionTests.world_curves(line)[0])
        self.assertEqual(path.Name, "Waste route")
        props = ifcopenshell.util.element.get_pset(path, "BBIM_DrawingPolyLine")
        self.assertEqual((props["Style"], props["Color"], props["LineWidth"]), ("solid", "#000000", .1))
        drawing.add_line_legend([(path, "Waste route")])
        classes = ifcopenshell.util.element.get_pset(path, "EPset_Annotation", "Classes")
        self.assertIn(classes, drawing._right_panel_tables[-1]["items"][0]["classes"])
        with TemporaryDirectory() as directory:
            output = house.write(Path(directory) / "paths.ifc")
            reopened = ifcopenshell.open(str(output))
            self.assertEqual(ifcopenshell.util.element.get_pset(reopened.by_guid(path.GlobalId), "BBIM_DrawingPolyLine", "Points"), props["Points"])

    def test_invalid_paths_do_not_create_partial_annotations(self):
        house = House("Paths")
        drawing = house.add_drawing("View", 0, 0, 2, 5)
        before = set(house.model.by_type("IfcAnnotation"))
        for points in (None, 123, "bad", [], [(0, 0)], [(0, 0), (0, 0)],
                       [(0, 0), (1, 1), (1, 1)], [(0, 0), (1, 2, 3)], [(0, 0), (1, float("nan"))]):
            with self.subTest(points=points), self.assertRaises((TypeError, ValueError)):
                drawing.add_poly_line(points)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for kwargs in ({"style": "bad"}, {"color": "bad-color"}, {"line_width": 0},
                       {"arrow_end": 1}, {"arrow_end": "yes"}, {"circle_start": 0}, {"circle_start": None},
                       {"line_width": True}, {"line_width": float("inf")}, {"name": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                drawing.add_poly_line([(0, 0), (1, 1)], **kwargs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        self.assertEqual(drawing._poly_line_count, 0)
        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": "0"})
        with self.assertRaisesRegex(ValueError, "positive drawing scale"):
            drawing.add_poly_line([(0, 0), (1, 1)], style="dashed-arrows")
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        for kwargs in ({"arrow_end": True}, {"circle_start": True}):
            with self.assertRaisesRegex(ValueError, "positive drawing scale"):
                drawing.add_poly_line([(0, 0), (1, 1)], **kwargs)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        oblique = house.add_drawing("Oblique", 0, 0, 2, 5, view="elevation", direction=(1, 1, 0))
        before = set(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            oblique.add_poly_line([(0, 0), (1, 1)])
        self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)


class DrawingLineTests(unittest.TestCase):
    def test_line_width_defaults_and_custom_values_persist_and_reach_legends(self):
        house = House("Line widths")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4, right_panel_width=40)
        for style in ("solid", "dashed", "dashed-arrows"):
            for width in (.1, .3, .725, .000001):
                with self.subTest(style=style, width=width):
                    line = drawing.add_line((0, 0), (1, 1), style=style, line_width=width)
                    exported = house._export_model().by_guid(line.GlobalId)
                    self.assertEqual(ifcopenshell.util.element.get_pset(exported, "BBIM_DrawingLine", "LineWidth"), width)
                    classes = ifcopenshell.util.element.get_pset(line, "EPset_Annotation", "Classes")
                    self.assertIn("drawing-line-width-", classes)
                    drawing.add_line_legend([(line, "Sample")])
                    self.assertIn(classes, drawing._right_panel_tables[-1]["items"][0]["classes"])
        default = drawing.add_line((0, 0), (1, 1))
        self.assertEqual(ifcopenshell.util.element.get_pset(default, "BBIM_DrawingLine", "LineWidth"), .1)

    def test_invalid_widths_do_not_create_partial_lines(self):
        house = House("Line widths")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        before = set(house.model.by_type("IfcAnnotation"))
        for width in (0, -1, float("inf"), float("nan"), True, None, "bad-width"):
            with self.subTest(width=width), self.assertRaises((ValueError, TypeError)):
                drawing.add_line((0, 0), (1, 1), line_width=width)
            self.assertEqual(set(house.model.by_type("IfcAnnotation")), before)
        self.assertEqual(drawing._line_count, 0)

    def test_width_css_is_paper_sized_specific_and_idempotent(self):
        for units_per_mm in (1, 2):
            with self.subTest(units_per_mm=units_per_mm), TemporaryDirectory() as directory:
                path = Path(directory) / "widths.svg"
                path.write_text(
                    f'<svg width="100mm" height="100mm" viewBox="0 0 {100*units_per_mm} {100*units_per_mm}">'
                    '<path class="PredefinedType-LINEWORK drawing-line drawing-line-width-0p3" d="M0 0 L10 10"/>'
                    '<line class="PredefinedType-LINEWORK drawing-line line-legend-sample drawing-line-width-1e-06" '
                    'x1="0" y1="1" x2="10" y2="1"/></svg>', encoding="utf-8",
                )
                _postprocess_drawing_line_colors(path)
                result = path.read_text(encoding="utf-8")
                self.assertIn(
                    f'.PredefinedType-LINEWORK.drawing-line.drawing-line-width-0p3 {{ stroke-width: {.3*units_per_mm:g}px !important; }}', result,
                )
                self.assertIn(f'stroke-width: {1e-6*units_per_mm:g}px !important;', result)
                self.assertLess(result.index('class="drawing-line-colors"'), result.index('<path'))
                self.assertIn('d="M0 0 L10 10"', result)
                _postprocess_drawing_line_colors(path)
                self.assertEqual(path.read_text(encoding="utf-8"), result)
                ET.fromstring(result)

    def test_arrow_dashes_alternate_and_point_toward_end_in_either_direction(self):
        segments = _dashed_arrow_segments((0, 0), (10.8, 0), units_per_mm=1)
        self.assertEqual(len(segments), 6)
        np.testing.assert_allclose(segments[0], [(0, 0), (1.26, 0)])
        np.testing.assert_allclose(segments[1], [(2.7, 0), (3.96, 0)])
        np.testing.assert_allclose(segments[2], [(3.42, 0.36), (3.96, 0), (3.42, -0.36)])
        np.testing.assert_allclose(segments[3], [(5.4, 0), (6.66, 0)])
        for start, end in (((6, 0), (0, 0)), ((0, 0), (0, 6)), ((0, 0), (3.6, 4.8))):
            direction = (np.array(end) - start) / 6
            for segment in _dashed_arrow_segments(start, end, units_per_mm=1):
                if len(segment) == 3:
                    self.assertGreater(np.dot(np.array(segment[1]) - segment[0], direction), 0)
                    self.assertGreater(np.dot(np.array(segment[1]) - segment[2], direction), 0)
        for length in (0.1, 1.6, 1.9, 4.6):
            for segment in _dashed_arrow_segments((0, 0), (length, 0), units_per_mm=1):
                for x, y in segment:
                    self.assertGreaterEqual(x, -1e-9)
                    self.assertLessEqual(x, length + 1e-9)

    def test_arrow_line_native_geometry_and_legend_use_the_same_paper_sized_pattern(self):
        for mirror in (False, True):
            for scale, metres_per_mm in (("1/100", 0.1), ("1/50", 0.05)):
                for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                        ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                        ("elevation", (0, -1, 0))):
                    with self.subTest(mirror=mirror, scale=scale, direction=direction):
                        house = House("Arrow lines", mirror_x=mirror)
                        drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction,
                                                    right_panel_width=40)
                        ifcopenshell.api.pset.edit_pset(house.model, pset=drawing._drawing_pset, properties={"Scale": scale})
                        line = drawing.add_line((2, 3), (3, 3), style="dashed-arrows", color="orange")
                        drawing.add_line_legend([(line, "Utility")])
                        curves = AngleDimensionTests.world_curves(line)
                        source_pattern = _dashed_arrow_segments((2, 3), (3, 3), units_per_mm=metres_per_mm)
                        self.assertEqual(len(curves), len(source_pattern))
                        for curve, points in zip(curves, source_pattern):
                            if view == "plan":
                                expected = np.array([(*p, 0) for p in points])
                            elif direction[0]:
                                expected = np.array([(1, *p) for p in points])
                            else:
                                expected = np.array([(p[0], 1.5, p[1]) for p in points])
                            # A mirrored viewing basis reverses the V's wing
                            # order, but not its geometry or arrow direction.
                            if len(points) == 3 and np.allclose(curve, expected[::-1]):
                                expected = expected[::-1]
                            np.testing.assert_allclose(curve, expected)
                        exported = house._export_model()
                        mirrored_curves = AngleDimensionTests.world_curves(exported.by_guid(line.GlobalId))
                        for curve, mirrored_curve in zip(curves, mirrored_curves):
                            np.testing.assert_allclose(mirrored_curve, curve * np.array((-1 if mirror else 1, 1, 1)))
                        classes = ifcopenshell.util.element.get_pset(line, "EPset_Annotation", "Classes")
                        self.assertIn("dashed-arrows", classes.split())
                        self.assertNotIn("dashed", classes.split())

    def test_lines_use_model_coordinates_in_plans_and_all_elevations_and_mirror_once(self):
        for mirror in (False, True):
            for view, direction in (("plan", None), ("elevation", (1, 0, 0)),
                                    ("elevation", (-1, 0, 0)), ("elevation", (0, 1, 0)),
                                    ("elevation", (0, -1, 0))):
                with self.subTest(mirror=mirror, direction=direction):
                    house = House("Lines", mirror_x=mirror)
                    house.storey("Floor", elevation=0.25)
                    drawing = house.add_drawing("View", 1, 1.5, 4, 5, view=view, direction=direction)
                    line = drawing.add_line((2, 3), (4, 5), style="dashed", color="red", name="Earth strip")
                    self.assertEqual(line.ObjectType, "LINEWORK")
                    properties = ifcopenshell.util.element.get_pset(line, "BBIM_DrawingLine")
                    self.assertEqual((properties["Style"], properties["Color"]), ("dashed", "#ff0000"))
                    self.assertEqual(json.loads(properties["Start"]), [2, 3])
                    if view == "plan":
                        expected = np.array([(2, 3, 0.25), (4, 5, 0.25)])
                    elif direction[0]:
                        expected = np.array([(1, 2, 3), (1, 4, 5)])
                    else:
                        expected = np.array([(2, 1.5, 3), (4, 1.5, 5)])
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(line)[0], expected)
                    exported = house._export_model()
                    expected *= np.array((-1 if mirror else 1, 1, 1))
                    np.testing.assert_allclose(AngleDimensionTests.world_curves(exported.by_guid(line.GlobalId))[0], expected)
                    self.assertIn(line, drawing.group.IsGroupedBy[0].RelatedObjects)
                    self.assertTrue(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "HasAnnotation"))
                    other = house.add_drawing("Other", 1, 1.5, 4, 5)
                    self.assertNotIn(line, other.group.IsGroupedBy[0].RelatedObjects)

    def test_defaults_hex_colors_and_line_legend_share_appearance(self):
        house = House("Lines")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4, right_panel_width=40)
        black = drawing.add_line((0, 0), (1, 1))
        colored = drawing.add_line((0, 1), (1, 2), color="#aBc")
        self.assertEqual(black.Name, "Plan Line 1")
        black_style = ifcopenshell.util.element.get_pset(black, "BBIM_DrawingLine")
        self.assertEqual((black_style["Style"], black_style["Color"]), ("solid", "#000000"))
        self.assertEqual(ifcopenshell.util.element.get_pset(colored, "BBIM_DrawingLine", "Color"), "#aabbcc")
        drawing.add_line_legend([(colored, "Colored line")])
        table = json.loads(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "RightPanelTables"))[0]
        classes = ifcopenshell.util.element.get_pset(colored, "EPset_Annotation", "Classes")
        self.assertEqual(table["items"][0]["classes"], f"IfcAnnotation PredefinedType-LINEWORK {classes}")

    def test_invalid_lines_leave_no_partial_annotations(self):
        house = House("Lines")
        drawing = house.add_drawing("Plan", 0, 0, 2, 4)
        invalid = (({"end": (0, 0)}, ValueError), ({"start": (0, 0, 0)}, TypeError),
                   ({"end": (float("nan"), 0)}, ValueError), ({"style": "wavy"}, ValueError),
                   ({"color": "not a color"}, ValueError), ({"color": True}, TypeError),
                   ({"name": ""}, ValueError))
        before = len(house.model.by_type("IfcAnnotation"))
        for kwargs, error in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                drawing.add_line(**(dict(start=(0, 0), end=(1, 1)) | kwargs))
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)
        self.assertEqual(drawing._line_count, 0)
        diagonal = house.add_drawing("Diagonal", 0, 0, 2, 4, view="elevation", direction=(1, 1, 0))
        before = len(house.model.by_type("IfcAnnotation"))
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            diagonal.add_line((0, 0), (1, 1))
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), before)

    def test_native_line_and_legend_colors_are_injected_in_svg_without_geometry_changes(self):
        svg = ('<svg><path class="PredefinedType-LINEWORK drawing-line dashed drawing-line-color-ff0000" '
               'd="M0 0 L10 10"/><line class="line-legend-sample drawing-line-color-000000" '
               'x1="1" y1="2" x2="3" y2="2"/></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "lines.svg"
            path.write_text(svg, encoding="utf-8")
            _postprocess_drawing_line_colors(path)
            result = path.read_text(encoding="utf-8")
            self.assertIn(".drawing-line-color-ff0000 { stroke: #ff0000 !important; }", result)
            self.assertIn(".drawing-line-color-000000 { stroke: #000000 !important; }", result)
            self.assertIn('d="M0 0 L10 10"', result)
            self.assertLess(result.index('class="drawing-line-colors"'), result.index('<path'))
            _postprocess_drawing_line_colors(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)
            ET.fromstring(result)


class SymbolLegendTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Symbols")
        self.drawing = self.house.add_drawing("Electrical", 0, 0, 2, 5, storeys=[], right_panel_width=60)

    def test_symbol_legend_persists_without_adding_plan_geometry(self):
        before = set(self.house.model.by_type("IfcAnnotation"))
        result = self.drawing.add_symbol_legend([("socket", "Zásuvka"), ("d_socket", "Dvojitá zásuvka")])
        self.assertIs(result, self.drawing)
        self.assertEqual(set(self.house.model.by_type("IfcAnnotation")), before)
        exported = self.house._export_model()
        tables = json.loads(ifcopenshell.util.element.get_pset(
            exported.by_guid(self.drawing.element.GlobalId), "EPset_Drawing", "RightPanelTables"))
        self.assertEqual(tables[0]["kind"], "symbol_legend")
        self.assertEqual(tables[0]["title"], "LEGENDA SYMBOLŮ")
        self.assertEqual(tables[0]["items"], [{"symbol": "socket", "description": "Zásuvka"},
                                            {"symbol": "d_socket", "description": "Dvojitá zásuvka"}])
        self.assertIn("drawing-line-color-008000", tables[0]["classes"])
        self.assertIn("drawing-line-width-0p3", tables[0]["classes"])

    def test_symbols_render_as_green_vectors_and_stack_after_line_legend(self):
        self.drawing.add_line_legend([{"color": "blue", "description": "Zásuvkový okruh"}])
        self.drawing.add_symbol_legend([("socket", "Zásuvka <A> & B"), ("d_socket", "Dvojitá zásuvka")])
        props = ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing")
        for physical_width in (160, 80):
            with self.subTest(physical_width=physical_width), TemporaryDirectory() as directory:
                path = Path(directory) / "symbols.svg"
                path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{physical_width}mm" '
                                'height="160mm" viewBox="0 0 160 160"><g id="geometry"/></svg>', encoding="utf-8")
                _postprocess_right_panel(path, props)
                panel_svg = path.read_text(encoding="utf-8")
                _postprocess_right_panel(path, props)
                self.assertEqual(path.read_text(encoding="utf-8"), panel_svg)
                _postprocess_drawing_line_colors(path)
                root = ET.parse(path).getroot()
                samples = [e for e in root.iter() if "symbol-legend-sample" in e.get("class", "").split()]
                self.assertEqual([sample.get("data-symbol") for sample in samples], ["socket", "d_socket"])
                for sample, curve_count in zip(samples, (2, 3)):
                    self.assertEqual(len(sample), curve_count)
                    self.assertTrue(all(e.tag.endswith("}path") for e in sample))
                    self.assertIn("drawing-line-color-008000", sample.get("class").split())
                    for curve in sample:
                        self.assertTrue(curve.get("d").startswith("M"))
                        self.assertNotIn("Z", curve.get("d"))
                svg = path.read_text(encoding="utf-8")
                self.assertLess(svg.index('class="right-panel-table line-legend"'),
                                svg.index('class="right-panel-table symbol-legend"'))
                self.assertIn("Zásuvka &lt;A&gt; &amp; B", svg)
                self.assertIn("stroke: #008000 !important", svg)
                expected_width = .3 * 160 / physical_width
                self.assertIn(f"stroke-width: {expected_width:g}px !important", svg)

    def test_mixed_legend_renders_blue_light_and_green_sockets(self):
        self.drawing.add_symbol_legend([("socket", "Zásuvka"), ("light", "Světlo")])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "symbols.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="160mm" '
                            'viewBox="0 0 160 160"></svg>', encoding="utf-8")
            _postprocess_right_panel(path, ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing"))
            _postprocess_drawing_line_colors(path)
            root = ET.parse(path).getroot()
            samples = [e for e in root.iter() if "symbol-legend-sample" in e.get("class", "").split()]
            self.assertEqual([e.get("data-symbol") for e in samples], ["socket", "light"])
            self.assertIn("drawing-line-color-008000", samples[0].get("class"))
            self.assertIn("drawing-line-color-0000ff", samples[1].get("class"))
            self.assertEqual(len(samples[1]), 3)
            self.assertEqual(samples[1][0].get("d").count(" L"), 64)
            for diagonal in list(samples[1])[1:]:
                self.assertEqual(diagonal.get("d").count(" L"), 1)
        overridden = self.house.add_drawing("Custom", 0, 0, 2, 5, right_panel_width=60)
        overridden.add_symbol_legend([("light", "Light")], color="red")
        self.assertIn("drawing-line-color-ff0000", overridden._right_panel_tables[0]["classes"])

    def test_three_phase_legend_sample_is_red_and_matches_single_socket(self):
        self.drawing.add_symbol_legend([("socket", "Zásuvka"), ("socket3f", "Zásuvka 380V, 3 fáze")])
        tables = json.loads(ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing", "RightPanelTables"))
        self.assertIn("drawing-line-color-ff0000", tables[0]["items"][1]["classes"])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "socket3f.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="160mm" '
                            'viewBox="0 0 160 160"></svg>', encoding="utf-8")
            _postprocess_right_panel(path, ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing"))
            _postprocess_drawing_line_colors(path)
            root = ET.parse(path).getroot()
            samples = [e for e in root.iter() if "symbol-legend-sample" in e.get("class", "").split()]
            self.assertEqual([sample.get("data-symbol") for sample in samples], ["socket", "socket3f"])
            self.assertIn("drawing-line-color-008000", samples[0].get("class"))
            self.assertIn("drawing-line-color-ff0000", samples[1].get("class"))
            self.assertEqual([[curve.get("d").count(" L") for curve in sample] for sample in samples],
                             [[1, 32], [1, 32]])
            self.assertIn("Zásuvka 380V, 3 fáze", path.read_text(encoding="utf-8"))
        custom = self.house.add_drawing("Custom socket", 0, 0, 2, 5, right_panel_width=60)
        custom.add_symbol_legend([("socket3f", "Socket")], color="blue")
        self.assertIn("drawing-line-color-0000ff", custom._right_panel_tables[0]["classes"])

    def test_switch_legend_has_branch_circle_and_lever(self):
        self.drawing.add_symbol_legend([("switch", "Vypínač")])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "switch.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="160mm" '
                            'viewBox="0 0 160 160"></svg>', encoding="utf-8")
            _postprocess_right_panel(path, ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing"))
            _postprocess_drawing_line_colors(path)
            root = ET.parse(path).getroot()
            sample = next(e for e in root.iter() if "symbol-legend-sample" in e.get("class", "").split())
            self.assertEqual(sample.get("data-symbol"), "switch")
            self.assertIn("drawing-line-color-008000", sample.get("class"))
            self.assertEqual([e.get("d").count(" L") for e in sample], [1, 64, 2])
            self.assertIn("Vypínač", path.read_text(encoding="utf-8"))

    def test_invalid_symbol_legends_leave_tables_unchanged(self):
        for items in ([], None, "socket", ["socket"], [("socket",)], [("unknown", "Bad")],
                      [("socket", "")], [("socket", "Valid"), ("unknown", "Bad")]):
            with self.subTest(items=items), self.assertRaises((TypeError, ValueError)):
                self.drawing.add_symbol_legend(items)
            self.assertEqual(self.drawing._right_panel_tables, [])
        for kwargs in ({"line_width": 0}, {"color": "bad-color"}, {"title": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                self.drawing.add_symbol_legend([("socket", "Socket")], **kwargs)
            self.assertEqual(self.drawing._right_panel_tables, [])
        narrow = self.house.add_drawing("Narrow", 0, 0, 2, 5, right_panel_width=30)
        with self.assertRaisesRegex(ValueError, "40 mm"):
            narrow.add_symbol_legend([("socket", "Socket")])


class LineLegendTests(unittest.TestCase):
    def test_style_only_samples_accept_width_and_reject_invalid_widths(self):
        before = len(self.house.model.by_type("IfcAnnotation"))
        self.drawing.add_line_legend([
            {"description": "Thick", "color": "orange", "line_width": .3},
        ])
        self.assertIn("drawing-line-width-0p3", self.drawing._right_panel_tables[-1]["items"][0]["classes"])
        self.assertEqual(len(self.house.model.by_type("IfcAnnotation")), before)
        tables = list(self.drawing._right_panel_tables)
        for width in (0, -1, float("inf"), True, None):
            with self.subTest(width=width), self.assertRaises((ValueError, TypeError)):
                self.drawing.add_line_legend([{"description": "Bad", "line_width": width}])
            self.assertEqual(self.drawing._right_panel_tables, tables)

    def test_arrow_samples_are_real_vectors_and_keep_color_classes(self):
        self.drawing.add_line_legend([
            {"description": "splašková kanalizace", "style": "dashed-arrows", "color": "orange"},
            {"description": "dešťová kanalizace", "style": "dashed-arrows", "color": "green"},
            {"description": "vodovod", "style": "dashed-arrows", "color": "blue"},
        ])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "found.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="160mm" '
                            'viewBox="0 0 160 160"><g id="geometry"/></svg>', encoding="utf-8")
            _postprocess_right_panel(path, ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing"))
            _postprocess_drawing_line_colors(path)
            root = ET.parse(path).getroot()
            samples = [e for e in root.iter() if "line-legend-sample" in e.get("class", "").split()]
            self.assertEqual(len(samples), 3)
            for sample, color in zip(samples, ("ffa500", "008000", "0000ff")):
                self.assertTrue(sample.tag.endswith("}g"))
                self.assertIn(f"drawing-line-color-{color}", sample.get("class").split())
                self.assertEqual(len(sample), 3)
                self.assertEqual(sum(path.get("d").count(" L") == 2 for path in sample), 1)

    def setUp(self):
        self.house = House("Lines")
        floor = self.house.storey("Floor", elevation=0)
        wall = floor.wall((0, 0), (4, 0), thickness=0.24, height=2.8)
        self.wall = wall
        self.drawing = self.house.add_drawing("Foundation", 2, 0, -1, 4, right_panel_width=40)
        self.outline = self.drawing.add_wall_outlines([wall], style="dashed")

    def test_line_legend_persists_source_styles_without_adding_geometry(self):
        count = len(self.house.model.by_type("IfcAnnotation"))
        result = self.drawing.add_line_legend([(self.outline, "Obrys nosných stěn")])
        self.assertIs(result, self.drawing)
        self.assertEqual(len(self.house.model.by_type("IfcAnnotation")), count)
        exported = self.house._export_model()
        pset = ifcopenshell.util.element.get_pset(exported.by_guid(self.drawing.element.GlobalId), "EPset_Drawing")
        table = json.loads(pset["RightPanelTables"])[0]
        self.assertEqual(table["kind"], "line_legend")
        self.assertEqual(table["title"], "LEGENDA ČAR")
        self.assertEqual(table["items"], [{
            "classes": "IfcAnnotation PredefinedType-LINEWORK load-bearing-wall-outline dashed",
            "description": "Obrys nosných stěn",
        }])

    def test_line_samples_share_outline_css_and_stack_with_existing_tables(self):
        self.drawing.add_material_legend([("brick", "Zdivo")])
        self.drawing.add_line_legend([(self.outline, "Obrys <nosných> & stěn")], title="LEGENDA ČAR")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "found.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="160mm" '
                            'viewBox="0 0 160 160"><g id="geometry"/></svg>', encoding="utf-8")
            pset = ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing")
            _postprocess_right_panel(path, pset)
            svg = path.read_text(encoding="utf-8")
            _postprocess_right_panel(path, pset)
            self.assertEqual(path.read_text(encoding="utf-8"), svg)
            root = ET.fromstring(svg)
            samples = [e for e in root.iter() if "line-legend-sample" in e.get("class", "").split()]
            self.assertEqual(len(samples), 1)
            sample = samples[0]
            source_classes = ifcopenshell.util.element.get_pset(self.outline, "EPset_Annotation", "Classes")
            self.assertTrue(set(source_classes.split()) <= set(sample.get("class").split()))
            self.assertIn("PredefinedType-LINEWORK", sample.get("class").split())
            self.assertEqual(sample.get("y1"), sample.get("y2"))
            self.assertGreater(float(sample.get("x2")) - float(sample.get("x1")), 3)
            self.assertLess(svg.index("material-legend"), svg.index("line-legend"))
            self.assertIn("Obrys &lt;nosných&gt; &amp; stěn", svg)
            self.assertEqual(root.get("width"), "200mm")

    def test_invalid_line_legends_do_not_change_existing_tables(self):
        other = self.house.add_drawing("Other", 2, 0, -1, 4, right_panel_width=40)
        angle = self.drawing.add_angle((0, 0), (1, 0), (1, 1))
        other_line = other.add_wall_outlines([self.wall])
        invalid = (([], ValueError), ("dashed", TypeError), (None, TypeError),
                   (["dashed"], TypeError), ([(self.outline,)], TypeError),
                   ([("dashed", "Wall")], TypeError), ([(other_line, "Wall")], ValueError),
                   ([(angle, "Angle")], ValueError), ([(self.outline, "")], ValueError),
                   ([{"description": "Line", "style": "wavy"}], ValueError),
                   ([{"description": "Line", "color": "bad-color"}], ValueError),
                   ([{"style": "solid"}], TypeError))
        for items, error in invalid:
            with self.subTest(items=items), self.assertRaises(error):
                self.drawing.add_line_legend(items)
            self.assertEqual(self.drawing._right_panel_tables, [])
        narrow = self.house.add_drawing("Narrow", 2, 0, -1, 4, right_panel_width=30)
        with self.assertRaisesRegex(ValueError, "40 mm"):
            narrow.add_line_legend([(self.outline, "Wall")])

    def test_style_only_samples_do_not_add_lines_to_the_plan(self):
        before = len(self.house.model.by_type("IfcAnnotation"))
        self.drawing.add_line_legend([
            {"description": "Bottom", "style": "solid", "color": "black"},
            {"description": "Earth strip", "style": "dashed", "color": "red"},
        ])
        self.assertEqual(len(self.house.model.by_type("IfcAnnotation")), before)
        table = json.loads(ifcopenshell.util.element.get_pset(self.drawing.element, "EPset_Drawing", "RightPanelTables"))[0]
        self.assertIn("drawing-line solid drawing-line-color-000000", table["items"][0]["classes"])
        self.assertIn("drawing-line dashed drawing-line-color-ff0000", table["items"][1]["classes"])

class HouseTests(unittest.TestCase):
    def test_calculates_roof_u_value_with_parallel_rafter_path(self) -> None:
        result = calculate_roof_u_value(
            wood_fiberboard_thickness=0.10,
            wood_fiberboard_lambda=0.05,
            rafter_height=0.20,
            rafter_width=0.08,
            rafter_spacing=0.80,
            rafter_wood_lambda=0.10,
            between_rafter_wool_lambda=0.04,
            under_rafter_wool_thickness=0.05,
            under_rafter_wool_lambda=0.04,
            installation_space_resistance=0.15,
        )

        self.assertIsInstance(result, RoofUValueResult)
        self.assertAlmostEqual(result.rafter_fraction, 0.10)
        self.assertAlmostEqual(result.wood_fiberboard_resistance, 2.0)
        self.assertAlmostEqual(result.rafter_wood_resistance, 2.0)
        self.assertAlmostEqual(result.between_rafter_wool_resistance, 5.0)
        self.assertAlmostEqual(result.under_rafter_wool_resistance, 1.25)
        self.assertAlmostEqual(result.rafter_path_resistance, 5.4)
        self.assertAlmostEqual(result.insulated_path_resistance, 8.4)
        expected_u_value = 0.10 / 5.4 + 0.90 / 8.4
        self.assertAlmostEqual(result.u_value, expected_u_value)
        self.assertAlmostEqual(result.effective_resistance, 1 / expected_u_value)

        with self.assertRaisesRegex(ValueError, "must not exceed"):
            calculate_roof_u_value(
                wood_fiberboard_thickness=0.10,
                wood_fiberboard_lambda=0.05,
                rafter_height=0.20,
                rafter_width=0.81,
                rafter_spacing=0.80,
                rafter_wood_lambda=0.10,
                between_rafter_wool_lambda=0.04,
                under_rafter_wool_thickness=0.05,
                under_rafter_wool_lambda=0.04,
            )

    def test_creates_counter_clockwise_elliptic_stair_polygons(self) -> None:
        polygons = elliptic_stairs(
            center=(2, -1),
            radiuses=(2, 2),
            width=1,
            initial_angle=0,
            step_size=0.8 * np.pi,
        )

        self.assertEqual(len(polygons), 4)
        np.testing.assert_allclose(
            polygons[0],
            (
                (3, -1),
                (2, 0),
                (2, 1),
                (4, -1),
            ),
            atol=1e-5,
        )
        np.testing.assert_allclose(polygons[-1][1], polygons[0][0])
        np.testing.assert_allclose(polygons[-1][2], polygons[0][3])

    def test_creates_elliptic_stairs_with_a_short_closing_step(self) -> None:
        polygons = elliptic_stairs(
            center=(1, 2),
            radiuses=(3, 2),
            width=0.8,
            initial_angle=30,
            step_size=0.7,
        )

        self.assertGreater(len(polygons), 1)
        first_inner = polygons[0][0]
        first_outer = polygons[0][3]
        np.testing.assert_allclose(polygons[-1][1], first_inner, atol=1e-9)
        np.testing.assert_allclose(polygons[-1][2], first_outer, atol=1e-9)
        self.assertGreater(polygons[0][1][1], polygons[0][0][1])

    def test_rejects_invalid_elliptic_stairs(self) -> None:
        with self.assertRaisesRegex(ValueError, "radiuses"):
            elliptic_stairs((0, 0), (0, 2), 1, 0, 0.2)
        with self.assertRaisesRegex(ValueError, "width"):
            elliptic_stairs((0, 0), (2, 2), 0, 0, 0.2)
        with self.assertRaisesRegex(ValueError, "smaller than both radiuses"):
            elliptic_stairs((0, 0), (2, 1), 1, 0, 0.2)
        with self.assertRaisesRegex(ValueError, "0.4 metres"):
            elliptic_stairs((0, 0), (0.4, 1), 0.1, 0, 0.2)
        with self.assertRaisesRegex(ValueError, "step_size"):
            elliptic_stairs((0, 0), (2, 2), 1, 0, 0)
        with self.assertRaisesRegex(ValueError, "circumference"):
            elliptic_stairs((0, 0), (2, 2), 1, 0, 20)

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

    def test_calculates_plane_height_at_xy_independent_of_point_order(
        self,
    ) -> None:
        points = (
            (0, 0, 1),
            (1, 0, 3),
            (0, 1, 4),
        )

        self.assertAlmostEqual(plane_height_at(*points, x=2, y=4), 17)
        self.assertAlmostEqual(
            plane_height_at(points[0], points[2], points[1], x=2, y=4),
            17,
        )

    def test_validates_plane_height_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be collinear"):
            plane_height_at(
                (0, 0, 0), (1, 0, 0), (2, 0, 0), x=0, y=0
            )
        with self.assertRaisesRegex(ValueError, "must not be vertical"):
            plane_height_at(
                (0, 0, 0), (0, 1, 0), (0, 0, 1), x=0, y=0
            )
        with self.assertRaisesRegex(TypeError, "x must be a number"):
            plane_height_at(
                (0, 0, 0), (1, 0, 0), (0, 1, 1), x=True, y=0
            )

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

    def test_wall_plate_role_is_persisted_without_changing_beam_geometry(self) -> None:
        house = House("Wall plates")
        upper = house.storey("Upper", elevation=3)
        plate = upper.beam("Plate", start=(0, 0, 4), end=(5, 0, 4),
                           size=(.16, .16), kind="wall_plate")
        self.assertEqual(plate.kind, "WALL_PLATE")
        self.assertEqual(plate.PredefinedType, "USERDEFINED")
        self.assertEqual(plate.ObjectType, "WALL_PLATE")
        self.assertEqual(ifcopenshell.util.element.get_predefined_type(plate), "WALL_PLATE")
        self.assertEqual(plate.start, (0, 0, 4))
        self.assertEqual(plate.end, (5, 0, 4))
        self.assertEqual(plate.size, (.16, .16))
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), plate)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_volume(shape.geometry), 5 * .16 * .16)
        with TemporaryDirectory() as directory:
            path = house.write(Path(directory) / "wall-plate.ifc")
            reopened = ifcopenshell.open(path)
            self.assertEqual(ifcopenshell.util.element.get_predefined_type(
                reopened.by_guid(plate.GlobalId)), "WALL_PLATE")

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

    def test_appends_beam_specific_cuts_to_roof_plane_cuts(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        plane_cuts = (
            ((0, 0, 0), (0, 1, 0), (0, 0, 1)),
            ((6, 0, 0), (6, 1, 0), (6, 0, 1)),
        )
        extra_cut = ((4, 0, 0), (4, 1, 0), (4, 0, 1))
        plane = roof.plane(
            "Flat roof",
            points=((0, 0, 4), (6, 0, 4), (0, 4, 4)),
            cuts=plane_cuts,
        )

        beam = plane.beam(
            "Trimmed purlin",
            start=(-1, 2),
            end=(7, 2),
            size=(0.1, 0.2),
            kind="PURLIN",
            extra_cuts=(extra_cut,),
        )

        self.assertEqual(beam.extra_cuts, (extra_cut,))
        self.assertEqual(beam.cuts, (*plane_cuts, extra_cut))
        body = ifcopenshell.util.representation.get_representation(
            beam, "Model", "Body", "MODEL_VIEW"
        )
        item = body.Items[0]
        clipping_count = 0
        while item.is_a("IfcBooleanClippingResult"):
            clipping_count += 1
            item = item.FirstOperand
        self.assertEqual(clipping_count, 3)
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), beam)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            4 * 0.1 * 0.2,
        )

        with self.assertRaisesRegex(ValueError, "cut 1 points"):
            plane.beam(
                "Invalid",
                start=(0, 2),
                end=(6, 2),
                size=(0.1, 0.2),
                extra_cuts=[((0, 0, 0), (1, 0, 0), (2, 0, 0))],
            )

    def test_cuts_an_absolute_xy_opening_through_all_roof_parts(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        slope = roof.plane(
            "South slope",
            points=((0, 0, 4), (6, 0, 4), (0, 4, 6)),
        )
        first_layer = slope.layer(
            "Decking",
            outline=((0, 0), (6, 0), (6, 4), (0, 4)),
            thickness=0.1,
            material="Wood",
        )
        batten = slope.beam(
            "Batten",
            start=(0, 1.5 * np.sqrt(5) / 2),
            end=(6, 1.5 * np.sqrt(5) / 2),
            size=(0.05, 0.05),
            material="Wood",
        )
        visibility_storey = house.storey("Roof - test layer", elevation=3)
        visibility_storey.add(first_layer, batten)

        opening = roof.add_opening(
            "Bedroom roof window",
            rectangle=((3, 2), (2, 1)),
        )

        self.assertIsInstance(opening, RoofOpening)
        self.assertEqual(opening.name, "Bedroom roof window")
        self.assertEqual(opening.rectangle, ((2, 1), (3, 2)))
        self.assertTrue(opening.trimmers)
        self.assertEqual(roof.openings, (opening,))
        self.assertEqual(slope.elements, (first_layer, batten))
        self.assertEqual(len(opening.elements), 2)
        for void in opening.elements:
            self.assertTrue(void.is_a("IfcOpeningElement"))
            self.assertEqual(void.PredefinedType, "OPENING")
            self.assertEqual(void.ObjectType, "ROOF_OPENING")
            self.assertEqual(len(void.VoidsElements), 1)
            self.assertEqual(
                json.loads(
                    ifcopenshell.util.element.get_pset(
                        void, "BBIM_RoofOpening", "Rectangle"
                    )
                ),
                [[2.0, 1.0], [3.0, 2.0]],
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    void, "BBIM_RoofOpening", "RoofPlane"
                ),
                slope.GlobalId,
            )
            self.assertTrue(
                ifcopenshell.util.element.get_pset(
                    void, "BBIM_RoofOpening", "Trimmers"
                )
            )
            opening_placement = (
                ifcopenshell.util.placement.get_local_placement(
                    void.ObjectPlacement
                )
            )
            np.testing.assert_allclose(
                opening_placement[:3, 2],
                slope.z_axis,
                atol=1e-9,
            )
        self.assertEqual(
            {void.VoidsElements[0].RelatingBuildingElement for void in opening.elements},
            {first_layer, batten},
        )

        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), first_layer
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            6 * 4 * 0.1 - np.sqrt(5) / 2 * 0.1,
            places=6,
        )

        # Opening framing may overlap the void slightly without being cut.
        trimmer = slope.beam(
            "Roof-window trimmer",
            start=(0, 1.5 * np.sqrt(5) / 2),
            end=(6, 1.5 * np.sqrt(5) / 2),
            size=(0.05, 0.05),
            material="Wood",
            trim_openings=False,
        )
        self.assertIn(trimmer, slope.elements)
        self.assertFalse(trimmer.HasOpenings)
        self.assertNotIn(
            trimmer,
            {
                void.VoidsElements[0].RelatingBuildingElement
                for void in opening.elements
            },
        )
        with self.assertRaisesRegex(TypeError, "trim_openings must be a boolean"):
            slope.beam(
                "Invalid trimmer",
                start=(0, 1),
                end=(1, 1),
                size=(0.05, 0.05),
                trim_openings="no",
            )

        # Registration is order independent: later roof parts inherit the cut.
        second_layer = slope.layer(
            "Underlay",
            outline=((0, 0), (6, 0), (6, 4), (0, 4)),
            z_offset=0.1,
            thickness=0.01,
            material="Underlay",
        )
        distant_layer = slope.layer(
            "Distant layer",
            outline=((7, 0), (8, 0), (8, 1), (7, 1)),
            thickness=0.1,
            material="Wood",
        )
        self.assertEqual(len(opening.elements), 3)
        self.assertEqual(len(second_layer.HasOpenings), 1)
        self.assertFalse(distant_layer.HasOpenings)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "roof-opening.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcOpeningElement")), 3)

    def test_roof_window_aligns_with_tiles_on_both_slopes_and_mirrors(self) -> None:
        for dz in (2, -2):
            with self.subTest(dz=dz):
                house = House("Roof window", mirror_x=True)
                roof = house.storey("Upper floor", elevation=3).roof("Roof")
                slope = roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 4 + dz)))
                opening = roof.add_opening("Bedroom", rectangle=((2, 1), (3, 2)))
                outline = ((0, 0), (6, 0), (6, 6), (0, 6))
                lower = slope.layer("Insulation", outline=outline, thickness=0.2, material="Wool")
                tiles = slope.layer("Tiles", outline=outline, z_offset=0.5,
                                    thickness=0.03, material="Roof tiles")
                window = slope.add_window(opening, top_layer=tiles)
                self.assertIs(opening.window, window)
                self.assertEqual(window.PredefinedType, "SKYLIGHT")
                self.assertAlmostEqual(window.OverallWidth, 1)
                self.assertAlmostEqual(window.OverallHeight, np.sqrt(5) / 2)
                self.assertEqual(len(window.FillsVoids), 1)
                self.assertEqual(window.FillsVoids[0].RelatingOpeningElement.VoidsElements[0].RelatingBuildingElement, tiles)
                self.assertFalse(lower.HasOpenings[0].RelatedOpeningElement.HasFillings)
                self.assertFalse(window.HasOpenings)
                self.assertEqual([r.RepresentationIdentifier for r in window.Representation.Representations], ["Body"])
                matrix = ifcopenshell.util.placement.get_local_placement(window.ObjectPlacement)
                np.testing.assert_allclose(matrix[:3, 1], -np.array(slope.z_axis), atol=1e-9)
                self.assertAlmostEqual(np.linalg.det(matrix[:3, :3]), 1)
                settings = ifcopenshell.geom.settings()
                settings.set(settings.USE_WORLD_COORDS, True)
                shape = ifcopenshell.geom.create_shape(settings, window)
                vertices = np.array(shape.geometry.verts).reshape(-1, 3)
                local = np.array([slope.to_local(tuple(v)) for v in vertices])
                self.assertAlmostEqual(local[:, 2].max(), 0.53)
                self.assertAlmostEqual(local[:, 2].min(), 0.43)
                np.testing.assert_allclose(local[:, :2].min(axis=0), (2, np.sqrt(5) / 2))
                np.testing.assert_allclose(local[:, :2].max(axis=0), (3, np.sqrt(5)))
                aspects = {a.Name: a for a in window.Representation.HasShapeAspects}
                self.assertEqual(set(aspects), {"Lining", "Framing", "Glazing"})
                glass = aspects["Glazing"].ShapeRepresentations[0].Items[0]
                self.assertAlmostEqual(glass.StyledByItem[0].Styles[0].Styles[0].Transparency, 0.6)
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "window.ifc"
                    house.write(path)
                    exported = ifcopenshell.open(path).by_guid(window.GlobalId)
                    self.assertEqual(exported.OverallHeight, window.OverallHeight)
                    self.assertEqual(len(exported.FillsVoids), 1)
                    mirrored_shape = ifcopenshell.geom.create_shape(settings, exported)
                    mirrored = np.array(mirrored_shape.geometry.verts).reshape(-1, 3)
                    vertices[:, 0] *= -1
                    np.testing.assert_allclose(mirrored.min(axis=0), vertices.min(axis=0), atol=1e-8)
                    np.testing.assert_allclose(mirrored.max(axis=0), vertices.max(axis=0), atol=1e-8)

    def test_roof_opening_lining_has_four_solid_reveals_on_both_slopes(self) -> None:
        for dz in (2, -2):
            with self.subTest(dz=dz):
                house = House("Roof reveals", mirror_x=True)
                roof = house.storey("Upper floor", elevation=3).roof("Roof")
                slope = roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 4 + dz)))
                opening = roof.add_opening("Bedroom", rectangle=((2, 1), (3, 2)))
                outline = ((0, 0), (6, 0), (6, 6), (0, 6))
                bottom = slope.layer("Plasterboard", outline=outline, z_offset=-0.2,
                                     thickness=0.025, material="Gypsum plasterboard")
                tiles = slope.layer("Tiles", outline=outline, z_offset=0.5,
                                    thickness=0.03, material="Roof tiles")
                slope.add_window(opening, top_layer=tiles)
                panels = slope.add_opening_lining(opening, bottom_layer=bottom)
                self.assertEqual(panels, opening.lining)
                self.assertEqual(len(panels), 4)
                visibility = house.storey("Roof - plasterboard", elevation=3)
                visibility.add(*panels)
                settings = ifcopenshell.geom.settings()
                settings.set(settings.USE_WORLD_COORDS, True)
                volume = 0
                bounds = []
                vertices_by_id = {}
                for panel in panels:
                    self.assertEqual(panel.is_a(), "IfcCovering")
                    self.assertEqual(panel.PredefinedType, "CLADDING")
                    self.assertEqual(ifcopenshell.util.element.get_material(panel).Name, "Gypsum plasterboard")
                    self.assertEqual(ifcopenshell.util.element.get_container(panel), visibility.element)
                    # Re-applying registered openings must not eat their own reveals.
                    roof._apply_openings(panel, plane=slope)
                    self.assertFalse(panel.HasOpenings)
                    shape = ifcopenshell.geom.create_shape(settings, panel)
                    volume += ifcopenshell.util.shape.get_volume(shape.geometry)
                    vertices = np.array(shape.geometry.verts).reshape(-1, 3)
                    vertices_by_id[panel.GlobalId] = vertices
                    local = np.array([slope.to_local(tuple(v)) for v in vertices])
                    low, high = local.min(axis=0), local.max(axis=0)
                    self.assertAlmostEqual(low[2], bottom.z_offset + bottom.thickness - 0.001)
                    self.assertAlmostEqual(high[2], 0.43)
                    bounds.append((low, high))
                # Exactly a rectangular ring: no corner overlaps or missing panels.
                w, h, t = 1, np.sqrt(5) / 2, 0.0125
                expected_area = w * h - (w - 2 * t) * (h - 2 * t)
                self.assertAlmostEqual(volume, expected_area * (0.63 - 0.025 + 0.001))
                # Interior plasterboard now extends underneath the reveal ends.
                shape = ifcopenshell.geom.create_shape(settings, bottom)
                self.assertAlmostEqual(ifcopenshell.util.shape.get_volume(shape.geometry),
                                       (36 - (w - 2 * t) * (h - 2 * t)) * 0.025)
                interior_void = bottom.HasOpenings[0].RelatedOpeningElement
                self.assertAlmostEqual(ifcopenshell.util.element.get_pset(interior_void, "BBIM_RoofOpening", "LiningInset"), t)
                # Tiles keep their original larger hole and window filling.
                shape = ifcopenshell.geom.create_shape(settings, tiles)
                self.assertAlmostEqual(ifcopenshell.util.shape.get_volume(shape.geometry), (36 - w * h) * 0.03)
                self.assertEqual(len(tiles.HasOpenings[0].RelatedOpeningElement.HasFillings), 1)
                for index, (low, high) in enumerate(bounds):
                    for other_low, other_high in bounds[index + 1:]:
                        overlap = np.maximum(0, np.minimum(high, other_high) - np.maximum(low, other_low))
                        self.assertAlmostEqual(float(np.prod(overlap)), 0)
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "reveals.ifc"
                    house.write(path)
                    exported = ifcopenshell.open(path)
                    for panel in panels:
                        mirror_panel = exported.by_guid(panel.GlobalId)
                        self.assertFalse(mirror_panel.HasOpenings)
                        mirror_shape = ifcopenshell.geom.create_shape(settings, mirror_panel)
                        mirrored = np.array(mirror_shape.geometry.verts).reshape(-1, 3)
                        expected = vertices_by_id[panel.GlobalId].copy()
                        expected[:, 0] *= -1
                        np.testing.assert_allclose(mirrored.min(axis=0), expected.min(axis=0), atol=1e-8)
                        np.testing.assert_allclose(mirrored.max(axis=0), expected.max(axis=0), atol=1e-8)

    def test_plasterboard_reveals_use_light_elevation_outlines(self) -> None:
        stylesheet = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text()
        rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .IfcCovering.material-Gypsumplasterboard.cut,", 1
        )[1].split("}", 1)[0]
        self.assertIn(".IfcCovering.material-Gypsumplasterboard.projection", rule)
        self.assertIn("stroke-width: 0.05;", rule)

    def test_roof_opening_lining_validates_before_creating_panels(self) -> None:
        house = House("Roof reveals")
        roof = house.storey("Upper floor", elevation=3).roof("Roof")
        slope = roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 6)))
        other = roof.plane("Other", points=((0, 0, 4), (6, 0, 4), (0, 4, 2)))
        opening = roof.add_opening("Bedroom", rectangle=((2, 1), (3, 2)))
        foreign = house.storey("Other storey", elevation=0).roof("Other roof").add_opening(rectangle=((2, 1), (3, 2)))
        outline = ((0, 0), (6, 0), (6, 6), (0, 6))
        bottom = slope.layer("Plasterboard", outline=outline, thickness=0.025, material="Gypsum plasterboard")
        tiles = slope.layer("Tiles", outline=outline, z_offset=0.5, thickness=0.03, material="Roof tiles")
        other_bottom = other.layer("Other bottom", outline=outline, thickness=0.025, material="Gypsum plasterboard")
        distant = slope.layer("Distant", outline=((7, 0), (8, 0), (8, 1), (7, 1)), thickness=0.025, material="Gypsum plasterboard")
        with self.assertRaisesRegex(ValueError, "create the roof window"):
            slope.add_opening_lining(opening, bottom_layer=bottom)
        slope.add_window(opening, top_layer=tiles)
        for subject, options in ((foreign, {}), (opening, {"thickness": 0}),
                                 (opening, {"thickness": 0.5}), (opening, {"color": "invalid"}),
                                 (opening, {"bottom_overlap": -0.001}),
                                 (opening, {"bottom_overlap": 0.025}),
                                 (opening, {"bottom_layer": other_bottom}),
                                 (opening, {"bottom_layer": tiles}),
                                 (opening, {"bottom_layer": distant})):
            with self.subTest(options=options):
                count = len(list(house.model))
                with self.assertRaises(ValueError):
                    slope.add_opening_lining(subject, **({"bottom_layer": bottom} | options))
                self.assertEqual(len(list(house.model)), count)
                self.assertFalse(opening.lining)
        slope.add_opening_lining(opening, bottom_layer=bottom)
        with self.assertRaisesRegex(ValueError, "already has a lining"):
            slope.add_opening_lining(opening, bottom_layer=bottom)

    def test_roof_opening_lining_spans_adjacent_plasterboard_pieces(self) -> None:
        roof = House("Split finishes").storey("Upper floor", elevation=3).roof("Roof")
        slope = roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 6)))
        opening = roof.add_opening("Bedroom", rectangle=((2, 1), (3, 2)))
        left = slope.layer("Left", outline=((0, 0), (2.5, 0), (2.5, 6), (0, 6)),
                           thickness=0.025, material="Gypsum plasterboard")
        tiles = slope.layer("Tiles", outline=((0, 0), (6, 0), (6, 6), (0, 6)),
                            z_offset=0.5, thickness=0.03, material="Roof tiles")
        slope.add_window(opening, top_layer=tiles)
        with self.assertRaisesRegex(ValueError, "matching bottom-layer pieces"):
            slope.add_opening_lining(opening, bottom_layer=left)
        right = slope.layer("Right", outline=((2.5, 0), (6, 0), (6, 6), (2.5, 6)),
                            thickness=0.025, material="Gypsum plasterboard")
        self.assertEqual(len(slope.add_opening_lining(opening, bottom_layer=left)), 4)
        for layer in (left, right):
            void = layer.HasOpenings[0].RelatedOpeningElement
            self.assertEqual(ifcopenshell.util.element.get_pset(void, "BBIM_RoofOpening", "LiningInset"), 0.0125)

    def test_roof_window_rejects_invalid_parameters_without_mutation(self) -> None:
        house = House("Roof window")
        roof = house.storey("Upper floor", elevation=3).roof("Roof")
        slope = roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 6)))
        other = roof.plane("Other", points=((0, 0, 4), (6, 0, 4), (0, 4, 2)))
        opening = roof.add_opening("Bedroom", rectangle=((2, 1), (3, 2)))
        outline = ((0, 0), (6, 0), (6, 6), (0, 6))
        tiles = slope.layer("Tiles", outline=outline, z_offset=0.5, thickness=0.03, material="Roof tiles")
        other_tiles = other.layer("Other tiles", outline=outline, thickness=0.03, material="Roof tiles")
        distant = slope.layer("Distant", outline=((7, 0), (8, 0), (8, 1), (7, 1)), thickness=0.03, material="Roof tiles")
        for options in ({"frame_depth": 0}, {"frame_thickness": 0.6},
                        {"glass_transparency": 2}, {"color": "invalid"},
                        {"top_layer": other_tiles}, {"top_layer": distant}):
            with self.subTest(options=options):
                count = len(list(house.model))
                with self.assertRaises(ValueError):
                    slope.add_window(opening, **({"top_layer": tiles} | options))
                self.assertEqual(len(list(house.model)), count)
                self.assertIsNone(opening.window)
        slope.add_window(opening, top_layer=tiles)
        with self.assertRaisesRegex(ValueError, "already has a window"):
            slope.add_window(opening, top_layer=tiles)

    def test_roof_window_rejects_skewed_rectangle(self) -> None:
        roof = House("Roof window").storey("Upper floor", elevation=3).roof("Roof")
        slope = roof.plane("Oblique", points=((0, 0, 4), (6, 6, 4), (-4, 4, 6)))
        opening = roof.add_opening("Bedroom", rectangle=((0, 2), (1, 3)))
        tiles = slope.layer("Tiles", outline=((-5, -5), (10, -5), (10, 10), (-5, 10)), thickness=0.03, material="Roof tiles")
        with self.assertRaisesRegex(ValueError, "align with the roof-plane axes"):
            slope.add_window(opening, top_layer=tiles)

    def test_validates_absolute_xy_roof_openings(self) -> None:
        roof = House("My house").storey("Upper floor", elevation=3).roof(
            "Main roof"
        )
        with self.assertRaisesRegex(TypeError, "exactly two opposite corners"):
            roof.add_opening("Invalid", rectangle=((0, 0),))
        with self.assertRaisesRegex(ValueError, "non-zero width and depth"):
            roof.add_opening("Invalid", rectangle=((0, 0), (0, 1)))
        with self.assertRaisesRegex(TypeError, "trimmers must be a boolean"):
            roof.add_opening(
                "Invalid trimmers",
                rectangle=((0, 0), (1, 1)),
                trimmers="no",
            )

        roof.add_opening("First", rectangle=((0, 0), (1, 1)))
        with self.assertRaisesRegex(ValueError, "name already exists"):
            roof.add_opening("First", rectangle=((2, 2), (3, 3)))
        with self.assertRaisesRegex(ValueError, "overlaps another opening"):
            roof.add_opening("Overlapping", rectangle=((0.5, 0.5), (2, 2)))

        # Edge-touching roof windows are permitted.
        adjacent = roof.add_opening(
            rectangle=((1, 0), (2, 1)),
            trimmers=False,
        )
        self.assertEqual(adjacent.name, "Roof Opening 2")
        self.assertFalse(adjacent.trimmers)

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

    def test_calculates_combined_nominal_window_and_glazed_door_area(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=3)
        window = wall.add_window(
            at=0.5,
            width=1.5,
            sill_height=0.9,
            height=2.4,
        )
        glazed_door = wall.add_door(
            at=2.5,
            width=0.8,
            sill_height=0.5,
            height=2.5,
        )

        self.assertAlmostEqual(window_area(window), 2.25)
        self.assertAlmostEqual(window_area(window, glazed_door), 3.85)
        self.assertEqual(window_area(), 0)
        with self.assertRaisesRegex(TypeError, "must be an IfcWindow or IfcDoor"):
            window_area(wall)

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
            scaled_toilet = ground.asset(
                "Scaled WC",
                asset="wc",
                center=(4, 3),
                size=(0.8, 0.3),
                rotation=90,
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
            self.assertEqual(
                ifcopenshell.util.element.get_type(scaled_toilet),
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
            scaled_shape = ifcopenshell.geom.create_shape(settings, scaled_toilet)
            scaled_vertices = scaled_shape.geometry.verts
            scaled_points = tuple(
                zip(
                    scaled_vertices[::3],
                    scaled_vertices[1::3],
                    scaled_vertices[2::3],
                )
            )
            self.assertAlmostEqual(
                max(point[0] for point in scaled_points)
                - min(point[0] for point in scaled_points),
                0.3,
            )
            self.assertAlmostEqual(
                max(point[1] for point in scaled_points)
                - min(point[1] for point in scaled_points),
                0.8,
            )
            self.assertAlmostEqual(
                max(point[2] for point in scaled_points)
                - min(point[2] for point in scaled_points),
                0.8,
            )
            scaled_targets = [
                item.MappingTarget
                for representation in scaled_toilet.Representation.Representations
                for item in representation.Items
                if item.is_a("IfcMappedItem")
            ]
            self.assertEqual(len(scaled_targets), 2)
            self.assertTrue(
                all(
                    target.is_a(
                        "IfcCartesianTransformationOperator3DnonUniform"
                    )
                    for target in scaled_targets
                )
            )
            self.assertTrue(all(target.Scale == 2 for target in scaled_targets))
            self.assertTrue(
                all(target.Scale2 == 0.5 for target in scaled_targets)
            )
            self.assertTrue(all(target.Scale3 == 1 for target in scaled_targets))
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
            with self.assertRaisesRegex(TypeError, "exactly two dimensions"):
                ground.asset(
                    "Bad size",
                    asset="toilet_with_cistern",
                    center=(0, 0),
                    size=(1,),
                )
            with self.assertRaisesRegex(ValueError, "greater than zero"):
                ground.asset(
                    "Bad size",
                    asset="toilet_with_cistern",
                    center=(0, 0),
                    size=(1, 0),
                )

    def test_creates_a_cylinder_with_body_geometry_and_material(self) -> None:
        house = House("My house", colors={"cylinder": "#8090A0"})
        ground = house.storey("Ground floor", elevation=0.25)
        cylinder = ground.cylinder(
            center=(2, 3),
            radius=0.2,
            height=1.4,
            start_height=0.1,
            material="Steel",
            name="Round column",
        )

        self.assertTrue(cylinder.is_a("IfcBuildingElementProxy"))
        self.assertEqual(cylinder.Name, "Round column")
        self.assertEqual(cylinder.PredefinedType, "USERDEFINED")
        self.assertEqual(cylinder.ObjectType, "CYLINDER")
        self.assertEqual(
            cylinder.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_material(cylinder).Name,
            "Steel",
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            cylinder.ObjectPlacement
        )
        np.testing.assert_allclose(placement[:3, 3], (2, 3, 0.35))

        body = ifcopenshell.util.representation.get_representation(
            cylinder, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "SweptSolid")
        self.assertTrue(body.Items[0].SweptArea.is_a("IfcCircleProfileDef"))
        self.assertAlmostEqual(body.Items[0].SweptArea.Radius, 0.2)
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), cylinder
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(shape.geometry), 0.4, delta=0.001
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(shape.geometry), 0.4, delta=0.001
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_z(shape.geometry), 1.4)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            np.pi * 0.2**2 * 1.4,
            delta=0.002,
        )

        self.assertIsNone(
            ifcopenshell.util.representation.get_representation(
                cylinder, "Plan", "Body", "PLAN_VIEW"
            )
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                cylinder, "BBIM_Cylinder", "Radius"
            ),
            0.2,
        )
        self.assert_surface_style(cylinder, (128 / 255, 144 / 255, 160 / 255))

    def test_rejects_invalid_cylinders(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)

        with self.assertRaisesRegex(ValueError, "radius"):
            ground.cylinder(center=(0, 0), radius=0, height=1)
        with self.assertRaisesRegex(ValueError, "height"):
            ground.cylinder(center=(0, 0), radius=1, height=0)
        with self.assertRaisesRegex(ValueError, "start_height"):
            ground.cylinder(
                center=(0, 0), radius=1, height=1, start_height=-0.1
            )
        with self.assertRaisesRegex(ValueError, "material must not be empty"):
            ground.cylinder(
                center=(0, 0), radius=1, height=1, material=""
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

    def test_adds_furniture_label_to_an_existing_elevation_drawing(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        elevation = house.add_drawing(
            "Interior elevation",
            0,
            -1,
            1.5,
            4,
            view="elevation",
            direction=(0, 1, 0),
            storeys=[ground],
        )

        stove = ground.furniture(
            "Kamna",
            kind="USERDEFINED",
            size=(0.6, 0.5, 1.5),
            center=(2, 2),
            start_height=0.1,
        )

        self.assertIs(elevation.include_element(stove), elevation)
        self.assertFalse(
            any(
                "furniture-elevation-label"
                in (
                    ifcopenshell.util.element.get_pset(
                        annotation, "EPset_Annotation", "Classes"
                    )
                    or ""
                ).split()
                for annotation in house.model.by_type("IfcAnnotation")
            )
        )
        elevation_label = elevation.add_furniture_label(stove)
        self.assertIs(elevation.add_furniture_label(stove), elevation_label)
        elevation_labels = [
            annotation
            for annotation in elevation.group.IsGroupedBy[0].RelatedObjects
            if "furniture-elevation-label"
            in (
                ifcopenshell.util.element.get_pset(
                    annotation, "EPset_Annotation", "Classes"
                )
                or ""
            ).split()
        ]
        self.assertEqual(len(elevation_labels), 1)
        literal = (
            elevation_labels[0].Representation.Representations[0].Items[0]
        )
        self.assertEqual(literal.Literal, "Kamna")
        self.assertIn(
            f"furniture-owner-{stove.GlobalId}",
            ifcopenshell.util.element.get_pset(
                elevation_labels[0], "EPset_Annotation", "Classes"
            ).split(),
        )
        self.assertTrue(
            ifcopenshell.util.element.get_pset(
                elevation.element, "EPset_Drawing", "HasAnnotation"
            )
        )
        self.assertEqual(
            sum(
                "furniture-elevation-label"
                in (
                    ifcopenshell.util.element.get_pset(
                        annotation, "EPset_Annotation", "Classes"
                    )
                    or ""
                ).split()
                for annotation in elevation.group.IsGroupedBy[0].RelatedObjects
            ),
            1,
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
        with patch("builtins.print") as print_mock:
            stair = ground.stair(
                (2, 1),
                (5, 1),
                width=0.9,
                height=2.75,
                risers=16,
                name="Main stair",
            )

        self.assertEqual(
            print_mock.call_args_list,
            [
                call("Main stair step height: 0.172 m (17.19 cm)"),
                call("Main stair step width: 0.200 m (20.00 cm)"),
            ],
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
        self.assertEqual(stair.construction, "monolithic")
        self.assertEqual(stair.underside, "solid")
        self.assertEqual(stair.slab_height, stair.start_height)
        self.assertIsNone(stair.tread_thickness)
        self.assertIsNone(stair.stringer_thickness)
        self.assertIsNone(stair.stringer_height)
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
        # Outline + one line per internal tread; no per-flight walking arrow
        # or zigzag stair break symbol.
        self.assertEqual(len(curve_set.Elements), stair.treads)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            ),
            "stair dashed",
        )
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

    def test_stair_annotation_keeps_outline_and_treads_without_per_flight_arrow(self) -> None:
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Stair route", mirror_x=mirror)
                ground = house.storey("Ground", elevation=0)
                with patch("builtins.print"):
                    stair = ground.stair((1, 2), (1, 4.7), width=1, height=1.9,
                                         risers=11, construction="timber")
                drawing = house.add_drawing("Plan", 1, 3, 1.6, 5)
                annotation = drawing.add_stair_annotation(stair)
                curves = annotation.Representation.Representations[0].Items[0].Elements
                self.assertEqual(len(curves), stair.treads)
                self.assertEqual(curves[0].Points.CoordList,
                                 ((0., -.5), (stair.length, -.5), (stair.length, .5),
                                  (0., .5), (0., -.5)))
                for index, curve in enumerate(curves[1:], start=1):
                    points = curve.Points.CoordList
                    self.assertEqual(len(points), 2)
                    self.assertAlmostEqual(points[0][0], index * stair.tread_length)
                    self.assertEqual(points[0][0], points[1][0])
                    self.assertEqual((points[0][1], points[1][1]), (-.5, .5))
                exported = house._export_model().by_guid(annotation.GlobalId)
                resolved = ifcopenshell.util.representation.resolve_items(exported.Representation.Representations[0])
                self.assertEqual(sum(len(item["item"].Elements) for item in resolved), stair.treads)

    def test_creates_open_timber_stair_between_side_stringers(self) -> None:
        house = House("My house", colors={"stair": "#C8B090"})
        ground = house.storey("Ground floor", elevation=0)
        stair = ground.stair(
            (0, 0),
            (3, 0),
            width=0.9,
            height=2.75,
            risers=16,
            construction="timber",
            tread_thickness=0.04,
            stringer_thickness=0.05,
            stringer_height=0.30,
        )

        self.assertEqual(stair.construction, "timber")
        self.assertEqual(stair.underside, "open")
        self.assertIsNone(stair.waist_thickness)
        self.assertAlmostEqual(stair.tread_thickness, 0.04)
        self.assertAlmostEqual(stair.stringer_thickness, 0.05)
        self.assertAlmostEqual(stair.stringer_height, 0.30)
        self.assertEqual(
            ifcopenshell.util.element.get_material(stair.flight).Name,
            "Wood",
        )

        body = ifcopenshell.util.representation.get_representation(
            stair.flight, "Model", "Body", "MODEL_VIEW"
        )
        self.assertEqual(body.RepresentationType, "Tessellation")
        coordinates = body.Items[0].Coordinates.CoordList
        y_coordinates = [coordinate[1] for coordinate in coordinates]
        self.assertAlmostEqual(min(y_coordinates), -0.45)
        self.assertAlmostEqual(max(y_coordinates), 0.45)
        self.assertTrue(
            any(abs(coordinate[1] + 0.40) < 1e-9 for coordinate in coordinates)
        )
        self.assertTrue(
            any(abs(coordinate[1] - 0.40) < 1e-9 for coordinate in coordinates)
        )

        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), stair.flight
        )
        self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), 3)
        self.assertAlmostEqual(ifcopenshell.util.shape.get_y(shape.geometry), 0.9)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(shape.geometry), 2.75
        )

        # The individual tread shells leave open risers, so the timber flight
        # occupies much less material than its full bounding box.
        bounding_box_volume = 3 * 0.9 * 2.75
        self.assertLess(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            bounding_box_volume / 3,
        )

    def test_creates_custom_stair_from_explicit_step_polygons(self) -> None:
        house = House("My house", colors={"stair": "#C8B090"})
        ground = house.storey("Ground floor", elevation=0.1)
        upper = house.storey("Upper floor", elevation=3)
        step_polygons = (
            ((0, 0), (1, 0), (1, 0.3), (0, 0.3)),
            ((0, 0.3), (1, 0.3), (1, 0.6), (0, 0.6)),
            ((0.7, 0.6), (1, 0.6), (1, 1.6), (0.7, 1.6)),
        )
        with patch("builtins.print") as print_mock:
            stair = ground.custom_stair(
                step_polygons,
                start_height=0.25,
                height=0.6,
                tread_thickness=0.04,
                name="Turning stair",
            )

        self.assertIsInstance(stair, CustomStair)
        self.assertTrue(stair.is_a("IfcStair"))
        self.assertIs(stair.element, stair)
        self.assertEqual(stair.PredefinedType, "USERDEFINED")
        self.assertEqual(stair.ObjectType, "CUSTOM_STAIR")
        self.assertEqual(stair.steps, 3)
        self.assertEqual(stair.risers, 3)
        self.assertEqual(stair.treads, 3)
        self.assertAlmostEqual(stair.start_height, 0.25)
        self.assertAlmostEqual(stair.end_height, 0.85)
        self.assertAlmostEqual(stair.step_height, 0.15)
        self.assertAlmostEqual(stair.tread_thickness, 0.04)
        self.assertEqual(stair.construction, "custom")
        self.assertEqual(stair.underside, "open")
        print_mock.assert_called_once_with(
            "Turning stair step height: 0.150 m (15.00 cm)"
        )

        flight = stair.flight
        self.assertEqual(flight.PredefinedType, "USERDEFINED")
        self.assertEqual(flight.ObjectType, "FREEFORM_TREADS")
        self.assertEqual(flight.NumberOfRisers, 3)
        self.assertEqual(flight.NumberOfTreads, 3)
        self.assertAlmostEqual(flight.RiserHeight, 0.15)
        self.assertIsNone(flight.TreadLength)
        self.assertEqual(
            ifcopenshell.util.element.get_material(flight).Name,
            "Wood",
        )
        self.assertEqual(
            flight.Decomposes[0].RelatingObject,
            stair,
        )

        placement = ifcopenshell.util.placement.get_local_placement(
            flight.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 0.35)
        self.assertIsNone(flight.Representation)
        self.assertEqual(len(stair.tread_elements), 3)
        self.assertEqual(stair.components, stair.tread_elements)
        expected_bottoms = (0.46, 0.61, 0.76)
        total_volume = 0.0
        for index, (tread, expected_bottom) in enumerate(
            zip(stair.tread_elements, expected_bottoms),
            start=1,
        ):
            self.assertTrue(tread.is_a("IfcBuildingElementPart"))
            self.assertEqual(tread.Name, f"Turning stair Tread {index}")
            self.assertEqual(tread.PredefinedType, "USERDEFINED")
            self.assertEqual(tread.ObjectType, "STAIR_TREAD")
            self.assertEqual(tread.Decomposes[0].RelatingObject, flight)
            self.assertEqual(
                ifcopenshell.util.element.get_material(tread).Name,
                "Wood",
            )
            tread_placement = ifcopenshell.util.placement.get_local_placement(
                tread.ObjectPlacement
            )
            self.assertAlmostEqual(tread_placement[2, 3], expected_bottom)
            body = ifcopenshell.util.representation.get_representation(
                tread,
                "Model",
                "Body",
                "MODEL_VIEW",
            )
            self.assertEqual(body.RepresentationType, "Tessellation")
            coordinates = body.Items[0].Coordinates.CoordList
            self.assertEqual(len(coordinates), 8)
            self.assertEqual(
                {round(point[2], 9) for point in coordinates},
                {0.0, 0.04},
            )
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(),
                tread,
            )
            total_volume += ifcopenshell.util.shape.get_volume(shape.geometry)
            self.assert_surface_style(
                tread,
                (200 / 255, 176 / 255, 144 / 255),
            )
        self.assertAlmostEqual(total_volume, 3 * 0.3 * 0.04)

        drawing = house.add_drawing(
            "Upper plan",
            0.5,
            0.8,
            4.5,
            3,
            storeys=[upper],
        )
        annotation = drawing.add_stair_annotation(stair)
        curves = annotation.Representation.Representations[0].Items[0].Elements
        self.assertEqual(len(curves), 3)
        self.assertTrue(
            all(len(curve.Points.CoordList) == 5 for curve in curves)
        )
        include = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
            "Include",
        )
        included_ids = {
            selector.strip() for selector in include.split("+")
        }
        self.assertTrue(
            all(tread.GlobalId in included_ids for tread in stair.tread_elements)
        )
        self.assertNotIn(stair.flight.GlobalId, included_ids)

    def test_rejects_invalid_custom_stairs(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        valid_step = ((0, 0), (1, 0), (1, 0.3), (0, 0.3))

        with self.assertRaisesRegex(ValueError, "at least one step"):
            ground.custom_stair((), height=1)
        with self.assertRaisesRegex(ValueError, "exactly four points"):
            ground.custom_stair((valid_step[:3],), height=1)
        with self.assertRaisesRegex(ValueError, "distinct points"):
            ground.custom_stair(
                (((0, 0), (1, 0), (1, 0.3), (1, 0.3)),),
                height=1,
            )
        with self.assertRaisesRegex(ValueError, "non-zero area"):
            ground.custom_stair(
                (((0, 0), (1, 0), (2, 0), (3, 0)),),
                height=1,
            )
        with self.assertRaisesRegex(ValueError, "height"):
            ground.custom_stair((valid_step,), height=0)
        with self.assertRaisesRegex(ValueError, "tread_thickness"):
            ground.custom_stair(
                (valid_step, valid_step),
                height=0.08,
                tread_thickness=0.04,
            )

    def test_extends_timber_stringers_into_landing_slab(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        stair = ground.stair(
            (0, 0),
            (3, 0),
            width=0.9,
            height=2.75,
            risers=16,
            start_height=1.0,
            slab_height=0.8,
            construction="timber",
            stringer_height=0.3,
        )

        self.assertAlmostEqual(stair.start_height, 1.0)
        self.assertAlmostEqual(stair.slab_height, 0.8)
        body = ifcopenshell.util.representation.get_representation(
            stair.flight, "Model", "Body", "MODEL_VIEW"
        )
        coordinates = body.Items[0].Coordinates.CoordList
        self.assertAlmostEqual(min(point[2] for point in coordinates), -0.2)

        placement = ifcopenshell.util.placement.get_local_placement(
            stair.flight.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 1.0)
        self.assertAlmostEqual(
            placement[2, 3] + min(point[2] for point in coordinates),
            stair.slab_height,
        )

    def test_includes_cross_storey_stair_geometry_in_plan(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        stair = ground.stair(
            (0, 0),
            (3, 0),
            width=0.9,
            height=3,
            risers=16,
            construction="timber",
        )
        landing = ground.stair_landing(
            (3, -0.45),
            (4, 0.45),
            height=3,
            thickness=0.2,
        )
        upper_wall = upper.wall(
            (0, 1),
            (1, 1),
            thickness=0.2,
            height=2.8,
        )
        drawing = house.add_drawing(
            "Upper plan",
            2,
            0,
            4.5,
            4,
            storeys=[upper],
        )

        drawing.add_stair_annotation(stair)
        drawing.add_stair_landing_annotation(landing)

        include = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
            "Include",
        )
        self.assertEqual(
            include,
            (
                f'location="{upper.element.GlobalId}"'
                f" + {stair.flight.GlobalId} + {landing.GlobalId}"
            ),
        )
        selected_elements = ifcopenshell.util.selector.filter_elements(
            house.model,
            include,
        )
        self.assertIn(stair.flight, selected_elements)
        self.assertIn(landing, selected_elements)
        self.assertIn(upper_wall, selected_elements)

    def test_creates_chimney_with_flue_and_scoped_plan_symbol(self) -> None:
        house = House("My house", colors={"chimney": "#B8A99A"})
        ground = house.storey("Ground floor", elevation=0.25)
        chimney = ground.chimney(
            (2, 3),
            size=0.5,
            height=6.5,
            flue_diameter=0.18,
            start_height=0.1,
            material="Chimney masonry",
            name="Main chimney",
        )

        self.assertIsInstance(chimney, Chimney)
        self.assertTrue(chimney.is_a("IfcChimney"))
        self.assertIs(chimney.element, chimney)
        self.assertEqual(chimney.PredefinedType, "NOTDEFINED")
        self.assertEqual(chimney.center, (2, 3))
        self.assertEqual(chimney.end_height, 6.6)
        self.assertEqual(
            ifcopenshell.util.element.get_material(chimney).Name,
            "Chimney masonry",
        )
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
            f'location="{upper.element.GlobalId}" + {chimney.GlobalId}',
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
            self.assertEqual(
                ifcopenshell.util.element.get_material(
                    reopened.by_type("IfcChimney")[0]
                ).Name,
                "Chimney masonry",
            )

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
        with self.assertRaisesRegex(ValueError, "material must not be empty"):
            ground.chimney(
                (0, 0),
                size=0.5,
                height=5,
                flue_diameter=0.18,
                material="",
            )

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

        with self.assertRaisesRegex(ValueError, "construction"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                construction="steel",
            )
        with self.assertRaisesRegex(ValueError, "slab_height"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                start_height=1.0,
                slab_height=1.1,
                construction="timber",
            )
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
        with self.assertRaisesRegex(ValueError, "tread_thickness"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                construction="timber",
                tread_thickness=0,
            )
        with self.assertRaisesRegex(ValueError, "stringer_thickness"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                construction="timber",
                stringer_thickness=0.45,
            )
        with self.assertRaisesRegex(ValueError, "stringer_height"):
            ground.stair(
                (0, 0),
                (3, 0),
                width=0.9,
                height=2.75,
                risers=16,
                construction="timber",
                stringer_height=0,
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

        drawing = house.add_drawing("Upper plan", 0, 0, 3.5, 5)
        other_drawing = house.add_drawing("Other plan", 0, 0, 3.5, 5)
        annotation = drawing.add_stair_landing_annotation(landing)
        self.assertEqual(annotation.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            ),
            "stair-landing dashed",
        )
        outline = annotation.Representation.Representations[0].Items[0].Elements[0]
        self.assertEqual(
            outline.Points.CoordList,
            ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0), (0.0, 0.0)),
        )
        annotation_placement = ifcopenshell.util.placement.get_local_placement(
            annotation.ObjectPlacement
        )
        np.testing.assert_allclose(annotation_placement, landing_placement)
        self.assertIn(
            annotation,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertEqual(
            set(other_drawing.group.IsGroupedBy[0].RelatedObjects),
            {other_drawing.element},
        )
        with self.assertRaisesRegex(ValueError, "already has"):
            drawing.add_stair_landing_annotation(landing)
        with self.assertRaisesRegex(TypeError, "IfcSlab"):
            drawing.add_stair_landing_annotation(lower)
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
        with patch("builtins.print") as print_mock:
            slab = upper.miako_slab(
                "Ground-floor ceiling",
                start=(0, 0),
                end=(0, 8),
                top=0,
                direction=(1, 0),
                structure=["wide", "beam", "narrow", "beam"],
                expected_width=1.125,
            )
        print_mock.assert_not_called()

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
        self.assertAlmostEqual(slab.width_before_axis, 0)
        self.assertAlmostEqual(slab.width_after_axis, 1.125)
        self.assertAlmostEqual(slab.expected_width, 1.125)
        self.assertAlmostEqual(slab.block_start_offset, 0)
        self.assertAlmostEqual(slab.block_end_offset, 0)
        self.assertEqual(
            slab.footprint,
            ((0, 0), (0, 8), (1.125, 8.0), (1.125, 0.0)),
        )
        self.assertEqual(
            slab.beam_centerlines,
            (
                ((0.54, 0.0), (0.54, 8.0)),
                ((1.04, 0.0), (1.04, 8.0)),
            ),
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
        self.assertEqual(len(reinforcement_body.Items), 5)
        wire_profiles = [
            item.SweptArea.OuterCurve.Points.CoordList
            for item in reinforcement_body.Items[:2]
        ]
        for wire_profile, expected_bottom, expected_top in zip(
            wire_profiles,
            ((-0.061, 0.04), (-0.109, 0.04)),
            ((-0.079, 0.175), (-0.091, 0.175)),
        ):
            np.testing.assert_allclose(
                np.mean((wire_profile[0], wire_profile[3]), axis=0),
                expected_bottom,
                atol=1e-9,
            )
            np.testing.assert_allclose(
                np.mean((wire_profile[1], wire_profile[2]), axis=0),
                expected_top,
                atol=1e-9,
            )
        reinforcement_dots = [
            item.SweptArea.OuterCurve
            for item in reinforcement_body.Items[2:]
        ]
        self.assertTrue(
            all(dot.is_a("IfcCircle") for dot in reinforcement_dots)
        )
        for dot, (expected_y, expected_z) in zip(
            reinforcement_dots,
            ((-0.055, 0.04), (-0.115, 0.04), (-0.085, 0.175)),
        ):
            dot_y, dot_z = dot.Position.Location.Coordinates
            self.assertAlmostEqual(dot_y, expected_y)
            self.assertAlmostEqual(dot_z, expected_z)
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

    def test_places_miako_layout_items_on_both_sides_of_an_axis(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Two-sided ceiling",
            start=(1, 2),
            end=(5, 2),
            top=0,
            direction=(0, 1),
            structure=[
                "beam",
                "wide",
                "beam",
                "axis",
                "beam",
                "narrow",
                "beam",
            ],
            expected_width=1.465,
        )

        self.assertEqual(
            slab.structure,
            ("beam", "wide", "beam", "axis", "beam", "narrow", "beam"),
        )
        self.assertAlmostEqual(slab.width_before_axis, 0.795)
        self.assertAlmostEqual(slab.width_after_axis, 0.67)
        self.assertAlmostEqual(slab.width, 1.465)
        np.testing.assert_allclose(
            slab.footprint,
            (
                (1.0, 1.205),
                (5.0, 1.205),
                (5.0, 2.67),
                (1.0, 2.67),
            ),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            slab.beam_centerlines,
            (
                ((1.0, 1.29), (5.0, 1.29)),
                ((1.0, 1.915), (5.0, 1.915)),
                ((1.0, 2.085), (5.0, 2.085)),
                ((1.0, 2.585), (5.0, 2.585)),
            ),
            atol=1e-9,
        )

        plan = ifcopenshell.util.representation.get_representation(
            slab, "Plan", "Body", "PLAN_VIEW"
        )
        np.testing.assert_allclose(
            plan.Items[0].Points.CoordList,
            (
                (0.0, -0.795),
                (4.0, -0.795),
                (4.0, 0.67),
                (0.0, 0.67),
                (0.0, -0.795),
            ),
            atol=1e-9,
        )
        beam_origins = [
            ifcopenshell.util.placement.get_local_placement(
                beam.ObjectPlacement
            )[:2, 3]
            for beam in slab.beams
        ]
        np.testing.assert_allclose(
            beam_origins,
            ((1.0, 1.205), (1.0, 1.83), (1.0, 2.0), (1.0, 2.5)),
            atol=1e-9,
        )

        miako_properties = ifcopenshell.util.element.get_pset(
            slab,
            "BBIM_MiakoSlab",
        )
        self.assertEqual(
            miako_properties["Structure"],
            "beam,wide,beam,axis,beam,narrow,beam",
        )
        self.assertAlmostEqual(miako_properties["WidthBeforeAxis"], 0.795)
        self.assertAlmostEqual(miako_properties["WidthAfterAxis"], 0.67)

        topping_body = ifcopenshell.util.representation.get_representation(
            slab.topping_element, "Model", "Body", "MODEL_VIEW"
        )
        profile = topping_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        self.assertTrue(
            any(np.allclose(point, (-0.135, 0.06)) for point in profile)
        )
        self.assertTrue(
            any(np.allclose(point, (0.135, 0.06)) for point in profile)
        )
        self.assertNotIn((0.0, 0.19), profile)

        with self.assertRaisesRegex(ValueError, "at most one axis"):
            upper.miako_slab(
                "Invalid axes",
                start=(0, 0),
                end=(2, 0),
                top=0,
                direction=(0, 1),
                structure=["beam", "axis", "wide", "axis", "beam"],
            )

    def test_insets_miako_blocks_from_both_beam_ends(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Inset blocks",
            start=(1, 2),
            end=(2.2, 2),
            top=0,
            direction=(0, 1),
            structure=["beam", "wide", "beam"],
            block_start_offset=0.1,
            block_end_offset=0.15,
        )

        self.assertAlmostEqual(slab.length, 1.2)
        self.assertAlmostEqual(slab.block_start_offset, 0.1)
        self.assertAlmostEqual(slab.block_end_offset, 0.15)
        self.assertEqual(len(slab.blocks), 4)
        block_origins = [
            ifcopenshell.util.placement.get_local_placement(
                block.ObjectPlacement
            )[0, 3]
            for block in slab.blocks
        ]
        np.testing.assert_allclose(
            block_origins,
            (1.1, 1.35, 1.6, 1.85),
            atol=1e-9,
        )
        block_lengths = [
            ifcopenshell.util.shape.get_x(
                ifcopenshell.geom.create_shape(
                    ifcopenshell.geom.settings(),
                    block,
                ).geometry
            )
            for block in slab.blocks
        ]
        np.testing.assert_allclose(
            block_lengths,
            (0.25, 0.25, 0.25, 0.2),
            atol=1e-9,
        )
        self.assertAlmostEqual(
            block_origins[-1] + block_lengths[-1],
            2.05,
        )
        properties = ifcopenshell.util.element.get_pset(
            slab,
            "BBIM_MiakoSlab",
        )
        self.assertAlmostEqual(properties["BlockStartOffset"], 0.1)
        self.assertAlmostEqual(properties["BlockEndOffset"], 0.15)

        valid_arguments = {
            "start": (0, 0),
            "end": (1.2, 0),
            "top": 0,
            "direction": (0, 1),
            "structure": ["beam", "wide"],
        }
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            upper.miako_slab(
                "Invalid offset",
                **valid_arguments,
                block_start_offset=-0.1,
            )
        with self.assertRaisesRegex(ValueError, "less than the beam length"):
            upper.miako_slab(
                "No block run",
                **valid_arguments,
                block_start_offset=0.6,
                block_end_offset=0.6,
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
            0.175 + 0.006 - (0.04 - 0.006),
            places=3,
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
        with patch("builtins.print") as print_mock:
            mismatched = upper.miako_slab(
                "Unexpected width",
                **valid_arguments,
                expected_width=1,
            )
        self.assertAlmostEqual(mismatched.width, 0.625)
        self.assertEqual(mismatched.expected_width, 1)
        print_mock.assert_called_once_with(
            "WARNING: MIAKO slab 'Unexpected width' width is 0.625 m; "
            "expected 1 m"
        )
        with self.assertRaisesRegex(ValueError, "expected_width"):
            upper.miako_slab(
                "Invalid", **valid_arguments, expected_width=0
            )
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
        with self.assertRaisesRegex(ValueError, "upper reinforcement bar"):
            upper.miako_slab(
                "Invalid",
                **valid_arguments,
                block_height=0.1,
                topping=0.07,
                beam_height=0.06,
            )

    def test_fills_concrete_cover_at_edge_and_consecutive_miako_beams(
        self,
    ) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Ceiling with grouped beams",
            start=(0, 0),
            end=(4, 0),
            top=0,
            direction=(0, 1),
            structure=[
                "beam",
                "wide",
                "beam",
                "beam",
                "narrow",
                "beam",
            ],
        )

        topping_body = ifcopenshell.util.representation.get_representation(
            slab.topping_element, "Model", "Body", "MODEL_VIEW"
        )
        profile = topping_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        np.testing.assert_allclose(
            profile[:13],
            (
                (0.0, 0.19),
                (0.0, 0.06),
                (0.135, 0.06),
                (0.135, 0.19),
                (0.66, 0.19),
                (0.66, 0.06),
                (0.93, 0.06),
                (0.93, 0.19),
                (1.33, 0.19),
                (1.33, 0.06),
                (1.465, 0.06),
                (1.465, 0.19),
                (1.465, 0.25),
            ),
            atol=1e-9,
        )
        self.assertNotIn((0.035, 0.06), profile)
        self.assertNotIn((0.795, 0.19), profile)
        self.assertNotIn((1.43, 0.06), profile)

    def test_adds_a_regular_vertical_frame_from_a_storey_relative_height(
        self,
    ) -> None:
        house = House("My house")
        wall_type = house.wall_type(
            "Exterior wall", layers=[("Brick", 0.25), "axis"]
        )
        ground = house.storey("Ground floor", elevation=0.5)
        wall = ground.wall(
            (1, 2),
            (6, 2),
            wall_type=wall_type,
            start_height=0.25,
            height=3,
        )

        frame = house.add_vertical_frame(
            wall,
            side="right",
            offset=0.1,
            width=0.04,
            depth=0.06,
            start_height=0.75,
            height=2,
            gap=0.4,
            lath_offsets=[1, 2, 3],
        )

        self.assertIsInstance(frame, VerticalFrame)
        self.assertTrue(frame.is_a("IfcElementAssembly"))
        self.assertEqual(frame.ObjectType, "FACADE_VERTICAL_FRAME")
        self.assertEqual(frame.start_height, 0.75)
        self.assertEqual(frame.gap, 0.4)
        self.assertEqual(frame.lath_offsets, (1, 2, 3))
        np.testing.assert_allclose(
            frame.lath_positions,
            (1, 1.44, 1.88, 2, 2.44, 2.88, 3),
            atol=1e-9,
        )
        self.assertEqual(len(frame.members), 7)
        self.assertEqual(
            frame.ContainedInStructure[0].RelatingStructure, ground.element
        )
        self.assertEqual(
            set(frame.IsDecomposedBy[0].RelatedObjects), set(frame.members)
        )

        expected_x = (2.02, 2.46, 2.9, 3.02, 3.46, 3.9, 4.02)
        for member, x in zip(frame.members, expected_x):
            self.assertTrue(member.is_a("IfcMember"))
            self.assertEqual(member.PredefinedType, "STUD")
            self.assertEqual(member.ObjectType, "FACADE_LATH")
            placement = ifcopenshell.util.placement.get_local_placement(
                member.ObjectPlacement
            )
            np.testing.assert_allclose(
                placement[:3, 3], (x, 1.87, 1.25), atol=1e-9
            )
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_volume(shape.geometry),
                2 * 0.04 * 0.06,
            )
            self.assertEqual(
                ifcopenshell.util.element.get_material(member).Name, "Wood"
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    member, "Pset_MemberCommon", "LoadBearing"
                ),
                False,
            )

        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_VerticalFrame", "StartHeight"
            ),
            0.75,
        )
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    frame, "BBIM_VerticalFrame", "LathPositions"
                )
            ),
            [1, 1.44, 1.88, 2, 2.44, 2.88, 3],
        )
        facade_storey = house.storey("Facade - +0: Frame", elevation=0)
        facade_storey.element.ObjectType = "FACADE_LAYER"
        facade_storey.add(frame)
        self.assertEqual(
            frame.ContainedInStructure[0].RelatingStructure,
            facade_storey.element,
        )
        self.assertEqual(frame.members[0].Decomposes[0].RelatingObject, frame)

    def test_adds_one_opening_aware_facade_covering(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.5)
        wall = ground.wall(
            (1, 2),
            (5, 2),
            thickness=0.2,
            start_height=0.25,
            height=3,
        )
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2.5)

        layer = house.add_facade_layer(
            wall,
            offset=0.1,
            thickness=0.01,
            start_extension=0.2,
            end_extension=0.3,
            space_before_openings=0.1,
            space_after_openings=0.2,
            space_above_openings=0.3,
            space_below_openings=0.4,
        )

        self.assertIsInstance(layer, FacadeLayer)
        self.assertTrue(layer.is_a("IfcCovering"))
        self.assertEqual(layer.PredefinedType, "CLADDING")
        self.assertEqual(layer.ObjectType, "FACADE_CLADDING")
        self.assertEqual(layer.material_name, "Cementovlaknita deska")
        self.assertEqual(layer.length, 4.5)
        self.assertEqual(layer.start_height, 0.25)
        self.assertEqual(layer.height, 3)
        self.assertEqual(len(layer.openings), 1)
        self.assertEqual(len(layer.HasOpenings), 1)
        self.assertEqual(layer.openings[0].VoidsElements[0].RelatingBuildingElement, layer)
        self.assertEqual(
            ifcopenshell.util.element.get_material(layer).Name,
            "Cementovlaknita deska",
        )
        self.assertEqual(
            layer.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), layer)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            (4.5 * 3 - 0.8 * 2.55) * 0.01,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                layer, "BBIM_FacadeLayer", "SpaceBeforeOpenings"
            ),
            0.1,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                layer, "BBIM_FacadeLayer", "SpaceAfterOpenings"
            ),
            0.2,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                layer, "BBIM_FacadeLayer", "SpaceAboveOpenings"
            ),
            0.3,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                layer, "BBIM_FacadeLayer", "SpaceBelowOpenings"
            ),
            0.4,
        )

    def test_projects_aligned_upper_wall_openings_into_one_facade_layer(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        host = ground.wall((0, 0), (4, 0), thickness=0.2, height=6)
        source = upper.wall((4, 0), (0, 0), thickness=0.2, height=3)
        source.add_window(at=1, width=1, sill_height=0.5, height=1.5)

        layer = house.add_facade_layer(
            host,
            offset=0,
            thickness=0.01,
            opening_walls=[source],
        )

        self.assertEqual(layer.opening_walls, (host, source))
        self.assertEqual(len(layer.openings), 1)
        placement = ifcopenshell.util.placement.get_local_placement(
            layer.openings[0].ObjectPlacement
        )
        np.testing.assert_allclose(placement[:3, 3], (2, 0, 3.5), atol=1e-9)
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), layer)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            (4 * 6 - 1) * 0.01,
        )

    def test_validates_facade_layer_arguments(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (4, 0), thickness=0.2, height=3)
        perpendicular = ground.wall((0, 0), (0, 4), thickness=0.2, height=3)
        shifted = ground.wall((0, 1), (4, 1), thickness=0.2, height=3)

        with self.assertRaisesRegex(ValueError, "offset"):
            house.add_facade_layer(wall, offset=-0.1, thickness=0.01)
        with self.assertRaisesRegex(ValueError, "thickness"):
            house.add_facade_layer(wall, offset=0, thickness=0)
        with self.assertRaisesRegex(TypeError, "trim_openings"):
            house.add_facade_layer(
                wall, offset=0, thickness=0.01, trim_openings="yes"
            )
        with self.assertRaisesRegex(ValueError, "parallel"):
            house.add_facade_layer(
                wall,
                offset=0,
                thickness=0.01,
                opening_walls=[perpendicular],
            )
        with self.assertRaisesRegex(ValueError, "aligned"):
            house.add_facade_layer(
                wall,
                offset=0,
                thickness=0.01,
                opening_walls=[shifted],
            )

    def test_adds_horizontal_frame_spanning_wall_with_extensions(self) -> None:
        house = House("My house")
        wall_type = house.wall_type(
            "Exterior wall", layers=[("Brick", 0.25), "axis"]
        )
        ground = house.storey("Ground floor", elevation=0.5)
        wall = ground.wall(
            (1, 2),
            (6, 2),
            wall_type=wall_type,
            start_height=0.25,
            height=3,
        )

        frame = house.add_horizontal_frame(
            wall,
            side="right",
            offset=0.1,
            width=0.04,
            depth=0.06,
            gap=0.4,
            lath_offsets=[0.25, 1, 2.5],
            start_extension=0.2,
            end_extension=0.3,
            insulation_material="Rockwool",
            insulation_color="#E8D36D",
        )

        self.assertIsInstance(frame, HorizontalFrame)
        self.assertTrue(frame.is_a("IfcElementAssembly"))
        self.assertEqual(frame.ObjectType, "FACADE_HORIZONTAL_FRAME")
        self.assertEqual(frame.gap, 0.4)
        self.assertEqual(frame.lath_offsets, (0.25, 1, 2.5))
        np.testing.assert_allclose(
            frame.lath_positions,
            (0.25, 0.69, 1, 1.44, 1.88, 2.32, 2.5),
            atol=1e-9,
        )
        self.assertEqual(frame.start_extension, 0.2)
        self.assertEqual(frame.end_extension, 0.3)
        self.assertAlmostEqual(frame.length, 5.5)
        self.assertEqual(len(frame.members), 7)
        self.assertEqual(frame.insulation_material, "Rockwool")
        self.assertEqual(len(frame.insulation_blocks), 6)
        self.assertEqual(
            frame.ContainedInStructure[0].RelatingStructure, ground.element
        )
        self.assertEqual(
            set(frame.IsDecomposedBy[0].RelatedObjects),
            {*frame.members, *frame.insulation_blocks},
        )
        first_insulation = frame.insulation_blocks[0]
        self.assertTrue(first_insulation.is_a("IfcBuildingElementPart"))
        self.assertEqual(first_insulation.ObjectType, "FACADE_INSULATION")
        self.assertEqual(
            ifcopenshell.util.element.get_material(first_insulation).Name,
            "Rockwool",
        )
        insulation_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), first_insulation
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(insulation_shape.geometry),
            5.5 * 0.4 * 0.06,
        )

        expected_z = (0.77, 1.21, 1.52, 1.96, 2.4, 2.84, 3.02)
        for member, z in zip(frame.members, expected_z):
            self.assertTrue(member.is_a("IfcMember"))
            self.assertEqual(member.PredefinedType, "MEMBER")
            self.assertEqual(member.ObjectType, "FACADE_LATH")
            placement = ifcopenshell.util.placement.get_local_placement(
                member.ObjectPlacement
            )
            np.testing.assert_allclose(
                placement[:3, 3], (0.8, 1.87, z), atol=1e-9
            )
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_volume(shape.geometry),
                5.5 * 0.04 * 0.06,
            )
            self.assertEqual(
                ifcopenshell.util.element.get_material(member).Name, "Wood"
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    member, "Pset_MemberCommon", "LoadBearing"
                ),
                False,
            )

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        first_shape = ifcopenshell.geom.create_shape(settings, frame.members[0])
        vertices = ifcopenshell.util.shape.get_vertices(first_shape.geometry)
        self.assertAlmostEqual(min(vertex[0] for vertex in vertices), 0.8)
        self.assertAlmostEqual(max(vertex[0] for vertex in vertices), 6.3)
        self.assertAlmostEqual(min(vertex[2] for vertex in vertices), 0.75)
        self.assertAlmostEqual(max(vertex[2] for vertex in vertices), 0.79)

        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    frame, "BBIM_HorizontalFrame", "LathOffsets"
                )
            ),
            [0.25, 1, 2.5],
        )
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    frame, "BBIM_HorizontalFrame", "LathPositions"
                )
            ),
            [0.25, 0.69, 1, 1.44, 1.88, 2.32, 2.5],
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "StartExtension"
            ),
            0.2,
        )

    def test_splits_horizontal_frame_laths_around_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (4, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_horizontal_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            gap=10,
            lath_offsets=[0, 1, 2.5],
            start_extension=0.2,
            end_extension=0.3,
            space_before_openings=0.1,
            space_after_openings=0.2,
            space_above_openings=0.6,
            space_below_openings=0.6,
            insulation_material="Rockwool",
        )

        self.assertTrue(frame.trim_openings)
        self.assertEqual(frame.space_before_openings, 0.1)
        self.assertEqual(frame.space_after_openings, 0.2)
        self.assertEqual(frame.space_above_openings, 0.6)
        self.assertEqual(frame.space_below_openings, 0.6)
        self.assertEqual(len(frame.members), 6)
        split_members = [
            member for member in frame.members if "Lath 2." in member.Name
        ]
        self.assertEqual(len(split_members), 2)
        split_lengths = []
        split_starts = []
        for member in split_members:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            split_lengths.append(
                ifcopenshell.util.shape.get_volume(shape.geometry) / (0.1 * 0.06)
            )
            placement = ifcopenshell.util.placement.get_local_placement(
                member.ObjectPlacement
            )
            split_starts.append(placement[0, 3])
        np.testing.assert_allclose(sorted(split_lengths), (0.9, 2.8), atol=1e-9)
        np.testing.assert_allclose(sorted(split_starts), (-0.2, 1.5), atol=1e-9)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "TrimOpenings"
            ),
            True,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "SpaceBeforeOpenings"
            ),
            0.1,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "SpaceAfterOpenings"
            ),
            0.2,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "SpaceAboveOpenings"
            ),
            0.6,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_HorizontalFrame", "SpaceBelowOpenings"
            ),
            0.6,
        )
        self.assertEqual(len(frame.insulation_blocks), 2)
        insulation_volumes = []
        for block in frame.insulation_blocks:
            self.assertEqual(len(block.HasOpenings), 1)
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), block
            )
            insulation_volumes.append(
                ifcopenshell.util.shape.get_volume(shape.geometry)
            )
        np.testing.assert_allclose(
            insulation_volumes,
            (
                (4.5 - 0.8) * 0.9 * 0.06,
                (4.5 - 0.8) * 1.4 * 0.06,
            ),
            atol=1e-9,
        )

        untrimmed = house.add_horizontal_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            gap=10,
            lath_offsets=[1, 2.5],
            start_extension=0.2,
            end_extension=0.3,
            trim_openings=False,
        )
        self.assertFalse(untrimmed.trim_openings)
        self.assertEqual(len(untrimmed.members), 2)
        for member in untrimmed.members:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_volume(shape.geometry),
                4.5 * 0.1 * 0.06,
            )

    def test_validates_horizontal_frame_arguments(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (1, 0), thickness=0.2, height=3)
        arguments = {
            "wall": wall,
            "offset": 0,
            "width": 0.04,
            "depth": 0.06,
            "gap": 0.4,
            "lath_offsets": [0, 1],
        }

        with self.assertRaisesRegex(ValueError, "offset"):
            house.add_horizontal_frame(**(arguments | {"offset": -0.1}))
        with self.assertRaisesRegex(ValueError, "width"):
            house.add_horizontal_frame(**(arguments | {"width": 0}))
        with self.assertRaisesRegex(ValueError, "depth"):
            house.add_horizontal_frame(**(arguments | {"depth": 0}))
        with self.assertRaisesRegex(ValueError, "gap"):
            house.add_horizontal_frame(**(arguments | {"gap": 0}))
        with self.assertRaisesRegex(ValueError, "at least two"):
            house.add_horizontal_frame(**(arguments | {"lath_offsets": [0]}))
        with self.assertRaisesRegex(TypeError, "sequence"):
            house.add_horizontal_frame(
                **(arguments | {"lath_offsets": "0,1"})
            )
        with self.assertRaisesRegex(ValueError, "negative positions"):
            house.add_horizontal_frame(
                **(arguments | {"lath_offsets": [-0.1, 1]})
            )
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            house.add_horizontal_frame(
                **(arguments | {"lath_offsets": [1, 0.5]})
            )
        with self.assertRaisesRegex(ValueError, "start_extension"):
            house.add_horizontal_frame(**arguments, start_extension=-0.1)
        with self.assertRaisesRegex(ValueError, "end_extension"):
            house.add_horizontal_frame(**arguments, end_extension=-0.1)
        with self.assertRaisesRegex(TypeError, "trim_openings"):
            house.add_horizontal_frame(**arguments, trim_openings="yes")
        with self.assertRaisesRegex(ValueError, "space_before_openings"):
            house.add_horizontal_frame(**arguments, space_before_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_after_openings"):
            house.add_horizontal_frame(**arguments, space_after_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_above_openings"):
            house.add_horizontal_frame(**arguments, space_above_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_below_openings"):
            house.add_horizontal_frame(**arguments, space_below_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "insulation_transparency"):
            house.add_horizontal_frame(
                **arguments, insulation_transparency=1.1
            )
        with self.assertRaisesRegex(ValueError, "must be one of"):
            house.add_horizontal_frame(**arguments, side="outside")

    def test_splits_vertical_frame_laths_around_existing_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (4, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_vertical_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            start_height=0,
            height=3,
            gap=0.875,
            lath_offsets=[0, 3.9],
        )

        self.assertEqual(len(frame.members), 6)
        split_members = [
            member for member in frame.members if "Lath 2." in member.Name
        ]
        self.assertEqual(len(split_members), 2)
        split_heights = []
        for member in split_members:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            split_heights.append(
                ifcopenshell.util.shape.get_volume(shape.geometry) / (0.1 * 0.06)
            )
        np.testing.assert_allclose(sorted(split_heights), (0.5, 1.0), atol=1e-9)

    def test_adds_one_insulation_block_per_vertical_frame_bay(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (2, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_vertical_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            start_height=0,
            height=3,
            gap=10,
            lath_offsets=[0, 1.9],
            insulation_material="Rockwool",
            insulation_color="#E8D36D",
        )

        self.assertEqual(frame.insulation_material, "Rockwool")
        self.assertEqual(len(frame.insulation_blocks), 1)
        block = frame.insulation_blocks[0]
        self.assertTrue(block.is_a("IfcBuildingElementPart"))
        self.assertEqual(block.ObjectType, "FACADE_INSULATION")
        self.assertEqual(len(block.HasOpenings), 1)
        self.assertEqual(
            ifcopenshell.util.element.get_material(block).Name, "Rockwool"
        )
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), block
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(shape.geometry),
            (1.8 * 3 - 0.5 * 1.5) * 0.06,
        )
        self.assertEqual(
            set(frame.IsDecomposedBy[0].RelatedObjects),
            {*frame.members, block},
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                block, "BBIM_FrameInsulation", "BayIndex"
            ),
            1,
        )

    def test_leaves_space_above_and_below_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (4, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_vertical_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            start_height=0,
            height=3,
            gap=0.875,
            lath_offsets=[0, 3.9],
            space_before_openings=0.1,
            space_after_openings=0.2,
            space_above_openings=0.1,
            space_below_openings=0.2,
        )

        self.assertEqual(frame.space_before_openings, 0.1)
        self.assertEqual(frame.space_after_openings, 0.2)
        self.assertEqual(frame.space_above_openings, 0.1)
        self.assertEqual(frame.space_below_openings, 0.2)
        split_members = [
            member for member in frame.members if "Lath 2." in member.Name
        ]
        split_heights = []
        for member in split_members:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            split_heights.append(
                ifcopenshell.util.shape.get_volume(shape.geometry) / (0.1 * 0.06)
            )
        np.testing.assert_allclose(sorted(split_heights), (0.3, 0.9), atol=1e-9)
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_VerticalFrame", "SpaceBeforeOpenings"
            ),
            0.1,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_VerticalFrame", "SpaceAfterOpenings"
            ),
            0.2,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_VerticalFrame", "SpaceAboveOpenings"
            ),
            0.1,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                frame, "BBIM_VerticalFrame", "SpaceBelowOpenings"
            ),
            0.2,
        )

    def test_uses_lath_start_offsets_at_opening_edges(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (2, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_vertical_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            height=3,
            gap=1,
            lath_offsets=[0.7, 1.3],
        )

        self.assertEqual(frame.lath_positions, (0.7, 1.3))
        self.assertEqual(len(frame.members), 2)
        for member, expected_x in zip(frame.members, (0.75, 1.35)):
            placement = ifcopenshell.util.placement.get_local_placement(
                member.ObjectPlacement
            )
            self.assertAlmostEqual(placement[0, 3], expected_x)

    def test_applies_all_opening_spaces_to_vertical_frame(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (2, 0), thickness=0.2, height=3)
        wall.add_opening(at=0.8, width=0.5, sill_height=0.5, height=2)

        frame = house.add_vertical_frame(
            wall,
            offset=0,
            width=0.1,
            depth=0.06,
            height=3,
            gap=10,
            lath_offsets=[0.65, 1.35],
            space_before_openings=0.1,
            space_after_openings=0.1,
            space_above_openings=0.2,
            space_below_openings=0.1,
        )

        self.assertEqual(len(frame.members), 4)
        segment_heights = []
        for member in frame.members:
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), member
            )
            segment_heights.append(
                ifcopenshell.util.shape.get_volume(shape.geometry) / (0.1 * 0.06)
            )
        np.testing.assert_allclose(
            sorted(segment_heights), (0.4, 0.4, 0.8, 0.8), atol=1e-9
        )

    def test_validates_vertical_frame_arguments(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (1, 0), thickness=0.2, height=3)
        arguments = {
            "wall": wall,
            "offset": 0,
            "width": 0.04,
            "depth": 0.06,
            "height": 3,
            "gap": 0.4,
            "lath_offsets": [0, 0.96],
        }

        with self.assertRaisesRegex(ValueError, "gap"):
            house.add_vertical_frame(**(arguments | {"gap": 0}))
        with self.assertRaisesRegex(ValueError, "at least two"):
            house.add_vertical_frame(**(arguments | {"lath_offsets": [0]}))
        with self.assertRaisesRegex(TypeError, "sequence"):
            house.add_vertical_frame(**(arguments | {"lath_offsets": "0,1"}))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            house.add_vertical_frame(
                **(arguments | {"lath_offsets": [0.5, 0.4]})
            )
        with self.assertRaisesRegex(ValueError, "within the wall"):
            house.add_vertical_frame(
                **(arguments | {"lath_offsets": [0, 0.97]})
            )
        with self.assertRaisesRegex(ValueError, "start_height"):
            house.add_vertical_frame(**arguments, start_height=-0.1)
        with self.assertRaisesRegex(ValueError, "offset"):
            house.add_vertical_frame(**(arguments | {"offset": -0.1}))
        with self.assertRaisesRegex(ValueError, "space_before_openings"):
            house.add_vertical_frame(**arguments, space_before_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_after_openings"):
            house.add_vertical_frame(**arguments, space_after_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_above_openings"):
            house.add_vertical_frame(**arguments, space_above_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "space_below_openings"):
            house.add_vertical_frame(**arguments, space_below_openings=-0.1)
        with self.assertRaisesRegex(ValueError, "insulation_transparency"):
            house.add_vertical_frame(
                **arguments, insulation_transparency=1.1
            )
        with self.assertRaisesRegex(ValueError, "must be one of"):
            house.add_vertical_frame(**arguments, side="outside")

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

    def test_assigns_vertical_wall_material_layers_without_splitting_wall(
        self,
    ) -> None:
        house = House("My house")
        wall_type = house.wall_type(
            "Load bearing wall", layers=[("Brick", 0.24), "axis"]
        )
        ground = house.storey("Ground floor", elevation=0)
        wall_1 = ground.wall(
            (0, 0), (4, 0), wall_type=wall_type, height=2.75
        )
        wall_2 = ground.wall(
            (4, 0), (4, 3), wall_type=wall_type, height=2.75
        )
        ground.connect_wall(wall_1, wall_2)
        door = wall_1.add_door(
            at=1,
            width=0.9,
            height=2.2,
            sill_height=0.1,
        )
        body_before = ifcopenshell.util.representation.get_representation(
            wall_1, "Model", "Body", "MODEL_VIEW"
        )

        vertical_type_1 = wall_1.set_vertical_material_layers(
            [("Liapor brick", 0.25), ("Brick", 2.50)],
            type_name="Ground load bearing wall",
        )
        vertical_type_2 = wall_2.set_vertical_material_layers(
            [("Liapor brick", 0.25), ("Brick", 2.50)],
            type_name="Ground load bearing wall",
        )

        self.assertEqual(vertical_type_1, vertical_type_2)
        self.assertEqual(
            ifcopenshell.util.element.get_type(wall_1), vertical_type_1
        )
        usage = ifcopenshell.util.element.get_material(wall_1)
        self.assertTrue(usage.is_a("IfcMaterialLayerSetUsage"))
        self.assertEqual(usage.LayerSetDirection, "AXIS3")
        self.assertEqual(usage.DirectionSense, "POSITIVE")
        self.assertEqual(usage.OffsetFromReferenceLine, 0.0)
        self.assertEqual(
            [
                (layer.Material.Name, layer.LayerThickness)
                for layer in usage.ForLayerSet.MaterialLayers
            ],
            [("Liapor brick", 0.25), ("Brick", 2.50)],
        )
        self.assertEqual(wall_1.thickness, 0.24)
        self.assertEqual(wall_1.body_offset, 0.0)
        self.assertEqual(
            ifcopenshell.util.representation.get_representation(
                wall_1, "Model", "Body", "MODEL_VIEW"
            ),
            body_before,
        )
        self.assertEqual(
            wall_1.HasOpenings[0]
            .RelatedOpeningElement.HasFillings[0]
            .RelatedBuildingElement,
            door,
        )
        self.assertAlmostEqual(
            ifcopenshell.util.placement.get_local_placement(
                door.ObjectPlacement
            )[2, 3],
            0.1,
        )
        with self.assertRaisesRegex(
            ValueError, "before assigning vertical material layers"
        ):
            ground.connect_wall(wall_1, wall_2)

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
            buildup_material="Floor build-up",
            color="#ffffff",
        )

        self.assertTrue(floor.is_a("IfcSlab"))
        self.assertIsInstance(floor, FloorLayer)
        self.assertIs(floor.element, floor)
        self.assertEqual(floor.PredefinedType, "FLOOR")
        self.assertEqual(
            floor.outline,
            ((0.25, 0.25), (11.75, 0.25), (11.75, 7.75), (0.25, 7.75)),
        )
        self.assertAlmostEqual(floor.area, 86.25)
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
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                floor, "BBIM_FloorLayer", "Area"
            ),
            86.25,
        )

        irregular_floor = upper.floor_layer(
            "Irregular floor",
            outline=((0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)),
            thickness=0.1,
        )
        self.assertAlmostEqual(irregular_floor.area, 5)

        base_slab = upper.floor_layer(
            "Base slab",
            outline=((0, 0), (2, 0), (2, 2), (0, 2)),
            thickness=0.2,
            start_height=-0.2,
            kind="BASESLAB",
            load_bearing=True,
            buildup_material="Concrete",
        )
        self.assertEqual(base_slab.PredefinedType, "BASESLAB")
        self.assertEqual(base_slab.start_height, -0.2)
        self.assertAlmostEqual(
            ifcopenshell.util.placement.get_local_placement(
                base_slab.ObjectPlacement
            )[2, 3],
            3.01,
        )
        self.assertTrue(
            ifcopenshell.util.element.get_pset(
                base_slab, "Pset_SlabCommon", "LoadBearing"
            )
        )

        insulated_floor = upper.floor_layer(
            "Insulated floor",
            outline=((3, 0), (5, 0), (5, 2), (3, 2)),
            thickness=0.17,
            insulation_thickness=0.10,
            insulation_material="Test insulation",
            buildup_material="Test build-up",
        )
        self.assertEqual(
            insulated_floor.layers,
            (
                ("Test insulation", 0.10),
                ("Test build-up", 0.07),
            ),
        )
        self.assertAlmostEqual(insulated_floor.insulation_thickness, 0.10)
        self.assertAlmostEqual(insulated_floor.buildup_thickness, 0.07)
        insulated_usage = ifcopenshell.util.element.get_material(
            insulated_floor
        )
        self.assertTrue(insulated_usage.is_a("IfcMaterialLayerSetUsage"))
        self.assertEqual(insulated_usage.LayerSetDirection, "AXIS3")
        self.assertEqual(insulated_usage.DirectionSense, "POSITIVE")
        self.assertAlmostEqual(insulated_usage.OffsetFromReferenceLine, 0)
        self.assertEqual(
            [
                layer.Material.Name
                for layer in insulated_usage.ForLayerSet.MaterialLayers
            ],
            ["Test insulation", "Test build-up"],
        )
        self.assertEqual(
            [
                layer.LayerThickness
                for layer in insulated_usage.ForLayerSet.MaterialLayers
            ],
            [0.10, 0.07],
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(
                ifcopenshell.geom.create_shape(
                    ifcopenshell.geom.settings(), insulated_floor
                ).geometry
            ),
            0.17,
        )
        matching_floor = upper.floor_layer(
            "Matching insulated floor",
            outline=((6, 0), (8, 0), (8, 2), (6, 2)),
            thickness=0.17,
            insulation_thickness=0.10,
            insulation_material="Test insulation",
            buildup_material="Test build-up",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_type(matching_floor),
            ifcopenshell.util.element.get_type(insulated_floor),
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
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0.1,
                kind="WALL",
            )
        with self.assertRaisesRegex(TypeError, "load_bearing must be a boolean"):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0.1,
                load_bearing=1,
            )
        with self.assertRaisesRegex(
            ValueError, "insulation_thickness must not be negative"
        ):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0.1,
                insulation_thickness=-0.01,
            )
        with self.assertRaisesRegex(
            ValueError, "insulation_thickness must be less than thickness"
        ):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0.1,
                insulation_thickness=0.1,
            )
        with self.assertRaisesRegex(
            ValueError, "insulation_material is required"
        ):
            upper.floor_layer(
                "Invalid",
                outline=((0, 0), (1, 0), (1, 1)),
                thickness=0.1,
                insulation_thickness=0.05,
            )

    def test_adds_a_simple_ceiling_layer_below_a_storey_ceiling(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.5)
        outline = (
            (0.25, 0.25),
            (4.25, 0.25),
            (4.25, 3.25),
            (0.25, 3.25),
        )

        ceiling = ground.ceiling_layer(
            "Room ceiling",
            outline=outline,
            thickness=0.02,
            start_height=2.78,
        )

        self.assertTrue(ceiling.is_a("IfcCovering"))
        self.assertIsInstance(ceiling, CeilingLayer)
        self.assertIs(ceiling.element, ceiling)
        self.assertEqual(ceiling.PredefinedType, "CEILING")
        self.assertEqual(ceiling.ObjectType, "Ceiling layer")
        self.assertEqual(ceiling.outline, outline)
        self.assertAlmostEqual(ceiling.area, 12)
        self.assertEqual(ceiling.thickness, 0.02)
        self.assertEqual(ceiling.start_height, 2.78)
        self.assertEqual(ceiling.end_height, 2.8)
        self.assertEqual(
            ceiling.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            ceiling.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 3.28)
        shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), ceiling
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(shape.geometry), 4
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(shape.geometry), 3
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(shape.geometry), 0.02
        )
        self.assertEqual(
            ifcopenshell.util.element.get_material(ceiling).Name,
            "Ceiling finish",
        )
        properties = ifcopenshell.util.element.get_pset(
            ceiling, "BBIM_CeilingLayer"
        )
        self.assertEqual(
            json.loads(properties["Outline"]),
            [
                [0.25, 0.25],
                [4.25, 0.25],
                [4.25, 3.25],
                [0.25, 3.25],
            ],
        )
        self.assertEqual(properties["Area"], 12)
        self.assertEqual(properties["Thickness"], 0.02)

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
            open_angle=45,
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
            "door-overhead",
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
        casing = next(
            aspect
            for aspect in door.Representation.HasShapeAspects
            if aspect.Name == "Casing"
        )
        casing_body = casing.ShapeRepresentations[0]
        self.assertEqual(len(casing_body.Items), 2)
        casing_profile = (
            casing_body.Items[0].SweptArea.OuterCurve.Points.CoordList
        )
        np.testing.assert_allclose(
            casing_profile,
            (
                (-0.125, 0.0),
                (-0.125, 2.225),
                (1.0250000000000001, 2.225),
                (1.0250000000000001, 0.0),
                (0.85, 0.0),
                (0.85, 2.0500000000000003),
                (0.05, 2.0500000000000003),
                (0.05, 0.0),
            ),
            atol=1e-9,
        )
        casing_positions = [
            ifcopenshell.util.placement.get_axis2placement(item.Position)
            for item in casing_body.Items
        ]
        self.assertAlmostEqual(casing_positions[0][1, 3], -0.13)
        self.assertAlmostEqual(casing_positions[1][1, 3], 0.125)
        self.assertTrue(
            all(item.Depth == 0.005 for item in casing_body.Items)
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "CasingOverlap"
            ),
            0.025,
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
            for item in ifcopenshell.util.representation.resolve_representation(plan).Items
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

    def test_can_omit_door_casings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.25, height=3)

        door = wall.add_door(
            at=1,
            width=0.9,
            height=2.1,
            opening_width=1.0,
            casing_depth=0,
        )

        self.assertNotIn(
            "Casing",
            {aspect.Name for aspect in door.Representation.HasShapeAspects},
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "CasingDepth"
            ),
            0,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                door, "EPset_Door", "OpenAngle"
            ),
            0,
        )
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
        panel_placement = ifcopenshell.util.placement.get_axis2placement(
            framing_body.Items[0].Position
        )
        self.assertAlmostEqual(panel_placement[0, 0], 1)
        self.assertAlmostEqual(panel_placement[1, 0], 0)

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
        with self.assertRaisesRegex(ValueError, "casing_overlap"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                casing_overlap=-0.01,
            )
        with self.assertRaisesRegex(ValueError, "casing_depth"):
            wall.add_door(
                at=1,
                width=0.9,
                height=2.1,
                casing_depth=-0.01,
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
        normal_plan = ifcopenshell.util.representation.resolve_representation(normal_plan)
        reversed_plan = ifcopenshell.util.representation.resolve_representation(reversed_plan)
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
        self.assertEqual(len(house._plan_annotations), 1)
        mask_source = house._plan_annotations[0]
        self.assertEqual(ifcopenshell.util.element.get_pset(
            mask_source, "EPset_Annotation", "Classes"), "opening-mask-source")
        drawing = house.add_drawing("Ground plan", 1, 4.5, 1.5, 4)
        self.assertIn(mask_source, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(mask_source.GlobalId, _overhead_mask_global_ids(house.model, .3))
        self.assertIn(mask_source.GlobalId, _overhead_mask_global_ids(house.model, 1.5))
        self.assertNotIn(mask_source.GlobalId, _overhead_mask_global_ids(house.model, 2.5))

        with TemporaryDirectory() as directory:
            output = Path(directory) / "opening.ifc"
            house.write(output)
            reopened = ifcopenshell.open(output)
            self.assertEqual(len(reopened.by_type("IfcOpeningElement")), 1)
            self.assertEqual(len(reopened.by_type("IfcDoor")), 0)

    def test_opening_continuation_defaults_and_explicit_overrides(self) -> None:
        house = House("Opening lines")
        ground = house.storey("Ground", elevation=0)
        wall = ground.wall((0, 0), (10, 0), thickness=.24, height=3)
        drawing = house.add_drawing("Plan", 5, 0, 1.5, 6)
        wall.add_door(at=0.5, width=.9, height=2.1, name="Default door")
        wall.add_door(at=2, width=.9, height=2.1, show_overhead=False, name="No-line door")
        wall.add_opening(at=4, width=1, height=2.1, name="Default opening")
        wall.add_opening(at=6, width=1, height=2.1, show_overhead=True, name="Opt-in opening")
        overheads = house._plan_annotations
        self.assertEqual({a.Name for a in overheads},
                         {"Default door Overhead", "Default opening Overhead", "Opt-in opening Overhead"})
        for annotation in overheads:
            self.assertEqual(ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"),
                "opening-mask-source" if annotation.Name == "Default opening Overhead" else "door-overhead")
            self.assertIn(annotation, drawing.group.IsGroupedBy[0].RelatedObjects)

    def test_adds_partial_depth_wall_recesses_from_either_side(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.25)
        wall = ground.wall((0, 0), (5, 0), thickness=0.24, height=3)
        right_recess = wall.add_recess(
            at=0.5,
            width=0.3,
            depth=0.12,
            height=0.08,
            sill_height=2.92,
            side="right",
            top_extension=0.01,
            name="Right purlin seat",
        )
        left_recess = wall.add_recess(
            at=1.0,
            width=0.4,
            depth=0.12,
            height=0.1,
            sill_height=2.9,
            side="left",
            name="Left purlin seat",
        )

        self.assertEqual(right_recess.PredefinedType, "RECESS")
        self.assertEqual(left_recess.PredefinedType, "RECESS")
        self.assertEqual(
            right_recess.VoidsElements[0].RelatingBuildingElement,
            wall,
        )
        self.assertEqual(
            left_recess.VoidsElements[0].RelatingBuildingElement,
            wall,
        )
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), 0)

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        def bounds(element):
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = np.asarray(shape.geometry.verts).reshape((-1, 3))
            return vertices.min(axis=0), vertices.max(axis=0)

        right_minimum, right_maximum = bounds(right_recess)
        np.testing.assert_allclose(right_minimum, (0.5, -0.13, 3.17))
        np.testing.assert_allclose(right_maximum, (0.8, 0.0, 3.26))
        left_minimum, left_maximum = bounds(left_recess)
        np.testing.assert_allclose(left_minimum, (1.0, 0.0, 3.15))
        np.testing.assert_allclose(left_maximum, (1.4, 0.13, 3.25))

        wall_shape = ifcopenshell.geom.create_shape(settings, wall)
        expected_volume = (
            5 * 0.24 * 3
            - 0.3 * 0.12 * 0.08
            - 0.4 * 0.12 * 0.1
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(wall_shape.geometry),
            expected_volume,
        )

    def test_rejects_a_wall_recess_as_deep_as_the_wall(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.24, height=3)

        with self.assertRaisesRegex(
            ValueError,
            "depth must be less than the wall thickness",
        ):
            wall.add_recess(
                at=0.5,
                width=0.3,
                depth=0.24,
                height=0.08,
                sill_height=2.92,
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

    def test_mirrors_exports_across_x_zero_without_changing_live_coordinates(
        self,
    ) -> None:
        house = House("Mirrored house", mirror_x=True)
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((2, 3), (5, 3), thickness=0.2, height=2.8)
        door = wall.add_door(
            at=0.5,
            opening_width=1.2,
            width=1,
            height=2.2,
            operation="SINGLE_SWING_LEFT",
        )
        rafter = ground.beam(
            "Sloped beam",
            start=(1, 2, 4),
            end=(5, 2, 7),
            size=(0.12, 0.2),
            kind="RAFTER",
        )
        drawing = house.add_drawing(
            "Section",
            4,
            3,
            2,
            6,
            view="elevation",
            direction=(-1, 0, 0),
            door_annotations=False,
        )

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        def bounds(
            model: ifcopenshell.file,
            global_id: str,
        ) -> tuple[np.ndarray, np.ndarray]:
            shape = ifcopenshell.geom.create_shape(
                settings,
                model.by_guid(global_id),
            )
            vertices = np.asarray(shape.geometry.verts).reshape((-1, 3))
            return vertices.min(axis=0), vertices.max(axis=0)

        original_rafter_bounds = bounds(house.model, rafter.GlobalId)
        original_wall_placement = ifcopenshell.util.placement.get_local_placement(
            wall.ObjectPlacement
        ).copy()

        with TemporaryDirectory() as directory:
            first_output = Path(directory) / "mirrored.ifc"
            second_output = Path(directory) / "mirrored-again.ifc"
            house.write(first_output)
            house.write(second_output)
            mirrored = ifcopenshell.open(first_output)
            mirrored_again = ifcopenshell.open(second_output)

            wall_minimum, wall_maximum = bounds(mirrored, wall.GlobalId)
            np.testing.assert_allclose(wall_minimum, (-5, 2.9, 0), atol=1e-8)
            np.testing.assert_allclose(wall_maximum, (-2, 3.1, 2.8), atol=1e-8)
            repeated_minimum, repeated_maximum = bounds(
                mirrored_again,
                wall.GlobalId,
            )
            np.testing.assert_allclose(repeated_minimum, wall_minimum, atol=1e-8)
            np.testing.assert_allclose(repeated_maximum, wall_maximum, atol=1e-8)

            mirrored_rafter_bounds = bounds(mirrored, rafter.GlobalId)
            np.testing.assert_allclose(
                mirrored_rafter_bounds[0][0],
                -original_rafter_bounds[1][0],
                atol=1e-8,
            )
            np.testing.assert_allclose(
                mirrored_rafter_bounds[1][0],
                -original_rafter_bounds[0][0],
                atol=1e-8,
            )
            np.testing.assert_allclose(
                mirrored_rafter_bounds[0][1:],
                original_rafter_bounds[0][1:],
                atol=1e-8,
            )
            np.testing.assert_allclose(
                mirrored_rafter_bounds[1][1:],
                original_rafter_bounds[1][1:],
                atol=1e-8,
            )

            mirrored_door = mirrored.by_guid(door.GlobalId)
            self.assertEqual(mirrored_door.OperationType, "SINGLE_SWING_RIGHT")
            mirrored_drawing = mirrored.by_guid(drawing.element.GlobalId)
            drawing_placement = (
                ifcopenshell.util.placement.get_local_placement(
                    mirrored_drawing.ObjectPlacement
                )
            )
            np.testing.assert_allclose(
                drawing_placement[:3, 3],
                (-4, 3, 2),
                atol=1e-9,
            )
            np.testing.assert_allclose(
                drawing_placement[:3, 2],
                (-1, 0, 0),
                atol=1e-9,
            )
            for product in mirrored.by_type("IfcProduct"):
                if product.ObjectPlacement is None:
                    continue
                placement = ifcopenshell.util.placement.get_local_placement(
                    product.ObjectPlacement
                )
                self.assertAlmostEqual(
                    np.linalg.det(placement[:3, :3]),
                    1,
                )

        np.testing.assert_allclose(
            ifcopenshell.util.placement.get_local_placement(
                wall.ObjectPlacement
            ),
            original_wall_placement,
            atol=1e-9,
        )
        self.assertEqual(wall.start, (2, 3))
        self.assertEqual(wall.end, (5, 3))
        self.assertEqual(door.OperationType, "SINGLE_SWING_LEFT")
        self.assertEqual(rafter.start, (1, 2, 4))
        self.assertEqual(rafter.end, (5, 2, 7))

    def test_keeps_mirrored_plan_text_readable_and_moves_it_to_negative_x(
        self,
    ) -> None:
        house = House("Mirrored plan", mirror_x=True)
        ground = house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing(
            "Ground plan",
            3,
            4,
            1.5,
            6,
            storeys=[ground],
            door_annotations=False,
        )
        annotation = drawing.add_room_annotation(
            (3.5, 4),
            identifier="A",
            description="Room",
            area=10,
        )
        dimension = drawing.add_dimension((1, 2), (4, 2))

        with TemporaryDirectory() as directory:
            output = Path(directory) / "mirrored-plan.ifc"
            house.write(output)
            mirrored = ifcopenshell.open(output)
            mirrored_annotation = mirrored.by_guid(annotation.GlobalId)
            placement = ifcopenshell.util.placement.get_local_placement(
                mirrored_annotation.ObjectPlacement
            )
            self.assertAlmostEqual(placement[0, 3], -3.5)
            np.testing.assert_allclose(placement[:3, 0], (1, 0, 0), atol=1e-9)
            representation = mirrored_annotation.Representation.Representations[0]
            self.assertEqual(representation.RepresentationType, "Annotation2D")
            self.assertTrue(
                any(item.is_a("IfcTextLiteral") for item in representation.Items)
            )
            mirrored_dimension = mirrored.by_guid(dimension.GlobalId)
            dimension_map = (
                mirrored_dimension.Representation.Representations[0].Items[0]
            )
            source_curve = (
                dimension_map.MappingSource.MappedRepresentation.Items[0]
            )
            self.assertEqual(
                source_curve.Points.CoordList,
                ((4.0, 2.0), (1.0, 2.0)),
            )

    def test_orients_mirrored_vertical_door_text_with_its_top_to_the_left(
        self,
    ) -> None:
        house = House("Mirrored door annotation", mirror_x=True)
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((1, 2), (5, 2), thickness=0.24, height=2.8)
        door = wall.add_door(at=1, width=0.9, height=2.1)
        drawing = house.add_drawing(
            "Ground plan",
            3,
            2,
            1.5,
            5,
            storeys=[ground],
            door_annotations=False,
        )
        annotation = drawing.add_door_annotation(door)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "mirrored-door-annotation.ifc"
            house.write(output)
            mirrored = ifcopenshell.open(output)
            text_annotations = [
                mirrored.by_guid(annotation.GlobalId),
                next(
                    candidate
                    for candidate in mirrored.by_type("IfcAnnotation")
                    if candidate.Name == f"{annotation.Name} Height"
                ),
            ]
            text_placements = []
            for text_annotation in text_annotations:
                placement = ifcopenshell.util.placement.get_local_placement(
                    text_annotation.ObjectPlacement
                )
                text_placements.append(placement)
                np.testing.assert_allclose(
                    placement[:3, 0],
                    (0, 1, 0),
                    atol=1e-9,
                )
                np.testing.assert_allclose(
                    placement[:3, 1],
                    (-1, 0, 0),
                    atol=1e-9,
                )
            width_placement, height_placement = text_placements
            self.assertAlmostEqual(
                np.dot(
                    width_placement[:3, 3] - height_placement[:3, 3],
                    width_placement[:3, 1],
                ),
                0.27,
            )

    def test_validates_mirror_x(self) -> None:
        with self.assertRaisesRegex(TypeError, "mirror_x must be a boolean"):
            House("Invalid", mirror_x=1)

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

    def test_adds_miako_beam_centre_dimensions_on_the_selected_side(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        slab = upper.miako_slab(
            "Ceiling",
            start=(1, 2),
            end=(5, 2),
            top=0,
            direction=(0, 1),
            structure=["beam", "narrow", "beam", "wide", "beam"],
        )
        drawing = house.add_drawing(
            "Ceiling plan", 3, 3, 3.1, 5, storeys=[upper]
        )

        dimensions = drawing.add_miako_beam_dimensions(
            slab,
            side="start",
            offset=0.4,
        )

        self.assertEqual(len(dimensions), 2)
        self.assertEqual(
            [dimension.Name for dimension in dimensions],
            [
                "Ceiling Beam Center Distance 1",
                "Ceiling Beam Center Distance 2",
            ],
        )
        expected_lines = (
            ((0.6, 2.085), (0.6, 2.585)),
            ((0.6, 2.585), (0.6, 3.21)),
        )
        for dimension, expected_line in zip(dimensions, expected_lines):
            representation = ifcopenshell.util.representation.get_representation(
                dimension, "Plan", "Annotation", "PLAN_VIEW"
            )
            np.testing.assert_allclose(
                representation.Items[0].Points.CoordList,
                expected_line,
                atol=1e-9,
            )

        end_dimensions = drawing.add_miako_beam_dimensions(
            slab,
            side="end",
            offset=0.4,
        )
        end_representation = ifcopenshell.util.representation.get_representation(
            end_dimensions[0], "Plan", "Annotation", "PLAN_VIEW"
        )
        np.testing.assert_allclose(
            end_representation.Items[0].Points.CoordList,
            ((5.4, 2.085), (5.4, 2.585)),
            atol=1e-9,
        )

        reversed_dimensions = drawing.add_miako_beam_dimensions(
            slab,
            side="start",
            offset=-0.4,
        )
        reversed_representation = (
            ifcopenshell.util.representation.get_representation(
                reversed_dimensions[0], "Plan", "Annotation", "PLAN_VIEW"
            )
        )
        np.testing.assert_allclose(
            reversed_representation.Items[0].Points.CoordList,
            ((1.4, 2.085), (1.4, 2.585)),
            atol=1e-9,
        )

        with self.assertRaisesRegex(TypeError, "must be a MiakoSlab"):
            drawing.add_miako_beam_dimensions(upper.element)
        with self.assertRaisesRegex(ValueError, "side must be one of"):
            drawing.add_miako_beam_dimensions(slab, side="left")

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
            description="Bedroom",
            area=8.3,
            window_area=1.8,
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
        self.assertEqual(metadata["Description"], "Bedroom")
        self.assertAlmostEqual(metadata["Area"], 8.3)
        self.assertAlmostEqual(metadata["WindowArea"], 1.8)

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
        with self.assertRaisesRegex(ValueError, "window_area must not be negative"):
            drawing.add_room_annotation(
                (1, 1), identifier="P.03", area=5, window_area=-1
            )
        with self.assertRaisesRegex(ValueError, "duplicated"):
            drawing.add_room_annotation((1, 1), identifier="P.01", area=5)

    def test_persists_room_legend_from_room_annotations(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing(
            "Ground plan",
            2,
            3,
            1.6,
            5,
            storeys=[ground],
            right_panel_width=40,
        )
        drawing.add_room_annotation(
            (2, 2),
            identifier="0.02",
            description="Living room",
            area=18.25,
            window_area=3.5,
        )
        drawing.add_room_annotation(
            (1, 1),
            identifier="0.01",
            description="Bedroom",
            area=12.5,
        )

        result = drawing.add_room_legend()

        self.assertIs(result, drawing)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "room_legend",
                    "title": "LEGENDA MÍSTNOSTÍ",
                    "items": [
                        {
                            "identifier": "0.02",
                            "description": "Living room",
                            "area": 18.25,
                            "window_area": 3.5,
                        },
                        {
                            "identifier": "0.01",
                            "description": "Bedroom",
                            "area": 12.5,
                        },
                    ],
                }
            ],
        )

        no_rooms = house.add_drawing(
            "No rooms", 2, 3, 1.6, 5, right_panel_width=40
        )
        with self.assertRaisesRegex(ValueError, "at least one room annotation"):
            no_rooms.add_room_legend()
        missing_description = house.add_drawing(
            "Missing description", 2, 3, 1.6, 5, right_panel_width=40
        )
        missing_description.add_room_annotation(
            (1, 1), identifier="P.01", area=5
        )
        with self.assertRaisesRegex(ValueError, "must include descriptions"):
            missing_description.add_room_legend()
        no_panel = house.add_drawing("No panel", 2, 3, 1.6, 5)
        no_panel.add_room_annotation(
            (1, 1), identifier="P.01", description="Bedroom", area=5
        )
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_room_legend()

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
        with self.assertRaisesRegex(
            TypeError, "automatic_plan_annotations must be a boolean"
        ):
            house.add_drawing(
                "Invalid automatic annotations",
                2.5,
                2,
                1.6,
                4,
                automatic_plan_annotations="yes",
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

    def test_adds_a_numbered_lintel_symbol_at_a_selected_opening_jamb(
        self,
    ) -> None:
        house = House("Lintel annotations")
        ground = house.storey("Ground floor", elevation=0.25)
        wall = ground.wall(
            (1, 2),
            (5, 2),
            thickness=0.24,
            height=2.8,
        )
        door = wall.add_door(
            at=1,
            opening_width=1.1,
            width=0.9,
            height=2.1,
        )
        bare_opening = wall.add_opening(
            at=2.5,
            width=0.8,
            height=2.2,
        )
        drawing = house.add_drawing(
            "Ground plan",
            3,
            2,
            1.6,
            4,
            storeys=[ground],
            door_annotations=False,
        )

        tag = drawing.add_lintel(
            door,
            2,
            position="after",
            direction="in",
        )

        self.assertEqual(tag.ObjectType, "TEXT")
        literals = tag.Representation.Representations[0].Items
        self.assertEqual([literal.Literal for literal in literals], ["Př", "2"])
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                tag, "EPset_Annotation", "Classes"
            ),
            "lintel-symbol lintel-tag regular",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                tag, "EPset_Annotation", "Symbol"
            ),
            "lintel-tag",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(tag, "BBIM_Lintel", "Number"),
            "2",
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                tag, "BBIM_Lintel", "OpeningWidth"
            ),
            1.1,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(tag, "BBIM_Lintel", "Position"),
            "after",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(tag, "BBIM_Lintel", "Direction"),
            "in",
        )
        tag_placement = ifcopenshell.util.placement.get_local_placement(
            tag.ObjectPlacement
        )
        np.testing.assert_allclose(
            tag_placement[:3, 3],
            (3.55, 2.77, 0.25),
            atol=1e-9,
        )

        leader = next(
            annotation
            for annotation in drawing.group.IsGroupedBy[0].RelatedObjects
            if annotation.Name == "Ground plan Lintel Př2 Leader"
        )
        self.assertEqual(leader.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                leader, "EPset_Annotation", "Classes"
            ),
            "lintel-leader",
        )
        leader_representation = ifcopenshell.util.representation.get_representation(
            leader,
            "Plan",
            "Annotation",
            "PLAN_VIEW",
        )
        np.testing.assert_allclose(
            leader_representation.Items[0].Points.CoordList,
            ((3.1, 2.12), (3.55, 2.77)),
            atol=1e-9,
        )
        self.assertTrue(
            any(
                relation.RelatingProduct == door
                for relation in tag.HasAssignments
                if relation.is_a("IfcRelAssignsToProduct")
            )
        )
        self.assertIn(tag, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(leader, drawing.group.IsGroupedBy[0].RelatedObjects)

        default_tag = drawing.add_lintel(bare_opening, "3A")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                default_tag, "BBIM_Lintel", "Position"
            ),
            "before",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                default_tag, "BBIM_Lintel", "Direction"
            ),
            "out",
        )
        default_tag_placement = ifcopenshell.util.placement.get_local_placement(
            default_tag.ObjectPlacement
        )
        np.testing.assert_allclose(
            default_tag_placement[:3, 3],
            (3.05, 1.23, 0.25),
            atol=1e-9,
        )
        self.assertIn(
            'id="lintel-tag"',
            Path("drawings/assets/symbols.svg").read_text(),
        )

        with self.assertRaisesRegex(ValueError, "already has"):
            drawing.add_lintel(door, 4)
        with self.assertRaisesRegex(ValueError, "position must be one of"):
            drawing.add_lintel(door, 4, position="middle")
        with self.assertRaisesRegex(TypeError, "opening must be"):
            drawing.add_lintel(wall, 4)

    def test_builds_lintel_legend_from_numbered_openings(self) -> None:
        house = House("Lintel legend")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (8, 0), thickness=0.24, height=2.8)
        first = wall.add_opening(at=0.5, width=1.0, height=2.1)
        second = wall.add_opening(at=2.0, width=1.0, height=2.1)
        third = wall.add_opening(at=3.5, width=1.125, height=2.1)
        conflicting = wall.add_opening(at=5.0, width=0.8, height=2.1)
        drawing = house.add_drawing(
            "Ground plan",
            4,
            2,
            1.6,
            5,
            storeys=[ground],
            door_annotations=False,
            right_panel_width=40,
        )
        drawing.add_lintel(first, 2)
        drawing.add_lintel(second, 2, position="after", direction="in")
        drawing.add_lintel(third, 1)

        result = drawing.add_lintel_legend()

        self.assertIs(result, drawing)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "lintel_legend",
                    "title": "LEGENDA PŘEKLADŮ",
                    "items": [
                        {
                            "number": "1",
                            "width": 1.125,
                            "count": 1,
                            "bearing": 0.1875,
                        },
                        {
                            "number": "2",
                            "width": 1.0,
                            "count": 2,
                            "bearing": 0.125,
                        },
                    ],
                }
            ],
        )

        drawing.add_lintel(conflicting, 2)
        with self.assertRaisesRegex(ValueError, "different opening widths"):
            drawing.add_lintel_legend()

        no_lintels = house.add_drawing(
            "No lintels",
            4,
            2,
            1.6,
            5,
            storeys=[ground],
            door_annotations=False,
            right_panel_width=40,
        )
        with self.assertRaisesRegex(ValueError, "at least one lintel"):
            no_lintels.add_lintel_legend()
        no_panel = house.add_drawing(
            "No panel",
            4,
            2,
            1.6,
            5,
            storeys=[ground],
            door_annotations=False,
        )
        no_panel.add_lintel(first, 5)
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_lintel_legend()

    def test_persists_notes_in_right_panel(self) -> None:
        house = House("Notes")
        drawing = house.add_drawing(
            "Roof plan",
            2,
            3,
            5,
            5,
            right_panel_width=65,
        )

        result = drawing.add_notes(
            ["First note", "Second note > threshold"],
            layout_scale=0.5,
        )

        self.assertIs(result, drawing)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "notes",
                    "title": "POZNÁMKY",
                    "items": [
                        {"text": "First note"},
                        {"text": "Second note > threshold"},
                    ],
                    "layout_scale": 0.5,
                }
            ],
        )

        no_panel = house.add_drawing("No panel", 2, 3, 5, 5)
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_notes(["Note"])
        with self.assertRaisesRegex(TypeError, "sequence of strings"):
            drawing.add_notes("Not a list")
        with self.assertRaisesRegex(ValueError, "at least one note"):
            drawing.add_notes([])

    def test_builds_timber_schedule_from_finished_beams(self) -> None:
        house = House("Timber schedule")
        roof = house.storey("Roof", elevation=0)
        first = roof.beam(
            "Rafter 1",
            start=(0, 0, 0),
            end=(4, 0, 0),
            size=(0.1, 0.18),
            cuts=[((3, 0, 0), (3, 1, 0), (3, 0, 1))],
        )
        second = roof.beam(
            "Rafter 2",
            start=(0, 1, 0),
            end=(4, 1, 0),
            size=(0.1, 0.18),
            cuts=[((3, 0, 0), (3, 1, 0), (3, 0, 1))],
        )
        drawing = house.add_drawing(
            "Roof plan",
            2,
            1,
            2,
            4,
            storeys=[roof],
            right_panel_width=90,
        )

        result = drawing.add_timber_schedule(
            [
                (
                    "Hlavní krokve",
                    (first, second),
                    0.315,
                    {
                        "pattern": "brick",
                        "color": "orange",
                        "drawing_order": 2,
                        "material": "c22",
                    },
                )
            ],
            layout_scale=0.5,
        )

        self.assertIs(result, drawing)
        self.assertAlmostEqual(first.finished_length(), 3.0)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "timber_schedule",
                    "title": "SPECIFIKACE PRVKŮ KROVU",
                    "items": [
                        {
                            "mark": "A",
                            "name": "Hlavní krokve",
                            "width": 100,
                            "height": 180,
                            "length": 3315,
                            "count": 2,
                            "pattern": "brick",
                            "color": "#ffa500",
                            "drawing_order": 2,
                            "material": "c22",
                            "member_guids": [
                                first.GlobalId,
                                second.GlobalId,
                            ],
                        }
                    ],
                    "layout_scale": 0.5,
                }
            ],
        )

        no_panel = house.add_drawing("No panel", 2, 1, 2, 4)
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_timber_schedule(
                [("Hlavní krokve", (first, second), 0)]
            )

    def test_timber_schedule_limits_elevation_styles_without_filtering_table_counts(self):
        house = House("Timber styles")
        ground = house.storey("Ground", elevation=0)
        members = [ground.beam(f"Rafter {x}", start=(x, 0, 2), end=(x, 3, 2),
                               size=(0.08, 0.2)) for x in (0, 1, 2)]
        rows = [("Krokve", members, 0.1,
                 {"color": "#ffaa00", "pattern": "diagonal1", "material": "C22"})]
        section = house.add_drawing("Section", 0, 0, 2, 5, view="elevation",
                                    direction=(1, 0, 0), right_panel_width=65)
        section.add_timber_schedule(rows, styled_members=[members[1], members[1]], layout_scale=0.5)
        properties = ifcopenshell.util.element.get_pset(section.element, "EPset_Drawing")
        table = json.loads(properties["RightPanelTables"])[0]
        self.assertEqual(table["styled_member_guids"], [members[1].GlobalId])
        self.assertEqual(table["items"][0]["count"], 3)
        self.assertEqual(table["items"][0]["length"], 3100)
        self.assertEqual(table["items"][0]["pattern"], "diagonal1")
        self.assertEqual(properties["Metadata"], "GlobalId")
        self.assertEqual(properties["UnstyledTimberColor"], "#ffffff")
        self.assertEqual(_timber_schedule_member_styles(properties),
                         {members[1].GlobalId: {"color": "#ffaa00", "pattern": "diagonal1"}})
        no_fills = house.add_drawing("No fills", 0, 0, 2, 5, view="elevation",
                                     direction=(1, 0, 0), right_panel_width=65)
        no_fills.add_timber_schedule(rows, styled_members=[])
        self.assertEqual(_timber_schedule_member_styles(
            ifcopenshell.util.element.get_pset(no_fills.element, "EPset_Drawing")), {})
        plan = house.add_drawing("Plan", 0, 0, 10, 5, right_panel_width=65)
        plan.add_timber_schedule(rows)
        self.assertEqual(set(_timber_schedule_member_styles(
            ifcopenshell.util.element.get_pset(plan.element, "EPset_Drawing"))),
            {b.GlobalId for b in members})

    def test_timber_schedule_validates_styled_members_before_adding_table(self):
        house = House("Timber styles")
        beam = house.storey("Ground", elevation=0).beam(
            "Beam", start=(0, 0, 1), end=(0, 3, 1), size=(0.08, 0.2))
        foreign = House("Foreign").storey("Ground", elevation=0).beam(
            "Foreign", start=(0, 0, 1), end=(0, 3, 1), size=(0.08, 0.2))
        drawing = house.add_drawing("Section", 0, 0, 2, 5, view="elevation",
                                   direction=(1, 0, 0), right_panel_width=65)
        for selection, error in (("guid", TypeError), (True, TypeError),
                                 ([object()], TypeError), ([foreign], ValueError)):
            with self.subTest(selection=selection), self.assertRaises(error):
                drawing.add_timber_schedule([("Beams", [beam], 0)], styled_members=selection)
        self.assertEqual(json.loads(ifcopenshell.util.element.get_pset(
            drawing.element, "EPset_Drawing", "RightPanelTables")), [])

    def test_timber_schedule_accepts_material_without_visual_style(self) -> None:
        house = House("Material labels")
        roof = house.storey("Roof", elevation=0)
        beam = roof.beam("Purlin", start=(0, 0, 0), end=(4, 0, 0), size=(0.2, 0.3))
        drawing = house.add_drawing("Roof", 2, 1, 2, 4, right_panel_width=110)
        drawing.add_timber_schedule([
            ("Vaznice", (beam,), 0, {"material": "gl24c"}),
            ("Unlabelled", (beam,), 0),
        ])
        tables = drawing._right_panel_tables
        self.assertEqual(tables[0]["items"][0]["material"], "gl24c")
        self.assertNotIn("color", tables[0]["items"][0])
        self.assertNotIn("material", tables[0]["items"][1])
        with self.assertRaisesRegex(TypeError, "material must be a string"):
            drawing.add_timber_schedule([("Vaznice", (beam,), 0, {"material": 22})])
        with self.assertRaisesRegex(ValueError, "material must not be empty"):
            drawing.add_timber_schedule([("Vaznice", (beam,), 0, {"material": " "})])

    def test_builds_miako_beam_schedule_from_explicit_and_slab_lengths(
        self,
    ) -> None:
        house = House("MIAKO schedule")
        upper = house.storey("Upper floor", elevation=3)
        left = upper.miako_slab(
            "Left ceiling",
            start=(0, 0),
            end=(3, 0),
            top=0,
            direction=(0, 1),
            structure=["beam", "wide", "beam", "narrow", "beam"],
        )
        middle = upper.miako_slab(
            "Middle ceiling",
            start=(3, 0),
            end=(7, 0),
            top=0,
            direction=(0, 1),
            structure=["beam", "wide", "beam"],
        )
        drawing = house.add_drawing(
            "Ceiling plan",
            3.5,
            2,
            3.1,
            5,
            storeys=[upper],
            right_panel_width=50,
        )

        result = drawing.add_miako_beam_schedule(
            [
                {"location": "Levá část", "slab": left, "length": 3.75},
                {"location": "Střed", "slab": middle},
            ]
        )

        self.assertIs(result, drawing)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "miako_beam_schedule",
                    "title": "SPECIFIKACE MIAKO NOSNÍKŮ",
                    "items": [
                        {
                            "location": "Levá část",
                            "length": 3750,
                            "count": 3,
                            "slab_guid": left.GlobalId,
                        },
                        {
                            "location": "Střed",
                            "length": 4000,
                            "count": 2,
                            "slab_guid": middle.GlobalId,
                        },
                    ],
                }
            ],
        )

        no_panel = house.add_drawing("No panel", 2, 2, 3.1, 4)
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_miako_beam_schedule(
                [{"location": "Left", "slab": left, "length": 3.75}]
            )
        narrow_panel = house.add_drawing(
            "Narrow panel", 2, 2, 3.1, 4, right_panel_width=30
        )
        with self.assertRaisesRegex(ValueError, "at least 40 mm"):
            narrow_panel.add_miako_beam_schedule(
                [{"location": "Left", "slab": left, "length": 3.75}]
            )
        with self.assertRaisesRegex(TypeError, "row 1 must be a mapping"):
            drawing.add_miako_beam_schedule([("Left", left, 3.75)])
        with self.assertRaisesRegex(ValueError, "must contain"):
            drawing.add_miako_beam_schedule(
                [{"location": "Left"}]
            )
        with self.assertRaisesRegex(TypeError, "slab must be a MiakoSlab"):
            drawing.add_miako_beam_schedule(
                [{"location": "Left", "slab": upper.element, "length": 3.75}]
            )
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            drawing.add_miako_beam_schedule(
                [{"location": "Left", "slab": left, "length": 0}]
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

    def test_adds_sloped_batting_in_an_elevation_drawing_plane(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing(
            "Section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )

        batting = drawing.add_batting(
            (2, 0, 1),
            (2, 3, 4),
            thickness=0.16,
            classes="roof-batting",
        )

        placement = ifcopenshell.util.placement.get_local_placement(
            batting.ObjectPlacement
        )
        diagonal = 2**-0.5
        np.testing.assert_allclose(
            placement,
            np.array(
                (
                    (0, 0, -1, 2),
                    (diagonal, diagonal, 0, 0),
                    (diagonal, -diagonal, 0, 1),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-9,
        )
        self.assertAlmostEqual(
            ifcopenshell.util.element.get_pset(
                batting,
                "BBIM_Batting",
                "Thickness",
            ),
            0.16,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                batting,
                "EPset_Annotation",
                "Classes",
            ),
            "roof-batting",
        )
        self.assertIn(batting, drawing.group.IsGroupedBy[0].RelatedObjects)

        projected_batting = drawing.add_batting(
            (4, 0, 1),
            (4, 3, 4),
            thickness=0.10,
        )
        projected_placement = ifcopenshell.util.placement.get_local_placement(
            projected_batting.ObjectPlacement
        )
        self.assertEqual(tuple(projected_placement[:3, 3]), (4, 0, 1))

        with self.assertRaisesRegex(ValueError, "parallel"):
            drawing.add_batting(
                (2.01, 0, 1),
                (2, 3, 4),
                thickness=0.16,
            )

    def test_adds_batting_between_actual_sloped_rafter_sections(self) -> None:
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                house = House("Longitudinal insulation", mirror_x=mirror)
                storey = house.storey("Upper", elevation=0)
                roof = storey.roof("Roof")
                plane = roof.plane("Slope", points=((0, 0, 3), (5, 0, 3), (0, 4, 5)))
                rafters = [plane.beam(f"Rafter {index}", start=(x, -1), end=(x, 5),
                                      z_offset=0.02, size=(width, 0.2), kind="RAFTER")
                           for index, (x, width) in enumerate(((0, 0.2), (1, 0.2),
                                                              (1.2, 0.2), (2, 0.3)))]
                projected = plane.beam("Projected only", start=(0.5, 2), end=(0.5, 4),
                                       z_offset=0.02, size=(0.2, 0.2), kind="RAFTER")
                section = house.add_drawing("Section", x=1, y=0, z=3, radius=4,
                                            view="elevation", direction=(0, 1, 0))
                other = house.add_drawing("Other", x=1, y=0, z=3, radius=4,
                                          view="elevation", direction=(0, 1, 0))
                before = len(house.model.by_type("IfcBeam"))
                batting = section.add_rafter_section_batting(rafters + [rafters[0], projected])
                self.assertEqual(len(batting), 2)
                self.assertEqual(len(house.model.by_type("IfcBeam")), before)
                expected_height = 0.2 * (1.25 ** 0.5)
                for annotation, (left, right) in zip(batting, ((0.13, 0.87), (1.33, 1.82))):
                    placement = ifcopenshell.util.placement.get_local_placement(annotation.ObjectPlacement)
                    axis = annotation.Representation.Representations[0].Items[0]
                    # Axis representations can use a polyline or indexed curve.
                    if axis.is_a("IfcPolyline"):
                        length = axis.Points[-1].Coordinates[0]
                    else:
                        length = axis.Points.CoordList[-1][0]
                    end = placement[:3, 3] + placement[:3, 0] * length
                    np.testing.assert_allclose(placement[:3, 3], (left, 0, 3 + 0.12 * 1.25**0.5), atol=1e-8)
                    np.testing.assert_allclose(end, (right, 0, placement[2, 3]), atol=1e-8)
                    self.assertAlmostEqual(ifcopenshell.util.element.get_pset(annotation, "BBIM_Batting", "Thickness"),
                                           expected_height * 0.7, places=8)
                    self.assertIn(annotation, section.group.IsGroupedBy[0].RelatedObjects)
                    self.assertNotIn(annotation, other.group.IsGroupedBy[0].RelatedObjects)
                    self.assertIn("rafter-section-batting", ifcopenshell.util.element.get_pset(
                        annotation, "EPset_Annotation", "Classes"))
                    if mirror:
                        reflected = house._export_model().by_guid(annotation.GlobalId)
                        reflected_placement = ifcopenshell.util.placement.get_local_placement(reflected.ObjectPlacement)
                        self.assertAlmostEqual(reflected_placement[0, 3], -left)
                self.assertEqual(section.add_rafter_section_batting([projected]), ())
                self.assertEqual(section.add_rafter_section_batting(rafters, end_inset=5), ())

    def test_validates_rafter_section_batting(self) -> None:
        house = House("Insulation")
        storey = house.storey("Upper", elevation=0)
        beam = storey.beam("Rafter", start=(0, -1, 2), end=(0, 1, 2), size=(0.1, 0.2))
        section = house.add_drawing("Section", x=0, y=0, z=2, radius=4,
                                    view="elevation", direction=(0, 1, 0))
        plan = house.add_drawing("Plan", x=0, y=0, z=2, radius=4)
        with self.assertRaisesRegex(ValueError, "elevation"):
            plan.add_rafter_section_batting([beam])
        for factor in (0, -0.1, 1, 1.1):
            with self.assertRaisesRegex(ValueError, "size_factor"):
                section.add_rafter_section_batting([beam], size_factor=factor)
        with self.assertRaisesRegex(ValueError, "end_inset"):
            section.add_rafter_section_batting([beam], end_inset=-0.01)
        with self.assertRaisesRegex(TypeError, "Beam"):
            section.add_rafter_section_batting([storey.element])
        with self.assertRaisesRegex(TypeError, "sequence"):
            section.add_rafter_section_batting("rafters")
        foreign = House("Other").storey("Upper", elevation=0).beam(
            "Foreign rafter", start=(0, -1, 2), end=(0, 1, 2), size=(0.1, 0.2))
        with self.assertRaisesRegex(ValueError, "this house"):
            section.add_rafter_section_batting([foreign])

    def test_adds_rotatable_hexagon_marker_to_elevation(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing(
            "Section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )
        other_drawing = house.add_drawing(
            "Other section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )

        marker = drawing.add_hexagon_marker(
            (2, 3, 4),
            "SK1",
            rotation=90,
            line_length=0.8,
        )

        self.assertEqual(marker.ObjectType, "TEXT")
        self.assertEqual(
            marker.Representation.Representations[0].Items[0].Literal,
            "SK1",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                marker,
                "EPset_Annotation",
                "Classes",
            ),
            "hexagon-marker",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                marker,
                "EPset_Annotation",
                "Symbol",
            ),
            "hexagon-marker",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                marker,
                "BBIM_HexagonMarker",
                "Identifier",
            ),
            "SK1",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                marker,
                "BBIM_HexagonMarker",
                "Rotation",
            ),
            90.0,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                marker,
                "BBIM_HexagonMarker",
                "LineLength",
            ),
            0.8,
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            marker.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement,
            np.array(
                (
                    (0, 0, -1, 2),
                    (-1, 0, 0, 3),
                    (0, 1, 0, 4),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-9,
        )
        leader = next(
            annotation
            for annotation in drawing.group.IsGroupedBy[0].RelatedObjects
            if annotation.Name == f"{marker.Name} Leader"
        )
        leader_placement = ifcopenshell.util.placement.get_local_placement(
            leader.ObjectPlacement
        )
        np.testing.assert_allclose(
            leader_placement,
            np.array(
                (
                    (0, 0, -1, 2),
                    (-1, 0, 0, 3),
                    (0, 1, 0, 4),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-9,
        )
        self.assertEqual(
            leader.Representation.Representations[0].Items[0].Points.CoordList,
            ((0.1732, 0.0), (0.8, 0.0)),
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                leader,
                "EPset_Annotation",
                "Classes",
            ),
            "hexagon-marker-leader",
        )
        self.assertIn(marker, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(leader, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(
            marker,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertTrue(
            ifcopenshell.util.element.get_pset(
                drawing.element,
                "EPset_Drawing",
                "HasAnnotation",
            )
        )
        self.assertIn(
            'id="hexagon-marker"',
            Path("drawings/assets/symbols.svg").read_text(),
        )
        self.assertIn(
            "text.hexagon-marker",
            Path("bonsai_scripts/assets/plan.css").read_text(),
        )

        plan = house.add_drawing("Plan", 2, 2, 1, 5)
        with self.assertRaisesRegex(ValueError, "elevation"):
            plan.add_hexagon_marker((2, 3, 4), "SK2")
        with self.assertRaisesRegex(ValueError, "identifier must not be empty"):
            drawing.add_hexagon_marker((2, 3, 4), " ")
        with self.assertRaisesRegex(ValueError, "hexagon boundary"):
            drawing.add_hexagon_marker(
                (2, 3, 4),
                "SK2",
                line_length=0.1,
            )

    def test_cut_definition_shares_geometry_between_symbols_and_camera(self) -> None:
        for start, end, direction in (((2, -1), (2, 9), -1),
                                      ((-1, 2), (9, 2), 1),
                                      ((1, 1), (4, 5), -1)):
            with self.subTest(start=start, end=end, direction=direction):
                cut = CutDefinition(start, end, " A ", direction)
                house = House("Cut definition", mirror_x=True)
                plan = house.add_drawing("Plan", 2, 2, 1, 5)
                line = cut.add_symbol(plan)
                section = cut.add_drawing(house, "AA", z=3.5, radius=8,
                                          doors_closed=True, right_panel_width=60)
                expected_center = (np.array(start) + np.array(end)) / 2
                np.testing.assert_allclose(cut.center, expected_center)
                np.testing.assert_allclose((section.x, section.y), expected_center)
                np.testing.assert_allclose(section.direction, cut.view_direction)
                self.assertEqual((section.z, section.radius, section.view), (3.5, 8, "elevation"))
                self.assertEqual(section.right_panel_width, 60)
                self.assertTrue(section.doors_closed)
                self.assertAlmostEqual(np.linalg.norm(cut.view_direction), 1)
                self.assertAlmostEqual(np.dot(cut.view_direction[:2], np.array(end) - start), 0)
                self.assertEqual(ifcopenshell.util.element.get_pset(line, "BBIM_CutSymbol", "Identifier"), "A")
                exported = house._export_model()
                arrow = next(a for a in exported.by_type("IfcAnnotation")
                             if ifcopenshell.util.element.get_pset(a, "EPset_Annotation", "Classes") == "cut-symbol-arrow")
                matrix = ifcopenshell.util.placement.get_local_placement(arrow.ObjectPlacement)
                item = arrow.Representation.Representations[0].Items[0]
                if item.is_a("IfcMappedItem"):
                    matrix = matrix @ ifcopenshell.util.placement.get_mappeditem_transformation(item)
                    item = item.MappingSource.MappedRepresentation.Items[0]
                shaft = item.Elements[0].Points.CoordList
                world_shaft = [matrix @ np.array((*point, 0, 1)) for point in shaft]
                arrow_direction = (world_shaft[1] - world_shaft[0])[:3] / .55
                exported_section = exported.by_guid(section.element.GlobalId)
                camera_matrix = ifcopenshell.util.placement.get_local_placement(exported_section.ObjectPlacement)
                np.testing.assert_allclose(arrow_direction, -camera_matrix[:3, 2], atol=1e-9)

    def test_cut_definition_validates_and_normalizes_inputs(self) -> None:
        cut = CutDefinition([1, 2], [1, 4], " A ")
        self.assertEqual((cut.start, cut.end, cut.identifier, cut.direction),
                         ((1., 2.), (1., 4.), "A", -1))
        with self.assertRaises(AttributeError):
            cut.direction = 1
        for direction in (0, 2, float("nan")):
            with self.assertRaises(ValueError):
                CutDefinition((0, 0), (1, 0), "A", direction)
        with self.assertRaises(TypeError):
            CutDefinition((0, 0), (1, 0), "A", True)
        with self.assertRaisesRegex(ValueError, "different points"):
            CutDefinition((0, 0), (0, 0), "A")
        with self.assertRaisesRegex(ValueError, "identifier"):
            CutDefinition((0, 0), (1, 0), " ")

    def test_adds_cut_symbols_with_two_perpendicular_arrows_and_letters(self) -> None:
        house = House("Cuts")
        ground = house.storey("Ground", elevation=0.4)
        drawing = house.add_drawing("Ground", 2, 2, 1.4, 5, storeys=[ground])
        other = house.add_drawing("Other", 2, 2, 1.4, 5)
        for start, end in (((1, 2), (4, 2)), ((2, 1), (2, 4)), ((1, 1), (4, 5))):
            for direction in (-1, 1):
                with self.subTest(start=start, end=end, direction=direction):
                    before = {a.id() for a in house.model.by_type("IfcAnnotation")}
                    line = drawing.add_cut_symbol(start, end, "A", direction=direction)
                    added = [a for a in house.model.by_type("IfcAnnotation") if a.id() not in before]
                    self.assertEqual(len(added), 5)
                    classes = lambda a: ifcopenshell.util.element.get_pset(a, "EPset_Annotation", "Classes")
                    self.assertEqual(classes(line), "cut-symbol-line")
                    props = ifcopenshell.util.element.get_pset(line, "BBIM_CutSymbol")
                    self.assertEqual(json.loads(props["Start"]), list(start))
                    self.assertEqual(json.loads(props["End"]), list(end))
                    self.assertEqual((props["Identifier"], props["Direction"]), ("A", direction))
                    tangent = np.array(end, dtype=float) - np.array(start)
                    tangent /= np.linalg.norm(tangent)
                    normal = direction * np.array((-tangent[1], tangent[0]))
                    arrows = [a for a in added if classes(a) == "cut-symbol-arrow"]
                    self.assertEqual(len(arrows), 2)
                    for arrow, endpoint in zip(arrows, (start, end)):
                        matrix = ifcopenshell.util.placement.get_local_placement(arrow.ObjectPlacement)
                        np.testing.assert_allclose(matrix[:3, 3], (*endpoint, .4))
                        curves = arrow.Representation.Representations[0].Items[0].Elements
                        shaft = np.array(curves[0].Points.CoordList)
                        np.testing.assert_allclose(shaft[0], -normal * .55)
                        np.testing.assert_allclose(shaft[1], (0, 0))
                        self.assertAlmostEqual(float(np.dot(shaft[1] - shaft[0], tangent)), 0)
                        self.assertGreater(float(np.dot(shaft[1] - shaft[0], normal)), 0)
                        wings = np.array(curves[1].Points.CoordList)
                        np.testing.assert_allclose(wings[1], (0, 0))
                    texts = [a for a in added if classes(a) == "cut-symbol-text"]
                    self.assertEqual(len(texts), 2)
                    for text in texts:
                        self.assertEqual(text.Representation.Representations[0].Items[0].Literal, "A")
                        np.testing.assert_allclose(
                            ifcopenshell.util.placement.get_local_placement(text.ObjectPlacement)[:3, :3],
                            np.eye(3),
                        )
                    self.assertTrue(set(added) <= set(drawing.group.IsGroupedBy[0].RelatedObjects))
                    self.assertTrue(set(added).isdisjoint(other.group.IsGroupedBy[0].RelatedObjects))
        self.assertTrue(ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "HasAnnotation"))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cuts.ifc"
            house.write(path)
            reloaded = ifcopenshell.open(str(path)).by_guid(line.GlobalId)
            self.assertEqual(ifcopenshell.util.element.get_pset(reloaded, "BBIM_CutSymbol", "Identifier"), "A")

    def test_cut_symbols_validate_inputs_without_creating_annotations(self) -> None:
        house = House("Cuts")
        plan = house.add_drawing("Plan", 2, 2, 1, 5)
        elevation = house.add_drawing("AA", 2, 0, 2, 5, view="elevation", direction=(1, 0, 0))
        count = len(house.model.by_type("IfcAnnotation"))
        for direction in (0, 2, -2, float("nan")):
            with self.assertRaises(ValueError):
                plan.add_cut_symbol((0, 0), (1, 0), "A", direction=direction)
        with self.assertRaises(TypeError):
            plan.add_cut_symbol((0, 0), (1, 0), "A", direction=True)
        with self.assertRaisesRegex(ValueError, "different points"):
            plan.add_cut_symbol((1, 1), (1, 1), "A")
        with self.assertRaisesRegex(ValueError, "identifier"):
            plan.add_cut_symbol((0, 0), (1, 0), " ")
        with self.assertRaisesRegex(ValueError, "plan drawings"):
            elevation.add_cut_symbol((0, 0), (1, 0), "A")
        self.assertEqual(len(house.model.by_type("IfcAnnotation")), count)
        line = plan.add_cut_symbol((0, 0), (1, 0), "AA")
        self.assertEqual(ifcopenshell.util.element.get_pset(line, "BBIM_CutSymbol", "Direction"), -1)

    def test_cut_symbol_overlays_are_complete_and_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cut.svg"
            path.write_text('''<svg>
<defs><path id="keep-definition" d="M0 0L1 1"/></defs>
<line class="cut-symbol-line" x1="0" y1="0" x2="5" y2="0"/>
<path class="cut-symbol-arrow" d="M0 0L0 5"/>
<polyline class="cut-symbol-arrow" points="0,0 1,1 2,0"/>
<text><tspan class="cut-symbol-text">A</tspan></text>
<g id="wall"><path d="M0 0L5 0"/></g>
<text class="unrelated">Keep me</text>
</svg>''', encoding="utf-8")
            _postprocess_cut_symbol_overlays(path)
            once = path.read_text()
            _postprocess_cut_symbol_overlays(path)
            self.assertEqual(path.read_text(), once)
            self.assertEqual(once.count('class="cut-symbol-overlays"'), 1)
            self.assertEqual(once.count('class="cut-symbol-arrow"'), 2)
            self.assertGreater(once.index('class="cut-symbol-overlays"'), once.index('id="wall"'))
            self.assertIn('id="keep-definition"', once)
            self.assertIn("Keep me", once)

    def test_adds_arrow_notes_to_plans_and_elevations(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0)
        plan = house.add_drawing("Plan", 2, 2, 1, 5)
        elevation = house.add_drawing(
            "Section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )

        plan_note = plan.add_note(
            point=(1, 2),
            angle=30,
            distance=2,
            text="Poznámka",
        )
        plan_placement = ifcopenshell.util.placement.get_local_placement(
            plan_note.ObjectPlacement
        )
        np.testing.assert_allclose(
            plan_placement[:3, 3],
            (1 + np.sqrt(3), 3, 0),
            atol=1e-9,
        )
        self.assertEqual(
            plan_note.Representation.Representations[0].Items[0].Literal,
            "Poznámka",
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                plan_note,
                "EPset_Annotation",
                "Classes",
            ),
            "note-text",
        )
        self.assertEqual(
            json.loads(
                ifcopenshell.util.element.get_pset(
                    plan_note,
                    "BBIM_Note",
                    "Point",
                )
            ),
            [1.0, 2.0],
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                plan_note,
                "BBIM_Note",
                "Angle",
            ),
            30.0,
        )

        elevation_note = elevation.add_note(
            point=(3, 4),
            angle=90,
            distance=1.5,
            text="Detail",
            name="Section note",
            text_alignment="bottom-right",
        )
        self.assertEqual(
            elevation_note.Representation.Representations[0].Items[0].BoxAlignment,
            "bottom-right",
        )
        np.testing.assert_allclose(
            ifcopenshell.util.placement.get_local_placement(
                elevation_note.ObjectPlacement
            ),
            np.array(
                (
                    (0, 0, -1, 2),
                    (-1, 0, 0, 3),
                    (0, 1, 0, 5.5),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-9,
        )
        leader = next(
            annotation
            for annotation in elevation.group.IsGroupedBy[0].RelatedObjects
            if annotation.Name == "Section note Leader"
        )
        np.testing.assert_allclose(
            ifcopenshell.util.placement.get_local_placement(
                leader.ObjectPlacement
            )[:3, 0],
            (0, 0, -1),
            atol=1e-9,
        )
        self.assertEqual(
            leader.Representation.Representations[0].Items[0].Points.CoordList,
            ((0.0, 0.0), (1.5, 0.0)),
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                leader,
                "EPset_Annotation",
                "Classes",
            ),
            "note-leader",
        )
        self.assertIn(elevation_note, elevation.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(leader, elevation.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(elevation_note, plan.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(
            'id="note-arrow-marker"',
            Path("drawings/assets/markers.svg").read_text(),
        )
        self.assertIn(
            ".PredefinedType-LINEWORK.note-leader",
            Path("bonsai_scripts/assets/plan.css").read_text(),
        )

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            plan.add_note((1, 2), 0, 0, "Invalid")
        with self.assertRaisesRegex(ValueError, "text_alignment"):
            plan.add_note(
                (1, 2),
                0,
                1,
                "Invalid",
                text_alignment="center",
            )
        oblique = house.add_drawing(
            "Oblique section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 1, 0),
        )
        with self.assertRaisesRegex(ValueError, "axis-aligned"):
            oblique.add_note((3, 4), 0, 1, "Invalid")

    def test_adds_camera_facing_ridge_tile_to_elevation(self) -> None:
        house = House("My house")
        house.storey("Ground floor", elevation=0)
        drawing = house.add_drawing(
            "Section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )
        other_drawing = house.add_drawing(
            "Other section",
            2,
            0,
            2,
            5,
            view="elevation",
            direction=(1, 0, 0),
        )

        ridge_tile = drawing.add_ridge_tile(
            (2, 3, 4),
            width=0.40,
            rise=0.12,
            thickness=0.025,
        )

        self.assertEqual(ridge_tile.ObjectType, "FILLAREA")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                ridge_tile,
                "EPset_Annotation",
                "Classes",
            ),
            "ridge-tile",
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            ridge_tile.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement,
            np.array(
                (
                    (0, 0, -1, 2),
                    (-1, 0, 0, 3),
                    (0, 1, 0, 4),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-9,
        )
        points = (
            ridge_tile.Representation.Representations[0]
            .Items[0]
            .OuterBoundary.Points.CoordList
        )
        self.assertEqual(len(points), 51)
        self.assertAlmostEqual(min(point[0] for point in points), -0.20)
        self.assertAlmostEqual(max(point[0] for point in points), 0.20)
        self.assertAlmostEqual(max(point[1] for point in points), 0.025)
        self.assertIn(ridge_tile, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(
            ridge_tile,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertTrue(
            ifcopenshell.util.element.get_pset(
                drawing.element,
                "EPset_Drawing",
                "HasAnnotation",
            )
        )

        plan = house.add_drawing("Plan", 2, 2, 1, 5)
        with self.assertRaisesRegex(ValueError, "elevation"):
            plan.add_ridge_tile(
                (2, 3, 4),
                width=0.40,
                rise=0.12,
                thickness=0.025,
            )
        with self.assertRaisesRegex(ValueError, "half the width"):
            drawing.add_ridge_tile(
                (2, 3, 4),
                width=0.04,
                rise=0.12,
                thickness=0.025,
            )

    def test_adds_merged_dashed_wall_outlines_without_junction_seams(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        horizontal = ground.wall(
            (0, 0), (4, 0), thickness=1, height=2.8
        )
        vertical = ground.wall(
            (2, 0), (2, 2), thickness=1, height=2.8
        )
        drawing = house.add_drawing(
            "Foundation", 2, 1, -1, 4, storeys=[ground]
        )
        other_drawing = house.add_drawing(
            "Other plan", 2, 1, -1, 4, storeys=[ground]
        )

        outline = drawing.add_wall_outlines(
            (horizontal, vertical),
            style="dashed",
        )

        self.assertEqual(outline.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                outline, "EPset_Annotation", "Classes"
            ),
            "load-bearing-wall-outline dashed",
        )
        curves = outline.Representation.Representations[0].Items[0].Elements
        self.assertEqual(len(curves), 1)
        points = [
            tuple(round(float(coordinate), 9) for coordinate in point)
            for point in curves[0].Points.CoordList
        ]
        self.assertEqual(len(points), 9)
        self.assertEqual(
            set(points),
            {
                (0.0, -0.5),
                (4.0, -0.5),
                (4.0, 0.5),
                (2.5, 0.5),
                (2.5, 2.0),
                (1.5, 2.0),
                (1.5, 0.5),
                (0.0, 0.5),
            },
        )
        self.assertIn(outline, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertNotIn(
            outline,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )

    def test_styles_wall_outlines_and_roof_openings_dashed_but_doors_solid(self) -> None:
        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        shared_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.load-bearing-wall-outline", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(
            ".PredefinedType-LINEWORK.roof-opening",
            shared_rule,
        )
        self.assertIn("stroke-width: 0.1 !important", shared_rule)
        self.assertIn("stroke-dasharray: 0.7 0.8 !important", shared_rule)
        door_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.door-overhead {", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke-width: 0.1 !important", door_rule)
        self.assertIn("stroke-dasharray: none !important", door_rule)

        roof_opening_rule = stylesheet.split(
            ".roof-opening-mask", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", roof_opening_rule)
        self.assertIn("stroke: none !important", roof_opening_rule)
        self.assertIn(
            ".PredefinedType-LINEWORK.roof-opening-mask-source",
            stylesheet,
        )

    def test_adds_white_backed_dashed_roof_opening_outline(self) -> None:
        house = House("My house")
        upper = house.storey("Upper floor", elevation=3)
        roof = upper.roof("Main roof")
        opening = roof.add_opening(
            "Bedroom roof window",
            rectangle=((3, 2), (2, 1)),
        )
        drawing = house.add_drawing(
            "Roof plan",
            2,
            2,
            8,
            5,
            storeys=[upper],
        )
        other_drawing = house.add_drawing(
            "Other plan",
            2,
            2,
            8,
            5,
            storeys=[upper],
        )

        outline = drawing.add_roof_opening_outline(opening)

        self.assertEqual(outline.ObjectType, "LINEWORK")
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                outline,
                "EPset_Annotation",
                "Classes",
            ),
            "roof-opening dashed",
        )
        curve = outline.Representation.Representations[0].Items[0].Elements[0]
        self.assertEqual(
            [tuple(point) for point in curve.Points.CoordList],
            [
                (2.05, 1.05),
                (2.95, 1.05),
                (2.95, 1.95),
                (2.05, 1.95),
                (2.05, 1.05),
            ],
        )
        mask_source = next(
            annotation
            for annotation in drawing.group.IsGroupedBy[0].RelatedObjects
            if ifcopenshell.util.element.get_pset(
                annotation,
                "EPset_Annotation",
                "Classes",
            )
            == "roof-opening-mask-source"
        )
        mask_curve = (
            mask_source.Representation.Representations[0].Items[0].Elements[0]
        )
        self.assertEqual(
            [tuple(point) for point in mask_curve.Points.CoordList],
            [
                (2.02, 1.0),
                (2.98, 1.0),
                (2.98, 2.0),
                (2.02, 2.0),
                (2.02, 1.0),
            ],
        )
        placement = ifcopenshell.util.placement.get_local_placement(
            outline.ObjectPlacement
        )
        self.assertAlmostEqual(placement[2, 3], 3)
        self.assertIn(outline, drawing.group.IsGroupedBy[0].RelatedObjects)
        self.assertIn(
            mask_source,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertNotIn(
            outline,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertNotIn(
            mask_source,
            other_drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        unmasked_drawing = house.add_drawing(
            "Unmasked roof plan",
            2,
            2,
            8,
            5,
            storeys=[upper],
        )
        unmasked_outline = unmasked_drawing.add_roof_opening_outline(
            opening,
            y_min_inset=0.1,
            mask=False,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                unmasked_outline,
                "EPset_Annotation",
                "Classes",
            ),
            "roof-opening roof-opening-unmasked dashed",
        )
        unmasked_curve = (
            unmasked_outline.Representation.Representations[0].Items[0].Elements[0]
        )
        self.assertEqual(
            [tuple(point) for point in unmasked_curve.Points.CoordList],
            [
                (2.05, 1.1),
                (2.95, 1.1),
                (2.95, 1.95),
                (2.05, 1.95),
                (2.05, 1.1),
            ],
        )
        self.assertFalse(
            any(
                ifcopenshell.util.element.get_pset(
                    annotation,
                    "EPset_Annotation",
                    "Classes",
                )
                == "roof-opening-mask-source"
                for annotation in unmasked_drawing.group.IsGroupedBy[0].RelatedObjects
            )
        )
        with self.assertRaisesRegex(ValueError, "already has an outline"):
            drawing.add_roof_opening_outline(opening)
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            other_drawing.add_roof_opening_outline(opening, inset=-0.01)
        with self.assertRaisesRegex(ValueError, "y_min_inset"):
            other_drawing.add_roof_opening_outline(
                opening,
                y_min_inset=-0.01,
            )
        with self.assertRaisesRegex(ValueError, "non-empty"):
            other_drawing.add_roof_opening_outline(opening, inset=0.5)
        with self.assertRaisesRegex(ValueError, "non-empty"):
            other_drawing.add_roof_opening_outline(
                opening,
                y_min_inset=0.95,
            )
        with self.assertRaisesRegex(ValueError, "mask_horizontal_inset"):
            other_drawing.add_roof_opening_outline(
                opening,
                mask_horizontal_inset=-0.01,
            )
        with self.assertRaisesRegex(ValueError, "non-empty roof opening mask"):
            other_drawing.add_roof_opening_outline(
                opening,
                mask_horizontal_inset=0.5,
            )
        with self.assertRaisesRegex(TypeError, "mask must be a boolean"):
            other_drawing.add_roof_opening_outline(opening, mask="no")

        elevation = house.add_drawing(
            "Elevation",
            2,
            0,
            3,
            5,
            view="elevation",
            direction=(0, 1, 0),
        )
        with self.assertRaisesRegex(ValueError, "only supported for plan"):
            elevation.add_roof_opening_outline(opening)

    def test_adds_direction_aware_wall_batting_split_at_openings(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall_type = house.wall_type(
            "Facade wall",
            layers=[
                ("Brick", 0.24),
                "axis",
                ("Rockwool", 0.20),
            ],
        )
        horizontal = ground.wall(
            (0, 0), (4, 0), wall_type=wall_type, height=2.8
        )
        horizontal.add_opening(at=1, width=1, height=2)
        vertical = ground.wall(
            (5, 0), (5, 4), wall_type=wall_type, height=2.8
        )
        drawing = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )

        split_batting = drawing.add_wall_batting(
            horizontal,
            side="right",
            thickness=0.20,
            name="Horizontal Rockwool",
        )
        vertical_batting = drawing.add_wall_batting(
            vertical,
            side="right",
            thickness=0.20,
        )

        self.assertEqual(len(split_batting), 2)
        self.assertEqual(
            [annotation.Name for annotation in split_batting],
            ["Horizontal Rockwool 1", "Horizontal Rockwool 2"],
        )
        horizontal_placements = [
            ifcopenshell.util.placement.get_local_placement(
                annotation.ObjectPlacement
            )
            for annotation in split_batting
        ]
        np.testing.assert_allclose(
            horizontal_placements[0][:3, 3], (0, -0.1, 0), atol=1e-9
        )
        np.testing.assert_allclose(
            horizontal_placements[1][:3, 3], (2, -0.1, 0), atol=1e-9
        )
        vertical_placement = ifcopenshell.util.placement.get_local_placement(
            vertical_batting[0].ObjectPlacement
        )
        np.testing.assert_allclose(
            vertical_placement[:3, 3], (5.1, 0, 0), atol=1e-9
        )
        np.testing.assert_allclose(
            vertical_placement[:3, 0], (0, 1, 0), atol=1e-9
        )
        self.assertEqual(
            {
                ifcopenshell.util.element.get_pset(
                    annotation, "BBIM_Batting", "Thickness"
                )
                for annotation in (*split_batting, *vertical_batting)
            },
            {0.20},
        )

    def test_adds_opening_aware_polystyrene_wall_insulation(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall(
            (0, 0), (4, 0), thickness=0.24, height=3
        )
        wall.add_opening(
            at=1,
            width=1,
            height=2,
            show_overhead=False,
        )
        # This high opening does not intersect the drawing cut and therefore
        # must not interrupt the insulation hatch.
        wall.add_opening(
            at=2.5,
            width=0.5,
            sill_height=2,
            height=2.8,
            show_overhead=False,
        )
        drawing = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )

        insulation = drawing.add_wall_insulation(
            wall,
            thickness=0.16,
            material="polystyrene",
            start_extension=0.2,
            end_extension=0.3,
        )

        self.assertEqual(len(insulation), 1)
        annotation = insulation[0]
        self.assertEqual(annotation.ObjectType, "FILLAREA")
        placement = ifcopenshell.util.placement.get_local_placement(
            annotation.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement[:3, 3], (0, 0, 0), atol=1e-9
        )
        representation = annotation.Representation.Representations[0]
        self.assertEqual(representation.RepresentationType, "Annotation2D")
        self.assertEqual(len(representation.Items), 2)
        self.assertEqual(
            [item.OuterBoundary.Points.CoordList for item in representation.Items],
            [
                (
                    (-0.2, -0.28),
                    (1.0, -0.28),
                    (1.0, -0.12),
                    (-0.2, -0.12),
                    (-0.2, -0.28),
                ),
                (
                    (2.0, -0.28),
                    (4.3, -0.28),
                    (4.3, -0.12),
                    (2.0, -0.12),
                    (2.0, -0.28),
                ),
            ],
        )
        self.assertEqual(
            ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            ),
            "wall-insulation wall-insulation-polystyrene",
        )
        properties = ifcopenshell.util.element.get_pset(
            annotation, "BBIM_WallInsulation"
        )
        self.assertEqual(properties["HostWall"], wall.GlobalId)
        self.assertEqual(properties["Material"], "polystyrene")
        self.assertEqual(properties["Thickness"], 0.16)
        self.assertAlmostEqual(properties["DrawnThickness"], 0.16)
        self.assertEqual(properties["WallOutlineClearance"], 0.0)
        self.assertEqual(properties["Side"], "right")
        self.assertEqual(properties["StartExtension"], 0.2)
        self.assertEqual(properties["EndExtension"], 0.3)
        self.assertEqual(
            json.loads(properties["Segments"]),
            [[-0.2, 1.0], [2.0, 4.3]],
        )
        self.assertIn(
            annotation,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        opening_boundary = next(
            candidate
            for candidate in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                candidate, "EPset_Annotation", "Classes"
            )
            == (
                "wall-insulation wall-insulation-polystyrene-opening "
                "wall-insulation-opening"
            )
        )
        opening_curves = (
            opening_boundary.Representation.Representations[0]
            .Items[0]
            .Elements
        )
        self.assertEqual(len(opening_curves), 1)
        self.assertEqual(
            opening_curves[0].Points.CoordList,
            ((1.0, -0.28), (2.0, -0.28)),
        )

    def test_adds_extended_rockwool_outside_the_wall_face(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall(
            (5, 0), (5, 4), thickness=0.24, height=3
        )
        wall.add_opening(
            at=0.8,
            width=0.5,
            height=2,
            show_overhead=False,
        )
        drawing = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )

        insulation = drawing.add_wall_insulation(
            wall,
            thickness=0.20,
            material="Rockwool",
            start_extension=0.1,
            end_extension=-0.2,
            name="Facade wool",
        )

        self.assertEqual(len(insulation), 2)
        self.assertEqual(
            [annotation.Name for annotation in insulation],
            ["Facade wool 1", "Facade wool 2"],
        )
        placements = [
            ifcopenshell.util.placement.get_local_placement(
                annotation.ObjectPlacement
            )
            for annotation in insulation
        ]
        np.testing.assert_allclose(
            placements[0][:3, 3], (5.22, -0.07, 0), atol=1e-9
        )
        np.testing.assert_allclose(
            placements[1][:3, 3], (5.22, 1.33, 0), atol=1e-9
        )
        for annotation in insulation:
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    annotation, "EPset_Annotation", "Classes"
                ),
                "wall-insulation wall-insulation-rockwool",
            )
            properties = ifcopenshell.util.element.get_pset(
                annotation, "BBIM_WallInsulation"
            )
            self.assertEqual(properties["HostWall"], wall.GlobalId)
            self.assertEqual(properties["Material"], "rockwool")
            self.assertEqual(properties["Thickness"], 0.20)
            self.assertAlmostEqual(properties["DrawnThickness"], 0.20)
            self.assertAlmostEqual(properties["BattingThickness"], 0.16)
            self.assertAlmostEqual(properties["BattingInset"], 0.02)
            self.assertEqual(properties["BattingEndInset"], 0.03)
            self.assertEqual(properties["WallOutlineClearance"], 0.0)
            self.assertEqual(properties["StartExtension"], 0.1)
            self.assertEqual(properties["EndExtension"], -0.2)
            self.assertAlmostEqual(
                ifcopenshell.util.element.get_pset(
                    annotation, "BBIM_Batting", "Thickness"
                ),
                0.16,
            )

        boundary = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            )
            == "wall-insulation wall-insulation-rockwool-boundary"
        )
        self.assertEqual(boundary.Name, "Facade wool Boundary")
        boundary_curves = (
            boundary.Representation.Representations[0].Items[0].Elements
        )
        self.assertEqual(len(boundary_curves), 2)
        self.assertEqual(
            boundary_curves[0].Points.CoordList,
            (
                (-0.1, -0.32),
                (0.8, -0.32),
                (0.8, -0.12),
                (-0.1, -0.12),
                (-0.1, -0.32),
            ),
        )
        self.assertIn(boundary, drawing.group.IsGroupedBy[0].RelatedObjects)

        opening_boundary = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            )
            == (
                "wall-insulation wall-insulation-rockwool-opening "
                "wall-insulation-opening"
            )
        )
        self.assertEqual(
            opening_boundary.Name,
            "Facade wool Opening Boundary",
        )
        opening_curves = (
            opening_boundary.Representation.Representations[0]
            .Items[0]
            .Elements
        )
        self.assertEqual(len(opening_curves), 1)
        self.assertEqual(
            opening_curves[0].Points.CoordList,
            ((0.8, -0.32), (1.3, -0.32)),
        )
        self.assertIn(
            opening_boundary,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )

    def test_resolves_zero_wall_insulation_extensions_for_corners(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (2, 0), thickness=0.24, height=3)
        drawing = house.add_drawing(
            "Ground plan", 1, 1, 1, 4, storeys=[ground]
        )

        annotation = drawing.add_wall_insulation(
            wall,
            thickness=0.16,
            material="polystyrene",
        )[0]

        fill_area = annotation.Representation.Representations[0].Items[0]
        self.assertEqual(
            fill_area.OuterBoundary.Points.CoordList,
            (
                (-0.0175, -0.28),
                (2.0175, -0.28),
                (2.0175, -0.12),
                (-0.0175, -0.12),
                (-0.0175, -0.28),
            ),
        )
        properties = ifcopenshell.util.element.get_pset(
            annotation, "BBIM_WallInsulation"
        )
        self.assertEqual(properties["StartExtension"], 0.0175)
        self.assertEqual(properties["EndExtension"], 0.0175)
        self.assertEqual(
            json.loads(properties["Segments"]),
            [[-0.0175, 2.0175]],
        )

    def test_sets_wall_insulation_ends_with_absolute_coordinates(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        horizontal_wall = ground.wall(
            (5, 2), (1, 2), thickness=0.24, height=3
        )
        vertical_wall = ground.wall(
            (2, 5), (2, 1), thickness=0.24, height=3
        )
        drawing = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )

        horizontal = drawing.add_wall_insulation(
            horizontal_wall,
            thickness=0.16,
            material="polystyrene",
            start_x=0.75,
            end_x=5.5,
        )[0]
        vertical = drawing.add_wall_insulation(
            vertical_wall,
            thickness=0.16,
            material="polystyrene",
            start_y=1.5,
            end_y=5.25,
        )[0]

        horizontal_properties = ifcopenshell.util.element.get_pset(
            horizontal, "BBIM_WallInsulation"
        )
        self.assertEqual(horizontal_properties["StartExtension"], 0.5)
        self.assertEqual(horizontal_properties["EndExtension"], 0.25)
        self.assertEqual(
            json.loads(horizontal_properties["Segments"]),
            [[-0.5, 4.25]],
        )
        vertical_properties = ifcopenshell.util.element.get_pset(
            vertical, "BBIM_WallInsulation"
        )
        self.assertEqual(vertical_properties["StartExtension"], 0.25)
        self.assertEqual(vertical_properties["EndExtension"], -0.5)
        self.assertEqual(
            json.loads(vertical_properties["Segments"]),
            [[-0.25, 3.5]],
        )

    def test_adds_opening_aware_polystyrene_to_elevation_section(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0.2)
        wall = ground.wall(
            (0, 0),
            (4, 0),
            thickness=0.24,
            height=3,
            start_height=0.1,
        )
        wall.add_opening(
            at=1,
            width=1,
            sill_height=0.8,
            height=2,
            show_overhead=False,
        )
        drawing = house.add_drawing(
            "Wall section",
            1.5,
            0,
            2,
            5,
            view="elevation",
            direction=(-1, 0, 0),
        )

        insulation = drawing.add_wall_insulation(
            wall,
            thickness=0.16,
            material="polystyrene",
            start_z=3,
            end_z=0.5,
        )

        self.assertEqual(len(insulation), 1)
        annotation = insulation[0]
        placement = ifcopenshell.util.placement.get_local_placement(
            annotation.ObjectPlacement
        )
        np.testing.assert_allclose(
            placement,
            (
                (0, 0, 1, 1.5),
                (1, 0, 0, 0),
                (0, 1, 0, 0),
                (0, 0, 0, 1),
            ),
            atol=1e-9,
        )
        self.assertEqual(
            [
                item.OuterBoundary.Points.CoordList
                for item in annotation.Representation.Representations[0].Items
            ],
            [
                (
                    (-0.28, 0.5),
                    (-0.12, 0.5),
                    (-0.12, 1.0),
                    (-0.28, 1.0),
                    (-0.28, 0.5),
                ),
                (
                    (-0.28, 2.2),
                    (-0.12, 2.2),
                    (-0.12, 3.0),
                    (-0.28, 3.0),
                    (-0.28, 2.2),
                ),
            ],
        )
        properties = ifcopenshell.util.element.get_pset(
            annotation, "BBIM_WallInsulation"
        )
        self.assertEqual(properties["StartZ"], 0.5)
        self.assertEqual(properties["EndZ"], 3.0)
        self.assertEqual(
            json.loads(properties["Segments"]),
            [[0.5, 1.0], [2.2, 3.0]],
        )
        self.assertTrue(
            ifcopenshell.util.element.get_pset(
                drawing.element, "EPset_Drawing", "HasAnnotation"
            )
        )
        opening_boundary = next(
            candidate
            for candidate in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                candidate, "EPset_Annotation", "Classes"
            )
            == (
                "wall-insulation wall-insulation-polystyrene-opening "
                "wall-insulation-opening"
            )
        )
        opening_curve = (
            opening_boundary.Representation.Representations[0]
            .Items[0]
            .Elements[0]
        )
        self.assertEqual(
            opening_curve.Points.CoordList,
            ((-0.28, 1.0), (-0.28, 2.2)),
        )

    def test_adds_xps_wall_insulation_with_its_own_material_class(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall(
            (0, 0), (4, 0), thickness=0.24, height=3
        )
        plan = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )
        section = house.add_drawing(
            "Wall section",
            1.5,
            0,
            1.5,
            4,
            view="elevation",
            direction=(-1, 0, 0),
        )

        plan_annotation = plan.add_wall_insulation(
            wall, thickness=0.16, material="XPS"
        )[0]
        section_annotation = section.add_wall_insulation(
            wall,
            thickness=0.16,
            material="xps",
            start_z=-1,
            end_z=0.3,
        )[0]

        for annotation in (plan_annotation, section_annotation):
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    annotation, "EPset_Annotation", "Classes"
                ),
                "wall-insulation wall-insulation-xps",
            )
            self.assertEqual(
                ifcopenshell.util.element.get_pset(
                    annotation, "BBIM_WallInsulation", "Material"
                ),
                "xps",
            )

    def test_adds_rockwool_batting_to_elevation_section(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall(
            (0, 0), (4, 0), thickness=0.24, height=3
        )
        wall.add_opening(
            at=1,
            width=1,
            sill_height=0.8,
            height=2,
            show_overhead=False,
        )
        drawing = house.add_drawing(
            "Wall section",
            1.5,
            0,
            1.5,
            4,
            view="elevation",
            direction=(-1, 0, 0),
        )

        insulation = drawing.add_wall_insulation(
            wall,
            thickness=0.20,
            material="rockwool",
        )

        self.assertEqual(len(insulation), 2)
        placements = [
            ifcopenshell.util.placement.get_local_placement(
                annotation.ObjectPlacement
            )
            for annotation in insulation
        ]
        np.testing.assert_allclose(
            placements[0][:3, 3], (1.5, -0.22, 0.03), atol=1e-9
        )
        np.testing.assert_allclose(
            placements[1][:3, 3], (1.5, -0.22, 2.03), atol=1e-9
        )
        np.testing.assert_allclose(
            placements[0][:3, :3],
            ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
            atol=1e-9,
        )
        np.testing.assert_allclose(
            [
                annotation.Representation.Representations[0]
                .Items[0]
                .Points.CoordList
                for annotation in insulation
            ],
            [((0.0, 0.0), (0.74, 0.0)), ((0.0, 0.0), (0.94, 0.0))],
            atol=1e-9,
        )
        self.assertTrue(
            all(
                ifcopenshell.util.element.get_pset(
                    annotation, "BBIM_Batting", "Thickness"
                )
                == 0.16
                for annotation in insulation
            )
        )
        boundary = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            )
            == "wall-insulation wall-insulation-rockwool-boundary"
        )
        self.assertEqual(
            [
                curve.Points.CoordList
                for curve in boundary.Representation.Representations[0]
                .Items[0]
                .Elements
            ],
            [
                (
                    (-0.32, 0.0),
                    (-0.12, 0.0),
                    (-0.12, 0.8),
                    (-0.32, 0.8),
                    (-0.32, 0.0),
                ),
                (
                    (-0.32, 2.0),
                    (-0.12, 2.0),
                    (-0.12, 3.0),
                    (-0.32, 3.0),
                    (-0.32, 2.0),
                ),
            ],
        )

    def test_validates_wall_insulation_arguments(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        wall = ground.wall((0, 0), (4, 0), thickness=0.24, height=3)
        vertical_wall = ground.wall(
            (0, 0), (0, 4), thickness=0.24, height=3
        )
        upper_wall = upper.wall(
            (0, 0), (4, 0), thickness=0.24, height=3
        )
        drawing = house.add_drawing(
            "Ground plan", 2, 2, 1, 6, storeys=[ground]
        )

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            drawing.add_wall_insulation(
                wall, thickness=0, material="polystyrene"
            )
        with self.assertRaisesRegex(ValueError, "material must be one of"):
            drawing.add_wall_insulation(
                wall, thickness=0.16, material="foam"
            )
        with self.assertRaisesRegex(ValueError, "not included"):
            drawing.add_wall_insulation(
                upper_wall,
                thickness=0.16,
                material="polystyrene",
            )
        with self.assertRaisesRegex(ValueError, "horizontal walls"):
            drawing.add_wall_insulation(
                vertical_wall,
                thickness=0.16,
                material="polystyrene",
                start_x=0,
            )
        with self.assertRaisesRegex(ValueError, "vertical walls"):
            drawing.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_y=0,
            )
        with self.assertRaisesRegex(ValueError, "must not be mixed"):
            drawing.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_x=0,
                end_y=4,
            )
        with self.assertRaisesRegex(ValueError, "are alternatives"):
            drawing.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_extension=0.2,
                start_x=-0.2,
            )
        with self.assertRaisesRegex(ValueError, "must precede"):
            drawing.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_extension=-3,
                end_extension=-2,
            )
        with self.assertRaisesRegex(ValueError, "elevation drawings"):
            drawing.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_z=0,
            )
        elevation = house.add_drawing(
            "Elevation",
            2,
            -2,
            1,
            6,
            view="elevation",
            direction=(0, 1, 0),
        )
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            elevation.add_wall_insulation(
                wall, thickness=0.16, material="polystyrene"
            )
        section = house.add_drawing(
            "Section",
            2,
            0,
            1,
            6,
            view="elevation",
            direction=(-1, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "plan drawings"):
            section.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_x=0,
            )
        with self.assertRaisesRegex(ValueError, "use start_z and end_z"):
            section.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_extension=0.2,
            )
        with self.assertRaisesRegex(ValueError, "must be different"):
            section.add_wall_insulation(
                wall,
                thickness=0.16,
                material="polystyrene",
                start_z=1,
                end_z=1,
            )

    def test_persists_material_legend_in_an_optional_right_panel(self) -> None:
        house = House("My house")
        drawing = house.add_drawing(
            "Ground plan",
            2,
            3,
            1.6,
            5,
            right_panel_width=90,
        )

        result = drawing.add_material_legend(
            [
                (
                    "diagonal1",
                    "OBVODOVÉ ZDIVO Z BROUŠENÝCH KERAMICKÝCH TVÁRNIC",
                ),
                (
                    "crosshatch1",
                    "ZTRACENÉ BEDNĚNÍ\nPROLITÉ BETONEM C 20/25",
                ),
            ],
            title="LEGENDA MATERIÁLŮ",
        )

        self.assertIs(result, drawing)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(properties["RightPanelWidth"], 90)
        self.assertEqual(
            json.loads(properties["RightPanelTables"]),
            [
                {
                    "kind": "material_legend",
                    "title": "LEGENDA MATERIÁLŮ",
                    "items": [
                        {
                            "pattern": "diagonal1",
                            "description": (
                                "OBVODOVÉ ZDIVO Z BROUŠENÝCH "
                                "KERAMICKÝCH TVÁRNIC"
                            ),
                        },
                        {
                            "pattern": "crosshatch1",
                            "description": (
                                "ZTRACENÉ BEDNĚNÍ\nPROLITÉ BETONEM C 20/25"
                            ),
                        },
                    ],
                }
            ],
        )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "legend.ifc"
            house.write(path)
            reopened = ifcopenshell.open(path)
            reopened_drawing = reopened.by_guid(drawing.element.GlobalId)
            reopened_properties = ifcopenshell.util.element.get_pset(
                reopened_drawing,
                "EPset_Drawing",
            )
            self.assertIn(
                "LEGENDA MATERIÁLŮ",
                reopened_properties["RightPanelTables"],
            )

        no_panel = house.add_drawing("No panel", 2, 3, 1.6, 5)
        with self.assertRaisesRegex(ValueError, "requires right_panel_width"):
            no_panel.add_material_legend([("brick", "Masonry")])
        narrow_panel = house.add_drawing(
            "Narrow panel", 2, 3, 1.6, 5, right_panel_width=30
        )
        with self.assertRaisesRegex(ValueError, "at least 40 mm"):
            narrow_panel.add_material_legend([("brick", "Masonry")])
        with self.assertRaisesRegex(ValueError, "is not available"):
            drawing.add_material_legend([("unknown", "Masonry")])
        with self.assertRaisesRegex(ValueError, "at least one material"):
            drawing.add_material_legend([])
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            house.add_drawing(
                "Invalid panel",
                2,
                3,
                1.6,
                5,
                right_panel_width=-1,
            )

    def test_mdf_legend_swatch_is_solid_without_batting(self) -> None:
        house = House("MDF legend")
        drawing = house.add_drawing("AA", 0, 0, 2, 4, storeys=[], right_panel_width=60)
        drawing.add_material_legend([("mdf-solid", "MDF deska")])
        properties = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing")
        patterns = ET.parse(Path(__file__).parent / "drawings/assets/patterns.svg")
        pattern = next(p for p in patterns.getroot().iter() if p.get("id") == "mdf-solid")
        self.assertEqual(len(pattern), 1)
        self.assertTrue(pattern[0].tag.endswith("}rect"))
        self.assertEqual(pattern[0].get("fill"), "#c9b56d")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "drawing.svg"
            path.write_text('<svg width="160mm" height="160mm" viewBox="0 0 160 160">'
                            '<defs></defs><g id="model-view"/></svg>', encoding="utf-8")
            _postprocess_right_panel(path, properties)
            svg = path.read_text(encoding="utf-8")
        self.assertIn("MDF deska", svg)
        self.assertIn('fill="url(#mdf-solid)"', svg)
        self.assertNotIn('class="material-legend-batting', svg)

    def test_appends_material_legend_and_expands_svg_sheet(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                "  <defs>"
                '<pattern id="diagonal1" width="2" height="2"/>'
                "</defs>\n"
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 40,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "material_legend",
                            "title": "LEGENDA & MATERIÁLY",
                            "items": [
                                {
                                    "pattern": "diagonal1",
                                    "description": (
                                        "A manually wrapped description\n"
                                        "continues on the next line"
                                    ),
                                },
                                {
                                    "pattern": "crosshatch1",
                                    "description": (
                                        "Nosná zeď - VPC Cihla 240 mm"
                                    ),
                                },
                                {
                                    "pattern": "rockwool-wave",
                                    "description": "Rockwool 200 mm",
                                },
                                {
                                    "pattern": "pavatex-wave",
                                    "description": "PAVATEX 100 mm",
                                },
                            ],
                        }
                    ],
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn('width="200mm"', svg)
            self.assertIn('height="160mm"', svg)
            self.assertIn('viewBox="0 0 200 160"', svg)
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertIn('x="160"', svg)
            self.assertIn('width="40"', svg)
            self.assertIn(
                'class="right-panel-table-outline" x="162" '
                'y="5" width="36"',
                svg,
            )
            self.assertIn('style="font-size:1.83333px"', svg)
            self.assertGreaterEqual(
                svg.count('style="font-size:1.46667px"'),
                4,
            )
            self.assertIn('fill="url(#diagonal1)"', svg)
            self.assertIn('fill="url(#crosshatch1)"', svg)
            self.assertIn('class="material-legend-batting"', svg)
            self.assertIn(
                'class="material-legend-batting material-legend-pavatex"',
                svg,
            )
            self.assertIn('fill="#c9b56d"', svg)
            self.assertIn(_BATTING_MARKER_PATH, svg)
            self.assertNotIn('fill="url(#rockwool-wave)"', svg)
            self.assertIn("LEGENDA &amp; MATERIÁLY", svg)
            self.assertGreaterEqual(
                svg.count('<tspan x="'),
                3,
            )
            self.assertRegex(
                svg,
                r'<tspan[^>]*>Nosná zeď - VPC Cihla 240 mm</tspan>',
            )
            self.assertRegex(
                svg,
                r'<tspan[^>]*>continues on the next line</tspan>',
            )
            self.assertGreater(
                svg.index('class="right-side-panel"'),
                svg.index('id="model-view"'),
            )

    def test_appends_room_legend_to_right_panel(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                '  <defs><pattern id="brick-tint-f4d35e"/></defs>\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 40,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "room_legend",
                            "title": "LEGENDA MÍSTNOSTÍ",
                            "items": [
                                {
                                    "identifier": "P.01",
                                    "description": "Pokoj & pracovna",
                                    "area": 12.345,
                                },
                                {
                                    "identifier": "P.02",
                                    "description": "Galerie",
                                    "area": 8,
                                },
                            ],
                        }
                    ]
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertEqual(svg.count('class="right-panel-table room-legend"'), 1)
            self.assertIn("LEGENDA MÍSTNOSTÍ", svg)
            self.assertIn(">ČÍSLO</text>", svg)
            self.assertIn(">POPIS</text>", svg)
            self.assertIn(">PLOCHA</text>", svg)
            self.assertNotIn(">PLOCHA OKEN</text>", svg)
            self.assertIn("Pokoj &amp; pracovna", svg)
            self.assertIn("12,35 m²", svg)
            self.assertIn("8,00 m²", svg)

    def test_appends_lintel_legend_to_right_panel(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 40,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "lintel_legend",
                            "title": "LEGENDA PŘEKLADŮ",
                            "items": [
                                {
                                    "number": "1",
                                    "width": 1.125,
                                    "bearing": 0.1875,
                                    "count": 1,
                                },
                                {
                                    "number": "2",
                                    "width": 1.0,
                                    "bearing": 0.125,
                                    "count": 4,
                                },
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertEqual(
                svg.count('class="right-panel-table lintel-legend"'),
                1,
            )
            self.assertIn("LEGENDA PŘEKLADŮ", svg)
            self.assertIn(">OZNAČENÍ</text>", svg)
            self.assertIn(">ŠÍŘKA</text>", svg)
            self.assertIn(">ULOŽENÍ</text>", svg)
            self.assertIn(">POČET</text>", svg)
            self.assertEqual(svg.count(">Př</text>"), 2)
            self.assertIn(">1125 mm</text>", svg)
            self.assertIn(">187,5 mm</text>", svg)
            self.assertIn(">1000 mm</text>", svg)
            self.assertIn(">125 mm</text>", svg)
            self.assertEqual(svg.count('class="lintel-legend-symbol"'), 2)

    def test_appends_wrapped_notes_to_right_panel(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="80mm" '
                'viewBox="0 0 160 80">\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 65,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "notes",
                            "title": "POZNÁMKY",
                            "layout_scale": 0.5,
                            "items": [
                                {
                                    "text": (
                                        "Hlavní krokve které maji osovou "
                                        "vzdálenost od sousedních krokví "
                                        "> 75 cm musí mít pevnostní třídu "
                                        "C24. Pro ostatní prvky dostačuje C22"
                                    )
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertEqual(
                svg.count('class="right-panel-table notes-section"'),
                1,
            )
            self.assertIn("POZNÁMKY", svg)
            self.assertIn('class="notes-bullet"', svg)
            self.assertIn("&gt;", svg)
            self.assertIn("75 cm", svg)
            self.assertGreaterEqual(svg.count("<tspan "), 2)
            self.assertIn(
                'style="font-size:1.6px">Hlavní', svg
            )

    def test_timber_legend_keeps_all_hatches_when_diagram_styles_are_filtered(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text('''<svg width="120mm" height="120mm" viewBox="0 0 120 120"><defs>
<pattern id="brick" width="10" height="10"><rect fill="#fff"/><path d="M0,0 L10,10"/></pattern>
</defs><g class="section target-view-ELEVATIONVIEW"/></svg>''')
            table = {
                "kind": "timber_schedule", "title": "SPECIFIKACE PRVKŮ KROVU",
                "styled_member_guids": ["selected"],
                "items": [
                    {"mark": "A", "name": "Selected", "width": 80, "height": 200,
                     "length": 4000, "count": 2, "pattern": "brick", "color": "#ff8800",
                     "member_guids": ["selected"]},
                    {"mark": "B", "name": "Unselected", "width": 80, "height": 200,
                     "length": 4000, "count": 10, "pattern": "brick", "color": "#ff0000",
                     "member_guids": ["other"]},
                ],
            }
            props = {"RightPanelWidth": 65, "RightPanelTables": json.dumps([table])}
            styles = _timber_schedule_member_styles(props)
            self.assertEqual(set(styles), {"selected"})
            _postprocess_projected_wood_surface_styles(
                path, color="#ffffff", styles=styles, view="elevation", include_cuts=True)
            _postprocess_right_panel(path, props)
            svg = path.read_text()
            self.assertIn('fill="#ff8800"', svg)
            self.assertIn('fill="#ff0000"', svg)
            self.assertNotIn(".GlobalId-other {", svg)
            tree = ET.fromstring(svg)
            ids = {e.attrib.get("id") for e in tree.iter()}
            for element in tree.iter():
                style = element.attrib.get("style", "")
                if "fill:url(#" in style:
                    pattern = style.split("fill:url(#", 1)[1].split(")", 1)[0]
                    self.assertIn(pattern, ids)
            _postprocess_right_panel(path, props)
            self.assertEqual(path.read_text(), svg)

    def test_appends_timber_schedule_to_right_panel(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 110,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "timber_schedule",
                            "title": "SPECIFIKACE PRVKŮ KROVU",
                            "layout_scale": 0.5,
                            "items": [
                                {
                                    "mark": "A",
                                    "name": "Hlavní krokve",
                                    "material": "c22",
                                    "width": 100,
                                    "height": 180,
                                    "length": 5989,
                                    "count": 27,
                                    "pattern": "brick",
                                    "color": "#f4d35e",
                                    "member_guids": ["rafter-guid"],
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertEqual(
                svg.count('class="right-panel-table timber-schedule"'),
                1,
            )
            self.assertIn("SPECIFIKACE PRVKŮ KROVU", svg)
            for heading in (
                "OZNAČENÍ",
                "NÁZEV",
                "Material",
                "ŠÍŘKA",
                "VÝŠKA",
                "DÉLKA",
                "POČET",
                "m³/kus",
                "m³",
            ):
                self.assertIn(f">{heading}</text>", svg)
            self.assertIn(">Hlavní krokve</text>", svg)
            self.assertIn(">c22</text>", svg)
            self.assertIn(">5989</text>", svg)
            self.assertIn(">27</text>", svg)
            self.assertIn(">0,108</text>", svg)
            self.assertEqual(svg.count(">2,911</text>"), 2)
            self.assertIn(">CELKEM</text>", svg)
            self.assertIn("font-size:1.45px", svg)
            self.assertIn(
                'class="timber-schedule-swatch"',
                svg,
            )
            self.assertIn('fill="url(#brick-tint-f4d35e)"', svg)
            self.assertNotIn(">A</text>", svg)

    def test_appends_miako_beam_schedule_to_right_panel(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 50,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "miako_beam_schedule",
                            "title": "SPECIFIKACE MIAKO NOSNÍKŮ",
                            "items": [
                                {
                                    "location": "Levá část",
                                    "length": 3750,
                                    "count": 9,
                                    "slab_guid": "left-guid",
                                },
                                {
                                    "location": "Střed",
                                    "length": 4750,
                                    "count": 10,
                                    "slab_guid": "middle-guid",
                                },
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
            }

            _postprocess_right_panel(svg_path, properties)
            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="right-side-panel"'), 1)
            self.assertEqual(
                svg.count('class="right-panel-table miako-beam-schedule"'),
                1,
            )
            self.assertIn("SPECIFIKACE MIAKO NOSNÍKŮ", svg)
            for heading in ("UMÍSTĚNÍ", "DÉLKA", "POČET"):
                self.assertIn(f">{heading}</text>", svg)
            self.assertIn(">Levá část</text>", svg)
            self.assertIn(">Střed</text>", svg)
            self.assertIn(">3750</text>", svg)
            self.assertIn(">4750</text>", svg)
            self.assertIn(">9</text>", svg)
            self.assertIn(">10</text>", svg)

    def test_appends_window_area_and_floor_area_percentage_to_room_legend(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg width="160mm" height="160mm" '
                'viewBox="0 0 160 160">\n'
                '  <g id="model-view"/>\n'
                "</svg>\n",
                encoding="utf-8",
            )
            properties = {
                "RightPanelWidth": 40,
                "RightPanelTables": json.dumps(
                    [
                        {
                            "kind": "room_legend",
                            "title": "LEGENDA MÍSTNOSTÍ",
                            "items": [
                                {
                                    "identifier": "P.01",
                                    "description": "Pokoj",
                                    "area": 12.5,
                                    "window_area": 2.25,
                                },
                                {
                                    "identifier": "P.02",
                                    "description": "Galerie",
                                    "area": 8,
                                },
                            ],
                        }
                    ]
                ),
            }

            _postprocess_right_panel(svg_path, properties)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn(">PLOCHA OKEN</text>", svg)
            self.assertIn("2,25 m² (18,0 %)", svg)
            self.assertIn("0,00 m² (0,0 %)", svg)

    def test_stores_elevation_camera_with_camera_facing_furniture_label(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        wall = ground.wall((0, 0), (5, 0), thickness=0.2, height=2.8)
        wall.add_door(at=0.5, width=0.9, height=2.1)
        table = ground.furniture(
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
        self.assertFalse(
            any(
                "furniture-elevation-label"
                in (
                    ifcopenshell.util.element.get_pset(
                        annotation, "EPset_Annotation", "Classes"
                    )
                    or ""
                ).split()
                for annotation in house.model.by_type("IfcAnnotation")
            )
        )
        drawing.add_furniture_label(table)

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
        self.assertEqual(drawing_pset["HasAnnotation"], True)
        self.assertEqual(drawing_pset["DoorsClosed"], True)
        plan_label = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if ifcopenshell.util.element.get_pset(
                annotation, "EPset_Annotation", "Classes"
            )
            == "furniture-label small"
        )
        elevation_label = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if "furniture-elevation-label"
            in (
                ifcopenshell.util.element.get_pset(
                    annotation, "EPset_Annotation", "Classes"
                )
                or ""
            ).split()
        )
        self.assertEqual(
            set(drawing.group.IsGroupedBy[0].RelatedObjects),
            {drawing.element, elevation_label},
        )
        self.assertNotIn(plan_label, drawing.group.IsGroupedBy[0].RelatedObjects)
        label_placement = ifcopenshell.util.placement.get_local_placement(
            elevation_label.ObjectPlacement
        )
        np.testing.assert_allclose(
            label_placement,
            np.array(
                (
                    (1, 0, 0, 2),
                    (0, 0, -1, 2),
                    (0, 1, 0, 0.375),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-12,
        )
        label_literal = (
            elevation_label.Representation.Representations[0].Items[0]
        )
        self.assertEqual(label_literal.Literal, "Table")
        self.assertAlmostEqual(label_literal.Extent.SizeInX, 1)
        self.assertAlmostEqual(label_literal.Extent.SizeInY, 0.75)
        self.assertIn(
            f"furniture-owner-{table.GlobalId}",
            ifcopenshell.util.element.get_pset(
                elevation_label, "EPset_Annotation", "Classes"
            ).split(),
        )
        self.assertFalse(drawing._automatic_door_annotations)
        elevation_dimension = drawing.add_dimension(
            (0, 0),
            (1, 0),
            offset=0.5,
            name="Elevation width",
        )
        elevation_dimension_placement = (
            ifcopenshell.util.placement.get_local_placement(
                elevation_dimension.ObjectPlacement
            )
        )
        np.testing.assert_allclose(
            elevation_dimension_placement,
            np.array(
                (
                    (1, 0, 0, 0),
                    (0, 0, -1, -1),
                    (0, 1, 0, 0.5),
                    (0, 0, 0, 1),
                )
            ),
            atol=1e-12,
        )
        elevation_dimension_representation = (
            ifcopenshell.util.representation.get_representation(
                elevation_dimension, "Plan", "Annotation", "PLAN_VIEW"
            )
        )
        np.testing.assert_allclose(
            elevation_dimension_representation.Items[0].Points.CoordList,
            ((0, 0), (1, 0)),
            atol=1e-12,
        )
        elevation_extension = next(
            annotation
            for annotation in house.model.by_type("IfcAnnotation")
            if annotation.Name == "Elevation width Extension Lines"
        )
        elevation_extension_representation = (
            ifcopenshell.util.representation.get_representation(
                elevation_extension, "Plan", "Annotation", "PLAN_VIEW"
            )
        )
        elevation_extension_curves = (
            elevation_extension_representation.Items[0].Elements
        )
        np.testing.assert_allclose(
            elevation_extension_curves[0].Points.CoordList,
            ((0, -0.5), (0, 0.1)),
            atol=1e-12,
        )
        np.testing.assert_allclose(
            elevation_extension_curves[1].Points.CoordList,
            ((1, -0.5), (1, 0.1)),
            atol=1e-12,
        )

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
        two_storeys_drawing = house.add_drawing(
            "Two storeys",
            2.5,
            2,
            1.6,
            4,
            storeys=[ground, upper],
            door_annotations=False,
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
        suppressed_future_annotations = house.add_drawing(
            "No automatic annotations created later",
            2.5,
            2,
            1.6,
            4,
            storeys=[upper],
            door_annotations=False,
            automatic_plan_annotations=False,
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
        suppressed_existing_annotations = house.add_drawing(
            "No existing automatic annotations",
            2.5,
            2,
            4.6,
            4,
            storeys=[upper],
            door_annotations=False,
            automatic_plan_annotations=False,
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
        self.assertEqual(
            automatic_members(two_storeys_drawing), automatic_annotations
        )
        self.assertEqual(automatic_members(empty_drawing), set())
        self.assertEqual(
            automatic_members(suppressed_future_annotations), set()
        )
        self.assertEqual(
            automatic_members(suppressed_existing_annotations), set()
        )
        self.assertEqual(ground_drawing.storeys, (ground,))
        self.assertEqual(all_storeys_drawing.storeys, (ground, upper))
        self.assertFalse(ground_drawing.includes_all_storeys)
        self.assertTrue(all_storeys_drawing.includes_all_storeys)

        ground_include = ifcopenshell.util.element.get_pset(
            ground_drawing.element, "EPset_Drawing", "Include"
        )
        self.assertEqual(ground_include, f'location="{ground.element.GlobalId}"')
        two_storeys_include = ifcopenshell.util.element.get_pset(
            two_storeys_drawing.element,
            "EPset_Drawing",
            "Include",
        )
        self.assertEqual(
            two_storeys_include,
            (
                f'location="{ground.element.GlobalId}" + '
                f'location="{upper.element.GlobalId}"'
            ),
        )
        selected_storey_elements = ifcopenshell.util.selector.filter_elements(
            house.model,
            two_storeys_include,
        )
        self.assertIn(ground_wall, selected_storey_elements)
        self.assertIn(upper_wall, selected_storey_elements)
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

    def test_includes_an_element_and_its_plan_label_outside_storey_scope(
        self,
    ) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        upper = house.storey("Upper floor", elevation=3)
        ground_wall = ground.wall((0, 0), (4, 0), thickness=0.2, height=2.8)
        upper_wall = upper.wall((0, 0), (4, 0), thickness=0.2, height=2.8)
        furniture = ground.furniture(
            "Heat pump",
            kind="USERDEFINED",
            size=(1.2, 0.5, 1.5),
            center=(4.5, 1),
        )
        drawing = house.add_drawing(
            "Upper plan",
            2,
            2,
            4.5,
            5,
            storeys=[upper],
        )

        self.assertIs(drawing.include_element(furniture), drawing)
        include = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
            "Include",
        )
        self.assertEqual(
            include,
            f'location="{upper.element.GlobalId}" + {furniture.GlobalId}',
        )
        selected_elements = ifcopenshell.util.selector.filter_elements(
            house.model,
            include,
        )
        self.assertIn(upper_wall, selected_elements)
        self.assertIn(furniture, selected_elements)
        self.assertNotIn(ground_wall, selected_elements)

        linked_label = next(
            related_object
            for relation in furniture.ReferencedBy
            if relation.is_a("IfcRelAssignsToProduct")
            for related_object in relation.RelatedObjects
            if related_object.is_a("IfcAnnotation")
        )
        self.assertIn(
            linked_label,
            drawing.group.IsGroupedBy[0].RelatedObjects,
        )
        self.assertEqual(len(house.model.by_type("IfcFurniture")), 1)

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
        drawing.add_angle((0, 0), (1, 0), (1, 1))

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
                    Path(command[output_index]).write_text(
                        '<svg width="100mm" height="100mm" viewBox="0 0 100 100">'
                        '<text class="ANGLE">45.0°</text></svg>', encoding="utf-8"
                    )
                else:
                    self.assertIn('>45°</text>', output.read_text(encoding="utf-8"))
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
            self.assertIn('>45°</text>', output.read_text(encoding="utf-8"))
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

    def test_suppresses_only_miako_shell_edges_shared_with_core(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg xmlns:ifc="http://www.ifcopenshell.org/ns">
  <g class="IfcBeam material-MIAKOconcrete projection" ifc:name="Ceiling A Beam 1">
    <path d="M0,1 L10,1"/>
    <path d="M0,2 L10,2"/>
    <path d="M0,1 L0,2"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKObeamceramic projection" ifc:name="Ceiling A Beam 1 Ceramic U-shell">
    <path d="M0,0.8 L10,0.8"/>
    <path d="M10,1 L0,1"/>
    <path d="M0,2 L10,2"/>
    <path d="M0,2.2 L10,2.2"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKObeamceramic projection" ifc:name="Ceiling B Beam 1 Ceramic U-shell">
    <path d="M0,1 L10,1"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKObeamceramic cut" ifc:name="Ceiling A Beam 1 Ceramic U-shell">
    <path d="M0,1 L10,1"/>
  </g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_miako_beam_shell_shared_edges(svg_path)
            _postprocess_miako_beam_shell_shared_edges(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(
                svg.count("miako-beam-shell-shared-edges-postprocess"),
                1,
            )
            self.assertNotIn('d="M10,1 L0,1"', svg)
            self.assertEqual(svg.count('d="M0,2 L10,2"'), 1)
            self.assertIn('d="M0,0.8 L10,0.8"', svg)
            self.assertIn('d="M0,2.2 L10,2.2"', svg)
            self.assertEqual(svg.count('d="M0,1 L10,1"'), 3)
            self.assertEqual(svg.count('class="miako-shell-plan-fill"'), 2)
            self.assertIn('d="M0,0.9 L10,0.9"', svg)
            self.assertIn('d="M0,2.1 L10,2.1"', svg)
            self.assertIn("stroke:#d98245;stroke-width:0.16", svg)
            self.assertIn(
                ".section.target-view-PLANVIEW "
                "g.material-MIAKOconcrete.projection",
                svg,
            )
            self.assertIn(
                ".section.target-view-PLANVIEW "
                "g.material-MIAKObeamceramic.cut",
                svg,
            )
            self.assertEqual(svg.count("stroke-width: 0.04 !important"), 1)

    def test_removes_only_projected_miako_slab_end_faces(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg xmlns:ifc="http://www.ifcopenshell.org/ns">
  <g class="IfcSlab material-null projection" ifc:name="Ceiling A">
    <path d="M0,0 L0,4"/>
    <path d="M5,0 L5,4"/>
    <path d="M10,0 L10,4"/>
  </g>
  <g class="IfcBeam material-MIAKOconcrete projection" ifc:name="Ceiling A Beam 1">
    <path d="M0,1 L0,2"/>
    <path d="M0,1 L10,1"/>
    <path d="M10,1 L10,2"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOblockceramic projection" ifc:name="Ceiling A Wide Block 1.1">
    <path d="M1,2 L1,3"/>
    <path d="M2.5,2 L2.5,3"/>
    <path d="M1,2 L2.5,2"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOblockceramic projection" ifc:name="Ceiling A Wide Block 1.2">
    <path d="M7.5,2 L7.5,3"/>
    <path d="M9,2 L9,3"/>
    <path d="M7.5,2 L9,2"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOblockceramic cut" ifc:name="Ceiling A Wide Block 1.1">
    <path d="M1,2 L2.5,2 L2.5,3 L1,3 Z"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOblockceramic cut" ifc:name="Other slab block">
    <path d="M20,2 L21,2 L21,3 L20,3 Z"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOreinforcement projection" ifc:name="Ceiling A Beam 1 Reinforcement">
    <path d="M0,1.4 L10,1.4"/>
    <path d="M10,1.4 L10,1.5"/>
    <path d="M10,1.5 L0,1.5"/>
    <path d="M0,1.5 L0,1.4"/>
  </g>
  <g class="IfcWall material-null projection" ifc:name="Unrelated">
    <path d="M0,0 L0,4"/>
  </g>
  <g class="IfcBuildingElementPart material-MIAKOreinforcement projection" ifc:name="Angled Beam 1 Reinforcement">
    <path d="M0,0 L10,10"/>
    <path d="M9,11 L11,9"/>
  </g>
  <g class="IfcBeam material-MIAKOconcrete projection" ifc:name="Angled Beam 1">
    <path d="M-1,1 L1,-1"/>
    <path d="M4,6 L6,4"/>
    <path d="M9,11 L11,9"/>
    <path d="M0,0 L10,10"/>
  </g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_miako_slab_end_faces(svg_path)
            _postprocess_miako_slab_end_faces(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count("miako-open-ends-postprocess"), 1)
            self.assertNotIn('d="M0,1 L0,2"', svg)
            self.assertNotIn('d="M10,1 L10,2"', svg)
            self.assertIn('d="M1,2 L1,3"', svg)
            self.assertIn('d="M9,2 L9,3"', svg)
            self.assertIn('d="M2.5,2 L2.5,3"', svg)
            self.assertIn('d="M7.5,2 L7.5,3"', svg)
            self.assertIn('d="M0,1 L10,1"', svg)
            self.assertEqual(svg.count('d="M0,0 L0,4"'), 1)
            self.assertNotIn('d="M-1,1 L1,-1"', svg)
            self.assertNotIn('d="M9,11 L11,9"', svg)
            self.assertIn('d="M4,6 L6,4"', svg)
            self.assertIn('d="M0,0 L10,10"', svg)
            self.assertNotIn("stroke: none !important", svg)
            self.assertIn(
                'class="IfcBuildingElementPart material-MIAKOblockceramic cut" '
                'ifc:name="Other slab block">',
                svg,
            )

    def test_furniture_label_overlays_skip_self_closing_text_templates(self):
        source = ('<svg xmlns="http://www.w3.org/2000/svg">'
                  '<defs><g id="template"><text class="regular" /></g></defs>'
                  '<g id="model"><path d="M0 0L1 1"/></g>'
                  '<text><tspan class="furniture-label">Kamna</tspan></text></svg>')
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.svg"
            path.write_text(source, encoding="utf-8")
            _postprocess_door_overheads(path)
            result = path.read_text(encoding="utf-8")
            root = ET.fromstring(result)
            ns = {"s": "http://www.w3.org/2000/svg"}
            overlay = root.find("s:g[@class='furniture-label-overlays']", ns)
            self.assertIsNotNone(overlay)
            self.assertEqual(len(overlay), 1)
            self.assertEqual("".join(overlay.itertext()).strip(), "Kamna")
            self.assertEqual(result.count('id="template"'), 1)
            self.assertEqual(result.count('id="model"'), 1)
            _postprocess_door_overheads(path)
            self.assertEqual(path.read_text(encoding="utf-8"), result)

    def test_keeps_only_visible_furniture_labels_above_elevation_linework(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "elevation.svg"
            svg_path.write_text(
                """<svg xmlns:ifc="http://www.ifcopenshell.org/namespaces/ifc">
  <g class="symbol"><text class="template"/></g>
  <g ifc:guid="VISIBLE" class="IfcFurniture projection"><path d="M0 0L1 1"/></g>
  <g ifc:guid="HIDDEN" class="IfcFurniture projection"><path/></g>
  <text style="font-size:0"><tspan class="IfcAnnotation furniture-label furniture-elevation-label furniture-owner-VISIBLE">Kamna</tspan></text>
  <text style="font-size:0"><tspan class="IfcAnnotation furniture-label furniture-elevation-label furniture-owner-HIDDEN">Skříň</tspan></text>
  <text class="unrelated"><tspan>Note</tspan></text>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_elevation_furniture_labels(svg_path)
            _postprocess_elevation_furniture_labels(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            overlay = '<g class="furniture-elevation-label-overlays">'
            self.assertEqual(svg.count(overlay), 1)
            self.assertEqual(svg.count("Kamna"), 1)
            self.assertNotIn("Skříň", svg)
            self.assertEqual(svg.count("Note"), 1)
            self.assertIn('<g class="symbol"><text class="template"/></g>', svg)
            self.assertGreater(svg.index(overlay), svg.index("VISIBLE"))

    def test_moves_complete_hexagon_markers_above_elevation_geometry(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "elevation.svg"
            svg_path.write_text(
                """<svg>
  <defs>
    <g id="hexagon-marker"><path/><text class="small"/></g>
  </defs>
  <line class="IfcAnnotation PredefinedType-LINEWORK hexagon-marker-leader" x1="1" y1="2" x2="3" y2="4"/>
  <g id="floor-layer"><path d="M0 0L5 0"/></g>
  <g transform="translate(2,3)">
    <path d="hexagon"/>
    <text class="IfcAnnotation PredefinedType-TEXT hexagon-marker">SK1</text>
  </g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_hexagon_marker_overlays(svg_path)
            _postprocess_hexagon_marker_overlays(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            overlay = (
                '<g class="hexagon-marker-overlays '
                'target-view-ELEVATIONVIEW">'
            )
            self.assertEqual(svg.count(overlay), 1)
            self.assertEqual(svg.count("hexagon-marker-leader"), 1)
            self.assertEqual(svg.count(">SK1</text>"), 1)
            self.assertEqual(svg.count('id="hexagon-marker"'), 1)
            self.assertGreater(svg.index(overlay), svg.index('id="floor-layer"'))
            overlay_svg = svg[svg.index(overlay) :]
            self.assertLess(
                overlay_svg.index("hexagon-marker-leader"),
                overlay_svg.index(">SK1</text>"),
            )

    def test_moves_complete_notes_above_drawing_geometry(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                """<svg>
  <defs><g id="symbol"><text data-type="text-template"/></g></defs>
  <line class="IfcAnnotation PredefinedType-LINEWORK note-leader" x1="1" y1="2" x2="3" y2="4"/>
  <g id="wall"><path d="M0 0L5 0"/></g>
  <text style="font-size:0"><tspan class="IfcAnnotation PredefinedType-TEXT note-text">Poznámka</tspan></text>
  <text class="unrelated">Keep me</text>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_note_overlays(svg_path)
            _postprocess_note_overlays(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            overlay = '<g class="note-overlays">'
            self.assertEqual(svg.count(overlay), 1)
            self.assertEqual(svg.count("note-leader"), 1)
            self.assertEqual(svg.count("Poznámka"), 1)
            self.assertEqual(svg.count("Keep me"), 1)
            self.assertEqual(svg.count('data-type="text-template"'), 1)
            self.assertGreater(svg.index(overlay), svg.index('id="wall"'))
            overlay_svg = svg[svg.index(overlay) :]
            self.assertLess(
                overlay_svg.index("note-leader"),
                overlay_svg.index("Poznámka"),
            )

    def test_masks_unfilled_openings_without_visible_continuation_lines(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.svg"
            path.write_text(
                '<svg>\n'
                '  <path id="projected-wall-edge" d="M0 10H10 M0 12H10"/>\n'
                '  <line class="GlobalId-opening IfcAnnotation PredefinedType-LINEWORK '
                'opening-mask-source" x1="0" y1="10" x2="10" y2="10"/>\n'
                '  <line class="GlobalId-opening IfcAnnotation PredefinedType-LINEWORK '
                'opening-mask-source" x1="0" y1="12" x2="10" y2="12"/>\n'
                '</svg>\n', encoding="utf-8")
            original = path.read_text()
            # A cut above/below the opening must not cover the projected wall.
            _postprocess_door_overheads(path, mask_global_ids=set())
            self.assertEqual(path.read_text(), original)
            _postprocess_door_overheads(path, mask_global_ids={"opening"})
            result = path.read_text()
            self.assertEqual(result.count('<polygon class="door-overhead-mask"'), 1)
            self.assertIn('points="0,10 10,10 10,12 0,12"', result)
            self.assertLess(result.index('id="projected-wall-edge"'),
                            result.index('<polygon class="door-overhead-mask"'))
            self.assertNotIn("door-overhead dashed", result)
            self.assertNotIn("door-overhead solid", result)
            _postprocess_door_overheads(path, mask_global_ids={"opening"})
            self.assertEqual(path.read_text(), result)
        stylesheet = (Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css").read_text()
        rule = stylesheet.split(".PredefinedType-LINEWORK.opening-mask-source {", 1)[1].split("}", 1)[0]
        self.assertIn("stroke: none !important", rule)
        self.assertIn("fill: none !important", rule)

    def test_insulation_continuations_never_create_door_overhead_masks(self) -> None:
        # Legacy IFCs give two dormer-window spans the same overhead class/ID.
        # Exclude them even when their linework would form a nondegenerate mask.
        for y2 in (10, 12):
            with self.subTest(y2=y2), TemporaryDirectory() as directory:
                path = Path(directory) / "plan.svg"
                path.write_text(
                    '<svg>\n'
                    '  <line class="GlobalId-insulation IfcAnnotation PredefinedType-LINEWORK '
                    'wall-insulation wall-insulation-opening door-overhead dashed" '
                    'x1="0" y1="10" x2="10" y2="10"/>\n'
                    '  <line class="GlobalId-insulation IfcAnnotation PredefinedType-LINEWORK '
                    'wall-insulation wall-insulation-opening door-overhead dashed" '
                    f'x1="20" y1="{y2}" x2="30" y2="{y2}"/>\n'
                    '  <line class="GlobalId-door IfcAnnotation PredefinedType-LINEWORK '
                    'door-overhead dashed" x1="0" y1="20" x2="10" y2="20"/>\n'
                    '  <line class="GlobalId-door IfcAnnotation PredefinedType-LINEWORK '
                    'door-overhead dashed" x1="0" y1="22" x2="10" y2="22"/>\n'
                    '</svg>\n', encoding="utf-8")
                _postprocess_door_overheads(path)
                _postprocess_wall_insulation_backdrop(path)
                result = path.read_text()
                self.assertEqual(result.count('<polygon class="door-overhead-mask"'), 1)
                self.assertIn('points="0,20 10,20 10,22 0,22"', result)
                self.assertEqual(result.count('GlobalId-insulation'), 2)
                _postprocess_door_overheads(path)
                _postprocess_wall_insulation_backdrop(path)
                self.assertEqual(path.read_text(), result)

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
  <g id="product-reinforcement-projection-only" ifc:guid="reinforcement-projection-only" class="IfcBuildingElementPart material-MIAKOreinforcement projection"><path/></g>
  <g ifc:guid="reinforcement-second" class="IfcBuildingElementPart material-MIAKOreinforcement cut"><path/></g>
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
            second_reinforcement_source = (
                "miako-reinforcement-overlay-source-2"
            )
            reinforcement_use = (
                f'<use href="#{reinforcement_source}" '
                f'xlink:href="#{reinforcement_source}"/>'
            )
            second_reinforcement_use = (
                f'<use href="#{second_reinforcement_source}" '
                f'xlink:href="#{second_reinforcement_source}"/>'
            )
            self.assertEqual(svg.count(reinforcement_overlay), 1)
            self.assertEqual(svg.count(f'id="{reinforcement_source}"'), 1)
            self.assertEqual(
                svg.count(f'id="{second_reinforcement_source}"'),
                1,
            )
            self.assertEqual(svg.count(reinforcement_use), 1)
            self.assertEqual(svg.count(second_reinforcement_use), 1)
            self.assertIn(
                'ifc:guid="reinforcement" '
                'class="IfcBuildingElementPart material-MIAKOreinforcement cut" '
                f'id="{second_reinforcement_source}">',
                svg,
            )
            self.assertIn(
                'ifc:guid="reinforcement-second" '
                'class="IfcBuildingElementPart material-MIAKOreinforcement cut" '
                f'id="{reinforcement_source}">',
                svg,
            )
            self.assertNotIn(
                '<use href="#product-reinforcement-projection"',
                svg,
            )
            self.assertNotIn(
                '<use href="#product-reinforcement-projection-only"',
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

    def test_vapour_barrier_is_blue_only_in_cut_and_matches_legend(self) -> None:
        stylesheet = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text(encoding="utf-8")
        rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .material-Vapourbarrier {", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", rule)
        self.assertIn("stroke: black !important", rule)
        self.assertNotIn("#4a90e2", rule)
        self.assertIn("stroke-width: 0.08 !important", rule)
        cut_rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .material-Vapourbarrier.cut {", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: #4a90e2 !important", cut_rule)
        self.assertIn("stroke: #4a90e2 !important", cut_rule)
        self.assertLess(stylesheet.index(".target-view-ELEVATIONVIEW .material-Vapourbarrier {"),
                        stylesheet.index(".target-view-ELEVATIONVIEW .material-Vapourbarrier.cut {"))
        patterns = ET.parse(Path(__file__).parent / "drawings/assets/patterns.svg")
        pattern = next(p for p in patterns.getroot().iter() if p.get("id") == "vapour-barrier-solid")
        self.assertEqual(len(pattern), 1)
        self.assertTrue(pattern[0].tag.endswith("}rect"))
        self.assertEqual(pattern[0].get("fill"), "#4a90e2")

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

    def test_plan_surface_fills_are_opt_in_and_preserve_member_metadata(self) -> None:
        house = House("Surface fills")
        legacy = house.add_drawing("Legacy", x=0, y=0, z=10, radius=5)
        roof = house.add_drawing("Roof", x=0, y=0, z=10, radius=5,
                                 surface_fills=True, projected_wood_color="#f4d35e")
        legacy_pset = ifcopenshell.util.element.get_pset(legacy.element, "EPset_Drawing")
        pset = ifcopenshell.util.element.get_pset(roof.element, "EPset_Drawing")
        self.assertEqual(legacy_pset["FillMode"], "NONE")
        self.assertNotIn("Metadata", legacy_pset)
        self.assertEqual(pset["FillMode"], "SHAPELY")
        self.assertEqual(pset["Metadata"], "GlobalId")
        self.assertEqual(pset["ProjectedWoodColor"], "#f4d35e")
        with self.assertRaisesRegex(TypeError, "surface_fills must be a boolean"):
            house.add_drawing("Invalid", x=0, y=0, z=10, radius=5, surface_fills="yes")

    def test_styles_native_wood_surfaces_without_hulls_or_reordering(self) -> None:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg"><defs>
<pattern id="brick" width="10" height="10"><rect fill="#fff"/><path d="M0,0 L10,10"/></pattern>
</defs><g class="section target-view-PLANVIEW">
<path class="IfcBeam material-Wood GlobalId-0bguid surface" d="M0,0 L10,0 L10,10 L0,10 Z M2,2 L2,8 L8,8 L8,2 Z"/>
<path class="IfcBeam material-Wood GlobalId-other surface" d="M11,0 L20,0 L20,10 Z"/>
<g class="IfcBeam material-Wood projection"><path d="M0,0 L10,0"/></g>
</g></svg>'''
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roof.svg"
            path.write_text(svg)
            styles = {"0$b_guid": {"color": "#ff8800", "pattern": "brick", "drawing_order": 99},
                      "other": {"color": "#00ff00", "drawing_order": 0}}
            _postprocess_projected_wood_surface_styles(path, color="#f4d35e", styles=styles)
            output = path.read_text()
            self.assertIn(".surface.GlobalId-0bguid { fill: url(#", output)
            self.assertIn(".surface.GlobalId-other { fill: #00ff00 !important; }", output)
            self.assertIn(".surface { fill: #f4d35e !important; }", output)
            self.assertIn('fill="#ff8800"', output)
            self.assertIn('d="M0,0 L10,0 L10,10 L0,10 Z M2,2 L2,8 L8,8 L8,2 Z"', output)
            self.assertLess(output.index("GlobalId-0bguid surface"), output.index("GlobalId-other surface"))
            self.assertNotIn("<polygon", output)
            self.assertNotIn("projected-wood-fill", output)
            self.assertNotIn("projected-wood-order", output)
            _postprocess_projected_wood_surface_styles(path, color="#f4d35e", styles=styles)
            self.assertEqual(path.read_text(), output)

    def test_styles_selected_native_elevation_surfaces_and_cuts_without_new_geometry(self):
        svg = '''<svg xmlns="http://www.w3.org/2000/svg"><defs>
<pattern id="brick" width="10" height="10"><rect fill="#fff"/><path d="M0,0 L10,10"/></pattern>
</defs><g class="section target-view-ELEVATIONVIEW">
<path class="IfcBeam material-Wood GlobalId-selected surface" d="M0,0 L10,0 L10,10 L0,10 Z"/>
<g class="IfcBeam material-Wood GlobalId-cutguid cut"><path d="M0,12 L2,12 L2,14 L0,14 Z"/></g>
<path class="IfcBeam material-Wood GlobalId-other surface" d="M20,0 L25,0 L25,5 Z"/>
</g></svg>'''
        styles = {"selected": {"color": "#ffee00", "pattern": "brick"},
                  "cut_guid": {"color": "#ff8800", "pattern": "brick"}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "section.svg"
            path.write_text(svg)
            _postprocess_projected_wood_surface_styles(
                path, color="#ffffff", styles=styles, view="elevation", include_cuts=True)
            output = path.read_text()
            self.assertIn(".target-view-ELEVATIONVIEW .IfcBeam.material-Wood.surface { fill: #ffffff", output)
            self.assertIn(".target-view-ELEVATIONVIEW .IfcBeam.material-Wood.cut { fill: #ffffff", output)
            self.assertIn(".surface.GlobalId-selected { fill: url(#", output)
            self.assertIn(".cut.GlobalId-cutguid { fill: url(#", output)
            self.assertNotIn(".GlobalId-other {", output)
            self.assertNotIn("PLANVIEW", output)
            self.assertNotIn("<polygon", output)
            for data in ("M0,0 L10,0 L10,10 L0,10 Z", "M0,12 L2,12 L2,14 L0,14 Z", "M20,0 L25,0 L25,5 Z"):
                self.assertIn(f'd="{data}"', output)
            _postprocess_projected_wood_surface_styles(
                path, color="#ffffff", styles=styles, view="elevation", include_cuts=True)
            self.assertEqual(path.read_text(), output)

    def test_fills_open_projected_wood_edges_in_plan(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "plan.svg"
            svg_path.write_text(
                """<svg>
<g class="section target-view-PLANVIEW">
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
  <g class="IfcBeam material-Wood projection">
    <path d="M4,2 L5,2 L5,4 L4,4 L4,2"/>
  </g>
  <g class="IfcBeam material-Wood projection">
    <path d="M6,2 L7,2"/>
    <path d="M6,2 L6,5"/>
    <path d="M7,2 L7,4"/>
  </g>
  <g class="IfcBeam material-Wood projection">
    <path d="M8,0 L9,1 L8,2 L7,1 L8,0"/>
  </g>
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
            self.assertIn(
                '<polygon class="projected-wood-fill" '
                'points="4,2 5,2 5,4 4,4"/>',
                svg,
            )
            self.assertIn(
                '<polygon class="projected-wood-fill" '
                'points="6,2 7,2 7,5 6,5"/>',
                svg,
            )
            self.assertIn(
                '<polygon class="projected-wood-fill" '
                'points="7,1 8,0 9,1 8,2"/>',
                svg,
            )
            fill_layer = '<g class="projected-wood-fill-layer">'
            wood_group = '<g class="IfcBeam material-Wood projection">'
            self.assertEqual(svg.count(fill_layer), 1)
            self.assertLess(svg.index(fill_layer), svg.index(wood_group))
            self.assertLess(
                svg.rindex('<polygon class="projected-wood-fill"'),
                svg.index(wood_group),
            )
            self.assertNotIn('points="5,0 6,0 6,1 5,1"', svg)

        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")
        projected_rule = stylesheet.split(
            ".target-view-PLANVIEW .projected-wood-fill", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        cut_rule = stylesheet.split(
            ".material-Wood.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", projected_rule)
        self.assertIn("fill: #f4d35e !important", cut_rule)

    def test_overrides_projected_wood_fill_for_one_plan(self) -> None:
        house = House("My house")
        drawing = house.add_drawing(
            "Roof plan",
            2,
            3,
            8,
            5,
            projected_wood_color="#f4d35e",
        )
        other_drawing = house.add_drawing("Upper plan", 2, 3, 4, 5)

        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        other_properties = ifcopenshell.util.element.get_pset(
            other_drawing.element,
            "EPset_Drawing",
        )
        self.assertEqual(properties["ProjectedWoodColor"], "#f4d35e")
        self.assertNotIn("ProjectedWoodColor", other_properties)

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "roof.svg"
            svg_path.write_text(
                """<svg>
<g class="section target-view-PLANVIEW">
  <g class="IfcBeam material-Wood projection">
    <path d="M0,0 L2,0 L2,1 L0,1 L0,0"/>
  </g>
</g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_projected_wood_fills(
                svg_path,
                color=properties["ProjectedWoodColor"],
            )

            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn(
                '<polygon class="projected-wood-fill" '
                'style="fill: #f4d35e !important;" '
                'points="0,0 2,0 2,1 0,1"/>',
                svg,
            )
            self.assertLess(
                svg.index('<g class="projected-wood-fill-layer">'),
                svg.index('<g class="IfcBeam material-Wood projection">'),
            )

        with self.assertRaisesRegex(ValueError, "only supported for plan"):
            house.add_drawing(
                "Invalid elevation",
                2,
                0,
                2,
                5,
                view="elevation",
                direction=(0, 1, 0),
                projected_wood_color="yellow",
            )

    def test_patterns_selected_projected_wood_members(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "roof.svg"
            svg_path.write_text(
                """<svg>
<defs>
  <pattern id="brick" width="3" height="3">
    <rect width="3" height="3" fill="white"/>
    <line x1="1" y1="0" x2="1" y2="3"/>
  </pattern>
</defs>
<g class="section target-view-PLANVIEW">
  <g id="styled-product" class="IfcBeam material-Wood projection" ifc:guid="styled-member">
    <path d="M0,0 L2,0 L2,1 L0,1 L0,0"/>
  </g>
  <g id="ordinary-product" class="IfcBeam material-Wood projection" ifc:guid="ordinary-member">
    <path d="M3,0 L5,0 L5,1 L3,1 L3,0"/>
  </g>
  <g id="solid-product" class="IfcBeam material-Wood projection" ifc:guid="solid-member">
    <path d="M6,0 L8,0 L8,1 L6,1 L6,0"/>
  </g>
</g>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_projected_wood_fills(
                svg_path,
                color="#f4d35e",
                styles={
                    "styled-member": {
                        "pattern": "brick",
                        "color": "#f4a261",
                        "drawing_order": 1,
                    },
                    "solid-member": {
                        "color": "#e76f51",
                        "drawing_order": 0,
                    },
                    "ordinary-member": {"drawing_order": 2},
                },
            )
            _postprocess_projected_wood_fills(
                svg_path,
                color="#f4d35e",
                styles={
                    "styled-member": {
                        "pattern": "brick",
                        "color": "#f4a261",
                        "drawing_order": 1,
                    },
                    "solid-member": {
                        "color": "#e76f51",
                        "drawing_order": 0,
                    },
                    "ordinary-member": {"drawing_order": 2},
                },
            )

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('id="brick-tint-f4a261"'), 1)
            self.assertIn(
                '<rect width="3" height="3" fill="#f4a261"/>',
                svg,
            )
            self.assertIn(
                'style="fill: url(#brick-tint-f4a261) !important;" '
                'points="0,0 2,0 2,1 0,1"',
                svg,
            )
            self.assertIn(
                'style="fill: #f4d35e !important;" '
                'points="3,0 5,0 5,1 3,1"',
                svg,
            )
            self.assertIn(
                'style="fill: #e76f51 !important;" '
                'points="6,0 8,0 8,1 6,1"',
                svg,
            )
            self.assertEqual(
                svg.count('class="projected-wood-order-layer"'),
                3,
            )
            self.assertIn('<use href="#styled-product"/>', svg)
            self.assertIn('<use href="#solid-product"/>', svg)
            self.assertIn('<use href="#ordinary-product"/>', svg)
            self.assertEqual(
                svg.count('class="projected-wood-order-outline"'),
                3,
            )
            self.assertLess(
                svg.index(
                    'style="fill: #e76f51 !important;" '
                    'points="6,0 8,0 8,1 6,1"'
                ),
                svg.index(
                    'class="projected-wood-order-outline" '
                    'points="6,0 8,0 8,1 6,1"'
                ),
            )
            self.assertLess(
                svg.index('data-drawing-order="0"'),
                svg.index('data-drawing-order="1"'),
            )
            self.assertLess(
                svg.index('data-drawing-order="1"'),
                svg.index('data-drawing-order="2"'),
            )

    def test_masks_projected_members_behind_roof_opening_outline(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "roof.svg"
            svg_path.write_text(
                """<svg>
  <polygon id="projected-rafter-fill" points="4,0 6,0 6,10 4,10"/>
  <line class="GlobalId-MASK IfcAnnotation PredefinedType-LINEWORK roof-opening-mask-source" x1="3" y1="4" x2="7" y2="4"/>
  <line class="GlobalId-MASK IfcAnnotation PredefinedType-LINEWORK roof-opening-mask-source" x1="7" y1="4" x2="7" y2="8"/>
  <line class="GlobalId-MASK IfcAnnotation PredefinedType-LINEWORK roof-opening-mask-source" x1="7" y1="8" x2="3" y2="8"/>
  <line class="GlobalId-MASK IfcAnnotation PredefinedType-LINEWORK roof-opening-mask-source" x1="3" y1="8" x2="3" y2="4"/>
  <line class="GlobalId-OPENING IfcAnnotation PredefinedType-LINEWORK roof-opening dashed" x1="3.5" y1="4.5" x2="6.5" y2="4.5"/>
  <line class="GlobalId-OPENING IfcAnnotation PredefinedType-LINEWORK roof-opening dashed" x1="6.5" y1="4.5" x2="6.5" y2="7.5"/>
  <line class="GlobalId-OPENING IfcAnnotation PredefinedType-LINEWORK roof-opening dashed" x1="6.5" y1="7.5" x2="3.5" y2="7.5"/>
  <line class="GlobalId-OPENING IfcAnnotation PredefinedType-LINEWORK roof-opening dashed" x1="3.5" y1="7.5" x2="3.5" y2="4.5"/>
  <line class="GlobalId-UNMASKED IfcAnnotation PredefinedType-LINEWORK roof-opening roof-opening-unmasked dashed" x1="8" y1="4" x2="10" y2="4"/>
  <line class="GlobalId-UNMASKED IfcAnnotation PredefinedType-LINEWORK roof-opening roof-opening-unmasked dashed" x1="10" y1="4" x2="10" y2="8"/>
  <line class="GlobalId-UNMASKED IfcAnnotation PredefinedType-LINEWORK roof-opening roof-opening-unmasked dashed" x1="10" y1="8" x2="8" y2="8"/>
  <line class="GlobalId-UNMASKED IfcAnnotation PredefinedType-LINEWORK roof-opening roof-opening-unmasked dashed" x1="8" y1="8" x2="8" y2="4"/>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_roof_opening_masks(svg_path)
            _postprocess_roof_opening_masks(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            mask = (
                '<polygon class="roof-opening-mask" '
                'points="3,4 7,4 7,8 3,8"/>'
            )
            self.assertEqual(svg.count(mask), 1)
            self.assertNotIn("roof-opening-mask-source", svg)
            self.assertGreater(svg.index(mask), svg.index("projected-rafter-fill"))
            self.assertLess(svg.index(mask), svg.index("roof-opening dashed"))
            self.assertNotIn(
                'points="8,4 10,4 10,8 8,8"',
                svg,
            )
            self.assertEqual(svg.count("roof-opening-unmasked"), 4)

    def test_applies_drawing_specific_model_line_width(self) -> None:
        house = House("My house")
        drawing = house.add_drawing(
            "Roof plan",
            2,
            3,
            8,
            5,
            model_line_width=0.06,
        )
        other_drawing = house.add_drawing("Upper plan", 2, 3, 4, 5)
        properties = ifcopenshell.util.element.get_pset(
            drawing.element,
            "EPset_Drawing",
        )
        other_properties = ifcopenshell.util.element.get_pset(
            other_drawing.element,
            "EPset_Drawing",
        )
        self.assertAlmostEqual(properties["ModelLineWidth"], 0.06)
        self.assertNotIn("ModelLineWidth", other_properties)

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "roof.svg"
            svg_path.write_text(
                """<svg>
  <g class="section target-view-PLANVIEW">
    <g class="IfcBeam projection"><path d="M0,0 L1,1"/></g>
  </g>
  <line class="IfcAnnotation roof-opening dashed"/>
</svg>
""",
                encoding="utf-8",
            )

            _postprocess_model_line_width(svg_path, width=0.06)
            _postprocess_model_line_width(svg_path, width=0.06)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count('class="model-line-width-override"'), 1)
            self.assertIn(
                ".section g.cut, .section g.projection "
                "{ stroke-width: 0.06 !important; }",
                svg,
            )
            self.assertIn("IfcAnnotation roof-opening dashed", svg)

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            house.add_drawing(
                "Invalid line width",
                2,
                3,
                8,
                5,
                model_line_width=0,
            )

    def test_styles_facade_laths_with_fine_plan_lines(self) -> None:
        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".target-view-PLANVIEW .IfcMember.cut", stylesheet)
        self.assertIn(".target-view-PLANVIEW .IfcMember.projection", stylesheet)
        lath_rule = stylesheet.split(
            ".target-view-PLANVIEW .IfcMember.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke-width: 0.06 !important", lath_rule)

        self.assertIn(
            ".target-view-PLANVIEW "
            ".IfcBuildingElementPart.material-Rockwool.cut",
            stylesheet,
        )
        insulation_rule = stylesheet.split(
            ".IfcBuildingElementPart.material-Rockwool.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", insulation_rule)
        self.assertIn("stroke-width: 0.06 !important", insulation_rule)

    def test_styles_lost_formwork_foundation_walls(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn('<pattern id="ztracene-bedneni"', patterns)
        lost_formwork_pattern = patterns.split(
            '<pattern id="ztracene-bedneni"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        self.assertIn('fill="white"', lost_formwork_pattern)
        self.assertNotIn('#fff2cc', lost_formwork_pattern)
        self.assertEqual(lost_formwork_pattern.count("<line "), 2)
        rule = stylesheet.split(
            ".cut.layer-material-ztracenebedneni", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: url(#ztracene-bedneni) !important", rule)
        self.assertIn("stroke-width: 0.05 !important", rule)

    def test_load_bearing_brick_is_white_but_partitions_keep_their_hatch(self) -> None:
        project_dir = Path(__file__).parent
        stylesheet = (project_dir / "bonsai_scripts/assets/plan.css").read_text()
        rule = stylesheet.split(".cut.layer-material-Brick", 1)[1].split("}", 1)[0]
        self.assertIn("fill: white !important", rule)
        self.assertNotIn("url(", rule)
        partition = stylesheet.split(".cut.material-PartitionwallVPC115mm", 1)[1].split("}", 1)[0]
        self.assertIn("fill: url(#diagonal1) !important", partition)
        patterns = ET.parse(project_dir / "drawings/assets/patterns.svg")
        pattern = next(p for p in patterns.getroot().iter() if p.get("id") == "solid-white")
        self.assertEqual(len(pattern), 1)
        self.assertTrue(pattern[0].tag.endswith("}rect"))
        self.assertEqual(pattern[0].get("fill"), "white")

    def test_styles_liapor_base_course_like_tinted_brick(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        brick_pattern = patterns.split(
            '<pattern id="brick"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        liapor_pattern = patterns.split(
            '<pattern id="liapor-brick"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        self.assertIn('fill="white"', brick_pattern)
        self.assertIn('fill="#fff2cc"', liapor_pattern)
        self.assertEqual(
            brick_pattern.count("<line "),
            liapor_pattern.count("<line "),
        )
        rule = stylesheet.split(
            ".cut.layer-material-Liaporbrick", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: url(#liapor-brick) !important", rule)
        self.assertIn("stroke-width: 0.05 !important", rule)

    def test_styles_drywall_with_tinted_partition_hatch(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        diagonal = patterns.split(
            '<pattern id="diagonal1"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        drywall_diagonal = patterns.split(
            '<pattern id="drywall-diagonal1"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        self.assertIn('fill="white"', diagonal)
        self.assertIn('fill="#dfefcf"', drywall_diagonal)
        self.assertIn(
            '<line x1="0" y1="0" x2="0" y2="1" '
            'style="stroke:black; stroke-width:0.25" />',
            diagonal,
        )
        self.assertIn(
            '<line x1="0" y1="0" x2="0" y2="1" '
            'style="stroke:black; stroke-width:0.25" />',
            drywall_diagonal,
        )
        rule = stylesheet.split(
            ".cut.layer-material-SDK", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: url(#drywall-diagonal1) !important", rule)
        self.assertNotIn("random-dots", rule)

    def test_preserves_random_dots_as_a_reusable_pattern(self) -> None:
        patterns = (
            Path(__file__).parent / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")

        random_dots = patterns.split(
            '<pattern id="random-dots"', maxsplit=1
        )[1].split("</pattern>", maxsplit=1)[0]
        self.assertEqual(random_dots.count("<circle "), 8)
        self.assertNotIn('<pattern id="sand-dense"', patterns)

    def test_styles_footing_cuts_with_cross_pattern(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn('<pattern id="footing-cross"', patterns)
        rule = stylesheet.split(
            ".IfcFooting.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: url(#footing-cross) !important", rule)
        self.assertIn("stroke-width: 0.05 !important", rule)

        plan_rule = stylesheet.split(
            ".target-view-PLANVIEW .IfcFooting.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", plan_rule)
        self.assertIn("stroke: white !important", plan_rule)

    def test_styles_base_plate_like_lost_formwork_with_opposite_diagonal(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn('<pattern id="base-plate"', patterns)
        root = ET.fromstring(patterns)
        base_plate = next(p for p in root if p.get("id") == "base-plate")
        formwork = next(p for p in root if p.get("id") == "ztracene-bedneni")
        self.assertEqual(base_plate.get("patternTransform"), "rotate(-45 0 0)")
        self.assertEqual(formwork.get("patternTransform"), "rotate(45 0 0)")
        for key in ("width", "height", "patternUnits"):
            self.assertEqual(base_plate.get(key), formwork.get(key))
        self.assertEqual([(child.tag, child.attrib) for child in base_plate],
                         [(child.tag, child.attrib) for child in formwork])
        self.assertFalse(any(child.tag.endswith("}circle") for child in base_plate))
        rule = stylesheet.split(
            ".IfcSlab.material-Baseplateconcrete.cut", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: url(#base-plate) !important", rule)
        self.assertIn("stroke-width: 0.05 !important", rule)

    def test_styles_floor_insulation_with_hexagon_pattern(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn('<pattern id="thermal-impact-insulation"', patterns)
        insulation_pattern = patterns.split('<pattern id="thermal-impact-insulation"', maxsplit=1)[1].split("</pattern>", maxsplit=1)[0]
        liapor_pattern = patterns.split('<pattern id="liapor-brick"', maxsplit=1)[1].split("</pattern>", maxsplit=1)[0]
        self.assertIn('fill="#fff2cc"', insulation_pattern)
        self.assertIn('fill="#fff2cc"', liapor_pattern)
        self.assertEqual(insulation_pattern.count("<path "), 3)
        rule = stylesheet.split(
            ".cut.layer-material-tepelnakrocejovaizolace", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(
            "fill: url(#thermal-impact-insulation) !important", rule
        )
        self.assertIn("stroke-width: 0.05 !important", rule)
        buildup_rule = stylesheet.split(
            ".IfcSlab.cut.layer-material-Floorbuildup,", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(".IfcSlab.material-Floorbuildup.cut", buildup_rule)
        self.assertIn("fill: #c5c7c8 !important", buildup_rule)
        self.assertNotIn("url(#", buildup_rule)
        concrete_rule = stylesheet.split("\n.material-Concretetopping.cut {", 1)[1].split("}", 1)[0]
        self.assertIn("fill: #c5c7c8 !important", concrete_rule)
        general_buildup_rule = stylesheet.split(".material-Floorbuildup {", 1)[1].split("}", 1)[0]
        self.assertIn("fill: white !important", general_buildup_rule)

    def test_styles_facade_insulation_patterns(self) -> None:
        project_dir = Path(__file__).parent
        patterns = (
            project_dir / "drawings" / "assets" / "patterns.svg"
        ).read_text(encoding="utf-8")
        stylesheet = (
            project_dir / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        self.assertIn('<pattern id="rockwool-wave"', patterns)
        polystyrene_rule = stylesheet.split(
            ".cut.layer-material-Polystyrene", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(".cut.material-Polystyrene", polystyrene_rule)
        self.assertIn(
            "fill: url(#polystyrene-transparent) !important",
            polystyrene_rule,
        )
        self.assertIn('<pattern id="perimeter-polystyrene"', patterns)
        perimeter_pattern = patterns.split('<pattern id="perimeter-polystyrene"', maxsplit=1)[1].split("</pattern>", maxsplit=1)[0]
        self.assertIn('fill="#f4dddd"', perimeter_pattern)
        perimeter_rule = stylesheet.split(
            ".cut.layer-material-XPS", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(".cut.material-XPS", perimeter_rule)
        self.assertIn(
            "fill: url(#perimeter-polystyrene) !important",
            perimeter_rule,
        )
        rockwool_rule = stylesheet.split(
            ".cut.layer-material-Rockwool", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", rockwool_rule)
        self.assertNotIn("yellow", rockwool_rule)
        drawing_rule = stylesheet.split(
            ".PredefinedType-FILLAREA.wall-insulation-polystyrene",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(
            "fill: url(#polystyrene-transparent) !important",
            drawing_rule,
        )
        xps_drawing_rule = stylesheet.split(
            ".PredefinedType-FILLAREA.wall-insulation-xps",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(
            "fill: url(#perimeter-polystyrene) !important",
            xps_drawing_rule,
        )
        batting_rule = stylesheet.split(
            'marker[id^="batting-"] path', maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke-width: 0.10 !important", batting_rule)
        boundary_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.wall-insulation-rockwool-boundary,",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: none !important", boundary_rule)
        self.assertIn("stroke-width: 0.05 !important", boundary_rule)
        opening_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.door-overhead", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke-dasharray: none !important", opening_rule)
        continuation_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.wall-insulation-opening {", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke-dasharray: none !important", continuation_rule)
        self.assertIn("stroke-width: 0.1 !important", continuation_rule)
        self.assertIn("fill: none !important", continuation_rule)
        self.assertGreater(stylesheet.index(".PredefinedType-LINEWORK.wall-insulation-opening {"),
                           stylesheet.index(".PredefinedType-LINEWORK.door-overhead"))
        self.assertNotIn("wall-insulation-interface", stylesheet)

    def test_roof_tiles_are_white_in_projection_and_red_in_cut(self) -> None:
        stylesheet = (Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css").read_text(encoding="utf-8")
        projection_selector = ".target-view-ELEVATIONVIEW .material-Rooftiles {"
        cut_selector = ".target-view-ELEVATIONVIEW .material-Rooftiles.cut {"
        projection_rule = stylesheet.split(projection_selector, maxsplit=1)[1].split("}", maxsplit=1)[0]
        cut_rule = stylesheet.split(cut_selector, maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", projection_rule)
        self.assertNotIn("#a64b35", projection_rule)
        self.assertIn("fill: #a64b35 !important", cut_rule)
        self.assertLess(stylesheet.index(projection_selector), stylesheet.index(cut_selector))
        outline_rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .material-Rooftiles.projection {", maxsplit=1
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke: black !important", outline_rule)
        self.assertIn("stroke-width: 0.06 !important", outline_rule)
        # Outline native projected linework, not every polygonized surface.
        self.assertIn("stroke: none", projection_rule)
        self.assertNotIn("stroke:", cut_rule)
        ridge_tile_rule = stylesheet.split(".PredefinedType-FILLAREA.ridge-tile {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: #a64b35 !important", ridge_tile_rule)

    def test_wood_fiberboard_is_white_in_projection_and_tinted_in_cut(self) -> None:
        stylesheet = (Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css").read_text(encoding="utf-8")
        projection_rule = stylesheet.split(".material-Woodfiberboard {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        cut_rule = stylesheet.split(".material-Woodfiberboard.cut {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", projection_rule)
        self.assertNotIn("#c9b56d", projection_rule)
        self.assertIn("fill: #c9b56d !important", cut_rule)
        # Equal importance and greater specificity keep the cut tint.
        self.assertLess(stylesheet.index(".material-Woodfiberboard {"),
                        stylesheet.index(".material-Woodfiberboard.cut {"))

    def test_facade_eps_pattern_is_transparent_without_changing_floor_or_xps(self) -> None:
        patterns_path = Path(__file__).parent / "drawings" / "assets" / "patterns.svg"
        root = ET.parse(patterns_path).getroot()
        patterns = {element.get("id"): element for element in root.iter()
                    if element.tag.endswith("}pattern")}
        eps = patterns["polystyrene-transparent"]
        self.assertEqual(len(eps), 3)
        for element in eps:
            self.assertTrue(element.tag.endswith("}path"))
            self.assertIn("fill:none", element.get("style", ""))
            self.assertIn("stroke:black", element.get("style", ""))
        for pattern_id, background in (("thermal-impact-insulation", "#fff2cc"),
                                       ("perimeter-polystyrene", "#f4dddd")):
            rect = next(element for element in patterns[pattern_id] if element.tag.endswith("}rect"))
            self.assertEqual(rect.get("fill"), background)

    def test_thins_only_wall_insulation_batting_markers(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<marker id="batting-rock"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<marker id="batting-end-rock"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<marker id="batting-other"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<polyline class="IfcAnnotation '
                'wall-insulation-rockwool" '
                'style="marker-start:url(#batting-rock);'
                'marker-end:url(#batting-end-rock)"/>'
                '<polyline class="IfcAnnotation" '
                'style="marker-start:url(#batting-other)"/>'
                "</svg>",
                encoding="utf-8",
            )

            _postprocess_wall_insulation_batting(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count("stroke-width:0.06!important"), 2)
            self.assertEqual(svg.count('stroke-width:0.18"'), 1)

    def test_uses_a_lighter_stroke_only_for_roof_batting_markers(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<marker id="batting-roof"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<marker id="batting-wall"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<g ifc:guid="roof-guid" class="IfcAnnotation cut">'
                '<path d="M 0 0 L 10 0"/></g>'
                '<g ifc:guid="other-guid" class="IfcAnnotation cut">'
                '<path d="M 0 1 L 10 1"/></g>'
                '<polyline id="ordinary-roof-batting" '
                'class="IfcAnnotation roof-batting" '
                'style="marker-start:url(#batting-roof)"/>'
                '<polyline class="GlobalId-roof-guid IfcAnnotation roof-batting" '
                'style="marker-start:url(#batting-roof)"/>'
                '<polyline id="under-rafter-batting" '
                'class="IfcAnnotation roof-batting under-rafter-batting" '
                'style="marker-start:url(#batting-roof)"/>'
                '<polyline class="IfcAnnotation wall-insulation-rockwool" '
                'style="marker-start:url(#batting-wall)"/>'
                '<path id="foreground-geometry"/>'
                '</svg>',
                encoding="utf-8",
            )

            _postprocess_wall_insulation_batting(svg_path)
            _postprocess_roof_batting(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertEqual(svg.count("stroke-width:0.06!important"), 2)
            self.assertIn(
                '<g ifc:guid="roof-guid" class="IfcAnnotation cut" '
                'style="display:none!important">',
                svg,
            )
            self.assertIn(
                '<g ifc:guid="other-guid" class="IfcAnnotation cut">',
                svg,
            )
            self.assertLess(
                svg.index('id="ordinary-roof-batting"'),
                svg.index('id="foreground-geometry"'),
            )
            self.assertLess(
                svg.index('id="under-rafter-batting"'),
                svg.index('id="foreground-geometry"'),
            )

    def test_places_pavatex_batting_in_its_depth_ordered_owner_group(self) -> None:
        owner_guid = "0AAAAAAAAAAAAAAAAAAAAA"
        annotation_guid = "1BBBBBBBBBBBBBBBBBBBBB"
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<marker id="batting-pavatex"><path '
                'style="stroke:black;stroke-width:0.18"/></marker>'
                '<path class="IfcSlab material-Woodfiberboard surface" '
                'd="M0,0 L10,0 L10,1 L0,1 Z"/>'
                f'<g ifc:guid="{owner_guid}" class="IfcSlab '
                'material-Woodfiberboard projection">'
                '<path id="original-owner"/></g>'
                '<g class="wall-insulation-foreground">'
                f'<g ifc:guid="{owner_guid}" class="IfcSlab '
                'material-Woodfiberboard projection">'
                '<path id="foreground-owner"/></g></g>'
                f'<g ifc:guid="{annotation_guid}" '
                'class="IfcAnnotation projection"><path/></g>'
                f'<polyline id="pavatex" class="GlobalId-{annotation_guid} '
                'IfcAnnotation pavatex-batting pavatex-target-projection '
                f'pavatex-owner-{owner_guid}" '
                'style="marker-start:url(#batting-pavatex)"/>'
                '</svg>',
                encoding="utf-8",
            )

            _postprocess_pavatex_batting(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            original_owner = svg.index('id="original-owner"')
            foreground_owner = svg.index('id="foreground-owner"')
            pavatex = svg.index('id="pavatex"')
            self.assertLess(original_owner, foreground_owner)
            self.assertLess(foreground_owner, pavatex)
            self.assertIn("stroke-width:0.06!important", svg)
            self.assertIn(
                'clip-path="url(#pavatex-batting-visible-material)"',
                svg,
            )
            self.assertEqual(
                svg.count('id="pavatex-batting-visible-material"'),
                1,
            )
            self.assertIn(
                f'<g ifc:guid="{annotation_guid}" '
                'class="IfcAnnotation projection" '
                'style="display:none!important">',
                svg,
            )

    def test_places_under_rafter_batting_in_its_depth_ordered_owner_group(
        self,
    ) -> None:
        owner_guid = "0AAAAAAAAAAAAAAAAAAAAA"
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                f'<g ifc:guid="{owner_guid}" class="IfcSlab projection">'
                '<path id="original-owner"/></g>'
                '<g class="depth-ordered-products">'
                f'<g ifc:guid="{owner_guid}" class="IfcSlab projection">'
                '<path id="ordered-owner"/></g>'
                '<g class="IfcBeam cut"><path id="purlin"/></g>'
                '</g>'
                '<polyline id="under-rafter" class="IfcAnnotation '
                'roof-batting under-rafter-batting '
                f'under-rafter-owner-{owner_guid} '
                'under-rafter-target-projection"/>'
                '</svg>',
                encoding="utf-8",
            )

            _postprocess_under_rafter_batting_depth(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            self.assertLess(
                svg.index('id="original-owner"'),
                svg.index('id="ordered-owner"'),
            )
            self.assertLess(
                svg.index('id="ordered-owner"'),
                svg.index('id="under-rafter"'),
            )
            self.assertLess(
                svg.index('id="under-rafter"'),
                svg.index('id="purlin"'),
            )

    def test_moves_wall_insulation_to_first_drawable_svg_layer(self) -> None:
        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">\n'
                '  <defs><pattern id="insulation"/></defs>\n'
                '  <g id="model"><path id="wall"/></g>\n'
                '  <line id="dimension" class="IfcAnnotation"/>\n'
                '  <path id="polystyrene" class="IfcAnnotation '
                'wall-insulation wall-insulation-polystyrene"/>\n'
                '  <polyline id="rockwool" class="IfcAnnotation '
                'wall-insulation wall-insulation-rockwool"/>\n'
                '  <line id="opening" class="IfcAnnotation wall-insulation '
                'wall-insulation-opening dashed"/>\n'
                '</svg>\n',
                encoding="utf-8",
            )

            _postprocess_wall_insulation_backdrop(svg_path)
            _postprocess_wall_insulation_backdrop(svg_path)

            svg = svg_path.read_text(encoding="utf-8")
            backdrop_start = svg.index(
                '<g class="wall-insulation-backdrop">'
            )
            backdrop_end = svg.index("</g>", backdrop_start)
            self.assertEqual(
                svg.count('<g class="wall-insulation-backdrop">'),
                1,
            )
            self.assertLess(svg.index("</defs>"), backdrop_start)
            self.assertLess(backdrop_end, svg.index('<g id="model">'))
            self.assertLess(
                svg.index('id="polystyrene"'),
                svg.index('id="rockwool"'),
            )
            self.assertLess(
                svg.index('id="rockwool"'),
                svg.index('id="opening"'),
            )
            self.assertGreater(svg.index('id="dimension"'), backdrop_end)
            self.assertNotIn("\n  \n", svg)

    def test_layers_elevation_insulation_by_closest_view_depth(self) -> None:
        near_guid = "0AAAAAAAAAAAAAAAAAAAAA"
        far_guid = "1BBBBBBBBBBBBBBBBBBBBB"
        spanning_guid = "2CCCCCCCCCCCCCCCCCCCCC"
        products = {
            near_guid: object(),
            far_guid: object(),
            spanning_guid: object(),
        }
        vertices = {
            products[near_guid]: (
                100.0,
                -100.0,
                -0.25,
                200.0,
                100.0,
                -0.75,
            ),
            products[far_guid]: (0.0, 0.0, -1.5, 1.0, 1.0, -2.0),
            products[spanning_guid]: (0.0, 0.0, -0.5, 0.0, 0.0, -3.0),
        }

        class Model:
            @staticmethod
            def by_guid(global_id: str) -> object:
                return products[global_id]

        class Drawing:
            ObjectPlacement = object()

        def create_shape(_settings: object, product: object) -> object:
            return type(
                "Shape",
                (),
                {
                    "geometry": type(
                        "Geometry",
                        (),
                        {"verts": vertices[product]},
                    )()
                },
            )()

        with TemporaryDirectory() as directory:
            svg_path = Path(directory) / "drawing.svg"
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:ifc="http://www.ifcopenshell.org/ns">\n'
                '  <defs/>\n'
                '  <g class="section target-view-ELEVATIONVIEW">\n'
                f'    <g class="IfcSlab projection" ifc:guid="{far_guid}">'
                '<path data-object="far"/></g>\n'
                f'    <g class="IfcSlab projection" ifc:guid="{near_guid}">'
                '<path data-object="near"/>'
                '<path d="M0,0 L1,0"/>'
                '<path d="M1,0 L1,1"/>'
                '<path d="M1,1 L0,1"/>'
                '<path d="M0,1 L0,0"/>'
                '</g>\n'
                f'    <g class="IfcWall cut {spanning_guid}">'
                '<path data-object="spanning"/></g>\n'
                '  </g>\n'
                '  <path class="IfcAnnotation wall-insulation" '
                'data-object="insulation"/>\n'
                '  <line class="IfcAnnotation" data-object="dimension"/>\n'
                '</svg>\n',
                encoding="utf-8",
            )

            with (
                patch(
                    "ifc_utils.ifcopenshell.util.placement.get_local_placement",
                    return_value=np.eye(4),
                ),
                patch(
                    "ifc_utils.ifcopenshell.geom.create_shape",
                    side_effect=create_shape,
                ),
            ):
                _postprocess_elevation_wall_insulation_depth(
                    svg_path,
                    Model(),
                    Drawing(),
                )
                _postprocess_elevation_wall_insulation_depth(
                    svg_path,
                    Model(),
                    Drawing(),
                )

            svg = svg_path.read_text(encoding="utf-8")
            insulation = svg.index('data-object="insulation"')
            self.assertEqual(svg.count("wall-insulation-depth-layer"), 1)
            self.assertEqual(svg.count('data-object="far"'), 1)
            self.assertEqual(svg.count('data-object="near"'), 2)
            self.assertEqual(svg.count('data-object="spanning"'), 2)
            self.assertEqual(
                svg.count('class="wall-insulation-foreground-mask"'),
                1,
            )
            self.assertEqual(
                svg.count('class="wall-insulation-foreground-fill"'),
                1,
            )
            self.assertLess(svg.index('data-object="far"'), insulation)
            self.assertGreater(
                svg.index('class="wall-insulation-foreground-mask"'),
                insulation,
            )
            self.assertGreater(svg.rindex('data-object="near"'), insulation)
            self.assertGreater(
                svg.rindex('data-object="spanning"'),
                insulation,
            )
            self.assertGreater(svg.index('data-object="dimension"'), insulation)

    def test_hides_miako_concrete_cover_seams(self) -> None:
        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        plan_rule = stylesheet.split(
            ".target-view-PLANVIEW .material-Concretetopping.projection",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke: none !important", plan_rule)

        cut_rule = stylesheet.split(
            ".IfcBuildingElementPart.material-Concretetopping.cut",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("stroke: none !important", cut_rule)

    def test_styles_stair_annotations_with_short_fine_dashes(self) -> None:
        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")

        stair_rule = stylesheet.split(
            ".PredefinedType-LINEWORK.stair.dashed,",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn(".PredefinedType-LINEWORK.stair-landing.dashed", stair_rule)
        self.assertIn("stroke-width: 0.08", stair_rule)
        self.assertIn("stroke-dasharray: 1, 0.67", stair_rule)
        self.assertIn(
            ".PredefinedType-LINEWORK.dashed { stroke-dasharray: 3, 2; }",
            stylesheet,
        )

    def test_styles_native_chimney_surfaces_and_outlines(self) -> None:
        stylesheet = (
            Path(__file__).parent / "bonsai_scripts" / "assets" / "plan.css"
        ).read_text(encoding="utf-8")
        self.assertNotIn("projected-chimney-fill", stylesheet)

        chimney_surface_rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .material-Chimney.surface",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", chimney_surface_rule)
        self.assertIn("stroke: none !important", chimney_surface_rule)

        chimney_projection_rule = stylesheet.split(
            ".target-view-ELEVATIONVIEW .material-Chimney.projection",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", chimney_projection_rule)
        self.assertIn("stroke: black !important", chimney_projection_rule)
        self.assertIn("stroke-width: 0.06 !important", chimney_projection_rule)

        chimney_cut_rule = stylesheet.split(
            ".IfcChimney.cut",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]
        self.assertIn("fill: white !important", chimney_cut_rule)
        self.assertNotIn("url(#", chimney_cut_rule)

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
        below_storey_wall = ground.wall(
            (0, 0),
            (1, 0),
            thickness=0.12,
            height=2.8,
            start_height=-0.1,
        )
        self.assertEqual(below_storey_wall.start_height, -0.1)
        self.assertAlmostEqual(below_storey_wall.end_height, 2.7)
        self.assertAlmostEqual(
            ifcopenshell.util.placement.get_local_placement(
                below_storey_wall.ObjectPlacement
            )[2, 3],
            -0.1,
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

    def test_adds_selected_wall_paths_to_another_storey(self) -> None:
        house = House("My house")
        foundation = house.storey("Foundations", elevation=0)
        ground = house.storey("Ground floor", elevation=0)
        load_bearing = house.wall_type(
            "Load bearing",
            layers=[
                ("Brick", 0.24),
                "axis",
                ("Rockwool", 0.20),
            ],
        )
        partition = house.wall_type(
            "Partition", layers=[("Brick", 0.12)]
        )
        foundation_concrete = house.wall_type(
            "Foundation concrete", layers=[("Concrete", 0.3)]
        )
        first = ground.wall(
            (0, 0), (4, 0), wall_type=load_bearing, height=2.8
        )
        partition_wall = ground.wall(
            (0, 1), (4, 1), wall_type=partition, height=2.8
        )
        second = ground.wall(
            (4, 0), (4, 5), wall_type=load_bearing, height=2.8
        )

        copied = foundation.add_walls_from(
            ground,
            source_wall_type=load_bearing,
            wall_type=foundation_concrete,
            start_height=-0.8,
            height=0.8,
        )

        self.assertEqual(ground.walls, (first, partition_wall, second))
        self.assertEqual(len(copied), 2)
        self.assertEqual(foundation.walls, copied)
        self.assertEqual(
            [(wall.start, wall.end) for wall in copied],
            [(first.start, first.end), (second.start, second.end)],
        )
        for wall in copied:
            self.assertEqual(wall.start_height, -0.8)
            self.assertEqual(wall.end_height, 0)
            self.assertEqual(
                ifcopenshell.util.element.get_type(wall),
                foundation_concrete,
            )
            self.assertFalse(wall.cuts)
            self.assertFalse(wall._openings)

        footings = foundation.add_strip_footings_from(
            ground,
            source_wall_type=load_bearing,
            structural_width=0.24,
            structural_center_offset=0.12,
            width=0.7,
            height=0.5,
            start_height=-1.3,
        )
        self.assertEqual(len(footings), 2)
        for footing, expected_length in zip(
            footings, (4.46, 5.46), strict=True
        ):
            self.assertTrue(footing.is_a("IfcFooting"))
            self.assertEqual(footing.PredefinedType, "STRIP_FOOTING")
            self.assertEqual(
                footing.ContainedInStructure[0].RelatingStructure,
                foundation.element,
            )
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), footing
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_y(shape.geometry), 0.7
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_x(shape.geometry),
                expected_length,
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_z(shape.geometry), 0.5
            )
            self.assertEqual(
                ifcopenshell.util.element.get_material(footing).Name,
                "Concrete",
            )
            self.assertTrue(
                ifcopenshell.util.element.get_pset(
                    footing, "Pset_FootingCommon", "LoadBearing"
                )
            )
        first_footing_placement = (
            ifcopenshell.util.placement.get_local_placement(
                footings[0].ObjectPlacement
            )
        )
        np.testing.assert_allclose(
            first_footing_placement[:3, 3],
            (-0.23, 0.12, -1.3),
            atol=1e-9,
        )

    def test_adds_reinforced_ring_beams_over_selected_wall_bodies(self) -> None:
        house = House("My house")
        ground = house.storey("Ground floor", elevation=0)
        load_bearing = house.wall_type(
            "Load bearing",
            layers=[
                ("Brick", 0.24),
                "axis",
                ("Rockwool", 0.20),
            ],
        )
        partition = house.wall_type(
            "Partition", layers=[("Brick", 0.12), "axis"]
        )
        source_wall = ground.wall(
            (0, 0), (4, 0), wall_type=load_bearing, height=2.8
        )
        ground.wall(
            (0, 1), (4, 1), wall_type=partition, height=2.8
        )

        ring_beams = ground.add_ring_beams_from(
            ground,
            source_wall_type=load_bearing,
            structural_width=0.24,
            structural_center_offset=0.12,
            height=0.21,
            start_height=2.8,
            bar_diameter=0.012,
            stirrup_diameter=0.008,
            concrete_cover=0.03,
        )

        self.assertEqual(len(ring_beams), 1)
        ring_beam = ring_beams[0]
        self.assertTrue(ring_beam.is_a("IfcBeam"))
        self.assertEqual(ring_beam.PredefinedType, "BEAM")
        self.assertEqual(ring_beam.ObjectType, "Ring beam")
        self.assertEqual(ring_beam.source_wall, source_wall)
        self.assertEqual(ring_beam.width, 0.24)
        self.assertEqual(ring_beam.height, 0.21)
        self.assertEqual(ring_beam.start_height, 2.8)
        self.assertEqual(
            ring_beam.ContainedInStructure[0].RelatingStructure,
            ground.element,
        )
        self.assertEqual(
            ifcopenshell.util.element.get_material(ring_beam).Name,
            "Concrete topping",
        )
        np.testing.assert_allclose(
            ring_beam.placement[:3, 3],
            (0.0, 0.12, 2.905),
            atol=1e-9,
        )
        ring_shape = ifcopenshell.geom.create_shape(
            ifcopenshell.geom.settings(), ring_beam
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_x(ring_shape.geometry), 4.0
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_y(ring_shape.geometry), 0.24
        )
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_z(ring_shape.geometry), 0.21
        )

        self.assertEqual(len(ring_beam.reinforcement), 4)
        expected_positions = {
            (0.0, 0.036, 2.836),
            (0.0, 0.204, 2.836),
            (0.0, 0.036, 2.974),
            (0.0, 0.204, 2.974),
        }
        actual_positions = set()
        for bar in ring_beam.reinforcement:
            self.assertTrue(bar.is_a("IfcReinforcingBar"))
            self.assertEqual(bar.PredefinedType, "MAIN")
            self.assertEqual(bar.NominalDiameter, 0.012)
            self.assertEqual(bar.BarLength, 4.0)
            self.assertEqual(
                ifcopenshell.util.element.get_material(bar).Name,
                "Ring beam reinforcement",
            )
            self.assertEqual(bar.Decomposes[0].RelatingObject, ring_beam)
            placement = ifcopenshell.util.placement.get_local_placement(
                bar.ObjectPlacement
            )
            actual_positions.add(
                tuple(round(float(value), 9) for value in placement[:3, 3])
            )
            bar_shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), bar
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_x(bar_shape.geometry), 4.0
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_y(bar_shape.geometry),
                0.012,
                delta=0.0002,
            )
            self.assertAlmostEqual(
                ifcopenshell.util.shape.get_z(bar_shape.geometry),
                0.012,
                delta=0.0002,
            )
        self.assertEqual(actual_positions, expected_positions)

        properties = ifcopenshell.util.element.get_pset(
            ring_beam, "BBIM_RingBeam"
        )
        self.assertEqual(properties["SourceWall"], source_wall.GlobalId)
        self.assertEqual(properties["BarDiameter"], 0.012)
        self.assertEqual(properties["StirrupDiameter"], 0.008)
        self.assertEqual(properties["ConcreteCover"], 0.03)

        drawing = house.add_drawing(
            "Ring beam section",
            x=2,
            y=0.12,
            z=2.905,
            radius=4,
            view="elevation",
            direction=(-1, 0, 0),
        )
        with TemporaryDirectory() as temporary_directory:
            svg_path = Path(temporary_directory) / "ring-beam.svg"
            reinforcement_groups = "".join(
                (
                    f'<g ifc:guid="{bar.GlobalId}" '
                    'class="IfcReinforcingBar '
                    'material-Ringbeamreinforcement cut"><path/></g>'
                )
                for bar in ring_beam.reinforcement
            )
            svg_path.write_text(
                '<svg data-scale="1:100" viewBox="0 0 100 100">'
                '<g ifc:guid="projected" class="IfcReinforcingBar '
                'material-Ringbeamreinforcement projection"><path/></g>'
                f'{reinforcement_groups}</svg>',
                encoding="utf-8",
            )
            _postprocess_ring_beam_stirrups(
                svg_path, house.model, drawing.element
            )
            _postprocess_ring_beam_stirrups(
                svg_path, house.model, drawing.element
            )
            svg = svg_path.read_text(encoding="utf-8")

        self.assertEqual(svg.count('class="ring-beam-stirrups'), 1)
        self.assertEqual(svg.count('class="ring-beam-stirrup"'), 1)
        self.assertIn('ifc:name="Ring beam 1"', svg)
        self.assertIn('stroke-width:0.08 !important', svg)
        self.assertIn('style="fill:none !important;stroke:#333', svg)
        self.assertEqual(
            svg.count('class="ring-beam-reinforcement-overlay"'),
            4,
        )
        self.assertGreater(
            svg.index('<g class="ring-beam-stirrups'),
            svg.rindex("material-Ringbeamreinforcement cut"),
        )
        for index in range(1, 5):
            source_id = f"ring-beam-reinforcement-overlay-source-{index}"
            self.assertEqual(svg.count(f'id="{source_id}"'), 1)
            self.assertEqual(
                svg.count(
                    f'href="#{source_id}" xlink:href="#{source_id}"'
                ),
                1,
            )
        self.assertNotIn('href="#projected"', svg)

    def test_ring_beam_band_replaces_masonry_and_splits_at_openings(self) -> None:
        house = House("Ring beam band")
        source = house.storey("Source", elevation=2)
        destination = house.storey("Destination", elevation=3)
        wall_type = house.wall_type("Load bearing", layers=[("Brick", 0.24), "axis"])
        wall = source.wall(
            (0, 0), (3, 4), wall_type=wall_type, start_height=0.2, height=3,
            cuts=[((0, 0, 4.8), (10, 0, 4.8), (0, 10, 4.8))],
        )
        wall.add_opening(at=1, width=1, sill_height=0.2, height=2.25)
        # A window starting exactly at the band's top must not split it.
        wall.add_window(at=3, width=1, sill_height=1.375, height=2.375)
        source.wall((0, 6), (3, 6), wall_type=wall_type, height=1.125)
        source.wall((0, 7), (3, 7), wall_type=wall_type, start_height=1.375, height=1)
        source.wall((0, 8), (3, 8), thickness=0.12, height=3)
        openings = tuple(wall._openings)
        voids = tuple(wall.HasOpenings)
        settings = ifcopenshell.geom.settings()
        before = ifcopenshell.geom.create_shape(settings, wall)
        before_volume = ifcopenshell.util.shape.get_volume(before.geometry)
        original_clips = json.loads(ifcopenshell.util.element.get_pset(wall, "BBIM_Boolean", "Data"))

        beams = destination.add_ring_beams_from(
            source, source_wall_type=wall_type, height=0.25, start_height=0.125,
            replace_wall_band=True,
        )

        self.assertEqual(len(beams), 2)
        self.assertEqual(tuple(wall._openings), openings)
        self.assertEqual(tuple(wall.HasOpenings), voids)
        self.assertEqual((wall.start_height, wall.height), (0.2, 3))
        self.assertEqual(len(wall.cuts), 1)
        self.assertEqual([beam.length for beam in beams], [1, 3])
        self.assertEqual([beam.source_wall for beam in beams], [wall, wall])
        for beam, along_start in zip(beams, (0, 2)):
            self.assertAlmostEqual(beam.start[2], 3.25)
            self.assertAlmostEqual(beam.end[2], 3.25)
            properties = ifcopenshell.util.element.get_pset(beam, "BBIM_RingBeam")
            self.assertEqual(properties["StartAlongWall"], along_start)
            self.assertEqual(properties["Length"], beam.length)
            for bar in beam.reinforcement:
                self.assertEqual(bar.BarLength, beam.length)
                shape = ifcopenshell.geom.create_shape(settings, bar)
                self.assertAlmostEqual(ifcopenshell.util.shape.get_x(shape.geometry), beam.length)
        after = ifcopenshell.geom.create_shape(settings, wall)
        self.assertAlmostEqual(
            before_volume - ifcopenshell.util.shape.get_volume(after.geometry),
            4 * 0.24 * 0.25,
        )
        boolean_ids = json.loads(ifcopenshell.util.element.get_pset(wall, "BBIM_Boolean", "Data"))
        self.assertEqual(boolean_ids[:-2], original_clips)
        self.assertEqual(house.model.by_id(boolean_ids[-1]).Operator, "DIFFERENCE")
        # The material change is retained in persisted IFC, not only wrappers.
        reloaded = ifcopenshell.file.from_string(house.model.to_string())
        saved_shape = ifcopenshell.geom.create_shape(settings, reloaded.by_guid(wall.GlobalId))
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(saved_shape.geometry),
            ifcopenshell.util.shape.get_volume(after.geometry),
        )

    def test_ring_beam_band_preserves_insulation_and_masonry_below_partial_openings(self) -> None:
        house = House("Composite ring beam wall")
        storey = house.storey("Upper", elevation=3)
        wall_type = house.wall_type(
            "Composite wall", layers=[("Brick", 0.24), "axis", ("Rockwool", 0.2)]
        )
        wall = storey.wall((0, 0), (5, 0), wall_type=wall_type, height=3)
        wall.add_window(at=2, width=1, sill_height=1.2, height=2.2)
        settings = ifcopenshell.geom.settings()
        before = ifcopenshell.geom.create_shape(settings, wall)
        beams = storey.add_ring_beams_from(
            storey, source_wall_type=wall_type, height=0.25, start_height=1.125,
            structural_width=0.24, structural_center_offset=0.12,
            replace_wall_band=True,
        )
        self.assertEqual(len(beams), 2)
        for beam in beams:
            self.assertAlmostEqual(beam.width, 0.24)
        after = ifcopenshell.geom.create_shape(settings, wall)
        self.assertAlmostEqual(
            ifcopenshell.util.shape.get_volume(before.geometry)
            - ifcopenshell.util.shape.get_volume(after.geometry),
            4 * 0.24 * 0.25,
        )

    def test_ring_beam_band_validates_height_and_option_before_mutation(self) -> None:
        house = House("Ring beam validation")
        storey = house.storey("Upper", elevation=3)
        storey.wall((0, 0), (4, 0), thickness=0.24, height=1.25)
        for kwargs, error, message in (
            ({"replace_wall_band": "yes"}, TypeError, "must be a boolean"),
            ({"replace_wall_band": True}, ValueError, "must fit within source wall"),
        ):
            with self.subTest(kwargs=kwargs):
                entity_count = len(list(house.model))
                with self.assertRaisesRegex(error, message):
                    storey.add_ring_beams_from(storey, height=0.25, start_height=1.125, **kwargs)
                self.assertEqual(len(list(house.model)), entity_count)

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
