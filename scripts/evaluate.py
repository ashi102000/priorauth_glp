"""Phase 8: evaluate benchmark runs and write results/ + presentation_results/.

Usage: python scripts/evaluate.py [--gpt main_gpt] [--hybrid main_hybrid_t0.90] [--sweep sweep]
"""
import argparse
import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.evaluation.cost import load_pricing, record_cost  # noqa: E402
from pa_bench.evaluation.failures import categorize, escalation_effect  # noqa: E402
from pa_bench.evaluation.metrics import (PA_CLASSES, STATUS_CLASSES, binary, calibration, cluster_bootstrap_ci,  # noqa: E402
                                         mcnemar_exact, percentiles, prf)
from pa_bench.policies.loader import load_all  # noqa: E402

RES, PRES = ROOT / "results", ROOT / "presentation_results"
THRESHOLDS = (0.60, 0.70, 0.80, 0.90, 0.95)


# ------------------------------------------------------------------------------------------ loading
def load_run(run_id: str) -> tuple[dict, dict]:
    d = ROOT / "results/runs" / run_id
    rows = {}
    for line in (d / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        rows[r["evaluation_id"]] = r          # last attempt wins
    return rows, json.loads((d / "run_manifest.json").read_text())


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(map(str, v)) if isinstance(v, list) else (round(v, 6) if isinstance(v, float) else v))
                        for k, v in r.items()})


def r6(x):
    return None if x is None else round(x, 6)


# ------------------------------------------------------------------------------------------ per-case accounting
def case_accounting(row: dict) -> dict:
    calls = row.get("calls", [])
    gpt = [c for c in calls if c["provider"] == "openai"]
    gpt_dec = [c for c in gpt if c["stage"] != "narrative"]
    jev = [c for c in calls if c["provider"] == "jev"]
    cost = lambda cs: sum(record_cost(c) or 0.0 for c in cs)  # noqa: E731
    lat = row["latency_ms"]
    raw = row["profile_tokens"]["raw_chart"]["total"]
    gpt_in_dec = sum(c["input_tokens"] for c in gpt_dec)
    jev_in = sum(c["input_tokens"] for c in jev)
    model_ctx = gpt_in_dec + jev_in
    return {
        "gpt_calls": len(gpt), "gpt_decision_calls": len(gpt_dec), "narrative_calls": len(gpt) - len(gpt_dec), "jev_calls": len(jev),
        "gpt_input_tokens": sum(c["input_tokens"] for c in gpt), "gpt_output_tokens": sum(c["output_tokens"] for c in gpt),
        "gpt_reasoning_tokens": sum(c["reasoning_tokens"] for c in gpt),
        "gpt_decision_input_tokens": gpt_in_dec, "gpt_decision_output_tokens": sum(c["output_tokens"] for c in gpt_dec),
        "jev_input_tokens": jev_in, "jev_output_tokens": sum(c["output_tokens"] for c in jev),
        "gpt_cost_usd": cost(gpt), "gpt_decision_cost_usd": cost(gpt_dec), "narrative_cost_usd": cost(gpt) - cost(gpt_dec),
        "jev_cost_usd": cost(jev), "total_cost_usd": cost(calls), "decision_cost_usd": cost(gpt_dec) + cost(jev),
        "total_latency_ms": lat["total"], "decision_latency_ms": lat.get("decision_total", lat["total"]),
        "retrieval_latency_ms": lat.get("retrieval", 0.0), "rules_latency_ms": lat.get("rules", 0.0),
        "jev_latency_ms": lat.get("jev", 0.0), "gpt_latency_ms": lat.get("gpt", 0.0), "narrative_latency_ms": lat.get("narrative", 0.0),
        "raw_chart_tokens": raw, "model_context_tokens": model_ctx, "frontier_context_tokens": gpt_in_dec,
        "context_reduction_pct": 100 * (1 - model_ctx / raw) if raw else None,
        "frontier_context_reduction_pct": 100 * (1 - gpt_in_dec / raw) if raw else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpt", default="main_gpt")
    ap.add_argument("--hybrid", default="main_hybrid_t0.90")
    ap.add_argument("--sweep", default="sweep")
    a = ap.parse_args(argv)

    spec = {p["patient_id"]: p for p in json.loads((ROOT / "data/cohort/patients.json").read_text())["patients"]}
    pa_truth = {r["evaluation_id"]: r for r in json.loads((ROOT / "ground_truth/pa_truth.json").read_text())["evaluations"]}
    crit_truth = {(r["evaluation_id"], r["criterion_id"]): r for r in json.loads((ROOT / "ground_truth/criterion_truth.json").read_text())["rows"]}
    policies = {p["policy_id"]: p for p in load_all()}
    retrieval = {}
    with (ROOT / "results/retrieval/retrieval_results.csv").open() as f:
        for r in csv.DictReader(f):
            for k in ("n_relevant", "n_retrieved", "n_hit", "hard_negatives_retrieved"):
                r[k] = int(r[k])
            for k in ("recall", "precision", "recall_supports", "recall_contradicts", "recall_ambiguous"):
                r[k] = float(r[k]) if r[k] not in ("", "None") else None
            retrieval[(r["patient_id"], r["policy_id"], r["criterion_id"])] = r

    runs = {"gpt": load_run(a.gpt), "hybrid": load_run(a.hybrid)}
    for name, (rows, _) in runs.items():
        assert len(rows) == 150 and not any(r.get("error") for r in rows.values()), f"{name} run incomplete or has errors"

    # -------------------------------------------------------------------------------- patient + criterion rows
    patient_rows, criterion_rows = [], []
    for pipeline, (rows, man) in runs.items():
        for eid, row in sorted(rows.items()):
            t = pa_truth[eid]
            pid, pol_id = row["patient_id"], row["policy_id"]
            acc = case_accounting(row)
            n_crit = len(t["ground_truth"]["criteria"])
            patient_rows.append({
                "run_id": row["run_id"], "evaluation_id": eid, "patient_id": pid, "policy_id": pol_id, "pipeline": pipeline,
                "ground_truth_state": t["ground_truth"]["pa_state"], "predicted_state": row["pa_state"],
                "correct": row["pa_state"] == t["ground_truth"]["pa_state"],
                "ground_truth_binary": t["ground_truth"]["binary_auto_ready"], "predicted_binary": row["binary_auto_ready"],
                "difficulty": t["difficulty"], "challenge_tags": t["challenge_tags"],
                **acc,
                "escalated": bool(row.get("escalated_criteria")), "n_escalated_criteria": len(row.get("escalated_criteria", [])),
                "review_required": row["pa_state"] == "REVIEW_REQUIRED",
                "model_self_reported_state": (row.get("model_self_reported") or {}).get("pa_state"),
                "criteria_correct": sum(row["criteria"][c]["status"] == crit_truth[(eid, c)]["status"] for c in t["ground_truth"]["criteria"]),
                "criteria_total": n_crit,
            })
            # cost/token attribution to criteria
            gpt_dec = [c for c in row["calls"] if c["provider"] == "openai" and c["stage"] != "narrative"]
            jev_calls = [c for c in row["calls"] if c["provider"] == "jev"]
            jev_crit = [c for c, v in row["criteria"].items() if v["engine"] in ("jev", "gpt_escalation")]
            esc = row.get("escalated_criteria", [])
            for cid in t["ground_truth"]["criteria"]:
                pred = row["criteria"][cid]
                truth = crit_truth[(eid, cid)]
                cdef = next(c for c in policies[pol_id]["criteria"] if c["criterion_id"] == cid)
                if pipeline == "gpt":
                    call = gpt_dec[0]
                    in_t, out_t, cost_c, lat_c = call["input_tokens"] / n_crit, call["output_tokens"] / n_crit, (record_cost(call) or 0) / n_crit, call["latency_ms"]
                else:
                    in_t = out_t = cost_c = 0.0
                    lat_c = 0.0
                    if cid in jev_crit and jev_calls:
                        jc = jev_calls[0]
                        in_t += jc["input_tokens"] / len(jev_crit)
                        cost_c += (record_cost(jc) or 0) / len(jev_crit)
                        lat_c += jc["latency_ms"]
                    if cid in esc and gpt_dec:
                        gc = gpt_dec[0]
                        in_t += gc["input_tokens"] / len(esc)
                        out_t += gc["output_tokens"] / len(esc)
                        cost_c += (record_cost(gc) or 0) / len(esc)
                        lat_c += gc["latency_ms"]
                ret = retrieval.get((pid, pol_id, cid))
                correct = pred["status"] == truth["status"]
                jev_status = pred.get("jev_status") if pred.get("escalated") else (pred["status"] if pred["engine"] == "jev" else None)
                jev_conf = pred.get("jev_confidence") if pred.get("escalated") else (pred.get("confidence") if pred["engine"] == "jev" else None)
                fc = {"failure_category": "", "secondary_flags": []}
                if not correct:
                    fc = categorize(criterion_id=cid, truth=truth["status"], pred=pred["status"], engine=pred["engine"],
                                    confidence=pred.get("confidence"), challenge_tags=t["challenge_tags"], retrieval=ret)
                criterion_rows.append({
                    "run_id": row["run_id"], "evaluation_id": eid, "patient_id": pid, "policy_id": pol_id, "pipeline": pipeline,
                    "criterion_id": cid, "criterion_type": cdef["type"], "difficulty": t["difficulty"], "challenge_tags": t["challenge_tags"],
                    "ground_truth": truth["status"], "prediction": pred["status"], "correct": correct,
                    "engine": pred["engine"], "confidence": pred.get("confidence"),
                    "jev_prediction": jev_status, "jev_confidence": jev_conf,
                    "retrieved_evidence_ids": (ret["retrieved_ids"].split(";") if ret and ret["retrieved_ids"] else []),
                    "cited_evidence_ids": pred.get("evidence_ids", []),
                    "supporting_evidence_found": (ret["recall_supports"] or 0) > 0 if ret and ret["recall_supports"] is not None else None,
                    "contradicting_evidence_found": (ret["recall_contradicts"] or 0) > 0 if ret and ret["recall_contradicts"] is not None else None,
                    "latency_ms": lat_c, "input_tokens": in_t, "output_tokens": out_t, "cost_usd": cost_c,
                    "escalated_to_gpt": bool(pred.get("escalated")),
                    "escalation_effect": escalation_effect(pred.get("jev_status"), pred["status"], truth["status"]) if pred.get("escalated") else "",
                    "failure_category": fc["failure_category"], "secondary_flags": fc["secondary_flags"],
                    "truth_rationale": truth["rationale"], "model_rationale": pred.get("rationale", ""),
                })

    # -------------------------------------------------------------------------------- aggregate metrics per pipeline
    def pa_metrics(prs):
        m = prf([r["ground_truth_state"] for r in prs], [r["predicted_state"] for r in prs], PA_CLASSES)
        b = binary([r["ground_truth_binary"] for r in prs], [r["predicted_binary"] for r in prs])
        return m, b

    summary = {"experiment": {"patients": 50, "policies": 3, "evaluations_per_pipeline": 150, "request_date": "2026-09-01",
                              "policy_ids": sorted(policies), "runs": {k: v[1]["run_id"] for k, v in runs.items()}}}
    per_pipe = {}
    for pipeline in runs:
        prs = [r for r in patient_rows if r["pipeline"] == pipeline]
        crs = [r for r in criterion_rows if r["pipeline"] == pipeline]
        m, b = pa_metrics(prs)
        ci_acc = cluster_bootstrap_ci(prs, lambda s: sum(r["correct"] for r in s) / len(s))
        ci_f1 = cluster_bootstrap_ci(prs, lambda s: prf([r["ground_truth_state"] for r in s], [r["predicted_state"] for r in s], PA_CLASSES)["macro_f1"])
        cm = prf([r["ground_truth"] for r in crs], [r["prediction"] for r in crs], STATUS_CLASSES)
        sem = [r for r in crs if r["criterion_type"] != "deterministic"]
        cm_sem = prf([r["ground_truth"] for r in sem], [r["prediction"] for r in sem], STATUS_CLASSES)
        tot = lambda k: sum(r[k] for r in prs)  # noqa: E731
        lat_tot, lat_dec = percentiles([r["total_latency_ms"] for r in prs]), percentiles([r["decision_latency_ms"] for r in prs])
        per_pipe[pipeline] = {
            "pa_accuracy": m["accuracy"], "pa_accuracy_ci95": ci_acc, "pa_macro_f1": m["macro_f1"], "pa_macro_f1_ci95": ci_f1,
            "pa_per_state": {k: {kk: r6(vv) for kk, vv in v.items()} for k, v in m["per_class"].items()},
            "pa_confusion": m["confusion"], "binary_auto_ready": b,
            "criterion_accuracy": cm["accuracy"], "criterion_macro_f1": cm["macro_f1"],
            "semantic_criterion_accuracy": cm_sem["accuracy"], "semantic_criterion_macro_f1": cm_sem["macro_f1"],
            "total_cost_usd": tot("total_cost_usd"), "cost_per_pa_usd": tot("total_cost_usd") / len(prs),
            "gpt_cost_usd": tot("gpt_cost_usd"), "jev_cost_usd": tot("jev_cost_usd"),
            "decision_cost_usd": tot("decision_cost_usd"), "decision_cost_per_pa_usd": tot("decision_cost_usd") / len(prs),
            "narrative_cost_usd": tot("narrative_cost_usd"),
            "gpt_calls": tot("gpt_calls"), "gpt_decision_calls": tot("gpt_decision_calls"), "narrative_calls": tot("narrative_calls"),
            "jev_calls": tot("jev_calls"),
            "gpt_input_tokens": tot("gpt_input_tokens"), "gpt_output_tokens": tot("gpt_output_tokens"),
            "gpt_reasoning_tokens": tot("gpt_reasoning_tokens"),
            "gpt_decision_input_tokens": tot("gpt_decision_input_tokens"), "gpt_decision_output_tokens": tot("gpt_decision_output_tokens"),
            "jev_input_tokens": tot("jev_input_tokens"),
            "latency_total_ms": lat_tot, "latency_decision_ms": lat_dec,
            "p50_latency_ms": lat_tot["p50"], "p95_latency_ms": lat_tot["p95"],
            "p50_decision_latency_ms": lat_dec["p50"], "p95_decision_latency_ms": lat_dec["p95"],
            "median_context_reduction_pct": percentiles([r["context_reduction_pct"] for r in prs])["median"],
            "median_frontier_context_reduction_pct": percentiles([r["frontier_context_reduction_pct"] for r in prs])["median"],
            "cases_escalated": sum(r["escalated"] for r in prs), "criteria_escalated": sum(r["escalated_to_gpt"] for r in crs),
            "review_required_predicted": sum(r["review_required"] for r in prs),
        }
        if pipeline == "gpt":
            per_pipe[pipeline]["self_reported_state_consistency"] = sum(r["model_self_reported_state"] == r["predicted_state"] for r in prs) / len(prs)
    g, h = per_pipe["gpt"], per_pipe["hybrid"]
    h["gpt_calls_avoided_pct"] = 100 * (1 - h["gpt_calls"] / g["gpt_calls"])
    h["gpt_decision_calls_avoided_pct"] = 100 * (1 - h["gpt_decision_calls"] / g["gpt_decision_calls"])
    h["gpt_tokens_avoided_pct"] = 100 * (1 - (h["gpt_input_tokens"] + h["gpt_output_tokens"]) / (g["gpt_input_tokens"] + g["gpt_output_tokens"]))
    h["gpt_decision_tokens_avoided_pct"] = 100 * (1 - (h["gpt_decision_input_tokens"] + h["gpt_decision_output_tokens"])
                                                   / (g["gpt_decision_input_tokens"] + g["gpt_decision_output_tokens"]))
    h["cost_reduction_pct"] = 100 * (1 - h["total_cost_usd"] / g["total_cost_usd"])
    h["decision_cost_reduction_pct"] = 100 * (1 - h["decision_cost_usd"] / g["decision_cost_usd"])

    # paired comparison
    gp = {r["evaluation_id"]: r["correct"] for r in patient_rows if r["pipeline"] == "gpt"}
    hp = {r["evaluation_id"]: r["correct"] for r in patient_rows if r["pipeline"] == "hybrid"}
    ids = sorted(gp)
    paired = mcnemar_exact([gp[i] for i in ids], [hp[i] for i in ids])
    diff_rows = [{"patient_id": i.split("__")[0], "d": int(hp[i]) - int(gp[i])} for i in ids]
    paired["accuracy_difference_hybrid_minus_gpt"] = sum(r["d"] for r in diff_rows) / len(diff_rows)
    paired["accuracy_difference_ci95"] = cluster_bootstrap_ci(diff_rows, lambda s: sum(r["d"] for r in s) / len(s))
    paired["note"] = "a = GPT-only, b = hybrid; exact two-sided McNemar on PA-state correctness; CI = patient-cluster bootstrap"
    gc = {(r["evaluation_id"], r["criterion_id"]): r["correct"] for r in criterion_rows if r["pipeline"] == "gpt"}
    hc = {(r["evaluation_id"], r["criterion_id"]): r["correct"] for r in criterion_rows if r["pipeline"] == "hybrid"}
    ck = sorted(gc)
    paired_crit = mcnemar_exact([gc[k] for k in ck], [hc[k] for k in ck])

    # escalation effect
    esc = Counter(r["escalation_effect"] for r in criterion_rows if r["pipeline"] == "hybrid" and r["escalated_to_gpt"])

    # -------------------------------------------------------------------------------- calibration
    hyb_c = [r for r in criterion_rows if r["pipeline"] == "hybrid" and r["jev_prediction"] is not None]
    jev_cal = calibration([r["jev_confidence"] for r in hyb_c], [r["jev_prediction"] == r["ground_truth"] for r in hyb_c])
    scope = {(r["evaluation_id"], r["criterion_id"]) for r in hyb_c}
    gpt_c_all = [r for r in criterion_rows if r["pipeline"] == "gpt" and r["confidence"] is not None]
    gpt_c_same = [r for r in gpt_c_all if (r["evaluation_id"], r["criterion_id"]) in scope]
    gpt_cal = calibration([min(1.0, max(0.0, r["confidence"])) for r in gpt_c_same], [r["correct"] for r in gpt_c_same])
    gpt_cal_all = calibration([min(1.0, max(0.0, r["confidence"])) for r in gpt_c_all], [r["correct"] for r in gpt_c_all])
    cal_rows = []
    for name, c, sc in (("jev", jev_cal, "criteria evaluated by Jev (pre-routing confidence)"),
                        ("gpt", gpt_cal, "same criterion set, GPT self-reported confidence"),
                        ("gpt", gpt_cal_all, "all criteria, GPT self-reported confidence")):
        for b in c["bins"]:
            cal_rows.append({"model": name, "scope": sc, **b, "brier": c["brier"], "ece": c["ece"], "n_total": c["n"]})

    # -------------------------------------------------------------------------------- threshold sweep (+ selective prediction)
    sweep_rows = []
    base = per_pipe["gpt"]
    for thr in THRESHOLDS:
        rid = f"{a.sweep}_t{thr:.2f}"
        if not (ROOT / "results/runs" / rid).exists():
            continue
        rows, _ = load_run(rid)
        prs = []
        crit_all, jev_kept = [], []
        for eid, row in rows.items():
            t = pa_truth[eid]
            prs.append({"patient_id": row["patient_id"], "ground_truth_state": t["ground_truth"]["pa_state"],
                        "predicted_state": row["pa_state"], **case_accounting(row)})
            for cid, p in row["criteria"].items():
                tr = crit_truth[(eid, cid)]["status"]
                crit_all.append(p["status"] == tr)
                if p["engine"] == "jev":
                    jev_kept.append(p["status"] == tr)
        m = prf([r["ground_truth_state"] for r in prs], [r["predicted_state"] for r in prs], PA_CLASSES)
        n_jev_eval = sum(1 for row in rows.values() for p in row["criteria"].values() if p["engine"] in ("jev", "gpt_escalation"))
        tot = lambda k: sum(r[k] for r in prs)  # noqa: E731
        sweep_rows.append({
            "threshold": thr, "run_id": rid, "pa_accuracy": m["accuracy"], "pa_macro_f1": m["macro_f1"],
            "criterion_accuracy": sum(crit_all) / len(crit_all),
            "jev_evaluated_criteria": n_jev_eval, "jev_coverage": len(jev_kept) / n_jev_eval,
            "criteria_escalated": n_jev_eval - len(jev_kept), "criterion_escalation_rate": 1 - len(jev_kept) / n_jev_eval,
            "cases_escalated": sum(1 for row in rows.values() if row.get("escalated_criteria")),
            "case_escalation_rate": sum(1 for row in rows.values() if row.get("escalated_criteria")) / len(rows),
            "jev_auto_decision_accuracy": sum(jev_kept) / len(jev_kept) if jev_kept else None,
            "jev_auto_decision_error_rate": 1 - sum(jev_kept) / len(jev_kept) if jev_kept else None,
            "gpt_calls": tot("gpt_calls"), "gpt_decision_calls": tot("gpt_decision_calls"),
            "gpt_calls_avoided_pct": 100 * (1 - tot("gpt_calls") / base["gpt_calls"]),
            "gpt_decision_calls_avoided_pct": 100 * (1 - tot("gpt_decision_calls") / base["gpt_decision_calls"]),
            "gpt_tokens": tot("gpt_input_tokens") + tot("gpt_output_tokens"),
            "gpt_tokens_avoided_pct": 100 * (1 - (tot("gpt_input_tokens") + tot("gpt_output_tokens")) / (base["gpt_input_tokens"] + base["gpt_output_tokens"])),
            "gpt_decision_tokens_avoided_pct": 100 * (1 - (tot("gpt_decision_input_tokens") + tot("gpt_decision_output_tokens"))
                                                        / (base["gpt_decision_input_tokens"] + base["gpt_decision_output_tokens"])),
            "total_cost_usd": tot("total_cost_usd"), "decision_cost_usd": tot("decision_cost_usd"),
            "cost_per_pa_usd": tot("total_cost_usd") / len(prs),
            "p50_latency_ms": percentiles([r["total_latency_ms"] for r in prs])["p50"],
            "p95_latency_ms": percentiles([r["total_latency_ms"] for r in prs])["p95"],
            "p50_decision_latency_ms": percentiles([r["decision_latency_ms"] for r in prs])["p50"],
            "p95_decision_latency_ms": percentiles([r["decision_latency_ms"] for r in prs])["p95"],
            "headline": abs(thr - 0.90) < 1e-9,
        })
    sweep_rows.append({"threshold": "gpt_only", "run_id": a.gpt, "pa_accuracy": base["pa_accuracy"], "pa_macro_f1": base["pa_macro_f1"],
                       "criterion_accuracy": base["criterion_accuracy"], "gpt_calls": base["gpt_calls"],
                       "gpt_decision_calls": base["gpt_decision_calls"], "gpt_calls_avoided_pct": 0.0,
                       "gpt_tokens": base["gpt_input_tokens"] + base["gpt_output_tokens"], "gpt_tokens_avoided_pct": 0.0,
                       "total_cost_usd": base["total_cost_usd"], "decision_cost_usd": base["decision_cost_usd"],
                       "cost_per_pa_usd": base["cost_per_pa_usd"], "p50_latency_ms": base["p50_latency_ms"],
                       "p95_latency_ms": base["p95_latency_ms"], "p50_decision_latency_ms": base["p50_decision_latency_ms"],
                       "p95_decision_latency_ms": base["p95_decision_latency_ms"], "headline": False})

    # -------------------------------------------------------------------------------- failure analysis
    fail_rows = []
    for r in criterion_rows:
        if r["correct"]:
            continue
        pr = next(p for p in patient_rows if p["pipeline"] == r["pipeline"] and p["evaluation_id"] == r["evaluation_id"])
        row = runs[r["pipeline"]][0][r["evaluation_id"]]
        decisive = [c for c in row["calls"] if c["stage"] in ("criterion_evaluation", "gpt_escalation", "criterion_reads")]
        fail_rows.append({
            "pipeline": r["pipeline"], "run_id": r["run_id"], "evaluation_id": r["evaluation_id"], "patient_id": r["patient_id"],
            "policy_id": r["policy_id"], "criterion_id": r["criterion_id"], "ground_truth": r["ground_truth"], "prediction": r["prediction"],
            "pa_state_truth": pr["ground_truth_state"], "pa_state_predicted": pr["predicted_state"], "pa_state_wrong": not pr["correct"],
            "changes_pa_state": not pr["correct"],
            "engine": r["engine"], "confidence": r["confidence"], "jev_prediction": r["jev_prediction"], "jev_confidence": r["jev_confidence"],
            "escalation_effect": r["escalation_effect"], "failure_category": r["failure_category"], "secondary_flags": r["secondary_flags"],
            "difficulty": r["difficulty"], "challenge_tags": r["challenge_tags"],
            "retrieved_evidence_ids": r["retrieved_evidence_ids"], "cited_evidence_ids": r["cited_evidence_ids"],
            "truth_rationale": r["truth_rationale"], "model_rationale": r["model_rationale"],
            "trace_prompt_sha256": [c["prompt_sha256"] for c in decisive], "trace_request_ids": [c.get("request_id") for c in decisive],
            "trace_file": f"results/traces/{r['run_id']}.jsonl",
        })

    # -------------------------------------------------------------------------------- write results/
    RES.mkdir(exist_ok=True)
    write_csv(RES / "patient_results.csv", patient_rows)
    write_csv(RES / "criterion_results.csv", criterion_rows)
    call_rows = []
    for rid in [a.gpt, a.hybrid] + [f"{a.sweep}_t{t:.2f}" for t in THRESHOLDS]:
        d = ROOT / "results/runs" / rid
        if not d.exists():
            continue
        rows, _ = load_run(rid)
        for eid, row in sorted(rows.items()):
            for c in row["calls"]:
                call_rows.append({"run_id": rid, "evaluation_id": eid, "pipeline": row["pipeline"], "stage": c["stage"],
                                  "provider": c["provider"], "model": c["model"], "response_model": c.get("extra", {}).get("response_model"),
                                  "input_tokens": c["input_tokens"], "cached_input_tokens": c["cached_input_tokens"],
                                  "output_tokens": c["output_tokens"], "reasoning_tokens": c["reasoning_tokens"],
                                  "latency_ms": c["latency_ms"], "total_latency_ms": c["total_latency_ms"], "attempts": c["attempts"],
                                  "estimated_cost_usd": record_cost(c), "cache_hit": c.get("extra", {}).get("cache_hit"),
                                  "request_id": c.get("request_id"), "prompt_sha256": c["prompt_sha256"], "error": c.get("error")})
        (RES / "traces").mkdir(exist_ok=True)
        shutil.copy(d / "traces.jsonl", RES / "traces" / f"{rid}.jsonl")
    write_csv(RES / "model_calls.csv", call_rows)
    shutil.copy(ROOT / "results/retrieval/retrieval_results.csv", RES / "retrieval_results.csv")
    write_csv(RES / "calibration.csv", cal_rows)
    write_csv(RES / "threshold_sweep.csv", sweep_rows)
    write_csv(RES / "failure_analysis.csv", fail_rows)

    ret_rows = list(retrieval.values())
    crit_miss = [r for r in ret_rows if r["truth_status"] in ("FAIL", "CONFLICT") and (r["recall_contradicts"] == 0.0 or
                                                                                      (r["recall_contradicts"] is None and r["recall_ambiguous"] == 0.0))]
    retrieval_summary = {
        "queries": len(ret_rows),
        "mean_recall": sum(r["recall"] for r in ret_rows if r["recall"] is not None) / sum(1 for r in ret_rows if r["recall"] is not None),
        "mean_recall_contradicts": (lambda xs: sum(xs) / len(xs))([r["recall_contradicts"] for r in ret_rows if r["recall_contradicts"] is not None]),
        "critical_misses": len(crit_miss),
        "report": "reports/retrieval_eval.md",
    }
    fail_cats = {p: {"all_criterion_errors": dict(Counter(f["failure_category"] for f in fail_rows if f["pipeline"] == p)),
                     "errors_in_pa_state_wrong_cases": dict(Counter(f["failure_category"] for f in fail_rows
                                                                    if f["pipeline"] == p and f["pa_state_wrong"]))} for p in runs}

    summary.update({
        "gpt": {k: v for k, v in per_pipe["gpt"].items()},
        "hybrid": {"threshold": 0.90, **per_pipe["hybrid"]},
        "jev": {"model": runs["hybrid"][1]["models"]["jev"], "brier_score": jev_cal["brier"], "ece": jev_cal["ece"], "n": jev_cal["n"],
                "scope": "criterion-level confidence for criteria evaluated by Jev before routing",
                "gpt_same_scope_brier": gpt_cal["brier"], "gpt_same_scope_ece": gpt_cal["ece"]},
        "paired_comparison": {"pa_state": paired, "criterion_status": {**paired_crit, "note": "a = GPT-only, b = hybrid"}},
        "escalation_effect": dict(esc),
        "threshold_sweep": [{k: r6(v) if isinstance(v, float) else v for k, v in r.items()} for r in sweep_rows],
        "retrieval": retrieval_summary,
        "failure_categories": fail_cats,
        "pricing_version": load_pricing()["pricing_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limitations": [
            "n = 150 evaluations (50 synthetic patients x 3 policies); cases are challenge-stratified, not epidemiologically representative.",
            "Evaluations of the same patient are correlated; CIs use a patient-cluster bootstrap.",
            "Hybrid questions/rules were revised once after a 5-patient smoke test on this cohort (no separate dev set); GPT baseline received one provenance formatting fix.",
            "Ground truth derives from user-approved policy interpretations; some labels (REVIEW_REQUIRED cases) encode judgment calls.",
            "Headline threshold 0.90 was fixed before the runs; the sweep is sensitivity analysis, not selection.",
            "Latency measured application-side with concurrency 4; GPT latency depends on provider load at run time.",
            "Clinical notes were authored by an LLM (Claude) from structured plans; distribution differs from real EHR text.",
        ],
    })
    manifest = {"evaluation_generated_at": summary["generated_at"], "evaluation_script": "scripts/evaluate.py",
                "runs": {k: v[1] for k, v in runs.items()},
                "sweep_runs": [f"{a.sweep}_t{t:.2f}" for t in THRESHOLDS],
                "ground_truth": ["ground_truth/pa_truth.json", "ground_truth/criterion_truth.json", "ground_truth/evidence_map.json"]}
    (RES / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (RES / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")

    # -------------------------------------------------------------------------------- presentation_results/
    PRES.mkdir(exist_ok=True)
    comp = []

    def addm(metric, gv, hv, unit="", note=""):
        comp.append({"metric": metric, "gpt_only": r6(gv) if isinstance(gv, float) else gv,
                     "jev_plus_gpt": r6(hv) if isinstance(hv, float) else hv,
                     "difference_hybrid_minus_gpt": r6(hv - gv) if isinstance(gv, (int, float)) and isinstance(hv, (int, float)) else "",
                     "unit": unit, "note": note})
    addm("pa_accuracy", g["pa_accuracy"], h["pa_accuracy"], "fraction", f"95% CI gpt {g['pa_accuracy_ci95']} hybrid {h['pa_accuracy_ci95']}")
    addm("pa_macro_f1", g["pa_macro_f1"], h["pa_macro_f1"], "", f"95% CI gpt {g['pa_macro_f1_ci95']} hybrid {h['pa_macro_f1_ci95']}")
    for s in PA_CLASSES:
        addm(f"recall_{s}", g["pa_per_state"][s]["recall"], h["pa_per_state"][s]["recall"], "fraction", "per-state accuracy")
    addm("binary_auto_ready_f1", g["binary_auto_ready"]["f1"], h["binary_auto_ready"]["f1"])
    addm("false_auto_submissions", g["binary_auto_ready"]["fp"], h["binary_auto_ready"]["fp"], "count", "predicted READY, truth not READY")
    addm("criterion_accuracy", g["criterion_accuracy"], h["criterion_accuracy"], "fraction")
    addm("criterion_macro_f1", g["criterion_macro_f1"], h["criterion_macro_f1"])
    addm("semantic_criterion_accuracy", g["semantic_criterion_accuracy"], h["semantic_criterion_accuracy"], "fraction", "non-deterministic criteria")
    addm("total_cost_usd", g["total_cost_usd"], h["total_cost_usd"], "USD", "150 PAs, end-to-end")
    addm("cost_per_pa_usd", g["cost_per_pa_usd"], h["cost_per_pa_usd"], "USD")
    addm("decision_cost_per_pa_usd", g["decision_cost_per_pa_usd"], h["decision_cost_per_pa_usd"], "USD", "excludes hybrid READY-case narratives")
    addm("gpt_calls", g["gpt_calls"], h["gpt_calls"], "count")
    addm("gpt_decision_calls", g["gpt_decision_calls"], h["gpt_decision_calls"], "count")
    addm("jev_calls", g["jev_calls"], h["jev_calls"], "count")
    addm("gpt_input_tokens", g["gpt_input_tokens"], h["gpt_input_tokens"], "tokens")
    addm("gpt_output_tokens", g["gpt_output_tokens"], h["gpt_output_tokens"], "tokens", "includes reasoning tokens")
    addm("jev_input_tokens", g["jev_input_tokens"], h["jev_input_tokens"], "tokens")
    addm("p50_latency_ms", g["p50_latency_ms"], h["p50_latency_ms"], "ms", "end-to-end incl. hybrid narrative")
    addm("p95_latency_ms", g["p95_latency_ms"], h["p95_latency_ms"], "ms", "end-to-end incl. hybrid narrative")
    addm("p50_decision_latency_ms", g["p50_decision_latency_ms"], h["p50_decision_latency_ms"], "ms")
    addm("p95_decision_latency_ms", g["p95_decision_latency_ms"], h["p95_decision_latency_ms"], "ms")
    addm("median_context_reduction_pct", g["median_context_reduction_pct"], h["median_context_reduction_pct"], "%", "1 - model input tokens / raw chart tokens")
    addm("median_frontier_context_reduction_pct", g["median_frontier_context_reduction_pct"], h["median_frontier_context_reduction_pct"], "%", "GPT input only")
    addm("criterion_confidence_brier", gpt_cal["brier"], jev_cal["brier"], "", "same criterion scope; GPT self-reported vs Jev pre-routing")
    addm("criterion_confidence_ece", gpt_cal["ece"], jev_cal["ece"])
    write_csv(PRES / "pipeline_comparison.csv", comp)

    cp = []
    for pipeline in runs:
        crs = [r for r in criterion_rows if r["pipeline"] == pipeline]
        for (pol, cid) in sorted({(r["policy_id"], r["criterion_id"]) for r in crs}):
            sub = [r for r in crs if r["policy_id"] == pol and r["criterion_id"] == cid]
            m = prf([r["ground_truth"] for r in sub], [r["prediction"] for r in sub], STATUS_CLASSES)
            pbin = binary([r["ground_truth"] == "PASS" for r in sub], [r["prediction"] == "PASS" for r in sub])
            cp.append({"pipeline": pipeline, "policy_id": pol, "criterion_id": cid, "criterion_type": sub[0]["criterion_type"], "n": len(sub),
                       "accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "pass_precision": pbin["precision"], "pass_recall": pbin["recall"],
                       "pass_f1": pbin["f1"], "errors": sum(not r["correct"] for r in sub),
                       "engine_counts": json.dumps(Counter(r["engine"] for r in sub)), "escalated": sum(r["escalated_to_gpt"] for r in sub)})
    write_csv(PRES / "criterion_performance.csv", cp)

    chp = []
    for pipeline in runs:
        prs = [r for r in patient_rows if r["pipeline"] == pipeline]
        groups = defaultdict(list)
        for r in prs:
            groups[("difficulty", r["difficulty"])].append(r)
            for tg in r["challenge_tags"]:
                groups[("challenge_tag", tg)].append(r)
        for (kind, k), rs in sorted(groups.items()):
            chp.append({"pipeline": pipeline, "group_type": kind, "group": k, "n_evaluations": len(rs),
                        "pa_accuracy": sum(r["correct"] for r in rs) / len(rs),
                        "criterion_accuracy": sum(r["criteria_correct"] for r in rs) / sum(r["criteria_total"] for r in rs),
                        "errors": sum(not r["correct"] for r in rs), "mean_cost_usd": sum(r["total_cost_usd"] for r in rs) / len(rs),
                        "cases_escalated": sum(r["escalated"] for r in rs)})
    write_csv(PRES / "challenge_performance.csv", chp)

    cost_rows = []
    for pipeline in runs:
        prs = [r for r in patient_rows if r["pipeline"] == pipeline]
        tot = lambda k: sum(r[k] for r in prs)  # noqa: E731
        for comp_name, key in (("gpt_decision", "gpt_decision_cost_usd"), ("gpt_narrative", "narrative_cost_usd"),
                               ("jev", "jev_cost_usd"), ("total", "total_cost_usd"), ("decision_only_total", "decision_cost_usd")):
            cost_rows.append({"pipeline": pipeline, "component": comp_name, "total_usd": tot(key), "per_pa_usd": tot(key) / len(prs),
                              "calls": {"gpt_decision": tot("gpt_decision_calls"), "gpt_narrative": tot("narrative_calls"),
                                        "jev": tot("jev_calls")}.get(comp_name, ""),
                              "input_tokens": {"gpt_decision": tot("gpt_decision_input_tokens"), "jev": tot("jev_input_tokens"),
                                               "gpt_narrative": tot("gpt_input_tokens") - tot("gpt_decision_input_tokens")}.get(comp_name, ""),
                              "output_tokens": {"gpt_decision": tot("gpt_decision_output_tokens"),
                                                "gpt_narrative": tot("gpt_output_tokens") - tot("gpt_decision_output_tokens"),
                                                "jev": tot("jev_output_tokens")}.get(comp_name, ""),
                              "pricing_version": summary["pricing_version"]})
    write_csv(PRES / "cost_analysis.csv", cost_rows)

    lat_rows = []
    for pipeline in runs:
        prs = [r for r in patient_rows if r["pipeline"] == pipeline]
        for stage in ("retrieval_latency_ms", "rules_latency_ms", "jev_latency_ms", "gpt_latency_ms", "narrative_latency_ms",
                      "decision_latency_ms", "total_latency_ms"):
            vals = [r[stage] for r in prs]
            if pipeline == "gpt" and stage == "gpt_latency_ms":
                vals = [r["total_latency_ms"] - r["retrieval_latency_ms"] for r in prs]
            lat_rows.append({"pipeline": pipeline, "stage": stage.replace("_latency_ms", ""), **{k: r6(v) if isinstance(v, float) else v
                                                                                                 for k, v in percentiles(vals).items()}})
    write_csv(PRES / "latency_analysis.csv", lat_rows)
    for f in ("calibration.csv", "threshold_sweep.csv", "failure_analysis.csv"):
        shutil.copy(RES / f, PRES / f)

    # interesting cases (objective selection; no characterization of which pipeline is better)
    by = {(r["pipeline"], r["evaluation_id"]): r for r in patient_rows}
    cases = []

    def case(reason, eid, extra=None):
        gpr, hpr = by[("gpt", eid)], by[("hybrid", eid)]
        cases.append({"selection_criterion": reason, "evaluation_id": eid, "patient_id": gpr["patient_id"], "policy_id": gpr["policy_id"],
                      "difficulty": gpr["difficulty"], "challenge_tags": gpr["challenge_tags"], "ground_truth_state": gpr["ground_truth_state"],
                      "gpt_only": {k: gpr[k] for k in ("predicted_state", "correct", "total_cost_usd", "total_latency_ms", "gpt_input_tokens", "gpt_output_tokens")},
                      "jev_plus_gpt": {k: hpr[k] for k in ("predicted_state", "correct", "total_cost_usd", "decision_latency_ms", "total_latency_ms",
                                                           "jev_input_tokens", "gpt_input_tokens", "n_escalated_criteria")},
                      "criteria": [{k: c[k] for k in ("pipeline", "criterion_id", "ground_truth", "prediction", "engine", "confidence",
                                                       "jev_prediction", "jev_confidence", "escalation_effect", "failure_category")}
                                   for c in criterion_rows if c["evaluation_id"] == eid and (not c["correct"] or c["escalated_to_gpt"])],
                      "trace_files": [f"results/traces/{a.gpt}.jsonl", f"results/traces/{a.hybrid}.jsonl"], **(extra or {})})
    ids_sorted = sorted(pa_truth)
    for eid in ids_sorted:
        if by[("gpt", eid)]["correct"] and not by[("hybrid", eid)]["correct"]:
            case("gpt_correct_hybrid_wrong", eid)
    for eid in ids_sorted:
        if by[("hybrid", eid)]["correct"] and not by[("gpt", eid)]["correct"]:
            case("hybrid_correct_gpt_wrong", eid)
    hi_err = sorted((c for c in criterion_rows if c["pipeline"] == "hybrid" and c["jev_prediction"] is not None
                     and c["jev_prediction"] != c["ground_truth"] and (c["jev_confidence"] or 0) >= 0.9),
                    key=lambda c: -c["jev_confidence"])
    if hi_err:
        case("jev_high_confidence_error", hi_err[0]["evaluation_id"], {"focus_criterion": hi_err[0]["criterion_id"]})
    fixed = [c for c in criterion_rows if c["escalation_effect"] == "escalation_fixed"]
    if fixed:
        case("jev_uncertain_gpt_resolved", min(fixed, key=lambda c: c["jev_confidence"])["evaluation_id"], {"focus_criterion": min(fixed, key=lambda c: c["jev_confidence"])["criterion_id"]})
    broke = sorted((c for c in criterion_rows if c["escalation_effect"] == "escalation_broke"),
                   key=lambda c: (by[("hybrid", c["evaluation_id"])]["correct"], c["evaluation_id"]))   # prefer PA-impacting
    if broke:
        case("escalation_changed_correct_jev_answer", broke[0]["evaluation_id"], {"focus_criterion": broke[0]["criterion_id"]})
    rf = [f for f in fail_rows if f["failure_category"] == "RETRIEVAL_FAILURE"]
    if rf:
        case("retrieval_failure", rf[0]["evaluation_id"], {"focus_criterion": rf[0]["criterion_id"]})
    for tag, reason in (("medication_reconciliation", "contradiction_medication"), ("noncontinuous_duration", "temporal_reasoning")):
        cand = [e for e in ids_sorted if tag in pa_truth[e]["challenge_tags"] and pa_truth[e]["ground_truth"]["pa_state"] != "READY"]
        if cand:
            case(reason, cand[0])
    hy = [r for r in patient_rows if r["pipeline"] == "hybrid"]
    big = max(hy, key=lambda r: by[("gpt", r["evaluation_id"])]["gpt_input_tokens"] - r["gpt_input_tokens"])
    case("largest_gpt_token_saving", big["evaluation_id"])
    slow = max(hy, key=lambda r: r["decision_latency_ms"])
    case("unusual_latency_hybrid_max_decision_latency", slow["evaluation_id"])
    seen, uniq = set(), []
    for c in cases:
        k = (c["selection_criterion"], c["evaluation_id"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    (PRES / "interesting_cases.json").write_text(json.dumps({"note": "Selected by objective criteria; measurements only.",
                                                             "cases": uniq}, indent=2, ensure_ascii=False, default=str) + "\n")
    exec_sum = {"note": "Measurements only; interpretation intentionally omitted.", "experiment": summary["experiment"],
                "gpt_only": {k: g[k] for k in ("pa_accuracy", "pa_accuracy_ci95", "pa_macro_f1", "criterion_accuracy", "total_cost_usd",
                                               "cost_per_pa_usd", "gpt_calls", "gpt_input_tokens", "gpt_output_tokens", "p50_latency_ms",
                                               "p95_latency_ms", "median_context_reduction_pct")},
                "jev_plus_gpt": {k: h[k] for k in ("pa_accuracy", "pa_accuracy_ci95", "pa_macro_f1", "criterion_accuracy", "total_cost_usd",
                                                   "cost_per_pa_usd", "decision_cost_per_pa_usd", "gpt_calls", "gpt_decision_calls", "jev_calls",
                                                   "gpt_input_tokens", "gpt_output_tokens", "jev_input_tokens", "p50_latency_ms", "p95_latency_ms",
                                                   "p50_decision_latency_ms", "p95_decision_latency_ms", "gpt_calls_avoided_pct",
                                                   "gpt_decision_calls_avoided_pct", "gpt_tokens_avoided_pct", "cost_reduction_pct",
                                                   "cases_escalated", "criteria_escalated", "median_context_reduction_pct")},
                "threshold": 0.90, "jev_calibration": summary["jev"], "paired_comparison": summary["paired_comparison"],
                "escalation_effect": summary["escalation_effect"], "retrieval": retrieval_summary,
                "failure_categories": fail_cats, "limitations": summary["limitations"]}
    (PRES / "executive_summary.json").write_text(json.dumps(exec_sum, indent=2, ensure_ascii=False, default=str) + "\n")
    (PRES / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({"gpt": {k: g[k] for k in ("pa_accuracy", "pa_accuracy_ci95", "criterion_accuracy", "total_cost_usd", "p50_latency_ms", "p95_latency_ms")},
                      "hybrid": {k: h[k] for k in ("pa_accuracy", "pa_accuracy_ci95", "criterion_accuracy", "total_cost_usd", "decision_cost_usd",
                                                   "p50_decision_latency_ms", "p95_decision_latency_ms", "gpt_calls_avoided_pct", "gpt_tokens_avoided_pct")},
                      "paired": paired, "escalation": dict(esc), "jev_cal": {"brier": jev_cal["brier"], "ece": jev_cal["ece"], "n": jev_cal["n"]},
                      "gpt_cal": {"brier": gpt_cal["brier"], "ece": gpt_cal["ece"], "n": gpt_cal["n"]}, "failures": fail_cats,
                      "interesting": len(uniq)}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
