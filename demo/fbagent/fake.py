"""Offline stand-in for Qwen used by `--fake` (CI and quick demos without a model server).

Rule-based enrichment, hashed bag-of-words embeddings and a scripted agent that follows the
prescribed tool order. It exercises the whole pipeline; it is NOT a quality claim about Qwen.
"""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np

from .baseline import tokenize
from .llm import FakeLLM

_SERVICE = re.compile(r"прошу|просим (перенести|отменить|увеличить)|требуется добавить|выпустить|перевыпустить|"
                      r"смените|нужно изменить реквизиты|помогите получить логин", re.I)
_CONSULT = re.compile(r"подскажите|^как |где в|какие документы|на каких|как получить|как узнать", re.I)
_FEATURE = re.compile(r"хотим|хотелось|просим (добавить|дать|сделать)|было бы|можно ли|нужна (возможность|функция)|"
                      r"предлагаем|предлагает|добавьте|нужно, чтобы|есть ли возможность|неудобно|сделайте", re.I)


def _enrich_reply(prompt: str) -> dict:
    text = prompt.rsplit('"""', 2)[-2] if '"""' in prompt else prompt
    body = text.replace("[Расшифровка звонка] Клиент: ", "")
    if _SERVICE.search(body):
        typ = "service_request"
    elif _CONSULT.search(body.strip()):
        typ = "consultation"
    elif _FEATURE.search(body):
        typ = "feature_request"
    else:
        typ = "bug"
    summary = body.split(".")[0][:160]
    return {"content": json.dumps({"type": typ, "feature": "general", "problem_summary": summary,
                                   "user_impact": "degraded", "confidence": 0.8}, ensure_ascii=False),
            "tool_calls": []}


def _tool_results(messages: list[dict]) -> list[tuple[str, dict]]:
    return [(m.get("tool_name", ""), json.loads(m["content"])) for m in messages if m.get("role") == "tool"]


def _agent_reply(messages: list[dict]) -> dict:
    cid = re.search(r"cluster_id: (\S+)", messages[1]["content"]).group(1)
    product = re.search(r"product_id: (\S+)", messages[1]["content"]).group(1)
    done = _tool_results(messages)
    res = dict(done)
    call = lambda name, **a: {"content": "", "tool_calls": [{"function": {"name": name, "arguments": a}}]}  # noqa: E731
    if "get_cluster_stats" not in res:
        return call("get_cluster_stats", cluster_id=cid)
    if "get_cluster_examples" not in res:
        return call("get_cluster_examples", cluster_id=cid, k=5)
    examples = res["get_cluster_examples"]["examples"]
    query = examples[0]["summary"] or examples[0]["text"]
    if "search_backlog" not in res:
        return call("search_backlog", product_id=product, query=query)
    issues = res["search_backlog"]["issues"]
    stats = res["get_cluster_stats"]
    if issues and "update_backlog_item" not in res:
        return call("update_backlog_item", issue_key=issues[0]["key"],
                    comment=f"+{stats['n_tickets']} обращений по теме за период наблюдения")
    if "get_product_owner" not in res:
        return call("get_product_owner", product_id=product, feature=(stats["top_features"] or ["*"])[0])
    if "submit_digest_item" not in res:
        draft = {"title": query[:60], "summary": f"Пользователи сообщают: {query}.",
                 "scale_text": f"{stats['n_tickets']} обращений от {stats['n_customers']} клиентов, "
                               f"динамика: {stats['trend']}",
                 "evidence": [e["ref"] for e in examples], "hypothesis": "Гипотеза: требуется проверка командой.",
                 "action": "Проверить сценарий и оценить приоритет.", "channel": res["get_product_owner"]["channel"]}
        return call("submit_digest_item", cluster_id=cid, draft=draft)
    return {"content": "Готово", "tool_calls": []}


def _respond(messages: list[dict]) -> dict:
    if messages and messages[0].get("role") == "system":
        return _agent_reply(messages)
    return _enrich_reply(messages[-1]["content"])


def _embed(texts: list[str], dim: int = 256) -> np.ndarray:
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        for tok in tokenize(t):
            out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
    return out


def make_fake_llm() -> FakeLLM:
    return FakeLLM(_respond, embed_fn=_embed)
