from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMGenerationResult:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    error: str | None = None
    raw: dict[str, Any] | None = None


class LLMProvider(Protocol):
    @property
    def enabled(self) -> bool: ...

    def generate(self, prompt: str) -> LLMGenerationResult: ...

    def stream(self, prompt: str) -> Any: ...

    def structured_generate(self, prompt: str, schema: dict[str, Any] | None = None) -> LLMGenerationResult: ...
