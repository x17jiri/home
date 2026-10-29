
# TODO:
# - roof angles

# Cihla:
# https://www.dek.cz/produkty/detail/4400914454-porfix-aku-248-pdk-tvarnice-p20-1800-248x249x248
# ma 56 dB, jine jen 53

# Sprcha:
# https://www.ravak.cz/p.sprchova-vanicka-sabina/A217001020

# Strecha:
#    - based on this:
#        - https://www.dataholz.eu/download/en/sdrhzi09b-4.pdf
#        - Rw+Ctr = 47 dB
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

# Zaves se sylomerem:
#    https://primavent.cz/primy-zaves-60-125-1-00-mm-akusticky-sylomer-baleni-35ks/

from dataclasses import dataclass
from pathlib import Path
from materials import resolve_timber_grade
from math import acos, degrees, isclose
import sys, math
import re
import xml.etree.ElementTree as ET
from ifc_utils import *
from shapely.geometry import Polygon, box as geometry_box
from shapely.ops import unary_union

class PDFFolder:
	def __init__(self, section, dir):
		self.section = section
		self.dir = dir
		self.counter = 0

	def add_pdf(self, name):
		self.counter += 1
		return self.dir + self.section + str(self.counter) + ". " + name + ".pdf"

DIR = PDFFolder("D1.1.", "projekt/D1.1. Architektonicko Stavební Řešení/")
DIR_ARCHITEKTONICKO_STAVEBNI_RESENI = DIR
PDF_FOUND = DIR.add_pdf("Základy")
PDF_GROUND = DIR.add_pdf("Půdorys 1.NP")
PDF_CEILING = DIR.add_pdf("Strop nad 1.NP")
PDF_UPPER = DIR.add_pdf("Půdorys podkroví")
PDF_KROV = DIR.add_pdf("Krov")
# Reserve the existing document numbers; these cuts now share PDF_KROV.
PDF_KROV_XX = DIR.add_pdf("Krov - řez XX")
PDF_KROV_YY = DIR.add_pdf("Krov - řez YY")
PDF_KROV_ZZ = DIR.add_pdf("Krov - řez ZZ")
PDF_AA = DIR.add_pdf("Řez AA")
PDF_BB = DIR.add_pdf("Podélný řez BB")
PDF_LAYERS = DIR.add_pdf("Skladby")
PDF_POHLED_ZAPAD = DIR.add_pdf("Pohled - Západ")
PDF_POHLED_ULICE = DIR.add_pdf("Pohled - Ulice")
PDF_POHLED_ZAHRADA = DIR.add_pdf("Pohled - Zahrada")
PDF_POHLED_VYCHOD = DIR.add_pdf("Pohled - Východ")

DIR_ZDRAVOTECHNICKE_INSTALACE = PDFFolder(
	"D1.5.", "projekt/D1.5. Zdravotechnické Instalace/",
)
PDF_KANAL = DIR_ZDRAVOTECHNICKE_INSTALACE.add_pdf("Kanalizace")
PDF_KANAL_GROUND = DIR_ZDRAVOTECHNICKE_INSTALACE.add_pdf("Kanalizace - Půdorys 1.NP")
PDF_KANAL_UPPER = DIR_ZDRAVOTECHNICKE_INSTALACE.add_pdf("Kanalizace - Půdorys podkroví")
PDF_VODA_GROUND = DIR_ZDRAVOTECHNICKE_INSTALACE.add_pdf("Vodovod - Půdorys 1.NP")
PDF_VODA_UPPER = DIR_ZDRAVOTECHNICKE_INSTALACE.add_pdf("Vodovod - Půdorys podkroví")

DIR_ELEKTRO = PDFFolder(
	"D1.4.", "projekt/D1.4. Zařízení Silnoproudé Elektrotechniky/",
)
PDF_ELEKTRO_GROUND = DIR_ELEKTRO.add_pdf("Elektro - Půdorys 1.NP")
PDF_ELEKTRO_UPPER = DIR_ELEKTRO.add_pdf("Elektro - Půdorys podkroví")
# Temporary wiring references; --no-room-corners also hides these guides.
ELEKTRO_SHOW_ROOM_CORNERS = False

@dataclass(frozen=True)
class SplitRafter:
	"""A main rafter divided at an absolute XY point inside a roof opening."""

	x: float
	y: float


@dataclass(frozen=True)
class StrongerRafter:
	"""A main rafter line using the stronger standard thickness."""

	x: float


def rafter_x_position(rafter):
	"""Return the main X coordinate of one entry in the rafters array."""
	if isinstance(rafter, (SplitRafter, StrongerRafter)):
		return rafter.x
	return rafter[0] if isinstance(rafter, tuple) else rafter


def framing_levels_from_arrays(high, lower):
	"""Index explicit assembly levels, keeping X-based drawing/support lookup."""
	levels = {}
	for level, entries in (("high", high), ("lower", lower)):
		for entry in entries:
			x = rafter_x_position(entry)
			if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
				raise ValueError("rafter X must be a finite number in metres")
			if x in levels:
				raise ValueError(f"duplicate main rafter X={x:g}; use distinct X coordinates for separate assemblies")
			levels[x] = level
	return levels


def rafter_collar_min_y(rafter):
	"""Optional absolute house-Y limit for both collar boards of a paired rafter."""
	if not isinstance(rafter, tuple):
		return None
	if len(rafter) not in (2, 3):
		raise ValueError("paired rafter must be (x, side) or (x, side, options)")
	options = rafter[2] if len(rafter) == 3 else {}
	if not isinstance(options, dict):
		raise TypeError("paired rafter options must be a dictionary")
	if set(options) - {"min_y"}:
		raise ValueError("unsupported paired rafter option; only min_y is supported")
	if "min_y" not in options:
		return None
	min_y = options["min_y"]
	if isinstance(min_y, bool) or not isinstance(min_y, (int, float)):
		raise TypeError("collar min_y must be a finite number in metres")
	if not math.isfinite(min_y):
		raise ValueError("collar min_y must be a finite number in metres")
	return float(min_y)

SECTION_OUTLINE_WIDTH = 0.3
SECTION_OUTLINE_COLOR = "black"
RAFTER_Z_OFFSET = -0.05
RAFTER_THICKNESS = 0.08
STRONGER_RAFTER_THICKNESS = 0.10
RAFTER_HEIGHT = 0.20
RAFTER_EXTRA_LENGTH = 0.0
RAFTER_SIZE = (RAFTER_THICKNESS, RAFTER_HEIGHT)
STRONGER_RAFTER_SIZE = (STRONGER_RAFTER_THICKNESS, RAFTER_HEIGHT)
SHORT_RAFTER_CUT_OVERLENGTH = 0.10
ROOF_WINDOW_TRIMMER_OVERLAP = 0.001
ROOF_WINDOW_OUTLINE_Y_MIN_INSET = 0.10
ROOF_BATTING_CENTER_OFFSET = RAFTER_Z_OFFSET + RAFTER_SIZE[1] / 2
# Keep the symbols centred, with clearance from both layer boundaries.
ROOF_BATTING_SIZE_FACTOR = 0.70
ROOF_BATTING_THICKNESS = RAFTER_SIZE[1] * ROOF_BATTING_SIZE_FACTOR
ROOF_BATTING_END_INSET = 0.03
VAPOUR_BARRIER_THICKNESS = 0.015
THERMAL_INSULATION_UNDER_RAFTERS = 0.14
UNDER_RAFTER_BATTING_THICKNESS = (
	THERMAL_INSULATION_UNDER_RAFTERS * ROOF_BATTING_SIZE_FACTOR
)
UNDER_RAFTER_BATTING_END_INSET = 0.015
INSTALLATION_SPACE_THICKNESS = 0.040
GYPSUM_PLASTERBOARD_THICKNESS = 0.025
MDF_THICKNESS = 0.015
# Thermal conductivities used by calculate_roof_u_value(), in W/(m K).
MDF_LAMBDA = 0.15
RAFTER_WOOD_LAMBDA = 0.15
BETWEEN_RAFTER_WOOL_LAMBDA = 0.04
UNDER_RAFTER_WOOL_LAMBDA = 0.04
# A closed air void is represented by an R-value instead of air lambda,
# because convection and radiation make thickness / lambda inappropriate.
INSTALLATION_SPACE_THERMAL_RESISTANCE = 0.16
ROOF_THERMAL_RAFTER_SPACING = 0.80
MDF_BOTTOM = RAFTER_Z_OFFSET + RAFTER_SIZE[1]
UNDERLAY_THICKNESS = 0.005
COUNTER_BATTEN_SIZE = (0.06, 0.06)
TILE_BATTEN_SIZE = (0.06, 0.04)
TILE_BATTEN_SPACING = 0.32
ROOF_TILE_PATTERN_WIDTH = 0.30
ROOF_TILE_THICKNESS = 0.03
RIDGE_TILE_WIDTH = 0.40
RIDGE_TILE_RISE = 0.12
RIDGE_TILE_THICKNESS = 0.025
CEMFLOW_AND_FINISH_THICKNESS = 0.065
GROUND_FLOOR_THICKNESS = 0.08+CEMFLOW_AND_FINISH_THICKNESS
UPPER_FLOOR_THICKNESS = 0.03+CEMFLOW_AND_FINISH_THICKNESS
FLOOR_INSULATION_MATERIAL = "tepelna/krocejova izolace"
FLOOR_BUILDUP_MATERIAL = "Floor build-up"
CEILING_FINISH_THICKNESS = 0.015
CEILING_FINISH_MATERIAL = "Ceiling finish"
FOUNDATION_BASE_PLATE_THICKNESS = 0.15
FOUNDATION_WALL_HEIGHT = 2.25
FOUNDATION_FOOTER_WIDTH = 0.70
FOUNDATION_FOOTER_HEIGHT = 0.50
BASEMENT_CEILING_SPACE = 0.25  # Reserved below the ground floor; no ceiling yet.
BASEMENT_FLOOR_START = -FOUNDATION_WALL_HEIGHT - BASEMENT_CEILING_SPACE
FOUNDATION_FOOTER_TOP_Z = BASEMENT_FLOOR_START - FOUNDATION_BASE_PLATE_THICKNESS
FOUNDATION_FOOTER_BOTTOM_Z = FOUNDATION_FOOTER_TOP_Z - FOUNDATION_FOOTER_HEIGHT
RING_BEAM_BAR_DIAMETER = 0.03
RING_BEAM_STIRRUP_DIAMETER = 0.008
RING_BEAM_CONCRETE_COVER = 0.05
UPPER_RING_BEAM_HEIGHT = 0.24
VAZNICE_HEIGHT = 0.32
VAZNICE_BASE = 0.20
VAZNICE_HALF_BASE = VAZNICE_BASE / 2.0
VAZNICE_DIST = 1.167 - VAZNICE_HALF_BASE
# High left pieces: tops and outer faces align with the middle.
VAZNICE_SIDE_HEIGHT = 0.24
VAZNICE_SIDE_BASE = 0.16
# New perpendicular roof: purlin TOP above the finished upper-floor surface.
TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR = 0.92
PURLIN_SIDE_PACKING_HEIGHT = VAZNICE_HEIGHT - VAZNICE_SIDE_HEIGHT
SEDLO_LENGTH = 1.5  # Retained for the force simulator's sedlo variant, not IFC geometry.
PURLIN_SPACER_SIZE = (0.08, 0.20)
PURLIN_SPACER_LENGTH = 2 * (VAZNICE_DIST - VAZNICE_HALF_BASE)
PURLIN_DRAWING_PATTERN = "brick"
PURLIN_LEFT_DRAWING_COLOR = "#f4a261"
PODLOZKY_VAZNIC_COLOR = "#f4a2f4"
PURLIN_MIDDLE_DRAWING_COLOR = "#e76f51"
PURLIN_RIGHT_DRAWING_COLOR = "#f4d35e"
WALL_PLATE_DRAWING_PATTERN = "brick-opposite"
STREET_WALL_PLATE_DRAWING_COLOR = "#e76f51"
SHORT_WALL_PLATE_DRAWING_COLOR = "#f4a261"
GARDEN_WALL_PLATE_DRAWING_COLOR = "#f4d35e"
DORMER_WALL_PLATE_DRAWING_COLOR = "#f4b6c2"
RAFTER_DRAWING_PATTERN = "diagonal1"
STRONGER_RAFTER_DRAWING_PATTERN = "crosshatch1"
MAIN_RAFTER_DRAWING_COLOR = "#f4d35e"
DORMER_SHORT_RAFTER_DRAWING_COLOR = "#f4b6c2"
DORMER_RAFTER_DRAWING_COLOR = "#5ed3f4"
PURLIN_AND_WALL_PLATE_DRAWING_ORDER = 1
COLLAR_TIE_DRAWING_COLOR = "#516fe7"
COLLAR_TIE_DRAWING_ORDER = 2
MAIN_RAFTER_DRAWING_ORDER = 3
DORMER_WALL_PLATE_DRAWING_ORDER = 4
DORMER_RAFTER_DRAWING_ORDER = 5
PERIMETER_TOP_HEIGHT = 0.0
EXTERIOR_XPS_INSULATION_THICKNESS = 0.16 + 0.005
FOUNDATION_XPS_INSULATION_THICKNESS = 0.10 + 0.005
PERIMETER_INSULATION_MATERIAL = "XPS"
PERIMETER_INSULATION_COLOR = "#f4dddd"
LIAPOR_COLOR = "#fff2cc"

THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM = (
	RAFTER_Z_OFFSET - THERMAL_INSULATION_UNDER_RAFTERS
)
UNDER_RAFTER_BATTING_CENTER_OFFSET = (
	THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM
	+ THERMAL_INSULATION_UNDER_RAFTERS / 2
)
VAPOUR_BARRIER_BOTTOM = (
	THERMAL_INSULATION_UNDER_RAFTERS_BOTTOM - VAPOUR_BARRIER_THICKNESS
)
GYPSUM_PLASTERBOARD_BOTTOM = (
	VAPOUR_BARRIER_BOTTOM
	- INSTALLATION_SPACE_THICKNESS
	- GYPSUM_PLASTERBOARD_THICKNESS
)

roof_u_value = calculate_roof_u_value(
	wood_fiberboard_thickness=MDF_THICKNESS,
	wood_fiberboard_lambda=MDF_LAMBDA,
	rafter_height=RAFTER_HEIGHT,
	rafter_width=RAFTER_THICKNESS,
	rafter_spacing=ROOF_THERMAL_RAFTER_SPACING,
	rafter_wood_lambda=RAFTER_WOOD_LAMBDA,
	between_rafter_wool_lambda=BETWEEN_RAFTER_WOOL_LAMBDA,
	under_rafter_wool_thickness=THERMAL_INSULATION_UNDER_RAFTERS,
	under_rafter_wool_lambda=UNDER_RAFTER_WOOL_LAMBDA,
	installation_space_resistance=(
		INSTALLATION_SPACE_THERMAL_RESISTANCE
		if INSTALLATION_SPACE_THICKNESS > 0
		else 0
	),
)
print("Roof thermal calculation (main layers only):")
print(
	f"  MDF R = "
	f"{roof_u_value.wood_fiberboard_resistance:.3f} m²K/W"
)
print(
	f"  Between-rafter layer R = "
	f"{roof_u_value.between_rafter_wool_resistance:.3f} m²K/W (wool), "
	f"{roof_u_value.rafter_wood_resistance:.3f} m²K/W (wood; "
	f"{roof_u_value.rafter_fraction:.1%} area)"
)
print(
	f"  Under-rafter wool R = "
	f"{roof_u_value.under_rafter_wool_resistance:.3f} m²K/W"
)
print(
	f"  Installation-space R = "
	f"{roof_u_value.installation_space_resistance:.3f} m²K/W"
)
print(f"  Effective R = {roof_u_value.effective_resistance:.3f} m²K/W")
print(f"  U = {roof_u_value.u_value:.3f} W/(m²K)")

BWT = 0.24 # Basic wall thickness
FACADE_INSULATION_THICKNESS = 0.20
FACADE_THICKNESS = 0.005

GROUND_WALL_BASE_COURSE_HEIGHT = 0.27
GROUND_WALL_BASE_COURSE_MATERIAL = "Liapor brick"
ground_floor_height = GROUND_WALL_BASE_COURSE_HEIGHT + 2.5
door_clear_height = 2.1
CEILING_THICKNESS = 0.25

UPPER_FLOOR_START = ground_floor_height + CEILING_THICKNESS
COLLAR_TIE_THICKNESS = 0.05
COLLAR_TIE_SIZE = (COLLAR_TIE_THICKNESS, 0.15)
COLLAR_TIE_EXTENSION = 1.5  # uncut overlength; roof planes define finished ends
NADEZDIVKA = 1.125 + UPPER_RING_BEAM_HEIGHT
# Lower horizontal plasterboard underside above the upper finished floor.
# Independent of the high bay's suspended-ceiling height.
LOWER_CEILING_CLEAR_HEIGHT = 2.30
PURLIN_WALL_TOP_HEIGHT = 3.5 - 1.375 + NADEZDIVKA - VAZNICE_HEIGHT
# Retained OSB/vapour-barrier top above the upper slab, no longer tied to a purlin.
LOWER_VAPOUR_BARRIER_TOP_HEIGHT = 2.5

house = House(
    "My house",
    mirror_x=False,
    colors={
        "wall": "#ffffff",
        "door": "#8B5A2B",
        "window": "#ffffff",
    },
)

foundation = house.storey("Foundations", elevation=FOUNDATION_FOOTER_BOTTOM_Z)
basement = house.storey("Basement", elevation=BASEMENT_FLOOR_START)
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
	color=LIAPOR_COLOR,
)

partition_wall = house.wall_type(
    "Partition wall - VPC 115 mm",
    layers=[
        ("Brick", 0.115),
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

HOUSE_DEPTH = 7.99
HALF_DEPTH = HOUSE_DEPTH / 2.0
KITCHEN_WIDTH = 4.5 + 0.01
KK_WIDTH = 2.50 + 0.01

wall2_x = BWT + 3.25 + 0.01 + BWT;
wall3_x = wall2_x + KITCHEN_WIDTH + BWT;
HOUSE_WIDTH = wall3_x + KK_WIDTH + BWT
LOWER_NADEZDIVKA_X = wall3_x + 1.375
if not wall3_x < LOWER_NADEZDIVKA_X < HOUSE_WIDTH:
	raise ValueError("LOWER_NADEZDIVKA_X must be between wall3 and wall4")


def west_roof_closure_layout():
	"""Shared layer positions for the closure and rooms meeting its inner face."""
	specs = (
		("Siding", FACADE_THICKNESS, "Facade finish", "#ffffff",
		 RAFTER_Z_OFFSET + RAFTER_HEIGHT, None),
		("MDF", MDF_THICKNESS, "MDF", "#f2b6d0", MDF_BOTTOM, None),
		("Insulation", FACADE_INSULATION_THICKNESS, None, None, None, None),
		("Vapour barrier", VAPOUR_BARRIER_THICKNESS, "Vapour barrier", "#4A90E2",
		 VAPOUR_BARRIER_BOTTOM, "Vapour barrier"),
		("Installation space", INSTALLATION_SPACE_THICKNESS, None, None, None, None),
		("Gypsum plasterboard", GYPSUM_PLASTERBOARD_THICKNESS, "Gypsum plasterboard", "#E8E5DE",
		 GYPSUM_PLASTERBOARD_BOTTOM, "Gypsum plasterboard"),
	)
	edge = LOWER_NADEZDIVKA_X - 0.03
	ranges = {}
	for name, thickness, *_ in specs:
		ranges[name] = (edge-thickness, edge)
		edge -= thickness
	return specs, ranges


WEST_CLOSURE_INNER_X = west_roof_closure_layout()[1]["Gypsum plasterboard"][0]

aa_cut = CutDefinition(
	start=(wall2_x + 0.01, -2.5),
	end=(wall2_x + 0.01, HOUSE_DEPTH + 2.5),
	identifier="A",
	direction=-1,
)
bb_cut = CutDefinition(
	start=(-2.5, HALF_DEPTH+0.01),
	end=(HOUSE_WIDTH + 2.5, HALF_DEPTH+0.01),
	identifier="B",
	direction=1,  # Look towards the garden (+Y).
)
MIDDLE_PURLIN_X_MIN = wall2_x - BWT / 2
MIDDLE_PURLIN_X_MAX = wall3_x - BWT / 2
stair_height = (
	ground_floor_height - GROUND_FLOOR_THICKNESS
	+ CEILING_THICKNESS + UPPER_FLOOR_THICKNESS)
step_count = 16
STAIR_TREAD_THICKNESS = 0.04
STAIR_STRINGER_THICKNESS = 0.05
STAIR_STRINGER_HEIGHT = 0.30

GYM_DEPTH = 2.01
pokoj_dole = ground.floor_layer(
	"Pokoj",
	room_id="0.02",
	outline=(
		(BWT, BWT+GYM_DEPTH+0.115),
		(wall2_x-BWT, BWT+GYM_DEPTH+0.115),
		(wall2_x-BWT, HOUSE_DEPTH-BWT),
		(BWT, HOUSE_DEPTH-BWT),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=GROUND_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
CHODBA_DEPTH = 2.635
GALERY_START = BWT+2.4

wall_zachod_nahore_y = math.ceil((GALERY_START)/0.125)*0.125
wall_za_umyvadlem_y = wall_zachod_nahore_y + 2.0
OBLOUK_WIDTH = 2.0
oblouk_at = HOUSE_DEPTH-BWT-1.5-OBLOUK_WIDTH

# Each number is the absolute X coordinate of a main rafter centre.
# SplitRafter divides its garden-side rafter at an absolute Y coordinate inside
# a roof opening; the opening then cuts the two parts back to its exact edges.
# StrongerRafter uses the stronger thickness on both sides of the main roof.
# A tuple also creates a touching dormer rafter on the requested side.  "before"
# and "after" shorten the main rafter on the garden side; "+before" and
# "+after" leave it full-length.
# An optional third tuple item {"min_y": y} trims both collar boards to Y >= y,
# in absolute house coordinates, without changing either rafter.

vk_from = wall2_x-0.24-0.1
vk_to = wall3_x+0.1

a = math.floor((vk_to - vk_from - 3*0.67 - 0.75 - 0.86) / 2 * 1000.0) / 1000.0
a = 0.91

# Remaining high/dormer assemblies, independent of the interior-layer ranges.
high_rafters = [
	-0.10,
	(-0.10+1.65)/2,
	1.65,
	1.65+0.91,
	(vk_from, "+before"),
	(vk_from+0.91, "before", {"min_y": GALERY_START+0.05}),
	(vk_from+0.91+0.67, "before"),
	(vk_from+0.91+0.67+0.75, "after"),
	(vk_from+0.91+0.67+0.75+0.67, "after"),
	(vk_from+0.91+0.67+0.75+0.67+0.67, "after"),
	(vk_from+0.91+0.67+0.75+0.67+0.67+0.67, "after"),
	(vk_to, "+after"),
	LOWER_NADEZDIVKA_X - 0.15,
	]
# Shared drawing indices and assembly generation keep the original order.
rafters = high_rafters
framing_levels = framing_levels_from_arrays(high_rafters, ())

# chimney
CHIMNEY_DIST=0.47
CHIMNEY_Y_START = HALF_DEPTH - VAZNICE_DIST - VAZNICE_HALF_BASE - 0.05 - 0.4
CHIMNEY_Y_START = 0.125*math.floor((CHIMNEY_Y_START - 0.04 - 0.17) / 0.125) + 0.04 + 0.17
CHIMNEY_Y_START = CHIMNEY_Y_START + 0.025 - 0.125

CHIMNEY_Y_START = GALERY_START - 0.5 # override

CHIMNEY_X_START = (rafters[5][0]+0.05 + rafters[6][0]-0.05-0.08)/2 - 0.2

############## overrides
CHIMNEY_Y_START = GALERY_START - 0.45
CHIMNEY_X_START = wall2_x + 0.02

CHIMNEY_Y_MID = CHIMNEY_Y_START + 0.2
CHIMNEY_Y_END = CHIMNEY_Y_START + 0.4
CHIMNEY_X_MID = CHIMNEY_X_START + 0.2
CHIMNEY_X_END = CHIMNEY_X_START + 0.4

print("CHIMNEY_Y_START = ", CHIMNEY_Y_START)
print("CHIMNEY_Y_MID = ", CHIMNEY_Y_MID)
print("CHIMNEY_Y_END = ", CHIMNEY_Y_END)

BATHROOM_DEPTH = 2.635
DRAINAGE_STACK_X = wall3_x + 0.1 + 0.12
DRAINAGE_STACK_Y = wall_zachod_nahore_y - 0.1 - 0.1
kuchyn = ground.floor_layer(
	"Kuchyn",
	room_id="0.01",
	outline=(
		(wall2_x, GALERY_START+0.115),
		(wall2_x+1.125, GALERY_START+0.115),
		(wall2_x+1.125, BWT+CHODBA_DEPTH+0.115),
		(wall3_x-BWT, BWT+CHODBA_DEPTH+0.115),
		(wall3_x-BWT, oblouk_at),
		(wall3_x, oblouk_at),
		(wall3_x, BWT+BATHROOM_DEPTH+0.115),
		(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH+0.115),
		(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT),
		(wall3_x, HOUSE_DEPTH-BWT),
		(wall3_x, oblouk_at+OBLOUK_WIDTH),
		(wall3_x-BWT, oblouk_at+OBLOUK_WIDTH),
		(wall3_x-BWT, HOUSE_DEPTH-BWT),
		(wall2_x, HOUSE_DEPTH-BWT),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=GROUND_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
chodba = ground.floor_layer(
	"Chodba",
	room_id="0.04",
	outline=(
		(BWT, BWT),
		(wall3_x-BWT, BWT),
		(wall3_x-BWT, BWT+CHODBA_DEPTH),
		(wall2_x+1.125, BWT+CHODBA_DEPTH),
		(wall2_x+1.125, GALERY_START),
		(wall2_x, GALERY_START),
		(wall2_x, BWT+GYM_DEPTH),
		(BWT, BWT+GYM_DEPTH),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=GROUND_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
	insulation_material=FLOOR_INSULATION_MATERIAL,
	buildup_material=FLOOR_BUILDUP_MATERIAL,
	color="#ffff80",
)
koupelna = ground.floor_layer(
	"Koupelna",
	room_id="0.03",
	outline=(
		(wall3_x, BWT),
		(HOUSE_WIDTH-BWT, BWT),
		(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH),
		(wall3_x, BWT+BATHROOM_DEPTH),
	),
	thickness=GROUND_FLOOR_THICKNESS,
	insulation_thickness=GROUND_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
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
wall_front_g = ground.wall((0, 0), (HOUSE_WIDTH, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_4_g = ground.wall((HOUSE_WIDTH, 0), (HOUSE_WIDTH, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_back_g = ground.wall((HOUSE_WIDTH, HOUSE_DEPTH), (0, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_1_g = ground.wall((0, HOUSE_DEPTH), (0, 0), wall_type=load_bearing_wall, height=ground_floor_height)
wall_2 = ground.wall((wall2_x, BWT), (wall2_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)
wall_3 = ground.wall((wall3_x, 0), (wall3_x, HOUSE_DEPTH), wall_type=load_bearing_wall, height=ground_floor_height)

ground.connect_wall(wall_1_g, wall_back_g)

#ground.connect_wall(wall_2, wall_front_g, is_atpath=True)
ground.connect_wall(wall_2, wall_back_g, is_atpath=True)

ground.connect_wall(wall_3, wall_front_g, is_atpath=True)
ground.connect_wall(wall_3, wall_back_g, is_atpath=True)

ground.connect_wall(wall_4_g, wall_front_g)
ground.connect_wall(wall_4_g, wall_back_g)

# Front door/window

BOTTOM_STAIR_TREADS = 9
GROUND_DOOR_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT + 2.125
GROUND_WINDOW_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT + 2.25
GROUND_WINDOW_SILL_HEIGHT = GROUND_WALL_BASE_COURSE_HEIGHT + 0.875
front_door = wall_1_g.add_door(
	at=HOUSE_DEPTH-BWT-GYM_DEPTH+0.125,
	opening_width=1.125, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=GROUND_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT"
)

# Front windows (koupelna)
window_bathroom = wall_front_g.add_window(
	at=HOUSE_WIDTH-BWT-1.0, width=0.5,
	sill_height=GROUND_WINDOW_HEIGHT-0.75,
	height=GROUND_WINDOW_HEIGHT)

# Back windows
print("KK_WIDTH=", KK_WIDTH)
window_obyvak = wall_back_g.add_window(
	at=BWT+KK_WIDTH+BWT + round(KITCHEN_WIDTH / 0.25) * 0.125 - 1.25, width=2.5,
	sill_height=GROUND_WINDOW_SILL_HEIGHT,
	height=GROUND_WINDOW_HEIGHT)
window_pokoj_dole = wall_back_g.add_window(
	at=HOUSE_WIDTH-wall2_x+BWT+0.875,
	width=1.5, sill_height=GROUND_WINDOW_SILL_HEIGHT, height=GROUND_WINDOW_HEIGHT)
window_kk = wall_back_g.add_window(
	at=BWT+KK_WIDTH-0.125-1,
	width=1.0, sill_height=GROUND_WINDOW_SILL_HEIGHT,
	height=GROUND_WINDOW_HEIGHT,)
window_kk1 = wall_4_g.add_window(
	at=HOUSE_DEPTH-BWT-1.5-1.5,
	sill_height=GROUND_WINDOW_SILL_HEIGHT,
	height=GROUND_WINDOW_SILL_HEIGHT+0.5,
	width=1.5,)

# Posilovna, Gym
wall_gym_g = ground.wall(
	(BWT, BWT+GYM_DEPTH), (wall2_x-BWT, BWT+GYM_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)

# The ring beam caps the ground-floor walls, but belongs to the upper storey.
# Its negative local offset keeps it directly below the upper-floor elevation.
ring_beams = upper.add_ring_beams_from(
	ground,
	source_wall_type=load_bearing_wall,
	height=CEILING_THICKNESS,
	start_height=-CEILING_THICKNESS,
	concrete_material="Concrete topping",
	reinforcement_material="Ring beam reinforcement",
	bar_diameter=RING_BEAM_BAR_DIAMETER,
	stirrup_diameter=RING_BEAM_STIRRUP_DIAMETER,
	concrete_cover=RING_BEAM_CONCRETE_COVER,
)

foundation_base_plate = basement.floor_layer(
	"Foundation base plate",
	outline=(
		(0, 0),
		(HOUSE_WIDTH, 0),
		(HOUSE_WIDTH, HOUSE_DEPTH),
		(0, HOUSE_DEPTH),
	),
	thickness=FOUNDATION_BASE_PLATE_THICKNESS,
	start_height=-FOUNDATION_BASE_PLATE_THICKNESS,
	kind="BASESLAB",
	load_bearing=True,
	buildup_material="Base plate concrete",
	color="#B8B8B8",
)
foundation_walls = basement.add_walls_from(
	ground,
	source_wall_type=load_bearing_wall,
	wall_type=foundation_wall,
	height=FOUNDATION_WALL_HEIGHT,
	start_height=0,
)
foundation_footers = foundation.add_strip_footings_from(
	ground,
	source_wall_type=load_bearing_wall,
	width=FOUNDATION_FOOTER_WIDTH,
	height=FOUNDATION_FOOTER_HEIGHT,
	start_height=0,
	material="Concrete",
	color="#969696",
)

_foundation_insulation_sets = []
_foundation_insulation_wall_types = {}

def add_foundation_insulation(outline, *, thickness, height):
	"""Add horizontal and inward-facing vertical foundation insulation.

	``outline`` is a polygon in global XY coordinates.  The horizontal layer
	sits directly below the foundation base plate.  Vertical layers follow the
	polygon boundary, extend inward, and finish at the base plate underside.
	Clockwise outlines are reversed automatically.
	"""
	def point(value, argument):
		if isinstance(value, (str, bytes)):
			raise TypeError(f"{argument} must contain exactly two coordinates")
		try:
			x, y = value
		except (TypeError, ValueError) as error:
			raise TypeError(
				f"{argument} must contain exactly two coordinates"
			) from error
		for coordinate, coordinate_name in ((x, "x"), (y, "y")):
			if (
				isinstance(coordinate, bool)
				or not isinstance(coordinate, (int, float))
				or not math.isfinite(coordinate)
			):
				raise TypeError(
					f"{argument} {coordinate_name} must be a finite number"
				)
		return float(x), float(y)

	if isinstance(outline, (str, bytes)):
		raise TypeError("outline must contain at least three points")
	try:
		supplied_outline = list(outline)
	except TypeError as error:
		raise TypeError("outline must contain at least three points") from error
	if len(supplied_outline) < 3:
		raise ValueError("outline must contain at least three points")
	points = tuple(
		point(value, f"outline point {index}")
		for index, value in enumerate(supplied_outline, start=1)
	)
	if len(points) > 3 and points[-1] == points[0]:
		points = points[:-1]
	if len(points) < 3:
		raise ValueError("outline must contain at least three distinct points")
	for current, following in zip(points, (*points[1:], points[0])):
		if current == following:
			raise ValueError(
				"outline must not contain consecutive duplicate points"
			)
	polygon = Polygon(points)
	if polygon.is_empty or polygon.area <= 1e-9:
		raise ValueError("foundation insulation outline must enclose an area")
	if not polygon.is_valid:
		raise ValueError("foundation insulation outline must be a valid polygon")
	twice_signed_area = sum(
		current[0] * following[1] - following[0] * current[1]
		for current, following in zip(points, (*points[1:], points[0]))
	)
	if twice_signed_area < 0:
		points = tuple(reversed(points))

	if (
		isinstance(thickness, bool)
		or not isinstance(thickness, (int, float))
		or not math.isfinite(thickness)
		or thickness <= 0
	):
		raise ValueError("thickness must be a finite number greater than zero")
	if (
		isinstance(height, bool)
		or not isinstance(height, (int, float))
		or not math.isfinite(height)
		or height <= 0
	):
		raise ValueError("height must be a finite number greater than zero")

	thickness = float(thickness)
	height = float(height)
	if polygon.buffer(-thickness, join_style="mitre").is_empty:
		raise ValueError(
			"thickness is too large for the foundation insulation outline"
		)

	set_number = len(_foundation_insulation_sets) + 1
	base_plate_bottom = foundation_base_plate.start_height
	horizontal = basement.floor_layer(
		f"Foundation insulation {set_number} horizontal",
		outline=points,
		thickness=thickness,
		start_height=base_plate_bottom-thickness,
		kind="FLOOR",
		buildup_material=PERIMETER_INSULATION_MATERIAL,
		color=PERIMETER_INSULATION_COLOR,
	)

	wall_type = _foundation_insulation_wall_types.get(thickness)
	if wall_type is None:
		wall_type = house.wall_type(
			f"Foundation insulation - {PERIMETER_INSULATION_MATERIAL} "
			f"{thickness * 1000:g} mm",
			layers=[(PERIMETER_INSULATION_MATERIAL, thickness), "axis"],
			color=PERIMETER_INSULATION_COLOR,
		)
		_foundation_insulation_wall_types[thickness] = wall_type

	vertical = tuple(
		basement.wall(
			wall_start,
			wall_end,
			wall_type=wall_type,
			height=height,
			start_height=base_plate_bottom-height,
		)
		for wall_start, wall_end in zip(
			points,
			(*points[1:], points[0]),
		)
	)
	for side_number, wall in enumerate(vertical, start=1):
		wall.Name = (
			f"Foundation insulation {set_number} vertical {side_number}"
		)
	for wall, next_wall in zip(vertical, (*vertical[1:], vertical[0])):
		basement.connect_wall(wall, next_wall)

	result = (horizontal, vertical)
	_foundation_insulation_sets.append(result)
	return result

# Bathroom, Koupelna
wall_bathroom = ground.wall(
	(wall3_x, BWT+BATHROOM_DEPTH), (HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
heat_pump = ground.furniture(
    "Tepelné\nČerpadlo",
    kind="USERDEFINED",
    size=(1.2, 0.5, 1.5),
    color="#ffffff",
    center=(1.5, 0.0-FACADE_INSULATION_THICKNESS-FACADE_THICKNESS-0.05-0.25),
#	rotation=-90,
)
rozvadec = ground.furniture(
    "Rozvaděč",
    kind="USERDEFINED",
    size=(0.8, 0.5, 1.5),
    color="#ffffff",
    center=(3, BWT+0.3),
	start_height=GROUND_FLOOR_THICKNESS+0.1,
)
ground.furniture(
    "Pračka",
    kind="USERDEFINED",
	start_height=GROUND_FLOOR_THICKNESS,
    size=(0.7, 0.7, 0.8),
    color="#ffffff",
    center=(wall3_x-BWT-0.4, BWT+0.4),
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
    "Hydro-\nbox",
    kind="USERDEFINED",
    size=(0.8, 0.5, 0.9),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(wall3_x+KK_WIDTH/2.0, BWT+0.3),
)
ground.furniture(
    "Vodo-\nměr",
    kind="USERDEFINED",
    size=(0.6, 0.55, 0.9),
	start_height=GROUND_FLOOR_THICKNESS,
    color="#ffffff",
    center=(wall3_x+KK_WIDTH/2.0, BWT+0.7),
)
gauc = ground.asset(
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
	start_height=GROUND_FLOOR_THICKNESS + 0.85 - 0.25,
	rotation=-90,
)
ground.asset(
    "Sprcha",
    asset="shower_90x90",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(HOUSE_WIDTH-(BWT+0.5), BWT+BATHROOM_DEPTH-0.5),
	rotation=0,
)
toilet_x = HOUSE_WIDTH-(BWT+KK_WIDTH)+0.4
toilet_y = BWT+0.5
ground.asset(
    "WC",
    asset="toilet_without_cistern",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(toilet_x, toilet_y),
    rotation=180,
)

# Kitchen, Kuchyn
wall_kitchen_1 = ground.wall(
	(wall2_x, GALERY_START),
	(wall2_x+1.01, GALERY_START),
	wall_type=partition_wall, height=ground_floor_height)
wall_kitchen_2 = ground.wall(
	(wall2_x+1.01, GALERY_START+0.75),
	(wall2_x+1.01, GALERY_START),
	wall_type=partition_wall, height=ground_floor_height)
wall_kitchen_3 = ground.wall(
	(wall2_x+1.125, BWT+CHODBA_DEPTH),
	(wall2_x+KITCHEN_WIDTH, BWT+CHODBA_DEPTH),
	wall_type=partition_wall, height=ground_floor_height)
kitchen_door = wall_kitchen_3.add_door(
	at=0.05,
	opening_width=1.0, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	sill_height=0,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_LEFT",
	reverse_swing=False
)

# Pokoj Risanek
pokoj0_door = wall_gym_g.add_door(
	at=wall2_x-2*BWT-0.125-1,
	opening_width=1.0, width=0.9,
	height=GROUND_DOOR_HEIGHT,
	sill_height=0,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_RIGHT",
#	reverse_swing=True,
)

# pruchod vchod
wall_2.add_opening(
	at=0.625,
	width=1.0,
	height=GROUND_DOOR_HEIGHT,
	sill_height=0,
)

# Oblouk
oblouk = wall_3.add_opening(
	at=oblouk_at,
	width=OBLOUK_WIDTH,
    height=ground_floor_height-0.5,
    sill_height=0,
	name="Oblouk"
)

# Bathroom
bathroom_door = wall_3.add_door(
    at=BWT+math.floor((CHODBA_DEPTH-1.125)/0.125)*0.125,
    opening_width=1.0, width=0.9,
    height=GROUND_DOOR_HEIGHT,
	sill_height=0,
	clear_height=door_clear_height,
	operation="SINGLE_SWING_RIGHT",
	reverse_swing=True,
)

ground_load_bearing_walls = (
	wall_front_g,
	wall_4_g,
	wall_back_g,
	wall_1_g,
	wall_2,
	wall_3,
)
for wall in ground_load_bearing_walls:
	wall.set_vertical_material_layers(
		[
			(
				GROUND_WALL_BASE_COURSE_MATERIAL,
				GROUND_WALL_BASE_COURSE_HEIGHT,
			),
			(
				"Brick",
				wall.height - GROUND_WALL_BASE_COURSE_HEIGHT,
			),
		],
		type_name="Ground load bearing wall - Liapor base course",
	)

# stairs
stairs_width = 1
straight_stair_step_size = 0.27
stair_step_height = stair_height / step_count
remaining_stair_count = step_count - 2 - BOTTOM_STAIR_TREADS
straight_stair_start_y = BWT + 1.02
landing_left_x = wall3_x - BWT - 1
bottom_stair_start_x = landing_left_x - straight_stair_step_size * BOTTOM_STAIR_TREADS
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
		straight_stair_start_y + straight_stair_step_size * remaining_stair_count,
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

stairway_notes = [
	f"Šířka stupně (nášlap): {main_stairs.tread_length * 1000:.0f} mm",
	f"Výška stupně: {main_stairs.riser_height * 1000:.1f} mm".replace(".", ","),
	f"Počet stupňů: {main_stairs.risers + gallery_stairs.risers}",
]

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

GALERY_END = BWT + math.ceil((GALERY_START - BWT)/0.125)*0.125 + 1.05

kamna = ground.furniture(
    "Kamna",
    kind="USERDEFINED",
    size=(0.6, 0.5, 1.5),
    color="#ffff2B",
    center=(wall2_x + 0.5, GALERY_START+0.115+0.2+0.25),
	start_height=GROUND_FLOOR_THICKNESS+0.05,
#    rotation=-45,
)

# Kuchyn
#print("SEARCH: ", "\n".join(str(x) for x in house.assets.search("table")))
ground.furniture(
	"Dřez",
    kind="USERDEFINED",
    size=(0.64, 0.64, 0.75),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
    center=(HOUSE_WIDTH-BWT-0.35, BWT+BATHROOM_DEPTH+0.115+0.35),
)
ground.furniture(
	"Myčka",
    kind="USERDEFINED",
    size=(0.64, 0.64, 0.75),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
    center=(HOUSE_WIDTH-BWT-0.35-0.64, BWT+BATHROOM_DEPTH+0.115+0.35),
)
ground.furniture(
	"Lednice",
    kind="USERDEFINED",
    size=(0.64, 1, 1.95),
    center=(HOUSE_WIDTH-BWT-0.35, HOUSE_DEPTH-BWT-0.55),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
)
ground.furniture(
	"Sporák",
    kind="USERDEFINED",
    size=(0.64, 0.64, 0.75),
    center=(HOUSE_WIDTH-BWT-0.35, BWT+BATHROOM_DEPTH+0.115+0.35+0.7),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
)
KUCH_LINKA_LEN = HOUSE_DEPTH-2*BWT-0.115-BATHROOM_DEPTH-0.1-0.64-0.7-1.0
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(0.64, KUCH_LINKA_LEN, 0.75),
    center=(HOUSE_WIDTH-BWT-0.35, HOUSE_DEPTH-BWT-1-KUCH_LINKA_LEN/2),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
)
KUCH_LINKA_LEN = KK_WIDTH-1.4
ground.furniture(
	"Kuch.\nLinka",
    kind="USERDEFINED",
    size=(KUCH_LINKA_LEN, 0.64, 0.75),
    center=(HOUSE_WIDTH-BWT-1.35-KUCH_LINKA_LEN/2, BWT+BATHROOM_DEPTH+0.115+0.35),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
)
ground.asset(
    "Stul",
    asset="retail_4_seater_rectangular_table",
    center=(wall3_x-BWT-1.1, HOUSE_DEPTH - BWT - 1.2),
	start_height=GROUND_FLOOR_THICKNESS+0.03,
	#size=(1.3, 0.8*3),
)

# MIAKO
ceiling1 = upper.miako_slab(
    "Ceiling 1",
    start=(BWT-0.135, HOUSE_DEPTH-BWT+0.04),
    end=(wall2_x-BWT+0.135, HOUSE_DEPTH-BWT+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=CEILING_THICKNESS-0.06,
    direction=(0, -1),
	block_start_offset=0.125,
    block_end_offset=0.125,
	structure=[
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"wide", "beam",
		],
)
ceiling2 = upper.miako_slab(
    "Ceiling 2",
    start=(wall2_x-0.135, GALERY_START),
    end=(wall3_x-BWT+0.135, GALERY_START),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=CEILING_THICKNESS-0.06,
    direction=(0, 1),
	block_start_offset=0.125,
    block_end_offset=0.125,
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
    start=(wall3_x-0.135, HOUSE_DEPTH-BWT+0.04),
    end=(HOUSE_WIDTH-BWT+0.135, HOUSE_DEPTH-BWT+0.04),
    top=0,
	topping=0.06,
	beam_height=0.06,
	block_height=CEILING_THICKNESS-0.06,
    direction=(0, -1),
	block_start_offset=0.125,
    block_end_offset=0.125,
    structure=[
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide", "beam",
		"narrow", "beam",
		"wide", "beam",
		"narrow", "beam",
		"wide", "beam",
		"wide", "beam",
		"wide",
		],
)

upper_pokoj_1 = upper.floor_layer(
		f"Upper Pokoj 1",
		room_id="P.02",
		outline=(
			(BWT, BWT),
			(wall2_x-BWT, BWT),
			(wall2_x-BWT, HOUSE_DEPTH-BWT),
			(BWT, HOUSE_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
upper_pokoj_2 = upper.floor_layer(
		f"Upper Pokoj 2",
		room_id="P.01",
		outline=(
			(wall2_x, GALERY_END+0.1),
			(wall3_x-BWT, GALERY_END+0.1),
			(wall3_x-BWT, HOUSE_DEPTH-BWT),
			(wall2_x, HOUSE_DEPTH-BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
galerie = upper.floor_layer(
		f"Galerie",
		room_id="P.03",
		outline=(
			(wall2_x, GALERY_START),
			(wall3_x-BWT, GALERY_START),
			(wall3_x-BWT, wall_zachod_nahore_y),
			(WEST_CLOSURE_INNER_X, wall_zachod_nahore_y),
			(WEST_CLOSURE_INNER_X, wall_za_umyvadlem_y-0.1),
			(wall3_x, wall_za_umyvadlem_y-0.1),
			(wall3_x, wall_zachod_nahore_y+1.0),
			(wall3_x-BWT, wall_zachod_nahore_y+1.0),
			(wall3_x-BWT, GALERY_END),
			(wall2_x, GALERY_END),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)
zachod_nahore = upper.floor_layer(
		f"Zachod",
		room_id="P.04",
		outline=(
			(wall3_x, wall_zachod_nahore_y-0.1),
			(WEST_CLOSURE_INNER_X, wall_zachod_nahore_y-0.1),
			(WEST_CLOSURE_INNER_X, BWT),
			(wall3_x, BWT),
		),
		thickness=UPPER_FLOOR_THICKNESS,
		insulation_thickness=UPPER_FLOOR_THICKNESS-CEMFLOW_AND_FINISH_THICKNESS,
		insulation_material=FLOOR_INSULATION_MATERIAL,
		buildup_material=FLOOR_BUILDUP_MATERIAL,
		color="#ffff80",
	)

STREET_ROOF_JOINT_Y = HALF_DEPTH-VAZNICE_DIST-VAZNICE_HALF_BASE
GARDEN_ROOF_JOINT_Y = HALF_DEPTH+VAZNICE_DIST+VAZNICE_HALF_BASE
# Inner walls stay at the middle-purlin underside. Side pieces bear higher:
# raised outer gables and short timber blocks on the outer half of inner walls.
INNER_SUPPORT_WALL_HEIGHT = PURLIN_WALL_TOP_HEIGHT
OUTER_SUPPORT_WALL_HEIGHT = PURLIN_WALL_TOP_HEIGHT + PURLIN_SIDE_PACKING_HEIGHT
PURLIN_SIDE_PACKING_LENGTH = BWT / 2
ROOF_JOINT_Z = (
	UPPER_FLOOR_START + PURLIN_WALL_TOP_HEIGHT + VAZNICE_HEIGHT
)
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
# Keep BOTH main and dormer roof planes unchanged by aligning top/outer edges.
# DIST measures to the centreline, hence half the difference in FULL widths.
MAIN_ROOF_SLOPE = (
	(ROOF_JOINT_Z - STREET_ROOF_PLANE_POINTS[2][2])
	/ (STREET_ROOF_JOINT_Y - STREET_ROOF_PLANE_POINTS[2][1])
)
VAZNICE_SIDE_DIST = (
	VAZNICE_DIST
	+ (VAZNICE_BASE - VAZNICE_SIDE_BASE) / 2
)
if any(not math.isfinite(value) or value <= 0 for value in (
	VAZNICE_HEIGHT, VAZNICE_BASE, VAZNICE_DIST,
	VAZNICE_SIDE_HEIGHT, VAZNICE_SIDE_BASE, VAZNICE_SIDE_DIST,
)):
	raise ValueError("purlin dimensions and ridge distances must be positive and finite")
if PURLIN_SIDE_PACKING_HEIGHT < 0:
	raise ValueError("side purlins cannot be taller than middle purlins")
DORMER_WALL_HEIGHT = 2.625
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


STREET_GYPSUM_PLASTERBOARD_CUT = offset_plane(
	*STREET_ROOF_PLANE_POINTS,
	offset=GYPSUM_PLASTERBOARD_BOTTOM,
)

# upper floor
wall_cuts_1 = [
	offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	offset_plane(*GARDEN_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	(
		(0, HALF_DEPTH-VAZNICE_DIST-VAZNICE_HALF_BASE, UPPER_FLOOR_START+OUTER_SUPPORT_WALL_HEIGHT),
		(0, HALF_DEPTH+VAZNICE_DIST+VAZNICE_HALF_BASE, UPPER_FLOOR_START+OUTER_SUPPORT_WALL_HEIGHT),
		(5, HALF_DEPTH+VAZNICE_DIST+VAZNICE_HALF_BASE, UPPER_FLOOR_START+OUTER_SUPPORT_WALL_HEIGHT),
	),
#	((0, 0.25, 0), (10, 0.25, 0), (0, 0.25, 10)),
]
wall_cuts_2_3 = [
	offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
	offset_plane(*DORMER_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET),
]

wall_dormer = upper.wall(
	(wall3_x, HOUSE_DEPTH), (wall2_x-BWT, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=DORMER_WALL_HEIGHT-NADEZDIVKA, start_height=NADEZDIVKA)
wall_front1_u = upper.wall(
	(0, 0), (LOWER_NADEZDIVKA_X, 0),
	wall_type=load_bearing_wall, height=NADEZDIVKA)
# Both back-wall parts retain the original right-to-left orientation.
# Part 1 is the higher (left) portion, matching front part 1.
wall_back1_u = upper.wall(
	(LOWER_NADEZDIVKA_X, HOUSE_DEPTH), (0, HOUSE_DEPTH),
	wall_type=load_bearing_wall, height=NADEZDIVKA)
wall_1_u = upper.wall(
	(0, HOUSE_DEPTH-BWT), (0, BWT),
	wall_type=load_bearing_wall,
	height=4, cuts=wall_cuts_1, )

EAST_UPPER_WINDOW_WIDTH = 1.0
EAST_UPPER_WINDOW_GAP = 1.0
EAST_UPPER_WINDOW_SILL_HEIGHT = 1.0  # Above the upper-floor start, before finishes.
EAST_UPPER_WINDOW_TOP_HEIGHT = 2.375
east_upper_window_start = (wall_1_u.length - (2*EAST_UPPER_WINDOW_WIDTH + EAST_UPPER_WINDOW_GAP)) / 2
east_upper_windows = tuple(
	wall_1_u.add_window(
		name=f"East upper window {index+1}",
		at=east_upper_window_start + index*(EAST_UPPER_WINDOW_WIDTH+EAST_UPPER_WINDOW_GAP),
		width=EAST_UPPER_WINDOW_WIDTH, sill_height=EAST_UPPER_WINDOW_SILL_HEIGHT,
		height=EAST_UPPER_WINDOW_TOP_HEIGHT, color="#ffffff",
	)
	for index in range(2)
)

wall_2 = upper.wall(
	(wall2_x, BWT), (wall2_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=INNER_SUPPORT_WALL_HEIGHT)

wall_3 = upper.wall(
	(wall3_x, BWT), (wall3_x, HOUSE_DEPTH-BWT),
	cuts=wall_cuts_2_3,
	wall_type=load_bearing_wall, height=INNER_SUPPORT_WALL_HEIGHT)

sklad_opening = wall_3.add_opening(
    at=wall_zachod_nahore_y - BWT,
    width=1,
    height=2.25,
)


wall_pokoj2 = upper.wall(
	start=(wall2_x, GALERY_END),
	end=(wall3_x-BWT, GALERY_END),
	wall_type=dry_wall, height=2.85)
UPPER_DOOR_HEIGHT = 2.25
pokoj2_door = wall_pokoj2.add_door(
	at=0.125,
	opening_width=1, width=0.9,
	height=UPPER_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
wall_zachod_nahore = upper.wall(
	start=(WEST_CLOSURE_INNER_X, wall_zachod_nahore_y),
	end=(wall3_x, wall_zachod_nahore_y),
	wall_type=dry_wall, height=2.0)
wall_za_umyvadlem = upper.wall(
	start=(WEST_CLOSURE_INNER_X, wall_za_umyvadlem_y),
	end=(wall3_x, wall_za_umyvadlem_y),
	wall_type=dry_wall, height=wall_zachod_nahore.height)
upper.asset(
    "WC",
    asset="toilet_without_cistern",
	start_height=GROUND_FLOOR_THICKNESS,
    center=(wall3_x + 0.5, wall_zachod_nahore_y - 0.1 - 1.0),
    rotation=180,
)
upper.asset(
    "Umyv",
    asset="basin_large",
    center=(wall3_x + 0.5, wall_zachod_nahore_y+1.0+0.35),
	start_height=UPPER_FLOOR_THICKNESS + 0.85 - 0.25,
#	rotation=180,
)

#upper.connect_wall(wall_1_u, wall_back1_u)
#
#upper.connect_wall(wall_2, wall_front1_u, is_atpath=True)
#upper.connect_wall(wall_2, wall_back1_u, is_atpath=True)
#upper.connect_wall(wall_2, wall_dormer)
#
#upper.connect_wall(wall_3, wall_front1_u, is_atpath=True)
#upper.connect_wall(wall_3, wall_back1_u, is_atpath=True)
#upper.connect_wall(wall_3, wall_dormer)
#


PURLIN_TOP_Z = (
	UPPER_FLOOR_START + PURLIN_WALL_TOP_HEIGHT + VAZNICE_HEIGHT
)
# Two independent high-roof pieces; the middle ones overhang wall3 and end
# at the remaining roof boundary. These are not connected Gerber segments.
PURLIN_X_SEGMENTS = (
	("left", -0.2, MIDDLE_PURLIN_X_MIN, VAZNICE_SIDE_HEIGHT),
	(
		"middle",
		MIDDLE_PURLIN_X_MIN,
		LOWER_NADEZDIVKA_X - 0.05,
		VAZNICE_HEIGHT,
	),
)
PURLIN_SECTION_DIMENSIONS = {
	"left": (VAZNICE_SIDE_BASE, VAZNICE_SIDE_HEIGHT, VAZNICE_SIDE_DIST),
	"middle": (VAZNICE_BASE, VAZNICE_HEIGHT, VAZNICE_DIST),
}
# Bottom of the MIDDLE pieces (and top of the unchanged inner walls).
PURLIN_BOTTOM_Z = PURLIN_TOP_Z - VAZNICE_HEIGHT
PURLIN_SECTION_BOTTOM_Z = {
	"left": PURLIN_TOP_Z - VAZNICE_SIDE_HEIGHT,
	"middle": PURLIN_BOTTOM_Z,
}
# One horizontal barrier level throughout, at the top of the inner support walls.
FLAT_VAPOUR_BARRIER_TOP_Z = UPPER_FLOOR_START + INNER_SUPPORT_WALL_HEIGHT
# Paired boards sit directly above the purlins. These dimensions do not move
# the separately defined insulation, vapour barrier or plasterboard ceiling.
COLLAR_TIE_BOTTOM_HEIGHT = PURLIN_TOP_Z - UPPER_FLOOR_START
COLLAR_TIE_TOP_HEIGHT = COLLAR_TIE_BOTTOM_HEIGHT + COLLAR_TIE_SIZE[1]


def framing_is_lower(x):
	"""Only the high roof remains; the former low bay has no framing."""
	return False


def purlin_segment_at(x):
	"""Select the high or low support explicitly where their X spans overlap."""
	return "middle" if x >= MIDDLE_PURLIN_X_MIN else "left"


def purlin_bottom_z_at(x):
	return PURLIN_SECTION_BOTTOM_Z[purlin_segment_at(x)]


def purlin_dimensions_at(x):
	"""Return width, height and ridge distance for the piece at logical X."""
	return PURLIN_SECTION_DIMENSIONS[purlin_segment_at(x)]


def purlin_top_z_at(x):
	return purlin_bottom_z_at(x) + purlin_dimensions_at(x)[1]


def purlin_at(x, *, side):
	if side not in {"street", "garden"}:
		raise ValueError("purlin side must be street or garden")
	pieces = street_purlins if side == "street" else garden_purlins
	beam = pieces[{"left": 0, "middle": 1}[purlin_segment_at(x)]]
	if not min(beam.start[0], beam.end[0]) - 1e-9 <= x <= max(beam.start[0], beam.end[0]) + 1e-9:
		raise ValueError(f"selected {side} purlin does not reach framing at x={x:g}")
	return beam


def purlin_outer_face_y_at(x, *, side):
	width, _, distance = purlin_dimensions_at(x)
	if side not in {"street", "garden"}:
		raise ValueError("purlin side must be 'street' or 'garden'")
	return HALF_DEPTH + (-1 if side == "street" else 1) * (distance + width / 2)


def add_purlin_segments(name, *, side):
	"""Add high left/middle pieces and independently positioned lower right pieces."""
	segments = []
	if side not in {"street", "garden"}:
		raise ValueError("purlin side must be 'street' or 'garden'")
	for segment_name, x_start, x_end, height in PURLIN_X_SEGMENTS:
		width, _, distance = PURLIN_SECTION_DIMENSIONS[segment_name]
		center_z = PURLIN_SECTION_BOTTOM_Z[segment_name] + height / 2
		y = HALF_DEPTH + (-1 if side == "street" else 1) * distance
		segments.append(upper.beam(
			f"{name} purlin {segment_name}",
			start=(x_start, y, center_z),
			end=(x_end, y, center_z),
			size=(width, height),
			material="Wood",
			kind="BEAM",
		))
	return tuple(segments)


street_purlins = add_purlin_segments(
	"Street",
	side="street",
)
garden_purlins = add_purlin_segments(
	"Garden",
	side="garden",
)


def add_purlin_packing_blocks():
	"""Support the high left pieces; lowered right pieces enter the uncut wall."""
	blocks = []
	if PURLIN_SIDE_PACKING_HEIGHT == 0:
		return tuple(blocks)
	center_z = PURLIN_BOTTOM_Z + PURLIN_SIDE_PACKING_HEIGHT / 2
	for side, direction in (("Street", -1), ("Garden", 1)):
		y = HALF_DEPTH + direction * VAZNICE_SIDE_DIST
		blocks.append(upper.beam(
			f"{side} left purlin packing block",
			start=(MIDDLE_PURLIN_X_MIN - PURLIN_SIDE_PACKING_LENGTH, y, center_z),
			end=(MIDDLE_PURLIN_X_MIN, y, center_z),
			size=(VAZNICE_SIDE_BASE, PURLIN_SIDE_PACKING_HEIGHT),
			material="Wood",
			kind="BEAM",
		))
	return tuple(blocks)


purlin_packing_blocks = add_purlin_packing_blocks()


beam3 = upper.beam(
    "Beam",
	start=(-0.2, STREET_WALL_PLATE_Y, STREET_WALL_PLATE_Z),
	end=(LOWER_NADEZDIVKA_X - 0.05, STREET_WALL_PLATE_Y, STREET_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="WALL_PLATE",
)
beam4_a = upper.beam(
    "Beam",
	start=(-0.2, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
	end=(wall2_x-BWT, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="WALL_PLATE",
)
beam4_b = upper.beam(
    "Beam",
	start=(wall3_x, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
	end=(LOWER_NADEZDIVKA_X - 0.05, GARDEN_WALL_PLATE_Y, GARDEN_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="WALL_PLATE",
)
beam_dormer = upper.beam(
    "Beam",
	start=(wall3_x+0.2, GARDEN_WALL_PLATE_Y, DORMER_WALL_PLATE_Z),
	end=(wall2_x-BWT-0.2, GARDEN_WALL_PLATE_Y, DORMER_WALL_PLATE_Z),
    size=WALL_PLATE_SIZE,
    material="Wood",
    kind="WALL_PLATE",
)
street_wall_plates = (beam3,)
garden_wall_plates = (beam4_a, beam4_b, beam_dormer)


def add_transverse_roof_supports():
	"""One continuous Y-aligned purlin and a plate seated on wall 4's ring beam."""
	if not math.isfinite(TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR) or TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR <= 0:
		raise ValueError("TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR must be positive and finite")
	bearings = [beam for beam in ring_beams if beam.source_wall == wall_4_g]
	if not bearings:
		raise ValueError("the transverse wall plate needs the ring beam on wall 4")
	x = bearings[0].start[0]
	top = bearings[0].start[2] + bearings[0].height / 2
	if any(not isclose(point[0], x, abs_tol=1e-9)
	       or not isclose(point[2] + beam.height / 2, top, abs_tol=1e-9)
	       for beam in bearings for point in (beam.start, beam.end)):
		raise ValueError("wall 4 ring-beam pieces must share one horizontal bearing line")
	y0 = min(point[1] for beam in bearings for point in (beam.start, beam.end))
	y1 = max(point[1] for beam in bearings for point in (beam.start, beam.end))
	purlin_x = LOWER_NADEZDIVKA_X + 0.125
	purlin_z = (UPPER_FLOOR_START + TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR - VAZNICE_SIDE_HEIGHT / 2)
	purlin = upper.beam(
		"Transverse roof purlin", start=(purlin_x, y0, purlin_z), end=(purlin_x, y1, purlin_z),
		size=(VAZNICE_SIDE_BASE, VAZNICE_SIDE_HEIGHT), material="Wood", kind="BEAM",
	)
	plate_z = top + WALL_PLATE_SIZE[1] / 2
	plate = upper.beam(
		"Transverse wall plate - wall 4", start=(x, y0, plate_z), end=(x, y1, plate_z),
		size=WALL_PLATE_SIZE, material="Wood", kind="WALL_PLATE",
	)
	return purlin, plate


transverse_purlin, transverse_wall_plate = add_transverse_roof_supports()


def wall_plate_at(x, *, side, dormer=False):
	if side == "street":
		plate = beam3
	elif side == "garden":
		if dormer:
			plate = beam_dormer
		else:
			plate = beam4_a if x <= max(beam4_a.start[0], beam4_a.end[0]) else beam4_b
	else:
		raise ValueError("wall plate side must be street or garden")
	if not min(plate.start[0], plate.end[0]) - 1e-9 <= x <= max(plate.start[0], plate.end[0]) + 1e-9:
		raise ValueError(f"selected {side} wall plate does not reach framing at x={x:g}")
	return plate

# Chodba nahore
upper.furniture(
    "Rekuperace",
    kind="USERDEFINED",
    size=(1, 0.5, 1.5),
    color="#ffff00",
    center=(HOUSE_WIDTH-BWT-0.3, wall_zachod_nahore_y-0.7),
	rotation=90,
	start_height=UPPER_FLOOR_THICKNESS,
)

# Okna obyvak
window_dormer_1 = wall_dormer.add_window(
	at=BWT+0.25,width=1.375, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
window_dormer_2 = wall_dormer.add_window(
	at=BWT+KITCHEN_WIDTH-0.25-1.375,
	width=1.375, sill_height=NADEZDIVKA, height=DORMER_WALL_HEIGHT-0.25)
# Dvere pokojik 1 nahore
pokoj1_door = wall_2.add_door(
	at=math.ceil((GALERY_START-BWT)/0.125)*0.125,
	opening_width=1, width=0.9,
	height=UPPER_DOOR_HEIGHT,
	clear_height=door_clear_height,
	sill_height=UPPER_FLOOR_THICKNESS,
	operation="SINGLE_SWING_LEFT")
# A level concrete band through the HIGH upper load-bearing walls, below
# the normal wall plates and dormer windows. Low wall parts lie entirely
# outside the remaining upper perimeter; no low-level ring beam is added.
# Openings interrupt concrete and bars. All roof support levels stay unchanged.
upper_ring_beams = upper.add_ring_beams_from(
	upper,
	source_wall_type=load_bearing_wall,
	height=UPPER_RING_BEAM_HEIGHT,
	start_height=NADEZDIVKA-UPPER_RING_BEAM_HEIGHT,
	replace_wall_band=True,
	concrete_material="Concrete topping",
	reinforcement_material="Ring beam reinforcement",
	bar_diameter=RING_BEAM_BAR_DIAMETER,
	stirrup_diameter=RING_BEAM_STIRRUP_DIAMETER,
	concrete_cover=RING_BEAM_CONCRETE_COVER,
)

# No upper west gable or knee walls in the former low-roof bay.

# Roof

roof = upper.roof("Main roof")

# Exact vertical chimney footprint; clearance/flashing design is separate.
chimney_roof_opening = roof.add_opening(
	name="Chimney roof penetration",
	rectangle=(
		(chimney.center[0] - chimney.size/2, chimney.center[1] - chimney.size/2),
		(chimney.center[0] + chimney.size/2, chimney.center[1] + chimney.size/2),
	),
	trimmers=False,
	vertical=True,
)

ROOF_WINDOW_Y1 = HOUSE_DEPTH - BWT - 0.25
roof_window_x = (rafters[2] + rafters[3]) / 2.0
roof_window_opening = roof.add_opening(
	name="Bedroom roof window",
	rectangle=(
		(roof_window_x-0.39, ROOF_WINDOW_Y1),
		(roof_window_x+0.39, ROOF_WINDOW_Y1 - 1.2),
	),
	trimmers=False,
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

ROOF_EAVE_OVERHANG = 0.75
DORMER_ROOF_EAVE_OVERHANG = 0.5
ROOF_EAVE_SETBACK = 0.02  # Shared eave and X-end allowance for roof siding.
ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.30
DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.0
for overhang in (ROOF_EAVE_OVERHANG, DORMER_ROOF_EAVE_OVERHANG):
	if not math.isfinite(overhang) or overhang <= 0:
		raise ValueError("roof eave overhangs must be positive and finite")
for drop in (ROOF_EAVE_DROP_BELOW_WALL_PLATE, DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE):
	if not math.isfinite(drop) or drop < 0:
		raise ValueError("roof eave drops must be non-negative and finite")
if not math.isfinite(ROOF_EAVE_SETBACK) or not 0 <= ROOF_EAVE_SETBACK < min(ROOF_EAVE_OVERHANG, DORMER_ROOF_EAVE_OVERHANG):
	raise ValueError("ROOF_EAVE_SETBACK must be finite, non-negative and less than both roof eave overhangs")
STREET_ROOF_EAVE_Y = -ROOF_EAVE_OVERHANG
GARDEN_ROOF_EAVE_Y = HOUSE_DEPTH + ROOF_EAVE_OVERHANG
DORMER_ROOF_EAVE_Y = HOUSE_DEPTH + DORMER_ROOF_EAVE_OVERHANG
TRANSVERSE_ROOF_EAVE_X = HOUSE_WIDTH + ROOF_EAVE_OVERHANG


def horizontal_roof_eave_cut(wall_plate_center_z, *, drop=None):
	"""Trim below the plate underside; main and dormer drops are independent."""
	if drop is None:
		drop = ROOF_EAVE_DROP_BELOW_WALL_PLATE
	z = wall_plate_center_z - WALL_PLATE_SIZE[1] / 2 - drop
	return ((0, 0, z), (10, 0, z), (0, 10, z))


def roof_eave_setback_cuts(plane):
	"""Inset vertical eave cuts; leave horizontal and ridge cuts untouched."""
	if ROOF_EAVE_SETBACK == 0:
		return ()
	cuts = []
	for cut in plane.cuts:
		if (max(p[0] for p in cut) - min(p[0] for p in cut) <= 1e-9
		    and isclose(cut[0][0], TRANSVERSE_ROOF_EAVE_X, abs_tol=1e-9)):
			x = TRANSVERSE_ROOF_EAVE_X - ROOF_EAVE_SETBACK
			cuts.append(((x, 0, 0), (x, 10, 0), (x, 0, 10)))
			continue
		if max(p[1] for p in cut) - min(p[1] for p in cut) > 1e-9:
			continue
		y = cut[0][1]
		if isclose(y, STREET_ROOF_EAVE_Y, abs_tol=1e-9):
			y += ROOF_EAVE_SETBACK
		elif any(isclose(y, end, abs_tol=1e-9) for end in (GARDEN_ROOF_EAVE_Y, DORMER_ROOF_EAVE_Y)):
			y -= ROOF_EAVE_SETBACK
		else:
			continue
		cuts.append(((0, y, 0), (10, y, 0), (0, y, 10)))
	return tuple(cuts)


street_roof = roof.plane(
    "Street slope",
	points=STREET_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		horizontal_roof_eave_cut(STREET_WALL_PLATE_Z),
		((0, STREET_ROOF_EAVE_Y, 0), (10, STREET_ROOF_EAVE_Y, 0), (0, STREET_ROOF_EAVE_Y, 10)),
	],
)
garden_roof = roof.plane(
    "Garden slope",
	points=GARDEN_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		horizontal_roof_eave_cut(GARDEN_WALL_PLATE_Z),
		((0, GARDEN_ROOF_EAVE_Y, 0), (10, GARDEN_ROOF_EAVE_Y, 0), (0, GARDEN_ROOF_EAVE_Y, 10)),
	],
)
dormer_roof = roof.plane(
    "Dormer slope",
	points=DORMER_ROOF_PLANE_POINTS,
    cuts=[
		((0, HALF_DEPTH, 0), (10, HALF_DEPTH, 0), (0, HALF_DEPTH, 10)),
		horizontal_roof_eave_cut(DORMER_WALL_PLATE_Z, drop=DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE),
		(
			(0, DORMER_ROOF_EAVE_Y, 0),
			(10, DORMER_ROOF_EAVE_Y, 0),
			(0, DORMER_ROOF_EAVE_Y, 10),
		),
	],
)
# Only the structural dormer rafters continue across the ridge-side void.
# Replace their vertical ridge boundary with the opposite main-rafter upper face;
# the dormer roof layers and counter-battens retain their original boundaries.
dormer_rafter_roof = roof.plane(
	"Dormer rafter slope",
	points=DORMER_ROOF_PLANE_POINTS,
	cuts=(
		offset_plane(*STREET_ROOF_PLANE_POINTS, offset=RAFTER_Z_OFFSET + RAFTER_HEIGHT),
		*dormer_roof.cuts[1:],
	),
)
flat_ceiling_roof = roof.plane(
	"Flat ceiling",
	points=FLAT_CEILING_ROOF_PLANE_POINTS,
)
# Independent retained ceiling plane; no lower sloped roof remains.
lower_flat_ceiling_roof = roof.plane(
	"Retained lower flat ceiling",
	points=((0, 0, UPPER_FLOOR_START), (10, 0, UPPER_FLOOR_START), (0, 1, UPPER_FLOOR_START)),
)


def add_transverse_roof_plane():
	"""Pitch through the outer top bearing edges, with the shared eave cuts."""
	purlin_x = transverse_purlin.start[0] + transverse_purlin.width / 2
	purlin_top = transverse_purlin.start[2] + transverse_purlin.height / 2
	plate_x = transverse_wall_plate.start[0] + transverse_wall_plate.width / 2
	plate_top = transverse_wall_plate.start[2] + transverse_wall_plate.height / 2
	if plate_x <= purlin_x or purlin_top <= plate_top:
		raise ValueError("transverse purlin must be higher than and inward of the wall plate")
	return roof.plane(
		"Transverse slope",
		points=((purlin_x, 0, purlin_top), (purlin_x, 10, purlin_top), (plate_x, 0, plate_top)),
		cuts=(
			((LOWER_NADEZDIVKA_X, 0, 0), (LOWER_NADEZDIVKA_X, 10, 0), (LOWER_NADEZDIVKA_X, 0, 10)),
			horizontal_roof_eave_cut(transverse_wall_plate.start[2]),
			((TRANSVERSE_ROOF_EAVE_X, 0, 0), (TRANSVERSE_ROOF_EAVE_X, 10, 0), (TRANSVERSE_ROOF_EAVE_X, 0, 10)),
		),
	)


transverse_roof = add_transverse_roof_plane()


def framing_roof_planes_at(x):
	return street_roof, garden_roof


def roof_batting_point(
	plane,
	*,
	x,
	y,
	center_offset=ROOF_BATTING_CENTER_OFFSET,
):
	"""Return a world point on an offset roof-layer centre plane."""
	batting_plane = offset_plane(
		*plane.points,
		offset=center_offset,
	)
	return (
		x,
		y,
		plane_height_at(*batting_plane, x=x, y=y),
	)


def roof_batting_local_point(
	plane,
	*,
	x,
	local_y,
	center_offset,
):
	"""Return a world point using a modeled roof layer's local Y limit."""
	return tuple(plane.to_world((x, local_y, center_offset)))


def roof_batting_intersection(
	first_plane,
	second_plane,
	*,
	x,
	center_offset=ROOF_BATTING_CENTER_OFFSET,
):
	"""Intersect two offset roof-layer centre planes in a vertical X section."""
	reference_y = HALF_DEPTH
	first_at_reference = roof_batting_point(
		first_plane,
		x=x,
		y=reference_y,
		center_offset=center_offset,
	)[2]
	second_at_reference = roof_batting_point(
		second_plane,
		x=x,
		y=reference_y,
		center_offset=center_offset,
	)[2]
	first_slope = (
		roof_batting_point(
			first_plane,
			x=x,
			y=reference_y + 1,
			center_offset=center_offset,
		)[2]
		- first_at_reference
	)
	second_slope = (
		roof_batting_point(
			second_plane,
			x=x,
			y=reference_y + 1,
			center_offset=center_offset,
		)[2]
		- second_at_reference
	)
	slope_delta = first_slope - second_slope
	if abs(slope_delta) <= 1e-9:
		raise ValueError("roof batting planes must not be parallel")
	intersection_y = reference_y + (
		(second_at_reference - first_at_reference) / slope_delta
	)
	return roof_batting_point(
		first_plane,
		x=x,
		y=intersection_y,
		center_offset=center_offset,
	)


def inset_roof_batting_segment(
	start,
	end,
	*,
	end_inset=ROOF_BATTING_END_INSET,
):
	"""Keep batting loops clear of wall, ridge, and roof-joint outlines."""
	delta = tuple(end_value - start_value for start_value, end_value in zip(start, end))
	length = math.sqrt(sum(value * value for value in delta))
	if length <= 2 * end_inset:
		raise ValueError("roof batting segment is too short for its end insets")
	direction = tuple(value / length for value in delta)
	return (
		tuple(
			value + axis * end_inset
			for value, axis in zip(start, direction)
		),
		tuple(
			value - axis * end_inset
			for value, axis in zip(end, direction)
		),
	)


def roof_angle_degrees(plane):
	"""Return a roof plane's acute pitch angle above horizontal."""
	normal_z = min(1.0, max(-1.0, abs(plane.z_axis[2])))
	return degrees(acos(normal_z))


def rafter_support_span(plane, first_support_y, second_support_y):
	"""Return the rafter distance between two support centrelines."""
	first_support = roof_batting_point(
		plane,
		x=0,
		y=first_support_y,
	)
	second_support = roof_batting_point(
		plane,
		x=0,
		y=second_support_y,
	)
	return math.dist(first_support, second_support)


street_roof_angle = roof_angle_degrees(street_roof)
garden_roof_angle = roof_angle_degrees(garden_roof)
dormer_roof_angle = roof_angle_degrees(dormer_roof)
transverse_roof_angle = roof_angle_degrees(transverse_roof)
if not isclose(street_roof_angle, garden_roof_angle, abs_tol=1e-9):
	raise ValueError("street and garden roof angles must match")
street_rafter_span = rafter_support_span(
	street_roof,
	STREET_WALL_PLATE_Y,
	HALF_DEPTH - VAZNICE_DIST,
)
garden_rafter_span = rafter_support_span(
	garden_roof,
	HALF_DEPTH + VAZNICE_DIST,
	GARDEN_WALL_PLATE_Y,
)
if not isclose(street_rafter_span, garden_rafter_span, abs_tol=1e-9):
	raise ValueError("street and garden rafter support spans must match")
dormer_rafter_span = rafter_support_span(
	dormer_roof,
	HALF_DEPTH + VAZNICE_DIST,
	GARDEN_WALL_PLATE_Y,
)
street_rafter_length_above_purlin = rafter_support_span(
	street_roof,
	HALF_DEPTH - VAZNICE_DIST,
	HALF_DEPTH,
)
garden_rafter_length_above_purlin = rafter_support_span(
	garden_roof,
	HALF_DEPTH,
	HALF_DEPTH + VAZNICE_DIST,
)
if not isclose(
	street_rafter_length_above_purlin,
	garden_rafter_length_above_purlin,
	abs_tol=1e-9,
):
	raise ValueError(
		"street and garden rafter lengths above the purlin must match"
	)
purlin_support_spans = (
	wall2_x,
	wall3_x - wall2_x,
)
print(
	f"Main roof angle: {street_roof_angle:.2f}° "
	f"({100 * math.tan(math.radians(street_roof_angle)):.2f}%)"
)
print(
	f"Dormer roof angle: {dormer_roof_angle:.2f}° "
	f"({100 * math.tan(math.radians(dormer_roof_angle)):.2f}%)"
)
print(
	f"Transverse roof angle: {transverse_roof_angle:.2f}° "
	f"({100 * math.tan(math.radians(transverse_roof_angle)):.2f}%)"
)
print("Rafter load inputs (support centreline to centreline):")
print(f"  SUPPORT_SPAN_M = {street_rafter_span:.3f}")
print(f"  ROOF_ANGLE_DEGREES = {street_roof_angle:.2f}")
print(f"  DORMER_SUPPORT_SPAN_M = {dormer_rafter_span:.3f}")
print(f"  DORMER_ROOF_ANGLE_DEGREES = {dormer_roof_angle:.2f}")
print(
	f"  RAFTER_LENGTH_ABOVE_PURLIN_M = "
	f"{street_rafter_length_above_purlin:.3f}"
)
print(
	"  PURLIN_SPANS_M = ("
	+ ", ".join(f"{span:.3f}" for span in purlin_support_spans)
	+ ")"
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
	"MDF": house.storey(
		"Roof - +1: MDF", elevation=upper.elevation),
	"Roofing underlay": house.storey("Roof - +2: Underlay", elevation=upper.elevation),
	"Counter-battens": house.storey("Roof - +3: Counter-battens", elevation=upper.elevation),
	"Tile battens": house.storey("Roof - +4: Tile battens", elevation=upper.elevation),
	"Roof tiles": house.storey("Roof - +5: Tiles", elevation=upper.elevation),
	"Roof windows": house.storey("Roof - +6: Windows", elevation=upper.elevation),
	"Eave siding": house.storey("Roof - Eave siding", elevation=upper.elevation),
	"Sloped siding": house.storey("Roof - Sloped siding", elevation=upper.elevation),
})
roof_under_rafter_insulations = {}
for layer_name, layer_storey in roof_layer_storeys.items():
	layer_storey.element.ObjectType = "ROOF_LAYER"
	layer_storey.element.Description = f"Visibility container for {layer_name}"


def wood_siding_color(*, patterned=False):
	"""Match the independent plain/patterned drawing colors in the IFC."""
	if not patterned:
		stylesheet = (Path(__file__).parent / "bonsai_scripts/assets/plan.css").read_text(encoding="utf-8")
		return re.search(r"\.material-Woodsidingsolid\.surface\s*\{[^}]*?\bfill:\s*([^;\s]+)", stylesheet)[1]
	patterns = ET.parse(Path(__file__).parent / "drawings/assets/patterns.svg").getroot()
	siding = next(p for p in patterns if p.get("id") == "wood-siding")
	return siding.find("{http://www.w3.org/2000/svg}rect").get("fill")


# The under-rafter insulation follows each occupied roof slope only as far as
# the outer vertical face of the purlin. The vapour barrier and plasterboard transition
# onto the horizontal ceiling, whose exceptional heights are described
# relative to the upper-storey floor.
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
	"Vapour barrier": (
		FLAT_VAPOUR_BARRIER_TOP_Z - UPPER_FLOOR_START - VAPOUR_BARRIER_THICKNESS,
		FLAT_VAPOUR_BARRIER_TOP_Z - UPPER_FLOOR_START,
	),
	# The horizontal plasterboard remains on its lower suspended-ceiling plane;
	# the space between it and the vapour barrier is the ceiling/service void.
	"Gypsum plasterboard": (
		UPPER_FLOOR_THICKNESS + 2.6,
		UPPER_FLOOR_THICKNESS + 2.6 +  GYPSUM_PLASTERBOARD_THICKNESS,
	),
}
FLAT_CEILING_INNER_LAYER_LAYOUT = {
	layer_name: (
		UPPER_FLOOR_START + bottom - ROOF_JOINT_Z,
		top - bottom,
	)
	for layer_name, (bottom, top) in FLAT_CEILING_LAYER_HEIGHTS.items()
}
LOWER_FLAT_CEILING_LAYER_HEIGHTS = {
	"Vapour barrier": (
		LOWER_VAPOUR_BARRIER_TOP_HEIGHT - VAPOUR_BARRIER_THICKNESS,
		LOWER_VAPOUR_BARRIER_TOP_HEIGHT,
	),
	"Gypsum plasterboard": (
		UPPER_FLOOR_THICKNESS + LOWER_CEILING_CLEAR_HEIGHT,
		UPPER_FLOOR_THICKNESS + LOWER_CEILING_CLEAR_HEIGHT + GYPSUM_PLASTERBOARD_THICKNESS,
	),
}
if not math.isfinite(LOWER_CEILING_CLEAR_HEIGHT) or LOWER_CEILING_CLEAR_HEIGHT <= 0:
	raise ValueError("LOWER_CEILING_CLEAR_HEIGHT must be positive and finite")
if LOWER_FLAT_CEILING_LAYER_HEIGHTS["Gypsum plasterboard"][1] > LOWER_FLAT_CEILING_LAYER_HEIGHTS["Vapour barrier"][0]:
	raise ValueError("lower plasterboard ceiling must fit below the vapour barrier")
LOWER_FLAT_CEILING_INNER_LAYER_LAYOUT = {
	layer_name: (bottom, top - bottom)
	for layer_name, (bottom, top) in LOWER_FLAT_CEILING_LAYER_HEIGHTS.items()
}
# Preserve the existing horizontal ceiling footprints without roof slopes.
LOWER_CEILING_Y_LIMITS = {
	"Vapour barrier": (HALF_DEPTH - 0.996266844889948, HALF_DEPTH + 0.996266844889948),
	"Gypsum plasterboard": (HALF_DEPTH - 1.0100002003806446, HALF_DEPTH + 1.0100002003806446),
}
UNDERLAY_BOTTOM = MDF_BOTTOM + MDF_THICKNESS
COUNTER_BATTEN_BOTTOM = UNDERLAY_BOTTOM + UNDERLAY_THICKNESS
TILE_BATTEN_BOTTOM = COUNTER_BATTEN_BOTTOM + COUNTER_BATTEN_SIZE[1]
ROOF_TILE_BOTTOM = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1]

rafter_layout = []
# The collar board on the dormer side must sit outside the touching pair,
# rather than in the space occupied by the adjacent dormer rafter.
paired_rafter_dormer_offsets = {}
collar_tie_min_y = {}
for rafter in rafters:
	if isinstance(rafter, SplitRafter):
		if not any(
			x_min < rafter.x < x_max and y_min < rafter.y < y_max
			for opening in roof.openings
			for (x_min, y_min), (x_max, y_max) in (opening.rectangle,)
		):
			raise ValueError(
				"SplitRafter position must be inside a registered roof opening"
			)
		rafter_layout.append((rafter.x, "main", False, rafter.y, False))
		continue
	if isinstance(rafter, StrongerRafter):
		rafter_layout.append((rafter.x, "main", False, None, True))
		continue
	if not isinstance(rafter, tuple):
		rafter_layout.append((rafter, "main", False, None, False))
		continue

	min_y = rafter_collar_min_y(rafter)
	rafter_x, dormer_side = rafter[:2]
	if min_y is not None:
		collar_tie_min_y[rafter_x] = min_y
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
	# Collar clearance is needed for both shortened and full-length (+) pairs.
	paired_rafter_dormer_offsets[rafter_x] = dormer_offset
	rafter_layout.extend(
		(
			(rafter_x, "main", shorten_garden_side, None, False),
			(rafter_x + dormer_offset, "dormer", False, None, False),
		)
	)

rafter_layout.sort(key=lambda entry: entry[0])
main_rafter_sections = [
	(
		x,
		STRONGER_RAFTER_THICKNESS if is_stronger else RAFTER_THICKNESS,
	)
	for x, kind, _, _, is_stronger in rafter_layout
	if kind == "main"
]
main_rafter_positions = [x for x, _ in main_rafter_sections]
# Associate offset ties and paired dormer members with their MAIN rafter line,
# rather than guessing ownership from proximity to the section camera.
rafter_assemblies = {x: [] for x in main_rafter_positions}
paired_dormer_owners = {x + offset: x for x, offset in paired_rafter_dormer_offsets.items()}


for x, kind, _, _, stronger in rafter_layout:
	parent_x = paired_dormer_owners[x] if kind == "dormer" else x
	if kind == "dormer" and framing_is_lower(parent_x):
		raise ValueError("dormer pairs must be in high_rafters; there is no lower dormer roof plane")
	if kind == "main":
		# A chosen level must still have physical supports at this X. The
		# independent layer/wall boundary may pass through offset collar boards.
		for side in ("street", "garden"):
			purlin_at(x, side=side)
		wall_plate_at(x, side="street")


def touching_rafter_sides(sections):
	"""Find touching main rafters within each level, ignoring the other level."""
	blocked_sides = set()
	for lower in (False, True):
		local_sections = sorted((x, width) for x, width in sections if framing_is_lower(x) == lower)
		for (left_x, left_width), (right_x, right_width) in zip(local_sections, local_sections[1:]):
			if isclose(right_x - left_x, (left_width + right_width) / 2,
					   rel_tol=0, abs_tol=1e-9):
				blocked_sides.update(((left_x, "right"), (right_x, "left")))
	return blocked_sides


def add_collar_ties():
	"""Two flanking boards per main-rafter pair, optionally trimmed at min_y."""
	# Offset dormer rafters do not suppress a board or create another pair.
	blocked_sides = touching_rafter_sides(main_rafter_sections)
	ties = []
	for index, (x, rafter_width) in enumerate(main_rafter_sections, start=1):
		street_plane, garden_plane = framing_roof_planes_at(x)
		cuts = tuple(offset_plane(*plane.points, offset=RAFTER_Z_OFFSET + RAFTER_HEIGHT)
			for plane in (street_plane, garden_plane))
		start_y = max(street_plane.origin[1] - COLLAR_TIE_EXTENSION,
		              collar_tie_min_y.get(x, float("-inf")))
		end_y = garden_plane.origin[1] + COLLAR_TIE_EXTENSION
		if start_y >= end_y:
			raise ValueError(f"collar min_y leaves no board length at rafter x={x:g}")
		x_offset = (rafter_width + COLLAR_TIE_THICKNESS) / 2
		for side, offset in (("left", -x_offset), ("right", x_offset)):
			if (x, side) in blocked_sides:
				continue
			dormer_offset = paired_rafter_dormer_offsets.get(x, 0)
			if offset * dormer_offset > 0:
				# Shift this entire board by one rafter width to the outer
				# face of the dormer rafter; the opposite board stays put.
				offset += dormer_offset
			centre_z = purlin_top_z_at(x) + COLLAR_TIE_SIZE[1] / 2
			tie = upper.beam(
				f"Collar tie {index} {side}",
				start=(x + offset, start_y, centre_z),
				end=(x + offset, end_y, centre_z),
				size=COLLAR_TIE_SIZE,
				material="Wood",
				kind="BEAM",
				cuts=cuts,
			)
			roof_layer_storeys["Collar ties"].add(tie)
			rafter_assemblies[x].append(tie)
			ties.append(tie)
	return tuple(ties)


collar_ties = add_collar_ties()
# One transverse spacer for each main-rafter line. Paired dormer rafters lie
# outside the purlins and do not need a second spacer at their offset X.
purlin_spacers = tuple(
	upper.beam(
		f"Purlin spacer {index}",
		start=(
			x, HALF_DEPTH - purlin_dimensions_at(x)[2] + purlin_dimensions_at(x)[0] / 2,
			purlin_top_z_at(x) - PURLIN_SPACER_SIZE[1] / 2,
		),
		end=(
			x, HALF_DEPTH + purlin_dimensions_at(x)[2] - purlin_dimensions_at(x)[0] / 2,
			purlin_top_z_at(x) - PURLIN_SPACER_SIZE[1] / 2,
		),
		size=PURLIN_SPACER_SIZE,
		material="Wood",
		kind="BEAM",
	)
	for index, x in enumerate(main_rafter_positions, start=1)
)
for x, spacer in zip(main_rafter_positions, purlin_spacers):
	rafter_assemblies[x].append(spacer)
dormer_rafter_positions = [
	x for x, kind, _, _, _ in rafter_layout if kind == "dormer"
]
main_rafter_thicknesses = dict(main_rafter_sections)
dormer_x_min = min(dormer_rafter_positions)
dormer_x_max = max(dormer_rafter_positions)

ROOF_X_OVERHANG = 0.25
# Transverse roof: overhang past both street/garden walls in global Y.
TRANSVERSE_ROOF_Y_OVERHANG = 0.25
if not math.isfinite(TRANSVERSE_ROOF_Y_OVERHANG) or TRANSVERSE_ROOF_Y_OVERHANG < 0:
	raise ValueError("TRANSVERSE_ROOF_Y_OVERHANG must be non-negative and finite")
# Authoritative layer X extents: inner finishes stop at the room boundaries;
# tiles use their separately specified overhangs; boards and battens below
# them leave ROOF_EAVE_SETBACK at each X end. Neither range list is split or
# extended to match purlin joints.
roof_under_rafter_x_ranges = (
	(BWT, wall2_x-BWT, "normal"),
	(wall2_x, wall3_x-BWT, "dormer"),
	(wall3_x, LOWER_NADEZDIVKA_X - 0.25, "normal"),
)
roof_over_rafter_x_ranges = (
	(-ROOF_X_OVERHANG, wall2_x-BWT-FACADE_INSULATION_THICKNESS, "normal"),
	(wall2_x-BWT-ROOF_X_OVERHANG, wall3_x+ROOF_X_OVERHANG, "dormer"),
	(wall3_x+FACADE_INSULATION_THICKNESS, LOWER_NADEZDIVKA_X, "normal"),
)


def validate_roof_layer_ranges(ranges, *, allow_overlap=False):
	"""Validate explicit profiles; only exterior layer ranges may overlap."""
	intervals = []
	for x_min, x_max, profile in ranges:
		if profile not in ({"normal", "dormer"} if allow_overlap else {"normal", "dormer", "ceiling"}):
			raise ValueError(f"unknown roof layer profile: {profile!r}")
		if not all(math.isfinite(x) for x in (x_min, x_max)) or x_min >= x_max:
			raise ValueError("roof layer ranges need finite x_min < x_max")
		intervals.append((x_min, x_max))
	if not allow_overlap:
		ordered = sorted(intervals)
		if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
			raise ValueError("under-rafter layer ranges must not overlap")


validate_roof_layer_ranges(roof_under_rafter_x_ranges)
validate_roof_layer_ranges(roof_over_rafter_x_ranges, allow_overlap=True)

def roof_under_tile_x_range(x_min, x_max):
	"""Leave the shared siding allowance at BOTH ends of a tile X range."""
	if not all(math.isfinite(x) for x in (x_min, x_max)) or x_min >= x_max:
		raise ValueError("roof X range needs finite x_min < x_max")
	lo, hi = x_min + ROOF_EAVE_SETBACK, x_max - ROOF_EAVE_SETBACK
	if lo >= hi:
		raise ValueError("roof X range is too short for the siding setbacks")
	return lo, hi


roof_inner_profiles = {
	"normal": {
		"street_plane": street_roof, "garden_plane": garden_roof,
		"flat_plane": flat_ceiling_roof, "flat_layout": FLAT_CEILING_INNER_LAYER_LAYOUT,
		"purlin_distance": VAZNICE_SIDE_DIST, "purlin_top_z": PURLIN_TOP_Z,
	},
	"dormer": {
		"street_plane": street_roof, "garden_plane": dormer_roof,
		"flat_plane": flat_ceiling_roof, "flat_layout": FLAT_CEILING_INNER_LAYER_LAYOUT,
		"purlin_distance": VAZNICE_DIST, "purlin_top_z": PURLIN_TOP_Z,
	},
	"ceiling": {
		"flat_plane": lower_flat_ceiling_roof, "flat_layout": LOWER_FLAT_CEILING_INNER_LAYER_LAYOUT,
		"ceiling_only": True,
	},
}


def inner_roof_section_at(x):
	"""Select interior geometry only from the explicit, non-overlapping ranges."""
	matches = [(x_min, index, profile)
		for index, (x_min, x_max, profile) in enumerate(roof_under_rafter_x_ranges)
		if x_min <= x <= x_max]
	if not matches:
		raise ValueError(f"no under-rafter layer range contains x={x:g}")
	# At a shared endpoint prefer the right-hand interval, independent of order.
	_, index, profile = max(matches)
	return index, profile, roof_inner_profiles[profile]


def interior_ceiling_bottom_z_at(x):
	"""Absolute plasterboard underside level for the interior range at X."""
	profile = inner_roof_section_at(x)[2]
	return profile["flat_plane"].to_world(
		(0, 0, profile["flat_layout"]["Gypsum plasterboard"][0])
	)[2]


def exterior_roof_sections_at(x):
	"""Return ALL matching exterior ranges, including intentional overlaps."""
	return tuple((index, profile) for index, (lo, hi, profile) in enumerate(roof_over_rafter_x_ranges)
		if lo <= x <= hi)


def exterior_roof_planes_at(x, *, side):
	"""Distinct visible slope planes; never resolve overlaps by taking the first."""
	if side not in {"street", "garden"}:
		raise ValueError("roof side must be street or garden")
	planes = []
	for _, profile in exterior_roof_sections_at(x):
		if side == "street":
			candidates = (street_roof,)
		else:
			candidates = (garden_roof, dormer_roof) if profile == "dormer" else (garden_roof,)
		for plane in candidates:
			if plane not in planes:
				planes.append(plane)
	return tuple(planes)


def exterior_ridge_planes_at(x):
	"""Ridge pairs at X; the dormer still has the main roof above its joint."""
	pairs = []
	for _, profile in exterior_roof_sections_at(x):
		pair = (street_roof, garden_roof)
		if pair not in pairs:
			pairs.append(pair)
	return tuple(pairs)


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
	include_under_rafter_insulation=True,
	under_rafter_end_y=None,
	include_inner_finishes=True,
	include_vapour_barrier=True,
	include_gypsum=True,
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
		if layer_name == "Thermal insulation under rafters":
			layer_y_min, layer_y_max = y_min, y_max
			if under_rafter_end_y is not None:
				bottom, thickness = inner_layout[layer_name]
				crossings = [
					local_y_at_global_y(plane, under_rafter_end_y, local_z=z)
					for z in (bottom, bottom + thickness)
				]
				# Leave only a short source overlap beyond the cut. The clipping
				# helper keeps the centroid side; a long ridge-side overshoot
				# can otherwise make the layer keep the wrong half.
				if plane.y_axis[2] < 0:
					layer_y_min = max(layer_y_min, min(crossings) - 0.10)
				else:
					layer_y_max = min(layer_y_max, max(crossings) + 0.10)
				# Bound the eave overshoot too: otherwise the source centroid can
				# fall outside the wall cut and retain the outside half instead.
				for cut in (*plane.cuts, *inner_cuts):
					if max(p[1] for p in cut) - min(p[1] for p in cut) > 1e-9:
						continue
					wall_crossings = [
						local_y_at_global_y(plane, cut[0][1], local_z=z)
						for z in (bottom, bottom + thickness)
					]
					if plane.y_axis[2] < 0 and min(wall_crossings) > max(crossings):
						layer_y_max = min(layer_y_max, max(wall_crossings) + 0.10)
					elif plane.y_axis[2] > 0 and max(wall_crossings) < min(crossings):
						layer_y_min = max(layer_y_min, min(wall_crossings) - 0.10)
		elif inner_y_limits is None:
			layer_y_min, layer_y_max = y_min, y_max
		else:
			layer_y_min, layer_y_max = inner_y_limits[layer_name]
		return (
			(x_min, layer_y_min),
			(x_max, layer_y_min),
			(x_max, layer_y_max),
			(x_min, layer_y_max),
		)

	if include_under_rafter_insulation:
		insulation_bottom, insulation_thickness = inner_layout[
			"Thermal insulation under rafters"
		]
		if insulation_thickness > 0:
			insulation_cuts = inner_cuts
			if under_rafter_end_y is not None:
				insulation_cuts = (
					*inner_cuts,
					(
						(0, under_rafter_end_y, 0),
						(1, under_rafter_end_y, 0),
						(0, under_rafter_end_y, 1),
					),
				)
			insulation = plane.layer(
				f"{name} thermal insulation under rafters",
				outline=inner_outline("Thermal insulation under rafters"),
				z_offset=insulation_bottom,
				thickness=insulation_thickness,
				material="Thermal insulation",
				color="#E8D36D",
				extra_cuts=insulation_cuts,
			)
			roof_under_rafter_insulations[name] = insulation
			roof_layer_storeys["Thermal insulation under rafters"].add(
				insulation
			)
	if include_inner_finishes and include_vapour_barrier:
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
	if include_inner_finishes and include_gypsum:
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
		board_x_min, board_x_max = roof_under_tile_x_range(outer_x_min, outer_x_max)
		board_outline = (
			(board_x_min, y_min), (board_x_max, y_min),
			(board_x_max, y_max), (board_x_min, y_max),
		)
		mdf = plane.layer(
			f"{name} MDF",
			outline=board_outline,
			z_offset=MDF_BOTTOM,
			thickness=MDF_THICKNESS,
			material="MDF",
			color="#f2b6d0",
			extra_cuts=roof_eave_setback_cuts(plane),
		)
		roof_layer_storeys["MDF"].add(mdf)
		underlay = plane.layer(
			f"{name} roofing underlay",
			outline=board_outline,
			z_offset=UNDERLAY_BOTTOM,
			thickness=UNDERLAY_THICKNESS,
			material="Roofing underlay",
			color="#3B4148",
			extra_cuts=roof_eave_setback_cuts(plane),
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
		tiles.set_tile_pattern(width=ROOF_TILE_PATTERN_WIDTH, course_length=TILE_BATTEN_SPACING)


def independent_inner_layer_boundaries(
	slope_plane,
	flat_plane,
	flat_layout,
):
	"""Return matching slope/ceiling endpoints for the interior finishes."""
	boundaries = {}
	for layer_name, (flat_bottom, _) in flat_layout.items():
		slope_bottom = SLOPED_INNER_LAYER_LAYOUT[layer_name][0]
		flat_z = flat_plane.to_world((0, 0, flat_bottom))[2]
		slope_origin_z = slope_plane.to_world((0, 0, slope_bottom))[2]
		slope_y = (flat_z - slope_origin_z) / slope_plane.y_axis[2]
		world_boundary = slope_plane.to_world((0, slope_y, slope_bottom))
		flat_y = flat_plane.to_local(world_boundary)[1]
		boundaries[layer_name] = (slope_y, flat_y)
	return boundaries


def local_y_limits_from_cuts(plane, local_z=0, *, eave_setback=False):
	"""Intersect ridge and all eave half-spaces, retaining the roof origin side.

	Main roofs have both vertical and horizontal eaves. At each layer offset,
	the more restrictive boundary wins; extending to the outermost crossing
	would place batten rows beyond the finished roof.
	"""
	lower, upper = -math.inf, math.inf
	for cut in plane.cuts:
		axes = [axis for axis in range(3) if max(p[axis] for p in cut) - min(p[axis] for p in cut) <= 1e-9]
		if len(axes) != 1:
			continue
		axis = axes[0]
		value = cut[0][axis]
		if eave_setback:
			if axis == 0 and isclose(value, TRANSVERSE_ROOF_EAVE_X, abs_tol=1e-9):
				value -= ROOF_EAVE_SETBACK
			elif axis == 1:
				if isclose(value, STREET_ROOF_EAVE_Y, abs_tol=1e-9):
					value += ROOF_EAVE_SETBACK
				elif any(isclose(value, end, abs_tol=1e-9) for end in (GARDEN_ROOF_EAVE_Y, DORMER_ROOF_EAVE_Y)):
					value -= ROOF_EAVE_SETBACK
		direction = plane.y_axis[axis]
		if abs(direction) <= 1e-12:
			continue
		limit = (value - plane.origin[axis] - local_z * plane.z_axis[axis]) / direction
		if (plane.origin[axis] - value) * direction > 0:
			lower = max(lower, limit)
		else:
			upper = min(upper, limit)
	if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
		raise ValueError(f"{plane.Name} must have a bounded local-Y span inside its ridge/eave cuts")
	return lower, upper


def exterior_source_y_limits(plane, *, y_min=None, y_max=None):
	"""Small, thickness-aware source overshoots keep the intended cut side."""
	limits = [local_y_limits_from_cuts(plane, z) for z in
		(MDF_BOTTOM, ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS)]
	lo = min(limit[0] for limit in limits) - 0.10 if y_min is None else y_min
	hi = max(limit[1] for limit in limits) + 0.10 if y_max is None else y_max
	if lo >= hi:
		raise ValueError("exterior roof piece has no local-Y extent")
	return lo, hi


def rafter_source_y_limits(plane, height):
	"""Reach both cut faces even when lower-purlin height/spacing is tuned."""
	limits = [local_y_limits_from_cuts(plane, z) for z in (RAFTER_Z_OFFSET, RAFTER_Z_OFFSET + height)]
	return min(lo for lo, _ in limits) - 0.10, max(hi for _, hi in limits) + 0.10


def local_y_at_global_z(plane, global_z, *, local_z=0):
	"""Return the roof-local Y where one local-Z line reaches global Z."""
	return (
		global_z
		- plane.origin[2]
		- local_z * plane.z_axis[2]
	) / plane.y_axis[2]


def local_y_at_global_y(plane, global_y, *, local_z=0):
	"""Return the roof-local Y where one local-Z line reaches global Y."""
	return (
		global_y
		- plane.origin[1]
		- local_z * plane.z_axis[1]
	) / plane.y_axis[1]


def local_y_at_plane_cut(plane, cut, *, local_x, local_z=0):
	"""Intersect a roof-local Y line with a non-vertical global cutting plane."""
	residuals = []
	for local_y in (0, 1):
		x, y, z = plane.to_world((local_x, local_y, local_z))
		residuals.append(z - plane_height_at(*cut, x=x, y=y))
	slope = residuals[1] - residuals[0]
	if abs(slope) <= 1e-9:
		raise ValueError("roof-local Y line must not be parallel to the cutting plane")
	return -residuals[0] / slope


def add_tile_battens(plane, name, x_ranges, y_min, y_max):
	x_ranges = [roof_under_tile_x_range(lo, hi) for lo, hi in x_ranges]
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
				extra_cuts=roof_eave_setback_cuts(plane),
			)
			roof_layer_storeys["Tile battens"].add(tile_batten)
		row += 1
		y += TILE_BATTEN_SPACING


# The outer layers deliberately overshoot in local Y so the roof-plane cuts
# trim them at the ridge and eaves.  Inner sloped and horizontal layers are
# separate solids whose outlines end where their bottom faces cross.  This is
# symmetric and avoids cross-plane Boolean mitres in the IFC model.
roof_y_min = -3
roof_y_max = +10
for profile in roof_inner_profiles.values():
	if profile.get("ceiling_only"):
		continue
	for side in ("street", "garden"):
		profile[f"{side}_boundaries"] = independent_inner_layer_boundaries(
			profile[f"{side}_plane"], profile["flat_plane"], profile["flat_layout"],
		)
street_inner_boundaries = roof_inner_profiles["normal"]["street_boundaries"]
garden_inner_boundaries = roof_inner_profiles["normal"]["garden_boundaries"]
dormer_inner_boundaries = roof_inner_profiles["dormer"]["garden_boundaries"]


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
print(f"  Normal roof: {normal_plasterboard_wall_height-UPPER_FLOOR_THICKNESS:.3f} m")
print(f"  Dormer roof: {dormer_plasterboard_wall_height-UPPER_FLOOR_THICKNESS:.3f} m")

roof_outer_face_offset = ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS
ground_floor_top = ground.elevation + GROUND_FLOOR_THICKNESS
active_exterior_ridge_planes = {
	plane for lo, hi, _ in roof_over_rafter_x_ranges
	for pair in exterior_ridge_planes_at((lo + hi) / 2) for plane in pair
}
total_house_height = max(
	roof_layer_height_at_y(
		plane,
		roof_outer_face_offset,
		HALF_DEPTH,
		ground_floor_top,
	)
	for plane in active_exterior_ridge_planes
)
print(
	f"Total house height from ground-storey finished floor level to top of roof, excluding chimney: "
	f"{total_house_height:.3f} m"
)


def flat_inner_y_limits(left_boundaries, right_boundaries, flat_layout):
	return {
		layer_name: (
			left_boundaries[layer_name][1],
			right_boundaries[layer_name][1],
		)
		for layer_name in flat_layout
	}


# Interior ranges are independent of exterior ranges and never overlap.
for segment, (x_min, x_max, profile_name) in enumerate(roof_under_rafter_x_ranges):
	profile = roof_inner_profiles[profile_name]
	if profile.get("ceiling_only"):
		add_continuous_roof_layers(
			profile["flat_plane"], f"Flat ceiling segment {segment}", x_min, x_max, BWT, HOUSE_DEPTH-BWT,
			inner_cuts=roof_inner_cuts, inner_y_limits=LOWER_CEILING_Y_LIMITS,
			inner_layout=profile["flat_layout"], include_under_rafter_insulation=False, include_outer=False,
		)
		continue
	for side, eave_y in (("street", 0.25), ("garden", 7.75)):
		plane = profile[f"{side}_plane"]
		label = "Dormer" if side == "garden" and profile_name == "dormer" else side.title()
		y_min = 0 if label == "Dormer" else roof_y_min
		y_max = roof_y_max-3 if label == "Dormer" else roof_y_max
		add_continuous_roof_layers(
			plane, f"{label} segment {segment}", x_min, x_max, y_min, y_max,
			include_outer=False,
			inner_cuts=roof_inner_cuts,
			inner_y_limits=sloped_inner_y_limits(plane, profile[f"{side}_boundaries"], eave_y),
			under_rafter_end_y=plane.origin[1],
		)
	flat_plane = profile["flat_plane"]
	add_continuous_roof_layers(
		flat_plane, f"Flat ceiling segment {segment}", x_min, x_max,
		BWT - flat_plane.origin[1], HOUSE_DEPTH-BWT - flat_plane.origin[1],
		inner_cuts=roof_inner_cuts,
		inner_y_limits=flat_inner_y_limits(
			profile["street_boundaries"], profile["garden_boundaries"], profile["flat_layout"],
		),
		inner_layout=profile["flat_layout"],
		include_under_rafter_insulation=False,
		include_outer=False,
	)

roof_exterior_pieces = []


def add_exterior_roof_piece(plane, name, x_min, x_max, *, side, y_min=None, y_max=None):
	"""Tiles keep their X range; boards, membrane and battens share an inset."""
	lo, hi = exterior_source_y_limits(plane, y_min=y_min, y_max=y_max)
	board_x_min, board_x_max = roof_under_tile_x_range(x_min, x_max)
	roof_exterior_pieces.append({
		"plane": plane, "name": name, "side": side,
		"x_min": board_x_min, "x_max": board_x_max,
		"tile_x_min": x_min, "tile_x_max": x_max,
		"source_y_min": lo, "source_y_max": hi,
	})
	add_continuous_roof_layers(
		plane, name, x_min, x_max, lo, hi,
		include_under_rafter_insulation=False, include_inner_finishes=False,
	)

# Exterior ranges may overlap. Do not pair them with the interior ranges.
for segment, (x_min, x_max, profile_name) in enumerate(roof_over_rafter_x_ranges):
	street_plane = street_roof
	garden_plane = {"normal": garden_roof, "dormer": dormer_roof}[profile_name]
	add_exterior_roof_piece(
		street_plane, f"Street segment {segment}", x_min, x_max, side="street",
	)
	if profile_name == "dormer":
		add_exterior_roof_piece(
			garden_roof, f"Garden segment {segment} above dormer", x_min, x_max,
			side="garden", y_max=0,
		)
	add_exterior_roof_piece(
		garden_plane, f"{'Dormer' if profile_name == 'dormer' else 'Garden'} segment {segment}",
		x_min, x_max, side="garden", y_min=0 if profile_name == "dormer" else None,
	)


def add_transverse_roof_layers():
	"""Reuse the exterior build-up; plane-local X is global Y on this slope."""
	add_exterior_roof_piece(
		transverse_roof, "Transverse roof",
		-TRANSVERSE_ROOF_Y_OVERHANG, HOUSE_DEPTH + TRANSVERSE_ROOF_Y_OVERHANG,
		side="transverse",
	)
	lo, hi = local_y_limits_from_cuts(
		transverse_roof, TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1] / 2,
		eave_setback=True,
	)
	add_tile_battens(
		transverse_roof, "Transverse roof",
		[(-TRANSVERSE_ROOF_Y_OVERHANG, HOUSE_DEPTH + TRANSVERSE_ROOF_Y_OVERHANG)],
		lo, hi,
	)


add_transverse_roof_layers()


def add_roof_siding():
	"""Fill each vertical eave setback down to its roof's horizontal cut."""
	if ROOF_EAVE_SETBACK == 0:
		return ()
	boards = []
	for side in ("street", "garden"):
		groups = {}
		for x_min, x_max, profile in roof_over_rafter_x_ranges:
			x_min, x_max = roof_under_tile_x_range(x_min, x_max)
			if side == "street":
				plane = street_roof
			else:
				plane = {"normal": garden_roof, "dormer": dormer_roof}[profile]
			groups.setdefault(plane, []).append((x_min, x_max))
		for plane, ranges in groups.items():
			eave_y = DORMER_ROOF_EAVE_Y if plane is dormer_roof else GARDEN_ROOF_EAVE_Y
			y0, y1 = ((STREET_ROOF_EAVE_Y, STREET_ROOF_EAVE_Y + ROOF_EAVE_SETBACK)
			          if side == "street" else (eave_y - ROOF_EAVE_SETBACK, eave_y))
			merged = []
			for lo, hi in sorted(ranges):
				if merged and lo <= merged[-1][1] + 1e-9:
					merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
				else:
					merged.append((lo, hi))
			top = offset_plane(*plane.points, offset=ROOF_TILE_BOTTOM)
			bottom = plane.cuts[1]
			for index, (x0, x1) in enumerate(merged, 1):
				corners = [(x, y) for x in (x0, x1) for y in (y0, y1)]
				z0 = min(plane_height_at(*bottom, x=x, y=y) for x, y in corners) - 0.10
				z1 = max(plane_height_at(*top, x=x, y=y) for x, y in corners) + 0.10
				keep_x, keep_y = (x0+x1)/2, (y0+y1)/2
				keep_z = (plane_height_at(*bottom, x=keep_x, y=keep_y)
				          + plane_height_at(*top, x=keep_x, y=keep_y)) / 2
				board = house.add_box(
					f"{side.title()} eave siding - {plane.Name} {index}",
					origin=(x0, y0, z0), size=(x1-x0, y1-y0, z1-z0),
					material="Wood siding solid", color=wood_siding_color(), cuts=(top, bottom),
					retained_point=(keep_x, keep_y, keep_z),
				)
				board.Description = "Non-structural eave fascia below the roof tiles"
				roof_layer_storeys["Eave siding"].add(board)
				boards.append(board)
	return tuple(boards)


roof_siding = add_roof_siding()


def add_sloped_roof_siding():
	"""Main gable caps plus the two side edges of each dormer roof range.

	Each main cap follows both roof pitches, filling the X-end allowance
	between the rafter underside and tile underside. Dormer caps follow their
	single pitch and stop at the exterior layers' ridge-side source boundary,
	not at the extended structural rafter ends.
	"""
	if ROOF_EAVE_SETBACK == 0:
		return ()
	color = wood_siding_color()
	high_ranges = [(lo, hi) for lo, hi, profile in roof_over_rafter_x_ranges if profile == "normal"]
	high_start = min(lo for lo, hi in high_ranges)
	high_end = max(hi for lo, hi in high_ranges)
	panels = []
	def add_cap(name, x0, profile):
		profile = profile.simplify(1e-9, preserve_topology=True)
		if profile.geom_type != "Polygon" or profile.is_empty or profile.interiors:
			raise ValueError(f"{name} must form one continuous siding band")
		points = list(profile.exterior.coords)[:-1]
		if not profile.exterior.is_ccw:
			points.reverse()
		panel = house.add_panel(
			name, outline=tuple((x0, y, z) for y, z in points), thickness=ROOF_EAVE_SETBACK,
			material="Wood siding solid", color=color,
		)
		panel.ObjectType = "ROOF_SLOPE_SIDING"
		panel.Description = "Solid-color non-structural roof-edge cap, rafter underside to tile underside"
		roof_layer_storeys["Sloped siding"].add(panel)
		panels.append(panel)

	for name, x0, planes in (
		("High roof left sloped siding", high_start, (street_roof, garden_roof)),
		("High roof right sloped siding", high_end - ROOF_EAVE_SETBACK, (street_roof, garden_roof)),
	):
		bands = []
		for plane, y0, y1 in (
			(planes[0], STREET_ROOF_EAVE_Y, HALF_DEPTH),
			(planes[1], HALF_DEPTH, GARDEN_ROOF_EAVE_Y),
		):
			bottom = offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
			top = offset_plane(*plane.points, offset=ROOF_TILE_BOTTOM)
			band = Polygon((
				(y0, plane_height_at(*bottom, x=x0, y=y0)),
				(y1, plane_height_at(*bottom, x=x0, y=y1)),
				(y1, plane_height_at(*top, x=x0, y=y1)),
				(y0, plane_height_at(*top, x=x0, y=y0)),
			))
			# At the eave, honor the horizontal cut as well as the vertical end.
			band = band.intersection(geometry_box(y0, plane.cuts[1][0][2], y1, band.bounds[3] + 1))
			bands.append(band)
		add_cap(name, x0, unary_union(bands))

	for index, piece in enumerate((p for p in roof_exterior_pieces if p["plane"] is dormer_roof), 1):
		# Keep the layer's local-Y source limits: the roof skin starts at the
		# purlin, while the dormer rafter itself continues farther towards ridge.
		lo, hi = piece["source_y_min"], piece["source_y_max"]
		points = [dormer_roof.to_world((0, y, z))[1:]
		          for y, z in ((lo, RAFTER_Z_OFFSET), (hi, RAFTER_Z_OFFSET),
		                       (hi, ROOF_TILE_BOTTOM), (lo, ROOF_TILE_BOTTOM))]
		band = Polygon(points)
		band = band.intersection(geometry_box(
			HALF_DEPTH, dormer_roof.cuts[1][0][2], DORMER_ROOF_EAVE_Y, band.bounds[3] + 1,
		))
		for side, x0 in (("left", piece["tile_x_min"]),
		                 ("right", piece["tile_x_max"] - ROOF_EAVE_SETBACK)):
			add_cap(f"Dormer {side} sloped siding {index}", x0, band)
	return tuple(panels)


roof_sloped_siding = add_sloped_roof_siding()


def add_transverse_roof_siding():
	"""Two sloped Y-end caps and the west fascia, inside the tile-edge slots."""
	if ROOF_EAVE_SETBACK == 0:
		return ()
	plane = transverse_roof
	top = offset_plane(*plane.points, offset=ROOF_TILE_BOTTOM)
	bottom = offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
	horizontal = plane.cuts[1]
	y0, y1 = -TRANSVERSE_ROOF_Y_OVERHANG, HOUSE_DEPTH + TRANSVERSE_ROOF_Y_OVERHANG
	x0, x1 = LOWER_NADEZDIVKA_X, TRANSVERSE_ROOF_EAVE_X
	boards = []
	for side, xa, xb, ya, yb, cuts, container in (
		("Street", x0, x1-ROOF_EAVE_SETBACK, y0, y0+ROOF_EAVE_SETBACK,
		 (top, bottom, horizontal), "Sloped siding"),
		("Garden", x0, x1-ROOF_EAVE_SETBACK, y1-ROOF_EAVE_SETBACK, y1,
		 (top, bottom, horizontal), "Sloped siding"),
		("West", x1-ROOF_EAVE_SETBACK, x1, y0, y1,
		 (top, horizontal), "Eave siding"),
	):
		corners = [(x, y) for x in (xa, xb) for y in (ya, yb)]
		heights = [plane_height_at(*cut, x=x, y=y) for cut in cuts for x, y in corners]
		z0, z1 = min(heights)-0.10, max(heights)+0.10
		keep_x, keep_y = (xa+xb)/2, (ya+yb)/2
		keep_z = (plane_height_at(*top, x=keep_x, y=keep_y)
		          + max(plane_height_at(*cut, x=keep_x, y=keep_y) for cut in cuts[1:])) / 2
		board = house.add_box(
			f"Transverse roof {side.lower()} siding",
			origin=(xa, ya, z0), size=(xb-xa, yb-ya, z1-z0),
			material="Wood siding solid", color=wood_siding_color(), cuts=cuts,
			retained_point=(keep_x, keep_y, keep_z),
		)
		board.Description = "Non-structural transverse roof edge below the roof tiles"
		roof_layer_storeys[container].add(board)
		boards.append(board)
	return tuple(boards)


transverse_roof_siding = add_transverse_roof_siding()


WEST_CLOSURE_WINDOW_CENTER_Y = HALF_DEPTH
WEST_CLOSURE_WINDOW_WIDTH = 1.0
WEST_CLOSURE_WINDOW_HEIGHT = 1.0
WEST_CLOSURE_WINDOW_SILL_HEIGHT = 1.5  # Above the finished upper floor.


def add_west_roof_closure():
	"""Window-bearing insulated gable with opening-aware finish coverings."""
	y0 = -FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001
	y1 = HOUSE_DEPTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
	z0 = UPPER_FLOOR_START
	specs, ranges = west_roof_closure_layout()

	def profile_at(roof_offset, ceiling_layer=None):
		street_top = offset_plane(*street_roof.points, offset=roof_offset)
		garden_top = offset_plane(*garden_roof.points, offset=roof_offset)
		profile = Polygon((
			(y0, z0), (y1, z0),
			(y1, plane_height_at(*garden_top, x=LOWER_NADEZDIVKA_X, y=y1)),
			(HALF_DEPTH, plane_height_at(*street_top, x=LOWER_NADEZDIVKA_X, y=HALF_DEPTH)),
			(y0, plane_height_at(*street_top, x=LOWER_NADEZDIVKA_X, y=y0)),
		))
		if ceiling_layer is not None:
			ceiling_z = flat_ceiling_roof.to_world(
				(0, 0, FLAT_CEILING_INNER_LAYER_LAYOUT[ceiling_layer][0])
			)[2]
			profile = profile.intersection(geometry_box(y0, z0, y1, ceiling_z))
		if profile.is_empty or profile.geom_type != "Polygon" or profile.interiors:
			raise ValueError("west closure must have one continuous profile above the upper slab")
		return profile

	profiles = {name: profile_at(roof_offset, ceiling_layer)
	            for name, _, material, _, roof_offset, ceiling_layer in specs if material is not None}
	core_profile = profile_at(MDF_BOTTOM)
	core_x0, core_x1 = ranges["Insulation"]
	wall_type = house.wall_type(
		"West closure - insulated timber wall",
		layers=[("Thermal insulation", FACADE_INSULATION_THICKNESS), "axis"],
		color="#E8D36D",
	)
	wall = upper.wall(
		(core_x1, y0), (core_x1, y1), wall_type=wall_type,
		height=core_profile.bounds[3]-z0,
		cuts=tuple(offset_plane(*plane.points, offset=MDF_BOTTOM) for plane in (street_roof, garden_roof)),
	)
	wall.Name = "West roof closure - insulated wall"
	wall.Description = "Insulated upper-floor gable with a service cavity and separate finishes"
	sill = UPPER_FLOOR_THICKNESS + WEST_CLOSURE_WINDOW_SILL_HEIGHT
	window_y0 = WEST_CLOSURE_WINDOW_CENTER_Y - WEST_CLOSURE_WINDOW_WIDTH / 2
	window_rectangle = geometry_box(
		window_y0, z0+sill, window_y0+WEST_CLOSURE_WINDOW_WIDTH, z0+sill+WEST_CLOSURE_WINDOW_HEIGHT,
	)
	for name, profile in {"Insulation": core_profile, **profiles}.items():
		if not profile.covers(window_rectangle):
			raise ValueError(f"west closure window must fit within the {name} roof/ceiling profile")
	# Coverings copy existing host openings, so create the window first.
	window = wall.add_window(
		name="West closure window", at=window_y0-y0, width=WEST_CLOSURE_WINDOW_WIDTH,
		sill_height=sill, height=sill+WEST_CLOSURE_WINDOW_HEIGHT, color="#ffffff",
	)
	panels = {}
	for name, thickness, material, color, _, _ in specs:
		if material is None:
			continue
		x0, x1 = ranges[name]
		profile = profiles[name]
		points = list(profile.exterior.coords)[:-1]
		if not profile.exterior.is_ccw:
			points.reverse()
		side, offset = ("right", x0-core_x1) if x0 >= core_x1 else ("left", core_x0-x1)
		panel = house.add_facade_layer(
			wall, name=f"West roof closure - {name}", side=side, offset=offset, thickness=thickness,
			start_height=0, height=profile.bounds[3]-z0,
			outline=tuple((y-y0, z-z0) for y, z in points),
			material=material, color=color,
		)
		panels[name] = panel
	return wall, window, panels, ranges


(west_closure_wall, west_closure_window,
 west_roof_closure, west_roof_closure_x_ranges) = add_west_roof_closure()

# A batten whose centre lies completely beyond a cut would retain the wrong
# half-space, so derive the first and last tile-batten rows from the cuts.
tile_batten_centerline_z = TILE_BATTEN_BOTTOM + TILE_BATTEN_SIZE[1] / 2
street_y_min, street_y_max = local_y_limits_from_cuts(
	street_roof, tile_batten_centerline_z, eave_setback=True,
)
garden_y_min, garden_y_max = local_y_limits_from_cuts(
	garden_roof, tile_batten_centerline_z, eave_setback=True,
)
dormer_y_min, dormer_y_max = local_y_limits_from_cuts(
	dormer_roof, tile_batten_centerline_z, eave_setback=True,
)
add_tile_battens(
	street_roof, "Street segments 0 to 2",
	[(lo, hi) for lo, hi, profile in roof_over_rafter_x_ranges if profile != "lower"],
	street_y_min, street_y_max
)
add_tile_battens(
	garden_roof,
	"Garden segments 0 and 2",
	[(lo, hi) for lo, hi, profile in roof_over_rafter_x_ranges if profile == "normal"],
	garden_y_min,
	garden_y_max,
)
add_tile_battens(
	garden_roof,
	"Garden segment 1 above dormer",
	[(lo, hi) for lo, hi, profile in roof_over_rafter_x_ranges if profile == "dormer"],
	garden_y_min,
	0,
)
add_tile_battens(
	dormer_roof,
	"Dormer segment 1",
	[(lo, hi) for lo, hi, profile in roof_over_rafter_x_ranges if profile == "dormer"],
	0,
	dormer_y_max,
)

main_roof_rafters = []
stronger_main_roof_rafters = []
dormer_short_rafters = []
dormer_roof_rafters = []

for i, (
	rafter_x,
	rafter_kind,
	shorten_garden_side,
	split_rafter_y,
	is_stronger_rafter,
) in enumerate(rafter_layout):
	is_dormer_rafter = rafter_kind == "dormer"
	parent_x = paired_dormer_owners[rafter_x] if is_dormer_rafter else rafter_x
	street_rafter_plane, garden_rafter_plane = framing_roof_planes_at(parent_x)
	rafter_size = (
		STRONGER_RAFTER_SIZE if is_stronger_rafter else RAFTER_SIZE
	)
	if not is_dormer_rafter:
		street_y_start, street_y_end = (rafter_source_y_limits(street_rafter_plane, rafter_size[1])
			if framing_is_lower(rafter_x) else (-2, 5))
		rafter = street_rafter_plane.beam(
			"Rafter 1",
			start=(rafter_x, street_y_start),
			end=(rafter_x, street_y_end),
			z_offset=RAFTER_Z_OFFSET,
			size=rafter_size,
			kind="RAFTER",
			extra_cuts=roof_eave_setback_cuts(street_rafter_plane),
		)
		roof_layer_storeys["Rafters"].add(rafter)
		(
			stronger_main_roof_rafters
			if is_stronger_rafter
			else main_roof_rafters
		).append(rafter)

	if is_dormer_rafter:
		# Overshoot the cut for BOTH section faces: the sloped cut, not a
		# square source-beam end, must define the complete finished joint.
		dormer_rafter_y_min = min(
			local_y_at_plane_cut(
				dormer_rafter_roof,
				dormer_rafter_roof.cuts[0],
				local_x=rafter_x,
				local_z=local_z,
			)
			for local_z in (RAFTER_Z_OFFSET, RAFTER_Z_OFFSET + rafter_size[1])
		) - SHORT_RAFTER_CUT_OVERLENGTH
		rafter = dormer_rafter_roof.beam(
			"Rafter 1",
			start=(rafter_x, dormer_rafter_y_min),
			end=(rafter_x, 5),
			z_offset=RAFTER_Z_OFFSET,
			size=rafter_size,
			kind="RAFTER",
			extra_cuts=roof_eave_setback_cuts(dormer_rafter_roof),
		)
		roof_layer_storeys["Rafters"].add(rafter)
		dormer_roof_rafters.append(rafter)
	else:
		rafter_y_min, rafter_full_y_max = (rafter_source_y_limits(garden_rafter_plane, rafter_size[1])
			if framing_is_lower(rafter_x) else (-2, 5))
		rafter_extra_cuts = ()
		if shorten_garden_side:
			short_rafter_cut_z = purlin_bottom_z_at(rafter_x)
			# Carry the uncut rafter completely past the horizontal cutting
			# plane.  Using its upper roof-local face here ensures the plane,
			# rather than the source beam's square end, defines the whole end.
			rafter_y_max = local_y_at_global_z(
				garden_rafter_plane,
				short_rafter_cut_z,
				local_z=RAFTER_Z_OFFSET + RAFTER_SIZE[1],
			) + SHORT_RAFTER_CUT_OVERLENGTH
			rafter_extra_cuts = (
				(
					(0, 0, short_rafter_cut_z),
					(1, 0, short_rafter_cut_z),
					(0, 1, short_rafter_cut_z),
				),
			)
		else:
			rafter_y_max = rafter_full_y_max
		rafter_segments = ((rafter_y_min, rafter_y_max, "Rafter 1"),)
		if split_rafter_y is not None:
			split_local_y = garden_rafter_plane.to_local_xy(
				(rafter_x, split_rafter_y)
			)[1]
			if not rafter_y_min < split_local_y < rafter_y_max:
				raise ValueError(
					"SplitRafter position must lie along the garden rafter"
				)
			rafter_segments = (
				(
					rafter_y_min,
					split_local_y,
					f"Rafter {i + 1} ridge segment",
				),
				(
					split_local_y,
					rafter_y_max,
					f"Rafter {i + 1} eave segment",
				),
			)
		for segment_start_y, segment_end_y, segment_name in rafter_segments:
			rafter = garden_rafter_plane.beam(
				segment_name,
				start=(rafter_x, segment_start_y),
				end=(rafter_x, segment_end_y),
				z_offset=RAFTER_Z_OFFSET,
				size=rafter_size,
				kind="RAFTER",
				extra_cuts=(*rafter_extra_cuts, *roof_eave_setback_cuts(garden_rafter_plane)),
			)
			roof_layer_storeys["Rafters"].add(rafter)
			if shorten_garden_side:
				dormer_short_rafters.append(rafter)
			else:
				(
					stronger_main_roof_rafters
					if is_stronger_rafter
					else main_roof_rafters
				).append(rafter)


def transverse_rafter_y_positions():
	"""Wall-aligned edge centres, with integer-metre centres strictly between."""
	if not all(math.isfinite(value) and value > 0 for value in (HOUSE_DEPTH, RAFTER_THICKNESS)) or HOUSE_DEPTH <= RAFTER_THICKNESS:
		raise ValueError("house depth must exceed the positive, finite rafter thickness")
	first, last = RAFTER_THICKNESS / 2, HOUSE_DEPTH - RAFTER_THICKNESS / 2
	return (first, *(float(y) for y in range(math.floor(first) + 1, math.ceil(last))), last)


def add_transverse_rafters():
	"""Normal-section rafters, cut at the roof step and both outside eave planes."""
	positions = transverse_rafter_y_positions()
	lo, hi = rafter_source_y_limits(transverse_roof, RAFTER_SIZE[1])
	beams = []
	for index, y in enumerate(positions, 1):
		beam = transverse_roof.beam(
			f"Transverse rafter {index}", start=(y, lo), end=(y, hi),
			z_offset=RAFTER_Z_OFFSET, size=RAFTER_SIZE, material="Wood", kind="RAFTER",
			extra_cuts=roof_eave_setback_cuts(transverse_roof),
		)
		roof_layer_storeys["Rafters"].add(beam)
		beams.append(beam)
	return tuple(beams)


transverse_rafters = add_transverse_rafters()


def add_exterior_counter_battens(pieces):
	"""Follow each rafter's level and union exterior intervals on its plane."""
	lines = {}
	for piece in pieces:
		plane = piece["plane"]
		if plane is transverse_roof:
			positions = transverse_rafter_y_positions()
		elif plane is dormer_roof:
			positions = dormer_rafter_positions
		else:
			positions = main_rafter_positions
		for x in positions:
			if piece["x_min"] <= x <= piece["x_max"]:
				key = (plane.GlobalId, x)
				lines.setdefault(key, (plane, []))[1].append((piece["source_y_min"], piece["source_y_max"]))
	battens = []
	labels = {street_roof: "Street", garden_roof: "Garden", dormer_roof: "Dormer", transverse_roof: "Transverse"}
	for (_, x), (plane, intervals) in lines.items():
		merged = []
		for lo, hi in sorted(intervals):
			if merged and lo <= merged[-1][1] + 1e-9:
				merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
			else:
				merged.append((lo, hi))
		for lo, hi in merged:
			batten = plane.beam(
				f"{labels[plane]} counter-batten {len(battens) + 1}",
				start=(x, lo), end=(x, hi), z_offset=COUNTER_BATTEN_BOTTOM,
				size=COUNTER_BATTEN_SIZE, material="Wood", kind="BEAM",
				extra_cuts=roof_eave_setback_cuts(plane),
			)
			roof_layer_storeys["Counter-battens"].add(batten)
			battens.append(batten)
	return tuple(battens)


exterior_counter_battens = add_exterior_counter_battens(roof_exterior_pieces)

for rafter in (
	*main_roof_rafters, *stronger_main_roof_rafters,
	*dormer_short_rafters,
):
	rafter_assemblies[rafter.local_start[0]].append(rafter)
dormer_rafter_owners = {
	x + offset: x for x, offset in paired_rafter_dormer_offsets.items()
}
for rafter in dormer_roof_rafters:
	rafter_assemblies[dormer_rafter_owners[rafter.local_start[0]]].append(rafter)

roof_window_trimmers = []
if roof_window_opening.trimmers:
	# Trimmers span between the inner faces of the two uninterrupted main
	# rafters.  Their roof-local Y positions use the same roof-plane datum as
	# the perpendicular opening, keeping their inner faces outside its void.
	roof_window_x_min, roof_window_y_min = roof_window_opening.rectangle[0]
	roof_window_x_max, roof_window_y_max = roof_window_opening.rectangle[1]
	roof_window_left_support_x = max(
		x for x in main_rafter_positions if x < roof_window_x_min
	)
	roof_window_right_support_x = min(
		x for x in main_rafter_positions if x > roof_window_x_max
	)
	roof_window_trimmer_x_min = (
		roof_window_left_support_x
		+ main_rafter_thicknesses[roof_window_left_support_x] / 2
	)
	roof_window_trimmer_x_max = (
		roof_window_right_support_x
		- main_rafter_thicknesses[roof_window_right_support_x] / 2
	)
	roof_window_center_x = (roof_window_x_min + roof_window_x_max) / 2
	roof_window_local_y_min = garden_roof.to_local_xy(
		(roof_window_center_x, roof_window_y_min)
	)[1]
	roof_window_local_y_max = garden_roof.to_local_xy(
		(roof_window_center_x, roof_window_y_max)
	)[1]

	for name, trimmer_local_y in (
		(
			"Roof window ridge trimmer",
			roof_window_local_y_min
			- RAFTER_SIZE[0] / 2
			+ ROOF_WINDOW_TRIMMER_OVERLAP,
		),
		(
			"Roof window eave trimmer",
			roof_window_local_y_max
			+ RAFTER_SIZE[0] / 2
			- ROOF_WINDOW_TRIMMER_OVERLAP,
		),
	):
		trimmer = garden_roof.beam(
			name,
			start=(roof_window_trimmer_x_min, trimmer_local_y),
			end=(roof_window_trimmer_x_max, trimmer_local_y),
			z_offset=RAFTER_Z_OFFSET + ROOF_WINDOW_TRIMMER_OVERLAP,
			size=RAFTER_SIZE,
			material="Wood",
			kind="BEAM",
			trim_openings=False,
		)
		roof_layer_storeys["Rafters"].add(trimmer)
		roof_window_trimmers.append(trimmer)

# Use the tiles actually cut by this opening, not a guessed vertical height.
roof_window_tiles = next(
	layer for layer in garden_roof.elements
	if isinstance(layer, RoofLayer)
	and layer.material_name == "Roof tiles"
	and any(void.RelatedOpeningElement in roof_window_opening.elements
			for void in (layer.HasOpenings or ()))
)
roof_window = garden_roof.add_window(
	roof_window_opening,
	top_layer=roof_window_tiles,
	color="#ffffff",
	glass_color="#ffffff",
)
roof_layer_storeys["Roof windows"].add(roof_window)
roof_window_plasterboard = next(
	layer for layer in garden_roof.elements
	if isinstance(layer, RoofLayer)
	and layer.material_name == "Gypsum plasterboard"
	and any(void.RelatedOpeningElement in roof_window_opening.elements
			for void in (layer.HasOpenings or ()))
)
roof_window_lining = garden_roof.add_opening_lining(
	roof_window_opening,
	bottom_layer=roof_window_plasterboard,
)
roof_layer_storeys["Gypsum plasterboard"].add(*roof_window_lining)


def add_facade(side="street"):
	"""Add full-height exterior finishes, without storey or gable seams.

	Panels meet at the roof step, not at storey/construction boundaries. The
	outer ends are staggered by 1 mm at perpendicular corner panels.
	"""
	if side not in {"street", "garden", "east", "west"}:
		raise ValueError("facade side must be 'street', 'garden', 'east' or 'west'")
	if side == "west":
		y0 = -FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001
		y1 = HOUSE_DEPTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
		top = transverse_wall_plate.start[2] - transverse_wall_plate.height / 2
		return (house.add_facade_layer(
			wall_4_g, name="West facade", material="Facade finish", color="#ffffff",
			offset=FACADE_INSULATION_THICKNESS, thickness=FACADE_THICKNESS, side="right",
			start_height=0, height=top - ground.elevation,
			start_extension=-y0, end_extension=y1-HOUSE_DEPTH,
		),)
	if side == "east":
		y0 = -FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001
		y1 = HOUSE_DEPTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
		wall, upper_wall = wall_1_g, wall_1_u
		street_plane, garden_plane = street_roof, garden_roof
		street_top = roof_layer_height_at_y(street_plane, RAFTER_Z_OFFSET, y0, ground.elevation)
		garden_top = roof_layer_height_at_y(garden_plane, RAFTER_Z_OFFSET, y1, ground.elevation)
		ridge_top = roof_layer_height_at_y(street_plane, RAFTER_Z_OFFSET, HALF_DEPTH, ground.elevation)
		if not isclose(ridge_top, roof_layer_height_at_y(garden_plane, RAFTER_Z_OFFSET, HALF_DEPTH, ground.elevation), abs_tol=1e-8):
			raise ValueError(f"{side} facade roof slopes must meet at the ridge")
		profile = ((y0, 0), (y1, 0), (y1, garden_top), (HALF_DEPTH, ridge_top), (y0, street_top))
		outline = tuple((y1-y if side == "east" else y-y0, z) for y, z in profile)
		return (house.add_facade_layer(
			wall, name=f"{side.title()} facade", material="Facade finish", color="#ffffff",
			offset=FACADE_INSULATION_THICKNESS, thickness=FACADE_THICKNESS, side="right",
			start_height=0, height=max(street_top, garden_top, ridge_top), outline=outline,
			start_extension=y1-HOUSE_DEPTH if side == "east" else -y0,
			end_extension=-y0 if side == "east" else y1-HOUSE_DEPTH,
			opening_walls=[upper_wall],
		),)
	x0 = -FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001
	x1 = HOUSE_WIDTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
	if side == "street":
		wall = wall_front_g
		insulation = FACADE_INSULATION_THICKNESS
		outer_y = -insulation - FACADE_THICKNESS
		high_roof = street_roof
		opening_walls = [wall_front1_u]
	else:
		wall = wall_back_g  # Host runs right-to-left; its right side faces the garden.
		insulation = FACADE_INSULATION_THICKNESS
		outer_y = HOUSE_DEPTH + insulation + FACADE_THICKNESS
		high_roof = garden_roof
		opening_walls = [wall_back1_u, wall_dormer]
	panels = []
	for name, start_x, end_x, plane, material, color in (
		(f"{side.title()} facade - high", x0, LOWER_NADEZDIVKA_X - 0.05,
		 high_roof, "Facade finish", "#ffffff"),
		(f"{side.title()} facade - low", LOWER_NADEZDIVKA_X - 0.05, x1,
		 transverse_roof, "Wood siding", wood_siding_color(patterned=True)),
	):
		outline = None
		if plane is transverse_roof:
			rafter_bottom = offset_plane(*plane.points, offset=RAFTER_Z_OFFSET)
			start_top, end_top = (
				plane_height_at(*rafter_bottom, x=x, y=outer_y) - ground.elevation
				for x in (start_x, end_x)
			)
			profile = ((start_x, 0), (end_x, 0), (end_x, end_top), (start_x, start_top))
			outline = tuple((x-start_x if side == "street" else end_x-x, z) for x, z in profile)
			top = max(start_top, end_top)
		else:
			top = roof_layer_height_at_y(plane, RAFTER_Z_OFFSET, outer_y, ground.elevation)
		if side == "garden" and plane is high_roof:
			dormer_start = min(wall_dormer.start[0], wall_dormer.end[0]) - FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001
			dormer_end = max(wall_dormer.start[0], wall_dormer.end[0]) + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
			dormer_top = roof_layer_height_at_y(dormer_roof, RAFTER_Z_OFFSET, outer_y, ground.elevation)
			# One concave profile, not two touching solids: no storey/dormer seam.
			profile = (
				(start_x, 0), (end_x, 0), (end_x, top),
				(dormer_end, top), (dormer_end, dormer_top),
				(dormer_start, dormer_top), (dormer_start, top), (start_x, top),
			)
			outline = tuple((end_x - x, z) for x, z in profile)
			top = dormer_top
		panels.append(house.add_facade_layer(
			wall,
			name=name,
			offset=insulation,
			thickness=FACADE_THICKNESS,
			side="right",
			start_height=0,
			height=top,
			outline=outline,
			start_extension=-start_x if side == "street" else end_x - HOUSE_WIDTH,
			end_extension=end_x - HOUSE_WIDTH if side == "street" else -start_x,
			opening_walls=opening_walls,
			material=material,
			color=color,
		))
	return tuple(panels)


street_facade = add_facade()
garden_facade = add_facade("garden")
east_facade = add_facade("east")
west_facade = add_facade("west")


def add_dormer_side_facades():
	"""White cheek finishes between main-roof tiles and dormer rafters."""
	bottom = offset_plane(*garden_roof.points, offset=ROOF_TILE_BOTTOM + ROOF_TILE_THICKNESS)
	top = offset_plane(*dormer_roof.points, offset=RAFTER_Z_OFFSET)
	y1 = HOUSE_DEPTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001
	panels = []
	for name, wall, side in (("east", wall_2, "left"), ("west", wall_3, "right")):
		def height(cut, y):
			return plane_height_at(*cut, x=wall.start[0], y=y)

		gap_at_zero = height(top, 0)-height(bottom, 0)
		gap_slope = height(top, 1)-height(bottom, 1)-gap_at_zero
		if gap_slope <= 1e-12:
			raise ValueError("dormer side facades need the dormer roof to rise above the main tiles towards the garden")
		y0 = -gap_at_zero/gap_slope
		if y0 >= y1:
			raise ValueError("dormer side facade has no exposed area above the main roof")
		z0 = height(bottom, y1)
		z1 = height(top, y0)
		panel = house.add_facade_layer(
			wall, name=f"Dormer {name} side facade", side=side,
			offset=FACADE_INSULATION_THICKNESS, thickness=FACADE_THICKNESS,
			start_height=z0-upper.elevation, height=z1-z0,
			start_extension=wall.start[1]-y0, end_extension=y1-wall.end[1],
			outline=((0, z1-z0), (y1-y0, 0), (y1-y0, height(top, y1)-z0)),
			material="Facade finish", color="#ffffff",
		)
		panels.append(panel)
	return tuple(panels)


dormer_side_facades = add_dormer_side_facades()

GARAGE_POST_SIZE = 0.15
GARAGE_ROOF_THICKNESS = 0.20

def draw_garage(x1, y1, x2, y2, height):
	"""Create a 3D-only garage placeholder, bounded by two opposite XY corners.

	The posts sit inside the footprint, from absolute Z=0 to ``height``;
	the roof sits on them. This is visual reference geometry, not a design.
	"""
	if not all(math.isfinite(value) for value in (x1, y1, x2, y2, height)):
		raise ValueError("garage coordinates and height must be finite")
	x_min, x_max = sorted((x1, x2))
	y_min, y_max = sorted((y1, y2))
	if x_max - x_min <= 2 * GARAGE_POST_SIZE or y_max - y_min <= 2 * GARAGE_POST_SIZE:
		raise ValueError("garage footprint must be wider than two posts on each axis")
	if height <= 0:
		raise ValueError("garage height must be greater than zero")
	posts = tuple(
		house.add_box(
			f"Garage post {index}",
			origin=(x, y, 0),
			size=(GARAGE_POST_SIZE, GARAGE_POST_SIZE, height),
			material="Wood",
			color="#8B5A2B",
			show_in_drawings=False,
		)
		for index, (x, y) in enumerate((
			(x_min+0.3, y_min+0.3),
			(x_max-0.3 - GARAGE_POST_SIZE, y_min+0.3),
			(x_max-0.3 - GARAGE_POST_SIZE, y_max-0.3 - GARAGE_POST_SIZE),
			(x_min+0.3, y_max-0.3 - GARAGE_POST_SIZE),
		), start=1)
	)
	roof = house.add_box(
		"Garage flat roof",
		origin=(x_min, y_min, height),
		size=(x_max - x_min, y_max - y_min, GARAGE_ROOF_THICKNESS),
		color="#A64B35",
		show_in_drawings=False,
	)
	roof = house.add_box(
		"Garage floor",
		origin=(x_min, y_min, 0.0),
		size=(x_max - x_min, y_max - y_min, 0.1),
		color="#151515",
		show_in_drawings=False,
	)
	return (*posts, roof)


# Initial 6 x 6 m footprint on the street side (negative Y); tune these here.
#garage = draw_garage(HOUSE_WIDTH-8, -4, HOUSE_WIDTH-2, -1, 3.0)

house.write("house.ifc")

def outside_dims(drawing1):
	# Vnejsi rozmery
	drawing1.add_dimension(start=(0, HOUSE_DEPTH-BWT), end=(HOUSE_WIDTH, HOUSE_DEPTH-BWT), offset=1.5)
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, 0), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH), offset=-1.5)

	drawing1.add_dimension(
		start=(-FACADE_INSULATION_THICKNESS-FACADE_THICKNESS, HOUSE_DEPTH-BWT),
		end=(HOUSE_WIDTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS, HOUSE_DEPTH-BWT),
		offset=2)
	drawing1.add_dimension(
		start=(HOUSE_WIDTH-BWT, -FACADE_INSULATION_THICKNESS-FACADE_THICKNESS),
		end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH+FACADE_INSULATION_THICKNESS+FACADE_THICKNESS),
		offset=-2)

def common_dims(drawing1):
	outside_dims(drawing1)
	drawing1.add_dimension(start=(BWT, HOUSE_DEPTH-BWT-1.3), end=(wall2_x-BWT, HOUSE_DEPTH-BWT-1.3), offset=0)
	drawing1.add_dimension(start=(wall2_x, HOUSE_DEPTH-BWT-1.3), end=(wall3_x-BWT, HOUSE_DEPTH-BWT-1.3), offset=0)
	drawing1.add_dimension(start=(wall3_x, HOUSE_DEPTH-BWT-1.3), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT-1.3), offset=0)

	# vzdalenost komina od obvodove zdi
	drawing1.add_dimension(start=(CHIMNEY_X_MID, BWT), end=(CHIMNEY_X_MID, CHIMNEY_Y_START))

def common_wall_insulation(
	drawing1, wall_front, wall_1, wall_back, wall_4
):
	# Keep insulation attached to actual hosts, never across the open bay.
	front_parts = wall_front if isinstance(wall_front, tuple) else (wall_front,)
	for index, front_part in enumerate(front_parts):
		drawing1.add_wall_insulation(
			front_part,
			thickness=FACADE_INSULATION_THICKNESS,
			material="polystyrene",
			# The front strip closes the corner over the side-wall wool.
			start_x=(-FACADE_INSULATION_THICKNESS if index == 0
				else min(front_part.start[0], front_part.end[0])),
			end_x=(HOUSE_WIDTH+FACADE_INSULATION_THICKNESS
			       if isclose(max(front_part.start[0], front_part.end[0]), HOUSE_WIDTH)
			       else max(front_part.start[0], front_part.end[0])),
		)
	drawing1.add_wall_insulation(
		wall_1,
		thickness=FACADE_INSULATION_THICKNESS,
		material="rockwool",
		start_y=0,
		end_y=HOUSE_DEPTH+0.01,
	)
	drawing1.add_wall_insulation(
		wall_back,
		thickness=FACADE_INSULATION_THICKNESS,
		material="rockwool",
		start_x=-FACADE_INSULATION_THICKNESS,
		end_x=HOUSE_WIDTH,
	)
	if wall_4 is not None:
		drawing1.add_wall_insulation(
			wall_4, thickness=FACADE_INSULATION_THICKNESS, material="polystyrene",
			start_y=-FACADE_INSULATION_THICKNESS, end_y=HOUSE_DEPTH+FACADE_INSULATION_THICKNESS,
		)

if "kanal" in sys.argv:
	# Schematic coordinates: horizontal distance is diagram layout, vertical
	# distance is the actual height above the finished ground-floor surface.
	datum = ground_floor_top
	miako_bottom = ceiling3.storey.elevation + ceiling3.bottom - datum
	miako_top = ceiling3.storey.elevation + ceiling3.top - datum
	upper_floor_top = upper.elevation + upper_pokoj_1.start_height + upper_pokoj_1.thickness - datum
	if inner_roof_section_at(DRAINAGE_STACK_X)[2].get("ceiling_only"):
		# The sloped lining was removed with the roof; retain the independent
		# suspended-ceiling level as the drainage schematic's reference.
		plasterboard_bottom = interior_ceiling_bottom_z_at(DRAINAGE_STACK_X)
	else:
		plasterboard_bottom, _ = roof.layer_vertical_extent(
			"Gypsum plasterboard", x=DRAINAGE_STACK_X, y=DRAINAGE_STACK_Y,
		)
	_, tiles_top = roof.layer_vertical_extent(
		"Roof tiles", x=DRAINAGE_STACK_X, y=DRAINAGE_STACK_Y,
	)
	levels = (
		("Přízemí - hotová podlaha", 0.0),
		("Suterén - horní líc základové desky",
		 foundation_base_plate.storey.elevation + foundation_base_plate.start_height + foundation_base_plate.thickness - datum),
		("Podkroví - spodní líc stropu MIAKO", miako_bottom),
		("Podkroví - horní líc stropu MIAKO", miako_top),
		("Podkroví - hotová podlaha", upper_floor_top),
		("Střecha - spodní líc sádrokartonu", plasterboard_bottom - datum),
		("Střecha - horní líc krytiny", tiles_top - datum),
	)
	line_start, line_end = -1.0, 12.0
	bottom, top = min(height for _, height in levels), max(height for _, height in levels)
	drawing1 = house.add_drawing(
		"kanal",
		x=(line_start + line_end) / 2,
		y=(bottom + top) / 2,
		z=1,
		radius=max((line_end - line_start) / 2 + 0.5, (top - bottom) / 2 + 0.7),
		storeys=[],
		door_annotations=False,
		automatic_plan_annotations=False,
	)
	for label, height in levels:
		drawing1.add_line((line_start, height), (line_end, height), name=label)
		print(f"kanal: {label}: {height:+.3f} m")
	for label, height in (
		("Přízemí 0 mm", 0.0),
		(f"Podkroví {upper_floor_top:.3f} mm".replace(".", ""), upper_floor_top),
		(f"Střecha {tiles_top:.3f} mm".replace(".", ""), tiles_top - datum),
	):
		# The house mirrors model X on export; anchor labels at the screen-left
		# endpoint so they extend into the drawing rather than off the page.
		label_x = line_end if house.mirror_x else line_start
		drawing1.add_text((label_x, height + 0.2), label, alignment="left", font_size=2.5)

	drawing1.add_poly_line(
		[
			(0.5, tiles_top+0.2),
			(0.5, miako_bottom-0.2),
			(2.5, 0.0),
			(2.5, -0.2),
		],
		color="orange", line_width=0.3)

	# slope
	drawing1.add_line(
		(2.5+5.5+1, 5.5*0.03),
		(2.5, -0.0),
		color="orange", line_width=0.3)

	drawing1.add_washing_machine_connection(x=2.5+2.5+3+1, z=0.65, identifier="Myčka")
	drawing1.add_line(
		(2.5+2.5+3+1, 0.65),
		(2.5+2.5+3+1, (2.5+3+1)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_sink(x=2.5+2.5+3, z=0.65)
	drawing1.add_line(
		(2.5+2.5+3, 0.65),
		(2.5+2.5+3, (2.5+3)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_shower(x=2.5+2.5+2.4, z=(2.5+2.4)*0.03+0.08)
	drawing1.add_line(
		(2.5+2.5+2.4, (2.5+2.4)*0.03+0.08),
		(2.5+2.5+2.4, (2.5+2.4)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_basin(x=2.5+2.5+1, z=0.65)
	drawing1.add_line(
		(2.5+2.5+1, 0.65),
		(2.5+2.5+1, (2.5+1)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_toilet(x=2.5+0, z=0.2)
	drawing1.add_line(
		(2.5+0, 0.2),
		(2.5+0, 0),
		color="orange", line_width=0.2)

	# slope
	drawing1.add_line(
		(8, upper_floor_top+7.5*0.03),
		(0.5, upper_floor_top),
		color="orange", line_width=0.3)

	drawing1.add_basin(x=8, z=upper_floor_top+0.65)
	drawing1.add_line(
		(8, upper_floor_top+0.65),
		(8, upper_floor_top+(8-0.5)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_toilet(x=0.5+0, z=upper_floor_top+0.2)

	drawing1.add_washing_machine_connection(x=2.5+1.5, z=upper_floor_top+0.65)
	drawing1.add_line(
		(2.5+1.5, upper_floor_top+0.65),
		(2.5+1.5, upper_floor_top+(8-0.5-2.5-1.5)*0.03),
		color="orange", line_width=0.3)

	drawing1.add_roof_vent(x=0.5, z=tiles_top+0.2)

	drawing1.add_text(
		point=(0.0, plasterboard_bottom+0.2),
		text="DN 100",
		font_size=2.5
	)

	drawing1.add_text(
		point=(0.5, 1.5),
		text="DN 100",
		font_size=2.5
	)

	drawing1.add_text(
		point=(2.5, -0.5),
		text="DN 100",
		font_size=2.5
	)

	drawing1.add_text(
		point=(4, 0.35),
		text="DN 50",
		font_size=2.5
	)

	drawing1.add_text(
		point=(2, upper_floor_top+0.3),
		text="DN 50",
		font_size=2.5
	)

	drawing1.render("kanal.svg", pdf=PDF_KANAL)

if "found" in sys.argv:
	drawing1 = house.add_drawing(
		"Foundation",
		x=5,
		y=3,
		z=foundation.elevation + FOUNDATION_FOOTER_HEIGHT / 2,
		radius=8,
		storeys=[foundation],
		right_panel_width=40,
	)
	wall_outline = drawing1.add_wall_outlines(foundation_walls, style="dashed")
	drawing1.add_line_legend([
		{"style": "solid", "color": "black", "description": "Spodní úroveň základových pasů"},
		(wall_outline, "Obrys nosných stěn"),
		{"style": "dashed", "color": "red", "description": "Zemnící pásovina FeZn 30/35"},
		{"style": "dashed-arrows", "color": "orange", "description": "splašková kanalizace"},
		{"style": "dashed-arrows", "color": "green", "description": "dešťová kanalizace"},
		{"style": "dashed-arrows", "color": "blue", "description": "vodovod"},
		{"style": "solid", "color": "blue", "description": "chránička"},
	])

	# FeZn
	drawing1.add_line((BWT/2, GYM_DEPTH-1), (BWT/2, HOUSE_DEPTH+1), style="dashed", color="red")
	drawing1.add_line((BWT/2, HOUSE_DEPTH-BWT/2), (HOUSE_WIDTH-BWT/2, HOUSE_DEPTH-BWT/2), style="dashed", color="red")
	drawing1.add_line((HOUSE_WIDTH-BWT/2, -1), (HOUSE_WIDTH-BWT/2, HOUSE_DEPTH+1), style="dashed", color="red")

	# Kanalizace
	drawing1.add_line((toilet_x+0.2, 1.0), (toilet_x+0.2, -1), style="dashed-arrows", color="orange")
	drawing1.add_line((toilet_x+0.2, -1), (3+1.1, -3), style="dashed-arrows", color="orange")
	drawing1.add_line((3-1.1, -3), (0, -3), style="dashed-arrows", color="orange")

	# Vodovod
	drawing1.add_line((HOUSE_WIDTH-1.3, -1.0), (HOUSE_WIDTH-1.3, 1.0), style="dashed-arrows", color="blue")
	# Chranicka
	drawing1.add_line((HOUSE_WIDTH-1.25, -0.5), (HOUSE_WIDTH-1.25, 0.7), style="solid", color="blue")
	drawing1.add_line((HOUSE_WIDTH-1.35, -0.5), (HOUSE_WIDTH-1.35, 0.7), style="solid", color="blue")
	drawing1.add_line((HOUSE_WIDTH-1.25, -0.5), (HOUSE_WIDTH-1.35, -0.5), style="solid", color="blue")
	drawing1.add_line((HOUSE_WIDTH-1.25, 0.7), (HOUSE_WIDTH-1.35, 0.7), style="solid", color="blue")

	drawing1.add_circle(center=(3, -3), radius=1.1, color="orange")
	drawing1.add_text(point=(3, -3), text="DČOV", font_size=3, color="orange")

	drawing1.add_dimension(
		(HOUSE_WIDTH-BWT/2.0-FOUNDATION_FOOTER_WIDTH/2.0, HOUSE_DEPTH-2),
		(HOUSE_WIDTH-BWT/2.0+FOUNDATION_FOOTER_WIDTH/2.0, HOUSE_DEPTH-2),
		offset=3
	)

	drawing1.render("found.svg", pdf=PDF_FOUND)

def add_elektro_legends(drawing):
	"""Keep circuit colors and electrical symbol samples shared by both floors."""
	drawing.add_line_legend([
		{"color": "blue", "line_width": 0.3, "description": "Zásuvkový okruh"},
		{"color": "red", "line_width": 0.3, "description": "3-fázový okruh"},
		{"color": "#f080f0", "line_width": 0.3, "description": "Světelný okruh"},
		{"color": "#80f080", "style": "dashed", "line_width": 0.3, "description": "Pospojování a uzemnění"},
	])
	drawing.add_symbol_legend([
		("socket", "Zásuvka"),
		("d_socket", "Dvojitá zásuvka"),
		("light", "Světlo"),
		("switch", "Vypínač"),
		("socket3f", "Zásuvka 380V, 3 fáze"),
	])

if "elektro_ground" in sys.argv:
	elektro_ground = house.add_drawing(
		"elektro_ground",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=GROUND_FLOOR_THICKNESS+2.05,
		radius=8.5,
		storeys=[ground],
		door_annotations=False,
		right_panel_width=60,
	)
	add_elektro_legends(elektro_ground)
	elektro_ground.add_stair_annotation(main_stairs)
	elektro_ground.add_stair_landing_annotation(middle_stair_landing)
	elektro_ground.add_stair_annotation(gallery_stairs)
	elektro_ground.add_chimney_annotation(chimney)
	elektro_ground_corners = elektro_ground.add_floor_corner_labels(
		ground,
		show=ELEKTRO_SHOW_ROOM_CORNERS and "--no-room-corners" not in sys.argv,
	)
	draw_elektro_line = ElektroLineDrawer(elektro_ground, elektro_ground_corners)

	elektro_ground.add_line(
		(HOUSE_WIDTH-1, BWT+BATHROOM_DEPTH-0.5),
		(HOUSE_WIDTH+0.5, BWT+BATHROOM_DEPTH-0.5),
		color="#80f080", style="dashed", line_width=0.3)
	elektro_ground.add_text(
		point=(HOUSE_WIDTH+0.6, BWT+BATHROOM_DEPTH-0.6),
		text="Připojení\nk FeZn\nv základech",
		font_size=2, color="#80f080")

	# zasuvka tepelne cerpadlo
	draw_elektro_line([
		"  0.04.1;1.5,0.1",
		" +0.03.1",
		"socket3f,0.4,up",
		"socket3f,1,left",
		" +0.03.2;0.3,0",
	], color="red", line_width=0.3)

	# zasuvky kuchyn
	draw_elektro_line([
		"  0.04.1;1.5,0.2",
		" +0.03.1",
		"-+0.03.2",
		"- 0.03.3",
		"-+0.01.6",
		"++0.01.5",
		"-+0.01.2",
		"d_socket,1,up",
		"  0.01.2;-1,0",
	], color="blue", line_width=0.3)

	draw_elektro_line([
		"  0.04.1;1.5,0.2",
		"  0.03.1",
		"  0.03.2",
		"  0.03.3",
		"  0.01.6",
		"d_socket,0.1,right",
		"d_socket,0.4,right",
		"d_socket,0.6,right",
		"d_socket,0.8,right",
		"d_socket,0.9,right",
		"--0.01.7",
		"+-0.01.8",
		"--0.01.11",
		"d_socket,0.2,down",
		"d_socket,0.5,down",
		"d_socket,0.8,down",
		"+-0.01.12",
		"d_socket,1,left",
		"+ 0.01.1;0,2",
	], color="blue", line_width=0.3)

	# zasuvka trouba
	draw_elektro_line([
		"  0.04.1;1.5,0.3",
		" +0.03.1",
		"-+0.03.2",
		"- 0.03.3",
		"-+0.01.6",
		"socket3f,1,right",
		"  0.01.6;0,1",
	], color="red", line_width=0.3)

	# zasuvky koupelna
	draw_elektro_line([
		"  0.04.1;1.5,0.4",
		" +0.03.1",
		"d_socket,0.75,up",
		"-+0.03.2",
		"d_socket,1,right",
		"  0.03.2;0,0.7",
	], color="blue", line_width=0.3)

	# zasuvky pokoj
	draw_elektro_line([
		"  0.04.1;1.0,0.1",
		"  0.04.1;0.1,0.1",
		"+-0.04.6",
		"++0.02.2",
		"d_socket,0.5,up",
		"++0.02.1",
		"d_socket,0.1,left",
		"d_socket,0.9,left",
		"+-0.02.5",
		"d_socket,0.1,down",
		"d_socket,0.9,down",
		"--0.02.4",
		"d_socket,0.1,right",
		"d_socket,0.9,right",
		"-+0.02.3",
	], color="blue", line_width=0.3)

	# svetlo kuchyn
	draw_elektro_line([
		"  0.04.1;1.3,0.5",
		"+-0.04.5",
		"++0.01.1",
		"  0.01.1;2.3,0",
		"switch,0.1,right",
		"light,1",
		"  0.01.1;2.3,2.5",
		"light,1",
		"  0.01.1;5.2,2.5",
	], color="#f080f0", line_width=0.3)

	# svetlo koupelna
	draw_elektro_line([
		"  0.04.1;1.5,0.5",
		"++0.03.1",
		"switch,0.9,left",
		"  0.03.1;0,1",
		"light,1",
		"  0.03.1;1,1",
	], color="#f080f0", line_width=0.3)

	# svetlo pokoj
	draw_elektro_line([
		"  0.04.1;1.0,0.2",
		"  0.04.1;0.2,0.2",
		"++0.02.2",
		"switch,0.1,left",
		"light,1",
		"  0.02.2;-0.5,3",
	], color="#f080f0", line_width=0.3)

	# svetlo chodba
	draw_elektro_line([
		"  0.04.1;1.4,0.5",
		"switch,0.75,right",
		"+ 0.04.5",
		"+-0.04.4;0.2,0",
		"  0.04.4;2.2,0",
		"switch,0.1,right",
		"light,1",
		"  0.04.4;2.2,-1",
		"  0.04.4;2.2,0",
		"--0.04.3",
		"switch,1,right",
		"  0.04.3;0,-1",
	], color="#f080f0", line_width=0.3)

	elektro_ground.render("elektro_ground.svg", pdf=PDF_ELEKTRO_GROUND)

if "elektro_upper" in sys.argv:
	elektro_upper = house.add_drawing(
		"elektro_upper",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=BWT+2.75+2,
		radius=8.5,
		storeys=[upper],
		door_annotations=False,
		right_panel_width=60,
	)
	elektro_upper.include_element(rozvadec)
	add_elektro_legends(elektro_upper)
	elektro_upper.add_stair_annotation(main_stairs)
	elektro_upper.add_stair_landing_annotation(middle_stair_landing)
	elektro_upper.add_stair_annotation(gallery_stairs)
	elektro_upper.add_chimney_annotation(chimney)
	elektro_upper_corners = elektro_upper.add_floor_corner_labels(
		upper,
		extra_floors=[chodba],
		show=ELEKTRO_SHOW_ROOM_CORNERS and "--no-room-corners" not in sys.argv,
	)
	draw_elektro_line = ElektroLineDrawer(elektro_upper, elektro_upper_corners)

	# zasuvky sklad
	draw_elektro_line([
		"  0.04.1;1.5,0.1",
		"-+0.04.2",
		" +P.04.4",
		"-+P.04.3",
		"--P.04.2",
		"-+P.03.2",
		"d_socket,0.5,right",
		"--P.03.3",
		"d_socket,0.7,down",
		"+-P.03.4",
		"d_socket,1,left",
		"  P.03.1;0.1,2",
	], color="blue", line_width=0.3)
	# zasuvky zachod
	draw_elektro_line([
		"  0.04.1;1.5,0.2",
		"-+0.04.2",
		" +P.04.4",
		"d_socket,0.7,up",
		"-+P.04.3",
		"d_socket,0.7,right",
		"--P.04.2",
	], color="blue", line_width=0.3)
	# svetlo zachod
	draw_elektro_line([
		"  0.04.1;1.5,0.3",
		"-+0.04.2",
		" +P.04.4;0.2,0",
		"+-P.04.1;0.1,0",
		"switch,1,down",
		"  P.04.1;0.6,0",
		"light,1",
		"  P.04.1;1,-1",
	], color="#f080f0", line_width=0.3)
	# svetlo sklad
	draw_elektro_line([
		"  0.04.1;1.5,0.4",
		"-+0.04.2",
		"++P.04.4",
		"++P.03.1",
		"switch,1,left",
		"  P.03.1;0,1.2",
		"light,1",
		"  P.03.1;1,2.5",
	], color="#f080f0", line_width=0.3)
	# zasuvky pokoj 1
	draw_elektro_line([
		"  0.04.1;1.3,0.5",
		"+-0.04.5",
		"++P.01.1",
		"d_socket,0.25,left",
		"d_socket,0.75,left",
		"+-P.01.4",
		"d_socket,0.25,down",
		"d_socket,0.75,down",
		"--P.01.3",
		"d_socket,0.25,right",
		"d_socket,0.75,right",
		"-+P.01.2",
		"d_socket,0.25,up",
		"d_socket,1,up",
		"  P.01.1;1.5,0",
	], color="blue", line_width=0.3)
	# svetlo pokoj 1
	draw_elektro_line([
		"  0.04.1;1.4,0.5",
		"+-0.04.5",
		"+ P.01.1",
		"switch,1,up",
		"  P.01.1;1.1,0",
		"light,1",
		"  P.01.1;2,2",
	], color="#f080f0", line_width=0.3)
	# zasuvky pokoj 2
	draw_elektro_line([
		"  0.04.1;1.2,0.5",
		"-+P.02.2",
		"d_socket,0.35,right",
		"d_socket,0.75,right",
		"--P.02.3",
		"d_socket,0.25,down",
		"d_socket,0.75,down",
		"+-P.02.4",
		"d_socket,0.25,left",
		"d_socket,0.75,left",
		"++P.02.1",
		"d_socket,1,up",
		"  P.02.2;-1,0",
	], color="blue", line_width=0.3)
	# svetlo pokoj 2
	draw_elektro_line([
		"  0.04.1;1.1,0.5",
		"-+P.02.2",
		"switch,1,right",
		"  P.02.2;0,1.2",
		"light,1",
		"  P.02.2;-1,2.5",
	], color="#f080f0", line_width=0.3)
	# svetlo chodba
	draw_elektro_line([
		"  0.04.1;1.5,0.5",
		"+-0.04.5",
		"--P.05.3;-4,0",
		"switch,0.25,down",
		"switch,1,down",
		"- P.05.3;-0.2,0",
	], color="#f080f0", line_width=0.3)

	elektro_upper.render("elektro_upper.svg", pdf=PDF_ELEKTRO_UPPER)

if "voda_ground" in sys.argv:
	drawing1 = house.add_drawing(
		"voda_ground",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=GROUND_FLOOR_THICKNESS+2.05,
		radius=8.5,
		storeys=[ground],
		right_panel_width=40,
	)
	drawing1.add_line_legend([
		{"style": "solid", "color": "red", "line_width": 0.3, "description": "teplá"},
		{"style": "solid", "color": "blue", "line_width": 0.3, "description": "studená"},
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_poly_line(
		[
			(wall3_x+0.4, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+3),
			(HOUSE_WIDTH-BWT-1, BWT+3),
		],style="solid", color="blue", line_width=0.3)
	drawing1.add_poly_line(
		[
			(wall3_x+1.5, BWT+0.2),
			(HOUSE_WIDTH-BWT-0.2, BWT+0.2),
			(HOUSE_WIDTH-BWT-0.2, BWT+2.9),
		],style="solid", color="red", line_width=0.3)

	drawing1.add_change_floor_symbol(wall3_x+1.25, BWT+0.1, "from down", color="black", line_width=0.3)
	drawing1.add_change_floor_symbol(wall3_x+1.25, BWT+0.1, "to up", color="black", line_width=0.3)
	drawing1.add_change_floor_symbol(wall3_x+1.5, BWT+0.2, "to up", color="black", line_width=0.3)

	drawing1.render("voda_ground.svg", pdf=PDF_VODA_GROUND)

if "voda_upper" in sys.argv:
	drawing1 = house.add_drawing(
		"voda_upper",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=BWT+2.75+2,
		radius=8.5,
		storeys=[upper],
		right_panel_width=40,
	)
	drawing1.add_line_legend([
		{"style": "solid", "color": "red", "line_width": 0.3, "description": "teplá"},
		{"style": "solid", "color": "blue", "line_width": 0.3, "description": "studená"},
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_poly_line(
		[
			(wall3_x+0.1, wall_zachod_nahore_y-0.6),
			(wall3_x+0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, wall_zachod_nahore_y+0.2),
		],style="solid", color="blue", line_width=0.3)
	drawing1.add_poly_line(
		[
			(wall3_x+1.5, BWT+0.2),
			(HOUSE_WIDTH-BWT-0.2, BWT+0.2),
			(HOUSE_WIDTH-BWT-0.2, wall_zachod_nahore_y+0.2),
		],style="solid", color="red", line_width=0.3)

	drawing1.add_change_floor_symbol(wall3_x+1.25, BWT+0.1, "from down", color="black", line_width=0.3)
	drawing1.add_change_floor_symbol(wall3_x+1.5, BWT+0.2, "from down", color="black", line_width=0.3)

	drawing1.render("voda_upper.svg", pdf=PDF_VODA_UPPER)

if "kanal_ground" in sys.argv:
	drawing1 = house.add_drawing(
		"kanal_ground",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=GROUND_FLOOR_THICKNESS+2.05,
		radius=8.5,
		storeys=[ground],
	)

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_poly_line(
		[
			(wall3_x+0.1, wall_zachod_nahore_y-0.6),
			(wall3_x+0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+3),
			(HOUSE_WIDTH-BWT-1, BWT+3),
		],style="solid", color="orange", line_width=0.3)

	drawing1.add_change_floor_symbol(wall3_x+0.1, wall_zachod_nahore_y-0.6, "from up", color="black", line_width=0.3)
	drawing1.add_change_floor_symbol(toilet_x, BWT+0.1, "to down", color="black", line_width=0.3)

	# DCOV
	drawing1.add_poly_line(
		[
			(toilet_x, BWT+0.1),
			(toilet_x, -1),
			(3+1.1, -3),
		], color="orange", style="dashed")

	drawing1.add_circle(center=(3, -3), radius=1.1, color="orange", style="dashed")
	drawing1.add_text(point=(3, -3), text="DČOV", font_size=3, color="orange")

	drawing1.render("kanal_ground.svg", pdf=PDF_KANAL_GROUND)

if "kanal_upper" in sys.argv:
	drawing1 = house.add_drawing(
		"kanal_upper",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=BWT+2.75+2,
		radius=8.5,
		storeys=[upper],
	)

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_poly_line(
		[
			(wall3_x+0.1, wall_zachod_nahore_y-0.6),
			(wall3_x+0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, BWT+0.1),
			(HOUSE_WIDTH-BWT-0.1, wall_zachod_nahore_y+0.2),
		],style="solid", color="orange", line_width=0.3)

	drawing1.add_change_floor_symbol(wall3_x+0.1, wall_zachod_nahore_y-0.6, "to down", color="black", line_width=0.3)
	drawing1.add_change_floor_symbol(wall3_x+0.1, wall_zachod_nahore_y-0.6, "to up", color="black", line_width=0.3)

	drawing1.render("kanal_upper.svg", pdf=PDF_KANAL_UPPER)

# Drawing 1 - ground floor
if "ground" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 1",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=GROUND_FLOOR_THICKNESS+2.0,
		radius=8.5,
		storeys=[ground],
		right_panel_width=40,
		section_outline_width=SECTION_OUTLINE_WIDTH,
		section_outline_color=SECTION_OUTLINE_COLOR,
	)
	aa_cut.add_symbol(drawing1)
	bb_cut.add_symbol(drawing1)
	drawing1.add_material_legend([
		("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
		("diagonal1", "Příčka - VPC Cihla 115 mm"),
		(
			"polystyrene-transparent",
			f"Fasádní izolace - Polystyren",
		),
		(
			"rockwool-wave",
			f"Fasádní izolace - Minerální vata",
		),
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	common_dims(drawing1)

	# Risankuv pokoj hloubka
	drawing1.add_dimension(start=(wall2_x-1.6, BWT+GYM_DEPTH+0.115), end=(wall2_x-1.6, HOUSE_DEPTH-BWT))
	# gym hloubka
	drawing1.add_dimension(start=(wall2_x-1.6, BWT), end=(wall2_x-1.6, BWT+GYM_DEPTH))

	# chodba hloubka
	drawing1.add_dimension(start=(CHIMNEY_X_END+1, BWT), end=(CHIMNEY_X_END+1, BWT+CHODBA_DEPTH), offset=0)
	# KK hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH+0.115), end=(HOUSE_WIDTH-BWT, HOUSE_DEPTH-BWT), offset=-1)
	# kuchyn hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-4, BWT+CHODBA_DEPTH+0.115), end=(HOUSE_WIDTH-4, HOUSE_DEPTH-BWT), offset=0)
	# koupelna hloubka
	drawing1.add_dimension(start=(HOUSE_WIDTH-BWT, BWT), end=(HOUSE_WIDTH-BWT, BWT+BATHROOM_DEPTH), offset=-1)

	# kamna
	drawing1.add_dimension(start=(wall2_x, CHODBA_DEPTH+0.5), end=(wall2_x+1, CHODBA_DEPTH+0.5), offset=1)

	drawing1.add_entrance_arrow(
		(-0.6, BWT + GYM_DEPTH - 0.125 - 0.55),
#		rotation=90,  # points left
		size=0.6,      # metres
	)

	drawing1.add_room_annotation(
		(wall3_x - 2, HOUSE_DEPTH - 3),
		identifier=kuchyn.room_id,
		description="Obývak s KK",
		area=kuchyn.area,
		window_area=window_area(window_obyvak, window_kk, window_kk1),
	)
	drawing1.add_room_annotation(
		(2, 5.7),
		identifier=pokoj_dole.room_id,
		description="Pokoj",
		area=pokoj_dole.area,
		window_area=window_area(window_pokoj_dole),
	)
	drawing1.add_room_annotation(
		(HOUSE_WIDTH-1.25, BWT+1.0),
		identifier=koupelna.room_id,
		description="Koupelna",
		area=koupelna.area,
		window_area=window_area(window_bathroom),
	)
	drawing1.add_room_annotation(
		(6.5, 1+0.5),
		identifier=chodba.room_id,
		description="Chodba a schody",
		area=chodba.area,
	)
	drawing1.add_room_legend()

	common_wall_insulation(
		drawing1,
		wall_front_g, wall_1_g, wall_back_g, wall_4_g
	)

	drawing1.add_lintel(front_door, 1, position="after")
	drawing1.add_lintel(kitchen_door, 2, position="after", direction="in")
	drawing1.add_lintel(pokoj0_door, 2, direction="in")
	drawing1.add_lintel(window_kk, 3, direction="in")
	drawing1.add_lintel(bathroom_door, 3)
	drawing1.add_lintel(window_bathroom, 4, position="after")
	drawing1.add_lintel(window_pokoj_dole, 5, direction="in")
	drawing1.add_lintel(window_obyvak, 7, position="after", direction="in")
	drawing1.add_lintel(oblouk, 8)
	drawing1.add_lintel_legend()

	drawing1.add_opening_dimension(kitchen_door, offset=-0.5)
	drawing1.add_opening_dimension(oblouk, offset=BWT/2)
	drawing1.add_opening_dimension(window_bathroom, offset=-0.75)
	drawing1.add_opening_dimension(window_obyvak, offset=-0.6)
	drawing1.add_opening_dimension(window_pokoj_dole, offset=-0.6)
	drawing1.add_opening_dimension(window_kk, offset=-0.6)
	drawing1.add_opening_dimension(pokoj0_door, offset=-0.5)
	drawing1.add_opening_dimension(front_door, offset=1.5)
	drawing1.add_opening_dimension(bathroom_door, offset=-1.25)

	# sirka schodu
	drawing1.add_dimension(start=(wall3_x-BWT-0.1, BWT), end=(wall3_x-BWT-0.1, BWT+1.0))
	drawing1.add_dimension(start=(wall3_x-BWT-1.0, BWT+0.1), end=(wall3_x-BWT, BWT+0.1))
	# zuzena chodba
	drawing1.add_dimension(start=(CHIMNEY_X_END+0.15, BWT), end=(CHIMNEY_X_END+0.15, GALERY_START))

	# sipka schody
	drawing1.add_poly_line(
		[
			(wall3_x-BWT-1.0-straight_stair_step_size*BOTTOM_STAIR_TREADS, BWT+0.5),
			(wall3_x-BWT-0.5, BWT+0.5),
			(wall3_x-BWT-0.5, GALERY_START-0.2),
		],
		style="solid",
		arrow_end=True,
		circle_start=True,
	)

	drawing1.add_notes(stairway_notes, title="SCHODIŠTĚ")
	drawing1.render("ground.svg", pdf=PDF_GROUND)

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
		section_outline_width=SECTION_OUTLINE_WIDTH,
		section_outline_color=SECTION_OUTLINE_COLOR,
		section_outline_projected_walls=True,
	)
	aa_cut.add_symbol(drawing1)
	bb_cut.add_symbol(drawing1)
	drawing1.include_element(heat_pump)
	drawing1.include_element(rozvadec)
	drawing1.add_material_legend([
		("solid-white", "Nosná zeď - VPC Cihla 240 mm"),
		("drywall-diagonal1", "Příčka - Sádrokarton 100 mm"),
		(
			"polystyrene-transparent",
			f"Fasádní izolace - Polystyren",
		),
		(
			"rockwool-wave",
			f"Fasádní izolace - Minerální vata",
		),
	])

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)

	drawing1.add_room_annotation(
		(6.5, 6),
		identifier=upper_pokoj_2.room_id,
		description="Pokoj 1",
		area=upper_pokoj_2.area,
		window_area=window_area(window_dormer_1, window_dormer_2),
	)
	drawing1.add_room_annotation(
		(1.5, 6),
		identifier=upper_pokoj_1.room_id,
		description="Pokoj 2",
		area=upper_pokoj_1.area,
		window_area=window_area(*east_upper_windows),
	)
	drawing1.add_room_annotation(
		((wall3_x + WEST_CLOSURE_INNER_X) / 2, BWT+0.5),
		identifier=zachod_nahore.room_id,
		description="Záchod",
		area=zachod_nahore.area
	)
	drawing1.add_room_annotation(
		(7, 3),
		description="Galerie",
		identifier=galerie.room_id,
		area=galerie.area
	)
	drawing1.add_room_legend()

	# sklad nahore hloubka
	drawing1.add_dimension(start=(WEST_CLOSURE_INNER_X, wall_zachod_nahore_y), end=(WEST_CLOSURE_INNER_X, wall_za_umyvadlem_y-wall_za_umyvadlem.thickness), offset=-1)
	# zachod nahore hloubka
	drawing1.add_dimension(start=(WEST_CLOSURE_INNER_X, BWT), end=(WEST_CLOSURE_INNER_X, wall_zachod_nahore_y-wall_zachod_nahore.thickness), offset=-1)
	# Pokoj 2, hloubka
	drawing1.add_dimension(start=(5.5, GALERY_END+0.1), end=(5.5, HOUSE_DEPTH-BWT), offset=0)
	# galerie hloubka
	drawing1.add_dimension(start=(6, GALERY_START), end=(6, GALERY_END), offset=0)
	# chodba hloubka
	drawing1.add_dimension(start=(CHIMNEY_X_END+0.1, BWT), end=(CHIMNEY_X_END+0.1, GALERY_START), offset=0)

	common_dims(drawing1)
	common_wall_insulation(
		drawing1,
		wall_front1_u, wall_1_u, wall_dormer, None
	)

	# sipka schody
	drawing1.add_poly_line(
		[
			(wall3_x-BWT-1.0-straight_stair_step_size*BOTTOM_STAIR_TREADS, BWT+0.5),
			(wall3_x-BWT-0.5, BWT+0.5),
			(wall3_x-BWT-0.5, GALERY_START-0.2),
		],
		style="solid",
		arrow_end=True,
		circle_start=True,
	)

	drawing1.add_lintel(pokoj1_door, 1, position="after", direction="in")
	drawing1.add_lintel(window_dormer_1, 2, direction="in", position="after")
	drawing1.add_lintel(window_dormer_2, 2, direction="in")
	drawing1.add_lintel(sklad_opening, 1, position="after")
	drawing1.add_lintel_legend()

	drawing1.add_notes(stairway_notes, title="SCHODIŠTĚ")
	drawing1.render("upper.svg", pdf=PDF_UPPER)

# Roof framing plan. Its camera is above the complete roof build-up, so all
# selected model elements are projections rather than section cuts.
roof_outline_walls = (
	wall_dormer,
	wall_front1_u,
	wall_back1_u,
	wall_1_u,
	wall_2,
	wall_3,
#	wall_pokoj2,
#	wall_zachod_nahore,
)
roof_wall_plates = (beam3, beam4_a, beam4_b, beam_dormer, transverse_wall_plate)
roof_structural_beams = (
	*street_purlins,
	*garden_purlins,
	transverse_purlin,
	*purlin_packing_blocks,
	*purlin_spacers,
	*roof_wall_plates,
)

# One schedule definition for every roof drawing; no diagram-specific copies.
collar_tie_groups = {}
for tie in collar_ties:
	collar_tie_groups.setdefault(round(tie.finished_length() * 1000), []).append(tie)
timber_schedule_rows = [
	(
		"Vaznice – pravý díl",
		(street_purlins[0], garden_purlins[0]),
		0,
		{
			"material": "gl24c",
			"pattern": PURLIN_DRAWING_PATTERN,
			"color": PURLIN_LEFT_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Vaznice – střední díl",
		(street_purlins[1], garden_purlins[1]),
		0,
		{
			"material": "gl28h",
			"pattern": PURLIN_DRAWING_PATTERN,
			"color": PURLIN_MIDDLE_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Vaznice – příčná",
		(transverse_purlin,),
		0,
		{
			"material": "gl24c",
			"pattern": PURLIN_DRAWING_PATTERN,
			"color": PURLIN_RIGHT_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Pozednice – příčná, zeď 4",
		(transverse_wall_plate,),
		0,
		{
			"material": "C16",
			"pattern": WALL_PLATE_DRAWING_PATTERN,
			"color": SHORT_WALL_PLATE_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Krokve – příčné",
		transverse_rafters,
		RAFTER_EXTRA_LENGTH,
		{
			"pattern": RAFTER_DRAWING_PATTERN,
			"color": MAIN_RAFTER_DRAWING_COLOR,
			"drawing_order": MAIN_RAFTER_DRAWING_ORDER,
		},
	),
	(
		"Krokve – hlavní",
		main_roof_rafters,
		RAFTER_EXTRA_LENGTH,
		{
			"pattern": RAFTER_DRAWING_PATTERN,
			"color": MAIN_RAFTER_DRAWING_COLOR,
			"drawing_order": MAIN_RAFTER_DRAWING_ORDER,
		},
	),
	*(
		(
			(
				"Krokve – zesílené",
				stronger_main_roof_rafters,
				RAFTER_EXTRA_LENGTH,
				{
					"pattern": STRONGER_RAFTER_DRAWING_PATTERN,
					"color": MAIN_RAFTER_DRAWING_COLOR,
					"drawing_order": MAIN_RAFTER_DRAWING_ORDER,
				},
			),
		)
		if stronger_main_roof_rafters
		else ()
	),
	(
		"Krokve – zkrácené, vikýř",
		dormer_short_rafters,
		RAFTER_EXTRA_LENGTH,
		{
			"material": "C16",
			"pattern": RAFTER_DRAWING_PATTERN,
			"color": DORMER_SHORT_RAFTER_DRAWING_COLOR,
			"drawing_order": MAIN_RAFTER_DRAWING_ORDER,
		},
	),
	(
		"Krokve – vikýř",
		dormer_roof_rafters,
		RAFTER_EXTRA_LENGTH,
		{
			"pattern": RAFTER_DRAWING_PATTERN,
			"color": DORMER_RAFTER_DRAWING_COLOR,
			"drawing_order": DORMER_RAFTER_DRAWING_ORDER,
		},
	),
	(
		"Pozednice – ulice",
		street_wall_plates,
		0,
		{
			"material": "C16",
			"pattern": WALL_PLATE_DRAWING_PATTERN,
			"color": STREET_WALL_PLATE_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Pozednice – krátká - zahrada",
		(beam4_a,),
		0,
		{
			"material": "C16",
			"pattern": WALL_PLATE_DRAWING_PATTERN,
			"color": SHORT_WALL_PLATE_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Pozednice – zahrada",
		(beam4_b,),
		0,
		{
			"material": "C16",
			"pattern": WALL_PLATE_DRAWING_PATTERN,
			"color": GARDEN_WALL_PLATE_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER,
		},
	),
	(
		"Pozednice – vikýř",
		(beam_dormer,),
		0,
		{
			"material": "C16",
			"pattern": WALL_PLATE_DRAWING_PATTERN,
			"color": DORMER_WALL_PLATE_DRAWING_COLOR,
			"drawing_order": DORMER_WALL_PLATE_DRAWING_ORDER,
		},
	),
	*(
		(
			"Kleštiny" if len(collar_tie_groups) == 1 else f"Kleštiny – {length_mm} mm",
			members,
			0,
			{
				"material": "C16",
				"color": COLLAR_TIE_DRAWING_COLOR,
				"drawing_order": COLLAR_TIE_DRAWING_ORDER,
			},
		)
		for length_mm, members in sorted(collar_tie_groups.items(), reverse=True)
	),
]
if roof_window_trimmers:
	timber_schedule_rows.append(
		(
			"Tesařská výměna",
			roof_window_trimmers,
			0,
			{"drawing_order": MAIN_RAFTER_DRAWING_ORDER},
		)
	)
timber_schedule_rows.extend(
	(
		f"Rozpěry vaznic – {label}",
		members,
		0,
		{
			"material": "C16",
			"color": MAIN_RAFTER_DRAWING_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER
		},
	)
	for label, members in (
		("střed", tuple(spacer for spacer in purlin_spacers
			if purlin_segment_at(spacer.start[0]) == "middle")),
		("krajní", tuple(spacer for spacer in purlin_spacers
			if purlin_segment_at(spacer.start[0]) == "left")),
		("nižší část", tuple(spacer for spacer in purlin_spacers
			if purlin_segment_at(spacer.start[0]) == "right")),
	)
	if members
)
if purlin_packing_blocks:
	timber_schedule_rows.append((
		"Podložky vaznic",
		purlin_packing_blocks,
		0,
		{
			"material": "C16",
			"pattern": PURLIN_DRAWING_PATTERN,
			"color": PODLOZKY_VAZNIC_COLOR,
			"drawing_order": PURLIN_AND_WALL_PLATE_DRAWING_ORDER - 1,
		},
	))
# Tables require identical finished lengths in a row; preserve each member's
# measured geometry and original material/appearance.
measured_timber_schedule_rows = []
for name, members, extra_length, settings in timber_schedule_rows:
	groups = {}
	for member in members:
		key = (round(member.width * 1000), round(member.height * 1000), round(member.finished_length() * 1000))
		groups.setdefault(key, []).append(member)
	for (width_mm, height_mm, length_mm), group in groups.items():
		row_name = name if len(groups) == 1 else f"{name} – {length_mm} mm"
		measured_timber_schedule_rows.append((row_name, tuple(group), extra_length, settings))
timber_schedule_rows = measured_timber_schedule_rows
# Any row may override this initial grade in its settings above.
timber_schedule_rows = [
	(name, members, extra_length, {
		**settings,
		"material": resolve_timber_grade(settings.get("material", "c22")).name,
	})
	for name, members, extra_length, settings in timber_schedule_rows
]

def roof_elevation_cut(*, rafter_index, offset=0.15, identifier="X"):
	"""Define the framing cut from the same rafter/offset used by its camera."""
	if isinstance(rafter_index, bool) or not isinstance(rafter_index, int):
		raise TypeError("rafter_index must be an integer")
	if not 0 <= rafter_index < len(rafters):
		raise ValueError("rafter_index must be within the rafters array")
	if isinstance(offset, bool) or not isinstance(offset, (int, float)):
		raise TypeError("offset must be a number in metres")
	if not math.isfinite(offset):
		raise ValueError("offset must be finite")
	rafter_x = rafter_x_position(rafters[rafter_index])
	camera_x = rafter_x - offset
	return CutDefinition(
		start=(camera_x, -2.0),
		end=(camera_x, HOUSE_DEPTH + 2.0),
		identifier=identifier,
		direction=-1,
	)


def add_roof_angles(drawing1):
	angles = [("AA main roof angle",
		plane, 2.2, -1) for plane in exterior_roof_planes_at(drawing1.x, side="street")]
	if dormer_roof in exterior_roof_planes_at(drawing1.x, side="garden"):
		angles.append(("AA dormer roof angle", dormer_roof, 6.5, 1))
	for angle_name, plane, y, slope_sign in angles:
		angle = roof_angle_degrees(plane)
		clearance, radius = -0.2, 1.0
		z = roof_layer_height_at_y(plane, ROOF_TILE_BOTTOM, y, 0) - clearance
		drawing1.add_angle(
			vertex=(y, z),
			start=(y + slope_sign, z),
			end=(y + slope_sign, z - math.tan(math.radians(angle))),
			radius=radius,
			name=angle_name,
		)

def add_roof_rafter_dimensions(drawing, *, rafter_x, offset=0.45):
	"""Dimension rafter spans between the supports' outer top corners.

	Use the selected assembly's actual rafter axes and purlin piece. The
	street wall plate follows the framing level; on the garden side, use the
	dormer rafter/plate when present. Symmetric lower spans need only
	one dimension. Keep the existing rafter-axis point at the ridge. These
	are support spans, not timber cutting lengths.
	"""
	members = [beam for beam in rafter_assemblies[rafter_x] if beam.kind == "RAFTER"]
	street_plane, garden_plane = framing_roof_planes_at(rafter_x)
	street = next(beam for beam in members if beam.roof_plane is street_plane)
	garden = next((beam for beam in members if beam.roof_plane is dormer_rafter_roof), None)
	if garden is None:
		garden = next(beam for beam in members if beam.roof_plane is garden_plane)
	street_plate = wall_plate_at(rafter_x, side="street")
	garden_plate = wall_plate_at(garden.start[0], side="garden", dormer=garden.roof_plane is dormer_rafter_roof)
	street_purlin = purlin_at(rafter_x, side="street")
	garden_purlin = purlin_at(rafter_x, side="garden")

	def outer_top_corner(beam, outside_direction):
		return (beam.start[1] + outside_direction * beam.width / 2,
		        beam.start[2] + beam.height / 2)

	def point_on_rafter(beam, y):
		fraction = (y - beam.start[1]) / (beam.end[1] - beam.start[1])
		return (y, beam.start[2] + fraction * (beam.end[2] - beam.start[2]))

	street_seat = outer_top_corner(street_plate, -1)
	street_support = outer_top_corner(street_purlin, -1)
	ridge = point_on_rafter(street, HALF_DEPTH+0.06)
	garden_seat = outer_top_corner(garden_plate, 1)
	garden_support = outer_top_corner(garden_purlin, 1)
	dimensions = [
		drawing.add_dimension(
			start=street_support, end=ridge, offset=offset,
			name=f"{drawing.name} street rafter purlin to ridge",
		),
		drawing.add_dimension(
			start=street_seat, end=street_support, offset=offset,
			name=f"{drawing.name} street rafter wall plate to purlin",
		),
	]
	if not isclose(math.dist(street_seat, street_support),
	               math.dist(garden_seat, garden_support), rel_tol=1e-9, abs_tol=1e-9):
		dimensions.append(drawing.add_dimension(
			start=garden_seat, end=garden_support, offset=-offset,
			name=f"{drawing.name} garden rafter wall plate to purlin",
		))
	return tuple(dimensions)


def add_roof_purlin_dimension(drawing, *, rafter_x, offset=-0.5):
	"""Dimension purlin centre spacing below the framing, using local pieces."""
	street, garden = (purlin_at(rafter_x, side=side) for side in ("street", "garden"))
	return drawing.add_dimension(
		start=(street.start[1], street.start[2]),
		end=(garden.start[1], garden.start[2]),
		offset=offset,
		name=f"{drawing.name} purlin centre spacing",
	)


def assembly_wall_plates(rafter_x):
	"""Only actual seats of this assembly, including paired dormer members."""
	plates = []
	for beam in rafter_assemblies[rafter_x]:
		if beam.kind != "RAFTER" or beam in dormer_short_rafters:
			continue
		if beam.roof_plane is street_roof:
			plate = wall_plate_at(beam.start[0], side="street")
		else:
			plate = wall_plate_at(beam.start[0], side="garden", dormer=beam.roof_plane is dormer_rafter_roof)
		if plate not in plates:
			plates.append(plate)
	return tuple(plates)


def add_roof_elevation(name, *, rafter_index, offset=0.15, radius=6, identifier="X"):
	"""Return a roof-framing section with the shared schedule and timber styles.

	``rafter_index`` is a zero-based index into ``rafters``. Positive ``offset``
	places the +X-looking camera before that assembly (towards lower X); zero
	cuts through it, and negative values move the camera past it. Coordinates
	remain unmirrored here, as for all other drawing helpers. Rendering is left
	to the caller so dimensions and notes can be added first.
	"""
	cut = roof_elevation_cut(rafter_index=rafter_index, offset=offset, identifier=identifier)
	rafter_x = rafter_x_position(rafters[rafter_index])
	camera_x = cut.center[0]
	drawing = cut.add_drawing(
		house, name,
		z=(UPPER_FLOOR_START + ground_floor_top + total_house_height) / 2,
		radius=radius,
		storeys=[roof_layer_storeys["Rafters"], roof_layer_storeys["Collar ties"]],
		door_annotations=False,
		automatic_plan_annotations=False,
		doors_closed=True,
		model_line_width=0.06,
		right_panel_width=65,
	)
	for element in (*roof_outline_walls, *upper_ring_beams, *roof_structural_beams):
		drawing.include_element(element)
	styled_members = (
		*rafter_assemblies[rafter_x],
		# Highlight plates at the selected assembly, not plates seen farther
		# along the house. Keep those distant plates as white projections.
		*assembly_wall_plates(rafter_x),
		*purlin_packing_blocks,
		*(beam for beam in (*street_purlins, *garden_purlins)
			if min(beam.start[0], beam.end[0]) <= camera_x <= max(beam.start[0], beam.end[0])),
	)
	drawing.add_timber_schedule(
		timber_schedule_rows, layout_scale=0.5,
		styled_members=styled_members,
	)
	add_roof_rafter_dimensions(drawing, rafter_x=rafter_x)
	add_roof_purlin_dimension(drawing, rafter_x=rafter_x)
	return drawing


# Shared camera/plan-marker inputs; changing a rafter or offset moves both.
roof_elevation_definitions = {
	"roof_xx": {"rafter_index": 1, "offset": 0.15, "identifier": "X"},
	"roof_yy": {"rafter_index": 5, "offset": 0.20, "identifier": "Y"},
}
roof_elevation_cuts = {
	name: roof_elevation_cut(**definition)
	for name, definition in roof_elevation_definitions.items()
}


if "roof" in sys.argv:
	drawing1 = house.add_drawing(
		"Roof plan",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=ground_floor_top+total_house_height+0.5,
		radius=8.5,
		storeys=[
			roof_layer_storeys["Rafters"],
			roof_layer_storeys["Collar ties"],
		],
		door_annotations=False,
		projected_wood_color="#f4d35e",
		surface_fills=True,
		model_line_width=0.06,
		right_panel_width=65,
		section_outline_width=SECTION_OUTLINE_WIDTH,
		section_outline_color=SECTION_OUTLINE_COLOR,
		section_outline_projected_walls=True,
	)
	aa_cut.add_symbol(drawing1)
	bb_cut.add_symbol(drawing1)
	for cut in roof_elevation_cuts.values():
		cut.add_symbol(drawing1)
	for element in (*roof_outline_walls, *upper_ring_beams, *roof_structural_beams):
		drawing1.include_element(element)
	drawing1.add_chimney_annotation(chimney)
	drawing1.add_roof_opening_outline(
		roof_window_opening,
		y_min_inset=ROOF_WINDOW_OUTLINE_Y_MIN_INSET,
		mask=False,
	)

	# Dimension the rafter centrelines directly from the layout derived from
	# ``rafters``.  Main-rafter spacings form one chain below the street eave;
	# dormer-rafter spacings form a second chain above the garden eave.
	for index, (start_x, end_x) in enumerate(
		zip(main_rafter_positions, main_rafter_positions[1:]),
		start=1,
	):
		drawing1.add_dimension(
			start=(start_x, STREET_ROOF_EAVE_Y),
			end=(end_x, STREET_ROOF_EAVE_Y),
			offset=-0.75,
			name=f"Main rafter spacing {index}",
		)
	for index, (start_x, end_x) in enumerate(
		zip(dormer_rafter_positions, dormer_rafter_positions[1:]),
		start=1,
	):
		drawing1.add_dimension(
			start=(start_x, DORMER_ROOF_EAVE_Y),
			end=(end_x, DORMER_ROOF_EAVE_Y),
			offset=0.75,
			name=f"Dormer rafter spacing {index}",
		)

	drawing1.add_timber_schedule(timber_schedule_rows, layout_scale=0.5)
	drawing1.add_notes(
		[
			"Hlavní krokve (nezkrácené), které mají "
			"součet osových vzdáleností od sousedních krokví "
			"1.7 m nebo více, musí mít pevnostní třídu C24. "
			"Pro všechny ostatní prvky krovu dostačuje C22."
		],
		layout_scale=0.5,
	)

	# stoupacka kanalizace
	drawing1.add_drainage_stack(
	    center=(DRAINAGE_STACK_X, DRAINAGE_STACK_Y),
    	diameter=0.11,
	)

	roof_plan = drawing1
	roof_xx = add_roof_elevation("roof_xx", **roof_elevation_definitions["roof_xx"])
	roof_yy = add_roof_elevation("roof_yy", **roof_elevation_definitions["roof_yy"])
	roof_yy.include_element(chimney)
	roof_yy.add_dimension(
		start=(CHIMNEY_Y_END, PURLIN_TOP_Z+0.03),
		end=(rafters[5][2]["min_y"], PURLIN_TOP_Z+0.03),
	)

	# Drawing centres as fractions of the whole page (left/top = 0, right/bottom = 1).
	# The top half keeps the previous A4 landscape layout at its original scale.
	roof_sheet = DrawingSheet(paper="A3", orientation="portrait")
	roof_sheet.add(roof_plan, x=0.5, y=0.25, title=Path(PDF_KROV).stem, crop=False)
	roof_sheet.add(roof_xx, x=0.25, y=0.64, title="Řez XX", tables=False)
	roof_sheet.add(roof_yy, x=0.74, y=0.75, title="Řez YY", tables=False)
	roof_sheet.render("roof.svg", pdf=PDF_KROV)

if "ceiling" in sys.argv:
	drawing1 = house.add_drawing(
		"Drawing 2",
		x=HOUSE_WIDTH/2,
		y=HOUSE_DEPTH/2,
		z=ground_floor_height+0.04,
		radius=8.5,
		storeys=[upper],
		door_annotations=False,
		automatic_plan_annotations=False,
		right_panel_width=50,
	)

	drawing1.add_stair_annotation(main_stairs)
	drawing1.add_stair_landing_annotation(middle_stair_landing)
	drawing1.add_stair_annotation(gallery_stairs)
	drawing1.add_chimney_annotation(chimney)
	drawing1.add_miako_beam_dimensions(ceiling1, side="start", offset=0.8)
	drawing1.add_miako_beam_dimensions(ceiling2, side="start", offset=-0.8)
	drawing1.add_miako_beam_dimensions(ceiling3, side="end", offset=0.8)

	outside_dims(drawing1)
	drawing1.add_dimension(start=(BWT-0.135, HOUSE_DEPTH-BWT), end=(wall2_x-BWT+0.135, HOUSE_DEPTH-BWT), offset=0.8)
	drawing1.add_dimension(start=(wall2_x-0.135, HOUSE_DEPTH-BWT), end=(wall3_x-BWT+0.135, HOUSE_DEPTH-BWT), offset=0.8)
	drawing1.add_dimension(start=(wall3_x-0.135, HOUSE_DEPTH-BWT), end=(HOUSE_WIDTH-BWT+0.135, HOUSE_DEPTH-BWT), offset=0.8)
	drawing1.add_miako_beam_schedule(
		[
			{"location": "Levá část", "slab": ceiling3},
			{"location": "Střed", "slab": ceiling2},
			{"location": "Pravá část", "slab": ceiling1},
		]
	)

	common_wall_insulation(
		drawing1,
		wall_front1_u, wall_1_u, wall_dormer, None
	)

	drawing1.render("ceiling.svg", pdf=PDF_CEILING)

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

def add_section_material_legend(drawing):
	"""Add the shared material legend used by the house sections."""
	return drawing.add_material_legend([
		("solid-white", "Nosná zeď\nVPC Cihla 240 mm"),
		(
			"liapor-brick",
			f"První řada cihel nosných stěn\nLiapor M AKU, 12 MPa",
		),
		(
			"base-plate",
			f"Základová deska\n"
			f"{FOUNDATION_BASE_PLATE_THICKNESS * 1000:.0f} mm",
		),
		(
			"ztracene-bedneni",
			"Ztracené bednění",
		),
		(
			"footing-cross",
			f"Základový pas\nbeton "
			f"{FOUNDATION_FOOTER_WIDTH * 1000:.0f} × "
			f"{FOUNDATION_FOOTER_HEIGHT * 1000:.0f} mm",
		),
		("wood-solid", "Dřevo"),
		("wood-siding", "Dřevěný obklad (pohled)"),
		("drywall-diagonal1", "Sádrokarton"),
		("thermal-impact-insulation", "podlahová izolace"),
		(
			"polystyrene-transparent",
			f"EPS Fasádní izolace"
		),
		(
			"perimeter-polystyrene",
			f"Perimetrická izolace"
		),
		(
			"rockwool-wave",
			"Minerální vata",
		),
		(
			"mdf-solid",
			"MDF záklop",
		),
		(
			"vapour-barrier-solid",
			"OSB záklop + parobrzda",
		),
	])

# Drawing - cut AA
if "aa" in sys.argv:
	drawing1 = aa_cut.add_drawing(
		house,
		"aa",
		z=3.5,
		radius=8,
		storeys=None,
		doors_closed=True,
		right_panel_width=60,
		section_outline_width=SECTION_OUTLINE_WIDTH,
		section_outline_color=SECTION_OUTLINE_COLOR,
	)
	drawing1.add_furniture_label(kamna)
	#drawing1.add_furniture_label(gauc)
	add_section_material_legend(drawing1)
	aa_x = drawing1.x
	aa_crosses_dormer_wall = min(wall_dormer.start[0], wall_dormer.end[0]) <= aa_x <= max(wall_dormer.start[0], wall_dormer.end[0])
	aa_garden_facade_wall = wall_dormer if aa_crosses_dormer_wall else wall_back_g

	drawing1.add_wall_insulation(
		wall_front_g,
		thickness=FACADE_INSULATION_THICKNESS,
		material="polystyrene",
		start_z=PERIMETER_TOP_HEIGHT,
		end_z=UPPER_FLOOR_START+NADEZDIVKA+0.15,
	)
	drawing1.add_wall_insulation(
		aa_garden_facade_wall,
		thickness=FACADE_INSULATION_THICKNESS,
		material="rockwool",
		start_z=PERIMETER_TOP_HEIGHT,
		end_z=UPPER_FLOOR_START+(DORMER_WALL_HEIGHT if aa_crosses_dormer_wall else NADEZDIVKA)+0.15,
	)
	drawing1.add_wall_insulation(
		wall_front_g,
		thickness=EXTERIOR_XPS_INSULATION_THICKNESS,
		material="xps",
		start_z=-1,
		end_z=PERIMETER_TOP_HEIGHT,
	)
	drawing1.add_wall_insulation(
		aa_garden_facade_wall,
		thickness=EXTERIOR_XPS_INSULATION_THICKNESS,
		material="xps",
		start_z=-1,
		end_z=PERIMETER_TOP_HEIGHT,
	)
	# Roof pitches measured against horizontal, with the same slopes as the
	# IFC roof planes. Keep the angular dimensions in clear space below them.
	add_roof_angles(drawing1)
	# Move each leader endpoint 100 mm into its referenced build-up so the
	# pointer visibly crosses the outer boundary instead of merely touching it.
	AA_COMPOSITION_MARKER_PENETRATION = 0.10
	composition_marker_clearance = (
		HEXAGON_MARKER_LEADER_REACH
		- AA_COMPOSITION_MARKER_PENETRATION
	)
	roof_composition_y = 0.5
	for plane in exterior_roof_planes_at(aa_x, side="street"):
		roof_composition_target = roof_batting_point(
			plane, x=aa_x, y=roof_composition_y, center_offset=roof_outer_face_offset,
		)
		roof_composition_angle = roof_angle_degrees(plane)
		roof_composition_normal_y = math.sin(math.radians(roof_composition_angle))
		roof_composition_normal_z = -math.cos(math.radians(roof_composition_angle))
		drawing1.add_hexagon_marker(
			(
				aa_x,
				roof_composition_target[1] - roof_composition_normal_y * composition_marker_clearance,
				roof_composition_target[2] - roof_composition_normal_z * composition_marker_clearance,
			),
			"SK3", rotation=-roof_composition_angle,
			name="AA roof composition SK3",
			line_length=1.3,
		)
	drawing1.add_hexagon_marker(
		(
			aa_x,
			HALF_DEPTH - 0.07,
			GROUND_FLOOR_THICKNESS
			+ composition_marker_clearance,
		),
		"SK1",
		#rotation=180,
		name="AA ground-floor composition SK1",
		line_length=1.1,
	)
	drawing1.add_hexagon_marker(
		(
			aa_x,
			HOUSE_DEPTH - 1.8,
			UPPER_FLOOR_START
			+ UPPER_FLOOR_THICKNESS
			+ composition_marker_clearance,
		),
		"SK2",
		name="AA upper-floor composition SK2",
		line_length=0.95,
	)
	wall_composition_z = (
		UPPER_FLOOR_START + UPPER_FLOOR_THICKNESS + 0.35
	)
	street_wall_outer_y = -FACADE_INSULATION_THICKNESS
	garden_wall_outer_y = HOUSE_DEPTH + FACADE_INSULATION_THICKNESS
	drawing1.add_hexagon_marker(
		(
			aa_x,
			street_wall_outer_y - composition_marker_clearance,
			wall_composition_z,
		),
		"SK4",
		rotation=-90,
		name="AA street-wall composition SK4",
		line_length=1.2,
	)
	drawing1.add_hexagon_marker(
		(
			aa_x,
			garden_wall_outer_y + composition_marker_clearance,
			wall_composition_z,
		),
		"SK5",
		rotation=90,
		name="AA garden-wall composition SK5",
		line_length=1.2,
	)
	street_foundation_outer_y = -EXTERIOR_XPS_INSULATION_THICKNESS
	drawing1.add_hexagon_marker(
		(
			aa_x,
			street_foundation_outer_y - composition_marker_clearance,
			-FOUNDATION_BASE_PLATE_THICKNESS - 0.25,
		),
		"SK6",
		rotation=-90,
		name="AA street-foundation-wall composition SK6",
		line_length=1.2,
	)
	aa_ridge_tiles = []
	for street_plane, garden_plane in exterior_ridge_planes_at(aa_x):
		ridge_tile_center = roof_batting_intersection(
			street_plane, garden_plane, x=aa_x, center_offset=roof_outer_face_offset,
		)
		aa_ridge_tiles.append(drawing1.add_ridge_tile(
			ridge_tile_center, width=RIDGE_TILE_WIDTH, rise=RIDGE_TILE_RISE,
			thickness=RIDGE_TILE_THICKNESS,
			name="AA ridge tile",
		))
	if exterior_roof_sections_at(aa_x):
		aa_frame_street, aa_frame_garden = framing_roof_planes_at(aa_x)
		aa_frame_has_dormer = not framing_is_lower(aa_x) and dormer_x_min <= aa_x <= dormer_x_max
		ridge_batting = roof_batting_intersection(
			aa_frame_street,
			aa_frame_garden,
			x=aa_x,
		)
		street_wall_batting = roof_batting_point(
			aa_frame_street,
			x=aa_x,
			y=0,
		)
		garden_wall_batting = roof_batting_point(
			dormer_roof if aa_frame_has_dormer else aa_frame_garden,
			x=aa_x,
			y=HOUSE_DEPTH,
		)
		frame_batting_segments = [("AA street roof batting", street_wall_batting, ridge_batting)]
		if aa_frame_has_dormer:
			garden_joint_batting = roof_batting_intersection(aa_frame_garden, dormer_roof, x=aa_x)
			frame_batting_segments.extend((
				("AA garden roof batting", ridge_batting, garden_joint_batting),
				("AA dormer roof batting", garden_joint_batting, garden_wall_batting),
			))
		else:
			frame_batting_segments.append(("AA garden roof batting", ridge_batting, garden_wall_batting))
		for batting_name, batting_start, batting_end in frame_batting_segments:
			drawing1.add_batting(
				*inset_roof_batting_segment(batting_start, batting_end),
				thickness=ROOF_BATTING_THICKNESS,
				name=batting_name,
				classes="roof-batting",
			)

	aa_inner_segment, aa_inner_profile_name, aa_inner_profile = inner_roof_section_at(aa_x)
	if not aa_inner_profile.get("ceiling_only"):
		aa_inner_street_plane = aa_inner_profile["street_plane"]
		aa_inner_garden_plane = aa_inner_profile["garden_plane"]
		aa_inner_garden_label = "Dormer" if aa_inner_profile_name == "dormer" else "Garden"
		if THERMAL_INSULATION_UNDER_RAFTERS > 0:
			under_rafter_street_top = roof_batting_point(
				aa_inner_street_plane,
				x=aa_x,
				y=aa_inner_street_plane.origin[1],
				center_offset=UNDER_RAFTER_BATTING_CENTER_OFFSET,
			)
			under_rafter_dormer_top = roof_batting_point(
				aa_inner_garden_plane,
				x=aa_x,
				y=aa_inner_garden_plane.origin[1],
				center_offset=UNDER_RAFTER_BATTING_CENTER_OFFSET,
			)
			under_rafter_street_eave = roof_batting_point(
				aa_inner_street_plane,
				x=aa_x,
				y=0.25,
				center_offset=UNDER_RAFTER_BATTING_CENTER_OFFSET,
			)
			under_rafter_dormer_eave = roof_batting_point(
				aa_inner_garden_plane,
				x=aa_x,
				y=7.75,
				center_offset=UNDER_RAFTER_BATTING_CENTER_OFFSET,
			)
			under_rafter_batting_segments = (
				(
					"AA street under-rafter batting",
					under_rafter_street_eave,
					under_rafter_street_top,
					roof_under_rafter_insulations[f"Street segment {aa_inner_segment}"],
				),
				(
					f"AA {aa_inner_garden_label.lower()} under-rafter batting",
					under_rafter_dormer_top,
					under_rafter_dormer_eave,
					roof_under_rafter_insulations[f"{aa_inner_garden_label} segment {aa_inner_segment}"],
				),
			)
			for batting_name, batting_start, batting_end, insulation in (
				under_rafter_batting_segments
			):
				drawing1.add_batting(
					*inset_roof_batting_segment(
						batting_start,
						batting_end,
						end_inset=UNDER_RAFTER_BATTING_END_INSET,
					),
					thickness=UNDER_RAFTER_BATTING_THICKNESS,
					name=batting_name,
					classes=(
						"roof-batting under-rafter-batting "
						f"under-rafter-owner-{insulation.element.GlobalId} "
						"under-rafter-target-projection"
					),
				)

			# The horizontal symbol spans purlin centre to purlin centre above their
			# tops, retaining the same thickness clearance as the sloped symbols.
			horizontal_batting_center_z = (
				aa_inner_profile["purlin_top_z"] + THERMAL_INSULATION_UNDER_RAFTERS / 2
			)
			aa_purlin_distance = aa_inner_profile["purlin_distance"]
			horizontal_batting_start = (
				aa_x, HALF_DEPTH - aa_purlin_distance, horizontal_batting_center_z,
			)
			horizontal_batting_end = (
				aa_x, HALF_DEPTH + aa_purlin_distance, horizontal_batting_center_z,
			)
			drawing1.add_batting(
				horizontal_batting_start,
				horizontal_batting_end,
				thickness=UNDER_RAFTER_BATTING_THICKNESS,
				name="AA horizontal ceiling insulation batting",
				classes="roof-batting horizontal-ceiling-insulation-batting",
			)

		# Nadezdivka
		drawing1.add_dimension(
			start=(BWT, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
			end=(BWT, roof_layer_height_at_y(aa_inner_street_plane, GYPSUM_PLASTERBOARD_BOTTOM, BWT, 0)),
			offset=-1)

		# Nadezdivka dormer
		drawing1.add_dimension(
			start=(HOUSE_DEPTH-BWT, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
			end=(HOUSE_DEPTH-BWT, roof_layer_height_at_y(aa_inner_garden_plane, GYPSUM_PLASTERBOARD_BOTTOM, HOUSE_DEPTH-BWT, 0)),
			offset=1)

	# Vyska stropu - podkrovi
	drawing1.add_dimension(
		start=(5.3, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
		end=(5.3, interior_ceiling_bottom_z_at(aa_x)),
		offset=0)

	# Vyska stropu - prizemi
	drawing1.add_dimension(
		start=(5.3, GROUND_FLOOR_THICKNESS),
		end=(5.3, ground_floor_height-CEILING_FINISH_THICKNESS),
		offset=0)
	drawing1.add_dimension(
		start=(5.3, BASEMENT_FLOOR_START),
		end=(5.3, BASEMENT_FLOOR_START+FOUNDATION_WALL_HEIGHT),
		offset=0)

	drawing1.render("aa.svg", pdf=PDF_AA)

# Longitudinal section through the ridge, perpendicular to AA.
if "bb" in sys.argv:
	drawing1 = bb_cut.add_drawing(
		house,
		"bb",
		z=3.5,
		radius=8,
		storeys=None,
		doors_closed=True,
		right_panel_width=60,
		section_outline_width=SECTION_OUTLINE_WIDTH,
		section_outline_color=SECTION_OUTLINE_COLOR,
	)
	add_section_material_legend(drawing1)
	# Dormer-rafter extensions cross this plane, but their insulation stops
	# at the purlin; only the main-roof ridge sections have batting here.
	bb_ridge_batting = drawing1.add_rafter_section_batting(
		main_roof_rafters + stronger_main_roof_rafters + dormer_short_rafters,
		size_factor=ROOF_BATTING_SIZE_FACTOR,
		end_inset=ROOF_BATTING_END_INSET,
		name="BB ridge insulation batting",
	)
	for wall, thickness, material in (
		(wall_1_g, FACADE_INSULATION_THICKNESS, "rockwool"),
		(wall_4_g, FACADE_INSULATION_THICKNESS, "polystyrene"),
	):
		drawing1.add_wall_insulation(
			wall,
			thickness=thickness,
			material=material,
			start_z=PERIMETER_TOP_HEIGHT,
			end_z=(ground_floor_height if wall is wall_4_g
			       else UPPER_FLOOR_START+OUTER_SUPPORT_WALL_HEIGHT+1.2),
		)
		drawing1.add_wall_insulation(
			wall,
			thickness=EXTERIOR_XPS_INSULATION_THICKNESS,
			material="xps",
			start_z=-1,
			end_z=PERIMETER_TOP_HEIGHT,
		)

	# vyska stropu nahore
	drawing1.add_dimension(
		start=(HOUSE_WIDTH-2, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
		end=(HOUSE_WIDTH-2, interior_ceiling_bottom_z_at(HOUSE_WIDTH-2)))
	# vyska stropu dole
	drawing1.add_dimension(
		start=(HOUSE_WIDTH-1.2, 0+GROUND_FLOOR_THICKNESS),
		end=(HOUSE_WIDTH-1.2, ground_floor_height-CEILING_FINISH_THICKNESS))

	# vyska oken na vikyri
	drawing1.add_dimension(
		start=(wall3_x-2, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
		end=(wall3_x-2, UPPER_FLOOR_START+NADEZDIVKA))

	# tloustka podlaha dole
	drawing1.add_dimension(
		start=(BWT, 0),
		end=(BWT, 0+GROUND_FLOOR_THICKNESS),
		offset=2.0)

	# tloustka podlaha nahore
	drawing1.add_dimension(
		start=(BWT, UPPER_FLOOR_START),
		end=(BWT, UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS),
		offset=2.0)
	# tloustka strop
	drawing1.add_dimension(
		start=(BWT, UPPER_FLOOR_START-CEILING_THICKNESS),
		end=(BWT, UPPER_FLOOR_START),
		offset=1.5)
	# tloustka zakladova deska
	drawing1.add_dimension(
		start=(BWT, BASEMENT_FLOOR_START-FOUNDATION_BASE_PLATE_THICKNESS),
		end=(BWT, BASEMENT_FLOOR_START),
		offset=1.5)
	drawing1.add_dimension(
		start=(HOUSE_WIDTH-2, BASEMENT_FLOOR_START),
		end=(HOUSE_WIDTH-2, BASEMENT_FLOOR_START+FOUNDATION_WALL_HEIGHT),
		offset=0)

	# podlaha spodni patro
	drawing1.add_elevation_dimension(
	    x0=-0.5, x1=-1,
    	z0=GROUND_FLOOR_THICKNESS, z1=GROUND_FLOOR_THICKNESS,
	)
	# podlaha horni patro
	drawing1.add_elevation_dimension(
	    x0=-0.5, x1=-1,
    	z0=GROUND_FLOOR_THICKNESS, z1=UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS,
	)
	# vyska stropu nahore
	drawing1.add_elevation_dimension(
	    x0=-0.5, x1=-1,
		z0=GROUND_FLOOR_THICKNESS, z1=UPPER_FLOOR_START+UPPER_FLOOR_THICKNESS+2.6,
	)
	# house height
	drawing1.add_elevation_dimension(
	    x0=-0.5, x1=-1,
		z0=GROUND_FLOOR_THICKNESS, z1=GROUND_FLOOR_THICKNESS+total_house_height,
	)

	drawing1.render("bb.svg", pdf=PDF_BB)

# Exterior west elevation (+X), outside the entire house including the open bay.
if "pohledy" in sys.argv or "pohled_zapad" in sys.argv:
	drawing1 = house.add_drawing(
		"pohled_zapad",
		x=max(HOUSE_WIDTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS,
		      max(end for _, end, _ in roof_over_rafter_x_ranges)) + 1.0,
		y=HALF_DEPTH,
		z=ground_floor_top + total_house_height / 2,
		radius=6,
		view="elevation",
		direction=(-1, 0, 0),
		storeys=[ground, upper, *roof_layer_storeys.values()],
		door_annotations=False,
		automatic_plan_annotations=False,
		doors_closed=True,
	)
	drawing1.render("pohled_zapad.svg", pdf=PDF_POHLED_ZAPAD)

# Exterior elevation from the street (negative Y), looking towards the garden.
if "pohledy" in sys.argv or "pohled_ulice" in sys.argv:
	drawing1 = house.add_drawing(
		"Pohled - Ulice",
		x=HOUSE_WIDTH / 2,
		y=STREET_ROOF_EAVE_Y - 1.0,
		z=ground_floor_top + total_house_height / 2,
		radius=8,
		view="elevation",
		direction=(0, 1, 0),
		storeys=[ground, upper, *roof_layer_storeys.values()],
		door_annotations=False,
		automatic_plan_annotations=False,
		doors_closed=True,
	)
	drawing1.render("pohled_ulice.svg", pdf=PDF_POHLED_ULICE)

# Exterior elevation from the garden (positive Y), looking towards the street.
if "pohledy" in sys.argv or "pohled_zahrada" in sys.argv:
	drawing1 = house.add_drawing(
		"Pohled - Zahrada",
		x=HOUSE_WIDTH / 2,
		y=max(GARDEN_ROOF_EAVE_Y, DORMER_ROOF_EAVE_Y) + 1.0,
		z=ground_floor_top + total_house_height / 2,
		radius=8,
		view="elevation",
		direction=(0, -1, 0),
		storeys=[ground, upper, *roof_layer_storeys.values()],
		door_annotations=False,
		automatic_plan_annotations=False,
		doors_closed=True,
	)
	# OpenCascade leaks this concealed beam's sill-level edge between the
	# dormer windows. Hide it and its bars only in this exterior drawing;
	# retain the concrete/steel geometry in the IFC and all other drawings.
	for beam in upper_ring_beams:
		if beam.source_wall == wall_back1_u:
			for element in (beam, *beam.reinforcement):
				drawing1.exclude_element(element)
	drawing1.render("pohled_zahrada.svg", pdf=PDF_POHLED_ZAHRADA)

# Exterior elevation from the high-roof end (-X), opposite the west view.
if "pohledy" in sys.argv or "pohled_vychod" in sys.argv:
	drawing1 = house.add_drawing(
		"Pohled - Východ",
		x=min(start for start, _, _ in roof_over_rafter_x_ranges) - 1.0,
		y=HALF_DEPTH,
		z=ground_floor_top + total_house_height / 2,
		radius=6,
		view="elevation",
		direction=(1, 0, 0),
		storeys=[ground, upper, *roof_layer_storeys.values()],
		door_annotations=False,
		automatic_plan_annotations=False,
		doors_closed=True,
	)
	drawing1.render("pohled_vychod.svg", pdf=PDF_POHLED_VYCHOD)

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

if "layers" in sys.argv:
	markdown_to_pdf(
		source="skladby.md",
		output=PDF_LAYERS,
	)
