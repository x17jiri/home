"""Markdown PDF checks; renderer mocks keep unit tests independent of WeasyPrint."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from markdown_it import MarkdownIt

from pdf_utils import markdown_to_pdf, _local_resource_fetcher


class MarkdownPdfTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "Skladby & materiály.md"
        self.source.write_text(
            "# Zatížení střechy\n\nParametry:\n- Žluťoučký kůň\n"
            "\nVrstva | Výška\n---|---\nVláknitá izolace | 100 mm\n"
            "\n![Schéma](obrázek.png)\n\n<script>alert(1)</script>\n", encoding="utf-8",
        )
        self.output = self.root / "reports" / "skladby.pdf"

    def libraries(self, writer):
        html = Mock()
        html.return_value.write_pdf.side_effect = writer
        css = Mock(side_effect=lambda **kwargs: kwargs["string"])
        return (MarkdownIt, html, css), html, css

    def test_defaults_tables_lists_unicode_and_relative_images(self):
        temporary_outputs = []

        def write(target, *, stylesheets):
            path = Path(target)
            temporary_outputs.append(path)
            path.write_bytes(b"%PDF-success")

        libraries, html, css = self.libraries(write)
        with patch("pdf_utils._load_pdf_libraries", return_value=libraries):
            result = markdown_to_pdf(self.source, self.output)
        self.assertEqual(result, self.output)
        self.assertEqual(self.output.read_bytes(), b"%PDF-success")
        kwargs = html.call_args.kwargs
        document = kwargs["string"]
        self.assertIn('<html lang="cs">', document)
        self.assertIn("<title>Skladby &amp; materiály</title>", document)
        self.assertIn("<h1>Zatížení střechy</h1>", document)
        self.assertIn("<li>Žluťoučký kůň</li>", document)
        self.assertIn("<table>", document)
        self.assertIn("<td>Vláknitá izolace</td>", document)
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertEqual(kwargs["base_url"], self.root.as_uri() + "/")
        self.assertIs(kwargs["url_fetcher"], _local_resource_fetcher)
        self.assertIn("size: A4 portrait; margin: 20mm", css.call_args.kwargs["string"])
        self.assertIn("DejaVu Sans", css.call_args.kwargs["string"])
        self.assertIn("table-header-group", css.call_args.kwargs["string"])
        self.assertFalse(any(p.exists() for p in temporary_outputs))

    def test_custom_page_settings_and_string_paths(self):
        def write(target, **kwargs):
            Path(target).write_bytes(b"%PDF")
        libraries, _, css = self.libraries(write)
        with patch("pdf_utils._load_pdf_libraries", return_value=libraries):
            markdown_to_pdf(str(self.source), str(self.output), paper="A3", orientation="landscape", margin=10)
        self.assertIn("size: A3 landscape; margin: 10mm", css.call_args.kwargs["string"])

    def test_invalid_inputs_do_not_load_renderer_or_create_output_directory(self):
        invalid = (
            ((True, self.output), {}, TypeError),
            ((self.root / "missing.md", self.output), {}, FileNotFoundError),
            ((self.source, self.output.with_suffix(".png")), {}, ValueError),
            ((self.source, self.output), {"paper": "A99"}, ValueError),
            ((self.source, self.output), {"orientation": "diagonal"}, ValueError),
            ((self.source, self.output), {"margin": -1}, ValueError),
            ((self.source, self.output), {"margin": 105}, ValueError),
            ((self.source, self.output), {"margin": float("inf")}, ValueError),
            ((self.source, self.output), {"margin": True}, TypeError),
        )
        with patch("pdf_utils._load_pdf_libraries") as load:
            for args, kwargs, error in invalid:
                with self.subTest(args=args, kwargs=kwargs), self.assertRaises(error):
                    markdown_to_pdf(*args, **kwargs)
            load.assert_not_called()
        self.assertFalse(self.output.parent.exists())

    def test_existing_pdf_is_preserved_if_render_fails_or_creates_no_pdf(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous PDF")
        for error in (RuntimeError("render failed"), None):
            def write(target, **kwargs):
                if error is not None:
                    Path(target).write_bytes(b"partial PDF")
                    raise error
            libraries, _, _ = self.libraries(write)
            with self.subTest(error=error), patch("pdf_utils._load_pdf_libraries", return_value=libraries):
                with self.assertRaises(RuntimeError):
                    markdown_to_pdf(self.source, self.output)
            self.assertEqual(self.output.read_bytes(), b"previous PDF")
            self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_output_directory_and_non_markdown_input_are_rejected(self):
        directory = self.root / "directory.pdf"
        directory.mkdir()
        with self.assertRaises(IsADirectoryError):
            markdown_to_pdf(self.source, directory)
        other_source = self.root / "input.txt"
        other_source.write_text("Text", encoding="utf-8")
        with self.assertRaises(ValueError):
            markdown_to_pdf(other_source, self.output)

    def test_network_resources_are_not_fetched_and_local_resources_use_weasyprint(self):
        fetch = Mock(return_value={"string": b"image"})
        with patch.dict("sys.modules", {"weasyprint": SimpleNamespace(default_url_fetcher=fetch)}):
            for url in ("https://example.com/image.png", "http://example.com/image.png", "ftp://example.com/image.png"):
                with self.assertRaises(ValueError):
                    _local_resource_fetcher(url)
            fetch.assert_not_called()
            for url in (self.source.as_uri(), "data:image/png;base64,AA=="):
                self.assertEqual(_local_resource_fetcher(url), {"string": b"image"})
                fetch.assert_called_with(url)

    def test_helper_is_available_through_ifc_utils(self):
        import ifc_utils
        self.assertIs(ifc_utils.markdown_to_pdf, markdown_to_pdf)
        self.assertIn("markdown_to_pdf", ifc_utils.__all__)


if __name__ == "__main__":
    unittest.main()
