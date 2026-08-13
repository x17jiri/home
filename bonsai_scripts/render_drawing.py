"""Render an existing drawing stored in an IFC file with Bonsai."""

from __future__ import annotations

import argparse
import faulthandler
import os
from pathlib import Path
import sys
from time import monotonic

import bpy


_STARTED_AT = monotonic()
_LAST_STAGE_AT = _STARTED_AT
_HANG_DIAGNOSTIC_SECONDS = 30


def report_stage(message: str) -> None:
    """Print an elapsed-time marker that remains visible during Blender hangs."""
    global _LAST_STAGE_AT
    now = monotonic()
    elapsed = now - _STARTED_AT
    stage_elapsed = now - _LAST_STAGE_AT
    print(
        f"[drawing pid={os.getpid()} +{elapsed:.2f}s; previous stage "
        f"{stage_elapsed:.2f}s] {message}",
        flush=True,
    )
    _LAST_STAGE_AT = now


def enable_hang_diagnostics() -> None:
    """Dump the Python stack repeatedly if a Blender operation stops returning."""
    faulthandler.enable()
    faulthandler.dump_traceback_later(
        _HANG_DIAGNOSTIC_SECONDS,
        repeat=True,
    )
    report_stage(
        f"Renderer started; Python stack watchdog armed for "
        f"{_HANG_DIAGNOSTIC_SECONDS}s"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ifc", required=True, type=Path)
    parser.add_argument("--drawing-guid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    result = parser.parse_args(arguments)
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


def clear_startup_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def render_drawing(args: argparse.Namespace) -> Path:
    report_stage("Checking Bonsai availability")
    require_bonsai()
    from bonsai import tool

    ifc_path = args.ifc.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if not ifc_path.is_file():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_stage("Clearing the Blender startup scene")
    clear_startup_scene()
    report_stage(f"Loading persisted IFC drawing from {ifc_path}")
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
    report_stage("IFC project loaded")

    model = tool.Ifc.get()
    if model is None:
        raise RuntimeError("Bonsai did not load the IFC model")
    try:
        drawing = model.by_guid(args.drawing_guid)
    except RuntimeError as error:
        raise RuntimeError(f"drawing not found: {args.drawing_guid}") from error
    if not drawing.is_a("IfcAnnotation") or drawing.ObjectType != "DRAWING":
        raise RuntimeError(f"IFC entity is not a drawing: {args.drawing_guid}")
    report_stage(f'Found drawing "{drawing.Name}" ({drawing.GlobalId})')

    drawing_document = tool.Drawing.get_drawing_document(drawing)
    if drawing_document is None:
        raise RuntimeError("the drawing has no IfcDocumentReference")
    tool.Ifc.run(
        "document.edit_reference",
        reference=drawing_document,
        attributes={"Location": str(output_path)},
    )

    document_props = tool.Drawing.get_document_props()
    document_props.should_use_underlay_cache = False
    document_props.should_use_linework_cache = False
    document_props.should_use_annotation_cache = False

    report_stage("Activating persisted drawing camera")
    require_finished(
        bpy.ops.bim.activate_drawing(
            drawing=drawing.id(),
            should_view_from_camera=False,
            use_quick_preview=False,
        ),
        "activating the drawing",
    )
    report_stage("Drawing camera activated")
    report_stage(f"Creating SVG at {output_path}")
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
    report_stage(f"Bonsai SVG created: {output_path}")
    return output_path


def main() -> None:
    enable_hang_diagnostics()
    try:
        render_drawing(parse_args())
    finally:
        faulthandler.cancel_dump_traceback_later()
    report_stage("Requesting Blender shutdown")
    bpy.ops.wm.quit_blender()


if __name__ == "__main__":
    main()
