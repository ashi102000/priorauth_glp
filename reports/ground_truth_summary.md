# Ground truth summary (hidden)

150 evaluations (50 patients × 3 policies); 750 criterion labels. Request date 2026-09-01.

## PA state by policy

| Policy | READY | NOT_READY | REVIEW_REQUIRED |
|---|---|---|---|
| AETNA_WEGOVY_4774C_2026_08_20 | 24 | 22 | 4 |
| BCBS_FEP_WEGOVY_2026_07_01 | 29 | 19 | 2 |
| UHC_WEGOVY_P1114_22_2026_09_01 | 33 | 15 | 2 |
| **All** | 86 | 56 | 8 |

## PA state by difficulty class (all policies)

| Class | READY | NOT_READY | REVIEW_REQUIRED |
|---|---|---|---|
| easy_positive | 30 | 0 | 0 |
| easy_negative | 0 | 15 | 0 |
| missing_evidence | 15 | 15 | 0 |
| ambiguous | 19 | 7 | 4 |
| hard | 22 | 19 | 4 |

## Criterion status counts

| Policy | Criterion | PASS | FAIL | INSUFFICIENT | CONFLICT |
|---|---|---|---|---|---|
| AETNA | age | 50 | 0 | 0 | 0 |
| AETNA | indication | 50 | 0 | 0 | 0 |
| AETNA | adjunct_diet_and_activity | 41 | 2 | 6 | 1 |
| AETNA | program_6_months | 34 | 4 | 9 | 3 |
| AETNA | bmi_threshold | 40 | 9 | 0 | 1 |
| BCBS | age | 50 | 0 | 0 | 0 |
| BCBS | indication | 50 | 0 | 0 | 0 |
| BCBS | bmi_threshold | 40 | 9 | 0 | 1 |
| BCBS | weight_management_program | 42 | 1 | 7 | 0 |
| BCBS | no_concurrent_glp1 | 46 | 0 | 3 | 1 |
| BCBS | no_concurrent_pa_weight_loss_med | 46 | 0 | 3 | 1 |
| UHC | age | 50 | 0 | 0 | 0 |
| UHC | indication | 50 | 0 | 0 | 0 |
| UHC | lifestyle_adjunct | 43 | 2 | 4 | 1 |
| UHC | bmi_threshold | 40 | 9 | 0 | 1 |

## Per-patient labels

`R`=READY, `N`=NOT_READY (failing/insufficient criteria), `V`=REVIEW_REQUIRED (conflicts)

| Patient | Class | AETNA | BCBS | UHC |
|---|---|---|---|---|
| GLP1-001 | easy_positive | R | R | R |
| GLP1-002 | easy_positive | R | R | R |
| GLP1-003 | easy_positive | R | R | R |
| GLP1-004 | easy_positive | R | R | R |
| GLP1-005 | easy_positive | R | R | R |
| GLP1-006 | easy_positive | R | R | R |
| GLP1-007 | easy_positive | R | R | R |
| GLP1-008 | easy_positive | R | R | R |
| GLP1-009 | easy_positive | R | R | R |
| GLP1-010 | easy_positive | R | R | R |
| GLP1-011 | easy_negative | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-012 | easy_negative | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-013 | easy_negative | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-014 | easy_negative | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-015 | easy_negative | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-016 | missing_evidence | N (adjunct_diet_and_activity, program_6_months) | N (weight_management_program) | N (lifestyle_adjunct) |
| GLP1-017 | missing_evidence | N (adjunct_diet_and_activity, program_6_months) | N (weight_management_program) | N (lifestyle_adjunct) |
| GLP1-018 | missing_evidence | N (adjunct_diet_and_activity, program_6_months) | N (weight_management_program) | R |
| GLP1-019 | missing_evidence | N (adjunct_diet_and_activity, program_6_months) | N (weight_management_program) | R |
| GLP1-020 | missing_evidence | N (program_6_months) | R | R |
| GLP1-021 | missing_evidence | N (adjunct_diet_and_activity, program_6_months) | R | N (lifestyle_adjunct) |
| GLP1-022 | missing_evidence | R | R | R |
| GLP1-023 | missing_evidence | R | N (no_concurrent_glp1, no_concurrent_pa_weight_loss_med) | R |
| GLP1-024 | missing_evidence | R | N (no_concurrent_glp1, no_concurrent_pa_weight_loss_med) | R |
| GLP1-025 | missing_evidence | R | R | R |
| GLP1-026 | ambiguous | N (program_6_months) | N (weight_management_program) | R |
| GLP1-027 | ambiguous | N (program_6_months) | N (weight_management_program) | R |
| GLP1-028 | ambiguous | V (⚠bmi_threshold) | V (⚠bmi_threshold) | V (⚠bmi_threshold) |
| GLP1-029 | ambiguous | R | R | R |
| GLP1-030 | ambiguous | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-031 | ambiguous | R | R | R |
| GLP1-032 | ambiguous | R | R | R |
| GLP1-033 | ambiguous | V (⚠program_6_months) | R | R |
| GLP1-034 | ambiguous | R | R | R |
| GLP1-035 | ambiguous | R | R | R |
| GLP1-036 | hard | N (adjunct_diet_and_activity, program_6_months) | R | N (lifestyle_adjunct) |
| GLP1-037 | hard | N (program_6_months) | R | R |
| GLP1-038 | hard | R | R | R |
| GLP1-039 | hard | R | R | R |
| GLP1-040 | hard | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-041 | hard | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-042 | hard | V (⚠program_6_months) | R | R |
| GLP1-043 | hard | N (adjunct_diet_and_activity, program_6_months) | N (weight_management_program) | N (lifestyle_adjunct) |
| GLP1-044 | hard | N (adjunct_diet_and_activity, program_6_months) | R | N (lifestyle_adjunct) |
| GLP1-045 | hard | R | V (⚠no_concurrent_glp1, ⚠no_concurrent_pa_weight_loss_med) | R |
| GLP1-046 | hard | N (bmi_threshold) | N (bmi_threshold) | N (bmi_threshold) |
| GLP1-047 | hard | R | R | R |
| GLP1-048 | hard | R | R | R |
| GLP1-049 | hard | V (⚠program_6_months) | R | R |
| GLP1-050 | hard | N (program_6_months, ⚠adjunct_diet_and_activity) | N (no_concurrent_glp1, no_concurrent_pa_weight_loss_med, weight_management_program) | V (⚠lifestyle_adjunct) |
