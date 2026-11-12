"""Benefit-side financial model (spec §6): maximum investment that still pays back within 3 years."""
from __future__ import annotations

from pathlib import Path

import yaml

WEEKS_PER_YEAR_WORKED = 48

PARAM_LABELS = {
    "h_week": "Часы ручной аналитики / нед. на менеджера",
    "hour_cost_rub": "Стоимость часа, ₽",
    "aht_min": "Время обработки обращения, мин",
    "clusters_per_year": "Тем в год",
    "accept_rate": "Доля принятых тем",
    "weekly_rate": "Обращений по теме в неделю",
    "lead_gain_weeks": "Опережение, недель",
    "extra_fixed_clusters": "Тем, которые без агента не исправили бы",
    "r": "Ставка дисконтирования",
    "g": "Рост стоимости часа",
}


def annual_benefit(p: dict) -> dict:
    avoided = (p["clusters_per_year"] * p["accept_rate"] * p["weekly_rate"] * p["lead_gain_weeks"]
               + p["extra_fixed_clusters"] * p["weekly_rate"] * p["remaining_weeks"])
    b1 = avoided * p["aht_min"] / 60 * p["hour_cost_rub"]
    b2 = p["managers"] * p["h_week"] * WEEKS_PER_YEAR_WORKED * p["hour_cost_rub"]
    return {"avoided_tickets": avoided, "b1": b1, "b2": b2, "total": b1 + b2}


def max_capex(p: dict, years: int = 3, component: str = "total") -> float:
    """Discounted benefit over the horizon = the most that still pays back within `years`.
    component="b1" gives the floor that does not depend on the unmeasured manual-aggregation hours (B2)."""
    b = annual_benefit(p)[component]
    return sum(b * (1 + p["g"]) ** (t - 1) / (1 + p["r"]) ** t for t in range(1, years + 1))


def deposit_alternative(capex: float, rate: float, years: int = 3) -> float:
    """Interest the same money would earn on a deposit over the horizon."""
    return capex * ((1 + rate) ** years - 1)


def scenarios(path: Path) -> list[dict]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = []
    for name, p in cfg["scenarios"].items():
        cap = max_capex(p)
        rows.append({"name": name, "params": p, **annual_benefit(p), "max_capex": cap,
                     "max_capex_b1_only": max_capex(p, component="b1"),
                     "deposit_interest_on_capex": deposit_alternative(cap, cfg["deposit_rate_for_comparison"])})
    return rows


# Chart palette (dataviz): series colours only on marks, text in ink/grey; teal ↔ orange validated as a
# CVD-safe pair (ΔE 12.6 protan, 29 normal); orange carries direct labels because its contrast is below 3:1.
INK, GREY, GRID, TEAL, ORANGE, NAVY_LIGHT = "#10314C", "#5A6775", "#E3E8EE", "#00918F", "#F56A2B", "#C9D6E2"
FONT = ["Arial", "DejaVu Sans"]  # DejaVu covers ₽ and ①–⑤, which Arial lacks


def _style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=GREY, labelsize=8, length=0)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_family(FONT)
    ax.set_axisbelow(True)


def _rounded_bar(ax, x, y, w, h, color, horizontal=True, radius=None):
    """Bar with the data end rounded and the baseline end square (dataviz mark spec)."""
    from matplotlib.patches import FancyBboxPatch, Rectangle
    if h == 0 or w == 0:
        return
    if horizontal:
        left, width = (x, w) if w > 0 else (x + w, -w)
        r = min(abs(h) / 2, radius or abs(h) / 2)
        ax.add_patch(FancyBboxPatch((left, y), width, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                    fc=color, ec="none", mutation_aspect=1))
        # square the baseline end
        if w > 0:
            ax.add_patch(Rectangle((left, y), min(r, width), h, fc=color, ec="none"))
        else:
            ax.add_patch(Rectangle((left + width - min(r, width), y), min(r, width), h, fc=color, ec="none"))
    else:
        bottom, height = (y, h) if h > 0 else (y + h, -h)
        r = min(abs(w) / 2, radius or abs(w) / 2)
        ax.add_patch(FancyBboxPatch((x, bottom), w, height, boxstyle=f"round,pad=0,rounding_size={r}",
                                    fc=color, ec="none", mutation_aspect=1))
        ax.add_patch(Rectangle((x, bottom), w, min(r, height), fc=color, ec="none"))


def _mln(x: float) -> str:
    return f"{x / 1e6:.1f}".replace(".", ",")


def tornado(base: dict, path_png: Path, swing: float = 0.3, figsize=(8, 4.5),
            fontsize: int = 8) -> list[tuple[str, float, float]]:
    """Vary each parameter ±swing around the base case; plot the resulting max_capex range as a tornado."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ref = max_capex(base)
    bars = []
    for k in PARAM_LABELS:
        lo = max_capex(dict(base, **{k: base[k] * (1 - swing)}))
        hi = max_capex(dict(base, **{k: base[k] * (1 + swing)}))
        bars.append((k, min(lo, hi), max(lo, hi)))
    bars.sort(key=lambda b: b[2] - b[1])
    fig, ax = plt.subplots(figsize=figsize)
    thick = 0.42
    for i, (k, lo, hi) in enumerate(bars):
        _rounded_bar(ax, 0, i - thick / 2, (hi - ref) / 1e6, thick, TEAL)
        _rounded_bar(ax, 0, i - thick / 2, (lo - ref) / 1e6, thick, ORANGE)
    # direct labels only on the three most influential parameters
    for i, (k, lo, hi) in list(enumerate(bars))[-3:]:
        ax.text((hi - ref) / 1e6 + 0.08, i, f"+{_mln(hi - ref)}", va="center", ha="left", fontsize=fontsize - 0.5,
                color=INK, family=FONT)
        ax.text((lo - ref) / 1e6 - 0.08, i, f"−{_mln(ref - lo)}", va="center", ha="right", fontsize=fontsize - 0.5,
                color=INK, family=FONT)
    span = max(abs((b[1] - ref) / 1e6) for b in bars + [(None, ref, ref)]) if bars else 1
    span = max(span, max(abs((b[2] - ref) / 1e6) for b in bars))
    ax.set_xlim(-span * 1.3, span * 1.3)
    ax.set_ylim(-0.6, len(bars) - 0.4)
    ax.set_yticks(range(len(bars)), [PARAM_LABELS[b[0]] for b in bars], fontsize=fontsize)
    ax.axvline(0, color=GREY, lw=0.9)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    _style(ax)
    ax.set_xlabel(f"Изменение допустимых инвестиций, млн ₽ (параметр ±{int(swing * 100)}%)", fontsize=fontsize, color=GREY,
                  family=FONT)
    fig.suptitle(f"Что сильнее всего влияет на допустимые инвестиции (база {_mln(ref)} млн ₽)", x=0.02, ha="left",
                 fontsize=fontsize + 2, fontweight="bold", color=INK, family=FONT)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(fc=TEAL, label=f"параметр +{int(swing * 100)}%"), Patch(fc=ORANGE, label=f"параметр −{int(swing * 100)}%")],
              loc="lower right", frameon=False, fontsize=fontsize - 0.5, handlelength=1.2, prop={"family": FONT, "size": fontsize - 0.5})
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    Path(path_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_png, dpi=200, facecolor="white")
    plt.close(fig)
    return bars[::-1]


def scenarios_chart(rows: list[dict], path_png: Path, figsize=(6.2, 4.0), fontsize: int = 8) -> None:
    """Allowable investment per scenario as a two-part column: the B1-only floor (teal) plus what B2 adds (orange).
    The split is the point: B2 rests on the manual-aggregation hours the case says are unknown."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    names = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
    fig, ax = plt.subplots(figsize=figsize)
    width, gap = 0.34, 0.03
    tops = []
    for i, r in enumerate(rows):
        b1 = r["max_capex_b1_only"] / 1e6
        total = r["max_capex"] / 1e6
        x = i - width / 2
        _rounded_bar(ax, x, 0, width, b1, TEAL, horizontal=False, radius=0.0)
        _rounded_bar(ax, x, b1 + gap, width, total - b1 - gap, ORANGE, horizontal=False)
        ax.text(i, total + 0.5, f"{_mln(r['max_capex'])} млн ₽", ha="center", va="bottom", fontsize=fontsize + 1,
                fontweight="bold", color=INK, family=FONT)
        ax.text(i, -1.1, f"эффект {_mln(r['total'])} млн ₽/год", ha="center", va="top", fontsize=fontsize - 0.5, color=GREY,
                family=FONT)
        if b1 > 0.5:
            ax.text(i + width / 2 + 0.05, b1 / 2, f"только B1\n{_mln(r['max_capex_b1_only'])} млн ₽", ha="left", va="center",
                    fontsize=fontsize - 0.5, color=INK, family=FONT, linespacing=1.2)
        tops.append(total)
    ax.set_xticks(range(len(rows)), [names.get(r["name"], r["name"]) for r in rows], fontsize=fontsize)
    ax.tick_params(axis="x", pad=22)
    ax.set_xlim(-0.6, len(rows) - 0.4)
    ax.set_ylim(0, max(tops) * 1.22)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    _style(ax)
    ax.set_ylabel("Допустимые инвестиции, млн ₽", fontsize=fontsize, color=GREY, family=FONT)
    fig.suptitle("Сколько можно вложить, чтобы окупиться за 3 года", x=0.02, ha="left", fontsize=fontsize + 2,
                 fontweight="bold", color=INK, family=FONT)
    ax.legend(handles=[Patch(fc=TEAL, label="B1 — предотвращённые обращения (измеримо)"),
                       Patch(fc=ORANGE, label="B2 — часы ручного сбора (пока допущение)")],
              loc="upper left", frameon=False, prop={"family": FONT, "size": fontsize - 0.5}, handlelength=1.2)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    Path(path_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_png, dpi=200, facecolor="white")
    plt.close(fig)


def write_report(rows: list[dict], path: Path) -> None:
    names = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
    m = lambda x: f"{x / 1e6:.2f}".replace(".", ",")  # noqa: E731
    lines = ["# Финансовая модель (только доходная часть)", "",
             "Все параметры, кроме числа менеджеров (40, PDF стр. 4), — допущения; см. demo/finance/assumptions.yaml.", "",
             "| Сценарий | Предотвращено обращений/год | B1, млн ₽/год | B2, млн ₽/год | Итого, млн ₽/год | "
             "Допустимые инвестиции (окупаемость ≤ 3 лет), млн ₽ | То же, только B1 (без часов ручного сбора), млн ₽ | "
             "Доход депозита на ту же сумму за 3 года, млн ₽ |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {names.get(r['name'], r['name'])} | {r['avoided_tickets']:.0f} | {m(r['b1'])} | {m(r['b2'])} "
                     f"| {m(r['total'])} | {m(r['max_capex'])} | {m(r['max_capex_b1_only'])} "
                     f"| {m(r['deposit_interest_on_capex'])} |")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
