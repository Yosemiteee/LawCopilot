import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { AssistantPage } from "../pages/AssistantPage";
import { DocumentViewerPage } from "../pages/DocumentViewerPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { MatterDetailPage } from "../pages/MatterDetailPage";
import { MattersPage } from "../pages/MattersPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { SettingsPage } from "../pages/SettingsPage";
import { WorkspacePage } from "../pages/WorkspacePage";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/assistant" replace />} />
        <Route path="/workspace" element={<Navigate to={{ pathname: "/assistant", search: "?tool=workspace" }} replace />} />
        <Route path="/dashboard" element={<Navigate to={{ pathname: "/assistant", search: "?tool=today" }} replace />} />
        <Route path="/matters" element={<Navigate to={{ pathname: "/assistant", search: "?tool=matters" }} replace />} />
        <Route path="/matters/:matterId" element={<MatterDetailPage />} />
        <Route path="/belge/:scope/:documentId" element={<DocumentViewerPage />} />
        <Route path="/documents" element={<Navigate to={{ pathname: "/assistant", search: "?tool=documents" }} replace />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/tasks" element={<Navigate to={{ pathname: "/assistant", search: "?tool=today" }} replace />} />
        <Route path="/drafts" element={<Navigate to={{ pathname: "/assistant", search: "?tool=drafts" }} replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/connectors" element={<Navigate to={{ pathname: "/assistant", search: "?tool=runtime" }} replace />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/_embedded/workspace" element={<WorkspacePage />} />
        <Route path="/_embedded/matters" element={<MattersPage />} />
        <Route path="/_embedded/documents" element={<DocumentsPage />} />
      </Route>
    </Routes>
  );
}
