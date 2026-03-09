export {};

declare global {
  interface Window {
    lawcopilotDesktop?: {
      getRuntimeInfo?: () => Promise<Record<string, unknown>>;
      getStoredConfig?: () => Promise<Record<string, unknown>>;
      saveStoredConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      getIntegrationConfig?: () => Promise<Record<string, unknown>>;
      saveIntegrationConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      validateProviderConfig?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      validateTelegramConfig?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      sendTelegramTestMessage?: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
      chooseWorkspaceRoot?: () => Promise<Record<string, unknown>>;
      getWorkspaceConfig?: () => Promise<Record<string, unknown>>;
      saveWorkspaceConfig?: (patch: Record<string, unknown>) => Promise<Record<string, unknown>>;
      openPathInOS?: (relativePath: string) => Promise<Record<string, unknown>>;
      revealPathInOS?: (relativePath: string) => Promise<Record<string, unknown>>;
    };
  }
}
