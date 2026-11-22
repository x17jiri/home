"""Paper-sized, editable single-line distribution-board diagrams."""

from dataclasses import dataclass
from itertools import groupby
from textwrap import wrap


@dataclass(frozen=True)
class Circuit:
    key: str
    group: str
    description: str
    kind: str
    room: str = ""
    cable: str = "—"
    protection: str = "— A"


def add_distribution_board(house, circuits):
    """Create native annotations; all layout distances below are paper millimetres.

    Device ratings, cables and earthing arrangement deliberately remain open.
    Bundled plan routes are not additional circuits. N/PE branches represent
    the conductors of each outgoing cable, as in the reference single-line view.
    """
    circuits = tuple(circuits)
    if not circuits or len({c.key for c in circuits}) != len(circuits):
        raise ValueError("Distribution-board circuits must have unique keys")
    pitch, first_x = 18, 69
    width = first_x+(len(circuits)-1)*pitch+10
    drawing = house.add_drawing(
        "rozvadec", x=width/2000, y=.09, z=1,
        radius=width/2000, height=.26, scale=1,
        storeys=[], door_annotations=False, automatic_plan_annotations=False,
    )

    def point(x, y):
        return (x/1000, y/1000)

    def line(x0, y0, x1, y1, name, *, style="solid", thickness=.18):
        return drawing.add_line(point(x0, y0), point(x1, y1),
                                style=style, line_width=thickness, name=f"rozvadec {name}")

    def text(x, y, value, name, *, size=2.1, align="center"):
        return drawing.add_text(point(x, y), value, font_size=size,
                                alignment=align, name=f"rozvadec {name}")

    def circle(x, y, name, radius=.55):
        drawing.add_circle(point(x, y), radius/1000, name=f"rozvadec {name}")

    def rectangle(x0, y0, x1, y1, name):
        drawing.add_rectangle(point(x0, y0), point(x1, y1), name=f"rozvadec {name}")

    def earth(x, y):
        for offset, half_width in ((0, 3), (-1.4, 2), (-2.8, 1)):
            line(x-half_width, y+offset, x+half_width, y+offset, "Earth electrode")

    def switch(x, identifier, *, poles=1, protective=False):
        line(x, 180, x, 166, f"{identifier} Upper connection")
        line(x, 157, x, 94, f"{identifier} Lower connection")
        line(x, 157, x-2, 163, f"{identifier} Open contact")
        for n in range(poles):
            y = 159.5-n*1.1
            line(x-2.2, y-1, x+.6, y+1, f"{identifier} Pole {n+1}")
        if protective:
            # Thermal/magnetic release mark beside the switching contact.
            drawing.add_poly_line(
                tuple(point(a, b) for a, b in ((x-2, 163), (x-3.3, 165.5),
                                              (x-4.3, 165), (x-3.3, 162.5), (x-2, 163))),
                name=f"rozvadec {identifier} Overcurrent release", line_width=.18,
            )
        circle(x, 180, f"{identifier} Supply junction")

    def cable_box(x, number, identifier, specification, half_width=7.5):
        rectangle(x-half_width, 80, x+half_width, 94, f"{identifier} Cable label")
        for y in (90, 85):
            line(x-half_width, y, x+half_width, y, f"{identifier} Cable label divider", thickness=.13)
        text(x, 92, number, f"{identifier} Outgoing number", size=1.9)
        text(x, 87.5, identifier, f"{identifier} Cable identifier", size=2)
        text(x, 82.5, specification, f"{identifier} Cable specification", size=1.8)

    text(2, 213, "3~ 400/230 V, 50 Hz   |   Soustava a parametry přívodu: doplnit",
         "Supply description", size=2.5, align="left")
    text(31, 198, "PŘÍVOD A UZEMNĚNÍ", "Incoming section heading", size=2.3)
    line(3, 193, 59, 193, "Incoming heading underline", thickness=.13)
    line(20, 180, width-1, 180, "Three-phase supply bus", thickness=.3)
    text(2, 180, "L1–L3", "Supply bus label", size=1.8, align="left")

    switch(20, "QM01", poles=3)
    text(22, 161, "QM01\nHlavní vypínač\n— A", "Main switch specification", size=1.8, align="left")
    cable_box(20, "PŘÍVOD", "WLN1", "Kabel: doplnit", half_width=10)
    line(20, 80, 20, 22, "Incoming cable")
    rectangle(16, 18, 24, 22, "RE Meter-board symbol")
    line(17, 20, 23, 20, "RE Meter-board bar", thickness=.65)
    text(20, 10, "RE\nPřívod", "Incoming source", size=2.3)

    circle(45, 180, "F001 Supply junction")
    line(45, 180, 45, 170, "F001 Supply connection")
    rectangle(42.5, 158, 47.5, 170, "F001 Surge protective device")
    line(42.5, 160, 47.5, 168, "F001 Varistor symbol")
    line(45, 158, 45, 22, "F001 Protective-earth connection")
    text(49, 162, "F001\nSvodič přepětí\nTyp: doplnit", "Surge protector specification", size=1.8, align="left")
    rectangle(40, 18, 50, 22, "HEP Main earthing terminal")
    text(45, 26, "HEP", "Main earthing terminal label", size=2.1)
    text(47, 48, "Zemnicí vodič\n— mm²", "Earthing conductor specification", size=1.8, align="left")
    line(45, 18, 45, 0, "Foundation earthing connection")
    earth(45, 0)
    text(45, -9, "Uzemnění\nFeZn: doplnit", "Earth electrode description", size=2)

    line(55, 112, width-1, 112, "Neutral bar", thickness=.13)
    line(45, 104, width-1, 104, "Protective-earth bar", thickness=.13)
    circle(45, 104, "HEP Protective-earth bar junction")
    text(53, 115, "N", "Neutral bar label", size=1.8)
    text(53, 107, "PE", "Protective-earth bar label", size=1.8)
    line(4, 70, width-1, 70, "Distribution-board enclosure boundary", style="dash-dot", thickness=.13)

    for group, entries in groupby(enumerate(circuits), key=lambda item: item[1].group):
        entries = tuple(entries)
        left, right = (first_x+entries[i][0]*pitch for i in (0, -1))
        text((left+right)/2, 198, f"{group}  ·  {len(entries)} okruhů",
             f"{group} Circuit group heading", size=2.4)
        line(left-7.5, 193, right+7.5, 193, f"{group} Heading underline", thickness=.13)

    for index, circuit in enumerate(circuits, 1):
        x = first_x+(index-1)*pitch
        identifier, cable_id = f"FA{index:02}", f"WL{index:02}"
        switch(x, identifier, poles=3 if circuit.kind == "three_phase" else 1, protective=True)
        text(x+2, 163, f"{identifier}\n{circuit.protection}\n{'3P' if circuit.kind == 'three_phase' else '1P'}",
             f"{identifier} Protection specification", size=1.9, align="left")
        for dx, y, conductor in ((-2.4, 112, "N"), (2.4, 104, "PE")):
            line(x, 98, x+dx, y, f"{identifier} {conductor} cable conductor", thickness=.13)
            circle(x+dx, y, f"{identifier} {conductor} terminal", radius=.5)
        cable_box(x, str(index), cable_id, circuit.cable)
        line(x, 80, x, 24, f"{identifier} Outgoing cable")
        if circuit.kind == "light":
            line(x, 24, x, 22, f"{identifier} Light connection")
            drawing.add_light_symbol(point(x, 20), radius=.002, color="black", line_width=.18,
                                    name=f"rozvadec {identifier} Light load")
        elif circuit.kind in ("socket", "three_phase"):
            drawing.add_socket_symbol(point(x, 24), "down", branch_length=.002,
                                     radius=.002, color="black", line_width=.18,
                                     name=f"rozvadec {identifier} Socket load")
            if circuit.kind == "three_phase":
                text(x, 15, "3~", f"{identifier} Three-phase load", size=1.8)
        else:
            rectangle(x-3.5, 18, x+3.5, 24, f"{identifier} Equipment load")
            text(x, 21, "FCU", f"{identifier} Equipment symbol label", size=1.8)
        purpose = {"light": "Světla", "socket": "Zásuvky", "three_phase": "3f přívod",
                   "fan_coil": "Fancoily"}[circuit.kind]
        description_lines = wrap(circuit.description, width=13)
        for row in range(1, len(description_lines)):
            # Bonsai treats leading '+' as a bullet; keep 'pokoj + KK' together.
            if description_lines[row].startswith("+ "):
                previous, separator, word = description_lines[row-1].rpartition(" ")
                if separator:
                    description_lines[row-1] = previous
                    description_lines[row] = f"{word} {description_lines[row]}"
        lines = [purpose, *description_lines]
        if circuit.room:
            lines.append(circuit.room)
        for row, value in enumerate(lines):
            text(x, 9-row*3.1, value, f"{identifier} Circuit description {row+1}", size=2)

    text(2, -27, "Jištění, proudové chrániče, průřezy kabelů a provedení přívodu budou doplněny.",
         "Unspecified electrical parameters", size=2.3, align="left")
    return drawing
