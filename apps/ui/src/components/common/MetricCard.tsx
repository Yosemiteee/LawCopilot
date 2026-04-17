export function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
}) {
  return (
    <div className="metric-card">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
        <div className="metric-card__label">{label}</div>
        {icon ? (
          <div
            style={{
              width: "1.6rem",
              height: "1.6rem",
              color: "var(--accent)",
              opacity: 0.5,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
        ) : null}
      </div>
      <div className="metric-card__value">{value}</div>
    </div>
  );
}
