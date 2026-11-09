"""Native geometry and IFC export checks for half-round gutters."""

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.shape
import numpy as np

from ifc_utils import House


def geometry(element):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set("mesher-linear-deflection", 1e-5)
    shape = ifcopenshell.geom.create_shape(settings, element)
    vertices = np.asarray(shape.geometry.verts).reshape(-1, 3).copy()
    return vertices, ifcopenshell.util.shape.get_volume(shape.geometry)


class GutterTests(unittest.TestCase):
    def test_curved_hollow_shell_caps_and_world_coordinates(self):
        for start, end in (((1, 2, 4), (1, 5, 4)), ((1, 5, 4), (1, 2, 4)),
                           ((1, 2, 4), (4, 6, 4))):
            for capped in (False, True):
                with self.subTest(start=start, end=end, capped=capped):
                    house = House("Gutter", mirror_x=False)
                    storey = house.storey("Rainwater drainage", elevation=2)
                    gutter = storey.gutter("Gutter", start=start, end=end, diameter=.16,
                                          wall_thickness=.002, end_caps=capped)
                    self.assertEqual(gutter.PredefinedType, "GUTTER")
                    self.assertEqual(ifcopenshell.util.element.get_container(gutter), storey.element)
                    vertices, volume = geometry(gutter)
                    direction = (np.asarray(end)-start)/math.dist(start, end)
                    across = np.cross((0, 0, 1), direction)
                    local = vertices-np.asarray(start)
                    np.testing.assert_allclose((min(local@direction), max(local@direction)),
                                               (0, math.dist(start, end)), atol=1e-7)
                    np.testing.assert_allclose((min(local@across), max(local@across)), (-.08, .08), atol=1e-7)
                    np.testing.assert_allclose((vertices[:, 2].min(), vertices[:, 2].max()), (3.92, 4), atol=1e-5)
                    expected = math.pi/2*(.08**2-.078**2)*math.dist(start, end)
                    if capped:
                        expected += math.pi*.078**2*.002
                    self.assertAlmostEqual(volume, expected, delta=expected*.002)
                    self.assertLess(volume, .1*math.pi/2*.08**2*math.dist(start, end))
                    body, = gutter.Representation.Representations
                    self.assertEqual(len(body.Items), 3 if capped else 1)
                    self.assertEqual(sum(s.is_a("IfcArcIndex") for s in body.Items[0].SweptArea.OuterCurve.Segments), 2)

    def test_mirrored_export_and_persisted_dimensions(self):
        for mirrored in (False, True):
            with self.subTest(mirrored=mirrored), TemporaryDirectory() as scratch:
                house = House("Gutter", mirror_x=mirrored)
                gutter = house.storey("Rainwater drainage", elevation=0).gutter(
                    "Gutter", start=(2, -1, 5), end=(2, 7, 5), diameter=.15,
                )
                path = Path(scratch)/"gutters.ifc"
                house.write(path)
                exported = ifcopenshell.open(path).by_guid(gutter.GlobalId)
                vertices, volume = geometry(exported)
                centre = -2 if mirrored else 2
                np.testing.assert_allclose((vertices[:, 0].min(), vertices[:, 0].max()),
                                           (centre-.075, centre+.075), atol=1e-7)
                self.assertGreater(volume, 0)
                self.assertEqual(ifcopenshell.util.element.get_pset(exported, "BBIM_Gutter", "Length"), 8)
                self.assertEqual(ifcopenshell.util.element.get_pset(exported, "BBIM_Gutter", "Diameter"), .15)

    def test_invalid_sections_and_endpoints_are_rejected_before_creating_elements(self):
        house = House("Gutter", mirror_x=False)
        storey = house.storey("Rainwater drainage", elevation=0)
        for options in ({"diameter": 0}, {"wall_thickness": 0}, {"wall_thickness": .075},
                        {"end": (0, 0, 0)}, {"end": (0, 2, 1)}, {"diameter": float("nan")}):
            arguments = dict(start=(0, 0, 0), end=(0, 2, 0))
            arguments.update(options)
            with self.subTest(options=options), self.assertRaises((ValueError, TypeError)):
                storey.gutter("Invalid", **arguments)
        self.assertEqual(len(house.model.by_type("IfcPipeSegment")), 0)


if __name__ == "__main__":
    unittest.main()
