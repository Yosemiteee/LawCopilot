export function StatusBadge({ tone = "neutral", children }: { tone?: "neutral" | "accent" | "warning" | "danger"; children: React.ReactNode }) {
  const className = tone === "neutral" ? "pill" : `pill pill--${tone}`;
  return <span className={className}>{children}</span>;
}
