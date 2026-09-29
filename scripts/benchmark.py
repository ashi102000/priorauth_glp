"""Benchmark CLI.

Examples:
  python scripts/benchmark.py --pipeline gpt --all
  python scripts/benchmark.py --pipeline hybrid --all --threshold 0.90
  python scripts/benchmark.py --pipeline hybrid --all --sweep 0.60,0.70,0.80,0.90,0.95
  python scripts/benchmark.py --pipeline gpt --patient GLP1-017 --policy UHC_WEGOVY_P1114_22_2026_09_01
Resumes automatically when --run-id points at an existing run; completed model calls are served from the
request-keyed cache unless --force.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
from pa_bench.benchmark.cache import CachedJev, CachedLLM  # noqa: E402
from pa_bench.benchmark.manifest import build_manifest, write_manifest  # noqa: E402
from pa_bench.benchmark.runner import Runner  # noqa: E402
from pa_bench.fhir.client import LocalBundleClient  # noqa: E402
from pa_bench.policies.loader import load_all, load_policy  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=["gpt", "hybrid"], required=True)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--patient", action="append", default=[])
    ap.add_argument("--policy", action="append", default=[])
    ap.add_argument("--threshold", type=float, default=float(os.environ.get("JEV_AUTO_THRESHOLD", "0.90")))
    ap.add_argument("--sweep", help="comma-separated thresholds (hybrid)")
    ap.add_argument("--narrative", default=os.environ.get("HYBRID_NARRATIVE", "ready_only"), choices=["ready_only", "all", "none"])
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--run-id")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if not (a.all or a.patient or a.policy):
        ap.error("choose --all or --patient/--policy")

    from pa_bench.models.openai_provider import OpenAIProvider
    base_llm = OpenAIProvider()
    llm = CachedLLM(base_llm, force=a.force)
    jev = None
    if a.pipeline == "hybrid":
        from pa_bench.models.jev_provider import JevProvider
        jev = CachedJev(JevProvider(), force=a.force)
    policies = [load_policy(p) for p in a.policy] if a.policy else load_all()
    pids = a.patient or LocalBundleClient().patient_ids()
    jobs = [(pid, pol) for pid in pids for pol in policies]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    thresholds = [float(t) for t in a.sweep.split(",")] if a.sweep else [a.threshold]
    base_id = a.run_id or f"{stamp}_{a.pipeline}"
    for thr in thresholds:
        run_id = base_id if a.pipeline == "gpt" else (f"{base_id}_t{thr:.2f}" if (a.sweep or not a.run_id) else base_id)
        run_dir = ROOT / "results/runs" / run_id
        man = build_manifest(run_id=run_id, pipeline=a.pipeline, evaluations=[f"{p}__{q['policy_id']}" for p, q in jobs],
                             policies=policies, gpt_model=base_llm.model, reasoning_effort=base_llm.reasoning_effort,
                             jev_model=jev.model if jev else None, threshold=thr, narrative_mode=a.narrative,
                             concurrency=a.concurrency, force=a.force, sweep_of=base_id if a.sweep else None)
        write_manifest(run_dir, man)
        stats = Runner(run_dir, a.pipeline, llm, jev, threshold=thr, narrative_mode=a.narrative,
                       concurrency=a.concurrency).run(jobs, run_id, force=a.force)
        print(f"[{run_id}] done: ok={stats['ok']} errors={stats['error']} new-run cost ${stats['cost']:.4f} -> {run_dir.relative_to(ROOT)}")
        if a.pipeline == "gpt":
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
