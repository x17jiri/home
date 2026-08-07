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
upper = house.storey("Ground floor", elevation=3.0 + 0.25)

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
	(0.25+3, 0.25+2.5), (0.25, 0.25+2.5),
	wall_type=partition_wall, height=ground_floor_height)
ground.furniture(
    "LG",
    kind="USERDEFINED",
    size=(0.80, 0.40, 1),
    color="#ffffff",
    center=(0.25+2.0, -0.2),
)

# Kitchen
wall_kitchen = ground.wall(
	(0.25+3+0.25+4.5, 0.25+1.75), (0.25+3+0.25, 0.25+1.75),
	wall_type=partition_wall, height=ground_floor_height)
kitchen_door = wall_kitchen.add_door(
	at=1.0,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=0.2,
	operation="SINGLE_SWING_LEFT",
#	reverse_swing=True,
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
    at=0.25+0.5,
    width=1.0,
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

# Chimney
chimney = ground.chimney(
    center=(0.25+3+0.25+4.5+0.25+0.6+0.2, 4.43),
    size=0.4,
    height=8.0,
    flue_diameter=0.18,
    start_height=0,
    name="Main chimney",
    color="#B8A99A",
)
# zed loznice
ground.wall(
	(0.25+3+0.25+4.5+0.25, 4.23), (0.25+3+0.25+4.5+0.25+0.55, 4.23),
	wall_type=partition_wall, height=ground_floor_height)
w1 = ground.wall(
	(0.25+3+0.25+4.5+0.25+1, 4.68),
	(0.25+3+0.25+4.5+0.25+3.5, 4.68),
	wall_type=partition_wall, height=ground_floor_height)
wall_3.add_door(
    at=8-0.25-1.5,
    width=1.0,
    height=2.125,
    sill_height=0.2,
    name="Bedroom door",
	operation="SINGLE_SWING_RIGHT"
)
# Vyklenek Krb
w2 = ground.wall(
	(0.25+3+0.25+4.5+0.25+1.0, 4.68),
	(0.25+3+0.25+4.5+0.25+1.0, 5.03),
	wall_type=partition_wall, height=ground_floor_height)
w3 = ground.wall(
	(0.25+3+0.25+4.5+0.25+1.0, 4.23+1.0),
	(0.25+3+0.25+4.5+0.25, 4.23+1.0),
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
    center=(0.25+3+0.25+4.5+0.25, 4.75),
	start_height=0.2,
#    rotation=90,
)

# Loznice
bed = ground.furniture(
    "Postel",
    kind="BED",
    size=(1.6, 2.0, 0.5),
    color="#8B5A2B",
    center=(0.25+3+0.25+4.5+0.25+3.5/2, 8-0.25-1),
#    rotation=90,
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

# upper floor
wall_cuts_1_4 = [
	(
		(0, 0.125-0.08, 3.25+1.25+0.12),
		(5, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25+0.24),
		(0, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25+0.24),
	),
	(
		(0, 8.0-0.125+0.08, 3.25+1.25+0.12),
		(0, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25+0.24),
		(5, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25+0.24),
	),
	(
		(0, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25),
		(0, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25),
		(5, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25),
	),
#	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
]
wall_cuts_2_3 = [
	(
		(0, 0.125-0.08, 3.25+1.25+0.12),
		(0, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25+0.24),
		(5, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25+0.24),
	),
	(
		(0, 8.0-0.125+0.08, 3.25+2.5+0.12),
		(0, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25+0.24),
		(5, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25+0.24),
	),
	(
		(0, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25),
		(0, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25),
		(5, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25),
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
wall_3 = upper.wall(
	(wall3_x, 0), (wall3_x, 8),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)

wall_4 = upper.wall(
	(12, 0), (12, 8),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_4.add_opening(at=0, width=0.25, height=0.25, sill_height=1.25)
wall_4.add_opening(at=7.75, width=0.25, height=0.25, sill_height=1.25)

wall_pracovna = upper.wall(
	start=(0.25+3+0.25+4.5, 2.75),
	end=(0.25+3+0.25, 2.75),
	wall_type=sdk_wall, height=4, cuts=wall_cuts_2_3)

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
    start=(0, 4.0-0.8, 3.25+2.875+0.5+0.12),
    end=(12, 4.0-0.8, 3.25+2.875+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam2 = upper.beam(
    "Beam",
    start=(0, 4.0+0.8, 3.25+2.875+0.5+0.12),
    end=(12, 4.0+0.8, 3.25+2.875+0.5+0.12),
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
    start=(0.25+3+0.25+4.5+0.25, 8-0.125, 3.25+2.5+0.06),
    end=(0.25+3, 8-0.125, 3.25+2.5+0.06),
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

street_roof = roof.plane(
    "Street slope",
    points=(
		(0, 0.125-0.08, 3.25+1.25+0.12), # origin
		(10, 0.125-0.08, 3.25+1.25+0.12), # +X direction
		(0, 4.0-0.8-0.07, 3.25+2.875+0.25+0.25+0.24), # +Y direction
	),
    cuts=[((0, 4, 0), (10, 4, 0), (0, 4, 10))],
)
garden_roof = roof.plane(
    "Garden slope",
    points=(
		(0, 8.0-0.125+0.08, 3.25+1.25+0.12), # origin
		(10, 8.0-0.125+0.08, 3.25+1.25+0.12), # +X direction
		(0, 4.0+0.8+0.07, 3.25+2.875+0.25+0.25+0.24), # +Y direction
	),
    cuts=[((0, 4, 0), (10, 4, 0), (0, 4, 10))],
)

for i in range(20):
	rafter = street_roof.beam(
		"Rafter 1",
		start=(0.25+0.65*i, -1),
		end=(0.25+0.65*i, 6),
		z_offset=-0.05,
		size=(0.06, 0.20),
		kind="RAFTER",
	)
	rafter = garden_roof.beam(
		"Rafter 1",
		start=(0.25+0.65*i, -1),
		end=(0.25+0.65*i, 6),
		z_offset=-0.05,
		size=(0.06, 0.20),
		kind="RAFTER",
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
