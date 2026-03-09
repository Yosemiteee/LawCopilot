import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { TasksPanel } from "../components/tasks/TasksPanel";

export function TasksPage() {
  const { settings } = useAppContext();
  return settings.currentMatterId ? (
    <TasksPanel matterId={settings.currentMatterId} />
  ) : (
    <EmptyState title="Önce bir dosya seçin" description="Görevler dosyaya bağlı tutulur; bağlam olmadan serbest bırakılmaz." />
  );
}
