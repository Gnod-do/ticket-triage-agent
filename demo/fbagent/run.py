"""End-to-end demo: python -m fbagent.run [--fake] [--model qwen3:8b] [--limit N]."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .agent import run_agent_for_cluster
from .baseline import bm25_clusters
from .cluster import cluster_stats, cluster_tickets, detect_spikes
from .data_gen import generate_tickets, save_jsonl
from .enrich import enrich_all
from .evaluate import evaluate, write_report
from .fake import make_fake_llm
from .finance import scenarios, tornado
from .finance import write_report as write_finance
from .llm import LLMUnavailable, OllamaClient
from .pii import mask_pii
from .tools import MIN_EVIDENCE, ToolBox

DEMO = Path(__file__).resolve().parents[1]


def _embed_all(llm, tickets, enrichments, batch=64) -> dict[str, np.ndarray]:
    ids = [t.ticket_id for t in tickets]
    by_id = {t.ticket_id: t for t in tickets}
    texts = [mask_pii(by_id[i].text.replace("[Расшифровка звонка] Клиент: ", "")) + " " +
             enrichments[i].problem_summary for i in ids]  # ticket text + Qwen summary (most stable on eval)
    vecs = []
    for k in range(0, len(texts), batch):
        vecs.append(llm.embed(texts[k:k + batch]))
    return dict(zip(ids, np.concatenate(vecs))) if vecs else {}


def _write_digest(items, path: Path) -> None:
    lines = ["# Дайджест для продуктовых команд", ""]
    for d in items:
        lines += [f"## {d.title}", "", f"- **Продукт / команда:** {d.product_id} — {d.owner_team} ({d.channel})",
                  f"- **Масштаб:** {d.scale_text}", f"- **Суть:** {d.summary}", f"- **{d.hypothesis}**",
                  f"- **Предлагаемое действие:** {d.action}",
                  f"- **Обращения-основания:** {', '.join(d.evidence_ids)}", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_alerts(alerts, path: Path) -> None:
    lines = ["# Ранние предупреждения (всплески)", "",
             "| Кластер | Продукт | Час (UTC) | Обращений за час | Фон, обращений/час | Примеры |", "|---|---|---|---|---|---|"]
    lines += [f"| {a.cluster_id} | {a.product_id} | {a.hour:%Y-%m-%d %H:00} | {a.count} | {a.baseline} | "
              f"{', '.join(a.sample_ids)} |" for a in alerts]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fake", action="store_true", help="rule-based offline stand-in instead of Ollama")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--embed-model", default="bge-m3")
    ap.add_argument("--limit", type=int, default=None, help="use only the first N tickets")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(DEMO / "out"))
    ap.add_argument("--cache", default=str(DEMO / ".cache"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    timings, t0 = {}, time.time()

    tickets = generate_tickets(DEMO / "data" / "seeds.yaml", seed=a.seed)[: a.limit]
    save_jsonl(tickets, out / "tickets.jsonl")
    llm = make_fake_llm() if a.fake else OllamaClient(model=a.model, embed_model=a.embed_model)
    try:
        print(f"[1/5] enrich {len(tickets)} tickets with {llm.model}", flush=True)
        enrichments = enrich_all(tickets, llm, Path(a.cache) / "enrich", progress=True)
        timings["enrich_s"] = round(time.time() - t0, 1)
        print("[2/5] embed + cluster", flush=True)
        embeddings = _embed_all(llm, tickets, enrichments)
        assignment = cluster_tickets(tickets, enrichments, embeddings)
        alerts = detect_spikes(assignment, tickets)
        as_of = max(t.ingested_at for t in tickets)
        backlog_path = DEMO / "data" / "mocks" / "backlog.json"
        owners_path = DEMO / "data" / "mocks" / "owners.json"
        box = ToolBox(tickets, enrichments, assignment, backlog_path, owners_path, as_of)
        clusters = sorted({c for c in assignment.values() if c != "noise"})
        eligible = [c for c in clusters if cluster_stats(c, assignment, tickets, as_of).n_tickets >= MIN_EVIDENCE]
        print(f"[3/5] agent over {len(eligible)} of {len(clusters)} clusters", flush=True)
        t1, traces = time.time(), {}
        for c in eligible:
            traces[c] = run_agent_for_cluster(c, box, llm)
        timings["agent_s"] = round(time.time() - t1, 1)
    except LLMUnavailable as e:
        print(f"ERROR: {e}\nStart the model server and pull the models first:\n"
              f"  ollama serve\n  ollama pull {a.model}\n  ollama pull {a.embed_model}", file=sys.stderr)
        return 2

    print("[4/5] baseline + evaluation", flush=True)
    baseline = bm25_clusters(tickets)
    backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
    allowlist = json.loads(owners_path.read_text(encoding="utf-8"))["allowlist"]
    metrics = evaluate(tickets, enrichments, assignment, box.outcomes, box.digests, baseline, backlog, allowlist)
    meta = {"model": llm.model, "embed_model": "hash-bow" if a.fake else a.embed_model, "n_tickets": len(tickets),
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **timings,
            "total_s": round(time.time() - t0, 1), "usage": getattr(llm, "usage", {})}
    write_report(metrics, out / "eval_report.md", meta={k: meta[k] for k in ("model", "embed_model", "n_tickets",
                                                                           "total_s")})
    _write_digest(box.digests, out / "digest.md")
    _write_alerts(alerts, out / "alerts.md")
    (out / "agent_traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")

    print("[5/5] finance", flush=True)
    rows = scenarios(DEMO / "finance" / "assumptions.yaml")
    write_finance(rows, out / "finance.md")
    tornado(next(r for r in rows if r["name"] == "base")["params"], out / "tornado.png")
    meta.update(n_alerts=len(alerts), metrics={k: v for k, v in metrics.items() if k != "lead_time_days"},
                lead_time_days=metrics["lead_time_days"])
    (out / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"done in {meta['total_s']}s → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
