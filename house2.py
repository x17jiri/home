"""Alternative house: export with `python3 house2.py`; draw with `ground`, `ceiling`, or `upper`."""

from pathlib import Path
from math import floor
import math
import sys

import ifcopenshell.api.pset
import ifcopenshell.util.element
from shapely.geometry import Polygon

from ifc_utils import House, window_area


HOUSE_WIDTH = 9.0
HOUSE_DEPTH = 8.75
BWT = 0.24
INNER_BWT = 0.175
PARTITION_THICKNESS = 0.115
FACADE_INSULATION_THICKNESS = 0.20
GARDEN_ROOMS_DEPTH = 3.47  # Clear depth between the divider and inside garden wall.
GARDEN_ROOMS_WALL_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT
THIRD_ROOM_WIDTH = 3.47  # Clear width of the left street-side room.
THIRD_ROOM_WALL_X = BWT+THIRD_ROOM_WIDTH+INNER_BWT
THIRD_ROOM_NARROW_WIDTH = 2.75
THIRD_ROOM_NARROW_DEPTH = 1.25  # Clear depth of the narrowed garden-side end.
THIRD_ROOM_NARROW_WALL_X = BWT+THIRD_ROOM_NARROW_WIDTH+INNER_BWT
THIRD_ROOM_STEP_Y = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_NARROW_DEPTH
STAIRWAY_WIDTH = 3.0  # Clear width of the right street-side section.
STAIRWAY_DEPTH = 2.25  # Clear depth of its bottom/street-side part.
STAIRWAY_WALL_X = HOUSE_WIDTH-BWT-STAIRWAY_WIDTH
STAIRWAY_WALL_Y = BWT+STAIRWAY_DEPTH
BATHROOM_WIDTH = 2.75  # Clear width; independent of the stairway below it.
BATHROOM_WALL_X = HOUSE_WIDTH-BWT-BATHROOM_WIDTH

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
NADEZDIVKA = 1.125+UPPER_RING_BEAM_HEIGHT
STAIR_FLIGHT_WIDTH = 1.05
STAIR_LANDING_LENGTH = 1.05
STAIR_TREAD_LENGTH = 0.27
STAIR_LOWER_RISERS = 9
STAIR_UPPER_RISERS = 7
STAIR_LOWER_RUN_LENGTH = (STAIR_LOWER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_UPPER_RUN_LENGTH = (STAIR_UPPER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_RISER_HEIGHT = (UPPER_FINISHED_FLOOR_HEIGHT-GROUND_FLOOR_THICKNESS)/(STAIR_LOWER_RISERS+STAIR_UPPER_RISERS)
STAIR_LANDING_START_X = HOUSE_WIDTH-BWT-STAIR_LANDING_LENGTH
STAIR_LOWER_START_X = STAIR_LANDING_START_X-STAIR_LOWER_RUN_LENGTH
STAIR_UPPER_END_X = STAIR_LANDING_START_X-STAIR_UPPER_RUN_LENGTH
STAIR_LOWER_CENTER_Y = STAIRWAY_WALL_Y-STAIR_FLIGHT_WIDTH/2
STAIR_UPPER_CENTER_Y = BWT+STAIR_FLIGHT_WIDTH/2
STAIR_WAIST_THICKNESS = 0.15
STAIR_RAILING_HEIGHT = 1.0
if STAIR_UPPER_RUN_LENGTH+STAIR_LANDING_LENGTH > STAIRWAY_WIDTH+1e-9:
    raise ValueError("upper stair flight and landing do not fit STAIRWAY_WIDTH")
# The lower flight may extend into the open hallway.
if STAIR_LOWER_START_X < THIRD_ROOM_WALL_X-1e-9:
    raise ValueError("lower stair flight reaches beyond the hallway into Pokoj 3")
if 2*STAIR_FLIGHT_WIDTH > STAIRWAY_DEPTH+1e-9:
    raise ValueError("the two stair flights do not fit STAIRWAY_DEPTH")
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
GARDEN_DOOR_PARTITION_CLEARANCE = 0.125
THIRD_ROOM_DOOR_FRONT_CLEARANCE = 1.25
BATHROOM_DOOR_STAIRWAY_CLEARANCE = 0.125
HALLWAY_CENTER_X = (THIRD_ROOM_WALL_X+STAIRWAY_WALL_X)/2
ENTRANCE_OPENING_AT = math.ceil(THIRD_ROOM_WIDTH/0.125)*0.125 + 0.5
ROOM_WINDOW_WIDTH = 1.75
GROUND_WINDOW_TOP_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+2.25
GROUND_WINDOW_SILL_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+0.875
BATHROOM_WINDOW_WIDTH = 0.75
BATHROOM_WINDOW_HEIGHT = 0.75
WINDOW_POSITION_STEP = 0.125

PROJECT_DIR = Path("projekt2")
DIR_ARCHITEKTONICKO_STAVEBNI_RESENI = PROJECT_DIR / "D1.1. Architektonicko Stavební Řešení"
PDF_GROUND = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.1. Půdorys 1.NP.pdf"
PDF_CEILING = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.2. Strop nad 1.NP.pdf"
PDF_UPPER = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.3. Půdorys 2.NP.pdf"
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
wall_bathroom_side_g = ground.wall(
    (BATHROOM_WALL_X, STAIRWAY_WALL_Y+INNER_BWT), (BATHROOM_WALL_X, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_bathroom_side_g.Name = "Hallway - bathroom wall"
wall_stairway_back_g = ground.wall(
    (STAIRWAY_WALL_X, STAIRWAY_WALL_Y), (HOUSE_WIDTH-BWT, STAIRWAY_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
front_door = wall_front_g.add_door(
    name="Entrance door",
    at=ENTRANCE_OPENING_AT,
    opening_width=ENTRANCE_OPENING_WIDTH,
    width=ENTRANCE_DOOR_WIDTH,
    height=ENTRANCE_DOOR_HEIGHT,
    clear_height=ENTRANCE_CLEAR_HEIGHT,
    sill_height=GROUND_FLOOR_THICKNESS,
    operation="SINGLE_SWING_LEFT",
)
pokoj1_door = wall_garden_rooms_g.add_door(
    name="Pokoj 1 door",
    at=(wall_garden_partition_g.start[0]-PARTITION_THICKNESS/2
        -GARDEN_DOOR_PARTITION_CLEARANCE-ROOM_DOOR_OPENING_WIDTH-wall_garden_rooms_g.start[0]),
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_RIGHT",
)
pokoj2_door = wall_garden_rooms_g.add_door(
    name="Pokoj 2 door",
    at=(wall_garden_partition_g.start[0]+PARTITION_THICKNESS/2
        +GARDEN_DOOR_PARTITION_CLEARANCE-wall_garden_rooms_g.start[0]),
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_LEFT",
)
pokoj3_door = wall_third_room_g.add_door(
    name="Pokoj 3 door",
    at=BWT+THIRD_ROOM_DOOR_FRONT_CLEARANCE-wall_third_room_g.start[1],
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=ROOM_DOOR_HEIGHT,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=0,
    operation="SINGLE_SWING_LEFT",
)
bathroom_door = wall_bathroom_side_g.add_door(
    name="Koupelna door",
    at=(STAIRWAY_WALL_Y+INNER_BWT+BATHROOM_DOOR_STAIRWAY_CLEARANCE
        -wall_bathroom_side_g.start[1]),
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
    wall_third_room_return_g, wall_third_room_top_g,
    wall_bathroom_side_g, wall_stairway_back_g,
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
chodba = ground.floor_layer(
    "Chodba", room_id="0.04",
    outline=(
        (THIRD_ROOM_WALL_X, BWT), (STAIRWAY_WALL_X, BWT),
        (STAIRWAY_WALL_X, STAIRWAY_WALL_Y+INNER_BWT),
        (BATHROOM_WALL_X-INNER_BWT, STAIRWAY_WALL_Y+INNER_BWT),
        (BATHROOM_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y),
        (THIRD_ROOM_NARROW_WALL_X, GARDEN_ROOMS_WALL_Y),
        (THIRD_ROOM_NARROW_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
        (THIRD_ROOM_WALL_X, THIRD_ROOM_STEP_Y+INNER_BWT),
    ),
    **floor_layer_settings,
)
koupelna = ground.floor_layer(
    "Koupelna", room_id="0.05",
    outline=(
        (BATHROOM_WALL_X, STAIRWAY_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, STAIRWAY_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y), (BATHROOM_WALL_X, GARDEN_ROOMS_WALL_Y),
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
window_koupelna = wall_west_g.add_window(
    name="Koupelna window",
    at=Polygon(koupelna.outline).centroid.y-wall_west_g.start[1]-BATHROOM_WINDOW_WIDTH/2,
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

# Stairs use the ceiling and future upper-floor levels.
lower_stairs = ground.stair(
    (STAIR_LOWER_START_X, STAIR_LOWER_CENTER_Y),
    (STAIR_LANDING_START_X, STAIR_LOWER_CENTER_Y),
    name="Lower stair flight",
    width=STAIR_FLIGHT_WIDTH,
    start_height=GROUND_FLOOR_THICKNESS,
    height=STAIR_RISER_HEIGHT*STAIR_LOWER_RISERS,
    risers=STAIR_LOWER_RISERS,
    underside="sloped",
    waist_thickness=STAIR_WAIST_THICKNESS,
)
middle_stair_landing = ground.stair_landing(
    (STAIR_LANDING_START_X, BWT), (HOUSE_WIDTH-BWT, STAIRWAY_WALL_Y),
    name="Middle stair landing",
    height=lower_stairs.end_height,
    thickness=STAIR_WAIST_THICKNESS,
)
upper_stairs = ground.stair(
    (STAIR_LANDING_START_X, STAIR_UPPER_CENTER_Y),
    (STAIR_UPPER_END_X, STAIR_UPPER_CENTER_Y),
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
if STAIR_LOWER_START_X > STAIRWAY_WALL_X+1e-9:
    ground.stair_landing(
        (STAIRWAY_WALL_X, STAIRWAY_WALL_Y-STAIR_FLIGHT_WIDTH),
        (STAIR_LOWER_START_X, STAIRWAY_WALL_Y),
        name="Stairway entrance approach",
        height=GROUND_FLOOR_THICKNESS,
        thickness=GROUND_FLOOR_THICKNESS,
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

# The upper-floor walls align with the ground-floor exterior faces.
wall_front_u = upper.wall(
    (0, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=NADEZDIVKA,
)
wall_west_u = upper.wall(
    (HOUSE_WIDTH, BWT), (HOUSE_WIDTH, HOUSE_DEPTH-BWT),
    wall_type=load_bearing_wall, height=NADEZDIVKA,
)
wall_back_u = upper.wall(
    (HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=NADEZDIVKA,
)
wall_east_u = upper.wall(
    (0, HOUSE_DEPTH-BWT), (0, BWT), wall_type=load_bearing_wall, height=NADEZDIVKA,
)
upper_exterior_walls = (wall_front_u, wall_west_u, wall_back_u, wall_east_u)
for wall, name in zip(upper_exterior_walls, ("front", "west", "back", "east")):
    wall.Name = f"Upper {name} wall"
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})


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
        ("brick", "Nosná zeď - VPC Cihla 240 mm"),
        ("solid-white", "Nosná zeď - VPC Cihla 175 mm"),
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
    route_x = HOUSE_WIDTH-BWT-STAIR_LANDING_LENGTH/2
    drawing1.add_poly_line(
        [
            lower_stairs.start, (route_x, STAIR_LOWER_CENTER_Y),
            (route_x, STAIR_UPPER_CENTER_Y), upper_stairs.end,
        ],
        arrow_end=True, circle_start=True,
    )
    drawing1.add_notes(stairway_notes, title="SCHODIŠTĚ")
    drawing1.add_opening_dimension(front_door, offset=-1.0, finished_floor_height=GROUND_FLOOR_THICKNESS)
    for door in (pokoj1_door, pokoj2_door):
        drawing1.add_opening_dimension(
            door, offset=1.5, finished_floor_height=GROUND_FLOOR_THICKNESS,
        )
    for door, offset in ((pokoj3_door, 1.2), (bathroom_door, 0.7)):
        drawing1.add_opening_dimension(
            door, offset=offset, finished_floor_height=GROUND_FLOOR_THICKNESS,
        )
    for window, offset in (
        (window_pokoj1, -0.65), (window_pokoj2, -0.65),
        (window_pokoj3, -1.0), (window_koupelna, -0.7),
    ):
        drawing1.add_opening_dimension(
            window, offset=offset, finished_floor_height=GROUND_FLOOR_THICKNESS,
        )
    drawing1.add_entrance_arrow(
        (ENTRANCE_OPENING_AT+ENTRANCE_OPENING_WIDTH/2, -0.5),
        rotation=90,
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
        start=(BWT, GARDEN_ROOMS_WALL_Y-0.5),
        end=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y-0.5),
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
        end=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y),
		offset=0.5
    )
    # hloubka tretiho pokoje
    drawing1.add_dimension(
        start=(BWT+0.5, BWT), end=(BWT+0.5, GARDEN_ROOMS_WALL_Y),
    )
    # delka koupelny
    drawing1.add_dimension(
        start=(BATHROOM_WALL_X, GARDEN_ROOMS_WALL_Y-0.5),
        end=(HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y-0.5),
    )
	# hloubka koupelny
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-0.5, STAIRWAY_WALL_Y+INNER_BWT),
        end=(HOUSE_WIDTH-BWT-0.5, GARDEN_ROOMS_WALL_Y),
    )
    # sirka vstupni chodby
    drawing1.add_dimension(
        start=(THIRD_ROOM_NARROW_WALL_X, GARDEN_ROOMS_WALL_Y-0.5),
        end=(BATHROOM_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y-0.5),
    )
    # Hallway clearances at the room step, stair enclosure, and first tread.
    drawing1.add_dimension(
        start=(THIRD_ROOM_WALL_X, THIRD_ROOM_STEP_Y),
        end=(BATHROOM_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y),
        name="Hallway width at Pokoj 3 step",
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_WALL_X, STAIRWAY_WALL_Y+INNER_BWT-0.1),
        end=(wall_stairway_back_g.start[0], STAIRWAY_WALL_Y+INNER_BWT-0.1),
        name="Hallway clearance to bathroom-stairway wall",
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_WALL_X, lower_stairs.start[1]+0.25),
        end=(lower_stairs.start[0], lower_stairs.start[1]+0.25),
        name="Hallway clearance to first stair tread",
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
        ("brick", "Nosná zeď - VPC Cihla 240 mm"),
        ("rockwool-wave", f"Rockwool - fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1, upper_exterior_walls)
    drawing1.include_element(stair_railing)
    drawing1.add_stair_annotation(lower_stairs)
    drawing1.add_stair_annotation(upper_stairs)
    drawing1.add_stair_landing_annotation(middle_stair_landing)
    route_x = HOUSE_WIDTH-BWT-STAIR_LANDING_LENGTH/2
    drawing1.add_poly_line(
        [
            lower_stairs.start, (route_x, STAIR_LOWER_CENTER_Y),
            (route_x, STAIR_UPPER_CENTER_Y), upper_stairs.end,
        ],
        arrow_end=True, circle_start=True,
    )
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-0.7)
    drawing1.add_dimension(start=(0, 0), end=(0, HOUSE_DEPTH), offset=0.7)
    drawing1.add_dimension(
        start=(BWT, HOUSE_DEPTH-BWT-0.5),
        end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-0.5),
    )
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-0.5, BWT),
        end=(HOUSE_WIDTH-BWT-0.5, HOUSE_DEPTH-BWT),
    )
    drawing1.render(PROJECT_DIR / "upper.svg", pdf=PDF_UPPER)
