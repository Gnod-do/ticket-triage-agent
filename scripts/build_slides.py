#!/usr/bin/env python3
"""Build the ~10-slide companion deck (16:9) from diagrams and the finance model.

  python scripts/build_slides.py [--pdf]  -> dist/Презентация.pptx (+ .pdf via PowerPoint/Keynote if --pdf)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from fbagent.finance import scenarios, scenarios_chart, tornado  # noqa: E402

DIAG = ROOT / "docs" / "diagrams" / "rendered"
DIST = ROOT / "dist"
CHARTS = DIST / "charts"
NAVY, TEAL, ORANGE = RGBColor(0x10, 0x31, 0x4C), RGBColor(0x00, 0x91, 0x8F), RGBColor(0xF5, 0x6A, 0x2B)
GREY, LIGHT, WHITE = RGBColor(0x5A, 0x67, 0x75), RGBColor(0xF2, 0xF5, 0xF8), RGBColor(0xFF, 0xFF, 0xFF)
TEAL_TINT, ORANGE_TINT, ICE = RGBColor(0xE4, 0xF3, 0xF2), RGBColor(0xFD, 0xEB, 0xE1), RGBColor(0xC9, 0xD6, 0xE2)
W, H = Inches(13.333), Inches(7.5)
TOTAL = 10


def text(slide, x, y, w, h, s, size=16, bold=False, color=NAVY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run(); r.text = line
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, "Arial"
    return tb


def box(slide, x, y, w, h, fill=LIGHT, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    s.adjustments[0] = 0.08
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line; s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def numcircle(slide, x, y, n, d=Inches(0.42), fill=NAVY, color=WHITE, size=13):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    c.fill.solid(); c.fill.fore_color.rgb = fill; c.line.fill.background(); c.shadow.inherit = False
    tf = c.text_frame; tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = str(n); r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), True, color, "Arial"
    return c


def card(slide, x, y, w, h, n, head, body, fill=LIGHT, accent=NAVY, head_size=14, body_size=11):
    """Card with a numbered circle: the deck's one repeating motif."""
    box(slide, x, y, w, h, fill)
    numcircle(slide, x + Inches(0.18), y + Inches(0.16), n, fill=accent)
    text(slide, x + Inches(0.72), y + Inches(0.12), w - Inches(0.85), Inches(0.5), head, head_size, True, accent)
    text(slide, x + Inches(0.72), y + Inches(0.55), w - Inches(0.85), h - Inches(0.6), body, body_size, False, NAVY)


def base(prs, title, n, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    if kicker:
        text(s, Inches(0.6), Inches(0.3), Inches(12), Inches(0.4), kicker.upper(), 11, True, TEAL)
    text(s, Inches(0.6), Inches(0.58), Inches(12.2), Inches(0.9), title, 28, True, NAVY)
    text(s, Inches(0.6), Inches(7.0), Inches(9), Inches(0.3), "Intelligence Cup 2026 · «Газпром нефть» · ИИ-агент «поддержка → продукт»", 9, False, GREY)
    text(s, Inches(12.2), Inches(7.0), Inches(0.8), Inches(0.3), f"{n} / {TOTAL}", 9, False, GREY, PP_ALIGN.RIGHT)
    return s


def picture_fit(slide, path, x, y, max_w, max_h):
    from PIL import Image
    w, h = Image.open(path).size
    scale = min(max_w / w, max_h / h)
    pw, ph = int(w * scale), int(h * scale)
    return slide.shapes.add_picture(str(path), x + (max_w - pw) // 2, y + (max_h - ph) // 2, pw, ph)


def stat(slide, x, y, w, big, label, color=TEAL):
    box(slide, x, y, w, Inches(1.7))
    text(slide, x + Inches(0.25), y + Inches(0.12), w - Inches(0.5), Inches(0.85), big, 36, True, color)
    text(slide, x + Inches(0.25), y + Inches(0.97), w - Inches(0.5), Inches(0.7), label, 12, False, GREY)


def build() -> Path:
    CHARTS.mkdir(parents=True, exist_ok=True)
    rows = scenarios(ROOT / "demo" / "finance" / "assumptions.yaml")
    base_row = next(r for r in rows if r["name"] == "base")
    scenarios_chart(rows, CHARTS / "scenarios.png")
    tornado(base_row["params"], CHARTS / "tornado.png", figsize=(6.4, 3.9), fontsize=9)

    prs = Presentation(); prs.slide_width, prs.slide_height = W, H

    # 1 — title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H); bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    text(s, Inches(0.8), Inches(0.6), Inches(11), Inches(0.4), "INTELLIGENCE CUP 2026 · КЕЙС «ГАЗПРОМ НЕФТИ»", 12, True, TEAL)
    text(s, Inches(0.8), Inches(1.9), Inches(11.5), Inches(1.9), "ИИ-агент, который слышит\nповторяющиеся просьбы пользователей", 40, True, WHITE)
    text(s, Inches(0.8), Inches(4.0), Inches(11.5), Inches(0.9),
         "Из техподдержки — в продуктовые команды: проверенные сигналы без дополнительной нагрузки на поддержку", 18, False, ICE)
    for i, (big, lab) in enumerate([("0", "внешних API — только внутренние Qwen"), ("≤ 8", "вызовов инструментов на кластер"),
                                    ("0,86", "найденных тем на holdout против 0,14 у BM25")]):
        x = Inches(0.8 + 4.0 * i)
        text(s, x, Inches(5.25), Inches(3.6), Inches(0.8), big, 32, True, TEAL)
        text(s, x, Inches(5.95), Inches(3.6), Inches(0.6), lab, 12, False, ICE)

    # 2 — problem
    s = base(prs, "Каждый видит 1–2 обращения. Сумму не видит никто", 2, "Проблема")
    stat(s, Inches(0.6), Inches(1.7), Inches(3.9), "≈ 40", "менеджеров поддержки на всех продуктах в охвате агента (кейс, стр. 4)")
    stat(s, Inches(4.7), Inches(1.7), Inches(3.9), "2 канала", "звонки с записью и единое окно с файлами и картинками; хранение 1 год")
    stat(s, Inches(8.8), Inches(1.7), Inches(3.9), "0 ч", "должно добавиться поддержке — главное требование кейса", ORANGE)
    text(s, Inches(0.6), Inches(3.75), Inches(12), Inches(0.4), "Так выглядит повтор в «Вебнефти» (примеры кейса, стр. 6):", 14, True, NAVY)
    quotes = ["«Не приходит код-смс для восстановления пароля»",
              "«В личном кабинете нельзя забронировать электронную очередь — ошибка 404»",
              "«Кнопка «Далее» горит синим, но ни в одном браузере не реагирует»"]
    for i, q in enumerate(quotes):
        box(s, Inches(0.6 + 4.1 * i), Inches(4.25), Inches(3.9), Inches(1.5), TEAL_TINT)
        text(s, Inches(0.8 + 4.1 * i), Inches(4.4), Inches(3.5), Inches(1.3), q, 14, False, NAVY, anchor=MSO_ANCHOR.MIDDLE)
    text(s, Inches(0.6), Inches(6.05), Inches(12.2), Inches(0.8),
         "Критичное уже уходит в разработку. Теряются некритичные повторы — пожелания и неудобства, по одному у каждого менеджера.", 14, False, GREY)

    # 3 — process
    s = base(prs, "Агент работает рядом с поддержкой, а не вместо неё", 3, "Бизнес-процесс")
    picture_fit(s, DIAG / "02-business-process.png", Inches(0.5), Inches(1.5), Inches(8.6), Inches(5.4))
    for i, (h, t) in enumerate([("SLA не меняется", "Срочное (смена телефона перед отгрузкой) решается как сейчас"),
                                ("Два ритма", "Всплеск за час → старшему смены\nТема ≥ 5 обращений → дайджест раз в неделю"),
                                ("Решает человек", "Задачу в бэклоге создаёт команда кнопкой «принять»")]):
        card(s, Inches(9.35), Inches(1.6 + 1.75 * i), Inches(3.5), Inches(1.6), i + 1, h, t, accent=TEAL)

    # 4 — architecture
    s = base(prs, "5 логических сервисов — 3 процесса — 1 база данных", 4, "Архитектура")
    picture_fit(s, DIAG / "01-architecture.png", Inches(0.4), Inches(1.45), Inches(9.0), Inches(5.5))
    items = [("Только внутренний контур", "Qwen 3.8, Qwen-ASR, Qwen-VL; внешних API нет. Каждое обращение несёт product_id"),
             ("Делим по ресурсам и правам", "ingest — read-only к источнику · model-workers — GPU · приложение — единственное с правом записи"),
             ("LLM — только для смысла", "классификация и текст дайджеста; числа, группировка и проверки — код"),
             ("Не добавляем лишнего", "без Kafka и отдельной векторной БД: PostgreSQL + pgvector; Qwen недоступен → повтор в следующем окне")]
    for i, (h, t) in enumerate(items):
        card(s, Inches(9.6), Inches(1.5 + 1.36 * i), Inches(3.3), Inches(1.25), i + 1, h, t, head_size=13, body_size=10.5)

    # 5 — load
    s = base(prs, "Нагрузка укладывается в ночное окно существующих GPU", 5, "Расчёт нагрузки")
    cards = [("≈ 1 400", "обращений в день\n40 менеджеров × 35"), ("≈ 0,9 млн", "токенов Qwen в день\n≈ 15 минут работы"),
             ("≈ 2,3", "GPU-часа ASR в день\n47 ч звонков, RTF 0,05"), ("≤ 240", "вызовов агента в неделю\nтолько кластеры ≥ 5"),
             ("≈ 1,4 ГБ", "эмбеддингов за год\n350 тыс. × 1024"), ("1 / мин", "запрос к системе обращений\nинкрементальная выгрузка")]
    for i, (big, lab) in enumerate(cards):
        stat(s, Inches(0.6 + 4.1 * (i % 3)), Inches(1.6 + 2.0 * (i // 3)), Inches(3.9), big, lab)
    text(s, Inches(0.6), Inches(5.75), Inches(12.2), Inches(1.1),
         "Как снижаем: ASR только для звонков, которые не классифицируются по метаданным · кэш классификации по хешу текста · "
         "агент запускается лишь для тем выше порога. Из кейса известно только число менеджеров — остальное допущения, проверяются на старте.",
         13, False, GREY)

    # 6 — agent & tools
    s = base(prs, "10 инструментов, 4 исхода, не более 8 вызовов", 6, "Агент и инструменты")
    picture_fit(s, DIAG / "03-agent-workflow.png", Inches(0.5), Inches(1.45), Inches(7.9), Inches(5.45))
    card(s, Inches(8.7), Inches(1.5), Inches(4.15), Inches(2.55), 6, "Инструментов чтения",
         "статистика кластера · примеры E1..E8 без ПДн · поиск обращений · поиск в бэклоге · владелец продукта · история решений команды",
         fill=TEAL_TINT, accent=TEAL, head_size=15, body_size=12)
    card(s, Inches(8.7), Inches(4.2), Inches(4.15), Inches(2.6), 4, "Инструмента записи",
         "через PolicyGate: дайджест · комментарий к задаче · эксперту · пометить кластер\nЗадачи не создаёт и приоритеты не меняет; ≥ 5 ссылок из 8 примеров",
         fill=ORANGE_TINT, accent=ORANGE, head_size=15, body_size=12)

    # 7 — prompt & safety
    s = base(prs, "Промпт задаёт поведение, код гарантирует безопасность", 7, "Промпт и защита")
    blocks = ["РОЛЬ", "ЦЕЛЬ", "ВХОД", "ИНСТРУМЕНТЫ", "ПРАВИЛА", "ФОРМАТ", "ПРИМЕР"]
    for i, b in enumerate(blocks):
        box(s, Inches(0.6 + 1.76 * i), Inches(1.6), Inches(1.6), Inches(0.75), NAVY if b == "ПРАВИЛА" else LIGHT)
        text(s, Inches(0.6 + 1.76 * i), Inches(1.6), Inches(1.6), Inches(0.75), b, 12, True,
             WHITE if b == "ПРАВИЛА" else NAVY, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    text(s, Inches(0.6), Inches(2.45), Inches(12.2), Inches(0.5),
         "7 блоков: узкая роль · 4 явных исхода, включая «не сообщать» · порядок вызовов · формат под продакт-менеджера · пример из кейса", 13, False, GREY)
    guards = [("Числа", "только из get_cluster_stats — PolicyGate сверяет каждое число"),
              ("Ссылки", "модель видит E1..E8, а не ID тикетов; выбирает ≥ 5 ссылок из своего кластера"),
              ("ПДн", "телефоны, e-mail, ИНН, карты маскируются до модели и проверяются на выходе"),
              ("Prompt injection", "текст обращения — данные; канал доставки только из справочника")]
    for i, (h, t) in enumerate(guards):
        x = Inches(0.6 + 3.08 * i)
        box(s, x, Inches(3.2), Inches(2.9), Inches(2.4), TEAL_TINT)
        text(s, x + Inches(0.2), Inches(3.3), Inches(2.5), Inches(0.5), h, 18, True, TEAL)
        text(s, x + Inches(0.2), Inches(3.85), Inches(2.5), Inches(1.7), t, 13, False, NAVY)
    text(s, Inches(0.6), Inches(5.85), Inches(12.2), Inches(1.0),
         "Из примеров кейса: №3 — одно обращение с двумя симптомами считается один раз · №1 и №2 — одна тема ≠ одна ошибка · "
         "№6–7 — агент никогда не предлагает выдать пароль или SMS-код", 13, False, GREY)

    # 8 — testing
    s = base(prs, "Приёмка: офлайн → shadow → пилот → масштаб", 8, "Тестирование")
    picture_fit(s, DIAG / "05-rollout.png", Inches(0.5), Inches(1.45), Inches(12.3), Inches(1.4))
    rows8 = [("Классификация", "macro-F1 ≥ 0,85 · сервисные запросы recall ≥ 0,90"),
             ("Кластеры", "чистота ≥ 0,90 · найдено ≥ 80% известных тем"),
             ("Агент", "числа = статистика 100% · дубли с бэклогом ≤ 10% · рубрика ≥ 4/5"),
             ("Безопасность", "0 утечек ПДн · 0 срабатываний prompt injection"),
             ("Нужен ли Qwen", "holdout: найдено тем 0,86 у гибрида против 0,14 у BM25 без LLM"),
             ("Релиз", "нижняя граница Уилсона доли принятых ≥ 0,5 на ≈ 250 оценках")]
    for i, (h, t) in enumerate(rows8):
        y = Inches(3.05 + 0.6 * i)
        numcircle(s, Inches(0.6), y + Inches(0.02), i + 1, d=Inches(0.36), fill=TEAL, size=12)
        text(s, Inches(1.1), y, Inches(2.3), Inches(0.5), h, 15, True, TEAL)
        text(s, Inches(3.5), y, Inches(9.3), Inches(0.5), t, 15, False, NAVY)
    text(s, Inches(0.6), Inches(6.85) - Inches(0.25), Inches(12), Inches(0.3),
         "Holdout 204 обращения, qwen3:8b локально: F1 0,96 · сервисные 0,92 · числа 100% · ПДн 0 · дубли с бэклогом и внутри дайджеста 0 · всплеск найден", 11, True, TEAL)

    # 9 — metrics
    s = base(prs, "Главное — сколько обращений не случилось", 9, "Эффект внедрения")
    m = [("M1", "Предотвращённые обращения", "темы исправлены раньше × поток обращений по теме", TEAL),
         ("M2", "Часы ручного сбора", "40 менеджеров × часы до и после внедрения", TEAL),
         ("M3", "Опережение бэклога", "порог в агенте → задача в бэклоге", NAVY),
         ("M4", "Доля принятых элементов", "accepted / все решения команды", NAVY)]
    for i, (k, h, t, c) in enumerate(m):
        x, y = Inches(0.6 + 6.2 * (i % 2)), Inches(1.6 + 1.75 * (i // 2))
        box(s, x, y, Inches(6.0), Inches(1.55))
        text(s, x + Inches(0.2), y + Inches(0.2), Inches(1.0), Inches(1.0), k, 32, True, c)
        text(s, x + Inches(1.3), y + Inches(0.2), Inches(4.5), Inches(0.5), h, 16, True, NAVY)
        text(s, x + Inches(1.3), y + Inches(0.75), Inches(4.5), Inches(0.6), t, 13, False, GREY)
    text(s, Inches(0.6), Inches(5.2), Inches(12.2), Inches(0.4), "Ретроспектива за год до запуска · рост по продуктам с контрольной группой (difference-in-differences)", 14, True, NAVY)
    text(s, Inches(0.6), Inches(5.7), Inches(12.2), Inches(1.2),
         "Ограничители: время поддержки на агента ≈ 0 · ложные сигналы · 0 инцидентов ПДн · SLA не хуже.\n"
         "Нет связи «тикет → задача»? — сопоставление по смыслу + ручная проверка; нет журнала выгрузок? — опрос × 0,7.", 13, False, GREY)

    # 10 — finance
    s = base(prs, f"Эффект ≈ {base_row['total'] / 1e6:.1f} млн ₽/год окупает до {base_row['max_capex'] / 1e6:.1f} млн ₽ за 3 года".replace(".", ","), 10, "Финансовая модель")
    picture_fit(s, CHARTS / "scenarios.png", Inches(0.4), Inches(1.5), Inches(6.2), Inches(3.8))
    picture_fit(s, CHARTS / "tornado.png", Inches(6.7), Inches(1.5), Inches(6.3), Inches(3.8))
    text(s, Inches(0.6), Inches(5.45), Inches(12.2), Inches(1.4),
         "B1 — предотвращённые обращения × AHT × стоимость часа · B2 — 40 менеджеров × часы ручного сбора × 48 нед.\n"
         "r = ключевая ставка (14% на 23.10.2026; прогноз ЦБ 12,5–13,5% в 2027) + 5 п.п. риска; g = 7% (рост зарплат, МЭР).\n"
         f"Без B2 (часы ручного сбора по условию кейса неизвестны) потолок только по B1 — {base_row['max_capex_b1_only'] / 1e6:.1f} млн ₽: минимальный бюджет пилота.\n"
         "Бюджет ~10 млн ₽ допускает только компактную архитектуру — поэтому 3 процесса, 1 БД и внутренние модели.", 11, False, NAVY)

    out = DIST / "Презентация.pptx"
    prs.save(out)
    assert len(prs.slides) == TOTAL
    return out


def to_pdf(pptx: Path) -> Path:
    pdf = pptx.with_suffix(".pdf")
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
