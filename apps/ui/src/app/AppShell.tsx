import { useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";


import { TopBar } from "../components/layout/TopBar";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { sozluk } from "../i18n";
import { normalizeUiErrorMessage } from "../lib/errors";
import { getHealth } from "../services/lawcopilotApi";
import { useAppContext } from "./AppContext";

export function AppShell() {
  const { settings, setSettings, setWorkspace } = useAppContext();
  const [connectionState, setConnectionState] = useState<"loading" | "ready" | "error">("loading");
  const [connectionMessage, setConnectionMessage] = useState("");
  const [isMainScrolling, setIsMainScrolling] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const mainRef = useRef<HTMLElement>(null);
  const mainScrollTimerRef = useRef<number | null>(null);
  const isAssistantRoute = location.pathname === "/assistant";
  const isSettingsRoute = location.pathname === "/settings";
  const isOnboardingRoute = location.pathname === "/onboarding";
  const toolsOpen = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return location.pathname === "/assistant" && Boolean(params.get("tool"));
  }, [location.pathname, location.search]);

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
        setConnectionMessage(normalizeUiErrorMessage(error, sozluk.shell.connectionErrorDescription));
      });
    return () => {
      isMounted = false;
    };
  }, [settings.baseUrl, settings.token, setSettings, setWorkspace]);

  useEffect(() => {
    const container = mainRef.current;
    if (!container) {
      return;
    }

    function handleScroll() {
      setIsMainScrolling(true);
      if (mainScrollTimerRef.current !== null) {
        window.clearTimeout(mainScrollTimerRef.current);
      }
      mainScrollTimerRef.current = window.setTimeout(() => {
        setIsMainScrolling(false);
        mainScrollTimerRef.current = null;
      }, 520);
    }

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      if (mainScrollTimerRef.current !== null) {
        window.clearTimeout(mainScrollTimerRef.current);
      }
    };
  }, []);

  function handleToggleTools() {
    if (location.pathname !== "/assistant") {
      navigate("/assistant?tool=today");
      return;
    }
    const params = new URLSearchParams(location.search);
    if (params.get("tool")) {
      params.delete("tool");
    } else {
      params.set("tool", "today");
    }
    const query = params.toString();
    navigate(query ? `/assistant?${query}` : "/assistant");
  }

  return (
    <div className="app-shell">
      <div className="app-shell__content">
        <TopBar toolsOpen={toolsOpen} onToggleTools={handleToggleTools} />
        <main
          ref={mainRef}
          className={`app-shell__main${isAssistantRoute ? " app-shell__main--assistant" : ""}${isSettingsRoute ? " app-shell__main--settings" : ""}${isMainScrolling ? " app-shell__main--scrolling" : ""}`}
        >
          {connectionState === "error" ? (
            <SectionCard title={sozluk.shell.connectionRequired} subtitle={sozluk.shell.connectionSubtitle}>
              <EmptyState
                title={sozluk.shell.connectionErrorTitle}
                description={connectionMessage || sozluk.shell.connectionErrorDescription}
              />
            </SectionCard>
          ) : (
            <>
              {connectionState === "ready" && !settings.workspaceConfigured && !isSettingsRoute && !isOnboardingRoute ? (
                <div className="shell-banner">
                  <div>
                    <strong>{sozluk.shell.setupBannerTitle}</strong>
                    <p>{sozluk.shell.setupBannerDescription}</p>
                  </div>
                  <button className="button" type="button" onClick={() => navigate("/onboarding")}>
                    {sozluk.shell.setupBannerAction}
                  </button>
                </div>
              ) : null}
              <Outlet />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
