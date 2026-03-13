import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { ConnectedAccountsCard } from "../components/workspace/ConnectedAccountsCard";
import { RecentActivityFeed } from "../components/workspace/RecentActivityFeed";
import { DataSourcesPanel } from "../components/workspace/DataSourcesPanel";
import { WorkspaceOverviewPanel } from "../components/workspace/WorkspaceOverviewPanel";
import {
  getHealth,
  getAssistantAgenda,
  getAssistantInbox,
  listEmailDrafts,
  listSocialEvents,
  getWorkspaceOverview,
  getGoogleIntegrationStatus,
} from "../services/lawcopilotApi";
import type {
  Health,
  AssistantAgendaItem,
  EmailDraft,
  SocialEvent,
  WorkspaceOverviewResponse,
  GoogleIntegrationStatus,
} from "../types/domain";
import "./WorkspacePage.css";

export function WorkspacePage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [health, setHealth] = useState<Health | null>(null);
  const [agenda, setAgenda] = useState<AssistantAgendaItem[]>([]);
  const [inbox, setInbox] = useState<AssistantAgendaItem[]>([]);
  const [emailDrafts, setEmailDrafts] = useState<EmailDraft[]>([]);
  const [socialEvents, setSocialEvents] = useState<SocialEvent[]>([]);
  const [workspaceOverview, setWorkspaceOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleIntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    let active = true;
    async function loadAll() {
      setLoading(true);
      const results = await Promise.allSettled([
        getHealth(settings),
        getAssistantAgenda(settings),
        getAssistantInbox(settings),
        listEmailDrafts(settings),
        listSocialEvents(settings),
        getWorkspaceOverview(settings),
        getGoogleIntegrationStatus(settings),
      ]);
      if (!active) return;

      if (results[0].status === "fulfilled") setHealth(results[0].value);
      if (results[1].status === "fulfilled") setAgenda(results[1].value.items);
      if (results[2].status === "fulfilled") setInbox(results[2].value.items);
      if (results[3].status === "fulfilled") setEmailDrafts(results[3].value.items);
      if (results[4].status === "fulfilled") setSocialEvents(results[4].value.items);
      if (results[5].status === "fulfilled") setWorkspaceOverview(results[5].value);
      if (results[6].status === "fulfilled") setGoogleStatus(results[6].value);
      setLoading(false);
    }
    loadAll();
    return () => { active = false; };
  }, [settings.baseUrl, settings.token]);

  return (
    <div className="workspace-hub">
      {/* Bağlı Hesaplar */}
      <ConnectedAccountsCard health={health} />

      {/* Ana gövde: aktivite + veri kaynakları */}
      <div className="workspace-hub__body">
        <RecentActivityFeed agenda={agenda} inbox={inbox} loading={loading} />
        <DataSourcesPanel
          emailDrafts={emailDrafts}
          socialEvents={socialEvents}
          workspaceOverview={workspaceOverview}
          googleStatus={googleStatus}
          loading={loading}
        />
      </div>

      {/* Çalışma Alanı Arama (daraltılabilir) */}
      <div className="hub-search-section">
        <button
          className="hub-search-toggle"
          type="button"
          onClick={() => setSearchOpen(!searchOpen)}
        >
          <span>Çalışma Alanı Araması ve Tarama</span>
          <span className={`hub-search-toggle__chevron${searchOpen ? " hub-search-toggle__chevron--open" : ""}`}>
            ▼
          </span>
        </button>
        {searchOpen ? (
          <div className="hub-search-content">
            <WorkspaceOverviewPanel />
          </div>
        ) : null}
      </div>
    </div>
  );
}
