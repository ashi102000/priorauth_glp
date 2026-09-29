"""Structured feature extraction (code, no models) from FHIR resources, as of the PA request date."""
from __future__ import annotations

from datetime import date

from ..calc import age_on
from ..retrieval.lexicon import ANTI_OBESITY_MED_TERMS, WEIGHT_RELATED_CONDITION_TERMS
from .client import FhirClient
from .parser import blood_pressure, codeable_text, condition_status, observation_code, observation_date, observation_value

LOINC = {"weight": "29463-7", "bmi": "39156-5", "height": "8302-2", "bp": "85354-9", "a1c": "4548-4", "ldl": "13457-7",
         "hdl": "2085-9", "tg": "2571-8"}


def _med_date(m: dict) -> str | None:
    return (m.get("authoredOn") or m.get("whenHandedOver") or m.get("dateAsserted")
            or (m.get("effectivePeriod") or {}).get("start") or m.get("effectiveDateTime"))


def _series(obs: list[dict], code: str, as_of: date) -> list[dict]:
    rows = [{"resource_id": f"Observation/{o['id']}", "date": observation_date(o).isoformat(), "value": observation_value(o)}
            for o in obs if observation_code(o) == code and observation_date(o) <= as_of]
    return sorted(rows, key=lambda r: r["date"])


def extract_features(client: FhirClient, patient_id: str, as_of: date) -> dict:
    ev = client.everything(patient_id)
    pt = ev["Patient"][0]
    birth = date.fromisoformat(pt["birthDate"])
    obs = ev.get("Observation", [])

    bmi = _series(obs, LOINC["bmi"], as_of)
    weights = _series(obs, LOINC["weight"], as_of)
    heights = _series(obs, LOINC["height"], as_of)
    bps = sorted(({"resource_id": f"Observation/{o['id']}", "date": observation_date(o).isoformat(),
                   "systolic": blood_pressure(o)[0], "diastolic": blood_pressure(o)[1]}
                  for o in obs if observation_code(o) == LOINC["bp"] and observation_date(o) <= as_of and blood_pressure(o)),
                 key=lambda r: r["date"])
    labs = {name: _series(obs, code, as_of) for name, code in LOINC.items() if name in ("a1c", "ldl", "hdl", "tg")}

    conditions = []
    for c in ev.get("Condition", []):
        text = codeable_text(c["code"])
        conditions.append({"resource_id": f"Condition/{c['id']}", "display": text, "clinical_status": condition_status(c),
                           "onset": c.get("onsetDateTime"), "abatement": c.get("abatementDateTime"),
                           "weight_related": any(t in text.lower() for t in WEIGHT_RELATED_CONDITION_TERMS)})

    meds, requested = [], None
    for rtype in ("MedicationRequest", "MedicationStatement", "MedicationDispense"):
        for m in ev.get(rtype, []):
            text = codeable_text(m["medicationCodeableConcept"])
            d = _med_date(m)
            row = {"resource_id": f"{rtype}/{m['id']}", "resource_type": rtype, "text": text, "status": m["status"], "date": d,
                   "anti_obesity": any(t in text.lower() for t in ANTI_OBESITY_MED_TERMS)}
            if (rtype == "MedicationRequest" and m["status"] == "draft" and "wegovy" in text.lower()
                    and d and date.fromisoformat(d[:10]) <= as_of):
                if requested is None or d > requested["date"]:
                    requested = row
                continue
            if d and date.fromisoformat(d[:10]) > as_of:
                continue
            meds.append(row)
    if requested:
        requested["is_requested_order"] = True
    meds.sort(key=lambda r: (r["date"] or "", r["resource_id"]))

    return {
        "patient_id": patient_id,
        "as_of": as_of.isoformat(),
        "demographics": {"birth_date": birth.isoformat(), "age": age_on(birth, as_of), "gender": pt.get("gender")},
        "bmi": {"latest": bmi[-1] if bmi else None, "history": bmi},
        "weight": {"latest": weights[-1] if weights else None, "history": weights},
        "height": heights[-1] if heights else None,
        "blood_pressure": {"latest": bps[-1] if bps else None, "history": bps},
        "labs": {k: v[-1] if v else None for k, v in labs.items()},
        "conditions": sorted(conditions, key=lambda c: c["resource_id"]),
        "weight_related_conditions": [c for c in conditions if c["weight_related"]],
        "medications": meds,
        "anti_obesity_medications": [m for m in meds if m["anti_obesity"]],
        "requested_order": requested,
        "counts": {t: len(v) for t, v in sorted(ev.items())},
    }
