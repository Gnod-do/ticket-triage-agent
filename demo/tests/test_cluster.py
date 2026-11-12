from datetime import datetime, timedelta, timezone

import numpy as np

from fbagent.cluster import cluster_stats, cluster_tickets, detect_spikes
from fbagent.models import Enrichment, Ticket

T0 = datetime(2026, 8, 3, 8, tzinfo=timezone.utc)  # Monday 08:00 UTC


def mk(i, product="webneft", when=None, customer=None, typ="bug", conf=0.9):
    when = when or T0 + timedelta(hours=i)
    t = Ticket(f"T{i:04d}", product, customer or f"c{i}", "portal", when, when, "x", None, typ)
    e = Enrichment(t.ticket_id, typ, "f", "s", "blocker", conf)
    return t, e


def blobs(n_per=8, centers=((1, 0, 0), (0, 1, 0), (0, 0, 1)), product="webneft", start=0):
    rng = np.random.default_rng(0)
    ts, es, emb, truth = [], {}, {}, {}
    i = start
    for k, c in enumerate(centers):
        for _ in range(n_per):
            t, e = mk(i, product)
            ts.append(t); es[t.ticket_id] = e
            emb[t.ticket_id] = np.array(c, dtype=float) + rng.normal(0, 0.02, 3)
            truth[t.ticket_id] = k
            i += 1
    return ts, es, emb, truth


def test_separates_three_blobs():
    ts, es, emb, truth = blobs()
    a = cluster_tickets(ts, es, emb)
    for k in range(3):
        ids = {a[t] for t, g in truth.items() if g == k}
        assert len(ids) == 1 and "noise" not in ids
    assert len({v for v in a.values()}) == 3


def test_never_mixes_products():
    same = ((1, 0, 0), (0, 1, 0))  # identical vectors in both products
    ts1, es1, emb1, _ = blobs(centers=same, product="webneft")
    ts2, es2, emb2, _ = blobs(centers=same, product="fuel_cards", start=100)
    a = cluster_tickets(ts1 + ts2, {**es1, **es2}, {**emb1, **emb2})
    c1 = {a[t.ticket_id] for t in ts1}
    c2 = {a[t.ticket_id] for t in ts2}
    assert c1.isdisjoint(c2) and "noise" not in c1 | c2
    assert all(c.startswith("webneft:") for c in c1) and all(c.startswith("fuel_cards:") for c in c2)


def test_service_requests_and_low_confidence_excluded():
    ts, es, emb, _ = blobs()
    es[ts[0].ticket_id].type = "service_request"
    es[ts[1].ticket_id].confidence = 0.2
    a = cluster_tickets(ts, es, emb)
    assert a[ts[0].ticket_id] == "noise" and a[ts[1].ticket_id] == "noise"


def test_stats_counts_distinct_tickets_and_customers():
    ts = [mk(i, customer=f"c{i % 4}")[0] for i in range(6)]
    a = {t.ticket_id: "webneft:0" for t in ts}
    s = cluster_stats("webneft:0", a, ts, as_of=T0 + timedelta(days=1))
    assert s.n_tickets == 6 and s.n_customers == 4 and s.product_id == "webneft"
    assert s.first_seen == ts[0].ingested_at and s.last_seen == ts[-1].ingested_at


def test_stats_ignore_tickets_after_as_of():
    ts = [mk(i)[0] for i in range(6)]
    a = {t.ticket_id: "webneft:0" for t in ts}
    s = cluster_stats("webneft:0", a, ts, as_of=ts[2].ingested_at)
    assert s.n_tickets == 3


def _weekly(counts):
    ts, i = [], 0
    for week, n in enumerate(counts):
        for _ in range(n):
            ts.append(mk(i, when=T0 + timedelta(weeks=week, hours=i % 8))[0]); i += 1
    return ts, {t.ticket_id: "webneft:0" for t in ts}


def _trend(counts):
    ts, a = _weekly(counts)
    return cluster_stats("webneft:0", a, ts, as_of=T0 + timedelta(weeks=len(counts))).trend


def test_trend_rising_over_four_week_windows():
    assert _trend([2, 2, 2, 2, 2, 2, 5, 6]) == "rising"


def test_trend_flat_rate_is_stable():
    assert _trend([2, 2, 2, 2, 2, 2, 2, 2]) == "stable"


def test_trend_poisson_noise_is_stable():
    # 5 then 3 tickets per four weeks is ordinary noise, not a decline
    assert _trend([1, 2, 1, 1, 1, 0, 1, 1]) == "stable"


def test_trend_falling():
    assert _trend([3, 3, 2, 2, 1, 0, 1, 0]) == "falling"


def test_trend_new_topic_is_rising():
    assert _trend([0, 0, 0, 0, 0, 1, 2, 3]) == "rising"


def test_spike_detected_and_baseline_not():
    steady = [mk(i, when=T0 + timedelta(days=i // 8, hours=i % 8))[0] for i in range(40)]
    burst = [mk(100 + j, when=T0 + timedelta(days=20, minutes=3 * j))[0] for j in range(12)]
    a = {t.ticket_id: "webneft:0" for t in steady}
    a.update({t.ticket_id: "webneft:1" for t in burst})
    alerts = detect_spikes(a, steady + burst)
    assert len(alerts) == 1 and alerts[0].cluster_id == "webneft:1" and alerts[0].count == 12
    assert detect_spikes({t.ticket_id: "webneft:0" for t in steady}, steady) == []


def test_small_groups_are_noise():
    ts, es, emb, _ = blobs(n_per=8, centers=((1, 0, 0), (0, 1, 0)))
    extra, e2, emb2, _ = blobs(n_per=3, centers=((0, 0, 1),), start=200)
    a = cluster_tickets(ts + extra, {**es, **e2}, {**emb, **emb2})
    assert all(a[t.ticket_id] == "noise" for t in extra)


def test_threshold_controls_merging():
    ts, es, emb, _ = blobs(n_per=6, centers=((1, 0.0, 0), (1, 0.35, 0)))  # ~19° apart: cosine distance ~0.055
    assert len({v for v in cluster_tickets(ts, es, emb, distance_threshold=0.4).values()}) == 1
    assert len({v for v in cluster_tickets(ts, es, emb, distance_threshold=0.02, merge_threshold=0.0).values()}) == 2


def test_centroid_merge_joins_split_topic():
    ts, es, emb, _ = blobs(n_per=6, centers=((1, 0.0, 0), (1, 0.35, 0)))  # cosine distance ~0.055
    split = cluster_tickets(ts, es, emb, distance_threshold=0.02, merge_threshold=0.0)
    merged = cluster_tickets(ts, es, emb, distance_threshold=0.02, merge_threshold=0.1)
    assert len(set(split.values())) == 2 and len(set(merged.values())) == 1 and "noise" not in merged.values()


def test_centroid_merge_keeps_distinct_topics():
    ts, es, emb, truth = blobs()  # orthogonal centres: distance 1.0
    a = cluster_tickets(ts, es, emb, distance_threshold=0.4, merge_threshold=0.3)
    assert len(set(a.values())) == 3


def test_centroid_merge_requires_same_feature():
    ts, es, emb, _ = blobs(n_per=6, centers=((1, 0.0, 0), (1, 0.35, 0)))
    for t in ts[6:]:
        es[t.ticket_id].feature = "another"
    a = cluster_tickets(ts, es, emb, distance_threshold=0.02, merge_threshold=0.1)
    assert len(set(a.values())) == 2
