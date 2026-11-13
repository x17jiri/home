import unittest

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import numpy as np
from shapely.geometry import Point, Polygon

from ifc_utils import House


def bounds(product):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, product)
    points = np.asarray(shape.geometry.verts).reshape(-1, 3)
    points = points[np.unique(np.asarray(shape.geometry.faces, dtype=int))]
    return points.min(axis=0), points.max(axis=0)


def yz_section(product):
    representation = ifcopenshell.util.representation.resolve_representation(
        ifcopenshell.util.representation.get_representation(product, "Model", "Body", "MODEL_VIEW")
    )
    solid = representation.Items[0]
    points = np.asarray(solid.SweptArea.OuterCurve.Points.CoordList)
    matrix = (ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
              @ ifcopenshell.util.placement.get_axis2placement(solid.Position))
    points = np.column_stack((points, np.zeros(len(points)), np.ones(len(points)))) @ matrix.T
    return Polygon(points[:, 1:3])


class MiakoSpaceTests(unittest.TestCase):
    def slab(self, structure, *, direction=(0, 1)):
        house = House("MIAKO spaces")
        slab = house.storey("Ceiling", elevation=3).miako_slab(
            "Test", start=(0, 0), end=(2, 0), direction=direction,
            structure=structure, top=.21, block_height=.15, topping=.06,
        )
        return house, slab

    def test_beams_are_160_mm_without_automatic_spaces(self):
        for bay, module in (("wide", .615), ("narrow", .490)):
            with self.subTest(bay=bay):
                _, slab = self.slab(["beam", bay, "beam"])
                self.assertEqual(slab.structure, ("beam", bay, "beam"))
                for shell in slab.beam_shells:
                    lo, hi = bounds(shell)
                    self.assertAlmostEqual(hi[1]-lo[1], .16)
                centres = [line[0][1] for line in slab.beam_centerlines]
                self.assertAlmostEqual(centres[1]-centres[0], module)

    def test_explicit_spaces_restore_625_and_500_mm_modules(self):
        for bay, module in (("wide", .625), ("narrow", .500)):
            for sign in (-1, 1):
                with self.subTest(bay=bay, sign=sign):
                    _, plain = self.slab(["beam", bay, "beam"], direction=(0, sign))
                    house, spaced = self.slab(["beam", "space", bay, "space", "beam"], direction=(0, sign))
                    self.assertEqual(len(spaced.components), len(plain.components))
                    self.assertAlmostEqual(spaced.width, plain.width+.01)
                    centres = [line[0][1] for line in spaced.beam_centerlines]
                    self.assertAlmostEqual(abs(centres[1]-centres[0]), module)
                    self.assertEqual(ifcopenshell.util.element.get_pset(spaced, "BBIM_MiakoSlab", "Structure"),
                                     f"beam,space,{bay},space,beam")
                    cover = yz_section(spaced.topping_element)
                    for block in spaced.blocks:
                        self.assertLess(cover.intersection(yz_section(block)).area, 1e-9)
                    # The 35 mm block lip reaches 30 mm onto the beam across a 5 mm space.
                    self.assertTrue(cover.contains(Point(sign*.129, 3.10)))
                    self.assertFalse(cover.contains(Point(sign*.131, 3.10)))
                    for component in spaced.components:
                        bounds(component)  # All resulting solids remain meshable.

    def test_space_between_beams_is_empty_below_continuous_topping(self):
        _, slab = self.slab(["beam", "space", "beam"])
        first_lo, first_hi = bounds(slab.beam_shells[0])
        second_lo, second_hi = bounds(slab.beam_shells[1])
        self.assertAlmostEqual(second_lo[1]-first_hi[1], .005)
        self.assertAlmostEqual(slab.width, .325)
        self.assertEqual(len(slab.beams), 2)
        self.assertFalse(slab.blocks)
        cover = yz_section(slab.topping_element)
        self.assertFalse(cover.covers(Point(.1625, 3.10)))
        self.assertTrue(cover.contains(Point(.1625, 3.18)))

    def test_spaces_work_with_axis_and_do_not_replace_a_beam_between_blocks(self):
        house, slab = self.slab(["space", "beam", "space", "axis", "narrow", "space", "beam", "space"])
        self.assertAlmostEqual(slab.width_before_axis, .17)
        self.assertAlmostEqual(slab.width_after_axis, .5)
        self.assertAlmostEqual(slab.width, .67)
        np.testing.assert_allclose([line[0][1] for line in slab.beam_centerlines], (-.085, .415))
        for component in slab.components:
            bounds(component)
        reopened = ifcopenshell.file.from_string(house.model.to_string())
        properties = ifcopenshell.util.element.get_pset(reopened.by_guid(slab.GlobalId), "BBIM_MiakoSlab")
        self.assertEqual(properties["Structure"], "space,beam,space,axis,narrow,space,beam,space")
        self.assertAlmostEqual(properties["OverallWidth"], .67)
        with self.assertRaisesRegex(ValueError, "separated by a beam"):
            self.slab(["beam", "wide", "space", "narrow", "beam"])
        with self.assertRaisesRegex(ValueError, "at least one beam"):
            self.slab(["space"])

    def test_spaces_rotate_with_the_span_and_mirror_with_the_model(self):
        for sign in (-1, 1):
            house = House("Rotated spaces", mirror_x=True)
            slab = house.storey("Ceiling", elevation=0).miako_slab(
                "Rotated", start=(2, 1), end=(2, 3), direction=(sign, 0),
                structure=["beam", "space", "beam"], top=.21, block_height=.15, topping=.06,
            )
            centres = [line[0][0] for line in slab.beam_centerlines]
            self.assertAlmostEqual(sign*(centres[1]-centres[0]), .165)
            first = bounds(slab.beam_shells[0]); second = bounds(slab.beam_shells[1])
            gap = second[0][0]-first[1][0] if sign == 1 else first[0][0]-second[1][0]
            self.assertAlmostEqual(gap, .005)
            exported = house._export_model()
            for shell in slab.beam_shells:
                lo, hi = bounds(shell)
                mirrored_lo, mirrored_hi = bounds(exported.by_guid(shell.GlobalId))
                np.testing.assert_allclose(mirrored_lo, (-hi[0], lo[1], lo[2]), atol=1e-8)
                np.testing.assert_allclose(mirrored_hi, (-lo[0], hi[1], hi[2]), atol=1e-8)


if __name__ == "__main__":
    unittest.main()
