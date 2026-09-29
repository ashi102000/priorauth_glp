"""Pipeline A — GPT baseline.

One structured call per PA case: GPT receives the normalized policy + the shared evidence profile and
evaluates every criterion. The PA state used for scoring is derived from GPT's criterion statuses with
the same deterministic aggregation used by the hybrid (so arms differ only in decision strategy);
GPT's self-reported pa_state is kept for a consistency metric.
"""
from __future__ import annotations

import json
import time

from ..policies.evaluator import PA_STATES, aggregate
from .common import (PA_STATE_RULE, STATUS_DEFINITIONS, check_safe, evidence_view, policy_view, render_evidence,
                     status_enum, structured_view, valid_evidence_ids)

PIPELINE = "gpt"

SYSTEM = f"""You are a meticulous prior-authorization clinical reviewer.
Evaluate a PA request against a payer policy using ONLY the patient evidence provided (structured data + retrieved note excerpts). Do not assume facts that are not documented.

{STATUS_DEFINITIONS}

{PA_STATE_RULE}

Guidance:
- Follow each criterion's payer text, parameters, and interpretation rules exactly.
- Structured values (age, BMI, dates) are authoritative as recorded; the requested order (status draft) is the drug under review and is not concurrent therapy.
- Relevance is not support: a note can discuss weight management yet contradict a criterion (e.g., declined, stopped, not enrolled).
- Pay attention to dates: start, stop, restart, and how recent each statement is relative to the request date.
- For every criterion, cite the ids (e.g., "DocumentReference/...", "MedicationRequest/...", "Observation/...") of the evidence you relied on.
- confidence is your probability (0-1) that the status you chose is correct.
- Keep each rationale to 1-2 sentences and the summary to at most 80 words."""


def output_schema(criterion_ids: list[str]) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["criteria", "pa_state", "missing_requirements", "review_reasons", "summary"],
        "properties": {
            "criteria": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["criterion_id", "status", "confidence", "evidence_ids", "rationale"],
                "properties": {"criterion_id": {"type": "string", "enum": criterion_ids},
                               "status": {"type": "string", "enum": status_enum()},
                               "confidence": {"type": "number"},
                               "evidence_ids": {"type": "array", "items": {"type": "string"}},
                               "rationale": {"type": "string"}}}},
            "pa_state": {"type": "string", "enum": list(PA_STATES)},
            "missing_requirements": {"type": "array", "items": {"type": "string"}},
            "review_reasons": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
    }


def build_prompt(profile: dict, policy: dict, only: list[str] | None = None) -> str:
    task = ("Evaluate every criterion in the policy and return the structured result." if not only else
            "Evaluate ONLY these criteria: " + ", ".join(only) + ". Return one entry per listed criterion; for pa_state, "
            "missing_requirements and review_reasons consider only the listed criteria.")
    return "\n\n".join([
        "## PA REQUEST\n" + json.dumps(profile["request"]),
        "## PAYER POLICY (normalized)\n" + json.dumps(policy_view(policy), indent=1),
        "## STRUCTURED PATIENT DATA (as of request date)\n" + json.dumps(structured_view(profile), separators=(",", ":")),
        "## RETRIEVED NOTE EXCERPTS (chronological)\n" + render_evidence(evidence_view(profile)),
        task,
    ])


def run(profile: dict, policy: dict, llm, *, retrieval_latency_ms: float = 0.0) -> dict:
    cids = [c["criterion_id"] for c in policy["criteria"]]
    user = build_prompt(profile, policy)
    check_safe(SYSTEM, user)
    t0 = time.perf_counter()
    rec = llm.generate(system=SYSTEM, user=user, schema=output_schema(cids), schema_name="pa_evaluation",
                       stage="criterion_evaluation")
    call = rec.to_dict()
    criteria, notes = {}, []
    if rec.parsed:
        valid_ids = valid_evidence_ids(profile)
        for c in rec.parsed["criteria"]:
            if c["criterion_id"] in criteria:
                notes.append(f"duplicate criterion {c['criterion_id']} (kept first)")
                continue
            ev = [i for i in c["evidence_ids"] if i in valid_ids]
            if len(ev) != len(c["evidence_ids"]):
                notes.append(f"{c['criterion_id']}: dropped {len(c['evidence_ids']) - len(ev)} unknown evidence ids")
            criteria[c["criterion_id"]] = {"status": c["status"], "confidence": c["confidence"], "evidence_ids": ev,
                                           "rationale": c["rationale"], "engine": "gpt"}
    for cid in cids:   # omitted criteria are treated as INSUFFICIENT (and flagged)
        if cid not in criteria:
            criteria[cid] = {"status": "INSUFFICIENT", "confidence": None, "evidence_ids": [], "rationale": "not returned by model",
                             "engine": "gpt", "missing_from_output": True}
            notes.append(f"{cid}: missing from model output")
    decision = aggregate(policy, {k: v["status"] for k, v in criteria.items()})
    total_ms = retrieval_latency_ms + (time.perf_counter() - t0) * 1000
    return {
        "pipeline": PIPELINE, "patient_id": profile["patient_id"], "policy_id": policy["policy_id"],
        "criteria": criteria, **decision,
        "model_self_reported": {k: rec.parsed[k] for k in ("pa_state", "missing_requirements", "review_reasons")} if rec.parsed else None,
        "summary": rec.parsed.get("summary") if rec.parsed else None,
        "calls": [call], "notes": notes, "error": rec.error,
        "latency_ms": {"retrieval": round(retrieval_latency_ms, 1), "rules": 0.0, "jev": 0.0,
                       "gpt": call["latency_ms"], "total": round(total_ms, 1)},
    }
