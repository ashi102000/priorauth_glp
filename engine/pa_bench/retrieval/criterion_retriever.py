"""Criterion-specific retrieval: top-K by BM25 relevance, plus earliest/latest relevant chunks for temporal criteria.

Relevance != support: retrieval only selects candidate evidence; stance is decided downstream.
"""
from __future__ import annotations

from .chunker import Chunk
from .index import BM25Index
from .lexicon import CONCEPT_TERMS, CRITERION_CONCEPTS


def query_terms(criterion_id: str, extra_terms: list[str] | None = None) -> list[str]:
    terms: list[str] = []
    for concept in CRITERION_CONCEPTS.get(criterion_id, []):
        terms += CONCEPT_TERMS[concept]
    terms += extra_terms or []
    return list(dict.fromkeys(terms))  # dedupe, keep order


def retrieve(index: BM25Index, criterion_id: str, *, extra_terms: list[str] | None, temporal: bool,
             top_k: int, min_relative_score: float, temporal_extras: bool = True) -> list[dict]:
    scores = index.score(query_terms(criterion_id, extra_terms))
    if not scores or max(scores) <= 0:
        return []
    floor = max(scores) * min_relative_score
    ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], index.chunks[i].date, index.chunks[i].chunk_id))
    chosen: dict[int, str] = {}
    for i in ranked[:top_k]:
        if scores[i] >= floor:
            chosen[i] = "top_k"
    if temporal and temporal_extras:
        candidates = [i for i in range(len(scores)) if scores[i] >= floor]
        if candidates:
            earliest = min(candidates, key=lambda i: (index.chunks[i].date, -scores[i]))
            latest = max(candidates, key=lambda i: (index.chunks[i].date, scores[i]))
            chosen.setdefault(earliest, "earliest_relevant")
            chosen.setdefault(latest, "latest_relevant")
    out = []
    for i in sorted(chosen, key=lambda i: (index.chunks[i].date, index.chunks[i].chunk_id)):
        c: Chunk = index.chunks[i]
        out.append({**c.to_dict(), "score": scores[i], "reason": chosen[i]})
    return out
