# Evaluation report — GLP-1 PA benchmark (GPT-only vs Jev + GPT)

Generated from `results/summary.json` (2026-09-29T09:12:43+00:00). 50 synthetic patients × 3 verified payer policies = 150 PA evaluations per pipeline. Request date 2026-09-01. Hybrid headline threshold **0.90** (fixed before the runs). Measurements only; interpretation is left to the reader.

## Quality

| Metric | GPT-only | Jev + GPT |
|---|---|---|
| PA-state accuracy (95% CI, patient-cluster bootstrap) | 94.7% [90.7, 98.0] | 96.7% [92.7, 99.3] |
| PA-state macro-F1 | 0.862 | 0.916 |
| READY accuracy (recall, n=86) | 96.5% | 98.8% |
| NOT_READY accuracy (recall, n=56) | 96.4% | 96.4% |
| REVIEW_REQUIRED accuracy (recall, n=8) | 62.5% | 75.0% |
| Binary auto-ready F1 | 0.971 | 0.983 |
| False auto-submissions (pred READY, truth not) | 2 | 2 |
| Criterion accuracy (750 labels) | 97.2% | 98.4% |
| Criterion macro-F1 | 0.811 | 0.890 |
| Semantic-criterion accuracy | 97.0% | 98.0% |

Paired comparison (same 150 cases): GPT-only correct & hybrid wrong = 0; hybrid correct & GPT-only wrong = 3; exact McNemar p = 0.250; accuracy difference (hybrid − GPT) = 2.0 pts, 95% CI [0.0, 4.7]. Criterion level: 1 vs 10, p = 0.0117 (criteria within a case are correlated; treat the criterion-level p-value as descriptive).

PA confusion matrices (rows = truth, cols = predicted):

**GPT-only**

| truth \ pred | READY | NOT_READY | REVIEW_REQUIRED |
|---|---|---|---|
| READY | 83 | 2 | 1 |
| NOT_READY | 1 | 54 | 1 |
| REVIEW_REQUIRED | 1 | 2 | 5 |

**Jev + GPT**

| truth \ pred | READY | NOT_READY | REVIEW_REQUIRED |
|---|---|---|---|
| READY | 85 | 1 | 0 |
| NOT_READY | 1 | 54 | 1 |
| REVIEW_REQUIRED | 1 | 1 | 6 |

## Cost, frontier usage and context

| Metric | GPT-only | Jev + GPT |
|---|---|---|
| Total cost, 150 PAs (end-to-end) | $2.333 | $0.866 |
| Cost per PA (end-to-end) | $0.0156 | $0.0058 |
| Decision cost per PA (excl. hybrid READY narratives) | $0.0156 | $0.0025 |
| GPT calls (decision + narrative) | 150 | 114 (27 + 87) |
| Jev calls | 0 | 150 |
| GPT input / output tokens | 633,572 / 106,584 | 229,398 / 39,680 |
| GPT decision input / output tokens | 633,572 / 106,584 | 110,363 / 11,674 |
| Jev input tokens | 0 | 909,004 |
| GPT calls avoided (all / decision-only) | — | 24.0% / 82.0% |
| GPT tokens avoided (all / decision-only) | — | 63.6% / 83.5% |
| Cost reduction (end-to-end / decision-only) | — | 62.9% / 84.2% |
| Median context reduction vs raw chart (all model input) | 53.0% | 30.7% |
| Median frontier-context reduction (GPT input only) | 53.0% | 100.0% |

Pricing version `PRICING_2026_09_29` (gpt-6-sol $2.00/$0.20/$10.00 per 1M input/cached/output; jev-1.13.0 $0.042 per 1M input, output free).

## Latency (application-side wall-clock, concurrency 4)

| | GPT-only | Jev + GPT |
|---|---|---|
| end-to-end p50 | 10.6 s | 5.6 s |
| end-to-end p90 | 15.1 s | 8.1 s |
| end-to-end p95 | 16.3 s | 10.3 s |
| end-to-end mean | 10.7 s | 5.0 s |
| end-to-end max | 26.9 s | 23.9 s |
| decision p50 | 10.6 s | 198 ms |
| decision p90 | 15.1 s | 6.9 s |
| decision p95 | 16.3 s | 8.7 s |

Per-stage percentiles: `presentation_results/latency_analysis.csv`.

## Jev calibration and routing

Criterion-level confidence for the 327 criteria Jev evaluated (before routing): **Brier 0.0208, ECE 0.0381**. GPT self-reported confidence on the same criteria: Brier 0.0558, ECE 0.0353. Reliability bins (with n) in `results/calibration.csv`; bins with small n are not interpretable on their own.

| model | scope | bin | n | mean confidence | empirical accuracy |
|---|---|---|---|---|---|
| jev | criteria evaluated by Jev (pre-routing c | 0.0-0.1 | 1 | 0.100 | 0.000 |
| jev | criteria evaluated by Jev (pre-routing c | 0.2-0.3 | 1 | 0.240 | 1.000 |
| jev | criteria evaluated by Jev (pre-routing c | 0.3-0.4 | 1 | 0.320 | 1.000 |
| jev | criteria evaluated by Jev (pre-routing c | 0.4-0.5 | 1 | 0.440 | 0.000 |
| jev | criteria evaluated by Jev (pre-routing c | 0.6-0.7 | 3 | 0.643 | 1.000 |
| jev | criteria evaluated by Jev (pre-routing c | 0.7-0.8 | 8 | 0.751 | 0.625 |
| jev | criteria evaluated by Jev (pre-routing c | 0.8-0.9 | 17 | 0.868 | 0.882 |
| jev | criteria evaluated by Jev (pre-routing c | 0.9-1.0 | 295 | 0.969 | 0.997 |
| gpt | same criterion set, GPT self-reported co | 0.7-0.8 | 1 | 0.780 | 0.000 |
| gpt | same criterion set, GPT self-reported co | 0.8-0.9 | 10 | 0.856 | 0.400 |
| gpt | same criterion set, GPT self-reported co | 0.9-1.0 | 316 | 0.975 | 0.956 |

Escalations at 0.90 (32 criteria in 27 cases): Jev and GPT both correct 16, GPT fixed a wrong Jev answer 5, GPT changed a correct Jev answer 9, both wrong 2.

## Threshold sweep (sensitivity analysis — not used to choose the headline threshold)

| threshold | PA acc | criterion acc | Jev coverage | Jev auto-decision acc | cases escalated | GPT decision calls | GPT tokens avoided | decision cost | end-to-end cost | decision p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.60 | 97.3% | 99.2% | 98.8% | 98.1% | 4 | 4 | 78.4% | $0.085 | $0.564 | 426 ms |
| 0.70 | 97.3% | 98.8% | 97.9% | 98.1% | 7 | 7 | 76.7% | $0.122 | $0.601 | 461 ms |
| 0.80 | 98.0% | 98.9% | 95.4% | 99.0% | 13 | 13 | 72.4% | $0.199 | $0.689 | 6.8 s |
| 0.90 (headline) | 96.7% | 98.4% | 90.2% | 99.7% | 27 | 27 | 63.6% | $0.369 | $0.866 | 8.7 s |
| 0.95 | 97.3% | 97.9% | 66.4% | 100.0% | 88 | 88 | 26.2% | $1.098 | $1.593 | 14.3 s |
| GPT-only | 94.7% | 97.2% | — | — | — | 150 | 0% | $2.333 | $2.333 | 16.3 s |

## Retrieval (shared by both pipelines)

450 criterion queries; mean recall 0.917; mean recall of contradicting evidence 1.000; critical misses 0. Details: `reports/retrieval_eval.md`.

## Failure analysis

See `reports/failure_analysis.md` and `results/failure_analysis.csv`.

## Limitations

- n = 150 evaluations (50 synthetic patients x 3 policies); cases are challenge-stratified, not epidemiologically representative.
- Evaluations of the same patient are correlated; CIs use a patient-cluster bootstrap.
- Hybrid questions/rules were revised once after a 5-patient smoke test on this cohort (no separate dev set); GPT baseline received one provenance formatting fix.
- Ground truth derives from user-approved policy interpretations; some labels (REVIEW_REQUIRED cases) encode judgment calls.
- Headline threshold 0.90 was fixed before the runs; the sweep is sensitivity analysis, not selection.
- Latency measured application-side with concurrency 4; GPT latency depends on provider load at run time.
- Clinical notes were authored by an LLM (Claude) from structured plans; distribution differs from real EHR text.

## Files

`results/`: run_manifest.json, summary.json, patient_results.csv, criterion_results.csv, model_calls.csv, retrieval_results.csv, calibration.csv, threshold_sweep.csv, failure_analysis.csv, traces/. `presentation_results/`: executive_summary.json, pipeline_comparison.csv, criterion_performance.csv, challenge_performance.csv, cost_analysis.csv, latency_analysis.csv, calibration.csv, threshold_sweep.csv, failure_analysis.csv, interesting_cases.json, experiment_manifest.json.
