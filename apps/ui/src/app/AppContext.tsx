import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "lawcopilot.ui.settings";

export type AppSettings = {
  baseUrl: string;
  token: string;
  deploymentMode: string;
  themeMode: "system" | "light" | "dark";
  themeAccent: string;
  chatFontSize: string;
  chatWallpaper: string;
  customWallpaper: string;
  selectedModelProfile: string;
  currentMatterId: number | null;
  currentMatterLabel: string;
  officeId: string;
  releaseChannel: string;
  locale: string;
  workspaceConfigured: boolean;
  workspaceRootName: string;
  workspaceRootPath: string;
  workspaceRootHash: string;
  scanOnStartup: boolean;
};

type AppContextValue = {
  settings: AppSettings;
  desktopHydrated: boolean;
  setSettings: (patch: Partial<AppSettings>) => void;
  setCurrentMatter: (matterId: number | null, matterLabel: string) => void;
  setWorkspace: (patch: Partial<Pick<AppSettings, "workspaceConfigured" | "workspaceRootName" | "workspaceRootPath" | "workspaceRootHash" | "scanOnStartup">>) => void;
};

const defaultSettings: AppSettings = {
  baseUrl: "http://127.0.0.1:18731",
  token: "",
  deploymentMode: "local-first-hybrid",
  themeMode: "system",
  themeAccent: "default",
  chatFontSize: "medium",
  chatWallpaper: "default",
  customWallpaper: "",
  selectedModelProfile: "cloud",
  currentMatterId: null,
  currentMatterLabel: "",
  officeId: "varsayilan-ofis",
  releaseChannel: "pilot",
  locale: "tr",
  workspaceConfigured: false,
  workspaceRootName: "",
  workspaceRootPath: "",
  workspaceRootHash: "",
  scanOnStartup: true
};

const AppContext = createContext<AppContextValue | null>(null);

function readStoredSettings(): AppSettings {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return defaultSettings;
  }
  try {
    const parsed = JSON.parse(raw);
    const themeMode = parsed?.themeMode === "light" || parsed?.themeMode === "dark" || parsed?.themeMode === "system"
      ? parsed.themeMode
      : defaultSettings.themeMode;
    const themeAccent = parsed?.themeAccent || defaultSettings.themeAccent;
    const chatFontSize = parsed?.chatFontSize || defaultSettings.chatFontSize;
    const chatWallpaper = parsed?.chatWallpaper || defaultSettings.chatWallpaper;
    const customWallpaper = parsed?.customWallpaper || defaultSettings.customWallpaper;
    return {
      ...defaultSettings,
      ...parsed,
      themeMode,
      themeAccent,
      chatFontSize,
      chatWallpaper,
      customWallpaper,
      // Sensitive desktop runtime values are session-scoped only.
      token: defaultSettings.token,
      workspaceRootPath: defaultSettings.workspaceRootPath,
      // Matter selection is route/session state, not durable workspace configuration.
      currentMatterId: null,
      currentMatterLabel: "",
    };
  } catch {
    return defaultSettings;
  }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettingsState] = useState<AppSettings>(readStoredSettings);
  const [desktopHydrated, setDesktopHydrated] = useState<boolean>(() => !window.lawcopilotDesktop);

  useEffect(() => {
    const {
      currentMatterId: _currentMatterId,
      currentMatterLabel: _currentMatterLabel,
      token: _token,
      workspaceRootPath: _workspaceRootPath,
      ...persisted
    } = settings;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
  }, [settings]);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");

    function applyTheme() {
      const resolvedTheme = settings.themeMode === "system"
        ? (mediaQuery?.matches ? "dark" : "light")
        : settings.themeMode;
      document.documentElement.dataset.theme = resolvedTheme;
      document.documentElement.dataset.themeMode = settings.themeMode;
      document.documentElement.style.colorScheme = resolvedTheme;
      document.documentElement.setAttribute("data-theme-accent", settings.themeAccent || "default");
      document.documentElement.setAttribute("data-chat-font-size", settings.chatFontSize || "medium");
      document.documentElement.setAttribute("data-chat-wallpaper", settings.chatWallpaper || "default");
      
      if (settings.customWallpaper) {
        document.documentElement.style.setProperty("--custom-wallpaper", `url(${settings.customWallpaper})`);
      } else {
        document.documentElement.style.removeProperty("--custom-wallpaper");
      }
    }

    applyTheme();
    mediaQuery?.addEventListener?.("change", applyTheme);
    return () => {
      mediaQuery?.removeEventListener?.("change", applyTheme);
    };
  }, [settings.themeMode, settings.themeAccent, settings.chatFontSize, settings.chatWallpaper, settings.customWallpaper]);

  useEffect(() => {
    let active = true;
    async function loadDesktopState() {
      if (!window.lawcopilotDesktop) {
        setDesktopHydrated(true);
        return;
      }
      const [runtimeInfo, storedConfig, workspaceConfig] = await Promise.all([
        window.lawcopilotDesktop.getRuntimeInfo?.().catch(() => ({})),
        window.lawcopilotDesktop.getStoredConfig?.().catch(() => ({})),
        window.lawcopilotDesktop.getWorkspaceConfig?.().catch(() => ({}))
      ]);
      if (!active) {
        return;
      }
      setSettingsState((prev) => ({
        ...prev,
        baseUrl: String((runtimeInfo as Record<string, unknown>)?.apiBaseUrl || (storedConfig as Record<string, unknown>)?.apiBaseUrl || prev.baseUrl),
        token: String((runtimeInfo as Record<string, unknown>)?.sessionToken || prev.token),
        deploymentMode: String((runtimeInfo as Record<string, unknown>)?.deploymentMode || (storedConfig as Record<string, unknown>)?.deploymentMode || prev.deploymentMode),
        themeMode: (["system", "light", "dark"].includes(String((storedConfig as Record<string, unknown>)?.themeMode))
          ? String((storedConfig as Record<string, unknown>)?.themeMode)
          : prev.themeMode) as AppSettings["themeMode"],
        themeAccent: String((storedConfig as Record<string, unknown>)?.themeAccent || prev.themeAccent),
        chatFontSize: String((storedConfig as Record<string, unknown>)?.chatFontSize || prev.chatFontSize),
        chatWallpaper: String((storedConfig as Record<string, unknown>)?.chatWallpaper || prev.chatWallpaper),
        customWallpaper: String((storedConfig as Record<string, unknown>)?.customWallpaper || prev.customWallpaper),
        selectedModelProfile: String((runtimeInfo as Record<string, unknown>)?.default_model_profile || (storedConfig as Record<string, unknown>)?.selectedModelProfile || prev.selectedModelProfile),
        officeId: String((runtimeInfo as Record<string, unknown>)?.officeId || (storedConfig as Record<string, unknown>)?.officeId || prev.officeId),
        releaseChannel: String((runtimeInfo as Record<string, unknown>)?.releaseChannel || (storedConfig as Record<string, unknown>)?.releaseChannel || prev.releaseChannel),
        locale: String((workspaceConfig as Record<string, unknown>)?.locale || (storedConfig as Record<string, unknown>)?.locale || prev.locale),
        workspaceConfigured: Boolean((workspaceConfig as Record<string, unknown>)?.workspaceRootPath || prev.workspaceConfigured),
        workspaceRootName: String((workspaceConfig as Record<string, unknown>)?.workspaceRootName || prev.workspaceRootName),
        workspaceRootPath: String((workspaceConfig as Record<string, unknown>)?.workspaceRootPath || prev.workspaceRootPath),
        workspaceRootHash: String((workspaceConfig as Record<string, unknown>)?.workspaceRootHash || prev.workspaceRootHash),
        scanOnStartup: typeof (workspaceConfig as Record<string, unknown>)?.scanOnStartup === "boolean"
          ? Boolean((workspaceConfig as Record<string, unknown>)?.scanOnStartup)
          : prev.scanOnStartup
      }));
      setDesktopHydrated(true);
    }
    loadDesktopState().catch(() => {
      if (active) {
        setDesktopHydrated(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const setSettings = useCallback((patch: Partial<AppSettings>) => {
    setSettingsState((prev) => ({ ...prev, ...patch }));
  }, []);

  const setCurrentMatter = useCallback((matterId: number | null, matterLabel: string) => {
    setSettingsState((prev) => ({
      ...prev,
      currentMatterId: matterId,
      currentMatterLabel: matterLabel
    }));
  }, []);

  const setWorkspace = useCallback(
    (patch: Partial<Pick<AppSettings, "workspaceConfigured" | "workspaceRootName" | "workspaceRootPath" | "workspaceRootHash" | "scanOnStartup">>) => {
      setSettingsState((prev) => ({ ...prev, ...patch }));
    },
    []
  );

  const value = useMemo(
    () => ({ settings, desktopHydrated, setSettings, setCurrentMatter, setWorkspace }),
    [settings, desktopHydrated, setSettings, setCurrentMatter, setWorkspace]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const value = useContext(AppContext);
  if (!value) {
    throw new Error("useAppContext must be used within AppProvider");
  }
  return value;
}
