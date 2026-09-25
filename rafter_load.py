#!/usr/bin/env python3
"""Estimate the uniform line load allowed by a rafter deflection limit.

Edit the values in the USER INPUTS section or pass command-line overrides.
The calculation assumes a rectangular, simply supported beam with a uniform
transverse load. It is a quick comparison tool, not a structural design.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from math import cos, isfinite, radians


# USER INPUTS
RAFTER_WIDTH_MM = 100.0
RAFTER_HEIGHT_MM = 180.0
SUPPORT_SPAN_M = 3.75
MAX_DEFLECTION_RATIO = 300.0  # 300 means L/300
ROOF_ANGLE_DEGREES = 36.65
DORMER_SUPPORT_SPAN_M = 3.10
DORMER_ROOF_ANGLE_DEGREES = 17.03
RAFTER_SPACING_M = 0.82

# Vertical roof snow load per square metre of HORIZONTAL projection. This is
# treated as the selected roof load case; no snow shape, exposure, thermal,
# drift, or partial-safety coefficient is applied automatically.
SNOW_LOAD_KN_M2 = 1.7

# Permanent masses per square metre of ACTUAL SLOPING roof surface. Enter the
# installed mass of every layer. Use 0 only when a listed layer is genuinely
# absent; None keeps the overall check explicitly incomplete.
ROOF_LAYERS_KG_M2: dict[str, float | None] = {
    "Roof tiles": 45,
    "Tile battens": 5,
    "Counter battens": 3,
    "other": 4,
    "Wood fibreboard": 15,
    "Mineral wool between rafters": 15,
    "Under rafter battens": 3,
    "Installation battens/services": 5,
    "Gypsum plasterboard": 40,
}

# Deflection also depends on timber stiffness. 11 GPa is an illustrative
# mean modulus for C24 timber; replace it with the value appropriate to the
# actual species, grade, moisture condition, and load duration.
ELASTIC_MODULUS_GPA = 11.0

# Used only to subtract the rafter's own mass from the total line load.
TIMBER_DENSITY_KG_M3 = 450.0

# Preliminary EN 1995 / C24 inputs. These are exposed rather than hidden so
# they can be matched to the selected timber declaration and Czech National
# Annex before treating the output as a design check.
C24_BENDING_STRENGTH_MPA = 24.0
C24_SHEAR_STRENGTH_MPA = 4.0
C24_COMPRESSION_PERPENDICULAR_MPA = 2.5
TIMBER_MATERIAL_PARTIAL_FACTOR = 1.30
TIMBER_MODIFICATION_FACTOR = 0.80  # solid timber, service class 2, snow
TIMBER_CREEP_FACTOR = 0.80  # k_def, solid timber, service class 2
SNOW_CREEP_COMBINATION_FACTOR = 0.0  # psi_2; verify for the project/NA
PERMANENT_LOAD_FACTOR = 1.35
SNOW_LOAD_FACTOR = 1.50
BEARING_LENGTH_MM = 160.0
BEARING_STRENGTH_FACTOR = 1.0  # conservative k_c,90 pending support detail
SHEAR_EFFECTIVE_WIDTH_FACTOR = 0.67  # k_cr; verify selected EC5 edition

GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class RafterLoadResult:
    second_moment_m4: float
    section_modulus_m3: float
    maximum_deflection_m: float
    roof_cosine: float
    self_mass_kg_per_m: float
    self_transverse_n_per_m: float
    deflection_total_n_per_m: float
    deflection_payload_kg_per_m: float
    snow_vertical_n_per_m: float
    snow_transverse_n_per_m: float
    snow_deflection_m: float
    snow_deflection_utilization: float
    maximum_snow_load_kn_m2: float
    bending_total_n_per_m: float | None
    bending_payload_kg_per_m: float | None
    snow_bending_utilization: float | None
    governing_payload_kg_per_m: float
    governing_limit: str


@dataclass(frozen=True)
class RoofCheckResult:
    """Combined permanent-load, snow, creep, and preliminary strength check."""

    rafter: RafterLoadResult
    roof_layer_mass_kg_m2: float
    missing_roof_layers: tuple[str, ...]
    permanent_transverse_n_per_m: float
    characteristic_transverse_n_per_m: float
    permanent_immediate_deflection_m: float
    snow_immediate_deflection_m: float
    characteristic_deflection_m: float
    final_deflection_m: float
    characteristic_deflection_utilization: float
    final_deflection_utilization: float
    maximum_snow_immediate_kn_m2: float
    maximum_snow_final_kn_m2: float
    design_transverse_n_per_m: float
    design_bending_moment_nm: float
    design_shear_force_n: float
    design_support_reaction_n: float
    bending_resistance_nm: float
    shear_resistance_n: float
    bearing_resistance_n: float
    bending_utilization: float
    shear_utilization: float
    bearing_utilization: float
    governing_strength_check: str
    governing_strength_utilization: float


def _positive(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a number") from error
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero")
    return result


def _roof_angle(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError("roof_angle_degrees must be a number") from error
    if not isfinite(result) or not 0 <= result < 90:
        raise ValueError(
            "roof_angle_degrees must be finite and between 0 and 90 degrees"
        )
    return result


def _non_negative(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a number") from error
    if not isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite number not less than zero")
    return result


def calculate_rafter_load(
    *,
    width_mm: float,
    height_mm: float,
    support_span_m: float,
    deflection_ratio: float,
    elastic_modulus_gpa: float,
    timber_density_kg_m3: float = TIMBER_DENSITY_KG_M3,
    allowable_bending_stress_mpa: float | None = None,
    roof_angle_degrees: float = 0,
    rafter_spacing_m: float = 1,
    snow_load_kn_m2: float = 0,
) -> RafterLoadResult:
    """Return uniform-load limits for a simply supported rectangular rafter.

    The load acts perpendicular to the rafter and is distributed uniformly
    per metre of its sloping length. The deflection equation is
    ``delta = 5 q L^4 / (384 E I)``. The optional bending check uses
    ``M_max = q L^2 / 8``. ``snow_load_kn_m2`` is a vertical load on the
    horizontal roof projection. It is converted to transverse line load as
    ``snow * spacing * cos(angle)^2``.
    """
    width_m = _positive(width_mm, "width_mm") / 1000
    height_m = _positive(height_mm, "height_mm") / 1000
    span_m = _positive(support_span_m, "support_span_m")
    ratio = _positive(deflection_ratio, "deflection_ratio")
    modulus_pa = _positive(elastic_modulus_gpa, "elastic_modulus_gpa") * 1e9
    density_kg_m3 = _positive(timber_density_kg_m3, "timber_density_kg_m3")
    angle_degrees = _roof_angle(roof_angle_degrees)
    spacing_m = _positive(rafter_spacing_m, "rafter_spacing_m")
    snow_load_pa = _non_negative(snow_load_kn_m2, "snow_load_kn_m2") * 1000
    roof_cosine = cos(radians(angle_degrees))

    second_moment_m4 = width_m * height_m**3 / 12
    section_modulus_m3 = width_m * height_m**2 / 6
    maximum_deflection_m = span_m / ratio

    # Rearranged simply supported UDL deflection equation.
    deflection_total_n_per_m = (
        maximum_deflection_m
        * 384
        * modulus_pa
        * second_moment_m4
        / (5 * span_m**4)
    )
    self_mass_kg_per_m = density_kg_m3 * width_m * height_m
    self_transverse_n_per_m = (
        self_mass_kg_per_m * GRAVITY_M_S2 * roof_cosine
    )
    deflection_payload_kg_per_m = max(
        0.0,
        (deflection_total_n_per_m - self_transverse_n_per_m) / GRAVITY_M_S2,
    )

    # One metre along the rafter covers cos(angle) metres in plan. The
    # vertical line load therefore receives one cosine for projected area,
    # then another when resolved perpendicular to the rafter.
    snow_vertical_n_per_m = snow_load_pa * spacing_m * roof_cosine
    snow_transverse_n_per_m = snow_vertical_n_per_m * roof_cosine
    combined_transverse_n_per_m = (
        self_transverse_n_per_m + snow_transverse_n_per_m
    )
    snow_deflection_utilization = (
        combined_transverse_n_per_m / deflection_total_n_per_m
    )
    snow_deflection_m = (
        maximum_deflection_m * snow_deflection_utilization
    )
    remaining_for_snow_n_per_m = max(
        0.0,
        deflection_total_n_per_m - self_transverse_n_per_m,
    )
    maximum_snow_load_kn_m2 = (
        remaining_for_snow_n_per_m
        / (spacing_m * roof_cosine**2)
        / 1000
    )

    bending_total_n_per_m: float | None = None
    bending_payload_kg_per_m: float | None = None
    snow_bending_utilization: float | None = None
    governing_payload_kg_per_m = deflection_payload_kg_per_m
    governing_limit = "deflection"
    if allowable_bending_stress_mpa is not None:
        allowable_stress_pa = (
            _positive(
                allowable_bending_stress_mpa,
                "allowable_bending_stress_mpa",
            )
            * 1e6
        )
        allowable_moment_nm = allowable_stress_pa * section_modulus_m3
        bending_total_n_per_m = 8 * allowable_moment_nm / span_m**2
        bending_payload_kg_per_m = max(
            0.0,
            (bending_total_n_per_m - self_transverse_n_per_m) / GRAVITY_M_S2,
        )
        snow_bending_utilization = (
            combined_transverse_n_per_m / bending_total_n_per_m
        )
        if bending_payload_kg_per_m < governing_payload_kg_per_m:
            governing_payload_kg_per_m = bending_payload_kg_per_m
            governing_limit = "bending"

    return RafterLoadResult(
        second_moment_m4=second_moment_m4,
        section_modulus_m3=section_modulus_m3,
        maximum_deflection_m=maximum_deflection_m,
        roof_cosine=roof_cosine,
        self_mass_kg_per_m=self_mass_kg_per_m,
        self_transverse_n_per_m=self_transverse_n_per_m,
        deflection_total_n_per_m=deflection_total_n_per_m,
        deflection_payload_kg_per_m=deflection_payload_kg_per_m,
        snow_vertical_n_per_m=snow_vertical_n_per_m,
        snow_transverse_n_per_m=snow_transverse_n_per_m,
        snow_deflection_m=snow_deflection_m,
        snow_deflection_utilization=snow_deflection_utilization,
        maximum_snow_load_kn_m2=maximum_snow_load_kn_m2,
        bending_total_n_per_m=bending_total_n_per_m,
        bending_payload_kg_per_m=bending_payload_kg_per_m,
        snow_bending_utilization=snow_bending_utilization,
        governing_payload_kg_per_m=governing_payload_kg_per_m,
        governing_limit=governing_limit,
    )


def calculate_roof_check(
    *,
    width_mm: float,
    height_mm: float,
    support_span_m: float,
    deflection_ratio: float,
    elastic_modulus_gpa: float,
    roof_angle_degrees: float,
    rafter_spacing_m: float,
    snow_load_kn_m2: float,
    roof_layers_kg_m2: Mapping[str, float | None] | None = None,
    timber_density_kg_m3: float = TIMBER_DENSITY_KG_M3,
    bending_strength_mpa: float = C24_BENDING_STRENGTH_MPA,
    shear_strength_mpa: float = C24_SHEAR_STRENGTH_MPA,
    compression_perpendicular_mpa: float = (
        C24_COMPRESSION_PERPENDICULAR_MPA
    ),
    material_partial_factor: float = TIMBER_MATERIAL_PARTIAL_FACTOR,
    modification_factor: float = TIMBER_MODIFICATION_FACTOR,
    creep_factor: float = TIMBER_CREEP_FACTOR,
    snow_creep_combination_factor: float = SNOW_CREEP_COMBINATION_FACTOR,
    permanent_load_factor: float = PERMANENT_LOAD_FACTOR,
    snow_load_factor: float = SNOW_LOAD_FACTOR,
    bearing_length_mm: float = BEARING_LENGTH_MM,
    bearing_strength_factor: float = BEARING_STRENGTH_FACTOR,
    shear_effective_width_factor: float = SHEAR_EFFECTIVE_WIDTH_FACTOR,
) -> RoofCheckResult:
    """Check one simply supported rafter under roof dead load and snow.

    Roof-layer masses use the actual sloping surface. Snow uses horizontal
    projection. Strength checks use a fundamental combination of factored
    permanent and snow actions. Final deflection applies ``k_def`` to the
    permanent action and ``psi_2 * k_def`` to snow.
    """
    rafter = calculate_rafter_load(
        width_mm=width_mm,
        height_mm=height_mm,
        support_span_m=support_span_m,
        deflection_ratio=deflection_ratio,
        elastic_modulus_gpa=elastic_modulus_gpa,
        timber_density_kg_m3=timber_density_kg_m3,
        roof_angle_degrees=roof_angle_degrees,
        rafter_spacing_m=rafter_spacing_m,
        snow_load_kn_m2=snow_load_kn_m2,
    )

    if roof_layers_kg_m2 is None:
        roof_layers_kg_m2 = {}
    if not isinstance(roof_layers_kg_m2, Mapping):
        raise TypeError("roof_layers_kg_m2 must be a mapping")
    missing_roof_layers: list[str] = []
    roof_layer_mass_kg_m2 = 0.0
    for supplied_name, supplied_mass in roof_layers_kg_m2.items():
        if not isinstance(supplied_name, str) or not supplied_name.strip():
            raise ValueError("roof layer names must be non-empty strings")
        if supplied_mass is None:
            missing_roof_layers.append(supplied_name.strip())
            continue
        roof_layer_mass_kg_m2 += _non_negative(
            supplied_mass,
            f'roof layer "{supplied_name}" mass',
        )

    spacing_m = _positive(rafter_spacing_m, "rafter_spacing_m")
    span_m = _positive(support_span_m, "support_span_m")
    width_m = _positive(width_mm, "width_mm") / 1000
    height_m = _positive(height_mm, "height_mm") / 1000
    layer_transverse_n_per_m = (
        roof_layer_mass_kg_m2
        * GRAVITY_M_S2
        * spacing_m
        * rafter.roof_cosine
    )
    permanent_transverse_n_per_m = (
        rafter.self_transverse_n_per_m + layer_transverse_n_per_m
    )
    characteristic_transverse_n_per_m = (
        permanent_transverse_n_per_m + rafter.snow_transverse_n_per_m
    )

    deflection_per_n_per_m = (
        rafter.maximum_deflection_m / rafter.deflection_total_n_per_m
    )
    permanent_immediate_deflection_m = (
        permanent_transverse_n_per_m * deflection_per_n_per_m
    )
    snow_immediate_deflection_m = (
        rafter.snow_transverse_n_per_m * deflection_per_n_per_m
    )
    characteristic_deflection_m = (
        permanent_immediate_deflection_m + snow_immediate_deflection_m
    )
    creep_factor = _non_negative(creep_factor, "creep_factor")
    snow_creep_combination_factor = _non_negative(
        snow_creep_combination_factor,
        "snow_creep_combination_factor",
    )
    final_deflection_m = (
        permanent_immediate_deflection_m * (1 + creep_factor)
        + snow_immediate_deflection_m
        * (1 + snow_creep_combination_factor * creep_factor)
    )
    characteristic_deflection_utilization = (
        characteristic_deflection_m / rafter.maximum_deflection_m
    )
    final_deflection_utilization = (
        final_deflection_m / rafter.maximum_deflection_m
    )

    snow_line_conversion = spacing_m * rafter.roof_cosine**2 * 1000
    immediate_snow_capacity_n_per_m = max(
        0.0,
        rafter.deflection_total_n_per_m - permanent_transverse_n_per_m,
    )
    maximum_snow_immediate_kn_m2 = (
        immediate_snow_capacity_n_per_m / snow_line_conversion
    )
    final_snow_capacity_n_per_m = max(
        0.0,
        (
            rafter.deflection_total_n_per_m
            - permanent_transverse_n_per_m * (1 + creep_factor)
        )
        / (1 + snow_creep_combination_factor * creep_factor),
    )
    maximum_snow_final_kn_m2 = (
        final_snow_capacity_n_per_m / snow_line_conversion
    )

    permanent_load_factor = _positive(
        permanent_load_factor,
        "permanent_load_factor",
    )
    snow_load_factor = _positive(snow_load_factor, "snow_load_factor")
    design_transverse_n_per_m = (
        permanent_load_factor * permanent_transverse_n_per_m
        + snow_load_factor * rafter.snow_transverse_n_per_m
    )
    design_bending_moment_nm = design_transverse_n_per_m * span_m**2 / 8
    design_shear_force_n = design_transverse_n_per_m * span_m / 2
    design_support_reaction_n = design_shear_force_n

    material_partial_factor = _positive(
        material_partial_factor,
        "material_partial_factor",
    )
    modification_factor = _positive(
        modification_factor,
        "modification_factor",
    )
    design_strength_multiplier = modification_factor / material_partial_factor
    bending_resistance_nm = (
        _positive(bending_strength_mpa, "bending_strength_mpa")
        * 1e6
        * design_strength_multiplier
        * rafter.section_modulus_m3
    )
    effective_width_m = (
        width_m
        * _positive(
            shear_effective_width_factor,
            "shear_effective_width_factor",
        )
    )
    design_shear_strength_pa = (
        _positive(shear_strength_mpa, "shear_strength_mpa")
        * 1e6
        * design_strength_multiplier
    )
    shear_resistance_n = (
        design_shear_strength_pa * effective_width_m * height_m / 1.5
    )
    bearing_area_m2 = (
        width_m * _positive(bearing_length_mm, "bearing_length_mm") / 1000
    )
    design_bearing_strength_pa = (
        _positive(
            compression_perpendicular_mpa,
            "compression_perpendicular_mpa",
        )
        * 1e6
        * design_strength_multiplier
        * _positive(bearing_strength_factor, "bearing_strength_factor")
    )
    bearing_resistance_n = design_bearing_strength_pa * bearing_area_m2

    bending_utilization = design_bending_moment_nm / bending_resistance_nm
    shear_utilization = design_shear_force_n / shear_resistance_n
    bearing_utilization = design_support_reaction_n / bearing_resistance_n
    strength_utilizations = {
        "bending": bending_utilization,
        "shear": shear_utilization,
        "bearing": bearing_utilization,
    }
    governing_strength_check = max(
        strength_utilizations,
        key=strength_utilizations.__getitem__,
    )

    return RoofCheckResult(
        rafter=rafter,
        roof_layer_mass_kg_m2=roof_layer_mass_kg_m2,
        missing_roof_layers=tuple(missing_roof_layers),
        permanent_transverse_n_per_m=permanent_transverse_n_per_m,
        characteristic_transverse_n_per_m=characteristic_transverse_n_per_m,
        permanent_immediate_deflection_m=permanent_immediate_deflection_m,
        snow_immediate_deflection_m=snow_immediate_deflection_m,
        characteristic_deflection_m=characteristic_deflection_m,
        final_deflection_m=final_deflection_m,
        characteristic_deflection_utilization=(
            characteristic_deflection_utilization
        ),
        final_deflection_utilization=final_deflection_utilization,
        maximum_snow_immediate_kn_m2=maximum_snow_immediate_kn_m2,
        maximum_snow_final_kn_m2=maximum_snow_final_kn_m2,
        design_transverse_n_per_m=design_transverse_n_per_m,
        design_bending_moment_nm=design_bending_moment_nm,
        design_shear_force_n=design_shear_force_n,
        design_support_reaction_n=design_support_reaction_n,
        bending_resistance_nm=bending_resistance_nm,
        shear_resistance_n=shear_resistance_n,
        bearing_resistance_n=bearing_resistance_n,
        bending_utilization=bending_utilization,
        shear_utilization=shear_utilization,
        bearing_utilization=bearing_utilization,
        governing_strength_check=governing_strength_check,
        governing_strength_utilization=strength_utilizations[
            governing_strength_check
        ],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check main-roof and dormer rafters under shared uniformly "
            "distributed loads."
        )
    )
    parser.add_argument("--width", type=float, default=RAFTER_WIDTH_MM,
                        help="rafter width in mm")
    parser.add_argument("--height", type=float, default=RAFTER_HEIGHT_MM,
                        help="rafter height in mm")
    parser.add_argument(
        "--span",
        type=float,
        default=SUPPORT_SPAN_M,
        help="main rafter distance between supports in m",
    )
    parser.add_argument(
        "--deflection-ratio",
        type=float,
        default=MAX_DEFLECTION_RATIO,
        help="denominator N of the L/N deflection limit",
    )
    parser.add_argument(
        "--modulus",
        type=float,
        default=ELASTIC_MODULUS_GPA,
        help="effective modulus of elasticity in GPa",
    )
    parser.add_argument(
        "--density",
        type=float,
        default=TIMBER_DENSITY_KG_M3,
        help="timber density in kg/m^3",
    )
    parser.add_argument(
        "--angle",
        type=float,
        default=ROOF_ANGLE_DEGREES,
        help="main roof angle above horizontal in degrees",
    )
    parser.add_argument(
        "--dormer-span",
        type=float,
        default=DORMER_SUPPORT_SPAN_M,
        help="dormer rafter distance between supports in m",
    )
    parser.add_argument(
        "--dormer-angle",
        type=float,
        default=DORMER_ROOF_ANGLE_DEGREES,
        help="dormer roof angle above horizontal in degrees",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=RAFTER_SPACING_M,
        help="rafter centre spacing in m",
    )
    parser.add_argument(
        "--snow-load",
        type=float,
        default=SNOW_LOAD_KN_M2,
        help="vertical roof snow load in kN/m^2 of horizontal projection",
    )
    return parser


def _status(utilization: float) -> str:
    return "PASS" if utilization <= 1 else "FAIL"


def _print_roof_check(
    name: str,
    *,
    support_span_m: float,
    roof_angle_degrees: float,
    deflection_ratio: float,
    check: RoofCheckResult,
) -> None:
    """Print the case-specific results for one roof rafter."""
    result = check.rafter

    print()
    print(f"{name}:")
    print(
        f"  Support span: {support_span_m:g} m; "
        f"roof angle: {roof_angle_degrees:g}°"
    )
    print(
        f"  Deflection limit: L/{deflection_ratio:g} = "
        f"{result.maximum_deflection_m * 1000:.1f} mm"
    )
    print(
        "  Deflection-limited total uniform transverse load: "
        f"{result.deflection_total_n_per_m / GRAVITY_M_S2:.1f} kg/m"
    )
    print(
        "  Snow load on one rafter: "
        f"{result.snow_vertical_n_per_m / 1000:.3f} kN/m vertical, "
        f"{result.snow_transverse_n_per_m / 1000:.3f} kN/m transverse"
    )

    print("  Serviceability (SLS):")
    print(
        "    Immediate deflection, permanent + snow: "
        f"{check.characteristic_deflection_m * 1000:.1f} mm / "
        f"{result.maximum_deflection_m * 1000:.1f} mm "
        f"({check.characteristic_deflection_utilization * 100:.1f}%, "
        f"{_status(check.characteristic_deflection_utilization)})"
    )
    print(
        f"    Final deflection with k_def={TIMBER_CREEP_FACTOR:g}: "
        f"{check.final_deflection_m * 1000:.1f} mm / "
        f"{result.maximum_deflection_m * 1000:.1f} mm "
        f"({check.final_deflection_utilization * 100:.1f}%, "
        f"{_status(check.final_deflection_utilization)})"
    )
    print(
        "    Maximum snow from immediate deflection: "
        f"{check.maximum_snow_immediate_kn_m2:.2f} kN/m²"
    )
    print(
        "    Maximum snow from final deflection: "
        f"{check.maximum_snow_final_kn_m2:.2f} kN/m²"
    )

    print(
        "  Ultimate strength (ULS, preliminary C24; "
        f"{PERMANENT_LOAD_FACTOR:g}G + {SNOW_LOAD_FACTOR:g}S):"
    )
    for check_name, demand, resistance, utilization, unit_scale, unit in (
        (
            "Bending",
            check.design_bending_moment_nm,
            check.bending_resistance_nm,
            check.bending_utilization,
            1000,
            "kN·m",
        ),
        (
            "Shear",
            check.design_shear_force_n,
            check.shear_resistance_n,
            check.shear_utilization,
            1000,
            "kN",
        ),
        (
            "Bearing",
            check.design_support_reaction_n,
            check.bearing_resistance_n,
            check.bearing_utilization,
            1000,
            "kN",
        ),
    ):
        print(
            f"    {check_name}: {demand / unit_scale:.2f} / "
            f"{resistance / unit_scale:.2f} {unit}, "
            f"{utilization * 100:.1f}% "
            f"({_status(utilization)})"
        )
    print(
        f"    Governing: {check.governing_strength_check}, "
        f"{check.governing_strength_utilization * 100:.1f}%"
    )


def main() -> None:
    arguments = _parser().parse_args()
    shared_check_arguments = {
        "width_mm": arguments.width,
        "height_mm": arguments.height,
        "deflection_ratio": arguments.deflection_ratio,
        "elastic_modulus_gpa": arguments.modulus,
        "timber_density_kg_m3": arguments.density,
        "rafter_spacing_m": arguments.spacing,
        "snow_load_kn_m2": arguments.snow_load,
        "roof_layers_kg_m2": ROOF_LAYERS_KG_M2,
    }
    roof_cases = (
        ("Main roof", arguments.span, arguments.angle),
        ("Dormer roof", arguments.dormer_span, arguments.dormer_angle),
    )
    checks = [
        (
            name,
            span,
            angle,
            calculate_roof_check(
                support_span_m=span,
                roof_angle_degrees=angle,
                **shared_check_arguments,
            ),
        )
        for name, span, angle in roof_cases
    ]

    print(
        f"Shared rafter: {arguments.width:g} × {arguments.height:g} mm, "
        f"spacing {arguments.spacing:g} m"
    )
    print(
        f"Shared timber: E={arguments.modulus:g} GPa, "
        f"density {arguments.density:g} kg/m³"
    )
    print(
        f"Rafter self-mass: {checks[0][3].rafter.self_mass_kg_per_m:.1f} kg/m"
    )

    print()
    print("Shared permanent roof layers (actual sloping surface):")
    for layer_name, mass in ROOF_LAYERS_KG_M2.items():
        value = "MISSING" if mass is None else f"{mass:.1f} kg/m²"
        print(f"  {layer_name}: {value}")
    print(
        f"  Known layer total: {checks[0][3].roof_layer_mass_kg_m2:.1f} kg/m²"
    )
    if checks[0][3].missing_roof_layers:
        print(
            "CHECK INCOMPLETE: enter a mass for every layer listed as MISSING."
        )

    print()
    print(
        f"Shared snow load: {arguments.snow_load:g} kN/m² on horizontal "
        f"projection ({arguments.snow_load * 1000 / GRAVITY_M_S2:.1f} "
        "kg/m² equivalent)"
    )
    for name, span, angle, check in checks:
        _print_roof_check(
            name,
            support_span_m=span,
            roof_angle_degrees=angle,
            deflection_ratio=arguments.deflection_ratio,
            check=check,
        )

    governing_sls = max(
        checks,
        key=lambda case: case[3].final_deflection_utilization,
    )
    governing_uls = max(
        checks,
        key=lambda case: case[3].governing_strength_utilization,
    )
    print()
    print("Governing roof cases:")
    print(
        f"  Final deflection: {governing_sls[0]}, "
        f"{governing_sls[3].final_deflection_utilization * 100:.1f}% "
        f"({_status(governing_sls[3].final_deflection_utilization)})"
    )
    print(
        f"  Strength: {governing_uls[0]} "
        f"{governing_uls[3].governing_strength_check}, "
        f"{governing_uls[3].governing_strength_utilization * 100:.1f}% "
        f"({_status(governing_uls[3].governing_strength_utilization)})"
    )

    print()
    print(
        "WARNING: Preliminary member check only. Confirm material values and "
        "National Annex factors. Axial force, lateral buckling/restraint, "
        "notches, holes, connections, wind uplift, fire, and snow drift/shape "
        "cases still require separate checks."
    )


if __name__ == "__main__":
    main()
