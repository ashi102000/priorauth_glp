"""GPT pipeline logic with a fake LLM (no API calls)."""
import json

import pytest

from pa_bench.config import request_date
from pa_bench.evaluation.cost import cost_usd
from pa_bench.guard import GroundTruthLeakError
from pa_bench.models.interfaces import CallRecord
from pa_bench.pipelines import gpt
from pa_bench.pipelines.common import policy_view, structured_view
from pa_bench.policies.loader import load_policy
from pa_bench.retrieval.profile import cached_profile

FEP = "BCBS_FEP_WEGOVY_2026_07_01"


class FakeLLM:
    provider, model = "openai", "gpt-6-sol"

    def __init__(self, statuses, drop=None, extra_ids=None):
        self.statuses, self.drop, self.extra_ids, self.seen = statuses, drop or [], extra_ids or [], None

    def generate(self, *, system, user, schema, schema_name, stage, max_output_tokens=4000):
        self.seen = {"system": system, "user": user, "schema": schema}
        crit = [{"criterion_id": k, "status": v, "confidence": 0.9, "evidence_ids": ["Patient/GLP1-038"] + self.extra_ids,
                 "rationale": "x"} for k, v in self.statuses.items() if k not in self.drop]
        parsed = {"criteria": crit, "pa_state": "READY", "missing_requirements": [], "review_reasons": [], "summary": "s"}
        return CallRecord(provider="openai", model="gpt-6-sol", stage=stage, input_tokens=4000, output_tokens=600,
                          latency_ms=10.0, total_latency_ms=10.0, attempts=1, output_text=json.dumps(parsed), parsed=parsed)


@pytest.fixture
def setup(client):
    pol = load_policy(FEP)
    return pol, cached_profile(client, "GLP1-038", pol, request_date())


def test_schema_enumerates_policy_criteria(setup):
    pol, prof = setup
    sch = gpt.output_schema([c["criterion_id"] for c in pol["criteria"]])
    assert sch["properties"]["criteria"]["items"]["properties"]["criterion_id"]["enum"] == [c["criterion_id"] for c in pol["criteria"]]
    assert sch["additionalProperties"] is False


def test_run_aggregates_with_shared_rule(setup):
    pol, prof = setup
    st = {c["criterion_id"]: "PASS" for c in pol["criteria"]}
    st["no_concurrent_glp1"] = "CONFLICT"
    res = gpt.run(prof, pol, FakeLLM(st))
    assert res["pa_state"] == "REVIEW_REQUIRED" and res["model_self_reported"]["pa_state"] == "READY"
    assert res["criteria"]["age"]["evidence_ids"] == ["Patient/GLP1-038"]


def test_missing_criteria_become_insufficient_and_bad_ids_dropped(setup):
    pol, prof = setup
    st = {c["criterion_id"]: "PASS" for c in pol["criteria"]}
    res = gpt.run(prof, pol, FakeLLM(st, drop=["weight_management_program"], extra_ids=["Patient.birthDate"]))
    assert res["criteria"]["weight_management_program"]["status"] == "INSUFFICIENT"
    assert res["pa_state"] == "NOT_READY"
    assert all("Patient.birthDate" not in c["evidence_ids"] for c in res["criteria"].values())
    assert any("missing from model output" in n for n in res["notes"])


def test_prompt_contents(setup):
    pol, prof = setup
    llm = FakeLLM({c["criterion_id"]: "PASS" for c in pol["criteria"]})
    gpt.run(prof, pol, llm)
    user = llm.seen["user"]
    assert "Patient/GLP1-038" in user and "NO dual therapy" in user and "USER-APPROVED" not in user
    assert structured_view(prof)["demographics"]["resource_id"] == "Patient/GLP1-038"
    assert "GLP1-0" not in json.dumps(policy_view(pol))


def test_leaky_profile_is_blocked_before_any_call(setup):
    pol, prof = setup
    bad = json.loads(json.dumps(prof))
    bad["structured"]["demographics"]["note"] = "benchmark_design says hard"
    llm = FakeLLM({})
    with pytest.raises(GroundTruthLeakError):
        gpt.run(bad, pol, llm)
    assert llm.seen is None


def test_cost_math_matches_pricing():
    assert cost_usd("gpt-6-sol", 4581, 0, 642) == pytest.approx(0.015582)
    assert cost_usd("gpt-6-sol", 200_000, 100_000, 0) == pytest.approx(0.2 + 0.02)          # short-context band
    assert cost_usd("gpt-6-sol", 1_000_000, 500_000, 0) == pytest.approx(2.0 + 0.2)        # > 272K: long-context band
    assert cost_usd("unknown-model", 10, 0, 10) is None
