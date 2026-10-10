# Preliminary 3D roof frame (PyNite)

This is a force/displacement experiment, **not a complete structural design or
permission to remove kleštiny**. It does not modify/generate the IFC model.

## Running

Use a separate virtual environment: PyNite 3.2 requires NumPy 2, which can
conflict with older packages in an existing IFC/Blender environment.

```bash
python3 -m venv .venv-roof3d
.venv-roof3d/bin/python -m pip install -r requirements-roof3d.txt
.venv-roof3d/bin/python roof_frame_3d.py
.venv-roof3d/bin/python -m unittest test_roof_frame_3d -v
```

The wall plate/ring beam is one immovable rigid support, not a second elastic
beam. Horizontal springs act directly at each rafter connection to this
support **only**, with a separate optional dormer stiffness. Purlin horizontal
guides are rigid, independently of those stiffnesses. **Independent purlin
pieces** are the default, with separate end supports at the inner-wall centres.
Their middle/side dimensions and positions follow the IFC definitions. There
are no sedla or Gerber hinges in the current configuration.
Purlin-to-wall bearings are **vertically attached** by default: upward movement
is prevented, and an upward force delivered to the wall is reported in kN as
the required hold-down demand. Red circles identify these supports in both PNGs.
This is an ideal attachment, not a fastener-capacity check. The same rule applies
to the saddle-to-wall bearing in the legacy sedlo model.
Use `--allow-purlin-lift-off` for the previous compression-only comparison
(`Settings.purlin_bearing_uplift=True`): closed contact uses a numerical rigid-limit
stiffness of 1e9 N/m, not measured wood compression. Open contact retains the
horizontal/roll guides but releases vertical restraint. `--fixed-purlin-bearings`
explicitly selects the default attached model (`purlin_bearing_uplift=False`).
When a rafter crosses two wall plates, only the lower/eave-side plate is a
connected seat. The intermediate plate remains as **vertical compression-only
bearing**: it prevents downward sagging but allows separation, horizontal
sliding and free rotation. No friction or hold-down is assumed there. This is
implemented as a unilateral spring to the immovable structure, using a numerical
rigid-limit stiffness of 1e9 N/m (not a measured connection stiffness). The
contact starts with zero gap and can open/reclose independently in each load case.
Rafters with only one wall-plate seat retain the existing connected-seat model.
The old sedlo and independent-piece arrangements remain available as explicit
comparisons; trial sedlo bolts apply only to the saddle arrangement.
Timber grades are selected independently by `--rafter-material` and
`--beam-material`; both accept C16, C18, C20, C22, C24, GL24c, GL24h, GL28c and GL28h (case-insensitive).
The supported names and properties come from `materials.py`, also used by the
IFC roof schedule and the 2D calculations. The beam grade also applies to
sedla and purlin spacers. Collar ties use their separate `COLLAR_TIE_MATERIAL`
setting (accepting the same four grades). Existing default grades are unchanged.
Actual endpoint pairs are used for all rafters.
The dormer rafters extend to the upper-face plane of the opposite main rafters
and have pinned top connections to the matching street-side members. These
extensions have timber self-weight only, with no roof-layer or snow load.
Roof-layer mass and snow are configured in `Settings` in this script and
printed in every run. Paired 50 × 150 mm collar ties above the purlins
are included by default; use `--no-collar-ties` for comparison.
Options:

```bash
python roof_frame_3d.py --purlin-lateral free
python roof_frame_3d.py --horizontal-stiffness 0.12
python roof_frame_3d.py --horizontal-stiffness 120 --dormer-horizontal-stiffness 0.12
python roof_frame_3d.py --horizontal-stiffness rigid --output roof_frame_3d_rigid
python roof_frame_3d.py --purlin-lateral both
python roof_frame_3d.py --middle-snow --purlin-lateral both
python roof_frame_3d.py --fixed-purlin-bearings --output /tmp/roof_fixed_bearings
python roof_frame_3d.py --middle-snow --allow-purlin-lift-off --output /tmp/roof_lift_off
python roof_frame_3d.py --rafter-material C24 --beam-material C22
python roof_frame_3d.py --rafter-material C18 --beam-material C18
python roof_frame_3d.py --collar-ties
python roof_frame_3d.py --no-collar-ties
python roof_frame_3d.py --no-spacers
python roof_frame_3d.py --purlin-system gerber
python roof_frame_3d.py --purlin-system simple --output /tmp/roof_independent_pieces
python roof_frame_3d.py --purlin-system saddles --output /tmp/roof_with_sedla
python roof_frame_3d.py --purlin-system saddles --saddle-contact-factor 0.1 --output /tmp/roof_soft_contact
python roof_frame_3d.py --purlin-system saddles --saddle-contact-spacing 0.05 --output /tmp/roof_fine_contact
python roof_frame_3d.py --purlin-system saddles --no-saddle-bolts --output /tmp/roof_bearing_only
python roof_frame_3d.py --purlin-system saddles --saddle-bolt-slip-gap 1 --output /tmp/roof_bolt_clearance
python roof_frame_3d.py --purlin-system saddles --saddle-bolt-hold-down ideal --output /tmp/roof_bolt_hold_down
python roof_frame_3d.py --output /tmp/roof3d
python roof_frame_3d.py --rafter-chord-fallback na
python roof_frame_3d.py --plan-force-combination SLS_symmetric
```

### Independent purlins (default)

The current IFC uses three independent pieces per roof side, split at the
inner-wall centres. Each adjacent beam end has its own support/node; no moment
or direct force transfer is imposed between the pieces. `--purlin-system simple`
is now the default, with no sedla or Gerber hinges.

`RoofLayout.from_house()` reads `PURLIN_X_SEGMENTS` and
`PURLIN_SECTION_DIMENSIONS` from `house_ifc.py`. Middle sections use
`VAZNICE_BASE`, `VAZNICE_HEIGHT`, `VAZNICE_DIST`; side sections use their
`VAZNICE_SIDE_*` equivalents. All tops share `PURLIN_TOP_Z`, while the
smaller side sections shift by half the width difference to align outer faces
and preserve both main/dormer roof slopes. `PURLIN_SECTION_BOTTOM_Z` records
their different underside elevations. The IFC outer gables rise under the
side pieces; four timber packing blocks bear on the unchanged inner walls.
These blocks are ideal rigid bearings here; their deformation, bearing capacity
and fastening are not modelled or assessed.
Purlin seat locations, section stiffness/self-weight, spacers and automatic
collar heights follow the local section. Collar boards on opposite sides of a
height boundary are separate axial links if their configured heights differ;
the current common-top arrangement groups paired boards at one height.
Middle deflection checks use the
4.72 m wall-centre span. The basis JSON records all six section dimensions,
endpoints and bearing coordinates under `purlin_sections`.

### Gerber purlins (legacy comparison)

`--purlin-system gerber` remains available for compatible house inputs whose
adjacent piece endpoints coincide. It cannot join the current staggered side
and middle sections: those are intentionally independent.

`RoofLayout.from_house()` reads the actual `PURLIN_X_SEGMENTS` from the IFC
script. The four **wall-centre** bearings stay at their real coordinates and
belong to whichever piece contains them. Changing joint positions automatically
changes the load path; no additional mode switch is necessary:

- **Both joints between the inner walls:** the outer pieces each have two wall
  bearings and cantilever inward to support a suspended middle piece. Its local
  chord runs hinge-to-hinge; the outer chords run wall-to-wall.
- **One joint in each side span:** the middle piece has both inner-wall bearings
  and cantilevers outward to support the side pieces. Its chord runs wall-to-wall
  (4.72 m for this house); each side chord runs between its outer wall and hinge.
- **One side-span joint and one middle-span joint:** the load path is evaluated
  in sequence, with each local chord using its actual wall/hinge support pair.

Example side-span coordinates are `GERBER_JOINT_1 = 2.84` and
`GERBER_JOINT_2 = 9.06` (0.75 m outside the inner-wall centres). Set these in
an older compatible `house_ifc.py`, then run with `--purlin-system gerber`. Two hinges in one side span
are rejected as unstable. A hinge exactly at an inner-wall centre retains the
outer-piece wall bearing, without duplicating the ground restraint.

Four shared hinge nodes have continuous translations. Both bending rotations
are released **only at hinge ends**, using
[PyNite member end releases](https://pynite.readthedocs.io/en/latest/member.html).
The carrying piece stays continuous through its wall bearings. Hinge displacement
comes from that flexible carrying piece, not an invented ground restraint.

In addition, each middle piece gets a **complete wall-to-wall bay check**:
draw a line through the displaced inner-wall bearings and check every portion
of the three pieces lying within that bay. This includes cantilever-tip sag
when the middle piece is suspended; with side-span hinges, it coincides with
the middle piece's ordinary wall-to-wall check. Its L/300 and L/500 limits use
the original inner-wall centre distance, regardless of the hinge spacing.
Both local and complete-bay checks govern the middle piece's PNG colour;
either L/300 failure makes it red. Overhangs outside the bay are excluded from
that check, but remain in the bending/shear and absolute-displacement results.
Cantilever-tip movement is also reported separately.

Torsion continuity at the joints and roll restraint at wall bearings are
retained as explicit idealisations. The hinges transfer axial and shear forces
bilaterally, with no assumed connection slip. **Gerber joint strength, fastener
capacity and uplift/separation are not checked**; this is not a connection design.
These idealisations must be validated against the proposed physical detail.

Blue diamonds identify the four hinges in the plan PNG; white circles remain
actual wall supports. `_gerber_joints.csv` reports their displacements and forces
delivered to the named `carrier` by the named `supported` piece, using the
`*_to_carrier_*` columns. Older `suspended` and `*_to_outer_*` columns remain
compatibility aliases; their names do not describe the new side-span arrangement.
Forces use global axes, for every load case. Global-Y/Z bending moments should
be zero; global-X torsion can be nonzero. The basis JSON records the connection
assumptions and joint locations.
The additional check is printed separately in the terminal and stored as
`wall_chord_*` columns in the member CSV, including the peak member and its
station measured from the left inner wall. Existing `chord_*` columns retain
the local actual-support-pair result. Both are immediate SLS checks with strict `<`;
they do not replace strength, creep, stability or connection checks.

The legacy `--purlin-system saddles` comparison requires uniform purlin
dimensions and compatible positions. `--no-saddles` is retained as an alias
for the default simple independent pieces.

### Middle-only snow (optional sensitivity case)

`--middle-snow` adds `SLS_middle` (1G + 1S) and `ULS_middle` (1.35G + 1.5S).
In these two cases snow is applied on both roof sides, including the dormer,
only between `wall2_x - BWT/2` and `wall3_x - BWT/2`. There is no snow outside
that X strip. Roof layers and timber self-weight remain everywhere, and the
usual symmetric/street/garden cases remain in the report and deflection envelope.
Boundary rafters receive their actual overlapping tributary area, not an
all-or-nothing load based on their centre position.

The boundaries are the **inner-wall centres**, not the shortened middle purlin's
Gerber hinges. They are stored in `RoofLayout.middle_snow_bounds`; the switch is
also available as `Settings.middle_snow=True`. This is an artificial load-pattern
experiment, not a code-prescribed snow distribution or a complete uplift check.
Snow intensity remains `Settings.snow_load`.

With the switch, force arrows default to `ULS_middle` and the deformation PNG
shows `SLS_middle`. Red lift-off circles still include **all** analysed cases.
Use `--plan-force-combination SLS_middle` to show service-case force arrows.
Output names receive `_middle_snow` so the usual reports are not overwritten.

### Purlin spacers (rozpěry vaznic)

Spacers are included by default at each **main** rafter station, using
`PURLIN_SPACER_SIZE` from `house_ifc.py` (currently 80 × 200 mm). Offset
dormer rafters do not add duplicate spacers. Physical length is the clear
distance between the local purlin faces, with tops aligned to the local section.
Their timber grade follows `--beam-material`.

The simple model uses a compression-only axial link, stiffness
`E_parallel × A / physical length`, attached at the two purlin centrelines.
There is no tensile attachment: the link releases if the purlins move apart,
and can re-engage if they move back together. The existing contact active-set
solver handles this (a linear solve cannot handle unilateral links; see
[PyNite analysis documentation](https://pynite.readthedocs.io/en/latest/analysis.html)).
Self-weight is shared equally between the endpoints, included once.
This assumes a snug fit and supported ends; it omits gaps/preload, eccentricity,
end-bearing compliance, friction and transverse bending. **Compression strength,
buckling, end bearing and fastening capacity are not checked.**

Terminal output lists maximum compression for every spacer. `_spacers.csv`
lists compression-positive forces, axial opening (negative when compressed),
active state and stiffness for every combination. `_members.csv` uses the usual
compression-negative sign. Teal outlines and force arrows identify spacers in
the plan PNG; they are not classified as passing a deflection check.
`--no-spacers` omits them and adds `_no_spacers` to filenames for comparison.

For each variant it writes (the default produces `_restrained`; `_free` is
only produced when explicitly requested):

- `roof_frame_3d_free_members.csv`: local axial forces, shear, both bending axes,
  and sampled absolute global vertical displacement, for every analysed timber and
  combination. Also includes each rafter's and purlin's maximum departure from
  its displaced endpoint/bearing chord and SLS L/300 and L/500 screening results
  (see below).
  N is tension-positive/compression-negative (converted from
  PyNite to match the 2D script). `_restrained` is the other support variant.
  Rigid wall-plate outlines are not elastic members and have no member rows.
- `roof_frame_3d_free_dormer_top_joints.csv`: forces delivered to each dormer top
  pin, released-end moments, connected main-rafter name and joint coordinates.
- `roof_frame_3d_free_supports.csv`: signed forces/moments **delivered to** wall
  plate/ring-beam structure and purlins' wall bearings. These are the
  negatives of the solver's support reactions. `outward_kN` is positive toward
  the street for street bearings, toward the garden for garden/dormer bearings.
  Negative means inward. The terminal totals are simultaneous signed sums,
  **not** a design force for the concrete ring beam; inspect individual loads.
  `support_kind` distinguishes `rafter_connection`, `rafter_bearing_only`, `purlin_bearing`,
  `purlin_horizontal_guide` (internal joint, no direct vertical reaction), and
  `saddle_bearing` (vertical reaction delivered to the wall under the saddle).
  `Dx_mm`, `Dy_mm`, `Dz_mm` record movements of the supported timber node:
  at a wall plate these are **rafter connection slip**, not ring-beam movement.
  `horizontal_movement_mm = sqrt(Dx_mm² + Dy_mm²)` is the horizontal resultant.
  The terminal reports the largest rafter-to-wall-plate movement over all
  connections and load combinations, plus a separate SLS maximum, naming the
  rafter, wall plate and governing combination. Purlin bearings are excluded
  from these connection maxima.
  Bearing-only seats are excluded from connection-slip maxima; their movements
  are nevertheless listed in the CSV. `vertical_contact_active` identifies closed
  versus open intermediate seats; positive `Dz_mm` is the separation gap there,
  and small negative values are numerical bearing compression. Their forces come
  from the fixed end of the contact spring, not the unrestrained rafter node.
  The rigid wall plate/ring beam never moves. The two
  `horizontal_*_stiffness_kn_mm` columns contain the spring stiffness, `rigid`
  for an ideal fixed direction, or zero for a free direction. Spring force
  delivered to a support satisfies `F = k × displacement` with these units.
  The terminal also lists the ring-beam horizontal load at every rafter-aligned
  wall-plate connection: signed outward `Hout` in kN for symmetric SLS, the maximum
  outward SLS/ULS values with their combinations, and signed global-X force
  for the governing outward ULS case. These are **direct rafter-connection
  reactions delivered to the rigid structure**, also used by the PNG arrows.
  Rafters without a wall-plate seat are explicitly labelled rather than given
  invented zero reactions. Existing seats on wall-plate overhangs also attach
  to the idealized rigid structure. Per-rafter maxima must not be added as
  simultaneous forces; the totals sum all direct rafter connections.
- `roof_frame_3d_free_basis.json`: inputs, assumptions, load combinations and
  library versions and independent global force/moment equilibrium residuals.
- `roof_frame_3d_free_saddle_contacts.csv`: active/open contact, tributary area,
  estimated stiffness, compression force, pressure and relative gap for each
  contact station/combination. Compression and opening are positive; negative
  gap denotes elastic contact compression. Not a bearing-capacity check.
- `roof_frame_3d_free_saddle_bolts.csv`: per-bolt face slips, shear stiffness,
  X/Y forces delivered to the purlin, resultant shear, face separation and
  ideal hold-down tension, for all combinations. **No bolt capacity check.**
- `roof_frame_3d_free_model.png`: original geometry faint, SLS deformed geometry
  amplified 20 times, and support positions. Displacement is absolute, including
  support/member movement; the image is not the chord-relative check.
- `roof_frame_3d_restrained_plan.png`: undeformed top-view report of every
  physical timber, with member IDs, white wall-bearing markers, a deflection
  legend and signed horizontal-force arrows at every rafter/wall-plate seat.
  `_free_plan.png` is produced when the free variant is requested.

### Collar ties (kleštiny)

Paired pinned axial collar links are enabled by default. Use `--no-collar-ties`
to compare the same roof without them (`--collar-ties` remains an explicit alias).
Edit the `COLLAR_TIE_*` constants near the top of `roof_frame_3d.py`; their
dimensions and placement do **not** depend on IFC collar-tie definitions:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `COLLAR_TIE_WIDTH_M` | 0.05 | Width of one board, m |
| `COLLAR_TIE_HEIGHT_M` | 0.15 | Height of one board, m |
| `COLLAR_TIE_BOARDS_PER_PAIR` | 2 | One or two boards per main rafter pair |
| `COLLAR_TIE_MATERIAL` | C18 | Any grade in `materials.py` |
| `COLLAR_TIE_TOP_HEIGHT_M` | None | Bottom follows purlin tops; a number overrides the board top above the upper-storey floor, m |
| `COLLAR_TIE_MIDDLE_LOWERING_M` | 0.0 | Optional lowering in the middle purlin region, m |
| `COLLAR_TIE_OMIT_TOUCHING_SIDES` | True | Omit boards between touching main rafters |

Programmatic callers can pass `collar_ties=CollarTieParameters(...)` to
`RoofLayout.from_house`. Placement follows main rafter pairs, not the offset
dormer duplicates. Touching main rafters omit only their inward-facing boards;
main/dormer pairs do not cause omissions. If both boards are at the same
elevation they become one equivalent link with their combined axial area.
Boards straddling the middle-height step become two separate links.

Each link has bilateral axial stiffness `EA/L`, transfers tension and compression
between the main rafter centre lines, and has no rotational stiffness or direct
purlin support. The rafters are subdivided at these connection nodes. Board
eccentricity, connection slip, bending, compression buckling and joint capacity
are **not assessed**. Collar self-weight is added once, half at each connection;
roof/snow loading is unchanged. Suspended-ceiling loads remain omitted.

Where an adjacent dormer rafter exists, the **garden-side** collar endpoint is
one shared force joint with the main (usually shortened) rafter and the dormer
rafter. A massless stiff offset arm bridges their staggered centre lines at the
same Y station; its dormer end releases all rotations. Both rafters remain
continuous through the joint, with independent bending rotations. This adds no
ground/purlin restraint, timber weight or roof/snow load. The street-side collar
connection is unchanged: the extended dormer top has its separate pin farther
up the opposite main rafter, not a connection to the street collar endpoint.
These shared joints are shown as black circles in both PNG views and recorded
in the basis JSON under `collar_ties.garden_dormer_joints`. Their fastening
stiffness/capacity is idealised, not a verified bolt design.

The terminal lists each link's governing SLS and ULS axial force, positive for
tension and negative for compression. This is the **total force for the grouped
boards**, not the force per board. The member CSV includes their `pieces` count;
bending/shear and chord-check fields are blank. Collar links have magenta outlines
in the top-view report and are purple in the 3D model image. Magenta is a category
colour, **not a successful deflection or strength check**. Their top-view strips
are diagrammatic equivalents on the rafter axes, not the separate side boards.

Default runs include ties and retain the usual filenames, for example
`roof_frame_3d_restrained_plan.png`. Runs with `--no-collar-ties` use a separate
`_no_collars` prefix so they do not overwrite the default reports.

### Top-view report

Normal runs generate the image automatically alongside the existing 3D image.
`--no-plot` suppresses both. `plot_plan_report(roof, members, path,
force_combo="ULS_symmetric")` can also be called directly with a solved model
and its existing `member_rows` results.

Both PNGs mark uplift locations with hollow **red circles** at the undeformed
support positions. The check matches the terminal warning: upward load delivered
to the support `Fz_kN > 1e-6`, over **all** SLS/ULS combinations, independently
of the image's selected arrow/deformation case. Each support has one circle;
both PNGs label its maximum uplift in kN and governing combination. Red circles
indicate uplift, not the red member fill used for failed deflection checks.
Bearing-only wall-plate seats are also circled when the rafter separates from
the plate, even though the transmitted uplift force is zero. These markers use
the largest positive `Dz_mm > 1e-6` over all load cases and are labelled
`lift-off ... mm` with the governing combination in both PNGs. This is an actual
opening displacement, distinct from an attached seat's hold-down force in kN.
Purlin and legacy saddle wall bearings use force labels in kN by default, because
they are attached and cannot lift. With `--allow-purlin-lift-off`, the same circles
instead mark open wall contacts with `lift-off ... mm`. Open contact transmits zero vertical force;
`Dz_mm` and `vertical_contact_active` in the support CSV identify the opening.
Vertical reactions are recovered at the ground end of the contact spring,
while horizontal forces and moments remain those of the timber's wall guide.

Colours use the **existing immediate chord-relative checks over all SLS load
combinations**, not ULS deflections or absolute settlement:

- green: all SLS cases pass strict `< L/500`;
- orange: all pass `< L/300`, but at least one fails `< L/500`;
- red: at least one fails `< L/300` (equality fails);
- grey: no applicable check. Wall plates are unassessed;
  they do not become green simply because a result is missing. Rafter references
  disabled by `--rafter-chord-fallback na` are also grey.
- magenta outlines: axial collar ties, drawn above the rafters so they remain
  visible without hiding the rafter's deflection colour. The ties are unassessed.

Each collar tie has two magenta axial-force arrows beside it and a signed force
label **between the arrows**. Compression (negative) points inward; tension
(positive) points outward. Force is in kN, total for the boards represented by
that link, using the same `--plan-force-combination` as the wall-plate arrows.
Zero force has a label but no directional arrows. Their lengths show direction,
not magnitude; these are member forces, not the ring-beam bearing reactions.

Arrows default to one simultaneous **ULS symmetric** combination. Use
`--plan-force-combination` to select any of the six existing SLS/ULS cases.
Numbers are the signed outward horizontal component `Hout` in **kN**;
positive pushes outward, negative points inward. Arrow length is constant,
showing direction only, not force magnitude. The along-house Fx component is
not represented by these arrows.

Image forces are the direct rafter-node support reactions, reversed to give
the force delivered **to the rigid wall plate/ring beam**. They are identical
to the terminal/support CSV for the same load combination, point by point.
`wall_plate_connection_rows` returns these values and the rafter-centreline
connection positions. Regression tests also check `F = k × slip` and that
very soft connections have correspondingly tiny horizontal reactions.

Top-view overlaps are diagrammatic: these are projected member-width strips,
not a hidden-surface rendering or cutting drawing. Numerical offset arms are
not drawn as physical timbers. A green member only passes the stated immediate
deflection screening; the image is **not a complete roof safety assessment**.

## Rafter chord-relative displacement

Absolute vertical displacement remains unchanged. In addition, for each rafter
with a wall-plate seat and ridge joint, the script joins the **displaced rafter
centre-line points** at those locations. It finds the maximum **3D perpendicular
distance** of the displaced centre line from this straight line, only between
the two reference points. Eave overhangs are excluded. If a street rafter crosses
two wall plates, the outer/eave-side plate is used.

This removes uniform settlement and straight-line endpoint movement, but still
includes bending and the effect of an intermediate purlin sagging relative to
the wall plate and ridge. It does not independently reset the reference line
at every FE element or purlin. The maximum is found from stationary points of
the first-order displacement polynomials and their FE/load boundaries, not
just a coarse sample grid.

`L` is the original **sloping** length between these reference points. Each
SLS combination is screened with strict `departure < L/300` and `< L/500`.
Equality fails. The terminal lists each rafter's worst SLS departure with its
combination, length, both limits and PASS/FAIL. The CSV also records the
reference kind, named endpoints, their stations, maximum-distance station, and
results for every combination. ULS departures are exported but their limit
statuses are `NOT_CHECKED_ULS`.

Not every rafter reaches both a wall plate and the ridge: in the current inputs,
8 dormer rafters also attach at their extended tops to the opposite main rafters.
Their chord runs from this actual top pin to the higher dormer wall plate,
including purlin sag and movement of the supporting main rafter. The reference
is `main_rafter_to_wall_plate` and remains available with `--rafter-chord-fallback na`.
The 6 shortened garden rafters run from the ridge to a purlin, with a short free
tail. By default (`--rafter-chord-fallback supports`), these use their actual
purlin–ridge pair, labelled explicitly in the exports and terminal. No missing
endpoint is invented. `--rafter-chord-fallback na` can disable these six
alternative references and mark them as `N/A`. Normal wall-plate–ridge
results are unchanged by this option.

These are user-selected **immediate-deflection screening criteria**, not a full
EC5 assessment. Creep/final deflection and strength/stability checks remain
outside this model. A PASS is only a pass of the indicated chord criterion.

## Purlin chord-relative displacement

Outer Gerber purlin pieces use the **displaced centre-line points above their
two wall centres** as chord endpoints. The suspended middle pieces use their
**displaced Gerber hinge endpoints**, labelled `gerber_hinge_to_hinge`.
For legacy simple/saddle layouts all six pieces use wall-centre references;
in the saddle comparison the internal endpoints move through flexible contact.
The
maximum 3D perpendicular distance is calculated by the same method as for
rafters. It includes both vertical and lateral bending, while removing the
straight-line movement of the bearings. `L` is the original bearing-to-bearing
length, not the full timber length: the free end overhangs are excluded from
this check, but remain in the model and absolute-displacement results.

Every purlin has a separate terminal result giving the worst SLS chord departure,
its load combination, L/300 and L/500 limits and strict PASS/FAIL comparisons.
Its maximum sampled absolute vertical displacement and governing combination
are also printed separately; these two maxima need not have the same location
or load combination. The CSV uses the shared `chord_*` columns with
`chord_reference=bearing_to_bearing` or `gerber_hinge_to_hinge`, with the
actual reference node names. Basis
JSON records the reference and assumptions.

These purlin comparisons have the same immediate-deflection screening scope
as the rafter comparisons above. In particular, they do not assess the
horizontal force capacity of walls/anchors or timber stability.

## Geometry and connectivity

`RoofLayout.from_house()` safely reads explicit arithmetic/data definitions in
`house_ifc.py`; it never imports/executes that module. It includes:

- all main rafters (including the shortened street corner and shortened garden
  rafters), `StrongerRafter` widths and the touching offset dormer rafters;
- the two purlins' three **independent** pieces with middle/side sections,
  a common top elevation, aligned outer faces and different bottom elevations;
- the five actual wall-plate pieces: street, cut street, garden left/right and
  dormer. Every matching physical seat is connected, including the cut-street
  plate where it crosses full-length rafters;
- a hinged, translation-only main ridge, **without** a ridge beam;
- paired kleštiny by default; their axial links connect the main rafter pairs,
  not directly the purlins.

Finished member endpoints use centre-line intersections with the IFC cutting
planes (not the stock/cutting-list extra length). The existing horizontal
short-rafter cut follows the local `PURLIN_SECTION_BOTTOM_Z` from the IFC inputs.
`SHORT_GARDEN_RAFTER_CUT_HEIGHT_M` is only a fallback for older input files.
It does not read IFC collar-tie dimensions, and changing the optional trial
ties does not move this cut. Do not infer that this is a buildable end detail.
Dormer upper ends follow the intersection of their centreline with the opposite
main rafter's upper-face plane. A massless stiff offset arm connects each end
to its matching street-side rafter axis, accounting for the staggered X positions
and section-height eccentricity. All three rotations are released at the dormer
end; translations are connected, while the main rafter remains continuous.
The numerical pin's otherwise-unused nodal rotations are fixed only to remove
zero-stiffness rows, not to clamp either timber. The offset arm can apply an
eccentric-force moment to the main rafter, but no couple passes across the pin.
This is an ideal connection assumption, not a fastening-capacity check.
Rotational releases use [PyNite's end-release interface](https://pynite.readthedocs.io/en/latest/member.html#end-releases).
`_dormer_top_joints.csv` records forces to the dormer and moments at its pin;
the basis JSON records the paired members and assumptions. Black circles show
these joints in the plan PNG and the 3D model image. Roof-layer/snow patches
remain unchanged; the new top extension has only its own timber self-weight.

An opening between rafters is retained as loaded roof area, conservatively for
gravity. If an opening intersects a rafter, or `SplitRafter` is used, the reader
fails explicitly: trimmers/disconnected framing need their own load paths.
This first version does not include trimmers, chimney bearing/loads or cut-outs.

## Seat and support assumptions (important)

Rafters and purlins keep their different physical centre-line elevations.
A short, high-stiffness, massless numerical offset arm connects each purlin
seat. It carries three translations, transfers the eccentric force to
the purlin, and releases rotations about global X/Y at the rafter.
It therefore does **not** weld the continuous rafter's roof-plane bending to
the purlin. Rotation about global Z (seat yaw) is retained, representing an
assumed seat/bracket restraint. This is a modelling assumption, not an assessed
connection. The arms have finite stiffness (1000× reference wood stiffness),
with a convergence regression test. They are not additional physical timbers.

The wall plate/ring beam is **one exactly rigid, immovable reference structure**.
Its geometry is retained for drawings, but no elastic wall-plate members or
wall-plate offset arms are added to the FE model. Each rafter centreline is
supported directly where it crosses the matching wall-plate line. This includes
existing overhang seats: their supporting outline is idealized as rigid too.
Vertical translation is fixed, global X/Y translation has independent springs,
global X/Y rotations are free, and the existing global-Z seat-yaw restraint
is retained. Horizontal node motion is attachment slip relative to the stationary
structure, not movement of the structure. No hidden bending or torsional path
through a separate elastic wall plate bypasses those horizontal springs.

Only rafter-to-wall-plate/ring-beam connections use
`Settings.horizontal_stiffness_kn_mm`, in kN/mm **per connection and direction**,
not a total ring-beam stiffness. It affects both global X and Y at those
connections, not the purlin bearings, purlin offset arms, ridge joint or collar
ties. `rigid` fixes the connection translations directly. Very small positive
values approach a sliding connection; the current interface accepts only
positive stiffness or `rigid`, not zero. The model does not design the concrete
ring beam, individual brackets or anchors.

`DORMER_HORIZONTAL_SUPPORT_STIFFNESS_KN_MM` (or
`Settings.dormer_horizontal_stiffness_kn_mm`) overrides **only** connections to
`dormer_wall_plate`. It accepts a positive value in kN/mm, `None` for rigid
connections, or `"inherit"` to use the general stiffness. Inheritance preserves
the previous shared-stiffness behaviour and makes changes to the general
setting apply to the dormer too. The script constant sets the CLI/API default.
The override affects both global X and Y at each dormer seat. Normal-roof,
house-cut and main garden-roof seats retain the general setting. Purlin bearings,
purlin/rafter offset arms and ridge joints are unchanged.

CLI equivalent: `--dormer-horizontal-stiffness 0.12`, `rigid`, or `inherit`.
Terminal and top-view reports show both effective stiffnesses; the basis JSON
also records the effective value for every wall plate. Support CSV stiffnesses
are those actually applied at each node. Softening a connection is a sensitivity
experiment, not proof that a buildable sliding detail has sufficient capacity
or travel; check redistributed forces and displacements elsewhere too.

Each purlin piece has **two** wall bearings at the **wall centre lines**.
The middle span is therefore `wall3_x - wall2_x` (currently 4.72 m), rather than
the clear opening or the distance between half-wall bearing centres. Outer
bearings are at `BWT/2` and `HOUSE_WIDTH - BWT/2`. This is the analysis-span
convention; it does not enlarge the physical bearing area used in other checks.
Adjacent pieces are not spliced together: each has its own nodes, including at
coincident endpoints/bearings on a shared wall. They do not share rotations or
accidentally become a continuous purlin. With saddles, their vertical
translations interact through the common saddle and bearing contact.
Their X translation and roll about X are fixed, and Y translation is fixed
by default (`--purlin-lateral restrained`), with no horizontal bearing springs.
`--purlin-lateral free` deliberately leaves purlin Y free while retaining
rigid X and the independent wall-plate connection springs. Direct wall supports
are vertically attached by default; internal vertical support is through saddles
(or directly attached to the wall with `--no-saddles`).
`--allow-purlin-lift-off` changes wall attachment to compression-only contact. Bending rotations
are free. Thus "laterally free" means free horizontal Y translation, **not**
freedom to roll/twist. `--horizontal-stiffness rigid` (or `None` in Settings)
makes general connections rigid; the dormer follows unless explicitly
overridden. Use `--dormer-horizontal-stiffness rigid` to fix the dormer separately.
Actual rolling restraint, brackets and anchorage need verification.

### Purlin saddles (sedla, legacy comparison only)

`add_purlin_saddles()` asserts equal width and height for all six purlin pieces.
It adds four longitudinal beams, centred at wall2/wall3 on the street and
garden purlin lines. Each has the adjacent purlin's section and grade, and its
top touches the purlin underside. Their length follows `SEDLO_LENGTH` in
`house_ifc.py` (currently 1.5 m); `SADDLE_LENGTH_M` is the fallback for synthetic
layouts. This is now a **simulator-only legacy comparison**: the current IFC
has no sedla and its inner walls reach the purlin underside. Purlin and sedlo
elevations in the comparison stay unchanged. Saddle bending
uses the normal along-grain timber modulus; self-weight is included once.

Saddles are vertically pinned at the wall centre, with free bending rotation.
Distributed **compression-only vertical** springs connect the stacked timbers.
Contact can open and reclose. Internal purlin vertical support is released so
the load cannot bypass these springs. The existing purlin horizontal/roll
restraints are retained; out-of-plane saddle DOFs are restrained but
vertical contacts do not add purlin lateral restraint. Finite wall-bearing
width, wall rotational compliance, friction, preloads and glued/full-composite
action are **not** modelled. Trial bolt shear/hold-down is described below;
`--no-saddle-bolts` retains the original bearing-only experiment. Neither model
is a complete representation or design of the reference connection.

The starting elastic stiffness for tributary contact area `A` is

```
k [N/m] = factor × A / (h_purlin / E90,purlin + h_saddle / E90,saddle)
```

This treats the two nominal full timber depths as compression layers in
series. `TIMBER_E90_MEAN_PA` is 330 MPa for C22 and 370 MPa for C24.
For two 240 mm deep C22 timbers and a 240 × 100 mm contact area it gives
16.5 kN/mm. Each mesh cell has its own area/stiffness; contact areas sum to
the actual saddle footprint, including the two half contributions at a joint.
**This is an estimate, not a calibrated or code-prescribed joint stiffness.**
Stress spreading, actual contact/gaps, moisture, creep and fastening can change
it. [Bearing-stiffness research](https://doi.org/10.1016/j.engstruct.2015.07.032)
supports using geometry and perpendicular-grain properties but does not
validate this simplified formula for our saddle. EN338 property values are
tabulated in the academic chapter
[Timber and wood-based products](https://napier-repository.worktribe.com/OutputFile/2762670).

`SADDLE_CONTACT_STIFFNESS_FACTOR` / `--saddle-contact-factor` is only a
sensitivity multiplier, separate from rafter horizontal support stiffness.
Use softer/stiffer contact variants and a finer `--saddle-contact-spacing`
to assess sensitivity, not to tune a desired result. Realistic calibration
requires a specified joint detail and suitable test/manufacturer data or a
validated bearing model; bolt stiffness needs its own fastening specification.

The pinned PyNite 3.2 two-node compression-only solver deactivates springs but
does not reactivate them after redistribution. `solve_saddle_contact()` uses
its stiffness assembly, solve and reaction recovery with an active-set
update that allows both opening and reclosing. Trial bolt face-slip stiffness
and deadband offsets are added locally; fixed-DOF bolt reactions are recovered
separately. Contact complementarity and
independent global force/moment equilibrium are checked after convergence.
This remains first-order analysis, not a second-order/nonlinear timber model.
Saddles are blue outlines in the plan image; their strength is not assessed.

### Simplified trial bolting

`SADDLE_BOLT_DIAMETER_MM = 12` and `SADDLE_BOLTS_PER_PURLIN_END = 2`
are the only fastening-size inputs. Positions are equally spaced within each
purlin end's overlap: currently 0.25 and 0.50 m from the joint on each side.
There are four bolts per sedlo and sixteen in the roof. These are illustrative
trial dimensions/locations, **not a verified fastening specification**.
Programmatic bearing-only layouts remain possible with `SaddleParameters()`;
use `SaddleParameters(bolts=SaddleBoltParameters())` to enable the trial links.

The approximate EC5 shear slip modulus per bolt and **one shear plane** is

```
Kser [N/mm] = rho_mean^1.5 × diameter_mm / 23
Ku = (2/3) × Kser  # ULS combinations
```

Mean densities from timber grade are C22=410 and C24=420 kg/m³, independently
of the deliberately conservative 450 kg/m³ self-weight setting. Dissimilar
timbers use the geometric mean. A 12 mm bolt joining two C24 timbers gives
4.491 kN/mm in SLS and 2.994 kN/mm in ULS. See
[bolted-connection stiffness research](https://www.sciencedirect.com/science/article/pii/S0950061821022510)
for these EC5 approximations, and the timber-property chapter linked above.

Two directional shear springs act at the **touching faces**, not the neutral
axes. For longitudinal X slip, the relative displacement is
`DX_p - DX_s - h_p/2 × RY_p - h_s/2 × RY_s`; the Y connector similarly
includes roll offsets. Their generalised forces supply the corresponding
face-offset moments, giving partial composite action without rigid bonding.
Rigid-body translation/rotation creates no false connection strain.

`SADDLE_BOLT_SLIP_GAP_MM` / `--saddle-bolt-slip-gap` selects an assumed
relative-slip deadband (default zero = close-fitting trial). A 1 mm trial
means no shear force until relative slip exceeds ±1 mm in that direction.
It is **not literal bolt-hole diameter clearance**, nor an exact circular-hole
model: X/Y deadbands are independent. Engagement and force reversal are solved
separately for every load combination, without load superposition.

Axial clamping is **not** inferred from shear stiffness. Default hold-down
`free` permits contact opening; `--saddle-bolt-hold-down ideal` adds tension-only
links at the bolt stations with a 1000 kN/mm numerical penalty, an approximate
rigid-limit comparison, **not an estimate of actual axial bolt/washer stiffness**.
The hold-down links never replace compression contact. Contact load minus
hold-down tension is used when reporting the purlin's net vertical bearing load.

Saddle wall supports retain their existing DX/DY/DZ/RX/RZ restraints, with RY
free for vertical-plane bending. RZ was only rigid-body stabilisation in the
bearing-only model; with lateral bolt shear it is an **assumed lateral
orientation restraint**, not a verified wall/anchorage detail.
Consequently bolts can transfer **Y load into the saddle wall support even
with `--purlin-lateral free`**: that option now frees only the direct purlin Y
guides, not the bolted load path. Use `--no-saddle-bolts` for the previous
unbolted comparison. Bolt dots and the gap/hold-down assumptions appear in PNGs;
CSV/JSON and terminal output record the model and bolt-force results.

No bolt yielding/capacity, washer bearing, withdrawal, group effects, minimum
spacing/end-distance, friction, preload, fastener creep or local timber failure
is checked. The purpose is sensitivity of roof forces/deflections to a plausible
elastic connection, not approval to construct the trial fastening.

### Historical calibration for the purlin/rafter deflection experiment

The values below were obtained with the **previous elastic wall-plate model**.
They are historical comparison data, not results or a calibration for the
current rigid-structure/direct-connection model. The script preserves the user's
chosen stiffness rather than automatically retuning it after this change.

The previous model used a common default stiffness of
`HORIZONTAL_SUPPORT_STIFFNESS_KN_MM = 0.12` kN/mm (120,000 N/m).
It was tuned against the **SLS symmetric total
vertical load delivered by `street_purlin_middle` to its two wall bearings**,
including its self-weight. With the then-current C22 240×320 mm middle purlin,
4.72 m bearing span, 135 kg/m² roof layers and 1.5 kN/m² roof snow, it gave
**39.064 kN**, close to the requested approximately 39 kN standalone reference.
It does not fit every purlin or snow pattern, nor reproduce a uniform load.
It is not automatically retuned when geometry or loads change.

For the same geometry/loads in `SLS_symmetric`:

| Quantity | Rigid horizontal supports | Shared 0.12 kN/mm springs |
| --- | ---: | ---: |
| Street middle purlin vertical load | 25.789 kN | 39.064 kN |
| Street middle purlin absolute vertical sag (sampled) | 5.399 mm | 8.327 mm |
| Street middle purlin 3D chord departure | 6.094 mm | 8.346 mm |
| `rafter_08_street` absolute vertical movement (sampled) | 6.741 mm | 10.229 mm |
| `rafter_08_street` wall-plate–ridge chord departure | 6.989 mm | 3.174 mm |
| Maximum absolute Y support movement | 0 mm | 6.538 mm |

The rafter's absolute movement increases while its departure from the displaced
endpoint chord decreases: flexible restraints change endpoint movements and
the whole deformation shape. The chord measure still includes intermediate
purlin sag; it must not be mistaken for the absolute movement or an isolated
rafter bending check. Compare both outputs when varying purlin dimensions.

**Calibration is not verification.** Matching a vertical force does not prove
that the real brackets, anchors, walls and ring beams have this stiffness or
capacity. This model is for exploring coupled roof deflections, not reducing
member sizes or approving the anchorage. Strength/stability and the actual
load path still need separate verification.

The roof is an effective elastic beam frame, not orthotropic timber solids.
The current CLI defaults are C18 rafters and collar ties, and GL24c purlins,
spacers and wall plates; all remain configurable. `materials.py` supplies the
E/G/E90 properties and mean densities for C16, C18, C20, C22, C24, GL24c, GL24h, GL28c and GL28h,
using EN 338 / EN 14080 ([published tables](https://www.swedishwood.com/siteassets/5-publikationer/pdfer/sw-design-of-timber-structures-vol2-2022.pdf#page=10)).
E90 and mean density are used for optional saddle contact/bolt-slip calculations.
The separately configured self-weight density remains unchanged. For example, select glulam purlins with
`--beam-material GL24c`. Section height is
explicitly oriented toward global Z (normal to each rafter's slope), despite
PyNite's default global-Y-up convention. Member torsional stiffness is included;
PyNite's beam formulation omits transverse shear deformation. Timber lateral
stability and diaphragm/bracing behaviour are not verified by this model.

GL24c properties are from EN 14080:2013, Table 4; an accessible reference is
[Swedish Wood's glulam strength-class table](https://www.traguiden.se/konstruktion/limtrakonstruktioner/projektering-av-limtrakonstruktioner/limtra-som-konstruktionsmaterial1/tillverkning-av-limtra/hallfasthetsklasser/).

## Loads and results

The current load inputs are `Settings.roof_mass` and `Settings.snow_load` in
this script. The shared snow import and CLI load overrides in `main()` are
currently commented out, so edit these script parameters rather than relying
on `--snow` or `--roof-mass`. Roof-layer mass is an aggregate roof-slope mass, not
an automatic layer calculation. **The flat ceiling and its supporting structure
are not loaded or designed here.** Do not include its OSB/SDK/services mass a
second time. Comparisons against the standalone script must use a matched load
basis. Timber self-weight is added once to actual members, never to numerical
seat arms. The rigid wall plate/ring beam's own weight is not a roof-frame load:
it goes directly to the supporting structure and does not load the rafters.
Defaults are 450 kg/m³ and g=10 m/s².

Roof surface patches distribute loads through neighbour midpoint tributary
widths, bounded at roof edges and transitions: cut/normal street; garden upper;
garden normal lower sides; dormer lower. The lower dormer surface loads dormer
rafters, not the shortened upper rafters. Roof-layer load is kg/m² actual slope;
snow is vertical kN/m² horizontal **roof** area. Exactly one cosine converts
snow to true-member-length load; the frame transformations resolve transverse
and axial components. Patch area assignment and global equilibrium are checked.

SLS uses 1G + 1S and ULS uses 1.35G + 1.5S, for snow multipliers street/garden
1/1, 1/0.5 and 0.5/1. These are **screening patterns, not a complete Eurocode
snow generator**. The snow input is applied roof snow, not ground sk: shape,
exposure, thermal factors and dormer drift must be determined separately.
Wind, creep, occupancy/storage loads and snow redistribution are absent.

This first version uses first-order elastic analysis only; second-order
behaviour requires a separately validated extension. It does not perform
EC5 strength/combined-stress/buckling checks, notch or
connection design, or concrete/anchor checks. Seats/bearings are bilateral:
uplift requires anchorage and cannot be carried by gravity contact alone.
The new saddle contacts are compression-only, unlike the existing bilateral
rafter seats/direct outer bearings. Any predicted support uplift is flagged.
Support reactions depend on these assumptions;
a structural engineer must validate them before relying on the forces.

## Code locations

- `HouseInputs`, `RoofLayout.from_house`: safe IFC-input geometry reader.
- `COLLAR_TIE_*`, `CollarTieParameters`, `add_collar_ties`: independent collar
  dimensions, local-section placement and board grouping; `PURLIN_SECTION_BOTTOM_Z`
  controls the shortened-rafter cut independently.
- `Timber.properties`, `orient_section`: section stiffness and orientation.
- `SADDLE_*`, `SaddleParameters`, `add_purlin_saddles`,
  `saddle_contact_stiffness`, `solve_saddle_contact`: saddle geometry and elastic
  bearing-contact estimate/active-set solve; `saddle_contact_rows`: exports.
- `SaddleBoltParameters`, `saddle_bolt_stiffness`, `bolt_face_terms`,
  `bolt_shear_assembly`, `saddle_bolt_rows`: trial bolt slip, face offsets,
  independent hold-down assumption and per-bolt exports.
- `build_roof_model`: connectivity, seat releases, supports, tributary loads
  and load combinations.
- `RoofLayout.purlin_system`, `RoofLayout.gerber_joints`, `gerber_joint_rows`:
  independent/Gerber/legacy layout choice, bending-hinge connectivity and hinge exports.
- `solve_roof_model`, `check_equilibrium`: solver and independent balance check.
- `rafter_chord`, `purlin_chord`, `maximum_chord_departure`, `chord_result_columns`: physical
  endpoint selection, maximum chord-relative displacement and SLS limit checks.
- `member_rows`, `support_rows`, `print_summary`, `plot_model`: results/export.
- `main`: CLI, optional ties, separate output prefixes and the two support variants.
