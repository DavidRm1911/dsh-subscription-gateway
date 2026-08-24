"""Provider-agnostic model interface. Callers only ever see this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelCapabilities:
    streaming: bool = False
    tools: bool = False
    vision: bool = False
    reasoning: bool = False


@dataclass
class ModelMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ModelResponse:
    text: str
    model: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    raw: dict = field(default_factory=dict)


class ModelProvider(ABC):
    name: str
    capabilities: ModelCapabilities

    @abstractmethod
    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        raise NotImplementedError
