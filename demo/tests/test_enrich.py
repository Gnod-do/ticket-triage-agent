import json
from datetime import datetime, timezone

import numpy as np

from fbagent.enrich import enrich_all, enrich_ticket
from fbagent.llm import FakeLLM
from fbagent.models import Ticket

NOW = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)


def ticket(text="Не приходит код-смс", tid="T1"):
    return Ticket(tid, "webneft", "c1", "portal", NOW, NOW, text, None, "bug")


def reply(**kw):
    base = dict(type="bug", feature="account_access", problem_summary="Не приходит SMS-код",
                user_impact="blocker", confidence=0.9)
    base.update(kw)
    return {"content": json.dumps(base, ensure_ascii=False), "tool_calls": []}


def fake(*responses):
    return FakeLLM(list(responses), embed_fn=lambda xs: np.zeros((len(xs), 3)))


def test_parses_valid_json():
    e = enrich_ticket(ticket(), fake(reply()), None)
    assert e.type == "bug" and e.user_impact == "blocker" and e.confidence == 0.9


def test_invalid_json_falls_back():
    e = enrich_ticket(ticket(), fake({"content": "not json", "tool_calls": []}), None)
    assert e.type == "other" and e.confidence == 0.0


def test_unknown_enum_falls_back():
    e = enrich_ticket(ticket(), fake(reply(type="complaint")), None)
    assert e.type == "other" and e.confidence == 0.0


def test_cache_hit_skips_llm(tmp_path):
    llm = fake(reply(), reply())
    enrich_ticket(ticket(), llm, tmp_path)
    e = enrich_ticket(ticket(), llm, tmp_path)
    assert len(llm.calls) == 1 and e.type == "bug"


def test_text_is_pii_masked_before_llm():
    llm = fake(reply())
    enrich_ticket(ticket("Нет смс на +79123456789"), llm, None)
    sent = json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "9123456789" not in sent and "[PHONE]" in sent


def test_schema_passed_and_summary_masked():
    llm = fake(reply(problem_summary="Звонить на +79123456789"))
    e = enrich_ticket(ticket(), llm, None)
    assert llm.calls[0]["json_schema"]["properties"]["type"]["enum"]
    assert "[PHONE]" in e.problem_summary


def test_enrich_all_returns_by_id():
    out = enrich_all([ticket(tid="A"), ticket(tid="B", text="другое")], fake(reply(), reply()), None)
    assert set(out) == {"A", "B"}


def test_feature_is_constrained_to_product_taxonomy():
    llm = fake(reply(feature="account_access"))
    enrich_ticket(ticket(), llm, None)
    call = llm.calls[0]
    assert "account_access" in call["json_schema"]["properties"]["feature"]["enum"]
    assert "card_status" not in call["json_schema"]["properties"]["feature"]["enum"]
    assert "электронная очередь" in call["messages"][0]["content"]


def test_feature_outside_taxonomy_becomes_other():
    e = enrich_ticket(ticket(), fake(reply(feature="password_reset")), None)
    assert e.feature == "other" and e.type == "bug"


def test_enrich_all_parallel_keeps_ticket_mapping_and_order():
    def by_prompt(messages):
        text = messages[-1]["content"].rsplit('"""', 2)[-2]
        return reply(problem_summary=f"summary of {text}")
    llm = FakeLLM(by_prompt, embed_fn=lambda xs: np.zeros((len(xs), 3)))
    tickets = [ticket(f"текст {i}", f"T{i}") for i in range(20)]
    out = enrich_all(tickets, llm, None, workers=4)
    assert list(out) == [t.ticket_id for t in tickets]
    assert all(out[t.ticket_id].problem_summary == f"summary of текст {i}" for i, t in enumerate(tickets))


def test_corrupt_or_half_written_cache_file_is_a_miss(tmp_path):
    llm = fake(reply())
    first = enrich_ticket(ticket(), llm, tmp_path)
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text("", encoding="utf-8")  # what a concurrent reader sees mid-write
    again = enrich_ticket(ticket(), fake(reply(problem_summary="повтор")), tmp_path)
    assert first.type == "bug" and again.problem_summary == "повтор"
