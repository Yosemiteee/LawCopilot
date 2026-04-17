from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse


def _segment_text(transcript: str, *, max_segments: int) -> list[dict[str, Any]]:
    words = str(transcript or "").split()
    if not words:
        return []
    chunk_size = max(40, min(180, max(1, len(words) // max(1, max_segments))))
    items: list[dict[str, Any]] = []
    for index in range(0, len(words), chunk_size):
        part = " ".join(words[index : index + chunk_size]).strip()
        if not part:
            continue
        items.append(
            {
                "segment_index": len(items) + 1,
                "text": part,
                "excerpt": (part[:319] + "…") if len(part) > 320 else part,
            }
        )
    return items[:max_segments]


def _youtube_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    if "youtube.com" in parsed.netloc:
        return parse_qs(parsed.query).get("v", [""])[0]
    return ""


def _fetch_youtube_transcript(video_id: str) -> str:
    if not video_id:
        return ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception:
        return ""
    try:
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=["tr", "en"])
    except Exception:
        return ""
    parts = [str(item.get("text") or "").strip() for item in items if str(item.get("text") or "").strip()]
    return " ".join(parts).strip()


def analyze_video_url(url: str, *, transcript_text: str | None = None, max_segments: int = 40) -> dict[str, Any]:
    cleaned = str(url or "").strip()
    transcript = str(transcript_text or "").strip()
    source = "provided"
    video_id = _youtube_id(cleaned)
    if not transcript and video_id:
        transcript = _fetch_youtube_transcript(video_id)
        source = "youtube-transcript-api" if transcript else "unavailable"
    summary = (
        "Video transkripti çözümlenemedi. youtube-transcript-api kurulursa YouTube linkleri doğrudan işlenebilir."
        if not transcript
        else "Video linkinden transcript tabanlı özet çıkarıldı."
    )
    segments = _segment_text(transcript, max_segments=max_segments) if transcript else []
    return {
        "url": cleaned,
        "video_id": video_id or None,
        "transcript_source": source,
        "transcript_available": bool(transcript),
        "transcript": transcript,
        "segments": segments,
        "summary": summary,
        "citations": [
            {
                "label": f"[{item['segment_index']}]",
                "segment_index": item["segment_index"],
                "excerpt": item["excerpt"],
                "source_type": "video_transcript",
            }
            for item in segments[:5]
        ],
    }
