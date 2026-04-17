import { Suspense, lazy, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./AppShell";
import { LoadingSpinner } from "../components/common/LoadingSpinner";

const AssistantPage = lazy(() => import("../pages/AssistantPage").then((module) => ({ default: module.AssistantPage })));
const DocumentViewerPage = lazy(() => import("../pages/DocumentViewerPage").then((module) => ({ default: module.DocumentViewerPage })));
const DocumentsPage = lazy(() => import("../pages/DocumentsPage").then((module) => ({ default: module.DocumentsPage })));
const MatterDetailPage = lazy(() => import("../pages/MatterDetailPage").then((module) => ({ default: module.MatterDetailPage })));
const MattersPage = lazy(() => import("../pages/MattersPage").then((module) => ({ default: module.MattersPage })));
const MemoryExplorerPage = lazy(() => import("../pages/MemoryExplorerPage").then((module) => ({ default: module.MemoryExplorerPage })));
const PersonalModelPage = lazy(() => import("../pages/PersonalModelPage").then((module) => ({ default: module.PersonalModelPage })));
const SettingsPage = lazy(() => import("../pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const WorkspacePage = lazy(() => import("../pages/WorkspacePage").then((module) => ({ default: module.WorkspacePage })));

function RoutedPage({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div style={{ padding: "1.5rem" }}><LoadingSpinner label="Sayfa hazirlaniyor..." /></div>}>
      {children}
    </Suspense>
  );
}

function LegacyIntegrationsRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const connector = String(params.get("connector") || "").trim().toLowerCase();
  const sectionMap: Record<string, string> = {
    google: "integration-google",
    outlook: "integration-outlook",
    telegram: "integration-telegram",
    whatsapp: "integration-whatsapp",
    x: "integration-x",
    instagram: "integration-instagram",
    linkedin: "integration-linkedin",
    elastic: "integration-elastic",
  };
  const nextParams = new URLSearchParams();
  nextParams.set("tab", "kurulum");
  nextParams.set("section", sectionMap[connector] || "kurulum-karti");
  if (params.get("return_to")) {
    nextParams.set("return_to", String(params.get("return_to")));
  }
  return <Navigate to={{ pathname: "/settings", search: `?${nextParams.toString()}` }} replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/assistant" replace />} />
        <Route path="/workspace" element={<RoutedPage><WorkspacePage /></RoutedPage>} />
        <Route path="/matters" element={<Navigate to={{ pathname: "/assistant", search: "?tool=matters" }} replace />} />
        <Route path="/matters/:matterId" element={<RoutedPage><MatterDetailPage /></RoutedPage>} />
        <Route path="/belge/:scope/:documentId" element={<RoutedPage><DocumentViewerPage /></RoutedPage>} />
        <Route path="/documents" element={<Navigate to={{ pathname: "/assistant", search: "?tool=documents" }} replace />} />
        <Route path="/assistant" element={<RoutedPage><AssistantPage /></RoutedPage>} />
        <Route path="/memory" element={<RoutedPage><MemoryExplorerPage /></RoutedPage>} />
        <Route path="/knowledge" element={<Navigate to="/memory" replace />} />
        <Route path="/personal-model" element={<RoutedPage><PersonalModelPage /></RoutedPage>} />
        <Route path="/profile-model" element={<Navigate to="/personal-model" replace />} />
        <Route path="/integrations" element={<LegacyIntegrationsRedirect />} />
        <Route path="/tasks" element={<Navigate to={{ pathname: "/assistant", search: "?tool=today" }} replace />} />
        <Route path="/drafts" element={<Navigate to={{ pathname: "/assistant", search: "?tool=drafts" }} replace />} />
        <Route path="/settings" element={<RoutedPage><SettingsPage /></RoutedPage>} />
        <Route path="/connectors" element={<LegacyIntegrationsRedirect />} />
        <Route
          path="/onboarding"
          element={<Navigate to={{ pathname: "/settings", search: "?tab=kurulum&section=kurulum-karti" }} replace />}
        />
        <Route path="/_embedded/workspace" element={<RoutedPage><WorkspacePage /></RoutedPage>} />
        <Route path="/_embedded/matters" element={<RoutedPage><MattersPage /></RoutedPage>} />
        <Route path="/_embedded/documents" element={<RoutedPage><DocumentsPage /></RoutedPage>} />
        <Route path="*" element={<Navigate to="/assistant" replace />} />
      </Route>
    </Routes>
  );
}
