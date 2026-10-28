"""Vertical chimney shafts must keep their XY footprint through roof layers."""

import unittest

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np

from ifc_utils import House


class VerticalRoofOpeningTests(unittest.TestCase):
    def setUp(self):
        self.house = House("Chimney shaft")
        self.roof = self.house.storey("Roof", elevation=3).roof("Roof")
        self.plane = self.roof.plane("Slope", points=((0, 0, 4), (6, 0, 4), (0, 4, 6)))

    @staticmethod
    def mesh(element):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        return np.asarray(shape.geometry.verts).reshape(-1, 3), np.asarray(shape.geometry.faces).reshape(-1, 3)

    @classmethod
    def volume(cls, element):
        vertices, faces = cls.mesh(element)
        return abs(np.einsum('ij,ij->i', vertices[faces[:, 0]],
                            np.cross(vertices[faces[:, 1]], vertices[faces[:, 2]])).sum()) / 6

    def layer(self, offset=0):
        return self.plane.layer(f"Layer {offset}", outline=((0, 0), (6, 0), (6, 5), (0, 5)),
                                z_offset=offset, thickness=.1, material="Roof tiles")

    def shaft(self):
        return self.roof.add_opening("Chimney", rectangle=((2, 1), (3, 2)), vertical=True, trimmers=False)

    def test_existing_and_future_layers_keep_the_same_vertical_shaft(self):
        before = self.layer()
        uncut_volume = self.volume(before)
        opening = self.shaft()
        layers = [before, self.layer(.3), self.layer(.7)]
        self.assertTrue(opening.vertical)
        self.assertFalse(opening.trimmers)
        self.assertEqual(len(opening.elements), 3)
        expected_removal = .1 / self.plane.z_axis[2]
        for layer in layers:
            self.assertAlmostEqual(self.volume(layer), uncut_volume - expected_removal)
        for void in opening.elements:
            matrix = ifcopenshell.util.placement.get_local_placement(void.ObjectPlacement)
            np.testing.assert_allclose(matrix[:3, 2], (0, 0, 1))
            vertices, faces = self.mesh(void)
            vertices = vertices[np.unique(faces)]
            np.testing.assert_allclose(vertices[:, :2].min(axis=0), (2, 1))
            np.testing.assert_allclose(vertices[:, :2].max(axis=0), (3, 2))
            self.assertTrue(ifcopenshell.util.element.get_pset(void, "BBIM_RoofOpening", "Vertical"))

    def test_vertical_shaft_registered_before_any_parts_also_cuts_beams(self):
        opening = self.shaft()
        layer = self.layer(.4)
        z_offset, height = -.1, .2
        y = (1.5 - (z_offset + height/2)*self.plane.z_axis[1]) / self.plane.y_axis[1]
        beam = self.plane.beam("Batten", start=(0, y), end=(6, y), size=(.1, height), z_offset=z_offset)
        self.assertEqual(len(opening.elements), 2)
        self.assertAlmostEqual(self.volume(beam), 5 * .1 * height)
        self.assertEqual(len(layer.HasOpenings), 1)
        self.assertEqual(len(beam.HasOpenings), 1)

    def test_finished_clipping_excludes_non_intersecting_roof_slopes(self):
        opening = self.shaft()
        plane = self.roof.plane("Other slope", points=self.plane.points,
                                cuts=[((0, 3, 0), (10, 3, 0), (0, 3, 10))])
        layer = plane.layer("Clipped", outline=((0, 0), (6, 0), (6, 10), (0, 10)),
                            thickness=.1, material="Roof tiles")
        vertices, faces = self.mesh(layer)
        self.assertGreaterEqual(vertices[np.unique(faces), 1].min(), 3 - 1e-7)
        self.assertFalse(layer.HasOpenings)
        self.assertFalse(opening.elements)

    def test_skylight_default_stays_roof_normal(self):
        opening = self.roof.add_opening("Window", rectangle=((2, 1), (3, 2)))
        self.layer()
        self.assertFalse(opening.vertical)
        void, = opening.elements
        matrix = ifcopenshell.util.placement.get_local_placement(void.ObjectPlacement)
        np.testing.assert_allclose(matrix[:3, 2], self.plane.z_axis)
        self.assertFalse(ifcopenshell.util.element.get_pset(void, "BBIM_RoofOpening", "Vertical"))

    def test_vertical_shaft_is_mirrored_once_without_changing_live_geometry(self):
        self.shaft()
        layer = self.layer(.3)
        before, faces = self.mesh(layer)
        before = before[np.unique(faces)]
        self.house.mirror_x = True
        exported = self.house._export_model()
        mirrored, faces = self.mesh(exported.by_guid(layer.GlobalId))
        mirrored = mirrored[np.unique(faces)]
        expected = before.copy()
        expected[:, 0] *= -1
        self.assertEqual({tuple(np.round(v, 7)) for v in mirrored},
                         {tuple(np.round(v, 7)) for v in expected})
        after, faces = self.mesh(layer)
        np.testing.assert_allclose(after[np.unique(faces)], before)

    def test_validates_vertical_flag_and_rejects_skylight_in_vertical_shaft(self):
        with self.assertRaisesRegex(TypeError, "vertical must be a boolean"):
            self.roof.add_opening("Invalid", rectangle=((2, 1), (3, 2)), vertical="yes")
        opening = self.shaft()
        layer = self.layer(.3)
        with self.assertRaisesRegex(ValueError, "roof-normal opening"):
            self.plane.add_window(opening, top_layer=layer)


if __name__ == "__main__":
    unittest.main()
