"""Winter checks of the selected LG/IVAR heating system; no drawing regeneration.

Uses the geometry in cache/heating_loss.json, verifies its fingerprints, and
keeps estimates distinct from manufacturer ratings and commissioning tests.
"""

import argparse
import hashlib
import json
from math import log, log10, pi
from pathlib import Path

from heating_loss import Assumptions, calculate, emitter_budgets, LG_SOURCE, IVAR_SOURCE
from project_documents import PROJECT_DIR, VYT
from roof_frame_3d import HouseInputs


CP_WATER = 4186 / 3600  # Wh/(litre K), density approximated as 1 kg/litre.
CP_AIR = .34  # Wh/(m3 K), consistent with heating_loss.py.
EUROVENT_SL600 = "https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275034"
LG_ENGINEERING = "https://cms.intermetal.bg/storage/uploads/2022/07/20/62d7c8195b938PDB-R32-heatpump-KR_ThermaV_SplitR32_50Hz_HP_EU_MFL66101114_5BPU0-03DNov.2021_compressed.pdf"
LG_INSTALL = "https://www.lgklimaat.nl/media/reofgoez/installatie-handleiding-hn091mrnk5.pdf"
QUANTUM = "https://quantumas.cz/files/2024/06/quantum_produktove-listy_q7-wwm-2.pdf"
IVAR_CONTROLS = "https://www.ivarcs.cz/storage/Folder_File/78001-80000/fc078428-b5f0-420e-8603-603d0b21f574_file_csnavod-instalace-regulace-fancoily-ivar-749-649-644-647-b3v-08-2024.pdf"

# LG maximum heat output including defrost, not minimum modulation or quiet mode.
# Blank manufacturer cells are intentionally absent. Never extrapolate them.
LG_CAPACITY = {
    35: [(-25, 3.90), (-20, 4.51), (-15, 5.12), (-7, 5.50), (7, 5.50)],
    40: [(-25, 3.78), (-20, 4.38), (-15, 4.99), (-7, 5.50), (7, 5.50)],
    45: [(-25, 3.66), (-20, 4.26), (-15, 4.85), (-7, 5.50), (7, 5.50)],
    50: [(-20, 4.13), (-15, 4.72), (-7, 5.50), (7, 5.50)],
    55: [(-15, 4.58), (-7, 5.50), (7, 5.50)],
}
FCU_DATA = {
    "SL 400 DC": dict(max_w=2210, air_m3_h=[118, 210, 294], lp_1m_db=[25, 34, 42],
                      rated_water_l_h=390, rated_drop_kpa=9.2, water_l=.8),
    "SL 600 DC": dict(max_w=3020, air_m3_h=[180, 318, 438], lp_1m_db=[26, 34, 44],
                      rated_water_l_h=532, rated_drop_kpa=19.1, water_l=1.13),
    "SL 1000 DC": dict(max_w=4320, air_m3_h=[262, 479, 663], lp_1m_db=[28, 38, 47],
                       rated_water_l_h=762, rated_drop_kpa=23.3, water_l=1.8),
}


class DesignInputs:
    """Design-conductivity sensitivity: wool +7 %, EPS +3 %, XPS unchanged.

    Uses the simplified correction option in 264/2020 Annex 5 C.1 as a
    transparent screening choice, not a product-specific hygrothermal proof.
    """
    def __init__(self, source):
        self.source = source

    def get(self, name):
        value = self.source.get(name)
        if name == "INSULATION_LAMBDA_D_MAX":
            return {key: lam*(1.03 if key == "floor_eps" else 1 if key == "perimeter_xps" else 1.07)
                    for key, lam in value.items()}
        return value


def interpolate(points, x):
    if not points[0][0] <= x <= points[-1][0]:
        raise ValueError("Outside the manufacturer's tabulated range")
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0+(y1-y0)*(x-x0)/(x1-x0)
    raise ValueError("Interpolation requires at least two points")


def water_energy(litres, cold_c, hot_c):
    if litres < 0 or hot_c < cold_c:
        raise ValueError("Invalid water-heating temperatures or volume")
    return litres*CP_WATER*(hot_c-cold_c)/1000


def mixed_volume(hot_litres, hot_c, cold_c, use_c):
    if not cold_c < use_c <= hot_c:
        raise ValueError("Mixed water must lie between cold and hot temperatures")
    return hot_litres*(hot_c-cold_c)/(use_c-cold_c)


def water_flow_l_h(power_w, delta_k=5):
    if power_w < 0 or delta_k <= 0:
        raise ValueError("Invalid load or temperature drop")
    return power_w/(CP_WATER*delta_k)


def temperature_derating(supply_c, return_c, indoor_c=20):
    """First-order water-to-room LMTD ratio, NOT a manufacturer selection."""
    def lm(supply, ret):
        if supply <= ret or ret <= indoor_c:
            raise ValueError("Water temperatures must exceed room temperature")
        return (supply-ret)/log((supply-indoor_c)/(ret-indoor_c))
    return lm(supply_c, return_c)/lm(45, 40)


def daily_balance(space_kw, space_capacity_kw, dhw_capacity_kw, dhw_kwh):
    """Ideal constant charging output: optimistic recovery/backup estimate."""
    if min(space_capacity_kw, dhw_capacity_kw) <= 0 or min(space_kw, dhw_kwh) < 0:
        raise ValueError("Invalid power or energy")
    charging_h = dhw_kwh/dhw_capacity_kw
    if charging_h > 24:
        raise ValueError("Hot-water demand alone exceeds a full day of operation")
    space_kwh = 24*space_kw
    delivered_space_kwh = (24-charging_h)*space_capacity_kw
    return dict(space_kwh=space_kwh, charging_h=charging_h,
                space_backup_kwh=max(0, space_kwh-delivered_space_kwh),
                dhw_available_h=max(0, 24-space_kwh/space_capacity_kw))


def pipe_loss(flow_l_h, inner_diameter_m, length_m, viscosity=1.31e-6, density=999.7):
    """Darcy–Weisbach, laminar or smooth-pipe Haaland; conservative transition."""
    if min(flow_l_h, length_m) < 0 or inner_diameter_m <= 0:
        raise ValueError("Invalid pipe dimensions or flow")
    if not flow_l_h:
        return dict(velocity_m_s=0, reynolds=0, drop_kpa=0)
    velocity = flow_l_h/3.6e6/(pi*inner_diameter_m**2/4)
    re = velocity*inner_diameter_m/viscosity
    turbulent = (-1.8*log10(6.9/max(re, 1000)))**-2
    friction = 64/re if re < 2300 else max(64/re, turbulent) if re < 4000 else turbulent
    return dict(velocity_m_s=velocity, reynolds=re,
                drop_kpa=friction*length_m/inner_diameter_m*density*velocity**2/2/1000)


def bivalence(geometry, supply_c, basement_c):
    """Space heating only at constant water temperature; excludes DHW downtime."""
    def margin(temp):
        load = calculate(geometry, Assumptions(outdoor_c=temp, basement_c=basement_c))["total_w"]/1000
        return interpolate(LG_CAPACITY[supply_c], temp)-load
    low, high = -25., -7.
    if margin(low) > 0 or margin(high) < 0:
        return None
    for _ in range(50):
        mid = (low+high)/2
        if margin(mid) >= 0:
            high = mid
        else:
            low = mid
    return (low+high)/2


def transfer_check(room_losses, room_env_conductance, incoming_flow=160, target_c=18, source_c=20):
    """Necessary heat transfer at a lower hall temperature, excluding wall gains.

    120 m3/h from ground bedrooms + (120 supply - 80 kitchen extract) upstairs.
    This is NOT an equilibrium-temperature prediction: internal wall properties
    and bidirectional flow through open doors are not known.
    """
    drop = source_c-target_c
    if drop < 0:
        raise ValueError("Target exceeds the assumed source-room temperature")
    remaining_loss = max(0, room_losses-room_env_conductance*drop)
    air_gain = CP_AIR*incoming_flow*drop
    deficit = max(0, remaining_loss-air_gain)
    required_conductance = deficit/drop if drop else None
    return dict(target_c=target_c, loss_w=remaining_loss, air_gain_w=air_gain,
                unexplained_w=deficit, required_internal_conductance_w_k=required_conductance)


def equipment_clearance(ifc_path, ceiling_z):
    import ifcopenshell
    import ifcopenshell.geom
    import numpy as np
    model = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    boxes = {}
    for obj in model.by_type("IfcFurniture"):
        name = "".join((obj.Name or "").lower().split()).replace("-", "")
        if name not in ("hydrobox", "zásobníktuv"):
            continue
        # Retain shape ownership until vertices have been copied.
        shape = ifcopenshell.geom.create_shape(settings, obj)
        vertices = np.array(shape.geometry.verts).reshape((-1, 3))
        boxes[name] = (vertices.min(axis=0), vertices.max(axis=0))
    h0, h1 = boxes["hydrobox"]
    t0, t1 = boxes["zásobníktuv"]
    overlaps_height = min(h1[2], t1[2])-max(h0[2], t0[2]) > 0
    gap = max(h0[1]-t1[1], t0[1]-h1[1], 0)
    return dict(tank_side_gap_m=float(gap), required_side_gap_m=.20,
                height_overlap=bool(overlaps_height), passes=bool(gap >= .20 or not overlaps_height),
                missing_gap_m=float(max(0, .20-gap)),
                top_gap_m=float(ceiling_z-h1[2]), required_top_gap_m=.25)


def run_checks(source=Path("house2.py"), ifc=Path("house2.ifc"), daily_mixed_l=300):
    cached = json.loads(Path("cache/heating_loss.json").read_text())
    for path in (source, ifc):
        expected = cached["input_sha256"].get(path.name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Heat-loss geometry is stale; run heating_loss.py first")
    inputs = HouseInputs(source)
    geometry = dict(inputs=DesignInputs(inputs), rooms=cached["geometry"])
    use_kwh = water_energy(daily_mixed_l, 10, 40)
    dhw_kwh = use_kwh+.066*24
    cases = []
    for outside, basement in [(-15, -15), (-15, 5), (-5, 5)]:
        loss = calculate(geometry, Assumptions(outdoor_c=outside, basement_c=basement))
        capacities = {str(t): interpolate(LG_CAPACITY[t], outside) for t in (35, 40, 45, 50, 55)}
        cases.append(dict(outdoor_c=outside, basement_c=basement, heat_loss=loss,
                          floor_kw={prefix: sum(v["total_w"] for r, v in loss["rooms"].items() if r.startswith(prefix))/1000
                                    for prefix in ("0.", "1.")},
                          capacity_kw=capacities,
                          daily={str(t): daily_balance(loss["total_w"]/1000, capacities[str(t)], capacities["55"], dhw_kwh)
                                 for t in (40, 45)}))
    design = cases[0]["heat_loss"]
    budgets = emitter_budgets(geometry, design)
    ratio = temperature_derating(40, 35)
    for room, budget in budgets.items():
        data = FCU_DATA[budget["model"]]
        budget.update(own_water_l_h=water_flow_l_h(budget["own_w"]),
                      budget_water_l_h=water_flow_l_h(budget["budget_w"]),
                      max_estimate_40_35_w=data["max_w"]*ratio,
                      min_airflow_m3_h=data["air_m3_h"][0],
                      absolute_low_airflow_limit_40_w=CP_AIR*data["air_m3_h"][0]*(40-20),
                      outlet_at_own_load_low_air_c=20+budget["own_w"]/(CP_AIR*data["air_m3_h"][0]))
    # This is a reference INNOVA SL600 record, not certified identity of an IVAR delivery.
    low600_40 = 1200*ratio
    low600_results = {room: dict(reference_low_40_35_w=low600_40,
                                  estimate_with_15pct_allowance_w=.85*low600_40,
                                  own_load_w=budgets[room]["own_w"])
                      for room in ("0.01", "0.02", "0.03")}
    hall_ids = ("0.04", "1.03")
    hall_loss = sum(design["rooms"][room]["total_w"] for room in hall_ids)
    # At the cold-basement case all environmental boundaries are -15 C; no direct supply in halls.
    hall_g = hall_loss/35
    halls = dict(rooms={room: design["rooms"][room]["total_w"] for room in hall_ids},
                 total_at20_w=hall_loss,
                 tests=[transfer_check(hall_loss, hall_g, target_c=t) for t in (20, 18, 16)],
                 wc_at20_w=design["rooms"]["1.02"]["total_w"])
    # Preliminary routes are LENGTH ALLOWANCES, not the schematic heating arrows.
    common = pipe_loss(948, .026, 20)
    pipes = {}
    for room, budget in budgets.items():
        data = FCU_DATA[budget["model"]]
        diameter = .020 if room == "1.01" else .016
        q = budget["budget_water_l_h"]
        branch = pipe_loss(q, diameter, 30)
        coil = data["rated_drop_kpa"]*(q/data["rated_water_l_h"])**2
        valve = 100*(q/1000/3.6)**2  # Kvs = 3.60 m3/h at 1 bar.
        # 50% pipe fitting allowance + common components 10 kPa + balancing 10 kPa.
        total = 1.5*(common["drop_kpa"]+branch["drop_kpa"])+coil+valve+20
        pipes[room] = dict(flow_l_h=q, diameter_m=diameter, pipe_length_m=30,
                           **branch, coil_estimate_kpa=coil, valve_kpa=valve,
                           route_estimate_kpa=total)
    total_flow = sum(b["budget_water_l_h"] for b in budgets.values())
    hydraulic = dict(common=common, branches=pipes, total_branch_l_h=total_flow,
                     bypass_l_h=max(0, 948-total_flow), available_head_kpa=7.3*9.81,
                     maximum_route_kpa=max(v["route_estimate_kpa"] for v in pipes.values()),
                     hp_delta_k=design["total_w"]/(CP_WATER*948),
                     controlled_return_c=40-design["total_w"]/(CP_WATER*948))
    pipe_volume = 20*pi*.026**2/4*1000+4*30*pi*.016**2/4*1000+30*pi*.020**2/4*1000
    space_volume = 51+5.99+pipe_volume
    dhw_volume_provisional = 25  # Hu.Ray comparable tank; NOT confirmed QUANTUM.
    volumes = dict(pipe_allowance_l=pipe_volume, space_circuit_l=space_volume,
                   total_with_comparable_tank_and_10l_reserve_l=space_volume+dhw_volume_provisional+10,
                   buffer_l=51, minimum_l=20, buffer_energy_at5k_kwh=water_energy(51, 0, 5),
                   available_expansion_l=8, lg_reference_max_l=230)
    # Confirmed incoming/high-use DHW profile, no circulation or pipe-loss allowance.
    dhw = dict(people=4, mixed_l_day=daily_mixed_l, use_c=40, cold_c=10, tank_c=55,
               draw_kwh=use_kwh, tank_loss_kwh=.066*24, daily_kwh=dhw_kwh,
               ideal_usable_mixed_l=mixed_volume(400, 55, 10, 40),
               equivalent_hot_draw_l=daily_mixed_l*(40-10)/(55-10),
               whole_cold_start_kwh=water_energy(400, 10, 55),
               booster_only_h=dhw_kwh/2.5,
               entire_tank_45_to55_kwh=water_energy(400, 45, 55),
               entire_tank_50_to55_kwh=water_energy(400, 50, 55),
               cold_point_dhw_water_max_kw=4.58)
    electric = dict(compressor_kw_at_minus15_w40=4.99/2.09,
                    backup_kw=6, dhw_booster_kw=2.5,
                    coincident_input_kw=4.99/2.09+6+2.5)
    return dict(source_hashes=cached["input_sha256"], assumptions=dict(
        daily_mixed_l=daily_mixed_l, floor_eps_lambda_factor=1.03, wool_lambda_factor=1.07,
        cold_water_c=10, design_setpoint_c=20, standing_loss_w=66,
        flow_l_h=948, total_common_pipe_m=20, total_branch_pipe_m=30),
        cases=cases, budgets=budgets, low600=low600_results, halls=halls,
        hydraulics=hydraulic, volumes=volumes, dhw=dhw, electric=electric,
        bivalence=[dict(supply_c=t, basement_c=b, outdoor_c=bivalence(geometry, t, b))
                   for t in (40, 45) for b in (-15, 5)],
        clearance=equipment_clearance(ifc, inputs.get("ground_floor_height")),
        references=dict(lg_capacity=LG_SOURCE, lg_engineering=LG_ENGINEERING,
                        lg_installation=LG_INSTALL, ivar=IVAR_SOURCE,
                        ivar_controls=IVAR_CONTROLS, reference_sl600=EUROVENT_SL600,
                        tank=QUANTUM))


def report(r):
    cases, budgets = r["cases"], r["budgets"]
    d, h, vol, halls = r["dhw"], r["hydraulics"], r["volumes"], r["halls"]
    lines = [
        "# D.1.2.1-VYT-03. Technické ověření vytápění a přípravy TV", "",
        "**RD Lažánky – LG HU051MR.U44 + HN091MR.NK5, pět IVAR.SL DC, QUANTUM Q7-400-WWM**", "",
        "## 1. Výsledek kontroly", "",
        "Malé tepelné čerpadlo lze ponechat jako základ bivalentní soustavy s automatickým elektrickým dohřevem. "
        "Provoz 40/35 °C je vhodnou výchozí variantou, avšak splnění všech teplot a hluku současným rozmístěním pěti FCU "
        "**není potvrzeno**. Hlavní neuzavřené body jsou dodávka tepla do chodeb a WC, tichý výkon horní FCU, "
        "nabíjecí charakteristika skutečného zásobníku a boční servisní prostor hydroboxu. "
        "Tato příloha rozlišuje početní ověření, odhad a zkoušku na stavbě; není autorizovaným normovým projektem.", "",
        "| Kontrola | Výsledek |", "|---|---|",
        "| Výkon zdroje pro vytápění | V uvedeném základním odhadu vychází; malá rezerva, automatický dohřev zůstává součástí návrhu |",
        "| Energetická bilance TV pro 4 osoby, vyšší odběr | Vyčíslena; za návrhových mrazů počítat s elektřinou také pro TV |",
        "| FCU při 40/35 °C, maximální otáčky | Odhad rezervy vychází; nejde o výrobcem potvrzený výběr při daném průtoku |",
        "| Chodby a WC při 20 °C | Současná koncepce bez vlastního tělesa neprokazuje potřebné předání tepla |",
        "| Horní FCU na nejnižším publikovaném průtoku vzduchu | 40 °C přívod nestačí pro celý horní výkon ani při ideálním přenosu |",
        "| Čerpadlo a dimenze potrubí | Vyhovují kontrolním délkám; skutečné trasy a tlaková zkouška zbývají |",
        "| Objem prostorové větve a topná expanze | Dostatečná předběžná rezerva; průtok při zavřených FCU ověřit měřením |",
        "| Větev zásobníku TV | Přesný objem, odpor a výkon skutečného QUANTUM potvrdit dodavatelem |",
        "| Umístění hydroboxu | Nevyhovuje boční servisní mezeře vedle zásobníku |", "",
        "## 2. Zimní vstupy a aktualizace vodivostí", "",
        "Přebírají se geometrie a konzervativní předpoklady přílohy VYT-02. Pro tuto kontrolu je navíc použita "
        "zjednodušená návrhová korekce deklarovaných λ: minerální vata +7 %, EPS +3 %, XPS beze změny. "
        "Jde o transparentní citlivostní variantu podle možnosti uvedené v příloze 5 části C vyhlášky 264/2020 Sb.; "
        "výrobkový návrhový přepočet může dát jinou hodnotu. Původní odhad VYT-02 s λD se tím zpětně nepřepisuje. "
        "Nadále se neuvažují kladné odpory zdiva a dalších pevných vrstev ani vnitřní a solární zisky.", "",
        "| Venkovní / suterén [°C] | 1.NP [kW] | 2.NP [kW] | Celkem [kW] | LG při W40 [kW] | LG při W45 [kW] |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for c in cases:
        lines.append(f"| {c['outdoor_c']:+g} / {c['basement_c']:+g} | {c['floor_kw']['0.']:.2f} | {c['floor_kw']['1.']:.2f} | {c['heat_loss']['total_w']/1000:.2f} | {c['capacity_kw']['40']:.2f} | {c['capacity_kw']['45']:.2f} |")
    lines += ["", "LG výkony jsou maximální, včetně odmrazování, nikoli v tichém režimu. "
              "Nesmějí být zaměňovány s minimální modulací nebo zaručeným výkonem ve skutečné instalaci. "
              "Suterén se samostatně nevytápí; jeho vlastní ztráta se k podlaze nepřičítá podruhé.", "",
              "### Bod bivalence – pouze prostorové vytápění", "",
              "Při konstantní teplotě vody vychází z průsečíku výkonové a ztrátové křivky:", "",
              "| Přívod [°C] | Suterén [°C] | Orientační venkovní bod bivalence [°C] |", "|---:|---:|---:|"]
    for b in r["bivalence"]:
        lines.append(f"| {b['supply_c']} | {b['basement_c']:+g} | {b['outdoor_c']:.1f} |")
    lines += ["", "Toto **není teplota zákazu elektrodohřevu**. Příprava TV odebírá čas, předpoklady ztráty jsou přibližné "
              "a provozní rezerva je malá. Automatická pomoc musí být dostupná také nad vypočteným bodem. "
              "Kamna jsou dobrovolný doplněk; v těchto výsledcích nemají připsaný výkon.", "",
              "## 3. Fan-coily při 40/35 °C", "",
              "Publikované maximální výkony IVAR jsou při 45/40/20 °C. Pro kontrolu 40/35/20 °C se používá pouze "
              "první přiblížení poměrem logaritmických rozdílů teplot voda–místnost: "
              "LMTD(40/35/20) / LMTD(45/40/20) = 0,776. Není to výstup výběrového programu. "
              "Změna průtoku vody mění i přestup tepla; odhad nelze použít jako potvrzený výkon při nejnižších otáčkách.", "",
              "| FCU | Vlastní místnost [W] | Bilanční podíl chodeb/WC [W] | Celkem [W] | Odhad maxima 40/35 [W] | Průtok pro celkový podíl při 5 K [l/h] |",
              "|---|---:|---:|---:|---:|---:|"]
    for room, b in budgets.items():
        lines.append(f"| {room}, {b['model']} | {b['own_w']:.0f} | {b['common_w']:.0f} | {b['budget_w']:.0f} | {b['max_estimate_40_35_w']:.0f} | {b['budget_water_l_h']:.0f} |")
    lines += ["", "Přiřazení chodeb do tabulky je výhradně bilanční. Nevytváří cestu, kterou se do nich teplo dostane. "
              "Průtoky jsou potřebou pro daný výkon při ΔT 5 K, ne konečným vyvážením ventilů. "
              "Při nižším výkonu může být skutečná vratná teplota vyšší než 35 °C.", "",
              "### Nízké otáčky a hluk", "",
              "Certifikovaný referenční INNOVA AirLeaf SL600 má při 45/40/20 °C výkon 1,20 kW na nízké "
              "a 2,16 kW na střední rychlosti. Shodují se rozměry a maximální výkon s publikovaným IVAR.SL600; "
              "totožnost konkrétní dodávky IVAR však musí být potvrzena. Pro nízkou rychlost vychází první odhad "
              "při 40/35 °C přibližně 931 W, s dodatečnou kontrolní srážkou 15 % asi 791 W. "
              "To pokrývá vlastní ztrátu pokojů v základním případě, ale neprokazuje předání připsané části ztráty chodby. "
              "Srážka 15 % není výrobcem garantovanou tolerancí.", "",
              "Pro SL1000 je publikovaný nejnižší průtok vzduchu 262 m³/h. I kdyby výstupní vzduch dosáhl celých "
              f"40 °C, odnesl by nejvýše **{budgets['1.01']['absolute_low_airflow_limit_40_w']:.0f} W**, "
              f"zatímco bilanční horní výkon je **{budgets['1.01']['budget_w']:.0f} W**. "
              "Skutečný výstup je chladnější, takže nejnižší publikovaný průtok není řešením pro celé horní podlaží "
              "v návrhovém stavu. Při 479 m³/h a tomto výkonu by potřebný výstupní vzduch měl přibližně "
              f"{20+budgets['1.01']['budget_w']/(CP_AIR*479):.1f} °C; výkon na této rychlosti musí potvrdit výběr jednotky.", "",
              "IVAR uvádí akustický tlak při nízké/střední rychlosti ve vzdálenosti 1 m: SL600 26/34 dB(A), "
              "SL1000 28/38 dB(A). Nejsou to hladiny u postele nebo sedačky a nejsou přímo zaměnitelné "
              "s akustickým výkonem. Reverberace, poloha a souběh s VZT nejsou doloženy. "
              "Splnění komfortního cíle 25 dB(A) v pokojích nelze z těchto údajů potvrdit; prosté odečtení útlumu "
              "volného pole v malé místnosti není dostatečné. Pokud má být tento cíl závazný i pro FCU, "
              "je třeba výběr při požadovaném výkonu a akustický návrh nebo měření.", "",
              "### Teplota vyfukovaného vzduchu a regulace", "",
              "Platí Tair,out = Troom + Q/(0,34·qair). Při vlastních ztrátách a nejnižším publikovaném průtoku:", "",
              "| FCU | Potřebný výkon místnosti [W] | Průtok vzduchu [m³/h] | Potřebný výstup vzduchu [°C] |",
              "|---|---:|---:|---:|"]
    for room, b in budgets.items():
        lines.append(f"| {room} | {b['own_w']:.0f} | {b['min_airflow_m3_h']} | {b['outlet_at_own_load_low_air_c']:.1f} |")
    lines += ["", "Tabulka je energetická potřeba, nikoli potvrzený pracovní bod. Zejména v koupelně by "
              "nepřetržité vyfukování při malé ztrátě bylo vlažné; ventilátor má při uspokojeném požadavku "
              "omezit nebo ukončit činnost, nikoli zbytečně rozdmýchávat vzduch. "
              "Čidlo vody H2/T2 musí zůstat zapojené; ovladač blokuje ventilaci při nevhodné teplotě vody, "
              "v topení pod 30 °C. Zpočátku držet přívod přibližně 36–40 °C, aby při ΔT do 5 K zbývala rezerva "
              "nad blokovacím prahem, a křivku nastavit při zprovoznění. Hodnota 40/35 je varianta k ověření; "
              "možnost 45/40 zůstává pro mráz či nedostatečný komfort. U běžného SL nepoužít nastavení nočního režimu, "
              "které zakáže ventilátor, a současně nepředpokládat nucený katalogový výkon.", "",
              "## 4. Místnosti bez FCU", "",
              f"Při 20 °C činí vlastní ztráta chodby 0.04 **{halls['rooms']['0.04']:.0f} W**, "
              f"chodby 1.03 **{halls['rooms']['1.03']:.0f} W** a WC 1.02 **{halls['wc_at20_w']:.0f} W**. "
              "Při stejné teplotě všech sousedních místností neexistuje hnací rozdíl pro přestup z interiéru. "
              "Přestupující vzduch o 20 °C také nemůže udržovat ztrátovou místnost na 20 °C bez dalšího zdroje. "
              "Samotná zásoba výkonu v pěti FCU tedy tento požadavek nesplňuje.", "",
              "Obě chodby se pro nutnou podmínku sloučí do jedné cirkulační zóny. Přitéká do ní "
              "120 m³/h z přízemních pokojů a čistých 40 m³/h z horního obývacího pokoje po odečtení "
              "kuchyňského odvodu. Není přidán nový větrací průtok. Otevřeným schodištěm se může vzduch "
              "míchat, ale samo o sobě nepřidává tepelný zdroj.", "",
              "| Teplota chodeb [°C] | Ztráta chodeb [W] | Přenos větracím vzduchem z místností 20 °C [W] | Zbývá dodat stěnami nebo jinou cestou [W] |",
              "|---:|---:|---:|---:|"]
    for t in halls["tests"]:
        lines.append(f"| {t['target_c']} | {t['loss_w']:.0f} | {t['air_gain_w']:.0f} | {t['unexplained_w']:.0f} |")
    lines += ["", "Jde o nutnou energetickou podmínku, ne o výpočet skutečné teploty chodby. Pro ni chybí "
              "potvrzené tepelné odpory vnitřních příček a dveří, jejich stav otevření a proudění. "
              "Nelze pouze prohlásit, že snížení požadavku na 18 °C problém vyřeší. "
              "K uzavření návrhu je nutné buď doložit konkrétní přenos tepla při přijatých nižších teplotách, "
              "nebo upravit rozdělení koncových zařízení. Orientační přímý výkon pro chodby při 20 °C je "
              "asi 0,6 kW v 1.NP a 0,3 kW ve 2.NP; to je podklad pro rozhodnutí, nikoli pokyn k přidání těles. "
              "WC může využívat přenos ze skutečně vytápěné chodby, ale i jeho výsledná teplota musí být doložena. "
              "Současný model s pěti FCU nebyl touto kontrolou změněn.", "",
              "## 5. Vyšší odběr TV a zimní časová bilance", "",
              f"Potvrzený odběr: čtyři osoby, **{d['mixed_l_day']:g} l/den při 40 °C**, studená voda 10 °C, "
              f"zásobník 400 l při 55 °C. Ohřev spotřebované vody potřebuje **{d['draw_kwh']:.2f} kWh/den**. "
              f"Se štítkovou ztrátou 66 W ({d['tank_loss_kwh']:.2f} kWh/den) jde o **{d['daily_kwh']:.2f} kWh/den**. "
              "Ztráty odboček a čekání na vodu nejsou zahrnuty; cirkulace se neuvažuje. "
              "Štítková ztráta není měřením skutečného denního provozu a zisk do koupelny se současně nezapočítává.", "",
              f"Ideálních 400 l při 55 °C odpovídá **{d['ideal_usable_mixed_l']:.0f} l při 40 °C** smícháním "
              f"se studenou vodou 10 °C. Denní odběr odpovídá **{d['equivalent_hot_draw_l']:.0f} l vody 55 °C**. "
              "Skutečnou využitelnost snižují promíchání, teplotní rozvrstvení, regulace a špičkový odběr; "
              "nejde o certifikovaný odběrový profil zásobníku. "
              f"Studený start celého zásobníku 10→55 °C je **{d['whole_cold_start_kwh']:.2f} kWh**, odlišný od běžného dne.", "",
              "### Idealizovaná časová bilance kompresoru", "",
              "V tabulce se celá denní energie TV dělí maximálním výkonem LG při výstupní vodě 55 °C. "
              "Po tento čas kompresor netopí do místností. Zbytek dne smí pro kontrolu pracovat na maximální "
              "výkon při 40 °C. Jde o optimistický výpočet doby nabíjení a dolní odhad potřebné pomoci "
              "v tomto konkrétním způsobu řízení; není garantován přenos výměníkem ani dokončení ohřevu na 55 °C.", "",
              "| Venkovní / suterén [°C] | Teplo místnosti [kWh/den] | Ideální nabíjení TV [h/den] | Prostorová pomoc elektřinou při W40 [kWh/den] |",
              "|---|---:|---:|---:|"]
    for c in cases:
        b = c["daily"]["40"]
        lines.append(f"| {c['outdoor_c']:+g} / {c['basement_c']:+g} | {b['space_kwh']:.1f} | {b['charging_h']:.2f} | {b['space_backup_kwh']:.2f} |")
    lines += ["", "Tento denní součet sám neprokazuje udržení teploty při dlouhém nepřerušeném nabíjení TV. "
              "LG umožňuje omezit délku jedné nabíjecí periody a vložit přestávku pro prostorové vytápění. "
              "Výchozí časování v citovaném návodu je 30 minut nabíjení / 30 minut přestávky; konkrétní firmware "
              "a nastavení ověřit. Nepředepisuje se jeden mnohahodinový blok bez vytápění místností.", "",
              "### Dokončení ohřevu zásobníku", "",
              "Výkon LG při W55 je výkon zdroje při teplotě jeho topné vody, nikoli výkon nabíjení zásobníku "
              "o teplotě 55 °C. Při stejné teplotě vody ve spirále a zásobníku přestup klesá k nule. "
              "Při A−15/W60 není v tabulce doložený výkon; nelze jej extrapolovat. Samotná plocha výměníku "
              "4,7 m² nestačí k určení jeho výkonu při malém teplotním rozdílu. "
              "Proto musí zůstat součástí návrhu samostatná elektrická patrona TV a její regulace. "
              "Objem vody a tlaková charakteristika převzaté ze srovnatelného Hu.Ray nejsou potvrzením dodávky QUANTUM.", "",
              f"Celých 400 l při 45→55 °C potřebuje **{d['entire_tank_45_to55_kwh']:.2f} kWh**; "
              f"při 50→55 °C **{d['entire_tank_50_to55_kwh']:.2f} kWh**. "
              "Skutečná energie poslední fáze závisí na rozvrstvení a poloze čidla.", "",
              f"Kapacitní záložní varianta: patrona 2,5 kW dodá celých {d['daily_kwh']:.2f} kWh za "
              f"**{d['booster_only_h']:.2f} h/den**. LG v návodu popisuje prioritu prostorového vytápění, "
              "při které TV přebírá patrona a kompresor se věnuje místnostem. Tím není nutné ani za mrazu "
              "spoléhat na obsluhu kamen. Vyžaduje to skutečně osazenou a mechanicky ověřenou patronu, "
              "správnou konfiguraci LG/PHLTA a dostatečné elektrické napájení. "
              "Jde o energetickou dostupnost, nikoli předpoklad, že se tak bude ohřívat celý rok. "
              "Hygienický režim a ochranu proti opaření stanoví návrh TV a návody výrobků.", "",
              "## 6. Hydraulická kontrola", "",
              "Kontrolní délky: společné potrubí 32×3 mm celkem 20 m přívod+zpátečka; každá větev celkem "
              "30 m. Pokojové a koupelnová větev 20×2 mm, horní větev 26×3 mm. Nejsou to zaměřené trasy "
              "ani délky konceptuálních šipek v půdorysu. Tření je počítáno konzervativně pro vodu 10 °C "
              "s laminárním/turbulentním rozlišením. Přičteno 50 % potrubního tření na místní odpory, "
              "10 kPa na společné armatury/filtr/nádobu a 10 kPa na rozdělovač a vyvážení. "
              "Odpor výměníku FCU je pouze kvadratický odhad z katalogového bodu, odpor ventilu z Kvs = 3,60.", "",
              "| Větev | Průtok [l/h] | Rychlost [m/s] | Potrubí [kPa] | Výměník – odhad [kPa] | Celá cesta – odhad [kPa] |",
              "|---|---:|---:|---:|---:|---:|"]
    for room, p in h["branches"].items():
        lines.append(f"| {room} | {p['flow_l_h']:.0f} | {p['velocity_m_s']:.2f} | {p['drop_kpa']:.2f} | {p['coil_estimate_kpa']:.2f} | {p['route_estimate_kpa']:.1f} |")
    lines += ["", f"Nejnepříznivější kontrolní cesta **{h['maximum_route_kpa']:.1f} kPa** je pod "
              f"disponibilní výškou přibližně **{h['available_head_kpa']:.1f} kPa** při 948 l/h. "
              "Druhé čerpadlo není pro tyto předpoklady potřeba. Výškový rozdíl podlaží se v uzavřeném "
              "okruhu nepřičítá k třecí tlakové ztrátě. Výsledek neplatí pro nezměřené dlouhé trasy "
              "nebo zanesené filtry bez kontroly skutečného průtoku.", "",
              f"Součet bilančních větví je **{h['total_branch_l_h']:.0f} l/h**. Při průtoku hydroboxu "
              f"948 l/h projde obtokem asi **{h['bypass_l_h']:.0f} l/h**. Při přívodu 40 °C a návrhové ztrátě "
              f"vyjde směšovaná zpátečka u zdroje asi **{h['controlled_return_c']:.1f} °C**, "
              "nikoli přesně 35 °C. Obtok tedy ovlivňuje skutečný pracovní bod. Při zavření větví musí "
              "obtok a buffer zajistit doporučené minimum LG 15 l/min; ověřit měřením, samotné nastavení "
              "20 kPa není důkazem. Rozdělovač/ventily musí umět měřit přibližně 0,5–0,8 l/min "
              "u koupelny, 2–3 l/min u pokojů a asi 6 l/min u horní větve; běžná stupnice 0–5 l/min "
              "nemusí vyhovět celému rozsahu.", "",
              "## 7. Dostupný objem, expanze a cyklování", "",
              f"Z kontrolních délek vychází potrubí **{vol['pipe_allowance_l']:.1f} l**, "
              f"prostorová větev s bufferem 51 l a výměníky FCU 5,99 l asi **{vol['space_circuit_l']:.1f} l**. "
              "Jde o horní kontrolní délky, nikoli skutečný napuštěný objem. Při zavření FCU zůstává dostupný "
              "buffer a společná větev; samotný buffer přesahuje minimum LG 20 l. "
              "Pro režim TV se připojení vrací až za bufferem. Požadavek 20 l se vztahuje k dostupnému "
              "součtu výměníku TV, potrubí a hydroboxu; výměník sám nemusí mít 20 l, pokud součet minimum splní.", "",
              f"Se srovnávacím 25l výměníkem a další 10l objemovou rezervou vychází nejvýše přibližně "
              f"**{vol['total_with_comparable_tank_and_10l_reserve_l']:.0f} l**, pod referenčními 230 l "
              "LG pro vestavěnou 8l expanzi a odpovídající statickou výšku. Skutečný objem, výška a předtlak "
              "se před plněním ověří. Pitná 25l expanze zásobníku zůstává samostatná a není součástí této 8l nádoby.", "",
              f"Buffer 51 l při využitelné hysterezi 5 K uloží **{vol['buffer_energy_at5k_kwh']:.3f} kWh**. "
              "Například při přebytku 1 kW prodlouží běh asi o 18 minut, při 3 kW asi o 6 minut. "
              "Nejde o předpověď počtu startů: minimální modulace LG v daném bodě, celkový dostupný objem "
              "a regulační hystereze nejsou doloženy. Zdroj má reagovat na součet požadavků FCU; "
              "při nulovém požadavku nepokračovat zbytečně v prostorovém ohřevu, ale zachovat ochrany "
              "proti mrazu, odmrazování a doběhy. Nevypínat celý zdroj odpojením napájení.", "",
              "## 8. Elektrické a prostorové podmínky", "",
              f"Při A−15/W40 a tabulkovém COP 2,09 činí příkon kompresorové sestavy asi "
              f"**{r['electric']['compressor_kw_at_minus15_w40']:.2f} kW**. S plným 6kW dohřevem a patronou TV "
              f"2,5 kW může souběh dosáhnout asi **{r['electric']['coincident_input_kw']:.1f} kW** před ostatními "
              "spotřebiči. Není to zaručené maximum příkonu instalace. Jde o jednofázové spotřebiče se samostatnými "
              "přívody podle návodů; nelze je bez kontroly seskupit na jednu fázi. Elektro musí ověřit "
              "přívody, fáze, jištění, hlavní jistič a případné omezení souběhů či stupňů dohřevu. "
              "Stávající symbol třífázového přívodu TČ sám neodpovídá ověřenému zapojení této splitové sestavy.", "",
              f"Modelová mezera vedle hydroboxu k zásobníku je **{r['clearance']['tank_side_gap_m']*1000:.1f} mm** "
              "v části, kde se jejich výšky překrývají. LG požaduje 200 mm po stranách. "
              f"Chybí tedy **{r['clearance']['missing_gap_m']*1000:.1f} mm**. "
              "Poloha musí být upravena před potvrzením montáže; touto kontrolou se zařízení neposouvají. "
              f"Horní odstup {r['clearance']['top_gap_m']*1000:.0f} mm je proti požadavku 250 mm dostatečný.", "",
              "## 9. Uzavření kontroly a nezbytné podklady", "",
              "Početně byly prověřeny zimní výkonová a denní bilance, přepočet 40/35 °C, nutné podmínky "
              "pro místnosti bez těles, kontrolní hydraulické cesty, objemy, základní expanzní rezerva a servisní mezera. "
              "Neuzavřené body se nerozepisují jako hotové ani jako požadavek na další PENB:", "",
              "- **Rozhodnutí o chodbách/WC:** doložit konkrétní přenos tepla a výsledné teploty, nebo upravit rozdělení zdrojů v místnostech.",
              "- **Výběr FCU:** výrobková identita IVAR/INNOVA, výkon při 40/35 °C a skutečném průtoku vody, potřebné otáčky a hluk v místě pobytu.",
              "- **QUANTUM:** výkon/UA při vodě 50–55 °C, tlaková charakteristika, objem výměníku, poloha čidla a slučitelnost konkrétní 2,5kW patrony se zástavbou.",
              "- **Provedení:** přesné trasy, měřicí rozsahy vyvážení, servisní mezera hydroboxu, elektrické přívody/fáze a schéma regulace.",
              "- **Zprovoznění:** průtok při všech kombinacích ventilů včetně zavřených, časování TV/topení, spínání patrony, směšování TV, expanze, počet startů a hluk.",
              "- **Další rozsah:** letní chladicí zátěže, skutečné trasy šesti kondenzátních odvodů a roční energie nejsou výsledkem této zimní kontroly. PENB řeší energetický specialista s těmito vstupy.", "",
              "## Podklady", "",
              f"- [LG – výkonové tabulky]({LG_SOURCE}); [LG – technický datový list, hydraulika a provozní obálka]({LG_ENGINEERING}); [LG – instalační návod, řízení TV]({LG_INSTALL}).",
              f"- [IVAR – technický list SL DC]({IVAR_SOURCE}); [IVAR – regulace]({IVAR_CONTROLS}); [Eurovent – referenční INNOVA SL600]({EUROVENT_SL600}).",
              f"- [QUANTUM – Q7-WWM]({QUANTUM}). Srovnávací Hu.Ray je uveden v technické zprávě VYT-01, nenahrazuje potvrzení QUANTUM.",
              "- [Vyhláška 264/2020 Sb., příloha 5, C.1 – návrhové vodivosti](https://www.zakonyprolidi.cz/cs/2020-264#prilohy).",
              "- Stavební část dokumentace, skladby, příloha VYT-02 a návrhové průtoky VZT.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-mixed-litres", type=float, default=300)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    results = run_checks(daily_mixed_l=args.daily_mixed_litres)
    Path("cache/heating_checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n")
    path = PROJECT_DIR/VYT/"D.1.2.1-VYT-03. Technické ověření vytápění a přípravy TV.md"
    path.write_text(report(results), encoding="utf-8")
    if args.pdf:
        from pdf_utils import markdown_to_pdf
        markdown_to_pdf(path, path.with_suffix(".pdf"))
    print(path)
    print("Heat loss [kW]", [round(c["heat_loss"]["total_w"]/1000, 3) for c in results["cases"]])
    print("DHW [kWh/day]", round(results["dhw"]["daily_kwh"], 3))
    print("Critical hydraulic route / available [kPa]", round(results["hydraulics"]["maximum_route_kpa"], 1), round(results["hydraulics"]["available_head_kpa"], 1))
    print("Hydrobox clearance pass:", results["clearance"]["passes"])


if __name__ == "__main__":
    main()
