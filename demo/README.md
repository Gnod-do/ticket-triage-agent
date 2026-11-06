# Demo: support → product feedback agent

Prototype of the solution for the Intelligence Cup 2026 Gazprom Neft case. It runs fully locally, with no external APIs:
the Qwen model and bge-m3 embeddings are served by Ollama, matching the case rule that only internal models may be used.

```
tickets (synthetic, labeled) → ③ enrich (Qwen, JSON) → ④ embed + HDBSCAN per product → spike alerts
                             → ⑤ agent (Qwen function calling, 10 tools, PolicyGate) → digest
                             → evaluation vs ground truth + BM25 baseline → finance scenarios
```

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                   # 63 offline tests, no model needed
.venv/bin/python -m fbagent.run --fake             # pipeline smoke run with rule-based stand-in
ollama serve &                                     # real run
ollama pull qwen3:8b && ollama pull bge-m3
.venv/bin/python -m fbagent.run                    # → demo/out/
```

Outputs in `demo/out/`: `digest.md` (items for product teams), `alerts.md` (early-warning spikes),
`eval_report.md` (metrics vs acceptance thresholds), `finance.md` and `tornado.png` (financial model),
`agent_traces.json`, `run_meta.json`.

`--fake` only proves that the plumbing works. Its lexical embeddings cannot group paraphrases,
so it says nothing about quality. Quality numbers come only from a real Qwen run.

## Layout

| Module | Spec service | Role |
|---|---|---|
| `data_gen.py`, `data/seeds.yaml` | — | ~370 synthetic Russian tickets, 2 products, spike, PII, prompt injection |
| `pii.py` | ① ingest | phone / e-mail / INN / card masking before any model call |
| `enrich.py`, `prompts.py` | ③ enrich | one JSON-schema call per ticket, validated, cached |
| `cluster.py` | ④ cluster | per-product HDBSCAN, deterministic stats, spike rule |
| `tools.py`, `agent.py` | ⑤ agent-digest | 10 tools, aliases E1..En, PolicyGate, 8-call budget |
| `baseline.py` | — | BM25 grouping without an LLM (method B, for comparison) |
| `evaluate.py`, `finance.py` | — | metrics with Wilson CI, lead time, max investment for ≤3-year payback |
