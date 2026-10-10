#!/usr/bin/env python3
"""Preliminary checks of the roof rafters and their supporting purlin.

Edit the check calls in ``main()`` to describe each structural member.
Rafters are treated as simply supported beams. Purlins can be checked either
as individual simply supported pieces or as one uniform continuous member over
four supports. Double purlins use two freely slipping beams in vertical contact,
without composite action. It is a quick comparison tool, not a structural design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from pathlib import Path
import re
from textwrap import wrap
from typing import TypeAlias

from materials import (
    TimberGrade,
    TIMBER_GRADES as _TIMBER_GRADES,
    TIMBER_MATERIAL_PARTIAL_FACTOR,
    resolve_timber_grade as _resolve_timber_grade,
)

from matplotlib import rcParams
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text


# Type 3 fonts render correctly but do not contain a reliable Unicode map,
# which breaks copying Czech and Greek characters from the generated PDF.
rcParams["pdf.fonttype"] = 42
rcParams["mathtext.fontset"] = "dejavusans"


# Shared project inputs used by the checks in main().
ROOF_ANGLE_DEGREES = 35.83
MAX_DEFLECTION_RATIO = 300.0  # 300 means L/300
SNOW_LOAD_KN_M2 = 1.7  # vertical load per horizontal roof projection

REPORT_SNOW_LOAD_STANDARD = "ČSN EN 1991-1-3:2005/Z1:2006"
REPORT_SNOW_LOAD_ZONE = 3
REPORT_BASIS_STANDARD = "ČSN EN 1990 a příslušná národní příloha"
REPORT_TIMBER_STANDARD = "ČSN EN 1995-1-1 a příslušná národní příloha"
REPORT_TIMBER_GRADES_STANDARD = "ČSN EN 338"
REPORT_GLULAM_GRADES_STANDARD = "ČSN EN 14080"

# Permanent masses per square metre of ACTUAL SLOPING roof surface. Enter the
# installed mass of every layer. Use 0 only when a listed layer is genuinely
# absent; None keeps the overall check explicitly incomplete.
ROOF_LAYERS_KG_M2: dict[str, float | None] = {
    "Roof tiles": 45,
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
TIMBER_MODIFICATION_FACTOR = 0.80  # solid timber/glulam, service class 2, snow
TIMBER_CREEP_FACTOR = 0.80  # k_def, solid timber/glulam, service class 2
SNOW_CREEP_COMBINATION_FACTOR = 0.0  # psi_2; verify for the project/NA
PERMANENT_LOAD_FACTOR = 1.35
SNOW_LOAD_FACTOR = 1.50
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
    # Normally the member's own reaction. A lower stacked beam also receives
    # the upper beam's end reaction directly at its support.
    bearing_design_reaction_n: float | None = None


@dataclass(frozen=True)
class DoublePurlinCheckResult:
    """Two equal-width, equal-material beams with free longitudinal slip.

    Component actions contain their allocated loads. Tributary roof-mass
    metadata remains the common, unallocated basis, counted only once per stack.
    """

    top: PurlinCheckResult
    bottom: PurlinCheckResult
    second_moment_top_m4: float
    second_moment_bottom_m4: float
    effective_second_moment_m4: float
    top_load_fraction: float
    bottom_load_fraction: float
    permanent_line_load_kn_m: float
    roof_snow_line_load_kn_m: float
    self_mass_top_kg_m: float
    self_mass_bottom_kg_m: float
    permanent_contact_load_kn_m: float


REPORT_RESULT_PASS_TINT = "#d8f0dc"
REPORT_RESULT_FAIL_TINT = "#f7d3d3"
REPORT_LIMIT_TINT = "#fff1ad"


@dataclass(frozen=True)
class ReportHighlight:
    text: str
    color: str


@dataclass(frozen=True)
class ReportLine:
    text: str
    highlights: tuple[ReportHighlight, ...] = ()


ReportSection: TypeAlias = tuple[str, Sequence[str | ReportLine]]


# Keep equations as plain text in the calculation code. Only the PDF renderer
# turns these known variable names into mathematical notation; explicit names
# and word boundaries prevent changing Czech prose or units such as kg/m².
_REPORT_VARIABLE_SUFFIXES = {
    "w": ("fin,max", "inst,max", "G,inst", "S,inst", "fin", "inst", "lim"),
    "q": ("G,k,vrstvy", "G,k,krokev", "G,k", "S,k", "inst", "fin", "k", "d"),
    "f": ("c,0,k", "c,90,k", "c,0,d", "c,90,d", "c,β,d", "m,k", "v,k",
          "m,d", "v,d", "k", "d"),
    "k": ("mod", "def", "cr", "c,90"),
    "γ": ("G", "Q", "M"),
    "ψ": ("2",),
    "M": ("Ed,+,max", "Ed,-,max", "Ed", "Rd"),
    "V": ("Ed,max", "Ed", "Rd"),
    "F": ("c,90,Ed,max", "c,90,Ed", "c,β,Ed", "c,Ed"),
    "σ": ("c,90,d", "c,β,d", "c,d", "m,d"),
    "τ": ("d",),
    "R": ("c,90,d", "c,β,d", "top,Ed", "bottom,Ed", "total,Ed", "d"),
    "I": ("top", "bottom", "eff"),
    "EI": ("eff",),
    "η": ("top", "bottom"),
    "E": ("0,mean", "d"),
    "G": ("k",),
    "S": ("k",),
    "g": ("k,total", "k", "dod"),
    "s": ("line,k,total", "line,k", "k"),
    "b": ("ef", "t,s", "t,h", "k"),
    "h": ("top", "bottom", "k"),
    "L": ("up", "dol"),
    "m": ("vrstvy", "krokve", "top", "bottom", "A", "v"),
    "p": ("G",),
}
_REPORT_VARIABLE_MATH = {
    base + suffix: rf"${base}_{{\mathrm{{{suffix}}}}}$"
    for base, suffixes in _REPORT_VARIABLE_SUFFIXES.items()
    for suffix in suffixes
}
_REPORT_VARIABLE_PATTERN = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(variable)
        for variable in sorted(_REPORT_VARIABLE_MATH, key=len, reverse=True)
    )
    + r")(?!\w)"
)


def _report_math_text(text: str) -> str:
    """Render variable suffixes upright and subscripted, not as baseline text.

    Wrap the original text before calling this helper so a math expression is
    never split between lines. Leave any existing math spans untouched.
    """
    return "".join(
        part if index % 2 else _REPORT_VARIABLE_PATTERN.sub(
            lambda match: _REPORT_VARIABLE_MATH[match.group()], part
        )
        for index, part in enumerate(re.split(r"(\$[^$]*\$)", text))
    )


def _highlighted_line(
    text: str,
    *highlights: tuple[str, str],
) -> ReportLine:
    return ReportLine(
        text,
        tuple(
            ReportHighlight(highlight_text, color)
            for highlight_text, color in highlights
        ),
    )


def _result_tint(utilization: float) -> str:
    return (
        REPORT_RESULT_PASS_TINT
        if utilization < 1
        else REPORT_RESULT_FAIL_TINT
    )


def _highlight_check_values(
    lines: Sequence[str | ReportLine],
    *,
    demand: str,
    limit: str,
    utilization: float,
) -> tuple[ReportLine, ...]:
    """Link the calculated values to their final comparison."""
    return tuple(
        _highlighted_line(
            line.text if isinstance(line, ReportLine) else line,
            (demand, _result_tint(utilization)),
            (limit, REPORT_LIMIT_TINT),
        )
        for line in lines
    )


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
        self._pending_highlights: dict[
            Figure,
            list[tuple[Text, tuple[ReportHighlight, ...]]],
        ] = {}

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
        self._add_highlight_rectangles(figure)
        self._pdf.savefig(figure)

    def add_figure(self, figure: Figure) -> None:
        """Append a caller-prepared diagram page to the calculation report."""
        if self._pdf is None:
            raise RuntimeError("CalculationReport must be used as a context manager")
        self._page_count += 1
        figure.text(0.925, 0.025, f"Strana {self._page_count}", fontsize=7,
                    color="#555555", ha="right", va="bottom")
        self._save_page(figure)

    def _add_highlight_rectangles(self, figure: Figure) -> None:
        pending = self._pending_highlights.pop(figure, ())
        if not pending:
            return

        canvas = FigureCanvasAgg(figure)
        canvas.draw()
        renderer = canvas.get_renderer()
        inverse = figure.transFigure.inverted()
        padding_x_px = figure.dpi * 1.2 / 72
        padding_y_px = figure.dpi * 0.7 / 72

        for artist, highlights in pending:
            full_text = artist.get_text()
            full_bounds = artist.get_window_extent(renderer)
            font_properties = artist.get_fontproperties()
            for highlight in highlights:
                search_from = 0
                while True:
                    start = full_text.find(highlight.text, search_from)
                    if start < 0:
                        break
                    prefix_width = renderer.get_text_width_height_descent(
                        full_text[:start],
                        font_properties,
                        ismath="$" in full_text[:start],
                    )[0]
                    # Measure the actual formatted prefix: subscripts have a
                    # smaller font and cannot be measured as literal markup.
                    end = start + len(highlight.text)
                    through_highlight_width = renderer.get_text_width_height_descent(
                        full_text[:end],
                        font_properties,
                        ismath="$" in full_text[:end],
                    )[0]
                    highlight_width = through_highlight_width - prefix_width
                    lower_left = inverse.transform(
                        (
                            full_bounds.x0 + prefix_width - padding_x_px,
                            full_bounds.y0 - padding_y_px,
                        )
                    )
                    upper_right = inverse.transform(
                        (
                            full_bounds.x0
                            + prefix_width
                            + highlight_width
                            + padding_x_px,
                            full_bounds.y1 + padding_y_px,
                        )
                    )
                    rectangle = Rectangle(
                        lower_left,
                        upper_right[0] - lower_left[0],
                        upper_right[1] - lower_left[1],
                        transform=figure.transFigure,
                        facecolor=highlight.color,
                        edgecolor="none",
                        zorder=artist.get_zorder() - 0.1,
                    )
                    figure.add_artist(rectangle)
                    search_from = start + len(highlight.text)

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
            wrapped_lines: list[ReportLine] = []
            for supplied_line in supplied_lines:
                if isinstance(supplied_line, ReportLine):
                    line = supplied_line.text
                    highlights = supplied_line.highlights
                else:
                    line = str(supplied_line)
                    highlights = ()
                # Keep highlighted values and their units on the same line.
                for highlight in highlights:
                    line = line.replace(
                        highlight.text,
                        highlight.text.replace(" ", "\u00a0"),
                    )
                for wrapped_line in (
                    wrap(
                        line,
                        width=105,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                    or ("",)
                ):
                    wrapped_line = wrapped_line.replace("\u00a0", " ")
                    wrapped_lines.append(
                        ReportLine(
                            wrapped_line,
                            tuple(
                                highlight
                                for highlight in highlights
                                if highlight.text in wrapped_line
                            ),
                        )
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

            for report_line in lines:
                line = report_line.text
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
                artist = figure.text(
                    0.085,
                    y,
                    _report_math_text(line),
                    fontsize=8.4,
                    family="DejaVu Sans",
                    fontweight="bold" if is_verdict_line else "normal",
                    fontstyle="italic" if is_verdict_line else "normal",
                    va="top",
                )
                if report_line.highlights:
                    self._pending_highlights.setdefault(figure, []).append(
                        (artist, report_line.highlights)
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

        labels = tuple(_report_math_text(str(label)) for label in column_labels)
        if not labels:
            raise ValueError("column_labels must not be empty")
        normalized_rows = tuple(
            tuple(_report_math_text(str(value)) for value in row)
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
                    _report_math_text(line),
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
    _line_loads_kn_m: tuple[float, float] | None = None,
    _bearing_design_reaction_n: float | None = None,
    _snow_load_fraction: float = 1.0,
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
    if _line_loads_kn_m is not None:
        permanent_line_load_kn_m, roof_snow_line_load_kn_m = (
            _non_negative(value, "assigned line load") for value in _line_loads_kn_m
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
    unit_snow_response = response(
        tributary_horizontal_width_m * _positive(_snow_load_fraction, "snow load fraction")
    )

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
    if _bearing_design_reaction_n is not None:
        maximum_reaction_n = _non_negative(
            _bearing_design_reaction_n, "bearing_design_reaction_n"
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
        bearing_design_reaction_n=_bearing_design_reaction_n,
    )


def calculate_double_purlin_check(
    *,
    width_mm: float,
    height_top_mm: float,
    height_bottom_mm: float,
    span_m: float,
    **purlin_parameters,
) -> DoublePurlinCheckResult:
    """Simply supported, frictionless stack with no composite action.

    Both beams cover the same span and use the same material. Roof loads act
    on the top beam; maintained compressive contact gives equal deflections.
    Each beam bends about its OWN centroid: EI_eff = E * (I_top + I_bottom).
    The bottom support receives the full stack reaction. No connection/slip
    modulus is assumed. The remaining parameters match calculate_purlin_check.
    Contact opening, unequal spans/materials and connection action are outside
    this model; reject a permanent-load state requiring tensile contact.
    """
    width = _positive(width_mm, "width_mm") / 1000
    top_height = _positive(height_top_mm, "height_top_mm") / 1000
    bottom_height = _positive(height_bottom_mm, "height_bottom_mm") / 1000
    span = _positive(span_m, "span_m")
    common = dict(width_mm=width_mm, support_spans_m=(span,), **purlin_parameters)
    # This intermediate call supplies ONLY the common tributary loading and
    # total timber mass; its solid-section responses are deliberately unused.
    load_basis = calculate_purlin_check(
        height_mm=(top_height + bottom_height) * 1000, **common
    )
    density = _positive(purlin_parameters.get("timber_density_kg_m3", TIMBER_DENSITY_KG_M3),
                        "timber_density_kg_m3")
    top_mass, bottom_mass = (density * width * h for h in (top_height, bottom_height))
    top_i, bottom_i = (width * h**3 / 12 for h in (top_height, bottom_height))
    total_i = top_i + bottom_i
    top_fraction, bottom_fraction = top_i / total_i, bottom_i / total_i
    g = load_basis.permanent_line_load_kn_m
    snow = load_basis.roof_snow_line_load_kn_m
    contact = bottom_fraction * g - bottom_mass * GRAVITY_M_S2 / 1000
    if contact < -1e-12:
        raise ValueError(
            "unconnected beams would lose vertical contact under permanent load; "
            "this check requires maintained compression contact"
        )
    design_g = _positive(purlin_parameters.get("permanent_load_factor", PERMANENT_LOAD_FACTOR),
                         "permanent_load_factor")
    design_s = _positive(purlin_parameters.get("snow_load_factor", SNOW_LOAD_FACTOR), "snow_load_factor")
    full_reaction = (design_g * g + design_s * snow) * 1000 * span / 2
    top = calculate_purlin_check(
        height_mm=height_top_mm,
        _line_loads_kn_m=(top_fraction * g, top_fraction * snow),
        _snow_load_fraction=top_fraction, **common,
    )
    bottom = calculate_purlin_check(
        height_mm=height_bottom_mm,
        _line_loads_kn_m=(bottom_fraction * g, bottom_fraction * snow),
        _bearing_design_reaction_n=full_reaction,
        _snow_load_fraction=bottom_fraction, **common,
    )
    return DoublePurlinCheckResult(
        top, bottom, top_i, bottom_i, total_i, top_fraction, bottom_fraction,
        g, snow, top_mass, bottom_mass, max(0.0, contact),
    )


def _status(utilization: float) -> str:
    return "PASS" if utilization < 1 else "FAIL"


def _status_cz(utilization: float) -> str:
    return "VYHOVUJE" if utilization < 1 else "NEVYHOVUJE"


def _comparison_cz(demand: str, limit: str, utilization: float) -> str:
    """Use the unrounded result for both the relation and the strict verdict."""
    relation = "<" if utilization < 1 else ">" if utilization > 1 else "="
    return f"{demand} {relation} {limit}, {_status_cz(utilization)}"


def _cz(value: float, decimals: int) -> str:
    """Format a report number with a Czech decimal comma."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _cz_scientific(value: float, decimals: int = 8) -> str:
    """Format scientific notation with a Czech decimal comma."""
    return f"{value:.{decimals}e}".replace(".", ",")


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
    snow_load_text = _cz(snow_load, 2)
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
                _cz(mass_kg_m2, 1),
                f"{_cz(mass_kg_m2, 1)} × "
                f"{_cz(GRAVITY_M_S2, 2)} / 1000 = "
                f"{_cz(mass_kg_m2 * GRAVITY_M_S2 / 1000, 3)}",
            )
        )

    total_label = "Stálé zatížení celkem"
    if has_missing_layer:
        total_label = "Součet zadaných vrstev (neúplný)"
    rows.append(
        (
            total_label,
            _cz(total_mass_kg_m2, 1),
            f"{_cz(total_mass_kg_m2, 1)} × "
            f"{_cz(GRAVITY_M_S2, 2)} / 1000 = "
            f"{_cz(total_mass_kg_m2 * GRAVITY_M_S2 / 1000, 3)}",
        )
    )

    report.add_table(
        "Zatížení střechy",
        column_labels=(
            "Vrstva",
            "Hmotnost [kg/m²]",
            "Výpočet gk [kN/m²]",
        ),
        rows=rows,
        column_widths=(0.40, 0.19, 0.41),
        intro_lines=(
            f"Zatížení sněhem dle {snow_load_standard}: "
            f"{snow_load_zone}. sněhová oblast, "
            f"sk = {snow_load_text} kN/m².",
            "Hmotnosti vrstev jsou vztaženy k 1 m² skutečné šikmé "
            "plochy střechy.",
            f"Přepočet: gk = m × g / 1000; "
            f"g = {_cz(GRAVITY_M_S2, 2)} m/s².",
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
            TIMBER_MODIFICATION_FACTOR / timber_grade.material_partial_factor
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
        bending_stress_mpa = (
            abs(check.design_bending_moment_nm) / result.section_modulus_m3 / 1e6
        )
        shear_stress_mpa = (
            1.5 * abs(check.design_shear_force_n)
            / (SHEAR_EFFECTIVE_WIDTH_FACTOR * width_m * height_m) / 1e6
        )
        bending_demand = f"{_cz(bending_stress_mpa, 4)} MPa"
        bending_limit = f"{_cz(bending_strength_mpa, 4)} MPa"
        shear_demand = f"{_cz(shear_stress_mpa, 4)} MPa"
        shear_limit = f"{_cz(shear_strength_mpa, 4)} MPa"
        bearing_reaction = (
            f"{_cz(check.design_support_reaction_n / 1000, 3)} kN"
        )
        bearing_stress_mpa = (
            check.design_support_reaction_n / bearing_area_m2 / 1e6
        )
        bearing_demand = f"{_cz(bearing_stress_mpa, 4)} MPa"
        bearing_limit = f"{_cz(bearing_strength_mpa, 4)} MPa"
        immediate_deflection = (
            f"{_cz(check.characteristic_deflection_m * 1000, 2)} mm"
        )
        final_deflection = f"{_cz(check.final_deflection_m * 1000, 2)} mm"
        deflection_limit = (
            f"{_cz(result.maximum_deflection_m * 1000, 2)} mm"
        )

        report.add_sections(
            name,
            (
                (
                    "Geometrie a průřezové charakteristiky",
                    (
                        f"Materiál: {timber_grade.name}; "
                        f"E = {_cz(elastic_modulus_gpa, 2)} GPa; "
                        f"fm,k = {_cz(timber_grade.bending_strength_mpa, 2)} MPa; "
                        f"fv,k = {_cz(timber_grade.shear_strength_mpa, 2)} MPa; "
                        f"fc,0,k = "
                        f"{_cz(timber_grade.compression_parallel_mpa, 2)} MPa; "
                        f"fc,90,k = "
                        f"{_cz(timber_grade.compression_perpendicular_mpa, 2)} MPa.",
                        f"Rozpětí mezi podporami L = {_cz(span_m, 3)} m "
                        "podél krokve",
                        f"Sklon střechy α = {_cz(angle, 2)}°; cos α = "
                        f"{_cz(result.roof_cosine, 5)}",
                        f"b = {_cz(width_m, 3)} m; "
                        f"h = {_cz(height_m, 3)} m",
                        f"I = b h³ / 12 = {_cz(width_m, 3)} × "
                        f"{_cz(height_m, 3)}³ / 12 = "
                        f"{_cz_scientific(result.second_moment_m4)} m⁴",
                        f"W = b h² / 6 = {_cz(width_m, 3)} × "
                        f"{_cz(height_m, 3)}² / 6 = "
                        f"{_cz_scientific(result.section_modulus_m3)} m³",
                    ),
                ),
                (
                    "Charakteristická liniová zatížení kolmá ke krokvi",
                    (
                        f"Stálé plošné zatížení střešních vrstev "
                        f"gk = m × g / 1000 = "
                        f"{_cz(known_layer_total_kg_m2, 1)} kg/m² × "
                        f"{_cz(GRAVITY_M_S2, 2)} m/s² / 1000 = "
                        f"{_cz(roof_layer_surface_load_kn_m2, 3)} kN/m².",
                        f"Maximální osová vzdálenost krokví "
                        f"a = {_cz(spacing_m, 3)} m.",
                        "Pro jednu krokev tedy použijeme liniové zatížení "
                        "vrstev kolmé ke krokvi:",
                        f"qG,k,vrstvy = gk × a × cos α = "
                        f"{_cz(roof_layer_surface_load_kn_m2, 3)} kN/m² × "
                        f"{_cz(spacing_m, 3)} m × cos {_cz(angle, 2)}° = "
                        f"{_cz(layer_transverse_n_per_m / 1000, 3)} kN/m.",
                        f"Vlastní tíha krokve qG,k,krokev = "
                        f"b × h × ρ × g × cos α / 1000 = "
                        f"{_cz(width_m, 3)} m × {_cz(height_m, 3)} m × "
                        f"{_cz(density, 1)} kg/m³ × "
                        f"{_cz(GRAVITY_M_S2, 2)} m/s² × "
                        f"cos {_cz(angle, 2)}° / 1000 = "
                        f"{_cz(result.self_transverse_n_per_m / 1000, 3)} kN/m.",
                        f"Stálé liniové zatížení celkem qG,k = "
                        f"qG,k,vrstvy + qG,k,krokev = "
                        f"{_cz(layer_transverse_n_per_m / 1000, 3)} + "
                        f"{_cz(result.self_transverse_n_per_m / 1000, 3)} = "
                        f"{_cz(check.permanent_transverse_n_per_m / 1000, 3)} "
                        "kN/m.",
                        f"Zatížení od sněhu qS,k = sk × a × cos² α = "
                        f"{_cz(snow_load, 2)} kN/m² × "
                        f"{_cz(spacing_m, 3)} m × "
                        f"cos² {_cz(angle, 2)}° = "
                        f"{_cz(result.snow_transverse_n_per_m / 1000, 3)} kN/m.",
                        f"Charakteristické zatížení celkem qk = qG,k + qS,k = "
                        f"{_cz(check.permanent_transverse_n_per_m / 1000, 3)} + "
                        f"{_cz(result.snow_transverse_n_per_m / 1000, 3)} = "
                        f"{_cz(check.characteristic_transverse_n_per_m / 1000, 3)} "
                        "kN/m.",
                    ),
                ),
                (
                    "Posouzení - namáhání ohybem",
                    (
                        "Mezní stav únosnosti (MSÚ).",
                        f"Návrhové liniové zatížení qd = γG qG,k + "
                        f"γQ qS,k = {_cz(PERMANENT_LOAD_FACTOR, 2)} × "
                        f"{_cz(check.permanent_transverse_n_per_m / 1000, 3)} + "
                        f"{_cz(SNOW_LOAD_FACTOR, 2)} × "
                        f"{_cz(result.snow_transverse_n_per_m / 1000, 3)} = "
                        f"{_cz(check.design_transverse_n_per_m / 1000, 3)} kN/m.",
                        f"Návrhový ohybový moment MEd = qd L² / 8 = "
                        f"{_cz(check.design_transverse_n_per_m / 1000, 3)} kN/m × "
                        f"{_cz(span_m, 3)}² m² / 8 = "
                        f"{_cz(check.design_bending_moment_nm / 1000, 3)} kNm.",
                        f"Průřezový modul W = "
                        f"{_cz_scientific(result.section_modulus_m3)} m³ = "
                        f"{_cz(result.section_modulus_m3 * 1e9, 3)} mm³.",
                        _highlighted_line(
                            f"Návrhové napětí v ohybu σm,d = |MEd| / W = "
                            f"{_cz(abs(check.design_bending_moment_nm) / 1000, 3)} kNm "
                            f"× 10⁶ / {_cz(result.section_modulus_m3 * 1e9, 3)} mm³ "
                            f"= {bending_demand}.",
                            (bending_demand, _result_tint(check.bending_utilization)),
                        ),
                        _highlighted_line(
                            f"Mezní hodnota fm,d = fm,k × kmod / γM = "
                            f"{_cz(timber_grade.bending_strength_mpa, 2)} MPa × "
                            f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                            f"{_cz(timber_grade.material_partial_factor, 2)} = "
                            f"{bending_limit}.",
                            (bending_limit, REPORT_LIMIT_TINT),
                        ),
                        _highlighted_line(
                            _comparison_cz(
                                bending_demand, bending_limit,
                                check.bending_utilization,
                            ),
                            (
                                bending_demand,
                                _result_tint(check.bending_utilization),
                            ),
                            (bending_limit, REPORT_LIMIT_TINT),
                        ),
                    ),
                ),
                (
                    "Posouzení - namáhání smykem",
                    (
                        "Mezní stav únosnosti (MSÚ).",
                        f"Návrhová posouvající síla VEd = qd L / 2 = "
                        f"{_cz(check.design_transverse_n_per_m / 1000, 3)} kN/m × "
                        f"{_cz(span_m, 3)} m / 2 = "
                        f"{_cz(check.design_shear_force_n / 1000, 3)} kN.",
                        f"Účinná šířka bef = kcr × b = "
                        f"{_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR, 2)} × "
                        f"{_cz(width_m * 1000, 0)} mm = "
                        f"{_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR * width_m * 1000, 1)} mm.",
                        _highlighted_line(
                            "Návrhové smykové napětí τd = 1,5 |VEd| / "
                            "(kcr × b × h) = "
                            f"1,5 × {_cz(abs(check.design_shear_force_n) / 1000, 3)} kN "
                            f"× 1000 / ({_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR, 2)} × "
                            f"{_cz(width_m * 1000, 0)} mm × "
                            f"{_cz(height_m * 1000, 0)} mm) = {shear_demand}.",
                            (shear_demand, _result_tint(check.shear_utilization)),
                        ),
                        _highlighted_line(
                            f"Mezní hodnota fv,d = fv,k × kmod / γM = "
                            f"{_cz(timber_grade.shear_strength_mpa, 2)} MPa × "
                            f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                            f"{_cz(timber_grade.material_partial_factor, 2)} = {shear_limit}.",
                            (shear_limit, REPORT_LIMIT_TINT),
                        ),
                        _highlighted_line(
                            _comparison_cz(
                                shear_demand, shear_limit,
                                check.shear_utilization,
                            ),
                            (
                                shear_demand,
                                _result_tint(check.shear_utilization),
                            ),
                            (shear_limit, REPORT_LIMIT_TINT),
                        ),
                    ),
                ),
                (
                    "Posouzení - tlak šikmo k vláknům v uložení",
                    (
                        "Mezní stav únosnosti (MSÚ), tlak šikmo k vláknům.",
                        f"Úhel síly k vláknům β = 90° − α = "
                        f"90° − {_cz(angle, 2)}° = "
                        f"{_cz(check.bearing_angle_degrees, 2)}°.",
                        f"Návrhová svislá reakce Fc,β,Ed = VEd / cos α = "
                        f"{_cz(check.design_shear_force_n / 1000, 3)} kN / "
                        f"cos {_cz(angle, 2)}° = {bearing_reaction}.",
                        f"fc,0,d = fc,0,k × kmod / γM = "
                        f"{_cz(timber_grade.compression_parallel_mpa, 2)} × "
                        f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                        f"{_cz(timber_grade.material_partial_factor, 2)} = "
                        f"{_cz(compression_parallel_strength_mpa, 4)} MPa.",
                        f"fc,90,d = fc,90,k × kmod / γM = "
                        f"{_cz(timber_grade.compression_perpendicular_mpa, 2)} × "
                        f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                        f"{_cz(timber_grade.material_partial_factor, 2)} = "
                        f"{_cz(compression_perpendicular_strength_mpa, 4)} MPa; "
                        f"kc,90 = {_cz(BEARING_STRENGTH_FACTOR, 2)}.",
                        "fc,β,d = fc,0,d / [(fc,0,d / (kc,90 × fc,90,d)) "
                        f"× sin² β + cos² β] = "
                        f"{_cz(compression_parallel_strength_mpa, 4)} / "
                        f"[({_cz(compression_parallel_strength_mpa, 4)} / "
                        f"({_cz(BEARING_STRENGTH_FACTOR, 2)} × "
                        f"{_cz(compression_perpendicular_strength_mpa, 4)})) × "
                        f"sin² {_cz(check.bearing_angle_degrees, 2)}° + "
                        f"cos² {_cz(check.bearing_angle_degrees, 2)}°] = "
                        f"{_cz(bearing_strength_mpa, 4)} MPa.",
                        f"Plocha uložení A = b × l = "
                        f"{_cz(width_m * 1000, 0)} mm × "
                        f"{_cz(bearing_length, 0)} mm = "
                        f"{_cz(bearing_area_m2 * 1e6, 0)} mm².",
                        _highlighted_line(
                            f"Návrhové tlakové napětí σc,β,d = Fc,β,Ed / A = "
                            f"{bearing_reaction} × 1000 / "
                            f"{_cz(bearing_area_m2 * 1e6, 0)} mm² = "
                            f"{bearing_demand}.",
                            (
                                bearing_demand,
                                _result_tint(check.bearing_utilization),
                            ),
                        ),
                        _highlighted_line(
                            f"Mezní hodnota fc,β,d = {bearing_limit}.",
                            (bearing_limit, REPORT_LIMIT_TINT),
                        ),
                        _highlighted_line(
                            _comparison_cz(
                                bearing_demand, bearing_limit,
                                check.bearing_utilization,
                            ),
                            (
                                bearing_demand,
                                _result_tint(check.bearing_utilization),
                            ),
                            (bearing_limit, REPORT_LIMIT_TINT),
                        ),
                        "Samostatné posouzení zářezu krokve není zahrnuto.",
                    ),
                ),
                (
                    "Posouzení - okamžitý průhyb",
                    (
                        "Mezní stav použitelnosti (MSP).",
                        f"Charakteristické liniové zatížení qk = qG,k + "
                        f"qS,k = "
                        f"{_cz(check.permanent_transverse_n_per_m / 1000, 3)} + "
                        f"{_cz(result.snow_transverse_n_per_m / 1000, 3)} = "
                        f"{_cz(check.characteristic_transverse_n_per_m / 1000, 3)} "
                        "kN/m.",
                        f"Modul pružnosti E = {_cz(elastic_modulus_gpa, 2)} GPa.",
                        f"Moment setrvačnosti I = "
                        f"{_cz_scientific(result.second_moment_m4)} m⁴.",
                        f"wG,inst = 5 qG,k L⁴ / (384 E I) = 5 × "
                        f"({_cz(check.permanent_transverse_n_per_m / 1000, 3)} × 10³ N/m) × "
                        f"{_cz(span_m, 3)}⁴ m⁴ / [384 × "
                        f"({_cz(elastic_modulus_gpa, 2)} × 10⁹ N/m²) × "
                        f"{_cz_scientific(result.second_moment_m4)} m⁴] × 1000 = "
                        f"{_cz(check.permanent_immediate_deflection_m * 1000, 2)} mm.",
                        f"wS,inst = 5 qS,k L⁴ / (384 E I) = 5 × "
                        f"({_cz(result.snow_transverse_n_per_m / 1000, 3)} × 10³ N/m) × "
                        f"{_cz(span_m, 3)}⁴ m⁴ / [384 × "
                        f"({_cz(elastic_modulus_gpa, 2)} × 10⁹ N/m²) × "
                        f"{_cz_scientific(result.second_moment_m4)} m⁴] × 1000 = "
                        f"{_cz(check.snow_immediate_deflection_m * 1000, 2)} mm.",
                        _highlighted_line(
                            f"Celkový průhyb winst = wG,inst + wS,inst = "
                            f"{_cz(check.permanent_immediate_deflection_m * 1000, 2)} + "
                            f"{_cz(check.snow_immediate_deflection_m * 1000, 2)} = "
                            f"{immediate_deflection}.",
                            (
                                immediate_deflection,
                                _result_tint(
                                    check.characteristic_deflection_utilization
                                ),
                            ),
                        ),
                        _highlighted_line(
                            f"Mezní hodnota wlim = L/{_cz(deflection_ratio, 0)} = "
                            f"{_cz(span_m, 3)} m / "
                            f"{_cz(deflection_ratio, 0)} × 1000 = "
                            f"{deflection_limit}.",
                            (deflection_limit, REPORT_LIMIT_TINT),
                        ),
                        _highlighted_line(
                            _comparison_cz(
                                immediate_deflection, deflection_limit,
                                check.characteristic_deflection_utilization,
                            ),
                            (
                                immediate_deflection,
                                _result_tint(
                                    check.characteristic_deflection_utilization
                                ),
                            ),
                            (deflection_limit, REPORT_LIMIT_TINT),
                        ),
                    ),
                ),
                *(
                    (
                        (
                            "Posouzení - konečný průhyb včetně dotvarování",
                            (
                                "Mezní stav použitelnosti (MSP).",
                                f"Součinitel dotvarování kdef = "
                                f"{_cz(TIMBER_CREEP_FACTOR, 2)}.",
                                f"Kombinační součinitel sněhu ψ2 = "
                                f"{_cz(SNOW_CREEP_COMBINATION_FACTOR, 2)}.",
                                _highlighted_line(
                                    "wfin = wG,inst × (1 + kdef) + "
                                    "wS,inst × (1 + ψ2 × kdef) = "
                                    f"{_cz(check.permanent_immediate_deflection_m * 1000, 2)} × "
                                    f"(1 + {_cz(TIMBER_CREEP_FACTOR, 2)}) + "
                                    f"{_cz(check.snow_immediate_deflection_m * 1000, 2)} × "
                                    f"(1 + {_cz(SNOW_CREEP_COMBINATION_FACTOR, 2)} × "
                                    f"{_cz(TIMBER_CREEP_FACTOR, 2)}) = "
                                    f"{final_deflection}.",
                                    (
                                        final_deflection,
                                        _result_tint(
                                            check.final_deflection_utilization
                                        ),
                                    ),
                                ),
                                _highlighted_line(
                                    f"Mezní hodnota wlim = L/"
                                    f"{_cz(deflection_ratio, 0)} = "
                                    f"{_cz(span_m, 3)} m / "
                                    f"{_cz(deflection_ratio, 0)} × 1000 = "
                                    f"{deflection_limit}.",
                                    (deflection_limit, REPORT_LIMIT_TINT),
                                ),
                                _highlighted_line(
                                    _comparison_cz(
                                        final_deflection, deflection_limit,
                                        check.final_deflection_utilization,
                                    ),
                                    (
                                        final_deflection,
                                        _result_tint(
                                            check.final_deflection_utilization
                                        ),
                                    ),
                                    (deflection_limit, REPORT_LIMIT_TINT),
                                ),
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
                    "Double purlins use two equal-width, equal-material beams "
                    "in maintained vertical contact with free longitudinal slip: "
                    "EI_eff = E × (I_top + I_bottom), no composite action.",
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
                    f"fc,90,k and mean modulus E0,mean for C16/C18/C20/C22/C24: "
                    f"{REPORT_TIMBER_GRADES_STANDARD}.",
                    f"Combined glulam GL24c/GL28c characteristic strengths "
                    f"and mean modulus: {REPORT_GLULAM_GRADES_STANDARD}.",
                    f"Homogeneous glulam GL24h/GL28h characteristic strengths "
                    f"and mean modulus: {REPORT_GLULAM_GRADES_STANDARD}.",
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
                    f"γM = {TIMBER_MATERIAL_PARTIAL_FACTOR:g} for solid "
                    f"timber and {_TIMBER_GRADES['gl28h'].material_partial_factor:g} "
                    "for glulam; the selected grade determines γM.",
                    "Design strengths are calculated from characteristic "
                    "strengths as fd = kmod × fk / γM.",
                    "Bending criterion: σm,d = |MEd| / W < fm,d.",
                    "Shear criterion: τd = 1.5 |VEd| / (kcr × b × h) < fv,d, "
                    f"with kcr = {SHEAR_EFFECTIVE_WIDTH_FACTOR:g}.",
                    f"Bearing uses the entered contact area A = b × l and "
                    f"kc,90 = {BEARING_STRENGTH_FACTOR:g}. Rafters are "
                    "checked in compression at an angle to grain; purlins "
                    "are checked perpendicular to grain.",
                    "Bearing criterion: compressive stress σc,d = Fc,Ed / A "
                    "must be strictly smaller than the design bearing strength.",
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
                    f"Default timber density for self-weight is "
                    f"{TIMBER_DENSITY_KG_M3:g} kg/m³ and g = "
                    f"{GRAVITY_M_S2:g} m/s².",
                    "Density can be overridden per member; confirm the "
                    "selected timber product's self-weight.",
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
            tuple[str, str, RoofCheckResult | PurlinCheckResult | DoublePurlinCheckResult]
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
        result: RoofCheckResult | PurlinCheckResult | DoublePurlinCheckResult,
    ) -> None:
        self.entries.append((title, kind, result))

    def _entry_status(
        self,
        kind: str,
        result: RoofCheckResult | PurlinCheckResult | DoublePurlinCheckResult,
    ) -> str:
        if kind == "double_purlin":
            assert isinstance(result, DoublePurlinCheckResult)
            statuses = [
                _purlin_report_status(check, include_creep=self.include_creep)
                for check in (result.top, result.bottom)
            ]
            failed = any("FAIL" in status for status in statuses)
            incomplete = any("INCOMPLETE" in status for status in statuses)
            return ("FAIL; CHECK INCOMPLETE" if failed and incomplete else
                    "FAIL" if failed else "CHECK INCOMPLETE" if incomplete else "PASS")
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
        material_partial_factor=grade.material_partial_factor,
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
    roof_angle_degrees: float,
    rafter_width_mm: float,
    rafter_height_mm: float,
    rafter_spacing_m: float,
    snow_load_kn_m2: float,
    roof_layer_mass_kg_m2: float,
    timber_density_kg_m3: float,
    include_creep: bool,
    check: PurlinCheckResult,
    geometry_and_load_lines: Sequence[str] | None = None,
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
    roof_angle = _roof_angle(roof_angle_degrees)
    rafter_width_m = _positive(rafter_width_mm, "rafter_width_mm") / 1000
    rafter_height_m = _positive(rafter_height_mm, "rafter_height_mm") / 1000
    rafter_spacing = _positive(rafter_spacing_m, "rafter_spacing_m")
    snow_load = _non_negative(snow_load_kn_m2, "snow_load_kn_m2")
    layer_mass = _non_negative(roof_layer_mass_kg_m2, "roof_layer_mass_kg_m2")
    density = _positive(timber_density_kg_m3, "timber_density_kg_m3")
    grade = _resolve_timber_grade(material)
    design_strength_multiplier = (
        TIMBER_MODIFICATION_FACTOR / grade.material_partial_factor
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
    immediate_line_load_kn_m = (
        check.permanent_line_load_kn_m + check.roof_snow_line_load_kn_m
    )
    final_line_load_kn_m = (
        check.permanent_line_load_kn_m * (1 + TIMBER_CREEP_FACTOR)
        + check.roof_snow_line_load_kn_m
        * (1 + SNOW_CREEP_COMBINATION_FACTOR * TIMBER_CREEP_FACTOR)
    )
    spans_text = " + ".join(
        f"{_cz(span, 3)} m" for span in check.span_lengths_m
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
    if check.bearing_design_reaction_n is not None:
        maximum_reaction_n = check.bearing_design_reaction_n
    positive_bending_stress_mpa = maximum_positive_moment_nm / section_modulus_m3 / 1e6
    negative_bending_stress_mpa = maximum_negative_moment_nm / section_modulus_m3 / 1e6
    shear_stress_mpa = (
        1.5 * maximum_shear_n
        / (SHEAR_EFFECTIVE_WIDTH_FACTOR * purlin_width_m * purlin_height_m) / 1e6
    )
    positive_bending_demand = f"{_cz(positive_bending_stress_mpa, 4)} MPa"
    negative_bending_demand = f"{_cz(negative_bending_stress_mpa, 4)} MPa"
    bending_limit = f"{_cz(bending_strength_mpa, 4)} MPa"
    shear_demand = f"{_cz(shear_stress_mpa, 4)} MPa"
    shear_limit = f"{_cz(shear_strength_mpa, 4)} MPa"
    bearing_area_mm2 = purlin_width_mm * bearing_length
    bearing_stress_mpa = maximum_reaction_n / bearing_area_mm2
    bearing_demand = f"{_cz(bearing_stress_mpa, 4)} MPa"
    bearing_limit = f"{_cz(compression_strength_mpa, 4)} MPa"
    bearing_force_symbol = "Fc,90,Ed,max" if is_continuous else "Fc,90,Ed"

    def beam_model_inputs(line_load_kn_m: float) -> str:
        return (
            "K(EI,L) u = F(q,L), "
            f"E = {_cz(elastic_modulus_gpa, 2)} × 10⁹ N/m², "
            f"I = {_cz_scientific(second_moment_m4)} m⁴, "
            f"L = ({spans_text}), q = "
            f"{_cz(line_load_kn_m, 3)} × 10³ N/m"
        )

    bending_limit_calculation = (
        "Mezní hodnota fm,d = fm,k × kmod / γM = "
        f"{_cz(grade.bending_strength_mpa, 2)} MPa × "
        f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
        f"{_cz(grade.material_partial_factor, 2)} = {bending_limit}."
    )

    def bending_stress_calculation(moment_nm: float, symbol: str) -> str:
        return (
            f"Návrhové napětí v ohybu σm,d = |{symbol}| / W = "
            f"{_cz(abs(moment_nm) / 1000, 3)} kNm × 10⁶ / "
            f"{_cz(section_modulus_m3 * 1e9, 3)} mm³ = "
            f"{_cz(abs(moment_nm) / section_modulus_m3 / 1e6, 4)} MPa."
        )

    def deflection_calculation(
        *,
        span: float,
        line_load_kn_m: float,
        deflection_m: float,
        symbol: str,
    ) -> str:
        result_text = f"{_cz(deflection_m * 1000, 2)} mm"
        if is_continuous:
            text = (
                f"{symbol} z prutového modelu {beam_model_inputs(line_load_kn_m)}: "
                f"{symbol},max = {result_text}."
            )
        else:
            text = (
                f"{symbol} = 5 q L⁴ / (384 E I) = 5 × "
                f"({_cz(line_load_kn_m, 3)} × 10³ N/m) × "
                f"{_cz(span, 3)}⁴ m⁴ / [384 × "
                f"({_cz(elastic_modulus_gpa, 2)} × 10⁹ N/m²) × "
                f"{_cz_scientific(second_moment_m4)} m⁴] × 1000 = "
                f"{result_text}."
            )
        return text

    sections: list[ReportSection] = [
        (
            "Geometrie, materiál a zatížení",
            (
                f"Materiál: {grade.name}; "
                f"E = {_cz(elastic_modulus_gpa, 2)} GPa.",
                f"Charakteristické pevnosti: fm,k = "
                f"{_cz(grade.bending_strength_mpa, 2)} MPa; fv,k = "
                f"{_cz(grade.shear_strength_mpa, 2)} MPa; fc,90,k = "
                f"{_cz(grade.compression_perpendicular_mpa, 2)} MPa.",
                f"Průřez {member_name} b × h = "
                f"{_cz(purlin_width_mm, 0)} × "
                f"{_cz(purlin_height_mm, 0)} mm.",
                f"I = b h³ / 12 = {_cz(purlin_width_m, 3)} × "
                f"{_cz(purlin_height_m, 3)}³ / 12 = "
                f"{_cz_scientific(second_moment_m4)} m⁴.",
                f"W = b h² / 6 = {_cz(purlin_width_m, 3)} × "
                f"{_cz(purlin_height_m, 3)}² / 6 = "
                f"{_cz_scientific(section_modulus_m3)} m³.",
                f"Rozpětí L = {spans_text}.",
                f"Šířka připadající na vaznici po sklonu "
                f"bt,s = Lup + Ldol / 2 = "
                f"{_cz(check.upper_rafter_length_m, 3)} m + "
                f"{_cz(check.lower_rafter_span_m, 3)} m / 2 = "
                f"{_cz(check.tributary_slope_width_m, 3)} m.",
                f"Vodorovná šířka pro sníh bt,h = bt,s × cos α = "
                f"{_cz(check.tributary_slope_width_m, 3)} m × "
                f"cos {_cz(roof_angle, 2)}° = "
                f"{_cz(check.tributary_horizontal_width_m, 3)} m.",
                f"Hmotnost vrstev na metr vaznice mvrstvy = "
                f"mA × bt,s = {_cz(layer_mass, 1)} kg/m² × "
                f"{_cz(check.tributary_slope_width_m, 3)} m = "
                f"{_cz(check.roof_layer_line_mass_kg_m, 1)} kg/m.",
                f"Hmotnost krokví na metr vaznice mkrokve = "
                f"ρ × bk × hk × bt,s / a = {_cz(density, 1)} kg/m³ × "
                f"{_cz(rafter_width_m, 3)} m × "
                f"{_cz(rafter_height_m, 3)} m × "
                f"{_cz(check.tributary_slope_width_m, 3)} m / "
                f"{_cz(rafter_spacing, 3)} m = "
                f"{_cz(check.rafter_line_mass_kg_m, 1)} kg/m.",
                f"Vlastní hmotnost vaznice mv = ρ × b × h = "
                f"{_cz(density, 1)} kg/m³ × {_cz(purlin_width_m, 3)} m × "
                f"{_cz(purlin_height_m, 3)} m = "
                f"{_cz(check.purlin_self_mass_kg_m, 1)} kg/m.",
                f"Stálé liniové zatížení gk = "
                f"(mvrstvy + mkrokve + mv) × g / 1000 + gdod = "
                f"({_cz(check.roof_layer_line_mass_kg_m, 1)} + "
                f"{_cz(check.rafter_line_mass_kg_m, 1)} + "
                f"{_cz(check.purlin_self_mass_kg_m, 1)}) kg/m × "
                f"{_cz(GRAVITY_M_S2, 2)} m/s² / 1000 + "
                f"{_cz(check.additional_permanent_load_kn_m, 3)} kN/m = "
                f"{_cz(check.permanent_line_load_kn_m, 3)} kN/m.",
                f"Zatížení sněhem sline,k = sk × bt,h = "
                f"{_cz(snow_load, 2)} kN/m² × "
                f"{_cz(check.tributary_horizontal_width_m, 3)} m = "
                f"{_cz(check.roof_snow_line_load_kn_m, 3)} kN/m.",
                f"Okamžité liniové zatížení qinst = gk + sline,k = "
                f"{_cz(check.permanent_line_load_kn_m, 3)} + "
                f"{_cz(check.roof_snow_line_load_kn_m, 3)} = "
                f"{_cz(immediate_line_load_kn_m, 3)} kN/m.",
                f"Konečné ekvivalentní zatížení qfin = "
                f"gk × (1 + kdef) + sline,k × (1 + ψ2 × kdef) = "
                f"{_cz(check.permanent_line_load_kn_m, 3)} × "
                f"(1 + {_cz(TIMBER_CREEP_FACTOR, 2)}) + "
                f"{_cz(check.roof_snow_line_load_kn_m, 3)} × "
                f"(1 + {_cz(SNOW_CREEP_COMBINATION_FACTOR, 2)} × "
                f"{_cz(TIMBER_CREEP_FACTOR, 2)}) = "
                f"{_cz(final_line_load_kn_m, 3)} kN/m.",
                f"Návrhové liniové zatížení qd = γG gk + γQ sline,k = "
                f"{_cz(PERMANENT_LOAD_FACTOR, 2)} × "
                f"{_cz(check.permanent_line_load_kn_m, 3)} + "
                f"{_cz(SNOW_LOAD_FACTOR, 2)} × "
                f"{_cz(check.roof_snow_line_load_kn_m, 3)} = "
                f"{_cz(design_line_load_kn_m, 3)} kN/m.",
                f"Použité součinitele: "
                f"γG = {_cz(PERMANENT_LOAD_FACTOR, 2)}; "
                f"γQ = {_cz(SNOW_LOAD_FACTOR, 2)}; "
                f"kmod = {_cz(TIMBER_MODIFICATION_FACTOR, 2)}; "
                f"γM = {_cz(grade.material_partial_factor, 2)}.",
                f"Mez průhybu = L/{_cz(ratio, 0)}.",
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

    if geometry_and_load_lines is not None:
        sections[0] = ("Geometrie, materiál a zatížení", tuple(geometry_and_load_lines))

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
                "Posouzení - okamžitý průhyb"
                + field_suffix.format(index=index),
                _highlight_check_values((
                    "Mezní stav použitelnosti (MSP).",
                    f"Rozpětí L = {_cz(span, 3)} m.",
                    deflection_calculation(
                        span=span,
                        line_load_kn_m=immediate_line_load_kn_m,
                        deflection_m=deflection,
                        symbol="winst",
                    ),
                    f"Mezní hodnota wlim = L/{_cz(ratio, 0)} = "
                    f"{_cz(span, 3)} m / {_cz(ratio, 0)} × 1000 = "
                    f"{_cz(limit * 1000, 2)} mm.",
                    _comparison_cz(
                        f"{_cz(deflection * 1000, 2)} mm",
                        f"{_cz(limit * 1000, 2)} mm", utilization,
                    ),
                ),
                    demand=f"{_cz(deflection * 1000, 2)} mm",
                    limit=f"{_cz(limit * 1000, 2)} mm",
                    utilization=utilization,
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
                    "Posouzení - konečný průhyb včetně dotvarování"
                    + field_suffix.format(index=index),
                    _highlight_check_values((
                        "Mezní stav použitelnosti (MSP).",
                        f"Rozpětí L = {_cz(span, 3)} m.",
                        deflection_calculation(
                            span=span,
                            line_load_kn_m=final_line_load_kn_m,
                            deflection_m=deflection,
                            symbol="wfin",
                        ),
                        f"Mezní hodnota wlim = L/{_cz(ratio, 0)} = "
                        f"{_cz(span, 3)} m / {_cz(ratio, 0)} × 1000 = "
                        f"{_cz(limit * 1000, 2)} mm.",
                        _comparison_cz(
                            f"{_cz(deflection * 1000, 2)} mm",
                            f"{_cz(limit * 1000, 2)} mm", utilization,
                        ),
                    ),
                        demand=f"{_cz(deflection * 1000, 2)} mm",
                        limit=f"{_cz(limit * 1000, 2)} mm",
                        utilization=utilization,
                    ),
                )
            )

    sections.extend(
        (
            (
                "Posouzení - namáhání ohybem",
                (
                    "Mezní stav únosnosti (MSÚ).",
                    (
                        f"Maximální kladný moment z prutového modelu "
                        f"{beam_model_inputs(design_line_load_kn_m)}: "
                        f"MEd,+,max = "
                        f"{_cz(maximum_positive_moment_nm / 1000, 3)} kNm."
                        if is_continuous
                        else f"Návrhový moment MEd = qd L² / 8 = "
                        f"{_cz(design_line_load_kn_m, 3)} kN/m × "
                        f"{_cz(check.span_lengths_m[0], 3)}² m² / 8 = "
                        f"{_cz(maximum_positive_moment_nm / 1000, 3)} kNm."
                    ),
                    f"Průřezový modul W = {_cz_scientific(section_modulus_m3)} m³ = "
                    f"{_cz(section_modulus_m3 * 1e9, 3)} mm³.",
                    bending_stress_calculation(
                        maximum_positive_moment_nm,
                        "MEd,+,max" if is_continuous else "MEd",
                    ),
                    bending_limit_calculation,
                    _comparison_cz(
                        positive_bending_demand, bending_limit,
                        check.positive_bending_utilization,
                    ),
                ),
            ),
            *(
                (
                    (
                        "Posouzení - namáhání ohybem - negativní moment",
                        (
                            "Mezní stav únosnosti (MSÚ).",
                            f"Maximální záporný moment z prutového modelu "
                            f"{beam_model_inputs(design_line_load_kn_m)}: "
                            f"|MEd,-,max| = "
                            f"{_cz(maximum_negative_moment_nm / 1000, 3)} kNm.",
                            f"Průřezový modul W = {_cz_scientific(section_modulus_m3)} m³ = "
                            f"{_cz(section_modulus_m3 * 1e9, 3)} mm³.",
                            bending_stress_calculation(maximum_negative_moment_nm, "MEd,-,max"),
                            bending_limit_calculation,
                            _comparison_cz(
                                negative_bending_demand, bending_limit,
                                check.negative_bending_utilization,
                            ),
                        ),
                    ),
                )
                if is_continuous
                else ()
            ),
            (
                "Posouzení - namáhání smykem",
                (
                    "Mezní stav únosnosti (MSÚ).",
                    (
                        f"Maximální posouvající síla z prutového modelu "
                        f"{beam_model_inputs(design_line_load_kn_m)}: "
                        f"VEd,max = {_cz(maximum_shear_n / 1000, 3)} kN."
                        if is_continuous
                        else f"Návrhová posouvající síla VEd = qd L / 2 = "
                        f"{_cz(design_line_load_kn_m, 3)} kN/m × "
                        f"{_cz(check.span_lengths_m[0], 3)} m / 2 = "
                        f"{_cz(maximum_shear_n / 1000, 3)} kN."
                    ),
                    f"Účinná šířka bef = kcr × b = "
                    f"{_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR, 2)} × "
                    f"{_cz(purlin_width_mm, 0)} mm = "
                    f"{_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR * purlin_width_mm, 1)} mm.",
                    "Návrhové smykové napětí τd = 1,5 |VEd| / (kcr × b × h) = "
                    f"1,5 × {_cz(maximum_shear_n / 1000, 3)} kN × 1000 / "
                    f"({_cz(SHEAR_EFFECTIVE_WIDTH_FACTOR, 2)} × "
                    f"{_cz(purlin_width_mm, 0)} mm × {_cz(purlin_height_mm, 0)} mm) = "
                    f"{shear_demand}.",
                    f"Mezní hodnota fv,d = fv,k × kmod / γM = "
                    f"{_cz(grade.shear_strength_mpa, 2)} MPa × "
                    f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                    f"{_cz(grade.material_partial_factor, 2)} = {shear_limit}.",
                    _comparison_cz(
                        shear_demand, shear_limit,
                        check.shear_utilization,
                    ),
                ),
            ),
            (
                "Posouzení - tlak kolmo k vláknům v uložení",
                (
                    "Mezní stav únosnosti (MSÚ), tlak kolmo k vláknům.",
                    f"Mezní hodnota fc,90,d = "
                    f"kc,90 × fc,90,k × kmod / γM = "
                    f"{_cz(BEARING_STRENGTH_FACTOR, 2)} × "
                    f"{_cz(grade.compression_perpendicular_mpa, 2)} MPa × "
                    f"{_cz(TIMBER_MODIFICATION_FACTOR, 2)} / "
                    f"{_cz(grade.material_partial_factor, 2)} = "
                    f"{bearing_limit}.",
                    f"Plocha uložení A = b × l = "
                    f"{_cz(purlin_width_mm, 0)} mm × "
                    f"{_cz(bearing_length, 0)} mm = "
                    f"{_cz(bearing_area_mm2, 0)} mm².",
                    (
                        f"Celková síla v uložení dolního nosníku "
                        f"Fc,90,Ed = Rtop,Ed + Rbottom,Ed = "
                        f"{_cz((maximum_reaction_n - max(abs(r) for r in check.design_response.support_reactions_n)) / 1000, 3)} + "
                        f"{_cz(max(abs(r) for r in check.design_response.support_reactions_n) / 1000, 3)} = "
                        f"{_cz(maximum_reaction_n / 1000, 3)} kN."
                        if check.bearing_design_reaction_n is not None else
                        f"Maximální reakce z prutového modelu "
                        f"{beam_model_inputs(design_line_load_kn_m)}: "
                        f"Fc,90,Ed,max = "
                        f"{_cz(maximum_reaction_n / 1000, 3)} kN."
                        if is_continuous
                        else f"Reakce Fc,90,Ed = qd L / 2 = "
                        f"{_cz(design_line_load_kn_m, 3)} kN/m × "
                        f"{_cz(check.span_lengths_m[0], 3)} m / 2 = "
                        f"{_cz(maximum_reaction_n / 1000, 3)} kN."
                    ),
                    f"Návrhové tlakové napětí σc,90,d = {bearing_force_symbol} / A = "
                    f"{_cz(maximum_reaction_n / 1000, 3)} kN × 1000 / "
                    f"{_cz(bearing_area_mm2, 0)} mm² = {bearing_demand}.",
                    _comparison_cz(
                        bearing_demand, bearing_limit, check.bearing_utilization,
                    ),
                ),
            ),
        )
    )

    strength_checks = {
        "Posouzení - namáhání ohybem": (
            positive_bending_demand,
            bending_limit,
            check.positive_bending_utilization,
        ),
        "Posouzení - namáhání ohybem - negativní moment": (
            negative_bending_demand,
            bending_limit,
            check.negative_bending_utilization,
        ),
        "Posouzení - namáhání smykem": (
            shear_demand,
            shear_limit,
            check.shear_utilization,
        ),
        "Posouzení - tlak kolmo k vláknům v uložení": (
            bearing_demand,
            bearing_limit,
            check.bearing_utilization,
        ),
    }
    for index, (heading, lines) in enumerate(sections):
        if heading in strength_checks:
            demand, limit, utilization = strength_checks[heading]
            sections[index] = (
                heading,
                _highlight_check_values(
                    lines,
                    demand=demand,
                    limit=limit,
                    utilization=utilization,
                ),
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
        material_partial_factor=grade.material_partial_factor,
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
        roof_angle_degrees=roof_angle,
        rafter_width_mm=rafter_width_mm,
        rafter_height_mm=rafter_height_mm,
        rafter_spacing_m=rafter_spacing,
        snow_load_kn_m2=snow_load,
        roof_layer_mass_kg_m2=(
            check.roof_layer_line_mass_kg_m
            / check.tributary_slope_width_m
        ),
        timber_density_kg_m3=timber_density,
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


def check_double_purlin(
    *,
    title: str,
    material: str | TimberGrade,
    width: float,
    height_top: float,
    height_bottom: float,
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
) -> DoublePurlinCheckResult:
    """Report two stacked beams without shear connection/composite action.

    Same API as check_purlin, replacing height with height_top/height_bottom.
    Geometry uses metres; elastic_modulus uses GPa. Both beams have equal width,
    material and span, with free longitudinal slip and maintained normal contact.
    The bottom beam bears on the two walls; the top bears on the bottom at the
    same ends. bearing_length applies to both end interfaces. Connections,
    lateral stability and deformation of the contact surfaces are not checked.
    """
    session = _active_session()
    normalized_title = str(title).strip()
    if not normalized_title:
        raise ValueError("title must be a non-empty string")
    grade = _resolve_timber_grade(material)
    layers = ROOF_LAYERS_KG_M2 if roof_layers is None else roof_layers
    width_mm = _positive(width, "width") * 1000
    top_mm = _positive(height_top, "height_top") * 1000
    bottom_mm = _positive(height_bottom, "height_bottom") * 1000
    bearing_mm = _positive(width if bearing_length is None else bearing_length,
                           "bearing_length") * 1000
    modulus = (grade.elastic_modulus_gpa if elastic_modulus is None
               else _positive(elastic_modulus, "elastic_modulus"))
    check = calculate_double_purlin_check(
        width_mm=width_mm, height_top_mm=top_mm, height_bottom_mm=bottom_mm,
        span_m=span, upper_rafter_length_m=rafter_length_above,
        lower_rafter_span_m=lower_rafter_span, roof_angle_degrees=roof_angle,
        rafter_width_mm=_positive(rafter_width, "rafter_width") * 1000,
        rafter_height_mm=_positive(rafter_height, "rafter_height") * 1000,
        rafter_spacing_m=rafter_spacing, deflection_ratio=max_deflection,
        elastic_modulus_gpa=modulus, snow_load_kn_m2=snow_load,
        roof_layers_kg_m2=layers, additional_permanent_load_kn_m=additional_load,
        timber_density_kg_m3=timber_density,
        bending_strength_mpa=grade.bending_strength_mpa,
        shear_strength_mpa=grade.shear_strength_mpa,
        compression_perpendicular_mpa=grade.compression_perpendicular_mpa,
        material_partial_factor=grade.material_partial_factor,
        bearing_length_mm=bearing_mm,
    )
    session.prepare_inputs(snow_load=snow_load, roof_layers=layers)
    g, snow = check.permanent_line_load_kn_m, check.roof_snow_line_load_kn_m
    qd = PERMANENT_LOAD_FACTOR * g + SNOW_LOAD_FACTOR * snow
    basis = check.top
    total_reaction = check.bottom.bearing_design_reaction_n
    model_lines = (
        "Dva nosníky na sobě, prosté podepření na stejném rozpětí. "
        "Zatížení střechy působí na horní nosník; dolní nosník leží na stěnách.",
        "Bez smykového spojení, bez tření; volný podélný prokluz. "
        "Předpokládá se tuhý svislý tlakový kontakt a společný průhyb, "
        "nikoliv spolupůsobení jako jednoho vysokého průřezu.",
        f"Materiál obou nosníků: {grade.name}; E = {_cz(modulus, 2)} GPa. "
        f"Šířka b = {_cz(width_mm, 0)} mm; htop = {_cz(top_mm, 0)} mm; "
        f"hbottom = {_cz(bottom_mm, 0)} mm; L = {_cz(span, 3)} m.",
        f"Itop = b htop³ / 12 = {_cz(width, 3)} × {_cz(height_top, 3)}³ / 12 = "
        f"{_cz_scientific(check.second_moment_top_m4)} m⁴.",
        f"Ibottom = b hbottom³ / 12 = {_cz(width, 3)} × {_cz(height_bottom, 3)}³ / 12 = "
        f"{_cz_scientific(check.second_moment_bottom_m4)} m⁴.",
        f"Ieff = Itop + Ibottom = {_cz_scientific(check.second_moment_top_m4)} + "
        f"{_cz_scientific(check.second_moment_bottom_m4)} = "
        f"{_cz_scientific(check.effective_second_moment_m4)} m⁴.",
        f"EIeff = E × Ieff = {_cz(modulus, 2)} × 10⁹ × "
        f"{_cz_scientific(check.effective_second_moment_m4)} = "
        f"{_cz_scientific(modulus * 1e9 * check.effective_second_moment_m4)} Nm².",
        "Každý nosník se ohýbá kolem vlastní neutrální osy; "
        "Steinerovy členy mezi nosníky se nezapočítávají.",
        f"Podíl horního nosníku ηtop = Itop / Ieff = "
        f"{_cz_scientific(check.second_moment_top_m4)} / "
        f"{_cz_scientific(check.effective_second_moment_m4)} = {_cz(check.top_load_fraction, 6)}.",
        f"Podíl dolního nosníku ηbottom = Ibottom / Ieff = "
        f"{_cz_scientific(check.second_moment_bottom_m4)} / "
        f"{_cz_scientific(check.effective_second_moment_m4)} = {_cz(check.bottom_load_fraction, 6)}.",
        f"Připadající šířka po sklonu bt,s = Lup + Ldol / 2 = "
        f"{_cz(rafter_length_above, 3)} + {_cz(lower_rafter_span, 3)} / 2 = "
        f"{_cz(basis.tributary_slope_width_m, 3)} m.",
        f"Vodorovná šířka bt,h = bt,s × cos α = "
        f"{_cz(basis.tributary_slope_width_m, 3)} × cos {_cz(roof_angle, 2)}° = "
        f"{_cz(basis.tributary_horizontal_width_m, 3)} m.",
        f"Hmotnost vrstev mvrstvy = mA × bt,s = "
        f"{_cz(basis.roof_layer_line_mass_kg_m / basis.tributary_slope_width_m, 1)} × "
        f"{_cz(basis.tributary_slope_width_m, 3)} = {_cz(basis.roof_layer_line_mass_kg_m, 1)} kg/m.",
        f"Hmotnost krokví mkrokve = ρ bk hk bt,s / a = "
        f"{_cz(timber_density, 1)} × {_cz(rafter_width, 3)} × {_cz(rafter_height, 3)} × "
        f"{_cz(basis.tributary_slope_width_m, 3)} / {_cz(rafter_spacing, 3)} = "
        f"{_cz(basis.rafter_line_mass_kg_m, 1)} kg/m.",
        f"Vlastní hmotnosti mtop = ρ b htop = {_cz(timber_density, 1)} × "
        f"{_cz(width, 3)} × {_cz(height_top, 3)} = {_cz(check.self_mass_top_kg_m, 1)} kg/m; "
        f"mbottom = ρ b hbottom = {_cz(timber_density, 1)} × {_cz(width, 3)} × "
        f"{_cz(height_bottom, 3)} = {_cz(check.self_mass_bottom_kg_m, 1)} kg/m.",
        f"gk = (mvrstvy + mkrokve + mtop + mbottom) × g / 1000 + gdod = "
        f"({_cz(basis.roof_layer_line_mass_kg_m, 1)} + {_cz(basis.rafter_line_mass_kg_m, 1)} + "
        f"{_cz(check.self_mass_top_kg_m, 1)} + {_cz(check.self_mass_bottom_kg_m, 1)}) × "
        f"{_cz(GRAVITY_M_S2, 2)} / 1000 + {_cz(additional_load, 3)} = {_cz(g, 3)} kN/m.",
        f"sline,k = sk × bt,h = {_cz(snow_load, 2)} × "
        f"{_cz(basis.tributary_horizontal_width_m, 3)} = {_cz(snow, 3)} kN/m.",
        f"Tlakový kontakt od stálého zatížení pG = ηbottom gk - mbottom g / 1000 = "
        f"{_cz(check.bottom_load_fraction, 6)} × {_cz(g, 3)} - "
        f"{_cz(check.self_mass_bottom_kg_m, 1)} × {_cz(GRAVITY_M_S2, 2)} / 1000 = "
        f"{_cz(check.permanent_contact_load_kn_m, 4)} kN/m. "
        "Kontakt nemusí přenášet tah; kladné přitížení sněhem tlak dále zvyšuje.",
        f"qd = γG gk + γQ sline,k = {_cz(PERMANENT_LOAD_FACTOR, 2)} × {_cz(g, 3)} + "
        f"{_cz(SNOW_LOAD_FACTOR, 2)} × {_cz(snow, 3)} = {_cz(qd, 3)} kN/m.",
        f"Celková reakce v každé podpoře Rtotal,Ed = qd L / 2 = "
        f"{_cz(qd, 3)} × {_cz(span, 3)} / 2 = {_cz(total_reaction / 1000, 3)} kN.",
        "Dolní uložení přenáší celou reakci dvojice, nikoliv pouze její podíl v ohybu. "
        "Stejná délka uložení se předpokládá pro stěnu i koncový kontakt nosníků.",
        "Neověřuje se lokální stlačení průběžného kontaktu, klopení, boční zajištění "
        "ani spojovací prostředky. Pružnost smykového spojení se zde nezavádí.",
        "Výpočet používá nezaokrouhlené hodnoty; zobrazené mezivýsledky jsou zaokrouhlené.",
    )
    session.report.add_sections(
        normalized_title + " – model dvojité vaznice", (("Model a rozdělení zatížení", model_lines),),
        footer_title="Předběžný statický výpočet střechy", page_label="Strana",
        continuation_label="pokračování",
    )
    print(f"\n{normalized_title}: UNCONNECTED stacked purlin; free longitudinal slip.")
    print(f"  I_eff = I_top + I_bottom = {check.effective_second_moment_m4:.8g} m^4; "
          f"load shares top/bottom = {check.top_load_fraction:.3%}/{check.bottom_load_fraction:.3%}")
    print(f"  Stack permanent/snow load = {g:.3f}/{snow:.3f} kN/m; "
          f"both beams' self-mass = {check.self_mass_top_kg_m + check.self_mass_bottom_kg_m:.1f} kg/m")
    print(f"  Compressive contact under permanent load = {check.permanent_contact_load_kn_m:.4f} kN/m; "
          "no connector stiffness or composite action assumed.")
    for label, height_mm, fraction, component in (
        ("Horní nosník", top_mm, check.top_load_fraction, check.top),
        ("Dolní nosník", bottom_mm, check.bottom_load_fraction, check.bottom),
    ):
        h = height_mm / 1000
        i = width * h**3 / 12
        w = width * h**2 / 6
        gi, si = component.permanent_line_load_kn_m, component.roof_snow_line_load_kn_m
        component_qd = PERMANENT_LOAD_FACTOR * gi + SNOW_LOAD_FACTOR * si
        geometry = (
            f"{label}: {grade.name}; b × h = {_cz(width_mm, 0)} × {_cz(height_mm, 0)} mm; "
            f"L = {_cz(span, 3)} m; E = {_cz(modulus, 2)} GPa.",
            f"I = b h³ / 12 = {_cz(width, 3)} × {_cz(h, 3)}³ / 12 = {_cz_scientific(i)} m⁴.",
            f"W = b h² / 6 = {_cz(width, 3)} × {_cz(h, 3)}² / 6 = {_cz_scientific(w)} m³.",
            f"Podíl zatížení η = {_cz(fraction, 6)} (odvozeno v modelu dvojice).",
            f"gk = η × gk,total = {_cz(fraction, 6)} × {_cz(g, 3)} = {_cz(gi, 3)} kN/m.",
            f"sline,k = η × sline,k,total = {_cz(fraction, 6)} × {_cz(snow, 3)} = {_cz(si, 3)} kN/m.",
            f"qinst = gk + sline,k = {_cz(gi, 3)} + {_cz(si, 3)} = {_cz(gi + si, 3)} kN/m.",
            f"qd = γG gk + γQ sline,k = {_cz(PERMANENT_LOAD_FACTOR, 2)} × {_cz(gi, 3)} + "
            f"{_cz(SNOW_LOAD_FACTOR, 2)} × {_cz(si, 3)} = {_cz(component_qd, 3)} kN/m.",
            *((
                f"qfin = gk × (1 + kdef) + sline,k × (1 + ψ2 × kdef) = "
                f"{_cz(gi, 3)} × (1 + {_cz(TIMBER_CREEP_FACTOR, 2)}) + "
                f"{_cz(si, 3)} × (1 + {_cz(SNOW_CREEP_COMBINATION_FACTOR, 2)} × "
                f"{_cz(TIMBER_CREEP_FACTOR, 2)}) = "
                f"{_cz(gi * (1 + TIMBER_CREEP_FACTOR) + si * (1 + SNOW_CREEP_COMBINATION_FACTOR * TIMBER_CREEP_FACTOR), 3)} kN/m.",
            ) if session.include_creep else ()),
            "Průhyb obou nosníků je společný; ohybové a smykové napětí se posuzuje v každém zvlášť.",
            *(('Výpočet je neúplný; chybí hmotnosti vrstev: ' + ', '.join(component.missing_roof_layers),)
              if component.missing_roof_layers else ()),
        )
        _add_purlin_evaluation(
            session.report, chapter_title=normalized_title + " – " + label,
            material=grade, width_mm=width_mm, height_mm=height_mm,
            deflection_ratio=max_deflection, elastic_modulus_gpa=modulus,
            bearing_length_mm=bearing_mm, roof_angle_degrees=roof_angle,
            rafter_width_mm=rafter_width * 1000, rafter_height_mm=rafter_height * 1000,
            rafter_spacing_m=rafter_spacing, snow_load_kn_m2=snow_load,
            roof_layer_mass_kg_m2=basis.roof_layer_line_mass_kg_m / basis.tributary_slope_width_m,
            timber_density_kg_m3=timber_density, include_creep=session.include_creep,
            check=component, geometry_and_load_lines=geometry,
        )
        print(f"  {label} {width_mm:g}x{height_mm:g} mm:")
        print(f"    Deflection L/{max_deflection:g}: immediate "
              f"{component.immediate_response.span_max_abs_deflections_m[0] * 1000:.2f} mm "
              f"({_status(component.immediate_deflection_utilizations[0])}); final "
              f"{component.final_response.span_max_abs_deflections_m[0] * 1000:.2f} mm "
              f"({_status(component.final_deflection_utilizations[0])})")
        moment = component.design_response.span_positive_moments_nm[0]
        shear = component.design_response.span_max_abs_shears_n[0]
        reaction = (component.bearing_design_reaction_n if component.bearing_design_reaction_n is not None
                    else max(abs(r) for r in component.design_response.support_reactions_n))
        print(f"    Bending M={moment / 1000:.3f} kNm, stress={moment / w / 1e6:.3f} MPa "
              f"({_status(component.positive_bending_utilization)}); "
              f"shear={shear / 1000:.3f} kN ({_status(component.shear_utilization)})")
        print(f"    Bearing reaction={reaction / 1000:.3f} kN "
              f"({_status(component.bearing_utilization)}); "
              f"governing={component.governing_strength_check} "
              f"{component.governing_strength_utilization:.1%}")
    session.add_result(normalized_title, "double_purlin", check)
    return check


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
#  SUPPORT_SPAN_M = 3.576
#  ROOF_ANGLE_DEGREES = 35.84
#  DORMER_SUPPORT_SPAN_M = 3.014
#  DORMER_ROOF_ANGLE_DEGREES = 15.91
#  RAFTER_LENGTH_ABOVE_PURLIN_M = 1.204
#  PURLIN_SPANS_M = (3.710, 4.720, 2.720)
        check_rafter(
            title="Hlavní krokve, C16",
            material="c16",
            width=0.08,
            height=0.20,
            span=3.5,
            spacing=0.80,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_rafter(
            title="Hlavní krokve, C18",
            material="c18",
            width=0.08,
            height=0.20,
            span=3.5,
            spacing=0.91,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_rafter(
            title="Hlavní krokve, C22",
            material="c22",
            width=0.08,
            height=0.20,
            span=3.5,
            spacing=1.02	,
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
            span=3.5,
            spacing=1.0,
            roof_angle=ROOF_ANGLE_DEGREES,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.05,
        )
        check_purlin(
            title="Vaznice Mid, gl24c",
            material="gl28h",
            width=0.20,
            height=0.32,
            span=4.75,
            rafter_length_above=1.4,
            lower_rafter_span=3.5,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.1,
        )
        check_purlin(
            title="Vaznice AC, c22",
            material="gl24c",
            width=0.20,
            height=0.24,
            span=3.5,
            rafter_length_above=1.4,
            lower_rafter_span=3.5,
            roof_angle=ROOF_ANGLE_DEGREES,
            rafter_width=0.08,
            rafter_height=0.20,
            rafter_spacing=0.75,
            max_deflection=MAX_DEFLECTION_RATIO,
            snow_load=SNOW_LOAD_KN_M2,
            bearing_length=0.1,
        )


if __name__ == "__main__":
    main()
