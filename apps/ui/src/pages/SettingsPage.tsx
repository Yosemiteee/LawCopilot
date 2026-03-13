import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import {
  baglayiciDurumuEtiketi,
  dagitimKipiEtiketi,
  modelProfilEtiketi,
  runtimeDurumuEtiketi,
  surumKanaliEtiketi,
} from "../lib/labels";
import { sozluk } from "../i18n";
import {
  getAssistantToolsStatus,
  getAssistantRuntimeProfile,
  getAssistantRuntimeWorkspace,
  getHealth,
  getModelProfiles,
  getTelemetryHealth,
  getUserProfile,
  saveAssistantRuntimeProfile,
  getWorkspaceOverview,
  saveUserProfile,
} from "../services/lawcopilotApi";
import type {
  AssistantRuntimeProfile,
  AssistantRuntimeWorkspaceStatus,
  AssistantToolStatus,
  Health,
  ModelProfilesResponse,
  TelemetryHealth,
  UserProfile,
  WorkspaceOverviewResponse,
} from "../types/domain";

function appendLegacyLine(lines: string[], label: string, value: string | null | undefined) {
  const cleaned = String(value || "").trim();
  if (cleaned) {
    lines.push(`${label}: ${cleaned}`);
  }
}

function buildProfileNarrative(profile?: Partial<UserProfile> | null) {
  const explicit = String(profile?.assistant_notes || "").trim();
  if (explicit) {
    return explicit;
  }
  const lines: string[] = [];
  appendLegacyLine(lines, "Ulaşım tercihi", profile?.transport_preference);
  appendLegacyLine(lines, "Hava tercihi", profile?.weather_preference);
  appendLegacyLine(lines, "İletişim stili", profile?.communication_style);
  appendLegacyLine(lines, "Yeme içme tercihleri", profile?.food_preferences);
  appendLegacyLine(lines, "Seyahat notları", profile?.travel_preferences);
  for (const item of profile?.important_dates || []) {
    const label = String(item.label || "").trim();
    const date = String(item.date || "").trim();
    const notes = String(item.notes || "").trim();
    if (label || date || notes) {
      lines.push(
        `Önemli tarih: ${label || "Plan"}${date ? ` (${date})` : ""}${notes ? ` - ${notes}` : ""}`,
      );
    }
  }
  return lines.join("\n");
}

function buildAssistantBehaviorNarrative(profile?: Partial<AssistantRuntimeProfile> | null) {
  const explicit = String(profile?.soul_notes || "").trim();
  if (explicit) {
    return explicit;
  }
  const lines: string[] = [];
  appendLegacyLine(lines, "Temel rol", profile?.role_summary);
  appendLegacyLine(lines, "Ton", profile?.tone);
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

function splitChecklist(value: string) {
  return value
    .split("\n")
    .map((item) => item.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 12);
}

function eventTitle(event: Record<string, unknown>) {
  return String(event.event_type || event.type || event.name || "Olay");
}

function createEmptyProfile(officeId: string): UserProfile {
  return {
    office_id: officeId,
    display_name: "",
    food_preferences: "",
    transport_preference: "",
    weather_preference: "",
    travel_preferences: "",
    communication_style: "",
    assistant_notes: "",
    important_dates: [],
    created_at: null,
    updated_at: null,
  };
}

function normalizeProfile(officeId: string, profile?: Partial<UserProfile> | null): UserProfile {
  const base = createEmptyProfile(officeId);
  return {
    ...base,
    ...(profile || {}),
    assistant_notes: buildProfileNarrative(profile),
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
  };
}

function createEmptyAssistantRuntimeProfile(officeId: string): AssistantRuntimeProfile {
  return {
    office_id: officeId,
    assistant_name: "",
    role_summary: "Kaynak dayanaklı hukuk çalışma asistanı",
    tone: "Net ve profesyonel",
    avatar_path: "",
    soul_notes: "",
    tools_notes: "",
    heartbeat_extra_checks: [],
    created_at: null,
    updated_at: null,
  };
}

function normalizeAssistantRuntimeProfile(officeId: string, profile?: Partial<AssistantRuntimeProfile> | null): AssistantRuntimeProfile {
  const base = createEmptyAssistantRuntimeProfile(officeId);
  return {
    ...base,
    ...(profile || {}),
    soul_notes: buildAssistantBehaviorNarrative(profile),
    tools_notes: buildAssistantOperationsNarrative(profile),
    heartbeat_extra_checks: Array.isArray(profile?.heartbeat_extra_checks)
      ? profile!.heartbeat_extra_checks.map((item) => String(item || ""))
      : [],
  };
}

export function SettingsPage() {
  const { settings, setSettings, setWorkspace, setCurrentMatter } = useAppContext();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"profile" | "appearance" | "workspace" | "integrations" | "system">("profile");
  const [profiles, setProfiles] = useState<ModelProfilesResponse | null>(null);
  const [health, setHealth] = useState<TelemetryHealth | null>(null);
  const [workspace, setWorkspaceOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [connectionHealth, setConnectionHealth] = useState<Health | null>(null);
  const [profile, setProfile] = useState<UserProfile>(createEmptyProfile(settings.officeId));
  const [assistantRuntimeProfile, setAssistantRuntimeProfile] = useState<AssistantRuntimeProfile>(createEmptyAssistantRuntimeProfile(settings.officeId));
  const [assistantRuntimeWorkspace, setAssistantRuntimeWorkspace] = useState<AssistantRuntimeWorkspaceStatus | null>(null);
  const [assistantToolsStatus, setAssistantToolsStatus] = useState<AssistantToolStatus[]>([]);
  const [error, setError] = useState("");
  const [desktopConfigSaved, setDesktopConfigSaved] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [assistantRuntimeMessage, setAssistantRuntimeMessage] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingAssistantRuntime, setIsSavingAssistantRuntime] = useState(false);
  const desktopReady = Boolean(window.lawcopilotDesktop);

  async function refreshSettingsSurface() {
    const [healthResponse, profileResponse, telemetryResponse, workspaceResponse, userProfileResponse, runtimeProfileResponse, runtimeWorkspaceResponse, toolsStatusResponse] = await Promise.all([
      getHealth(settings),
      getModelProfiles(settings),
      getTelemetryHealth(settings),
      getWorkspaceOverview(settings),
      getUserProfile(settings),
      getAssistantRuntimeProfile(settings).catch(() => createEmptyAssistantRuntimeProfile(settings.officeId)),
      getAssistantRuntimeWorkspace(settings).catch(() => null),
      getAssistantToolsStatus(settings).catch(() => ({ items: [], generated_from: "connector_registry" })),
    ]);

    setConnectionHealth(healthResponse);
    setProfiles(profileResponse);
    setHealth(telemetryResponse);
    setWorkspaceOverview(workspaceResponse);
    setProfile(normalizeProfile(healthResponse.office_id, userProfileResponse));
    setAssistantRuntimeProfile(normalizeAssistantRuntimeProfile(healthResponse.office_id, runtimeProfileResponse));
    setAssistantRuntimeWorkspace(runtimeWorkspaceResponse);
    setAssistantToolsStatus(toolsStatusResponse.items || []);
    setSettings({
      deploymentMode: healthResponse.deployment_mode,
      officeId: healthResponse.office_id,
      releaseChannel: healthResponse.release_channel || settings.releaseChannel,
      selectedModelProfile: healthResponse.default_model_profile || settings.selectedModelProfile,
    });
    setWorkspace({
      workspaceConfigured: Boolean(healthResponse.workspace_configured),
      workspaceRootName: String(healthResponse.workspace_root_name || settings.workspaceRootName),
      workspaceRootPath: workspaceResponse.workspace?.root_path || settings.workspaceRootPath,
      workspaceRootHash: workspaceResponse.workspace?.root_path_hash || settings.workspaceRootHash,
    });
    setError("");
  }

  useEffect(() => {
    refreshSettingsSurface().catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function saveDesktopMode(mode: string) {
    setSettings({ deploymentMode: mode });
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      return;
    }
    try {
      await window.lawcopilotDesktop.saveStoredConfig({ deploymentMode: mode });
      setDesktopConfigSaved(sozluk.settings.desktopModeSaved);
    } catch {
      setDesktopConfigSaved(sozluk.settings.desktopModeSaveError);
    }
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

  async function saveModelProfile(value: string) {
    setSettings({ selectedModelProfile: value });
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      return;
    }
    try {
      await window.lawcopilotDesktop.saveStoredConfig({ selectedModelProfile: value });
      setDesktopConfigSaved(sozluk.settings.modelProfileSaved);
    } catch {
      setDesktopConfigSaved(sozluk.settings.desktopModeSaveError);
    }
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
      setWorkspace({
        workspaceConfigured: Boolean(chosen.workspaceRootPath),
        workspaceRootName: String(chosen.workspaceRootName || ""),
        workspaceRootPath: String(chosen.workspaceRootPath || ""),
        workspaceRootHash: String(chosen.workspaceRootHash || ""),
      });
      setCurrentMatter(null, "");
      await refreshSettingsSurface();
      setDesktopConfigSaved(sozluk.settings.workspaceChanged);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.workspaceChangeError);
    }
  }

  function updateProfileField(field: keyof UserProfile, value: string) {
    setProfile((current) => ({ ...current, [field]: value }));
    setProfileMessage("");
  }

  function updateAssistantRuntimeField(field: keyof AssistantRuntimeProfile, value: string) {
    setAssistantRuntimeProfile((current) => ({ ...current, [field]: value }));
    setAssistantRuntimeMessage("");
  }

  async function handleSaveProfile() {
    setIsSavingProfile(true);
    try {
      const response = await saveUserProfile(settings, {
        display_name: profile.display_name,
        food_preferences: "",
        transport_preference: "",
        weather_preference: "",
        travel_preferences: "",
        communication_style: "",
        assistant_notes: profile.assistant_notes.trim(),
        important_dates: [],
      });
      setProfile(normalizeProfile(settings.officeId, response.profile));
      const runtimeWorkspace = await getAssistantRuntimeWorkspace(settings).catch(() => null);
      setAssistantRuntimeWorkspace(runtimeWorkspace);
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
        heartbeat_extra_checks: splitChecklist(assistantRuntimeProfile.tools_notes),
      });
      setAssistantRuntimeProfile(normalizeAssistantRuntimeProfile(settings.officeId, response.profile));
      setAssistantRuntimeWorkspace(response.workspace);
      setAssistantRuntimeMessage(response.message);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.assistantRuntimeSaveError);
    } finally {
      setIsSavingAssistantRuntime(false);
    }
  }

  const setupBadges = useMemo(() => {
    const items = [
      <StatusBadge key="mode" tone="accent">
        {dagitimKipiEtiketi(settings.deploymentMode)}
      </StatusBadge>,
      <StatusBadge key="profile">{modelProfilEtiketi(settings.selectedModelProfile)}</StatusBadge>,
      <StatusBadge key="office">{settings.officeId}</StatusBadge>,
      <StatusBadge key="channel">{surumKanaliEtiketi(settings.releaseChannel)}</StatusBadge>,
    ];
    if (health?.provider_configured) {
      items.push(
        <StatusBadge key="provider" tone="accent">
          {sozluk.settings.providerConfigured}
        </StatusBadge>,
      );
    }
    if (health?.telegram_configured) {
      items.push(
        <StatusBadge key="telegram" tone="accent">
          {sozluk.settings.telegramConfigured}
        </StatusBadge>,
      );
    }
    return items;
  }, [
    health?.provider_configured,
    health?.telegram_configured,
    settings.deploymentMode,
    settings.officeId,
    settings.releaseChannel,
    settings.selectedModelProfile,
  ]);

  return (
    <div className="settings-surface">
      <div className="toolbar settings-surface__header" style={{ padding: "0.5rem 0 1.5rem", borderBottom: "1px solid var(--line-soft)", marginBottom: "1rem" }}>
        <div>
          <h1 style={{ margin: 0, fontFamily: "var(--font-heading)", fontSize: "1.8rem" }}>{sozluk.navigation.find((n) => n.to === "/settings")?.label || "Ayarlar"}</h1>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)" }}>Sistem ve kişisel tercihlerinizi yapılandırın.</p>
        </div>
        <button className="button button--secondary" type="button" onClick={() => navigate("/assistant")}>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "0.5rem" }}><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          Ayarları Kapat
        </button>
      </div>
      <div className="page-grid page-grid--settings settings-layout">
        {/* Sidebar Tabs */}
        <div className="tabs tabs--vertical settings-layout__sidebar">
          <button
            className={`tab ${activeTab === "profile" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("profile")}
          >
            {sozluk.settings.personalProfileTitle}
          </button>
          <button
            className={`tab ${activeTab === "appearance" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("appearance")}
          >
            Arayüz & Tema
          </button>
          <button
            className={`tab ${activeTab === "workspace" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("workspace")}
          >
            {sozluk.settings.setupTitle}
          </button>
          <button
            className={`tab ${activeTab === "integrations" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("integrations")}
          >
            Bağlantılar
          </button>
          <button
            className={`tab ${activeTab === "system" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("system")}
          >
            Sistem & Tanı
          </button>
        </div>

        {/* Tab Content */}
        <div className="stack settings-layout__content">
          {activeTab === "appearance" && (
            <SectionCard
              title={sozluk.settings.themeStatusTitle}
              subtitle={sozluk.settings.themeQuickSubtitle}
            >
        <div className="theme-picker">
          <div className="theme-picker__options">
            {([
              {
                mode: "system" as const,
                title: sozluk.settings.themeSystem,
                description: sozluk.settings.themeSystemDescription,
              },
              {
                mode: "light" as const,
                title: sozluk.settings.themeLight,
                description: sozluk.settings.themeLightDescription,
              },
              {
                mode: "dark" as const,
                title: sozluk.settings.themeDark,
                description: sozluk.settings.themeDarkDescription,
              },
            ]).map((item) => (
              <button
                key={item.mode}
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
          {desktopConfigSaved ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{desktopConfigSaved}</p> : null}
        </div>
      </SectionCard>
      )}

      {activeTab === "workspace" && (
        <div className="stack">
        <SectionCard
          title={sozluk.settings.setupTitle}
        subtitle={sozluk.settings.setupSubtitle}
        actions={
          settings.workspaceConfigured ? (
            <button className="button button--secondary" type="button" onClick={() => navigate("/workspace")}>
              {sozluk.settings.openWorkspaceAction}
            </button>
          ) : null
        }
      >
        <div className="page-grid page-grid--setup">
          <div className="stack">
            <div className="callout callout--accent">
              <strong>{sozluk.settings.setupWorkspaceTitle}</strong>
              <p style={{ marginBottom: 0 }}>{sozluk.settings.setupWorkspaceDescription}</p>
            </div>
            <div className="toolbar">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>{setupBadges}</div>
              <button className="button" type="button" onClick={chooseWorkspaceRoot}>
                {settings.workspaceConfigured ? sozluk.settings.workspaceChange : sozluk.workspace.choose}
              </button>
            </div>
            <label className="stack stack--tight">
              <span>{sozluk.settings.mode}</span>
              <select className="select" value={settings.deploymentMode} onChange={(event) => saveDesktopMode(event.target.value)}>
                <option value="local-only">Yalnız yerel</option>
                <option value="local-first-hybrid">Yerel öncelikli hibrit</option>
                <option value="cloud-assisted">Bulut destekli</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>{sozluk.settings.modelProfile}</span>
              <select className="select" value={settings.selectedModelProfile} onChange={(event) => saveModelProfile(event.target.value)}>
                {Object.keys(profiles?.profiles || { local: {}, hybrid: {}, cloud: {} }).map((name) => (
                  <option key={name} value={name}>
                    {modelProfilEtiketi(name)}
                  </option>
                ))}
              </select>
            </label>
            {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
          </div>

          <div className="stack">
            <SectionCard title={sozluk.settings.setupStatusTitle} subtitle={sozluk.settings.setupStatusSubtitle}>
              <div className="stack">
                <div className="callout">
                  <strong>{settings.workspaceConfigured ? settings.workspaceRootName || sozluk.settings.workspaceTitle : sozluk.settings.workspaceMissingTitle}</strong>
                  <p style={{ marginBottom: 0 }}>
                    {workspace?.workspace?.root_path || sozluk.settings.workspaceMissingDescription}
                  </p>
                </div>
                <div className="callout">
                  <strong>{sozluk.settings.setupProfileTitle}</strong>
                  <p style={{ marginBottom: 0 }}>{sozluk.settings.setupProfileDescription}</p>
                </div>
                <div className="callout">
                  <strong>{sozluk.settings.themeStatusTitle}</strong>
                  <p style={{ marginBottom: 0 }}>
                    {sozluk.settings.themeStatusDescription} {settings.themeMode === "system"
                      ? sozluk.settings.themeSystem
                      : settings.themeMode === "light"
                        ? sozluk.settings.themeLight
                        : sozluk.settings.themeDark}
                  </p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone={health?.provider_configured ? "accent" : "warning"}>
                    {sozluk.settings.providerStatusLabel}: {health?.provider_configured ? sozluk.settings.providerConfigured : sozluk.settings.providerMissing}
                  </StatusBadge>
                  <StatusBadge tone={health?.google_configured ? "accent" : "warning"}>
                    {sozluk.settings.googleStatusLabel}: {health?.google_configured ? sozluk.settings.googleConfigured : sozluk.settings.googleMissing}
                  </StatusBadge>
                  <StatusBadge tone={health?.telegram_configured ? "accent" : "warning"}>
                    {sozluk.settings.telegramStatusLabel}: {health?.telegram_configured ? sozluk.settings.telegramConfigured : sozluk.settings.telegramMissing}
                  </StatusBadge>
                </div>
              </div>
            </SectionCard>
          </div>
        </div>
      </SectionCard>

      <details className="list-item">
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Gelişmiş ajan köprüsü ve çalışma alanı
        </summary>
        <div className="stack" style={{ marginTop: "1rem" }}>
          <SectionCard title={sozluk.settings.assistantWorkspaceTitle} subtitle={sozluk.settings.assistantWorkspaceSubtitle}>
            {assistantRuntimeWorkspace ? (
              <div className="stack">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={assistantRuntimeWorkspace.workspace_ready ? "accent" : "warning"}>
                {assistantRuntimeWorkspace.workspace_ready ? sozluk.settings.assistantWorkspaceReady : sozluk.settings.assistantWorkspaceMissing}
              </StatusBadge>
              <StatusBadge tone={assistantRuntimeWorkspace.bootstrap_required ? "warning" : "accent"}>
                {assistantRuntimeWorkspace.bootstrap_required ? sozluk.settings.assistantBootstrapRequired : sozluk.settings.assistantBootstrapComplete}
              </StatusBadge>
              <StatusBadge>{sozluk.settings.assistantCuratedSkillCount.replace("{count}", String(assistantRuntimeWorkspace.curated_skill_count || 0))}</StatusBadge>
            </div>
            <div className="callout">
              <strong>{assistantRuntimeWorkspace.workspace_path || sozluk.settings.assistantWorkspaceMissing}</strong>
              <p style={{ marginBottom: 0 }}>
                {sozluk.settings.assistantWorkspaceLastSync}: {assistantRuntimeWorkspace.last_sync_at || sozluk.common.unknown}
              </p>
            </div>
            <div className="list">
              {assistantRuntimeWorkspace.curated_skills.map((skill) => (
                <article className="list-item" key={skill.slug}>
                  <div className="toolbar">
                    <strong>{skill.title}</strong>
                    <StatusBadge tone={skill.enabled ? "accent" : "warning"}>{skill.enabled ? sozluk.settings.assistantSkillEnabled : sozluk.settings.assistantSkillDisabled}</StatusBadge>
                  </div>
                  <p className="list-item__meta">{skill.summary}</p>
                  {skill.reason ? <p style={{ marginBottom: 0 }}>{skill.reason}</p> : null}
                </article>
              ))}
            </div>
            <p style={{ marginBottom: 0 }}>
              {sozluk.settings.assistantWorkspaceDailyLog}: {assistantRuntimeWorkspace.daily_log_path || sozluk.common.notRecorded}
            </p>
            <SectionCard title={sozluk.settings.assistantWorkspaceFilesTitle} subtitle={sozluk.settings.assistantWorkspaceFilesSubtitle}>
              {assistantRuntimeWorkspace.files.length ? (
                <div className="stack">
                  {assistantRuntimeWorkspace.files.map((file) => (
                    <details key={file.name} className="list-item">
                      <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                        {file.name} {file.exists ? "" : `(${sozluk.settings.assistantWorkspaceFileMissing})`}
                      </summary>
                      <pre style={{ marginTop: "0.75rem", whiteSpace: "pre-wrap", overflowX: "auto" }}>{file.preview || sozluk.settings.assistantWorkspaceFileMissing}</pre>
                    </details>
                  ))}
                </div>
              ) : (
                <EmptyState title={sozluk.settings.assistantWorkspaceFilesEmptyTitle} description={sozluk.settings.assistantWorkspaceFilesEmptyDescription} />
              )}
            </SectionCard>
              </div>
            ) : (
              <EmptyState title={sozluk.settings.assistantWorkspaceFilesEmptyTitle} description={sozluk.settings.assistantWorkspaceFilesEmptyDescription} />
            )}
          </SectionCard>
        </div>
      </details>
      </div>
      )}

      {activeTab === "profile" && (
        <div className="stack">
      <SectionCard
        title={sozluk.settings.personalProfileTitle}
        subtitle={sozluk.settings.personalProfileSubtitle}
        actions={
          <button className="button" type="button" onClick={handleSaveProfile} disabled={isSavingProfile}>
            {isSavingProfile ? sozluk.settings.personalProfileSaving : sozluk.settings.personalProfileSave}
          </button>
        }
      >
        <div className="callout">
          <strong>{sozluk.settings.personalProfileCalloutTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.settings.personalProfileCalloutDescription}</p>
        </div>
        <div className="field-grid" style={{ marginTop: "1rem" }}>
          <label className="stack stack--tight">
            <span>{sozluk.settings.profileDisplayName}</span>
            <input className="input" value={profile.display_name} onChange={(event) => updateProfileField("display_name", event.target.value)} />
          </label>
          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
            <span>{sozluk.settings.profileAssistantNotes}</span>
            <textarea
              className="textarea"
              rows={10}
              placeholder={sozluk.settings.profileAssistantNotesPlaceholder}
              value={profile.assistant_notes}
              onChange={(event) => updateProfileField("assistant_notes", event.target.value)}
            />
          </label>
        </div>
        <div className="callout callout--accent" style={{ marginTop: "1rem" }}>
          <strong>{sozluk.settings.profileCalendarFlowTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.settings.profileCalendarFlowDescription}</p>
        </div>
        {profileMessage ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{profileMessage}</p> : null}
      </SectionCard>

      <SectionCard
        title={sozluk.settings.assistantRuntimeTitle}
        subtitle={sozluk.settings.assistantRuntimeSubtitle}
        actions={
          <button className="button" type="button" onClick={handleSaveAssistantRuntimeProfile} disabled={isSavingAssistantRuntime}>
            {isSavingAssistantRuntime ? sozluk.settings.assistantRuntimeSaving : sozluk.settings.assistantRuntimeSave}
          </button>
        }
      >
        <div className="callout">
          <strong>{sozluk.settings.assistantRuntimeCalloutTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.settings.assistantRuntimeCalloutDescription}</p>
        </div>
        <div className="field-grid" style={{ marginTop: "1rem" }}>
          <label className="stack stack--tight">
            <span>{sozluk.settings.assistantNameLabel}</span>
            <input className="input" value={assistantRuntimeProfile.assistant_name} onChange={(event) => updateAssistantRuntimeField("assistant_name", event.target.value)} />
          </label>
          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
            <span>{sozluk.settings.assistantSoulNotesLabel}</span>
            <textarea
              className="textarea"
              rows={9}
              placeholder={sozluk.settings.assistantSoulNotesPlaceholder}
              value={assistantRuntimeProfile.soul_notes}
              onChange={(event) => updateAssistantRuntimeField("soul_notes", event.target.value)}
            />
          </label>
          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
            <span>{sozluk.settings.assistantToolsNotesLabel}</span>
            <textarea
              className="textarea"
              rows={7}
              placeholder={sozluk.settings.assistantToolsNotesPlaceholder}
              value={assistantRuntimeProfile.tools_notes}
              onChange={(event) => updateAssistantRuntimeField("tools_notes", event.target.value)}
            />
          </label>
        </div>
        <div className="callout callout--accent" style={{ marginTop: "1rem" }}>
          <strong>{sozluk.settings.assistantRuntimeFlowTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.settings.assistantRuntimeFlowDescription}</p>
        </div>
        {assistantRuntimeMessage ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{assistantRuntimeMessage}</p> : null}
      </SectionCard>
      </div>
      )}

      {activeTab === "integrations" && (
        <div className="stack">
          <SectionCard title="Bağlı araç yetkinlikleri" subtitle="Okuma, yazma ve onay sınırları tek listede görünür.">
            {assistantToolsStatus.length ? (
              <div className="list">
                {assistantToolsStatus.map((item) => (
                  <article className="list-item" key={item.provider}>
                    <div className="toolbar">
                      <strong>{item.account_label || item.provider}</strong>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone={item.connected ? "accent" : "warning"}>{item.status}</StatusBadge>
                        <StatusBadge>{item.write_enabled ? "Yazma açık" : "Salt okuma"}</StatusBadge>
                        <StatusBadge>{item.approval_required ? "Onaylı aksiyon" : "Doğrudan"}</StatusBadge>
                      </div>
                    </div>
                    <p className="list-item__meta">{item.capabilities.join(" · ")}</p>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="Araç özeti yüklenemedi" description="Bağlı araç durumu geldiğinde burada görünür." />
            )}
          </SectionCard>
          <IntegrationSetupPanel mode="settings" />
        </div>
      )}

      {activeTab === "system" && (
        <div className="stack">
      <SectionCard
        title={sozluk.settings.coreVisibilityTitle}
        subtitle={sozluk.settings.coreVisibilitySubtitle}
        actions={
          <button className="button button--secondary" type="button" onClick={() => navigate("/connectors")}>
            {sozluk.settings.openCoreAction}
          </button>
        }
      >
        {health ? (
          <div className="list">
            <article className="list-item">
              <div className="toolbar">
                <h3 className="list-item__title">{health.app_name}</h3>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone="accent">{health.version}</StatusBadge>
                  <StatusBadge>{surumKanaliEtiketi(health.release_channel)}</StatusBadge>
                  <StatusBadge>{baglayiciDurumuEtiketi(health.connector_dry_run)}</StatusBadge>
                </div>
              </div>
              <p className="list-item__meta">
                {sozluk.settings.officeLabel} {health.office_id} · {sozluk.settings.modeLabel} {dagitimKipiEtiketi(health.deployment_mode)}
              </p>
              <p style={{ marginBottom: "0.4rem" }}>
                {sozluk.settings.providerStatusLabel}: {health.provider_configured ? sozluk.settings.providerConfigured : sozluk.settings.providerMissing}
              </p>
              <p style={{ marginBottom: "0.4rem" }}>
                {sozluk.settings.googleStatusLabel}: {health.google_configured ? sozluk.settings.googleConfigured : sozluk.settings.googleMissing}
                {" · "}
                {sozluk.settings.telegramStatusLabel}: {health.telegram_configured ? sozluk.settings.telegramConfigured : sozluk.settings.telegramMissing}
              </p>
              <p style={{ marginBottom: "0.4rem" }}>
                Asistan çalışma modu: {health.assistant_runtime_mode === "advanced-openclaw"
                  ? "Gelişmiş ajan köprüsü"
                  : health.assistant_runtime_mode === "direct-provider"
                    ? "Doğrudan sağlayıcı"
                    : "Fallback modu"}
              </p>
              <p style={{ marginBottom: "0.4rem" }}>{sozluk.settings.structuredLog}: {health.structured_log_path}</p>
              <p style={{ marginBottom: 0 }}>{sozluk.settings.database}: {health.db_path}</p>
            </article>
          </div>
        ) : (
          <EmptyState title={sozluk.settings.runtimeMissingTitle} description={sozluk.settings.runtimeMissingDescription} />
        )}
      </SectionCard>

      <SectionCard title={sozluk.settings.recentEventsTitle} subtitle={sozluk.settings.recentEventsSubtitle}>
        {health?.recent_events?.length ? (
          <div className="list">
            {health.recent_events.slice(0, 8).map((event, index) => (
              <article className="list-item" key={`${eventTitle(event)}-${index}`}>
                <div className="toolbar">
                  <h3 className="list-item__title">{eventTitle(event)}</h3>
                  {event.status ? <StatusBadge>{String(event.status)}</StatusBadge> : null}
                </div>
                <p className="list-item__meta">{String(event.timestamp || event.created_at || "Zaman bilgisi yok")}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title={sozluk.settings.noEventsTitle} description={sozluk.settings.noEventsDescription} />
        )}
      </SectionCard>

      <SectionCard title={sozluk.connectors.recentModelCallsTitle} subtitle={sozluk.connectors.recentModelCallsSubtitle}>
        {health?.recent_runtime_events?.length ? (
          <div className="list">
            {health.recent_runtime_events.slice(0, 8).map((event, index) => (
              <article className="list-item" key={`${String(event.event || "runtime")}-${index}`}>
                <div className="toolbar">
                  <h3 className="list-item__title">{runtimeDurumuEtiketi(String(event.event || ""))}</h3>
                  <StatusBadge>{String(event.task || "Görev belirtilmedi")}</StatusBadge>
                </div>
                <p className="list-item__meta">
                  {String(event.provider || health.provider_type || "Sağlayıcı yok")} · {String(event.model || health.runtime_last_model || "Model yok")}
                </p>
                <p style={{ marginBottom: 0 }}>
                  {String(event.error || event.ts || "Ek bilgi yok")}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title={sozluk.connectors.noModelCallsTitle} description={sozluk.connectors.noModelCallsDescription} />
        )}
      </SectionCard>

      <details className="list-item">
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Gelişmiş OpenClaw tanısı
        </summary>
        <div className="stack" style={{ marginTop: "1rem" }}>
          <p style={{ marginBottom: 0 }}>
            {sozluk.settings.assistantWorkspaceStatusLabel}: {health?.openclaw_workspace_ready ? sozluk.settings.assistantWorkspaceReady : sozluk.settings.assistantWorkspaceMissing}
          </p>
          <p style={{ marginBottom: 0 }}>
            {sozluk.settings.assistantCuratedSkillCount.replace("{count}", String(health?.openclaw_curated_skill_count || 0))}
          </p>
        </div>
      </details>

      <SectionCard title={sozluk.settings.advancedConnectionTitle} subtitle={sozluk.settings.advancedConnectionSubtitle}>
        {desktopReady ? (
          <div className="callout">
            <strong>{sozluk.settings.desktopManagedConnection}</strong>
            <p style={{ marginBottom: 0 }}>
              {connectionHealth?.app_name || "LawCopilot"} · {settings.baseUrl}
            </p>
          </div>
        ) : (
          <div className="field-grid">
            <label className="stack stack--tight">
              <span>{sozluk.settings.serviceUrl}</span>
              <input className="input" value={settings.baseUrl} onChange={(event) => setSettings({ baseUrl: event.target.value })} />
            </label>
            <label className="stack stack--tight">
              <span>{sozluk.settings.token}</span>
              <textarea
                className="textarea"
                value={settings.token}
                onChange={(event) => setSettings({ token: event.target.value })}
                placeholder={sozluk.settings.tokenPlaceholder}
              />
            </label>
          </div>
        )}
      </SectionCard>
      </div>
      )}
        </div>
      </div>
    </div>
  );
}
