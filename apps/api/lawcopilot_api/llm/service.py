from __future__ import annotations

from typing import Any, Iterator

from ..agent_bridges.openclaw_runtime import create_openclaw_runtime
from .base import LLMGenerationResult
from .direct_provider import DirectProviderLLM


class LLMService:
    def __init__(self, *, direct_provider: DirectProviderLLM, advanced_bridge: Any | None = None) -> None:
        self.direct_provider = direct_provider
        self.advanced_bridge = advanced_bridge

    @property
    def provider_type(self) -> str:
        if self.direct_provider.enabled:
            return self.direct_provider.provider_type
        if self.advanced_bridge:
            return str(getattr(self.advanced_bridge, "provider_type", "") or "openai-codex")
        return ""

    @property
    def advanced_enabled(self) -> bool:
        return bool(self.advanced_bridge and getattr(self.advanced_bridge, "enabled", False))

    @property
    def direct_enabled(self) -> bool:
        return self.direct_provider.enabled

    @property
    def enabled(self) -> bool:
        return self.direct_enabled or self.advanced_enabled

    @property
    def runtime_mode(self) -> str:
        if self.direct_enabled:
            return "direct-provider"
        if self.advanced_enabled:
            return "advanced-openclaw"
        return "fallback-only"

    @property
    def vision_enabled(self) -> bool:
        return bool(self.direct_enabled and getattr(self.direct_provider, "supports_vision", False))

    @property
    def audio_enabled(self) -> bool:
        return bool(self.direct_enabled and getattr(self.direct_provider, "supports_audio", False))

    def complete(self, prompt: str, events=None, *, task: str, **meta) -> dict[str, Any] | None:
        result: LLMGenerationResult
        if self.direct_enabled:
            result = self.direct_provider.generate(prompt)
            if result.ok and result.text:
                if events:
                    events.log("direct_provider_runtime_used", task=task, provider=result.provider, model=result.model, **meta)
                return {
                    "text": result.text,
                    "provider": result.provider,
                    "model": result.model,
                    "runtime_mode": "direct-provider",
                }
            if events:
                events.log("direct_provider_runtime_fallback", level="warning", task=task, error=result.error, **meta)
            return None
        if self.advanced_enabled and self.advanced_bridge:
            result = self.advanced_bridge.complete(prompt)
            if result.ok and result.text:
                if events:
                    events.log("openclaw_runtime_used", task=task, provider=result.provider, model=result.model, **meta)
                return {
                    "text": result.text,
                    "provider": result.provider,
                    "model": result.model,
                    "runtime_mode": "advanced-openclaw",
                }
            if events:
                events.log("openclaw_runtime_fallback", level="warning", task=task, error=result.error, **meta)
        return None

    def stream_complete(self, prompt: str, events=None, *, task: str, **meta) -> tuple[Iterator[str] | None, dict[str, Any] | None]:
        if self.direct_enabled:
            try:
                stream = self.direct_provider.stream(prompt)
            except Exception as exc:
                if events:
                    events.log("direct_provider_stream_fallback", level="warning", task=task, error=str(exc), **meta)
                return None, None
            if events:
                events.log(
                    "direct_provider_runtime_stream_used",
                    task=task,
                    provider=self.direct_provider.provider_type,
                    model=self.direct_provider.model,
                    **meta,
                )
            return stream, {
                "provider": self.direct_provider.provider_type,
                "model": self.direct_provider.model,
                "runtime_mode": "direct-provider",
            }
        return None, None

    def analyze_image(self, *, content: bytes, mime_type: str, prompt: str, events=None, task: str, **meta) -> dict[str, Any] | None:
        if not self.vision_enabled:
            return None
        result = self.direct_provider.analyze_image(content=content, mime_type=mime_type, prompt=prompt)
        if result.ok and result.text:
            if events:
                events.log("direct_provider_vision_used", task=task, provider=result.provider, model=result.model, **meta)
            return {
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
                "runtime_mode": "direct-provider-vision",
            }
        if events:
            events.log("direct_provider_vision_fallback", level="warning", task=task, error=result.error, **meta)
        return None

    def analyze_audio(
        self,
        *,
        content: bytes,
        mime_type: str,
        prompt: str,
        filename: str,
        events=None,
        task: str,
        **meta,
    ) -> dict[str, Any] | None:
        if not self.audio_enabled:
            return None
        result = self.direct_provider.analyze_audio(
            content=content,
            mime_type=mime_type,
            prompt=prompt,
            filename=filename,
        )
        if result.ok and result.text:
            if events:
                events.log("direct_provider_audio_used", task=task, provider=result.provider, model=result.model, **meta)
            return {
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
                "runtime_mode": "direct-provider-audio",
            }
        if events:
            events.log("direct_provider_audio_fallback", level="warning", task=task, error=result.error, **meta)
        return None


def create_llm_service(settings: Any) -> LLMService:
    direct_provider = DirectProviderLLM(
        provider_type=settings.provider_type,
        base_url=settings.provider_base_url,
        model=settings.provider_model,
        api_key=getattr(settings, "provider_api_key", ""),
        configured=settings.provider_configured,
    )
    advanced_bridge = create_openclaw_runtime(settings)
    return LLMService(direct_provider=direct_provider, advanced_bridge=advanced_bridge)
