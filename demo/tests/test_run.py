import json

from fbagent import run
from fbagent.llm import LLMUnavailable


def test_fake_end_to_end(tmp_path):
    out = tmp_path / "out"
    assert run.main(["--fake", "--out", str(out), "--cache", str(tmp_path / "cache")]) == 0
    for name in ("tickets.jsonl", "digest.md", "alerts.md", "eval_report.md", "finance.md", "tornado.png",
                 "run_meta.json"):
        assert (out / name).exists(), name
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "fake" and meta["metrics"]["pii_leak_count"] == 0
    assert meta["metrics"]["n_digests"] >= 1


def test_ollama_down_message(tmp_path, capsys, monkeypatch):
    class Down:
        model = "qwen3:8b"

        def __init__(self, *a, **k):
            pass

        def chat(self, *a, **k):
            raise LLMUnavailable("Ollama is not reachable")

        embed = chat

    monkeypatch.setattr(run, "OllamaClient", Down)
    code = run.main(["--out", str(tmp_path / "o"), "--cache", str(tmp_path / "c"), "--limit", "3"])
    assert code == 2 and "ollama pull qwen3:8b" in capsys.readouterr().err


def test_custom_seeds_file(tmp_path):
    from pathlib import Path
    seeds = Path(__file__).resolve().parents[1] / "data" / "holdout_seeds.yaml"
    out = tmp_path / "h"
    assert run.main(["--fake", "--seeds", str(seeds), "--out", str(out), "--cache", str(tmp_path / "c")]) == 0
    assert json.loads((out / "run_meta.json").read_text(encoding="utf-8"))["seeds"] == "holdout_seeds.yaml"
