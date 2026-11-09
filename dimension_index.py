"""Trace rendered linear dimension labels back to their Python call sites."""

import csv
import inspect
import json
import linecache
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

import ifcopenshell.util.element


INDEX_FIELDS = (
    "value", "drawing", "dimension", "source", "start", "end", "offset_m",
    "length_mm", "label", "guid", "callers", "code",
)


def capture_dimension_source(library_file):
    """Find the nearest caller outside the drawing library, without retaining frames."""
    library_file = Path(library_file).resolve()
    internal = {library_file, Path(__file__).resolve()}
    callers = []
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            raw_file = frame.f_code.co_filename
            if callers and raw_file.startswith("<"):
                break  # Stop at runpy/interactive execution wrappers.
            path = Path(raw_file).resolve()
            if path not in internal:
                if callers and not path.is_relative_to(library_file.parent):
                    break
                callers.append({
                    "file": raw_file if raw_file.startswith("<") else str(path),
                    "line": frame.f_lineno,
                    "function": frame.f_code.co_name,
                    "code": linecache.getline(raw_file, frame.f_lineno).strip(),
                })
            frame = frame.f_back
    finally:
        del frame
    if not callers:
        return {}
    first = callers[0]
    return {
        "SourceFile": first["file"], "SourceLine": first["line"],
        "SourceFunction": first["function"], "SourceCode": first["code"],
        "Callers": json.dumps(callers, ensure_ascii=False),
    }


def rendered_dimension_labels(svg_path):
    """Read Bonsai's line-ID / following-text pairs, including opening captions."""
    labels = []

    def tag(element):
        return element.tag.rsplit("}", 1)[-1]

    def visit(parent):
        children = list(parent)
        for index, element in enumerate(children):
            classes = element.get("class", "").split()
            if tag(element) == "line" and "PredefinedType-DIMENSION" in classes:
                guid = next((value[len("GlobalId-"):] for value in classes
                             if value.startswith("GlobalId-")), None)
                label_index = 0
                for sibling in children[index+1:]:
                    if tag(sibling) != "text" or not any(
                        "DIMENSION" in node.get("class", "").split() for node in sibling.iter()
                    ):
                        break
                    value = "".join(sibling.itertext()).strip()
                    if guid and value:
                        labels.append((guid, value, "length" if label_index == 0 else "description"))
                    label_index += 1
            visit(element)

    visit(ET.parse(svg_path).getroot())
    return labels


def write_dimension_rows(path, rows):
    """Atomically replace a UTF-8 TSV, including when no dimensions remain."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                            prefix=f".{path.name}-", delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            writer = csv.DictWriter(temporary, fieldnames=INDEX_FIELDS, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda row: (
                row["value"], row["drawing"], row["dimension"], row["guid"], row["label"],
            )))
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def write_dimension_index(svg_path, model, drawing):
    """Join visible SVG labels to IFC source metadata; never infer rounded labels."""
    rows = []
    for guid, value, label in rendered_dimension_labels(svg_path):
        try:
            dimension = model.by_guid(guid)
        except RuntimeError:
            continue
        if dimension is None:
            continue
        properties = ifcopenshell.util.element.get_pset(dimension, "BBIM_DimensionSource") or {}
        source_file = properties.get("SourceFile", "")
        source_line = properties.get("SourceLine", "")
        callers = json.loads(properties.get("Callers", "[]"))
        length = properties.get("Length")
        rows.append({
            "value": value, "drawing": drawing.Name or "", "dimension": dimension.Name or "",
            "source": f"{source_file}:{source_line}" if source_file and source_line else "",
            "start": properties.get("Start", ""), "end": properties.get("End", ""),
            "offset_m": properties.get("Offset", ""),
            "length_mm": f"{length*1000:.12g}" if length is not None else "",
            "label": label, "guid": guid,
            "callers": " -> ".join(f"{caller['file']}:{caller['line']}" for caller in callers
                                    if not caller["file"].startswith("<")),
            "code": properties.get("SourceCode", ""),
        })
    return write_dimension_rows(Path(svg_path).with_suffix(".dimensions.tsv"), rows)


def read_dimension_rows(svg_path):
    """Read an individual drawing index when composing a multi-drawing sheet."""
    path = Path(svg_path).with_suffix(".dimensions.tsv")
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))
