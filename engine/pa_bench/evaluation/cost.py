"""Cost accounting from raw usage + versioned pricing config (never hard-coded in inference logic)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..paths import ROOT  # noqa: E402  (PA_BENCH_ROOT-aware)


@lru_cache(maxsize=None)
def load_pricing(path: str | None = None) -> dict:
    return json.loads(Path(path or ROOT / "config/model_pricing.json").read_text())


def cost_usd(model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int, pricing: dict | None = None) -> float | None:
    """Standard-tier cost. Returns None if the model has no verified price (never guessed)."""
    pricing = pricing or load_pricing()
    p = pricing["models"].get(model)
    if p is None:
        return None
    band = p
    lc = p.get("long_context")
    if lc and input_tokens > lc["threshold_input_tokens"]:
        band = lc
    uncached = max(0, input_tokens - cached_input_tokens)
    c = (uncached * band["input_per_million"] + cached_input_tokens * band["cached_input_per_million"]
         + output_tokens * band["output_per_million"]) / 1_000_000
    return round(c, 8)


def record_cost(rec: dict, pricing: dict | None = None) -> float | None:
    return cost_usd(rec["model"], rec.get("input_tokens", 0), rec.get("cached_input_tokens", 0), rec.get("output_tokens", 0), pricing)
