from __future__ import annotations

from typing import Any

import httpx

from .base import LLMGenerationResult


def _strip_trailing_slash(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _payload_error(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if error:
            return str(error)
        if payload.get("message"):
            return str(payload["message"])
    return fallback


class DirectProviderLLM:
    def __init__(
        self,
        *,
        provider_type: str = "",
        base_url: str = "",
        model: str = "",
        api_key: str = "",
        configured: bool = False,
        timeout_seconds: int = 45,
    ) -> None:
        self.provider_type = str(provider_type or "").strip().lower()
        self.base_url = _strip_trailing_slash(base_url)
        self.model = str(model or "").strip()
        self.api_key = str(api_key or "").strip()
        self.configured = bool(configured)
        self.timeout_seconds = max(10, int(timeout_seconds or 45))

    @property
    def enabled(self) -> bool:
        if self.provider_type not in {"openai", "openai-compatible", "ollama"}:
            return False
        if not self.configured:
            return False
        if not self.base_url or not self.model:
            return False
        if self.provider_type != "ollama" and not self.api_key:
            return False
        return True

    def generate(self, prompt: str) -> LLMGenerationResult:
        if not self.enabled:
            return LLMGenerationResult(
                ok=False,
                provider=self.provider_type or "direct-provider",
                model=self.model,
                error="direct_provider_not_enabled",
            )
        if not prompt.strip():
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="empty_prompt")
        try:
            if self.provider_type == "ollama":
                return self._generate_ollama(prompt)
            return self._generate_openai_compatible(prompt)
        except httpx.TimeoutException:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="direct_provider_timeout")
        except httpx.HTTPError as exc:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error=f"direct_provider_http_error:{exc}")

    def stream(self, prompt: str) -> Any:
        raise NotImplementedError("streaming_not_implemented")

    def structured_generate(self, prompt: str, schema: dict[str, Any] | None = None) -> LLMGenerationResult:
        _ = schema
        return self.generate(prompt)

    def _generate_openai_compatible(self, prompt: str) -> LLMGenerationResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are LawCopilot. Reply in Turkish, be concise, and prefer source-grounded legal assistance.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider=self.provider_type,
                model=self.model,
                error=_payload_error(payload, f"direct_provider_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": response.text},
            )
        text = ""
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                message = (choices[0] or {}).get("message") or {}
                if isinstance(message, dict):
                    text = str(message.get("content") or "").strip()
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider=self.provider_type,
            model=str((payload.get("model") if isinstance(payload, dict) else None) or self.model),
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": response.text},
        )

    def _generate_ollama(self, prompt: str) -> LLMGenerationResult:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider="ollama",
                model=self.model,
                error=_payload_error(payload, f"ollama_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": response.text},
            )
        text = str(payload.get("response") if isinstance(payload, dict) else "").strip()
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider="ollama",
            model=self.model,
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": response.text},
        )
