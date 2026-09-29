"""Trim a pipeline result to the shape the web app consumes (shared by the static export and the live API)."""
from __future__ import annotations

from ..evaluation.cost import record_cost

CRIT_KEYS = ("status", "confidence", "engine", "evidence_ids", "rationale", "jev_status", "jev_confidence", "escalated",
             "decisive_answers", "missing_from_output")


def trim_result(res: dict, source: str) -> dict:
    calls = [{"stage": c["stage"], "provider": c["provider"], "model": c["model"],
              "response_model": (c.get("extra") or {}).get("response_model"),
              "input_tokens": c["input_tokens"], "cached_input_tokens": c["cached_input_tokens"],
              "output_tokens": c["output_tokens"], "reasoning_tokens": c["reasoning_tokens"],
              "latency_ms": c["latency_ms"], "cost_usd": record_cost(c), "error": c.get("error")}
             for c in res.get("calls", [])]
    out = {"pipeline": res["pipeline"], "patient_id": res["patient_id"], "policy_id": res["policy_id"],
           "pa_state": res.get("pa_state"), "binary_auto_ready": res.get("binary_auto_ready"),
           "missing_requirements": res.get("missing_requirements", []), "review_reasons": res.get("review_reasons", []),
           "summary": res.get("summary"), "threshold": res.get("threshold"),
           "escalated_criteria": res.get("escalated_criteria", []),
           "criteria": {k: {kk: v[kk] for kk in CRIT_KEYS if kk in v} for k, v in (res.get("criteria") or {}).items()},
           "latency_ms": res.get("latency_ms"), "cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 8),
           "calls": calls, "source": source, "error": res.get("error")}
    jev = next((c for c in res.get("calls", []) if c["provider"] == "jev"), None)
    if jev:
        out["jev_reads"] = {"note_ids": (res.get("jev_request") or {}).get("note_ids", []), "answers": jev.get("parsed") or {}}
    return out
