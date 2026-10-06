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

The default uses equal horizontal support springs for wall plates and purlin
bearings, with C22 for all timber and actual endpoint pairs for all rafters.
Roof-layer mass is 135 kg/m² and the shared roof snow input is 1.5 kN/m².
Options:

```bash
python roof_frame_3d.py --purlin-lateral free
python roof_frame_3d.py --horizontal-stiffness 0.12
python roof_frame_3d.py --horizontal-stiffness rigid --output roof_frame_3d_rigid
python roof_frame_3d.py --purlin-lateral both
python roof_frame_3d.py --rafter-material C24 --beam-material C22
python roof_frame_3d.py --snow 1.5 --roof-mass 85 --no-plot
python roof_frame_3d.py --output /tmp/roof3d
python roof_frame_3d.py --rafter-chord-fallback na
```

For each variant it writes (the default produces `_restrained`; `_free` is
only produced when explicitly requested):

- `roof_frame_3d_free_members.csv`: local axial forces, shear, both bending axes,
  and sampled absolute global vertical displacement, for every timber and
  combination. Also includes each rafter's and purlin's maximum departure from
  its displaced endpoint/bearing chord and SLS L/300 and L/500 screening results
  (see below).
  N is tension-positive/compression-negative (converted from
  PyNite to match the 2D script). `_restrained` is the other support variant.
- `roof_frame_3d_free_supports.csv`: signed forces/moments **delivered to** wall
  plates' underlying ring beams and purlins' wall bearings. These are the
  negatives of the solver's support reactions. `outward_kN` is positive toward
  the street for street bearings, toward the garden for garden/dormer bearings.
  Negative means inward. The terminal totals are simultaneous signed sums,
  **not** a design force for the concrete ring beam; inspect individual loads.
  `Dx_mm`, `Dy_mm`, `Dz_mm` record support movements. The two
  `horizontal_*_stiffness_kn_mm` columns contain the spring stiffness, `rigid`
  for an ideal fixed direction, or zero for a free direction. Spring force
  delivered to a support satisfies `F = k × displacement` with these units.
  The terminal also lists the ring-beam horizontal load at every rafter-aligned
  wall-plate bearing: signed outward `Hout` in kN for symmetric SLS, the maximum
  outward SLS/ULS values with their combinations, and signed global-X force
  for the governing outward ULS case. These are **support reactions after
  redistribution through the wall plate**, not isolated rafter/bracket forces.
  Rafters without a wall-plate seat, and seats beyond the supporting wall, are
  explicitly labelled rather than given invented zero reactions. Per-rafter
  maxima must not be added as simultaneous forces; wall-end bearings without
  a rafter are retained in the existing totals and support CSV.
- `roof_frame_3d_free_basis.json`: inputs, assumptions, load combinations and
  library versions and independent global force/moment equilibrium residuals.
- `roof_frame_3d_free_model.png`: original geometry faint, SLS deformed geometry
  amplified 20 times, and support positions. Displacement is absolute, including
  support/member movement; the image is not the chord-relative check.

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
8 dormer rafters connect a purlin to the higher dormer wall plate, and 6 shortened
garden rafters run from the ridge to a purlin, with a short free tail. By default
(`--rafter-chord-fallback supports`), these 14 use their actual wall-plate–purlin
or purlin–ridge pair, labelled explicitly in the exports and terminal. No
missing endpoint is invented. `--rafter-chord-fallback na` can disable these
alternative references and mark the 14 as `N/A`. Normal wall-plate–ridge
results are unchanged by this option.

These are user-selected **immediate-deflection screening criteria**, not a full
EC5 assessment. Creep/final deflection and strength/stability checks remain
outside this model. A PASS is only a pass of the indicated chord criterion.

## Purlin chord-relative displacement

Each of the six independent purlin pieces uses the **displaced centre-line
points at its two actual wall-bearing nodes** as its chord endpoints. The
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
`chord_reference=bearing_to_bearing` and the actual bearing node names. Basis
JSON records the reference and assumptions.

These purlin comparisons have the same immediate-deflection screening scope
as the rafter comparisons above. In particular, they do not assess the
horizontal force capacity of walls/anchors or timber stability.

## Geometry and connectivity

`RoofLayout.from_house()` safely reads explicit arithmetic/data definitions in
`house_ifc.py`; it never imports/executes that module. It includes:

- all main rafters (including the shortened street corner and shortened garden
  rafters), `StrongerRafter` widths and the touching offset dormer rafters;
- the two purlins' three **independent** pieces with their actual sections,
  downward extension of the middle pieces, and common top elevation;
- the five actual wall-plate pieces: street, cut street, garden left/right and
  dormer. Every matching physical seat is connected, including the cut-street
  plate where it crosses full-length rafters;
- a hinged, translation-only main ridge, **without** a ridge beam;
- no kleštiny or other transverse connection between the purlins.

Finished member endpoints use centre-line intersections with the IFC cutting
planes (not the stock/cutting-list extra length). The existing horizontal
short-rafter cut remains at its current IFC height, even though kleštiny are
absent in this experiment. Do not infer that this is a buildable end detail.
Dormer upper ends follow the current source local Y=-0.5 position.

An opening between rafters is retained as loaded roof area, conservatively for
gravity. If an opening intersects a rafter, or `SplitRafter` is used, the reader
fails explicitly: trimmers/disconnected framing need their own load paths.
This first version does not include trimmers, chimney bearing/loads or cut-outs.

## Seat and support assumptions (important)

Rafters and longitudinal beams keep their different physical centre-line
elevations. A short, high-stiffness, massless numerical offset arm connects
each seat. It carries three translations, transfers the eccentric force to
the longitudinal beam, and releases rotations about global X/Y at the rafter.
It therefore does **not** weld the continuous rafter's roof-plane bending to
the purlin. Rotation about global Z (seat yaw) is retained, representing an
assumed seat/bracket restraint. This is a modelling assumption, not an assessed
connection. The arms have finite stiffness (1000× reference wood stiffness),
with a convergence regression test. They are not additional physical timbers.

Wall plates have rigid vertical supports and independent horizontal X/Y springs
at the existing analysis nodes within the supporting wall extent; no support
is added beyond the wall, on their overhangs. Every spring uses the same
`Settings.horizontal_stiffness_kn_mm` parameter. Wall-plate roll about X remains
restrained. The high-stiffness rafter seat arms themselves are unchanged: the
bearing springs represent the combined flexibility of the attachment and its
supporting structure, rather than literal brackets in the IFC.

The spring locations are **analysis points, not actual anchor spacing**. They
include rafter-seat locations and wall-extent endpoints. Consequently, the
parameter is per support node/direction, not a total ring-beam stiffness; adding
support nodes would add stiffness. These independent ground springs do not
model the coupling between adjacent anchors through a real ring beam.

Each purlin piece has **two** wall bearings at the **wall centre lines**.
The middle span is therefore `wall3_x - wall2_x` (currently 4.72 m), rather than
the clear opening or the distance between half-wall bearing centres. Outer
bearings are at `BWT/2` and `HOUSE_WIDTH - BWT/2`. This is the analysis-span
convention; it does not enlarge the physical bearing area used in other checks.
Adjacent pieces are not spliced together: each has its own nodes, including at
coincident endpoints/bearings on a shared wall. They do not share translations
or rotations and cannot accidentally become a continuous purlin when their
sections have the same height.
Their Z translation and roll about X are fixed, X has the shared spring, and
Y has the shared spring by default (`--purlin-lateral restrained`).
`--purlin-lateral free` deliberately leaves purlin Y free while retaining
the X springs and both directions of the wall-plate springs. Bending rotations
are free. Thus "laterally free" means free horizontal Y translation, **not**
freedom to roll/twist. `--horizontal-stiffness rigid` (or `None` in Settings)
restores the previous ideal fixed horizontal directions for comparison.
Actual rolling restraint, brackets and anchorage need verification.

### Calibration for the purlin/rafter deflection experiment

`HORIZONTAL_SUPPORT_STIFFNESS_KN_MM = 0.12` in `roof_frame_3d.py` is the single
default stiffness (120,000 N/m). It was tuned against the **SLS symmetric total
vertical load delivered by `street_purlin_middle` to its two wall bearings**,
including its self-weight. With the current IFC C22 240×320 mm middle purlin,
4.72 m bearing span, 135 kg/m² roof layers and 1.5 kN/m² roof snow, it gives
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
C22 is the default for rafters, purlins and wall plates; C24 remains an explicit
CLI override. E/G are 10 GPa/0.63 GPa for C22 and 11 GPa/0.69 GPa for C24. Section height is
explicitly oriented toward global Z (normal to each rafter's slope), despite
PyNite's default global-Y-up convention. Member torsional stiffness is included;
PyNite's beam formulation omits transverse shear deformation. Timber lateral
stability and diaphragm/bracing behaviour are not verified by this model.

## Loads and results

Snow defaults to `SNOW_LOAD_KN_M2` from `rafter_load.py`. Roof-layer mass defaults
to the explicit `Settings.roof_mass = 135` kg/m², matching the current experiment;
it is no longer overwritten by the old shared-layer sum of 85 kg/m² in the CLI.
`--roof-mass` can override it. This input is an aggregate roof-slope mass, not
an automatic layer calculation. **The flat ceiling and its supporting structure
are not loaded or designed here.** Do not include its OSB/SDK/services mass a
second time. Comparisons against the standalone script must use a matched load
basis. Timber self-weight is added once to actual members, never to numerical
seat arms. Defaults are 450 kg/m³ and g=10 m/s².

Roof surface patches distribute loads through neighbour midpoint tributary
widths, bounded at roof edges and transitions: cut/normal street; garden upper;
garden normal lower sides; dormer lower. The lower dormer surface loads dormer
rafters, not the shortened upper rafters. Roof-layer load is kg/m² actual slope;
snow is vertical kN/m² horizontal **roof** area. Exactly one cosine converts
snow to true-member-length load; the frame transformations resolve transverse
and axial components. Patch area assignment and global equilibrium are checked.

SLS uses 1G + 1S and ULS uses 1.35G + 1.5S, for snow multipliers street/garden
1/1, 1/0.5 and 0.5/1. These are **screening patterns, not a complete Eurocode
snow generator**. The 1.5 input is applied roof snow, not ground sk: shape,
exposure, thermal factors and dormer drift must be determined separately.
Wind, creep, occupancy/storage loads and snow redistribution are absent.

This first version uses first-order elastic analysis only; second-order
behaviour requires a separately validated extension. It does not perform
EC5 strength/combined-stress/buckling checks, notch or
connection design, or concrete/anchor checks. Seats/bearings are bilateral:
uplift requires anchorage and cannot be carried by gravity contact alone.
Any predicted uplift is flagged. Support reactions depend on these assumptions;
a structural engineer must validate them before relying on the forces.

## Code locations

- `HouseInputs`, `RoofLayout.from_house`: safe IFC-input geometry reader.
- `Timber.properties`, `orient_section`: section stiffness and orientation.
- `build_roof_model`: connectivity, seat releases, supports, tributary loads
  and load combinations.
- `solve_roof_model`, `check_equilibrium`: solver and independent balance check.
- `rafter_chord`, `purlin_chord`, `maximum_chord_departure`, `chord_result_columns`: physical
  endpoint selection, maximum chord-relative displacement and SLS limit checks.
- `member_rows`, `support_rows`, `print_summary`, `plot_model`: results/export.
- `main`: CLI, shared load defaults and the two support variants.
