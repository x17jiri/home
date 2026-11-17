"""A shared, physical-size title block for exported project drawing PDFs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from textwrap import wrap
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


TITLE_BLOCK_WIDTH = 85.0
TITLE_BLOCK_HEIGHT = 64.0
TITLE_BLOCK_GAP = 2.0
TITLE_BLOCK_EDGE = 5.0
TITLE_BLOCK_CONFIG = "title_block.json"


def load_title_block(svg_path: Path) -> dict[str, str] | None:
    """Opt a project's drawings in through a config beside their source SVGs."""
    path = svg_path.parent / TITLE_BLOCK_CONFIG
    if not path.exists():
        return None
    settings = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict) or any(
        key not in {"author", "chief_engineer", "responsible_designer", "investor", "project", "stage", "date"}
        or not isinstance(value, str) for key, value in settings.items()
    ):
        raise ValueError(f"{path}: use text fields author, chief_engineer, responsible_designer, investor, project, stage and optional date")
    return settings


def drawing_scale(svg: str) -> str:
    """Read scales from final drawing headers, including composed sheets."""
    scales = []
    for element in ET.fromstring(svg).iter():
        if "drawing-title" not in element.get("class", "").split():
            continue
        match = re.search(r"(\d+\s*:\s*\d+)\s*$", "".join(element.itertext()))
        if match:
            scale = re.sub(r"\s+", "", match[1])
            if scale not in scales:
                scales.append(scale)
    return ", ".join(scales) or "—"


def title_block_svg(settings: Mapping[str, str], *, filename: str, scale: str,
                    paper: str, x: float, y: float) -> str:
    """Render a Czech title block in mm; all text remains selectable."""
    match = re.fullmatch(r"([A-Za-z]\d+(?:\.\d+)+)\.\s+(.+)", Path(filename).stem)
    number, title = match.groups() if match else ("—", Path(filename).stem)
    parts = [
        f'<g class="drawing-title-block" transform="translate({x:g}, {y:g})" '
        f'data-width="{TITLE_BLOCK_WIDTH:g}" data-height="{TITLE_BLOCK_HEIGHT:g}">',
        '<rect x="0" y="0" width="85" height="64" style="fill:white;stroke:none"/>',
        '<rect x="0" y="6" width="85" height="58" '
        'style="fill:white;stroke:black;stroke-width:.35"/>',
        '<path d="M0 11H55 M0 16H55 M0 21H55 M0 26H55 M55 6V36 '
        'M0 36H85 M55 36V64 M55 43H85 M55 50H85 M55 57H85" '
        'style="fill:none;stroke:black;stroke-width:.18"/>',
        '<g class="title-block-logo" data-x="55" data-y="6" data-width="30" data-height="30"/>',
    ]

    def text(x, y, value, size=2.5, *, bold=False, anchor="start"):
        parts.append(
            f'<text x="{x:g}" y="{y:g}" style="font-family:DejaVu Sans,sans-serif;'
            f'font-size:{size:g}px;font-weight:{"bold" if bold else "normal"};'
            f'text-anchor:{anchor};fill:black;stroke:none">{escape(value)}</text>'
        )

    text(42.5, 4.6, settings.get("stage", ""), 4.5, bold=True, anchor="middle")
    for y, label, field in (
        (9.4, "AUTOR NÁVRHU:", "author"),
        (14.4, "HL. ING. PROJEKTU:", "chief_engineer"),
        (19.4, "ZOD. PROJEKTANT:", "responsible_designer"),
        (24.4, "INVESTOR:", "investor"),
    ):
        text(2, y, label, 1.7, bold=True)
        text(25, y, settings.get(field, ""), 2.7)
    text(2, 29, "AKCE:", 1.7)
    text(2, 34, settings.get("project", ""), 3.8, bold=True)
    text(2, 39, "VÝKRES:", 1.7)
    for index, line in enumerate(wrap(title, width=27, max_lines=5, placeholder="…")):
        text(2, 44+4*index, line, 3, bold=True)
    for row, label, value in (
        (0, "DATUM:", settings.get("date") or datetime.now(ZoneInfo("Europe/Prague")).strftime("%m/%Y")),
        (1, "FORMÁT:", paper),
        (2, "MĚŘÍTKO:", scale),
        (3, "Č. VÝKRESU:", number),
    ):
        text(57, 38.5+7*row, label, 1.6)
        text(57, 41.9+7*row, value, 3 if row == 3 else 2.5, bold=row == 3)
    parts.append("</g>")
    return "".join(parts)
