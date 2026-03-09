import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { SidebarNav } from "../components/layout/SidebarNav";
import { TopBar } from "../components/layout/TopBar";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { sozluk } from "../i18n";
import { getHealth } from "../services/lawcopilotApi";
import { useAppContext } from "./AppContext";

export function AppShell() {
  const { settings, setSettings, setWorkspace } = useAppContext();
  const [connectionState, setConnectionState] = useState<"loading" | "ready" | "error">("loading");
  const [connectionMessage, setConnectionMessage] = useState("");
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let isMounted = true;
    getHealth(settings)
      .then((health) => {
        if (!isMounted) {
          return;
        }
        setSettings({
          deploymentMode: health.deployment_mode,
          selectedModelProfile: health.default_model_profile || settings.selectedModelProfile,
          officeId: health.office_id,
          releaseChannel: health.release_channel || settings.releaseChannel
        });
        setWorkspace({
          workspaceConfigured: Boolean(health.workspace_configured),
          workspaceRootName: String(health.workspace_root_name || settings.workspaceRootName)
        });
        setConnectionState("ready");
        setConnectionMessage("");
      })
      .catch((error: Error) => {
        if (!isMounted) {
          return;
        }
        setConnectionState("error");
        setConnectionMessage(error.message);
      });
    return () => {
      isMounted = false;
    };
  }, [settings.baseUrl, settings.token, settings.releaseChannel, settings.workspaceRootName, setSettings, setWorkspace]);

  const onboardingLocked = connectionState === "ready" && !settings.workspaceConfigured;

  useEffect(() => {
    if (connectionState !== "ready") {
      return;
    }
    if (!settings.workspaceConfigured && location.pathname !== "/onboarding") {
      navigate("/onboarding", { replace: true });
      return;
    }
    if (settings.workspaceConfigured && location.pathname === "/onboarding") {
      navigate("/workspace", { replace: true });
    }
  }, [connectionState, location.pathname, navigate, settings.workspaceConfigured]);

  if (onboardingLocked && location.pathname !== "/onboarding") {
    return null;
  }

  return (
    <div className="app-shell">
      {onboardingLocked ? null : <SidebarNav />}
      <div className="app-shell__content">
        <TopBar connectionState={connectionState} />
        <main className="app-shell__main">
          {connectionState === "error" ? (
            <SectionCard title={sozluk.shell.connectionRequired} subtitle={sozluk.shell.connectionSubtitle}>
              <EmptyState
                title={sozluk.shell.connectionErrorTitle}
                description={connectionMessage || sozluk.shell.connectionErrorDescription}
              />
            </SectionCard>
          ) : onboardingLocked && location.pathname !== "/onboarding" ? (
            <SectionCard title={sozluk.shell.onboardingLockTitle} subtitle={sozluk.shell.connectionSubtitle}>
              <EmptyState title={sozluk.shell.onboardingLockTitle} description={sozluk.shell.onboardingLockDescription} />
            </SectionCard>
          ) : (
            <Outlet />
          )}
        </main>
      </div>
    </div>
  );
}
