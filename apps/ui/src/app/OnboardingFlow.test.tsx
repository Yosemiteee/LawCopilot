import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Onboarding flow", () => {
  it("ilk açılışta çalışma klasörü seçme akışını gösterir", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspace_configured: false,
        workspace_root_name: "",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
    });

    renderApp(["/onboarding"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        chooseWorkspaceRoot: async () => ({ canceled: true }),
      },
    });

    await waitFor(() => expect(screen.getByText("Başlangıç")).toBeInTheDocument());
    expect(screen.getByText("Çalışma klasörü seç")).toBeInTheDocument();
  });

  it("çalışma klasörü seçilmeden dosya ekranını açmaz", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspace_configured: false,
        workspace_root_name: "",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /matters": { items: [] },
    });

    renderApp(["/matters"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
      },
    });

    await waitFor(() => expect(screen.queryByText("Yeni dosya oluştur")).not.toBeInTheDocument());
  });

  it("çalışma klasörü seçildikten sonra çalışma alanına geçer", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspace_configured: false,
        workspace_root_name: "",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /workspace": {
        configured: true,
        workspace: {
          id: 1,
          display_name: "Dava Belgeleri",
          root_path: "/tmp/dava-belgeleri",
          root_path_hash: "hash",
          status: "active",
        },
        documents: { count: 0, items: [] },
        scan_jobs: { items: [] },
      },
    });

    renderApp(["/onboarding"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        chooseWorkspaceRoot: async () => ({
          canceled: false,
          workspace: {
            workspaceRootPath: "/tmp/dava-belgeleri",
            workspaceRootName: "Dava Belgeleri",
            workspaceRootHash: "hash",
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByText("Çalışma klasörü seç")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Çalışma klasörü seç"));

    await waitFor(() => {
      expect(
        screen.queryByText("Çalışma alanına geç") || screen.queryByText("Çalışma alanı araması")
      ).toBeTruthy();
    });
    if (screen.queryByText("Çalışma alanına geç")) {
      fireEvent.click(screen.getByText("Çalışma alanına geç"));
    }
    expect(screen.getByText("Çalışma alanı araması")).toBeInTheDocument();
  });
});
