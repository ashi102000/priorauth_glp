# GLP-1 Prior Authorization Synthetic Benchmark

## Separation rule
- `cohort/patients.json`: canonical synthetic truth used by the generator; never model input.
- `fhir/`: model-visible generated FHIR R4 bundles; upload these to HAPI.
- `policies/`: exact versioned human-verified normalized payer policies.
- `ground_truth/`: hidden criterion/evidence/final labels; never send to models.
- `schemas/`: JSON schemas.
- `scripts/`: generator, HAPI seeder, policy evaluator, benchmark runner.

## Cohort
50 adult initial Wegovy requests: 10 easy positive, 5 easy negative, 10 missing-evidence, 10 ambiguous, 15 hard/contradictory. Challenge-balanced, not epidemiologically representative.

## Final states
READY, NOT_READY, REVIEW_REQUIRED. For binary auto-readiness, only READY maps to true.

## Next
Generate longitudinal FHIR resources + synthetic notes while simultaneously producing hidden evidence annotations.
