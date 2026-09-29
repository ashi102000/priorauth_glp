import json
import re
from datetime import date

import pytest

from pa_bench.config import request_date, retrieval_config
from pa_bench.fhir.feature_extractor import extract_features
from pa_bench.fhir.parser import document_text
from pa_bench.guard import assert_model_safe
from pa_bench.policies.loader import load_all, load_policy
from pa_bench.retrieval.chunker import chunk_document
from pa_bench.retrieval.criterion_retriever import retrieve
from pa_bench.retrieval.index import BM25Index, tokenize
from pa_bench.retrieval.profile import build_profile, cached_profile

AETNA = "AETNA_WEGOVY_4774C_2026_08_20"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def test_chunks_cover_note_text_exactly(client):
    cfg = retrieval_config()["chunking"]
    for pid in ("GLP1-001", "GLP1-047", "GLP1-048"):
        for d in client.search("DocumentReference", patient=pid):
            chunks = chunk_document(d, cfg["max_words"], cfg["min_words"])
            assert chunks and all(c.resource_id == f"DocumentReference/{d['id']}" for c in chunks)
            assert norm(" ".join(c.text for c in chunks)) == norm(document_text(d))
            assert all(len(c.text.split()) <= cfg["max_words"] + 40 for c in chunks)


def test_bm25_ranks_matching_chunk_first(client):
    docs = client.search("DocumentReference", patient="GLP1-043")
    chunks = [c for d in docs for c in chunk_document(d)]
    idx = BM25Index(chunks)
    scores = idx.score(["declined", "dietitian referral"])
    best = chunks[max(range(len(scores)), key=scores.__getitem__)]
    assert best.resource_id == "DocumentReference/GLP1-043-PCP-001"
    assert tokenize("Walking walks") == ["walk", "walk"]


def test_temporal_extras_include_earliest_and_latest(client):
    docs = client.search("DocumentReference", patient="GLP1-037")
    chunks = [c for d in docs for c in chunk_document(d)]
    ev = retrieve(BM25Index(chunks), "program_6_months", extra_terms=None, temporal=True, top_k=1,
                  min_relative_score=0.2, temporal_extras=True)
    reasons = {e["reason"] for e in ev}
    assert "top_k" in reasons and len(ev) >= 2
    assert [e["date"] for e in ev] == sorted(e["date"] for e in ev)


def test_features_exclude_requested_order_and_future_data(client):
    f = extract_features(client, "GLP1-038", request_date())
    assert f["requested_order"]["resource_id"] == "MedicationRequest/GLP1-038-WEGOVY-REQ"
    assert all("WEGOVY-REQ" not in m["resource_id"] for m in f["medications"])
    assert [m["text"].split()[0] for m in f["anti_obesity_medications"]] == ["Ozempic"]
    early = extract_features(client, "GLP1-038", date(2025, 1, 1))
    assert all(r["date"] <= "2025-01-01" for r in early["bmi"]["history"])
    assert early["anti_obesity_medications"] == []


def test_features_designed_values(client):
    assert extract_features(client, "GLP1-041", request_date())["bmi"]["latest"]["value"] == 29.8
    f = extract_features(client, "GLP1-046", request_date())
    assert [(c["display"], c["clinical_status"]) for c in f["weight_related_conditions"]] == [("Hypertensive disorder", "resolved")]
    assert extract_features(client, "GLP1-022", request_date())["weight_related_conditions"] == []


@pytest.mark.parametrize("pid", ["GLP1-016", "GLP1-038", "GLP1-048"])
def test_profiles_are_model_safe_and_deterministic(client, pid):
    for pol in load_all():
        a = build_profile(client, pid, pol, request_date())
        b = build_profile(client, pid, pol, request_date())
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        assert_model_safe(a)
        semantic = {c["criterion_id"] for c in pol["criteria"] if c["evaluator"] == "semantic"}
        assert semantic <= set(a["evidence"]) and "comorbidity" in a["evidence"]


def test_profile_contains_no_hidden_fields(client):
    prof = build_profile(client, "GLP1-043", load_policy(AETNA), request_date())
    text = json.dumps(prof)
    for bad in ("stance", "relevance", "hard_negative", "SUPPORTS", "difficulty", "challenge"):
        assert bad not in text


def test_cache_roundtrip(client, tmp_path, monkeypatch):
    import pa_bench.retrieval.profile as prof_mod
    monkeypatch.setattr(prof_mod, "CACHE_DIR", tmp_path)
    pol = load_policy(AETNA)
    first = cached_profile(client, "GLP1-001", pol, request_date())
    assert list(tmp_path.rglob("*.json"))
    assert cached_profile(client, "GLP1-001", pol, request_date()) == json.loads(json.dumps(first))
