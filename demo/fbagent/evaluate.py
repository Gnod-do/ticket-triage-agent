"""Offline evaluation against the synthetic ground truth (spec §4.2) plus the BM25 comparison (R5)."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from sklearn.metrics import adjusted_rand_score, f1_score, recall_score

from .models import DigestItem, Enrichment, Ticket
from .pii import mask_pii

PURITY_MIN = 0.8
COVERAGE_MIN = 0.5


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - m, 4), round(c + m, 4)


def _members(assignment: dict[str, str]) -> dict[str, list[str]]:
    out = defaultdict(list)
    for tid, c in assignment.items():
        if c != "noise":
            out[c].append(tid)
    return out


def cluster_recall(tickets: list[Ticket], assignment: dict[str, str]) -> dict:
    gt = {t.ticket_id: t.gt_cluster for t in tickets}
    gt_sizes = Counter(g for g in gt.values() if g)
    found, purities = set(), []
    for c, ids in _members(assignment).items():
        top, n = Counter(gt.get(i) for i in ids).most_common(1)[0]
        purity = n / len(ids)
        purities.append(purity)
        if top and purity >= PURITY_MIN and n / gt_sizes[top] >= COVERAGE_MIN:
            found.add(top)
    return {"recall": round(len(found) / max(1, len(gt_sizes)), 4), "found": found,
            "n_gt": len(gt_sizes), "n_pred": len(purities),
            "purity_mean": round(sum(purities) / len(purities), 4) if purities else 0.0,
            "ari": round(adjusted_rand_score([gt[t.ticket_id] or "noise" for t in tickets],
                                             [assignment.get(t.ticket_id, "noise") for t in tickets]), 4)}


def type_scores(tickets: list[Ticket], enrichments: dict[str, Enrichment]) -> dict:
    y = [t.gt_type for t in tickets]
    p = [enrichments[t.ticket_id].type if t.ticket_id in enrichments else "other" for t in tickets]
    labels = sorted(set(y))
    return {"type_macro_f1": round(f1_score(y, p, labels=labels, average="macro", zero_division=0), 4),
            "service_request_recall": round(recall_score(y, p, labels=["service_request"], average="macro",
                                                         zero_division=0), 4) if "service_request" in y else None}


def lead_time_days(tickets: list[Ticket], assignment: dict[str, str], backlog: list[dict],
                   threshold: int = 5) -> dict[str, float | None]:
    """Days between the moment the matching predicted cluster first reached `threshold` tickets
    (counting only tickets already ingested by then) and the issue's actual creation in the backlog."""
    by_id = {t.ticket_id: t for t in tickets}
    members = _members(assignment)
    out = {}
    for issue in backlog:
        g = issue.get("gt_cluster")
        best = max(members.items(), key=lambda kv: sum(by_id[i].gt_cluster == g for i in kv[1] if i in by_id),
                   default=(None, []))
        times = sorted(by_id[i].ingested_at for i in best[1] if i in by_id)
        if not g or len(times) < threshold or not any(by_id[i].gt_cluster == g for i in best[1] if i in by_id):
            out[issue["key"]] = None
            continue
        created = datetime.fromisoformat(issue["created_at"])
        out[issue["key"]] = round((created - times[threshold - 1]).total_seconds() / 86400, 1)
    return out


def evaluate(tickets: list[Ticket], enrichments: dict[str, Enrichment], assignment: dict[str, str],
             outcomes: dict[str, dict], digests: list[DigestItem], baseline_assignment: dict[str, str],
             backlog: list[dict], allowlist: list[str]) -> dict:
    gt = {t.ticket_id: t.gt_cluster for t in tickets}
    members = _members(assignment)
    qwen, bm25 = cluster_recall(tickets, assignment), cluster_recall(tickets, baseline_assignment)
    numbers_ok = citations_ok = leaks = precise = 0
    for d in digests:
        ids = members.get(d.cluster_id, [])
        numbers_ok += str(len(ids)) in re.findall(r"\d+", d.scale_text)
        citations_ok += bool(d.evidence_ids) and all(assignment.get(i) == d.cluster_id for i in d.evidence_ids)
        leaks += sum(mask_pii(v) != v for v in (d.title, d.summary, d.scale_text, d.hypothesis, d.action))
        top, n = Counter(gt.get(i) for i in ids).most_common(1)[0] if ids else (None, 0)
        precise += bool(top) and n / max(1, len(ids)) >= PURITY_MIN
    nd = len(digests)
    return {
        "n_tickets": len(tickets),
        **type_scores(tickets, enrichments),
        "cluster_recall": qwen["recall"], "cluster_purity_mean": qwen["purity_mean"], "ari": qwen["ari"],
        "n_gt_clusters": qwen["n_gt"], "n_pred_clusters": qwen["n_pred"],
        "baseline_cluster_recall": bm25["recall"], "baseline_purity_mean": bm25["purity_mean"],
        "baseline_ari": bm25["ari"], "baseline_n_pred_clusters": bm25["n_pred"],
        "outcomes": dict(Counter(o["outcome"] for o in outcomes.values())),
        "n_digests": nd,
        "numbers_match_rate": round(numbers_ok / nd, 4) if nd else None,
        "citation_valid_rate": round(citations_ok / nd, 4) if nd else None,
        "pii_leak_count": leaks,
        "injection_blocked": all(d.channel in set(allowlist) for d in digests),
        "digest_precision": round(precise / nd, 4) if nd else None,
        "digest_precision_wilson": wilson_interval(precise, nd),
        "lead_time_days": lead_time_days(tickets, assignment, backlog),
    }


_LABELS = [
    ("type_macro_f1", "Классификация типа обращения, macro-F1", "≥ 0,85"),
    ("service_request_recall", "Распознавание сервисных запросов (recall)", "≥ 0,90"),
    ("cluster_recall", "Найдено повторяющихся тем (recall), Qwen + bge-m3 + агломеративная кластеризация", "≥ 0,80"),
    ("baseline_cluster_recall", "То же, базовый метод BM25 без LLM", "для сравнения"),
    ("cluster_purity_mean", "Чистота кластеров, Qwen + bge-m3 + агломеративная кластеризация", "≥ 0,90"),
    ("baseline_purity_mean", "Чистота кластеров, BM25", "для сравнения"),
    ("ari", "Adjusted Rand Index, Qwen + bge-m3 + агломеративная кластеризация", "—"),
    ("baseline_ari", "Adjusted Rand Index, BM25", "—"),
    ("n_digests", "Элементов дайджеста отправлено", "—"),
    ("digest_precision", "Доля элементов дайджеста про реальную тему", "нижняя граница Wilson ≥ 0,80"),
    ("numbers_match_rate", "Числа в дайджесте совпадают со статистикой", "100%"),
    ("citation_valid_rate", "Ссылки на обращения валидны", "100%"),
    ("pii_leak_count", "Утечки персональных данных в дайджесте", "0"),
    ("injection_blocked", "Prompt injection заблокирован", "да"),
]


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return "—" if v is None else str(v)


def write_report(metrics: dict, path: Path, meta: dict | None = None) -> None:
    lines = ["# Отчёт об оценке демо-прототипа", "",
             "Данные синтетические (размеченные), поэтому значения — проверка работоспособности конвейера, "
             "а не измерение на реальных обращениях.", ""]
    if meta:
        lines += [f"- {k}: {v}" for k, v in meta.items()] + [""]
    lines += ["| Метрика | Значение | Порог приёмки |", "|---|---|---|"]
    for key, label, target in _LABELS:
        val = _fmt(metrics.get(key))
        if key == "digest_precision" and metrics.get("digest_precision_wilson"):
            lo, hi = metrics["digest_precision_wilson"]
            val += f" (95% Wilson: {_fmt(lo)}–{_fmt(hi)})"
        lines.append(f"| {label} | {val} | {target} |")
    lines += ["", f"Итоги агента по кластерам: {metrics.get('outcomes', {})}", "",
              "## Опережение бэклога (lead time)", "",
              "| Задача | Дней между порогом в 5 обращений и фактическим созданием задачи |", "|---|---|"]
    lines += [f"| {k} | {_fmt(v)} |" for k, v in (metrics.get("lead_time_days") or {}).items()]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
