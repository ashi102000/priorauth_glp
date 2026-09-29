# Retrieval evaluation (Phase 3)

Config `RETRIEVAL_V1` (hash `bb02d66cc68d`): top_k=5, min_relative_score=0.2, temporal extras=True, chunk ≤120 words, BM25 k1=1.5 b=0.75. Defaults fixed a priori; not tuned on these annotations.

Profiles: 150 (50 patients × 3 policies); criterion queries evaluated: 450.

Document-level metrics vs. hidden evidence annotations. Structured resources are always supplied in full and not scored.

### By criterion

| group | n | recall | precision | recall SUPPORTS | recall CONTRADICTS | recall AMBIGUOUS | hard-neg / query | critical hits |
|---|---|---|---|---|---|---|---|---|
| adjunct_diet_and_activity | 50 | 0.955 | 0.831 | 0.953 | 1.0 | 1.0 | 0.48 | 3/3 |
| comorbidity | 150 | 0.827 | 0.412 | 0.812 | 1.0 | 1.0 | 0 | — |
| lifestyle_adjunct | 50 | 0.946 | 0.825 | 0.943 | 1.0 | 1.0 | 0.46 | 3/3 |
| no_concurrent_glp1 | 50 | 1.0 | 0.045 | 1.0 | — | 1.0 | 0 | — |
| no_concurrent_pa_weight_loss_med | 50 | 1.0 | 0.045 | 1.0 | — | 1.0 | 0 | — |
| program_6_months | 50 | 0.946 | 0.832 | 0.943 | 1.0 | 1.0 | 0.48 | 7/7 |
| weight_management_program | 50 | 0.934 | 0.879 | 0.929 | 1.0 | 1.0 | 0.38 | 1/1 |

### By difficulty class

| group | n | recall | precision | recall SUPPORTS | recall CONTRADICTS | recall AMBIGUOUS | hard-neg / query | critical hits |
|---|---|---|---|---|---|---|---|---|
| ambiguous | 90 | 0.943 | 0.463 | 0.94 | 1.0 | 1.0 | 0.24 | 1/1 |
| easy_negative | 45 | 0.872 | 0.537 | 0.872 | — | — | 0.09 | — |
| easy_positive | 90 | 0.861 | 0.652 | 0.861 | — | — | 0.07 | — |
| hard | 135 | 0.933 | 0.515 | 0.921 | 1.0 | 1.0 | 0.3 | 13/13 |
| missing_evidence | 90 | 0.954 | 0.451 | 0.95 | — | 1.0 | 0.19 | — |

### By policy

| group | n | recall | precision | recall SUPPORTS | recall CONTRADICTS | recall AMBIGUOUS | hard-neg / query | critical hits |
|---|---|---|---|---|---|---|---|---|
| AETNA_WEGOVY_4774C_2026_08_20 | 150 | 0.925 | 0.692 | 0.921 | 1.0 | 1.0 | 0.32 | 10/10 |
| BCBS_FEP_WEGOVY_2026_07_01 | 200 | 0.916 | 0.345 | 0.904 | 1.0 | 1.0 | 0.1 | 1/1 |
| UHC_WEGOVY_P1114_22_2026_09_01 | 100 | 0.905 | 0.619 | 0.9 | 1.0 | 1.0 | 0.23 | 3/3 |

### Context size (tiktoken cl100k_base, per patient × policy profile)

| measure | min | median | max |
|---|---|---|---|
| raw candidate chart (structured JSON + decoded notes) | 7005 | 9038.5 | 12715 |
| retrieved note evidence (unique chunks) | 418 | 722.0 | 1705 |
| structured features | 1131 | 1680.5 | 2051 |
| full evidence profile | 2186 | 4345.5 | 6788 |
| context reduction (1 − profile / raw chart) | 32.5% | 50.7% | 69.4% |

### Critical misses (truth FAIL/CONFLICT but no contradicting/ambiguous evidence retrieved)

- none

### Low-recall queries (recall < 0.5): 0


### Sensitivity to top_k (reported only — the benchmark uses the fixed default)

| top_k | recall | precision | recall CONTRADICTS | critical hits | median profile tokens |
|---|---|---|---|---|---|
| 3 | 0.741 | 0.537 | 0.65 | 14/14 | 3583.0 |
| 5 | 0.917 | 0.521 | 1.0 | 14/14 | 4345.5 |
| 8 | 0.962 | 0.493 | 1.0 | 14/14 | 4795.0 |
| 12 | 0.962 | 0.489 | 1.0 | 14/14 | 4814.0 |
