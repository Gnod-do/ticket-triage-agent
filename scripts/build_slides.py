#!/usr/bin/env python3
"""Build the 10-slide companion deck (16:9): visual-first, minimal text.

  python scripts/build_slides.py [--pdf]  -> dist/Презентация.pptx (+ .pdf via Keynote if --pdf)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.dml import MSO_LINE  # noqa: E402
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from fbagent.finance import scenarios, scenarios_chart, tornado  # noqa: E402

DIAG = ROOT / "docs" / "diagrams" / "rendered"
DIST = ROOT / "dist"
CHARTS = DIST / "charts"
NAVY, TEAL, ORANGE = RGBColor(0x10, 0x31, 0x4C), RGBColor(0x00, 0x91, 0x8F), RGBColor(0xF5, 0x6A, 0x2B)
GREY, LIGHT, WHITE = RGBColor(0x5A, 0x67, 0x75), RGBColor(0xF2, 0xF5, 0xF8), RGBColor(0xFF, 0xFF, 0xFF)
TEAL_TINT, ORANGE_TINT, ICE = RGBColor(0xE4, 0xF3, 0xF2), RGBColor(0xFD, 0xEB, 0xE1), RGBColor(0xC9, 0xD6, 0xE2)
LINE = RGBColor(0x8A, 0x9B, 0xAD)
W, H = Inches(13.333), Inches(7.5)
TOTAL = 10
I = Inches


# ---------------------------------------------------------------- primitives
def text(slide, x, y, w, h, s, size=16, bold=False, color=NAVY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, margin=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    if margin is not None:
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = margin
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run(); r.text = line
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, "Arial"
    return tb


def box(slide, x, y, w, h, fill=LIGHT, line=None, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, dash=False):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid(); s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line; s.line.width = Pt(1.25)
        if dash:
            s.line.dash_style = MSO_LINE.DASH
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def label(slide, x, y, w, h, s, fill=LIGHT, color=NAVY, size=13, bold=False, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12):
    """Box with centred text: the building block of the native diagrams."""
    b = box(slide, x, y, w, h, fill, line, radius, shape)
    tf = b.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = I(0.08); tf.margin_top = tf.margin_bottom = I(0.04)
    for i, line_ in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = line_
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, "Arial"
    return b


def arrow(slide, x1, y1, x2, y2, color=LINE, width=1.75, dash=False, head=True):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color; c.line.width = Pt(width)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    if head:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle"); tail.set("w", "med"); tail.set("len", "med")
    return c


def numcircle(slide, x, y, n, d=I(0.42), fill=NAVY, color=WHITE, size=13):
    return label(slide, x, y, d, d, str(n), fill, color, size, True, shape=MSO_SHAPE.OVAL)


def stat(slide, x, y, w, big, lab, color=TEAL, h=I(1.7), big_size=36, fill=LIGHT):
    box(slide, x, y, w, h, fill)
    text(slide, x + I(0.25), y + I(0.1), w - I(0.5), I(0.9), big, big_size, True, color)
    text(slide, x + I(0.25), y + h - I(0.75), w - I(0.5), I(0.7), lab, 12, False, GREY)


def base(prs, title, n, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    if kicker:
        text(s, I(0.6), I(0.3), I(12), I(0.4), kicker.upper(), 11, True, TEAL)
    text(s, I(0.6), I(0.58), I(12.2), I(0.9), title, 28, True, NAVY)
    text(s, I(0.6), I(7.0), I(9), I(0.3), "Intelligence Cup 2026 · «Газпром нефть» · ИИ-агент «поддержка → продукт»", 9, False, GREY)
    text(s, I(12.2), I(7.0), I(0.8), I(0.3), f"{n} / {TOTAL}", 9, False, GREY, PP_ALIGN.RIGHT)
    return s


def picture_fit(slide, path, x, y, max_w, max_h):
    from PIL import Image
    w, h = Image.open(path).size
    scale = min(max_w / w, max_h / h)
    pw, ph = int(w * scale), int(h * scale)
    return slide.shapes.add_picture(str(path), x + (max_w - pw) // 2, y + (max_h - ph) // 2, pw, ph)


def did_schema(path: Path):
    """Schematic (no data) of the difference-in-differences read-out for M1."""
    import numpy as np
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    t = np.arange(0, 13)
    ctrl = 10 + 0.25 * t
    pil = 10.3 + 0.25 * t
    cf = pil.copy()
    pil_after = np.where(t >= 6, pil - 0.9 * (t - 6), pil)
    teal, orange, grey, ink = "#00918F", "#F56A2B", "#8A9BAD", "#10314C"
    ax.plot(t, ctrl, color=grey, lw=2, label="контрольные продукты")
    ax.plot(t, cf, color=teal, lw=1.5, ls="--", label="пилот без агента (ожидание)")
    ax.plot(t, pil_after, color=teal, lw=2.4, label="пилотные продукты")
    ax.axvline(6, color=ink, lw=1, ls=":")
    ax.text(6.15, 13.6, "запуск агента", color=ink, fontsize=9, va="top")
    ax.annotate("", xy=(12, pil_after[-1]), xytext=(12, cf[-1]), arrowprops=dict(arrowstyle="<->", color=orange, lw=1.8))
    ax.text(11.85, (pil_after[-1] + cf[-1]) / 2, "M1", color=orange, fontsize=12, fontweight="bold", ha="right", va="center")
    ax.set_xlim(0, 12.6); ax.set_ylim(3, 14)
    ax.set_xlabel("недели", color=ink, fontsize=9); ax.set_ylabel("обращений по теме", color=ink, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(grey)
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=220); plt.close(fig)


# ---------------------------------------------------------------- deck
def build() -> Path:
    CHARTS.mkdir(parents=True, exist_ok=True)
    rows = scenarios(ROOT / "demo" / "finance" / "assumptions.yaml")
    base_row = next(r for r in rows if r["name"] == "base")
    scenarios_chart(rows, CHARTS / "scenarios.png")
    tornado(base_row["params"], CHARTS / "tornado.png", figsize=(6.4, 3.9), fontsize=9)
    did_schema(CHARTS / "did_schema.png")

    prs = Presentation(); prs.slide_width, prs.slide_height = W, H

    # 1 — title ---------------------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H); bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    text(s, I(0.8), I(0.6), I(11), I(0.4), "INTELLIGENCE CUP 2026 · КЕЙС «ГАЗПРОМ НЕФТИ»", 12, True, TEAL)
    text(s, I(0.8), I(1.8), I(8.2), I(2.2), "ИИ-агент, который слышит\nповторяющиеся просьбы\nпользователей", 38, True, WHITE)
    text(s, I(0.8), I(4.1), I(8.0), I(0.8), "Из техподдержки — в продуктовые команды", 18, False, ICE)
    # visual: scattered tickets → one topic → product team
    for i, (dx, dy) in enumerate([(0, 0), (0.35, 0.45), (0.7, 0.9), (0.2, 1.5), (0.6, 1.95)]):
        label(s, I(9.0 + dx), I(1.7 + dy), I(1.5), I(0.45), "обращение", ICE if i != 2 else TEAL, NAVY if i != 2 else WHITE, 10)
    arrow(s, I(10.9), I(2.9), I(11.5), I(2.9), ICE, 2)
    label(s, I(11.55), I(2.4), I(1.3), I(1.0), "1 тема\n→ команде", TEAL, WHITE, 12, True)
    for i, (big, lab) in enumerate([("0", "внешних API — только внутренние Qwen"), ("≤ 8", "вызовов инструментов на кластер"),
                                    ("0,86", "найденных тем на holdout (BM25: 0,14)")]):
        x = I(0.8 + 4.0 * i)
        text(s, x, I(5.25), I(3.6), I(0.8), big, 34, True, TEAL)
        text(s, x, I(5.95), I(3.6), I(0.6), lab, 12, False, ICE)

    # 2 — problem -------------------------------------------------------------
    s = base(prs, "Каждый видит 1–2 обращения. Сумму не видит никто", 2, "Проблема")
    # 40 managers as a grid; the same request scattered across 6 of them
    hot = {3, 11, 18, 26, 29, 37}
    for k in range(40):
        c, r = k % 10, k // 10
        x, y = I(0.6 + 0.76 * c), I(1.65 + 0.76 * r)
        label(s, x, y, I(0.64), I(0.64), "", TEAL if k in hot else LIGHT, WHITE, 9, radius=0.18)
    text(s, I(0.6), I(4.75), I(7.6), I(0.5), "40 менеджеров · одна и та же просьба у шести · повтор не видит никто", 14, True, NAVY)
    label(s, I(0.6), I(5.35), I(7.6), I(0.95), "«Не приходит код-смс для восстановления пароля»", TEAL_TINT, NAVY, 15)
    stat(s, I(8.8), I(1.65), I(4.1), "≈ 40", "менеджеров поддержки", h=I(1.45))
    stat(s, I(8.8), I(3.25), I(4.1), "2 канала", "звонки с записью · единое окно", h=I(1.45))
    stat(s, I(8.8), I(4.85), I(4.1), "0 ч", "дополнительной нагрузки на поддержку", ORANGE, h=I(1.45))

    # 3 — process (native swim-lanes) ------------------------------------------
    s = base(prs, "Агент работает рядом с поддержкой, а не вместо неё", 3, "Бизнес-процесс")
    lanes = [(I(1.5), I(1.5), "ПОДДЕРЖКА\nкак сейчас", WHITE, ICE), (I(3.15), I(2.25), "АГЕНТ\nрядом, не вместо", TEAL_TINT, None),
             (I(5.55), I(1.3), "КОМАНДА\nрешает человек", ORANGE_TINT, None)]
    for y, h, name, fill, ln in lanes:
        box(s, I(0.5), y, I(12.35), h, fill, ln, 0.04)
        text(s, I(0.65), y, I(1.6), h, name, 11, True, GREY, anchor=MSO_ANCHOR.MIDDLE)
    # lane 1
    label(s, I(2.4), I(1.95), I(2.0), I(0.6), "Пользователь", WHITE, NAVY, 13, line=ICE)
    arrow(s, I(4.4), I(2.25), I(5.2), I(2.25))
    label(s, I(5.2), I(1.95), I(2.4), I(0.6), "Менеджер поддержки", WHITE, NAVY, 13, line=ICE)
    arrow(s, I(7.6), I(2.25), I(8.6), I(2.25))
    label(s, I(8.6), I(1.95), I(2.4), I(0.6), "Решено по SLA ✓", NAVY, WHITE, 13, True)
    arrow(s, I(5.5), I(2.55), I(4.0), I(3.6), dash=True)
    text(s, I(4.9), I(2.85), I(2.2), I(0.4), "копия обращения", 10, False, GREY)
    # lane 2
    label(s, I(2.4), I(3.6), I(2.1), I(0.85), "Классификация\nQwen 3.8", TEAL, WHITE, 13, True)
    arrow(s, I(4.5), I(4.02), I(5.2), I(4.02))
    label(s, I(5.2), I(3.6), I(2.2), I(0.85), "Кластер\nпо продукту", TEAL, WHITE, 13, True)
    arrow(s, I(7.4), I(3.9), I(8.0), I(3.65)); arrow(s, I(7.4), I(4.15), I(8.0), I(4.9))
    label(s, I(8.0), I(3.3), I(2.5), I(0.75), "≥ 5 за неделю\n→ дайджест", WHITE, NAVY, 12, line=TEAL)
    label(s, I(8.0), I(4.55), I(2.5), I(0.75), "всплеск за час\n→ сигнал", WHITE, NAVY, 12, line=ORANGE)
    arrow(s, I(10.5), I(3.67), I(10.9), I(3.67)); arrow(s, I(10.5), I(4.92), I(10.9), I(4.92))
    label(s, I(10.9), I(3.3), I(1.85), I(0.75), "Продуктовая\nкоманда", NAVY, WHITE, 12, True)
    label(s, I(10.9), I(4.55), I(1.85), I(0.75), "Старший\nсмены", NAVY, WHITE, 12, True)
    # lane 3
    arrow(s, I(11.8), I(5.3), I(11.8), I(5.95))
    text(s, I(2.4), I(5.55), I(5.0), I(1.3), "Задачу в бэклоге создаёт человек.\nАгент — не создаёт и приоритеты не меняет.", 14, True, NAVY, anchor=MSO_ANCHOR.MIDDLE)
    label(s, I(8.0), I(5.95), I(2.5), I(0.7), "Принять ✓ → задача", ORANGE, WHITE, 13, True)
    label(s, I(10.9), I(5.95), I(1.85), I(0.7), "Отклонить ✗", WHITE, NAVY, 13, line=ORANGE)

    # 4 — architecture ----------------------------------------------------------
    s = base(prs, "5 логических сервисов — 3 процесса — 1 база данных", 4, "Архитектура")
    picture_fit(s, DIAG / "01-architecture.png", I(0.4), I(1.45), I(9.6), I(5.45))
    chips = [("0", "внешних API\nQwen 3.8 · Qwen-ASR · Qwen-VL"), ("3", "процесса\ningest · model-workers · приложение"),
             ("1", "база данных\nPostgreSQL + pgvector")]
    for i, (big, lab) in enumerate(chips):
        y = I(1.6 + 1.8 * i)
        box(s, I(10.2), y, I(2.7), I(1.6))
        text(s, I(10.4), y + I(0.08), I(2.3), I(0.8), big, 36, True, TEAL)
        text(s, I(10.4), y + I(0.85), I(2.3), I(0.75), lab, 11, False, NAVY)

    # 5 — load ------------------------------------------------------------------
    s = base(prs, "Нагрузка укладывается в ночное окно существующих GPU", 5, "Расчёт нагрузки")
    cards = [("≈ 1 400", "обращений в день"), ("≈ 0,9 млн", "токенов Qwen в день ≈ 15 мин"), ("≈ 2,3", "GPU-часа ASR в день"),
             ("≤ 240", "вызовов агента в неделю"), ("≈ 1,4 ГБ", "эмбеддингов за год"), ("1 / мин", "запрос к системе обращений")]
    for i, (big, lab) in enumerate(cards):
        stat(s, I(0.6 + 4.15 * (i % 3)), I(1.55 + 1.6 * (i // 3)), I(3.9), big, lab, h=I(1.45), big_size=34)
    # 24-hour bar
    text(s, I(0.6), I(4.95), I(12.2), I(0.4), "Сутки GPU: ≈ 2,5 ч работы умещаются в ночное окно", 14, True, NAVY)
    bx, bw, by, bh = I(0.6), I(12.2), I(5.45), I(0.6)
    box(s, bx, by, bw, bh, LIGHT, radius=0.3)
    box(s, bx, by, int(bw * 6 / 24), bh, ICE, radius=0.3)
    box(s, bx + I(0.25), by + I(0.1), int(bw * 2.5 / 24), bh - I(0.2), TEAL, radius=0.3)
    for hr in (0, 6, 12, 18, 24):
        text(s, bx + int(bw * hr / 24) - I(0.4), by + bh + I(0.02), I(0.8), I(0.3), f"{hr} ч", 10, False, GREY, PP_ALIGN.CENTER)
    text(s, bx + I(1.8), by + I(0.1), I(3.0), I(0.4), "ночное окно 6 ч", 11, False, GREY, anchor=MSO_ANCHOR.MIDDLE)
    text(s, bx + I(6.2), by + I(0.1), I(5.8), I(0.4), "днём — только ingest, 1 запрос/мин", 11, False, GREY, PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE)
    text(s, I(0.6), I(6.45), I(12.2), I(0.4), "ASR — только для звонков без метаданных · кэш классификации по хешу текста", 11, False, GREY)

    # 6 — agent & tools (native) ------------------------------------------------
    s = base(prs, "10 инструментов, 4 исхода, не более 8 вызовов", 6, "Агент и инструменты")
    text(s, I(0.6), I(1.45), I(3.4), I(0.4), "6 ИНСТРУМЕНТОВ ЧТЕНИЯ", 11, True, TEAL)
    reads = ["статистика кластера", "примеры E1..E8 без ПДн", "поиск обращений", "поиск в бэклоге", "владелец продукта", "история решений"]
    for i, r in enumerate(reads):
        y = I(1.95 + 0.72 * i)
        label(s, I(0.6), y, I(3.2), I(0.55), r, TEAL_TINT, NAVY, 12)
        arrow(s, I(3.8), y + I(0.27), I(4.7), I(3.65), TEAL, 1.25)
    label(s, I(4.7), I(2.55), I(3.3), I(2.2), "Агент\nQwen 3.8", NAVY, WHITE, 20, True)
    numcircle(s, I(7.55), I(2.3), "≤ 8", d=I(0.75), fill=ORANGE, size=14)
    text(s, I(4.7), I(4.8), I(3.3), I(0.5), "≤ 8 вызовов на кластер", 11, False, GREY, PP_ALIGN.CENTER)
    arrow(s, I(8.0), I(3.65), I(8.7), I(3.65), ORANGE, 2)
    label(s, I(8.7), I(1.95), I(1.1), I(3.95), "Policy\nGate", ORANGE, WHITE, 14, True)
    text(s, I(8.6), I(1.45), I(4.3), I(0.4), "4 ИНСТРУМЕНТА ЗАПИСИ", 11, True, ORANGE)
    writes = ["дайджест команде", "комментарий к задаче", "эксперту", "пометить «не сообщать»"]
    for i, wname in enumerate(writes):
        y = I(2.1 + 0.95 * i)
        arrow(s, I(9.8), I(3.65), I(10.5), y + I(0.3), ORANGE, 1.25)
        label(s, I(10.5), y, I(2.4), I(0.6), wname, ORANGE_TINT, NAVY, 12)
    for i, t in enumerate(["не создаёт задачи", "не меняет приоритеты", "≥ 5 ссылок из 8 примеров", "числа — только из статистики"]):
        label(s, I(0.6 + 3.1 * i), I(6.3), I(2.95), I(0.5), t, WHITE, GREY, 11, line=ICE)

    # 7 — prompt & safety -------------------------------------------------------
    s = base(prs, "Промпт задаёт поведение, код гарантирует безопасность", 7, "Промпт и защита")
    blocks = ["РОЛЬ", "ЦЕЛЬ", "ВХОД", "ИНСТРУМЕНТЫ", "ПРАВИЛА", "ФОРМАТ", "ПРИМЕР"]
    for i, b in enumerate(blocks):
        label(s, I(0.6 + 1.76 * i), I(1.6), I(1.6), I(0.75), b, NAVY if b == "ПРАВИЛА" else LIGHT, WHITE if b == "ПРАВИЛА" else NAVY, 12, True)
        if i < 6:
            arrow(s, I(2.2 + 1.76 * i), I(1.975), I(2.36 + 1.76 * i), I(1.975), LINE, 1.25)
    text(s, I(0.6), I(2.45), I(12.2), I(0.4), "7 блоков промпта · 4 явных исхода, включая «не сообщать»", 12, False, GREY)
    guards = [("123", "Числа", "только из статистики\nPolicyGate сверяет каждое"),
              ("E1…E8", "Ссылки", "примеры вместо ID\n≥ 5 из своего кластера"),
              ("•••", "ПДн", "маска до модели\nпроверка на выходе"),
              ("</>", "Prompt injection", "текст обращения — данные\nканал только из справочника")]
    for i, (glyph, h, t) in enumerate(guards):
        x = I(0.6 + 3.1 * i)
        box(s, x, I(3.15), I(2.95), I(3.1), TEAL_TINT)
        text(s, x + I(0.2), I(3.3), I(2.6), I(0.9), glyph, 30, True, TEAL)
        text(s, x + I(0.2), I(4.3), I(2.6), I(0.5), h, 18, True, NAVY)
        text(s, x + I(0.2), I(4.85), I(2.6), I(1.3), t, 13, False, NAVY)
    text(s, I(0.6), I(6.4), I(12.2), I(0.4), "Пароль или SMS-код агент не предлагает никогда (примеры кейса №6–7)", 12, True, ORANGE)

    # 8 — testing ---------------------------------------------------------------
    s = base(prs, "Приёмка: офлайн → shadow → пилот → масштаб", 8, "Тестирование")
    stages = [("Офлайн", "golden set ≈ 800\nF1 ≥ 0,85 · темы ≥ 80%"), ("Shadow", "4 недели\n≥ 70% «полезно»"),
              ("Пилот", "2–3 продукта\nпринято ≥ 50%"), ("Масштаб", "все продукты\n< 40% три недели → пересмотр")]
    for i, (h, t) in enumerate(stages):
        x = I(0.5 + 3.1 * i)
        label(s, x, I(1.55), I(3.0), I(0.9), h, NAVY if i < 2 else TEAL, WHITE, 18, True, shape=MSO_SHAPE.CHEVRON)
        text(s, x + I(0.3), I(2.55), I(2.6), I(1.0), t, 13, False, NAVY, PP_ALIGN.CENTER)
    text(s, I(0.6), I(3.75), I(12.2), I(0.4), "HOLDOUT: 204 НОВЫХ ОБРАЩЕНИЯ · QWEN3:8B ЛОКАЛЬНО", 11, True, TEAL)
    res = [("0,96", "macro-F1\nклассификации"), ("0,92", "recall сервисных\nзапросов"), ("100 %", "чисел совпали\nсо статистикой"),
           ("0", "утечек ПДн ·\nдублей"), ("0,86", "найдено тем\n(BM25: 0,14)")]
    for i, (big, lab) in enumerate(res):
        stat(s, I(0.6 + 2.47 * i), I(4.2), I(2.3), big, lab, TEAL if i < 4 else ORANGE, h=I(1.75), big_size=34)
    text(s, I(0.6), I(6.2), I(12.2), I(0.5), "Релиз — нижняя граница Уилсона доли принятых ≥ 0,5 на ≈ 250 оценках", 12, False, GREY)

    # 9 — metrics ---------------------------------------------------------------
    s = base(prs, "Главное — сколько обращений не случилось", 9, "Эффект внедрения")
    m = [("M1", "Предотвращённые\nобращения", TEAL), ("M2", "Часы ручного\nсбора", TEAL),
         ("M3", "Опережение\nбэклога", NAVY), ("M4", "Доля принятых\nэлементов", NAVY)]
    for i, (k, h, c) in enumerate(m):
        x, y = I(0.6 + 3.25 * (i % 2)), I(1.6 + 1.65 * (i // 2))
        box(s, x, y, I(3.1), I(1.5))
        text(s, x + I(0.1), y + I(0.15), I(0.95), I(1.2), k, 28, True, c, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + I(1.0), y + I(0.15), I(2.05), I(1.2), h, 13, True, NAVY, anchor=MSO_ANCHOR.MIDDLE, margin=I(0.03))
    text(s, I(0.6), I(5.0), I(6.2), I(0.4), "Как считаем M1", 14, True, NAVY)
    for i, t in enumerate(["ретроспектива за год до запуска", "пилотные продукты против контрольных", "SLA не хуже · 0 инцидентов ПДн"]):
        numcircle(s, I(0.6), I(5.45 + 0.45 * i), i + 1, d=I(0.34), fill=TEAL, size=11)
        text(s, I(1.05), I(5.4 + 0.45 * i), I(5.6), I(0.4), t, 13, False, NAVY)
    picture_fit(s, CHARTS / "did_schema.png", I(7.0), I(1.55), I(5.9), I(4.6))
    text(s, I(7.0), I(6.2), I(5.9), I(0.5), "Схема оценки: difference-in-differences", 11, False, GREY, PP_ALIGN.CENTER)

    # 10 — finance --------------------------------------------------------------
    s = base(prs, f"Эффект ≈ {base_row['total'] / 1e6:.1f} млн ₽/год окупает до {base_row['max_capex'] / 1e6:.1f} млн ₽ за 3 года".replace(".", ","), 10, "Финансовая модель")
    picture_fit(s, CHARTS / "scenarios.png", I(0.4), I(1.5), I(6.2), I(4.1))
    picture_fit(s, CHARTS / "tornado.png", I(6.7), I(1.5), I(6.3), I(4.1))
    b1 = f"{base_row['max_capex_b1_only'] / 1e6:.1f}".replace(".", ",")
    chips = [("B1", "предотвращённые обращения\n× AHT × стоимость часа", TEAL_TINT, TEAL),
             ("B2", "часы ручного сбора\n× 40 менеджеров × 48 нед.", ORANGE_TINT, ORANGE),
             (f"{b1} млн ₽", "потолок только по B1 —\nминимальный бюджет пилота", LIGHT, NAVY)]
    for i, (big, lab, fill, c) in enumerate(chips):
        x = I(0.6 + 4.15 * i)
        box(s, x, I(5.75), I(3.9), I(1.05), fill)
        text(s, x + I(0.15), I(5.75), I(1.65), I(1.05), big, 18, True, c, anchor=MSO_ANCHOR.MIDDLE, margin=I(0.03))
        text(s, x + I(1.8), I(5.75), I(2.05), I(1.05), lab, 10.5, False, NAVY, anchor=MSO_ANCHOR.MIDDLE, margin=I(0.03))

    out = DIST / "Презентация.pptx"
    prs.save(out)
    assert len(prs.slides) == TOTAL
    return out


def to_pdf(pptx: Path) -> Path:
    pdf = pptx.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    subprocess.run(["open", "-a", "Keynote"], check=True)
    script = f'''
    tell application "Keynote"
      set d to open POSIX file "{pptx}"
      export d to POSIX file "{pdf}" as PDF
      close d saving no
    end tell'''
    subprocess.run(["osascript", "-e", script], check=True)
    return pdf


if __name__ == "__main__":
    p = build()
    print("slides:", p)
    if "--pdf" in sys.argv:
        print("PDF:", to_pdf(p))
