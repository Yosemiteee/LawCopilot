import { useEffect, useMemo, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import {
  answerPersonalModelInterview,
  getUserProfile,
  deletePersonalModelFact,
  getPersonalModelOverview,
  pausePersonalModelInterview,
  previewPersonalModelRetrieval,
  resumePersonalModelInterview,
  reviewPersonalModelSuggestion,
  saveUserProfile,
  skipPersonalModelInterviewQuestion,
  startPersonalModelInterview,
  updatePersonalModelFact,
} from "../services/lawcopilotApi";
import type {
  AssistantContextPackEntry,
  PersonalModelFact,
  PersonalModelOverview,
  PersonalModelRetrievalPreview,
  PersonalModelSuggestion,
  ProfileImportantDate,
  ProfileReconciliationSummary,
  RelatedProfile,
  SourcePreferenceRule,
  UserProfile,
} from "../types/domain";

type PersonalModelTab = "overview" | "facts" | "preview" | "history";

const PERSONAL_MODEL_TABS: Array<{ key: PersonalModelTab; label: string }> = [
  { key: "overview", label: "Benim bilgilerim" },
  { key: "facts", label: "Öğrenilmiş bilgiler" },
  { key: "preview", label: "Asistan neyi kullanır?" },
  { key: "history", label: "Geçmiş ve onay" },
];
const SETTINGS_MEMORY_UPDATE_EVENT = "lawcopilot:memory-updates";
const PERSONAL_MODEL_LIVE_REFRESH_INTERVAL_MS = 60000;

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

const PERSONAL_MODEL_EMBEDDED_CACHE = new Map<string, {
  overview: PersonalModelOverview | null;
  profile: UserProfile;
}>();

export function invalidateEmbeddedPersonalModelCache(officeId?: string) {
  if (officeId) {
    PERSONAL_MODEL_EMBEDDED_CACHE.delete(officeId);
    return;
  }
  PERSONAL_MODEL_EMBEDDED_CACHE.clear();
}

function splitCommaList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 12);
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

function normalizeProfile(officeId: string, profile?: Partial<UserProfile> | null): UserProfile {
  const base = createEmptyProfile(officeId);
  return {
    ...base,
    ...(profile || {}),
    display_name: String(profile?.display_name || ""),
    favorite_color: String(profile?.favorite_color || ""),
    food_preferences: String(profile?.food_preferences || ""),
    transport_preference: String(profile?.transport_preference || ""),
    weather_preference: String(profile?.weather_preference || ""),
    travel_preferences: String(profile?.travel_preferences || ""),
    home_base: String(profile?.home_base || ""),
    current_location: String(profile?.current_location || ""),
    location_preferences: String(profile?.location_preferences || ""),
    maps_preference: String(profile?.maps_preference || "Google Maps"),
    prayer_notifications_enabled: Boolean(profile?.prayer_notifications_enabled),
    prayer_habit_notes: String(profile?.prayer_habit_notes || ""),
    communication_style: String(profile?.communication_style || ""),
    assistant_notes: String(profile?.assistant_notes || ""),
    important_dates: Array.isArray(profile?.important_dates)
      ? profile!.important_dates.map((item) => ({
        label: String(item.label || ""),
        date: String(item.date || ""),
        recurring_annually: item.recurring_annually !== false,
        notes: String(item.notes || ""),
        next_occurrence: item.next_occurrence || null,
        days_until: typeof item.days_until === "number" ? item.days_until : null,
      }))
      : [],
    related_profiles: Array.isArray(profile?.related_profiles)
      ? profile!.related_profiles.map((item, index) => ({
        id: String(item.id || `related-${index + 1}`),
        name: String(item.name || ""),
        relationship: String(item.relationship || ""),
        closeness: normalizeCloseness(item.closeness, 3),
        preferences: String(item.preferences || ""),
        notes: String(item.notes || ""),
        important_dates: Array.isArray(item.important_dates)
          ? item.important_dates.map((dateItem) => ({
            label: String(dateItem.label || ""),
            date: String(dateItem.date || ""),
            recurring_annually: dateItem.recurring_annually !== false,
            notes: String(dateItem.notes || ""),
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

function dateLabel(value?: string | null) {
  if (!value) return "bilinmiyor";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("tr-TR");
}

function factTone(fact: PersonalModelFact): "neutral" | "accent" | "warning" | "danger" {
  if (fact.sensitive || fact.never_use) return "warning";
  if (fact.enabled === false) return "danger";
  if (fact.confidence_type === "explicit") return "accent";
  return "neutral";
}

function moduleScopeLabel(value?: string | null) {
  const normalized = String(value || "").trim();
  if (!normalized) return "global";
  if (normalized === "personal") return "kişisel";
  if (normalized === "global") return "genel";
  if (normalized === "workspace") return "çalışma alanı";
  if (normalized.startsWith("project:")) return normalized.replace("project:", "proje:");
  return normalized;
}

function factScopeOptions(overview: PersonalModelOverview | null) {
  const scopes = new Set<string>(["global", "personal"]);
  for (const fact of overview?.facts || []) {
    if (fact.scope) scopes.add(String(fact.scope));
  }
  return Array.from(scopes);
}

function friendlyModuleTitle(value?: string | null) {
  const normalized = String(value || "").trim();
  const mapping: Record<string, string> = {
    goals: "Hedefler",
    work_style: "Çalışma düzeni",
    preferences: "Tercihler",
    communication: "İletişim tarzı",
    Goals: "Hedefler",
    "Work Style": "Çalışma düzeni",
    Preferences: "Tercihler",
    Communication: "İletişim tarzı",
  };
  return mapping[normalized] || normalized || "Modül";
}

function humanConfidenceLabel(value?: number | null, fallback?: string | null) {
  if (fallback) return fallback;
  const percent = Math.round(Number(value || 0) * 100);
  return percent > 0 ? `Bu bilgiden %${percent} eminiz.` : "Bu bilgi henüz zayıf.";
}

function factStatusLabel(fact: PersonalModelFact) {
  if (fact.never_use) return "Yanıtlarda kullanılmıyor";
  if (fact.sensitive) return "Hassas tutuluyor";
  if (fact.enabled === false) return "Şimdilik kapalı";
  return fact.confidence_type === "explicit" ? "Sen söyledin" : "Onaylı çıkarım";
}

function contextVisibilityLabel(entry: AssistantContextPackEntry) {
  return String(entry.assistant_visibility || "").trim() === "blocked" ? "şu an gizleniyor" : "asistana açık";
}

function contextFreshnessLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "bilinmiyor";
  const mapping: Record<string, string> = {
    hot: "çok güncel",
    warm: "yakın geçmiş",
    stable: "kalıcı bilgi",
    stale: "eskimeye yakın",
    unknown: "bilinmiyor",
  };
  return mapping[normalized] || normalized;
}

function contextFamilyLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    personal_model: "benim bilgilerim",
    knowledge_base: "arka plan bilgi katmanı",
    operational: "anlık operasyon",
  };
  return mapping[normalized] || normalized || "bağlam";
}

function reconciliationActionLabel(entry: { field: string; direction?: string | null }) {
  const fieldLabels: Record<string, string> = {
    communication_style: "iletişim tonu",
    food_preferences: "yemek tercihleri",
    transport_preference: "ulaşım tercihi",
    weather_preference: "hava tercihi",
    travel_preferences: "seyahat tercihleri",
    home_base: "ana yaşam alanı",
    maps_preference: "harita tercihi",
  };
  const label = fieldLabels[String(entry.field || "").trim()] || String(entry.field || "profil alanı");
  return String(entry.direction || "").trim() === "fact_to_profile"
    ? `${label} profile geri yazıldı`
    : `${label} hafıza kaydına senkronlandı`;
}

export function PersonalModelPage(
  { embedded = false, hideRelatedProfilesSection = false }: { embedded?: boolean; hideRelatedProfilesSection?: boolean } = {},
) {
  const { settings } = useAppContext();
  const cachedEmbedded = embedded ? PERSONAL_MODEL_EMBEDDED_CACHE.get(settings.officeId) || null : null;
  const [overview, setOverview] = useState<PersonalModelOverview | null>(() => cachedEmbedded?.overview || null);
  const [profile, setProfile] = useState<UserProfile>(() => cachedEmbedded?.profile || createEmptyProfile(settings.officeId));
  const [retrievalPreview, setRetrievalPreview] = useState<PersonalModelRetrievalPreview | null>(null);
  const [isLoading, setIsLoading] = useState(() => !cachedEmbedded);
  const [isMutating, setIsMutating] = useState(false);
  const [isProfileSaving, setIsProfileSaving] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [profileReconciliation, setProfileReconciliation] = useState<ProfileReconciliationSummary | null>(null);
  const [activeTab, setActiveTab] = useState<PersonalModelTab>("overview");
  const [answerText, setAnswerText] = useState("");
  const [choiceValue, setChoiceValue] = useState("");
  const [retrievalQuery, setRetrievalQuery] = useState("Bugün planımı nasıl yönetmeliyim?");
  const [factDrafts, setFactDrafts] = useState<Record<string, { value_text: string; scope: string; note: string }>>({});

  const activeSession = overview?.active_session || null;
  const currentQuestion = activeSession?.current_question || null;
  const scopeOptions = useMemo(() => factScopeOptions(overview), [overview]);
  const hiddenFactsCount = useMemo(
    () => (overview?.facts || []).filter((fact) => fact.never_use || fact.enabled === false || fact.sensitive).length,
    [overview],
  );
  const explicitFactsCount = useMemo(
    () => (overview?.facts || []).filter((fact) => String(fact.confidence_type || "").trim() === "explicit").length,
    [overview],
  );
  const derivedHighlights = useMemo(
    () => (overview?.facts || [])
      .filter((fact) => !fact.never_use && !fact.sensitive && fact.enabled !== false)
      .filter((fact) => ["identity", "career", "communication", "preferences", "routines", "work_style"].includes(String(fact.category || "")))
      .sort((left, right) => {
        const leftSource = String(left.metadata?.source_kind || "");
        const rightSource = String(right.metadata?.source_kind || "");
        const leftExternal = ["connector_observed", "connector_profile_learning", "document_extracted"].includes(leftSource) ? 1 : 0;
        const rightExternal = ["connector_observed", "connector_profile_learning", "document_extracted"].includes(rightSource) ? 1 : 0;
        if (leftExternal !== rightExternal) return rightExternal - leftExternal;
        return String(right.updated_at || "").localeCompare(String(left.updated_at || ""));
      })
      .slice(0, 8),
    [overview],
  );

  async function refreshOverviewAndProfile() {
    const [nextOverview, nextProfile] = await Promise.all([
      getPersonalModelOverview(settings),
      getUserProfile(settings),
    ]);
    const normalizedProfile = normalizeProfile(settings.officeId, nextProfile);
    setOverview(nextOverview);
    setProfile(normalizedProfile);
    if (embedded) {
      PERSONAL_MODEL_EMBEDDED_CACHE.set(settings.officeId, {
        overview: nextOverview,
        profile: normalizedProfile,
      });
    }
    setFactDrafts((current) => {
      const draftState = { ...current };
      for (const fact of nextOverview.facts || []) {
        if (!draftState[fact.id]) {
          draftState[fact.id] = {
            value_text: String(fact.value_text || ""),
            scope: String(fact.scope || "global"),
            note: "",
          };
        }
      }
      return draftState;
    });
    return nextOverview;
  }

  useEffect(() => {
    let cancelled = false;
    if (!embedded || !cachedEmbedded) {
      setIsLoading(true);
    }
    refreshOverviewAndProfile()
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : (embedded ? "Profil bölümü yüklenemedi." : "Benim Bilgilerim bölümü yüklenemedi."));
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [settings]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const handleMemoryUpdate = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail as { kinds?: string[] } | undefined : undefined;
      const kinds = new Set((detail?.kinds || []).map((item) => String(item || "").trim()));
      if (!kinds.has("profile_signal")) {
        return;
      }
      void refreshOverviewAndProfile().catch(() => null);
    };
    window.addEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    return () => {
      window.removeEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    };
  }, [settings]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      if (document.hidden || isMutating || isProfileSaving || isPreviewLoading) {
        return;
      }
      void refreshOverviewAndProfile().catch(() => null);
    }, PERSONAL_MODEL_LIVE_REFRESH_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [embedded, isMutating, isPreviewLoading, isProfileSaving, settings.baseUrl, settings.token]);

  function updateProfileField<K extends keyof UserProfile>(field: K, value: UserProfile[K]) {
    setProfile((current) => ({ ...current, [field]: value }));
    setFeedbackMessage("");
  }

  async function runMutation(task: () => Promise<void>, successMessage: string) {
    setError("");
    setFeedbackMessage("");
    setIsMutating(true);
    try {
      await task();
      setFeedbackMessage(successMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem tamamlanamadı.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSaveProfile() {
    setError("");
    setFeedbackMessage("");
    setIsProfileSaving(true);
    try {
      const response = await saveUserProfile(settings, {
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
        communication_style: profile.communication_style.trim(),
        assistant_notes: profile.assistant_notes.trim(),
        important_dates: profile.important_dates.map((item) => ({
          label: item.label.trim(),
          date: item.date,
          recurring_annually: item.recurring_annually !== false,
          notes: String(item.notes || "").trim() || undefined,
        })),
        related_profiles: profile.related_profiles
          .map((item) => ({
            id: item.id || undefined,
            name: item.name.trim(),
            relationship: item.relationship.trim() || undefined,
            closeness: normalizeCloseness(item.closeness, 3),
            preferences: item.preferences.trim() || undefined,
            notes: item.notes.trim() || undefined,
            important_dates: (item.important_dates || []).map((dateItem) => ({
              label: dateItem.label.trim(),
              date: dateItem.date,
              recurring_annually: dateItem.recurring_annually !== false,
              notes: String(dateItem.notes || "").trim() || undefined,
            })),
          }))
          .filter((item) => item.name),
        contact_profile_overrides: profile.contact_profile_overrides
          .filter((item) => item.contact_id.trim() && item.description.trim())
          .map((item) => ({
            contact_id: item.contact_id.trim(),
            description: item.description.trim(),
            updated_at: item.updated_at || undefined,
          })),
        inbox_watch_rules: profile.inbox_watch_rules.map((rule) => ({
          id: rule.id || undefined,
          label: rule.label,
          match_type: rule.match_type,
          match_value: rule.match_value,
          channels: rule.channels,
        })),
        inbox_keyword_rules: profile.inbox_keyword_rules.map((rule) => ({
          id: rule.id || undefined,
          keyword: rule.keyword,
          label: rule.label || undefined,
          channels: rule.channels,
        })),
        inbox_block_rules: profile.inbox_block_rules.map((rule) => ({
          id: rule.id || undefined,
          label: rule.label,
          match_type: rule.match_type,
          match_value: rule.match_value,
          channels: rule.channels,
          duration_kind: rule.duration_kind,
          starts_at: rule.starts_at || undefined,
          expires_at: rule.expires_at || undefined,
        })),
        source_preference_rules: (profile.source_preference_rules || []).map((rule) => ({
          id: rule.id || undefined,
          label: String(rule.label || "").trim() || undefined,
          task_kind: rule.task_kind,
          policy_mode: rule.policy_mode,
          preferred_domains: (rule.preferred_domains || []).map((value) => value.trim()).filter(Boolean),
          preferred_links: (rule.preferred_links || []).map((value) => value.trim()).filter(Boolean),
          preferred_providers: (rule.preferred_providers || []).map((value) => value.trim()).filter(Boolean),
          note: String(rule.note || "").trim() || undefined,
        })),
      });
      setProfile(normalizeProfile(settings.officeId, response.profile));
      setProfileReconciliation(response.profile_reconciliation || null);
      setFeedbackMessage(response.message || "Bilgiler kaydedildi.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bilgiler kaydedilemedi.");
    } finally {
      setIsProfileSaving(false);
    }
  }

  function addImportantDate() {
    setProfile((current) => ({ ...current, important_dates: [...current.important_dates, createEmptyImportantDate()] }));
  }

  function updateImportantDate(index: number, patch: Partial<ProfileImportantDate>) {
    setProfile((current) => ({
      ...current,
      important_dates: current.important_dates.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    }));
    setFeedbackMessage("");
  }

  function removeImportantDate(index: number) {
    setProfile((current) => ({ ...current, important_dates: current.important_dates.filter((_, itemIndex) => itemIndex !== index) }));
    setFeedbackMessage("");
  }

  function addRelatedProfile() {
    setProfile((current) => ({ ...current, related_profiles: [...current.related_profiles, createEmptyRelatedProfile()] }));
    setFeedbackMessage("");
  }

  function updateRelatedProfileField(index: number, field: "name" | "relationship" | "preferences" | "notes", value: string) {
    setProfile((current) => ({
      ...current,
      related_profiles: current.related_profiles.map((item, itemIndex) => (itemIndex === index ? { ...item, [field]: value } : item)),
    }));
    setFeedbackMessage("");
  }

  function removeRelatedProfile(index: number) {
    setProfile((current) => ({ ...current, related_profiles: current.related_profiles.filter((_, itemIndex) => itemIndex !== index) }));
    setFeedbackMessage("");
  }

  function addSourcePreferenceRule() {
    setProfile((current) => ({
      ...current,
      source_preference_rules: [...(current.source_preference_rules || []), createEmptySourcePreferenceRule()],
    }));
    setFeedbackMessage("");
  }

  function updateSourcePreferenceRule(index: number, patch: Partial<SourcePreferenceRule>) {
    setProfile((current) => ({
      ...current,
      source_preference_rules: (current.source_preference_rules || []).map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    }));
    setFeedbackMessage("");
  }

  function removeSourcePreferenceRule(index: number) {
    setProfile((current) => ({
      ...current,
      source_preference_rules: (current.source_preference_rules || []).filter((_, itemIndex) => itemIndex !== index),
    }));
    setFeedbackMessage("");
  }

  async function handleStartInterview(moduleKeys?: string[]) {
    await runMutation(async () => {
      const response = await startPersonalModelInterview(settings, { module_keys: moduleKeys || [], scope: "personal" });
      setOverview(response.overview);
      setAnswerText("");
      setChoiceValue("");
    }, "Tanıma oturumu başlatıldı.");
  }

  async function handleAnswerQuestion() {
    if (!activeSession?.id || !currentQuestion) return;
    const selectedLabel = (currentQuestion.choices || []).find((item) => item.value === choiceValue)?.label || "";
    const resolvedAnswer = String(answerText || selectedLabel || "").trim();
    if (!resolvedAnswer) {
      setError("Önce bir cevap gir.");
      return;
    }
    await runMutation(async () => {
      const response = await answerPersonalModelInterview(settings, activeSession.id, {
        answer_text: resolvedAnswer,
        choice_value: choiceValue || undefined,
        answer_kind: currentQuestion.input_mode === "choice" ? "choice" : "text",
      });
      setOverview(response.overview);
      setProfileReconciliation(response.profile_reconciliation || null);
      setAnswerText("");
      setChoiceValue("");
    }, "Cevap kaydedildi.");
  }

  async function handlePauseSession() {
    if (!activeSession?.id) return;
    await runMutation(async () => {
      const response = await pausePersonalModelInterview(settings, activeSession.id);
      setOverview(response.overview);
    }, "Tanıma oturumu duraklatıldı.");
  }

  async function handleResumeSession() {
    if (!activeSession?.id) return;
    await runMutation(async () => {
      const response = await resumePersonalModelInterview(settings, activeSession.id);
      setOverview(response.overview);
    }, "Tanıma oturumu kaldığı yerden devam ediyor.");
  }

  async function handleSkipQuestion() {
    if (!activeSession?.id) return;
    await runMutation(async () => {
      const response = await skipPersonalModelInterviewQuestion(settings, activeSession.id);
      setOverview(response.overview);
      setAnswerText("");
      setChoiceValue("");
    }, "Soru atlandı.");
  }

  async function handleUpdateFact(fact: PersonalModelFact) {
    const draft = factDrafts[fact.id] || { value_text: String(fact.value_text || ""), scope: String(fact.scope || "global"), note: "" };
    await runMutation(async () => {
      const response = await updatePersonalModelFact(settings, fact.id, {
        value_text: draft.value_text,
        scope: draft.scope,
        note: draft.note || undefined,
      });
      setOverview(response.overview);
      setProfileReconciliation(response.fact.profile_reconciliation || null);
    }, "Bilgi güncellendi.");
  }

  async function handleToggleFactFlag(fact: PersonalModelFact, field: "enabled" | "never_use" | "sensitive", value: boolean) {
    await runMutation(async () => {
      const response = await updatePersonalModelFact(settings, fact.id, { [field]: value });
      setOverview(response.overview);
      setProfileReconciliation(response.fact.profile_reconciliation || null);
    }, "Bilgi ayarı güncellendi.");
  }

  async function handleDeleteFact(fact: PersonalModelFact) {
    await runMutation(async () => {
      const response = await deletePersonalModelFact(settings, fact.id);
      setOverview(response.overview);
    }, "Bilgi silindi.");
  }

  async function handleSuggestionReview(suggestion: PersonalModelSuggestion, decision: "accept" | "reject") {
    await runMutation(async () => {
      const response = await reviewPersonalModelSuggestion(settings, suggestion.id, { decision });
      setOverview(response.overview);
      setProfileReconciliation(response.profile_reconciliation || null);
    }, decision === "accept" ? "Öneri kabul edildi." : "Öneri reddedildi.");
  }

  async function handlePreviewRetrieval() {
    setError("");
    setIsPreviewLoading(true);
    try {
      const preview = await previewPersonalModelRetrieval(settings, {
        query: retrievalQuery,
        scopes: ["global", "personal"],
        limit: 6,
      });
      setRetrievalPreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kullanım önizlemesi yüklenemedi.");
    } finally {
      setIsPreviewLoading(false);
    }
  }

  if (isLoading) {
    return <LoadingSpinner label={embedded ? "Profil yükleniyor..." : "Benim Bilgilerim yükleniyor..."} />;
  }

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <SectionCard
        title={embedded ? "Profil" : "Benim Bilgilerim"}
        subtitle={embedded
          ? "Seninle ilgili kalıcı bilgiler, tercih kuralları ve öğrenilmiş hafıza burada tek yerde toplanır."
          : "Seninle ilgili kalıcı bilgiler, tercih kuralları ve öğrenilmiş hafıza burada tek yerde toplanır."}
        actions={(
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={activeSession ? "accent" : "neutral"}>{activeSession ? "aktif tanıma" : "hazır"}</StatusBadge>
          </div>
        )}
      >
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <div className="insight-grid">
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
              <strong>{overview?.facts.length || 0}</strong>
              <div>toplam bilgi</div>
            </div>
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
              <strong>{explicitFactsCount}</strong>
              <div>doğrudan senden gelen</div>
            </div>
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
              <strong>{overview?.pending_suggestions.length || 0}</strong>
              <div>onay bekleyen çıkarım</div>
            </div>
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
              <strong>{hiddenFactsCount}</strong>
              <div>şu an kullanılmayan</div>
            </div>
          </div>
          {feedbackMessage ? <div className="notice notice--success">{feedbackMessage}</div> : null}
          {error ? <div className="notice notice--warning">{error}</div> : null}
          <div className="callout callout--accent">
            <strong>{embedded ? "Bu bölüm neyi yönetir?" : "Bu sayfa neyi yönetir?"}</strong>
            <div className="list" style={{ marginTop: "0.75rem" }}>
              <article className="list-item">
                <strong>Kişisel bilgi merkezi</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>Elle verdiğin bilgiler, önemli tarihler, yakın kişiler ve öğrenilmiş tercihler burada birleşir.</p>
              </article>
              <article className="list-item">
                <strong>{embedded ? "Sistem ayarları ayrı tutulur" : "Ayarlar ayrı kaldı"}</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>
                  {embedded
                    ? "Bu sekme kişisel gerçekleri yönetir. Model, entegrasyon ve otomasyon gibi sistem ayarları Ayarlar içindeki diğer sekmelerde kalır."
                    : "Ayarlar artık model, entegrasyon, otomasyon ve iletişim filtreleri içindir. Kişisel gerçekler burada yaşar."}
                </p>
              </article>
              <article className="list-item">
                <strong>Asistan bunları çalışırken kullanır</strong>
                <p className="list-item__meta" style={{ marginBottom: 0 }}>Burada tuttuğun bilgiler cevap kalitesini, önerileri ve araştırma tercihlerini doğrudan etkiler.</p>
              </article>
            </div>
          </div>
          {profileReconciliation?.changed ? (
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px", display: "grid", gap: "0.45rem" }}>
              <strong>Profil eşitlemesi</strong>
              {profileReconciliation.authority_model === "predicate_family_split" ? (
                <div style={{ fontSize: "0.88rem", opacity: 0.8 }}>
                  Kalıcı kişisel gerçek niteliğindeki alanlar bu bellek katmanına yansır. Uygulama ayarı olarak kalan alanlar burada claim üretmez.
                </div>
              ) : null}
              {(profileReconciliation.synced_facts || []).map((entry) => (
                <div key={`sync-${entry.field}-${entry.fact_key || ""}`} style={{ fontSize: "0.9rem", opacity: 0.82 }}>
                  {reconciliationActionLabel(entry)}
                </div>
              ))}
              {(profileReconciliation.hydrated_fields || []).map((entry) => (
                <div key={`hydrate-${entry.field}-${entry.fact_key || ""}`} style={{ fontSize: "0.9rem", opacity: 0.82 }}>
                  {reconciliationActionLabel(entry)}
                </div>
              ))}
              {(profileReconciliation.claim_projection_fields || []).length ? (
                <div style={{ fontSize: "0.84rem", opacity: 0.74, marginTop: "0.15rem" }}>
                  Belleğe yansıyan alanlar: {(profileReconciliation.claim_projection_fields || []).slice(0, 6).map((entry) => entry.title || entry.field).join(", ")}.
                </div>
              ) : null}
              {(profileReconciliation.settings_fields || []).length ? (
                <div style={{ fontSize: "0.84rem", opacity: 0.74 }}>
                  Yalnız ayar olarak kalanlar: {(profileReconciliation.settings_fields || []).slice(0, 6).map((entry) => entry.title || entry.field).join(", ")}.
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
            <strong>Kısa güvenlik özeti</strong>
            <ul style={{ margin: "0.65rem 0 0", paddingLeft: "1rem" }}>
              <li>Senin doğrudan söylediğin bilgiler ile çıkarımlar ayrı tutulur.</li>
              <li>Hassas işaretlenen veya “kullanma” dediğin bilgiler yanıtlara girmez.</li>
              <li>Her bilgiyi tek tek düzeltebilir, taşıyabilir veya silebilirsin.</li>
            </ul>
          </div>
          <div className="tabs" style={{ marginTop: "0.25rem" }}>
            {PERSONAL_MODEL_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`tab${activeTab === tab.key ? " tab--active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </SectionCard>

      {activeTab === "overview" ? (
        <>
      <SectionCard
        title="Şu ana kadar senden öğrendiklerim"
        subtitle="Bağlı hesaplar, belgeler ve onaylı hafıza birlikte değerlendirilir. Asistan cevap üretirken önce buraya bakar."
      >
        <div style={{ display: "grid", gap: "1rem" }}>
          {derivedHighlights.length ? (
            <div style={{ display: "grid", gap: "0.75rem", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              {derivedHighlights.map((fact) => (
                <div key={fact.id} className="surface-subtle" style={{ padding: "0.9rem", borderRadius: "16px", display: "grid", gap: "0.45rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}>
                    <strong>{fact.title || fact.fact_key}</strong>
                    <StatusBadge tone={factTone(fact)}>{factStatusLabel(fact)}</StatusBadge>
                  </div>
                  <div>{fact.value_text}</div>
                  <div style={{ fontSize: "0.84rem", opacity: 0.74 }}>
                    {fact.source_summary || "Bu çıkarım bağlı hesap ve belge sinyallerinden üretildi."}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="Henüz görünür çıkarım yok" description="Hesaplar ve belgeler geldikçe burada daha dolu bir profil özeti oluşur." />
          )}
          {overview?.profile_summary?.markdown ? (
            <div className="surface-subtle" style={{ padding: "0.95rem", borderRadius: "16px", display: "grid", gap: "0.5rem" }}>
              <strong>Kompakt profil özeti</strong>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.9rem" }}>
                {overview.profile_summary.markdown}
              </pre>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Temel bilgiler ve tercihler"
        subtitle="Asistanın seni anlaması için gerekli kişisel bilgiler artık burada düzenlenir."
        actions={(
          <button className="button" type="button" disabled={isProfileSaving} onClick={() => void handleSaveProfile()}>
            {isProfileSaving ? "Kaydediliyor..." : "Bilgileri kaydet"}
          </button>
        )}
      >
        <div style={{ display: "grid", gap: "1rem" }}>
          <div className="field-grid">
            <label className="stack stack--tight">
              <span>Hitap / isim</span>
              <input className="input" value={profile.display_name} onChange={(event) => updateProfileField("display_name", event.target.value)} />
            </label>
            <label className="stack stack--tight">
              <span>Sana karşı üslup tercihi</span>
              <input className="input" value={profile.communication_style} onChange={(event) => updateProfileField("communication_style", event.target.value)} placeholder="Örn: kısa, net, resmi" />
            </label>
            <label className="stack stack--tight">
              <span>Sevdiğin renk</span>
              <input className="input" value={profile.favorite_color} onChange={(event) => updateProfileField("favorite_color", event.target.value)} />
            </label>
            <label className="stack stack--tight">
              <span>Harita tercihi</span>
              <select className="input" value={profile.maps_preference} onChange={(event) => updateProfileField("maps_preference", event.target.value)}>
                <option value="Google Maps">Google Maps</option>
                <option value="Apple Maps">Apple Maps</option>
                <option value="Yandex Maps">Yandex Maps</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>Ana yaşam noktası</span>
              <input className="input" value={profile.home_base} onChange={(event) => updateProfileField("home_base", event.target.value)} placeholder="İstanbul / Kadıköy" />
            </label>
            <label className="stack stack--tight">
              <span>Güncel konum</span>
              <input className="input" value={profile.current_location} onChange={(event) => updateProfileField("current_location", event.target.value)} placeholder="Bugün neredesin?" />
            </label>
            <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
              <span>Çalışma ve kişisel not</span>
              <textarea
                className="textarea"
                rows={3}
                value={profile.assistant_notes}
                onChange={(event) => updateProfileField("assistant_notes", event.target.value)}
                placeholder="Asistanın seni daha iyi anlaması için elle vermek istediğin kısa notlar."
              />
            </label>
          </div>

          <div className="field-grid">
            <label className="stack stack--tight">
              <span>Yeme içme tercihleri</span>
              <textarea className="textarea" rows={3} value={profile.food_preferences} onChange={(event) => updateProfileField("food_preferences", event.target.value)} />
            </label>
            <label className="stack stack--tight">
              <span>Ulaşım tercihi</span>
              <textarea className="textarea" rows={3} value={profile.transport_preference} onChange={(event) => updateProfileField("transport_preference", event.target.value)} />
            </label>
            <label className="stack stack--tight">
              <span>Hava tercihi</span>
              <textarea className="textarea" rows={3} value={profile.weather_preference} onChange={(event) => updateProfileField("weather_preference", event.target.value)} />
            </label>
            <label className="stack stack--tight">
              <span>Seyahat notları</span>
              <textarea className="textarea" rows={3} value={profile.travel_preferences} onChange={(event) => updateProfileField("travel_preferences", event.target.value)} />
            </label>
            <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
              <span>Yakın çevre ve yaşam tercihleri</span>
              <textarea className="textarea" rows={3} value={profile.location_preferences} onChange={(event) => updateProfileField("location_preferences", event.target.value)} />
            </label>
            <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
              <span>Özel rutin / mekan notu</span>
              <textarea className="textarea" rows={3} value={profile.prayer_habit_notes} onChange={(event) => updateProfileField("prayer_habit_notes", event.target.value)} />
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem" }}>
              <input
                type="checkbox"
                checked={profile.prayer_notifications_enabled}
                onChange={(event) => updateProfileField("prayer_notifications_enabled", event.target.checked)}
              />
              özel rutin desteğini açık tut
            </label>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Kaynak ve alışveriş tercihleri"
        subtitle="Asistanın hangi site, marka, sağlayıcı ve sabit bağlantıları önceleyeceğini burada tutarsın."
        actions={(
          <button className="button button--secondary" type="button" onClick={addSourcePreferenceRule}>
            Kaynak tercihi ekle
          </button>
        )}
      >
        {(profile.source_preference_rules || []).length ? (
          <div className="stack stack--tight">
            {(profile.source_preference_rules || []).map((rule, index) => (
              <article className="list-item" key={rule.id || `source-pref-${index}`}>
                <div className="field-grid">
                  <label className="stack stack--tight">
                    <span>İş türü</span>
                    <select className="input" value={rule.task_kind} onChange={(event) => updateSourcePreferenceRule(index, { task_kind: event.target.value })}>
                      {SOURCE_PREFERENCE_TASK_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="stack stack--tight">
                    <span>Davranış</span>
                    <select className="input" value={rule.policy_mode} onChange={(event) => updateSourcePreferenceRule(index, { policy_mode: event.target.value as SourcePreferenceRule["policy_mode"] })}>
                      <option value="prefer">Öncelikle kullan</option>
                      <option value="restrict">Yalnız bunlarda ara</option>
                    </select>
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Kısa başlık</span>
                    <input className="input" value={String(rule.label || "")} onChange={(event) => updateSourcePreferenceRule(index, { label: event.target.value })} />
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Marka / sağlayıcı</span>
                    <input className="input" value={(rule.preferred_providers || []).join(", ")} onChange={(event) => updateSourcePreferenceRule(index, { preferred_providers: splitCommaList(event.target.value) })} />
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Alan adları</span>
                    <input className="input" value={(rule.preferred_domains || []).join(", ")} onChange={(event) => updateSourcePreferenceRule(index, { preferred_domains: splitCommaList(event.target.value) })} />
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Sabit bağlantılar</span>
                    <textarea className="textarea" rows={2} value={(rule.preferred_links || []).join("\n")} onChange={(event) => updateSourcePreferenceRule(index, { preferred_links: splitCommaList(event.target.value) })} />
                  </label>
                  <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                    <span>Not</span>
                    <textarea className="textarea" rows={2} value={String(rule.note || "")} onChange={(event) => updateSourcePreferenceRule(index, { note: event.target.value })} />
                  </label>
                </div>
                <div className="toolbar" style={{ justifyContent: "space-between", marginTop: "0.75rem" }}>
                  <span className="list-item__meta">Sohbette verdiğin “şuradan ara / buradan al” kuralları da burada görünür.</span>
                  <button className="button button--ghost" type="button" onClick={() => removeSourcePreferenceRule(index)}>
                    Kuralı kaldır
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz kaynak tercihi yok" description="Bir site, mağaza veya sağlayıcıyı özellikle kullanmamı istiyorsan burada ekleyebilirsin." />
        )}
      </SectionCard>

      <SectionCard
        title={hideRelatedProfilesSection ? "Önemli tarihler" : "İnsanlar ve tarihler"}
        subtitle={
          hideRelatedProfilesSection
            ? "Yaklaşan kişisel tarihleri burada tut; asistan bunları gerektiğinde kullanır."
            : "Yakın kişileri ve önemli tarihleri tek yerde tut; asistan bunları gerektiğinde kullanır."
        }
      >
        <div style={{ display: "grid", gap: "1rem" }}>
          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <strong>Önemli tarihler</strong>
            <button className="button button--secondary" type="button" onClick={addImportantDate}>
              Tarih ekle
            </button>
          </div>
          {profile.important_dates.length ? (
            <div className="list">
              {profile.important_dates.map((item, index) => (
                <article className="list-item" key={`${item.label}-${item.date}-${index}`}>
                  <div className="field-grid">
                    <label className="stack stack--tight">
                      <span>Başlık</span>
                      <input className="input" value={item.label} onChange={(event) => updateImportantDate(index, { label: event.target.value })} />
                    </label>
                    <label className="stack stack--tight">
                      <span>Tarih</span>
                      <input className="input" type="date" value={item.date} onChange={(event) => updateImportantDate(index, { date: event.target.value })} />
                    </label>
                    <label className="stack stack--tight">
                      <span>Tekrar</span>
                      <select className="input" value={item.recurring_annually ? "yearly" : "single"} onChange={(event) => updateImportantDate(index, { recurring_annually: event.target.value === "yearly" })}>
                        <option value="yearly">Her yıl tekrarlar</option>
                        <option value="single">Tek seferlik</option>
                      </select>
                    </label>
                    <div className="stack stack--tight">
                      <span>&nbsp;</span>
                      <button className="button button--ghost" type="button" onClick={() => removeImportantDate(index)}>Sil</button>
                    </div>
                    <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                      <span>Not</span>
                      <input className="input" value={String(item.notes || "")} onChange={(event) => updateImportantDate(index, { notes: event.target.value })} />
                    </label>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Önemli tarih yok" description="Doğum günü, yıldönümü veya hazırlık gerektiren tarihleri buraya ekleyebilirsin." />
          )}

          {!hideRelatedProfilesSection ? (
            <>
              <div className="toolbar" style={{ justifyContent: "space-between" }}>
                <strong>Yakın kişiler</strong>
                <button className="button button--secondary" type="button" onClick={addRelatedProfile}>
                  Kişi ekle
                </button>
              </div>
              {profile.related_profiles.length ? (
                <div className="stack stack--tight">
                  {profile.related_profiles.map((item, index) => (
                    <article className="list-item" key={item.id || `related-profile-${index}`}>
                      <div className="toolbar">
                        <strong>{item.name || `Kişi ${index + 1}`}</strong>
                        <button className="button button--ghost" type="button" onClick={() => removeRelatedProfile(index)}>Sil</button>
                      </div>
                      <div className="field-grid" style={{ marginTop: "0.75rem" }}>
                        <label className="stack stack--tight">
                          <span>İsim</span>
                          <input className="input" value={item.name} onChange={(event) => updateRelatedProfileField(index, "name", event.target.value)} />
                        </label>
                        <label className="stack stack--tight">
                          <span>Yakınlık</span>
                          <input className="input" value={item.relationship} onChange={(event) => updateRelatedProfileField(index, "relationship", event.target.value)} />
                        </label>
                        <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                          <span>Tercihler ve sevdikleri</span>
                          <textarea className="textarea" rows={2} value={item.preferences} onChange={(event) => updateRelatedProfileField(index, "preferences", event.target.value)} />
                        </label>
                        <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
                          <span>Not</span>
                          <textarea className="textarea" rows={2} value={item.notes} onChange={(event) => updateRelatedProfileField(index, "notes", event.target.value)} />
                        </label>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="Yakın kişi yok" description="Aile, partner, çocuk veya önemli kişiler için kısa profil tutabilirsin." />
              )}
            </>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Seni Daha İyi Tanıyayım"
        subtitle="Uzun bir form değil. Bildiğimiz şeyleri tekrar sormadan, eksik kalan önemli alanları kısa kısa tamamlar."
        actions={
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="button button--secondary" type="button" disabled={!!activeSession || isMutating} onClick={() => handleStartInterview()}>
              Hızlı başlangıç
            </button>
          </div>
        }
      >
        {activeSession ? (
          <div style={{ display: "grid", gap: "0.85rem" }}>
            <div className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
              <strong>Aktif tanıma oturumu</strong>
              <div>Bu oturum {moduleScopeLabel(activeSession.scope)} alanda kullanılacak.</div>
              <div>
                İlerleme: {Number((activeSession.progress as Record<string, unknown> | undefined)?.answered || 0)} /{" "}
                {Number((activeSession.progress as Record<string, unknown> | undefined)?.total || 0)} soru
              </div>
            </div>
            {currentQuestion ? (
              <div style={{ display: "grid", gap: "0.75rem" }}>
                <div>
                  <div style={{ fontSize: "0.85rem", opacity: 0.72 }}>{friendlyModuleTitle(currentQuestion.module_key)}</div>
                  <h3 style={{ margin: "0.2rem 0" }}>{currentQuestion.prompt}</h3>
                  {currentQuestion.help_text ? <p style={{ margin: 0, opacity: 0.78 }}>{currentQuestion.help_text}</p> : null}
                </div>
                {currentQuestion.choices?.length ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {currentQuestion.choices.map((choice) => (
                      <button
                        key={choice.value}
                        type="button"
                        className={choiceValue === choice.value ? "button" : "button button--secondary"}
                        onClick={() => {
                          setChoiceValue(choice.value);
                          setAnswerText(choice.label);
                        }}
                      >
                        {choice.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                <textarea
                  className="input"
                  rows={4}
                  placeholder="Cevabını yaz..."
                  value={answerText}
                  onChange={(event) => setAnswerText(event.target.value)}
                />
                <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                  <button className="button" type="button" disabled={isMutating} onClick={handleAnswerQuestion}>
                    Kaydet
                  </button>
                  <button className="button button--secondary" type="button" disabled={isMutating} onClick={handleSkipQuestion}>
                    Şimdi değil
                  </button>
                  {String(activeSession.status || "") === "paused" ? (
                    <button className="button button--secondary" type="button" disabled={isMutating} onClick={handleResumeSession}>
                      Devam et
                    </button>
                  ) : (
                    <button className="button button--secondary" type="button" disabled={isMutating} onClick={handlePauseSession}>
                      Duraklat
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <EmptyState title="Soru kalmadı" description="Bu oturum tamamlandı. Yeni bir modül başlatabilir veya bilgileri düzenleyebilirsin." />
            )}
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem" }}>
            {(overview?.modules || []).map((module) => (
              <div key={module.key} className="surface-subtle" style={{ padding: "0.9rem", borderRadius: "16px", display: "grid", gap: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}>
                  <strong>{friendlyModuleTitle(module.title || module.key)}</strong>
                  <StatusBadge tone={module.complete ? "accent" : "neutral"}>
                    {module.answered_count}/{module.question_count}
                  </StatusBadge>
                </div>
                <div style={{ opacity: 0.8 }}>{module.description}</div>
                <button className="button button--secondary" type="button" disabled={isMutating} onClick={() => handleStartInterview([module.key])}>
                  Buradan başla
                </button>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Kaydetmeden Önce Sana Sorulanlar" subtitle="Sohbetten fark edilen olası tercihler burada bekler. Onay olmadan kalıcı hale gelmezler.">
        {(overview?.pending_suggestions || []).length ? (
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {overview?.pending_suggestions.map((suggestion) => (
              <div key={suggestion.id} className="surface-subtle" style={{ padding: "0.95rem", borderRadius: "16px", display: "grid", gap: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
                  <strong>{suggestion.title || suggestion.fact_key}</strong>
                  <StatusBadge tone="warning">onay bekliyor</StatusBadge>
                </div>
                <div>{suggestion.learning_reason || suggestion.prompt}</div>
                <div style={{ opacity: 0.8 }}>{suggestion.proposed_value_text}</div>
                <div style={{ fontSize: "0.88rem", opacity: 0.76 }}>
                  {suggestion.why_asked || "Kalıcı hale getirmeden önce onayını istiyoruz."} {humanConfidenceLabel(suggestion.confidence, suggestion.confidence_label)}
                </div>
                <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                  <button className="button" type="button" disabled={isMutating} onClick={() => handleSuggestionReview(suggestion, "accept")}>
                    Evet, kaydet
                  </button>
                  <button className="button button--secondary" type="button" disabled={isMutating} onClick={() => handleSuggestionReview(suggestion, "reject")}>
                    Hayır, kaydetme
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Bekleyen sinyal yok" description="Sohbetten yeni bir olası tercih çıkarsa burada önce onayına sunulur." />
        )}
      </SectionCard>
        </>
      ) : null}

      {activeTab === "facts" ? (
      <SectionCard title="Öğrenilmiş Bilgiler" subtitle="Asistanın seni anlamak için başvurabileceği bilgiler. Her biri tek tek kontrol edilebilir.">
        {(overview?.facts || []).length ? (
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {overview?.facts.map((fact) => {
              const draft = factDrafts[fact.id] || { value_text: String(fact.value_text || ""), scope: String(fact.scope || "global"), note: "" };
              return (
                <div key={fact.id} className="surface-subtle" style={{ padding: "0.95rem", borderRadius: "16px", display: "grid", gap: "0.65rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
                    <div>
                      <strong>{fact.title || fact.fact_key}</strong>
                      <div style={{ fontSize: "0.86rem", opacity: 0.76 }}>
                        {friendlyModuleTitle(fact.category || "")} · {moduleScopeLabel(fact.scope)} · {factStatusLabel(fact)}
                      </div>
                    </div>
                    <StatusBadge tone={factTone(fact)}>{factStatusLabel(fact)}</StatusBadge>
                  </div>
                  <div style={{ fontSize: "0.9rem", lineHeight: 1.5 }}>
                    <div>{humanConfidenceLabel(fact.confidence, fact.confidence_label)}</div>
                    <div style={{ opacity: 0.78 }}>{fact.why_known || "Bu bilgi önceki kullanımından öğrenildi."}</div>
                    <div style={{ opacity: 0.78 }}>{fact.usage_label || "Yalnız ilgili olduğunda kullanılır."}</div>
                    <div style={{ opacity: 0.72 }}>Kaynak: {fact.source_summary || "Kaynak özeti yok."}</div>
                  </div>
                  <input
                    className="input"
                    value={draft.value_text}
                    onChange={(event) => setFactDrafts((current) => ({ ...current, [fact.id]: { ...draft, value_text: event.target.value } }))}
                  />
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 220px) minmax(0, 1fr)", gap: "0.75rem" }}>
                    <select
                      className="input"
                      value={draft.scope}
                      onChange={(event) => setFactDrafts((current) => ({ ...current, [fact.id]: { ...draft, scope: event.target.value } }))}
                    >
                      {scopeOptions.map((scopeValue) => (
                        <option key={scopeValue} value={scopeValue}>
                          {moduleScopeLabel(scopeValue)}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input"
                      placeholder="İstersen kısa bir not bırak"
                      value={draft.note}
                      onChange={(event) => setFactDrafts((current) => ({ ...current, [fact.id]: { ...draft, note: event.target.value } }))}
                    />
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                    <button className="button button--secondary" type="button" disabled={isMutating} onClick={() => handleUpdateFact(fact)}>
                      Düzelt
                    </button>
                    <button className="button button--ghost" type="button" disabled={isMutating} onClick={() => handleDeleteFact(fact)}>
                      Unut
                    </button>
                    <button
                      className="button button--secondary"
                      type="button"
                      disabled={isMutating}
                      onClick={() => handleToggleFactFlag(fact, "never_use", !fact.never_use)}
                    >
                      {fact.never_use ? "Tekrar kullan" : "Bu konuda önerme"}
                    </button>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem" }}>
                      <input type="checkbox" checked={fact.enabled !== false} onChange={(event) => handleToggleFactFlag(fact, "enabled", event.target.checked)} />
                      kullanılsın
                    </label>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem" }}>
                      <input type="checkbox" checked={!!fact.sensitive} onChange={(event) => handleToggleFactFlag(fact, "sensitive", event.target.checked)} />
                      hassas tut
                    </label>
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", fontSize: "0.84rem", opacity: 0.72 }}>
                    <span>Son güncelleme: {dateLabel(fact.updated_at)}</span>
                    <span>•</span>
                    <span>{fact.scope_label || moduleScopeLabel(fact.scope)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState title="Henüz bilgi yok" description="Tanıma oturumu veya onaylı sohbet öğrenmeleri geldikçe burada görünür." />
        )}
      </SectionCard>
      ) : null}

      {activeTab === "preview" ? (
      <SectionCard title="Bir İstekte Neleri Kullanırım?" subtitle="Asistan her istekte tüm belleği taşımaz; yalnız ilgili bilgileri seçer.">
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "0.75rem" }}>
            <input className="input" value={retrievalQuery} onChange={(event) => setRetrievalQuery(event.target.value)} />
            <button className="button button--secondary" type="button" disabled={isPreviewLoading} onClick={handlePreviewRetrieval}>
              {isPreviewLoading ? "Bakılıyor..." : "Göster"}
            </button>
          </div>
          {retrievalPreview ? (
            <div className="surface-subtle" style={{ padding: "0.95rem", borderRadius: "16px", display: "grid", gap: "0.6rem" }}>
              <div>
                <strong>İstek türü:</strong> {String(retrievalPreview.intent?.name || "general")}
              </div>
              <div>
                <strong>Bakılan alanlar:</strong> {(retrievalPreview.selected_categories || []).join(", ") || "yok"}
              </div>
              <div>
                <strong>Not:</strong> {retrievalPreview.usage_note}
              </div>
              <ul style={{ margin: 0, paddingLeft: "1rem" }}>
                {(retrievalPreview.facts || []).map((fact) => (
                  <li key={fact.id}>
                    {fact.title}: {fact.value_text}
                    {fact.selection_reason_labels?.length ? ` (${fact.selection_reason_labels.join(", ")})` : ""}
                  </li>
                ))}
              </ul>
              {(retrievalPreview.assistant_context_pack || []).length ? (
                <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.35rem" }}>
                  <strong>Asistanın bu istekte gerçekten gördüğü bağlam</strong>
                  {(retrievalPreview.assistant_context_pack || []).slice(0, 6).map((entry) => (
                    <div key={String(entry.id || `${entry.family}-${entry.source_ref}-${entry.predicate}`)} className="surface-subtle" style={{ padding: "0.75rem", borderRadius: "12px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                        <strong>{entry.title || entry.predicate || "Bağlam girdisi"}</strong>
                        <StatusBadge tone={entry.assistant_visibility === "blocked" ? "warning" : "accent"}>{contextVisibilityLabel(entry)}</StatusBadge>
                      </div>
                      <div style={{ fontSize: "0.85rem", opacity: 0.8, marginTop: "0.25rem" }}>
                        {contextFamilyLabel(entry.family)} · {moduleScopeLabel(entry.scope)} · {contextFreshnessLabel(entry.freshness)}
                      </div>
                      <div style={{ marginTop: "0.35rem" }}>{entry.summary || entry.prompt_line || "Özet görünmüyor."}</div>
                      <div style={{ fontSize: "0.84rem", opacity: 0.76, marginTop: "0.35rem" }}>
                        {entry.why_visible || entry.why_blocked || "Bu kayıt seçilen bağlam paketinin bir parçası."}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </SectionCard>
      ) : null}

      {activeTab === "history" ? (
      <SectionCard title="Nasıl Öğrendim?" subtitle="Görüşmelerden ve onay verdiğin sohbet çıkarımlarından gelen ham kayıtlar burada tutulur.">
        {(overview?.raw_entries || []).length ? (
          <div style={{ display: "grid", gap: "0.6rem" }}>
            {overview?.raw_entries.slice(0, 12).map((entry) => (
              <div key={String(entry.id)} className="surface-subtle" style={{ padding: "0.85rem", borderRadius: "16px" }}>
                <strong>{entry.question_text}</strong>
                <div style={{ marginTop: "0.35rem" }}>{entry.answer_text}</div>
                <div style={{ marginTop: "0.35rem", fontSize: "0.82rem", opacity: 0.72 }}>
                  {entry.source === "interview" ? "Görüşme" : "Sohbet"} · {entry.confidence_type === "explicit" ? "doğrudan bilgi" : "onaylı çıkarım"} · {dateLabel(entry.created_at)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz ham kayıt yok" description="Tanıma oturumu cevapları burada ham kayıt olarak görünür." />
        )}
      </SectionCard>
      ) : null}
    </div>
  );
}

export default PersonalModelPage;
