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

from ifc_utils import CutDefinition, DrawingSheet, House, offset_plane, plane_height_at, window_area
from pdf_utils import PDFFolder


HOUSE_WIDTH = 8.75
HOUSE_DEPTH = 9.0
BWT = 0.24
INNER_BWT = 0.175
PARTITION_THICKNESS = 0.115
DRY_WALL_WIDTH = 0.10
FACADE_INSULATION_THICKNESS = 0.20
EXTERIOR_XPS_INSULATION_THICKNESS = 0.12
FACADE_THICKNESS = 0.005
GARDEN_ROOMS_DEPTH = 3.47  # Clear depth between the divider and inside garden wall.
GARDEN_ROOMS_WALL_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT
THIRD_ROOM_NARROW_WIDTH = HOUSE_WIDTH/2.0 - BWT - 0.125-1.0-0.1-0.05
THIRD_ROOM_NARROW_WALL_X = BWT+THIRD_ROOM_NARROW_WIDTH+DRY_WALL_WIDTH
THIRD_ROOM_WIDTH = 3.47  # Clear width of the left street-side room.
THIRD_ROOM_WALL_X = BWT+THIRD_ROOM_WIDTH+INNER_BWT
STAIRWAY_WIDTH = 2.25  # Clear width beside the west exterior wall.
STAIRWAY_WALL_X = HOUSE_WIDTH-BWT-STAIRWAY_WIDTH
BATHROOM_LEFT_X = THIRD_ROOM_WALL_X
BATHROOM_RIGHT_X = STAIRWAY_WALL_X-INNER_BWT
BATHROOM_DEPTH = 3.0  # Clear depth from the inside front wall.
BATHROOM_PARTITION_Y = BWT+BATHROOM_DEPTH
HALLWAY_OPENING_LENGTH = 1.25  # From the garden-room wall towards the street.
STAIRWAY_OPENING_START_Y = GARDEN_ROOMS_WALL_Y-HALLWAY_OPENING_LENGTH
THIRD_ROOM_STEP_Y = STAIRWAY_OPENING_START_Y-DRY_WALL_WIDTH  # Hallway face meets the opening end.
THIRD_ROOM_NARROW_DEPTH = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_STEP_Y
HALLWAY_OPENING_TOP_GAP = 0.25  # Masonry below the underside of the ground-floor ceiling.

UPPER_BATHROOM_WIDTH = 1.12
LIVING_ROOM_WIDTH = HOUSE_WIDTH - 2*BWT - STAIRWAY_WIDTH - 2*DRY_WALL_WIDTH - UPPER_BATHROOM_WIDTH
UPPER_VPC_RETURN_LENGTH = 1.0  # Four 175 mm wall sections extending from the side walls.
KITCHEN_UNIT_SIZE = (0.64, 0.64, 0.75)
KITCHEN_WALL_GAP = 0.03  # Same 350 mm centre offset as the old house's 640 mm units.
KITCHEN_COOKER_SINK_GAP = 0.06  # Old house: 700 mm centre spacing between 640 mm units.
STOVE_SIZE = (0.60, 0.50, 1.50)

ZAKLADACI_MALTA = 0.02
GROUND_WALL_BASE_COURSE_HEIGHT = ZAKLADACI_MALTA + 0.2
GROUND_WALL_BASE_COURSE_MATERIAL = "Liapor brick"
ground_floor_height = GROUND_WALL_BASE_COURSE_HEIGHT + 2.625
CEMFLOW_AND_FINISH_THICKNESS = 0.065
GROUND_FLOOR_INSULATION_THICKNESS = 0.14
GROUND_FLOOR_THICKNESS = GROUND_FLOOR_INSULATION_THICKNESS+CEMFLOW_AND_FINISH_THICKNESS
PERIMETER_TOP_HEIGHT = GROUND_FLOOR_THICKNESS
GROUND_FINISHED_FLOOR_ELEVATION = 417.8  # Metres above sea level.
# Corner terrain elevations above sea level: X=0 east, X=HOUSE_WIDTH west;
# Y=0 street, Y=HOUSE_DEPTH garden.
TERRAIN_STREET_EAST_ELEVATION = 415.8
TERRAIN_STREET_WEST_ELEVATION = 415.3
TERRAIN_GARDEN_EAST_ELEVATION = 416.8
TERRAIN_GARDEN_WEST_ELEVATION = 416.8
WEST_STONE_WALL_DISTANCE = 4.5  # Beyond the garden end, measured from Y=HOUSE_DEPTH.
WEST_STONE_WALL_WIDTH = 0.5
STONE_WALL_SIDE_OVERHANG = 1.0
WEST_STONE_WALL_TOP_ELEVATION = 418.9
WEST_STONE_WALL_TERRAIN_SLOPE_DEGREES = 10.0
WEST_STONE_WALL_TERRAIN_LENGTH = 2.0
WEST_BACKGROUND_WALL_HOUSE_GAP = 0.05
EAST_STONE_WALL_TERRAIN_SLOPE_DEGREES = 10.0
EAST_STONE_WALL_TERRAIN_LENGTH = 2.0
EAST_VIEW_STONE_WALL_OVERHANG = 2.0
EAST_VIEW_STONE_WALL_LEFT_ELEVATION = 418.8
EAST_VIEW_STONE_WALL_RIGHT_ELEVATION = 417.8
STREET_STONE_WALL_DISTANCE = 3.5
STREET_STONE_WALL_WIDTH = 0.5
STREET_STONE_WALL_TOP_ELEVATION = 418.0
STREET_STONE_WALL_TERRAIN_SLOPE_DEGREES = 10.0
STREET_STONE_WALL_TERRAIN_LENGTH = 2.0
GARAGE_RETAINING_WALL_WIDTH = 0.30
GARAGE_RETAINING_WALL_TOP_ELEVATION = 416.0
SHOW_STREET_BACKGROUND_STONE_WALL = True
STREET_BACKGROUND_WALL_HOUSE_GAP = 0.05
STREET_BACKGROUND_WALL_WEST_EXTENT = 1.0
STREET_BACKGROUND_TERRAIN_BELOW_STAIRS = 0.05
CEILING_THICKNESS = 0.21
# Retain the hallway ceiling layout while its separate front support is designed.
HALLWAY_CEILING_SUPPORT_Y = BATHROOM_PARTITION_Y+INNER_BWT/2
HALLWAY_CEILING_SUPPORT_WIDTH = INNER_BWT
BASEMENT_WALL_HEIGHT = 2.35
BASEMENT_WALL_THICKNESS = 0.25
BASEMENT_SLAB_THICKNESS = 0.15
FOUNDATION_FOOTING_WIDTH = 0.60
FOUNDATION_FOOTING_HEIGHT = 0.50
GROUNDING_LEAD_LENGTH = 1.0  # Length beyond the outside masonry face/corner.
BASEMENT_WALL_TOP_Z = -CEILING_THICKNESS  # Ground-floor layers start at Z = 0.
BASEMENT_FLOOR_START = BASEMENT_WALL_TOP_Z-BASEMENT_WALL_HEIGHT
BASEMENT_FLOOR_THICKNESS = CEMFLOW_AND_FINISH_THICKNESS
BASEMENT_FINISHED_FLOOR_HEIGHT = BASEMENT_FLOOR_START+BASEMENT_FLOOR_THICKNESS
BASEMENT_TO_GROUND_RISE = GROUND_FLOOR_THICKNESS-BASEMENT_FINISHED_FLOOR_HEIGHT
BASEMENT_OPENING_WIDTH = 1.0
BASEMENT_OPENING_TOP_HEIGHT = BASEMENT_WALL_HEIGHT-0.25
GARAGE_FRONT_OPENING_SIDE_CLEARANCE = 0.50
GARAGE_FRONT_OPENING_TOP_HEIGHT = BASEMENT_WALL_HEIGHT-0.20
BASEMENT_SLAB_BOTTOM_Z = BASEMENT_FLOOR_START-BASEMENT_SLAB_THICKNESS
PERIMETER_BOTTOM_Z = BASEMENT_SLAB_BOTTOM_Z  # Top of the foundation footings.
FOUNDATION_FOOTING_BOTTOM_Z = BASEMENT_SLAB_BOTTOM_Z-FOUNDATION_FOOTING_HEIGHT
CEILING_BEAM_BEARING = 0.125  # Minimum at each end, before rounding the beam length up.
CEILING_BEAM_LENGTH_STEP = 0.25
CEILING_LAYOUT_TOLERANCE = 0.07  # Total width mismatch, not the gap at each side.
CEILING_STRIP_WIDTHS = {"beam": 0.17, "wide": 0.455, "narrow": 0.33}
UPPER_FLOOR_THICKNESS = 0.03+CEMFLOW_AND_FINISH_THICKNESS
UPPER_FLOOR_START = ground_floor_height+CEILING_THICKNESS
UPPER_FINISHED_FLOOR_HEIGHT = UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS
UPPER_RING_BEAM_HEIGHT = 0.24
NADEZDIVKA = ZAKLADACI_MALTA + 1.20 + UPPER_RING_BEAM_HEIGHT
WALL_PLATE_SIZE = (0.16, 0.12)
WALL_PLATE_OVERHANG = 0.2
WALL_PLATE_Z = UPPER_FLOOR_START+NADEZDIVKA+WALL_PLATE_SIZE[1]/2
PURLIN_SIZE = (0.17, 0.25)
PURLIN_WALL_DISTANCE = 2.93
PURLIN_X_POSITIONS = (
	BWT+PURLIN_WALL_DISTANCE-PURLIN_SIZE[0]/2.0,
	HOUSE_WIDTH-BWT-PURLIN_WALL_DISTANCE+PURLIN_SIZE[0]/2.0
)
PURLIN_CENTER_HEIGHT = 3.75  # Purlin TOP above the upper-floor datum / ceiling top (legacy name).
PURLIN_Z = UPPER_FLOOR_START+PURLIN_CENTER_HEIGHT-PURLIN_SIZE[1]/2
PURLIN_SUPPORT_SIZE = (0.16, 0.16)
PURLIN_SUPPORT_1_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT/2.0+0.3
PURLIN_SUPPORT_Y_POSITIONS = (
#    (BWT+2.8, HOUSE_DEPTH-BWT-2.8),  # Purlin 1, at PURLIN_X_POSITIONS[0].
#    (BWT+2.8, HOUSE_DEPTH-BWT-2.8),  # Purlin 2, at PURLIN_X_POSITIONS[1].
    (BWT+2.52, BWT+2.52+3),  # Purlin 2, at PURLIN_X_POSITIONS[1].
    (BWT+2.52, BWT+2.52+3),  # Purlin 2, at PURLIN_X_POSITIONS[1].
)
PURLIN_CONNECTION_BEAM_SIZE = (0.12, 0.20)  # Width along Y, height along Z.
PURLIN_CONNECTION_WALL_CLEARANCE = 0.10  # Clear gap from each gable wall's inner face.
PURLIN_CONNECTION_Y_POSITIONS = (
    *sorted({y for positions in PURLIN_SUPPORT_Y_POSITIONS for y in positions}),
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
ROOF_GABLE_OVERHANG = 0.25 + 0.125
CHIMNEY_SIZE = 0.40
CHIMNEY_FLUE_DIAMETER = 0.20
CHIMNEY_ABOVE_ROOF = 1.6
SHOW_CHIMNEY_PLANNING_MARKER = True  # Temporary location marker in basement/ground/ceiling plans.
SHOW_PURLIN_SUPPORT_PLANNING_MARKERS = True  # Project upper-floor post footprints onto those plans.
ROOF_EAVE_SETBACK = 0.02
ROOF_SLOPED_SIDING_BOARD_COUNT = 4
ROOF_WOOD_SIDING_COLOR = "#f2d08b"
ROOF_EDGE_TRIM_THICKNESS = 0.02  # Beyond the front/back tile edges along Y.
GUTTER_DIAMETER = 0.15
GUTTER_WALL_THICKNESS = 0.001
GUTTER_EDGE_GAP = 0.005  # Horizontal clearance outside the tile edge.
GUTTER_DROP_BELOW_TILES = 0.02  # Open rim below the tile edge's underside.
GUTTER_COLOR = "#666666"
# Same roof build-up as house_ifc.py; offsets are normal to each slope.
THERMAL_INSULATION_UNDER_RAFTERS = 0.2
VAPOUR_BARRIER_THICKNESS = 0.015
INSTALLATION_SPACE_THICKNESS = 0.030
GYPSUM_PLASTERBOARD_THICKNESS = 0.025
MDF_THICKNESS = 0.015
UNDERLAY_THICKNESS = 0.001
COUNTER_BATTEN_SIZE = (0.06, 0.06)
TILE_BATTEN_SIZE = (0.06, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_THICKNESS = 0.03
ROOF_TILE_COLOR = "#e46b55"
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
BASEMENT_STAIR_LOWER_RISERS = 7
BASEMENT_STAIR_UPPER_RISERS = 8
BASEMENT_STAIR_LOWER_RUN_LENGTH = (BASEMENT_STAIR_LOWER_RISERS-1)*STAIR_TREAD_LENGTH
BASEMENT_STAIR_UPPER_RUN_LENGTH = (BASEMENT_STAIR_UPPER_RISERS-1)*STAIR_TREAD_LENGTH
BASEMENT_STAIR_RISER_HEIGHT = BASEMENT_TO_GROUND_RISE/(BASEMENT_STAIR_LOWER_RISERS+BASEMENT_STAIR_UPPER_RISERS)
STAIR_FLIGHT_GAP = 0.05
STAIR_LEFT_X = STAIRWAY_WALL_X
STAIR_UPPER_CENTER_X = STAIR_LEFT_X+STAIR_FLIGHT_WIDTH/2
STAIR_LOWER_CENTER_X = STAIR_UPPER_CENTER_X+STAIR_FLIGHT_WIDTH+STAIR_FLIGHT_GAP
STAIR_RIGHT_X = STAIR_LOWER_CENTER_X+STAIR_FLIGHT_WIDTH/2
STAIR_LANDING_START_Y = BWT
STAIR_LANDING_END_Y = STAIR_LANDING_START_Y+STAIR_LANDING_LENGTH
STAIR_LOWER_START_Y = STAIR_LANDING_END_Y+STAIR_LOWER_RUN_LENGTH
STAIR_UPPER_END_Y = STAIR_LANDING_END_Y+STAIR_UPPER_RUN_LENGTH
CHIMNEY_CENTER = (HOUSE_WIDTH/2.0+0.7, HOUSE_DEPTH-BWT-3.47-0.5)
STAIR_WAIST_THICKNESS = 0.15
STAIR_RAILING_HEIGHT = 1.0
STAIR_RAILING_INSET = 0.02  # Centreline inset onto each flight; 60 mm posts clear the edge by 30 mm.
TECHNIKA_RAILING_START_FROM_FRONT = 1.5  # Metres from the front wall's inside face.
if STAIR_RIGHT_X > HOUSE_WIDTH-BWT+1e-9:
    raise ValueError("rotated stairs do not fit between room 3 and the west wall")
if max(STAIR_LOWER_START_Y, STAIR_UPPER_END_Y) > GARDEN_ROOMS_WALL_Y+1e-9:
    raise ValueError("rotated stairs reach the garden-room dividing wall")
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
ENTRANCE_OPENING_WIDTH = 1.1
ENTRANCE_STAIR_RISERS = 8
ENTRANCE_STAIR_TREAD_LENGTH = 0.30
ENTRANCE_STAIR_WIDTH = ENTRANCE_OPENING_WIDTH
ENTRANCE_LANDING_DEPTH = 1.125  # Projection beyond the facade, as in house_ifc.py.
ENTRANCE_LANDING_THICKNESS = 0.20
ENTRANCE_DOOR_WIDTH = 0.9
ENTRANCE_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ENTRANCE_CLEAR_HEIGHT = 2.1
ROOM_DOOR_WIDTH = 0.9
ROOM_DOOR_OPENING_WIDTH = 1.0
ROOM_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.125
ROOM_DOOR_CLEAR_HEIGHT = 2.1
TECHNIKA_SLIDING_DOOR_WIDTH = 0.7
TECHNIKA_SLIDING_DOOR_OPENING_WIDTH = 0.8
TECHNIKA_SLIDING_DOOR_Y = None  # None aligns the opening's garden edge with the chimney's street face.
GARDEN_DOOR_CENTER_CLEARANCE = 0.125
THIRD_ROOM_DOOR_GARDEN_CLEARANCE = 0.125  # From the room 1 face to the construction opening.
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
UPPER_BASIN_SIZE = (0.60, 0.5)
BATHROOM_WINDOW_CENTER_X = BATHROOM_RIGHT_X-0.25-BATHROOM_WINDOW_WIDTH/2
WINDOW_POSITION_STEP = 0.125

PROJECT_DIR = Path("projekt2")
DIR_ARCHITEKTONICKO_STAVEBNI_RESENI = PROJECT_DIR / "D1.1. Architektonicko Stavební Řešení"
PDF_FOLDER = PDFFolder("D1.1.", DIR_ARCHITEKTONICKO_STAVEBNI_RESENI)
PDF_GROUND = Path(PDF_FOLDER.add_pdf("Půdorys 1.NP"))
PDF_CEILING = Path(PDF_FOLDER.add_pdf("Strop nad 1.NP"))
PDF_UPPER = Path(PDF_FOLDER.add_pdf("Půdorys podkroví"))
PDF_ROOF = Path(PDF_FOLDER.add_pdf("Krov"))
PDF_POHLEDY = Path(PDF_FOLDER.add_pdf("Pohledy"))
# Reserve the former individual-elevation numbers to keep later plans stable.
PDF_FOLDER.add_pdf("Pohled - Ulice")
PDF_FOLDER.add_pdf("Pohled - Zahrada")
PDF_FOLDER.add_pdf("Pohled - Východ")
POHLEDY_SCALE = 200
PDF_BASEMENT = Path(PDF_FOLDER.add_pdf("Půdorys suterénu"))
PDF_FOUND = Path(PDF_FOLDER.add_pdf("Základy"))
PDF_AA = Path(PDF_FOLDER.add_pdf("Řez AA"))
PDF_BB = Path(PDF_FOLDER.add_pdf("Řez BB"))
SECTION_OUTLINE_WIDTH = 0.3

RAFTERS_MIDPOINT = CHIMNEY_CENTER[1]-0.04
RAFTER_Y_POSITIONS = (
	0.33,
	-0.125+1.00,
	-0.125+1.00+1.00,
	-0.125+1.00+1.00+1.00,
	-0.125+1.00+1.00+1.00+0.67,
	-0.125+1.00+1.00+1.00+0.67+1.00, # komin
	-0.125+1.00+1.00+1.00+0.67+1.00+0.67,
	-0.125+1.00+1.00+1.00+0.67+1.00+0.67+0.91,
	-0.125+1.00+1.00+1.00+0.67+1.00+0.67+0.91+1.00,
	-0.125+1.00+1.00+1.00+0.67+1.00+0.67+0.91+1.00+1.00,
	HOUSE_DEPTH-0.33,
)
found_chimney_space = False
for i in range(1, len(RAFTER_Y_POSITIONS)):
	dist = abs(RAFTER_Y_POSITIONS[i]-RAFTER_Y_POSITIONS[i-1])
	if dist > 1.0701:
		print("**** WARNING: rafter dist =", dist)
	if i == 5:
		found_chimney_space = found_chimney_space or (
			dist >= 0.99 and
			abs((RAFTER_Y_POSITIONS[i]+RAFTER_Y_POSITIONS[i-1]) / 2.0 - RAFTERS_MIDPOINT) <= 0.05
		)
		#if not found_chimney_space:
#assert(found_chimney_space)

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


def add_purlin_support_planning_markers(drawing):
    """Project timber post footprints into a plan as green crossed rectangles."""
    half_x, half_y = (dimension/2 for dimension in PURLIN_SUPPORT_SIZE)
    for post in purlin_supports:
        x, y = post.start[:2]
        lower = (x-half_x, y-half_y)
        upper = (x+half_x, y+half_y)
        name = f"{drawing.name} {post.Name} Planning Footprint"
        drawing.add_rectangle(lower, upper, color="#2e7d32", name=name)
        drawing.add_line(lower, upper, color="#2e7d32", name=f"{name} Diagonal 1")
        drawing.add_line(
            (x-half_x, y+half_y), (x+half_x, y-half_y),
            color="#2e7d32", name=f"{name} Diagonal 2",
        )


def earth_to_z(m_above_sea):
    """Convert survey heights while keeping the ground-floor wall base at Z=0."""
    return m_above_sea-(GROUND_FINISHED_FLOOR_ELEVATION-GROUND_FLOOR_THICKNESS)


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
    f"Basement wall - ztracene bedneni {BASEMENT_WALL_THICKNESS*1000:g} mm",
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
    (THIRD_ROOM_WALL_X, BWT), (THIRD_ROOM_WALL_X, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_third_room_g.Name = "Hallway - Pokoj 3 lower wall"
# Keep the room-facing surfaces fixed when replacing the recess walls with SDK.
wall_third_room_return_g = ground.wall(
    (THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y+DRY_WALL_WIDTH/2),
    (THIRD_ROOM_WALL_X-INNER_BWT, THIRD_ROOM_STEP_Y+DRY_WALL_WIDTH/2),
    wall_type=dry_wall, height=ground_floor_height,
)
wall_third_room_return_g.Name = "Hallway - Pokoj 3 wall return"
wall_third_room_top_g = ground.wall(
    (THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH/2, THIRD_ROOM_STEP_Y+DRY_WALL_WIDTH),
    (THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH/2, GARDEN_ROOMS_WALL_Y),
    wall_type=dry_wall, height=ground_floor_height,
)
wall_third_room_top_g.Name = "Hallway - Pokoj 3 upper wall"
wall_stairway_g = ground.wall(
    (STAIRWAY_WALL_X, BWT), (STAIRWAY_WALL_X, GARDEN_ROOMS_WALL_Y),
    wall_type=load_bearing_wall_inner, height=ground_floor_height,
)
wall_stairway_g.Name = "Stairway - hallway and bathroom wall"
wall_bathroom_partition_g = ground.wall(
    (BATHROOM_LEFT_X, BATHROOM_PARTITION_Y+DRY_WALL_WIDTH/2),
    (BATHROOM_RIGHT_X, BATHROOM_PARTITION_Y+DRY_WALL_WIDTH/2),
    wall_type=dry_wall, height=ground_floor_height,
)
wall_bathroom_partition_g.Name = "Hallway - bathroom SDK wall"
stairway_opening = wall_stairway_g.add_opening(
    name="Hallway - stairway opening",
    at=STAIRWAY_OPENING_START_Y-wall_stairway_g.start[1],
    width=HALLWAY_OPENING_LENGTH,
    height=ground_floor_height-HALLWAY_OPENING_TOP_GAP,
)
bathroom_left_opening = wall_third_room_g.add_opening(
    name="Hallway - bathroom left wall opening",
    at=STAIRWAY_OPENING_START_Y-wall_third_room_g.start[1],
    width=HALLWAY_OPENING_LENGTH,
    height=ground_floor_height-HALLWAY_OPENING_TOP_GAP,
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
    at=0.125,
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
    wall_stairway_g,
)
# Apply the base course to all ground-floor masonry walls.
# Add subsequent ground-floor walls above this common finishing pass.
for wall in ground.walls:
    load_bearing = wall in ground_load_bearing_walls
    role = "load bearing" if load_bearing else "partition"
    material_set = ifcopenshell.util.element.get_material(wall, should_skip_usage=True)
    wall_material = material_set.MaterialLayers[0].Material.Name
    if wall_material == "Brick":
        layers = [
            (GROUND_WALL_BASE_COURSE_MATERIAL, GROUND_WALL_BASE_COURSE_HEIGHT),
            (wall_material, wall.height-GROUND_WALL_BASE_COURSE_HEIGHT),
        ]
        wall.set_vertical_material_layers(
            layers,
            type_name=f"Ground {role} wall - VPC {wall.thickness*1000:g} mm - Liapor base course",
        )
    common = ifcopenshell.api.pset.add_pset(house.model, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": load_bearing})

# Centre solid basement walls beneath the physical bodies, including walls
# whose ground-floor reference line lies on a face rather than the centre.
basement_walls = []
basement_wall_corners = []
basement_wall_footprints = []
basement_source_walls = tuple(
    wall for wall in ground.walls
    if wall not in (wall_third_room_return_g, wall_third_room_top_g, wall_bathroom_partition_g)
)
for source in basement_source_walls:
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
    basement_wall_footprints.append(Polygon((
        start-normal*BASEMENT_WALL_THICKNESS/2,
        end-normal*BASEMENT_WALL_THICKNESS/2,
        end+normal*BASEMENT_WALL_THICKNESS/2,
        start+normal*BASEMENT_WALL_THICKNESS/2,
    )))
    for point in (start, end):
        for sign in (-1, 1):
            basement_wall_corners.append(point+sign*normal*BASEMENT_WALL_THICKNESS/2)
basement_walls = tuple(basement_walls)

# One continuous slab covers the full outer footprint of the thicker walls.
basement_plan_min = np.min(basement_wall_corners, axis=0)
basement_plan_max = np.max(basement_wall_corners, axis=0)
# Rooms and floor layers follow the clear spaces between the basement walls.
basement_clear_floor = box(*basement_plan_min, *basement_plan_max).difference(
    unary_union(basement_wall_footprints),
)
basement_room_regions = (
    (basement_clear_floor,) if basement_clear_floor.geom_type == "Polygon"
    else tuple(basement_clear_floor.geoms)
)
basement_rooms = []
for index, region in enumerate(sorted(
    (region for region in basement_room_regions if region.area > 1e-8),
    key=lambda region: (-round(region.centroid.y, 8), region.centroid.x),
), 1):
    center = region.representative_point()
    name = "Skladovací prostor"
    if center.y < GARDEN_ROOMS_WALL_Y:
        if center.x < THIRD_ROOM_WALL_X:
            name = "Garáž"
        elif center.x > STAIRWAY_WALL_X:
            name = "Schody"
    basement_rooms.append(dict(identifier=f"S.{index:02d}", name=name, region=region))
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
basement_room_floors = tuple(
    basement.floor_layer(
        room["name"], room_id=room["identifier"],
        outline=tuple(room["region"].exterior.coords)[:-1],
        thickness=BASEMENT_FLOOR_THICKNESS,
        buildup_material=FLOOR_BUILDUP_MATERIAL, color="#b8b8b8",
    )
    for room in basement_rooms
)
# Resolve each host from its ground-floor source; room extents stay separate
# from the circulation openings so the five room identifiers remain stable.
basement_walls_by_source = {wall.source_wall: wall for wall in basement_walls}
basement_rooms_by_id = {room["identifier"]: room["region"] for room in basement_rooms}
wall_basement_s03_s04 = basement_walls_by_source[wall_third_room_g]
wall_basement_s04_s05 = basement_walls_by_source[wall_stairway_g]
wall_basement_garden_rooms = basement_walls_by_source[wall_garden_rooms_g]
wall_basement_s01_s02 = basement_walls_by_source[wall_garden_partition_g]
wall_basement_front = basement_walls_by_source[wall_front_g]
basement_garden_wall_inner_y = basement_rooms_by_id["S.04"].bounds[3]

basement_garage_door = wall_basement_s03_s04.add_door(
    name="Basement door S.03 - S.04",
    at=basement_garden_wall_inner_y-0.75-BASEMENT_OPENING_WIDTH-wall_basement_s03_s04.start[1],
    width=0.9, opening_width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
    operation="SINGLE_SWING_RIGHT",
	reverse_swing=True
)
basement_stairway_opening = wall_basement_s04_s05.add_opening(
    name="Basement opening S.04 - S.05",
    at=basement_garden_wall_inner_y-0.75-BASEMENT_OPENING_WIDTH-wall_basement_s04_s05.start[1],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
basement_stair_room_x0, _, basement_stair_room_x1, _ = basement_rooms_by_id["S.05"].bounds
basement_garden_opening = wall_basement_garden_rooms.add_opening(
    name="Basement opening S.02 - S.05",
    at=(basement_stair_room_x0+basement_stair_room_x1-BASEMENT_OPENING_WIDTH)/2-wall_basement_garden_rooms.start[0],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
_, basement_garden_room_y0, _, basement_garden_room_y1 = basement_rooms_by_id["S.01"].bounds
basement_storage_opening = wall_basement_s01_s02.add_opening(
    name="Basement opening S.01 - S.02",
    at=(basement_garden_room_y0+basement_garden_room_y1-BASEMENT_OPENING_WIDTH)/2-wall_basement_s01_s02.start[1],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
basement_garage_x0, _, basement_garage_x1, _ = basement_rooms_by_id["S.03"].bounds
garage_front_opening = wall_basement_front.add_opening(
    name="Garage front opening",
    at=basement_garage_x0+GARAGE_FRONT_OPENING_SIDE_CLEARANCE-wall_basement_front.start[0],
    width=basement_garage_x1-basement_garage_x0-2*GARAGE_FRONT_OPENING_SIDE_CLEARANCE,
    height=GARAGE_FRONT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
garage_front_door = wall_basement_front.add_garage_door(
    garage_front_opening, name="Garage sectional door", color="#ffffff",
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
        (THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y),
        (THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, GARDEN_ROOMS_WALL_Y), (BWT, GARDEN_ROOMS_WALL_Y),
    ),
    **floor_layer_settings,
)
# Keep the floor up to the unchanged bathroom partition, including the
# stair approach, and exclude the longer solid part of its side wall.
hallway_front_y = BATHROOM_PARTITION_Y+DRY_WALL_WIDTH
hallway_outline = box(
    THIRD_ROOM_WALL_X, hallway_front_y, HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y,
).union(box(
    THIRD_ROOM_NARROW_WALL_X, THIRD_ROOM_STEP_Y+DRY_WALL_WIDTH,
    THIRD_ROOM_WALL_X, GARDEN_ROOMS_WALL_Y,
))
if STAIRWAY_OPENING_START_Y > hallway_front_y:
    hallway_outline = hallway_outline.difference(box(
        BATHROOM_RIGHT_X, hallway_front_y, STAIRWAY_WALL_X, STAIRWAY_OPENING_START_Y,
    ))
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
ground_room_floors = (pokoj1, pokoj2, pokoj3, (chodba, 0.3, -0.2), koupelna)

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
bathroom_water_heater = ground.furniture(
    "Zásobník\nTUV", kind="USERDEFINED",
    size=(0.7, 0.7, 2.0),
    center=(bathroom_services_center_x, BWT+0.05+0.7/2),
    start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
)
basement_water_meter = basement.furniture(
    "Vodo-\nměr", kind="USERDEFINED",
    size=(0.6, 0.55, 0.9),
    center=(bathroom_services_center_x, BWT+0.7),
    start_height=BASEMENT_FLOOR_THICKNESS,
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
    path=upper_stairs.railing_path("right", inset=STAIR_RAILING_INSET),
    height=STAIR_RAILING_HEIGHT,
    color="#C8B090",
)
lower_stair_railing = ground.railing(
    "Lower stair flight railing",
    path=lower_stairs.railing_path("right", inset=STAIR_RAILING_INSET),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
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
def stairway_notes_for(lower, upper):
    return [
        f"Šířka ramene: {lower.width*1000:.0f} mm",
        f"Nášlap: {lower.tread_length*1000:.0f} mm",
        f"Výška stupně: {lower.riser_height*1000:.1f} mm".replace(".", ","),
        f"Počet výšek: {lower.risers} + {upper.risers} = {lower.risers+upper.risers}",
    ]


stairway_notes = stairway_notes_for(lower_stairs, upper_stairs)


def add_entrance_stairs():
    """West entrance landing and timber flight, descending towards the garden."""
    opening = entrance_door.FillsVoids[0].RelatingOpeningElement
    opening_placement = ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)
    landing_street_y = float(opening_placement[1, 3])
    landing_garden_y = landing_street_y+ENTRANCE_OPENING_WIDTH
    foot_y = landing_garden_y+(ENTRANCE_STAIR_RISERS-1)*ENTRANCE_STAIR_TREAD_LENGTH
    fraction = min(1.0, max(0.0, foot_y/HOUSE_DEPTH))
    foot_elevation = TERRAIN_STREET_WEST_ELEVATION+fraction*(
        TERRAIN_GARDEN_WEST_ELEVATION-TERRAIN_STREET_WEST_ELEVATION
    )
    foot_z = earth_to_z(foot_elevation)
    landing_z = float(ifcopenshell.util.placement.get_local_placement(entrance_door.ObjectPlacement)[2, 3])
    if foot_z >= landing_z:
        raise ValueError("entrance stair foot must be below the door threshold")
    if not 0 < ENTRANCE_STAIR_WIDTH <= ENTRANCE_LANDING_DEPTH:
        raise ValueError("entrance flight must fit within the landing projection")
    facade_x = HOUSE_WIDTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS
    outer_x = facade_x+ENTRANCE_LANDING_DEPTH
    center_x = outer_x-ENTRANCE_STAIR_WIDTH/2
    stairs = ground.stair(
        (center_x, foot_y), (center_x, landing_garden_y),
        name="Entrance stair", width=ENTRANCE_STAIR_WIDTH,
        start_height=foot_z-ground.elevation, height=landing_z-foot_z,
        risers=ENTRANCE_STAIR_RISERS, construction="timber",
        color="#bfc3c5",
    )
    # Extend through the facade reveal to the west wall's outer face.
    landing = ground.stair_landing(
        (HOUSE_WIDTH, landing_street_y), (outer_x, landing_garden_y),
        name="Entrance landing", height=stairs.end_height,
        thickness=ENTRANCE_LANDING_THICKNESS, color="#bfc3c5",
    )
    inset = 0.03
    path = stairs.railing_path("left", inset=inset)
    path = path.extended((
        (path[-1][0], landing_street_y+inset, landing_z),
        (facade_x+inset, landing_street_y+inset, landing_z),
    ))
    railing = ground.railing(
        "Entrance stair and landing railing", path=path,
        height=STAIR_RAILING_HEIGHT, color="#C8B090",
    )
    return stairs, landing, railing


entrance_stairs, entrance_landing, entrance_railing = add_entrance_stairs()
entrance_stairway_notes = [
    f"Vstupní: {entrance_stairs.risers} výšek po {entrance_stairs.riser_height*1000:.1f} mm".replace(".", ",")+".",
    f"Šířka {entrance_stairs.width*1000:.0f} mm; nášlap {entrance_stairs.tread_length*1000:.0f} mm.",
]
print(f"Entrance stairs: {entrance_stairs.risers} risers x {entrance_stairs.riser_height*1000:.1f} mm; "
      f"tread {entrance_stairs.tread_length*1000:.0f} mm; "
      f"2h+b = {(2*entrance_stairs.riser_height+entrance_stairs.tread_length)*1000:.1f} mm")

# Stack the same two-flight layout below the ground-floor stairway, shifted
# just enough to fit the thicker, centred basement walls.
basement_stair_room = next(room["region"] for room in basement_rooms if room["name"] == "Schody")
basement_stair_left_x, basement_landing_start_y, basement_stair_room_right_x, basement_stair_room_back_y = basement_stair_room.bounds
basement_stair_right_x = basement_stair_left_x+2*STAIR_FLIGHT_WIDTH+STAIR_FLIGHT_GAP
basement_landing_end_y = basement_landing_start_y+STAIR_LANDING_LENGTH
basement_lower_start_y = basement_landing_end_y+BASEMENT_STAIR_LOWER_RUN_LENGTH
basement_upper_end_y = basement_landing_end_y+BASEMENT_STAIR_UPPER_RUN_LENGTH
if (basement_stair_right_x > basement_stair_room_right_x+1e-9
        or max(basement_lower_start_y, basement_upper_end_y) > basement_stair_room_back_y+1e-9):
    raise ValueError("basement stairs do not fit inside the clear stairway room")
basement_upper_center_x = basement_stair_left_x+STAIR_FLIGHT_WIDTH/2
basement_lower_center_x = basement_stair_right_x-STAIR_FLIGHT_WIDTH/2
basement_lower_stairs = basement.stair(
    (basement_lower_center_x, basement_lower_start_y),
    (basement_lower_center_x, basement_landing_end_y),
    name="Basement lower stair flight", width=STAIR_FLIGHT_WIDTH,
    start_height=BASEMENT_FLOOR_THICKNESS,
    height=BASEMENT_STAIR_RISER_HEIGHT*BASEMENT_STAIR_LOWER_RISERS,
    risers=BASEMENT_STAIR_LOWER_RISERS, underside="sloped", waist_thickness=STAIR_WAIST_THICKNESS,
)
basement_stair_landing = basement.stair_landing(
    (basement_stair_left_x, basement_landing_start_y),
    (basement_stair_right_x, basement_landing_end_y),
    name="Basement middle stair landing", height=basement_lower_stairs.end_height,
    thickness=STAIR_WAIST_THICKNESS,
)
basement_upper_stairs = basement.stair(
    (basement_upper_center_x, basement_landing_end_y),
    (basement_upper_center_x, basement_upper_end_y),
    name="Basement upper stair flight", width=STAIR_FLIGHT_WIDTH,
    start_height=basement_lower_stairs.end_height,
    height=BASEMENT_STAIR_RISER_HEIGHT*BASEMENT_STAIR_UPPER_RISERS,
    risers=BASEMENT_STAIR_UPPER_RISERS, underside="sloped", waist_thickness=STAIR_WAIST_THICKNESS,
)
basement_stair_railing = basement.railing(
    "Basement stair flight railing",
    path=basement_upper_stairs.railing_path("right", inset=STAIR_RAILING_INSET),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
)
basement_lower_stair_railing = basement.railing(
    "Basement lower stair flight railing",
    path=basement_lower_stairs.railing_path("right", inset=STAIR_RAILING_INSET),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
)
basement_route_landing_y = (basement_landing_start_y+basement_landing_end_y)/2
basement_stair_walking_route = (
    basement_lower_stairs.start, (basement_lower_center_x, basement_route_landing_y),
    (basement_upper_center_x, basement_route_landing_y), basement_upper_stairs.end,
)
basement_stairway_notes = stairway_notes_for(basement_lower_stairs, basement_upper_stairs)+[
    f"Rozdíl hotových podlah: {BASEMENT_TO_GROUND_RISE*1000:.0f} mm",
]
print(f"Basement to ground finished-floor rise: {BASEMENT_TO_GROUND_RISE:.3f} m; "
      f"stair riser: {basement_lower_stairs.riser_height*1000:.1f} mm "
      f"({BASEMENT_STAIR_LOWER_RISERS} + {BASEMENT_STAIR_UPPER_RISERS} risers)")

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
# Both parts bear on the full masonry wall; the narrower room walls are SDK.
# Keep their adjoining edges fixed so the two parallel end beams do not overlap.
ceiling_third_room_front = add_miako_ceiling(
    "Ceiling - Pokoj 3 street part",
    (BWT, BWT, THIRD_ROOM_WALL_X-INNER_BWT, BATHROOM_PARTITION_Y),
    beam_axis="x", width_alignment="end",
)
ceiling_third_room_back = add_miako_ceiling(
    "Ceiling - Pokoj 3 garden part",
    (BWT, BATHROOM_PARTITION_Y, THIRD_ROOM_WALL_X-INNER_BWT, GARDEN_ROOMS_WALL_Y),
    beam_axis="x", width_alignment="start",
)
# The front bearing requires a separate structural support above the SDK/stairs.
ceiling_hallway = add_miako_ceiling(
    "Ceiling - Chodba",
    (THIRD_ROOM_WALL_X, HALLWAY_CEILING_SUPPORT_Y+HALLWAY_CEILING_SUPPORT_WIDTH/2,
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
    not positions for positions in PURLIN_SUPPORT_Y_POSITIONS
):
    raise ValueError("PURLIN_SUPPORT_Y_POSITIONS must contain a nonempty tuple of Y coordinates for each purlin")
purlin_bottom_z = PURLIN_Z-PURLIN_SIZE[1]/2
purlin_support_top_z = purlin_bottom_z
purlin_connection_bottom_z = PURLIN_Z-PURLIN_CONNECTION_BEAM_SIZE[1]/2
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
                continue
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
# Match the visible plasterboard faces at the inner edge of the east purlin.
# Layer offsets are perpendicular to the slope, so the purlin bottom alone
# does not give the height of this junction. The west junction is symmetric.
FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z = plane_height_at(
    *offset_plane(*roof_east.points, offset=GYPSUM_PLASTERBOARD_BOTTOM),
    x=PURLIN_X_POSITIONS[0]+PURLIN_SIZE[0]/2, y=0,
)
FLAT_VAPOUR_BARRIER_TOP_Z = (
    FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z+GYPSUM_PLASTERBOARD_THICKNESS
    +INSTALLATION_SPACE_THICKNESS+VAPOUR_BARRIER_THICKNESS
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
upper_partition_cuts = (
    *(offset_plane(*plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM)
      for plane in (roof_east, roof_west)),
    ((0, 0, FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z),
     (1, 0, FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z),
     (0, 1, FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z)),
)
wall_living_room_side_u = upper.wall(
    (living_room_wall_x, BWT), (living_room_wall_x, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
upper_technical_left_x = wall_living_room_side_u.start[0]-wall_living_room_side_u.body_offset
upper_technical_right_x = STAIR_LEFT_X-DRY_WALL_WIDTH
upper_technical_center_x = (upper_technical_left_x+STAIR_LEFT_X)/2
# Keep the VPC sections centred over the ground-floor load-bearing wall.
upper_vpc_living_room_center_y = (
    wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset+wall_garden_rooms_g.thickness/2
)
# Use the first west-purlin support for the new technical-room cross-wall.
living_room_support_ys = sorted(PURLIN_SUPPORT_Y_POSITIONS[max(
    range(len(PURLIN_X_POSITIONS)), key=lambda index: PURLIN_X_POSITIONS[index],
)])
upper_technical_cross_y = living_room_support_ys[0]
upper_technical_cross_front_y = upper_technical_cross_y-DRY_WALL_WIDTH/2
upper_technical_cross_back_y = upper_technical_cross_y+DRY_WALL_WIDTH/2
# Align the garden faces of the horizontal SDK and the nearby VPC sections.
living_room_right_wall_y = upper_vpc_living_room_center_y+(INNER_BWT-DRY_WALL_WIDTH)/2
living_room_right_wall_front_y = living_room_right_wall_y-DRY_WALL_WIDTH/2
upper_technical_back_y = living_room_right_wall_front_y
LIVING_ROOM_WALL_FRONT_Y = living_room_right_wall_front_y
LIVING_ROOM_DEPTH = HOUSE_DEPTH-BWT-LIVING_ROOM_WALL_FRONT_Y-DRY_WALL_WIDTH
living_room_wall_y = living_room_right_wall_y
wall_living_room_side_extension_u = upper.wall(
    (living_room_wall_x, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2),
    (living_room_wall_x, living_room_wall_y+DRY_WALL_WIDTH/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
# Keep the source-wall centre below the sloped ceiling so the clipping
# retains the wall below it rather than the wedge above the roof plane.
living_room_right_wall_height = min(
    gable_wall_height,
    2*(min(plane_height_at(
        *cut, x=(living_room_wall_x+DRY_WALL_WIDTH/2+HOUSE_WIDTH-BWT-UPPER_VPC_RETURN_LENGTH)/2,
        y=living_room_right_wall_y,
    ) for cut in upper_partition_cuts)-UPPER_FLOOR_START)-0.01,
)
wall_living_room_back_u = upper.wall(
    (living_room_wall_x+DRY_WALL_WIDTH/2, living_room_right_wall_y),
    (HOUSE_WIDTH-BWT-UPPER_VPC_RETURN_LENGTH, living_room_right_wall_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
# Keep the stair-side face flush with the stairwell edge; thickness is in Technika.
upper_technical_wall_x = STAIR_LEFT_X-DRY_WALL_WIDTH/2
wall_technical_stairway_u = upper.wall(
    (upper_technical_wall_x, upper_technical_cross_front_y),
    (upper_technical_wall_x, living_room_right_wall_front_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
wall_technical_cross_u = upper.wall(
    (upper_technical_left_x, upper_technical_cross_y),
    (upper_technical_right_x, upper_technical_cross_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
# The front part remains open to the stairwell, protected by a 60 mm railing.
upper_technical_railing_inset = 0.03
upper_technical_railing = upper.railing(
    "Technika - stairwell railing",
    path=(
        (STAIR_LEFT_X-upper_technical_railing_inset,
         BWT+TECHNIKA_RAILING_START_FROM_FRONT+upper_technical_railing_inset, UPPER_FINISHED_FLOOR_HEIGHT),
        (STAIR_LEFT_X-upper_technical_railing_inset,
         upper_technical_cross_front_y-upper_technical_railing_inset, UPPER_FINISHED_FLOOR_HEIGHT),
    ),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
)
technical_sliding_door_y = (
    CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2-TECHNIKA_SLIDING_DOOR_OPENING_WIDTH
    if TECHNIKA_SLIDING_DOOR_Y is None else TECHNIKA_SLIDING_DOOR_Y
)
technical_sliding_door = wall_technical_stairway_u.add_door(
    name="Technika sliding door",
    at=technical_sliding_door_y-wall_technical_stairway_u.start[1],
    opening_width=TECHNIKA_SLIDING_DOOR_OPENING_WIDTH,
    width=TECHNIKA_SLIDING_DOOR_WIDTH,
    height=UPPER_FLOOR_THICKNESS+ROOM_DOOR_HEIGHT-GROUND_FLOOR_THICKNESS,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=UPPER_FLOOR_THICKNESS,
    operation="SLIDING_TO_RIGHT",  # Towards the street, clear of the horizontal wall.
)
# Keep the masonry sections in their existing rows. Align the front row
# with the ground-floor bathroom/room 3 wall, on both sides of the house.
upper_vpc_front_y = wall_bathroom_partition_g.start[1]+wall_bathroom_partition_g.body_offset
upper_vpc_walls = []
upper_vpc_footprints = []
for side, start_x in (
    ("West", HOUSE_WIDTH-BWT-UPPER_VPC_RETURN_LENGTH),
    ("East", BWT),
):
    for position, front_y in (
        ("living room", upper_vpc_living_room_center_y-INNER_BWT/2),
        ("bathroom wall alignment", upper_vpc_front_y),
    ):
        end_x = start_x+UPPER_VPC_RETURN_LENGTH
        # This face-based VPC type grows towards +Y. Keep the living-room
        # sections over the ground-floor wall and the front sections aligned
        # with the bathroom wall's room-facing surface.
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
living_room_door = wall_living_room_back_u.add_door(
    name="Living room door",
    at=upper_stairs.end[0]-ROOM_DOOR_OPENING_WIDTH/2-wall_living_room_back_u.start[0],
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=UPPER_FLOOR_THICKNESS+ROOM_DOOR_HEIGHT-GROUND_FLOOR_THICKNESS,
    clear_height=ROOM_DOOR_CLEAR_HEIGHT,
    sill_height=UPPER_FLOOR_THICKNESS,
    operation="SINGLE_SWING_LEFT",
)
for wall, name in (
    (wall_living_room_side_u, "Living room - side partition"),
    (wall_living_room_side_extension_u, "Living room - side partition above chimney"),
    (wall_living_room_back_u, "Living room - back partition"),
    (wall_technical_stairway_u, "Technika - stairway partition"),
    (wall_technical_cross_u, "Technika - toilet cross partition"),
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
    (HOUSE_WIDTH-BWT, living_room_right_wall_front_y+DRY_WALL_WIDTH),
    (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
    (BWT, HOUSE_DEPTH-BWT),
)).difference(upper_vpc_region).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
))
living_room = upper.floor_layer(
    "Obývací pokoj", room_id="1.01",
    outline=tuple(living_room_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_technical_outline = box(
    upper_technical_left_x, BWT, STAIR_LEFT_X, upper_technical_cross_front_y,
)
upper_technical_room = upper.floor_layer(
    "Technika", room_id="1.02", outline=tuple(upper_technical_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_toilet_outline = box(
    upper_technical_left_x, upper_technical_cross_back_y, upper_technical_right_x, upper_technical_back_y,
).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
))
upper_toilet_room = upper.floor_layer(
    "Zachod", room_id="1.04", outline=tuple(upper_toilet_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_hallway_outline = box(
    STAIR_LEFT_X, STAIR_UPPER_END_Y, HOUSE_WIDTH-BWT, living_room_right_wall_front_y,
).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
)).difference(upper_vpc_region)
upper_hallway = upper.floor_layer(
    "Chodba", room_id="1.03", outline=tuple(upper_hallway_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_room_floors = (living_room, upper_technical_room, upper_hallway, upper_toilet_room)
upper_room_windows = {
    living_room.room_id: (window_living_room_front, *windows_living_room_back),
    upper_technical_room.room_id: (),
    upper_hallway.room_id: (),
    upper_toilet_room.room_id: (),
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
# Return the basin to the gardenward half of the hallway beside the washer.
upper_basin_center_x = HOUSE_WIDTH-BWT-0.4-upper_fixture_wall_gap-UPPER_BASIN_SIZE[1]/2
upper_basin_center_y = min(
    STAIR_UPPER_END_Y+3*upper_hallway_right_depth/4,
    upper_vpc_living_room_center_y-INNER_BWT/2-upper_fixture_wall_gap-UPPER_BASIN_SIZE[0]/2,
)
upper_hallway_basin = upper.asset(
    "Umyvadlo", asset="basin_large", size=UPPER_BASIN_SIZE,
    center=(upper_basin_center_x, upper_basin_center_y),
    start_height=UPPER_FLOOR_THICKNESS+0.85-0.25,
    rotation=-90,  # Front towards -X, facing into the hallway from the west wall.
)
# Centre the equipment between the room's finished wall faces.
upper_recuperation_center = (upper_technical_center_x,
                             BWT+upper_fixture_wall_gap+0.25)
upper_toilet_center = (
    upper_technical_right_x - 0.5,
    living_room_support_ys[0]+PURLIN_SUPPORT_SIZE[1]/2+upper_fixture_wall_gap+0.35,
)
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
upper_hydrobox_center = (
    upper_technical_left_x+0.3,
    (upper_recuperation_center[1]+0.5/2+upper_toilet_center[1]-0.53/2)/2,
)
upper_hydrobox = upper.furniture(
    "Hydro-\nbox", kind="USERDEFINED", size=(0.8, 0.5, 0.9), color="#ffffff",
    center=upper_hydrobox_center,
    start_height=UPPER_FLOOR_THICKNESS,
	rotation=90,
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
    center=(
		CHIMNEY_CENTER[0]-0.6,
        CHIMNEY_CENTER[1]
	),
    start_height=UPPER_FLOOR_THICKNESS+0.05,
    rotation=90,  # Front toward the garden / back wall (+Y).
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
    purlin_inner_x = PURLIN_X_POSITIONS[purlin_index]+(1 if purlin_index == 0 else -1)*PURLIN_SIZE[0]/2
    inner_x = (inner_wall_x, purlin_inner_x)
    purlin_bottom_cut = ((0, 0, purlin_bottom_z),
                         (1, 0, purlin_bottom_z), (0, 1, purlin_bottom_z))
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
        ("Roof tiles", ROOF_TILE_BOTTOM, ROOF_TILE_THICKNESS, "Roof tiles", ROOF_TILE_COLOR, 0),
    )
    layers = []
    for key, offset, thickness, material, color, transparency in definitions:
        is_inner = key in {"Thermal insulation under rafters", "Vapour barrier", "Gypsum plasterboard"}
        is_tile = key=="Roof tiles"
        x_limits = inner_x if is_inner else outer_x if is_tile else board_x
        y_limits = inner_y if is_inner else tile_y if is_tile else board_y
        extra_cuts = (
            (roof_vertical_cut(inner_wall_x), roof_vertical_cut(purlin_inner_x), purlin_bottom_cut) if is_inner
            else () if is_tile else (roof_vertical_cut(inset_eave_x),)
        )
        layer = plane.layer(
            f"{side} {key}", outline=roof_layer_outline(plane, x_limits, y_limits, offset, thickness),
            z_offset=offset, thickness=thickness, material=material, color=color,
            transparency=transparency, extra_cuts=extra_cuts,
        )
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


flat_ceiling_plane = roof.plane(
    "Horizontal ceiling",
    points=((0, 0, FLAT_VAPOUR_BARRIER_TOP_Z),
            (1, 0, FLAT_VAPOUR_BARRIER_TOP_Z),
            (0, 1, FLAT_VAPOUR_BARRIER_TOP_Z)),
)


def add_horizontal_roof_layers():
    """Join the sloped plasterboard undersides, preserving the horizontal stack."""
    left = PURLIN_X_POSITIONS[0]+PURLIN_SIZE[0]/2
    right = PURLIN_X_POSITIONS[1]-PURLIN_SIZE[0]/2
    if left >= right:
        raise ValueError("purlins leave no space for the horizontal ceiling")
    outline = ((left, BWT), (right, BWT),
               (right, HOUSE_DEPTH-BWT), (left, HOUSE_DEPTH-BWT))
    layers = []
    for key, offset, thickness, material, color, transparency in (
        ("Vapour barrier", -VAPOUR_BARRIER_THICKNESS, VAPOUR_BARRIER_THICKNESS,
         "Vapour barrier", "#4A90E2", 0.35),
        ("Gypsum plasterboard", FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z-FLAT_VAPOUR_BARRIER_TOP_Z,
         GYPSUM_PLASTERBOARD_THICKNESS, "Gypsum plasterboard", "#E8E5DE", 0),
    ):
        layer = flat_ceiling_plane.layer(
            f"Horizontal {key}", outline=outline, z_offset=offset, thickness=thickness,
            material=material, color=color, transparency=transparency,
        )
        roof_layer_storeys[key].add(layer)
        layers.append(layer)
    return tuple(layers)


horizontal_roof_layers = add_horizontal_roof_layers()
roof_layers = (
    *add_roof_build_up(roof_east, "East", 0, east_eave_x, BWT),
    *add_roof_build_up(roof_west, "West", 1, west_eave_x, HOUSE_WIDTH-BWT),
    *horizontal_roof_layers,
)
# The transverse SDK partition also meets the exposed west purlin.
cut_roof_layer_at_purlin(wall_living_room_back_u, 1)
cut_roof_layer_at_purlin(wall_technical_cross_u, 1)
add_timber_clearances((wall_living_room_back_u, wall_technical_stairway_u, wall_technical_cross_u), purlin_supports)
add_timber_clearances(
    (wall_living_room_side_u, wall_living_room_side_extension_u, wall_living_room_back_u,
     wall_technical_stairway_u, wall_technical_cross_u,
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
print(f"Roof ridge elevation (top of roof tiles): {GROUND_FINISHED_FLOOR_ELEVATION+total_house_height:.3f} m above sea level")
print(f"Basement finished-floor elevation: {GROUND_FINISHED_FLOOR_ELEVATION-BASEMENT_TO_GROUND_RISE:.3f} m above sea level")
plasterboard_wall_heights = {}

plasterboard_height_at_wall = plane_height_at(
        *offset_plane(*roof_east.points, offset=GYPSUM_PLASTERBOARD_BOTTOM),
        x=BWT, y=HOUSE_DEPTH/2,
    )-UPPER_FINISHED_FLOOR_HEIGHT
print(f"Plasterboard inner-face height at wall, above finished upper floor: {plasterboard_height_at_wall:.3f} m")
print(
    "Horizontal plasterboard inner-face height above finished upper floor: "
    f"{FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z-UPPER_FINISHED_FLOOR_HEIGHT:.3f} m"
)
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


def add_perimeter_insulation(drawing):
    """Draw pink XPS around the basement, down to the footing tops in sections."""
    exterior = (wall_front_g, wall_west_g, wall_back_g, wall_east_g)
    extra = (BASEMENT_WALL_THICKNESS-BWT)/2
    for wall in basement_walls:
        if wall.source_wall not in exterior:
            continue
        if drawing.view == "elevation":
            dx, dy = wall.end[0]-wall.start[0], wall.end[1]-wall.start[1]
            if abs((dx*drawing.direction[0]+dy*drawing.direction[1])/wall.length) < 1-1e-9:
                continue
            endpoints = dict(start_z=PERIMETER_BOTTOM_Z, end_z=PERIMETER_TOP_HEIGHT)
        elif math.isclose(wall.start[1], wall.end[1], abs_tol=1e-9):
            extension = extra+EXTERIOR_XPS_INSULATION_THICKNESS
            endpoints = dict(start_x=-extension, end_x=HOUSE_WIDTH+extension)
        else:
            endpoints = dict(start_y=-extra, end_y=HOUSE_DEPTH+extra)
        drawing.add_wall_insulation(
            wall, thickness=EXTERIOR_XPS_INSULATION_THICKNESS, material="xps", **endpoints,
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
        def panel_options(host, reference_wall, insulation_thickness):
            # Front/back panels cover side-panel ends. The thicker basement
            # masonry projects slightly beyond the ground-floor wall faces.
            extra = (BASEMENT_WALL_THICKNESS-BWT)/2 if reference_wall == basement_wall else 0
            extension = insulation_thickness+extra+(FACADE_THICKNESS if axis == 0 else 0)
            low, high = -extension, (HOUSE_WIDTH if axis == 0 else HOUSE_DEPTH)+extension
            first, last = (low, high) if tangent[axis] > 0 else (high, low)
            reference_face = np.asarray(reference_wall.start)+normal*reference_wall.body_offset
            host_face = np.asarray(host.start)+normal*host.body_offset
            offset = insulation_thickness+float((reference_face-host_face)@(-normal))
            return dict(
                offset=offset, thickness=FACADE_THICKNESS, side="right",
                start_extension=float((host.start[axis]-first)*tangent[axis]),
                end_extension=float((last-host.end[axis])*tangent[axis]),
            )

        basement_wall = next(w for w in basement_walls if w.source_wall == ground_wall)
        perimeter.append(house.add_facade_layer(
            basement_wall, name=f"{side} facade - grey perimeter",
            material="Perimeter facade finish", color="#d9d9d9",
            start_height=PERIMETER_BOTTOM_Z-basement.elevation,
            height=PERIMETER_TOP_HEIGHT-PERIMETER_BOTTOM_Z,
            cuts=(), **panel_options(basement_wall, basement_wall, EXTERIOR_XPS_INSULATION_THICKNESS),
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
            **panel_options(ground_wall, ground_wall, FACADE_INSULATION_THICKNESS),
        ))
    return tuple(perimeter), tuple(white)


def add_roof_edge_facades():
    """Timber siding and red trim along the sloped roof ends, plus eave boards."""
    if ROOF_EAVE_SETBACK <= 0:
        return ()
    boards = []

    def add_sloped_board(name, plane, lo, hi, edge_y, normal_y,
                         bottom_offset, top_offset, thickness, material, color):
        bottom = offset_plane(*plane.points, offset=bottom_offset)
        top = offset_plane(*plane.points, offset=top_offset)
        profile = Polygon((
            (lo, plane_height_at(*bottom, x=lo, y=edge_y)),
            (hi, plane_height_at(*bottom, x=hi, y=edge_y)),
            (hi, plane_height_at(*top, x=hi, y=edge_y)),
            (lo, plane_height_at(*top, x=lo, y=edge_y)),
        ))
        profile = profile.intersection(box(lo, ROOF_EAVE_CUT_Z, hi, profile.bounds[3]+1))
        if profile.is_empty or profile.geom_type != "Polygon":
            raise ValueError(f"{name} has no continuous profile")
        outline = [(float(x), edge_y, float(z)) for x, z in list(profile.exterior.coords)[:-1]]
        vertices = np.asarray(outline)
        area_normal = np.sum(np.cross(vertices, np.roll(vertices, -1, axis=0)), axis=0)
        if area_normal[1]*normal_y < 0:
            outline.reverse()
        board = house.add_panel(
            name, outline=outline, thickness=thickness, material=material, color=color,
        )
        board.ObjectType = "ROOF_EDGE_CLADDING"
        boards.append(board)

    for side, edge_y, normal_y in (
        ("Street", -ROOF_GABLE_OVERHANG, 1),
        ("Garden", HOUSE_DEPTH+ROOF_GABLE_OVERHANG, -1),
    ):
        for slope, plane, lo, hi in (
            ("east", roof_east, east_eave_x, roof_ridge_x),
            ("west", roof_west, roof_ridge_x, west_eave_x),
        ):
            board_width = (ROOF_TILE_BOTTOM-GYPSUM_PLASTERBOARD_BOTTOM)/ROOF_SLOPED_SIDING_BOARD_COUNT
            for index in range(ROOF_SLOPED_SIDING_BOARD_COUNT):
                # Equal widths perpendicular to the slope; each board runs eave to ridge.
                bottom_offset = GYPSUM_PLASTERBOARD_BOTTOM+index*board_width
                add_sloped_board(
                    f"{side} {slope} roof-edge siding {index+1}", plane, lo, hi, edge_y, normal_y,
                    bottom_offset, bottom_offset+board_width,
                    ROOF_EAVE_SETBACK, "Wood siding solid", ROOF_WOOD_SIDING_COLOR,
                )
            add_sloped_board(
                f"{side} {slope} red roof-edge trim", plane, lo, hi, edge_y, -normal_y,
                TILE_BATTEN_BOTTOM, ROOF_TILE_BOTTOM+ROOF_TILE_THICKNESS,
                ROOF_EDGE_TRIM_THICKNESS, "Roof edge trim", ROOF_TILE_COLOR,
            )
    y0, y1 = -ROOF_GABLE_OVERHANG+ROOF_EAVE_SETBACK, HOUSE_DEPTH+ROOF_GABLE_OVERHANG-ROOF_EAVE_SETBACK
    for side, plane, x0, x1 in (
        ("East", roof_east, east_eave_x, east_eave_x+ROOF_EAVE_SETBACK),
        ("West", roof_west, west_eave_x-ROOF_EAVE_SETBACK, west_eave_x),
    ):
        bottom = offset_plane(*plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM)
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
            material="Wood siding solid", color=ROOF_WOOD_SIDING_COLOR,
            cuts=(bottom, top, horizontal_eave_cut), retained_point=(xmid, ymid, (zbottom+ztop)/2),
        )
        board.ObjectType = "ROOF_EDGE_CLADDING"
        boards.append(board)
    return tuple(boards)


def add_roof_gutters(*, gutter_diameter=GUTTER_DIAMETER, color=GUTTER_COLOR):
    """Follow the actual clipped tile edges, with no downpipes or outlets."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    gutters = []
    for side, plane, outward in (("East", roof_east, -1), ("West", roof_west, 1)):
        tiles = next(layer for layer in roof_layers
                     if layer.material_name == "Roof tiles" and layer.plane is plane)
        shape = ifcopenshell.geom.create_shape(settings, tiles)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        tile_edge_x = vertices[:, 0].min() if outward < 0 else vertices[:, 0].max()
        edge = vertices[np.isclose(vertices[:, 0], tile_edge_x, rtol=0, atol=1e-7)]
        x = tile_edge_x+outward*(gutter_diameter/2+GUTTER_EDGE_GAP)
        rim_z = edge[:, 2].min()-GUTTER_DROP_BELOW_TILES
        gutters.append(rainwater_storey.gutter(
            f"{side} roof gutter",
            start=(x, vertices[:, 1].min(), rim_z),
            end=(x, vertices[:, 1].max(), rim_z),
            diameter=gutter_diameter, wall_thickness=GUTTER_WALL_THICKNESS, color=color,
        ))
    return tuple(gutters)


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

rainwater_storey = house.storey("Rainwater drainage", elevation=0)
rainwater_storey.element.Description = "Roof gutters without downpipes"
roof_gutters = add_roof_gutters()


house.write("house2.ifc")

if "basement" in sys.argv:
    drawing1 = house.add_drawing(
        "basement", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        # Keep the landing in projection when the flight's riser count changes.
        z=BASEMENT_FLOOR_START+basement_lower_stairs.end_height+0.1,
        radius=6.5, storeys=[basement], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("ztracene-bedneni", f"Ztracené bednění {BASEMENT_WALL_THICKNESS*1000:.0f} mm"),
        ("perimeter-polystyrene", f"Perimetrická izolace {EXTERIOR_XPS_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_perimeter_insulation(drawing1)
    drawing1.add_notes([
        "Strop nad suterénem: samostatná nosná podpora čela stropu chodby zatím nenavržena.",
    ])
    for room in basement_rooms:
        region = room["region"]
        x0, y0, x1, y1 = region.bounds
        position = region.representative_point().coords[0]
        # Keep the centre room's symbol clear of the AA section line.
        if abs(position[0]-aa_cut.center[0]) < 0.4:
            position = (min(x1-0.45, position[0]+0.45), position[1])
        if room["name"] == "Schody":
            position = ((x0+x1)/2, (basement_upper_end_y+y1)/2-0.5)
        if room["identifier"] == "S.04":
            position = (position[0], position[1]-0.45)
        drawing1.add_room_annotation(
            position, identifier=room["identifier"], description=room["name"], area=region.area,
        )
        inset = min(0.7, (x1-x0)/3, (y1-y0)/3)
        width_y = y1-inset if room["identifier"] in ("S.02", "S.05") else y0+inset
        depth_x = x1+0.45 if room["name"] == "Schody" else x0+inset
        drawing1.add_dimension(
            start=(x0, width_y), end=(x1, width_y),
            name=f"{room['identifier']} clear width",
        )
        drawing1.add_dimension(
            start=(depth_x, y0), end=(depth_x, y1),
            name=f"{room['identifier']} clear depth",
        )
    drawing1.add_room_legend()
    for opening, offset in (
        (basement_garage_door, 1.15),
        (basement_stairway_opening, 0.7),
        (basement_garden_opening, 1.0),
        (basement_storage_opening, 0.7),
        (garage_front_opening, +0.40),
    ):
        drawing1.add_opening_dimension(
            opening, offset=offset, finished_floor_height=BASEMENT_FLOOR_THICKNESS,
        )
    drawing1.add_lintel(basement_garage_door, 1, direction="in")
    drawing1.add_lintel(basement_stairway_opening, 1, direction="in")
    drawing1.add_lintel(basement_garden_opening, 1, direction="in")
    drawing1.add_lintel(basement_storage_opening, 1, position="after", direction="in")
    drawing1.add_lintel(garage_front_opening, 2)
    drawing1.add_lintel_legend()
    drawing1.add_stair_annotation(basement_lower_stairs)
    drawing1.add_stair_annotation(basement_upper_stairs)
    drawing1.add_stair_landing_annotation(basement_stair_landing)
    drawing1.add_poly_line(
        basement_stair_walking_route, arrow_end=True, circle_start=True,
    )
    drawing1.add_notes(basement_stairway_notes, title="SCHODIŠTĚ SUTERÉN–1.NP")
    drawing1.add_dimension(
        start=tuple(float(v) for v in basement_plan_min),
        end=(float(basement_plan_max[0]), float(basement_plan_min[1])), offset=-1.2,
    )
    drawing1.add_dimension(
        start=tuple(float(v) for v in basement_plan_min),
        end=(float(basement_plan_min[0]), float(basement_plan_max[1])), offset=.7,
    )
    drawing1.add_dimension(
        start=(float(basement_plan_max[0])+.6, float(basement_plan_min[1])),
        end=(float(basement_plan_max[0])+.6, float(basement_plan_min[1])+BASEMENT_WALL_THICKNESS),
    )
    if SHOW_CHIMNEY_PLANNING_MARKER:
        drawing1.add_chimney_annotation(chimney, projected=True)
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
        ("drywall-diagonal1", f"Příčka - SDK {DRY_WALL_WIDTH*1000:g} mm"),
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1)
    for room in ground_room_floors:
        match room:
            case (room, offset_x, offset_y):
                pass
            case _:
                offset_x = 0.0
                offset_y = 0.0
        position = Polygon(room.outline).representative_point().coords[0]
        position = (position[0] + offset_x, position[1] + offset_y)
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*ground_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
    # Only openings in load-bearing masonry need lintel tags. The Pokoj 3
    # and bathroom doors are in drywall partitions and are omitted.
    drawing1.add_lintel(entrance_door, 1)
    drawing1.add_lintel(pokoj1_door, 2, direction="in")
    drawing1.add_lintel(pokoj2_door, 2, position="after", direction="in")
    drawing1.add_lintel(bathroom_left_opening, 3, direction="in")
    drawing1.add_lintel(stairway_opening, 3)
    drawing1.add_lintel(window_pokoj1, 4)
    drawing1.add_lintel(window_pokoj2, 4, position="after")
    drawing1.add_lintel(window_pokoj3, 4)
    drawing1.add_lintel(window_koupelna, 5, position="after")
    drawing1.add_lintel_legend()
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
    drawing1.add_notes(stairway_notes+entrance_stairway_notes, title="SCHODIŠTĚ")
    drawing1.add_stair_annotation(entrance_stairs)
    drawing1.add_stair_landing_annotation(entrance_landing)
    drawing1.add_poly_line(
        (entrance_stairs.start, entrance_stairs.end), arrow_end=True, circle_start=True,
        name="Entrance stair walking route",
    )
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
        start=(BWT, THIRD_ROOM_STEP_Y+0.1),
        end=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y+0.1),
    )
    drawing1.add_dimension(
        start=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y),
        end=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, GARDEN_ROOMS_WALL_Y),
		offset=1.05
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
        start=(BATHROOM_LEFT_X+1.7, GARDEN_ROOMS_WALL_Y),
        end=(BATHROOM_LEFT_X+1.7, BATHROOM_PARTITION_Y+DRY_WALL_WIDTH),
        name="Hallway clear depth",
    )
    drawing1.add_dimension(
        start=(BATHROOM_LEFT_X, BWT+0.5),
        end=(BATHROOM_RIGHT_X, BWT+0.5),
        name="Bathroom clear width",
    )

    if SHOW_CHIMNEY_PLANNING_MARKER:
        drawing1.add_chimney_annotation(chimney, projected=True)
    if SHOW_PURLIN_SUPPORT_PLANNING_MARKERS:
        add_purlin_support_planning_markers(drawing1)
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
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
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
        (THIRD_ROOM_WALL_X, HALLWAY_CEILING_SUPPORT_Y),
        (HOUSE_WIDTH-BWT, HALLWAY_CEILING_SUPPORT_Y),
        style="dashed", color="#0080c0", name="Assumed hallway ceiling support",
    )
    drawing1.add_notes([
        f"Uložení nosníků min. {CEILING_BEAM_BEARING*1000:.0f} mm na obou koncích; délky po 250 mm.",
        f"Tolerance celkové šířky skladby ±{CEILING_LAYOUT_TOLERANCE*1000:.0f} mm; úzké vložky uprostřed.",
        "Modrá čárkovaná čára: nutná samostatná nosná podpora stropu chodby nad SDK příčkou a schodištěm; zatím nenavržena.",
        "Styk nosníků koupelny a pokoje 3 zatím není řešen.",
        "Styk protilehlých nosníků chodby a pokojů 1 a 2 na společné stěně zatím není řešen.",
    ])
    if SHOW_CHIMNEY_PLANNING_MARKER:
        drawing1.add_chimney_annotation(chimney, projected=True)
    if SHOW_PURLIN_SUPPORT_PLANNING_MARKERS:
        add_purlin_support_planning_markers(drawing1)
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "ceiling.svg", pdf=PDF_CEILING)

if "upper" in sys.argv:
    drawing1 = house.add_drawing(
        "upper",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=UPPER_FLOOR_START+1.2,
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
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1, upper_exterior_walls)
    # These continuous coverings are hosted downstairs but span both floors.
    for facade in wall_facades:
        drawing1.include_element(facade)
    drawing1.add_chimney_annotation(chimney)
    drawing1.add_dimension(
        start=(CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]),
        end=(upper_technical_right_x, CHIMNEY_CENTER[1]),
        name="Chimney clearance to stairway partition",
    )
    drawing1.add_dimension(
        start=(upper_technical_left_x, STAIR_UPPER_END_Y),
        end=(upper_technical_right_x, STAIR_UPPER_END_Y),
        offset=0.2,
        name="Toilet clear width between vertical walls",
    )
    technical_purlin_index = max(range(len(PURLIN_X_POSITIONS)), key=lambda i: PURLIN_X_POSITIONS[i])
    technical_post_x = PURLIN_X_POSITIONS[technical_purlin_index]
    technical_post_y = min(PURLIN_SUPPORT_Y_POSITIONS[technical_purlin_index])
    drawing1.add_dimension(
        start=(upper_technical_left_x, technical_post_y),
        end=(technical_post_x-PURLIN_SUPPORT_SIZE[0]/2, technical_post_y),
        offset=-0.5,
        name="Front west purlin post clearance to living room wall",
    )
    drawing1.add_dimension(
        start=(technical_post_x+PURLIN_SUPPORT_SIZE[0]/2, technical_post_y),
        end=(upper_technical_right_x, technical_post_y),
        offset=-0.5,
        name="Front west purlin post clearance to stairway wall",
    )
    hallway_dimension_x = upper_stairs.end[0]+ROOM_DOOR_OPENING_WIDTH/2+0.1
    drawing1.add_dimension(
        start=(hallway_dimension_x, upper_stairs.end[1]),
        end=(hallway_dimension_x, living_room_right_wall_front_y),
        name="Living room wall clearance from stairs",
    )
    for room in upper_room_floors:
        position = Polygon(room.outline).representative_point().coords[0]
        if room == upper_hallway:
            position = (STAIR_LEFT_X+0.4,
                        (technical_sliding_door_y+TECHNIKA_SLIDING_DOOR_OPENING_WIDTH
                         +LIVING_ROOM_WALL_FRONT_Y)/2)
        elif room == upper_technical_room:
            position = (upper_technical_center_x,
                        (upper_recuperation_center[1]+0.25+upper_hydrobox_center[1]-0.5/2)/2)
        elif room == upper_toilet_room:
            position = ((upper_technical_left_x+upper_technical_right_x)/2,
                        (upper_toilet_center[1]+0.53/2+CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2)/2)
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*upper_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
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
    drawing1.include_element(lower_stair_railing)
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
    east_support_ys = sorted(PURLIN_SUPPORT_Y_POSITIONS[east_purlin_index])
    east_front_y = east_support_ys[0]
    support_dimension_ys = [BWT, *east_support_ys, HOUSE_DEPTH-BWT]
    for index, (start_y, end_y) in enumerate(zip(support_dimension_ys, support_dimension_ys[1:])):
        if index == 0:
            label = "Front wall to east purlin support centre"
        elif index == len(east_support_ys):
            label = "East purlin support centre to back wall"
        else:
            label = f"East purlin support centre spacing {index}"
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
    wall_back_face_y = living_room_right_wall_front_y+DRY_WALL_WIDTH
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
                    *roof_rafters, *collar_ties, *roof_gutters):
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


def add_bb_roof_batting(drawing):
    """Draw the two roof-insulation layers in the section plane."""
    clearance = 0.01
    purlin_overlap = 0.10  # Batting overlap above the purlin bottom, in metres.
    for index, side, plane in ((0, "East", roof_east), (1, "West", roof_west)):
        inward = 1 if index == 0 else -1

        def point(x, offset):
            return (x, drawing.y, plane_height_at(
                *offset_plane(*plane.points, offset=offset), x=x, y=drawing.y,
            ))

        # The first layer occupies the full rafter depth, up to the ridge.
        offset = RAFTER_Z_OFFSET+RAFTER_HEIGHT/2
        half_x = abs(plane.z_axis[0])*RAFTER_HEIGHT/2
        wall_plate_x = BWT/2 if index == 0 else HOUSE_WIDTH-BWT/2
        drawing.add_batting(
            point(wall_plate_x+inward*clearance, offset),
            point(roof_ridge_x-inward*(half_x+clearance), offset),
            thickness=RAFTER_HEIGHT, name=f"BB {side} between-rafter insulation",
            classes="roof-batting roof-batting-overlay",
        )

        # The second sloped layer follows the actual under-rafter space,
        # ending slightly above the purlin bottom for a fuller batting symbol.
        thickness = THERMAL_INSULATION_UNDER_RAFTERS
        offset = THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM+thickness/2
        half_x = abs(plane.z_axis[0])*thickness/2
        half_z = plane.z_axis[2]*thickness/2
        wall_x = BWT if index == 0 else HOUSE_WIDTH-BWT
        purlin_inner_x = PURLIN_X_POSITIONS[index]+inward*PURLIN_SIZE[0]/2
        start = point(wall_x+inward*(half_x+clearance), offset)
        end = point(purlin_inner_x-inward*(half_x+clearance), offset)
        end_z_limit = purlin_bottom_z-half_z+purlin_overlap
        if end[2] > end_z_limit:
            fraction = (end_z_limit-start[2])/(end[2]-start[2])
            end = point(start[0]+fraction*(end[0]-start[0]), offset)
        drawing.add_batting(
            start, end, thickness=thickness,
            name=f"BB {side} under-rafter insulation", classes="roof-batting roof-batting-overlay",
        )

    center_z = FLAT_VAPOUR_BARRIER_TOP_Z+THERMAL_INSULATION_UNDER_RAFTERS/2
    drawing.add_batting(
        (PURLIN_X_POSITIONS[0]+PURLIN_SIZE[0]/2+clearance, drawing.y, center_z),
        (PURLIN_X_POSITIONS[1]-PURLIN_SIZE[0]/2-clearance, drawing.y, center_z),
        thickness=THERMAL_INSULATION_UNDER_RAFTERS,
        name="BB horizontal ceiling insulation", classes="roof-batting roof-batting-overlay",
    )


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
    for wall, upper_wall in zip(
        (wall_front_g, wall_west_g, wall_back_g, wall_east_g), upper_exterior_walls,
    ):
        dx, dy = wall.end[0]-wall.start[0], wall.end[1]-wall.start[1]
        if abs((dx*view_x+dy*view_y)/wall.length) < 1-1e-9:
            continue
        if upper_wall in (wall_east_u, wall_west_u):
            insulation_top = wall_plate_top_z
        else:
            fraction = -((wall.start[0]-cut.center[0])*view_x
                         +(wall.start[1]-cut.center[1])*view_y)/(dx*view_x+dy*view_y)
            section_x = wall.start[0]+fraction*dx
            roof_plane = roof_east if section_x <= roof_ridge_x else roof_west
            roof_bottom_z = plane_height_at(
                *offset_plane(*roof_plane.points, offset=RAFTER_Z_OFFSET),
                x=section_x, y=cut.center[1],
            )
            insulation_top = min(upper_wall.storey.elevation+upper_wall.end_height, roof_bottom_z)
        drawing.add_wall_insulation(
            wall, thickness=FACADE_INSULATION_THICKNESS, material="rockwool",
            start_z=PERIMETER_TOP_HEIGHT, end_z=insulation_top, opening_walls=(upper_wall,),
        )
    add_perimeter_insulation(drawing)
    if name == "bb":
        add_bb_roof_batting(drawing)
        drawing.add_dimension(
            start=(roof_ridge_x, UPPER_FINISHED_FLOOR_HEIGHT),
            end=(roof_ridge_x, FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z),
            name="Upper finished floor to horizontal plasterboard underside",
        )
        for x, y, offset, label in (
            (*stair_arrival_west_corner, .3, "Lowest ceiling clearance at west edge of upper stair exit"),
            (BWT, HOUSE_DEPTH/2, -.4, "Lowest ceiling clearance at east wall"),
        ):
            ceiling_z = min(
                FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z,
                *(plane_height_at(*offset_plane(*plane.points, offset=GYPSUM_PLASTERBOARD_BOTTOM), x=x, y=y)
                  for plane in (roof_east, roof_west)),
            )
            drawing.add_dimension(
                start=(x, UPPER_FINISHED_FLOOR_HEIGHT), end=(x, ceiling_z),
                offset=offset, name=label,
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
        ("perimeter-polystyrene", "Perimetrická izolace XPS"),
        ("mdf-solid", "MDF záklop"),
        ("vapour-barrier-solid", "OSB záklop + parobrzda"),
    ])
    drawing.render(PROJECT_DIR / f"{name}.svg", pdf=pdf)
    return drawing


for name, cut, pdf in (("aa", aa_cut, PDF_AA), ("bb", bb_cut, PDF_BB)):
    if name in sys.argv:
        add_house_section(cut, name, pdf)


def terrain_edge_profile(length, start_elevation, end_elevation):
    """Slope between two house corners, with flat terrain beyond each end."""
    return (
        (-2.0, start_elevation), (0.0, start_elevation),
        (length, end_elevation), (length+2.0, end_elevation),
    )


# Profile coordinates: global Y for west/east, global X for street/garden.
# The camera handles each edge's orientation on the page. Adjacent profiles
# share their corner elevation, defined only by the four constants above.
TERRAIN_PROFILES = {
    "pohled_zapad": terrain_edge_profile(
        HOUSE_DEPTH, TERRAIN_STREET_WEST_ELEVATION, TERRAIN_GARDEN_WEST_ELEVATION,
    ),
    "pohled_ulice": terrain_edge_profile(
        HOUSE_WIDTH, TERRAIN_STREET_EAST_ELEVATION, TERRAIN_STREET_WEST_ELEVATION,
    ),
    "pohled_zahrada": terrain_edge_profile(
        HOUSE_WIDTH, TERRAIN_GARDEN_EAST_ELEVATION, TERRAIN_GARDEN_WEST_ELEVATION,
    ),
    "pohled_vychod": terrain_edge_profile(
        HOUSE_DEPTH, TERRAIN_STREET_EAST_ELEVATION, TERRAIN_GARDEN_EAST_ELEVATION,
    ),
}


def add_exterior_view(name, camera, direction):
    """Create a complete elevation for the shared exterior-view sheet."""
    view_top = max(roof_tiles_top_z, upper.elevation+chimney.end_height)
    terrain_profile = list(TERRAIN_PROFILES[name])
    radius = 6.5
    if name == "pohled_zapad":
        stone_wall_y0 = HOUSE_DEPTH+WEST_STONE_WALL_DISTANCE
        stone_wall_y1 = stone_wall_y0+WEST_STONE_WALL_WIDTH
        # Flat garden terrain to the far wall face, then a vertical rise and
        # the uphill ground behind the wall. Repeated Y marks the vertical face.
        uphill_end_y = stone_wall_y1+WEST_STONE_WALL_TERRAIN_LENGTH
        uphill_end_elevation = WEST_STONE_WALL_TOP_ELEVATION+math.tan(
            math.radians(WEST_STONE_WALL_TERRAIN_SLOPE_DEGREES)
        )*WEST_STONE_WALL_TERRAIN_LENGTH
        terrain_profile[-1:] = [
            (stone_wall_y1, TERRAIN_GARDEN_WEST_ELEVATION),
            (stone_wall_y1, WEST_STONE_WALL_TOP_ELEVATION),
            (uphill_end_y, uphill_end_elevation),
        ]
        y_min, y_max = terrain_profile[0][0], terrain_profile[-1][0]
        camera = (camera[0], (y_min+y_max)/2)
        radius = max(radius, (y_max-y_min)/2)
        view_top = max(view_top, earth_to_z(uphill_end_elevation))
    elif name == "pohled_zahrada":
        # East is X<0, on the right of this view. Read the raised terrain
        # from east to west so the vertical step retains the profile order.
        wall_east_x = -STONE_WALL_SIDE_OVERHANG
        uphill_end_x = wall_east_x-EAST_STONE_WALL_TERRAIN_LENGTH
        uphill_end_elevation = WEST_STONE_WALL_TOP_ELEVATION+math.tan(
            math.radians(EAST_STONE_WALL_TERRAIN_SLOPE_DEGREES)
        )*EAST_STONE_WALL_TERRAIN_LENGTH
        terrain_profile[:1] = [
            (uphill_end_x, uphill_end_elevation),
            (wall_east_x, WEST_STONE_WALL_TOP_ELEVATION),
            (wall_east_x, TERRAIN_GARDEN_EAST_ELEVATION),
        ]
        x_min, x_max = terrain_profile[0][0], terrain_profile[-1][0]
        radius = max(radius, (x_max-x_min)/2)
        view_top = max(view_top, earth_to_z(uphill_end_elevation))
        # Look toward the house from beyond the retaining wall.
        camera = ((x_min+x_max)/2, HOUSE_DEPTH+WEST_STONE_WALL_DISTANCE+WEST_STONE_WALL_WIDTH+1)
    elif name == "pohled_ulice":
        # The east wall is left of the house in the street elevation.
        street_wall_x1 = -STREET_STONE_WALL_DISTANCE
        street_wall_x0 = street_wall_x1-STREET_STONE_WALL_WIDTH
        uphill_end_x = street_wall_x0-STREET_STONE_WALL_TERRAIN_LENGTH
        uphill_end_elevation = STREET_STONE_WALL_TOP_ELEVATION+math.tan(
            math.radians(STREET_STONE_WALL_TERRAIN_SLOPE_DEGREES)
        )*STREET_STONE_WALL_TERRAIN_LENGTH
        garage_x0 = float(ifcopenshell.util.placement.get_local_placement(
            garage_front_door.ObjectPlacement,
        )[0, 3])
        garage_x1 = garage_x0+garage_front_door.OverallWidth
        garage_floor_elevation = GROUND_FINISHED_FLOOR_ELEVATION-BASEMENT_TO_GROUND_RISE

        def street_earth_at(x):
            return TERRAIN_STREET_EAST_ELEVATION+(x/HOUSE_WIDTH)*(
                TERRAIN_STREET_WEST_ELEVATION-TERRAIN_STREET_EAST_ELEVATION
            )

        terrain_profile = [
            (uphill_end_x, uphill_end_elevation),
            (street_wall_x0, STREET_STONE_WALL_TOP_ELEVATION),
            (street_wall_x0, TERRAIN_STREET_EAST_ELEVATION),
            (0.0, TERRAIN_STREET_EAST_ELEVATION),
            (garage_x0, street_earth_at(garage_x0)),
            (garage_x0, garage_floor_elevation),
            (garage_x1, garage_floor_elevation),
            (garage_x1, street_earth_at(garage_x1)),
            (HOUSE_WIDTH, TERRAIN_STREET_WEST_ELEVATION),
            (HOUSE_WIDTH+2.0, TERRAIN_STREET_WEST_ELEVATION),
        ]
        x_min, x_max = terrain_profile[0][0], terrain_profile[-1][0]
        camera = ((x_min+x_max)/2, camera[1])
        radius = max(radius, (x_max-x_min)/2)
        view_top = max(view_top, earth_to_z(uphill_end_elevation))
    elif name == "pohled_vychod":
        # Looking along +X, garden (+Y) is left and street (-Y) is right.
        east_house_left_y = HOUSE_DEPTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS
        east_house_right_y = -FACADE_INSULATION_THICKNESS-FACADE_THICKNESS
        east_wall_left_y = east_house_left_y+EAST_VIEW_STONE_WALL_OVERHANG
        east_wall_right_y = east_house_right_y-EAST_VIEW_STONE_WALL_OVERHANG
        east_wall_bottom_z = FOUNDATION_FOOTING_BOTTOM_Z-.1
        camera = (camera[0], (east_wall_left_y+east_wall_right_y)/2)
        radius = max(radius, (east_wall_left_y-east_wall_right_y)/2+.1)
        view_top = max(view_top, earth_to_z(EAST_VIEW_STONE_WALL_LEFT_ELEVATION),
                       earth_to_z(EAST_VIEW_STONE_WALL_RIGHT_ELEVATION))
    view_bottom = (east_wall_bottom_z if name == "pohled_vychod"
                   else min(earth_to_z(height) for _, height in terrain_profile)-.4)
    drawing = house.add_drawing(
        name, x=camera[0], y=camera[1], z=(view_bottom+view_top)/2,
        radius=max(radius, (view_top-view_bottom)/2+.5), view="elevation", direction=direction,
        storeys=[foundation, basement, basement_ceiling_storey, ground, ceiling_storey, upper, facade_storey, rainwater_storey,
                 *roof_layer_storeys.values()],
        door_annotations=False, automatic_plan_annotations=False,
        doors_closed=True, surface_fills=True,
        scale=POHLEDY_SCALE,
    )
    if name != "pohled_vychod":
        drawing.add_terrain(terrain_profile, earth_to_z=earth_to_z)
    if name == "pohled_zapad":
        garden_facade_y = HOUSE_DEPTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS
        drawing.add_rectangle(
            (garden_facade_y+WEST_BACKGROUND_WALL_HOUSE_GAP, earth_to_z(TERRAIN_GARDEN_WEST_ELEVATION)),
            (stone_wall_y0, earth_to_z(WEST_STONE_WALL_TOP_ELEVATION)),
            pattern="stone-wall-background", color="#d0d0d0", background=True,
            name="West background connecting stone wall",
        )
        drawing.add_rectangle(
            (stone_wall_y0, earth_to_z(TERRAIN_GARDEN_WEST_ELEVATION)),
            (stone_wall_y1, earth_to_z(WEST_STONE_WALL_TOP_ELEVATION)),
            pattern="stone-wall", name="Garden stone wall",
        )
    elif name == "pohled_zahrada":
        drawing.add_rectangle(
            (-STONE_WALL_SIDE_OVERHANG, earth_to_z(TERRAIN_GARDEN_WEST_ELEVATION)),
            (HOUSE_WIDTH+STONE_WALL_SIDE_OVERHANG, earth_to_z(WEST_STONE_WALL_TOP_ELEVATION)),
            pattern="stone-wall", name="Garden stone wall front",
        )
    elif name == "pohled_ulice":
        if SHOW_STREET_BACKGROUND_STONE_WALL:
            background_ground_z = ground.elevation+entrance_stairs.start_height-STREET_BACKGROUND_TERRAIN_BELOW_STAIRS
            east_facade_x = -FACADE_INSULATION_THICKNESS-FACADE_THICKNESS-STREET_BACKGROUND_WALL_HOUSE_GAP
            drawing.add_polygon(
                (
                    (street_wall_x1, background_ground_z),
                    (east_facade_x, background_ground_z),
                    (east_facade_x, earth_to_z(WEST_STONE_WALL_TOP_ELEVATION)),
                    (street_wall_x1, earth_to_z(STREET_STONE_WALL_TOP_ELEVATION)),
                ),
                pattern="stone-wall-background", color="#d0d0d0", background=True,
                name="Street background connecting stone wall",
            )
            west_facade_x = HOUSE_WIDTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS
            drawing.add_rectangle(
                (west_facade_x+STREET_BACKGROUND_WALL_HOUSE_GAP, background_ground_z),
                (west_facade_x+STREET_BACKGROUND_WALL_WEST_EXTENT, earth_to_z(WEST_STONE_WALL_TOP_ELEVATION)),
                pattern="stone-wall-background", color="#d0d0d0", background=True,
                name="Street background west stone wall",
            )
            for x0, x1 in (
                (street_wall_x1, east_facade_x),
                (west_facade_x+STREET_BACKGROUND_WALL_HOUSE_GAP,
                 west_facade_x+STREET_BACKGROUND_WALL_WEST_EXTENT),
            ):
                drawing.add_terrain(
                    ((x0, background_ground_z), (x1, background_ground_z)),
                    background=True, opacity=0.2, line_width=0.2,
                )
        drawing.add_rectangle(
            (street_wall_x0, earth_to_z(TERRAIN_STREET_EAST_ELEVATION)),
            (street_wall_x1, earth_to_z(STREET_STONE_WALL_TOP_ELEVATION)),
            pattern="stone-wall", name="Street east stone wall",
        )
        for side, x0, x1 in (
            ("east", garage_x0-GARAGE_RETAINING_WALL_WIDTH, garage_x0),
            ("west", garage_x1, garage_x1+GARAGE_RETAINING_WALL_WIDTH),
        ):
            drawing.add_rectangle(
                (x0, earth_to_z(garage_floor_elevation)),
                (x1, earth_to_z(GARAGE_RETAINING_WALL_TOP_ELEVATION)),
                pattern="stone-wall", name=f"Garage retaining wall {side}",
            )
    elif name == "pohled_vychod":
        drawing.add_polygon(
            (
                (east_wall_left_y, earth_to_z(EAST_VIEW_STONE_WALL_LEFT_ELEVATION)),
                (east_house_left_y, earth_to_z(EAST_VIEW_STONE_WALL_LEFT_ELEVATION)),
                (east_wall_right_y, earth_to_z(EAST_VIEW_STONE_WALL_RIGHT_ELEVATION)),
                (east_wall_right_y, east_wall_bottom_z),
                (east_wall_left_y, east_wall_bottom_z),
            ),
            pattern="stone-wall", name="East stone wall",
        )
    return drawing


if "pohledy" in sys.argv:
    pohledy_sheet = DrawingSheet(paper="A3", orientation="landscape")
    for name, title, camera, direction, x, y in (
        ("pohled_zapad", "Pohled - Západ", (west_eave_x+1, HOUSE_DEPTH/2), (-1, 0, 0), .25, .25),
        ("pohled_ulice", "Pohled - Ulice", (HOUSE_WIDTH/2, -ROOF_GABLE_OVERHANG-1), (0, 1, 0), .75, .25),
        ("pohled_zahrada", "Pohled - Zahrada", (HOUSE_WIDTH/2, HOUSE_DEPTH+ROOF_GABLE_OVERHANG+1), (0, -1, 0), .25, .75),
        ("pohled_vychod", "Pohled - Východ", (east_eave_x-1, HOUSE_DEPTH/2), (1, 0, 0), .75, .75),
    ):
        view = add_exterior_view(name, camera, direction)
        pohledy_sheet.add(view, x=x, y=y, title=title, tables=False)
    pohledy_sheet.render(PROJECT_DIR / "pohledy.svg", pdf=PDF_POHLEDY)
