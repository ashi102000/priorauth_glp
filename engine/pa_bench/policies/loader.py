"""Load normalized, user-verified payer policies (policies/*.json)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)
POLICY_DIR = ROOT / "policies"


class UnverifiedPolicyError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def load_policy(policy_id: str, allow_unverified: bool = False) -> dict:
    path = POLICY_DIR / f"{policy_id}.json"
    pol = json.loads(path.read_text())
    status = pol["human_verification"]["status"]
    if not allow_unverified and status not in ("verified", "verified_with_changes"):
        raise UnverifiedPolicyError(f"{policy_id} is '{status}'; benchmark runs require verified policies")
    return pol


def policy_ids() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.json") if not p.name.startswith("_"))


def load_all(allow_unverified: bool = False) -> list[dict]:
    return [load_policy(pid, allow_unverified) for pid in policy_ids()]


def criterion(policy: dict, criterion_id: str) -> dict:
    for c in policy["criteria"]:
        if c["criterion_id"] == criterion_id:
            return c
    raise KeyError(f"{policy['policy_id']} has no criterion {criterion_id}")
