import pytest

from pa_bench.evaluation.failures import categorize, escalation_effect
from pa_bench.evaluation.metrics import binary, calibration, cluster_bootstrap_ci, mcnemar_exact, percentiles, prf


def test_prf_and_confusion():
    m = prf(["A", "A", "B", "C"], ["A", "B", "B", "C"], ("A", "B", "C"))
    assert m["accuracy"] == 0.75
    assert m["per_class"]["A"]["recall"] == 0.5 and m["per_class"]["B"]["precision"] == 0.5
    assert m["confusion"]["A"]["B"] == 1
    assert m["macro_f1"] == pytest.approx((2 / 3 + 2 / 3 + 1) / 3)


def test_binary_counts_false_auto_submissions():
    b = binary([True, False, False, True], [True, True, False, False])
    assert (b["tp"], b["fp"], b["fn"], b["tn"], b["false_auto_submissions"]) == (1, 1, 1, 1, 1)


def test_calibration_perfect_and_bins_report_n():
    c = calibration([0.95] * 20 + [0.55] * 20, [True] * 19 + [False] + [True] * 11 + [False] * 9)
    assert c["n"] == 40 and c["ece"] == pytest.approx(0.0)
    assert [b["n"] for b in c["bins"] if b["n"]] == [20, 20]
    assert calibration([1.0], [False])["brier"] == 1.0


def test_percentiles_linear():
    p = percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert p["p50"] == 5.5 and p["p90"] == pytest.approx(9.1) and p["max"] == 10


def test_mcnemar_exact():
    assert mcnemar_exact([True] * 5, [True] * 5)["p_value"] == 1.0
    r = mcnemar_exact([False] * 10 + [True], [True] * 10 + [False])
    assert (r["a_only_correct"], r["b_only_correct"]) == (1, 10) and r["p_value"] == pytest.approx(0.01171875)


def test_cluster_bootstrap_deterministic():
    rows = [{"patient_id": f"p{i % 10}", "x": i % 3 == 0} for i in range(60)]
    stat = lambda s: sum(r["x"] for r in s) / len(s)  # noqa: E731
    assert cluster_bootstrap_ci(rows, stat, reps=200) == cluster_bootstrap_ci(rows, stat, reps=200)


def test_categorize_priority():
    ret_miss = {"n_relevant": 2, "recall_contradicts": 0.0, "recall_ambiguous": None, "recall_supports": 1.0}
    assert categorize(criterion_id="program_6_months", truth="FAIL", pred="PASS", engine="jev", confidence=0.95,
                      challenge_tags=["negation"], retrieval=ret_miss)["failure_category"] == "RETRIEVAL_FAILURE"
    r = categorize(criterion_id="bmi_threshold", truth="FAIL", pred="INSUFFICIENT", engine="gpt", confidence=0.96,
                   challenge_tags=["numeric_boundary"], retrieval=None)
    assert r["failure_category"] == "MISSING_NOT_NEGATIVE" and r["secondary_flags"] == ["MODEL_OVERCONFIDENCE"]
    assert categorize(criterion_id="program_6_months", truth="CONFLICT", pred="FAIL", engine="gpt", confidence=0.5,
                      challenge_tags=["noncontinuous_duration"], retrieval=None)["failure_category"] == "TEMPORAL_REASONING"
    assert categorize(criterion_id="age", truth="PASS", pred="FAIL", engine="code", confidence=1.0,
                      challenge_tags=[], retrieval=None)["failure_category"] == "POLICY_LOGIC"


def test_escalation_effect():
    assert escalation_effect("PASS", "FAIL", "PASS") == "escalation_broke"
    assert escalation_effect("FAIL", "PASS", "PASS") == "escalation_fixed"
    assert escalation_effect(None, "PASS", "PASS") is None
