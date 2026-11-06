"""Stage ⑤ agent: a bounded function-calling loop over one cluster."""
from __future__ import annotations

import json

from .llm import LLMClient
from .prompts import AGENT_SYSTEM_PROMPT
from .tools import MIN_EVIDENCE, ToolBox

TOOL_NAMES = {"get_cluster_stats", "get_cluster_examples", "search_tickets", "search_backlog", "get_product_owner",
              "get_cluster_history", "submit_digest_item", "update_backlog_item", "request_human_review",
              "label_cluster"}


def _execute(box: ToolBox, cluster_id: str, name: str, args) -> dict:
    if name not in TOOL_NAMES:
        return {"error": f"неизвестный инструмент: {name}"}
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return {"error": "аргументы должны быть JSON-объектом"}
    if not isinstance(args, dict):
        return {"error": "аргументы должны быть JSON-объектом"}
    if "cluster_id" in args and args["cluster_id"] != cluster_id:
        return {"error": f"можно работать только с кластером {cluster_id}"}
    try:
        return getattr(box, name)(**args)
    except (TypeError, KeyError, ValueError) as e:
        return {"error": f"ошибка вызова {name}: {e}"}


MAX_REJECTED_SUBMITS = 2


def run_agent_for_cluster(cluster_id: str, toolbox: ToolBox, llm: LLMClient, max_calls: int = 8) -> dict:
    toolbox.current_cluster = cluster_id
    product = toolbox.get_cluster_stats(cluster_id)["product_id"]
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": f"cluster_id: {cluster_id}\nproduct_id: {product}\n"
                                            f"Минимум ссылок на обращения: {MIN_EVIDENCE}. Начни с get_cluster_stats."}]
    schemas, calls, trace, rejected = toolbox.schemas(), 0, [], 0

    def done():
        return toolbox.outcomes.get(cluster_id)

    while not done():
        resp = llm.chat(messages, tools=schemas)
        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            toolbox.request_human_review(cluster_id, "агент завершил работу без итогового действия")
            break
        messages.append({"role": "assistant", "content": resp.get("content", ""), "tool_calls": tool_calls})
        for tc in tool_calls:
            if calls >= max_calls:
                break
            fn = tc.get("function", {})
            name = fn.get("name", "")
            result = _execute(toolbox, cluster_id, name, fn.get("arguments", {}))
            calls += 1
            trace.append({"tool": name, "args": fn.get("arguments"), "result": result})
            messages.append({"role": "tool", "tool_name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)})
            if name == "submit_digest_item" and result.get("ok") is False:
                rejected += 1
                if rejected >= MAX_REJECTED_SUBMITS:
                    toolbox.request_human_review(cluster_id, "PolicyGate отклонил черновик дважды: "
                                                 + "; ".join(result.get("violations", [])))
            if done():
                break
        if not done() and calls >= max_calls:
            toolbox.request_human_review(cluster_id, f"превышен лимит вызовов инструментов ({max_calls})")
    toolbox.current_cluster = None
    return {"outcome": done()["outcome"], "calls": calls, "trace": trace}
