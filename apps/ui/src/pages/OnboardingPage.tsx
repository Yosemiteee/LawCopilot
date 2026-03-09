import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { SectionCard } from "../components/common/SectionCard";
import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import { StatusBadge } from "../components/common/StatusBadge";
import { sozluk } from "../i18n";
import { modelProfilEtiketi } from "../lib/labels";
import { getModelProfiles } from "../services/lawcopilotApi";
import type { ModelProfilesResponse } from "../types/domain";

export function OnboardingPage() {
  const { settings, setSettings, setWorkspace } = useAppContext();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<ModelProfilesResponse | null>(null);

  useEffect(() => {
    getModelProfiles(settings)
      .then((response) => setProfiles(response))
      .catch(() => setProfiles(null));
  }, [settings.baseUrl, settings.token]);

  async function chooseRoot() {
    if (!window.lawcopilotDesktop?.chooseWorkspaceRoot) {
      return;
    }
    const response = await window.lawcopilotDesktop.chooseWorkspaceRoot();
    if ((response as { canceled?: boolean }).canceled) {
      return;
    }
    const workspace = (response as { workspace?: Record<string, unknown> }).workspace || {};
    setWorkspace({
      workspaceConfigured: Boolean(workspace.workspaceRootPath),
      workspaceRootName: String(workspace.workspaceRootName || ""),
      workspaceRootPath: String(workspace.workspaceRootPath || ""),
      workspaceRootHash: String(workspace.workspaceRootHash || "")
    });
    navigate("/workspace", { replace: true });
  }

  async function saveModelProfile(value: string) {
    setSettings({ selectedModelProfile: value });
    if (!window.lawcopilotDesktop?.saveStoredConfig) {
      return;
    }
    await window.lawcopilotDesktop.saveStoredConfig({ selectedModelProfile: value });
  }

  return (
    <SectionCard title={sozluk.onboarding.title} subtitle={sozluk.onboarding.subtitle}>
      <div className="stack">
        <div className="callout callout--accent">
          <strong>{sozluk.onboarding.chooseRootTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.onboarding.chooseRootDescription}</p>
        </div>
        <div className="callout">
          <strong>{sozluk.onboarding.localTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.onboarding.localDescription}</p>
        </div>
        <div className="callout">
          <strong>{sozluk.onboarding.modelTitle}</strong>
          <p style={{ marginBottom: "0.75rem" }}>{sozluk.onboarding.modelDescription}</p>
          <label className="stack stack--tight">
            <span>{sozluk.onboarding.profileLabel}</span>
            <select
              className="select"
              value={settings.selectedModelProfile}
              onChange={(event) => {
                const value = event.target.value;
                void saveModelProfile(value);
              }}
            >
              {Object.keys(profiles?.profiles || { local: {}, hybrid: {}, cloud: {} }).map((name) => (
                <option key={name} value={name}>
                  {modelProfilEtiketi(name)}
                </option>
              ))}
            </select>
          </label>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
            <StatusBadge tone="accent">{modelProfilEtiketi(settings.selectedModelProfile)}</StatusBadge>
            {profiles?.profiles?.[settings.selectedModelProfile]?.provider ? (
              <StatusBadge>{String(profiles.profiles[settings.selectedModelProfile]?.provider)}</StatusBadge>
            ) : null}
          </div>
          <p style={{ marginBottom: 0, marginTop: "0.75rem" }}>{sozluk.onboarding.providerNote}</p>
        </div>
        <div className="callout">
          <strong>{sozluk.onboarding.sourceBackedTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.onboarding.sourceBackedDescription}</p>
        </div>
        <div className="callout">
          <strong>{sozluk.onboarding.blockedReasonTitle}</strong>
          <p style={{ marginBottom: 0 }}>{sozluk.onboarding.blockedReasonDescription}</p>
        </div>
        <IntegrationSetupPanel mode="onboarding" />
        {settings.workspaceConfigured ? (
          <div className="callout callout--accent">
            <strong>{sozluk.onboarding.ready}</strong>
            <p style={{ marginBottom: "0.75rem" }}>{settings.workspaceRootName || sozluk.onboarding.selectedWorkspace}</p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button" type="button" onClick={() => navigate("/workspace", { replace: true })}>
                {sozluk.onboarding.continue}
              </button>
              <button className="button button--secondary" type="button" onClick={chooseRoot}>
                {sozluk.onboarding.chooseAgain}
              </button>
            </div>
          </div>
        ) : window.lawcopilotDesktop?.chooseWorkspaceRoot ? (
          <button className="button" type="button" onClick={chooseRoot}>
            {sozluk.onboarding.choose}
          </button>
        ) : (
          <div className="callout">
            <strong>{sozluk.onboarding.desktopRequiredTitle}</strong>
            <p style={{ marginBottom: 0 }}>{sozluk.onboarding.desktopRequiredDescription}</p>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
