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
