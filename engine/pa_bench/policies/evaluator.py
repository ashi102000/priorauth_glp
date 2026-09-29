"""Deterministic policy evaluation: code-evaluated criteria + PA-state aggregation.

Criterion statuses:
  PASS          clearly met
  FAIL          clearly not met
  INSUFFICIENT  required evidence not documented (missing is not negative, but cannot auto-submit)
  CONFLICT      genuinely contradictory / unsafe to resolve automatically

PA state (user-approved rule, DECISIONS.md):
  NOT_READY        if any required criterion is FAIL or INSUFFICIENT
  REVIEW_REQUIRED  else if any is CONFLICT
  READY            else
Binary auto-submission: READY -> True, otherwise False.
"""
from __future__ import annotations

from datetime import date

from ..calc import age_on

PASS, FAIL, INSUFFICIENT, CONFLICT = "PASS", "FAIL", "INSUFFICIENT", "CONFLICT"
STATUSES = (PASS, FAIL, INSUFFICIENT, CONFLICT)
READY, NOT_READY, REVIEW_REQUIRED = "READY", "NOT_READY", "REVIEW_REQUIRED"
PA_STATES = (READY, NOT_READY, REVIEW_REQUIRED)


# ---------------------------------------------------------------- code-evaluated criteria

def eval_age(birth_date: date | None, request_date: date, params: dict) -> str:
    if birth_date is None:
        return INSUFFICIENT
    return PASS if age_on(birth_date, request_date) >= params["min_age"] else FAIL


def eval_indication(request_indication: str | None, params: dict) -> str:
    if not request_indication:
        return INSUFFICIENT
    return PASS if request_indication == params["required_indication"] else FAIL


def eval_bmi(latest_bmi: float | None, comorbidity: str | None, params: dict) -> str:
    """latest_bmi: latest recorded structured BMI. comorbidity: status of 'has a qualifying weight-related
    comorbidity' (PASS present / FAIL absent / INSUFFICIENT unknown / CONFLICT ambiguous), only consulted
    when bmi_with_comorbidity <= BMI < bmi_primary."""
    if latest_bmi is None:
        return INSUFFICIENT
    if latest_bmi >= params["bmi_primary"]:
        return PASS
    if latest_bmi < params["bmi_with_comorbidity"]:
        return FAIL
    if comorbidity in STATUSES:
        return comorbidity
    return INSUFFICIENT


# ---------------------------------------------------------------- aggregation

def _flatten(logic) -> list[str]:
    if isinstance(logic, str):
        return [logic]
    key = "all_of" if "all_of" in logic else "any_of"
    return [cid for item in logic[key] for cid in _flatten(item)]


def _combine(logic, statuses: dict[str, str]) -> str:
    if isinstance(logic, str):
        return statuses[logic]
    if "all_of" in logic:
        parts = [_combine(x, statuses) for x in logic["all_of"]]
        for s in (FAIL, INSUFFICIENT, CONFLICT):
            if s in parts:
                return s
        return PASS
    parts = [_combine(x, statuses) for x in logic["any_of"]]
    if PASS in parts:
        return PASS
    for s in (CONFLICT, INSUFFICIENT):
        if s in parts:
            return s
    return FAIL


def aggregate(policy: dict, statuses: dict[str, str]) -> dict:
    """Combine per-criterion statuses into a PA decision."""
    required = _flatten(policy["decision_logic"])
    missing = [c for c in required if c not in statuses]
    if missing:
        raise ValueError(f"missing criterion statuses: {missing}")
    bad = {c: s for c, s in statuses.items() if s not in STATUSES}
    if bad:
        raise ValueError(f"invalid statuses: {bad}")
    overall = _combine(policy["decision_logic"], statuses)   # any_of branches can rescue individual failures
    state = {PASS: READY, CONFLICT: REVIEW_REQUIRED}.get(overall, NOT_READY)
    fails = [c for c in required if statuses[c] in (FAIL, INSUFFICIENT)] if state == NOT_READY else []
    conflicts = [c for c in required if statuses[c] == CONFLICT] if state != READY else []
    return {
        "pa_state": state,
        "binary_auto_ready": state == READY,
        "missing_requirements": sorted(fails),
        "review_reasons": sorted(conflicts),
    }
