from __future__ import annotations

from pathlib import Path

from lawcopilot_api.observability import StructuredLogger


def test_structured_logger_redacts_sensitive_payload_fields(tmp_path: Path) -> None:
    logger = StructuredLogger(tmp_path / "events.jsonl")

    logger.log(
        "assistant_request",
        prompt="Bana özel mesaj içeriğini tekrar yaz.",
        response_text="Özel yanıt gövdesi",
        access_token="secret-token",
        safe_counter=3,
    )

    recent = logger.recent(limit=1)[0]

    assert recent["prompt"] == "[redacted]"
    assert recent["prompt_redacted"] is True
    assert recent["prompt_size"] > 0
    assert recent["response_text"] == "[redacted]"
    assert recent["access_token"] == "[redacted]"
    assert recent["safe_counter"] == 3


def test_structured_logger_redacts_nested_sensitive_fields(tmp_path: Path) -> None:
    logger = StructuredLogger(tmp_path / "events.jsonl")

    logger.log(
        "connector_event",
        provider="whatsapp",
        payload={
            "message_text": "Müşteri ekran görüntüsü attı.",
            "summary": "Yeni müşteri etkileşimi",
            "oauth_secret": "hidden",
        },
    )

    recent = logger.recent(limit=1)[0]
    payload = dict(recent["payload"])

    assert payload["message_text"] == "[redacted]"
    assert payload["message_text_redacted"] is True
    assert payload["oauth_secret"] == "[redacted]"
    assert payload["summary"] == "Yeni müşteri etkileşimi"
