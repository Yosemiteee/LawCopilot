export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="callout" style={{ display: "grid", gap: "0.5rem", alignItems: "start" }}>
      {icon ? (
        <div
          style={{
            width: "2.4rem",
            height: "2.4rem",
            borderRadius: "0.7rem",
            background: "color-mix(in srgb, var(--accent) 10%, transparent)",
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            marginBottom: "0.25rem",
          }}
        >
          {icon}
        </div>
      ) : (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ opacity: 0.5 }}
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
      )}
      <strong>{title}</strong>
      <p style={{ marginBottom: 0, color: "var(--text-muted)", lineHeight: 1.6, fontSize: "0.92rem" }}>
        {description}
      </p>
    </div>
  );
}
