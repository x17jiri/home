import unittest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ifcopenshell
import ifcopenshell.api.aggregate
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

    def svg(self, content, *, width=100, view_width=100):
        text = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" '
                f'width="{width}mm" height="100mm" viewBox="0 0 {view_width} 100">{content}</svg>')
        self.path.write_text(text, encoding="utf-8")
        return text

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

    def test_adjacent_materials_and_floor_wall_contact_have_no_internal_outlines(self):
        wall = self.product()
        floor = self.product("IfcSlab", "FLOOR")
        original = self.svg(self.cut(wall, "M0 0H10V10H0Z", "layer-material-Brick")
                            + self.cut(wall, "M10 0H12V10H10Z", "layer-material-Polystyrene")
                            + self.cut(floor, "M0 10H12V12H0Z"))
        self.assertEqual(add_section_outlines(self.path, self.model), 1)
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
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(0, 0, 10, 2).boundary))
        self.assertAlmostEqual(self.lines().intersection(LineString([(0, 0), (10, 0)])).length, 10)
        self.assertEqual(self.lines().intersection(LineString([(1, .5), (9, .5)])).length, 0)

    def test_roof_exclusion_also_respects_inherited_types(self):
        roof = self.product("IfcSlab")
        roof_type = self.product("IfcSlabType", "ROOF")
        ifcopenshell.api.type.assign_type(self.model, related_objects=[roof], relating_type=roof_type)
        self.svg(self.cut(roof, "M0 0H10V2H0Z"))
        self.assertEqual(add_section_outlines(self.path, self.model), 0)

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
                add_section_outlines(self.path, self.model)
                self.assertTrue(self.lines().equals(box(4, 5, 7, 7).boundary))
                # No heavy interface at x=6 between wall and wool.
                self.assertEqual(self.lines().intersection(LineString([(6, 5.1), (6, 6.9)])).length, 0)
                self.svg(''.join(lines))
                self.assertEqual(add_section_outlines(self.path, self.model), 0)
                self.svg(self.cut(wall, "M0 0H2V2H0Z") + ''.join(lines[:-1]))
                add_section_outlines(self.path, self.model)
                self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_rooms_holes_concavity_and_door_gaps_are_preserved(self):
        wall = self.product()
        d = "M0 0H10V10H0Z M2 2H8V8H2Z"
        self.svg(self.cut(wall, d))
        add_section_outlines(self.path, self.model)
        expected = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                           holes=[[(2, 2), (8, 2), (8, 8), (2, 8)]])
        self.assertTrue(self.lines().equals(expected.boundary))
        self.svg(self.cut(wall, "M0 0H10V10H8V2H2V10H0Z"))
        add_section_outlines(self.path, self.model)
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
        add_section_outlines(self.path, self.model, projected_walls=False)
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))

    def test_projected_walls_merge_with_cuts_by_default_and_leave_gaps(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H2V2H0Z")
                 + self.cut(wall, "M2 0H4V2H2Z M6 0H8V2H6Z", view="projection"))
        add_section_outlines(self.path, self.model)
        expected = unary_union([box(0, 0, 4, 2), box(6, 0, 8, 2)]).boundary
        self.assertTrue(self.lines().equals(expected))
        result = self.path.read_text()
        add_section_outlines(self.path, self.model)
        self.assertEqual(self.path.read_text(), result)
        add_section_outlines(self.path, self.model, projected_walls=False)
        self.assertTrue(self.lines().equals(box(0, 0, 2, 2).boundary))
        add_section_outlines(self.path, self.model, categories=("ceilings",))
        self.assertTrue(self.lines().is_empty)

    def test_projected_segment_network_merges_internal_divisions_without_closing_gaps(self):
        wall = self.product()
        # Separate edges, a shared face division, and an incomplete contour.
        segments = ("M0 0H5", "M5 0H10", "M10 0V2", "M10 2H5", "M5 2H0", "M0 2V0",
                    "M5 0V2", "M20 0H22V2")
        self.svg('<g transform="translate(3,4) scale(2)">' + ''.join(
            self.cut(wall, d, view="projection") for d in segments) + '</g>')
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(3, 4, 23, 8).boundary))
        self.assertEqual(self.lines().intersection(LineString([(13, 4.1), (13, 7.9)])).length, 0)

    def test_projected_wall_holes_and_nested_islands_are_preserved(self):
        wall = self.product()
        self.svg(self.cut(wall, "M0 0H10V10H0Z M2 2H8V8H2Z M4 4H6V6H4Z M10 5H12",
                          view="surface"))
        add_section_outlines(self.path, self.model)
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
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(0, 0, 4, 2).boundary))
        add_section_outlines(self.path, self.model, projected_walls=False)
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
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(0, 0, 10, 4).boundary))
        add_section_outlines(self.path, self.model, projected_walls=False)
        expected = unary_union([box(0, 0, 10, 1), box(0, 2, 10, 4)]).boundary
        self.assertTrue(self.lines().equals(expected))

    def test_cut_wall_plate_is_a_wall_assembly_even_when_aggregated_in_a_roof(self):
        plate = self.product("IfcBeam", "USERDEFINED")
        plate.ObjectType = "WALL_PLATE"
        roof = self.product("IfcRoof")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[plate], relating_object=roof)
        self.svg(self.cut(plate, "M0 0H2V2H0Z"))
        add_section_outlines(self.path, self.model, projected_walls=False)
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
                add_section_outlines(self.path, self.model)
                self.assertTrue(self.lines().equals(box(0, 0, 12, 3).boundary))
                result = self.path.read_text()
                add_section_outlines(self.path, self.model)
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
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(0, 0, 10, 3).boundary))
        add_section_outlines(self.path, self.model, projected_walls=False)
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
                add_section_outlines(self.path, self.model)
                bold = self.lines()
                self.assertAlmostEqual(bold.intersection(LineString([(0, 0), (10, 0)])).length, 10)
                self.assertAlmostEqual(bold.intersection(LineString([(0, 3), (10, 3)])).length, 10)
                # Neither the cap/insulation seam nor the occluder contacts get heavy.
                for y in (.5, 1.5, 2):
                    self.assertEqual(bold.intersection(LineString([(1, y), (9, y)])).length, 0)
                add_section_outlines(self.path, self.model, projected_walls=False)
                self.assertTrue(self.lines().is_empty)
        self.svg(fragmented + insulation)
        self.assertEqual(add_section_outlines(self.path, self.model), 0)
        self.svg(fragmented + self.cut(occluder, "M0 .5H10V1.5", view="projection") + insulation)
        self.assertEqual(add_section_outlines(self.path, self.model), 0)
        # A distant enclosing solid must not be mistaken for a wall/room face.
        self.svg(fragmented + self.cut(occluder, "M-20 -20H20V20H-20Z") + insulation)
        self.assertEqual(add_section_outlines(self.path, self.model), 0)

    def test_contact_with_unselected_cut_solids_is_not_air(self):
        wall, footing = self.product(), self.product("IfcFooting")
        self.svg(self.cut(wall, "M0 0H2V2H0Z") + self.cut(footing, "M0 2H2V4H0Z"))
        add_section_outlines(self.path, self.model)
        self.assertLess(self.lines().intersection(LineString([(0, 2), (2, 2)])).length, .001)
        self.assertAlmostEqual(self.lines().length, 6, delta=.01)

    def test_miako_parts_form_one_ceiling_and_do_not_outline_internal_cells(self):
        slab = self.product("IfcSlab", "FLOOR", pset="BBIM_MiakoSlab")
        part = self.product("IfcBuildingElementPart")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[part], relating_object=slab)
        self.svg(self.cut(part, "M0 0H10V2H0Z M1 .5H2V1.5H1Z"))
        add_section_outlines(self.path, self.model, categories=("ceilings",))
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
        add_section_outlines(self.path, self.model)
        self.assertTrue(self.lines().equals(box(0, 0, 3, 4).boundary))
        self.svg(insulation_svg)
        self.assertEqual(add_section_outlines(self.path, self.model), 0)

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
                add_section_outlines(self.path, self.model)
                self.assertTrue(self.lines().equals(box(0, 0, 3, 2).boundary))
                result = self.path.read_text()
                add_section_outlines(self.path, self.model)
                self.assertEqual(self.path.read_text(), result)
        # Aliases on projected geometry must not qualify as cut hosts.
        self.svg(self.cut(primary, "M0 0H2V2H0Z", secondary.GlobalId, view="projection") + wool_svg)
        self.assertEqual(add_section_outlines(self.path, self.model, projected_walls=False), 0)

    def test_scale_transforms_repeatability_and_annotation_order(self):
        wall = self.product()
        content = ('<g transform="translate(2, 3) scale(2)">' + self.cut(wall, "m0 0h2v2h-2z")
                   + '<g class="dimension-overlays"><text>Dimension</text></g></g>')
        self.svg(content, width=100, view_width=200)
        add_section_outlines(self.path, self.model, width_mm=.2)
        self.assertTrue(self.lines().equals(box(2, 3, 6, 7).boundary))
        result = self.path.read_text()
        self.assertLess(result.index('id="section-outlines"'), result.index('class="dimension-overlays"'))
        self.assertIn("stroke-width:0.4", result)
        add_section_outlines(self.path, self.model, width_mm=.2)
        self.assertEqual(self.path.read_text(), result)
        add_section_outlines(self.path, self.model, width_mm=.3)
        self.assertEqual(self.path.read_text().count('id="section-outlines"'), 1)
        self.assertIn("stroke-width:0.6", self.path.read_text())

    def test_no_selected_geometry_leaves_svg_unchanged_and_removes_stale_layer(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0H2V2H0Z", view="projection"))
        self.assertEqual(add_section_outlines(self.path, self.model, projected_walls=False), 0)
        self.assertEqual(self.path.read_text(), original)
        self.svg(self.cut(wall, "M0 0H2V2H0Z"))
        add_section_outlines(self.path, self.model)
        self.assertEqual(add_section_outlines(self.path, self.model, categories=("ceilings",)), 0)
        self.assertNotIn('id="section-outlines"', self.path.read_text())

    def test_open_paths_are_not_closed_with_an_invented_hull(self):
        wall = self.product()
        original = self.svg(self.cut(wall, "M0 0L10 0L10 10"))
        self.assertEqual(add_section_outlines(self.path, self.model), 0)
        self.assertEqual(self.path.read_text(), original)

    def test_bad_configuration_does_not_edit_svg(self):
        original = self.svg("")
        for kwargs in ({"width_mm": 0}, {"width_mm": True}, {"width_mm": float("nan")},
                       {"categories": "walls"}, {"categories": ("roof",)},
                       {"projected_walls": 1}, {"projected_walls": "false"}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                add_section_outlines(self.path, self.model, **kwargs)
            self.assertEqual(self.path.read_text(), original)

    def test_drawing_option_is_opt_in_persisted_and_validated(self):
        from ifc_utils import House
        house = House("Outlines")
        normal = house.add_drawing("Normal", 0, 0, 2, 5)
        outlined = house.add_drawing("Outlined", 0, 0, 2, 5, section_outline_width=.2)
        cut_only = house.add_drawing("Cut only", 0, 0, 2, 5, section_outline_width=.2,
                                     section_outline_projected_walls=False)
        self.assertIsNone(ifcopenshell.util.element.get_pset(normal.element, "EPset_Drawing", "SectionOutlineWidth"))
        self.assertEqual(ifcopenshell.util.element.get_pset(outlined.element, "EPset_Drawing", "SectionOutlineWidth"), .2)
        self.assertTrue(outlined.section_outline_projected_walls)
        self.assertIs(ifcopenshell.util.element.get_pset(
            outlined.element, "EPset_Drawing", "SectionOutlineProjectedWalls"), True)
        self.assertIs(ifcopenshell.util.element.get_pset(
            cut_only.element, "EPset_Drawing", "SectionOutlineProjectedWalls"), False)
        for value in (0, -.1, True, float("inf")):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_width=value)
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                house.add_drawing("Invalid", 0, 0, 2, 5, section_outline_projected_walls=value)

    def test_renderer_adds_outlines_before_export_and_above_model_fills(self):
        from ifc_utils import House
        for view, projected in (("plan", True), ("plan", False), ("elevation", True), ("elevation", False)):
            with self.subTest(view=view, projected=projected):
                house = House("Outlines")
                wall = ifcopenshell.api.root.create_entity(house.model, ifc_class="IfcWall", name="Wall")
                drawing = house.add_drawing("Outlined", 0, 0, 2, 5, view=view,
                                            direction=(1, 0, 0) if view == "elevation" else None,
                                            section_outline_projected_walls=projected,
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
                        self.assertLess(result.index('id="section-outlines"'),
                                        result.index('class="dimension-overlays"'))
                        self.assertAlmostEqual(self.lines().bounds[2], 3 if projected else 2)
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
