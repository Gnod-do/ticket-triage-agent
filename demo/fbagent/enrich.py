"""Stage ③: one structured LLM call per ticket, validated and cached."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .llm import LLMClient
from .models import TICKET_TYPES, USER_IMPACTS, Enrichment, Ticket
from .pii import mask_pii
from .prompts import ENRICH_PROMPT, ENRICH_SCHEMA, PROMPT_VERSION

log = logging.getLogger(__name__)


def _fallback(ticket_id: str, reason: str) -> Enrichment:
    log.warning("enrich fallback for %s: %s", ticket_id, reason)
    return Enrichment(ticket_id, "other", "unknown", "", "degraded", 0.0)


def _parse(ticket_id: str, content: str) -> Enrichment:
    try:
        d = json.loads(content)
        if d["type"] not in TICKET_TYPES or d["user_impact"] not in USER_IMPACTS:
            return _fallback(ticket_id, f"enum out of range: {d.get('type')}/{d.get('user_impact')}")
        return Enrichment(ticket_id, d["type"], str(d["feature"]).strip() or "unknown",
                          mask_pii(str(d["problem_summary"]).strip()), d["user_impact"],
                          max(0.0, min(1.0, float(d["confidence"]))))
    except (ValueError, KeyError, TypeError) as e:
        return _fallback(ticket_id, f"invalid output: {e}")


def enrich_ticket(t: Ticket, llm: LLMClient, cache_dir: Path | None) -> Enrichment:
    text = mask_pii(t.text)
    key = hashlib.sha256(f"{llm.model}|{PROMPT_VERSION}|{t.product_id}|{text}".encode()).hexdigest()
    cache_file = Path(cache_dir) / f"{key}.json" if cache_dir else None
    if cache_file and cache_file.exists():
        d = json.loads(cache_file.read_text(encoding="utf-8"))
        return Enrichment(**{**d, "ticket_id": t.ticket_id})
    prompt = ENRICH_PROMPT.format(product_id=t.product_id, text=text)
    resp = llm.chat([{"role": "user", "content": prompt}], json_schema=ENRICH_SCHEMA)
    e = _parse(t.ticket_id, resp.get("content", ""))
    if cache_file and e.confidence > 0:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(asdict(e), ensure_ascii=False), encoding="utf-8")
    return e


def enrich_all(tickets: list[Ticket], llm: LLMClient, cache_dir: Path | None,
               progress: bool = False) -> dict[str, Enrichment]:
    out = {}
    for i, t in enumerate(tickets, 1):
        out[t.ticket_id] = enrich_ticket(t, llm, cache_dir)
        if progress and i % 25 == 0:
            print(f"  enriched {i}/{len(tickets)}", flush=True)
    return out
