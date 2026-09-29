"""Ground-truth isolation. The most important safeguard in the benchmark.

1. Model-visible data (FHIR bundles, notes) contains no answer-key vocabulary.
2. The guard rejects payloads that contain ground-truth content.
3. Model-facing code never references hidden directories.
"""
import json
from pathlib import Path

import pytest

from pa_bench.guard import GroundTruthLeakError, assert_model_safe, find_leaks

STANCE_LABELS = ("SUPPORTS", "CONTRADICTS", "AMBIGUOUS", "NEUTRAL")
MODEL_FACING_PACKAGES = ("fhir", "retrieval", "models", "pipelines")


def model_visible_files(root: Path):
    yield from sorted((root / "data/fhir/bundles").glob("*.json"))
    yield from sorted((root / "data/notes").glob("*.json"))


def test_model_visible_data_has_no_leaks(root):
    offenders = {}
    for f in model_visible_files(root):
        hits = find_leaks(f.read_text())
        if hits:
            offenders[f.name] = hits
    assert not offenders, offenders


def test_model_visible_data_has_no_stance_labels(root):
    for f in model_visible_files(root):
        text = f.read_text()
        for s in STANCE_LABELS:
            assert s not in text, f"{f.name} contains {s}"


def test_bundle_tags_are_neutral(root):
    for f in sorted((root / "data/fhir/bundles").glob("*.json")):
        for e in json.loads(f.read_text())["entry"]:
            assert e["resource"]["meta"]["tag"] == [
                {"system": "urn:jev-pa-benchmark", "code": "GLP1_PA_COHORT_V1", "display": "GLP-1 PA benchmark cohort v1"}]


def test_no_cohort_truth_values_serialized_into_bundles(root, spec):
    """No spec record, evidence annotation, or plan-only field appears verbatim in a bundle."""
    plan_only = ("facts_to_express", "must_not_say", '"role"', '"trap"', "generator_notes")
    for f in sorted((root / "data/fhir/bundles").glob("*.json")):
        text = f.read_text()
        for key in plan_only:
            assert key not in text, f"{f.name} contains plan-only field {key}"


@pytest.mark.parametrize("payload", [
    {"patient": "GLP1-017", "benchmark_design": {"class": "hard"}},
    "Hint: this is an easy_positive case",
    "documentation_state=negated_structured_program",
    {"evaluation_id": "GLP1-038__BCBS_FEP_WEGOVY_2026_02_13"},
    "see ground_truth/pa_truth.json",
    "retrieval_trap in note 3",
    {"facts_to_express": ["x"]},
])
def test_guard_rejects_leaky_payloads(payload):
    with pytest.raises(GroundTruthLeakError):
        assert_model_safe(payload)


def test_guard_matches_whole_identifiers_only():
    assert find_leaks({"min_duration_months": 6}) == []
    assert find_leaks({"duration_months": 6}) == ["duration_months"]


def test_guard_accepts_every_model_prompt(root, client):
    """Every GPT prompt the benchmark can build (50 patients x 3 policies) passes the guard."""
    from pa_bench.config import request_date
    from pa_bench.pipelines import gpt
    from pa_bench.policies.loader import load_all
    from pa_bench.retrieval.profile import cached_profile
    for pol in load_all():
        for pid in client.patient_ids():
            assert_model_safe({"system": gpt.SYSTEM, "user": gpt.build_prompt(cached_profile(client, pid, pol, request_date()), pol)})


def test_guard_accepts_real_evidence_payload(root, client):
    """A realistic prompt built from model-visible data (incl. answer-space words) passes the guard."""
    from pa_bench.fhir.parser import document_text
    docs = client.search("DocumentReference", patient="GLP1-043")
    prompt = {"instructions": "Answer PASS, FAIL, or UNKNOWN. Stance options: SUPPORTS / CONTRADICTS / AMBIGUOUS.",
              "evidence": [{"id": d["id"], "text": document_text(d)} for d in docs]}
    assert_model_safe(prompt)


def test_model_facing_code_never_references_hidden_paths(root):
    hidden = ("ground_truth", "_generation", "patients.json", "evidence_map", "pa_truth", "criterion_truth")
    for pkg in MODEL_FACING_PACKAGES:
        for py in (root / "engine/pa_bench" / pkg).rglob("*.py"):
            src = py.read_text()
            for h in hidden:
                assert h not in src, f"{py.relative_to(root)} references hidden path/term '{h}'"


def test_web_workbench_data_has_no_ground_truth(root):
    """Files the Workbench/Patients views ship to the browser must not carry answer-key content;
    ground truth lives only in web/server-data (reveal API)."""
    web = root / "web/public/data"
    if not web.exists():
        pytest.skip("web export not generated")
    files = [web / "policies.json", web / "patients.json", web / "live_cases.json"]
    files += sorted((web / "patients").glob("*.json")) + sorted((web / "cases").glob("*.json"))
    ui_fields = {"evaluation_id", "binary_auto_ready"}   # structural ids / pipeline predictions, not answer keys
    for f in files:
        leaks = [x for x in find_leaks(f.read_text()) if x not in ui_fields]
        assert not leaks, f"{f.relative_to(root)} leaks {leaks}"
        assert "rationale\":\"Latest structured BMI" not in f.read_text()          # truth rationales never exported here
    assert (root / "web/server-data/truth.json").exists()
    assert not list((root / "web/pyengine").rglob("patients.json")) and not (root / "web/pyengine/pa_bench/generation").exists()
