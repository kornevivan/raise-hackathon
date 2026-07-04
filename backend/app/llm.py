"""Thin Vultr Serverless Inference wrapper — the ONLY module that talks to the
inference API. Handles three-tier model routing, strict-JSON output with a
one-shot repair retry, prompt-hash caching, and a per-run call budget.

If no inference key is configured it routes each call to a deterministic offline
handler so the full agent pipeline (and the demo) runs without the network. Every
result records which backend produced it, surfaced in the UI trace.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass

from . import config

PRIME, CORE, FLASH = "prime", "core", "flash"
_MODEL = {PRIME: config.MODEL_PRIME, CORE: config.MODEL_CORE, FLASH: config.MODEL_FLASH}

_client = None
if config.LIVE:
    try:
        from openai import OpenAI
        _client = OpenAI(base_url=config.VULTR_BASE_URL, api_key=config.VULTR_INFERENCE_KEY,
                         timeout=config.LLM_TIMEOUT_S, max_retries=0)
    except Exception:
        _client = None


@dataclass
class LLMResult:
    data: dict
    tier: str
    model: str
    mode: str          # "vultr" | "offline"
    latency_ms: int
    raw: str = ""


class BudgetExceeded(RuntimeError):
    pass


class LLM:
    """One instance per run — tracks the call budget."""

    def __init__(self):
        self.calls = 0
        os.makedirs(config.CACHE_DIR, exist_ok=True)

    # -- caching -------------------------------------------------------------
    def _cache_path(self, model: str, payload: str) -> str:
        h = hashlib.sha256((model + payload).encode()).hexdigest()[:24]
        return os.path.join(config.CACHE_DIR, f"{model.replace('/', '_')}-{h}.json")

    # -- public --------------------------------------------------------------
    def json_call(self, *, tier: str, system: str, user: str, schema: dict,
                  offline_fn, few_shot: list[dict] | None = None) -> LLMResult:
        """Return structured JSON from the chosen tier. `offline_fn()` supplies the
        deterministic result when the inference key is absent (or a call fails)."""
        if self.calls >= config.MAX_LLM_CALLS:
            raise BudgetExceeded(f"exceeded {config.MAX_LLM_CALLS} LLM calls")
        self.calls += 1
        model = _MODEL[tier]

        if not config.LIVE or _client is None:
            t0 = time.time()
            data = offline_fn()
            return LLMResult(data=data, tier=tier, model=model, mode="offline",
                             latency_ms=int((time.time() - t0) * 1000))

        messages = [{"role": "system", "content": system + _schema_hint(schema)}]
        for ex in (few_shot or []):
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": json.dumps(ex["assistant"])})
        messages.append({"role": "user", "content": user})

        cache_key = self._cache_path(model, json.dumps(messages))
        if os.path.exists(cache_key):
            with open(cache_key) as fh:
                cached = json.load(fh)
            return LLMResult(data=cached["data"], tier=tier, model=model, mode="vultr",
                             latency_ms=cached.get("latency_ms", 0), raw=cached.get("raw", ""))

        t0 = time.time()
        try:
            raw = self._raw_chat(model, messages)
            data = _extract_json(raw)
            if data is None:  # one repair retry
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 "That was not valid JSON matching the schema. "
                                 "Reply with ONLY the corrected JSON object."})
                raw = self._raw_chat(model, messages)
                data = _extract_json(raw)
            if data is None:
                raise ValueError("model did not return valid JSON after repair")
        except Exception:
            # never let a flaky call break the demo — degrade to deterministic
            data = offline_fn()
            return LLMResult(data=data, tier=tier, model=model, mode="offline",
                             latency_ms=int((time.time() - t0) * 1000))

        latency = int((time.time() - t0) * 1000)
        with open(cache_key, "w") as fh:
            json.dump({"data": data, "raw": raw, "latency_ms": latency}, fh)
        return LLMResult(data=data, tier=tier, model=model, mode="vultr",
                         latency_ms=latency, raw=raw)

    def _raw_chat(self, model: str, messages: list[dict]) -> str:
        # Plain mode + explicit "ONLY JSON" instruction proved far more reliable than
        # the endpoint's json_object mode (which truncated some models mid-object).
        resp = _client.chat.completions.create(
            model=model, messages=messages, temperature=config.TEMPERATURE,
            max_tokens=1800)
        msg = resp.choices[0].message
        return msg.content or getattr(msg, "reasoning_content", "") or ""


def _schema_hint(schema: dict) -> str:
    return ("\n\nReturn ONLY a single JSON object, no prose, matching this schema:\n"
            + json.dumps(schema))


_THINK = None


def _extract_json(text: str) -> dict | None:
    import re
    global _THINK
    if _THINK is None:
        _THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
    text = (text or "").strip()
    text = _THINK.sub("", text)          # strip reasoning-model think blocks
    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None
