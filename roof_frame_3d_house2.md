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

## Geometry and load path

Global X runs east to west, Y street to garden, and Z upward, matching
`house2.py` without drawing mirroring. Read-only AST evaluation follows
numeric assignments and the restricted rafter-spacing comprehension.
The model follows the current dimensions and positions when rerun:

- The two continuous purlins along Y, including their end overhangs.
- Each rafter pair at every `RAFTER_Y_POSITIONS` station. Roof slopes pass
  through the outer top corners of the wall plates and purlins; rafter axes
  use `RAFTER_Z_OFFSET + RAFTER_HEIGHT/2` normal to those planes.
- Two X-aligned connecting beams immediately below the purlins.
- Four posts from the ceiling top to the connecting-beam undersides.
- Twelve 45-degree braces: two under the purlin and one under the
  connecting beam at each post. The section and anchor drop follow
  `PURLIN_BRACE_SIZE` and `PURLIN_BRACE_DROP`.

Both gable walls and the timber posts support the purlins. The gable
bearings are at the front/back wall centrelines. There is no direct rigid
ground support at the four purlin/post locations: load passes through the
cross beams, posts and braces. Post bases are pinned against an immovable
supporting slab. The slab, gable walls, ring beams and their capacities
are outside this model.

The rafters are continuous over their purlin seats. The ridge is a pin
between each pair, with no ridge beam or ground support. Wall plates are
treated as continuously supported, immovable ring-beam/plate assemblies,
rather than additional elastic beams. Rafter seats are vertically attached
and restrained against yaw; horizontal translation is fixed by default.
Gable purlin bearings fix translations and restrain purlin roll, while
allowing the bending rotations.

Timber-to-timber interfaces are ideal pins. Massless stiff arms connect
each member axis to the actual contact position, retaining eccentricity.
All three rotations at the pin end of each arm are released. Otherwise
unused rotations of pin nodes are suppressed; the tests verify that these
nodes acquire no artificial foundation force or moment reactions.
`--joint-stiffness-factor` sets only the numerical arm stiffness. It is
not a claimed carpentry-joint stiffness; the tests compare factors 1,000
and 10,000 to check convergence of the rigid-arm approximation.

Braces are axial springs with stiffness E×A/L, pin-ended and initially
snug. By default they carry compression only, with an iterative active-set
solution that permits opening and reclosing separately in every load
combination. Inactive braces are dashed in the pictures. The stiffness
assumes no connection slip; the model does not credit moment resistance
of carpentry joints or claim a verified fastener stiffness.

The model uses prismatic rafter axes to the vertical eave planes. Local
horizontal end cuts, notches and reduced net sections are omitted. Roof
diaphragm action, wind, chimney weight and small roof penetrations are
not modelled. There are no collar ties or purlin spacers in House 2, so
none are introduced into this simulator.

## Loads and materials

CLI defaults read `ROOF_LAYERS_KG_M2` and `SNOW_LOAD_KN_M2` from
`rafter_load.py` as data. Currently these are:

- Full sloped build-up: **130 kg/m² of actual slope**, including the
  sloped internal insulation/OSB/installation space/plasterboard finish.
- Roof snow: **1.7 kN/m² of horizontal projection**, already a roof load,
  not ground snow requiring another shape coefficient.
- Timber self-weight: **450 kg/m³**, with **g = 10 m/s²**.

Actual modelled timber self-weight is added once. Brace weight is shared
between its two ends; braces do not carry distributed roof/snow load.
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

Both material options default to **C18**, as a trial selection consistent
with the earlier simulator; this is not inferred from the ungraded IFC
`Wood` material. `--rafter-material` and `--beam-material` select properties
from the shared `materials.py` registry. The second option applies to the
purlins, cross beams, posts and braces.

## Outputs

The default prefix is `roof_frame_3d_house2`. A run creates:

- `_model.png`: original and amplified deformed frame in 3D.
- `_plan.png`: top view, member identifiers and horizontal forces delivered
  to the wall plates for the selected plot combination. Arrow direction
  shows the force direction; arrow lengths are schematic, with kN labels.
- `_members.csv`: section, grade, length, axial-force range, bending and
  shear envelopes for each combination. Braces have compression force
  and active/inactive state. Axial force is positive in compression.
- `_supports.csv`: support forces and movements for every combination.
  Forces are those delivered **to the wall/slab**, so positive Fz means
  upward force requiring hold-down. These are opposite to solver reactions.
- `_deflections.csv`: exact instantaneous departure from deformed support
  chords, with L/300 and L/500 comparisons. Rafter checks cover wall
  plate–purlin and purlin–ridge; purlin checks cover successive wall/post
  bays; cross-beam checks run between the post centrelines. Overhangs are
  excluded from these span checks. Endpoint settlement is excluded from
  chord departure; the member CSV also includes sampled absolute vertical
  movement, including movement of its supporting members.
- `_basis.json`: source, geometry, material choices, settings, versions,
  combinations, tributary widths and force/moment equilibrium residuals.

Both PNGs circle supports with uplift in **any** analysed combination,
regardless of which case is shown deformed. Supports are attached and
cannot lift in this model; the red annotation shows upward force in kN.

The console prints the roof slope, load/material basis, maximum horizontal
rafter-to-wall-plate movement, uplift envelope, instantaneous chord-check
failures and the governing L/300 comparison. With rigid wall-plate seats,
their horizontal movement is zero by definition.

All solutions are first-order elastic. Passing the instantaneous chord
comparisons does not establish strength, buckling, final creep deflection,
joint/anchor capacity, bearing compression or slab adequacy.

## Comparisons

```bash
# Select actual purchased timber grades; these are example choices.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --rafter-material C24 --beam-material GL24c --output /tmp/house2_grades

# Explicit assumed wall-plate connection slip stiffness, kN/mm per X/Y DOF.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --horizontal-stiffness 0.12 --output /tmp/house2_slip

# Attached braces capable of both axial tension and compression.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --brace-action both --output /tmp/house2_bilateral_braces

# Compare against posts alone, without gable-wall purlin bearings.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --gable-bearings off --output /tmp/house2_posts_only

# Override the load basis and show the west-heavy ULS case.
.venv-roof3d/bin/python roof_frame_3d_house2.py \
    --roof-mass 130 --snow 1.7 --plot-combination ULS_west
```

Use distinct output prefixes for comparisons. A positive horizontal
stiffness is a sensitivity input, not an inferred fastener specification.
