import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { AppProvider, useAppContext } from "./AppContext";

function ThemeProbe() {
  const { settings, setSettings } = useAppContext();

  return (
    <div>
      <span>{settings.themeMode}</span>
      <button type="button" onClick={() => setSettings({ themeMode: "dark" })}>
        karanlik
      </button>
    </div>
  );
}

function SensitiveSettingsProbe() {
  const { settings, setSettings } = useAppContext();

  return (
    <div>
      <span data-testid="token">{settings.token || "empty"}</span>
      <span data-testid="workspace-root-path">{settings.workspaceRootPath || "empty"}</span>
      <button
        type="button"
        onClick={() => setSettings({ token: "session-secret", workspaceRootPath: "/secret/workspace" })}
      >
        hassas
      </button>
    </div>
  );
}

function mockMatchMedia(matches = false) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const mediaQuery = {
    matches,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener),
    dispatch(nextMatches: boolean) {
      mediaQuery.matches = nextMatches;
      listeners.forEach((listener) => listener({ matches: nextMatches } as MediaQueryListEvent));
    },
  };

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: () => mediaQuery,
  });

  return mediaQuery;
}

describe("AppProvider theme mode", () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.themeMode;
    document.documentElement.style.colorScheme = "";
  });

  it("applies stored system theme using current OS preference", async () => {
    mockMatchMedia(true);
    window.localStorage.setItem(
      "lawcopilot.ui.settings",
      JSON.stringify({ themeMode: "system" }),
    );

    render(
      <AppProvider>
        <ThemeProbe />
      </AppProvider>,
    );

    await waitFor(() => {
      expect(document.documentElement.dataset.themeMode).toBe("system");
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.style.colorScheme).toBe("dark");
    });
  });

  it("updates document theme when user switches to dark mode", async () => {
    mockMatchMedia(false);

    render(
      <AppProvider>
        <ThemeProbe />
      </AppProvider>,
    );

    screen.getAllByRole("button", { name: "karanlik" })[0].click();

    await waitFor(() => {
      expect(document.documentElement.dataset.themeMode).toBe("dark");
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.style.colorScheme).toBe("dark");
    });
  });

  it("does not rehydrate or persist sensitive runtime fields", async () => {
    mockMatchMedia(false);
    window.localStorage.setItem(
      "lawcopilot.ui.settings",
      JSON.stringify({ token: "persisted-secret", workspaceRootPath: "/persisted/workspace" }),
    );

    render(
      <AppProvider>
        <SensitiveSettingsProbe />
      </AppProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("token")).toHaveTextContent("empty");
      expect(screen.getByTestId("workspace-root-path")).toHaveTextContent("empty");
    });

    screen.getByRole("button", { name: "hassas" }).click();

    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem("lawcopilot.ui.settings") || "{}");
      expect(stored.token).toBeUndefined();
      expect(stored.workspaceRootPath).toBeUndefined();
    });
  });
});
