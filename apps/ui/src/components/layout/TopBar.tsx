import { sozluk } from "../../i18n";
import { useLocation, useNavigate } from "react-router-dom";

function WorkspacePanelIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9 4.5v15" />
      <path d="M12.5 9h4" />
      <path d="M12.5 12.5h4" />
      <path d="M12.5 16h2.5" />
    </svg>
  );
}

export function TopBar({
  toolsOpen,
  onToggleTools,
}: {
  toolsOpen: boolean;
  onToggleTools?: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const isSettingsRoute = location.pathname === "/settings";
  const isAssistantRoute = location.pathname === "/assistant";
  const isMemoryRoute = location.pathname === "/memory" || location.pathname === "/knowledge";
  const isPersonalModelRoute = location.pathname === "/personal-model" || location.pathname === "/profile-model";
  const isWorkspaceRoute = location.pathname === "/workspace" || location.pathname === "/_embedded/workspace";
  const showReturnToAssistant = isSettingsRoute || isWorkspaceRoute || isMemoryRoute || isPersonalModelRoute;

  if (isAssistantRoute) {
    return (
      <header className="app-shell__topbar app-shell__topbar--overlay">
        <div className="app-shell__topbar-group app-shell__topbar-group--left" />
        <div className="app-shell__topbar-group app-shell__topbar-group--right">
          {!toolsOpen && onToggleTools ? (
            <button
              className="button button--secondary"
              type="button"
              onClick={onToggleTools}
              aria-label={sozluk.topBar.tools}
              aria-pressed={toolsOpen}
              title={sozluk.topBar.tools}
              style={{ padding: "0.62rem", marginRight: "0.35rem", borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center" }}
            >
              <WorkspacePanelIcon />
            </button>
          ) : null}
        </div>
      </header>
    );
  }

  return (
    <header className="app-shell__topbar">
      <div className="app-shell__topbar-group app-shell__topbar-group--left">
        {showReturnToAssistant ? (
          <button
            className="button button--secondary"
            type="button"
            title={sozluk.topBar.returnToAssistant}
            onClick={() => navigate("/assistant")}
            style={{ padding: isAssistantRoute ? "0.4rem" : "0.55rem 0.85rem", display: "inline-flex", alignItems: "center", gap: "0.45rem", borderRadius: isAssistantRoute ? "50%" : undefined }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m15 18-6-6 6-6"></path>
            </svg>
            {isAssistantRoute ? null : <span>{sozluk.topBar.returnToAssistant}</span>}
          </button>
        ) : (
          <button
            className="button button--secondary"
            type="button"
            title={sozluk.navigation.find((n) => n.to === "/settings")?.label || "Ayarlar"}
            onClick={() => navigate("/settings")}
            style={{ padding: "0.4rem", borderRadius: "50%" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
          </button>
        )}
        {isAssistantRoute || isSettingsRoute ? null : (
          <span style={{ fontWeight: 600, fontSize: "1rem", fontFamily: "var(--font-heading)" }}>{sozluk.app.name}</span>
        )}
      </div>
      <div className="app-shell__topbar-group app-shell__topbar-group--right" />
    </header>
  );
}
