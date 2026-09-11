from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.intelligence.schemas import ModelClass
from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class ProviderAdapter(Protocol):
    name: str
    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, timeout: float) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelRoute:
    model_class: ModelClass
    model: str
    max_tokens: int
    timeout: float
    retries: int


ROUTES = {
    ModelClass.FAST: ModelRoute(ModelClass.FAST, "fast", 700, 12, 1),
    ModelClass.REASONING: ModelRoute(ModelClass.REASONING, "reasoning", 1800, 30, 1),
    ModelClass.EXTRACTION: ModelRoute(ModelClass.EXTRACTION, "extraction", 2200, 30, 2),
    ModelClass.EMBEDDING: ModelRoute(ModelClass.EMBEDDING, "embedding", 0, 30, 1),
}


@dataclass(frozen=True)
class GatewayResult:
    value: BaseModel
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_micros: int
    latency_ms: int
    degraded: bool = False


class ModelGateway:
    """The only model-provider boundary used by new Gigi code."""
    def __init__(self, providers: list[ProviderAdapter] | None = None):
        self.providers = providers or []

    def structured(self, *, model_class: ModelClass, system: str, prompt: str,
                   schema: type[T], fallback: T) -> GatewayResult:
        route = ROUTES[model_class]
        started = time.monotonic()
        for provider in self.providers:
            for _ in range(route.retries + 1):
                try:
                    schema_prompt = f"{prompt}\nReturn only JSON matching this schema: {schema.model_json_schema()}"
                    raw = provider.complete(model=route.model, system=system, prompt=schema_prompt,
                                            max_tokens=route.max_tokens, timeout=route.timeout)
                    usage = raw.pop("_usage", {}) if isinstance(raw, dict) else {}
                    value = schema.model_validate(raw)
                    return GatewayResult(value, provider.name, route.model,
                        int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)),
                        int(usage.get("cost_micros", 0)), int((time.monotonic() - started) * 1000))
                except (TimeoutError, ValueError, TypeError):
                    continue
        return GatewayResult(fallback, "deterministic", "safe-fallback", 0, 0, 0,
                             int((time.monotonic() - started) * 1000), True)


class GroqAdapter:
    name = "groq"
    def __init__(self, api_key: str, model_map: dict[str, str]):
        self.api_key, self.model_map = api_key, model_map

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, timeout: float) -> dict[str, Any]:
        import json
        from groq import Groq
        response = Groq(api_key=self.api_key, timeout=timeout).chat.completions.create(
            model=self.model_map.get(model, self.model_map["reasoning"]), temperature=0.1,
            max_tokens=max_tokens, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        content = response.choices[0].message.content or "{}"
        value = json.loads(content)
        usage = getattr(response, "usage", None)
        value["_usage"] = {"input_tokens": getattr(usage, "prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0), "cost_micros": 0}
        return value


def configured_gateway() -> ModelGateway:
    settings = get_settings()
    if settings.ai_provider == "groq" and settings.groq_api_key:
        return ModelGateway([GroqAdapter(settings.groq_api_key, {
            "fast": settings.agent_fast_model, "reasoning": settings.agent_primary_model,
            "extraction": settings.agent_primary_model})])
    return ModelGateway()
