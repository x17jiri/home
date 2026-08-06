from ifc_utils import *

house = House("My house")

ground = house.storey("Ground floor", elevation=0)

load_bearing_wall = house.wall_type(
    "Load bearing wall - VPC 24 cm",
    layers=[
        ("Brick", 0.25),
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

# Load-bearing walls

wall_front = ground.wall((0, 0), (12, 0), wall_type=load_bearing_wall, height=2.75)
wall_4 = ground.wall((12, 0), (12, 8), wall_type=load_bearing_wall, height=2.75)
wall_back = ground.wall((12, 8), (0, 8), wall_type=load_bearing_wall, height=2.75)
wall_1 = ground.wall((0, 8), (0, 0), wall_type=load_bearing_wall, height=2.75)
wall_2 = ground.wall((wall2_x, 0), (wall2_x, 8), wall_type=load_bearing_wall, height=2.75)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, 8), wall_type=load_bearing_wall, height=2.75)

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
	height=2.125,
	operation="SINGLE_SWING_RIGHT"
)
wall_front.add_window(
    at=wall3_x+1.5+0.5,
    width=0.75,
    height=2.125,
    sill_height=2.125-0.375,
    partition="SINGLE_PANEL",
)

# Back windows
wall_back.add_window(
	at=2.75, width=0.5, sill_height=0.875, height=2.25)
wall_back.add_window(
	at=0.25+3.5+0.25+0.375, width=1.5, sill_height=0.875, height=2.25)
wall_back.add_window(
	at=0.25+3.5+0.25+0.375+1.5+0.75,
	width=1.5, sill_height=0, height=2.125)

wall_back.add_window(
	at=0.25+3.5+0.25+4.5+0.25+0.75,
	width=1.5, sill_height=0.875, height=2.25)

# Drawing 1
drawing1 = house.add_drawing("Drawing 1", x=6, y=4, z=2, radius=8)

# The Rockwool occupies the right side of each wall axis.  These annotations
# belong only to Drawing 1 and follow the Rockwool centre lines.
#drawing1.add_batting((-0.10, -0.10), (12.10, -0.10), thickness=0.12)
#drawing1.add_batting((12.10, -0.10), (12.10, 8.10), thickness=0.12)
#drawing1.add_batting((12.10, 8.10), (-0.10, 8.10), thickness=0.12)
#drawing1.add_batting((-0.10, 8.10), (-0.10, -0.10), thickness=0.12)

house.write("house.ifc")
drawing1.render("house.svg", png=True, png_dpi=600)
