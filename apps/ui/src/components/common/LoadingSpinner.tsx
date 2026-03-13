import "./LoadingSpinner.css";

export function LoadingSpinner({ label = "Yükleniyor..." }: { label?: string }) {
  return (
    <div className="loading-spinner">
      <div className="loading-spinner__ring" />
      <span className="loading-spinner__label">{label}</span>
    </div>
  );
}
