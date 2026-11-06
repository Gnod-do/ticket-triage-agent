"""Method B baseline: lexical BM25 grouping with no LLM (used to test whether Qwen adds value)."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from .models import Ticket


class BM25:
    """Okapi BM25 with the Lucene IDF log(1 + (N-n+0.5)/(n+0.5)): always positive, and only terms
    present in a document contribute (rank_bm25's Okapi zeroes common terms on small corpora and
    its Plus/L variants score absent terms)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = sum(self.lens) / max(1, len(docs))
        df = Counter(t for d in self.docs for t in d)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def get_scores(self, query: list[str]) -> list[float]:
        out = []
        for d, dl in zip(self.docs, self.lens):
            s = 0.0
            for q in query:
                tf = d.get(q, 0)
                if tf:
                    s += self.idf[q] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out

_WORD = re.compile(r"[a-zа-яё0-9]+")
_STOP = {"для", "что", "как", "это", "или", "при", "уже", "так", "она", "его", "нас", "вам", "все", "был", "была",
         "есть", "нет", "клиент", "добрый", "день", "пожалуйста", "расшифровка", "звонка"}


def tokenize(text: str) -> list[str]:
    """Lowercase, drop short/stop words, crude stemming by 5-char prefix (good enough for Russian BM25)."""
    return [w[:5] for w in _WORD.findall(text.lower().replace("ё", "е")) if len(w) >= 3 and w not in _STOP]


def bm25_clusters(tickets: list[Ticket], threshold: float = 0.3, min_size: int = 4) -> dict[str, str]:
    """Greedy leader clustering per product: join the best earlier leader whose normalised BM25 score
    (score / leader self-score) is >= threshold, otherwise start a new group. Small groups become noise."""
    assignment: dict[str, str] = {}
    by_product: dict[str, list[Ticket]] = defaultdict(list)
    for t in sorted(tickets, key=lambda t: t.ingested_at):
        by_product[t.product_id].append(t)
    for product, items in sorted(by_product.items()):
        docs = [tokenize(t.text) or ["_"] for t in items]
        bm = BM25(docs)
        self_score = [max(bm.get_scores(d)[i], 1e-9) for i, d in enumerate(docs)]
        leaders: list[int] = []
        group: dict[int, int] = {}
        for i, d in enumerate(docs):
            best, best_score = None, 0.0
            if leaders:
                scores = bm.get_scores(d)
                for j in leaders:
                    s = scores[j] / self_score[j]
                    if s > best_score:
                        best, best_score = j, s
            if best is not None and best_score >= threshold:
                group[i] = group[best]
            else:
                group[i] = len(leaders)
                leaders.append(i)
        sizes = Counter(group.values())
        for i, t in enumerate(items):
            g = group[i]
            assignment[t.ticket_id] = f"bm25:{product}:{g}" if sizes[g] >= min_size else "noise"
    return assignment
