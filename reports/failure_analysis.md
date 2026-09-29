# Failure analysis

Generated from `results/failure_analysis.csv`. Every incorrect criterion decision is listed with its automatic category (priority: retrieval → missing-vs-negative → criterion/challenge-tag family → policy logic → semantic), the deciding engine and confidence, and trace pointers (prompt SHA-256 + request id in `results/traces/<run>.jsonl`).

## GPT-only: 21 criterion errors, 8 wrong PA states

| category | all criterion errors | errors in wrong-PA cases |
|---|---|---|
| CONTRADICTION | 3 | 3 |
| MISSING_NOT_NEGATIVE | 10 | 0 |
| SEMANTIC_INTERPRETATION | 1 | 1 |
| TEMPORAL_REASONING | 7 | 4 |

Wrong with confidence ≥ 0.90 (MODEL_OVERCONFIDENCE flag): 14 of 21.

| evaluation | criterion | truth | predicted | engine | conf | Jev pre-routing | escalation | changes PA | category |
|---|---|---|---|---|---|---|---|---|---|
| GLP1-013__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.88 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-013__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.88 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-014__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.96 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-020__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | PASS | INSUFFICIENT | gpt | 0.84 | — | — | no | TEMPORAL_REASONING |
| GLP1-021__BCBS_FEP_WEGOVY_2026_07_01 | weight_management_program | PASS | INSUFFICIENT | gpt | 0.85 | — | — | yes | TEMPORAL_REASONING |
| GLP1-027__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | PASS | INSUFFICIENT | gpt | 0.96 | — | — | no | TEMPORAL_REASONING |
| GLP1-030__AETNA_WEGOVY_4774C_2026_08_20 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.96 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-030__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.98 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-030__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.91 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-032__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | PASS | INSUFFICIENT | gpt | 0.98 | — | — | yes | TEMPORAL_REASONING |
| GLP1-033__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | CONFLICT | FAIL | gpt | 0.98 | — | — | yes | TEMPORAL_REASONING |
| GLP1-039__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | PASS | CONFLICT | gpt | 0.94 | — | — | yes | SEMANTIC_INTERPRETATION |
| GLP1-040__AETNA_WEGOVY_4774C_2026_08_20 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.96 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-040__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.93 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-040__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.89 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-041__AETNA_WEGOVY_4774C_2026_08_20 | bmi_threshold | FAIL | INSUFFICIENT | gpt | 0.96 | — | — | no | MISSING_NOT_NEGATIVE |
| GLP1-041__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | PASS | gpt | 0.86 | — | — | yes | CONTRADICTION |
| GLP1-041__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | CONFLICT | gpt | 0.78 | — | — | yes | CONTRADICTION |
| GLP1-042__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | CONFLICT | FAIL | gpt | 0.96 | — | — | yes | CONTRADICTION |
| GLP1-050__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | CONFLICT | INSUFFICIENT | gpt | 0.95 | — | — | no | TEMPORAL_REASONING |
| GLP1-050__UHC_WEGOVY_P1114_22_2026_09_01 | lifestyle_adjunct | CONFLICT | PASS | gpt | 0.94 | — | — | yes | TEMPORAL_REASONING |

## Jev + GPT (0.90): 12 criterion errors, 5 wrong PA states

| category | all criterion errors | errors in wrong-PA cases |
|---|---|---|
| CONTRADICTION | 3 | 3 |
| MISSING_NOT_NEGATIVE | 4 | 0 |
| TEMPORAL_REASONING | 5 | 2 |

Wrong with confidence ≥ 0.90 (MODEL_OVERCONFIDENCE flag): 10 of 12.

| evaluation | criterion | truth | predicted | engine | conf | Jev pre-routing | escalation | changes PA | category |
|---|---|---|---|---|---|---|---|---|---|
| GLP1-026__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | PASS | INSUFFICIENT | gpt_escalation | 0.82 | PASS (0.32) | escalation_broke | no | TEMPORAL_REASONING |
| GLP1-027__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | PASS | INSUFFICIENT | jev | 0.92 | INSUFFICIENT (0.92) | — | no | TEMPORAL_REASONING |
| GLP1-030__AETNA_WEGOVY_4774C_2026_08_20 | bmi_threshold | FAIL | INSUFFICIENT | gpt_escalation | 0.96 | FAIL (0.61) | escalation_broke | no | MISSING_NOT_NEGATIVE |
| GLP1-030__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt_escalation | 0.97 | FAIL (0.69) | escalation_broke | no | MISSING_NOT_NEGATIVE |
| GLP1-030__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | INSUFFICIENT | gpt_escalation | 0.96 | FAIL (0.63) | escalation_broke | no | MISSING_NOT_NEGATIVE |
| GLP1-032__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | PASS | INSUFFICIENT | gpt_escalation | 0.91 | PASS (0.70) | escalation_broke | yes | TEMPORAL_REASONING |
| GLP1-040__AETNA_WEGOVY_4774C_2026_08_20 | bmi_threshold | FAIL | INSUFFICIENT | gpt_escalation | 0.97 | FAIL (0.89) | escalation_broke | no | MISSING_NOT_NEGATIVE |
| GLP1-041__BCBS_FEP_WEGOVY_2026_07_01 | bmi_threshold | FAIL | PASS | gpt_escalation | 0.90 | FAIL (0.89) | escalation_broke | yes | CONTRADICTION |
| GLP1-041__UHC_WEGOVY_P1114_22_2026_09_01 | bmi_threshold | FAIL | CONFLICT | gpt_escalation | 0.82 | FAIL (0.88) | escalation_broke | yes | CONTRADICTION |
| GLP1-042__AETNA_WEGOVY_4774C_2026_08_20 | program_6_months | CONFLICT | FAIL | gpt_escalation | 0.95 | CONFLICT (0.84) | escalation_broke | yes | CONTRADICTION |
| GLP1-050__AETNA_WEGOVY_4774C_2026_08_20 | adjunct_diet_and_activity | CONFLICT | INSUFFICIENT | gpt_escalation | 0.96 | INSUFFICIENT (0.88) | both_wrong | no | TEMPORAL_REASONING |
| GLP1-050__UHC_WEGOVY_P1114_22_2026_09_01 | lifestyle_adjunct | CONFLICT | PASS | gpt_escalation | 0.97 | INSUFFICIENT (0.70) | both_wrong | yes | TEMPORAL_REASONING |

## Notes on categories

- `MISSING_NOT_NEGATIVE` here is dominated by BMI 27–30 cases with no comorbidity: ground truth labels the criterion FAIL (the patient has no qualifying comorbidity) while the model answered INSUFFICIENT (absence of documentation). These disagreements do not change the PA state (both map to NOT_READY).
- `RETRIEVAL_FAILURE` count is 0: in every error, the evidence needed for the correct status had been retrieved (see `reports/retrieval_eval.md`).
- Escalation effects are measured against Jev's own pre-routing status (`jev_prediction`), so hybrid errors can be attributed to Jev reads, code composition, or the GPT escalation.
