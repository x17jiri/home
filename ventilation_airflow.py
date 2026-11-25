"""Check supplied room airflows against volumes in the current house model."""

import argparse
import json
from math import sqrt
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from roof_frame_3d import HouseInputs


def volume_under_ceiling(footprint, floor_z, profile):
    """Integrate a piecewise linear ceiling over a polygon, including its holes."""
    xmin, ymin, xmax, ymax = footprint.bounds
    if profile[0][0] > xmin or profile[-1][0] < xmax:
        raise ValueError("Ceiling profile does not cover the room")
    volume = 0.0
    for (x0, z0), (x1, z1) in zip(profile, profile[1:]):
        if x1 <= x0:
            raise ValueError("Ceiling profile X coordinates must increase")
        slope = (z1-z0)/(x1-x0)
        left, right = max(xmin, x0), min(xmax, x1)
        if slope > 0:
            left = max(left, x0+(floor_z-z0)/slope)
        elif slope < 0:
            right = min(right, x0+(floor_z-z0)/slope)
        elif z0 <= floor_z:
            continue
        if right <= left:
            continue
        region = footprint.intersection(box(left, ymin-1, right, ymax+1))
        if region.area:
            # An affine function integrates exactly as area × centroid height.
            volume += region.area*(z0+slope*(region.centroid.x-x0)-floor_z)
    return volume


def upper_ceiling_profile(inputs):
    """Finished SDK underside: two roof slopes and the flat section between them."""
    g = inputs.get
    width = g("HOUSE_WIDTH")
    plate_width, plate_height = g("WALL_PLATE_SIZE")
    purlin_width, purlin_height = g("PURLIN_SIZE")
    plate_top = g("WALL_PLATE_Z")+plate_height/2
    purlin_top = g("PURLIN_Z")+purlin_height/2
    offset = g("GYPSUM_PLASTERBOARD_BOTTOM")
    positions = g("PURLIN_X_POSITIONS")

    def height(x, index, direction):
        seat = (g("BWT")/2 if direction == 1 else width-g("BWT")/2)-direction*plate_width/2
        support = positions[index]-direction*purlin_width/2
        slope = (purlin_top-plate_top)/(support-seat)
        return plate_top+slope*(x-seat)+offset*sqrt(1+slope*slope)

    left = positions[0]+purlin_width/2
    right = positions[-1]-purlin_width/2
    flat = height(left, 0, 1)
    if abs(height(right, -1, -1)-flat) > 1e-8:
        raise ValueError("Upper ceiling is no longer symmetric; review its profile")
    return [(0.0, height(0, 0, 1)), (left, flat),
            (right, flat), (width, height(width, -1, -1))]


def check_room_airflows(source, ifc, airflows, rate=0.5):
    source, ifc = Path(source), Path(ifc)
    if ifc.stat().st_mtime < source.stat().st_mtime:
        raise ValueError("IFC predates house2.py; regenerate the model before checking volumes")
    if rate <= 0 or any(flow < 0 for flow in airflows.values()):
        raise ValueError("Air-change rate must be positive and supply airflows nonnegative")
    inputs = HouseInputs(source)
    g = inputs.get
    model = ifcopenshell.open(ifc)
    parts = {}
    for slab in model.by_type("IfcSlab"):
        properties = ifcopenshell.util.element.get_pset(slab, "BBIM_FloorLayer") or {}
        room = properties.get("RoomIdentifier")
        if room not in airflows:
            continue
        storey = ifcopenshell.util.element.get_container(slab)
        level = float(storey.Elevation)
        expected = 0.0 if room.startswith("0.") else g("UPPER_FLOOR_START")
        if abs(level-expected) > 1e-8:
            raise ValueError(f"Room {room}: IFC and source storey levels differ")
        floor_z = level+properties["StartHeight"]+properties["Thickness"]
        parts.setdefault(room, []).append((Polygon(json.loads(properties["Outline"])), floor_z))
    results = []
    for room, supply in airflows.items():
        if room not in parts:
            raise ValueError(f"Room {room} not found in IFC room floors")
        room_parts = parts[room]
        floor_z = room_parts[0][1]
        if any(abs(z-floor_z) > 1e-8 for _, z in room_parts):
            raise ValueError(f"Room {room} has multiple finished-floor levels")
        footprint = unary_union([polygon for polygon, _ in room_parts])
        if room.startswith("0."):
            ceiling_z = g("ground_floor_height")-g("CEILING_PLASTER_THICKNESS")
            profile = [(0.0, ceiling_z), (g("HOUSE_WIDTH"), ceiling_z)]
        else:
            profile = upper_ceiling_profile(inputs)
        volume = volume_under_ceiling(footprint, floor_z, profile)
        required = rate*volume
        results.append(dict(room=room, area_m2=footprint.area,
                            mean_clear_height_m=volume/footprint.area, volume_m3=volume,
                            required_m3_h=required, supply_m3_h=supply,
                            air_changes_h=supply/volume, passes=supply+1e-8 >= required))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("airflows", nargs="+", metavar="ROOM=M3/H")
    parser.add_argument("--source", type=Path, default=Path("house2.py"))
    parser.add_argument("--ifc", type=Path, default=Path("house2.ifc"))
    parser.add_argument("--rate", type=float, default=0.5)
    args = parser.parse_args()
    flows = dict((room, float(value)) for room, value in
                 (argument.split("=", 1) for argument in args.airflows))
    print(json.dumps(check_room_airflows(args.source, args.ifc, flows, args.rate),
                     ensure_ascii=False, indent=2))
