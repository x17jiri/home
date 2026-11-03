"""Transverse MIAKO ribs: local coordinates, concrete continuity and type reuse."""

import json
import unittest
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import House, MiakoStiffeningRib


def shape(element):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    return ifcopenshell.geom.create_shape(settings, element)


def vertices(element):
    result = shape(element)
    return np.asarray(result.geometry.verts).reshape(-1, 3).copy()


def volume(element):
    result = shape(element)
    return ifcopenshell.util.shape.get_volume(result.geometry)


class MiakoRibTests(unittest.TestCase):
    def make_slab(self, *, start=(2, 3), end=(5, 3), direction=(0, 1), structure=None):
        house = House("MIAKO rib test")
        storey = house.storey("Upper", elevation=3)
        slab = storey.miako_slab("Slab", start=start, end=end, direction=direction,
            top=.2, concrete_color="#bfc3c5", block_start_offset=.125, block_end_offset=.125,
            structure=structure or ["beam", "wide", "beam", "narrow", "beam"])
        return house, storey, slab

    def test_lowers_only_inserts_and_joins_concrete_to_existing_cover(self):
        house, storey, slab = self.make_slab()
        old_cover = volume(slab.topping_element)
        old_blocks = sum(volume(b) for b in slab.blocks)
        unchanged = {b.id(): vertices(b) for b in (*slab.beams, *slab.beam_shells, *slab.reinforcements)}
        # Both strips align with insert joints, so two whole inserts are lowered.
        result = slab.add_stiffening_rib(at=.75, width=.25)
        self.assertIs(result, slab)
        self.assertEqual(slab.stiffening_ribs, (MiakoStiffeningRib(.75, .25, .08),))
        changed = [b for b in slab.blocks if b.HasOpenings]
        self.assertEqual(len(changed), 2)
        for block in changed:
            self.assertAlmostEqual(vertices(block)[:, 2].max(), storey.elevation+slab.bottom+.08)
        expected = .25*(.19-.08)*(.455+.07+.33+.07)
        self.assertAlmostEqual(volume(slab.topping_element)-old_cover, expected)
        self.assertAlmostEqual(old_blocks-sum(volume(b) for b in slab.blocks), expected)
        for element in (*slab.beams, *slab.beam_shells, *slab.reinforcements):
            np.testing.assert_allclose(vertices(element), unchanged[element.id()])
        self.assertEqual(len(slab.components), len(ifcopenshell.util.element.get_parts(slab)))
        self.assertEqual(ifcopenshell.util.element.get_material(slab.topping_element).Name, "Concrete topping")
        self.assertTrue(ifcopenshell.util.element.get_styles(slab.topping_element))
        # Rib/cover union is one continuous solid rather than overlapping bodies.
        body = ifcopenshell.util.representation.get_representation(slab.topping_element, "Model", "Body", "MODEL_VIEW")
        self.assertEqual(len(body.Items), 1)
        self.assertEqual(body.Items[0].Operator, "UNION")

    def test_partial_blocks_and_cached_types_in_other_slab_are_not_changed(self):
        house, storey, slab = self.make_slab()
        neighbour = storey.miako_slab("Neighbour", start=(2, 6), end=(5, 6), top=.2,
            direction=(0, 1), block_start_offset=.125, block_end_offset=.125,
            structure=["beam", "wide", "beam", "narrow", "beam"])
        original = {b.id(): vertices(b) for b in neighbour.blocks}
        shared_type = ifcopenshell.util.element.get_type(slab.blocks[2])
        self.assertEqual(shared_type, ifcopenshell.util.element.get_type(neighbour.blocks[2]))
        before = sum(volume(b) for b in slab.blocks)+volume(slab.topping_element)
        slab.add_stiffening_rib(at=1.375, width=.25, block_height=.1)
        self.assertEqual(len([b for b in slab.blocks if b.HasOpenings]), 4)
        self.assertAlmostEqual(sum(volume(b) for b in slab.blocks)+volume(slab.topping_element), before)
        for block in neighbour.blocks:
            self.assertFalse(block.HasOpenings)
            np.testing.assert_allclose(vertices(block), original[block.id()])
        self.assertEqual(ifcopenshell.util.element.get_type(slab.blocks[2]), shared_type)

    def test_reversed_span_signed_layout_and_mirroring(self):
        for direction in ((1, 0), (-1, 0)):
            with self.subTest(direction=direction):
                house, _, slab = self.make_slab(start=(2, 6), end=(2, 3), direction=direction,
                    structure=["beam", "wide", "axis", "beam", "narrow", "beam"])
                original = volume(slab.topping_element)
                slab.add_stiffening_rib(at=.75)
                self.assertGreater(volume(slab.topping_element), original)
                changed = [b for b in slab.blocks if b.HasOpenings]
                self.assertEqual(len(changed), 2)
                self.assertTrue(any((vertices(b)[:, 0].mean()-2)*direction[0] < 0 for b in changed))
                self.assertTrue(any((vertices(b)[:, 0].mean()-2)*direction[0] > 0 for b in changed))
                for block in changed:
                    points = vertices(block)
                    self.assertAlmostEqual(points[:, 1].min(), 5.125)
                    self.assertAlmostEqual(points[:, 1].max(), 5.375)
                with patch.object(house, "mirror_x", True):
                    exported = house._export_model()
                for element in (slab.topping_element, *changed):
                    self.assertEqual({tuple(p) for p in np.round(vertices(exported.by_guid(element.GlobalId)), 7)},
                                     {tuple(p) for p in np.round(vertices(element)*(-1, 1, 1), 7)})

    def test_multiple_ribs_persist_and_touching_strips_are_allowed(self):
        house, _, slab = self.make_slab()
        slab.add_stiffening_rib(at=.75).add_stiffening_rib(at=1, block_height=.1)
        ribs = ifcopenshell.util.element.get_pset(slab, "BBIM_MiakoSlab", "StiffeningRibs")
        self.assertEqual(json.loads(ribs), [dict(at=.75, width=.25, block_height=.08),
                                          dict(at=1, width=.25, block_height=.1)])
        exported = ifcopenshell.file.from_string(house.model.to_string())
        self.assertAlmostEqual(volume(exported.by_guid(slab.topping_element.GlobalId)), volume(slab.topping_element))
        for block in slab.blocks:
            self.assertAlmostEqual(volume(exported.by_guid(block.GlobalId)), volume(block))

    def test_invalid_rib_has_no_side_effects(self):
        house, _, slab = self.make_slab()
        slab.add_stiffening_rib(at=1.5)
        previous_model = house.model.to_string()
        cases = [dict(at=-1), dict(at=0), dict(at=3), dict(at=4), dict(at=float("nan")),
                 dict(at=True), dict(at=2, width=0), dict(at=2, width=float("inf")),
                 dict(at=2, block_height=.05), dict(at=2, block_height=.19),
                 dict(at=2, block_height=.3), dict(at=1.5), dict(at=1.6)]
        for options in cases:
            with self.subTest(options=options), self.assertRaises((TypeError, ValueError)):
                slab.add_stiffening_rib(**options)
            self.assertEqual(house.model.to_string(), previous_model)


if __name__ == "__main__":
    unittest.main()
