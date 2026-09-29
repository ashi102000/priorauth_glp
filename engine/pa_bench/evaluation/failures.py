"""Automatic failure categorization for incorrect criterion decisions (evaluation-only).

Primary category, first match wins:
  1 RETRIEVAL_FAILURE          evidence needed for the true status was not retrieved
                               (truth FAIL/CONFLICT: no CONTRADICTS/AMBIGUOUS doc retrieved while such docs exist;
                                truth PASS: no SUPPORTS doc retrieved while such docs exist)
  2 MISSING_NOT_NEGATIVE       truth INSUFFICIENT vs predicted FAIL or vice versa (absence vs. negative evidence)
  3 by criterion + challenge tag (TEMPORAL_REASONING, NEGATION, CONTRADICTION, MEDICATION_RECONCILIATION,
                               NUMERIC_BOUNDARY)
  4 POLICY_LOGIC               code-evaluated criterion wrong (deterministic logic / structured data)
  5 SEMANTIC_INTERPRETATION    default for model-evaluated criteria
  6 OTHER
Secondary flags: MODEL_OVERCONFIDENCE (wrong with confidence >= 0.9), MODEL_UNDERCONFIDENCE (right but
escalated/low-confidence), and escalation effect for hybrid escalations.
"""
from __future__ import annotations

TAG_CATEGORY = {
    "TEMPORAL_REASONING": {"duration_boundary", "infer_duration_from_dates", "noncontinuous_duration", "program_discontinuation",
                           "continuity", "temporality", "later_evidence_reversal", "duration_ambiguity", "vague_temporality",
                           "missing_temporality", "incomplete_longitudinal", "near_duration_threshold", "evidence_aggregation"},
    "NEGATION": {"negation", "retrieval_trap"},
    "CONTRADICTION": {"contradiction", "source_contradiction", "structured_narrative_conflict", "longitudinal_bmi_conflict",
                      "ambiguity"},
    "MEDICATION_RECONCILIATION": {"medication_reconciliation", "stale_medication", "missing_medication_evidence",
                                  "unknown_not_negative"},
    "NUMERIC_BOUNDARY": {"numeric_boundary", "near_bmi_30", "near_bmi_threshold", "just_below_bmi_27", "below_bmi_threshold",
                         "bmi_failure", "condition_ambiguity", "condition_status", "semantic_comorbidity",
                         "structured_data_omission"},
}
CRITERION_FAMILY = {
    "program_6_months": {"TEMPORAL_REASONING", "NEGATION", "CONTRADICTION"},
    "weight_management_program": {"TEMPORAL_REASONING", "NEGATION", "CONTRADICTION"},
    "lifestyle_adjunct": {"TEMPORAL_REASONING", "NEGATION", "CONTRADICTION"},
    "adjunct_diet_and_activity": {"TEMPORAL_REASONING", "NEGATION", "CONTRADICTION"},
    "no_concurrent_glp1": {"MEDICATION_RECONCILIATION", "CONTRADICTION"},
    "no_concurrent_pa_weight_loss_med": {"MEDICATION_RECONCILIATION", "CONTRADICTION"},
    "bmi_threshold": {"NUMERIC_BOUNDARY", "CONTRADICTION"},
}


def categorize(*, criterion_id: str, truth: str, pred: str, engine: str, confidence: float | None,
               challenge_tags: list[str], retrieval: dict | None) -> dict:
    primary = None
    if retrieval and retrieval.get("n_relevant"):
        if truth in ("FAIL", "CONFLICT") and retrieval.get("recall_contradicts") in (0, 0.0) and retrieval.get("recall_ambiguous") in (0, 0.0, None):
            primary = "RETRIEVAL_FAILURE"
        elif truth in ("FAIL", "CONFLICT") and retrieval.get("recall_contradicts") is None and retrieval.get("recall_ambiguous") in (0, 0.0):
            primary = "RETRIEVAL_FAILURE"
        elif truth == "PASS" and retrieval.get("recall_supports") in (0, 0.0):
            primary = "RETRIEVAL_FAILURE"
    if primary is None and {truth, pred} == {"INSUFFICIENT", "FAIL"}:
        primary = "MISSING_NOT_NEGATIVE"          # absence vs. negative evidence (checked before tag mapping)
    if primary is None:
        allowed = CRITERION_FAMILY.get(criterion_id, set())
        for cat, tags in TAG_CATEGORY.items():
            if cat in allowed and set(challenge_tags) & tags:
                primary = cat
                break
    if primary is None and {truth, pred} == {"INSUFFICIENT", "FAIL"}:
        primary = "MISSING_NOT_NEGATIVE"
    if primary is None:
        primary = "POLICY_LOGIC" if engine == "code" else ("SEMANTIC_INTERPRETATION" if engine else "OTHER")
    flags = []
    if confidence is not None and confidence >= 0.9:
        flags.append("MODEL_OVERCONFIDENCE")
    return {"failure_category": primary, "secondary_flags": flags}


def escalation_effect(jev_status: str | None, final_status: str, truth: str) -> str | None:
    if jev_status is None:
        return None
    jr, fr = jev_status == truth, final_status == truth
    return {(True, True): "both_correct", (False, True): "escalation_fixed", (True, False): "escalation_broke",
            (False, False): "both_wrong"}[(jr, fr)]
