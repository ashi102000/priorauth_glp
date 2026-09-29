from datetime import date

import pytest

from pa_bench.policies.evaluator import (CONFLICT, FAIL, INSUFFICIENT, NOT_READY, PASS, READY, REVIEW_REQUIRED,
                                         aggregate, eval_age, eval_bmi, eval_indication)
from pa_bench.policies.loader import load_all, load_policy, policy_ids

BMI = {"bmi_primary": 30.0, "bmi_with_comorbidity": 27.0}


def test_all_policies_verified_and_loadable():
    assert len(policy_ids()) == 3
    for p in load_all():
        assert p["human_verification"]["status"] == "verified"


@pytest.mark.parametrize("bmi,comorb,expected", [
    (30.0, None, PASS), (29.99, PASS, PASS), (29.99, FAIL, FAIL), (29.95, None, INSUFFICIENT),
    (28.8, CONFLICT, CONFLICT), (27.0, PASS, PASS), (26.99, PASS, FAIL), (None, PASS, INSUFFICIENT), (42.3, FAIL, PASS),
])
def test_bmi_logic(bmi, comorb, expected):
    assert eval_bmi(bmi, comorb, BMI) == expected


def test_age_and_indication():
    assert eval_age(date(2008, 9, 2), date(2026, 9, 1), {"min_age": 18}) == FAIL
    assert eval_age(date(2008, 9, 1), date(2026, 9, 1), {"min_age": 18}) == PASS
    assert eval_age(None, date(2026, 9, 1), {"min_age": 18}) == INSUFFICIENT
    assert eval_indication("chronic_weight_management", {"required_indication": "chronic_weight_management"}) == PASS
    assert eval_indication(None, {"required_indication": "chronic_weight_management"}) == INSUFFICIENT


def _statuses(policy, **overrides):
    s = {c["criterion_id"]: PASS for c in policy["criteria"]}
    s.update(overrides)
    return s


def test_aggregation_rules():
    fep = load_policy("BCBS_FEP_WEGOVY_2026_07_01")
    assert aggregate(fep, _statuses(fep))["pa_state"] == READY
    r = aggregate(fep, _statuses(fep, no_concurrent_glp1=CONFLICT))
    assert r["pa_state"] == REVIEW_REQUIRED and r["review_reasons"] == ["no_concurrent_glp1"] and not r["binary_auto_ready"]
    r = aggregate(fep, _statuses(fep, bmi_threshold=FAIL, no_concurrent_glp1=CONFLICT))
    assert r["pa_state"] == NOT_READY and r["missing_requirements"] == ["bmi_threshold"]
    assert aggregate(fep, _statuses(fep, weight_management_program=INSUFFICIENT))["pa_state"] == NOT_READY


def test_aggregation_rejects_incomplete_or_invalid():
    uhc = load_policy("UHC_WEGOVY_P1114_22_2026_09_01")
    with pytest.raises(ValueError):
        aggregate(uhc, {"age": PASS})
    with pytest.raises(ValueError):
        aggregate(uhc, _statuses(uhc, age="MAYBE"))


def test_any_of_logic():
    pol = {"policy_id": "T", "decision_logic": {"all_of": ["a", {"any_of": ["b", "c"]}]}}
    assert aggregate(pol, {"a": PASS, "b": FAIL, "c": PASS})["pa_state"] == READY
    assert aggregate(pol, {"a": PASS, "b": FAIL, "c": FAIL})["pa_state"] == NOT_READY
