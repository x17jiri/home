"""Embedded HEB geometry, centreline placement and composite drawing selection."""

import json
import unittest
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.selector
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import Beam, Girder, House
from steel_profiles import HEB_SECTIONS, heb_section


def shape(element):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    return ifcopenshell.geom.create_shape(settings, element)


def vertices(element):
    result = shape(element)
    return np.array(result.geometry.verts).reshape(-1, 3)


def volume(element):
    result = shape(element)
    return ifcopenshell.util.shape.get_volume(result.geometry)


class GirderTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Girder tests")
        self.storey = self.house.storey("Upper", elevation=3)

    def girder(self, **changes):
        return self.storey.girder("Průvlak", **(dict(start=(1, 2, 3.1), end=(5, 2, 3.1),
                                                   width=.3, height=.35, heb=180) | changes))

    def test_centred_concrete_and_steel_have_separate_nonoverlapping_volumes(self):
        girder = self.girder()
        self.assertIsInstance(girder, Girder)
        self.assertIsInstance(girder, Beam)
        self.assertEqual(girder.is_a(), "IfcBeam")
        self.assertIs(girder.concrete, girder)
        self.assertEqual(ifcopenshell.util.element.get_container(girder), self.storey.element)
        self.assertEqual(ifcopenshell.util.element.get_container(girder.steel), self.storey.element)
        self.assertEqual(ifcopenshell.util.element.get_aggregate(girder.steel), girder)
        self.assertEqual(ifcopenshell.util.element.get_material(girder).Name, "Girder concrete")
        self.assertEqual(ifcopenshell.util.element.get_material(girder.steel).Name, "Structural steel")
        concrete, steel = vertices(girder), vertices(girder.steel)
        np.testing.assert_allclose(concrete.min(axis=0), (1, 1.85, 3.1-.175))
        np.testing.assert_allclose(concrete.max(axis=0), (5, 2.15, 3.1+.175))
        np.testing.assert_allclose(steel.min(axis=0), (1, 1.91, 3.01))
        np.testing.assert_allclose(steel.max(axis=0), (5, 2.09, 3.19))
        self.assertAlmostEqual(volume(girder)+volume(girder.steel), 4*.3*.35)
        self.assertAlmostEqual(girder.finished_length(), 4)
        pset = ifcopenshell.util.element.get_pset(girder, "BBIM_Girder")
        self.assertEqual(pset["HEB"], "HEB180")
        self.assertEqual(pset["Steel"], girder.steel.GlobalId)
        self.assertEqual(json.loads(pset["Start"]), [1, 2, 3.1])

    def test_diagonal_sloping_reversed_and_vertical_spans_use_same_frame(self):
        for start, end in (((2, 1, 3), (5, 5, 5)), ((5, 5, 5), (2, 1, 3)), ((1, 1, 2), (1, 1, 5))):
            with self.subTest(start=start, end=end):
                girder = self.girder(start=start, end=end)
                for element, width, height in ((girder, .3, .35), (girder.steel, .18, .18)):
                    local = (vertices(element)-start) @ girder.placement[:3, :3]
                    np.testing.assert_allclose(local.min(axis=0), (0, -width/2, -height/2), atol=1e-7)
                    np.testing.assert_allclose(local.max(axis=0), (girder.length, width/2, height/2), atol=1e-7)
                self.assertAlmostEqual(volume(girder)+volume(girder.steel), girder.length*.3*.35)

    def test_non_square_heb320_dimensions_are_taken_from_catalog(self):
        girder = self.girder(heb="he 320 b", width=.4, height=.5)
        section = girder.heb_section
        self.assertEqual(section.nominal, 320)
        self.assertEqual((section.height, section.width), (.32, .3))
        points = vertices(girder.steel)
        np.testing.assert_allclose(points.max(axis=0)-points.min(axis=0), (4, .3, .32))
        body = ifcopenshell.util.representation.get_representation(girder.steel, "Model", "Body", "MODEL_VIEW")
        profile = body.Items[0].SweptArea
        self.assertEqual(profile.ProfileName, "HEB320")
        self.assertAlmostEqual(profile.WebThickness, .0115)
        self.assertAlmostEqual(profile.FlangeThickness, .0205)
        self.assertAlmostEqual(profile.FilletRadius, .027)

    def test_catalog_profiles_and_name_forms(self):
        for value in (180, 180., "180", "HEB180", "heb 180", "HE 180 B"):
            self.assertEqual(heb_section(value), HEB_SECTIONS[180])
        for section in HEB_SECTIONS.values():
            with self.subTest(section=section.name):
                girder = self.girder(heb=section.nominal, width=section.width+.1, height=section.height+.1)
                self.assertGreater(volume(girder.steel), 0)
                self.assertAlmostEqual(volume(girder)+volume(girder.steel), girder.width*girder.height*girder.length)

    def test_invalid_arguments_leave_no_partial_ifc_products(self):
        before = self.house.model.to_string()
        for changes in (dict(start=(1, 2, 3.1), end=(1, 2, 3.1)), dict(width=0), dict(height=-1),
                        dict(width=.17), dict(height=.17), dict(heb=185), dict(heb=.18),
                        dict(heb="HEA180"), dict(heb="HEB180+"), dict(heb=True), dict(heb=float("inf")),
                        dict(start=(1, 2)), dict(end=(1, float("nan"), 2)),
                        dict(concrete_color="no-color"), dict(steel_color="no-color"), dict(transparency=2)):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                self.girder(**changes)
            self.assertEqual(self.house.model.to_string(), before)

    def test_explicit_inclusion_and_exclusion_handle_both_parts(self):
        girder = self.girder()
        ground = self.house.storey("Ground", elevation=0)
        drawing = self.house.add_drawing("Cross-storey", x=3, y=2, z=3.2, radius=3, storeys=[ground])
        drawing.include_element(girder)
        included = ifcopenshell.util.selector.filter_elements(self.house.model,
            ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Include"))
        self.assertTrue({girder, girder.steel}.issubset(included))
        drawing.exclude_element(girder)
        excluded = ifcopenshell.util.selector.filter_elements(self.house.model,
            ifcopenshell.util.element.get_pset(drawing.element, "EPset_Drawing", "Exclude"))
        self.assertEqual(excluded, {girder, girder.steel})

    def test_export_mirrors_once_and_reopening_preserves_parts_and_volumes(self):
        girder = self.girder(start=(2, 1, 3), end=(5, 5, 4), heb="HEB200")
        original = {e.GlobalId: vertices(e) for e in (girder, girder.steel)}
        with patch.object(self.house, "mirror_x", True):
            exported = self.house._export_model()
        for element in (girder, girder.steel):
            self.assertEqual({tuple(p) for p in np.round(vertices(exported.by_guid(element.GlobalId)), 7)},
                             {tuple(p) for p in np.round(original[element.GlobalId]*(-1, 1, 1), 7)})
            np.testing.assert_allclose(vertices(element), original[element.GlobalId])
        reopened = ifcopenshell.file.from_string(exported.to_string())
        self.assertEqual(ifcopenshell.util.element.get_aggregate(reopened.by_guid(girder.steel.GlobalId)),
                         reopened.by_guid(girder.GlobalId))
        self.assertAlmostEqual(volume(reopened.by_guid(girder.GlobalId))+volume(reopened.by_guid(girder.steel.GlobalId)),
                               girder.length*girder.width*girder.height)


if __name__ == "__main__":
    unittest.main()
