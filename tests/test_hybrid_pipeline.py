"""Hybrid orchestrator with fake Jev / GPT (no network)."""
import json

import pytest

from pa_bench.config import request_date
from pa_bench.models.interfaces import CallRecord
from pa_bench.pipelines import hybrid
from pa_bench.pipelines.hybrid_questions import build_request
from pa_bench.pipelines.hybrid_rules import needs_comorbidity
from pa_bench.policies.loader import load_policy
from pa_bench.retrieval.profile import cached_profile

UHC = "UHC_WEGOVY_P1114_22_2026_09_01"


class FakeJev:
    provider, model = "jev", "jev-1.13.0"

    def __init__(self, event_conf):
        self.event_conf, self.calls = event_conf, 0

    def ask(self, *, state, questions, stage):
        self.calls += 1
        ans = {}
        for q, spec in questions.items():
            if spec["type"] == "noul":
                ans[q] = {"type": "noul", "noul": 0.97}
            elif q.startswith("event_"):
                p = self.event_conf
                ans[q] = {"type": "choice", "choice": "program_ongoing", "confidence": 2 * p - 1,
                          "probabilities": {"program_ongoing": p, "not_about_weight_management": round(1 - p, 6)}}
            else:
                k = next(iter(spec["criteria"]))
                ans[q] = {"type": "choice", "choice": k, "confidence": 1.0, "probabilities": {k: 1.0}}
        return CallRecord(provider="jev", model=self.model, stage=stage, input_tokens=2000, latency_ms=150.0,
                          total_latency_ms=150.0, attempts=1, parsed=ans, output_text=json.dumps({"answers": ans}))


class FakeLLM:
    provider, model = "openai", "gpt-6-sol"

    def __init__(self):
        self.stages = []

    def generate(self, *, system, user, schema, schema_name, stage, max_output_tokens=4000):
        self.stages.append(stage)
        if stage == "narrative":
            parsed = {"narrative": "Meets requirements [Patient/GLP1-001]."}
        else:
            ids = schema["properties"]["criteria"]["items"]["properties"]["criterion_id"]["enum"]
            parsed = {"criteria": [{"criterion_id": c, "status": "INSUFFICIENT", "confidence": 0.8, "evidence_ids": [],
                                    "rationale": "r"} for c in ids], "pa_state": "NOT_READY", "missing_requirements": [],
                      "review_reasons": [], "summary": "s"}
        return CallRecord(provider="openai", model=self.model, stage=stage, input_tokens=3000, output_tokens=300,
                          latency_ms=5000.0, total_latency_ms=5000.0, attempts=1, parsed=parsed, output_text=json.dumps(parsed))


@pytest.fixture
def case(client):
    pol = load_policy(UHC)
    return cached_profile(client, "GLP1-001", pol, request_date()), pol


def test_confident_case_no_escalation_and_ready_narrative(case):
    prof, pol = case
    llm = FakeLLM()
    res = hybrid.run(prof, pol, FakeJev(0.99), llm, threshold=0.9, narrative_mode="ready_only")
    assert res["pa_state"] == "READY" and res["escalated_criteria"] == []
    assert llm.stages == ["narrative"] and res["summary"].startswith("Meets")


def test_uncertain_criterion_escalates_once_and_uses_gpt_status(case):
    prof, pol = case
    llm = FakeLLM()
    res = hybrid.run(prof, pol, FakeJev(0.6), llm, threshold=0.9, narrative_mode="ready_only")
    assert res["escalated_criteria"] == ["lifestyle_adjunct"]
    c = res["criteria"]["lifestyle_adjunct"]
    assert c["engine"] == "gpt_escalation" and c["status"] == "INSUFFICIENT" and c["jev_status"] == "PASS"
    assert llm.stages == ["gpt_escalation"]                      # NOT_READY -> no narrative
    assert res["pa_state"] == "NOT_READY" and "not ready" in res["summary"].lower()


def test_lower_threshold_keeps_jev_answer(case):
    prof, pol = case
    res = hybrid.run(prof, pol, FakeJev(0.6), FakeLLM(), threshold=0.1, narrative_mode="none")
    assert res["escalated_criteria"] == [] and res["criteria"]["lifestyle_adjunct"]["engine"] == "jev"


def test_cached_jev_and_escalation_are_reused(case):
    prof, pol = case
    jev, llm, cache = FakeJev(0.6), FakeLLM(), {}
    first = hybrid.run(prof, pol, jev, llm, threshold=0.9, narrative_mode="none", escalation_cache=cache)
    again = hybrid.run(prof, pol, jev, llm, threshold=0.9, narrative_mode="none", escalation_cache=cache,
                       jev_record=first["calls"][0])
    assert jev.calls == 1 and llm.stages == ["gpt_escalation"]
    assert again["criteria"] == first["criteria"]


def test_code_only_when_no_semantic_questions(client):
    pol = load_policy(UHC)
    prof = cached_profile(client, "GLP1-011", pol, request_date())
    state, qs, rows = build_request(prof, pol, need_comorbidity=needs_comorbidity(prof["structured"], pol["criteria"][3]["params"]))
    assert qs  # UHC still reads lifestyle notes; BMI 24.8 is decided by code
    res = hybrid.run(prof, pol, FakeJev(0.99), FakeLLM(), threshold=0.9, narrative_mode="ready_only")
    assert res["criteria"]["bmi_threshold"] == {**res["criteria"]["bmi_threshold"], "status": "FAIL", "engine": "code"}
