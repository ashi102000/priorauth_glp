"""Phase-1 validation scripts must pass (cohort spec, note lint, local FHIR source)."""
import validate_cohort
import lint_notes
import verify_local_fhir


def test_cohort_spec_valid():
    assert validate_cohort.main() == 0


def test_notes_lint_strict():
    assert lint_notes.main(["--strict"]) == 0


def test_local_fhir_matches_plans():
    assert verify_local_fhir.main() == 0
