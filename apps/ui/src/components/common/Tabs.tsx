export function Tabs({
  items,
  activeTab
}: {
  items: Array<{ key: string; label: string; onSelect: () => void }>;
  activeTab: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label="Dosya bölümleri">
      {items.map((item) => (
        <button
          key={item.key}
          className={item.key === activeTab ? "tab tab--active" : "tab"}
          onClick={item.onSelect}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
