# Preliminary 2D roof-frame model

Run `python3 roof_frame.py`. It prints diagnostics and creates
`roof_frame_report.pdf`, separate from `rafter_load_report.pdf`.

This is an elastic **normal roof cross-section**, not an IFC modification or
a complete structural verification. The lowered-collar variant is a sensitivity
test of that same normal section, **not a dormer model**.

## Inputs and implementation

- `roof_frame.py:main()` contains the member dimensions, material classes and
  rafter spacing. Defaults: C22 rafters 80 × 200 mm at 750 mm; two C22 collar
  boards, each 50 × 200 mm. Wider spacings/materials need their own runs.
- `RoofGeometry.from_house()` reads the current roof planes, wall-plate/purlin
  positions, eave overhang and collar heights from `house_ifc.py`. It evaluates
  only arithmetic and tuples using the Python syntax tree, never imports or
  executes the IFC script. Unsupported expressions fail explicitly. It uses
  rafter centre lines; support/joint eccentricities and local seat geometry are
  idealised away. Geometry assumes symmetric normal roof slopes.
- `build_roof_frame()` defines the member continuity, hinges and supports.
- `roof_loads()` converts the vertical gravity loads into distributed loads.
- `Frame.solve()` assembles the plane-frame stiffness matrix with axial and
  bending deformation and consistent distributed-load vectors.
- `check_roof_frame()` solves the load cases, prints diagnostics and optionally
  appends pages to an open `CalculationReport`.

The reusable check accepts a `RoofGeometry`, both timber material classes and
sections, number of collar boards, spacing, roof/ceiling masses, roof snow load,
and `restrain_purlins`. Geometry and the chosen section heights must describe
the same centre lines. A caller can set `maximum_element_length` to refine the
mesh. The normal/lowered collar geometry is selected with `lowered=False/True`.

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

The leading comparison table shows independent design-force envelopes. Detail
pages include a schematic/deformed shape and N/M diagrams for the design case
with largest collar axial force.

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
