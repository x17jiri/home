"""HEB180 layout spacing, bearing, material separation and drawing metadata."""

import unittest
from unittest.mock import patch

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import House


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


class MiakoHebTests(unittest.TestCase):
    def make_slab(self, *, structure=None, start=(0, 0), end=(3, 0), direction=(0, 1)):
        house = House("HEB180 test")
        storey = house.storey("Upper", elevation=3)
        slab = storey.miako_slab("Slab", start=start, end=end, direction=direction,
            top=0, structure=structure or ["beam", "HEB180+", "beam"])
        return house, storey, slab

    def test_profile_bears_30mm_on_both_beams_at_shell_top(self):
        house, storey, slab = self.make_slab()
        self.assertEqual(slab.structure, ("beam", "heb180+", "beam"))
        self.assertAlmostEqual(slab.width, .16+.12+.16)
        self.assertEqual(len(slab.beams), 2)
        self.assertEqual(len(slab.steel_beams), 1)
        self.assertEqual(slab.blocks, ())
        steel, = slab.steel_beams
        points = vertices(steel)
        lower, upper = points.min(axis=0), points.max(axis=0)
        np.testing.assert_allclose(upper-lower, (slab.length, .18, .18), atol=1e-8)
        self.assertAlmostEqual(lower[1], .16-.03)
        self.assertAlmostEqual(upper[1], .16+.12+.03)
        self.assertAlmostEqual(lower[2], storey.elevation+slab.bottom+slab.beam_height)
        self.assertEqual(steel.is_a(), "IfcBeam")
        self.assertEqual(ifcopenshell.util.element.get_material(steel).Name, "Structural steel")
        self.assertEqual(ifcopenshell.util.element.get_aggregate(steel), slab)
        self.assertIn(steel, slab.components)
        rep = ifcopenshell.util.representation.resolve_representation(
            ifcopenshell.util.representation.get_representation(steel, "Model", "Body", "MODEL_VIEW"))
        profile = rep.Items[0].SweptArea
        self.assertEqual(profile.is_a(), "IfcIShapeProfileDef")
        self.assertEqual(profile.ProfileName, "HEB180")
        self.assertAlmostEqual(profile.WebThickness, .0085)
        self.assertAlmostEqual(profile.FlangeThickness, .014)
        self.assertAlmostEqual(profile.FilletRadius, .015)
        # Every bit of steel is excluded from the cast-in-place concrete.
        self.assertAlmostEqual(volume(slab.topping_element)+volume(steel),
            slab.length*(slab.width*slab.height-2*.16*slab.beam_height))

    def test_mixed_layout_and_schedule_count_only_miako_beams(self):
        house, storey, slab = self.make_slab(structure=["beam", "wide", "beam", "heb180+", "beam", "narrow", "beam"])
        self.assertAlmostEqual(slab.width, 4*.16+.455+.12+.33)
        self.assertEqual(len(slab.beam_centerlines), 4)
        self.assertEqual(len(slab.beam_shells), 4)
        self.assertEqual(len(slab.reinforcements), 4)
        self.assertEqual(len(slab.blocks), 24)
        points = vertices(slab.steel_beams[0])
        self.assertAlmostEqual(points[:, 1].min(), .16+.455+.16-.03)
        self.assertAlmostEqual(points[:, 1].max(), .16+.455+.16+.12+.03)
        drawing = house.add_drawing("Plan", x=1.5, y=.8, z=3.1, radius=2,
                                    storeys=[storey], right_panel_width=40)
        drawing.add_miako_beam_schedule([{"location": "Test", "slab": slab}])
        self.assertEqual(drawing._right_panel_tables[-1]["items"][0]["count"], 4)

    def test_minus_is_flush_with_beam_bottoms_without_overlap(self):
        house, storey, slab = self.make_slab(structure=["beam", "HEB180-", "beam"])
        self.assertEqual(slab.structure, ("beam", "heb180-", "beam"))
        self.assertAlmostEqual(slab.width, .50)
        steel, = slab.steel_beams
        points = vertices(steel)
        self.assertAlmostEqual(points[:, 1].min(), .16)
        self.assertAlmostEqual(points[:, 1].max(), .34)
        self.assertAlmostEqual(points[:, 2].min(), storey.elevation+slab.bottom)
        self.assertAlmostEqual(points[:, 2].max(), storey.elevation+slab.bottom+.18)
        # Concrete reaches the bottom throughout the gap, excluding only the
        # steel profile and the two prefabricated beam strips beside it.
        self.assertAlmostEqual(volume(slab.topping_element)+volume(steel),
            slab.length*(slab.width*slab.height-2*.16*slab.beam_height), delta=1e-6)
        # Each flange touches the adjacent beam side, without intersecting it.
        np.testing.assert_allclose(slab.beam_centerlines, (((0, .08), (3, .08)), ((0, .42), (3, .42))))
        old_cover = volume(slab.topping_element)
        old_steel = points.copy()
        slab.add_stiffening_rib(at=1.5)
        self.assertAlmostEqual(volume(slab.topping_element), old_cover, delta=1e-6)
        np.testing.assert_allclose(vertices(steel), old_steel)
        # Both variants can coexist without reusing different placement geometry.
        plus = storey.miako_slab("Plus", start=(0, 2), end=(3, 2), top=0,
            direction=(0, 1), structure=["beam", "heb180+", "beam"])
        self.assertNotEqual(ifcopenshell.util.element.get_type(steel),
                            ifcopenshell.util.element.get_type(plus.steel_beams[0]))

    def test_two_minus_sections_share_gap_and_keep_types_and_voids(self):
        house, storey, slab = self.make_slab(structure=["beam", "heb180-", "heb180-", "beam"])
        self.assertAlmostEqual(slab.width, .68)
        self.assertEqual(len(slab.beams), 2)
        self.assertEqual(len(slab.steel_beams), 2)
        first, second = slab.steel_beams
        self.assertAlmostEqual(vertices(first)[:, 1].max(), vertices(second)[:, 1].min())
        self.assertEqual(ifcopenshell.util.element.get_type(first), ifcopenshell.util.element.get_type(second))
        self.assertAlmostEqual(volume(slab.topping_element)+volume(first)+volume(second),
            slab.length*(slab.width*slab.height-2*.16*slab.beam_height), delta=1e-6)

    def test_bare_heb180_is_rejected_with_migration_hint(self):
        with self.assertRaisesRegex(ValueError, r"heb180\+.*heb180-"):
            self.make_slab(structure=["beam", "heb180", "beam"])

    def test_minus_pair_across_axis_rotates_and_mirrors_correctly(self):
        for direction in ((1, 0), (-1, 0)):
            with self.subTest(direction=direction):
                house, _, slab = self.make_slab(start=(2, 6), end=(2, 3), direction=direction,
                    structure=["beam", "wide", "beam", "heb180-", "axis", "heb180-", "beam"])
                self.assertAlmostEqual(slab.width_before_axis, .16+.455+.16+.18)
                self.assertAlmostEqual(slab.width_after_axis, .18+.16)
                first, second = slab.steel_beams
                first_offsets = (vertices(first)[:, 0]-2)*direction[0]
                second_offsets = (vertices(second)[:, 0]-2)*direction[0]
                np.testing.assert_allclose((first_offsets.min(), first_offsets.max()), (-.18, 0), atol=1e-8)
                np.testing.assert_allclose((second_offsets.min(), second_offsets.max()), (0, .18), atol=1e-8)
                self.assertGreater(volume(slab.topping_element), 0)
                with patch.object(house, "mirror_x", True):
                    exported = house._export_model()
                for element in (first, second, slab.topping_element):
                    self.assertEqual({tuple(p) for p in np.round(vertices(exported.by_guid(element.GlobalId)), 7)},
                                     {tuple(p) for p in np.round(vertices(element)*(-1, 1, 1), 7)})

    def test_signed_axis_layout_rotated_span_and_export_mirroring(self):
        for direction in ((1, 0), (-1, 0)):
            with self.subTest(direction=direction):
                house, _, slab = self.make_slab(start=(2, 6), end=(2, 3), direction=direction,
                    structure=["beam", "wide", "beam", "axis", "heb180+", "beam"])
                self.assertAlmostEqual(slab.width_before_axis, .16+.455+.16)
                self.assertAlmostEqual(slab.width_after_axis, .12+.16)
                steel = slab.steel_beams[0]
                local_offsets = (vertices(steel)[:, 0]-2)*direction[0]
                self.assertAlmostEqual(local_offsets.min(), -.03)
                self.assertAlmostEqual(local_offsets.max(), .15)
                self.assertGreater(volume(slab.topping_element), 0)
                with patch.object(house, "mirror_x", True):
                    exported = house._export_model()
                for element in (steel, slab.topping_element):
                    self.assertEqual({tuple(p) for p in np.round(vertices(exported.by_guid(element.GlobalId)), 7)},
                                     {tuple(p) for p in np.round(vertices(element)*(-1, 1, 1), 7)})

    def test_stiffening_rib_does_not_fill_embedded_steel(self):
        house, _, slab = self.make_slab()
        before = volume(slab.topping_element)
        steel_before = vertices(slab.steel_beams[0])
        # This slab already has concrete between and over both beams. A
        # transverse rib must not refill the HEB void during its union.
        slab.add_stiffening_rib(at=1.5)
        # Boolean splits tessellate the root fillets differently; allow 1 cm³.
        self.assertAlmostEqual(volume(slab.topping_element), before, delta=1e-6)
        np.testing.assert_allclose(vertices(slab.steel_beams[0]), steel_before)
        reopened = ifcopenshell.file.from_string(house.model.to_string())
        self.assertAlmostEqual(volume(reopened.by_guid(slab.topping_element.GlobalId)), before, delta=1e-6)

    def test_types_reuse_only_matching_geometry_and_heights(self):
        house, storey, slab = self.make_slab()
        other = storey.miako_slab("Other", start=(0, 2), end=(3, 2), top=0,
                                  direction=(0, 1), structure=["beam", "heb180+", "beam"])
        self.assertEqual(ifcopenshell.util.element.get_type(slab.steel_beams[0]),
                         ifcopenshell.util.element.get_type(other.steel_beams[0]))
        taller = storey.miako_slab("Taller", start=(0, 4), end=(3, 4), top=0,
            direction=(0, 1), structure=["beam", "heb180+", "beam"],
            beam_height=.08, block_height=.25, topping=.01)
        self.assertNotEqual(ifcopenshell.util.element.get_type(slab.steel_beams[0]),
                            ifcopenshell.util.element.get_type(taller.steel_beams[0]))
        self.assertAlmostEqual(vertices(taller.steel_beams[0])[:, 2].max(), storey.elevation)

    def test_invalid_placements_fail_before_creating_ifc_geometry(self):
        house = House("Invalid HEB layouts")
        storey = house.storey("Upper", elevation=3)
        baseline = house.model.to_string()
        for structure in (["heb180+", "beam", "wide"], ["wide", "beam", "heb180+"],
                          ["beam", "heb180+", "wide", "beam"],
                          ["beam", "wide", "heb180+", "beam"],
                          ["beam", "heb180+", "heb180+", "beam"],
                          ["heb180-", "beam", "wide"],
                          ["beam", "heb180-", "wide", "beam"],
                          ["beam", "heb180-", "heb180-"]):
            with self.subTest(structure=structure):
                with self.assertRaisesRegex(ValueError, "between two beam"):
                    storey.miako_slab("Invalid", start=(0, 0), end=(3, 0), top=0,
                        direction=(0, 1), structure=structure)
                self.assertEqual(house.model.to_string(), baseline)
        with self.assertRaisesRegex(ValueError, "fit within"):
            storey.miako_slab("Too thin", start=(0, 0), end=(3, 0), top=0,
                direction=(0, 1), structure=["beam", "heb180+", "beam"], block_height=.13)
        self.assertEqual(house.model.to_string(), baseline)
        # The minus variant fits in a slab too thin for the raised variant.
        minus = storey.miako_slab("Thin minus", start=(0, 0), end=(3, 0), top=0,
            direction=(0, 1), structure=["beam", "heb180-", "beam"], block_height=.13)
        self.assertAlmostEqual(vertices(minus.steel_beams[0])[:, 2].min(), 3-.19)


if __name__ == "__main__":
    unittest.main()
