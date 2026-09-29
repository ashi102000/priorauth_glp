"""M1.5: validate the local FHIR bundles.

Run under the strict R4 validator venv (fhir.resources 5.1.1 = FHIR 4.0.1):
    .venv-r4/bin/python scripts/validate_fhir.py
It also runs under the main venv, where it validates against R4B (4.3.0) models.

Checks: per-resource schema validation, id format, reference integrity inside each bundle,
cohort tag present (and nothing else in meta.tag), DocumentReference text round-trips to data/notes.
"""
import base64
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import importlib  # noqa: E402

import fhir.resources as fr  # noqa: E402

if fr.__fhir_version__.startswith("4.0"):          # fhir.resources 5.x -> FHIR R4 4.0.1 (strict)
    PKG, FHIR_VERSION = "fhir.resources", f"{fr.__fhir_version__} (R4)"
else:                                               # fhir.resources 7.x default is R5; use its R4B subpackage
    PKG, FHIR_VERSION = "fhir.resources.R4B", "4.3.0 (R4B)"


def construct_fhir_element(rt: str, data: dict):
    cls = getattr(importlib.import_module(f"{PKG}.{rt.lower()}"), rt)
    for api in ("model_validate", "parse_obj"):     # pydantic-based models (7.x R4B)
        if hasattr(cls, api):
            return getattr(cls, api)(data)
    return cls(data, strict=True)                   # fhirclient-style models (5.x R4): raises FHIRValidationError

ID_RE = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


def refs(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "reference" and isinstance(v, str):
                yield v
            else:
                yield from refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from refs(v)


def main() -> int:
    errors, counts = [], Counter()
    bundles = sorted((ROOT / "data/fhir/bundles").glob("GLP1-*.json"))
    for bp in bundles:
        pid = bp.stem
        b = json.loads(bp.read_text())
        notes = json.loads((ROOT / f"data/notes/{pid}.json").read_text())["notes"]
        try:
            construct_fhir_element("Bundle", {k: v for k, v in b.items() if k != "entry"} | {"entry": []})
        except Exception as e:  # noqa: BLE001
            errors.append(f"{pid}: Bundle shell invalid: {e}")
        present = {e["request"]["url"] for e in b["entry"]}
        for e in b["entry"]:
            r = e["resource"]
            rt, rid = r["resourceType"], r["id"]
            counts[rt] += 1
            if not ID_RE.match(rid):
                errors.append(f"{pid}: bad id {rt}/{rid}")
            if e["request"]["url"] != f"{rt}/{rid}" or e["request"]["method"] != "PUT":
                errors.append(f"{pid}: bad request for {rt}/{rid}")
            if r.get("meta", {}).get("tag") != [{"system": "urn:jev-pa-benchmark", "code": "GLP1_PA_COHORT_V1",
                                                 "display": "GLP-1 PA benchmark cohort v1"}]:
                errors.append(f"{pid}: unexpected meta.tag on {rt}/{rid}")
            try:
                construct_fhir_element(rt, r)
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{pid}: {rt}/{rid} invalid: {str(ex)[:300]}")
            for ref in refs(r):
                if ref not in present:
                    errors.append(f"{pid}: {rt}/{rid} dangling reference {ref}")
            if rt == "DocumentReference":
                txt = base64.b64decode(r["content"][0]["attachment"]["data"]).decode("utf-8")
                if txt != notes.get(rid):
                    errors.append(f"{pid}: DocumentReference/{rid} text does not match data/notes")
        doc_ids = {e["resource"]["id"] for e in b["entry"] if e["resource"]["resourceType"] == "DocumentReference"}
        if doc_ids != set(notes):
            errors.append(f"{pid}: DocumentReference set != note set")
    print(f"FHIR version validated against: {FHIR_VERSION}")
    print(f"bundles: {len(bundles)}  resources: {sum(counts.values())}")
    for k, v in sorted(counts.items()):
        print(f"  {k:<20} {v}")
    for e in errors[:50]:
        print("ERROR", e)
    print(f"\nRESULT: {'FAIL' if errors else 'PASS'} ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
