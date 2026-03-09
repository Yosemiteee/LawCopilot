import { IntegrationSetupPanel } from "../components/connectors/IntegrationSetupPanel";
import { SectionCard } from "../components/common/SectionCard";
import { sozluk } from "../i18n";

export function ConnectorsPage() {
  return (
    <div className="stack">
      <SectionCard title={sozluk.connectors.title} subtitle={sozluk.connectors.subtitle}>
        <div className="stack">
          <div className="callout callout--accent">
            <strong>{sozluk.connectors.currentPostureTitle}</strong>
            <p style={{ marginBottom: 0 }}>{sozluk.connectors.currentPostureDescription}</p>
          </div>
          <div className="callout">
            <strong>{sozluk.connectors.reviewFirstTitle}</strong>
            <p style={{ marginBottom: 0 }}>{sozluk.connectors.reviewFirstDescription}</p>
          </div>
        </div>
      </SectionCard>
      <IntegrationSetupPanel mode="connectors" />
    </div>
  );
}
