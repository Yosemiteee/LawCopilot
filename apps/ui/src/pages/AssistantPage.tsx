import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { SearchWorkbench } from "../components/documents/SearchWorkbench";

export function AssistantPage() {
  const { settings } = useAppContext();
  return settings.currentMatterId ? (
    <SearchWorkbench matterId={settings.currentMatterId} heading="Dosya asistanı" />
  ) : (
    <SectionCard title="Asistan" subtitle="Asistan yalnız seçili dosya ve dayanak belgelerle birlikte anlamlı hale gelir.">
      <EmptyState title="Henüz dosya seçilmedi" description="Alıntılar ve taslaklar doğru kapsamda kalsın diye önce bir dosya açın." />
    </SectionCard>
  );
}
