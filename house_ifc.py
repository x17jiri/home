
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

RAFTER_Z_OFFSET = -0.04
RAFTER_THICKNESS = 0.08
RAFTER_SIZE = (RAFTER_THICKNESS, 0.20)
VAPOUR_BARRIER_THICKNESS = 0.001
THERMAL_INSULATION_UNDER_RAFTERS = 0
INSTALLATION_SPACE_THICKNESS = 0.08
GYPSUM_PLASTERBOARD_THICKNESS = 0.015
WOOD_FIBERBOARD_THICKNESS = 0.1
UNDERLAY_THICKNESS = 0.005
COUNTER_BATTEN_SIZE = (0.04, 0.06)
TILE_BATTEN_SIZE = (0.06, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_THICKNESS = 0.05
GROUND_FLOOR_THICKNESS = 0.17
UPPER_FLOOR_THICKNESS = 0.10
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
CEILING_FINISH_THICKNESS = 0.02
CEILING_FINISH_MATERIAL = "Ceiling finish"
FOUNDATION_BASE_PLATE_THICKNESS = 0.20
FOUNDATION_WALL_HEIGHT = 0.80
FOUNDATION_FOOTER_WIDTH = 0.70
FOUNDATION_FOOTER_HEIGHT = 0.50
RING_BEAM_BAR_DIAMETER = 0.03
RING_BEAM_CONCRETE_COVER = 0.05
VAZNICE_DIST = 0.85 # Vzdalenost vaznice od hrebene
VAZNICE_HEIGHT = 0.28

THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM = (
	RAFTER_Z_OFFSET - THERMAL_INSULATION_UNDER_RAFTERS
)
VAPOUR_BARRIER_BOTTOM = (
	THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM - VAPOUR_BARRIER_THICKNESS
)
GYPSUM_PLASTERBOARD_BOTTOM = (
	VAPOUR_BARRIER_BOTTOM
	- INSTALLATION_SPACE_THICKNESS
	- GYPSUM_PLASTERBOARD_THICKNESS
)

BWT = 0.24 # Basic wall thickness
POLYSTYRENE_INSULATION_THICKNESS = 0.16 + 0.0075
ROCKWOOL_INSULATION_THICKNESS = 0.20 + 0.0075

ground_floor_height = 2.82
door_clear_height = 2.1
CEILING_THICKNESS = 0.21

UNDER_HOLE = 2.85
HOLE_HEIGHT = 0.25
ABOVE_HOLE = 0.25
UPPER_FLOOR_START = ground_floor_height + CEILING_THICKNESS
COLLAR_TIE_THICKNESS = 0.06
COLLAR_TIE_SIZE = (COLLAR_TIE_THICKNESS, 0.16)
COLLAR_TIE_EXTENSION = 1.5
COLLAR_TIE_X_OFFSET = (RAFTER_SIZE[0] + COLLAR_TIE_SIZE[0]) / 2
# The collar-tie tops meet the underside of the two central purlins and the
# wall below them.  The horizontal vapour barrier is derived from the tie
# underside so the two cannot drift apart when the framing changes.
COLLAR_TIE_TOP_HEIGHT = UNDER_HOLE + HOLE_HEIGHT + ABOVE_HOLE
COLLAR_TIE_BOTTOM_HEIGHT = COLLAR_TIE_TOP_HEIGHT - COLLAR_TIE_SIZE[1]
NADEZDIVKA = 1.25

house = House(
    "My house",
    mirror_x=True,
    colors={
        "wall": "#ffffff",
        "door": "#8B5A2B",
        "window": "#4A90E2",
    },
)

foundation = house.storey("Foundations", elevation=0)
ground = house.storey("Ground floor", elevation=0)
upper = house.storey("Upper floor", elevation=UPPER_FLOOR_START)

load_bearing_wall = house.wall_type(
    "Load bearing wall - VPC 240 mm",
    layers=[
        ("Brick", BWT),
        "axis",
    ],
)

foundation_wall = house.wall_type(
	"Foundation wall - ztracene bedneni 240 mm",
	layers=[
		("ztracene bedneni", BWT),
		"axis",
	],
	color="#A9A9A9",
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

HOUSE_DEPTH = 8.0
HALF_DEPTH = HOUSE_DEPTH / 2.0
KITCHEN_WIDTH = 4.75 - 0.03
HOUSE_WIDTH = 11.375
CUT_WIDTH = 1.75

wall2_x = BWT + 3.25 - 0.03 + BWT;
wall3_x = wall2_x + KITCHEN_WIDTH + BWT;
stair_height = (
	ground_floor_height - GROUND_FLOOR_THICKNESS
	+ CEILING_THICKNESS + UPPER_FLOOR_THICKNESS)
step_count = 16
STAIR_TREAD_THICKNESS = 0.04
STAIR_STRINGER_THICKNESS = 0.05
STAIR_STRINGER_HEIGHT = 0.30
KK_WIDTH = HOUSE_WIDTH - wall3_x - BWT

GYM_DEPTH = 2
pokoj_dole = ground.floor_layer(
	"Pokoj",
	outline=(
		(BWT, BWT+GYM_DEPTH+BWT),
		(wall2_x-BWT, BWT+GYM_DEPTH+BWT),
		(wall2_x-BWT, HOUSE_DEPTH-BWT),
		(BWT, HOUSE_DEPTH-BWT),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=0.10,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
CHODBA_DEPTH = 2.5
wall_zachod_nahore_y = BWT+1.2+1+0.1
oblouk_at = HOUSE_DEPTH-BWT-1-2.5

# chimney
CHIMNEY_DIST=0.47
CHIMNEY_Y_START = HALF_DEPTH - VAZNICE_DIST - 0.08 - 0.05 - 0.4
CHIMNEY_Y_START = 0.125*math.floor((CHIMNEY_Y_START - 0.04 - 0.17) / 0.125) + 0.04 + 0.17
CHIMNEY_Y_START = CHIMNEY_Y_START + 0.025 - 0.125

CHIMNEY_Y_START = BWT + CHODBA_DEPTH - 0.45 # override

CHIMNEY_Y_MID = CHIMNEY_Y_START + 0.2
CHIMNEY_Y_END = CHIMNEY_Y_START + 0.4

CHIMNEY_X_START = (3.98+4.98)/2 - 0.2

CHIMNEY_X_MID = CHIMNEY_X_START + 0.2
CHIMNEY_X_END = CHIMNEY_X_START + 0.4

print("CHIMNEY_Y_START = ", CHIMNEY_Y_START)
print("CHIMNEY_Y_MID = ", CHIMNEY_Y_MID)
print("CHIMNEY_Y_END = ", CHIMNEY_Y_END)

BATHROOM_DEPTH = 2.6
kuchyn = ground.floor_layer(
	"Kuchyn",
	outline=(
		(wall2_x, BWT+CHODBA_DEPTH+0.15),
		(wall3_x-BWT, BWT+CHODBA_DEPTH+0.15),
		(wall3_x-BWT, oblouk_at),
		(wall3_x, oblouk_at),
		(wall3_x, BWT+BATHROOM_DEPTH+0.15),
		(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH+0.15),
		(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
		(wall3_x, HOUSE_DEPTH-BWT),
		(wall3_x, oblouk_at+2.5),
		(wall3_x-BWT, oblouk_at+2.5),
		(wall3_x-BWT, HOUSE_DEPTH-BWT),
		(wall2_x, HOUSE_DEPTH-BWT),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=0.10,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
chodba = ground.floor_layer(
	"Chodba",
	outline=(
		(BWT+CUT_WIDTH, BWT),
		(wall3_x-BWT, BWT),
		(wall3_x-BWT, BWT+CHODBA_DEPTH),
		(wall2_x, BWT+CHODBA_DEPTH),
		(wall2_x, BWT+GYM_DEPTH),
		(BWT+CUT_WIDTH, BWT+GYM_DEPTH),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=0.10,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
koupelna = ground.floor_layer(
	"Koupelna",
	outline=(
		(wall3_x, BWT),
		(HOUSE_WIDTH-BWT, BWT),
		(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH),
		(wall3_x, BWT+BATHROOM_DEPTH),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=0.10,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)

ceiling_pokoj_dole = ground.ceiling_layer(
	"Ceiling - Pokoj",
	outline=pokoj_dole.outline,
	thickness=CEILING_FINISH_THICKNESS,
	start_height=ground_floor_height-CEILING_FINISH_THICKNESS,
	material=CEILING_FINISH_MATERIAL,
)
ceiling_kuchyn = ground.ceiling_layer(
	"Ceiling - Kuchyn",
	outline=kuchyn.outline,
	thickness=CEILING_FINISH_THICKNESS,
	start_height=ground_floor_height-CEILING_FINISH_THICKNESS,
	material=CEILING_FINISH_MATERIAL,
)
ceiling_koupelna = ground.ceiling_layer(
	"Ceiling - Koupelna",
	outline=koupelna.outline,
	thickness=CEILING_FINISH_THICKNESS,
	start_height=ground_floor_height-CEILING_FINISH_THICKNESS,
	material=CEILING_FINISH_MATERIAL,
)

# Load-bearing walls
wall_front_g = ground.wall((CUT_WIDTH, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_4_g = ground.wall((HOUSE_WIDTH, 0), (HOUSE_WIDTH, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_back_g = ground.wall((HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1a_g = ground.wall((0, HOUSE_DEPTH), (0, BWT+GYM_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1b_g = ground.wall((CUT_WIDTH, GYM_DEPTH+2*BWT), (CUT_WIDTH, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_2 = ground.wall((wall2_x, BWT+GYM_DEPTH), (wall2_x, HOUSE_DEPTH-0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)

ground.connect_wall(wall_1a_g, wall_back_g)

#ground.connect_wall(wall_2, wall_front_g, is_atpath=True)
ground.connect_wall(wall_2, wall_back_g, is_atpath=True)

ground.connect_wall(wall_3, wall_front_g, is_atpath=True)
ground.connect_wall(wall_3, wall_back_g, is_atpath=True)

ground.connect_wall(wall_4_g, wall_front_g)
ground.connect_wall(wall_4_g, wall_back_g)

# Front door/window

BOTTOM_STAIR_TREADS = 9
GROUND_DOOR_HEIGHT = 2.32
GROUND_WINDOW_HEIGHT = 2.5
GROUND_WINDOW_SILL_HEIGHT = 1.125
front_door = wall_1b_g.add_door(
	at=2*BWT+GYM_DEPTH-0.375-1.125,
	opening_width=1.125, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=GROUND_FLOOR_THICKNESS,
	operation="SINGLE_SWING_RIGHT"
)

# Front windows (koupelna)
window_bathroom = wall_front_g.add_window(
	at=wall3_x-CUT_WIDTH+KK_WIDTH/2-0.25, width=0.5,
	sill_height=GROUND_WINDOW_HEIGHT-0.5,
	height=GROUND_WINDOW_HEIGHT)

# Back windows
print("KK_WIDTH=", KK_WIDTH)
window_obyvak = wall_back_g.add_window(
	at=2*BWT+KK_WIDTH+1, width=2.5,
	sill_height=GROUND_WINDOW_SILL_HEIGHT,
	height=GROUND_WINDOW_HEIGHT)
window_pokoj_dole = wall_back_g.add_window(
	at=HOUSE_WIDTH-wall2_x+BWT+0.875,
	width=1.5, sill_height=GROUND_WINDOW_SILL_HEIGHT, height=GROUND_WINDOW_HEIGHT)
window_kk = wall_back_g.add_door(
	at=BWT+KK_WIDTH-0.125-1,
	width=0.8, sill_height=GROUND_WINDOW_HEIGHT-2.0,
	height=GROUND_WINDOW_HEIGHT, # align height with windows even though this is door
	opening_width=1, clear_height=2,
	operation="SINGLE_SWING_RIGHT",)

window_pokoj_dole_2 = wall_1a_g.add_window(
	at=1,#HOUSE_DEPTH/2-0.75-BWT,
	width=1,
	sill_height=GROUND_WINDOW_HEIGHT-0.75,
	height=GROUND_WINDOW_HEIGHT)

# Posilovna, Gym
wall_gym_g = ground.wall(
	(BWT, BWT+GYM_DEPTH), (wall2_x-BWT, BWT+GYM_DEPTH),
	wall_type=load_bearing_wall, height=ground_floor_height)

ring_beams = ground.add_ring_beams_from(
	ground,
	source_wall_type=load_bearing_wall,
	height=CEILING_THICKNESS,
	start_height=ground_floor_height,
	concrete_material="Concrete topping",
	reinforcement_material="Ring beam reinforcement",
	bar_diameter=RING_BEAM_BAR_DIAMETER,
	concrete_cover=RING_BEAM_CONCRETE_COVER,
)

foundation_base_plate = foundation.floor_layer(
	"Foundation base plate",
	outline=(
		(CUT_WIDTH, 0),
		(HOUSE_WIDTH, 0),
		(HOUSE_WIDTH, HOUSE_DEPTH),
		(0, HOUSE_DEPTH),
		(0, BWT + GYM_DEPTH),
		(CUT_WIDTH, BWT + GYM_DEPTH),
	),
	thickness=FOUNDATION_BASE_PLATE_THICKNESS,
	start_height=-FOUNDATION_BASE_PLATE_THICKNESS,
	kind="BASESLAB",
	load_bearing=True,
	buildup_material="Base plate concrete",
	color="#B8B8B8",
)
foundation_walls = foundation.add_walls_from(
	ground,
	source_wall_type=load_bearing_wall,
	wall_type=foundation_wall,
	height=FOUNDATION_WALL_HEIGHT,
	start_height=(
		-FOUNDATION_BASE_PLATE_THICKNESS - FOUNDATION_WALL_HEIGHT
	),
)
foundation_footers = foundation.add_strip_footings_from(
	ground,
	source_wall_type=load_bearing_wall,
	width=FOUNDATION_FOOTER_WIDTH,
	height=FOUNDATION_FOOTER_HEIGHT,
	start_height=(
		-FOUNDATION_BASE_PLATE_THICKNESS
		- FOUNDATION_WALL_HEIGHT
		- FOUNDATION_FOOTER_HEIGHT
	),
	material="Concrete",
	color="#969696",
)

# Bathroom, Koupelna
wall_bathroom = ground.wall(
	(wall3_x, BWT+BATHROOM_DEPTH), (HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
heat_pump = ground.furniture(
    "Tepelné\nČerpadlo",
    kind="USERDEFINED",
    size=(1.2, 0.5, 1.5),
    color="#ffffff",
    center=(HOUSE_WIDTH+POLYSTYRENE_INSULATION_THICKNESS+0.1+0.25, 0+0.6),
	rotation=-90,
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
    center=(HOUSE_WIDTH-(BWT+0.8)-0.4, BWT+0.4),
)
ground.asset(
	"Gauc", asset="3_seater_sofa",
	center=(wall2_x+0.1+0.55, HOUSE_DEPTH-BWT-0.1-1.25),
	start_height=GROUND_FLOOR_THICKNESS,
	size=(2.5, 1.1),
	rotation=90,
)
ground.asset(
	"Gauc", asset="1_seater_sofa",
	center=(wall2_x+0.1+1.1+0.1+0.55, HOUSE_DEPTH-BWT-0.1-0.55),
	start_height=GROUND_FLOOR_THICKNESS,
#	rotation=90,
	size=(1.1, 1.1)
)
ground.asset(
    "Umyv",
    asset="basin_large",
	center=(HOUSE_WIDTH-BWT-0.35, BWT+0.8+0.4),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=-90,
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
    center=(HOUSE_WIDTH-(BWT+KK_WIDTH)+0.4, BWT+0.5),
    rotation=180,
)

# Kitchen, Kuchyn
#wall_kitchen_0 = ground.wall(
#	(wall2_x, BWT+GYM_DEPTH+0.5+1.05),
#	(wall2_x+1.15, BWT+GYM_DEPTH+0.5+1.05),
#	wall_type=dry_wall, height=ground_floor_height)
wall_kitchen_1 = ground.wall(
	(wall2_x, BWT+CHODBA_DEPTH),
	(wall2_x+KITCHEN_WIDTH, BWT+CHODBA_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
wall_kitchen_2 = ground.wall(
	(wall2_x+1, BWT+CHODBA_DEPTH+0.75),
	(wall2_x+1, BWT+CHODBA_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
#wall_kitchen_3 = ground.wall(
#	(wall2_x+1.15+0.15+0.9, BWT+CHODBA_DEPTH+0.5),
#	(wall2_x+1.15+0.15+0.9, BWT+CHODBA_DEPTH),
#	wall_type=partition_wall, height=ground_floor_height)
wall_kitchen_1.add_door(
	at=1.25,
	opening_width=1.0, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=False
)

# Pokoj Risanek
wall_gym_g.add_door(
	at=wall2_x-2*BWT-0.25-1,
	opening_width=1.0, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_RIGHT",
#	reverse_swing=True,
)

# Oblouk
wall_3.add_opening(
	at=oblouk_at,
	width=2.5,
    height=ground_floor_height-0.5,
    sill_height=GROUND_FLOOR_THICKNESS,
	name="Oblouk"
)

# Bathroom
wall_3.add_door(
    at=BWT+math.floor((CHODBA_DEPTH-1)/0.125)*0.125,
    opening_width=1.0, width=0.9,
    height=GROUND_DOOR_HEIGHT,
	sill_height=GROUND_FLOOR_THICKNESS,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True,
)

# stairs
GALERY_START = BWT+CHODBA_DEPTH
stairs_width = 1
straight_stair_step_size = 0.27
stair_step_height = stair_height / step_count
remaining_stair_count = step_count - 2 - BOTTOM_STAIR_TREADS
straight_stair_start_y = BWT + 1.02
landing_left_x = wall3_x - BWT - 1
bottom_stair_start_x = landing_left_x - 0.27*BOTTOM_STAIR_TREADS
bottom_stair_center_y = BWT + stairs_width / 2

main_stairs = ground.stair(
	(bottom_stair_start_x, bottom_stair_center_y),
	(landing_left_x, bottom_stair_center_y),
	width=stairs_width,
	start_height=GROUND_FLOOR_THICKNESS,
	height=stair_step_height * (BOTTOM_STAIR_TREADS + 1),
	risers=BOTTOM_STAIR_TREADS + 1,
	construction="timber",
	tread_thickness=STAIR_TREAD_THICKNESS,
	stringer_thickness=STAIR_STRINGER_THICKNESS,
	stringer_height=STAIR_STRINGER_HEIGHT,
	name="Main stair",
	color="#C8B090",
)

middle_stair_landing = ground.stair_landing(
	(landing_left_x, BWT),
	(landing_left_x + 1, straight_stair_start_y),
	height=main_stairs.end_height,
	thickness=STAIR_TREAD_THICKNESS,
	name="Middle stair landing",
	color="#C8B090",
)

gallery_stairs = ground.stair(
	(
		landing_left_x + 0.5,
		straight_stair_start_y,
	),
	(
		landing_left_x + 0.5,
		straight_stair_start_y + 0.27 * remaining_stair_count,
	),
	width=1,
	start_height=main_stairs.end_height,
	slab_height=main_stairs.end_height - STAIR_TREAD_THICKNESS,
	height=stair_step_height * (remaining_stair_count + 1),
	risers=remaining_stair_count + 1,
	construction="timber",
	tread_thickness=STAIR_TREAD_THICKNESS,
	stringer_thickness=STAIR_STRINGER_THICKNESS,
	stringer_height=STAIR_STRINGER_HEIGHT,
	name="Gallery stair",
	color="#C8B090",
)

# Chimney
chimney = ground.chimney(
    center=(CHIMNEY_X_MID, CHIMNEY_Y_MID),
    size=0.4,
    height=8.5,
    flue_diameter=0.2,
    start_height=0,
    name="Main chimney",
    material="Chimney",
    color="#B8A99A",
)

GALERY_END = GALERY_START + 1.05

ground.furniture(
    "Kamna",
    kind="USERDEFINED",
    size=(0.6, 0.5, 1.5),
    color="#ffff2B",
    center=(wall2_x + 0.5, BWT+CHODBA_DEPTH+0.15+0.2+0.25),
	start_height=GROUND_FLOOR_THICKNESS,
#    rotation=-45,
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
    center=(wall3_x-BWT-1.1, HOUSE_DEPTH - BWT - 1.2),
	start_height=GROUND_FLOOR_THICKNESS,
	#size=(1.3, 0.8*3),
)

# MIAKO
ceiling1 = upper.miako_slab(
    "Ceiling 1",
    start=(0.1, BWT+GYM_DEPTH+BWT-0.04),
    end=(wall2_x-0.15, BWT+GYM_DEPTH+BWT-0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, 1),
	expected_width=HOUSE_DEPTH-3*BWT-GYM_DEPTH+0.08,
    structure=[
		"beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow"
		],
)
ceiling2 = upper.miako_slab(
    "Ceiling 2",
    start=(wall2_x-0.125, GALERY_START),
    end=(wall3_x-0.125, GALERY_START),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=0.15,
    direction=(0, 1),
	expected_width=HOUSE_DEPTH-2*BWT-CHODBA_DEPTH,
    structure=[
		"beam", "narrow",
		"beam", "narrow",
		"beam", "beam", "wide",
		"beam", "wide",
		"beam", "wide",
		"beam", "wide",
		"beam", "wide",
		"beam", "wide",
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
			(BWT, BWT+GYM_DEPTH+BWT),
			(wall2_x-BWT, BWT+GYM_DEPTH+BWT),
			(wall2_x-BWT, HOUSE_DEPTH-BWT),
			(BWT, HOUSE_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=0.03,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
upper_pokoj_2 = upper.floor_layer(
		f"Upper Pokoj 2",
		outline=(
			(wall2_x, GALERY_END+0.1),
			(wall3_x-BWT, GALERY_END+0.1),
			(wall3_x-BWT, HOUSE_DEPTH-BWT),
			(wall2_x, HOUSE_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=0.03,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
galerie = upper.floor_layer(
		f"Galerie",
		outline=(
			(wall2_x, GALERY_START),
			(wall3_x-BWT, GALERY_START),
			(wall3_x-BWT, GALERY_END),
			(wall2_x, GALERY_END),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=0.03,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
upper_sklad = upper.floor_layer(
		f"Sklad",
		outline=(
			(wall3_x, wall_zachod_nahore_y),
			(HOUSE_WIDTH-BWT, wall_zachod_nahore_y),
			(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
			(wall3_x, HOUSE_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=0.03,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
zachod_nahore = upper.floor_layer(
		f"Zachod",
		outline=(
			(wall3_x, wall_zachod_nahore_y-0.1),
			(HOUSE_WIDTH-BWT, wall_zachod_nahore_y-0.1),
			(HOUSE_WIDTH-BWT, BWT),
			(wall3_x, BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=0.03,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)

STREET_ROOF_JOINT_Y = HALF_DEPTH-VAZNICE_DIST-0.08
GARDEN_ROOF_JOINT_Y = HALF_DEPTH+VAZNICE_DIST+0.08
ROOF_JOINT_Z = UPPER_FLOOR_START + UNDER_HOLE + HOLE_HEIGHT + ABOVE_HOLE + VAZNICE_HEIGHT
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
WALL_PLATE_SIZE = (0.16, 0.12)
STREET_WALL_PLATE_Y = 0.125
GARDEN_WALL_PLATE_Y = HOUSE_DEPTH - 0.125


def wall_plate_center_z(roof_plane_points, center_y, *, side):
	"""Return a wall plate centre Z with its outer top edge on the roof plane."""
	if side not in {"street", "garden"}:
		raise ValueError("wall plate side must be 'street' or 'garden'")
	outside_direction = -1 if side == "street" else 1
	roof_contact_y = (
		center_y + outside_direction * WALL_PLATE_SIZE[0] / 2
	)
	return (
		plane_height_at(*roof_plane_points, x=0, y=roof_contact_y)
		- WALL_PLATE_SIZE[1] / 2
	)


STREET_WALL_PLATE_Z = wall_plate_center_z(
	STREET_ROOF_PLANE_POINTS,
	STREET_WALL_PLATE_Y,
	side="street",
)
GARDEN_WALL_PLATE_Z = wall_plate_center_z(
	GARDEN_ROOF_PLANE_POINTS,
	GARDEN_WALL_PLATE_Y,
	side="garden",
)
DORMER_WALL_PLATE_Z = wall_plate_center_z(
	DORMER_ROOF_PLANE_POINTS,
	GARDEN_WALL_PLATE_Y,
	side="garden",
)
CUT_STREET_WALL_PLATE_Y = BWT + GYM_DEPTH + STREET_WALL_PLATE_Y
CUT_STREET_WALL_PLATE_Z = wall_plate_center_z(
	STREET_ROOF_PLANE_POINTS,
	CUT_STREET_WALL_PLATE_Y,
	side="street",
)
CUT_STREET_WALL_HEIGHT = (
	CUT_STREET_WALL_PLATE_Z
	- WALL_PLATE_SIZE[1] / 2
	- UPPER_FLOOR_START
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
		(0, HALF_DEPTH-VAZNICE_DIST-0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
		(0, HALF_DEPTH+VAZNICE_DIST+0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
		(5, HALF_DEPTH+VAZNICE_DIST+0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
	),
#	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
]
wall_cuts_2_3 = [
	offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	offset_plane(*DORMER_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	(
		(0, HALF_DEPTH-VAZNICE_DIST-0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
		(0, HALF_DEPTH+VAZNICE_DIST+0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
		(5, HALF_DEPTH+VAZNICE_DIST+0.08, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE),
	),
]

wall_dormer = upper.wall(
	(wall3_x, HOUSE_DEPTH), (wall2_x-BWT, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=DORMER_WALL_HEIGHT-NADEZDIVKA, start_height=NADEZDIVKA)
wall_front_u = upper.wall((CUT_WIDTH, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_back_u = upper.wall(
	(HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_1a_u = upper.wall(
	(0, HOUSE_DEPTH-BWT), (0, BWT+GYM_DEPTH+BWT),
	wall_type=load_bearing_wall,
	height=4, cuts=wall_cuts_1_4, )
wall_1b_u = upper.wall(
	(CUT_WIDTH, GYM_DEPTH+BWT), (CUT_WIDTH, BWT),
	wall_type=load_bearing_wall,
	height=4, cuts=wall_cuts_1_4, )
wall_gym_u = upper.wall(
	(0, BWT+GYM_DEPTH), (wall2_x-BWT, BWT+GYM_DEPTH),
	wall_type=load_bearing_wall,
	height=CUT_STREET_WALL_HEIGHT,
	cuts=wall_cuts_1_4,
)
wall_2 = upper.wall(
	(wall2_x, BWT+GYM_DEPTH), (wall2_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_2.add_opening(
	at=3.625-BWT-GYM_DEPTH, width=0.75, height=UNDER_HOLE+HOLE_HEIGHT, sill_height=UNDER_HOLE)

wall_3 = upper.wall(
	(wall3_x, BWT), (wall3_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=4)
wall_3.add_opening(
	at=3.625-BWT, width=0.75, height=UNDER_HOLE+HOLE_HEIGHT, sill_height=UNDER_HOLE)

wall_3.add_opening(
    at=GALERY_START-BWT,
    width=1,
    height=2.25,
)

wall_4_u = upper.wall(
	(HOUSE_WIDTH, 0.002), (HOUSE_WIDTH, HOUSE_DEPTH-0.002),
	wall_type=load_bearing_wall,
	height=4,
	cuts=wall_cuts_1_4,
)
wall_4_u.add_opening(at=0, width=BWT, height=1.5, sill_height=NADEZDIVKA)
wall_4_u.add_opening(at=7.75, width=BWT, height=1.5, sill_height=NADEZDIVKA)

wall_pokoj2 = upper.wall(
	start=(wall2_x, GALERY_END),
	end=(wall3_x-BWT, GALERY_END),
	wall_type=dry_wall, height=2.85)
UPPER_DOOR_HEIGHT = 2.25
wall_pokoj2.add_door(
	at=0.125,
	opening_width=1, width=0.9,
	height=UPPER_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
wall_zachod_nahore = upper.wall(
	start=(HOUSE_WIDTH-BWT, wall_zachod_nahore_y),
	end=(wall3_x, wall_zachod_nahore_y),
	wall_type=dry_wall, height=2.85)
wall_zachod_nahore.add_door(
	at=0.8,
	opening_width=0.8, width=0.7,
	height=UPPER_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=True)
upper.asset(
    "WC",
    asset="toilet_without_cistern",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-(BWT+KK_WIDTH)+0.4, wall_zachod_nahore_y-0.1-0.5),
    rotation=90,
)
upper.asset(
    "Umyv",
    asset="basin_large",
    center=(HOUSE_WIDTH-BWT-0.4, wall_zachod_nahore_y+0.35),
	start_height=GROUND_FLOOR_THICKNESS,
	rotation=180,
)

#upper.connect_wall(wall_1, wall_back_u)
#
#upper.connect_wall(wall_2, wall_front_u, is_atpath=True)
#upper.connect_wall(wall_2, wall_back_u, is_atpath=True)
#upper.connect_wall(wall_2, wall_dormer)
#
#upper.connect_wall(wall_3, wall_front_u, is_atpath=True)
#upper.connect_wall(wall_3, wall_back_u, is_atpath=True)
#upper.connect_wall(wall_3, wall_dormer)
#
#upper.connect_wall(wall_4_u, wall_front_u)
#upper.connect_wall(wall_4_u, wall_back_u)


beam1 = upper.beam(
    "Beam",
    start=(-0.2, HALF_DEPTH-VAZNICE_DIST, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE+VAZNICE_HEIGHT/2),
    end=(HOUSE_WIDTH+0.2, HALF_DEPTH-VAZNICE_DIST, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE+VAZNICE_HEIGHT/2),
    size=(0.16, VAZNICE_HEIGHT),
    material="Wood",
    kind="BEAM",
)
beam2 = upper.beam(
    "Beam",
    start=(-0.2, HALF_DEPTH+VAZNICE_DIST, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE+VAZNICE_HEIGHT/2),
    end=(HOUSE_WIDTH+0.2, HALF_DEPTH+VAZNICE_DIST, UPPER_FLOOR_START+UNDER_HOLE+HOLE_HEIGHT+ABOVE_HOLE+VAZNICE_HEIGHT/2),
    size=(0.16, VAZNICE_HEIGHT),
    material="Wood",
    kind="BEAM",
)
beam3 = upper.beam(
    "Beam",
	start=(CUT_WIDTH-0.2, STREET_WALL_PLATE_Y, STREET_WALL_PLATE_Z),
	end=(HOUSE_WIDTH+0.2, STREET_WALL_PLATE_Y, STREET_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="BEAM",
)
beam_cut_street = upper.beam(
	"Cut street wall plate",
	start=(-0.2, CUT_STREET_WALL_PLATE_Y, CUT_STREET_WALL_PLATE_Z),
	end=(wall2_x-BWT, CUT_STREET_WALL_PLATE_Y, CUT_STREET_WALL_PLATE_Z),
	size=WALL_PLATE_SIZE,
	material="Wood",
	kind="BEAM",
)
beam4_a = upper.beam(
    "Beam",
	start=(-0.2, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
	end=(wall2_x-BWT, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="BEAM",
)
beam4_b = upper.beam(
    "Beam",
	start=(wall3_x, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
	end=(HOUSE_WIDTH+0.2, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="BEAM",
)
beam_dormer = upper.beam(
    "Beam",
	start=(wall3_x+0.3, GARDEN_WALL_PLATE_Y, DORMER_WALL_PLATE_Z),
	end=(wall2_x-BWT-0.3, GARDEN_WALL_PLATE_Y, DORMER_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="BEAM",
)

# Chodba nahore
upper.furniture(
    "Rekuperace",
    kind="USERDEFINED",
    size=(1, 0.5, 2.5),
    color="#ffff00",
    center=(HOUSE_WIDTH-BWT-0.3, wall_zachod_nahore_y-0.7),
	rotation=90,
	start_height=UPPER_FLOOR_THICKNESS,
)
upper.furniture(
    "Hydrobox",
    kind="USERDEFINED",
    size=(0.8, 0.4, 0.9),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(HOUSE_WIDTH-BWT-0.5, BWT+0.25),
)

# Okna obyvak
window_dormer_1 = wall_dormer.add_window(
	at=BWT+0.5,width=1.375, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
window_dormer_2 = wall_dormer.add_window(
	at=BWT+KITCHEN_WIDTH-0.5-1.375,
	width=1.375, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
# Dvere pokojik 1 nahore
wall_2.add_door(
	at=GALERY_START-GYM_DEPTH-BWT,
	opening_width=1, width=0.9,
	height=UPPER_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
# Okna pokojik 1 nahore
#window_pokoj_nahore_1 = wall_1a_u.add_window(
#	at=HOUSE_DEPTH/2-0.75-BWT,
#	width=1.5,
#	height=2.375,
#	sill_height=2.375-0.875, partition="SINGLE_PANEL",)
# okno do silnice
window_pokoj_nahore_2 = wall_gym_u.add_window(
	at=BWT,width=1.25, sill_height=NADEZDIVKA, height=2.375
)
# Okno k sousedum nahore
window_sklad = wall_4_u.add_window(
	at=HALF_DEPTH-0.5,
	width=1,
	height=2.375,
	sill_height=NADEZDIVKA, partition="SINGLE_PANEL",)

# Roof

roof = upper.roof("Main roof")

ROOF_WINDOW_Y1 = HOUSE_DEPTH - BWT - 0.25
roof_window_opening = roof.add_opening(
	name="Bedroom roof window",
	rectangle=(
		(1.88+0.04, ROOF_WINDOW_Y1),
		(2.88-0.04, ROOF_WINDOW_Y1 - 1.2),
	),
)

roof_inner_cuts = [
	((0, BWT, 0), (10, BWT, 0), (0, BWT, 10)),
	((0, 7.75, 0), (10, 7.75, 0), (0, 7.75, 10)),
	(
		(BWT, 0, 0),
		(BWT, 10, 0),
		(BWT, 0, 10),
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
CUT_STREET_EAVE_Y = BWT + GYM_DEPTH - 0.5
cut_street_roof = roof.plane(
	"Cut street slope",
	points=STREET_ROOF_PLANE_POINTS,
	cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		(
			(0, CUT_STREET_EAVE_Y, 0),
			(10, CUT_STREET_EAVE_Y, 0),
			(0, CUT_STREET_EAVE_Y, 10),
		),
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
dormer_roof_angle = roof_angle_degrees(dormer_roof)
if not isclose(street_roof_angle, garden_roof_angle, abs_tol=1e-9):
	raise ValueError("street and garden roof angles must match")
print(
	f"Main roof angle: {street_roof_angle:.2f}° "
	f"({100 * math.tan(math.radians(street_roof_angle)):.2f}%)"
)
print(
	f"Dormer roof angle: {dormer_roof_angle:.2f}° "
	f"({100 * math.tan(math.radians(dormer_roof_angle)):.2f}%)"
)

# Bonsai creates Outliner collections from spatial containers, but flattens
# ordinary IFC aggregation.  These intentionally artificial storeys provide
# one portable visibility collection for each roof layer in shared IFC files.
roof_layer_storeys = {}
if THERMAL_INSULATION_UNDER_RAFTERS > 0:
	roof_layer_storeys["Thermal insulation under rafters"] = house.storey(
		"Roof - -1: Thermal insulation under rafters",
		elevation=upper.elevation,
	)
roof_layer_storeys.update({
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
})
for layer_name, layer_storey in roof_layer_storeys.items():
	layer_storey.element.ObjectType = "ROOF_LAYER"
	layer_storey.element.Description = f"Visibility container for {layer_name}"

# Sloping layers remain a conventional contiguous build-up.  The horizontal
# ceiling has an installation void, so describe that exceptional part with
# readable storey-relative bottom/top heights instead of adding more roof
# planes or special geometry types.
SLOPED_INNER_LAYER_LAYOUT = {
	"Thermal insulation under rafters": (
		THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM,
		THERMAL_INSULATION_UNDER_RAFTERS,
	),
	"Vapour barrier": (VAPOUR_BARRIER_BOTTOM, VAPOUR_BARRIER_THICKNESS),
	"Gypsum plasterboard": (
		GYPSUM_PLASTERBOARD_BOTTOM,
		GYPSUM_PLASTERBOARD_THICKNESS,
	),
}
FLAT_CEILING_LAYER_HEIGHTS = {
	# Values are (bottom, top), measured from the upper-storey floor.
	"Thermal insulation under rafters": (
		COLLAR_TIE_BOTTOM_HEIGHT - THERMAL_INSULATION_UNDER_RAFTERS,
		COLLAR_TIE_BOTTOM_HEIGHT,
	),
	"Vapour barrier": (
		COLLAR_TIE_BOTTOM_HEIGHT
		- THERMAL_INSULATION_UNDER_RAFTERS
		- VAPOUR_BARRIER_THICKNESS,
		COLLAR_TIE_BOTTOM_HEIGHT - THERMAL_INSULATION_UNDER_RAFTERS,
	),
	# The first 50 mm below the vapour barrier is an empty installation
	# space.  The horizontal plasterboard retains its lower ceiling height.
	"Gypsum plasterboard": (
		UPPER_FLOOR_THICKNESS + 2.63,
		UPPER_FLOOR_THICKNESS + 2.63 +  GYPSUM_PLASTERBOARD_THICKNESS,
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

# Each number is the absolute X coordinate of a main rafter centre.  A tuple
# also creates a touching dormer rafter on the requested side.  "before" and
# "after" shorten the main rafter on the garden side; "+before" and "+after"
# leave it full-length.
rafters = [
	-0.12,
	0.88,
	1.88,
	2.88,
	(3.34, "+before"),
	(3.98, "after"),
	(4.98, "after"),
	(5.98, "after"),
	(6.98, "after"),
	(7.98, "after"),
	(8.78, "+after"),
	9.78,
	10.78,
	11.5,
	]
rafter_layout = []
for rafter in rafters:
	if not isinstance(rafter, tuple):
		rafter_layout.append((rafter, "main", False))
		continue

	rafter_x, dormer_side = rafter
	if dormer_side not in {"before", "after", "+before", "+after"}:
		raise ValueError(
			"paired rafter side must be 'before', 'after', "
			"'+before', or '+after'"
		)
	shorten_garden_side = not dormer_side.startswith("+")
	dormer_side = dormer_side.removeprefix("+")
	dormer_offset = (
		-RAFTER_THICKNESS if dormer_side == "before" else RAFTER_THICKNESS
	)
	rafter_layout.extend(
		(
			(rafter_x, "main", shorten_garden_side),
			(rafter_x + dormer_offset, "dormer", False),
		)
	)

rafter_layout.sort(key=lambda entry: entry[0])
main_rafter_positions = [
	x for x, kind, _ in rafter_layout if kind == "main"
]
dormer_rafter_positions = [
	x for x, kind, _ in rafter_layout if kind == "dormer"
]
dormer_x_min = min(dormer_rafter_positions)
dormer_x_max = max(dormer_rafter_positions)

def print_rafter_center_distances(label, positions):
	print(f"{label} rafter center distances:")
	for previous_x, current_x in zip(positions, positions[1:]):
		print(
			f"  {current_x - previous_x:.3f} m "
			f"({previous_x:.3f} -> {current_x:.3f})"
		)

print_rafter_center_distances("Main", main_rafter_positions)
print_rafter_center_distances("Dormer", dormer_rafter_positions)


ROOF_X_OVERHANG = 0.25
roof_under_rafter_x_ranges = (
	(0, CUT_WIDTH),
	(CUT_WIDTH, wall2_x-BWT),
	(wall2_x-BWT, wall3_x),
	(wall3_x, HOUSE_WIDTH),
)
roof_over_rafter_x_ranges = (
	(-ROOF_X_OVERHANG, CUT_WIDTH-ROOF_X_OVERHANG),
	(CUT_WIDTH-ROOF_X_OVERHANG, wall2_x-BWT),
	(wall2_x-BWT-ROOF_X_OVERHANG, wall3_x+ROOF_X_OVERHANG),
	(wall3_x, HOUSE_WIDTH + ROOF_X_OVERHANG),
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
	outer_x_range=None,
):
	"""Add selected inner and outer parts of the roof build-up."""
	if outer_x_range is None:
		outer_x_range = (x_min, x_max)
	outer_x_min, outer_x_max = outer_x_range
	outer_outline = (
		(outer_x_min, y_min),
		(outer_x_max, y_min),
		(outer_x_max, y_max),
		(outer_x_min, y_max),
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
		insulation_bottom, insulation_thickness = inner_layout[
			"Thermal insulation under rafters"
		]
		if insulation_thickness > 0:
			insulation = plane.layer(
				f"{name} thermal insulation under rafters",
				outline=inner_outline("Thermal insulation under rafters"),
				z_offset=insulation_bottom,
				thickness=insulation_thickness,
				material="Thermal insulation",
				color="#E8D36D",
				extra_cuts=inner_cuts,
			)
			roof_layer_storeys["Thermal insulation under rafters"].add(
				insulation
			)
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
cut_street_inner_boundaries = independent_inner_layer_boundaries(
	cut_street_roof
)
garden_inner_boundaries = independent_inner_layer_boundaries(garden_roof)
dormer_inner_boundaries = independent_inner_layer_boundaries(dormer_roof)
cut_street_outer_y_min, cut_street_outer_y_max = local_y_limits_from_cuts(
	cut_street_roof,
	ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS / 2,
)
# Keep the source solid's centroid between the shortened slope's two cuts.
# The overshoot leaves the exact ridge and eave positions to those cuts.
cut_street_outer_y_min -= 0.25
cut_street_outer_y_max += 0.25


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


def roof_layer_height_at_y(plane, layer_offset, global_y, datum):
	"""Return a roof-layer face height at global Y, relative to a datum."""
	local_y = (
		global_y
		- plane.origin[1]
		- layer_offset * plane.z_axis[1]
	) / plane.y_axis[1]
	return plane.to_world((0, local_y, layer_offset))[2] - datum


normal_plasterboard_wall_height = roof_layer_height_at_y(
	garden_roof,
	GYPSUM_PLASTERBOARD_BOTTOM,
	7.75,
	upper.elevation,
)
dormer_plasterboard_wall_height = roof_layer_height_at_y(
	dormer_roof,
	GYPSUM_PLASTERBOARD_BOTTOM,
	7.75,
	upper.elevation,
)
print("Plasterboard inner-face height at wall, relative to upper floor:")
print(f"  Normal roof: {normal_plasterboard_wall_height:.3f} m")
print(f"  Dormer roof: {dormer_plasterboard_wall_height:.3f} m")

roof_outer_face_offset = ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS
total_house_height = max(
	roof_layer_height_at_y(
		plane,
		roof_outer_face_offset,
		HALF_DEPTH,
		ground.elevation,
	)
	for plane in (
		street_roof,
		garden_roof,
		dormer_roof,
	)
)
print(
	f"Total house height to top of roof, excluding chimney: "
	f"{total_house_height:.3f} m"
)


def flat_inner_y_limits(left_boundaries, right_boundaries):
	return {
		layer_name: (
			left_boundaries[layer_name][1],
			right_boundaries[layer_name][1],
		)
		for layer_name in SLOPED_INNER_LAYER_LAYOUT
	}


add_continuous_roof_layers(
	cut_street_roof,
	"Street segment 0",
	*roof_under_rafter_x_ranges[0],
	cut_street_outer_y_min,
	cut_street_outer_y_max,
	outer_x_range=roof_over_rafter_x_ranges[0],
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		cut_street_roof,
		cut_street_inner_boundaries,
		BWT + GYM_DEPTH + 0.25,
	),
)
for part_name, (x_min, x_max), outer_x_range in zip(
	(
		"Street segment 1",
		"Street segment 2",
		"Street segment 3",
	),
	roof_under_rafter_x_ranges[1:],
	roof_over_rafter_x_ranges[1:],
):
	add_continuous_roof_layers(
		street_roof, part_name, x_min, x_max, roof_y_min, roof_y_max,
		outer_x_range=outer_x_range,
		inner_cuts=roof_inner_cuts,
		inner_y_limits=sloped_inner_y_limits(
			street_roof, street_inner_boundaries, 0.25
		),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 0", *roof_under_rafter_x_ranges[0],
	roof_y_min, roof_y_max,
	outer_x_range=roof_over_rafter_x_ranges[0],
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 1", *roof_under_rafter_x_ranges[1],
	roof_y_min, roof_y_max,
	outer_x_range=roof_over_rafter_x_ranges[1],
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 2 above dormer",
	*roof_under_rafter_x_ranges[2], roof_y_min, 0,
	outer_x_range=roof_over_rafter_x_ranges[2],
	include_inner=False,
)
add_continuous_roof_layers(
	dormer_roof, "Dormer segment 2", *roof_under_rafter_x_ranges[2], 0,
	roof_y_max-1, # overshoot a little less for the dormer so our cuts work properly
	outer_x_range=roof_over_rafter_x_ranges[2],
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		dormer_roof, dormer_inner_boundaries, 7.75
	),
)
add_continuous_roof_layers(
	garden_roof, "Garden segment 3", *roof_under_rafter_x_ranges[3],
	roof_y_min, roof_y_max,
	outer_x_range=roof_over_rafter_x_ranges[3],
	inner_cuts=roof_inner_cuts,
	inner_y_limits=sloped_inner_y_limits(
		garden_roof, garden_inner_boundaries, 7.75
	),
)
for (
	part_name,
	(x_min, x_max),
	street_side_boundaries,
	garden_side_boundaries,
) in zip(
	(
		"Flat ceiling segment 0",
		"Flat ceiling segment 1",
		"Flat ceiling segment 2",
		"Flat ceiling segment 3",
	),
	roof_under_rafter_x_ranges,
	(
		cut_street_inner_boundaries,
		street_inner_boundaries,
		street_inner_boundaries,
		street_inner_boundaries,
	),
	(
		garden_inner_boundaries,
		garden_inner_boundaries,
		dormer_inner_boundaries,
		garden_inner_boundaries,
	),
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
			street_side_boundaries,
			garden_side_boundaries,
		),
		inner_layout=FLAT_CEILING_INNER_LAYER_LAYOUT,
		include_outer=False,
	)

# A batten whose centre lies completely beyond a cut would retain the wrong
# half-space, so derive the first and last tile-batten rows from the cuts.
tile_batten_centerline_z = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1] / 2
street_y_min, street_y_max = local_y_limits_from_cuts(
	street_roof, tile_batten_centerline_z
)
cut_street_y_min, cut_street_y_max = local_y_limits_from_cuts(
	cut_street_roof, tile_batten_centerline_z
)
cut_street_rafter_y_min, cut_street_rafter_y_max = local_y_limits_from_cuts(
	cut_street_roof, RAFTER_Z_OFFSET + RAFTER_SIZE[1] / 2
)
(
	cut_street_counter_batten_y_min,
	cut_street_counter_batten_y_max,
) = local_y_limits_from_cuts(
	cut_street_roof,
	COUNTER_BATTEN_BOTTOM + COUNTER_BATTEN_SIZE[1] / 2,
)
garden_y_min, garden_y_max = local_y_limits_from_cuts(
	garden_roof, tile_batten_centerline_z
)
dormer_y_min, dormer_y_max = local_y_limits_from_cuts(
	dormer_roof, tile_batten_centerline_z
)
add_tile_battens(
	cut_street_roof,
	"Street segment 0",
	[roof_over_rafter_x_ranges[0]],
	cut_street_y_min,
	cut_street_y_max,
)
add_tile_battens(
	street_roof, "Street segments 1 to 3", roof_over_rafter_x_ranges[1:],
	street_y_min, street_y_max
)
add_tile_battens(
	garden_roof,
	"Garden segments 0, 1 and 3",
	[
		roof_over_rafter_x_ranges[0],
		roof_over_rafter_x_ranges[1],
		roof_over_rafter_x_ranges[3],
	],
	garden_y_min,
	garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden segment 2 above dormer",
	[roof_over_rafter_x_ranges[2]],
	garden_y_min,
	0,
)
add_tile_battens(
	dormer_roof,
	"Dormer segment 2",
	[roof_over_rafter_x_ranges[2]],
	0,
	dormer_y_max,
)

for i, (rafter_x, rafter_kind, shorten_garden_side) in enumerate(rafter_layout):
	is_dormer_rafter = rafter_kind == "dormer"
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
		street_side_plane = (
			cut_street_roof
			if rafter_x < roof_over_rafter_x_ranges[0][1]
			else street_roof
		)
		if street_side_plane is cut_street_roof:
			street_rafter_y_min = cut_street_rafter_y_min - 0.25
			street_rafter_y_max = cut_street_rafter_y_max + 0.25
			street_counter_batten_y_min = (
				cut_street_counter_batten_y_min - 0.25
			)
			street_counter_batten_y_max = (
				cut_street_counter_batten_y_max + 0.25
			)
		else:
			street_rafter_y_min = -2
			street_rafter_y_max = 5
			street_counter_batten_y_min = -2
			street_counter_batten_y_max = 5
		rafter = street_side_plane.beam(
			"Rafter 1",
			start=(rafter_x, street_rafter_y_min),
			end=(rafter_x, street_rafter_y_max),
			z_offset=RAFTER_Z_OFFSET,
			size=RAFTER_SIZE,
			kind="RAFTER",
		)
		roof_layer_storeys["Rafters"].add(rafter)
		counter_batten = street_side_plane.beam(
			f"Street counter-batten {i + 1}",
			start=(rafter_x, street_counter_batten_y_min),
			end=(rafter_x, street_counter_batten_y_max),
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
		rafter_y_min = -2
		rafter_y_max = 0.7 if shorten_garden_side else 5
		counter_batten_y_min = -2
		counter_batten_y_max = 0 if shorten_garden_side else 5
		rafter = garden_roof.beam(
			"Rafter 1",
			start=(rafter_x, rafter_y_min),
			end=(rafter_x, rafter_y_max),
			z_offset=RAFTER_Z_OFFSET,
			size=RAFTER_SIZE,
			kind="RAFTER",
		)
		roof_layer_storeys["Rafters"].add(rafter)
		counter_batten = garden_roof.beam(
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

def common_dims(drawing1):
	# Risankuv pokoj hloubka
	drawing1.add_dimension(start=(BWT, BWT+GYM_DEPTH+BWT), end=(BWT, HOUSE_DEPTH-BWT), offset=1)
	# chodba hloubka
	drawing1.add_dimension(start=(CHIMNEY_X_END+0.1, BWT), end=(CHIMNEY_X_END+0.1, BWT+CHODBA_DEPTH), offset=0)
	# gym hloubka
	drawing1.add_dimension(start=(wall2_x-BWT, BWT), end=(wall2_x-BWT, BWT+GYM_DEPTH))

	# Vnejsi rozmery
	drawing1.add_dimension(start=(-ROCKWOOL_INSULATION_THICKNESS, HOUSE_DEPTH-BWT), end=(HOUSE_WIDTH+POLYSTYRENE_INSULATION_THICKNESS, HOUSE_DEPTH-BWT), offset=2)
	drawing1.add_dimension(start=(0, HOUSE_DEPTH-BWT), end=(HOUSE_WIDTH, HOUSE_DEPTH-BWT), offset=1.5)
	drawing1.add_dimension(start=(BWT, HOUSE_DEPTH-BWT), end=(wall2_x-BWT, HOUSE_DEPTH-BWT), offset=1)
	drawing1.add_dimension(start=(wall2_x, HOUSE_DEPTH-BWT), end=(wall3_x-BWT, HOUSE_DEPTH-BWT), offset=1)
	drawing1.add_dimension(start=(wall3_x, HOUSE_DEPTH-BWT), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT), offset=1)
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, 0), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH), offset=-1.5)
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, -POLYSTYRENE_INSULATION_THICKNESS), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH+ROCKWOOL_INSULATION_THICKNESS), offset=-2)
	# chodba delka
	drawing1.add_dimension(start=(CUT_WIDTH+BWT, BWT), end=(HOUSE_WIDTH-BWT-KK_WIDTH-BWT, BWT), offset=-1)
	# komin
	drawing1.add_dimension(start=(wall2_x, CHIMNEY_Y_MID-0.1), end=(CHIMNEY_X_START, CHIMNEY_Y_MID-0.1))

def common_wall_insulation(
	drawing1, wall_front, wall_1a, wall_1b, wall_gym, wall_back, wall_4
):
	drawing1.add_wall_insulation(
		wall_front,
		thickness=POLYSTYRENE_INSULATION_THICKNESS,
		material="polystyrene",
		start_x=CUT_WIDTH-POLYSTYRENE_INSULATION_THICKNESS,
		end_x=HOUSE_WIDTH+POLYSTYRENE_INSULATION_THICKNESS,
	)
	drawing1.add_wall_insulation(
		wall_1a,
		thickness=ROCKWOOL_INSULATION_THICKNESS,
		material="rockwool",
		start_y=GYM_DEPTH+BWT,
		end_y=HOUSE_DEPTH+0.01,
	)
	drawing1.add_wall_insulation(
		wall_1b,
		thickness=POLYSTYRENE_INSULATION_THICKNESS,
		material="polystyrene",
		start_y=-POLYSTYRENE_INSULATION_THICKNESS,
		end_y=BWT+GYM_DEPTH-ROCKWOOL_INSULATION_THICKNESS,
	)
	drawing1.add_wall_insulation(
		wall_gym,
		thickness=ROCKWOOL_INSULATION_THICKNESS,
		material="rockwool",
		start_x=-ROCKWOOL_INSULATION_THICKNESS,
		end_x=CUT_WIDTH,
	)
	drawing1.add_wall_insulation(
		wall_back,
		thickness=ROCKWOOL_INSULATION_THICKNESS,
		material="rockwool",
		start_x=-ROCKWOOL_INSULATION_THICKNESS,
		end_x=HOUSE_WIDTH,
	)
	drawing1.add_wall_insulation(
		wall_4,
		thickness=POLYSTYRENE_INSULATION_THICKNESS,
		material="polystyrene",
		start_extension=POLYSTYRENE_INSULATION_THICKNESS,
		end_extension=ROCKWOOL_INSULATION_THICKNESS,
	)

if "found" in sys.argv:
	drawing1 = house.add_drawing(
		"Foundation",
		x=5,
		y=4,
		z=-1.3,
		radius=8,
		storeys=[foundation],
		right_panel_width=40,
	)

	drawing1.render("found.svg", png=True, png_dpi=600)

# Drawing 1 - ground floor
if "ground" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 1",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=GROUND_FLOOR_THICKNESS+2.05,
		radius=8.5,
		storeys=[ground],
		right_panel_width=40,
	)
	drawing1.add_material_legend([
		("brick", "Nosná zeď - VPC Cihla 240 mm"),
		("diagonal1", "Příčka - VPC Cihla 115 mm"),
		("drywall-diagonal1", "Příčka - Sádrokarton 100 mm"),
		(
			"thermal-impact-insulation",
			f"Fasádní izolace - Polystyren 160 mm",
		),
		(
			"rockwool-wave",
			f"Fasádní izolace - Minerální vata 200 mm",
		),
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	common_dims(drawing1)

	# KK hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH+0.15), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT), offset=-1)
	# kuchyn hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-4, BWT+CHODBA_DEPTH+0.15), end=(HOUSE_WIDTH-4, HOUSE_DEPTH-BWT), offset=0)
	# koupelna hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, BWT), end=(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH), offset=-1)

	# kamna
	drawing1.add_dimension(start=(wall2_x, CHODBA_DEPTH+0.5), end=(wall2_x+1, CHODBA_DEPTH+0.5), offset=1)

	drawing1.add_entrance_arrow(
		(CUT_WIDTH - 0.6, BWT + 0.125 + 0.55),
#		rotation=90,  # points left
		size=0.6,      # metres
	)

	drawing1.add_room_annotation(
		(wall3_x - 2.5, HOUSE_DEPTH - 2.5),
		identifier="0.01",
		description="Obývak s KK",
		area=kuchyn.area,
		window_area=window_area(window_obyvak, window_kk),
	)
	drawing1.add_room_annotation(
		(1.5, 6),
		identifier="0.02",
		description="Pokoj",
		area=pokoj_dole.area,
		window_area=window_area(window_pokoj_dole, window_pokoj_dole_2),
	)
	drawing1.add_room_annotation(
		(HOUSE_WIDTH-1.4, BWT+1.25),
		identifier="0.03",
		description="Koupelna",
		area=koupelna.area,
		window_area=window_area(window_bathroom),
	)
	drawing1.add_room_annotation(
		(6, 1+1),
		identifier="0.04",
		description="Chodba a schody",
		area=chodba.area,
	)
	drawing1.add_room_legend()

	common_wall_insulation(
		drawing1,
		wall_front_g, wall_1a_g, wall_1b_g, wall_gym_g, wall_back_g, wall_4_g
	)

	drawing1.render("ground.svg", png=True, png_dpi=600)

# Drawing 2 - upper floor
if "upper" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=BWT+2.75+2,
		radius=8.5,
		storeys=[upper],
		right_panel_width=40,
	)
	drawing1.include_element(heat_pump)
	drawing1.add_material_legend([
		("brick", "Nosná zeď - VPC Cihla 240 mm"),
		("drywall-diagonal1", "Příčka - Sádrokarton 100 mm"),
		("wood-solid", "Dřevěné části krovu"),
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_room_annotation(
		(6.5, 6),
		identifier="P.01",
		description="Pokoj 1",
		area=upper_pokoj_2.area,
		window_area=window_area(window_dormer_1, window_dormer_2),
	)
	drawing1.add_room_annotation(
		(1.5, 6),
		identifier="P.02",
		description="Pokoj 2",
		area=upper_pokoj_1.area,
		window_area=1.3+window_area(
			window_pokoj_nahore_2,
		),
	)
	drawing1.add_room_annotation(
		(9.5, 5),
		identifier="P.03",
		description="Skladovací prostor",
		area=upper_sklad.area,
		window_area=window_area(window_sklad),
	)

	drawing1.add_room_annotation(
		(9.5, 1.5),
		identifier="P.04",
		description="Záchod",
		area=zachod_nahore.area
	)
	drawing1.add_room_annotation(
		(7, 3),
		description="Galerie",
		identifier="P.05",
		area=galerie.area
	)
	drawing1.add_room_legend()

	# sklad nahore hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, wall_zachod_nahore_y), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT), offset=-0.75)
	# Pokoj 2, hloubka
	drawing1.add_dimension(start=(5.5, GALERY_END+0.1), end=(5.5, HOUSE_DEPTH-BWT), offset=0)

	# zachod nahire hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, BWT), end=(HOUSE_WIDTH-BWT, wall_zachod_nahore_y-0.1), offset=-0.75)

	# galerie hloubka
	drawing1.add_dimension(start=(6, GALERY_START), end=(6, GALERY_END), offset=0)

	common_dims(drawing1)
	common_wall_insulation(
		drawing1,
		wall_front_u, wall_1a_u, wall_1b_u, wall_gym_u, wall_dormer, wall_4_u
	)

	drawing1.render("upper.svg", png=True, png_dpi=600)

if "ceiling" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2", x=6, y=4, z=ground_floor_height+0.1, radius=8, storeys=[upper]
	)

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
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
