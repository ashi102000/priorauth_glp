"""Build ground_truth/evidence_map.json = plan annotations + incidental comorbidity mentions found in note text.

Plan annotations come from generate_plans.py. Authored notes also mention comorbidities incidentally
(e.g. "HTN on losartan" in a dental clearance). Those are real evidence, so they are annotated here
with source "incidental_scan". Only conditions the patient actually has (active, narrative-only,
resolved, or ambiguous) are scanned; LDL/A1c values alone never count for patients without the condition.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "hypertension": re.compile(r"\bHTN\b|hypertensi|amlodipine|losartan|lisinopril", re.I),
    "dyslipidemia": re.compile(r"hyperlipidemia|high cholesterol|atorvastatin|rosuvastatin|\bstatin\b", re.I),
    "prediabetes": re.compile(r"prediabet|\bA1c\b", re.I),
}


def condition_status(p: dict) -> dict[str, str]:
    conds = p["clinical_truth"]["conditions"]
    out = {}
    for key in PATTERNS:
        if key not in conds:
            continue
        v = conds[key]
        if v is None:
            out[key] = "ambiguous"
        elif v and key == "hypertension" and conds.get("condition_status") == "resolved":
            out[key] = "resolved"
        elif v:
            out[key] = "active"
    return out


NEGATED = re.compile(r"\bno\s*$", re.I)   # e.g. "no hypertensive retinopathy" is not evidence of hypertension
STANCE = {"active": "SUPPORTS", "resolved": "CONTRADICTS", "ambiguous": "AMBIGUOUS"}


def main() -> int:
    spec = json.loads((ROOT / "data/cohort/patients.json").read_text())
    plan_anns = json.loads((ROOT / "data/_generation/plan_annotations.json").read_text())["annotations"]
    have = {(a["resource_id"], a["criterion_id"]) for a in plan_anns}
    added = []
    for p in spec["patients"]:
        pid = p["patient_id"]
        status = condition_status(p)
        if not status:
            continue
        notes = json.loads((ROOT / f"data/notes/{pid}.json").read_text())["notes"]
        for doc_id, text in notes.items():
            rid = f"DocumentReference/{doc_id}"
            if (rid, "comorbidity") in have:
                continue
            for key, st in status.items():
                m = next((m for m in PATTERNS[key].finditer(text) if not NEGATED.search(text[max(0, m.start() - 12):m.start()])), None)
                if m:
                    added.append({"patient_id": pid, "resource_id": rid, "criterion_id": "comorbidity", "relevance": True,
                                  "stance": STANCE[st], "facts": [{"predicate": "condition", "value": key},
                                                                   {"predicate": "source", "value": "incidental_scan"},
                                                                   {"predicate": "matched", "value": m.group(0)}]})
                    have.add((rid, "comorbidity"))
                    break
    out = {"warning": "EVALUATION ONLY — never send to models", "cohort_id": spec["cohort_id"],
           "status": "concept_level (mapped to policy criteria in Phase 2)",
           "annotations": plan_anns + added}
    (ROOT / "ground_truth/evidence_map.json").write_text(json.dumps(out, indent=2))
    print(f"plan annotations: {len(plan_anns)}  incidental comorbidity annotations added: {len(added)}")
    for a in added:
        print(f"  {a['resource_id']:<40} {a['stance']:<11} matched '{a['facts'][2]['value']}'")
    print("by stance:", dict(Counter(a["stance"] for a in added)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
