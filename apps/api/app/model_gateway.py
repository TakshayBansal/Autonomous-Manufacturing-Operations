"""Provider-independent structured model gateway with bounded retries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
Provider = Callable[[str, str, int, float], dict[str, Any]]


@dataclass(frozen=True)
class ModelTaskProfile:
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_retries: int
    prompt_version: str
    cost_limit_micros: int


TASK_PROFILES = {
    "classification": ModelTaskProfile("fast", 10, 600, 1, "classification@1", 500),
    "extraction_repair": ModelTaskProfile("extraction", 30, 2400, 2, "extraction-repair@1", 5000),
    "explanation": ModelTaskProfile("primary", 20, 1000, 1, "explanation@1", 2500),
    "scenario_narration": ModelTaskProfile("primary", 30, 1600, 1, "scenario-narration@1", 4000),
}


class ModelGateway:
    def __init__(self, providers: dict[str, Provider] | None = None):
        self.providers = providers or {}

    def structured(self, task: str, prompt: str, schema: type[T], *, provider: str = "default",
                   fallback: Callable[[], dict[str, Any]] | None = None) -> T:
        profile = TASK_PROFILES[task]
        adapter = self.providers.get(provider)
        last_error: Exception | None = None
        if adapter:
            for _attempt in range(profile.max_retries + 1):
                try:
                    raw = adapter(prompt, profile.model, profile.max_output_tokens, profile.timeout_seconds)
                    return schema.model_validate(raw)
                except (TimeoutError, ValidationError, ValueError) as exc:
                    last_error = exc
        if fallback is not None:
            return schema.model_validate(fallback())
        raise RuntimeError(f"Structured model task failed: {task}") from last_error
