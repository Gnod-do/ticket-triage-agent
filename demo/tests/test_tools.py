import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fbagent.baseline import bm25_clusters
from fbagent.models import Enrichment, Ticket
from fbagent.tools import ToolBox

MOCKS = Path(__file__).resolve().parents[1] / "data" / "mocks"
T0 = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def mk(i, text, cluster="webneft:0", product="webneft", feature="account_access"):
    t = Ticket(f"T{i:04d}", product, f"c{i}", "portal", T0 + timedelta(hours=i), T0 + timedelta(hours=i), text,
               None, "bug")
    return t, Enrichment(t.ticket_id, "bug", feature, "Не приходит SMS-код", "blocker", 0.9), cluster


@pytest.fixture
def box(tmp_path):
    rows = [mk(i, f"Не приходит смс код восстановления пароля, вариант {i}. Тел +7912345678{i}") for i in range(9)]
    rows += [mk(20 + i, "Выгрузка УПД в Excel", "webneft:1", feature="documents") for i in range(5)]
    tickets = [r[0] for r in rows]
    backlog = tmp_path / "backlog.json"
    backlog.write_text((MOCKS / "backlog.json").read_text(encoding="utf-8"), encoding="utf-8")
    return ToolBox(tickets, {r[0].ticket_id: r[1] for r in rows}, {r[0].ticket_id: r[2] for r in rows},
                   backlog, MOCKS / "owners.json", as_of=T0 + timedelta(days=30))


def good_draft(box, n=9, channel="inbox:webneft-access"):
    refs = [e["ref"] for e in box.get_cluster_examples("webneft:0", k=5)["examples"]]
    return {"title": "Не приходит SMS-код", "summary": "Пользователи не получают SMS-код.",
            "scale_text": f"{n} обращений от 9 клиентов", "evidence": refs,
            "hypothesis": "Гипотеза: сбой доставки SMS", "action": "Проверить шлюз SMS", "channel": channel}


def test_examples_use_aliases_not_ids(box):
    ex = box.get_cluster_examples("webneft:0", k=5)["examples"]
    assert [e["ref"] for e in ex] == ["E1", "E2", "E3", "E4", "E5"]
    dump = json.dumps(ex, ensure_ascii=False)
    assert "T00" not in dump and "[PHONE]" in dump
    assert set(box.resolve_refs("webneft:0", ["E1", "E2"])) <= {f"T{i:04d}" for i in range(9)}


def test_stats_tool_matches_counts(box):
    s = box.get_cluster_stats("webneft:0")
    assert s["n_tickets"] == 9 and s["n_customers"] == 9 and s["top_features"][0] == "account_access"


def test_gate_rejects_wrong_count(box):
    r = box.submit_digest_item("webneft:0", good_draft(box, n=12))
    assert r["ok"] is False and any("число" in v for v in r["violations"])
    assert box.digests == []


def test_gate_rejects_pii_and_foreign_ref(box):
    d = good_draft(box)
    d["summary"] = "Позвоните клиенту +79123456789"
    d["evidence"] = d["evidence"][:4] + ["E99"]
    r = box.submit_digest_item("webneft:0", d)
    joined = " ".join(r["violations"])
    assert r["ok"] is False and "персональные" in joined and "E99" in joined


def test_gate_rejects_channel_not_allowlisted(box):
    r = box.submit_digest_item("webneft:0", good_draft(box, channel="all@company.ru"))
    assert r["ok"] is False and any("канал" in v for v in r["violations"])


def test_gate_requires_five_evidence(box):
    d = good_draft(box)
    d["evidence"] = d["evidence"][:3]
    assert box.submit_digest_item("webneft:0", d)["ok"] is False


def test_submit_records_outcome_only_when_gate_passes(box):
    r = box.submit_digest_item("webneft:0", good_draft(box))
    assert r["ok"] is True
    assert box.outcomes["webneft:0"]["outcome"] == "digest"
    item = box.digests[0]
    assert item.owner_team.startswith("Вебнефть") and all(i.startswith("T") for i in item.evidence_ids)


def test_update_backlog_only_comments(box):
    before = box.backlog_path.read_text(encoding="utf-8")
    box.current_cluster = "webneft:0"
    r = box.update_backlog_item("WEB-412", "+9 новых обращений за период")
    assert r["ok"] and box.outcomes["webneft:0"] == {"outcome": "linked", "issue_key": "WEB-412"}
    assert box.backlog_path.read_text(encoding="utf-8") == before
    assert box.update_backlog_item("NOPE-1", "x")["ok"] is False


def test_search_backlog_finds_sms_issue(box):
    hits = box.search_backlog("webneft", "не приходит смс код пароль")["issues"]
    assert hits and hits[0]["key"] == "WEB-412"
    assert box.search_backlog("fuel_cards", "смс код")["issues"] == [] or \
        all(h["key"].startswith("FC") for h in box.search_backlog("fuel_cards", "смс код")["issues"])


def test_owner_lookup_and_unknown(box):
    assert box.get_product_owner("webneft", "account_access")["channel"] == "inbox:webneft-access"
    assert box.get_product_owner("webneft", "documents")["channel"] == "inbox:webneft-product"
    assert box.get_product_owner("unknown_product", "x")["team"] is None


def test_label_and_review_record_outcomes(box):
    box.label_cluster("webneft:1", "service_request")
    box.request_human_review("webneft:0", "неясно")
    assert box.outcomes["webneft:1"]["outcome"] == "labeled"
    assert box.outcomes["webneft:0"]["outcome"] == "review"


def test_schemas_cover_all_tools(box):
    names = {s["function"]["name"] for s in box.schemas()}
    assert len(names) == 10 and "submit_digest_item" in names


def test_bm25_groups_paraphrases_sharing_terms():
    texts = ["Не приходит смс код для восстановления пароля"] * 2 + \
            ["Смс код восстановления пароля не приходит второй день", "Не приходит код смс пароль",
             "Кнопка далее не работает на втором шаге оферты", "Кнопка далее не нажимается в оферте",
             "Кнопка далее на шаге оферты не реагирует", "Не работает кнопка далее оферта"]
    ts = [Ticket(f"T{i}", "webneft", "c", "portal", T0 + timedelta(hours=i), T0 + timedelta(hours=i), x, None, "bug")
          for i, x in enumerate(texts)]
    a = bm25_clusters(ts, threshold=0.3)
    assert len({a[f"T{i}"] for i in range(4)}) == 1 and len({a[f"T{i}"] for i in range(4, 8)}) == 1
    assert a["T0"] != a["T4"] and a["T0"] != "noise"


def test_gate_allows_iso_week_labels(box):
    d = good_draft(box)
    d["scale_text"] = "9 обращений от 9 клиентов, динамика: рост (W36, 2026-W37)"
    assert box.submit_digest_item("webneft:0", d)["ok"] is True


def test_digest_blocked_when_backlog_issue_found(box):
    box.current_cluster = "webneft:0"
    assert box.search_backlog("webneft", "не приходит смс код пароль")["issues"]
    r = box.submit_digest_item("webneft:0", good_draft(box))
    assert r["ok"] is False and any("WEB-412" in v for v in r["violations"])


def test_weak_backlog_match_is_ignored(box):
    assert box.search_backlog("webneft", "пароль выгрузка отчёт документы")["issues"] == []


def test_long_query_still_matches_backlog(box):
    hits = box.search_backlog("fuel_cards", "автоматическая блокировка карт после изменения лимитов")["issues"]
    assert hits and hits[0]["key"] == "FC-118"
    assert box.search_backlog("fuel_cards", "отчёт расход топлива не совпадает")["issues"] == []
    assert box.search_backlog("fuel_cards", "установить лимиты по видам топлива")["issues"] == []


def test_examples_default_k_is_eight(box):
    assert len(box.get_cluster_examples("webneft:0")["examples"]) == 8
