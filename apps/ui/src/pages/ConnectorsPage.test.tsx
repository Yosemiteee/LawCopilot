import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ConnectorsPage", () => {
  it("sağlayıcı doğrulama akışını gösterir", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspace_configured: true,
        workspace_root_name: "Dava Belgeleri",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
    });

    renderApp(["/connectors"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Dava Belgeleri",
      },
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({ workspaceRootPath: "/tmp/dava", workspaceRootName: "Dava Belgeleri" }),
        getIntegrationConfig: async () => ({
          provider: {
            type: "openai",
            baseUrl: "https://api.openai.com/v1",
            model: "gpt-4.1-mini",
            validationStatus: "pending",
            apiKeyConfigured: false,
            apiKeyMasked: "",
          },
          telegram: {
            enabled: false,
            botUsername: "",
            allowedUserId: "",
            validationStatus: "pending",
            botTokenConfigured: false,
            botTokenMasked: "",
          },
        }),
        validateProviderConfig: async () => ({
          ok: true,
          message: "Sağlayıcı bağlantısı doğrulandı.",
          provider: {
            validationStatus: "valid",
            availableModels: ["gpt-4.1-mini"],
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByText("Sağlayıcı kurulumu")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("Kaydedilmiş anahtar yok"), {
      target: { value: "test-anahtar" },
    });
    fireEvent.click(screen.getByText("Sağlayıcıyı doğrula"));

    await waitFor(() => expect(screen.getByText("Sağlayıcı bağlantısı doğrulandı.")).toBeInTheDocument());
    expect(screen.getByText("Görülen modeller")).toBeInTheDocument();
  });
});
