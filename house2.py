"""Alternative house: export with `python3 house2.py`; plans plus `pohledy` for all four exterior views."""

from pathlib import Path
from math import floor
import math
import json
import sys

import ifcopenshell.api.pset
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import nearest_points, unary_union

from ifc_utils import CutDefinition, DrawingSheet, House, offset_plane, plane_height_at, window_area
from materials import resolve_timber_grade
from pdf_utils import PDFFolder


HOUSE_WIDTH = 8.74
HOUSE_DEPTH = 8.99
BWT = 0.24
INNER_BWT = 0.24
GARDEN_PARTITION_THICKNESS = 0.115
DRY_WALL_WIDTH = 0.10
WOODEN_WALL_THICKNESS = 0.06
FACADE_INSULATION_THICKNESS = 0.20
EXTERIOR_XPS_INSULATION_THICKNESS = 0.10
FACADE_THICKNESS = 0.005
GARDEN_ROOMS_DEPTH = 3.375 + 0.01  # Clear depth between the divider and inside garden wall.
GARDEN_ROOMS_WALL_Y = HOUSE_DEPTH-BWT-GARDEN_ROOMS_DEPTH-INNER_BWT
ROOM_DOOR_OPENING_WIDTH = 1.0
GARDEN_DOOR_CENTER_CLEARANCE = 0.25  # Each construction opening stops this far from the centreline.
THIRD_ROOM_DRYWALL_DOOR_CLEARANCE = 0.05  # Hallway face to the near jamb of the Pokoj 1 opening.
THIRD_ROOM_NARROW_WALL_X = (
    HOUSE_WIDTH/2-GARDEN_DOOR_CENTER_CLEARANCE-ROOM_DOOR_OPENING_WIDTH-THIRD_ROOM_DRYWALL_DOOR_CLEARANCE
)
THIRD_ROOM_NARROW_WIDTH = THIRD_ROOM_NARROW_WALL_X-BWT-DRY_WALL_WIDTH
THIRD_ROOM_WIDTH = 3.26  # Clear width of the left street-side room.
THIRD_ROOM_WALL_X = BWT+THIRD_ROOM_WIDTH+INNER_BWT
STAIRWAY_WIDTH = 2.26  # Clear width beside the west exterior wall.
STAIRWAY_WALL_X = HOUSE_WIDTH-BWT-STAIRWAY_WIDTH
BATHROOM_LEFT_X = THIRD_ROOM_WALL_X
BATHROOM_RIGHT_X = STAIRWAY_WALL_X-INNER_BWT
HALLWAY_OPENING_LENGTH = 1.755  # From the garden-room wall towards the street.
STAIRWAY_OPENING_START_Y = GARDEN_ROOMS_WALL_Y-HALLWAY_OPENING_LENGTH
STAIRWAY_OPENING_FRONT_Y = STAIRWAY_OPENING_START_Y
BATHROOM_PARTITION_Y = STAIRWAY_OPENING_FRONT_Y-DRY_WALL_WIDTH
BATHROOM_DEPTH = BATHROOM_PARTITION_Y-BWT
BATHROOM_TOILET_ZONE_DEPTH = 0.90
BATHROOM_BASIN_ZONE_DEPTH = 0.80
BATHROOM_TUV_ZONE_DEPTH = 0.80
BATHROOM_TUV_STAIRWAY_CLEARANCE = 0.10
BATHROOM_HYDROBOX_WALL_GAP = 0.05
HYDROBOX_SIZE = (0.8, 0.5, 0.9)
THIRD_ROOM_OPENING_LENGTH = 1.755  # Room 3 to hallway; independent of the stairway opening.
THIRD_ROOM_OPENING_START_Y = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_OPENING_LENGTH
THIRD_ROOM_STEP_Y = THIRD_ROOM_OPENING_START_Y-DRY_WALL_WIDTH  # Hallway face meets the opening end.
THIRD_ROOM_NARROW_DEPTH = GARDEN_ROOMS_WALL_Y-THIRD_ROOM_STEP_Y
HALLWAY_OPENING_TOP_GAP = 0.25  # Masonry below the underside of the ground-floor ceiling.

UPPER_BATHROOM_WIDTH = 1.0
LIVING_ROOM_WIDTH = HOUSE_WIDTH - 2*BWT - STAIRWAY_WIDTH - 2*DRY_WALL_WIDTH - UPPER_BATHROOM_WIDTH
UPPER_BEARING_WALL_THICKNESS = 0.24
UPPER_BEARING_WALL_RAFTER_TOP_CLEARANCE = 0.05  # Perpendicular to the roof slope.
KITCHEN_UNIT_SIZE = (0.64, 0.64, 0.75)
FRIDGE_SIZE = (0.64, 1.0, 1.95)
DINING_TABLE_SIZE = (1.25, 1.7)  # Complete asset footprint, including chairs.
DINING_TABLE_WALL_GAP = 1.0  # Clear distance from the east wall's inner face.
KITCHEN_WALL_GAP = 0.03  # Same 350 mm centre offset as the old house's 640 mm units.
STOVE_SIZE = (0.60, 0.50, 1.50)
SOFA_SIZE = (2.5, 1.1)
ARMCHAIR_SIZE = (1.1, 1.1)
SEATING_WALL_GAP = 0.10
SEATING_GAP = 0.10
HEAT_PUMP_SIZE = (1.2, 0.5, 1.5)
HEAT_PUMP_GARAGE_GAP = 0.50
HEAT_PUMP_HEIGHT_ABOVE_BASEMENT_FLOOR = 0.60
ROZVADEC_SIZE = (0.7, 0.3, 0.50)  # Width along X, depth, height.
ROZVADEC_BOTTOM_ABOVE_FLOOR = 1.20
ROZVADEC_WALL_GAP = 0.05
FAN_COIL_SIZE = (.90, .23, .30)
FAN_COIL_DOOR_CLEARANCE = .05
FAN_COIL_WINDOW_CLEARANCE = .05
FAN_COIL_WALL_GAP = .01
BATHROOM_FAN_COIL_SIZE = (.80, .12, .60)
BATHROOM_FAN_COIL_DOOR_WALL_GAP = .10

ZAKLADACI_MALTA = 0.02
GROUND_WALL_BASE_COURSE_HEIGHT = ZAKLADACI_MALTA + 0.125
GROUND_WALL_BASE_COURSE_MATERIAL = "Liapor brick"
ground_floor_height = GROUND_WALL_BASE_COURSE_HEIGHT + 2.625
CEMFLOW_AND_FINISH_THICKNESS = 0.07
GROUND_FLOOR_INSULATION_THICKNESS = 0.08
GROUND_FLOOR_THICKNESS = GROUND_FLOOR_INSULATION_THICKNESS+CEMFLOW_AND_FINISH_THICKNESS
PERIMETER_TOP_HEIGHT = 0.0#GROUND_FLOOR_THICKNESS
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
CEILING_PLASTER_THICKNESS = 0.015  # Allowance below the slab for clear-height dimensions.
BASEMENT_CEILING_INSULATION_THICKNESS = 0.10
BASEMENT_CEILING_WOOD_THICKNESS = 0.02
BASEMENT_CEILING_FINISH_THICKNESS = BASEMENT_CEILING_INSULATION_THICKNESS+BASEMENT_CEILING_WOOD_THICKNESS
# Retain the former bathroom-wall reference for the upper-floor fixtures.
CEILING_ROOM3_SPLIT_Y = BWT+3.0
BASEMENT_WALL_HEIGHT = ZAKLADACI_MALTA + 2.35 # 7*25 + 3*20 = 235cm
BASEMENT_WALL_THICKNESS = 0.30
BASEMENT_SLAB_THICKNESS = 0.15
FOUNDATION_FOOTING_WIDTH = 0.74
FOUNDATION_FOOTING_HEIGHT = 0.50
GROUNDING_LEAD_LENGTH = 1.0  # Length beyond the outside masonry face/corner.
BASEMENT_WALL_TOP_Z = -CEILING_THICKNESS  # Ground-floor layers start at Z = 0.
BASEMENT_FINISHED_CEILING_Z = BASEMENT_WALL_TOP_Z-BASEMENT_CEILING_FINISH_THICKNESS
BASEMENT_FLOOR_START = BASEMENT_WALL_TOP_Z-BASEMENT_WALL_HEIGHT
BASEMENT_FLOOR_THICKNESS = CEMFLOW_AND_FINISH_THICKNESS
BASEMENT_FINISHED_FLOOR_HEIGHT = BASEMENT_FLOOR_START+BASEMENT_FLOOR_THICKNESS
BASEMENT_TO_GROUND_RISE = GROUND_FLOOR_THICKNESS-BASEMENT_FINISHED_FLOOR_HEIGHT
BASEMENT_OPENING_WIDTH = 1.0
BASEMENT_S01_S02_GARDEN_CLEARANCE = 1.25
BASEMENT_S02_S05_WEST_CLEARANCE = 0.50
BASEMENT_S01_S03_EAST_CLEARANCE = 1.25
BASEMENT_S04_S05_FRONT_CLEARANCE = 2.75
BASEMENT_S03_S04_FRONT_CLEARANCE = 1.00
BASEMENT_OPENING_TOP_HEIGHT = BASEMENT_WALL_HEIGHT-0.25
GARAGE_FRONT_OPENING_SIDE_CLEARANCE = 0.50  # From the inner east wall face.
GARAGE_FRONT_OPENING_WIDTH = 2.25
GARAGE_FRONT_OPENING_TOP_HEIGHT = BASEMENT_WALL_HEIGHT-0.20
BASEMENT_SLAB_BOTTOM_Z = BASEMENT_FLOOR_START-BASEMENT_SLAB_THICKNESS
PERIMETER_BOTTOM_Z = BASEMENT_SLAB_BOTTOM_Z  # Top of the foundation footings.
FOUNDATION_FOOTING_BOTTOM_Z = BASEMENT_SLAB_BOTTOM_Z-FOUNDATION_FOOTING_HEIGHT
SECTION_SOIL_EXTENT = 2.0  # Visible ground beyond each exterior basement wall.
SECTION_SOIL_DEPTH = 0.4  # Visible soil below the footings.
SECTION_GRAVEL_BOTTOM_WIDTH = 0.3
SECTION_GRAVEL_SLOPE = 0.5  # Horizontal widening per metre of height; drawing geometry.
CEILING_BEAM_BEARING = 0.125  # Minimum at each end, before rounding the beam length up.
CEILING_BEAM_LENGTH_STEP = 0.25
CEILING_LAYOUT_TOLERANCE = 0.07  # Total width mismatch, not the gap at each side.
CEILING_STRIP_WIDTHS = {"beam": 0.16, "wide": 0.455, "narrow": 0.33, "space": 0.005}
CEILING_BEAM_SPACING_OUTSIDE_OFFSETS = (1.0, 1.5)  # Alternate beyond the exterior wall faces.
BASEMENT_STAIR_OPENING_LENGTH = 3.0  # Clear depth from the inside face of the street wall.
UPPER_FLOOR_THICKNESS = 0.03+CEMFLOW_AND_FINISH_THICKNESS
UPPER_MASONRY_COURSE_HEIGHT = 0.125
UPPER_FLOOR_START = ground_floor_height+CEILING_THICKNESS
UPPER_FINISHED_FLOOR_HEIGHT = UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS
UPPER_RING_BEAM_HEIGHT = 0.24
NADEZDIVKA = ZAKLADACI_MALTA + 1.20 + UPPER_RING_BEAM_HEIGHT
WALL_PLATE_SIZE = (0.16, 0.12)
WALL_PLATE_OVERHANG = 0.2
WALL_PLATE_Z = UPPER_FLOOR_START+NADEZDIVKA+WALL_PLATE_SIZE[1]/2
PURLIN_SIZE = (0.16, 0.24)
ROOF_TIMBER_MATERIAL = resolve_timber_grade("c22").name
PURLIN_WALL_DISTANCE = 2.95
PURLIN_X_POSITIONS = (
	BWT+PURLIN_WALL_DISTANCE-PURLIN_SIZE[0]/2.0,
	HOUSE_WIDTH-BWT-PURLIN_WALL_DISTANCE+PURLIN_SIZE[0]/2.0
)
PURLIN_CENTER_HEIGHT = 3.75  # Purlin TOP above the upper-floor datum / ceiling top (legacy name).
PURLIN_Z = UPPER_FLOOR_START+PURLIN_CENTER_HEIGHT-PURLIN_SIZE[1]/2
PURLIN_SUPPORT_SIZE = (0.16, 0.16)
PURLIN_SUPPORT_GIRDER_SIZE = (0.21, 0.21)  # Concrete width/height; top flush with ceiling.
PURLIN_SUPPORT_GIRDER_HEB = 180
PURLIN_SUPPORT_GIRDER_BEARING = 0.10
# Centre the remaining posts between the facing masonry surfaces.
PURLIN_BEARING_WALL_Y = GARDEN_ROOMS_WALL_Y+INNER_BWT/2
PURLIN_SUPPORT_STREET_Y = BWT+2.4
PURLIN_SUPPORT_Y_POSITIONS = tuple((PURLIN_SUPPORT_STREET_Y,) for _ in PURLIN_X_POSITIONS)
UPPER_TECHNICAL_CROSS_Y = (
    min(PURLIN_SUPPORT_Y_POSITIONS[-1])+PURLIN_SUPPORT_SIZE[1]/2
    -DRY_WALL_WIDTH/2
)
PURLIN_SADDLE_LENGTH = 1.50
PURLIN_SADDLE_SIZE = PURLIN_SIZE
PURLIN_CONNECTION_GARDEN_Y = BWT+2.52+3  # Retain the transverse connector after removing its old posts.
PURLIN_CONNECTION_BEAM_SIZE = (0.16, 0.16)  # Width along Y, height along Z.
PURLIN_CONNECTION_WALL_CLEARANCE = 0.10  # Clear gap from each gable wall's inner face.
PURLIN_CONNECTION_Y_POSITIONS = (
    *sorted({y for positions in PURLIN_SUPPORT_Y_POSITIONS for y in positions}),
    PURLIN_CONNECTION_GARDEN_Y,
    BWT+PURLIN_CONNECTION_WALL_CLEARANCE+PURLIN_CONNECTION_BEAM_SIZE[0]/2,
    HOUSE_DEPTH-BWT-PURLIN_CONNECTION_WALL_CLEARANCE-PURLIN_CONNECTION_BEAM_SIZE[0]/2,
)
# Legacy simulator comparison settings; the IFC model has sedla, no diagonal braces.
PURLIN_BRACE_SIZE = (0.12, 0.12)
PURLIN_BRACE_DROP = 0.80  # Brace anchor below the post top; braces rise at 45 degrees.
PURLIN_CONNECTION_BRACE_DROP = 0.60  # Anchor drop below the connector underside.
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
CHIMNEY_BASEMENT_WALL_CLEARANCE = 0.125
CHIMNEY_FOOTING_OVERHANG = 0.20
CHIMNEY_FLUE_DIAMETER = 0.20
CHIMNEY_ABOVE_ROOF = 1.25
SHOW_PURLIN_SUPPORT_PLANNING_MARKERS = True  # Ground-floor post footprints and stove; ceiling plans always show posts.
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
BASEMENT_STAIR_FLIGHT_GAP = 0.24  # Reserved future basement layout.
BASEMENT_STAIR_LOWER_RUN_LENGTH = (BASEMENT_STAIR_LOWER_RISERS-1)*STAIR_TREAD_LENGTH
BASEMENT_STAIR_UPPER_RUN_LENGTH = (BASEMENT_STAIR_UPPER_RISERS-1)*STAIR_TREAD_LENGTH
BASEMENT_STAIR_RISER_HEIGHT = BASEMENT_TO_GROUND_RISE/(BASEMENT_STAIR_LOWER_RISERS+BASEMENT_STAIR_UPPER_RISERS)
STAIR_LEFT_X = STAIRWAY_WALL_X
STAIR_RIGHT_X = HOUSE_WIDTH-BWT
STAIR_FLIGHT_GAP = STAIR_RIGHT_X-STAIR_LEFT_X-2*STAIR_FLIGHT_WIDTH
STAIR_UPPER_CENTER_X = STAIR_LEFT_X+STAIR_FLIGHT_WIDTH/2
STAIR_LOWER_CENTER_X = STAIR_RIGHT_X-STAIR_FLIGHT_WIDTH/2
STAIR_LANDING_START_Y = BWT
STAIR_LANDING_END_Y = STAIR_LANDING_START_Y+STAIR_LANDING_LENGTH
STAIR_LOWER_START_Y = STAIR_LANDING_END_Y+STAIR_LOWER_RUN_LENGTH
STAIR_UPPER_END_Y = STAIR_LANDING_END_Y+STAIR_UPPER_RUN_LENGTH
# The thicker basement wall is centred beneath the garden-room divider.
BASEMENT_GARDEN_WALL_STREET_Y = (
    GARDEN_ROOMS_WALL_Y+INNER_BWT/2-BASEMENT_WALL_THICKNESS/2
)
CHIMNEY_CENTER = (
    HOUSE_WIDTH/2.0 + 0.05,
    BASEMENT_GARDEN_WALL_STREET_Y-CHIMNEY_SIZE/2-CHIMNEY_BASEMENT_WALL_CLEARANCE,
)
print("CHIMNEY_CENTER =", CHIMNEY_CENTER)
for purlin_index, purlin_x in enumerate(PURLIN_X_POSITIONS, 1):
    purlin_chimney_clearance = abs(purlin_x-CHIMNEY_CENTER[0])-(PURLIN_SIZE[0]+CHIMNEY_SIZE)/2
    # Ignore sub-nanometre roundoff at the exact 100 mm warning boundary.
    warning_prefix = "**** WARNING: " if purlin_chimney_clearance < 0.10-1e-9 else ""
    print(f"{warning_prefix}Purlin {purlin_index} to chimney clearance: {purlin_chimney_clearance*1000:.1f} mm")
STAIR_WAIST_THICKNESS = 0.15
INTERNAL_STAIR_CONSTRUCTION = "timber"
INTERNAL_STAIR_MATERIAL = "Wood" if INTERNAL_STAIR_CONSTRUCTION == "timber" else "Concrete"
INTERNAL_STAIR_COLOR = "#C8B090" if INTERNAL_STAIR_CONSTRUCTION == "timber" else None
STAIR_RAILING_HEIGHT = 1.0
STAIR_RAILING_INSET = 0.03  # Centreline inset onto each flight and the middle landing.
TECHNIKA_RAILING_START_FROM_FRONT = 1.5  # Metres from the front wall's inside face.
if STAIR_FLIGHT_GAP < 0:
    raise ValueError("stair flights do not fit between the stairway wall and the west wall")
if max(STAIR_LOWER_START_Y, STAIR_UPPER_END_Y) > GARDEN_ROOMS_WALL_Y+1e-9:
    raise ValueError("rotated stairs reach the garden-room dividing wall")
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
ENTRANCE_OPENING_WIDTH = 1.125
ENTRANCE_STAIR_RISERS = 7
ENTRANCE_STAIR_TREAD_LENGTH = 0.30
ENTRANCE_STAIR_WIDTH = ENTRANCE_OPENING_WIDTH
ENTRANCE_LANDING_DEPTH = 1.125  # Projection beyond the facade, as in house_ifc.py.
ENTRANCE_LANDING_LENGTH = 2.0  # Along Y, from the door's street edge towards the garden.
ENTRANCE_LANDING_THICKNESS = 0.20
ENTRANCE_DOOR_WIDTH = 0.9
ENTRANCE_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.135
ENTRANCE_CLEAR_HEIGHT = 2.1
ROOM_DOOR_WIDTH = 0.9
ROOM_DOOR_HEIGHT = GROUND_FLOOR_THICKNESS+2.135
ROOM_DOOR_CLEAR_HEIGHT = 2.1
UPPER_DOOR_TOP_HEIGHT = ZAKLADACI_MALTA+18*UPPER_MASONRY_COURSE_HEIGHT
UPPER_DOOR_CLEAR_HEIGHT = 2.1
LIVING_ROOM_DOOR_WEST_CLEARANCE = 0.005 + 1.75  # From the inner west wall face to the construction opening.
LIVING_ROOM_OPENING_EAST_CLEARANCE = 0.005 + 1.75  # From the inner east wall face to the unfilled opening.
LIVING_ROOM_OPENING_WIDTH = 2.75
LIVING_ROOM_OPENING_END_X = BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE+LIVING_ROOM_OPENING_WIDTH
LIVING_ROOM_PARTITION_RETURN_CLEARANCE = 0.70  # Clear distance to the street face of the middle VPC wall.
UPPER_TOILET_DEPTH = 1.15  # Clear depth from the lower cross-wall's toilet face.
UPPER_TOILET_DOOR_WIDTH = 0.7
UPPER_TOILET_DOOR_OPENING_WIDTH = 0.8
UPPER_TOILET_DOOR_SIDE_CLEARANCE = 0.05  # From the vertical living-room wall's toilet face.
THIRD_ROOM_DOOR_GARDEN_CLEARANCE = 0.125  # From the room 1 face to the construction opening.
BATHROOM_DOOR_SIDE_CLEARANCE = 0.125
ENTRANCE_OPENING_AT = 0.01+4.875-1.125  # From the front wall's inside face, along the west wall.
ROOM_WINDOW_WIDTH = 1.50
GARDEN_WINDOW_CENTER_CLEARANCE = 1.0  # House centreline to the nearest opening jamb.
THIRD_ROOM_WINDOW_EAST_CLEARANCE = 1.255  # Inside east wall face to the opening.
GROUND_WINDOW_TOP_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+2.25
GROUND_WINDOW_SILL_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT+0.875
UPPER_WINDOW_WIDTH = 1.5
UPPER_BACK_WINDOW_WIDTH = 1.5
UPPER_BACK_WINDOW_GAP = 1.0
UPPER_FRONT_WINDOW_EAST_CLEARANCE = 2.255
UPPER_WINDOW_SILL_HEIGHT = ZAKLADACI_MALTA+8*UPPER_MASONRY_COURSE_HEIGHT
UPPER_WINDOW_TOP_HEIGHT = ZAKLADACI_MALTA+19*UPPER_MASONRY_COURSE_HEIGHT
UPPER_WINDOW_HEIGHT = UPPER_WINDOW_TOP_HEIGHT-UPPER_WINDOW_SILL_HEIGHT
BATHROOM_WINDOW_WIDTH = 0.75
BATHROOM_WINDOW_HEIGHT = 0.75
BATHROOM_WINDOW_STAIRWAY_CLEARANCE = 0.38  # Inside stairway wall face to the opening jamb.
UPPER_BASIN_SIZE = (0.60, 0.5)
BATHROOM_WINDOW_CENTER_X = BATHROOM_RIGHT_X-BATHROOM_WINDOW_STAIRWAY_CLEARANCE-BATHROOM_WINDOW_WIDTH/2

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
POHLEDY_SCALE = 130
PDF_BASEMENT = Path(PDF_FOLDER.add_pdf("Půdorys suterénu"))
PDF_FOUND = Path(PDF_FOLDER.add_pdf("Základy"))
PDF_AA = Path(PDF_FOLDER.add_pdf("Řez AA"))
PDF_BB = Path(PDF_FOLDER.add_pdf("Řez BB"))
PDF_BASEMENT_CEILING = Path(PDF_FOLDER.add_pdf("Strop nad suterénem"))
PDF_BASEMENT_CEILING2 = Path(PDF_FOLDER.add_pdf("Strop nad suterénem - podrobný plán"))
PDF_CEILING2 = Path(PDF_FOLDER.add_pdf("Strop nad 1.NP - podrobný plán"))
DIR_ZDRAVOTECHNICKE_INSTALACE = PROJECT_DIR / "D1.5. Zdravotechnické Instalace"
PDF_KANAL_FOLDER = PDFFolder("D1.5.", DIR_ZDRAVOTECHNICKE_INSTALACE)
PDF_KANAL_BASEMENT = Path(PDF_KANAL_FOLDER.add_pdf("Kanalizace - Půdorys suterénu"))
PDF_KANAL_GROUND = Path(PDF_KANAL_FOLDER.add_pdf("Kanalizace - Půdorys 1.NP"))
PDF_KANAL_UPPER = Path(PDF_KANAL_FOLDER.add_pdf("Kanalizace - Půdorys podkroví"))
PDF_KANAL = Path(PDF_KANAL_FOLDER.add_pdf("Kanalizace"))
PDF_VODA_GROUND = Path(PDF_KANAL_FOLDER.add_pdf("Vodovod - Půdorys 1.NP"))
PDF_VODA_UPPER = Path(PDF_KANAL_FOLDER.add_pdf("Vodovod - Půdorys podkroví"))
PDF_VODA_BASEMENT = Path(PDF_KANAL_FOLDER.add_pdf("Vodovod - Půdorys suterénu"))
DIR_ELEKTRO = PROJECT_DIR / "D1.4. Zařízení Silnoproudé Elektrotechniky"
PDF_ELEKTRO_FOLDER = PDFFolder("D1.4.", DIR_ELEKTRO)
PDF_ELEKTRO_GROUND = Path(PDF_ELEKTRO_FOLDER.add_pdf("Elektro - Půdorys 1.NP"))
PDF_ELEKTRO_UPPER = Path(PDF_ELEKTRO_FOLDER.add_pdf("Elektro - Půdorys podkroví"))
PDF_ELEKTRO_BASEMENT = Path(PDF_ELEKTRO_FOLDER.add_pdf("Elektro - Půdorys suterénu"))
ELECTRICAL_LINE_WIDTH = 0.30  # Printed millimetres, matching the reference electrical plans.
ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH = 0.30  # Black riser symbols, matching sewer and water drawings.
ELECTRICAL_LIGHT_OFFSETS = {}  # Optional room-specific offsets from the calculated centre.
ELECTRICAL_ROOM_LABEL_OFFSETS = {"0.04": (.55, .40), "1.03": (-.60, .95), "1.01": (-.60, 0.0), "S.03": (.55, 0.0), "S.01": (.55, 0.0), "S.02": (.55, 0.0), "S.04": (.55, 0.0)}  # Keep IDs clear of wiring.
ELECTRICAL_ENTRANCE_LIGHT_WALL_GAP = 0.25  # Outside the finished west facade.
ELECTRICAL_TRUNK_LINE_WIDTH = 0.70  # Printed millimetres: bundled cable routes.
ELECTRICAL_TRUNK_SEPARATION = 0.15
ELECTRICAL_TRUNK_CHIMNEY_CLEARANCE = 0.55  # From the chimney's street-facing surface.
ELECTRICAL_SOCKET_WALL_OFFSET = 0.08
ELECTRICAL_SOCKET_CORNER_DISTANCE = 0.65
ELECTRICAL_LIGHT_CIRCUIT_COLOR = "#f080f0"
ELECTRICAL_FAN_COIL_CIRCUIT_COLOR = "#e6c200"
ELECTRICAL_OUTPUT_PORT_CLOCKS = {
    "basement": 9.5, "upper": 12.0, "0.01_light": 10.7, "0.01_sockets": 11.3,
    "0.02_sockets": 11.9, "0.02_light": 12.5, "0.04_light": 1.1,
    "outside_light": 2.5, "stair_landing_light": 3.0,
    "0.05_sockets": 5.0, "0.05_light": 6.0, "0.03_sockets": 8.0, "0.03_light": 9.0,
    "fan_coils": 9.0,
}
WATER_WALL_CLEARANCE = 0.10  # Plan centreline distance from the room-facing wall surface.
WATER_HOT_ROUTE_OFFSET = 0.10  # Hot water is drawn farther into the room than cold water.
WATER_BASEMENT_RISER_OFFSET_Y = 0.50  # From the drawn bottom-right corner towards the garden.
WATER_LINE_WIDTH = 0.30  # Printed millimetres.
SEWER_WALL_CLEARANCE = 0.10  # Plan centreline distance from the room-facing wall surface.
SEWER_LINE_WIDTH = 0.30  # Printed millimetres.
SECTION_OUTLINE_WIDTH = 0.3
HYDROIZOLACE_LINE_WIDTH = 0.4  # Printed millimetres; drawing-only waterproofing.

RAFTERS_MIDPOINT = CHIMNEY_CENTER[1]-0.04
4.79
RAFTER_Y_POSITIONS = (
	-0.12,
	4.29-0.67-2.75,
	4.29-0.67-1.75,
	4.29-0.67-1.0,
	4.29-0.67,
	4.29,
	5.29,
	5.29+0.84,
	5.29+0.84+1.0,
	5.29+0.84+2.0,
	9.12
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
    start=(HOUSE_WIDTH/2+0.35, -1.5),
    end=(HOUSE_WIDTH/2+0.35, HOUSE_DEPTH+1.5),
    identifier="A", direction=-1,  # Look towards +X.
)
bb_cut = CutDefinition(
    start=(-2.0, HOUSE_DEPTH/2-0.2),
    end=(HOUSE_WIDTH+0.9, HOUSE_DEPTH/2-0.2),
    identifier="B", direction=-1,  # Look towards -Y.
)
roof_xx_cut = CutDefinition(
    start=(-2, 4.0),
    end=(HOUSE_WIDTH+1, 4.0),
    identifier="X", direction=-1,  # Fixed Y; independent of BB. Look towards -Y.
)
roof_yy_cut = CutDefinition(
    start=(HOUSE_WIDTH/2, -1.3),
    end=(HOUSE_WIDTH/2, HOUSE_DEPTH+1),
    identifier="Y", direction=-1,  # Along the ridge; look towards +X.
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


def add_purlin_support_girder_plan(drawing):
    """Outline the embedded-HEB girders and dimension their span, bearings and position."""
    front_wall_inner_y = wall_front_g.start[1]+wall_front_g.body_offset+wall_front_g.thickness
    for girder in purlin_support_girders:
        x0, y = girder.start[:2]
        x1 = girder.end[0]
        left_face, right_face = purlin_support_girder_wall_faces[girder]
        bearing_offset = 0.35 if left_face == room3_ceiling_east_face_x else 0.65
        half_width = girder.width/2
        drawing.add_rectangle(
            (x0, y-half_width), (x1, y+half_width),
            name=f"{girder.Name} Plan outline",
        )
        drawing.add_text(
            (x0+(x1-x0)*0.18, y),
            f"{girder.heb_section.name}",
            font_size=1.5, name=f"{girder.Name} Plan label",
        )
        drawing.add_dimension((x0, y), (x1, y), offset=-0.7, name=f"{girder.Name} Length")
        drawing.add_dimension(
            (x0, y), (left_face, y), offset=bearing_offset,
            name=f"{girder.Name} Start wall bearing",
        )
        drawing.add_dimension(
            (right_face, y), (x1, y), offset=bearing_offset,
            name=f"{girder.Name} End wall bearing",
        )
        if left_face == room3_ceiling_east_face_x:
            drawing.add_dimension(
                (BWT, front_wall_inner_y), (BWT, y), offset=-0.5,
                name=f"{girder.Name} Centre distance from front wall",
            )


def add_ceiling_beam_plan(drawing, slab, *, wall_bounds, bearing_offset=-0.3):
    """Show beam axes, spacing, outer-beam wall offsets and bearing at both ends."""
    for index, (start, end) in enumerate(slab.beam_centerlines, 1):
        axis = drawing.add_line(
            start, end, style="dash-dot", color="red", line_width=0.08,
            name=f"{slab.Name} Beam {index} Centreline",
        )
        appearance = ifcopenshell.util.element.get_pset(axis, "EPset_Annotation")
        ifcopenshell.api.pset.edit_pset(
            drawing.house.model, pset=drawing.house.model.by_id(appearance["id"]),
            properties={"Classes": appearance["Classes"]+" ceiling-beam-axis"},
        )
    # Dimension directly at midspan so black extension lines do not cover the red axes.
    midpoints = tuple(np.mean(centreline, axis=0) for centreline in slab.beam_centerlines)
    for index, (first, second) in enumerate(zip(midpoints, midpoints[1:]), 1):
        drawing.add_dimension(
            start=tuple(first), end=tuple(second),
            name=f"{slab.Name} Beam Center Distance {index}",
        )

    start, end = (np.asarray(point) for point in slab.beam_centerlines[0])
    along = (end-start)/slab.length
    span_axis = int(np.argmax(np.abs(along)))
    start_wall, end_wall = start.copy(), end.copy()
    start_wall[span_axis], end_wall[span_axis] = wall_bounds[span_axis], wall_bounds[span_axis+2]
    drawing.add_dimension(
        start=tuple(start), end=tuple(start_wall), offset=bearing_offset,
        name=f"{slab.Name} Start Bearing",
    )
    drawing.add_dimension(
        start=tuple(end_wall), end=tuple(end), offset=bearing_offset,
        name=f"{slab.Name} End Bearing",
    )

    # Keep wall offsets beside the spacing chain, clear of the chimney and small end spacings.
    across_axis = int(np.argmax(np.abs(slab.direction)))
    near_face, far_face = wall_bounds[across_axis], wall_bounds[across_axis+2]
    if slab.direction[across_axis] < 0:
        near_face, far_face = far_face, near_face
    wall_reference_shift = along*min(0.4, slab.length/4)
    first_beam, last_beam = midpoints[0]+wall_reference_shift, midpoints[-1]+wall_reference_shift
    first_wall, last_wall = first_beam.copy(), last_beam.copy()
    first_wall[across_axis], last_wall[across_axis] = near_face, far_face
    for dimension_start, dimension_end, label in (
        (first_wall, first_beam, "First Beam to Wall"),
        (last_beam, last_wall, "Last Beam to Wall"),
    ):
        distance = np.linalg.norm(dimension_end-dimension_start)
        if distance < 1e-9:
            drawing.add_text(
                tuple(dimension_start), "0", font_size=2,
                name=f"{slab.Name} {label}",
            )
            continue
        drawing.add_dimension(
            start=tuple(dimension_start), end=tuple(dimension_end),
            name=f"{slab.Name} {label}",
        )


def add_chimney_footing(chimney):
    """Add a concrete pad beneath the foundation slab, centred under the stack."""
    size = chimney.size+2*CHIMNEY_FOOTING_OVERHANG
    half = size/2
    model = house.model
    footing = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcFooting", predefined_type="PAD_FOOTING", name="Chimney pad footing",
    )
    ifcopenshell.api.spatial.assign_container(model, products=[footing], relating_structure=foundation.element)
    placement = np.eye(4)
    placement[:3, 3] = (*chimney.center, BASEMENT_SLAB_BOTTOM_Z-FOUNDATION_FOOTING_HEIGHT)
    ifcopenshell.api.geometry.edit_object_placement(model, product=footing, matrix=placement, is_si=True)
    body = ifcopenshell.api.geometry.add_slab_representation(
        model, context=house._body_context, depth=FOUNDATION_FOOTING_HEIGHT,
        polyline=[(-half, -half), (half, -half), (half, half), (-half, half), (-half, -half)],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=footing, representation=body)
    ifcopenshell.api.style.assign_representation_styles(
        model, shape_representation=body, styles=[house._surface_style("slab", color="#969696", transparency=0)],
    )
    ifcopenshell.api.material.assign_material(
        model, products=[footing], type="IfcMaterial", material=house._materials["Concrete"],
    )
    for name, properties in (
        ("Pset_FootingCommon", {"LoadBearing": True}),
        ("BBIM_ChimneyFooting", {"Chimney": chimney.GlobalId, "Width": size, "Length": size,
                                 "Height": FOUNDATION_FOOTING_HEIGHT, "Overhang": CHIMNEY_FOOTING_OVERHANG}),
    ):
        pset = ifcopenshell.api.pset.add_pset(model, product=footing, name=name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=properties)
    return footing


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
    f"Load bearing wall - VPC {INNER_BWT*1000:g} mm",
    layers=[("Brick", INNER_BWT), "axis"],
)
garden_partition_wall = house.wall_type(
    f"Partition wall - VPC {GARDEN_PARTITION_THICKNESS*1000:g} mm",
    layers=[("Brick", GARDEN_PARTITION_THICKNESS)],  # Centred between rooms.
)
upper_bearing_wall_type = house.wall_type(
    f"Upper load bearing wall - VPC {UPPER_BEARING_WALL_THICKNESS*1000:g} mm",
    layers=[("Brick", UPPER_BEARING_WALL_THICKNESS)],  # Centred over the wall below.
)
dry_wall = house.wall_type(
    f"drywall - {DRY_WALL_WIDTH*1000:g} mm", layers=[("SDK", DRY_WALL_WIDTH)], color="#dfefcf",
)
wooden_wall = house.wall_type(
    "drevena stena", layers=[("drevena stena", WOODEN_WALL_THICKNESS)], color="#fff2cc",
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
    wall_type=garden_partition_wall, height=ground_floor_height,
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
    at=STAIRWAY_OPENING_FRONT_Y-wall_stairway_g.start[1],
    width=HALLWAY_OPENING_LENGTH,
    height=ground_floor_height-HALLWAY_OPENING_TOP_GAP,
)
bathroom_left_opening = wall_third_room_g.add_opening(
    name="Hallway - bathroom left wall opening",
    at=THIRD_ROOM_OPENING_START_Y-wall_third_room_g.start[1],
    width=THIRD_ROOM_OPENING_LENGTH,
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
    if wall_material in ("Brick", "Ytong Klasik"):
        layers = [
            (GROUND_WALL_BASE_COURSE_MATERIAL, GROUND_WALL_BASE_COURSE_HEIGHT),
            (wall_material, wall.height-GROUND_WALL_BASE_COURSE_HEIGHT),
        ]
        masonry_name = "VPC" if wall_material == "Brick" else wall_material
        wall.set_vertical_material_layers(
            layers,
            type_name=f"Ground {role} wall - {masonry_name} {wall.thickness*1000:g} mm - Liapor base course",
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
    # Retain the existing garden-room basement support's endpoints when
    # replacing the wall above with a thinner, non-load-bearing partition.
    extension = (0 if source == wall_garden_partition_g
                 else max(0, (BASEMENT_WALL_THICKNESS-source.thickness)/2))
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
    if center.y < GARDEN_ROOMS_WALL_Y and center.x < THIRD_ROOM_WALL_X:
        name = "Garáž"
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
basement_s04_x0, _, basement_s04_x1, _ = basement_rooms_by_id["S.04"].bounds
basement_s05_x0, _, basement_s05_x1, _ = basement_rooms_by_id["S.05"].bounds
basement_s05_front_door = wall_basement_front.add_door(
    name="Basement front door S.05",
    at=basement_s04_x1-0.25-BASEMENT_OPENING_WIDTH-wall_basement_front.start[0],
    width=0.9, opening_width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
    operation="SINGLE_SWING_RIGHT",
)

basement_garage_door = wall_basement_s03_s04.add_door(
    name="Basement door S.03 - S.04",
    at=basement_rooms_by_id["S.03"].bounds[1]+BASEMENT_S03_S04_FRONT_CLEARANCE-wall_basement_s03_s04.start[1],
    width=0.9, opening_width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
    operation="SINGLE_SWING_RIGHT",
	reverse_swing=True
)
basement_s01_s03_start_x = max(basement_rooms_by_id["S.01"].bounds[0], basement_rooms_by_id["S.03"].bounds[0])
basement_s01_s03_door = wall_basement_garden_rooms.add_door(
    name="Basement door S.01 - S.03",
    at=basement_s01_s03_start_x+BASEMENT_S01_S03_EAST_CLEARANCE-wall_basement_garden_rooms.start[0],
    width=0.9, opening_width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
    operation="SINGLE_SWING_LEFT",
)
basement_stairway_opening = wall_basement_s04_s05.add_opening(
    name="Basement opening S.04 - S.05",
    at=basement_rooms_by_id["S.05"].bounds[1]+BASEMENT_S04_S05_FRONT_CLEARANCE-wall_basement_s04_s05.start[1],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
basement_stair_room_x0, _, basement_stair_room_x1, _ = basement_rooms_by_id["S.05"].bounds
basement_garden_opening = wall_basement_garden_rooms.add_opening(
    name="Basement opening S.02 - S.05",
    at=basement_stair_room_x1-BASEMENT_S02_S05_WEST_CLEARANCE-BASEMENT_OPENING_WIDTH-wall_basement_garden_rooms.start[0],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
_, basement_garden_room_y0, _, basement_garden_room_y1 = basement_rooms_by_id["S.01"].bounds
basement_storage_opening = wall_basement_s01_s02.add_opening(
    name="Basement opening S.01 - S.02",
    at=basement_garden_room_y1-BASEMENT_S01_S02_GARDEN_CLEARANCE-BASEMENT_OPENING_WIDTH-wall_basement_s01_s02.start[1],
    width=BASEMENT_OPENING_WIDTH,
    height=BASEMENT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
basement_garage_x0, _, basement_garage_x1, _ = basement_rooms_by_id["S.03"].bounds
garage_front_opening = wall_basement_front.add_opening(
    name="Garage front opening",
    at=basement_garage_x0+GARAGE_FRONT_OPENING_SIDE_CLEARANCE-wall_basement_front.start[0],
    width=GARAGE_FRONT_OPENING_WIDTH,
    height=GARAGE_FRONT_OPENING_TOP_HEIGHT, sill_height=BASEMENT_FLOOR_THICKNESS,
)
garage_front_door = wall_basement_front.add_garage_door(
    garage_front_opening, name="Garage sectional door", color="#ffffff",
)
garage_front_opening_west_x = float(ifcopenshell.util.placement.get_local_placement(
    garage_front_opening.ObjectPlacement,
)[0, 3])+garage_front_door.OverallWidth
heat_pump = basement.furniture(
    "Tepelné\nČerpadlo", kind="USERDEFINED", size=HEAT_PUMP_SIZE, color="#ffffff",
    center=(
		garage_front_opening_west_x+HEAT_PUMP_GARAGE_GAP+HEAT_PUMP_SIZE[0]/2-0.25,
        wall_basement_front.start[1]+wall_basement_front.body_offset
            -EXTERIOR_XPS_INSULATION_THICKNESS-FACADE_THICKNESS-0.05-HEAT_PUMP_SIZE[1]/2),
    start_height=BASEMENT_FLOOR_THICKNESS+HEAT_PUMP_HEIGHT_ABOVE_BASEMENT_FLOOR+0.4,
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
        (HOUSE_WIDTH/2-GARDEN_PARTITION_THICKNESS/2, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH/2-GARDEN_PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT),
        (BWT, HOUSE_DEPTH-BWT),
    ),
    **floor_layer_settings,
)
pokoj2 = ground.floor_layer(
    "Pokoj 2", room_id="0.02",
    outline=(
        (HOUSE_WIDTH/2+GARDEN_PARTITION_THICKNESS/2, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
        (HOUSE_WIDTH/2+GARDEN_PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT),
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
# Follow the bathroom partition and extend the stair approach to the first tread.
hallway_front_y = BATHROOM_PARTITION_Y+DRY_WALL_WIDTH
hallway_outline = box(
    THIRD_ROOM_WALL_X, hallway_front_y, HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y,
).union(box(
    THIRD_ROOM_NARROW_WALL_X, THIRD_ROOM_STEP_Y+DRY_WALL_WIDTH,
    THIRD_ROOM_WALL_X, GARDEN_ROOMS_WALL_Y,
))
for wall_start_y, wall_end_y in (
    (hallway_front_y, STAIRWAY_OPENING_FRONT_Y),
    (STAIRWAY_OPENING_FRONT_Y+HALLWAY_OPENING_LENGTH, GARDEN_ROOMS_WALL_Y),
):
    if wall_end_y > wall_start_y:
        hallway_outline = hallway_outline.difference(box(
            BATHROOM_RIGHT_X, wall_start_y, STAIRWAY_WALL_X, wall_end_y,
        ))
hallway_outline = hallway_outline.union(box(
    STAIR_LEFT_X, min(STAIR_LOWER_START_Y, STAIR_UPPER_END_Y),
    STAIR_RIGHT_X, hallway_front_y,
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
    at=wall_back_g.start[0]-(HOUSE_WIDTH/2-GARDEN_WINDOW_CENTER_CLEARANCE),
    width=ROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_SILL_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
window_pokoj2 = wall_back_g.add_window(
    name="Pokoj 2 window",
    at=wall_back_g.start[0]-(HOUSE_WIDTH/2+GARDEN_WINDOW_CENTER_CLEARANCE+ROOM_WINDOW_WIDTH),
    width=ROOM_WINDOW_WIDTH,
    sill_height=GROUND_WINDOW_SILL_HEIGHT,
    height=GROUND_WINDOW_TOP_HEIGHT,
)
window_pokoj3 = wall_front_g.add_window(
    name="Pokoj 3 window",
    at=BWT+THIRD_ROOM_WINDOW_EAST_CLEARANCE-wall_front_g.start[0],
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


def add_ground_room_annotations(drawing, *, include_legend=True):
    """Share ground-floor room identifiers and an optional table between plans."""
    for room in ground_room_floors:
        match room:
            case (room, offset_x, offset_y):
                pass
            case _:
                offset_x = 0.0
                offset_y = 0.0
        position = Polygon(room.outline).representative_point().coords[0]
        position = (position[0]+offset_x, position[1]+offset_y)
        if room == chodba:
            position = (position[0]+1.0, position[1]-0.1)
        elif room == pokoj3 or room == koupelna:
            position = (position[0]-0.5, position[1])
        drawing.add_room_annotation(
            position, identifier=room.room_id, description=room.Name, area=room.area,
            window_area=window_area(*ground_room_windows[room.room_id]),
        )
    if include_legend:
        drawing.add_room_legend()


# Fan coils face into their rooms, centred above the construction door openings.
ground_fan_coils = []
for room, door, wall, room_normal in (
    (pokoj1, pokoj1_door, wall_garden_rooms_g, (0., 1.)),
    (pokoj2, pokoj2_door, wall_garden_rooms_g, (0., 1.)),
    (pokoj3, pokoj3_door, wall_third_room_top_g, (-1., 0.)),
):
    opening = door.FillsVoids[0].RelatingOpeningElement
    opening_placement = ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)
    door_center = opening_placement[:2, 3]+opening_placement[:2, 0]*ROOM_DOOR_OPENING_WIDTH/2
    tangent = (np.asarray(wall.end)-wall.start)/wall.length
    wall_normal = np.array((-tangent[1], tangent[0]))
    inward = np.asarray(room_normal)
    face_offset = wall.body_offset+(wall.thickness if np.dot(wall_normal, inward)>0 else 0)
    face = np.asarray(wall.start)+wall_normal*face_offset
    wall_face_center = door_center+inward*np.dot(face-door_center, inward)
    center = wall_face_center+inward*(FAN_COIL_WALL_GAP+FAN_COIL_SIZE[1]/2)
    door_placement = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
    bottom = float(door_placement[2, 3])+door.OverallHeight+FAN_COIL_DOOR_CLEARANCE-ground.elevation
    if bottom+FAN_COIL_SIZE[2] > ground_floor_height-CEILING_PLASTER_THICKNESS:
        raise ValueError(f"Fan coil above {room.room_id} door does not fit below the ceiling")
    ground_fan_coils.append(ground.fan_coil(
        f"Fan coil {room.room_id}", center=tuple(float(v) for v in center), size=FAN_COIL_SIZE,
        start_height=bottom, rotation=math.degrees(math.atan2(inward[1], inward[0]))+90,
        label="FCU",
    ))
ground_fan_coils = tuple(ground_fan_coils)

# Hallway-facing cabinet beside the bathroom door, on the bathroom SDK wall.
rozvadec = ground.furniture(
    "Rozvaděč", kind="USERDEFINED", size=ROZVADEC_SIZE, color="#ffffff",
    center=(wall_bathroom_partition_g.start[0]+BATHROOM_DOOR_SIDE_CLEARANCE
            +ROOM_DOOR_OPENING_WIDTH+ROZVADEC_WALL_GAP+ROZVADEC_SIZE[0]/2+0.15,
            wall_bathroom_partition_g.start[1]+wall_bathroom_partition_g.body_offset
            +wall_bathroom_partition_g.thickness+ROZVADEC_WALL_GAP+ROZVADEC_SIZE[1]/2),
    start_height=GROUND_FLOOR_THICKNESS+ROZVADEC_BOTTOM_ABOVE_FLOOR,
)

# Right-hand fixtures occupy consecutive zones from the inside garden partition.
bathroom_right_x = BATHROOM_RIGHT_X
bathroom_toilet_center_y = BATHROOM_PARTITION_Y-BATHROOM_TOILET_ZONE_DEPTH/2
bathroom_basin_center_y = BATHROOM_PARTITION_Y-BATHROOM_TOILET_ZONE_DEPTH-BATHROOM_BASIN_ZONE_DEPTH/2
bathroom_tuv_center_y = (BATHROOM_PARTITION_Y-BATHROOM_TOILET_ZONE_DEPTH
                         -BATHROOM_BASIN_ZONE_DEPTH-BATHROOM_TUV_ZONE_DEPTH/2)
bathroom_toilet = ground.asset(
    "WC", asset="toilet_without_cistern",
    center=(bathroom_right_x-0.53/2-0.2, bathroom_toilet_center_y),
    start_height=GROUND_FLOOR_THICKNESS,
    rotation=-90,
)
bathroom_basin = ground.asset(
    "Umyvadlo", asset="basin_large",
    center=(bathroom_right_x-0.55/2-0.1, bathroom_basin_center_y),
    start_height=GROUND_FLOOR_THICKNESS+0.85-0.25,
    rotation=-90,
)
bathroom_shower = ground.asset(
    "Sprcha", asset="shower_90x90", label="Sprcha",
    center=(BATHROOM_LEFT_X+0.55, BWT+0.55),
    start_height=GROUND_FLOOR_THICKNESS+0.03,
    rotation=180,
)
bathroom_services_center_x = bathroom_right_x-BATHROOM_TUV_STAIRWAY_CLEARANCE-0.7/2
bathroom_water_heater = ground.furniture(
    "Zásobník\nTUV", kind="USERDEFINED",
    size=(0.7, 0.7, 2.0),
    center=(bathroom_services_center_x, bathroom_tuv_center_y),
    start_height=GROUND_FLOOR_THICKNESS+0.03,
    color="#ffffff",
)
bathroom_hydrobox_center = (
    BATHROOM_WINDOW_CENTER_X,
    BWT+BATHROOM_HYDROBOX_WALL_GAP+HYDROBOX_SIZE[1]/2,
)
bathroom_hydrobox = ground.furniture(
    "Hydro-\nbox", kind="USERDEFINED", size=HYDROBOX_SIZE, color="#ffffff",
    center=bathroom_hydrobox_center,
    start_height=GROUND_FLOOR_THICKNESS+0.03,
)
bathroom_fan_coil_center = (
    BATHROOM_LEFT_X+FAN_COIL_WALL_GAP+BATHROOM_FAN_COIL_SIZE[1]/2,
    BATHROOM_PARTITION_Y-BATHROOM_FAN_COIL_DOOR_WALL_GAP-BATHROOM_FAN_COIL_SIZE[0]/2,
)
bathroom_fan_coil = ground.fan_coil(
    "Fan coil 0.05 console", center=bathroom_fan_coil_center, size=BATHROOM_FAN_COIL_SIZE,
    start_height=GROUND_FLOOR_THICKNESS, rotation=90, form="console", label="FCU",
)
basement_water_meter = basement.furniture(
    "Vodo-\nměr", kind="USERDEFINED",
    size=(0.6, 0.55, 0.5),
    center=(basement_s04_x1-0.05-0.6/2, BWT+0.7),
    start_height=BASEMENT_FLOOR_THICKNESS + 0.8,
    color="#ffffff",
)

# Stairs use the ceiling and future upper-floor levels.
lower_stairs = ground.stair(
    (STAIR_LOWER_CENTER_X, STAIR_LOWER_START_Y),
    (STAIR_LOWER_CENTER_X, STAIR_LANDING_END_Y),
    name="Lower stair flight",
    construction=INTERNAL_STAIR_CONSTRUCTION, color=INTERNAL_STAIR_COLOR,
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
    material=INTERNAL_STAIR_MATERIAL, color=INTERNAL_STAIR_COLOR,
    height=lower_stairs.end_height,
    thickness=STAIR_WAIST_THICKNESS,
)
upper_stairs = ground.stair(
    (STAIR_UPPER_CENTER_X, STAIR_LANDING_END_Y),
    (STAIR_UPPER_CENTER_X, STAIR_UPPER_END_Y),
    name="Upper stair flight",
    construction=INTERNAL_STAIR_CONSTRUCTION, color=INTERNAL_STAIR_COLOR,
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
stair_landing_gap_railing = ground.railing(
    "Middle landing - flight gap railing",
    path=tuple(
        (point[0], STAIR_LANDING_END_Y-STAIR_RAILING_INSET,
         ground.elevation+lower_stairs.end_height)
        for point in (stair_railing.path[0], lower_stair_railing.path[-1])
    ),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
)
# Match the former railing's outer envelope, including its end posts.
wall_stairwell_wood_g = ground.wall(
    (STAIR_LEFT_X, STAIR_LOWER_START_Y+STAIR_RAILING_INSET),
    (STAIR_LEFT_X+1.2, STAIR_LOWER_START_Y+STAIR_RAILING_INSET),
    wall_type=wooden_wall, start_height=GROUND_FLOOR_THICKNESS,
    height=ground_floor_height-CEILING_PLASTER_THICKNESS-GROUND_FLOOR_THICKNESS,
)
wall_stairwell_wood_g.Name = "Dřevěná stěna u schodiště"
common = ifcopenshell.api.pset.add_pset(house.model, product=wall_stairwell_wood_g, name="Pset_WallCommon")
ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": False})
upper_stair_exit_railing = upper.railing(
    "Upper stair exit - west wall railing",
    path=(
        (STAIR_UPPER_CENTER_X+STAIR_FLIGHT_WIDTH/2-STAIR_RAILING_INSET,
         STAIR_UPPER_END_Y+STAIR_RAILING_INSET, UPPER_FINISHED_FLOOR_HEIGHT),
        (HOUSE_WIDTH-BWT-0.03,
         STAIR_UPPER_END_Y+STAIR_RAILING_INSET, UPPER_FINISHED_FLOOR_HEIGHT),
    ),
    height=STAIR_RAILING_HEIGHT, color="#C8B090",
)
stair_route_landing_y = (STAIR_LANDING_START_Y+STAIR_LANDING_END_Y)/2
stair_walking_route = (
    lower_stairs.start, (STAIR_LOWER_CENTER_X, stair_route_landing_y),
    (STAIR_UPPER_CENTER_X, stair_route_landing_y), upper_stairs.end,
)
# Keep one quarter circle aligned with the street edge of the stairway opening.
stair_entry_clearance_points = tuple(
    (center_x+STAIR_FLIGHT_WIDTH*math.cos(angle), center_y+STAIR_FLIGHT_WIDTH*math.sin(angle))
    for center_x, center_y, angle_start, angle_end in (
        (STAIR_LOWER_CENTER_X-STAIR_FLIGHT_WIDTH/2, BWT+3.0, math.pi/2, 0),
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
    if not math.isfinite(ENTRANCE_LANDING_LENGTH) or ENTRANCE_LANDING_LENGTH < ENTRANCE_OPENING_WIDTH:
        raise ValueError("entrance landing length must be finite and cover the door opening")
    landing_garden_y = landing_street_y+ENTRANCE_LANDING_LENGTH
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
    f"{entrance_stairs.risers} výšek po {entrance_stairs.riser_height*1000:.1f} mm".replace(".", ",")+".",
    f"Šířka {entrance_stairs.width*1000:.0f} mm; nášlap {entrance_stairs.tread_length*1000:.0f} mm.",
]
print(f"Entrance stairs: {entrance_stairs.risers} risers x {entrance_stairs.riser_height*1000:.1f} mm; "
      f"tread {entrance_stairs.tread_length*1000:.0f} mm; "
      f"2h+b = {(2*entrance_stairs.riser_height+entrance_stairs.tread_length)*1000:.1f} mm")

# Retain the layout coordinates for future basement stairs and their ground-floor closure.
basement_stair_room = basement_rooms_by_id["S.05"]
basement_stair_left_x, basement_landing_start_y, basement_stair_room_right_x, basement_stair_room_back_y = basement_stair_room.bounds
basement_stair_right_x = basement_stair_room_right_x
basement_stair_width = (basement_stair_right_x-basement_stair_left_x-BASEMENT_STAIR_FLIGHT_GAP)/2
basement_landing_end_y = basement_landing_start_y+STAIR_LANDING_LENGTH
basement_lower_start_y = basement_landing_end_y+BASEMENT_STAIR_LOWER_RUN_LENGTH
basement_upper_end_y = basement_landing_end_y+BASEMENT_STAIR_UPPER_RUN_LENGTH
if (basement_stair_width <= 0
        or max(basement_lower_start_y, basement_upper_end_y) > basement_stair_room_back_y+1e-9):
    raise ValueError("basement stairs do not fit inside the clear stairway room")
basement_upper_center_x = basement_stair_left_x+basement_stair_width/2
basement_lower_center_x = basement_stair_right_x-basement_stair_width/2
# The full-height wooden wall guards the former descending entrance.
# The ceiling itself remains open for a future stair.
print(f"Basement to ground finished-floor rise: {BASEMENT_TO_GROUND_RISE:.3f} m; "
      "basement stairs omitted, ceiling opening retained for future installation")

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


def add_miako_ceiling(
    storey, name, bounds, *, beam_axis, structure=None,
    width_alignment="center", reverse_width=False,
):
    """Fit bearing spans; use an explicit beam/wide/narrow list or auto-fit rows."""
    x0, y0, x1, y1 = bounds
    if x1 <= x0 or y1 <= y0 or beam_axis not in {"x", "y"}:
        raise ValueError(f"invalid ceiling bounds or beam axis for {name}")
    clear_span, covered_width = (x1-x0, y1-y0) if beam_axis == "x" else (y1-y0, x1-x0)
    structure = design_miako_structure(covered_width) if structure is None else tuple(structure)
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
    # Start row numbering at the far edge when laying out towards the street.
    width_origin = width_start+width if reverse_width else width_start
    layout_sign = -1 if reverse_width else 1
    if beam_axis == "x":
        start, end = (cx-length/2, width_origin), (cx+length/2, width_origin)
        direction = (0, layout_sign)
    else:
        start, end = (width_origin, cy-length/2), (width_origin, cy+length/2)
        direction = (layout_sign, 0)
    slab = storey.miako_slab(
        name, start=start, end=end, top=CEILING_THICKNESS,
        direction=direction, structure=structure,
        topping=0.06, beam_height=0.06, block_height=CEILING_THICKNESS-0.06,
        block_start_offset=bearing, block_end_offset=bearing,
    )
    print(f"{name}: {len(slab.beams)} beams x {length:.3f} m along {beam_axis}; "
          f"{structure.count('wide')} wide + {structure.count('narrow')} narrow rows; "
          f"width {width:.3f}/{covered_width:.3f} m (difference {(width-covered_width)*1000:+.0f} mm); "
          f"bearing {bearing*1000:.0f} mm each end")
    return slab


def add_horizontal_opening(host, name, region, *, bottom_z, height):
    """Cut one occurrence without changing mapped geometry shared by other parts."""
    opening = ifcopenshell.api.root.create_entity(
        house.model, ifc_class="IfcOpeningElement", predefined_type="OPENING", name=name,
    )
    body = ifcopenshell.api.geometry.add_slab_representation(
        house.model, context=house._body_context, depth=height,
        polyline=tuple(region.exterior.coords)[:-1],
    )
    ifcopenshell.api.geometry.assign_representation(house.model, product=opening, representation=body)
    ifcopenshell.api.feature.add_feature(house.model, feature=opening, element=host)
    placement = np.eye(4)
    placement[2, 3] = bottom_z
    ifcopenshell.api.geometry.edit_object_placement(house.model, product=opening, matrix=placement, is_si=True)
    return opening


def trim_first_miako_block_row(slab, region):
    """Retain blocks on both sides of a bounded opening in the first bay."""
    xmin, ymin, xmax, ymax = region.bounds
    block_cut = box(xmin, ymin-0.1, xmax, ymax+0.1)  # Include the ceramic bearing lips.
    removed = []
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    for block in slab.blocks:
        if " Block 1." not in block.Name:
            continue
        shape = ifcopenshell.geom.create_shape(settings, block)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
        first_x, last_x = vertices[:, 0].min(), vertices[:, 0].max()
        if last_x <= xmin+1e-9 or first_x >= xmax-1e-9:
            continue
        if first_x >= xmin-1e-9 and last_x <= xmax+1e-9:
            removed.append(block)
        else:
            add_horizontal_opening(
                block, f"{slab.Name} First block row chimney trim", block_cut,
                bottom_z=slab.storey.elevation-0.01, height=CEILING_THICKNESS+0.02,
            )
    removed_ids = {block.id() for block in removed}
    object.__setattr__(slab, "blocks", tuple(block for block in slab.blocks if block.id() not in removed_ids))
    object.__setattr__(slab, "components", tuple(part for part in slab.components if part.id() not in removed_ids))
    for block in removed:
        ifcopenshell.api.root.remove_product(house.model, product=block)
    return add_horizontal_opening(
        slab.topping_element, f"{slab.Name} Chimney opening", region,
        bottom_z=slab.storey.elevation-0.01, height=CEILING_THICKNESS+0.02,
    )


# Define the upstairs layouts before the basement copies of their garden-side parts.
# One ceiling across both garden rooms, with beams spanning along Y between
# the transverse bearing wall and garden wall, independently of the partition.
GARDEN_CEILING_STRUCTURE = [  # East to west; 14 beams, 13 wide bays, 26 spaces.
    "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
    "space", "wide", "space", "beam",
]
GARDEN_CEILING_WIDTH = sum(CEILING_STRIP_WIDTHS[item] for item in GARDEN_CEILING_STRUCTURE)
GARDEN_CEILING_BEAM_LENGTH = math.ceil(
    (GARDEN_ROOMS_DEPTH+2*CEILING_BEAM_BEARING-1e-9)/CEILING_BEAM_LENGTH_STEP
)*CEILING_BEAM_LENGTH_STEP
GARDEN_CEILING_BEARING = (GARDEN_CEILING_BEAM_LENGTH-GARDEN_ROOMS_DEPTH)/2
GARDEN_CEILING_START_X = (HOUSE_WIDTH-GARDEN_CEILING_WIDTH)/2
GARDEN_CEILING_START_Y = GARDEN_ROOMS_WALL_Y+INNER_BWT-GARDEN_CEILING_BEARING
ceiling_garden_rooms = ceiling_storey.miako_slab(
    "Ceiling - Pokoj 1 + Pokoj 2",
    start=(GARDEN_CEILING_START_X, GARDEN_CEILING_START_Y),
    end=(GARDEN_CEILING_START_X, GARDEN_CEILING_START_Y+GARDEN_CEILING_BEAM_LENGTH),
    direction=(1, 0), top=CEILING_THICKNESS,
    structure=GARDEN_CEILING_STRUCTURE,
    block_length=0.25,
    block_start_offset=GARDEN_CEILING_BEARING,
    block_end_offset=GARDEN_CEILING_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

# Independent spans on either side of the middle load-bearing wall.
room3_ceiling_east_face_x = wall_east_g.start[0]+wall_east_g.body_offset+wall_east_g.thickness
room3_ceiling_middle_face_x = wall_third_room_g.start[0]-(wall_third_room_g.body_offset+wall_third_room_g.thickness)
bathroom_ceiling_middle_face_x = wall_third_room_g.start[0]-wall_third_room_g.body_offset
bathroom_ceiling_stairway_face_x = wall_stairway_g.start[0]-(wall_stairway_g.body_offset+wall_stairway_g.thickness)
ROOM3_CEILING_BEAM_LENGTH = 3.50
ROOM3_CEILING_EAST_BEARING = 0.13
ROOM3_CEILING_MIDDLE_BEARING = (
    ROOM3_CEILING_BEAM_LENGTH
    -(room3_ceiling_middle_face_x-room3_ceiling_east_face_x)
    -ROOM3_CEILING_EAST_BEARING
)
ceiling_room3_start_x = room3_ceiling_east_face_x-ROOM3_CEILING_EAST_BEARING
ceiling_room3_end_x = room3_ceiling_middle_face_x+ROOM3_CEILING_MIDDLE_BEARING
BATHROOM_CEILING_BEARING = 0.12
ceiling_bathroom_start_x = bathroom_ceiling_middle_face_x-BATHROOM_CEILING_BEARING
ceiling_bathroom_end_x = bathroom_ceiling_stairway_face_x+BATHROOM_CEILING_BEARING
BATHROOM_CEILING_BEAM_LENGTH = ceiling_bathroom_end_x-ceiling_bathroom_start_x


# One garden-side ceiling per room, with a local first-row chimney opening.
UPPER_CHIMNEY_BEAM_CLEARANCE = 0.03
UPPER_CHIMNEY_BLOCK_CLEARANCE = 0.05
upper_ceiling_garden_y = (
    CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2+UPPER_CHIMNEY_BEAM_CLEARANCE+CEILING_STRIP_WIDTHS["beam"]
)
ceiling_room3 = ceiling_storey.miako_slab(
    "Ceiling - 0.03 Pokoj 3",
    start=(ceiling_room3_start_x, upper_ceiling_garden_y),
    end=(ceiling_room3_end_x, upper_ceiling_garden_y),
    direction=(0, -1), top=CEILING_THICKNESS,
    structure=[  # Garden to street; first beam/bay and following rows in one slab.
        "beam", "space", "wide", "space",
        "beam", "beam",
		"space", "wide", "space", "beam",
		"space", "wide", "space", "beam",
		"beam"
    ],
    block_length=0.25,
    block_start_offset=ROOM3_CEILING_EAST_BEARING,
    block_end_offset=ROOM3_CEILING_MIDDLE_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

ceiling_bathroom = ceiling_storey.miako_slab(
    "Ceiling - 0.05 Koupelna a chodba",
    start=(ceiling_bathroom_start_x, upper_ceiling_garden_y),
    end=(ceiling_bathroom_end_x, upper_ceiling_garden_y),
    direction=(0, -1), top=CEILING_THICKNESS,
    structure=[  # Garden to street; first beam/bay and following rows in one slab.
        "beam", "space", "wide", "space",
        "beam", "beam",
		"space", "wide", "space", "beam",
		"space", "wide", "space", "beam",
		"beam"
    ],
    block_length=0.25,
    block_start_offset=BATHROOM_CEILING_BEARING,
    block_end_offset=BATHROOM_CEILING_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

upper_chimney_first_bay_width = (
    CEILING_STRIP_WIDTHS["beam"]+2*CEILING_STRIP_WIDTHS["space"]+CEILING_STRIP_WIDTHS["wide"]
)
upper_chimney_clearance_region = box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2-UPPER_CHIMNEY_BLOCK_CLEARANCE,
    upper_ceiling_garden_y-upper_chimney_first_bay_width,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2+UPPER_CHIMNEY_BLOCK_CLEARANCE,
    upper_ceiling_garden_y-CEILING_STRIP_WIDTHS["beam"],
)
upper_chimney_opening = trim_first_miako_block_row(ceiling_bathroom, upper_chimney_clearance_region)

FRONT_CEILING_WALL_OVERLAP = 0.04
ceiling_front_girder_edge_y = min(
    y for positions in PURLIN_SUPPORT_Y_POSITIONS for y in positions
)-PURLIN_SUPPORT_GIRDER_SIZE[0]/2
ceiling_room3_front = ceiling_storey.miako_slab(
    "Ceiling - 0.03 Pokoj 3 u ulice",
    start=(ceiling_room3_start_x, BWT-FRONT_CEILING_WALL_OVERLAP),
    end=(ceiling_room3_end_x, BWT-FRONT_CEILING_WALL_OVERLAP),
    direction=(0, 1), top=CEILING_THICKNESS,
    structure=[  # Street to garden; another full wide-block bay would reach the girder.
        "narrow", "space",
        "beam", "space", "narrow", "space",
        "beam", "space", "wide", "space",
        "beam", "space", "narrow", "space",
		"beam",
		"beam",
    ],
    block_length=0.25,
    block_start_offset=ROOM3_CEILING_EAST_BEARING,
    block_end_offset=ROOM3_CEILING_MIDDLE_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

ceiling_bathroom_front = ceiling_storey.miako_slab(
    "Ceiling - 0.05 Koupelna u ulice",
    start=(ceiling_bathroom_start_x, BWT-FRONT_CEILING_WALL_OVERLAP),
    end=(ceiling_bathroom_end_x, BWT-FRONT_CEILING_WALL_OVERLAP),
    direction=(0, 1), top=CEILING_THICKNESS,
    structure=[  # Street to garden; another full wide-block bay would reach the girder.
        "narrow", "space",
        "beam", "space", "narrow", "space",
        "beam", "space", "wide", "space",
        "beam", "space", "narrow", "space",
		"beam",
		"beam",
    ],
    block_length=0.25,
    block_start_offset=BATHROOM_CEILING_BEARING,
    block_end_offset=BATHROOM_CEILING_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

STAIRWAY_CEILING_GARDEN_WALL_CLEARANCE = -0.005
# Preserve the main layout's Y position after removing the separate beam strip.
ceiling_stairway_start_y = (
    wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset
    -STAIRWAY_CEILING_GARDEN_WALL_CLEARANCE
)
STAIRWAY_CEILING_BEAM_LENGTH = 2.50
STAIRWAY_CEILING_WEST_BEARING = 0.13
# Both walls run along +Y, with their material towards -X.
stairway_ceiling_stairway_face_x = wall_stairway_g.start[0]-wall_stairway_g.body_offset
stairway_ceiling_west_face_x = wall_west_g.start[0]-(wall_west_g.body_offset+wall_west_g.thickness)
STAIRWAY_CEILING_STAIRWAY_BEARING = (
    STAIRWAY_CEILING_BEAM_LENGTH
    -(stairway_ceiling_west_face_x-stairway_ceiling_stairway_face_x)
    -STAIRWAY_CEILING_WEST_BEARING
)
ceiling_stairway_start_x = stairway_ceiling_stairway_face_x-STAIRWAY_CEILING_STAIRWAY_BEARING
ceiling_stairway_end_x = stairway_ceiling_west_face_x+STAIRWAY_CEILING_WEST_BEARING
ceiling_stairway = ceiling_storey.miako_slab(
    "Ceiling - Schodiště",
    # Keep the garden edge fixed; the structure determines the street edge.
    start=(ceiling_stairway_start_x, ceiling_stairway_start_y),
    end=(ceiling_stairway_end_x, ceiling_stairway_start_y),
    direction=(0, -1), top=CEILING_THICKNESS,
    structure=[  # Garden to street for X-spanning beams; east to west for Y-spanning beams.
		"beam", "space", "wide", "space",
		"beam", "space", "wide", "space",
		"beam", "beam", "beam", "beam"
    ],
    block_length=0.25,
    block_start_offset=STAIRWAY_CEILING_STAIRWAY_BEARING,
    block_end_offset=STAIRWAY_CEILING_WEST_BEARING,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

# Basement garden rooms: equal end bearings and centred seven-beam layouts.
basement_ceiling_s01 = add_miako_ceiling(
    basement_ceiling_storey, "Basement ceiling - S.01",
    basement_rooms_by_id["S.01"].bounds,
    beam_axis="y",
    structure=[  # Seven beams and six wide bays, centred across the clear room.
        "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
    ],
)
basement_ceiling_s02 = add_miako_ceiling(
    basement_ceiling_storey, "Basement ceiling - S.02",
    basement_rooms_by_id["S.02"].bounds,
    beam_axis="y",
    structure=[  # Seven beams and six wide bays, centred across the clear room.
        "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
        "space", "wide", "space", "beam",
    ],
)
# S.05 retains the reusable stairway layout; S.03/S.04 have direct specifications below.
def add_basement_ceiling_copy(source, name, identifier, *, shift_y=0.0):
    x0, _, x1, _ = basement_rooms_by_id[identifier].bounds
    start_bearing = x0-source.start[0]
    end_bearing = source.end[0]-x1
    if min(start_bearing, end_bearing) < CEILING_BEAM_BEARING-1e-9:
        raise ValueError(f"{name} cannot reuse its upstairs span with the required wall bearings")
    return basement_ceiling_storey.miako_slab(
        name,
        start=(source.start[0], source.start[1]+shift_y),
        end=(source.end[0], source.end[1]+shift_y),
        direction=source.direction, top=CEILING_THICKNESS,
        structure=list(source.structure),
        block_length=source.block_length,
        block_start_offset=max(start_bearing, source.block_start_offset),
        block_end_offset=max(end_bearing, source.block_end_offset),
        block_height=source.block_height, topping=source.topping, beam_height=source.beam_height,
    )


basement_s03_x0, basement_s03_y0, basement_s03_x1, basement_s03_y1 = basement_rooms_by_id["S.03"].bounds
basement_s04_x0, basement_s04_y0, basement_s04_x1, basement_s04_y1 = basement_rooms_by_id["S.04"].bounds
basement_s05_x0, basement_s05_y0, basement_s05_x1, basement_s05_y1 = basement_rooms_by_id["S.05"].bounds
# Independent basement specifications. Append/edit rows towards the street;
# neither ceiling stops at, or depends on, the upstairs HEB position.
BASEMENT_S03_BEAM_LENGTH = 3.50
BASEMENT_S03_EAST_BEARING = 0.16
BASEMENT_S04_BEAM_LENGTH = 2.50
BASEMENT_S04_MIDDLE_BEARING = 0.15
BASEMENT_CHIMNEY_BEAM_CLEARANCE = 0.03
BASEMENT_CHIMNEY_BLOCK_CLEARANCE = 0.05
basement_ceiling_garden_y = (
    CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2+BASEMENT_CHIMNEY_BEAM_CLEARANCE
    +CEILING_STRIP_WIDTHS["beam"]
)
basement_s03_ceiling_start_x = basement_s03_x0-BASEMENT_S03_EAST_BEARING
basement_s03_ceiling_end_x = basement_s03_ceiling_start_x+BASEMENT_S03_BEAM_LENGTH
basement_s04_ceiling_start_x = basement_s04_x0-BASEMENT_S04_MIDDLE_BEARING
basement_s04_ceiling_end_x = basement_s04_ceiling_start_x+BASEMENT_S04_BEAM_LENGTH

basement_ceiling_s03 = basement_ceiling_storey.miako_slab(
    "Basement ceiling - S.03",
    start=(basement_s03_ceiling_start_x, basement_ceiling_garden_y),
    end=(basement_s03_ceiling_end_x, basement_ceiling_garden_y),
    direction=(0, -1), top=CEILING_THICKNESS,
    structure=[  # Garden to street. Keep the first beam and first wide bay.
        "beam", "space", "wide", "space",
        # Edit or append the remaining rows here; there is no HEB split.
        "beam",
        "space", "wide", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
    ],
    block_length=0.25,
    block_start_offset=BASEMENT_S03_EAST_BEARING,
    block_end_offset=basement_s03_ceiling_end_x-basement_s03_x1,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

basement_ceiling_s04 = basement_ceiling_storey.miako_slab(
    "Basement ceiling - S.04",
    start=(basement_s04_ceiling_start_x, basement_ceiling_garden_y),
    end=(basement_s04_ceiling_end_x, basement_ceiling_garden_y),
    direction=(0, -1), top=CEILING_THICKNESS,
    structure=[  # Garden to street. Keep the first beam and first wide bay.
        "beam", "space", "wide", "space",
        # Edit or append the remaining rows here; there is no HEB split.
        "beam",
        "space", "wide", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
        "space", "narrow", "space", "beam",
    ],
    block_length=0.25,
    block_start_offset=BASEMENT_S04_MIDDLE_BEARING,
    block_end_offset=basement_s04_ceiling_end_x-basement_s04_x1,
    block_height=CEILING_THICKNESS-0.06, topping=0.06, beam_height=0.06,
)

basement_stair_opening_end_y = basement_s05_y0+BASEMENT_STAIR_OPENING_LENGTH
if not 0 < BASEMENT_STAIR_OPENING_LENGTH < basement_s05_y1-basement_s05_y0:
    raise ValueError("BASEMENT_STAIR_OPENING_LENGTH must leave a ceiling at the garden end of S.05")
basement_s05_ceiling_shift_y = max(
    0.0, basement_stair_opening_end_y-min(point[1] for point in ceiling_stairway.footprint),
)
basement_ceiling_s05 = add_basement_ceiling_copy(
    ceiling_stairway, "Basement ceiling - S.05", "S.05", shift_y=basement_s05_ceiling_shift_y,
)

# The same bounded chimney opening leaves full block rows on both sides.
basement_chimney_first_bay_width = (
    CEILING_STRIP_WIDTHS["beam"]+2*CEILING_STRIP_WIDTHS["space"]+CEILING_STRIP_WIDTHS["wide"]
)
basement_chimney_clearance_region = box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2-BASEMENT_CHIMNEY_BLOCK_CLEARANCE,
    basement_ceiling_garden_y-basement_chimney_first_bay_width,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2+BASEMENT_CHIMNEY_BLOCK_CLEARANCE,
    basement_ceiling_garden_y-CEILING_STRIP_WIDTHS["beam"],
)
basement_chimney_opening = trim_first_miako_block_row(basement_ceiling_s04, basement_chimney_clearance_region)

basement_ceilings_by_room = {
    "S.01": (basement_ceiling_s01,),
    "S.02": (basement_ceiling_s02,),
    "S.03": (basement_ceiling_s03,),
    "S.04": (basement_ceiling_s04,),
    "S.05": (basement_ceiling_s05,),
}
basement_ceiling_slabs = tuple(slab for slabs in basement_ceilings_by_room.values() for slab in slabs)
basement_ceiling_coverage_by_room = {
    identifier: unary_union([
        Polygon(slab.footprint).difference(basement_chimney_clearance_region)
        if slab == basement_ceiling_s04 else Polygon(slab.footprint)
        for slab in slabs
    ])
    for identifier, slabs in basement_ceilings_by_room.items()
}
# Finish only the clear room areas beneath the existing ceiling footprints,
# retaining the stair opening, chimney notch and unfinished street-side areas.
basement_ceiling_insulation = []
basement_ceiling_wood = []
for identifier, coverage in basement_ceiling_coverage_by_room.items():
    region = basement_rooms_by_id[identifier].intersection(coverage)
    parts = (region,) if region.geom_type == "Polygon" else region.geoms
    for part_index, part in enumerate(parts, 1):
        if part.area <= 1e-9:
            continue
        outline = tuple(part.exterior.coords)[:-1]
        basement_ceiling_insulation.append(basement_ceiling_storey.floor_layer(
            f"Basement ceiling insulation - {identifier}.{part_index}",
            outline=outline, thickness=BASEMENT_CEILING_INSULATION_THICKNESS,
            start_height=-BASEMENT_CEILING_INSULATION_THICKNESS,
            buildup_material=FLOOR_INSULATION_MATERIAL, color="#ffff80",
        ))
        basement_ceiling_wood.append(basement_ceiling_storey.floor_layer(
            f"Basement ceiling wood - {identifier}.{part_index}",
            outline=outline, thickness=BASEMENT_CEILING_WOOD_THICKNESS,
            start_height=-BASEMENT_CEILING_FINISH_THICKNESS,
            buildup_material="Wood", color="#C8B090",
        ))
        for finish in (basement_ceiling_insulation[-1], basement_ceiling_wood[-1]):
            for hole_index, ring in enumerate(part.interiors, 1):
                add_horizontal_opening(
                    finish, f"{finish.Name} Opening {hole_index}", Polygon(ring),
                    bottom_z=basement_ceiling_storey.elevation+finish.start_height-0.001,
                    height=finish.thickness+0.002,
                )
            object.__setattr__(finish, "area", part.area)
            layer_pset = ifcopenshell.util.element.get_pset(finish, "BBIM_FloorLayer")
            ifcopenshell.api.pset.edit_pset(house.model, pset=house.model.by_id(layer_pset["id"]),
                                          properties={"Area": part.area})
basement_ceiling_insulation = tuple(basement_ceiling_insulation)
basement_ceiling_wood = tuple(basement_ceiling_wood)
basement_ceiling_finishes = (*basement_ceiling_insulation, *basement_ceiling_wood)
basement_ceiling_schedule_rows = [
    {"location": "S.01", "slab": basement_ceiling_s01},
    {"location": "S.02", "slab": basement_ceiling_s02},
    {"location": "S.03", "slab": basement_ceilings_by_room["S.03"]},
    {"location": "S.04", "slab": basement_ceilings_by_room["S.04"]},
    {"location": "S.05", "slab": basement_ceiling_s05},
]


ceiling_slabs = (
    ceiling_garden_rooms, ceiling_room3, ceiling_bathroom,
    ceiling_room3_front, ceiling_bathroom_front, ceiling_stairway,
)
# Actual ground-floor inner wall faces, used by this level's dimensions.
ceiling_wall_bounds = (
    (BWT, GARDEN_ROOMS_WALL_Y+INNER_BWT, HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
    (room3_ceiling_east_face_x, BWT, room3_ceiling_middle_face_x, GARDEN_ROOMS_WALL_Y),
    (bathroom_ceiling_middle_face_x, BWT, bathroom_ceiling_stairway_face_x, GARDEN_ROOMS_WALL_Y),
    (room3_ceiling_east_face_x, BWT, room3_ceiling_middle_face_x, ceiling_front_girder_edge_y),
    (bathroom_ceiling_middle_face_x, BWT, bathroom_ceiling_stairway_face_x, ceiling_front_girder_edge_y),
    (STAIRWAY_WALL_X, BWT, HOUSE_WIDTH-BWT, GARDEN_ROOMS_WALL_Y),
)

ceiling_plan_min, ceiling_plan_max = (0., 0.), (HOUSE_WIDTH, HOUSE_DEPTH)
ceiling_stair_opening_end_y = min(point[1] for point in ceiling_stairway.footprint)
ceiling_schedule_rows = [
    {"location": "0.01, 0.02", "slab": ceiling_garden_rooms},
    {"location": "0.03", "slab": (ceiling_room3, ceiling_room3_front)},
    {"location": "0.04, 0.05", "slab": (ceiling_stairway, ceiling_bathroom, ceiling_bathroom_front)},
]

def add_ceiling_spacing_dimension(drawing, start, end, *, side, index, name):
    """Alternate consecutive spacing dimensions between the two outside lines."""
    distance = CEILING_BEAM_SPACING_OUTSIDE_OFFSETS[index % 2]
    if side == "garden":
        dimension_coordinate = HOUSE_DEPTH+distance
        normal = 1 if end[0] > start[0] else -1
        offset = (dimension_coordinate-start[1])/normal
    else:
        dimension_coordinate = -distance if side == "left" else HOUSE_WIDTH+distance
        normal = 1 if end[1] < start[1] else -1
        offset = (dimension_coordinate-start[0])/normal
    drawing.add_dimension(
        start, end, offset=offset, name=name,
    )


def add_ceiling_beam_spacing_dimensions(drawing, slab, *, side):
    """Dimension consecutive beam centres in each complete slab layout."""
    # Aligned room-3/bathroom rows share one outside spacing chain.
    counterpart = {ceiling_bathroom: ceiling_room3,
                   ceiling_bathroom_front: ceiling_room3_front}.get(slab)
    if counterpart is not None and len(slab.beams) == len(counterpart.beams):
        if all(math.isclose(first[0][1], second[0][1], abs_tol=1e-9)
               for first, second in zip(slab.beam_centerlines, counterpart.beam_centerlines)):
            return
    endpoint = 0 if side == "left" else 1
    lines = slab.beam_centerlines
    for index, (first, second) in enumerate(zip(lines, lines[1:]), 1):
        add_ceiling_spacing_dimension(
            drawing, first[endpoint], second[endpoint], side=side, index=index-1,
            name=f"{slab.Name} Beam Center Distance {index}",
        )


def add_stairway_ceiling_bearing_dimensions(drawing):
    """Dimension the main stairway ceiling's bearings against its wall faces."""
    start, end = ceiling_stairway.beam_centerlines[0]
    drawing.add_dimension(
        start, (stairway_ceiling_stairway_face_x, start[1]), offset=0.65,
        name="Stairway ceiling stairway-wall bearing",
    )
    drawing.add_dimension(
        (stairway_ceiling_west_face_x, end[1]), end, offset=0.65,
        name="Stairway ceiling west-wall bearing",
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
purlin_saddle_center_z = purlin_bottom_z-PURLIN_SADDLE_SIZE[1]/2
purlin_support_top_z = purlin_bottom_z-PURLIN_SADDLE_SIZE[1]
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

# Each post row has separate HEB girders on either side of the middle wall.
purlin_girder_z = UPPER_FLOOR_START-PURLIN_SUPPORT_GIRDER_SIZE[1]/2
purlin_support_girders = []
purlin_support_girder_wall_faces = {}
for index, y in enumerate(sorted({post.start[1] for post in purlin_supports}), 1):
    for room, left_face, right_face in (
        ("0.03", room3_ceiling_east_face_x, room3_ceiling_middle_face_x),
        ("0.05", bathroom_ceiling_middle_face_x, bathroom_ceiling_stairway_face_x),
    ):
        girder = ceiling_storey.girder(
            f"Průvlak pod sloupky vaznic {index} - {room}",
            start=(left_face-PURLIN_SUPPORT_GIRDER_BEARING, y, purlin_girder_z),
            end=(right_face+PURLIN_SUPPORT_GIRDER_BEARING, y, purlin_girder_z),
            width=PURLIN_SUPPORT_GIRDER_SIZE[0], height=PURLIN_SUPPORT_GIRDER_SIZE[1],
            heb=PURLIN_SUPPORT_GIRDER_HEB,
        )
        purlin_support_girders.append(girder)
        purlin_support_girder_wall_faces[girder] = (left_face, right_face)
purlin_support_girders = tuple(purlin_support_girders)


if not math.isfinite(PURLIN_SADDLE_LENGTH) or PURLIN_SADDLE_LENGTH <= 0:
    raise ValueError("PURLIN_SADDLE_LENGTH must be positive and finite")
if purlin_support_top_z <= UPPER_FINISHED_FLOOR_HEIGHT:
    raise ValueError("sedla leave no height for the purlin posts")
purlin_saddles = tuple(
    upper.beam(
        f"Sedlo vaznice {purlin_index}.{support_index}",
        start=(x, y-PURLIN_SADDLE_LENGTH/2, purlin_saddle_center_z),
        end=(x, y+PURLIN_SADDLE_LENGTH/2, purlin_saddle_center_z),
        size=PURLIN_SADDLE_SIZE,
    )
    for purlin_index, (x, positions) in enumerate(zip(PURLIN_X_POSITIONS, PURLIN_SUPPORT_Y_POSITIONS), 1)
    for support_index, y in enumerate(positions, 1)
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
# The side partition steps towards the chimney before the middle masonry wall.
upper_bearing_wall_center_y = (
    wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset+wall_garden_rooms_g.thickness/2
)
living_room_right_wall_y = upper_bearing_wall_center_y
living_room_right_wall_front_y = living_room_right_wall_y-UPPER_BEARING_WALL_THICKNESS/2
living_room_back_face_y = living_room_right_wall_y+UPPER_BEARING_WALL_THICKNESS/2
living_room_return_back_y = living_room_right_wall_front_y-LIVING_ROOM_PARTITION_RETURN_CLEARANCE
living_room_return_y = living_room_return_back_y-DRY_WALL_WIDTH/2
living_room_return_front_y = living_room_return_y-DRY_WALL_WIDTH/2
living_room_chimney_face_x = CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2
living_room_chimney_wall_x = living_room_chimney_face_x+DRY_WALL_WIDTH/2
upper_hallway_living_wall_x = living_room_chimney_face_x+DRY_WALL_WIDTH
living_room_step_towards_west = living_room_chimney_wall_x > living_room_wall_x
living_room_step_y = living_room_return_back_y if living_room_step_towards_west else living_room_return_front_y
upper_hallway_living_step_y = living_room_return_front_y if living_room_step_towards_west else living_room_return_back_y
wall_living_room_side_u = upper.wall(
    (living_room_wall_x, BWT), (living_room_wall_x, living_room_return_y),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
wall_living_room_return_u = upper.wall(
    (living_room_wall_x, living_room_return_y), (living_room_chimney_wall_x, living_room_return_y),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
# Leave the chimney itself exposed on the same plane, rather than putting
# a second drywall volume through its masonry.
wall_living_room_chimney_front_u = upper.wall(
    (living_room_chimney_wall_x, living_room_return_y),
    (living_room_chimney_wall_x, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2),
    wall_type=dry_wall, height=gable_wall_height, cuts=upper_partition_cuts,
)
# The living-room face runs straight from the chimney to the VPC opening's
# garden-side jamb. Horizontal/vertical end cuts keep it out of both solids.
living_room_diagonal_start = np.array((living_room_chimney_face_x, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2))
living_room_diagonal_end = np.array((LIVING_ROOM_OPENING_END_X, living_room_back_face_y))
living_room_diagonal_delta = living_room_diagonal_end-living_room_diagonal_start
if np.any(living_room_diagonal_delta <= 0):
    raise ValueError("the chimney diagonal must lead towards the opening's garden-side jamb")
living_room_diagonal_tangent = living_room_diagonal_delta/np.linalg.norm(living_room_diagonal_delta)
living_room_diagonal_normal = np.array((-living_room_diagonal_tangent[1], living_room_diagonal_tangent[0]))

def living_room_diagonal_living_x(y):
    return float(living_room_diagonal_start[0]+living_room_diagonal_delta[0]
                 *(y-living_room_diagonal_start[1])/living_room_diagonal_delta[1])

def living_room_diagonal_hall_x(y):
    return living_room_diagonal_living_x(y)+DRY_WALL_WIDTH/abs(living_room_diagonal_normal[0])

living_room_diagonal_hall_end_y = living_room_diagonal_end[1]-DRY_WALL_WIDTH/living_room_diagonal_normal[1]
wall_living_room_chimney_back_u = upper.wall(
    tuple(living_room_diagonal_start-living_room_diagonal_normal*DRY_WALL_WIDTH/2-living_room_diagonal_tangent*.2),
    tuple(living_room_diagonal_end-living_room_diagonal_normal*DRY_WALL_WIDTH/2+living_room_diagonal_tangent*.2),
    wall_type=dry_wall, height=gable_wall_height,
    cuts=(*upper_partition_cuts,
          ((0, living_room_diagonal_start[1], 0), (1, living_room_diagonal_start[1], 0), (0, living_room_diagonal_start[1], 1)),
          ((LIVING_ROOM_OPENING_END_X, 0, 0), (LIVING_ROOM_OPENING_END_X, 1, 0), (LIVING_ROOM_OPENING_END_X, 0, 1))),
)
# Above the opening head, the VPC already occupies this part of the wall.
living_room_diagonal_masonry_clearance = ifcopenshell.api.root.create_entity(
    house.model, ifc_class="IfcOpeningElement", predefined_type="OPENING",
    name="Living room diagonal - VPC masonry clearance",
)
living_room_diagonal_clearance_body = ifcopenshell.api.geometry.add_slab_representation(
    house.model, context=house._body_context, depth=gable_wall_height,
    polyline=((living_room_chimney_face_x-.2, living_room_right_wall_front_y),
              (LIVING_ROOM_OPENING_END_X+.2, living_room_right_wall_front_y),
              (LIVING_ROOM_OPENING_END_X+.2, living_room_back_face_y+.2),
              (living_room_chimney_face_x-.2, living_room_back_face_y+.2)),
)
ifcopenshell.api.geometry.assign_representation(house.model, product=living_room_diagonal_masonry_clearance, representation=living_room_diagonal_clearance_body)
ifcopenshell.api.feature.add_feature(house.model, feature=living_room_diagonal_masonry_clearance, element=wall_living_room_chimney_back_u)
living_room_diagonal_clearance_placement = np.eye(4)
living_room_diagonal_clearance_placement[2, 3] = UPPER_FLOOR_START+UPPER_DOOR_TOP_HEIGHT
ifcopenshell.api.geometry.edit_object_placement(house.model, product=living_room_diagonal_masonry_clearance, matrix=living_room_diagonal_clearance_placement, is_si=True)
upper.connect_wall(wall_living_room_side_u, wall_living_room_return_u)
upper.connect_wall(wall_living_room_return_u, wall_living_room_chimney_front_u)
upper_technical_left_x = wall_living_room_side_u.start[0]-wall_living_room_side_u.body_offset
upper_technical_right_x = STAIR_LEFT_X-DRY_WALL_WIDTH
upper_technical_center_x = (upper_technical_left_x+STAIR_LEFT_X)/2
# Leave the configured face-to-face gap behind the west purlin post.
upper_technical_cross_y = UPPER_TECHNICAL_CROSS_Y
upper_technical_cross_front_y = upper_technical_cross_y-DRY_WALL_WIDTH/2
upper_technical_cross_back_y = upper_technical_cross_y+DRY_WALL_WIDTH/2
upper_toilet_end_front_y = upper_technical_cross_back_y+UPPER_TOILET_DEPTH
upper_toilet_end_y = upper_toilet_end_front_y+DRY_WALL_WIDTH/2
upper_toilet_end_back_y = upper_toilet_end_y+DRY_WALL_WIDTH/2
upper_toilet_door_x = upper_technical_left_x+UPPER_TOILET_DOOR_SIDE_CLEARANCE
upper_toilet_door_end_x = upper_toilet_door_x+UPPER_TOILET_DOOR_OPENING_WIDTH
upper_toilet_door_y = upper_toilet_end_y
LIVING_ROOM_WALL_FRONT_Y = living_room_right_wall_front_y
LIVING_ROOM_DEPTH = HOUSE_DEPTH-BWT-living_room_back_face_y
living_room_wall_y = living_room_right_wall_y
# Keep the source-wall centre below the sloped ceiling so the clipping
# retains the wall below it rather than the wedge above the roof plane.
living_room_right_wall_height = min(
    gable_wall_height,
    2*(min(plane_height_at(
        *cut, x=(living_room_wall_x+DRY_WALL_WIDTH/2+HOUSE_WIDTH-BWT)/2,
        y=living_room_right_wall_y,
    ) for cut in upper_partition_cuts)-UPPER_FLOOR_START)-0.01,
)
# One continuous masonry wall replaces both VPC returns and the SDK between them.
# Cut the slopes 50 mm below the rafter tops; keep the cap below the purlins.
upper_bearing_wall_cuts = (
    *(offset_plane(
        *plane.points,
        offset=RAFTER_Z_OFFSET+RAFTER_HEIGHT-UPPER_BEARING_WALL_RAFTER_TOP_CLEARANCE,
    ) for plane in (roof_east, roof_west)),
    gable_masonry_cuts[-1],  # Horizontal plane at the purlin underside.
)
wall_living_room_back_u = upper.wall(
    (BWT, upper_bearing_wall_center_y), (HOUSE_WIDTH-BWT, upper_bearing_wall_center_y),
    wall_type=upper_bearing_wall_type, height=gable_masonry_height, cuts=upper_bearing_wall_cuts,
)
wall_living_room_back_u.Name = f"Upper load-bearing wall - VPC {UPPER_BEARING_WALL_THICKNESS*1000:g} mm"
common = ifcopenshell.api.pset.add_pset(house.model, product=wall_living_room_back_u, name="Pset_WallCommon")
ifcopenshell.api.pset.edit_pset(house.model, pset=common, properties={"LoadBearing": True})
upper_bearing_wall_region = box(
    BWT, living_room_right_wall_front_y, HOUSE_WIDTH-BWT, living_room_back_face_y,
)
# Keep the stair-side face flush with the stairwell edge; thickness is in Technika.
upper_technical_wall_x = STAIR_LEFT_X-DRY_WALL_WIDTH/2
living_room_door_opening_x = HOUSE_WIDTH-BWT-LIVING_ROOM_DOOR_WEST_CLEARANCE-ROOM_DOOR_OPENING_WIDTH
wall_technical_stairway_u = upper.wall(
    (upper_technical_wall_x, upper_technical_cross_front_y),
    (upper_technical_wall_x, upper_toilet_end_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
wall_toilet_end_u = upper.wall(
    (upper_technical_left_x, upper_toilet_end_y),
    (upper_technical_wall_x, upper_toilet_end_y),
    wall_type=dry_wall, height=living_room_right_wall_height, cuts=upper_partition_cuts,
)
upper.connect_wall(wall_technical_stairway_u, wall_toilet_end_u)
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
upper_toilet_door = wall_toilet_end_u.add_door(
    name="Upper toilet door",
    at=upper_toilet_door_x-wall_toilet_end_u.start[0],
    opening_width=UPPER_TOILET_DOOR_OPENING_WIDTH,
    width=UPPER_TOILET_DOOR_WIDTH,
    height=UPPER_DOOR_TOP_HEIGHT,
    clear_height=UPPER_DOOR_CLEAR_HEIGHT,
    sill_height=UPPER_FLOOR_THICKNESS,
    operation="SINGLE_SWING_LEFT",  # Opens north into the hallway, outside 1.04.
)
living_room_door = wall_living_room_back_u.add_door(
    name="Living room door",
    # Measure the construction opening from the west wall's inner face.
    at=living_room_door_opening_x-wall_living_room_back_u.start[0],
    opening_width=ROOM_DOOR_OPENING_WIDTH,
    width=ROOM_DOOR_WIDTH,
    height=UPPER_DOOR_TOP_HEIGHT,
    clear_height=UPPER_DOOR_CLEAR_HEIGHT,
    sill_height=0.0,
    operation="SINGLE_SWING_RIGHT",
)
living_room_opening = wall_living_room_back_u.add_opening(
    name="Living room - kitchen opening",
    at=BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE-wall_living_room_back_u.start[0],
    width=LIVING_ROOM_OPENING_WIDTH,
    plan_mask_width=tuple(
        living_room_diagonal_living_x(y)-(BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE)
        for y in (living_room_right_wall_front_y, living_room_back_face_y)
    ),
    height=UPPER_DOOR_TOP_HEIGHT,
    sill_height=0.0,
)
# Continue the finished floor through this passage between the two parts of 1.01.
upper_bearing_wall_region = upper_bearing_wall_region.difference(box(
    BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE, living_room_right_wall_front_y,
    BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE+LIVING_ROOM_OPENING_WIDTH, living_room_back_face_y,
))
for wall, name in (
    (wall_living_room_side_u, "Living room - side partition"),
    (wall_living_room_return_u, "Living room - chimney return"),
    (wall_living_room_chimney_front_u, "Living room - partition before chimney"),
    (wall_living_room_chimney_back_u, "Living room - diagonal partition after chimney"),
    (wall_technical_stairway_u, "Technika - stairway partition"),
    (wall_toilet_end_u, "Toilet - end partition"),
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
    (living_room_wall_x-DRY_WALL_WIDTH/2, living_room_step_y),
    (living_room_chimney_face_x, living_room_step_y),
    tuple(living_room_diagonal_start),
    tuple(living_room_diagonal_end),
    (HOUSE_WIDTH-BWT, living_room_back_face_y),
    (HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
    (BWT, HOUSE_DEPTH-BWT),
)).difference(upper_bearing_wall_region).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
))
# Both sides retain room 1.01, whether connected through a passage or separate.
living_room_regions = sorted(
    (living_room_outline,) if living_room_outline.geom_type == "Polygon" else living_room_outline.geoms,
    key=lambda region: -region.centroid.y,
)
living_room_floor_parts = tuple(
    upper.floor_layer(
        "Obývací pokoj + KK" if index == 0 else "Obývací pokoj - kuchyňská část",
        room_id="1.01", outline=tuple(region.exterior.coords)[:-1],
        **upper_floor_layer_settings,
    )
    for index, region in enumerate(living_room_regions)
)
living_room = living_room_floor_parts[0]
upper_technical_outline = box(
    upper_technical_left_x, BWT, STAIR_LEFT_X, upper_technical_cross_front_y,
)
upper_technical_room = upper.floor_layer(
    "Technika", room_id="1.02", outline=tuple(upper_technical_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_toilet_outline = box(
    upper_technical_left_x, upper_technical_cross_back_y,
    upper_technical_right_x, upper_toilet_end_front_y,
)
upper_toilet_room = upper.floor_layer(
    "Zachod", room_id="1.04", outline=tuple(upper_toilet_outline.exterior.coords)[:-1],
    **upper_floor_layer_settings,
)
upper_hallway_outline = Polygon((
    (STAIR_LEFT_X, STAIR_UPPER_END_Y),
    (HOUSE_WIDTH-BWT, STAIR_UPPER_END_Y),
    (HOUSE_WIDTH-BWT, living_room_right_wall_front_y),
    (living_room_diagonal_hall_x(living_room_right_wall_front_y), living_room_right_wall_front_y),
    (living_room_diagonal_hall_x(living_room_diagonal_start[1]), living_room_diagonal_start[1]),
    (upper_hallway_living_wall_x, living_room_diagonal_start[1]),
    (upper_hallway_living_wall_x, upper_hallway_living_step_y),
    (upper_technical_left_x, upper_hallway_living_step_y),
    (upper_technical_left_x, upper_toilet_end_back_y),
    (STAIR_LEFT_X, upper_toilet_end_back_y),
)).union(box(
    upper_toilet_door_x, upper_toilet_end_front_y,
    upper_toilet_door_end_x, upper_toilet_end_back_y,
)).union(Polygon((
    (living_room_diagonal_hall_x(living_room_right_wall_front_y), living_room_right_wall_front_y),
    (LIVING_ROOM_OPENING_END_X, living_room_right_wall_front_y),
    (LIVING_ROOM_OPENING_END_X, living_room_diagonal_hall_end_y),
))).difference(box(
    CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2,
    CHIMNEY_CENTER[0]+CHIMNEY_SIZE/2, CHIMNEY_CENTER[1]+CHIMNEY_SIZE/2,
)).difference(upper_bearing_wall_region)
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

# Garden-wall fan coil: centred on the house and above both window heads.
upper_fan_coil_center = (
    HOUSE_WIDTH/2,
    wall_back_u.start[1]-wall_back_u.body_offset-wall_back_u.thickness-FAN_COIL_WALL_GAP-FAN_COIL_SIZE[1]/2,
)
upper_fan_coil_bottom = max(
    float(ifcopenshell.util.placement.get_local_placement(window.ObjectPlacement)[2, 3])+window.OverallHeight
    for window in windows_living_room_back
)-upper.elevation+FAN_COIL_WINDOW_CLEARANCE
upper_fan_coil_ceiling = min(
    plane_height_at(*cut, x=x, y=y)
    for cut in upper_partition_cuts
    for x in (upper_fan_coil_center[0]-FAN_COIL_SIZE[0]/2, upper_fan_coil_center[0]+FAN_COIL_SIZE[0]/2)
    for y in (upper_fan_coil_center[1]-FAN_COIL_SIZE[1]/2, upper_fan_coil_center[1]+FAN_COIL_SIZE[1]/2)
)
if upper.elevation+upper_fan_coil_bottom+FAN_COIL_SIZE[2] > upper_fan_coil_ceiling:
    raise ValueError("Upper garden-wall fan coil does not fit below the ceiling")
upper_fan_coil = upper.fan_coil(
    "Fan coil 1.01 garden wall", center=upper_fan_coil_center, size=FAN_COIL_SIZE,
    start_height=upper_fan_coil_bottom, rotation=0, label="FCU",
)

# Reuse the old house's technical-equipment sizes, with small wall gaps.
upper_fixture_wall_gap = 0.05
# Keep the upper washer fixed when the ground-floor bathroom partition moves.
upper_fixture_front_reference_y = CEILING_ROOM3_SPLIT_Y+0.175  # Retain the former partition face independently of ground-floor wall thickness.
upper_hallway_right_depth = living_room_right_wall_front_y-STAIR_UPPER_END_Y
upper_washing_machine = upper.furniture(
    "Pračka", kind="USERDEFINED", size=(0.7, 0.7, 0.8), color="#ffffff",
    center=(HOUSE_WIDTH-BWT-0.3-upper_fixture_wall_gap-0.35,
            max(STAIR_UPPER_END_Y+upper_hallway_right_depth/4,
                upper_fixture_front_reference_y+upper_fixture_wall_gap+0.35)),
    start_height=UPPER_FLOOR_THICKNESS,
)
# Return the basin to the gardenward half of the hallway beside the washer.
upper_basin_center_x = HOUSE_WIDTH-BWT-0.4-upper_fixture_wall_gap-UPPER_BASIN_SIZE[1]/2
upper_basin_center_y = min(
    STAIR_UPPER_END_Y+3*upper_hallway_right_depth/4,
    living_room_right_wall_front_y-upper_fixture_wall_gap-UPPER_BASIN_SIZE[0]/2,
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
    UPPER_TECHNICAL_CROSS_Y+PURLIN_SUPPORT_SIZE[1]/2+upper_fixture_wall_gap+0.35,
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
# Kitchen on the living-room side of the vertical SDK wall, toward the front.
kitchen_wall_face_x = wall_living_room_side_u.start[0]-(
    wall_living_room_side_u.body_offset+wall_living_room_side_u.thickness
)
kitchen_center_x = kitchen_wall_face_x-KITCHEN_WALL_GAP-KITCHEN_UNIT_SIZE[0]/2
kitchen_cooker_y = upper_bearing_wall_center_y-1.0-KITCHEN_UNIT_SIZE[1]/2
kitchen_sink_y = kitchen_cooker_y-KITCHEN_UNIT_SIZE[1]
kitchen_dishwasher_y = kitchen_sink_y-KITCHEN_UNIT_SIZE[1]
kitchen_fridge_y = kitchen_dishwasher_y-KITCHEN_UNIT_SIZE[1]/2-FRIDGE_SIZE[1]/2
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
kitchen_fridge = upper.furniture(
    "Lednice", kind="USERDEFINED", size=FRIDGE_SIZE,
    center=(kitchen_center_x, kitchen_fridge_y),
    start_height=kitchen_start_height,
)
kitchen_counter_start_y = BWT+KITCHEN_WALL_GAP
kitchen_counter_end_y = kitchen_fridge_y-FRIDGE_SIZE[1]/2
kitchen_counter_length = kitchen_counter_end_y-kitchen_counter_start_y
if kitchen_counter_length <= 0:
    raise ValueError("the kitchen appliances leave no room for a worktop before the front wall")
kitchen_counter = upper.furniture(
    "Kuch.\nLinka", kind="USERDEFINED",
    size=(KITCHEN_UNIT_SIZE[0], kitchen_counter_length, KITCHEN_UNIT_SIZE[2]),
    center=(kitchen_center_x, (kitchen_counter_start_y+kitchen_counter_end_y)/2),
    start_height=kitchen_start_height,
)
kitchen_front_counter_start_x = BWT+KITCHEN_WALL_GAP
kitchen_front_counter_end_x = kitchen_center_x-KITCHEN_UNIT_SIZE[0]/2
kitchen_front_counter = upper.furniture(
    "Kuchyňská linka - přední stěna", label="Kuch.\nLinka", kind="USERDEFINED",
    size=(kitchen_front_counter_end_x-kitchen_front_counter_start_x,
          KITCHEN_UNIT_SIZE[0], KITCHEN_UNIT_SIZE[2]),
    center=((kitchen_front_counter_start_x+kitchen_front_counter_end_x)/2,
            kitchen_counter_start_y+KITCHEN_UNIT_SIZE[0]/2),
    start_height=kitchen_start_height,
)
living_room_dining_table = upper.asset(
    "Jídelní stůl", asset="retail_4_seater_rectangular_table", size=DINING_TABLE_SIZE,
    center=(BWT+DINING_TABLE_WALL_GAP+DINING_TABLE_SIZE[0]/2, kitchen_cooker_y),
    start_height=UPPER_FLOOR_THICKNESS,
)
# Reuse the old seating assets in an L at the garden/east corner.
living_room_sofa = upper.asset(
    "Gauč", asset="3_seater_sofa", size=SOFA_SIZE, rotation=90,
    center=(BWT+SEATING_WALL_GAP+SOFA_SIZE[1]/2,
            HOUSE_DEPTH-BWT-SEATING_WALL_GAP-SOFA_SIZE[0]/2),
    start_height=UPPER_FLOOR_THICKNESS,
)
living_room_armchair = upper.asset(
    "Křeslo", asset="1_seater_sofa", size=ARMCHAIR_SIZE,
    center=(BWT+SEATING_WALL_GAP+SOFA_SIZE[1]+SEATING_GAP+ARMCHAIR_SIZE[0]/2,
            HOUSE_DEPTH-BWT-SEATING_WALL_GAP-ARMCHAIR_SIZE[1]/2),
    start_height=UPPER_FLOOR_THICKNESS,
)
kamna = upper.furniture(
    "Kamna", kind="USERDEFINED", size=STOVE_SIZE, color="#ffff2B",
    center=(kitchen_center_x-0.6, CHIMNEY_CENTER[1]+0.6),
    start_height=UPPER_FLOOR_THICKNESS+0.05,
    rotation=45,  # Front toward the garden / back wall (+Y).
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
# The masonry wall already ends below the purlins; only SDK needs a timber pocket.
cut_roof_layer_at_purlin(wall_technical_cross_u, 1)
add_timber_clearances((wall_living_room_back_u, wall_technical_stairway_u, wall_toilet_end_u, wall_technical_cross_u), purlin_supports)
add_timber_clearances(
    (wall_living_room_side_u, wall_living_room_return_u,
     wall_living_room_chimney_front_u, wall_living_room_chimney_back_u, wall_living_room_back_u,
     wall_technical_stairway_u, wall_toilet_end_u, wall_technical_cross_u,
     *(layer for layer in roof_layers if layer.material_name in
       {"Thermal insulation", "Vapour barrier", "Gypsum plasterboard"})),
    (*purlin_connection_beams, *purlin_saddles, *collar_ties),
)
roof_tiles_top_z = max(
    plane_height_at(
        *offset_plane(*layer.plane.points, offset=layer.z_offset+layer.thickness),
        x=roof_ridge_x, y=HOUSE_DEPTH/2,
    )
    for layer in roof_layers if layer.material_name=="Roof tiles"
)
roof_tiles_lowest_z = min(
    max(ROOF_EAVE_CUT_Z, plane_height_at(
        *offset_plane(*layer.plane.points, offset=layer.z_offset),
        x=east_eave_x if layer.plane is roof_east else west_eave_x,
        y=HOUSE_DEPTH/2,
    ))
    for layer in roof_layers if layer.material_name=="Roof tiles"
)
chimney_top_z = roof_tiles_top_z+CHIMNEY_ABOVE_ROOF
chimney = basement.chimney(
    center=CHIMNEY_CENTER,
    size=CHIMNEY_SIZE,
    height=chimney_top_z-basement.elevation,
    flue_diameter=CHIMNEY_FLUE_DIAMETER,
    start_height=0,
    name="Main chimney",
    material="Chimney",
    color="#B8A99A",
)
chimney_footing = add_chimney_footing(chimney)
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
        for wall in upper_exterior_walls
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


def sewer_fixture_center(fixture):
    """Use the actual plan centre, including library assets with shifted origins."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, fixture)
    vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
    used = np.unique(np.asarray(shape.geometry.faces, dtype=int))
    points = vertices[used, :2]
    return tuple(float(v) for v in (points.min(axis=0)+points.max(axis=0))/2)


def sewer_plan_layout():
    """Shared floor-change coordinates keep the three drainage plans aligned."""
    clearance = SEWER_WALL_CLEARANCE
    sink = sewer_fixture_center(kitchen_sink)
    dishwasher = sewer_fixture_center(kitchen_dishwasher)
    upstairs_toilet = sewer_fixture_center(upper_toilet)
    upstairs_basin = sewer_fixture_center(upper_hallway_basin)
    washing_machine = sewer_fixture_center(upper_washing_machine)
    toilet = sewer_fixture_center(bathroom_toilet)
    basin = sewer_fixture_center(bathroom_basin)
    kitchen_run_x = kitchen_wall_face_x-clearance
    bathroom_street_y = upper_technical_cross_back_y+clearance
    # Use the ground-floor masonry face, rather than the upper SDK.
    stairway_room_face_x = wall_stairway_g.start[0]-(
        wall_stairway_g.body_offset+wall_stairway_g.thickness
    )
    bathroom_run_x = stairway_room_face_x-clearance
    upper_drop = (bathroom_run_x, bathroom_street_y)
    roof_vent = (upstairs_toilet[0], bathroom_street_y)
    west_wall_face_x = wall_west_u.start[0]-(wall_west_u.body_offset+wall_west_u.thickness)
    west_run_x = west_wall_face_x-clearance
    hallway_turn_y = STAIR_UPPER_END_Y-clearance  # Along the street side, outside room 1.03.
    bathroom_drop = (bathroom_run_x, (toilet[1]+basin[1])/2)
    bathroom_corner = (bathroom_run_x, BWT+clearance)
    shower_corner = (BATHROOM_LEFT_X, BWT)
    basement_x0, basement_y0, _, _ = basement_rooms_by_id["S.04"].bounds
    shower_shift = max(basement_x0+clearance-shower_corner[0],
                       basement_y0+clearance-shower_corner[1])
    shower_drop = tuple(value+shower_shift for value in shower_corner)
    outlet = bathroom_corner
    return dict(
        upper_drop=upper_drop, roof_vent=roof_vent,
        bathroom_drop=bathroom_drop, bathroom_corner=bathroom_corner,
        shower_drop=shower_drop, outlet=outlet,
        upper_routes=(
            ("Kitchen sink branch", (sink, (kitchen_run_x, sink[1]))),
            ("Dishwasher branch", (dishwasher, (kitchen_run_x, dishwasher[1]))),
            ("Kitchen vertical run", ((kitchen_run_x, max(sink[1], dishwasher[1], bathroom_street_y)),
                                      (kitchen_run_x, min(sink[1], dishwasher[1], bathroom_street_y)))),
            ("Kitchen to bathroom", ((kitchen_run_x, bathroom_street_y), upper_drop)),
            ("Upper toilet branch", (upstairs_toilet, roof_vent)),
            ("Upper hallway basin branch", (upstairs_basin, (west_run_x, upstairs_basin[1]))),
            ("Upper washing machine branch", (washing_machine, (west_run_x, washing_machine[1]))),
            ("West wall collector", ((west_run_x, max(upstairs_basin[1], washing_machine[1], hallway_turn_y)),
                                     (west_run_x, min(upstairs_basin[1], washing_machine[1], hallway_turn_y)))),
            ("Hallway to upper bathroom", ((west_run_x, hallway_turn_y),
                                           (bathroom_run_x, hallway_turn_y), upper_drop)),
        ),
        ground_routes=(
            ("Shower to basement", (shower_corner, shower_drop)),
            ("Toilet branch", (toilet, (bathroom_run_x, toilet[1]))),
            ("Basin branch", (basin, (bathroom_run_x, basin[1]))),
            ("Bathroom to basement", ((bathroom_run_x, max(toilet[1], basin[1], upper_drop[1])),
                                      (bathroom_run_x, min(toilet[1], basin[1])))),
        ),
        basement_routes=(
            ("Basement collector to down", (bathroom_drop, outlet)),
            ("Shower collector", (shower_drop, (shower_drop[0], bathroom_corner[1]), bathroom_corner)),
        ),
        # Route, segment index, nominal diameter, one-time text offset (metres).
        # Fixture offsets are from the connection point; basement offsets are
        # from the segment midpoint. All offsets are editable for clarity.
        upper_pipe_labels=(
            ("Kitchen sink branch", 0, 50, (0, .20)),
            ("Dishwasher branch", 0, 50, (0, .20)),
            ("Upper toilet branch", 0, 100, (0, .20)),
            ("Upper hallway basin branch", 0, 50, (0, .20)),
            ("Upper washing machine branch", 0, 50, (0, .20)),
        ),
        ground_pipe_labels=(
            ("Shower to basement", 0, 50, (.48, .30)),
            ("Toilet branch", 0, 100, (0, .20)),
            ("Basin branch", 0, 50, (0, -.15)),
        ),
        basement_pipe_labels=(
            ("Shower collector", 1, 50, (0, .14)),
            ("Basement collector to down", 0, 100, (-.35, .05)),
        ),
    )


def water_basement_layout():
    """Shared basement/ground connection, aligned with the bathroom cold-water run."""
    corner = (BATHROOM_RIGHT_X-WATER_WALL_CLEARANCE, BWT+WATER_WALL_CLEARANCE)
    riser = (corner[0], corner[1]+WATER_BASEMENT_RISER_OFFSET_Y)
    return corner, riser


def water_riser_positions():
    """Cold/hot risers shared by the ground and upper water plans."""
    cold = (BATHROOM_RIGHT_X-WATER_WALL_CLEARANCE, BATHROOM_PARTITION_Y-WATER_WALL_CLEARANCE)
    hot = (cold[0]-WATER_HOT_ROUTE_OFFSET, cold[1])
    return cold, hot


def add_plumbing_plan(name, storey, cut_height, room_floors, *, room_positions=None,
                      include_room_legend=True):
    """Bare-wall services plan with room IDs, furniture labels and chimney."""
    drawing = house.add_drawing(
        name, x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=storey.elevation+cut_height, radius=6.5, storeys=[storey],
        door_annotations=False, automatic_plan_annotations=True,
        right_panel_width=60,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    # Facade boards are offset past insulation and otherwise appear as a
    # detached outer contour. Show the same bare masonry at every level.
    for facade in (*perimeter_facades, *wall_facades, *roof_edge_facades):
        drawing.exclude_element(facade)
    for entry in room_floors:
        room = entry[0] if isinstance(entry, tuple) else entry
        position = Polygon(room.outline).representative_point().coords[0]
        position = (room_positions or {}).get(room.room_id, position)
        drawing.add_room_annotation(
            position, identifier=room.room_id, description=room.Name,
            area=living_room_outline.area if room == living_room else room.area,
            show_area=False, name=f"{name} Room {room.room_id}",
        )
    if include_room_legend:
        drawing.add_room_legend()
    drawing.add_chimney_annotation(chimney)
    return drawing


def electrical_board_ports():
    """Clock-positioned outputs on the cabinet perimeter."""
    board_x, board_y = sewer_fixture_center(rozvadec)
    half_width, half_depth = ROZVADEC_SIZE[0]/2, ROZVADEC_SIZE[1]/2
    ports = {}
    for name, clock in ELECTRICAL_OUTPUT_PORT_CLOCKS.items():
        angle = math.radians(90-30*clock)
        dx, dy = math.cos(angle), math.sin(angle)
        distance = min(half_width/abs(dx) if abs(dx)>1e-9 else math.inf,
                       half_depth/abs(dy) if abs(dy)>1e-9 else math.inf)
        ports[name] = (board_x+distance*dx, board_y+distance*dy)
    return ports


def electrical_trunk_layout():
    """Basement bundle beside the chimney; upper bundle in front of the upper bathroom door."""
    ports = electrical_board_ports()
    front_y = CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2-ELECTRICAL_TRUNK_CHIMNEY_CLEARANCE
    half_gap = ELECTRICAL_TRUNK_SEPARATION/2
    down = (CHIMNEY_CENTER[0]-half_gap, front_y)
    up = (ports["upper"][0], CHIMNEY_CENTER[1])
    routes = []
    for name, port, end in (("down", "basement", down), ("up", "upper", up)):
        routes.append((name, (ports[port], end)))
    return dict(down=down, up=up, routes=tuple(routes))


def electrical_ground_fan_coil_layout():
    """Shared circuit branching below the chimney to the four ground-floor FCUs."""
    junction = (CHIMNEY_CENTER[0], CHIMNEY_CENTER[1]-CHIMNEY_SIZE/2-.30)
    routes = [("feed", (electrical_board_ports()["fan_coils"], junction))]
    for unit in (*ground_fan_coils, bathroom_fan_coil):
        placement = ifcopenshell.util.placement.get_local_placement(unit.ObjectPlacement)
        end = tuple(float(v) for v in placement[:2, 3])
        room_id = unit.Name.split()[2]
        if room_id in ("0.01", "0.02"):
            # Approach the garden rooms outside the chimney's masonry.
            side = -1 if room_id == "0.01" else 1
            turn = (CHIMNEY_CENTER[0]+side*(CHIMNEY_SIZE/2+.10), junction[1])
            points = (junction, turn, end)
        else:
            points = (junction, end)
        routes.append((room_id, points))
    return dict(junction=junction, routes=tuple(routes))


def electrical_upper_fan_coil_layout():
    """Receive the shared circuit, clear the chimney on the left, then run north."""
    riser = electrical_ground_fan_coil_layout()["junction"]
    clear_x = CHIMNEY_CENTER[0]-CHIMNEY_SIZE/2-.10
    placement = ifcopenshell.util.placement.get_local_placement(upper_fan_coil.ObjectPlacement)
    # This vertical run meets the room-facing edge of the garden-wall casing.
    end = (clear_x, float(placement[1, 3])-FAN_COIL_SIZE[1]/2)
    return dict(riser=riser, route=(riser, (clear_x, riser[1]), end))


def add_electrical_trunk_legend(drawing, extra_lines=()):
    drawing.add_line_legend([
        {"style": "solid", "color": "black", "line_width": ELECTRICAL_TRUNK_LINE_WIDTH,
         "description": "Sdružená trasa kabelů"},
        *extra_lines,
    ])


def electrical_room01_layout():
    """Room 0.01 branches, with an open counter-clockwise socket route."""
    x0, y0, x1, y1 = Polygon(pokoj1.outline).bounds
    left, bottom = x0+ELECTRICAL_SOCKET_WALL_OFFSET, y0+ELECTRICAL_SOCKET_WALL_OFFSET
    right, top = x1-ELECTRICAL_SOCKET_WALL_OFFSET, y1-ELECTRICAL_SOCKET_WALL_OFFSET
    opening = pokoj1_door.FillsVoids[0].RelatingOpeningElement
    door_left = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])
    door_right = door_left+ROOM_DOOR_OPENING_WIDTH
    ports = electrical_board_ports()
    switch = (door_left-.20, bottom)
    light = electrical_room_centres((pokoj1,))[0][pokoj1.room_id]
    socket_entry = ((door_right+x1)/2, bottom)
    socket_end = (door_left-.40, bottom)
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    return dict(
        lighting=(ports["0.01_light"], switch, light),
        switch=switch,
        socket_feed=(ports["0.01_sockets"], socket_entry),
        socket_perimeter=(socket_entry, (right, bottom), (right, top), (left, top),
                          (left, bottom), socket_end),
        sockets=(
            ("bottom-right right wall", (right, y0+setback), "left", .1125),
            ("top-right right wall", (right, y1-setback), "left", .1125),
            ("top-right top wall", (x1-setback, top), "down", .1125),
            ("top-left top wall", (x0+setback, top), "down", .1125),
            ("top-left left wall", (left, y1-setback), "right", .1125),
            ("bottom-left left wall", (left, y0+setback), "right", .1125),
            ("bottom-left bottom wall", (x0+setback, bottom), "up", .1125),
            ("loop end before door", socket_end, "up", .1125),
        ),
    )


def electrical_room02_layout():
    """Mirror the socket perimeter; keep the switch clear of the open door on its right."""
    x0, y0, x1, y1 = Polygon(pokoj2.outline).bounds
    left, bottom = x0+ELECTRICAL_SOCKET_WALL_OFFSET, y0+ELECTRICAL_SOCKET_WALL_OFFSET
    right, top = x1-ELECTRICAL_SOCKET_WALL_OFFSET, y1-ELECTRICAL_SOCKET_WALL_OFFSET
    opening = pokoj2_door.FillsVoids[0].RelatingOpeningElement
    door_left = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])
    door_right = door_left+ROOM_DOOR_OPENING_WIDTH
    ports = electrical_board_ports()
    switch = (door_right+.20, bottom)
    switch_radius = .075
    light = electrical_room_centres((pokoj2,))[0][pokoj2.room_id]
    socket_entry, socket_end = (left, bottom), (door_right+.40, bottom)
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    return dict(
        lighting=(ports["0.02_light"], switch, light),
        switch=switch, switch_radius=switch_radius,
        socket_feed=(ports["0.02_sockets"], socket_entry),
        socket_perimeter=(socket_entry, (left, top), (right, top), (right, bottom), socket_end),
        sockets=(
            ("bottom-left left wall", (left, y0+setback), "right", .1125),
            ("top-left left wall", (left, y1-setback), "right", .1125),
            ("top-left top wall", (x0+setback, top), "down", .1125),
            ("top-right top wall", (x1-setback, top), "down", .1125),
            ("top-right right wall", (right, y1-setback), "left", .1125),
            ("bottom-right right wall", (right, y0+setback), "left", .1125),
            ("bottom-right bottom wall", (x1-setback, bottom), "up", .1125),
            ("loop end before door", socket_end, "up", .1125),
        ),
    )


def electrical_room03_layout():
    """Clockwise sockets from the wide section; light switched below the narrow-side door."""
    x0, y0, _, y1 = Polygon(pokoj3.outline).bounds
    wide_x = THIRD_ROOM_WALL_X-INNER_BWT
    narrow_x = THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH
    left, bottom = x0+ELECTRICAL_SOCKET_WALL_OFFSET, y0+ELECTRICAL_SOCKET_WALL_OFFSET
    wide_right = wide_x-ELECTRICAL_SOCKET_WALL_OFFSET
    narrow_right = narrow_x-ELECTRICAL_SOCKET_WALL_OFFSET
    wide_top = THIRD_ROOM_STEP_Y-ELECTRICAL_SOCKET_WALL_OFFSET
    top = y1-ELECTRICAL_SOCKET_WALL_OFFSET
    opening = pokoj3_door.FillsVoids[0].RelatingOpeningElement
    door_bottom = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[1, 3])
    door_top = door_bottom+ROOM_DOOR_OPENING_WIDTH
    ports = electrical_board_ports()
    switch = (narrow_right, (wall_third_room_top_g.start[1]+door_bottom)/2)
    light = electrical_room_centres((pokoj3,))[0][pokoj3.room_id]
    socket_entry = (wide_right, wide_top)
    socket_end = (narrow_right, (door_top+y1)/2)
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    # A short shoulder-side branch supplies the second socket at the starting corner.
    shoulder_socket = ((narrow_x+wide_x)/2, wide_top)
    return dict(
        lighting=(ports["0.03_light"], switch, light),
        switch=switch, switch_direction="left",
        socket_feed=(ports["0.03_sockets"], socket_entry),
        socket_perimeter=(shoulder_socket, socket_entry, (wide_right, bottom), (left, bottom),
                          (left, top), (narrow_right, top), socket_end),
        sockets=(
            ("wide top-right shoulder wall", shoulder_socket, "down", .1125),
            ("wide top-right right wall", (wide_right, THIRD_ROOM_STEP_Y-setback), "left", .1125),
            ("bottom-right right wall", (wide_right, y0+setback), "left", .1125),
            ("bottom-right bottom wall", (wide_x-.25, bottom), "up", .1125),
            ("bottom-left bottom wall", (x0+setback, bottom), "up", .1125),
            ("bottom-left left wall", (left, y0+setback), "right", .1125),
            ("top-left left wall", (left, y1-setback), "right", .1125),
            ("top-left top wall", (x0+setback, top), "down", .1125),
            ("narrow top-right top wall", (narrow_x-.75, top), "down", .1125),
            ("loop end above door", socket_end, "left", .1125),
        ),
    )


def electrical_room04_layout():
    """Board to hall light first, then to the hall-side switch beside room 0.02."""
    port = electrical_board_ports()["0.04_light"]
    opening = pokoj2_door.FillsVoids[0].RelatingOpeningElement
    door_right = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])+ROOM_DOOR_OPENING_WIDTH
    wall_y = wall_garden_rooms_g.start[1]+wall_garden_rooms_g.body_offset-ELECTRICAL_SOCKET_WALL_OFFSET
    switch = (door_right+.20, wall_y)
    switch_approach = (switch[0]+.30, switch[1])
    light = electrical_room_centres((chodba,))[0][chodba.room_id]
    return dict(
        lighting=(port, light, switch_approach, switch),
        switch=switch, switch_direction="down",
    )


def electrical_room05_layout():
    """Bathroom perimeter sockets and a light switched beside the door's right jamb."""
    x0, y0, x1, y1 = Polygon(koupelna.outline).bounds
    left, bottom = x0+ELECTRICAL_SOCKET_WALL_OFFSET, y0+ELECTRICAL_SOCKET_WALL_OFFSET
    right, top = x1-ELECTRICAL_SOCKET_WALL_OFFSET, y1-ELECTRICAL_SOCKET_WALL_OFFSET
    ports = electrical_board_ports()
    opening = bathroom_door.FillsVoids[0].RelatingOpeningElement
    door_right = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])+ROOM_DOOR_OPENING_WIDTH
    switch = (door_right+.20, top)
    light_departure = (switch[0]+.30, switch[1])
    light = electrical_room_centres((koupelna,))[0][koupelna.room_id]
    basin = sewer_fixture_center(bathroom_basin)
    tuv = sewer_fixture_center(bathroom_water_heater)
    hydrobox = sewer_fixture_center(bathroom_hydrobox)
    socket_entry, socket_end = (right, top), (left, y1-.40)
    hydrobox_socket_x = min(right-.15, hydrobox[0]+HYDROBOX_SIZE[0]/2+.15)
    return dict(
        lighting=(ports["0.05_light"], switch, light_departure, light),
        switch=switch, switch_direction="down",
        socket_feed=(ports["0.05_sockets"], socket_entry),
        socket_perimeter=(socket_entry, (right, bottom), (left, bottom), socket_end),
        sockets=(
            ("basin", (right, basin[1]), "left", .1125),
            ("TUV", (right, tuv[1]-.25), "left", .1125),
            ("hydrobox", (hydrobox_socket_x, bottom), "up", .1125),
            ("loop end before door", socket_end, "right", .1125),
        ),
    )


def electrical_stair_lighting_layout():
    """Entrance-side switches and a shared ground/upper stair-light continuation."""
    ports = electrical_board_ports()
    opening = entrance_door.FillsVoids[0].RelatingOpeningElement
    door_bottom = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[1, 3])
    west_inner_x = wall_west_g.start[0]-(wall_west_g.body_offset+wall_west_g.thickness)
    wall_x = west_inner_x-ELECTRICAL_SOCKET_WALL_OFFSET
    outside_switch = (wall_x, door_bottom-.20)
    inside_switch = (wall_x, outside_switch[1]-.40)
    outside_approach = (wall_x, outside_switch[1]+.20)
    inside_approach = (wall_x, inside_switch[1]+.20)
    landing_y = (STAIR_LANDING_START_Y+STAIR_LANDING_END_Y)/2
    riser = (wall_x, landing_y)
    outside_light = (
        HOUSE_WIDTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS+ELECTRICAL_ENTRANCE_LIGHT_WALL_GAP,
        door_bottom+ENTRANCE_OPENING_WIDTH/2,
    )
    landing_light = ((STAIR_LEFT_X+STAIR_RIGHT_X)/2, landing_y)
    upper_wall_x = STAIR_LEFT_X+ELECTRICAL_SOCKET_WALL_OFFSET
    upper_switch = (upper_wall_x, STAIR_UPPER_END_Y+.25)
    return dict(
        outside_switch=outside_switch, inside_switch=inside_switch,
        outside_light=outside_light, landing_light=landing_light, riser=riser,
        upper_switch=upper_switch,
        upper_route=(riser, landing_light, (upper_wall_x, landing_y), upper_switch),
        outside_route=(ports["outside_light"], outside_approach, outside_switch, outside_light),
        inside_route=(ports["stair_landing_light"], inside_approach, inside_switch, riser),
    )


def electrical_basement_socket_layout():
    """One shared socket circuit, down the S.04 divider then counter-clockwise."""
    rooms = {identifier: region.bounds for identifier, region in basement_rooms_by_id.items()}
    offset = ELECTRICAL_SOCKET_WALL_OFFSET
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    x0, y0, _, y1 = rooms["S.04"]
    divider_x, front_y = x0+offset, y0+offset
    east_x = rooms["S.03"][0]+offset
    west_x = rooms["S.05"][2]-offset
    garden_y = rooms["S.01"][3]-offset
    origin = electrical_trunk_layout()["down"]
    entry = (divider_x, origin[1]-(origin[0]-divider_x))
    end = (east_x, rooms["S.03"][1]+setback)
    sockets = [
        ("S.04 divider front", (divider_x, y0+setback), "right", .1125),
        ("S.04 divider garden", (divider_x, min(y1-setback, entry[1]-.25)), "right", .1125),
    ]
    for identifier, wall in (("S.05", "front"), ("S.05", "west"),
                             ("S.02", "west"), ("S.02", "garden"),
                             ("S.01", "garden"), ("S.01", "east")):
        x0, y0, x1, y1 = rooms[identifier]
        point, direction = {
            "front": (((x0+x1)/2, front_y), "up"),
            "west": ((west_x, (y0+y1)/2), "left"),
            "garden": (((x0+x1)/2, garden_y), "down"),
            "east": ((east_x, (y0+y1)/2), "right"),
        }[wall]
        sockets.append((f"{identifier} {wall} wall", point, direction, .1125))
    x0, y0, x1, y1 = rooms["S.03"]
    for index, fraction in enumerate((1/3, 2/3), 1):
        sockets.append((f"S.03 east wall {index}", (east_x, y0+(y1-y0)*fraction), "right", .1125))
    return dict(
        socket_feed=(origin, entry),
        socket_perimeter=(entry, (divider_x, front_y), (west_x, front_y),
                          (west_x, garden_y), (east_x, garden_y), end),
        sockets=tuple(sockets),
    )


def electrical_basement_garage_light_layout():
    """8-o'clock garage feed, switch below the S.04 door, then via the front wall."""
    _, front_y, divider_x, _ = basement_rooms_by_id["S.03"].bounds
    wall_x = divider_x-ELECTRICAL_SOCKET_WALL_OFFSET
    front_y += ELECTRICAL_SOCKET_WALL_OFFSET
    origin = electrical_trunk_layout()["down"]
    entry = (wall_x, origin[1]-(origin[0]-wall_x)*math.tan(math.radians(30)))
    opening = basement_garage_door.FillsVoids[0].RelatingOpeningElement
    door_bottom = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[1, 3])
    switch = (wall_x, door_bottom-.20)
    garage_floor = next(room for room in basement_room_floors if room.room_id == "S.03")
    light = electrical_room_centres((garage_floor,))[0]["S.03"]
    return dict(
        lighting=(origin, entry, switch, (wall_x, front_y), (light[0], front_y), light),
        switch=switch, switch_direction="left",
    )


def electrical_basement_s01_light_layout():
    """Diagonal S.01 feed, then along the door wall and up to the existing light."""
    _, bottom, right, _ = basement_rooms_by_id["S.01"].bounds
    bottom += ELECTRICAL_SOCKET_WALL_OFFSET
    # Inset the corner approach so the straight diagonal clears the chimney.
    corner = (right-.30, bottom)
    opening = basement_s01_s03_door.FillsVoids[0].RelatingOpeningElement
    door_right = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])+BASEMENT_OPENING_WIDTH
    switch = (door_right+.20, bottom)
    room = next(room for room in basement_room_floors if room.room_id == "S.01")
    light = electrical_room_centres((room,))[0]["S.01"]
    return dict(
        lighting=(electrical_trunk_layout()["down"], corner, switch, (light[0], bottom), light),
        switch=switch, switch_direction="up",
    )


def electrical_basement_s02_light_layout():
    """S.02 feed via its bottom-left corner, right along the wall, then up."""
    left, bottom, _, _ = basement_rooms_by_id["S.02"].bounds
    bottom += ELECTRICAL_SOCKET_WALL_OFFSET
    corner = (left+.30, bottom)
    origin = electrical_trunk_layout()["down"]
    room = next(room for room in basement_room_floors if room.room_id == "S.02")
    light = electrical_room_centres((room,))[0]["S.02"]
    switch = (light[0], bottom+.20)
    return dict(
        # Approach beside the chimney instead of crossing its masonry.
        lighting=(origin, (corner[0], origin[1]), corner, (light[0], bottom), switch, light),
        switch=switch, switch_direction="right",
    )


def electrical_basement_garden_socket_layout():
    """Outside garden socket, following the S.02 wall closer than its light cable."""
    left, bottom, _, _ = basement_rooms_by_id["S.02"].bounds
    wall_x = left+.16
    origin = electrical_trunk_layout()["down"]
    corner = (wall_x, bottom+ELECTRICAL_SOCKET_WALL_OFFSET)
    socket = (wall_x, float(basement_plan_max[1])+ELECTRICAL_SOCKET_WALL_OFFSET)
    return dict(route=(origin, (wall_x, origin[1]), corner, socket), socket=socket)


def electrical_basement_s04_light_layout():
    """Diagonal to the S.04 light, then down to the switch before the front wall."""
    _, front_y, _, _ = basement_rooms_by_id["S.04"].bounds
    room = next(room for room in basement_room_floors if room.room_id == "S.04")
    light = electrical_room_centres((room,))[0]["S.04"]
    switch = (light[0], front_y+.20)
    return dict(
        lighting=(electrical_trunk_layout()["down"], light, switch),
        switch=switch, switch_direction="left",
    )


def electrical_basement_s05_light_layout():
    """Shallow diagonal through the S.04 opening, down the wall, then right."""
    left, _, _, _ = basement_rooms_by_id["S.05"].bounds
    wall_x = left+ELECTRICAL_SOCKET_WALL_OFFSET
    opening_bottom = float(ifcopenshell.util.placement.get_local_placement(
        basement_stairway_opening.ObjectPlacement,
    )[1, 3])
    entry = (wall_x, opening_bottom+ELECTRICAL_SOCKET_WALL_OFFSET)
    room = next(room for room in basement_room_floors if room.room_id == "S.05")
    light = electrical_room_centres((room,))[0]["S.05"]
    switch = (wall_x, light[1]+.20)
    return dict(
        lighting=(electrical_trunk_layout()["down"], entry, switch, (wall_x, light[1]), light),
        switch=switch, switch_direction="right",
    )


def electrical_basement_three_phase_layout():
    """Red branches from the basement receiving point to the garage and heat pump."""
    origin = electrical_trunk_layout()["down"]
    garage = (basement_rooms_by_id["S.03"].bounds[2]-ELECTRICAL_SOCKET_WALL_OFFSET, origin[1])
    pump = sewer_fixture_center(heat_pump)
    # The down-facing socket's semicircle sits at the heat pump's centre Y.
    pump_socket = (origin[0], pump[1]+.225+.1125)
    return (
        ("Garage", (origin, garage), garage, "left"),
        ("Heat pump", (origin, pump_socket), pump_socket, "down"),
    )


def electrical_upper_living_light_layout():
    """Diagonal feed to the switch, then orthogonal runs to both living-room lights."""
    opening = living_room_door.FillsVoids[0].RelatingOpeningElement
    door_left = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])
    switch = (door_left-.20, living_room_back_face_y+ELECTRICAL_SOCKET_WALL_OFFSET)
    lights = []
    for name, region in (
        ("garden-side", living_room_outline.intersection(box(0, living_room_back_face_y, HOUSE_WIDTH, HOUSE_DEPTH))),
        ("street-side", living_room_outline.intersection(box(0, 0, HOUSE_WIDTH, living_room_right_wall_front_y))),
    ):
        centre = electrical_region_centre(region)
        lights.append((name, (centre.x, centre.y)))
    upper_light, lower_light = lights[0][1], lights[1][1]
    switch_jog = (switch[0]-.30, switch[1])
    upper_turn = (switch_jog[0], upper_light[1])
    lower_branch = (upper_light, (lower_light[0], upper_light[1]), lower_light)
    return dict(
        lighting=(electrical_trunk_layout()["up"], switch, switch_jog, upper_turn, upper_light),
        lighting_branches=(("lower light", lower_branch),),
        switch=switch, switch_direction="up", lights=tuple(lights),
    )


def electrical_upper_living_garden_socket_layout():
    """First 1.01 socket circuit: 60-degree feed and an open garden-side perimeter."""
    region = living_room_outline.intersection(box(0, living_room_back_face_y, HOUSE_WIDTH, HOUSE_DEPTH))
    x0, y0, x1, y1 = region.bounds
    left, bottom = x0+ELECTRICAL_SOCKET_WALL_OFFSET, y0+ELECTRICAL_SOCKET_WALL_OFFSET
    right, top = x1-ELECTRICAL_SOCKET_WALL_OFFSET, y1-ELECTRICAL_SOCKET_WALL_OFFSET
    origin = electrical_trunk_layout()["up"]
    entry = (origin[0]+(bottom-origin[1])/math.tan(math.radians(60)), bottom)
    opening_left = float(ifcopenshell.util.placement.get_local_placement(living_room_opening.ObjectPlacement)[0, 3])
    end = (opening_left-.40, bottom)
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    return dict(
        socket_feed=(origin, entry),
        socket_perimeter=(entry, (right, bottom), (right, top), (left, top), (left, bottom), end),
        sockets=(
            ("garden bottom-right bottom wall", (x1-setback, bottom), "up", .1125),
            ("garden bottom-right right wall", (right, y0+setback), "left", .1125),
            ("garden top-right right wall", (right, y1-setback), "left", .1125),
            ("garden top-right top wall", (x1-setback, top), "down", .1125),
            ("garden top-left top wall", (x0+setback, top), "down", .1125),
            ("garden top-left left wall", (left, y1-setback), "right", .1125),
            ("garden bottom-left left wall", (left, y0+setback), "right", .1125),
            ("garden bottom-left bottom wall", (x0+setback, bottom), "up", .1125),
        ),
    )


def electrical_upper_living_street_socket_layout():
    """Second 1.01 socket circuit along the kitchen, front and east walls."""
    offset = ELECTRICAL_SOCKET_WALL_OFFSET
    left, bottom = BWT+offset, BWT+offset
    right = kitchen_wall_face_x-offset
    wall_entry = (right, living_room_return_front_y-.20)
    end = (left, living_room_right_wall_front_y-offset)
    dishwasher = sewer_fixture_center(kitchen_dishwasher)
    fridge = sewer_fixture_center(kitchen_fridge)
    setback = ELECTRICAL_SOCKET_CORNER_DISTANCE
    front_start, front_end = BWT+setback, kitchen_wall_face_x-setback
    return dict(
        socket_feed=(electrical_trunk_layout()["up"], wall_entry),
        socket_perimeter=(wall_entry, (right, bottom), (left, bottom), end),
        sockets=(
            ("dishwasher", (right, dishwasher[1]), "left", .1125),
            ("fridge", (right, fridge[1]), "left", .1125),
            *((f"front wall {index+1}", (float(x), bottom), "up", .1125)
              for index, x in enumerate(np.linspace(front_start, front_end, 5))),
            ("corner before VPC", (left, living_room_right_wall_front_y-setback), "right", .1125),
            ("east wall below corner", (left, living_room_right_wall_front_y-setback-2.0), "right", .1125),
        ),
    )


def electrical_upper_cooker_layout():
    """Separate three-phase cooker feed, using the old house's red convention."""
    origin = electrical_trunk_layout()["up"]
    diagonal = (origin[0]-.20, origin[1]+.20)
    cooker = sewer_fixture_center(kitchen_cooker)
    socket = (kitchen_wall_face_x-ELECTRICAL_SOCKET_WALL_OFFSET-.14, cooker[1])
    return dict(route=(origin, diagonal, (socket[0], diagonal[1]), socket), socket=socket)


def electrical_upper_hallway_layout():
    """Approach the VPC wall at 45 degrees; retain the diagonal light/switch branches."""
    origin = electrical_trunk_layout()["up"]
    stairs_switch = electrical_stair_lighting_layout()["upper_switch"]
    switch = (stairs_switch[0], stairs_switch[1]+.40)
    light = electrical_room_centres((upper_hallway,))[0][upper_hallway.room_id]
    opening = living_room_door.FillsVoids[0].RelatingOpeningElement
    door_right = float(ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)[0, 3])+ROOM_DOOR_OPENING_WIDTH
    door_switch = (door_right+.20, living_room_right_wall_front_y-ELECTRICAL_SOCKET_WALL_OFFSET)
    door_approach = (door_switch[0]+.30, door_switch[1])
    wall_rise = door_switch[1]-origin[1]
    wall_entry = (origin[0]+wall_rise, door_switch[1])
    socket_wall_y = door_switch[1]-.10
    socket_wall_entry = (origin[0]+(socket_wall_y-origin[1])/math.tan(math.radians(30)), socket_wall_y)
    west_inner_x = wall_west_u.start[0]-(wall_west_u.body_offset+wall_west_u.thickness)
    socket_wall_x = west_inner_x-ELECTRICAL_SOCKET_WALL_OFFSET
    basin = sewer_fixture_center(upper_hallway_basin)
    washer = sewer_fixture_center(upper_washing_machine)
    socket_end = (socket_wall_x, min(basin[1], washer[1]))
    return dict(
        lighting=(origin, wall_entry, door_switch), switch=switch, switch_direction="right",
        lighting_branches=(("stair switch", (light, switch)),
                           ("living-room door switch", (light, door_approach, door_switch))),
        extra_switches=(("living-room door", door_switch, "down"),),
        socket_feed=(origin, socket_wall_entry, (socket_wall_x, socket_wall_y), socket_end),
        sockets=(("basin", (socket_wall_x, basin[1]), "left", .1125),
                 ("washing machine", (socket_wall_x, washer[1]), "left", .1125)),
    )


def electrical_upper_toilet_layout():
    """Upper bathroom lighting via a switch near its top-left corner."""
    x0, _, _, y1 = Polygon(upper_toilet_room.outline).bounds
    switch = (x0+ELECTRICAL_SOCKET_WALL_OFFSET, y1-.20)
    light = electrical_room_centres((upper_toilet_room,))[0][upper_toilet_room.room_id]
    origin = electrical_trunk_layout()["up"]
    wall_entry = (switch[0], origin[1])
    return dict(
        lighting=(origin, wall_entry, switch, light),
        switch=switch, switch_direction="right",
    )


def electrical_upper_technical_socket_layout():
    """Double 1.02 socket via the inside face of room 1.04's right wall."""
    _, front_y, _, _ = Polygon(upper_technical_room.outline).bounds
    _, _, right_x, top_y = Polygon(upper_toilet_room.outline).bounds
    wall_x = right_x-ELECTRICAL_SOCKET_WALL_OFFSET
    wall_entry = (wall_x, top_y-.20)
    socket = (wall_x, front_y+ELECTRICAL_SOCKET_WALL_OFFSET)
    return dict(route=(electrical_trunk_layout()["up"], wall_entry, socket), socket=socket)


def add_ground_stair_lighting_routes(drawing, layout):
    for name in ("outside", "inside"):
        drawing.add_poly_line(
            layout[f"{name}_route"], color=ELECTRICAL_LIGHT_CIRCUIT_COLOR,
            line_width=ELECTRICAL_LINE_WIDTH, foreground=True,
            name=f"{drawing.name} {name.capitalize()} stair light cable",
        )
        drawing.add_switch_symbol(
            layout[f"{name}_switch"], "left", line_width=ELECTRICAL_LINE_WIDTH,
            name=f"{drawing.name} {name.capitalize()} stair light switch",
        )
    drawing.add_change_floor_symbol(
        *layout["riser"], "to up", color="black", line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH,
        name=f"{drawing.name} Stair light to upper floor",
    )


def add_room_electrical_routes(drawing, identifier, layout):
    prefix = f"{drawing.name} Room {identifier}"
    drawing.add_poly_line(
        layout["lighting"], color=ELECTRICAL_LIGHT_CIRCUIT_COLOR, line_width=ELECTRICAL_LINE_WIDTH,
        foreground=True,
        name=f"{prefix} light cable",
    )
    for name, points in layout.get("lighting_branches", ()):
        drawing.add_poly_line(
            points, color=ELECTRICAL_LIGHT_CIRCUIT_COLOR, line_width=ELECTRICAL_LINE_WIDTH,
            foreground=True, name=f"{prefix} {name} cable",
        )
    drawing.add_switch_symbol(
        layout["switch"], layout.get("switch_direction", "up"), radius=layout.get("switch_radius", .075),
        line_width=ELECTRICAL_LINE_WIDTH,
        name=f"{prefix} light switch",
    )
    for name, point, direction in layout.get("extra_switches", ()):
        drawing.add_switch_symbol(
            point, direction, line_width=ELECTRICAL_LINE_WIDTH,
            name=f"{prefix} {name} light switch",
        )
    add_room_socket_routes(drawing, identifier, layout)


def add_room_socket_routes(drawing, identifier, layout):
    prefix = f"{drawing.name} Room {identifier}"
    for name, key in (("socket feed", "socket_feed"), ("socket perimeter", "socket_perimeter")):
        points = layout.get(key)
        if points is None:
            continue
        drawing.add_poly_line(
            points, color="blue", line_width=ELECTRICAL_LINE_WIDTH,
            foreground=True,
            name=f"{prefix} {name}",
        )
    for name, point, direction, radius in layout.get("sockets", ()):
        drawing.add_socket_symbol(
            point, direction, double=True, radius=radius, line_width=ELECTRICAL_LINE_WIDTH,
            name=f"{prefix} double socket {name}",
        )


def electrical_region_centre(region, offset=(0.0, 0.0)):
    """Keep a light near an area's centre with space for its full symbol."""
    centre = region.centroid
    centre = Point(centre.x+offset[0], centre.y+offset[1])
    clear_region = region.buffer(-.25)
    if not clear_region.is_empty and not clear_region.covers(centre):
        centre = nearest_points(clear_region, centre)[0]
    elif not region.contains(centre):
        centre = region.representative_point()
    return centre


def electrical_room_centres(room_floors):
    """Place lights near room centroids with clearance for the full symbol."""
    centres, labels = {}, {}
    for entry in room_floors:
        room = entry[0] if isinstance(entry, tuple) else entry
        region = living_room_outline if room == living_room else Polygon(room.outline)
        centre = electrical_region_centre(region, ELECTRICAL_LIGHT_OFFSETS.get(room.room_id, (0.0, 0.0)))
        centres[room.room_id] = (centre.x, centre.y)
        # Keep the room ID clear of its light symbol, including small rooms.
        label_dx, label_dy = ELECTRICAL_ROOM_LABEL_OFFSETS.get(room.room_id, (0.0, 0.0))
        for dx, dy in ((0, -.40), (0, .40), (.40, 0), (-.40, 0)):
            label = Point(centre.x+dx+label_dx, centre.y+dy+label_dy)
            if region.contains(label):
                labels[room.room_id] = (label.x, label.y)
                break
    return centres, labels


def add_electrical_plan(name, storey, cut_height, room_floors, *, skip_lights=(), extra_symbols=()):
    centres, labels = electrical_room_centres(room_floors)
    drawing = add_plumbing_plan(
        name, storey, cut_height, room_floors, room_positions=labels,
        include_room_legend=True,
    )
    drawing.add_symbol_legend([("light", "Světlo"), *extra_symbols])
    for identifier, centre in centres.items():
        if identifier in skip_lights:
            continue
        drawing.add_light_symbol(
            centre, color="blue", line_width=ELECTRICAL_LINE_WIDTH,
            name=f"{name} Room {identifier} light",
        )
    return drawing


def add_sewer_routes(drawing, routes):
    for name, points in routes:
        drawing.add_poly_line(points, color="orange", line_width=SEWER_LINE_WIDTH,
                              name=f"{drawing.name} {name}")


def add_sewer_pipe_labels(drawing, routes, labels, *, at_start=False):
    """Place nominal pipe sizes near the selected branch or collector segment."""
    routes_by_name = dict(routes)
    for route_name, segment, diameter, offset in labels:
        points = routes_by_name[route_name]
        anchor = np.asarray(points[segment]) if at_start else (np.asarray(points[segment])+points[segment+1])/2
        position = anchor+offset
        drawing.add_text(
            tuple(float(value) for value in position), f"DN{diameter}", font_size=2.2,
            name=f"{drawing.name} {route_name} DN{diameter}",
        )


def add_sewer_floor_change(drawing, point, direction, name):
    drawing.add_change_floor_symbol(
        *point, direction, color="black", line_width=SEWER_LINE_WIDTH,
        name=f"{drawing.name} {name}",
    )


if "basement" in sys.argv:
    drawing1 = house.add_drawing(
        "basement", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        # Keep the cut just above the heat pump's coplanar bottom/plan footprint.
        z=BASEMENT_FINISHED_FLOOR_HEIGHT+1.01,
        radius=7, storeys=[basement], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=True,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("ztracene-bedneni", f"Ztracené bednění {BASEMENT_WALL_THICKNESS*1000:.0f} mm"),
        ("perimeter-polystyrene", f"Perimetrická izolace {EXTERIOR_XPS_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_perimeter_insulation(drawing1)
    drawing1.add_notes([
        "Prostor pro budoucí schodiště; schodiště není součástí současného návrhu.",
    ])
    for room in basement_rooms:
        region = room["region"]
        x0, y0, x1, y1 = region.bounds
        position = region.representative_point().coords[0]
        # Keep the centre room's symbol clear of the AA section line.
        if abs(position[0]-aa_cut.center[0]) < 0.4:
            position = (min(x1-0.45, position[0]+0.45), position[1])
        if room["identifier"] == "S.04":
            position = (position[0], position[1]-0.6)
        elif room["identifier"] == "S.05":
            position = (position[0]+0.45, position[1]-1.0)
        drawing1.add_room_annotation(
            position, identifier=room["identifier"], description=room["name"], area=region.area,
        )
        inset = min(0.7, (x1-x0)/3, (y1-y0)/3)
        if room["identifier"] in ("S.01", "S.02"):
            width_inset = 1.15 if room["identifier"] == "S.01" else 1.0
            width_y = y1-min(width_inset, (y1-y0)/3)
        elif room["identifier"] == "S.05":
            width_y = y0+inset
        elif room["identifier"] == "S.03":
            width_y = y0+min(0.9, (y1-y0)/3)
        else:
            width_y = y0+min(1.2, (y1-y0)/3)
        depth_x = x1+0.45 if room["identifier"] == "S.05" else x0+inset
        if room["identifier"] == "S.02":
            depth_x = x0+1.2
        width_dimension = drawing1.add_dimension(
            start=(x0, width_y), end=(x1, width_y),
            name=f"{room['identifier']} clear width",
        )
        if room["identifier"] == "S.04":
            appearance = ifcopenshell.api.pset.add_pset(
                house.model, product=width_dimension, name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                house.model, pset=appearance, properties={"Classes": "fill-bg"},
            )
        drawing1.add_dimension(
            start=(depth_x, y0), end=(depth_x, y1),
            name=f"{room['identifier']} clear depth",
			offset=0.7
        )
    drawing1.add_room_legend()
    basement_opening_widths = {}
    for opening, offset in (
        (basement_garage_door, 1.15),
        (basement_s01_s03_door, 1.0),
        (basement_stairway_opening, -1.0),
        (basement_garden_opening, 1.0),
        (basement_storage_opening, -0.55),
        (garage_front_opening, +0.40),
        (basement_s05_front_door, -0.7),
    ):
        dimension = drawing1.add_opening_dimension(
            opening, offset=offset, finished_floor_height=BASEMENT_FLOOR_THICKNESS,
        )
        basement_opening_widths[opening] = ifcopenshell.util.element.get_pset(
            dimension, "BBIM_OpeningDimension", "Width",
        )
    # Dimension actual construction jambs from the clear faces of the adjacent room.
    for opening, identifier, side, offset in (
        (garage_front_opening, "S.03", "street", 0.4),
        (basement_s05_front_door, "S.04", "street", 0.4),
        (basement_s01_s03_door, "S.03", "garden", -0.4),
        (basement_garden_opening, "S.05", "garden", -0.4),
        (basement_garage_door, "S.03", "west", 1.0),
        (basement_stairway_opening, "S.05", "east", -0.85),
        (basement_storage_opening, "S.02", "east", -0.4),
    ):
        void = opening.FillsVoids[0].RelatingOpeningElement if opening.is_a("IfcDoor") else opening
        placement = ifcopenshell.util.placement.get_local_placement(void.ObjectPlacement)
        axis = 0 if side in ("street", "garden") else 1
        jamb0, jamb1 = sorted(
            float((placement @ np.array((x, 0., 0., 1.)))[axis])
            for x in (0., basement_opening_widths[opening])
        )
        bounds = basement_rooms_by_id[identifier].bounds
        face = bounds[{"street": 1, "garden": 3, "east": 0, "west": 2}[side]]
        labels = ("east", "west") if axis == 0 else ("street", "garden")
        for first, last, label in (
            (bounds[axis], jamb0, labels[0]),
            (jamb1, bounds[axis+2], labels[1]),
        ):
            start, end = ((first, face), (last, face)) if axis == 0 else ((face, first), (face, last))
            dimension = drawing1.add_dimension(
                start, end, offset=offset,
                name=f"{identifier} {opening.Name} clearance to {label} wall",
            )
            appearance = ifcopenshell.api.pset.add_pset(
                house.model, product=dimension, name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                house.model, pset=appearance, properties={"Classes": "fill-bg"},
            )
    drawing1.add_lintel(basement_garage_door, 1, position="after", direction="in")
    drawing1.add_lintel(basement_s01_s03_door, 1, direction="in")
    drawing1.add_lintel(basement_stairway_opening, 1, direction="in")
    drawing1.add_lintel(basement_garden_opening, 1, direction="in")
    drawing1.add_lintel(basement_storage_opening, 1, position="after", direction="in")
    drawing1.add_lintel(garage_front_opening, 2)
    drawing1.add_lintel(basement_s05_front_door, 1)
    drawing1.add_lintel_legend()
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
    drawing1.add_chimney_annotation(chimney)
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
        ground_load_bearing_walls, style="dashed", color="blue",
        name="Ground-floor load-bearing wall outlines",
    )
    chimney_half = chimney.size/2
    chimney_corners = tuple(
        (chimney.center[0]+dx*chimney_half, chimney.center[1]+dy*chimney_half)
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )
    chimney_outline = drawing1.add_poly_line(
        (*chimney_corners, chimney_corners[0]), style="dashed", color="green",
        line_width=.15, name="Chimney outline above footing",
    )
    # The common plan style hides individual footing cut edges to avoid
    # junction seams. Draw the boundary of their actual merged footprints.
    chimney_footing_half = chimney.size/2+CHIMNEY_FOOTING_OVERHANG
    footing_polygons = [box(
        chimney.center[0]-chimney_footing_half, chimney.center[1]-chimney_footing_half,
        chimney.center[0]+chimney_footing_half, chimney.center[1]+chimney_footing_half,
    )]
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
        (ground_wall_outline, "Obrys nosných stěn 1.NP"),
        (chimney_outline, "Obrys komína"),
        (grounding_ring, "Zemnící pásovina FeZn 30/35"),
    ])
    drawing1.add_material_legend([
        ("solid-white", f"Betonové základové pasy\n{FOUNDATION_FOOTING_WIDTH*1000:.0f} × {FOUNDATION_FOOTING_HEIGHT*1000:.0f} mm"),
        ("solid-white", f"Základ pod komín\n{2*chimney_footing_half*1000:.0f} × {2*chimney_footing_half*1000:.0f} × {FOUNDATION_FOOTING_HEIGHT*1000:.0f} mm"),
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
        ("diagonal1", f"Příčka - VPC Cihla {GARDEN_PARTITION_THICKNESS*1000:g} mm"),
        ("drywall-diagonal1", f"Příčka - SDK {DRY_WALL_WIDTH*1000:g} mm"),
        ("wooden-wall", "Dřevěná stěna"),
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1)
    add_ground_room_annotations(drawing1)
    # Only openings in load-bearing masonry need lintel tags. The Pokoj 3
    # and bathroom doors are in drywall partitions and are omitted.
    drawing1.add_lintel(entrance_door, 1)
    drawing1.add_lintel(pokoj1_door, 2, direction="in")
    drawing1.add_lintel(pokoj2_door, 2, position="after", direction="in")
    drawing1.add_lintel(bathroom_left_opening, 3, direction="in")
    drawing1.add_lintel(stairway_opening, 3, position="after")
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
    # Along Y to a point 100 mm gardenward of the street-side entrance jamb.
    entrance_opening_street_y = wall_west_g.start[1]+ENTRANCE_OPENING_AT
    drawing1.add_dimension(
        start=(STAIR_RIGHT_X, lower_stairs.start[1]+0.02),
        end=(STAIR_RIGHT_X, entrance_opening_street_y+0.08), offset=0.35,
        name="Ground stairway clearance to entrance opening plus 100 mm",
    )
    drawing1.add_notes([
        ("Hlavní:", stairway_notes),
        ("Vstupní:", entrance_stairway_notes),
    ], title="SCHODIŠTĚ")
    drawing1.add_stair_annotation(entrance_stairs)
    drawing1.add_stair_landing_annotation(entrance_landing)
    drawing1.add_poly_line(
        (entrance_stairs.start, entrance_stairs.end), arrow_end=True, circle_start=True,
        name="Entrance stair walking route",
    )
    drawing1.add_opening_dimension(entrance_door, offset=-1.6, finished_floor_height=GROUND_FLOOR_THICKNESS)
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT, wall_front_g.start[1]+wall_front_g.body_offset+wall_front_g.thickness),
        end=(HOUSE_WIDTH-BWT, entrance_opening_street_y), offset=-1.45,
        name="Entrance opening clearance from front wall",
    )
    drawing1.add_opening_dimension(
        pokoj1_door, offset=1.5, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        pokoj2_door, offset=1.5, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    room3_door_dimension = drawing1.add_opening_dimension(
        pokoj3_door, offset=1.0, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        bathroom_door, offset=0.4, finished_floor_height=GROUND_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        bathroom_left_opening,
        offset=wall_third_room_g.body_offset+wall_third_room_g.thickness/2,
        finished_floor_height=GROUND_FLOOR_THICKNESS,
        name="Ground Pokoj 3 to hallway opening",
    )
    drawing1.add_opening_dimension(
        stairway_opening,
        offset=wall_stairway_g.body_offset+wall_stairway_g.thickness/2,
        finished_floor_height=GROUND_FLOOR_THICKNESS,
        name="Ground hallway to stairway opening",
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
        start=(BWT+0.5, GARDEN_ROOMS_WALL_Y+INNER_BWT),
        end=(BWT+0.5, HOUSE_DEPTH-BWT),
    )
	# delka leva zahradni mistnost
    drawing1.add_dimension(
        start=(BWT, HOUSE_DEPTH-BWT-0.95),
        end=(HOUSE_WIDTH/2-GARDEN_PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT-0.95),
        name="Pokoj 1 clear width",
    )
	# delka prava zahradni mistnost
    drawing1.add_dimension(
        start=(HOUSE_WIDTH/2+GARDEN_PARTITION_THICKNESS/2, HOUSE_DEPTH-BWT-0.95),
        end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-0.95),
        name="Pokoj 2 clear width",
    )
	# delka tretiho pokoje
    drawing1.add_dimension(
        start=(BWT, BWT+1.0), end=(THIRD_ROOM_WALL_X-INNER_BWT, BWT+1.0),
        name="Pokoj 3 clear width",
    )
    # Resolve jambs from the actual openings, including the reversed back wall.
    room_window_x_bounds = {}
    for window in (window_pokoj1, window_pokoj2, window_pokoj3, window_koupelna):
        opening = window.FillsVoids[0].RelatingOpeningElement
        placement = ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)
        room_window_x_bounds[window] = sorted(
            float((placement @ np.array((x, 0., 0., 1.)))[0])
            for x in (0., window.OverallWidth)
        )
    garden_left_x0, garden_left_x1 = room_window_x_bounds[window_pokoj1]
    garden_right_x0, garden_right_x1 = room_window_x_bounds[window_pokoj2]
    garden_opening_wall_y = HOUSE_DEPTH-BWT
    for x0, x1, name in (
        (BWT, garden_left_x0, "Pokoj 1 window to east wall"),
        (garden_left_x1, garden_right_x0, "Garden window opening gap"),
        (garden_right_x1, HOUSE_WIDTH-BWT, "Pokoj 2 window to west wall"),
    ):
        dimension = drawing1.add_dimension(
            (x0, garden_opening_wall_y), (x1, garden_opening_wall_y), offset=-0.4, name=name,
        )
        if name == "Garden window opening gap":
            # The centred label crosses the partition hatch.
            appearance = ifcopenshell.api.pset.add_pset(
                house.model, product=dimension, name="EPset_Annotation",
            )
            ifcopenshell.api.pset.edit_pset(
                house.model, pset=appearance, properties={"Classes": "fill-bg"},
            )
    room3_window_x0, room3_window_x1 = room_window_x_bounds[window_pokoj3]
    room3_opening_wall_y = BWT
    for x0, x1, name in (
        (BWT, room3_window_x0, "Pokoj 3 window to east wall"),
        (room3_window_x1, THIRD_ROOM_WALL_X-INNER_BWT, "Pokoj 3 window to middle wall"),
    ):
        drawing1.add_dimension(
            (x0, room3_opening_wall_y), (x1, room3_opening_wall_y), offset=0.4, name=name,
        )
    bathroom_window_x0, bathroom_window_x1 = room_window_x_bounds[window_koupelna]
    for x0, x1, name in (
        (BATHROOM_LEFT_X, bathroom_window_x0, "Bathroom window to room 3 wall"),
        (bathroom_window_x1, BATHROOM_RIGHT_X, "Bathroom window to stairway wall"),
    ):
        dimension = drawing1.add_dimension(
            (x0, BWT), (x1, BWT), offset=0.4, name=name,
        )
        # Keep the values readable over the shower and hot-water tank labels.
        appearance = ifcopenshell.api.pset.add_pset(
            house.model, product=dimension, name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            house.model, pset=appearance, properties={"Classes": "fill-bg"},
        )
    # Clear width and depth of Pokoj 3's narrowed garden-side end.
    drawing1.add_dimension(
        start=(BWT, THIRD_ROOM_STEP_Y+0.1),
        end=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y+0.1),
    )
    room3_narrow_depth_dimension = drawing1.add_dimension(
        start=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, THIRD_ROOM_STEP_Y),
        end=(THIRD_ROOM_NARROW_WALL_X-DRY_WALL_WIDTH, GARDEN_ROOMS_WALL_Y),
        offset=1.5, name="Pokoj 3 narrow section depth",
    )
    for dimension in (room3_door_dimension, room3_narrow_depth_dimension):
        appearance = ifcopenshell.api.pset.add_pset(
            house.model, product=dimension, name="EPset_Annotation",
        )
        ifcopenshell.api.pset.edit_pset(
            house.model, pset=appearance, properties={"Classes": "fill-bg"},
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
        start=(BATHROOM_LEFT_X, BWT+1.0),
        end=(BATHROOM_RIGHT_X, BWT+1.0),
        name="Bathroom clear width",
    )

    drawing1.add_chimney_annotation(chimney)
    drawing1.add_dimension(
        start=(chimney.center[0]+chimney.size/2, chimney.center[1]),
        end=(BATHROOM_RIGHT_X, chimney.center[1]),
        name="Ground chimney clearance to stairway wall",
    )
    drawing1.add_dimension(
        start=(chimney.center[0]+chimney.size/2, chimney.center[1]-chimney.size/2),
        end=(chimney.center[0]+chimney.size/2,
             wall_bathroom_partition_g.start[1]+wall_bathroom_partition_g.body_offset
             +wall_bathroom_partition_g.thickness),
        offset=-0.2, name="Ground chimney clearance to bathroom drywall",
    )
    if SHOW_PURLIN_SUPPORT_PLANNING_MARKERS:
        add_purlin_support_planning_markers(drawing1)
        # Project the upstairs stove for planning, following its actual rotation.
        stove_placement = ifcopenshell.util.placement.get_local_placement(kamna.ObjectPlacement)
        stove_corners = [
            tuple((stove_placement @ np.array((x, y, 0., 1.)))[:2])
            for x, y in ((-STOVE_SIZE[0]/2, -STOVE_SIZE[1]/2),
                         (STOVE_SIZE[0]/2, -STOVE_SIZE[1]/2),
                         (STOVE_SIZE[0]/2, STOVE_SIZE[1]/2),
                         (-STOVE_SIZE[0]/2, STOVE_SIZE[1]/2))
        ]
        drawing1.add_poly_line(
            (*stove_corners, stove_corners[0]), color="#2e7d32",
            name="Upper-floor stove planning footprint",
        )
        drawing1.add_text(
            tuple(stove_placement[:2, 3]), "Kamna", font_size=1.7, color="#2e7d32",
            name="Upper-floor stove planning label",
        )
    add_house_cut_symbols(drawing1)
    # Keep the legends on A4 at 1:100.
    drawing1.render(PROJECT_DIR / "ground.svg", pdf=PDF_GROUND, margin=8)

if "ceiling" in sys.argv:
    drawing1 = house.add_drawing(
        "ceiling", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=ceiling_storey.elevation+CEILING_THICKNESS+0.1,
        radius=7, storeys=[], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
    )
    drawing1.add_material_legend([
        ("purlin-support-footprint", "Uložení sloupku krovu"),
    ], title="Symboly")
    drawing1.add_wall_outlines(
        ground_load_bearing_walls, style="solid", color="black",
        name="Ground-floor ceiling load-bearing wall outlines",
    )
    # Deliberate copy of the basement diagram: this level will be edited independently.
    for slab, wall_bounds in zip(ceiling_slabs, ceiling_wall_bounds):
        for index, (start, end) in enumerate(slab.beam_centerlines, 1):
            axis = drawing1.add_line(
                start, end, style="dash-dot", color="red", line_width=0.08,
                name=f"{slab.Name} Beam {index} Centreline",
            )
            appearance = ifcopenshell.util.element.get_pset(axis, "EPset_Annotation")
            ifcopenshell.api.pset.edit_pset(
                drawing1.house.model, pset=drawing1.house.model.by_id(appearance["id"]),
                properties={"Classes": appearance["Classes"]+" ceiling-beam-axis"},
            )
        add_ceiling_beam_spacing_dimensions(
            drawing1, slab, side=("garden" if slab == ceiling_garden_rooms
                                 else "right" if slab == ceiling_stairway else "left"),
        )
        # Room wall-offset dimensions still reference the inner wall faces.
        midpoints = tuple(np.mean(centreline, axis=0) for centreline in slab.beam_centerlines)

        # Put the shared garden ceiling's end bearings outside the west wall.
        garden_slab = slab == ceiling_garden_rooms
        bearing_row = -1 if garden_slab else 0
        bearing_offset = (-0.85 if garden_slab else -0.65
                          if slab in (ceiling_bathroom, ceiling_bathroom_front) else -0.3)
        start, end = (np.asarray(point) for point in slab.beam_centerlines[bearing_row])
        along = (end-start)/slab.length
        # Measure against the real wall faces at this level, not the cloned insert offsets.
        span_axis = int(np.argmax(np.abs(along)))
        start_wall, end_wall = start.copy(), end.copy()
        start_wall[span_axis], end_wall[span_axis] = wall_bounds[span_axis], wall_bounds[span_axis+2]
        drawing1.add_dimension(
            start=tuple(start), end=tuple(start_wall), offset=bearing_offset,
            name=f"{slab.Name} Start Bearing",
        )
        drawing1.add_dimension(
            start=tuple(end_wall), end=tuple(end), offset=bearing_offset,
            name=f"{slab.Name} End Bearing",
        )

        # Keep room wall offsets clear of the chimney and small end spacings.
        across_axis = int(np.argmax(np.abs(slab.direction)))
        near_face, far_face = wall_bounds[across_axis], wall_bounds[across_axis+2]
        if slab.direction[across_axis] < 0:
            near_face, far_face = far_face, near_face
        wall_reference_shift = along*min(0.4, slab.length/4)
        first_beam, last_beam = midpoints[0]+wall_reference_shift, midpoints[-1]+wall_reference_shift
        first_wall, last_wall = first_beam.copy(), last_beam.copy()
        first_wall[across_axis], last_wall[across_axis] = near_face, far_face
        for dimension_start, dimension_end, label in (
            (first_wall, first_beam, "First Beam to Wall"),
            (last_beam, last_wall, "Last Beam to Wall"),
        ):
            distance = np.linalg.norm(dimension_end-dimension_start)
            if distance < 1e-9:
                drawing1.add_text(
                    tuple(dimension_start), "0", font_size=2,
                    name=f"{slab.Name} {label}",
                )
                continue
            drawing1.add_dimension(
                start=tuple(dimension_start), end=tuple(dimension_end),
                name=f"{slab.Name} {label}",
            )
    add_purlin_support_girder_plan(drawing1)
    drawing1.add_miako_beam_schedule(ceiling_schedule_rows)
    add_ground_room_annotations(drawing1, include_legend=False)
    drawing1.add_chimney_annotation(chimney)
    add_purlin_support_planning_markers(drawing1)
    drawing1.render(PROJECT_DIR / "ceiling.svg", pdf=PDF_CEILING)

if "ceiling2" in sys.argv:
    drawing1 = house.add_drawing(
        "ceiling2", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=ceiling_storey.elevation+0.1,
        radius=7, storeys=[ceiling_storey], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    # Include only supporting walls as context, without furniture or floor finishes.
    for wall in ground_load_bearing_walls:
        drawing1.include_element(wall)
    add_facade_insulation(drawing1)
    drawing1.add_material_legend([
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
        ("reinforced-concrete", "Železobetonový věnec"),
        ("purlin-support-footprint", "Uložení sloupku krovu"),
    ])
    for slab in ceiling_slabs:
        add_ceiling_beam_spacing_dimensions(
            drawing1, slab, side=("garden" if slab == ceiling_garden_rooms
                                 else "right" if slab == ceiling_stairway else "left"),
        )
    add_stairway_ceiling_bearing_dimensions(drawing1)
    add_purlin_support_girder_plan(drawing1)
    drawing1.add_dimension(
        start=tuple(ceiling_plan_min),
        end=(float(ceiling_plan_max[0]), float(ceiling_plan_min[1])), offset=-1.0,
    )
    drawing1.add_dimension(
        start=tuple(ceiling_plan_min),
        end=(float(ceiling_plan_min[0]), float(ceiling_plan_max[1])), offset=1.2,
    )
    drawing1.add_dimension(
        start=ceiling_garden_rooms.start, end=ceiling_garden_rooms.end,
        offset=0.65,
        name="Shared Pokoj 1 and Pokoj 2 beam length",
    )
    drawing1.add_dimension(
        start=ceiling_garden_rooms.end,
        end=tuple(np.asarray(ceiling_garden_rooms.end)
                  +ceiling_garden_rooms.width*np.asarray(ceiling_garden_rooms.direction)),
        offset=0.45, name="Shared Pokoj 1 and Pokoj 2 ceiling width",
    )
    for slab, left_face, right_face in (
        (ceiling_room3, room3_ceiling_east_face_x, room3_ceiling_middle_face_x),
        (ceiling_bathroom, bathroom_ceiling_middle_face_x, bathroom_ceiling_stairway_face_x),
    ):
        street_edge_y = min(point[1] for point in slab.footprint)
        drawing1.add_dimension(
            start=(slab.start[0], street_edge_y), end=(slab.end[0], street_edge_y),
            offset=-1.0, name=f"{slab.Name} Beam length",
        )
        start, end = slab.beam_centerlines[0]
        bearing_offset = 0.65 if slab == ceiling_bathroom else 0.35
        drawing1.add_dimension(
            start, (left_face, start[1]), offset=bearing_offset,
            name=f"{slab.Name} Start bearing",
        )
        drawing1.add_dimension(
            (right_face, end[1]), end, offset=bearing_offset,
            name=f"{slab.Name} End bearing",
        )
    front_ceiling_garden_edge_y = max(point[1] for point in ceiling_room3_front.footprint)
    front_ceiling_dimension_x = (ceiling_room3_front.start[0]+ceiling_room3_front.end[0])/2+0.4
    drawing1.add_dimension(
        start=(front_ceiling_dimension_x, front_ceiling_garden_edge_y),
        end=(front_ceiling_dimension_x, ceiling_front_girder_edge_y),
        name="Front ceiling clear gap to purlin support girder",
    )
    ceiling_stairway_street_y = min(point[1] for point in ceiling_stairway.footprint)
    drawing1.add_dimension(
        start=(ceiling_stairway.start[0], ceiling_stairway_street_y),
        end=(ceiling_stairway.end[0], ceiling_stairway_street_y),
        offset=-0.35,
    )
    ceiling_stair_opening_dimension_x = (ceiling_wall_bounds[-1][0]+ceiling_wall_bounds[-1][2])/2
    drawing1.add_dimension(
        start=(ceiling_stair_opening_dimension_x, BWT),
        end=(ceiling_stair_opening_dimension_x, ceiling_stair_opening_end_y),
        name="Ground stairwell clear ceiling opening",
    )
    drawing1.add_miako_beam_schedule(ceiling_schedule_rows)
    drawing1.add_notes([
        f"Pokoje 1 a 2: společný strop, 14 nosníků {ceiling_garden_rooms.length*1000:.0f} mm ve směru Y, 13 širokých vložkových řad.",
        f"Pokoje 1 a 2: šířka {ceiling_garden_rooms.width*1000:.0f} mm, vystředěno nad oběma pokoji; mezery 5 mm mezi nosníky a vložkami.",
        f"Uložení na příčné a zahradní stěně: {GARDEN_CEILING_BEARING*1000:g} mm na každém konci.",
        f"0.03: nosníky {ROOM3_CEILING_BEAM_LENGTH*1000:.0f} mm; uložení obvod {ROOM3_CEILING_EAST_BEARING*1000:.0f} mm / střed {ROOM3_CEILING_MIDDLE_BEARING*1000:.0f} mm.",
        f"0.05: nosníky {BATHROOM_CEILING_BEAM_LENGTH*1000:.0f} mm; uložení {BATHROOM_CEILING_BEARING*1000:.0f} mm na obou koncích.",
        "Uložení nosníků je nutné upravit podle stěn v 1.NP.",
        f"Pod sloupky vaznic: dělené HEB{PURLIN_SUPPORT_GIRDER_HEB} v průvlacích {PURLIN_SUPPORT_GIRDER_SIZE[0]*1000:.0f} × {PURLIN_SUPPORT_GIRDER_SIZE[1]*1000:.0f} mm; uložení {PURLIN_SUPPORT_GIRDER_BEARING*1000:.0f} mm na všech stěnách.",
        f"Otvor schodiště: {(ceiling_stair_opening_end_y-BWT)*1000:.0f} mm od vnitřního líce uliční stěny.",
        "Detail otvoru pro komín zatím není řešen.",
    ])
    drawing1.add_chimney_annotation(chimney)
    add_purlin_support_planning_markers(drawing1)
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "ceiling2.svg", pdf=PDF_CEILING2)

if "basement_ceiling" in sys.argv:
    drawing1 = house.add_drawing(
        "basement_ceiling", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        # This is an annotation-only diagram; keep its Z=0 linework below the camera.
        z=0.1, radius=7, storeys=[], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
    )
    drawing1.add_wall_outlines(
        [wall for wall in basement_walls
         if ifcopenshell.util.element.get_pset(wall, "Pset_WallCommon", "LoadBearing")],
        style="solid", color="black",
        name="Basement ceiling load-bearing wall outlines",
    )
    for identifier, slabs in basement_ceilings_by_room.items():
        for slab in slabs:
            add_ceiling_beam_plan(
                drawing1, slab, wall_bounds=basement_rooms_by_id[identifier].bounds,
                bearing_offset=-0.65 if identifier == "S.04" else -0.3,
            )
    drawing1.add_miako_beam_schedule(basement_ceiling_schedule_rows)
    for room in basement_rooms:
        region = room["region"]
        position = region.representative_point().coords[0]
        # Leave the beam-spacing dimension chains at midspan clear.
        if room["identifier"] in ("S.03", "S.04", "S.05"):
            position = (position[0]-0.5, position[1])
        else:
            position = (position[0], position[1]-0.5)
        drawing1.add_room_annotation(
            position, identifier=room["identifier"], description=room["name"], area=region.area,
        )
    drawing1.add_chimney_annotation(chimney)
    drawing1.render(PROJECT_DIR / "basement_ceiling.svg", pdf=PDF_BASEMENT_CEILING)

if "basement_ceiling2" in sys.argv:
    drawing1 = house.add_drawing(
        "basement_ceiling2", x=HOUSE_WIDTH/2, y=HOUSE_DEPTH/2,
        z=basement_ceiling_storey.elevation+0.1,
        radius=7, storeys=[basement_ceiling_storey], right_panel_width=60,
        door_annotations=False, automatic_plan_annotations=False,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    for finish in basement_ceiling_finishes:
        drawing1.exclude_element(finish)
    # Include only supporting walls as context, without furniture or floor finishes.
    for wall in basement_walls:
        drawing1.include_element(wall)
    add_perimeter_insulation(drawing1)
    drawing1.add_material_legend([
        ("ztracene-bedneni", f"Ztracené bednění {BASEMENT_WALL_THICKNESS*1000:.0f} mm"),
        ("reinforced-concrete", "Železobetonový věnec"),
        ("perimeter-polystyrene", f"Perimetrická izolace {EXTERIOR_XPS_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    drawing1.add_miako_beam_dimensions(basement_ceiling_s01, side="end", offset=0.7)
    drawing1.add_miako_beam_dimensions(basement_ceiling_s02, side="end", offset=0.7)
    drawing1.add_miako_beam_dimensions(basement_ceiling_s03, side="start", offset=0.7)
    drawing1.add_miako_beam_dimensions(basement_ceiling_s04, side="end", offset=0.45)
    drawing1.add_miako_beam_dimensions(basement_ceiling_s05, side="end", offset=0.65)
    drawing1.add_dimension(
        start=tuple(basement_plan_min),
        end=(float(basement_plan_max[0]), float(basement_plan_min[1])), offset=-1.0,
    )
    drawing1.add_dimension(
        start=tuple(basement_plan_min),
        end=(float(basement_plan_min[0]), float(basement_plan_max[1])), offset=1.2,
    )
    drawing1.add_dimension(
        start=basement_ceiling_s01.start, end=basement_ceiling_s01.end,
        offset=0.65,
    )
    drawing1.add_dimension(
        start=basement_ceiling_s02.start, end=basement_ceiling_s02.end, offset=-0.55,
    )
    for slab in (basement_ceiling_s01, basement_ceiling_s02):
        drawing1.add_dimension(
            start=slab.end, end=(slab.end[0]+slab.width, slab.end[1]), offset=1.15,
        )
    for slab in (basement_ceiling_s03, basement_ceiling_s04):
        street_edge_y = min(point[1] for point in slab.footprint)
        drawing1.add_dimension(
            start=(slab.start[0], street_edge_y), end=(slab.end[0], street_edge_y), offset=-0.75,
        )
    basement_s05_ceiling_street_y = min(point[1] for point in basement_ceiling_s05.footprint)
    drawing1.add_dimension(
        start=(basement_ceiling_s05.start[0], basement_s05_ceiling_street_y),
        end=(basement_ceiling_s05.end[0], basement_s05_ceiling_street_y),
        offset=-0.35,
    )
    basement_stair_opening_dimension_x = (basement_s05_x0+basement_s05_x1)/2
    drawing1.add_dimension(
        start=(basement_stair_opening_dimension_x, basement_s05_y0),
        end=(basement_stair_opening_dimension_x, basement_stair_opening_end_y),
        name="S.05 clear ceiling opening from inside street wall",
    )
    drawing1.add_miako_beam_schedule(basement_ceiling_schedule_rows)
    drawing1.add_notes([
        f"Uložení nosníků min. {CEILING_BEAM_BEARING*1000:.0f} mm na obou koncích; délky po 250 mm.",
        "S.01/S.02: 7 nosníků 3750 mm, 6 širokých řad, mezery 5 mm, vystředěno nad místnostmi.",
        "S.03/S.04: samostatné průběžné skladby bez dělení u HEB; další řady se doplní k ulici.",
        f"S.05: skladba 0.04 posunuta k zahradě o {basement_s05_ceiling_shift_y*1000:.0f} mm kvůli otvoru.",
        f"Otvor nad S.05: {BASEMENT_STAIR_OPENING_LENGTH*1000:.0f} mm od vnitřního líce uliční stěny.",
        "Styk protilehlých nosníků na společných stěnách zatím není řešen.",
        "S.04: zachován výřez vložek a nadbetonávky před komínem.",
    ])
    drawing1.add_chimney_annotation(chimney)
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "basement_ceiling2.svg", pdf=PDF_BASEMENT_CEILING2)

if "upper" in sys.argv:
    drawing1 = house.add_drawing(
        "upper",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=UPPER_FLOOR_START+1.2,
        radius=6.5,
        storeys=[upper],
        door_annotations=False,
        right_panel_width=60,
        section_outline_width=SECTION_OUTLINE_WIDTH,
    )
    drawing1.add_material_legend([
        ("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
        ("drywall-diagonal1", f"Sádrokartonová příčka {DRY_WALL_WIDTH*1000:.0f} mm"),
        ("wood-solid", "Dřevěný sloupek pod vaznicí"),
        ("rockwool-wave", f"Fasádní izolace {FACADE_INSULATION_THICKNESS*1000:.0f} mm"),
    ])
    add_facade_insulation(drawing1, upper_exterior_walls)
    # These continuous coverings are hosted downstairs but span both floors.
    for facade in wall_facades:
        drawing1.include_element(facade)
    drawing1.add_chimney_annotation(chimney)
    drawing1.add_door_annotation(living_room_door)
    # Use the standard label position inside the swing symbol.
    drawing1.add_door_annotation(upper_toilet_door)
    drawing1.add_dimension(
        start=(upper_technical_left_x, STAIR_UPPER_END_Y),
        end=(upper_technical_right_x, STAIR_UPPER_END_Y),
        offset=0.1,
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
        start=(STAIR_LEFT_X, upper_stairs.end[1]),
        end=(STAIR_LEFT_X, upper_toilet_end_back_y),
        offset=-0.40,
        name="Bathroom end wall clearance from stair exit",
    )
    drawing1.add_dimension(
        start=(STAIR_LEFT_X, upper_technical_cross_back_y),
        end=(STAIR_LEFT_X, upper_toilet_end_front_y),
        offset=0.8,
        name="Upper toilet clear depth",
    )
    drawing1.add_dimension(
        start=(STAIR_LEFT_X, upper_toilet_end_back_y),
        end=(STAIR_LEFT_X, living_room_right_wall_front_y),
        offset=0.10,
        name="Bathroom garden wall clearance to VPC wall",
    )
    drawing1.add_dimension(
        start=(hallway_dimension_x, upper_stairs.end[1]),
        end=(hallway_dimension_x, living_room_right_wall_front_y),
        name="Living room wall clearance from stairs",
    )
    living_room_return_dimension_x = living_room_wall_x-DRY_WALL_WIDTH/2
    drawing1.add_dimension(
        start=(living_room_return_dimension_x, living_room_return_back_y),
        end=(living_room_return_dimension_x, living_room_right_wall_front_y),
        name="Living room drywall return clearance to VPC wall",
    )
    for room in upper_room_floors:
        position = Polygon(room.outline).representative_point().coords[0]
        if room == living_room:
            position = (3.5, 7)
        elif room == upper_hallway:
            position = (STAIR_LEFT_X+0.5,
                        (upper_toilet_end_back_y+LIVING_ROOM_WALL_FRONT_Y)/2)
        elif room == upper_toilet_room:
            position = ((upper_technical_left_x+upper_technical_right_x)/2,
                        (upper_toilet_center[1]-0.1))
        drawing1.add_room_annotation(
            position, identifier=room.room_id, description=room.Name,
            area=living_room_outline.area if room == living_room else room.area,
            window_area=window_area(*upper_room_windows[room.room_id]),
        )
    drawing1.add_room_legend()
    # Keep numbers consistent with equal-width openings on the ground floor.
    drawing1.add_lintel(living_room_door, 2, position="after", direction="in")
    drawing1.add_lintel(living_room_opening, 6, direction="in")
    drawing1.add_lintel(window_living_room_front, 4)
    for index, window in enumerate(windows_living_room_back):
        drawing1.add_lintel(window, 4, position="before" if index == 0 else "after")
    drawing1.add_lintel_legend()
    drawing1.add_opening_dimension(
        living_room_door, offset=1.15, finished_floor_height=UPPER_FLOOR_THICKNESS,
    )
    drawing1.add_opening_dimension(
        living_room_opening, offset=0.0, finished_floor_height=UPPER_FLOOR_THICKNESS,
    )
    drawing1.add_dimension(
        start=(BWT, living_room_back_face_y),
        end=(BWT+LIVING_ROOM_OPENING_EAST_CLEARANCE, living_room_back_face_y), offset=1.0,
        name="Living-room wide opening clearance from east wall",
    )
    drawing1.add_dimension(
        start=(LIVING_ROOM_OPENING_END_X, living_room_back_face_y),
        end=(living_room_door_opening_x, living_room_back_face_y), offset=1.0,
        name="VPC wall segment between living-room openings",
    )
    drawing1.add_dimension(
        start=(living_room_door_opening_x+ROOM_DOOR_OPENING_WIDTH, living_room_back_face_y),
        end=(HOUSE_WIDTH-BWT, living_room_back_face_y), offset=1.0,
        name="Living-room door opening clearance from west wall",
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
    drawing1.include_element(stair_landing_gap_railing)
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
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-1.75)
    drawing1.add_dimension(start=(0, 0), end=(0, HOUSE_DEPTH), offset=0.7)
    drawing1.add_dimension(
        start=(BWT, HOUSE_DEPTH-BWT-0.95),
        end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-0.95),
        name="Living room garden-side clear width",
    )
    upper_window_x_bounds = {}
    for window in (window_living_room_front, *windows_living_room_back):
        opening = window.FillsVoids[0].RelatingOpeningElement
        placement = ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)
        upper_window_x_bounds[window] = sorted(
            float((placement @ np.array((x, 0., 0., 1.)))[0])
            for x in (0., window.OverallWidth)
        )
    garden_left, garden_right = sorted(
        upper_window_x_bounds[window] for window in windows_living_room_back
    )
    garden_window_wall_y = HOUSE_DEPTH-BWT
    for x0, x1, name in (
        (BWT, garden_left[0], "Upper garden window clearance to east wall"),
        (garden_left[1], garden_right[0], "Upper garden window opening gap"),
        (garden_right[1], HOUSE_WIDTH-BWT, "Upper garden window clearance to west wall"),
    ):
        drawing1.add_dimension(
            (x0, garden_window_wall_y), (x1, garden_window_wall_y), offset=-0.6, name=name,
        )
    front_x0, front_x1 = upper_window_x_bounds[window_living_room_front]
    street_window_wall_y = BWT
    for x0, x1, name in (
        (BWT, front_x0, "Upper street window clearance to east wall"),
        (front_x1, kitchen_wall_face_x, "Upper street window clearance to drywall"),
    ):
        drawing1.add_dimension(
            (x0, street_window_wall_y), (x1, street_window_wall_y), offset=0.75, name=name,
        )
    drawing1.add_dimension(
        start=(BWT+0.5, BWT),
        end=(BWT+0.5, HOUSE_DEPTH-BWT),
    )
    # Clear sections on each side of the full-width masonry wall.
    for index, (start_y, end_y) in enumerate((
        (BWT, living_room_right_wall_front_y),
        (living_room_back_face_y, HOUSE_DEPTH-BWT),
    ), 1):
        drawing1.add_dimension(
            start=(BWT+1.25, start_y), end=(BWT+1.25, end_y),
            offset=-0.35, name=f"East VPC wall clear section {index}",
        )
    drawing1.add_dimension(
        start=(BWT, 2.3),
        end=(living_room_wall_x-DRY_WALL_WIDTH/2, 2.3),
    )
    drawing1.add_dimension(
        start=(HOUSE_WIDTH-BWT-1.0, living_room_back_face_y),
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
    west_front_y = min(PURLIN_SUPPORT_Y_POSITIONS[west_purlin_index])
    drawing1.add_dimension(
        start=(east_support_x, east_front_y),
        end=(east_support_x, living_room_right_wall_front_y), offset=0.35,
        name="Street est purlin support clearance to living room wall",
    )
    add_house_cut_symbols(drawing1)
    drawing1.render(PROJECT_DIR / "upper.svg", pdf=PDF_UPPER)

def roof_member_axial_ends(beam, reference, *, horizontal_axis=0):
    """Project finished timber tips onto a reference line in XZ or YZ."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shape = ifcopenshell.geom.create_shape(settings, beam)
    vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
    axes = (horizontal_axis, 2)
    used = vertices[np.unique(np.asarray(shape.geometry.faces, dtype=int))][:, axes]
    axis = np.asarray(beam.end)[list(axes)]-np.asarray(beam.start)[list(axes)]
    axis = axis/np.linalg.norm(axis)
    reference = np.asarray(reference)
    stations = (used-reference) @ axis
    return tuple(tuple(float(v) for v in reference+axis*station)
                 for station in (stations.min(), stations.max()))


def add_roof_framing_dimensions(drawing, *, rafter_index):
    """Dimension finished timber extents and bearing stations in a roof section.

    Project the clipped rafter tips onto the support-contact line: all three
    segments then use the same longitudinal stations as the procurement length.
    Bearing stations are the supports' outer top corners. The ridge station
    is the actual longest timber tip, including the oblique ridge end cut.
    """
    axial_ends = roof_member_axial_ends
    _, west_rafter = rafter_pairs[rafter_index]
    wall_seat = (west_contact_x, wall_plate_top_z)
    purlin_seat = (PURLIN_X_POSITIONS[1]+PURLIN_SIZE[0]/2, purlin_top_z)
    eave, ridge = axial_ends(west_rafter, wall_seat)
    for start, end, name in (
        (eave, wall_seat, "rafter eave to wall plate"),
        (wall_seat, purlin_seat, "rafter wall plate to purlin"),
        (purlin_seat, ridge, "rafter purlin to ridge"),
    ):
        drawing.add_dimension(start, end, offset=-.55, name=f"{drawing.name} {name}")
    drawing.add_dimension(
        eave, ridge, offset=-1.15, name=f"{drawing.name} rafter total finished length",
    )
    drawing.add_dimension(
        (PURLIN_X_POSITIONS[0], PURLIN_Z), (PURLIN_X_POSITIONS[1], PURLIN_Z),
        offset=+0.35, name=f"{drawing.name} purlin centre distance",
    )
    tie = collar_ties[2*rafter_index+1]
    tie_start, tie_end = axial_ends(tie, (tie.start[0], tie.start[2]-tie.height/2))
    drawing.add_dimension(
        tie_start, tie_end, offset=2.3, name=f"{drawing.name} collar tie total finished length",
    )
    support = max(
        (post for post in purlin_supports
         if math.isclose(post.start[0], PURLIN_X_POSITIONS[0]) and post.start[1] < drawing.y),
        key=lambda post: post.start[1],
    )
    support_start, support_end = axial_ends(support, (support.start[0], support.start[2]))
    drawing.add_dimension(
        support_start, support_end, offset=.5, name=f"{drawing.name} support height",
    )
    saddle = next(beam for beam in purlin_saddles
                  if math.isclose(beam.start[0], PURLIN_X_POSITIONS[1]))
    drawing.add_dimension(
        (saddle.start[0], saddle.start[2]-PURLIN_SADDLE_SIZE[1]/2),
        (saddle.start[0], saddle.start[2]+PURLIN_SADDLE_SIZE[1]/2),
        offset=1.0, name=f"{drawing.name} sedlo height",
    )


def add_roof_framing_section(name, cut, *, framing_elements, schedule_rows):
    """Create a framing-only section with the shared roof palette and context."""
    drawing = cut.add_drawing(
        house, name, z=(UPPER_FLOOR_START+roof_tiles_top_z)/2+0.5,
        radius=7, storeys=[], door_annotations=False, automatic_plan_annotations=False,
        model_line_width=0.06, right_panel_width=65,
        hide_projected_ring_beam_seams=True,
    )
    for element in framing_elements:
        drawing.include_element(element)
    # Keep the colour definitions even when the sheet hides this view's table.
    drawing.add_timber_schedule(schedule_rows)
    return drawing


if "roof" in sys.argv:
    drawing1 = house.add_drawing(
        "roof",
        x=HOUSE_WIDTH/2,
        y=HOUSE_DEPTH/2,
        z=max(roof_tiles_top_z, chimney.storey.elevation+chimney.end_height)+0.5,
        radius=6.5,
        storeys=[],
        door_annotations=False,
        automatic_plan_annotations=False,
        projected_wood_color="#c8e6c9",
        surface_fills=True,
        model_line_width=0.06,
        right_panel_width=65,
        section_outline_width=SECTION_OUTLINE_WIDTH,
        section_outline_projected_walls=True,
    )
    roof_rafters = tuple(member for pair in rafter_pairs for member in pair)
    roof_framing_elements = (
        *upper_exterior_walls, wall_living_room_back_u, *upper_ring_beams, wall_plate_east, wall_plate_west, *purlins,
        *purlin_connection_beams, *purlin_supports, *purlin_saddles, *roof_rafters, *collar_ties,
    )
    for element in roof_framing_elements:
        drawing1.include_element(element)
    drawing1.add_chimney_annotation(chimney)
    for index, y in enumerate(RAFTER_Y_POSITIONS, 1):
        drawing1.add_line(
            (east_eave_x-.15, y), (west_eave_x+.15, y),
            style="dash-dot", line_width=.08, name=f"Rafter centreline {index}",
        )
    for index, (start_y, end_y) in enumerate(zip(RAFTER_Y_POSITIONS, RAFTER_Y_POSITIONS[1:]), 1):
        drawing1.add_dimension(
            start=(east_eave_x, start_y), end=(east_eave_x, end_y), offset=0.65,
            name=f"Rafter spacing {index}",
        )
    support_x_positions = (BWT/2, *PURLIN_X_POSITIONS, HOUSE_WIDTH-BWT/2)
    for index, (start_x, end_x) in enumerate(zip(support_x_positions, support_x_positions[1:]), 1):
        drawing1.add_dimension(
            start=(start_x, -WALL_PLATE_OVERHANG), end=(end_x, -WALL_PLATE_OVERHANG), offset=-0.5,
            name=f"Roof support centre distance {index}",
        )
    drawing1.add_dimension(start=(0, 0), end=(HOUSE_WIDTH, 0), offset=-2.0)
    drawing1.add_dimension(
        start=(HOUSE_WIDTH, 0),
        end=(HOUSE_WIDTH, HOUSE_DEPTH),
		offset=-1.0
    )
    roof_timber_schedule_rows = [
        ("Pozednice", (wall_plate_east, wall_plate_west), 0,
         {"color": "#f4d35e"}),
        ("Vaznice", purlins, 0, {"color": "#f4a261"}),
        ("Sloupky pod vaznice", purlin_supports, 0, {"color": "#c8e6c9"}),
        ("Spojovací trámy", purlin_connection_beams, 0, {"color": "#c8e6c9"}),
        ("Sedla pod vaznice", purlin_saddles, 0, {"color": "#c8e6c9"}),
        ("Krokve", roof_rafters, 0, {"color": "#ffeb3b"}),
        ("Kleštiny", collar_ties, 0, {"color": "#f4d35e"}),
    ]
    roof_timber_schedule_rows = [
        (name, members, extra_length, {**settings, "material": ROOF_TIMBER_MATERIAL})
        for name, members, extra_length, settings in roof_timber_schedule_rows
    ]
    drawing1.add_timber_schedule(roof_timber_schedule_rows)
    #add_house_cut_symbols(drawing1)
    roof_xx_cut.add_symbol(drawing1)
    roof_yy_cut.add_symbol(drawing1)
    roof_plan = drawing1
    roof_xx = add_roof_framing_section(
        "roof_xx", roof_xx_cut, framing_elements=roof_framing_elements,
        schedule_rows=roof_timber_schedule_rows,
    )
    roof_yy = add_roof_framing_section(
        "roof_yy", roof_yy_cut, framing_elements=roof_framing_elements,
        schedule_rows=roof_timber_schedule_rows,
    )
    xx_rafter_index = max(
        (index for index, y in enumerate(RAFTER_Y_POSITIONS) if y < roof_xx.y),
        key=lambda index: RAFTER_Y_POSITIONS[index],
    )
    add_roof_framing_dimensions(roof_xx, rafter_index=xx_rafter_index)
    # Show the longitudinal sedlo replacing the diagonal purlin braces.
    yy_purlin_x = min(x for x in PURLIN_X_POSITIONS if x > roof_yy.x)
    yy_saddle = next(beam for beam in purlin_saddles if math.isclose(beam.start[0], yy_purlin_x))
    yy_start, yy_end = roof_member_axial_ends(
        yy_saddle, (yy_saddle.start[1], yy_saddle.start[2]), horizontal_axis=1,
    )
    roof_yy.add_dimension(yy_start, yy_end, offset=-.35, name="roof_yy sedlo length")
    roof_sheet = DrawingSheet(paper="A3", orientation="portrait")
    roof_sheet.add(roof_plan, x=0.5, y=0.25, title=PDF_ROOF.stem, crop=False)
    roof_sheet.add(roof_xx, x=0.5, y=0.65, title="Řez XX", tables=False)
    roof_sheet.add(roof_yy, x=0.5, y=0.87, title="Řez YY", tables=False)
    roof_sheet.render(PROJECT_DIR / "roof.svg", pdf=PDF_ROOF)


def aa_roof_batting_bands(x):
    """Return the two horizontal insulation bands at the AA section's X."""
    plane = roof_east if x <= roof_ridge_x else roof_west
    rafter_center_z = plane_height_at(
        *offset_plane(*plane.points, offset=RAFTER_Z_OFFSET+RAFTER_HEIGHT/2), x=x, y=0,
    )
    return (
        ("between-rafter insulation", rafter_center_z, RAFTER_HEIGHT),
        ("horizontal ceiling insulation", FLAT_VAPOUR_BARRIER_TOP_Z+THERMAL_INSULATION_UNDER_RAFTERS/2,
         THERMAL_INSULATION_UNDER_RAFTERS),
    )


def add_aa_roof_batting(drawing):
    """Overlay uninterrupted insulation across the rafters and projected purlins."""
    for label, center_z, thickness in aa_roof_batting_bands(drawing.x):
        drawing.add_batting(
            (drawing.x, -FACADE_INSULATION_THICKNESS, center_z),
            (drawing.x, HOUSE_DEPTH+FACADE_INSULATION_THICKNESS, center_z),
            thickness=thickness, name=f"AA {label}",
            classes="roof-batting roof-batting-overlay",
        )


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


def add_section_ground(drawing):
    """Draw section-only natural soil and gravel outside the perimeter insulation."""
    if math.isclose(abs(drawing.direction[0]), 1.0):
        axis, length = 1, HOUSE_DEPTH
        fraction = min(1.0, max(0.0, drawing.x/HOUSE_WIDTH))
        first = TERRAIN_STREET_EAST_ELEVATION+fraction*(TERRAIN_STREET_WEST_ELEVATION-TERRAIN_STREET_EAST_ELEVATION)
        last = TERRAIN_GARDEN_EAST_ELEVATION+fraction*(TERRAIN_GARDEN_WEST_ELEVATION-TERRAIN_GARDEN_EAST_ELEVATION)
    else:
        axis, length = 0, HOUSE_WIDTH
        fraction = min(1.0, max(0.0, drawing.y/HOUSE_DEPTH))
        first = TERRAIN_STREET_EAST_ELEVATION+fraction*(TERRAIN_GARDEN_EAST_ELEVATION-TERRAIN_STREET_EAST_ELEVATION)
        last = TERRAIN_STREET_WEST_ELEVATION+fraction*(TERRAIN_GARDEN_WEST_ELEVATION-TERRAIN_STREET_WEST_ELEVATION)
    first, last = earth_to_z(first), earth_to_z(last)
    wall_start, wall_end = float(basement_plan_min[axis]), float(basement_plan_max[axis])
    left, right = wall_start-SECTION_SOIL_EXTENT, wall_end+SECTION_SOIL_EXTENT
    bottom = FOUNDATION_FOOTING_BOTTOM_Z-SECTION_SOIL_DEPTH
    ground_region = Polygon(((left, bottom), (right, bottom), (right, last),
                             (length, last), (0, first), (left, first)))
    finish = EXTERIOR_XPS_INSULATION_THICKNESS+FACADE_THICKNESS
    inner_left, inner_right = wall_start-finish, wall_end+finish
    interior = box(inner_left, BASEMENT_SLAB_BOTTOM_Z, inner_right, max(first, last)+1)
    gravel_regions = []
    for face, outward, terrain_z in ((inner_left, -1, first), (inner_right, 1, last)):
        if terrain_z <= BASEMENT_SLAB_BOTTOM_Z:
            continue
        top_width = SECTION_GRAVEL_BOTTOM_WIDTH+(terrain_z-BASEMENT_SLAB_BOTTOM_Z)*SECTION_GRAVEL_SLOPE
        gravel_regions.append(Polygon((
            (face, BASEMENT_SLAB_BOTTOM_Z),
            (face+outward*SECTION_GRAVEL_BOTTOM_WIDTH, BASEMENT_SLAB_BOTTOM_Z),
            (face+outward*top_width, terrain_z), (face, terrain_z),
        )).intersection(ground_region))
    soil = ground_region.difference(unary_union((interior, *gravel_regions)))
    for region, pattern, label in ((soil, "earth-section", "Rostlý terén"),
                                   *((region, "gravel", "Zhutněná zemina") for region in gravel_regions)):
        parts = (region,) if region.geom_type == "Polygon" else region.geoms
        for index, part in enumerate(parts, 1):
            if part.area > 1e-9:
                drawing.add_polygon(tuple(part.exterior.coords)[:-1], pattern=pattern,
                                    background=True, name=f"{drawing.name} {label} {index}")
    # Background profiles add the ground line without hiding the foundations.
    for start, end, z in ((left, inner_left, first), (inner_right, right, last)):
        drawing.add_terrain(((start, z), (end, z)), hatch_depth=0, background=True, line_width=0.2)


def add_section_waterproofing(drawing):
    """Draw waterproofing above the foundation slab and behind the perimeter XPS."""
    axis = 1 if math.isclose(abs(drawing.direction[0]), 1.0) else 0
    outer_start, outer_end = float(basement_plan_min[axis]), float(basement_plan_max[axis])
    line = drawing.add_poly_line(
        (
            (outer_start, PERIMETER_TOP_HEIGHT),
            (outer_start, BASEMENT_FLOOR_START),
            (outer_end, BASEMENT_FLOOR_START),
            (outer_end, PERIMETER_TOP_HEIGHT),
        ),
        style="dashed", line_width=HYDROIZOLACE_LINE_WIDTH, name="Hydroizolace",
    )
    appearance = ifcopenshell.util.element.get_pset(line, "EPset_Annotation")
    ifcopenshell.api.pset.edit_pset(
        house.model, pset=house.model.by_id(appearance["id"]),
        properties={"Classes": appearance["Classes"]+" hydroizolace"},
    )
    return line


def add_bb_elevation_marks(drawing):
    """Mark section levels relative to the finished ground floor, in millimetres."""
    datum_z = ground.elevation+GROUND_FLOOR_THICKNESS
    # Use opposite sides for close levels to keep their arrows and labels apart.
    for z, west_side, label in (
        (datum_z, False, "Ground finished floor level"),
        (ceiling_storey.elevation-CEILING_PLASTER_THICKNESS, True, "Ground plastered ceiling level"),
        (UPPER_FINISHED_FLOOR_HEIGHT, False, "Upper finished floor level"),
        (roof_tiles_lowest_z, False, "Lowest roof tile level"),
        (roof_tiles_top_z, False, "Roof ridge level"),
        (BASEMENT_FINISHED_CEILING_Z, True, "Basement wood ceiling underside level"),
        (BASEMENT_FINISHED_FLOOR_HEIGHT, False, "Basement finished floor level"),
        (BASEMENT_SLAB_BOTTOM_Z, True, "Foundation slab bottom level"),
        (FOUNDATION_FOOTING_BOTTOM_Z, False, "Foundation footing bottom level"),
    ):
        x0, x1 = (HOUSE_WIDTH+1.25, HOUSE_WIDTH+1.85) if west_side else (-1.0, -0.4)
        drawing.add_elevation_dimension(
            x0=x0, x1=x1, z0=datum_z, z1=z, side="left" if west_side else "right", name=label,
        )


def add_house_section(cut, name, pdf):
    """Create a complete vertical section using the same cut as its plan markers."""
    section_top = max(roof_tiles_top_z, chimney.storey.elevation+chimney.end_height)
    section_bottom = FOUNDATION_FOOTING_BOTTOM_Z-SECTION_SOIL_DEPTH
    drawing = cut.add_drawing(
        house, name, z=(section_bottom+section_top)/2,
        radius=max(6.5, (section_top-section_bottom)/2+.5),
        storeys=None, doors_closed=True,
        door_annotations=False, automatic_plan_annotations=False,
        right_panel_width=60, section_outline_width=SECTION_OUTLINE_WIDTH,
        hide_projected_ring_beam_seams=True,
    )
    add_section_ground(drawing)
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
            if name == "aa":
                _, center_z, thickness = aa_roof_batting_bands(section_x)[0]
                insulation_top = center_z-thickness/2
        drawing.add_wall_insulation(
            wall, thickness=FACADE_INSULATION_THICKNESS, material="rockwool",
            start_z=PERIMETER_TOP_HEIGHT, end_z=insulation_top, opening_walls=(upper_wall,),
        )
    add_perimeter_insulation(drawing)
    waterproofing = add_section_waterproofing(drawing)
    basement_height_dimension_x = ((basement_ceiling_garden_y+min(point[1] for point in basement_ceiling_s04.footprint))/2
                                   if name == "aa" else BWT+0.4)
    drawing.add_dimension(
        start=(basement_height_dimension_x, BASEMENT_FINISHED_FLOOR_HEIGHT),
        end=(basement_height_dimension_x, BASEMENT_FINISHED_CEILING_Z),
        name="Basement finished floor to wood ceiling",
    )
    if name == "aa":
        add_aa_roof_batting(drawing)
        for furniture in (
            kamna, kitchen_cooker, kitchen_sink, kitchen_dishwasher, kitchen_fridge,
            kitchen_counter, kitchen_front_counter, bathroom_shower, basement_water_meter,
        ):
            drawing.add_furniture_label(furniture)
    if name == "bb":
        for furniture in (kamna, kitchen_cooker, upper_washing_machine, basement_water_meter, kitchen_front_counter):
            drawing.add_furniture_label(furniture)
        add_bb_roof_batting(drawing)
        add_bb_elevation_marks(drawing)
        drawing.add_dimension(
            start=(BWT+0.4, ground.elevation+GROUND_FLOOR_THICKNESS),
            end=(BWT+0.4, ceiling_storey.elevation-CEILING_PLASTER_THICKNESS),
            name="Ground finished floor to plastered ceiling",
        )
        drawing.add_dimension(
            start=(roof_ridge_x, UPPER_FINISHED_FLOOR_HEIGHT),
            end=(roof_ridge_x, FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z),
            name="Upper finished floor to horizontal plasterboard underside",
        )
        for x, y, offset, label in (
            (*stair_arrival_west_corner, 0.0, "Lowest ceiling clearance at west edge of upper stair exit"),
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
        ("diagonal1", f"Příčka - VPC Cihla {GARDEN_PARTITION_THICKNESS*1000:g} mm"),
        ("liapor-brick", "Zakládací řada - Ytong Statik Plus"),
        ("ztracene-bedneni", "Ztracené bednění"),
        ("base-plate", "Základová deska"),
        ("earth-section", "Rostlý terén"),
        ("gravel", "Zhutněná zemina"),
        ("reinforced-concrete", "Železobetonový věnec"),
        ("wood-solid", "Dřevo"),
        ("drywall-diagonal1", "Sádrokarton"),
        ("wooden-wall", "Dřevěná stěna"),
        ("thermal-impact-insulation", "Podlahová a stropní izolace"),
        ("rockwool-wave", "Minerální vata"),
        ("perimeter-polystyrene", "Perimetrická izolace"),
        ("mdf-solid", "MDF záklop"),
        ("vapour-barrier-solid", "OSB záklop + parobrzda"),
    ])
    drawing.add_line_legend([(waterproofing, "Hydroizolace")])
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


def add_heat_pump_front_symbol(drawing):
    """Draw a fan on the street-facing heat-pump box, without changing the model."""
    placement = ifcopenshell.util.placement.get_local_placement(heat_pump.ObjectPlacement)
    center = np.array((placement[0, 3], placement[2, 3]+HEAT_PUMP_SIZE[2]/2))
    radius = min(HEAT_PUMP_SIZE[0], HEAT_PUMP_SIZE[2])*0.36
    drawing.add_circle(tuple(center), radius, color="#555555", name="Heat pump fan rim")
    drawing.add_circle(tuple(center), radius*0.16, color="#555555", name="Heat pump fan hub")

    def bezier(a, b, c, d):
        return [(1-t)**3*np.array(a)+3*(1-t)**2*t*np.array(b)
                +3*(1-t)*t*t*np.array(c)+t**3*np.array(d)
                for t in np.linspace(0, 1, 17)]

    blade = bezier((.20, -.08), (.40, -.65), (1.0, -.50), (.83, .05))
    blade += bezier((.83, .05), (.80, .30), (.42, .24), (.17, .12))[1:]
    blade.append(blade[0])
    for index in range(3):
        angle = index*2*math.pi/3
        rotation = np.array(((math.cos(angle), -math.sin(angle)),
                             (math.sin(angle), math.cos(angle))))
        drawing.add_poly_line(
            [tuple(center+radius*(rotation@point)) for point in blade],
            color="#555555", line_width=0.1, name=f"Heat pump fan blade {index+1}",
        )


def add_exterior_view(name, camera, direction):
    """Create a complete elevation for the shared exterior-view sheet."""
    view_top = max(roof_tiles_top_z, chimney.storey.elevation+chimney.end_height)
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
        # Both access pockets follow the construction openings, including the
        # clearance around the pedestrian door's narrower leaf.
        street_access_ranges = []
        for label, opening, width in (
            ("Garage", garage_front_opening, garage_front_door.OverallWidth),
            ("S.05 entrance", basement_s05_front_door.FillsVoids[0].RelatingOpeningElement,
             BASEMENT_OPENING_WIDTH),
        ):
            matrix = ifcopenshell.util.placement.get_local_placement(opening.ObjectPlacement)
            ends = sorted(float((matrix @ np.array((x, 0, 0, 1)))[0]) for x in (0, width))
            street_access_ranges.append((label, *ends))
        street_access_ranges.sort(key=lambda item: item[1])
        basement_floor_elevation = GROUND_FINISHED_FLOOR_ELEVATION-BASEMENT_TO_GROUND_RISE

        def street_earth_at(x):
            return TERRAIN_STREET_EAST_ELEVATION+(x/HOUSE_WIDTH)*(
                TERRAIN_STREET_WEST_ELEVATION-TERRAIN_STREET_EAST_ELEVATION
            )

        terrain_profile = [
            (uphill_end_x, uphill_end_elevation),
            (street_wall_x0, STREET_STONE_WALL_TOP_ELEVATION),
            (street_wall_x0, TERRAIN_STREET_EAST_ELEVATION),
            (0.0, TERRAIN_STREET_EAST_ELEVATION),
        ]
        for _, x0, x1 in street_access_ranges:
            terrain_profile.extend((
                (x0, street_earth_at(x0)),
                (x0, basement_floor_elevation),
                (x1, basement_floor_elevation),
                (x1, street_earth_at(x1)),
            ))
        terrain_profile.extend((
            (HOUSE_WIDTH, TERRAIN_STREET_WEST_ELEVATION),
            (HOUSE_WIDTH+2.0, TERRAIN_STREET_WEST_ELEVATION),
        ))
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
        add_heat_pump_front_symbol(drawing)
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
        for label, opening_x0, opening_x1 in street_access_ranges:
            for side, x0, x1 in (
                ("east", opening_x0-GARAGE_RETAINING_WALL_WIDTH, opening_x0),
                ("west", opening_x1, opening_x1+GARAGE_RETAINING_WALL_WIDTH),
            ):
                drawing.add_rectangle(
                    (x0, earth_to_z(basement_floor_elevation)),
                    (x1, earth_to_z(GARAGE_RETAINING_WALL_TOP_ELEVATION)),
                    pattern="stone-wall", name=f"{label} retaining wall {side}",
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
        ("pohled_zapad", "Pohled - Západ", (west_eave_x+1, HOUSE_DEPTH/2), (-1, 0, 0), .35, .35),
        ("pohled_ulice", "Pohled - Ulice", (HOUSE_WIDTH/2, -ROOF_GABLE_OVERHANG-1), (0, 1, 0), .65, .35),
        ("pohled_zahrada", "Pohled - Zahrada", (HOUSE_WIDTH/2, HOUSE_DEPTH+ROOF_GABLE_OVERHANG+1), (0, -1, 0), .65, .75),
        ("pohled_vychod", "Pohled - Východ", (east_eave_x-1, HOUSE_DEPTH/2), (1, 0, 0), .35, .75),
    ):
        view = add_exterior_view(name, camera, direction)
        pohledy_sheet.add(view, x=x, y=y, title=title, tables=False)
    pohledy_sheet.render(PROJECT_DIR / "pohledy.svg", pdf=PDF_POHLEDY)


# Schematic: horizontal layout is arbitrary; heights follow the model.
if "kanal" in sys.argv or "kanal_schematic" in sys.argv:
    sewer_schematic_datum = ground.elevation+GROUND_FLOOR_THICKNESS
    sewer_schematic_roof_height = roof_tiles_top_z-sewer_schematic_datum
    sewer_schematic_ground_ceiling = ceiling_storey.elevation-CEILING_PLASTER_THICKNESS-sewer_schematic_datum
    sewer_schematic_upper_floor = UPPER_FINISHED_FLOOR_HEIGHT-sewer_schematic_datum
    sewer_schematic_basement_floor = BASEMENT_FINISHED_FLOOR_HEIGHT-sewer_schematic_datum
    sewer_schematic_basement_ceiling = BASEMENT_FINISHED_CEILING_Z-sewer_schematic_datum
    sewer_schematic_levels = (
        ("Suterén - hotová podlaha", sewer_schematic_basement_floor),
        ("Suterén - hotový podhled", sewer_schematic_basement_ceiling),
        ("Přízemí - hotová podlaha", 0.0),
        ("Přízemí - hotový podhled", sewer_schematic_ground_ceiling),
        ("Podkroví - hotová podlaha", sewer_schematic_upper_floor),
        ("Podkroví - vodorovný sádrokarton", FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z-sewer_schematic_datum),
        ("Střecha - horní líc krytiny", sewer_schematic_roof_height),
    )
    sewer_schematic_line_start, sewer_schematic_line_end = -1.0, 12.0
    sewer_schematic_stack_x = (sewer_schematic_line_start+sewer_schematic_line_end)/2
    sewer_schematic_stack_bottom = sewer_schematic_basement_ceiling-0.10
    sewer_schematic_stack_top = sewer_schematic_roof_height+0.30
    sewer_schematic_shower_x = sewer_schematic_stack_x+4.0
    sewer_schematic_basement_slope = 0.03
    sewer_schematic_merge_x = (sewer_schematic_stack_x+sewer_schematic_shower_x)/2
    sewer_schematic_merge_z = (sewer_schematic_stack_bottom
                               -(sewer_schematic_merge_x-sewer_schematic_stack_x)*sewer_schematic_basement_slope)
    sewer_schematic_outlet_z = sewer_schematic_basement_floor-0.50
    sewer_schematic_bottom = min(sewer_schematic_outlet_z, *(height for _, height in sewer_schematic_levels))
    sewer_schematic_top = sewer_schematic_stack_top+0.60
    sewer_schematic = house.add_drawing(
        "kanal_schematic",
        x=(sewer_schematic_line_start+sewer_schematic_line_end)/2,
        y=(sewer_schematic_bottom+sewer_schematic_top)/2,
        z=1.0,
        radius=max((sewer_schematic_line_end-sewer_schematic_line_start)/2+0.5,
                   (sewer_schematic_top-sewer_schematic_bottom)/2+0.7),
        storeys=[], door_annotations=False, automatic_plan_annotations=False,
    )
    for label, height in sewer_schematic_levels:
        sewer_schematic.add_line(
            (sewer_schematic_line_start, height), (sewer_schematic_line_end, height),
            color="black", line_width=0.1, name=label,
        )
    for label, height in (
        ("Suterén", sewer_schematic_basement_floor),
        ("Přízemí", 0.0),
        ("Podkroví", sewer_schematic_upper_floor),
        ("Střecha", sewer_schematic_roof_height),
    ):
        sewer_schematic.add_text(
            (sewer_schematic_line_start, height+0.2), f"{label} {round(height*1000)} mm",
            alignment="left", font_size=2.5, name=f"Schematic {label} height label",
        )
    sewer_schematic.add_line(
        (sewer_schematic_stack_x, sewer_schematic_stack_bottom),
        (sewer_schematic_stack_x, sewer_schematic_stack_top),
        color="orange", line_width=SEWER_LINE_WIDTH, name="Schematic DN100 stack",
    )
    sewer_schematic.add_roof_vent(
        x=sewer_schematic_stack_x, z=sewer_schematic_stack_top,
        identifier="Odvětrání", name="Schematic roof vent",
    )
    sewer_schematic.add_text(
        (sewer_schematic_stack_x-0.6, sewer_schematic_ground_ceiling/2),
        "DN100", font_size=2.5, name="Schematic DN100 label",
    )
    sewer_schematic_branch_start_z = sewer_schematic_ground_ceiling-0.10
    sewer_schematic_branch_slope = 0.03
    sewer_schematic_branch_length = 4.0
    sewer_schematic_fixture_z = sewer_schematic_upper_floor+0.65
    sewer_schematic.add_line(
        (sewer_schematic_stack_x, sewer_schematic_branch_start_z),
        (sewer_schematic_stack_x+sewer_schematic_branch_length,
         sewer_schematic_branch_start_z+sewer_schematic_branch_length*sewer_schematic_branch_slope),
        color="orange", line_width=SEWER_LINE_WIDTH, name="Schematic 3 percent branch",
    )
    sewer_schematic.add_washing_machine_connection(
        x=sewer_schematic_stack_x+3.0, z=sewer_schematic_fixture_z,
        name="Schematic washing machine connection",
    )
    sewer_schematic.add_basin(
        x=sewer_schematic_stack_x+4.0, z=sewer_schematic_fixture_z,
        outlet_length=0.10, name="Schematic basin",
    )
    for distance, outlet_z, name in (
        (3.0, sewer_schematic_fixture_z, "Washing machine branch connection"),
        (4.0, sewer_schematic_fixture_z-0.10, "Basin branch connection"),
    ):
        fixture_x = sewer_schematic_stack_x+distance
        sewer_schematic.add_line(
            (fixture_x, sewer_schematic_branch_start_z+distance*sewer_schematic_branch_slope),
            (fixture_x, outlet_z), color="orange", line_width=SEWER_LINE_WIDTH,
            name=name,
        )
    sewer_schematic_left_start_z = sewer_schematic_upper_floor-0.10
    sewer_schematic_left_slope = 0.03
    sewer_schematic_left_length = 1.7
    sewer_schematic.add_line(
        (sewer_schematic_stack_x, sewer_schematic_left_start_z),
        (sewer_schematic_stack_x-sewer_schematic_left_length,
         sewer_schematic_left_start_z+sewer_schematic_left_length*sewer_schematic_left_slope),
        color="orange", line_width=SEWER_LINE_WIDTH, name="Schematic left 3 percent branch",
    )
    sewer_schematic.add_toilet(
        x=sewer_schematic_stack_x-0.5, z=sewer_schematic_upper_floor+0.20,
        name="Schematic toilet",
    )
    # Preserve the connection height even where the kitchen symbols overlap.
    sewer_schematic_dishwasher_z = sewer_schematic_upper_floor+0.65
    sewer_schematic_dishwasher = sewer_schematic.add_washing_machine_connection(
        x=sewer_schematic_stack_x-1.5, z=sewer_schematic_dishwasher_z,
        identifier="Myčka", name="Schematic dishwasher connection",
    )
    sewer_schematic_sink_pipe_x = sewer_schematic_stack_x-1.7
    sewer_schematic_sink_z = sewer_schematic_upper_floor+0.65
    sewer_schematic_sink_symbol_shift = 0.25
    sewer_schematic.add_sink(
        x=sewer_schematic_sink_pipe_x-sewer_schematic_sink_symbol_shift,
        z=sewer_schematic_sink_z, outlet_length=0, name="Schematic sink",
    )
    # The pipe and outlet stay fixed, meeting the shifted symbol's flat bottom.
    sewer_schematic.add_line(
        (sewer_schematic_sink_pipe_x, sewer_schematic_sink_z-0.10),
        (sewer_schematic_sink_pipe_x, sewer_schematic_sink_z),
        color="black", name="Schematic sink fixed outlet",
    )
    # Place the dishwasher caption beside its connector, clear of the sink bowl.
    dishwasher_caption = house.model.by_guid(ifcopenshell.util.element.get_pset(
        sewer_schematic_dishwasher, "BBIM_SanitarySymbol", "IdentifierAnnotation",
    ))
    dishwasher_caption_point = (sewer_schematic_stack_x-1.05, sewer_schematic_dishwasher_z+0.24+0.30)
    dishwasher_caption_matrix = ifcopenshell.util.placement.get_local_placement(dishwasher_caption.ObjectPlacement)
    dishwasher_caption_matrix[:2, 3] = dishwasher_caption_point
    ifcopenshell.api.geometry.edit_object_placement(
        house.model, product=dishwasher_caption, matrix=dishwasher_caption_matrix, is_si=True,
    )
    caption_appearance = ifcopenshell.util.element.get_pset(dishwasher_caption, "EPset_Annotation")
    ifcopenshell.api.pset.edit_pset(
        house.model, pset=house.model.by_id(caption_appearance["id"]),
        properties={"Classes": caption_appearance["Classes"].replace("drawing-text-size-2p5", "drawing-text-size-2p2")},
    )
    caption_data = ifcopenshell.util.element.get_pset(dishwasher_caption, "BBIM_DrawingText")
    ifcopenshell.api.pset.edit_pset(
        house.model, pset=house.model.by_id(caption_data["id"]),
        properties={"Point": json.dumps(dishwasher_caption_point), "FontSize": 2.2},
    )
    for distance, outlet_z, name in (
        (0.5, sewer_schematic_upper_floor+0.20, "Toilet branch connection"),
        (1.5, sewer_schematic_dishwasher_z, "Dishwasher branch connection"),
        (1.7, sewer_schematic_sink_z-0.10, "Sink branch connection"),
    ):
        fixture_x = sewer_schematic_stack_x-distance
        sewer_schematic.add_line(
            (fixture_x, sewer_schematic_left_start_z+distance*sewer_schematic_left_slope),
            (fixture_x, outlet_z), color="orange", line_width=SEWER_LINE_WIDTH,
            name=name,
        )
    # Join both fixtures in the floor build-up, before the shared ceiling penetration.
    sewer_schematic_ground_branch_z = -0.10
    sewer_schematic_ground_branch_slope = 0.03
    sewer_schematic.add_toilet(
        x=sewer_schematic_stack_x-0.5, z=0.20, name="Schematic ground toilet",
    )
    sewer_schematic.add_basin(
        x=sewer_schematic_stack_x+0.5, z=0.65,
        outlet_length=0.10, name="Schematic ground basin",
    )
    for direction, outlet_z, name in (
        (-1, 0.20, "Ground toilet"),
        (1, 0.65-0.10, "Ground basin"),
    ):
        fixture_x = sewer_schematic_stack_x+direction*0.5
        branch_z = sewer_schematic_ground_branch_z+0.5*sewer_schematic_ground_branch_slope
        sewer_schematic.add_line(
            (sewer_schematic_stack_x, sewer_schematic_ground_branch_z), (fixture_x, branch_z),
            color="orange", line_width=SEWER_LINE_WIDTH, name=f"{name} horizontal branch",
        )
        sewer_schematic.add_line(
            (fixture_x, branch_z), (fixture_x, outlet_z),
            color="orange", line_width=SEWER_LINE_WIDTH, name=f"{name} vertical connection",
        )
    sewer_schematic_shower_z = 0.03
    sewer_schematic_shower_width = 0.90
    # Centre the tray and its drain at the specified horizontal offset.
    sewer_schematic.add_shower(
        x=sewer_schematic_shower_x+sewer_schematic_shower_width/2,
        z=sewer_schematic_shower_z, width=sewer_schematic_shower_width,
        name="Schematic ground shower",
    )
    sewer_schematic.add_line(
        (sewer_schematic_shower_x, sewer_schematic_shower_z),
        (sewer_schematic_shower_x, sewer_schematic_stack_bottom),
        color="orange", line_width=SEWER_LINE_WIDTH, name="Ground shower down to basement",
    )
    for start_x, name in (
        (sewer_schematic_stack_x, "WC and basin basement collector"),
        (sewer_schematic_shower_x, "Shower basement collector"),
    ):
        sewer_schematic.add_line(
            (start_x, sewer_schematic_stack_bottom),
            (sewer_schematic_merge_x, sewer_schematic_merge_z),
            color="orange", line_width=SEWER_LINE_WIDTH, name=name,
        )
    sewer_schematic.add_line(
        (sewer_schematic_merge_x, sewer_schematic_merge_z),
        (sewer_schematic_merge_x, sewer_schematic_outlet_z),
        color="orange", line_width=SEWER_LINE_WIDTH, name="Combined basement outlet",
    )
    for name, diameter, point in (
        ("Washing machine", 50, (sewer_schematic_stack_x+2.65, sewer_schematic_upper_floor+0.30)),
        ("Basin", 50, (sewer_schematic_stack_x+3.65, sewer_schematic_upper_floor+0.30)),
        ("Toilet", 100, (sewer_schematic_stack_x-0.5, sewer_schematic_left_start_z-0.45)),
        ("Dishwasher", 50, (sewer_schematic_stack_x-1.0, sewer_schematic_upper_floor+0.05)),
        ("Sink", 50, (sewer_schematic_stack_x-2.05, sewer_schematic_upper_floor+0.30)),
        ("Ground toilet", 100, (sewer_schematic_stack_x-0.9, -0.20)),
        ("Ground basin", 50, (sewer_schematic_stack_x+0.85, 0.30)),
        ("Ground shower", 50, (sewer_schematic_shower_x-0.35, -0.20)),
        ("WC and basin basement collector", 100,
         ((sewer_schematic_stack_x+sewer_schematic_merge_x)/2, sewer_schematic_merge_z-0.25)),
        ("Shower basement collector", 50,
         ((sewer_schematic_shower_x+sewer_schematic_merge_x)/2, sewer_schematic_merge_z-0.25)),
        ("Combined basement outlet", 160,
         (sewer_schematic_merge_x+0.45, (sewer_schematic_merge_z+sewer_schematic_outlet_z)/2)),
    ):
        label = sewer_schematic.add_text(
            point, f"DN{diameter}", font_size=2.2, name=f"Schematic {name} DN label",
        )
        appearance = ifcopenshell.util.element.get_pset(label, "EPset_Annotation")
        ifcopenshell.api.pset.edit_pset(
            house.model, pset=house.model.by_id(appearance["id"]),
            properties={"Classes": appearance["Classes"]+" fill-bg"},
        )
    sewer_schematic.render(PROJECT_DIR / "kanal.svg", pdf=PDF_KANAL)


# `kanal` creates the schematic and all three plans; targets also run separately.
if {"kanal", "kanal_upper", "kanal_ground", "kanal_basement"}.intersection(sys.argv):
    sewer_layout = sewer_plan_layout()

if "kanal" in sys.argv or "kanal_upper" in sys.argv:
    kanal_upper = add_plumbing_plan(
        "kanal_upper", upper, 1.20, upper_room_floors,
        room_positions={
            "1.01": (3.5, 7),
            "1.04": ((upper_technical_left_x+upper_technical_right_x)/2, upper_toilet_end_front_y-0.20),
        },
    )
    add_sewer_routes(kanal_upper, sewer_layout["upper_routes"])
    add_sewer_pipe_labels(kanal_upper, sewer_layout["upper_routes"], sewer_layout["upper_pipe_labels"], at_start=True)
    add_sewer_floor_change(kanal_upper, sewer_layout["upper_drop"], "to down", "Down to ground floor")
    add_sewer_floor_change(kanal_upper, sewer_layout["roof_vent"], "to up", "Roof vent up")
    kanal_upper.render(PROJECT_DIR / "kanal_upper.svg", pdf=PDF_KANAL_UPPER)

if "kanal" in sys.argv or "kanal_ground" in sys.argv:
    kanal_ground = add_plumbing_plan("kanal_ground", ground, 2.0, ground_room_floors)
    add_sewer_routes(kanal_ground, sewer_layout["ground_routes"])
    add_sewer_pipe_labels(kanal_ground, sewer_layout["ground_routes"], sewer_layout["ground_pipe_labels"], at_start=True)
    # Riser arrows show continuation away from the circle, not water flow.
    add_sewer_floor_change(kanal_ground, sewer_layout["upper_drop"], "to up", "From upper floor")
    add_sewer_floor_change(kanal_ground, sewer_layout["shower_drop"], "to down", "Shower down to basement")
    add_sewer_floor_change(kanal_ground, sewer_layout["bathroom_drop"], "to down", "Bathroom down to basement")
    kanal_ground.render(PROJECT_DIR / "kanal_ground.svg", pdf=PDF_KANAL_GROUND)

if "kanal" in sys.argv or "kanal_basement" in sys.argv:
    kanal_basement = add_plumbing_plan(
        "kanal_basement", basement, BASEMENT_FLOOR_THICKNESS+1.01, basement_room_floors,
    )
    add_sewer_routes(kanal_basement, sewer_layout["basement_routes"])
    add_sewer_pipe_labels(kanal_basement, sewer_layout["basement_routes"], sewer_layout["basement_pipe_labels"])
    add_sewer_floor_change(kanal_basement, sewer_layout["shower_drop"], "to up", "Shower from ground floor")
    add_sewer_floor_change(kanal_basement, sewer_layout["bathroom_drop"], "to up", "Bathroom from ground floor")
    add_sewer_floor_change(kanal_basement, sewer_layout["outlet"], "to down", "Drain down")
    outlet_x, outlet_y = sewer_layout["outlet"]
    kanal_basement.add_text(
        (outlet_x-0.6, outlet_y-0.2), "DN160", font_size=2.2,
        name="kanal_basement Drain down DN160",
    )
    kanal_basement.render(PROJECT_DIR / "kanal_basement.svg", pdf=PDF_KANAL_BASEMENT)


if "voda" in sys.argv or "voda_basement" in sys.argv:
    voda_basement = add_plumbing_plan(
        "voda_basement", basement, BASEMENT_FLOOR_THICKNESS+1.01, basement_room_floors,
    )
    voda_basement.add_line_legend([
        {"style": "solid", "color": "blue", "line_width": WATER_LINE_WIDTH,
         "description": "studená"},
    ])
    water_basement_entry, water_basement_riser = water_basement_layout()
    voda_basement.add_poly_line(
        [water_basement_entry, water_basement_riser],
        color="blue", line_width=WATER_LINE_WIDTH, name="Basement cold water route",
    )
    voda_basement.add_change_floor_symbol(
        *water_basement_entry, "from down", color="black", line_width=WATER_LINE_WIDTH,
        name="Basement water supply from below",
    )
    voda_basement.add_change_floor_symbol(
        *water_basement_riser, "to up", color="black", line_width=WATER_LINE_WIDTH,
        name="Basement water to ground floor",
    )
    voda_basement.render(PROJECT_DIR / "voda_basement.svg", pdf=PDF_VODA_BASEMENT)


if "voda" in sys.argv or "voda_ground" in sys.argv:
    voda_ground = add_plumbing_plan("voda_ground", ground, 2.0, ground_room_floors)
    voda_ground.add_line_legend([
        {"style": "solid", "color": "red", "line_width": WATER_LINE_WIDTH,
         "description": "teplá"},
        {"style": "solid", "color": "blue", "line_width": WATER_LINE_WIDTH,
         "description": "studená"},
    ])
    water_bathroom_bottom_left = (BATHROOM_LEFT_X+WATER_WALL_CLEARANCE, BWT+WATER_WALL_CLEARANCE)
    water_bathroom_bottom_right, water_ground_supply = water_basement_layout()
    water_bathroom_top_right, hot_water_top_right = water_riser_positions()
    voda_ground.add_poly_line(
        [water_bathroom_bottom_left, water_bathroom_bottom_right, water_bathroom_top_right],
        color="blue", line_width=WATER_LINE_WIDTH, name="Ground bathroom cold water route",
    )
    voda_ground.add_change_floor_symbol(
        *water_ground_supply, "from down", color="black", line_width=WATER_LINE_WIDTH,
        name="Ground water from basement",
    )
    voda_ground.add_change_floor_symbol(
        *water_bathroom_top_right, "to up", color="black", line_width=WATER_LINE_WIDTH,
        name="Ground water to upper floor",
    )
    hot_water_bottom_left = (water_bathroom_bottom_left[0]+WATER_HOT_ROUTE_OFFSET,
                             water_bathroom_bottom_left[1]+WATER_HOT_ROUTE_OFFSET)
    hot_water_bottom_right = (water_bathroom_bottom_right[0]-WATER_HOT_ROUTE_OFFSET,
                              water_bathroom_bottom_right[1]+WATER_HOT_ROUTE_OFFSET)
    voda_ground.add_poly_line(
        [hot_water_bottom_left, hot_water_bottom_right, hot_water_top_right],
        color="red", line_width=WATER_LINE_WIDTH, name="Ground bathroom hot water route",
    )
    voda_ground.add_change_floor_symbol(
        *hot_water_top_right, "to up", color="black", line_width=WATER_LINE_WIDTH,
        name="Ground hot water to upper floor",
    )
    voda_ground.render(PROJECT_DIR / "voda_ground.svg", pdf=PDF_VODA_GROUND)


if "voda" in sys.argv or "voda_upper" in sys.argv:
    voda_upper = add_plumbing_plan(
        "voda_upper", upper, 1.20, upper_room_floors,
        room_positions={
            "1.01": (3.5, 7),
            "1.04": ((upper_technical_left_x+upper_technical_right_x)/2, upper_toilet_end_front_y-0.20),
        },
    )
    voda_upper.add_line_legend([
        {"style": "solid", "color": "red", "line_width": WATER_LINE_WIDTH,
         "description": "teplá"},
        {"style": "solid", "color": "blue", "line_width": WATER_LINE_WIDTH,
         "description": "studená"},
    ])
    water_upper_cold_riser, water_upper_hot_riser = water_riser_positions()
    water_upper_basin = sewer_fixture_center(upper_hallway_basin)
    water_upper_sink = sewer_fixture_center(kitchen_sink)
    water_upper_dishwasher = sewer_fixture_center(kitchen_dishwasher)
    water_upper_cold_kitchen_x = water_upper_sink[0]
    water_upper_hot_kitchen_x = water_upper_cold_kitchen_x+WATER_HOT_ROUTE_OFFSET
    water_upper_cold_basin_x = water_upper_basin[0]+WATER_HOT_ROUTE_OFFSET
    water_upper_hot_basin_x = water_upper_basin[0]
    water_upper_hot_branch_y = water_upper_hot_riser[1]+WATER_HOT_ROUTE_OFFSET
    water_upper_routes = (
        ("Cold water to basin", "blue", (
            water_upper_cold_riser,
            (water_upper_cold_basin_x, water_upper_cold_riser[1]),
            (water_upper_cold_basin_x, water_upper_basin[1]),
        )),
        ("Hot water to basin", "red", (
            water_upper_hot_riser,
            (water_upper_hot_riser[0], water_upper_hot_branch_y),
            (water_upper_hot_basin_x, water_upper_hot_branch_y),
            (water_upper_hot_basin_x, water_upper_basin[1]),
        )),
        ("Cold water to sink", "blue", (
            water_upper_cold_riser,
            (water_upper_cold_kitchen_x, water_upper_cold_riser[1]),
            (water_upper_cold_kitchen_x, water_upper_sink[1]),
        )),
        ("Hot water to sink", "red", (
            (water_upper_hot_riser[0], water_upper_hot_branch_y),
            (water_upper_hot_kitchen_x, water_upper_hot_branch_y),
            (water_upper_hot_kitchen_x, water_upper_sink[1]+WATER_HOT_ROUTE_OFFSET),
        )),
        ("Cold water to dishwasher", "blue", (
            (water_upper_cold_kitchen_x, water_upper_cold_riser[1]),
            (water_upper_cold_kitchen_x, water_upper_dishwasher[1]),
        )),
    )
    for name, color, points in water_upper_routes:
        voda_upper.add_poly_line(
            points, color=color, line_width=WATER_LINE_WIDTH, name=f"Upper {name}",
        )
    for name, point in (("cold", water_upper_cold_riser), ("hot", water_upper_hot_riser)):
        voda_upper.add_change_floor_symbol(
            *point, "from down", color="black", line_width=WATER_LINE_WIDTH,
            name=f"Upper {name} water from ground floor",
        )
    voda_upper.render(PROJECT_DIR / "voda_upper.svg", pdf=PDF_VODA_UPPER)


if "elektro" in sys.argv or "elektro_basement" in sys.argv:
    elektro_basement = add_electrical_plan(
        "elektro_basement", basement, BASEMENT_FLOOR_THICKNESS+1.01, basement_room_floors,
        extra_symbols=(("socket", "Zásuvka"), ("d_socket", "Dvojitá zásuvka"), ("socket3f", "Zásuvka 380V, 3 fáze"),
                       ("switch", "Vypínač")),
    )
    add_electrical_trunk_legend(elektro_basement, extra_lines=(
        {"color": "blue", "line_width": ELECTRICAL_LINE_WIDTH, "description": "Zásuvkový okruh"},
        {"color": "red", "line_width": ELECTRICAL_LINE_WIDTH, "description": "3-fázový okruh"},
        {"color": ELECTRICAL_LIGHT_CIRCUIT_COLOR, "line_width": ELECTRICAL_LINE_WIDTH,
         "description": "Světelný okruh"},
    ))
    elektro_basement.add_change_floor_symbol(
        *electrical_trunk_layout()["down"], "from up", color="black",
        line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH, name="elektro_basement Cables from ground floor",
    )
    add_room_socket_routes(elektro_basement, "S.01-S.05", electrical_basement_socket_layout())
    add_room_electrical_routes(elektro_basement, "S.03", electrical_basement_garage_light_layout())
    add_room_electrical_routes(elektro_basement, "S.01", electrical_basement_s01_light_layout())
    add_room_electrical_routes(elektro_basement, "S.02", electrical_basement_s02_light_layout())
    add_room_electrical_routes(elektro_basement, "S.04", electrical_basement_s04_light_layout())
    add_room_electrical_routes(elektro_basement, "S.05", electrical_basement_s05_light_layout())
    garden_socket_layout = electrical_basement_garden_socket_layout()
    elektro_basement.add_poly_line(
        garden_socket_layout["route"], color="blue", line_width=ELECTRICAL_LINE_WIDTH,
        foreground=True, name="elektro_basement Garden outside socket feed",
    )
    elektro_basement.add_socket_symbol(
        garden_socket_layout["socket"], "up", line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_basement Garden outside single socket",
    )
    for name, route, socket, direction in electrical_basement_three_phase_layout():
        elektro_basement.add_poly_line(
            route, color="red", line_width=ELECTRICAL_LINE_WIDTH,
            foreground=True, name=f"elektro_basement {name} three-phase cable",
        )
        elektro_basement.add_socket_symbol(
            socket, direction, color="red", line_width=ELECTRICAL_LINE_WIDTH,
            name=f"elektro_basement {name} 380V socket",
        )
    elektro_basement.render(PROJECT_DIR / "elektro_basement.svg", pdf=PDF_ELEKTRO_BASEMENT)

if "elektro" in sys.argv or "elektro_ground" in sys.argv:
    elektro_ground = add_electrical_plan(
        "elektro_ground", ground, 2.0, ground_room_floors,
        extra_symbols=(("d_socket", "Dvojitá zásuvka"), ("switch", "Vypínač")),
    )
    add_electrical_trunk_legend(elektro_ground, extra_lines=(
        {"color": ELECTRICAL_LIGHT_CIRCUIT_COLOR, "line_width": ELECTRICAL_LINE_WIDTH,
         "description": "Světelný okruh"},
        {"color": "blue", "line_width": ELECTRICAL_LINE_WIDTH, "description": "Zásuvkový okruh"},
        {"color": ELECTRICAL_FAN_COIL_CIRCUIT_COLOR, "line_width": ELECTRICAL_LINE_WIDTH,
         "description": "Okruh Fancoily"},
    ))
    add_room_electrical_routes(elektro_ground, "0.01", electrical_room01_layout())
    add_room_electrical_routes(elektro_ground, "0.02", electrical_room02_layout())
    add_room_electrical_routes(elektro_ground, "0.03", electrical_room03_layout())
    add_room_electrical_routes(elektro_ground, "0.04", electrical_room04_layout())
    add_room_electrical_routes(elektro_ground, "0.05", electrical_room05_layout())
    for name, points in electrical_ground_fan_coil_layout()["routes"]:
        elektro_ground.add_poly_line(
            points, color=ELECTRICAL_FAN_COIL_CIRCUIT_COLOR, line_width=ELECTRICAL_LINE_WIDTH,
            foreground=True, name=f"elektro_ground Fan coil circuit {name}",
        )
    elektro_ground.add_change_floor_symbol(
        *electrical_ground_fan_coil_layout()["junction"], "to up",
        color="black", line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH,
        name="elektro_ground Fan coil circuit to upper floor",
    )
    electrical_trunks = electrical_trunk_layout()
    for direction, points in electrical_trunks["routes"]:
        elektro_ground.add_poly_line(
            points, color="black", line_width=ELECTRICAL_TRUNK_LINE_WIDTH,
            name=f"elektro_ground Bundled cables to {direction}",
        )
        elektro_ground.add_change_floor_symbol(
            *points[-1], f"to {direction}", color="black", line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH,
            name=f"elektro_ground Cable riser {direction}",
        )
    elektro_ground.add_stair_annotation(lower_stairs)
    elektro_ground.add_stair_annotation(upper_stairs)
    elektro_ground.add_stair_landing_annotation(middle_stair_landing)
    stair_light_layout = electrical_stair_lighting_layout()
    add_ground_stair_lighting_routes(elektro_ground, stair_light_layout)
    elektro_ground.add_light_symbol(
        stair_light_layout["outside_light"],
        color="blue", line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_ground Outside entrance landing light",
    )
    elektro_ground.render(PROJECT_DIR / "elektro_ground.svg", pdf=PDF_ELEKTRO_GROUND)

if "elektro" in sys.argv or "elektro_upper" in sys.argv:
    elektro_upper = add_electrical_plan(
        "elektro_upper", upper, 1.20, upper_room_floors, skip_lights=("1.01", "1.02"),
        extra_symbols=(("switch", "Vypínač"), ("d_socket", "Dvojitá zásuvka"),
                       ("socket3f", "Zásuvka 380V, 3 fáze")),
    )
    add_electrical_trunk_legend(elektro_upper, extra_lines=(
        {"color": ELECTRICAL_LIGHT_CIRCUIT_COLOR, "line_width": ELECTRICAL_LINE_WIDTH,
         "description": "Světelný okruh"},
        {"color": "blue", "line_width": ELECTRICAL_LINE_WIDTH, "description": "Zásuvkový okruh"},
        {"color": "red", "line_width": ELECTRICAL_LINE_WIDTH, "description": "3-fázový okruh"},
        {"color": ELECTRICAL_FAN_COIL_CIRCUIT_COLOR, "line_width": ELECTRICAL_LINE_WIDTH,
         "description": "Okruh Fancoily"},
    ))
    upper_fan_coil_layout = electrical_upper_fan_coil_layout()
    elektro_upper.add_change_floor_symbol(
        *upper_fan_coil_layout["riser"], "from down", color="black",
        line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH, name="elektro_upper Fan coil circuit from ground floor",
    )
    elektro_upper.add_poly_line(
        upper_fan_coil_layout["route"], color=ELECTRICAL_FAN_COIL_CIRCUIT_COLOR,
        line_width=ELECTRICAL_LINE_WIDTH, foreground=True,
        name="elektro_upper Fan coil circuit to garden unit",
    )
    elektro_upper.add_change_floor_symbol(
        *electrical_trunk_layout()["up"], "from down", color="black",
        line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH, name="elektro_upper Cables from ground floor",
    )
    add_room_electrical_routes(elektro_upper, "1.03", electrical_upper_hallway_layout())
    add_room_electrical_routes(elektro_upper, "1.04", electrical_upper_toilet_layout())
    living_light_layout = electrical_upper_living_light_layout()
    add_room_electrical_routes(elektro_upper, "1.01", {
        **living_light_layout, **electrical_upper_living_garden_socket_layout(),
    })
    add_room_socket_routes(elektro_upper, "1.01 street-side", electrical_upper_living_street_socket_layout())
    cooker_layout = electrical_upper_cooker_layout()
    elektro_upper.add_poly_line(
        cooker_layout["route"], color="red", line_width=ELECTRICAL_LINE_WIDTH,
        foreground=True, name="elektro_upper Cooker three-phase cable",
    )
    elektro_upper.add_socket_symbol(
        cooker_layout["socket"], "left", color="red", line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_upper Cooker 380V socket",
    )
    technical_socket_layout = electrical_upper_technical_socket_layout()
    elektro_upper.add_poly_line(
        technical_socket_layout["route"], color="blue", line_width=ELECTRICAL_LINE_WIDTH,
        foreground=True, name="elektro_upper Room 1.02 socket feed",
    )
    elektro_upper.add_socket_symbol(
        technical_socket_layout["socket"], "left", double=True, line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_upper Room 1.02 socket",
    )
    for name, point in living_light_layout["lights"]:
        elektro_upper.add_light_symbol(
            point, color="blue", line_width=ELECTRICAL_LINE_WIDTH,
            name=f"elektro_upper Living room {name} light",
        )
    elektro_upper.include_element(stair_railing)
    elektro_upper.include_element(lower_stair_railing)
    elektro_upper.include_element(stair_landing_gap_railing)
    elektro_upper.add_stair_annotation(lower_stairs)
    elektro_upper.add_stair_annotation(upper_stairs)
    elektro_upper.add_stair_landing_annotation(middle_stair_landing)
    stair_light_layout = electrical_stair_lighting_layout()
    elektro_upper.add_change_floor_symbol(
        *stair_light_layout["riser"], "from down", color="black", line_width=ELECTRICAL_FLOOR_CHANGE_LINE_WIDTH,
        name="elektro_upper Stair light from ground floor",
    )
    elektro_upper.add_poly_line(
        stair_light_layout["upper_route"],
        color=ELECTRICAL_LIGHT_CIRCUIT_COLOR, line_width=ELECTRICAL_LINE_WIDTH, foreground=True,
        name="elektro_upper Stair landing light cable",
    )
    elektro_upper.add_switch_symbol(
        stair_light_layout["upper_switch"], "right", line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_upper Stair landing light switch",
    )
    elektro_upper.add_light_symbol(
        stair_light_layout["landing_light"],
        color="blue", line_width=ELECTRICAL_LINE_WIDTH,
        name="elektro_upper Middle stair landing light",
    )
    elektro_upper.render(PROJECT_DIR / "elektro_upper.svg", pdf=PDF_ELEKTRO_UPPER)
