# House 2 roof simulator

Run from the project directory with the existing solver environment:

```bash
.venv-roof3d/bin/python roof_frame_3d_house2.py
.venv-roof3d/bin/python -m unittest test_roof_frame_3d_house2 -v
```

Dependencies are the same as the old roof simulator, in
`requirements-roof3d.txt` (PyNiteFEA 3.2.0). This script does not require
Blender or IFC dependencies, execute `house2.py`, or change the IFC/PDFs.
It reuses the old simulator's timber sections, section orientation,
equilibrium check and exact chord-deflection calculation. The House 2
layout and frame connections are separate from the old house model.

Edit the **USER INPUTS** block at the top of `roof_frame_3d_house2.py` to set
loads, timber grades, density, gravity, supports, braces, purlin continuity,
connection stiffness and output options. `Settings` is the single source for
simulation defaults; the command-line run uses those exact values. Optional
CLI flags override only the settings explicitly supplied for that run.
For example, set `continuous_purlins = True` there to enable continuity by
default; `--no-continuous-purlins` switches it off for a comparison.
`house2.py` supplies geometry only. No load inputs are read from `rafter_load.py`.

## Geometry and load path

Global X runs east to west, Y street to garden, and Z upward, matching
`house2.py` without drawing mirroring. Read-only AST evaluation follows
numeric assignments and the restricted rafter-spacing comprehension.
The model follows the current dimensions and positions when rerun:

- Two or three purlins along Y, including their end overhangs. With three,
  `PURLIN_X_POSITIONS` must be ordered east-to-west, with the middle entry
  at `HOUSE_WIDTH/2`. Provide a matching tuple of post Y positions for each.
  The two outside purlins keep `PURLIN_Z` and define the roof slopes. The
  centre (`P2`) is automatically raised so its outer top corners meet those
  reference planes under the ridge. Its posts become taller. The rafter
  axes and roof/snow loading stay unchanged; both rafter halves have ideal
  pinned bearings on the new purlin's outer faces. Rafter chord-deflection
  checks include these extra supports. The command prints every purlin's
  top elevation. This inferred ridge height is simulator geometry; no IFC
  generator changes are made.
  Configure one or more
  posts per purlin using `PURLIN_SUPPORT_Y_POSITIONS`; each purlin has its own
  tuple and the Y positions need not match. By default each purlin is split
  at every internal support: the current post plus Ytong wall give three
  members (`P1.1`–`P1.3`) per purlin. Without a wall bearing, one post gives two. Both bending moments are released at each splice, with
  common axial/shear translations and retained torsional roll compatibility.
  No extra ground restraint is added. `--continuous-purlins` restores the
  continuous members (`Settings(continuous_purlins=True)` in
  Python). Only the simulator is split; the IFC geometry is unchanged.
- Each rafter pair at every `RAFTER_Y_POSITIONS` station. Roof slopes pass
  through the outer top corners of the wall plates and purlins; rafter axes
  use `RAFTER_Z_OFFSET + RAFTER_HEIGHT/2` normal to those planes.
- Two collar boards per rafter pair, with dimensions from `COLLAR_TIE_SIZE`
  and their bottoms at the purlin top. Each pair is represented by one
  bilateral axial spring (`CT01`, `CT02`, …), connected where the tie
  centreline intersects the two rafter axes. Its stiffness is `2 × E × A / L`;
  the two flanking boards' lateral eccentricities are omitted. The joint
  transmits axial force without moment resistance or connection slip.
- X-aligned connecting beams between the **outer** purlins' inner faces, with
  their centrelines at the same Z as the purlin centrelines. Their ends
  attach to the purlin sides through ideal pins at those faces.
  `PURLIN_CONNECTION_Y_POSITIONS` is shared with the IFC: one connector
  at each distinct post Y coordinate, the retained garden connector, and two with a 100 mm clear gap to the inner gable-wall
  faces, controlled by `PURLIN_CONNECTION_WALL_CLEARANCE`. The extra
  connectors do not introduce additional posts or braces.
  With a ridge purlin, the lower connectors have no added joint to the
  ridge posts they cross. The ridge posts run directly to the ceiling.
- One 160 × 160 mm street-side post per purlin, at the midpoint of the clear
  front-wall/Ytong-wall span (Y = 2.67875 m). The two garden posts are removed.
- One `SEDLO` (saddle beam) per post, 1.50 m along Y, with the purlin's
  170 × 250 mm section. Its top touches the purlin bottom. Post tops are
  lowered by the sedlo height; the roof slopes and purlin tops stay fixed.
- The interior Ytong wall supports each outer purlin at Y = 5.2425 m. It does
  not reach a raised optional ridge purlin. Wall reactions are exported as
  `wall_bearing` rows and printed separately from post loads.
- Diagonal braces are absent with sedla. The legacy comparison
  `--no-saddles --braces` restores the optional axial brace model; the IFC
  remains brace-free. `--no-wall-bearings` omits the interior-wall restraint.

Front/back gable bearings, the interior Ytong wall and the elastic timber
post/sedlo assemblies support the purlins. Masonry bearings are anchored
translation pins with unloaded purlin-roll orientation fixed. Post bases
are pinned to the immovable supporting slab. Wall/lintel capacity, wall
settlement and local timber bearing capacity are outside this frame model.

### Sedlo contact model

Purlin and sedlo are separate elastic bending members, each with its own
section stiffness. There is no composite-section stiffness. An ideal
central translation pin attaches the purlin to the sedlo, and another
attaches the sedlo to the post; these retain the existing anchored-joint
assumption. The two beams can have different bending rotations. Away from
that centre, only vertical compression is transferred; axial slip is free.
No wing fastener slip or fastener capacity is assumed verified.

`Settings.saddle_contact_points = 5` selects an odd, evenly spaced grid along
the sedlo. The centre uses the ideal pin; four wing contacts per sedlo are
compression-only axial springs. Their transverse-compression stiffness is

```text
A = min(purlin width, sedlo width) × tributary contact length
k = A / ((purlin height / 2) / E90,mean + (sedlo height / 2) / E90,mean)
```

`E90,mean` comes from the selected shared timber grade. End stations have
half the interior tributary length. Contact opening/reclosing is solved
per load combination. Sedlo unloaded roll/yaw orientations are fixed to
remove free spin; vertical bending rotation remains free. Sedlo self-weight
is included and the shorter posts lose their removed self-weight. Roof and
snow loads are unchanged. Refining from 5 to 9 contact stations changes
current SLS post loads by about 0.05%; a 17-station check differs by about
0.08% from the default. This checks discretisation, not joint capacity.

`--no-saddles` selects direct purlin/post bearing for a comparison;
`--saddle-contact-points 9` refines the bearing grid. Geometry options are
passed to `Layout.from_house(..., saddles=..., wall_bearings=...,
saddle_contact_points=...)`; material/load defaults remain in `Settings`.

The rafters are continuous over their purlin seats. The ridge is a pin
between each pair, with no ridge beam or ground support. Wall plates are
treated as continuously supported, immovable ring-beam/plate assemblies,
rather than additional elastic beams. Rafter seats are vertically attached
and restrained against yaw. By default they slide freely in X (across the
house, allowing inward/outward movement), with zero X restraint force and
no small numerical spring. Y translation is fixed along the wall plates,
preventing a rafter pair from tipping sideways about its purlin joints.
`--horizontal-stiffness rigid` also fixes X;
`--horizontal-stiffness 0.12` adds a 0.12 kN/mm spring in X only.
`free` or `0` explicitly selects the default sliding-X seats. In the Python
`Settings`, zero means free X, `None` means rigid X, and a positive value
means X spring stiffness in kN/mm. Y and vertical support remain fixed in
every mode. The previous free-X/free-Y experiment had an unrestrained
tipping mechanism; its roughly 1.5 m movement was a numerical artefact.
Gable purlin bearings fix translations and restrain purlin roll, while
allowing the bending rotations.

Timber-to-timber interfaces are ideal pins. Massless stiff arms connect
each member axis to the actual contact position, retaining eccentricity.
All three rotations at the pin end of each arm are released. Otherwise
unused rotations of pin nodes are suppressed; the tests verify that these
nodes acquire no artificial foundation force or moment reactions.
Each connector has one X-axis rotation fixed solely to remove its unloaded
rigid spin about the line through its pin ends. Its translations and bending
rotations remain free at that point; tests verify no support force or moment
is introduced by this orientation constraint.
The same convention fixes only the unloaded Z-axis spin at each post top;
post bending remains pinned and the tests check for zero artificial moment.
`--joint-stiffness-factor` sets only the numerical arm stiffness. It is
not a claimed carpentry-joint stiffness; the tests compare factors 1,000
and 10,000 to check convergence of the rigid-arm approximation.

When using the legacy `--no-saddles --braces` comparison, braces are axial
springs with stiffness E×A/L, pin-ended and initially snug. The enabled
default is compression only, with an iterative active-set
solution that permits opening and reclosing separately in every load
combination. Inactive braces are dashed in the pictures. The stiffness
assumes no connection slip; the model does not credit moment resistance
of carpentry joints or claim a verified fastener stiffness.

The model uses prismatic rafter axes to the vertical eave planes. Local
horizontal end cuts, notches and reduced net sections are omitted. Roof
diaphragm action, wind, chimney weight and small roof penetrations are
not modelled. Collar ties have no bending or buckling check, and the assumed
no-slip connections have no fastener-capacity verification. The chimney
clash retained in the IFC is also retained here: the model does not interrupt
that tie or credit the chimney as a support. No purlin spacers are introduced.

## Loads and materials

Defaults are local fields of `Settings` in the simulator's USER INPUTS block:

- `roof_mass`: **150 kg/m² of actual slope**, including the
  sloped internal insulation/OSB/installation space/plasterboard finish.
- `roof_mass_outside_supports_factor`: **1/3**. Roof layers keep the full
  `roof_mass` between the wall-plate and outer-purlin contact points, and use
  one third before the wall plate and above the outer purlin (currently
  **50 kg/m²**). This reduction does not apply to snow or timber self-weight.
  Set the factor to `1` to restore uniform roof-layer weight.
- `snow_load`: **1.5 kN/m² of horizontal projection**, already a roof load,
  not ground snow requiring another shape coefficient.
- Timber self-weight: **450 kg/m³**, with **g = 10 m/s²**.

Actual modelled timber self-weight is added once. Brace and collar weight
is shared between their two ends; neither carries distributed roof/snow
load. Collar weight includes both boards and their short extensions past
the rafter-axis joints to the sloped end cuts, using the mean cut length.
Numerical arms have no self-weight. Wall-plate weight goes directly to
its continuous masonry support and is excluded from roof-frame reactions.

Neighbour-midpoint tributary widths extend to the gable roof edges,
including the irregular central rafter gap. They sum to the full roof
width along Y. Roof dead load is vertical per unit sloping area, and snow
is vertical per horizontal area; the conversion includes the slope cosine.

There are eight combinations:

| Case | Permanent G | East snow | West snow |
| --- | ---: | ---: | ---: |
| SLS_dead | 1.00 | 0 | 0 |
| SLS_symmetric | 1.00 | 1.00 | 1.00 |
| SLS_east | 1.00 | 1.00 | 0.50 |
| SLS_west | 1.00 | 0.50 | 1.00 |
| ULS_dead | 1.35 | 0 | 0 |
| ULS_symmetric | 1.35 | 1.50 | 1.50 |
| ULS_east | 1.35 | 1.50 | 0.75 |
| ULS_west | 1.35 | 0.75 | 1.50 |

This preserves the earlier simulator's symmetric/asymmetric snow pattern
convention, reoriented to this roof. It is not an automatic determination
of all project-specific snow, drift, wind or regulatory combinations.

Material defaults are **C22 for rafters** (`rafter_material`) and **C22 for
other timber** (`beam_material`); these are not inferred from the ungraded IFC
`Wood` material. `--rafter-material` and `--beam-material` select properties
from the shared `materials.py` registry. The second option applies to the
purlins, cross beams, posts, braces and collar ties.

## Outputs

The default prefix is `roof_frame_3d_house2`.

The terminal explains each failed purlin deflection limit, for example:

```text
P1.3, SLS_symmetric: L/500 failed; maximum allowed 3.000 mm, actual 4.000 mm (span 0.000–1.500 m along member)
```

It reports the worst SLS combination for each purlin support span, printing
both limits if L/300 and L/500 fail. The span coordinates are measured from
that member's start. Actual deflection is departure from the straight chord
between the deformed span supports, matching `_deflections.csv` and the plan
colours. The overall failure counts still count individual span/combination
checks for all assessed member types; the CSV retains all combinations.
If all purlin spans pass, the terminal explicitly says so.

A run creates:

- `_purlin_support_loads.csv`: maximum downward load at each purlin post base,
  separately for SLS and ULS, with coordinates and the governing combination.
  Positive values mean downward loading; negative values mean uplift.
  These loads include post self-weight and are delivered to the supporting
  ceiling. The terminal prints the same envelope in kN and equivalent kg
  using the configured gravity. Values come from the solved base reactions,
  so enabled braces and purlin continuity are included. Each post's maximum
  is selected independently; do not sum these envelopes as one load case.
  `_supports.csv` retains every combination with its original +Z-up sign.
- `_sedlo_contacts.csv`: wing contact stiffness, compression force, opening and
  active state for every combination. Central pin forces are not wing pressures.
- `_model.png`: original and amplified deformed frame in 3D.
- `_plan.png`: undeformed top view with timber footprints coloured by the
  worst instantaneous chord check over every SLS combination and support
  span: green if L/300 and L/500 both pass, orange if L/500 fails while
  L/300 passes, red if L/300 fails. Rigid wall plates and members without
  chord checks are grey; axial collar ties have magenta outlines and no
  deflection classification. These colours are independent of the chosen
  force-arrow combination and deformation scale.
  Blue diamonds mark the purlin cuts above posts and the interior bearing wall. Each of the six pieces
  gets its own member ID, check colour and CSV rows. Self-weight is unchanged
  by splitting, and deflection chords still use the actual wall/post supports.
  Blue arrows show horizontal forces delivered to the wall plates for the
  selected plot combination. The signed labels show their outward X
  component: positive outward, negative inward, in kN. Arrow directions
  follow the full horizontal force vector; their lengths are schematic.
  Magenta collar labels show total axial force per board pair: positive
  tension, negative compression, with arrows pointing outward or inward.
  This is the House 2 counterpart of the old `roof_frame_3d_restrained_plan.png`.
- `_members.csv`: section, grade, length, axial-force range, bending and
  shear envelopes for each combination. Braces have compression force
  and active/inactive state. Axial force is positive in compression.
  Collar rows report `pieces=2`, the section of one board, connection span,
  mean physical cut length for self-weight, stiffness and total pair force.
  CSV axial force uses the compression-positive convention, opposite to
  the tension-positive collar labels on the plan.
- `_supports.csv`: support forces and movements for every combination.
  Forces are those delivered **to the wall/slab**, so positive Fz means
  upward force requiring hold-down. These are opposite to solver reactions.
- `_deflections.csv`: exact instantaneous departure from deformed support
  chords, with L/300 and L/500 comparisons. Rafter checks cover wall
  plate–purlin and purlin–ridge; purlin checks cover successive wall/post
  bays; cross-beam checks run between the purlin inner faces. Overhangs are
  excluded from these span checks. Endpoint settlement is excluded from
  chord departure; the member CSV also includes sampled absolute vertical
  movement, including movement of its supporting members.
- `_basis.json`: source, geometry, material choices, settings, versions,
  combinations, tributary widths and force/moment equilibrium residuals.

Both PNGs circle supports with uplift in **any** analysed combination,
regardless of which case is shown deformed. Supports are attached and
cannot lift in this model; the red annotation shows upward force in kN.

The console prints the roof slope, load/material basis, maximum horizontal
rafter-to-wall-plate movement over all combinations, separate SLS/ULS
maxima with X/Y components and the governing seat/case, and the largest
X and Y seat reactions separately. Default seats should report zero X
reaction and zero Y movement; Y reactions are allowed.
It also prints the uplift envelope, instantaneous chord-check failures and
governing L/300 comparison. With explicitly selected rigid seats, horizontal
movement is zero by definition.

All solutions are first-order elastic. Passing the instantaneous chord
comparisons does not establish strength, buckling, final creep deflection,
joint/anchor capacity, bearing compression or slab adequacy.

## Comparisons

```bash
# Restore uniform roof-layer weight for comparison; snow and timber unchanged.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --roof-mass-outside-supports-factor 1 --output /tmp/house2_uniform_layers

# Restore bending continuity over each purlin's configured posts.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --continuous-purlins --output /tmp/house2_continuous

# Select actual purchased timber grades; these are example choices.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --rafter-material C24 --beam-material GL24c --output /tmp/house2_grades

# Explicit assumed wall-plate connection slip stiffness in X, kN/mm; Y fixed.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --horizontal-stiffness 0.12 --output /tmp/house2_slip

# Restore the previous rigid wall-plate-seat comparison.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --horizontal-stiffness rigid --output /tmp/house2_rigid

# Enable the IFC's tesařské pásky as compression-only axial springs.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --no-saddles --braces --output /tmp/house2_with_braces

# Enabled braces capable of both axial tension and compression.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --no-saddles --braces --brace-action both --output /tmp/house2_bilateral_braces

# Compare against posts alone, without gable-wall purlin bearings.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --gable-bearings off --no-saddles --no-wall-bearings --braces --output /tmp/house2_posts_only

# Override the load basis and show the west-heavy ULS case.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --roof-mass 130 --snow 1.7 --plot-combination ULS_west
```

Use distinct output prefixes for comparisons. A positive horizontal
stiffness is a sensitivity input, not an inferred fastener specification.
