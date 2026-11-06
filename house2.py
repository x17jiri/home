"""Alternative house: export with `python3 house2.py`; draw with `ground`, `ceiling`, `upper`, or `roof`."""

from pathlib import Path
from math import floor
import math
import sys

import ifcopenshell.api.pset
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.root
import ifcopenshell.util.element
import numpy as np
from shapely.geometry import Polygon, box

from ifc_utils import House, offset_plane, plane_height_at, window_area


HOUSE_WIDTH = 8.75
HOUSE_DEPTH = 8.75
BWT = 0.24
INNER_BWT = 0.175
PARTITION_THICKNESS = 0.115
DRY_WALL_WIDTH = 0.10
FACADE_INSULATION_THICKNESS = 0.20
GARDEN_ROOMS_DEPTH = 3.47  # Clear depth between the divider and inside garden wall.
GARDEN_ROOMS_WALL_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT
THIRD_ROOM_NARROW_WIDTH = HOUSE_WIDTH/2.0 - BWT - 0.125-1.0-0.1-0.2
THIRD_ROOM_NARROW_DEPTH = 1.375  # Clear depth of the narrowed garden-side end.
THIRD_ROOM_NARROW_WALL_X = BWT+THIRD_ROOM_NARROW_WIDTH+INNER_BWT
THIRD_ROOM_WIDTH = 3.47  # Clear width of the left street-side room.
THIRD_ROOM_WALL_X = BWT+THIRD_ROOM_WIDTH+INNER_BWT
THIRD_ROOM_STEP_Y = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_NARROW_DEPTH
STAIRWAY_WIDTH = 2.25  # Clear distance from the straight room 3 wall.
STAIRWAY_WALL_X = THIRD_ROOM_WALL_X+STAIRWAY_WIDTH+INNER_BWT
BATHROOM_DEPTH = 2.8  # Clear depth from the inside front wall.
BATHROOM_PARTITION_Y = BWT+BATHROOM_DEPTH
STAIRWAY_OPENING_START_Y = BATHROOM_PARTITION_Y+PARTITION_THICKNESS

LIVING_ROOM_WIDTH = THIRD_ROOM_WIDTH + INNER_BWT - DRY_WALL_WIDTH
LIVING_ROOM_STAIR_CLEARANCE = 1.10  # Clear distance to the stair-facing wall surface.
KITCHEN_UNIT_SIZE = (0.64, 0.64, 0.75)
KITCHEN_WALL_GAP = 0.03  # Same 350 mm centre offset as the old house's 640 mm units.
KITCHEN_COOKER_SINK_GAP = 0.06  # Old house: 700 mm centre spacing between 640 mm units.

GROUND_WALL_BASE_COURSE_HEIGHT = 0.20
GROUND_WALL_BASE_COURSE_MATERIAL = "Liapor brick"
ground_floor_height = GROUND_WALL_BASE_COURSE_HEIGHT + 2.625
CEMFLOW_AND_FINISH_THICKNESS = 0.065
GROUND_FLOOR_INSULATION_THICKNESS = 0.12
GROUND_FLOOR_THICKNESS = GROUND_FLOOR_INSULATION_THICKNESS+CEMFLOW_AND_FINISH_THICKNESS
CEILING_THICKNESS = 0.21
GARDEN_CEILING_BEAM_LENGTH = math.ceil(GARDEN_ROOMS_DEPTH/0.25)*0.25
GARDEN_CEILING_STRUCTURE = [
    "beam",
    "wide", "beam", "wide", "beam", "wide", "beam", "wide", "beam",
    "narrow", "beam", "narrow", "beam", "narrow", "beam", "narrow", "beam", "narrow", "beam",
    "wide", "beam", "wide", "beam", "wide", "beam", "wide", "beam", "wide", "beam",
]
GARDEN_CEILING_WIDTH = sum(
    {"beam": 0.17, "wide": 0.455, "narrow": 0.33}[item]
    for item in GARDEN_CEILING_STRUCTURE
)
THIRD_ROOM_CEILING_BEAM_LENGTH = math.ceil(THIRD_ROOM_WIDTH/0.25)*0.25
THIRD_ROOM_CEILING_STRUCTURE = [
    "beam",
    "wide", "beam", "wide", "beam", "wide", "beam", "wide", "beam",
    "wide", "beam", "wide", "beam", "wide", "beam",
]
THIRD_ROOM_CEILING_WIDTH = sum(
    {"beam": 0.17, "wide": 0.455}[item]
    for item in THIRD_ROOM_CEILING_STRUCTURE
)
UPPER_FLOOR_THICKNESS = 0.03+CEMFLOW_AND_FINISH_THICKNESS
UPPER_FLOOR_START = ground_floor_height+CEILING_THICKNESS
UPPER_FINISHED_FLOOR_HEIGHT = UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS
UPPER_RING_BEAM_HEIGHT = 0.24
NADEZDIVKA = 1.125+0.05+UPPER_RING_BEAM_HEIGHT
WALL_PLATE_SIZE = (0.16, 0.12)
WALL_PLATE_OVERHANG = 0.30
WALL_PLATE_Z = UPPER_FLOOR_START+NADEZDIVKA+WALL_PLATE_SIZE[1]/2
PURLIN_SIZE = (0.16, 0.28)
PURLIN_X_POSITIONS = (BWT+2.8-PURLIN_SIZE[0]/2.0, HOUSE_WIDTH-BWT-2.8+PURLIN_SIZE[0]/2.0)
PURLIN_CENTER_HEIGHT = 3.5  # Above the upper-floor storey datum / ceiling top.
PURLIN_Z = UPPER_FLOOR_START+PURLIN_CENTER_HEIGHT
RAFTER_THICKNESS = 0.08
RAFTER_HEIGHT = 0.20
RAFTER_SIZE = (RAFTER_THICKNESS, RAFTER_HEIGHT)
RAFTER_Z_OFFSET = -0.05  # Perpendicular to the support-contact roof plane.
RAFTER_SPACING = 0.67
RAFTER_FIRST_Y = -0.125
RAFTER_LAST_Y = HOUSE_DEPTH+0.125
ROOF_EAVE_OVERHANG = .6
ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.20
ROOF_EAVE_CUT_Z = WALL_PLATE_Z-WALL_PLATE_SIZE[1]/2-ROOF_EAVE_DROP_BELOW_WALL_PLATE
ROOF_GABLE_OVERHANG = 0.25
CHIMNEY_SIZE = 0.40
CHIMNEY_STAIR_CLEARANCE = 1.0  # Clear plan distance from the upper stair arrival.
CHIMNEY_FLUE_DIAMETER = 0.20
CHIMNEY_ABOVE_ROOF = 0.65
ROOF_EAVE_SETBACK = 0.02
# Same roof build-up as house_ifc.py; offsets are normal to each slope.
THERMAL_INSULATION_UNDER_RAFTERS = 0.14
VAPOUR_BARRIER_THICKNESS = 0.015
INSTALLATION_SPACE_THICKNESS = 0.040
GYPSUM_PLASTERBOARD_THICKNESS = 0.025
MDF_THICKNESS = 0.015
UNDERLAY_THICKNESS = 0.001
COUNTER_BATTEN_SIZE = (0.06, 0.06)
TILE_BATTEN_SIZE = (0.06, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_THICKNESS = 0.03
ROOF_TILE_PATTERN_WIDTH = 0.30
THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM = RAFTER_Z_OFFSET-THERMAL_INSULATION_UNDER_RAFTERS
VAPOUR_BARRIER_BOTTOM = THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM-VAPOUR_BARRIER_THICKNESS
GYPSUM_PLASTERBOARD_BOTTOM = VAPOUR_BARRIER_BOTTOM-INSTALLATION_SPACE_THICKNESS-GYPSUM_PLASTERBOARD_THICKNESS
MDF_BOTTOM = RAFTER_Z_OFFSET+RAFTER_HEIGHT
UNDERLAY_BOTTOM = MDF_BOTTOM+MDF_THICKNESS
COUNTER_BATTEN_BOTTOM = UNDERLAY_BOTTOM+UNDERLAY_THICKNESS
TILE_BATTEN_BOTTOM = COUNTER_BATTEN_BOTTOM+COUNTER_BATTEN_SIZE[1]
ROOF_TILE_BOTTOM = TILE_BATTEN_BOTTOM+TILE_BATTEN_SIZE[1]
# Put the remainder into one central gap, retaining the regular spacing elsewhere.
rafter_interval_count = max(1, math.floor((RAFTER_LAST_Y-RAFTER_FIRST_Y+1e-9)/RAFTER_SPACING))
rafter_middle_interval = rafter_interval_count//2
rafter_extra_spacing = RAFTER_LAST_Y-RAFTER_FIRST_Y-rafter_interval_count*RAFTER_SPACING
RAFTER_Y_POSITIONS = tuple(
    RAFTER_FIRST_Y+index*RAFTER_SPACING+(rafter_extra_spacing if index>rafter_middle_interval else 0)
    for index in range(rafter_interval_count+1)
)
STAIR_FLIGHT_WIDTH = 1.05
STAIR_LANDING_LENGTH = 1.05
STAIR_TREAD_LENGTH = 0.27
STAIR_LOWER_RISERS = 8
STAIR_UPPER_RISERS = 8
STAIR_LOWER_RUN_LENGTH = (STAIR_LOWER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_UPPER_RUN_LENGTH = (STAIR_UPPER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_RISER_HEIGHT = (UPPER_FINISHED_FLOOR_HEIGHT-GROUND_FLOOR_THICKNESS)/(STAIR_LOWER_RISERS+STAIR_UPPER_RISERS)
STAIR_FLIGHT_GAP = 0.15
STAIR_LEFT_X = THIRD_ROOM_WALL_X
STAIR_UPPER_CENTER_X = STAIR_LEFT_X+STAIR_FLIGHT_WIDTH/2
STAIR_LOWER_CENTER_X = STAIR_UPPER_CENTER_X+STAIR_FLIGHT_WIDTH+STAIR_FLIGHT_GAP
STAIR_RIGHT_X = STAIR_LOWER_CENTER_X+STAIR_FLIGHT_WIDTH/2
STAIR_LANDING_START_Y = BWT
STAIR_LANDING_END_Y = STAIR_LANDING_START_Y+STAIR_LANDING_LENGTH
STAIR_LOWER_START_Y = STAIR_LANDING_END_Y+STAIR_LOWER_RUN_LENGTH
STAIR_UPPER_END_Y = STAIR_LANDING_END_Y+STAIR_UPPER_RUN_LENGTH
LIVING_ROOM_DEPTH = HOUSE_DEPTH-BWT-STAIR_UPPER_END_Y-LIVING_ROOM_STAIR_CLEARANCE-DRY_WALL_WIDTH
CHIMNEY_CENTER = (HOUSE_WIDTH/2.0-0.5, STAIR_UPPER_END_Y+CHIMNEY_STAIR_CLEARANCE+CHIMNEY_SIZE/2)
STAIR_WAIST_THICKNESS = 0.15
STAIR_RAILING_HEIGHT = 1.0
if STAIR_RIGHT_X > HOUSE_WIDTH-BWT+1e-9:
    raise ValueError("rotated stairs do not fit between room 3 and the west wall")
if max(STAIR_LOWER_START_Y, STAIR_UPPER_END_Y) > GARDEN_ROOMS_WALL_Y+1e-9:
    raise ValueError("rotated stairs reach the garden-room dividing wall")
if STAIR_UPPER_END_Y > THIRD_ROOM_STEP_Y+INNER_BWT+1e-9:
    raise ValueError("upper stair flight must fit alongside the straight room 3 wall")
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
ENTRANCE_OPENING_WIDTH = 1.125
ENTRANCE_DOOR_WIDTH = 0.9
ENTRANCE_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ENTRANCE_CLEAR_HEIGHT = 2.1
ROOM_DOOR_WIDTH = 0.9
ROOM_DOOR_OPENING_WIDTH = 1.0
ROOM_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ROOM_DOOR_CLEAR_HEIGHT = 2.1
GARDEN_DOOR_CENTER_CLEARANCE = 0.125
BATHROOM_DOOR_SIDE_CLEARANCE = 0.125
ENTRANCE_OPENING_AT = 3.375  # Along the west wall, measured from its start.
ROOM_WINDOW_WIDTH = 1.75
GROUND_WINDOW_TOP_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+2.25
GROUND_WINDOW_SILL_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+0.875
UPPER_WINDOW_WIDTH = 1.25
UPPER_BACK_WINDOW_WIDTH = 3.0
UPPER_FRONT_WINDOW_EAST_CLEARANCE = 1.625
UPPER_WINDOW_HEIGHT = GROUND_WINDOW_TOP_HEIGHT-GROUND_WINDOW_SILL_HEIGHT
UPPER_WINDOW_SILL_HEIGHT = UPPER_FLOOR_THICKNESS+GROUND_WINDOW_SILL_HEIGHT-GROUND_FLOOR_THICKNESS
UPPER_WINDOW_TOP_HEIGHT = UPPER_WINDOW_SILL_HEIGHT+UPPER_WINDOW_HEIGHT
BATHROOM_WINDOW_WIDTH = 0.75
BATHROOM_WINDOW_HEIGHT = 0.75
BATHROOM_WINDOW_CENTER_X = (STAIRWAY_WALL_X+HOUSE_WIDTH-BWT)/2
WINDOW_POSITION_STEP = 0.125

PROJECT_DIR = Path("projekt2")
DIR_ARCHITEKTONICKO_STAVEBNI_RESENI = PROJECT_DIR / "D1.1. Architektonicko Stavební Řešení"
PDF_GROUND = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.1. Půdorys 1.NP.pdf"
PDF_CEILING = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.2. Strop nad 1.NP.pdf"
PDF_UPPER = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.3. Půdorys 2.NP.pdf"
PDF_ROOF = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.4. Krov.pdf"
SECTION_OUTLINE_WIDTH = 0.3

house = House("House 2", mirror_x=False, colors={"wall": "#ffffff", "window": "#ffffff"})
ground = house.storey("Ground floor", elevation=0)
ceiling_storey = house.storey("Ceiling", elevation=ground_floor_height)
upper = house.storey("Upper floor", elevation=UPPER_FLOOR_START)

load_bearing_wall = house.wall_type(
    "Load bearing wall - VPC 240 mm",
    layers=[("Brick", BWT), "axis"],
)
load_bearing_wall_inner = house.wall_type(
    "Load bearing wall - VPC 175 mm",
    layers=[("Brick", INNER_BWT), "axis"],
)
partition_wall = house.wall_type(
    "Partition wall - VPC 115 mm",
    layers=[("Brick", PARTITION_THICKNESS)],  # Centred on its reference line.
)
dry_wall = house.wall_type(
    f"drywall - {DRY_WALL_WIDTH*1000:g} mm", layers=[("SDK", DRY_WALL_WIDTH)], color="#dfefcf",
)

# Outer-face reference lines, with all material toward the interior.
# Front/back span the full width; side walls fit between them.
wall_front_g = ground.wall(
    (0, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=ground_floor_height,
)
wall_west_g = ground.wall(
    (HOUSE_WIDTH, BWT), (HOUSE_WIDTH, HOUSE_DEPTH-BWT),
    wall_type=load_bearing_wall, height=ground_floor_height,
)
wall_back_g = ground.wall(
    (HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=ground_floor_height,
)
wall_east_g = ground.wall(
    (0, HOUSE_DEPTH-BWT), (0, BWT), wall_type=load_bearing_wall, height=ground_floor_height,
)
wall_garden_rooms_g = ground.wall(
    (BWT, GARDEN_ROOMS_WALL_Y), (HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_garden_partition_g = ground.wall(
    (HOUSE_WIDTH/2, GARDEN_ROOMS_WALL_Y+INNER_BWT),
    (HOUSE_WIDTH/2, HOUSE_DEPTH-BWT),
    wall_type=partition_wall, height=ground_floor_height,
)
wall_third_room_g = ground.wall(
    (THIRD_ROOM_WALL_X, BWT), (THIRD_ROOM_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_third_room_g.Name = "Hallway - Pokoj 3 lower wall"
# The return's room-facing side sets the clear 1.25 m depth of the narrow end.
wall_third_room_return_g = ground.wall(
    (THIRD_ROOM_NARROW_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
    (THIRD_ROOM_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_third_room_return_g.Name = "Hallway - Pokoj 3 wall return"
wall_third_room_top_g = ground.wall(
    (THIRD_ROOM_NARROW_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
    (THIRD_ROOM_NARROW_WALL_X, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_third_room_top_g.Name = "Hallway - Pokoj 3 upper wall"
wall_stairway_g = ground.wall(
    (STAIRWAY_WALL_X, BWT), (STAIRWAY_WALL_X, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_stairway_g.Name = "Stairway - hallway and bathroom wall"
wall_bathroom_partition_g = ground.wall(
    (STAIRWAY_WALL_X, BATHROOM_PARTITION_Y+PARTITION_THICKNESS/2),
    (HOUSE_WIDTH-BWT, BATHROOM_PARTITION_Y+PARTITION_THICKNESS/2),
    wall_type=partition_wall, height=ground_floor_height,
)
wall_bathroom_partition_g.Name = "Hallway - bathroom partition"
stairway_opening = wall_stairway_g.add_opening(
    name="Hallway - stairway opening",
    at=STAIRWAY_OPENING_START_Y-wall_stairway_g.start[1],
    width=GARDEN_ROOMS_WALL_Y-STAIRWAY_OPENING_START_Y,
    height=ROOM_DOOR_HEIGHT,
)
entrance_door = wall_west_g.add_door(
    name="Entrance door",
    at=ENTRANCE_OPENING_AT,
    opening_width=ENTRANCE_OPENING_WIDTH,
    width=ENTRANCE_DOOR_WIDTH,
    height=ENTRANCE_DOOR_HEIGHT,
    clear_height=ENTRANCE_CLEAR_HEIGHT,
    sill_height=GROUND_FLOOR_THICKNESS,
    operation="SINGLE_SWING_RIGHT",
)
pokoj1_door = wall_garden_rooms_g.add_door(
    name="Pokoj 1 door",
    at=(HOUSE_WIDTH/2-GARDEN_DOOR_CENTER_CLEARANCE
        -ROOM_DOOR_OPENING_WIDTH-wall_garden_rooms_g.start[0]),
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_RIGHT",
)
pokoj2_door = wall_garden_rooms_g.add_door(
    name="Pokoj 2 door",
    at=HOUSE_WIDTH/2+GARDEN_DOOR_CENTER_CLEARANCE-wall_garden_rooms_g.start[0],
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_LEFT",
)
pokoj3_door = wall_third_room_top_g.add_door(
    name="Pokoj 3 door",
    at=(wall_third_room_top_g.end[1]-wall_third_room_top_g.start[1]-ROOM_DOOR_OPENING_WIDTH)/2,
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_RIGHT",
)
bathroom_door = wall_bathroom_partition_g.add_door(
    name="Koupelna door",
    at=BATHROOM_DOOR_SIDE_CLEARANCE,
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_LEFT",
    reverse_swing=True,
)
ground_load_bearing_walls = (
    wall_front_g, wall_west_g, wall_back_g, wall_east_g, wall_garden_rooms_g, wall_third_room_g,
    wall_third_room_return_g, wall_third_room_top_g, wall_stairway_g,
)
# Apply the base course to all ground-floor masonry walls.
# Add subsequent ground-floor walls above this common finishing pass.
for wall in ground.walls:
    load_bearing = wall in ground_load_bearing_walls
    role = "load bearing" if load_bearing else "partition"
    material_set = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
    wall_material = material_set.MaterialLayers[0].Material.Name
    construction = "VPC" if wall_material == "Brick" else wall_material
    layers = [
        (GROUND_WALL_BASE_COURSE_MATERIAL, GROUND_WALL_BASE_COURSE_HEIGHT),
        (wall_material, wall.height-GROUND_WALL_BASE_COURSE_HEIGHT),
    ]
    wall.set_vertical_material_layers(
        layers,
        type_name=f"Ground {role} wall - {construction} {wall.thickness*1000:g} mm - Liapor base course",
    )
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": load_bearing})

floor_layer_settings = dict(
    thickness=GROUND_FLOOR_THICKNESS,
    insulation_thickness=GROUND_FLOOR_INSULATION_THICKNESS,
    insulation_material=FLOOR_INSULATION_MATERIAL,
    buildup_material=FLOOR_BUILDUP_MATERIAL,
    color="#ffff80",
)
pokoj1 = ground.floor_layer(
    "Pokoj 1", room_id="0.01",
    outline=(
        (BWT, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH/2-PARTITION_THICKNESS/2, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH/2-PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT),
        (BWT, HOUSE_DEPTH-BWT),
    ),
    **floor_layer_settings,
)
pokoj2 = ground.floor_layer(
    "Pokoj 2", room_id="0.02",
    outline=(
        (HOUSE_WIDTH/2+PARTITION_THICKNESS/2, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
        (HOUSE_WIDTH/2+PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT),
    ),
    **floor_layer_settings,
)
pokoj3 = ground.floor_layer(
    "Pokoj 3", room_id="0.03",
    outline=(
        (BWT, BWT), (THIRD_ROOM_WALL_X-INNER_BWT, BWT),
        (THIRD_ROOM_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
        (THIRD_ROOM_NARROW_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
        (THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y), (BWT, GARDEN_ROOMS_WALL_Y),
    ),
    **floor_layer_settings,
)
# Extend the same room through the opening, following room 3's stepped wall.
hallway_outline = Polygon((
    (THIRD_ROOM_WALL_X, BWT), (HOUSE_WIDTH-BWT, BWT),
    (HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y),
    (THIRD_ROOM_NARROW_WALL_X, GARDEN_ROOMS_WALL_Y),
    (THIRD_ROOM_NARROW_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
    (THIRD_ROOM_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
)).intersection(box(0, STAIRWAY_OPENING_START_Y, HOUSE_WIDTH, GARDEN_ROOMS_WALL_Y))
# Stop at each flight's footprint; the upper flight's underside stays outside
# the hallway, even though there is headroom beneath its upper treads.
for center_x, end_y in (
    (STAIR_LOWER_CENTER_X, STAIR_LOWER_START_Y),
    (STAIR_UPPER_CENTER_X, STAIR_UPPER_END_Y),
):
    hallway_outline = hallway_outline.difference(box(
        center_x-STAIR_FLIGHT_WIDTH/2, STAIR_LANDING_END_Y,
        center_x+STAIR_FLIGHT_WIDTH/2, end_y,
    ))
chodba = ground.floor_layer(
    "Chodba", room_id="0.04",
    outline=tuple(hallway_outline.exterior.coords)[:-1],
    **floor_layer_settings,
)
koupelna = ground.floor_layer(
    "Koupelna", room_id="0.05",
    outline=(
        (STAIRWAY_WALL_X, BWT), (HOUSE_WIDTH-BWT, BWT),
        (HOUSE_WIDTH-BWT, BATHROOM_PARTITION_Y), (STAIRWAY_WALL_X, BATHROOM_PARTITION_Y),
    ),
    **floor_layer_settings,
)
ground_room_floors = (pokoj1, pokoj2, pokoj3, chodba, koupelna)

# The back wall runs toward decreasing X: `at` is measured from its right end.
window_pokoj1 = wall_back_g.add_window(
    name="Pokoj 1 window",
    at=round((wall_back_g.start[0]-Polygon(pokoj1.outline).centroid.x-ROOM_WINDOW_WIDTH/2)
             / WINDOW_POSITION_STEP)*WINDOW_POSITION_STEP,
    width=ROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_SILL_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
window_pokoj2 = wall_back_g.add_window(
    name="Pokoj 2 window",
    at=round((wall_back_g.start[0]-Polygon(pokoj2.outline).centroid.x-ROOM_WINDOW_WIDTH/2)
             / WINDOW_POSITION_STEP)*WINDOW_POSITION_STEP,
    width=ROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_SILL_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
window_pokoj3 = wall_front_g.add_window(
    name="Pokoj 3 window",
    at=BWT+THIRD_ROOM_WIDTH/2-wall_front_g.start[0]-ROOM_WINDOW_WIDTH/2,
    width=ROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_SILL_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
window_koupelna = wall_front_g.add_window(
    name="Koupelna window",
    at=HOUSE_WIDTH-BWT-0.25-BATHROOM_WINDOW_WIDTH,
    width=BATHROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_TOP_HEIGHT-BATHROOM_WINDOW_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
ground_room_windows = {
    pokoj1.room_id: (window_pokoj1,),
    pokoj2.room_id: (window_pokoj2,),
    pokoj3.room_id: (window_pokoj3,),
    chodba.room_id: (),
    koupelna.room_id: (window_koupelna,),
}

# Bathroom grid, garden to street: door/WC, clear space/basin, shower/services.
bathroom_right_x = HOUSE_WIDTH-BWT
bathroom_row_depth = BATHROOM_DEPTH/3
bathroom_toilet = ground.asset(
    "WC", asset="toilet_without_cistern",
    center=(bathroom_right_x-0.53/2-0.2, BWT+2.5*bathroom_row_depth),
    start_height=GROUND_FLOOR_THICKNESS,
    rotation=-90,
)
bathroom_basin = ground.asset(
    "Umyvadlo", asset="basin_large",
    center=(bathroom_right_x-0.55/2-0.1, BWT+1.5*bathroom_row_depth),
    start_height=GROUND_FLOOR_THICKNESS+0.85-0.25,
    rotation=-90,
)
bathroom_shower = ground.asset(
    "Sprcha", asset="shower_90x90",
    center=(STAIRWAY_WALL_X+0.55, BWT+0.55),
    start_height=GROUND_FLOOR_THICKNESS,
)
bathroom_services_center_x = bathroom_right_x-(bathroom_right_x-STAIRWAY_WALL_X)/4
bathroom_hydrobox = ground.furniture(
    "Hydro-\nbox", kind="USERDEFINED",
    size=(0.8, 0.5, 0.9),
    center=(bathroom_services_center_x, BWT+0.3),
    start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
)
bathroom_water_meter = ground.furniture(
    "Vodo-\nměr", kind="USERDEFINED",
    size=(0.6, 0.55, 0.9),
    center=(bathroom_services_center_x, BWT+0.7),
    start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
)

# Stairs use the ceiling and future upper-floor levels.
lower_stairs = ground.stair(
    (STAIR_LOWER_CENTER_X, STAIR_LOWER_START_Y),
    (STAIR_LOWER_CENTER_X, STAIR_LANDING_END_Y),
    name="Lower stair flight",
    width=STAIR_FLIGHT_WIDTH,
    start_height=GROUND_FLOOR_THICKNESS,
    height=STAIR_RISER_HEIGHT*STAIR_LOWER_RISERS,
    risers=STAIR_LOWER_RISERS,
    underside="sloped",
    waist_thickness=STAIR_WAIST_THICKNESS,
)
middle_stair_landing = ground.stair_landing(
    (STAIR_LEFT_X, STAIR_LANDING_START_Y), (STAIR_RIGHT_X, STAIR_LANDING_END_Y),
    name="Middle stair landing",
    height=lower_stairs.end_height,
    thickness=STAIR_WAIST_THICKNESS,
)
upper_stairs = ground.stair(
    (STAIR_UPPER_CENTER_X, STAIR_LANDING_END_Y),
    (STAIR_UPPER_CENTER_X, STAIR_UPPER_END_Y),
    name="Upper stair flight",
    width=STAIR_FLIGHT_WIDTH,
    start_height=lower_stairs.end_height,
    height=STAIR_RISER_HEIGHT*STAIR_UPPER_RISERS,
    risers=STAIR_UPPER_RISERS,
    underside="sloped",
    waist_thickness=STAIR_WAIST_THICKNESS,
)
stair_railing = ground.railing(
    "Stair flight railing",
    path=upper_stairs.railing_path("right"),
    height=STAIR_RAILING_HEIGHT,
    color="#C8B090",
)
stair_route_landing_y = (STAIR_LANDING_START_Y+STAIR_LANDING_END_Y)/2
stair_walking_route = (
    lower_stairs.start, (STAIR_LOWER_CENTER_X, stair_route_landing_y),
    (STAIR_UPPER_CENTER_X, stair_route_landing_y), upper_stairs.end,
)
stairway_notes = [
    f"Šířka ramene: {STAIR_FLIGHT_WIDTH*1000:.0f} mm",
    f"Nášlap: {lower_stairs.tread_length*1000:.0f} mm",
    f"Výška stupně: {lower_stairs.riser_height*1000:.1f} mm".replace(".", ","),
    f"Počet výšek: {STAIR_LOWER_RISERS} + {STAIR_UPPER_RISERS} = {STAIR_LOWER_RISERS+STAIR_UPPER_RISERS}",
]

# Centre the complete ceiling on the partition between rooms 1 and 2.
# Without an "axis" marker, miako_slab's reference line is its first edge.
garden_ceiling_center_y = (GARDEN_ROOMS_WALL_Y+INNER_BWT+HOUSE_DEPTH-BWT)/2
garden_ceiling_axis = (
    (wall_garden_partition_g.start[0], garden_ceiling_center_y-GARDEN_CEILING_BEAM_LENGTH/2),
    (wall_garden_partition_g.start[0], garden_ceiling_center_y+GARDEN_CEILING_BEAM_LENGTH/2),
)
garden_ceiling_bearing = (GARDEN_CEILING_BEAM_LENGTH-GARDEN_ROOMS_DEPTH)/2
ceiling_garden_rooms = ceiling_storey.miako_slab(
    "Ceiling - Pokoj 1 and 2",
    start=(garden_ceiling_axis[0][0]-GARDEN_CEILING_WIDTH/2, garden_ceiling_axis[0][1]),
    end=(garden_ceiling_axis[1][0]-GARDEN_CEILING_WIDTH/2, garden_ceiling_axis[1][1]),
    top=CEILING_THICKNESS,
    direction=(1, 0),
    structure=GARDEN_CEILING_STRUCTURE,
    topping=0.06,
    beam_height=0.06,
    block_height=CEILING_THICKNESS-0.06,
    block_start_offset=garden_ceiling_bearing,
    block_end_offset=garden_ceiling_bearing,
)

# Use the full rectangular room envelope, ignoring the narrowed garden-side corner.
third_room_ceiling_center_x = BWT+THIRD_ROOM_WIDTH/2
third_room_ceiling_center_y = (BWT+GARDEN_ROOMS_WALL_Y)/2
third_room_ceiling_bearing = (THIRD_ROOM_CEILING_BEAM_LENGTH-THIRD_ROOM_WIDTH)/2
ceiling_third_room = ceiling_storey.miako_slab(
    "Ceiling - Pokoj 3",
    start=(third_room_ceiling_center_x-THIRD_ROOM_CEILING_BEAM_LENGTH/2,
           third_room_ceiling_center_y-THIRD_ROOM_CEILING_WIDTH/2),
    end=(third_room_ceiling_center_x+THIRD_ROOM_CEILING_BEAM_LENGTH/2,
         third_room_ceiling_center_y-THIRD_ROOM_CEILING_WIDTH/2),
    top=CEILING_THICKNESS,
    direction=(0, 1),
    structure=THIRD_ROOM_CEILING_STRUCTURE,
    topping=0.06,
    beam_height=0.06,
    block_height=CEILING_THICKNESS-0.06,
    block_start_offset=third_room_ceiling_bearing,
    block_end_offset=third_room_ceiling_bearing,
)

wall_plate_east = upper.beam(
    "Pozednice - východ",
    start=(BWT/2, -WALL_PLATE_OVERHANG, WALL_PLATE_Z),
    end=(BWT/2, HOUSE_DEPTH+WALL_PLATE_OVERHANG, WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    kind="WALL_PLATE",
)
wall_plate_west = upper.beam(
    "Pozednice - západ",
    start=(HOUSE_WIDTH-BWT/2, -WALL_PLATE_OVERHANG, WALL_PLATE_Z),
    end=(HOUSE_WIDTH-BWT/2, HOUSE_DEPTH+WALL_PLATE_OVERHANG, WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    kind="WALL_PLATE",
)
purlins = tuple(
    upper.beam(
        f"Vaznice {index}",
        start=(x, -WALL_PLATE_OVERHANG, PURLIN_Z),
        end=(x, HOUSE_DEPTH+WALL_PLATE_OVERHANG, PURLIN_Z),
        size=PURLIN_SIZE,
        kind="PURLIN",
    )
    for index, x in enumerate(PURLIN_X_POSITIONS, 1)
)

# Each reference plane passes through the outer top corners of its supports.
roof = upper.roof("Roof")
roof_ridge_x = HOUSE_WIDTH/2
wall_plate_top_z = WALL_PLATE_Z+WALL_PLATE_SIZE[1]/2
purlin_top_z = PURLIN_Z+PURLIN_SIZE[1]/2
east_contact_x = BWT/2-WALL_PLATE_SIZE[0]/2
west_contact_x = HOUSE_WIDTH-BWT/2+WALL_PLATE_SIZE[0]/2
ridge_cut = ((roof_ridge_x, 0, 0), (roof_ridge_x, 1, 0), (roof_ridge_x, 0, 1))
horizontal_eave_cut = ((0, 0, ROOF_EAVE_CUT_Z), (1, 0, ROOF_EAVE_CUT_Z), (0, 1, ROOF_EAVE_CUT_Z))
east_eave_x = -ROOF_EAVE_OVERHANG
west_eave_x = HOUSE_WIDTH+ROOF_EAVE_OVERHANG
roof_east = roof.plane(
    "East slope",
    points=((east_contact_x, 0, wall_plate_top_z),
            (east_contact_x, -1, wall_plate_top_z),
            (PURLIN_X_POSITIONS[0]-PURLIN_SIZE[0]/2, 0, purlin_top_z)),
    cuts=[ridge_cut, horizontal_eave_cut,
          ((east_eave_x, 0, 0), (east_eave_x, 1, 0), (east_eave_x, 0, 1))],
)
roof_west = roof.plane(
    "West slope",
    points=((west_contact_x, 0, wall_plate_top_z),
            (west_contact_x, 1, wall_plate_top_z),
            (PURLIN_X_POSITIONS[1]+PURLIN_SIZE[0]/2, 0, purlin_top_z)),
    cuts=[ridge_cut, horizontal_eave_cut,
          ((west_eave_x, 0, 0), (west_eave_x, 1, 0), (west_eave_x, 0, 1))],
)
roof_angle_degrees = math.degrees(math.atan2(
    math.hypot(roof_east.z_axis[0], roof_east.z_axis[1]), roof_east.z_axis[2],
))
print(f"Roof angle: {roof_angle_degrees:.2f}°")
rafter_support_span = math.dist(roof_east.points[0], roof_east.points[2])
roof_ridge_point = roof_east.to_world((*roof_east.to_local_xy((roof_ridge_x, 0)), 0))
rafter_upper_span = math.dist(roof_east.points[2], roof_ridge_point)
print(f"Rafter span (wall plate to purlin): {rafter_support_span:.3f} m")
print(f"Rafter upper span (purlin to ridge): {rafter_upper_span:.3f} m")

# Front/back gables reach the rafter undersides; the side walls remain low.
gable_wall_cuts = tuple(
    offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
    for plane in (roof_east, roof_west)
)
gable_wall_height = roof_ridge_point[2]-UPPER_FLOOR_START+RAFTER_HEIGHT
wall_front_u = upper.wall(
    (BWT, 0), (HOUSE_WIDTH-BWT, 0), wall_type=load_bearing_wall,
    height=gable_wall_height, cuts=gable_wall_cuts,
)
wall_west_u = upper.wall(
    (HOUSE_WIDTH, 0), (HOUSE_WIDTH, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=NADEZDIVKA,
)
wall_back_u = upper.wall(
    (HOUSE_WIDTH-BWT, HOUSE_DEPTH), (BWT, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=gable_wall_height, cuts=gable_wall_cuts,
)
wall_east_u = upper.wall(
    (0, HOUSE_DEPTH), (0, 0), wall_type=load_bearing_wall, height=NADEZDIVKA,
)
upper_exterior_walls = (wall_front_u, wall_west_u, wall_back_u, wall_east_u)
for wall, name in zip(upper_exterior_walls, ("front", "west", "back", "east")):
    wall.Name = f"Upper {name} wall"
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})

window_living_room_back = wall_back_u.add_window(
    name="Living room back window",
    at=(wall_back_u.length-UPPER_BACK_WINDOW_WIDTH)/2,
    width=UPPER_BACK_WINDOW_WIDTH,
    sill_height=UPPER_WINDOW_SILL_HEIGHT,
    height=UPPER_WINDOW_TOP_HEIGHT,
)
window_living_room_front = wall_front_u.add_window(
    name="Living room front window",
    at=BWT+UPPER_FRONT_WINDOW_EAST_CLEARANCE-wall_front_u.start[0],
    width=UPPER_WINDOW_WIDTH,
    sill_height=UPPER_WINDOW_SILL_HEIGHT,
    height=UPPER_WINDOW_TOP_HEIGHT,
)

# Keep clear living-room strips along the east and back sides of the house.
living_room_wall_x = BWT+LIVING_ROOM_WIDTH+DRY_WALL_WIDTH/2
living_room_wall_y = HOUSE_DEPTH-BWT-LIVING_ROOM_DEPTH-DRY_WALL_WIDTH/2
upper_partition_cuts = tuple(
    offset_plane(*plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM)
    for plane in (roof_east, roof_west)
)
wall_living_room_side_u = upper.wall(
    (living_room_wall_x, BWT), (living_room_wall_x, living_room_wall_y-DRY_WALL_WIDTH/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
wall_living_room_back_u = upper.wall(
    (living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y),
    (HOUSE_WIDTH-BWT, living_room_wall_y),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
for wall, name in (
    (wall_living_room_side_u, "Living room - side partition"),
    (wall_living_room_back_u, "Living room - back partition"),
):
    wall.Name = name
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": False})

living_room = upper.floor_layer(
    "Obývací pokoj", room_id="1.01",
    outline=(
        (BWT, BWT),
        (living_room_wall_x-DRY_WALL_WIDTH/2, BWT),
        (living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y+DRY_WALL_WIDTH/2),
        (HOUSE_WIDTH-BWT, living_room_wall_y+DRY_WALL_WIDTH/2),
        (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
        (BWT, HOUSE_DEPTH-BWT),
    ),
    thickness=UPPER_FLOOR_THICKNESS,
    insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
    insulation_material=FLOOR_INSULATION_MATERIAL,
    buildup_material=FLOOR_BUILDUP_MATERIAL,
    color="#ffff80",
)
upper_room_floors = (living_room,)
upper_room_windows = {
    living_room.room_id: (window_living_room_front, window_living_room_back),
}

# Kitchen on the living-room side of the vertical SDK wall, toward the front.
kitchen_wall_face_x = wall_living_room_side_u.start[0]-(
    wall_living_room_side_u.body_offset+wall_living_room_side_u.thickness
)
kitchen_center_x = kitchen_wall_face_x-KITCHEN_WALL_GAP-KITCHEN_UNIT_SIZE[0]/2
kitchen_cooker_y = wall_living_room_side_u.end[1]-KITCHEN_WALL_GAP-KITCHEN_UNIT_SIZE[1]/2
kitchen_sink_y = kitchen_cooker_y-KITCHEN_UNIT_SIZE[1]-KITCHEN_COOKER_SINK_GAP
kitchen_dishwasher_y = kitchen_sink_y-KITCHEN_UNIT_SIZE[1]
kitchen_start_height = UPPER_FLOOR_THICKNESS+0.03
kitchen_cooker, kitchen_sink, kitchen_dishwasher = (
    upper.furniture(
        name, kind="USERDEFINED", size=KITCHEN_UNIT_SIZE,
        center=(kitchen_center_x, center_y), start_height=kitchen_start_height,
    )
    for name, center_y in (
        ("Sporák", kitchen_cooker_y), ("Dřez", kitchen_sink_y), ("Myčka", kitchen_dishwasher_y),
    )
)
kitchen_counter_start_y = BWT+KITCHEN_WALL_GAP
kitchen_counter_end_y = kitchen_dishwasher_y-KITCHEN_UNIT_SIZE[1]/2
kitchen_counter_length = kitchen_counter_end_y-kitchen_counter_start_y
if kitchen_counter_length <= 0:
    raise ValueError("the kitchen appliances leave no room for a worktop before the front wall")
kitchen_counter = upper.furniture(
    "Kuch.\nLinka", kind="USERDEFINED",
    size=(KITCHEN_UNIT_SIZE[0], kitchen_counter_length, KITCHEN_UNIT_SIZE[2]),
    center=(kitchen_center_x, (kitchen_counter_start_y+kitchen_counter_end_y)/2),
    start_height=kitchen_start_height,
)

rafter_pairs = tuple(
    tuple(
        plane.beam(
            f"Krokev {index} - {side}",
            start=plane.to_local_xy((eave_x+overshoot, y)),
            end=plane.to_local_xy((roof_ridge_x-overshoot, y)),
            size=RAFTER_SIZE,
            z_offset=RAFTER_Z_OFFSET,
            kind="RAFTER",
        )
        for plane, side, eave_x, overshoot in (
            (roof_east, "východ", east_eave_x, -1.0),
            (roof_west, "západ", west_eave_x, 1.0),
        )
    )
    for index, y in enumerate(RAFTER_Y_POSITIONS, 1)
)

roof_layer_storeys = {
    name: house.storey(f"Roof - {name}", elevation=UPPER_FLOOR_START)
    for name in (
        "Thermal insulation under rafters", "Vapour barrier", "Gypsum plasterboard",
        "MDF", "Roofing underlay", "Counter-battens", "Tile battens", "Roof tiles",
    )
}
for layer_name, layer_storey in roof_layer_storeys.items():
    layer_storey.element.ObjectType = "ROOF_LAYER"
    layer_storey.element.Description = f"Visibility container for {layer_name}"


def roof_slope_limits(plane, x_limits, offsets, *, cover=False):
    """Intersect the vertical and horizontal eave limits at each layer face."""
    intervals = []
    for z in offsets:
        lo, hi = sorted((x-plane.origin[0]-z*plane.z_axis[0])/plane.y_axis[0] for x in x_limits)
        cut_y = (ROOF_EAVE_CUT_Z-plane.origin[2]-z*plane.z_axis[2])/plane.y_axis[2]
        if plane.y_axis[2]>0:
            lo = max(lo, cut_y)
        else:
            hi = min(hi, cut_y)
        if lo>=hi:
            raise ValueError(f"{plane.Name}: roof eave cut leaves no layer span")
        intervals.append((lo, hi))
    if cover:
        return min(lo for lo, hi in intervals), max(hi for lo, hi in intervals)
    return max(lo for lo, hi in intervals), min(hi for lo, hi in intervals)


def roof_layer_outline(plane, x_limits, y_limits, offset, thickness):
    """Overshoot only the clipped slope ends; retain exact gable endpoints."""
    lo, hi = roof_slope_limits(plane, x_limits, (offset, offset+thickness), cover=True)
    first, last = sorted(plane.to_local_xy((plane.origin[0], y))[0] for y in y_limits)
    return ((first, lo-0.1), (last, lo-0.1), (last, hi+0.1), (first, hi+0.1))


def roof_vertical_cut(x):
    return ((x, 0, 0), (x, 1, 0), (x, 0, 1))


def cut_roof_layer_at_purlin(layer, index):
    """Leave exposed supporting timber where it crosses the sloped inner finish."""
    opening = ifcopenshell.api.root.create_entity(
        house.model, ifc_class="IfcOpeningElement", predefined_type="OPENING",
        name=f"{layer.Name} - purlin clearance",
    )
    opening.ObjectType = "ROOF_SUPPORT_CLEARANCE"
    half_width = PURLIN_SIZE[0]/2
    x = PURLIN_X_POSITIONS[index]
    # The opening matches the timber volume, extending beyond the finish along Y.
    representation = ifcopenshell.api.geometry.add_slab_representation(
        house.model, context=house._body_context, depth=PURLIN_SIZE[1],
        polyline=((x-half_width, -WALL_PLATE_OVERHANG),
                  (x+half_width, -WALL_PLATE_OVERHANG),
                  (x+half_width, HOUSE_DEPTH+WALL_PLATE_OVERHANG),
                  (x-half_width, HOUSE_DEPTH+WALL_PLATE_OVERHANG)),
    )
    ifcopenshell.api.geometry.assign_representation(house.model, product=opening, representation=representation)
    ifcopenshell.api.feature.add_feature(house.model, feature=opening, element=layer)
    placement = np.eye(4)
    placement[2, 3] = PURLIN_Z-PURLIN_SIZE[1]/2
    ifcopenshell.api.geometry.edit_object_placement(house.model, product=opening, matrix=placement, is_si=True)


def add_roof_build_up(plane, side, purlin_index, eave_x, inner_wall_x):
    """Build the original house's roof stack on one of the new roof planes."""
    inner_x = (inner_wall_x, roof_ridge_x)
    inner_y = (BWT, HOUSE_DEPTH-BWT)
    outer_x = (eave_x, roof_ridge_x)
    inset_eave_x = eave_x+(ROOF_EAVE_SETBACK if eave_x<roof_ridge_x else -ROOF_EAVE_SETBACK)
    board_x = (inset_eave_x, roof_ridge_x)
    tile_y = (-ROOF_GABLE_OVERHANG, HOUSE_DEPTH+ROOF_GABLE_OVERHANG)
    board_y = (tile_y[0]+ROOF_EAVE_SETBACK, tile_y[1]-ROOF_EAVE_SETBACK)
    definitions = (
        ("Thermal insulation under rafters", THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM,
         THERMAL_INSULATION_UNDER_RAFTERS, "Thermal insulation", "#E8D36D", 0),
        ("Vapour barrier", VAPOUR_BARRIER_BOTTOM, VAPOUR_BARRIER_THICKNESS, "Vapour barrier", "#4A90E2", 0.35),
        ("Gypsum plasterboard", GYPSUM_PLASTERBOARD_BOTTOM, GYPSUM_PLASTERBOARD_THICKNESS,
         "Gypsum plasterboard", "#E8E5DE", 0),
        ("MDF", MDF_BOTTOM, MDF_THICKNESS, "MDF", "#f2b6d0", 0),
        ("Roofing underlay", UNDERLAY_BOTTOM, UNDERLAY_THICKNESS, "Roofing underlay", "#3B4148", 0),
        ("Roof tiles", ROOF_TILE_BOTTOM, ROOF_TILE_THICKNESS, "Roof tiles", "#A64B35", 0),
    )
    layers = []
    for key, offset, thickness, material, color, transparency in definitions:
        is_inner = key in {"Thermal insulation under rafters", "Vapour barrier", "Gypsum plasterboard"}
        is_tile = key=="Roof tiles"
        x_limits = inner_x if is_inner else outer_x if is_tile else board_x
        y_limits = inner_y if is_inner else tile_y if is_tile else board_y
        extra_cuts = () if is_tile else (roof_vertical_cut(inner_wall_x if is_inner else inset_eave_x),)
        layer = plane.layer(
            f"{side} {key}", outline=roof_layer_outline(plane, x_limits, y_limits, offset, thickness),
            z_offset=offset, thickness=thickness, material=material, color=color,
            transparency=transparency, extra_cuts=extra_cuts,
        )
        if is_inner:
            cut_roof_layer_at_purlin(layer, purlin_index)
        if is_tile:
            layer.set_tile_pattern(width=ROOF_TILE_PATTERN_WIDTH, course_length=TILE_BATTEN_SPACING)
        roof_layer_storeys[key].add(layer)
        layers.append(layer)

    # Counter-battens follow the actual, nonuniformly spaced rafter stations.
    lo, hi = roof_slope_limits(
        plane, board_x, (COUNTER_BATTEN_BOTTOM, COUNTER_BATTEN_BOTTOM+COUNTER_BATTEN_SIZE[1]), cover=True,
    )
    for index, y in enumerate(RAFTER_Y_POSITIONS, 1):
        local_x = plane.to_local_xy((plane.origin[0], y))[0]
        batten = plane.beam(
            f"{side} counter-batten {index}", start=(local_x, lo-0.1), end=(local_x, hi+0.1),
            z_offset=COUNTER_BATTEN_BOTTOM, size=COUNTER_BATTEN_SIZE,
            extra_cuts=(roof_vertical_cut(inset_eave_x),),
        )
        roof_layer_storeys["Counter-battens"].add(batten)

    # Tile battens run along the ridge, 320 mm apart measured on the slope.
    lo, hi = roof_slope_limits(plane, board_x, (TILE_BATTEN_BOTTOM, TILE_BATTEN_BOTTOM+TILE_BATTEN_SIZE[1]))
    first, last = sorted(plane.to_local_xy((plane.origin[0], y))[0] for y in board_y)
    row, local_y = 1, lo+TILE_BATTEN_SPACING/2
    while local_y+TILE_BATTEN_SIZE[0]/2 <= hi:
        batten = plane.beam(
            f"{side} tile batten {row}", start=(first, local_y), end=(last, local_y),
            z_offset=TILE_BATTEN_BOTTOM, size=TILE_BATTEN_SIZE,
            extra_cuts=(roof_vertical_cut(inset_eave_x),),
        )
        roof_layer_storeys["Tile battens"].add(batten)
        row += 1
        local_y += TILE_BATTEN_SPACING
    return tuple(layers)


roof_layers = (
    *add_roof_build_up(roof_east, "East", 0, east_eave_x, BWT),
    *add_roof_build_up(roof_west, "West", 1, west_eave_x, HOUSE_WIDTH-BWT),
)
# The transverse SDK partition also meets the exposed west purlin.
cut_roof_layer_at_purlin(wall_living_room_back_u, 1)
roof_tiles_top_z = max(
    plane_height_at(
        *offset_plane(*layer.plane.points, offset=layer.z_offset+layer.thickness),
        x=roof_ridge_x, y=HOUSE_DEPTH/2,
    )
    for layer in roof_layers if layer.material_name=="Roof tiles"
)
chimney = upper.chimney(
    center=CHIMNEY_CENTER,
    size=CHIMNEY_SIZE,
    height=roof_tiles_top_z+CHIMNEY_ABOVE_ROOF-UPPER_FLOOR_START,
    flue_diameter=CHIMNEY_FLUE_DIAMETER,
    start_height=0,
    name="Main chimney",
    material="Chimney",
    color="#B8A99A",
)
chimney_roof_opening = roof.add_opening(
    name="Chimney roof penetration",
    rectangle=(
        (chimney.center[0]-chimney.size/2, chimney.center[1]-chimney.size/2),
        (chimney.center[0]+chimney.size/2, chimney.center[1]+chimney.size/2),
    ),
    trimmers=False,
    vertical=True,
)
# Cut the side partition if the configured chimney position crosses it.
partition_x_min = wall_living_room_side_u.start[0]-(wall_living_room_side_u.body_offset+wall_living_room_side_u.thickness)
partition_x_max = wall_living_room_side_u.start[0]-wall_living_room_side_u.body_offset
chimney_y_start = max(wall_living_room_side_u.start[1], chimney.center[1]-chimney.size/2)
chimney_y_end = min(wall_living_room_side_u.end[1], chimney.center[1]+chimney.size/2)
if (chimney.center[0]-chimney.size/2 < partition_x_max
        and chimney.center[0]+chimney.size/2 > partition_x_min
        and chimney_y_start < chimney_y_end):
    wall_living_room_side_u.add_opening(
        name="Chimney passage through living-room partition",
        at=chimney_y_start-wall_living_room_side_u.start[1],
        width=chimney_y_end-chimney_y_start,
        height=wall_living_room_side_u.height,
        sill_height=0,
    )
partition_y_min = wall_living_room_back_u.start[1]+wall_living_room_back_u.body_offset
partition_y_max = partition_y_min+wall_living_room_back_u.thickness
chimney_x_start = max(wall_living_room_back_u.start[0], chimney.center[0]-chimney.size/2)
chimney_x_end = min(wall_living_room_back_u.end[0], chimney.center[0]+chimney.size/2)
if (chimney.center[1]-chimney.size/2 < partition_y_max
        and chimney.center[1]+chimney.size/2 > partition_y_min
        and chimney_x_start < chimney_x_end):
    wall_living_room_back_u.add_opening(
        name="Chimney passage through living-room back partition",
        at=chimney_x_start-wall_living_room_back_u.start[0],
        width=chimney_x_end-chimney_x_start,
        height=wall_living_room_back_u.height,
        sill_height=0,
    )
total_house_height = roof_tiles_top_z-(ground.elevation+GROUND_FLOOR_THICKNESS)
print(f"Total house height from ground-floor finished floor to top of roof tiles: {total_house_height:.3f} m")
plasterboard_wall_heights = {}

plasterboard_height_at_wall = plane_height_at(
        *offset_plane(*roof_east.points, offset=GYPSUM_PLASTERBOARD_BOTTOM),
        x=BWT, y=HOUSE_DEPTH/2,
    )-UPPER_FINISHED_FLOOR_HEIGHT
print(f"Plasterboard inner-face height at wall, above finished upper floor: {plasterboard_height_at_wall:.3f} m")

def add_facade_insulation(drawing, walls=None):
    """Add drawing-only Rockwool around the exterior walls, including the corners."""
    if walls is None:
        walls = (wall_front_g, wall_west_g, wall_back_g, wall_east_g)
    for wall in walls:
        if math.isclose(wall.start[1], wall.end[1], abs_tol=1e-9):
            endpoints = dict(start_x=-FACADE_INSULATION_THICKNESS,
                             end_x=HOUSE_WIDTH+FACADE_INSULATION_THICKNESS)
        else:
            endpoints = dict(start_y=0, end_y=HOUSE_DEPTH)
        drawing.add_wall_insulation(
            wall,
            thickness=FACADE_INSULATION_THICKNESS,
            material="rockwool",
            **endpoints,
        )


house.write("house2.ifc")

if "ground" in sys.argv:
    drawing1 = house.add_drawing(
        "ground",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=2.0,
        radius=6.5,
        storeys=[ground],
        right_panel_width=60,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
        ("brick", "Nosná zeď - VPC Cihla 175 mm"),
        ("diagonal1", "Příčka - VPC Cihla 115 mm"),
        ("rockwool-wave", f"Rockwool - fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1)
    for room in ground_room_floors:
        position = Polygon(room.outline).representative_point().coords[0]
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*ground_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
    drawing1.add_stair_annotation(lower_stairs)
    drawing1.add_stair_annotation(upper_stairs)
    drawing1.add_stair_landing_annotation(middle_stair_landing)
    drawing1.add_poly_line(
        stair_walking_route,
        arrow_end=True, circle_start=True,
    )
    drawing1.add_notes(stairway_notes, title="SCHODIŠTĚ")
    drawing1.add_opening_dimension(entrance_door, offset=1.6, finished_floor_height=GROUND_FLOOR_THICKNESS)
    for door in (pokoj1_door, pokoj2_door):
        drawing1.add_opening_dimension(
            door, offset=1.5, finished_floor_height=GROUND_FLOOR_THICKNESS,
        )
    drawing1.add_opening_dimension(
        pokoj3_door, offset=-0.5, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        bathroom_door, offset=0.4, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    for window, offset in (
        (window_pokoj1, -0.65), (window_pokoj2, -0.65),
        (window_pokoj3, -1.0), (window_koupelna, -1.0),
    ):
        drawing1.add_opening_dimension(
            window, offset=offset, finished_floor_height=GROUND_FLOOR_THICKNESS,
        )
    drawing1.add_entrance_arrow(
        (HOUSE_WIDTH+0.5, wall_west_g.start[1]+ENTRANCE_OPENING_AT+ENTRANCE_OPENING_WIDTH/2),
        rotation=180,
        size=0.35,
    )

	# delka domu (bez izolace)
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-1.75)
	# hloubka domu (bez izolace)
    drawing1.add_dimension(start=(0, 0), end=(0, HOUSE_DEPTH), offset=0.7)
	# hloubka mistnosti do zahrady
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-0.5, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        end=(HOUSE_WIDTH-BWT-0.5, HOUSE_DEPTH-BWT),
    )
	# delka leva zahradni mistnost
    drawing1.add_dimension(
        start=(BWT, HOUSE_DEPTH-BWT-0.5),
        end=(HOUSE_WIDTH/2-PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT-0.5),
    )
	# delka prava zahradni mistnost
    drawing1.add_dimension(
        start=(HOUSE_WIDTH/2+PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT-0.5),
        end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-0.5),
    )
	# delka tretiho pokoje
    drawing1.add_dimension(
        start=(BWT, BWT+0.5), end=(THIRD_ROOM_WALL_X-INNER_BWT, BWT+0.5),
    )
    # Clear width and depth of Pokoj 3's narrowed garden-side end.
    drawing1.add_dimension(
        start=(BWT, GARDEN_ROOMS_WALL_Y-1.25),
        end=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y-1.25),
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
        end=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y),
		offset=1.5
    )
    # hloubka tretiho pokoje
    drawing1.add_dimension(
        start=(BWT+0.5, BWT), end=(BWT+0.5, GARDEN_ROOMS_WALL_Y),
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_WALL_X, 2.0),
        end=(STAIRWAY_WALL_X-INNER_BWT, 2.0),
        name="Stairway clear width",
		offset=1.5
    )
    drawing1.add_dimension(
        start=(STAIRWAY_WALL_X+0.3, BWT),
        end=(STAIRWAY_WALL_X+0.3, BATHROOM_PARTITION_Y),
        name="Bathroom clear depth",
    )
    drawing1.add_dimension(
        start=(STAIRWAY_WALL_X+0.3, GARDEN_ROOMS_WALL_Y),
        end=(STAIRWAY_WALL_X+0.3, BATHROOM_PARTITION_Y+PARTITION_THICKNESS),
        name="Bathroom clear depth",
    )
    drawing1.add_dimension(
        start=(STAIRWAY_WALL_X, BWT+0.5),
        end=(HOUSE_WIDTH-BWT, BWT+0.5),
        name="Bathroom clear width",
    )

    drawing1.render(PROJECT_DIR / "ground.svg", pdf=PDF_GROUND)

if "ceiling" in sys.argv:
    drawing1 = house.add_drawing(
        "ceiling",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=ground_floor_height+0.1,
        radius=6.5,
        storeys=[ceiling_storey],
        door_annotations=False,
        automatic_plan_annotations=False,
        right_panel_width=60,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    # Show wall context without including the ground-floor finishes or stairs.
    for wall in ground.walls:
        drawing1.include_element(wall)
    add_facade_insulation(drawing1)
    drawing1.add_material_legend([
        ("rockwool-wave", f"Rockwool - fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    drawing1.add_miako_beam_dimensions(ceiling_garden_rooms, side="end", offset=0.7)
    drawing1.add_miako_beam_dimensions(ceiling_third_room, side="start", offset=0.7)
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-0.7)
    drawing1.add_dimension(start=(0, 0), end=(0, HOUSE_DEPTH), offset=1.2)
    drawing1.add_dimension(
        start=ceiling_garden_rooms.start, end=ceiling_garden_rooms.end, offset=0.65,
    )
    drawing1.add_dimension(
        start=ceiling_garden_rooms.end,
        end=(ceiling_garden_rooms.end[0]+ceiling_garden_rooms.width, ceiling_garden_rooms.end[1]),
        offset=1.15,
    )
    drawing1.add_dimension(
        start=ceiling_third_room.start, end=ceiling_third_room.end, offset=-0.55,
    )
    drawing1.add_miako_beam_schedule([
        {"location": "Pokoj 1 a 2", "slab": ceiling_garden_rooms},
        {"location": "Pokoj 3", "slab": ceiling_third_room},
    ])
    drawing1.render(PROJECT_DIR / "ceiling.svg", pdf=PDF_CEILING)

if "upper" in sys.argv:
    drawing1 = house.add_drawing(
        "upper",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=UPPER_FLOOR_START+1.0,
        radius=6.5,
        storeys=[upper],
        right_panel_width=60,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
        ("drywall-diagonal1", f"Sádrokartonová příčka {DRY_WALL_WIDTH*1000:.0f} mm"),
        ("rockwool-wave", f"Rockwool - fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1, upper_exterior_walls)
    drawing1.add_chimney_annotation(chimney)
    drawing1.add_dimension(
        start=(chimney.center[0], upper_stairs.end[1]),
        end=(chimney.center[0], chimney.center[1]-chimney.size/2),
		offset=-0.5,
        name="Chimney clearance from upper stairs",
    )
    drawing1.add_dimension(
        start=(STAIR_RIGHT_X-1.4, upper_stairs.end[1]),
        end=(STAIR_RIGHT_X-1.4, wall_living_room_back_u.start[1]+wall_living_room_back_u.body_offset),
        name="Living room wall clearance from stairs",
    )
    for room in upper_room_floors:
        position = Polygon(room.outline).representative_point().coords[0]
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*upper_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
    for window, offset in (
        (window_living_room_front, -1.3),
        (window_living_room_back, -0.65),
    ):
        drawing1.add_opening_dimension(
            window, offset=offset, finished_floor_height=UPPER_FLOOR_THICKNESS,
        )
    drawing1.include_element(stair_railing)
    drawing1.add_stair_annotation(lower_stairs)
    drawing1.add_stair_annotation(upper_stairs)
    drawing1.add_stair_landing_annotation(middle_stair_landing)
    drawing1.add_poly_line(
        stair_walking_route,
        arrow_end=True, circle_start=True,
    )
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-0.7)
    drawing1.add_dimension(start=(0, 0), end=(0, HOUSE_DEPTH), offset=0.7)
    drawing1.add_dimension(
        start=(BWT, HOUSE_DEPTH-BWT-0.5),
        end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-0.5),
    )
    drawing1.add_dimension(
        start=(BWT+0.5, BWT),
        end=(BWT+0.5, HOUSE_DEPTH-BWT),
    )
    drawing1.add_dimension(
        start=(BWT, living_room_wall_y-DRY_WALL_WIDTH/2-0.9),
        end=(living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y-DRY_WALL_WIDTH/2-0.9),
    )
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-1.0, living_room_wall_y+DRY_WALL_WIDTH/2),
        end=(HOUSE_WIDTH-BWT-1.0, HOUSE_DEPTH-BWT),
    )
    drawing1.render(PROJECT_DIR / "upper.svg", pdf=PDF_UPPER)

if "roof" in sys.argv:
    drawing1 = house.add_drawing(
        "roof",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=max(roof_tiles_top_z, upper.elevation+chimney.end_height)+0.5,
        radius=6.5,
        storeys=[],
        door_annotations=False,
        automatic_plan_annotations=False,
        projected_wood_color="#f4d35e",
        surface_fills=True,
        model_line_width=0.06,
        right_panel_width=65,
        section_outline_width=SECTION_OUTLINE_WIDTH,
        section_outline_projected_walls=True,
    )
    roof_rafters = tuple(member for pair in rafter_pairs for member in pair)
    for element in (*upper_exterior_walls, wall_plate_east, wall_plate_west, *purlins, *roof_rafters):
        drawing1.include_element(element)
    drawing1.add_chimney_annotation(chimney)
    for index, (start_y, end_y) in enumerate(zip(RAFTER_Y_POSITIONS, RAFTER_Y_POSITIONS[1:]), 1):
        drawing1.add_dimension(
            start=(east_eave_x, start_y), end=(east_eave_x, end_y), offset=0.65,
            name=f"Rafter spacing {index}",
        )
    support_x_positions = (BWT/2, *PURLIN_X_POSITIONS, HOUSE_WIDTH-BWT/2)
    for index, (start_x, end_x) in enumerate(zip(support_x_positions, support_x_positions[1:]), 1):
        drawing1.add_dimension(
            start=(start_x, -WALL_PLATE_OVERHANG), end=(end_x, -WALL_PLATE_OVERHANG), offset=-0.2,
            name=f"Roof support centre distance {index}",
        )
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-1.0)
    drawing1.add_dimension(
        start=(HOUSE_WIDTH+ROOF_EAVE_OVERHANG+0.7, 0),
        end=(HOUSE_WIDTH+ROOF_EAVE_OVERHANG+0.7, HOUSE_DEPTH),
    )
    drawing1.add_timber_schedule([
        ("Pozednice", (wall_plate_east, wall_plate_west), 0,
         {"color": "#f4d35e", "pattern": "brick-opposite"}),
        ("Vaznice", purlins, 0, {"color": "#f4a261", "pattern": "brick"}),
        ("Krokve", roof_rafters, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
    ])
    drawing1.render(PROJECT_DIR / "roof.svg", pdf=PDF_ROOF)
