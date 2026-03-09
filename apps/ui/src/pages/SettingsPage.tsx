import { useEffect, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import { baglayiciDurumuEtiketi, dagitimKipiEtiketi, masaustuKabukEtiketi, modelProfilEtiketi, ortamEtiketi, surumKanaliEtiketi } from "../lib/labels";
import { sozluk } from "../i18n";
import { getHealth, getModelProfiles, getTelemetryHealth, getWorkspaceOverview } from "../services/lawcopilotApi";
import type { ModelProfilesResponse, TelemetryHealth, WorkspaceOverviewResponse } from "../types/domain";

export function SettingsPage() {
  const { settings, setSettings, setWorkspace } = useAppContext();
  const [profiles, setProfiles] = useState<ModelProfilesResponse | null>(null);
  const [health, setHealth] = useState<TelemetryHealth | null>(null);
  const [workspace, setWorkspaceOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [connectionResult, setConnectionResult] = useState("");
  const [error, setError] = useState("");
  const [desktopConfigSaved, setDesktopConfigSaved] = useState("");

  useEffect(() => {
    Promise.all([getModelProfiles(settings), getTelemetryHealth(settings), getWorkspaceOverview(settings)])
      .then(([profileResponse, telemetryResponse, workspaceResponse]) => {
        setProfiles(profileResponse);
        setHealth(telemetryResponse);
        setWorkspaceOverview(workspaceResponse);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function testConnection() {
    try {
      const healthResponse = await getHealth(settings);
      setSettings({
        deploymentMode: healthResponse.deployment_mode,
        officeId: healthResponse.office_id,
        releaseChannel: healthResponse.release_channel || settings.releaseChannel
      });
      setWorkspace({
        workspaceConfigured: Boolean(healthResponse.workspace_configured),
        workspaceRootName: String(healthResponse.workspace_root_name || settings.workspaceRootName)
      });
      setConnectionResult(`${sozluk.settings.connected}: ${healthResponse.app_name || "LawCopilot"} (${healthResponse.version})`);
      setError("");
    } catch (err) {
      setConnectionResult("");
      setError(err instanceof Error ? err.message : sozluk.settings.connectionError);
    }
  }

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
        workspaceRootHash: String(chosen.workspaceRootHash || "")
      });
      const workspaceResponse = await getWorkspaceOverview(settings);
      setWorkspaceOverview(workspaceResponse);
      setDesktopConfigSaved(sozluk.settings.workspaceChanged);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.settings.workspaceChangeError);
    }
  }

  return (
    <div className="page-grid page-grid--split">
      <SectionCard title={sozluk.settings.title} subtitle={sozluk.settings.subtitle}>
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
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone="accent">{dagitimKipiEtiketi(settings.deploymentMode)}</StatusBadge>
              <StatusBadge>{modelProfilEtiketi(settings.selectedModelProfile)}</StatusBadge>
              <StatusBadge>{settings.officeId}</StatusBadge>
              <StatusBadge>{surumKanaliEtiketi(settings.releaseChannel)}</StatusBadge>
            </div>
            <button className="button" type="button" onClick={testConnection}>
              {sozluk.settings.validateConnection}
            </button>
          </div>
          {desktopConfigSaved ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{desktopConfigSaved}</p> : null}
          {connectionResult ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{connectionResult}</p> : null}
          {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
        </div>
      </SectionCard>

      <div className="stack">
        <SectionCard title={sozluk.settings.workspaceTitle} subtitle={sozluk.settings.workspaceSubtitle}>
          {workspace?.workspace ? (
            <div className="stack">
              <div className="callout callout--accent">
                <strong>{workspace.workspace.display_name}</strong>
                <p style={{ marginBottom: 0 }}>{workspace.workspace.root_path}</p>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone="accent">{workspace.documents.count ?? workspace.documents.items.length} {sozluk.settings.workspaceDocumentCount}</StatusBadge>
                <StatusBadge>{workspace.scan_jobs.items.length} {sozluk.settings.workspaceScanJobCount}</StatusBadge>
                <StatusBadge>{settings.locale.toUpperCase()}</StatusBadge>
              </div>
            </div>
          ) : (
            <EmptyState title={sozluk.settings.workspaceMissingTitle} description={sozluk.settings.workspaceMissingDescription} />
          )}
          <div className="toolbar" style={{ marginTop: "1rem" }}>
            <span style={{ color: "var(--text-muted)" }}>{sozluk.settings.workspacePolicy}</span>
            <button className="button button--secondary" type="button" onClick={chooseWorkspaceRoot}>
              {sozluk.settings.workspaceChange}
            </button>
          </div>
        </SectionCard>

        <SectionCard title={sozluk.settings.modelProfilesTitle} subtitle={sozluk.settings.modelProfilesSubtitle}>
          {profiles ? (
            <div className="list">
              {Object.entries(profiles.profiles).map(([name, profile]) => (
                <article className="list-item" key={name}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{name}</h3>
                    <StatusBadge tone={profiles.default === name ? "accent" : "warning"}>
                      {profiles.default === name ? sozluk.settings.defaultProfile : sozluk.settings.availableProfile}
                    </StatusBadge>
                  </div>
                  <p className="list-item__meta">{profile.provider || sozluk.common.routerPolicy} · {profile.model || profile.policy || sozluk.common.policyBased}</p>
                  <p style={{ marginBottom: 0 }}>{profile.notes || profile.dataResidency || sozluk.common.notRecorded}</p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title={sozluk.settings.noProfileTitle} description={sozluk.settings.noProfileDescription} />
          )}
        </SectionCard>

        <SectionCard title={sozluk.settings.runtimeTitle} subtitle={sozluk.settings.runtimeSubtitle}>
          {health ? (
            <div className="list">
              <article className="list-item">
                <div className="toolbar">
                  <h3 className="list-item__title">{health.app_name}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone="accent">{health.version}</StatusBadge>
                    <StatusBadge>{surumKanaliEtiketi(health.release_channel)}</StatusBadge>
                    <StatusBadge>{masaustuKabukEtiketi(health.desktop_shell)}</StatusBadge>
                  </div>
                </div>
                <p className="list-item__meta">
                  {sozluk.settings.officeLabel} {health.office_id} · {sozluk.settings.modeLabel} {dagitimKipiEtiketi(health.deployment_mode)} · {sozluk.settings.environmentLabel} {ortamEtiketi(health.environment)}
                </p>
                <p style={{ marginBottom: "0.4rem" }}>{sozluk.settings.auditLog}: {health.audit_log_path}</p>
                <p style={{ marginBottom: "0.4rem" }}>{sozluk.settings.structuredLog}: {health.structured_log_path}</p>
                <p style={{ marginBottom: 0 }}>{sozluk.settings.database}: {health.db_path}</p>
              </article>
              <article className="list-item">
                <div className="toolbar">
                  <h3 className="list-item__title">{sozluk.settings.securityTitle}</h3>
                  <StatusBadge tone={health.connector_dry_run ? "accent" : "warning"}>{baglayiciDurumuEtiketi(health.connector_dry_run)}</StatusBadge>
                </div>
                <p className="list-item__meta">{sozluk.settings.recentEvents}: {health.recent_events.length}</p>
                <p style={{ marginBottom: "0.4rem" }}>
                  {sozluk.settings.providerStatusLabel}: {health.provider_configured ? sozluk.settings.providerConfigured : sozluk.settings.providerMissing}
                </p>
                <p style={{ marginBottom: "0.4rem" }}>
                  {sozluk.settings.telegramStatusLabel}: {health.telegram_configured ? sozluk.settings.telegramConfigured : sozluk.settings.telegramMissing}
                </p>
                {health.telegram_bot_username ? <p style={{ marginBottom: 0 }}>{sozluk.settings.telegramBotLabel}: {health.telegram_bot_username}</p> : null}
              </article>
            </div>
          ) : (
            <EmptyState title={sozluk.settings.runtimeMissingTitle} description={sozluk.settings.runtimeMissingDescription} />
          )}
        </SectionCard>

        <IntegrationSetupPanel mode="settings" />
      </div>
    </div>
  );
}
