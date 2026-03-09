import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { DraftsPanel } from "../components/drafts/DraftsPanel";

export function DraftsPage() {
  const { settings } = useAppContext();
  return settings.currentMatterId ? (
    <DraftsPanel matterId={settings.currentMatterId} matterLabel={settings.currentMatterLabel || "Seçili dosya"} />
  ) : (
    <EmptyState title="Önce bir dosya seçin" description="Taslak inceleme, doğru alıcı ve belge bağlamı için dosya temelli ilerler." />
  );
}
