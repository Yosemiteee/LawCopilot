import { sozluk } from "../../i18n";
import { useLocation, useNavigate } from "react-router-dom";

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
  const showToolsButton = isAssistantRoute && Boolean(onToggleTools) && !toolsOpen;

  return (
    <header className={`app-shell__topbar${isAssistantRoute ? " app-shell__topbar--overlay" : ""}`}>
      <div className="app-shell__topbar-group app-shell__topbar-group--left">
        {isSettingsRoute ? (
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
      <div className="app-shell__topbar-group app-shell__topbar-group--right">
        {showToolsButton ? (
          <button
            className="button button--secondary"
            type="button"
            onClick={onToggleTools}
            aria-pressed={toolsOpen}
            style={{ padding: "0.65rem 1rem" }}
          >
            {sozluk.topBar.tools}
          </button>
        ) : null}
      </div>
    </header>
  );
}
