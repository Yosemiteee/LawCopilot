import { sozluk } from "../../i18n";
import { useNavigate } from "react-router-dom";

export function TopBar({
  toolsOpen,
  onToggleTools,
}: {
  toolsOpen: boolean;
  onToggleTools?: () => void;
}) {
  const navigate = useNavigate();

  return (
    <header className="app-shell__topbar">
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
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
        <span style={{ fontWeight: 600, fontSize: "1rem", fontFamily: "var(--font-heading)" }}>{sozluk.app.name}</span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
        {onToggleTools ? (
          <button className="button button--secondary" type="button" onClick={onToggleTools} style={{ padding: "0.65rem 1rem" }}>
            {toolsOpen ? sozluk.assistant.toolsClose : sozluk.topBar.tools}
          </button>
        ) : null}
      </div>
    </header>
  );
}
