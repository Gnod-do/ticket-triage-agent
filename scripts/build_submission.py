#!/usr/bin/env python3
"""Build the official submission files from Markdown sources.

  submissions/main-solution.ru.md     -> dist/Решение_Q1-4_Q6.docx  (checked: <= 15 000 characters)
  submissions/05-effect-metrics.ru.md -> dist/Q5_Эффект_внедрения.md (copied as required: separate .md)

Character count = all visible text of the DOCX (paragraphs + tables, spaces included),
i.e. what a reviewer sees in Word statistics. Images and Markdown markup are not counted.
Usage: python scripts/build_submission.py [--pdf]   (--pdf converts via Microsoft Word on macOS)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "submissions"
DIST = ROOT / "dist"
LIMIT = 15_000
NAVY, TEAL, GREY = RGBColor(0x10, 0x31, 0x4C), RGBColor(0x00, 0x7F, 0x84), RGBColor(0x55, 0x63, 0x7A)
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def add_runs(p, text: str, size: float | None = None, bold: bool = False):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.color.rgb = NAVY
        else:
            r = p.add_run(part); r.bold = bold
        if size:
            r.font.size = Pt(size)


def shade(cell, hex_fill: str):
    tc = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:fill"), hex_fill); tc.append(sh)


def add_table(doc, rows: list[list[str]]):
    cols = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=cols)
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j in range(cols):
            p = cells[j].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            add_runs(p, row[j] if j < len(row) else "", size=8.5, bold=(i == 0))
            if i == 0:
                shade(cells[j], "E6EEF5")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build_docx(md_path: Path, out: Path) -> int:
    md = re.sub(r"<!--.*?-->", "", md_path.read_text(encoding="utf-8"), flags=re.S)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2))
    normal = doc.styles["Normal"]; normal.font.name = "Arial"; normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(4); normal.paragraph_format.line_spacing = 1.1
    for name, size, color in (("Title", 18, NAVY), ("Heading 1", 14, NAVY), ("Heading 2", 12, TEAL), ("Heading 3", 11, TEAL)):
        st = doc.styles[name]; st.font.name = "Arial"; st.font.size = Pt(size); st.font.color.rgb = color

    lines, i = md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            p = doc.add_paragraph(); p.paragraph_format.left_indent = Cm(0.4)
            r = p.add_run("\n".join(block)); r.font.name = "Consolas"; r.font.size = Pt(8.5); r.font.color.rgb = NAVY
            shade_p = OxmlElement("w:shd"); shade_p.set(qn("w:val"), "clear"); shade_p.set(qn("w:fill"), "F3F5F8")
            p._p.get_or_add_pPr().append(shade_p)
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            add_table(doc, rows)
            continue
        elif m := re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip()):
            img = (md_path.parent / m.group(2)).resolve()
            from PIL import Image
            w, h = Image.open(img).size
            width_cm = min(16.0, 19.0 * w / h)  # fit into a 16 x 19 cm box
            doc.add_picture(str(img), width=Cm(width_cm))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap = doc.add_paragraph(); add_runs(cap, f"Рис. {m.group(1)}", size=8.5)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER; cap.runs[0].font.color.rgb = GREY
        elif line.startswith("# "):
            doc.add_paragraph(line[2:].strip(), style="Title")
        elif m := re.match(r"(#{2,4}) (.*)", line):
            doc.add_heading(m.group(2).strip(), level=len(m.group(1)) - 1)
        elif m := re.match(r"(\s*)[-*] (.*)", line):
            p = doc.add_paragraph(style="List Bullet" if not m.group(1) else "List Bullet 2"); add_runs(p, m.group(2))
        elif m := re.match(r"(\s*)(\d+)\. (.*)", line):  # keep source numbering (Word lists would continue)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(0.63), Cm(-0.63)
            add_runs(p, f"{m.group(2)}.\t{m.group(3)}")
        elif line.strip():
            add_runs(doc.add_paragraph(), line.strip())
        i += 1

    DIST.mkdir(exist_ok=True)
    doc.save(out)
    text = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            text += [c.text for c in row.cells]
    return sum(len(x) for x in text)


def to_pdf_with_word(docx: Path) -> Path:
    pdf = docx.with_suffix(".pdf")
    script = f'''
    tell application "Microsoft Word"
      open POSIX file "{docx}"
      set d to active document
      save as d file name (POSIX file "{pdf}" as string) file format format PDF
      close d saving no
    end tell'''
    subprocess.run(["osascript", "-e", script], check=True)
    return pdf


def main(argv: list[str]) -> int:
    main_docx = DIST / "Решение_Q1-4_Q6.docx"
    n = build_docx(SRC / "main-solution.ru.md", main_docx)
    print(f"{main_docx.name}: {n} characters (limit {LIMIT})")
    shutil.copy(SRC / "05-effect-metrics.ru.md", DIST / "Q5_Эффект_внедрения.md")
    if "--pdf" in argv:
        print("PDF:", to_pdf_with_word(main_docx))
    if n > LIMIT:
        print(f"FAIL: {n - LIMIT} characters over the limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
