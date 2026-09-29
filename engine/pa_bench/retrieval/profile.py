"""Patient evidence profile = structured features + criterion-specific retrieved note evidence.

This is the ONLY patient content that model pipelines receive. Built once per (patient, policy, config)
and cached, so every experimental arm sees identical evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import tiktoken

from ..config import pa_request, retrieval_config
from ..fhir.client import FhirClient
from ..fhir.feature_extractor import extract_features
from ..guard import assert_model_safe
from .chunker import chunk_document
from .criterion_retriever import retrieve
from .index import BM25Index

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)
CACHE_DIR = ROOT / "data/cache/profiles"
SEMANTIC_TYPES = ("semantic", "semantic_temporal", "medication_reconciliation")


@lru_cache(maxsize=1)
def _enc():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(obj) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return len(_enc().encode(text))


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


def raw_chart_tokens(client: FhirClient, patient_id: str) -> dict:
    """Candidate-chart size if everything were sent: all resources with note text decoded."""
    from ..fhir.parser import document_text
    ev = client.everything(patient_id)
    structured = {t: rs for t, rs in ev.items() if t != "DocumentReference"}
    notes = [document_text(d) for d in ev.get("DocumentReference", [])]
    s, n = count_tokens(structured), sum(count_tokens(t) for t in notes)
    return {"structured": s, "notes": n, "total": s + n}


def build_profile(client: FhirClient, patient_id: str, policy: dict, as_of: date, cfg: dict | None = None) -> dict:
    cfg = cfg or retrieval_config()
    feats = extract_features(client, patient_id, as_of)
    docs = [d for d in client.search("DocumentReference", patient=patient_id) if d["date"][:10] <= as_of.isoformat()]
    chunks = [c for d in docs for c in chunk_document(d, cfg["chunking"]["max_words"], cfg["chunking"]["min_words"])]
    index = BM25Index(chunks, **cfg["bm25"])

    evidence = {}
    needs_comorbidity = False
    for c in policy["criteria"]:
        if c["criterion_id"] == "bmi_threshold":
            needs_comorbidity = True
        if c["type"] not in SEMANTIC_TYPES:
            continue
        r = c.get("retrieval", {})
        evidence[c["criterion_id"]] = retrieve(index, c["criterion_id"], extra_terms=r.get("concepts"),
                                               temporal=bool(r.get("temporal")) or c["type"] == "semantic_temporal",
                                               top_k=cfg["top_k"], min_relative_score=cfg["min_relative_score"],
                                               temporal_extras=cfg["temporal_extras"])
    if needs_comorbidity:   # narrative comorbidity evidence for the BMI 27–30 band (structured Conditions are in features)
        evidence["comorbidity"] = retrieve(index, "comorbidity", extra_terms=None, temporal=False, top_k=cfg["top_k"],
                                           min_relative_score=cfg["min_relative_score"], temporal_extras=False)

    profile = {
        "patient_id": patient_id,
        "policy_id": policy["policy_id"],
        "request": pa_request(),
        "structured": {k: feats[k] for k in ("demographics", "bmi", "weight", "height", "blood_pressure", "labs",
                                             "conditions", "weight_related_conditions", "medications",
                                             "anti_obesity_medications", "requested_order")},
        "evidence": evidence,
        "meta": {"retrieval_version": cfg["version"], "retrieval_config_hash": config_hash(cfg),
                 "n_chunks_indexed": len(chunks), "n_notes": len(docs)},
    }
    assert_model_safe(profile)
    unique_chunks = {e["chunk_id"]: e["text"] for ev in evidence.values() for e in ev}
    profile["meta"]["tokens"] = {
        "raw_chart": raw_chart_tokens(client, patient_id),
        "retrieved_evidence": sum(count_tokens(t) for t in unique_chunks.values()),
        "structured_features": count_tokens(profile["structured"]),
        "profile_total": count_tokens({k: profile[k] for k in ("request", "structured", "evidence")}),
    }
    return profile


def cached_profile(client: FhirClient, patient_id: str, policy: dict, as_of: date, cfg: dict | None = None,
                   refresh: bool = False) -> dict:
    cfg = cfg or retrieval_config()
    path = CACHE_DIR / config_hash(cfg) / f"{patient_id}__{policy['policy_id']}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    prof = build_profile(client, patient_id, policy, as_of, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prof, indent=1, ensure_ascii=False))
    return prof
