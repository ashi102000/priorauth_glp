"""Small helpers for reading FHIR R4 resources produced by this cohort."""
from __future__ import annotations

import base64
from datetime import date


def document_text(doc: dict) -> str:
    """Decode the first text/plain attachment of a DocumentReference."""
    att = doc["content"][0]["attachment"]
    if "data" in att:
        return base64.b64decode(att["data"]).decode("utf-8")
    raise ValueError(f"DocumentReference/{doc.get('id')} has no inline data")


def document_date(doc: dict) -> date:
    return date.fromisoformat(doc["date"][:10])


def observation_code(obs: dict) -> str:
    return obs["code"]["coding"][0]["code"]


def observation_date(obs: dict) -> date:
    return date.fromisoformat(obs["effectiveDateTime"][:10])


def observation_value(obs: dict) -> float | None:
    q = obs.get("valueQuantity")
    return float(q["value"]) if q else None


def blood_pressure(obs: dict) -> tuple[float, float] | None:
    comps = {c["code"]["coding"][0]["code"]: c["valueQuantity"]["value"] for c in obs.get("component", [])}
    if "8480-6" in comps and "8462-4" in comps:
        return float(comps["8480-6"]), float(comps["8462-4"])
    return None


def condition_status(cond: dict) -> str:
    return cond["clinicalStatus"]["coding"][0]["code"]


def codeable_text(cc: dict) -> str:
    if cc.get("text"):
        return cc["text"]
    c = (cc.get("coding") or [{}])[0]
    return c.get("display") or c.get("code", "")
