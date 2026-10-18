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
In `house_ifc.py`, `UPPER_RING_BEAM_HEIGHT` controls the additional 250 mm band,
whose top is at `UPPER_FLOOR_START + NADEZDIVKA` around the perimeter and along
the internal load-bearing walls, interrupted at the bedroom and storage openings.

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

Run `python3 house_ifc.py roof_xx` for a transverse roof-framing section looking
along +X (parallel to AA). Its `add_roof_elevation()` call selects index 1 in
`rafters` and puts the camera 0.15 m before it. It uses the roof plan's
structural timber selection and upper-floor walls, without roof build-up layers,
furniture or dimensions. The complete timber schedule comes from the same
`timber_schedule_rows` definition as the roof plan. Only the selected rafter
assembly (both roof sides, paired dormer members, collar ties and spacer) and
the purlins cut by the camera, all wall plates and purlin packing blocks receive
its colours/hatches (including projected plates/blocks); other timber stays
white with outlines, and Bonsai still determines visibility. Outputs are
`roof_xx.svg` and `roof_xx.png`; the camera is mirrored with the IFC as usual.

Reuse the same helper in `house_ifc.py` for additional framing sections:

```python
section = add_roof_elevation("roof_yy", rafter_index=5, offset=0.15)
# Add dimensions or notes here, if needed.
section.render("roof_yy.svg", png=True, png_dpi=600)
```

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
including raised house-cut/dormer wall plates and local purlin sections.
Unequal lower spans are shown on both sides (XX/YY); symmetric ones are shown
once (ZZ). Dimension lines are offset 0.45 m outward and exclude eave
overhangs and fabrication allowances.
Each framing section also calls `add_roof_purlin_dimension()` to show horizontal
purlin centre-to-centre spacing below the beams. It uses the local purlin pieces
(side pieces in XX/ZZ, middle pieces in YY), with a default offset of -0.5 m
from their centreline level. Existing rafter dimensions are unchanged.

`roof_elevation_definitions` holds the rafter indices, offsets and marker
letters for `roof_xx`, `roof_yy` and `roof_zz`. The roof plan displays their
X–X, Y–Y and Z–Z cut lines, derived by `roof_elevation_cut()` from those same
settings, even when only the plan is being generated. Section cameras use
that cut-definition helper too, keeping locations and viewing arrows aligned
through export mirroring. Tune the settings in that shared dictionary.

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
single dashed outer boundary continues across each door or window opening for
all insulation materials, using the same dash cadence as the opening;
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
SVG filename when no PDF is requested). The drawing is moved down, not scaled;
the header is included in the paper-fit check. Print the PDF at actual size /
100%, not "fit to page".

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
as height zero: ground-floor surface and foundation slab top; MIAKO bottom,
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
door dimensions, room labels, and stair arrows. Furniture labels remain
automatic in plan drawings but are opt-in for elevations:

```python
stove = ground.furniture("Kamna", ...)
elevation.add_furniture_label(stove)
```

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

## IFC purlin sections

Each street/garden purlin consists of three independent pieces, split at the
inner-wall centre lines. Their tops align at `PURLIN_TOP_Z`.
The middle pieces bear on the unchanged inner-wall level
`PURLIN_WALL_TOP_HEIGHT = UNDER_HOLE + HOLE_HEIGHT + ABOVE_HOLE`.
`VAZNICE_BASE`, `VAZNICE_HEIGHT` and `VAZNICE_DIST` describe the middle piece.
`VAZNICE_SIDE_BASE` and `VAZNICE_SIDE_HEIGHT` describe both side pieces.

`VAZNICE_SIDE_DIST = VAZNICE_DIST + (VAZNICE_BASE - VAZNICE_SIDE_BASE) / 2`
aligns the outer faces (DIST measures to the centreline), preserving both the
main and dormer roof planes. Side pieces sit higher by
`PURLIN_SIDE_PACKING_HEIGHT = VAZNICE_HEIGHT - VAZNICE_SIDE_HEIGHT`.
The outer gable wall tops rise by that amount. At the two inner walls, four
short timber blocks support just the side-piece halves: width
`VAZNICE_SIDE_BASE`, height `PURLIN_SIDE_PACKING_HEIGHT`, length `BWT/2`.
They appear as “Podložky vaznic” in the roof timber schedule. Spacers,
collar ties and under-rafter insulation endpoints follow the local section.
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

`roof_frame_3d.py` models rafters (including the dormer), the six independent
purlin pieces, with paired axial kleštiny by default (`--no-collar-ties` for comparison).
The six purlin sections follow the current middle/side dimensions, common
top level and aligned outer faces from `house_ifc.py`.
Adjacent pieces have separate supported ends, with no Gerber joints or sedla.
Spacers and automatic collar heights follow their local purlin sections.
The five wall-plate outlines represent
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
house-cut seats keep the general value. Reports record both effective values.
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
