"""Compose independently styled vector drawings on a scale-preserving sheet."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

import tinycss2
from tinycss2.serializer import serialize_string_value

if TYPE_CHECKING:
    from ifc_utils import Drawing

_SVG = "http://www.w3.org/2000/svg"
_XLINK = "http://www.w3.org/1999/xlink"
_URL = re.compile(r"url\(\s*(['\"]?)#([^)'\"\s]+)\1\s*\)")


def _urls(value, prefix):
    return _URL.sub(lambda match: f"url(#{prefix}{match[2]})", value)


def _selector(tokens, prefix):
    """Namespace IDs, including marker prefix selectors and nested :not()."""
    for token in tokens:
        if token.type == "hash" and token.is_identifier:
            token.value = prefix + token.value
        elif token.type == "[] block":
            values = [item for item in token.content if item.type not in {"whitespace", "comment"}]
            if len(values) >= 3 and values[0].type == "ident":
                attribute, value = values[0].value, values[2]
                if value.type in {"string", "ident"}:
                    if attribute == "id":
                        value.value = prefix + value.value
                    elif attribute in {"href", "xlink:href"} and value.value.startswith("#"):
                        value.value = "#" + prefix + value.value[1:]
                    if value.type == "string":
                        value.representation = '"' + serialize_string_value(value.value) + '"'
        elif token.type == "function":
            _selector(token.arguments, prefix)


def _scoped_css(css, scope, prefix):
    """Isolate native drawing styles; a nested SVG alone does not scope CSS."""
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    output = []
    for rule in rules:
        if rule.type == "qualified-rule":
            _selector(rule.prelude, prefix)
            selectors, current = [], []
            for token in rule.prelude:
                if token.type == "literal" and token.value == ",":
                    selectors.append(tinycss2.serialize(current).strip())
                    current = []
                else:
                    current.append(token)
            selectors.append(tinycss2.serialize(current).strip())
            prelude = ", ".join(f"#{scope} {selector}" for selector in selectors)
            output.append(prelude + " {" + _urls(tinycss2.serialize(rule.content), prefix) + "}")
        elif rule.type == "at-rule" and rule.lower_at_keyword in {"media", "supports", "layer"} and rule.content is not None:
            output.append("@" + rule.at_keyword + " " + tinycss2.serialize(rule.prelude).strip()
                          + " {" + _scoped_css(tinycss2.serialize(rule.content), scope, prefix) + "}")
        else:
            raise ValueError("Drawing sheets support ordinary SVG CSS rules and @media/@supports/@layer only")
    return "\n".join(output)


def _namespace(root, index, source_dir):
    scope, prefix = f"sheet-drawing-{index}", f"sheet-{index}-"
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                element.set(key, prefix + value)
            elif key in {"href", f"{{{_XLINK}}}href"}:
                if value.startswith("#"):
                    element.set(key, "#" + prefix + value[1:])
                elif value and not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", value):
                    element.set(key, (source_dir / value).resolve().as_uri())
            else:
                element.set(key, _urls(value, prefix))
        if element.tag == f"{{{_SVG}}}style" and element.text:
            element.text = _scoped_css(element.text, scope, prefix)
    wrapper = ET.Element(f"{{{_SVG}}}g", {"id": scope})
    wrapper.append(root)
    return wrapper


def _write_svg(root, path):
    ET.register_namespace("", _SVG)
    ET.register_namespace("xlink", _XLINK)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _content_bounds(root, path, inkscape, physical, view_box):
    """Ask the SVG renderer for painted bounds, including text and markers."""
    identifier = root.get("id")
    if identifier is None:
        identifier = "sheet-crop-query"
        identifiers = {e.get("id") for e in root.iter()}
        while identifier in identifiers:
            identifier += "-root"
        root.set("id", identifier)
    _write_svg(root, path)
    result = subprocess.run(
        [inkscape, str(path), f"--query-id={identifier}", "--query-x", "--query-y", "--query-width", "--query-height"],
        check=True, capture_output=True, text=True,
    )
    try:
        x, y, width, height = map(float, result.stdout.split())
    except ValueError:
        raise ValueError("Inkscape did not return a drawing's painted bounds") from None
    if not all(isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
        raise ValueError("Cannot crop an empty drawing")
    sx, sy = view_box[2] / (physical[0] * 96 / 25.4), view_box[3] / (physical[1] * 96 / 25.4)
    return view_box[0] + x * sx, view_box[1] + y * sy, width * sx, height * sy


def _crop(root, path, inkscape, physical, view_box, padding):
    units = view_box[2] / physical[0]
    # Move the title next to the cropped content. Otherwise the old camera's
    # empty space between its header and geometry would defeat tight cropping.
    titles = [(parent, child) for parent in root.iter() for child in parent
              if "drawing-title" in child.get("class", "").split()]
    for parent, title in titles:
        parent.remove(title)
    x, y, width, height = _content_bounds(root, path, inkscape, physical, view_box)
    for parent, title in titles:
        title.set("x", f"{x + width / 2:.12g}")
        title.set("y", f"{y - 3.5 * units:.12g}")
        parent.append(title)
    if titles:
        x, y, width, height = _content_bounds(root, path, inkscape, physical, view_box)
    pad = padding * units
    root.set("viewBox", f"{x - pad:.12g} {y - pad:.12g} {width + 2 * pad:.12g} {height + 2 * pad:.12g}")
    width, height = width / units + 2 * padding, height / units + 2 * padding
    root.set("width", f"{width:.12g}mm")
    root.set("height", f"{height:.12g}mm")
    return width, height


@dataclass(frozen=True)
class _SheetDrawing:
    drawing: Drawing
    x: float
    y: float
    title: str | None
    tables: bool
    crop: bool


class DrawingSheet:
    """One physical SVG/PDF page with manually placed, unscaled drawings.

    X/Y are centres in [0, 1] across the WHOLE page, from left/top to right/
    bottom, not fractions of the printable area. A centre at the page edge
    usually overflows; render() rejects placements crossing the chosen margins.
    Manual overlaps are allowed. No automatic fitting or rearrangement occurs.
    """

    def __init__(self, *, paper="A4", orientation="landscape", margin=10, padding=2):
        from ifc_utils import _drawing_pdf_options, _number
        _, self.width, self.height, self.margin = _drawing_pdf_options(None, paper, orientation, margin)
        self.paper, self.orientation = paper, orientation
        self.padding = _number(padding, "padding")
        if self.padding < 0:
            raise ValueError("padding must not be negative")
        self._drawings = []

    def add(self, drawing, *, x, y, title=None, tables=True, crop=True):
        from ifc_utils import Drawing, _name, _number
        if not isinstance(drawing, Drawing):
            raise TypeError("drawing must be a Drawing")
        x, y = _number(x, "x"), _number(y, "y")
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError("drawing centre x/y must be between 0 and 1")
        if not isinstance(tables, bool) or not isinstance(crop, bool):
            raise TypeError("tables and crop must be booleans")
        title = _name(title, "title") if title is not None else None
        self._drawings.append(_SheetDrawing(drawing, x, y, title, tables, crop))
        return self

    def render(self, output, *, pdf=None, blender="blender", inkscape="inkscape"):
        from ifc_utils import _drawing_pdf_options, _drawing_svg_frame, _export_drawing_pdf, _render_existing_drawing
        output = Path(output)
        if output.suffix.lower() != ".svg":
            raise ValueError("sheet output must use the .svg extension")
        _drawing_pdf_options(pdf, self.paper, self.orientation, 0)
        if not self._drawings:
            raise ValueError("a drawing sheet must contain at least one drawing")
        for item in self._drawings:
            if item.drawing.house._ifc_path is None:
                raise RuntimeError("write each house before rendering a drawing sheet")
        inkscape_command = shutil.which(str(inkscape))
        if inkscape_command is None and (any(item.crop for item in self._drawings) or pdf is not None):
            raise FileNotFoundError(f"Inkscape executable not found: {inkscape}")
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet = ET.Element(f"{{{_SVG}}}svg", {
            "width": f"{self.width:g}mm", "height": f"{self.height:g}mm",
            "viewBox": f"0 0 {self.width:g} {self.height:g}",
        })
        ET.SubElement(sheet, f"{{{_SVG}}}rect", {"width": f"{self.width:g}", "height": f"{self.height:g}", "fill": "white"})
        with TemporaryDirectory(prefix="drawing-sheet-") as directory:
            directory = Path(directory)
            models = {}
            for index, item in enumerate(self._drawings, 1):
                house = item.drawing.house
                if house not in models:
                    # Persist current drawings as normal, but render an isolated
                    # copy: never redirect live IFC document links to temp SVGs.
                    house._write_model(house._ifc_path)
                    models[house] = directory / f"house-{len(models) + 1}.ifc"
                    shutil.copyfile(house._ifc_path, models[house])
                path = directory / f"drawing-{index}.svg"
                _render_existing_drawing(
                    models[house], item.drawing.element.GlobalId, path,
                    png=False, png_dpi=200, blender=blender, inkscape=inkscape,
                    title=item.title if item.title is not None else item.drawing.name,
                    tables=item.tables,
                )
                _, width, height, view_box = _drawing_svg_frame(path.read_text())
                if not isclose(view_box[2] / width, view_box[3] / height, rel_tol=1e-9):
                    raise ValueError("a sheet drawing must have a uniform physical SVG scale")
                root = ET.parse(path).getroot()
                if item.crop:
                    width, height = _crop(root, path, inkscape_command, (width, height), view_box, self.padding)
                x, y = item.x * self.width - width / 2, item.y * self.height - height / 2
                if min(x, y) < self.margin - 1e-6 or x + width > self.width - self.margin + 1e-6 \
                        or y + height > self.height - self.margin + 1e-6:
                    raise ValueError(f"Drawing {item.drawing.name!r} ({width:.1f} × {height:.1f} mm) at "
                                     f"({item.x:g}, {item.y:g}) crosses the sheet margins; move its centre "
                                     "or choose larger paper. Drawings will not be scaled.")
                root.set("width", f"{width:.12g}")
                root.set("height", f"{height:.12g}")
                root.set("x", f"{x:.12g}")
                root.set("y", f"{y:.12g}")
                sheet.append(_namespace(root, index, path.parent))
            with NamedTemporaryFile(suffix=".svg", dir=output.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
            try:
                _write_svg(sheet, temporary_path)
                temporary_path.replace(output)
            finally:
                temporary_path.unlink(missing_ok=True)
        if pdf is not None:
            _export_drawing_pdf(output, pdf, paper=self.paper, orientation=self.orientation, margin=0, inkscape=inkscape)
        return output
