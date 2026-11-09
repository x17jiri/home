"""Classify the native surface hit rather than colouring an entire window."""

from types import SimpleNamespace
import unittest

from bonsai_scripts.glazing_surfaces import _aspect_style_ids, glazing_surface_classes
from ifc_utils import House


class GlazingSurfaceTests(unittest.TestCase):
    def test_glass_hits_only_and_methods_restored_after_export(self):
        house = House("Glazing", mirror_x=False)
        wall = house.storey("Ground", elevation=0).wall((0, 0), (5, 0), thickness=.24, height=3)
        window = wall.add_window(at=1, width=1.5, sill_height=1, height=2, color="#ffffff")
        glass_style = next(iter(_aspect_style_ids(window, "Glazing")))
        frame_style = next(iter(_aspect_style_ids(window, "Framing")))
        self.assertNotEqual(glass_style, frame_style)
        obj = SimpleNamespace(data=SimpleNamespace(
            polygons=[SimpleNamespace(material_index=0), SimpleNamespace(material_index=1)],
            materials=[glass_style, frame_style],
        ))
        tool = SimpleNamespace(
            Ifc=SimpleNamespace(get_entity=lambda obj: window),
            Blender=SimpleNamespace(get_ifc_definition_id=lambda material: material),
        )

        class Operator:
            hit = (obj, None, 0)

            def cast_rays_and_get_best_object(self):
                return self.hit

            def get_svg_classes(self, element, layer=None):
                return [element.is_a(), "surface"]

        original_cast = Operator.cast_rays_and_get_best_object
        original_classes = Operator.get_svg_classes
        operator = Operator()
        with self.assertRaisesRegex(RuntimeError, "export failed"):
            with glazing_surface_classes(Operator, tool):
                operator.cast_rays_and_get_best_object()
                self.assertIn("drawing-glazing", operator.get_svg_classes(window))
                # A later projection outline must not inherit the surface hit.
                self.assertNotIn("drawing-glazing", operator.get_svg_classes(window))
                operator.hit = (obj, None, 1)
                operator.cast_rays_and_get_best_object()
                self.assertNotIn("drawing-glazing", operator.get_svg_classes(window))
                operator.hit = (None, None, None)
                operator.cast_rays_and_get_best_object()
                self.assertNotIn("drawing-glazing", operator.get_svg_classes(window))
                raise RuntimeError("export failed")
        self.assertIs(Operator.cast_rays_and_get_best_object, original_cast)
        self.assertIs(Operator.get_svg_classes, original_classes)


if __name__ == "__main__":
    unittest.main()
