export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="callout">
      <strong>{title}</strong>
      <p style={{ marginBottom: 0, color: "var(--text-muted)" }}>{description}</p>
    </div>
  );
}
