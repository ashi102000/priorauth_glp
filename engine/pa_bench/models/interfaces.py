"""Provider-neutral model interfaces. Evaluation code never imports provider-specific modules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class CallRecord:
    """One model call. Raw usage is kept so cost can be recomputed under any pricing version."""
    provider: str
    model: str
    stage: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    latency_ms: float = 0.0            # wall-clock of the successful attempt
    total_latency_ms: float = 0.0      # including retries/backoff
    attempts: int = 0
    request_id: str | None = None
    prompt_sha256: str = ""
    output_text: str = ""
    parsed: Any = None
    probabilities: dict[str, float] | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class StructuredLLM(Protocol):
    provider: str
    model: str

    def generate(self, *, system: str, user: str, schema: dict, schema_name: str, stage: str,
                 max_output_tokens: int = 4000) -> CallRecord: ...


class DecisionProvider(Protocol):
    """Bounded-decision provider (Jev). Implemented in Phase 5 from the official API docs."""
    provider: str
    model: str

    def binary_decision(self, *, question: str, context: str, stage: str) -> CallRecord: ...
    def choice_decision(self, *, question: str, options: list[str], context: str, stage: str) -> CallRecord: ...
    def score_decision(self, *, question: str, context: str, stage: str) -> CallRecord: ...
