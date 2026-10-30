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
In `house_ifc.py`, `UPPER_RING_BEAM_HEIGHT` controls the additional concrete band,
whose top is at `UPPER_FLOOR_START + NADEZDIVKA` on the higher perimeter parts
and internal load-bearing walls, interrupted at existing openings.
`LOWER_NADEZDIVKA_X` ends the high upper front/back walls between wall3 and
wall4. The former low knee walls and west upper gable have been removed;
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
cells are not treated as room openings. Foundation slabs (`BASESLAB`) and walls
made of `ztracene bedneni` keep their original thin lines in all views; they
still mask contact edges of adjoining outlined solids. Ordinary walls, floors
and ceilings remain outlined.
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
high wall plates end at the closure MDF's inner face,
`LOWER_NADEZDIVKA_X - 0.05`.
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

### Multiple drawings on one sheet

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
part and `Wood siding` on the low part, meeting at `LOWER_NADEZDIVKA_X + 0.1`.
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

Projected roof tiles use the `roof-tiles` SVG pattern: terracotta red
background, thin black side joints and curved course edges. Projected facade siding
uses the `wood-siding` pattern with a warm timber-brown background. Change the
background `<rect fill="...">` in either pattern in `drawings/assets/patterns.svg`
to tune its view color; the render passes preserve it while scaling/projecting
the pattern. Exposed tile edges use that same color as a solid fill, without
the top-face tile pattern. Section-cut colors are independent and remain unchanged. Tile width is
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
Points must be ordered horizontally. Hatch depth is in model metres and line
width in printed millimetres. Terrain masks building geometry below the
profile while dimensions and annotations remain visible. It adds no 3D earth
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
Notes are preserved for reference and do not affect connections or ordering.
The drawing preserves each measured position, using small crosses and height
labels directly below the crosses, in light blue and without leader lines.
Hovering over a cross in the SVG reveals its ID, original coordinates and note,
and hovering over a polyline shows its color and ordered point IDs. Add `--point-ids` to either
command to print IDs too. All points are retained, including points describing
structures; no terrain surface or property boundary is inferred from them.

The plot uses local grid-east/grid-north axes, `east = Y0-Y`, `north = X0-X`,
with a printed origin and scale bar. `SurveyFrame` provides the inverse mapping
for later placement work. Grid north follows S-JTSK, not geographic north.
Original coordinates and notes are also embedded in the SVG's `survey-data`
metadata. House coordinates and X mirroring do not affect this drawing.

PDF defaults to A4 landscape and chooses a scale that fits (currently 1:500).
For a larger copy, run
`python3 survey_points.py --paper A3 --scale 250`.

## IFC basement and foundations

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
Its centreline is X = `LOWER_NADEZDIVKA_X + 0.125`, its section reuses
`VAZNICE_SIDE_BASE` / `VAZNICE_SIDE_HEIGHT`, and it remains one continuous
piece for now. It runs along Y over wall 4's ring-beam span. The new transverse
wall plate uses `WALL_PLATE_SIZE`, with its centreline and underside derived
from that ring beam so it sits directly on the concrete. Both are created by
`add_transverse_roof_supports()` as `transverse_purlin` and
`transverse_wall_plate`, included in the roof drawing and shared timber schedule
(GL24c purlin, C16 plate), without changing existing rafter-support lookups.

`transverse_roof` slopes through the outer top edges of these two supports.
`transverse_rafters` uses the normal `RAFTER_SIZE` and `RAFTER_Z_OFFSET`, with
centres returned by `transverse_rafter_y_positions()`: `RAFTER_THICKNESS/2`,
each integer metre strictly between the edge centres, then
`HOUSE_DEPTH - RAFTER_THICKNESS/2`. The current house has nine rafters.
Their high ends are cut vertically at `LOWER_NADEZDIVKA_X`. Outside wall 4,
both main-roof eave rules apply: the vertical limit is
`HOUSE_WIDTH + ROOF_EAVE_OVERHANG - ROOF_EAVE_SETBACK`; the horizontal limit
is `ROOF_EAVE_DROP_BELOW_WALL_PLATE` below the wall-plate underside.
The finished beam follows whichever cut is reached first. The common
`local_y_limits_from_cuts()` now handles global-X, Y and Z boundaries, so
the complete rafter section reaches all cuts without guessed source lengths.
These rafters share the Rafters visibility container and have their own
measured C22 schedule row, without changing the high/dormer rafter arrays.

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
The high ends remain cut at `LOWER_NADEZDIVKA_X`; the retained interior
ceilings and their independent ranges are unchanged.

`add_west_roof_closure()` closes the high roof from the upper-floor slab up.
The white `Facade finish` occupies X = `LOWER_NADEZDIVKA_X - 0.035` to
`LOWER_NADEZDIVKA_X - 0.03`. Towards decreasing X it is followed by MDF,
a `FACADE_INSULATION_THICKNESS` insulated wall, the OSB/vapour
barrier, an empty `INSTALLATION_SPACE_THICKNESS` service space, and gypsum
plasterboard. `west_closure_wall` is an upper-floor `IfcWall` with insulation
material; `west_roof_closure` contains its four opening-aware `IfcCovering`
finishes. They appear automatically in upper-floor plans. The former roof
visibility container is no longer needed. `west_roof_closure_x_ranges`
records the six adjoining ranges for later insulation annotations.
The finish uses `FACADE_THICKNESS` (5 mm)
and reaches the main-rafter top;
MDF meets the main-roof MDF underside. The interior linings meet the
undersides of their matching sloped layers and stop at the horizontal
ceiling where that is lower. Width follows the street/garden facade faces.

`west_closure_window` is defined before the coverings so its opening is copied
through all four finishes. Tune `WEST_CLOSURE_WINDOW_CENTER_Y`,
`WEST_CLOSURE_WINDOW_WIDTH`, `WEST_CLOSURE_WINDOW_HEIGHT` and
`WEST_CLOSURE_WINDOW_SILL_HEIGHT` beside the helper. Defaults are centred along
Y, 1.0 × 1.0 m, with a 1.5 m sill above the finished upper floor.
This clears the transverse roof and leaves 100 mm below the current ceiling.
The opening must fit within every roof/ceiling profile. The wall core and
finish positions are preserved, including the 1045 mm clear distance to
wall 3 with the current roof-step setting. Installation space remains empty.

`west_roof_closure_layout()` is also the source for `WEST_CLOSURE_INNER_X`.
Both upper service-room floors (P.03/P.04) and their two 100 mm partitions
end at that finished plasterboard face. The existing WC partition retains
`wall_zachod_nahore_y`; the second, `wall_za_umyvadlem`, is 2 m farther along Y.
P.03 ends at the second partition's inner face, while P.04 ends at the
first partition's inner face. Room areas, labels and depth dimensions follow
these shortened floor regions.

Each street/garden purlin consists of two independent pieces. The left and
middle pieces meet at the wall2 centre line and share the top `PURLIN_TOP_Z`.
The middle piece extends to `LOWER_NADEZDIVKA_X - 0.05`. Only the left and middle purlin pieces remain;
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

## 3D roof-frame model (PyNite)

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
drawing.add_text(point=(5, 3), text="Nádrž", color="green")
```

Circle radii and rectangle corners are in metres. Both shapes are unfilled
and support `style="solid"` (default) or `"dashed"`. Text uses printed
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
