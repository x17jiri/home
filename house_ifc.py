
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
#    - akusticky SDK: Knauf Silentboard

# Fasada:
#    - Centris Basic s bilym naterem
#        - tloustka 12mm (je nutna pro roztec rostu 600mm)
#        - https://www.dek.cz/produkty/detail/3025110040-cetris-basic-12mm-3350x1250mm-40ks-paleta-a2
#    - Rost delany pomoci OSB prilozek
#        - https://www.pasivnidomy.cz/detaily/napojeni-obvodovych-sten-v-miste-narozi-133

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

from math import acos, degrees, isclose
import sys, math
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

BWT = 0.24 # Basic wall thickness

ground_floor_height = 2.875
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
upper = house.storey("Upper floor", elevation=UPPER_FLOOR_START)

load_bearing_wall = house.wall_type(
    "Load bearing wall - VPC 240 mm",
    layers=[
        ("Brick", BWT),
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

HOUSE_DEPTH = 8.0
HALF_DEPTH = HOUSE_DEPTH / 2.0
KITCHEN_WIDTH = 4.75 - 0.03
HOUSE_WIDTH = 11.125

wall2_x = BWT + 3.0 - 0.03 + BWT;
wall3_x = wall2_x + KITCHEN_WIDTH + BWT;
stair_height = (
	ground_floor_height - GROUND_FLOOR_THICKNESS
	+ CEILING_THICKNESS + UPPER_FLOOR_THICKNESS)
step_count = 17
KK_WIDTH = HOUSE_WIDTH - wall3_x - BWT

HOUSE_EXT = 1
EXT_DIST_FROM_HALF = 1.5
EXT_DEPTH = HALF_DEPTH + EXT_DIST_FROM_HALF

# For now each finished-floor build-up is one homogeneous interior slab.  It
# can later be replaced with insulation, heating, and screed components without
# changing the storey elevations or the existing sill-height coordinates.
FLOOR_OUTLINE = (
	(-HOUSE_EXT+BWT, BWT),
	(HOUSE_WIDTH-BWT, BWT),
	(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
	(BWT, HOUSE_DEPTH-BWT),
	(BWT, EXT_DEPTH-BWT),
	(-HOUSE_EXT+BWT, EXT_DEPTH-BWT),
)
ground_floor_layer = ground.floor_layer(
	"Ground-floor build-up",
	outline=FLOOR_OUTLINE,
	thickness=GROUND_FLOOR_THICKNESS,
	color="#ffffff",
)

# Load-bearing walls
wall_front = ground.wall((-HOUSE_EXT, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_4 = ground.wall((HOUSE_WIDTH, 0), (HOUSE_WIDTH, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_back = ground.wall((HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_0 = ground.wall((-HOUSE_EXT, EXT_DEPTH), (-HOUSE_EXT, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_0x = ground.wall((BWT, EXT_DEPTH), (-HOUSE_EXT, EXT_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1 = ground.wall((0, HOUSE_DEPTH), (0, EXT_DEPTH-BWT), wall_type=load_bearing_wall, height=ground_floor_height)
wall_2 = ground.wall((wall2_x, 0), (wall2_x, HOUSE_DEPTH-0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)

ground.connect_wall(wall_0, wall_front)
ground.connect_wall(wall_0, wall_0x)
ground.connect_wall(wall_1, wall_0x)
ground.connect_wall(wall_1, wall_back)

ground.connect_wall(wall_2, wall_front, is_atpath=True)
ground.connect_wall(wall_2, wall_back, is_atpath=True)

ground.connect_wall(wall_3, wall_front, is_atpath=True)
ground.connect_wall(wall_3, wall_back, is_atpath=True)

ground.connect_wall(wall_4, wall_front)
ground.connect_wall(wall_4, wall_back)

# Front door/window

wall_front.add_door(
	at=HOUSE_EXT+wall3_x-BWT-0.5-1.125,
	opening_width=1.125, width=0.9,
	height=0.25+2.125,
	clear_height=door_clear_height,
	sill_height=GROUND_FLOOR_THICKNESS,
	operation="SINGLE_SWING_RIGHT"
)
wall_front.add_window(
    at=HOUSE_EXT+wall3_x+0.25,
    width=0.5,
    height=0.25+2.125,
    sill_height=0.25+2.125-0.375,
    partition="SINGLE_PANEL",
)

# Back windows
print("KK_WIDTH=", KK_WIDTH)
wall_back.add_window(
	at=2*BWT+KK_WIDTH+math.floor((KITCHEN_WIDTH-2.5)/0.125)*0.125/2, width=2.5, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_window(
	at=3+KITCHEN_WIDTH+BWT+0.75-0.125,
	width=1.5, sill_height=0.25+0.875, height=0.25+2.25)
wall_back.add_door(
	at=BWT+KK_WIDTH-0.125-1,
	width=0.8, sill_height=0.25+0.1, height=0.25+2.25, opening_width=1, clear_height=2,
	operation="SINGLE_SWING_RIGHT",)


# Posilovna, Gym
wall_gym = ground.wall(
	(-HOUSE_EXT+BWT, BWT+2.25), (wall2_x-BWT, BWT+2.25),
	wall_type=partition_wall, height=ground_floor_height)
wall_2.add_opening(
	at=BWT+0.625,
	width=1, sill_height=0.25+0.1, height=0.25+2.25)
wall_gym.add_door(
	at=HOUSE_EXT+wall2_x-2*BWT-1-0.125,
	width=0.9, sill_height=0.25+0.1, height=0.25+2.25, opening_width=1, clear_height=2,
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True)


# Bathroom, Koupelna
BATHROOM_DEPTH = 2.6
wall_bathroom = ground.wall(
	(wall3_x, BWT+BATHROOM_DEPTH), (HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
ground.furniture(
    "TČ",
    kind="USERDEFINED",
    size=(1.2, 0.5, 1.5),
    color="#ffffff",
    center=(HOUSE_WIDTH-5.5, 0-0.5),
)
ground.furniture(
    "TČ",
    kind="USERDEFINED",
    size=(0.5, 0.4, 0.9),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(HOUSE_WIDTH-(BWT+1.6)-0.4, BWT+0.25),
)
ground.furniture(
    "Zásobník\nTUV",
    kind="USERDEFINED",
    size=(0.7, 0.7, 2.0),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(HOUSE_WIDTH-(BWT+0.4), BWT+0.4),
)
ground.furniture(
    "Pračka",
    kind="USERDEFINED",
	start_height=GROUND_FLOOR_THICKNESS,
    size=(0.7, 0.7, 2.0),
    color="#ffffff",
    center=(HOUSE_WIDTH-BWT-0.4, BWT+0.8+0.4),
)
ground.asset(
	"Gauc", asset="3_seater_sofa",
	center=(wall2_x+1.2, 7.2),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.asset(
	"Gauc", asset="1_seater_sofa",
	center=(wall2_x+0.6, 6.2),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=90,
)
ground.asset(
    "Umyv",
    asset="basin_large",
    center=(HOUSE_WIDTH-(BWT+0.8)-0.4, BWT+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=180,
)
ground.asset(
    "Sprcha",
    asset="shower_90x90",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-(BWT+0.5), BWT+BATHROOM_DEPTH-0.5),
	rotation=0,
)
ground.asset(
    "WC",
    asset="toilet_without_cistern",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-(BWT+KK_WIDTH)+0.4, BWT+BATHROOM_DEPTH-0.5),
    rotation=90,
)

# Kitchen, Kuchyn
CHODBA_DEPTH = 2.6
wall_kitchen = ground.wall(
	(wall2_x, BWT+CHODBA_DEPTH),
	(wall2_x+KITCHEN_WIDTH, BWT+CHODBA_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
wall_kitchen.add_door(
	at=KITCHEN_WIDTH-2.125,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=True
)

# Pokoj Risanek
wall_2.add_door(
	at=HOUSE_DEPTH-BWT-3.5,
	opening_width=1.0, width=0.9,
	height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_LEFT",
#	reverse_swing=True,
)

# Oblouk
wall_3.add_opening(
	at=math.floor((0.25+CHODBA_DEPTH+0.15+1)/0.125)*0.125,
	width=2,
    height=0.25+2.125,
    sill_height=GROUND_FLOOR_THICKNESS,
	name="Oblouk"
)

# Bathroom
wall_3.add_door(
    at=BWT+0.625,
    opening_width=1.0, width=0.9,
    height=0.25+2.125,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	reverse_swing=True,
)

# Main hallway
stairs1 = ground.stair(
    (wall2_x+1+4*0.27, BWT+0.5),       # bottom centre
    (wall2_x+1, BWT+0.5),       # upper landing edge centre
    width=1.0,
	start_height=GROUND_FLOOR_THICKNESS,
    height=stair_height/17*5,
    risers=5,
    name="Main stair",
    color="#C8B090",
    underside="sloped",
    waist_thickness=0.15,)

stairs2 = ground.stair(
    (wall2_x+0.5, BWT+CHODBA_DEPTH-1-2*0.27),
    (wall2_x+0.5, BWT+CHODBA_DEPTH-1),
    width=1.0,
    height=stair_height/17*3,
    risers=3,
    start_height=stairs1.end_height,
    name="Main stair",
    color="#C8B090",
    underside="sloped",
    waist_thickness=0.15,)

stairs3 = ground.stair(
    (wall2_x+1, BWT+CHODBA_DEPTH-0.5),
    (wall2_x+1+8*0.27, BWT+CHODBA_DEPTH-0.5),
    width=1.0,
    height=stair_height/17*9,
    risers=9,
    start_height=stairs2.end_height,
    name="Main stair",
    color="#C8B090",
    underside="sloped",
    waist_thickness=0.15,)

stairs_landing1 = ground.stair_landing(
    (wall2_x+0, BWT),
    (wall2_x+1, BWT+CHODBA_DEPTH-1-2*0.27),
    height=stairs1.end_height,
    thickness=0.20,
    name="Main stair landing",
    color="#C8B090",
)
stairs_landing2 = ground.stair_landing(
    (wall2_x+0, BWT+CHODBA_DEPTH-1),
    (wall2_x+1, BWT+CHODBA_DEPTH),
    height=stairs2.end_height,
    thickness=0.20,
    name="Main stair landing",
    color="#C8B090",
)

# Chimney
CHIMNEY_DIST=0.47
CHIMNEY_Y_START = HALF_DEPTH - 0.8 - 0.07 - 0.05 - 0.4
CHIMNEY_Y_START = 0.125*math.floor((CHIMNEY_Y_START - 0.04 - 0.17) / 0.125) + 0.04 + 0.17
CHIMNEY_Y_START = CHIMNEY_Y_START + 0.025 - 0.125

CHIMNEY_Y_START = BWT + CHODBA_DEPTH - 0.45 # override

CHIMNEY_Y_MID = CHIMNEY_Y_START + 0.2
CHIMNEY_Y_END = CHIMNEY_Y_START + 0.4

print("CHIMNEY_Y_START = ", CHIMNEY_Y_START)
print("CHIMNEY_Y_MID = ", CHIMNEY_Y_MID)
print("CHIMNEY_Y_END = ", CHIMNEY_Y_END)

chimney = ground.chimney(
    center=(wall3_x-BWT-0.05-0.2, CHIMNEY_Y_MID),
    size=0.4,
    height=8.8,
    flue_diameter=0.18,
    start_height=0,
    name="Main chimney",
    material="Chimney",
    color="#B8A99A",
)

ground.furniture(
    "Kamna",
    kind="USERDEFINED",
    size=(0.5, 0.6, 1.5),
    color="#ffff2B",
    center=(wall3_x-BWT-0.5, BWT+2.6+BWT+0.4),
	start_height=GROUND_FLOOR_THICKNESS,
    rotation=-45,
)

# Kuchyn
#print("SEARCH: ", "\n".join(str(x) for x in house.assets.search("table")))
ground.furniture(
	"Dřez",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-BWT-0.35, BWT+BATHROOM_DEPTH+0.15+0.35),
)
ground.furniture(
	"Myčka",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-BWT-0.35-0.7, BWT+BATHROOM_DEPTH+0.15+0.35),
)
ground.furniture(
	"Lednice",
    kind="USERDEFINED",
    size=(0.7, 1, 2),
    center=(HOUSE_WIDTH-BWT-0.35, HOUSE_DEPTH-BWT-0.5),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.furniture(
	"Sporák",
    kind="USERDEFINED",
    size=(0.7, 0.7, 0.8),
    center=(HOUSE_WIDTH-BWT-0.35, BWT+BATHROOM_DEPTH+0.15+0.35+0.7),
	start_height=GROUND_FLOOR_THICKNESS,
)
KUCH_LINKA_LEN = HOUSE_DEPTH-2*BWT-0.15-BATHROOM_DEPTH-2.4
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(0.7, KUCH_LINKA_LEN, 0.8),
    center=(HOUSE_WIDTH-BWT-0.35, HOUSE_DEPTH-BWT-1-KUCH_LINKA_LEN/2),
	start_height=GROUND_FLOOR_THICKNESS,
)
KUCH_LINKA_LEN = KK_WIDTH-1.4
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(KUCH_LINKA_LEN, 0.7, 0.8),
    center=(HOUSE_WIDTH-BWT-1.4-KUCH_LINKA_LEN/2, BWT+BATHROOM_DEPTH+0.15+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
)
ground.asset(
    "Stul",
    asset="retail_4_seater_rectangular_table",
    center=(wall2_x+1.2, 2*BWT+CHODBA_DEPTH+0.8),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=90,
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
			BWT+3.5+BWT+0.5 - lath_width-window_space, BWT+3.5+BWT+0.5 + 1 + window_space,
			BWT+3.5+BWT+0.5 + 1.5 + window_space,
			BWT+3.5+BWT+0.5+1+1 - lath_width-window_space, BWT+3.5+BWT+0.5+1+1 + 1.5 + window_space,
			BWT+3.5+BWT+KITCHEN_WIDTH+BWT+0.75 - lath_width-window_space, BWT+3.5+BWT+KITCHEN_WIDTH+BWT+0.75 + 1.5 + window_space,
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
			BWT+0.875-lath_width-window_space,
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
			BWT+3.5+BWT+0.5 - lath_width-window_space, BWT+3.5+BWT+0.5 + 1 + window_space,
			BWT+3.5+BWT+0.5 + 1.5 + window_space,
			BWT+3.5+BWT+0.5+1+1 - lath_width-window_space, BWT+3.5+BWT+0.5+1+1 + 1.5 + window_space,
			BWT+3.5+BWT+KITCHEN_WIDTH+BWT+0.75 - lath_width-window_space, BWT+3.5+BWT+KITCHEN_WIDTH+BWT+0.75 + 1.5 + window_space,
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
ceiling1_a = upper.miako_slab(
    "Ceiling 1 a",
    start=(0.1 - HOUSE_EXT, BWT+2.06),
    end=(wall2_x-0.15, BWT+2.06),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, 1),
    structure=[
		"beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide"
		],
)
ceiling1_b = upper.miako_slab(
    "Ceiling 1 b",
    start=(0.1, BWT+2.06 + 3.0),
    end=(wall2_x-0.15, BWT+2.06 + 3.0),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, 1),
	expected_width=HOUSE_DEPTH-2*BWT - 3.0 -2.06+0.04,
    structure=[
        "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide",
		],
)
ceiling2 = upper.miako_slab(
    "Ceiling 2",
    start=(wall2_x-0.125, BWT+CHODBA_DEPTH),
    end=(wall3_x-0.125, BWT+CHODBA_DEPTH),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, 1),
	expected_width=HOUSE_DEPTH-2*BWT-CHODBA_DEPTH,
    structure=[
		"beam",
		"beam",
		"beam",

		"wide", "beam", "beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam"
		],
)
ceiling2_b =  upper.miako_slab(
    "Ceiling 2 b",
    start=(wall3_x-BWT-0.5, BWT-0.15),
    end=(wall3_x-BWT-0.5, BWT+CHODBA_DEPTH),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(-1, 0),
	expected_width=KITCHEN_WIDTH+0.04-(1.5+8*0.27 + 0.05),
    structure=[
		"beam",
		"wide",
		"beam",
		"beam"
		],
)

ceiling3 = upper.miako_slab(
    "Ceiling 3",
    start=(wall3_x-0.1, HOUSE_DEPTH-BWT+0.04),
    end=(HOUSE_WIDTH-0.1, HOUSE_DEPTH-BWT+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, -1),
	expected_width=HOUSE_DEPTH-2*BWT+0.08,
    structure=[
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide",
		],
)

upper_pokoj_1 = upper.floor_layer(
		f"Upper Pokoj 1",
		outline=(
			(-HOUSE_EXT+BWT, ceiling1_a.start[1]+0.1),
			(wall2_x-BWT, ceiling1_a.start[1]+0.1),
			(wall2_x-BWT, HOUSE_DEPTH-BWT),
			(BWT, HOUSE_DEPTH-BWT),
			(BWT, EXT_DEPTH-BWT),
			(-HOUSE_EXT+BWT, EXT_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		color="#ffffff",
	)

upper_floor_layers = (
	upper_pokoj_1
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
DORMER_WALL_HEIGHT = 2.5+0.125
DORMER_ROOF_PLANE_POINTS = (
	(0, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, HOUSE_DEPTH-0.125+0.08, UPPER_FLOOR_START+DORMER_WALL_HEIGHT+0.12),
)
FLAT_CEILING_ROOF_PLANE_POINTS = (
	(0, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(10, STREET_ROOF_JOINT_Y, ROOF_JOINT_Z),
	(0, GARDEN_ROOF_JOINT_Y, ROOF_JOINT_Z),
)
STREET_GYPSUM_PLASTERBOARD_CUT = offset_plane(
	*STREET_ROOF_PLANE_POINTS,
	offset=GYPSUM_PLASTERBOARD_BOTTOM,
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
	(wall3_x, HOUSE_DEPTH), (wall2_x-BWT, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=DORMER_WALL_HEIGHT-NADEZDIVKA, start_height=NADEZDIVKA)
wall_front = upper.wall((-HOUSE_EXT, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_back = upper.wall(
	(HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_0 = upper.wall(
	(-HOUSE_EXT, EXT_DEPTH-BWT), (-HOUSE_EXT, BWT),
	wall_type=load_bearing_wall,
	height=4, cuts=wall_cuts_1_4, )
wall_0x = upper.wall(
	(BWT, EXT_DEPTH), (-HOUSE_EXT, EXT_DEPTH),
	wall_type=load_bearing_wall,
	height=COLLAR_TIE_BOTTOM_HEIGHT-0.12, cuts=wall_cuts_1_4, )
wall_1 = upper.wall(
	(0, HOUSE_DEPTH-BWT), (0, EXT_DEPTH),
	wall_type=load_bearing_wall,
	height=4, cuts=wall_cuts_1_4, )
#wall_1.add_opening(at=0, width=BWT, height=1.5, sill_height=NADEZDIVKA)
#wall_0.add_opening(at=HOUSE_DEPTH-EXT_DEPTH-BWT, width=BWT, height=1.5, sill_height=NADEZDIVKA)

wall_2 = upper.wall(
	(wall2_x, 0.002), (wall2_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_2.add_opening(
	at=3.625, width=0.75, height=UNDER_HOLE+0.25, sill_height=UNDER_HOLE)
# okno ninja gym
wall_2.add_opening(
	at=BWT+0.625,
	width=1, height=1.25)

wall_3 = upper.wall(
	(wall3_x, 0.002), (wall3_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_3.add_opening(
	at=3.625, width=0.75, height=UNDER_HOLE+0.25, sill_height=UNDER_HOLE)

wall_3.add_opening(
    at=BWT+CHODBA_DEPTH,
    width=1,
    height=2.25,
)

wall_4 = upper.wall(
	(HOUSE_WIDTH, 0.002), (HOUSE_WIDTH, HOUSE_DEPTH-0.002),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_4.add_opening(at=0, width=BWT, height=1.5, sill_height=NADEZDIVKA)
wall_4.add_opening(at=7.75, width=BWT, height=1.5, sill_height=NADEZDIVKA)

wall_pokoj1 = upper.wall(
	start=(-HOUSE_EXT+BWT, ceiling1_a.start[1]),
	end=(wall2_x-BWT, ceiling1_a.start[1]),
	wall_type=dry_wall, height=UNDER_HOLE + 0.15)
wall_pokoj2 = upper.wall(
	start=(wall2_x, BWT+CHODBA_DEPTH+1.0),
	end=(wall3_x-BWT, BWT+CHODBA_DEPTH+1.0),
	wall_type=dry_wall, height=UNDER_HOLE + 0.15)
wall_zachod_nahore = upper.wall(
	start=(HOUSE_WIDTH-BWT, BWT+CHODBA_DEPTH),
	end=(wall3_x, BWT+CHODBA_DEPTH),
	wall_type=dry_wall, height=UNDER_HOLE + 0.15)
wall_zachod_nahore.add_door(
	at=0.8,
	opening_width=0.8, width=0.7,
	height=2.25,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=True)
upper.asset(
    "WC",
    asset="toilet_without_cistern",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-(BWT+KK_WIDTH)+0.4, BWT+BATHROOM_DEPTH-0.5),
    rotation=90,
)
upper.asset(
    "Umyv",
    asset="basin_large",
    center=(HOUSE_WIDTH-BWT-0.4, BWT+CHODBA_DEPTH+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=180,
)
#wall_zachod_nahore.add_door(
#	at=KITCHEN_WIDTH-1,
#	opening_width=0.8, width=0.7,
#	height=2.25,
#	clear_height=door_clear_height,
#	sill_height=UPPER_FLOOR_THICKNESS,
#	operation="SINGLE_SWING_RIGHT",
#	reverse_swing=True)
#wall_zachod_nahore_2 = upper.wall(
#	start=(3.5+1.2, 2.55),
#	end=(3.5+1.2, BWT),
#	wall_type=dry_wall,
#	height=UNDER_HOLE - 0.05 - GYPSUM_PLASTERBOARD_THICKNESS,
#	cuts=[STREET_GYPSUM_PLASTERBOARD_CUT],
#)

#upper.connect_wall(wall_0, wall_front)
#upper.connect_wall(wall_0, wall_0x)
#upper.connect_wall(wall_1, wall_0x)
#upper.connect_wall(wall_1, wall_back)
#
#upper.connect_wall(wall_2, wall_front, is_atpath=True)
#upper.connect_wall(wall_2, wall_back, is_atpath=True)
#upper.connect_wall(wall_2, wall_dormer)
#
#upper.connect_wall(wall_3, wall_front, is_atpath=True)
#upper.connect_wall(wall_3, wall_back, is_atpath=True)
#upper.connect_wall(wall_3, wall_dormer)
#
#upper.connect_wall(wall_4, wall_front)
#upper.connect_wall(wall_4, wall_back)


beam1 = upper.beam(
    "Beam",
    start=(-HOUSE_EXT, HALF_DEPTH-0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    end=(HOUSE_WIDTH, HALF_DEPTH-0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam2 = upper.beam(
    "Beam",
    start=(-HOUSE_EXT, HALF_DEPTH+0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    end=(HOUSE_WIDTH, HALF_DEPTH+0.8, UPPER_FLOOR_START+UNDER_HOLE+0.5+0.12),
    size=(0.14, 0.24),
    material="Wood",
    kind="BEAM",
)
beam3 = upper.beam(
    "Beam",
    start=(-HOUSE_EXT, 0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    end=(HOUSE_WIDTH, 0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam4_a = upper.beam(
    "Beam",
    start=(0, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    end=(wall2_x-BWT, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam4_b = upper.beam(
    "Beam",
    start=(wall3_x, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    end=(HOUSE_WIDTH, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+NADEZDIVKA+0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam4_c = upper.beam(
    "Beam",
    start=(-HOUSE_EXT, EXT_DEPTH-0.125, UPPER_FLOOR_START+COLLAR_TIE_BOTTOM_HEIGHT-0.06),
    end=(BWT, EXT_DEPTH-0.125, UPPER_FLOOR_START+COLLAR_TIE_BOTTOM_HEIGHT-0.06),
    size=(0.16, 0.12),
    material="Wood",
    kind="BEAM",
)
beam_dormer = upper.beam(
    "Beam",
    start=(wall3_x+0.3, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+DORMER_WALL_HEIGHT+0.06),
    end=(BWT+3-0.3, HOUSE_DEPTH-0.125, UPPER_FLOOR_START+DORMER_WALL_HEIGHT+0.06),
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
    center=(HOUSE_WIDTH-BWT-0.3, 7.75-2),
	rotation=90,
	start_height=UPPER_FLOOR_THICKNESS,
)

# Okna obyvak
wall_dormer.add_window(
	at=BWT+0.5,width=1.5, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
wall_dormer.add_window(
	at=BWT+KITCHEN_WIDTH-0.5-1.5,
	width=1.5, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
# Dvere obyvak
#wall_3.add_door(
#	at=math.ceil(CHIMNEY_Y_END/0.125)*0.125,
#	opening_width=1, width=0.9,
#	height=2.25,
#	clear_height=door_clear_height,
#	sill_height=UPPER_FLOOR_THICKNESS,
#	operation="SINGLE_SWING_LEFT")
# Dvere pokojik nahore
wall_2.add_door(
	at=BWT+CHODBA_DEPTH,
	opening_width=1, width=0.9,
	height=2.25,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
# Okna pokojik nahore
wall_0.add_window(
	at=1,
	width=1.5,
	height=2.25,
	sill_height=1, partition="SINGLE_PANEL",)
wall_0x.add_window(
	at=BWT,
	width=HOUSE_EXT-BWT,
	height=2.25,
	sill_height=1, partition="SINGLE_PANEL",)
# Okno k sousedum nahore
wall_4.add_window(
	at=HALF_DEPTH-0.75,
	width=1.5,
	height=2.25,
	sill_height=NADEZDIVKA, partition="SINGLE_PANEL",)

# Roof

roof = upper.roof("Main roof")

roof_inner_cuts = [
	((0, BWT, 0), (10, BWT, 0), (0, BWT, 10)),
	((0, 7.75, 0), (10, 7.75, 0), (0, 7.75, 10)),
	(
		(-HOUSE_EXT+BWT, 0, 0),
		(-HOUSE_EXT+BWT, 10, 0),
		(-HOUSE_EXT+BWT, 0, 10),
	),
	((HOUSE_WIDTH-BWT, 0, 0), (HOUSE_WIDTH-BWT, 10, 0), (HOUSE_WIDTH-BWT, 0, 10)),
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
extension_garden_roof = roof.plane(
	"Garden extension slope",
	points=GARDEN_ROOF_PLANE_POINTS,
	cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		(
			(0, EXT_DEPTH+0.5, 0),
			(10, EXT_DEPTH+0.5, 0),
			(0, EXT_DEPTH+0.5, 10),
		),
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

def d_raft(x):
	return ("dormer", x)

rafters = [
	-0.09, 0.43,
	0.66, 0.66, 0.66, 0.66,

	d_raft(0.06), 0.60, ###################################
	d_raft(0.06), 0.60,
	d_raft(0.06), 0.60,
	d_raft(0.06), 0.60,
	d_raft(0.06), d_raft(0.55),
	0.06, d_raft(0.60),
	0.06, d_raft(0.60),
	0.06, d_raft(0.60), ###################################

	0.06, 0.80, ################################### komin
	0.66, 0.66, 0.66,
	0.54
	]
rafter_positions = []
rafter_keywords = []
rafter_x = 0
for rafter in rafters:
	if isinstance(rafter, tuple):
		keyword, distance = rafter
	else:
		keyword, distance = None, rafter
	rafter_x += distance
	rafter_positions.append(rafter_x)
	rafter_keywords.append(keyword)

dormer_rafter_indices = [
	i for i, keyword in enumerate(rafter_keywords)
	if keyword == "dormer"
]
dormer_x_min = min(rafter_positions[i] for i in dormer_rafter_indices)
dormer_x_max = max(rafter_positions[i] for i in dormer_rafter_indices)
roof_x_ranges = (
	(-HOUSE_EXT, 0),
	(0, wall2_x-BWT),
	(wall2_x-BWT, wall3_x),
	(wall3_x, HOUSE_WIDTH),
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
extension_garden_inner_boundaries = independent_inner_layer_boundaries(
	extension_garden_roof
)
dormer_inner_boundaries = independent_inner_layer_boundaries(dormer_roof)
extension_outer_y_min, extension_outer_y_max = local_y_limits_from_cuts(
	extension_garden_roof,
	ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS / 2,
)
# Keep the uncut solid's centroid between the two close extension cuts so the
# half-spaces retain the ridge-to-eave portion.  A small overshoot leaves the
# actual edges to the cut planes.
extension_outer_y_min -= 0.25
extension_outer_y_max += 0.25


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
	(
		"Street segment 0",
		"Street segment 1",
		"Street segment 2",
		"Street segment 3",
	),
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
	extension_garden_roof,
	"Garden segment 0",
	*roof_x_ranges[0],
	extension_outer_y_min,
	extension_outer_y_max,
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		extension_garden_roof,
		extension_garden_inner_boundaries,
		EXT_DEPTH-0.25,
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 1", *roof_x_ranges[1], roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 2 above dormer",
	*roof_x_ranges[2], roof_y_min, 0,
	include_inner=False,
)
add_continuous_roof_layers(
	dormer_roof, "Dormer segment 2", *roof_x_ranges[2], 0,
	roof_y_max-1, # overshoot a little less for the dormer so our cuts work properly
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		dormer_roof, dormer_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 3", *roof_x_ranges[3], roof_y_min, roof_y_max,
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
for part_name, (x_min, x_max), garden_side_plane in zip(
	(
		"Flat ceiling segment 0",
		"Flat ceiling segment 1",
		"Flat ceiling segment 2",
		"Flat ceiling segment 3",
	),
	roof_x_ranges,
	(extension_garden_roof, garden_roof, dormer_roof, garden_roof),
):
	add_continuous_roof_layers(
		flat_ceiling_roof,
		part_name,
		x_min,
		x_max,
		BWT - STREET_ROOF_JOINT_Y,
		HOUSE_DEPTH-BWT - STREET_ROOF_JOINT_Y,
		inner_cuts=roof_inner_cuts,
		inner_y_limits=flat_inner_y_limits(
			street_inner_boundaries,
			(
				dormer_inner_boundaries
				if garden_side_plane is dormer_roof
				else (
					extension_garden_inner_boundaries
					if garden_side_plane is extension_garden_roof
					else garden_inner_boundaries
				)
			),
		),
		inner_layout=FLAT_CEILING_INNER_LAYER_LAYOUT,
		include_outer=False,
	)

# A batten whose centre lies completely beyond a cut would retain the wrong
# half-space, so derive the first and last tile-batten rows from the cuts.  The
# shortened extension's rafters and counter-battens use the same approach.
tile_batten_centerline_z = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1] / 2
street_y_min, street_y_max = local_y_limits_from_cuts(
	street_roof, tile_batten_centerline_z
)
garden_y_min, garden_y_max = local_y_limits_from_cuts(
	garden_roof, tile_batten_centerline_z
)
extension_garden_y_min, extension_garden_y_max = local_y_limits_from_cuts(
	extension_garden_roof, tile_batten_centerline_z
)
extension_rafter_y_min, extension_rafter_y_max = local_y_limits_from_cuts(
	extension_garden_roof, RAFTER_Z_OFFSET + RAFTER_SIZE[1] / 2
)
extension_counter_batten_y_min, extension_counter_batten_y_max = local_y_limits_from_cuts(
	extension_garden_roof,
	COUNTER_BATTEN_BOTTOM + COUNTER_BATTEN_SIZE[1] / 2,
)
dormer_y_min, dormer_y_max = local_y_limits_from_cuts(
	dormer_roof, tile_batten_centerline_z
)
add_tile_battens(
	street_roof, "Street", roof_x_ranges, street_y_min, street_y_max
)
add_tile_battens(
	extension_garden_roof,
	"Garden segment 0",
	[roof_x_ranges[0]],
	extension_garden_y_min,
	extension_garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden segments 1 and 3",
	[roof_x_ranges[1], roof_x_ranges[3]],
	garden_y_min,
	garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden segment 2 above dormer",
	[roof_x_ranges[2]],
	garden_y_min,
	0,
)
add_tile_battens(
	dormer_roof,
	"Dormer segment 2",
	[roof_x_ranges[2]],
	0,
	dormer_y_max,
)

for i, rafter_x in enumerate(rafter_positions):
	print("rafter_x = ", rafter_x)
	is_dormer_rafter = i in dormer_rafter_indices
	if not is_dormer_rafter:
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

	if is_dormer_rafter:
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
		under_dormer = dormer_x_min < rafter_x < dormer_x_max
		garden_side_plane = (
			extension_garden_roof if rafter_x < 0 else garden_roof
		)
		if garden_side_plane is extension_garden_roof:
			rafter_y_min = extension_rafter_y_min - 0.25
			rafter_y_max = extension_rafter_y_max + 0.25
			counter_batten_y_min = extension_counter_batten_y_min - 0.25
			counter_batten_y_max = extension_counter_batten_y_max + 0.25
		else:
			rafter_y_min = -2
			rafter_y_max = 0.7 if under_dormer else 5
			counter_batten_y_min = -2
			counter_batten_y_max = 0 if under_dormer else 5
		rafter = garden_side_plane.beam(
			"Rafter 1",
			start=(rafter_x, rafter_y_min),
			end=(rafter_x, rafter_y_max),
			z_offset=RAFTER_Z_OFFSET,
			size=RAFTER_SIZE,
			kind="RAFTER",
		)
		roof_layer_storeys["Rafters"].add(rafter)
		counter_batten = garden_side_plane.beam(
			f"Garden counter-batten {i + 1}",
			start=(rafter_x, counter_batten_y_min),
			end=(rafter_x, counter_batten_y_max),
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
		x=5,
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
	drawing1.add_stair_annotation(stairs3)
	drawing1.add_chimney_annotation(chimney)

	# Risankuv pokoj hloubka
	drawing1.add_dimension(start=(BWT, BWT+2.25+0.15), end=(BWT, HOUSE_DEPTH-BWT), offset=1.5+HOUSE_EXT)
	drawing1.add_dimension(start=(BWT, BWT+2.25+0.15), end=(BWT, EXT_DEPTH-BWT), offset=1+HOUSE_EXT)
	# Risankuv pokoj extense
	drawing1.add_dimension(start=(-HOUSE_EXT+BWT, 4), end=(BWT, 4), offset=0)
	# Kuchyn, stredni cast, pokoj hloubka
	drawing1.add_dimension(start=(wall2_x+2.55, BWT+CHODBA_DEPTH+0.15), end=(wall2_x+2.5, HOUSE_DEPTH-BWT), offset=0)

	drawing1.add_dimension(start=(BWT, 7.5), end=(wall2_x-BWT, 7.5), offset=1.5)
	drawing1.add_dimension(start=(wall2_x, 7.5), end=(wall3_x-BWT, 7.5), offset=1.5)
	drawing1.add_dimension(start=(wall3_x, 7.5), end=(HOUSE_WIDTH-BWT, 7.5), offset=1.5)
	drawing1.add_dimension(start=(0, 0.5), end=(HOUSE_WIDTH, 0.5), offset=-1.5)
	drawing1.add_dimension(start=(HOUSE_WIDTH-0.5, 0), end=(HOUSE_WIDTH-0.5, 8), offset=-1.5)

	drawing1.add_entrance_arrow(
		(3.5+KITCHEN_WIDTH+1.1, -0.5),
		rotation=90,  # points left
		size=0.6,      # metres
	)

	drawing1.add_room_annotation(
		(1.5, 6),
		identifier="0.01",
		area=5.12*2.97 + 1.125*2.62,   # m²
	)
	drawing1.add_room_annotation(
		(wall3_x - 1.5, HOUSE_DEPTH - 1.5),
		identifier="0.02",
		area=
			(HOUSE_DEPTH-2*BWT-0.15-CHODBA_DEPTH)*KITCHEN_WIDTH
			+ (HOUSE_DEPTH-2*BWT-0.15-BATHROOM_DEPTH)*KK_WIDTH,   # m²
	)
	drawing1.add_room_annotation(
		(HOUSE_WIDTH-1.4, BWT+1.25),
		identifier="0.05",
		area=KK_WIDTH*BATHROOM_DEPTH,   # m²
	)
	drawing1.add_room_annotation(
		(7, 0.5+0.9),
		identifier="0.04",
		area=CHODBA_DEPTH*KITCHEN_WIDTH,   # m²
	)
	drawing1.add_room_annotation(
		(1, 1),
		identifier="0.03",
		area=(2.97+1.125)*2.25,   # m²
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
		"Drawing 2", x=6, y=4, z=BWT+2.75+2, radius=8, storeys=[upper]
	)

	drawing1.add_stair_annotation(stairs1)
	drawing1.add_stair_annotation(stairs2)
	drawing1.add_stair_annotation(stairs3)
	drawing1.add_stair_landing_annotation(stairs_landing1)
	drawing1.add_stair_landing_annotation(stairs_landing2)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_room_annotation(
		(1.5, 6),
		identifier="P.01",
		area=upper_pokoj_1.area
	)

	drawing1.render("upper.svg", png=True, png_dpi=600)

if "ceiling" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2", x=6, y=4, z=2.875+0.1, radius=8, storeys=[upper]
	)

	drawing1.add_stair_annotation(stairs1)
	drawing1.add_stair_annotation(stairs2)
	drawing1.add_stair_annotation(stairs3)
	drawing1.add_stair_landing_annotation(stairs_landing1)
	drawing1.add_stair_landing_annotation(stairs_landing2)
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
		x=11.275-0.5,
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
		x=BWT+3+0.1,
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
		x=3.5+KITCHEN_WIDTH+0.1,
		y=4,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("wall3.svg", png=True, png_dpi=600)

# Drawing - wall_back
if "wall_back" in sys.argv:
	drawing1 = house.add_drawing(
		"wall_back",
		x=HOUSE_WIDTH/2,
		y=7.75+0.1,
		z=3.5,
		radius=8,
		view="elevation",
		direction=(0, -1, 0),
		storeys=None,
		doors_closed=True,
	)
	drawing1.render("wall_back.svg", png=True, png_dpi=600)
