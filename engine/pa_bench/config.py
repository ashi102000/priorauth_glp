"""Runtime configuration (env + versioned config files). No secrets are ever logged."""
from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from .paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def request_date() -> date:
    return date.fromisoformat(os.environ.get("PA_INDEX_DATE", "2026-09-01"))


def pa_request() -> dict:
    """PA request context sent to pipelines — identical for every case in this cohort."""
    return {"drug": "Wegovy (semaglutide 2.4 mg injection)", "indication": "chronic_weight_management",
            "request_type": "initial", "request_date": request_date().isoformat()}


@lru_cache(maxsize=1)
def retrieval_config() -> dict:
    return json.loads((ROOT / "config/retrieval.json").read_text())
