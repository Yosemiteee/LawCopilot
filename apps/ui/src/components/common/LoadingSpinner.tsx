import "./LoadingSpinner.css";

export function LoadingSpinner({ label = "Yükleniyor..." }: { label?: string }) {
  return (
    <div className="loading-spinner">
      <div className="loading-spinner__ring-wrapper">
        <div className="loading-spinner__ring" />
      </div>
      <span className="loading-spinner__label">{label}</span>
    </div>
  );
}
