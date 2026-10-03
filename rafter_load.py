#!/usr/bin/env python3
"""Preliminary checks of the roof rafters and their supporting purlin.

Edit the values in the USER INPUTS section or pass command-line overrides.
Rafters are treated as simply supported beams. The street-side purlin is
checked both as one continuous beam over four supports and, as an alternative,
as separate simply supported pieces. It is a quick comparison tool, not a
structural design.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import cos, isfinite, radians
from pathlib import Path
from textwrap import wrap
from typing import TypeAlias

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


# USER INPUTS
RAFTER_WIDTH_MM = 80.0
RAFTER_HEIGHT_MM = 200.0
MAX_DEFLECTION_RATIO = 300.0  # 300 means L/300
RAFTER_SPACING_M = 0.9

PURLIN_SUPPORT_SPAN_M = 4.8  # middle span; retained as a convenient input
if 1:
  SUPPORT_SPAN_M = 3.85
  ROOF_ANGLE_DEGREES = 35.83
  DORMER_SUPPORT_SPAN_M = 3.25
  DORMER_ROOF_ANGLE_DEGREES = 17.22
  RAFTER_LENGTH_ABOVE_PURLIN_M = 1.05
  PURLIN_SPANS_M = (3.740, 4.8, 2.750)

# RAFTER_LENGTH_ABOVE_PURLIN_M is the part assigned to one purlin by the user;
# copy the geometry-derived value printed by house_ifc.py when it changes.
# RAFTER_LENGTH_ABOVE_PURLIN_M is measured along the main roof slope, from the
# purlin support towards the ridge.
# Width × height for the left, middle, and right purlin segments. The
# continuous-purlin alternative uses the middle size for the entire member;
# the split-purlin alternative uses all three sizes independently.
PURLIN_SEGMENT_SIZES_MM = (
    (240.0, 240.0),
    (240.0, 320.0),
    (240.0, 240.0),
)
PURLIN_WIDTH_MM, PURLIN_HEIGHT_MM = PURLIN_SEGMENT_SIZES_MM[1]
PURLIN_BEARING_LENGTH_MM = 240.0

# Add any permanent vertical line load carried by the purlin but not included
# in ROOF_LAYERS_KG_M2, for example a ceiling/collar-tie load whose load path
# really terminates at the purlin.
PURLIN_ADDITIONAL_PERMANENT_LOAD_KN_M = 0.0

# Conservative load used by the interactive terminal check. The official
# report uses REPORT_SNOW_LOAD_KN_M2 below. Both are vertical roof snow loads
# per square metre of HORIZONTAL projection. No snow shape, exposure, thermal,
# drift, or partial-safety coefficient is applied automatically.
SNOW_LOAD_KN_M2 = 1.7
REPORT_SNOW_LOAD_KN_M2 = 1.5
REPORT_SNOW_LOAD_STANDARD = "ČSN EN 1991-1-3:2005/Z1:2006"
REPORT_SNOW_LOAD_ZONE = 3
REPORT_PDF_PATH = "rafter_load_report.pdf"

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

# Values stated in the formal calculation report. Keep this as a distinct set
# even where a value currently matches the conservative terminal input, so a
# future safety margin cannot silently alter the documented design basis.
REPORT_ROOF_LAYERS_KG_M2: dict[str, float | None] = {
    "Roof tiles": 45,
    "Tile battens": 5,
    "Counter battens": 5,
    "MDF": 10,
    "vata": 20,
    "OSB": 10,
    "Installation battens/services": 5,
    "Gypsum plasterboard": 30,
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

GRAVITY_M_S2 = 10.0


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
class IndependentPurlinSpanResult:
    """One purlin segment checked without continuity into adjacent spans."""

    segment_index: int
    span_m: float
    width_mm: float
    height_mm: float
    bearing_length_mm: float
    self_mass_kg_m: float
    permanent_line_load_kn_m: float
    immediate_deflection_m: float
    final_deflection_m: float
    deflection_limit_m: float
    immediate_deflection_utilization: float
    final_deflection_utilization: float
    maximum_roof_snow_immediate_kn_m2: float
    maximum_roof_snow_final_kn_m2: float
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


@dataclass(frozen=True)
class PurlinCheckResult:
    """Three-span street-side purlin check and its tributary roof load."""

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
    independent_spans: tuple[IndependentPurlinSpanResult, ...]
    missing_roof_layers: tuple[str, ...]

    @property
    def independent_longest_span(self) -> IndependentPurlinSpanResult:
        """Retain convenient access to the geometrically longest piece."""
        return max(self.independent_spans, key=lambda result: result.span_m)


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

        continued_title = f"{title} ({continuation_label})"
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


def assert_terminal_inputs_are_conservative(
    *,
    terminal_snow_load_kn_m2: float,
    report_snow_load_kn_m2: float,
    terminal_roof_layers_kg_m2: Mapping[str, float | None],
    report_roof_layers_kg_m2: Mapping[str, float | None],
) -> None:
    """Assert that terminal loads are no lower than documented report loads."""
    terminal_snow = _non_negative(
        terminal_snow_load_kn_m2,
        "terminal_snow_load_kn_m2",
    )
    report_snow = _non_negative(
        report_snow_load_kn_m2,
        "report_snow_load_kn_m2",
    )
    assert terminal_snow >= report_snow, (
        "terminal snow load must be at least the official report snow load"
    )
    assert terminal_roof_layers_kg_m2.keys() == (
        report_roof_layers_kg_m2.keys()
    ), "terminal and report roof-layer sets must contain the same layers"

    for name in terminal_roof_layers_kg_m2:
        terminal_mass = terminal_roof_layers_kg_m2[name]
        report_mass = report_roof_layers_kg_m2[name]
        assert (terminal_mass is None) == (report_mass is None), (
            f'roof layer "{name}" must be specified in both load sets'
        )
        if terminal_mass is not None and report_mass is not None:
            assert terminal_mass >= report_mass, (
                f'terminal roof layer "{name}" must be at least the '
                "official report value"
            )

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
    support_spans_m: tuple[float, float, float],
    segment_sizes_mm: (
        tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
        | None
    ) = None,
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
    bearing_length_mm: float = PURLIN_BEARING_LENGTH_MM,
    split_bearing_length_mm: float | None = None,
    bearing_strength_factor: float = BEARING_STRENGTH_FACTOR,
    shear_effective_width_factor: float = SHEAR_EFFECTIVE_WIDTH_FACTOR,
) -> PurlinCheckResult:
    """Check the street-side purlin as one continuous three-span beam.

    Permanent load and the selected street-roof snow load are uniform over all
    three spans. The rafter reactions are smeared into a purlin line load.
    """
    if len(support_spans_m) != 3:
        raise ValueError("support_spans_m must contain exactly three spans")
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
    default_width_mm = _positive(width_mm, "width_mm")
    default_height_mm = _positive(height_mm, "height_mm")
    if segment_sizes_mm is None:
        segment_sizes = tuple(
            (default_width_mm, default_height_mm) for _ in spans
        )
    else:
        if len(segment_sizes_mm) != len(spans):
            raise ValueError(
                "segment_sizes_mm must contain one (width, height) pair "
                "for every purlin span"
            )
        validated_segment_sizes = []
        for index, size in enumerate(segment_sizes_mm):
            if not isinstance(size, (tuple, list)) or len(size) != 2:
                raise ValueError(
                    f"segment_sizes_mm[{index}] must contain width and height"
                )
            validated_segment_sizes.append(
                (
                    _positive(size[0], f"segment_sizes_mm[{index}][0]"),
                    _positive(size[1], f"segment_sizes_mm[{index}][1]"),
                )
            )
        segment_sizes = tuple(validated_segment_sizes)
    continuous_width_mm, continuous_height_mm = segment_sizes[1]
    purlin_width_m = continuous_width_mm / 1000
    purlin_height_m = continuous_height_mm / 1000
    continuous_bearing_length_mm = _positive(
        bearing_length_mm,
        "bearing_length_mm",
    )
    if split_bearing_length_mm is None:
        independent_bearing_length_mm = continuous_bearing_length_mm / 2
    else:
        independent_bearing_length_mm = _positive(
            split_bearing_length_mm,
            "split_bearing_length_mm",
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
        continuous_bearing_length_mm
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
    strength_utilizations = {
        "positive bending": positive_bending_utilization,
        "negative bending": negative_bending_utilization,
        "shear": shear_utilization,
        "bearing": bearing_utilization,
    }
    governing_strength_check = max(
        strength_utilizations,
        key=strength_utilizations.__getitem__,
    )

    # Alternative construction: cut the purlin at its supports and check each
    # piece as a simply supported beam using its own section. None of the
    # pieces receives a continuity benefit from its neighbours.
    independent_spans: list[IndependentPurlinSpanResult] = []
    transferred_permanent_line_load_kn_m = (
        (roof_layer_line_mass_kg_m + rafter_line_mass_kg_m)
        * GRAVITY_M_S2
        / 1000
        + extra_line_load_kn_m
    )
    for index, (independent_span_m, segment_size) in enumerate(
        zip(spans, segment_sizes),
        start=1,
    ):
        segment_width_mm, segment_height_mm = segment_size
        segment_width_m = segment_width_mm / 1000
        segment_height_m = segment_height_mm / 1000
        segment_self_mass_kg_m = (
            density_kg_m3 * segment_width_m * segment_height_m
        )
        segment_permanent_line_load_kn_m = (
            transferred_permanent_line_load_kn_m
            + segment_self_mass_kg_m * GRAVITY_M_S2 / 1000
        )
        segment_immediate_line_load_kn_m = (
            segment_permanent_line_load_kn_m + roof_snow_line_load_kn_m
        )
        segment_final_line_load_kn_m = (
            segment_permanent_line_load_kn_m * (1 + creep_factor)
            + roof_snow_line_load_kn_m
            * (1 + snow_creep_combination_factor * creep_factor)
        )
        segment_design_line_load_kn_m = (
            permanent_factor * segment_permanent_line_load_kn_m
            + snow_factor * roof_snow_line_load_kn_m
        )
        segment_second_moment_m4 = (
            segment_width_m * segment_height_m**3 / 12
        )
        segment_section_modulus_m3 = (
            segment_width_m * segment_height_m**2 / 6
        )

        def independent_deflection(line_load_kn_m: float) -> float:
            return (
                5
                * line_load_kn_m
                * 1000
                * independent_span_m**4
                / (384 * modulus_pa * segment_second_moment_m4)
            )

        independent_limit_m = independent_span_m / ratio
        independent_permanent_deflection_m = independent_deflection(
            segment_permanent_line_load_kn_m
        )
        independent_unit_snow_deflection_m = independent_deflection(
            tributary_horizontal_width_m
        )
        independent_immediate_deflection_m = independent_deflection(
            segment_immediate_line_load_kn_m
        )
        independent_final_deflection_m = independent_deflection(
            segment_final_line_load_kn_m
        )
        independent_immediate_snow_capacity = (
            max(
                0.0,
                independent_limit_m
                - independent_permanent_deflection_m,
            )
            / independent_unit_snow_deflection_m
        )
        independent_final_snow_capacity = (
            max(
                0.0,
                independent_limit_m
                - independent_permanent_deflection_m * (1 + creep_factor),
            )
            / (
                independent_unit_snow_deflection_m
                * (1 + snow_creep_combination_factor * creep_factor)
            )
        )
        independent_design_load_n_m = (
            segment_design_line_load_kn_m * 1000
        )
        independent_design_bending_nm = (
            independent_design_load_n_m * independent_span_m**2 / 8
        )
        independent_design_reaction_n = (
            independent_design_load_n_m * independent_span_m / 2
        )
        independent_bending_resistance_nm = (
            design_bending_strength_pa * segment_section_modulus_m3
        )
        independent_shear_resistance_n = (
            design_shear_strength_pa
            * segment_width_m
            * _positive(
                shear_effective_width_factor,
                "shear_effective_width_factor",
            )
            * segment_height_m
            / 1.5
        )
        independent_bearing_resistance_n = bearing_resistance(
            segment_width_m,
            independent_bearing_length_mm,
        )
        independent_strength_utilizations = {
            "bending": (
                independent_design_bending_nm
                / independent_bending_resistance_nm
            ),
            "shear": (
                independent_design_reaction_n
                / independent_shear_resistance_n
            ),
            "bearing": (
                independent_design_reaction_n
                / independent_bearing_resistance_n
            ),
        }
        independent_governing_strength_check = max(
            independent_strength_utilizations,
            key=independent_strength_utilizations.__getitem__,
        )
        independent_spans.append(
            IndependentPurlinSpanResult(
                segment_index=index,
                span_m=independent_span_m,
                width_mm=segment_width_mm,
                height_mm=segment_height_mm,
                bearing_length_mm=independent_bearing_length_mm,
                self_mass_kg_m=segment_self_mass_kg_m,
                permanent_line_load_kn_m=segment_permanent_line_load_kn_m,
                immediate_deflection_m=independent_immediate_deflection_m,
                final_deflection_m=independent_final_deflection_m,
                deflection_limit_m=independent_limit_m,
                immediate_deflection_utilization=(
                    independent_immediate_deflection_m / independent_limit_m
                ),
                final_deflection_utilization=(
                    independent_final_deflection_m / independent_limit_m
                ),
                maximum_roof_snow_immediate_kn_m2=(
                    independent_immediate_snow_capacity
                ),
                maximum_roof_snow_final_kn_m2=(
                    independent_final_snow_capacity
                ),
                design_bending_moment_nm=independent_design_bending_nm,
                design_shear_force_n=independent_design_reaction_n,
                design_support_reaction_n=independent_design_reaction_n,
                bending_resistance_nm=independent_bending_resistance_nm,
                shear_resistance_n=independent_shear_resistance_n,
                bearing_resistance_n=independent_bearing_resistance_n,
                bending_utilization=(
                    independent_strength_utilizations["bending"]
                ),
                shear_utilization=independent_strength_utilizations["shear"],
                bearing_utilization=(
                    independent_strength_utilizations["bearing"]
                ),
                governing_strength_check=(
                    independent_governing_strength_check
                ),
                governing_strength_utilization=(
                    independent_strength_utilizations[
                        independent_governing_strength_check
                    ]
                ),
            )
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
        independent_spans=tuple(independent_spans),
        missing_roof_layers=tuple(missing_roof_layers),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check main-roof and dormer rafters, plus continuous and split "
            "street-side purlin options, under uniformly distributed loads."
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
        help=(
            "conservative terminal-check snow load in kN/m^2 of horizontal "
            "projection; the PDF uses REPORT_SNOW_LOAD_KN_M2"
        ),
    )
    parser.add_argument(
        "--purlin-width",
        type=float,
        default=PURLIN_WIDTH_MM,
        help="middle-segment purlin width in mm",
    )
    parser.add_argument(
        "--purlin-height",
        type=float,
        default=PURLIN_HEIGHT_MM,
        help="middle-segment purlin height in mm",
    )
    parser.add_argument(
        "--purlin-left-width",
        type=float,
        default=PURLIN_SEGMENT_SIZES_MM[0][0],
        help="left independent purlin width in mm",
    )
    parser.add_argument(
        "--purlin-left-height",
        type=float,
        default=PURLIN_SEGMENT_SIZES_MM[0][1],
        help="left independent purlin height in mm",
    )
    parser.add_argument(
        "--purlin-right-width",
        type=float,
        default=PURLIN_SEGMENT_SIZES_MM[2][0],
        help="right independent purlin width in mm",
    )
    parser.add_argument(
        "--purlin-right-height",
        type=float,
        default=PURLIN_SEGMENT_SIZES_MM[2][1],
        help="right independent purlin height in mm",
    )
    parser.add_argument(
        "--purlin-spans",
        type=float,
        nargs=3,
        metavar=("LEFT", "MIDDLE", "RIGHT"),
        default=PURLIN_SPANS_M,
        help="three consecutive purlin support spans in m",
    )
    parser.add_argument(
        "--upper-rafter-length",
        type=float,
        default=RAFTER_LENGTH_ABOVE_PURLIN_M,
        help="rafter length along the main slope from purlin to ridge in m",
    )
    parser.add_argument(
        "--purlin-bearing-length",
        type=float,
        default=PURLIN_BEARING_LENGTH_MM,
        help="purlin bearing length along its axis at a support in mm",
    )
    parser.add_argument(
        "--purlin-split-bearing-length",
        type=float,
        default=None,
        help=(
            "end bearing length for each independently supported purlin "
            "piece in mm; defaults to half --purlin-bearing-length"
        ),
    )
    parser.add_argument(
        "--purlin-extra-load",
        type=float,
        default=PURLIN_ADDITIONAL_PERMANENT_LOAD_KN_M,
        help=(
            "additional permanent vertical purlin line load in kN/m "
            "(for example a separately supported ceiling)"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(REPORT_PDF_PATH),
        help=(
            "write the official-input rafter calculation to this PDF "
            f"(default: {REPORT_PDF_PATH})"
        ),
    )
    parser.add_argument(
        "--no-report",
        dest="report",
        action="store_const",
        const=None,
        help="skip PDF report generation",
    )
    return parser


def _status(utilization: float) -> str:
    return "PASS" if utilization <= 1 else "FAIL"


def _percent(utilization: float) -> str:
    return f"{utilization * 100:.1f}%"


def _status_cz(utilization: float) -> str:
    return "VYHOVUJE" if utilization <= 1 else "NEVYHOVUJE"


RafterReportCase: TypeAlias = tuple[str, float, float, RoofCheckResult]

_REPORT_CASE_NAMES_CZ = {
    "Main roof": "hlavní střecha",
    "Dormer roof": "střecha vikýře",
}
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


def _rafter_report_case_status(check: RoofCheckResult) -> str:
    """Return the report status without considering long-term deflection."""
    has_failure = max(
        check.characteristic_deflection_utilization,
        check.bending_utilization,
        check.shear_utilization,
        check.bearing_utilization,
    ) > 1
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
) -> None:
    """Append a traceable rafter calculation to an open PDF report.

    The report deliberately checks immediate deflection only. The interactive
    terminal calculation remains the conservative check and also includes
    creep/final deflection.
    """
    if not rafter_checks:
        raise ValueError("rafter_checks must contain at least one case")

    width_m = _positive(width_mm, "width_mm") / 1000
    height_m = _positive(height_mm, "height_mm") / 1000
    spacing_m = _positive(rafter_spacing_m, "rafter_spacing_m")
    _positive(elastic_modulus_gpa, "elastic_modulus_gpa")
    density = _positive(timber_density_kg_m3, "timber_density_kg_m3")
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

    case_summary_lines: list[str] = []
    for name, span_m, angle_degrees, check in rafter_checks:
        case_summary_lines.append(
            f"{name}: {_rafter_report_case_status(check)}; "
            f"immediate deflection "
            f"{check.characteristic_deflection_m * 1000:.2f} mm "
            f"({_percent(check.characteristic_deflection_utilization)}); "
            f"governing ULS {check.governing_strength_check} "
            f"({_percent(check.governing_strength_utilization)})"
        )

    report.add_sections(
        "Rafter calculation – design basis and summary",
        (
            (
                "Purpose and structural model",
                (
                    "Preliminary verification of timber rafters as simply "
                    "supported beams.",
                    "The support span is the real length measured along the "
                    "sloping rafter.",
                    "Snow is a vertical action per horizontal roof projection; "
                    "roof-layer masses are per actual sloping surface.",
                    "This PDF uses the official input set. A separate, more "
                    "conservative input set is used by the terminal check.",
                ),
            ),
            (
                "Shared geometry and material",
                (
                    f"Cross-section b × h = {width_mm:.0f} × "
                    f"{height_mm:.0f} mm",
                    f"Rafter centre spacing a = {spacing_m:.3f} m",
                    f"Mean modulus E = {elastic_modulus_gpa:.2f} GPa",
                    f"Timber density = {density:.1f} kg/m³",
                    f"Deflection criterion = L/{deflection_ratio:g}",
                    f"C24 characteristic strengths: fm,k = "
                    f"{C24_BENDING_STRENGTH_MPA:g} MPa, fv,k = "
                    f"{C24_SHEAR_STRENGTH_MPA:g} MPa, fc,90,k = "
                    f"{C24_COMPRESSION_PERPENDICULAR_MPA:g} MPa",
                    f"kmod = {TIMBER_MODIFICATION_FACTOR:g}; "
                    f"γM = {TIMBER_MATERIAL_PARTIAL_FACTOR:g}; "
                    f"kcr = {SHEAR_EFFECTIVE_WIDTH_FACTOR:g}",
                    f"Assumed bearing length = {BEARING_LENGTH_MM:g} mm",
                ),
            ),
            (
                "Characteristic actions",
                (
                    f"Official roof snow load sk = {snow_load:.3f} kN/m²",
                    f"ULS factors: γG = {PERMANENT_LOAD_FACTOR:g}; "
                    f"γQ = {SNOW_LOAD_FACTOR:g}",
                    f"Official roof-layer permanent load gk = "
                    f"{known_layer_total_kg_m2:.1f} kg/m² = "
                    f"{roof_layer_surface_load_kn_m2:.3f} kN/m²",
                    "The layer breakdown is shown in the following table.",
                ),
            ),
            ("Result summary", tuple(case_summary_lines)),
            (
                "Scope and limitations",
                (
                    "Serviceability in this PDF includes immediate deflection "
                    "from permanent load and snow only.",
                    "Creep/final deflection is intentionally omitted from this "
                    "PDF; it remains included in the conservative terminal "
                    "check.",
                    "The calculation does not replace project-specific "
                    "structural design. Verify load combinations, national "
                    "annex choices, stability, notches, connections, fire, "
                    "moisture, and local load effects.",
                ),
            ),
        ),
    )

    add_roof_load_table(
        report,
        roof_layers_kg_m2,
        snow_load_kn_m2=snow_load,
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
            C24_BENDING_STRENGTH_MPA * design_strength_multiplier
        )
        shear_strength_mpa = (
            C24_SHEAR_STRENGTH_MPA * design_strength_multiplier
        )
        bearing_strength_mpa = (
            C24_COMPRESSION_PERPENDICULAR_MPA
            * design_strength_multiplier
            * BEARING_STRENGTH_FACTOR
        )
        bearing_area_m2 = width_m * BEARING_LENGTH_MM / 1000

        case_name_cz = _REPORT_CASE_NAMES_CZ.get(name, name)
        report.add_sections(
            f"Krokev – {case_name_cz}",
            (
                (
                    "Geometrie a průřezové charakteristiky",
                    (
                        f"Rozpětí mezi podporami L = {span_m:.3f} m podél krokve",
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
                        f"<= {check.bending_resistance_nm / 1000:.3f} kNm, "
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
                        f"<= {check.shear_resistance_n / 1000:.3f} kN, "
                        f"{_status_cz(check.shear_utilization)}",
                    ),
                ),
                (
                    "Posouzení - otlačení v uložení",
                    (
                        "Mezní stav únosnosti (MSÚ), tlak kolmo k vláknům.",
                        f"Návrhová reakce Fc,90,Ed = "
                        f"{check.design_support_reaction_n / 1000:.3f} kN",
                        f"Návrhová pevnost fc,90,d = "
                        f"{bearing_strength_mpa:.2f} MPa",
                        f"Plocha uložení A = b × l = "
                        f"{width_m * 1000:.0f} × {BEARING_LENGTH_MM:g} = "
                        f"{bearing_area_m2 * 1e6:.0f} mm²",
                        f"Mezní hodnota Rc,90,d = fc,90,d × A = "
                        f"{check.bearing_resistance_n / 1000:.3f} kN",
                        f"{check.design_support_reaction_n / 1000:.3f} kN "
                        f"<= {check.bearing_resistance_n / 1000:.3f} kN, "
                        f"{_status_cz(check.bearing_utilization)}",
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
                        f"<= {result.maximum_deflection_m * 1000:.2f} mm, "
                        f"{_status_cz(check.characteristic_deflection_utilization)}",
                    ),
                ),
            ),
            footer_title="Předběžný statický výpočet střechy",
            page_label="Strana",
            continuation_label="pokračování",
        )


def generate_rafter_report(
    path: str | Path,
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
) -> int:
    """Write one rafter report and return its number of pages."""
    with CalculationReport(
        path,
        document_title="Preliminary roof structural calculation",
    ) as report:
        add_rafter_report(
            report,
            width_mm=width_mm,
            height_mm=height_mm,
            rafter_spacing_m=rafter_spacing_m,
            deflection_ratio=deflection_ratio,
            elastic_modulus_gpa=elastic_modulus_gpa,
            timber_density_kg_m3=timber_density_kg_m3,
            snow_load_kn_m2=snow_load_kn_m2,
            roof_layers_kg_m2=roof_layers_kg_m2,
            rafter_checks=rafter_checks,
        )
        return report.page_count

def _overall_result(
    rafter_checks: list[tuple[str, float, float, RoofCheckResult]],
    purlin_check: PurlinCheckResult,
) -> str:
    """Summarize every SLS and ULS utilization reported by the script."""
    utilizations = [
        utilization
        for _, _, _, check in rafter_checks
        for utilization in (
            check.characteristic_deflection_utilization,
            check.final_deflection_utilization,
            check.bending_utilization,
            check.shear_utilization,
            check.bearing_utilization,
        )
    ]
    utilizations.extend(purlin_check.immediate_deflection_utilizations)
    utilizations.extend(purlin_check.final_deflection_utilizations)
    utilizations.extend(
        (
            purlin_check.positive_bending_utilization,
            purlin_check.negative_bending_utilization,
            purlin_check.shear_utilization,
            purlin_check.bearing_utilization,
        )
    )
    has_failures = any(utilization > 1 for utilization in utilizations)
    is_incomplete = any(
        check.missing_roof_layers for _, _, _, check in rafter_checks
    ) or bool(purlin_check.missing_roof_layers)

    if has_failures and is_incomplete:
        return "THERE ARE FAILURES, AND THE CHECK IS INCOMPLETE."
    if has_failures:
        return "THERE ARE FAILURES. Review the checks marked FAIL above."
    if is_incomplete:
        return "CHECK INCOMPLETE. Enter all missing roof-layer masses."
    return "EVERYTHING PASSED."


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


def _print_purlin_check(
    *,
    deflection_ratio: float,
    check: PurlinCheckResult,
) -> None:
    """Print the continuous street-side purlin results."""
    print()
    print("Street-side continuous purlin:")
    print(
        "  Support spans: "
        + " + ".join(f"{span:g} m" for span in check.span_lengths_m)
    )
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
        "kN/m vertical, uniformly on all spans"
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
        print(
            f"    Span {index} ({span:g} m), L/{deflection_ratio:g} = "
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
        "  Ultimate strength (ULS, preliminary C24; "
        f"{PERMANENT_LOAD_FACTOR:g}G + {SNOW_LOAD_FACTOR:g}S):"
    )
    for index, (moment, location) in enumerate(
        zip(
            check.design_response.span_positive_moments_nm,
            check.design_response.span_positive_moment_locations_m,
        ),
        start=1,
    ):
        print(
            f"    Span {index} positive moment: {moment / 1000:.2f} "
            f"kN·m at {location:.2f} m"
        )
    support_moments = ", ".join(
        f"{moment / 1000:.2f}"
        for moment in check.design_response.support_moments_nm
    )
    print(f"    Support moments: {support_moments} kN·m")
    print(
        "    Bending resistance: "
        f"{check.bending_resistance_nm / 1000:.2f} kN·m; positive "
        f"{check.positive_bending_utilization * 100:.1f}% "
        f"({_status(check.positive_bending_utilization)}), negative "
        f"{check.negative_bending_utilization * 100:.1f}% "
        f"({_status(check.negative_bending_utilization)})"
    )
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


def _independent_span_has_failure(
    span: IndependentPurlinSpanResult,
) -> bool:
    return max(
        span.immediate_deflection_utilization,
        span.final_deflection_utilization,
        span.bending_utilization,
        span.shear_utilization,
        span.bearing_utilization,
    ) > 1


def _independent_purlin_status(check: PurlinCheckResult) -> str:
    has_failure = any(
        _independent_span_has_failure(span)
        for span in check.independent_spans
    )
    if has_failure and check.missing_roof_layers:
        return "FAIL; CHECK INCOMPLETE"
    if has_failure:
        return "FAIL"
    if check.missing_roof_layers:
        return "CHECK INCOMPLETE"
    return "PASS"


def _print_independent_purlin_spans(
    *,
    deflection_ratio: float,
    check: PurlinCheckResult,
) -> None:
    """Print the alternative with every purlin segment split off."""
    print()
    print("Independent purlin pieces:")
    print("  Each segment is simply supported with no continuity benefit.")
    print(
        "  End bearing length used per piece: "
        f"{check.independent_spans[0].bearing_length_mm:g} mm "
        "(override with --purlin-split-bearing-length; default is half the "
        "continuous-purlin bearing length)"
    )
    for span in check.independent_spans:
        print()
        print(
            f"  Segment {span.segment_index}: {span.span_m:g} m, "
            f"{span.width_mm:g} × {span.height_mm:g} mm"
        )
        print(
            f"    Self-mass: {span.self_mass_kg_m:.1f} kg/m; permanent "
            f"line load: {span.permanent_line_load_kn_m:.3f} kN/m"
        )
        print("    Serviceability (SLS):")
        print(
            f"      L/{deflection_ratio:g} = "
            f"{span.deflection_limit_m * 1000:.1f} mm: immediate "
            f"{span.immediate_deflection_m * 1000:.1f} mm "
            f"({span.immediate_deflection_utilization * 100:.1f}%, "
            f"{_status(span.immediate_deflection_utilization)}); final "
            f"{span.final_deflection_m * 1000:.1f} mm "
            f"({span.final_deflection_utilization * 100:.1f}%, "
            f"{_status(span.final_deflection_utilization)})"
        )
        print(
            "      Maximum roof snow from immediate/final deflection: "
            f"{span.maximum_roof_snow_immediate_kn_m2:.2f} / "
            f"{span.maximum_roof_snow_final_kn_m2:.2f} kN/m²"
        )
        print(
            "    Ultimate strength (ULS, preliminary C24; "
            f"{PERMANENT_LOAD_FACTOR:g}G + {SNOW_LOAD_FACTOR:g}S):"
        )
        for check_name, demand, resistance, utilization, unit in (
            (
                "Bending",
                span.design_bending_moment_nm,
                span.bending_resistance_nm,
                span.bending_utilization,
                "kN·m",
            ),
            (
                "Shear",
                span.design_shear_force_n,
                span.shear_resistance_n,
                span.shear_utilization,
                "kN",
            ),
            (
                "Bearing",
                span.design_support_reaction_n,
                span.bearing_resistance_n,
                span.bearing_utilization,
                "kN",
            ),
        ):
            print(
                f"      {check_name}: {demand / 1000:.2f} / "
                f"{resistance / 1000:.2f} {unit}, "
                f"{utilization * 100:.1f}% ({_status(utilization)})"
            )
        print(
            f"      Governing strength: {span.governing_strength_check}, "
            f"{span.governing_strength_utilization * 100:.1f}% "
            f"({_status(span.governing_strength_utilization)})"
        )
        print(
            "    SEGMENT RESULT: "
            f"{'FAIL' if _independent_span_has_failure(span) else 'PASS'}"
        )
    print(f"  SPLIT OPTION RESULT: {_independent_purlin_status(check)}")


def main() -> None:
    arguments = _parser().parse_args()
    assert_terminal_inputs_are_conservative(
        terminal_snow_load_kn_m2=arguments.snow_load,
        report_snow_load_kn_m2=REPORT_SNOW_LOAD_KN_M2,
        terminal_roof_layers_kg_m2=ROOF_LAYERS_KG_M2,
        report_roof_layers_kg_m2=REPORT_ROOF_LAYERS_KG_M2,
    )

    shared_rafter_check_arguments = {
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
    rafter_checks = [
        (
            name,
            span,
            angle,
            calculate_roof_check(
                support_span_m=span,
                roof_angle_degrees=angle,
                **shared_rafter_check_arguments,
            ),
        )
        for name, span, angle in roof_cases
    ]

    shared_purlin_check_arguments = {
        "width_mm": arguments.purlin_width,
        "height_mm": arguments.purlin_height,
        "support_spans_m": tuple(arguments.purlin_spans),
        "segment_sizes_mm": (
            (arguments.purlin_left_width, arguments.purlin_left_height),
            (arguments.purlin_width, arguments.purlin_height),
            (arguments.purlin_right_width, arguments.purlin_right_height),
        ),
        "upper_rafter_length_m": arguments.upper_rafter_length,
        "lower_rafter_span_m": arguments.span,
        "roof_angle_degrees": arguments.angle,
        "rafter_width_mm": arguments.width,
        "rafter_height_mm": arguments.height,
        "rafter_spacing_m": arguments.spacing,
        "deflection_ratio": arguments.deflection_ratio,
        "elastic_modulus_gpa": arguments.modulus,
        "snow_load_kn_m2": arguments.snow_load,
        "roof_layers_kg_m2": ROOF_LAYERS_KG_M2,
        "additional_permanent_load_kn_m": arguments.purlin_extra_load,
        "timber_density_kg_m3": arguments.density,
        "bearing_length_mm": arguments.purlin_bearing_length,
        "split_bearing_length_mm": arguments.purlin_split_bearing_length,
    }
    purlin_check = calculate_purlin_check(
        **shared_purlin_check_arguments,
    )

    report_page_count: int | None = None
    if arguments.report is not None:
        official_rafter_arguments = {
            "width_mm": arguments.width,
            "height_mm": arguments.height,
            "deflection_ratio": arguments.deflection_ratio,
            "elastic_modulus_gpa": arguments.modulus,
            "timber_density_kg_m3": arguments.density,
            "rafter_spacing_m": arguments.spacing,
            "snow_load_kn_m2": REPORT_SNOW_LOAD_KN_M2,
            "roof_layers_kg_m2": REPORT_ROOF_LAYERS_KG_M2,
        }
        official_rafter_checks = [
            (
                name,
                span,
                angle,
                calculate_roof_check(
                    support_span_m=span,
                    roof_angle_degrees=angle,
                    **official_rafter_arguments,
                ),
            )
            for name, span, angle in roof_cases
        ]
        report_page_count = generate_rafter_report(
            arguments.report,
            width_mm=arguments.width,
            height_mm=arguments.height,
            rafter_spacing_m=arguments.spacing,
            deflection_ratio=arguments.deflection_ratio,
            elastic_modulus_gpa=arguments.modulus,
            timber_density_kg_m3=arguments.density,
            snow_load_kn_m2=REPORT_SNOW_LOAD_KN_M2,
            roof_layers_kg_m2=REPORT_ROOF_LAYERS_KG_M2,
            rafter_checks=official_rafter_checks,
        )

    print(
        f"Shared rafter: {arguments.width:g} × {arguments.height:g} mm, "
        f"spacing {arguments.spacing:g} m"
    )
    print(
        f"Shared timber: E={arguments.modulus:g} GPa, "
        f"density {arguments.density:g} kg/m³"
    )
    print(
        "Rafter self-mass: "
        f"{rafter_checks[0][3].rafter.self_mass_kg_per_m:.1f} kg/m"
    )

    print()
    print("Shared permanent roof layers (actual sloping surface):")
    for layer_name, mass in ROOF_LAYERS_KG_M2.items():
        value = "MISSING" if mass is None else f"{mass:.1f} kg/m²"
        print(f"  {layer_name}: {value}")
    print(
        "  Known layer total: "
        f"{rafter_checks[0][3].roof_layer_mass_kg_m2:.1f} kg/m²"
    )
    if rafter_checks[0][3].missing_roof_layers:
        print(
            "CHECK INCOMPLETE: enter a mass for every layer listed as MISSING."
        )

    print()
    print(
        f"Shared snow load: {arguments.snow_load:g} kN/m² on horizontal "
        f"projection ({arguments.snow_load * 1000 / GRAVITY_M_S2:.1f} "
        "kg/m² equivalent)"
    )
    for name, span, angle, check in rafter_checks:
        _print_roof_check(
            name,
            support_span_m=span,
            roof_angle_degrees=angle,
            deflection_ratio=arguments.deflection_ratio,
            check=check,
        )

    governing_rafter_sls = max(
        rafter_checks,
        key=lambda case: case[3].final_deflection_utilization,
    )
    governing_rafter_uls = max(
        rafter_checks,
        key=lambda case: case[3].governing_strength_utilization,
    )
    print()
    print("Governing rafter cases:")
    print(
        f"  Final deflection: {governing_rafter_sls[0]}, "
        f"{governing_rafter_sls[3].final_deflection_utilization * 100:.1f}% "
        f"({_status(governing_rafter_sls[3].final_deflection_utilization)})"
    )
    print(
        f"  Strength: {governing_rafter_uls[0]} "
        f"{governing_rafter_uls[3].governing_strength_check}, "
        f"{governing_rafter_uls[3].governing_strength_utilization * 100:.1f}% "
        f"({_status(governing_rafter_uls[3].governing_strength_utilization)})"
    )

    print()
    print(
        "Continuous purlin section (middle-segment size): "
        f"{arguments.purlin_width:g} × "
        f"{arguments.purlin_height:g} mm, bearing length "
        f"{arguments.purlin_bearing_length:g} mm"
    )
    print(
        "Only the simple street roof is applied to the purlin. It carries "
        f"the entered {arguments.upper_rafter_length:g} m above it and half "
        "of the street-side lower rafter span."
    )
    _print_purlin_check(
        deflection_ratio=arguments.deflection_ratio,
        check=purlin_check,
    )
    _print_independent_purlin_spans(
        deflection_ratio=arguments.deflection_ratio,
        check=purlin_check,
    )

    print()
    print(
        "WARNING: Preliminary member check only. Confirm material values and "
        "National Annex factors. Axial force, lateral buckling/restraint, "
        "notches, holes, connections, wind uplift, fire, and snow drift/shape "
        "cases still require separate checks. The primary purlin model assumes "
        "continuity over all four supports and uses the middle segment's "
        "section throughout. The split alternative treats every segment as a "
        "separate simply supported piece with its specified section. Discrete "
        "rafter reactions are smeared into a uniform load. The garden/dormer "
        "purlin, end overhangs, concentrated-load effects, and the design of "
        "any splice or connection are not checked."
    )
    print()
    print("OVERALL RESULT FOR RAFTERS AND CONTINUOUS PURLIN:")
    print(f"  {_overall_result(rafter_checks, purlin_check)}")
    print(
        "SPLIT-PURLIN ALTERNATIVE: "
        f"{_independent_purlin_status(purlin_check)}"
    )


    if arguments.report is not None:
        print()
        print(
            f"OFFICIAL RAFTER REPORT: {arguments.report} "
            f"({report_page_count} pages)"
        )

if __name__ == "__main__":
    main()
