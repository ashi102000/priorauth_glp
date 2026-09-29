"""Experiment manifest — written BEFORE any result, so no result exists without one."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import request_date, retrieval_config
from ..evaluation.cost import load_pricing
from ..retrieval.profile import config_hash

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)
TRACKED = ("engine", "scripts", "policies", "config", "data/fhir/bundles", "data/notes", "ground_truth")


def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def source_tree_sha256() -> str:
    h = hashlib.sha256()
    for top in TRACKED:
        for p in sorted((ROOT / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json", ".md", ".txt"):
                h.update(str(p.relative_to(ROOT)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()


def build_manifest(*, run_id: str, pipeline: str, evaluations: list[str], policies: list[dict], gpt_model: str,
                   reasoning_effort: str, jev_model: str | None, threshold: float | None, narrative_mode: str | None,
                   concurrency: int, force: bool, sweep_of: str | None = None) -> dict:
    import openai
    cfg = retrieval_config()
    pricing = load_pricing()
    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "source_tree_sha256": source_tree_sha256(),
        "cohort_version": "GLP1_PA_COHORT_V1",
        "request_date": request_date().isoformat(),
        "pipeline": pipeline,
        "n_evaluations": len(evaluations),
        "policy_versions": [{"policy_id": p["policy_id"], "effective_date": p["effective_date"],
                             "version_as_printed": p["source"]["version_as_printed"],
                             "verification": p["human_verification"]["status"]} for p in policies],
        "models": {"gpt": gpt_model, "gpt_reasoning_effort": reasoning_effort,
                   "jev": jev_model if pipeline == "hybrid" else None},
        "jev_threshold": threshold if pipeline == "hybrid" else None,
        "hybrid_narrative": narrative_mode if pipeline == "hybrid" else None,
        "retrieval_config": cfg, "retrieval_config_hash": config_hash(cfg),
        "pricing_version": pricing["pricing_version"],
        "execution": {"concurrency": concurrency, "force": force, "sweep_of": sweep_of,
                      "python": sys.version.split()[0], "platform": platform.platform(), "openai_sdk": openai.__version__},
        "notes": "Latency = application-side wall-clock per case under the stated concurrency (same for both arms).",
    }


def write_manifest(run_dir: Path, manifest: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
