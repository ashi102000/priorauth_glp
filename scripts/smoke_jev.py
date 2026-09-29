"""Phase 5 smoke test: Jev bounded judgments over real retrieved evidence; verifies raw probabilities are
preserved exactly. Outputs results/smoke/jev_<run_id>/{traces.jsonl, calls.jsonl}."""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
from pa_bench.benchmark.trace import TraceWriter, trace_row  # noqa: E402
from pa_bench.config import request_date  # noqa: E402
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.models.jev_provider import JevProvider, choice  # noqa: E402
from pa_bench.pipelines.common import evidence_view  # noqa: E402
from pa_bench.policies.loader import load_policy  # noqa: E402
from pa_bench.retrieval.profile import cached_profile  # noqa: E402

PROGRAM_EVENT = {
    "program_started": "The note documents that the patient starts or enrolls in a weight-management program or a structured diet and exercise plan.",
    "program_ongoing": "The note documents that the patient is currently continuing a weight-management program or structured diet/exercise plan.",
    "program_stopped": "The note documents that the patient stopped, dropped out of, or lapsed from the program or plan.",
    "program_restarted": "The note documents that the patient is restarting the program or plan after a break.",
    "declined_or_not_enrolled": "The note documents that the patient declined, did not enroll in, or has no formal diet or exercise program.",
    "informal_or_counseling_only": "Only informal efforts, vague intentions, or brief counseling — no program or structured plan.",
    "not_about_weight_management": "The note does not discuss the patient's weight-management efforts.",
}
MED_STATUS = {
    "currently_taking": "The note says the patient is currently taking a GLP-1 or other weight-loss medication (not counting a newly planned Wegovy start).",
    "stopped": "The note says the patient stopped or is no longer taking such a medication.",
    "unclear_if_still_taking": "The note mentions such a medication but it is unclear whether the patient is still taking it.",
    "not_mentioned": "The note does not mention the patient using a GLP-1 or weight-loss medication, other than a newly planned Wegovy start.",
}
COMORB = {
    "diagnosed_active": "The notes document an active diagnosis of hypertension, dyslipidemia/high cholesterol, type 2 diabetes, sleep apnea, or cardiovascular disease.",
    "resolved": "The notes document that such a condition existed but has resolved.",
    "suspected_not_diagnosed": "The notes mention elevated readings or concern (e.g., high blood pressure) without a diagnosis.",
    "none": "None of these conditions is documented.",
}


def note_state(profile, criteria):
    rows = evidence_view(profile, criteria)
    return {"request_date": profile["request"]["request_date"],
            "notes": [{"date": r["date"], "note_type": r["note_type"], "text": r["text"]} for r in rows]}, rows


def main():
    jev, client = JevProvider(), LocalBundleClient()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out = ROOT / f"results/smoke/jev_{run_id}"
    tw = TraceWriter(out / "traces.jsonl")
    aetna, fep, uhc = (load_policy(p) for p in ("AETNA_WEGOVY_4774C_2026_08_20", "BCBS_FEP_WEGOVY_2026_07_01",
                                                 "UHC_WEGOVY_P1114_22_2026_09_01"))
    cases = [("GLP1-043", aetna, ["program_6_months"], "program"), ("GLP1-037", aetna, ["program_6_months"], "program"),
             ("GLP1-038", fep, ["no_concurrent_glp1"], "med"), ("GLP1-045", fep, ["no_concurrent_glp1"], "med"),
             ("GLP1-028", uhc, ["comorbidity"], "comorb")]
    total_cost, exact = 0.0, True
    for pid, pol, crit, kind in cases:
        prof = cached_profile(client, pid, pol, request_date())
        state, rows = note_state(prof, crit)
        if kind == "program":
            qs = {f"event_{i}": choice(f"Which option best describes what `notes[{i}]` documents about the patient's weight-management program participation?", PROGRAM_EVENT) for i in range(len(rows))}
        elif kind == "med":
            qs = {f"med_{i}": choice(f"What does `notes[{i}]` say about the patient's use of a GLP-1 receptor agonist or other weight-loss medication?", MED_STATUS) for i in range(len(rows))}
        else:
            qs = {"comorbidity": choice("Which option best describes the weight-related comorbidities documented in `notes`?", COMORB)}
        rec = jev.ask(state=state, questions=qs, stage=f"smoke_{kind}")
        call = rec.to_dict()
        raw = json.loads(rec.output_text)["answers"] if rec.output_text else {}
        for qid, a in raw.items():
            exp = a["probabilities"] if a["type"] != "noul" else {"yes": a["noul"]}
            exact &= rec.probabilities[qid] == exp
        tr = trace_row(run_id=run_id, evaluation_id=f"{pid}__{pol['policy_id']}", pipeline="jev_smoke", call=call)
        tw.write(tr)
        with (out / "calls.jsonl").open("a") as f:
            f.write(json.dumps(call, ensure_ascii=False) + "\n")
        total_cost += tr["estimated_cost_usd"] or 0
        print(f"\n== {pid} {kind}  model={rec.extra.get('response_model')} in={rec.input_tokens} out={rec.output_tokens} "
              f"latency={rec.latency_ms}ms cost=${tr['estimated_cost_usd']:.6f} err={rec.error}")
        for qid, a in (rec.parsed or {}).items():
            i = int(qid.split("_")[-1]) if qid[-1].isdigit() else None
            label = f"{rows[i]['date']} {rows[i]['id'].split('/')[1]}" if i is not None else "all notes"
            top = sorted(a["probabilities"].items(), key=lambda kv: -kv[1])[:3]
            print(f"  {label:<32} -> {a['choice']:<28} conf={a['confidence']:.2f}  top={[(k, round(v, 3)) for k, v in top]}")
    print(f"\nraw probabilities preserved exactly: {exact}   total cost ${total_cost:.6f}   outputs {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
