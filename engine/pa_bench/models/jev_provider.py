"""Jev (TypeSafe System One) decision provider — raw HTTP client for POST /v1/systemone.

Contract (docs.typesafe.ai/api, read 2026-09-29):
  request  {"state": str|object|array, "model": str, "questions": {id: {"type": "noul"|"choice"|"score",
            "instructions": str|object|array, "criteria": ...}}}
  response {"model": versioned id, "answers": {id: noul{noul} | choice{choice, probabilities, confidence} |
            score{score, legend, probabilities, confidence}}, "usage": {input_tokens, output_tokens}}
  errors   401 auth, 422 validation, 429 rate limit, 529 overloaded (retry with backoff)
Answers — including every probability — are stored exactly as returned (raw JSON kept in the record).
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import httpx

from ..guard import assert_model_safe
from .interfaces import CallRecord

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.13.0"          # pinned versioned id (jev-latest alias pointed here on 2026-09-29)
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


def noul(instructions, true=None, false=None) -> dict:
    q = {"type": "noul", "instructions": instructions}
    if true is not None or false is not None:
        q["criteria"] = {k: v for k, v in (("true", true), ("false", false)) if v is not None}
    return q


def choice(instructions, options: dict) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def score(instructions, levels: list) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}


class JevProvider:
    provider = "jev"

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 max_retries: int = 5, timeout_s: float = 60.0, client: httpx.Client | None = None):
        self.model = model or os.environ.get("JEV_MODEL") or DEFAULT_MODEL
        self.base_url = (base_url or os.environ.get("JEV_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key = api_key or os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise RuntimeError("JEV_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.max_retries = max_retries
        self.http = client or httpx.Client(timeout=timeout_s)

    # ---------------------------------------------------------------- core call
    def ask(self, *, state, questions: dict[str, dict], stage: str) -> CallRecord:
        body = {"state": state, "model": self.model, "questions": questions}
        assert_model_safe(body)                                  # ground-truth isolation, every call
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
        rec = CallRecord(provider=self.provider, model=self.model, stage=stage,
                         prompt_sha256=hashlib.sha256(payload.encode()).hexdigest(),
                         extra={"n_questions": len(questions)})
        t_all = time.perf_counter()
        for attempt in range(1, self.max_retries + 1):
            rec.attempts = attempt
            t0 = time.perf_counter()
            try:
                r = self.http.post(f"{self.base_url}/v1/systemone", headers=self._headers, content=payload.encode())
                rec.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                if r.status_code in RETRY_STATUS and attempt < self.max_retries:
                    delay = float(r.headers.get("retry-after", 0) or 0) or min(2 ** attempt, 30)
                    rec.error = f"HTTP {r.status_code}"
                    time.sleep(delay)
                    continue
                rec.output_text = r.text
                if r.status_code != 200:
                    rec.error = f"HTTP {r.status_code}: {r.text[:300]}"
                    break
                data = r.json()
                rec.parsed = data["answers"]
                rec.extra["response_model"] = data.get("model")
                u = data.get("usage") or {}
                rec.input_tokens, rec.output_tokens = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
                rec.request_id = r.headers.get("x-request-id") or r.headers.get("request-id")
                rec.probabilities = {qid: (a.get("probabilities") if a["type"] != "noul" else {"yes": a["noul"]})
                                     for qid, a in data["answers"].items()}
                rec.error = None
                break
            except (httpx.TimeoutException, httpx.TransportError) as e:
                rec.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                rec.error = f"{type(e).__name__}: {e}"
                if attempt == self.max_retries:
                    break
                time.sleep(min(2 ** attempt, 30))
        rec.total_latency_ms = round((time.perf_counter() - t_all) * 1000, 1)
        return rec

    # ---------------------------------------------------------------- DecisionProvider convenience
    def binary_decision(self, *, question: str, context, stage: str, true: str | None = None, false: str | None = None) -> CallRecord:
        return self.ask(state=context, questions={"q": noul(question, true, false)}, stage=stage)

    def choice_decision(self, *, question: str, options: dict, context, stage: str) -> CallRecord:
        return self.ask(state=context, questions={"q": choice(question, options)}, stage=stage)

    def score_decision(self, *, question: str, levels: list, context, stage: str) -> CallRecord:
        return self.ask(state=context, questions={"q": score(question, levels)}, stage=stage)
