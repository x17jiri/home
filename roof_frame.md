# Preliminary 2D roof-frame model

Run `python3 roof_frame.py`. It prints diagnostics and creates
`roof_frame_report.pdf`, separate from `rafter_load_report.pdf`.

This is an elastic **normal roof cross-section**, not an IFC modification or
a complete structural verification. The default runs compare that same actual
section with and without collars and with horizontally free/fixed purlins.
It is **not a dormer model** and does not remove anything from the IFC.

## Inputs and implementation

- `HouseRoofSection.from_house()` reads timber sizes and the `rafters` array
  from `house_ifc.py`, selecting an interior uncut normal main-rafter line with
  the largest tributary width among eligible lines. Its width is half the sum
  of the two neighbouring main-rafter centre distances, not a hard-coded 750 mm.
  It excludes the cut corner, roof-window split lines, paired dormer lines and
  the dormer region. `StrongerRafter` is supported as a data wrapper; arbitrary
  Python calls are never executed. The number of collar boards accounts for
  touching main rafters and their heights follow the appropriate purlin part.
  Pass `rafter_x=...` to select another eligible line explicitly.
- `roof_frame.py:main()` keeps material classes explicit: C24 rafters and C22
  collars. The current selected line is x = 2.55 m, tributary width 0.865 m,
  rafters 80 × 200 mm and two collar boards each 50 × 200 mm. C24 matches the
  current roof-drawing note for this wider strip. Strength grades and support
  stiffnesses cannot be inferred from the IFC geometry.
- `RoofGeometry.from_house()` reads the current roof planes, wall-plate/purlin
  positions, eave overhang and collar heights from `house_ifc.py`. It evaluates
  only arithmetic and tuples using the Python syntax tree, never imports or
  executes the IFC script. Unsupported expressions fail explicitly. It uses
  rafter centre lines; support/joint eccentricities and local seat geometry are
  idealised away. Geometry assumes symmetric normal roof slopes.
- `build_roof_frame()` defines the member continuity, hinges and supports.
- `roof_loads()` converts the vertical gravity loads into distributed loads.
- `ceiling_nodal_loads()` defines the explicitly chosen alternative ceiling
  load path for a no-collar frame.
- `Frame.solve()` assembles the plane-frame stiffness matrix with axial and
  bending deformation and consistent distributed-load vectors.
- `check_roof_frame()` solves the load cases, prints diagnostics and optionally
  appends pages to an open `CalculationReport`.

The reusable check accepts a `RoofGeometry`, both timber material classes and
sections, number of collar boards, spacing, roof/ceiling masses, roof snow load,
and `restrain_purlins`. Geometry and the chosen section heights must describe
the same centre lines. A caller can set `maximum_element_length` to refine the
mesh. All purlin pieces now have the same height, so `lowered=False/True` is
retained for compatibility but no longer changes the collar geometry.

Use `include_collar_ties=False` in `check_roof_frame()` to remove the member
entirely (not just reduce its stiffness). You must also specify
`ceiling_support_without_collars`:

- `"rafter_end_reactions"`: retain the horizontal ceiling mass as equal vertical
  loads at the former collar ends, without a horizontal tie between those ends.
  This represents an unspecified alternative ceiling arrangement with no
  horizontal coupling. It is a **sensitivity assumption, not a designed
  replacement ceiling**, and is the default main-program comparison.
- `"independent_support"`: the horizontal ceiling is supported elsewhere, so
  its load leaves this roof frame. Sloping ceiling finishes remain on rafters.

In both modes the removed collar timber's own weight disappears. No unknown
replacement member's self-weight is invented or added. With collars present,
passing either alternative is rejected to prevent double-counting. The ceiling
footprint and load distribution remain an idealisation of the roof section.

## Supports and connections

- Ridge: the rafters share horizontal and vertical translations, **not
  rotations**. The ridge is a hinge with no external support or ridge beam.
- Wall plates: horizontal and vertical translations fixed; rotation free.
  Horizontal support is an assumption about the planned ring beam/anchors,
  not a check of their capacity.
- Purlins: vertical translations fixed, rotations free. Run both horizontal
  translations free and fixed. These are ideal supports; longitudinal purlin
  bending/flexibility is not included.
- Rafters remain continuous over the purlins and at the collar connections.
- Collar ends share translations with rafters but have their own rotations.
  The collars do **not** receive a direct support from the purlins, even though
  they pass close to them.
- Collar boards share load equally. Their in-plane EA and EI are summed; no
  out-of-plane composite action is assumed or verified.

Here, “restrained purlin” means horizontal movement **across the roof** is
prevented. It is not synonymous with lateral-torsional buckling restraint of
the purlin. Real brackets, purlin bearing details and connections must be able
to provide the chosen boundary condition, including any uplift reactions.

## Loads and results

Masses are shared with `ROOF_LAYERS_KG_M2` in `rafter_load.py`. OSB, SDK and
installation battens/services are moved to the interior ceiling path: horizontal
on the collars and sloping below them, between wall plates. They are not also
counted on the upper roof. Other roof masses are uniform over the full slopes,
including eaves, a simplifying assumption. Timber self-weight is added separately.
No occupancy/storage load on the collar ceiling is included.

All loads are initially **global vertical** forces. With spacing `a`:

- Roof dead load: `qG = roof_mass × g × a` per metre of actual slope.
- Snow: `qS = s × a × cos(angle)` per metre of actual slope, where `s` is per
  horizontal roof area. The frame transformation then obtains axial and
  transverse components; it supplies the second cosine for transverse snow.
- Ceiling load: `ceiling_mass × g × a` per metre of the corresponding ceiling
  member, plus the timber self-weight of that member.

The shared 1.5 kN/m² input is treated here as **roof** snow load, not ground
`sk`. Ground-to-roof shape/exposure/thermal factors are not inferred. Confirm
the intended roof load with the structural designer before using reactions.

Cases are characteristic `G + S` and design `1.35 G + 1.5 S`, each with snow
left/right ratios `1/1`, `1/0.5`, `0.5/1`. These are screening cases, **not a
complete national-annex snow/wind/load-combination generator**.

The report gives axial tension/compression, shear, bending moment, immediate
absolute vertical displacement, and reactions. Positive axial force is tension.
Support reactions act **on the timber**: H positive toward increasing y, V
upwards. Loads on supports have opposite signs; divide by spacing for kN/m.
Collar forces are the total for both boards; divide by their count for the
assumed equal-sharing per-board force. Table extrema are independent and
must not be treated as coincident values for a combined N + M check. Vertical
displacement maxima are sampled within elements; no L/300 comparison is made
because displacement relative to the moving supports must be distinguished.

The leading comparison table shows independent design-force envelopes. A second
table gives signed loads **ON each purlin**, their maximum absolute kN/m values,
and horizontal movements of the rafter support nodes. Positive horizontal load
is toward the garden (+y): inward on the left purlin, outward on the right.
For a horizontally free support, its horizontal reaction is zero **by model
definition**. This does not establish safety or adequate spatial restraint.
The node movement is not a prediction of the purlin's transverse bending.

Detail pages include a schematic/deformed shape and N/M diagrams for the design
case with largest collar axial force, or largest purlin horizontal reaction
when no collars are present. Absence of the collar is shown as a dash in its
force columns, not a zero-force member still drawn in the model.

## What this model does not verify

There is deliberately no overall PASS/FAIL. Separate checks remain for
combined axial force and bending, buckling/klopení, notches and seat cuts,
connections and their slip/eccentricity, ridge detail, creep, wind/uplift,
snow drifts, dormer load paths, purlin flexibility, spatial bracing, anchors,
ring beams and supporting masonry. Have these assumptions and the model
reviewed by a structural engineer before construction.

For methodological context, [FRILO's roof-model documentation](https://www.frilo.eu/wp-content/uploads/EN/Manuals/fl_dach_eng.pdf)
describes roof frames with axial deformations, specified supports, ridge joint
options and collars. The [University of Memphis beam-element notes](https://www.ce.memphis.edu/7117/notes/presentations/chapter_04a.pdf)
give the beam stiffness and consistent distributed-load formulation.

## Verification

`python3 -m unittest test_roof_frame test_rafter_load` checks simple-beam and
sloping-cantilever analytical solutions, a three-span continuous beam against
the independent existing solver, released-end moments, rafter continuity,
global force/moment equilibrium, mirrored snow, mesh convergence, load scaling,
snow projection, ceiling load accounting and PDF generation.

Additional tests cover IFC-input section selection, variable spacing and
stronger rafters, touching-rafter collar counts, unsupported geometry rejection,
actual collar removal, preservation of ceiling loads, the removed timber's
self-weight, no-collar equilibrium/mesh convergence, signed purlin envelopes,
and PDF generation without any collar member.
