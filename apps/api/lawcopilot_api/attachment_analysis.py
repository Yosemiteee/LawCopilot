from __future__ import annotations

from pathlib import Path
from typing import Any

from .parsers import ParseError, guess_content_type, parse_document_content

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".webm", ".mp4", ".mpeg"}


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def compact_attachment_context(text: str, *, max_lines: int = 8, max_chars: int = 1200) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        lines = [_normalize_space(text)]
    compact = "\n".join(lines[:max_lines]).strip()
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars - 1].rstrip()
    cut = trimmed.rfind(" ")
    if cut > int(max_chars * 0.6):
        trimmed = trimmed[:cut]
    return trimmed.rstrip() + "…"


def is_image_attachment(filename: str, content_type: str | None = None) -> bool:
    ext = Path(filename or "").suffix.lower()
    return ext in IMAGE_EXTENSIONS or str(content_type or "").lower().startswith("image/")


def is_audio_attachment(filename: str, content_type: str | None = None) -> bool:
    ext = Path(filename or "").suffix.lower()
    return ext in AUDIO_EXTENSIONS or str(content_type or "").lower().startswith("audio/")


def _image_metadata_context(filename: str, *, content_type: str, size_bytes: int) -> str:
    label = Path(filename or "gorsel").name
    kb = max(1, round(int(size_bytes or 0) / 1024))
    return (
        f"{label} adlı görsel eklendi. Biçim: {content_type or 'bilinmiyor'}. Boyut: yaklaşık {kb} KB. "
        "Bu kurulumda görsel çözümleme aktif olmadığı için yalnız dosya bilgisi görülebiliyor."
    )


def _audio_metadata_context(filename: str, *, content_type: str, size_bytes: int) -> str:
    label = Path(filename or "ses-kaydi").name
    kb = max(1, round(int(size_bytes or 0) / 1024))
    return (
        f"{label} adlı ses kaydı eklendi. Biçim: {content_type or 'bilinmiyor'}. Boyut: yaklaşık {kb} KB. "
        "Bu kurulumda ses çözümleme aktif olmadığı için yalnız dosya bilgisi görülebiliyor."
    )


def analyze_attachment_content(
    *,
    filename: str,
    content: bytes,
    content_type: str | None,
    runtime: Any | None,
    events: Any | None = None,
    subject: str | None = None,
    analysis_prompt: str | None = None,
) -> dict[str, Any]:
    resolved_content_type = str(content_type or guess_content_type(Path(filename or "attachment.bin")))
    if is_image_attachment(filename, resolved_content_type):
        if runtime and hasattr(runtime, "analyze_image"):
            result = runtime.analyze_image(
                content=content,
                mime_type=resolved_content_type,
                prompt=analysis_prompt or (
                    "LawCopilot için bu görseli Türkçe ve kısa şekilde çözümle. "
                    "Önce okunabilen yazıları düzenli biçimde çıkar. "
                    "Ardından görselin neyi gösterdiğini ve hukuki/operasyonel açıdan önemli noktaları özetle. "
                    "Uydurma yapma; emin değilsen bunu açıkça belirt."
                ),
                events=events,
                task="assistant_attachment_analysis",
                subject=subject or "assistant",
                filename=Path(filename or "gorsel").name,
            )
            if result and result.get("text"):
                return {
                    "content_type": resolved_content_type,
                    "attachment_context": compact_attachment_context(str(result["text"])),
                    "analysis_available": True,
                    "analysis_mode": str(result.get("runtime_mode") or "direct-provider-vision"),
                    "ai_provider": result.get("provider"),
                    "ai_model": result.get("model"),
                }
        return {
            "content_type": resolved_content_type,
            "attachment_context": _image_metadata_context(
                filename,
                content_type=resolved_content_type,
                size_bytes=len(content),
            ),
            "analysis_available": False,
            "analysis_mode": "image-metadata",
            "ai_provider": None,
            "ai_model": None,
        }

    if is_audio_attachment(filename, resolved_content_type):
        if runtime and hasattr(runtime, "analyze_audio"):
            result = runtime.analyze_audio(
                content=content,
                mime_type=resolved_content_type,
                prompt=analysis_prompt or (
                    "LawCopilot için bu ses kaydını Türkçe ve kısa şekilde çözümle. "
                    "Önce konuşulanları olabildiğince doğru biçimde yazıya dök. "
                    "Ardından önemli noktaları, soruları, istekleri ve takip edilmesi gereken adımı özetle. "
                    "Uydurma yapma; emin değilsen bunu açıkça belirt."
                ),
                events=events,
                task="assistant_attachment_analysis",
                subject=subject or "assistant",
                filename=Path(filename or "ses-kaydi").name,
            )
            if result and result.get("text"):
                transcript = str(result["text"])
                return {
                    "content_type": resolved_content_type,
                    "attachment_context": compact_attachment_context(transcript, max_lines=10, max_chars=1600),
                    "analysis_available": True,
                    "analysis_mode": str(result.get("runtime_mode") or "direct-provider-audio"),
                    "text": transcript,
                    "ai_provider": result.get("provider"),
                    "ai_model": result.get("model"),
                }
        return {
            "content_type": resolved_content_type,
            "attachment_context": _audio_metadata_context(
                filename,
                content_type=resolved_content_type,
                size_bytes=len(content),
            ),
            "analysis_available": False,
            "analysis_mode": "audio-metadata",
            "ai_provider": None,
            "ai_model": None,
        }

    try:
        text, detected_type = parse_document_content(filename, content, content_type=resolved_content_type)
    except ParseError as exc:
        return {
            "content_type": resolved_content_type,
            "attachment_context": "",
            "analysis_available": False,
            "analysis_mode": "unsupported",
            "analysis_error": str(exc),
            "ai_provider": None,
            "ai_model": None,
        }
    return {
        "content_type": detected_type,
        "attachment_context": compact_attachment_context(text),
        "analysis_available": True,
        "analysis_mode": "document-text",
        "text": text,
        "ai_provider": None,
        "ai_model": None,
    }
