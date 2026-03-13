from __future__ import annotations

from typing import Any


class MemoryService:
    def __init__(self, store, office_id: str) -> None:
        self.store = store
        self.office_id = office_id

    def capture_chat_signal(self, query: str) -> list[dict[str, Any]]:
        text = " ".join(str(query or "").strip().split())
        if not text:
            return []
        lowered = text.lower()
        if not any(marker in lowered for marker in ("tercih ederim", "severim", "sevmem", "genelde", "kullanirim", "kullanırım")):
            return []
        profile = self.store.get_user_profile(self.office_id)
        existing_notes = str((profile or {}).get("assistant_notes") or "").strip()
        if text in existing_notes:
            return []
        merged = existing_notes
        if merged:
            merged = f"{merged}\n- {text}"
        else:
            merged = f"- {text}"
        updated = self.store.upsert_user_profile(
            self.office_id,
            display_name=(profile or {}).get("display_name"),
            food_preferences=(profile or {}).get("food_preferences"),
            transport_preference=(profile or {}).get("transport_preference"),
            weather_preference=(profile or {}).get("weather_preference"),
            travel_preferences=(profile or {}).get("travel_preferences"),
            communication_style=(profile or {}).get("communication_style"),
            assistant_notes=merged,
            important_dates=(profile or {}).get("important_dates") or [],
        )
        return [
            {
                "kind": "profile_signal",
                "status": "stored",
                "summary": "Kullanıcının sohbetten aktardığı tercih notu profile eklendi.",
                "value": text,
                "updated_at": updated.get("updated_at"),
            }
        ]
