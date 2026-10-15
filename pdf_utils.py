"""Markdown-to-PDF helpers, independent of the IFC/drawing libraries."""

from __future__ import annotations

import argparse
from html import escape
from math import isfinite
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

__all__ = ["markdown_to_pdf"]

_PAPER_SIZES = {"A4": (210, 297), "A3": (297, 420), "A2": (420, 594),
                "A1": (594, 841), "A0": (841, 1189)}

_MARKDOWN_CSS = """
@page {
    @bottom-center { content: counter(page); font-size: 9pt; color: #666; }
}
body { font-family: "DejaVu Sans", sans-serif; font-size: 10.5pt; line-height: 1.45; }
h1, h2, h3, h4 { break-after: avoid; line-height: 1.2; }
h1 { font-size: 19pt; }
h2 { font-size: 15pt; margin-top: 1.2em; }
h3 { font-size: 12pt; }
p, ul, ol { margin: 0.5em 0; }
li > p { margin: 0.2em 0; }
a { color: #225588; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; font-size: 10pt; }
thead { display: table-header-group; background: #f2f2f2; }
tr { break-inside: avoid; }
th, td { border: 0.2mm solid #bbb; padding: 1.5mm 2mm; text-align: left; }
img { max-width: 100%; height: auto; }
blockquote { margin: 0.7em 0; padding-left: 4mm; border-left: 0.6mm solid #ccc; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f5f5f5; padding: 3mm; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }
hr { border: none; border-top: 0.2mm solid #bbb; }
"""


def _load_pdf_libraries():
    # Keep the normal IFC workflow usable until these optional dependencies
    # are installed in the interpreter used for PDF generation.
    try:
        from markdown_it import MarkdownIt
        from weasyprint import CSS, HTML
    except ImportError as error:
        raise RuntimeError(
            "Markdown PDF export requires markdown-it-py and WeasyPrint. "
            "Install the project requirements in your Python environment."
        ) from error
    return MarkdownIt, HTML, CSS


def _local_resource_fetcher(url, *args, **kwargs):
    """Render local/data images without making unexpected network requests."""
    if urlparse(url).scheme not in {"file", "data"}:
        raise ValueError("Markdown PDF export only loads local files or data URLs")
    from weasyprint import default_url_fetcher
    return default_url_fetcher(url, *args, **kwargs)


def markdown_to_pdf(
    source: str | PathLike[str],
    output: str | PathLike[str],
    *,
    paper: str = "A4",
    orientation: str = "portrait",
    margin: float = 20,
) -> Path:
    """Render UTF-8 Markdown to a paginated, selectable-text PDF.

    Defaults are A4 portrait, 20 mm margins and Czech-capable DejaVu fonts.
    Headings, lists, tables, fenced code and local images are supported.
    Image paths resolve relative to the Markdown file; raw HTML is escaped
    and remote resources are not downloaded. Existing PDFs are replaced only
    after a successful, nonempty export. Return the requested output path.
    """
    if not isinstance(source, (str, PathLike)) or not isinstance(output, (str, PathLike)):
        raise TypeError("source and output must be file paths")
    source_path, output_path = Path(source).resolve(), Path(output)
    if not source_path.is_file():
        raise FileNotFoundError(f"Markdown input is not a file: {source_path}")
    if source_path.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("source must use the .md or .markdown extension")
    target = output_path.resolve()
    if target.suffix.lower() != ".pdf":
        raise ValueError("output must use the .pdf extension")
    if target.exists() and not target.is_file():
        raise IsADirectoryError(f"PDF output is not a file: {target}")
    if not isinstance(paper, str) or paper not in _PAPER_SIZES:
        raise ValueError("paper must be A4, A3, A2, A1, or A0")
    if orientation not in {"portrait", "landscape"}:
        raise ValueError("orientation must be portrait or landscape")
    if isinstance(margin, bool):
        raise TypeError("margin must be a number in millimetres")
    try:
        margin = float(margin)
    except (TypeError, ValueError) as error:
        raise TypeError("margin must be a number in millimetres") from error
    if not isfinite(margin) or margin < 0 or 2 * margin >= min(_PAPER_SIZES[paper]):
        raise ValueError("margin must be finite, non-negative and leave usable paper area")

    MarkdownIt, HTML, CSS = _load_pdf_libraries()
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    body = parser.render(source_path.read_text(encoding="utf-8"))
    document = (
        '<!DOCTYPE html><html lang="cs"><head><meta charset="utf-8">'
        f'<title>{escape(source_path.stem)}</title></head><body>{body}</body></html>'
    )
    css = f"@page {{ size: {paper} {orientation}; margin: {margin:g}mm; }}\n" + _MARKDOWN_CSS
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{target.stem}-markdown-", dir=target.parent) as directory:
        temporary_pdf = Path(directory) / target.name
        HTML(string=document, base_url=source_path.parent.as_uri() + "/",
             url_fetcher=_local_resource_fetcher).write_pdf(str(temporary_pdf), stylesheets=[CSS(string=css)])
        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise RuntimeError(f"WeasyPrint did not create the PDF: {target}")
        temporary_pdf.replace(target)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Markdown to a styled PDF (default: A4 portrait).")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--paper", choices=_PAPER_SIZES, default="A4")
    parser.add_argument("--orientation", choices=("portrait", "landscape"), default="portrait")
    parser.add_argument("--margin", type=float, default=20, help="Page margin in mm (default: 20)")
    arguments = parser.parse_args()
    print(markdown_to_pdf(arguments.source, arguments.output, paper=arguments.paper,
                          orientation=arguments.orientation, margin=arguments.margin))
