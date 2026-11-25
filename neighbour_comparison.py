"""Compose the live street elevation with two surveyed neighbour schematics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from html import escape
import json
from math import cos, radians, sin, sqrt
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

import ifcopenshell.util.element

from drawing_title_block import load_title_block, title_block_svg
from pdf_utils import save_drawing_svg
from project_documents import DRAWINGS, document_path
from survey_points import HOUSE_PLACEMENT, SurveyAxes, named_survey_groups, read_survey_groups, read_survey_points


ROOT = Path(__file__).resolve().parent
SVG_NS = "http://www.w3.org/2000/svg"
TITLE = DRAWINGS["sousede"].title
NUMBER = DRAWINGS["sousede"].number
SCALE = 150
LEFT_WIDTH = 16.8  # Overall width, including the open carport on the left.
LEFT_RIDGE_HEIGHT = 9.0  # Above point 94; the chimneys extend above the ridge.
LEFT_ROOF_FILL = "#c8c8c8"
RIGHT_WIDTH = 7.0
RIGHT_RIDGE_ELEVATION = 422.87
LEFT_ASSET = ROOT / "drawings/assets/neighbour-house-elevation.svg"
RIGHT_ASSET = ROOT / "drawings/assets/neighbour-gable-elevation.svg"
# Reference points are on the façades, not on the SVG canvas or gutter tips.
LEFT_REFERENCE = dict(left_x=-260.0, right_x=1270.0, base_y=825.0, ridge_y=-60.0, top_y=-156.0)
RIGHT_REFERENCE = dict(left_x=14.999917, right_x=413.039956, base_y=446.040039, ridge_y=15.0,
                       right_base_y=459.240051)


def projected_anchors(source=ROOT / "points.txt", house=HOUSE_PLACEMENT):
    """Orthographic horizontal stations along the proposed front façade."""
    groups = named_survey_groups(read_survey_groups(source))
    axes = SurveyAxes.from_polylines(groups["street"], groups["neighbour"])
    centre = axes.to_local(*house.center)
    angle = radians(house.angle_degrees)
    right, forward = (cos(angle), sin(angle)), (-sin(angle), cos(angle))
    points = {p.number:p for p in read_survey_points(source)}
    result = {}
    for number in ("94", "13"):
        point = points[number]
        local = axes.frame.to_local(point.y, point.x)
        delta = tuple(local[i]-centre[i] for i in (0,1))
        result[number] = dict(survey=asdict(point), station_m=sum(delta[i]*right[i] for i in (0,1)),
                              depth_m=sum(delta[i]*forward[i] for i in (0,1)))
    return result


def asset_matrix(anchor_xy, source_anchor, metres_per_unit, mm_per_m):
    """Positive screen Y maps downward from the specified surveyed bottom corner."""
    sx, sy = (v*mm_per_m for v in metres_per_unit)
    return sx, 0, 0, sy, anchor_xy[0]-sx*source_anchor[0], anchor_xy[1]-sy*source_anchor[1]


def embedded_asset(path, identifier, matrix, *, roof_fill=None):
    root = ET.parse(path).getroot()
    group = ET.Element(f"{{{SVG_NS}}}g",id=identifier,
                       transform="matrix("+" ".join(f"{v:.12g}" for v in matrix)+")")
    for child in root:
        if child.tag.rsplit("}",1)[-1] in {"title","desc","metadata"}:
            continue
        child = deepcopy(child)
        if child.get("id") == "ground-line":
            continue  # Joined in survey elevations on the composed sheet.
        if child.tag.rsplit("}",1)[-1] == "style":
            child.text = re.sub(r"([^{}]+)\{",lambda m:",".join(f"#{identifier} {s.strip()}" for s in m[1].split(","))+"{",child.text or "")
        for element in child.iter():
            if element.get("id"):
                element.set("id",f"{identifier}-{element.get('id')}")
        group.append(child)
    style = ET.SubElement(group,f"{{{SVG_NS}}}style")
    # Inkscape's PDF exporter inconsistently handles non-scaling strokes on
    # paths. Compensate for the affine scale explicitly for uniform linework.
    stroke_width = .13 / sqrt(abs(matrix[0] * matrix[3]))
    style.text = (f"#{identifier} path,#{identifier} rect,#{identifier} line"
                  f"{{stroke-width:{stroke_width:.12g} !important;vector-effect:none}}")
    if roof_fill is not None:
        for roof_id in ("main-roof", "left-wing-roof"):
            roof = group.find(f".//{{{SVG_NS}}}g[@id='{identifier}-{roof_id}']")
            if roof is not None:
                roof.find(f"{{{SVG_NS}}}path").set("style", f"fill:{roof_fill}")
    return group


def render_comparison(*, width, floor_z, floor_bpv, top_z,
                      street_terrain, create_view,
                      output=ROOT / "projekt2/sousede.svg", pdf=None):
    """Render only a new front view; compose neighbours at one shared Bpv datum."""
    output = Path(output)
    pdf = Path(pdf or ROOT / document_path("sousede"))
    anchors = projected_anchors()
    left, right = anchors["94"], anchors["13"]
    left_sx = LEFT_WIDTH/(LEFT_REFERENCE["right_x"]-LEFT_REFERENCE["left_x"])
    left_sy = LEFT_RIDGE_HEIGHT/(LEFT_REFERENCE["base_y"]-LEFT_REFERENCE["ridge_y"])
    right_sx = RIGHT_WIDTH/(RIGHT_REFERENCE["right_x"]-RIGHT_REFERENCE["left_x"])
    right_sy = (RIGHT_RIDGE_ELEVATION-right["survey"]["z"])/(RIGHT_REFERENCE["base_y"]-RIGHT_REFERENCE["ridge_y"])
    if right_sy <= 0:
        raise ValueError("Right neighbour's ridge must be above point 13")
    # Reuse the street elevation's walls and access pockets. Its uphill terrain
    # ends at the surveyed corner, rather than at the usual short slope segment.
    uphill_endpoint = (left["station_m"]+width/2, left["survey"]["z"])
    view = create_view(scale=SCALE, street_uphill_endpoint=uphill_endpoint)
    registrations = []
    for x,z in ((width/2,floor_z),(width/2+1,floor_z+1)):
        item = view.add_circle((x,z),.01,name="Comparison calibration")
        classes = ifcopenshell.util.element.get_pset(item,"EPset_Annotation","Classes")
        registrations.append(next(c for c in classes.split() if re.fullmatch(r"drawing-circle-\d+",c)))
    native_path = output.parent / "cache/comparison_front.svg"
    view.render(native_path,title="Podklad – čelní pohled",tables=False)
    root = ET.parse(native_path).getroot()
    ns = {"s":SVG_NS}
    marks = [next(e for e in root.findall('.//s:circle',ns) if token in e.get("class","").split())
             for token in registrations]
    native_floor = tuple(float(marks[0].get(k)) for k in ("cx","cy"))
    native_delta = tuple(float(marks[1].get(k))-native_floor[i] for i,k in enumerate(("cx","cy")))
    k = 1000/SCALE
    if abs(native_delta[0]-k) > .002 or abs(native_delta[1]+k) > .002:
        raise ValueError("Front-view registration does not match the comparison's horizontal/vertical scale")
    content = root.find('.//s:g[@class="drawing-title-content"]',ns)
    if content is None:
        raise ValueError("The native elevation is missing its drawing-content group")
    content = deepcopy(content)
    content.attrib.pop("transform",None)
    content.set("id","new-house-elevation")
    for parent in content.iter():
        for child in list(parent):
            if set(child.get("class","").split()).intersection(registrations):
                parent.remove(child)

    x_lo = left["station_m"]-LEFT_WIDTH-.6
    x_hi = right["station_m"]+RIGHT_WIDTH+.2
    station_zero_x = 210-(x_lo+x_hi)/2*k
    highest = max(left["survey"]["z"]+(LEFT_REFERENCE["base_y"]-LEFT_REFERENCE["top_y"])*left_sy,
                  top_z-floor_z+floor_bpv,RIGHT_RIDGE_ELEVATION)
    top_elevation = highest+1.6

    def paper(x,z):
        return station_zero_x+x*k,42+(top_elevation-z)*k

    paper_floor = paper(0,floor_bpv)
    content.set("transform",f"translate({paper_floor[0]-native_floor[0]:.12g} {paper_floor[1]-native_floor[1]:.12g})")
    left_matrix = asset_matrix(paper(left["station_m"],left["survey"]["z"]),
                              (LEFT_REFERENCE["right_x"],LEFT_REFERENCE["base_y"]),(left_sx,left_sy),k)
    right_matrix = asset_matrix(paper(right["station_m"],right["survey"]["z"]),
                               (RIGHT_REFERENCE["left_x"],RIGHT_REFERENCE["base_y"]),(right_sx,right_sy),k)
    ET.register_namespace("",SVG_NS)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             'width="420mm" height="297mm" viewBox="0 0 420 297">',
             '<rect width="420" height="297" fill="white"/>',
             '<style>.comparison-text{font-family:DejaVu Sans,sans-serif;fill:black;stroke:none}'
             '.comparison-halo{paint-order:stroke;stroke:white;stroke-width:1;stroke-linejoin:round}</style>']

    def text(x,y,value,size=2.6,*,anchor="start",bold=False,halo=False):
        parts.append(f'<text class="comparison-text{" comparison-halo" if halo else ""}" '
                     f'x="{x:g}" y="{y:g}" font-size="{size:g}" text-anchor="{anchor}" '
                     f'font-weight="{"bold" if bold else "normal"}">{escape(str(value))}</text>')

    text(210,15,f"{NUMBER}. {TITLE}  1:{SCALE}",4.1,anchor="middle",bold=True)
    text(210,23,"Pohled kolmo k čelní fasádě navrhovaného RD",2.8,anchor="middle")
    parts.append(ET.tostring(content,encoding="unicode"))
    parts.append(ET.tostring(embedded_asset(LEFT_ASSET,"left-house",left_matrix,
                                          roof_fill=LEFT_ROOF_FILL),encoding="unicode"))
    parts.append(ET.tostring(embedded_asset(RIGHT_ASSET,"right-house",right_matrix),encoding="unicode"))
    # Ground between the surveyed corners and the street-side house corners.
    profile = [(left["station_m"]-LEFT_WIDTH,left["survey"]["z"]),
               (left["station_m"],left["survey"]["z"]),
               (-width/2,street_terrain[0][1]),(width/2,street_terrain[-1][1]),
               (right["station_m"],right["survey"]["z"]),
               (right["station_m"]+RIGHT_WIDTH,
                right["survey"]["z"]-(RIGHT_REFERENCE["right_base_y"]-RIGHT_REFERENCE["base_y"])*right_sy)]
    for first,last in ((profile[0],profile[1]),(profile[3],profile[4]),(profile[4],profile[5])):
        x1,y1=paper(*first);x2,y2=paper(*last)
        parts.append(f'<path d="M{x1:g},{y1:g}L{x2:g},{y2:g}" fill="none" stroke="black" stroke-width=".2"/>')
    left_ridge = left["survey"]["z"]+LEFT_RIDGE_HEIGHT
    label_y = max(paper(0,414)[1]+13,177)
    for x,label,detail in ((left["station_m"]-LEFT_WIDTH/2,"Levý sousední RD",
                           f"Celková šířka {LEFT_WIDTH:g} m".replace(".", ",")),
                           (0,"Navrhovaný RD",f"±0,000 = {floor_bpv:.3f} m Bpv"),
                           (right["station_m"]+RIGHT_WIDTH/2,"Pravý sousední RD","Šířka přibližně 7 m")):
        xx,_=paper(x,0)
        text(xx,label_y,label,3.0,anchor="middle",bold=True)
        text(xx,label_y+6,detail,2.5,anchor="middle")
    for x,elevation,label in ((left["station_m"]-3.5,left_ridge,"Hřeben"),
                              (0,top_z-floor_z+floor_bpv,"Komín navrhovaného RD"),
                              (right["station_m"]+RIGHT_WIDTH/2,RIGHT_RIDGE_ELEVATION,"Hřeben")):
        xx,yy=paper(x,elevation)
        parts.append(f'<path d="M{xx-5:g},{yy:g}h10" fill="none" stroke="black" stroke-width=".15"/>')
        text(xx,yy-2,f"{elevation:.3f} m Bpv",2.5,anchor="middle",halo=True)
        text(xx,yy-6,label,2.2,anchor="middle",halo=True)
    for number in ("94","13"):
        anchor=anchors[number];xx,yy=paper(anchor["station_m"],anchor["survey"]["z"])
        parts.append(f'<circle cx="{xx:g}" cy="{yy:g}" r=".65" fill="white" stroke="black" stroke-width=".2"/>')
        text(xx,yy+5,f"Roh fasády: {anchor['survey']['z']:.3f} m Bpv",2.3,anchor="middle",halo=True)
    text(15,214,"Výšky jsou ve společném systému Bpv; půdorysné polohy jsou promítnuty do směru fasády.",2.4)
    text(15,221,"Sousední domy jsou schematické. Jejich šířky a natočení jsou orientační.",2.4)
    text(15,228,"Levý RD: pravý dolní roh fasády; hřeben 9,00 m nad rohem; komíny nad hřebenem.",2.4)
    text(15,235,"Pravý RD: levý dolní roh fasády; hřeben 422,87 m Bpv.",2.4)
    settings=load_title_block(output)
    if settings is not None:
        parts.append(title_block_svg(settings,filename=pdf.name,scale=f"1:{SCALE}",paper="A3",x=330,y=228))
    metadata=dict(scale=SCALE,paper_mm=[420,297],house_placement=asdict(HOUSE_PLACEMENT),anchors=anchors,
                  left=dict(width_m=LEFT_WIDTH,ridge_height_above_anchor_m=LEFT_RIDGE_HEIGHT,ridge_elevation_bpv=left_ridge,
                            source_reference=LEFT_REFERENCE,matrix=left_matrix),
                  right=dict(width_m=RIGHT_WIDTH,ridge_elevation_bpv=RIGHT_RIDGE_ELEVATION,
                             source_reference=RIGHT_REFERENCE,matrix=right_matrix),
                  proposed=dict(floor_elevation_bpv=floor_bpv,top_elevation_bpv=top_z-floor_z+floor_bpv,
                                street_uphill_endpoint=uphill_endpoint,
                                native_registration_mm=native_floor,registration_step_mm=native_delta))
    parts.append('<metadata id="comparison-data">'+escape(json.dumps(metadata,ensure_ascii=False))+'</metadata></svg>')
    output.parent.mkdir(parents=True,exist_ok=True);pdf.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(re.sub(r"(?m)[ \t]+$", "", "\n".join(parts))+"\n",encoding="utf-8")
    inkscape=shutil.which("inkscape")
    if inkscape is None:
        raise FileNotFoundError("Inkscape is required to export the comparison PDF")
    sheet_path = save_drawing_svg(output, pdf)
    with TemporaryDirectory(prefix=".neighbours-pdf-",dir=pdf.parent) as directory:
        target=Path(directory)/pdf.name
        subprocess.run([inkscape,str(sheet_path),f"--export-filename={target}","--export-type=pdf","--export-area-page","--batch-process"],check=True)
        if not target.is_file() or target.stat().st_size==0:
            raise RuntimeError("Inkscape did not create the comparison PDF")
        target.replace(pdf)
    print(f"Neighbour comparison: {pdf}")
    print(f"Left: point 94 at {left['survey']['z']:.3f} m Bpv; ridge {left_ridge:.3f} m; width {LEFT_WIDTH:g} m")
    print(f"Right: point 13 at {right['survey']['z']:.3f} m Bpv; ridge {RIGHT_RIDGE_ELEVATION:.3f} m; width {RIGHT_WIDTH:g} m")
    return output
