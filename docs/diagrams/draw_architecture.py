#!/usr/bin/env python3
"""Architecture figure (01-architecture.png/.svg), drawn on a fixed grid with matplotlib.

Mermaid/dagre lays this compound graph out as a 1:2.4 vertical strip, unreadable at page width,
so the one figure that both the document and the deck lean on is drawn by hand: 16:9, navy = deterministic
code, teal = Qwen models, orange = policy/decisions, white = people, grey = data stores.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parent / "rendered"
NAVY, TEAL, ORANGE, GREY, INK = "#10314C", "#00918F", "#F56A2B", "#5A6775", "#10314C"
F = {"det": ("#E6EEF5", NAVY), "ai": ("#DDF3F2", TEAL), "gate": ("#FDEBE1", ORANGE),
     "human": ("#FFFFFF", "#8A98A8"), "src": ("#F2F5F8", GREY)}
FONT = ["Arial", "DejaVu Sans"]  # DejaVu covers ₽ and ①–⑤, which Arial lacks
W, H = 16.0, 9.0


def box(ax, x, y, w, h, kind, title, body="", r=0.18, fs=8.2):
    fill, edge = F[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fill, ec=edge, lw=1.3))
    cy = y + h / 2
    if body:
        ax.text(x + w / 2, cy + 0.16, title, ha="center", va="bottom", fontsize=fs + 1, fontweight="bold", color=INK, family=FONT)
        ax.text(x + w / 2, cy + 0.08, body, ha="center", va="top", fontsize=fs - 0.6, color=INK, family=FONT, linespacing=1.25)
    else:
        ax.text(x + w / 2, cy, title, ha="center", va="center", fontsize=fs + 0.6, fontweight="bold", color=INK, family=FONT, linespacing=1.25)


def cylinder(ax, x, y, w, h, title, body=""):
    fill, edge = F["src"]
    ry = 0.14
    ax.add_patch(Rectangle((x, y + ry), w, h - 2 * ry, fc=fill, ec="none"))
    ax.plot([x, x], [y + ry, y + h - ry], color=edge, lw=1.3)
    ax.plot([x + w, x + w], [y + ry, y + h - ry], color=edge, lw=1.3)
    ax.add_patch(Ellipse((x + w / 2, y + ry), w, 2 * ry, fc=fill, ec=edge, lw=1.3))
    ax.add_patch(Ellipse((x + w / 2, y + h - ry), w, 2 * ry, fc=fill, ec=edge, lw=1.3))
    ax.text(x + w / 2, y + h / 2 + (0.14 if body else 0), title, ha="center", va="center" if not body else "bottom",
            fontsize=8.8, fontweight="bold", color=INK, family=FONT, linespacing=1.2)
    if body:
        ax.text(x + w / 2, y + h / 2 + 0.06, body, ha="center", va="top", fontsize=7.6, color=INK, family=FONT, linespacing=1.25)


def hexagon(ax, cx, cy, w, h, title, body):
    fill, edge = F["gate"]
    d = h / 2
    pts = [(cx - w / 2 + d * 0.55, cy - d), (cx + w / 2 - d * 0.55, cy - d), (cx + w / 2, cy),
           (cx + w / 2 - d * 0.55, cy + d), (cx - w / 2 + d * 0.55, cy + d), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, fc=fill, ec=edge, lw=1.3))
    ax.text(cx, cy + 0.14, title, ha="center", va="bottom", fontsize=9.2, fontweight="bold", color="#5A2A10", family=FONT)
    ax.text(cx, cy + 0.06, body, ha="center", va="top", fontsize=7.6, color="#5A2A10", family=FONT, linespacing=1.25)


def frame(ax, x, y, w, h, title, edge, dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.22", fc="#FBFCFD", ec=edge,
                                lw=1.1, ls=(0, (4, 3)) if dashed else "-"))
    ax.text(x + 0.22, y + h - 0.1, title, ha="left", va="top", fontsize=8.6, fontweight="bold", color=edge, family=FONT)


def arrow(ax, p, q, label="", style="-", conn="arc3,rad=0", lab_off=(0, 0.16), color=GREY, fs=7.4):
    ax.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2, ls=style,
                                                    connectionstyle=conn, shrinkA=2, shrinkB=2, mutation_scale=11))
    if label:
        mx, my = (p[0] + q[0]) / 2 + lab_off[0], (p[1] + q[1]) / 2 + lab_off[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs, color=INK, family=FONT,
                bbox=dict(fc="white", ec="none", pad=1.2), linespacing=1.15)


def draw(path_png: Path, path_svg: Path | None = None) -> None:
    fig, ax = plt.subplots(figsize=(W, H), dpi=100)
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)

    # corporate contour
    frame(ax, 3.1, 0.35, 10.3, 8.3, "Корпоративный контур · внешние LLM и API не используются", "#B8C4D0", dashed=True)
    # processes
    frame(ax, 3.4, 5.1, 2.5, 3.1, "Процесс 1 · ingest-worker", NAVY)
    frame(ax, 6.25, 1.0, 2.85, 7.2, "Процесс 2 · model-workers (GPU)", TEAL)
    frame(ax, 10.3, 0.65, 2.85, 7.55, "Процесс 3 · приложение", NAVY)

    # left column: source, support, dashboard
    cylinder(ax, 0.35, 5.55, 2.3, 2.45, "Система обработки\nобращений", "тикеты · записи звонков\n· вложения\nхранение 1 год")
    box(ax, 0.35, 2.75, 2.3, 1.1, "human", "Поддержка", "решает по действующему SLA,\nкак сейчас")
    box(ax, 0.35, 0.9, 2.3, 0.9, "human", "Дашборд метрик M1–M4", "")

    # process 1
    box(ax, 3.6, 5.5, 2.1, 2.15, "det", "① Ingest", "read-only · курсор\nпо updated_at\nдедупликация\nмаскирование ПДн\nproduct_id")
    # process 2
    box(ax, 6.5, 5.5, 2.35, 1.95, "ai", "② Media", "Qwen-ASR — звонки\nQwen-VL — изображения")
    box(ax, 6.5, 2.4, 2.35, 2.0, "ai", "③ Enrich", "Qwen 3.8 → JSON:\nтип · функция · суть\n+ эмбеддинг bge-m3")
    # process 3
    box(ax, 10.55, 5.85, 2.35, 1.95, "det", "④ Cluster", "кластеризация по продукту\nсчётчики · тренды\nправило всплеска")
    box(ax, 10.55, 3.55, 2.35, 1.75, "ai", "⑤ Agent-digest", "Qwen 3.8 + 10 инструментов\n≤ 8 вызовов на кластер")
    hexagon(ax, 11.725, 2.3, 2.5, 1.35, "PolicyGate", "≥ 5 ссылок · числа из статистики\nнет ПДн · канал из allowlist")
    box(ax, 10.55, 0.85, 2.35, 0.85, "det", "Outbox · идемпотентная доставка")
    # data stores
    cylinder(ax, 3.55, 1.0, 2.2, 2.0, "PostgreSQL\n+ pgvector", "сигналы · кластеры\nаудит · обратная связь")
    cylinder(ax, 6.5, 0.55, 2.35, 1.2, "Справочник и бэклог", "продукт → команда · трекер")

    # recipients
    box(ax, 13.75, 6.3, 2.0, 1.1, "human", "Старший смены", "ранний сигнал о всплеске\nв течение часа")
    box(ax, 13.75, 3.4, 2.0, 1.2, "human", "Продуктовые\nкоманды", "")

    def poly(points, label="", lab_at=None, style="-", fs=7.2):
        xs, ys = zip(*points)
        ax.plot(xs[:-1], ys[:-1], color=GREY, lw=1.2, ls=style, solid_capstyle="round")
        arrow(ax, points[-2], points[-1], style=style)
        if label:
            ax.text(*lab_at, label, ha="center", va="center", fontsize=fs, color=INK, family=FONT,
                    bbox=dict(fc="white", ec="none", pad=1.2), linespacing=1.15)

    # flows
    arrow(ax, (1.5, 5.5), (1.5, 3.9), "сразу,\nкак сейчас", lab_off=(0.0, 0.0))
    arrow(ax, (2.65, 6.6), (3.6, 6.6), "read-only\nкаждые\n15–60 мин", lab_off=(0, 0.55))
    arrow(ax, (5.7, 6.9), (6.5, 6.9), "аудио /\nизображения", lab_off=(0, 0.38))
    poly([(5.3, 5.5), (5.3, 4.1), (6.5, 4.1)], "текст без ПДн", (5.75, 4.5))
    arrow(ax, (7.675, 5.5), (7.675, 4.4), "расшифровка /\nописание", lab_off=(0.0, 0.0), fs=7.0)
    arrow(ax, (6.5, 2.75), (5.75, 2.75), "JSON + вектор", lab_off=(0.0, 0.2), fs=7.0)
    poly([(3.55, 2.0), (3.25, 2.0), (3.25, 8.45), (11.725, 8.45), (11.725, 7.8)],
         "чтение сигналов микропакетами · полный пересчёт раз в неделю", (9.4, 8.45))
    arrow(ax, (11.725, 5.85), (11.725, 5.3), "кластеры ≥ 5 обращений,\nраз в неделю", lab_off=(0.0, 0.0), fs=7.0)
    arrow(ax, (11.725, 3.55), (11.725, 2.98), "черновик", lab_off=(0.0, 0.0), fs=7.0)
    arrow(ax, (11.725, 1.625), (11.725, 1.7))
    arrow(ax, (12.4, 2.98), (12.4, 3.55), "нарушение:\nисправить или\nэксперту", style="--", lab_off=(0.75, 0.0), fs=6.8)
    poly([(10.55, 4.0), (9.7, 4.0), (9.7, 1.15), (8.85, 1.15)], "чтение", (9.7, 2.6))
    arrow(ax, (12.9, 6.9), (13.75, 6.9), "≥ 5 за час\nи ≥ 3× фона", lab_off=(0, 0.42), fs=7.0)
    poly([(12.9, 1.5), (13.55, 1.5), (13.55, 4.0), (13.75, 4.0)], "дайджест", (13.55, 2.75))
    poly([(15.75, 4.0), (15.9, 4.0), (15.9, 0.15), (4.65, 0.15), (4.65, 1.0)],
         "accepted / rejected / needs_info", (10.2, 0.15), style="--")
    arrow(ax, (3.55, 1.35), (2.65, 1.35), "метрики", lab_off=(0.0, 0.2), fs=7.0)

    # legend (right column, bottom)
    for i, (k, lab) in enumerate([("det", "детерминированный код"), ("ai", "модели Qwen"), ("gate", "политика и решения"),
                                  ("human", "люди"), ("src", "данные")]):
        x, y = 13.9, 2.2 - i * 0.3
        ax.add_patch(FancyBboxPatch((x, y), 0.3, 0.2, boxstyle="round,pad=0,rounding_size=0.04", fc=F[k][0], ec=F[k][1], lw=1))
        ax.text(x + 0.4, y + 0.1, lab, ha="left", va="center", fontsize=7.2, color=GREY, family=FONT)

    OUT.mkdir(exist_ok=True)
    fig.savefig(path_png, dpi=200, facecolor="white")
    if path_svg:
        fig.savefig(path_svg, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    draw(OUT / "01-architecture.png", OUT / "01-architecture.svg")
    print(OUT / "01-architecture.png")
