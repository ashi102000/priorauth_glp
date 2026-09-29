"""M1.5: build one FHIR R4 transaction bundle per patient from the chart plan + frozen note text.

Output: data/fhir/bundles/GLP1-xxx.json  (model-visible data only)

Only model-visible content is copied from the plan. Hidden plan fields (note role, trap flag,
facts_to_express, generator notes) never enter a bundle; tests/test_isolation.py enforces this.
"""
import base64
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pa_bench.generation import catalog as C  # noqa: E402

COHORT_TAG = {"system": "urn:jev-pa-benchmark", "code": "GLP1_PA_COHORT_V1", "display": "GLP-1 PA benchmark cohort v1"}
UUID_NS = uuid.UUID("6f1c2d3e-0000-4000-8000-6a65762d7061")   # fixed namespace -> deterministic fullUrls
UCUM = "http://unitsofmeasure.org"
UNITS = {"kg": "kg", "kg/m2": "kg/m2", "cm": "cm", "%": "%", "mg/dL": "mg/dL", "ng/mL": "ng/mL", "m[IU]/L": "m[IU]/L"}
CAT_SYS = "http://terminology.hl7.org/CodeSystem/observation-category"
VITALS = {"WT", "BMI", "HT", "BP"}


def meta() -> dict:
    return {"tag": [dict(COHORT_TAG)]}


def ref(rtype: str, rid: str) -> dict:
    return {"reference": f"{rtype}/{rid}"}


def note_time(doc_id: str, day: str) -> str:
    """Deterministic clinic-hours timestamp for DocumentReference.date (FHIR instant requires a time)."""
    h = int(hashlib.sha256(doc_id.encode()).hexdigest(), 16)
    return f"{day}T{8 + h % 9:02d}:{(h // 9) % 4 * 15:02d}:00-05:00"


def patient(plan: dict) -> dict:
    pt = plan["patient"]
    return {"resourceType": "Patient", "id": pt["id"], "meta": meta(),
            "identifier": [{"system": "urn:jev-pa-benchmark:mrn", "value": pt["id"]}],
            "name": [{"use": "official", "family": pt["family"], "given": [pt["given"]]}],
            "gender": pt["gender"], "birthDate": pt["birthDate"]}


def encounter(pid: str, e: dict) -> dict:
    return {"resourceType": "Encounter", "id": e["id"], "meta": meta(), "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
            "type": [{"text": e["type"]}], "subject": ref("Patient", pid),
            "period": {"start": e["date"], "end": e["date"]}}


def condition(pid: str, c: dict) -> dict:
    r = {"resourceType": "Condition", "id": c["id"], "meta": meta(),
         "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                        "code": c["clinical_status"]}]},
         "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                            "code": "confirmed"}]},
         "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                   "code": "problem-list-item", "display": "Problem List Item"}]}],
         "code": {"coding": [{"system": C.SNOMED, "code": c["code"], "display": c["display"]}], "text": c["display"]},
         "subject": ref("Patient", pid), "onsetDateTime": c["onset"], "recordedDate": c["onset"]}
    if c.get("abatement"):
        r["abatementDateTime"] = c["abatement"]
    return r


def observation(pid: str, o: dict) -> dict:
    code, display, unit = C.OBS_CODES[o["key"]]
    cat = "vital-signs" if o["key"] in VITALS else "laboratory"
    r = {"resourceType": "Observation", "id": o["id"], "meta": meta(), "status": "final",
         "category": [{"coding": [{"system": CAT_SYS, "code": cat}]}],
         "code": {"coding": [{"system": C.LOINC, "code": code, "display": display}], "text": display},
         "subject": ref("Patient", pid), "effectiveDateTime": o["date"]}
    if o.get("encounter_id"):
        r["encounter"] = ref("Encounter", o["encounter_id"])
    if o["key"] == "BP":
        r["component"] = [
            {"code": {"coding": [{"system": C.LOINC, "code": "8480-6", "display": "Systolic blood pressure"}]},
             "valueQuantity": {"value": o["systolic"], "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}},
            {"code": {"coding": [{"system": C.LOINC, "code": "8462-4", "display": "Diastolic blood pressure"}]},
             "valueQuantity": {"value": o["diastolic"], "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}},
        ]
    else:
        r["valueQuantity"] = {"value": o["value"], "unit": unit, "system": UCUM, "code": UNITS[unit]}
    return r


def medication(pid: str, m: dict) -> dict:
    med = {"text": m["text"]}
    base = {"id": m["id"], "meta": meta(), "status": m["status"], "medicationCodeableConcept": med, "subject": ref("Patient", pid)}
    if m["resourceType"] == "MedicationRequest":
        r = {"resourceType": "MedicationRequest", **base, "intent": m["intent"], "authoredOn": m["authoredOn"],
             "dosageInstruction": [{"text": m["text"]}]}
    elif m["resourceType"] == "MedicationStatement":
        r = {"resourceType": "MedicationStatement", **base}
        if m.get("effective_end"):
            r["effectivePeriod"] = {"start": m["effective_start"], "end": m["effective_end"]}
        else:
            r["effectivePeriod"] = {"start": m["effective_start"]}
        r["dateAsserted"] = m["dateAsserted"]
    elif m["resourceType"] == "MedicationDispense":
        r = {"resourceType": "MedicationDispense", **base, "whenHandedOver": m["whenHandedOver"],
             "authorizingPrescription": [ref("MedicationRequest", m["authorizingPrescription"])],
             "quantity": {"value": 4, "unit": "pen"}}
    else:
        raise ValueError(m["resourceType"])
    if m.get("note"):
        r["note"] = [{"text": m["note"]}]
    return r


def document(pid: str, n: dict, text: str) -> dict:
    code, display = n["doc_type_loinc"], n["doc_type_display"]
    r = {"resourceType": "DocumentReference", "id": n["doc_id"], "meta": meta(), "status": "current", "docStatus": "final",
         "type": {"coding": [{"system": C.LOINC, "code": code, "display": display}], "text": n["note_type"]},
         "category": [{"text": n["note_type"]}],
         "subject": ref("Patient", pid), "date": note_time(n["doc_id"], n["date"]),
         "description": f"{n['note_type']} — {n['author_role']}",
         "content": [{"attachment": {"contentType": "text/plain; charset=utf-8", "language": "en-US",
                                     "data": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                                     "title": f"{n['note_type']} {n['date']}", "creation": n["date"]}}],
         "context": {"period": {"start": n["date"], "end": n["date"]}}}
    if n.get("encounter_id"):
        r["context"]["encounter"] = [ref("Encounter", n["encounter_id"])]
    return r


def build(pid: str) -> dict:
    plan = json.loads((ROOT / f"data/_generation/plans/{pid}.json").read_text())
    notes = json.loads((ROOT / f"data/notes/{pid}.json").read_text())["notes"]
    resources = [patient(plan)]
    resources += [encounter(pid, e) for e in plan["encounters"]]
    resources += [condition(pid, c) for c in plan["conditions"]]
    resources += [observation(pid, o) for o in plan["observations"]]
    resources += [medication(pid, m) for m in plan["medications"]]
    resources += [document(pid, n, notes[n["doc_id"]]) for n in plan["notes"]]
    entries = [{"fullUrl": f"urn:uuid:{uuid.uuid5(UUID_NS, r['resourceType'] + '/' + r['id'])}", "resource": r,
                "request": {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}} for r in resources]
    return {"resourceType": "Bundle", "id": f"{pid}-BUNDLE", "meta": meta(), "type": "transaction", "entry": entries}


def main() -> int:
    out = ROOT / "data/fhir/bundles"
    out.mkdir(parents=True, exist_ok=True)
    pids = sorted(p.stem for p in (ROOT / "data/_generation/plans").glob("GLP1-*.json"))
    total = 0
    for pid in pids:
        b = build(pid)
        ids = [e["request"]["url"] for e in b["entry"]]
        assert len(ids) == len(set(ids)), f"duplicate resource ids in {pid}"
        (out / f"{pid}.json").write_text(json.dumps(b, indent=2, ensure_ascii=False) + "\n")
        total += len(b["entry"])
    print(f"bundles: {len(pids)}  resources: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
