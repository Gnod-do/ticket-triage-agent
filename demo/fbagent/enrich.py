"""Stage ③: one structured LLM call per ticket, validated and cached."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import yaml

from .llm import LLMClient
from .models import TICKET_TYPES, USER_IMPACTS, Enrichment, Ticket
from .pii import mask_pii
from .prompts import ENRICH_PROMPT, PROMPT_VERSION, enrich_schema

log = logging.getLogger(__name__)
TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data" / "taxonomy.yaml"
_TAXONOMY: dict | None = None


def taxonomy() -> dict[str, dict[str, str]]:
    global _TAXONOMY
    if _TAXONOMY is None:
        _TAXONOMY = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return _TAXONOMY


def _fallback(ticket_id: str, reason: str) -> Enrichment:
    log.warning("enrich fallback for %s: %s", ticket_id, reason)
    return Enrichment(ticket_id, "other", "unknown", "", "degraded", 0.0)


def _parse(ticket_id: str, content: str, features: list[str] | None = None) -> Enrichment:
    try:
        d = json.loads(content)
        if d["type"] not in TICKET_TYPES or d["user_impact"] not in USER_IMPACTS:
            return _fallback(ticket_id, f"enum out of range: {d.get('type')}/{d.get('user_impact')}")
        feature = str(d["feature"]).strip() or "other"
        if features and feature not in features:
            feature = "other"
        return Enrichment(ticket_id, d["type"], feature,
                          mask_pii(str(d["problem_summary"]).strip()), d["user_impact"],
                          max(0.0, min(1.0, float(d["confidence"]))))
    except (ValueError, KeyError, TypeError) as e:
        return _fallback(ticket_id, f"invalid output: {e}")


def enrich_ticket(t: Ticket, llm: LLMClient, cache_dir: Path | None) -> Enrichment:
    text = mask_pii(t.text)
    key = hashlib.sha256(f"{llm.model}|{PROMPT_VERSION}|{t.product_id}|{text}".encode()).hexdigest()
    cache_file = Path(cache_dir) / f"{key}.json" if cache_dir else None
    if cache_file and cache_file.exists():
        try:
            d = json.loads(cache_file.read_text(encoding="utf-8"))
            return Enrichment(**{**d, "ticket_id": t.ticket_id})
        except (ValueError, TypeError):
            log.warning("unreadable cache entry %s, recomputing", cache_file.name)  # half-written or corrupt
    feats = taxonomy().get(t.product_id)
    listing = "\n".join(f"  {k} — {v}" for k, v in feats.items()) if feats else "  (свободный код латиницей)"
    prompt = ENRICH_PROMPT.format(product_id=t.product_id, text=text, features=listing)
    resp = llm.chat([{"role": "user", "content": prompt}], json_schema=enrich_schema(list(feats) if feats else None))
    e = _parse(t.ticket_id, resp.get("content", ""), list(feats) if feats else None)
    if cache_file and e.confidence > 0:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_name(f"{cache_file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(asdict(e), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache_file)  # atomic: concurrent readers see either nothing or a complete file
    return e


def enrich_all(tickets: list[Ticket], llm: LLMClient, cache_dir: Path | None,
               progress: bool = False, workers: int = 1) -> dict[str, Enrichment]:
    """One call per ticket; `workers` > 1 sends requests concurrently (Ollama serves several at once when
    OLLAMA_NUM_PARALLEL allows). Results keep ticket order whatever the completion order."""
    out: dict[str, Enrichment] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, (t, e) in enumerate(zip(tickets, pool.map(lambda t: enrich_ticket(t, llm, cache_dir), tickets)), 1):
            out[t.ticket_id] = e
            if progress and i % 25 == 0:
                print(f"  enriched {i}/{len(tickets)}", flush=True)
    return out
