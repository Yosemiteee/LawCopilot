import { useAppContext } from "../../app/AppContext";
import { sozluk } from "../../i18n";
import { dagitimKipiEtiketi } from "../../lib/labels";
import { StatusBadge } from "../common/StatusBadge";

export function TopBar({ connectionState }: { connectionState: "loading" | "ready" | "error" }) {
  const { settings } = useAppContext();

  return (
    <header
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        padding: "1.15rem 1.5rem",
        borderBottom: "1px solid var(--line-soft)",
        background: "rgba(255,250,243,0.72)",
        backdropFilter: "blur(10px)"
      }}
    >
      <div>
        <div style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>{sozluk.topBar.selectedMatter}</div>
        <strong style={{ fontSize: "1.05rem" }}>{settings.currentMatterLabel || sozluk.topBar.notSelected}</strong>
        <div style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginTop: "0.2rem" }}>
          {sozluk.topBar.workspace}: {settings.workspaceRootName || sozluk.topBar.notSelected}
        </div>
        {settings.workspaceRootPath ? (
          <div style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "0.1rem" }}>
            {sozluk.topBar.workspacePath}: {settings.workspaceRootPath}
          </div>
        ) : null}
      </div>
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
        <StatusBadge tone="accent">{dagitimKipiEtiketi(settings.deploymentMode)}</StatusBadge>
        <StatusBadge tone={connectionState === "error" ? "danger" : connectionState === "loading" ? "warning" : "accent"}>
          {connectionState === "ready" ? sozluk.topBar.serviceReady : connectionState === "loading" ? sozluk.topBar.serviceLoading : sozluk.topBar.serviceError}
        </StatusBadge>
      </div>
    </header>
  );
}
