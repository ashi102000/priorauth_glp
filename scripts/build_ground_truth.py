"""P2.5: derive criterion-level and PA-level ground truth for 50 patients x 3 verified policies.

Inputs (hidden): cohort spec, frozen chart plans, evidence map, truth_rules (user-approved interpretations).
Computed by code: age, latest structured BMI, BMI thresholds, Aetna program duration (calendar whole months).
Outputs: ground_truth/criterion_truth.json, ground_truth/pa_truth.json, reports/ground_truth_summary.md
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.calc import age_on, whole_months_between  # noqa: E402
from pa_bench.generation.truth_rules import COMPUTE, DOC_TRUTH, MED_TRUTH, comorbidity_truth  # noqa: E402
from pa_bench.policies.evaluator import aggregate, eval_age, eval_bmi, eval_indication  # noqa: E402
from pa_bench.policies.loader import load_all  # noqa: E402

REQUEST_DATE = date(2026, 9, 1)
CRITERION_KEY = {  # policy criterion -> truth key
    "weight_management_program": ("doc", "fep_program"),
    "program_6_months": ("doc", "aetna_program"),
    "lifestyle_adjunct": ("doc", "current_any"),
    "adjunct_diet_and_activity": ("doc", "current_both"),
    "no_concurrent_glp1": ("med", "glp1"),
    "no_concurrent_pa_weight_loss_med": ("med", "pa"),
}
START_EVENTS = {"start", "summary_since"}
END_EVENTS = {"continuation", "nutrition_visit", "summary"}


def program_duration(pid: str, anns: list[dict]) -> tuple[date, date, int]:
    starts, ends = [], []
    for a in anns:
        if a["patient_id"] != pid or a["criterion_id"] not in ("program_duration", "weight_management_program"):
            continue
        f = {x["predicate"]: x["value"] for x in a["facts"]}
        if "event_date" not in f or a["stance"] != "SUPPORTS":
            continue
        d = date.fromisoformat(f["event_date"])
        if f.get("program_event") in START_EVENTS:
            starts.append(d)
        if f.get("program_event") in END_EVENTS:
            ends.append(d)
    s, e = min(starts), max(ends)
    return s, e, whole_months_between(s, e)


def main() -> int:
    spec = {p["patient_id"]: p for p in json.loads((ROOT / "data/cohort/patients.json").read_text())["patients"]}
    anns = json.loads((ROOT / "ground_truth/evidence_map.json").read_text())["annotations"]
    ann_by = defaultdict(list)
    for a in anns:
        if a["relevance"]:
            ann_by[(a["patient_id"], a["criterion_id"])].append(a)
    policies = load_all()
    crit_rows, pa_rows = [], []

    for pid, p in sorted(spec.items()):
        plan = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
        birth = date.fromisoformat(plan["patient"]["birthDate"])
        bmis = sorted((o for o in plan["observations"] if o["key"] == "BMI"), key=lambda o: o["date"])
        latest_bmi = bmis[-1]["value"]
        comorb, comorb_why = comorbidity_truth(p["clinical_truth"]["conditions"])
        state = p["clinical_truth"]["weight_management"]["documentation_state"]
        med = p["clinical_truth"]["medication_scenario"]
        doc_truth, med_truth = DOC_TRUTH[state], MED_TRUTH[med]
        duration = None
        if doc_truth["aetna_program"][0] == COMPUTE:
            s, e, m = program_duration(pid, anns)
            duration = {"start": s.isoformat(), "last_participation": e.isoformat(), "whole_months": m}

        for pol in policies:
            statuses, rows = {}, []
            for c in pol["criteria"]:
                cid = c["criterion_id"]
                if cid == "age":
                    st = eval_age(birth, REQUEST_DATE, c["params"])
                    why = f"Age {age_on(birth, REQUEST_DATE)} on {REQUEST_DATE} (min {c['params']['min_age']})."
                elif cid == "indication":
                    st = eval_indication(p["request"]["indication"], c["params"])
                    why = "Initial Wegovy request for chronic weight management."
                elif cid == "bmi_threshold":
                    st = eval_bmi(latest_bmi, comorb, c["params"])
                    why = f"Latest structured BMI {latest_bmi} ({bmis[-1]['date']})."
                    if c["params"]["bmi_with_comorbidity"] <= latest_bmi < c["params"]["bmi_primary"]:
                        why += f" In 27–30 band; comorbidity: {comorb} — {comorb_why}"
                else:
                    src, key = CRITERION_KEY[cid]
                    st, why = (doc_truth if src == "doc" else med_truth)[key]
                    if st == COMPUTE:
                        st = "PASS" if duration["whole_months"] >= c["params"]["min_duration_months"] else "FAIL"
                        why = f"{why} {duration['start']} -> {duration['last_participation']} = {duration['whole_months']} whole months (min {c['params']['min_duration_months']})."
                statuses[cid] = st
                ev = defaultdict(list)
                for concept in c["evidence_concepts"]:
                    for a in ann_by[(pid, concept)]:
                        if concept == "comorbidity" and not (c["params"].get("bmi_with_comorbidity", 0) <= latest_bmi < c["params"].get("bmi_primary", 0)):
                            continue   # comorbidity evidence only matters in the 27–30 band
                        ev[a["stance"].lower()].append(a["resource_id"])
                rows.append({"criterion_id": cid, "criterion_type": c["type"], "evaluator": c["evaluator"], "status": st,
                             "rationale": why,
                             "evidence": {k: sorted(set(v)) for k, v in sorted(ev.items())}})
            decision = aggregate(pol, statuses)
            eid = f"{pid}__{pol['policy_id']}"
            for r in rows:
                crit_rows.append({"evaluation_id": eid, "patient_id": pid, "policy_id": pol["policy_id"], **r})
            pa_rows.append({
                "evaluation_id": eid, "patient_id": pid, "policy_id": pol["policy_id"],
                "ground_truth": {"criteria": {r["criterion_id"]: {"status": r["status"]} for r in rows}, **decision},
                "difficulty": p["benchmark_design"]["class"], "challenge_tags": p["benchmark_design"]["challenge_tags"],
            })

    hdr = {"warning": "EVALUATION ONLY — never send to models", "cohort_id": "GLP1_PA_COHORT_V1",
           "request_date": REQUEST_DATE.isoformat(), "policies": [p["policy_id"] for p in policies]}
    (ROOT / "ground_truth/criterion_truth.json").write_text(json.dumps({**hdr, "rows": crit_rows}, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "ground_truth/pa_truth.json").write_text(json.dumps({**hdr, "evaluations": pa_rows}, indent=2, ensure_ascii=False) + "\n")

    # ---- summary report
    L = ["# Ground truth summary (hidden)", "", f"{len(pa_rows)} evaluations (50 patients × {len(policies)} policies); "
         f"{len(crit_rows)} criterion labels. Request date {REQUEST_DATE}.", "", "## PA state by policy", "",
         "| Policy | READY | NOT_READY | REVIEW_REQUIRED |", "|---|---|---|---|"]
    for pol in policies:
        c = Counter(r["ground_truth"]["pa_state"] for r in pa_rows if r["policy_id"] == pol["policy_id"])
        L.append(f"| {pol['policy_id']} | {c['READY']} | {c['NOT_READY']} | {c['REVIEW_REQUIRED']} |")
    c = Counter(r["ground_truth"]["pa_state"] for r in pa_rows)
    L.append(f"| **All** | {c['READY']} | {c['NOT_READY']} | {c['REVIEW_REQUIRED']} |")
    L += ["", "## PA state by difficulty class (all policies)", "", "| Class | READY | NOT_READY | REVIEW_REQUIRED |", "|---|---|---|---|"]
    for k in ("easy_positive", "easy_negative", "missing_evidence", "ambiguous", "hard"):
        c = Counter(r["ground_truth"]["pa_state"] for r in pa_rows if r["difficulty"] == k)
        L.append(f"| {k} | {c['READY']} | {c['NOT_READY']} | {c['REVIEW_REQUIRED']} |")
    L += ["", "## Criterion status counts", "", "| Policy | Criterion | PASS | FAIL | INSUFFICIENT | CONFLICT |", "|---|---|---|---|---|---|"]
    for pol in policies:
        for cr in pol["criteria"]:
            c = Counter(r["status"] for r in crit_rows if r["policy_id"] == pol["policy_id"] and r["criterion_id"] == cr["criterion_id"])
            L.append(f"| {pol['policy_id'].split('_')[0]} | {cr['criterion_id']} | {c['PASS']} | {c['FAIL']} | {c['INSUFFICIENT']} | {c['CONFLICT']} |")
    short = {pol["policy_id"]: pol["policy_id"].split("_")[0] for pol in policies}
    L += ["", "## Per-patient labels", "", "`R`=READY, `N`=NOT_READY (failing/insufficient criteria), `V`=REVIEW_REQUIRED (conflicts)", "",
          "| Patient | Class | " + " | ".join(short.values()) + " |", "|---|---|" + "---|" * len(short)]
    by_pid = defaultdict(dict)
    for r in pa_rows:
        g = r["ground_truth"]
        tag = {"READY": "R", "NOT_READY": "N", "REVIEW_REQUIRED": "V"}[g["pa_state"]]
        detail = ", ".join(g["missing_requirements"] + [f"⚠{x}" for x in g["review_reasons"]])
        by_pid[r["patient_id"]][r["policy_id"]] = f"{tag}" + (f" ({detail})" if detail else "")
    for pid in sorted(by_pid):
        L.append(f"| {pid} | {spec[pid]['benchmark_design']['class']} | " + " | ".join(by_pid[pid][pp] for pp in short) + " |")
    (ROOT / "reports/ground_truth_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
