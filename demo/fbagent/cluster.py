"""Stage ④: per-product clustering plus deterministic statistics and spike rule.

No LLM here — every number shown to a product team comes from this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from .models import Alert, ClusterStats, Enrichment, Ticket

CLUSTERABLE_TYPES = {"bug", "feature_request"}
MIN_CONFIDENCE = 0.5
NOISE = "noise"


MERGE_THRESHOLD = 0.28


def _merge_close_clusters(X: np.ndarray, labels: list[int], features: list[str], merge_threshold: float) -> list[int]:
    """Second pass: repeatedly merge the two closest clusters that share a dominant feature code and whose
    normalised centroids are closer than `merge_threshold` (cosine distance).

    Average linkage splits a topic when users describe it with two different symptoms (holdout: «404»
    vs «время не существует» for the same booking bug, centroid distance 0.26). Different topics on the
    same feature stayed ≥ 0.30 apart on both synthetic sets, so 0.28 joins the split without merging
    neighbours; without the feature constraint every threshold ≥ 0.25 collapsed unrelated topics.
    """
    labels = list(labels)
    while True:
        groups: dict[int, list[int]] = defaultdict(list)
        for idx, lab in enumerate(labels):
            groups[lab].append(idx)
        cent, feat = {}, {}
        for lab, idxs in groups.items():
            c = X[idxs].mean(axis=0)
            cent[lab] = c / (np.linalg.norm(c) + 1e-12)
            feat[lab] = Counter(features[i] for i in idxs).most_common(1)[0][0]
        labs, best = sorted(groups), None
        for i, a in enumerate(labs):
            for b in labs[i + 1:]:
                if feat[a] != feat[b]:
                    continue
                d = 1 - float(cent[a] @ cent[b])
                if d < merge_threshold and (best is None or d < best[0]):
                    best = (d, a, b)
        if best is None:
            return labels
        labels = [best[1] if lab == best[2] else lab for lab in labels]


def cluster_tickets(tickets: list[Ticket], enrichments: dict[str, Enrichment],
                    embeddings: dict[str, np.ndarray], min_cluster_size: int = 4,
                    distance_threshold: float = 0.4, merge_threshold: float = MERGE_THRESHOLD) -> dict[str, str]:
    """Average-linkage agglomerative clustering on cosine distance, separately per product, followed by a
    feature-constrained centroid merge (see `_merge_close_clusters`).

    Chosen over HDBSCAN on real bge-m3 embeddings (synthetic labelled set): HDBSCAN(min_cluster_size=4)
    split 14 topics into 45 pure fragments (recall 0.14); average linkage at 0.4 gave recall 0.93,
    purity 0.99. Both thresholds must be re-tuned on a real golden set before production.
    """
    assignment = {t.ticket_id: NOISE for t in tickets}
    by_product: dict[str, list[str]] = defaultdict(list)
    for t in tickets:
        e = enrichments.get(t.ticket_id)
        if e and e.type in CLUSTERABLE_TYPES and e.confidence >= MIN_CONFIDENCE and t.ticket_id in embeddings:
            by_product[t.product_id].append(t.ticket_id)
    for product, ids in sorted(by_product.items()):
        if len(ids) < min_cluster_size:
            continue
        X = np.stack([embeddings[i] for i in ids]).astype(float)
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
        labels = AgglomerativeClustering(n_clusters=None, distance_threshold=distance_threshold,
                                         metric="cosine", linkage="average").fit_predict(X)
        if merge_threshold > 0:
            labels = _merge_close_clusters(X, labels, [enrichments[i].feature for i in ids], merge_threshold)
        sizes = Counter(labels)
        for tid, lab in zip(ids, labels):
            if sizes[lab] >= min_cluster_size:
                assignment[tid] = f"{product}:{lab}"
    return assignment


def _iso_week(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


TREND_WINDOW_DAYS = 28
TREND_RATIO = 1.5
TREND_MIN_DIFF = 3


def _trend(members: list[Ticket], as_of: datetime) -> str:
    """Compare the last 4 weeks with the 4 weeks before. Topics arrive at 1–3 tickets a week, so a 14-day
    window flagged ordinary Poisson noise as «снижение»; a change must be both ×1.5 and ≥ 3 tickets."""
    w = timedelta(days=TREND_WINDOW_DAYS)
    recent = sum(as_of - w < t.ingested_at <= as_of for t in members)
    prev = sum(as_of - 2 * w < t.ingested_at <= as_of - w for t in members)
    if prev == 0:
        return "rising" if recent >= TREND_MIN_DIFF else "stable"
    if recent >= prev * TREND_RATIO and recent - prev >= TREND_MIN_DIFF:
        return "rising"
    if recent * TREND_RATIO <= prev and prev - recent >= TREND_MIN_DIFF:
        return "falling"
    return "stable"


def cluster_stats(cluster_id: str, assignment: dict[str, str], tickets: list[Ticket],
                  as_of: datetime) -> ClusterStats:
    members = sorted((t for t in tickets if assignment.get(t.ticket_id) == cluster_id and t.ingested_at <= as_of),
                     key=lambda t: t.ingested_at)
    if not members:
        raise KeyError(f"unknown or empty cluster: {cluster_id}")
    trend = _trend(members, as_of)
    return ClusterStats(
        cluster_id=cluster_id,
        product_id=members[0].product_id,
        ticket_ids=[t.ticket_id for t in members],
        n_tickets=len(members),
        n_customers=len({t.customer_id for t in members}),
        weekly_counts=dict(sorted(Counter(_iso_week(t.ingested_at) for t in members).items())),
        first_seen=members[0].ingested_at,
        last_seen=members[-1].ingested_at,
        trend=trend,
    )


def detect_spikes(assignment: dict[str, str], tickets: list[Ticket], min_count: int = 5,
                  ratio: float = 3.0) -> list[Alert]:
    if not tickets:
        return []
    hour = lambda d: d.replace(minute=0, second=0, microsecond=0)  # noqa: E731
    span_hours = max(1, int((max(t.ingested_at for t in tickets) - min(t.ingested_at for t in tickets))
                            .total_seconds() // 3600) + 1)
    buckets: dict[str, dict[datetime, list[Ticket]]] = defaultdict(lambda: defaultdict(list))
    for t in tickets:
        c = assignment.get(t.ticket_id, NOISE)
        if c != NOISE:
            buckets[c][hour(t.ingested_at)].append(t)
    alerts = []
    for c, by_hour in sorted(buckets.items()):
        total = sum(len(v) for v in by_hour.values())
        for h, items in sorted(by_hour.items()):
            baseline = (total - len(items)) / span_hours
            if len(items) >= min_count and len(items) >= ratio * baseline:
                alerts.append(Alert(c, items[0].product_id, h, len(items), round(baseline, 3),
                                    [t.ticket_id for t in items[:3]]))
    return alerts
