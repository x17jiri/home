"""Geometry and house placement checks for path-based railings."""

from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import numpy as np

from ifc_utils import Drawing, House, RailingPath


def mesh(element, representation=None):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, element, representation)
    return (np.asarray(shape.geometry.verts).reshape(-1, 3).copy(),
            np.asarray(shape.geometry.faces).reshape(-1, 3).copy())


class RailingTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Railing tests")
        self.storey = self.house.storey("Upper", elevation=3)

    def test_drawings_use_panel_without_posts_and_keep_full_model_body(self):
        railing = self.storey.railing("Plan", path=[(2, 1, 3), (2, 3, 4), (3, 3, 4)])
        plan = ifcopenshell.util.representation.get_representation(railing, "Plan", "Body", "PLAN_VIEW")
        body = ifcopenshell.util.representation.get_representation(railing, "Model", "Body", "MODEL_VIEW")
        self.assertEqual(len(plan.Items), 2)
        self.assertGreater(len(body.Items), 2)
        np.testing.assert_allclose(plan.Items[0].Coordinates.CoordList,
                                   body.Items[0].Coordinates.CoordList)
        plan_vertices, _ = mesh(railing, plan)
        model_vertices, _ = mesh(railing)
        self.assertAlmostEqual(plan_vertices[:, 2].min(), 3.05)
        self.assertAlmostEqual(model_vertices[:, 2].min(), 3)
        panel = plan.Items[1]
        np.testing.assert_allclose(np.array(panel.Coordinates.CoordList)[:4, 2],
                                   (3.05, 3.05, 3.91, 3.91))
        for target in ("ELEVATION_VIEW", "SECTION_VIEW"):
            elevation = ifcopenshell.util.representation.get_representation(railing, "Model", "Body", target)
            self.assertEqual(elevation.Items, plan.Items)
        _, triangles = mesh(railing, plan)
        edges = Counter(tuple(sorted(edge)) for a, b, c in triangles
                        for edge in ((a, b), (b, c), (c, a)))
        self.assertEqual(set(edges.values()), {2})

        with patch.object(self.house, "mirror_x", True):
            exported = self.house._export_model().by_guid(railing.GlobalId)
            mirrored_plan = ifcopenshell.util.representation.get_representation(exported, "Plan", "Body", "PLAN_VIEW")
            mirrored_vertices, _ = mesh(exported, mirrored_plan)
        self.assertEqual({tuple(p) for p in np.round(mirrored_vertices, 7)},
                         {tuple(p) for p in np.round(plan_vertices*(-1, 1, 1), 7)})

    def test_rotated_stair_path_and_posts_rest_on_treads(self):
        with redirect_stdout(StringIO()):
            stair = self.storey.stair((2, 1), (2, 3.7), width=1, height=1.8,
                                      start_height=.2, risers=10, construction="timber")
        path = stair.railing_path("left", inset=.03)
        np.testing.assert_allclose(path, ((1.53, 1, 3.38), (1.53, 3.7, 5)))
        self.assertAlmostEqual(stair.railing_path("right")[0][0], 2.47)
        self.assertAlmostEqual(path.support_height((1.53, 1.59, 0)), 3.56)
        railing = self.storey.railing("Stair", path=path, post_spacing=.81)
        for x, y, z in (*railing.post_positions, *railing.baluster_positions):
            step = min(10, int(np.floor((y-1)/.3+1e-9))+1)
            self.assertAlmostEqual(z, 3.2+step*.18)
        # The handrail covers the endpoint post, continuing 30 mm past the nosing.
        self.assertAlmostEqual(mesh(railing)[0][:, 2].max(), 6+.03*(1.62/2.7))

    def test_polyline_has_one_corner_post_and_watertight_meshes(self):
        path = [(0, 0, 3), (1.8, 0, 4), (1.8, 1, 4)]
        railing = self.storey.railing("Corner", path=path, post_spacing=.9)
        self.assertEqual(railing.is_a(), "IfcRailing")
        self.assertEqual(railing.PredefinedType, "GUARDRAIL")
        self.assertEqual(railing.post_positions.count((1.8, 0, 4)), 1)
        self.assertEqual(len(railing.post_positions), 5)
        self.assertIs(ifcopenshell.util.element.get_container(railing).file, self.house.model)
        self.assertEqual(ifcopenshell.util.element.get_container(railing), self.storey.element)
        pset = ifcopenshell.util.element.get_pset(railing, "BBIM_Railing")
        self.assertEqual(pset["Height"], 1)
        self.assertEqual(pset["Infill"], "vertical")
        self.assertEqual(ifcopenshell.util.element.get_material(railing).Name, "Wood")
        vertices, triangles = mesh(railing)
        self.assertTrue(np.isfinite(vertices).all())
        # Every component is a closed mesh, including the mitered handrail.
        edges = Counter(tuple(sorted(edge)) for a, b, c in triangles
                        for edge in ((a, b), (b, c), (c, a)))
        self.assertEqual(set(edges.values()), {2})
        self.assertAlmostEqual(vertices[:, 2].max(), 5)

    def test_closed_path_no_infill_and_duplicate_points(self):
        railing = self.storey.railing("Closed", infill="none", post_spacing=2,
            path=[(0, 0, 3), (1, 0, 3), (1, 0, 3), (1, 1, 3), (0, 1, 3), (0, 0, 3)])
        self.assertEqual(len(railing.post_positions), 4)
        self.assertEqual(railing.baluster_positions, ())
        _, triangles = mesh(railing)
        edges = Counter(tuple(sorted(edge)) for a, b, c in triangles
                        for edge in ((a, b), (b, c), (c, a)))
        self.assertEqual(set(edges.values()), {2})

    def test_invalid_input_does_not_create_partial_railing(self):
        cases = [dict(path=[]), dict(path=[(0, 0, 0), (0, 0, 1)]),
                 dict(path=[(0, 0, 0), (1, 0, 0), (0, 0, 0)]),
                 dict(path=[(0, 0, 0), (float("nan"), 0, 0)]),
                 dict(height=0), dict(post_spacing=-1), dict(infill="glass"),
                 dict(handrail_size=(.06, 1.1)), dict(post_size=(0, .06)),
                 dict(path=RailingPath(((0, 0, 0), (1, 0, 0)), lambda p: 10))]
        for changes in cases:
            with self.subTest(changes=changes):
                options = dict(path=[(0, 0, 0), (1, 0, 0)]) | changes
                with self.assertRaises((ValueError, TypeError)):
                    self.storey.railing("Invalid", **options)
                self.assertEqual(self.house.model.by_type("IfcRailing"), [])

    def test_export_mirrors_railing_once_and_keeps_live_path(self):
        railing = self.storey.railing("Mirror", path=[(2, 1, 3), (3, 1, 4), (3, 2, 4)])
        original, _ = mesh(railing)
        with patch.object(self.house, "mirror_x", True):
            mirrored, _ = mesh(self.house._export_model().by_guid(railing.GlobalId))
        self.assertEqual({tuple(p) for p in np.round(mirrored, 7)},
                         {tuple(p) for p in np.round(original*(-1, 1, 1), 7)})
        np.testing.assert_allclose(mesh(railing)[0], original)
        self.assertEqual(railing.path[0], (2, 1, 3))


class HouseRailingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("house_ifc.py")
        with patch.object(sys, "argv", [str(source), "ground", "upper"]), \
             patch.object(House, "write"), patch.object(Drawing, "render"), redirect_stdout(StringIO()):
            cls.v = runpy.run_path(str(source))

    def test_all_flights_and_landing_have_guard_with_access_clear(self):
        v = self.v
        self.assertEqual(len(v["house_railings"]), 4)
        for name, stair_name, side in (("main_stair_railing", "main_stairs", "left"),
                                      ("gallery_stair_railing", "gallery_stairs", "left"),
                                      ("entrance_railing", "entrance_stairs", "right")):
            railing, stair = v[name], v[stair_name]
            np.testing.assert_allclose(railing.path[:2], stair.railing_path(side))
            self.assertGreater(len(mesh(railing)[1]), 0)
        exterior = v["entrance_railing"]
        self.assertEqual(len(exterior.path), 4)
        # Outer landing edge continues the flight, then returns toward the facade.
        self.assertAlmostEqual(exterior.path[1][0], exterior.path[2][0])
        self.assertAlmostEqual(exterior.path[2][1], exterior.path[3][1])
        self.assertGreater(exterior.path[3][0], exterior.path[2][0])
        # No guard crosses the approach at the first tread.
        self.assertGreater(exterior.path[0][1], max(p[1] for p in exterior.path[1:]))

    def test_gallery_gap_clears_chimney_and_stair_opening(self):
        v = self.v
        before, after = v["gallery_railings"]
        before_max_x = mesh(before)[0][:, 0].max()
        after_min_x = mesh(after)[0][:, 0].min()
        self.assertLessEqual(before_max_x, v["CHIMNEY_X_START"]-v["GALLERY_RAILING_CHIMNEY_CLEARANCE"]+1e-8)
        self.assertGreaterEqual(after_min_x, v["CHIMNEY_X_END"]+v["GALLERY_RAILING_CHIMNEY_CLEARANCE"]-1e-8)
        # End at the open stair edge rather than crossing the landing entrance.
        self.assertLess(after.path[-2][0], v["wall3_start"])
        self.assertAlmostEqual(after.path[-1][2], v["upper"].elevation+v["UPPER_FLOOR_THICKNESS"])

    def test_indoor_railings_are_included_in_upper_plan(self):
        v = self.v
        upper = next(d for d in v["house"]._drawings if d.name == "Drawing 2")
        query = ifcopenshell.util.element.get_pset(upper.element, "EPset_Drawing", "Include")
        included = ifcopenshell.util.selector.filter_elements(v["house"].model, query)
        self.assertTrue(set((v["main_stair_railing"], *v["gallery_railings"])).issubset(included))
        self.assertNotIn(v["entrance_railing"], included)


if __name__ == "__main__":
    unittest.main()
