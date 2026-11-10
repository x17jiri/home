# Roof simulator: saved deflection failures

This report summarizes the current saved CSV results; the simulator was not rerun.

## Inputs recorded for this run

- Two purlins, each with two posts and three modelled pieces.
- Roof layers: 150 kg/m² of slope; snow: 2 kN/m² of plan area.
- Timber: rafters C22; other timber C22.
- Gable bearings: on; braces: off; purlins: split above posts.
- Wall-plate X restraint: 0 kN/mm.

## Results

L/300: 0 failed checks. L/500: 12 failed checks, on 6 distinct members.

Checks use the maximum departure of each beam span from the straight line between its support positions. These are instantaneous elastic deflection checks; they are not timber strength, buckling, creep or connection-capacity checks.

## Worst failed check per member

| Member | Load case | Section (mm) | Span (m) | Deflection (mm) | L/300 (mm) | L/500 (mm) | L/500 excess | Location X, Y, Z (m) |
|---|---|---|---:|---:|---:|---:|---:|---|
| P1.1 | SLS_symmetric | 160 × 240 | 2.920 | 6.559 | 9.733 | 5.840 | 12.3% | 2.860, 1.582, 6.525 |
| P1.2 | SLS_symmetric | 160 × 240 | 2.920 | 6.542 | 9.733 | 5.840 | 12.0% | 2.860, 4.511, 6.525 |
| P1.3 | SLS_symmetric | 160 × 240 | 2.920 | 6.630 | 9.733 | 5.840 | 13.5% | 2.860, 7.415, 6.525 |
| P2.1 | SLS_symmetric | 160 × 240 | 2.920 | 6.559 | 9.733 | 5.840 | 12.3% | 5.890, 1.582, 6.525 |
| P2.2 | SLS_symmetric | 160 × 240 | 2.920 | 6.542 | 9.733 | 5.840 | 12.0% | 5.890, 4.511, 6.525 |
| P2.3 | SLS_symmetric | 160 × 240 | 2.920 | 6.630 | 9.733 | 5.840 | 13.5% | 5.890, 7.415, 6.525 |

P1 and P2 identify the purlins. The suffix .1, .2 or .3 identifies the piece between a beam end and a post, or between posts. Coordinates above locate the point of maximum chord departure on the undeformed beam.

## All failed checks

| Member | Load case | Span (m) | Deflection (mm) | L/300 status | L/500 limit (mm) |
|---|---|---:|---:|---|---:|
| P1.1 | SLS_east | 2.920 | 6.329 | PASS | 5.840 |
| P1.1 | SLS_symmetric | 2.920 | 6.559 | PASS | 5.840 |
| P1.2 | SLS_east | 2.920 | 6.233 | PASS | 5.840 |
| P1.2 | SLS_symmetric | 2.920 | 6.542 | PASS | 5.840 |
| P1.3 | SLS_east | 2.920 | 6.397 | PASS | 5.840 |
| P1.3 | SLS_symmetric | 2.920 | 6.630 | PASS | 5.840 |
| P2.1 | SLS_symmetric | 2.920 | 6.559 | PASS | 5.840 |
| P2.1 | SLS_west | 2.920 | 6.329 | PASS | 5.840 |
| P2.2 | SLS_symmetric | 2.920 | 6.542 | PASS | 5.840 |
| P2.2 | SLS_west | 2.920 | 6.233 | PASS | 5.840 |
| P2.3 | SLS_symmetric | 2.920 | 6.630 | PASS | 5.840 |
| P2.3 | SLS_west | 2.920 | 6.397 | PASS | 5.840 |

## Source files

- [Deflection checks](roof_frame_3d_house2_deflections.csv): every checked span and SLS load case.
- [Member forces](roof_frame_3d_house2_members.csv): sections, forces, moments and sampled displacements.
- [Support reactions](roof_frame_3d_house2_supports.csv): reactions and movements by load case.
- [Saved inputs and assumptions](roof_frame_3d_house2_basis.json).

`start_m`, `end_m` and `at_m` in the deflection CSV are distances along the individual modelled member, not global house coordinates. `L300_status` and `L500_status` are the pass/fail fields.

This is a snapshot of the saved results. To save the console summary on a future run:

```bash
.venv-roof3d/bin/python roof_frame_3d_house2.py 2>&1 | tee roof_frame_3d_house2.log
```
