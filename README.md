# House drawing helpers

`house_drawing.py` provides a small Matplotlib-based API for plans measured in
millimetres. Coordinates increase rightwards and downwards, like positions on a
sheet of paper.

```python
from house_drawing import Drawing

drawing = Drawing(-100, -100, 800, 1400)
drawing.add_wall(10, 10, 30, 200)
drawing.save("house_plan.svg")
```

`add_wall()` takes two opposite corners and draws a filled rectangle with a
diagonal hatch by default. The fill, outline and pattern can be changed:

```python
drawing.add_wall(
    100, 100, 125, 500,
    facecolor="#dbeafe",
    edgecolor="navy",
    hatch="xx",
)
```

The module also has `add_line()`, `add_box()`, `add_polygon()`, `add_ellipse()`,
`add_text()` and `add_dimension()` helpers. Use `drawing.ax` and `drawing.fig`
when direct access to Matplotlib is useful.

Ceiling sections are placed from left to right. `Beam`, `Wide`, and `Narrow`
have widths of 125 mm, 500 mm, and 375 mm respectively:

```python
from house_drawing import Beam, Narrow, Wide

drawing.add_ceiling(
    x=10,
    y=300,
    height=1200,
    objects=[Beam(), Wide(), Beam(), Narrow()],
)
```

`Beam` uses zero top and bottom offsets. `Wide` and `Narrow` are inset by
400 mm from both ends by default. Offsets can be overridden per object:

```python
Beam(top_offset=50, bottom_offset=-100)
Wide(top_offset=0, bottom_offset=0)
```

Every ceiling object is visible by default. Set `visible=False` to leave its
horizontal space empty without drawing the object:

```python
drawing.add_ceiling(
    x=10,
    y=300,
    height=1200,
    objects=[Beam(), Wide(visible=False), Beam(), Narrow()],
)
```

Brick walls are generated directly by `Drawing` and clipped to a polygon:

```python
drawing.add_brick_wall(
    polygon=[(0, 3000), (0, 0), (6000, 0), (6000, 3000)],
    brick_width=250,
    brick_height=250,
    half_rows=[0, 4, -2],
)
```

Row 0 is immediately above the pattern anchor, positive indexes continue
upward, and row -1 is immediately below it. Rows listed in `half_rows` use half
the normal brick height.

Run the example with:

```shell
python example_house.py
```

It creates both `house_plan.svg` and `house_plan.png`.

## Alternative house

`house2.py` is an independent model using the shared `ifc_utils` helpers.
Its `Basement` storey duplicates the selected `basement_source_walls`, including
partitions, as solid 300 mm `ztracene bedneni` walls. The two SDK walls forming
room 3's narrow end and the bathroom/hallway SDK partition are excluded,
together with their strip footings and
basement-ceiling ring beams. The new walls are centred beneath
the physical ground-floor wall bodies, accounting for face-based reference
lines. Their ends extend by half the increase in thickness to fill junctions.
Ground-floor doors, windows and the Liapor base course are not copied.
The basement hallway ceiling's front bearing also needs a separate structural
support after omitting the wall beneath the bathroom/hallway partition;
this is noted in the basement plan. No replacement support is modelled yet.

`BASEMENT_WALL_HEIGHT = 2.25 m` leaves `CEILING_THICKNESS = 0.21 m` above
the basement walls, immediately below the ground-floor layers at Z = 0.
That space contains the same five MIAKO layouts as above the ground floor,
in a separate `Basement ceiling` storey. The layouts reuse the original
beam positions, lengths, block rows and end offsets without recalculation;
their bottom is Z = −0.210 m and their top is Z = 0. The same stair opening
and unresolved beam junctions are retained. With the current settings:

| Element | Bottom Z | Top Z |
| --- | ---: | ---: |
| Basement walls | −2.460 m | −0.210 m |
| Basement ceiling, 210 mm | −0.210 m | 0.000 m |
| Foundation slab, 150 mm | −2.610 m | −2.460 m |
| Strip footings, 600 × 600 mm | −3.210 m | −2.610 m |

Ring beams occupy the 210 mm ceiling bands above all basement walls and
all ground-floor load-bearing walls. Their widths and centrelines follow
the physical wall bodies. The 115 mm partition between Pokoj 1 and 2 is
excluded at the ground-floor ceiling; its 300 mm basement support wall
receives a ring beam. These beams belong to the corresponding ceiling
storeys, so hiding a ceiling hides its ring beams as well.

The single `Base plate concrete` slab covers the outer footprint of the
thicker basement walls. Every basement wall has a centred concrete strip
footing, with returns at its ends. Footings belong to the separate
`Foundation` storey. Configure these elements with `BASEMENT_WALL_THICKNESS`,
`BASEMENT_SLAB_THICKNESS`, `FOUNDATION_FOOTING_WIDTH` and
`FOUNDATION_FOOTING_HEIGHT`; all lower elevations follow automatically.

Run `python3 house2.py basement found` to generate the basement and foundation
plans. Their PDFs are `D1.1.9. Půdorys suterénu.pdf` (`PDF_BASEMENT`) and
`D1.1.10. Základy.pdf` (`PDF_FOUND`) in the architectural folder; SVGs are
`projekt2/basement.svg` and `projekt2/found.svg`. The basement cut passes
through the middle of the basement walls.

The basement plan labels the five clear rooms `S.01`–`S.05` and includes a
room legend with areas and a width/depth dimension for every room. Names are
`Garáž` below room 3, `Schody` below the stairway, and `Skladovací prostor`
for the remaining rooms. Their boundaries and dimensions follow the actual
300 mm basement walls; no extra floor layers are added.

The foundation cut passes through
the middle of the strip footings, at
`FOUNDATION_FOOTING_BOTTOM_Z + FOUNDATION_FOOTING_HEIGHT/2` (currently
Z = −2.910 m). The foundation plan includes black dashed outlines of the
basement walls and blue dashed outlines of the ground-floor walls above,
with matching line-legend entries. Both plans show overall dimensions and wall/footing thickness.
`foundation` is also accepted as an alias for `found`.
The foundation plan includes a red dashed `Zemnící pásovina FeZn 30/35`
ring through the four exterior wall centrelines. Each corner has a diagonal
lead extending `GROUNDING_LEAD_LENGTH = 1.0 m` beyond the masonry corner;
a perpendicular lead also exits below the entrance-opening centre. The
entrance lead follows the actual door host and position. These are drawing
annotations, rather than 3D grounding hardware.

Run `python3 house2.py aa bb` for the two full-height sections, from the
footings through the roof. AA cuts at `X = HOUSE_WIDTH/2 + 0.1` and looks
towards +X; BB cuts at `Y = HOUSE_DEPTH/2` and looks towards -Y. Their shared
`CutDefinition` instances also place matching symbols on the ground, upper,
ceiling, roof, basement and foundation plans. PDFs are
`D1.1.11. Řez AA.pdf` (`PDF_AA`) and `D1.1.12. Řez BB.pdf` (`PDF_BB`)
in the architectural folder, with SVGs in `projekt2/aa.svg` and
`projekt2/bb.svg`. Regenerate the corresponding plans to update their symbols.

All exterior finishes belong to the separate `Facades` visibility storey.
`add_house_facades()` adds a grey perimeter band from `PERIMETER_BOTTOM_Z`
(the footing tops) to `PERIMETER_TOP_HEIGHT` (the finished ground-floor level),
and white finishes above it through both
storeys, including the gables and low upper walls. Each white side is one
continuous 5 mm covering, with openings projected from the ground and upper
walls and its top cut at the roof's rafter undersides. The panels sit outside
the 200 mm facade-insulation allowance. The recessed perimeter finish sits
outside `EXTERIOR_XPS_INSULATION_THICKNESS = 0.12` m of insulation on the
thicker basement walls. Pink hexagonal XPS hatching appears in the basement
plan and sections; section wool starts above the perimeter and continues
as one strip across the ceiling up to the wall-plate top at the eaves.
Openings on both storeys remain clear. Front/back panels cover the side-panel
ends at the corners. `FACADE_THICKNESS` controls the finish thickness.

`add_roof_edge_facades()` adds four equal-width timber strips along each
front/back slope and two eave boards. Their solid `Wood siding solid` colour
is `ROOF_WOOD_SIDING_COLOR = "#f2d08b"`, without a board-joint pattern; the
projected fill uses the same yellow in `plan.css`. The 20 mm boards fill
`ROOF_EAVE_SETBACK`, running from the plasterboard underside to the tile underside
and respecting the horizontal eave cut. A separate red trim on each front/back
slope runs from the tile-batten bottom to the tile top. It starts at the tile's
Y edge and extends outward by `ROOF_EDGE_TRIM_THICKNESS` (20 mm), matching the
tiles' 3D and drawing colours without a tile pattern. Rafters stop at the inside of the
eave boards. The upper plan explicitly includes the continuous white panels
despite their ground-floor host, while their separate storey allows all
facades and roof-edge boards to be toggled together in 3D.

`add_roof_gutters(gutter_diameter=GUTTER_DIAMETER, color=GUTTER_COLOR)` adds
two half-round, capped gutters without downpipes. They belong to the separate
`Rainwater drainage` storey and appear in exterior views, sections and the roof
plan. Positions and lengths follow the actual clipped tile geometry, including
the horizontal eave cut. `GUTTER_EDGE_GAP` sets horizontal clearance outside
the tile edge (5 mm); `GUTTER_DROP_BELOW_TILES` places the open rim below its
underside (20 mm). `GUTTER_DIAMETER` and `GUTTER_WALL_THICKNESS` initially use
150 mm and 1 mm. The default 3D colour and drawing fill are dark grey.
For another model, use `storey.gutter(name, start=(x0, y0, z), end=(x1, y1, z),
diameter=0.15, wall_thickness=0.001, end_caps=True, color="#666666")`.
The endpoints are world-coordinate centres of the open rim; the shell lies
below them. The IFC element is an `IfcPipeSegment` of type `GUTTER`, with
true circular arcs and persisted dimensions in `BBIM_Gutter`.

Roof extents are configured separately: `ROOF_EAVE_OVERHANG` measures the
east/west X overhang from the outside structural walls, while
`ROOF_GABLE_OVERHANG` measures the front/back Y overhang.
`ROOF_EAVE_DROP_BELOW_WALL_PLATE` sets the horizontal eave cut, and
`ROOF_EAVE_SETBACK` recesses the outer layers below the tiles by 20 mm.

Run `python3 house2.py pohledy` for all four exterior views on one A3 landscape
sheet at 1:200. `projekt2/pohledy.svg` and the architectural folder's
`D1.1.5. Pohledy.pdf` replace the four separate elevation PDFs. Both house
scripts share `pdf_utils.PDFFolder` for automatic numbering; the three former
view numbers are reserved so subsequent plans keep their existing names.
`POHLEDY_SCALE` sets
the shared scale denominator; each view has its own title and scale label.
The four `pohledy_sheet.add(...)` placements use normalized centre coordinates
in a 2×2 layout. The shared
`add_exterior_view()` helper includes the basement, ceilings, roof and
facades, closes doors for rendering, and suppresses plan annotations.

The four corner constants in `house2.py` define terrain heights above sea level:
`TERRAIN_STREET_EAST_ELEVATION`, `TERRAIN_STREET_WEST_ELEVATION`,
`TERRAIN_GARDEN_EAST_ELEVATION` and `TERRAIN_GARDEN_WEST_ELEVATION`.
East is global X = 0, west is X = `HOUSE_WIDTH`; street is Y = 0 and garden
is Y = `HOUSE_DEPTH`. `TERRAIN_PROFILES` derives each view's profile from its
two corner heights through `terrain_edge_profile()`: a straight slope along
the house and flat terrain beyond each end. Adjacent views share the same
corner heights, and the cameras handle their orientation on the page.
Profile positions use global X for street/garden and global Y for east/west.
`earth_to_z()` converts the heights using `GROUND_FINISHED_FLOOR_ELEVATION`
and the ground-floor build-up. Terrain is a drawing overlay with earth
hatching and a mask below the profile, rather than a 3D earth solid.

The east view replaces its terrain overlay with a foreground `stone-wall`
polygon. On the page, garden is left and street is right. The wall extends
`EAST_VIEW_STONE_WALL_OVERHANG` (2 m) beyond each facade outline. Its top is
flat at `EAST_VIEW_STONE_WALL_LEFT_ELEVATION` (418.8 m) up to the left house
outline, then falls to `EAST_VIEW_STONE_WALL_RIGHT_ELEVATION` (417.8 m) at the
right end. The bottom extends 100 mm below the footings. All profile heights
use `earth_to_z()`; no earth line or hatch is added in this view.

It starts with a ground-floor storey at Z = 0 and four 240 mm VPC
outer walls enclosing the `HOUSE_WIDTH × HOUSE_DEPTH` footprint. A 175 mm VPC
load-bearing wall along X separates the garden rooms, with clear depth
`GARDEN_ROOMS_DEPTH`; the street-side area uses the remaining space.
A 175 mm VPC load-bearing wall separates room 3 from the bathroom.
Two 100 mm SDK partitions define room 3's narrowed garden-side end, without
a Liapor base course or a ground-ceiling ring beam above them.
Pokoj 3 keeps `THIRD_ROOM_WIDTH = 3.47 m` clear below its garden-side end;
the top `THIRD_ROOM_NARROW_DEPTH` is only
`THIRD_ROOM_NARROW_WIDTH` wide, clearing the Pokoj 1 doorway.
The return's hallway-facing surface aligns with the street-side end of the
two side-wall openings. Its room-facing surface is `THIRD_ROOM_STEP_Y`;
the recess depth follows this position independently of the bathroom partition.
The floor polygons and dimensions follow the step. Its street window stays
centred on the wider street-side part.
The stairs occupy the west/right side, enclosed by a 175 mm VPC wall from
the front wall to the garden-room wall, with `STAIRWAY_WIDTH = 2.25 m`
clear beside the west exterior wall. The 2.20 m wide bathroom sits to their
left, next to room 3. A 100 mm SDK partition splits that area into hallway at
the garden end and bathroom at the front. `BATHROOM_DEPTH` is the
clear bathroom depth. The stairway wall is load-bearing VPC with a Liapor base
course; the bathroom/hallway partition is non-load-bearing SDK without a base
course or a ground-ceiling ring beam above it. Its room-facing surface and
door opening position along X follow the same bathroom dimensions.
A matching unfilled opening spans each bathroom side wall across the hallway,
running `HALLWAY_OPENING_LENGTH = 1.25 m` from the garden-room wall towards
the street. The bathroom's horizontal SDK partition keeps its own position.
Both openings stop `HALLWAY_OPENING_TOP_GAP = 0.25 m` below the ceiling
underside. The left wall continues above its opening and its basement wall
and footing follow the full extended wall length. The hallway's
continuous floor extends through it into the stair approach, follows room
3's stepped wall and excludes both stair-flight footprints. Its room area
and legend update from that same outline. Floor build-up still reaches the
bathroom partition and excludes the new solid side-wall segment below the opening.
The bathroom uses a two-column layout read from garden to street:
door/toilet, clear space/basin, shower/hot-water tank. The 900 mm door leaf
has a 1000 mm opening 125 mm from room 3's wall and swings into the
bathroom. The WC and basin face inward from the stairway wall. The shower is
900 × 900 mm. The bottom-right cell contains the 700 × 700 × 2000 mm
hot-water tank swapped from upstairs, with a 50 mm gap from the front wall.
The 600 × 550 × 900 mm water-meter box is in the basement, at its former
ground-floor X/Y position and on the basement finished floor. Fixtures start at the
finished floor, with the basin rim at 850 mm above it.
The entrance has a 900 mm leaf; `ENTRANCE_OPENING_WIDTH` controls its
construction opening. `ENTRANCE_OPENING_AT = 3.375 m` measures along the
west wall from its start at Y = `BWT`. Its dimension and inward entrance
arrow follow that wall. Its threshold and opening dimension use the finished-floor level,
`GROUND_FLOOR_THICKNESS`, preserving the door's 2.125 m overall height and
2.1 m clear height.
`add_entrance_stairs()` adds a ground-storey timber flight and landing outside
this west door, with the lower end toward the garden. `ENTRANCE_STAIR_RISERS`
and `ENTRANCE_STAIR_TREAD_LENGTH` control its steps; their rise follows the
actual door threshold and the west terrain interpolated at the flight's foot.
`ENTRANCE_STAIR_WIDTH` follows the opening width, and
`ENTRANCE_LANDING_DEPTH`/`ENTRANCE_LANDING_THICKNESS` set the landing geometry.
The outer railing continues around the landing's street edge. The ground plan
shows the stair symbols, uphill walking arrow and combined stair notes.

A centred 115 mm VPC partition along Y splits the garden section into equal
rooms, each with 4.2025 m clear width. The common finishing pass gives every
ground-floor masonry wall a Liapor base course. Partitions remain non-load-bearing.
Pokoj 1 and 2 have inward-opening 900 mm doors in 1000 mm construction
openings through the garden-room dividing wall. Each opening's nearest edge
is 125 mm from the house centreline (`HOUSE_WIDTH/2`), controlled by
`GARDEN_DOOR_CENTER_CLEARANCE`; the hinges face the centre partition.
Pokoj 3 also has a 900 mm inward-opening door in a 1000 mm construction
opening at its narrow garden-side end. The opening's garden-side edge is
375 mm from the room 1 face of the garden-room dividing wall, controlled by
`THIRD_ROOM_DOOR_GARDEN_CLEARANCE` (200 mm from the room 3 face with the
current 175 mm wall).
Opening dimensions are placed inside the rooms.
Basement support walls will be added in a later step.
Five room floors (`0.01–0.05`: Pokoj 1, Pokoj 2, Pokoj 3, Chodba, Koupelna)
use 120 mm insulation and 65 mm screed/finish,
starting at Z = 0. The stairway room has no floor build-up. Floor polygons
follow the clear room boundaries, and their measured areas supply the plan
labels and room legend from the same `ground_room_floors` collection.
Wall height is
`GROUND_WALL_BASE_COURSE_HEIGHT + 2.625 m` (currently 2.825 m), including the
200 mm Liapor base course.

The stairway has two 1.00 m wide flights, each with **eight risers and seven
treads**, all with 270 mm treads.
The lower flight runs toward the front wall (−Y); the upper returns toward
the garden (+Y), with its left edge touching the stairway/bathroom wall.
The landing is against the front wall and measures 2.25 × 1.05 m.
Both runs are 1.89 m; the flights are separated by
`STAIR_FLIGHT_GAP = 0.25 m`; the outside flight touches the west wall.
The basement flights keep the same gap and divide the remaining clear
stairwell width equally (978.75 mm each with the current basement walls).
Both flights are concrete with 150 mm
sloped waists; there is no general floor build-up in the stairway room.
The ground-floor plan shows a dashed entrance-clearance curve beyond the flights:
two quarter circles of radius `STAIR_FLIGHT_WIDTH`, centred on the inner
flight corners, joined by a straight segment across `STAIR_FLIGHT_GAP`.
This is a drawing annotation only.
Both floor plans dimension any clear gap from the stairway's west edge to
the inside west wall. The terminal prints the plasterboard inner-face
height above the finished upper floor at the west corner of the upper
stair arrival, including that point's X/Y coordinates.

Five MIAKO assemblies cover the downstairs rooms. Pokoj 1 and 2 share one
assembly with beams along Y, centred over their separating partition.
Pokoj 3 has street and garden assemblies with beams along X, split at
`BATHROOM_PARTITION_Y`, the bathroom-facing edge of the bathroom/hallway
wall. Both room 3 assemblies span to the full load-bearing bathroom wall,
passing above the SDK partitions. Chodba has beams along Y from that
load-bearing wall across the hallway and stair approach. Its front bearing
requires a separate structural support above the SDK partition and stair
approach. `HALLWAY_CEILING_SUPPORT_Y` and `HALLWAY_CEILING_SUPPORT_WIDTH`
retain the previous ceiling layout independently of the partition thickness.
The full support line is marked blue and dashed in the ceiling plan and
noted as not yet designed; no structural member is added there.
Koupelna has beams along X; its junction with Pokoj 3's beams
is deliberately left unresolved for now. Opposing hallway and garden-room
beam ends also overlap on their shared 175 mm wall; that junction remains
unresolved and is noted in the ceiling drawing.

`design_miako_structure()` starts and ends each layout with a 170 mm beam,
alternating beams and 455 mm wide or 330 mm narrow block rows. It accepts
a total width difference of up to `CEILING_LAYOUT_TOLERANCE = 0.07 m`,
first trying all-wide blocks and otherwise minimising the number of narrow
rows. Narrow rows are grouped in the middle; among layouts with the same
number of narrow rows, the closest width wins. Layouts are centred over
their covered widths, except the two Pokoj 3 assemblies: their adjoining
edges stay fixed at the split so their parallel edge beams do not overlap.
`add_miako_ceiling()` adds at least
`CEILING_BEAM_BEARING = 0.125 m` at each end and rounds the full beam length
up in `CEILING_BEAM_LENGTH_STEP = 0.25 m` increments. Blocks stop at the
clear-span boundaries. The terminal reports beam counts/lengths, block-row
counts, fitted/target widths, signed width differences and end bearings.
The ceiling plan dimensions and beam schedule use the same assemblies.
All five use 150 mm blocks and 60 mm topping, extending from the ground
wall top to `UPPER_FLOOR_START`, in a separate `Ceiling` storey that can be
hidden in the 3D viewer.
Both ground and ceiling plans show 200 mm Rockwool around all four exterior
walls (`FACADE_INSULATION_THICKNESS`). The shared `add_facade_insulation`
helper uses opening-aware drawing annotations, closing the corners without
adding insulation solids or changing the 3D wall construction.

`CEILING_THICKNESS = 0.21` and
`UPPER_FLOOR_THICKNESS = 0.03 + CEMFLOW_AND_FINISH_THICKNESS` define the
levels; no upper-floor slab is created. The total stair
rise is `ground_floor_height + CEILING_THICKNESS + UPPER_FLOOR_THICKNESS -
GROUND_FLOOR_THICKNESS`, shared equally between 16 risers. With the current
parameters the rise is 2.945 m (184.0625 mm per riser), the middle landing
is at Z = 1.6575 m and the upper finished level at Z = 3.130 m. The drawing
shows both flights, one continuous ascent arrow, and a stair configuration note.
Wooden banisters run along the inner edges of both flights, also on the
basement stairway. Each `railing_path("right", inset=STAIR_RAILING_INSET)`
sets the slope and seats posts and balusters on the actual treads. The shared
`STAIR_RAILING_INSET` controls the centreline inset onto each flight.
`STAIR_RAILING_HEIGHT = 1.0` controls the vertical handrail height.
Horizontal railings close the 250 mm flight gap at both middle landings
and between the ascending and descending flights at ground-floor level.
Another guards the 1.25 m edge from the upper stair arrival to the west wall.
The ground-floor railings are explicitly included in the
upper-floor plan; it is visible in both floor drawings and the 3D model.
The living-room layout is retained. The relocated stairs are to its right
and no longer overlap its floor. The technical room occupies the space
between the stairs and the living-room wall, with the hallway beyond the
stair arrival.

Pokoj 1 and 2 have 1.75 m windows centred on their back-wall segments, with
the opening starts rounded to the nearest 0.125 m along the wall. Pokoj 3 has
an exactly centred 1.75 m front-wall window. The bathroom has a
0.75 × 0.75 m front-wall window with a 250 mm gap to its right wall. All window tops are at
`GROUND_WALL_BASE_COURSE_HEIGHT + 2.25 m`; bedroom sills use
`GROUND_WALL_BASE_COURSE_HEIGHT + 0.875 m`. The west-window sill follows from
its 0.75 m height. All window frames use white in 3D.
Exterior views fill visible window glazing light cyan (`#d9f4f7`), with
white frames. The colour is in `bonsai_scripts/assets/plan.css`; the renderer
identifies glazing using the native surface ray hit and its IFC aspect style,
preserving Bonsai's occlusion. Plan drawings and 3D colours are unchanged.
All four windows have construction-opening dimensions outside their host
walls: width above the line and height/sill below, relative to the finished
floor. The room legend includes summed nominal window area (modelled width
times height) and its percentage of each room's floor area.
`ground_room_windows` assigns windows to the three remaining room IDs;
the right panel is 60 mm wide to keep the extra column readable.

Run `python3 house2.py` to export `house2.ifc`. Run
`python3 house2.py ground` to also render `projekt2/ground.svg` and
`projekt2/D1.1. Architektonicko Stavební Řešení/D1.1.1. Půdorys 1.NP.pdf`
(A4 landscape, 1:100), matching the original project's PDF directory structure.
Run `python3 house2.py ceiling` for `projekt2/ceiling.svg` and
`projekt2/D1.1. Architektonicko Stavební Řešení/D1.1.2. Strop nad 1.NP.pdf`.
The ceiling plan shows the wall context, beam spacing, overall and slab
dimensions, and a MIAKO beam schedule. Pass both `ground ceiling` to generate
both plans in one run.

The `Upper floor` storey starts at `UPPER_FLOOR_START` (Z = 3.035 m), with
four 240 mm VPC exterior walls aligned above the ground-floor walls. The
east/west wall height is `NADEZDIVKA = 1.125 + UPPER_RING_BEAM_HEIGHT`;
with the initial 240 mm ring-beam-height parameter this is 1.365 m,
reaching Z = 4.400 m. The front/back masonry follows both roof planes at
`RAFTER_Z_OFFSET` near the sides and is capped horizontally at
`purlin_bottom_z = PURLIN_Z - PURLIN_SIZE[1]/2`. The upper facade panels
retain their roof-shaped tops all the way to the ridge. The existing wall
X ranges and thicknesses are preserved. A common horizontal concrete band
of height `UPPER_RING_BEAM_HEIGHT` ends at `UPPER_FLOOR_START+NADEZDIVKA`,
directly below the wall plates. It replaces masonry in the four exterior
walls and both 1.25 m garden-side VPC sections, inherits each wall's width, and is
interrupted by any opening crossing the band. The existing ring-beam
helper supplies schematic reinforcement. Upper beams belong to the
`Upper floor` storey and are included explicitly in the roof plan.
The upper plan includes the same drawing-only Rockwool,
material legend, and overall and inside dimensions. Both existing stair
flights and the middle landing are explicitly included with their plan
symbols and one continuous ascent arrow, retaining their ground-floor storey.
Two upper-floor SDK partitions enclose a rectangle in the front-west
corner; the remaining L-shaped area is the living room.
`LIVING_ROOM_WIDTH` is the clear width of its east-side strip.
`LIVING_ROOM_DEPTH = HOUSE_DEPTH - BWT - LIVING_ROOM_WALL_FRONT_Y -
DRY_WALL_WIDTH` is the clear depth of its back/garden-side strip.
The horizontal SDK partition's garden face aligns with the garden face of
the nearby 1.25 m VPC section. It extends between the vertical partition and
that section, whose centre stays over the ground-floor load-bearing wall.
The vertical partition has two segments, stopping
at the near chimney face and continuing from its far face to the horizontal
wall. The chimney footprint is left clear. The former two short SDK walls
forming the hallway step are removed; the upper plan dimensions the actual
clearance from the stair arrival to the living-room wall's facing surface.
With `DRY_WALL_WIDTH = 0.10`, the excluded rectangle has clear dimensions
`HOUSE_WIDTH - 2*BWT - DRY_WALL_WIDTH - LIVING_ROOM_WIDTH` by
`HOUSE_DEPTH - 2*BWT - DRY_WALL_WIDTH - LIVING_ROOM_DEPTH`.
The non-load-bearing walls start at the upper-storey datum, meet without
overlap, and are clipped to the underside of the sloped plasterboard.
The back partition has a clearance where the west purlin passes through it.
The upper plan dimensions the two living-room strips and includes the SDK
material legend.
The living room has an L-shaped floor build-up (`living_room`, room `1.01`,
"Obývací pokoj") following the clear inside faces of the partitions and
exterior walls. It uses 30 mm impact insulation and 65 mm screed/finish,
from Z = 3.035 to 3.130 m. Its 48.90 m² area supplies the room label and
room legend via `upper_room_floors`. The stair arrival currently crosses this
layout; the upstairs layout will be revised separately.
The living room has two 1.50 m back windows (`UPPER_BACK_WINDOW_WIDTH`),
centred as a pair with a 1.00 m gap (`UPPER_BACK_WINDOW_GAP`),
and a 1.50 m front window. The front opening
starts 2.00 m from the east wall's inside face
(`UPPER_FRONT_WINDOW_EAST_CLEARANCE`). Their 1.375 m height and 0.890 m sill
above the finished floor match the ground-floor room windows; dedicated
`UPPER_WINDOW_SILL_HEIGHT` and `UPPER_WINDOW_TOP_HEIGHT` hold storey-relative
coordinates. Both have opening dimensions in the upper plan, and
`upper_room_windows` supplies their combined area to the room legend.
`upper_room_floors` contains the living room (`1.01`), front Technika (`1.02`),
hallway (`1.03`) and rear Zachod (`1.04`). A 100 mm SDK cross-wall is centred
on the first west-purlin post, with a clearance for the post itself. It joins
the vertical living-room wall to the parallel stair-side wall. The latter
runs from the cross-wall's street face to the horizontal living-room wall;
its stair-facing side is flush with `STAIR_LEFT_X`. In front of the cross-wall,
a timber banister replaces it, with its posts entirely on Technika's floor.
`TECHNIKA_RAILING_START_FROM_FRONT = 1.5` sets its start distance from the
front wall's inside face; its garden end meets the cross-wall's street face.
The rear toilet floor excludes the chimney footprint and all room floors
end at the appropriate partition faces.
The plan dimensions the 1120 mm clear toilet-room width and both face-to-face gaps
beside the first west-purlin post. A further dimension measures the clear X
distance from the chimney to the stair-side partition. This wall has a
700 mm sliding door in an 800 mm opening, sliding towards the street.
`TECHNIKA_SLIDING_DOOR_Y = None` aligns the opening's garden edge with the
chimney's street face; a number sets the absolute Y coordinate of its start instead. Dedicated
`TECHNIKA_SLIDING_DOOR_WIDTH` and `TECHNIKA_SLIDING_DOOR_OPENING_WIDTH` control its size.
The two 1.25 m garden-side VPC sections stay centred above the ground-floor
garden-room load-bearing wall, including its material offset and thickness.
The horizontal SDK and nearby VPC section share the same garden face.
The floor outlines follow the new wall faces, fill the removed step, and
exclude the chimney footprint. The upper plan also
dimensions the clear gap from the rear west post to the living-room wall.
A 900 mm living-room door in a 1000 mm opening is centred on the upper
stairway exit and hosted by the horizontal living-room SDK wall. It swings
towards the garden (+Y), with an opening dimension on the living-room side.
The vertical SDK wall between the living room and Technika has no doorway.
The upper room floors share the living room's 30 mm impact
insulation and 65 mm screed/finish, and supply labels and room-legend rows
from their measured outlines.
The upper hallway has the old house's 700 × 700 × 800 mm washing machine
beside the west exterior wall, centred in the half nearest the stair arrival.
The former street-side VPC pair is removed. The washing machine retains its
position, using the downstairs bathroom partition as its reference.
A basin sits beside the west wall, gardenward of the washing machine in
the hallway's second half, with a 50 mm gap before the nearby VPC segment.
It faces into the hallway (-X, `rotation=-90`).
`UPPER_BASIN_SIZE` controls its plan size;
its top remains 850 mm above the finished floor. The technical room's front end contains the
1000 × 500 × 1500 mm recuperation unit against the front wall, centred in Technika.
The toilet faces the garden and stands gardenward of the first west-purlin
post; `upper_toilet_center` controls its placement. The 800 × 500 × 900 mm
hydrobox swapped from downstairs stands beside the living-room wall, with
a 50 mm wall gap, centred in Y between the recuperation unit and toilet.
Equipment starts at the finished upper floor;
`upper_fixture_wall_gap` controls its wall spacing (currently 50 mm).
The Technika label sits between the recuperation unit and hydrobox; Zachod has
its own label behind the toilet.
When a plan cuts below a door's raised swing symbol, export lowers only
the 2D symbol just beneath the cut. This keeps low upper-floor cuts from
hiding the bathroom door, without changing its 3D position or floor levels.
The kitchen follows the living-room side of the vertical SDK partition,
from garden to street: cooker, sink, dishwasher, fridge, then worktop to the front
wall. The three appliances use the old house's 640 × 640 × 750 mm boxes;
the remaining worktop is 640 mm deep and 750 mm high, with its length
calculated from the available space. `KITCHEN_WALL_GAP = 0.03 m` keeps
the units off the SDK and front wall. The cooker and sink retain the old
700 mm centre spacing (60 mm gap), and the boxes start 30 mm above the
finished upper floor as in the original kitchen.
`FRIDGE_SIZE = (0.64, 1.0, 1.95)` controls the fridge; the adjacent worktop
shortens automatically to make room. The dining table reuses the old house's
four-seat asset, aligned with the cooker between it and the east wall.
`DINING_TABLE_SIZE = (1.25, 1.7)` includes the chairs, and
`DINING_TABLE_WALL_GAP = 1.0` sets its clearance from the east wall's inner face.
The attic `kamna` uses the original house's stove placeholder, controlled by
`STOVE_SIZE = (0.60, 0.50, 1.50)`. Its X centre matches `kitchen_center_x`;
its back face has `STOVE_WALL_GAP = 0.20 m` clear to the living-room side
of the horizontal SDK wall. It faces the back/garden wall (+Y).
Two wooden wall plates (`wall_plate_east`, `wall_plate_west`) sit directly
on the east and west upper walls, centred across their 240 mm thickness.
`WALL_PLATE_SIZE = (0.16, 0.12)` sets their width and height, matching the
original house. `WALL_PLATE_OVERHANG = 0.30` extends them beyond both outside
front/back wall faces: Y = −0.30 to 9.05 m, length 9.35 m. Their bottoms
are at Z = 4.400 m and tops at Z = 4.520 m.
Two wooden purlins (`purlins`) run parallel to the wall plates at
`PURLIN_X_POSITIONS = (3.0, HOUSE_WIDTH-3.0)`. Their section is
`PURLIN_SIZE = (0.16, 0.24)`. Despite its legacy name,
`PURLIN_CENTER_HEIGHT = 3.65 m` specifies their **top** above the upper-storey
datum (the ceiling top). `PURLIN_Z` is the derived centreline elevation.
Changing the purlin height keeps its top and roof slope fixed and adjusts
the post height below it.
They share `WALL_PLATE_OVERHANG`, so their Y range is also −0.30 to 9.05 m.
Each purlin has configurable vertical timber posts (`purlin_supports`) in the
upper storey. `PURLIN_SUPPORT_Y_POSITIONS` contains a nonempty tuple of absolute
Y coordinates per purlin. For one post per purlin at the house centre, use
`((HOUSE_DEPTH/2,), (HOUSE_DEPTH/2,))`; two-post layouts remain supported.
`PURLIN_SUPPORT_SIZE = (0.16, 0.16)` sets their cross-section. They run from
the ceiling top (`UPPER_FLOOR_START`, before the floor build-up) directly
to the purlin undersides. X-aligned connecting beams
(`purlin_connection_beams`) span between the purlin inner faces, with their
centrelines at `PURLIN_Z`, level with the purlin centrelines.
`PURLIN_CONNECTION_BEAM_SIZE = (0.12, 0.20)` controls their section.
`PURLIN_CONNECTION_Y_POSITIONS` is shared with the simulator: one beam
aligns with each distinct post Y coordinate, and two sit inside the front/back
gable walls.
`PURLIN_CONNECTION_WALL_CLEARANCE = 0.10` measures the clear wall-to-beam
gap; each end beam's centre includes half its 120 mm width.
The purlin bears directly on its post; the connector is attached at its side.
East/west posts can have different Y coordinates and different counts. Each
post has three 45-degree timber braces: two along Y beneath its purlin and one
along X toward the opposite purlin, beneath the connecting beam.
`PURLIN_BRACE_SIZE = (0.10, 0.12)`
sets the brace section, and `PURLIN_BRACE_DROP = 0.80` sets the anchor's drop
below the post top. Brace ends are cut flush to the post face and beam
underside. Braces that would extend beyond a purlin end are skipped individually.
The upper plan shows the post cut footprints; the roof drawing
and timber schedule include the posts, connecting beams and all fitting braces.
Intersecting SDK partitions and inner roof finishes have clearance openings
matching the new timber solids, so the frame remains exposed at penetrations.
The upper plan dimensions only the east support row: inside front-wall face
to first-post centre, between successive post centres when there is more than
one, and last-post centre to inside back-wall face. One horizontal dimension
shows the clear distance from the front east post's face to the common front
edge of the kitchen run.
All endpoints follow the configured post and kitchen positions.
The roof has 14 pairs of `RAFTER_SIZE = (0.08, 0.20)` rafters, with their
centres at `RAFTER_FIRST_Y = -0.125` through
`RAFTER_LAST_Y = HOUSE_DEPTH + 0.125`. There are six 670 mm gaps, one
central 960 mm gap, and six more 670 mm gaps. Both slopes are defined by
the outer top corners of their wall plate and purlin, meeting at
`X = HOUSE_WIDTH/2`. `RAFTER_Z_OFFSET = -0.05` sets the rafter bottom
50 mm below that reference plane, measured perpendicular to the slope.
`ROOF_EAVE_OVERHANG = 0.30` controls the initial X overhang independently
of the Y spacing. Each rafter is cut vertically at its eave and the ridge;
the members are grouped under the roof in the upper-floor storey.
`ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.30` adds the original house's
horizontal cut, measured below the wall-plate bottom. It applies to the
rafters and roof build-up alongside the retained vertical overhang limit.
Layer source extents and tile-batten rows respect both limits.
Both slopes use the previous house's build-up, with interior
layers clipped at the inner purlin faces and horizontally at the purlin
undersides: 200 mm
under-rafter wool, 15 mm OSB/vapour barrier, a 30 mm empty service space,
and 25 mm plasterboard. Above the rafters are 15 mm MDF, 1 mm underlay,
60 × 60 mm counter-battens at every rafter, 60 × 40 mm tile battens at
320 mm slope spacing, and 30 mm roof tiles with the shared tile pattern.
The materials and IFC colours match `house_ifc.py`. As in that model,
the between-rafter wool space has no additional solid overlapping the rafters.
The sloped inner sheets and wool run from the inside wall faces to the
purlins. Between the purlins' inner faces, a horizontal roof plane carries
25 mm plasterboard whose underside, `FLAT_GYPSUM_PLASTERBOARD_BOTTOM_Z`,
meets the sloped plasterboard underside at the purlins' inner faces.
This height is calculated from the offset roof plane. Above it are a
30 mm service void and the 15 mm vapour barrier, whose top is
`FLAT_VAPOUR_BARRIER_TOP_Z`. There is no horizontal under-rafter
insulation solid: that insulation belongs between the collar ties. Both
horizontal layers share their corresponding `Roof - …` visibility storeys
with the slopes, receive timber-clearance openings, and are penetrated by
the same chimney opening. Outer roof layers still continue to the ridge.
The upper plasterboard partitions are clipped to the underside of this
horizontal ceiling as well as to the sloped finishes.
`ROOF_GABLE_OVERHANG = 0.25` sets the
front/back tile extents; `ROOF_EAVE_SETBACK = 0.02` leaves the same 20 mm
setback beneath the tiles for boards and battens. Each new layer type has
its own `Roof - …` visibility storey, including both roof slopes.
The chimney starts at the upper-floor storey datum, centred at
`CHIMNEY_CENTER`. Its back face touches the stair-facing surface of the
horizontal living-room wall, at `LIVING_ROOM_WALL_FRONT_Y`; its body is on
the stairs side. The vertical SDK wall stops at the chimney's front face,
and the kitchen follows the shortened wall. There is no chimney-to-stair
clearance parameter or dimension. It reuses the original model's
400 mm square body, 200 mm circular flue and material/colour. Its top is
`CHIMNEY_ABOVE_ROOF = 0.65 m` above the roof-tile ridge. The roof receives
an exact vertical shaft opening; the SDK partitions meet the chimney
without intersecting it. The upper plan includes the chimney/flue
symbol. `SHOW_CHIMNEY_PLANNING_MARKER = True` also adds a temporary
flue symbol and dashed body footprint to the basement, ground and ceiling plans.
Set it to `False` to hide these planning markers. The physical chimney
still begins upstairs. The reusable helper is
`drawing.add_chimney_annotation(chimney, projected=True)`.
`SHOW_PURLIN_SUPPORT_PLANNING_MARKERS = True` adds green crossed rectangles
for all timber-post footprints to the same plans. These follow the actual
post positions and section size; set the flag to `False` to hide them.
Run `python3 house2.py roof` for the roof framing plan (`projekt2/roof.svg`)
and `projekt2/D1.1. Architektonicko Stavební Řešení/D1.1.4. Krov.pdf`.
`COLLAR_TIE_SIZE = (0.05, 0.15)` sets paired collar ties, one on each side
of every rafter pair. Their bottom is at the purlin top; their ends are cut
by the upper rafter-face planes. They belong to the upper-floor storey and
appear in the roof drawing and timber schedule. All 28 ties are retained
for layout review, including the garden-side tie at rafter pair 7 that
currently crosses the chimney.
It includes only the structural timber, exterior wall context and chimney,
with real material fills, rafter spacings, support centre distances and an
automatically measured timber schedule. Roof covering and interior finishes
are excluded from this framing view. Use `ground ceiling upper roof` to
generate all four drawing targets in one run.
Run `python3 house2.py upper` to create `projekt2/upper.svg` and
`projekt2/D1.1. Architektonicko Stavební Řešení/D1.1.3. Půdorys podkroví.pdf`.
Use `python3 house2.py ground ceiling upper` to generate all three plans.

## IFC wall types and material layers

`ifc_utils.py` can define a reusable wall construction as an `IfcWallType`.
Each layer is an ordered `(material_name, thickness_in_metres)` pair. Looking
from a wall's `start` point towards its `end` point, layers are listed from left
to right:

```python
from ifc_utils import House

house = House("My house")
exterior_wall = house.wall_type(
    "Brick and rock wool",
    layers=[
        ("Brick", 0.12),
        "axis",
        ("Rock wool", 0.10),
    ],
)

ground = house.storey("Ground floor", elevation=0)
wall_1 = ground.wall((0, 0), (5, 0), wall_type=exterior_wall, height=2.8)
wall_2 = ground.wall((5, 0), (5, 4), wall_type=exterior_wall, height=2.8)
ground.connect_wall(wall_1, wall_2)
house.write("house.ifc")
```

Pass `mirror_x=True` to mirror the exported house and its drawings across the
global `x=0` plane:

```python
house = House("My mirrored house", mirror_x=True)
```

The Python-side coordinates remain unchanged, including values returned by
walls, stairs, and roof planes. Only written IFC files and rendered drawings
are mirrored, so existing coordinate calculations need no special handling.

## Concrete girders with an embedded HEB

```python
girder = upper.girder(
    "Průvlak", start=(1, 2, 3.1), end=(5, 2, 3.1),
    width=0.30, height=0.35, heb=180,
)
```

The two points are **world XYZ centreline endpoints**, just like `beam()`;
the storey's elevation is not added to them. Width and height are in metres,
perpendicular to the span, with the height axis kept as upright as possible.
The HEB runs the full span, centred horizontally and vertically inside the
concrete block. Both ends are flush. A profile too large for the concrete
envelope is rejected.

`heb` takes the nominal size in millimetres (`180`) or its name (`"HEB180"`,
`"HE 180 B"`, case-insensitive). `steel_profiles.py` holds the standard HEB
sizes from 100 through 1000, using the [ArcelorMittal Orange Book dimensions](https://orangebook.arcelormittal.com/node/16),
including root fillets. The MIAKO HEB180 profile uses the same library.

The returned `Girder` is a `Beam`/`IfcBeam` whose concrete body excludes the
steel volume. Its embedded `IfcBuildingElementPart` has its own steel
material and geometry. Use `girder.concrete` and `girder.steel` to access
the two solids, and `girder.heb_section` for section dimensions in metres.
`concrete_color`, `steel_color` and `transparency` control their 3D styles;
the defaults are gray concrete and dark gray steel. Sections distinguish
the two materials. Drawing inclusion/exclusion of the girder also handles
its embedded steel, including in drawings scoped to another storey.

## MIAKO layout axis

Insert one zero-width `"axis"` marker in `miako_slab(structure=...)` to put
the supplied `start`–`end` line inside the layout:

```python
slab = upper.miako_slab(
    "Ceiling", start=(0, 0), end=(4, 0), top=0, direction=(0, 1),
    structure=["beam", "wide", "beam", "axis", "beam", "narrow", "beam"],
)
```

Items after `"axis"` lie on the side selected by `direction`; items before
it lie on the opposite side, in their original order. Here, the first group
occupies Y = −0.795 … 0 m and the second Y = 0 … 0.670 m. The marker uses no
space: the preceding item ends exactly at the line, and the following item
starts there. For `direction=(0, -1)`, the sides are reversed.

The marker also works between consecutive `"heb180-"` sections, placing one
on each side of the line. `slab.width_before_axis` and `width_after_axis`
report the two extents. Use at most one marker; without it, all items are
placed on the `direction` side as before.

## MIAKO HEB180 inserts

Use `"heb180+"` or `"heb180-"` between `"beam"` items in `miako_slab(structure=...)`:

```python
structure=[
    "beam", "wide", "beam",
    "heb180+", "beam",
    "narrow", "beam",
]
```

Both tokens are case-insensitive and create an HEB180 parallel to the MIAKO
beams, for their full start-to-end span. Their placements differ:

- `"heb180+"`: bottom flange at `beam_height` above the slab bottom, with
  30 mm bearing on each neighbouring beam. It adds a **120 mm gap**;
  `["beam", "heb180+", "beam"]` is 460 mm wide.
- `"heb180-"`: bottom aligned with the slab and beam bottoms, without any
  overlap. It adds the full **180 mm width**;
  `["beam", "heb180-", "beam"]` is 520 mm wide. Multiple minus entries may
  sit side by side between the flanking beams, for example
  `["beam", "heb180-", "heb180-", "beam"]` is 700 mm wide.

A zero-width `"axis"` marker may occur between these items without changing
their placement. Bare `"heb180"` is rejected; choose the desired variant.

The native IFC I-profile uses the [ArcelorMittal HE 180 B dimensions](https://orangebook.arcelormittal.com/node/16):
180 × 180 mm, 8.5 mm web, 14 mm flanges and 15 mm root fillets. Its top must
fit within `block_height + topping`. `steel_color` controls the 3D color
(default dark gray); cut steel is also dark gray. In both variants the
concrete reaches the slab bottom throughout the HEB gap; it stops at the
precast body tops over the neighbouring MIAKO beams. The steel profile's
occupied volume is subtracted from the concrete, including after
`add_stiffening_rib()` calls.

Steel members are in `slab.steel_beams` and the slab's IFC decomposition.
`slab.beams`, `beam_centerlines` and the MIAKO beam schedule retain just the
prefabricated concrete beams. Layouts consisting of two beams and an HEB180
are supported even without block bays.

## MIAKO stiffening ribs

Add a transverse **ztužující žebro** to an existing MIAKO slab:

```python
ceiling2.add_stiffening_rib(at=2.625, width=0.25, block_height=0.08)
```

`at` is the centre measured in metres from the slab's `start` towards `end`,
along the MIAKO beams. `width` is the strip's extent along those beams
(default 250 mm). The rib crosses the whole slab width, including both sides
of a layout `axis`. `block_height` is the retained insert height above the
slab bottom (default 80 mm), rather than an absolute Z coordinate. It must
be at least the slab's `beam_height` and below its normal `block_height`.

The helper trims the block occurrences in this strip and extends the slab's
existing concrete cover down over them. The concrete is joined into one
body with the cover. Prefabricated beams and their ceramic shells and
reinforcement are retained; shared block types and other slabs are unaffected.
Transverse reinforcing bars are not generated by this helper.

Call it after `miako_slab()` and before rendering or writing the IFC. It
returns the same slab, so calls can be chained. Multiple ribs may touch but
cannot overlap, and every strip must fit within the beam span. Definitions
are available in `slab.stiffening_ribs` as `MiakoStiffeningRib` records
(`at`, `width`, `block_height`) and are saved in `BBIM_MiakoSlab.StiffeningRibs`.
No ribs are added to the house until these calls are made explicitly.

## Railings

Create physical railings along a world-XYZ polyline, or derive the open edge
of a stair with `stair.railing_path()`:

```python
ground.railing(
    "Zábradlí schodiště",
    path=main_stairs.railing_path(side="left"),
    height=1.0, post_spacing=0.9,
    infill="vertical", material="Wood", color="#C8B090",
)
upper.railing(
    "Zábradlí galerie",
    path=[(4, 3, 3.24), (6, 3, 3.24), (6, 4, 3.24)],
)
```

Left/right means looking **upstairs**, before export mirroring. The stair
helper follows the tread nosings and retains actual tread heights for the
bottoms of posts and balusters. Its `inset` defaults to 30 mm. Use
`path.extended([(x, y, z), ...])` to continue onto the upper landing.
Raw paths use their Z coordinates as the support surface.

Height is vertical from the path to the handrail top; it defaults to 1 m.
`post_spacing` and `baluster_spacing` are maximum horizontal centre distances.
Defaults are 60 × 60 mm posts, 60 × 40 mm handrail, and 25 × 25 mm balusters
at no more than 120 mm centres. Override these with `post_size`,
`handrail_size`, `baluster_size` and `baluster_spacing`. `infill="none"`
leaves only the handrail and posts. Corners share a post and a mitered
handrail; repeat the first point to close a path. The returned element is a
single `IfcRailing`, with geometry, material and a `BBIM_Railing` property set.

`add_house_railings()` adds the open-side guards for both indoor flights,
the entrance flight and landing, and the gallery on either side of the
chimney. The upper flight continues into the gallery guard after the chimney;
the entrance guard similarly continues around the landing. Their dimensions
and color use `RAILING_*` constants; the gallery gap also uses
`GALLERY_RAILING_CHIMNEY_CLEARANCE`. Stair and doorway access remains clear.
Ground-storey indoor railings are explicitly included in the upper plan.

## 3D-only reference boxes

`House.add_panel(name, outline=[(x, y, z), ...], thickness=..., material=..., color=...)`
extrudes one planar polygon, including a concave outline, into a non-structural
panel. Coordinates are absolute and unmirrored; point winding determines the
extrusion side. Export mirroring is applied once, as with boxes.

`House.add_box()` creates an axis-aligned box in absolute, unmirrored metre
coordinates. `origin` is its minimum X/Y/Z corner; `size` is its X/Y/Z extent:

```python
house.add_box(
    "Installation space",
    origin=(2, -3, 0),
    size=(1, 2, 2.5),
    color="#80c0ff",
    transparency=0.5,
    show_in_drawings=False,
)
```

Boxes are eligible for drawing selection by default (normal storey filters
still apply). With `show_in_drawings=False` they
remain in the exported IFC, but are removed from disposable drawing models
before rendering, so they neither appear nor obscure other geometry. This
applies to plans, sections and the legacy `generate_plan()` entry point. The
visibility property and an exclusion rule are also persisted for Bonsai.

`house_ifc.py` uses `draw_garage(x1, y1, x2, y2, height)` to add four corner
posts and one flat roof, all 3D-only. Its call controls the initial footprint
and clear height; `GARAGE_POST_SIZE` and `GARAGE_ROOF_THICKNESS` control the
placeholder member dimensions. This is visual reference geometry only.

## Roof openings

For longitudinal sections through rafters, use drawing-only batting between
their actual cut sections:

```python
section.add_rafter_section_batting(
    rafters,
    size_factor=0.7,  # Symbol thickness / actual section height.
    end_inset=0.03,  # Clearance from each rafter face, in metres.
)
```

The helper intersects finished beam geometry with the drawing plane, ignores
projected-only rafters, and merges doubled/overlapping sections before placing
symbols in the remaining gaps. No insulation solids or convex hull fills are
added. `bb` uses it for the between-rafter insulation at the ridge.

Use `Roof.add_opening()` to cut a roof-normal opening through every intersecting
roof slab or beam. The absolute XY rectangle defines the opening at the roof
plane's zero-offset surface. The two supplied points are opposite
corners and may be given in either order:

```python
upper = house.storey("Upper floor", elevation=3)
roof = upper.roof("Main roof")

opening = roof.add_opening(
    rectangle=((2.4, 1.8), (3.2, 3.0)),
    name="Bedroom roof window",  # Optional; defaults to "Roof Opening 1".
)
```

For a vertical chimney shaft, use `vertical=True`. Its XY rectangle stays
fixed through all layer heights, rather than shifting along the roof normal:

```python
chimney_opening = roof.add_opening(
    "Chimney penetration", rectangle=((x0, y0), (x1, y1)),
    vertical=True, trimmers=False,
)
```

The house's `chimney_roof_opening` follows the chimney's exact outside
footprint and cuts intersecting roof layers and plane-based members. This is
geometry only: it does not specify required fire clearance or flashing, add
headers, or change the roof-force simulator. Skylight openings retain the
existing roof-normal default. The real penetration gives Bonsai the missing
roof/chimney boundary, so its native SHAPELY fill creates the opaque chimney
face in the street elevation; no extra 2D edge or chimney-fill workaround is
needed.

The opening may be registered before or after the roof planes, layers, and
beams are created. IFC permits one opening to void only one host, so the
returned `RoofOpening.elements` contains one aligned `IfcOpeningElement` for
each intersecting roof part. To fill it with a sloped window, use the roof
plane containing the opening and its roof-tile layer:

```python
window = garden_roof.add_window(
    opening,
    top_layer=roof_tiles,  # RoofLayer returned by garden_roof.layer(...).
    frame_depth=0.10,
    frame_thickness=0.04,
)
```

The outer frame face is flush with the tile layer's top surface. Frame depth
extends inward, perpendicular to the roof; the frame's width and height are
derived from the opening along the slope. This creates an `IfcWindow/SKYLIGHT`
with frame and glazing and fills the tile-layer void without cutting the
window itself. The rectangular opening must align with the roof-plane axes
and fit entirely within that layer. `opening.window` returns the created window.

To conceal the cut edges of the roof layers, add plasterboard reveals after
creating the window:

```python
reveals = garden_roof.add_opening_lining(
    opening,
    bottom_layer=roof_plasterboard,
    thickness=0.0125,
    material="Gypsum plasterboard",
)
```

The four IFC coverings lie just inside the opening and run perpendicular to
the roof, from the back of the interior plasterboard to the underside of the
window frame. A configurable `bottom_overlap=0.001` embeds their ends 1 mm into
the plasterboard. The helper reduces only the plasterboard's opening by the
lining thickness on each side, so it covers the panel ends from below; other
roof layers retain the full opening. The reveals have
nonoverlapping butt-jointed corners, and are not cut away by their own
opening. `opening.lining` returns the panels; they can be assigned to the
plasterboard visibility storey with `storey.add(*reveals)`.
An opening may span multiple adjacent plasterboard pieces at the same offset
and thickness; in that case, supply any intersecting piece as `bottom_layer`.

The optional `"axis"` marker places the reference line at a boundary between
layers. In this example, brick extends 120 mm to the left of the axis and rock
wool extends 100 mm to the right. Without a marker, the wall construction is
centred on its axis. The direct `thickness=...` form also creates a centred
wall. `connect_wall()` creates an
`IfcRelConnectsPathElements` relationship and regenerates both wall bodies. By
default it joins their nearest ends; pass `is_atpath=True` to terminate the end
of the first wall along the path of the second wall at a T-junction.

To vary a wall's material from bottom to top without splitting its geometry,
assign vertical material layers after all wall joins have been made. Their
thicknesses are vertical heights and must add up to the wall height:

```python
wall.set_vertical_material_layers(
    [
        ("Liapor brick", 0.25),
        ("Brick", wall.height - 0.25),
    ],
    type_name="Ground load bearing wall - Liapor base course",
)
```

The original wall, its body, and its hosted door and window openings remain
unchanged; the resulting IFC material usage has layers along `AXIS3`.

To insert a reinforced-concrete band into existing walls, use
`storey.add_ring_beams_from(source_storey, height=0.25, start_height=1.125,
replace_wall_band=True, source_wall_type=load_bearing_wall)`. The height offset
is relative to the destination storey. This removes the structural band from
the masonry without introducing new hosted openings and splits both concrete
and longitudinal bars at existing openings intersecting that level. Walls
wholly above or below the band are skipped. Call after wall joins and openings;
the original wall heights and roof clipping planes are preserved. Without
`replace_wall_band`, the helper retains its existing wall-capping behaviour.
For section elevations, `hide_projected_ring_beam_seams=True` on
`house.add_drawing()` removes shared level strokes between an inserted beam
and its source wall. Cut geometry, reinforcement, fills, jambs and exterior
silhouettes remain intact. This uses the `BBIM_RingBeam` source-wall link and
`ReplacesWallBand` flag; it does not infer joins between unrelated elements.
House 2 enables it for AA and BB only. Plans and exterior views keep the
default `False`.
In `house_ifc.py`, `UPPER_RING_BEAM_HEIGHT` controls the additional concrete band,
whose top is at `UPPER_FLOOR_START + NADEZDIVKA` on the higher perimeter parts
and internal load-bearing walls, interrupted at existing openings.
`LOWER_NADEZDIVKA_X` is the outer X face of the closure masonry and ends the
high upper front/back knee walls and their ring beams between wall3 and wall4.
Its definition moved 155 mm inward from the former roof-step coordinate;
the other offsets were increased by 155 mm to retain existing positions.
They still follow this same parameter: purlin/wall-plate ends and the facade
split are at `LOWER_NADEZDIVKA_X + 0.105`, roof overlap trims at
`LOWER_NADEZDIVKA_X + 0.155`, and the transverse purlin centre at
`LOWER_NADEZDIVKA_X + 0.280`. Changing the parameter moves all these dependent
coordinates together. Facade insulation retains its architectural extent
to the roof boundary rather than stopping at the shortened masonry.
The former low knee walls and west upper gable have been removed;
there is no `LOWER_NADEZDIVKA` setting or low-level ring beam.

## Library objects and plan symbols

The roof framing drawing opts in to Bonsai's native visible surface fills with
`house.add_drawing(..., surface_fills=True)`. This uses `FillMode="SHAPELY"`
and member-ID metadata; colours and hatches from the timber schedule are
applied as CSS to those surface paths. No convex hulls, rectangular repairs,
or category-based ordering are used for this drawing. Visibility and holes
come from the actual model geometry. Other plan drawings retain their existing
linework/hull-fill behaviour. Chimney elevations now rely only on Bonsai's
native surfaces and their white CSS fill; the former hull-fill workaround
has been removed.

### Exposed section outlines

`house.add_drawing(..., section_outline_width=0.20)` adds heavier exposed
boundaries to wall, floor and ceiling assemblies (width in printed mm).
Use `None`, the default, to disable it. Ground/upper plans and AA/BB sections
enable this pass; roof drawings do not.

`section_outline_color="black"` sets the added outline's color; named colors
and `#RGB`/`#RRGGBB` values are supported, e.g. `"#555555"`. Original thin model
lines are unchanged. In `house_ifc.py`, edit `SECTION_OUTLINE_COLOR` next to
`SECTION_OUTLINE_WIDTH` to change all configured drawings. The standalone
postprocessor calls this option `color`.

In section/elevation drawings, the same pass also thickens just the cut roof
plasterboard's room-facing underside. This is an edge-only addition: the board
does not join the wall/floor/ceiling assembly union, and its upper edges, end
faces, projections and roof-window linings are not outlined. It shares the
outline width, color and outward offset, preserves cut opening gaps, and masks
parts in contact with walls or other solids. The standalone pass needs the
drawing's elevation camera to identify the underside; the `ceilings` category
controls this addition.

`section_outline_offset_ratio=0.25` shifts the new outline centreline toward
air by 25% of its printed width, so a 0.6 mm stroke moves outward by 0.15 mm.
Use `0` for the previous centred stroke or `0.5` to put the heavy stroke fully
outside the assembly. This also moves hole boundaries into rooms/openings;
the original SVG lines, fills and dimension positions stay unchanged. The
offset is applied after assembly merging, and contact masks move with it to
avoid reintroducing hidden edges. The standalone postprocessor calls this
option `offset_ratio`.

With `section_outline_projected_walls=True`, visible projected wall contours
and their insulation join the cut regions. Set it to `False` in any
drawing definition to restore cut-only outlines. This switch has no effect
unless `section_outline_width` is set. The standalone postprocessor exposes
the same switch as `projected_walls=True`.
Projected wall regions are clipped by the existing door/unfilled-opening
masks before assembly merging and offsetting. Their 25 mm endpoint insets are
restored using the SVG drawing scale, so outlines stop at the actual jambs
without thick stubs. Cut-wall geometry and the original thin lines stay intact;
cut-only drawings are unchanged.

The independent `section_outlines.add_section_outlines()` postprocessor reads
Bonsai's actual closed SVG cut polygons and uses IFC metadata to group the
assemblies. It merges adjoining materials, retains room and opening boundaries,
and suppresses edges in contact with other cut solids. MIAKO internal ceramic
cells are not treated as room openings. Foundation slabs (`BASESLAB`) keep
their original thin lines in all views and still mask contact edges of
adjoining outlined solids. Permanent-formwork (`ztracene bedneni`) basement
walls receive the same exposed outlines as other walls, floors and ceilings.
Roof layers, rafters, purlins and other
projected objects retain their original line weights. Existing SVG paths are
unchanged; a replaceable `section-outlines` group is inserted below annotation
overlays before PDF/PNG export. No convex hulls are constructed. The pass accepts
closed straight-edged paths/polygons, including wool boundaries exported as
separate line segments forming closed loops. Floor/roof classification also
respects IFC types inherited from their definitions. Open or branching wool
outlines are not closed artificially; unsupported selected geometry is skipped
with a warning rather than approximated.
When Bonsai merges adjoining wall cuts, all wall IDs on the resulting polygon
are recognised as insulation hosts, not just the first one.
SHAPELY surface classes can omit `$` and `_` from IFC identifiers. The outline pass
resolves these classes through native SVG product groups that retain the exact
identifier, independent of element order. Ambiguous aliases are not guessed.
Projected wall regions are polygonized from the exported visible linework,
merging face divisions and retaining nested holes. Open contours are not closed
artificially; fragmented contours can use touching rendered cut/closed-wall or
covering-beam boundaries to complete a region. Faces outside the visible extent
or inside those supporting solids are rejected. All closed visible projected
beam regions remain unoutlined and mask wall contact edges, whether or not they
were needed for contour completion. Original thin timber lines remain intact;
the same outward tolerance follows the configured outline offset. Full hidden wall footprints
are never substituted. Visible ring beams also qualify their source wall as an
insulation host when the masonry underneath is hidden.

Wall plates created with `storey.beam(..., kind="WALL_PLATE")` are an exception:
their visible cut/projected regions join the wall assembly outline, removing
heavy seams between the plate, masonry and facade insulation. IFC stores this
role as `IfcBeam/USERDEFINED` with `ObjectType="WALL_PLATE"`; it does not depend
on beam names or change their geometry. The five pozednice in `house_ifc.py`
use this role. `section_outline_projected_walls=False` still excludes projected
wall plates while retaining cut wall-plate outlines. Contour completion repeats
until no new faces can be found, so a plate completed against a wall can in turn
complete the ring-beam contour without depending on SVG element order.

`House.assets` provides a searchable catalog of the plan-ready objects in
Bonsai's IFC furniture library. You do not need to remember its original type
names:

```python
house.assets.search("toilet")
house.assets.search("cooker")
house.assets.list(category="sanitary")
```

Each result is an `AssetInfo` with a short `alias`, the original `type_name`,
its category, and its IFC classes. Place an object using the alias:

```python
ground.asset(
    "WC",
    asset="toilet_with_cistern",
    center=(2.85, 2.05),
    size=(0.7, 1.1),
    rotation=90,
)
ground.asset("Basin", asset="basin_medium", center=(2.1, 1.2))
ground.asset("Sink", asset="sink_86x44", center=(5.0, 1.0))
ground.asset("Cooker", asset="cooktop_58x51", center=(6.0, 1.0))
ground.asset("Shower", asset="shower_90x90", center=(0.8, 1.8))
```

The object keeps its semantic IFC class and shares its imported IFC type with
repeated instances. Its 3D body and purpose-made 2D plan symbol are both
included. `center` consistently means the centre of the object in plan even
when the source library uses a corner or wall face as its origin. Pass
`size=(width, depth)` to resize the complete footprint, including surrounding
parts such as the chairs in a dining-table asset. The original height is kept.
If an asset is given `label="..."`, that text is also centred on its visible
projection in elevation drawings.

For simple cylindrical objects, provide the centre of the circular footprint,
its radius, and its vertical dimensions:

```python
ground.cylinder(
    center=(3.0, 2.0),
    radius=0.25,
    height=1.0,
    start_height=0.1,
    material="Concrete",
    color="#cccccc",
)
```

The cylinder's 3D body is projected or cut as a circle in plan drawings.

Common search synonyms such as `wc`, `toilet`, `cooker`, `basin`, and `sink`
also work directly as the `asset` value. To select a type outside the stable
aliases, use the exact name returned by a search:

```python
ground.asset(
    "Special fixture",
    type_name="Generic Toilet without Cistern",
    center=(3.5, 2.0),
    start_height=0.1,
    label="WC",
)
```

The Bonsai library is discovered automatically. If it is installed elsewhere,
configure it once when creating the house:

```python
house = House("My house", asset_library="path/to/IFC4 Furniture Library.ifc")
```

## Automated Bonsai plans

Generate the ground-floor electrical wiring draft with
`python3 house_ifc.py elektro_ground`. It saves `elektro_ground.svg` and the PDF
at `PDF_ELEKTRO_GROUND` under `projekt/D1.4. Zařízení Silnoproudé Elektrotechniky/`.
The right panel includes circuit line colors (blue: zásuvkový okruh, red:
3-fázový okruh, pink `#f080f0`: světelný okruh), single/double socket symbols,
and symbols for a blue crossed-circle light (Světlo) and a green switch (Vypínač).
Temporary magenta corner guides use the existing room IDs and one-based floor
outline order, e.g. `0.01.1`. Every room floor in `ground.floor_layers` is
included automatically; `floor_layer(room_id="0.01", ...)` sets the ID, with
the floor name used as a fallback. No physical 3D guide geometry is added.

Generate the upper-floor electrical draft with
`python3 house_ifc.py elektro_upper`. It saves `elektro_upper.svg` and
`PDF_ELEKTRO_UPPER` in the same electrical folder, using the upper plan's
`P.01`–`P.05` room IDs (e.g. corner `P.01.1`). The ground-floor hallway's
`0.04.1`–`0.04.6` corners are also included, without adding the rest of the
ground floor to the plan. Both floors share electrical
legends. The upper block exposes `elektro_upper_corners` and its own
`draw_elektro_line` instance for adding routes before rendering.

Set `ELEKTRO_SHOW_ROOM_CORNERS = False` or run
`python3 house_ifc.py elektro_ground --no-room-corners` to hide the guides.
The same switch/flag hides guides in `elektro_upper` too.
The returned `elektro_ground_corners` dictionary always remains available, so
wire routes can reference `elektro_ground_corners["0.01.1"]` even in the final
drawing. `drawing.add_floor_corner_labels(storey, show=True)` is reusable for
other floor-plan drawings.
Use `extra_floors=[chodba]` to include selected room-floor outlines from another
storey in the same label layout and returned coordinate map.

Use the stateful `draw_elektro_line` helper before `elektro_ground.render(...)`:

```python
draw_elektro_line(["-+0.03.2", "--0.01.7"], style="solid", color="red", line_width=0.3)
draw_elektro_line(["-+0.03.2", "--0.01.7"], style="dashed", color="blue", line_width=0.3)
```

The first two signs change model X and Y by 0.1 m **before** placing each point.
For example, `-+0.03.2` first uses corner `0.03.2` minus 0.1 m in X and plus
0.1 m in Y; the second call uses minus/plus 0.2 m. Each corner has independent
state, shared across all sign combinations and repeated references within a
route. Signs follow model coordinates, even when the drawing mirrors X.
Use a literal space in either of the first two positions to keep that axis's
current accumulated value: `" +0.04.1"` changes only Y, `"- 0.04.1"` changes
only X, and `"  0.04.1"` changes neither. Keep both prefix positions, including
leading spaces, inside the string.
Failed calls leave offsets unchanged; the original corner dictionary is never
modified. The helper works even with corner guides hidden.

Append `;x,y` to a corner reference for an additional one-time shift in metres,
e.g. `"++0.04.1;0.25,-0.05"`. The normal `++` offset still accumulates, but the
extra `(0.25, -0.05)` applies only to this occurrence. It uses model X/Y axes,
not page directions. Socket positions interpolate between the final, shifted
segment endpoints.

For another plan, create its own callable with
`draw_elektro_line = ElektroLineDrawer(drawing, corners, step=0.1)`.
Creating a new instance resets offsets. Styles, colors, printed-mm `line_width`
and optional `name` work exactly as in `drawing.add_poly_line()`; it returns
the resulting drawing annotation.

Insert socket entries between the two corner IDs defining a segment:

```python
draw_elektro_line([
    "-+0.03.2",
    "socket,0.4,up",
    "d_socket,0.8,left",
    "--0.01.7",
], color="blue", line_width=0.3)
```

The fraction (0–1) measures from the preceding corner to the following corner,
after their cumulative offsets. Multiple sockets may share a segment; they do
not bend the route or advance corner offsets. Each draws a solid dark-green
(`#008000`) branch ending in an open semicircle. `up`, `down`, `left`, `right`
refer to the **page**, including mirrored exports. The wire keeps its own
style/color; sockets use its line width. The default branch is 0.225 m long and
the semicircle radius is 0.1125 m (75% of the original size). `d_socket` adds
a second, nested semicircle with 2/3 of the outer radius; both rims align and
it supports the same fractions and directions as `socket`.
Standalone/custom-sized sockets can use
`drawing.add_socket_symbol(point, "up", branch_length=0.225, radius=0.1125)`;
add `double=True` for a double socket. Explicit dimensions and line widths
are used as supplied, without additional scaling.

Three-phase outlets use `"socket3f,0.4,up"`: the same single-socket geometry,
size and placement rules as `socket`, but red regardless of the route color.
The shared legend labels them “Zásuvka 380V, 3 fáze”. Existing outlets on red
electrical routes use `socket3f`; ordinary `socket` and `d_socket` remain green.
For standalone placement, use `drawing.add_socket_symbol((x, y), "up", color="red")`.

Lights use a blue circle with a diagonal X, placed directly on the route with
`"light,0.4"` (40% between the neighboring corner points, without a branch).
Standalone placement uses `drawing.add_light_symbol((x, y))`; its default
radius is 0.15 m. Optional `radius`, `color`, `line_width` and `name` are supported.
The light stays blue even when the circuit line uses another color.

Switches use `"switch,0.4,up"`, just like sockets: a green branch extends from
the point 40% along the segment to a small circle with a tilted lever and a
short tip. Directions (`up`, `down`, `left`, `right`) refer to the page, even
with X mirroring, and rotate the whole symbol. Standalone placement uses
`drawing.add_switch_symbol((x, y), "up")`; optional `branch_length` (default
0.225 m), `radius` (default 0.075 m), `color`, `line_width` and `name` are supported.
Switch entries do not advance corner offsets and use the route's line width.

For other drawings with a right panel of at least 40 mm, symbol legends can use
`drawing.add_symbol_legend([("socket", "Zásuvka"), ("d_socket", "Dvojitá zásuvka"), ("light", "Světlo"), ("switch", "Vypínač")])`.
They reuse symbol geometry, add no objects to the plan, and stack with other
legends. Optional `title`, `color` and `line_width` control their appearance;
omitting `color` uses green ordinary sockets/switches, red `socket3f` and blue lights, while an explicit color
overrides all samples.

Linear and angular dimensions, including labels and extension/reference lines,
are placed above model fills and masks in the final SVG, PNG and PDF output.

`Drawing.add_angle(vertex, start, end, radius=0.65)` adds a native angular
dimension between two rays, with an arc, arrowheads, degree label and reference
lines. Coordinates are `(x, y)` in plans, `(y, z)` in sections looking along X,
or `(x, z)` when looking along Y, matching `add_dimension()`. Ray lengths are
ignored; `radius` controls the arc size in metres. Collinear rays are rejected.
The helper defaults the drawing's `AngleDecimalPlaces` to 2 if unset and
preserves an existing setting. AA uses it for the main and dormer roof pitches,
derived from their model planes.

```python
drawing.add_angle(
    vertex=(2.5, 5.0),
    start=(1.5, 5.0),
    end=(1.5, 4.3),
    radius=0.65,
)
```

The authoritative `roof_under_rafter_x_ranges` and `roof_over_rafter_x_ranges`
are independent lists of `(x_min, x_max, profile)` entries. Exterior profiles
are `"normal"` and `"dormer"`; interior ranges also accept `"ceiling"`, which
creates only the retained horizontal vapour barrier and plasterboard.
Inner ranges do not overlap; exterior ranges may overlap at the dormer.

The low roof has been removed: no low rafters, ties, spacers, purlins, wall
plates, sloped build-up, roof tiles, battens, fascia or gable. Its replacement
transverse roof and the restored rectangular west facade are described below.
The MDF/wood roof-step closure is also removed. The high roof still ends
at its explicit range boundary, based on `LOWER_NADEZDIVKA_X`.
MIAKO slabs, floors, internal partitions, fixtures and stairs are retained.
The horizontal lower ceilings retain their exact previous heights and Y
footprints via `LOWER_CEILING_CLEAR_HEIGHT`, `LOWER_VAPOUR_BARRIER_TOP_HEIGHT`
and `LOWER_CEILING_Y_LIMITS`, independently of any roof slope or purlin.
Street/garden wooden facades retain their X bounds; their sloped tops follow
the transverse rafter underside.

Only roof tiles use the full `roof_over_rafter_x_ranges` extents. MDF,
underlay and tile battens use `[x_min + ROOF_EAVE_SETBACK, x_max - ROOF_EAVE_SETBACK]`
for each range, leaving 20 mm at each X end for slope-following siding.
Counter-battens follow these inset build-up footprints; structural rafter/tie
positions and under-rafter ranges are unchanged. `roof_under_tile_x_range()`
centralizes the shared inset, rejects ranges consumed by it, and restores the
full width if the setback is zero. This reuses the existing 20 mm eave-siding
allowance, rather than adding another parameter. Tile ranges and overlaps
remain untouched. Source outlines use
small thickness-aware ridge/eave overshoots to keep the correct clipping side.
Main roofs retain vertical eave cuts at `ROOF_EAVE_OVERHANG = 0.75` metres
beyond the outside walls; the dormer independently uses
`DORMER_ROOF_EAVE_OVERHANG = 0.5` (`DORMER_ROOF_EAVE_Y`). Main roofs (street and garden)
also have a horizontal cut `ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.30` metres
below their own wall-plate underside. The dormer has its own horizontal cut,
`DORMER_ROOF_EAVE_DROP_BELOW_WALL_PLATE = 0.0`, at the dormer wall-plate underside.
Both cuts apply to the roof layers, battens and rafters (including the extended
dormer rafters); neither changes the roof pitch or ridge-side connection.
`ROOF_EAVE_SETBACK = 0.02` trims rafters, MDF, underlay, counter-battens and
tile battens 20 mm back from the vertical tile edge. Source limits intersect
all cut half-spaces, so batten rows stop at whichever eave cut is reached
first at their height. Set the setback to zero to restore matching vertical edges
and X ends. Ridge cuts, tile overhangs and interior finishes are unchanged.
`add_roof_siding()` fills the setbacks with vertical, non-structural fascia
boards using the plain `Wood siding solid` material.
Their top follows the roof tiles' underside. Main fascia bottoms use the
horizontal eave-cut height (wall-plate underside minus 300 mm); the dormer
bottom uses its own horizontal cut. Thickness equals
`ROOF_EAVE_SETBACK`; zero disables them.
X extents follow the inset `roof_over_rafter_x_ranges`, merging touching or overlapping
ranges on each roof plane. The current layout creates four boards: one street
and three garden (high/dormer/high). They are returned as `roof_siding`
and live in the `Roof - Eave siding` visibility container.
`add_sloped_roof_siding()` adds two main gable-end caps at both X ends
of the high main roof. Each is one
continuous panel following both pitches, in the 20 mm X-end allowance, from
the rafter underside to the tile underside, respecting both eave cuts.
It also adds a side cap at both X ends of each dormer exterior range, along
the dormer's single pitch. These stop at the roof layers' ridge-side boundary
(local Y=0), not the extended structural rafters, and at the full tile eave,
also clipped by the dormer horizontal eave plane.
The current layout has four caps in total, including the two dormer side caps.
Results are `roof_sloped_siding`
in the `Roof - Sloped siding` container. `Wood siding solid` has a plain view
fill `#f9e5bf` set in `.material-Woodsidingsolid.surface` in
`bonsai_scripts/assets/plan.css`; there are no board-joint lines or sloped pattern
yet. Section cuts remain timber-yellow, independently of that view color.
Counter-battens use the existing main/dormer rafter positions but are generated
outside the structural-rafter loop. Main positions are filtered by their explicit
high-roof assembly positions. Dormer battens keep their paired dormer
positions. Coincident intervals on the same plane are unioned as before.

`exterior_roof_sections_at(x)` returns every matching range, not a single
winner. AA roof angles, SK3 composition markers and ridge-cap symbols include
each distinct exterior profile crossing the view. Under-rafter batting and
interior-height dimensions continue to select the independent inner profile.
Structural framing now uses only `high_rafters`; `rafters` keeps the same
high-roof assembly order for shared drawing indices. Entries still accept
numbers, paired dormer tuples, `StrongerRafter` and `SplitRafter`. The last
high rafter, its collar ties and spacer stay in place. The middle purlins and
high wall plates end at the facade material transition,
`LOWER_NADEZDIVKA_X + 0.105`.
Timber schedules contain only the remaining members, grouped by measured
section and finished length. The former low-rafter ZZ cut is removed from
the roof sheet; XX and YY remain.

Roof and closure boards use the canonical `MDF` material, with
`MDF_THICKNESS`, `MDF_BOTTOM` and `MDF_LAMBDA` settings in `house_ifc.py`.
MDF has a pink (`#f2b6d0`) cut fill and outline, with white projections.
The `mdf-solid` legend pattern uses the same pink. Styles also retain support
for the `Wood fiberboard` and `mdf-solid` material names in older IFC files.
The thin dark `Roofing underlay` remains a separate membrane above the MDF.
The reusable `Wood siding` material for facades uses closed projected faces with thin
horizontal board joints (`wood-siding` pattern), and yellow wood fill in cuts.
Open projected edges stay unfilled; no grain texture or individual-board solids
are generated. Roof-edge siding (eave boards and sloped caps)
uses `Wood siding solid`: `#f9e5bf` without joints. Patterned siding uses the
lighter `#fcf2df` background set in `drawings/assets/patterns.svg`.
The two colors are independent and also applied in 3D by `wood_siding_color()`.
Joint pitch is 150 mm by
default: edit `data-board-height-mm` on `wood-siding` in
`drawings/assets/patterns.svg` to change it. Rendering adjusts the pitch to the
drawing scale while keeping the joint stroke at 0.06 mm on paper. AA/BB share
the same projected-siding legend swatch.
Flashing, attachment details and remaining wall details are not modelled.
The 3D force simulator has not yet been updated for the low-roof removal.
There is no shortened house-cut slope or raised street-side wall plate.
The street, garden and dormer wall plates are centred at `BWTy / 2` and
`HOUSE_DEPTH - BWTy / 2`. Roof-plane contact points use their actual outer top
corners, preserving the bearing heights as wall thickness changes. The transverse
plate follows the wall-4 ring-beam centre (`HOUSE_WIDTH - BWTx / 2`).

Run `python3 house_ifc.py roof` for one A3 portrait sheet containing the roof
plan above the XX and YY framing sections, with a single timber schedule.
The separate `roof_xx`, `roof_yy` and `roof_zz` command-line targets are removed;
their previous PDF numbers remain reserved to avoid renumbering later documents.
The XX framing section looks along +X (parallel to AA). Its
`add_roof_elevation()` call selects index 1 in
`rafters` and puts the camera 0.15 m before it. It uses the roof plan's
structural timber selection and upper-floor walls, without roof build-up layers,
furniture or roof-layer finishes. The complete timber schedule comes from the same
`timber_schedule_rows` definition as the roof plan. Only the selected rafter
assembly (both roof sides, paired dormer members, collar ties and spacer) and
the purlins cut by the camera, all wall plates and purlin packing blocks receive
its colours/hatches (including projected plates/blocks); other timber stays
white with outlines, and Bonsai still determines visibility. The camera is
mirrored with the IFC as usual. The YY section also includes the chimney and
its collar-board clearance dimension.

Reuse the same helper in `house_ifc.py` for additional framing sections:

```python
section = add_roof_elevation("roof_yy", rafter_index=5, offset=0.15)
# Add dimensions or notes here, if needed.
section.render("roof_yy.svg", png=True, png_dpi=600)
```

Paired entries in either framing array can optionally trim their two IFC collar boards:

```python
(rafter_x, "before", {"min_y": BWT + CHODBA_DEPTH + 0.02})
```

`min_y` is an absolute house Y coordinate in metres. Both boards keep only
the part at or beyond that boundary; the rafters and other collar pairs are
unchanged. Their shorter finished lengths are reflected in the timber schedule.
This is an IFC geometry option. The 3D force simulator accepts it with
`--no-collar-ties`; with collars enabled it stops explicitly, because the
shortened boards need a new connection model rather than an uncut axial tie.

The index is zero-based and accepts any existing `rafters` entry, including
paired dormer, stronger and split rafters. Positive offsets move the camera
before the assembly, zero cuts through it, and negative offsets move it past
the assembly. `radius=6` controls the view size. The helper returns a `Drawing`
without rendering; each drawing keeps independent styles and uses the same
full schedule definition.

These framing sections also dimension the sloping rafter spans between the
outer top corners of the wall plates and purlins, and from the street purlin's
outer top corner to the ridge. The ridge endpoint remains on the rafter axis.
`add_roof_rafter_dimensions()` uses the selected assembly's actual beams,
including the dormer wall plate and local purlin sections. The street plate
now spans the whole house; the former raised house-cut plate is removed.
Unequal lower spans are shown on both sides (YY); symmetric ones are shown
once (XX/ZZ). Dimension lines are offset 0.45 m outward and exclude eave
overhangs and fabrication allowances.
Each framing section also calls `add_roof_purlin_dimension()` to show horizontal
purlin centre-to-centre spacing below the beams. It uses the local purlin pieces
(side pieces in XX/ZZ, middle pieces in YY), with a default offset of -0.5 m
from their centreline level. Existing rafter dimensions are unchanged.
Linear dimension labels stay centred along their dimension lines in plans and
elevations, even for very short spans. This overrides Bonsai's automatic
endpoint placement. Text is kept upright regardless of endpoint order or X-axis
mirroring. When a label needs a half-turn, its perpendicular offset is reversed
too, keeping opening widths above the line and heights below it (widths to the
left and heights to the right for vertical dimensions). Opening-height labels
are centred as well.

To mark an elevation relative to a reference datum, use:

```python
drawing.add_elevation_dimension(x0=2, x1=4, z0=0, z1=1.5)
```

This draws a horizontal line from `(2, 1.5)` to `(4, 1.5)`, with an open
downward arrow at its midpoint and `+1500` above/right of the arrow. `z0`
only supplies the reference height; no line is drawn there. Labels use signed
whole millimetres without thousands separators (`±0` at zero); input coordinates
remain metres. The arrow stem is 2.5 mm tall with a 0.75 mm arrowhead. The horizontal
coordinate is world X when looking along Y, or world Y when looking along X,
just like `add_line()`. Axis-aligned elevation views are required. Optional
`font_size=2` (matching other dimension labels), `line_width=0.1` and
`color="black"` control appearance; sizes
are printed millimetres, independent of scale. Mirroring keeps the arrow
upright, the label readable and the shelf pointing right. The symbol and its
text are native IFC annotations kept above model fills like other dimensions.

`roof_elevation_definitions` holds the rafter indices, offsets and marker
letters for `roof_xx` and `roof_yy`. The roof plan displays their
X–X and Y–Y cut lines, derived by `roof_elevation_cut()` from those same
settings, even when only the plan is being generated. Section cameras use
that cut-definition helper too, keeping locations and viewing arrows aligned
through export mirroring. Tune the settings in that shared dictionary.
Bonsai's automatic camera-position markers are disabled (`GlobalReferencing=False`);
only explicitly added cut symbols appear in other views.

`drawing.add_timber_schedule(rows, styled_members=members)` limits diagram
styles without filtering the schedule's counts, lengths, volumes or pattern
examples. Omit `styled_members` to style all scheduled members, or pass an
empty list for white timber throughout. Styling native elevation cuts and
surfaces does not construct hulls or reorder elements.

After writing the IFC model, `House.generate_plan()` can launch Blender and
Bonsai, create a downward-looking orthographic camera, and save a styled SVG:

```python
house.write("house.ifc")
house.generate_plan(
    "house.svg",
    x=0,
    y=0,
    z=1.6,
    radius=5,
    png=True,
)
```

Door openings use thin solid wall-continuation lines (0.1 mm); pass
`show_overhead=False` to omit them. Unfilled `wall.add_opening()` openings
have no continuation lines by default; `show_overhead=True` explicitly opts
back in. Facade-insulation opening boundaries are independent of this switch.
Unfilled openings retain an invisible mask source so projected wall/lintel
edges are covered even when no continuation line is drawn. The cover is only
used when the plan cut intersects the opening.

Use `wall.add_door(..., glazed=True)` for a balcony-style glazed door. It
remains an `IfcDoor` with the same construction opening, handles, casing,
plan swing and dimensions. The leaf becomes a frame around a centred glass
pane; frame width is 80 mm (scaled for small leaves), glass is 10 mm thick.
The default frame/glass color follows the house's window color, or can be
overridden with `color`. `transparency` controls the frame and
`glass_transparency=0.75` independently controls the glass. Single, double
and sliding doors are supported; opening/closing and X mirroring also move
the glass. Without `glazed=True`, solid doors are unchanged.

Use `wall.add_garage_door(opening, section_height=0.5, color="#ffffff")`
to fill an existing unfilled wall opening with a sectional garage door.
It retains the original opening and its dimensions, lintel tags and facade
voids. The closed 3D door has a frame and horizontal panel joints (equal
sections no taller than `section_height`); a continuous backing closes the
joints. Plans show a thin closed panel and frame without a swing arc.
`panel_thickness=0.04` and `frame_width=0.06` control the simplified geometry.
It is an `IfcDoor` with a user-defined `SECTIONAL_OVERHEAD` operation;
tracks and opening motion are not modelled.

Plan drawings automatically label every included door with its width and
height in millimetres, separated by a line. The label sits inside the door
swing. Use `clear_height` when the usable passage is lower than the door's
construction height; it changes the annotation without changing the opening
or door geometry:

```python
kitchen_door = wall.add_door(
    at=1.0,
    width=0.9,
    height=2.375,
    clear_height=2.1,
)
```

For an external plan dimension of a door, window, or unfilled wall opening:

```python
drawing.add_opening_dimension(
    kitchen_door,
    offset=-1,
    finished_floor_height=GROUND_FLOOR_THICKNESS,
)
```

The construction width is above the line; `height (sill_height)` is below it,
all in millimetres. Height is opening top minus bottom, not its top elevation
or the door's usable passage height. Sill height is relative to finished floor.
For a negative sill, the lower label instead shows height above floor + depth
below floor, e.g. `2100 + 100`.
`finished_floor_height` is in metres above the host storey base, not absolute Z.
Omit it to use the common top level of that storey's FLOOR layers; absent or
different floor levels require an explicit value. Offset follows the normal
dimension convention, relative to the wall's start-to-end direction. Native
dimension markers, readable mirrored text, and topmost dimension layering are
preserved. This does not replace automatic labels inside door swings.

Use `opening_width` and `opening_height` for the larger construction opening.
The door casing automatically bridges that clearance on both wall faces and,
by default, continues 25 mm over the surrounding wall with a 5 mm projection.
Both dimensions are configurable in metres:

```python
wall.add_door(
    at=1.0,
    width=0.9,
    height=2.1,
    opening_width=1.0,
    opening_height=2.15,
    casing_overlap=0.03,
    casing_depth=0.008,
)
```

Set `casing_depth=0` when a door should have no casing.

To span storeys, supply the additional aligned walls with `through_walls`:

```python
basement_door = basement_street_wall.add_door(
    at=wall3_start - 1.0, width=0.9, opening_width=1.0,
    sill_height=1.25, height=3.25, clear_height=2.0,
    through_walls=[wall_front_g],
    through_elements=[chodba],  # optional floor/ceiling layers to cut
)
```

Heights remain relative to the host storey's elevation: this example runs
from Z = -1.25 to +0.75 m. One full-height door and its opening belong to the
basement; extra wall openings are clipped to the corresponding walls. Wall
directions can be reversed and thicknesses can differ. All wall cuts are
validated before creating the door, including alignment, length and clashes
with existing openings. `through_elements` cuts the listed floor/ceiling
layers over the rough-opening width and host-wall depth. Facades copy the
wall openings, and drawings scoped to either storey include the same door
automatically. Its plan symbol is raised above intersected-storey floor
finishes. Ordinary single-wall doors retain their height-fit validation.

A common offset can move all labels farther into the room:

```python
drawing = house.add_drawing(
    "Ground plan",
    x=6,
    y=4,
    z=1.6,
    radius=8,
    storeys=[ground],
    door_annotation_offset=0.05,
)
```

Add a section reference to a plan (coordinates are in model metres):

```python
drawing.add_cut_symbol(
    start=(1, 2), end=(8, 2), identifier="A", direction=-1,
)
# Equivalent positional ID:
# drawing.add_cut_symbol((1, 2), (8, 2), "A", direction=-1)
```

This draws a dash-dot line with a perpendicular open arrow and the same letter
at each endpoint, above the plan geometry. Looking from `start` towards `end`,
`direction=1` looks to the left and `direction=-1` (the default) to the right.
The letters stay upright. It labels an existing cut; it does not create a new
section drawing/camera automatically.

For one shared definition of the plan markers and the actual section view:

```python
aa_cut = CutDefinition(start=(4.31, -1), end=(4.31, 9), identifier="A", direction=-1)
aa_cut.add_symbol(ground_drawing)
aa_cut.add_symbol(upper_drawing)
aa_drawing = aa_cut.add_drawing(house, "aa", z=3.5, radius=8, doors_closed=True)
```

The section camera uses the cut midpoint and the same viewing direction as
the arrows. In `house_ifc.py`, `aa_cut` is defined alongside the house geometry
constants; editing it updates both plans and the AA view.
`bb_cut` defines a longitudinal section through the ridge at `HOUSE_DEPTH / 2`,
perpendicular to AA and looking towards the garden (+Y). Both cuts are marked
on the ground, upper and roof plans. Generate the section with
`python3 house_ifc.py bb` (outputs `bb.svg` and `bb.png`).

For manual control, disable the automatic labels and add selected doors with
individual offsets:

```python
drawing = house.add_drawing(
    "Ground plan", 6, 4, 1.6, 8,
    storeys=[ground],
    door_annotations=False,
)
drawing.add_door_annotation(kitchen_door, offset=0.05)
```

Room labels are deliberately manual: provide the separator centre, room
identifier, and area in square metres. The helper formats the area with two
decimal places and does not attempt to infer room boundaries:

```python
drawing.add_room_annotation(
    (4.5, 3.2),
    identifier="P.01",
    area=8.30,
)
```

Mark the building entrance with a drawing-scoped direction arrow. Rotation is
counter-clockwise in degrees: zero points right and 180 points left.

```python
drawing.add_entrance_arrow(
    (9.0, -0.5),
    rotation=180,
)
```

Add drawing-only façade insulation outside an individual wall with
`add_wall_insulation()`. It does not alter the wall or its 3D construction.
The default `side="right"` means the right side when looking from the wall's
start towards its end. Doors and windows intersecting the plan cut are left
clear. Positive extensions can close corner gaps, while negative extensions
trim the insulation before a wall end. A zero extension is automatically
resolved to 17.5 mm so perpendicular insulation strips meet:

```python
drawing.add_wall_insulation(
    wall_front,
    thickness=0.16,
    material="polystyrene",  # or "xps" / "rockwool"
    start_extension=0.16,
    end_extension=0,
)
```

For horizontal walls, the insulation endpoints may instead be specified as
absolute model X coordinates. Vertical walls accept the corresponding Y
coordinates:

```python
drawing.add_wall_insulation(
    horizontal_wall,
    thickness=0.16,
    material="polystyrene",
    start_x=1.38,
    end_x=2.30,
)
drawing.add_wall_insulation(
    vertical_wall,
    thickness=0.20,
    material="rockwool",
    start_y=3.50,
    end_y=1.75,
)
```

The two coordinates may be given in either order; they are automatically
matched to the wall's start-to-end direction, including for walls drawn
right-to-left or top-to-bottom. A coordinate and its corresponding extension
cannot be supplied together.

Polystyrene uses the existing white hexagonal hatch. XPS uses the same hatch
with the light-pink perimeter-insulation tint. Rockwool uses the conventional
batting wave and follows the wall direction. Rockwool also receives an
opening-aware boundary box matching the polystyrene outline; its batting is
inset slightly inside that box on all four sides and uses a lighter stroke. A
single thin solid outer boundary continues across each door or window opening
for all insulation materials (0.1 mm, without a heavy section outline);
the wall-side boundary remains absent to avoid duplicating opening linework.
The insulation begins directly at the finished wall face and is drawn at its
full requested thickness. It is placed behind the wall linework so the shared
boundary remains visible without introducing a geometric gap.
In elevation sections, `opening_walls=[upper_wall]` includes openings from
aligned walls on other storeys in the same `start_z`–`end_z` strip, avoiding
separate boundary lines at floor levels.

The camera is centred at `(x, y, z)`. Its square view covers `2 * radius`
metres in both X and Y, so the example cuts the model at 1.6 m and covers a
10 m by 10 m area. `png=True` additionally creates `house.png` through
Inkscape.

Pass a PDF output path (or `None` to skip PDF export) to render a vector PDF
of the finished drawing, including all legends, notes and post-processing:

```python
from pathlib import Path

drawing.render("house.svg", png=True, pdf=Path("house.pdf"))
drawing.render("house.svg", pdf=Path("house-a3.pdf"), paper="A3")
drawing.render("house.svg", pdf=Path("house.pdf"), title="Půdorys přízemí")
```

PDFs default to **A4 landscape** with **10 mm margins**. `paper` supports
`"A4"`, `"A3"`, `"A2"`, `"A1"` and `"A0"`; `orientation` is `"landscape"`
or `"portrait"`, and `margin` is in millimetres. The complete SVG is centred
on the sheet without resizing it, preserving its drawing scale and vector
linework. Oversized drawings raise an error rather than silently shrinking.
Existing PDFs are replaced only after a successful export. `title` adds a
centred, bold 4 mm heading to SVG, PNG and PDF in a compact 10 mm header. If
omitted, it uses the PDF filename without its directory or extension (or the
SVG filename when no PDF is requested). The drawing scale is appended to both
automatic and custom titles, e.g. `D1.1.5. Krov 1:100`. The drawing is moved down, not scaled;
the header is included in the paper-fit check. Print the PDF at actual size /
100%, not "fit to page".

### Finding dimensions in the source

Every drawing render writes a UTF-8, tab-separated index beside the SVG,
for example `projekt2/basement.dimensions.tsv`. Search by the exact value
shown in the drawing:

```bash
rg '^3955\t' projekt2/basement.dimensions.tsv
```

Rows include the displayed value, drawing and dimension names, a
`/path/to/house2.py:line` source location, original endpoints and offset,
unrounded length in millimetres, and the caller chain for project helpers.
Repeated values stay as separate rows, including iterations of the same loop.
Opening captions below the width are indexed separately with `label=description`.
Labels come from the final SVG, preserving Bonsai's rounding and formatting.
The index covers linear dimensions, opening dimensions and helpers built on
`add_dimension()`. Source information is captured when the dimension is
created and persists in the IFC's `BBIM_DimensionSource` property set; rebuild
older IFCs from Python to populate missing source locations. Source lines
refer to generation time; regenerate a drawing after editing its script.
A sheet's index
combines its subdrawings and retains their drawing names. Indices are replaced
on each render, including when the drawing no longer contains dimensions.

### Multiple drawings on one sheet

Set `house.add_drawing(..., scale=200)` to render a drawing at 1:200;
the default denominator is 100. Sheet composition preserves that scale and
the physical text sizes and line widths.

```python
sheet = DrawingSheet(paper="A3", orientation="portrait")
sheet.add(roof, x=0.5, y=0.25, title="D1.1.5. Krov", crop=False)
sheet.add(roof_xx, x=0.25, y=0.64, title="Řez XX", tables=False)
sheet.add(roof_yy, x=0.74, y=0.75, title="Řez YY", tables=False)
sheet.add(roof_zz, x=0.25, y=0.87, title="Řez ZZ", tables=False)
sheet.render("roof.svg", pdf=PDF_KROV)
```

Each `x`, `y` is the drawing's centre as a fraction of the **whole page**:
`0` is left/top and `1` right/bottom. Placement is manual; overlaps are allowed.
There is no automatic layout, resizing or fitting. Drawings crossing the sheet
margins produce an error. Constructor defaults are A4 landscape, 10 mm margins
and 2 mm cropping padding; the roof sheet explicitly uses A3 portrait.

`crop=True` (the default) trims empty camera space around the actual SVG
geometry, text and markers, moving the title next to the cropped diagram.
The original viewport clipping is retained so cropping cannot reveal geometry
outside the camera frame.
`crop=False` preserves the entire original viewport: an A4-sized main drawing
centred at `(0.5, 0.25)` retains its previous position in the top half of A3.
Neither option changes scale, line widths or text sizes. `title` defaults to
the drawing name; its actual scale is appended as for standalone drawings.

`tables=False` hides the right-side panel but retains all timber colors and
hatches. Schedules and document links on the original drawing objects remain
unchanged. This option is also available on `drawing.render(...)` for standalone
exports. Sheet SVGs remain vector drawings, with separately scoped styles,
marker/pattern IDs and references for each view. `house.write(...)` must precede
rendering, just as with standalone drawings. Old separate-cut PDF files are not
automatically deleted.

### Drainage schematic

Run `python3 house_ifc.py kanal_ground` for the ground-floor drainage plan.
It initially includes only the ground-floor model, without the architectural
plan's manually added dimensions, legends or notes. The outputs are
`kanal_ground.svg` and the path specified by `PDF_KANAL_GROUND`, currently
`projekt/D1.5. Zdravotechnické instalace/D1.5.2. Kanalizace - Půdorys 1.NP.pdf`.

Run `python3 house_ifc.py kanal` to create the annotation-only drawing
`kanal.svg` and `projekt/D1.5. Zdravotechnické instalace/D1.5.1. Kanalizace.pdf`.
It uses `storeys=[]`, so no house plans or other model geometry are shown.
Its seven horizontal reference lines use the finished ground-floor surface
as height zero: ground-floor surface and basement foundation-slab top; MIAKO bottom,
MIAKO top and upper-floor surface; plasterboard bottom and roof-tile top.
The last two are measured at `DRAINAGE_STACK_X, DRAINAGE_STACK_Y` using
`roof.layer_vertical_extent(material, x=..., y=...)`, which intersects the
actual clipped roof/ceiling solids, including any openings. Horizontal
positions are schematic; vertical coordinates retain the model's heights.

Draw simple washbasin (`umyvadlo`) and kitchen sink (`dřez`) symbols with:

```python
drawing.add_basin(x=2, z=0.65)
drawing.add_sink(x=4, z=0.65, width=0.8, height=0.25)
drawing.add_toilet(x=6, z=0.2)
```

`x` is the bowl's horizontal centre, and `z` its bottom. The washbasin has a
rounded bowl; the sink is rectangular. Both have a horizontal rim and a
short central outlet below the bowl. Dimensions use metres: default width
0.60, bowl height 0.20 and `outlet_length=0.10` (set to 0 to omit the outlet).
The rounded bowl is a half-ellipse; `height=width/2` makes it a semicircle.
These are unfilled, thin black native linework icons, scoped to the drawing,
not physical IFC fixtures. All sanitary helpers add a centred identifier
above the symbol: `Umyvadlo`, `Dřez`, `WC`, `Sprcha`, `Pračka` or `Odvětrání`,
according to type.
Override it with `identifier="U1"`, for example:

```python
drawing.add_basin(x=2, z=0.65, identifier="U1")
```

Identifiers use the symbol color, selectable 2.5 mm text and a text centre
3 printed mm above the icon's top (including the toilet rim), independent
of drawing scale. `name` remains the internal IFC annotation name, not the
visible identifier. Actual drainage pipes are added with `add_line()`.
In the plan-based `kanal` schematic, `z` maps to the vertical page coordinate
(model Y); the helpers also support axis-aligned elevations.

`add_toilet()` uses the same coordinates and a rounded bowl with a thin,
closed rim (two horizontal lines). Default bowl dimensions are 0.40 m wide
and 0.20 m high, with `rim_thickness=0.025` above the bowl. There is no outlet
stub by default (`outlet_length=0`); draw the waste pipe separately. Width,
height, rim thickness, outlet length, color and name are configurable.

For a shower tray, use `drawing.add_shower(x=7, z=0.2)`. It draws only a
0.90 m wide, 0.30 m high rectangle. **Its coordinates specify the bottom-left
corner, not the centre.** Optional `width`, `height`, `color` and `name`
parameters work as for the other icons. There is no rim or outlet stub.

Use `drawing.add_washing_machine_connection(x=4, z=0.6)` for a washing-machine
wall waste connector, **not the machine itself**. It is a 0.16 m wide,
0.24 m high upright rectangle with a small circular socket inside. X is the
horizontal centre and Z the bottom; the socket centre is at
`(x, z + 2*height/3)`. `width`, `height`, `color`, `identifier` (default
`"Pračka"`) and `name` are configurable. Connect pipes separately with
`add_line()`; the helper creates no physical plumbing.

`drawing.add_roof_vent(x=0, z=6.5)` draws an upward-pointing outlined triangle
labelled `"Odvětrání"`. X is its horizontal centre and Z its bottom edge,
where the separately drawn vent pipe connects. Default width is 0.40 m and
height 0.20 m; `width`, `height`, `color`, `identifier` and `name` can be
overridden. It adds no physical roof-vent geometry.

### PDFs from Markdown

Use the independent Markdown helper, also re-exported by `ifc_utils`:

```python
from pathlib import Path
from pdf_utils import markdown_to_pdf

markdown_to_pdf(source=Path("skladby.md"), output=Path("skladby.pdf"))
markdown_to_pdf("checklist.md", "checklist.pdf", paper="A3", orientation="landscape")
```

The default is **A4 portrait**, with **20 mm margins**, page numbers, readable
DejaVu fonts and selectable Czech text. Headings, lists, tables (with repeated
headers), fenced code and local images are supported. Image paths resolve
relative to the Markdown file. Raw HTML is escaped and remote resources are
not downloaded. Existing PDFs are replaced only after a successful export.
`margin` is configurable in millimetres; paper sizes A4 through A0 are available.

The helper uses `markdown-it-py` and WeasyPrint, listed in `requirements.txt`.
WeasyPrint also needs system Pango libraries; see its
[installation instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
These system libraries are already available on this machine. Dependencies
for this helper have been installed in the isolated `.venv-pdf` environment:

```bash
.venv-pdf/bin/python pdf_utils.py skladby.md skladby.pdf
```

For a fresh environment:

```bash
python3 -m venv --system-site-packages .venv-pdf
.venv-pdf/bin/python -m pip install -r requirements.txt
```

Generate the west exterior elevation from the lower-roof end with
`python3 house_ifc.py pohled_zapad`. It looks from +X towards -X, includes both
storeys and all roof layers (without foundations or plan annotations), and
saves `pohled_zapad.svg` and the PDF configured by `PDF_POHLED_ZAPAD`.
For the opposite, east elevation from the high-roof end, use
`python3 house_ifc.py pohled_vychod`. It looks from -X towards +X with the
same storeys and annotation settings, saving `pohled_vychod.svg` and
`PDF_POHLED_VYCHOD` ("Pohled - Východ").
For the street elevation, use `python3 house_ifc.py pohled_ulice`.
The camera looks from negative Y towards positive Y, with both storeys and all
roof layers (including eave siding), without foundations or plan annotations.
It saves `pohled_ulice.svg` and `PDF_POHLED_ULICE` ("Pohled - Ulice").
For the opposite, garden-side elevation, use `python3 house_ifc.py pohled_zahrada`.
It looks from positive Y towards negative Y with the same storey and annotation
settings, saving `pohled_zahrada.svg` and `PDF_POHLED_ZAHRADA` ("Pohled - Zahrada").
The garden elevation excludes only the concealed upper ring beam hosted on
`wall_back1_u` and its reinforcing bars. This avoids an OpenCascade projected
edge leaking between the dormer-window sills; it is a per-drawing visibility
workaround, not a general hidden-line repair or a geometry change. The beam
remains in the IFC, sections and other drawings. Use
`drawing.exclude_element(element)` for explicit per-drawing exclusions;
existing 3D-only exclusions are preserved, and parts are excluded separately.

`add_facade()` creates the street finish; `add_facade("garden")` creates the
garden finish. Both use two full-height IFC coverings, white on the high
part and `Wood siding` on the low part, meeting at `FACADE_MATERIAL_SPLIT_X`.
All exterior wall finishes are contained in the artificial `Facades` storey
(`facade_storey`) so they can be toggled together in a 3D viewer. This includes
the basement finishes, dormer sides and west closure finish. Their geometry
and openings remain anchored to the original walls. Drawings continue to
include each finish with its host wall's physical storey; explicit per-element
exclusions still apply. Roof-edge siding keeps its separate roof-layer storeys.
Each wooden covering is one four-point profile whose top follows
`transverse_roof` at `RAFTER_Z_OFFSET`, from its higher inner end to its
lower west end. Its height updates with the transverse support positions.
The garden's white covering is one stepped polygon raised at the dormer,
not separate touching panels, so there is no horizontal joint to mask.
`add_dormer_side_facades()` adds the white east/west dormer cheeks, returned
as `dormer_side_facades`. Both use `FACADE_THICKNESS` outside the side-wall
insulation, from the main roof's tile top to the dormer-rafter underside.
Their ridge-side ends follow the intersection of those two planes. The
garden facade's raised part overlaps these corner finishes by 1 mm.
Thickness is `FACADE_THICKNESS`, immediately outside the respective street
polystyrene/garden rockwool insulation. Tops meet the respective rafter
undersides. Ground and dormer openings are cut automatically, including the
door crossing the material change. Results are `street_facade` and `garden_facade`.
All facade insulation uses one `FACADE_INSULATION_THICKNESS = 0.20` setting,
for both EPS and mineral wool. Insulation materials remain unchanged.
The outer X limits are `-FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001`
and `HOUSE_WIDTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001`,
staggering the perpendicular corner joints by 1 mm. Panels span the
storey/construction joints rather than introducing horizontal finish seams.
`add_facade("east")` creates one white gabled covering, returned as
`east_facade`. It extends from
`-FACADE_INSULATION_THICKNESS - FACADE_THICKNESS + 0.001` to
`HOUSE_DEPTH + FACADE_INSULATION_THICKNESS + FACADE_THICKNESS - 0.001` along Y,
directly outside the end-wall insulation, up to both high-rafter undersides.
Door/window openings from both storeys are cut automatically.
`east_upper_windows` contains the two centred `wall_1_u` windows, configured
by `EAST_UPPER_WINDOW_*` beside that wall. Each is 1 m wide, with a 1 m clear
gap. Their sill and head are 1.0 m and 2.375 m above `UPPER_FLOOR_START`
(excluding floor finishes), giving a 1.375 m opening height. The upper ring
beam and east facade inherit the openings; P.02's window area totals 2.75 m².
`add_facade("west")` returns one white rectangular covering (`west_facade`)
outside wall 4's insulation, using the same Y limits as the east facade.
It starts at ground-storey Z=0 and ends at the transverse wall-plate underside,
covering the ring beam while preserving the ground-floor window opening.

`House.add_facade_layer(..., outline=[(along, height), ...])` supports such
continuous profiles in general. Outline coordinates are relative to the
covering's start and bottom and must fit inside its length/height bounds;
omitting `outline` preserves the existing rectangular behavior. IFC voids,
host-wall clipping and X mirroring apply to either shape.

Projected roof tiles use the `roof-tiles` SVG pattern: vivid terracotta red
background (`#e46b55`), thin darker red (`#b33425`) side joints and curved course edges.
The roof trim and ridge-tile symbols use the same colours in `plan.css`;
`ROOF_TILE_COLOR` sets the tiles and trim in the house2 3D model. Projected facade siding
uses the `wood-siding` pattern with a warm timber-brown background. Change the
background `<rect fill="...">` in either pattern in `drawings/assets/patterns.svg`
to tune its view color; the render passes preserve it while scaling/projecting
the pattern. Exposed tile edges use that same color as a solid fill, without
the top-face tile pattern. The source path's `stroke` sets the pattern outline
colour, including PDF exports. Section-cut colours are controlled in `plan.css`. Tile width is
`ROOF_TILE_PATTERN_WIDTH` (initially 300 mm); course length follows
`TILE_BATTEN_SPACING` (320 mm along the slope). `RoofLayer.set_tile_pattern()`
persists these dimensions in `BBIM_RoofTilePattern`, without changing the 3D
slab. The render pass in `roof_tile_patterns.py` maps the pattern through each
exported roof layer's frame into the drawing, so main, dormer and lower roofs
have independently foreshortened courses. Pattern anchoring is shared by
adjoining pieces on the same plane and works with X mirroring and any drawing
scale. The glyph and 0.06 mm printed stroke are defined in
`drawings/assets/patterns.svg`. Fixed-width stroke outlines are baked before
the pattern transform, so SVG, raster and PDF backends keep the same line
weight even for the shallow dormer (rather than relying on vector-effect).
Hatching uses Bonsai's existing visible `GlobalId` surface paths and a clip
from the actual top-face triangles, not convex hulls or replacement fills.
Bonsai can merge touching regions of the same material even across different
roof slopes and give the combined region only one product identifier. The
pass resolves the nearest roof faces in projected depth, so a merged main/
dormer region still gets separate patterns; tile edge faces also mask hatches.
Openings and depth order stay intact. Undersides, edge-on roofs, thin tile
edges and native projection linework are not hatched; section cuts remain red.
This projected pattern is added by the Python render pass (including PDF/PNG
export), not by creating individual 3D tiles or changing their 3D appearance.

A basic side elevation uses the same persisted drawing interface.  Place the
camera outside the building and point ``direction`` toward it:

```python
elevation = house.add_drawing(
    "South elevation",
    x=6,
    y=-1,
    z=3.5,
    radius=8,
    view="elevation",
    direction=(0, 1, 0),
    storeys=[ground, upper],
)
house.write("south.ifc")
elevation.render("south.svg", png=True, png_dpi=600)
```

Elevation directions must currently be horizontal. Elevations project the
existing 3D model bodies and deliberately omit plan-only annotations such as
door dimensions, room labels, and stair tread symbols. Furniture labels remain
automatic in plan drawings but are opt-in for elevations:

```python
stove = ground.furniture("Kamna", ...)
elevation.add_furniture_label(stove)
```

Axis-aligned exterior elevations can have a drawing-only terrain overlay:

```python
elevation.add_terrain(
    profile=[(-2, 417.0), (5, 417.0), (HOUSE_WIDTH + 2, 416.8)],
    earth_to_z=earth_to_z,
    hatch="earth", hatch_depth=0.4, line_width=0.35,
)
```

Profile positions are global X for views looking along Y, or global Y for
views looking along X. Heights use model Z unless `earth_to_z` is supplied;
that callable converts above-sea-level heights once when adding the profile.
Points must be ordered horizontally; consecutive points with the same
horizontal position and different heights create a vertical terrain step.
Hatch depth is in model metres and line
width in printed millimetres. Terrain masks building geometry below the
profile while dimensions and annotations remain visible.
For distant terrain, `background=True, opacity=0.2` draws a pale
profile and hatch behind the model without masking it. In `house2.py`,
`STREET_BACKGROUND_TERRAIN_BELOW_STAIRS` sets the distance below the lowest
entrance step for both faint wall bases and their background earth profiles.
The normal terrain profile remains the foreground mask. Terrain adds no 3D earth
solid and affects only the drawing receiving the call. Include the basement
storey to show exposed walls when lowering the profile. In `house_ifc.py`, edit
`TERRAIN_PROFILES` to tune each of the four exterior views independently.

Each selected label faces the elevation camera, is centred on the projected
object, and is omitted when that object has no visible SVG geometry.

A stylised ridge-tile section can be attached to an elevation without adding
3D roof geometry. The supplied world point is the underside crown of the cap;
the intersection of the two roof outer faces is therefore a useful anchor:

```python
drawing.add_ridge_tile(
    ridge,
    width=0.40,
    rise=0.12,
    thickness=0.025,
)
```

The curved, terracotta-filled annotation is scoped to that drawing and stays
attached to the model when its camera or scale changes.

## Survey points

`python3 house_ifc.py points` reads `points.txt` and creates a top-down point
drawing: `points.svg`, `points.png`, and `projekt/Zaměření pozemku.pdf`.
The standalone command `python3 survey_points.py` creates the same outputs
without building the house model or running Bonsai.

Input rows use **point ID, Y, X, Z, optional note**, in S-JTSK/Bpv metres.
The original geodet header is optional. Blank lines separate groups; start a
group with a color such as `#ff0000` to join its points in file order:

```text
#ff0000
10 588808.00 1144310.00 418.00 B
1 588802.23 1144303.39 415.73 other

2 588802.24 1144303.40 415.74 B
```

Here points 10 and 1 are connected in red, while point 2 is unconnected.
Each blank line resets the color. Colors may be hex values or names such as
`#red`. Groups with no color (or only one point) have no connecting line.
Add `, closed` to a color header (e.g. `#ff0000, closed`) to connect the last
point back to the first. Without it the polyline stays open. Blank lines also
reset this option.
Name a polyline by appending `: name`, e.g. `#0000ff: street` or
`#ff0000, closed: boundary`. Names are case-sensitive and must be unique.
`named_survey_groups(read_survey_groups(path))` returns a map from names to
their groups. Blank lines reset the name as well as the style.
Notes are preserved for reference and do not affect connections or ordering.
Repeat a point's complete row in another group to use it in multiple polylines.
Every occurrence stays in its group's path, while its cross, height label and
SVG point record are drawn only once. Repeated IDs must have the same Y/X/Z
coordinates; conflicting rows report both line numbers. Unique points keep
their first-occurrence order and the first row's note for their label/tooltip.
The drawing preserves each measured position, using small crosses and height
labels directly below the crosses, in light blue and without leader lines.
Hovering over a cross in the SVG reveals its ID, original coordinates and note,
and hovering over a polyline shows its color and ordered point IDs. Add `--point-ids` to either
command to print IDs too. All points are retained, including points describing
structures; no terrain surface or property boundary is inferred from them.

When a `street` polyline exists, its unique points define a best-fit straight
line by orthogonal least squares (minimum sum of squared perpendicular
distances). The drawing rotates to put that line on the x axis, with the
origin at the street points' centroid. The view is reversed by 180° to place
the street below the land, matching the house plans. Positive x points toward
grid west (grid south for a vertical line), regardless of vertex order. All groups,
crosses and the grid-north arrow rotate together; heights and plan distances
stay unchanged. A street needs at least two distinct plan positions and a
unique fitted direction. The rotation and RMS distance from the line are
printed in the terminal.

Without `street`, the plot uses local grid-east/grid-north axes,
`east = Y0-Y`, `north = X0-X`, as before. The origin and scale bar are printed.
`SurveyFrame` stores the origin and x-axis angle (`rotation_radians`), and
provides an inverse mapping for later placement work. Grid north follows
S-JTSK, not geographic north.
Original coordinates and notes are also embedded in the SVG's `survey-data`
metadata. House coordinates and X mirroring do not affect this drawing.

PDF defaults to A4 landscape and chooses a scale that fits (currently 1:500).
For a larger copy, run
`python3 survey_points.py --paper A3 --scale 250`.

The two drawing commands also place an **11.6 × 8.4 m rectangular house**.
Edit `HOUSE_PLACEMENT` in `survey_points.py` to move or rotate it:

```python
HOUSE_PLACEMENT = SurveyHouse(center=(-8.0, 7.0), angle_degrees=0.0)
```

Placement origin `(0, 0)` is the intersection of the best-fit `street` and
`neighbour` lines. Positive x runs right along the street; positive y follows
the neighbour line upward. Both are measured in metres along their respective
lines. They form an oblique basis: a center `(x, y)` is the origin plus
`x * unit_street + y * unit_neighbour`. It is **not** a perpendicular offset
from either line. The house stays a true rectangle, with its 11.6 m side along
the street at zero rotation. Positive angles rotate it counterclockwise about
its center. The drawing grid remains Cartesian, with its origin moved to the
intersection; short x/y arrows show the oblique placement axes.

For a one-off placement without editing the configuration, use:

```bash
python3 survey_points.py --house-center -8 7 --house-angle 10
```

Use `--no-house` to omit the rectangle. Python callers can pass
`house=SurveyHouse(...)` to `render_survey_points`; its default `None` omits the
overlay. Placement requires both named lines and rejects parallel fitted
lines. SVG metadata includes the oblique directions, center, rotation, and
rectangle corners in drawing and original survey coordinates.
The terminal also prints the shortest perpendicular distance from the rotated
house rectangle to each infinite fitted line, in metres. A line that crosses
or touches the rectangle has distance zero. These are actual perpendicular
gaps, rather than distances measured along the oblique placement axes.

When both fitted lines are available, a derived **neighbour window** point is
drawn at placement coordinates `(0, 7.75)`, with elevation **417.60 m Bpv**.
It follows the fitted neighbour line automatically, even with `--no-house`.
Tune `NEIGHBOUR_WINDOW_DISTANCE` and `NEIGHBOUR_WINDOW_ELEVATION` in
`survey_points.py`. It is labelled by name and elevation and included in SVG
metadata, but never added to `points.txt` or used to fit the measured lines.

The first default roof profile follows the **two right-hand corners of the
placed house**, including its current rotation. Its midpoint elevation is
`417.0 + total_house_height - 0.875` metres Bpv. A second parallel profile is
2.25 m away, perpendicular to the first and on the side farther from the
neighbour line. It retains the original midpoint elevation
`417.0 + total_house_height`. Both use the main roof angle.
`HOUSE_ROOF_EDGE_DROP` and `HOUSE_ROOF_PROFILE_SPACING` control these distances.
`house_ifc.py points` supplies the live calculated values. The standalone
command reads the current arithmetic geometry definitions without executing
the model or solver, using the same normal-offset roof-plane geometry.
`HOUSE_ROOF_ENABLED` turns these profiles on/off; `HOUSE_ROOF_GROUND_ELEVATION`
sets the explicit 417.0 m datum. Python callers enable it with
`house_roof=True` and can supply `total_house_height` and `main_roof_angle`.

Define additional roof profiles in the shared `ROOF_SLOPES` tuple in `survey_points.py`:

```python
ROOF_SLOPES = (
    RoofSlope(start=(-10, 5), end=(-10, 14), elevation=423.0, angle_degrees=35),
)
```

The example values are illustrative. Both points use the same oblique
street/neighbour coordinates. The highest elevation (metres Bpv) is at their
midpoint, and the roof descends toward either point at the specified angle
to horizontal. Heights use actual plan distances, rather than distances in
the oblique coordinate pair. At any plan position, the height is
`elevation - abs(projected_distance_from_midpoint) * tan(angle)`; it is
constant in the direction perpendicular to the specified line. Query it with
`roof.elevation_at((x, y), axes)` using `SurveyAxes.from_polylines(...)`.
The calculation extends indefinitely past both points, without clipping.

Both drawing commands show each profile as a line that fades from red at the
highest point to pale red at the sides, labelled with its midpoint elevation
and slope. `ROOF_SLOPE_OVERHANG` adds 2 m beyond each endpoint for the preview;
this affects only the drawing. The page fits the preview as well as the points
and house. Python callers can pass `roof_slopes=(...)` and `roof_overhang=2.0`
to `render_survey_points`. Roof profiles require both named reference lines
and can be drawn with the house overlay disabled.

For every drawing with roof profiles, the terminal reports the first
**clockwise rotation from neighbour window → origin** at which any profile
is seen at least 45° above horizontal. At each ray/profile intersection,
the test is `plan_distance <= roof_elevation - window_elevation`. Distances
are true Cartesian plan distances. The calculation uses infinite profile
lines, including their continuing downhill heights; drawing overhangs and
endpoints do not limit it.

`first_roof_45_degree_hit(roof_slopes, axes, observer)` returns the first hit
(or `None` if there is none in a full turn). It solves the quadratic
intersection of each two-sided height profile with the observer's 45° cone,
and also tests the initial bearing. Tangencies and roofs already above the
threshold at the starting direction are included without angular stepping.
Output includes clockwise angle, roof profile number, intersection in
street/neighbour coordinates, roof elevation, plan distance, elevation rise,
and vertical angle.

## IFC basement and foundations

`foundation_specs` in `house_ifc.py` explicitly lists every supported
ground-floor load-bearing wall, including `wall_kitchen_3` and `wall_bathroom`.
It is evaluated after those walls are created, and missing load-bearing walls
are reported instead of silently omitted. Each entry can override the defaults:

```python
FoundationSpec(
    wall_kitchen_3,
    wall_thickness=0.30,
    footer_width=0.80,
    footer_height=0.50,
)
```

Omitted dimensions use `FOUNDATION_WALL_THICKNESS`, `FOUNDATION_FOOTER_WIDTH`
and `FOUNDATION_FOOTER_HEIGHT`. Footers are centred under the configured
foundation wall and retain corner returns at real wall ends.

`FOUNDATION_HEIGHT_MAP` holds ordered `(global_y, nominal_footer_bottom_z)` breakpoints:

```python
FOUNDATION_HEIGHT_MAP = FoundationHeightMap((
    (0.0, FOUNDATION_FOOTER_BOTTOM_Z),  # one entry gives a uniform level
    # (3.0, FOUNDATION_FOOTER_BOTTOM_Z + 0.25),
    # (6.0, FOUNDATION_FOOTER_BOTTOM_Z + 0.50),
))
```

Each level applies until the next Y breakpoint; the first/last levels extend
outside the range. Values are absolute model Z, so `earth_to_z(...)` can also
be used. Footer tops change immediately at each breakpoint, at nominal bottom
plus `footer_height`. The actual underside follows 45-degree ramps on the
shallower side, adding concrete while preserving the configured minimum height.
A 0.4 m upward change at Y = 3.3 starts its underside ramp there and reaches the
new bottom at Y = 3.7. Downward changes ramp before the breakpoint. Closely
spaced ramps combine continuously without becoming steeper than 45 degrees.
`foundations.py` clips both wall bodies and complete footer footprints at the
Y boundaries, including transverse strips crossing a step. No corner return is
added at an artificial step. Wall tops remain at `-BASEMENT_CEILING_SPACE`;
bottoms follow footer top plus `FOUNDATION_BASE_PLATE_THICKNESS`. The foundation
plan camera follows the highest footer and section legends mark ramped-footer
heights as minima. `BBIM_StripFooting.BottomZ` retains the nominal level;
`MinimumBottomZ` and `BottomProfile` describe the actual underside.

The basement slab footprint and exterior finishes are separate from this
depth profile. Changing it does not change the slab footprint; defining the
partial basement is a separate layout change.

The ground-floor storey stays at Z = 0. `BASEMENT_FLOOR_START` is the top of
the basement slab, derived from `FOUNDATION_WALL_HEIGHT = 2.25` and
`BASEMENT_CEILING_SPACE = 0.25`. The latter reserves space for a future
ceiling; no ceiling element is generated yet.

| Part | Absolute Z range (m) | Storey |
|---|---|---|
| Strip footers | −3.15 to −2.65 | Foundations |
| 150 mm base plate | −2.65 to −2.50 | Basement |
| 2.25 m walls | −2.50 to −0.25 | Basement |
| Reserved ceiling space | −0.25 to 0.00 | — |

The slab sits directly on the footer tops; the walls start at the slab top.
The Foundations storey is at `FOUNDATION_FOOTER_BOTTOM_Z`, and Basement is
at `BASEMENT_FLOOR_START`. All above-ground storey elevations are preserved.
`found` cuts the footers at mid-height and adds the basement wall footprints
as drawing-only dashed outlines. `add_wall_outlines()` can use walls from
other storeys without including their 3D bodies in the drawing.
The AA/BB sections and the drainage schematic reference the relocated slab.
The optional foundation-insulation helper follows that slab in Basement.

## IFC purlin sections

The replacement perpendicular roof has its two support members, rafters and
above-rafter layers. No simulator connections have been added yet.
`TRANSVERSE_PURLIN_TOP_ABOVE_FLOOR` sets the new purlin's top relative
to the upper structural slab/storey datum (`UPPER_FLOOR_START`).
Its centreline is X = `LOWER_NADEZDIVKA_X + 0.280`, its section reuses
`VAZNICE_SIDE_BASE` / `VAZNICE_SIDE_HEIGHT`, and it remains one continuous
piece for now. It runs along Y over wall 4's ring-beam span. The new transverse
wall plate uses `WALL_PLATE_SIZE`, with its centreline and underside derived
from that ring beam so it sits directly on the concrete. Both are created by
`add_transverse_roof_supports()` as `transverse_purlin` and
`transverse_wall_plate`, included in the roof drawing and shared timber schedule
(GL24c purlin, C16 plate), without changing existing rafter-support lookups.

`transverse_roof` slopes through the outer top edges of these two supports.
`transverse_rafters` uses `TRANSVERSE_RAFTER_SIZE` (80 × 140 mm) and `RAFTER_Z_OFFSET`, with
centres returned by `transverse_rafter_y_positions()`: `TRANSVERSE_RAFTER_SIZE[0]/2`,
each integer metre strictly between the edge centres, then
`HOUSE_DEPTH - TRANSVERSE_RAFTER_SIZE[0]/2`. The current house has nine rafters.
Their high ends are cut vertically at `LOWER_NADEZDIVKA_X + 0.155`. Outside wall 4,
both main-roof eave rules apply: the vertical limit is
`HOUSE_WIDTH + TRANSVERSE_ROOF_EAVE_OVERHANG - ROOF_EAVE_SETBACK`; the horizontal limit
is controlled by `TRANSVERSE_ROOF_EAVE_REFERENCE_X_OFFSET` and
`TRANSVERSE_ROOF_EAVE_REFERENCE_DROP`, retaining the previous roof outline
independently of its supports.
The finished beam follows whichever cut is reached first. The common
`local_y_limits_from_cuts()` now handles global-X, Y and Z boundaries, so
the complete rafter section reaches all cuts without guessed source lengths.
These rafters share the Rafters visibility container and have their own
measured C22 schedule row, without changing the high/dormer rafter arrays.

`add_transverse_rafter_braces()` adds one outward-rising 45° brace beneath
each transverse rafter. The former outer beam and four posts are removed.
The brace centreline starts at the structural wall's outer face, 0.50 m below
the wall-plate underside (`TRANSVERSE_RAFTER_BRACE_DROP`), and meets the
rafter underside. Vertical wall-face and sloped rafter cuts trim the full
section. `TRANSVERSE_RAFTER_BRACE_SIZE` defaults to the transverse rafter
section. Braces use the exposed-wood finish and appear in the shared roof
schedule as `Vzpěry – příčné krokve` with material C22.

`add_transverse_roof_layers()` reuses the main-roof MDF board, underlay,
counter-battens, tile battens and tiles on this slope. Set
`TRANSVERSE_ROOF_Y_OVERHANG` (default 0.25 m) to control the overhang past
both street/garden walls: the tiles span global Y from `-overhang` to
`HOUSE_DEPTH + overhang`. The layers below them keep the shared 20 mm siding
allowance at both Y ends and at the X eave. Counter-battens follow the new
rafters; tile battens cross them at the existing `TILE_BATTEN_SPACING`.
`add_transverse_roof_siding()` closes the two sloped street/garden edges
and the west eave using plain `Wood siding solid` in the shared
`ROOF_EAVE_SETBACK` slots. The side caps run from rafter underside to tile
underside, clipped by the horizontal eave cut; the west fascia runs from
that horizontal cut to tile underside. The facade's board pattern is not used.
The high ends remain cut at `LOWER_NADEZDIVKA_X + 0.155`; the retained interior
ceilings and their independent ranges are unchanged.

`add_west_roof_closure()` closes the high roof above the upper floor.
The white `Facade finish` occupies X = `LOWER_NADEZDIVKA_X + WEST_CLOSURE_AIR_GAP`
to `LOWER_NADEZDIVKA_X + WEST_CLOSURE_AIR_GAP + FACADE_THICKNESS`.
The outer wall face is exactly `LOWER_NADEZDIVKA_X`; its inner face is
`LOWER_NADEZDIVKA_X - WEST_CLOSURE_WALL_THICKNESS`.
Towards decreasing X, it is followed by an empty cavity
(`WEST_CLOSURE_AIR_GAP`) and a 175 mm VPC wall
(`WEST_CLOSURE_WALL_THICKNESS = BWTy`). The wall reuses the project's
`VPC cihla 175mm` type and its Brick material. The siding's outer position
stays fixed; its offset from the wall is the cavity width.

`west_closure_wall` is an upper-floor `IfcWall`; `west_roof_closure` contains
just its opening-aware siding `IfcCovering`. The cavity has no solid IFC
element. `west_roof_closure_x_ranges` records `Siding`, `Air gap` and `Wall`.
The closure masonry reuses all cut planes from the east upper gable (`wall_1_u`):
the two rafter-underside slopes and the horizontal masonry cap. Its facade uses
those same two slopes up to the ridge, matching the east facade. The masonry
runs only between `BWTy` and `HOUSE_DEPTH - BWTy`; the siding extends beyond its
host ends to meet the street/garden facade faces. `add_facade_layer(cuts=...)`
can override the host cuts; the default inherits them.

The masonry bottom follows the common top of `pruvlak31x`, `pruvlak32x` and
`pruvlak33x` (`WEST_CLOSURE_SUPPORT_GIRDERS`), currently 300 mm above
`UPPER_FLOOR_START`. The supports must be horizontal and have matching top
levels. The siding extends down to the upper-floor slab, covering the girders.
The window's sill remains referenced to the finished upper floor.

`west_closure_window` is defined before the siding so its opening is copied
through that covering across the gap. Tune `WEST_CLOSURE_WINDOW_CENTER_Y`,
`WEST_CLOSURE_WINDOW_WIDTH`, `WEST_CLOSURE_WINDOW_HEIGHT` and
`WEST_CLOSURE_WINDOW_SILL_HEIGHT` beside the helper. Defaults are centred along
Y, 1.0 × 1.0 m, with a 1.5 m sill above the finished upper floor.
The window moves with its wall while retaining its Y and Z coordinates.

`west_roof_closure_layout()` is also the source for `WEST_CLOSURE_INNER_X`.
Service-room floor boundaries, partition lengths and dimensions use that
inner wall face. The stiffening ribs under the closure also derive their
position from it, so they remain centred under the 175 mm wall.

Each street/garden purlin consists of two independent pieces. The left and
middle pieces meet at the wall2 centre line and share the top `PURLIN_TOP_Z`.
The middle piece extends to `LOWER_NADEZDIVKA_X + 0.105`. Only the left and middle purlin pieces remain;
the low right pieces and their independent roof settings have been removed.
The middle pieces bear on the unchanged inner-wall level
`PURLIN_WALL_TOP_HEIGHT`. `VAZNICE_BASE`, `VAZNICE_HEIGHT` and `VAZNICE_DIST`
describe the middle piece; `VAZNICE_SIDE_BASE` and `VAZNICE_SIDE_HEIGHT`
describe the high left piece.

`VAZNICE_SIDE_DIST = VAZNICE_DIST + (VAZNICE_BASE - VAZNICE_SIDE_BASE) / 2`
aligns the outer faces (DIST measures to the centreline), preserving both the
main and dormer roof angles. The high left piece sits above the inner-wall
level by `PURLIN_SIDE_PACKING_HEIGHT = VAZNICE_HEIGHT - VAZNICE_SIDE_HEIGHT`.
The left gable top rises by that amount. At wall2, two
short timber blocks support just the left-piece halves: width
`VAZNICE_SIDE_BASE`, height `PURLIN_SIDE_PACKING_HEIGHT`, length `BWT/2`.
They appear as “Podložky vaznic” in the roof timber schedule. Spacers and
collar ties follow the explicitly selected framing supports; lower under-rafter
insulation independently uses the lower purlin faces throughout its inner bay.
The timber schedule separates the middle/side collar ties and spacers.
Its `Material` column starts with `gl24c` for purlins and `c22` for other
members. Override a row using `"material"` in its fourth settings dictionary
in `house_ifc.py`; these labels do not change IFC materials or simulator inputs.

## 2D roof-frame model

Run `python3 roof_frame.py` to compare a normal roof section with horizontally
free versus restrained purlin supports, with and without kleštiny. It reads
geometry, member dimensions and tributary widths from `house_ifc.py` without
importing it or generating an IFC. The default selects an actual interior
uncut normal main-rafter line; material classes remain explicit in `main()`.
Masses and snow are shared with `rafter_load.py`.

It prints forces/reactions and generates `roof_frame_report.pdf`, including
a comparison table, signed horizontal purlin loads, assumptions, and frame/N/M
diagrams. The no-collar comparison keeps the ceiling mass as vertical loads at
the former collar ends; a replacement ceiling is not designed. This is a
preliminary normal-section model, not a dormer or complete roof safety verification. See
[roof_frame.md](roof_frame.md) for the interfaces, support assumptions,
load conventions and remaining checks.

## House 2 roof simulator (PyNite)

`roof_frame_3d_house2.py` reads the current `house2.py` geometry without
executing the IFC generator. It models the rafters, purlins,
side cross beams, configurable posts, optional pin-ended braces and paired
collar ties above the purlins. Each collar pair is one bilateral axial spring
with the combined stiffness and self-weight of its two IFC boards.
Each purlin accepts one or more posts at independent Y coordinates. By default
each purlin is split at every post centre (two pieces for one post),
with bending hinges shown as blue diamonds on the plan. Use
`--continuous-purlins` to restore continuous purlins. The cuts do not add
ground supports or change timber weight; the IFC purlins remain unchanged.
The default includes gable-wall bearings and omits the tesařské pásky,
including their self-weight and attachment arms. Use `--braces` to include
three per post as compression-only axial springs, or `--braces --brace-action both`
to allow tension too. The IFC braces remain in the house model.
Rafter-to-wall-plate seats are vertically supported and completely free
to slide in X by default, with zero X reaction; Y stays fixed to prevent
sideways tipping. The console
prints the maximum movement, including separate SLS/ULS maxima. Use
`--horizontal-stiffness rigid` to compare with the previous restrained seats,
or supply a positive kN/mm stiffness for elastic X connections (Y fixed).
All simulation defaults are in the **USER INPUTS** block at the top of
`roof_frame_3d_house2.py`: edit `Settings.roof_mass`, `snow_load`, material
grades and connection/support options there. The CLI uses these local
defaults and changes only explicitly supplied options. Loads are independent
of `rafter_load.py`; geometry follows `house2.py`, and material properties
use `materials.py`.

```bash
.venv-roof3d/bin/python roof_frame_3d_house2.py
.venv-roof3d/bin/python -m unittest test_roof_frame_3d_house2 -v
```

Outputs include 3D/plan PNGs, force and support CSVs, instantaneous L/300
and L/500 chord checks, and a JSON calculation basis. Red circles mark
support uplift forces. See [roof_frame_3d_house2.md](roof_frame_3d_house2.md)
for assumptions, material/load overrides and connection comparisons.
The default plan image is `roof_frame_3d_house2_plan.png`, the counterpart
of the old `roof_frame_3d_restrained_plan.png`. It shows wall-plate reaction
arrows over undeformed timber footprints: green when all SLS chord checks
pass L/500, orange when L/500 fails but L/300 passes, red when L/300 fails,
and grey for unassessed members and rigid wall plates. Colours use the worst
support span and SLS combination. It also shows magenta collar forces (positive tension, negative compression,
total per board pair). `--plot-combination ULS_symmetric` selects ULS forces;
the default is `SLS_symmetric`.

## Original house 3D roof-frame model (PyNite)

The simulator has not yet been updated for the lowered roof section and split
wall plates. The description below refers to its previous, single-level framing;
do not use its results to assess the current stepped IFC roof.

`roof_frame_3d.py` models rafters (including the dormer), the six independent
purlin pieces, with paired axial kleštiny by default (`--no-collar-ties` for comparison).
The six purlin sections follow the current middle/side dimensions, common
top level and aligned outer faces from `house_ifc.py`.
Adjacent pieces have separate supported ends, with no Gerber joints or sedla.
Spacers and automatic collar heights follow their local purlin sections.
The four wall-plate outlines represent
one immovable rigid wall plate/ring-beam support, not elastic timber members.
It safely reads the
current `house_ifc.py` input geometry without regenerating the IFC. Purlins bend
between their actual wall bearings, rather than being fixed at each rafter.
Shortened dormer-side rafters end at the local purlin bottom datum. Packing
blocks are ideal rigid bearings in the simulator, not separately deformable
members; their compression/fastening is not checked.

Install the optional dependencies in a separate environment (PyNite uses NumPy
2), then run:

```bash
python3 -m venv .venv-roof3d
.venv-roof3d/bin/python -m pip install -r requirements-roof3d.txt
.venv-roof3d/bin/python roof_frame_3d.py
.venv-roof3d/bin/python roof_frame_3d.py --no-collar-ties
```

The optional ties use pinned axial tension/compression links. Edit their
`COLLAR_TIE_*` dimensions and placement parameters near the top of this script,
independent of the IFC collar definitions. Ties add their own weight but not
suspended-ceiling loads; bending, buckling and joint capacity are not checked.
Reports without ties use `_no_collars_restrained` (or `_no_collars_free`) filenames so
they do not overwrite the default reports. The terminal/CSV include signed axial
forces, positive for tension and negative for compression.

It uses a shared horizontal spring stiffness **only for the rafter connections to
the rigid wall plate/ring beam**, set by
`HORIZONTAL_SUPPORT_STIFFNESS_KN_MM`. Rafter motion at a wall plate is connection
slip; the supporting structure does not move. Purlin bearings are rigid and do
not use this setting. `DORMER_HORIZONTAL_SUPPORT_STIFFNESS_KN_MM` separately
controls only dormer seats in both horizontal directions: `"inherit"`,
a positive kN/mm value, or `None` for rigid. The CLI equivalent is
`--dormer-horizontal-stiffness 0.12` (or `inherit` / `rigid`). Normal-roof and
legacy house-cut seats keep the general value. Reports record both effective values.
The original
0.12 kN/mm sensitivity calibration gave about 39 kN on the street middle
purlin with 135 kg/m² roof layers in the previous elastic wall-plate model;
that calibration is historical, **not verified connection stiffness**.
Use `--horizontal-stiffness rigid` for a fixed-connection comparison, or
`--purlin-lateral both` to compare explicitly free/rigid lateral purlin bearings.
It exports timber forces, support/ring-beam loads and movements, input
assumptions and a deformed 3D image. It retains
absolute displacement and also screens rafter and purlin departure from their
displaced endpoint/bearing line against L/300 and L/500. Rafters without a
wall-plate–ridge pair use their actual two supports by default. All timber
defaults to C22. Suspended ceiling loads are omitted because their replacement
support is unspecified.
This is a preliminary force model, not a roof safety assessment. See
[roof_frame_3d.md](roof_frame_3d.md) for assumptions, options and regression tests.

It also generates `roof_frame_3d_restrained_plan.png`: a top view coloured
green/orange/red by the worst SLS L/500 and L/300 chord checks. Unassessed
members and rigid wall-plate/ring-beam outlines are grey. Optional collar ties have magenta
outlines and axial force labels between two inward (compression) or outward
(tension) arrows; magenta does not indicate a passed check. Signed outward force arrows in kN
mark every rafter/wall-plate connection for ULS symmetric snow; use
`--plan-force-combination SLS_symmetric` for service loads. These are **direct
connection reactions delivered to the rigid wall plate/ring beam**, identical
to terminal/support CSV values for the same combination. `--no-plot` suppresses
both images.

## Rafter load helper

Structural timber properties live in the dependency-free [materials.py](materials.py).
It defines C16, C18, C20, C22, C24, GL24c, GL24h, GL28c and GL28h once: strengths, E/G/E90,
mean density for connection slip, and the material partial factor. Use
`resolve_timber_grade("c16")` to retrieve a frozen grade; names are case-insensitive.
`rafter_load.py`, `roof_frame.py`, `roof_frame_3d.py` and the IFC roof schedule
all use this registry. Element selections, drawing colours/hatches, loads and
the separately configured conservative self-weight density remain local.

The report/check wrappers accept `material="gl24c"` for combined glulam
(EN 14080), alongside C16, C18, C20, C22, C24, GL24h, GL28c and GL28h. This applies to rafters,
simple/continuous purlins and stacked double purlins. Material names in this
script are case-insensitive; existing selections are unchanged.

`rafter_load.py` checks the main and dormer rafters as simply supported
rectangular members. It checks the street-side purlin as one continuous beam
over four supports. Edit its `USER INPUTS` constants or override them on the
command line:

```bash
python rafter_load.py --width 80 --height 200 --span 3.7 \
    --angle 36.65 --dormer-span 3.1 --dormer-angle 17.03 \
    --deflection-ratio 300 --modulus 11 --spacing 0.8 --snow-load 1.5 \
    --purlin-width 160 --purlin-height 280 \
    --purlin-left-width 140 --purlin-left-height 240 \
    --purlin-right-width 120 --purlin-right-height 220 \
    --purlin-spans 3.74 4.80 2.75 \
    --upper-rafter-length 1.08
```

Enter each permanent roof-layer mass in `ROOF_LAYERS_KG_M2` near the top of
the script. Values are kg/m² of the actual sloping surface. Leave an unknown
value as `None`: the script will calculate with the known layers while clearly
marking the result incomplete instead of silently treating that layer as
weightless.

The snow input is a vertical roof load per square metre of horizontal
projection; the helper applies both its tributary-area projection and its
component perpendicular to the sloping rafter. It reports immediate and
creep-adjusted final deflection, followed by preliminary C24 bending, shear,
and support-bearing checks for both the main and dormer rafters. Both cases
share the section, spacing, material, layers, snow, and safety factors; only
their support spans and roof angles are separate. The Eurocode-style material,
creep, action, and partial factors are all editable constants. Lateral
stability, axial force, notches, connections, wind uplift, fire, and the
selection of governing snow arrangements remain outside this member check.

The purlin check intentionally uses only the simple street roof. Its
transferred permanent load uses the entered upper rafter contribution plus
half of the lower rafter support span. Snow uses the horizontal projection of
that tributary roof width and is applied uniformly to all three purlin spans.
Rafter self-weight and purlin self-weight are included. Use
`PURLIN_ADDITIONAL_PERMANENT_LOAD_KN_M` (or `--purlin-extra-load`) for a
ceiling, collar-tie, or other vertical line load that really bears on the
purlin. The purlin calculation smears discrete rafter reactions into a uniform
line load. It reports deflection in every span, positive span moments, negative
support moments, shear, and reactions/bearing. The garden/dormer purlin, end
overhangs, non-moment-transferring splices, snow drift/shape cases, and
lateral-torsional stability remain outside this simplified check.

The report also checks all three purlin spans as independent, simply supported
pieces. Configure their `(width, height)` pairs in
`PURLIN_SEGMENT_SIZES_MM`. On the command line, `--purlin-width` and
`--purlin-height` set the middle piece, while the corresponding
`--purlin-left-*` and `--purlin-right-*` options set the side pieces. The
continuous alternative deliberately uses the middle piece's dimensions over
all three spans; the split alternative calculates each piece with its own
self-weight, stiffness, and resistance.

For a butt joint centred over a support, each independent piece defaults to
half of `--purlin-bearing-length`; override that detail with
`--purlin-split-bearing-length`. The calculation checks the individual timber
pieces, but not the splice hardware or the supporting wall itself.

Persisted plan and elevation drawings may reserve additional paper space on
their right side without changing the camera framing.  The width is expressed
in printed millimetres.  Optional tables are stacked from the top of this
panel; the first supported table is a material-pattern legend:

```python
drawing = house.add_drawing(
    "Ground plan",
    x=6,
    y=4,
    z=1.6,
    radius=8,
    storeys=[ground],
    right_panel_width=100,
)
drawing.add_material_legend(
    [
        (
            "brick",
            "OBVODOVÉ ZDIVO Z BROUŠENÝCH KERAMICKÝCH TVÁRNIC, "
            "TLOUŠŤKY 440 MM",
        ),
        (
            "diagonal1",
            "VNITŘNÍ NENOSNÉ ZDIVO Z BROUŠENÝCH KERAMICKÝCH CIHEL",
        ),
        (
            "crosshatch1",
            "TVÁRNICE ZTRACENÉHO BEDNĚNÍ PROLITÉ BETONEM C 20/25",
        ),
    ],
    title="LEGENDA MATERIÁLŮ",
)
```

Line legends use the actual linework annotation's style, so dash spacing and
thickness stay consistent with the drawing:

```python
outline = drawing.add_wall_outlines(walls, style="dashed")
drawing.add_line_legend([(outline, "Obrys nosných stěn")])
```

Draw individual lines using model-space 2D coordinates (metres):

```python
line = drawing.add_line(start=(1, 2), end=(3, 2), style="dashed", color="red")
drawing.add_line((2, 0.65), (2, 0.1), color="orange", line_width=0.3)
```

`style` defaults to `"solid"`; `color` defaults to `"black"` and accepts
named colors or `#RGB`/`#RRGGBB`. Plans use `(x, y)`, elevations looking along
X use `(y, z)`, and elevations looking along Y use `(x, z)`, just like notes
and dimensions. Lines are drawing-only annotations, not physical model parts.
`line_width` sets stroke thickness in printed millimetres (default 0.1),
independently of drawing scale. It must be positive. Legend samples inherit
the line's thickness; style-only legend dictionaries also accept `line_width`.

Use `add_poly_line()` to draw a connected route through more than two points:

```python
pipe = drawing.add_poly_line(
    [(2, 0.65), (2, 0.2), (4, 0.25), (4, 1)],
    color="orange", line_width=0.3,
)
```

Coordinates and options match `add_line()` (in `kanal`, points are `(x, z)`).
It returns a single native annotation, usable in `add_line_legend()`.
At least two points are required, with no consecutive duplicates. Repeat the
first point at the end to close an unfilled outline. For `dashed-arrows`,
arrows follow point order and the pattern restarts at each corner.

For a single route spanning stair flights and their landing, add optional
endpoint symbols instead of repeated arrows:

```python
drawing.add_poly_line(
    [(1, 1), (3.7, 1), (4.2, 1), (4.2, 2.5)],
    style="dashed", arrow_end=True, circle_start=True,
)
```

Both options default to `False` and may be used independently. The open
arrowhead sits at the last point and follows the final segment; the small
unfilled circle is centred on the first point. They share the line's color
and width, but remain solid even for dashed routes. Symbols have fixed printed
sizes (arrowhead 2 mm long × 1.5 mm wide; circle radius 0.5 mm), independent of
drawing scale. They work in plans, axis-aligned elevations and mirrored exports.
The returned entity is still the route; its endpoint symbols use one additional
native annotation scoped to the same drawing.

For one diagonal floor-change arrow, use:

```python
drawing.add_change_floor_symbol(x=2, y=1, type="to up")
```

Left/right always mean the rendered page, even when the house's X axis is
mirrored. `"to up"` starts at the point and points right/up; `"to down"`
starts there and points left/down; `"from up"` comes from right/up and ends
at the point; `"from down"` comes from left/down and ends there. Coordinates
match `add_line()` (in `kanal`, `y` is the diagram's height Z). Optional
`size` sets the diagonal shaft length in metres (default 0.6); `color`,
`line_width` (printed mm, default 0.1) and `name` are also supported. Each
call adds one drawing-only arrow with a single open head and a small
outlined circle at the supplied anchor point. The circle radius is `size/12`
and uses the arrow's color and line width.
The complete symbol is moved to a final SVG overlay layer, so wall-opening
masks, walls, doors and other drawing geometry cannot cover it. This applies
to SVG, PNG and PDF exports and does not alter the IFC model geometry.

`style="dashed-arrows"` alternates a plain dash with an arrow pointing toward
`end`; reversing the endpoints reverses the arrows. The pattern uses actual
vector segments (including the arrowheads), at a constant paper size for the
drawing scale, and the same geometry is used in legend samples.
Pass `(line, description)` to `add_line_legend()` to reuse its appearance, or
use a style-only dictionary when the line has not yet been placed:

```python
drawing.add_line_legend([
    {"style": "solid", "color": "black", "description": "Spodní úroveň základových pasů"},
    {"style": "dashed", "color": "red", "description": "Zemnící pásovina FeZn 30/35"},
])
```

Circles, rectangles and text use the same model coordinates as `add_line()`:

```python
drawing.add_circle(center=(2, 3), radius=0.5, color="blue")
drawing.add_text(point=(2, 3), text="ČOV", font_size=3)
drawing.add_rectangle(start=(4, 2), end=(6, 4), style="dashed")
drawing.add_rectangle(start=(7, 2), end=(7.5, 4), pattern="stone-wall")
drawing.add_polygon([(8, 2), (11, 2), (11, 4), (8, 3.5)],
                    pattern="stone-wall-background", color="#d0d0d0", background=True)
drawing.add_text(point=(5, 3), text="Nádrž", color="green")
```

Circle radii and rectangle corners are in metres. Both shapes are unfilled
by default and support `style="solid"` (default) or `"dashed"`. Rectangles
accept `pattern="stone-wall"` (or another ID in `drawings/assets/patterns.svg`)
for a native filled area; the stone pattern has irregular polygon outlines
and narrow white mortar gaps. Rectangles and polygons accept `background=True`
to paint them behind model geometry and terrain, keeping stairs and other
foreground parts visible. Text uses printed
millimetres for `font_size` (default 3 mm), so its size does not depend on the
drawing scale. It is centred horizontally and vertically by default;
`alignment="left"`/`"right"` changes horizontal alignment. All three helpers
accept named or hex colors (default black), return drawing-scoped native IFC
annotations and work in plans or axis-aligned elevations. Czech text remains
selectable in PDF exports. None of these helpers adds physical 3D geometry.

For a drainage stack (stoupačka kanalizace), use a diagonal half-white,
half-orange circle without a surrounding box:

```python
stack_position = (2, 3)  # model coordinates, shared by all floor plans
ground_drawing.add_drainage_stack(center=stack_position)
upper_drawing.add_drainage_stack(center=stack_position, diameter=0.11)
```

`add_drainage_stack()` is plan-only; its diameter is in metres (default
0.11 m). It returns the circular outline and creates drawing-scoped native
IFC annotations, without adding a physical pipe or cutting any openings.

Like material legends, `add_line_legend()` requires a right panel at least
40 mm wide and stacks with other tables. Its default title is `LEGENDA ČAR`.

Descriptions wrap automatically and may also contain explicit newlines.
Available pattern names are defined in `drawings/assets/patterns.svg`, including
`diagonal1`, `diagonal2`, `crosshatch1`, `brick`, `concrete`, `sand`, and
`wood`. Project-specific reusable patterns include `drywall-diagonal1` (the
`diagonal1` hatch on the drywall tint) and `random-dots` (the preserved
irregular dot field). A zero `right_panel_width` (the default) keeps the
original square drawing sheet.

The Blender-side implementation is in `bonsai_scripts/generate_plan.py`.
Parameters are passed directly after Blender's `--` command separator instead
of through a shared parameter file, preventing stale settings and allowing
independent runs. Bonsai must be installed and enabled in Blender. The current
drawing operators require a live 3D viewport, so Blender opens normally, runs
without user interaction, and closes after creating the SVG.

The editable drawing stylesheet is `bonsai_scripts/assets/plan.css`. Each plan
generation explicitly assigns this file to the Bonsai drawing and embeds its
current contents in the SVG. This makes the SVG disposable: change `plan.css`
and regenerate instead of editing `drawings/assets/default.css` or the output
SVG. A different complete stylesheet can be supplied with
`stylesheet="path/to/other.css"`.
