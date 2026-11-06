"""Deterministic synthetic ticket generator driven by seeds.yaml."""
from __future__ import annotations

import json
import random
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .models import Ticket

DEFAULT_START = datetime(2026, 8, 3, tzinfo=timezone.utc)  # a Monday
WORK_HOURS_UTC = range(6, 15)  # 09:00–18:00 MSK


def _rand_phone(rng: random.Random) -> str:
    fmt = rng.choice(["+7 ({a}) {b}-{c}-{d}", "8{a}{b}{c}{d}", "+7{a}{b}{c}{d}", "8 {a} {b} {c} {d}"])
    return fmt.format(a=rng.randint(900, 999), b=rng.randint(100, 999),
                      c=f"{rng.randint(0, 99):02d}", d=f"{rng.randint(0, 99):02d}")


def _fill(text: str, rng: random.Random, fillers: dict, when: datetime) -> str:
    return text.format(
        phone=_rand_phone(rng),
        inn=str(rng.randint(10**9, 10**10 - 1)),
        card=" ".join(str(rng.randint(1000, 9999)) for _ in range(4)),
        company=rng.choice(fillers["companies"]),
        car=rng.choice(fillers["cars"]),
        date=(when + timedelta(days=rng.randint(1, 5))).strftime("%d.%m.%Y"),
    )


def _work_time(rng: random.Random, start: datetime, week: int) -> datetime:
    day = start + timedelta(weeks=week, days=rng.randint(0, 4))
    return day.replace(hour=rng.choice(list(WORK_HOURS_UTC)), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def generate_tickets(seeds_path: Path, n_weeks: int = 12, seed: int = 42,
                     start: datetime = DEFAULT_START) -> list[Ticket]:
    cfg = yaml.safe_load(Path(seeds_path).read_text(encoding="utf-8"))
    rng = random.Random(seed)
    np_rng = __import__("numpy").random.default_rng(seed)
    fillers = cfg["fillers"]
    raw: list[dict] = []  # product, cluster, type, created, text

    for c in cfg["clusters"]:
        for week in range(n_weeks):
            for _ in range(int(np_rng.poisson(c["weekly_rate"][week]))):
                raw.append(dict(product=c["product_id"], cluster=c["id"], type=c["type"],
                                created=_work_time(rng, start, week), template=rng.choice(c["templates"])))

    sp = cfg["spike"]
    spike_cluster = next(c for c in cfg["clusters"] if c["id"] == sp["cluster"])
    spike_hour = (start + timedelta(weeks=sp["week"], days=sp["weekday"])).replace(hour=sp["hour_utc"])
    for _ in range(sp["count"]):
        raw.append(dict(product=spike_cluster["product_id"], cluster=spike_cluster["id"], type=spike_cluster["type"],
                        created=spike_hour + timedelta(minutes=rng.randint(0, 59)),
                        template=rng.choice(spike_cluster["templates"])))

    noise = cfg["noise"]
    for _ in range(noise["count"]):
        n = rng.choice(noise["templates"])
        raw.append(dict(product=n["product_id"], cluster=None, type=n["type"],
                        created=_work_time(rng, start, rng.randrange(n_weeks)), template=n["text"]))

    inj = cfg["injection"]
    inj_cluster = next(c for c in cfg["clusters"] if c["id"] == inj["cluster"])
    for _ in range(inj["count"]):
        raw.append(dict(product=inj_cluster["product_id"], cluster=inj_cluster["id"], type=inj_cluster["type"],
                        created=_work_time(rng, start, rng.randrange(n_weeks)),
                        template=rng.choice(inj_cluster["templates"]) + inj["suffix"]))

    raw.sort(key=lambda r: r["created"])
    tickets = []
    for i, r in enumerate(raw, start=1):
        text = _fill(r["template"], rng, fillers, r["created"])
        if rng.random() < fillers["contact_suffix_prob"]:
            text += _fill(fillers["contact_suffix"], rng, fillers, r["created"])
        channel = "call" if rng.random() < fillers["call_prob"] else "portal"
        if channel == "call":
            text = fillers["call_prefix"] + text
        tickets.append(Ticket(
            ticket_id=f"T{i:05d}",
            product_id=r["product"],
            customer_id=f"{r['product']}-c{rng.randint(1, 60):03d}",
            channel=channel,
            source_created_at=r["created"],
            ingested_at=r["created"] + timedelta(minutes=rng.randint(1, 30)),
            text=text,
            gt_cluster=r["cluster"],
            gt_type=r["type"],
        ))
    return tickets


def _to_json(t: Ticket) -> dict:
    d = asdict(t)
    d["source_created_at"] = t.source_created_at.isoformat()
    d["ingested_at"] = t.ingested_at.isoformat()
    return d


def save_jsonl(tickets: list[Ticket], path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for t in tickets:
            f.write(json.dumps(_to_json(t), ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[Ticket]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        d["source_created_at"] = datetime.fromisoformat(d["source_created_at"])
        d["ingested_at"] = datetime.fromisoformat(d["ingested_at"])
        out.append(Ticket(**d))
    return out
