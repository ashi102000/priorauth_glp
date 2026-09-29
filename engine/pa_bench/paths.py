"""Single source of the project root. PA_BENCH_ROOT overrides it (used by the bundled web/pyengine deployment)."""
import os
from pathlib import Path

ROOT = Path(os.environ["PA_BENCH_ROOT"]).resolve() if os.environ.get("PA_BENCH_ROOT") else Path(__file__).resolve().parents[2]
