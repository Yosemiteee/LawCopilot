import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { ElasticSetupPanel } from "../components/connectors/ElasticSetupPanel";
import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import { sozluk } from "../i18n";
import { PersonalModelPage } from "./PersonalModelPage";
import {
  buildAssistantRuntimeBlueprint,
  getAssistantContactProfiles,
  getAssistantRuntimeCore,
  getAssistantRuntimeProfile,
  getHealth,
  getUserProfile,
  saveAssistantRuntimeProfile,
  updateAssistantLocationContext,
  getWorkspaceOverview,
  saveUserProfile,
} from "../services/lawcopilotApi";
import type {
  AssistantContactProfile,
  AssistantCoreBlueprint,
  AssistantCoreCapabilityCatalogItem,
  AssistantCoreStatus,
  AssistantCoreSurfaceCatalogItem,
  AssistantRuntimeProfile,
  InboxBlockRule,
  InboxKeywordRule,
  InboxWatchRule,
  ProfileImportantDate,
  RelatedProfile,
  SourcePreferenceRule,
  UserProfile,
  WorkspaceOverviewResponse,
} from "../types/domain";

const PROFILE_CACHE_KEY = "lawcopilot.settings.profile";
const ASSISTANT_RUNTIME_CACHE_KEY = "lawcopilot.settings.assistant-runtime-profile";
const SETTINGS_MEMORY_UPDATE_EVENT = "lawcopilot:memory-updates";
const SETTINGS_CONTACT_REFRESH_INTERVAL_MS = 60000;
const DEFAULT_ASSISTANT_ROLE_SUMMARY = "Kullanıcının istediğine göre şekillenen çekirdek asistan";
const SOURCE_PREFERENCE_TASK_OPTIONS = [
  { value: "general_research", label: "Genel araştırma" },
  { value: "legal_research", label: "Hukuk araştırması" },
  { value: "travel_booking", label: "Bilet ve rezervasyon" },
  { value: "travel", label: "Seyahat planı" },
  { value: "places", label: "Yer ve rota" },
  { value: "cinema", label: "Sinema ve etkinlik" },
  { value: "shopping", label: "Alışveriş" },
  { value: "clothing", label: "Kıyafet" },
  { value: "gift", label: "Hediye" },
  { value: "dining", label: "Yeme içme" },
] as const;

function normalizeNarrativeLine(value: string) {
  return String(value || "")
    .replace(/^[-*]\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function appendNarrativeLine(lines: string[], value: string | null | undefined) {
  const cleaned = normalizeNarrativeLine(String(value || ""));
  if (!cleaned) {
    return;
  }
  const comparable = cleaned.replace(/[.!?]+$/, "").toLocaleLowerCase("tr-TR");
  const existing = lines.map((item) => normalizeNarrativeLine(item).replace(/[.!?]+$/, "").toLocaleLowerCase("tr-TR"));
  if (existing.includes(comparable)) {
    return;
  }
  lines.push(/[.!?]$/.test(cleaned) ? cleaned : `${cleaned}.`);
}

function splitNarrative(value: string | null | undefined) {
  return String(value || "")
    .split("\n")
    .map((item) => normalizeNarrativeLine(item))
    .filter(Boolean);
}

function narrativeComparable(value: string) {
  return normalizeNarrativeLine(value)
    .replace(/[.!?]+$/, "")
    .toLocaleLowerCase("tr-TR");
}

function buildStructuredProfileLines(profile?: Partial<UserProfile> | null) {
  const lines: string[] = [];
  appendNarrativeLine(lines, profile?.communication_style);
  if (profile?.favorite_color) {
    appendNarrativeLine(lines, `Sevdiği renk: ${profile.favorite_color}`);
  }
  appendNarrativeLine(lines, profile?.transport_preference);
  appendNarrativeLine(lines, profile?.weather_preference);
  appendNarrativeLine(lines, profile?.food_preferences);
  appendNarrativeLine(lines, profile?.travel_preferences);
  if (profile?.home_base) {
    appendNarrativeLine(lines, `Ana yaşam / dönüş noktası: ${profile.home_base}`);
  }
  if (profile?.current_location) {
    appendNarrativeLine(lines, `Güncel konum: ${profile.current_location}`);
  }
  appendNarrativeLine(lines, profile?.location_preferences ? `Yakın çevre tercihleri: ${profile.location_preferences}` : "");
  appendNarrativeLine(lines, profile?.maps_preference ? `Harita tercihi: ${profile.maps_preference}` : "");
  if (Array.isArray(profile?.source_preference_rules)) {
    profile.source_preference_rules.slice(0, 3).forEach((item) => {
      const providers = Array.isArray(item.preferred_providers) ? item.preferred_providers.filter(Boolean).slice(0, 2).join(", ") : "";
      const domains = Array.isArray(item.preferred_domains) ? item.preferred_domains.filter(Boolean).slice(0, 2).join(", ") : "";
      appendNarrativeLine(lines, `${String(item.label || item.task_kind || "Kaynak tercihi")}: ${providers || domains || String(item.note || "").trim()}`);
    });
  }
  if (profile?.prayer_notifications_enabled) {
    appendNarrativeLine(lines, "Özel rutin ve mekan desteğini proaktif tut.");
  }
  appendNarrativeLine(lines, profile?.prayer_habit_notes);
  return lines;
}

function cleanManualProfileNotes(profile?: Partial<UserProfile> | null) {
  const structuredLines = new Set(buildStructuredProfileLines(profile).map((item) => narrativeComparable(item)));
  return splitNarrative(profile?.assistant_notes)
    .filter((item) => {
      const comparable = narrativeComparable(item);
      return comparable && !structuredLines.has(comparable);
    })
    .join("\n");
}

function buildAssistantBehaviorNarrative(profile?: Partial<AssistantRuntimeProfile> | null) {
  const lines: string[] = [];
  for (const item of splitNarrative(profile?.soul_notes)) {
    appendNarrativeLine(lines, item);
  }
  if (profile?.role_summary) {
    appendNarrativeLine(lines, `Rol: ${profile.role_summary}`);
  }
  if (profile?.tone) {
    appendNarrativeLine(lines, `Ton: ${profile.tone}`);
  }
  return lines.join("\n");
}

function buildAssistantOperationsNarrative(profile?: Partial<AssistantRuntimeProfile> | null) {
  const explicit = String(profile?.tools_notes || "").trim();
  if (explicit) {
    return explicit;
  }
  const lines = (profile?.heartbeat_extra_checks || [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  return lines.join("\n");
}

function buildAssistantSignals(profile: Partial<AssistantRuntimeProfile> | null | undefined) {
  return [
    profile?.role_summary ? `Rol: ${profile.role_summary}` : "",
    profile?.tone ? `Ton: ${profile.tone}` : "",
    profile?.tools_notes ? "Rutinler kayıtlı" : "",
    (profile?.assistant_forms || []).some((item) => item.active) ? `${(profile?.assistant_forms || []).filter((item) => item.active).length} aktif form` : "",
  ].filter(Boolean);
}

type DesktopUpdateDraft = {
  enabled: boolean;
  feedUrl: string;
  channel: string;
  autoCheckOnLaunch: boolean;
  autoDownload: boolean;
  allowPrerelease: boolean;
};

type DesktopUpdateStatus = DesktopUpdateDraft & {
  status: string;
  configured: boolean;
  supported: boolean;
  support_reason: string;
  support_message: string;
  current_version: string;
  available_version: string;
  downloaded_version: string;
  last_checked_at: string;
  last_error: string;
  release_notes: string;
  download_percent: number;
  update_downloaded_at: string;
};

function createDefaultDesktopUpdateDraft(): DesktopUpdateDraft {
  return {
    enabled: true,
    feedUrl: "",
    channel: "latest",
    autoCheckOnLaunch: true,
    autoDownload: false,
    allowPrerelease: false,
  };
}

function normalizeDesktopUpdateDraft(raw: Record<string, unknown> | null | undefined): DesktopUpdateDraft {
  const value = raw && typeof raw === "object" ? raw : {};
  const defaults = createDefaultDesktopUpdateDraft();
  return {
    enabled: typeof value.enabled === "boolean" ? Boolean(value.enabled) : defaults.enabled,
    feedUrl: String(value.feedUrl || value.feed_url || "").trim(),
    channel: String(value.channel || defaults.channel).trim() || defaults.channel,
    autoCheckOnLaunch: typeof value.autoCheckOnLaunch === "boolean"
      ? Boolean(value.autoCheckOnLaunch)
      : (typeof value.auto_check_on_launch === "boolean" ? Boolean(value.auto_check_on_launch) : defaults.autoCheckOnLaunch),
    autoDownload: typeof value.autoDownload === "boolean"
      ? Boolean(value.autoDownload)
      : (typeof value.auto_download === "boolean" ? Boolean(value.auto_download) : defaults.autoDownload),
    allowPrerelease: typeof value.allowPrerelease === "boolean"
      ? Boolean(value.allowPrerelease)
      : (typeof value.allow_prerelease === "boolean" ? Boolean(value.allow_prerelease) : defaults.allowPrerelease),
  };
}

function normalizeDesktopUpdateStatus(raw: Record<string, unknown> | null | undefined): DesktopUpdateStatus {
  const value = raw && typeof raw === "object" ? raw : {};
  const draft = normalizeDesktopUpdateDraft(value);
  return {
    ...draft,
    status: String(value.status || "idle").trim() || "idle",
    configured: Boolean(value.configured ?? Boolean(draft.feedUrl && draft.enabled)),
    supported: Boolean(value.supported),
    support_reason: String(value.support_reason || "").trim(),
    support_message: String(value.support_message || "").trim(),
    current_version: String(value.current_version || "").trim(),
    available_version: String(value.available_version || "").trim(),
    downloaded_version: String(value.downloaded_version || "").trim(),
    last_checked_at: String(value.last_checked_at || "").trim(),
    last_error: String(value.last_error || "").trim(),
    release_notes: String(value.release_notes || "").trim(),
    download_percent: Number(value.download_percent || 0),
    update_downloaded_at: String(value.update_downloaded_at || "").trim(),
  };
}

function desktopUpdateDateLabel(value: string) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "Henüz yok";
  }
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return normalized;
  }
  return parsed.toLocaleString("tr-TR");
}

function buildDesktopUpdateSummary(status: DesktopUpdateStatus) {
  const availableVersion = status.available_version ? ` ${status.available_version}` : "";
  const currentVersion = status.current_version || "bilinmiyor";
  if (!status.supported) {
    return {
      tone: "warning" as const,
      title: "Bu kurulum otomatik güncellenemiyor",
      description: status.support_message || "Bu kurulumda güncelleme elle yapılmalı.",
    };
  }
  switch (status.status) {
    case "available":
      return {
        tone: "accent" as const,
        title: "Güncelleme var",
        description: `Yeni sürüm${availableVersion} hazır. Şu an kullandığınız sürüm ${currentVersion}.`,
      };
    case "downloading":
      return {
        tone: "accent" as const,
        title: "Güncelleme indiriliyor",
        description: "İndirme sürüyor. Tamamlandığında yalnız kurulum adımı kalacak.",
      };
    case "downloaded":
      return {
        tone: "accent" as const,
        title: "Kurulum hazır",
        description: `Yeni sürüm${availableVersion || ""} indirildi. Uygulamayı yeniden başlatıp kurabilirsiniz.`,
      };
    case "checking":
      return {
        tone: "neutral" as const,
        title: "Yeni sürüm kontrol ediliyor",
        description: `Şu anki sürüm ${currentVersion}. Kontrol tamamlanınca sonuç burada görünür.`,
      };
    case "no_update":
      return {
        tone: "accent" as const,
        title: "Uygulama güncel",
        description: `Şu an kullandığınız sürüm ${currentVersion}. Yeni bir işlem yapmanız gerekmiyor.`,
      };
    case "disabled":
      return {
        tone: "neutral" as const,
        title: "Güncellemeler kapalı",
        description: "Teknik ayarlardan yeniden açılabilir.",
      };
    case "unconfigured":
      return {
        tone: "warning" as const,
        title: "Güncelleme kaynağı hazır değil",
        description: "Bu alan çoğu kullanıcı için gerekli değildir. Gerekirse teknik ayarlardan tamamlanır.",
      };
    case "error":
      return {
        tone: "warning" as const,
        title: "Güncellemede sorun oldu",
        description: status.last_error || "Biraz sonra yeniden deneyebilirsiniz.",
      };
    default:
      return {
        tone: "neutral" as const,
        title: "Masaüstü sürümü",
        description: `Şu an kullandığınız sürüm ${currentVersion}.`,
      };
  }
}

const ASSISTANT_FORM_PRESETS = [
  {
    slug: "life_coach",
    title: "Yaşam koçu",
    summary: "Hedef, alışkanlık ve takip düzeni kurar.",
    category: "personal",
    scopes: ["personal"],
    capabilities: ["goal_tracking", "habit_checkins", "accountability", "weekly_review"],
    ui_surfaces: ["coaching_dashboard", "progress_tracking", "proactive_triggers"],
    supports_coaching: true,
  },
  {
    slug: "legal_copilot",
    title: "Hukuk asistanı",
    summary: "Dosya, belge, taslak ve tarih takibini öne alır.",
    category: "professional",
    scopes: ["professional", "project"],
    capabilities: ["legal_reasoning", "document_tracking", "deadline_follow_up", "draft_support"],
    ui_surfaces: ["matter_context", "decision_timeline", "proactive_triggers"],
    supports_coaching: false,
  },
  {
    slug: "personal_ops",
    title: "Kişisel organizasyon",
    summary: "Takvim, görev ve günlük yükü düzenler.",
    category: "personal",
    scopes: ["personal", "global"],
    capabilities: ["daily_planning", "task_follow_up", "calendar_load_management", "reminder_support"],
    ui_surfaces: ["agenda", "task_cards", "proactive_triggers"],
    supports_coaching: false,
  },
  {
    slug: "device_companion",
    title: "Telefon / cihaz asistanı",
    summary: "Mesajlar, bildirimler ve cihaz akışını yönetir.",
    category: "device",
    scopes: ["personal"],
    capabilities: ["message_triage", "notification_guidance", "location_handoffs", "device_routines"],
    ui_surfaces: ["connector_status", "location_context", "proactive_triggers"],
    supports_coaching: false,
  },
  {
    slug: "study_mentor",
    title: "Çalışma mentoru",
    summary: "Okuma ve çalışma hedeflerini takip eder.",
    category: "learning",
    scopes: ["personal"],
    capabilities: ["study_planning", "reading_progress", "focus_support", "review_cycles"],
    ui_surfaces: ["coaching_dashboard", "progress_tracking"],
    supports_coaching: true,
  },
  {
    slug: "travel_planner",
    title: "Seyahat planlayıcısı",
    summary: "Rota ve yakın bağlam önerilerini öne alır.",
    category: "travel",
    scopes: ["personal", "global"],
    capabilities: ["route_planning", "travel_preference_support", "nearby_recommendations"],
    ui_surfaces: ["location_context", "travel_cards", "proactive_triggers"],
    supports_coaching: false,
  },
  {
    slug: "customer_support",
    title: "Müşteri destek asistanı",
    summary: "WhatsApp, Instagram ve sipariş kanallarındaki müşteri sorularını toplar.",
    category: "business",
    scopes: ["workspace", "project", "global"],
    capabilities: ["omnichannel_inbox", "order_status_support", "draft_support", "customer_tone_control"],
    ui_surfaces: ["customer_inbox", "decision_timeline", "draft_preview", "connector_status"],
    supports_coaching: false,
  },
  {
    slug: "commerce_ops",
    title: "Mağaza ve satış asistanı",
    summary: "Katalog, stok, sipariş ve sosyal medya yazışmalarını birlikte yönetir.",
    category: "business",
    scopes: ["workspace", "project", "global"],
    capabilities: ["omnichannel_inbox", "catalog_grounding", "inventory_lookup", "order_status_support", "product_recommendation", "draft_support"],
    ui_surfaces: ["customer_inbox", "catalog_panel", "connector_status", "draft_preview", "decision_timeline"],
    supports_coaching: false,
  },
] as const;

const ASSISTANT_SCOPE_OPTIONS = [
  { slug: "personal", title: "Kişisel" },
  { slug: "workspace", title: "Çalışma alanı" },
  { slug: "professional", title: "Profesyonel" },
  { slug: "project", title: "Proje" },
  { slug: "global", title: "Global" },
] as const;

const ASSISTANT_CAPABILITY_FALLBACK: AssistantCoreCapabilityCatalogItem[] = [
  { slug: "goal_tracking", title: "Hedef takibi", category: "coaching", suggested_scopes: ["personal"], implies_surfaces: ["coaching_dashboard", "progress_tracking"] },
  { slug: "habit_checkins", title: "Alışkanlık check-in", category: "coaching", suggested_scopes: ["personal"], implies_surfaces: ["coaching_dashboard", "proactive_triggers"] },
  { slug: "accountability", title: "Hesap verilebilirlik", category: "coaching", suggested_scopes: ["personal"], implies_surfaces: ["coaching_dashboard", "progress_tracking"] },
  { slug: "daily_planning", title: "Günlük planlama", category: "personal_ops", suggested_scopes: ["personal", "global"], implies_surfaces: ["agenda", "task_cards"] },
  { slug: "task_follow_up", title: "Görev takibi", category: "personal_ops", suggested_scopes: ["personal", "workspace"], implies_surfaces: ["task_cards", "proactive_triggers"] },
  { slug: "document_tracking", title: "Belge takibi", category: "professional", suggested_scopes: ["workspace", "project"], implies_surfaces: ["matter_context", "decision_timeline"] },
  { slug: "draft_support", title: "Taslak desteği", category: "communication", suggested_scopes: ["personal", "workspace"], implies_surfaces: ["draft_preview", "decision_timeline"] },
  { slug: "message_triage", title: "Mesaj triyajı", category: "device", suggested_scopes: ["personal"], implies_surfaces: ["connector_status", "proactive_triggers"] },
  { slug: "notification_guidance", title: "Bildirim rehberliği", category: "device", suggested_scopes: ["personal"], implies_surfaces: ["connector_status", "proactive_triggers"] },
  { slug: "study_planning", title: "Çalışma planı", category: "learning", suggested_scopes: ["personal"], implies_surfaces: ["coaching_dashboard", "progress_tracking"] },
  { slug: "reading_progress", title: "Okuma ilerlemesi", category: "learning", suggested_scopes: ["personal"], implies_surfaces: ["coaching_dashboard", "progress_tracking"] },
  { slug: "route_planning", title: "Rota planlama", category: "travel", suggested_scopes: ["personal", "global"], implies_surfaces: ["location_context", "travel_cards"] },
  { slug: "nearby_recommendations", title: "Yakın öneriler", category: "travel", suggested_scopes: ["personal", "global"], implies_surfaces: ["location_context", "proactive_triggers"] },
  { slug: "omnichannel_inbox", title: "Çok kanallı müşteri kutusu", category: "business", suggested_scopes: ["workspace", "project", "global"], implies_surfaces: ["customer_inbox", "connector_status"] },
  { slug: "catalog_grounding", title: "Kataloga dayalı cevaplama", category: "business", suggested_scopes: ["workspace", "project"], implies_surfaces: ["catalog_panel", "draft_preview"] },
  { slug: "inventory_lookup", title: "Stok kontrolü", category: "business", suggested_scopes: ["workspace", "project"], implies_surfaces: ["catalog_panel", "customer_inbox"] },
  { slug: "order_status_support", title: "Sipariş durumu desteği", category: "business", suggested_scopes: ["workspace", "project"], implies_surfaces: ["customer_inbox", "decision_timeline"] },
  { slug: "product_recommendation", title: "Ürün önerisi", category: "business", suggested_scopes: ["workspace", "project", "global"], implies_surfaces: ["catalog_panel", "draft_preview"] },
  { slug: "customer_tone_control", title: "Müşteri iletişim tonu", category: "business", suggested_scopes: ["workspace", "project"], implies_surfaces: ["draft_preview", "decision_timeline"] },
  { slug: "custom_guidance", title: "Özel rehberlik", category: "custom", suggested_scopes: ["personal", "global"], implies_surfaces: ["assistant_core"] },
];

const ASSISTANT_SURFACE_FALLBACK: AssistantCoreSurfaceCatalogItem[] = [
  { slug: "assistant_core", title: "Asistan çekirdeği", category: "core" },
  { slug: "coaching_dashboard", title: "Koçluk paneli", category: "coaching" },
  { slug: "progress_tracking", title: "İlerleme takibi", category: "coaching" },
  { slug: "proactive_triggers", title: "Proaktif öneriler", category: "core" },
  { slug: "agenda", title: "Ajanda", category: "planning" },
  { slug: "task_cards", title: "Görev kartları", category: "planning" },
  { slug: "matter_context", title: "Dosya bağlamı", category: "professional" },
  { slug: "decision_timeline", title: "Karar zaman çizgisi", category: "core" },
  { slug: "connector_status", title: "Bağlayıcı durumu", category: "device" },
  { slug: "location_context", title: "Konum bağlamı", category: "location" },
  { slug: "travel_cards", title: "Seyahat kartları", category: "travel" },
  { slug: "draft_preview", title: "Taslak önizleme", category: "communication" },
  { slug: "customer_inbox", title: "Müşteri kutusu", category: "business" },
  { slug: "catalog_panel", title: "Katalog ve stok paneli", category: "business" },
];

type CustomAssistantFormDraft = {
  title: string;
  summary: string;
  category: string;
  scopes: string[];
  capabilities: string[];
  ui_surfaces: string[];
  supports_coaching: boolean;
  active: boolean;
};

function normalizeAssistantForms(profile?: Partial<AssistantRuntimeProfile> | null) {
  const items = Array.isArray(profile?.assistant_forms) ? profile!.assistant_forms : [];
  return items.map((item) => ({
    slug: String(item?.slug || ""),
    title: String(item?.title || item?.slug || ""),
    summary: String(item?.summary || ""),
    category: String(item?.category || "custom"),
    active: Boolean(item?.active),
    source: String(item?.source || "manual"),
    scopes: Array.isArray(item?.scopes) ? item.scopes.map((value) => String(value || "")) : [],
    capabilities: Array.isArray(item?.capabilities) ? item.capabilities.map((value) => String(value || "")) : [],
    ui_surfaces: Array.isArray(item?.ui_surfaces) ? item.ui_surfaces.map((value) => String(value || "")) : [],
    supports_coaching: Boolean(item?.supports_coaching),
    custom: Boolean(item?.custom),
    created_at: item?.created_at ?? null,
    updated_at: item?.updated_at ?? null,
    last_requested_at: item?.last_requested_at ?? null,
  })).filter((item) => item.slug);
}

function getCustomAssistantForms(profile?: Partial<AssistantRuntimeProfile> | null) {
  const presetSlugs = new Set<string>(ASSISTANT_FORM_PRESETS.map((item) => String(item.slug)));
  return normalizeAssistantForms(profile).filter((item) => Boolean(item.custom) || !presetSlugs.has(item.slug));
}

function normalizeBehaviorContract(profile?: Partial<AssistantRuntimeProfile> | null) {
  const contract = (profile?.behavior_contract || {}) as Record<string, unknown>;
  return {
    initiative_level: String(contract.initiative_level || "balanced"),
    planning_depth: String(contract.planning_depth || "structured"),
    accountability_style: String(contract.accountability_style || "supportive"),
    follow_up_style: String(contract.follow_up_style || "check_in"),
    explanation_style: String(contract.explanation_style || "balanced"),
  };
}

function createEmptyCustomAssistantFormDraft(): CustomAssistantFormDraft {
  return {
    title: "",
    summary: "",
    category: "custom",
    scopes: ["personal"],
    capabilities: [],
    ui_surfaces: ["assistant_core"],
    supports_coaching: false,
    active: true,
  };
}

function toggleStringToken(items: string[], value: string) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return items;
  }
  return items.includes(normalized) ? items.filter((item) => item !== normalized) : [...items, normalized];
}

function assistantFormSlug(value: string) {
  return String(value || "")
    .toLocaleLowerCase("tr-TR")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64) || "ozel-form";
}

function splitChecklist(value: string) {
  return value
    .split("\n")
    .map((item) => item.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 12);
}

function splitCommaList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 12);
}

function createEmptyProfile(officeId: string): UserProfile {
  return {
    office_id: officeId,
    display_name: "",
    favorite_color: "",
    food_preferences: "",
    transport_preference: "",
    weather_preference: "",
    travel_preferences: "",
    home_base: "",
    current_location: "",
    location_preferences: "",
    maps_preference: "Google Maps",
    prayer_notifications_enabled: false,
    prayer_habit_notes: "",
    communication_style: "",
    assistant_notes: "",
    important_dates: [],
    related_profiles: [],
    contact_profile_overrides: [],
    inbox_watch_rules: [],
    inbox_keyword_rules: [],
    inbox_block_rules: [],
    source_preference_rules: [],
    created_at: null,
    updated_at: null,
  };
}

function createEmptyImportantDate(): ProfileImportantDate {
  return {
    label: "",
    date: "",
    recurring_annually: true,
    notes: "",
    next_occurrence: null,
    days_until: null,
  };
}

function createEmptyRelatedProfile(): RelatedProfile {
  return {
    id: `related-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    source: "manual",
    name: "",
    relationship: "",
    closeness: 3,
    preferences: "",
    notes: "",
    important_dates: [],
  };
}

function normalizeCloseness(value: unknown, fallback = 3): number {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return Math.max(1, Math.min(5, Math.round(numeric)));
  }
  return fallback;
}

function inferRelationshipCloseness(value: string) {
  const normalized = String(value || "").trim().toLocaleLowerCase("tr-TR");
  if (!normalized) {
    return 3;
  }
  if (["anne", "annem", "baba", "babam", "eş", "es", "partner", "sevgili", "çocuk", "cocuk", "oğlum", "oglum", "kızım", "kizim"].some((item) => normalized.includes(item))) {
    return 5;
  }
  if (["kardeş", "kardes", "aile", "arkadaş", "arkadas", "kuzen", "yakın dost", "yakin dost"].some((item) => normalized.includes(item))) {
    return 4;
  }
  if (["avukat", "doktor", "müşteri", "musteri", "müvekkil", "muvekkil", "iş ortağı", "is ortagi", "koç", "koc"].some((item) => normalized.includes(item))) {
    return 3;
  }
  return 3;
}

function createEmptySourcePreferenceRule(): SourcePreferenceRule {
  return {
    id: `source-pref-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    task_kind: "general_research",
    policy_mode: "prefer",
    preferred_domains: [],
    preferred_links: [],
    preferred_providers: [],
    note: "",
  };
}

function normalizeProfile(officeId: string, profile?: Partial<UserProfile> | null): UserProfile {
  const base = createEmptyProfile(officeId);
  return {
    ...base,
    ...(profile || {}),
    assistant_notes: cleanManualProfileNotes(profile),
    home_base: String(profile?.home_base || ""),
    current_location: String(profile?.current_location || ""),
    location_preferences: String(profile?.location_preferences || ""),
    maps_preference: String(profile?.maps_preference || "Google Maps"),
    prayer_notifications_enabled: Boolean(profile?.prayer_notifications_enabled),
    prayer_habit_notes: String(profile?.prayer_habit_notes || ""),
    important_dates: Array.isArray(profile?.important_dates)
      ? profile!.important_dates.map((item) => ({
        label: String(item.label || ""),
        date: String(item.date || ""),
        recurring_annually: item.recurring_annually !== false,
        notes: item.notes || "",
        next_occurrence: item.next_occurrence || null,
        days_until: typeof item.days_until === "number" ? item.days_until : null,
      }))
      : [],
    related_profiles: Array.isArray(profile?.related_profiles)
      ? profile!.related_profiles.map((item, index) => ({
        id: String(item.id || `related-${index + 1}`),
        source: String(item.source || "manual"),
        name: String(item.name || ""),
        relationship: String(item.relationship || ""),
        closeness: normalizeCloseness(item.closeness, inferRelationshipCloseness(String(item.relationship || ""))),
        preferences: String(item.preferences || ""),
        notes: String(item.notes || ""),
        important_dates: Array.isArray(item.important_dates)
          ? item.important_dates.map((dateItem) => ({
            label: String(dateItem.label || ""),
            date: String(dateItem.date || ""),
            recurring_annually: dateItem.recurring_annually !== false,
            notes: dateItem.notes || "",
            next_occurrence: dateItem.next_occurrence || null,
            days_until: typeof dateItem.days_until === "number" ? dateItem.days_until : null,
          }))
          : [],
      }))
      : [],
    contact_profile_overrides: Array.isArray(profile?.contact_profile_overrides)
      ? profile!.contact_profile_overrides
        .map((item) => ({
          contact_id: String(item.contact_id || "").trim(),
          description: String(item.description || ""),
          updated_at: item.updated_at || null,
        }))
        .filter((item) => item.contact_id && item.description.trim())
      : [],
    inbox_watch_rules: Array.isArray(profile?.inbox_watch_rules)
      ? profile!.inbox_watch_rules.map((item, index) => ({
        id: String(item.id || `watch-${index + 1}`),
        label: String(item.label || item.match_value || ""),
        match_type: item.match_type === "group" ? "group" : "person",
        match_value: String(item.match_value || item.label || ""),
        channels: Array.isArray(item.channels) ? item.channels.map((channel) => String(channel || "")) : [],
      }))
      : [],
    inbox_keyword_rules: Array.isArray(profile?.inbox_keyword_rules)
      ? profile!.inbox_keyword_rules.map((item, index) => ({
        id: String(item.id || `keyword-${index + 1}`),
        keyword: String(item.keyword || ""),
        label: item.label ? String(item.label) : "",
        channels: Array.isArray(item.channels) ? item.channels.map((channel) => String(channel || "")) : [],
      }))
      : [],
    inbox_block_rules: Array.isArray(profile?.inbox_block_rules)
      ? profile!.inbox_block_rules.map((item, index) => ({
        id: String(item.id || `block-${index + 1}`),
        label: String(item.label || item.match_value || ""),
        match_type: item.match_type === "group" ? "group" : "person",
        match_value: String(item.match_value || item.label || ""),
        channels: Array.isArray(item.channels) ? item.channels.map((channel) => String(channel || "")) : [],
        duration_kind: item.duration_kind === "month" || item.duration_kind === "forever" ? item.duration_kind : "day",
        starts_at: item.starts_at || null,
        expires_at: item.expires_at || null,
      }))
      : [],
    source_preference_rules: Array.isArray(profile?.source_preference_rules)
      ? profile!.source_preference_rules.map((item, index) => ({
        id: String(item.id || `source-pref-${index + 1}`),
        label: String(item.label || ""),
        task_kind: String(item.task_kind || "general_research"),
        policy_mode: item.policy_mode === "restrict" ? "restrict" : "prefer",
        preferred_domains: Array.isArray(item.preferred_domains) ? item.preferred_domains.map((value) => String(value || "")) : [],
        preferred_links: Array.isArray(item.preferred_links) ? item.preferred_links.map((value) => String(value || "")) : [],
        preferred_providers: Array.isArray(item.preferred_providers) ? item.preferred_providers.map((value) => String(value || "")) : [],
        note: String(item.note || ""),
      }))
      : [],
  };
}

function buildUserProfilePayload(profile: UserProfile) {
  return {
    display_name: profile.display_name,
    favorite_color: profile.favorite_color,
    food_preferences: profile.food_preferences,
    transport_preference: profile.transport_preference,
    weather_preference: profile.weather_preference,
    travel_preferences: profile.travel_preferences,
    home_base: profile.home_base.trim(),
    current_location: profile.current_location.trim(),
    location_preferences: profile.location_preferences.trim(),
    maps_preference: profile.maps_preference.trim(),
    prayer_notifications_enabled: profile.prayer_notifications_enabled,
    prayer_habit_notes: profile.prayer_habit_notes.trim(),
    communication_style: profile.communication_style,
    assistant_notes: profile.assistant_notes.trim(),
    important_dates: profile.important_dates.map((item) => ({
      label: item.label,
      date: item.date,
      recurring_annually: item.recurring_annually,
      notes: item.notes ?? undefined,
    })),
    related_profiles: profile.related_profiles
      .filter((item) => item.name.trim())
      .map((item) => ({
        id: item.id || undefined,
        name: item.name.trim(),
        relationship: item.relationship.trim() || undefined,
        closeness: normalizeCloseness(item.closeness, inferRelationshipCloseness(item.relationship)),
        preferences: item.preferences.trim() || undefined,
        notes: item.notes.trim() || undefined,
        important_dates: item.important_dates
          .filter((dateItem) => dateItem.label.trim() && dateItem.date.trim())
          .map((dateItem) => ({
            label: dateItem.label.trim() || "Önemli tarih",
            date: dateItem.date,
            recurring_annually: dateItem.recurring_annually,
            notes: dateItem.notes ?? undefined,
          })),
      })),
    contact_profile_overrides: profile.contact_profile_overrides
      .filter((item) => item.contact_id.trim() && item.description.trim())
      .map((item) => ({
        contact_id: item.contact_id.trim(),
        description: item.description.trim(),
        updated_at: item.updated_at || undefined,
      })),
    inbox_watch_rules: profile.inbox_watch_rules
      .filter((item) => item.match_value.trim())
      .map((item) => ({
        id: item.id || undefined,
        label: item.label.trim() || item.match_value.trim(),
        match_type: item.match_type,
        match_value: item.match_value.trim(),
        channels: uniqueChannels(item.channels.map((channel) => channel.trim().toLowerCase()).filter(Boolean)),
      })),
    inbox_keyword_rules: profile.inbox_keyword_rules
      .filter((item) => item.keyword.trim())
      .map((item) => ({
        id: item.id || undefined,
        keyword: item.keyword.trim(),
        label: item.label?.trim() || undefined,
        channels: uniqueChannels(item.channels.map((channel) => channel.trim().toLowerCase()).filter(Boolean)),
      })),
    inbox_block_rules: profile.inbox_block_rules
      .filter((item) => item.match_value.trim())
      .map((item) => ({
        id: item.id || undefined,
        label: item.label.trim() || item.match_value.trim(),
        match_type: item.match_type,
        match_value: item.match_value.trim(),
        channels: uniqueChannels(item.channels.map((channel) => channel.trim().toLowerCase()).filter(Boolean)),
        duration_kind: item.duration_kind,
        starts_at: item.starts_at || undefined,
        expires_at: item.expires_at || undefined,
      })),
    source_preference_rules: (profile.source_preference_rules || [])
      .filter((item) => (
        item.task_kind.trim()
        && (
          item.preferred_domains.length
          || item.preferred_links.length
          || item.preferred_providers.length
          || String(item.note || "").trim()
        )
      ))
      .map((item) => ({
        id: item.id || undefined,
        label: item.label?.trim() || undefined,
        task_kind: item.task_kind.trim(),
        policy_mode: item.policy_mode,
        preferred_domains: item.preferred_domains.map((value) => value.trim()).filter(Boolean),
        preferred_links: item.preferred_links.map((value) => value.trim()).filter(Boolean),
        preferred_providers: item.preferred_providers.map((value) => value.trim()).filter(Boolean),
        note: item.note?.trim() || undefined,
      })),
  };
}

function createEmptyWatchRule(): InboxWatchRule {
  return {
    id: `watch-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    match_type: "person",
    match_value: "",
    channels: ["email", "whatsapp"],
  };
}

function createEmptyKeywordRule(): InboxKeywordRule {
  return {
    id: `keyword-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    keyword: "",
    label: "",
    channels: ["email"],
  };
}

function buildBlockTimestamps(durationKind: InboxBlockRule["duration_kind"]) {
  const startedAt = new Date();
  if (durationKind === "forever") {
    return { starts_at: startedAt.toISOString(), expires_at: null };
  }
  const expiresAt = new Date(startedAt);
  if (durationKind === "month") {
    expiresAt.setMonth(expiresAt.getMonth() + 1);
  } else {
    expiresAt.setDate(expiresAt.getDate() + 1);
  }
  return { starts_at: startedAt.toISOString(), expires_at: expiresAt.toISOString() };
}

function createEmptyBlockRule(): InboxBlockRule {
  const timestamps = buildBlockTimestamps("day");
  return {
    id: `block-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    label: "",
    match_type: "person",
    match_value: "",
    channels: ["email", "whatsapp"],
    duration_kind: "day",
    starts_at: timestamps.starts_at,
    expires_at: timestamps.expires_at,
  };
}

function uniqueChannels(channels: string[]) {
  return channels.filter((channel, index) => channel && channels.indexOf(channel) === index);
}

function toggleChannel(channels: string[], channel: string) {
  const normalized = channel.trim().toLowerCase();
  if (!normalized) {
    return channels;
  }
  return channels.includes(normalized)
    ? channels.filter((item) => item !== normalized)
    : [...channels, normalized];
}

function formatBlockUntil(value?: string | null) {
  if (!value) {
    return "Süresiz";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

function createEmptyAssistantRuntimeProfile(officeId: string): AssistantRuntimeProfile {
  return {
    office_id: officeId,
    assistant_name: "",
    role_summary: DEFAULT_ASSISTANT_ROLE_SUMMARY,
    tone: "Net ve profesyonel",
    avatar_path: "",
    soul_notes: "",
    tools_notes: "",
    assistant_forms: [],
    behavior_contract: normalizeBehaviorContract(null),
    evolution_history: [],
    heartbeat_extra_checks: [],
    created_at: null,
    updated_at: null,
  };
}

function normalizeAssistantRuntimeProfile(officeId: string, profile?: Partial<AssistantRuntimeProfile> | null): AssistantRuntimeProfile {
  const base = createEmptyAssistantRuntimeProfile(officeId);
  const normalizedRoleSummary = String(profile?.role_summary || "").trim();
  return {
    ...base,
    ...(profile || {}),
    role_summary: normalizedRoleSummary === "Kaynak dayanaklı hukuk çalışma asistanı" ? DEFAULT_ASSISTANT_ROLE_SUMMARY : (normalizedRoleSummary || base.role_summary),
    soul_notes: buildAssistantBehaviorNarrative(profile),
    tools_notes: buildAssistantOperationsNarrative(profile),
    assistant_forms: normalizeAssistantForms(profile),
    behavior_contract: normalizeBehaviorContract(profile),
    evolution_history: Array.isArray(profile?.evolution_history) ? profile!.evolution_history : [],
    heartbeat_extra_checks: Array.isArray(profile?.heartbeat_extra_checks)
      ? profile!.heartbeat_extra_checks.map((item) => String(item || ""))
      : [],
  };
}

function readCachedSettingsValue<T>(key: string): T | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : null;
  } catch {
    return null;
  }
}

function writeCachedSettingsValue(key: string, value: unknown) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    return;
  }
}

type SettingsTab = "kurulum" | "gorunum" | "profil" | "iletisim" | "assistant" | "automation";

type DesktopAutomationRule = {
  id: string;
  summary: string;
  instruction: string;
  mode: string;
  channels: string[];
  targets: string[];
  match_terms: string[];
  reply_text: string;
  reminder_at?: string;
  thread_id?: number;
  active: boolean;
};

type DesktopAutomationSettings = {
  enabled: boolean;
  autoSyncConnectedServices: boolean;
  desktopNotifications: boolean;
  automationRules: DesktopAutomationRule[];
  lastRunAt: string;
};

function normalizeAutomationText(value: unknown, maxLength = 240) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function normalizeAutomationList(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: string[] = [];
  for (const raw of value) {
    const candidate = String(raw || "").trim();
    if (!candidate || items.includes(candidate)) {
      continue;
    }
    items.push(candidate);
  }
  return items;
}

function normalizeAutomationRule(rule: unknown, fallbackId: string): DesktopAutomationRule | null {
  if (!rule || typeof rule !== "object") {
    return null;
  }
  const record = rule as Record<string, unknown>;
  const summary = normalizeAutomationText(record.summary || record.label || record.instruction || "");
  if (!summary) {
    return null;
  }
  return {
    id: normalizeAutomationText(record.id || fallbackId, 80) || fallbackId,
    summary,
    instruction: normalizeAutomationText(record.instruction || summary, 400),
    mode: normalizeAutomationText(record.mode || "custom", 32).toLowerCase() || "custom",
    channels: normalizeAutomationList(record.channels).map((item) => item.toLowerCase()).slice(0, 6),
    targets: normalizeAutomationList(record.targets).slice(0, 12),
    match_terms: normalizeAutomationList(record.match_terms ?? record.matchTerms).slice(0, 12),
    reply_text: normalizeAutomationText(record.reply_text ?? record.replyText, 280),
    reminder_at: normalizeAutomationText(record.reminder_at ?? record.reminderAt, 80),
    thread_id: Number.parseInt(String(record.thread_id ?? record.threadId ?? 0), 10) || undefined,
    active: record.active !== false,
  };
}

function normalizeAutomationRules(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as DesktopAutomationRule[];
  }
  const items: DesktopAutomationRule[] = [];
  const seen = new Set<string>();
  value.forEach((rule, index) => {
    const normalized = normalizeAutomationRule(rule, `rule-${index + 1}`);
    if (!normalized) {
      return;
    }
    const key = `${normalized.mode}:${normalized.summary.toLocaleLowerCase("tr-TR")}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    items.push(normalized);
  });
  return items.slice(0, 40);
}

function createDefaultAutomationSettings(): DesktopAutomationSettings {
  return {
    enabled: true,
    autoSyncConnectedServices: true,
    desktopNotifications: false,
    automationRules: [],
    lastRunAt: "",
  };
}

function normalizeAutomationConfig(raw?: Record<string, unknown> | null): DesktopAutomationSettings {
  const base = createDefaultAutomationSettings();
  const config = raw || {};
  return {
    enabled: typeof config.enabled === "boolean" ? config.enabled : base.enabled,
    autoSyncConnectedServices: typeof config.autoSyncConnectedServices === "boolean" ? config.autoSyncConnectedServices : base.autoSyncConnectedServices,
    desktopNotifications: typeof config.desktopNotifications === "boolean" ? config.desktopNotifications : base.desktopNotifications,
    automationRules: normalizeAutomationRules(config.automationRules),
    lastRunAt: String(config.lastRunAt || ""),
  };
}

function assignAutomationField<K extends keyof DesktopAutomationSettings>(
  target: DesktopAutomationSettings,
  source: DesktopAutomationSettings,
  field: K,
) {
  (target as Record<string, unknown>)[String(field)] = source[field];
}

function normalizeSettingsTab(value: string | null): SettingsTab {
  if (value === "appearance" || value === "gorunum") {
    return "gorunum";
  }
  if (value === "profile" || value === "profil" || value === "ben") {
    return "profil";
  }
  if (value === "communication" || value === "iletisim") {
    return "iletisim";
  }
  if (value === "assistant") {
    return "assistant";
  }
  if (value === "system" || value === "automation") {
    return "automation";
  }
  return "kurulum";
}

function automationModeLabel(mode: string) {
  const normalized = String(mode || "").trim().toLowerCase();
  if (normalized === "reminder") {
    return "Hatırlatma";
  }
  if (normalized === "auto_reply") {
    return sozluk.settings.automationRuleModeAutoReply;
  }
  if (normalized === "notify") {
    return sozluk.settings.automationRuleModeNotify;
  }
  return sozluk.settings.automationRuleModeCustom;
}

function automationChannelLabel(channel: string) {
  const normalized = String(channel || "").trim().toLowerCase();
  if (normalized === "whatsapp") {
    return "WhatsApp";
  }
  if (normalized === "telegram") {
    return "Telegram";
  }
  if (normalized === "email" || normalized === "outlook") {
    return "E-posta";
  }
  if (normalized === "calendar") {
    return "Takvim";
  }
  if (normalized === "x") {
    return "X";
  }
  return normalized ? normalized[0].toLocaleUpperCase("tr-TR") + normalized.slice(1) : "Genel";
}

function automationLastRunLabel(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value || sozluk.common.notRecorded;
  }
  return parsed.toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

function automationReminderLabel(value?: string) {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

function automationPadNumber(value: number) {
  return String(value).padStart(2, "0");
}

function automationDateTimeInputValue(value?: string) {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) {
    return "";
  }
  return [
    parsed.getFullYear(),
    automationPadNumber(parsed.getMonth() + 1),
    automationPadNumber(parsed.getDate()),
  ].join("-")
    + `T${automationPadNumber(parsed.getHours())}:${automationPadNumber(parsed.getMinutes())}`;
}

function automationDateTimeFromInput(value: string) {
  const parsed = new Date(value);
  if (!value || Number.isNaN(parsed.getTime())) {
    return "";
  }
  const offsetMinutes = -parsed.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteOffset = Math.abs(offsetMinutes);
  const offsetHours = automationPadNumber(Math.floor(absoluteOffset / 60));
  const offsetRemainder = automationPadNumber(absoluteOffset % 60);
  return [
    parsed.getFullYear(),
    automationPadNumber(parsed.getMonth() + 1),
    automationPadNumber(parsed.getDate()),
  ].join("-")
    + `T${automationPadNumber(parsed.getHours())}:${automationPadNumber(parsed.getMinutes())}:00${sign}${offsetHours}:${offsetRemainder}`;
}

type SetupGroupId = "provider" | "mail-calendar" | "messaging" | "social" | "data-sources";

function setupGroupFromSection(sectionId: string | null): SetupGroupId | null {
  const normalized = String(sectionId || "").trim();
  if (!normalized) {
    return null;
  }
  if (normalized === "integration-provider") {
    return "provider";
  }
  if (["integration-google", "integration-outlook"].includes(normalized)) {
    return "mail-calendar";
  }
  if (["integration-telegram", "integration-whatsapp"].includes(normalized)) {
    return "messaging";
  }
  if (["integration-x", "integration-instagram", "integration-linkedin"].includes(normalized)) {
    return "social";
  }
  if (["integration-elastic", "integration-postgresql", "integration-mysql", "integration-mssql"].includes(normalized)) {
    return "data-sources";
  }
  return null;
}

export function SettingsPage() {
  const { settings, setSettings, setWorkspace, setCurrentMatter } = useAppContext();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handledSectionScrollRef = useRef<string | null>(null);
  const loadedSurfacesRef = useRef({
    base: false,
    profile: false,
    contacts: false,
    assistant: false,
    desktop: false,
  });

  async function handleCustomWallpaperUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      const base64 = event.target?.result as string;
      if (base64) {
        await saveCustomWallpaper(base64);
      }
    };
    reader.readAsDataURL(file);
  }
  const [activeTab, setActiveTab] = useState<SettingsTab>(() => normalizeSettingsTab(searchParams.get("tab")));
  const [expandedSetupGroups, setExpandedSetupGroups] = useState<SetupGroupId[]>(() => {
    const initialGroup = setupGroupFromSection(searchParams.get("section"));
    return initialGroup ? [initialGroup] : [];
  });
  const [workspace, setWorkspaceOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [profile, setProfile] = useState<UserProfile>(() => normalizeProfile(settings.officeId, readCachedSettingsValue<UserProfile>(PROFILE_CACHE_KEY)));
  const [contactProfiles, setContactProfiles] = useState<AssistantContactProfile[]>([]);
  const [editingContactDescriptions, setEditingContactDescriptions] = useState<Record<string, boolean>>({});
  const [contactDescriptionDrafts, setContactDescriptionDrafts] = useState<Record<string, string>>({});
  const [assistantRuntimeCore, setAssistantRuntimeCore] = useState<AssistantCoreStatus | null>(null);
  const [assistantRuntimeProfile, setAssistantRuntimeProfile] = useState<AssistantRuntimeProfile>(() => (
    normalizeAssistantRuntimeProfile(settings.officeId, readCachedSettingsValue<AssistantRuntimeProfile>(ASSISTANT_RUNTIME_CACHE_KEY))
  ));
  const [customAssistantFormDraft, setCustomAssistantFormDraft] = useState<CustomAssistantFormDraft>(createEmptyCustomAssistantFormDraft);
  const [assistantBlueprintPrompt, setAssistantBlueprintPrompt] = useState("");
  const [assistantBlueprintPreview, setAssistantBlueprintPreview] = useState<AssistantCoreBlueprint | null>(null);
  const [automationSettings, setAutomationSettings] = useState<DesktopAutomationSettings>(createDefaultAutomationSettings());
  const [desktopUpdateDraft, setDesktopUpdateDraft] = useState<DesktopUpdateDraft>(createDefaultDesktopUpdateDraft);
  const [desktopUpdateStatus, setDesktopUpdateStatus] = useState<DesktopUpdateStatus>(() => normalizeDesktopUpdateStatus({}));
  const automationDirtyFieldsRef = useRef<Set<keyof DesktopAutomationSettings>>(new Set());
  const [error, setError] = useState("");
  const [desktopConfigSaved, setDesktopConfigSaved] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [assistantRuntimeMessage, setAssistantRuntimeMessage] = useState("");
  const [automationMessage, setAutomationMessage] = useState("");
  const [desktopUpdateMessage, setDesktopUpdateMessage] = useState("");
  const [locationCaptureMessage, setLocationCaptureMessage] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [savingContactDescriptionId, setSavingContactDescriptionId] = useState<string | null>(null);
  const [isSavingAssistantRuntime, setIsSavingAssistantRuntime] = useState(false);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [isSavingDesktopUpdate, setIsSavingDesktopUpdate] = useState(false);
  const [isCheckingDesktopUpdate, setIsCheckingDesktopUpdate] = useState(false);
  const [isDownloadingDesktopUpdate, setIsDownloadingDesktopUpdate] = useState(false);
  const [isInstallingDesktopUpdate, setIsInstallingDesktopUpdate] = useState(false);
  const [isRefreshingLocation, setIsRefreshingLocation] = useState(false);
  const [isGeneratingAssistantBlueprint, setIsGeneratingAssistantBlueprint] = useState(false);
  const autoLocationAttemptedRef = useRef(false);
  const desktopReady = Boolean(window.lawcopilotDesktop);
  const selectedWorkspacePath = workspace?.workspace?.root_path || settings.workspaceRootPath;
  const selectedWorkspaceName = settings.workspaceRootName || workspace?.workspace?.display_name || sozluk.settings.workspaceTitle;
  const assistantFormCatalog = (Array.isArray(assistantRuntimeCore?.form_catalog) && assistantRuntimeCore?.form_catalog?.length
    ? assistantRuntimeCore.form_catalog
    : ASSISTANT_FORM_PRESETS.map((item) => ({ ...item })));
  const assistantCapabilityCatalog = (Array.isArray(assistantRuntimeCore?.capability_catalog) && assistantRuntimeCore?.capability_catalog?.length
    ? assistantRuntimeCore.capability_catalog
    : ASSISTANT_CAPABILITY_FALLBACK);
  const assistantSurfaceCatalog = (Array.isArray(assistantRuntimeCore?.surface_catalog) && assistantRuntimeCore?.surface_catalog?.length
    ? assistantRuntimeCore.surface_catalog
    : ASSISTANT_SURFACE_FALLBACK);
  const assistantTransformationExamples = Array.isArray(assistantRuntimeCore?.transformation_examples)
    ? assistantRuntimeCore.transformation_examples
    : [];
  const sortedContactProfiles = useMemo(
    () => [...contactProfiles].sort((left, right) => {
      const closenessDelta = normalizeCloseness(right.closeness, 0) - normalizeCloseness(left.closeness, 0);
      if (closenessDelta !== 0) {
        return closenessDelta;
      }
      return String(left.display_name || "").localeCompare(String(right.display_name || ""), "tr");
    }),
    [contactProfiles],
  );
  const watchedRuleCount = profile.inbox_watch_rules.length;
  const keywordRuleCount = profile.inbox_keyword_rules.length;
  const blockedRuleCount = profile.inbox_block_rules.length;

  async function refreshSettingsSurface(options?: {
    force?: boolean;
    includeBase?: boolean;
    includeProfile?: boolean;
    includeContacts?: boolean;
    includeAssistant?: boolean;
    includeDesktop?: boolean;
  }) {
    const force = Boolean(options?.force);
    const shouldLoadProfile = activeTab === "profil" || activeTab === "iletisim";
    const shouldLoadAssistantRuntime = activeTab === "assistant";
    const includeBase = options?.includeBase ?? (force || !loadedSurfacesRef.current.base);
    const includeProfile = options?.includeProfile ?? (shouldLoadProfile && (force || !loadedSurfacesRef.current.profile));
    const includeContacts = options?.includeContacts ?? (shouldLoadProfile && (force || !loadedSurfacesRef.current.contacts));
    const includeAssistant = options?.includeAssistant ?? (shouldLoadAssistantRuntime && (force || !loadedSurfacesRef.current.assistant));
    const includeDesktop = options?.includeDesktop ?? (desktopReady && (force || !loadedSurfacesRef.current.desktop));

    const [healthResponse, workspaceResponse, userProfileResponse, runtimeProfileResponse, runtimeCoreResponse, contactProfilesResponse, storedConfig, updateStatusResponse] = await Promise.all([
      includeBase ? getHealth(settings) : Promise.resolve(null),
      includeBase ? getWorkspaceOverview(settings) : Promise.resolve(null),
      includeProfile ? getUserProfile(settings).catch(() => null) : Promise.resolve(null),
      includeAssistant ? getAssistantRuntimeProfile(settings).catch(() => null) : Promise.resolve(null),
      includeAssistant ? getAssistantRuntimeCore(settings).catch(() => null) : Promise.resolve(null),
      includeContacts ? getAssistantContactProfiles(settings).catch(() => null) : Promise.resolve(null),
      includeDesktop ? window.lawcopilotDesktop?.getStoredConfig?.().catch(() => ({})) : Promise.resolve(null),
      includeDesktop ? window.lawcopilotDesktop?.getUpdateStatus?.().catch(() => ({})) : Promise.resolve(null),
    ]);

    if (workspaceResponse) {
      setWorkspaceOverview(workspaceResponse);
      loadedSurfacesRef.current.base = true;
    }
    if (userProfileResponse) {
      const nextOfficeId = healthResponse?.office_id || settings.officeId;
      const nextProfile = normalizeProfile(nextOfficeId, userProfileResponse);
      setProfile(nextProfile);
      writeCachedSettingsValue(PROFILE_CACHE_KEY, nextProfile);
      loadedSurfacesRef.current.profile = true;
    }
    if (contactProfilesResponse?.items) {
      setContactProfiles(contactProfilesResponse.items);
      loadedSurfacesRef.current.contacts = true;
    }
    if (runtimeProfileResponse) {
      const nextOfficeId = healthResponse?.office_id || settings.officeId;
      const nextAssistantRuntimeProfile = normalizeAssistantRuntimeProfile(nextOfficeId, runtimeProfileResponse);
      setAssistantRuntimeProfile(nextAssistantRuntimeProfile);
      writeCachedSettingsValue(ASSISTANT_RUNTIME_CACHE_KEY, nextAssistantRuntimeProfile);
    }
    if (runtimeCoreResponse || runtimeProfileResponse) {
      if (runtimeCoreResponse) {
        setAssistantRuntimeCore(runtimeCoreResponse);
      }
      loadedSurfacesRef.current.assistant = true;
    }
    if (storedConfig) {
      const nextAutomationSettings = normalizeAutomationConfig((storedConfig as Record<string, unknown>)?.automation as Record<string, unknown> | undefined);
      setAutomationSettings((current) => {
        const dirtyFields = automationDirtyFieldsRef.current;
        if (!dirtyFields.size) {
          return nextAutomationSettings;
        }
        const merged: DesktopAutomationSettings = { ...nextAutomationSettings };
        dirtyFields.forEach((field) => {
          assignAutomationField(merged, current, field);
        });
        return merged;
      });
      setDesktopUpdateDraft(normalizeDesktopUpdateDraft((storedConfig as Record<string, unknown>)?.updater as Record<string, unknown> | undefined));
      loadedSurfacesRef.current.desktop = true;
    }
    if (updateStatusResponse) {
      setDesktopUpdateStatus(normalizeDesktopUpdateStatus(updateStatusResponse as Record<string, unknown> | undefined));
      loadedSurfacesRef.current.desktop = true;
    }
    if (healthResponse) {
      setSettings({
        deploymentMode: healthResponse.deployment_mode,
        officeId: healthResponse.office_id,
        releaseChannel: healthResponse.release_channel || settings.releaseChannel,
        selectedModelProfile: healthResponse.default_model_profile || settings.selectedModelProfile,
      });
      setWorkspace({
        workspaceConfigured: Boolean(healthResponse.workspace_configured),
        workspaceRootName: String(healthResponse.workspace_root_name || settings.workspaceRootName),
        workspaceRootPath: workspaceResponse?.workspace?.root_path || settings.workspaceRootPath,
        workspaceRootHash: workspaceResponse?.workspace?.root_path_hash || settings.workspaceRootHash,
      });
    }
    const shouldReturnToAssistant = activeTab === "kurulum" && searchParams.get("return_to") === "assistant";
    if (shouldReturnToAssistant && Boolean(healthResponse?.provider_configured) && Boolean(healthResponse?.provider_model)) {
      navigate("/assistant", { replace: true });
      return;
    }
    setError("");
  }

  useEffect(() => {
    refreshSettingsSurface().catch((err: Error) => setError(err.message));
  }, [activeTab, desktopReady, settings.baseUrl, settings.token]);

  useEffect(() => {
    if (!desktopReady || !window.lawcopilotDesktop?.onUpdateStatus) {
      return;
    }
    const dispose = window.lawcopilotDesktop.onUpdateStatus((payload) => {
      setDesktopUpdateStatus(normalizeDesktopUpdateStatus(payload));
      setDesktopUpdateDraft((current) => ({
        ...current,
        ...normalizeDesktopUpdateDraft(payload),
      }));
    });
    return () => {
      if (typeof dispose === "function") {
        dispose();
      }
    };
  }, [desktopReady]);

  useEffect(() => {
    if (activeTab !== "profil" || autoLocationAttemptedRef.current) {
      return;
    }
    if (typeof navigator === "undefined" || !navigator.geolocation || !navigator.permissions?.query) {
      return;
    }
    autoLocationAttemptedRef.current = true;
    navigator.permissions.query({ name: "geolocation" as PermissionName })
      .then((result) => {
        if (result.state === "granted") {
          void captureCurrentLocation({ silent: true });
        }
      })
      .catch(() => {
        return;
      });
  }, [activeTab]);

  useEffect(() => {
    const requestedTab = searchParams.get("tab");
    const normalizedTab = normalizeSettingsTab(requestedTab);
    if (activeTab !== normalizedTab) {
      setActiveTab(normalizedTab);
    }
    if (requestedTab && requestedTab !== normalizedTab) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("tab", normalizedTab);
      setSearchParams(nextParams, { replace: true });
    }
  }, [activeTab, searchParams, setSearchParams]);

  useEffect(() => {
    const sectionId = searchParams.get("section");
    if (!sectionId) {
      handledSectionScrollRef.current = null;
      return;
    }
    if (handledSectionScrollRef.current === sectionId) {
      return;
    }
    const element = document.getElementById(sectionId);
    if (!element) {
      return;
    }
    const frameId = window.requestAnimationFrame(() => {
      if (typeof element.scrollIntoView === "function") {
        element.scrollIntoView({ block: "start", behavior: "smooth" });
      }
      handledSectionScrollRef.current = sectionId;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [activeTab, searchParams, expandedSetupGroups]);

  useEffect(() => {
    if (activeTab !== "kurulum") {
      return;
    }
    const group = setupGroupFromSection(searchParams.get("section"));
    if (!group) {
      return;
    }
    setExpandedSetupGroups((current) => (current.includes(group) ? current : [...current, group]));
  }, [activeTab, searchParams]);

  function toggleSetupGroup(groupId: SetupGroupId) {
    setExpandedSetupGroups((current) => (
      current.includes(groupId)
        ? current.filter((item) => item !== groupId)
        : [...current, groupId]
    ));
  }

  async function saveThemeMode(mode: "system" | "light" | "dark") {
    setSettings({ themeMode: mode });
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      return;
    }
    try {
      await window.lawcopilotDesktop.saveStoredConfig({ themeMode: mode });
      setDesktopConfigSaved(sozluk.settings.themeSaved);
    } catch {
      setDesktopConfigSaved(sozluk.settings.desktopModeSaveError);
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const handleMemoryUpdate = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail as { kinds?: string[] } | undefined : undefined;
      const kinds = new Set((detail?.kinds || []).map((item) => String(item || "").trim()));
      if (!kinds.size) {
        return;
      }
      if (kinds.has("profile_signal")) {
        loadedSurfacesRef.current.profile = false;
        loadedSurfacesRef.current.contacts = false;
      }
      if (kinds.has("assistant_persona_signal")) {
        loadedSurfacesRef.current.assistant = false;
      }
      if (
        activeTab === "profil"
        || activeTab === "iletisim"
        || activeTab === "assistant"
      ) {
        void refreshSettingsSurface({
          force: true,
          includeProfile: kinds.has("profile_signal"),
          includeContacts: kinds.has("profile_signal"),
          includeAssistant: kinds.has("assistant_persona_signal"),
        }).catch(() => null);
      }
    };
    window.addEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    return () => {
      window.removeEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    };
  }, [activeTab, settings.officeId]);

  useEffect(() => {
    if (typeof window === "undefined" || !["profil", "iletisim"].includes(activeTab)) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      if (document.hidden) {
        return;
      }
      void refreshSettingsSurface({
        force: true,
        includeProfile: true,
        includeContacts: true,
      }).catch(() => null);
    }, SETTINGS_CONTACT_REFRESH_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeTab, settings.baseUrl, settings.token]);

  async function saveThemeAccent(accent: string) {
    setSettings({ themeAccent: accent });
    if (!window.lawcopilotDesktop?.saveStoredConfig) return;
    try { await window.lawcopilotDesktop.saveStoredConfig({ themeAccent: accent }); } catch {}
  }

  async function saveChatFontSize(size: string) {
    setSettings({ chatFontSize: size });
    if (!window.lawcopilotDesktop?.saveStoredConfig) return;
    try { await window.lawcopilotDesktop.saveStoredConfig({ chatFontSize: size }); } catch {}
  }

  async function saveChatWallpaper(wallpaper: string) {
    setSettings({ chatWallpaper: wallpaper });
    if (!window.lawcopilotDesktop?.saveStoredConfig) return;
    try { await window.lawcopilotDesktop.saveStoredConfig({ chatWallpaper: wallpaper }); } catch {}
  }

  async function saveCustomWallpaper(base64: string) {
    setSettings({ customWallpaper: base64, chatWallpaper: "custom" });
    if (!window.lawcopilotDesktop?.saveStoredConfig) return;
    try { await window.lawcopilotDesktop.saveStoredConfig({ customWallpaper: base64, chatWallpaper: "custom" }); } catch {}
  }

  async function chooseWorkspaceRoot() {
    if (!window.lawcopilotDesktop?.chooseWorkspaceRoot) {
      setError(sozluk.settings.desktopOnlyChoose);
      return;
    }
    try {
      const response = await window.lawcopilotDesktop.chooseWorkspaceRoot();
      if ((response as { canceled?: boolean }).canceled) {
        return;
      }
      const chosen = (response as { workspace?: Record<string, unknown> }).workspace || {};
      const workspaceRootPath = String(chosen.workspaceRootPath || "");
      const workspaceRootName = String(chosen.workspaceRootName || "").trim() || workspaceRootPath || sozluk.settings.workspaceTitle;
      setWorkspace({
        workspaceConfigured: Boolean(workspaceRootPath),
        workspaceRootName,
        workspaceRootPath,
        workspaceRootHash: String(chosen.workspaceRootHash || ""),
      });
      setCurrentMatter(null, "");
      setError("");
      const savedMessage = sozluk.settings.workspaceSavedWithName.replace("{name}", workspaceRootName);
      setDesktopConfigSaved(savedMessage);
      try {
        await refreshSettingsSurface({ force: true, includeBase: true, includeDesktop: true });
      } catch {
        setDesktopConfigSaved([savedMessage, sozluk.settings.workspaceRefreshPending].join(" "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.workspaceChangeError);
    }
  }

  function updateAutomationField<K extends keyof DesktopAutomationSettings>(field: K, value: DesktopAutomationSettings[K]) {
    setAutomationSettings((current) => ({ ...current, [field]: value }));
    automationDirtyFieldsRef.current = new Set(automationDirtyFieldsRef.current).add(field);
    setAutomationMessage("");
  }

  function updateAutomationRule(ruleId: string, patch: Partial<DesktopAutomationRule>) {
    setAutomationSettings((current) => ({
      ...current,
      automationRules: normalizeAutomationRules(
        current.automationRules.map((rule) => (rule.id === ruleId ? { ...rule, ...patch } : rule)),
      ),
    }));
    automationDirtyFieldsRef.current = new Set(automationDirtyFieldsRef.current).add("automationRules");
    setAutomationMessage("");
  }

  function removeAutomationRule(ruleId: string) {
    setAutomationSettings((current) => ({
      ...current,
      automationRules: current.automationRules.filter((rule) => rule.id !== ruleId),
    }));
    automationDirtyFieldsRef.current = new Set(automationDirtyFieldsRef.current).add("automationRules");
    setAutomationMessage("");
  }

  async function saveAutomationConfiguration() {
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      setAutomationMessage(sozluk.settings.automationDesktopOnly);
      return;
    }
    setIsSavingAutomation(true);
    try {
      const saved = await window.lawcopilotDesktop.saveStoredConfig({
        automation: {
          enabled: automationSettings.enabled,
          autoSyncConnectedServices: true,
          desktopNotifications: true,
          automationRules: automationSettings.automationRules,
        },
      });
      automationDirtyFieldsRef.current = new Set();
      setAutomationSettings(normalizeAutomationConfig((saved as Record<string, unknown>)?.automation as Record<string, unknown> | undefined));
      setAutomationMessage(sozluk.settings.automationSaved);
    } catch {
      setAutomationMessage(sozluk.settings.automationSaveError);
    } finally {
      setIsSavingAutomation(false);
    }
  }

  function updateDesktopUpdateField<K extends keyof DesktopUpdateDraft>(field: K, value: DesktopUpdateDraft[K]) {
    setDesktopUpdateDraft((current) => ({ ...current, [field]: value }));
    setDesktopUpdateMessage("");
  }

  async function saveDesktopUpdateConfiguration() {
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDesktopOnlyDescription);
      return;
    }
    setIsSavingDesktopUpdate(true);
    try {
      const saved = await window.lawcopilotDesktop.saveStoredConfig({
        updater: {
          enabled: desktopUpdateDraft.enabled,
          feedUrl: desktopUpdateDraft.feedUrl,
          channel: desktopUpdateDraft.channel,
          autoCheckOnLaunch: desktopUpdateDraft.autoCheckOnLaunch,
          autoDownload: desktopUpdateDraft.autoDownload,
          allowPrerelease: desktopUpdateDraft.allowPrerelease,
        },
      });
      setDesktopUpdateDraft(normalizeDesktopUpdateDraft((saved as Record<string, unknown>)?.updater as Record<string, unknown> | undefined));
      if (window.lawcopilotDesktop?.getUpdateStatus) {
        const status = await window.lawcopilotDesktop.getUpdateStatus();
        setDesktopUpdateStatus(normalizeDesktopUpdateStatus(status as Record<string, unknown> | undefined));
      }
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateSaved);
    } catch {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateSaveError);
    } finally {
      setIsSavingDesktopUpdate(false);
    }
  }

  async function checkDesktopUpdates() {
    if (!window.lawcopilotDesktop?.checkForUpdates) {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDesktopOnlyDescription);
      return;
    }
    setIsCheckingDesktopUpdate(true);
    setDesktopUpdateMessage("");
    try {
      const status = await window.lawcopilotDesktop.checkForUpdates();
      setDesktopUpdateStatus(normalizeDesktopUpdateStatus(status as Record<string, unknown> | undefined));
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateCheckStarted);
    } catch {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateCheckError);
    } finally {
      setIsCheckingDesktopUpdate(false);
    }
  }

  async function downloadDesktopUpdate() {
    if (!window.lawcopilotDesktop?.downloadUpdate) {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDesktopOnlyDescription);
      return;
    }
    setIsDownloadingDesktopUpdate(true);
    setDesktopUpdateMessage("");
    try {
      const status = await window.lawcopilotDesktop.downloadUpdate();
      setDesktopUpdateStatus(normalizeDesktopUpdateStatus(status as Record<string, unknown> | undefined));
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDownloadStarted);
    } catch {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDownloadError);
    } finally {
      setIsDownloadingDesktopUpdate(false);
    }
  }

  async function installDesktopUpdate() {
    if (!window.lawcopilotDesktop?.quitAndInstallUpdate) {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateDesktopOnlyDescription);
      return;
    }
    setIsInstallingDesktopUpdate(true);
    try {
      const result = await window.lawcopilotDesktop.quitAndInstallUpdate();
      const payload = (result || {}) as Record<string, unknown>;
      if (payload.ok) {
        setDesktopUpdateMessage(sozluk.settings.desktopUpdateInstallStarted);
        return;
      }
      setDesktopUpdateStatus(normalizeDesktopUpdateStatus(payload.status as Record<string, unknown> | undefined));
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateInstallUnavailable);
    } catch {
      setDesktopUpdateMessage(sozluk.settings.desktopUpdateInstallError);
    } finally {
      setIsInstallingDesktopUpdate(false);
    }
  }

  function updateProfileField(field: keyof UserProfile, value: string) {
    setProfile((current) => ({ ...current, [field]: value }));
    setProfileMessage("");
    if (field !== "current_location") {
      setLocationCaptureMessage("");
    }
  }

  function defaultNearbyPreferenceCategories() {
    return ["cafe", "restaurant", "coworking", "historic_site", "transit", "nightlife"];
  }

  function formatCurrentLocationLabel(currentPlace: Record<string, unknown> | null | undefined) {
    const place = currentPlace || {};
    const label = String(place.label || "").trim();
    if (label) {
      return label;
    }
    const area = String(place.area || "").trim();
    const city = String((place.city as string | undefined) || "").trim();
    if (area && city && !area.includes(city)) {
      return `${city} / ${area}`;
    }
    if (area) {
      return area;
    }
    const latitude = Number(place.latitude || 0);
    const longitude = Number(place.longitude || 0);
    if (Number.isFinite(latitude) && Number.isFinite(longitude) && latitude !== 0 && longitude !== 0) {
      return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
    }
    return "";
  }

  async function captureCurrentLocation(options: { silent?: boolean } = {}) {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      if (!options.silent) {
        setLocationCaptureMessage("Bu cihazda konum erişimi kullanılamıyor.");
      }
      return;
    }
    setIsRefreshingLocation(true);
    setLocationCaptureMessage("");
    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 12000,
          maximumAge: 300000,
        });
      });
      const observedAt = new Date(position.timestamp || Date.now()).toISOString();
      const payload: {
        current_place: Record<string, unknown>;
        recent_places: Array<Record<string, unknown>>;
        nearby_categories: string[];
        observed_at: string;
        source: string;
        scope: string;
        sensitivity: string;
        persist_raw: boolean;
        provider: string;
        provider_mode: string;
        provider_status: string;
        capture_mode: string;
        permission_state: string;
        privacy_mode: boolean;
      } = {
        current_place: {
          place_id: `device-${position.coords.latitude.toFixed(4)}-${position.coords.longitude.toFixed(4)}`,
          label: "Cihaz konumu",
          category: "device_location",
          area: profile.current_location || profile.home_base || "",
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_meters: position.coords.accuracy,
          observed_at: observedAt,
          started_at: observedAt,
          scope: "personal",
          sensitivity: "high",
          captured_via: "browser_geolocation",
          tags: ["device_capture"],
        },
        recent_places: [],
        nearby_categories: defaultNearbyPreferenceCategories(),
        observed_at: observedAt,
        source: "browser_geolocation",
        scope: "personal",
        sensitivity: "high",
        persist_raw: true,
        provider: "desktop_browser_capture_v1",
        provider_mode: "desktop_renderer_geolocation",
        provider_status: "fresh",
        capture_mode: "device_capture",
        permission_state: "granted",
        privacy_mode: false,
      };
      const response = await updateAssistantLocationContext(settings, payload);
      const nextLabel = formatCurrentLocationLabel(
        (response as { location_context?: { current_place?: Record<string, unknown> } } | null)?.location_context?.current_place
          || payload.current_place,
      );
      if (nextLabel) {
        setProfile((current) => ({ ...current, current_location: nextLabel }));
      }
      if (!options.silent) {
        setLocationCaptureMessage(nextLabel ? "Canlı konum cihazdan güncellendi." : "Konum alındı.");
      }
      setError("");
      setProfileMessage("");
    } catch (err) {
      const code = Number((err as { code?: number } | null)?.code || 0);
      let message = err instanceof Error ? err.message : "Konum alınamadı.";
      if (code === 1) {
        message = "Konum izni reddedildi.";
      } else if (code === 2) {
        message = "Konum şu anda alınamadı.";
      } else if (code === 3) {
        message = "Konum alma isteği zaman aşımına uğradı.";
      }
      setLocationCaptureMessage(message);
    } finally {
      setIsRefreshingLocation(false);
    }
  }

  function addImportantDate() {
    setProfile((current) => ({
      ...current,
      important_dates: [...current.important_dates, createEmptyImportantDate()],
    }));
    setProfileMessage("");
  }

  function updateImportantDate(index: number, patch: Partial<ProfileImportantDate>) {
    setProfile((current) => ({
      ...current,
      important_dates: current.important_dates.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }));
    setProfileMessage("");
  }

  function removeImportantDate(index: number) {
    setProfile((current) => ({
      ...current,
      important_dates: current.important_dates.filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function addRelatedProfile() {
    setProfile((current) => ({ ...current, related_profiles: [...current.related_profiles, createEmptyRelatedProfile()] }));
    setProfileMessage("");
  }

  function removeRelatedProfile(index: number) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function updateRelatedProfileField(index: number, field: "name" | "relationship" | "preferences" | "notes", value: string) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => (
        itemIndex === index
          ? {
            ...item,
            [field]: value,
            ...(field === "relationship" && (!item.closeness || item.closeness === inferRelationshipCloseness(String(item.relationship || "")))
              ? { closeness: inferRelationshipCloseness(value) }
              : {}),
          }
          : item
      )),
    }));
    setProfileMessage("");
  }

  function updateRelatedProfileCloseness(index: number, value: number) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => (
        itemIndex === index ? { ...item, closeness: normalizeCloseness(value, 3) } : item
      )),
    }));
    setProfileMessage("");
  }

  function addRelatedProfileImportantDate(index: number) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => (
        itemIndex === index ? { ...item, important_dates: [...item.important_dates, createEmptyImportantDate()] } : item
      )),
    }));
    setProfileMessage("");
  }

  function updateRelatedProfileImportantDate(index: number, dateIndex: number, patch: Partial<ProfileImportantDate>) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => {
        if (itemIndex !== index) {
          return item;
        }
        return {
          ...item,
          important_dates: item.important_dates.map((dateItem, currentDateIndex) => (
            currentDateIndex === dateIndex ? { ...dateItem, ...patch } : dateItem
          )),
        };
      }),
    }));
    setProfileMessage("");
  }

  function removeRelatedProfileImportantDate(index: number, dateIndex: number) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => (
        itemIndex === index
          ? { ...item, important_dates: item.important_dates.filter((_, currentDateIndex) => currentDateIndex !== dateIndex) }
          : item
      )),
    }));
    setProfileMessage("");
  }

  function upsertRelatedProfileFromContact(contact: AssistantContactProfile) {
    setProfile((current) => {
      const existingIndex = current.related_profiles.findIndex((item) => {
        const relatedId = String(item.id || "").trim();
        const linkedId = String(contact.related_profile_id || "").trim();
        if (linkedId && relatedId && linkedId === relatedId) {
          return true;
        }
        return String(item.name || "").trim().toLocaleLowerCase("tr-TR") === String(contact.display_name || "").trim().toLocaleLowerCase("tr-TR");
      });

      const relationship = String(contact.relationship_hint || "").trim();
      const closeness = normalizeCloseness(contact.closeness, inferRelationshipCloseness(relationship));
      const suggestedNotes = String(contact.persona_detail || contact.persona_summary || "").trim();

      const candidate: RelatedProfile = {
        id: String(contact.related_profile_id || "").trim() || `related-${contact.id}`,
        source: "manual",
        name: String(contact.display_name || "").trim(),
        relationship: relationship && relationship !== "İletişim kişisi" ? relationship : "",
        closeness,
        preferences: "",
        notes: suggestedNotes,
        important_dates: [],
      };

      if (existingIndex === -1) {
        return { ...current, related_profiles: [...current.related_profiles, candidate] };
      }

      return {
        ...current,
        related_profiles: current.related_profiles.map((item, index) => (
          index === existingIndex
            ? {
              ...item,
              source: item.source || candidate.source,
              id: item.id || candidate.id,
              name: item.name || candidate.name,
              relationship: item.relationship || candidate.relationship,
              closeness: normalizeCloseness(item.closeness, closeness),
              notes: item.notes || candidate.notes,
            }
            : item
        )),
      };
    });
    setProfileMessage("");
  }

  function beginEditContactDescription(contact: AssistantContactProfile) {
    const initialDraft = String(contact.persona_detail || contact.generated_persona_detail || contact.persona_summary || "").trim();
    setEditingContactDescriptions((current) => ({ ...current, [contact.id]: true }));
    setContactDescriptionDrafts((current) => ({ ...current, [contact.id]: initialDraft }));
    setProfileMessage("");
  }

  function cancelEditContactDescription(contactId: string) {
    setEditingContactDescriptions((current) => ({ ...current, [contactId]: false }));
    setContactDescriptionDrafts((current) => {
      const next = { ...current };
      delete next[contactId];
      return next;
    });
  }

  function updateContactDescriptionDraft(contactId: string, value: string) {
    setContactDescriptionDrafts((current) => ({ ...current, [contactId]: value }));
    setProfileMessage("");
  }

  async function saveContactDescription(contact: AssistantContactProfile) {
    const nextDescription = String(contactDescriptionDrafts[contact.id] || "").trim();
    const updatedAt = nextDescription ? new Date().toISOString() : null;
    const nextOverrides = [
      ...profile.contact_profile_overrides.filter((item) => item.contact_id !== contact.id),
      ...(nextDescription ? [{ contact_id: contact.id, description: nextDescription, updated_at: updatedAt }] : []),
    ];
    const draftProfile = normalizeProfile(settings.officeId, {
      ...profile,
      contact_profile_overrides: nextOverrides,
    });

    setSavingContactDescriptionId(contact.id);
    try {
      const response = await saveUserProfile(settings, buildUserProfilePayload(draftProfile));
      const nextProfile = normalizeProfile(settings.officeId, response.profile);
      setProfile(nextProfile);
      writeCachedSettingsValue(PROFILE_CACHE_KEY, nextProfile);
      setContactProfiles((current) => current.map((item) => {
        if (item.id !== contact.id) {
          return item;
        }
        const fallbackDetail = String(item.generated_persona_detail || item.persona_summary || "").trim();
        return {
          ...item,
          persona_detail: nextDescription || fallbackDetail,
          persona_detail_source: nextDescription ? "manual" : "generated",
          persona_detail_updated_at: updatedAt,
        };
      }));
      setEditingContactDescriptions((current) => ({ ...current, [contact.id]: false }));
      setContactDescriptionDrafts((current) => {
        const next = { ...current };
        delete next[contact.id];
        return next;
      });
      setProfileMessage(nextDescription ? "İletişim açıklaması kaydedildi." : "Manuel iletişim açıklaması kaldırıldı.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "İletişim açıklaması kaydedilemedi.");
    } finally {
      setSavingContactDescriptionId(null);
    }
  }

  function addWatchRule() {
    setProfile((current) => ({ ...current, inbox_watch_rules: [...current.inbox_watch_rules, createEmptyWatchRule()] }));
    setProfileMessage("");
  }

  function updateWatchRule(index: number, patch: Partial<InboxWatchRule>) {
    setProfile((current) => ({
      ...current,
      inbox_watch_rules: current.inbox_watch_rules.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }));
    setProfileMessage("");
  }

  function removeWatchRule(index: number) {
    setProfile((current) => ({
      ...current,
      inbox_watch_rules: current.inbox_watch_rules.filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function addKeywordRule() {
    setProfile((current) => ({ ...current, inbox_keyword_rules: [...current.inbox_keyword_rules, createEmptyKeywordRule()] }));
    setProfileMessage("");
  }

  function updateKeywordRule(index: number, patch: Partial<InboxKeywordRule>) {
    setProfile((current) => ({
      ...current,
      inbox_keyword_rules: current.inbox_keyword_rules.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }));
    setProfileMessage("");
  }

  function removeKeywordRule(index: number) {
    setProfile((current) => ({
      ...current,
      inbox_keyword_rules: current.inbox_keyword_rules.filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function addBlockRule() {
    setProfile((current) => ({ ...current, inbox_block_rules: [...current.inbox_block_rules, createEmptyBlockRule()] }));
    setProfileMessage("");
  }

  function updateBlockRule(index: number, patch: Partial<InboxBlockRule>) {
    setProfile((current) => ({
      ...current,
      inbox_block_rules: current.inbox_block_rules.map((item, itemIndex) => {
        if (itemIndex !== index) {
          return item;
        }
        const next = { ...item, ...patch };
        if (patch.duration_kind && patch.duration_kind !== item.duration_kind) {
          const timestamps = buildBlockTimestamps(patch.duration_kind);
          next.starts_at = timestamps.starts_at;
          next.expires_at = timestamps.expires_at;
        }
        return next;
      }),
    }));
    setProfileMessage("");
  }

  function removeBlockRule(index: number) {
    setProfile((current) => ({
      ...current,
      inbox_block_rules: current.inbox_block_rules.filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function addSourcePreferenceRule() {
    setProfile((current) => ({
      ...current,
      source_preference_rules: [...(current.source_preference_rules || []), createEmptySourcePreferenceRule()],
    }));
    setProfileMessage("");
  }

  function updateSourcePreferenceRule(index: number, patch: Partial<SourcePreferenceRule>) {
    setProfile((current) => ({
      ...current,
      source_preference_rules: (current.source_preference_rules || []).map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }));
    setProfileMessage("");
  }

  function removeSourcePreferenceRule(index: number) {
    setProfile((current) => ({
      ...current,
      source_preference_rules: (current.source_preference_rules || []).filter((_, itemIndex) => itemIndex !== index),
    }));
    setProfileMessage("");
  }

  function upsertWatchRuleFromContact(contact: AssistantContactProfile) {
    setProfile((current) => {
      const exists = current.inbox_watch_rules.some((item) => item.match_type === contact.kind && item.match_value === contact.display_name);
      if (exists) {
        return current;
      }
      return {
        ...current,
        inbox_watch_rules: [
          ...current.inbox_watch_rules,
          {
            id: `watch-${contact.id}`,
            label: contact.display_name,
            match_type: contact.kind,
            match_value: contact.display_name,
            channels: uniqueChannels(contact.channels.length ? contact.channels : ["email"]),
          },
        ],
      };
    });
    setProfileMessage("");
  }

  function removeWatchRuleForContact(contact: AssistantContactProfile) {
    setProfile((current) => ({
      ...current,
      inbox_watch_rules: current.inbox_watch_rules.filter((item) => !(item.match_type === contact.kind && item.match_value === contact.display_name)),
    }));
    setProfileMessage("");
  }

  function upsertBlockRuleFromContact(contact: AssistantContactProfile, durationKind: InboxBlockRule["duration_kind"]) {
    setProfile((current) => {
      const timestamps = buildBlockTimestamps(durationKind);
      const existingIndex = current.inbox_block_rules.findIndex((item) => item.match_type === contact.kind && item.match_value === contact.display_name);
      const nextRule: InboxBlockRule = {
        id: `block-${contact.id}`,
        label: contact.display_name,
        match_type: contact.kind,
        match_value: contact.display_name,
        channels: uniqueChannels(contact.channels.length ? contact.channels : ["email"]),
        duration_kind: durationKind,
        starts_at: timestamps.starts_at,
        expires_at: timestamps.expires_at,
      };
      if (existingIndex === -1) {
        return { ...current, inbox_block_rules: [...current.inbox_block_rules, nextRule] };
      }
      return {
        ...current,
        inbox_block_rules: current.inbox_block_rules.map((item, index) => (index === existingIndex ? nextRule : item)),
      };
    });
    setProfileMessage("");
  }

  function removeBlockRuleForContact(contact: AssistantContactProfile) {
    setProfile((current) => ({
      ...current,
      inbox_block_rules: current.inbox_block_rules.filter((item) => !(item.match_type === contact.kind && item.match_value === contact.display_name)),
    }));
    setProfileMessage("");
  }

  function updateAssistantRuntimeField(field: keyof AssistantRuntimeProfile, value: string) {
    setAssistantRuntimeProfile((current) => ({ ...current, [field]: value }));
    setAssistantRuntimeMessage("");
  }

  function toggleAssistantForm(slug: string, enabled: boolean) {
    const preset = assistantFormCatalog.find((item) => item.slug === slug);
    setAssistantRuntimeProfile((current) => {
      const forms = normalizeAssistantForms(current);
      const nextForms = [...forms];
      const index = nextForms.findIndex((item) => item.slug === slug);
      const timestamp = new Date().toISOString();
      if (index >= 0) {
        nextForms[index] = {
          ...nextForms[index],
          active: enabled,
          updated_at: timestamp,
          last_requested_at: timestamp,
        };
      } else {
        if (!preset) {
          return current;
        }
        nextForms.push({
          slug,
          title: preset.title,
          summary: preset.summary || "",
          category: preset.category || "preset",
          active: enabled,
          source: "settings",
          scopes: Array.isArray(preset.scopes) ? preset.scopes : (slug === "legal_copilot" ? ["professional", "project"] : ["personal", "global"]),
          capabilities: Array.isArray(preset.capabilities) ? preset.capabilities : [],
          ui_surfaces: Array.isArray(preset.ui_surfaces) ? preset.ui_surfaces : ["assistant_core"],
          supports_coaching: Boolean(preset.supports_coaching),
          custom: false,
          created_at: timestamp,
          updated_at: timestamp,
          last_requested_at: timestamp,
        });
      }
      return { ...current, assistant_forms: nextForms };
    });
    setAssistantRuntimeMessage("");
  }

  function addOrUpdateCustomAssistantForm() {
    const title = customAssistantFormDraft.title.trim();
    if (!title) {
      setAssistantRuntimeMessage("Özel form için önce bir başlık yaz.");
      return;
    }
    const slug = assistantFormSlug(title);
    const timestamp = new Date().toISOString();
    const selectedCapabilities = assistantCapabilityCatalog.filter((item) => customAssistantFormDraft.capabilities.includes(item.slug));
    const impliedSurfaces = selectedCapabilities.flatMap((item) => item.implies_surfaces || []).filter(Boolean);
    const suggestedScopes = selectedCapabilities.flatMap((item) => item.suggested_scopes || []).filter(Boolean);
    const nextScopes = Array.from(
      new Set([
        ...(customAssistantFormDraft.scopes.length ? customAssistantFormDraft.scopes : (suggestedScopes.length ? suggestedScopes : ["personal", "global"])),
      ]),
    );
    const nextSurfaces = Array.from(
      new Set(["assistant_core", ...customAssistantFormDraft.ui_surfaces, ...impliedSurfaces]),
    );
    const supportsCoaching = Boolean(
      customAssistantFormDraft.supports_coaching
      || customAssistantFormDraft.capabilities.some((item) => ["goal_tracking", "habit_checkins", "accountability", "study_planning", "reading_progress"].includes(item)),
    );

    setAssistantRuntimeProfile((current) => {
      const forms = normalizeAssistantForms(current);
      const existingIndex = forms.findIndex((item) => item.slug === slug);
      const nextForm = {
        slug,
        title,
        summary: customAssistantFormDraft.summary.trim() || `${title} için kullanıcı tarafından tanımlanmış özel asistan formu.`,
        category: customAssistantFormDraft.category.trim() || "custom",
        active: customAssistantFormDraft.active,
        source: "settings",
        scopes: nextScopes,
        capabilities: Array.from(new Set(customAssistantFormDraft.capabilities)),
        ui_surfaces: nextSurfaces,
        supports_coaching: supportsCoaching,
        custom: true,
        created_at: existingIndex >= 0 ? forms[existingIndex].created_at : timestamp,
        updated_at: timestamp,
        last_requested_at: timestamp,
      };
      const nextForms = [...forms];
      if (existingIndex >= 0) {
        nextForms[existingIndex] = { ...nextForms[existingIndex], ...nextForm };
      } else {
        nextForms.push(nextForm);
      }
      return { ...current, assistant_forms: nextForms };
    });
    setCustomAssistantFormDraft(createEmptyCustomAssistantFormDraft());
    setAssistantRuntimeMessage("Özel asistan formu hazırlandı. Kaydettiğinde kalıcı hale gelecek.");
  }

  function applyAssistantBlueprintToDraft(blueprint: AssistantCoreBlueprint, description: string) {
    const form = blueprint.form || {};
    const nextCapabilities = Array.from(new Set((form.capabilities || []).map((item) => String(item || "").trim()).filter(Boolean)));
    const selectedCapabilities = assistantCapabilityCatalog.filter((item) => nextCapabilities.includes(item.slug));
    const impliedSurfaces = selectedCapabilities.flatMap((item) => item.implies_surfaces || []).filter(Boolean);
    const nextScopes = Array.from(
      new Set((form.scopes || []).map((item) => String(item || "").trim()).filter(Boolean).concat("personal").filter(Boolean)),
    );
    const nextSurfaces = Array.from(
      new Set(["assistant_core", ...(form.ui_surfaces || []).map((item) => String(item || "").trim()).filter(Boolean), ...impliedSurfaces]),
    );
    setAssistantBlueprintPrompt(description);
    setAssistantBlueprintPreview(blueprint);
    setCustomAssistantFormDraft({
      title: String(form.title || "").trim(),
      summary: String(form.summary || description || "").trim(),
      category: String(form.category || "custom").trim() || "custom",
      scopes: nextScopes.length ? nextScopes : ["personal"],
      capabilities: nextCapabilities.length ? nextCapabilities : ["custom_guidance"],
      ui_surfaces: nextSurfaces,
      supports_coaching: Boolean(form.supports_coaching),
      active: true,
    });
    if (blueprint.behavior_contract_patch && Object.keys(blueprint.behavior_contract_patch).length > 0) {
      setAssistantRuntimeProfile((current) => ({
        ...current,
        behavior_contract: {
          ...(current.behavior_contract || {}),
          ...blueprint.behavior_contract_patch,
        },
      }));
    }
    setAssistantRuntimeMessage("Tarif edilen asistana uygun bir form taslağı hazırlandı. Düzenleyip kaydettiğinde çekirdek buna göre evrilir.");
  }

  async function handleGenerateAssistantBlueprint(promptOverride?: string) {
    const description = String(promptOverride ?? assistantBlueprintPrompt).trim();
    if (!description) {
      setAssistantRuntimeMessage("Önce çekirdeğin neye dönüşmesini istediğini tarif et.");
      return;
    }
    setIsGeneratingAssistantBlueprint(true);
    try {
      const blueprint = await buildAssistantRuntimeBlueprint(settings, { description });
      applyAssistantBlueprintToDraft(blueprint, description);
      setError("");
    } catch (err) {
      setAssistantRuntimeMessage(err instanceof Error ? err.message : "Asistan formu taslağı üretilemedi.");
    } finally {
      setIsGeneratingAssistantBlueprint(false);
    }
  }

  function updateAssistantBehaviorContract(field: keyof AssistantRuntimeProfile["behavior_contract"], value: string) {
    setAssistantRuntimeProfile((current) => ({
      ...current,
      behavior_contract: {
        ...(current.behavior_contract || {}),
        [field]: value,
      },
    }));
    setAssistantRuntimeMessage("");
  }

  function openTab(tab: SettingsTab) {
    setActiveTab(tab);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", tab);
    nextParams.delete("section");
    setSearchParams(nextParams, { replace: true });
  }

  async function handleSaveProfile() {
    setIsSavingProfile(true);
    try {
      const response = await saveUserProfile(settings, buildUserProfilePayload(profile));
      const nextProfile = normalizeProfile(settings.officeId, response.profile);
      setProfile(nextProfile);
      writeCachedSettingsValue(PROFILE_CACHE_KEY, nextProfile);
      setProfileMessage(response.message);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.profileSaveError);
    } finally {
      setIsSavingProfile(false);
    }
  }

  async function handleSaveAssistantRuntimeProfile() {
    setIsSavingAssistantRuntime(true);
    try {
      const response = await saveAssistantRuntimeProfile(settings, {
        assistant_name: assistantRuntimeProfile.assistant_name,
        role_summary: assistantRuntimeProfile.role_summary,
        tone: assistantRuntimeProfile.tone,
        avatar_path: assistantRuntimeProfile.avatar_path,
        soul_notes: assistantRuntimeProfile.soul_notes.trim(),
        tools_notes: assistantRuntimeProfile.tools_notes.trim(),
        assistant_forms: assistantRuntimeProfile.assistant_forms.map((item) => ({
          slug: item.slug,
          title: item.title,
          summary: item.summary,
          category: item.category,
          active: item.active,
          source: item.source,
          scopes: item.scopes,
          capabilities: item.capabilities,
          ui_surfaces: item.ui_surfaces,
          supports_coaching: item.supports_coaching,
          custom: item.custom,
          created_at: item.created_at,
          updated_at: item.updated_at,
          last_requested_at: item.last_requested_at,
        })),
        behavior_contract: assistantRuntimeProfile.behavior_contract,
        evolution_history: assistantRuntimeProfile.evolution_history,
        heartbeat_extra_checks: splitChecklist(assistantRuntimeProfile.tools_notes),
      });
      const nextAssistantRuntimeProfile = normalizeAssistantRuntimeProfile(settings.officeId, response.profile);
      setAssistantRuntimeProfile(nextAssistantRuntimeProfile);
      writeCachedSettingsValue(ASSISTANT_RUNTIME_CACHE_KEY, nextAssistantRuntimeProfile);
      setAssistantRuntimeMessage(response.message);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.assistantRuntimeSaveError);
    } finally {
      setIsSavingAssistantRuntime(false);
    }
  }

  const themeModeOptions = [
    { mode: "system" as const, title: sozluk.settings.themeSystem, description: sozluk.settings.themeSystemDescription },
    { mode: "light" as const, title: sozluk.settings.themeLight, description: sozluk.settings.themeLightDescription },
    { mode: "dark" as const, title: sozluk.settings.themeDark, description: sozluk.settings.themeDarkDescription },
  ];
  const accentOptions = [
    { val: "default", label: "Varsayılan", desc: "Düz ve nötr gri", color: "#71717a" },
    { val: "purple", label: "Mor", desc: "İndigo ve belirgin", color: "#6366f1" },
    { val: "green", label: "Klasik", desc: "Yeşil ve sakin", color: "#22c55e" },
    { val: "blue", label: "Sakin", desc: "Mavi ve odaklı", color: "#3b82f6" },
    { val: "rose", label: "Canlı", desc: "Daha sıcak vurgular", color: "#f43f5e" },
  ];
  const wallpaperOptions = [
    { val: "default", label: "Varsayılan", desc: "Temiz arka plan" },
    { val: "paper", label: "Doku", desc: "Hafif kağıt hissi" },
    { val: "doodle", label: "Doodle", desc: "Daha hareketli görünüm" },
    { val: "custom", label: "Özel", desc: "Kendi görseliniz" },
  ];
  const fontSizeOptions = [
    { val: "small", label: "Küçük", desc: "Daha yoğun yerleşim", preview: "Aa" },
    { val: "medium", label: "Orta", desc: "Dengeli görünüm", preview: "Aa" },
    { val: "large", label: "Büyük", desc: "Daha rahat okunur", preview: "Aa" },
  ];
  return (
    <div className="settings-surface">
      <div className="page-grid page-grid--settings settings-layout">
        <div className="tabs tabs--vertical settings-layout__sidebar">
          <button
            className={`tab ${activeTab === "kurulum" ? "tab--active" : ""}`}
            onClick={() => openTab("kurulum")}
          >
            {sozluk.settings.setupTitle}
          </button>
          <button
            className={`tab ${activeTab === "gorunum" ? "tab--active" : ""}`}
            onClick={() => openTab("gorunum")}
          >
            {sozluk.settings.appearanceTabTitle}
          </button>
          <button
            className={`tab ${activeTab === "profil" ? "tab--active" : ""}`}
            onClick={() => openTab("profil")}
          >
            {sozluk.settings.personalProfileTitle}
          </button>
          <button
            className={`tab ${activeTab === "iletisim" ? "tab--active" : ""}`}
            onClick={() => openTab("iletisim")}
          >
            {sozluk.settings.communicationTabTitle}
          </button>
          <button
            className={`tab ${activeTab === "assistant" ? "tab--active" : ""}`}
            onClick={() => openTab("assistant")}
          >
            {sozluk.settings.assistantRuntimeTitle}
          </button>
          <button
            className={`tab ${activeTab === "automation" ? "tab--active" : ""}`}
            onClick={() => openTab("automation")}
          >
            {sozluk.settings.automationTabTitle}
          </button>
        </div>

        <div className="stack settings-layout__content">
          {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}

          {activeTab === "kurulum" && (
            <div className="stack">
              <div id="kurulum-karti" style={{ scrollMarginTop: "1rem" }}>
                <SectionCard
                  title={sozluk.settings.setupTitle}
                  subtitle={sozluk.settings.setupSubtitle}
                >
                  <div className="stack">
                    <div className="callout callout--accent">
                      <strong>{sozluk.settings.setupWorkspaceTitle}</strong>
                      <p style={{ marginBottom: 0 }}>{sozluk.settings.setupWorkspaceDescription}</p>
                    </div>
                    <div className={`callout ${settings.workspaceConfigured ? "callout--accent" : ""}`}>
                      <strong>{settings.workspaceConfigured ? selectedWorkspaceName : sozluk.settings.workspaceMissingTitle}</strong>
                      <p style={{ marginBottom: settings.workspaceConfigured ? "0.5rem" : 0 }}>
                        {settings.workspaceConfigured ? selectedWorkspacePath : sozluk.settings.workspaceMissingDescription}
                      </p>
                      {settings.workspaceConfigured ? (
                        <p style={{ marginBottom: 0 }}>{sozluk.settings.setupProfileDescription}</p>
                      ) : null}
                    </div>
                    <div className="toolbar">
                      <button className="button" type="button" onClick={chooseWorkspaceRoot}>
                        {settings.workspaceConfigured ? sozluk.settings.workspaceChange : sozluk.workspace.choose}
                      </button>
                      {settings.workspaceConfigured ? (
                        <button className="button button--secondary" type="button" onClick={() => navigate("/workspace")}>
                          {sozluk.settings.openWorkspaceAction}
                        </button>
                      ) : null}
                    </div>
                    {desktopConfigSaved ? (
                      <div className="callout callout--accent">
                        <strong>{desktopConfigSaved}</strong>
                      </div>
                    ) : null}
                  </div>
                </SectionCard>
              </div>

              <SectionCard
                title={sozluk.settings.desktopUpdateTitle}
                subtitle={sozluk.settings.desktopUpdateSubtitle}
              >
                {desktopReady ? (
                  <div className="stack">
                    {(() => {
                      const summary = buildDesktopUpdateSummary(desktopUpdateStatus);
                      const primaryAction = (() => {
                        if (!desktopUpdateStatus.supported || !desktopUpdateStatus.enabled || !desktopUpdateStatus.configured) {
                          return null;
                        }
                        if (desktopUpdateStatus.status === "downloaded") {
                          return {
                            label: isInstallingDesktopUpdate ? sozluk.settings.desktopUpdateInstalling : sozluk.settings.desktopUpdateInstall,
                            onClick: installDesktopUpdate,
                            disabled: isInstallingDesktopUpdate,
                          };
                        }
                        if (desktopUpdateStatus.status === "available") {
                          return {
                            label: isDownloadingDesktopUpdate ? sozluk.settings.desktopUpdateDownloading : sozluk.settings.desktopUpdateDownload,
                            onClick: downloadDesktopUpdate,
                            disabled: isDownloadingDesktopUpdate,
                          };
                        }
                        if (desktopUpdateStatus.status === "downloading") {
                          return {
                            label: sozluk.settings.desktopUpdateDownloading,
                            onClick: null,
                            disabled: true,
                          };
                        }
                        if (desktopUpdateStatus.status === "checking") {
                          return {
                            label: sozluk.settings.desktopUpdateChecking,
                            onClick: null,
                            disabled: true,
                          };
                        }
                        return {
                          label: isCheckingDesktopUpdate ? sozluk.settings.desktopUpdateChecking : sozluk.settings.desktopUpdateCheck,
                          onClick: checkDesktopUpdates,
                          disabled: isCheckingDesktopUpdate,
                        };
                      })();
                      return (
                        <div className={`callout ${summary.tone === "accent" ? "callout--accent" : ""}`}>
                          <strong>{summary.title}</strong>
                          <p style={{ marginBottom: "0.5rem" }}>{summary.description}</p>
                          <p style={{ marginBottom: 0 }}>
                            {sozluk.settings.desktopUpdateCurrentVersionLabel.replace("{version}", desktopUpdateStatus.current_version || "-")}
                          </p>
                          <p style={{ marginBottom: desktopUpdateStatus.available_version ? "0.5rem" : 0 }}>
                            {sozluk.settings.desktopUpdateLastCheckedLabel.replace("{value}", desktopUpdateDateLabel(desktopUpdateStatus.last_checked_at))}
                          </p>
                          {desktopUpdateStatus.available_version ? (
                            <p style={{ marginBottom: 0 }}>
                              {sozluk.settings.desktopUpdateAvailableVersionLabel.replace("{version}", desktopUpdateStatus.available_version)}
                            </p>
                          ) : null}
                          {desktopUpdateStatus.downloaded_version ? (
                            <p style={{ marginBottom: 0 }}>
                              {sozluk.settings.desktopUpdateDownloadedVersionLabel.replace("{version}", desktopUpdateStatus.downloaded_version)}
                            </p>
                          ) : null}
                          {desktopUpdateStatus.status === "downloading" ? (
                            <p style={{ marginBottom: 0 }}>
                              {sozluk.settings.desktopUpdateDownloadProgressLabel.replace("{percent}", String(Math.max(0, Math.round(desktopUpdateStatus.download_percent || 0))))}
                            </p>
                          ) : null}
                          {desktopUpdateMessage ? (
                            <p style={{ color: "var(--text-muted)", marginTop: "0.5rem", marginBottom: 0 }}>{desktopUpdateMessage}</p>
                          ) : null}
                          {primaryAction ? (
                            <div className="toolbar" style={{ marginTop: "0.9rem" }}>
                              <button
                                className={`button ${desktopUpdateStatus.status === "downloaded" ? "" : "button--secondary"}`}
                                type="button"
                                onClick={primaryAction.onClick || undefined}
                                disabled={primaryAction.disabled}
                              >
                                {primaryAction.label}
                              </button>
                            </div>
                          ) : null}
                        </div>
                      );
                    })()}
                    <details className="setup-form-details">
                      <summary className="setup-form-details__summary">{sozluk.settings.desktopUpdateAdvancedToggle}</summary>
                      <div className="stack">
                        <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.settings.desktopUpdateAdvancedDescription}</p>
                        <div className="field-grid field-grid--two">
                          <label className="stack stack--tight">
                            <span>{sozluk.settings.desktopUpdateEnabledLabel}</span>
                            <select
                              className="select"
                              value={desktopUpdateDraft.enabled ? "on" : "off"}
                              onChange={(event) => updateDesktopUpdateField("enabled", event.target.value === "on")}
                            >
                              <option value="on">{sozluk.settings.enabled}</option>
                              <option value="off">{sozluk.settings.disabled}</option>
                            </select>
                          </label>
                          <label className="stack stack--tight">
                            <span>{sozluk.settings.desktopUpdateAutoCheckLabel}</span>
                            <select
                              className="select"
                              value={desktopUpdateDraft.autoCheckOnLaunch ? "on" : "off"}
                              onChange={(event) => updateDesktopUpdateField("autoCheckOnLaunch", event.target.value === "on")}
                            >
                              <option value="on">{sozluk.settings.enabled}</option>
                              <option value="off">{sozluk.settings.disabled}</option>
                            </select>
                          </label>
                          <label className="stack stack--tight">
                            <span>{sozluk.settings.desktopUpdateAutoDownloadLabel}</span>
                            <select
                              className="select"
                              value={desktopUpdateDraft.autoDownload ? "on" : "off"}
                              onChange={(event) => updateDesktopUpdateField("autoDownload", event.target.value === "on")}
                            >
                              <option value="off">{sozluk.settings.disabled}</option>
                              <option value="on">{sozluk.settings.enabled}</option>
                            </select>
                          </label>
                          <label className="stack stack--tight">
                            <span>{sozluk.settings.desktopUpdatePrereleaseLabel}</span>
                            <select
                              className="select"
                              value={desktopUpdateDraft.allowPrerelease ? "on" : "off"}
                              onChange={(event) => updateDesktopUpdateField("allowPrerelease", event.target.value === "on")}
                            >
                              <option value="off">{sozluk.settings.disabled}</option>
                              <option value="on">{sozluk.settings.enabled}</option>
                            </select>
                          </label>
                        </div>
                        <details className="setup-form-details">
                          <summary className="setup-form-details__summary">{sozluk.settings.desktopUpdateTechnicalToggle}</summary>
                          <div className="stack">
                            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.settings.desktopUpdateTechnicalDescription}</p>
                            <div className="field-grid field-grid--two">
                              <label className="stack stack--tight">
                                <span>{sozluk.settings.desktopUpdateUrlLabel}</span>
                                <input
                                  className="input"
                                  type="url"
                                  placeholder={sozluk.settings.desktopUpdateUrlPlaceholder}
                                  value={desktopUpdateDraft.feedUrl}
                                  onChange={(event) => updateDesktopUpdateField("feedUrl", event.target.value)}
                                />
                              </label>
                              <label className="stack stack--tight">
                                <span>{sozluk.settings.desktopUpdateChannelLabel}</span>
                                <select
                                  className="select"
                                  value={desktopUpdateDraft.channel}
                                  onChange={(event) => updateDesktopUpdateField("channel", event.target.value)}
                                >
                                  <option value="latest">Stable / latest</option>
                                  <option value="pilot">Pilot</option>
                                  <option value="nightly">Nightly</option>
                                </select>
                              </label>
                            </div>
                            {!desktopUpdateStatus.supported && desktopUpdateStatus.support_message ? (
                              <div className="callout">
                                <strong>{sozluk.settings.desktopUpdateUnsupportedTitle}</strong>
                                <p style={{ marginBottom: 0 }}>{desktopUpdateStatus.support_message}</p>
                              </div>
                            ) : null}
                            {desktopUpdateStatus.release_notes ? (
                              <div className="callout">
                                <strong>{sozluk.settings.desktopUpdateReleaseNotesTitle}</strong>
                                <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{desktopUpdateStatus.release_notes}</p>
                              </div>
                            ) : null}
                            {desktopUpdateStatus.last_error ? (
                              <div className="callout">
                                <strong>{sozluk.settings.desktopUpdateErrorTitle}</strong>
                                <p style={{ marginBottom: 0 }}>{desktopUpdateStatus.last_error}</p>
                              </div>
                            ) : null}
                          </div>
                        </details>
                        <div className="toolbar">
                          <button className="button" type="button" onClick={saveDesktopUpdateConfiguration} disabled={isSavingDesktopUpdate}>
                            {isSavingDesktopUpdate ? sozluk.settings.desktopUpdateSaving : sozluk.settings.desktopUpdateSave}
                          </button>
                        </div>
                      </div>
                    </details>
                  </div>
                ) : (
                  <EmptyState
                    title={sozluk.settings.desktopUpdateDesktopOnlyTitle}
                    description={sozluk.settings.desktopUpdateDesktopOnlyDescription}
                  />
                )}
              </SectionCard>

              <SectionCard title={sozluk.settings.setupConnectionsTitle} subtitle={sozluk.settings.setupConnectionsSubtitle}>
                <div className="stack">
                  <div className="callout">
                    <strong>Bağlantıları burada yönetin</strong>
                    <p style={{ marginBottom: 0 }}>
                      Google, Outlook, Telegram, WhatsApp, sosyal medya ve Elastic bağlantılarını bu bölümden kurabilir, güncelleyebilir, yeniden bağlayabilir ve son durumlarını izleyebilirsin.
                    </p>
                  </div>
                  <div className="stack" style={{ gap: "0.75rem" }}>
                    {[
                      {
                        id: "provider" as const,
                        title: "Yapay zekâ sağlayıcısı",
                        description: "OpenAI, Gemini, uyumlu API veya Ollama bağlantısını burada yönetin.",
                        badges: ["Model ve hesap"],
                        sections: ["provider"] as const,
                      },
                      {
                        id: "mail-calendar" as const,
                        title: "E-posta ve takvim",
                        description: "Google ve Outlook hesaplarını bağlayın; e-posta ve takvim akışları birlikte çalışsın.",
                        badges: ["Google", "Outlook"],
                        sections: ["google", "outlook"] as const,
                      },
                      {
                        id: "messaging" as const,
                        title: "Mesajlaşma",
                        description: "Telegram ve WhatsApp kurulumlarını tek yerde tamamlayın.",
                        badges: ["Telegram", "WhatsApp"],
                        sections: ["telegram", "whatsapp"] as const,
                      },
                      {
                        id: "social" as const,
                        title: "Sosyal medya",
                        description: "X ve Instagram DM'lerini, LinkedIn yorumlarını, paylaşım ve takip akışlarını yönetin.",
                        badges: ["X", "Instagram", "LinkedIn"],
                        sections: ["x", "instagram", "linkedin"] as const,
                      },
                      {
                        id: "data-sources" as const,
                        title: "Veri kaynaklari",
                        description: "Yerel klasordeki dosyalar otomatik okunur. Harici Elastic cluster kullaniyorsaniz buradan baglayabilirsiniz.",
                        badges: ["Yerel klasor", "Elastic"],
                        sections: [] as const,
                      },
                    ].map((group) => {
                      const isOpen = expandedSetupGroups.includes(group.id);
                      return (
                        <div
                          key={group.id}
                          style={{
                            border: "1px solid rgba(15, 23, 42, 0.08)",
                            borderRadius: "1rem",
                            overflow: "hidden",
                            background: "var(--bg-surface)",
                          }}
                        >
                          <button
                            type="button"
                            aria-expanded={isOpen}
                            onClick={() => toggleSetupGroup(group.id)}
                            style={{
                              width: "100%",
                              border: "none",
                              background: "transparent",
                              padding: "1rem 1.1rem",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: "0.9rem",
                              textAlign: "left",
                              cursor: "pointer",
                            }}
                          >
                            <div className="stack stack--tight" style={{ gap: "0.35rem", minWidth: 0 }}>
                              <strong>{group.title}</strong>
                              <span style={{ color: "var(--text-muted)" }}>{group.description}</span>
                              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                                {group.badges.map((item) => (
                                  <StatusBadge key={item}>{item}</StatusBadge>
                                ))}
                              </div>
                            </div>
                            <StatusBadge tone={isOpen ? "accent" : "neutral"}>{isOpen ? "Açık" : "Kapalı"}</StatusBadge>
                          </button>
                          {isOpen ? (
                            <div style={{ padding: "0 1.1rem 1.1rem", borderTop: "1px solid rgba(15, 23, 42, 0.08)" }}>
                              {group.id === "data-sources" ? (
                                <div className="stack">
                                  <div className="callout">
                                    <strong>Yerel klasor icin ek kurulum gerekmez</strong>
                                    <p style={{ marginBottom: "0.75rem" }}>
                                      Calisma klasorunuzun icindeki dosyalar, belgeler ve alt klasorler zaten otomatik olarak okunur. Bu yuzden PostgreSQL, MySQL veya SQL Server gibi veritabani motorlarini normal kullanici kurulumu gibi burada gostermiyoruz.
                                    </p>
                                    <p style={{ marginBottom: "0.75rem" }}>
                                      Harici bir Elastic cluster kullaniyorsaniz burada dogrudan baglayabilirsiniz. Kaydedilen baglanti sonrasinda arama, DSL ve Elastic SQL aksiyonlari asistan ve veri akislari icinde kullanilabilir.
                                    </p>
                                  </div>
                                  <ElasticSetupPanel onUpdated={() => void refreshSettingsSurface({ force: true, includeBase: true, includeDesktop: true })} />
                                </div>
                              ) : (
                                <IntegrationSetupPanel mode="settings" sections={[...group.sections]} onUpdated={() => void refreshSettingsSurface({ force: true, includeBase: true, includeDesktop: true })} />
                              )}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                  <div className="callout">
                    <strong>Günlük kullanım için iki ana ekran yeterlidir</strong>
                    <p style={{ marginBottom: "0.75rem" }}>
                      Belgeler ve Kaynaklar ekranında klasörünüzdeki içerikleri görürsünüz. Günlük iş akışını ise doğrudan Asistan ekranından yönetirsiniz.
                    </p>
                    <div className="toolbar">
                      <button className="button button--secondary" type="button" onClick={() => navigate("/workspace")}>
                        {sozluk.settings.openWorkspaceAction}
                      </button>
                      <button className="button button--secondary" type="button" onClick={() => navigate("/assistant")}>
                        Asistana dön
                      </button>
                    </div>
                  </div>
                </div>
              </SectionCard>
            </div>
          )}

          {activeTab === "gorunum" && (
            <div className="stack">
              <SectionCard title="Görünüm" subtitle="Renk, yazı boyutu ve sohbet görünümünü burada değiştirin.">
                <div className="appearance-studio">
                  <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: "none" }}
                    accept="image/*"
                    onChange={handleCustomWallpaperUpload}
                  />

                  <div className="appearance-studio__grid">
                    <section className="appearance-card">
                      <div className="appearance-card__head">
                        <strong>Tema modu</strong>
                        <p>Uygulamanın genel ışık seviyesini ve kontrastını seçin.</p>
                      </div>
                      <div className="theme-picker theme-picker--wide">
                        <div className="theme-picker__options">
                          {themeModeOptions.map((item) => (
                            <button
                              key={item.mode}
                              aria-label={item.title}
                              className={`theme-picker__option${settings.themeMode === item.mode ? " theme-picker__option--active" : ""}`}
                              type="button"
                              onClick={() => saveThemeMode(item.mode)}
                            >
                              <div className={`theme-picker__swatch theme-picker__swatch--${item.mode}`} aria-hidden="true" />
                              <strong>{item.title}</strong>
                              <span>{item.description}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </section>

                    <section className="appearance-card">
                      <div className="appearance-card__head">
                        <strong>Sohbet tasarımı</strong>
                        <p>Vurgu rengini değiştirip sohbetin genel hissini ayarlayın.</p>
                      </div>
                      <div className="theme-picker theme-picker--wide">
                        <div className="theme-picker__options">
                          {accentOptions.map((acc) => (
                            <button
                              key={acc.val}
                              aria-label={acc.label}
                              className={`theme-picker__option${settings.themeAccent === acc.val ? " theme-picker__option--active" : ""}`}
                              type="button"
                              onClick={() => saveThemeAccent(acc.val)}
                            >
                              <div className="theme-picker__swatch" style={{ background: acc.color, border: "none" }} aria-hidden="true" />
                              <strong>{acc.label}</strong>
                              <span>{acc.desc}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </section>

                    <section className="appearance-card appearance-card--full">
                      <div className="appearance-card__head">
                        <strong>Sohbet arka planı</strong>
                        <p>İstersen nötr bir yüzey kullan, istersen kendi görselini ekle.</p>
                      </div>
                      <div className="theme-picker theme-picker--wide">
                        <div className="theme-picker__options">
                          {wallpaperOptions.map((bg) => (
                            <button
                              key={bg.val}
                              aria-label={bg.label}
                              className={`theme-picker__option${settings.chatWallpaper === bg.val ? " theme-picker__option--active" : ""}`}
                              type="button"
                              onClick={() => {
                                if (bg.val === "custom" && !settings.customWallpaper) {
                                  fileInputRef.current?.click();
                                } else {
                                  saveChatWallpaper(bg.val);
                                }
                              }}
                            >
                              <div
                                className="theme-picker__swatch"
                                style={{
                                  backgroundImage: bg.val === "doodle"
                                    ? "repeating-linear-gradient(45deg, var(--line-soft) 0, var(--line-soft) 1px, transparent 0, transparent 50%)"
                                    : bg.val === "custom" && settings.customWallpaper
                                      ? `url(${settings.customWallpaper})`
                                      : "none",
                                  backgroundSize: bg.val === "custom" ? "cover" : "10px 10px",
                                  backgroundColor: "var(--bg-surface-soft)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: "0.74rem",
                                  color: "var(--text-muted)",
                                }}
                                aria-hidden="true"
                              >
                                {bg.val === "custom" && !settings.customWallpaper ? "Seçilmedi" : ""}
                              </div>
                              <strong>{bg.label}</strong>
                              <span>{bg.desc}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="appearance-card__footer">
                        <button
                          className="button button--secondary button--small"
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                        >
                          <svg style={{ marginRight: "0.5rem" }} xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                          Yeni resim yükle
                        </button>
                      </div>
                    </section>

                    <section className="appearance-card appearance-card--full">
                      <div className="appearance-card__head">
                        <strong>Yazı boyutu</strong>
                        <p>Bu seçim sohbet, ayarlar ve genel arayüz metinlerini birlikte ölçekler.</p>
                      </div>
                      <div className="theme-picker theme-picker--wide">
                        <div className="theme-picker__options">
                          {fontSizeOptions.map((sz) => (
                            <button
                              key={sz.val}
                              aria-label={sz.label}
                              className={`theme-picker__option${settings.chatFontSize === sz.val ? " theme-picker__option--active" : ""}`}
                              type="button"
                              onClick={() => saveChatFontSize(sz.val)}
                            >
                              <div
                                className="theme-picker__swatch"
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: sz.val === "small" ? "0.9rem" : sz.val === "large" ? "1.7rem" : "1.18rem",
                                  fontWeight: 700,
                                }}
                                aria-hidden="true"
                              >
                                {sz.preview}
                              </div>
                              <strong>{sz.label}</strong>
                              <span>{sz.desc}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </section>
                  </div>
                </div>
              </SectionCard>
            </div>
          )}

          {activeTab === "profil" && (
            <div className="stack">
              <div id="personal-profile" style={{ scrollMarginTop: "1rem" }}>
                <PersonalModelPage embedded hideRelatedProfilesSection />
              </div>
            </div>
          )}

          {activeTab === "iletisim" && (
            <div className="stack">
              <SectionCard
                title="İletişim ve bildirim kuralları"
                subtitle="Hangi kişi, grup ve kelimelerden gelen mesaj ve maillerin sana bildirileceğini burada belirlersin."
                actions={(
                  <button className="button" type="button" onClick={() => void handleSaveProfile()} disabled={isSavingProfile}>
                    {isSavingProfile ? "Kurallar kaydediliyor..." : "Kuralları kaydet"}
                  </button>
                )}
              >
                <div className="stack stack--tight">
                  {profileMessage ? <div className="notice notice--success">{profileMessage}</div> : null}
                  <div className="callout callout--accent">
                    <strong>Bildirim mantığı</strong>
                    <p style={{ marginBottom: "0.6rem" }}>
                      İzlenen kişi ve gruplardan gelen yeni mesajlar sana bildirilir. Bir kişi izlenmese bile aşağıdaki anahtar kelimelerden birini içeren mesaj veya mail sana yine bildirilir. Engellenen kişi ve gruplardan gelen hiçbir içerik görünmez.
                    </p>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <StatusBadge tone="accent">{watchedRuleCount} izleme kuralı</StatusBadge>
                      <StatusBadge tone="warning">{keywordRuleCount} anahtar kelime</StatusBadge>
                      <StatusBadge tone="danger">{blockedRuleCount} engel kuralı</StatusBadge>
                    </div>
                  </div>
                </div>
              </SectionCard>

              <SectionCard
                title="Yakın kişiler"
                subtitle="Senin için önemli kişileri burada tut. Asistan mesajlardan, beğeni açıklamalarından ve geri bildirimlerden bu profilleri beslemeye devam eder."
                actions={(
                  <button className="button button--secondary" type="button" onClick={addRelatedProfile}>
                    Yakın kişi ekle
                  </button>
                )}
              >
                {profile.related_profiles.length ? (
                  <div className="stack stack--tight">
                    {profile.related_profiles.map((item, index) => (
                      <article className="list-item" key={item.id || `related-profile-${index}`}>
                        <div className="toolbar" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                          <div className="stack stack--tight" style={{ flex: 1 }}>
                            <div className="toolbar" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                              <strong>{item.name || `Yakın kişi ${index + 1}`}</strong>
                              <StatusBadge tone="accent">{normalizeCloseness(item.closeness, 3)}/5 yakın</StatusBadge>
                            </div>
                            <div className="field-grid" style={{ marginTop: "0.5rem" }}>
                              <label className="stack stack--tight">
                                <span>İsim</span>
                                <input className="input" value={item.name} onChange={(event) => updateRelatedProfileField(index, "name", event.target.value)} />
                              </label>
                              <label className="stack stack--tight">
                                <span>İlişki</span>
                                <input className="input" value={item.relationship} onChange={(event) => updateRelatedProfileField(index, "relationship", event.target.value)} />
                              </label>
                              <label className="stack stack--tight">
                                <span>Yakınlık derecesi</span>
                                <select
                                  aria-label={`${item.name || `Yakın kişi ${index + 1}`} yakınlık derecesi`}
                                  className="select"
                                  value={String(normalizeCloseness(item.closeness, 3))}
                                  onChange={(event) => updateRelatedProfileCloseness(index, Number(event.target.value))}
                                >
                                  <option value="1">1 · Uzak</option>
                                  <option value="2">2</option>
                                  <option value="3">3 · Orta</option>
                                  <option value="4">4</option>
                                  <option value="5">5 · Çok yakın</option>
                                </select>
                              </label>
                              <div className="stack stack--tight">
                                <span>&nbsp;</span>
                                <button className="button button--ghost" type="button" onClick={() => removeRelatedProfile(index)}>
                                  Kaldır
                                </button>
                              </div>
                              <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                                <span>Tercihler ve sevdikleri</span>
                                <textarea className="textarea" rows={2} value={item.preferences} onChange={(event) => updateRelatedProfileField(index, "preferences", event.target.value)} />
                              </label>
                              <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                                <span>Notlar</span>
                                <textarea className="textarea" rows={2} value={item.notes} onChange={(event) => updateRelatedProfileField(index, "notes", event.target.value)} />
                              </label>
                            </div>
                            <div className="toolbar" style={{ justifyContent: "space-between", marginTop: "0.5rem" }}>
                              <strong>Bu kişiye ait önemli tarihler</strong>
                              <button className="button button--ghost" type="button" onClick={() => addRelatedProfileImportantDate(index)}>
                                Tarih ekle
                              </button>
                            </div>
                            {item.important_dates.length ? (
                              <div className="stack stack--tight">
                                {item.important_dates.map((dateItem, dateIndex) => (
                                  <div className="field-grid" key={`${item.id || index}-date-${dateIndex}`}>
                                    <label className="stack stack--tight">
                                      <span>Başlık</span>
                                      <input className="input" value={dateItem.label} onChange={(event) => updateRelatedProfileImportantDate(index, dateIndex, { label: event.target.value })} />
                                    </label>
                                    <label className="stack stack--tight">
                                      <span>Tarih</span>
                                      <input className="input" type="date" value={dateItem.date} onChange={(event) => updateRelatedProfileImportantDate(index, dateIndex, { date: event.target.value })} />
                                    </label>
                                    <label className="stack stack--tight">
                                      <span>Tekrar</span>
                                      <select className="select" value={dateItem.recurring_annually ? "yearly" : "single"} onChange={(event) => updateRelatedProfileImportantDate(index, dateIndex, { recurring_annually: event.target.value === "yearly" })}>
                                        <option value="yearly">Her yıl tekrarlar</option>
                                        <option value="single">Tek seferlik</option>
                                      </select>
                                    </label>
                                    <div className="stack stack--tight">
                                      <span>&nbsp;</span>
                                      <button className="button button--ghost" type="button" onClick={() => removeRelatedProfileImportantDate(index, dateIndex)}>
                                        Sil
                                      </button>
                                    </div>
                                    <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                                      <span>Not</span>
                                      <input className="input" value={String(dateItem.notes || "")} onChange={(event) => updateRelatedProfileImportantDate(index, dateIndex, { notes: event.target.value })} />
                                    </label>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                Bu kişi için henüz özel tarih eklenmedi.
                              </p>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="Yakın kişi profili yok"
                    description="Aile, partner, dost, avukat veya diğer önemli kişileri burada tut. Rehberden tek tıkla ekleyebilirsin."
                  />
                )}
              </SectionCard>

              <SectionCard
                title="İletişim rehberi"
                subtitle="Mail ve mesajlardan çıkan tüm kişi ve grup profilleri burada listelenir. İstersen buradan doğrudan izlemeye veya engellemeye alabilirsin."
              >
                {sortedContactProfiles.length ? (
                  <div className="stack stack--tight">
                    {sortedContactProfiles.map((item) => (
                      <article className="list-item" key={item.id}>
                        <div className="toolbar" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                          <div className="stack stack--tight" style={{ flex: 1 }}>
                            <strong>{item.display_name}</strong>
                            <p className="list-item__meta" style={{ marginBottom: 0 }}>
                              {item.relationship_hint}. {item.persona_summary}
                            </p>
                            {editingContactDescriptions[item.id] ? (
                              <label className="stack stack--tight" style={{ marginTop: "0.35rem" }}>
                                <span>Açıklama</span>
                                <textarea
                                  aria-label={`${item.display_name} açıklaması`}
                                  className="textarea"
                                  rows={5}
                                  value={contactDescriptionDrafts[item.id] ?? item.persona_detail ?? item.generated_persona_detail ?? item.persona_summary ?? ""}
                                  onChange={(event) => updateContactDescriptionDraft(item.id, event.target.value)}
                                />
                              </label>
                            ) : (
                              <>
                                <p style={{ margin: "0.35rem 0 0", lineHeight: 1.55 }}>
                                  {item.persona_detail || item.persona_summary}
                                </p>
                                <div className="stack stack--tight" style={{ marginTop: "0.5rem" }}>
                                  {item.inference_signals?.length ? (
                                    <div className="stack stack--tight">
                                      <strong style={{ fontSize: "0.9rem" }}>Çıkarılan notlar</strong>
                                      <ul style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.5 }}>
                                        {item.inference_signals.slice(0, 4).map((signal) => (
                                          <li key={`${item.id}-signal-${signal}`}>{signal}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : null}
                                  <div className="stack stack--tight">
                                    <strong style={{ fontSize: "0.9rem" }}>Tercihler ve sevdikleri</strong>
                                    {item.preference_signals?.length || item.gift_ideas?.length ? (
                                      <ul style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.5 }}>
                                        {(item.preference_signals || []).slice(0, 3).map((signal) => (
                                          <li key={`${item.id}-pref-${signal}`}>{signal}</li>
                                        ))}
                                        {(item.gift_ideas || []).slice(0, 2).map((idea) => (
                                          <li key={`${item.id}-gift-${idea}`}>Hediye fikri: {idea}</li>
                                        ))}
                                      </ul>
                                    ) : (
                                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                        Bu kişi için henüz güçlü tercih sinyali çıkmadı.
                                      </p>
                                    )}
                                  </div>
                                  {item.last_inbound_preview ? (
                                    <div className="stack stack--tight">
                                      <strong style={{ fontSize: "0.9rem" }}>Son mesaj örneği</strong>
                                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                        {item.last_inbound_preview}
                                      </p>
                                    </div>
                                  ) : null}
                                </div>
                              </>
                            )}
                            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                              <StatusBadge tone={item.kind === "group" ? "warning" : "neutral"}>
                                {item.kind === "group" ? "Grup" : "Kişi"}
                              </StatusBadge>
                              {item.related_profile_id ? <StatusBadge tone="accent">Profilde kayıtlı</StatusBadge> : null}
                              {item.closeness ? <StatusBadge tone="accent">{item.closeness}/5 yakın</StatusBadge> : null}
                              {item.persona_detail_source === "manual" ? <StatusBadge tone="accent">Açıklama elle düzenlendi</StatusBadge> : null}
                              {item.channels.map((channel) => (
                                <StatusBadge key={`${item.id}-${channel}`} tone="neutral">
                                  {channel}
                                </StatusBadge>
                              ))}
                              {item.watch_enabled ? <StatusBadge tone="accent">İzleniyor</StatusBadge> : null}
                              {item.blocked ? (
                                <StatusBadge tone="warning">
                                  Engelli{item.blocked_until ? ` · ${formatBlockUntil(item.blocked_until)}` : ""}
                                </StatusBadge>
                              ) : null}
                            </div>
                            {item.emails.length ? (
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                E-posta: {item.emails.join(", ")}
                              </p>
                            ) : null}
                            {item.phone_numbers.length ? (
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                Telefon: {item.phone_numbers.join(", ")}
                              </p>
                            ) : null}
                            {item.handles.length ? (
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                Handle: {item.handles.join(", ")}
                              </p>
                            ) : null}
                          </div>
                          <div className="toolbar" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
                            {editingContactDescriptions[item.id] ? (
                              <>
                                <button
                                  className="button button--secondary"
                                  type="button"
                                  disabled={savingContactDescriptionId === item.id}
                                  onClick={() => saveContactDescription(item)}
                                >
                                  {savingContactDescriptionId === item.id ? "Kaydediliyor..." : "Kaydet"}
                                </button>
                                <button className="button button--ghost" type="button" disabled={savingContactDescriptionId === item.id} onClick={() => cancelEditContactDescription(item.id)}>
                                  Vazgeç
                                </button>
                              </>
                            ) : (
                              <button className="button button--ghost" type="button" onClick={() => beginEditContactDescription(item)}>
                                Düzenle
                              </button>
                            )}
                            {item.kind === "person" ? (
                              item.related_profile_id ? (
                                <button className="button button--ghost" type="button" onClick={() => upsertRelatedProfileFromContact(item)}>
                                  Yakın kişi profilini güncelle
                                </button>
                              ) : (
                                <button className="button button--secondary" type="button" onClick={() => upsertRelatedProfileFromContact(item)}>
                                  Yakın kişilere ekle
                                </button>
                              )
                            ) : null}
                            {item.watch_enabled ? (
                              <button className="button button--ghost" type="button" onClick={() => removeWatchRuleForContact(item)}>
                                İzlemeyi kaldır
                              </button>
                            ) : (
                              <button className="button button--secondary" type="button" onClick={() => upsertWatchRuleFromContact(item)}>
                                Gör ve bildir
                              </button>
                            )}
                            {item.blocked ? (
                              <button className="button button--ghost" type="button" onClick={() => removeBlockRuleForContact(item)}>
                                Engeli kaldır
                              </button>
                            ) : (
                              <>
                                <button className="button button--ghost" type="button" onClick={() => upsertBlockRuleFromContact(item, "day")}>
                                  1 gün engelle
                                </button>
                                <button className="button button--ghost" type="button" onClick={() => upsertBlockRuleFromContact(item, "month")}>
                                  1 ay engelle
                                </button>
                                <button className="button button--ghost" type="button" onClick={() => upsertBlockRuleFromContact(item, "forever")}>
                                  Süresiz engelle
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="Henüz iletişim profili yok"
                    description="WhatsApp, Telegram ve e-posta verileri geldikçe kişiler ve gruplar burada kısa profiller olarak görünür."
                  />
                )}
              </SectionCard>

              <SectionCard
                title="İzlenen Kişi ve Gruplar"
                subtitle="Sadece görmek ve bildirilmesini istediğin kişi veya grupları burada tanımla."
                actions={(
                  <button className="button button--secondary" type="button" onClick={addWatchRule}>
                    İzleme kuralı ekle
                  </button>
                )}
              >
                {profile.inbox_watch_rules.length ? (
                  <div className="stack stack--tight">
                    {profile.inbox_watch_rules.map((rule, index) => (
                      <article className="list-item" key={rule.id || `watch-rule-${index}`}>
                        <div className="field-grid">
                          <label className="stack stack--tight">
                            <span>Etiket</span>
                            <input className="input" value={rule.label} onChange={(event) => updateWatchRule(index, { label: event.target.value })} />
                          </label>
                          <label className="stack stack--tight">
                            <span>Tür</span>
                            <select className="select" value={rule.match_type} onChange={(event) => updateWatchRule(index, { match_type: event.target.value as "person" | "group" })}>
                              <option value="person">Kişi</option>
                              <option value="group">Grup</option>
                            </select>
                          </label>
                          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                            <span>Eşleşecek isim / adres / grup</span>
                            <input className="input" value={rule.match_value} onChange={(event) => updateWatchRule(index, { match_value: event.target.value })} />
                          </label>
                          <div className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                            <span>Kanallar</span>
                            <div className="toolbar" style={{ flexWrap: "wrap" }}>
                              {["email", "whatsapp", "telegram"].map((channel) => (
                                <button
                                  key={`${rule.id || index}-${channel}`}
                                  className={`button ${rule.channels.includes(channel) ? "" : "button--ghost"}`}
                                  type="button"
                                  onClick={() => updateWatchRule(index, { channels: toggleChannel(rule.channels, channel) })}
                                >
                                  {channel}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="stack stack--tight">
                            <span>&nbsp;</span>
                            <button className="button button--ghost" type="button" onClick={() => removeWatchRule(index)}>
                              Kaldır
                            </button>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="İzleme kuralı yok"
                    description="Buraya eklediğin kişi ve gruplardan gelen yeni mesaj ve mailler sana bildirilir. Rehber listesinden tek tıkla ekleyebilirsin."
                  />
                )}
              </SectionCard>

              <SectionCard
                title="Anahtar Kelime Uyarıları"
                subtitle="Göndereni izlemesen bile geçtiğinde haber almak istediğin kelimeleri ekle."
                actions={(
                  <button className="button button--secondary" type="button" onClick={addKeywordRule}>
                    Keyword ekle
                  </button>
                )}
              >
                {profile.inbox_keyword_rules.length ? (
                  <div className="stack stack--tight">
                    {profile.inbox_keyword_rules.map((rule, index) => (
                      <article className="list-item" key={rule.id || `keyword-rule-${index}`}>
                        <div className="field-grid">
                          <label className="stack stack--tight">
                            <span>Keyword</span>
                            <input className="input" value={rule.keyword} onChange={(event) => updateKeywordRule(index, { keyword: event.target.value })} />
                          </label>
                          <label className="stack stack--tight">
                            <span>Etiket</span>
                            <input className="input" value={rule.label || ""} onChange={(event) => updateKeywordRule(index, { label: event.target.value })} />
                          </label>
                          <div className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                            <span>Kanallar</span>
                            <div className="toolbar" style={{ flexWrap: "wrap" }}>
                              {["email", "whatsapp", "telegram"].map((channel) => (
                                <button
                                  key={`${rule.id || index}-${channel}`}
                                  className={`button ${rule.channels.includes(channel) ? "" : "button--ghost"}`}
                                  type="button"
                                  onClick={() => updateKeywordRule(index, { channels: toggleChannel(rule.channels, channel) })}
                                >
                                  {channel}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="stack stack--tight">
                            <span>&nbsp;</span>
                            <button className="button button--ghost" type="button" onClick={() => removeKeywordRule(index)}>
                              Kaldır
                            </button>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="Keyword kuralı yok"
                    description="Örnek: “check in”, “boarding”, “ödeme”, “imza”, “teyit”. Bu kelimeler geçtiğinde gönderen izlenmese bile sana bildirilir."
                  />
                )}
              </SectionCard>

              <SectionCard
                title="Engellenen Kişiler ve Gruplar"
                subtitle="Buraya eklediğin kişiler/gruplar hiçbir bildirim ve inbox görünümüne düşmez."
                actions={(
                  <button className="button button--secondary" type="button" onClick={addBlockRule}>
                    Engel kuralı ekle
                  </button>
                )}
              >
                {profile.inbox_block_rules.length ? (
                  <div className="stack stack--tight">
                    {profile.inbox_block_rules.map((rule, index) => (
                      <article className="list-item" key={rule.id || `block-rule-${index}`}>
                        <div className="field-grid">
                          <label className="stack stack--tight">
                            <span>Etiket</span>
                            <input className="input" value={rule.label} onChange={(event) => updateBlockRule(index, { label: event.target.value })} />
                          </label>
                          <label className="stack stack--tight">
                            <span>Tür</span>
                            <select className="select" value={rule.match_type} onChange={(event) => updateBlockRule(index, { match_type: event.target.value as "person" | "group" })}>
                              <option value="person">Kişi</option>
                              <option value="group">Grup</option>
                            </select>
                          </label>
                          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                            <span>Eşleşecek isim / adres / grup</span>
                            <input className="input" value={rule.match_value} onChange={(event) => updateBlockRule(index, { match_value: event.target.value })} />
                          </label>
                          <label className="stack stack--tight">
                            <span>Süre</span>
                            <select className="select" value={rule.duration_kind} onChange={(event) => updateBlockRule(index, { duration_kind: event.target.value as InboxBlockRule["duration_kind"] })}>
                              <option value="day">1 gün</option>
                              <option value="month">1 ay</option>
                              <option value="forever">Süresiz</option>
                            </select>
                          </label>
                          <div className="stack stack--tight">
                            <span>Bitiş</span>
                            <StatusBadge tone="warning">{formatBlockUntil(rule.expires_at)}</StatusBadge>
                          </div>
                          <div className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                            <span>Kanallar</span>
                            <div className="toolbar" style={{ flexWrap: "wrap" }}>
                              {["email", "whatsapp", "telegram"].map((channel) => (
                                <button
                                  key={`${rule.id || index}-${channel}`}
                                  className={`button ${rule.channels.includes(channel) ? "" : "button--ghost"}`}
                                  type="button"
                                  onClick={() => updateBlockRule(index, { channels: toggleChannel(rule.channels, channel) })}
                                >
                                  {channel}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="stack stack--tight">
                            <span>&nbsp;</span>
                            <button className="button button--ghost" type="button" onClick={() => removeBlockRule(index)}>
                              Kaldır
                            </button>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="Engel kuralı yok"
                    description="Bir kişi veya grubu engellediğinde ondan gelen hiçbir mail/mesaj inbox’ta görünmez ve bildirim olarak öne çıkmaz."
                  />
                )}
              </SectionCard>

            </div>
          )}

          {activeTab === "assistant" && (
            <div className="stack">
              <div id="assistant-runtime" style={{ scrollMarginTop: "1rem" }}>
                <SectionCard
                  title="Asistan davranışı ve çalışma biçimi"
                  subtitle="Bu sekme hafıza yönetmez; rol, ton, proaktiflik ve çalışma biçimini belirler."
                  actions={
                    <button className="button" type="button" onClick={handleSaveAssistantRuntimeProfile} disabled={isSavingAssistantRuntime}>
                      {isSavingAssistantRuntime ? sozluk.settings.assistantRuntimeSaving : sozluk.settings.assistantRuntimeSave}
                    </button>
                  }
                >
                  <div className="callout callout--accent">
                    <strong>Rol ile hafızayı karıştırma</strong>
                    <p style={{ marginBottom: "0.75rem" }}>
                      Burada asistanın nasıl davranacağını belirlersin. Sana dair kalıcı bilgiler <strong>Profil</strong> sekmesinde tutulur. Bu alan sadece rol, ton ve çalışma biçimi içindir.
                    </p>
                  </div>
                <div className="field-grid" style={{ marginTop: "1rem" }}>
                  <label className="stack stack--tight">
                    <span>{sozluk.settings.assistantNameLabel}</span>
                    <input className="input" value={assistantRuntimeProfile.assistant_name} onChange={(event) => updateAssistantRuntimeField("assistant_name", event.target.value)} />
                  </label>
                  <label className="stack stack--tight">
                    <span>Çekirdek rol özeti</span>
                    <input
                      className="input"
                      value={assistantRuntimeProfile.role_summary}
                      onChange={(event) => updateAssistantRuntimeField("role_summary", event.target.value)}
                      placeholder={assistantRuntimeCore?.defaults?.role_summary || DEFAULT_ASSISTANT_ROLE_SUMMARY}
                    />
                  </label>
                  <label className="stack stack--tight">
                    <span>Ton</span>
                    <input
                      className="input"
                      value={assistantRuntimeProfile.tone}
                      onChange={(event) => updateAssistantRuntimeField("tone", event.target.value)}
                      placeholder={assistantRuntimeCore?.defaults?.tone || "Net ve profesyonel"}
                    />
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Davranış notu</span>
                    <textarea
                      className="textarea"
                      rows={7}
                      placeholder="Örnek: Gereksiz uzatma yapma, önce net karar ver, gerektiğinde alternatifleri kısaca sun."
                      value={assistantRuntimeProfile.soul_notes}
                      onChange={(event) => updateAssistantRuntimeField("soul_notes", event.target.value)}
                    />
                    <span className="list-item__meta">Bu alan asistanın çalışma tarzını etkiler; kullanıcıya dair bilgi kaydetmez.</span>
                  </label>
                </div>
                {buildAssistantSignals(assistantRuntimeProfile).length ? (
                  <div className="stack stack--tight" style={{ marginTop: "1rem" }}>
                    <span>{sozluk.settings.assistantSignalsTitle}</span>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      {buildAssistantSignals(assistantRuntimeProfile).map((item) => (
                        <StatusBadge key={item}>{item}</StatusBadge>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div id="assistant-core-forms" style={{ marginTop: "1rem", scrollMarginTop: "1rem" }}>
                  <div className="callout callout--accent">
                    <strong>Asistan çekirdeğini burada şekillendir</strong>
                    <p style={{ marginBottom: 0 }}>
                      Bu formlar programa gömülü sabit kişilikler değildir. İstersen buradan aç, istersen sohbet içinde “sen artık benim yaşam koçum ol” gibi söyle; asistan bu forma göre evrilir.
                    </p>
                  </div>
                  {assistantRuntimeCore?.core_summary ? (
                    <p className="list-item__meta" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
                      {assistantRuntimeCore.core_summary}
                    </p>
                  ) : null}
                  <div className="stack stack--tight" style={{ marginTop: "0.9rem" }}>
                    <label className="stack stack--tight">
                      <span>Asistanı nasıl bir role çevirmek istiyorsun?</span>
                      <textarea
                        className="textarea"
                        rows={4}
                        value={assistantBlueprintPrompt}
                        onChange={(event) => setAssistantBlueprintPrompt(event.target.value)}
                        placeholder="Örnek: Beni kitap okuma koçuna çevir. Her akşam hedefimi takip et ve nazik ama disiplinli ol."
                      />
                    </label>
                    <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
                      <button className="button button--secondary" type="button" onClick={() => void handleGenerateAssistantBlueprint()} disabled={isGeneratingAssistantBlueprint}>
                        {isGeneratingAssistantBlueprint ? "Taslak hazırlanıyor..." : "Tariften form oluştur"}
                      </button>
                      {assistantTransformationExamples.map((item) => (
                        <button
                          className="button button--ghost"
                          key={item.prompt}
                          type="button"
                          onClick={() => void handleGenerateAssistantBlueprint(item.prompt)}
                        >
                          {item.title}
                        </button>
                      ))}
                    </div>
                    {assistantBlueprintPreview ? (
                      <div className="callout">
                        <strong>{assistantBlueprintPreview.form?.title || "Özel form taslağı"}</strong>
                        <p style={{ marginBottom: "0.35rem" }}>{assistantBlueprintPreview.summary || "Tarif edilen asistana göre bir form taslağı hazırlandı."}</p>
                        <p className="list-item__meta" style={{ marginBottom: "0.35rem" }}>
                          {`Güven: ${Math.round(Number(assistantBlueprintPreview.confidence || 0) * 100)}%`}
                        </p>
                        {assistantBlueprintPreview.capability_titles?.length ? (
                          <p className="list-item__meta" style={{ marginBottom: "0.35rem" }}>
                            {`Önerilen yetenekler: ${assistantBlueprintPreview.capability_titles.join(", ")}`}
                          </p>
                        ) : null}
                        {assistantBlueprintPreview.why?.length ? (
                          <ul className="list-item__meta" style={{ margin: "0.25rem 0 0", paddingLeft: "1rem" }}>
                            {assistantBlueprintPreview.why.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <div className="stack stack--tight" style={{ marginTop: "0.9rem" }}>
                    <span>Dönüşebileceği formlar</span>
                    <div className="list">
                      {assistantFormCatalog.map((item) => {
                        const active = assistantRuntimeProfile.assistant_forms.some((form) => form.slug === item.slug && form.active);
                        return (
                          <article className="list-item" key={item.slug}>
                            <div className="toolbar" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                              <label style={{ display: "inline-flex", gap: "0.55rem", alignItems: "flex-start", flex: 1 }}>
                                <input
                                  type="checkbox"
                                  checked={active}
                                  onChange={(event) => toggleAssistantForm(item.slug, event.target.checked)}
                                  aria-label={`${item.title} formunu aktif et`}
                                />
                                <span className="stack stack--tight">
                                  <strong>{item.title}</strong>
                                  <span className="list-item__meta">{item.summary}</span>
                                </span>
                              </label>
                              {active ? <StatusBadge tone="accent">aktif</StatusBadge> : <StatusBadge tone="neutral">beklemede</StatusBadge>}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                    <p className="list-item__meta" style={{ marginBottom: 0 }}>
                      Daha özel bir forma ihtiyacın varsa bunu sohbet içinde tarif et. Asistan o talebi runtime profile’a yazar ve sonraki konuşmalarda buna göre davranır.
                    </p>
                    {getCustomAssistantForms(assistantRuntimeProfile).length ? (
                      <div className="stack stack--tight" style={{ marginTop: "0.75rem" }}>
                        <span>Konuşmalardan öğrenilen özel formlar</span>
                        <div className="list">
                          {getCustomAssistantForms(assistantRuntimeProfile).map((item) => (
                            <article className="list-item" key={item.slug}>
                              <div className="toolbar" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                                <label style={{ display: "inline-flex", gap: "0.55rem", alignItems: "flex-start", flex: 1 }}>
                                  <input
                                    type="checkbox"
                                    checked={Boolean(item.active)}
                                    onChange={(event) => toggleAssistantForm(item.slug, event.target.checked)}
                                    aria-label={`${item.title} özel formunu aktif et`}
                                  />
                                  <span className="stack stack--tight">
                                    <strong>{item.title}</strong>
                                    <span className="list-item__meta">{item.summary || "Sohbet içinde tanımlanmış özel asistan formu."}</span>
                                    <span className="list-item__meta">
                                      {`Kaynak: ${item.source || "conversation"} · Scope: ${(item.scopes || []).join(", ") || "global"}`}
                                    </span>
                                  </span>
                                </label>
                                <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                                  {item.supports_coaching ? <StatusBadge tone="accent">koçluk destekli</StatusBadge> : null}
                                  {item.active ? <StatusBadge tone="accent">aktif</StatusBadge> : <StatusBadge tone="neutral">pasif</StatusBadge>}
                                </div>
                              </div>
                            </article>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    <div className="stack stack--tight" style={{ marginTop: "0.9rem" }}>
                      <span>Kendi özel asistan formunu tasarla</span>
                      <div className="field-grid">
                        <label className="stack stack--tight">
                          <span>Form adı</span>
                          <input
                            className="input"
                            value={customAssistantFormDraft.title}
                            onChange={(event) => setCustomAssistantFormDraft((current) => ({ ...current, title: event.target.value }))}
                            placeholder="Kitap okuma koçu"
                          />
                        </label>
                        <label className="stack stack--tight">
                          <span>Kategori</span>
                          <input
                            className="input"
                            value={customAssistantFormDraft.category}
                            onChange={(event) => setCustomAssistantFormDraft((current) => ({ ...current, category: event.target.value }))}
                            placeholder="learning"
                          />
                        </label>
                        <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                          <span>Kısa açıklama</span>
                          <input
                            className="input"
                            value={customAssistantFormDraft.summary}
                            onChange={(event) => setCustomAssistantFormDraft((current) => ({ ...current, summary: event.target.value }))}
                            placeholder="Okuma hedefleri, takip ve düzen kurma desteği verir."
                          />
                        </label>
                      </div>
                      <div className="stack stack--tight">
                        <span>Scope sınırları</span>
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          {ASSISTANT_SCOPE_OPTIONS.map((item) => (
                            <label key={item.slug} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                              <input
                                type="checkbox"
                                checked={customAssistantFormDraft.scopes.includes(item.slug)}
                                onChange={() => setCustomAssistantFormDraft((current) => ({ ...current, scopes: toggleStringToken(current.scopes, item.slug) }))}
                              />
                              <span>{item.title}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div className="stack stack--tight">
                        <span>Yetenekler</span>
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          {assistantCapabilityCatalog.map((item) => (
                            <label key={item.slug} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                              <input
                                type="checkbox"
                                checked={customAssistantFormDraft.capabilities.includes(item.slug)}
                                onChange={() => setCustomAssistantFormDraft((current) => ({ ...current, capabilities: toggleStringToken(current.capabilities, item.slug) }))}
                              />
                              <span>{item.title}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div className="stack stack--tight">
                        <span>UI yüzeyleri</span>
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          {assistantSurfaceCatalog.map((item) => (
                            <label key={item.slug} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                              <input
                                type="checkbox"
                                checked={customAssistantFormDraft.ui_surfaces.includes(item.slug)}
                                onChange={() => setCustomAssistantFormDraft((current) => ({ ...current, ui_surfaces: toggleStringToken(current.ui_surfaces, item.slug) }))}
                              />
                              <span>{item.title}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                          <input
                            type="checkbox"
                            checked={customAssistantFormDraft.supports_coaching}
                            onChange={(event) => setCustomAssistantFormDraft((current) => ({ ...current, supports_coaching: event.target.checked }))}
                          />
                          <span>Koçluk özelliklerini açabilir</span>
                        </label>
                        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                          <input
                            type="checkbox"
                            checked={customAssistantFormDraft.active}
                            onChange={(event) => setCustomAssistantFormDraft((current) => ({ ...current, active: event.target.checked }))}
                          />
                          <span>Eklenince aktif olsun</span>
                        </label>
                        <button className="button button--secondary" type="button" onClick={addOrUpdateCustomAssistantForm}>
                          Özel form ekle / güncelle
                        </button>
                        <button className="button button--ghost" type="button" onClick={() => setCustomAssistantFormDraft(createEmptyCustomAssistantFormDraft())}>
                          Temizle
                        </button>
                      </div>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                        Bu alan, ürünün içine sabit bir yaşam koçu yüklemek için değil; kullanıcının istediği anda çekirdeği kendi ihtiyacına göre şekillendirmesi için var.
                      </p>
                    </div>
                  </div>
                  <div className="field-grid" style={{ marginTop: "1rem" }}>
                    <label className="stack stack--tight">
                      <span>Proaktiflik</span>
                      <select
                        className="select"
                        value={assistantRuntimeProfile.behavior_contract.initiative_level || "balanced"}
                        onChange={(event) => updateAssistantBehaviorContract("initiative_level", event.target.value)}
                      >
                        <option value="low">Düşük</option>
                        <option value="balanced">Dengeli</option>
                        <option value="high">Yüksek</option>
                      </select>
                    </label>
                    <label className="stack stack--tight">
                      <span>Takip stili</span>
                      <select
                        className="select"
                        value={assistantRuntimeProfile.behavior_contract.follow_up_style || "check_in"}
                        onChange={(event) => updateAssistantBehaviorContract("follow_up_style", event.target.value)}
                      >
                        <option value="on_request">İstek gelince</option>
                        <option value="check_in">Aralıklı check-in</option>
                        <option value="persistent">Israrlı takip</option>
                      </select>
                    </label>
                    <label className="stack stack--tight">
                      <span>Plan derinliği</span>
                      <select
                        className="select"
                        value={assistantRuntimeProfile.behavior_contract.planning_depth || "structured"}
                        onChange={(event) => updateAssistantBehaviorContract("planning_depth", event.target.value)}
                      >
                        <option value="light">Hafif</option>
                        <option value="structured">Yapılı</option>
                        <option value="deep">Derin</option>
                      </select>
                    </label>
                    <label className="stack stack--tight">
                      <span>Açıklama düzeyi</span>
                      <select
                        className="select"
                        value={assistantRuntimeProfile.behavior_contract.explanation_style || "balanced"}
                        onChange={(event) => updateAssistantBehaviorContract("explanation_style", event.target.value)}
                      >
                        <option value="concise">Kısa</option>
                        <option value="balanced">Dengeli</option>
                        <option value="detailed">Detaylı</option>
                      </select>
                    </label>
                  </div>
                </div>
                <div className="callout" id="assistant-advanced-routines" style={{ marginTop: "1rem", scrollMarginTop: "1rem" }}>
                  <strong>{sozluk.settings.assistantAdvancedRoutinesTitle}</strong>
                  <p style={{ marginBottom: 0 }}>{sozluk.settings.assistantAdvancedRoutinesDescription}</p>
                </div>
                <div className="callout callout--accent" style={{ marginTop: "1rem" }}>
                  <strong>{sozluk.settings.assistantRuntimeFlowTitle}</strong>
                  <p style={{ marginBottom: 0 }}>{sozluk.settings.assistantRuntimeFlowDescription}</p>
                </div>
                </SectionCard>
              </div>
              {assistantRuntimeMessage ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{assistantRuntimeMessage}</p> : null}
            </div>
          )}

          {activeTab === "automation" && (
            <div className="stack">
              {desktopReady ? (
                <>
                  <div id="automation-panel" style={{ scrollMarginTop: "1rem" }}>
                    <SectionCard
                      title={sozluk.settings.automationTitle}
                      subtitle={sozluk.settings.automationSubtitle}
                      actions={(
                        <button className="button" type="button" onClick={saveAutomationConfiguration} disabled={isSavingAutomation}>
                          {isSavingAutomation ? sozluk.settings.automationSaving : sozluk.settings.automationSave}
                        </button>
                      )}
                    >
                      <div className="stack">
                        <div className="callout callout--accent">
                          <strong>{sozluk.settings.automationCalloutTitle}</strong>
                          <p style={{ marginBottom: 0 }}>{sozluk.settings.automationCalloutDescription}</p>
                        </div>
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          <StatusBadge tone={automationSettings.enabled ? "accent" : "warning"}>
                            {sozluk.settings.automationEnabledLabel}: {automationSettings.enabled ? sozluk.settings.enabled : sozluk.settings.disabled}
                          </StatusBadge>
                          <StatusBadge tone={automationSettings.automationRules.length ? "neutral" : "warning"}>
                            {sozluk.settings.automationRuleCountLabel.replace("{count}", String(automationSettings.automationRules.length))}
                          </StatusBadge>
                          <StatusBadge tone={automationSettings.lastRunAt ? "accent" : "neutral"}>
                            {sozluk.settings.automationLastRunLabel}: {automationLastRunLabel(automationSettings.lastRunAt)}
                          </StatusBadge>
                        </div>
                        <label className="stack stack--tight" style={{ maxWidth: "22rem" }}>
                          <span>{sozluk.settings.automationEnabledLabel}</span>
                          <select
                            className="select"
                            value={automationSettings.enabled ? "on" : "off"}
                            onChange={(event) => updateAutomationField("enabled", event.target.value === "on")}
                          >
                            <option value="on">{sozluk.settings.enabled}</option>
                            <option value="off">{sozluk.settings.disabled}</option>
                          </select>
                        </label>
                        <p className="list-item__meta" style={{ marginBottom: 0 }}>
                          Bildirimler ve arka plan yenileme bu bölüm açık olduğunda otomatik kullanılır. Yeni kuralı asistana konuşarak oluşturabilir, burada da gerektiğinde düzeltebilirsin.
                        </p>
                        {automationMessage ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{automationMessage}</p> : null}
                      </div>
                    </SectionCard>
                  </div>

                  <SectionCard title={sozluk.settings.automationRulesTitle} subtitle={sozluk.settings.automationRulesSubtitle}>
                    {automationSettings.automationRules.length ? (
                      <div className="stack stack--tight">
                        {automationSettings.automationRules.map((rule) => (
                          <article className="list-item" key={rule.id}>
                            <div className="stack stack--tight">
                              <div className="toolbar" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
                                <div className="toolbar" style={{ flexWrap: "wrap" }}>
                                  <StatusBadge tone={rule.active ? "accent" : "warning"}>
                                    {automationModeLabel(rule.mode)}
                                  </StatusBadge>
                                  {(rule.channels.length ? rule.channels : ["genel"]).map((channel) => (
                                    <StatusBadge key={`${rule.id}-${channel}`} tone="neutral">
                                      {automationChannelLabel(channel)}
                                    </StatusBadge>
                                  ))}
                                </div>
                                <button
                                  className="button button--ghost"
                                  type="button"
                                  style={{ marginLeft: "auto" }}
                                  onClick={() => removeAutomationRule(rule.id)}
                                >
                                  {sozluk.settings.automationDeleteRule}
                                </button>
                              </div>
                              <label className="stack stack--tight">
                                <span>{sozluk.settings.automationRuleSummaryLabel}</span>
                                <input
                                  className="input"
                                  value={rule.summary}
                                  onChange={(event) => updateAutomationRule(rule.id, { summary: event.target.value })}
                                />
                              </label>
                              <label className="stack stack--tight">
                                <span>{sozluk.settings.automationRuleInstructionLabel}</span>
                                <textarea
                                  className="textarea"
                                  rows={2}
                                  value={rule.instruction}
                                  onChange={(event) => updateAutomationRule(rule.id, { instruction: event.target.value })}
                                />
                              </label>
                              {rule.reminder_at ? (
                                <label className="stack stack--tight" style={{ maxWidth: "20rem" }}>
                                  <span>{sozluk.settings.automationRuleReminderAtLabel}</span>
                                  <input
                                    className="input"
                                    type="datetime-local"
                                    value={automationDateTimeInputValue(rule.reminder_at)}
                                    onChange={(event) => updateAutomationRule(rule.id, { reminder_at: automationDateTimeFromInput(event.target.value) })}
                                  />
                                  <span className="list-item__meta">{`Çalışma zamanı: ${automationReminderLabel(rule.reminder_at)}`}</span>
                                </label>
                              ) : null}
                              <div className="toolbar" style={{ justifyContent: "space-between", alignItems: "center" }}>
                                <span className="list-item__meta">
                                  {rule.targets.length ? `${sozluk.settings.automationRuleTargetsLabel}: ${rule.targets.join(", ")}` : sozluk.settings.automationRuleManualHint}
                                </span>
                                <label className="toolbar" style={{ gap: "0.5rem", alignItems: "center" }}>
                                  <span>{sozluk.settings.automationRuleActiveLabel}</span>
                                  <input
                                    type="checkbox"
                                    checked={rule.active}
                                    onChange={(event) => updateAutomationRule(rule.id, { active: event.target.checked })}
                                  />
                                </label>
                              </div>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        title={sozluk.settings.automationRulesEmptyTitle}
                        description={sozluk.settings.automationRulesEmptyDescription}
                      />
                    )}
                  </SectionCard>
                </>
              ) : (
                <EmptyState title={sozluk.settings.automationDesktopOnlyTitle} description={sozluk.settings.automationDesktopOnlyDescription} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
