"""M1.1: validate the canonical cohort spec (data/cohort/patients.json)."""
import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.generation.scenarios import DOC_STATES, MED_SCENARIOS  # noqa: E402

EXPECTED_CLASSES = {"easy_positive": 10, "easy_negative": 5, "missing_evidence": 10, "ambiguous": 10, "hard": 15}
BMI_TOL = 0.15
BMI_BOUNDARY = (29.5, 30.5)


def main() -> int:
    spec = json.loads((ROOT / "data/cohort/patients.json").read_text())
    schema = json.loads((ROOT / "schemas/patient.schema.json").read_text())
    patients = spec["patients"]
    errors, warnings = [], []

    if spec.get("n_patients") != len(patients):
        errors.append(f"n_patients={spec.get('n_patients')} but {len(patients)} records")
    ids = [p["patient_id"] for p in patients]
    if len(set(ids)) != len(ids):
        errors.append(f"duplicate ids: {[i for i, c in Counter(ids).items() if c > 1]}")

    for p in patients:
        pid = p["patient_id"]
        try:
            jsonschema.validate(p, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"{pid}: schema: {e.message}")
        a = p["anthropometrics"]
        calc = a["current_weight_kg"] / (a["height_cm"] / 100) ** 2
        if abs(calc - a["current_bmi"]) > BMI_TOL:
            errors.append(f"{pid}: BMI {a['current_bmi']} != computed {calc:.2f}")
        if p["demographics"]["age"] < 18:
            errors.append(f"{pid}: age {p['demographics']['age']} < 18")
        ct = p["clinical_truth"]
        if ct["weight_management"]["documentation_state"] not in DOC_STATES:
            errors.append(f"{pid}: unmapped documentation_state {ct['weight_management']['documentation_state']}")
        if ct["medication_scenario"] not in MED_SCENARIOS:
            errors.append(f"{pid}: unmapped medication_scenario {ct['medication_scenario']}")
        for k, v in ct["conditions"].items():
            if v is None:
                warnings.append(f"{pid}: condition '{k}' is null (intentionally ambiguous)")

    classes = Counter(p["benchmark_design"]["class"] for p in patients)
    if dict(classes) != EXPECTED_CLASSES:
        errors.append(f"class counts {dict(classes)} != {EXPECTED_CLASSES}")

    print(f"Cohort {spec['cohort_id']}: {len(patients)} patients")
    print("Classes:", dict(classes))
    print(f"Mapped documentation_states: {len({p['clinical_truth']['weight_management']['documentation_state'] for p in patients})}/{len(DOC_STATES)} used")
    print(f"Mapped medication_scenarios: {len({p['clinical_truth']['medication_scenario'] for p in patients})}/{len(MED_SCENARIOS)} used")
    print("\nBMI boundary cases (29.5–30.5):")
    for p in patients:
        a = p["anthropometrics"]
        if BMI_BOUNDARY[0] <= a["current_bmi"] <= BMI_BOUNDARY[1]:
            calc = a["current_weight_kg"] / (a["height_cm"] / 100) ** 2
            print(f"  {p['patient_id']}: spec {a['current_bmi']}, computed {calc:.3f}  [{p['benchmark_design']['class']}]")
    for w in warnings:
        print("WARN", w)
    for e in errors:
        print("ERROR", e)
    print("\nRESULT:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
