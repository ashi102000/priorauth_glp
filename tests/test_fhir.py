import json
from datetime import date

from pa_bench.fhir.parser import (blood_pressure, condition_status, document_date, document_text, observation_code,
                                  observation_value)


def test_client_serves_cohort(client):
    assert len(client.patient_ids()) == 50
    ev = client.everything("GLP1-017")
    assert len(ev["Patient"]) == 1 and ev["Patient"][0]["id"] == "GLP1-017"
    assert 10 <= len(ev["DocumentReference"]) <= 20


def test_read_and_search(client):
    p = client.read("Patient", "GLP1-001")
    assert p["gender"] == "female"
    obs = client.search("Observation", patient="GLP1-001")
    assert all(o["subject"]["reference"] == "Patient/GLP1-001" for o in obs)


def test_document_text_matches_frozen_notes(client, root):
    notes = json.loads((root / "data/notes/GLP1-043.json").read_text())["notes"]
    for d in client.search("DocumentReference", patient="GLP1-043"):
        assert document_text(d) == notes[d["id"]]


def test_latest_bmi_designed_values(client):
    def latest_bmi(pid):
        bmis = [o for o in client.search("Observation", patient=pid) if observation_code(o) == "39156-5"]
        return observation_value(max(bmis, key=lambda o: o["effectiveDateTime"]))
    assert latest_bmi("GLP1-029") == 30.0     # recorded value (computed 29.997)
    assert latest_bmi("GLP1-030") == 29.95
    assert latest_bmi("GLP1-040") == 29.7
    assert latest_bmi("GLP1-041") == 29.8     # prior reading 30.3


def test_bp_components_and_condition_status(client):
    bps = [o for o in client.search("Observation", patient="GLP1-001") if observation_code(o) == "85354-9"]
    assert bps and all(blood_pressure(o) for o in bps)
    htn = client.read("Condition", "GLP1-046-HTN")
    assert condition_status(htn) == "resolved"


def test_designed_structured_omissions(client):
    conds = lambda pid: {c["code"]["coding"][0]["code"] for c in client.search("Condition", patient=pid)}
    assert "38341003" not in conds("GLP1-022")        # hypertension narrative-only
    assert "370992007" not in conds("GLP1-034")       # dyslipidemia narrative-only
    meds = [m for t in ("MedicationRequest", "MedicationStatement") for m in client.search(t, patient="GLP1-023")]
    assert [m["id"] for m in meds] == ["GLP1-023-WEGOVY-REQ"]


def test_document_dates_within_window(client):
    for pid in client.patient_ids():
        for d in client.search("DocumentReference", patient=pid):
            assert date(2024, 9, 1) <= document_date(d) < date(2026, 9, 1)
