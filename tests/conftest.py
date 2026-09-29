import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def spec() -> list[dict]:
    return json.loads((ROOT / "data/cohort/patients.json").read_text())["patients"]


@pytest.fixture(scope="session")
def client():
    from pa_bench.fhir.client import LocalBundleClient
    return LocalBundleClient()
