from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from .base import LLMGenerationResult


BASE_SYSTEM_INSTRUCTION = (
    "You are LawCopilot. Reply in Turkish, be concise, and prefer source-grounded legal assistance. "
    "Always preserve natural Turkish spelling, spacing, and punctuation, and never merge adjacent words."
)


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


def _gemini_model_path(model: str) -> str:
    cleaned = str(model or "").strip()
    if cleaned.startswith("models/"):
        return cleaned
    return f"models/{cleaned}"


def _extract_gemini_text(payload: Any, *, strip_parts: bool = True) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for item in parts:
        if not isinstance(item, dict):
            continue
        raw = item.get("text")
        if raw is None:
            continue
        text = str(raw)
        if text == "":
            continue
        texts.append(text)
    if not texts:
        return ""
    combined = "".join(texts)
    return combined.strip() if strip_parts else combined


def _coerce_stream_delta(chunk_text: str, emitted_text: str) -> tuple[str, str]:
    current = str(chunk_text or "")
    emitted = str(emitted_text or "")
    if not current:
        return "", emitted
    if not emitted:
        return current, current
    if current == emitted:
        return "", emitted
    if current.startswith(emitted):
        return current[len(emitted) :], current
    if emitted.endswith(current):
        return "", emitted
    return current, emitted + current


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
        if self.provider_type not in {"openai", "openai-compatible", "ollama", "gemini"}:
            return False
        if not self.configured:
            return False
        if not self.base_url or not self.model:
            return False
        if self.provider_type != "ollama" and not self.api_key:
            return False
        return True

    @property
    def supports_vision(self) -> bool:
        return self.enabled and self.provider_type in {"openai", "openai-compatible", "gemini"}

    @property
    def supports_audio(self) -> bool:
        return self.enabled and self.provider_type in {"openai", "openai-compatible", "gemini"}

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
            if self.provider_type == "gemini":
                return self._generate_gemini(prompt)
            return self._generate_openai_compatible(prompt)
        except httpx.TimeoutException:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="direct_provider_timeout")
        except httpx.HTTPError as exc:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error=f"direct_provider_http_error:{exc}")

    def stream(self, prompt: str) -> Any:
        if not self.enabled:
            raise RuntimeError("direct_provider_not_enabled")
        if not prompt.strip():
            raise RuntimeError("empty_prompt")
        if self.provider_type == "ollama":
            return self._stream_ollama(prompt)
        if self.provider_type == "gemini":
            return self._stream_gemini(prompt)
        if self.provider_type in {"openai", "openai-compatible"}:
            return self._stream_openai_compatible(prompt)
        raise RuntimeError("streaming_not_supported")

    def structured_generate(self, prompt: str, schema: dict[str, Any] | None = None) -> LLMGenerationResult:
        _ = schema
        return self.generate(prompt)

    def analyze_image(self, *, content: bytes, mime_type: str, prompt: str) -> LLMGenerationResult:
        if not self.supports_vision:
            return LLMGenerationResult(
                ok=False,
                provider=self.provider_type or "direct-provider",
                model=self.model,
                error="vision_not_enabled",
            )
        if not content:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="empty_image")
        try:
            if self.provider_type == "gemini":
                return self._generate_gemini_vision(content=content, mime_type=mime_type, prompt=prompt)
            return self._generate_openai_compatible_vision(content=content, mime_type=mime_type, prompt=prompt)
        except httpx.TimeoutException:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="direct_provider_timeout")
        except httpx.HTTPError as exc:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error=f"direct_provider_http_error:{exc}")

    def analyze_audio(self, *, content: bytes, mime_type: str, prompt: str, filename: str = "ses-kaydi") -> LLMGenerationResult:
        if not self.supports_audio:
            return LLMGenerationResult(
                ok=False,
                provider=self.provider_type or "direct-provider",
                model=self.model,
                error="audio_not_enabled",
            )
        if not content:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="empty_audio")
        try:
            if self.provider_type == "gemini":
                return self._generate_gemini_audio(content=content, mime_type=mime_type, prompt=prompt)
            return self._generate_openai_compatible_audio_transcription(
                content=content,
                mime_type=mime_type,
                prompt=prompt,
                filename=filename,
            )
        except httpx.TimeoutException:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error="direct_provider_timeout")
        except httpx.HTTPError as exc:
            return LLMGenerationResult(ok=False, provider=self.provider_type, model=self.model, error=f"direct_provider_http_error:{exc}")

    def _preferred_audio_model(self) -> str:
        normalized = str(self.model or "").strip()
        normalized_lower = normalized.lower()
        if any(token in normalized_lower for token in ("transcribe", "whisper")):
            return normalized
        return "gpt-4o-mini-transcribe"

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
                            "content": BASE_SYSTEM_INSTRUCTION,
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

    def _generate_openai_compatible_vision(self, *, content: bytes, mime_type: str, prompt: str) -> LLMGenerationResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        encoded = base64.b64encode(content).decode("ascii")
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": BASE_SYSTEM_INSTRUCTION,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                                },
                            ],
                        },
                    ],
                    "temperature": 0.1,
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

    def _generate_openai_compatible_audio_transcription(
        self,
        *,
        content: bytes,
        mime_type: str,
        prompt: str,
        filename: str,
    ) -> LLMGenerationResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        model_name = self._preferred_audio_model()
        with httpx.Client(timeout=max(self.timeout_seconds, 90)) as client:
            response = client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                data={
                    "model": model_name,
                    "prompt": prompt,
                    "response_format": "text",
                },
                files={
                    "file": (filename, content, mime_type or "application/octet-stream"),
                },
            )
        raw_text = response.text or ""
        try:
            payload = response.json()
        except ValueError:
            payload = {"text": raw_text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider=self.provider_type,
                model=model_name,
                error=_payload_error(payload, f"direct_provider_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": raw_text},
            )
        text = ""
        if isinstance(payload, dict):
            text = str(payload.get("text") or "").strip()
        if not text:
            text = raw_text.strip()
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider=self.provider_type,
            model=model_name,
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": raw_text},
        )

    def _stream_openai_compatible(self, prompt: str):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        def iterator():
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": BASE_SYSTEM_INSTRUCTION,
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code >= 400:
                        payload = self._safe_stream_error_payload(response)
                        raise RuntimeError(_payload_error(payload, f"direct_provider_failed:{response.status_code}"))
                    for payload in self._iter_sse_payloads(response):
                        if not isinstance(payload, dict):
                            continue
                        choices = payload.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        delta = (choices[0] or {}).get("delta") or {}
                        if not isinstance(delta, dict):
                            continue
                        text = str(delta.get("content") or "")
                        if text:
                            yield text

        return iterator()

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

    def _stream_ollama(self, prompt: str):
        def iterator():
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code >= 400:
                        payload = self._safe_stream_error_payload(response)
                        raise RuntimeError(_payload_error(payload, f"ollama_failed:{response.status_code}"))
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        text = str(payload.get("response") or "")
                        if text:
                            yield text

        return iterator()

    def _generate_gemini(self, prompt: str) -> LLMGenerationResult:
        model_path = _gemini_model_path(self.model)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/{model_path}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {
                        "parts": [
                            {
                                "text": BASE_SYSTEM_INSTRUCTION,
                            }
                        ]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.2,
                    },
                },
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider="gemini",
                model=self.model,
                error=_payload_error(payload, f"gemini_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": response.text},
            )
        text = _extract_gemini_text(payload)
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider="gemini",
            model=self.model,
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": response.text},
        )

    def _generate_gemini_vision(self, *, content: bytes, mime_type: str, prompt: str) -> LLMGenerationResult:
        model_path = _gemini_model_path(self.model)
        encoded = base64.b64encode(content).decode("ascii")
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/{model_path}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {
                        "parts": [
                            {
                                "text": BASE_SYSTEM_INSTRUCTION,
                            }
                        ]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {"inline_data": {"mime_type": mime_type, "data": encoded}},
                            ],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                    },
                },
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider="gemini",
                model=self.model,
                error=_payload_error(payload, f"gemini_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": response.text},
            )
        text = _extract_gemini_text(payload)
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider="gemini",
            model=self.model,
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": response.text},
        )

    def _generate_gemini_audio(self, *, content: bytes, mime_type: str, prompt: str) -> LLMGenerationResult:
        model_path = _gemini_model_path(self.model)
        encoded = base64.b64encode(content).decode("ascii")
        with httpx.Client(timeout=max(self.timeout_seconds, 90)) as client:
            response = client.post(
                f"{self.base_url}/{model_path}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {
                        "parts": [
                            {
                                "text": BASE_SYSTEM_INSTRUCTION,
                            }
                        ]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {"inline_data": {"mime_type": mime_type, "data": encoded}},
                            ],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                    },
                },
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            return LLMGenerationResult(
                ok=False,
                provider="gemini",
                model=self.model,
                error=_payload_error(payload, f"gemini_failed:{response.status_code}"),
                raw=payload if isinstance(payload, dict) else {"raw": response.text},
            )
        text = _extract_gemini_text(payload)
        return LLMGenerationResult(
            ok=bool(text),
            text=text,
            provider="gemini",
            model=self.model,
            error=None if text else "direct_provider_empty_text",
            raw=payload if isinstance(payload, dict) else {"raw": response.text},
        )

    def _stream_gemini(self, prompt: str):
        model_path = _gemini_model_path(self.model)

        def iterator():
            emitted_text = ""
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/{model_path}:streamGenerateContent",
                    params={"key": self.api_key, "alt": "sse"},
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {
                            "parts": [
                                {
                                    "text": BASE_SYSTEM_INSTRUCTION,
                                }
                            ]
                        },
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": prompt}],
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.2,
                        },
                    },
                ) as response:
                    if response.status_code >= 400:
                        payload = self._safe_stream_error_payload(response)
                        raise RuntimeError(_payload_error(payload, f"gemini_failed:{response.status_code}"))
                    for payload in self._iter_sse_payloads(response):
                        text = _extract_gemini_text(payload, strip_parts=False)
                        delta, emitted_text = _coerce_stream_delta(text, emitted_text)
                        if delta:
                            yield delta

        return iterator()

    @staticmethod
    def _iter_sse_payloads(response: httpx.Response):
        for line in response.iter_lines():
            if not line:
                continue
            cleaned = str(line).strip()
            if not cleaned.startswith("data:"):
                continue
            data = cleaned[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            yield payload

    @staticmethod
    def _safe_stream_error_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.read().decode("utf-8", errors="ignore")}
