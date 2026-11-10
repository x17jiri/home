"""Use railing drawing bodies for both native lines and visible-surface fills."""

import ifcopenshell.util.element
import ifcopenshell.util.representation


def activate_railing_drawing_bodies(tool, drawing):
    """Switch only the temporary Blender meshes, retaining the physical IFC body.

    The SVG serializer already selects target-view representations. Bonsai's
    surface-fill raycasts also need those meshes rather than the model posts.
    """
    from bonsai.core.geometry import switch_representation

    target = ifcopenshell.util.element.get_pset(drawing, "EPset_Drawing", "TargetView")
    context_type = "Plan" if target == "PLAN_VIEW" else "Model"
    count = 0
    for railing in tool.Ifc.get().by_type("IfcRailing"):
        obj = tool.Ifc.get_object(railing)
        representation = ifcopenshell.util.representation.get_representation(
            railing, context_type, "Body", target,
        )
        if obj is not None and representation is not None:
            switch_representation(tool.Ifc, tool.Geometry, obj, representation)
            count += 1
    return count
