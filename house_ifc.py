from ifc_utils import *

house = House(
    "My house",
    colors={
        "wall": "#ffffff",
        "door": "#8B5A2B",
        "window": "#4A90E2",
    },
)

ground = house.storey("Ground floor", elevation=0)

load_bearing_wall = house.wall_type(
    "Load bearing wall - VPC 240 mm",
    layers=[
        ("Brick", 0.25),
        "axis",
    ],
)

partition_wall = house.wall_type(
    "Partition wall - VPC 115 mm",
    layers=[
        ("Brick", 0.115),
        "axis",
    ],
)

facade_insulation = house.wall_type(
    "Facade insulation - Rockwool",
    layers=[
        "axis",
        ("Rockwool", 0.20),
    ],
)

wall2_x = 0.25 + 3 + 0.25;
wall3_x = wall2_x + 4.5 + 0.25;
ground_floor_height = 0.25+2.75
stair_height = 3.0-0.2+0.25+0.11
step_count = 17

# Load-bearing walls

wall_front = ground.wall((0, 0), (12, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_4 = ground.wall((12, 0), (12, 8), wall_type=load_bearing_wall, height=ground_floor_height)
wall_back = ground.wall((12, 8), (0, 8), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1 = ground.wall((0, 8), (0, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_2 = ground.wall((wall2_x, 0), (wall2_x, 8), wall_type=load_bearing_wall, height=ground_floor_height)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, 8), wall_type=load_bearing_wall, height=ground_floor_height)

ground.connect_wall(wall_1, wall_front)
ground.connect_wall(wall_1, wall_back)

ground.connect_wall(wall_2, wall_front, is_atpath=True)
ground.connect_wall(wall_2, wall_back, is_atpath=True)

ground.connect_wall(wall_3, wall_front, is_atpath=True)
ground.connect_wall(wall_3, wall_back, is_atpath=True)

ground.connect_wall(wall_4, wall_front)
ground.connect_wall(wall_4, wall_back)

# Front door/window

wall_front.add_door(
	at=wall3_x+0.25,
	opening_width=1.125, width=0.9,
	height=0.25+2.125,
	sill_height=0.2,
	operation="SINGLE_SWING_RIGHT"
)
wall_front.add_window(
    at=wall3_x+1.5+0.5,
    width=0.75,
    height=0.25+2.125,
    sill_height=0.25+2.125-0.375,
    partition="SINGLE_PANEL",
)

# Back windows
wall_back.add_window(
	at=2.75, width=0.5, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_window(
	at=0.25+3.5+0.25+0.5, width=1, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_window(
	at=0.25+3.5+0.25+0.375+1.5+0.75,
	width=1.5, sill_height=0.25+0.25, height=0.25+2.125)

wall_back.add_window(
	at=0.25+3.5+0.25+4.5+0.25+0.75,
	width=1.5, sill_height=0.25+0.875, height=0.25+2.25)

# Bathroom
wall_bathroom = ground.wall(
	(0.25+3, 0.25+2.5), (0.25, 0.25+2.5),
	wall_type=partition_wall, height=ground_floor_height)

# Kitchen
wall_kitchen = ground.wall(
	(0.25+3+0.25+4.5, 0.25+1.75), (0.25+3+0.25, 0.25+1.75),
	wall_type=partition_wall, height=ground_floor_height)

# Main hallway
stairs1 = ground.stair(
    (12-0.25-0.5, 0.25+1+0.27*8),       # bottom centre
    (12-0.25-0.5, 0.25+1),       # upper landing edge centre
    width=1.0,
    height=stair_height/17*9,
    risers=9,
    name="Main stair",
    color="#C8B090",
    underside="sloped",
    waist_thickness=0.15,)

stairs2 = ground.stair(
    (12-0.25-1.5, 0.25+1),       # bottom centre
    (12-0.25-1.5, 0.25+1+0.27*7),       # upper landing edge centre
    width=1.0,
    height=stair_height/17*8,
    risers=8,
    start_height=stairs1.end_height,
    name="Main stair",
    color="#C8B090",
    underside="sloped",
    waist_thickness=0.15,)

stair_landing = ground.stair_landing(
    (12-0.25-2.0, 0.25),
    (12-0.25, 0.25+1.0),
    height=stairs1.end_height,
    thickness=0.20,
    name="Main stair landing",
    color="#C8B090",
)

# Chimney

chimney = ground.chimney(
    center=(0.25+3+0.25+4.5+0.25+0.6+0.2, 4+0.21+0.2),
    size=0.4,
    height=8.0,
    flue_diameter=0.18,
    start_height=0,
    name="Main chimney",
    color="#B8A99A",
)

# Opening from main to side hallway
opening = wall_3.add_opening(
    at=0.25+0.5,
    width=1.0,
    height=2.125,
    sill_height=0.2,
    name="Hallway passage",
    show_overhead=True,
)

# Drawing 1
drawing1 = house.add_drawing("Drawing 1", x=6, y=4, z=0.25+2, radius=8)

drawing1.add_stair_annotation(stairs1)
drawing1.add_stair_annotation(stairs2)
drawing1.add_chimney_annotation(chimney)

# The Rockwool occupies the right side of each wall axis.  These annotations
# belong only to Drawing 1 and follow the Rockwool centre lines.
#drawing1.add_batting((-0.10, -0.10), (12.10, -0.10), thickness=0.12)
#drawing1.add_batting((12.10, -0.10), (12.10, 8.10), thickness=0.12)
#drawing1.add_batting((12.10, 8.10), (-0.10, 8.10), thickness=0.12)
#drawing1.add_batting((-0.10, 8.10), (-0.10, -0.10), thickness=0.12)

house.write("house.ifc")
drawing1.render("house.svg", png=True, png_dpi=600)
