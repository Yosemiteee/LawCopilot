from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any

from .persona_text import ASSISTANT_DIRECTION_MARKERS, clean_persona_text, normalize_persona_text


DEFAULT_ASSISTANT_ROLE_SUMMARY = "Kullanıcının istediğine göre şekillenen çekirdek asistan"
DEFAULT_ASSISTANT_TONE = "Net ve profesyonel"

DEFAULT_BEHAVIOR_CONTRACT: dict[str, str] = {
    "initiative_level": "balanced",
    "planning_depth": "structured",
    "accountability_style": "supportive",
    "follow_up_style": "check_in",
    "explanation_style": "balanced",
}


ASSISTANT_FORM_CATALOG: dict[str, dict[str, Any]] = {
    "life_coach": {
        "slug": "life_coach",
        "title": "Yaşam koçu",
        "summary": "Hedef, alışkanlık, check-in ve kişisel düzen takibi için daha takipçi çalışır.",
        "category": "personal",
        "scopes": ["personal"],
        "capabilities": ["goal_tracking", "habit_checkins", "accountability", "weekly_review"],
        "ui_surfaces": ["coaching_dashboard", "progress_tracking", "proactive_triggers"],
        "aliases": (
            "yasam kocu",
            "yaşam koçu",
            "yasam koc",
            "yaşam koç",
            "hayat kocu",
            "hayat koçu",
            "hayat koc",
            "hayat koç",
            "koc ol",
            "koç ol",
            "yasam koçu",
        ),
        "supports_coaching": True,
    },
    "legal_copilot": {
        "slug": "legal_copilot",
        "title": "Hukuk asistanı",
        "summary": "Dosya, belge, tarih, taslak ve müvekkil işlerini merkez alan profesyonel copilot gibi davranır.",
        "category": "professional",
        "scopes": ["professional", "project"],
        "capabilities": ["legal_reasoning", "document_tracking", "deadline_follow_up", "draft_support"],
        "ui_surfaces": ["matter_context", "decision_timeline", "proactive_triggers"],
        "aliases": (
            "hukuk asistani",
            "hukuk asistanı",
            "avukat asistani",
            "avukat asistanı",
            "legal assistant",
            "legal copilot",
        ),
        "supports_coaching": False,
    },
    "personal_ops": {
        "slug": "personal_ops",
        "title": "Kişisel organizasyon asistanı",
        "summary": "Takvim, görev, mesaj ve günlük düzeni toplar; takip ve önceliklendirme yapar.",
        "category": "personal",
        "scopes": ["personal", "global"],
        "capabilities": ["daily_planning", "task_follow_up", "calendar_load_management", "reminder_support"],
        "ui_surfaces": ["agenda", "task_cards", "proactive_triggers"],
        "aliases": (
            "kisisel asistan",
            "kişisel asistan",
            "organizasyon asistani",
            "organizasyon asistanı",
            "planlayici asistan",
            "planlayıcı asistan",
        ),
        "supports_coaching": False,
    },
    "device_companion": {
        "slug": "device_companion",
        "title": "Telefon ve cihaz asistanı",
        "summary": "Mesajlar, bildirimler, yakın bağlam ve cihaz akışları üstünde daha aktif çalışır.",
        "category": "device",
        "scopes": ["personal"],
        "capabilities": ["message_triage", "notification_guidance", "location_handoffs", "device_routines"],
        "ui_surfaces": ["connector_status", "location_context", "proactive_triggers"],
        "aliases": (
            "telefon asistani",
            "telefon asistanı",
            "cihaz asistani",
            "cihaz asistanı",
            "telefonumu yonet",
            "telefonumu yönet",
        ),
        "supports_coaching": False,
    },
    "study_mentor": {
        "slug": "study_mentor",
        "title": "Çalışma ve öğrenme mentoru",
        "summary": "Öğrenme planı, okuma hedefleri ve çalışma ritmini takip eder.",
        "category": "learning",
        "scopes": ["personal"],
        "capabilities": ["study_planning", "reading_progress", "focus_support", "review_cycles"],
        "ui_surfaces": ["coaching_dashboard", "progress_tracking"],
        "aliases": (
            "ders koçu",
            "ders kocu",
            "ogrenme mentoru",
            "öğrenme mentoru",
            "calisma koçu",
            "çalışma koçu",
            "study coach",
        ),
        "supports_coaching": True,
    },
    "travel_planner": {
        "slug": "travel_planner",
        "title": "Seyahat planlayıcısı",
        "summary": "Rota, konaklama, ulaşım ve yakın bağlam önerilerini öne alır.",
        "category": "travel",
        "scopes": ["personal", "global"],
        "capabilities": ["route_planning", "travel_preference_support", "nearby_recommendations"],
        "ui_surfaces": ["location_context", "travel_cards", "proactive_triggers"],
        "aliases": (
            "seyahat planlayici",
            "seyahat planlayıcı",
            "travel planner",
            "gezi asistani",
            "gezi asistanı",
        ),
        "supports_coaching": False,
    },
    "customer_support": {
        "slug": "customer_support",
        "title": "Müşteri destek asistanı",
        "summary": "WhatsApp, Instagram, web sitesi ve sipariş kanallarından gelen müşteri sorularını toparlar; güven veren cevap taslakları üretir.",
        "category": "business",
        "scopes": ["workspace", "project", "global"],
        "capabilities": ["omnichannel_inbox", "order_status_support", "draft_support", "customer_tone_control"],
        "ui_surfaces": ["customer_inbox", "decision_timeline", "draft_preview", "connector_status"],
        "aliases": (
            "musteri destek",
            "müşteri destek",
            "musteri temsilcisi",
            "müşteri temsilcisi",
            "satis temsilcisi",
            "satış temsilcisi",
            "customer support",
            "support agent",
        ),
        "supports_coaching": False,
    },
    "commerce_ops": {
        "slug": "commerce_ops",
        "title": "Mağaza ve satış asistanı",
        "summary": "Ürün kataloğu, stok, sipariş ve sosyal medya yazışmalarını birlikte yönetir.",
        "category": "business",
        "scopes": ["workspace", "project", "global"],
        "capabilities": [
            "omnichannel_inbox",
            "catalog_grounding",
            "inventory_lookup",
            "order_status_support",
            "product_recommendation",
            "draft_support",
        ],
        "ui_surfaces": ["customer_inbox", "catalog_panel", "connector_status", "draft_preview", "decision_timeline"],
        "aliases": (
            "magaza asistani",
            "mağaza asistanı",
            "e ticaret asistani",
            "e-ticaret asistanı",
            "satis asistani",
            "satış asistanı",
            "commerce assistant",
            "store assistant",
        ),
        "supports_coaching": False,
    },
}

ASSISTANT_CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "goal_tracking": {
        "slug": "goal_tracking",
        "title": "Hedef takibi",
        "summary": "Hedef tanımlar, ilerlemeyi izler ve check-in önerileri üretir.",
        "category": "coaching",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["coaching_dashboard", "progress_tracking"],
    },
    "habit_checkins": {
        "slug": "habit_checkins",
        "title": "Alışkanlık check-in",
        "summary": "Tekrarlayan rutinler için takip ve geri bildirim akışı kurar.",
        "category": "coaching",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["coaching_dashboard", "proactive_triggers"],
    },
    "accountability": {
        "slug": "accountability",
        "title": "Hesap verilebilirlik",
        "summary": "Kullanıcı isterse daha sıkı takip ve ilerleme hatırlatması yapar.",
        "category": "coaching",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["coaching_dashboard", "progress_tracking"],
    },
    "daily_planning": {
        "slug": "daily_planning",
        "title": "Günlük planlama",
        "summary": "Günlük yük, görev ve takvimi toparlayıp plan önerir.",
        "category": "personal_ops",
        "suggested_scopes": ["personal", "global"],
        "implies_surfaces": ["agenda", "task_cards"],
    },
    "task_follow_up": {
        "slug": "task_follow_up",
        "title": "Görev takibi",
        "summary": "Açık işlerin durumunu izler ve gecikmeleri işaretler.",
        "category": "personal_ops",
        "suggested_scopes": ["personal", "workspace", "project"],
        "implies_surfaces": ["task_cards", "proactive_triggers"],
    },
    "calendar_load_management": {
        "slug": "calendar_load_management",
        "title": "Takvim yükü yönetimi",
        "summary": "Yoğun günleri algılar ve hafifletme önerileri üretir.",
        "category": "personal_ops",
        "suggested_scopes": ["personal", "workspace"],
        "implies_surfaces": ["agenda", "proactive_triggers"],
    },
    "document_tracking": {
        "slug": "document_tracking",
        "title": "Belge takibi",
        "summary": "Belge, dosya ve kaynak takibini sistematik hale getirir.",
        "category": "professional",
        "suggested_scopes": ["workspace", "professional", "project"],
        "implies_surfaces": ["matter_context", "decision_timeline"],
    },
    "draft_support": {
        "slug": "draft_support",
        "title": "Taslak desteği",
        "summary": "Mail, mesaj ve belge taslaklarını hazırlar ve preview akışına taşır.",
        "category": "communication",
        "suggested_scopes": ["personal", "workspace", "project"],
        "implies_surfaces": ["draft_preview", "decision_timeline"],
    },
    "legal_reasoning": {
        "slug": "legal_reasoning",
        "title": "Hukuki çalışma desteği",
        "summary": "Hukuki bağlamı, dayanakları ve dosya ilişkilerini öne alır.",
        "category": "professional",
        "suggested_scopes": ["professional", "project"],
        "implies_surfaces": ["matter_context", "decision_timeline"],
    },
    "message_triage": {
        "slug": "message_triage",
        "title": "Mesaj triyajı",
        "summary": "Mesaj ve bildirim akışını filtreleyip önceliklendirir.",
        "category": "device",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["connector_status", "proactive_triggers"],
    },
    "notification_guidance": {
        "slug": "notification_guidance",
        "title": "Bildirim rehberliği",
        "summary": "Hangi bildirimlerin önemli olduğuna dair akıllı filtreler uygular.",
        "category": "device",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["connector_status", "proactive_triggers"],
    },
    "device_routines": {
        "slug": "device_routines",
        "title": "Cihaz rutinleri",
        "summary": "Cihaz ve günlük kullanım alışkanlıklarını izleyip destekler.",
        "category": "device",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["connector_status", "location_context"],
    },
    "study_planning": {
        "slug": "study_planning",
        "title": "Çalışma planı",
        "summary": "Okuma, çalışma ve öğrenme planını yapılandırır.",
        "category": "learning",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["coaching_dashboard", "progress_tracking"],
    },
    "reading_progress": {
        "slug": "reading_progress",
        "title": "Okuma ilerlemesi",
        "summary": "Kitap veya öğrenme hedeflerinde ilerlemeyi izler.",
        "category": "learning",
        "suggested_scopes": ["personal"],
        "implies_surfaces": ["coaching_dashboard", "progress_tracking"],
    },
    "review_cycles": {
        "slug": "review_cycles",
        "title": "Review döngüleri",
        "summary": "Belirli aralıklarla gözden geçirme ve pekiştirme önerir.",
        "category": "learning",
        "suggested_scopes": ["personal", "workspace"],
        "implies_surfaces": ["progress_tracking", "proactive_triggers"],
    },
    "route_planning": {
        "slug": "route_planning",
        "title": "Rota planlama",
        "summary": "Yer, zaman ve tercih bağlamına göre rota/handoff önerir.",
        "category": "travel",
        "suggested_scopes": ["personal", "global"],
        "implies_surfaces": ["location_context", "travel_cards"],
    },
    "nearby_recommendations": {
        "slug": "nearby_recommendations",
        "title": "Yakındaki öneriler",
        "summary": "Yakın bağlama göre yer, rota veya mekan önerisi hazırlar.",
        "category": "travel",
        "suggested_scopes": ["personal", "global"],
        "implies_surfaces": ["location_context", "proactive_triggers"],
    },
    "custom_guidance": {
        "slug": "custom_guidance",
        "title": "Özel rehberlik",
        "summary": "Kullanıcının tarif ettiği özgün asistan formunu destekler.",
        "category": "custom",
        "suggested_scopes": ["personal", "global"],
        "implies_surfaces": ["assistant_core"],
    },
    "omnichannel_inbox": {
        "slug": "omnichannel_inbox",
        "title": "Çok kanallı müşteri kutusu",
        "summary": "WhatsApp, Instagram, web sitesi ve benzeri müşteri temas kanallarını birlikte ele alır.",
        "category": "business",
        "suggested_scopes": ["workspace", "project", "global"],
        "implies_surfaces": ["customer_inbox", "connector_status"],
    },
    "catalog_grounding": {
        "slug": "catalog_grounding",
        "title": "Kataloga dayalı cevaplama",
        "summary": "Yanıtları ürün linki, görsel, web sitesi ve katalog bilgisinden dayanaklı kurar.",
        "category": "business",
        "suggested_scopes": ["workspace", "project"],
        "implies_surfaces": ["catalog_panel", "draft_preview"],
    },
    "inventory_lookup": {
        "slug": "inventory_lookup",
        "title": "Stok kontrolü",
        "summary": "Stok, varyant ve ürün uygunluğu bilgisini cevap üretmeden önce kontrol etmeyi öne alır.",
        "category": "business",
        "suggested_scopes": ["workspace", "project"],
        "implies_surfaces": ["catalog_panel", "customer_inbox"],
    },
    "order_status_support": {
        "slug": "order_status_support",
        "title": "Sipariş durumu desteği",
        "summary": "Sipariş, kargo ve teslimat sorularını uygun kaynaklara dayalı yanıtlar.",
        "category": "business",
        "suggested_scopes": ["workspace", "project"],
        "implies_surfaces": ["customer_inbox", "decision_timeline"],
    },
    "product_recommendation": {
        "slug": "product_recommendation",
        "title": "Ürün önerisi",
        "summary": "Müşterinin ihtiyacına göre ürün, varyant ve alternatif önerisi hazırlar.",
        "category": "business",
        "suggested_scopes": ["workspace", "project", "global"],
        "implies_surfaces": ["catalog_panel", "draft_preview"],
    },
    "customer_tone_control": {
        "slug": "customer_tone_control",
        "title": "Müşteri iletişim tonu",
        "summary": "Markaya uygun, kısa ve güven veren müşteri iletişim tonu uygular.",
        "category": "business",
        "suggested_scopes": ["workspace", "project"],
        "implies_surfaces": ["draft_preview", "decision_timeline"],
    },
}

ASSISTANT_SURFACE_CATALOG: dict[str, dict[str, Any]] = {
    "assistant_core": {
        "slug": "assistant_core",
        "title": "Asistan çekirdeği",
        "summary": "Aktif formlar, davranış kontratı ve evrim geçmişini gösterir.",
        "category": "core",
    },
    "coaching_dashboard": {
        "slug": "coaching_dashboard",
        "title": "Koçluk paneli",
        "summary": "Hedef, habit, progress ve check-in takibi gösterir.",
        "category": "coaching",
    },
    "progress_tracking": {
        "slug": "progress_tracking",
        "title": "İlerleme takibi",
        "summary": "Hedefe kalan mesafe ve son güncellemeleri görünür kılar.",
        "category": "coaching",
    },
    "proactive_triggers": {
        "slug": "proactive_triggers",
        "title": "Proaktif öneriler",
        "summary": "Bağlama göre çıkan zamanlı önerileri görünür kılar.",
        "category": "core",
    },
    "agenda": {
        "slug": "agenda",
        "title": "Ajanda",
        "summary": "Takvim ve günün planını öne çıkarır.",
        "category": "planning",
    },
    "task_cards": {
        "slug": "task_cards",
        "title": "Görev kartları",
        "summary": "Açık işler ve takip gerektiren maddeleri listeler.",
        "category": "planning",
    },
    "matter_context": {
        "slug": "matter_context",
        "title": "Dosya bağlamı",
        "summary": "Profesyonel veya proje bağlamını yoğunlaştırır.",
        "category": "professional",
    },
    "decision_timeline": {
        "slug": "decision_timeline",
        "title": "Karar zaman çizgisi",
        "summary": "Öneri ve aksiyon geçmişini görünür kılar.",
        "category": "core",
    },
    "connector_status": {
        "slug": "connector_status",
        "title": "Bağlayıcı durumu",
        "summary": "Servis sync ve sağlık görünümünü gösterir.",
        "category": "device",
    },
    "location_context": {
        "slug": "location_context",
        "title": "Konum bağlamı",
        "summary": "Yakın yerler ve konum sinyallerini gösterir.",
        "category": "location",
    },
    "travel_cards": {
        "slug": "travel_cards",
        "title": "Seyahat kartları",
        "summary": "Rota, mekan ve seyahat önerilerini görünür kılar.",
        "category": "travel",
    },
    "draft_preview": {
        "slug": "draft_preview",
        "title": "Taslak önizleme",
        "summary": "Dış iletişim aksiyonlarını preview akışına taşır.",
        "category": "communication",
    },
    "customer_inbox": {
        "slug": "customer_inbox",
        "title": "Müşteri kutusu",
        "summary": "Çok kanallı müşteri mesajlarını ve öncelikli talepleri görünür kılar.",
        "category": "business",
    },
    "catalog_panel": {
        "slug": "catalog_panel",
        "title": "Katalog ve stok paneli",
        "summary": "Ürün linki, varyant, stok ve alternatif cevap dayanaklarını gösterir.",
        "category": "business",
    },
}

ASSISTANT_FORM_BLUEPRINT_HINTS: dict[str, tuple[str, ...]] = {
    "goal_tracking": ("hedef", "hedefim", "hedeflerim", "takip et", "plan tut", "ilerleme"),
    "habit_checkins": ("alışkanlık", "rutin", "günlük düzen", "her gün", "check-in"),
    "accountability": ("hesap sor", "disiplin", "takip et", "sıkı takip", "beni dürt", "beni durt"),
    "daily_planning": ("günlük plan", "günümü planla", "ajanda", "gün planı", "organize et"),
    "task_follow_up": ("görev", "todo", "yapılacak", "deadline", "iş takibi", "takip et"),
    "calendar_load_management": ("takvim", "yoğunluk", "program", "ajanda yükü"),
    "document_tracking": ("belge", "doküman", "dosya", "evrak", "klasör"),
    "draft_support": ("taslak", "mail yaz", "mesaj yaz", "cevap hazırla", "yanıt hazırla"),
    "legal_reasoning": ("hukuk", "avukat", "dava", "müvekkil", "sözleşme", "legal"),
    "message_triage": ("mesaj", "wp", "whatsapp", "telegram", "gelen kutusu"),
    "notification_guidance": ("bildirim", "uyarı", "önemli mesaj"),
    "device_routines": ("telefon", "cihaz", "mobil", "uygulama", "device"),
    "study_planning": ("çalışma planı", "ders", "öğrenme", "study", "sınav"),
    "reading_progress": ("kitap", "okuma", "sayfa", "reading"),
    "review_cycles": ("tekrar", "review", "gözden geçir", "pekiştir"),
    "route_planning": ("rota", "yol", "navigasyon", "ulaşım", "harita"),
    "nearby_recommendations": ("yakınımda", "yakında", "çevrede", "mekan öner", "yer öner"),
    "omnichannel_inbox": ("müşteri mesajı", "instagram dm", "instagram", "whatsapp", "wp", "çok kanallı", "mesaj kutusu"),
    "catalog_grounding": ("ürün linki", "ürün görseli", "web sitesi", "siteyi tara", "katalog", "ürün sayfası"),
    "inventory_lookup": ("stok", "stok durumu", "varyant", "beden", "renk kaldı mı", "envanter"),
    "order_status_support": ("sipariş", "kargo", "teslimat", "sipariş durumu", "order status"),
    "product_recommendation": ("ürün öner", "alternatif ürün", "benzeri var mı", "müşteriye öner", "ürün tavsiye"),
    "customer_tone_control": ("müşteriye böyle cevap ver", "müşteri dili", "satış dili", "marka tonu"),
    "custom_guidance": ("özel", "bana göre", "kişiselleştir", "istediğim gibi"),
}

ASSISTANT_BEHAVIOR_HINTS: dict[str, dict[str, str]] = {
    "high": {"initiative_level": "high", "follow_up_style": "persistent"},
    "low": {"initiative_level": "low", "follow_up_style": "on_request"},
    "firm": {"accountability_style": "firm"},
    "gentle": {"accountability_style": "gentle"},
    "deep": {"planning_depth": "deep", "explanation_style": "detailed"},
    "light": {"planning_depth": "light", "explanation_style": "concise"},
}

_HIGH_INITIATIVE_HINTS = ("çok proaktif", "yüksek proaktif", "sıkı takip", "takip et", "beni dürt", "beni durt", "hesap sor", "ısrarcı", "inatçı takip")
_LOW_INITIATIVE_HINTS = ("fazla proaktif olma", "beni bunaltma", "az takip", "gerektikçe", "sadece isteyince")
_FIRM_HINTS = ("disiplin", "disiplinli", "sert", "kararlı", "sıkı", "hesap sor")
_GENTLE_HINTS = ("nazik", "yumuşak", "kibar", "sert olma")
_DEEP_HINTS = ("detaylı", "derin", "ince", "mikro plan", "ayrıntılı")
_LIGHT_HINTS = ("hafif", "kısa", "özet", "minimal", "sade")

ASSISTANT_TRANSFORMATION_EXAMPLES: list[dict[str, str]] = [
    {
        "prompt": "Beni kitap okuma koçuna çevir. Her akşam okuma hedefimi takip et.",
        "title": "Kitap okuma koçu",
        "focus": "okuma hedefleri ve progress takibi",
    },
    {
        "prompt": "Telefonumu yöneten kişisel asistan gibi davran. Mesajları ve bildirimleri önceliklendir.",
        "title": "Telefon ve cihaz asistanı",
        "focus": "mesaj triyajı ve cihaz rutinleri",
    },
    {
        "prompt": "Bana hukuk çalışma asistanı ol. Dosyaları, taslakları ve tarihleri öne çıkar.",
        "title": "Hukuk asistanı",
        "focus": "dosya, belge ve taslak takibi",
    },
    {
        "prompt": "Beni bebek giyim mağazası için satış temsilcisine çevir. WhatsApp, Instagram ve web sitesinden gelen soruları ürün linki, stok ve varyanta bakarak cevapla.",
        "title": "Mağaza ve satış asistanı",
        "focus": "müşteri mesajları, stok kontrolü ve satış cevapları",
    },
]


_ACTIVATION_MARKERS = (
    "ol",
    "olsun",
    "olmani istiyorum",
    "olmanı istiyorum",
    "gibi davran",
    "moduna gec",
    "moduna geç",
    "donus",
    "dönüş",
    "donustur",
    "dönüştür",
    "cevir",
    "çevir",
    "evril",
    "forma sok",
    "destek ol",
)
_DEACTIVATION_MARKERS = (
    "olma",
    "kapat",
    "cikar",
    "çıkar",
    "devre disi",
    "devre dışı",
    "istemiyorum",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    normalized = normalize_persona_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:64] or "custom-form"


def _fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def assistant_form_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in ASSISTANT_FORM_CATALOG.values()]


def assistant_capability_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in ASSISTANT_CAPABILITY_CATALOG.values()]


def assistant_surface_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in ASSISTANT_SURFACE_CATALOG.values()]


def assistant_transformation_examples() -> list[dict[str, str]]:
    return [dict(item) for item in ASSISTANT_TRANSFORMATION_EXAMPLES]


def _active_capability_contracts(active_forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for form in active_forms:
        for slug in list(form.get("capabilities") or []):
            normalized = str(slug or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            spec = dict(ASSISTANT_CAPABILITY_CATALOG.get(normalized) or {})
            implied_surfaces = [str(item).strip() for item in list(spec.get("implies_surfaces") or []) if str(item).strip()]
            summary = str(spec.get("summary") or normalized.replace("_", " ")).strip()
            contracts.append(
                {
                    "slug": normalized,
                    "title": str(spec.get("title") or normalized.replace("_", " ").title()).strip(),
                    "summary": summary,
                    "category": str(spec.get("category") or "custom"),
                    "suggested_scopes": [str(item).strip() for item in list(spec.get("suggested_scopes") or []) if str(item).strip()],
                    "implies_surfaces": implied_surfaces,
                    "operating_hint": _capability_operating_hint(normalized, summary),
                }
            )
    return contracts


def _active_surface_contracts(active_forms: list[dict[str, Any]], capability_contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    raw_slugs = sorted(
        {
            str(surface).strip()
            for form in active_forms
            for surface in list(form.get("ui_surfaces") or [])
            if str(surface).strip()
        }
        | {
            str(surface).strip()
            for contract in capability_contracts
            for surface in list(contract.get("implies_surfaces") or [])
            if str(surface).strip()
        }
    )
    for slug in raw_slugs:
        if slug in seen:
            continue
        seen.add(slug)
        spec = dict(ASSISTANT_SURFACE_CATALOG.get(slug) or {})
        items.append(
            {
                "slug": slug,
                "title": str(spec.get("title") or slug.replace("_", " ").title()).strip(),
                "summary": str(spec.get("summary") or "").strip(),
                "category": str(spec.get("category") or "custom"),
            }
        )
    return items


def _capability_operating_hint(slug: str, summary: str) -> str:
    if slug in {"goal_tracking", "habit_checkins", "accountability", "study_planning", "reading_progress"}:
        return "Bu yetenek açık olduğunda sistem hedef, ilerleme ve check-in dilini daha aktif kullanır."
    if slug in {"task_follow_up", "daily_planning", "calendar_load_management"}:
        return "Bu yetenek açık olduğunda sistem görev ve ajanda yükünü daha görünür biçimde düzenler."
    if slug in {"message_triage", "notification_guidance", "device_routines"}:
        return "Bu yetenek açık olduğunda mesaj, bildirim ve cihaz akışları daha öncelikli işlenir."
    if slug in {"legal_reasoning", "document_tracking", "draft_support"}:
        return "Bu yetenek açık olduğunda profesyonel bağlam ve taslak hazırlığı daha belirgin hale gelir."
    if slug == "omnichannel_inbox":
        return "Bu yetenek açık olduğunda WhatsApp, Instagram, web sitesi ve diğer müşteri kanalları tek akış gibi ele alınır."
    if slug == "catalog_grounding":
        return "Bu yetenek açık olduğunda ürün görseli, linki ve web katalog bilgisi görülmeden net ürün cevabı verilmez."
    if slug == "inventory_lookup":
        return "Bu yetenek açık olduğunda cevaptan önce stok, renk, beden ve varyant uygunluğu doğrulanmaya çalışılır."
    if slug == "order_status_support":
        return "Bu yetenek açık olduğunda sipariş ve kargo soruları bağlı sipariş kaynağına dayandırılır; belirsizlik varsa açıkça söylenir."
    if slug == "product_recommendation":
        return "Bu yetenek açık olduğunda müşterinin isteğine göre alternatif ürün ve varyant önerileri hazırlanır."
    if slug == "customer_tone_control":
        return "Bu yetenek açık olduğunda müşteri cevapları kısa, güven veren ve marka tonuna uygun tutulur."
    if slug in {"route_planning", "nearby_recommendations"}:
        return "Bu yetenek açık olduğunda konum, rota ve yakın çevre sinyalleri daha çok kullanılır."
    return f"Bu yetenek açık: {summary}"


def _behavior_style_summary(contract: dict[str, str]) -> str:
    return ", ".join(
        [
            f"proaktiflik={contract.get('initiative_level')}",
            f"takip={contract.get('follow_up_style')}",
            f"plan={contract.get('planning_depth')}",
            f"hesap verilebilirlik={contract.get('accountability_style')}",
            f"açıklama={contract.get('explanation_style')}",
        ]
    )


def _assistant_setup_actions(
    active_forms: list[dict[str, Any]],
    capability_contracts: list[dict[str, Any]],
    surface_contracts: list[dict[str, Any]],
    *,
    coaching_goal_count: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not active_forms:
        actions.append(
            {
                "id": "choose-first-form",
                "title": "İlk formunu seç",
                "why": "Çekirdek şu an genel modda. Belirli bir role geçtiğinde öneriler daha isabetli olur.",
                "surface": "assistant_core",
                "priority": "high",
            }
        )
    if any(item.get("slug") in {"goal_tracking", "habit_checkins", "study_planning", "reading_progress"} for item in capability_contracts) and coaching_goal_count <= 0:
        actions.append(
            {
                "id": "create-first-goal",
                "title": "İlk hedefi oluştur",
                "why": "Koçluk ve ilerleme yetenekleri hedef olmadan tam çalışmaz.",
                "surface": "coaching_dashboard",
                "priority": "high",
            }
        )
    if any(item.get("slug") == "message_triage" for item in capability_contracts):
        actions.append(
            {
                "id": "connect-messaging",
                "title": "Mesaj kaynaklarını bağla",
                "why": "Mesaj triyajı yeteneği, bağlı mesaj kaynakları olduğunda daha faydalı olur.",
                "surface": "connector_status",
                "priority": "medium",
            }
        )
    if any(item.get("slug") == "omnichannel_inbox" for item in capability_contracts):
        actions.append(
            {
                "id": "connect-customer-channels",
                "title": "Müşteri kanallarını bağla",
                "why": "WhatsApp, Instagram, e-posta veya web formları bağlı olduğunda müşteri akışı gerçekten çalışır.",
                "surface": "customer_inbox",
                "priority": "high",
            }
        )
    if any(item.get("slug") in {"catalog_grounding", "inventory_lookup", "product_recommendation"} for item in capability_contracts):
        actions.append(
            {
                "id": "connect-catalog-and-stock",
                "title": "Katalog ve stok kaynağını bağla",
                "why": "Ürün, varyant ve stok dayanağı olmadan satış cevapları güvenilir kalmaz.",
                "surface": "catalog_panel",
                "priority": "high",
            }
        )
    if any(item.get("slug") == "order_status_support" for item in capability_contracts):
        actions.append(
            {
                "id": "connect-order-source",
                "title": "Sipariş kaynağını doğrula",
                "why": "Sipariş ve kargo sorularını cevaplamak için web sitesi veya sipariş sistemiyle güncel bağ kurmak gerekir.",
                "surface": "customer_inbox",
                "priority": "medium",
            }
        )
    if any(item.get("slug") in {"route_planning", "nearby_recommendations"} for item in capability_contracts):
        actions.append(
            {
                "id": "refresh-location",
                "title": "Konum bağlamını yenile",
                "why": "Konum odaklı form, güncel yer sinyalleriyle daha doğru çalışır.",
                "surface": "location_context",
                "priority": "medium",
            }
        )
    if any(item.get("slug") == "document_tracking" for item in capability_contracts):
        actions.append(
            {
                "id": "connect-workspace",
                "title": "Belge/workspace bağlamını doğrula",
                "why": "Belge takibi formu, kaynak klasörü ve matter bağlamıyla güçlenir.",
                "surface": "matter_context",
                "priority": "medium",
            }
        )
    if not surface_contracts:
        actions.append(
            {
                "id": "enable-surfaces",
                "title": "İlk yüzeyi aç",
                "why": "Seçili forma uygun görünüm açıldığında asistanın davranışı daha şeffaf olur.",
                "surface": "assistant_core",
                "priority": "low",
            }
        )
    return actions[:6]


def _matches_any(normalized: str, tokens: tuple[str, ...] | list[str]) -> bool:
    return any(normalize_persona_text(token) in normalized for token in tokens if str(token).strip())


def _blueprint_behavior_patch(normalized: str) -> dict[str, str]:
    patch: dict[str, str] = {}
    if _matches_any(normalized, _HIGH_INITIATIVE_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["high"])
    if _matches_any(normalized, _LOW_INITIATIVE_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["low"])
    if _matches_any(normalized, _GENTLE_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["gentle"])
    if _matches_any(normalized, _FIRM_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["firm"])
    if _matches_any(normalized, _DEEP_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["deep"])
    if _matches_any(normalized, _LIGHT_HINTS):
        patch.update(ASSISTANT_BEHAVIOR_HINTS["light"])
    return patch


def _extract_blueprint_title(raw_text: str, normalized: str, matched_forms: list[dict[str, Any]]) -> str:
    if matched_forms:
        return str(matched_forms[0].get("title") or "").strip()
    first_sentence = re.split(r"[.!?\n]", raw_text, maxsplit=1)[0]
    quoted = re.search(r"“([^”]{3,80})”|\"([^\"]{3,80})\"", raw_text)
    if quoted:
        return clean_persona_text(next(part for part in quoted.groups() if part), limit=80)
    cleaned = clean_persona_text(first_sentence, limit=120)
    for marker in ("çevir", "cevir", "olsun", "ol", "davran", "dönüştür", "donustur"):
        cleaned = re.sub(rf"\b{marker}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(sen|beni|bana|benim|asistanı|asistani|assistant|artık|artik|olarak|gibi|bir|tam|moduna|geç|gec|olmasını|istiyorum)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(koçuna|kocuna)\b", "koçu", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(asistanına|asistanina)\b", "asistanı", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(mentoruna)\b", "mentoru", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    if not cleaned:
        return "Özel asistan formu"
    tokens = cleaned.split()
    if len(tokens) > 6:
        cleaned = " ".join(tokens[:6])
    return clean_persona_text(cleaned, limit=80).title() or "Özel asistan formu"


def suggest_assistant_form_blueprint(description: str, runtime_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_text = str(description or "").strip()
    normalized = normalize_persona_text(raw_text)
    if len(normalized) < 3:
        return {
            "summary": "Önce nasıl bir asistan istediğini biraz daha açık tarif et.",
            "confidence": 0.0,
            "matched_forms": [],
            "why": ["Yeterli açıklama olmadığı için net bir form önerisi üretilemedi."],
            "form": {
                "title": "",
                "summary": "",
                "category": "custom",
                "scopes": ["personal"],
                "capabilities": ["custom_guidance"],
                "ui_surfaces": ["assistant_core"],
                "supports_coaching": False,
            },
            "behavior_contract_patch": {},
            "activation_prompt": "İstediğin asistanı biraz daha açık tarif et.",
        }

    matched_forms: list[dict[str, Any]] = []
    matched_form_slugs: set[str] = set()
    for slug, spec in ASSISTANT_FORM_CATALOG.items():
        aliases = [normalize_persona_text(alias) for alias in spec.get("aliases") or []]
        if normalize_persona_text(spec.get("title") or "") in normalized or any(alias in normalized for alias in aliases):
            matched_forms.append(dict(spec))
            matched_form_slugs.add(slug)

    capability_hits: set[str] = set()
    why: list[str] = []
    for slug, tokens in ASSISTANT_FORM_BLUEPRINT_HINTS.items():
        if _matches_any(normalized, tokens):
            capability_hits.add(slug)
    if matched_forms:
        for spec in matched_forms:
            capability_hits.update(str(item).strip() for item in list(spec.get("capabilities") or []) if str(item).strip())
            why.append(f"`{spec.get('title')}` formuna benzeyen bir talep algılandı.")

    inferred = _infer_custom_form_traits(raw_text)
    capability_hits.update(str(item).strip() for item in inferred.get("capabilities") or [])

    scopes = set(str(item).strip() for item in inferred.get("scopes") or [])
    for slug in capability_hits:
        spec = ASSISTANT_CAPABILITY_CATALOG.get(slug) or {}
        scopes.update(str(item).strip() for item in list(spec.get("suggested_scopes") or []) if str(item).strip())
    if any(token in normalized for token in ("hukuk", "avukat", "müvekkil", "muvekkil", "sözleşme", "sozlesme", "iş", "work")):
        scopes.update({"workspace", "professional"})
    if any(token in normalized for token in ("kişisel", "günlük", "benim", "hayat", "yasam", "yaşam", "telefon")):
        scopes.add("personal")
    if any(token in normalized for token in ("proje", "dosya", "matter")):
        scopes.add("project")
    if not scopes:
        scopes.update({"personal", "global"})

    surfaces = {"assistant_core"}
    for slug in capability_hits:
        surfaces.update(str(item).strip() for item in list((ASSISTANT_CAPABILITY_CATALOG.get(slug) or {}).get("implies_surfaces") or []) if str(item).strip())
    surfaces.update(str(item).strip() for item in inferred.get("ui_surfaces") or [])

    category = inferred.get("category") or (matched_forms[0].get("category") if matched_forms else "custom")
    title = _extract_blueprint_title(raw_text, normalized, matched_forms)
    title_slug = _slugify(title)
    existing_slugs = {item.get("slug") for item in normalize_assistant_forms((runtime_profile or {}).get("assistant_forms"))}
    if title_slug in existing_slugs and matched_forms:
        title = str(matched_forms[0].get("title") or title).strip()
    behavior_patch = _blueprint_behavior_patch(normalized)
    supports_coaching = bool(inferred.get("supports_coaching")) or any(
        slug in {"goal_tracking", "habit_checkins", "accountability", "study_planning", "reading_progress", "review_cycles"}
        for slug in capability_hits
    )

    summary_parts = []
    if matched_forms:
        summary_parts.append(f"{matched_forms[0].get('title')} odağına yakın.")
    if capability_hits:
        capability_titles = [
            str((ASSISTANT_CAPABILITY_CATALOG.get(slug) or {}).get("title") or slug).strip()
            for slug in sorted(capability_hits)
        ]
        summary_parts.append(f"Öne çıkan yetenekler: {', '.join(capability_titles[:5])}.")
    if behavior_patch:
        summary_parts.append(
            "Davranış ayarı önerisi: "
            + ", ".join(f"{key}={value}" for key, value in behavior_patch.items())
            + "."
        )
    if not why and capability_hits:
        why.append("Talepte geçen hedefler ve iş akışları bu yeteneklerle eşleşti.")
    elif not why:
        why.append("Talep özel bir asistan formu olarak yorumlandı.")

    confidence = min(0.95, 0.42 + (0.18 * len(matched_forms)) + (0.06 * min(len(capability_hits), 5)) + (0.05 if behavior_patch else 0.0))
    capability_titles = [
        str((ASSISTANT_CAPABILITY_CATALOG.get(slug) or {}).get("title") or slug).strip()
        for slug in sorted(capability_hits)
    ]
    return {
        "summary": " ".join(summary_parts).strip() or f"{title} için özel bir assistant form blueprint'i üretildi.",
        "confidence": round(confidence, 2),
        "matched_forms": [
            {"slug": str(item.get("slug") or ""), "title": str(item.get("title") or ""), "category": str(item.get("category") or "")}
            for item in matched_forms
        ],
        "why": why[:4],
        "behavior_contract_patch": behavior_patch,
        "activation_prompt": f'"{title}" formunu aktif edip buna göre davran.',
        "transformation_scope": sorted(scopes),
        "capability_titles": capability_titles,
        "form": {
            "slug": _slugify(title),
            "title": title,
            "summary": clean_persona_text(raw_text, limit=220) or f"{title} için kullanıcı tarafından tarif edilen özel asistan formu.",
            "category": str(category or "custom"),
            "scopes": sorted(scopes),
            "capabilities": sorted(capability_hits) or ["custom_guidance"],
            "ui_surfaces": sorted(surfaces),
            "supports_coaching": supports_coaching,
            "custom": True,
            "source": "blueprint",
        },
    }


def assistant_operating_contract(runtime_profile: dict[str, Any] | None, *, coaching_goal_count: int = 0) -> dict[str, Any]:
    profile = runtime_profile or {}
    forms = normalize_assistant_forms(profile.get("assistant_forms"))
    contract = normalize_behavior_contract(profile.get("behavior_contract"))
    active_forms = [item for item in forms if item.get("active")]
    capability_contracts = _active_capability_contracts(active_forms)
    surface_contracts = _active_surface_contracts(active_forms, capability_contracts)
    supports_coaching = any(bool(item.get("supports_coaching")) for item in active_forms) or coaching_goal_count > 0
    if coaching_goal_count > 0 and not any(item.get("slug") == "goal_tracking" for item in capability_contracts):
        goal_tracking = dict(ASSISTANT_CAPABILITY_CATALOG.get("goal_tracking") or {})
        capability_contracts.append(
            {
                "slug": "goal_tracking",
                "title": str(goal_tracking.get("title") or "Hedef takibi").strip(),
                "summary": str(goal_tracking.get("summary") or "Aktif hedeflerin ilerlemesini takip eder.").strip(),
                "category": str(goal_tracking.get("category") or "coaching"),
                "suggested_scopes": [str(item).strip() for item in list(goal_tracking.get("suggested_scopes") or ["personal"]) if str(item).strip()],
                "implies_surfaces": [str(item).strip() for item in list(goal_tracking.get("implies_surfaces") or ["coaching_dashboard", "progress_tracking"]) if str(item).strip()],
                "operating_hint": _capability_operating_hint("goal_tracking", str(goal_tracking.get("summary") or "")),
            }
        )
        surface_contracts = _active_surface_contracts(active_forms, capability_contracts)
    primary_scope = "global"
    if active_forms:
        scopes = [str(scope).strip() for item in active_forms for scope in list(item.get("scopes") or []) if str(scope).strip()]
        if "personal" in scopes:
            primary_scope = "personal"
        elif scopes:
            primary_scope = scopes[0]
    guidance = [str(item.get("operating_hint") or "").strip() for item in capability_contracts if str(item.get("operating_hint") or "").strip()]
    setup_actions = _assistant_setup_actions(active_forms, capability_contracts, surface_contracts, coaching_goal_count=coaching_goal_count)
    return {
        "mode": "specialized" if active_forms else "general_core",
        "primary_scope": primary_scope,
        "supports_coaching": supports_coaching,
        "behavior_style": _behavior_style_summary(contract),
        "active_form_titles": [str(item.get("title") or item.get("slug") or "").strip() for item in active_forms],
        "capability_contracts": capability_contracts,
        "surface_contracts": surface_contracts,
        "guidance": guidance[:6],
        "setup_actions": setup_actions,
    }


def normalize_behavior_contract(contract: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(DEFAULT_BEHAVIOR_CONTRACT)
    for key in payload:
        value = str((contract or {}).get(key) or "").strip()
        if value:
            payload[key] = value
    return payload


def normalize_assistant_forms(forms: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in list(forms or []):
        if isinstance(raw_item, str):
            raw_item = {"slug": raw_item}
        if not isinstance(raw_item, dict):
            continue
        raw_slug = str(raw_item.get("slug") or "").strip()
        slug = raw_slug if raw_slug in ASSISTANT_FORM_CATALOG else _slugify(raw_slug or str(raw_item.get("title") or raw_item.get("name") or ""))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        spec = dict(ASSISTANT_FORM_CATALOG.get(slug) or {})
        title = str(raw_item.get("title") or spec.get("title") or slug.replace("-", " ").title()).strip()
        summary = clean_persona_text(str(raw_item.get("summary") or spec.get("summary") or ""), limit=280)
        normalized_items.append(
            {
                "slug": slug,
                "title": title,
                "summary": summary,
                "category": str(raw_item.get("category") or spec.get("category") or "custom"),
                "active": bool(raw_item.get("active", True)),
                "source": str(raw_item.get("source") or raw_item.get("created_from") or "manual"),
                "scopes": [str(item).strip() for item in list(raw_item.get("scopes") or spec.get("scopes") or []) if str(item).strip()],
                "capabilities": [str(item).strip() for item in list(raw_item.get("capabilities") or spec.get("capabilities") or []) if str(item).strip()],
                "ui_surfaces": [str(item).strip() for item in list(raw_item.get("ui_surfaces") or spec.get("ui_surfaces") or []) if str(item).strip()],
                "supports_coaching": bool(raw_item.get("supports_coaching", spec.get("supports_coaching"))),
                "custom": slug not in ASSISTANT_FORM_CATALOG,
                "created_at": raw_item.get("created_at") or _iso_now(),
                "updated_at": raw_item.get("updated_at") or raw_item.get("created_at") or _iso_now(),
                "last_requested_at": raw_item.get("last_requested_at") or raw_item.get("updated_at") or raw_item.get("created_at") or _iso_now(),
            }
        )
    normalized_items.sort(key=lambda item: (0 if item.get("active") else 1, str(item.get("title") or "").lower()))
    return normalized_items


def assistant_core_prompt_lines(runtime_profile: dict[str, Any] | None) -> list[str]:
    if not runtime_profile:
        return []
    lines: list[str] = []
    active_forms = [item for item in normalize_assistant_forms(runtime_profile.get("assistant_forms")) if item.get("active")]
    if active_forms:
        form_bits = [f"{item['title']} ({', '.join(item.get('capabilities') or [])})" for item in active_forms[:4]]
        lines.append(f"- Aktif asistan formları: {'; '.join(form_bits)}")
    contract = normalize_behavior_contract(runtime_profile.get("behavior_contract"))
    if contract:
        lines.append(
            "- Çalışma kontratı: "
            + _behavior_style_summary(contract)
        )
    operating_contract = assistant_operating_contract(runtime_profile)
    capability_contracts = list(operating_contract.get("capability_contracts") or [])
    if capability_contracts:
        lines.append(
            "- Aktif capability sözleşmeleri: "
            + "; ".join(
                f"{item.get('title')} -> {item.get('operating_hint')}"
                for item in capability_contracts[:4]
                if str(item.get("title") or "").strip()
            )
        )
    return lines


def build_assistant_core_status(runtime_profile: dict[str, Any] | None, *, coaching_goal_count: int = 0) -> dict[str, Any]:
    profile = runtime_profile or {}
    forms = normalize_assistant_forms(profile.get("assistant_forms"))
    contract = normalize_behavior_contract(profile.get("behavior_contract"))
    active_forms = [item for item in forms if item.get("active")]
    operating_contract = assistant_operating_contract(profile, coaching_goal_count=coaching_goal_count)
    capability_contracts = list(operating_contract.get("capability_contracts") or [])
    surface_contracts = list(operating_contract.get("surface_contracts") or [])
    capabilities = sorted({cap for item in active_forms for cap in list(item.get("capabilities") or [])})
    scopes = sorted({scope for item in active_forms for scope in list(item.get("scopes") or [])})
    ui_surfaces = sorted({surface for item in active_forms for surface in list(item.get("ui_surfaces") or [])})
    available_forms = [
        {
            "slug": spec["slug"],
            "title": spec["title"],
            "summary": spec["summary"],
            "category": spec["category"],
            "scopes": list(spec.get("scopes") or []),
            "capabilities": list(spec.get("capabilities") or []),
            "ui_surfaces": list(spec.get("ui_surfaces") or []),
            "supports_coaching": bool(spec.get("supports_coaching")),
        }
        for spec in assistant_form_catalog()
        if spec["slug"] not in {item["slug"] for item in active_forms}
    ]
    evolution_history = [dict(item) for item in list(profile.get("evolution_history") or [])][-8:]
    supports_coaching = any(bool(item.get("supports_coaching")) for item in active_forms) or coaching_goal_count > 0
    return {
        "summary": {
            "active_forms": len(active_forms),
            "available_forms": len(available_forms),
            "supports_coaching": supports_coaching,
            "capability_count": len(capabilities),
        },
        "active_forms": active_forms,
        "available_forms": available_forms[:6],
        "behavior_contract": contract,
        "capabilities": capabilities,
        "scopes": scopes,
        "ui_surfaces": ui_surfaces,
        "capability_contracts": capability_contracts,
        "surface_contracts": surface_contracts,
        "operating_contract": operating_contract,
        "suggested_setup_actions": list(operating_contract.get("setup_actions") or []),
        "supports_coaching": supports_coaching,
        "evolution_history": evolution_history,
        "core_summary": _build_core_summary(active_forms, contract, supports_coaching=supports_coaching),
        "defaults": {
            "role_summary": DEFAULT_ASSISTANT_ROLE_SUMMARY,
            "tone": DEFAULT_ASSISTANT_TONE,
        },
        "form_catalog": assistant_form_catalog(),
        "capability_catalog": assistant_capability_catalog(),
        "surface_catalog": assistant_surface_catalog(),
        "transformation_examples": assistant_transformation_examples(),
    }


def _build_core_summary(active_forms: list[dict[str, Any]], contract: dict[str, str], *, supports_coaching: bool) -> str:
    if not active_forms:
        return "Asistan çekirdeği şu an genel amaçlı. Kullanıcı sohbet içinde yeni bir forma yön verdikçe kişiselleşir."
    form_titles = ", ".join(str(item.get("title") or "") for item in active_forms[:3])
    summary = f"Asistan çekirdeği şu anda {form_titles} odağıyla çalışıyor."
    if supports_coaching:
        summary += " Hedef ve alışkanlık takibi aktif hale gelebilir."
    if contract.get("initiative_level") == "high":
        summary += " Proaktiflik yüksek."
    return summary


def apply_assistant_core_update(text: str, runtime_profile: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_persona_text(text)
    profile = dict(runtime_profile or {})
    forms = normalize_assistant_forms(profile.get("assistant_forms"))
    contract = normalize_behavior_contract(profile.get("behavior_contract"))
    history = [dict(item) for item in list(profile.get("evolution_history") or [])]
    changed_fields: list[str] = []

    form_updates = _extract_form_updates(normalized, text, forms)
    if form_updates:
        forms = _merge_form_updates(forms, form_updates)
        changed_fields.append("assistant_forms")
        history.append(
            {
                "id": f"assistant-form-{_fingerprint(text)}",
                "kind": "assistant_form_update",
                "summary": _form_history_summary(form_updates),
                "source_text": clean_persona_text(text, limit=240),
                "created_at": _iso_now(),
            }
        )

    next_contract = _extract_behavior_contract_updates(normalized, contract)
    if next_contract != contract:
        contract = next_contract
        changed_fields.append("behavior_contract")
        history.append(
            {
                "id": f"assistant-contract-{_fingerprint(text + json_contract_key(contract))}",
                "kind": "behavior_contract_update",
                "summary": _contract_history_summary(contract),
                "source_text": clean_persona_text(text, limit=240),
                "created_at": _iso_now(),
            }
        )

    if not changed_fields:
        return {}

    history = history[-40:]
    patch: dict[str, Any] = {
        "assistant_forms": forms,
        "behavior_contract": contract,
        "evolution_history": history,
    }
    auto_role = _auto_role_summary(forms)
    if auto_role and _should_replace_role_summary(str(profile.get("role_summary") or "")):
        patch["role_summary"] = auto_role
        changed_fields.append("role_summary")
    return {
        "patch": patch,
        "changed_fields": list(dict.fromkeys(changed_fields)),
        "summary": _core_update_summary(changed_fields, forms),
    }


def json_contract_key(contract: dict[str, str]) -> str:
    return "|".join(f"{key}:{contract.get(key, '')}" for key in sorted(contract))


def _should_replace_role_summary(current: str) -> bool:
    normalized = normalize_persona_text(current)
    return normalized in {
        "",
        normalize_persona_text("Kaynak dayanaklı hukuk çalışma asistanı"),
        normalize_persona_text(DEFAULT_ASSISTANT_ROLE_SUMMARY),
    } or normalized.startswith(normalize_persona_text(DEFAULT_ASSISTANT_ROLE_SUMMARY))


def _auto_role_summary(forms: list[dict[str, Any]]) -> str | None:
    active_forms = [item for item in forms if item.get("active")]
    if not active_forms:
        return None
    if len(active_forms) == 1:
        return f"{DEFAULT_ASSISTANT_ROLE_SUMMARY}. Şu anda {active_forms[0]['title']} odağında çalışıyor."
    labels = ", ".join(str(item.get("title") or "") for item in active_forms[:3])
    return f"{DEFAULT_ASSISTANT_ROLE_SUMMARY}. Aktif formlar: {labels}."


def _extract_form_updates(normalized: str, raw_text: str, existing_forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not any(marker in normalized for marker in _ACTIVATION_MARKERS + _DEACTIVATION_MARKERS):
        return []
    updates: list[dict[str, Any]] = []
    negative = any(marker in normalized for marker in _DEACTIVATION_MARKERS)
    positive = any(marker in normalized for marker in _ACTIVATION_MARKERS)
    for slug, spec in ASSISTANT_FORM_CATALOG.items():
        aliases = [normalize_persona_text(alias) for alias in spec.get("aliases") or []]
        if not any(alias in normalized for alias in aliases):
            continue
        active = False if negative and not positive else True
        updates.append(
            {
                "slug": slug,
                "title": spec["title"],
                "summary": spec["summary"],
                "category": spec["category"],
                "active": active,
                "source": "conversation",
                "scopes": list(spec.get("scopes") or []),
                "capabilities": list(spec.get("capabilities") or []),
                "ui_surfaces": list(spec.get("ui_surfaces") or []),
                "supports_coaching": bool(spec.get("supports_coaching")),
                "updated_at": _iso_now(),
                "last_requested_at": _iso_now(),
            }
        )
    if updates:
        return updates

    if not positive:
        return []

    custom_match = re.search(
        r"(?:bundan sonra|artik|artık|sen|bana)\s+(?:benim\s+)?(.+?)\s+(?:ol|olsun|gibi davran|olarak calis|olarak çalış)",
        normalized,
    )
    if not custom_match:
        return []
    title = clean_persona_text(custom_match.group(1), limit=80)
    if not title or len(title.split()) > 6:
        return []
    slug = _slugify(title)
    if slug in {item.get("slug") for item in existing_forms}:
        return []
    inferred = _infer_custom_form_traits(title)
    return [
        {
            "slug": slug,
            "title": title.title(),
            "summary": f"Kullanıcının sohbet içinde tanımladığı özel asistan formu: {title}.",
            "category": inferred["category"],
            "active": True,
            "source": "conversation",
            "scopes": inferred["scopes"],
            "capabilities": inferred["capabilities"],
            "ui_surfaces": inferred["ui_surfaces"],
            "supports_coaching": inferred["supports_coaching"],
            "updated_at": _iso_now(),
            "last_requested_at": _iso_now(),
            "custom": True,
        }
    ]


def _merge_form_updates(existing_forms: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {str(item.get("slug") or ""): dict(item) for item in existing_forms}
    for update in updates:
        slug = str(update.get("slug") or "")
        if not slug:
            continue
        current = dict(merged.get(slug) or {})
        current.update(update)
        current["updated_at"] = update.get("updated_at") or _iso_now()
        current["last_requested_at"] = update.get("last_requested_at") or current.get("updated_at") or _iso_now()
        merged[slug] = current
    return normalize_assistant_forms(list(merged.values()))


def _infer_custom_form_traits(title: str) -> dict[str, Any]:
    normalized = normalize_persona_text(title)
    category = "custom"
    scopes = ["personal", "global"]
    capabilities = {"custom_guidance"}
    ui_surfaces = {"assistant_core"}
    supports_coaching = False

    if any(token in normalized for token in ("koc", "koç", "mentor", "rehber", "danisman", "danışman")):
        category = "coaching"
        capabilities.update({"goal_tracking", "habit_checkins", "accountability"})
        ui_surfaces.update({"coaching_dashboard", "progress_tracking", "proactive_triggers"})
        supports_coaching = True
    if any(token in normalized for token in ("okuma", "kitap", "ders", "ogren", "öğren", "calisma", "çalışma", "study")):
        category = "learning" if category == "custom" else category
        capabilities.update({"study_planning", "reading_progress", "review_cycles"})
        ui_surfaces.update({"progress_tracking", "coaching_dashboard"})
        supports_coaching = True
    if any(token in normalized for token in ("hukuk", "avukat", "legal", "dava", "muvekkil", "müvekkil", "sozlesme", "sözleşme")):
        category = "professional"
        scopes = ["professional", "project"]
        capabilities.update({"legal_reasoning", "document_tracking", "deadline_follow_up", "draft_support"})
        ui_surfaces.update({"matter_context", "decision_timeline"})
        supports_coaching = False
    if any(token in normalized for token in ("telefon", "cihaz", "mobil", "bildirim", "notification")):
        category = "device"
        scopes = ["personal"]
        capabilities.update({"message_triage", "notification_guidance", "device_routines"})
        ui_surfaces.update({"connector_status", "location_context"})
    if any(
        token in normalized
        for token in (
            "magaza",
            "mağaza",
            "e ticaret",
            "e-ticaret",
            "store",
            "shop",
            "musteri",
            "müşteri",
            "satis",
            "satış",
            "instagram",
            "whatsapp",
            "siparis",
            "sipariş",
            "stok",
            "urun",
            "ürün",
            "katalog",
            "inventory",
        )
    ):
        category = "business"
        scopes = ["workspace", "project", "global"]
        capabilities.update(
            {
                "omnichannel_inbox",
                "catalog_grounding",
                "inventory_lookup",
                "order_status_support",
                "product_recommendation",
                "customer_tone_control",
                "draft_support",
            }
        )
        ui_surfaces.update({"customer_inbox", "catalog_panel", "connector_status", "draft_preview", "decision_timeline"})
    if any(token in normalized for token in ("seyahat", "travel", "gezi", "rota", "ulasim", "ulaşım")):
        category = "travel" if category == "custom" else category
        capabilities.update({"route_planning", "travel_preference_support", "nearby_recommendations"})
        ui_surfaces.update({"location_context", "travel_cards"})
    if any(token in normalized for token in ("organizasyon", "duzen", "düzen", "planlayici", "planlayıcı", "ops")):
        category = "personal_ops" if category == "custom" else category
        capabilities.update({"daily_planning", "task_follow_up", "calendar_load_management"})
        ui_surfaces.update({"agenda", "task_cards"})

    return {
        "category": category,
        "scopes": sorted(scopes),
        "capabilities": sorted(capabilities),
        "ui_surfaces": sorted(ui_surfaces),
        "supports_coaching": supports_coaching,
    }


def _extract_behavior_contract_updates(normalized: str, current: dict[str, str]) -> dict[str, str]:
    directive_markers = (
        *ASSISTANT_DIRECTION_MARKERS,
        "bundan sonra",
        "cevap verirken",
        "yanit verirken",
        "yanıt verirken",
        "bana kisa cevap ver",
        "bana kısa cevap ver",
        "cevaplari kisa tut",
        "cevapları kısa tut",
        "daha proaktif ol",
        "fazla proaktif olma",
        "cok bildirim istemiyorum",
        "çok bildirim istemiyorum",
        "arada sor",
        "gerekirse sor",
        "nazik ol",
        "yumusak ol",
        "yumuşak ol",
        "detayli plan",
        "detaylı plan",
        "hafif plan",
        "kisa plan",
        "kısa plan",
        "ozet plan",
        "özet plan",
        "detayli acikla",
        "detaylı açıkla",
        "gerekcesini anlat",
        "gerekçesini anlat",
    )
    if not any(token in normalized for token in directive_markers):
        return normalize_behavior_contract(current)
    contract = dict(current)
    if any(token in normalized for token in ("proaktif ol", "takip et", "beni durt", "beni dürt", "hesap sor", "sik takip", "sık takip")):
        contract["initiative_level"] = "high"
        contract["follow_up_style"] = "persistent"
        contract["accountability_style"] = "firm"
    if any(token in normalized for token in ("fazla proaktif olma", "cok bildirim istemiyorum", "çok bildirim istemiyorum", "arada sor", "gerekirse sor")):
        contract["initiative_level"] = "low"
        contract["follow_up_style"] = "on_request"
    if any(token in normalized for token in ("nazik ol", "yumusak ol", "yumuşak ol", "sert olma")):
        contract["accountability_style"] = "gentle"
    if any(token in normalized for token in ("detayli plan", "detaylı plan", "ince plan", "mikro plan")):
        contract["planning_depth"] = "deep"
    if any(token in normalized for token in ("hafif plan", "kisa plan", "kısa plan", "ozet plan", "özet plan")):
        contract["planning_depth"] = "light"
    if any(token in normalized for token in ("kisa cevap", "kısa cevap", "kisa yanit", "kısa yanıt", "cevaplari kisa tut", "cevapları kısa tut", "ozet gec", "özet geç", "ozet anlat", "özet anlat")):
        contract["explanation_style"] = "concise"
    if any(token in normalized for token in ("detayli acikla", "detaylı açıkla", "gerekcesini anlat", "gerekçesini anlat")):
        contract["explanation_style"] = "detailed"
    return normalize_behavior_contract(contract)


def _form_history_summary(updates: list[dict[str, Any]]) -> str:
    labels = []
    for item in updates:
        title = str(item.get("title") or item.get("slug") or "").strip()
        if not title:
            continue
        labels.append(f"{title} {'aktif' if item.get('active') else 'pasif'}")
    return f"Asistan formları güncellendi: {', '.join(labels[:4])}."


def _contract_history_summary(contract: dict[str, str]) -> str:
    return (
        "Davranış kontratı güncellendi: "
        f"proaktiflik={contract.get('initiative_level')}, "
        f"takip={contract.get('follow_up_style')}, "
        f"plan={contract.get('planning_depth')}."
    )


def _core_update_summary(changed_fields: list[str], forms: list[dict[str, Any]]) -> str:
    if "assistant_forms" in changed_fields:
        active_titles = [str(item.get("title") or "") for item in forms if item.get("active")]
        if active_titles:
            return f"Asistan çekirdeği yeni forma geçti: {', '.join(active_titles[:3])}."
    if "behavior_contract" in changed_fields:
        return "Asistanın çalışma kontratı güncellendi."
    return "Asistan çekirdeği güncellendi."
