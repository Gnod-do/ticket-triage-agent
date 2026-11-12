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
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
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


def cell_margins(cell, top=40, bottom=40, left=80, right=80):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        el = OxmlElement(f"w:{k}"); el.set(qn("w:w"), str(v)); el.set(qn("w:type"), "dxa"); mar.append(el)
    tcPr.append(mar)


def table_borders(table, color="D9E0E8", size=4):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(size)); el.set(qn("w:space"), "0"); el.set(qn("w:color"), color)
        borders.append(el)
    tblPr.append(borders)


def para_shade(p, fill: str, left_color: str | None = None, left_size: int = 18):
    pPr = p._p.get_or_add_pPr()
    if left_color:
        bdr = OxmlElement("w:pBdr")
        el = OxmlElement("w:left"); el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(left_size))
        el.set(qn("w:space"), "8"); el.set(qn("w:color"), left_color); bdr.append(el)
        pPr.append(bdr)
    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:fill"), fill); pPr.append(sh)


def add_field(run, instr: str):
    for tag, extra in (("begin", None), ("instr", instr), ("end", None)):
        if tag == "instr":
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = extra
        else:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), tag)
        run._r.append(el)


def footer(sec):
    p = sec.footer.paragraphs[0]
    p.paragraph_format.tab_stops.add_tab_stop(Cm(17), WD_TAB_ALIGNMENT.RIGHT)
    r = p.add_run("Intelligence Cup 2026 · кейс «Газпром нефти» · ИИ-агент «поддержка → продукт»\t")
    r.font.size = Pt(8); r.font.color.rgb = GREY; r.font.name = "Arial"
    r2 = p.add_run("стр. "); r2.font.size = Pt(8); r2.font.color.rgb = GREY; r2.font.name = "Arial"
    r3 = p.add_run(); r3.font.size = Pt(8); r3.font.color.rgb = GREY; r3.font.name = "Arial"
    add_field(r3, "PAGE")


def add_table(doc, rows: list[list[str]]):
    cols = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_borders(t)
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j in range(cols):
            p = cells[j].paragraphs[0]
            p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.05
            add_runs(p, row[j] if j < len(row) else "", size=8.5, bold=(i == 0))
            cell_margins(cells[j])
            if i == 0:
                shade(cells[j], "10314C")
                for r in p.runs:
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            elif i % 2 == 0:
                shade(cells[j], "F5F8FB")
        if i == 0:  # repeat header on page break
            trPr = t.rows[0]._tr.get_or_add_trPr(); h = OxmlElement("w:tblHeader"); h.set(qn("w:val"), "true"); trPr.append(h)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build_docx(md_path: Path, out: Path) -> int:
    md = re.sub(r"<!--.*?-->", "", md_path.read_text(encoding="utf-8"), flags=re.S)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2))
    footer(sec)
    normal = doc.styles["Normal"]; normal.font.name = "Arial"; normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0x1E, 0x27, 0x33)
    normal.paragraph_format.space_after = Pt(5); normal.paragraph_format.line_spacing = 1.15
    for name, size, color, before, after in (("Title", 20, NAVY, 0, 2), ("Heading 1", 14, NAVY, 18, 6),
                                             ("Heading 2", 11.5, TEAL, 12, 4), ("Heading 3", 10.5, NAVY, 10, 3)):
        st = doc.styles[name]; st.font.name = "Arial"; st.font.size = Pt(size); st.font.color.rgb = color
        st.font.bold = True; st.font.italic = False
        st.paragraph_format.space_before = Pt(before); st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True
        rpr = st.element.get_or_add_rPr()  # Word's heading styles carry a theme font that overrides .font.name
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            rfonts.set(qn(f"w:{attr}"), "Arial")
        for attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            rfonts.attrib.pop(qn(f"w:{attr}"), None)
    for name in ("List Bullet", "List Bullet 2"):
        st = doc.styles[name]; st.font.name = "Arial"; st.font.size = Pt(10.5)
        st.paragraph_format.space_after = Pt(2)
    fig_no = 0

    lines, i = md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            p = doc.add_paragraph(); p.paragraph_format.left_indent = Cm(0.3)
            p.paragraph_format.space_after = Pt(2); p.paragraph_format.line_spacing = 1.05
            r = p.add_run("\n".join(block)); r.font.name = "Consolas"; r.font.size = Pt(8.5); r.font.color.rgb = NAVY
            para_shade(p, "F3F5F8", "00918F")
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
            width_cm = min(17.0, 17.0 * w / h)  # fit into a 17 x 17 cm box
            doc.add_picture(str(img), width=Cm(width_cm))
            pic = doc.paragraphs[-1]; pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pic.paragraph_format.keep_with_next = True; pic.paragraph_format.space_before = Pt(6)
            fig_no += 1
            cap = doc.add_paragraph(); add_runs(cap, f"Рис. {fig_no}. {m.group(1)}", size=8.5)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER; cap.paragraph_format.space_after = Pt(10)
            for r in cap.runs:
                r.font.color.rgb = GREY; r.font.italic = True
        elif line.startswith("# "):
            doc.add_paragraph(line[2:].strip(), style="Title")
        elif line.startswith("> "):  # callout
            p = doc.add_paragraph(); add_runs(p, line[2:].strip())
            p.paragraph_format.left_indent = Cm(0.3); p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(8)
            para_shade(p, "E8F4F4", "00918F", 24)
        elif line.startswith("→ "):  # commentary under a prompt block
            p = doc.add_paragraph(); add_runs(p, line.strip(), size=9.5)
            p.paragraph_format.left_indent = Cm(0.3); p.paragraph_format.space_after = Pt(8)
            for r in p.runs:
                r.font.color.rgb = GREY; r.font.italic = True
        elif i == 2 and line.startswith("**Intelligence Cup"):  # subtitle under the title
            p = doc.add_paragraph(); add_runs(p, line.strip(), size=10)
            p.paragraph_format.space_after = Pt(12)
            for r in p.runs:
                r.font.color.rgb = GREY; r.font.bold = False
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
