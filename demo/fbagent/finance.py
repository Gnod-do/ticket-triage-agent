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


def max_capex(p: dict, years: int = 3) -> float:
    b = annual_benefit(p)["total"]
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
                     "deposit_interest_on_capex": deposit_alternative(cap, cfg["deposit_rate_for_comparison"])})
    return rows


def tornado(base: dict, path_png: Path, swing: float = 0.3) -> list[tuple[str, float, float]]:
    """Vary each parameter ±swing around the base case; plot the resulting max_capex range."""
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
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, (k, lo, hi) in enumerate(bars):
        ax.barh(i, (hi - ref) / 1e6, left=0, color="#2f7d6d")
        ax.barh(i, (lo - ref) / 1e6, left=0, color="#c4553a")
    ax.set_yticks(range(len(bars)), [PARAM_LABELS[b[0]] for b in bars], fontsize=8)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel(f"Изменение допустимых инвестиций, млн ₽ (база {ref / 1e6:.1f} млн ₽, параметры ±{int(swing * 100)}%)")
    ax.set_title("Чувствительность допустимых инвестиций (окупаемость ≤ 3 лет)")
    fig.tight_layout()
    Path(path_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_png, dpi=150)
    plt.close(fig)
    return bars[::-1]


def write_report(rows: list[dict], path: Path) -> None:
    names = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
    m = lambda x: f"{x / 1e6:.2f}".replace(".", ",")  # noqa: E731
    lines = ["# Финансовая модель (только доходная часть)", "",
             "Все параметры, кроме числа менеджеров (40, PDF стр. 4), — допущения; см. demo/finance/assumptions.yaml.", "",
             "| Сценарий | Предотвращено обращений/год | B1, млн ₽/год | B2, млн ₽/год | Итого, млн ₽/год | "
             "Допустимые инвестиции (окупаемость ≤ 3 лет), млн ₽ | Доход депозита на ту же сумму за 3 года, млн ₽ |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {names.get(r['name'], r['name'])} | {r['avoided_tickets']:.0f} | {m(r['b1'])} | {m(r['b2'])} "
                     f"| {m(r['total'])} | {m(r['max_capex'])} | {m(r['deposit_interest_on_capex'])} |")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
