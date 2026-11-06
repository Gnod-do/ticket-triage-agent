"""Stage ⑤ tools: what the agent may read and the guarded actions it may take.

The model never sees real ticket IDs (only per-cluster aliases E1..En) and never computes numbers:
every count comes from cluster_stats, and every write passes PolicyGate.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .baseline import BM25, tokenize
from .cluster import cluster_stats
from .models import ClusterStats, DigestItem, Enrichment, Ticket
from .pii import mask_pii

MIN_EVIDENCE = 5
LABEL_STATUSES = ("noise", "service_request")
DRAFT_TEXT_FIELDS = ("title", "summary", "scale_text", "hypothesis", "action")

class PolicyGate:
    def __init__(self, allowlist: list[str]):
        self.allowlist = set(allowlist)

    def check(self, draft: dict, stats: ClusterStats, owner: dict, valid_refs: set[str]) -> list[str]:
        v = []
        refs = draft.get("evidence") or []
        if len(set(refs)) < MIN_EVIDENCE:
            v.append(f"нужно не менее {MIN_EVIDENCE} разных ссылок на обращения (evidence), получено {len(set(refs))}")
        bad = [r for r in refs if r not in valid_refs]
        if bad:
            v.append(f"ссылки не из этого кластера или не выданы инструментом: {', '.join(map(str, bad))}")
        for f in DRAFT_TEXT_FIELDS:
            val = str(draft.get(f, ""))
            if not val.strip():
                v.append(f"пустое поле {f}")
            elif mask_pii(val) != val:
                v.append(f"поле {f} содержит персональные данные")
        allowed_numbers = {stats.n_tickets, stats.n_customers, len(stats.weekly_counts), *stats.weekly_counts.values()}
        scale = re.sub(r"(?:\d{4}-)?W\d{1,2}\b", "", str(draft.get("scale_text", "")))  # ISO week labels are not counts
        nums = {int(x) for x in re.findall(r"\d+", scale)}
        if stats.n_tickets not in nums:
            v.append(f"scale_text должен содержать число обращений из get_cluster_stats ({stats.n_tickets})")
        if nums - allowed_numbers:
            v.append(f"scale_text содержит число не из get_cluster_stats: {sorted(nums - allowed_numbers)}")
        channel = draft.get("channel")
        if channel not in self.allowlist:
            v.append(f"канал {channel!r} не входит в разрешённый список")
        elif owner.get("channel") and channel != owner["channel"]:
            v.append(f"канал должен совпадать с каналом владельца ({owner['channel']})")
        return v

class ToolBox:
    def __init__(self, tickets: list[Ticket], enrichments: dict[str, Enrichment], assignment: dict[str, str],
                 backlog_path: Path, owners_path: Path, as_of: datetime, history: dict | None = None):
        self.tickets = [t for t in tickets if t.ingested_at <= as_of]
        self.by_id = {t.ticket_id: t for t in self.tickets}
        self.enrichments, self.assignment, self.as_of = enrichments, assignment, as_of
        self.backlog_path = Path(backlog_path)
        self.backlog = json.loads(self.backlog_path.read_text(encoding="utf-8"))
        owners = json.loads(Path(owners_path).read_text(encoding="utf-8"))
        self.owners, self.gate = owners["owners"], PolicyGate(owners["allowlist"])
        self.history = history or {}
        self.aliases: dict[str, dict[str, str]] = {}
        self.outcomes: dict[str, dict] = {}
        self.digests: list[DigestItem] = []
        self.backlog_comments: list[dict] = []
        self.current_cluster: str | None = None

    # ---------- helpers ----------
    def _stats(self, cluster_id: str) -> ClusterStats:
        return cluster_stats(cluster_id, self.assignment, self.tickets, self.as_of)

    def _top_features(self, ids: list[str]) -> list[str]:
        return [f for f, _ in Counter(self.enrichments[i].feature for i in ids if i in self.enrichments).most_common(3)]

    def resolve_refs(self, cluster_id: str, refs: list[str]) -> list[str]:
        m = self.aliases.get(cluster_id, {})
        return [m[r] for r in refs if r in m]

    # ---------- read tools ----------
    def get_cluster_stats(self, cluster_id: str) -> dict:
        s = self._stats(cluster_id)
        return {"cluster_id": cluster_id, "product_id": s.product_id, "n_tickets": s.n_tickets,
                "n_customers": s.n_customers, "weekly_counts": s.weekly_counts, "trend": s.trend,
                "first_seen": s.first_seen.date().isoformat(), "last_seen": s.last_seen.date().isoformat(),
                "top_features": self._top_features(s.ticket_ids),
                "channels": dict(Counter(self.by_id[i].channel for i in s.ticket_ids))}

    def get_cluster_examples(self, cluster_id: str, k: int = 5) -> dict:
        s = self._stats(cluster_id)
        members = sorted((self.by_id[i] for i in s.ticket_ids), key=lambda t: t.ingested_at, reverse=True)
        seen, picked = set(), []
        for t in members:  # diverse by customer first, then fill
            if t.customer_id not in seen:
                picked.append(t); seen.add(t.customer_id)
        picked += [t for t in members if t not in picked]
        amap = self.aliases.setdefault(cluster_id, {})
        rev = {tid: a for a, tid in amap.items()}
        out = []
        for t in picked[:max(1, min(int(k), 10))]:
            alias = rev.get(t.ticket_id) or f"E{len(amap) + 1}"
            amap[alias] = t.ticket_id
            rev[t.ticket_id] = alias
            e = self.enrichments.get(t.ticket_id)
            out.append({"ref": alias, "channel": t.channel, "date": t.ingested_at.date().isoformat(),
                        "text": mask_pii(t.text), "summary": e.problem_summary if e else ""})
        return {"cluster_id": cluster_id, "examples": out}

    def search_tickets(self, query: str, product_id: str, k: int = 5) -> dict:
        items = [t for t in self.tickets if t.product_id == product_id]
        if not items:
            return {"results": []}
        bm = BM25([tokenize(t.text) or ["_"] for t in items])
        scores = bm.get_scores(tokenize(query))
        top = sorted(zip(scores, items), key=lambda x: -x[0])[:max(1, min(int(k), 10))]
        return {"results": [{"cluster_id": self.assignment.get(t.ticket_id, "noise"), "score": round(float(s), 2),
                             "text": mask_pii(t.text)} for s, t in top if s > 0]}

    def search_backlog(self, product_id: str, query: str) -> dict:
        q = set(tokenize(query))
        hits = []
        for issue in self.backlog:
            if issue["product_id"] != product_id:
                continue
            overlap = len(q & set(tokenize(issue["title"]))) / max(1, len(q))
            if overlap >= 0.25:
                hits.append({"key": issue["key"], "title": issue["title"], "status": issue.get("status", "open"),
                             "score": round(overlap, 2)})
        return {"issues": sorted(hits, key=lambda h: -h["score"])[:3]}

    def get_product_owner(self, product_id: str, feature: str) -> dict:
        exact = [o for o in self.owners if o["product_id"] == product_id and o["feature"] == feature]
        fallback = [o for o in self.owners if o["product_id"] == product_id and o["feature"] == "*"]
        o = (exact or fallback or [None])[0]
        return {"team": o["team"], "channel": o["channel"]} if o else {"team": None, "channel": None}

    def get_cluster_history(self, cluster_id: str) -> dict:
        return {"cluster_id": cluster_id, "previous": self.history.get(cluster_id, [])}

    # ---------- write tools (guarded) ----------
    def submit_digest_item(self, cluster_id: str, draft: dict) -> dict:
        s = self._stats(cluster_id)
        owner = self.get_product_owner(s.product_id, (self._top_features(s.ticket_ids) or ["*"])[0])
        violations = self.gate.check(draft, s, owner, set(self.aliases.get(cluster_id, {})))
        if owner["team"] is None:
            violations.append("владелец продукта не найден — нужна ручная проверка")
        if violations:
            return {"ok": False, "violations": violations}
        item = DigestItem(cluster_id, s.product_id, draft["title"], draft["summary"], draft["scale_text"],
                          self.resolve_refs(cluster_id, list(dict.fromkeys(draft["evidence"]))),
                          draft["hypothesis"], draft["action"], owner["team"], draft["channel"])
        self.digests.append(item)
        self.outcomes[cluster_id] = {"outcome": "digest"}
        return {"ok": True, "message": "элемент дайджеста принят"}

    def update_backlog_item(self, issue_key: str, comment: str) -> dict:
        if not any(i["key"] == issue_key for i in self.backlog):
            return {"ok": False, "violations": [f"задача {issue_key} не найдена"]}
        if mask_pii(comment) != comment:
            return {"ok": False, "violations": ["комментарий содержит персональные данные"]}
        self.backlog_comments.append({"issue_key": issue_key, "comment": comment, "cluster_id": self.current_cluster})
        if self.current_cluster:
            self.outcomes[self.current_cluster] = {"outcome": "linked", "issue_key": issue_key}
        return {"ok": True, "message": "комментарий добавлен"}

    def request_human_review(self, cluster_id: str, reason: str) -> dict:
        self.outcomes[cluster_id] = {"outcome": "review", "reason": mask_pii(str(reason))}
        return {"ok": True}

    def label_cluster(self, cluster_id: str, status: str) -> dict:
        if status not in LABEL_STATUSES and not str(status).startswith("merge_with:"):
            return {"ok": False, "violations": [f"недопустимый статус {status}"]}
        self.outcomes[cluster_id] = {"outcome": "labeled", "status": status}
        return {"ok": True}

    # ---------- schemas for function calling ----------
    def schemas(self) -> list[dict]:
        def fn(name, desc, props, required):
            return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
                "type": "object", "properties": props, "required": required}}}
        s, i = {"type": "string"}, {"type": "integer"}
        cid = {"cluster_id": s}
        return [
            fn("get_cluster_stats", "Точная статистика кластера: число обращений, клиентов, динамика.", cid, ["cluster_id"]),
            fn("get_cluster_examples", "Примеры обращений кластера с псевдонимами E1..En.", {**cid, "k": i}, ["cluster_id"]),
            fn("search_tickets", "Поиск похожих обращений внутри продукта.", {"query": s, "product_id": s}, ["query", "product_id"]),
            fn("search_backlog", "Поиск уже существующих задач в бэклоге продукта. query — ключевые слова на русском из текстов обращений.", {"product_id": s, "query": s}, ["product_id", "query"]),
            fn("get_product_owner", "Команда-владелец и канал доставки.", {"product_id": s, "feature": s}, ["product_id", "feature"]),
            fn("get_cluster_history", "Прошлые дайджесты и решения команды по кластеру.", cid, ["cluster_id"]),
            fn("submit_digest_item", "Отправить элемент дайджеста (проверяется политикой).", {**cid, "draft": {
                "type": "object", "properties": {k: s for k in DRAFT_TEXT_FIELDS + ("channel",)} | {
                    "evidence": {"type": "array", "items": s}},
                "required": list(DRAFT_TEXT_FIELDS) + ["channel", "evidence"]}}, ["cluster_id", "draft"]),
            fn("update_backlog_item", "Добавить комментарий к существующей задаче.", {"issue_key": s, "comment": s}, ["issue_key", "comment"]),
            fn("request_human_review", "Передать кластер эксперту.", {**cid, "reason": s}, ["cluster_id", "reason"]),
            fn("label_cluster", "Пометить кластер: noise | service_request | merge_with:<id>.", {**cid, "status": s}, ["cluster_id", "status"]),
        ]
