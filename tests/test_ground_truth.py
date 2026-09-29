"""Ground-truth integrity: completeness, internal consistency, and independent reproduction of the
code-evaluated criteria from the model-visible FHIR bundles."""
import json
from collections import Counter
from datetime import date

import pytest

from pa_bench.fhir.parser import observation_code, observation_value
from pa_bench.guard import find_leaks
from pa_bench.policies.evaluator import STATUSES, aggregate, eval_age
from pa_bench.policies.loader import load_policy


@pytest.fixture(scope="module")
def pa_truth(root):
    return json.loads((root / "ground_truth/pa_truth.json").read_text())["evaluations"]


@pytest.fixture(scope="module")
def crit_truth(root):
    return json.loads((root / "ground_truth/criterion_truth.json").read_text())["rows"]


def test_complete_grid(pa_truth, crit_truth):
    assert len(pa_truth) == 150
    assert len({r["evaluation_id"] for r in pa_truth}) == 150
    assert Counter(r["policy_id"] for r in pa_truth) == Counter({p: 50 for p in {r["policy_id"] for r in pa_truth}})
    per_eval = Counter(r["evaluation_id"] for r in crit_truth)
    for r in pa_truth:
        pol = load_policy(r["policy_id"])
        assert per_eval[r["evaluation_id"]] == len(pol["criteria"])


def test_statuses_valid_and_aggregation_consistent(pa_truth):
    for r in pa_truth:
        g = r["ground_truth"]
        statuses = {k: v["status"] for k, v in g["criteria"].items()}
        assert set(statuses.values()) <= set(STATUSES)
        expected = aggregate(load_policy(r["policy_id"]), statuses)
        assert g["pa_state"] == expected["pa_state"]
        assert g["binary_auto_ready"] == (g["pa_state"] == "READY")


def test_sanity_anchors(pa_truth):
    by = {(r["patient_id"], r["policy_id"].split("_")[0]): r["ground_truth"]["pa_state"] for r in pa_truth}
    for r in pa_truth:
        if r["difficulty"] == "easy_positive":
            assert r["ground_truth"]["pa_state"] == "READY", r["evaluation_id"]
        if r["difficulty"] == "easy_negative":
            assert r["ground_truth"]["pa_state"] == "NOT_READY", r["evaluation_id"]
    assert by[("GLP1-045", "BCBS")] == "REVIEW_REQUIRED"      # Zepbound fill after 'stopped'
    assert by[("GLP1-038", "BCBS")] == "READY"                # newer explicit note wins
    assert by[("GLP1-029", "AETNA")] == "READY"               # exactly 6 calendar months
    assert by[("GLP1-043", "UHC")] == "NOT_READY"             # negation
    assert by[("GLP1-040", "UHC")] == "NOT_READY"             # structured BMI 29.7 governs


def test_code_criteria_reproducible_from_fhir(client, crit_truth):
    """age and BMI labels must be derivable from the bundles alone (what the pipelines will see)."""
    request_date = date(2026, 9, 1)
    for r in crit_truth:
        pid, cid = r["patient_id"], r["criterion_id"]
        pol = load_policy(r["policy_id"])
        params = next(c["params"] for c in pol["criteria"] if c["criterion_id"] == cid)
        if cid == "age":
            birth = date.fromisoformat(client.read("Patient", pid)["birthDate"])
            assert eval_age(birth, request_date, params) == r["status"]
        if cid == "bmi_threshold":
            bmis = [o for o in client.search("Observation", patient=pid) if observation_code(o) == "39156-5"]
            latest = observation_value(max(bmis, key=lambda o: o["effectiveDateTime"]))
            assert f"Latest structured BMI {latest}" in r["rationale"]
            if latest >= params["bmi_primary"]:
                assert r["status"] == "PASS"
            elif latest < params["bmi_with_comorbidity"]:
                assert r["status"] == "FAIL"


def test_ground_truth_files_are_guarded(root):
    for f in ("pa_truth.json", "criterion_truth.json", "evidence_map.json"):
        text = (root / "ground_truth" / f).read_text()
        assert "EVALUATION ONLY" in text
        assert find_leaks(text), f"guard failed to flag {f}"
