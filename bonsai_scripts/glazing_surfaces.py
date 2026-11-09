"""Identify glazing in Bonsai's native visible-surface fills."""

from contextlib import contextmanager


def _aspect_style_ids(element, name):
    result = set()
    for aspect in element.Representation.HasShapeAspects:
        if aspect.Name != name:
            continue
        for representation in aspect.ShapeRepresentations:
            for item in representation.Items:
                for styled in item.StyledByItem:
                    for style in styled.Styles:
                        if style.is_a("IfcPresentationStyleAssignment"):
                            result.update(s.id() for s in style.Styles)
                        else:
                            result.add(style.id())
    return result


@contextmanager
def glazing_surface_classes(operator_class, tool):
    """Use the actual ray-hit face material, retaining native occlusion and holes.

    Bonsai labels surface fills by product, which otherwise merges the glass
    and frame. Scope this adapter to a single export; never alter installed code.
    """
    cast = operator_class.cast_rays_and_get_best_object
    classes = operator_class.get_svg_classes
    glazing_styles = {}

    def cast_with_glazing(self, *args, **kwargs):
        self._drawing_glazing_hit = None
        hit = cast(self, *args, **kwargs)
        obj, _, face_index = hit
        if obj is None:
            return hit
        element = tool.Ifc.get_entity(obj)
        if element is None or not element.is_a("IfcWindow"):
            return hit
        if element.id() not in glazing_styles:
            glazing_styles[element.id()] = (
                _aspect_style_ids(element, "Glazing")
                - _aspect_style_ids(element, "Framing")
                - _aspect_style_ids(element, "Lining")
            )
        polygon = obj.data.polygons[face_index]
        material = obj.data.materials[polygon.material_index] if obj.data.materials else None
        if material and tool.Blender.get_ifc_definition_id(material) in glazing_styles[element.id()]:
            self._drawing_glazing_hit = element.id()
        return hit

    def classes_with_glazing(self, element, *args, **kwargs):
        result = list(classes(self, element, *args, **kwargs))
        if getattr(self, "_drawing_glazing_hit", None) == element.id():
            result.append("drawing-glazing")
        self._drawing_glazing_hit = None
        return result

    operator_class.cast_rays_and_get_best_object = cast_with_glazing
    operator_class.get_svg_classes = classes_with_glazing
    try:
        yield
    finally:
        operator_class.cast_rays_and_get_best_object = cast
        operator_class.get_svg_classes = classes
