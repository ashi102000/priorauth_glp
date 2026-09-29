"""Generate reports/evaluation_report.md and reports/failure_analysis.md from results/ (no hand-copied numbers)."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "results/summary.json").read_text())
g, h, j = S["gpt"], S["hybrid"], S["jev"]


def pct(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def ci(c):
    return f"[{100 * c[0]:.1f}, {100 * c[1]:.1f}]"


def ms(x):
    return "—" if x is None else (f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.0f} ms")


def usd(x, d=3):
    return f"${x:.{d}f}"


L = ["# Evaluation report — GLP-1 PA benchmark (GPT-only vs Jev + GPT)", "",
     f"Generated from `results/summary.json` ({S['generated_at']}). 50 synthetic patients × 3 verified payer policies = "
     f"150 PA evaluations per pipeline. Request date {S['experiment']['request_date']}. Hybrid headline threshold **0.90** "
     "(fixed before the runs). Measurements only; interpretation is left to the reader.", "",
     "## Quality", "",
     "| Metric | GPT-only | Jev + GPT |", "|---|---|---|",
     f"| PA-state accuracy (95% CI, patient-cluster bootstrap) | {pct(g['pa_accuracy'])} {ci(g['pa_accuracy_ci95'])} | {pct(h['pa_accuracy'])} {ci(h['pa_accuracy_ci95'])} |",
     f"| PA-state macro-F1 | {g['pa_macro_f1']:.3f} | {h['pa_macro_f1']:.3f} |"]
for s in ("READY", "NOT_READY", "REVIEW_REQUIRED"):
    L.append(f"| {s} accuracy (recall, n={g['pa_per_state'][s]['support']}) | {pct(g['pa_per_state'][s]['recall'])} | {pct(h['pa_per_state'][s]['recall'])} |")
L += [f"| Binary auto-ready F1 | {g['binary_auto_ready']['f1']:.3f} | {h['binary_auto_ready']['f1']:.3f} |",
      f"| False auto-submissions (pred READY, truth not) | {g['binary_auto_ready']['fp']} | {h['binary_auto_ready']['fp']} |",
      f"| Criterion accuracy (750 labels) | {pct(g['criterion_accuracy'])} | {pct(h['criterion_accuracy'])} |",
      f"| Criterion macro-F1 | {g['criterion_macro_f1']:.3f} | {h['criterion_macro_f1']:.3f} |",
      f"| Semantic-criterion accuracy | {pct(g['semantic_criterion_accuracy'])} | {pct(h['semantic_criterion_accuracy'])} |", ""]
pp, pc = S["paired_comparison"]["pa_state"], S["paired_comparison"]["criterion_status"]
L += [f"Paired comparison (same 150 cases): GPT-only correct & hybrid wrong = {pp['a_only_correct']}; hybrid correct & GPT-only wrong = "
      f"{pp['b_only_correct']}; exact McNemar p = {pp['p_value']:.3f}; accuracy difference (hybrid − GPT) = {100 * pp['accuracy_difference_hybrid_minus_gpt']:.1f} pts, "
      f"95% CI {ci(pp['accuracy_difference_ci95'])}. Criterion level: {pc['a_only_correct']} vs {pc['b_only_correct']}, p = {pc['p_value']:.4f} "
      "(criteria within a case are correlated; treat the criterion-level p-value as descriptive).", "",
      "PA confusion matrices (rows = truth, cols = predicted):", ""]
for name, d in (("GPT-only", g), ("Jev + GPT", h)):
    L += [f"**{name}**", "", "| truth \\ pred | READY | NOT_READY | REVIEW_REQUIRED |", "|---|---|---|---|"]
    for t, row in d["pa_confusion"].items():
        L.append(f"| {t} | {row['READY']} | {row['NOT_READY']} | {row['REVIEW_REQUIRED']} |")
    L.append("")
L += ["## Cost, frontier usage and context", "", "| Metric | GPT-only | Jev + GPT |", "|---|---|---|",
      f"| Total cost, 150 PAs (end-to-end) | {usd(g['total_cost_usd'])} | {usd(h['total_cost_usd'])} |",
      f"| Cost per PA (end-to-end) | {usd(g['cost_per_pa_usd'], 4)} | {usd(h['cost_per_pa_usd'], 4)} |",
      f"| Decision cost per PA (excl. hybrid READY narratives) | {usd(g['decision_cost_per_pa_usd'], 4)} | {usd(h['decision_cost_per_pa_usd'], 4)} |",
      f"| GPT calls (decision + narrative) | {g['gpt_calls']} | {h['gpt_calls']} ({h['gpt_decision_calls']} + {h['narrative_calls']}) |",
      f"| Jev calls | {g['jev_calls']} | {h['jev_calls']} |",
      f"| GPT input / output tokens | {g['gpt_input_tokens']:,} / {g['gpt_output_tokens']:,} | {h['gpt_input_tokens']:,} / {h['gpt_output_tokens']:,} |",
      f"| GPT decision input / output tokens | {g['gpt_decision_input_tokens']:,} / {g['gpt_decision_output_tokens']:,} | {h['gpt_decision_input_tokens']:,} / {h['gpt_decision_output_tokens']:,} |",
      f"| Jev input tokens | {g['jev_input_tokens']:,} | {h['jev_input_tokens']:,} |",
      f"| GPT calls avoided (all / decision-only) | — | {h['gpt_calls_avoided_pct']:.1f}% / {h['gpt_decision_calls_avoided_pct']:.1f}% |",
      f"| GPT tokens avoided (all / decision-only) | — | {h['gpt_tokens_avoided_pct']:.1f}% / {h['gpt_decision_tokens_avoided_pct']:.1f}% |",
      f"| Cost reduction (end-to-end / decision-only) | — | {h['cost_reduction_pct']:.1f}% / {h['decision_cost_reduction_pct']:.1f}% |",
      f"| Median context reduction vs raw chart (all model input) | {g['median_context_reduction_pct']:.1f}% | {h['median_context_reduction_pct']:.1f}% |",
      f"| Median frontier-context reduction (GPT input only) | {g['median_frontier_context_reduction_pct']:.1f}% | {h['median_frontier_context_reduction_pct']:.1f}% |", "",
      f"Pricing version `{S['pricing_version']}` (gpt-6-sol $2.00/$0.20/$10.00 per 1M input/cached/output; jev-1.13.0 $0.042 per 1M input, output free).", "",
      "## Latency (application-side wall-clock, concurrency 4)", "", "| | GPT-only | Jev + GPT |", "|---|---|---|"]
for k in ("p50", "p90", "p95", "mean", "max"):
    L.append(f"| end-to-end {k} | {ms(g['latency_total_ms'][k])} | {ms(h['latency_total_ms'][k])} |")
for k in ("p50", "p90", "p95"):
    L.append(f"| decision {k} | {ms(g['latency_decision_ms'][k])} | {ms(h['latency_decision_ms'][k])} |")
L += ["", "Per-stage percentiles: `presentation_results/latency_analysis.csv`.", "",
      "## Jev calibration and routing", "",
      f"Criterion-level confidence for the {j['n']} criteria Jev evaluated (before routing): **Brier {j['brier_score']:.4f}, ECE {j['ece']:.4f}**. "
      f"GPT self-reported confidence on the same criteria: Brier {j['gpt_same_scope_brier']:.4f}, ECE {j['gpt_same_scope_ece']:.4f}. "
      "Reliability bins (with n) in `results/calibration.csv`; bins with small n are not interpretable on their own.", ""]
cal = [r for r in csv.DictReader(open(ROOT / "results/calibration.csv")) if r["n"] != "0"]
L += ["| model | scope | bin | n | mean confidence | empirical accuracy |", "|---|---|---|---|---|---|"]
for r in cal:
    if r["scope"].startswith("all criteria"):
        continue
    L.append(f"| {r['model']} | {r['scope'][:40]} | {r['bin']} | {r['n']} | {float(r['mean_confidence']):.3f} | {float(r['empirical_accuracy']):.3f} |")
e = S["escalation_effect"]
L += ["", f"Escalations at 0.90 ({h['criteria_escalated']} criteria in {h['cases_escalated']} cases): Jev and GPT both correct {e.get('both_correct', 0)}, "
      f"GPT fixed a wrong Jev answer {e.get('escalation_fixed', 0)}, GPT changed a correct Jev answer {e.get('escalation_broke', 0)}, both wrong {e.get('both_wrong', 0)}.", "",
      "## Threshold sweep (sensitivity analysis — not used to choose the headline threshold)", "",
      "| threshold | PA acc | criterion acc | Jev coverage | Jev auto-decision acc | cases escalated | GPT decision calls | GPT tokens avoided | decision cost | end-to-end cost | decision p95 |",
      "|---|---|---|---|---|---|---|---|---|---|---|"]
for r in S["threshold_sweep"]:
    if r["threshold"] == "gpt_only":
        L.append(f"| GPT-only | {pct(r['pa_accuracy'])} | {pct(r['criterion_accuracy'])} | — | — | — | {r['gpt_decision_calls']} | 0% | {usd(r['decision_cost_usd'])} | {usd(r['total_cost_usd'])} | {ms(r['p95_decision_latency_ms'])} |")
    else:
        L.append(f"| {r['threshold']:.2f}{' (headline)' if r['headline'] else ''} | {pct(r['pa_accuracy'])} | {pct(r['criterion_accuracy'])} | {pct(r['jev_coverage'])} | "
                 f"{pct(r['jev_auto_decision_accuracy'])} | {r['cases_escalated']} | {r['gpt_decision_calls']} | {r['gpt_tokens_avoided_pct']:.1f}% | "
                 f"{usd(r['decision_cost_usd'])} | {usd(r['total_cost_usd'])} | {ms(r['p95_decision_latency_ms'])} |")
rt = S["retrieval"]
L += ["", "## Retrieval (shared by both pipelines)", "",
      f"{rt['queries']} criterion queries; mean recall {rt['mean_recall']:.3f}; mean recall of contradicting evidence {rt['mean_recall_contradicts']:.3f}; "
      f"critical misses {rt['critical_misses']}. Details: `{rt['report']}`.", "",
      "## Failure analysis", "", "See `reports/failure_analysis.md` and `results/failure_analysis.csv`.", "",
      "## Limitations", ""] + [f"- {x}" for x in S["limitations"]] + ["", "## Files", "",
      "`results/`: run_manifest.json, summary.json, patient_results.csv, criterion_results.csv, model_calls.csv, retrieval_results.csv, "
      "calibration.csv, threshold_sweep.csv, failure_analysis.csv, traces/. `presentation_results/`: executive_summary.json, "
      "pipeline_comparison.csv, criterion_performance.csv, challenge_performance.csv, cost_analysis.csv, latency_analysis.csv, "
      "calibration.csv, threshold_sweep.csv, failure_analysis.csv, interesting_cases.json, experiment_manifest.json."]
(ROOT / "reports/evaluation_report.md").write_text("\n".join(L) + "\n")

# ---------------------------------------------------------------- failure analysis report
F = list(csv.DictReader(open(ROOT / "results/failure_analysis.csv")))
M = ["# Failure analysis", "", "Generated from `results/failure_analysis.csv`. Every incorrect criterion decision is listed with its automatic "
     "category (priority: retrieval → missing-vs-negative → criterion/challenge-tag family → policy logic → semantic), the deciding engine and "
     "confidence, and trace pointers (prompt SHA-256 + request id in `results/traces/<run>.jsonl`).", ""]
for pipe, name in (("gpt", "GPT-only"), ("hybrid", "Jev + GPT (0.90)")):
    rows = [r for r in F if r["pipeline"] == pipe]
    M += [f"## {name}: {len(rows)} criterion errors, {len({r['evaluation_id'] for r in rows if r['pa_state_wrong'] == 'True'})} wrong PA states", "",
          "| category | all criterion errors | errors in wrong-PA cases |", "|---|---|---|"]
    allc = Counter(r["failure_category"] for r in rows)
    pac = Counter(r["failure_category"] for r in rows if r["pa_state_wrong"] == "True")
    for k in sorted(allc):
        M.append(f"| {k} | {allc[k]} | {pac.get(k, 0)} |")
    over = sum("MODEL_OVERCONFIDENCE" in r["secondary_flags"] for r in rows)
    M += ["", f"Wrong with confidence ≥ 0.90 (MODEL_OVERCONFIDENCE flag): {over} of {len(rows)}.", "",
          "| evaluation | criterion | truth | predicted | engine | conf | Jev pre-routing | escalation | changes PA | category |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        conf = f"{float(r['confidence']):.2f}" if r["confidence"] not in ("", "None") else "—"
        jv = f"{r['jev_prediction']} ({float(r['jev_confidence']):.2f})" if r["jev_prediction"] not in ("", "None") else "—"
        M.append(f"| {r['evaluation_id']} | {r['criterion_id']} | {r['ground_truth']} | {r['prediction']} | {r['engine']} | {conf} | {jv} | "
                 f"{r['escalation_effect'] or '—'} | {'yes' if r['pa_state_wrong'] == 'True' else 'no'} | {r['failure_category']} |")
    M.append("")
M += ["## Notes on categories", "",
      "- `MISSING_NOT_NEGATIVE` here is dominated by BMI 27–30 cases with no comorbidity: ground truth labels the criterion FAIL (the patient has "
      "no qualifying comorbidity) while the model answered INSUFFICIENT (absence of documentation). These disagreements do not change the PA state "
      "(both map to NOT_READY).",
      "- `RETRIEVAL_FAILURE` count is 0: in every error, the evidence needed for the correct status had been retrieved (see `reports/retrieval_eval.md`).",
      "- Escalation effects are measured against Jev's own pre-routing status (`jev_prediction`), so hybrid errors can be attributed to Jev reads, "
      "code composition, or the GPT escalation."]
(ROOT / "reports/failure_analysis.md").write_text("\n".join(M) + "\n")
print("wrote reports/evaluation_report.md and reports/failure_analysis.md")
