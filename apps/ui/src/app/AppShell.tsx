import { useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";


import { TopBar } from "../components/layout/TopBar";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { sozluk } from "../i18n";
import { normalizeUiErrorMessage } from "../lib/errors";
import { getHealth } from "../services/lawcopilotApi";
import { useAppContext } from "./AppContext";

export function AppShell() {
  const { settings, setSettings, setWorkspace, desktopHydrated } = useAppContext();
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
    if (!desktopHydrated) {
      return;
    }
    let isMounted = true;
    setConnectionState("loading");
    setConnectionMessage("");
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
  }, [desktopHydrated, settings.baseUrl, settings.token, setSettings, setWorkspace]);

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

  const startupPending = !desktopHydrated || connectionState === "loading";
  const startupLabel = desktopHydrated ? "Bağlantı kuruluyor..." : "Çalışma alanı hazırlanıyor...";

  if (startupPending) {
    return (
      <div className="app-shell app-shell--startup">
        <div className="app-shell__startup" role="status" aria-live="polite">
          <span className="app-shell__startup-eyebrow">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "0.35rem" }}>
              <path d="M3 6l9-4 9 4" />
              <path d="M3 6v6l9 4 9-4V6" />
              <path d="M3 12v6l9 4 9-4v-6" />
            </svg>
            Assistant Core
          </span>
          <h1 className="app-shell__startup-title">{sozluk.app.name}</h1>
          <p className="app-shell__startup-subtitle">
            Asistanınız hazırlanıyor. Güvenli bağlantı ve çalışma alanı doğrulanıyor...
          </p>
          <LoadingSpinner label={startupLabel} />
          <div className="app-shell__startup-meta">
            <span>🔒 Yerel öncelikli</span>
            <span>📚 Bilgi tabanı hazır</span>
            <span>🛡️ Gizlilik kontrollü</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="app-shell__content">
        {connectionState === "ready" ? <TopBar toolsOpen={toolsOpen} onToggleTools={handleToggleTools} /> : null}
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
              <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                <button className="button" type="button" onClick={() => navigate("/settings")}>
                  {sozluk.shell.setupBannerAction}
                </button>
                <button className="button button--secondary" type="button" onClick={() => window.location.reload()}>
                  Yeniden dene
                </button>
              </div>
            </SectionCard>
          ) : (
            <>
              {connectionState === "ready" && !settings.workspaceConfigured && !isSettingsRoute && !isOnboardingRoute && !isAssistantRoute ? (
                <div className="shell-banner">
                  <div>
                    <strong>{sozluk.shell.setupBannerTitle}</strong>
                    <p>{sozluk.shell.setupBannerDescription}</p>
                  </div>
                  <button className="button" type="button" onClick={() => navigate("/settings?tab=kurulum&section=kurulum-karti")}>
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
