import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { AssistantPage } from "../pages/AssistantPage";
import { ConnectorsPage } from "../pages/ConnectorsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DocumentViewerPage } from "../pages/DocumentViewerPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { DraftsPage } from "../pages/DraftsPage";
import { MatterDetailPage } from "../pages/MatterDetailPage";
import { MattersPage } from "../pages/MattersPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { SettingsPage } from "../pages/SettingsPage";
import { TasksPage } from "../pages/TasksPage";
import { WorkspacePage } from "../pages/WorkspacePage";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route index element={<Navigate to="/workspace" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/matters" element={<MattersPage />} />
        <Route path="/matters/:matterId" element={<MatterDetailPage />} />
        <Route path="/belge/:scope/:documentId" element={<DocumentViewerPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/drafts" element={<DraftsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>
    </Routes>
  );
}
