"""Foundation source coverage, per-wall dimensions and clipped Y steps."""

import json
import unittest

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.shape
import numpy as np

from foundations import FoundationHeightMap, FoundationSpec, build_foundations
from ifc_utils import House


class FoundationProfileTests(unittest.TestCase):
    def fixture(self):
        house = House("Foundation steps")
        ground = house.storey("Ground", elevation=0)
        basement = house.storey("Basement", elevation=-2.35)
        footers = house.storey("Footers", elevation=-3)
        source_type = house.wall_type("Source", layers=[("Brick", .175), "axis"])
        foundation_type = house.wall_type("Foundation", layers=[("ztracene bedneni", .24), "axis"])
        horizontal = ground.wall((0, 0), (4, 0), wall_type=source_type, height=3)
        vertical = ground.wall((4, 0), (4, 6), wall_type=source_type, height=3)
        reverse = ground.wall((6, 6), (6, 0), wall_type=source_type, height=3)
        options = dict(wall_storey=basement, footer_storey=footers,
                       wall_type=foundation_type, wall_top_z=-.25,
                       default_wall_thickness=.24, default_footer_width=.7,
                       default_footer_height=.5, slab_thickness=.15)
        return house, (horizontal, vertical, reverse), options

    @staticmethod
    def vertices(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        points = np.asarray(shape.geometry.verts).reshape(-1, 3)
        return points[np.unique(shape.geometry.faces)]

    @staticmethod
    def volume(element):
        shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), element)
        return ifcopenshell.util.shape.get_volume(shape.geometry)

    def test_uniform_profile_has_one_foundation_and_footer_for_each_explicit_source(self):
        house, sources, options = self.fixture()
        walls, footers = build_foundations([FoundationSpec(w) for w in sources],
            height_map=FoundationHeightMap(((0, -3),)), **options)
        self.assertEqual(len(walls), 3)
        self.assertEqual(len(footers), 3)
        self.assertEqual({w.source_wall for w in walls}, set(sources))
        for source, wall, footer in zip(sources, walls, footers):
            self.assertEqual((wall.start, wall.end), (source.start, source.end))
            points = self.vertices(wall)
            self.assertAlmostEqual(points[:, 2].min(), -2.35)
            self.assertAlmostEqual(points[:, 2].max(), -.25)
            points = self.vertices(footer)
            self.assertAlmostEqual(points[:, 2].min(), -3)
            self.assertAlmostEqual(points[:, 2].max(), -2.5)
            self.assertAlmostEqual(self.volume(footer), (source.length+.46)*.7*.5)
            self.assertEqual(ifcopenshell.util.element.get_pset(footer, "BBIM_StripFooting", "SourceWall"), source.GlobalId)
            self.assertEqual(ifcopenshell.util.element.get_container(wall), options["wall_storey"].element)
        # The footing follows the foundation wall centre even though the
        # supported ground wall is thinner (175 rather than 240 mm).
        p = self.vertices(footers[0])
        self.assertAlmostEqual((p[:, 1].min()+p[:, 1].max())/2, .24/2)

    def test_per_wall_dimensions_override_defaults_and_change_the_correct_geometry(self):
        _, sources, options = self.fixture()
        walls, footers = build_foundations(
            [FoundationSpec(sources[0], wall_thickness=.3, footer_width=.8, footer_height=.6),
             FoundationSpec(sources[1])], height_map=FoundationHeightMap(((0, -3),)), **options)
        self.assertAlmostEqual(walls[0].thickness, .3)
        self.assertAlmostEqual(walls[1].thickness, .24)
        points = self.vertices(footers[0])
        self.assertAlmostEqual(np.ptp(points[:, 1]), .8)
        self.assertAlmostEqual(np.ptp(points[:, 2]), .6)
        self.assertAlmostEqual((points[:, 1].min()+points[:, 1].max())/2, .15)
        self.assertAlmostEqual(self.vertices(walls[0])[:, 2].min(), -3+.6+.15)
        self.assertAlmostEqual(self.vertices(walls[1])[:, 2].min(), -3+.5+.15)

    def test_y_profile_splits_reversed_and_forward_walls_without_end_extensions_at_steps(self):
        _, sources, options = self.fixture()
        profile = FoundationHeightMap(((0, -3), (3, -2.75)))
        walls, footers = build_foundations([FoundationSpec(w) for w in sources[1:]], height_map=profile, **options)
        self.assertEqual(len(walls), 4)
        self.assertEqual(len(footers), 4)
        for wall in walls:
            points = self.vertices(wall)
            low = points[:, 2].min()
            expected_y = (0, 3) if abs(low-(-2.35)) < 1e-8 else (3, 6)
            np.testing.assert_allclose((points[:, 1].min(), points[:, 1].max()), expected_y)
            self.assertAlmostEqual(points[:, 2].max(), -.25)
        for footer in footers:
            points = self.vertices(footer)
            low = ifcopenshell.util.element.get_pset(footer, "BBIM_StripFooting", "BottomZ")
            expected_y = (-.23, 3) if abs(low-(-3)) < 1e-8 else (3, 6.23)
            np.testing.assert_allclose((points[:, 1].min(), points[:, 1].max()), expected_y)
        expected_volume = sum((s.length+.46)*.7*.5 for s in sources[1:])
        self.assertAlmostEqual(sum(self.volume(f) for f in footers), expected_volume+2*.7*.25**2/2)

    def test_a_step_crossing_horizontal_wall_thickness_clips_the_full_footprints(self):
        _, sources, options = self.fixture()
        walls, footers = build_foundations([FoundationSpec(sources[0])],
            height_map=FoundationHeightMap(((0, -3), (.1, -2.75))), **options)
        self.assertEqual((len(walls), len(footers)), (2, 2))
        for elements, expected in ((walls, ((0, .1), (.1, .24))),
                                   (footers, ((-.23, .1), (.1, .47)))):
            for element, bounds in zip(elements, expected):
                p = self.vertices(element)
                np.testing.assert_allclose((p[:, 1].min(), p[:, 1].max()), bounds, atol=1e-8)
        self.assertAlmostEqual(sum(self.volume(f) for f in footers), (4+.46)*(.7*.5+.25**2/2))

    def test_bottom_profile_has_exact_45_degree_rises_falls_and_combined_ramps(self):
        cases = (
            (((0, -3), (3.3, -2.6)), ((0, -3), (3.3, -3), (3.7, -2.6), (6, -2.6))),
            (((0, -2.6), (3.3, -3)), ((0, -2.6), (2.9, -2.6), (3.3, -3), (6, -3))),
            (((0, -3), (1, -2.5), (1.2, -2)), ((0, -3), (1, -3), (2, -2), (6, -2))),
            (((0, -3), (1, -2), (2, -3)), ((0, -3), (1, -3), (1.5, -2.5), (2, -3), (6, -3))),
        )
        for steps, expected in cases:
            with self.subTest(steps=steps):
                profile = FoundationHeightMap(steps).bottom_profile(0, 6)
                np.testing.assert_allclose(profile, expected)
                for (y0, z0), (y1, z1) in zip(profile, profile[1:]):
                    self.assertTrue(abs(z1-z0) < 1e-8 or abs(abs(z1-z0)-(y1-y0)) < 1e-8)

    def test_top_steps_immediately_while_native_underside_rises_over_the_same_distance(self):
        _, sources, options = self.fixture()
        profile = FoundationHeightMap(((0, -3), (3.3, -2.6)))
        _, footers = build_foundations([FoundationSpec(sources[1])], height_map=profile, **options)
        low, high = footers
        a, b = self.vertices(low), self.vertices(high)
        self.assertAlmostEqual(a[:, 2].max(), -2.5)
        self.assertAlmostEqual(b[:, 2].max(), -2.1)
        self.assertAlmostEqual(a[:, 1].max(), 3.3)
        self.assertAlmostEqual(b[:, 1].min(), 3.3)
        for y, z in ((3.3, -3), (3.7, -2.6), (6.23, -2.6)):
            self.assertAlmostEqual(b[np.isclose(b[:, 1], y), 2].min(), z)
        data = ifcopenshell.util.element.get_pset(high, "BBIM_StripFooting")
        self.assertAlmostEqual(data["MinimumBottomZ"], -3)
        self.assertAlmostEqual(data["BottomZ"], -2.6)
        np.testing.assert_allclose(json.loads(data["BottomProfile"]), ((3.3, -3), (3.7, -2.6), (6.23, -2.6)))
        self.assertAlmostEqual(self.volume(high), .7*((6.23-3.3)*.5+.4**2/2))

    def test_sloped_bottom_with_rotated_footprint_exports_and_mirrors_once(self):
        house, _, options = self.fixture()
        ground = house._storeys[0]
        diagonal = ground.wall((0, 0), (4, 4), thickness=.2, height=3)
        _, footers = build_foundations([FoundationSpec(diagonal)],
            height_map=FoundationHeightMap(((0, -3), (2, -2.6))), **options)
        house.mirror_x = True
        exported = house._export_model()
        for footer in footers:
            with self.subTest(footer=footer.Name):
                original = self.vertices(footer)
                mirrored = self.vertices(exported.by_guid(footer.GlobalId))
                self.assertEqual({tuple(p) for p in np.round(mirrored, 6)},
                                 {tuple(p) for p in np.round(original*(-1, 1, 1), 6)})

    def test_equal_levels_merge_and_invalid_configuration_creates_no_products(self):
        house, sources, options = self.fixture()
        self.assertEqual(FoundationHeightMap(((0, -3), (2, -3))).steps, ((0.0, -3.0),))
        for steps in ((), ((1, -3), (0, -2)), ((0, -3), (0, -2)), ((0, float("nan")),)):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                FoundationHeightMap(steps)
        count = len(house.model.by_type("IfcElement"))
        for specs, profile in (([FoundationSpec(sources[0], footer_width=.1)], ((0, -3),)),
                               ([FoundationSpec(sources[0]), FoundationSpec(sources[0])], ((0, -3),)),
                               ([FoundationSpec(sources[0])], ((0, 0),))):
            with self.subTest(specs=specs), self.assertRaises(ValueError):
                build_foundations(specs, height_map=FoundationHeightMap(profile), **options)
            self.assertEqual(len(house.model.by_type("IfcElement")), count)


if __name__ == "__main__":
    unittest.main()
