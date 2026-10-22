import unittest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.type
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
import numpy as np

from section_outlines import add_section_outlines, _rings, _transform


class SectionOutlineTests(unittest.TestCase):
    def setUp(self):
        self.model = ifcopenshell.file(schema="IFC4")
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "section.svg"

    def product(self, kind="IfcWall", predefined=None, pset=None):
        obj = ifcopenshell.api.root.create_entity(self.model, ifc_class=kind, name=kind)
        if predefined:
            obj.PredefinedType = predefined
        if pset:
            prop = ifcopenshell.api.pset.add_pset(self.model, product=obj, name=pset)
            ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"Source": "test"})
        return obj

    def cut(self, obj, d, classes="", view="cut"):
        return (f'<g ifc:guid="{obj.GlobalId}" class="{obj.is_a()} {view} {classes}">'
                f'<path d="{d}"/></g>')

    def svg(self, content, *, width=100, view_width=100, scale=None):
        scale_attr = f' data-scale="{scale}"' if scale else ""
        text = (f'<svg{scale_attr} xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" '
                f'width="{width}mm" height="100mm" viewBox="0 0 {view_width} 100">{content}</svg>')
        self.path.write_text(text, encoding="utf-8")
        return text

    def outline(self, **kwargs):
        """Keep topology tests centred; dedicated offset tests use the public default."""
        kwargs.setdefault("offset_ratio", 0)
        return add_section_outlines(self.path, self.model, **kwargs)

    def lines(self):
        root = ET.parse(self.path).getroot()
        output = []

        def walk(e, matrix):
            matrix = matrix @ _transform(e.get("transform", ""))
            if e.get("class") == "section-outline":
                for ring in _rings(e):
                    output.append(LineString([(matrix @ (*p, 1))[:2] for p in ring]))
                # Open output boundary fragments are allowed too.
                if not _rings(e):
                    import re
                    values = [float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', e.get("d"))]
                    output.append(LineString([(matrix @ (x, y, 1))[:2] for x, y in zip(values[::2], values[1::2])]))
            for child in e:
                walk(child, matrix)

        walk(root, np.eye(3))
        return unary_union(output)

    def roof_ceiling(self, *, slope=0, view="elevation"):
        from ifc_utils import House
        house = House("Roof ceiling", mirror_x=False)
        self.model = house.model
        storey = house.storey("Upper", elevation=0)
        plane = storey.roof("Roof").plane(
            "Ceiling plane", points=((0, 0, 0), (1, 0, 0), (0, 1, slope)))
        board = plane.layer("Ceiling", outline=((0, 0), (10, 0), (10, 10), (0, 10)),
                            thickness=.1, material="Gypsum plasterboard")
        drawing = house.add_drawing("Section", 0, 0, 3, 20, view=view,
                                    direction=(1, 0, 0) if view == "elevation" else None)
        return house, plane, board, drawing

    def test_roof_plasterboard_adds_only_the_cut_underside(self):
        _, _, board, drawing = self.roof_ceiling()
        original = self.svg(self.cut(board, "M0 0H10V1H0Z"))
        self.outline(drawing=drawing.element, color="#445566")
        self.assertTrue(self.lines().equals(LineString([(0, 1), (10, 1)])))
        self.assertIn(original[:-6], self.path.read_text())
        self.assertIn("stroke:#445566;", self.path.read_text())
        result = self.path.read_text()
        self.outline(drawing=drawing.element, color="#445566")
        self.assertEqual(self.path.read_text(), result)

    def test_sloped_plasterboard_underside_respects_winding_mirroring_and_offset(self):
        _, _, board, drawing = self.roof_ceiling(slope=.5)
        for d in ("M0 0L10 5L10 6L0 1Z", "M0 1L10 6L10 5L0 0Z"):
            with self.subTest(d=d):
                self.svg('<g transform="translate(20,3) scale(-2,2)">' + self.cut(board, d) + '</g>')
                self.outline(drawing=drawing.element, width_mm=.6, offset_ratio=.25)
                shift = np.array((.5, 1)) / np.linalg.norm((.5, 1)) * .15
                expected = LineString([np.array((20, 5)) + shift, np.array((0, 15)) + shift])
                self.assertLess(self.lines().hausdorff_distance(expected), 1e-7)

    def test_plasterboard_underside_preserves_opening_gaps_and_hides_wall_contacts(self):
        _, _, board, drawing = self.roof_ceiling()
        wall = self.product()
        self.svg(self.cut(board, "M0 0H4V1H0Z M6 0H10V1H6Z")
                 + self.cut(wall, "M1 1H2V4H1Z"))
        self.outline(drawing=drawing.element, categories=("ceilings",))
        lines = self.lines()
        self.assertLess(lines.distance(LineString([(0, 1), (.5, 1)])), 1e-9)
        self.assertGreater(lines.distance(LineString([(1.2, 1), (1.8, 1)])), .1)
        self.assertGreater(lines.distance(LineString([(4.2, 1), (5.8, 1)])), .1)
        self.assertLess(lines.distance(LineString([(7, 1), (9, 1)])), 1e-9)
        # No vertical ends or upper edges, even beside a wall or opening.
        self.assertLess(abs(lines.bounds[1] - 1), 1e-9)
        self.assertLess(abs(lines.bounds[3] - 1), 1e-9)

    def test_plasterboard_underside_skips_projections_linings_other_materials_and_plans(self):
        _, plane, board, drawing = self.roof_ceiling()
        other = plane.layer("Other roof layer", outline=((0, 0), (10, 0), (10, 10), (0, 10)),
                            thickness=.1, material="Wood")
        lining = self.product("IfcCovering")
        self.svg(self.cut(board, "M0 0H10V1H0Z", view="projection")
                 + self.cut(other, "M0 2H10V3H0Z")
                 + self.cut(lining, "M0 4H10V5H0Z", "material-Gypsumplasterboard"))
        self.assertEqual(self.outline(drawing=drawing.element), 0)
        self.svg(self.cut(board, "M0 0H10V1H0Z"))
        self.assertEqual(self.outline(drawing=drawing.element, categories=("walls",)), 0)
        self.assertEqual(self.outline(), 0)  # No elevation camera: never guess a face.
        plan = plane.roof.storey.house.add_drawing("Plan", 0, 0, 3, 20)
        self.assertEqual(self.outline(drawing=plan.element), 0)

    def test_default_offset_is_a_quarter_of_printed_width_and_preserves_source(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0H5V10H0Z") + self.cut(wall, "M5 0H10V10H5Z"))
        add_section_outlines(self.path, self.model, width_mm=.6)
        self.assertTrue(self.lines().equals(box(-.15, -.15, 10.15, 10.15).boundary))
        result = self.path.read_text()
        self.assertIn(original[:-6], result)
        self.assertIn('data-offset-ratio="0.25"', result)
        self.assertIn('data-offset-mm="0.15"', result)
        add_section_outlines(self.path, self.model, width_mm=.6)
        self.assertEqual(self.path.read_text(), result)

    def test_outline_color_changes_only_the_added_layer(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0H5V10H0Z"))
        for color in ("black", "red", "#789", "#445566"):
            with self.subTest(color=color):
                self.outline(color=color)
                result = self.path.read_text()
                self.assertIn(original[:-6], result)
                self.assertEqual(result.count('id="section-outlines"'), 1)
                layer = next(e for e in ET.fromstring(result).iter()
                             if e.get("id") == "section-outlines")
                self.assertIn(f"stroke:{color};", layer.get("style"))
                self.assertTrue(self.lines().equals(box(0, 0, 5, 10).boundary))
                self.outline(color=color)
                self.assertEqual(self.path.read_text(), result)

    def test_offset_moves_into_room_holes_even_with_a_mirrored_view(self):
        wall = self.product()
        self.svg('<g transform="translate(20,0) scale(-1,1)">'
                 + self.cut(wall, "M0 0H10V10H0Z M2 2H8V8H2Z") + '</g>')
        add_section_outlines(self.path, self.model, width_mm=.6)
        expected = box(9.85, -.15, 20.15, 10.15).difference(box(12.15, 2.15, 17.85, 7.85))
        self.assertTrue(self.lines().equals(expected.boundary))

    def test_offset_respects_printed_scale_and_zero_restores_centred_lines(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H10V10H0Z"), width=100, view_width=200)
        add_section_outlines(self.path, self.model, width_mm=.6)
        self.assertTrue(self.lines().equals(box(-.3, -.3, 10.3, 10.3).boundary))
        add_section_outlines(self.path, self.model, width_mm=1)
        self.assertTrue(self.lines().equals(box(-.5, -.5, 10.5, 10.5).boundary))
        add_section_outlines(self.path, self.model, width_mm=.6, offset_ratio=0)
        self.assertTrue(self.lines().equals(box(0, 0, 10, 10).boundary))
        self.assertEqual(self.path.read_text().count('id="section-outlines"'), 1)

    def test_offset_does_not_resurrect_contacts_or_their_corner_returns(self):
        wall, footing = self.product(), self.product("IfcFooting")
        self.svg(self.cut(wall, "M0 0H2V2H0Z") + self.cut(footing, "M0 2H2V4H0Z"))
        add_section_outlines(self.path, self.model, width_mm=.6)
        bold = self.lines()
        self.assertEqual(bold.intersection(LineString([(-.15, 2.15), (2.15, 2.15)])).length, 0)
        self.assertAlmostEqual(bold.intersection(LineString([(-.15, -.15), (2.15, -.15)])).length, 2.3)

    def test_half_width_offset_keeps_the_heavy_stroke_outside_the_solid(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H10V10H0Z"))
        add_section_outlines(self.path, self.model, width_mm=.6, offset_ratio=.5)
        self.assertTrue(self.lines().equals(box(-.3, -.3, 10.3, 10.3).boundary))
        self.assertAlmostEqual(self.lines().buffer(.3).intersection(box(0, 0, 10, 10)).area, 0)

    def test_adjacent_materials_and_floor_wall_contact_have_no_internal_outlines(self):
        wall = self.product()
        floor = self.product("IfcSlab", "FLOOR")
        original = self.svg(self.cut(wall, "M0 0H10V10H0Z", "layer-material-Brick")
                            + self.cut(wall, "M10 0H12V10H10Z", "layer-material-Polystyrene")
                            + self.cut(floor, "M0 10H12V12H0Z"))
        self.assertEqual(self.outline(), 1)
        self.assertTrue(self.lines().equals(box(0, 0, 12, 12).boundary))
        result = self.path.read_text()
        self.assertIn(original[:-6], result)

    def test_layered_floors_inherit_their_type_and_have_bold_finished_tops(self):
        from ifc_utils import House
        house = House("Layered floor")
        ground = house.storey("Ground", elevation=0)
        floor = ground.floor_layer("Floor", outline=((0, 0), (5, 0), (5, 4), (0, 4)),
                                   thickness=.2, insulation_thickness=.15,
                                   insulation_material="Insulation")
        self.model = house.model
        self.assertIsNone(floor.PredefinedType)
        self.svg(self.cut(floor, "M0 0H10V2H0Z")
                 + self.cut(floor, "M0 0H10V.5H0Z", "IfcMaterialLayer layer-material-Floorbuildup")
                 + self.cut(floor, "M0 .5H10V2H0Z", "IfcMaterialLayer layer-material-Insulation"))
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))
        self.assertAlmostEqual(self.lines().intersection(LineString([(0, 0), (10, 0)])).length, 10)
        self.assertEqual(self.lines().intersection(LineString([(1, .5), (9, .5)])).length, 0)

    def test_foundations_keep_native_strokes_in_every_view_and_with_any_offset(self):
        slab = self.product("IfcSlab")
        slab_type = self.product("IfcSlabType", "BASESLAB")
        ifcopenshell.api.type.assign_type(self.model, related_objects=[slab], relating_type=slab_type)
        wall = self.product()
        wall_type = self.product("IfcWallType")
        material = ifcopenshell.api.material.add_material(self.model, name="ztracene bedneni")
        ifcopenshell.api.material.assign_material(self.model, products=[wall_type], material=material)
        ifcopenshell.api.type.assign_type(self.model, related_objects=[wall], relating_type=wall_type)
        floor = self.product("IfcSlab", "FLOOR")
        for view in ("PLANVIEW", "ELEVATIONVIEW"):
            for ratio in (0, .25, .5):
                with self.subTest(view=view, ratio=ratio):
                    original = self.svg(
                        f'<g class="section target-view-{view}">'
                        + self.cut(slab, "M0 5H10V7H0Z")
                        + self.cut(slab, "M0 5H10V6H0Z", "layer-material-Concrete")
                        + self.cut(wall, "M0 7H2V10H0Z")
                        + self.cut(wall, "M0 7H2V10H0Z", view="projection")
                        + self.cut(floor, "M2 1H8V3H2Z") + '</g>')
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    offset = .6 * ratio
                    self.assertTrue(self.lines().equals(
                        box(2-offset, 1-offset, 8+offset, 3+offset).boundary))
                    result = self.path.read_text()
                    self.assertIn(original[:-6], result)
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    self.assertEqual(self.path.read_text(), result)

    def test_foundation_only_has_no_extra_outline_and_still_masks_floor_contact(self):
        slab = self.product("IfcSlab", "BASESLAB")
        original = self.svg(self.cut(slab, "M0 2H10V7H0Z"))
        self.assertEqual(self.outline(), 0)
        self.assertEqual(self.path.read_text(), original)
        floor = self.product("IfcSlab", "FLOOR")
        self.svg(self.cut(slab, "M0 2H10V7H0Z") + self.cut(floor, "M0 0H10V2H0Z"))
        self.outline()
        self.assertEqual(self.lines().intersection(LineString([(0, 2), (10, 2)])).length, 0)
        self.assertAlmostEqual(self.lines().intersection(LineString([(0, 0), (10, 0)])).length, 10)

    def test_permanent_formwork_exclusion_uses_material_not_wall_name(self):
        for name in ("ztracene bedneni", "Ztracené bednění", "ztracene-bedneni", "Brick"):
            with self.subTest(material=name):
                wall = self.product()
                material = ifcopenshell.api.material.add_material(self.model, name=name)
                ifcopenshell.api.material.assign_material(self.model, products=[wall], material=material)
                original = self.svg(self.cut(wall, "M0 0H10V7H0Z"))
                count = self.outline()
                if name == "Brick":
                    self.assertGreater(count, 0)
                else:
                    self.assertEqual(count, 0)
                    self.assertEqual(self.path.read_text(), original)

    def test_roof_exclusion_also_respects_inherited_types(self):
        roof = self.product("IfcSlab")
        roof_type = self.product("IfcSlabType", "ROOF")
        ifcopenshell.api.type.assign_type(self.model, related_objects=[roof], relating_type=roof_type)
        self.svg(self.cut(roof, "M0 0H10V2H0Z"))
        self.assertEqual(self.outline(), 0)

    def test_real_wool_boundaries_exported_as_lines_merge_with_host_wall(self):
        from ifc_utils import House
        for view in ("plan", "elevation"):
            with self.subTest(view=view):
                house = House("Wool outlines")
                ground = house.storey("Ground", elevation=0)
                wall = ground.wall((0, 0), (4, 0), thickness=.24, height=3)
                drawing = house.add_drawing("Wool", 1.5, 0, 1.5, 4, view=view,
                                            direction=(-1, 0, 0) if view == "elevation" else None)
                drawing.add_wall_insulation(wall, thickness=.2, material="rockwool")
                boundary = next(a for a in house.model.by_type("IfcAnnotation")
                                if ifcopenshell.util.element.get_pset(
                                    a, "BBIM_WallInsulationBoundary", "HostWall") == wall.GlobalId)
                self.model = house.model
                # Simulate Bonsai's separate line elements, with a transformed
                # coordinate system and duplicated edges. Batting is inset and
                # must not be used to determine the insulation's outer face.
                coords = [(2, 0), (3, 0), (3, 2), (2, 2), (2, 0)]
                lines = [f'<line class="GlobalId-{boundary.GlobalId} wall-insulation '
                         f'wall-insulation-rockwool-boundary" x1="{a}" y1="{b}" x2="{c}" y2="{d}"/>'
                         for (a, b), (c, d) in zip(coords, coords[1:])]
                self.svg('<g transform="translate(4,5)">' + self.cut(wall, "M0 0H2V2H0Z")
                         + ''.join(lines + lines[:1]) + '</g>')
                self.outline()
                self.assertTrue(self.lines().equals(box(4, 5, 7, 7).boundary))
                # No heavy interface at x=6 between wall and wool.
                self.assertEqual(self.lines().intersection(LineString([(6, 5.1), (6, 6.9)])).length, 0)
                self.svg(''.join(lines))
                self.assertEqual(self.outline(), 0)
                self.svg(self.cut(wall, "M0 0H2V2H0Z") + ''.join(lines[:-1]))
                self.outline()
                self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_rooms_holes_concavity_and_door_gaps_are_preserved(self):
        wall = self.product()
        d = "M0 0H10V10H0Z M2 2H8V8H2Z"
        self.svg(self.cut(wall, d))
        self.outline()
        expected = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                           holes=[[(2, 2), (8, 2), (8, 8), (2, 8)]])
        self.assertTrue(self.lines().equals(expected.boundary))
        self.svg(self.cut(wall, "M0 0H10V10H8V2H2V10H0Z"))
        self.outline()
        self.assertTrue(self.lines().equals(Polygon([(0, 0), (10, 0), (10, 10), (8, 10),
                                                    (8, 2), (2, 2), (2, 10), (0, 10)]).boundary))

    def test_disabled_projections_roofs_furniture_and_timber_are_not_outlined(self):
        wall = self.product()
        roof = self.product("IfcSlab", "ROOF")
        wood = self.product("IfcBeam")
        furniture = self.product("IfcFurniture")
        content = self.cut(wall, "M0 0H2V2H0Z")
        content += self.cut(wall, "M3 0H5V2H3Z", view="projection")
        content += self.cut(roof, "M6 0H8V2H6Z")
        content += self.cut(wood, "M9 0H11V2H9Z")
        content += self.cut(furniture, "M12 0H14V2H12Z")
        self.svg(content)
        self.outline(projected_walls=False)
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_projected_walls_merge_with_cuts_by_default_and_leave_gaps(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H2V2H0Z")
                 + self.cut(wall, "M2 0H4V2H2Z M6 0H8V2H6Z", view="projection"))
        self.outline()
        expected = unary_union([box(0, 0, 4, 2), box(6, 0, 8, 2)]).boundary
        self.assertTrue(self.lines().equals(expected))
        result = self.path.read_text()
        self.outline()
        self.assertEqual(self.path.read_text(), result)
        self.outline(projected_walls=False)
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))
        self.outline(categories=("ceilings",))
        self.assertTrue(self.lines().is_empty)

    def test_css_safe_surface_guids_resolve_through_native_product_groups(self):
        wall = self.product()
        wall.GlobalId = "14$J2N_v56dvt91LW0voYz"
        plate = self.product("IfcBeam", "USERDEFINED")
        plate.GlobalId = "3c01u7Tlr4$BVWZwVQ9B0C"
        plate.ObjectType = "WALL_PLATE"
        underscore_wall = self.product()
        underscore_wall.GlobalId = "0jptrZUo92VBdLb7p_zadq"
        for obj in (wall, plate, underscore_wall):
            for surface_first in (True, False):
                with self.subTest(kind=obj.is_a(), surface_first=surface_first):
                    alias = obj.GlobalId.replace("$", "").replace("_", "")
                    native = self.cut(obj, "M0 0H10 M0 2H10", f"GlobalId-{alias}", view="projection")
                    surface = (f'<path class="{obj.is_a()} GlobalId-{alias} surface" '
                               'd="M0 0H10V2H0Z"/>')
                    original = self.svg(surface + native if surface_first else native + surface)
                    self.outline()
                    self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))
                    result = self.path.read_text()
                    self.assertIn(original[:-6], result)
                    self.outline()
                    self.assertEqual(self.path.read_text(), result)
                    self.assertEqual(self.outline(projected_walls=False), 0)

    def test_css_safe_surface_aliases_do_not_select_unrelated_timber(self):
        beam = self.product("IfcBeam")
        beam.GlobalId = "3c01u7Tlr4$BVWZwVQ9B0C"
        alias = beam.GlobalId.replace("$", "")
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H2V2H0Z")
                 + f'<path class="IfcBeam GlobalId-{alias} surface" d="M5 0H10V2H5Z"/>'
                 + self.cut(beam, "M5 0H10", f"GlobalId-{alias}", view="projection"))
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_ambiguous_css_safe_guids_are_not_guessed_but_exact_guids_still_work(self):
        alias = "0" + "A" * 20
        walls = [self.product(), self.product()]
        for characters in (("$", "$"), ("_", "_"), ("$", "_")):
            with self.subTest(characters=characters):
                for wall, index, char in zip(walls, (3, 5), characters):
                    wall.GlobalId = alias[:index] + char + alias[index:]
                native = "".join(self.cut(w, "", f"GlobalId-{alias}", view="projection") for w in walls)
                surface = f'<path class="IfcWall GlobalId-{alias} surface" d="M0 0H10V2H0Z"/>'
                self.svg(surface + native)
                self.assertEqual(self.outline(), 0)
                self.svg(surface.replace("<path ", f'<path ifc:guid="{walls[0].GlobalId}" ') + native)
                self.outline()
                self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))

    def test_opening_masks_preserve_cut_jambs_and_other_projected_walls(self):
        wall, other_wall = self.product(), self.product()
        for ratio in (0, .25, .5):
            for scale, view_width in (("1:100", 100), ("1:50", 100), ("1:100", 200)):
                with self.subTest(ratio=ratio, scale=scale, view_width=view_width):
                    inset = 25 / float(scale.split(":")[1]) * view_width / 100
                    content = (self.cut(wall, "M0 0H4V2H0Z M6 0H10V2H6Z")
                               + self.cut(wall, "M0 0H12V2H0Z", view="projection")
                               + self.cut(other_wall, "M14 0H16V2H14Z", view="projection")
                               + f'<polygon class="door-overhead-mask" '
                                 f'points="{4+inset},0 {6-inset},0 {6-inset},2 {4+inset},2"/>'
                                 '<line class="IfcAnnotation door-overhead" '
                                 'x1="4.25" y1="0" x2="5.75" y2="0"/>')
                    original = self.svg(content, view_width=view_width, scale=scale)
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    offset = .6 * ratio * view_width / 100
                    expected = unary_union([box(0, 0, 4, 2), box(6, 0, 12, 2),
                                            box(14, 0, 16, 2)]).buffer(offset, join_style=2).boundary
                    self.assertLess(self.lines().hausdorff_distance(expected), 1e-8)
                    result = self.path.read_text()
                    self.assertIn(original[:-6], result)
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    self.assertEqual(self.path.read_text(), result)
                    self.outline(projected_walls=False, width_mm=.6, offset_ratio=ratio)
                    expected = unary_union([box(0, 0, 4, 2), box(6, 0, 10, 2)]).buffer(
                        offset, join_style=2).boundary
                    self.assertLess(self.lines().hausdorff_distance(expected), 1e-8)

    def test_opening_exclusions_apply_after_fragmented_projection_completion(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H4V2H0Z M6 0H10V2H6Z")
                 + self.cut(wall, "M0 0H10V2H0", view="projection")
                 + '<polygon class="door-overhead-mask" points="4.25,0 5.75,0 5.75,2 4.25,2"/>',
                 scale="1:100")
        self.outline()
        self.assertTrue(self.lines().equals(unary_union([box(0, 0, 4, 2), box(6, 0, 10, 2)]).boundary))

    def test_opening_exclusions_follow_mirrored_rotated_scaled_svg_transforms(self):
        wall = self.product()
        for transform in ("translate(30,5) scale(-2,2)", "translate(30,5) rotate(30)"):
            with self.subTest(transform=transform):
                self.svg(f'<g transform="{transform}">'
                         + self.cut(wall, "M0 0H4V2H0Z M6 0H10V2H6Z")
                         + self.cut(wall, "M0 0H10V2H0Z", view="projection")
                         + '<polygon class="door-overhead-mask" points="4.25,0 5.75,0 5.75,2 4.25,2"/>'
                           '</g>', scale="1:100")
                self.outline(width_mm=.6, offset_ratio=.25)
                projected = self.lines()
                self.outline(projected_walls=False, width_mm=.6, offset_ratio=.25)
                self.assertLess(projected.hausdorff_distance(self.lines()), .01)
                self.assertAlmostEqual(projected.length, self.lines().length, delta=.03)

    def test_degenerate_legacy_masks_do_not_remove_projected_walls(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H10V2H0Z", view="projection")
                 + '<polygon class="door-overhead-mask" points="2,0 4,0 8,0 6,0"/>',
                 scale="1:100")
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))

    def test_projected_segment_network_merges_internal_divisions_without_closing_gaps(self):
        wall = self.product()
        # Separate edges, a shared face division, and an incomplete contour.
        segments = ("M0 0H5", "M5 0H10", "M10 0V2", "M10 2H5", "M5 2H0", "M0 2V0",
                    "M5 0V2", "M20 0H22V2")
        self.svg('<g transform="translate(3,4) scale(2)">' + ''.join(
            self.cut(wall, d, view="projection") for d in segments) + '</g>')
        self.outline()
        self.assertTrue(self.lines().equals(box(3, 4, 23, 8).boundary))
        self.assertEqual(self.lines().intersection(LineString([(13, 4.1), (13, 7.9)])).length, 0)

    def test_projected_wall_holes_and_nested_islands_are_preserved(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H10V10H0Z M2 2H8V8H2Z M4 4H6V6H4Z M10 5H12",
                          view="surface"))
        self.outline()
        expected = box(0, 0, 10, 10).difference(box(2, 2, 8, 8)).union(box(4, 4, 6, 6))
        self.assertTrue(self.lines().equals(expected.boundary))

    def test_projected_wall_hosts_include_wool_and_eps_but_not_unrelated_projections(self):
        primary, secondary = self.product(), self.product()
        wool, eps = self.product("IfcAnnotation"), self.product("IfcAnnotation")
        for obj, pset in ((wool, "BBIM_WallInsulationBoundary"), (eps, "BBIM_WallInsulation")):
            prop = ifcopenshell.api.pset.add_pset(self.model, product=obj, name=pset)
            ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"HostWall": secondary.GlobalId})
        coords = [(2, 0), (3, 0), (3, 2), (2, 2), (2, 0)]
        wool_svg = ''.join(f'<line class="GlobalId-{wool.GlobalId} wall-insulation '
                           f'wall-insulation-rockwool-boundary" x1="{a}" y1="{b}" x2="{c}" y2="{d}"/>'
                           for (a, b), (c, d) in zip(coords, coords[1:]))
        content = self.cut(primary, "M0 0H2V2H0Z", secondary.GlobalId, view="projection") + wool_svg
        content += f'<path class="GlobalId-{eps.GlobalId} wall-insulation" d="M3 0H4V2H3Z"/>'
        for kind, predefined in (("IfcSlab", "FLOOR"), ("IfcSlab", "ROOF"), ("IfcFurniture", None),
                                 ("IfcBeam", None)):
            content += self.cut(self.product(kind, predefined), "M10 0H20V20H10Z", view="projection")
        self.svg(content)
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 4, 2).boundary))
        self.outline(projected_walls=False)
        self.assertTrue(self.lines().is_empty)

    def test_wall_plates_join_wall_and_facade_regions_without_outlining_other_roof_members(self):
        wall = self.product()
        plate = self.product("IfcBeam", "USERDEFINED")
        plate.ObjectType = "WALL_PLATE"
        insulation = self.product("IfcAnnotation")
        prop = ifcopenshell.api.pset.add_pset(self.model, product=insulation, name="BBIM_WallInsulation")
        ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"HostWall": wall.GlobalId})
        content = self.cut(wall, "M0 2H10V4H0Z")
        content += self.cut(plate, "M0 1H10V2H0Z", view="projection")
        content += f'<path class="GlobalId-{insulation.GlobalId} wall-insulation" d="M0 0H10V1H0Z"/>'
        for kind in ("RAFTER", "PURLIN", "BEAM"):
            other = self.product("IfcBeam", "USERDEFINED")
            other.ObjectType = kind
            content += self.cut(other, "M20 0H30V10H20Z", view="projection")
        self.svg(content)
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 10, 4).boundary))
        self.outline(projected_walls=False)
        expected = unary_union([box(0, 0, 10, 1), box(0, 2, 10, 4)]).boundary
        self.assertTrue(self.lines().equals(expected))

    def test_cut_wall_plate_is_a_wall_assembly_even_when_aggregated_in_a_roof(self):
        plate = self.product("IfcBeam", "USERDEFINED")
        plate.ObjectType = "WALL_PLATE"
        roof = self.product("IfcRoof")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[plate], relating_object=roof)
        self.svg(self.cut(plate, "M0 0H2V2H0Z"))
        self.outline(projected_walls=False)
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_wall_plate_then_ring_beam_contours_complete_independently_of_svg_order(self):
        wall = self.product()
        plate = self.product("IfcBeam", "USERDEFINED")
        plate.ObjectType = "WALL_PLATE"
        cap = self.product("IfcBeam", pset="BBIM_RingBeam")
        anchor = self.cut(wall, "M10 0H12V3H10Z")
        # The plate is open against the right-hand wall. Only after completing
        # it can its upper/lower faces close the surrounding ring-beam strips.
        plate_svg = self.cut(plate, "M0 1H10 M0 2H10 M0 1V2", view="projection")
        cap_svg = self.cut(cap, "M0 0H10 M0 3H10 M0 0V1 M0 2V3", view="projection")
        for projections in (cap_svg + plate_svg, plate_svg + cap_svg):
            with self.subTest(projections=projections):
                self.svg(anchor + projections)
                self.outline()
                self.assertTrue(self.lines().equals(box(0, 0, 12, 3).boundary))
                result = self.path.read_text()
                self.outline()
                self.assertEqual(self.path.read_text(), result)

    def test_ring_beam_projection_includes_source_wall_insulation_even_when_masonry_is_hidden(self):
        wall = self.product()
        cap = self.product("IfcBeam", pset="BBIM_RingBeam")
        prop = ifcopenshell.util.element.get_pset(cap, "BBIM_RingBeam")
        ifcopenshell.api.pset.edit_pset(self.model, pset=self.model.by_id(prop["id"]),
                                       properties={"SourceWall": wall.GlobalId})
        insulation = self.product("IfcAnnotation")
        prop = ifcopenshell.api.pset.add_pset(self.model, product=insulation, name="BBIM_WallInsulation")
        ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"HostWall": wall.GlobalId})
        eps = f'<path class="GlobalId-{insulation.GlobalId} wall-insulation" d="M0 2H10V3H0Z"/>'
        self.svg(self.cut(cap, "M0 0H10V2H0Z", view="projection") + eps)
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 10, 3).boundary))
        self.outline(projected_walls=False)
        self.assertTrue(self.lines().is_empty)

    def test_cut_solids_can_complete_fragmented_wall_contours_without_inventing_closing_edges(self):
        wall = self.product()
        occluder = self.product("IfcBeam")
        eps = self.product("IfcAnnotation")
        prop = ifcopenshell.api.pset.add_pset(self.model, product=eps, name="BBIM_WallInsulation")
        ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"HostWall": wall.GlobalId})
        # Like the street ring beam: the middle of each end return is hidden
        # by another cut member, whose true boundary completes the two strips.
        fragmented = self.cut(wall, "M0 0H10 M0 2H10 M0 0V.5 M0 1.5V2 M10 0V.5 M10 1.5V2",
                              view="projection")
        insulation = f'<path class="GlobalId-{eps.GlobalId} wall-insulation" d="M0 2H10V3H0Z"/>'
        for view in ("cut", "projection"):
            with self.subTest(covering_view=view):
                self.svg(fragmented + self.cut(occluder, "M0 .5H10V1.5H0Z", view=view) + insulation)
                self.outline()
                bold = self.lines()
                self.assertAlmostEqual(bold.intersection(LineString([(0, 0), (10, 0)])).length, 10)
                self.assertAlmostEqual(bold.intersection(LineString([(0, 3), (10, 3)])).length, 10)
                # Neither the cap/insulation seam nor the occluder contacts get heavy.
                for y in (.5, 1.5, 2):
                    self.assertEqual(bold.intersection(LineString([(1, y), (9, y)])).length, 0)
                self.outline(projected_walls=False)
                self.assertTrue(self.lines().is_empty)
        self.svg(fragmented + insulation)
        self.assertEqual(self.outline(), 0)
        self.svg(fragmented + self.cut(occluder, "M0 .5H10V1.5", view="projection") + insulation)
        self.assertEqual(self.outline(), 0)
        # A distant enclosing solid must not be mistaken for a wall/room face.
        self.svg(fragmented + self.cut(occluder, "M-20 -20H20V20H-20Z") + insulation)
        self.assertEqual(self.outline(), 0)

    def test_all_visible_projected_timber_masks_wall_contacts_without_needing_completion(self):
        wall, beam = self.product(), self.product("IfcBeam")
        for view in ("projection", "surface"):
            for ratio in (0, .25, .5):
                with self.subTest(view=view, ratio=ratio):
                    original = self.svg(self.cut(wall, "M0 0H10V4H0Z")
                                        + self.cut(beam, "M3 4H7V6H3Z", view=view))
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    offset = .6 * ratio
                    bold = self.lines()
                    self.assertEqual(bold.intersection(
                        LineString([(3.2, 4+offset), (6.8, 4+offset)])).length, 0)
                    for start, end in ((.2, 2.5), (7.5, 9.8)):
                        self.assertAlmostEqual(bold.intersection(
                            LineString([(start, 4+offset), (end, 4+offset)])).length, end-start)
                    self.assertAlmostEqual(bold.intersection(
                        LineString([(.2, -offset), (9.8, -offset)])).length, 9.6)
                    # The timber's exposed perimeter is still only its native thin line.
                    self.assertEqual(bold.intersection(
                        LineString([(3.2, 6), (6.8, 6)])).length, 0)
                    result = self.path.read_text()
                    self.assertIn(original[:-6], result)
                    self.outline(width_mm=.6, offset_ratio=ratio)
                    self.assertEqual(self.path.read_text(), result)
                    self.outline(projected_walls=False, width_mm=.6, offset_ratio=ratio)
                    self.assertLess(self.lines().hausdorff_distance(
                        box(0, 0, 10, 4).buffer(offset, join_style=2).boundary), 1e-8)

    def test_timber_crossing_a_fragmented_wall_hides_both_thick_end_caps(self):
        wall, beam = self.product(), self.product("IfcBeam")
        self.svg(self.cut(wall, "M0 0H2V2H0Z M0 4H2V6H0Z", view="projection")
                 + self.cut(beam, "M-2 2H4V4H-2Z", view="projection"))
        self.outline(width_mm=.6, offset_ratio=.25)
        bold = self.lines()
        for y in (2.15, 3.85):
            self.assertEqual(bold.intersection(LineString([(-.15, y), (2.15, y)])).length, 0)
        for y in (-.15, 6.15):
            self.assertAlmostEqual(bold.intersection(
                LineString([(-.15, y), (2.15, y)])).length, 2.3)

    def test_open_projected_timber_edges_do_not_invent_a_contact_mask(self):
        wall, beam = self.product(), self.product("IfcBeam")
        self.svg(self.cut(wall, "M0 0H10V4H0Z")
                 + self.cut(beam, "M3 4H7V6H3", view="projection"))
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 10, 4).boundary))

    def test_contact_with_unselected_cut_solids_is_not_air(self):
        wall, footing = self.product(), self.product("IfcFooting")
        self.svg(self.cut(wall, "M0 0H2V2H0Z") + self.cut(footing, "M0 2H2V4H0Z"))
        self.outline()
        self.assertLess(self.lines().intersection(LineString([(0, 2), (2, 2)])).length, .001)
        self.assertAlmostEqual(self.lines().length, 6, delta=.01)

    def test_miako_parts_form_one_ceiling_and_do_not_outline_internal_cells(self):
        slab = self.product("IfcSlab", "FLOOR", pset="BBIM_MiakoSlab")
        part = self.product("IfcBuildingElementPart")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[part], relating_object=slab)
        self.svg(self.cut(part, "M0 0H10V2H0Z M1 .5H2V1.5H1Z"))
        self.outline(categories=("ceilings",))
        self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))

    def test_ceiling_finishes_ring_beams_and_insulation_are_assembly_members(self):
        wall = self.product()
        ring = self.product("IfcBeam", pset="BBIM_RingBeam")
        ceiling = self.product("IfcCovering", "CEILING")
        insulation = self.product("IfcAnnotation")
        prop = ifcopenshell.api.pset.add_pset(self.model, product=insulation, name="BBIM_WallInsulation")
        ifcopenshell.api.pset.edit_pset(self.model, pset=prop, properties={"HostWall": wall.GlobalId})
        insulation_svg = (f'<polyline class="GlobalId-{insulation.GlobalId} wall-insulation" '
                          'points="2,0 3,0 3,2 2,2 2,0"/>')
        self.svg(self.cut(wall, "M0 0H2V2H0Z") + self.cut(ring, "M0 2H3V3H0Z")
                 + self.cut(ceiling, "M0 3H3V4H0Z") + insulation_svg)
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 3, 4).boundary))
        self.svg(insulation_svg)
        self.assertEqual(self.outline(), 0)

    def test_merged_wall_cut_preserves_insulation_of_every_host(self):
        primary, secondary = self.product(), self.product()
        wool = self.product("IfcAnnotation")
        prop = ifcopenshell.api.pset.add_pset(self.model, product=wool,
                                            name="BBIM_WallInsulationBoundary")
        ifcopenshell.api.pset.edit_pset(self.model, pset=prop,
                                       properties={"HostWall": secondary.GlobalId})
        coords = [(2, 0), (3, 0), (3, 2), (2, 2), (2, 0)]
        wool_svg = ''.join(f'<line class="GlobalId-{wool.GlobalId} wall-insulation '
                           f'wall-insulation-rockwool-boundary" x1="{a}" y1="{b}" x2="{c}" y2="{d}"/>'
                           for (a, b), (c, d) in zip(coords, coords[1:]))
        # The explicit GUID always resolves to the primary wall first. The
        # secondary wall appears only as an alias on the merged cut polygon.
        for classes in (secondary.GlobalId, f"{secondary.GlobalId} {primary.GlobalId}"):
            with self.subTest(classes=classes):
                self.svg(self.cut(primary, "M0 0H2V2H0Z", classes) + wool_svg)
                self.outline()
                self.assertTrue(self.lines().equals(box(0, 0, 3, 2).boundary))
                result = self.path.read_text()
                self.outline()
                self.assertEqual(self.path.read_text(), result)
        # Aliases on projected geometry must not qualify as cut hosts.
        self.svg(self.cut(primary, "M0 0H2V2H0Z", secondary.GlobalId, view="projection") + wool_svg)
        self.assertEqual(self.outline(projected_walls=False), 0)

    def test_scale_transforms_repeatability_and_annotation_order(self):
        wall = self.product()
        content = ('<g transform="translate(2, 3) scale(2)">' + self.cut(wall, "m0 0h2v2h-2z")
                   + '<g class="dimension-overlays"><text>Dimension</text></g></g>')
        self.svg(content, width=100, view_width=200)
        self.outline(width_mm=.2)
        self.assertTrue(self.lines().equals(box(2, 3, 6, 7).boundary))
        result = self.path.read_text()
        self.assertLess(result.index('id="section-outlines"'), result.index('class="dimension-overlays"'))
        self.assertIn("stroke-width:0.4", result)
        self.outline(width_mm=.2)
        self.assertEqual(self.path.read_text(), result)
        self.outline(width_mm=.3)
        self.assertEqual(self.path.read_text().count('id="section-outlines"'), 1)
        self.assertIn("stroke-width:0.6", self.path.read_text())

    def test_no_selected_geometry_leaves_svg_unchanged_and_removes_stale_layer(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0H2V2H0Z", view="projection"))
        self.assertEqual(self.outline(projected_walls=False), 0)
        self.assertEqual(self.path.read_text(), original)
        self.svg(self.cut(wall, "M0 0H2V2H0Z"))
        self.outline()
        self.assertEqual(self.outline(categories=("ceilings",)), 0)
        self.assertNotIn('id="section-outlines"', self.path.read_text())

    def test_solid_insulation_continuations_never_receive_thick_outlines(self):
        wall = self.product()
        annotation = self.product("IfcAnnotation")
        original = self.svg(
            self.cut(wall, "M0 0H2V10H0Z")
            + f'<g ifc:guid="{annotation.GlobalId}" class="IfcAnnotation '
              'wall-insulation wall-insulation-opening">'
              '<line x1="5" y1="1" x2="8" y2="1"/>'
              '<line x1="10" y1="1" x2="13" y2="1"/></g>')
        self.outline()
        self.assertTrue(self.lines().equals(box(0, 0, 2, 10).boundary))
        self.assertIn(original[:-6], self.path.read_text())

    def test_open_paths_are_not_closed_with_an_invented_hull(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0L10 0L10 10"))
        self.assertEqual(self.outline(), 0)
        self.assertEqual(self.path.read_text(), original)

    def test_bad_configuration_does_not_edit_svg(self):
        original = self.svg("")
        for kwargs in ({"width_mm": 0}, {"width_mm": True}, {"width_mm": float("nan")},
                       {"categories": "walls"}, {"categories": ("roof",)},
                       {"projected_walls": 1}, {"projected_walls": "false"},
                       {"offset_ratio": -.1}, {"offset_ratio": True},
                       {"offset_ratio": float("inf")}, {"offset_ratio": float("nan")},
                       {"color": None}, {"color": True}, {"color": ""},
                       {"color": "#ggg"}, {"color": "#12345"},
                       {"color": "red;stroke-width:99"}, {"color": 'red"/>'}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                self.outline(**kwargs)
            self.assertEqual(self.path.read_text(), original)

    def test_drawing_option_is_opt_in_persisted_and_validated(self):
        from ifc_utils import House
        house = House("Outlines")
        normal = house.add_drawing("Normal", 0, 0, 2, 5)
        outlined = house.add_drawing("Outlined", 0, 0, 2, 5, section_outline_width=.2,
                                     section_outline_projected_walls=True, section_outline_color="#ABC")
        cut_only = house.add_drawing("Cut only", 0, 0, 2, 5, section_outline_width=.2,
                                     section_outline_projected_walls=False, section_outline_offset_ratio=0)
        self.assertIsNone(ifcopenshell.util.element.get_pset(normal.element, "EPset_Drawing", "SectionOutlineWidth"))
        self.assertEqual(ifcopenshell.util.element.get_pset(outlined.element, "EPset_Drawing", "SectionOutlineWidth"), .2)
        self.assertEqual(outlined.section_outline_color, "#aabbcc")
        self.assertEqual(ifcopenshell.util.element.get_pset(
            outlined.element, "EPset_Drawing", "SectionOutlineColor"), "#aabbcc")
        self.assertEqual(ifcopenshell.util.element.get_pset(
            cut_only.element, "EPset_Drawing", "SectionOutlineColor"), "#000000")
        self.assertIsNone(ifcopenshell.util.element.get_pset(
            normal.element, "EPset_Drawing", "SectionOutlineColor"))
        self.assertTrue(outlined.section_outline_projected_walls)
        self.assertIs(ifcopenshell.util.element.get_pset(
            outlined.element, "EPset_Drawing", "SectionOutlineProjectedWalls"), True)
        self.assertIs(ifcopenshell.util.element.get_pset(
            cut_only.element, "EPset_Drawing", "SectionOutlineProjectedWalls"), False)
        self.assertEqual(outlined.section_outline_offset_ratio, .25)
        self.assertEqual(ifcopenshell.util.element.get_pset(
            outlined.element, "EPset_Drawing", "SectionOutlineOffsetRatio"), .25)
        self.assertEqual(ifcopenshell.util.element.get_pset(
            cut_only.element, "EPset_Drawing", "SectionOutlineOffsetRatio"), 0)
        for value in (0, -.1, True, float("inf")):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_width=value)
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_projected_walls=value)
        for value in (-.1, True, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_offset_ratio=value)
        for value in (None, True, 123, "", "not-a-color", "#ggg", "red;stroke-width:99"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_color=value)

    def test_renderer_adds_outlines_before_export_and_above_model_fills(self):
        from ifc_utils import House
        for view, projected, offset, color in (("plan", True, .25, "black"), ("plan", False, 0, "red"),
                                               ("elevation", True, .5, "#ABC"), ("elevation", False, .25, "#445566")):
            with self.subTest(view=view, projected=projected, offset=offset):
                house = House("Outlines")
                wall = ifcopenshell.api.root.create_entity(house.model, ifc_class="IfcWall", name="Wall")
                drawing = house.add_drawing("Outlined", 0, 0, 2, 5, view=view,
                                            direction=(1, 0, 0) if view == "elevation" else None,
                                            section_outline_projected_walls=projected,
                                            section_outline_offset_ratio=offset,
                                            section_outline_color=color,
                                            section_outline_width=.25)
                house.write(Path(self.directory.name) / "house.ifc")
                exports = []

                def run(command, *, check):
                    if "--output" in command:
                        self.svg(self.cut(wall, "M0 0H2V2H0Z")
                                 + self.cut(wall, "M2 0H3V2H2Z", view="projection")
                                 + '<g class="dimension-overlays"><text>Dimension</text></g>')
                    else:
                        result = self.path.read_text()
                        self.assertIn('id="section-outlines"', result)
                        self.assertIn('data-width-mm="0.25"', result)
                        layer = next(e for e in ET.fromstring(result).iter()
                                     if e.get("id") == "section-outlines")
                        self.assertIn(f"stroke:{drawing.section_outline_color};", layer.get("style"))
                        self.assertLess(result.index('id="section-outlines"'),
                                        result.index('class="dimension-overlays"'))
                        self.assertAlmostEqual(self.lines().bounds[2], (3 if projected else 2) + .25 * offset)
                        self.assertIn(f'data-offset-mm="{.25 * offset:g}"', result)
                        exports.append(command)
                        target = next(arg.split("=", 1)[1] for arg in command
                                      if arg.startswith("--export-filename="))
                        Path(target).write_bytes(b"png")
                    return subprocess.CompletedProcess(command, 0)

                with patch("ifc_utils.shutil.which", return_value="/usr/bin/blender"), \
                     patch("ifc_utils.subprocess.run", side_effect=run):
                    drawing.render(self.path, png=True)
                self.assertEqual(len(exports), 1)


if __name__ == "__main__":
    unittest.main()
