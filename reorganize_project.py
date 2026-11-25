"""Rename existing project drawings and export their cached SVG sheets.

No IFC model generation is needed. Old files are removed only after every
new PDF has exported successfully; the original files are first backed up.
"""

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from drawing_title_block import load_title_block, title_block_svg
from pdf_utils import save_drawing_svg
from project_documents import DRAWINGS, PROJECT_DIR, ELE, ZTI


SVG = "http://www.w3.org/2000/svg"
REPORT_MOVES = {
    "A. DSP Průvodní Zpráva/A_DSP_Průvodní zpráva.doc": "A. Průvodní list/A. Průvodní list.doc",
    "B. DSP Souhrnná Technická Zpráva/B_DSP_Souhrnná technická zpráva_.docx": "B. Souhrnná technická zpráva/B. Souhrnná technická zpráva.docx",
    "D1.4. Zařízení Silnoproudé Elektrotechniky/D1.4.0. Technická zpráva.doc": f"{ELE}/D.1.2.1-ELE-01. Technická zpráva.doc",
    "D1.5. Zdravotechnické Instalace/D.1.5.0. Technická zpráva.docx": f"{ZTI}/D.1.2.1-ZTI-01. Technická zpráva.docx",
}


def _replace_title_block(svg, replacement):
    """Replace only the title-block group, preserving all drawing geometry."""
    start = re.search(r'<(?P<tag>(?:\w+:)?g)\b[^>]*\bclass="drawing-title-block"[^>]*>', svg)
    if start is None:
        return svg
    depth = 1
    for tag in re.finditer(r'</?(?:\w+:)?g\b[^>]*>', svg[start.end():]):
        value = tag[0]
        depth += -1 if value.startswith('</') else (0 if value.endswith('/>') else 1)
        if depth == 0:
            end = start.end()+tag.end()
            return svg[:start.start()]+replacement+svg[end:]
    raise ValueError("Unclosed drawing title block")


def update_sheet(svg, drawing, settings):
    """Update naming text and the title block without serializing model paths."""
    old_stem = Path(drawing.legacy_pdf).stem
    new_stem = Path(drawing.filename).stem
    svg = svg.replace(escape(old_stem), escape(new_stem))
    if drawing.key == "situace":
        svg = svg.replace("C1.2 Koordinační situace", f"{drawing.number} {drawing.title}")
    old_number = old_stem.split('. ',1)[0]
    svg = re.sub(rf'(?<![\w.]){re.escape(old_number)}(?![\d.])', drawing.number, svg)
    root = ET.fromstring(svg)
    block = root.find(f'.//{{{SVG}}}g[@class="drawing-title-block"]')
    if block is not None:
        if settings is None:
            raise ValueError("Existing title block requires project title_block.json")
        texts = [e.text or "" for e in block.iter(f'{{{SVG}}}text')]
        paper = texts[texts.index("FORMÁT:")+1]
        scale = texts[texts.index("MĚŘÍTKO:")+1]
        replacement = title_block_svg(settings, filename=drawing.filename, paper=paper, scale=scale, x=0, y=0)
        replacement = replacement.replace('<g ', f'<g xmlns="{SVG}" ', 1)
        replacement = replacement.replace('transform="translate(0, 0)"',
                                          f'transform="{block.get("transform")}"',1)
        svg = _replace_title_block(svg,replacement)
    return re.sub(r'(?m)[ \t]+$', '',svg)


def reorganize(project=PROJECT_DIR):
    project = Path(project).resolve()
    inkscape = shutil.which("inkscape")
    if not inkscape:
        raise FileNotFoundError("Inkscape is required")
    for old in REPORT_MOVES:
        path = project / old
        if path.exists() and list(path.parent.glob('.~lock.*')):
            raise RuntimeError(f"Save and close the report before moving it: {path}")
    inputs = {}
    for key, drawing in DRAWINGS.items():
        old_pdf = project / drawing.legacy_pdf
        old_svg = old_pdf.parent / 'src' / old_pdf.with_suffix('.svg').name
        source = old_svg if old_svg.exists() else drawing.svg(project)
        if not source.is_file():
            raise FileNotFoundError(f"No complete cached SVG sheet for {key}: {source}")
        inputs[key] = source
    settings = load_title_block(project/'ground.svg')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = Path('/tmp')/f'projekt2-before-reorganization-{stamp}.zip'
    files = set(inputs.values())
    for drawing in DRAWINGS.values():
        files.update(p for p in (project/drawing.legacy_pdf,drawing.pdf(project),drawing.working_svg(project)) if p.is_file())
    files.update(project/old for old in REPORT_MOVES if (project/old).is_file())
    obsolete = project/'C. Situace Stavby/C1.2 Koordinační Situace.pdf'
    if obsolete.exists():
        files.add(obsolete)
    with ZipFile(backup,'w',ZIP_DEFLATED) as archive:
        for source in sorted(files):
            archive.write(source,source.relative_to(project))
    print(f'Backup: {backup}',flush=True)
    staged_pdfs = []
    # Keep old PDFs and SVGs in place until the entire set has rendered.
    with TemporaryDirectory(prefix='project-reorganization-') as directory:
        for index,(key,drawing) in enumerate(DRAWINGS.items(),1):
            source = inputs[key]
            sheet = update_sheet(source.read_text(encoding='utf-8'),drawing,settings)
            target = drawing.pdf(project)
            saved = save_drawing_svg(source,target,svg=sheet)
            temporary_pdf = Path(directory)/f'{index:02d}.pdf'
            subprocess.run([inkscape,str(saved),f'--export-filename={temporary_pdf}',
                            '--export-type=pdf','--export-area-page','--batch-process'],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if not temporary_pdf.is_file() or not temporary_pdf.read_bytes().startswith(b'%PDF-'):
                raise RuntimeError(f'PDF export failed: {target}')
            staged_pdfs.append((temporary_pdf,target))
            print(f'Prepared {index}/{len(DRAWINGS)}: {drawing.filename}',flush=True)
        for source,target in staged_pdfs:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    for key,drawing in DRAWINGS.items():
        working = drawing.working_svg(project)
        if working.exists():
            working.write_text(update_sheet(working.read_text(encoding='utf-8'),drawing,settings),encoding='utf-8')
        old_pdf = project/drawing.legacy_pdf
        old_svg = old_pdf.parent/'src'/old_pdf.with_suffix('.svg').name
        for old in (old_pdf,old_svg):
            if old.exists() and old not in (drawing.pdf(project),drawing.svg(project)):
                old.unlink()
    for old,new in REPORT_MOVES.items():
        source,target = project/old,project/new
        if source.exists():
            if target.exists():
                raise FileExistsError(target)
            target.parent.mkdir(parents=True,exist_ok=True)
            source.rename(target)
    if obsolete.exists():
        obsolete.unlink()  # Earlier duplicate; preserved in the backup.
    old_folders = {str(Path(d.legacy_pdf).parent) for d in DRAWINGS.values()}
    old_folders.update(str(Path(p).parent) for p in REPORT_MOVES)
    for folder in old_folders:
        path = project/folder
        for directory in (path/'src',path):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    index = [dict(number=d.number,title=d.title,pdf=str(d.pdf(project).relative_to(project)),
                  svg=str(d.svg(project).relative_to(project)),former_pdf=d.legacy_pdf)
             for d in DRAWINGS.values()]
    (project/'seznam_vykresu.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Reorganized {len(DRAWINGS)} drawings and their sources.',flush=True)
    return backup


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=PROJECT_DIR)
    reorganize(parser.parse_args().project)
