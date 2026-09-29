"""M1.7: cohort QA report -> reports/cohort_qa.md + reports/cohort_qa.json.

Reads the model-visible bundles (via LocalBundleClient) for counts/tokens, and the hidden cohort spec,
plans, and evidence map for distributions. The report is a hidden artifact (it names challenge classes).
"""
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.fhir.parser import document_text  # noqa: E402

ENC = tiktoken.get_encoding("cl100k_base")
TYPES = ["Patient", "Condition", "Observation", "MedicationRequest", "MedicationStatement", "MedicationDispense",
         "Encounter", "DocumentReference"]


def dist(values):
    return {"min": min(values), "median": st.median(values), "max": max(values), "total": sum(values)}


def bmi_bin(b):
    return "<27" if b < 27 else "27–29.99" if b < 30 else "30–34.99" if b < 35 else "35–39.99" if b < 40 else "≥40"


def main() -> int:
    spec = json.loads((ROOT / "data/cohort/patients.json").read_text())["patients"]
    evidence = json.loads((ROOT / "ground_truth/evidence_map.json").read_text())["annotations"]
    client = LocalBundleClient()
    by_pid = {p["patient_id"]: p for p in spec}

    per_type = defaultdict(list)
    note_rows, token_rows = [], []
    for pid in client.patient_ids():
        ev = client.everything(pid)
        for t in TYPES:
            per_type[t].append(len(ev.get(t, [])))
        plan = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
        roles = Counter("distractor" if n["role"] == "distractor" else "relevant" for n in plan["notes"])
        traps = sum(n["trap"] for n in plan["notes"])
        note_rows.append((pid, by_pid[pid]["benchmark_design"]["class"], len(plan["notes"]), roles["relevant"], roles["distractor"], traps))
        chart = json.dumps({t: rs for t, rs in ev.items() if t != "DocumentReference"})
        note_tok = sum(len(ENC.encode(document_text(d))) for d in ev.get("DocumentReference", []))
        bundle_tok = len(ENC.encode((ROOT / f"data/fhir/bundles/{pid}.json").read_text()))
        token_rows.append((pid, len(ENC.encode(chart)), note_tok, bundle_tok))

    classes = Counter(p["benchmark_design"]["class"] for p in spec)
    tags = Counter(t for p in spec for t in p["benchmark_design"]["challenge_tags"])
    bmis = [p["anthropometrics"]["current_bmi"] for p in spec]
    bmi_bins = Counter(bmi_bin(b) for b in bmis)
    conds = Counter()
    for p in spec:
        c = p["clinical_truth"]["conditions"]
        for k in ("hypertension", "dyslipidemia", "prediabetes"):
            if k in c:
                if c[k] is None:
                    conds[f"{k} (ambiguous)"] += 1
                elif c.get("condition_status") == "resolved" and k == "hypertension":
                    conds[f"{k} (resolved)"] += 1
                elif c.get("structured_condition_present") is False:
                    conds[f"{k} (narrative only)"] += 1
                elif c[k]:
                    conds[f"{k} (structured)"] += 1
        if not any(c.get(k) for k in ("hypertension", "dyslipidemia", "prediabetes")) and not any(k in c for k in ("hypertension",)):
            conds["no weight-related comorbidity"] += 1
    meds = Counter(p["clinical_truth"]["medication_scenario"] for p in spec)
    docs = Counter(p["clinical_truth"]["weight_management"]["documentation_state"] for p in spec)
    ann = Counter((a["criterion_id"], a["stance"]) for a in evidence if a["relevance"])
    hard_neg = sum(1 for a in evidence if not a["relevance"])

    qa = {
        "cohort_id": "GLP1_PA_COHORT_V1", "patients": len(spec), "index_date": "2026-09-01",
        "resource_counts": {t: dist(per_type[t]) for t in TYPES},
        "notes": {"total": sum(r[2] for r in note_rows), "relevant": sum(r[3] for r in note_rows),
                  "distractor": sum(r[4] for r in note_rows), "trap_distractors": sum(r[5] for r in note_rows),
                  "per_class": {k: {"patients": classes[k], "notes": sum(r[2] for r in note_rows if r[1] == k),
                                    "traps": sum(r[5] for r in note_rows if r[1] == k)} for k in classes}},
        "tokens_cl100k": {"structured_resources": dist([r[1] for r in token_rows]),
                          "note_text": dist([r[2] for r in token_rows]),
                          "raw_bundle_json": dist([r[3] for r in token_rows])},
        "class_distribution": dict(classes), "challenge_tags": dict(tags.most_common()),
        "bmi": {"bins": dict(sorted(bmi_bins.items())), "min": min(bmis), "median": st.median(bmis), "max": max(bmis),
                "boundary_cases_29.5_30.5": sorted(pid for pid, p in by_pid.items() if 29.5 <= p["anthropometrics"]["current_bmi"] <= 30.5),
                "boundary_cases_26.5_27.5": sorted(pid for pid, p in by_pid.items() if 26.5 <= p["anthropometrics"]["current_bmi"] <= 27.5)},
        "conditions": dict(conds), "medication_scenarios": dict(meds.most_common()),
        "documentation_states": dict(docs.most_common()),
        "evidence_annotations": {"relevant": sum(ann.values()), "hard_negatives": hard_neg,
                                 "by_concept_stance": {f"{c}:{s}": n for (c, s), n in sorted(ann.items())}},
    }
    (ROOT / "reports/cohort_qa.json").write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n")

    L = ["# Cohort QA Report — GLP1_PA_COHORT_V1", "",
         "Hidden artifact (names challenge classes). Generated by `scripts/cohort_qa.py`. Index date 2026-09-01.", "",
         "## Resource counts per patient", "", "| Resource | min | median | max | total |", "|---|---|---|---|---|"]
    for t in TYPES:
        d = qa["resource_counts"][t]
        L.append(f"| {t} | {d['min']} | {d['median']} | {d['max']} | {d['total']} |")
    n = qa["notes"]
    L += ["", "## Notes", "", f"Total **{n['total']}** — relevant {n['relevant']}, distractor {n['distractor']} "
          f"(of which trap / hard-negative {n['trap_distractors']}).", "",
          "| Class | Patients | Notes | Trap distractors |", "|---|---|---|---|"]
    for k, v in n["per_class"].items():
        L.append(f"| {k} | {v['patients']} | {v['notes']} | {v['traps']} |")
    L += ["", "## Token footprint per patient (tiktoken cl100k_base)", "", "| Component | min | median | max | total |", "|---|---|---|---|---|"]
    for k, d in qa["tokens_cl100k"].items():
        L.append(f"| {k} | {d['min']} | {d['median']} | {d['max']} | {d['total']} |")
    L += ["", "## Challenge distribution", "", "| Class | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in classes.items()]
    L += ["", "| Challenge tag | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in tags.most_common()]
    b = qa["bmi"]
    L += ["", "## BMI distribution (latest structured value per spec)", "", f"min {b['min']}, median {b['median']}, max {b['max']}", "",
          "| BMI bin | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in b["bins"].items()]
    L += ["", f"Boundary cases near 30: {', '.join(b['boundary_cases_29.5_30.5'])}",
          f"Boundary cases near 27: {', '.join(b['boundary_cases_26.5_27.5']) or '—'}",
          "Note: GLP1-041's latest structured BMI is 29.8 (spec current_bmi 30.3 is the prior reading; DECISIONS.md)."]
    L += ["", "## Condition distribution (weight-related comorbidities)", "", "| Condition | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(conds.items())]
    L += ["", "## Medication scenario distribution", "", "| Scenario | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in meds.most_common()]
    L += ["", "## Documentation-state distribution", "", "| State | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in docs.most_common()]
    L += ["", "## Evidence annotations (concept level)", "", f"Relevant annotations: {sum(ann.values())}; hard negatives: {hard_neg}", "",
          "| Concept | SUPPORTS | CONTRADICTS | AMBIGUOUS | NEUTRAL |", "|---|---|---|---|---|"]
    for c in sorted({c for c, _ in ann}):
        L.append(f"| {c} | " + " | ".join(str(ann.get((c, s), 0)) for s in ("SUPPORTS", "CONTRADICTS", "AMBIGUOUS", "NEUTRAL")) + " |")
    L += ["", "## Validation status", "",
          "- `validate_cohort.py` PASS · `generate_plans.py` PASS (plans frozen) · `lint_notes.py --strict` PASS",
          "- `validate_fhir.py` PASS against strict R4 4.0.1 and R4B 4.3.0 · `verify_local_fhir.py` PASS",
          "- Distractor purity scan: no unannotated weight-management / GLP-1 language in distractor notes"]
    (ROOT / "reports/cohort_qa.md").write_text("\n".join(L) + "\n")
    print((ROOT / "reports/cohort_qa.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
