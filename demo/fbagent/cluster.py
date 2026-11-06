"""Stage ④: per-product clustering plus deterministic statistics and spike rule.

No LLM here — every number shown to a product team comes from this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sklearn.cluster import HDBSCAN

from .models import Alert, ClusterStats, Enrichment, Ticket

CLUSTERABLE_TYPES = {"bug", "feature_request"}
MIN_CONFIDENCE = 0.5
NOISE = "noise"


def cluster_tickets(tickets: list[Ticket], enrichments: dict[str, Enrichment],
                    embeddings: dict[str, np.ndarray], min_cluster_size: int = 4,
                    min_samples: int | None = None) -> dict[str, str]:
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
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-12  # euclidean on unit vectors ~ cosine
        labels = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, copy=True).fit_predict(X)
        for tid, lab in zip(ids, labels):
            if lab >= 0:
                assignment[tid] = f"{product}:{lab}"
    return assignment


def _iso_week(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def cluster_stats(cluster_id: str, assignment: dict[str, str], tickets: list[Ticket],
                  as_of: datetime) -> ClusterStats:
    members = sorted((t for t in tickets if assignment.get(t.ticket_id) == cluster_id and t.ingested_at <= as_of),
                     key=lambda t: t.ingested_at)
    if not members:
        raise KeyError(f"unknown or empty cluster: {cluster_id}")
    recent = sum(as_of - timedelta(days=14) < t.ingested_at <= as_of for t in members)
    prev = sum(as_of - timedelta(days=28) < t.ingested_at <= as_of - timedelta(days=14) for t in members)
    if prev == 0:
        trend = "rising" if recent >= 2 else "stable"
    elif recent >= prev * 1.3:
        trend = "rising"
    elif recent <= prev * 0.7:
        trend = "falling"
    else:
        trend = "stable"
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
