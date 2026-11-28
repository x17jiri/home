"""Reproducible, simplified winter heat-loss budget from the current house model.

This is a steady-state screening calculation, not an EN 12831 calculation.
Run with .venv-pdf/bin/python heating_loss.py. No drawings are regenerated.
"""

import argparse
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from math import ceil, hypot
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as element
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from project_documents import PROJECT_DIR, VYT
from roof_frame_3d import HouseInputs
from ventilation_airflow import upper_ceiling_profile, volume_under_ceiling


LG_SOURCE = "https://www.lg.com/content/dam/channel/wcms/hu/business/download/airsolution/2021_THERMA_V_%28AWHP%29_R32_Split_R410A_Split_leaflet_0302_FIN_20211102_223018918_.pdf"
IVAR_SOURCE = "https://www.ivarcs.cz/storage/Folder_File/82001-84000/360054f7-d649-40dc-bfc5-9bfc64f13a35_file_cstl-ivar-sl-fancoil.pdf"
METHOD_SOURCE = "https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch17/F21_Ch17_si.aspx"
SUPPLIES = {"0.01": 40, "0.02": 40, "0.03": 40, "1.01": 120}
FCUS = {"0.01": ("SL 600 DC", 3020), "0.02": ("SL 600 DC", 3020),
        "0.03": ("SL 600 DC", 3020), "0.05": ("SL 400 DC", 2210),
        "1.01": ("SL 1000 DC", 4320)}


@dataclass(frozen=True)
class Assumptions:
    indoor_c: float = 20
    outdoor_c: float = -15
    basement_c: float = -15
    recovery: float = .77
    ventilation_m3_h: float = 240
    infiltration_ach: float = .10  # Operational ACH, NOT a blower-door n50.
    bridge_delta_u: float = .05
    window_u: float = 1.2
    door_u: float = 1.5
    timber_fraction: float = .10
    timber_lambda: float = .18
    insulation_lambda_factor: float = 1.0

    def __post_init__(self):
        if not 0 <= self.recovery <= 1 or not 0 <= self.timber_fraction < 1:
            raise ValueError("Invalid recovery or timber fraction")
        if min(self.ventilation_m3_h, self.infiltration_ach, self.bridge_delta_u) < 0:
            raise ValueError("Negative airflow or thermal-bridge allowance")
        if min(self.window_u, self.door_u, self.timber_lambda, self.insulation_lambda_factor) <= 0:
            raise ValueError("U-values and conductivities must be positive")
        if max(self.outdoor_c, self.basement_c) > self.indoor_c:
            raise ValueError("This winter calculation requires nonnegative temperature differences")


def partition_plan(footprints, envelope, cell_size=.10):
    """Keep clear room areas; assign remaining walls/voids to the nearest room.

    Only the residual area uses a grid, at most 100 mm. Changing this grid affects
    the room allocation, not the exact house envelope or total heat loss.
    """
    if cell_size <= 0:
        raise ValueError("Cell size must be positive")
    rooms = sorted(footprints)
    parts = {room: [footprints[room].intersection(envelope)] for room in rooms}
    occupied = unary_union([part[0] for part in parts.values()])
    if sum(part[0].area for part in parts.values())-occupied.area > 1e-7:
        raise ValueError("Room footprints overlap")
    residual = envelope.difference(occupied)
    xmin, ymin, xmax, ymax = envelope.bounds
    nx, ny = ceil((xmax-xmin)/cell_size), ceil((ymax-ymin)/cell_size)
    # Put grid edges on both house axes so mirrored rooms are treated equally.
    nx, ny = nx+nx % 2, ny+ny % 2
    dx, dy = (xmax-xmin)/nx, (ymax-ymin)/ny
    for ix in range(nx):
        for iy in range(ny):
            cell = residual.intersection(box(xmin+ix*dx, ymin+iy*dy,
                                            xmin+(ix+1)*dx, ymin+(iy+1)*dy))
            if cell.area <= 1e-12:
                continue
            point = cell.centroid
            nearest = min(rooms, key=lambda room: (footprints[room].distance(point), room))
            parts[nearest].append(cell)
    zones = {room: unary_union(pieces) for room, pieces in parts.items()}
    if abs(sum(zone.area for zone in zones.values())-envelope.area) > 1e-7:
        raise ValueError("Room allocation does not cover the house exactly")
    return zones


def profile_height(profile, x):
    for (x0, z0), (x1, z1) in zip(profile, profile[1:]):
        if x0-1e-9 <= x <= x1+1e-9:
            return z0+(z1-z0)*(x-x0)/(x1-x0)
    raise ValueError("X lies outside the ceiling profile")


def wall_area(zone, width, depth, floor_z, profile):
    """Integrate exterior wall height, including gables, on a room's boundary."""
    area = 0.0
    for x in (0, width):
        edge = zone.intersection(LineString([(x, 0), (x, depth)]))
        area += edge.length*(profile_height(profile, x)-floor_z)
    for y in (0, depth):
        for (x0, z0), (x1, z1) in zip(profile, profile[1:]):
            edge = zone.intersection(LineString([(x0, y), (x1, y)]))
            if edge.length:
                area += edge.length*(z0+(z1-z0)*(edge.centroid.x-x0)/(x1-x0)-floor_z)
    return area


def roof_areas(zone, profile, depth):
    sloped, flat = 0.0, 0.0
    for (x0, z0), (x1, z1) in zip(profile, profile[1:]):
        projected = zone.intersection(box(x0, 0, x1, depth)).area
        if abs(z1-z0) < 1e-9:
            flat += projected
        else:
            sloped += projected*hypot(x1-x0, z1-z0)/(x1-x0)
    return sloped, flat


def opening_size(model_opening):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, model_opening)
    vertices = np.array(shape.geometry.verts).reshape((-1, 3))
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    # All facade openings in the current model are axis-aligned.
    size = high-low
    if min(size) <= 0:
        raise ValueError("Invalid exterior opening")
    return dict(area_m2=float(max(size[:2])*size[2]),
                width_m=float(max(size[:2])), height_m=float(size[2]),
                center_xy=((low+high)/2)[:2].tolist())


def read_geometry(source, ifc, cell_size=.10):
    source, ifc = Path(source), Path(ifc)
    if ifc.stat().st_mtime_ns < source.stat().st_mtime_ns:
        raise ValueError("IFC predates house2.py; regenerate one drawing to update the model")
    inputs = HouseInputs(source)
    g = inputs.get
    model = ifcopenshell.open(ifc)
    width, depth = g("HOUSE_WIDTH"), g("HOUSE_DEPTH")
    envelope = box(0, 0, width, depth)
    rooms, board = {}, None
    for slab in model.by_type("IfcSlab"):
        ps = element.get_pset(slab, "BBIM_FloorLayer") or {}
        room = ps.get("RoomIdentifier", "")
        if slab.Name == "Timber board over basement stair opening":
            board = Polygon(json.loads(ps["Outline"]))
        if not room.startswith(("0.", "1.")):
            continue
        if room in rooms:
            raise ValueError(f"Multiple room floor records: {room}")
        polygon = Polygon(json.loads(ps["Outline"]))
        storey_z = float(element.get_container(slab).Elevation)
        floor_z = storey_z+ps["StartHeight"]+ps["Thickness"]
        expected = g("GROUND_FLOOR_THICKNESS") if room.startswith("0.") else g("UPPER_FINISHED_FLOOR_HEIGHT")
        if abs(floor_z-expected) > 1e-8:
            raise ValueError(f"Source/IFC finished-floor mismatch in {room}")
        rooms[room] = dict(name=slab.Name, footprint=polygon, floor_z=floor_z,
                           clear_floor_area_m2=ps["Area"])
    if set(rooms) != {"0.01", "0.02", "0.03", "0.04", "0.05", "1.01", "1.02", "1.03"}:
        raise ValueError("Room list changed; update emitter and ventilation assignments")
    if board is None:
        raise ValueError("Under-stairs floor board not found")
    for prefix in ("0.", "1."):
        footprints = {r: v["footprint"] for r, v in rooms.items() if r.startswith(prefix)}
        if prefix == "0.":
            footprints["0.04"] = footprints["0.04"].union(board)
        else:
            # Upper floor void: heated staircase, not an outdoor roof opening.
            stairs = box(g("UPPER_STAIRWAY_WALL_X"), g("FRONT_WALL_THICKNESS"),
                         g("STAIR_RIGHT_X"), g("STAIR_UPPER_END_Y"))
            footprints["1.03"] = footprints["1.03"].union(stairs.difference(
                unary_union(list(footprints.values()))))
        for room, zone in partition_plan(footprints, envelope, cell_size).items():
            rooms[room]["zone"] = zone
    openings = []
    for product in [*model.by_type("IfcWindow"), *model.by_type("IfcDoor")]:
        storey = element.get_container(product)
        if storey is None or float(storey.Elevation) < -.001:
            continue
        if product.is_a("IfcDoor") and product.Name != "Entrance door":
            continue
        op = opening_size(product.FillsVoids[0].RelatingOpeningElement)
        prefix = "0." if float(storey.Elevation) < .001 else "1."
        candidates = [r for r in rooms if r.startswith(prefix)]
        point = Point(op["center_xy"])
        room = min(candidates, key=lambda r: rooms[r]["zone"].distance(point))
        openings.append(dict(name=product.Name, room=room,
                             kind="window" if product.is_a("IfcWindow") else "door", **op))
    profile = upper_ceiling_profile(inputs)
    ground_floor = g("GROUND_FLOOR_THICKNESS")
    upper_floor = g("UPPER_FINISHED_FLOOR_HEIGHT")
    for room, data in rooms.items():
        ground = room.startswith("0.")
        zone = data["zone"]
        storey_profile = [(0, upper_floor), (width, upper_floor)] if ground else profile
        data["wall_gross_m2"] = wall_area(zone, width, depth, data["floor_z"], storey_profile)
        data["roof_sloped_m2"], data["roof_flat_m2"] = (0, 0) if ground else roof_areas(zone, profile, depth)
        data["floor_stair_m2"] = zone.intersection(board).area if ground else 0
        data["floor_regular_m2"] = zone.area-data["floor_stair_m2"] if ground else 0
        data["gross_volume_m3"] = volume_under_ceiling(zone, data["floor_z"], storey_profile)
        data["zone_area_m2"] = zone.area
        for kind in ("window", "door"):
            data[f"{kind}_m2"] = sum(o["area_m2"] for o in openings if o["room"] == room and o["kind"] == kind)
        data["wall_net_m2"] = data["wall_gross_m2"]-data["window_m2"]-data["door_m2"]
        if data["wall_net_m2"] < -1e-8:
            raise ValueError(f"Openings exceed allocated wall area in {room}")
    # Independent full-envelope checks: allocation must not change any house total.
    expected_wall = wall_area(envelope, width, depth, ground_floor, profile)
    expected_volume = volume_under_ceiling(envelope, ground_floor, profile)
    for key, expected in (("wall_gross_m2", expected_wall), ("gross_volume_m3", expected_volume),
                          ("floor_regular_m2", envelope.area-board.area)):
        if abs(sum(v[key] for v in rooms.values())-expected) > 1e-6:
            raise ValueError(f"Room allocations do not reconcile: {key}")
    return dict(inputs=inputs, rooms=rooms, openings=openings, width_m=width, depth_m=depth,
                profile=profile, cell_size_m=cell_size)


def u_values(inputs, assumptions):
    g, a = inputs.get, assumptions
    conductivities = {key: value*a.insulation_lambda_factor
                      for key, value in g("INSULATION_LAMBDA_D_MAX").items()}
    # Parallel conductivity within each insulation layer: deliberately conservative.
    roof_lambda = (1-a.timber_fraction)*conductivities["roof_wool"]+a.timber_fraction*a.timber_lambda
    floor_wool = .03  # SK3 divides the model's combined 150 mm into 120+30 mm.
    return dict(
        wall=1/(g("FACADE_INSULATION_THICKNESS")/conductivities["facade_wool"]+.13+.04),
        roof_sloped=1/((g("RAFTER_HEIGHT")+g("THERMAL_INSULATION_UNDER_RAFTERS"))/roof_lambda+.10+.04),
        # Treat the space above the horizontal ceiling as cold/ventilated.
        # Do not count its additional, remote between-rafter insulation.
        roof_flat=1/(g("THERMAL_INSULATION_UNDER_RAFTERS")/roof_lambda+.10+.04),
        floor_regular=1/((g("GROUND_FLOOR_INSULATION_THICKNESS")-floor_wool)/conductivities["floor_eps"]
                        +floor_wool/conductivities["floor_wool"]+.17+.17),
        floor_stair=1/(g("GROUND_STAIR_OPENING_INSULATION_THICKNESS")/conductivities["stair_floor_wool"]+.17+.17),
        window=a.window_u, door=a.door_u,
    )


def calculate(geometry, assumptions=Assumptions()):
    a = assumptions
    u = u_values(geometry["inputs"], a)
    outdoor_delta, basement_delta = a.indoor_c-a.outdoor_c, a.indoor_c-a.basement_c
    results = {}
    for room, geom in geometry["rooms"].items():
        components = {}
        for key in ("wall_net", "window", "door", "roof_sloped", "roof_flat"):
            components[key] = geom[f"{key}_m2"]*u["wall" if key == "wall_net" else key]*outdoor_delta
        for key in ("floor_regular", "floor_stair"):
            components[key] = geom[f"{key}_m2"]*u[key]*basement_delta
        exposed_area = sum(geom[f"{key}_m2"] for key in (
            "wall_gross", "roof_sloped", "roof_flat", "floor_regular", "floor_stair"))
        # Use outdoor delta also for the floor bridge allowance: conservative when basement is warmer.
        components["bridges"] = exposed_area*a.bridge_delta_u*outdoor_delta
        components["infiltration"] = .34*a.infiltration_ach*geom["gross_volume_m3"]*outdoor_delta
        supply = SUPPLIES.get(room, 0)*a.ventilation_m3_h/sum(SUPPLIES.values())
        components["ventilation"] = .34*supply*(1-a.recovery)*outdoor_delta
        results[room] = dict(name=geom["name"], components_w=components,
                             total_w=sum(components.values()), supply_m3_h=supply)
    totals = {key: sum(room["components_w"][key] for room in results.values())
              for key in next(iter(results.values()))["components_w"]}
    return dict(assumptions=asdict(a), u_w_m2k=u, rooms=results, components_w=totals,
                total_w=sum(totals.values()))


def emitter_budgets(geometry, result):
    """Apportion common-space loss; this does NOT prove heat transfer to it."""
    budgets = {}
    ground_fc = [r for r in FCUS if r.startswith("0.")]
    area = sum(geometry["rooms"][r]["clear_floor_area_m2"] for r in ground_fc)
    for room, (model, capacity) in FCUS.items():
        own = result["rooms"][room]["total_w"]
        if room.startswith("0."):
            common = result["rooms"]["0.04"]["total_w"]*geometry["rooms"][room]["clear_floor_area_m2"]/area
        else:
            common = sum(result["rooms"][r]["total_w"] for r in ("1.02", "1.03"))
        budgets[room] = dict(model=model, own_w=own, common_w=common,
                             budget_w=own+common, catalogue_max_w=capacity,
                             water_l_h=(own+common)*.86/5)
    return budgets


def scenarios(geometry):
    base = Assumptions()
    cases = [(f"Suterén {temp:+g} °C", replace(base, basement_c=temp)) for temp in (-15, 0, 5, 10)]
    cases += [
        ("Boost 300 m³/h", replace(base, ventilation_m3_h=300)),
        ("Rekuperace pouze 65 %", replace(base, recovery=.65)),
        ("Infiltrace 0,20 h⁻¹", replace(base, infiltration_ach=.20)),
        ("Tepelné mosty ΔU = 0,10", replace(base, bridge_delta_u=.10)),
        ("Vodivosti izolací +10 %", replace(base, insulation_lambda_factor=1.1)),
        ("Kombinovaný nepříznivý případ", replace(base, recovery=.65, infiltration_ach=.20,
                                                 bridge_delta_u=.10, insulation_lambda_factor=1.1)),
        ("Bez zpětného získávání tepla", replace(base, recovery=0)),
    ]
    return [dict(name=name, **calculate(geometry, assumptions)) for name, assumptions in cases]


def markdown_report(geometry, base, cases, budgets):
    g = geometry["inputs"].get
    rooms = geometry["rooms"]
    area = lambda key: sum(r[key] for r in rooms.values())
    lines = [
        "# D.1.2.1-VYT-02. Zjednodušený výpočet tepelné ztráty",
        "", "**RD Lažánky – orientační ustálená zimní bilance**", "",
        f"Výsledná ztráta při 20/−15 °C a suterénu −15 °C je **{base['total_w']/1000:.2f} kW**. "
        "Jde o konzervativní kontrolu velikosti zdroje a otopných těles, nikoli o výpočet podle ČSN EN 12831-1. "
        "Zvolená míra infiltrace, tepelné mosty, účinnost větrání a U dveří nejsou změřené ani konečně doložené; "
        "výsledek proto není zaručenou horní mezí skutečné ztráty.",
        "", "## 1. Hranice a předpoklady", "",
        f"Obálku tvoří půdorys vnějšího líce zdiva {geometry['width_m']:.2f} × {geometry['depth_m']:.2f} m "
        f"({geometry['width_m']*geometry['depth_m']:.2f} m²), obvodové stěny a dvě šikmé části podhledu s vodorovným středem. "
        "Střešní přesahy neleží nad vytápěným prostorem a nezvětšují plochu tepelné obálky. "
        "Stěna mezi podlažími není venkovní konstrukcí; výška mezistropu je započtena v obvodové stěně 1.NP.",
        "", "Suterén je pro hlavní kontrolu nahrazen venkovním prostředím −15 °C. Započítává se proto ztráta "
        "podlahou nad suterénem, nikoli znovu jeho obvodovými stěnami a základovou deskou. "
        "Pod schody je samostatně zohledněna izolovaná dřevěná podlaha. Vnitřní schodiště mezi vytápěnými "
        "podlažími není venkovním otvorem. Předpokladem je vzduchové oddělení nevytápěného suterénu; "
        "netěsný nebo otevřený průchod by vyžadoval další bilanci proudění.",
        "", "| Parametr | Hodnota |", "|---|---:|",
        "| Vnitřní / venkovní teplota | +20 / −15 °C |",
        "| Větrání, normální provoz | 240 m³/h |",
        "| Zpětné získávání tepla | 77 % – referenční hodnota HERU, předpoklad pro tuto bilanci |",
        "| Dodatečná provozní infiltrace | 0,10 h⁻¹; nejde o n50 |",
        f"| Hrubý objem uvnitř obálky pro infiltraci | {area('gross_volume_m3'):.1f} m³ |",
        "| Přirážka na tepelné mosty | ΔU = 0,05 W/(m²·K) celé hrubé obálky |",
        "| Okna / vstupní dveře | Uw = 1,20 / předpoklad Ud = 1,50 W/(m²·K) |",
        "| Podíl dřeva v obou střešních izolačních vrstvách | předpoklad 10 %, λ dřeva 0,18 W/(m·K) |",
        "", "Objem pro infiltraci je záměrně hrubý, tedy včetně vnitřního zdiva a mezistropu; "
        "nejde o čistý vzduchový objem používaný při kontrole větrání. "
        "Nezapočítávají se tepelné zisky od osob, spotřebičů, slunce, zásobníku TV ani kamen. "
        "Není přidána další paušální výkonová rezerva. Bilance neobsahuje ohřev TV, zátop po útlumu "
        "ani samostatné ztráty potrubí a VZT vedených suterénem.",
        "", "## 2. Skladby a zjednodušené U", "",
        "Pro izolace se přebírají aktuální požadavky modelu. Deklarované λ jsou zde použity jako "
        "výpočtový předpoklad; konečný návrhový přepočet podle vlhkosti a provedení není proveden. "
        "Kladný odpor zdiva, potěrů, MIAKO, dřevěných desek, omítek a vzduchových vrstev je vynechán, "
        "což zvyšuje odhad prostupu tepla. U = 1 / (Rsi + Σ d/λ + Rse). "
        "U vrstvy s dřevem se používá konzervativní účinná vodivost 0,9λ izolace + 0,1λ dřeva.",
        "", "| Konstrukce | Započtená izolace | U [W/(m²·K)] |", "|---|---|---:|",
    ]
    u = base["u_w_m2k"]
    lam = g("INSULATION_LAMBDA_D_MAX")
    definitions = [
        ("Obvodová stěna", f"{g('FACADE_INSULATION_THICKNESS')*1000:g} mm minerální vaty, λ {lam['facade_wool']:.3f}", "wall"),
        ("Šikmá střecha", f"{g('RAFTER_HEIGHT')*1000:g} + {g('THERMAL_INSULATION_UNDER_RAFTERS')*1000:g} mm vaty, λ {lam['roof_wool']:.3f}; dřevo 10 %", "roof_sloped"),
        ("Vodorovný podhled", f"{g('THERMAL_INSULATION_UNDER_RAFTERS')*1000:g} mm vaty, λ {lam['roof_wool']:.3f}; dřevo 10 %", "roof_flat"),
        ("Podlaha nad suterénem", f"{(g('GROUND_FLOOR_INSULATION_THICKNESS')-.03)*1000:g} mm EPS, λ {lam['floor_eps']:.3f} + 30 mm vaty, λ {lam['floor_wool']:.3f}", "floor_regular"),
        ("Podlaha pod schody", f"{g('GROUND_STAIR_OPENING_INSULATION_THICKNESS')*1000:g} mm vaty, λ {lam['stair_floor_wool']:.3f}", "floor_stair"),
    ]
    lines += [f"| {name} | {insulation} | {u[key]:.3f} |" for name, insulation, key in definitions]
    lines += [
        "", "Povrchové odpory: stěny 0,13 + 0,04; střecha 0,10 + 0,04; "
        "podlaha mezi vytápěným a nevytápěným vzduchem 0,17 + 0,17 m²·K/W. "
        "Nad vodorovným podhledem se konzervativně předpokládá studená větraná dutina; "
        "izolace mezi krokvemi nad touto dutinou se proto nepřičítá. "
        "Tepelná přirážka ΔU se vztahuje na plochu včetně otvorů, nikoli pouze neprůsvitné konstrukce; "
        "i u podlahy zůstává vztažena k rozdílu 35 K v citlivostních případech s teplejším suterénem.",
        "", "## 3. Celková bilance", "",
        "Prostup Q = A·U·ΔT; větrání Q = 0,34·q·(1−η)·ΔT; infiltrace Q = 0,34·n·V·ΔT. "
        "Hodnota 0,34 má jednotku Wh/(m³·K). Odvodní průtoky nejsou k přívodním přičteny podruhé. "
        "Ztráta větráním se přiřazuje přívodním místnostem, odkud přestupuje vzduch do odvodních místností.",
        "", "| Složka | Plocha [m²] | Ztráta [W] |", "|---|---:|---:|",
    ]
    labels = [("wall_net", "Obvodové stěny bez otvorů"), ("window", "Okna"), ("door", "Vstupní dveře"),
              ("roof_sloped", "Šikmé části střechy"), ("roof_flat", "Vodorovný podhled"),
              ("floor_regular", "Běžná podlaha nad suterénem"), ("floor_stair", "Podlaha pod schody")]
    for key, label in labels:
        lines.append(f"| {label} | {area(key+'_m2'):.2f} | {base['components_w'][key]:.0f} |")
    for key, label in (("bridges", "Tepelné mosty"), ("infiltration", "Infiltrace"), ("ventilation", "Řízené větrání po rekuperaci")):
        lines.append(f"| {label} | — | {base['components_w'][key]:.0f} |")
    lines += [f"| **Celkem** | | **{base['total_w']:.0f}** |", "",
              "Zaokrouhlené řádky se mohou od celku lišit o jednotky wattů.",
              "", "## 4. Orientační rozdělení po místnostech", "",
              "Plochy otvorů jsou převzaty z konstrukčních otvorů, nikoli z rozměru dveřního křídla. "
              "Obvodové plochy se přiřazují podle polohy místností. Zbývající pruhy pod vnitřním zdivem "
              "a u vnějších líců se přiřazují nejbližší místnosti na síti nejvýše 100 mm. Schodiště patří chodbám. "
              "Tím jsou zahrnuty i konstrukce mimo čisté podlahové polygony a součet odpovídá celé obálce. "
              "Síť ovlivňuje pouze rozdělení mezi místnosti, nikoli celkovou ztrátu. "
              "Vnitřní přestupy při rozdílných teplotách místností se zde neřeší.", "",
              "| Místnost | Čistá podlaha [m²] | Stěna bez otvorů [m²] | Okna [m²] | Ztráta [W] |",
              "|---|---:|---:|---:|---:|"]
    for room in sorted(rooms):
        geom, result = rooms[room], base["rooms"][room]
        lines.append(f"| {room} {geom['name']} | {geom['clear_floor_area_m2']:.2f} | {geom['wall_net_m2']:.2f} | {geom['window_m2']:.2f} | {result['total_w']:.0f} |")
    lines += ["", "Čistá plocha chodby 0.04 v tabulce nezahrnuje samostatnou dřevěnou podlahu pod schody; "
              "její konstrukce je přesto zahrnuta do ztráty této chodby.",
              "", "## 5. Kontrola zařízení", "",
              "Pro rozpočtovou kontrolu se ztráta chodby 0.04 dělí mezi čtyři přízemní fan-coily podle čistých "
              "ploch jejich místností. Ztráty WC 1.02 a chodby 1.03 se přidávají k obývacímu pokoji. "
              "Toto rozdělení dokládá pouze výkonový rozpočet, **nikoli schopnost vytápět chodby a WC přes "
              "uzavřené dveře**. Při shodné teplotě přívodních a odvodních místností vzduch přestupující "
              "mezi nimi nepokrývá jejich vlastní tepelné ztráty. Udržení 20 °C v prostorech bez těles "
              "zůstává neověřené.", "",
              "| FCU | Vlastní místnost [W] | Podíl společných prostor [W] | Rozpočtový výkon [W] | Max. katalog 45/40/20 [W] | Voda při ΔT 5 K [l/h] |",
              "|---|---:|---:|---:|---:|---:|"]
    for room, b in budgets.items():
        lines.append(f"| {room}, {b['model']} | {b['own_w']:.0f} | {b['common_w']:.0f} | {b['budget_w']:.0f} | {b['catalogue_max_w']:.0f} | {b['water_l_h']:.0f} |")
    lines += ["", "Katalogové maximální výkony FCU mají proti tomuto odhadu rezervu. "
              "List IVAR však nedokládá tyto výkony při nejnižších otáčkách. "
              "Nelze je poměrově přepočítat podle průtoku vzduchu ani tím prohlásit splnění hlukového cíle. "
              "Uvedené průtoky vody jsou orientační potřeby místností při 5 K; obtok musí nadále zajistit "
              "minimální průtok zdrojem a při chlazení mohou být potřeby jiné.", "",
              f"LG HU051MR.U44 + HN091MR.NK5 má podle výkonové tabulky při A−15/W45 **4,85 kW** "
              f"včetně vlivu odmrazování. Proti odhadu {base['total_w']/1000:.2f} kW zbývá "
              f"jen **{(4850-base['total_w'])/1000:.2f} kW**. "
              "Jde o tabulkový maximální provoz, nikoli doložený tichý režim; skutečné podmínky instalace "
              "výkon ovlivňují. Jmenovitých 5,50 kW při A7/W35 není výkon pro návrhový mráz. "
              "Tepelné čerpadlo pro základní zjednodušený případ vychází těsně; nezbývá tím automaticky "
              "rezerva na souběžný ohřev TV. Soustava využívá prioritu TV a vestavěný elektrický dohřev, "
              "jejich provozní podíl však tato ustálená bilance nestanovuje.",
              "", "## 6. Citlivost výsledku", "",
              "Každý řádek mění jen uvedený předpoklad vůči hlavnímu případu; kombinovaný případ mění "
              "účinnost na 65 %, infiltraci na 0,20 h⁻¹, ΔU na 0,10 a λ izolací zvyšuje o 10 %. "
              "Nejde o pravděpodobnostní interval ani o vzájemně současně platné výsledky.", "",
              "| Případ | Ztráta [kW] |", "|---|---:|"]
    lines += [f"| {case['name']} | {case['total_w']/1000:.2f} |" for case in cases]
    lines += ["", "## 7. Rozsah použití a podklady", "",
              "Výpočet poskytuje podklad pro rozhodnutí o vytápění a zpřesnění projektu. "
              "Nevyčísluje letní chladicí zátěž, roční spotřebu, samostatný bod bivalence ani "
              "normovou tepelnou ztrátu místností. Pro konečné potvrzení je třeba ověřit zejména "
              "těsnost stavby, tepelné mosty, provedení a návrhové U skladeb, venkovní dveře, "
              "zimní čistou účinnost větrání včetně rozvodů v suterénu, výkon FCU při přijatelném hluku "
              "a předávání tepla do místností bez těles. Změny rozměrů a skladeb vyžadují přepočet.", "",
              f"- [ASHRAE – princip ustálené zimní bilance a nevytápěné sousední prostory]({METHOD_SOURCE}).",
              f"- [LG – tabulka výkonů R32 Split, strana 2]({LG_SOURCE}).",
              f"- [IVAR – technický list SL DC, 03/2026]({IVAR_SOURCE}).",
              "- Stavební část dokumentace: půdorysy, řezy a skladby konstrukcí; část VZT: normální průtok 240 m³/h a referenční účinnost HERU 77 %.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("house2.py"))
    parser.add_argument("--ifc", type=Path, default=Path("house2.ifc"))
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR/VYT)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    geometry = read_geometry(args.source, args.ifc)
    base = calculate(geometry)
    cases = scenarios(geometry)
    budgets = emitter_budgets(geometry, base)
    serial_geometry = {room: {k: v for k, v in data.items() if k not in ("footprint", "zone")}
                       for room, data in geometry["rooms"].items()}
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.source, args.ifc)}
    payload = dict(input_sha256=hashes, geometry=serial_geometry, openings=geometry["openings"],
                   base=base, scenarios=cases, emitter_budgets=budgets,
                   allocation_grid_m=geometry["cell_size_m"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_dir/"D.1.2.1-VYT-02. Zjednodušený výpočet tepelné ztráty"
    # Internal provenance belongs in a separate developer artifact, not the report.
    output_json = Path("cache/heating_loss.json")
    output_json.parent.mkdir(exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    md = Path(str(stem)+".md")
    md.write_text(markdown_report(geometry, base, cases, budgets), encoding="utf-8")
    if args.pdf:
        from pdf_utils import markdown_to_pdf
        markdown_to_pdf(md, Path(str(stem)+".pdf"))
    for case in cases:
        print(f"{case['name']}: {case['total_w']/1000:.3f} kW")
    print(f"Report: {md}")
    print(f"Machine-readable results: {output_json}")


if __name__ == "__main__":
    main()
