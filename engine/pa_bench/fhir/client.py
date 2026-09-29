"""FHIR data access for the benchmark.

The benchmark reads the cohort from local FHIR R4 transaction bundles (data/fhir/bundles), not from a
remote server (see DECISIONS.md). `LocalBundleClient` behaves like a minimal read-only FHIR server:
read by id, search by type + patient, and a patient `$everything`. A remote server client can be added
later by implementing the same `FhirClient` protocol.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Protocol

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)
DEFAULT_BUNDLE_DIR = ROOT / "data/fhir/bundles"

PATIENT_REF_FIELDS = ("subject", "patient")


class FhirClient(Protocol):
    def patient_ids(self) -> list[str]: ...
    def read(self, resource_type: str, resource_id: str) -> dict: ...
    def search(self, resource_type: str, patient: str | None = None) -> list[dict]: ...
    def everything(self, patient: str) -> dict[str, list[dict]]: ...


class LocalBundleClient:
    """Read-only FHIR access over local transaction bundles (one bundle per patient)."""

    def __init__(self, bundle_dir: Path | str = DEFAULT_BUNDLE_DIR):
        self.bundle_dir = Path(bundle_dir)
        if not self.bundle_dir.is_dir():
            raise FileNotFoundError(f"bundle directory not found: {self.bundle_dir}")
        self._by_key: dict[str, dict] = {}
        self._by_patient: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for path in sorted(self.bundle_dir.glob("*.json")):
            bundle = json.loads(path.read_text())
            if bundle.get("resourceType") != "Bundle":
                raise ValueError(f"{path.name} is not a FHIR Bundle")
            for entry in bundle.get("entry", []):
                r = entry["resource"]
                key = f"{r['resourceType']}/{r['id']}"
                if key in self._by_key:
                    raise ValueError(f"duplicate resource {key} ({path.name})")
                self._by_key[key] = r
                pid = r["id"] if r["resourceType"] == "Patient" else _patient_of(r)
                if pid:
                    self._by_patient[pid][r["resourceType"]].append(r)

    def patient_ids(self) -> list[str]:
        return sorted(pid for pid, types in self._by_patient.items() if "Patient" in types)

    def read(self, resource_type: str, resource_id: str) -> dict:
        key = f"{resource_type}/{resource_id}"
        if key not in self._by_key:
            raise KeyError(f"resource not found: {key}")
        return self._by_key[key]

    def search(self, resource_type: str, patient: str | None = None) -> list[dict]:
        if patient is not None:
            return list(self._by_patient.get(patient, {}).get(resource_type, []))
        return [r for k, r in self._by_key.items() if k.startswith(resource_type + "/")]

    def everything(self, patient: str) -> dict[str, list[dict]]:
        if patient not in self._by_patient:
            raise KeyError(f"unknown patient: {patient}")
        return {t: list(rs) for t, rs in self._by_patient[patient].items()}


def _patient_of(resource: dict) -> str | None:
    for f in PATIENT_REF_FIELDS:
        ref = resource.get(f, {}).get("reference", "")
        if ref.startswith("Patient/"):
            return ref.split("/", 1)[1]
    return None
