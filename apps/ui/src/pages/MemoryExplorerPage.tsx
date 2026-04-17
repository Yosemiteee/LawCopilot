import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import {
  changeMemoryExplorerScope,
  editMemoryExplorerRecord,
  forgetMemoryExplorerRecord,
  getMemoryExplorerGraph,
  getMemoryExplorerHealth,
  getMemoryExplorerPage,
  getMemoryExplorerPages,
  getMemoryExplorerTimeline,
} from "../services/lawcopilotApi";
import type {
  MemoryExplorerArticleClaimBinding,
  MemoryExplorerClaimBinding,
  MemoryExplorerGraphResponse,
  MemoryExplorerHealthResponse,
  MemoryExplorerPageDetail,
  MemoryExplorerPagesResponse,
  MemoryExplorerRecord,
  MemoryExplorerTimelineResponse,
} from "../types/domain";

type ExplorerTab = "pages" | "graph" | "timeline" | "provenance" | "health";

const EXPLORER_TABS: Array<{ key: ExplorerTab; label: string }> = [
  { key: "pages", label: "Dizin" },
  { key: "graph", label: "Harita" },
  { key: "timeline", label: "Geçmiş" },
  { key: "provenance", label: "Dayanak" },
  { key: "health", label: "Riskler" },
];

const DEFAULT_SCOPE_OPTIONS = ["personal", "workspace", "professional", "global"];
const MEMORY_TITLE_LABELS: Record<string, string> = {
  "agents.md": "Asistan kontratı",
  assistant_runtime_snapshot: "Asistan çalışma özeti",
  assistant_tone: "Asistan tonu",
  communication_style: "İletişim tarzı",
  constraint: "Çalışma sınırı",
  contacts: "Kişiler",
  decision: "Karar",
  decisions: "Kararlar",
  persona: "Kimlik profili",
  person: "Kişi",
  places: "Konumlar",
  preferences: "Tercihler",
  profile_snapshot: "Profil özeti",
  projects: "Projeler",
  role_summary: "Rol özeti",
  routines: "Rutinler",
  tone: "Ton",
};
const MEMORY_KIND_LABELS: Record<string, string> = {
  concept: "kavram",
  report: "rapor",
  system_file: "sistem dosyası",
  wiki_page: "wiki sayfası",
};
const MEMORY_SUMMARY_LABELS: Record<string, string> = {
  concept_articles: "kavram yazısı",
  contradictions: "çelişki",
  contamination_risks: "kirlenme riski",
  cross_link_gaps: "bağlantı boşluğu",
  edge_count: "bağlantı sayısı",
  hot: "sıcak",
  knowledge_gaps: "bilgi boşluğu",
  node_count: "düğüm sayısı",
  orphan_concepts: "yetim kavram",
  orphan_pages: "yetim sayfa",
  records: "kayıt",
  stale_claims: "eski claim",
  stale_items: "eski öğe",
  superseded_claims: "yerine geçen claim",
  total_items: "toplam öğe",
  unbound_pages: "claimsiz sayfa",
  weak_claims: "zayıf claim",
  warm: "ılık",
  wiki_pages: "wiki sayfası",
  cold: "soğuk",
};
const MEMORY_ACTION_LABELS: Record<string, string> = {
  merge_duplicates: "Çift kayıtları birleştir",
  rebuild_article: "Yazıyı yeniden oluştur",
  refresh_summary: "Özeti yenile",
  review_contradiction: "Çelişkiyi gözden geçir",
};
const MEMORY_TRANSPARENCY_LABELS: Record<string, string> = {
  reports_dir: "rapor klasörü",
  root_path: "kök dizin",
  wiki_dir: "wiki klasörü",
};
const MEMORY_STATUS_LABELS: Record<string, string> = {
  active: "aktif",
  attention_required: "ilgi gerekiyor",
  completed: "tamamlandı",
  contradiction: "çelişki",
  critical: "kritik",
  current: "güncel",
  error: "hata",
  failed: "başarısız",
  healthy: "sağlıklı",
  rejected: "reddedildi",
  retry_scheduled: "yeniden denenecek",
  stale: "eskimiş",
  warning: "uyarı",
};
const MEMORY_RECORD_TYPE_LABELS: Record<string, string> = {
  conversation_style: "iletişim tarzı",
  reference: "referans",
  relation_target: "ilişki hedefi",
  topic: "konu",
};
const MEMORY_LINE_PREFIX_LABELS: Array<[RegExp, string]> = [
  [/^active records?:\s*/i, "Aktif kayıtlar: "],
  [/^claim binding:\s*/i, "Claim bağı: "],
  [/^claim refs:\s*/i, "Claim referansları: "],
  [/^claim status:\s*/i, "Çözüm durumu: "],
  [/^confidence:\s*/i, "Güven: "],
  [/^exportability:\s*/i, "Dışa aktarım: "],
  [/^model routine:\s*/i, "Model rutini: "],
  [/^persona:\s*/i, "Kimlik profili: "],
  [/^preferences:\s*/i, "Tercihler: "],
  [/^record type:\s*/i, "Kayıt türü: "],
  [/^scope:\s*/i, "Kapsam: "],
  [/^sensitivity:\s*/i, "Hassasiyet: "],
  [/^sources:\s*/i, "Kaynaklar: "],
  [/^status:\s*/i, "Durum: "],
  [/^support quality:\s*/i, "Dayanak kalitesi: "],
  [/^summary:\s*/i, "Özet: "],
  [/^total records?:\s*/i, "Toplam kayıtlar: "],
  [/^updated at:\s*/i, "Güncellendi: "],
];
type MemoryMarkdownBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

function normalizeMemoryKey(value?: string | null) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[-\s]+/g, "_");
}

function memoryTitleLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const exact = MEMORY_TITLE_LABELS[normalizeMemoryKey(raw)];
  if (exact) {
    return exact;
  }
  return raw
    .replace(/\bcommunication style\b/gi, "İletişim tarzı")
    .replace(/\bassistant tone\b/gi, "Asistan tonu")
    .replace(/\brole summary\b/gi, "Rol özeti")
    .replace(/\bconstraint\b/gi, "Çalışma sınırı")
    .replace(/\bpersona\b/gi, "Kimlik profili")
    .replace(/\bpreferences\b/gi, "Tercihler")
    .replace(/\bprojects\b/gi, "Projeler")
    .replace(/\bplaces\b/gi, "Konumlar")
    .replace(/\broutines\b/gi, "Rutinler")
    .replace(/\bdecisions\b/gi, "Kararlar")
    .replace(/\bdecision\b/gi, "Karar")
    .replace(/\bcontacts\b/gi, "Kişiler")
    .replace(/\bperson\b/gi, "Kişi")
    .replace(/\btone\b/gi, "Ton")
    .replace(/\bmother\b/gi, "anne")
    .replace(/\bthin article\b/gi, "Yazı henüz çok kısa");
}

function memoryKindLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "öğe";
  const normalized = raw.toLowerCase();
  return MEMORY_KIND_LABELS[normalized] || raw.replaceAll("_", " ");
}

function memorySummaryLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return MEMORY_SUMMARY_LABELS[raw.toLowerCase()] || raw.replaceAll("_", " ");
}

function memoryStatusLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return MEMORY_STATUS_LABELS[raw.toLowerCase()] || raw.replaceAll("_", " ");
}

function memoryTransparencyLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return MEMORY_TRANSPARENCY_LABELS[raw.toLowerCase()] || raw.replaceAll("_", " ");
}

function memoryRecordTypeLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return MEMORY_RECORD_TYPE_LABELS[raw.toLowerCase()] || raw.replaceAll("_", " ");
}

function memoryActionLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return MEMORY_ACTION_LABELS[raw.toLowerCase()] || raw.replaceAll("_", " ");
}

function articleSectionLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    summary: "Özet",
    detailed_explanation: "Detaylı açıklama",
    patterns: "Örüntü",
    inferred_insights: "Çıkarım",
    strategy_notes: "Strateji notu",
    cross_links: "Çapraz bağlantı",
  };
  return mapping[normalized] || String(value || "").trim() || "Yazı bölümü";
}

function localizeMemoryLine(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const exact = memoryTitleLabel(raw);
  if (exact !== raw) {
    return exact;
  }
  for (const [pattern, replacement] of MEMORY_LINE_PREFIX_LABELS) {
    if (pattern.test(raw)) {
      return raw.replace(pattern, replacement);
    }
  }
  return raw;
}

function pageMetricLabel(recordCount?: number | null, backlinkCount?: number | null, updatedAt?: string | null) {
  return `${Number(recordCount || 0)} kayıt · ${Number(backlinkCount || 0)} bağlantı · güncellendi: ${dateLabel(updatedAt)}`;
}

function graphNodeKindLabel(node: Record<string, unknown>) {
  const kind = String(node.entity_type || node.kind || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    concept: "kavram",
    topic: "kavram",
    record: "kayıt",
    reference: "referans",
    relation_target: "referans",
    system_file: "sistem",
  };
  return mapping[kind] || memoryKindLabel(kind || "öğe");
}

function scopeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "genel";
  if (normalized === "personal") return "kişisel";
  if (normalized === "workspace") return "çalışma alanı";
  if (normalized === "professional") return "profesyonel";
  if (normalized === "global") return "genel";
  if (normalized.startsWith("project:")) return normalized.replace("project:", "proje:");
  return normalized;
}

function statusTone(value?: string | null): "neutral" | "accent" | "warning" | "danger" {
  const normalized = String(value || "").trim().toLowerCase();
  if (["healthy", "completed", "accepted", "active", "current", "grounded", "supported", "hot"].includes(normalized)) return "accent";
  if (["attention_required", "retry_scheduled", "warning", "rejected", "stale", "weak", "warm"].includes(normalized)) return "warning";
  if (["critical", "failed", "error", "contradiction", "contaminated"].includes(normalized)) return "danger";
  return "neutral";
}

function dateLabel(value?: string | null) {
  if (!value) return "bilinmiyor";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("tr-TR");
}

function relationLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    prefers: "tercih eder",
    avoids: "kaçınır",
    related_to: "ilişkili",
    inferred_from: "şuradan öğrenildi",
    supports: "destekler",
    contradicts: "çelişir",
    supersedes: "yerine geçti",
    relevant_to: "ilgili",
    scoped_to: "alana bağlı",
    requires_confirmation: "onay ister",
  };
  return mapping[normalized] || normalized || "ilişki";
}

function eventLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("memory_")) return `bellek · ${normalized.replace("memory_", "")}`;
  const mapping: Record<string, string> = {
    knowledge_record: "bilgi kaydı",
    claim_update: "claim güncellemesi",
    claim_superseded: "claim değişikliği",
    assistant_context_snapshot: "asistan bağlamı",
    recommendation_feedback: "öneri geri bildirimi",
    decision_record: "karar kaydı",
    reflection_output: "değerlendirme",
    trigger: "tetikleme",
    system_event: "sistem",
  };
  return mapping[normalized] || normalized || "olay";
}

function epistemicStatusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    current: "Şu an geçerli",
    contested: "Çelişkili",
    unknown: "Belirsiz",
  };
  return mapping[normalized] || normalized || "Belirsiz";
}

function epistemicBasisLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    user_explicit: "Kullanıcı açıkça söyledi",
    user_confirmed_inference: "Kullanıcı onayladı",
    connector_observed: "Bağlı kaynaktan gözlendi",
    document_extracted: "Belgeden çıkarıldı",
    inferred: "Çıkarım",
    assistant_generated: "Asistan üretimi",
  };
  return mapping[normalized] || normalized || "Bilinmiyor";
}

function retrievalEligibilityLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    eligible: "Yanıtlarda kullanılabilir",
    demoted: "Düşük öncelikli kullanılır",
    blocked: "Yanıtlarda kullanılmaz",
    quarantined: "Karantinada tutulur",
  };
  return mapping[normalized] || normalized || "Bilinmiyor";
}

function supportStrengthLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    grounded: "Sağlam dayanak",
    supported: "Destekli dayanak",
    weak: "Zayıf dayanak",
    contaminated: "Kirli dayanak",
    unknown: "Bilinmiyor",
  };
  return mapping[normalized] || normalized || "Bilinmiyor";
}

function memoryTierLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    hot: "Sıcak bellek",
    warm: "Ilık bellek",
    cold: "Soğuk bellek",
  };
  return mapping[normalized] || normalized || "Bilinmiyor";
}

function assistantVisibilityFromEpistemic(epistemic?: MemoryExplorerRecord["epistemic"]) {
  if (!epistemic) return "Belirsiz";
  if (epistemic.support_contaminated) return "Şu an gizleniyor";
  const retrieval = String(epistemic.retrieval_eligibility || "").trim().toLowerCase();
  if (retrieval === "blocked") return "Şu an gizleniyor";
  if (retrieval === "quarantined") return "Karantinada";
  if (retrieval === "demoted") return "Düşük öncelikle görünür";
  if (retrieval === "eligible") return "Asistana açık";
  return "Belirsiz";
}

function supportReasonLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    cycle_detected: "Destek zincirinde döngü var.",
    self_generated_without_external_support: "Bilgi yalnız asistan üretimine dayanıyor.",
    assistant_only_support_chain: "Destek zinciri yalnız asistan üretimi kayıtlarından oluşuyor.",
    contaminated_support_chain: "Destek zinciri kirli bir kayda bağlı.",
  };
  return mapping[normalized] || normalized || "Ek inceleme gerekli.";
}

function normalizeClaimBinding(item: MemoryExplorerClaimBinding | Record<string, unknown>): MemoryExplorerClaimBinding | null {
  if (!item || typeof item !== "object") return null;
  const value = item as MemoryExplorerClaimBinding;
  if (!value.current_claim_id && !value.record_title && !value.predicate) return null;
  return value;
}

function normalizeArticleClaimBinding(item: MemoryExplorerArticleClaimBinding | Record<string, unknown>): MemoryExplorerArticleClaimBinding | null {
  if (!item || typeof item !== "object") return null;
  const value = item as MemoryExplorerArticleClaimBinding;
  if (!value.text && !(Array.isArray(value.claim_ids) && value.claim_ids.length)) return null;
  return value;
}

function normalizeRecord(item: MemoryExplorerRecord | Record<string, unknown>): MemoryExplorerRecord | null {
  if (!item || typeof item !== "object") return null;
  const value = item as MemoryExplorerRecord;
  if (!value.id && !value.title) return null;
  return value;
}

function renderUnknownValue(value: unknown) {
  if (value === null || value === undefined) return "bilinmiyor";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function parseJsonishText(text: string): unknown | null {
  const normalized = String(text || "").trim();
  if (!normalized) return null;

  if ((normalized.startsWith("{") && normalized.endsWith("}")) || (normalized.startsWith("[") && normalized.endsWith("]"))) {
    try {
      return JSON.parse(normalized);
    } catch {
      return null;
    }
  }

  const firstBraceIndex = normalized.indexOf("{");
  const lastBraceIndex = normalized.lastIndexOf("}");
  if (firstBraceIndex >= 0 && lastBraceIndex > firstBraceIndex) {
    try {
      return JSON.parse(normalized.substring(firstBraceIndex, lastBraceIndex + 1));
    } catch {
      // continue
    }
  }

  const firstBracketIndex = normalized.indexOf("[");
  const lastBracketIndex = normalized.lastIndexOf("]");
  if (firstBracketIndex >= 0 && lastBracketIndex > firstBracketIndex) {
    try {
      return JSON.parse(normalized.substring(firstBracketIndex, lastBracketIndex + 1));
    } catch {
      return null;
    }
  }

  return null;
}

function sourceTypeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    assistant_runtime_snapshot: "Asistan çalışma özeti",
    profile_snapshot: "Profil özeti",
    user_preferences: "Kullanıcı tercihi",
  };
  return mapping[normalized] || memoryFieldLabel(value);
}

function humanizeMetadataValue(field: string, value: unknown): string {
  const normalizedField = String(field || "").trim().toLowerCase();
  const normalizedValue = String(value ?? "").trim().toLowerCase();
  if (!normalizedValue) return "bilinmiyor";

  if (normalizedField === "source_type") {
    return sourceTypeLabel(String(value || ""));
  }
  if (normalizedField === "sensitivity") {
    return normalizedValue === "high" ? "yüksek" : normalizedValue === "medium" ? "orta" : normalizedValue === "low" ? "düşük" : normalizedValue;
  }
  if (normalizedField === "exportability") {
    return normalizedValue === "local_only" ? "yalnız yerelde" : normalizedValue.replaceAll("_", " ");
  }
  if (normalizedField === "model_routing_hint") {
    return normalizedValue === "prefer_local" ? "yerel modeli tercih et" : normalizedValue.replaceAll("_", " ");
  }
  if (normalizedField === "record_type") {
    return memoryRecordTypeLabel(String(value || ""));
  }
  if (normalizedField === "status") {
    return memoryStatusLabel(String(value || ""));
  }
  if (Array.isArray(value)) {
    return value.map((item) => humanizeMetadataValue(field, item)).join(" · ");
  }
  return String(value);
}

function memoryFieldLabel(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "alan";
  const normalized = raw.toLowerCase();
  const mapping: Record<string, string> = {
    assistant_notes: "Asistan notu",
    capture_mode: "Yakalama türü",
    current_location: "Güncel konum",
    current_place: "Bulunulan yer",
    display_name: "Hitap / isim",
    home_base: "Ana yaşam noktası",
    location_preferences: "Konum tercihleri",
    maps_preference: "Harita tercihi",
    office_id: "Ofis",
    preferred_domains: "Tercih edilen siteler",
    preferred_links: "Tercih edilen bağlantılar",
    preferred_providers: "Tercih edilen sağlayıcılar",
    prayer_habit_notes: "Rutin notu",
    source_ref: "Kaynak",
    source_type: "Kaynak türü",
    task_kind: "Görev türü",
    travel_preferences: "Seyahat notları",
  };
  return mapping[normalized] || raw.replaceAll("_", " ");
}

function compactMemoryValue(value: unknown, depth = 0): string {
  if (value === null || value === undefined || value === "") return "bilinmiyor";
  if (typeof value === "string") {
    return value.length > 160 ? `${value.slice(0, 157)}...` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    if (!value.length) return "boş";
    if (depth > 0) return `${value.length} öğe`;
    const preview = value.slice(0, 3).map((item) => compactMemoryValue(item, depth + 1)).join(" · ");
    return value.length > 3 ? `${preview} +${value.length - 3}` : preview;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item !== null && item !== undefined && item !== "");
    if (!entries.length) return "boş";
    if (depth > 0) return `${entries.length} alan`;
    const preview = entries
      .slice(0, 3)
      .map(([key, item]) => `${memoryFieldLabel(key)}: ${compactMemoryValue(item, depth + 1)}`)
      .join(" · ");
    return entries.length > 3 ? `${preview} +${entries.length - 3}` : preview;
  }
  return String(value);
}

function memoryRecordTitle(record?: MemoryExplorerRecord | null) {
  if (!record) return "Kayıt";
  const direct = String(record.title || "").trim();
  const parsed = parseJsonishText(String(record.summary || ""));
  if (parsed && typeof parsed === "object" && "profile" in (parsed as Record<string, unknown>)) {
    return "Profil özeti";
  }
  if (parsed && typeof parsed === "object" && "runtime_profile" in (parsed as Record<string, unknown>) && !("profile" in (parsed as Record<string, unknown>))) {
    return "Asistan çalışma özeti";
  }
  return memoryTitleLabel(direct || String(record.id || "Kayıt"));
}

function profileSnapshotSummary(parsed: Record<string, unknown>) {
  const profile = (parsed.profile && typeof parsed.profile === "object") ? parsed.profile as Record<string, unknown> : {};
  const runtimeProfile = (parsed.runtime_profile && typeof parsed.runtime_profile === "object") ? parsed.runtime_profile as Record<string, unknown> : {};

  const lines = [
    profile.display_name ? `Hitap: ${String(profile.display_name)}` : "",
    profile.communication_style ? `İletişim tarzı: ${String(profile.communication_style)}` : "",
    profile.home_base ? `Ana yaşam noktası: ${String(profile.home_base)}` : profile.current_location ? `Güncel konum: ${String(profile.current_location)}` : "",
    Array.isArray(profile.source_preference_rules) ? `Kaynak kuralı: ${profile.source_preference_rules.length}` : "",
    Array.isArray(profile.related_profiles) ? `Yakın kişi: ${profile.related_profiles.length}` : "",
    Array.isArray(profile.important_dates) ? `Önemli tarih: ${profile.important_dates.length}` : "",
    runtimeProfile.assistant_name ? `Asistan adı: ${String(runtimeProfile.assistant_name)}` : "",
    runtimeProfile.tone ? `Asistan tonu: ${String(runtimeProfile.tone)}` : "",
  ].filter(Boolean);

  return lines.length ? lines.join(" · ") : "Profil ve asistan çalışma ayarlarının özet kaydı.";
}

function memoryRecordSummary(record?: MemoryExplorerRecord | null) {
  const raw = String(record?.summary || "").trim();
  if (!raw) return "Özet yok.";

  const parsed = parseJsonishText(raw);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const value = parsed as Record<string, unknown>;
    if ("profile" in value || "runtime_profile" in value) {
      return profileSnapshotSummary(value);
    }
    return compactMemoryValue(parsed);
  }
  return compactMemoryValue(localizeMemoryLine(raw));
}

function renderRecordSummary(record?: MemoryExplorerRecord | null) {
  const raw = String(record?.summary || "").trim();
  const parsed = parseJsonishText(raw);

  if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && ("profile" in (parsed as Record<string, unknown>) || "runtime_profile" in (parsed as Record<string, unknown>))) {
    const value = parsed as Record<string, unknown>;
    const profile = (value.profile && typeof value.profile === "object") ? value.profile as Record<string, unknown> : null;
    const runtimeProfile = (value.runtime_profile && typeof value.runtime_profile === "object") ? value.runtime_profile as Record<string, unknown> : null;
    return (
      <div className="memory-explorer__summary-preview">
        <p className="list-item__meta" style={{ marginBottom: 0 }}>{profileSnapshotSummary(value)}</p>
        <div className="memory-explorer__summary-grid">
          {profile ? renderStructuredValue(profile, "Kişisel bilgiler") : null}
          {runtimeProfile ? renderStructuredValue(runtimeProfile, "Asistan çalışma ayarları") : null}
        </div>
      </div>
    );
  }

  if (parsed) {
    return (
      <div className="memory-explorer__summary-preview">
        <p className="list-item__meta" style={{ marginBottom: 0 }}>{compactMemoryValue(parsed)}</p>
        <details className="memory-explorer__expander">
          <summary>Özetin ayrıntısı</summary>
          {renderStructuredValue(parsed)}
        </details>
      </div>
    );
  }

  return <p className="list-item__meta" style={{ marginBottom: 0 }}>{memoryRecordSummary(record)}</p>;
}

function renderStructuredValue(value: unknown, title?: string) {
  if (value === null || value === undefined) {
    return <p className="list-item__meta" style={{ marginBottom: 0 }}>bilinmiyor</p>;
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    const text = String(value);
    const isLong = text.length > 220;
    return (
      <div className="memory-explorer__structured-value">
        <p className="list-item__meta memory-explorer__structured-text" style={{ marginBottom: 0 }}>
          {isLong ? `${text.slice(0, 220)}...` : text}
        </p>
        {isLong ? (
          <details className="memory-explorer__expander">
            <summary>Tamamını göster</summary>
            <pre className="memory-explorer__pre">{text}</pre>
          </details>
        ) : null}
      </div>
    );
  }

  const rows = Array.isArray(value)
    ? value.map((item, index) => [`Öğe ${index + 1}`, compactMemoryValue(item, 1)] as const)
    : Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== null && item !== undefined && item !== "")
        .map(([key, item]) => [memoryFieldLabel(key), compactMemoryValue(item, 1)] as const);

  return (
    <div className="memory-explorer__structured-value">
      <div className="memory-explorer__structured-card">
        {title ? <strong>{title}</strong> : null}
        <div className="memory-explorer__structured-grid">
          {rows.slice(0, 8).map(([label, content]) => (
            <div className="memory-explorer__structured-row" key={`${title || "value"}-${label}`}>
              <span className="memory-explorer__structured-label">{label}</span>
              <span className="memory-explorer__structured-content">{content}</span>
            </div>
          ))}
        </div>
      </div>
      {rows.length > 8 || typeof value === "object" ? (
        <details className="memory-explorer__expander">
          <summary>Ham görünüm</summary>
          <pre className="memory-explorer__pre">{JSON.stringify(value, null, 2)}</pre>
        </details>
      ) : null}
    </div>
  );
}

function renderInlineMarkdown(text: string, keyPrefix: string) {
  const normalized = localizeMemoryLine(text);
  if (!normalized) {
    return "";
  }
  const tokens = normalized.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g).filter(Boolean);
  return tokens.map((token, index) => {
    if (/^\*\*[^*]+\*\*$/.test(token)) {
      return <strong key={`${keyPrefix}-strong-${index}`}>{token.slice(2, -2)}</strong>;
    }
    if (/^\*[^*]+\*$/.test(token)) {
      return <em key={`${keyPrefix}-em-${index}`}>{token.slice(1, -1)}</em>;
    }
    if (/^`[^`]+`$/.test(token)) {
      return <code key={`${keyPrefix}-code-${index}`}>{token.slice(1, -1)}</code>;
    }
    return <span key={`${keyPrefix}-text-${index}`}>{token}</span>;
  });
}

function tryFormatJsonLike(text: string) {
  const parsed = parseJsonishText(text);
  if (parsed !== null) {
    const stringified = String(text || "");
    const jsonStart = Math.min(
      ...[stringified.indexOf("{"), stringified.indexOf("[")].filter((value) => value >= 0),
    );
    const prefix = Number.isFinite(jsonStart) && jsonStart >= 0 ? stringified.substring(0, jsonStart) : "";
    return (
      <div style={{ marginTop: "0.35rem" }}>
        {prefix ? <span>{prefix}</span> : null}
        <div style={{ marginTop: "0.5rem" }}>{renderStructuredValue(parsed)}</div>
      </div>
    );
  }

  return null;
}

function parseMemoryMarkdown(markdown?: string | null): MemoryMarkdownBlock[] {
  const lines = String(markdown || "").split(/\r?\n/);
  const blocks: MemoryMarkdownBlock[] = [];
  let paragraphLines: string[] = [];
  let listItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    blocks.push({
      kind: "paragraph",
      text: paragraphLines.join(" ").replace(/\s+/g, " ").trim(),
    });
    paragraphLines = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({ kind: "list", items: [...listItems] });
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = String(rawLine || "").trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        kind: "heading",
        level: Math.min(3, headingMatch[1].length) as 1 | 2 | 3,
        text: localizeMemoryLine(headingMatch[2].trim()),
      });
      continue;
    }
    const listMatch = line.match(/^[-*]\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      listItems.push(localizeMemoryLine(listMatch[1].trim()));
      continue;
    }
    flushList();
    paragraphLines.push(localizeMemoryLine(line));
  }

  flushParagraph();
  flushList();

  return blocks;
}

function renderMemoryMarkdown(markdown?: string | null, options?: { bounded?: boolean }) {
  const blocks = parseMemoryMarkdown(markdown);
  if (!blocks.length) {
    return <p className="list-item__meta" style={{ marginBottom: 0 }}>İçerik yok.</p>;
  }
  return (
    <div className={`memory-explorer__content${options?.bounded ? " memory-explorer__content--bounded" : ""}`}>
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          if (block.level === 1) {
            return <h3 key={`md-heading-${index}`}>{renderInlineMarkdown(block.text, `md-heading-${index}`)}</h3>;
          }
          if (block.level === 2) {
            return <h4 key={`md-heading-${index}`}>{renderInlineMarkdown(block.text, `md-heading-${index}`)}</h4>;
          }
          return <h5 key={`md-heading-${index}`}>{renderInlineMarkdown(block.text, `md-heading-${index}`)}</h5>;
        }
        if (block.kind === "list") {
          return (
            <ul key={`md-list-${index}`}>
              {block.items.map((item, itemIndex) => {
                const formattedJson = tryFormatJsonLike(item);
                return (
                  <li key={`md-list-${index}-${itemIndex}`}>
                    {formattedJson ? formattedJson : renderInlineMarkdown(item, `md-list-${index}-${itemIndex}`)}
                  </li>
                );
              })}
            </ul>
          );
        }
        const formattedJson = tryFormatJsonLike(block.text);
        if (formattedJson) {
           return <div key={`md-paragraph-${index}`}>{formattedJson}</div>;
        }
        return <p key={`md-paragraph-${index}`}>{renderInlineMarkdown(block.text, `md-paragraph-${index}`)}</p>;
      })}
    </div>
  );
}

function MemorySection({
  title,
  subtitle,
  children,
  defaultOpen = false,
  countLabel,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  countLabel?: string;
}) {
  return (
    <details className="memory-explorer__section" open={defaultOpen}>
      <summary className="memory-explorer__section-summary">
        <div className="memory-explorer__section-title">
          <strong>{title}</strong>
          {subtitle ? <span>{subtitle}</span> : null}
        </div>
        {countLabel ? <span className="pill">{countLabel}</span> : null}
      </summary>
      <div className="memory-explorer__section-body">{children}</div>
    </details>
  );
}

function backlinkReasonLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    record_backlink: "Bu sayfayı destekleyen kayıt",
    shared_topic: "Ortak kavram bağlantısı",
    inferred_from: "Buradan türetilmiş bilgi",
    supports: "Bu sayfayı destekliyor",
    related_to: "Bu sayfayla ilişkili",
  };
  if (mapping[normalized]) {
    return mapping[normalized];
  }
  return normalized ? normalized.replaceAll("_", " ") : "";
}

function linkedPageLabel(sharedBacklinks: unknown) {
  const count = Number(sharedBacklinks || 0);
  if (!Number.isFinite(count) || count <= 0) {
    return "İlişkili sayfa";
  }
  return count === 1 ? "1 ortak bağlantı" : `${count} ortak bağlantı`;
}

function buildGraphLayout(nodes: Array<Record<string, unknown>>) {
  const width = 760;
  const height = 420;
  const centerX = width / 2;
  const centerY = height / 2;
  const count = Math.max(nodes.length, 1);
  const radius = Math.min(160, 70 + count * 4);
  const positions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((node, index) => {
    const id = String(node.id || `node-${index}`);
    const angle = (Math.PI * 2 * index) / count - Math.PI / 2;
    positions[id] = {
      x: Math.round(centerX + Math.cos(angle) * radius),
      y: Math.round(centerY + Math.sin(angle) * radius),
    };
  });
  return { width, height, positions };
}

export function MemoryExplorerPage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<ExplorerTab>("pages");
  const [isLoading, setIsLoading] = useState(true);
  const [isPageLoading, setIsPageLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [searchText, setSearchText] = useState("");
  const [pagesResponse, setPagesResponse] = useState<MemoryExplorerPagesResponse | null>(null);
  const [graphResponse, setGraphResponse] = useState<MemoryExplorerGraphResponse | null>(null);
  const [timelineResponse, setTimelineResponse] = useState<MemoryExplorerTimelineResponse | null>(null);
  const [healthResponse, setHealthResponse] = useState<MemoryExplorerHealthResponse | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [selectedPage, setSelectedPage] = useState<MemoryExplorerPageDetail | null>(null);
  const [selectedRecordId, setSelectedRecordId] = useState("");
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editNote, setEditNote] = useState("");
  const [scopeDraft, setScopeDraft] = useState("personal");

  async function refreshOverview(preferredPageId?: string) {
    setError("");
    const [pages, graph, timeline, health] = await Promise.all([
      getMemoryExplorerPages(settings),
      getMemoryExplorerGraph(settings, { limit: 24 }),
      getMemoryExplorerTimeline(settings, { limit: 80 }),
      getMemoryExplorerHealth(settings),
    ]);
    setPagesResponse(pages);
    setGraphResponse(graph);
    setTimelineResponse(timeline);
    setHealthResponse(health);
    const candidateId = preferredPageId || selectedPageId || pages.items.find((item) => item.kind === "wiki_page")?.id || pages.items[0]?.id || "";
    if (candidateId) {
      setSelectedPageId(candidateId);
      return candidateId;
    }
    return "";
  }

  async function refreshSelectedPage(pageId: string) {
    if (!pageId) {
      setSelectedPage(null);
      return;
    }
    setIsPageLoading(true);
    try {
      const page = await getMemoryExplorerPage(settings, pageId);
      setSelectedPage(page);
      const records = Array.isArray(page.records) ? page.records.map(normalizeRecord).filter(Boolean) as MemoryExplorerRecord[] : [];
      const selectedRecord = records.find((item) => String(item.id || "") === selectedRecordId) || records[0] || null;
      const pageScope = Object.keys(page.scope_summary || {})[0] || "personal";
      setSelectedRecordId(String(selectedRecord?.id || ""));
      setEditSummary(String(selectedRecord?.summary || ""));
      setEditNote("");
      setScopeDraft(String(selectedRecord?.scope || pageScope));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bellek sayfası yüklenemedi.");
      setSelectedPage(null);
    } finally {
      setIsPageLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    refreshOverview()
      .then((pageId) => {
        if (cancelled) return;
        if (pageId) {
          return refreshSelectedPage(pageId);
        }
        return undefined;
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Gelişmiş Hafıza yüklenemedi.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [settings]);

  useEffect(() => {
    if (!selectedPageId) return;
    void refreshSelectedPage(selectedPageId);
  }, [selectedPageId]);

  const visiblePages = useMemo(() => {
    const items = pagesResponse?.items || [];
    const query = searchText.trim().toLocaleLowerCase("tr-TR");
    if (!query) return items;
    return items.filter((item) =>
      [
        item.title,
        memoryTitleLabel(item.title),
        item.summary,
        item.kind,
        memoryKindLabel(item.kind),
        item.page_key,
        memoryTitleLabel(item.page_key),
      ].some((part) => String(part || "").toLocaleLowerCase("tr-TR").includes(query))
    );
  }, [pagesResponse, searchText]);

  const selectedRecords = useMemo(() => {
    if (!selectedPage?.records) return [];
    return (selectedPage.records.map(normalizeRecord).filter(Boolean) as MemoryExplorerRecord[]);
  }, [selectedPage]);

  const selectedClaimBindings = useMemo(() => {
    if (!selectedPage?.claim_bindings) return [];
    return (selectedPage.claim_bindings.map(normalizeClaimBinding).filter(Boolean) as MemoryExplorerClaimBinding[]);
  }, [selectedPage]);

  const selectedArticleClaimBindings = useMemo(() => {
    if (!selectedPage?.article_claim_bindings) return [];
    return (selectedPage.article_claim_bindings.map(normalizeArticleClaimBinding).filter(Boolean) as MemoryExplorerArticleClaimBinding[]);
  }, [selectedPage]);

  const selectedRecord = useMemo(
    () => selectedRecords.find((item) => String(item.id || "") === selectedRecordId) || selectedRecords[0] || null,
    [selectedRecordId, selectedRecords],
  );

  useEffect(() => {
    if (!selectedRecord) return;
    setEditSummary(String(selectedRecord.summary || ""));
    setScopeDraft(String(selectedRecord.scope || Object.keys(selectedPage?.scope_summary || {})[0] || "personal"));
  }, [selectedRecord?.id]);

  const graphNodes = useMemo(() => {
    const nodes = (graphResponse?.nodes || []).slice(0, 18);
    return nodes;
  }, [graphResponse]);

  const graphEdges = useMemo(() => {
    const allowedIds = new Set(graphNodes.map((item) => String(item.id || "")));
    return (graphResponse?.edges || []).filter(
      (item) => allowedIds.has(String(item.source || "")) && allowedIds.has(String(item.target || ""))
    ).slice(0, 32);
  }, [graphResponse, graphNodes]);

  const graphLayout = useMemo(() => buildGraphLayout(graphNodes), [graphNodes]);
  const graphNodeTitles = useMemo(
    () =>
      Object.fromEntries(
        graphNodes.map((item) => [String(item.id || ""), memoryTitleLabel(String(item.title || item.id || ""))]),
      ) as Record<string, string>,
    [graphNodes],
  );
  const selectedGraphNode = useMemo(
    () => graphNodes.find((item) => String(item.id || "") === selectedGraphNodeId) || graphNodes[0] || null,
    [graphNodes, selectedGraphNodeId],
  );
  const selectedGraphRelations = useMemo(() => {
    if (!selectedGraphNode) return [];
    const selectedId = String(selectedGraphNode.id || "");
    return graphEdges.filter((edge) => String(edge.source || "") === selectedId || String(edge.target || "") === selectedId);
  }, [graphEdges, selectedGraphNode]);

  useEffect(() => {
    if (!graphNodes.length) return;
    if (!selectedGraphNodeId || !graphNodes.some((item) => String(item.id || "") === selectedGraphNodeId)) {
      setSelectedGraphNodeId(String(graphNodes[0]?.id || ""));
    }
  }, [graphNodes, selectedGraphNodeId]);

  async function handleRecordMutation(kind: "correct" | "reduce_confidence" | "forget" | "change_scope") {
    if (!selectedRecord) return;
    setIsMutating(true);
    setFeedbackMessage("");
    setError("");
    try {
      if (kind === "forget") {
        await forgetMemoryExplorerRecord(settings, {
          page_key: selectedPage?.page_key || undefined,
          target_record_id: String(selectedRecord.id || ""),
          note: editNote || undefined,
          source_refs: selectedRecord.source_refs || [],
        });
        setFeedbackMessage("Kayıt unutuldu.");
      } else if (kind === "change_scope") {
        await changeMemoryExplorerScope(settings, {
          page_key: selectedPage?.page_key || undefined,
          target_record_id: String(selectedRecord.id || ""),
          scope: scopeDraft,
          note: editNote || undefined,
          source_refs: selectedRecord.source_refs || [],
        });
        setFeedbackMessage("Kapsam güncellendi.");
      } else {
        await editMemoryExplorerRecord(settings, {
          action: kind,
          page_key: selectedPage?.page_key || undefined,
          target_record_id: String(selectedRecord.id || ""),
          corrected_summary: kind === "correct" ? editSummary : undefined,
          note: editNote || undefined,
          source_refs: selectedRecord.source_refs || [],
        });
        setFeedbackMessage(kind === "correct" ? "Kayıt düzeltildi." : "Güven düşürüldü.");
      }
      const nextPageId = await refreshOverview(selectedPageId);
      if (nextPageId) {
        await refreshSelectedPage(nextPageId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bellek işlemi uygulanamadı.");
    } finally {
      setIsMutating(false);
    }
  }

  const transparency = pagesResponse?.transparency || selectedPage?.transparency || healthResponse?.transparency || {};
  const summary = pagesResponse?.summary || {};

  if (isLoading) {
    return (
      <SectionCard title="Gelişmiş Hafıza" subtitle="Bilgi ağı hazırlanıyor.">
        <LoadingSpinner label="Bellek yüzeyi yükleniyor..." />
      </SectionCard>
    );
  }

  if (error && !pagesResponse) {
    return (
      <SectionCard title="Gelişmiş Hafıza" subtitle="Asistanın bilgi ağı ve dayanakları burada görünür.">
        <EmptyState title="Gelişmiş Hafıza yüklenemedi" description={error} />
      </SectionCard>
    );
  }

  return (
    <div className="page-grid memory-explorer">
      <SectionCard
        title="Gelişmiş Hafıza"
        subtitle="Asistanın ne bildiğini, nereden öğrendiğini, nasıl değiştiğini ve hangi teknik dayanaklarla çalıştığını izle."
        actions={(
          <div className="memory-explorer__header-actions">
            <button className="button button--secondary" type="button" onClick={() => navigate("/assistant")}>
              Asistana dön
            </button>
            <button className="button button--secondary" type="button" onClick={() => navigate("/settings?tab=profil")}>
              Profil
            </button>
            <button
              className="button"
              type="button"
              onClick={() => {
                setIsLoading(true);
                void refreshOverview(selectedPageId)
                  .then((pageId) => (pageId ? refreshSelectedPage(pageId) : undefined))
                  .finally(() => setIsLoading(false));
              }}
            >
              Yenile
            </button>
          </div>
        )}
      >
        <div className="memory-explorer__hero">
          <div className="memory-explorer__hero-main">
            <div className="callout callout--accent" style={{ marginBottom: "1rem" }}>
              <strong>Bu ekran gelişmiş denetim içindir</strong>
              <p style={{ marginBottom: 0 }}>
                Günlük kullanım için <strong>Asistan</strong> ve <strong>Profil</strong> yeterlidir. Bu yüzey; bilgi ağını, dayanakları, riskleri ve zaman içindeki değişimi ayrıntılı görmek istediğinde kullanılır.
              </p>
            </div>
            <div className="insight-grid">
              <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
                <strong>{Number(summary.total_items || summary.records || 0)}</strong>
                <div>atlas öğesi</div>
              </div>
              <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
                <strong>{Number((healthResponse?.summary?.contradictions as number | undefined) || 0)}</strong>
                <div>çelişki</div>
              </div>
              <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
                <strong>{Number((graphResponse?.summary?.node_count as number | undefined) || 0)}</strong>
                <div>harita düğümü</div>
              </div>
              <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
                <strong>{Number((timelineResponse?.items || []).length)}</strong>
                <div>yakın değişim</div>
              </div>
            </div>
            <div className="memory-explorer__hero-badges">
              {Object.entries(summary).slice(0, 5).map(([key, value]) => (
                <span className="pill" key={key}>{`${memorySummaryLabel(key)}: ${value}`}</span>
              ))}
              {healthResponse?.health_status ? (
                <StatusBadge tone={statusTone(healthResponse.health_status)}>{memoryStatusLabel(healthResponse.health_status)}</StatusBadge>
              ) : null}
            </div>
            <p className="list-item__meta" style={{ marginBottom: 0 }}>
              Bu yüzey wiki yazılarını değil, onların dayandığı kayıt ve claim ağını görünür kılar. Dizin keşif içindir; gerçek çözüm katmanı claim bağlarında kalır.
            </p>
          </div>
          <div className="callout">
            <strong>Nasıl kullanılır?</strong>
            <div className="list" style={{ marginTop: "0.75rem" }}>
              <article className="list-item">
                <strong>Dizin</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>Bir sayfayı veya kavramı aç, sonra sağ taraftan onun claim dayanağını oku.</p>
              </article>
              <article className="list-item">
                <strong>Harita</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>Kavramlar ile kayıtlar arasındaki ilişkiyi düğüm bazında keşfet.</p>
              </article>
              <article className="list-item">
                <strong>Geçmiş ve riskler</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>Ne değişti, hangi bilgi zayıf kaldı, nerede kirlenme riski var burada görünür.</p>
              </article>
              {Object.entries(transparency).slice(0, 2).map(([key, value]) => (
                <article className="list-item" key={key}>
                  <strong>{memoryTransparencyLabel(key)}</strong>
                  <p className="list-item__meta" style={{ marginBottom: 0, wordBreak: "break-all" }}>{renderUnknownValue(value)}</p>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="tabs" style={{ marginTop: "1rem" }}>
          {EXPLORER_TABS.map((tab) => (
            <button
              className={`tab${activeTab === tab.key ? " tab--active" : ""}`}
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </SectionCard>

      {feedbackMessage ? (
        <div className="callout callout--accent">
          <strong>İşlem sonucu</strong>
          <p className="list-item__meta" style={{ marginBottom: 0 }}>{feedbackMessage}</p>
        </div>
      ) : null}
      {error ? (
        <div className="callout">
          <strong>Hata</strong>
          <p className="list-item__meta" style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : null}

      {activeTab === "pages" ? (
        <div className="page-grid page-grid--split memory-explorer__split">
          <SectionCard title="Sayfa dizini" subtitle="Wiki sayfaları, kavram yazıları ve sistem şeffaflık dosyaları." className="sticky-panel">
            <div className="field-grid">
              <input
                className="input"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Bellekte ara..."
              />
              <div className="list memory-explorer__list">
                {visiblePages.map((item) => (
                  <button
                    className={`list-item memory-explorer__page-button${selectedPageId === item.id ? " memory-explorer__page-button--active" : ""}`}
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedPageId(item.id)}
                    >
                    <div className="toolbar memory-explorer__item-header">
                      <strong className="memory-explorer__item-title">{memoryTitleLabel(item.title)}</strong>
                      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                        <StatusBadge>{memoryKindLabel(item.kind)}</StatusBadge>
                        {item.scope ? <StatusBadge tone="neutral">{scopeLabel(item.scope)}</StatusBadge> : null}
                        {Object.entries(item.claim_summary?.status_counts || {}).slice(0, 2).map(([key, value]) => (
                          <StatusBadge key={`${item.id}-claim-${key}`} tone={statusTone(key)}>{`${epistemicStatusLabel(key)}: ${value}`}</StatusBadge>
                        ))}
                      </div>
                    </div>
                    <p className="list-item__meta memory-explorer__item-summary">{item.summary || item.description || ""}</p>
                    <p className="list-item__meta" style={{ marginBottom: 0 }}>
                      {pageMetricLabel(item.record_count, item.backlink_count, item.last_updated)}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title={memoryTitleLabel(selectedPage?.title) || "Sayfa detayı"}
            subtitle={selectedPage?.summary || "Seçili sayfanın özetini, claim dayanağını ve bağlantılarını burada görürsün."}
          >
            {isPageLoading ? (
              <LoadingSpinner label="Sayfa detayı hazırlanıyor..." />
            ) : selectedPage ? (
              <div className="stack">
                <div className="memory-explorer__page-meta">
                  <div className="memory-explorer__hero-badges">
                    <StatusBadge>{memoryKindLabel(selectedPage.kind)}</StatusBadge>
                    {selectedPage.confidence !== null && selectedPage.confidence !== undefined ? (
                      <StatusBadge tone="accent">{`güven ${Math.round(Number(selectedPage.confidence) * 100)}%`}</StatusBadge>
                    ) : null}
                    {Object.keys(selectedPage.scope_summary || {}).slice(0, 3).map((key) => (
                      <StatusBadge key={key} tone="neutral">{`${scopeLabel(key)}: ${(selectedPage.scope_summary || {})[key]}`}</StatusBadge>
                    ))}
                  </div>
                </div>

                <div className="memory-explorer__inner-split">
                  <div className="stack">
                    <MemorySection title="Sayfa özeti" subtitle="Bu sayfanın okunabilir özeti" defaultOpen>
                      {renderMemoryMarkdown(selectedPage.content_markdown, { bounded: true })}
                    </MemorySection>
                    {selectedPage.records?.length ? (
                      <MemorySection title="Kayıtlar" subtitle="Bu sayfayı oluşturan temel öğeler" countLabel={`${selectedRecords.length} kayıt`}>
                        <div className="list" style={{ marginTop: "0.75rem" }}>
                          {selectedRecords.map((record) => (
                            <button
                              className={`list-item memory-explorer__page-button${selectedRecordId === String(record.id || "") ? " memory-explorer__page-button--active" : ""}`}
                              key={String(record.id || record.key || record.title)}
                              type="button"
                              onClick={() => setSelectedRecordId(String(record.id || ""))}
                            >
                              <div className="toolbar memory-explorer__item-header">
                                <strong className="memory-explorer__item-title">{memoryRecordTitle(record)}</strong>
                                <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                                  {record.record_type ? <StatusBadge>{memoryRecordTypeLabel(String(record.record_type))}</StatusBadge> : null}
                                  {record.scope ? <StatusBadge tone="neutral">{scopeLabel(String(record.scope))}</StatusBadge> : null}
                                  {record.confidence !== null && record.confidence !== undefined ? (
                                    <StatusBadge tone="accent">{`${Math.round(Number(record.confidence) * 100)}%`}</StatusBadge>
                                  ) : null}
                                </div>
                              </div>
                              <p className="list-item__meta memory-explorer__item-summary">{memoryRecordSummary(record)}</p>
                            </button>
                          ))}
                        </div>
                      </MemorySection>
                    ) : null}
                  </div>

                  <div className="stack">
                    {selectedClaimBindings.length ? (
                      <MemorySection title="Çözüm bağları" subtitle="Bu yazının hangi claim ağına dayandığı" countLabel={`${selectedClaimBindings.length} bağ`}>
                        <p className="list-item__meta" style={{ marginTop: "0.35rem" }}>
                          Bu sayfadaki anlatım ayrı bir gerçek katmanı değil; aşağıdaki claim çözümünden derlenir.
                        </p>
                        {(selectedPage.claim_summary?.status_counts && Object.keys(selectedPage.claim_summary.status_counts).length) ? (
                          <div className="memory-explorer__hero-badges" style={{ marginTop: "0.75rem" }}>
                            {Object.entries(selectedPage.claim_summary.status_counts || {}).map(([key, value]) => (
                              <StatusBadge key={`claim-status-${key}`} tone={statusTone(key)}>{`${epistemicStatusLabel(key)}: ${value}`}</StatusBadge>
                            ))}
                          </div>
                        ) : null}
                        <div className="list" style={{ marginTop: "0.75rem" }}>
                          {selectedClaimBindings.slice(0, 8).map((item, index) => (
                            <article className="list-item" key={`claim-binding-${index}`}>
                              <div className="toolbar">
                                <strong>{memoryTitleLabel(String(item.record_title || item.predicate || item.current_claim_id || "Claim"))}</strong>
                                <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                                  {item.status ? <StatusBadge tone={statusTone(item.status)}>{epistemicStatusLabel(item.status)}</StatusBadge> : null}
                                  {item.support_strength ? <StatusBadge tone={statusTone(item.support_strength)}>{supportStrengthLabel(item.support_strength)}</StatusBadge> : null}
                                  {item.memory_tier ? <StatusBadge tone={statusTone(item.memory_tier)}>{memoryTierLabel(item.memory_tier)}</StatusBadge> : null}
                                </div>
                              </div>
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                {(item.subject_key || "bilinmiyor")} · {item.predicate || "özellik yok"} · {epistemicBasisLabel(item.basis)}
                              </p>
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                {retrievalEligibilityLabel(item.retrieval_eligibility)}
                                {item.current_claim_id ? ` · claim ${item.current_claim_id}` : ""}
                              </p>
                              {(item.salience_score !== null && item.salience_score !== undefined) || (item.age_days !== null && item.age_days !== undefined) ? (
                                <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                  {item.salience_score !== null && item.salience_score !== undefined ? `Önem skoru: ${Math.round(Number(item.salience_score) * 100)}%` : ""}
                                  {(item.salience_score !== null && item.salience_score !== undefined) && (item.age_days !== null && item.age_days !== undefined) ? " · " : ""}
                                  {item.age_days !== null && item.age_days !== undefined ? `Yaş: ${Number(item.age_days)} gün` : ""}
                                </p>
                              ) : null}
                              {(item.supporting_claim_ids?.length || item.source_claim_ids?.length || item.derived_from_claim_ids?.length) ? (
                                <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                  {item.supporting_claim_ids?.length ? `Destek: ${item.supporting_claim_ids.slice(0, 3).join(", ")}` : ""}
                                  {item.source_claim_ids?.length ? `${item.supporting_claim_ids?.length ? " · " : ""}Kaynak: ${item.source_claim_ids.slice(0, 3).join(", ")}` : ""}
                                  {item.derived_from_claim_ids?.length ? `${(item.supporting_claim_ids?.length || item.source_claim_ids?.length) ? " · " : ""}Türeyen: ${item.derived_from_claim_ids.slice(0, 3).join(", ")}` : ""}
                                </p>
                              ) : null}
                            </article>
                          ))}
                        </div>
                      </MemorySection>
                    ) : null}
                    {selectedArticleClaimBindings.length ? (
                      <MemorySection title="Yazı dayanakları" subtitle="Metin bölümleri hangi claimlerden üretildi" countLabel={`${selectedArticleClaimBindings.length} bölüm`}>
                        <p className="list-item__meta" style={{ marginTop: "0.35rem" }}>
                          Yazı bölümlerinin hangi claim’lerle derlendiği burada görünür.
                        </p>
                        <div className="list" style={{ marginTop: "0.75rem" }}>
                          {selectedArticleClaimBindings.slice(0, 10).map((item, index) => (
                            <article className="list-item" key={`article-claim-${index}`}>
                              <div className="toolbar">
                                <strong>{articleSectionLabel(item.section)}</strong>
                                <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                                  {(item.support_strengths || []).slice(0, 2).map((strength) => (
                                    <StatusBadge key={`${index}-${strength}`} tone={statusTone(strength)}>
                                      {supportStrengthLabel(strength)}
                                    </StatusBadge>
                                  ))}
                                </div>
                              </div>
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                {String(item.text || "")}
                              </p>
                              {item.claim_ids?.length ? (
                                <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                  Claimler: {item.claim_ids.slice(0, 4).join(", ")}
                                </p>
                              ) : null}
                              {(item.anchor || item.offset_start !== null && item.offset_start !== undefined) ? (
                                <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                  {item.anchor ? `Bağ: ${String(item.anchor)}` : ""}
                                  {item.anchor && item.offset_start !== null && item.offset_start !== undefined ? " · " : ""}
                                  {item.offset_start !== null && item.offset_start !== undefined ? `Konum: ${Number(item.offset_start)}-${Number(item.offset_end ?? item.offset_start)}` : ""}
                                </p>
                              ) : null}
                            </article>
                          ))}
                        </div>
                      </MemorySection>
                    ) : null}
                    <MemorySection title="Bağlantılar" subtitle="Bu sayfaya gelen bağlantılar" countLabel={`${(selectedPage.backlinks || []).length} bağlantı`}>
                      <div className="list" style={{ marginTop: "0.75rem" }}>
                        {(selectedPage.backlinks || []).slice(0, 8).map((item, index) => (
                          <article className="list-item" key={`backlink-${index}`}>
                            <strong>{memoryTitleLabel(String((item as Record<string, unknown>).title || "Bağlantı"))}</strong>
                            <p className="list-item__meta" style={{ marginBottom: 0 }}>
                              {backlinkReasonLabel(String((item as Record<string, unknown>).reason || "")) || String((item as Record<string, unknown>).path || "")}
                            </p>
                          </article>
                        ))}
                        {!selectedPage.backlinks?.length ? (
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>Bağlantı yok.</p>
                        ) : null}
                      </div>
                    </MemorySection>
                    <MemorySection title="İlişkili sayfalar" subtitle="Ortak kavram veya ortak bağlantı taşıyan sayfalar" countLabel={`${(selectedPage.linked_pages || []).length} sayfa`}>
                      <div className="list" style={{ marginTop: "0.75rem" }}>
                        {(selectedPage.linked_pages || []).slice(0, 8).map((item, index) => (
                          <article className="list-item" key={`linked-page-${index}`}>
                            <strong>{memoryTitleLabel(String((item as Record<string, unknown>).title || "İlişkili sayfa"))}</strong>
                            <p className="list-item__meta" style={{ marginBottom: 0 }}>
                              {linkedPageLabel((item as Record<string, unknown>).shared_backlinks)}
                            </p>
                          </article>
                        ))}
                        {!selectedPage.linked_pages?.length ? (
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>İlişkili sayfa yok.</p>
                        ) : null}
                      </div>
                    </MemorySection>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState title="Sayfa seçilmedi" description="Sol taraftan bir memory sayfası seç." />
            )}
          </SectionCard>
        </div>
      ) : null}

      {activeTab === "graph" ? (
        <div className="page-grid page-grid--split memory-explorer__split">
          <SectionCard title="Bellek haritası" subtitle="Obsidian benzeri bir keşif yüzeyi: solda düğümler, ortada ağ, sağda seçili düğümün ilişkileri.">
            {graphNodes.length ? (
              <div className="memory-explorer__graph-browser">
                <div className="memory-explorer__graph-list">
                  {graphNodes.map((node) => {
                    const active = String(node.id || "") === String(selectedGraphNode?.id || "");
                    return (
                      <button
                        key={String(node.id || "")}
                        type="button"
                        className={`list-item memory-explorer__page-button${active ? " memory-explorer__page-button--active" : ""}`}
                        onClick={() => setSelectedGraphNodeId(String(node.id || ""))}
                      >
                        <div className="toolbar">
                          <strong>{memoryTitleLabel(String(node.title || node.id || ""))}</strong>
                          <StatusBadge tone={statusTone(String(node.entity_type || node.kind || ""))}>
                            {graphNodeKindLabel(node)}
                          </StatusBadge>
                        </div>
                      </button>
                    );
                  })}
                </div>
                <div className="memory-explorer__graph-shell memory-explorer__graph-shell--focused">
                  <svg
                    className="memory-explorer__graph-canvas"
                    viewBox={`0 0 ${graphLayout.width} ${graphLayout.height}`}
                    role="img"
                    aria-label="Bellek haritası"
                  >
                    {graphEdges.map((edge, index) => {
                    const source = graphLayout.positions[String(edge.source || "")];
                    const target = graphLayout.positions[String(edge.target || "")];
                    if (!source || !target) return null;
                    const isActive = String(edge.source || "") === String(selectedGraphNode?.id || "") || String(edge.target || "") === String(selectedGraphNode?.id || "");
                    return (
                      <line
                        key={`edge-${index}`}
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        stroke="currentColor"
                        opacity={isActive ? "0.48" : "0.16"}
                        strokeWidth={isActive ? "2" : "1.1"}
                      />
                    );
                  })}
                  {graphNodes.map((node, index) => {
                    const position = graphLayout.positions[String(node.id || `node-${index}`)];
                    if (!position) return null;
                    const tone = statusTone(String(node.entity_type || node.kind || ""));
                    const fill = tone === "accent" ? "var(--accent)" : tone === "warning" ? "var(--warning)" : tone === "danger" ? "var(--danger)" : "var(--text-muted)";
                    const active = String(node.id || "") === String(selectedGraphNode?.id || "");
                    return (
                      <g key={String(node.id || index)} onClick={() => setSelectedGraphNodeId(String(node.id || ""))} style={{ cursor: "pointer" }}>
                        <circle cx={position.x} cy={position.y} r={active ? "14" : "11"} fill={fill} opacity={active ? "1" : "0.82"} />
                        <text x={position.x} y={position.y + 22} textAnchor="middle" fontSize="12" fill="currentColor">
                          {memoryTitleLabel(String(node.title || node.id || "")).slice(0, 18)}
                        </text>
                      </g>
                    );
                  })}
                  </svg>
                </div>
              </div>
            ) : (
              <EmptyState title="Harita boş" description="Bellek haritası üretilemedi." />
            )}
          </SectionCard>
          <SectionCard title="Seçili düğüm" subtitle="Sağ panel, haritadaki odak düğümün ne olduğunu ve kimlere bağlandığını açıklar.">
            <div className="stack">
              <div className="callout">
                <strong>{selectedGraphNode ? memoryTitleLabel(String(selectedGraphNode.title || selectedGraphNode.id || "")) : "Düğüm seç"}</strong>
                {selectedGraphNode ? (
                  <>
                    <p className="list-item__meta" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
                      {graphNodeKindLabel(selectedGraphNode)} · {String(selectedGraphNode.id || "")}
                    </p>
                    <div className="memory-explorer__hero-badges" style={{ marginTop: "0.75rem" }}>
                      {Object.entries(graphResponse?.summary || {}).slice(0, 4).map(([key, value]) => (
                        <span className="pill" key={key}>{`${memorySummaryLabel(key)}: ${renderUnknownValue(value)}`}</span>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="list-item__meta" style={{ marginBottom: 0 }}>Soldan bir düğüm seç.</p>
                )}
              </div>
              <div className="callout">
                <strong>İlişkiler</strong>
                <div className="list" style={{ marginTop: "0.75rem" }}>
                  {selectedGraphRelations.map((edge, index) => (
                    <article className="list-item" key={`graph-relation-${index}`}>
                      <strong>{`${graphNodeTitles[String(edge.source || "")] || memoryTitleLabel(String(edge.source || ""))} → ${graphNodeTitles[String(edge.target || "")] || memoryTitleLabel(String(edge.target || ""))}`}</strong>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>{relationLabel(String(edge.relation_type || "related_to"))}</p>
                    </article>
                  ))}
                  {!selectedGraphRelations.length ? (
                    <p className="list-item__meta" style={{ marginBottom: 0 }}>Bu düğüm için görünür ilişki yok.</p>
                  ) : null}
                </div>
              </div>
              <div className="callout">
                <strong>Hızlı geçiş</strong>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={!selectedGraphNode}
                    onClick={() => {
                      setSearchText(String(selectedGraphNode?.title || ""));
                      setActiveTab("pages");
                    }}
                  >
                    Dizinde bul
                  </button>
                  <button className="button button--secondary" type="button" onClick={() => setActiveTab("health")}>
                    Risklere geç
                  </button>
                </div>
              </div>
            </div>
          </SectionCard>
        </div>
      ) : null}

      {activeTab === "timeline" ? (
        <SectionCard title="Bellek zaman akışı" subtitle="Asistanın nasıl öğrendiği, neyi değiştirdiği ve hangi reflection çıktılarının üretildiği kronolojik görünür.">
          <div className="agent-center__timeline memory-explorer__timeline">
            {(timelineResponse?.items || []).map((item) => (
              <article className="agent-center__timeline-item" key={item.id}>
                <div className="agent-center__timeline-marker" />
                <div className="agent-center__timeline-body">
                  <div className="toolbar">
                    <strong>{item.title}</strong>
                    <StatusBadge tone={statusTone(item.event_type)}>{eventLabel(item.event_type)}</StatusBadge>
                  </div>
                  <span>{dateLabel(item.timestamp)}</span>
                  <p>{item.summary}</p>
                </div>
              </article>
            ))}
            {!timelineResponse?.items?.length ? (
              <EmptyState title="Zaman akışı boş" description="Henüz kronolojik memory olayı yok." />
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === "provenance" ? (
        <div className="page-grid page-grid--split memory-explorer__split">
          <SectionCard title="Bilginin dayanağı" subtitle="Seçili kaydın nereden geldiği, nasıl düzeltildiği ve hangi ilişkilere bağlandığı.">
            {selectedRecord ? (
              <div className="stack">
                <div className="callout">
                  <div className="toolbar memory-explorer__item-header">
                    <strong className="memory-explorer__item-title">{memoryRecordTitle(selectedRecord)}</strong>
                    <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                      {selectedRecord.scope ? <StatusBadge>{scopeLabel(String(selectedRecord.scope))}</StatusBadge> : null}
                      {selectedRecord.record_type ? <StatusBadge tone="neutral">{memoryRecordTypeLabel(String(selectedRecord.record_type))}</StatusBadge> : null}
                    </div>
                  </div>
                  {renderRecordSummary(selectedRecord)}
                </div>
                <MemorySection title="Kaynaklar" subtitle="Bu kaydın geldiği ham dayanaklar" defaultOpen countLabel={`${(selectedRecord.source_basis || selectedRecord.source_refs || []).length} kaynak`}>
                  <div className="list" style={{ marginTop: "0.75rem" }}>
                    {(selectedRecord.source_basis || selectedRecord.source_refs || []).map((item, index) => (
                      <article className="list-item" key={`source-${index}`}>
                        {renderStructuredValue(item, `Kaynak ${index + 1}`)}
                      </article>
                    ))}
                    {!selectedRecord.source_basis?.length && !selectedRecord.source_refs?.length ? (
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>Kaynak görünmüyor.</p>
                    ) : null}
                  </div>
                </MemorySection>
                {selectedRecord.metadata && Object.keys(selectedRecord.metadata).length ? (
                  <MemorySection title="Teknik ayrıntı" subtitle="Kaynağın teknik sınıflandırması ve yardımcı alanlar" countLabel={`${Object.keys(selectedRecord.metadata).length} alan`}>
                    {renderStructuredValue(
                      Object.fromEntries(
                        Object.entries(selectedRecord.metadata || {}).map(([key, value]) => [memoryFieldLabel(key), humanizeMetadataValue(key, value)]),
                      ),
                      "Metadata",
                    )}
                  </MemorySection>
                ) : null}
                {selectedRecord.epistemic ? (
                  <MemorySection title="Çözüm durumu" subtitle="Asistanın bu kaydı nasıl değerlendirdiği" defaultOpen>
                    <div className="list" style={{ marginTop: "0.75rem" }}>
                      <article className="list-item">
                        <strong>{epistemicStatusLabel(selectedRecord.epistemic.status)}</strong>
                        <p className="list-item__meta" style={{ marginBottom: 0 }}>
                          {epistemicBasisLabel(selectedRecord.epistemic.current_basis)} · {retrievalEligibilityLabel(selectedRecord.epistemic.retrieval_eligibility)}
                        </p>
                      </article>
                      <article className="list-item">
                        <strong>Asistana görünürlük</strong>
                        <p className="list-item__meta" style={{ marginBottom: 0 }}>
                          {assistantVisibilityFromEpistemic(selectedRecord.epistemic)}
                        </p>
                      </article>
                      {selectedRecord.epistemic.subject_key ? (
                        <article className="list-item">
                          <strong>Özne</strong>
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>{String(selectedRecord.epistemic.subject_key || "")}</p>
                        </article>
                      ) : null}
                      {selectedRecord.epistemic.predicate ? (
                        <article className="list-item">
                          <strong>Özellik</strong>
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>{String(selectedRecord.epistemic.predicate || "")}</p>
                        </article>
                      ) : null}
                      {selectedRecord.epistemic.support_strength ? (
                        <article className="list-item">
                          <strong>Dayanak kalitesi</strong>
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>
                            {supportStrengthLabel(selectedRecord.epistemic.support_strength)}
                          </p>
                        </article>
                      ) : null}
                      {selectedRecord.epistemic.memory_tier ? (
                        <article className="list-item">
                          <strong>Bellek katmanı</strong>
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>
                            {memoryTierLabel(selectedRecord.epistemic.memory_tier)}
                            {(selectedRecord.epistemic.salience_score !== null && selectedRecord.epistemic.salience_score !== undefined)
                              ? ` · önem ${Math.round(Number(selectedRecord.epistemic.salience_score) * 100)}%`
                              : ""}
                            {(selectedRecord.epistemic.age_days !== null && selectedRecord.epistemic.age_days !== undefined)
                              ? ` · ${Number(selectedRecord.epistemic.age_days)} gün`
                              : ""}
                          </p>
                        </article>
                      ) : null}
                      {(selectedRecord.epistemic.external_support_count || selectedRecord.epistemic.self_generated_support_count) ? (
                        <article className="list-item">
                          <strong>Destek zinciri</strong>
                          <p className="list-item__meta" style={{ marginBottom: 0 }}>
                            Harici destek: {Number(selectedRecord.epistemic.external_support_count || 0)} ·
                            asistan üretimi destek: {Number(selectedRecord.epistemic.self_generated_support_count || 0)}
                          </p>
                        </article>
                      ) : null}
                      {selectedRecord.epistemic.support_contaminated ? (
                        <article className="list-item">
                          <strong>Uyarı</strong>
                          <div className="list" style={{ marginTop: "0.35rem" }}>
                            {(selectedRecord.epistemic.support_reason_codes || []).map((item, index) => (
                              <article className="list-item" key={`support-reason-${index}`}>
                                <p className="list-item__meta" style={{ marginBottom: 0 }}>{supportReasonLabel(item)}</p>
                              </article>
                            ))}
                          </div>
                        </article>
                      ) : null}
                    </div>
                  </MemorySection>
                ) : null}
                <MemorySection title="Düzeltme geçmişi" subtitle="Bu kayıt üstünde yapılan değişiklikler" countLabel={`${(selectedRecord.correction_history || []).length} kayıt`}>
                  <div className="list" style={{ marginTop: "0.75rem" }}>
                    {(selectedRecord.correction_history || []).map((item, index) => (
                      <article className="list-item" key={`correction-${index}`}>
                        <strong>{String(item.action || "note")}</strong>
                        <p className="list-item__meta">{renderUnknownValue(item.note || item.to || item.from || item.timestamp)}</p>
                      </article>
                    ))}
                    {!selectedRecord.correction_history?.length ? (
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>Düzeltme geçmişi yok.</p>
                    ) : null}
                  </div>
                </MemorySection>
                <MemorySection
                  title="İlişkiler ve backlinkler"
                  subtitle="Bu kaydın bağlandığı diğer alanlar"
                  countLabel={`${(selectedRecord.relations || []).length + (selectedRecord.backlinks || []).length} bağ`}
                >
                  <div className="list" style={{ marginTop: "0.75rem" }}>
                    {(selectedRecord.relations || []).map((item, index) => (
                      <article className="list-item" key={`relation-${index}`}>
                        <strong>{relationLabel(String(item.relation_type || "related_to"))}</strong>
                        <p className="list-item__meta">{String(item.target || "")}</p>
                      </article>
                    ))}
                    {(selectedRecord.backlinks || []).map((item, index) => (
                      <article className="list-item" key={`backlink-record-${index}`}>
                        <strong>{memoryTitleLabel(String((item as Record<string, unknown>).title || "Bağlantı"))}</strong>
                        <p className="list-item__meta">{String((item as Record<string, unknown>).path || (item as Record<string, unknown>).key || "")}</p>
                      </article>
                    ))}
                    {!selectedRecord.relations?.length && !selectedRecord.backlinks?.length ? (
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>İlişki veya bağlantı görünmüyor.</p>
                    ) : null}
                  </div>
                </MemorySection>
              </div>
            ) : (
              <EmptyState title="Kayıt seçilmedi" description="Sayfalar görünümünden bir kayıt seç." />
            )}
          </SectionCard>

          <SectionCard title="Bellek kontrolü" subtitle="Düzelt, unut, alan değiştir veya güveni azalt.">
            {selectedRecord ? (
              <div className="stack">
                <div className="field-grid">
                  <label className="stack--tight">
                    <span>Düzeltilmiş özet</span>
                    <textarea className="textarea" value={editSummary} onChange={(event) => setEditSummary(event.target.value)} />
                  </label>
                  <label className="stack--tight">
                    <span>Not</span>
                    <textarea className="textarea" value={editNote} onChange={(event) => setEditNote(event.target.value)} />
                  </label>
                  <label className="stack--tight">
                    <span>Yeni scope</span>
                    <select className="select" value={scopeDraft} onChange={(event) => setScopeDraft(event.target.value)}>
                      {Array.from(new Set([scopeDraft, String(selectedRecord.scope || ""), ...DEFAULT_SCOPE_OPTIONS].filter(Boolean))).map((item) => (
                        <option key={item} value={item}>{scopeLabel(item)}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="memory-explorer__header-actions">
                  <button className="button" type="button" disabled={isMutating || !editSummary.trim()} onClick={() => void handleRecordMutation("correct")}>
                    {isMutating ? "İşleniyor..." : "Düzelt"}
                  </button>
                  <button className="button button--secondary" type="button" disabled={isMutating} onClick={() => void handleRecordMutation("reduce_confidence")}>
                    Güveni düşür
                  </button>
                  <button className="button button--secondary" type="button" disabled={isMutating || !scopeDraft.trim()} onClick={() => void handleRecordMutation("change_scope")}>
                    Kapsam taşı
                  </button>
                  <button className="button button--ghost" type="button" disabled={isMutating} onClick={() => void handleRecordMutation("forget")}>
                    Unut
                  </button>
                </div>
              </div>
            ) : (
              <EmptyState title="Düzenlenecek kayıt yok" description="Önce bir memory kaydı seç." />
            )}
          </SectionCard>
        </div>
      ) : null}

      {activeTab === "health" ? (
        <div className="page-grid page-grid--split memory-explorer__split">
          <SectionCard title="Bilgi sağlığı" subtitle="Düşük güven, eskiyen kayıtlar, çelişkiler ve değerlendirme önerileri görünür.">
            <div className="stack">
              <div className="memory-explorer__hero-badges">
                {Object.entries(healthResponse?.summary || {}).slice(0, 8).map(([key, value]) => (
                  <span className="pill" key={key}>{`${memorySummaryLabel(key)}: ${value}`}</span>
                ))}
              </div>
              <MemorySection title="Değerlendirme çıktısı" subtitle="Sistemin kendi bilgi sağlığı özeti" defaultOpen>
                <div className="list" style={{ marginTop: "0.75rem" }}>
                  {(healthResponse?.reflection_output?.user_model_summary as string[] | undefined)?.map((item, index) => (
                    <article className="list-item" key={`reflection-summary-${index}`}>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>{item}</p>
                    </article>
                  ))}
                  {!((healthResponse?.reflection_output?.user_model_summary as string[] | undefined)?.length) ? (
                    <p className="list-item__meta" style={{ marginBottom: 0 }}>Değerlendirme özeti henüz görünmüyor.</p>
                  ) : null}
                </div>
              </MemorySection>
              <MemorySection title="Önerilen aksiyonlar" subtitle="Bilgi kalitesini toparlamak için önerilen işler" countLabel={`${(healthResponse?.recommended_kb_actions || []).length} öneri`}>
                <div className="list" style={{ marginTop: "0.75rem" }}>
                  {(healthResponse?.recommended_kb_actions || []).map((item, index) => (
                    <article className="list-item" key={`kb-action-${index}`}>
                      <strong>{memoryActionLabel(String(item.action || "aksiyon"))}</strong>
                      <p className="list-item__meta">{String(item.reason || "")}</p>
                    </article>
                  ))}
                </div>
              </MemorySection>
              <MemorySection title="Epistemik riskler" subtitle="Zayıf veya kirlenme riski taşıyan claimler" countLabel={`${(healthResponse?.suspicious_claims || []).length} claim`}>
                {(((healthResponse?.claim_summary as Record<string, unknown> | undefined)?.memory_tier_counts as Record<string, number> | undefined) && Object.keys(((healthResponse?.claim_summary as Record<string, unknown> | undefined)?.memory_tier_counts as Record<string, number> | undefined) || {}).length) ? (
                  <div className="memory-explorer__hero-badges" style={{ marginTop: "0.75rem" }}>
                    {Object.entries((((healthResponse?.claim_summary as Record<string, unknown> | undefined)?.memory_tier_counts as Record<string, number> | undefined) || {})).map(([key, value]) => (
                      <StatusBadge key={`memory-tier-${key}`} tone={statusTone(key)}>{`${memoryTierLabel(key)}: ${value}`}</StatusBadge>
                    ))}
                  </div>
                ) : null}
                <div className="list" style={{ marginTop: "0.75rem" }}>
                  {(healthResponse?.suspicious_claims || []).slice(0, 4).map((item, index) => (
                    <article className="list-item" key={`suspicious-claim-${index}`}>
                      <strong>{String(item.subject_key || "claim")} · {String(item.predicate || "özellik")}</strong>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                        {supportStrengthLabel(String(item.support_strength || ""))}
                        {String((item as Record<string, unknown>).memory_tier || "").trim() ? ` · ${memoryTierLabel(String((item as Record<string, unknown>).memory_tier || ""))}` : ""}
                        {(item as Record<string, unknown>).salience_score !== undefined && (item as Record<string, unknown>).salience_score !== null ? ` · önem ${Math.round(Number((item as Record<string, unknown>).salience_score) * 100)}%` : ""}
                      </p>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                        {(Array.isArray(item.reason_codes) ? item.reason_codes : []).map((reason) => supportReasonLabel(String(reason))).join(" ")}
                      </p>
                    </article>
                  ))}
                  {!(healthResponse?.suspicious_claims || []).length ? (
                    <p className="list-item__meta" style={{ marginBottom: 0 }}>Kirli veya döngüsel dayanak görünmüyor.</p>
                  ) : null}
                </div>
              </MemorySection>
              <MemorySection title="Knowledge lint" subtitle="Çelişki, zayıf claim ve boşluk kontrolleri">
                <div className="memory-explorer__hero-badges" style={{ marginTop: "0.75rem" }}>
                  {Object.entries(((healthResponse as Record<string, unknown> | null)?.knowledge_lint as Record<string, unknown> | undefined)?.summary || {}).slice(0, 8).map(([key, value]) => (
                    <span className="pill" key={`lint-${key}`}>{`${memorySummaryLabel(key)}: ${value}`}</span>
                  ))}
                </div>
              </MemorySection>
            </div>
          </SectionCard>

          <SectionCard title="Risk ve boşluklar" subtitle="Asistana görünür hata yüzeyi.">
            <div className="stack">
              {[
                ["Düşük güven", healthResponse?.low_confidence_records || []],
                ["Çelişkiler", healthResponse?.contradictions || []],
                ["Eskiyen kayıtlar", healthResponse?.stale_records || []],
                ["Spam riski", healthResponse?.recommendation_spam_risk || []],
                ["Bilgi boşlukları", healthResponse?.knowledge_gaps || []],
                ["Araştırma konuları", healthResponse?.research_topics || []],
              ].map(([title, items]) => (
                <div className="callout" key={String(title)}>
                  <strong>{String(title)}</strong>
                  <div className="list" style={{ marginTop: "0.75rem" }}>
                    {(items as Array<Record<string, unknown>>).slice(0, 4).map((item, index) => (
                      <article className="list-item" key={`${title}-${index}`}>
                        <strong>{memoryTitleLabel(String(item.title || item.page || item.trigger_type || item.concept_key || "Kayıt"))}</strong>
                        <p className="list-item__meta" style={{ marginBottom: 0 }}>
                          {localizeMemoryLine(String(item.reason || item.age_days || item.count || item.confidence || item.scope || ""))}
                        </p>
                      </article>
                    ))}
                    {!(items as Array<Record<string, unknown>>).length ? (
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>Kayıt yok.</p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      ) : null}
    </div>
  );
}
