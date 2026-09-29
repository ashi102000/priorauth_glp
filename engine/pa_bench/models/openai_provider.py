"""OpenAI Responses API provider with strict JSON-schema structured output."""
from __future__ import annotations

import hashlib
import json
import os
import time

from ..guard import assert_model_safe
from .interfaces import CallRecord

RETRYABLE = ("RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError")


class OpenAIProvider:
    provider = "openai"

    def __init__(self, model: str | None = None, reasoning_effort: str | None = None, max_retries: int = 4,
                 timeout_s: float = 180.0, client=None):
        from openai import OpenAI
        self.model = model or os.environ["OPENAI_MODEL"]
        self.reasoning_effort = reasoning_effort or os.environ.get("OPENAI_REASONING_EFFORT", "medium")
        self.max_retries = max_retries
        self.client = client or OpenAI(timeout=timeout_s, max_retries=0)   # retries handled here, so they are timed/logged

    def generate(self, *, system: str, user: str, schema: dict, schema_name: str, stage: str,
                 max_output_tokens: int = 4000) -> CallRecord:
        assert_model_safe({"system": system, "user": user})    # ground-truth isolation, every call
        rec = CallRecord(provider=self.provider, model=self.model, stage=stage,
                         prompt_sha256=hashlib.sha256((system + "\n\n" + user).encode()).hexdigest(),
                         extra={"reasoning_effort": self.reasoning_effort, "schema_name": schema_name})
        t_all = time.perf_counter()
        for attempt in range(1, self.max_retries + 1):
            rec.attempts = attempt
            t0 = time.perf_counter()
            try:
                resp = self.client.responses.create(
                    model=self.model, instructions=system, input=user, max_output_tokens=max_output_tokens,
                    reasoning={"effort": self.reasoning_effort},
                    text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
                )
                rec.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                u = resp.usage
                rec.input_tokens = u.input_tokens
                rec.output_tokens = u.output_tokens
                rec.cached_input_tokens = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
                rec.reasoning_tokens = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
                rec.request_id = getattr(resp, "_request_id", None) or resp.id
                rec.output_text = resp.output_text
                rec.extra["status"] = resp.status
                if resp.status != "completed":
                    rec.error = f"incomplete: {getattr(resp, 'incomplete_details', None)}"
                else:
                    rec.parsed = json.loads(resp.output_text)
                break
            except Exception as e:  # noqa: BLE001
                rec.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                name = type(e).__name__
                rec.error = f"{name}: {str(e)[:300]}"
                if name not in RETRYABLE or attempt == self.max_retries:
                    break
                time.sleep(min(2 ** attempt, 30))
        rec.total_latency_ms = round((time.perf_counter() - t_all) * 1000, 1)
        if rec.parsed is not None:
            rec.error = None
        return rec
