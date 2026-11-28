"""Eight FCU alternatives at mixed room temperatures; no model/plan regeneration.

Run with .venv-pdf/bin/python heating_combinations.py. Outputs a screening
worksheet in cache; does not regenerate geometry or the official report.
"""

import hashlib
import json
from dataclasses import replace
from itertools import product
from math import log
from pathlib import Path

from heating_checks import CP_AIR, DesignInputs
from heating_loss import Assumptions, SUPPLIES, calculate
from roof_frame_3d import HouseInputs


TEMPERATURES = {"0.01": 25, "0.02": 25, "0.03": 25, "0.04": 20,
                "0.05": 25, "1.01": 25, "1.02": 25, "1.03": 20}
EXTRACTS = {"0.05": 60, "1.01": 80, "1.02": 40, "1.03": 60}
# Net transfer routes inferred from the balanced 240 m3/h ventilation scheme.
# They are a heat-accounting assumption, not a completed door-transfer design.
TRANSFERS = [("0.01", "0.04", 40), ("0.02", "0.04", 40),
             ("0.03", "0.04", 40), ("0.04", "0.05", 60),
             ("0.04", "1.03", 60), ("1.01", "1.03", 40),
             ("1.03", "1.02", 40)]
REFERENCES = {
    "sl600": "https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275034",
    "sl600_full_flat_reference": "https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275035",
    "sl800": "https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275040",
    "bathroom": "https://www.thermannpro.cz/sortiment/fancoily/koupelnove-fancoily/",
}
# Reference heating watts at 45/40 water, 20 C room. Exact IVAR delivery and
# interpolation away from this condition still need a manufacturer selection.
REFERENCE_W = {"SL600": {"low": 1200, "medium": 2160},
               "SL800": {"low": 1470, "medium": 2590}}
SELECTED = dict(confirmed_date="2026-11-28", water_c=[45, 40],
                living_pair="SL800", hall="SL600")


def ventilation_loads(temperatures, outdoor_c=-15, recovery=.77):
    """Room air-heating loads, including heat gained/lost in transfer air.

    Positive = emitter heat required. Negative = incoming air heats the room.
    No recirculation or unmeasured bidirectional exchange is invented.
    """
    flow = sum(SUPPLIES.values())
    if flow != sum(EXTRACTS.values()) or not 0 <= recovery <= 1:
        raise ValueError("Invalid ventilation balance or recovery")
    extract_c = sum(q*temperatures[r] for r, q in EXTRACTS.items())/flow
    supply_c = outdoor_c+recovery*(extract_c-outdoor_c)
    loads = {}
    for room, temperature in temperatures.items():
        incoming = [(a, q) for a, b, q in TRANSFERS if b == room]
        outgoing = sum(q for a, b, q in TRANSFERS if a == room)
        if SUPPLIES.get(room, 0)+sum(q for _, q in incoming) != EXTRACTS.get(room, 0)+outgoing:
            raise ValueError(f"Unbalanced room airflow: {room}")
        loads[room] = CP_AIR*(SUPPLIES.get(room, 0)*(temperature-supply_c)
                              +sum(q*(temperature-temperatures[a]) for a, q in incoming))
    expected = CP_AIR*flow*(extract_c-supply_c)
    if abs(sum(loads.values())-expected) > 1e-8:
        raise ValueError("Ventilation heat balance does not close")
    return dict(extract_c=extract_c, supply_c=supply_c, rooms_w=loads, total_w=expected)


def output_w(model, speed, supply_c, return_c, indoor_c):
    """First-order LMTD scaling from a FIXED 45/40/20 reference."""
    if not supply_c > return_c > indoor_c:
        raise ValueError("Water temperatures must exceed room temperature")
    lmtd = (supply_c-return_c)/log((supply_c-indoor_c)/(return_c-indoor_c))
    reference = 5/log(25/20)
    return REFERENCE_W[model][speed]*lmtd/reference


def run():
    cached = json.loads(Path("cache/heating_loss.json").read_text())
    for name in ("house2.py", "house2.ifc"):
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != cached["input_sha256"][name]:
            raise ValueError("Geometry is stale; run heating_loss.py first")
    geometry = dict(inputs=DesignInputs(HouseInputs(Path("house2.py"))), rooms=cached["geometry"])
    assumptions = Assumptions(outdoor_c=-15, basement_c=5)
    ventilation = ventilation_loads(TEMPERATURES, assumptions.outdoor_c, assumptions.recovery)
    by_temperature = {t: calculate(geometry, replace(assumptions, indoor_c=t))
                      for t in set(TEMPERATURES.values())}
    rooms = {}
    for room, temperature in TEMPERATURES.items():
        components = by_temperature[temperature]["rooms"][room]["components_w"].copy()
        components["ventilation"] = ventilation["rooms_w"][room]
        rooms[room] = dict(temperature_c=temperature, components_w=components,
                           loss_before_internal_wall_transfer_w=sum(components.values()))
    total = sum(v["loss_before_internal_wall_transfer_w"] for v in rooms.values())
    rows = []
    for (supply, ret), living, hall in product([(40, 35), (45, 40)], REFERENCE_W, REFERENCE_W):
        bedroom = output_w("SL600", "low", supply, ret, 25)
        living_pair = 2*output_w(living, "low", supply, ret, 25)
        hall_output = output_w(hall, "medium", supply, ret, 20)
        known = 3*bedroom+living_pair+hall_output
        # A zero bathroom contribution makes this an explicit lower bound on
        # estimated combined output. It is NOT the actual BT400 output.
        deficits = {r: max(0, rooms[r]["loss_before_internal_wall_transfer_w"]-bedroom)
                    for r in ("0.01", "0.02", "0.03")}
        deficits["1.01"] = max(0, rooms["1.01"]["loss_before_internal_wall_transfer_w"]-living_pair)
        rows.append(dict(water_c=[supply, ret], living_pair=living, hall=hall,
                         bedroom_each_w=bedroom, living_pair_w=living_pair,
                         hall_medium_w=hall_output, known_output_excluding_bathroom_w=known,
                         aggregate_margin_excluding_bathroom_w=known-total,
                         local_shortfall_before_internal_wall_transfer_w=deficits,
                         occupied_room_screen_passes=not any(deficits.values())))
    return dict(assumptions=dict(outdoor_c=-15, basement_c=5, room_temperatures_c=TEMPERATURES,
                                recovery=assumptions.recovery,
                                internal_wall_transfer="not calculated; cancels from whole-house total",
                                bathroom_low_output="unknown; electric panel excluded"),
                selected_alternative=SELECTED,
                input_sha256=cached["input_sha256"], references=REFERENCES,
                ventilation=ventilation, rooms=rooms, total_loss_w=total, combinations=rows)


def worksheet(result):
    lines = ["# FCU combinations — mixed room temperatures", "",
             "Screening worksheet: outdoors −15 °C, basement +5 °C, both hallways +20 °C; "
             "bedrooms, bathroom, living room and separate WC +25 °C. Existing design-conductivity "
             "corrections and conservative envelope assumptions are retained.", "",
             "**Selected by the investor on 2026-11-28:** 45/40 °C water, two SL800s in the living "
             "room at low speed and one SL600 in the downstairs hallway at medium speed; bedrooms "
             "retain SL600s and the bathroom candidate is THE-BT400. This is the enhanced-comfort "
             "case (25 °C rooms / 20 °C hallways). Lower normal-operation water temperatures and "
             "the statutory PENB profile remain separate questions. Equipment positions, revised "
             "seven-branch hydraulics and the official report have not been updated by this worksheet.", "",
             f"**Whole-house loss: {result['total_loss_w']/1000:.3f} kW.** Internal partition heat "
             "transfer cancels from this total, but is not calculated for individual rooms.", "",
             "The balanced 240 m³/h ventilation scheme gives an extract temperature of "
             f"{result['ventilation']['extract_c']:.2f} °C and supply temperature "
             f"{result['ventilation']['supply_c']:.2f} °C at 77% recovery. Net transfer air follows "
             "the assumed door/stair routes in the calculation; final transfer openings are not designed.", "",
             "| Room | Temperature [°C] | Heat required before partition transfer [W] |",
             "|---|---:|---:|"]
    for room, value in result["rooms"].items():
        lines.append(f"| {room} | {value['temperature_c']} | "
                     f"{value['loss_before_internal_wall_transfer_w']:.0f} |")
    lines += ["", "## Eight combinations", "",
              "All outputs are first-order LMTD estimates from reference AirLeaf data at 45/40/20. "
              "They are not confirmed performance selections for the actual IVAR delivery. "
              "Bedrooms and living-room units run low; the ground hallway runs medium at 20 °C.", "",
              "| Water [°C] | Living-room pair | Ground hall | Known output, excluding BT400 [kW] | "
              "Aggregate margin, excluding BT400 [kW] | Bedrooms/living screen |",
              "|---|---|---|---:|---:|---|"]
    for row in result["combinations"]:
        water = "/".join(map(str, row["water_c"]))
        screen = "Potentially adequate" if row["occupied_room_screen_passes"] else "Local shortfall"
        lines.append(f"| {water} | 2 × {row['living_pair']} | {row['hall']} | "
                     f"{row['known_output_excluding_bathroom_w']/1000:.3f} | "
                     f"{row['aggregate_margin_excluding_bathroom_w']/1000:+.3f} | {screen} |")
    lines += ["", "## Interpretation and limits", "",
              "All eight have sufficient estimated combined output even before adding the unknown "
              "BT400 output. This does not establish the specified temperatures in every room:", "",
              "- At 40/35, room 3 and the living room have local deficits even before heat transfer "
              "through partitions to cooler hallways; increasing the hallway unit does not establish "
              "delivery of this heat to rooms at 25 °C while keeping the hallway at 20 °C.",
              "- At 45/40, the pair of SL600s still falls short in the living room. The pair of SL800s "
              "and either hallway option passes this preliminary occupied-room screen. Partition "
              "losses and the unheated upper hallway/WC still need a heat-transfer check.",
              "- Thermann publishes BT400 heating output at 50 °C inlet/20 °C room, not low-speed "
              "output at the requested conditions. No value is invented, and the electric panel "
              "is excluded. Its required room output is listed above before partition transfer.",
              "- This is an emitter comparison. Heat-pump capacity, DHW downtime, room warm-up, "
              "pipe/duct losses and cooling are separate checks.", "", "## References", ""]
    lines += [f"- [{name}]({url})" for name, url in result["references"].items()]
    return "\n".join(lines)+"\n"


if __name__ == "__main__":
    result = run()
    destination = Path("cache")
    destination.mkdir(exist_ok=True)
    (destination/"heating_combinations.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    (destination/"heating_combinations.md").write_text(worksheet(result))
    print(worksheet(result))
