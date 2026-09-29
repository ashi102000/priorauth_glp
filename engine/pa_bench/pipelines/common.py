"""Shared, model-facing formatting used by BOTH pipelines (same policy view + same evidence profile)."""
from __future__ import annotations

import json
import re

from ..guard import assert_model_safe
from ..policies.evaluator import STATUSES

STATUS_DEFINITIONS = """Criterion status definitions (use exactly one):
- PASS: the evidence clearly shows the requirement is met.
- FAIL: the evidence clearly shows the requirement is NOT met (e.g., value below threshold, program declined or stopped, explicitly not following a plan).
- INSUFFICIENT: the required evidence is not documented. Missing documentation is NOT negative evidence, but it cannot support approval.
- CONFLICT: the evidence is genuinely contradictory or too ambiguous to resolve safely without human review."""

PA_STATE_RULE = """PA state rule:
- NOT_READY if any criterion is FAIL or INSUFFICIENT;
- otherwise REVIEW_REQUIRED if any criterion is CONFLICT;
- otherwise READY."""

_APPROVAL_TAG = re.compile(r"USER-APPROVED \(\d{4}-\d{2}-\d{2}\):\s*")


def policy_view(policy: dict) -> dict:
    """Model-facing normalized policy: requirements, verbatim payer text, parameters, interpretation rules."""
    view = {"policy_id": policy["policy_id"], "payer": policy["payer"], "drug": policy["drug"],
            "applicability": policy.get("applicability", ""), "decision_logic": policy["decision_logic"],
            "criteria": [{"criterion_id": c["criterion_id"], "requirement": c["description"],
                          "payer_text": c["source_quote"], "parameters": c["params"],
                          "interpretation_rules": _APPROVAL_TAG.sub("", c.get("interpretation_notes", "")).strip()}
                         for c in policy["criteria"]]}
    assert not re.search(r"GLP1-\d{3}", json.dumps(view)), "policy view must not reference specific patients"
    return view


def structured_view(profile: dict) -> dict:
    s = profile["structured"]
    return {
        "demographics": {"resource_id": f"Patient/{profile['patient_id']}", **s["demographics"]},
        "bmi_latest": s["bmi"]["latest"], "bmi_history": s["bmi"]["history"],
        "weight_history": s["weight"]["history"], "height": s["height"],
        "blood_pressure_latest": s["blood_pressure"]["latest"], "blood_pressure_history": s["blood_pressure"]["history"],
        "labs_latest": s["labs"], "conditions": s["conditions"],
        "medications": s["medications"], "requested_order": s["requested_order"],
    }


def evidence_view(profile: dict, criteria: list[str] | None = None) -> list[dict]:
    """Deduplicated, chronological note excerpts with the criteria each was retrieved for."""
    by_chunk: dict[str, dict] = {}
    for cid, items in profile["evidence"].items():
        if criteria is not None and cid not in criteria:
            continue
        for e in items:
            row = by_chunk.setdefault(e["chunk_id"], {"id": e["resource_id"], "chunk_id": e["chunk_id"], "date": e["date"],
                                                      "note_type": e["note_type"], "retrieved_for": [], "text": e["text"]})
            row["retrieved_for"].append(cid)
    return sorted(by_chunk.values(), key=lambda r: (r["date"], r["chunk_id"]))


def render_evidence(rows: list[dict]) -> str:
    return "\n\n".join(f"[{r['id']}] {r['date']} | {r['note_type']} | retrieved for: {', '.join(r['retrieved_for'])}\n{r['text'].strip()}"
                       for r in rows) or "(no note excerpts retrieved)"


def valid_evidence_ids(profile: dict) -> set[str]:
    ids = {e["resource_id"] for items in profile["evidence"].values() for e in items}
    s = profile["structured"]
    for key in ("conditions", "medications"):
        ids |= {r["resource_id"] for r in s[key]}
    for r in s["bmi"]["history"] + s["weight"]["history"] + s["blood_pressure"]["history"]:
        ids.add(r["resource_id"])
    if s["requested_order"]:
        ids.add(s["requested_order"]["resource_id"])
    ids.add(f"Patient/{profile['patient_id']}")
    return ids


def check_safe(*parts) -> None:
    for p in parts:
        assert_model_safe(p)


def status_enum() -> list[str]:
    return list(STATUSES)
