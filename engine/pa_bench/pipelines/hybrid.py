"""Pipeline B — Jev + GPT hybrid.

  deterministic criteria (age, indication, BMI arithmetic)            -> code
  bounded semantic reads (one fan-out Jev request per case)           -> Jev
  composition: dates, durations, recency, conflicts, med reconciliation -> code (hybrid_rules)
  criteria with confidence < threshold                               -> ONE GPT call covering only those criteria
  PA state                                                            -> shared deterministic aggregator
  submission narrative (READY cases only by default)                 -> GPT
"""
from __future__ import annotations

import json
import os
import time
from datetime import date

from ..policies.evaluator import aggregate, eval_age, eval_indication
from . import gpt
from .common import check_safe, valid_evidence_ids
from .hybrid_questions import build_request
from .hybrid_rules import RULES, Answers, Ctx, comorbidity_from, needs_comorbidity, rule_bmi, with_confidence

PIPELINE = "hybrid"

NARRATIVE_SYSTEM = """You write prior-authorization submission narratives for a payer reviewer.
Use ONLY the criterion determinations and patient facts provided. Do not add facts. Cite evidence ids in brackets.
At most 150 words, plain clinical prose."""
NARRATIVE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["narrative"],
                    "properties": {"narrative": {"type": "string"}}}


def _code_summary(decision: dict) -> str:
    if decision["pa_state"] == "NOT_READY":
        return "Not ready for submission. Missing or failing requirements: " + ", ".join(decision["missing_requirements"]) + "."
    if decision["pa_state"] == "REVIEW_REQUIRED":
        return "Requires human review. Conflicting or ambiguous evidence for: " + ", ".join(decision["review_reasons"]) + "."
    return "All requirements met."


def run(profile: dict, policy: dict, jev, llm, *, threshold: float, narrative_mode: str | None = None,
        retrieval_latency_ms: float = 0.0, jev_record: dict | None = None, escalation_cache: dict | None = None) -> dict:
    narrative_mode = narrative_mode or os.environ.get("HYBRID_NARRATIVE", "ready_only")
    t_start = time.perf_counter()
    feats = profile["structured"]
    req_date = date.fromisoformat(profile["request"]["request_date"])
    crit = {c["criterion_id"]: c for c in policy["criteria"]}
    calls, notes = [], []
    lat = {"retrieval": round(retrieval_latency_ms, 1), "rules": 0.0, "jev": 0.0, "gpt": 0.0, "narrative": 0.0}

    # 1) Jev fan-out (skipped entirely if no semantic question is needed)
    t0 = time.perf_counter()
    bmi_params = crit["bmi_threshold"]["params"]
    need_comorb = needs_comorbidity(feats, bmi_params)
    state, questions, rows = build_request(profile, policy, need_comorbidity=need_comorb)
    lat["rules"] += (time.perf_counter() - t0) * 1000
    answers_raw = {}
    if questions:
        if jev_record is None:
            rec = jev.ask(state=state, questions=questions, stage="criterion_reads")
            jev_record = rec.to_dict()
        calls.append(jev_record)
        lat["jev"] = jev_record["latency_ms"]
        if jev_record.get("parsed") is None:
            notes.append(f"jev error: {jev_record.get('error')}")
        answers_raw = jev_record.get("parsed") or {}
    missing_q = [q for q in questions if q not in answers_raw]
    answers = Answers(answers_raw)

    # 2) code composition + confidence
    t0 = time.perf_counter()
    ctx = Ctx(rows=rows, request_date=req_date, features=feats)
    results = {}
    for cid, c in crit.items():
        if cid == "age":
            st = eval_age(date.fromisoformat(feats["demographics"]["birth_date"]), req_date, c["params"])
            results[cid] = {"status": st, "confidence": 1.0, "engine": "code", "evidence_ids": [f"Patient/{profile['patient_id']}"]}
        elif cid == "indication":
            st = eval_indication(profile["request"]["indication"], c["params"])
            results[cid] = {"status": st, "confidence": 1.0, "engine": "code", "evidence_ids": []}
        elif cid == "bmi_threshold":
            rule, keys = rule_bmi(ctx, c["params"])
            st, conf, decisive = with_confidence(rule, answers, keys)
            src = comorbidity_from(feats, answers)[1] if need_comorb else "structured"
            ev = [feats["bmi"]["latest"]["resource_id"]] if feats["bmi"]["latest"] else []
            ev += [x["resource_id"] for x in feats["weight_related_conditions"]]
            if src == "jev":
                ev += [rows[i]["resource_id"] for i in ctx.idx("comorbidity")]
            results[cid] = {"status": st, "confidence": conf, "engine": "jev" if src == "jev" else "code",
                            "decisive_answers": decisive, "evidence_ids": sorted(set(ev))}
        elif cid in RULES:
            rule, keys = RULES[cid](ctx, c)
            if any(k in missing_q for k in keys) or (keys and not answers_raw):
                st, conf, decisive = "INSUFFICIENT", 0.0, ["<jev answers missing>"]
            else:
                st, conf, decisive = with_confidence(rule, answers, keys)
            ev = sorted({rows[i]["resource_id"] for i in ctx.idx(cid)})
            if cid.startswith("no_concurrent"):
                ev += [m["resource_id"] for m in feats["anti_obesity_medications"]]
            results[cid] = {"status": st, "confidence": conf, "engine": "jev", "decisive_answers": decisive,
                            "evidence_ids": ev}
        else:
            results[cid] = {"status": "INSUFFICIENT", "confidence": 0.0, "engine": "jev", "evidence_ids": [],
                            "decisive_answers": ["<no rule>"]}
            notes.append(f"{cid}: no hybrid rule; routed to GPT")
    lat["rules"] += (time.perf_counter() - t0) * 1000

    # 3) confidence router -> single GPT escalation call for uncertain criteria
    escalate = sorted(cid for cid, r in results.items() if r["engine"] == "jev" and r["confidence"] < threshold)
    if escalate:
        key = ",".join(escalate)
        cached = (escalation_cache or {}).get(key)
        if cached is None:
            user = gpt.build_prompt(profile, policy, only=escalate)
            check_safe(gpt.SYSTEM, user)
            rec = llm.generate(system=gpt.SYSTEM, user=user, schema=gpt.output_schema(escalate),
                               schema_name="pa_escalation", stage="gpt_escalation")
            cached = rec.to_dict()
            if escalation_cache is not None:
                escalation_cache[key] = cached
        calls.append(cached)
        lat["gpt"] += cached["latency_ms"]
        valid = valid_evidence_ids(profile)
        got = {c["criterion_id"]: c for c in (cached.get("parsed") or {}).get("criteria", [])}
        for cid in escalate:
            r = results[cid]
            r["jev_status"], r["jev_confidence"] = r["status"], r["confidence"]
            if cid in got:
                g = got[cid]
                r.update({"status": g["status"], "confidence": g["confidence"], "engine": "gpt_escalation",
                          "evidence_ids": [i for i in g["evidence_ids"] if i in valid], "rationale": g["rationale"]})
            else:
                r.update({"status": "INSUFFICIENT", "engine": "gpt_escalation", "missing_from_output": True})
                notes.append(f"{cid}: missing from escalation output")
            r["escalated"] = True

    decision = aggregate(policy, {k: v["status"] for k, v in results.items()})

    # 4) narrative
    summary = _code_summary(decision)
    narrative_call = None
    if narrative_mode == "all" or (narrative_mode == "ready_only" and decision["pa_state"] == "READY"):
        payload = {"request": profile["request"], "policy_id": policy["policy_id"], "pa_state": decision["pa_state"],
                   "patient_facts": {"age": feats["demographics"]["age"], "bmi_latest": feats["bmi"]["latest"],
                                     "weight_related_conditions": feats["weight_related_conditions"]},
                   "criteria": {k: {"status": v["status"], "evidence_ids": v["evidence_ids"]} for k, v in results.items()},
                   "evidence_excerpts": [{"id": r["resource_id"], "date": r["date"], "text": r["text"]} for r in rows]}
        user = json.dumps(payload, ensure_ascii=False)
        check_safe(NARRATIVE_SYSTEM, user)
        rec = llm.generate(system=NARRATIVE_SYSTEM, user=user, schema=NARRATIVE_SCHEMA, schema_name="pa_narrative",
                           stage="narrative", max_output_tokens=1500)
        narrative_call = rec.to_dict()
        calls.append(narrative_call)
        lat["narrative"] = narrative_call["latency_ms"]
        if rec.parsed:
            summary = rec.parsed["narrative"]

    lat["decision_total"] = round(lat["retrieval"] + lat["rules"] + lat["jev"] + lat["gpt"], 1)
    lat["total"] = round(lat["decision_total"] + lat["narrative"], 1)
    lat["rules"] = round(lat["rules"], 2)
    lat["wall_clock"] = round(retrieval_latency_ms + (time.perf_counter() - t_start) * 1000, 1)
    return {
        "pipeline": PIPELINE, "patient_id": profile["patient_id"], "policy_id": policy["policy_id"], "threshold": threshold,
        "criteria": results, **decision, "summary": summary, "escalated_criteria": escalate,
        "jev_questions": len(questions), "calls": calls, "notes": notes, "latency_ms": lat,
        "jev_request": {"n_notes": len(rows), "note_ids": [r["chunk_id"] for r in rows]},
    }
