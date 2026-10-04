#!/usr/bin/env python3
"""Preliminary checks of the roof rafters and their supporting purlin.

Edit the check calls in ``main()`` to describe each structural member.
Rafters are treated as simply supported beams. Purlins can be checked either
as individual simply supported pieces or as one uniform continuous member over
four supports. It is a quick comparison tool, not a structural design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from pathlib import Path
from textwrap import wrap
from typing import TypeAlias

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


# Shared project inputs used by the checks in main().
ROOF_ANGLE_DEGREES = 35.83
MAX_DEFLECTION_RATIO = 300.0  # 300 means L/300
SNOW_LOAD_KN_M2 = 1.7  # vertical load per horizontal roof projection

REPORT_SNOW_LOAD_STANDARD = "ČSN EN 1991-1-3:2005/Z1:2006"
REPORT_SNOW_LOAD_ZONE = 3
REPORT_BASIS_STANDARD = "ČSN EN 1990 a příslušná národní příloha"
REPORT_TIMBER_STANDARD = "ČSN EN 1995-1-1 a příslušná národní příloha"
REPORT_TIMBER_GRADES_STANDARD = "ČSN EN 338"

# Permanent masses per square metre of ACTUAL SLOPING roof surface. Enter the
# installed mass of every layer. Use 0 only when a listed layer is genuinely
# absent; None keeps the overall check explicitly incomplete.
ROOF_LAYERS_KG_M2: dict[str, float | None] = {
    "Roof tiles": 50,
    "Tile battens": 5,
    "Counter battens": 5,
    "MDF": 10,
    "vata": 20,
    "OSB": 10,
    "Installation battens/services": 5,
    "Gypsum plasterboard": 30,
}

# Shared calculation assumptions. These are model/code properties rather than
# project geometry, so keeping them together as constants is useful.
TIMBER_DENSITY_KG_M3 = 450.0
TIMBER_MATERIAL_PARTIAL_FACTOR = 1.30
TIMBER_MODIFICATION_FACTOR = 0.80  # solid timber, service class 2, snow
TIMBER_CREEP_FACTOR = 0.80  # k_def, solid timber, service class 2
SNOW_CREEP_COMBINATION_FACTOR = 0.0  # psi_2; verify for the project/NA
PERMANENT_LOAD_FACTOR = 1.35
SNOW_LOAD_FACTOR = 1.50
BEARING_STRENGTH_FACTOR = 1.0  # conservative k_c,90 pending support detail
SHEAR_EFFECTIVE_WIDTH_FACTOR = 0.67  # k_cr; verify selected EC5 edition
GRAVITY_M_S2 = 10.0


@dataclass(frozen=True)
class TimberGrade:
    name: str
    elastic_modulus_gpa: float
    bending_strength_mpa: float
    shear_strength_mpa: float
    compression_parallel_mpa: float
    compression_perpendicular_mpa: float


_TIMBER_GRADES = {
    "c22": TimberGrade("C22", 10.0, 22.0, 3.8, 20.0, 2.4),
    "c24": TimberGrade("C24", 11.0, 24.0, 4.0, 21.0, 2.5),
}


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
    bearing_angle_degrees: float
    design_bearing_strength_pa: float
    bearing_area_m2: float
    bending_resistance_nm: float
    shear_resistance_n: float
    bearing_resistance_n: float
    bending_utilization: float
    shear_utilization: float
    bearing_utilization: float
    governing_strength_check: str
    governing_strength_utilization: float


@dataclass(frozen=True)
class ContinuousBeamResponse:
    """Elastic response of one continuous beam under span-wise UDLs."""

    span_lengths_m: tuple[float, ...]
    rotations_radians: tuple[float, ...]
    support_moments_nm: tuple[float, ...]
    support_reactions_n: tuple[float, ...]
    span_positive_moments_nm: tuple[float, ...]
    span_positive_moment_locations_m: tuple[float, ...]
    span_max_abs_shears_n: tuple[float, ...]
    span_max_abs_deflections_m: tuple[float, ...]



@dataclass(frozen=True)
class PurlinCheckResult:
    """One- or three-span purlin check and its tributary roof load."""

    span_lengths_m: tuple[float, ...]
    upper_rafter_length_m: float
    lower_rafter_span_m: float
    tributary_slope_width_m: float
    tributary_horizontal_width_m: float
    roof_layer_line_mass_kg_m: float
    rafter_line_mass_kg_m: float
    additional_permanent_load_kn_m: float
    purlin_self_mass_kg_m: float
    permanent_line_load_kn_m: float
    roof_snow_line_load_kn_m: float
    immediate_response: ContinuousBeamResponse
    final_response: ContinuousBeamResponse
    design_response: ContinuousBeamResponse
    deflection_limits_m: tuple[float, ...]
    immediate_deflection_utilizations: tuple[float, ...]
    final_deflection_utilizations: tuple[float, ...]
    maximum_roof_snow_immediate_kn_m2: float
    maximum_roof_snow_final_kn_m2: float
    bending_resistance_nm: float
    shear_resistance_n: float
    bearing_resistance_n: float
    positive_bending_utilization: float
    negative_bending_utilization: float
    shear_utilization: float
    bearing_utilization: float
    governing_strength_check: str
    governing_strength_utilization: float
    missing_roof_layers: tuple[str, ...]


ReportSection: TypeAlias = tuple[str, Sequence[str]]


class CalculationReport:
    """Small reusable writer for calculation sections in one PDF.

    Element-specific functions such as :func:`add_rafter_report` only prepare
    headings and lines. This class owns pagination, page numbering, and the PDF
    file, so future purlin or collar-tie functions can append their own pages.
    """

    _TOP = 0.915
    _BOTTOM = 0.065
    _LINE_HEIGHT = 0.0175

    def __init__(
        self,
        path: str | Path,
        *,
        document_title: str = "Roof structural calculation",
    ) -> None:
        self.path = Path(path)
        self.document_title = document_title
        self._pdf: PdfPages | None = None
        self._page_count = 0

    @property
    def page_count(self) -> int:
        return self._page_count

    def __enter__(self) -> "CalculationReport":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pdf = PdfPages(
            self.path,
            metadata={
                "Title": self.document_title,
                "Creator": "rafter_load.py",
                "Subject": "Preliminary timber member verification",
            },
        )
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None

    def _start_page(
        self,
        title: str,
        *,
        footer_title: str | None = None,
        page_label: str = "Page",
    ) -> tuple[Figure, float]:
        self._page_count += 1
        figure = Figure(figsize=(8.27, 11.69))
        figure.text(
            0.075,
            0.957,
            title,
            fontsize=15,
            fontweight="bold",
            va="top",
        )
        figure.text(
            0.075,
            0.025,
            footer_title or self.document_title,
            fontsize=7,
            color="#555555",
            va="bottom",
        )
        figure.text(
            0.925,
            0.025,
            f"{page_label} {self._page_count}",
            fontsize=7,
            color="#555555",
            ha="right",
            va="bottom",
        )
        return figure, self._TOP

    def _save_page(self, figure: Figure) -> None:
        if self._pdf is None:
            raise RuntimeError(
                "CalculationReport must be used as a context manager"
            )
        self._pdf.savefig(figure)

    def add_sections(
        self,
        title: str,
        sections: Sequence[ReportSection],
        *,
        footer_title: str | None = None,
        page_label: str = "Page",
        continuation_label: str = "continued",
    ) -> None:
        """Append one or more automatically paginated text pages."""
        if self._pdf is None:
            raise RuntimeError(
                "CalculationReport must be used as a context manager"
            )

        continued_title = None
        figure, y = self._start_page(
            title,
            footer_title=footer_title,
            page_label=page_label,
        )
        has_content = False
        for heading, supplied_lines in sections:
            wrapped_lines: list[str] = []
            for supplied_line in supplied_lines:
                line = str(supplied_line)
                wrapped_lines.extend(
                    wrap(
                        line,
                        width=105,
                        break_long_words=False,
                        break_on_hyphens=False,
                    ) or ("",)
                )
            lines = tuple(wrapped_lines)
            section_height = (
                0.028 + len(lines) * self._LINE_HEIGHT + 0.008
            )
            if has_content and y - section_height < self._BOTTOM:
                self._save_page(figure)
                figure, y = self._start_page(
                    continued_title,
                    footer_title=footer_title,
                    page_label=page_label,
                )
                has_content = False

            figure.text(
                0.075,
                y,
                heading,
                fontsize=10,
                fontweight="bold",
                va="top",
            )
            y -= 0.028
            has_content = True

            for line in lines:
                if y < self._BOTTOM:
                    self._save_page(figure)
                    figure, y = self._start_page(
                        continued_title,
                        footer_title=footer_title,
                        page_label=page_label,
                    )
                    figure.text(
                        0.075,
                        y,
                        f"{heading} ({continuation_label})",
                        fontsize=10,
                        fontweight="bold",
                        va="top",
                    )
                    y -= 0.028
                is_verdict_line = (
                    "VYHOVUJE" in line
                    or "NEVYHOVUJE" in line
                )
                figure.text(
                    0.085,
                    y,
                    line,
                    fontsize=8.4,
                    family="DejaVu Sans",
                    fontweight="bold" if is_verdict_line else "normal",
                    fontstyle="italic" if is_verdict_line else "normal",
                    va="top",
                )
                y -= self._LINE_HEIGHT

            y -= 0.008

        self._save_page(figure)


    def add_table(
        self,
        title: str,
        *,
        column_labels: Sequence[str],
        rows: Sequence[Sequence[str]],
        column_widths: Sequence[float] | None = None,
        intro_lines: Sequence[str] = (),
        bold_last_row: bool = False,
        footer_title: str | None = None,
        page_label: str = "Page",
    ) -> None:
        """Append a single table page to the report."""
        if self._pdf is None:
            raise RuntimeError(
                "CalculationReport must be used as a context manager"
            )

        labels = tuple(str(label) for label in column_labels)
        if not labels:
            raise ValueError("column_labels must not be empty")
        normalized_rows = tuple(
            tuple(str(value) for value in row)
            for row in rows
        )
        if any(len(row) != len(labels) for row in normalized_rows):
            raise ValueError("every table row must match column_labels")

        if column_widths is None:
            widths = tuple(1 / len(labels) for _ in labels)
        else:
            widths = tuple(float(width) for width in column_widths)
            if len(widths) != len(labels):
                raise ValueError(
                    "column_widths must match column_labels"
                )
            if any(width <= 0 for width in widths):
                raise ValueError("column widths must be greater than zero")
            total_width = sum(widths)
            widths = tuple(width / total_width for width in widths)

        figure, y = self._start_page(
            title,
            footer_title=footer_title,
            page_label=page_label,
        )
        for supplied_line in intro_lines:
            for line in wrap(
                str(supplied_line),
                width=105,
                break_long_words=False,
                break_on_hyphens=False,
            ) or ("",):
                figure.text(
                    0.075,
                    y,
                    line,
                    fontsize=8.4,
                    family="DejaVu Sans",
                    va="top",
                )
                y -= self._LINE_HEIGHT
        y -= 0.014

        table_bottom = 0.11
        axes = figure.add_axes(
            (0.075, table_bottom, 0.85, max(0.10, y - table_bottom))
        )
        axes.set_axis_off()
        table = axes.table(
            cellText=normalized_rows,
            colLabels=labels,
            colWidths=widths,
            cellLoc="left",
            colLoc="center",
            loc="upper center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.4)
        table.scale(1, 1.5)

        final_row_index = len(normalized_rows)
        for (row_index, column_index), cell in table.get_celld().items():
            cell.set_edgecolor("#333333")
            cell.set_linewidth(0.55)
            text = cell.get_text()
            text.set_fontfamily("DejaVu Sans")
            if row_index == 0:
                cell.set_facecolor("#e5e5e5")
                text.set_fontweight("bold")
            elif column_index > 0:
                text.set_ha("right")
            if bold_last_row and row_index == final_row_index:
                cell.set_facecolor("#f2f2f2")
                text.set_fontweight("bold")

        self._save_page(figure)


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
    bending_strength_mpa: float = _TIMBER_GRADES["c24"].bending_strength_mpa,
    shear_strength_mpa: float = _TIMBER_GRADES["c24"].shear_strength_mpa,
    compression_parallel_mpa: float = (
        _TIMBER_GRADES["c24"].compression_parallel_mpa
    ),
    compression_perpendicular_mpa: float = (
        _TIMBER_GRADES["c24"].compression_perpendicular_mpa
    ),
    material_partial_factor: float = TIMBER_MATERIAL_PARTIAL_FACTOR,
    modification_factor: float = TIMBER_MODIFICATION_FACTOR,
    creep_factor: float = TIMBER_CREEP_FACTOR,
    snow_creep_combination_factor: float = SNOW_CREEP_COMBINATION_FACTOR,
    permanent_load_factor: float = PERMANENT_LOAD_FACTOR,
    snow_load_factor: float = SNOW_LOAD_FACTOR,
    bearing_length_mm: float = 50.0,
    bearing_strength_factor: float = BEARING_STRENGTH_FACTOR,
    shear_effective_width_factor: float = SHEAR_EFFECTIVE_WIDTH_FACTOR,
) -> RoofCheckResult:
    """Check one simply supported rafter under roof dead load and snow.

    Roof-layer masses use the actual sloping surface. Snow uses horizontal
    projection. Strength checks use a fundamental combination of factored
    permanent and snow actions. Final deflection applies ``k_def`` to the
    permanent action and ``psi_2 * k_def`` to snow.
    Rafter bearing assumes a horizontal seat: the transverse beam reaction is
    converted to its full vertical value and checked as compression at an
    angle to the grain. The support notch itself is not checked.
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
    bearing_angle_degrees = 90 - _roof_angle(roof_angle_degrees)
    bearing_angle_radians = radians(bearing_angle_degrees)
    design_support_reaction_n = design_shear_force_n / rafter.roof_cosine

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
    design_compression_parallel_pa = (
        _positive(
            compression_parallel_mpa,
            "compression_parallel_mpa",
        )
        * 1e6
        * design_strength_multiplier
    )
    design_compression_perpendicular_pa = (
        _positive(
            compression_perpendicular_mpa,
            "compression_perpendicular_mpa",
        )
        * 1e6
        * design_strength_multiplier
    )
    compression_perpendicular_factor = _positive(
        bearing_strength_factor,
        "bearing_strength_factor",
    )
    design_bearing_strength_pa = design_compression_parallel_pa / (
        (
            design_compression_parallel_pa
            / (
                compression_perpendicular_factor
                * design_compression_perpendicular_pa
            )
        )
        * sin(bearing_angle_radians) ** 2
        + cos(bearing_angle_radians) ** 2
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
        bearing_angle_degrees=bearing_angle_degrees,
        design_bearing_strength_pa=design_bearing_strength_pa,
        bearing_area_m2=bearing_area_m2,
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


def _solve_linear_system(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float]:
    """Solve a small dense linear system using pivoted Gauss elimination."""
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise ValueError("continuous beam stiffness matrix is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_row_value
                for value, pivot_row_value in zip(
                    augmented[row],
                    augmented[column],
                )
            ]
    return [augmented[row][-1] for row in range(size)]


def _slope_roots_in_span(slope, span_m: float) -> list[float]:
    """Numerically locate stationary deflection points in one span."""
    roots: list[float] = []
    steps = 256
    previous_x = 0.0
    previous_value = slope(previous_x)
    for step in range(1, steps + 1):
        current_x = span_m * step / steps
        current_value = slope(current_x)
        if previous_value == 0:
            roots.append(previous_x)
        if previous_value * current_value < 0:
            low = previous_x
            high = current_x
            low_value = previous_value
            for _ in range(60):
                middle = (low + high) / 2
                middle_value = slope(middle)
                if low_value * middle_value <= 0:
                    high = middle
                else:
                    low = middle
                    low_value = middle_value
            roots.append((low + high) / 2)
        previous_x = current_x
        previous_value = current_value
    if previous_value == 0:
        roots.append(span_m)
    return [
        value
        for index, value in enumerate(roots)
        if index == 0 or abs(value - roots[index - 1]) > 1e-8
    ]


def calculate_continuous_beam_response(
    *,
    span_lengths_m: tuple[float, ...],
    uniform_loads_n_per_m: tuple[float, ...],
    elastic_modulus_pa: float,
    second_moment_m4: float,
) -> ContinuousBeamResponse:
    """Return the first-order elastic response of a continuous beam.

    All supports restrain vertical translation and allow rotation. The member
    is continuous over every support, has constant ``E I``, and carries one
    uniform vertical load per span. Positive moment is sagging.
    """
    if len(span_lengths_m) != len(uniform_loads_n_per_m):
        raise ValueError("continuous beam needs one load for every span")
    if not span_lengths_m:
        raise ValueError("continuous beam needs at least one span")
    spans = tuple(
        _positive(value, f"span_lengths_m[{index}]")
        for index, value in enumerate(span_lengths_m)
    )
    loads = tuple(
        _non_negative(value, f"uniform_loads_n_per_m[{index}]")
        for index, value in enumerate(uniform_loads_n_per_m)
    )
    modulus_pa = _positive(elastic_modulus_pa, "elastic_modulus_pa")
    inertia_m4 = _positive(second_moment_m4, "second_moment_m4")
    flexural_rigidity = modulus_pa * inertia_m4
    node_count = len(spans) + 1

    rotation_stiffness = [
        [0.0 for _ in range(node_count)] for _ in range(node_count)
    ]
    rotation_loads = [0.0 for _ in range(node_count)]
    for index, (span_m, load_n_m) in enumerate(zip(spans, loads)):
        stiffness = flexural_rigidity / span_m
        rotation_stiffness[index][index] += 4 * stiffness
        rotation_stiffness[index][index + 1] += 2 * stiffness
        rotation_stiffness[index + 1][index] += 2 * stiffness
        rotation_stiffness[index + 1][index + 1] += 4 * stiffness
        rotation_loads[index] -= load_n_m * span_m**2 / 12
        rotation_loads[index + 1] += load_n_m * span_m**2 / 12

    rotations = tuple(
        _solve_linear_system(rotation_stiffness, rotation_loads)
    )
    support_moments = [0.0 for _ in range(node_count)]
    support_reactions = [0.0 for _ in range(node_count)]
    positive_moments: list[float] = []
    positive_locations: list[float] = []
    maximum_shears: list[float] = []
    maximum_deflections: list[float] = []

    for index, (span_m, load_n_m) in enumerate(zip(spans, loads)):
        left_rotation = rotations[index]
        right_rotation = rotations[index + 1]
        left_shear_n = (
            6
            * flexural_rigidity
            / span_m**2
            * (left_rotation + right_rotation)
            + load_n_m * span_m / 2
        )
        right_nodal_shear_n = (
            -6
            * flexural_rigidity
            / span_m**2
            * (left_rotation + right_rotation)
            + load_n_m * span_m / 2
        )
        left_nodal_moment_nm = (
            flexural_rigidity
            / span_m
            * (4 * left_rotation + 2 * right_rotation)
            + load_n_m * span_m**2 / 12
        )
        right_moment_nm = (
            flexural_rigidity
            / span_m
            * (2 * left_rotation + 4 * right_rotation)
            - load_n_m * span_m**2 / 12
        )
        left_moment_nm = -left_nodal_moment_nm
        support_moments[index] = left_moment_nm
        support_moments[index + 1] = right_moment_nm
        support_reactions[index] += left_shear_n
        support_reactions[index + 1] += right_nodal_shear_n

        moment_candidates = [(0.0, left_moment_nm), (span_m, right_moment_nm)]
        if load_n_m > 0:
            zero_shear_x = left_shear_n / load_n_m
            if 0 < zero_shear_x < span_m:
                moment_candidates.append(
                    (
                        zero_shear_x,
                        left_moment_nm
                        + left_shear_n * zero_shear_x
                        - load_n_m * zero_shear_x**2 / 2,
                    )
                )
        positive_x, positive_moment = max(
            moment_candidates,
            key=lambda candidate: candidate[1],
        )
        positive_moments.append(max(0.0, positive_moment))
        positive_locations.append(positive_x)
        maximum_shears.append(
            max(
                abs(left_shear_n),
                abs(left_shear_n - load_n_m * span_m),
            )
        )

        def deflection(x: float) -> float:
            return (
                left_rotation * x
                + (
                    left_moment_nm * x**2 / 2
                    + left_shear_n * x**3 / 6
                    - load_n_m * x**4 / 24
                )
                / flexural_rigidity
            )

        def slope(x: float) -> float:
            return (
                left_rotation
                + (
                    left_moment_nm * x
                    + left_shear_n * x**2 / 2
                    - load_n_m * x**3 / 6
                )
                / flexural_rigidity
            )

        deflection_points = [0.0, span_m]
        deflection_points.extend(_slope_roots_in_span(slope, span_m))
        maximum_deflections.append(
            max(abs(deflection(x)) for x in deflection_points)
        )

    return ContinuousBeamResponse(
        span_lengths_m=spans,
        rotations_radians=rotations,
        support_moments_nm=tuple(support_moments),
        support_reactions_n=tuple(support_reactions),
        span_positive_moments_nm=tuple(positive_moments),
        span_positive_moment_locations_m=tuple(positive_locations),
        span_max_abs_shears_n=tuple(maximum_shears),
        span_max_abs_deflections_m=tuple(maximum_deflections),
    )


def calculate_purlin_check(
    *,
    width_mm: float,
    height_mm: float,
    support_spans_m: Sequence[float],
    upper_rafter_length_m: float,
    lower_rafter_span_m: float,
    roof_angle_degrees: float,
    rafter_width_mm: float,
    rafter_height_mm: float,
    rafter_spacing_m: float,
    deflection_ratio: float,
    elastic_modulus_gpa: float,
    snow_load_kn_m2: float,
    roof_layers_kg_m2: Mapping[str, float | None] | None = None,
    additional_permanent_load_kn_m: float = 0,
    timber_density_kg_m3: float = TIMBER_DENSITY_KG_M3,
    bending_strength_mpa: float = _TIMBER_GRADES["c24"].bending_strength_mpa,
    shear_strength_mpa: float = _TIMBER_GRADES["c24"].shear_strength_mpa,
    compression_perpendicular_mpa: float = (
        _TIMBER_GRADES["c24"].compression_perpendicular_mpa
    ),
    material_partial_factor: float = TIMBER_MATERIAL_PARTIAL_FACTOR,
    modification_factor: float = TIMBER_MODIFICATION_FACTOR,
    creep_factor: float = TIMBER_CREEP_FACTOR,
    snow_creep_combination_factor: float = SNOW_CREEP_COMBINATION_FACTOR,
    permanent_load_factor: float = PERMANENT_LOAD_FACTOR,
    snow_load_factor: float = SNOW_LOAD_FACTOR,
    bearing_length_mm: float = 240.0,
    bearing_strength_factor: float = BEARING_STRENGTH_FACTOR,
    shear_effective_width_factor: float = SHEAR_EFFECTIVE_WIDTH_FACTOR,
) -> PurlinCheckResult:
    """Check one simply supported span or one continuous three-span member.

    Loads are uniform over every span. Rafter reactions are represented as a
    uniformly distributed purlin line load.
    """
    if len(support_spans_m) not in (1, 3):
        raise ValueError("support_spans_m must contain one or three spans")
    spans = tuple(
        _positive(value, f"support_spans_m[{index}]")
        for index, value in enumerate(support_spans_m)
    )
    upper_length_m = _positive(
        upper_rafter_length_m,
        "upper_rafter_length_m",
    )
    lower_span_m = _positive(lower_rafter_span_m, "lower_rafter_span_m")
    angle_degrees = _roof_angle(roof_angle_degrees)
    spacing_m = _positive(rafter_spacing_m, "rafter_spacing_m")
    rafter_width_m = _positive(rafter_width_mm, "rafter_width_mm") / 1000
    rafter_height_m = _positive(rafter_height_mm, "rafter_height_mm") / 1000
    purlin_width_mm = _positive(width_mm, "width_mm")
    purlin_height_mm = _positive(height_mm, "height_mm")
    purlin_width_m = purlin_width_mm / 1000
    purlin_height_m = purlin_height_mm / 1000
    purlin_bearing_length_mm = _positive(
        bearing_length_mm,
        "bearing_length_mm",
    )
    density_kg_m3 = _positive(timber_density_kg_m3, "timber_density_kg_m3")
    modulus_pa = _positive(elastic_modulus_gpa, "elastic_modulus_gpa") * 1e9
    ratio = _positive(deflection_ratio, "deflection_ratio")
    snow_pressure_kn_m2 = _non_negative(
        snow_load_kn_m2,
        "snow_load_kn_m2",
    )
    extra_line_load_kn_m = _non_negative(
        additional_permanent_load_kn_m,
        "additional_permanent_load_kn_m",
    )
    creep_factor = _non_negative(creep_factor, "creep_factor")
    snow_creep_combination_factor = _non_negative(
        snow_creep_combination_factor,
        "snow_creep_combination_factor",
    )

    tributary_slope_width_m = upper_length_m + lower_span_m / 2
    tributary_horizontal_width_m = (
        tributary_slope_width_m * cos(radians(angle_degrees))
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

    roof_layer_line_mass_kg_m = (
        roof_layer_mass_kg_m2 * tributary_slope_width_m
    )
    rafter_mass_kg_m = density_kg_m3 * rafter_width_m * rafter_height_m
    rafter_line_mass_kg_m = (
        rafter_mass_kg_m * tributary_slope_width_m / spacing_m
    )
    purlin_self_mass_kg_m = (
        density_kg_m3 * purlin_width_m * purlin_height_m
    )
    permanent_line_load_kn_m = (
        (
            roof_layer_line_mass_kg_m
            + rafter_line_mass_kg_m
            + purlin_self_mass_kg_m
        )
        * GRAVITY_M_S2
        / 1000
        + extra_line_load_kn_m
    )
    roof_snow_line_load_kn_m = (
        snow_pressure_kn_m2 * tributary_horizontal_width_m
    )
    second_moment_m4 = purlin_width_m * purlin_height_m**3 / 12
    section_modulus_m3 = purlin_width_m * purlin_height_m**2 / 6

    def response(line_load_kn_m: float) -> ContinuousBeamResponse:
        loads = tuple(line_load_kn_m * 1000 for _ in spans)
        return calculate_continuous_beam_response(
            span_lengths_m=spans,
            uniform_loads_n_per_m=loads,
            elastic_modulus_pa=modulus_pa,
            second_moment_m4=second_moment_m4,
        )

    immediate_line_load_kn_m = (
        permanent_line_load_kn_m + roof_snow_line_load_kn_m
    )
    final_line_load_kn_m = (
        permanent_line_load_kn_m * (1 + creep_factor)
        + roof_snow_line_load_kn_m
        * (1 + snow_creep_combination_factor * creep_factor)
    )
    permanent_factor = _positive(
        permanent_load_factor,
        "permanent_load_factor",
    )
    snow_factor = _positive(snow_load_factor, "snow_load_factor")
    design_line_load_kn_m = (
        permanent_factor * permanent_line_load_kn_m
        + snow_factor * roof_snow_line_load_kn_m
    )
    immediate_response = response(immediate_line_load_kn_m)
    final_response = response(final_line_load_kn_m)
    design_response = response(design_line_load_kn_m)
    permanent_response = response(permanent_line_load_kn_m)
    unit_snow_response = response(tributary_horizontal_width_m)

    deflection_limits_m = tuple(span / ratio for span in spans)
    immediate_utilizations = tuple(
        deflection / limit
        for deflection, limit in zip(
            immediate_response.span_max_abs_deflections_m,
            deflection_limits_m,
        )
    )
    final_utilizations = tuple(
        deflection / limit
        for deflection, limit in zip(
            final_response.span_max_abs_deflections_m,
            deflection_limits_m,
        )
    )

    immediate_snow_capacities = []
    final_snow_capacities = []
    for limit, permanent_deflection, unit_snow_deflection in zip(
        deflection_limits_m,
        permanent_response.span_max_abs_deflections_m,
        unit_snow_response.span_max_abs_deflections_m,
    ):
        immediate_snow_capacities.append(
            max(0.0, limit - permanent_deflection) / unit_snow_deflection
        )
        final_snow_capacities.append(
            max(0.0, limit - permanent_deflection * (1 + creep_factor))
            / (
                unit_snow_deflection
                * (1 + snow_creep_combination_factor * creep_factor)
            )
        )

    design_strength_multiplier = _positive(
        modification_factor,
        "modification_factor",
    ) / _positive(material_partial_factor, "material_partial_factor")
    design_bending_strength_pa = (
        _positive(bending_strength_mpa, "bending_strength_mpa")
        * 1e6
        * design_strength_multiplier
    )
    bending_resistance_nm = design_bending_strength_pa * section_modulus_m3
    design_shear_strength_pa = (
        _positive(shear_strength_mpa, "shear_strength_mpa")
        * 1e6
        * design_strength_multiplier
    )
    effective_width_m = purlin_width_m * _positive(
        shear_effective_width_factor,
        "shear_effective_width_factor",
    )
    shear_resistance_n = (
        design_shear_strength_pa * effective_width_m * purlin_height_m / 1.5
    )
    design_compression_perpendicular_pa = (
        _positive(
            compression_perpendicular_mpa,
            "compression_perpendicular_mpa",
        )
        * 1e6
        * design_strength_multiplier
        * _positive(bearing_strength_factor, "bearing_strength_factor")
    )

    def bearing_resistance(width_m: float, length_mm: float) -> float:
        return (
            design_compression_perpendicular_pa
            * width_m
            * length_mm
            / 1000
        )

    bearing_resistance_n = bearing_resistance(
        purlin_width_m,
        purlin_bearing_length_mm
    )

    maximum_positive_moment_nm = max(
        design_response.span_positive_moments_nm
    )
    maximum_negative_moment_nm = abs(min(design_response.support_moments_nm))
    maximum_shear_n = max(design_response.span_max_abs_shears_n)
    maximum_reaction_n = max(
        abs(reaction) for reaction in design_response.support_reactions_n
    )
    positive_bending_utilization = (
        maximum_positive_moment_nm / bending_resistance_nm
    )
    negative_bending_utilization = (
        maximum_negative_moment_nm / bending_resistance_nm
    )
    shear_utilization = maximum_shear_n / shear_resistance_n
    bearing_utilization = maximum_reaction_n / bearing_resistance_n
    bending_check_name = (
        "positive bending" if len(spans) == 3 else "bending"
    )
    strength_utilizations = {
        bending_check_name: positive_bending_utilization,
        "shear": shear_utilization,
        "bearing": bearing_utilization,
    }
    if len(spans) == 3:
        strength_utilizations["negative bending"] = (
            negative_bending_utilization
        )
    governing_strength_check = max(
        strength_utilizations,
        key=strength_utilizations.__getitem__,
    )

    return PurlinCheckResult(
        span_lengths_m=spans,
        upper_rafter_length_m=upper_length_m,
        lower_rafter_span_m=lower_span_m,
        tributary_slope_width_m=tributary_slope_width_m,
        tributary_horizontal_width_m=tributary_horizontal_width_m,
        roof_layer_line_mass_kg_m=roof_layer_line_mass_kg_m,
        rafter_line_mass_kg_m=rafter_line_mass_kg_m,
        additional_permanent_load_kn_m=extra_line_load_kn_m,
        purlin_self_mass_kg_m=purlin_self_mass_kg_m,
        permanent_line_load_kn_m=permanent_line_load_kn_m,
        roof_snow_line_load_kn_m=roof_snow_line_load_kn_m,
        immediate_response=immediate_response,
        final_response=final_response,
        design_response=design_response,
        deflection_limits_m=deflection_limits_m,
        immediate_deflection_utilizations=immediate_utilizations,
        final_deflection_utilizations=final_utilizations,
        maximum_roof_snow_immediate_kn_m2=min(immediate_snow_capacities),
        maximum_roof_snow_final_kn_m2=min(final_snow_capacities),
        bending_resistance_nm=bending_resistance_nm,
        shear_resistance_n=shear_resistance_n,
        bearing_resistance_n=bearing_resistance_n,
        positive_bending_utilization=positive_bending_utilization,
        negative_bending_utilization=negative_bending_utilization,
        shear_utilization=shear_utilization,
        bearing_utilization=bearing_utilization,
        governing_strength_check=governing_strength_check,
        governing_strength_utilization=strength_utilizations[
            governing_strength_check
        ],
        missing_roof_layers=tuple(missing_roof_layers),
    )


def _status(utilization: float) -> str:
    return "PASS" if utilization < 1 else "FAIL"


def _status_cz(utilization: float) -> str:
    return "VYHOVUJE" if utilization < 1 else "NEVYHOVUJE"


RafterReportCase: TypeAlias = tuple[str, float, float, RoofCheckResult]

_REPORT_ROOF_LAYER_NAMES_CZ = {
    "Roof tiles": "Střešní krytina",
    "Tile battens": "Střešní latě",
    "Counter battens": "Kontralatě",
    "MDF": "Dřevovláknitá deska (MDF)",
    "vata": "Minerální vata",
    "OSB": "OSB deska",
    "Installation battens/services": "Instalační rošt a rozvody",
    "Gypsum plasterboard": "Sádrokarton",
}


def _rafter_report_case_status(
    check: RoofCheckResult,
    *,
    include_creep: bool = False,
) -> str:
    """Return the status for the checks included in the PDF report."""
    utilizations = [
        check.characteristic_deflection_utilization,
        check.bending_utilization,
        check.shear_utilization,
        check.bearing_utilization,
    ]
    if include_creep:
        utilizations.append(check.final_deflection_utilization)
    has_failure = max(utilizations) >= 1
    is_incomplete = bool(check.missing_roof_layers)
    if has_failure and is_incomplete:
        return "FAIL; CHECK INCOMPLETE"
    if has_failure:
        return "FAIL"
    if is_incomplete:
        return "CHECK INCOMPLETE"
    return "PASS"


def add_roof_load_table(
    report: CalculationReport,
    roof_layers_kg_m2: Mapping[str, float | None],
    *,
    snow_load_kn_m2: float,
    snow_load_standard: str = REPORT_SNOW_LOAD_STANDARD,
    snow_load_zone: int = REPORT_SNOW_LOAD_ZONE,
) -> None:
    """Append the report-wide roof-layer permanent-load table."""
    rows: list[tuple[str, str, str]] = []
    total_mass_kg_m2 = 0.0
    has_missing_layer = False

    snow_load = _non_negative(snow_load_kn_m2, "snow_load_kn_m2")
    snow_load_text = f"{snow_load:.2f}".replace(".", ",")
    if snow_load_zone <= 0:
        raise ValueError("snow_load_zone must be greater than zero")
    if not snow_load_standard.strip():
        raise ValueError("snow_load_standard must not be empty")

    for supplied_name, supplied_mass in roof_layers_kg_m2.items():
        display_name = _REPORT_ROOF_LAYER_NAMES_CZ.get(
            supplied_name,
            supplied_name,
        )
        if supplied_mass is None:
            has_missing_layer = True
            rows.append((display_name, "NEZADÁNO", "NEZADÁNO"))
            continue

        mass_kg_m2 = _non_negative(
            supplied_mass,
            f'roof layer "{supplied_name}" mass',
        )
        total_mass_kg_m2 += mass_kg_m2
        rows.append(
            (
                display_name,
                f"{mass_kg_m2:.1f}",
                f"{mass_kg_m2 * GRAVITY_M_S2 / 1000:.3f}",
            )
        )

    total_label = "Stálé zatížení celkem"
    if has_missing_layer:
        total_label = "Součet zadaných vrstev (neúplný)"
    rows.append(
        (
            total_label,
            f"{total_mass_kg_m2:.1f}",
            f"{total_mass_kg_m2 * GRAVITY_M_S2 / 1000:.3f}",
        )
    )

    report.add_table(
        "Zatížení střechy",
        column_labels=(
            "Vrstva",
            "Hmotnost [kg/m²]",
            "gk [kN/m²]",
        ),
        rows=rows,
        column_widths=(0.50, 0.22, 0.28),
        intro_lines=(
            f"Zatížení sněhem dle {snow_load_standard}: "
            f"{snow_load_zone}. sněhová oblast, "
            f"sk = {snow_load_text} kN/m².",
            "Hmotnosti vrstev jsou vztaženy k 1 m² skutečné šikmé "
            "plochy střechy.",
            f"Přepočet: gk = m × g / 1000; g = {GRAVITY_M_S2:g} m/s².",
        ),
        bold_last_row=True,
        footer_title="Předběžný statický výpočet střechy",
        page_label="Strana",
    )


def add_rafter_report(
    report: CalculationReport,
    *,
    width_mm: float,
    height_mm: float,
    rafter_spacing_m: float,
    deflection_ratio: float,
    elastic_modulus_gpa: float,
    timber_density_kg_m3: float,
    snow_load_kn_m2: float,
    roof_layers_kg_m2: Mapping[str, float | None],
    rafter_checks: Sequence[RafterReportCase],
    timber_grade: TimberGrade = _TIMBER_GRADES["c24"],
    include_creep: bool = False,
    bearing_length_mm: float = 50.0,
) -> None:
    """Append one or more traceable rafter checks to an open PDF report."""
    if not rafter_checks:
        raise ValueError("rafter_checks must contain at least one case")

    width_m = _positive(width_mm, "width_mm") / 1000
    height_m = _positive(height_mm, "height_mm") / 1000
    spacing_m = _positive(rafter_spacing_m, "rafter_spacing_m")
    _positive(elastic_modulus_gpa, "elastic_modulus_gpa")
    density = _positive(timber_density_kg_m3, "timber_density_kg_m3")
    bearing_length = _positive(bearing_length_mm, "bearing_length_mm")
    snow_load = _non_negative(snow_load_kn_m2, "snow_load_kn_m2")
    deflection_ratio = _positive(deflection_ratio, "deflection_ratio")

    known_layer_total_kg_m2 = 0.0
    for name, mass in roof_layers_kg_m2.items():
        if mass is not None:
            known_layer_total_kg_m2 += _non_negative(
                mass,
                f'roof layer "{name}" mass',
            )
    roof_layer_surface_load_kn_m2 = (
        known_layer_total_kg_m2 * GRAVITY_M_S2 / 1000
    )

    for name, supplied_span_m, angle_degrees, check in rafter_checks:
        span_m = _positive(supplied_span_m, f"{name} support span")
        angle = _roof_angle(angle_degrees)
        result = check.rafter
        layer_transverse_n_per_m = (
            check.permanent_transverse_n_per_m
            - result.self_transverse_n_per_m
        )
        design_strength_multiplier = (
            TIMBER_MODIFICATION_FACTOR / TIMBER_MATERIAL_PARTIAL_FACTOR
        )
        bending_strength_mpa = (
            timber_grade.bending_strength_mpa * design_strength_multiplier
        )
        shear_strength_mpa = (
            timber_grade.shear_strength_mpa * design_strength_multiplier
        )
        compression_parallel_strength_mpa = (
            timber_grade.compression_parallel_mpa
            * design_strength_multiplier
        )
        compression_perpendicular_strength_mpa = (
            timber_grade.compression_perpendicular_mpa
            * design_strength_multiplier
        )
        bearing_strength_mpa = check.design_bearing_strength_pa / 1e6
        bearing_area_m2 = check.bearing_area_m2

        report.add_sections(
            name,
            (
                (
                    "Geometrie a průřezové charakteristiky",
                    (
                        f"Materiál: {timber_grade.name}; "
                        f"E = {elastic_modulus_gpa:.2f} GPa; "
                        f"fm,k = {timber_grade.bending_strength_mpa:g} MPa; "
                        f"fv,k = {timber_grade.shear_strength_mpa:g} MPa; "
                        f"fc,0,k = "
                        f"{timber_grade.compression_parallel_mpa:g} MPa; "
                        f"fc,90,k = "
                        f"{timber_grade.compression_perpendicular_mpa:g} MPa.",
                        f"Rozpětí mezi podporami L = {span_m:.3f} m "
                        "podél krokve",
                        f"Sklon střechy α = {angle:.2f}°; cos α = "
                        f"{result.roof_cosine:.5f}",
                        f"b = {width_m:.3f} m; h = {height_m:.3f} m",
                        f"I = b h³ / 12 = "
                        f"{result.second_moment_m4:.8e} m⁴",
                        f"W = b h² / 6 = "
                        f"{result.section_modulus_m3:.8e} m³",
                    ),
                ),
                (
                    "Charakteristická liniová zatížení kolmá ke krokvi",
                    (
                        f"Stálé plošné zatížení střešních vrstev gk = "
                        f"{roof_layer_surface_load_kn_m2:.3f} kN/m² "
                        f"({known_layer_total_kg_m2:.1f} kg/m²).",
                        f"Maximální osová vzdálenost krokví a = {spacing_m:.3f} m.",
                        "Pro jednu krokev tedy použijeme liniové zatížení "
                        "vrstev kolmé ke krokvi:",
                        f"qG,k,vrstvy = gk × a × cos α = "
                        f"{roof_layer_surface_load_kn_m2:.3f} × "
                        f"{spacing_m:.3f} × {result.roof_cosine:.5f} = "
                        f"{layer_transverse_n_per_m / 1000:.3f} kN/m.",
                        f"Vlastní tíha krokve qG,k,krokev = "
                        f"{width_m:.3f} × {height_m:.3f} × "
                        f"{density:.1f} × g × cos α = "
                        f"{result.self_transverse_n_per_m / 1000:.3f} kN/m.",
                        f"Stálé liniové zatížení celkem qG,k = "
                        f"{check.permanent_transverse_n_per_m / 1000:.3f} "
                        "kN/m.",
                        f"Zatížení od sněhu qS,k = sk × a × cos² α = "
                        f"{result.snow_transverse_n_per_m / 1000:.3f} kN/m",
                        f"Charakteristické zatížení celkem qk = qG,k + qS,k = "
                        f"{check.characteristic_transverse_n_per_m / 1000:.3f} "
                        "kN/m",
                    ),
                ),
                (
                    "Posouzení - namáhání ohybem",
                    (
                        "Mezní stav únosnosti (MSÚ).",
                        f"Návrhové liniové zatížení qd = γG qG,k + "
                        f"γQ qS,k = "
                        f"{check.design_transverse_n_per_m / 1000:.3f} kN/m",
                        f"Návrhový ohybový moment MEd = qd L² / 8 = "
                        f"{check.design_bending_moment_nm / 1000:.3f} kNm",
                        f"Průřezový modul W = "
                        f"{result.section_modulus_m3:.8e} m³",
                        f"Návrhová pevnost v ohybu fm,d = "
                        f"fm,k × kmod / γM = {bending_strength_mpa:.2f} MPa",
                        f"Mezní hodnota MRd = fm,d × W = "
                        f"{check.bending_resistance_nm / 1000:.3f} kNm",
                        f"{check.design_bending_moment_nm / 1000:.3f} kNm "
                        f"< {check.bending_resistance_nm / 1000:.3f} kNm, "
                        f"{_status_cz(check.bending_utilization)}",
                    ),
                ),
                (
                    "Posouzení - namáhání smykem",
                    (
                        "Mezní stav únosnosti (MSÚ).",
                        f"Návrhová posouvající síla VEd = qd L / 2 = "
                        f"{check.design_shear_force_n / 1000:.3f} kN",
                        f"Návrhová pevnost ve smyku fv,d = "
                        f"fv,k × kmod / γM = {shear_strength_mpa:.2f} MPa",
                        f"Účinná šířka bef = kcr × b = "
                        f"{SHEAR_EFFECTIVE_WIDTH_FACTOR:g} × "
                        f"{width_m * 1000:.0f} mm",
                        f"Mezní hodnota VRd = fv,d × kcr × b × h / 1,5 = "
                        f"{check.shear_resistance_n / 1000:.3f} kN",
                        f"{check.design_shear_force_n / 1000:.3f} kN "
                        f"< {check.shear_resistance_n / 1000:.3f} kN, "
                        f"{_status_cz(check.shear_utilization)}",
                    ),
                ),
                (
                    "Posouzení - tlak šikmo k vláknům v uložení",
                    (
                        "Mezní stav únosnosti (MSÚ), tlak šikmo k vláknům.",
                        f"Úhel síly k vláknům β = 90° − α = "
                        f"{check.bearing_angle_degrees:.2f}°.",
                        f"Návrhová svislá reakce Fc,β,Ed = VEd / cos α = "
                        f"{check.design_shear_force_n / 1000:.3f} / "
                        f"{result.roof_cosine:.5f} = "
                        f"{check.design_support_reaction_n / 1000:.3f} kN.",
                        f"Návrhové pevnosti fc,0,d = "
                        f"{compression_parallel_strength_mpa:.2f} MPa; "
                        f"fc,90,d = "
                        f"{compression_perpendicular_strength_mpa:.2f} MPa; "
                        f"kc,90 = {BEARING_STRENGTH_FACTOR:g}.",
                        "fc,β,d = fc,0,d / [(fc,0,d / (kc,90 × fc,90,d)) "
                        "× sin² β + cos² β] = "
                        f"{bearing_strength_mpa:.2f} MPa",
                        f"Plocha uložení A = b × l = "
                        f"{width_m * 1000:.0f} × {bearing_length:g} = "
                        f"{bearing_area_m2 * 1e6:.0f} mm²",
                        f"Mezní hodnota Rc,β,d = fc,β,d × A = "
                        f"{check.bearing_resistance_n / 1000:.3f} kN",
                        f"{check.design_support_reaction_n / 1000:.3f} kN "
                        f"< {check.bearing_resistance_n / 1000:.3f} kN, "
                        f"{_status_cz(check.bearing_utilization)}",
                        "Samostatné posouzení zářezu krokve není zahrnuto.",
                    ),
                ),
                (
                    "Posouzení - okamžitý průhyb",
                    (
                        "Mezní stav použitelnosti (MSP).",
                        f"Charakteristické liniové zatížení qk = qG,k + "
                        f"qS,k = "
                        f"{check.characteristic_transverse_n_per_m / 1000:.3f} "
                        "kN/m",
                        f"Modul pružnosti E = {elastic_modulus_gpa:.2f} GPa",
                        f"Moment setrvačnosti I = "
                        f"{result.second_moment_m4:.8e} m⁴",
                        f"Průhyb od stálého zatížení wG,inst = "
                        f"{check.permanent_immediate_deflection_m * 1000:.2f} "
                        "mm",
                        f"Průhyb od sněhu wS,inst = "
                        f"{check.snow_immediate_deflection_m * 1000:.2f} mm",
                        f"Celkový průhyb winst = 5 qk L⁴ / (384 E I) = "
                        f"{check.characteristic_deflection_m * 1000:.2f} mm",
                        f"Mezní hodnota wlim = L/{deflection_ratio:g} = "
                        f"{result.maximum_deflection_m * 1000:.2f} mm",
                        f"{check.characteristic_deflection_m * 1000:.2f} mm "
                        f"< {result.maximum_deflection_m * 1000:.2f} mm, "
                        f"{_status_cz(check.characteristic_deflection_utilization)}",
                    ),
                ),
                *(
                    (
                        (
                            "Posouzení - konečný průhyb včetně dotvarování",
                            (
                                "Mezní stav použitelnosti (MSP).",
                                f"Součinitel dotvarování kdef = "
                                f"{TIMBER_CREEP_FACTOR:g}",
                                f"Kombinační součinitel sněhu ψ2 = "
                                f"{SNOW_CREEP_COMBINATION_FACTOR:g}",
                                "wfin = wG,inst × (1 + kdef) + "
                                "wS,inst × (1 + ψ2 × kdef)",
                                f"wfin = "
                                f"{check.final_deflection_m * 1000:.2f} mm",
                                f"Mezní hodnota wlim = L/"
                                f"{deflection_ratio:g} = "
                                f"{result.maximum_deflection_m * 1000:.2f} mm",
                                f"{check.final_deflection_m * 1000:.2f} mm "
                                f"< "
                                f"{result.maximum_deflection_m * 1000:.2f} mm, "
                                f"{_status_cz(check.final_deflection_utilization)}",
                            ),
                        ),
                    )
                    if include_creep
                    else ()
                ),
            ),
            footer_title="Předběžný statický výpočet střechy",
            page_label="Strana",
            continuation_label="pokračování",
        )


def add_roof_report_overview(
    report: CalculationReport,
    *,
    snow_load: float,
    roof_layers: Mapping[str, float | None],
    include_creep: bool,
) -> None:
    """Append the common design basis and roof-load table once."""
    report.add_sections(
        "Roof calculation – design basis",
        (
            (
                "Purpose and structural models",
                (
                    "Preliminary verification of timber roof members.",
                    "Rafters are modelled as simply supported sloping beams; "
                    "purlins are modelled either as one simply supported "
                    "piece or as one uniform member continuous over four "
                    "supports.",
                    "Snow is a vertical action per horizontal roof projection; "
                    "roof-layer masses are per actual sloping surface.",
                ),
            ),
            (
                "Standards and characteristic material values",
                (
                    f"Basis and combinations of actions: "
                    f"{REPORT_BASIS_STANDARD}.",
                    f"Timber resistance and deformation model: "
                    f"{REPORT_TIMBER_STANDARD}.",
                    f"Characteristic strengths fm,k, fv,k, fc,0,k and "
                    f"fc,90,k and mean modulus E0,mean for C22/C24: "
                    f"{REPORT_TIMBER_GRADES_STANDARD}.",
                    "The strength class values used by each member are "
                    "printed again in its analysis chapter.",
                ),
            ),
            (
                "Ultimate limit state (ULS) factors and criteria",
                (
                    f"Fundamental action combination used here: qd = "
                    f"γG Gk + γQ Sk, with γG = {PERMANENT_LOAD_FACTOR:g} "
                    f"and γQ = {SNOW_LOAD_FACTOR:g}.",
                    "Only permanent action and snow as the leading variable "
                    "action are included in this preliminary model.",
                    f"Service class 2 and a medium-term governing action are "
                    f"assumed: kmod = {TIMBER_MODIFICATION_FACTOR:g}; "
                    f"γM = {TIMBER_MATERIAL_PARTIAL_FACTOR:g}.",
                    "Design strengths are calculated from characteristic "
                    "strengths as fd = kmod × fk / γM.",
                    "Bending criterion: MEd < MRd = fm,d × W.",
                    f"Shear criterion: VEd < VRd = fv,d × kcr × b × h / "
                    f"1.5, with kcr = {SHEAR_EFFECTIVE_WIDTH_FACTOR:g}.",
                    f"Bearing uses the entered contact area A = b × l and "
                    f"kc,90 = {BEARING_STRENGTH_FACTOR:g}. Rafters are "
                    "checked in compression at an angle to grain; purlins "
                    "are checked perpendicular to grain.",
                    "Every ULS result is accepted only when the design action "
                    "Ed is strictly smaller than the design resistance Rd.",
                ),
            ),
            (
                "Serviceability scope",
                (
                    "The deflection limit L/300 is a selected project "
                    "criterion supplied to the checks; it is not a timber "
                    "strength-class property.",
                    "The same strict criterion w < L/300 is applied to "
                    "immediate deflection in every chapter.",
                    (
                        "Final deflection is also checked against L/300: "
                        "wfin = wG,inst(1 + kdef) + "
                        "wS,inst(1 + ψ2 kdef), with "
                        f"kdef = {TIMBER_CREEP_FACTOR:g} and "
                        f"ψ2 = {SNOW_CREEP_COMBINATION_FACTOR:g}."
                        if include_creep
                        else "Final deflection including creep is omitted "
                        "from this report."
                    ),
                ),
            ),
            (
                "Explicit preliminary-model assumptions",
                (
                    f"Solid-timber density for self-weight is "
                    f"{TIMBER_DENSITY_KG_M3:g} kg/m³ and g = "
                    f"{GRAVITY_M_S2:g} m/s².",
                    "kcr, kc,90, load-duration class, service class, ψ2, "
                    "bearing lengths and nationally determined parameters "
                    "must be confirmed for the final project and chosen "
                    "standard edition.",
                    "The model does not verify connections, notches, member "
                    "stability, wind/uplift, concentrated loads or all "
                    "possible asymmetric snow arrangements.",
                ),
            ),
        ),
    )
    add_roof_load_table(
        report,
        roof_layers,
        snow_load_kn_m2=snow_load,
    )



def _resolve_timber_grade(material: str | TimberGrade) -> TimberGrade:
    if isinstance(material, TimberGrade):
        return material
    if not isinstance(material, str):
        raise TypeError("material must be 'c22', 'c24', or a TimberGrade")
    try:
        return _TIMBER_GRADES[material.strip().lower()]
    except KeyError as error:
        choices = ", ".join(sorted(_TIMBER_GRADES))
        raise ValueError(f"unknown timber material; choose {choices}") from error


class RoofCalculationSession:
    """One terminal run and the PDF assembled from the same results."""

    def __init__(
        self,
        report: CalculationReport,
        *,
        include_creep: bool,
    ) -> None:
        self.report = report
        self.include_creep = include_creep
        self.entries: list[
            tuple[str, str, RoofCheckResult | PurlinCheckResult]
        ] = []
        self._snow_load: float | None = None
        self._roof_layers: dict[str, float | None] | None = None

    def prepare_inputs(
        self,
        *,
        snow_load: float,
        roof_layers: Mapping[str, float | None],
    ) -> None:
        normalized_snow = _non_negative(snow_load, "snow_load")
        normalized_layers = dict(roof_layers)
        if self._snow_load is None:
            self._snow_load = normalized_snow
            self._roof_layers = normalized_layers
            add_roof_report_overview(
                self.report,
                snow_load=normalized_snow,
                roof_layers=normalized_layers,
                include_creep=self.include_creep,
            )
            return
        if normalized_snow != self._snow_load:
            raise ValueError(
                "all checks in one report must use the same snow_load"
            )
        if normalized_layers != self._roof_layers:
            raise ValueError(
                "all checks in one report must use the same roof_layers"
            )

    def add_result(
        self,
        title: str,
        kind: str,
        result: RoofCheckResult | PurlinCheckResult,
    ) -> None:
        self.entries.append((title, kind, result))

    def _entry_status(
        self,
        kind: str,
        result: RoofCheckResult | PurlinCheckResult,
    ) -> str:
        if kind == "rafter":
            assert isinstance(result, RoofCheckResult)
            return _rafter_report_case_status(
                result,
                include_creep=self.include_creep,
            )
        assert isinstance(result, PurlinCheckResult)
        return _purlin_report_status(
            result,
            include_creep=self.include_creep,
        )

    def finish(self) -> None:
        if not self.entries:
            return
        status_lines = tuple(
            f"{title}: {self._entry_status(kind, result)}"
            for title, kind, result in self.entries
        )
        self.report.add_sections(
            "Souhrn výsledků",
            (("Posouzené prvky", status_lines),),
            footer_title="Předběžný statický výpočet střechy",
            page_label="Strana",
        )
        print()
        print("OVERALL RESULT:")
        for line in status_lines:
            print(f"  {line}")


_ACTIVE_SESSION: RoofCalculationSession | None = None


@contextmanager
def calculation_report(
    path: str | Path = "rafter_load_report.pdf",
    *,
    include_creep: bool = True,
):
    """Collect check calls into one PDF while printing the same calculations."""
    global _ACTIVE_SESSION
    if _ACTIVE_SESSION is not None:
        raise RuntimeError("calculation_report contexts cannot be nested")
    report_path = Path(path)
    with CalculationReport(
        report_path,
        document_title="Preliminary roof structural calculation",
    ) as report:
        session = RoofCalculationSession(
            report,
            include_creep=include_creep,
        )
        _ACTIVE_SESSION = session
        try:
            yield session
        except Exception:
            raise
        else:
            session.finish()
        finally:
            _ACTIVE_SESSION = None
    print(f"PDF REPORT: {report_path} ({report.page_count} pages)")


def _active_session() -> RoofCalculationSession:
    if _ACTIVE_SESSION is None:
        raise RuntimeError(
            "check functions must be called inside calculation_report()"
        )
    return _ACTIVE_SESSION


def check_rafter(
    *,
    title: str,
    material: str | TimberGrade,
    width: float,
    height: float,
    span: float,
    spacing: float,
    roof_angle: float,
    max_deflection: float,
    snow_load: float,
    roof_layers: Mapping[str, float | None] | None = None,
    bearing_length: float = 0.05,
    elastic_modulus: float | None = None,
    timber_density: float = TIMBER_DENSITY_KG_M3,
) -> RoofCheckResult:
    """Check one rafter, print diagnostics, and append its PDF pages.

    All geometric arguments use metres. max_deflection=300 means L/300.
    """
    session = _active_session()
    normalized_title = str(title).strip()
    if not normalized_title:
        raise ValueError("title must be a non-empty string")
    grade = _resolve_timber_grade(material)
    layers = ROOF_LAYERS_KG_M2 if roof_layers is None else roof_layers
    width_mm = _positive(width, "width") * 1000
    height_mm = _positive(height, "height") * 1000
    bearing_length_mm = _positive(bearing_length, "bearing_length") * 1000
    modulus = (
        grade.elastic_modulus_gpa
        if elastic_modulus is None
        else _positive(elastic_modulus, "elastic_modulus")
    )
    check = calculate_roof_check(
        width_mm=width_mm,
        height_mm=height_mm,
        support_span_m=span,
        deflection_ratio=max_deflection,
        elastic_modulus_gpa=modulus,
        timber_density_kg_m3=timber_density,
        roof_angle_degrees=roof_angle,
        rafter_spacing_m=spacing,
        snow_load_kn_m2=snow_load,
        roof_layers_kg_m2=layers,
        bending_strength_mpa=grade.bending_strength_mpa,
        shear_strength_mpa=grade.shear_strength_mpa,
        compression_parallel_mpa=grade.compression_parallel_mpa,
        compression_perpendicular_mpa=(
            grade.compression_perpendicular_mpa
        ),
        bearing_length_mm=bearing_length_mm,
    )
    session.prepare_inputs(snow_load=snow_load, roof_layers=layers)
    add_rafter_report(
        session.report,
        width_mm=width_mm,
        height_mm=height_mm,
        rafter_spacing_m=spacing,
        deflection_ratio=max_deflection,
        elastic_modulus_gpa=modulus,
        timber_density_kg_m3=timber_density,
        snow_load_kn_m2=snow_load,
        roof_layers_kg_m2=layers,
        rafter_checks=((normalized_title, span, roof_angle, check),),
        timber_grade=grade,
        include_creep=session.include_creep,
        bearing_length_mm=bearing_length_mm,
    )
    _print_roof_check(
        normalized_title,
        support_span_m=span,
        roof_angle_degrees=roof_angle,
        deflection_ratio=max_deflection,
        check=check,
        timber_grade_name=grade.name,
    )
    session.add_result(normalized_title, "rafter", check)
    return check


def _add_purlin_evaluation(
    report: CalculationReport,
    *,
    chapter_title: str,
    material: TimberGrade,
    width_mm: float,
    height_mm: float,
    deflection_ratio: float,
    elastic_modulus_gpa: float,
    bearing_length_mm: float,
    include_creep: bool,
    check: PurlinCheckResult,
) -> None:
    """Append a simple- or continuous-purlin evaluation."""
    is_continuous = len(check.span_lengths_m) == 3
    if len(check.span_lengths_m) not in (1, 3):
        raise ValueError("purlin report needs one or three spans")
    member_name = "spojité vaznice" if is_continuous else "vaznice"
    field_suffix = ", pole {index}" if is_continuous else ""
    purlin_width_mm = _positive(width_mm, "width_mm")
    purlin_height_mm = _positive(height_mm, "height_mm")
    purlin_width_m = purlin_width_mm / 1000
    purlin_height_m = purlin_height_mm / 1000
    second_moment_m4 = purlin_width_m * purlin_height_m**3 / 12
    section_modulus_m3 = purlin_width_m * purlin_height_m**2 / 6
    ratio = _positive(deflection_ratio, "deflection_ratio")
    bearing_length = _positive(bearing_length_mm, "bearing_length_mm")
    grade = _resolve_timber_grade(material)
    design_strength_multiplier = (
        TIMBER_MODIFICATION_FACTOR / TIMBER_MATERIAL_PARTIAL_FACTOR
    )
    bending_strength_mpa = (
        grade.bending_strength_mpa * design_strength_multiplier
    )
    shear_strength_mpa = (
        grade.shear_strength_mpa * design_strength_multiplier
    )
    compression_strength_mpa = (
        grade.compression_perpendicular_mpa
        * design_strength_multiplier
        * BEARING_STRENGTH_FACTOR
    )
    design_line_load_kn_m = (
        PERMANENT_LOAD_FACTOR * check.permanent_line_load_kn_m
        + SNOW_LOAD_FACTOR * check.roof_snow_line_load_kn_m
    )
    maximum_positive_moment_nm = max(
        check.design_response.span_positive_moments_nm
    )
    maximum_negative_moment_nm = abs(
        min(check.design_response.support_moments_nm)
    )
    maximum_shear_n = max(check.design_response.span_max_abs_shears_n)
    maximum_reaction_n = max(
        abs(value) for value in check.design_response.support_reactions_n
    )

    sections: list[ReportSection] = [
        (
            "Geometrie, materiál a zatížení",
            (
                f"Materiál: {grade.name}; E = {elastic_modulus_gpa:.2f} GPa.",
                f"Charakteristické pevnosti: fm,k = "
                f"{grade.bending_strength_mpa:g} MPa; fv,k = "
                f"{grade.shear_strength_mpa:g} MPa; fc,90,k = "
                f"{grade.compression_perpendicular_mpa:g} MPa.",
                f"Průřez {member_name} b × h = "
                f"{purlin_width_mm:g} × {purlin_height_mm:g} mm.",
                f"I = b h³ / 12 = {second_moment_m4:.8e} m⁴; "
                f"W = b h² / 6 = {section_modulus_m3:.8e} m³.",
                "Rozpětí L = "
                + " + ".join(f"{span:g} m" for span in check.span_lengths_m)
                + ".",
                f"Plocha střechy připadající na vaznici: "
                f"{check.tributary_slope_width_m:.3f} m po sklonu; "
                f"{check.tributary_horizontal_width_m:.3f} m vodorovně.",
                f"Stálé liniové zatížení gk = "
                f"{check.permanent_line_load_kn_m:.3f} kN/m.",
                f"Zatížení sněhem sk = "
                f"{check.roof_snow_line_load_kn_m:.3f} kN/m.",
                f"Návrhové liniové zatížení qd = γG gk + γQ sk = "
                f"{design_line_load_kn_m:.3f} kN/m.",
                f"Použité součinitele: γG = {PERMANENT_LOAD_FACTOR:g}; "
                f"γQ = {SNOW_LOAD_FACTOR:g}; "
                f"kmod = {TIMBER_MODIFICATION_FACTOR:g}; "
                f"γM = {TIMBER_MATERIAL_PARTIAL_FACTOR:g}.",
                f"Mez průhybu = L/{ratio:g}.",
                *(
                    (
                        "Výpočet je neúplný; chybí hmotnosti vrstev: "
                        + ", ".join(check.missing_roof_layers),
                    )
                    if check.missing_roof_layers
                    else ()
                ),
            ),
        ),
    ]

    for index, (
        span,
        deflection,
        limit,
        utilization,
    ) in enumerate(
        zip(
            check.span_lengths_m,
            check.immediate_response.span_max_abs_deflections_m,
            check.deflection_limits_m,
            check.immediate_deflection_utilizations,
        ),
        start=1,
    ):
        sections.append(
            (
                f"Posouzení - okamžitý průhyb {member_name}"
                + field_suffix.format(index=index),
                (
                    "Mezní stav použitelnosti (MSP).",
                    f"Rozpětí L = {span:.3f} m.",
                    f"Okamžitý průhyb winst = {deflection * 1000:.2f} mm.",
                    f"Mezní hodnota wlim = L/{ratio:g} = "
                    f"{limit * 1000:.2f} mm.",
                    f"{deflection * 1000:.2f} mm < "
                    f"{limit * 1000:.2f} mm, "
                    f"{_status_cz(utilization)}",
                ),
            )
        )

    if include_creep:
        for index, (
            span,
            deflection,
            limit,
            utilization,
        ) in enumerate(
            zip(
                check.span_lengths_m,
                check.final_response.span_max_abs_deflections_m,
                check.deflection_limits_m,
                check.final_deflection_utilizations,
            ),
            start=1,
        ):
            sections.append(
                (
                    f"Posouzení - konečný průhyb {member_name}"
                    + field_suffix.format(index=index),
                    (
                        "Mezní stav použitelnosti (MSP), včetně dotvarování.",
                        f"Rozpětí L = {span:.3f} m.",
                        f"Konečný průhyb wfin = "
                        f"{deflection * 1000:.2f} mm.",
                        f"Mezní hodnota wlim = L/{ratio:g} = "
                        f"{limit * 1000:.2f} mm.",
                        f"{deflection * 1000:.2f} mm < "
                        f"{limit * 1000:.2f} mm, "
                        f"{_status_cz(utilization)}",
                    ),
                )
            )

    sections.extend(
        (
            (
                f"Posouzení - kladný ohybový moment {member_name}",
                (
                    "Mezní stav únosnosti (MSÚ).",
                    f"Návrhová pevnost fm,d = fm,k × kmod / γM = "
                    f"{bending_strength_mpa:.2f} MPa.",
                    f"Maximální kladný moment MEd,+ = "
                    f"{maximum_positive_moment_nm / 1000:.3f} kNm.",
                    f"Mezní hodnota MRd = fm,d × W = "
                    f"{check.bending_resistance_nm / 1000:.3f} kNm.",
                    f"{maximum_positive_moment_nm / 1000:.3f} kNm < "
                    f"{check.bending_resistance_nm / 1000:.3f} kNm, "
                    f"{_status_cz(check.positive_bending_utilization)}",
                ),
            ),
            *(
                (
                    (
                        f"Posouzení - záporný ohybový moment {member_name}",
                        (
                            "Mezní stav únosnosti (MSÚ).",
                            f"Maximální záporný moment |MEd,-| = "
                            f"{maximum_negative_moment_nm / 1000:.3f} kNm.",
                            f"Mezní hodnota MRd = fm,d × W = "
                            f"{check.bending_resistance_nm / 1000:.3f} kNm.",
                            f"{maximum_negative_moment_nm / 1000:.3f} kNm < "
                            f"{check.bending_resistance_nm / 1000:.3f} kNm, "
                            f"{_status_cz(check.negative_bending_utilization)}",
                        ),
                    ),
                )
                if is_continuous
                else ()
            ),
            (
                f"Posouzení - namáhání {member_name} smykem",
                (
                    "Mezní stav únosnosti (MSÚ).",
                    f"Návrhová pevnost fv,d = fv,k × kmod / γM = "
                    f"{shear_strength_mpa:.2f} MPa.",
                    f"Maximální posouvající síla VEd = "
                    f"{maximum_shear_n / 1000:.3f} kN.",
                    f"Mezní hodnota VRd = fv,d × kcr × b × h / 1,5; "
                    f"kcr = {SHEAR_EFFECTIVE_WIDTH_FACTOR:g}; VRd = "
                    f"{check.shear_resistance_n / 1000:.3f} kN.",
                    f"{maximum_shear_n / 1000:.3f} kN < "
                    f"{check.shear_resistance_n / 1000:.3f} kN, "
                    f"{_status_cz(check.shear_utilization)}",
                ),
            ),
            (
                f"Posouzení - otlačení {member_name} v uložení",
                (
                    "Mezní stav únosnosti (MSÚ), tlak kolmo k vláknům.",
                    f"Návrhová pevnost fc,90,d = "
                    f"kc,90 × fc,90,k × kmod / γM = "
                    f"{compression_strength_mpa:.2f} MPa; "
                    f"kc,90 = {BEARING_STRENGTH_FACTOR:g}.",
                    f"Plocha uložení A = b × l = "
                    f"{purlin_width_mm:g} × {bearing_length:g} = "
                    f"{purlin_width_mm * bearing_length:.0f} mm².",
                    f"Maximální reakce Fc,90,Ed = "
                    f"{maximum_reaction_n / 1000:.3f} kN.",
                    f"Mezní hodnota Rc,90,d = fc,90,d × A = "
                    f"{check.bearing_resistance_n / 1000:.3f} kN.",
                    f"{maximum_reaction_n / 1000:.3f} kN < "
                    f"{check.bearing_resistance_n / 1000:.3f} kN, "
                    f"{_status_cz(check.bearing_utilization)}",
                ),
            ),
        )
    )

    report.add_sections(
        chapter_title,
        tuple(sections),
        footer_title="Předběžný statický výpočet střechy",
        page_label="Strana",
        continuation_label="pokračování",
    )


def _check_purlin(
    *,
    title: str,
    material: str | TimberGrade,
    width: float,
    height: float,
    spans: Sequence[float],
    rafter_length_above: float,
    lower_rafter_span: float,
    roof_angle: float,
    rafter_width: float,
    rafter_height: float,
    rafter_spacing: float,
    max_deflection: float,
    snow_load: float,
    roof_layers: Mapping[str, float | None] | None = None,
    additional_load: float = 0,
    bearing_length: float | None = None,
    elastic_modulus: float | None = None,
    timber_density: float = TIMBER_DENSITY_KG_M3,
) -> PurlinCheckResult:
    """Check one purlin, print diagnostics, and append its PDF pages.

    All geometric arguments use metres. max_deflection=300 means L/300.
    """
    session = _active_session()
    normalized_title = str(title).strip()
    if not normalized_title:
        raise ValueError("title must be a non-empty string")
    grade = _resolve_timber_grade(material)
    layers = ROOF_LAYERS_KG_M2 if roof_layers is None else roof_layers
    width_mm = _positive(width, "width") * 1000
    height_mm = _positive(height, "height") * 1000
    rafter_width_mm = _positive(rafter_width, "rafter_width") * 1000
    rafter_height_mm = _positive(rafter_height, "rafter_height") * 1000
    bearing_m = width if bearing_length is None else bearing_length
    bearing_length_mm = _positive(bearing_m, "bearing_length") * 1000
    modulus = (
        grade.elastic_modulus_gpa
        if elastic_modulus is None
        else _positive(elastic_modulus, "elastic_modulus")
    )
    check = calculate_purlin_check(
        width_mm=width_mm,
        height_mm=height_mm,
        support_spans_m=spans,
        upper_rafter_length_m=rafter_length_above,
        lower_rafter_span_m=lower_rafter_span,
        roof_angle_degrees=roof_angle,
        rafter_width_mm=rafter_width_mm,
        rafter_height_mm=rafter_height_mm,
        rafter_spacing_m=rafter_spacing,
        deflection_ratio=max_deflection,
        elastic_modulus_gpa=modulus,
        snow_load_kn_m2=snow_load,
        roof_layers_kg_m2=layers,
        additional_permanent_load_kn_m=additional_load,
        timber_density_kg_m3=timber_density,
        bending_strength_mpa=grade.bending_strength_mpa,
        shear_strength_mpa=grade.shear_strength_mpa,
        compression_perpendicular_mpa=(
            grade.compression_perpendicular_mpa
        ),
        bearing_length_mm=bearing_length_mm,
    )
    session.prepare_inputs(snow_load=snow_load, roof_layers=layers)
    _add_purlin_evaluation(
        session.report,
        chapter_title=normalized_title,
        material=grade,
        width_mm=width_mm,
        height_mm=height_mm,
        deflection_ratio=max_deflection,
        elastic_modulus_gpa=modulus,
        bearing_length_mm=bearing_length_mm,
        include_creep=session.include_creep,
        check=check,
    )
    _print_purlin_check(
        title=normalized_title,
        deflection_ratio=max_deflection,
        check=check,
        timber_grade_name=grade.name,
    )
    session.add_result(normalized_title, "purlin", check)
    return check


def check_purlin(
    *,
    title: str,
    material: str | TimberGrade,
    width: float,
    height: float,
    span: float,
    rafter_length_above: float,
    lower_rafter_span: float,
    roof_angle: float,
    rafter_width: float,
    rafter_height: float,
    rafter_spacing: float,
    max_deflection: float,
    snow_load: float,
    roof_layers: Mapping[str, float | None] | None = None,
    additional_load: float = 0,
    bearing_length: float | None = None,
    elastic_modulus: float | None = None,
    timber_density: float = TIMBER_DENSITY_KG_M3,
) -> PurlinCheckResult:
    """Check one simply supported purlin span between two supports."""
    return _check_purlin(
        title=title,
        material=material,
        width=width,
        height=height,
        spans=(span,),
        rafter_length_above=rafter_length_above,
        lower_rafter_span=lower_rafter_span,
        roof_angle=roof_angle,
        rafter_width=rafter_width,
        rafter_height=rafter_height,
        rafter_spacing=rafter_spacing,
        max_deflection=max_deflection,
        snow_load=snow_load,
        roof_layers=roof_layers,
        additional_load=additional_load,
        bearing_length=bearing_length,
        elastic_modulus=elastic_modulus,
        timber_density=timber_density,
    )


def check_continuous_purlin(
    *,
    title: str,
    material: str | TimberGrade,
    width: float,
    height: float,
    spans: tuple[float, float, float],
    rafter_length_above: float,
    lower_rafter_span: float,
    roof_angle: float,
    rafter_width: float,
    rafter_height: float,
    rafter_spacing: float,
    max_deflection: float,
    snow_load: float,
    roof_layers: Mapping[str, float | None] | None = None,
    additional_load: float = 0,
    bearing_length: float | None = None,
    elastic_modulus: float | None = None,
    timber_density: float = TIMBER_DENSITY_KG_M3,
) -> PurlinCheckResult:
    """Check one uniform purlin continuous across four supports."""
    if len(spans) != 3:
        raise ValueError("spans must contain exactly three spans")
    return _check_purlin(
        title=title,
        material=material,
        width=width,
        height=height,
        spans=spans,
        rafter_length_above=rafter_length_above,
        lower_rafter_span=lower_rafter_span,
        roof_angle=roof_angle,
        rafter_width=rafter_width,
        rafter_height=rafter_height,
        rafter_spacing=rafter_spacing,
        max_deflection=max_deflection,
        snow_load=snow_load,
        roof_layers=roof_layers,
        additional_load=additional_load,
        bearing_length=bearing_length,
        elastic_modulus=elastic_modulus,
        timber_density=timber_density,
    )



def _print_roof_check(
    name: str,
    *,
    support_span_m: float,
    roof_angle_degrees: float,
    deflection_ratio: float,
    check: RoofCheckResult,
    timber_grade_name: str = "C24",
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
        f"  Ultimate strength (ULS, preliminary {timber_grade_name}; "
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
            "Bearing at angle to grain",
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


def _print_purlin_check(
    *,
    title: str,
    deflection_ratio: float,
    check: PurlinCheckResult,
    timber_grade_name: str = "C24",
) -> None:
    """Print simple- or continuous-purlin results."""
    is_continuous = len(check.span_lengths_m) == 3
    print()
    print(f"{title}:")
    if is_continuous:
        print(
            "  Support spans: "
            + " + ".join(f"{span:g} m" for span in check.span_lengths_m)
        )
    else:
        print(f"  Support span: {check.span_lengths_m[0]:g} m")
    print(
        "  Rafter tributary length: "
        f"{check.upper_rafter_length_m:.3f} m above + "
        f"{check.lower_rafter_span_m / 2:.3f} m below = "
        f"{check.tributary_slope_width_m:.3f} m along the roof"
    )
    print(
        "  Horizontal snow tributary width: "
        f"{check.tributary_horizontal_width_m:.3f} m"
    )
    print(
        "  Transferred permanent mass: "
        f"roof layers {check.roof_layer_line_mass_kg_m:.1f} kg/m + "
        f"rafters {check.rafter_line_mass_kg_m:.1f} kg/m"
    )
    print(
        "  Additional permanent line load: "
        f"{check.additional_permanent_load_kn_m:.3f} kN/m; "
        f"purlin self-mass: {check.purlin_self_mass_kg_m:.1f} kg/m"
    )
    print(
        f"  Total permanent line load: {check.permanent_line_load_kn_m:.3f} "
        "kN/m vertical"
    )
    print(
        f"  Snow line load on purlin: {check.roof_snow_line_load_kn_m:.3f} "
        "kN/m vertical"
    )

    print("  Serviceability (SLS):")
    for index, (
        span,
        immediate_deflection,
        final_deflection,
        limit,
        immediate_utilization,
        final_utilization,
    ) in enumerate(
        zip(
            check.span_lengths_m,
            check.immediate_response.span_max_abs_deflections_m,
            check.final_response.span_max_abs_deflections_m,
            check.deflection_limits_m,
            check.immediate_deflection_utilizations,
            check.final_deflection_utilizations,
        ),
        start=1,
    ):
        span_label = f"Span {index}" if is_continuous else "Span"
        print(
            f"    {span_label} ({span:g} m), L/{deflection_ratio:g} = "
            f"{limit * 1000:.1f} mm: immediate "
            f"{immediate_deflection * 1000:.1f} mm "
            f"({immediate_utilization * 100:.1f}%, "
            f"{_status(immediate_utilization)}); final "
            f"{final_deflection * 1000:.1f} mm "
            f"({final_utilization * 100:.1f}%, "
            f"{_status(final_utilization)})"
        )
    print(
        "    Maximum roof snow from immediate deflection: "
        f"{check.maximum_roof_snow_immediate_kn_m2:.2f} kN/m²"
    )
    print(
        "    Maximum roof snow from final deflection: "
        f"{check.maximum_roof_snow_final_kn_m2:.2f} kN/m²"
    )

    print(
        f"  Ultimate strength (ULS, preliminary {timber_grade_name}; "
        f"{PERMANENT_LOAD_FACTOR:g}G + {SNOW_LOAD_FACTOR:g}S):"
    )
    for index, (moment, location) in enumerate(
        zip(
            check.design_response.span_positive_moments_nm,
            check.design_response.span_positive_moment_locations_m,
        ),
        start=1,
    ):
        moment_label = (
            f"Span {index} positive moment"
            if is_continuous
            else "Bending moment"
        )
        print(
            f"    {moment_label}: {moment / 1000:.2f} "
            f"kN·m at {location:.2f} m"
        )
    if is_continuous:
        support_moments = ", ".join(
            f"{moment / 1000:.2f}"
            for moment in check.design_response.support_moments_nm
        )
        print(f"    Support moments: {support_moments} kN·m")
    bending_line = (
        "    Bending resistance: "
        f"{check.bending_resistance_nm / 1000:.2f} kN·m; "
        f"{check.positive_bending_utilization * 100:.1f}% "
        f"({_status(check.positive_bending_utilization)})"
    )
    if is_continuous:
        bending_line += (
            ", negative "
            f"{check.negative_bending_utilization * 100:.1f}% "
            f"({_status(check.negative_bending_utilization)})"
        )
    print(bending_line)
    maximum_shear_n = max(check.design_response.span_max_abs_shears_n)
    print(
        f"    Shear: {maximum_shear_n / 1000:.2f} / "
        f"{check.shear_resistance_n / 1000:.2f} kN, "
        f"{check.shear_utilization * 100:.1f}% "
        f"({_status(check.shear_utilization)})"
    )
    support_reactions = ", ".join(
        f"{reaction / 1000:.2f}"
        for reaction in check.design_response.support_reactions_n
    )
    print(f"    Support reactions: {support_reactions} kN")
    maximum_reaction_n = max(
        abs(value) for value in check.design_response.support_reactions_n
    )
    print(
        f"    Bearing: {maximum_reaction_n / 1000:.2f} / "
        f"{check.bearing_resistance_n / 1000:.2f} kN, "
        f"{check.bearing_utilization * 100:.1f}% "
        f"({_status(check.bearing_utilization)})"
    )
    print(
        f"    Governing: {check.governing_strength_check}, "
        f"{check.governing_strength_utilization * 100:.1f}% "
        f"({_status(check.governing_strength_utilization)})"
    )



def _purlin_report_status(
    check: PurlinCheckResult,
    *,
    include_creep: bool,
) -> str:
    """Return a purlin status using only checks included in the PDF."""
    utilizations = [
        *check.immediate_deflection_utilizations,
        *(
            check.final_deflection_utilizations
            if include_creep
            else ()
        ),
        check.positive_bending_utilization,
        check.negative_bending_utilization,
        check.shear_utilization,
        check.bearing_utilization,
    ]
    has_failure = max(utilizations) >= 1
    if has_failure and check.missing_roof_layers:
        return "FAIL; CHECK INCOMPLETE"
    if has_failure:
        return "FAIL"
    if check.missing_roof_layers:
        return "CHECK INCOMPLETE"
    return "PASS"




def main() -> None:
    with calculation_report(
        "rafter_load_report.pdf",
        include_creep=True,
    ):
        check_rafter(
            title="Hlavní krokve, C22",
            material="c22",
            width=0.08,
            height=0.20,
            span=3.85,
            spacing=0.75,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_rafter(
            title="Hlavní krokve, C24",
            material="c24",
            width=0.08,
            height=0.20,
            span=3.85,
            spacing=0.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_rafter(
            title="Hlavní krokve, zesílené, C22",
            material="c24",
            width=0.10,
            height=0.20,
            span=3.85,
            spacing=1.0,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_rafter(
            title="Krokve vikýře, C22",
            material="c22",
            width=0.08,
            height=0.20,
            span=3.25,
            spacing=0.75,
            roof_angle=17.22,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_purlin(
            title="Vaznice A, C22",
            material="c22",
            width=0.24,
            height=0.24,
            span=3.74,
            rafter_length_above=1.05,
            lower_rafter_span=3.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.12,
        )
        check_purlin(
            title="Vaznice B, C22",
            material="c22",
            width=0.24,
            height=0.32,
            span=4.80,
            rafter_length_above=1.05,
            lower_rafter_span=3.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.12,
        )
        check_purlin(
            title="Vaznice B, C22, tenka",
            material="c22",
            width=0.24,
            height=0.28,
            span=4.80,
            rafter_length_above=1.05,
            lower_rafter_span=3.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.12,
        )
        check_purlin(
            title="Vaznice C, C22",
            material="c22",
            width=0.24,
            height=0.24,
            span=2.75,
            rafter_length_above=1.05,
            lower_rafter_span=3.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.12,
        )
        check_continuous_purlin(
            title="Souvislá vaznice, C22",
            material="c22",
            width=0.24,
            height=0.32,
            spans=(3.74, 4.80, 2.75),
            rafter_length_above=1.05,
            lower_rafter_span=3.85,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.24,
        )


if __name__ == "__main__":
    main()
