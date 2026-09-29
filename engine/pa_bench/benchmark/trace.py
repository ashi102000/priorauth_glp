"""Standardized trace logging. One JSONL line per model call; never contains API keys."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..evaluation.cost import load_pricing, record_cost

SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{10,}|api[_-]?key\s*[:=]\s*\S+)", re.I)


def _scrub(obj):
    if isinstance(obj, str):
        return SECRET.sub("[REDACTED]", obj)
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if "api_key" not in k.lower()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def trace_row(*, run_id: str, evaluation_id: str, pipeline: str, call: dict, criterion_id: str | None = None,
              result: str | None = None, confidence: float | None = None, evidence_ids: list[str] | None = None) -> dict:
    pricing = load_pricing()
    return _scrub({
        "run_id": run_id, "evaluation_id": evaluation_id, "pipeline": pipeline, "stage": call["stage"],
        "criterion_id": criterion_id, "provider": call["provider"], "model": call["model"],
        "input_tokens": call["input_tokens"], "cached_input_tokens": call["cached_input_tokens"],
        "output_tokens": call["output_tokens"], "reasoning_tokens": call["reasoning_tokens"],
        "latency_ms": call["latency_ms"], "total_latency_ms": call["total_latency_ms"], "attempts": call["attempts"],
        "estimated_cost_usd": record_cost(call, pricing), "pricing_version": pricing["pricing_version"],
        "result": result, "confidence": confidence, "probabilities": call.get("probabilities"),
        "evidence_ids": evidence_ids or [], "request_id": call.get("request_id"), "prompt_sha256": call["prompt_sha256"],
        "error": call.get("error"), "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    })


class TraceWriter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, row: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
