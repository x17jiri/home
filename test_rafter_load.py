import unittest
from contextlib import redirect_stdout
from io import StringIO
from math import cos, radians, sin
from pathlib import Path
from shutil import which
import subprocess
from tempfile import TemporaryDirectory

from matplotlib import rcParams
from matplotlib.colors import to_hex
from matplotlib.mathtext import MathTextParser

from rafter_load import (
    CalculationReport,
    REPORT_LIMIT_TINT,
    REPORT_RESULT_FAIL_TINT,
    REPORT_RESULT_PASS_TINT,
    ReportHighlight,
    ReportLine,
    GRAVITY_M_S2,
    ROOF_LAYERS_KG_M2,
    SNOW_LOAD_KN_M2,
    _report_math_text,
    _comparison_cz,
    _add_purlin_evaluation,
    _resolve_timber_grade,
    _status,
    _status_cz,
    calculate_continuous_beam_response,
    calculate_rafter_load,
    calculate_purlin_check,
    check_continuous_purlin,
    calculate_roof_check,
    add_rafter_report,
    calculation_report,
    check_purlin,
    check_rafter,
)


class RafterLoadTests(unittest.TestCase):
    def test_c18_material_properties_and_case_insensitive_lookup(self) -> None:
        grade = _resolve_timber_grade(" c18 ")
        self.assertEqual(grade, _resolve_timber_grade("C18"))
        self.assertEqual(grade.name, "C18")
        self.assertEqual(grade.elastic_modulus_gpa, 9.0)
        self.assertEqual(grade.bending_strength_mpa, 18.0)
        self.assertEqual(grade.shear_strength_mpa, 3.4)
        self.assertEqual(grade.compression_parallel_mpa, 18.0)
        self.assertEqual(grade.compression_perpendicular_mpa, 2.2)
        with self.assertRaisesRegex(TypeError, "'c18'"):
            _resolve_timber_grade(None)
        with self.assertRaisesRegex(ValueError, "c18, c22, c24, gl28h"):
            _resolve_timber_grade("c16")

    def test_gl28h_material_properties_and_case_insensitive_lookup(self) -> None:
        grade = _resolve_timber_grade(" gl28h ")
        self.assertEqual(grade, _resolve_timber_grade("GL28H"))
        self.assertEqual(grade, _resolve_timber_grade("GL28h"))
        self.assertEqual(grade.name, "GL28h")
        self.assertEqual(grade.elastic_modulus_gpa, 12.6)
        self.assertEqual(grade.bending_strength_mpa, 28.0)
        self.assertEqual(grade.shear_strength_mpa, 3.5)
        self.assertEqual(grade.compression_parallel_mpa, 28.0)
        self.assertEqual(grade.compression_perpendicular_mpa, 2.5)
        self.assertEqual(grade.material_partial_factor, 1.25)
        for material in ("c18", "c22", "c24"):
            self.assertEqual(_resolve_timber_grade(material).material_partial_factor, 1.3)
        with self.assertRaisesRegex(TypeError, "'gl28h'"):
            _resolve_timber_grade(None)
        with self.assertRaisesRegex(ValueError, "gl28h"):
            _resolve_timber_grade("gl28c")

    @unittest.skipUnless(which("pdftotext"), "PDF text extraction needs pdftotext")
    def test_gl28h_works_in_all_checks_and_report(self) -> None:
        output = StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "gl28h.pdf"
            with redirect_stdout(output):
                with calculation_report(path, include_creep=True):
                    rafter = check_rafter(
                        title="Krokve GL28h", material="GL28H", width=0.08,
                        height=0.20, span=3.85, spacing=0.75, roof_angle=35.83,
                        max_deflection=300, snow_load=1.5,
                        roof_layers={"Layers": 130}, bearing_length=0.05,
                    )
                    arguments = dict(
                        material="gl28h", width=0.24, height=0.28,
                        rafter_length_above=1.05, lower_rafter_span=3.85,
                        roof_angle=35.83, rafter_width=0.08, rafter_height=0.20,
                        rafter_spacing=0.75, max_deflection=300, snow_load=1.5,
                        roof_layers={"Layers": 130}, bearing_length=0.12,
                    )
                    purlin = check_purlin(title="Vaznice GL28h", span=4.72, **arguments)
                    continuous = check_continuous_purlin(
                        title="Souvislá vaznice GL28h", spans=(3.47, 4.72, 2.72),
                        **arguments,
                    )
            text = subprocess.run(
                ["pdftotext", str(path), "-"], check=True, capture_output=True,
                text=True,
            ).stdout
            self.assertIn("EN 14080", text)
            self.assertIn("1,25", text)
            self.assertIn("12,60 GPa", text)
            self.assertIn("17,9200 MPa", text)
            self.assertIn("2,2400 MPa", text)
            self.assertIn("1,6000 MPa", text)
            for title in ("Krokve GL28h", "Vaznice GL28h", "Souvislá vaznice GL28h"):
                self.assertIn(title, text)
                self.assertIn(title + ":", output.getvalue())
        multiplier = 0.8 / 1.25
        self.assertAlmostEqual(
            rafter.bending_resistance_nm, 28e6 * multiplier * 0.08 * 0.20**2 / 6
        )
        self.assertAlmostEqual(
            rafter.shear_resistance_n, 3.5e6 * multiplier * 0.67 * 0.08 * 0.20 / 1.5
        )
        reference = calculate_roof_check(
            width_mm=80, height_mm=200, support_span_m=3.85,
            deflection_ratio=300, elastic_modulus_gpa=12.6,
            roof_angle_degrees=35.83, rafter_spacing_m=0.75,
            snow_load_kn_m2=1.5, roof_layers_kg_m2={"Layers": 130},
            bending_strength_mpa=28, shear_strength_mpa=3.5,
            compression_parallel_mpa=28, compression_perpendicular_mpa=2.5,
            material_partial_factor=1.25, bearing_length_mm=50,
        )
        self.assertEqual(rafter, reference)
        for check in (purlin, continuous):
            self.assertAlmostEqual(
                check.bending_resistance_nm, 28e6 * multiplier * 0.24 * 0.28**2 / 6
            )
            self.assertAlmostEqual(
                check.shear_resistance_n, 3.5e6 * multiplier * 0.67 * 0.24 * 0.28 / 1.5
            )
            self.assertAlmostEqual(
                check.bearing_resistance_n, 2.5e6 * multiplier * 0.24 * 0.12
            )

    @unittest.skipUnless(which("pdftotext"), "PDF text extraction needs pdftotext")
    def test_c18_works_in_all_checks_and_report(self) -> None:
        output = StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "c18.pdf"
            with redirect_stdout(output):
                with calculation_report(path):
                    rafter = check_rafter(
                        title="Krokve C18", material="C18", width=0.08,
                        height=0.20, span=3.85, spacing=0.75, roof_angle=35.83,
                        max_deflection=300, snow_load=1.5,
                        roof_layers={"Layers": 130}, bearing_length=0.05,
                    )
                    arguments = dict(
                        material="c18", width=0.24, height=0.28,
                        rafter_length_above=1.05, lower_rafter_span=3.85,
                        roof_angle=35.83, rafter_width=0.08, rafter_height=0.20,
                        rafter_spacing=0.75, max_deflection=300, snow_load=1.5,
                        roof_layers={"Layers": 130}, bearing_length=0.12,
                    )
                    purlin = check_purlin(title="Vaznice C18", span=4.72, **arguments)
                    continuous = check_continuous_purlin(
                        title="Souvislá vaznice C18", spans=(3.47, 4.72, 2.72),
                        **arguments,
                    )
            text = subprocess.run(
                ["pdftotext", str(path), "-"], check=True, capture_output=True,
                text=True,
            ).stdout
            self.assertIn("C18/C22/C24", text)
            for title in ("Krokve C18", "Vaznice C18", "Souvislá vaznice C18"):
                self.assertIn(title, text)
                self.assertIn(title + ":", output.getvalue())
        design_strength_pa = 18e6 * 0.8 / 1.3
        self.assertAlmostEqual(
            rafter.bending_resistance_nm, design_strength_pa * 0.08 * 0.20**2 / 6
        )
        for check in (purlin, continuous):
            self.assertAlmostEqual(
                check.bending_resistance_nm, design_strength_pa * 0.24 * 0.28**2 / 6
            )

    def test_pdf_embeds_unicode_mapped_truetype_fonts(self) -> None:
        self.assertEqual(rcParams["pdf.fonttype"], 42)

    def assert_stress_section(self, lines, *, symbol, strength_symbol,
                              stress_mpa, strength_mpa, utilization) -> None:
        demand = f"{stress_mpa:.4f} MPa".replace(".", ",")
        limit = f"{strength_mpa:.4f} MPa".replace(".", ",")
        text = "\n".join(
            line.text if isinstance(line, ReportLine) else line for line in lines
        )
        self.assertIn(symbol + " = ", text)
        self.assertIn("Mezní hodnota " + strength_symbol + " = ", text)
        self.assertNotIn("MRd", text)
        self.assertNotIn("VRd", text)
        self.assertAlmostEqual(stress_mpa / strength_mpa, utilization)
        relation = "<" if utilization < 1 else ">" if utilization > 1 else "="
        self.assertEqual(
            lines[-1].text,
            f"{demand} {relation} {limit}, " + _status_cz(utilization),
        )
        for value, color in (
            (demand, REPORT_RESULT_PASS_TINT if utilization < 1 else REPORT_RESULT_FAIL_TINT),
            (limit, REPORT_LIMIT_TINT),
        ):
            matching_lines = [
                line for line in lines
                if isinstance(line, ReportLine) and value in line.text
            ]
            self.assertEqual(len(matching_lines), 2)
            for line in matching_lines:
                self.assertIn(ReportHighlight(value, color), line.highlights)

    def test_stress_variable_subscripts(self) -> None:
        self.assertEqual(
            _report_math_text("σm,d < fm,d; τd < fv,d"),
            r"$σ_{\mathrm{m,d}}$ < $f_{\mathrm{m,d}}$; "
            r"$τ_{\mathrm{d}}$ < $f_{\mathrm{v,d}}$",
        )

    def test_report_subscripts_only_known_variable_names(self) -> None:
        self.assertEqual(
            _report_math_text("wfin = wG,inst + wS,inst; qS,k; fc,β,d; MEd,-,max"),
            r"$w_{\mathrm{fin}}$ = $w_{\mathrm{G,inst}}$ + "
            r"$w_{\mathrm{S,inst}}$; $q_{\mathrm{S,k}}$; "
            r"$f_{\mathrm{c,β,d}}$; $M_{\mathrm{Ed,-,max}}$",
        )
        prose = "Zatížení střechy, vrstvy, krokve, kg/m²; qk_extra; sklon"
        self.assertEqual(_report_math_text(prose), prose)
        existing_math = r"$w_{\mathrm{fin}}$ = 8,91 mm"
        self.assertEqual(_report_math_text(existing_math), existing_math)

    @unittest.skipUnless(which("pdftotext"), "PDF text extraction needs pdftotext")
    def test_subscripts_preserve_pdf_text_and_highlight_positions(self) -> None:
        class RecordingPdf(CalculationReport):
            def _save_page(self, figure) -> None:
                super()._save_page(figure)
                self.saved_figure = figure

        with TemporaryDirectory() as temporary_directory:
            pdf_path = Path(temporary_directory) / "subscripts.pdf"
            with RecordingPdf(pdf_path) as report:
                report.add_sections(
                    "Zatížení střechy",
                    (("Průhyb", (
                        ReportLine(
                            "Celkový průhyb wfin = 8,91 mm.",
                            (ReportHighlight("8,91 mm", REPORT_RESULT_PASS_TINT),),
                        ),
                        ReportLine(
                            "Mezní hodnota wlim = 12,83 mm.",
                            (ReportHighlight("12,83 mm", REPORT_LIMIT_TINT),),
                        ),
                        ReportLine(
                            "8,91 mm < 12,83 mm, VYHOVUJE",
                            (ReportHighlight("8,91 mm", REPORT_RESULT_PASS_TINT),
                             ReportHighlight("12,83 mm", REPORT_LIMIT_TINT)),
                        ),
                        "qS,k = sk × a × cos² α; fc,β,d; MEd,-,max; σm,d; τd",
                    )),),
                )
                figure = report.saved_figure
                artist = next(
                    artist for artist in figure.texts
                    if artist.get_text().startswith("Celkový průhyb")
                )
                glyphs = MathTextParser("path").parse(
                    artist.get_text(), figure.dpi, artist.get_fontproperties()
                ).glyphs
                # Verify actual glyph placement, not just the presence of markup.
                w = next(glyph for glyph in glyphs if glyph[2] == ord("w"))
                f = next(glyph for glyph in glyphs if glyph[2] == ord("f"))
                self.assertLess(f[1], w[1])  # font size
                self.assertLess(f[4], w[4])  # baseline
                result_first_glyph = next(
                    glyph for glyph in glyphs if glyph[2] == ord("8")
                )
                renderer = figure.canvas.get_renderer()
                bounds = artist.get_window_extent(renderer)
                rectangle = figure.artists[0].get_window_extent(renderer)
                # The tint must sit under the number even after a subscript.
                number_x = bounds.x0 + result_first_glyph[3]
                self.assertLessEqual(rectangle.x0, number_x)
                self.assertLess(number_x - rectangle.x0, 4)
                self.assertCountEqual(
                    [to_hex(item.get_facecolor()) for item in figure.artists],
                    [REPORT_RESULT_PASS_TINT, REPORT_LIMIT_TINT] * 2,
                )

            copied_text = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertIn("Zatížení střechy", copied_text)
            self.assertIn("Celkový průhyb wfin", copied_text)
            self.assertIn("Mezní hodnota wlim", copied_text)
            self.assertIn("σ", copied_text)
            self.assertIn("τ", copied_text)
            self.assertEqual(copied_text.count("8,91 mm"), 2)
            self.assertEqual(copied_text.count("12,83 mm"), 2)
            self.assertNotIn(r"\mathrm", copied_text)
            self.assertNotIn("$", copied_text)

    def test_rafter_report_substitutes_exact_values_into_formulas(self) -> None:
        check = calculate_roof_check(
            width_mm=80,
            height_mm=200,
            support_span_m=3.85,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=35.83,
            rafter_spacing_m=0.85,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Layers": 135},
        )

        class RecordingReport:
            sections = ()

            def add_sections(self, title, sections, **kwargs) -> None:
                self.sections = tuple(sections)

        report = RecordingReport()
        add_rafter_report(
            report,
            width_mm=80,
            height_mm=200,
            rafter_spacing_m=0.85,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            timber_density_kg_m3=450,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Layers": 135},
            rafter_checks=(("Krokev", 3.85, 35.83, check),),
        )
        text = "\n".join(
            line.text if isinstance(line, ReportLine) else line
            for _, lines in report.sections
            for line in lines
        )

        self.assertIn(
            "Zatížení od sněhu qS,k = sk × a × cos² α = "
            "1,50 kN/m² × 0,850 m × cos² 35,83° = 0,838 kN/m.",
            text,
        )
        deflection_lines = dict(report.sections)["Posouzení - okamžitý průhyb"]
        for value, color in (
            ("8,91 mm", REPORT_RESULT_PASS_TINT),
            ("12,83 mm", REPORT_LIMIT_TINT),
        ):
            matching_lines = [
                line
                for line in deflection_lines
                if isinstance(line, ReportLine) and value in line.text
            ]
            self.assertEqual(len(matching_lines), 2)
            for line in matching_lines:
                self.assertIn(
                    (value, color),
                    [
                        (highlight.text, highlight.color)
                        for highlight in line.highlights
                    ],
                )

    def test_highlights_survive_wrapping_and_bold_verdicts(self) -> None:
        class RecordingPdf(CalculationReport):
            def _save_page(self, figure) -> None:
                super()._save_page(figure)
                self.saved_text = "\n".join(
                    artist.get_text() for artist in figure.texts
                )
                self.saved_colors = [
                    to_hex(artist.get_facecolor())
                    for artist in figure.artists
                ]

        result = ReportHighlight("8,91 mm", REPORT_RESULT_PASS_TINT)
        limit = ReportHighlight("12,83 mm", REPORT_LIMIT_TINT)
        with TemporaryDirectory() as temporary_directory:
            with RecordingPdf(
                Path(temporary_directory) / "highlights.pdf"
            ) as report:
                report.add_sections(
                    "Zatížení střechy",
                    (("Průhyb", (
                        ReportLine("x" * 95 + " = 8,91 mm.", (result,)),
                        ReportLine("Mezní hodnota = 12,83 mm.", (limit,)),
                        ReportLine(
                            "8,91 mm < 12,83 mm, VYHOVUJE",
                            (result, limit),
                        ),
                    )),),
                )
                self.assertEqual(report.saved_text.count("8,91 mm"), 2)
                self.assertEqual(report.saved_text.count("12,83 mm"), 2)
                self.assertIn("Zatížení střechy", report.saved_text)
                self.assertCountEqual(
                    report.saved_colors,
                    [REPORT_RESULT_PASS_TINT, REPORT_LIMIT_TINT] * 2,
                )

    def test_utilization_must_be_strictly_below_one(self) -> None:
        self.assertEqual(_status(0.999), "PASS")
        self.assertEqual(_status(1.0), "FAIL")
        self.assertEqual(_status(1.001), "FAIL")
        self.assertEqual(_status_cz(0.999), "VYHOVUJE")
        self.assertEqual(_status_cz(1.0), "NEVYHOVUJE")
        self.assertEqual(_status_cz(1.001), "NEVYHOVUJE")

    def test_report_comparisons_show_the_actual_relation(self) -> None:
        self.assertEqual(
            _comparison_cz("8,91 mm", "12,83 mm", 8.91 / 12.83),
            "8,91 mm < 12,83 mm, VYHOVUJE",
        )
        self.assertEqual(
            _comparison_cz("18,32 mm", "16,00 mm", 18.32 / 16),
            "18,32 mm > 16,00 mm, NEVYHOVUJE",
        )
        self.assertEqual(
            _comparison_cz("16,00 mm", "16,00 mm", 1.0),
            "16,00 mm = 16,00 mm, NEVYHOVUJE",
        )

    def test_rafter_bearing_report_compares_stresses_and_failures(self) -> None:
        class RecordingReport:
            def add_sections(self, title, sections, **kwargs) -> None:
                self.sections = dict(sections)

        for mass in (130, 3000):
            with self.subTest(layer_mass=mass):
                check = calculate_roof_check(
                    width_mm=80, height_mm=200, support_span_m=3.85,
                    deflection_ratio=300, elastic_modulus_gpa=11,
                    roof_angle_degrees=35.83, rafter_spacing_m=0.85,
                    snow_load_kn_m2=1.5, roof_layers_kg_m2={"Layers": mass},
                    bearing_length_mm=50,
                )
                report = RecordingReport()
                add_rafter_report(
                    report, width_mm=80, height_mm=200, rafter_spacing_m=0.85,
                    deflection_ratio=300, elastic_modulus_gpa=11,
                    timber_density_kg_m3=450, snow_load_kn_m2=1.5,
                    roof_layers_kg_m2={"Layers": mass},
                    rafter_checks=(("Krokev", 3.85, 35.83, check),),
                    include_creep=True, bearing_length_mm=50,
                )
                lines = report.sections["Posouzení - tlak šikmo k vláknům v uložení"]
                text = "\n".join(
                    line.text if isinstance(line, ReportLine) else line
                    for line in lines
                )
                # N / mm² = MPa, with the configured 80 × 50 mm contact area.
                stress = check.design_support_reaction_n / (80 * 50)
                strength = check.design_bearing_strength_pa / 1e6
                demand = f"{stress:.4f} MPa".replace(".", ",")
                limit = f"{strength:.4f} MPa".replace(".", ",")
                self.assertIn("σc,β,d = Fc,β,Ed / A = ", text)
                self.assertIn("kN × 1000 / 4000 mm² = " + demand, text)
                self.assertIn("Mezní hodnota fc,β,d = " + limit, text)
                self.assertNotIn("Rc,β,d", text)
                self.assertAlmostEqual(stress / strength, check.bearing_utilization)
                verdict = lines[-2]
                self.assertIn(" < " if mass == 130 else " > ", verdict.text)
                self.assertIn(
                    ReportHighlight(demand, REPORT_RESULT_PASS_TINT if mass == 130
                                    else REPORT_RESULT_FAIL_TINT),
                    verdict.highlights,
                )
                self.assertIn(ReportHighlight(limit, REPORT_LIMIT_TINT), verdict.highlights)
                # Work independently in N·mm and mm³, rather than the renderer's SI units.
                section_modulus_mm3 = 80 * 200**2 / 6
                self.assert_stress_section(
                    report.sections["Posouzení - namáhání ohybem"],
                    symbol="σm,d", strength_symbol="fm,d",
                    stress_mpa=abs(check.design_bending_moment_nm) * 1000 / section_modulus_mm3,
                    strength_mpa=check.bending_resistance_nm * 1000 / section_modulus_mm3,
                    utilization=check.bending_utilization,
                )
                effective_area_mm2 = 0.67 * 80 * 200
                self.assert_stress_section(
                    report.sections["Posouzení - namáhání smykem"],
                    symbol="τd", strength_symbol="fv,d",
                    stress_mpa=1.5 * abs(check.design_shear_force_n) / effective_area_mm2,
                    strength_mpa=1.5 * check.shear_resistance_n / effective_area_mm2,
                    utilization=check.shear_utilization,
                )
                shear_text = "\n".join(
                    line.text if isinstance(line, ReportLine) else line
                    for line in report.sections["Posouzení - namáhání smykem"]
                )
                self.assertIn("(kcr × b × h)", shear_text)
                self.assertIn("kN × 1000 / (0,67 × 80 mm × 200 mm)", shear_text)
                if mass == 3000:
                    verdicts = [
                        line.text
                        for section in report.sections.values()
                        for line in section
                        if isinstance(line, ReportLine) and "NEVYHOVUJE" in line.text
                    ]
                    self.assertEqual(len(verdicts), 5)
                    self.assertTrue(all(" > " in line for line in verdicts))

    def test_purlin_report_stresses_headings_and_failure_relations(self) -> None:
        class RecordingReport:
            def add_sections(self, title, sections, **kwargs) -> None:
                self.sections = dict(sections)

        for spans in ((4.8,), (3.74, 4.8, 2.75)):
            with self.subTest(spans=spans):
                check = calculate_purlin_check(
                    width_mm=160, height_mm=200, support_spans_m=spans,
                    upper_rafter_length_m=1.05, lower_rafter_span_m=3.85,
                    roof_angle_degrees=35.83, rafter_width_mm=80,
                    rafter_height_mm=200, rafter_spacing_m=0.75,
                    deflection_ratio=300, elastic_modulus_gpa=10,
                    snow_load_kn_m2=1.5, roof_layers_kg_m2={"Layers": 3000},
                    bearing_length_mm=120,
                )
                report = RecordingReport()
                _add_purlin_evaluation(
                    report, chapter_title="Vaznice", material=_resolve_timber_grade("c24"),
                    width_mm=160, height_mm=200, deflection_ratio=300,
                    elastic_modulus_gpa=10, bearing_length_mm=120,
                    roof_angle_degrees=35.83, rafter_width_mm=80, rafter_height_mm=200,
                    rafter_spacing_m=0.75, snow_load_kn_m2=1.5,
                    roof_layer_mass_kg_m2=3000, timber_density_kg_m3=450,
                    include_creep=True, check=check,
                )
                self.assertIn("Posouzení - namáhání ohybem", report.sections)
                if len(spans) == 3:
                    self.assertIn(
                        "Posouzení - namáhání ohybem - negativní moment", report.sections,
                    )
                for index in range(1, len(spans) + 1):
                    suffix = f", pole {index}" if len(spans) == 3 else ""
                    self.assertIn("Posouzení - okamžitý průhyb" + suffix, report.sections)
                    self.assertIn(
                        "Posouzení - konečný průhyb včetně dotvarování" + suffix,
                        report.sections,
                    )
                bearing = report.sections["Posouzení - tlak kolmo k vláknům v uložení"]
                text = "\n".join(line.text for line in bearing)
                force = max(abs(value) for value in check.design_response.support_reactions_n)
                stress = force / (160 * 120)
                limit = check.bearing_resistance_n / (160 * 120)
                self.assertIn("σc,90,d = Fc,90,Ed", text)
                self.assertIn("kN × 1000 / 19200 mm²", text)
                self.assertIn(f"{stress:.4f} MPa".replace(".", ","), text)
                self.assertNotIn("Rc,90,d", text)
                self.assertAlmostEqual(stress / limit, check.bearing_utilization)
                section_modulus_mm3 = 160 * 200**2 / 6
                positive_moment = max(check.design_response.span_positive_moments_nm)
                self.assert_stress_section(
                    report.sections["Posouzení - namáhání ohybem"],
                    symbol="σm,d", strength_symbol="fm,d",
                    stress_mpa=positive_moment * 1000 / section_modulus_mm3,
                    strength_mpa=check.bending_resistance_nm * 1000 / section_modulus_mm3,
                    utilization=check.positive_bending_utilization,
                )
                if len(spans) == 3:
                    negative_moment = abs(min(check.design_response.support_moments_nm))
                    negative_lines = report.sections[
                        "Posouzení - namáhání ohybem - negativní moment"
                    ]
                    self.assert_stress_section(
                        negative_lines, symbol="σm,d", strength_symbol="fm,d",
                        stress_mpa=negative_moment * 1000 / section_modulus_mm3,
                        strength_mpa=check.bending_resistance_nm * 1000 / section_modulus_mm3,
                        utilization=check.negative_bending_utilization,
                    )
                    self.assertIn("σm,d = |MEd,-,max| / W", "\n".join(
                        line.text for line in negative_lines
                    ))
                effective_area_mm2 = 0.67 * 160 * 200
                self.assert_stress_section(
                    report.sections["Posouzení - namáhání smykem"],
                    symbol="τd", strength_symbol="fv,d",
                    stress_mpa=1.5 * max(check.design_response.span_max_abs_shears_n) / effective_area_mm2,
                    strength_mpa=1.5 * check.shear_resistance_n / effective_area_mm2,
                    utilization=check.shear_utilization,
                )
                verdicts = [
                    line.text for section in report.sections.values() for line in section
                    if isinstance(line, ReportLine) and "NEVYHOVUJE" in line.text
                ]
                self.assertEqual(len(verdicts), 2 * len(spans) + (4 if len(spans) == 3 else 3))
                self.assertTrue(all(" > " in line for line in verdicts))

    def test_calculates_deflection_limited_uniform_load(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=200,
            support_span_m=3.7,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            timber_density_kg_m3=450,
        )

        self.assertAlmostEqual(result.second_moment_m4, 0.0000533333333333)
        self.assertAlmostEqual(result.maximum_deflection_m, 3.7 / 300)
        self.assertAlmostEqual(result.self_mass_kg_per_m, 7.2)
        expected_total_n_per_m = (
            (3.7 / 300)
            * 384
            * 11e9
            * (0.08 * 0.2**3 / 12)
            / (5 * 3.7**4)
        )
        self.assertAlmostEqual(
            result.deflection_total_n_per_m,
            expected_total_n_per_m,
        )
        self.assertAlmostEqual(
            result.deflection_payload_kg_per_m,
            expected_total_n_per_m / GRAVITY_M_S2 - 7.2,
        )
        self.assertEqual(result.governing_limit, "deflection")

    def test_uses_optional_allowable_bending_stress(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=200,
            support_span_m=3.7,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            allowable_bending_stress_mpa=5,
        )

        self.assertIsNotNone(result.bending_payload_kg_per_m)
        self.assertEqual(result.governing_limit, "bending")
        self.assertEqual(
            result.governing_payload_kg_per_m,
            result.bending_payload_kg_per_m,
        )

    def test_converts_plan_snow_load_using_angle_and_spacing(self) -> None:
        result = calculate_rafter_load(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
        )

        roof_cosine = cos(radians(36.65))
        self.assertAlmostEqual(result.roof_cosine, roof_cosine)
        self.assertAlmostEqual(
            result.snow_vertical_n_per_m,
            1500 * 0.8 * roof_cosine,
        )
        self.assertAlmostEqual(
            result.snow_transverse_n_per_m,
            1500 * 0.8 * roof_cosine**2,
        )
        self.assertAlmostEqual(
            result.snow_deflection_m,
            result.maximum_deflection_m
            * (
                result.self_transverse_n_per_m
                + result.snow_transverse_n_per_m
            )
            / result.deflection_total_n_per_m,
        )

    def test_rejects_non_positive_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "width_mm"):
            calculate_rafter_load(
                width_mm=0,
                height_mm=200,
                support_span_m=3.7,
                deflection_ratio=300,
                elastic_modulus_gpa=11,
            )
        with self.assertRaisesRegex(ValueError, "roof_angle_degrees"):
            calculate_rafter_load(
                width_mm=80,
                height_mm=200,
                support_span_m=3.7,
                deflection_ratio=300,
                elastic_modulus_gpa=11,
                roof_angle_degrees=90,
            )

    def test_checks_roof_layers_snow_creep_and_design_strength(self) -> None:
        check = calculate_roof_check(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Tiles": 50, "Insulation": 20},
        )

        cosine = cos(radians(36.65))
        layer_transverse = 70 * GRAVITY_M_S2 * 0.8 * cosine
        expected_permanent = (
            check.rafter.self_transverse_n_per_m + layer_transverse
        )
        bearing_angle = radians(90 - 36.65)
        compression_parallel_pa = (
            21.0 * 1e6 * 0.8 / 1.3
        )
        compression_perpendicular_pa = (
            2.5 * 1e6 * 0.8 / 1.3
        )
        expected_bearing_strength_pa = compression_parallel_pa / (
            compression_parallel_pa / compression_perpendicular_pa
            * sin(bearing_angle) ** 2
            + cos(bearing_angle) ** 2
        )
        self.assertEqual(check.roof_layer_mass_kg_m2, 70)
        self.assertEqual(check.missing_roof_layers, ())
        self.assertAlmostEqual(
            check.permanent_transverse_n_per_m,
            expected_permanent,
        )
        self.assertAlmostEqual(
            check.design_transverse_n_per_m,
            1.35 * expected_permanent
            + 1.5 * check.rafter.snow_transverse_n_per_m,
        )
        self.assertAlmostEqual(
            check.final_deflection_m,
            check.permanent_immediate_deflection_m * 1.8
            + check.snow_immediate_deflection_m,
        )
        self.assertGreater(check.bending_resistance_nm, 0)
        self.assertGreater(check.shear_resistance_n, 0)
        self.assertAlmostEqual(check.bearing_angle_degrees, 90 - 36.65)
        self.assertAlmostEqual(
            check.design_support_reaction_n,
            check.design_shear_force_n / cosine,
        )
        self.assertAlmostEqual(
            check.design_bearing_strength_pa,
            expected_bearing_strength_pa,
        )
        self.assertAlmostEqual(
            check.bearing_area_m2,
            0.08 * 50 / 1000,
        )
        self.assertAlmostEqual(
            check.bearing_resistance_n,
            expected_bearing_strength_pa * check.bearing_area_m2,
        )
        self.assertAlmostEqual(
            check.bearing_utilization,
            check.design_support_reaction_n / check.bearing_resistance_n,
        )
        self.assertGreater(check.bearing_resistance_n, 0)

    def test_rafter_bearing_length_is_configurable(self) -> None:
        shared_arguments = {
            "width_mm": 80,
            "height_mm": 180,
            "support_span_m": 3.75,
            "deflection_ratio": 300,
            "elastic_modulus_gpa": 11,
            "roof_angle_degrees": 36.65,
            "rafter_spacing_m": 0.8,
            "snow_load_kn_m2": 1.5,
            "roof_layers_kg_m2": {"Layers": 70},
        }
        default_check = calculate_roof_check(**shared_arguments)
        double_bearing_check = calculate_roof_check(
            **shared_arguments,
            bearing_length_mm=2 * 50,
        )

        self.assertAlmostEqual(
            double_bearing_check.bearing_resistance_n,
            2 * default_check.bearing_resistance_n,
        )
        self.assertAlmostEqual(
            double_bearing_check.bearing_utilization,
            default_check.bearing_utilization / 2,
        )

    def test_marks_unentered_roof_layers_as_missing(self) -> None:
        check = calculate_roof_check(
            width_mm=80,
            height_mm=180,
            support_span_m=3.75,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            roof_angle_degrees=36.65,
            rafter_spacing_m=0.8,
            snow_load_kn_m2=1.5,
            roof_layers_kg_m2={"Tiles": 50, "Unknown": None},
        )

        self.assertEqual(check.roof_layer_mass_kg_m2, 50)
        self.assertEqual(check.missing_roof_layers, ("Unknown",))

    def test_purlin_uses_sloping_dead_and_horizontal_snow_tributaries(
        self,
    ) -> None:
        check = calculate_purlin_check(
            width_mm=160,
            height_mm=280,
            support_spans_m=(3.7, 4.75, 2.75),
            upper_rafter_length_m=1.08,
            lower_rafter_span_m=3.7,
            roof_angle_degrees=35.84,
            rafter_width_mm=100,
            rafter_height_mm=180,
            rafter_spacing_m=0.82,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            snow_load_kn_m2=1.7,
            roof_layers_kg_m2={"Layers": 100, "Unknown": None},
            additional_permanent_load_kn_m=0.2,
            timber_density_kg_m3=450,
            bearing_length_mm=240,
        )

        expected_slope_width = 1.08 + 3.7 / 2
        expected_horizontal_width = expected_slope_width * cos(
            radians(35.84)
        )
        expected_rafter_mass = (
            450 * 0.1 * 0.18 * expected_slope_width / 0.82
        )
        expected_transferred_mass = (
            100 * expected_slope_width
            + expected_rafter_mass
            + 0.2 * 1000 / GRAVITY_M_S2
        )

        self.assertAlmostEqual(
            check.tributary_slope_width_m,
            expected_slope_width,
        )
        self.assertAlmostEqual(
            check.tributary_horizontal_width_m,
            expected_horizontal_width,
        )
        self.assertAlmostEqual(
            check.rafter_line_mass_kg_m,
            expected_rafter_mass,
        )
        self.assertAlmostEqual(
            check.roof_snow_line_load_kn_m,
            1.7 * expected_horizontal_width,
        )
        self.assertAlmostEqual(
            check.permanent_line_load_kn_m,
            (450 * 0.16 * 0.28 + expected_transferred_mass)
            * GRAVITY_M_S2
            / 1000,
        )
        self.assertLess(min(check.design_response.support_moments_nm), 0)
        self.assertEqual(len(check.final_deflection_utilizations), 3)
        self.assertEqual(check.missing_roof_layers, ("Unknown",))


    def test_simple_purlin_is_one_simply_supported_span(self) -> None:
        span = 4.75
        check = calculate_purlin_check(
            width_mm=160,
            height_mm=280,
            support_spans_m=(span,),
            upper_rafter_length_m=1.08,
            lower_rafter_span_m=3.7,
            roof_angle_degrees=35.84,
            rafter_width_mm=100,
            rafter_height_mm=180,
            rafter_spacing_m=0.82,
            deflection_ratio=300,
            elastic_modulus_gpa=11,
            snow_load_kn_m2=1.7,
            roof_layers_kg_m2={"Layers": 100},
            additional_permanent_load_kn_m=0.2,
            timber_density_kg_m3=450,
            bearing_length_mm=120,
        )

        design_line_load_n_m = (
            1.35 * check.permanent_line_load_kn_m
            + 1.5 * check.roof_snow_line_load_kn_m
        ) * 1000
        second_moment_m4 = 0.16 * 0.28**3 / 12
        expected_immediate_deflection = (
            5
            * (
                check.permanent_line_load_kn_m
                + check.roof_snow_line_load_kn_m
            )
            * 1000
            * span**4
            / (384 * 11e9 * second_moment_m4)
        )

        self.assertEqual(check.span_lengths_m, (span,))
        self.assertEqual(check.design_response.support_moments_nm, (0.0, 0.0))
        self.assertAlmostEqual(
            check.immediate_response.span_max_abs_deflections_m[0],
            expected_immediate_deflection,
        )
        self.assertAlmostEqual(
            check.design_response.span_positive_moments_nm[0],
            design_line_load_n_m * span**2 / 8,
        )
        self.assertAlmostEqual(
            max(check.design_response.support_reactions_n),
            design_line_load_n_m * span / 2,
        )

    def test_continuous_beam_matches_two_equal_span_solution(self) -> None:
        span = 4.0
        load = 1000.0
        response = calculate_continuous_beam_response(
            span_lengths_m=(span, span),
            uniform_loads_n_per_m=(load, load),
            elastic_modulus_pa=11e9,
            second_moment_m4=0.0001,
        )

        self.assertAlmostEqual(
            response.support_moments_nm[1],
            -load * span**2 / 8,
        )
        self.assertAlmostEqual(
            response.span_positive_moments_nm[0],
            9 * load * span**2 / 128,
        )
        self.assertAlmostEqual(
            response.support_reactions_n[0],
            3 * load * span / 8,
        )
        self.assertAlmostEqual(
            response.support_reactions_n[1],
            5 * load * span / 4,
        )

    def test_check_calls_print_and_append_the_same_results(self) -> None:
        output = StringIO()
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "roof.pdf"
            with redirect_stdout(output):
                with calculation_report(report_path):
                    c22_rafter = check_rafter(
                        title="Krokve C22",
                        material="c22",
                        width=0.08,
                        height=0.20,
                        span=3.85,
                        spacing=0.75,
                        roof_angle=35.83,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                    )
                    c24_rafter = check_rafter(
                        title="Krokve C24",
                        material="c24",
                        width=0.08,
                        height=0.20,
                        span=3.85,
                        spacing=0.75,
                        roof_angle=35.83,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                    )
                    purlin = check_purlin(
                        title="Vaznice C22",
                        material="c22",
                        width=0.24,
                        height=0.32,
                        span=4.80,
                        rafter_length_above=1.05,
                        lower_rafter_span=3.85,
                        roof_angle=35.83,
                        rafter_width=0.08,
                        rafter_height=0.20,
                        rafter_spacing=0.75,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                        bearing_length=0.12,
                    )
                    continuous_purlin = check_continuous_purlin(
                        title="Souvislá vaznice C22",
                        material="c22",
                        width=0.24,
                        height=0.32,
                        spans=(3.74, 4.80, 2.75),
                        rafter_length_above=1.05,
                        lower_rafter_span=3.85,
                        roof_angle=35.83,
                        rafter_width=0.08,
                        rafter_height=0.20,
                        rafter_spacing=0.75,
                        max_deflection=300,
                        snow_load=1.5,
                        roof_layers={"Layers": 130},
                        bearing_length=0.24,
                    )

            terminal = output.getvalue()
            self.assertIn("Krokve C22:", terminal)
            self.assertIn("Krokve C24:", terminal)
            self.assertIn("Vaznice C22:", terminal)
            self.assertIn("Souvislá vaznice C22:", terminal)
            self.assertIn("Final deflection with k_def=0.8", terminal)
            self.assertNotIn("Independent purlin pieces:", terminal)
            self.assertIn("OVERALL RESULT:", terminal)
            self.assertIn("PDF REPORT:", terminal)
            self.assertTrue(report_path.read_bytes().startswith(b"%PDF-"))
            self.assertGreater(report_path.stat().st_size, 10_000)

        self.assertAlmostEqual(c22_rafter.rafter.self_mass_kg_per_m, 7.2)
        self.assertGreater(
            c24_rafter.bending_resistance_nm,
            c22_rafter.bending_resistance_nm,
        )
        self.assertLess(
            c24_rafter.characteristic_deflection_m,
            c22_rafter.characteristic_deflection_m,
        )
        self.assertAlmostEqual(
            purlin.roof_snow_line_load_kn_m,
            1.5 * purlin.tributary_horizontal_width_m,
        )
        self.assertEqual(purlin.span_lengths_m, (4.8,))
        self.assertEqual(
            continuous_purlin.span_lengths_m,
            (3.74, 4.8, 2.75),
        )

    def test_checks_require_one_consistent_report_context(self) -> None:
        arguments = {
            "title": "Krokve",
            "material": "c22",
            "width": 0.08,
            "height": 0.20,
            "span": 3.85,
            "spacing": 0.75,
            "roof_angle": 35.83,
            "max_deflection": 300,
            "snow_load": 1.5,
            "roof_layers": {"Layers": 130},
        }
        with self.assertRaisesRegex(RuntimeError, "calculation_report"):
            check_rafter(**arguments)

        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "roof.pdf"
            with redirect_stdout(StringIO()):
                with calculation_report(report_path):
                    check_rafter(**arguments)
                    with self.assertRaisesRegex(
                        ValueError,
                        "same snow_load",
                    ):
                        check_rafter(
                            **{
                                **arguments,
                                "title": "Jiná krokev",
                                "snow_load": 1.6,
                            }
                        )
                    with self.assertRaisesRegex(
                        ValueError,
                        "unknown timber material",
                    ):
                        check_rafter(
                            **{
                                **arguments,
                                "title": "Neznámý materiál",
                                "material": "c99",
                            }
                        )

    def test_project_uses_one_snow_load(self) -> None:
        self.assertEqual(SNOW_LOAD_KN_M2, 1.5)
if __name__ == "__main__":


    unittest.main()
