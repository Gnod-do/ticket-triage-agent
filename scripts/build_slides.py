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
from fbagent.finance import scenarios, tornado  # noqa: E402

DIAG = ROOT / "docs" / "diagrams" / "rendered"
DIST = ROOT / "dist"
CHARTS = DIST / "charts"
NAVY, TEAL, ORANGE = RGBColor(0x10, 0x31, 0x4C), RGBColor(0x00, 0x91, 0x8F), RGBColor(0xF5, 0x6A, 0x2B)
GREY, LIGHT, WHITE = RGBColor(0x5A, 0x67, 0x75), RGBColor(0xF2, 0xF5, 0xF8), RGBColor(0xFF, 0xFF, 0xFF)
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


def base(prs, title, n, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.18), H)
    bar.fill.solid(); bar.fill.fore_color.rgb = TEAL; bar.line.fill.background()
    if kicker:
        text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.4), kicker.upper(), 11, True, TEAL)
    text(s, Inches(0.6), Inches(0.62), Inches(12.2), Inches(0.9), title, 28, True, NAVY)
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
    text(slide, x + Inches(0.2), y + Inches(0.15), w - Inches(0.4), Inches(0.8), big, 34, True, color)
    text(slide, x + Inches(0.2), y + Inches(0.95), w - Inches(0.4), Inches(0.7), label, 12, False, GREY)


def chart_scenarios(rows, path):
    names = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    xs = [names[r["name"]] for r in rows]
    vals = [r["max_capex"] / 1e6 for r in rows]
    eff = [r["total"] / 1e6 for r in rows]
    bars = ax.bar(xs, vals, color=["#c4d3df", "#00918f", "#10314c"], width=0.55)
    for b, v, e in zip(bars, vals, eff):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.1f} млн ₽".replace(".", ","), ha="center", fontsize=12,
                fontweight="bold", color="#10314c")
        ax.text(b.get_x() + b.get_width() / 2, v / 2, f"эффект\n{e:.1f} млн ₽/год".replace(".", ","), ha="center",
                va="center", fontsize=8.5, color="white") if v > 5 else None
    ax.set_ylabel("Допустимые инвестиции, млн ₽")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, max(vals) * 1.18)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def build() -> Path:
    CHARTS.mkdir(parents=True, exist_ok=True)
    rows = scenarios(ROOT / "demo" / "finance" / "assumptions.yaml")
    base_row = next(r for r in rows if r["name"] == "base")
    chart_scenarios(rows, CHARTS / "scenarios.png")
    tornado(base_row["params"], CHARTS / "tornado.png", figsize=(6.4, 3.9), fontsize=9)

    prs = Presentation(); prs.slide_width, prs.slide_height = W, H

    # 1 — title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H); bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    acc = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.3), Inches(1.2), Inches(0.08))
    acc.fill.solid(); acc.fill.fore_color.rgb = ORANGE; acc.line.fill.background()
    text(s, Inches(0.8), Inches(2.6), Inches(11.5), Inches(1.9), "ИИ-агент, который слышит\nповторяющиеся просьбы пользователей", 38, True, WHITE)
    text(s, Inches(0.8), Inches(4.75), Inches(11.5), Inches(0.9),
         "Из техподдержки — в продуктовые команды: проверенные сигналы без дополнительной нагрузки на поддержку", 18, False, RGBColor(0xC9, 0xD6, 0xE2))
    text(s, Inches(0.8), Inches(6.5), Inches(11), Inches(0.4), "Intelligence Cup 2026 · кейс «Газпром нефти» · Искусственный интеллект", 12, False, RGBColor(0x9F, 0xB3, 0xC6))

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
        box(s, Inches(0.6 + 4.1 * i), Inches(4.25), Inches(3.9), Inches(1.5), WHITE, TEAL)
        text(s, Inches(0.8 + 4.1 * i), Inches(4.4), Inches(3.5), Inches(1.3), q, 14, False, NAVY, anchor=MSO_ANCHOR.MIDDLE)
    text(s, Inches(0.6), Inches(6.05), Inches(12.2), Inches(0.8),
         "Критичное уже уходит в разработку. Теряются некритичные повторы — пожелания и неудобства, по одному у каждого менеджера.", 14, False, GREY)

    # 3 — process
    s = base(prs, "Агент работает рядом с поддержкой, а не вместо неё", 3, "Бизнес-процесс")
    picture_fit(s, DIAG / "02-business-process.png", Inches(0.5), Inches(1.5), Inches(8.6), Inches(5.4))
    for i, (h, t) in enumerate([("SLA не меняется", "Срочное (смена телефона перед отгрузкой) решается как сейчас"),
                                ("Два ритма", "Всплеск за час → старшему смены\nТема ≥ 5 обращений → дайджест раз в неделю"),
                                ("Решает человек", "Задачу в бэклоге создаёт команда кнопкой «принять»")]):
        box(s, Inches(9.35), Inches(1.6 + 1.75 * i), Inches(3.5), Inches(1.6))
        text(s, Inches(9.5), Inches(1.7 + 1.75 * i), Inches(3.2), Inches(0.4), h, 15, True, TEAL)
        text(s, Inches(9.5), Inches(2.1 + 1.75 * i), Inches(3.2), Inches(1.1), t, 12, False, NAVY)

    # 4 — architecture
    s = base(prs, "5 логических сервисов — 3 процесса — 1 база данных", 4, "Архитектура")
    picture_fit(s, DIAG / "01b-architecture-slide.png", Inches(0.4), Inches(1.5), Inches(12.5), Inches(2.4))
    items = [("Только внутренний контур", "Qwen 3.8, Qwen-ASR, Qwen-VL; внешних API нет"),
             ("Делим по ресурсам и правам", "ingest — read-only к источнику · model-workers — GPU · приложение — единственное с правом записи"),
             ("LLM — только для смысла", "классификация и текст дайджеста; числа, группировка, проверки — код"),
             ("Не добавляем лишнего", "без Kafka и отдельной векторной БД: PostgreSQL + pgvector"),
             ("Свой product_id у обращения", "группировка и маршрутизация отдельно по каждому продукту"),
             ("Отказоустойчивость", "Qwen недоступен → повтор в следующем окне; outbox исключает дубли")]
    for i, (h, t) in enumerate(items):
        x, y = Inches(0.6 + 4.15 * (i % 3)), Inches(4.15 + 1.35 * (i // 3))
        box(s, x, y, Inches(3.95), Inches(1.2))
        text(s, x + Inches(0.15), y + Inches(0.1), Inches(3.65), Inches(0.4), h, 14, True, TEAL)
        text(s, x + Inches(0.15), y + Inches(0.48), Inches(3.65), Inches(0.7), t, 11, False, NAVY)

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
    box(s, Inches(8.7), Inches(1.5), Inches(4.15), Inches(2.55))
    text(s, Inches(8.9), Inches(1.6), Inches(3.8), Inches(0.4), "Чтение — 6", 16, True, TEAL)
    text(s, Inches(8.9), Inches(2.0), Inches(3.8), Inches(2.0),
         "статистика кластера · примеры E1..E5 · поиск обращений · поиск в бэклоге · владелец продукта · история решений", 12, False, NAVY)
    box(s, Inches(8.7), Inches(4.2), Inches(4.15), Inches(2.6), WHITE, ORANGE)
    text(s, Inches(8.9), Inches(4.3), Inches(3.8), Inches(0.4), "Запись — 4, через PolicyGate", 16, True, ORANGE)
    text(s, Inches(8.9), Inches(4.7), Inches(3.8), Inches(2.0),
         "дайджест · комментарий к задаче · эксперту · пометить кластер\nЗадачи не создаёт и приоритеты не меняет", 12, False, NAVY)

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
              ("Ссылки", "модель видит E1..E5, а не ID тикетов; ≥ 5 ссылок из своего кластера"),
              ("ПДн", "телефоны, e-mail, ИНН, карты маскируются до модели и проверяются на выходе"),
              ("Prompt injection", "текст обращения — данные; канал доставки только из справочника")]
    for i, (h, t) in enumerate(guards):
        x = Inches(0.6 + 3.08 * i)
        box(s, x, Inches(3.2), Inches(2.9), Inches(2.4), WHITE, TEAL)
        text(s, x + Inches(0.15), Inches(3.3), Inches(2.6), Inches(0.5), h, 18, True, TEAL)
        text(s, x + Inches(0.15), Inches(3.85), Inches(2.6), Inches(1.7), t, 13, False, NAVY)
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
             ("Нужен ли Qwen", "прототип: найдено тем 0,93 у гибрида против 0,07 у BM25 без LLM"),
             ("Релиз", "нижняя граница Уилсона доли принятых ≥ 0,5 на ≈ 250 оценках")]
    for i, (h, t) in enumerate(rows8):
        y = Inches(3.05 + 0.62 * i)
        text(s, Inches(0.6), y, Inches(2.6), Inches(0.5), h, 15, True, TEAL)
        text(s, Inches(3.2), y, Inches(9.6), Inches(0.5), t, 15, False, NAVY)
    text(s, Inches(0.6), Inches(6.85) - Inches(0.25), Inches(12), Inches(0.3),
         "Прототип, 369 обращений, qwen3:8b локально: F1 0,93 · числа 100% · ПДн 0 · дубли 0 · injection заблокирован · всплеск найден", 11, True, TEAL)

    # 9 — metrics
    s = base(prs, "Главное — сколько обращений не случилось", 9, "Эффект внедрения")
    m = [("M1", "Предотвращённые повторные обращения", "темы исправлены раньше × поток обращений", TEAL),
         ("M2", "Высвобожденные часы ручного сбора", "40 менеджеров × часы до и после", TEAL),
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
         "Бюджет ~10 млн ₽ допускает только компактную архитектуру — поэтому 3 процесса, 1 БД и внутренние модели.", 12, False, NAVY)

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
