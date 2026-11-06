"""Model access behind one small interface so tests never need a running model."""
from __future__ import annotations

from typing import Callable, Protocol

import httpx
import numpy as np


class LLMUnavailable(RuntimeError):
    """Raised when the local model server cannot be reached or a model is missing."""


class LLMClient(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             json_schema: dict | None = None) -> dict: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


class OllamaClient:
    def __init__(self, model: str = "qwen3:8b", embed_model: str = "bge-m3",
                 host: str = "http://localhost:11434", timeout: float = 600.0):
        self.model, self.embed_model, self.host = model, embed_model, host.rstrip("/")
        self._http = httpx.Client(timeout=timeout)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self._http.post(self.host + path, json=body)
        except httpx.TransportError as e:
            raise LLMUnavailable(f"Ollama is not reachable at {self.host}: {e}") from e
        if r.status_code == 404:
            raise LLMUnavailable(f"Model not found: {body.get('model')} — run `ollama pull {body.get('model')}`")
        r.raise_for_status()
        return r.json()

    def chat(self, messages, tools=None, json_schema=None):
        body = {"model": self.model, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": 0}}
        if tools:
            body["tools"] = tools
        if json_schema:
            body["format"] = json_schema
        data = self._post("/api/chat", body)
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += data.get("prompt_eval_count", 0)
        self.usage["completion_tokens"] += data.get("eval_count", 0)
        msg = data.get("message", {})
        return {"content": msg.get("content", ""), "tool_calls": msg.get("tool_calls") or []}

    def embed(self, texts):
        data = self._post("/api/embed", {"model": self.embed_model, "input": texts})
        return np.asarray(data["embeddings"], dtype=np.float32)


class FakeLLM:
    """Scripted stand-in: returns queued chat responses in order and records every call."""

    model = "fake"

    def __init__(self, chat_responses: list[dict] | Callable[[list[dict]], dict],
                 embed_fn: Callable[[list[str]], np.ndarray] | None = None):
        self._responses = chat_responses
        self._embed_fn = embed_fn or (lambda xs: np.zeros((len(xs), 8), dtype=np.float32))
        self.calls: list[dict] = []
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def chat(self, messages, tools=None, json_schema=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "json_schema": json_schema})
        self.usage["calls"] += 1
        if callable(self._responses):
            return self._responses(messages)
        if not self._responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self._responses.pop(0)

    def embed(self, texts):
        return np.asarray(self._embed_fn(list(texts)), dtype=np.float32)
