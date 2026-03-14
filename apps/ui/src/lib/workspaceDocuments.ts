import { buildDocumentViewerPath, type DocumentViewerTarget } from "./documentViewer";

type OpenWorkspaceDocumentOptions = {
  relativePath?: string | null;
  fallbackTarget?: DocumentViewerTarget;
  navigate?: (to: string) => void;
};

export async function openWorkspaceDocument(options: OpenWorkspaceDocumentOptions) {
  const normalizedPath = String(options.relativePath || "").trim();
  if (normalizedPath && window.lawcopilotDesktop?.openPathInOS) {
    await window.lawcopilotDesktop.openPathInOS(normalizedPath);
    return "desktop";
  }
  if (options.navigate && options.fallbackTarget) {
    options.navigate(buildDocumentViewerPath(options.fallbackTarget));
    return "viewer";
  }
  return "unavailable";
}
