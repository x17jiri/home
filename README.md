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

The optional `"axis"` marker places the reference line at a boundary between
layers. In this example, brick extends 120 mm to the left of the axis and rock
wool extends 100 mm to the right. Without a marker, the wall construction is
centred on its axis. The direct `thickness=...` form also creates a centred
wall. `connect_wall()` creates an
`IfcRelConnectsPathElements` relationship and regenerates both wall bodies. By
default it joins their nearest ends; pass `is_atpath=True` to terminate the end
of the first wall along the path of the second wall at a T-junction.

## Library objects and plan symbols

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
when the source library uses a corner or wall face as its origin.

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

The camera is centred at `(x, y, z)`. Its square view covers `2 * radius`
metres in both X and Y, so the example cuts the model at 1.6 m and covers a
10 m by 10 m area. `png=True` additionally creates `house.png` through
Inkscape.

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
