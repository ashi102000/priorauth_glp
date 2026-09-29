"""Disk cache for model calls, keyed by the exact request (model + settings + prompt/state + schema).

A cached CallRecord is returned verbatim (original usage, latency, request id), flagged extra.cache_hit=True,
so cost/latency still describe the computation that produced the answer. --force bypasses reads.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from ..models.interfaces import CallRecord

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)
CACHE_ROOT = ROOT / "results/cache"
_lock = threading.Lock()


def _key(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _load(path: Path) -> CallRecord | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    rec = CallRecord(**{k: v for k, v in d.items() if k in CallRecord.__dataclass_fields__})
    rec.extra = {**rec.extra, "cache_hit": True}
    return rec


def _store(path: Path, rec: CallRecord) -> None:
    if rec.parsed is None:          # never cache failures
        return
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec.to_dict(), ensure_ascii=False))


class CachedLLM:
    def __init__(self, inner, force: bool = False):
        self.inner, self.force = inner, force
        self.provider, self.model = inner.provider, inner.model

    def generate(self, *, system, user, schema, schema_name, stage, max_output_tokens=4000) -> CallRecord:
        k = _key({"model": self.model, "effort": getattr(self.inner, "reasoning_effort", None), "system": system,
                  "user": user, "schema": schema, "max_out": max_output_tokens})
        path = CACHE_ROOT / "openai" / k[:2] / f"{k}.json"
        if not self.force and (hit := _load(path)):
            hit.stage = stage
            return hit
        rec = self.inner.generate(system=system, user=user, schema=schema, schema_name=schema_name, stage=stage,
                                  max_output_tokens=max_output_tokens)
        rec.extra = {**rec.extra, "cache_hit": False}
        _store(path, rec)
        return rec


class CachedJev:
    def __init__(self, inner, force: bool = False):
        self.inner, self.force = inner, force
        self.provider, self.model = inner.provider, inner.model

    def ask(self, *, state, questions, stage) -> CallRecord:
        k = _key({"model": self.model, "state": state, "questions": questions})
        path = CACHE_ROOT / "jev" / k[:2] / f"{k}.json"
        if not self.force and (hit := _load(path)):
            hit.stage = stage
            return hit
        rec = self.inner.ask(state=state, questions=questions, stage=stage)
        rec.extra = {**rec.extra, "cache_hit": False}
        _store(path, rec)
        return rec
