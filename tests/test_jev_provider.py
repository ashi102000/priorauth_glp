"""Jev provider against a mocked HTTP transport (no network)."""
import json

import httpx
import pytest

from pa_bench.evaluation.cost import cost_usd
from pa_bench.guard import GroundTruthLeakError
from pa_bench.models import jev_provider as jp

RESP = {"model": "jev-1.13.0",
        "answers": {"a": {"type": "choice", "choice": "stopped", "probabilities": {"stopped": 0.9612, "currently_taking": 0.0388},
                          "confidence": 0.9224},
                    "b": {"type": "noul", "noul": 0.137}},
        "usage": {"input_tokens": 1810, "output_tokens": 302}}


def make(handler, **kw):
    kw.setdefault("api_key", "test-key")
    return jp.JevProvider(client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def test_request_shape_and_exact_probabilities(monkeypatch):
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=RESP, headers={"x-request-id": "r1"})

    jev = make(handler)
    rec = jev.ask(state={"notes": ["x"]}, questions={"a": jp.choice("Q?", {"stopped": None, "currently_taking": None}),
                                                     "b": jp.noul("Yes?")}, stage="t")
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone" and seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "jev-1.13.0" and seen["body"]["questions"]["b"] == {"type": "noul", "instructions": "Yes?"}
    assert rec.probabilities == {"a": {"stopped": 0.9612, "currently_taking": 0.0388}, "b": {"yes": 0.137}}
    assert rec.parsed == RESP["answers"] and json.loads(rec.output_text) == RESP
    assert (rec.input_tokens, rec.output_tokens, rec.request_id, rec.error) == (1810, 302, "r1", None)
    assert rec.extra["response_model"] == "jev-1.13.0"


def test_retries_on_429_and_529(monkeypatch):
    monkeypatch.setattr(jp.time, "sleep", lambda s: None)
    codes = iter([429, 529, 200])

    def handler(req):
        c = next(codes)
        return httpx.Response(c, json=RESP if c == 200 else {"error": "busy"}, headers={"retry-after": "1"})

    rec = make(handler).ask(state="s", questions={"a": jp.noul("q")}, stage="t")
    assert rec.attempts == 3 and rec.error is None and rec.parsed


def test_non_retryable_error_is_reported():
    rec = make(lambda req: httpx.Response(422, json={"detail": "bad question"})).ask(state="s", questions={"a": jp.noul("q")}, stage="t")
    assert rec.parsed is None and rec.error.startswith("HTTP 422") and rec.attempts == 1


def test_guard_blocks_before_network():
    called = []
    jev = make(lambda req: called.append(1) or httpx.Response(200, json=RESP))
    with pytest.raises(GroundTruthLeakError):
        jev.ask(state={"hint": "easy_positive"}, questions={"a": jp.noul("q")}, stage="t")
    assert not called


def test_missing_key_raises(monkeypatch):
    for k in ("JEV_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        jp.JevProvider(api_key=None)


def test_jev_pricing_input_only():
    assert cost_usd("jev-1.13.0", 1_000_000, 0, 500_000) == pytest.approx(0.042)
