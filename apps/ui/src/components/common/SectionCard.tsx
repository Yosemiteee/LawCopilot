export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  className
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={className ? `card ${className}` : "card"}>
      <div className="card__header">
        <div className="toolbar">
          <div>
            <h2 className="card__title">{title}</h2>
            {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
          </div>
          {actions}
        </div>
      </div>
      <div className="card__body">{children}</div>
    </section>
  );
}
