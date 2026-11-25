"""Compose the overview image and a cadastral-only map on the combined C.1-C.2 sheet."""

from __future__ import annotations

import argparse
from base64 import b64encode
from html import escape
import json
from math import degrees
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps
import shapefile
from shapely.geometry import Polygon
from shapely.ops import polylabel

from cadastral_situation import (
    DEFAULT_CADASTRE, HOUSE_COLOR, HOUSE_FILL, NorthUpFrame, ROOT,
    cadastral_parcel_area, layer_features, parcel_arrow_paths,
    WATER_LINE_COLOR, WATER_ADJUSTMENT_COLOR, GAS_LINE_COLOR, CETIN_LINE_COLOR, ELECTRIC_LINE_COLOR,
)
from drawing_title_block import load_title_block, title_block_svg
from pdf_utils import save_drawing_svg
from project_documents import DRAWINGS, document_path


DEFAULT_SVG = ROOT / "projekt2/situace_prehled.svg"
DEFAULT_PDF = ROOT / document_path("situace_prehled")
PARCELS = ("105", "106/1", "103/2")


def render_overview(*, image=ROOT / "lokalizace.jpg", source_map=ROOT / "projekt2/situace.svg",
                    cadastre=DEFAULT_CADASTRE, output=DEFAULT_SVG, pdf=DEFAULT_PDF):
    inkscape = shutil.which("inkscape")
    if inkscape is None:
        raise FileNotFoundError("Inkscape is required to export the overview PDF")
    source = ET.parse(source_map).getroot()
    metadata = json.loads(source.find("{http://www.w3.org/2000/svg}metadata[@id='situation-data']").text)
    frame = NorthUpFrame(**metadata["frame"])
    original_bounds = metadata["map_bounds_local_m"]
    centre = ((original_bounds[0] + original_bounds[2]) / 2,
              (original_bounds[1] + original_bounds[3]) / 2)
    # A3 landscape, two equally sized panels; reserve the bottom for the title block.
    map_x, map_y, map_w, map_h = 216, 28, 194, 190
    scale = 1000
    mm_per_m = 1000 / scale
    bounds = (centre[0] - map_w / mm_per_m / 2, centre[1] - map_h / mm_per_m / 2,
              centre[0] + map_w / mm_per_m / 2, centre[1] + map_h / mm_per_m / 2)
    corners = [frame.to_grid(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
    bbox = (min(p[0] for p in corners), min(p[1] for p in corners),
            max(p[0] for p in corners), max(p[1] for p in corners))
    highlighted = cadastral_parcel_area(cadastre, PARCELS, frame)
    if not (bounds[0] < highlighted.bounds[0] < highlighted.bounds[2] < bounds[2]
            and bounds[1] < highlighted.bounds[1] < highlighted.bounds[3] < bounds[3]):
        raise ValueError("The highlighted parcels must fit inside the cadastral map")

    def position(east, north):
        x, y = frame.to_local(east, north)
        return map_x + (x - bounds[0]) * mm_per_m, map_y + (bounds[3] - y) * mm_per_m

    def path(vertices, *, close=False):
        return "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in map(lambda p: position(*p), vertices)) + (" Z" if close else "")

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="420mm" height="297mm" viewBox="0 0 420 297">',
           '<rect width="420" height="297" fill="white"/>',
           '<style>text{font-family:DejaVu Sans,sans-serif;fill:#222;stroke:none}'
           '.map-label{paint-order:stroke;stroke:white;stroke-width:.5;stroke-linejoin:round}'
           'path{stroke-linejoin:round;stroke-linecap:round}</style>',
           f'<defs><clipPath id="cadastre-clip"><rect x="{map_x}" y="{map_y}" '
           f'width="{map_w}" height="{map_h}"/></clipPath>'
           f'<marker id="area-arrowhead" markerUnits="userSpaceOnUse" viewBox="0 0 5 4" '
           f'refX="5" refY="2" markerWidth="5" markerHeight="4" orient="auto">'
           f'<path d="M0,0L5,2L0,4Z" fill="{HOUSE_COLOR}"/></marker></defs>']

    def text(x, y, value, size=2.3, *, anchor="start", bold=False, attrs=""):
        svg.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" text-anchor="{anchor}" '
                   f'font-weight="{"bold" if bold else "normal"}" {attrs}>{escape(str(value))}</text>')

    text(107, 17, "C.1 Širší vztahy", 4.5, anchor="middle", bold=True)
    text(313, 17, "C.2 Katastrální situace", 4.5, anchor="middle", bold=True)
    # Embed the original JPEG, preserving its aspect ratio and avoiding external links.
    with Image.open(image) as overview:
        overview = ImageOps.exif_transpose(overview)
        width, height = overview.size
    factor = min(194 / width, 190 / height)
    image_w, image_h = width * factor, height * factor
    image_x = 10 + (194 - image_w) / 2
    # JPEGs without orientation changes can be embedded byte-for-byte.
    with Image.open(image) as original:
        orientation = original.getexif().get(274, 1)
    if orientation != 1:
        from io import BytesIO
        stream = BytesIO()
        overview.save(stream, format="PNG")
        payload, mime = stream.getvalue(), "image/png"
    else:
        payload, mime = image.read_bytes(), "image/jpeg"
    svg.append(f'<image id="overview-image" x="{image_x:g}" y="28" width="{image_w:g}" '
               f'height="{image_h:g}" preserveAspectRatio="xMidYMin meet" '
               f'xlink:href="data:{mime};base64,{b64encode(payload).decode()}"/>')
    svg.append(f'<rect x="{image_x:g}" y="28" width="{image_w:g}" height="{image_h:g}" '
               'fill="none" stroke="#333" stroke-width=".25"/>')
    svg.append('<path d="M210,10V220" fill="none" stroke="#bbb" stroke-width=".2"/>')
    svg.append('<g id="cadastral-map" clip-path="url(#cadastre-clip)">')
    for name, fill, stroke, line_width in (
        ("BUDOVY_P", "#e5e5e5", "#202020", .2),
        ("DALSI_PRVKY_MAPY_L", "none", "#909090", .12),
    ):
        svg.append(f'<g id="{name}" fill="{fill}" stroke="{stroke}" stroke-width="{line_width}">')
        for record, feature in layer_features(cadastre, name, bbox):
            if not feature.points:
                continue
            indices = [*feature.parts, len(feature.points)]
            d = " ".join(path(feature.points[a:b], close=feature.shapeType == shapefile.POLYGON)
                         for a, b in zip(indices, indices[1:]))
            svg.append(f'<path d="{d}" fill-rule="evenodd"/>')
        svg.append('</g>')
    polygons = highlighted.geoms if highlighted.geom_type == "MultiPolygon" else (highlighted,)
    d = " ".join(path([frame.to_grid(*p) for p in ring.coords], close=True)
                 for polygon in polygons for ring in (polygon.exterior, *polygon.interiors))
    svg.append(f'<path id="highlighted-parcels" d="{d}" fill="{HOUSE_FILL}" fill-opacity=".75" '
               f'fill-rule="evenodd" stroke="{HOUSE_COLOR}" stroke-width=".35">'
               '<title>Zájmové území – parcely 105, 106/1 a 103/2</title></path>')
    svg.append('<g id="parcel-boundaries" fill="none" stroke="#454545" stroke-width=".15">')
    for record, feature in layer_features(cadastre, "PARCELY_KN_P", bbox):
        indices = [*feature.parts, len(feature.points)]
        d = " ".join(path(feature.points[a:b], close=True) for a, b in zip(indices, indices[1:]))
        svg.append(f'<path d="{d}" fill-rule="evenodd"/>')
    svg.append('</g>')
    svg.append('<g id="parcel-leaders" fill="none" stroke="#202020" stroke-width=".13">')
    for record, feature in layer_features(cadastre, "PARCELY_KN_L", bbox):
        if str(record["TYPPPD_KOD"]) != "1032":
            continue
        indices = [*feature.parts, len(feature.points)]
        d = " ".join(path(feature.points[a:b]) for a, b in zip(indices, indices[1:]))
        svg.append(f'<path d="{d}"/>')
    for record, feature in layer_features(cadastre, "PARCELY_KN_B", bbox):
        if str(record["TYPPPD_KOD"]) != "1033" or not feature.points:
            continue
        shaft, head = parcel_arrow_paths(feature.points[0], float(record["ROTACE"] or 0),
                                         float(record["MERITKO"] or 1))
        svg.append(f'<path d="{path(shaft)} {path(head)}"/>')
    svg.append('</g>')
    for name, size in (("PARCELY_KN_T", 1.8), ("BUDOVY_DEF", 1.4), ("DALSI_PRVKY_MAPY_T", 1.7)):
        for record, feature in layer_features(cadastre, name, bbox):
            if not feature.points:
                continue
            x, y = position(*feature.points[0])
            if not (map_x + 2 < x < map_x + map_w - 2 and map_y + 2 < y < map_y + map_h - 2):
                continue
            if name == "PARCELY_KN_T":
                reference = record.get("VZ_BOD") or "BC"
                anchor = {"L": "start", "C": "middle", "R": "end"}[reference[1]]
                baseline = {"T": "text-before-edge", "C": "central", "B": "text-after-edge"}[reference[0]]
                angle = -float(record.get("ROTACE") or 0) - degrees(frame.north_angle)
                text(x, y, record["TEXT_KM"], size, anchor=anchor,
                     attrs=f'class="map-label" dominant-baseline="{baseline}" transform="rotate({angle:g} {x:g} {y:g})"')
            else:
                text(x, y, record["TEXT_KM"], size, anchor="middle", attrs='class="map-label"')
    # The cadastral panel includes the actual proposed footprint, the existing
    # supply networks and the connection identified in the coordination sheet.
    for key,color in (("water_routes",WATER_LINE_COLOR),("gas_routes",GAS_LINE_COLOR),
                      ("cetin_routes",CETIN_LINE_COLOR),("electric_routes",ELECTRIC_LINE_COLOR)):
        svg.append(f'<g id="overview-{key}" fill="none" stroke="{color}" stroke-width=".18">')
        for route in metadata[key]:
            adjusted=route.get('to_be_adjusted',False)
            dash=' stroke-dasharray="1.2,.6"' if adjusted or key=='cetin_routes' or route.get('installation')=='overhead' else ''
            tint=f' stroke="{WATER_ADJUSTMENT_COLOR}"' if adjusted else ''
            svg.append(f'<path d="{path(route["grid_points_m"])}"{dash}{tint}/>')
        svg.append('</g>')
    proposed=[(-y,-x) for y,x in metadata['house']['survey_corners']]
    centre_house=tuple(sum(p[i] for p in proposed)/4 for i in (0,1))
    svg.append(f'<path id="proposed-house" d="{path(proposed,close=True)}" fill="#efaaaa" stroke="{HOUSE_COLOR}" stroke-width=".5"/>')
    hx,hy=position(*centre_house)
    svg.append(f'<path d="M{hx-19:.3f},{hy-9:.3f}L{hx:.3f},{hy:.3f}" fill="none" stroke="{HOUSE_COLOR}" stroke-width=".25"/>')
    text(hx-19,hy-10,'Navrhovaný RD',2.3,anchor='middle',bold=True,attrs='class="map-label"')
    design=metadata.get('site_design')
    if design is None:
        raise ValueError('Regenerate C.3 before the overview: the site connection data is missing')
    nn=[frame.to_grid(*p) for p in design['proposed_nn_route_local_m']]
    svg.append(f'<path id="overview-nn-connection" d="{path(nn)}" fill="none" stroke="#b30032" stroke-width=".3" stroke-dasharray="1,.6"/>')
    entrances=[]
    for i,p in enumerate(design['existing_accesses_local_m'],1):
        grid=frame.to_grid(*p);x,y=position(*grid)
        svg.append(f'<circle id="overview-access-{i}" cx="{x:.3f}" cy="{y:.3f}" r=".9" fill="white" stroke="black" stroke-width=".2"/>')
        entrances.append(grid)
    footprint = Polygon([frame.to_local(*p) for p in proposed])
    arrow_area = highlighted.difference(footprint.buffer(5))
    areas = arrow_area.geoms if arrow_area.geom_type == 'MultiPolygon' else (arrow_area,)
    target = polylabel(max(areas,key=lambda area:area.area),tolerance=.02)
    target_paper = position(*frame.to_grid(target.x, target.y))
    label_x, label_y = map_x + map_w - 12, map_y + map_h * .79
    svg.append(f'<path id="interest-area-arrow" d="M{label_x-12:g},{label_y-4:g} '
               f'L{target_paper[0]:.3f},{target_paper[1]:.3f}" fill="none" '
               f'stroke="{HOUSE_COLOR}" stroke-width=".65" marker-end="url(#area-arrowhead)"/>')
    text(label_x, label_y, "Zájmové území", 3.5, anchor="end", bold=True,
         attrs='class="map-label" id="interest-area-label"')
    svg.append('<rect x="387" y="32" width="18" height="29" fill="white" fill-opacity=".9"/>')
    text(396, 38, "S", 3, anchor="middle", bold=True)
    svg.append('<path d="M396,56V42 M396,42L394,47L396,45L398,47Z" '
               'fill="black" stroke="black" stroke-width=".3"/>')
    svg.append('</g>')
    svg.append(f'<rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" '
               'fill="none" stroke="#333" stroke-width=".25"/>')
    text(216, 224, "Katastrální mapa 1:1000 · geografický sever nahoře", 2.1)
    text(10, 232, "Zájmové území: parcely 105, 106/1 a 103/2", 2.6, bold=True)
    text(10, 239, "k. ú. Lažánky u Blanska (679453)", 2.5)
    text(10,247,"Červený obrys: navrhovaný RD. Růžová plocha: řešené parcely.",2.3)
    for i,(label,color) in enumerate((("Vodovod",WATER_LINE_COLOR),("NN",ELECTRIC_LINE_COLOR),
                                    ("CETIN",CETIN_LINE_COLOR),("Plynovod",GAS_LINE_COLOR))):
        x=10+i*47
        svg.append(f'<path d="M{x},254h9" fill="none" stroke="{color}" stroke-width=".3"/>')
        text(x+12,255,label,2.1)
    text(10,263,"Napojení: stávající vodovod a NN; stávající sjezdy jsou zachovány.",2.3)
    text(10,270,"Přívod NN od stávajícího elektroměrového pilíře; plynová přípojka se nenavrhuje.",2.1)
    text(10,277,"Podrobné osazení, přípojky a výšky jsou uvedeny v C.3.",2.3)
    settings = load_title_block(output)
    if settings is not None:
        svg.append(title_block_svg(settings, filename=pdf.name, scale="1:1000*", paper="A3", x=330, y=228))
    text(10, 290, "* Měřítko platí pro katastrální mapu; přehledová mapa je bez určeného měřítka.", 2)
    info = {"highlighted_parcels": PARCELS, "highlight_geometry_local_m": highlighted.__geo_interface__,
            "frame": metadata["frame"], "map_bounds_local_m": bounds, "map_scale": scale,
            "overview_image": str(image), "cadastre": str(cadastre), "paper_mm": [420, 297],
            "proposed_house_grid_corners": proposed, "existing_access_grid_points": entrances,
            "proposed_nn_grid_points": nn, "interest_area_target_local_m": list(target.coords[0])}
    svg.append('<metadata id="overview-data">' + escape(json.dumps(info, ensure_ascii=False)) + '</metadata></svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(svg) + "\n", encoding="utf-8")
    sheet_path = save_drawing_svg(output, pdf)
    with TemporaryDirectory(prefix=".prehled-pdf-", dir=pdf.parent) as directory:
        temporary_pdf = Path(directory) / pdf.name
        subprocess.run([inkscape, str(sheet_path), f"--export-filename={temporary_pdf}",
                        "--export-type=pdf", "--export-area-page", "--batch-process"], check=True)
        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise RuntimeError("Inkscape did not create the overview PDF")
        temporary_pdf.replace(pdf)
    print(f"Overview: {pdf} (A3 landscape; cadastral map 1:{scale})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "lokalizace.jpg")
    parser.add_argument("--source-map", type=Path, default=ROOT / "projekt2/situace.svg")
    parser.add_argument("--cadastre", type=Path, default=DEFAULT_CADASTRE)
    parser.add_argument("--output", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    render_overview(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
