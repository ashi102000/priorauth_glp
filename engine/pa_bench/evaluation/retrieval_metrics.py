"""Retrieval evaluation against the hidden evidence map (evaluation-only; never used by pipelines).

Document-level metrics per (patient, policy, criterion):
  relevant   = DocumentReferences annotated relevance=true for the criterion's evidence concepts
  recall@K   = |retrieved ∩ relevant| / |relevant|
  precision  = |retrieved ∩ relevant| / |retrieved|
  stance coverage: recall restricted to SUPPORTS / CONTRADICTS / AMBIGUOUS evidence
  hard negatives: retrieved trap documents (relevance=false annotations for the concepts)
  critical_hit: when truth status is FAIL/CONFLICT and contradicting/ambiguous evidence exists, >= 1 was retrieved
Structured resources (Conditions, medications, BMI) are always supplied in full, so they are not scored here.
"""
from __future__ import annotations

from collections import defaultdict

COMORBIDITY_CONCEPTS = ["comorbidity"]


def index_annotations(annotations: list[dict]) -> dict:
    idx = defaultdict(lambda: defaultdict(set))
    for a in annotations:
        if not a["resource_id"].startswith("DocumentReference/"):
            continue
        key = (a["patient_id"], a["criterion_id"])
        idx[key]["relevant" if a["relevance"] else "hard_negative"].add(a["resource_id"])
        if a["relevance"]:
            idx[key][a["stance"]].add(a["resource_id"])
    return idx


def criterion_metrics(pid: str, concepts: list[str], retrieved_docs: set[str], ann_idx: dict,
                      truth_status: str | None = None) -> dict:
    rel, stance = set(), defaultdict(set)
    hard = set()
    for c in concepts:
        d = ann_idx.get((pid, c), {})
        rel |= d.get("relevant", set())
        hard |= d.get("hard_negative", set())
        for s in ("SUPPORTS", "CONTRADICTS", "AMBIGUOUS", "NEUTRAL"):
            stance[s] |= d.get(s, set())
    hard -= rel
    hit = retrieved_docs & rel

    def rec(s):
        return (len(retrieved_docs & s) / len(s)) if s else None

    critical = None
    neg = stance["CONTRADICTS"] | stance["AMBIGUOUS"]
    if truth_status in ("FAIL", "CONFLICT") and neg:
        critical = bool(retrieved_docs & neg)
    return {
        "n_relevant": len(rel), "n_retrieved": len(retrieved_docs), "n_hit": len(hit),
        "recall": rec(rel), "precision": (len(hit) / len(retrieved_docs)) if retrieved_docs else None,
        "recall_supports": rec(stance["SUPPORTS"]), "recall_contradicts": rec(stance["CONTRADICTS"]),
        "recall_ambiguous": rec(stance["AMBIGUOUS"]),
        "hard_negatives_retrieved": len(retrieved_docs & hard), "critical_hit": critical,
        "missed": sorted(rel - retrieved_docs),
    }
