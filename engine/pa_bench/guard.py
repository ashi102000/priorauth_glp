"""Ground-truth isolation guard.

Every payload sent to a model provider must pass `assert_model_safe`. The guard rejects any text that
contains answer-key vocabulary: cohort-spec field names, benchmark class labels, distinctive challenge
tags, evaluation ids, annotation-only field names, or references to hidden directories.

Output-schema words that are legitimately part of a prompt (e.g. PASS/FAIL, SUPPORTS/CONTRADICTS as an
answer space) are NOT blocked; they carry no information about a specific case.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)

HIDDEN_PATHS = ("ground_truth/", "data/_generation/", "data/cohort/")

SPEC_FIELD_NAMES = {
    "benchmark_design", "clinical_truth", "challenge_tags", "primary_test", "documentation_state",
    "medication_scenario", "program_documented", "duration_months", "diet_documented", "exercise_documented",
    "followup_documented", "inadequate_response_documented", "structured_condition_present",
}
ANNOTATION_FIELD_NAMES = {"hard_negative", "program_event", "incidental_scan", "evidence_map", "criterion_truth",
                          "pa_truth", "binary_auto_ready", "ground_truth", "facts_to_express", "must_not_say"}
CLASS_LABELS = {"easy_positive", "easy_negative", "missing_evidence"}
EVAL_ID = re.compile(r"GLP1-\d{3}__[A-Z]")


class GroundTruthLeakError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _cohort_vocabulary() -> frozenset[str]:
    """Distinctive (underscore-joined) tags/states from the cohort spec, e.g. 'retrieval_trap'."""
    spec_path = ROOT / "data/cohort/patients.json"
    vocab: set[str] = set()
    packaged = Path(__file__).with_name("guard_vocab.json")      # deployments ship the vocabulary, not the cohort
    if not spec_path.exists() and packaged.exists():
        return frozenset(json.loads(packaged.read_text()))
    if spec_path.exists():
        for p in json.loads(spec_path.read_text())["patients"]:
            bd, ct = p["benchmark_design"], p["clinical_truth"]
            vocab.update(bd["challenge_tags"])
            vocab.add(bd["primary_test"])
            vocab.add(ct["weight_management"]["documentation_state"])
            vocab.add(ct["medication_scenario"])
    return frozenset(v for v in vocab if "_" in v and v != "none")


def leak_terms() -> frozenset[str]:
    return frozenset(SPEC_FIELD_NAMES | ANNOTATION_FIELD_NAMES | CLASS_LABELS) | _cohort_vocabulary()


def find_leaks(payload: str | dict | list) -> list[str]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    low = text.lower()
    # whole-identifier match: 'duration_months' must not fire on the policy parameter 'min_duration_months'
    hits = sorted(t for t in leak_terms()
                  if re.search(rf"(?<![a-z0-9_]){re.escape(t.lower())}(?![a-z0-9_])", low))
    hits += [f"path:{p}" for p in HIDDEN_PATHS if p in text]
    if EVAL_ID.search(text):
        hits.append("evaluation_id")
    return hits


def assert_model_safe(payload: str | dict | list) -> None:
    hits = find_leaks(payload)
    if hits:
        raise GroundTruthLeakError(f"ground-truth vocabulary in model payload: {hits[:10]}")
