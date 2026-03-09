import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppProvider } from "../app/AppContext";
import { AppRouter } from "../app/Router";

type RenderOptions = {
  desktop?: Record<string, unknown>;
  storedSettings?: Record<string, unknown>;
};

export function renderApp(initialEntries: string[], options: RenderOptions = {}) {
  window.localStorage.clear();
  if (options.storedSettings) {
    window.localStorage.setItem("lawcopilot.ui.settings", JSON.stringify(options.storedSettings));
  }
  if (options.desktop) {
    Object.defineProperty(window, "lawcopilotDesktop", {
      configurable: true,
      value: options.desktop,
    });
  }
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AppProvider>
        <AppRouter />
      </AppProvider>
    </MemoryRouter>
  );
}
