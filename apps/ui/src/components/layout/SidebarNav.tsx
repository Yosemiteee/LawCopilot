import { NavLink } from "react-router-dom";
import { sozluk } from "../../i18n";

const navigation = sozluk.navigation;

export function SidebarNav() {
  return (
    <aside
      style={{
        padding: "2rem 1.25rem",
        borderRight: "1px solid var(--line-soft)",
        background: "rgba(17, 33, 36, 0.96)",
        color: "#f8f5ef",
        display: "flex",
        flexDirection: "column",
        gap: "1rem"
      }}
    >
      <div style={{ padding: "0 0.75rem 1.5rem" }}>
        <div style={{ fontSize: "0.82rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(248,245,239,0.6)" }}>
          {sozluk.app.name}
        </div>
        <h1 style={{ margin: "0.4rem 0 0", fontFamily: "var(--font-heading)", fontSize: "2rem" }}>{sozluk.app.workbench}</h1>
        <p style={{ margin: "0.65rem 0 0", color: "rgba(248,245,239,0.76)", lineHeight: 1.5 }}>
          {sozluk.app.summary}
        </p>
      </div>
      <nav className="stack stack--tight" aria-label="Ana gezinme">
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              padding: "0.9rem 1rem",
              borderRadius: "14px",
              border: isActive ? "1px solid rgba(255,255,255,0.24)" : "1px solid transparent",
              background: isActive ? "rgba(255,255,255,0.09)" : "transparent",
              color: isActive ? "#fff" : "rgba(248,245,239,0.78)"
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="callout" style={{ marginTop: "auto", background: "rgba(255,255,255,0.08)", color: "rgba(248,245,239,0.84)" }}>
        <strong style={{ display: "block", marginBottom: "0.5rem" }}>{sozluk.app.reviewNoticeTitle}</strong>
        {sozluk.app.reviewNoticeBody}
      </div>
    </aside>
  );
}
