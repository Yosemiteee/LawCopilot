from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote


def _iso_to_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _time_bucket(value: str | None) -> str:
    dt = _iso_to_datetime(value) or datetime.now(timezone.utc)
    hour = dt.hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 16:
        return "midday"
    if 16 <= hour < 21:
        return "evening"
    return "night"


def _maps_handoff_url(*, label: str, latitude: float | None = None, longitude: float | None = None) -> str:
    if latitude is not None and longitude is not None:
        return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    return f"https://www.google.com/maps/search/?api=1&query={quote(label)}"


def _age_minutes(value: str | None) -> float | None:
    dt = _iso_to_datetime(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)


def _freshness_label(value: str | None) -> str:
    age_minutes = _age_minutes(value)
    if age_minutes is None:
        return "unknown"
    if age_minutes <= 20:
        return "fresh"
    if age_minutes <= 120:
        return "aging"
    if age_minutes <= 360:
        return "stale"
    return "expired"


@dataclass
class LocationObservation:
    place_id: str
    label: str
    category: str
    area: str = ""
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = None
    started_at: str | None = None
    ended_at: str | None = None
    scope: str = "personal"
    sensitivity: str = "high"
    captured_via: str = "manual_memory"
    tags: list[str] = field(default_factory=list)


@dataclass
class LocationPattern:
    category: str
    time_bucket: str
    count: int
    confidence: float
    last_seen_at: str | None = None


@dataclass
class NearbyPlaceCandidate:
    category: str
    title: str
    reason: str
    confidence: float
    scope: str = "personal"
    sensitivity: str = "high"
    latitude: float | None = None
    longitude: float | None = None
    navigation_prep: dict[str, Any] = field(default_factory=dict)
    explainability_tags: list[str] = field(default_factory=list)


class LocationProvider(Protocol):
    name: str
    mode: str

    def normalize_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def summarize(
        self,
        *,
        current_place: dict[str, Any] | None,
        recent_places: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def load_context(self, *, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
        ...


class NativeLocationAdapter(Protocol):
    name: str
    mode: str

    def inspect_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class DesktopSnapshotLocationAdapter:
    name = "desktop_snapshot_adapter_v1"
    mode = "desktop_renderer_geolocation"

    def inspect_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        observed_at = str(payload.get("observed_at") or payload.get("saved_at") or "").strip() or None
        permission_state = str(payload.get("permission_state") or payload.get("permission") or "unknown").strip().lower() or "unknown"
        privacy_mode = bool(payload.get("privacy_mode"))
        capture_failure_reason = str(payload.get("capture_failure_reason") or payload.get("last_error") or "").strip() or None
        device_context = dict(payload.get("device_context") or {}) if isinstance(payload.get("device_context"), dict) else {}
        activity_state = str(device_context.get("activity_state") or payload.get("activity_state") or "unknown").strip().lower() or "unknown"
        idle_minutes_raw = device_context.get("idle_minutes")
        try:
            idle_minutes = float(idle_minutes_raw) if idle_minutes_raw is not None else None
        except (TypeError, ValueError):
            idle_minutes = None
        active_hours = [
            int(item)
            for item in list(device_context.get("active_hours") or [])
            if str(item).strip().isdigit()
        ][:24]
        freshness = _freshness_label(observed_at)
        provider_status = str(payload.get("provider_status") or "").strip().lower()
        if not provider_status:
            if privacy_mode:
                provider_status = "privacy_mode"
            elif permission_state in {"denied", "blocked", "restricted"}:
                provider_status = "permission_denied"
            elif capture_failure_reason:
                provider_status = "capture_failed"
            else:
                provider_status = freshness
        lifecycle_stage = "fresh_snapshot"
        if privacy_mode:
            lifecycle_stage = "privacy_restricted"
        elif permission_state in {"denied", "blocked", "restricted"}:
            lifecycle_stage = "permission_denied"
        elif capture_failure_reason:
            lifecycle_stage = "capture_failed"
        elif freshness in {"stale", "expired"}:
            lifecycle_stage = "stale_snapshot"
        explanations: list[str] = []
        if privacy_mode:
            explanations.append("Gizlilik modu aktif olduğu için hassas konum ayrıntıları gizlendi.")
        if permission_state in {"denied", "blocked", "restricted"}:
            explanations.append("Cihaz konum izni verilmediği için son güvenilir snapshot kullanılıyor.")
        if capture_failure_reason:
            explanations.append(f"Son konum alma denemesi başarısız oldu: {capture_failure_reason}.")
        if freshness in {"stale", "expired"}:
            explanations.append("Konum anlık görüntüsü güncel değil; yakın öneriler ve rota yönlendirmesi daha temkinli gösteriliyor.")
        if not explanations:
            explanations.append("Cihaz konum anlık görüntüsü kullanılabilir görünüyor.")
        return {
            "provider_status": provider_status,
            "permission_state": permission_state,
            "privacy_mode": privacy_mode,
            "capture_failure_reason": capture_failure_reason,
            "freshness_label": freshness,
            "freshness_minutes": _age_minutes(observed_at),
            "route_available": not privacy_mode and permission_state not in {"denied", "blocked", "restricted"},
            "explanations": explanations,
            "lifecycle_stage": lifecycle_stage,
            "activity_state": activity_state,
            "idle_minutes": idle_minutes,
            "active_hours": active_hours,
        }


class MockLocationProvider:
    name = "mock_location_memory_v2"
    mode = "mock_memory"

    default_nearby_titles = {
        "mosque": "Yakındaki cami/mescit",
        "cafe": "Yakındaki kafe",
        "coworking": "Yakındaki çalışma alanı",
        "market": "Yakındaki market",
        "light_meal": "Yakındaki hafif yemek noktası",
        "historic_site": "Yakındaki tarihi nokta",
        "transit": "Yakındaki ulaşım bağlantısı",
    }

    def normalize_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = str(payload.get("label") or payload.get("title") or payload.get("area") or payload.get("category") or "Konum").strip()
        category = str(payload.get("category") or "unknown").strip().lower() or "unknown"
        observation = LocationObservation(
            place_id=str(payload.get("place_id") or payload.get("id") or f"{category}:{label}".lower()).strip(),
            label=label,
            category=category,
            area=str(payload.get("area") or "").strip(),
            latitude=float(payload["latitude"]) if payload.get("latitude") is not None else None,
            longitude=float(payload["longitude"]) if payload.get("longitude") is not None else None,
            accuracy_meters=float(payload["accuracy_meters"]) if payload.get("accuracy_meters") is not None else None,
            started_at=str(payload.get("started_at") or payload.get("observed_at") or "").strip() or None,
            ended_at=str(payload.get("ended_at") or "").strip() or None,
            scope=str(payload.get("scope") or "personal").strip() or "personal",
            sensitivity=str(payload.get("sensitivity") or "high").strip() or "high",
            captured_via=str(payload.get("captured_via") or payload.get("source") or "manual_memory").strip() or "manual_memory",
            tags=[str(item).strip().lower() for item in list(payload.get("tags") or []) if str(item).strip()],
        )
        return asdict(observation)

    def summarize(
        self,
        *,
        current_place: dict[str, Any] | None,
        recent_places: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        patterns = self._build_patterns(recent_places)
        nearby_candidates = self._build_nearby_candidates(
            current_place=current_place,
            patterns=patterns,
            profile=profile or {},
        )
        observed_at = str((current_place or {}).get("started_at") or (current_place or {}).get("ended_at") or "") or None
        return {
            "provider": self.name,
            "provider_mode": self.mode,
            "provider_status": "generated",
            "capture_mode": "inferred_memory",
            "current_place": current_place,
            "recent_places": recent_places[-12:],
            "frequent_patterns": patterns[:8],
            "nearby_candidates": nearby_candidates[:6],
            "time_bucket": _time_bucket((current_place or {}).get("started_at")),
            "observed_at": observed_at,
            "navigation_handoff": {
                "available": bool(nearby_candidates),
                "provider": "maps_link",
                "candidates": nearby_candidates[:4],
            },
            "location_explainability": {
                "status_reason": "Yakın öneriler son konum örüntülerinden türetildi.",
                "freshness_label": "generated",
                "permission_state": "not_applicable",
            },
        }

    def load_context(self, *, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return None

    def _build_patterns(self, recent_places: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in recent_places:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "unknown").strip().lower() or "unknown"
            time_bucket = _time_bucket(str(item.get("started_at") or item.get("ended_at") or ""))
            grouped[(category, time_bucket)].append(item)
        patterns: list[LocationPattern] = []
        max_count = max((len(items) for items in grouped.values()), default=1)
        for (category, time_bucket), items in grouped.items():
            last_seen = next(
                (
                    str(item.get("started_at") or item.get("ended_at") or "")
                    for item in sorted(items, key=lambda value: str(value.get("started_at") or value.get("ended_at") or ""), reverse=True)
                    if str(item.get("started_at") or item.get("ended_at") or "")
                ),
                None,
            )
            patterns.append(
                LocationPattern(
                    category=category,
                    time_bucket=time_bucket,
                    count=len(items),
                    confidence=round(min(0.96, 0.45 + (len(items) / max_count) * 0.45), 2),
                    last_seen_at=last_seen,
                )
            )
        patterns.sort(key=lambda item: (-item.count, -item.confidence, item.category, item.time_bucket))
        return [asdict(item) for item in patterns]

    def _build_nearby_candidates(
        self,
        *,
        current_place: dict[str, Any] | None,
        patterns: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        current_category = str((current_place or {}).get("category") or "").strip().lower()
        area_tags = {str(item).strip().lower() for item in list((current_place or {}).get("tags") or []) if str(item).strip()}
        bucket = _time_bucket((current_place or {}).get("started_at"))
        requested_nearby = [
            str(item).strip().lower()
            for item in list(profile.get("nearby_categories") or [])
            if str(item).strip()
        ]
        likely_categories = []
        if bucket == "morning":
            likely_categories.extend(["cafe", "coworking", "transit"])
        elif bucket == "midday":
            likely_categories.extend(["light_meal", "cafe", "mosque"])
        elif bucket == "evening":
            likely_categories.extend(["market", "light_meal", "historic_site"])
        else:
            likely_categories.extend(["transit", "market"])

        if current_category == "home":
            likely_categories.insert(0, "light_meal")
        elif current_category in {"office", "court", "workspace"}:
            likely_categories.insert(0, "coworking")
        elif current_category in {"transit", "station"}:
            likely_categories.insert(0, "transit")
        if "historic" in area_tags or "historical" in area_tags:
            likely_categories.insert(0, "historic_site")

        if any(token in str(profile.get("food_preferences") or "").lower() for token in ("hafif", "light", "salata", "soup", "çorba")):
            likely_categories.insert(0, "light_meal")
        if any(token in str(profile.get("assistant_notes") or "").lower() for token in ("namaz", "cami", "mescit")):
            likely_categories.insert(0, "mosque")
        if any(token in str(profile.get("maps_preference") or "").lower() for token in ("yürü", "walk", "metro", "train", "tren")):
            likely_categories.insert(0, "transit")
        likely_categories = [*requested_nearby, *likely_categories]

        pattern_counts = Counter[str]()
        for item in patterns:
            category = str(item.get("category") or "").strip().lower()
            pattern_counts[category] += int(item.get("count") or 0)

        seen: set[str] = set()
        candidates: list[NearbyPlaceCandidate] = []
        for category in likely_categories:
            if category in seen:
                continue
            seen.add(category)
            confidence = round(
                min(
                    0.92,
                    0.48
                    + pattern_counts.get(category, 0) * 0.07
                    + (0.08 if category == current_category else 0.0)
                    + (0.04 if category in requested_nearby else 0.0),
                ),
                2,
            )
            title = self.default_nearby_titles.get(category, f"Yakındaki {category}")
            explainability_tags = [bucket, current_category or "unknown"]
            if category == "light_meal" and str(profile.get("food_preferences") or "").strip():
                reason = "Zaman bandı ve hafif yemek tercihi sinyali bir araya geldi."
                explainability_tags.append("food_preference")
            elif category == "mosque":
                reason = "Zaman ve hassasiyet sinyallerine göre ibadet noktası uygun görünüyor."
                explainability_tags.append("routine_sensitivity")
            elif category == "historic_site":
                reason = "Bu bölgede tarihi ilgi alanı sinyali veya area tag bulundu."
                explainability_tags.append("historic_area")
            else:
                reason = "Mevcut zaman dilimi, son yer örüntüsü ve bağlama göre bu kategori uygun olabilir."
            maps_label = f"{title} {(current_place or {}).get('area') or (current_place or {}).get('label') or ''}".strip()
            candidates.append(
                NearbyPlaceCandidate(
                    category=category,
                    title=title,
                    reason=reason,
                    confidence=confidence,
                    navigation_prep={
                        "title": title,
                        "category": category,
                        "provider": "maps_link",
                        "maps_url": _maps_handoff_url(
                            label=maps_label,
                            latitude=(current_place or {}).get("latitude"),
                            longitude=(current_place or {}).get("longitude"),
                        ),
                        "query": maps_label,
                        "route_mode": "walking" if category in {"mosque", "market", "cafe", "light_meal"} else "transit",
                    },
                    explainability_tags=explainability_tags,
                )
            )
        return [asdict(item) for item in candidates]


class FileBackedLocationProvider:
    name = "desktop_location_snapshot_v1"
    mode = "desktop_file_snapshot"

    def __init__(
        self,
        snapshot_path: Path,
        *,
        fallback_provider: MockLocationProvider | None = None,
        adapter: NativeLocationAdapter | None = None,
    ) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.fallback_provider = fallback_provider or MockLocationProvider()
        self.adapter = adapter or DesktopSnapshotLocationAdapter()

    def normalize_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.fallback_provider.normalize_observation(payload)

    def summarize(
        self,
        *,
        current_place: dict[str, Any] | None,
        recent_places: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summary = self.fallback_provider.summarize(
            current_place=current_place,
            recent_places=recent_places,
            profile=profile,
        )
        summary["provider"] = self.name
        summary["provider_mode"] = self.mode
        return summary

    def load_context(self, *, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.snapshot_path.exists():
            return None
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        inspection = self.adapter.inspect_snapshot(payload)
        current_payload = payload.get("current_place") if isinstance(payload.get("current_place"), dict) else {}
        recent_payloads = [item for item in list(payload.get("recent_places") or []) if isinstance(item, dict)]
        nearby_categories = [str(item).strip().lower() for item in list(payload.get("nearby_categories") or []) if str(item).strip()]
        if not current_payload and not recent_payloads:
            if not payload:
                return None
            return {
                "provider": self.name,
                "provider_mode": self.mode,
                "provider_status": inspection.get("provider_status") or "unavailable",
                "capture_mode": str(payload.get("capture_mode") or "snapshot_fallback"),
                "source": str(payload.get("source") or "desktop_snapshot"),
                "observed_at": str(payload.get("observed_at") or "") or None,
                "scope": str(payload.get("scope") or "personal"),
                "sensitivity": str(payload.get("sensitivity") or "high"),
                "current_place": None,
                "recent_places": [],
                "frequent_patterns": [],
                "nearby_candidates": [],
                "navigation_handoff": {
                    "available": False,
                    "provider": "maps_link",
                    "blocked_reason": inspection.get("provider_status"),
                    "candidates": [],
                },
                "snapshot_path": str(self.snapshot_path),
                "nearby_categories": nearby_categories,
                "permission_state": inspection.get("permission_state"),
                "privacy_mode": inspection.get("privacy_mode"),
                "capture_failure_reason": inspection.get("capture_failure_reason"),
                "freshness_label": inspection.get("freshness_label"),
                "freshness_minutes": inspection.get("freshness_minutes"),
                "device_context": {
                    "activity_state": inspection.get("activity_state"),
                    "idle_minutes": inspection.get("idle_minutes"),
                    "active_hours": inspection.get("active_hours") or [],
                },
                "context_composition": {
                    "lifecycle_stage": inspection.get("lifecycle_stage"),
                    "route_available": bool(inspection.get("route_available")),
                    "has_current_place": False,
                    "nearby_candidate_count": 0,
                    "frequent_pattern_count": 0,
                },
                "location_explainability": {
                    "status_reason": " ".join(str(item) for item in list(inspection.get("explanations") or []) if str(item).strip()),
                    "freshness_label": inspection.get("freshness_label"),
                    "permission_state": inspection.get("permission_state"),
                    "fallback_reason": inspection.get("provider_status"),
                    "lifecycle_stage": inspection.get("lifecycle_stage"),
                },
            }
        current_place = self.normalize_observation(
            {
                **current_payload,
                "scope": str(current_payload.get("scope") or payload.get("scope") or "personal"),
                "sensitivity": str(current_payload.get("sensitivity") or payload.get("sensitivity") or "high"),
                "observed_at": str(current_payload.get("observed_at") or payload.get("observed_at") or ""),
            }
        ) if current_payload else None
        recent_places = [
            self.normalize_observation(
                {
                    **item,
                    "scope": str(item.get("scope") or payload.get("scope") or "personal"),
                    "sensitivity": str(item.get("sensitivity") or payload.get("sensitivity") or "high"),
                }
            )
            for item in recent_payloads
        ]
        if current_place:
            recent_places = [current_place, *recent_places]
        summary = self.summarize(current_place=current_place, recent_places=recent_places[:12], profile=profile or {})
        summary["provider"] = self.name
        summary["provider_mode"] = self.mode
        summary["provider_status"] = inspection.get("provider_status") or self._provider_status(payload, current_place)
        summary["capture_mode"] = str(payload.get("capture_mode") or ("device_capture" if "device_capture" in list((current_place or {}).get("tags") or []) else "snapshot_fallback"))
        summary["source"] = str(payload.get("source") or "desktop_snapshot")
        summary["observed_at"] = str(payload.get("observed_at") or summary.get("observed_at") or "") or None
        summary["scope"] = str(payload.get("scope") or (current_place or {}).get("scope") or "personal")
        summary["sensitivity"] = str(payload.get("sensitivity") or (current_place or {}).get("sensitivity") or "high")
        summary["snapshot_path"] = str(self.snapshot_path)
        summary["nearby_categories"] = nearby_categories
        summary["permission_state"] = inspection.get("permission_state")
        summary["privacy_mode"] = inspection.get("privacy_mode")
        summary["capture_failure_reason"] = inspection.get("capture_failure_reason")
        summary["freshness_label"] = inspection.get("freshness_label")
        summary["freshness_minutes"] = inspection.get("freshness_minutes")
        summary["device_context"] = {
            "activity_state": inspection.get("activity_state"),
            "idle_minutes": inspection.get("idle_minutes"),
            "active_hours": inspection.get("active_hours") or [],
        }
        if not bool(inspection.get("route_available")):
            summary["navigation_handoff"] = {
                **dict(summary.get("navigation_handoff") or {}),
                "available": False,
                "blocked_reason": inspection.get("provider_status"),
            }
        adjusted_candidates: list[dict[str, Any]] = []
        for candidate in list(summary.get("nearby_candidates") or []):
            item = dict(candidate)
            confidence = float(item.get("confidence") or 0.0)
            if summary["provider_status"] in {"stale", "expired", "capture_failed"}:
                confidence = max(0.2, confidence - 0.12)
            if bool(inspection.get("privacy_mode")):
                confidence = max(0.2, confidence - 0.08)
            item["confidence"] = round(confidence, 2)
            item["freshness_label"] = inspection.get("freshness_label")
            reason = str(item.get("reason") or "").strip()
            if summary["provider_status"] in {"stale", "expired"}:
                reason = f"{reason} Snapshot taze olmadığı için öneri temkinli tutuldu.".strip()
            adjusted_candidates.append(item)
        summary["nearby_candidates"] = adjusted_candidates
        summary["location_explainability"] = {
            "status_reason": " ".join(str(item) for item in list(inspection.get("explanations") or []) if str(item).strip()),
            "freshness_label": inspection.get("freshness_label"),
            "permission_state": inspection.get("permission_state"),
            "fallback_reason": summary["provider_status"] if summary["provider_status"] not in {"fresh", "generated"} else None,
            "route_available": bool(inspection.get("route_available")),
            "lifecycle_stage": inspection.get("lifecycle_stage"),
        }
        summary["context_composition"] = {
            "time_bucket": summary.get("time_bucket"),
            "lifecycle_stage": inspection.get("lifecycle_stage"),
            "route_available": bool(inspection.get("route_available")),
            "has_current_place": bool(current_place),
            "nearby_candidate_count": len(list(summary.get("nearby_candidates") or [])),
            "frequent_pattern_count": len(list(summary.get("frequent_patterns") or [])),
            "activity_state": inspection.get("activity_state"),
        }
        return summary

    @staticmethod
    def _provider_status(payload: dict[str, Any], current_place: dict[str, Any] | None) -> str:
        observed_at = _iso_to_datetime(str(payload.get("observed_at") or (current_place or {}).get("started_at") or ""))
        if not observed_at:
            return "unknown"
        age_minutes = max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds() / 60.0)
        if age_minutes <= 30:
            return "fresh"
        if age_minutes <= 180:
            return "stale"
        return "expired"
