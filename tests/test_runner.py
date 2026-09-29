"""Checkpoint/resume and call-cache behaviour (fake models, temp dirs)."""
import json

import pytest

import pa_bench.benchmark.cache as cache_mod
from pa_bench.benchmark.cache import CachedJev, CachedLLM
from pa_bench.benchmark.manifest import build_manifest, write_manifest
from pa_bench.benchmark.runner import Runner, completed_ids
from pa_bench.models.interfaces import CallRecord
from pa_bench.policies.loader import load_policy

UHC = "UHC_WEGOVY_P1114_22_2026_09_01"


class CountingLLM:
    provider, model, reasoning_effort = "openai", "gpt-6-sol", "medium"

    def __init__(self):
        self.n = 0

    def generate(self, *, system, user, schema, schema_name, stage, max_output_tokens=4000):
        self.n += 1
        ids = schema["properties"]["criteria"]["items"]["properties"]["criterion_id"]["enum"]
        parsed = {"criteria": [{"criterion_id": c, "status": "PASS", "confidence": 0.9, "evidence_ids": [], "rationale": "r"}
                               for c in ids], "pa_state": "READY", "missing_requirements": [], "review_reasons": [], "summary": "s"}
        return CallRecord(provider="openai", model=self.model, stage=stage, input_tokens=4000, output_tokens=500,
                          latency_ms=1.0, total_latency_ms=1.0, attempts=1, parsed=parsed, output_text=json.dumps(parsed))


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", tmp_path / "cache")
    return tmp_path


def test_resume_skips_completed_and_cache_serves_repeats(tmp_cache):
    pol = load_policy(UHC)
    jobs = [("GLP1-001", pol), ("GLP1-002", pol)]
    inner = CountingLLM()
    run_dir = tmp_cache / "run"
    r = Runner(run_dir, "gpt", CachedLLM(inner), concurrency=1)
    r.run(jobs[:1], "R1")
    assert completed_ids(run_dir) == {f"GLP1-001__{UHC}"} and inner.n == 1
    r.run(jobs, "R1")                                  # resume: only the missing evaluation runs
    assert inner.n == 2 and len((run_dir / "results.jsonl").read_text().splitlines()) == 2
    r2 = Runner(tmp_cache / "run2", "gpt", CachedLLM(inner), concurrency=1)
    r2.run(jobs, "R2")                                 # new run, identical prompts -> served from cache
    assert inner.n == 2
    rows = [json.loads(line) for line in (tmp_cache / "run2/results.jsonl").read_text().splitlines()]
    assert all(row["calls"][0]["extra"]["cache_hit"] for row in rows)
    assert all(row["cost_usd"] > 0 for row in rows)   # cost reflects the original computation
    Runner(tmp_cache / "run3", "gpt", CachedLLM(inner, force=True), concurrency=1).run(jobs[:1], "R3", force=True)
    assert inner.n == 3                                # --force bypasses the cache


def test_failures_are_not_cached(tmp_cache):
    class Failing(CountingLLM):
        def generate(self, **kw):
            self.n += 1
            return CallRecord(provider="openai", model=self.model, stage=kw["stage"], error="boom")
    inner = Failing()
    llm = CachedLLM(inner)
    for _ in range(2):
        llm.generate(system="s", user="u", schema={}, schema_name="x", stage="t")
    assert inner.n == 2


def test_jev_cache_keyed_by_request(tmp_cache):
    calls = []

    class J:
        provider, model = "jev", "jev-1.13.0"

        def ask(self, *, state, questions, stage):
            calls.append(1)
            return CallRecord(provider="jev", model=self.model, stage=stage, parsed={"q": {"type": "noul", "noul": 0.9}})
    j = CachedJev(J())
    j.ask(state={"a": 1}, questions={"q": {"type": "noul", "instructions": "x"}}, stage="s")
    j.ask(state={"a": 1}, questions={"q": {"type": "noul", "instructions": "x"}}, stage="s")
    j.ask(state={"a": 2}, questions={"q": {"type": "noul", "instructions": "x"}}, stage="s")
    assert len(calls) == 2


def test_manifest_written_with_required_fields(tmp_path):
    pol = load_policy(UHC)
    m = build_manifest(run_id="R", pipeline="hybrid", evaluations=["e"], policies=[pol], gpt_model="gpt-6-sol",
                       reasoning_effort="medium", jev_model="jev-1.13.0", threshold=0.9, narrative_mode="ready_only",
                       concurrency=4, force=False)
    write_manifest(tmp_path, m)
    saved = json.loads((tmp_path / "run_manifest.json").read_text())
    for k in ("run_id", "timestamp", "git_commit", "source_tree_sha256", "cohort_version", "policy_versions", "models",
              "jev_threshold", "retrieval_config", "pricing_version"):
        assert k in saved
    assert saved["models"] == {"gpt": "gpt-6-sol", "gpt_reasoning_effort": "medium", "jev": "jev-1.13.0"}
    assert "sk-" not in json.dumps(saved)
