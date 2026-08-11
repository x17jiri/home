
# Kamna:
#	Eva Calor Arianna - Krbová kamna na dřevo,hermetická
#	https://www.centrumvytapeni.cz/eva-calor-arianna-krbova-kamna-na-drevo-hermeticka/

# Cerpadlo:
#	Tepelné čerpadlo LG Therma V Split 12kW HN1636M+HU123MA (model 2023)
#	https://www.vzduchotechnika1.cz/lg-therma-v-split-12kw-hn1636m-hu123ma

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
upper = house.storey("Upper floor", elevation=3.0 + 0.25)

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
        ("Brick", 0.15),
        "axis",
    ],
)
sdk_wall = house.wall_type(
    "SDK wall - 100 mm",
    layers=[
        ("SDK", 0.100),
        "axis",
    ],
	color="#dfefcf"
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
	at=0.25+3.5+0.25+0.5+1.5+1,width=1, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_window(
	at=0.25+3.5+0.25+0.5,
	width=1.5, sill_height=0.25+0.25, height=0.25+2.125)
wall_back.add_window(
	at=0.25+3.5+0.25+4.5+0.25+0.75,
	width=1.5, sill_height=0.25+0.875, height=0.25+2.25)

# Bathroom
wall_bathroom = ground.wall(
	(0.25, 0.25+2.3), (0.25+3, 0.25+2.3),
	wall_type=partition_wall, height=ground_floor_height)
ground.furniture(
    "LG",
    kind="USERDEFINED",
    size=(1.2, 0.5, 1.5),
    color="#ffffff",
    center=(0.25+2.5, 0-0.25),
)
ground.furniture(
    "LG",
    kind="USERDEFINED",
    size=(0.5, 0.4, 0.9),
    color="#ffffff",
    center=(0.25+2.7, 0.25+0.2),
)
ground.furniture(
    "TUV",
    kind="USERDEFINED",
    size=(0.7, 0.7, 2.0),
    color="#ffffff",
    center=(0.25+0.4, 0.25+0.35),
)
#ground.furniture(
#    "Pracka",
#    kind="USERDEFINED",
#    size=(0.7, 0.7, 2.0),
#    color="#ffffff",
#    center=(0.25+1.2, 0.25+0.35),
#)
ground.asset(
    "Pracka",
    asset="washing_machine",
    center=(0.25+1.2, 0.25+0.35),
	rotation=90,
)
#ground.furniture(
#    "Umyv",
#    kind="USERDEFINED",
#    size=(0.7, 0.7, 2.0),
#    color="#ffffff",
#    center=(0.25+2, 0.25+0.35),
#)
ground.asset(
    "Umyv",
    asset="basin_large",
    center=(0.25+2, 0.25+0.35),
	rotation=180,
)
#ground.furniture(
#    "Sprcha",
#    kind="USERDEFINED",
#    size=(1, 1, 2.0),
#    color="#ffffff",
#    center=(0.25+0.5, 0.25+1.8),
#)
ground.asset(
    "Sprcha",
    asset="shower_90x90",
    center=(0.25+0.5, 0.25+1.8),
	rotation=90,
)
#ground.furniture(
#    "WC",
#    kind="USERDEFINED",
#    size=(0.7, 0.4, 1.0),
#    color="#ffffff",
#    center=(0.25+2.6, 0.25+1.8),
#)
ground.asset(
    "WC",
    asset="toilet_without_cistern",
    center=(0.25+2.6, 0.25+1.8),
    rotation=-90,
)

# Kitchen, Kuchyn
wall_kitchen = ground.wall(
	(0.25+3+0.25, 0.25+1.7),
	(0.25+3+0.25+4.5, 0.25+1.7),
	wall_type=partition_wall, height=ground_floor_height)
kitchen_door = wall_kitchen.add_door(
	at=2.75,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=0.2,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=True,
)

# Pokoj Risanek
wall_2.add_door(
	at=8.0-0.25-3.0,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=0.2,
	operation="SINGLE_SWING_LEFT",
#	reverse_swing=True,
)

# Bathroom
wall_2.add_door(
    at=0.25+0.625,
    opening_width=1.0, width=0.9,
    height=2.125,
    sill_height=0.2,
	reverse_swing=True,
)

# Main hallway
stairs1 = ground.stair(
    (12-0.25-0.5, 0.25+1+0.27*8),       # bottom centre
    (12-0.25-0.5, 0.25+1),       # upper landing edge centre
    width=1.0,
	start_height=0.2,
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

# Vedlejsi chodba
ground.furniture(
    "vestavna skrin",
    kind="USERDEFINED",
    size=(4.4, 0.5, 1.5),
    color="#ffffff",
    center=(0.25+3+0.25+4.5/2, 0.25+0.6/2),
)

# Chimney
CHIMNEY_DIST=0.5
chimney = ground.chimney(
    center=(0.25+3+0.25+4.5+0.25+CHIMNEY_DIST+0.2, 4.43),
    size=0.4,
    height=8.8,
    flue_diameter=0.18,
    start_height=0,
    name="Main chimney",
    color="#B8A99A",
)
# zed loznice
w0 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.5, 4.25),
	(0.25+3+0.25+4.5+0.25, 4.25),
	wall_type=partition_wall, height=ground_floor_height)
w1 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.9, 4.63),
	(0.25+3+0.25+4.5+0.25+3.5, 4.63),
	wall_type=partition_wall, height=ground_floor_height)
wall_3.add_door(
    at=8-0.25-1.5,
    opening_width=1.0, width=0.9,
    height=2.125,
    sill_height=0.2,
    name="Bedroom door",
	operation="SINGLE_SWING_RIGHT"
)
# Vyklenek Krb
w2 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.5, 5.25),
	(0.25+3+0.25+4.5+0.25+0.5, 4.65),
	wall_type=partition_wall, height=ground_floor_height)
w3 = ground.wall(
	(0.25+3+0.25+4.5+0.25, 4.25+1.0),
	(0.25+3+0.25+4.5+0.25+0.4, 4.25+1.0),
	wall_type=partition_wall, height=ground_floor_height)
wall_3.add_opening(
    at=4.25,
    width=1.0,
    height=2.125,
    sill_height=0.2,
    name="Fireplace opening",
)
ground.connect_wall(w1, w2)
ground.connect_wall(w2, w3)

ground.furniture(
    "Krb",
    kind="USERDEFINED",
    size=(0.5, 0.5, 1.5),
    color="#ffff2B",
    center=(0.25+3+0.25+4.5-0.27, 4.75),
	start_height=0.2,
#    rotation=90,
)

# Kuchyn
print("SEARCH: ", "\n".join(str(x) for x in house.assets.search("sink")))
ground.furniture(
	"Drez",
    kind="USERDEFINED",
    size=(0.7, 0.95, 0.8),
    center=(0.25+3+0.25+0.35, 0.25+1.7+0.15+(0.95/2)),
)
ground.furniture(
	"Mycka",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
    center=(0.25+3+0.25+0.35, 0.25+1.7+0.15+0.35+0.95),
)
ground.furniture(
	"Lednice",
    kind="USERDEFINED",
    size=(0.7, 1, 2),
    center=(0.25+3+0.25+0.35, 4.75-0.5),
)
ground.furniture(
	"Sporak",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
    center=(0.25+3+0.25+0.35+0.7, 0.25+1.7+0.15+0.35),
)
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(1.25, 0.7, 0.8),
    center=(0.25+3+0.25+0.7+0.7+1.25/2, 0.25+1.7+0.15+0.35),
)
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(0.7, 1.8, 0.8),
    center=(0.25+3+0.25+4.5-0.35, 0.25+1.7+0.15+0.9),
)

# Loznice
bed = ground.furniture(
    "Postel",
    kind="BED",
    size=(1.6, 2.0, 0.5),
    color="#8B5A2B",
    center=(0.25+3+0.25+4.5+0.25+3.5/2, 8-0.25-1),
)

# Opening from main to side hallway
opening = wall_3.add_opening(
    at=0.25+0.625,
    width=1.0,
    height=2.125,
    sill_height=0.2,
    name="Hallway passage",
    show_overhead=True,
)

# MIAKO
ceiling1 = upper.miako_slab(
    "Ceiling 1",
    start=(0.1, 8.0-0.25+0.04),
    end=(0.25+3.0+0.25-0.15, 8.0-0.25+0.04),
    top=0.11,
	topping=0.11,
	beam_height=0.25,
	block_height=0.25,
    direction=(0, -1),
    structure=[
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"narrow",
		],
)
ceiling2 = upper.miako_slab(
    "Ceiling 2",
    start=(0.25+3.0+0.125, 8.0-0.25+0.04),
    end=(0.25+3.0+0.25+4.5+0.125, 8.0-0.25+0.04),
    top=0.11,
	topping=0.11,
	beam_height=0.25,
	block_height=0.25,
    direction=(0, -1),
    structure=[
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"narrow",
		],
)
ceiling3 = upper.miako_slab(
    "Ceiling 3",
    start=(0.25+3.0+0.25+4.5+0.15, 8.0-0.25+0.04),
    end=(0.25+3.0+0.25+4.5+0.15+3.75, 8.0-0.25+0.04),
    top=0.11,
	topping=0.11,
	beam_height=0.25,
	block_height=0.25,
    direction=(0, -1),
    structure=[
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"beam",
		],
)

UNDER_HOLE = 2.80

# upper floor
wall_cuts_1_4 = [
	(
		(0, 0.125-0.08, 3.25+1.25+0.12),
		(5, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
		(0, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
	),
	(
		(0, 8.0-0.125+0.08, 3.25+1.25+0.12),
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
		(5, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
	),
	(
		(0, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25),
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25),
		(5, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25),
	),
#	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
]
wall_cuts_2_3 = [
	(
		(0, 0.125-0.08, 3.25+1.25+0.12),
		(0, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
		(5, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
	),
	(
		(0, 8.0-0.125+0.08, 3.25+2.5+0.12),
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
		(5, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24),
	),
	(
		(0, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25),
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25),
		(5, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25),
	),
]

wall_dormer = upper.wall((0.25+3+0.25+4.5+0.25, 8), (0.25+3, 8), wall_type=load_bearing_wall, height=1.25, start_height=1.25)
wall_front = upper.wall((0, 0), (12, 0), wall_type=load_bearing_wall, height=1.25)
wall_back = upper.wall((12, 8), (0, 8), wall_type=load_bearing_wall, height=1.25)
wall_1 = upper.wall(
	(0, 8), (0, 0),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_1.add_opening(at=0, width=0.25, height=0.25, sill_height=1.25)
wall_1.add_opening(at=7.75, width=0.25, height=0.25, sill_height=1.25)

wall_2 = upper.wall(
	(wall2_x, 0), (wall2_x, 8),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_2.add_opening(at=3.5, width=1, height=0.25, sill_height=UNDER_HOLE)
wall_3 = upper.wall(
	(wall3_x, 0), (wall3_x, 8),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_3.add_opening(at=3.5, width=1, height=0.25, sill_height=UNDER_HOLE)

wall_4 = upper.wall(
	(12, 0), (12, 8),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_4.add_opening(at=0, width=0.25, height=0.25, sill_height=1.25)
wall_4.add_opening(at=7.75, width=0.25, height=0.25, sill_height=1.25)

wall_pracovna = upper.wall(
	start=(0.25+3+0.25+4.5, 2.7),
	end=(0.25+3+0.25, 2.7),
	wall_type=sdk_wall, height=4, cuts=wall_cuts_2_3)
wall_pracovna.add_door(
	at=2.2,
	opening_width=1, width=0.9,
	height=2.25,
	sill_height=0.11,
	operation="SINGLE_SWING_RIGHT")
upper.furniture(
    "zachod nahore",
    kind="USERDEFINED",
    size=(1.2, 1, 2.1),
    color="#ffff2B",
    center=(3.5+0.6, 0.25+2.35-0.5),
	start_height=0.11,
)

upper.connect_wall(wall_1, wall_front)
upper.connect_wall(wall_1, wall_back)

upper.connect_wall(wall_2, wall_front, is_atpath=True)
upper.connect_wall(wall_2, wall_back, is_atpath=True)
upper.connect_wall(wall_2, wall_dormer)

upper.connect_wall(wall_3, wall_front, is_atpath=True)
upper.connect_wall(wall_3, wall_back, is_atpath=True)
upper.connect_wall(wall_3, wall_dormer)

upper.connect_wall(wall_4, wall_front)
upper.connect_wall(wall_4, wall_back)


beam1 = upper.beam(
    "Beam",
    start=(0, 4.0-0.8, 3.25+UNDER_HOLE+0.5+0.12),
    end=(12, 4.0-0.8, 3.25+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam2 = upper.beam(
    "Beam",
    start=(0, 4.0+0.8, 3.25+UNDER_HOLE+0.5+0.12),
    end=(12, 4.0+0.8, 3.25+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam3 = upper.beam(
    "Beam",
    start=(0, 0.125, 3.25+1.25+0.06),
    end=(12, 0.125, 3.25+1.25+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam4 = upper.beam(
    "Beam",
    start=(0, 8-0.125, 3.25+1.25+0.06),
    end=(12, 8-0.125, 3.25+1.25+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam_dormer = upper.beam(
    "Beam",
    start=(0.25+3+0.25+4.5+0.25+0.3, 8-0.125, 3.25+2.5+0.06),
    end=(0.25+3-0.3, 8-0.125, 3.25+2.5+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)

# Okna obyvak
wall_dormer.add_window(
	at=0.25+0.5,width=1.5, sill_height=1.25, height=2.25)
wall_dormer.add_window(
	at=0.25+2.5,
	width=1.5, sill_height=1.25, height=2.25)
# Dvere obyvak
wall_3.add_door(
	at=4.43+0.07+0.125,
	opening_width=1, width=0.9,
	height=2.25,
	sill_height=0.11,
	operation="SINGLE_SWING_RIGHT")
# Dvere pokojik nahore
wall_2.add_door(
	at=2.75,
	opening_width=1, width=0.9,
	height=2.25,
	sill_height=0.11,
	operation="SINGLE_SWING_RIGHT")
wall_2.add_door(
	at=4.25,
	opening_width=1, width=0.9,
	height=2.25,
	sill_height=0.11,
	operation="SINGLE_SWING_LEFT")
# Okna pokojik nahore
wall_1.add_window(
	at=2.75,
	width=1,
	height=2.25,
	sill_height=1, partition="SINGLE_PANEL",)
wall_1.add_window(
	at=4.25,
	width=1,
	height=2.25,
	sill_height=1, partition="SINGLE_PANEL",)

# Roof

roof = upper.roof("Main roof")

roof_inner_cuts = [
	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
	((0, 7.75, 0), (10, 7.75, 0), (0, 7.75, 10)),
	((0.25, 0, 0), (0.25, 10, 0), (0.25, 0, 10)),
	((11.75, 0, 0), (11.75, 10, 0), (11.75, 0, 10)),
]

street_roof = roof.plane(
    "Street slope",
    points=(
		(0, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # origin
		(10, 4.0-0.8-0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # +X direction
		(0, 0.125-0.08, 3.25+1.25+0.12), # +Y direction
	),
    cuts=[
		((0, 4, 0), (10, 4, 0), (0, 4, 10)),
		((0, -0.4, 0), (10, -0.4, 0), (0, -0.4, 10)),
	],
)
garden_roof = roof.plane(
    "Garden slope",
    points=(
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # origin
		(10, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # +X direction
		(0, 8.0-0.125+0.08, 3.25+1.25+0.12), # +Y direction
	),
    cuts=[
		((0, 4, 0), (10, 4, 0), (0, 4, 10)),
		((0, 8.4, 0), (10, 8.4, 0), (0, 8.4, 10)),
	],
)
dormer_roof = roof.plane(
    "Dormer slope",
    points=(
		(0, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # origin
		(10, 4.0+0.8+0.07, 3.25+UNDER_HOLE+0.25+0.25+0.24), # +X direction
		(0, 8.0-0.125+0.08, 3.25+2.5+0.12), # +Y direction
	),
    cuts=[
		((0, 4, 0), (10, 4, 0), (0, 4, 10)),
		((0, 8.4, 0), (10, 8.4, 0), (0, 8.4, 10)),
	],
)

# Bonsai creates Outliner collections from spatial containers, but flattens
# ordinary IFC aggregation.  These intentionally artificial storeys provide
# one portable visibility collection for each roof layer in shared IFC files.
roof_layer_storeys = {
	"Thermal insulation 100 mm": house.storey(
		"Roof - -1: 100 mm thermal insulation", elevation=upper.elevation),
	"Vapour barrier": house.storey(
		"Roof - -2: Vapour barrier", elevation=upper.elevation),
	"Thermal insulation 50 mm": house.storey(
		"Roof - -3: 50 mm thermal insulation", elevation=upper.elevation),
	"Gypsum plasterboard": house.storey(
		"Roof - -4: Gypsum plasterboard", elevation=upper.elevation),
	"Rafters": house.storey("Roof - 0: Rafters", elevation=upper.elevation),
	"Roof sheathing": house.storey("Roof - +1: Sheathing", elevation=upper.elevation),
	"Roofing underlay": house.storey("Roof - +2: Underlay", elevation=upper.elevation),
	"Counter-battens": house.storey("Roof - +3: Counter-battens", elevation=upper.elevation),
	"Tile battens": house.storey("Roof - +4: Tile battens", elevation=upper.elevation),
	"Roof tiles": house.storey("Roof - +5: Tiles", elevation=upper.elevation),
}
for layer_name, layer_storey in roof_layer_storeys.items():
	layer_storey.element.ObjectType = "ROOF_LAYER"
	layer_storey.element.Description = f"Visibility container for {layer_name}"

RAFTER_Z_OFFSET = -0.05
RAFTER_SIZE = (0.06, 0.20)
THERMAL_INSULATION_100_THICKNESS = 0.10
VAPOUR_BARRIER_THICKNESS = 0.001
THERMAL_INSULATION_50_THICKNESS = 0.05
GYPSUM_PLASTERBOARD_THICKNESS = 0.025
SHEATHING_THICKNESS = 0.025
UNDERLAY_THICKNESS = 0.005
COUNTER_BATTEN_SIZE = (0.04, 0.06)
TILE_BATTEN_SIZE = (0.05, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_THICKNESS = 0.03

THERMAL_INSULATION_100_BOTTOM = (
	RAFTER_Z_OFFSET - THERMAL_INSULATION_100_THICKNESS
)
VAPOUR_BARRIER_BOTTOM = (
	THERMAL_INSULATION_100_BOTTOM - VAPOUR_BARRIER_THICKNESS
)
THERMAL_INSULATION_50_BOTTOM = (
	VAPOUR_BARRIER_BOTTOM - THERMAL_INSULATION_50_THICKNESS
)
GYPSUM_PLASTERBOARD_BOTTOM = (
	THERMAL_INSULATION_50_BOTTOM - GYPSUM_PLASTERBOARD_THICKNESS
)
SHEATHING_BOTTOM = RAFTER_Z_OFFSET + RAFTER_SIZE[1]
UNDERLAY_BOTTOM = SHEATHING_BOTTOM + SHEATHING_THICKNESS
COUNTER_BATTEN_BOTTOM = UNDERLAY_BOTTOM + UNDERLAY_THICKNESS
TILE_BATTEN_BOTTOM = COUNTER_BATTEN_BOTTOM + COUNTER_BATTEN_SIZE[1]
ROOF_TILE_BOTTOM = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1]

rafters = [
	0.03, 0.65, 0.65, 0.65,
	0.89, ############################################

	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,
	0.06, 0.59,

	0.06, 0.9,
	0.65, 0.65, 0.65,
	0.49 #############################################
	]
skip_street = [5, 7, 9, 11, 12, 14, 16, 18, 20]
skip_garden = [6, 8, 10, 13, 15, 17, 19]
rafter_positions = []
rafter_x = 0.25
for distance in rafters:
	rafter_x += distance
	rafter_positions.append(rafter_x)

dormer_rafter_indices = [
	i for i in range(5, 21)
	if i not in skip_garden
]
dormer_x_min = min(rafter_positions[i] for i in dormer_rafter_indices) - RAFTER_SIZE[0] / 2
dormer_x_max = max(rafter_positions[i] for i in dormer_rafter_indices) + RAFTER_SIZE[0] / 2


def add_continuous_roof_layers(
	plane, name, x_min, x_max, y_min, y_max, *, inner_cuts=[],
):
	"""Add the roof build-up with optional global cuts keyed by layer name."""
	allowed_layers = {
		"thermal_insulation_100",
		"vapour_barrier",
		"thermal_insulation_50",
		"gypsum_plasterboard",
		"roof_sheathing",
		"roofing_underlay",
		"roof_tiles",
	}
	outline = (
		(x_min, y_min),
		(x_max, y_min),
		(x_max, y_max),
		(x_min, y_max),
	)
	insulation_100 = plane.layer(
		f"{name} 100 mm thermal insulation",
		outline=outline,
		z_offset=THERMAL_INSULATION_100_BOTTOM,
		thickness=THERMAL_INSULATION_100_THICKNESS,
		material="Thermal insulation",
		color="#E8D36D",
		extra_cuts=inner_cuts,
	)
	roof_layer_storeys["Thermal insulation 100 mm"].add(insulation_100)
	vapour_barrier = plane.layer(
		f"{name} vapour barrier",
		outline=outline,
		z_offset=VAPOUR_BARRIER_BOTTOM,
		thickness=VAPOUR_BARRIER_THICKNESS,
		material="Vapour barrier",
		color="#4A90E2",
		transparency=0.35,
		extra_cuts=inner_cuts,
	)
	roof_layer_storeys["Vapour barrier"].add(vapour_barrier)
	insulation_50 = plane.layer(
		f"{name} 50 mm thermal insulation",
		outline=outline,
		z_offset=THERMAL_INSULATION_50_BOTTOM,
		thickness=THERMAL_INSULATION_50_THICKNESS,
		material="Thermal insulation",
		color="#E8D36D",
		extra_cuts=inner_cuts,
	)
	roof_layer_storeys["Thermal insulation 50 mm"].add(insulation_50)
	gypsum_plasterboard = plane.layer(
		f"{name} gypsum plasterboard",
		outline=outline,
		z_offset=GYPSUM_PLASTERBOARD_BOTTOM,
		thickness=GYPSUM_PLASTERBOARD_THICKNESS,
		material="Gypsum plasterboard",
		color="#E8E5DE",
		extra_cuts=inner_cuts,
	)
	roof_layer_storeys["Gypsum plasterboard"].add(gypsum_plasterboard)
	sheathing = plane.layer(
		f"{name} roof sheathing",
		outline=outline,
		z_offset=SHEATHING_BOTTOM,
		thickness=SHEATHING_THICKNESS,
		material="Wood",
		color="#D1A46F",
	)
	roof_layer_storeys["Roof sheathing"].add(sheathing)
	underlay = plane.layer(
		f"{name} roofing underlay",
		outline=outline,
		z_offset=UNDERLAY_BOTTOM,
		thickness=UNDERLAY_THICKNESS,
		material="Roofing underlay",
		color="#3B4148",
	)
	roof_layer_storeys["Roofing underlay"].add(underlay)
	tiles = plane.layer(
		f"{name} roof tiles",
		outline=outline,
		z_offset=ROOF_TILE_BOTTOM,
		thickness=ROOF_TILE_THICKNESS,
		material="Roof tiles",
		color="#A64B35",
	)
	roof_layer_storeys["Roof tiles"].add(tiles)


def local_y_limits_from_cuts(plane, local_z=0):
	"""Return local Y limits for the two constant-global-Y roof cuts."""
	limits = []
	for cut in plane.cuts:
		global_y_values = [point[1] for point in cut]
		if max(global_y_values) - min(global_y_values) <= 1e-9:
			limits.append(
				(
					global_y_values[0]
					- plane.origin[1]
					- local_z * plane.z_axis[1]
				) / plane.y_axis[1]
			)
	if len(limits) != 2:
		raise ValueError(f"{plane.Name} must have two constant-global-Y cuts")
	return min(limits), max(limits)


def add_tile_battens(plane, name, x_ranges, y_min, y_max):
	row = 1
	y = y_min + TILE_BATTEN_SPACING / 2
	while y < y_max:
		for segment, (x_min, x_max) in enumerate(x_ranges, start=1):
			tile_batten = plane.beam(
				f"{name} tile batten {row}.{segment}",
				start=(x_min, y),
				end=(x_max, y),
				z_offset=TILE_BATTEN_BOTTOM,
				size=TILE_BATTEN_SIZE,
				material="Wood",
				kind="BEAM",
			)
			roof_layer_storeys["Tile battens"].add(tile_batten)
		row += 1
		y += TILE_BATTEN_SPACING


# The continuous layers deliberately overshoot in local Y.  The roof-plane
# cuts trim them at the ridge and eaves.  Around the dormer, the normal garden
# slope covers the ridge side and the dormer slope covers the eaves side.
roof_y_min = -1.5
roof_y_max = 7
add_continuous_roof_layers(
	street_roof, "Street", 0, 12, roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts
)
add_continuous_roof_layers(
	garden_roof, "Garden left", 0, dormer_x_min, roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts
)
add_continuous_roof_layers(
	garden_roof, "Garden right", dormer_x_max, 12, roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts
)
add_continuous_roof_layers(
	garden_roof, "Garden above dormer",
	dormer_x_min, dormer_x_max, roof_y_min, 0,
	inner_cuts=roof_inner_cuts
)
add_continuous_roof_layers(
	dormer_roof, "Dormer", dormer_x_min, dormer_x_max, 0,
	roof_y_max-1, # overshoot a little less for the dormer so our cuts work properly
	inner_cuts=roof_inner_cuts
)

# A batten whose centre lies completely beyond a cut would retain the wrong
# half-space, so derive the first and last tile-batten rows from the cuts.  The
# longer continuous layers and counter-battens can safely overshoot them.
tile_batten_centerline_z = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1] / 2
street_y_min, street_y_max = local_y_limits_from_cuts(
	street_roof, tile_batten_centerline_z
)
garden_y_min, garden_y_max = local_y_limits_from_cuts(
	garden_roof, tile_batten_centerline_z
)
dormer_y_min, dormer_y_max = local_y_limits_from_cuts(
	dormer_roof, tile_batten_centerline_z
)
add_tile_battens(
	street_roof, "Street", [(0, 12)], street_y_min, street_y_max
)
add_tile_battens(
	garden_roof,
	"Garden outer",
	[(0, dormer_x_min), (dormer_x_max, 12)],
	garden_y_min,
	garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden above dormer",
	[(dormer_x_min, dormer_x_max)],
	garden_y_min,
	0,
)
add_tile_battens(
	dormer_roof,
	"Dormer",
	[(dormer_x_min, dormer_x_max)],
	0,
	dormer_y_max,
)

for i, rafter_x in enumerate(rafter_positions):
	print("rafter_x = ", rafter_x)
	if i not in skip_street:
		rafter = street_roof.beam(
			"Rafter 1",
			start=(rafter_x, -2),
			end=(rafter_x, 5),
			z_offset=RAFTER_Z_OFFSET,
			size=RAFTER_SIZE,
			kind="RAFTER",
		)
		roof_layer_storeys["Rafters"].add(rafter)
		counter_batten = street_roof.beam(
			f"Street counter-batten {i + 1}",
			start=(rafter_x, -2),
			end=(rafter_x, 5),
			z_offset=COUNTER_BATTEN_BOTTOM,
			size=COUNTER_BATTEN_SIZE,
			material="Wood",
			kind="BEAM",
		)
		roof_layer_storeys["Counter-battens"].add(counter_batten)

	if i > 4 and i < 21:
		if i in skip_garden:
			rafter = garden_roof.beam(
				"Rafter 1",
				start=(rafter_x, -2),
				end=(rafter_x, 0.5),
				z_offset=RAFTER_Z_OFFSET,
				size=RAFTER_SIZE,
				kind="RAFTER",
			)
			roof_layer_storeys["Rafters"].add(rafter)
			counter_batten = garden_roof.beam(
				f"Garden counter-batten {i + 1}",
				start=(rafter_x, -2),
				end=(rafter_x, 0.5),
				z_offset=COUNTER_BATTEN_BOTTOM,
				size=COUNTER_BATTEN_SIZE,
				material="Wood",
				kind="BEAM",
			)
			roof_layer_storeys["Counter-battens"].add(counter_batten)
		else:
			rafter = dormer_roof.beam(
				"Rafter 1",
				start=(rafter_x, -0.5),
				end=(rafter_x, 5),
				z_offset=RAFTER_Z_OFFSET,
				size=RAFTER_SIZE,
				kind="RAFTER",
			)
			roof_layer_storeys["Rafters"].add(rafter)
			counter_batten = dormer_roof.beam(
				f"Dormer counter-batten {i + 1}",
				start=(rafter_x, -0.5),
				end=(rafter_x, 5),
				z_offset=COUNTER_BATTEN_BOTTOM,
				size=COUNTER_BATTEN_SIZE,
				material="Wood",
				kind="BEAM",
			)
			roof_layer_storeys["Counter-battens"].add(counter_batten)
	else:
		if i not in skip_garden:
			rafter = garden_roof.beam(
				"Rafter 1",
				start=(rafter_x, -2),
				end=(rafter_x, 5),
				z_offset=RAFTER_Z_OFFSET,
				size=RAFTER_SIZE,
				kind="RAFTER",
			)
			roof_layer_storeys["Rafters"].add(rafter)
			counter_batten = garden_roof.beam(
				f"Garden counter-batten {i + 1}",
				start=(rafter_x, -2),
				end=(rafter_x, 5),
				z_offset=COUNTER_BATTEN_BOTTOM,
				size=COUNTER_BATTEN_SIZE,
				material="Wood",
				kind="BEAM",
			)
			roof_layer_storeys["Counter-battens"].add(counter_batten)

# Drawing 1
drawing1 = house.add_drawing(
	"Drawing 1", x=6, y=4, z=0.25+2, radius=8, storeys=[ground]
)

drawing1.add_stair_annotation(stairs1)
drawing1.add_stair_annotation(stairs2)
drawing1.add_chimney_annotation(chimney)

drawing1.add_dimension(start=(0.5, 0.25), end=(0.5, 0.25+2.3), offset=1.5)
drawing1.add_dimension(start=(0.25, 7.5), end=(3.25, 7.5), offset=1.5)
drawing1.add_dimension(start=(3.5, 7.5), end=(8.0, 7.5), offset=1.5)
drawing1.add_dimension(start=(8.25, 7.5), end=(11.75, 7.5), offset=1.5)
drawing1.add_dimension(start=(0, 0.5), end=(12, 0.5), offset=-1.5)
drawing1.add_dimension(start=(11.5, 0), end=(11.5, 8), offset=-1.5)
drawing1.add_dimension(start=(11.5, 4.63), end=(11.5, 7.75), offset=-1)
drawing1.add_dimension(start=(5, 0.25), end=(5, 0.25+1.7), offset=0)

# The Rockwool occupies the right side of each wall axis.  These annotations
# belong only to Drawing 1 and follow the Rockwool centre lines.
#drawing1.add_batting((-0.10, -0.10), (12.10, -0.10), thickness=0.12)
#drawing1.add_batting((12.10, -0.10), (12.10, 8.10), thickness=0.12)
#drawing1.add_batting((12.10, 8.10), (-0.10, 8.10), thickness=0.12)
#drawing1.add_batting((-0.10, 8.10), (-0.10, -0.10), thickness=0.12)

house.write("house.ifc")
drawing1.render("house.svg", png=True, png_dpi=600)
