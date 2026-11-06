import re
from collections import Counter
from pathlib import Path

import pytest

from fbagent.data_gen import generate_tickets, load_jsonl, save_jsonl

SEEDS = Path(__file__).resolve().parents[1] / "data" / "seeds.yaml"


def gen(seed=42):
    return generate_tickets(SEEDS, seed=seed)


@pytest.fixture(scope="module")
def tickets():
    return gen()


def test_volume_and_labels(tickets):
    assert 300 <= len(tickets) <= 500
    assert all(t.gt_type for t in tickets)


def test_deterministic():
    assert [t.text for t in gen(seed=1)] == [t.text for t in gen(seed=1)]


def test_spike_injected(tickets):
    hours = Counter(
        t.source_created_at.replace(minute=0, second=0, microsecond=0)
        for t in tickets
        if t.gt_cluster == "webneft_queue_404"
    )
    assert max(hours.values()) >= 12


def test_injection_and_pii_present(tickets):
    assert sum("Игнорируй предыдущие инструкции" in t.text for t in tickets) >= 3
    phone = re.compile(r"(\+7|8)[\s(-]*\d{3}")
    assert sum(bool(phone.search(t.text)) for t in tickets) >= 10


def test_ingested_after_created(tickets):
    assert all(t.ingested_at >= t.source_created_at for t in tickets)


def test_two_products(tickets):
    assert {t.product_id for t in tickets} == {"webneft", "fuel_cards"}


def test_noise_has_no_cluster(tickets):
    noise = [t for t in tickets if t.gt_cluster is None]
    assert len(noise) >= 30
    assert {t.gt_type for t in noise} <= {"service_request", "consultation"}


def test_jsonl_roundtrip(tmp_path, tickets):
    p = tmp_path / "t.jsonl"
    save_jsonl(tickets, p)
    assert load_jsonl(p) == tickets
