"""Alternative house: export with `python3 house2.py`; plans plus `pohledy` for all four exterior views."""

from pathlib import Path
from math import floor
import math
import sys

import ifcopenshell.api.pset
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.root
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ifc_utils import CutDefinition, House, offset_plane, plane_height_at, window_area


HOUSE_WIDTH = 8.75
HOUSE_DEPTH = 9.0
BWT = 0.24
INNER_BWT = 0.175
PARTITION_THICKNESS = 0.115
DRY_WALL_WIDTH = 0.10
FACADE_INSULATION_THICKNESS = 0.20
FACADE_THICKNESS = 0.005
PERIMETER_TOP_HEIGHT = 0.0
GARDEN_ROOMS_DEPTH = 3.47  # Clear depth between the divider and inside garden wall.
GARDEN_ROOMS_WALL_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT
THIRD_ROOM_NARROW_WIDTH = HOUSE_WIDTH/2.0 - BWT - 0.125-1.0-0.1-0.2
THIRD_ROOM_NARROW_WALL_X = BWT+THIRD_ROOM_NARROW_WIDTH+INNER_BWT
THIRD_ROOM_WIDTH = 3.47  # Clear width of the left street-side room.
THIRD_ROOM_WALL_X = BWT+THIRD_ROOM_WIDTH+INNER_BWT
STAIRWAY_WIDTH = 2.25  # Clear width beside the west exterior wall.
STAIRWAY_WALL_X = HOUSE_WIDTH-BWT-STAIRWAY_WIDTH
BATHROOM_LEFT_X = THIRD_ROOM_WALL_X
BATHROOM_RIGHT_X = STAIRWAY_WALL_X-INNER_BWT
BATHROOM_DEPTH = 3.0  # Clear depth from the inside front wall.
BATHROOM_PARTITION_Y = BWT+BATHROOM_DEPTH
THIRD_ROOM_STEP_Y = BATHROOM_PARTITION_Y  # Align the room 3 return with the bathroom wall.
THIRD_ROOM_NARROW_DEPTH = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_STEP_Y
STAIRWAY_OPENING_START_Y = BATHROOM_PARTITION_Y+INNER_BWT

UPPER_BATHROOM_WIDTH = 1.35
LIVING_ROOM_WIDTH = HOUSE_WIDTH - 2*BWT - STAIRWAY_WIDTH - 2*DRY_WALL_WIDTH - UPPER_BATHROOM_WIDTH
LIVING_ROOM_STAIR_CLEARANCE = 1.10  # Clear distance to the stair-facing wall surface.
UPPER_HALLWAY_WIDE_PART_START_X = STAIRWAY_WALL_X  # Default: bathroom's right face.
UPPER_VPC_RETURN_LENGTH = 1.0  # Four 175 mm wall sections extending from the side walls.
KITCHEN_UNIT_SIZE = (0.64, 0.64, 0.75)
KITCHEN_WALL_GAP = 0.03  # Same 350 mm centre offset as the old house's 640 mm units.
KITCHEN_COOKER_SINK_GAP = 0.06  # Old house: 700 mm centre spacing between 640 mm units.
STOVE_SIZE = (0.60, 0.50, 1.50)

GROUND_WALL_BASE_COURSE_HEIGHT = 0.20
GROUND_WALL_BASE_COURSE_MATERIAL = "Liapor brick"
ground_floor_height = GROUND_WALL_BASE_COURSE_HEIGHT + 2.625
CEMFLOW_AND_FINISH_THICKNESS = 0.065
GROUND_FLOOR_INSULATION_THICKNESS = 0.12
GROUND_FLOOR_THICKNESS = GROUND_FLOOR_INSULATION_THICKNESS+CEMFLOW_AND_FINISH_THICKNESS
GROUND_FINISHED_FLOOR_ELEVATION = 417.5  # Metres above sea level.
TERRAIN_STREET_ELEVATION = 416.0
TERRAIN_GARDEN_ELEVATION = 416.6
CEILING_THICKNESS = 0.21
BASEMENT_WALL_HEIGHT = 2.25
BASEMENT_WALL_THICKNESS = 0.30
BASEMENT_SLAB_THICKNESS = 0.15
FOUNDATION_FOOTING_WIDTH = 0.60
FOUNDATION_FOOTING_HEIGHT = 0.50
GROUNDING_LEAD_LENGTH = 1.0  # Length beyond the outside masonry face/corner.
BASEMENT_WALL_TOP_Z = -CEILING_THICKNESS  # Ground-floor layers start at Z = 0.
BASEMENT_FLOOR_START = BASEMENT_WALL_TOP_Z-BASEMENT_WALL_HEIGHT
BASEMENT_SLAB_BOTTOM_Z = BASEMENT_FLOOR_START-BASEMENT_SLAB_THICKNESS
FOUNDATION_FOOTING_BOTTOM_Z = BASEMENT_SLAB_BOTTOM_Z-FOUNDATION_FOOTING_HEIGHT
CEILING_BEAM_BEARING = 0.125  # Minimum at each end, before rounding the beam length up.
CEILING_BEAM_LENGTH_STEP = 0.25
CEILING_LAYOUT_TOLERANCE = 0.07  # Total width mismatch, not the gap at each side.
CEILING_STRIP_WIDTHS = {"beam": 0.17, "wide": 0.455, "narrow": 0.33}
UPPER_FLOOR_THICKNESS = 0.03+CEMFLOW_AND_FINISH_THICKNESS
UPPER_FLOOR_START = ground_floor_height+CEILING_THICKNESS
UPPER_FINISHED_FLOOR_HEIGHT = UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS
UPPER_RING_BEAM_HEIGHT = 0.24
NADEZDIVKA = 1.125+0.05+UPPER_RING_BEAM_HEIGHT
WALL_PLATE_SIZE = (0.16, 0.12)
WALL_PLATE_OVERHANG = 0.30
WALL_PLATE_Z = UPPER_FLOOR_START+NADEZDIVKA+WALL_PLATE_SIZE[1]/2
PURLIN_SIZE = (0.16, 0.24)
PURLIN_WALL_DISTANCE = 2.7
PURLIN_X_POSITIONS = (BWT+PURLIN_WALL_DISTANCE-PURLIN_SIZE[0]/2.0, HOUSE_WIDTH-BWT-PURLIN_WALL_DISTANCE+PURLIN_SIZE[0]/2.0)
PURLIN_CENTER_HEIGHT = 3.45  # Above the upper-floor storey datum / ceiling top.
PURLIN_Z = UPPER_FLOOR_START+PURLIN_CENTER_HEIGHT
PURLIN_SUPPORT_SIZE = (0.16, 0.16)
PURLIN_SUPPORT_Y_POSITIONS = (
    (BWT+2.8, HOUSE_DEPTH-BWT-2.8),  # Purlin 1, at PURLIN_X_POSITIONS[0].
    (BWT+2.8, HOUSE_DEPTH-BWT-2.8),  # Purlin 2, at PURLIN_X_POSITIONS[1].
)
PURLIN_CONNECTION_BEAM_SIZE = (0.12, 0.20)  # Width along Y, height along Z.
PURLIN_CONNECTION_WALL_CLEARANCE = 0.10  # Clear gap from each gable wall's inner face.
PURLIN_CONNECTION_Y_POSITIONS = (
    min(PURLIN_SUPPORT_Y_POSITIONS[0]),
    max(PURLIN_SUPPORT_Y_POSITIONS[0]),
    BWT+PURLIN_CONNECTION_WALL_CLEARANCE+PURLIN_CONNECTION_BEAM_SIZE[0]/2,
    HOUSE_DEPTH-BWT-PURLIN_CONNECTION_WALL_CLEARANCE-PURLIN_CONNECTION_BEAM_SIZE[0]/2,
)
PURLIN_BRACE_SIZE = (0.10, 0.12)
PURLIN_BRACE_DROP = 0.80  # Brace anchor below the post top; braces rise at 45 degrees.
RAFTER_THICKNESS = 0.08
RAFTER_HEIGHT = 0.20
RAFTER_SIZE = (RAFTER_THICKNESS, RAFTER_HEIGHT)
COLLAR_TIE_SIZE = (0.05, 0.15)
RAFTER_Z_OFFSET = -0.05  # Perpendicular to the support-contact roof plane.
RAFTER_SPACING = 0.67
RAFTER_FIRST_Y = -0.125
RAFTER_LAST_Y = HOUSE_DEPTH+0.125
ROOF_EAVE_OVERHANG = .6
ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.20
ROOF_EAVE_CUT_Z = WALL_PLATE_Z-WALL_PLATE_SIZE[1]/2-ROOF_EAVE_DROP_BELOW_WALL_PLATE
ROOF_GABLE_OVERHANG = 0.25
CHIMNEY_SIZE = 0.40
CHIMNEY_FLUE_DIAMETER = 0.20
CHIMNEY_ABOVE_ROOF = 1.6
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
STAIR_FLIGHT_WIDTH = 1.0
STAIR_LANDING_LENGTH = 1.05
STAIR_TREAD_LENGTH = 0.27
STAIR_LOWER_RISERS = 8
STAIR_UPPER_RISERS = 8
STAIR_LOWER_RUN_LENGTH = (STAIR_LOWER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_UPPER_RUN_LENGTH = (STAIR_UPPER_RISERS-1)*STAIR_TREAD_LENGTH
STAIR_RISER_HEIGHT = (UPPER_FINISHED_FLOOR_HEIGHT-GROUND_FLOOR_THICKNESS)/(STAIR_LOWER_RISERS+STAIR_UPPER_RISERS)
STAIR_FLIGHT_GAP = 0.05
STAIR_LEFT_X = STAIRWAY_WALL_X
STAIR_UPPER_CENTER_X = STAIR_LEFT_X+STAIR_FLIGHT_WIDTH/2
STAIR_LOWER_CENTER_X = STAIR_UPPER_CENTER_X+STAIR_FLIGHT_WIDTH+STAIR_FLIGHT_GAP
STAIR_RIGHT_X = STAIR_LOWER_CENTER_X+STAIR_FLIGHT_WIDTH/2
STAIR_LANDING_START_Y = BWT
STAIR_LANDING_END_Y = STAIR_LANDING_START_Y+STAIR_LANDING_LENGTH
STAIR_LOWER_START_Y = STAIR_LANDING_END_Y+STAIR_LOWER_RUN_LENGTH
STAIR_UPPER_END_Y = STAIR_LANDING_END_Y+STAIR_UPPER_RUN_LENGTH
LIVING_ROOM_WALL_FRONT_Y = STAIR_UPPER_END_Y+LIVING_ROOM_STAIR_CLEARANCE
LIVING_ROOM_DEPTH = HOUSE_DEPTH-BWT-LIVING_ROOM_WALL_FRONT_Y-DRY_WALL_WIDTH
# Chimney against the stair-facing side of the horizontal living-room wall.
CHIMNEY_CENTER = (HOUSE_WIDTH/2.0+0.4, LIVING_ROOM_WALL_FRONT_Y-CHIMNEY_SIZE/2)
STAIR_WAIST_THICKNESS = 0.15
STAIR_RAILING_HEIGHT = 1.0
if STAIR_RIGHT_X > HOUSE_WIDTH-BWT+1e-9:
    raise ValueError("rotated stairs do not fit between room 3 and the west wall")
if max(STAIR_LOWER_START_Y, STAIR_UPPER_END_Y) > GARDEN_ROOMS_WALL_Y+1e-9:
    raise ValueError("rotated stairs reach the garden-room dividing wall")
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
ENTRANCE_OPENING_WIDTH = 1.1
ENTRANCE_DOOR_WIDTH = 0.9
ENTRANCE_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ENTRANCE_CLEAR_HEIGHT = 2.1
ROOM_DOOR_WIDTH = 0.9
ROOM_DOOR_OPENING_WIDTH = 1.0
ROOM_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ROOM_DOOR_CLEAR_HEIGHT = 2.1
UPPER_BATHROOM_DOOR_WIDTH = 0.8
UPPER_BATHROOM_DOOR_OPENING_WIDTH = 0.9
UPPER_BATHROOM_DOOR_SIDE_CLEARANCE = 0.05
GARDEN_DOOR_CENTER_CLEARANCE = 0.125
THIRD_ROOM_DOOR_GARDEN_CLEARANCE = 0.375  # From the room 1 face to the construction opening.
BATHROOM_DOOR_SIDE_CLEARANCE = 0.125
ENTRANCE_OPENING_AT = 3.65  # Along the west wall, measured from its start.
ROOM_WINDOW_WIDTH = 1.75
GROUND_WINDOW_TOP_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+2.25
GROUND_WINDOW_SILL_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+0.875
UPPER_WINDOW_WIDTH = 1.5
UPPER_BACK_WINDOW_WIDTH = 1.5
UPPER_BACK_WINDOW_GAP = 1.0
UPPER_FRONT_WINDOW_EAST_CLEARANCE = 2.25
UPPER_WINDOW_HEIGHT = GROUND_WINDOW_TOP_HEIGHT-GROUND_WINDOW_SILL_HEIGHT
UPPER_WINDOW_SILL_HEIGHT = UPPER_FLOOR_THICKNESS+GROUND_WINDOW_SILL_HEIGHT-GROUND_FLOOR_THICKNESS
UPPER_WINDOW_TOP_HEIGHT = UPPER_WINDOW_SILL_HEIGHT+UPPER_WINDOW_HEIGHT
BATHROOM_WINDOW_WIDTH = 0.75
BATHROOM_WINDOW_HEIGHT = 0.75
BATHROOM_WINDOW_CENTER_X = BATHROOM_RIGHT_X-0.25-BATHROOM_WINDOW_WIDTH/2
WINDOW_POSITION_STEP = 0.125

PROJECT_DIR = Path("projekt2")
DIR_ARCHITEKTONICKO_STAVEBNI_RESENI = PROJECT_DIR / "D1.1. Architektonicko Stavební Řešení"
PDF_GROUND = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.1. Půdorys 1.NP.pdf"
PDF_CEILING = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.2. Strop nad 1.NP.pdf"
PDF_UPPER = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.3. Půdorys podkroví.pdf"
PDF_ROOF = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.4. Krov.pdf"
PDF_POHLED_ZAPAD = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.5. Pohled - Západ.pdf"
PDF_POHLED_ULICE = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.6. Pohled - Ulice.pdf"
PDF_POHLED_ZAHRADA = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.7. Pohled - Zahrada.pdf"
PDF_POHLED_VYCHOD = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.8. Pohled - Východ.pdf"
PDF_BASEMENT = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.9. Půdorys suterénu.pdf"
PDF_FOUND = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.10. Základy.pdf"
PDF_AA = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.11. Řez AA.pdf"
PDF_BB = DIR_ARCHITEKTONICKO_STAVEBNI_RESENI / "D1.1.12. Řez BB.pdf"
SECTION_OUTLINE_WIDTH = 0.3

RAFTERS_MIDPOINT = CHIMNEY_CENTER[1]-0.04
RAFTER_Y_POSITIONS = (
	-0.125,
	-0.125+1.07,
	-0.125+1.07+0.82,
	-0.125+1.07+0.82+1.07,
	-0.125+1.07+0.82+1.07+0.67,
	-0.125+1.07+0.82+1.07+0.67+1.07, # komin
	-0.125+1.07+0.82+1.07+0.67+1.07+0.67,
	-0.125+1.07+0.82+1.07+0.67+1.07+0.67+0.67,
	-0.125+1.07+0.82+1.07+0.67+1.07+0.67+0.67+1.07,
	-0.125+1.07+0.82+1.07+0.67+1.07+0.67+0.67+1.07+1.07,
	HOUSE_DEPTH+0.125,
)
found_chimney_space = False
for i in range(1, len(RAFTER_Y_POSITIONS)):
	dist = abs(RAFTER_Y_POSITIONS[i]-RAFTER_Y_POSITIONS[i-1])
	if dist > 1.0701:
		print("**** WARNING: rafter dist =", dist)
	if i == 5:
		found_chimney_space = found_chimney_space or (
			dist >= 1.05 and
			abs((RAFTER_Y_POSITIONS[i]+RAFTER_Y_POSITIONS[i-1]) / 2.0 - RAFTERS_MIDPOINT) <= 0.05
		)
assert(found_chimney_space)

aa_cut = CutDefinition(
    start=(HOUSE_WIDTH/2+0.5, -1.5),
    end=(HOUSE_WIDTH/2+0.5, HOUSE_DEPTH+1.5),
    identifier="A", direction=-1,  # Look towards +X.
)
bb_cut = CutDefinition(
    start=(-1.5, HOUSE_DEPTH/2),
    end=(HOUSE_WIDTH+1.5, HOUSE_DEPTH/2),
    identifier="B", direction=-1,  # Look towards -Y.
)


def add_house_cut_symbols(drawing):
    """Keep the AA/BB markers identical across the house plans."""
    aa_cut.add_symbol(drawing)
    bb_cut.add_symbol(drawing)


house = House("House 2", mirror_x=False, colors={"wall": "#ffffff", "window": "#ffffff"})
foundation = house.storey("Foundation", elevation=FOUNDATION_FOOTING_BOTTOM_Z)
basement = house.storey("Basement", elevation=BASEMENT_FLOOR_START)
basement_ceiling_storey = house.storey("Basement ceiling", elevation=BASEMENT_WALL_TOP_Z)
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
basement_wall_type = house.wall_type(
    "Basement wall - ztracene bedneni 300 mm",
    layers=[("ztracene bedneni", BASEMENT_WALL_THICKNESS)],
    color="#ffffff",
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
# The return shares both wall faces with the 175 mm bathroom wall.
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
    (BATHROOM_LEFT_X, BATHROOM_PARTITION_Y),
    (BATHROOM_RIGHT_X, BATHROOM_PARTITION_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_bathroom_partition_g.Name = "Hallway - bathroom VPC 175 mm wall"
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
    at=(wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset
        +wall_garden_rooms_g.thickness-THIRD_ROOM_DOOR_GARDEN_CLEARANCE
        -ROOM_DOOR_OPENING_WIDTH-wall_third_room_top_g.start[1]),
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
    wall_third_room_return_g, wall_third_room_top_g, wall_stairway_g, wall_bathroom_partition_g,
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

# Centre solid basement walls beneath the physical bodies, including walls
# whose ground-floor reference line lies on a face rather than the centre.
basement_walls = []
basement_wall_corners = []
for source in ground.walls:
    tangent = (np.asarray(source.end)-source.start)/source.length
    normal = np.array((-tangent[1], tangent[0]))
    centre_offset = source.body_offset+source.thickness/2
    # Fill the thicker corner/partition junctions without moving wall centres.
    extension = (BASEMENT_WALL_THICKNESS-source.thickness)/2
    start = np.asarray(source.start)+normal*centre_offset-tangent*extension
    end = np.asarray(source.end)+normal*centre_offset+tangent*extension
    wall = basement.wall(
        tuple(float(v) for v in start), tuple(float(v) for v in end),
        wall_type=basement_wall_type, height=BASEMENT_WALL_HEIGHT,
    )
    wall.Name = f"Basement - {source.Name}"
    object.__setattr__(wall, "source_wall", source)
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})
    provenance = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="BBIM_BasementWall")
    ifcopenshell.api.pset.edit_pset(house.model, pset=provenance, properties={"SourceWall": source.GlobalId})
    basement_walls.append(wall)
    for point in (start, end):
        for sign in (-1, 1):
            basement_wall_corners.append(point+sign*normal*BASEMENT_WALL_THICKNESS/2)
basement_walls = tuple(basement_walls)

# One continuous slab covers the full outer footprint of the thicker walls.
basement_plan_min = np.min(basement_wall_corners, axis=0)
basement_plan_max = np.max(basement_wall_corners, axis=0)
basement_base_plate = basement.floor_layer(
    "Foundation base plate",
    outline=(
        (float(basement_plan_min[0]), float(basement_plan_min[1])),
        (float(basement_plan_max[0]), float(basement_plan_min[1])),
        (float(basement_plan_max[0]), float(basement_plan_max[1])),
        (float(basement_plan_min[0]), float(basement_plan_max[1])),
    ),
    thickness=BASEMENT_SLAB_THICKNESS, start_height=-BASEMENT_SLAB_THICKNESS,
    kind="BASESLAB", load_bearing=True,
    buildup_material="Base plate concrete", color="#b8b8b8",
)
foundation_footings = foundation.add_strip_footings_from(
    basement, width=FOUNDATION_FOOTING_WIDTH, height=FOUNDATION_FOOTING_HEIGHT,
    start_height=0, material="Concrete", color="#969696",
)
print(
    "Foundation footing bottom below ground-floor finished floor: "
    f"{ground.elevation+GROUND_FLOOR_THICKNESS-FOUNDATION_FOOTING_BOTTOM_Z:.3f} m"
)

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
        (BATHROOM_LEFT_X, BWT), (BATHROOM_RIGHT_X, BWT),
        (BATHROOM_RIGHT_X, BATHROOM_PARTITION_Y), (BATHROOM_LEFT_X, BATHROOM_PARTITION_Y),
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
    at=BATHROOM_WINDOW_CENTER_X-BATHROOM_WINDOW_WIDTH/2-wall_front_g.start[0],
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
bathroom_right_x = BATHROOM_RIGHT_X
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
    center=(BATHROOM_LEFT_X+0.55, BWT+0.55),
    start_height=GROUND_FLOOR_THICKNESS,
)
bathroom_services_center_x = bathroom_right_x-(bathroom_right_x-BATHROOM_LEFT_X)/4
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
# Two quarter circles around the inner entrance corners, joined across the
# flight gap. Sample finely enough for a smooth curve at the drawing scale.
stair_entry_clearance_points = tuple(
    (center_x+STAIR_FLIGHT_WIDTH*math.cos(angle), center_y+STAIR_FLIGHT_WIDTH*math.sin(angle))
    for center_x, center_y, angle_start, angle_end in (
        (STAIR_UPPER_CENTER_X+STAIR_FLIGHT_WIDTH/2, STAIR_UPPER_END_Y, math.pi, math.pi/2),
        (STAIR_LOWER_CENTER_X-STAIR_FLIGHT_WIDTH/2, STAIR_LOWER_START_Y, math.pi/2, 0),
    )
    for angle in np.linspace(angle_start, angle_end, 33)
)
stairway_notes = [
    f"Šířka ramene: {STAIR_FLIGHT_WIDTH*1000:.0f} mm",
    f"Nášlap: {lower_stairs.tread_length*1000:.0f} mm",
    f"Výška stupně: {lower_stairs.riser_height*1000:.1f} mm".replace(".", ","),
    f"Počet výšek: {STAIR_LOWER_RISERS} + {STAIR_UPPER_RISERS} = {STAIR_LOWER_RISERS+STAIR_UPPER_RISERS}",
]

def design_miako_structure(covered_width):
    """Fit a beam/block alternation, preferring the fewest narrow block rows."""
    widths = CEILING_STRIP_WIDTHS
    max_bays = math.ceil((covered_width+CEILING_LAYOUT_TOLERANCE-widths["beam"])
                         /(widths["beam"]+widths["narrow"]))
    candidates = []
    for bays in range(1, max_bays+1):
        for narrow in range(bays+1):
            width = ((bays+1)*widths["beam"]+(bays-narrow)*widths["wide"]
                     +narrow*widths["narrow"])
            error = abs(width-covered_width)
            if error <= CEILING_LAYOUT_TOLERANCE+1e-9:
                candidates.append((narrow, error, bays))
    if not candidates:
        raise ValueError(f"no MIAKO layout fits {covered_width:.3f} m within the width tolerance")
    narrow, _, bays = min(candidates)
    wide = bays-narrow
    blocks = ["wide"]*(wide//2)+["narrow"]*narrow+["wide"]*(wide-wide//2)
    return tuple(["beam"]+[item for block in blocks for item in (block, "beam")])


ceiling_designs = []


def add_miako_ceiling(name, bounds, *, beam_axis, width_alignment="center"):
    """Fit clear bounds with rounded-up bearing spans and an optional fixed edge."""
    x0, y0, x1, y1 = bounds
    if x1 <= x0 or y1 <= y0 or beam_axis not in {"x", "y"}:
        raise ValueError(f"invalid ceiling bounds or beam axis for {name}")
    clear_span, covered_width = (x1-x0, y1-y0) if beam_axis == "x" else (y1-y0, x1-x0)
    structure = design_miako_structure(covered_width)
    width = sum(CEILING_STRIP_WIDTHS[item] for item in structure)
    length = math.ceil((clear_span+2*CEILING_BEAM_BEARING-1e-9)
                       /CEILING_BEAM_LENGTH_STEP)*CEILING_BEAM_LENGTH_STEP
    bearing = (length-clear_span)/2
    cx, cy = (x0+x1)/2, (y0+y1)/2
    width_start = y0 if beam_axis == "x" else x0
    if width_alignment == "center":
        width_start += (covered_width-width)/2
    elif width_alignment == "end":
        width_start += covered_width-width
    elif width_alignment != "start":
        raise ValueError(f"invalid width alignment for {name}")
    if beam_axis == "x":
        start, end = (cx-length/2, width_start), (cx+length/2, width_start)
        direction = (0, 1)
    else:
        start, end = (width_start, cy-length/2), (width_start, cy+length/2)
        direction = (1, 0)
    slab = ceiling_storey.miako_slab(
        name, start=start, end=end, top=CEILING_THICKNESS,
        direction=direction, structure=structure,
        topping=0.06, beam_height=0.06, block_height=CEILING_THICKNESS-0.06,
        block_start_offset=bearing, block_end_offset=bearing,
    )
    ceiling_designs.append(dict(
        slab=slab, bounds=bounds, beam_axis=beam_axis,
        clear_span=clear_span, covered_width=covered_width, bearing=bearing,
    ))
    print(f"{name}: {len(slab.beams)} beams x {length:.3f} m along {beam_axis}; "
          f"{structure.count('wide')} wide + {structure.count('narrow')} narrow rows; "
          f"width {width:.3f}/{covered_width:.3f} m (difference {(width-covered_width)*1000:+.0f} mm); "
          f"bearing {bearing*1000:.0f} mm each end")
    return slab


ceiling_garden_rooms = add_miako_ceiling(
    "Ceiling - Pokoj 1 and 2",
    (BWT, GARDEN_ROOMS_WALL_Y+INNER_BWT, HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
    beam_axis="y",
)
# Split at the same Y as the bathroom-facing edge of its hallway wall.
# The garden portion uses room 3's narrower width, rather than its old envelope.
# Keep their adjoining edges fixed so the two parallel end beams do not overlap.
ceiling_third_room_front = add_miako_ceiling(
    "Ceiling - Pokoj 3 street part",
    (BWT, BWT, THIRD_ROOM_WALL_X-INNER_BWT, BATHROOM_PARTITION_Y),
    beam_axis="x", width_alignment="end",
)
ceiling_third_room_back = add_miako_ceiling(
    "Ceiling - Pokoj 3 garden part",
    (BWT, BATHROOM_PARTITION_Y, THIRD_ROOM_NARROW_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y),
    beam_axis="x", width_alignment="start",
)
# The front bearing assumes the bathroom wall continues across the stair approach.
ceiling_hallway = add_miako_ceiling(
    "Ceiling - Chodba",
    (THIRD_ROOM_NARROW_WALL_X, BATHROOM_PARTITION_Y+INNER_BWT,
     HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y), beam_axis="y",
)
ceiling_bathroom = add_miako_ceiling(
    "Ceiling - Koupelna",
    (BATHROOM_LEFT_X, BWT, BATHROOM_RIGHT_X, BATHROOM_PARTITION_Y), beam_axis="x",
)

# Reuse the completed layouts verbatim; only the containing storey's Z changes.
basement_ceiling_slabs = tuple(
    basement_ceiling_storey.miako_slab(
        source.Name.replace("Ceiling -", "Basement ceiling -", 1),
        start=source.start, end=source.end, top=source.top,
        direction=source.direction, structure=source.structure,
        block_length=source.block_length,
        block_start_offset=source.block_start_offset,
        block_end_offset=source.block_end_offset,
        block_height=source.block_height, topping=source.topping,
        beam_height=source.beam_height,
    )
    for source in (design["slab"] for design in ceiling_designs)
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
if len(PURLIN_SUPPORT_Y_POSITIONS) != len(purlins) or any(
    len(positions) != 2 for positions in PURLIN_SUPPORT_Y_POSITIONS
):
    raise ValueError("PURLIN_SUPPORT_Y_POSITIONS must contain two Y coordinates for each purlin")
purlin_bottom_z = PURLIN_Z-PURLIN_SIZE[1]/2
purlin_support_top_z = purlin_bottom_z
purlin_connection_bottom_z = PURLIN_Z-PURLIN_CONNECTION_BEAM_SIZE[1]/2
support_rows = tuple(zip(*(sorted(positions) for positions in PURLIN_SUPPORT_Y_POSITIONS)))
if len(purlins) != 2 or any(abs(row[0]-row[1]) > 1e-8 for row in support_rows):
    raise ValueError("east and west supports must have matching Y coordinates for X-aligned connection beams")
support_east_x, support_west_x = sorted(PURLIN_X_POSITIONS)
purlin_connection_beams = tuple(
    upper.beam(
        f"Spojovací trám mezi vaznicemi {index}",
        start=(support_east_x+PURLIN_SIZE[0]/2, y, PURLIN_Z),
        end=(support_west_x-PURLIN_SIZE[0]/2, y, PURLIN_Z),
        size=PURLIN_CONNECTION_BEAM_SIZE,
    )
    for index, y in enumerate(PURLIN_CONNECTION_Y_POSITIONS, 1)
)
purlin_supports = tuple(
    upper.beam(
        f"Sloupek vaznice {purlin_index}.{support_index}",
        start=(x, y, UPPER_FLOOR_START),
        end=(x, y, purlin_support_top_z),
        size=PURLIN_SUPPORT_SIZE,
        kind="USERDEFINED",
    )
    for purlin_index, (x, positions) in enumerate(zip(PURLIN_X_POSITIONS, PURLIN_SUPPORT_Y_POSITIONS), 1)
    for support_index, y in enumerate(positions, 1)
)


def add_purlin_support_brace(name, start, end, post_face_cut):
    """Trim a diagonal brace flush to the post face and supported beam underside."""
    length = math.dist(start, end)
    extension = PURLIN_BRACE_SIZE[1]
    direction = tuple((b-a)/length for a, b in zip(start, end))
    return upper.beam(
        name,
        start=tuple(a-extension*d for a, d in zip(start, direction)),
        end=tuple(b+extension*d for b, d in zip(end, direction)),
        size=PURLIN_BRACE_SIZE,
        cuts=(post_face_cut, ((0, 0, end[2]), (1, 0, end[2]), (0, 1, end[2]))),
    )


if not math.isfinite(PURLIN_BRACE_DROP) or PURLIN_BRACE_DROP <= 0:
    raise ValueError("PURLIN_BRACE_DROP must be positive and finite")
brace_anchor_z = purlin_support_top_z-PURLIN_BRACE_DROP
if brace_anchor_z-PURLIN_BRACE_SIZE[1] <= UPPER_FINISHED_FLOOR_HEIGHT:
    raise ValueError("purlin braces must start above the finished upper floor")
connection_brace_rise = purlin_connection_bottom_z-brace_anchor_z
if connection_brace_rise <= 0:
    raise ValueError("connection-beam underside must be above the brace anchors")
if 2*connection_brace_rise >= support_west_x-support_east_x-PURLIN_SUPPORT_SIZE[0]:
    raise ValueError("purlin connection-beam braces would overlap; reduce PURLIN_BRACE_DROP")
purlin_y_braces = []
purlin_x_braces = []
for purlin_index, (x, positions) in enumerate(zip(PURLIN_X_POSITIONS, PURLIN_SUPPORT_Y_POSITIONS), 1):
    for support_index, y in enumerate(positions, 1):
        # Two braces in the YZ plane, one on each side of the post.
        for sign, side in ((-1, "ulice"), (1, "zahrada")):
            post_face_y = y+sign*PURLIN_SUPPORT_SIZE[1]/2
            contact_y = post_face_y+sign*(purlin_bottom_z-brace_anchor_z)
            if not -WALL_PLATE_OVERHANG <= contact_y <= HOUSE_DEPTH+WALL_PLATE_OVERHANG:
                raise ValueError("purlin brace extends beyond its purlin; reduce PURLIN_BRACE_DROP")
            purlin_y_braces.append(add_purlin_support_brace(
                f"Tesařský pásek {purlin_index}.{support_index} - {side}",
                (x, post_face_y, brace_anchor_z), (x, contact_y, purlin_bottom_z),
                ((0, post_face_y, 0), (1, post_face_y, 0), (0, post_face_y, 1)),
            ))
        # The third brace supports the X beam toward the opposite post.
        sign = 1 if x == support_east_x else -1
        post_face_x = x+sign*PURLIN_SUPPORT_SIZE[0]/2
        purlin_x_braces.append(add_purlin_support_brace(
            f"Tesařský pásek {purlin_index}.{support_index} - příčný trám",
            (post_face_x, y, brace_anchor_z),
            (post_face_x+sign*connection_brace_rise, y, purlin_connection_bottom_z),
            ((post_face_x, 0, 0), (post_face_x, 1, 0), (post_face_x, 0, 1)),
        ))
purlin_y_braces = tuple(purlin_y_braces)
purlin_x_braces = tuple(purlin_x_braces)
purlin_braces = (*purlin_y_braces, *purlin_x_braces)

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
roof_slope_percent = 100*math.tan(math.radians(roof_angle_degrees))
print(f"Roof angle: {roof_angle_degrees:.2f}° ({roof_slope_percent:.2f}%)")
rafter_support_span = math.dist(roof_east.points[0], roof_east.points[2])
roof_ridge_point = roof_east.to_world((*roof_east.to_local_xy((roof_ridge_x, 0)), 0))
rafter_upper_span = math.dist(roof_east.points[2], roof_ridge_point)
print(f"Rafter span (wall plate to purlin): {rafter_support_span:.3f} m")
print(f"Rafter upper span (purlin to ridge): {rafter_upper_span:.3f} m")

# Keep the roof slopes at the gable sides and cap the masonry below the purlins.
gable_wall_cuts = tuple(
    offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
    for plane in (roof_east, roof_west)
)
gable_wall_height = roof_ridge_point[2]-UPPER_FLOOR_START+RAFTER_HEIGHT
gable_masonry_height = purlin_bottom_z-UPPER_FLOOR_START
gable_masonry_cuts = (
    *gable_wall_cuts,
    ((0, 0, purlin_bottom_z), (1, 0, purlin_bottom_z), (0, 1, purlin_bottom_z)),
)
wall_front_u = upper.wall(
    (BWT, 0), (HOUSE_WIDTH-BWT, 0), wall_type=load_bearing_wall,
    height=gable_masonry_height, cuts=gable_masonry_cuts,
)
wall_west_u = upper.wall(
    (HOUSE_WIDTH, 0), (HOUSE_WIDTH, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=NADEZDIVKA,
)
wall_back_u = upper.wall(
    (HOUSE_WIDTH-BWT, HOUSE_DEPTH), (BWT, HOUSE_DEPTH),
    wall_type=load_bearing_wall, height=gable_masonry_height, cuts=gable_masonry_cuts,
)
wall_east_u = upper.wall(
    (0, HOUSE_DEPTH), (0, 0), wall_type=load_bearing_wall, height=NADEZDIVKA,
)
upper_exterior_walls = (wall_front_u, wall_west_u, wall_back_u, wall_east_u)
for wall, name in zip(upper_exterior_walls, ("front", "west", "back", "east")):
    wall.Name = f"Upper {name} wall"
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})

windows_living_room_back = tuple(
    wall_back_u.add_window(
        name=f"Living room back window {index+1}",
        at=(wall_back_u.length-2*UPPER_BACK_WINDOW_WIDTH-UPPER_BACK_WINDOW_GAP)/2
           +index*(UPPER_BACK_WINDOW_WIDTH+UPPER_BACK_WINDOW_GAP),
        width=UPPER_BACK_WINDOW_WIDTH,
        sill_height=UPPER_WINDOW_SILL_HEIGHT,
        height=UPPER_WINDOW_TOP_HEIGHT,
    )
    for index in range(2)
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
living_room_wall_y = LIVING_ROOM_WALL_FRONT_Y+DRY_WALL_WIDTH/2
upper_partition_cuts = tuple(
    offset_plane(*plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM)
    for plane in (roof_east, roof_west)
)
wall_living_room_side_u = upper.wall(
    (living_room_wall_x, BWT), (living_room_wall_x, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
upper_bathroom_left_x = wall_living_room_side_u.start[0]-wall_living_room_side_u.body_offset
upper_bathroom_right_x = STAIR_LEFT_X-DRY_WALL_WIDTH
upper_bathroom_back_y = STAIR_UPPER_END_Y-DRY_WALL_WIDTH
living_room_wall_step_x = UPPER_HALLWAY_WIDE_PART_START_X
# Centre the wider hallway's SDK wall over the ground-floor load-bearing wall.
living_room_right_wall_y = (
    wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset+wall_garden_rooms_g.thickness/2
)
living_room_right_wall_front_y = living_room_right_wall_y-DRY_WALL_WIDTH/2
if living_room_right_wall_front_y < LIVING_ROOM_WALL_FRONT_Y:
    raise ValueError("the garden-room wall must leave room for the wider upper hallway")
if not living_room_wall_x+DRY_WALL_WIDTH/2 < living_room_wall_step_x < HOUSE_WIDTH-BWT:
    raise ValueError("UPPER_HALLWAY_WIDE_PART_START_X must be between the living-room partition and west wall")
wall_living_room_back_u = upper.wall(
    (living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y),
    (living_room_wall_step_x-DRY_WALL_WIDTH, living_room_wall_y),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
wall_living_room_back_step_u = upper.wall(
    (living_room_wall_step_x-DRY_WALL_WIDTH/2, LIVING_ROOM_WALL_FRONT_Y),
    (living_room_wall_step_x-DRY_WALL_WIDTH/2, living_room_right_wall_front_y+DRY_WALL_WIDTH),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
# Keep the source-wall centre below the sloped ceiling so the clipping
# retains the wall below it rather than the wedge above the roof plane.
living_room_right_wall_height = min(
    gable_wall_height,
    2*(min(plane_height_at(
        *cut, x=(living_room_wall_step_x+HOUSE_WIDTH-BWT)/2,
        y=living_room_right_wall_y,
    ) for cut in upper_partition_cuts)-UPPER_FLOOR_START)-0.01,
)
wall_living_room_back_right_u = upper.wall(
    (living_room_wall_step_x, living_room_right_wall_y),
    (HOUSE_WIDTH-BWT-UPPER_VPC_RETURN_LENGTH, living_room_right_wall_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
# Replace the west end of the SDK wall with masonry. Align the other row
# with the ground-floor bathroom/room 3 wall, on both sides of the house.
upper_vpc_front_y = wall_bathroom_partition_g.start[1]+wall_bathroom_partition_g.body_offset
upper_vpc_walls = []
upper_vpc_footprints = []
for side, start_x in (
    ("West", HOUSE_WIDTH-BWT-UPPER_VPC_RETURN_LENGTH),
    ("East", BWT),
):
    for position, front_y in (
        ("living room", living_room_right_wall_y-INNER_BWT/2),
        ("bathroom wall alignment", upper_vpc_front_y),
    ):
        end_x = start_x+UPPER_VPC_RETURN_LENGTH
        # This face-based VPC type grows towards +Y. Centre the living-room
        # sections on the SDK; align both faces of the front sections
        # with the ground-floor bathroom wall and room 3 return.
        center_y = front_y+INNER_BWT/2
        height = min(
            gable_wall_height,
            2*(min(plane_height_at(*cut, x=(start_x+end_x)/2, y=center_y)
                   for cut in upper_partition_cuts)-UPPER_FLOOR_START)-.01,
        )
        wall = upper.wall(
            (start_x, front_y), (end_x, front_y),
            wall_type=load_bearing_wall_inner, height=height, cuts=upper_partition_cuts,
        )
        wall.Name = f"Upper {side.lower()} VPC wall - {position}"
        common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})
        upper_vpc_walls.append(wall)
        upper_vpc_footprints.append(box(start_x, front_y, end_x, front_y+INNER_BWT))
upper_vpc_walls = tuple(upper_vpc_walls)
upper_vpc_region = unary_union(upper_vpc_footprints)
living_room_door = wall_living_room_back_right_u.add_door(
    name="Living room door",
    at=upper_stairs.end[0]-ROOM_DOOR_OPENING_WIDTH/2-wall_living_room_back_right_u.start[0],
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=UPPER_FLOOR_THICKNESS+ROOM_DOOR_HEIGHT-GROUND_FLOOR_THICKNESS,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=UPPER_FLOOR_THICKNESS,
    operation="SINGLE_SWING_RIGHT",
)
# Bathroom between the living-room partition and stairs. Keep its hallway
# face at the stair arrival so the full 1.10 m approach remains clear.
if upper_bathroom_right_x-upper_bathroom_left_x < (
    UPPER_BATHROOM_DOOR_SIDE_CLEARANCE+UPPER_BATHROOM_DOOR_OPENING_WIDTH
):
    raise ValueError("upper bathroom is too narrow for the configured door opening")
wall_bathroom_stairway_u = upper.wall(
    (STAIR_LEFT_X-DRY_WALL_WIDTH/2, BWT),
    (STAIR_LEFT_X-DRY_WALL_WIDTH/2, upper_bathroom_back_y),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
wall_bathroom_hallway_u = upper.wall(
    (upper_bathroom_left_x, STAIR_UPPER_END_Y-DRY_WALL_WIDTH/2),
    (STAIR_LEFT_X, STAIR_UPPER_END_Y-DRY_WALL_WIDTH/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
upper_bathroom_door = wall_bathroom_hallway_u.add_door(
    name="Upper bathroom door",
    at=UPPER_BATHROOM_DOOR_SIDE_CLEARANCE,
    opening_width=UPPER_BATHROOM_DOOR_OPENING_WIDTH,
    width=UPPER_BATHROOM_DOOR_WIDTH,
    height=UPPER_FLOOR_THICKNESS+ROOM_DOOR_HEIGHT-GROUND_FLOOR_THICKNESS,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=UPPER_FLOOR_THICKNESS,
    operation="SINGLE_SWING_LEFT",
    reverse_swing=True,
)
for wall, name in (
    (wall_living_room_side_u, "Living room - side partition"),
    (wall_living_room_back_u, "Living room - back partition"),
    (wall_living_room_back_step_u, "Living room - hallway step partition"),
    (wall_living_room_back_right_u, "Living room - back right partition"),
    (wall_bathroom_stairway_u, "Upper bathroom - stairway partition"),
    (wall_bathroom_hallway_u, "Upper bathroom - hallway partition"),
):
    wall.Name = name
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": False})

upper_floor_layer_settings = dict(
    thickness=UPPER_FLOOR_THICKNESS,
    insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
    insulation_material=FLOOR_INSULATION_MATERIAL,
    buildup_material=FLOOR_BUILDUP_MATERIAL,
    color="#ffff80",
)
living_room_outline = Polygon((
    (BWT, BWT),
    (living_room_wall_x-DRY_WALL_WIDTH/2, BWT),
    (living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y+DRY_WALL_WIDTH/2),
    (living_room_wall_step_x-DRY_WALL_WIDTH, living_room_wall_y+DRY_WALL_WIDTH/2),
    (living_room_wall_step_x-DRY_WALL_WIDTH, living_room_right_wall_front_y+DRY_WALL_WIDTH),
    (HOUSE_WIDTH-BWT, living_room_right_wall_front_y+DRY_WALL_WIDTH),
    (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
    (BWT, HOUSE_DEPTH-BWT),
)).difference(upper_vpc_region)
living_room = upper.floor_layer(
    "Obývací pokoj", room_id="1.01",
    outline=tuple(living_room_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_bathroom = upper.floor_layer(
    "Koupelna", room_id="1.02",
    outline=(
        (upper_bathroom_left_x, BWT), (upper_bathroom_right_x, BWT),
        (upper_bathroom_right_x, upper_bathroom_back_y),
        (upper_bathroom_left_x, upper_bathroom_back_y),
    ),
    **upper_floor_layer_settings,
)
upper_hallway_outline = box(
    upper_bathroom_left_x, STAIR_UPPER_END_Y, HOUSE_WIDTH-BWT, LIVING_ROOM_WALL_FRONT_Y,
).union(box(
    living_room_wall_step_x, STAIR_UPPER_END_Y, HOUSE_WIDTH-BWT, living_room_right_wall_front_y,
)).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
)).difference(upper_vpc_region)
upper_hallway = upper.floor_layer(
    "Chodba", room_id="1.03", outline=tuple(upper_hallway_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_room_floors = (living_room, upper_bathroom, upper_hallway)
upper_room_windows = {
    living_room.room_id: (window_living_room_front, *windows_living_room_back),
    upper_bathroom.room_id: (),
    upper_hallway.room_id: (),
}

# Reuse the old house's technical-equipment sizes, with small wall gaps.
upper_fixture_wall_gap = 0.05
upper_hallway_right_depth = living_room_right_wall_front_y-STAIR_UPPER_END_Y
upper_washing_machine = upper.furniture(
    "Pračka", kind="USERDEFINED", size=(0.7, 0.7, 0.8), color="#ffffff",
    center=(HOUSE_WIDTH-BWT-0.3-upper_fixture_wall_gap-0.35,
            max(STAIR_UPPER_END_Y+upper_hallway_right_depth/4,
                upper_vpc_front_y+INNER_BWT+upper_fixture_wall_gap+0.35)),
    start_height=UPPER_FLOOR_THICKNESS,
)
upper_hallway_basin = upper.asset(
    "Umyvadlo", asset="basin_large",
    center=(HOUSE_WIDTH-BWT-0.4-upper_fixture_wall_gap-0.55/2,
            STAIR_UPPER_END_Y+3*upper_hallway_right_depth/4),
    start_height=UPPER_FLOOR_THICKNESS+0.85-0.25,
    rotation=-90,
)
upper_recuperation_center = ((upper_bathroom_left_x+upper_bathroom_right_x)/2,
                             BWT+upper_fixture_wall_gap+0.25)
upper_toilet_center = (upper_bathroom_right_x-0.5, BWT+2.0)
upper_recuperation = upper.furniture(
    "Rekuperace", kind="USERDEFINED", size=(1.0, 0.5, 1.5), color="#ffff00",
    center=upper_recuperation_center,
    rotation=0,
    start_height=UPPER_FLOOR_THICKNESS,
)
upper_toilet = upper.asset(
    "Upper bathroom WC", asset="toilet_without_cistern",
    center=upper_toilet_center,
    rotation=180,
    start_height=UPPER_FLOOR_THICKNESS,
)
upper_water_heater_center = (
    upper_bathroom_left_x+upper_fixture_wall_gap+0.35,
    (upper_recuperation_center[1]+0.5/2+upper_toilet_center[1]-0.53/2)/2,
)
upper_water_heater = upper.furniture(
    "Zásobník\nTUV", kind="USERDEFINED", size=(0.7, 0.7, 2.0), color="#ffffff",
    center=upper_water_heater_center,
    start_height=UPPER_FLOOR_THICKNESS,
)

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
kamna = upper.furniture(
    "Kamna", kind="USERDEFINED", size=STOVE_SIZE, color="#ffff2B",
    center=(kitchen_center_x-0.1,
            living_room_wall_y+DRY_WALL_WIDTH/2-0.1+STOVE_SIZE[1]/2),
    start_height=UPPER_FLOOR_THICKNESS+0.05,
    rotation=180,  # Front toward the garden / back wall (+Y).
)
# Keep the plan label upright independently of the stove's facing direction.
for assignment in kamna.ReferencedBy:
    for annotation in assignment.RelatedObjects:
        if annotation.is_a("IfcAnnotation") and annotation.Name == "Kamna Label":
            label_placement = ifcopenshell.util.placement.get_local_placement(annotation.ObjectPlacement)
            label_placement[:3, :3] = np.eye(3)
            ifcopenshell.api.geometry.edit_object_placement(
                house.model, product=annotation, matrix=label_placement, is_si=True,
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
            extra_cuts=(
                ((eave_x+(ROOF_EAVE_SETBACK if side == "východ" else -ROOF_EAVE_SETBACK), 0, 0),
                 (eave_x+(ROOF_EAVE_SETBACK if side == "východ" else -ROOF_EAVE_SETBACK), 1, 0),
                 (eave_x+(ROOF_EAVE_SETBACK if side == "východ" else -ROOF_EAVE_SETBACK), 0, 1)),
            ),
        )
        for plane, side, eave_x, overshoot in (
            (roof_east, "východ", east_eave_x, -1.0),
            (roof_west, "západ", west_eave_x, 1.0),
        )
    )
    for index, y in enumerate(RAFTER_Y_POSITIONS, 1)
)

collar_tie_cuts = tuple(
    offset_plane(*plane.points, offset=RAFTER_Z_OFFSET+RAFTER_HEIGHT)
    for plane in (roof_east, roof_west)
)
collar_ties = tuple(
    upper.beam(
        f"Kleština {index} - {side}",
        start=(0, y+offset, purlin_top_z+COLLAR_TIE_SIZE[1]/2),
        end=(HOUSE_WIDTH, y+offset, purlin_top_z+COLLAR_TIE_SIZE[1]/2),
        size=COLLAR_TIE_SIZE, cuts=collar_tie_cuts,
    )
    for index, y in enumerate(RAFTER_Y_POSITIONS, 1)
    for side, offset in (
        ("ulice", -(RAFTER_THICKNESS+COLLAR_TIE_SIZE[0])/2),
        ("zahrada", (RAFTER_THICKNESS+COLLAR_TIE_SIZE[0])/2),
    )
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


def add_timber_clearances(elements, members):
    """Expose the new frame where its actual solids pass through inner finishes."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    def bounds(element):
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        used = vertices[np.unique(shape.geometry.faces)]
        return used.min(axis=0), used.max(axis=0)

    member_bounds = [(member, bounds(member)) for member in members]
    for element in elements:
        low, high = bounds(element)
        for member, (member_low, member_high) in member_bounds:
            if np.any(np.minimum(high, member_high)-np.maximum(low, member_low) <= 1e-8):
                continue
            opening = ifcopenshell.api.root.create_entity(
                house.model, ifc_class="IfcOpeningElement", predefined_type="OPENING",
                name=f"{element.Name} - {member.Name} clearance",
            )
            opening.ObjectType = "ROOF_SUPPORT_CLEARANCE"
            body = next(rep for rep in member.Representation.Representations
                        if rep.RepresentationIdentifier == "Body")
            ifcopenshell.api.geometry.assign_representation(house.model, product=opening, representation=body)
            ifcopenshell.api.feature.add_feature(house.model, feature=opening, element=element)
            ifcopenshell.api.geometry.edit_object_placement(
                house.model, product=opening,
                matrix=ifcopenshell.util.placement.get_local_placement(member.ObjectPlacement), is_si=True,
            )


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
cut_roof_layer_at_purlin(wall_living_room_back_step_u, 1)
cut_roof_layer_at_purlin(wall_living_room_back_right_u, 1)
cut_roof_layer_at_purlin(wall_bathroom_hallway_u, 1)
add_timber_clearances(
    (wall_living_room_side_u, wall_living_room_back_u, wall_living_room_back_step_u,
     wall_living_room_back_right_u, wall_bathroom_stairway_u, wall_bathroom_hallway_u,
     *(layer for layer in roof_layers if layer.material_name in
       {"Thermal insulation", "Vapour barrier", "Gypsum plasterboard"})),
    (*purlin_connection_beams, *purlin_braces, *collar_ties),
)
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
total_house_height = roof_tiles_top_z-(ground.elevation+GROUND_FLOOR_THICKNESS)
print(f"Total house height from ground-floor finished floor to top of roof tiles: {total_house_height:.3f} m")
plasterboard_wall_heights = {}

plasterboard_height_at_wall = plane_height_at(
        *offset_plane(*roof_east.points, offset=GYPSUM_PLASTERBOARD_BOTTOM),
        x=BWT, y=HOUSE_DEPTH/2,
    )-UPPER_FINISHED_FLOOR_HEIGHT
print(f"Plasterboard inner-face height at wall, above finished upper floor: {plasterboard_height_at_wall:.3f} m")
stair_arrival_west_corner = (upper_stairs.end[0]+STAIR_FLIGHT_WIDTH/2, upper_stairs.end[1])
stair_arrival_roof_plane = roof_east if stair_arrival_west_corner[0] <= roof_ridge_x else roof_west
plasterboard_height_at_stairs = plane_height_at(
    *offset_plane(*stair_arrival_roof_plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM),
    x=stair_arrival_west_corner[0], y=stair_arrival_west_corner[1],
)-UPPER_FINISHED_FLOOR_HEIGHT
print(
    "Plasterboard inner-face height at upper stair arrival, west corner "
    f"(x={stair_arrival_west_corner[0]:.3f}, y={stair_arrival_west_corner[1]:.3f}), "
    f"above finished upper floor: {plasterboard_height_at_stairs:.3f} m"
)

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


def add_house_facades():
    """Continuous grey/white wall finishes, with openings from both floors."""
    perimeter, white = [], []
    for side, ground_wall, upper_wall in (
        ("Street", wall_front_g, wall_front_u),
        ("Garden", wall_back_g, wall_back_u),
        ("East", wall_east_g, wall_east_u),
        ("West", wall_west_g, wall_west_u),
    ):
        tangent = (np.asarray(ground_wall.end)-ground_wall.start)/ground_wall.length
        normal = np.array((-tangent[1], tangent[0]))
        axis = 0 if abs(tangent[0]) > .5 else 1
        # Front/back panels cover the side-panel ends, forming butt joints.
        extension = FACADE_INSULATION_THICKNESS+(FACADE_THICKNESS if axis == 0 else 0)
        low, high = -extension, (HOUSE_WIDTH if axis == 0 else HOUSE_DEPTH)+extension
        ground_face = np.asarray(ground_wall.start)+normal*ground_wall.body_offset

        def panel_options(host):
            first, last = (low, high) if tangent[axis] > 0 else (high, low)
            host_face = np.asarray(host.start)+normal*host.body_offset
            offset = FACADE_INSULATION_THICKNESS+float((ground_face-host_face)@(-normal))
            return dict(
                offset=offset, thickness=FACADE_THICKNESS, side="right",
                start_extension=float((host.start[axis]-first)*tangent[axis]),
                end_extension=float((last-host.end[axis])*tangent[axis]),
            )

        basement_wall = next(w for w in basement_walls if w.source_wall == ground_wall)
        perimeter.append(house.add_facade_layer(
            basement_wall, name=f"{side} facade - grey perimeter",
            material="Perimeter facade finish", color="#d9d9d9",
            start_height=0, height=PERIMETER_TOP_HEIGHT-basement.elevation,
            cuts=(), **panel_options(basement_wall),
        ))
        face_midpoint = (np.asarray(ground_wall.start)+ground_wall.end)/2
        face_midpoint -= normal*(FACADE_INSULATION_THICKNESS+FACADE_THICKNESS/2)
        # A low source centre retains the wall below the sloped cuts, also
        # at the eaves where using the full ridge height would keep a wedge.
        top = min(plane_height_at(*cut, x=float(face_midpoint[0]), y=float(face_midpoint[1]))
                  for cut in gable_wall_cuts)+.05
        white.append(house.add_facade_layer(
            ground_wall, name=f"{side} facade - white",
            material="Facade finish", color="#ffffff",
            start_height=PERIMETER_TOP_HEIGHT-ground.elevation,
            height=top-PERIMETER_TOP_HEIGHT,
            cuts=gable_wall_cuts, opening_walls=(upper_wall,),
            **panel_options(ground_wall),
        ))
    return tuple(perimeter), tuple(white)


def add_roof_edge_facades():
    """Timber edge boards below the tiles; facade walls themselves stay white."""
    if ROOF_EAVE_SETBACK <= 0:
        return ()
    boards = []
    for side, edge_y, normal_y in (
        ("Street", -ROOF_GABLE_OVERHANG, 1),
        ("Garden", HOUSE_DEPTH+ROOF_GABLE_OVERHANG, -1),
    ):
        for slope, plane, lo, hi in (
            ("east", roof_east, east_eave_x, roof_ridge_x),
            ("west", roof_west, roof_ridge_x, west_eave_x),
        ):
            bottom = offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
            top = offset_plane(*plane.points, offset=ROOF_TILE_BOTTOM)
            profile = Polygon((
                (lo, plane_height_at(*bottom, x=lo, y=edge_y)),
                (hi, plane_height_at(*bottom, x=hi, y=edge_y)),
                (hi, plane_height_at(*top, x=hi, y=edge_y)),
                (lo, plane_height_at(*top, x=lo, y=edge_y)),
            ))
            profile = profile.intersection(box(lo, ROOF_EAVE_CUT_Z, hi, profile.bounds[3]+1))
            if profile.is_empty or profile.geom_type != "Polygon":
                raise ValueError(f"{side} {slope} roof-edge board has no continuous profile")
            outline = [(float(x), edge_y, float(z)) for x, z in list(profile.exterior.coords)[:-1]]
            vertices = np.asarray(outline)
            area_normal = np.sum(np.cross(vertices, np.roll(vertices, -1, axis=0)), axis=0)
            if area_normal[1]*normal_y < 0:
                outline.reverse()
            board = house.add_panel(
                f"{side} {slope} roof-edge siding", outline=outline,
                thickness=ROOF_EAVE_SETBACK, material="Wood siding solid", color="#f9e5bf",
            )
            board.ObjectType = "ROOF_EDGE_CLADDING"
            boards.append(board)
    y0, y1 = -ROOF_GABLE_OVERHANG+ROOF_EAVE_SETBACK, HOUSE_DEPTH+ROOF_GABLE_OVERHANG-ROOF_EAVE_SETBACK
    for side, plane, x0, x1 in (
        ("East", roof_east, east_eave_x, east_eave_x+ROOF_EAVE_SETBACK),
        ("West", roof_west, west_eave_x-ROOF_EAVE_SETBACK, west_eave_x),
    ):
        bottom = offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
        top = offset_plane(*plane.points, offset=ROOF_TILE_BOTTOM)
        z0 = min(plane_height_at(*bottom, x=x, y=y0) for x in (x0, x1))-.1
        z1 = max(plane_height_at(*top, x=x, y=y0) for x in (x0, x1))+.1
        xmid, ymid = (x0+x1)/2, (y0+y1)/2
        zbottom = max(ROOF_EAVE_CUT_Z, plane_height_at(*bottom, x=xmid, y=ymid))
        ztop = plane_height_at(*top, x=xmid, y=ymid)
        if ztop <= zbottom:
            raise ValueError(f"{side} eave board has no height above the horizontal roof cut")
        board = house.add_box(
            f"{side} eave siding", origin=(x0, y0, z0), size=(x1-x0, y1-y0, z1-z0),
            material="Wood siding solid", color="#f9e5bf",
            cuts=(bottom, top, horizontal_eave_cut), retained_point=(xmid, ymid, (zbottom+ztop)/2),
        )
        board.ObjectType = "ROOF_EDGE_CLADDING"
        boards.append(board)
    return tuple(boards)


# Concrete at each ceiling occupies the reserved band directly above its walls.
# Keep these beams with the corresponding ceiling so visibility follows it.
basement_ring_beams = basement_ceiling_storey.add_ring_beams_from(
    basement, height=CEILING_THICKNESS, start_height=0,
)
ground_ring_beams = tuple(
    beam
    for source_type in dict.fromkeys(
        ifcopenshell.util.element.get_type(wall) for wall in ground_load_bearing_walls
    )
    for beam in ceiling_storey.add_ring_beams_from(
        ground, source_wall_type=source_type, height=CEILING_THICKNESS, start_height=0,
    )
)
# Insert the common horizontal band below the wall plates into masonry,
# after all upper-wall openings have been created.
upper_ring_beams = tuple(
    beam
    for source_type in dict.fromkeys(
        ifcopenshell.util.element.get_type(wall)
        for wall in (*upper_exterior_walls, *upper_vpc_walls)
    )
    for beam in upper.add_ring_beams_from(
        upper, source_wall_type=source_type,
        height=UPPER_RING_BEAM_HEIGHT,
        start_height=NADEZDIVKA-UPPER_RING_BEAM_HEIGHT,
        replace_wall_band=True,
    )
)

perimeter_facades, wall_facades = add_house_facades()
roof_edge_facades = add_roof_edge_facades()
facade_storey = house.storey("Facades", elevation=0)
facade_storey.element.ObjectType = "FACADE_LAYER"
facade_storey.element.Description = "Visibility container for grey/white facades and timber roof-edge boards"
facade_storey.add(*perimeter_facades, *wall_facades, *roof_edge_facades)


house.write("house2.ifc")

if "basement" in sys.argv:
    drawing1 = house.add_drawing(
        "basement", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=BASEMENT_FLOOR_START+BASEMENT_WALL_HEIGHT/2,
        radius=6.5, storeys=[basement], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("ztracene-bedneni", f"Ztracené bednění {BASEMENT_WALL_THICKNESS*1000:.0f} mm"),
    ])
    drawing1.add_dimension(
        start=tuple(float(v) for v in basement_plan_min),
        end=(float(basement_plan_max[0]), float(basement_plan_min[1])), offset=-.7,
    )
    drawing1.add_dimension(
        start=tuple(float(v) for v in basement_plan_min),
        end=(float(basement_plan_min[0]), float(basement_plan_max[1])), offset=.7,
    )
    drawing1.add_dimension(
        start=(float(basement_plan_max[0])+.6, float(basement_plan_min[1])),
        end=(float(basement_plan_max[0])+.6, float(basement_plan_min[1])+BASEMENT_WALL_THICKNESS),
    )
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "basement.svg", pdf=PDF_BASEMENT)

if "found" in sys.argv or "foundation" in sys.argv:
    drawing1 = house.add_drawing(
        "found", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=FOUNDATION_FOOTING_BOTTOM_Z+FOUNDATION_FOOTING_HEIGHT/2,
        radius=6.5, storeys=[foundation], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
    )
    wall_outline = drawing1.add_wall_outlines(basement_walls, style="dashed")
    ground_wall_outline = drawing1.add_wall_outlines(
        ground.walls, style="dashed", color="blue", name="Ground-floor wall outlines",
    )
    # The common plan style hides individual footing cut edges to avoid
    # junction seams. Draw the boundary of their actual merged footprints.
    footing_polygons = []
    for footing in foundation_footings:
        properties = ifcopenshell.util.element.get_pset(footing, "BBIM_StripFooting")
        length, width = properties["Length"], properties["Width"]
        placement = ifcopenshell.util.placement.get_local_placement(footing.ObjectPlacement)
        corners = ((0, -width/2), (length, -width/2), (length, width/2), (0, width/2))
        footing_polygons.append(Polygon([
            tuple((placement @ np.array((x, y, 0, 1)))[:2]) for x, y in corners
        ]))
    footing_region = unary_union(footing_polygons).simplify(1e-9, preserve_topology=True)
    footing_regions = (footing_region,) if footing_region.geom_type == "Polygon" else footing_region.geoms
    for region in footing_regions:
        for ring in (region.exterior, *region.interiors):
            drawing1.add_poly_line(tuple(ring.coords), line_width=.15, name="Strip footing boundary")
    # Closed grounding ring through the exterior basement-wall centrelines.
    grounding_min = basement_plan_min+BASEMENT_WALL_THICKNESS/2
    grounding_max = basement_plan_max-BASEMENT_WALL_THICKNESS/2
    grounding_corners = (
        (float(grounding_min[0]), float(grounding_min[1])),
        (float(grounding_max[0]), float(grounding_min[1])),
        (float(grounding_max[0]), float(grounding_max[1])),
        (float(grounding_min[0]), float(grounding_max[1])),
    )
    grounding_ring = drawing1.add_poly_line(
        (*grounding_corners, grounding_corners[0]), style="dashed", color="red",
        name="FeZn grounding ring",
    )
    for index, (corner, signs) in enumerate(zip(grounding_corners, ((-1, -1), (1, -1), (1, 1), (-1, 1))), 1):
        diagonal_offset = BASEMENT_WALL_THICKNESS/2+GROUNDING_LEAD_LENGTH/math.sqrt(2)
        drawing1.add_line(
            corner, tuple(value+sign*diagonal_offset for value, sign in zip(corner, signs)),
            style="dashed", color="red", name=f"FeZn corner lead {index}",
        )
    # Resolve the actual entrance opening, rather than assuming it is on the
    # street wall. It currently sits in the west exterior wall.
    entrance_opening = entrance_door.FillsVoids[0].RelatingOpeningElement
    host_element = entrance_opening.VoidsElements[0].RelatingBuildingElement
    entrance_host = next(w for w in ground.walls if w.id() == host_element.id())
    entrance_tangent = (np.asarray(entrance_host.end)-entrance_host.start)/entrance_host.length
    entrance_normal = np.array((-entrance_tangent[1], entrance_tangent[0]))
    entrance_placement = ifcopenshell.util.placement.get_local_placement(entrance_opening.ObjectPlacement)
    entrance_reference = (entrance_placement @ np.array((ENTRANCE_OPENING_WIDTH/2, 0, 0, 1)))[:2]
    entrance_grounding_start = entrance_reference+entrance_normal*(entrance_host.body_offset+entrance_host.thickness/2)
    entrance_grounding_end = entrance_grounding_start-entrance_normal*(BASEMENT_WALL_THICKNESS/2+GROUNDING_LEAD_LENGTH)
    drawing1.add_line(
        tuple(float(v) for v in entrance_grounding_start), tuple(float(v) for v in entrance_grounding_end),
        style="dashed", color="red", name="FeZn entrance lead",
    )
    drawing1.add_line_legend([
        {"style": "solid", "color": "black", "description": "Obrys základových pasů"},
        (wall_outline, "Obrys suterénních stěn nad pasy"),
        (ground_wall_outline, "Obrys stěn 1.NP"),
        (grounding_ring, "Zemnící pásovina FeZn 30/35"),
    ])
    drawing1.add_material_legend([
        ("solid-white", f"Betonové základové pasy\n{FOUNDATION_FOOTING_WIDTH*1000:.0f} × {FOUNDATION_FOOTING_HEIGHT*1000:.0f} mm"),
    ])
    footing_margin = (FOUNDATION_FOOTING_WIDTH-BASEMENT_WALL_THICKNESS)/2
    footing_plan_min = basement_plan_min-footing_margin
    footing_plan_max = basement_plan_max+footing_margin
    drawing1.add_dimension(
        start=tuple(float(v) for v in footing_plan_min),
        end=(float(footing_plan_max[0]), float(footing_plan_min[1])), offset=-.7,
    )
    drawing1.add_dimension(
        start=tuple(float(v) for v in footing_plan_min),
        end=(float(footing_plan_min[0]), float(footing_plan_max[1])), offset=.7,
    )
    drawing1.add_dimension(
        start=(float(footing_plan_max[0])+.6, float(footing_plan_min[1])),
        end=(float(footing_plan_max[0])+.6, float(footing_plan_min[1])+FOUNDATION_FOOTING_WIDTH),
    )
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "found.svg", pdf=PDF_FOUND)

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
    drawing1.add_poly_line(
        stair_entry_clearance_points, style="dashed", name="Stair entry clearance",
    )
    if HOUSE_WIDTH-BWT-STAIR_RIGHT_X > 1e-9:
        drawing1.add_dimension(
            start=(STAIR_RIGHT_X, STAIR_LOWER_START_Y),
            end=(HOUSE_WIDTH-BWT, STAIR_LOWER_START_Y), offset=0.35,
            name="Stairway clearance to west wall",
        )
    drawing1.add_notes(stairway_notes, title="SCHODIŠTĚ")
    drawing1.add_opening_dimension(entrance_door, offset=-1.6, finished_floor_height=GROUND_FLOOR_THICKNESS)
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
        start=(BWT, THIRD_ROOM_STEP_Y+THIRD_ROOM_NARROW_DEPTH/2),
        end=(THIRD_ROOM_NARROW_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y+THIRD_ROOM_NARROW_DEPTH/2),
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
        start=(STAIR_LEFT_X, 2.0),
        end=(STAIR_RIGHT_X, 2.0),
        name="Stairway clear width",
		offset=1.5
    )
    drawing1.add_dimension(
        start=(BATHROOM_LEFT_X+0.3, BWT),
        end=(BATHROOM_LEFT_X+0.3, BATHROOM_PARTITION_Y),
        name="Bathroom clear depth",
    )
    drawing1.add_dimension(
        start=(BATHROOM_LEFT_X+0.3, GARDEN_ROOMS_WALL_Y),
        end=(BATHROOM_LEFT_X+0.3, BATHROOM_PARTITION_Y+INNER_BWT),
        name="Hallway clear depth",
    )
    drawing1.add_dimension(
        start=(BATHROOM_LEFT_X, BWT+0.5),
        end=(BATHROOM_RIGHT_X, BWT+0.5),
        name="Bathroom clear width",
    )

    add_house_cut_symbols(drawing1)
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
        ("concrete", "Železobetonový věnec"),
    ])
    drawing1.add_miako_beam_dimensions(ceiling_garden_rooms, side="end", offset=0.7)
    drawing1.add_miako_beam_dimensions(ceiling_third_room_front, side="start", offset=0.7)
    drawing1.add_miako_beam_dimensions(ceiling_third_room_back, side="start", offset=0.7)
    drawing1.add_miako_beam_dimensions(ceiling_hallway, side="end", offset=-0.45)
    drawing1.add_miako_beam_dimensions(ceiling_bathroom, side="end", offset=0.45)
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
    for slab in (ceiling_third_room_front, ceiling_third_room_back, ceiling_bathroom):
        drawing1.add_dimension(start=slab.start, end=slab.end, offset=-0.55)
    drawing1.add_dimension(start=ceiling_hallway.start, end=ceiling_hallway.end, offset=0.4)
    drawing1.add_miako_beam_schedule([
        {"location": "Pokoj 1 a 2", "slab": ceiling_garden_rooms},
        {"location": "Pokoj 3", "slab": [ceiling_third_room_front, ceiling_third_room_back]},
        {"location": "Chodba", "slab": ceiling_hallway},
        {"location": "Koupelna", "slab": ceiling_bathroom},
    ])
    drawing1.add_line(
        (STAIRWAY_WALL_X, BATHROOM_PARTITION_Y+INNER_BWT/2),
        (HOUSE_WIDTH-BWT, BATHROOM_PARTITION_Y+INNER_BWT/2),
        style="dashed", color="#0080c0", name="Assumed hallway ceiling support",
    )
    drawing1.add_notes([
        f"Uložení nosníků min. {CEILING_BEAM_BEARING*1000:.0f} mm na obou koncích; délky po 250 mm.",
        f"Tolerance celkové šířky skladby ±{CEILING_LAYOUT_TOLERANCE*1000:.0f} mm; úzké vložky uprostřed.",
        "Modrá čárkovaná čára: uvažované pokračování koupelnové stěny pod stropem chodby.",
        "Styk nosníků koupelny a pokoje 3 zatím není řešen.",
        "Styk protilehlých nosníků chodby a pokojů 1 a 2 na společné stěně zatím není řešen.",
    ])
    add_house_cut_symbols(drawing1)
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
        ("brick", f"Nosná zeď - VPC Cihla {INNER_BWT*1000:.0f} mm"),
        ("wood-solid", "Dřevěný sloupek pod vaznicí"),
        ("rockwool-wave", f"Rockwool - fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1, upper_exterior_walls)
    # These continuous coverings are hosted downstairs but span both floors.
    for facade in wall_facades:
        drawing1.include_element(facade)
    drawing1.add_chimney_annotation(chimney)
    drawing1.add_dimension(
        start=(STAIR_RIGHT_X-1.4, upper_stairs.end[1]),
        end=(STAIR_RIGHT_X-1.4, living_room_right_wall_front_y),
        name="Living room wall clearance from stairs",
    )
    for room in upper_room_floors:
        position = Polygon(room.outline).representative_point().coords[0]
        if room == upper_hallway:
            position = (upper_bathroom_right_x, (STAIR_UPPER_END_Y+LIVING_ROOM_WALL_FRONT_Y)/2)
        elif room == upper_bathroom:
            position = ((upper_water_heater_center[0]+0.35+upper_bathroom_right_x)/2,
                        upper_water_heater_center[1])
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*upper_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
    drawing1.add_opening_dimension(
        upper_bathroom_door, offset=0.4, finished_floor_height=UPPER_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        living_room_door, offset=1.15, finished_floor_height=UPPER_FLOOR_THICKNESS,
    )
    for window, offset in (
        (window_living_room_front, -1.3),
        *((window, -0.65) for window in windows_living_room_back),
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
    if HOUSE_WIDTH-BWT-STAIR_RIGHT_X > 1e-9:
        drawing1.add_dimension(
            start=(STAIR_RIGHT_X, STAIR_LOWER_START_Y),
            end=(HOUSE_WIDTH-BWT, STAIR_LOWER_START_Y), offset=0.35,
            name="Stairway clearance to west wall",
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
    # Clear lengths between the faces of the east-side VPC sections.
    east_vpc_walls = sorted(
        (wall for wall in upper_vpc_walls if math.isclose(wall.start[0], BWT)),
        key=lambda wall: wall.start[1]+wall.body_offset,
    )
    east_vpc_gaps = []
    previous_y = BWT
    for wall in east_vpc_walls:
        front_y = wall.start[1]+wall.body_offset
        east_vpc_gaps.append((previous_y, front_y))
        previous_y = front_y+wall.thickness
    east_vpc_gaps.append((previous_y, HOUSE_DEPTH-BWT))
    for index, (start_y, end_y) in enumerate(east_vpc_gaps, 1):
        drawing1.add_dimension(
            start=(BWT+UPPER_VPC_RETURN_LENGTH, start_y),
            end=(BWT+UPPER_VPC_RETURN_LENGTH, end_y),
            offset=-0.35, name=f"East VPC wall clear section {index}",
        )
    drawing1.add_dimension(
        start=(BWT, living_room_wall_y-DRY_WALL_WIDTH/2-0.9),
        end=(living_room_wall_x-DRY_WALL_WIDTH/2, living_room_wall_y-DRY_WALL_WIDTH/2-0.9),
    )
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-1.0, living_room_right_wall_front_y+DRY_WALL_WIDTH),
        end=(HOUSE_WIDTH-BWT-1.0, HOUSE_DEPTH-BWT),
    )
    # Locate the east posts by their configured coordinates, even if the
    # purlin or support arrays are reordered. Dimension only this side.
    east_purlin_index = min(range(len(PURLIN_X_POSITIONS)), key=lambda i: PURLIN_X_POSITIONS[i])
    east_support_x = PURLIN_X_POSITIONS[east_purlin_index]
    east_front_y, east_back_y = sorted(PURLIN_SUPPORT_Y_POSITIONS[east_purlin_index])
    for start_y, end_y, label in (
        (BWT, east_front_y, "Front wall to east purlin support centre"),
        (east_front_y, east_back_y, "East purlin support centre spacing"),
        (east_back_y, HOUSE_DEPTH-BWT, "East purlin support centre to back wall"),
    ):
        drawing1.add_dimension(
            start=(east_support_x, start_y), end=(east_support_x, end_y),
            offset=0.55, name=label,
        )
    drawing1.add_dimension(
        start=(east_support_x+PURLIN_SUPPORT_SIZE[0]/2, east_front_y),
        end=(kitchen_center_x-KITCHEN_UNIT_SIZE[0]/2, east_front_y),
        name="East front purlin support clearance to kitchen run",
    )
    west_purlin_index = max(range(len(PURLIN_X_POSITIONS)), key=lambda i: PURLIN_X_POSITIONS[i])
    west_support_x = PURLIN_X_POSITIONS[west_purlin_index]
    west_back_y = max(PURLIN_SUPPORT_Y_POSITIONS[west_purlin_index])
    wall_back_face_y = (
        living_room_wall_y+DRY_WALL_WIDTH/2
        if west_support_x < living_room_wall_step_x-DRY_WALL_WIDTH
        else living_room_right_wall_front_y+DRY_WALL_WIDTH
    )
    drawing1.add_dimension(
        start=(west_support_x, wall_back_face_y),
        end=(west_support_x, west_back_y-PURLIN_SUPPORT_SIZE[1]/2), offset=0.35,
        name="Rear west purlin support clearance to living room wall",
    )
    add_house_cut_symbols(drawing1)
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
    for element in (*upper_exterior_walls, *upper_ring_beams, wall_plate_east, wall_plate_west, *purlins,
                    *purlin_connection_beams, *purlin_supports, *purlin_braces,
                    *roof_rafters, *collar_ties):
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
        ("Sloupky pod vaznice", purlin_supports, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
        ("Spojovací trámy", purlin_connection_beams, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
        ("Pásky pod vaznice", purlin_y_braces, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
        ("Pásky pod spojovací trámy", purlin_x_braces, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
        ("Krokve", roof_rafters, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
        ("Kleštiny", collar_ties, 0, {"color": "#f4d35e", "pattern": "diagonal1"}),
    ])
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "roof.svg", pdf=PDF_ROOF)


def add_house_section(cut, name, pdf):
    """Create a complete vertical section using the same cut as its plan markers."""
    section_top = max(roof_tiles_top_z, upper.elevation+chimney.end_height)
    section_bottom = FOUNDATION_FOOTING_BOTTOM_Z
    drawing = cut.add_drawing(
        house, name, z=(section_bottom+section_top)/2,
        radius=max(6.5, (section_top-section_bottom)/2+.5),
        storeys=None, doors_closed=True,
        door_annotations=False, automatic_plan_annotations=False,
        right_panel_width=60, section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    # Batting is drawing-only. Add it only where this section crosses an
    # exterior wall, and let the wall helper leave gaps at openings.
    view_x, view_y, _ = cut.view_direction
    for wall in (wall_front_g, wall_west_g, wall_back_g, wall_east_g, *upper_exterior_walls):
        dx, dy = wall.end[0]-wall.start[0], wall.end[1]-wall.start[1]
        if abs((dx*view_x+dy*view_y)/wall.length) < 1-1e-9:
            continue
        options = {}
        if wall in upper_exterior_walls:
            fraction = -((wall.start[0]-cut.center[0])*view_x
                         +(wall.start[1]-cut.center[1])*view_y)/(dx*view_x+dy*view_y)
            section_x = wall.start[0]+fraction*dx
            roof_plane = roof_east if section_x <= roof_ridge_x else roof_west
            roof_bottom_z = plane_height_at(
                *offset_plane(*roof_plane.points, offset=RAFTER_Z_OFFSET),
                x=section_x, y=cut.center[1],
            )
            options["end_z"] = min(wall.storey.elevation+wall.end_height, roof_bottom_z)
        drawing.add_wall_insulation(
            wall, thickness=FACADE_INSULATION_THICKNESS, material="rockwool", **options,
        )
    drawing.add_material_legend([
        ("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
        ("brick", "Nosná zeď - VPC Cihla 175 mm"),
        ("liapor-brick", "Zakládací řada - Liapor"),
        ("ztracene-bedneni", "Ztracené bednění"),
        ("base-plate", "Základová deska"),
        ("concrete", "Železobetonový věnec"),
        ("wood-solid", "Dřevo"),
        ("drywall-diagonal1", "Sádrokarton"),
        ("thermal-impact-insulation", "Podlahová izolace"),
        ("rockwool-wave", "Minerální vata"),
        ("mdf-solid", "MDF záklop"),
        ("vapour-barrier-solid", "OSB záklop + parobrzda"),
    ])
    drawing.render(PROJECT_DIR / f"{name}.svg", pdf=pdf)
    return drawing


for name, cut, pdf in (("aa", aa_cut, PDF_AA), ("bb", bb_cut, PDF_BB)):
    if name in sys.argv:
        add_house_section(cut, name, pdf)


def earth_to_z(m_above_sea):
    """Convert survey heights while keeping the ground-floor wall base at Z=0."""
    return m_above_sea-(GROUND_FINISHED_FLOOR_ELEVATION-GROUND_FLOOR_THICKNESS)


def y_to_earth(y):
    """Initial street-to-garden terrain slope, copied from the old house."""
    return TERRAIN_STREET_ELEVATION+y/HOUSE_DEPTH*(TERRAIN_GARDEN_ELEVATION-TERRAIN_STREET_ELEVATION)


# Profile coordinates: global Y for west/east, global X for street/garden.
# Heights are metres above sea level; edit individual profiles here.
TERRAIN_PROFILES = {
    "pohled_zapad": [
		(-2.0, 415.5),
		(0.0, 415.5),
		(HOUSE_DEPTH, 416.7),
		(HOUSE_DEPTH + 2.0, 416.7),
	],
    "pohled_ulice": [
		(-2.0, 415.5)
	],
    "pohled_zahrada": [
		(-2.0, 416.7)
	],
    "pohled_vychod": [
		(-2.0, 416.7),
		(0.0, 416.7),
		(HOUSE_DEPTH, 415.5),
		(HOUSE_DEPTH + 2.0, 415.5),
	],
}


def add_exterior_view(name, camera, direction, pdf):
    """Render a complete house elevation with terrain masking and closed doors."""
    view_top = max(roof_tiles_top_z, upper.elevation+chimney.end_height)
    view_bottom = min(earth_to_z(height) for _, height in TERRAIN_PROFILES[name])-.4
    drawing = house.add_drawing(
        name, x=camera[0], y=camera[1], z=(view_bottom+view_top)/2,
        radius=max(6.5, (view_top-view_bottom)/2+.5), view="elevation", direction=direction,
        storeys=[foundation, basement, basement_ceiling_storey, ground, ceiling_storey, upper, facade_storey,
                 *roof_layer_storeys.values()],
        door_annotations=False, automatic_plan_annotations=False,
        doors_closed=True, surface_fills=True,
    )
    drawing.add_terrain(TERRAIN_PROFILES[name], earth_to_z=earth_to_z)
    drawing.render(PROJECT_DIR / f"{name}.svg", pdf=pdf)
    return drawing


for name, camera, direction, pdf in (
    ("pohled_zapad", (west_eave_x+1, HOUSE_DEPTH/2), (-1, 0, 0), PDF_POHLED_ZAPAD),
    ("pohled_ulice", (HOUSE_WIDTH/2, -ROOF_GABLE_OVERHANG-1), (0, 1, 0), PDF_POHLED_ULICE),
    ("pohled_zahrada", (HOUSE_WIDTH/2, HOUSE_DEPTH+ROOF_GABLE_OVERHANG+1), (0, -1, 0), PDF_POHLED_ZAHRADA),
    ("pohled_vychod", (east_eave_x-1, HOUSE_DEPTH/2), (1, 0, 0), PDF_POHLED_VYCHOD),
):
    if "pohledy" in sys.argv or name in sys.argv:
        add_exterior_view(name, camera, direction, pdf)
