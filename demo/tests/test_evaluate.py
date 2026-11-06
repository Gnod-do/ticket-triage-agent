from datetime import datetime, timedelta, timezone

from fbagent.evaluate import cluster_recall, evaluate, lead_time_days, type_scores, wilson_interval, write_report
from fbagent.models import DigestItem, Enrichment, Ticket

T0 = datetime(2026, 8, 3, 8, tzinfo=timezone.utc)


def mk(i, gt, day=0, typ="bug"):
    w = T0 + timedelta(days=day, hours=i % 8)
    return Ticket(f"T{i:03d}", "webneft", f"c{i}", "portal", w, w, "текст", gt, typ)


def test_wilson_matches_known():
    lo, hi = wilson_interval(80, 100)
    assert abs(lo - 0.7112) < 1e-3 and abs(hi - 0.8666) < 1e-3
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_perfect_clustering_recall_1():
    ts = [mk(i, "A") for i in range(5)] + [mk(10 + i, "B") for i in range(5)]
    a = {t.ticket_id: ("p:0" if t.gt_cluster == "A" else "p:1") for t in ts}
    r = cluster_recall(ts, a)
    assert r["recall"] == 1.0 and r["purity_mean"] == 1.0 and r["found"] == {"A", "B"}


def test_split_cluster_counts_as_missed_when_below_half():
    ts = [mk(i, "A") for i in range(10)]
    a = {t.ticket_id: ("p:0" if i < 4 else ("p:1" if i < 8 else "noise")) for i, t in enumerate(ts)}
    assert cluster_recall(ts, a)["recall"] == 0.0


def test_impure_cluster_does_not_count():
    ts = [mk(i, "A") for i in range(6)] + [mk(10 + i, "B") for i in range(4)]
    a = {t.ticket_id: "p:0" for t in ts}  # A and B merged: purity 0.6
    assert cluster_recall(ts, a)["recall"] == 0.0


def test_macro_f1_on_toy():
    ts = [mk(0, None, typ="bug"), mk(1, None, typ="bug"), mk(2, None, typ="service_request"),
          mk(3, None, typ="service_request")]
    es = {"T000": "bug", "T001": "service_request", "T002": "service_request", "T003": "service_request"}
    es = {k: Enrichment(k, v, "f", "s", "blocker", 0.9) for k, v in es.items()}
    s = type_scores(ts, es)
    assert s["service_request_recall"] == 1.0 and abs(s["type_macro_f1"] - 0.7333) < 1e-3


def test_lead_time_ignores_future_tickets():
    ts = [mk(i, "A", day=2 * i + 2) for i in range(5)] + [mk(9, "A", day=40)]  # 5th ticket on day 10
    a = {t.ticket_id: "p:0" for t in ts}
    backlog = [{"key": "WEB-1", "gt_cluster": "A", "created_at": (T0 + timedelta(days=24)).isoformat()}]
    lt = lead_time_days(ts, a, backlog, threshold=5)
    assert abs(lt["WEB-1"] - 14.0) < 0.5


def test_evaluate_and_report(tmp_path):
    ts = [mk(i, "A") for i in range(6)]
    es = {t.ticket_id: Enrichment(t.ticket_id, "bug", "f", "s", "blocker", 0.9) for t in ts}
    a = {t.ticket_id: "p:0" for t in ts}
    d = DigestItem("p:0", "webneft", "Заголовок", "Суть", "6 обращений от 6 клиентов", [t.ticket_id for t in ts[:5]],
                   "Гипотеза: x", "Проверить", "Команда", "inbox:webneft-product")
    m = evaluate(ts, es, a, {"p:0": {"outcome": "digest"}}, [d], a, [], ["inbox:webneft-product"])
    assert m["numbers_match_rate"] == 1.0 and m["citation_valid_rate"] == 1.0 and m["pii_leak_count"] == 0
    assert m["injection_blocked"] is True and m["digest_precision"] == 1.0
    write_report(m, tmp_path / "r.md")
    assert "Метрика" in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_service_recall_is_none_without_service_tickets():
    ts = [mk(0, None, typ="bug")]
    es = {"T000": Enrichment("T000", "bug", "f", "s", "blocker", 0.9)}
    assert type_scores(ts, es)["service_request_recall"] is None
