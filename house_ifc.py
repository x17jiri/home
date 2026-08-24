
# Strecha:
#    - taska:
#        - KMB BETA Briliant cihlová
#        - https://www.dek.cz/produkty/detail/1225121900-km-beta-briliant-t-zakladni-cc-252ks-pal
#        - sklon od 22 stupnu, od 12 stupnu s opatrenimi
#    - late 40x60 (40 na vysku)
#    - kontra late 60x40 (60 na vysku)
#    - pojistna hydroizolace
#        - Sunflex Contact Pro
#        - difuzne otevrena, reflexni
#        - https://www.nonstopstavebniny.cz/difuzni-folie-reflexni-membrana-sunflex-contact-pro-75m2/
#    - 80 mm drevovlakno
#        - Pavatex Isolair Eco
#        - https://www.ceskytesar.cz/variant/drevovlaknite-izolace/pavatex/isolair-eco/1051/25168
# 	 - mezi krokve:
#        - 20 cm vata
#        - Isover UNI: https://www.dek.cz/produkty/detail/1435541180-isover-uni-200mm-1-44m2-bal
#        - Rockton Super: https://www.dskstavebniny.cz/rockwool-rockton-super-tl-200-mm-bal-1-83-m2-0-035-p544923/
#    - 40 mm PIR
#        - TERMPIR AL
#        - https://www.nonstopstavebniny.cz/izolacni-pir-deska-termpir-al-40-mm-600-x-1200-mm/
#    - Parozabrana
#        - Neni potreba - je soucast PIR
#    - 50mm instalacni mezera s pruznymi zavesy
#    - akusticky SDK

# Fasada:
#    - Cementovlakno
#        - https://www.fasadnidesky.cz/produkty/cementovlaknita-deska-typ-20-250/

# Podlaha dole:
#    - 100 mm EPS 150
#        - https://www.dek.cz/produkty/detail/1460405120-eps-150-100mm-500x1000-isover-2-5m2-bal
#    - 50 mm PIR
#        - https://www.dek.cz/produkty/detail/1421010680-dekpir-floor-022-50mm-1200x600-7-2m2-bal
#    - 70 mm Cemflow + trubky topeni
#    - finalni krytina - dlazdice / zamkove PVC

# Podlaha dole chodba/posilovna:
#    - 150 mm XPS (3x50mm)
#        - https://www.dek.cz/produkty/detail/1420361060-fibran-xps-etics-gf-i-300kpa-50mm-dek-6m2-bal/28
#    - 2x25 mm OSB
#    - 30mm guma

# Podlaha nahore:
#    - krocejova izolace: ISOVER T-P 30 mm
#        - https://www.dek.cz/produkty/detail/1435401015-isover-t-p-30mm-1200x600-5-04m2-bal
#    - 70 mm Cemflow + trubky topeni
#    - finalni krytina - dlazdice / zamkove PVC

# Fasada:
#    - 200mm mineralni vata
#        - Rockwool Frontrock Plus 200 mm
#        - https://www.dek.cz/produkty/detail/1440402620-frontrock-plus-200mm-600x1000-1-2m2-bal/175

# Kamna:
#	ROMOTOP LUGO N04 AKUM krbová kamna 3-7,8kW, akumulační, pískovec
#	https://www.kotelrychle.cz/romotop-lugo-n04-akum-krbova-kamna-3-7-8kw--akumulacni--piskovec/

# Cerpadlo:
#	Tepelné čerpadlo LG Therma V Split 12kW HN1636M+HU123MA (model 2023)
#	https://www.vzduchotechnika1.cz/lg-therma-v-split-12kw-hn1636m-hu123ma

from math import acos, degrees, isclose, floor
import sys
from ifc_utils import *

RAFTER_Z_OFFSET = -0.05
RAFTER_SIZE = (0.06, 0.20)
VAPOUR_BARRIER_THICKNESS = 0.001
THERMAL_INSULATION_40_THICKNESS = 0.04
INSTALLATION_SPACE_THICKNESS = 0.05
GYPSUM_PLASTERBOARD_THICKNESS = 0.03
WOOD_FIBERBOARD_THICKNESS = 0.06
UNDERLAY_THICKNESS = 0.005
COUNTER_BATTEN_SIZE = (0.04, 0.06)
TILE_BATTEN_SIZE = (0.06, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_THICKNESS = 0.05
GROUND_FLOOR_THICKNESS = 0.20
UPPER_FLOOR_THICKNESS = 0.11

THERMAL_INSULATION_40_BOTTOM = (
	RAFTER_Z_OFFSET - THERMAL_INSULATION_40_THICKNESS
)
VAPOUR_BARRIER_BOTTOM = (
	THERMAL_INSULATION_40_BOTTOM - VAPOUR_BARRIER_THICKNESS
)
GYPSUM_PLASTERBOARD_BOTTOM = (
	VAPOUR_BARRIER_BOTTOM
	- INSTALLATION_SPACE_THICKNESS
	- GYPSUM_PLASTERBOARD_THICKNESS
)

ground_floor_height = 0.25+2.75
door_clear_height = 2.1
CEILING_THICKNESS = 0.21

UNDER_HOLE = 2.875
UPPER_FLOOR_START = ground_floor_height + CEILING_THICKNESS
COLLAR_TIE_SIZE = (0.06, 0.16)
COLLAR_TIE_EXTENSION = 1.5
COLLAR_TIE_X_OFFSET = (RAFTER_SIZE[0] + COLLAR_TIE_SIZE[0]) / 2
# The collar-tie tops meet the underside of the two central purlins and the
# wall below them.  The horizontal vapour barrier is derived from the tie
# underside so the two cannot drift apart when the framing changes.
COLLAR_TIE_TOP_HEIGHT = UNDER_HOLE + 0.5
COLLAR_TIE_BOTTOM_HEIGHT = COLLAR_TIE_TOP_HEIGHT - COLLAR_TIE_SIZE[1]
NADEZDIVKA = 1.25

house = House(
    "My house",
    colors={
        "wall": "#ffffff",
        "door": "#8B5A2B",
        "window": "#4A90E2",
    },
)

ground = house.storey("Ground floor", elevation=0)
upper = house.storey("Upper floor", elevation=3.0 + 0.21)

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
dry_wall = house.wall_type(
    "drywall - 100 mm",
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
stair_height = (
	ground_floor_height - GROUND_FLOOR_THICKNESS
	+ CEILING_THICKNESS + UPPER_FLOOR_THICKNESS)
step_count = 17

# For now each finished-floor build-up is one homogeneous interior slab.  It
# can later be replaced with insulation, heating, and screed components without
# changing the storey elevations or the existing sill-height coordinates.
FLOOR_OUTLINE = (
	(0.25, 0.25),
	(11.75, 0.25),
	(11.75, 7.75),
	(0.25, 7.75),
)
ground_floor_layer = ground.floor_layer(
	"Ground-floor build-up",
	outline=FLOOR_OUTLINE,
	thickness=GROUND_FLOOR_THICKNESS,
	color="#ffffff",
)

# Load-bearing walls

HOUSE_DEPTH = 8.0
HALF_DEPTH = HOUSE_DEPTH / 2.0

wall_front = ground.wall((0, 0), (12, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_4 = ground.wall((12, 0), (12, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_back = ground.wall((12, HOUSE_DEPTH), (0, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1 = ground.wall((0, HOUSE_DEPTH), (0, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_2 = ground.wall((wall2_x, 0), (wall2_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)

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
	clear_height=door_clear_height,
	sill_height=GROUND_FLOOR_THICKNESS,
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
	at=0.25+3.5+0.25+0.5+1+1,width=1.5, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_door(
	at=0.25+3.5+0.25+0.5,
	width=0.8, sill_height=0.25+0.1, height=0.25+2.25, opening_width=1, clear_height=2)
wall_back.add_window(
	at=0.25+3.5+0.25+4.5+0.25+0.75,
	width=1.5, sill_height=0.25+0.875, height=0.25+2.25)

# Bathroom, Koupelna
wall_bathroom = ground.wall(
	(0.25, 0.25+2.3), (0.25+3, 0.25+2.3),
	wall_type=partition_wall, height=ground_floor_height)
ground.furniture(
    "TČ",
    kind="USERDEFINED",
    size=(1.2, 0.5, 1.5),
    color="#ffffff",
    center=(0.25+2.5, 0-0.5),
)
ground.furniture(
    "TČ",
    kind="USERDEFINED",
    size=(0.5, 0.4, 0.9),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(0.25+2.7, 0.25+0.2),
)
ground.furniture(
    "Zásobník\nTUV",
    kind="USERDEFINED",
    size=(0.7, 0.7, 2.0),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(0.25+0.4, 0.25+0.35),
)
ground.furniture(
    "Pračka",
    kind="USERDEFINED",
	start_height=GROUND_FLOOR_THICKNESS,
    size=(0.7, 0.7, 2.0),
    color="#ffffff",
    center=(0.25+1.2, 0.25+0.35),
)
#ground.asset(
#    "Pracka",
#    asset="washing_machine",
#    center=(0.25+1.2, 0.25+0.35),
#	rotation=90,
#)
ground.asset(
	"Gauc", asset="3_seater_sofa",
	center=(0.25+3+0.25+1.1, 7.2),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.asset(
	"Gauc", asset="1_seater_sofa",
	center=(0.25+3+0.25+0.5, 6.2),
	start_height=GROUND_FLOOR_THICKNESS,
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
	start_height=GROUND_FLOOR_THICKNESS,
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
	start_height=GROUND_FLOOR_THICKNESS,
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
	start_height=GROUND_FLOOR_THICKNESS,
    center=(0.25+2.6, 0.25+1.8),
    rotation=-90,
)

# Kitchen, Kuchyn
wall_kitchen = ground.wall(
	(0.25+3+0.25, 0.25+1.7),
	(0.25+3+0.25+4.5, 0.25+1.7),
	wall_type=partition_wall, height=ground_floor_height)
kitchen_door = wall_3.add_door(
	at=0.25+0.625+1+1,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True,
)

# Pokoj Risanek
wall_2.add_door(
	at=HOUSE_DEPTH-0.25-3.0,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_LEFT",
#	reverse_swing=True,
)

# Bathroom
wall_2.add_door(
    at=0.25+0.625,
    opening_width=1.0, width=0.9,
    height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	reverse_swing=True,
)

# Main hallway
stairs1 = ground.stair(
    (12-0.25-0.5, 0.25+1+0.27*8),       # bottom centre
    (12-0.25-0.5, 0.25+1),       # upper landing edge centre
    width=1.0,
	start_height=GROUND_FLOOR_THICKNESS,
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
    "vestavěná skříň",
    kind="USERDEFINED",
    size=(4.4, 0.5, 1.5),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(0.25+3+0.25+4.5/2, 0.25+0.6/2),
)

# Chimney
CHIMNEY_DIST=0.47
CHIMNEY_Y_START = HALF_DEPTH + 0.8 - 0.07 - 0.05 - 0.4
CHIMNEY_Y_START = 0.125*floor((CHIMNEY_Y_START - 0.04 - 0.17) / 0.125) + 0.04 + 0.17
CHIMNEY_Y_START = CHIMNEY_Y_START + 0.025
CHIMNEY_Y_MID = CHIMNEY_Y_START + 0.2
CHIMNEY_Y_END = CHIMNEY_Y_START + 0.4

print("CHIMNEY_Y_START = ", CHIMNEY_Y_START)
print("CHIMNEY_Y_MID = ", CHIMNEY_Y_MID)
print("CHIMNEY_Y_END = ", CHIMNEY_Y_END)

chimney = ground.chimney(
    center=(0.25+3+0.25+4.5+0.25+CHIMNEY_DIST+0.2, CHIMNEY_Y_MID),
    size=0.4,
    height=8.8,
    flue_diameter=0.18,
    start_height=0,
    name="Main chimney",
    color="#B8A99A",
)
# zed loznice
w0 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.9, 4.21),
	(0.25+3+0.25+4.5+0.25, 4.21),
	wall_type=partition_wall, height=ground_floor_height)
w1 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.9, 4.65),
	(0.25+3+0.25+4.5+0.25+3.5, 4.65),
	wall_type=partition_wall, height=ground_floor_height)
wall_3.add_door(
    at=HOUSE_DEPTH-0.25-1.5,
    opening_width=1.0, width=0.9,
    height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
    clear_height=door_clear_height,
    name="Bedroom door",
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True,
)
# Vyklenek Krb
w2 = ground.wall(
	(0.25+3+0.25+4.5+0.25+0.5, 5.25),
	(0.25+3+0.25+4.5+0.25+0.5, 4.65),
	wall_type=partition_wall, height=ground_floor_height)
w3 = ground.wall(
	(0.25+3+0.25+4.5+0.25, 4.375+1.0),
	(0.25+3+0.25+4.5+0.25+0.4, 4.375+1.0),
	wall_type=partition_wall, height=ground_floor_height)
wall_3.add_opening(
    at=0.25+0.625+1+1+1.5,
    width=1.0,
    height=0.25+2.125,
    sill_height=GROUND_FLOOR_THICKNESS,
    name="Fireplace opening",
)
ground.connect_wall(w1, w2)
ground.connect_wall(w2, w3)

ground.furniture(
    "Kamna",
    kind="USERDEFINED",
    size=(0.5, 0.6, 1.5),
    color="#ffff2B",
    center=(0.25+3+0.25+4.5+0.2, 4.375+0.5),
	start_height=GROUND_FLOOR_THICKNESS,
#    rotation=90,
)

# Kuchyn
print("SEARCH: ", "\n".join(str(x) for x in house.assets.search("table")))
ground.furniture(
	"Dřez",
    kind="USERDEFINED",
    size=(0.7, 0.95, 0.8),
	start_height=GROUND_FLOOR_THICKNESS,
    center=(0.25+3+0.25+0.35, 0.25+1.7+0.15+(0.95/2)),
)
ground.furniture(
	"Myčka",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
	start_height=GROUND_FLOOR_THICKNESS,
    center=(0.25+3+0.25+0.35, 0.25+1.7+0.15+0.35+0.95),
)
ground.furniture(
	"Lednice",
    kind="USERDEFINED",
    size=(0.7, 1, 2),
    center=(0.25+3+0.25+0.35, 4.75-0.5),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.furniture(
	"Sporák",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
    center=(0.25+3+0.25+0.35+0.7, 0.25+1.7+0.15+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.furniture(
	"Kuchyňská Linka",
    kind="USERDEFINED",
    size=(3.1, 0.7, 0.8),
    center=(0.25+3+0.25+0.7+0.7+3.1/2, 0.25+1.7+0.15+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.asset(
    "Stul",
    asset="retail_4_seater_rectangular_table",
    center=(6, 4.5),
	start_height=GROUND_FLOOR_THICKNESS,
#	rotation=90,
)

# Loznice
bed = ground.furniture(
    "Postel",
    kind="BED",
    size=(1.6, 2.0, 0.5),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#8B5A2B",
    center=(11.75-1, 7.75-3.1/2),
	rotation=-90
)

# Opening from main to side hallway
opening = wall_3.add_opening(
    at=0.25+0.625,
    width=1.0,
    height=0.25+2.125,
    sill_height=GROUND_FLOOR_THICKNESS,
    name="Hallway passage",
    show_overhead=True,
)

# facade
if 0:
	frame1_v = house.add_vertical_frame(
	    wall_front,
	    offset=0,
	    width=0.05,
	    depth=0.08,
	    start_height=0.2,
	    height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
	    gap=0.60,
	    lath_offsets=[0, wall_front.length - 0.05],
	)
	lath_width=0.05
	window_space=0.03
	frame2_v = house.add_vertical_frame(
	    wall_back,
	    offset=0,
	    width=lath_width,
	    depth=0.1,
	    start_height=0.2,
	    height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
	    gap=0.60,
	    lath_offsets=[
			0,
			2.75 - lath_width-window_space, 2.75 + 0.5 + window_space,
			0.25+3.5+0.25+0.5 - lath_width-window_space, 0.25+3.5+0.25+0.5 + 1 + window_space,
			0.25+3.5+0.25+0.5 + 1.5 + window_space,
			0.25+3.5+0.25+0.5+1+1 - lath_width-window_space, 0.25+3.5+0.25+0.5+1+1 + 1.5 + window_space,
			0.25+3.5+0.25+4.5+0.25+0.75 - lath_width-window_space, 0.25+3.5+0.25+4.5+0.25+0.75 + 1.5 + window_space,
			wall_back.length - lath_width
		],
		space_before_openings=window_space,
		space_after_openings=window_space,
		space_above_openings=window_space,
		space_below_openings=window_space,
		insulation_material="Rockwool",
		insulation_color="#E8D36D",
	)
	lath_width=0.04
	frame2_h = house.add_horizontal_frame(
	    wall_back,
	    offset=0.1,
	    width=lath_width,
	    depth=0.06,
	    lath_offsets=[
			0.2,
			0.25+0.875-lath_width-window_space,
			UPPER_FLOOR_START+NADEZDIVKA-lath_width-0.1
		],
	    start_extension=0.1,
	    end_extension=0.1,
		gap=0.6,
		space_before_openings=window_space,
		space_after_openings=window_space,
		space_above_openings=window_space,
		space_below_openings=window_space,
		insulation_material="Rockwool",
		insulation_color="#E8D36D",
	)
	lath_width=0.03
	frame2_v2 = house.add_vertical_frame(
	    wall_back,
	    offset=0.16,
	    width=lath_width,
	    depth=0.05,
	    start_height=0.2,
	    height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
	    gap=0.40,
	    lath_offsets=[
			0,
			2.75 - lath_width-window_space, 2.75 + 0.5 + window_space,
			0.25+3.5+0.25+0.5 - lath_width-window_space, 0.25+3.5+0.25+0.5 + 1 + window_space,
			0.25+3.5+0.25+0.5 + 1.5 + window_space,
			0.25+3.5+0.25+0.5+1+1 - lath_width-window_space, 0.25+3.5+0.25+0.5+1+1 + 1.5 + window_space,
			0.25+3.5+0.25+4.5+0.25+0.75 - lath_width-window_space, 0.25+3.5+0.25+4.5+0.25+0.75 + 1.5 + window_space,
			wall_back.length - lath_width
		],
		space_before_openings=window_space,
		space_after_openings=window_space,
		space_above_openings=window_space,
		space_below_openings=window_space,
	)
	frame2_finish = house.add_facade_layer(
		wall_back,
		name="Cementovlaknita deska - garden facade",
		offset=0.21,
		thickness=0.01,
		start_height=0.2,
		height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
		color="#ffffff",
	)
	frame3_v = house.add_vertical_frame(
	    wall_4,
	    offset=0,
	    width=0.05,
	    depth=0.08,
	    start_height=0.2,
	    height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
	    gap=0.60,
	    lath_offsets=[0, wall_4.length - 0.05],
	)
	frame4_v = house.add_vertical_frame(
	    wall_1,
	    offset=0,
	    width=0.05,
	    depth=0.08,
	    start_height=0.2,
	    height=UPPER_FLOOR_START+NADEZDIVKA-0.2-0.1,
	    gap=0.60,
	    lath_offsets=[0, wall_1.length - 0.05],
	)


	facade_1 = house.storey("Facade Layer 1", elevation=ground.elevation)
	facade_1.add(frame1_v)
	facade_1.add(frame2_v)
	facade_1.add(frame3_v)
	facade_1.add(frame4_v)

	facade_2 = house.storey("Facade Layer 2", elevation=ground.elevation)
	#facade_2.add(frame1_h)
	facade_2.add(frame2_h)
	#facade_2.add(frame3_h)
	#facade_2.add(frame4_h)

	facade_3 = house.storey("Facade Layer 3", elevation=ground.elevation)
	#facade_3.add(frame1_v)
	facade_3.add(frame2_v2)
	#facade_3.add(frame3_v)
	#facade_3.add(frame4_v)

	facade_4 = house.storey(
		"Facade Layer 4 - Cementovlaknita deska",
		elevation=ground.elevation,
	)
	facade_4.add(frame2_finish)

# MIAKO
ceiling1 = upper.miako_slab(
    "Ceiling 1",
    start=(0.1, HOUSE_DEPTH-0.25+0.04),
    end=(0.25+3.0+0.25-0.15, HOUSE_DEPTH-0.25+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, -1),
    structure=[
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide",
		],
)
ceiling2 = upper.miako_slab(
    "Ceiling 2",
    start=(0.25+3.0+0.125, HOUSE_DEPTH-0.25+0.04),
    end=(0.25+3.0+0.25+4.5+0.125, HOUSE_DEPTH-0.25+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, -1),
    structure=[
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide",
		],
)
ceiling3 = upper.miako_slab(
    "Ceiling 3",
    start=(0.25+3.0+0.25+4.5+0.15, HOUSE_DEPTH-0.25+0.04),
    end=(0.25+3.0+0.25+4.5+0.15+3.75, HOUSE_DEPTH-0.25+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
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


def floor_bounds_over_miako(*ceilings):
	"""Return an interior, axis-aligned floor rectangle over MIAKO slabs."""
	points = [point for ceiling in ceilings for point in ceiling.footprint]
	floor_x = [point[0] for point in FLOOR_OUTLINE]
	floor_y = [point[1] for point in FLOOR_OUTLINE]
	return [
		max(min(floor_x), min(point[0] for point in points)),
		max(min(floor_y), min(point[1] for point in points)),
		min(max(floor_x), max(point[0] for point in points)),
		min(max(floor_y), max(point[1] for point in points)),
	]


main_floor_bounds = floor_bounds_over_miako(ceiling1, ceiling2)
stair_hall_floor_bounds = floor_bounds_over_miako(ceiling3)
# The structural slabs stop on opposite sides of their bearing transition.
# Split the narrow interval at its midpoint so the two simplified floor
# layers meet without duplicating volume or leaving a crack.
floor_split_x = (
	main_floor_bounds[2] + stair_hall_floor_bounds[0]
) / 2
main_floor_bounds[2] = floor_split_x
stair_hall_floor_bounds[0] = floor_split_x


def rectangle_outline(bounds):
	min_x, min_y, max_x, max_y = bounds
	return (
		(min_x, min_y),
		(max_x, min_y),
		(max_x, max_y),
		(min_x, max_y),
	)


upper_floor_layers = (
	upper.floor_layer(
		"Upper-floor build-up - main",
		outline=rectangle_outline(main_floor_bounds),
		thickness=UPPER_FLOOR_THICKNESS,
		color="#ffffff",
	),
	upper.floor_layer(
		"Upper-floor build-up - stair hall",
		outline=rectangle_outline(stair_hall_floor_bounds),
		thickness=UPPER_FLOOR_THICKNESS,
		color="#ffffff",
	),
)

STREET_ROOF_JOINT_Y = HALF_DEPTH-0.8-0.07
GARDEN_ROOF_JOINT_Y = HALF_DEPTH+0.8+0.07
ROOF_JOINT_Z = UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25+0.24
STREET_ROOF_PLANE_POINTS = (
	(0, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, 0.125-0.08, UPPER_FLOOR_START+NADEZDIVKA+0.12),
)
GARDEN_ROOF_PLANE_POINTS = (
	(0, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, HOUSE_DEPTH-0.125+0.08, UPPER_FLOOR_START+NADEZDIVKA+0.12),
)
COLLAR_TIE_CUTS = (
	offset_plane(
		*STREET_ROOF_PLANE_POINTS,
		offset=RAFTER_Z_OFFSET + RAFTER_SIZE[1],
	),
	offset_plane(
		*GARDEN_ROOF_PLANE_POINTS,
		offset=RAFTER_Z_OFFSET + RAFTER_SIZE[1],
	),
)
DORMER_ROOF_PLANE_POINTS = (
	(0, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, HOUSE_DEPTH-0.125+0.08, UPPER_FLOOR_START+2.5+0.12),
)
FLAT_CEILING_ROOF_PLANE_POINTS = (
	(0, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
)

# upper floor
wall_cuts_1_4 = [
	offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	offset_plane(*GARDEN_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	(
		(0, HALF_DEPTH-0.8-0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
		(0, HALF_DEPTH+0.8+0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
		(5, HALF_DEPTH+0.8+0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
	),
#	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
]
wall_cuts_2_3 = [
	offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	offset_plane(*DORMER_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	(
		(0, HALF_DEPTH-0.8-0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
		(0, HALF_DEPTH+0.8+0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
		(5, HALF_DEPTH+0.8+0.07, UPPER_FLOOR_START+UNDER_HOLE+0.25+0.25),
	),
]

wall_dormer = upper.wall(
	(0.25+3+0.25+4.5+0.25, HOUSE_DEPTH), (0.25+3, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=1.25, start_height=NADEZDIVKA)
wall_front = upper.wall((0, 0), (12, 0), wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_back = upper.wall(
	(12, HOUSE_DEPTH), (0, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_1 = upper.wall(
	(0, HOUSE_DEPTH), (0, 0),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_1.add_opening(at=0, width=0.25, height=1.5, sill_height=NADEZDIVKA)
wall_1.add_opening(at=7.75, width=0.25, height=1.5, sill_height=NADEZDIVKA)

wall_2 = upper.wall(
	(wall2_x, 0), (wall2_x, HOUSE_DEPTH),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_2.add_opening(
	at=3.5, width=1, height=UNDER_HOLE+0.25, sill_height=UNDER_HOLE)
wall_3 = upper.wall(
	(wall3_x, 0), (wall3_x, HOUSE_DEPTH),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_3.add_opening(
	at=3.5, width=1, height=UNDER_HOLE+0.25, sill_height=UNDER_HOLE)

wall_4 = upper.wall(
	(12, 0), (12, HOUSE_DEPTH),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_4.add_opening(at=0, width=0.25, height=1.5, sill_height=NADEZDIVKA)
wall_4.add_opening(at=7.75, width=0.25, height=1.5, sill_height=NADEZDIVKA)

wall_2.add_opening(at=1.55, width=1, height=2.25)
wall_zachod_nahore = upper.wall(
	start=(0.25+3+0.25, 2.55),
	end=(0.25+3+0.25+4.5, 2.55),
	wall_type=dry_wall, height=UNDER_HOLE + 0.15)
wall_zachod_nahore.add_door(
	at=3.5,
	opening_width=0.8, width=0.7,
	height=2.25,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True)
upper.wall(
	start=(3.5+1.2, 2.55),
	end=(3.5+1.2, 0.25),
	wall_type=dry_wall, height=UNDER_HOLE - 0.05 - GYPSUM_PLASTERBOARD_THICKNESS
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
    start=(0, HALF_DEPTH-0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    end=(12, HALF_DEPTH-0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam2 = upper.beam(
    "Beam",
    start=(0, HALF_DEPTH+0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    end=(12, HALF_DEPTH+0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam3 = upper.beam(
    "Beam",
    start=(0, 0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    end=(12, 0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam4 = upper.beam(
    "Beam",
    start=(0, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    end=(12, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam_dormer = upper.beam(
    "Beam",
    start=(0.25+3+0.25+4.5+0.25+0.3, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+2.5+0.06),
    end=(0.25+3-0.3, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+2.5+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)

# Chodba nahore
upper.furniture(
    "Rekuperace",
    kind="USERDEFINED",
    size=(1, 0.5, 2.5),
    color="#ffff00",
    center=(11.75-0.3, 7.75-2),
	rotation=90,
	start_height=UPPER_FLOOR_THICKNESS,
)

# Okna obyvak
wall_dormer.add_window(
	at=0.25+0.5,width=1.5, sill_height=NADEZDIVKA, height=2.25)
wall_dormer.add_window(
	at=0.25+2.5,
	width=1.5, sill_height=NADEZDIVKA, height=2.25)
# Dvere obyvak
wall_3.add_door(
	#at=CHIMNEY_Y_MID+0.07+0.25,
	at=3.25,
	opening_width=1, width=0.9,
	height=2.25,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
# Dvere pokojik nahore
wall_2.add_door(
	at=3,
	opening_width=1, width=0.9,
	height=2.25,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
# Okna pokojik nahore
wall_1.add_window(
	at=3.25,
	width=1.5,
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
	points=STREET_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		((0, -0.5, 0), (10, -0.5, 0), (0, -0.5, 10)),
	],
)
garden_roof = roof.plane(
    "Garden slope",
	points=GARDEN_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		((0, HOUSE_DEPTH+0.5, 0), (10, HOUSE_DEPTH+0.5, 0), (0, HOUSE_DEPTH+0.5, 10)),
	],
)
dormer_roof = roof.plane(
    "Dormer slope",
	points=DORMER_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		((0, HOUSE_DEPTH+0.5, 0), (10, HOUSE_DEPTH+0.5, 0), (0, HOUSE_DEPTH+0.5, 10)),
	],
)
flat_ceiling_roof = roof.plane(
	"Flat ceiling",
	points=FLAT_CEILING_ROOF_PLANE_POINTS,
)


def roof_angle_degrees(plane):
	"""Return a roof plane's acute pitch angle above horizontal."""
	normal_z = min(1.0, max(-1.0, abs(plane.z_axis[2])))
	return degrees(acos(normal_z))


street_roof_angle = roof_angle_degrees(street_roof)
garden_roof_angle = roof_angle_degrees(garden_roof)
if not isclose(street_roof_angle, garden_roof_angle, abs_tol=1e-9):
	raise ValueError("street and garden roof angles must match")
print(f"Main roof angle: {street_roof_angle:.2f}°")
print(f"Dormer roof angle: {roof_angle_degrees(dormer_roof):.2f}°")

# Bonsai creates Outliner collections from spatial containers, but flattens
# ordinary IFC aggregation.  These intentionally artificial storeys provide
# one portable visibility collection for each roof layer in shared IFC files.
roof_layer_storeys = {
	"Thermal insulation 40 mm": house.storey(
		"Roof - -1: 40 mm thermal insulation", elevation=upper.elevation),
	"Vapour barrier": house.storey(
		"Roof - -2: Vapour barrier", elevation=upper.elevation),
	"Gypsum plasterboard": house.storey(
		"Roof - -3: Gypsum plasterboard", elevation=upper.elevation),
	"Rafters": house.storey("Roof - 0: Rafters", elevation=upper.elevation),
	"Collar ties": house.storey(
		"Roof - 0a: Collar ties", elevation=upper.elevation),
	"Wood fiberboard": house.storey(
		"Roof - +1: Wood fiberboard", elevation=upper.elevation),
	"Roofing underlay": house.storey("Roof - +2: Underlay", elevation=upper.elevation),
	"Counter-battens": house.storey("Roof - +3: Counter-battens", elevation=upper.elevation),
	"Tile battens": house.storey("Roof - +4: Tile battens", elevation=upper.elevation),
	"Roof tiles": house.storey("Roof - +5: Tiles", elevation=upper.elevation),
}
for layer_name, layer_storey in roof_layer_storeys.items():
	layer_storey.element.ObjectType = "ROOF_LAYER"
	layer_storey.element.Description = f"Visibility container for {layer_name}"

# Sloping layers remain a conventional contiguous build-up.  The horizontal
# ceiling has an installation void, so describe that exceptional part with
# readable storey-relative bottom/top heights instead of adding more roof
# planes or special geometry types.
SLOPED_INNER_LAYER_LAYOUT = {
	"Thermal insulation 40 mm": (
		THERMAL_INSULATION_40_BOTTOM,
		THERMAL_INSULATION_40_THICKNESS,
	),
	"Vapour barrier": (VAPOUR_BARRIER_BOTTOM, VAPOUR_BARRIER_THICKNESS),
	"Gypsum plasterboard": (
		GYPSUM_PLASTERBOARD_BOTTOM,
		GYPSUM_PLASTERBOARD_THICKNESS,
	),
}
FLAT_CEILING_LAYER_HEIGHTS = {
	# Values are (bottom, top), measured from the upper-storey floor.
	"Thermal insulation 40 mm": (
		COLLAR_TIE_BOTTOM_HEIGHT - THERMAL_INSULATION_40_THICKNESS,
		COLLAR_TIE_BOTTOM_HEIGHT,
	),
	"Vapour barrier": (
		COLLAR_TIE_BOTTOM_HEIGHT
		- THERMAL_INSULATION_40_THICKNESS
		- VAPOUR_BARRIER_THICKNESS,
		COLLAR_TIE_BOTTOM_HEIGHT - THERMAL_INSULATION_40_THICKNESS,
	),
	# The first 50 mm below the vapour barrier is an empty installation
	# space.  The horizontal plasterboard retains its lower ceiling height.
	"Gypsum plasterboard": (
		UNDER_HOLE - 0.05 - GYPSUM_PLASTERBOARD_THICKNESS,
		UNDER_HOLE - 0.05,
	),
}
FLAT_CEILING_INNER_LAYER_LAYOUT = {
	layer_name: (
		UPPER_FLOOR_START + bottom - ROOF_JOINT_Z,
		top - bottom,
	)
	for layer_name, (bottom, top) in FLAT_CEILING_LAYER_HEIGHTS.items()
}
WOOD_FIBERBOARD_BOTTOM = RAFTER_Z_OFFSET + RAFTER_SIZE[1]
UNDERLAY_BOTTOM = WOOD_FIBERBOARD_BOTTOM + WOOD_FIBERBOARD_THICKNESS
COUNTER_BATTEN_BOTTOM = UNDERLAY_BOTTOM + UNDERLAY_THICKNESS
TILE_BATTEN_BOTTOM = COUNTER_BATTEN_BOTTOM + COUNTER_BATTEN_SIZE[1]
ROOF_TILE_BOTTOM = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1]

rafters = [
	0.09, 0.66, 0.66, 0.66, 0.66,

	0.06, 0.70, ###################################
	0.06, 0.60,
	0.06, 0.60,
	0.06, 0.60,
	0.06, 0.60,
	0.06, 0.60,
	0.06, 0.60,
	0.06, 0.70, ###################################

	0.06, 0.80, ################################### komin
	0.78, 0.78, 0.78
	]
skip_street = [5, 7, 9, 11, 13, 14, 16, 18, 20]
skip_garden = [6, 8, 10, 12, 15, 17, 19]
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
roof_x_ranges = (
	(0, dormer_x_min),
	(dormer_x_min, dormer_x_max),
	(dormer_x_max, 12),
)


def add_continuous_roof_layers(
	plane,
	name,
	x_min,
	x_max,
	y_min,
	y_max,
	*,
	inner_cuts=(),
	inner_y_limits=None,
	inner_layout=SLOPED_INNER_LAYER_LAYOUT,
	include_inner=True,
	include_outer=True,
):
	"""Add selected inner and outer parts of the roof build-up."""
	outer_outline = (
		(x_min, y_min),
		(x_max, y_min),
		(x_max, y_max),
		(x_min, y_max),
	)

	def inner_outline(layer_name):
		if inner_y_limits is None:
			layer_y_min, layer_y_max = y_min, y_max
		else:
			layer_y_min, layer_y_max = inner_y_limits[layer_name]
		return (
			(x_min, layer_y_min),
			(x_max, layer_y_min),
			(x_max, layer_y_max),
			(x_min, layer_y_max),
		)

	if include_inner:
		insulation_40_bottom, insulation_40_thickness = inner_layout[
			"Thermal insulation 40 mm"
		]
		insulation_40 = plane.layer(
			f"{name} 40 mm thermal insulation",
			outline=inner_outline("Thermal insulation 40 mm"),
			z_offset=insulation_40_bottom,
			thickness=insulation_40_thickness,
			material="Thermal insulation",
			color="#E8D36D",
			extra_cuts=inner_cuts,
		)
		roof_layer_storeys["Thermal insulation 40 mm"].add(insulation_40)
		vapour_barrier_bottom, vapour_barrier_thickness = inner_layout[
			"Vapour barrier"
		]
		vapour_barrier = plane.layer(
			f"{name} vapour barrier",
			outline=inner_outline("Vapour barrier"),
			z_offset=vapour_barrier_bottom,
			thickness=vapour_barrier_thickness,
			material="Vapour barrier",
			color="#4A90E2",
			transparency=0.35,
			extra_cuts=inner_cuts,
		)
		roof_layer_storeys["Vapour barrier"].add(vapour_barrier)
		gypsum_bottom, gypsum_thickness = inner_layout["Gypsum plasterboard"]
		gypsum_plasterboard = plane.layer(
			f"{name} gypsum plasterboard",
			outline=inner_outline("Gypsum plasterboard"),
			z_offset=gypsum_bottom,
			thickness=gypsum_thickness,
			material="Gypsum plasterboard",
			color="#E8E5DE",
			extra_cuts=inner_cuts,
		)
		roof_layer_storeys["Gypsum plasterboard"].add(gypsum_plasterboard)
	if include_outer:
		fiberboard = plane.layer(
			f"{name} wood fiberboard",
			outline=outer_outline,
			z_offset=WOOD_FIBERBOARD_BOTTOM,
			thickness=WOOD_FIBERBOARD_THICKNESS,
			material="Wood fiberboard",
			color="#C9B56D",
		)
		roof_layer_storeys["Wood fiberboard"].add(fiberboard)
		underlay = plane.layer(
			f"{name} roofing underlay",
			outline=outer_outline,
			z_offset=UNDERLAY_BOTTOM,
			thickness=UNDERLAY_THICKNESS,
			material="Roofing underlay",
			color="#3B4148",
		)
		roof_layer_storeys["Roofing underlay"].add(underlay)
		tiles = plane.layer(
			f"{name} roof tiles",
			outline=outer_outline,
			z_offset=ROOF_TILE_BOTTOM,
			thickness=ROOF_TILE_THICKNESS,
			material="Roof tiles",
			color="#A64B35",
		)
		roof_layer_storeys["Roof tiles"].add(tiles)


def independent_inner_layer_boundaries(slope_plane):
	"""Return matching, unconnected slope/ceiling endpoints for each layer."""
	boundaries = {}
	for layer_name, (slope_bottom, _) in SLOPED_INNER_LAYER_LAYOUT.items():
		flat_bottom = FLAT_CEILING_INNER_LAYER_LAYOUT[layer_name][0]
		flat_z = flat_ceiling_roof.to_world((0, 0, flat_bottom))[2]
		slope_origin_z = slope_plane.to_world((0, 0, slope_bottom))[2]
		slope_y = (flat_z - slope_origin_z) / slope_plane.y_axis[2]
		world_boundary = slope_plane.to_world((0, slope_y, slope_bottom))
		flat_y = flat_ceiling_roof.to_local(world_boundary)[1]
		boundaries[layer_name] = (slope_y, flat_y)
	return boundaries


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


# The outer layers deliberately overshoot in local Y so the roof-plane cuts
# trim them at the ridge and eaves.  Inner sloped and horizontal layers are
# separate solids whose outlines end where their bottom faces cross.  This is
# symmetric and avoids cross-plane Boolean mitres in the IFC model.
roof_y_min = -1.5
roof_y_max = 7
street_inner_boundaries = independent_inner_layer_boundaries(street_roof)
garden_inner_boundaries = independent_inner_layer_boundaries(garden_roof)
dormer_inner_boundaries = independent_inner_layer_boundaries(dormer_roof)


def sloped_inner_y_limits(plane, boundaries, eave_y):
	return {
		layer_name: (
			slope_y,
			(
				eave_y
				- plane.origin[1]
				- SLOPED_INNER_LAYER_LAYOUT[layer_name][0] * plane.z_axis[1]
			) / plane.y_axis[1],
		)
		for layer_name, (slope_y, _) in boundaries.items()
	}


def flat_inner_y_limits(left_boundaries, right_boundaries):
	return {
		layer_name: (
			left_boundaries[layer_name][1],
			right_boundaries[layer_name][1],
		)
		for layer_name in SLOPED_INNER_LAYER_LAYOUT
	}


for part_name, (x_min, x_max) in zip(
	("Street left", "Street middle", "Street right"),
	roof_x_ranges,
):
	add_continuous_roof_layers(
		street_roof, part_name, x_min, x_max, roof_y_min, roof_y_max,
		inner_cuts=roof_inner_cuts,
		inner_y_limits=sloped_inner_y_limits(
			street_roof, street_inner_boundaries, 0.25
		),
	)
add_continuous_roof_layers(
	garden_roof, "Garden left", *roof_x_ranges[0], roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden right", *roof_x_ranges[2], roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden above dormer",
	*roof_x_ranges[1], roof_y_min, 0,
	include_inner=False,
)
add_continuous_roof_layers(
	dormer_roof, "Dormer", *roof_x_ranges[1], 0,
	roof_y_max-1, # overshoot a little less for the dormer so our cuts work properly
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		dormer_roof, dormer_inner_boundaries, 7.75
	),
)
for part_name, (x_min, x_max), garden_side_plane in zip(
	("Flat ceiling left", "Flat ceiling middle", "Flat ceiling right"),
	roof_x_ranges,
	(garden_roof, dormer_roof, garden_roof),
):
	add_continuous_roof_layers(
		flat_ceiling_roof,
		part_name,
		x_min,
		x_max,
		0.25 - STREET_ROOF_JOINT_Y,
		7.75 - STREET_ROOF_JOINT_Y,
		inner_cuts=roof_inner_cuts,
		inner_y_limits=flat_inner_y_limits(
			street_inner_boundaries,
			(
				dormer_inner_boundaries
				if garden_side_plane is dormer_roof
				else garden_inner_boundaries
			),
		),
		inner_layout=FLAT_CEILING_INNER_LAYER_LAYOUT,
		include_outer=False,
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
	street_roof, "Street", roof_x_ranges, street_y_min, street_y_max
)
add_tile_battens(
	garden_roof,
	"Garden outer",
	[roof_x_ranges[0], roof_x_ranges[2]],
	garden_y_min,
	garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden above dormer",
	[roof_x_ranges[1]],
	garden_y_min,
	0,
)
add_tile_battens(
	dormer_roof,
	"Dormer",
	[roof_x_ranges[1]],
	0,
	dormer_y_max,
)

for i, rafter_x in enumerate(rafter_positions):
	print("rafter_x = ", rafter_x)
	if i not in skip_street:
		for side, x_offset in (
			("left", -COLLAR_TIE_X_OFFSET),
			("right", COLLAR_TIE_X_OFFSET),
		):
			collar_tie = upper.beam(
				f"Collar tie {i + 1} {side}",
				start=(
					rafter_x + x_offset,
					STREET_ROOF_JOINT_Y - COLLAR_TIE_EXTENSION,
					UPPER_FLOOR_START
					+ COLLAR_TIE_BOTTOM_HEIGHT
					+ COLLAR_TIE_SIZE[1] / 2,
				),
				end=(
					rafter_x + x_offset,
					GARDEN_ROOF_JOINT_Y + COLLAR_TIE_EXTENSION,
					UPPER_FLOOR_START
					+ COLLAR_TIE_BOTTOM_HEIGHT
					+ COLLAR_TIE_SIZE[1] / 2,
				),
				size=COLLAR_TIE_SIZE,
				material="Wood",
				kind="BEAM",
				cuts=COLLAR_TIE_CUTS,
			)
			roof_layer_storeys["Collar ties"].add(collar_tie)
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
				end=(rafter_x, 0.9),
				z_offset=RAFTER_Z_OFFSET,
				size=RAFTER_SIZE,
				kind="RAFTER",
			)
			roof_layer_storeys["Rafters"].add(rafter)
			counter_batten = garden_roof.beam(
				f"Garden counter-batten {i + 1}",
				start=(rafter_x, -2),
				end=(rafter_x, 0),
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

house.write("house.ifc")

# Drawing 1 - ground floor
if "ground" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 1",
		x=6,
		y=4,
		z=0.25+2,
		radius=8,
		storeys=[ground],
		right_panel_width=40,
	)
	drawing1.add_material_legend([
		("brick", "Nosná zeď - VPC Cihla 240 mm"),
		("diagonal1", "Příčka - VPC Cihla 115 mm"),
	])

	drawing1.add_stair_annotation(stairs1)
	drawing1.add_stair_annotation(stairs2)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_dimension(start=(0.5, 0.25), end=(0.5, 0.25+2.3), offset=1.5)
	drawing1.add_dimension(start=(0.25, 7.5), end=(3.25, 7.5), offset=1.5)
	drawing1.add_dimension(start=(3.5, 7.5), end=(8.0, 7.5), offset=1.5)
	drawing1.add_dimension(start=(8.25, 7.5), end=(11.75, 7.5), offset=1.5)
	drawing1.add_dimension(start=(0, 0.5), end=(12, 0.5), offset=-1.5)
	drawing1.add_dimension(start=(11.5, 0), end=(11.5, 8), offset=-1.5)
	drawing1.add_dimension(start=(11.5, 4.65), end=(11.5, 7.75), offset=-1)
	drawing1.add_dimension(start=(5, 0.25), end=(5, 0.25+1.7), offset=0)

	drawing1.add_dimension(start=(3.5+4.75, 0.25), end=(3.5+4.75, 0.25+0.625), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625), end=(3.5+4.75, 0.25+0.625+1), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1), end=(3.5+4.75, 0.25+0.625+1+1), offset=-0.5)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1), end=(3.5+4.75, 0.25+0.625+1+1+1), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1+1), end=(3.5+4.75, 0.25+0.625+1+1+1+0.5), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1+1+0.5), end=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1), end=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1+0.875), offset=1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1+0.875), end=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1+0.875+1), offset=-1.3)
	drawing1.add_dimension(start=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1+0.875+1), end=(3.5+4.75, 0.25+0.625+1+1+1+0.5+1+0.875+1+0.5), offset=-1.3)

	drawing1.add_dimension(start=(3.5, 7.75-2), end=(3.5, 7.75), offset=1.3)
	drawing1.add_dimension(start=(3.5, 7.75-2-1), end=(3.5, 7.75-2), offset=1.3)
	drawing1.add_dimension(start=(3.5, 0.25+2.3+0.15), end=(3.5, 7.75-2-1), offset=1.3)

	drawing1.add_entrance_arrow(
		(3.5+4.5+1.1, -0.5),
		rotation=90,  # points left
		size=0.6,      # metres
	)

	drawing1.add_room_annotation(
		(1.1, 0.25+2.3+0.25+2.5),
		identifier="0.01",
		area=5.05*3,   # m²
	)
	drawing1.add_room_annotation(
		(1.6, 0.25+1.15),
		identifier="0.02",
		area=2.3*3,   # m²
	)
	drawing1.add_room_annotation(
		(3.5+1.4, 0.5+1.7+2.3),
		identifier="0.03",
		area=5.65*4.5,   # m²
	)
	drawing1.add_room_annotation(
		(3.5+2.3, 0.5+0.8),
		identifier="0.04",
		area=1.7*4.5,   # m²
	)
	drawing1.add_room_annotation(
		(3.5+4.25+2.1, 5+0.5),
		identifier="0.05",
		area=3*3.5-0.65*0.75,   # m²
	)
	drawing1.add_room_annotation(
		(3.5+4.25+2.1, 5-1.3),
		identifier="0.06",
		area=4.4*3.5-0.9*0.55,   # m²
	)

	# The Rockwool occupies the right side of each wall axis.  These annotations
	# belong only to Drawing 1 and follow the Rockwool centre lines.
	#drawing1.add_batting((-0.10, -0.10), (12.10, -0.10), thickness=0.12)
	#drawing1.add_batting((12.10, -0.10), (12.10, 8.10), thickness=0.12)
	#drawing1.add_batting((12.10, 8.10), (-0.10, 8.10), thickness=0.12)
	#drawing1.add_batting((-0.10, 8.10), (-0.10, -0.10), thickness=0.12)

	drawing1.render("ground.svg", png=True, png_dpi=600)

# Drawing 2 - upper floor
if "upper" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2", x=6, y=4, z=0.25+2.75+2, radius=8, storeys=[upper]
	)

	drawing1.add_stair_annotation(stairs1)
	drawing1.add_stair_annotation(stairs2)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_dimension(start=(0.25, 7.5), end=(3.25, 7.5), offset=1.5)
	drawing1.add_dimension(start=(3.5, 7.5), end=(8.0, 7.5), offset=1.5)
	drawing1.add_dimension(start=(8.25, 7.5), end=(11.75, 7.5), offset=1.5)
	drawing1.add_dimension(start=(0, 0.5), end=(12, 0.5), offset=-1.5)
	drawing1.add_dimension(start=(11.5, 0), end=(11.5, 8), offset=-1.5)

	drawing1.add_dimension(start=(3.5+4.5, 4.25), end=(3.5+4.5, 7.75), offset=1)
	drawing1.add_dimension(start=(3.5+4.5, 3.25), end=(3.5+4.5, 4.25), offset=1)

	drawing1.add_dimension(start=(3.5+4.5, 2.55+0.1), end=(3.5+4.5, 7.75), offset=2)

	drawing1.add_dimension(start=(3.5+4.5+0.5, CHIMNEY_Y_MID), end=(3.5+4.5+0.5, 3.2), offset=0)

	drawing1.render("upper.svg", png=True, png_dpi=600)

if "ceiling" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2", x=6, y=4, z=0.25+2.75+0.1, radius=8, storeys=[upper]
	)

	drawing1.add_stair_annotation(stairs1)
	drawing1.add_stair_annotation(stairs2)
	drawing1.add_chimney_annotation(chimney)

	drawing1.render("ceiling.svg", png=True, png_dpi=600)

# Drawing - cut1
if "cut1" in sys.argv:
	drawing1 = house.add_drawing(
		"Cut1",
		x=2.775,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("cut1.svg", png=True, png_dpi=600)

# Drawing - cut1
if "cut2" in sys.argv:
	drawing1 = house.add_drawing(
		"Cut2",
		x=7.275,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("cut2.svg", png=True, png_dpi=600)

# Drawing - cut3
if "cut3" in sys.argv:
	drawing1 = house.add_drawing(
		"Cut3",
		x=11.275,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("cut3.svg", png=True, png_dpi=600)

# Drawing - wall2
if "wall2" in sys.argv:
	drawing1 = house.add_drawing(
		"Wall2",
		x=0.25+3+0.1,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("wall2.svg", png=True, png_dpi=600)

# Drawing - wall3
if "wall3" in sys.argv:
	drawing1 = house.add_drawing(
		"Wall3",
		x=3.5+4.5+0.1,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("wall3.svg", png=True, png_dpi=600)
