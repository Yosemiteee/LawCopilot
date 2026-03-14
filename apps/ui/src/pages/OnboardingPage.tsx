import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import { sozluk } from "../i18n";
import {
  getAssistantOnboardingState,
  getAssistantRuntimeProfile,
  getHealth,
  getUserProfile,
} from "../services/lawcopilotApi";
import type { AssistantOnboardingState, AssistantRuntimeProfile, Health, UserProfile } from "../types/domain";

function stepTone(complete: boolean) {
  return complete ? "accent" as const : "warning" as const;
}

export function OnboardingPage() {
  const { settings, setSettings, setWorkspace, setCurrentMatter } = useAppContext();
  const navigate = useNavigate();
  const [health, setHealth] = useState<Health | null>(null);
  const [assistantProfile, setAssistantProfile] = useState<AssistantRuntimeProfile | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isChoosingWorkspace, setIsChoosingWorkspace] = useState(false);
  const [error, setError] = useState("");
  const [onboarding, setOnboarding] = useState<AssistantOnboardingState | null>(null);

  async function refreshOnboarding() {
    const [healthResponse, onboardingResponse, assistantProfileResponse, profileResponse] = await Promise.all([
      getHealth(settings),
      getAssistantOnboardingState(settings).catch(() => null),
      getAssistantRuntimeProfile(settings).catch(() => null),
      getUserProfile(settings).catch(() => null),
    ]);
    setHealth(healthResponse);
    setOnboarding(onboardingResponse);
    setAssistantProfile(assistantProfileResponse);
    setProfile(profileResponse);
    setSettings({
      deploymentMode: healthResponse.deployment_mode,
      officeId: healthResponse.office_id,
      releaseChannel: healthResponse.release_channel || settings.releaseChannel,
      selectedModelProfile: healthResponse.default_model_profile || settings.selectedModelProfile,
    });
    setWorkspace({
      workspaceConfigured: Boolean(healthResponse.workspace_configured),
      workspaceRootName: String(healthResponse.workspace_root_name || settings.workspaceRootName),
    });
  }

  useEffect(() => {
    refreshOnboarding().catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function chooseWorkspaceRoot() {
    if (!window.lawcopilotDesktop?.chooseWorkspaceRoot) {
      setError(sozluk.onboarding.desktopRequiredDescription);
      return;
    }
    setIsChoosingWorkspace(true);
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
      setError("");
      await refreshOnboarding();
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.onboarding.blockedReasonDescription);
    } finally {
      setIsChoosingWorkspace(false);
    }
  }

  const workspaceReady = Boolean(settings.workspaceConfigured || onboarding?.workspace_ready || health?.workspace_configured);
  const providerReady = Boolean(onboarding?.provider_ready ?? health?.provider_configured);
  const assistantReady = Boolean(onboarding?.assistant_ready ?? assistantProfile?.assistant_name ?? assistantProfile?.soul_notes);
  const userReady = Boolean(onboarding?.user_ready ?? profile?.display_name ?? profile?.assistant_notes);
  const assistantSnapshot = [
    onboarding?.assistant_profile?.assistant_name || assistantProfile?.assistant_name,
    onboarding?.assistant_profile?.role_summary || assistantProfile?.role_summary,
    onboarding?.assistant_profile?.tone || assistantProfile?.tone,
  ].filter(Boolean);
  const userSnapshot = [
    onboarding?.profile?.display_name || profile?.display_name,
    onboarding?.profile?.favorite_color || profile?.favorite_color,
    onboarding?.profile?.transport_preference || profile?.transport_preference,
    onboarding?.profile?.communication_style || profile?.communication_style,
  ].filter(Boolean);
  const checklist = useMemo(
    () => [
      { id: "workspace", title: sozluk.onboarding.chooseRootTitle, complete: workspaceReady },
      { id: "provider", title: sozluk.onboarding.providerStepTitle, complete: providerReady },
      { id: "assistant", title: "Asistan stili", complete: assistantReady },
      { id: "user", title: "Kullanıcı profili", complete: userReady },
    ],
    [assistantReady, providerReady, userReady, workspaceReady],
  );

  return (
    <div className="settings-surface">
      <div className="toolbar settings-surface__header" style={{ padding: "0.5rem 0 1.5rem", borderBottom: "1px solid var(--line-soft)", marginBottom: "1rem" }}>
        <div>
          <h1 style={{ margin: 0, fontFamily: "var(--font-heading)", fontSize: "1.8rem" }}>{sozluk.onboarding.title}</h1>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)" }}>{sozluk.onboarding.subtitle}</p>
        </div>
        <button className="button button--secondary" type="button" onClick={() => navigate("/assistant")}>
          {sozluk.onboarding.openAssistant}
        </button>
      </div>

      <div className="stack">
      <SectionCard title={sozluk.settings.setupTitle} subtitle={sozluk.settings.setupSubtitle}>
        <div className="stack">
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {checklist.map((item) => (
                <StatusBadge key={item.id} tone={stepTone(item.complete)}>
                  {item.title}
                </StatusBadge>
              ))}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button button--secondary" type="button" onClick={() => void refreshOnboarding()}>
                Durumu yenile
              </button>
              <button className="button" type="button" onClick={() => navigate("/assistant")}>
                Çalışma alanına git
              </button>
            </div>
          </div>
          <div className="callout">
            <strong>{onboarding?.summary || "Kurulum adımları burada özetlenir."}</strong>
            <p style={{ marginBottom: 0 }}>
              {onboarding?.interview_intro || "Kurulum tamamlandığında asistan sizinle kim olduğunuzu ve nasıl bir asistan istediğinizi konuşarak profili doldurur."}
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard title={sozluk.settings.setupWorkspaceTitle} subtitle={sozluk.settings.setupWorkspaceDescription}>
        <div className="stack">
          <strong>Çalışma klasörünü seçin</strong>
          {window.lawcopilotDesktop ? null : (
            <EmptyState
              title={sozluk.onboarding.desktopRequiredTitle}
              description={sozluk.onboarding.desktopRequiredDescription}
            />
          )}
          <div className="toolbar">
            <div>
              <strong>{settings.workspaceRootName || onboarding?.workspace_root_name || "Henüz seçilmedi"}</strong>
              <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)" }}>
                {workspaceReady ? sozluk.onboarding.selectedWorkspace : sozluk.onboarding.chooseRootDescription}
              </p>
            </div>
            <button className="button" type="button" onClick={chooseWorkspaceRoot} disabled={isChoosingWorkspace}>
              {isChoosingWorkspace ? "Seçiliyor..." : workspaceReady ? sozluk.onboarding.chooseAgain : sozluk.onboarding.choose}
            </button>
          </div>
          {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
        </div>
      </SectionCard>

      <SectionCard title={sozluk.settings.setupConnectionsTitle} subtitle={sozluk.settings.setupConnectionsSubtitle}>
        <div className="stack">
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={stepTone(providerReady)}>
              {providerReady ? "Sağlayıcı bağlı" : "Sağlayıcı eksik"}
            </StatusBadge>
            {(onboarding?.provider_type || health?.provider_type) ? (
              <StatusBadge>{String(onboarding?.provider_type || health?.provider_type)}</StatusBadge>
            ) : null}
            {(onboarding?.provider_model || health?.provider_model) ? (
              <StatusBadge>{String(onboarding?.provider_model || health?.provider_model)}</StatusBadge>
            ) : null}
          </div>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            Google hesabını bağladığınızda Gmail, Takvim ve Drive birlikte gelir. Sağlayıcı, Google ve Telegram bağlantıları aynı kurulum alanında tutulur.
          </p>
          <IntegrationSetupPanel mode="simple" />
        </div>
      </SectionCard>

      <SectionCard title="Asistan stilini başlatın" subtitle="İlk sohbetlerde asistan önce kendi kimliğini ve tonunu netleştirir.">
        <div className="stack">
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={stepTone(assistantReady)}>
              {assistantReady ? "Persona hazır" : "Persona başlangıçta"}
            </StatusBadge>
            {assistantSnapshot.map((item) => (
              <StatusBadge key={item}>{item}</StatusBadge>
            ))}
          </div>
          <div className="callout">
            <strong>Beklenen ilk asistan soruları</strong>
            <p style={{ marginBottom: 0 }}>
              Asistan, "Ben kimim?", "Nasıl davranayım?" ve "Daha ciddi mi, daha şakacı mı olayım?" gibi sorularla kendi persona ayarlarını sizinle kurar.
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Sohbetle kişiselleştirme" subtitle="Asistan sizi tanıdıkça kullanıcı profilini ve tercih belleğini günceller.">
        <div className="stack">
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={stepTone(userReady)}>
              {userReady ? "Profil hazır" : "Profil toplanıyor"}
            </StatusBadge>
            {userSnapshot.map((item) => (
              <StatusBadge key={item}>{item}</StatusBadge>
            ))}
          </div>
          <div className="callout callout--accent">
            <strong>Kullanıcı profili nasıl oluşur?</strong>
            <p style={{ marginBottom: 0 }}>
              Asistan sizi tanımak için isim, sevdiğiniz renk, tercih ettiğiniz ulaşım biçimi, iletişim tarzınız ve benzer kişisel bağlamları sohbet içinde sorar. Öğrendikçe bunlar ayarlardaki profil alanlarına yansır.
            </p>
          </div>
          {onboarding?.interview_topics?.length ? (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {onboarding.interview_topics.map((item) => (
                <StatusBadge key={item}>{item}</StatusBadge>
              ))}
            </div>
          ) : null}
          {onboarding?.questions?.length ? (
            <div className="list">
              {onboarding.questions.map((question) => (
                <article className="list-item" key={question.id}>
                  <div className="toolbar">
                    <strong>{question.question}</strong>
                    <StatusBadge>{question.target}</StatusBadge>
                  </div>
                  <p className="list-item__meta">{question.reason}</p>
                </article>
              ))}
            </div>
          ) : null}
          {onboarding?.next_question ? (
            <div className="callout">
              <strong>İlk soru</strong>
              <p style={{ marginBottom: 0 }}>{onboarding.next_question}</p>
            </div>
          ) : null}
          <div className="toolbar">
            <button className="button" type="button" onClick={() => navigate("/assistant")}>
              Asistanla tanışmayı başlat
            </button>
            <button className="button button--secondary" type="button" onClick={() => navigate("/settings")}>
              Ayarlara dön
            </button>
          </div>
        </div>
      </SectionCard>
      {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
      {!window.lawcopilotDesktop ? (
        <EmptyState
          title={sozluk.onboarding.desktopRequiredTitle}
          description={sozluk.onboarding.desktopRequiredDescription}
        />
      ) : null}
      </div>
    </div>
  );
}
