"""The house can use stepped foundations and per-wall overrides together."""

import ast
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.selector
import numpy as np

from ifc_utils import Drawing, House


class HouseFoundationProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FOUNDATION_HEIGHT_MAP" for t in node.targets):
                node.value = ast.parse("FoundationHeightMap(((0, FOUNDATION_FOOTER_BOTTOM_Z), "
                    "(3, FOUNDATION_FOOTER_BOTTOM_Z+.25), (6, FOUNDATION_FOOTER_BOTTOM_Z+.5)))").body[0].value
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "FoundationSpec"
                    and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "wall_4_g"):
                node.keywords.extend([ast.keyword("wall_thickness", ast.Constant(.3)),
                                      ast.keyword("footer_width", ast.Constant(.9))])
        module = ModuleType("_house_foundation_profile_test")
        module.__file__ = str(source)
        with patch.dict(sys.modules, {module.__name__: module}), \
             patch.object(sys, "argv", [str(source), "found", "bb", "pohled_zapad"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            exec(compile(ast.fix_missing_locations(tree), str(source), "exec"), module.__dict__)
        cls.v = module.__dict__

    @staticmethod
    def vertices(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        return np.asarray(shape.geometry.verts).reshape(-1, 3)[np.unique(shape.geometry.faces)]

    def test_all_source_walls_have_foundations_and_each_footer_follows_its_y_band(self):
        v = self.v
        expected = {spec.wall.GlobalId for spec in v["foundation_specs"]}
        self.assertEqual(len(expected), 9)
        actual = set()
        for footer in v["foundation_footers"]:
            data = ifcopenshell.util.element.get_pset(footer, "BBIM_StripFooting")
            actual.add(data["SourceWall"])
            p = self.vertices(footer)
            self.assertGreaterEqual(p[:, 1].min(), data["YMin"]-1e-8)
            self.assertLessEqual(p[:, 1].max(), data["YMax"]+1e-8)
            self.assertAlmostEqual(p[:, 2].min(), data["MinimumBottomZ"])
            self.assertAlmostEqual(p[:, 2].max(), data["BottomZ"]+data["Height"])
            y = (p[:, 1].min()+p[:, 1].max())/2
            expected_bottom = v["FOUNDATION_FOOTER_BOTTOM_Z"] + (.5 if y >= 6 else .25 if y >= 3 else 0)
            self.assertAlmostEqual(data["BottomZ"], expected_bottom)
        self.assertEqual(actual, expected)

    def test_overridden_wall_thickness_and_footer_width_reach_every_step(self):
        v = self.v
        walls = [w for w in v["foundation_walls"] if w.source_wall == v["wall_4_g"]]
        self.assertEqual(len(walls), 3)
        for wall in walls:
            p = self.vertices(wall)
            self.assertAlmostEqual(np.ptp(p[:, 0]), .3)
            self.assertAlmostEqual(p[:, 2].max(), -v["BASEMENT_CEILING_SPACE"])
        for footer in v["foundation_footers"]:
            data = ifcopenshell.util.element.get_pset(footer, "BBIM_StripFooting")
            if data["SourceWall"] == v["wall_4_g"].GlobalId:
                p = self.vertices(footer)
                self.assertAlmostEqual(np.ptp(p[:, 0]), .9)
                self.assertAlmostEqual((p[:, 0].max()+p[:, 0].min())/2, v["HOUSE_WIDTH"]-.15)

    def test_foundation_camera_includes_all_footer_levels_and_end_facades_stay_continuous(self):
        v = self.v
        drawing, = [d for d in v["house"]._drawings if d.name == "Foundation"]
        highest = max(ifcopenshell.util.element.get_pset(f, "BBIM_StripFooting", "BottomZ")
                      +ifcopenshell.util.element.get_pset(f, "BBIM_StripFooting", "Height")/2
                      for f in v["foundation_footers"])
        self.assertAlmostEqual(drawing.z, highest)
        rule = ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include")
        included = ifcopenshell.util.selector.filter_elements(v["house"].model, rule)
        self.assertTrue(set(v["foundation_footers"]).issubset(included))
        extension = v["EXTERIOR_XPS_INSULATION_THICKNESS"]+v["FACADE_THICKNESS"]-.001
        for side in ("east", "west"):
            panel, = v["perimeter_facades"][side]
            p = self.vertices(panel)
            np.testing.assert_allclose((p[:, 1].min(), p[:, 1].max()),
                                       (-extension, v["HOUSE_DEPTH"]+extension), atol=1e-8)


if __name__ == "__main__":
    unittest.main()
