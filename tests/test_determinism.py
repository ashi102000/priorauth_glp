"""Frozen artifacts must be exactly reproducible from the generator + frozen notes."""
import json

import pytest

from pa_bench.generation.plan import build_plan


@pytest.mark.parametrize("pid", [f"GLP1-{i:03d}" for i in range(1, 51)])
def test_plan_regenerates_identically(pid, root, spec):
    p = next(x for x in spec if x["patient_id"] == pid)
    plan, _ = build_plan(p)
    frozen = json.loads((root / f"data/_generation/plans/{pid}.json").read_text())
    assert json.loads(json.dumps(plan)) == frozen


def test_bundles_rebuild_identically(root):
    import build_fhir
    for pid in ("GLP1-001", "GLP1-038", "GLP1-048"):
        rebuilt = json.loads(json.dumps(build_fhir.build(pid), ensure_ascii=False))
        assert rebuilt == json.loads((root / f"data/fhir/bundles/{pid}.json").read_text())
