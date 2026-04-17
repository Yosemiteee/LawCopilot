import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { RecentActivityFeed } from "../components/workspace/RecentActivityFeed";
import { DataSourcesPanel } from "../components/workspace/DataSourcesPanel";
import { WorkspaceOverviewPanel } from "../components/workspace/WorkspaceOverviewPanel";
import { sozluk } from "../i18n";
import {
  getAssistantAgenda,
  getAssistantInbox,
  listAssistantDrafts,
  listSocialEvents,
  getWorkspaceOverview,
  getGoogleIntegrationStatus,
} from "../services/lawcopilotApi";
import type {
  AssistantAgendaItem,
  OutboundDraft,
  SocialEvent,
  WorkspaceOverviewResponse,
  GoogleIntegrationStatus,
} from "../types/domain";
import "./WorkspacePage.css";

export function WorkspacePage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [agenda, setAgenda] = useState<AssistantAgendaItem[]>([]);
  const [inbox, setInbox] = useState<AssistantAgendaItem[]>([]);
  const [assistantDrafts, setAssistantDrafts] = useState<OutboundDraft[]>([]);
  const [socialEvents, setSocialEvents] = useState<SocialEvent[]>([]);
  const [workspaceOverview, setWorkspaceOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleIntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function loadAll() {
      setLoading(true);
      const results = await Promise.allSettled([
        getAssistantAgenda(settings),
        getAssistantInbox(settings),
        listAssistantDrafts(settings),
        listSocialEvents(settings),
        getWorkspaceOverview(settings),
        getGoogleIntegrationStatus(settings),
      ]);
      if (!active) return;

      if (results[0].status === "fulfilled") setAgenda(results[0].value.items);
      if (results[1].status === "fulfilled") setInbox(results[1].value.items);
      if (results[2].status === "fulfilled") setAssistantDrafts(results[2].value.items);
      if (results[3].status === "fulfilled") setSocialEvents(results[3].value.items);
      if (results[4].status === "fulfilled") setWorkspaceOverview(results[4].value);
      if (results[5].status === "fulfilled") setGoogleStatus(results[5].value);
      setLoading(false);
    }
    loadAll();
    return () => { active = false; };
  }, [settings.baseUrl, settings.token]);

  const workspaceName =
    workspaceOverview?.workspace?.display_name || settings.workspaceRootName || "Çalışma alanı";
  const workspacePath = workspaceOverview?.workspace?.root_path || settings.workspaceRootPath;
  const documentCount = workspaceOverview?.documents.count ?? 0;
  const priorityCount = [...inbox, ...agenda].filter((item) => item.priority === "high").length;
  const sourceCount =
    assistantDrafts.length +
    socialEvents.length +
    Number(googleStatus?.drive_file_count || 0);

  return (
    <div className="workspace-hub">
      <section className="workspace-hub__hero-card">
        <div className="workspace-hub__hero-main">
          <span className="workspace-hub__eyebrow">{sozluk.workspace.title}</span>
          <h1 className="workspace-hub__title">{workspaceName}</h1>
          <p className="workspace-hub__subtitle">{sozluk.workspace.hubSubtitle}</p>
          <div className="workspace-hub__path-card">
            <strong>{settings.workspaceConfigured ? sozluk.workspace.activePathLabel : sozluk.workspace.notSelectedTitle}</strong>
            <p>{workspacePath || sozluk.workspace.hubPathMissing}</p>
          </div>
        </div>
        <div className="workspace-hub__hero-side">
          <div className="workspace-hub__hero-stats">
            <div className="workspace-hub__stat">
              <span className="workspace-hub__stat-label">{sozluk.workspace.connectedSourcesLabel}</span>
              <strong className="workspace-hub__stat-value">{documentCount}</strong>
            </div>
            <div className="workspace-hub__stat">
              <span className="workspace-hub__stat-label">{sozluk.workspace.prioritySignalsLabel}</span>
              <strong className="workspace-hub__stat-value">{priorityCount}</strong>
            </div>
            <div className="workspace-hub__stat">
              <span className="workspace-hub__stat-label">{sozluk.workspace.totalSignalsLabel}</span>
              <strong className="workspace-hub__stat-value">{sourceCount}</strong>
            </div>
          </div>
          <div className="workspace-hub__hero-actions">
            <button className="button" type="button" onClick={() => navigate("/settings?tab=kurulum&section=kurulum-karti")}>
              {sozluk.workspace.manageSetupAction}
            </button>
            <button className="button button--secondary" type="button" onClick={() => navigate("/assistant")}>
              {sozluk.workspace.openAssistantAction}
            </button>
          </div>
        </div>
      </section>

      <div className="workspace-hub__layout">
        <div className="workspace-hub__primary">
          <WorkspaceOverviewPanel />
        </div>
        <aside className="workspace-hub__secondary">
          <DataSourcesPanel
            assistantDrafts={assistantDrafts}
            socialEvents={socialEvents}
            workspaceOverview={workspaceOverview}
            googleStatus={googleStatus}
            loading={loading}
          />
        </aside>
      </div>

      <RecentActivityFeed
        agenda={agenda}
        inbox={inbox}
        assistantDrafts={assistantDrafts}
        socialEvents={socialEvents}
        loading={loading}
      />
    </div>
  );
}
