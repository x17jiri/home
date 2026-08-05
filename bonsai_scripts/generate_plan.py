"""Create a Bonsai floor-plan SVG from an IFC model.

This file is launched by ``ifc_utils.generate_plan`` through Blender.
Arguments after Blender's ``--`` separator keep each run self-contained and
avoid a shared parameter file that can become stale or collide with another
run.
"""

from __future__ import annotations

import argparse
from math import isfinite
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ifc", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stylesheet", required=True, type=Path)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--z", required=True, type=float)
    parser.add_argument("--radius", required=True, type=float)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    result = parser.parse_args(arguments)

    for name in ("x", "y", "z", "radius"):
        if not isfinite(getattr(result, name)):
            parser.error(f"--{name} must be finite")
    if result.radius <= 0:
        parser.error("--radius must be greater than zero")
    if result.output.suffix.lower() != ".svg":
        parser.error("--output must use the .svg extension")
    return result


def require_bonsai() -> None:
    try:
        bpy.ops.bim.load_project.get_rna_type()
    except Exception as error:
        raise RuntimeError(
            "Bonsai must be installed and enabled in Blender's user preferences"
        ) from error


def require_finished(result: set[str], operation: str) -> None:
    if "FINISHED" not in result:
        raise RuntimeError(f"{operation} failed with result {sorted(result)}")


def choose_storey(model, cut_z: float):
    import ifcopenshell.util.placement

    storeys = model.by_type("IfcBuildingStorey")
    if not storeys:
        raise RuntimeError("the IFC model contains no IfcBuildingStorey")

    elevations = [
        (ifcopenshell.util.placement.get_storey_elevation(storey), storey)
        for storey in storeys
    ]
    storeys_below_cut = [item for item in elevations if item[0] <= cut_z]
    if storeys_below_cut:
        return max(storeys_below_cut, key=lambda item: item[0])[1]
    return min(elevations, key=lambda item: abs(item[0] - cut_z))[1]


def clear_startup_scene() -> None:
    # Avoid including Blender's default cube, camera, or light in the drawing.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def generate_plan(args: argparse.Namespace) -> Path:
    require_bonsai()
    from bonsai import tool

    ifc_path = args.ifc.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    stylesheet_path = args.stylesheet.expanduser().resolve()
    if not ifc_path.is_file():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")
    if not stylesheet_path.is_file():
        raise FileNotFoundError(f"plan stylesheet not found: {stylesheet_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clear_startup_scene()
    require_finished(
        bpy.ops.bim.load_project(
            filepath=str(ifc_path),
            is_advanced=False,
            use_relative_path=False,
            should_start_fresh_session=False,
            import_without_ifc_data=False,
        ),
        "loading the IFC project",
    )

    model = tool.Ifc.get()
    if model is None:
        raise RuntimeError("Bonsai did not load the IFC model")
    storey = choose_storey(model, args.z)

    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("Blender has no active scene")
    scene.cursor.location = Vector((args.x, args.y, args.z))

    document_props = tool.Drawing.get_document_props()
    document_props.target_view = "PLAN_VIEW"
    document_props.location_hint = str(storey.id())
    document_props.should_use_underlay_cache = False
    document_props.should_use_linework_cache = False
    document_props.should_use_annotation_cache = False

    existing_drawing_ids = {
        drawing.id()
        for drawing in model.by_type("IfcAnnotation")
        if drawing.ObjectType == "DRAWING"
    }
    require_finished(bpy.ops.bim.add_drawing(), "adding the plan drawing")
    new_drawings = [
        drawing
        for drawing in model.by_type("IfcAnnotation")
        if drawing.ObjectType == "DRAWING" and drawing.id() not in existing_drawing_ids
    ]
    if len(new_drawings) != 1:
        raise RuntimeError(f"expected one new drawing, found {len(new_drawings)}")
    drawing = new_drawings[0]

    # Annotations authored before this drawing exists cannot already belong to
    # its drawing group.  Associate persisted batting annotations in Blender's
    # in-memory IFC so Bonsai includes them in this export.  The source IFC on
    # disk is intentionally left unchanged.
    batting_annotations = [
        annotation
        for annotation in model.by_type("IfcAnnotation")
        if annotation != drawing and annotation.ObjectType == "BATTING"
    ]
    if batting_annotations:
        drawing_group = tool.Drawing.get_drawing_group(drawing)
        if drawing_group is None:
            raise RuntimeError("the new drawing has no annotation group")
        tool.Ifc.run(
            "group.assign_group",
            group=drawing_group,
            products=batting_annotations,
        )

    drawing_document = tool.Drawing.get_drawing_document(drawing)
    if drawing_document is None:
        raise RuntimeError("the new drawing has no IfcDocumentReference")
    tool.Ifc.run(
        "document.edit_reference",
        reference=drawing_document,
        attributes={"Location": str(output_path)},
    )

    import ifcopenshell.util.element

    drawing_pset_data = ifcopenshell.util.element.get_pset(drawing, "EPset_Drawing")
    if not drawing_pset_data:
        raise RuntimeError("the new drawing has no EPset_Drawing property set")
    drawing_pset = model.by_id(drawing_pset_data["id"])
    tool.Ifc.run(
        "pset.edit_pset",
        pset=drawing_pset,
        properties={"Stylesheet": str(stylesheet_path)},
    )

    require_finished(
        bpy.ops.bim.activate_drawing(
            drawing=drawing.id(),
            should_view_from_camera=False,
            use_quick_preview=False,
        ),
        "activating the plan drawing",
    )

    camera = scene.camera
    if camera is None or not isinstance(camera.data, bpy.types.Camera):
        raise RuntimeError("Bonsai did not activate a drawing camera")
    camera_matrix = camera.matrix_world.copy()
    camera_matrix.translation = Vector((args.x, args.y, args.z))
    camera.matrix_world = camera_matrix
    camera.data.type = "ORTHO"
    camera.data.clip_start = 0.002
    camera.data.clip_end = max(10.0, abs(args.z) + 10.0)

    # Bonsai treats these properties as authoritative and synchronises the
    # native Blender ortho_scale and raster dimensions from them.
    camera_props = tool.Drawing.get_camera_props(camera.data)
    camera_props.width = 2 * args.radius
    camera_props.height = 2 * args.radius
    camera_props.update_camera_resolution()

    require_finished(
        bpy.ops.bim.create_drawing(
            print_all=False,
            open_viewer=False,
            sync=True,
        ),
        "creating the SVG drawing",
    )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Bonsai did not create the SVG: {output_path}")
    print(f"Bonsai SVG created: {output_path}", flush=True)
    return output_path


def main() -> None:
    generate_plan(parse_args())
    bpy.ops.wm.quit_blender()


if __name__ == "__main__":
    main()
