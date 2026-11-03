"""Knee-wall boundary semantics and retained offsets to the roof and finishes."""

import ast
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np

from ifc_utils import Drawing, DrawingSheet, House


def load_house(shift=0):
    source = Path(__file__).with_name('house_ifc.py')
    tree = ast.parse(source.read_text())
    if shift:
        node, = [n for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'LOWER_NADEZDIVKA_X' for t in n.targets)]
        node.value = ast.BinOp(node.value, ast.Add(), ast.Constant(shift))
    module = ModuleType('_house_knee_wall_test')
    module.__file__ = str(source)
    with patch.dict(sys.modules, {module.__name__: module}), \
         patch.object(sys, 'argv', [str(source), 'upper']), patch.object(House, 'write'), \
         patch.object(Drawing, 'render'), patch.object(DrawingSheet, 'render'), redirect_stdout(StringIO()):
        exec(compile(ast.fix_missing_locations(tree), str(source), 'exec'), module.__dict__)
    return module.__dict__


def bounds(element):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, element)
    pts = np.array(shape.geometry.verts).reshape(-1, 3)[np.unique(shape.geometry.faces)]
    return pts.min(axis=0), pts.max(axis=0)


class KneeWallBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load_house()
        cls.shift = .10
        cls.moved = load_house(cls.shift)

    def test_boundary_is_outer_face_of_closure_masonry(self):
        v = self.v
        lower = v['LOWER_NADEZDIVKA_X']
        self.assertAlmostEqual(bounds(v['west_closure_wall'])[1][0], lower)
        np.testing.assert_allclose(v['west_roof_closure_x_ranges']['Wall'],
                                   (lower-v['WEST_CLOSURE_WALL_THICKNESS'], lower))
        self.assertAlmostEqual(bounds(v['west_roof_closure']['Siding'])[0][0], lower+v['WEST_CLOSURE_AIR_GAP'])

    def test_upper_knee_walls_and_their_ring_beams_end_at_boundary(self):
        v = self.v
        for wall in (v['wall_front1_u'], v['wall_back1_u']):
            self.assertAlmostEqual(bounds(wall)[1][0], v['LOWER_NADEZDIVKA_X'])
            beams = [b for b in v['upper_ring_beams'] if b.source_wall == wall]
            self.assertTrue(beams)
            self.assertAlmostEqual(max(bounds(b)[1][0] for b in beams), v['LOWER_NADEZDIVKA_X'])
            for beam in beams:
                self.assertTrue(beam.reinforcement)
                for bar in beam.reinforcement:
                    self.assertLessEqual(bounds(bar)[1][0], v['LOWER_NADEZDIVKA_X']+1e-7)

    def test_roof_and_finish_offsets_preserve_the_architectural_boundary(self):
        v = self.v
        lower = v['LOWER_NADEZDIVKA_X']
        self.assertAlmostEqual(v['FACADE_MATERIAL_SPLIT_X'], lower+.105)
        for beam in (v['street_purlins'][1], v['garden_purlins'][1], v['beam3'], v['beam4_b']):
            self.assertAlmostEqual(max(beam.start[0], beam.end[0]), lower+.105)
        self.assertAlmostEqual(v['transverse_purlin'].start[0], lower+.280)
        self.assertAlmostEqual(v['roof_under_rafter_x_ranges'][-1][1], lower-.095)
        self.assertAlmostEqual(v['roof_over_rafter_x_ranges'][-1][1], lower+.155)
        self.assertTrue(all(abs(point[0]-(lower+.155)) < 1e-8 for point in v['transverse_roof'].cuts[0]))
        self.assertAlmostEqual(v['high_rafters'][-1], lower+.005)
        self.assertAlmostEqual(bounds(v['street_facade'][0])[1][0], lower+.105)

    def test_insulation_extents_remain_at_roof_boundary(self):
        v = self.v
        drawing, = [d for d in v['house']._drawings if d.name == 'Drawing 2']
        records = [record for relation in drawing.group.IsGroupedBy for element in relation.RelatedObjects
                   if (record := ifcopenshell.util.element.get_pset(element, 'BBIM_WallInsulation'))
                   and 'Segments' in record]
        for host in (v['wall_front1_u'], v['wall_front_g']):
            matches = [r for r in records if r.get('HostWall') == host.GlobalId]
            self.assertTrue(matches)
            spans = [span for r in matches for span in json.loads(r['Segments'])]
            coordinate = max(s[1] for s in spans) if host == v['wall_front1_u'] else min(s[0] for s in spans)
            self.assertAlmostEqual(coordinate, v['LOWER_NADEZDIVKA_X']+.155)

    def test_parameter_shift_still_moves_dependent_elements(self):
        a, b, shift = self.v, self.moved, self.shift
        for key in ('LOWER_NADEZDIVKA_X', 'WEST_CLOSURE_INNER_X', 'FACADE_MATERIAL_SPLIT_X'):
            self.assertAlmostEqual(b[key]-a[key], shift)
        for key in ('wall_front1_u', 'wall_back1_u', 'beam3', 'beam4_b', 'west_closure_wall', 'west_closure_window'):
            self.assertAlmostEqual(bounds(b[key])[1][0]-bounds(a[key])[1][0], shift)
        self.assertAlmostEqual(b['transverse_purlin'].start[0]-a['transverse_purlin'].start[0], shift)
        for key in ('roof_under_rafter_x_ranges', 'roof_over_rafter_x_ranges'):
            self.assertAlmostEqual(b[key][-1][1]-a[key][-1][1], shift)
        for side in ('street', 'garden'):
            self.assertAlmostEqual(bounds(b[f'{side}_facade'][0])[1][0]-bounds(a[f'{side}_facade'][0])[1][0], shift)
        np.testing.assert_allclose(b['transverse_wall_plate'].start, a['transverse_wall_plate'].start)


if __name__ == '__main__':
    unittest.main()
