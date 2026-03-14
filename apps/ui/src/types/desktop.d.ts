export {};

declare global {
  interface Window {
    lawcopilotDesktop?: {
      getRuntimeInfo?: () => Promise<Record<string, unknown>>;
      ensureBackend?: (options?: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getStoredConfig?: () => Promise<Record<string, unknown>>;
      saveStoredConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getIntegrationConfig?: () => Promise<Record<string, unknown>>;
      saveIntegrationConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      validateProviderConfig?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getCodexAuthStatus?: () => Promise<Record<string, unknown>>;
      startCodexAuth?: () => Promise<Record<string, unknown>>;
      submitCodexAuthCallback?: (callbackUrl: string) => Promise<Record<string, unknown>>;
      cancelCodexAuth?: () => Promise<Record<string, unknown>>;
      setCodexModel?: (model: string) => Promise<Record<string, unknown>>;
      getGoogleAuthStatus?: () => Promise<Record<string, unknown>>;
      startGoogleAuth?: () => Promise<Record<string, unknown>>;
      submitGoogleAuthCallback?: (callbackUrl: string) => Promise<Record<string, unknown>>;
      cancelGoogleAuth?: () => Promise<Record<string, unknown>>;
      syncGoogleData?: () => Promise<Record<string, unknown>>;
      sendGmailMessage?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      createGoogleCalendarEvent?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      validateTelegramConfig?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      sendTelegramTestMessage?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getWhatsAppStatus?: () => Promise<Record<string, unknown>>;
      validateWhatsAppConfig?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      syncWhatsAppData?: () => Promise<Record<string, unknown>>;
      sendWhatsAppMessage?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getXAuthStatus?: () => Promise<Record<string, unknown>>;
      startXAuth?: () => Promise<Record<string, unknown>>;
      cancelXAuth?: () => Promise<Record<string, unknown>>;
      syncXData?: () => Promise<Record<string, unknown>>;
      postXUpdate?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      dispatchApprovedAction?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      chooseWorkspaceRoot?: () => Promise<Record<string, unknown>>;
      getWorkspaceConfig?: () => Promise<Record<string, unknown>>;
      saveWorkspaceConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      openPathInOS?: (relativePath: string) => Promise<Record<string, unknown>>;
      revealPathInOS?: (relativePath: string) => Promise<Record<string, unknown>>;
    };
  }
}
