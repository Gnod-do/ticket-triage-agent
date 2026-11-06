from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fbagent.agent import run_agent_for_cluster
from fbagent.llm import FakeLLM
from fbagent.models import Enrichment, Ticket
from fbagent.tools import ToolBox

MOCKS = Path(__file__).resolve().parents[1] / "data" / "mocks"
T0 = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
CID = "webneft:0"


@pytest.fixture
def box(tmp_path):
    ts, es, a = [], {}, {}
    for i in range(7):
        t = Ticket(f"T{i:04d}", "webneft", f"c{i}", "portal", T0 + timedelta(hours=i), T0 + timedelta(hours=i),
                   "Электронная очередь: ошибка 404 при бронировании", None, "bug")
        ts.append(t)
        es[t.ticket_id] = Enrichment(t.ticket_id, "bug", "electronic_queue", "Ошибка 404 в очереди", "blocker", 0.9)
        a[t.ticket_id] = CID
    backlog = tmp_path / "b.json"
    backlog.write_text((MOCKS / "backlog.json").read_text(encoding="utf-8"), encoding="utf-8")
    return ToolBox(ts, es, a, backlog, MOCKS / "owners.json", as_of=T0 + timedelta(days=3))


def call(name, **args):
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def final(text="Готово"):
    return {"content": text, "tool_calls": []}


DRAFT = {"title": "Ошибка 404 в электронной очереди", "summary": "Пользователи не могут записаться в очередь.",
         "scale_text": "7 обращений от 7 клиентов", "evidence": ["E1", "E2", "E3", "E4", "E5"],
         "hypothesis": "Гипотеза: недоступен сервис слотов", "action": "Проверить API бронирования",
         "channel": "inbox:webneft-product"}

READS = [call("get_cluster_stats", cluster_id=CID), call("get_cluster_examples", cluster_id=CID, k=5),
         call("get_cluster_history", cluster_id=CID), call("search_backlog", product_id="webneft", query="очередь 404"),
         call("get_product_owner", product_id="webneft", feature="electronic_queue")]


def test_happy_path_submits_digest(box):
    llm = FakeLLM(READS + [call("submit_digest_item", cluster_id=CID, draft=DRAFT), final()])
    r = run_agent_for_cluster(CID, box, llm)
    assert r["outcome"] == "digest" and r["calls"] == 6 and len(box.digests) == 1
    assert llm.calls[0]["tools"] and llm.calls[0]["messages"][0]["role"] == "system"


def test_existing_backlog_links(box):
    llm = FakeLLM(READS[:4] + [call("update_backlog_item", issue_key="WEB-412", comment="+7 обращений"), final()])
    r = run_agent_for_cluster(CID, box, llm)
    assert r["outcome"] == "linked" and box.digests == []


def test_budget_exceeded_goes_to_review(box):
    llm = FakeLLM([call("get_cluster_stats", cluster_id=CID) for _ in range(9)])
    r = run_agent_for_cluster(CID, box, llm, max_calls=8)
    assert r["outcome"] == "review" and r["calls"] == 8
    assert "лимит" in box.outcomes[CID]["reason"]


def test_unknown_tool_name_is_error_not_crash(box):
    llm = FakeLLM([call("drop_database"), call("label_cluster", cluster_id=CID, status="noise"), final()])
    r = run_agent_for_cluster(CID, box, llm)
    assert r["outcome"] == "labeled"
    assert "неизвестный инструмент" in r["trace"][0]["result"]["error"]


def test_injection_cannot_bypass_gate(box):
    bad = dict(DRAFT, channel="all@company.ru")
    llm = FakeLLM(READS[:2] + [call("submit_digest_item", cluster_id=CID, draft=bad), final("Отправлено всем")])
    r = run_agent_for_cluster(CID, box, llm)
    assert r["outcome"] == "review" and box.digests == []


def test_cannot_act_on_other_cluster(box):
    llm = FakeLLM([call("label_cluster", cluster_id="webneft:99", status="noise"), final()])
    r = run_agent_for_cluster(CID, box, llm)
    assert "webneft:99" not in box.outcomes and r["outcome"] == "review"


def test_no_tool_call_final_answer_without_action_is_review(box):
    r = run_agent_for_cluster(CID, box, FakeLLM([final("Думаю, всё в порядке")]))
    assert r["outcome"] == "review" and r["calls"] == 0


def test_string_arguments_are_parsed(box):
    llm = FakeLLM([{"content": "", "tool_calls": [{"function": {"name": "label_cluster",
                   "arguments": '{"cluster_id": "webneft:0", "status": "noise"}'}}]}, final()])
    assert run_agent_for_cluster(CID, box, llm)["outcome"] == "labeled"
