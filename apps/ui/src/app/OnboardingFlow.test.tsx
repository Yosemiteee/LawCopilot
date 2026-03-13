import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Onboarding flow", () => {
  it("başlangıç rotasını ayarlara yönlendirir", async () => {
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
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: { hybrid: { provider: "router", policy: "sensitive->local" } },
      },
      "GET /telemetry/health": {
        ok: true,
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        release_channel: "pilot",
        environment: "pilot",
        deployment_mode: "local-only",
        desktop_shell: "electron",
        office_id: "default-office",
        structured_log_path: "/tmp/events.log.jsonl",
        audit_log_path: "/tmp/audit.log.jsonl",
        db_path: "/tmp/lawcopilot.db",
        connector_dry_run: true,
        provider_configured: false,
        telegram_configured: false,
        recent_events: [],
      },
      "GET /workspace": {
        configured: false,
        workspace: null,
        documents: { count: 0, items: [] },
        scan_jobs: { items: [] },
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

    await waitFor(() => expect(screen.getByRole("button", { name: /İlk kurulum/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /İlk kurulum/i }));
    await waitFor(() => expect(screen.getByText("Çalışma klasörü erişimi")).toBeInTheDocument());
  });

  it("çalışma klasörü seçilmeden kurulum uyarısı gösterir", async () => {
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

    await waitFor(() => expect(screen.getByText("Önce kurulum tamamlanmalı")).toBeInTheDocument());
    expect(screen.getByText("Ayarları aç")).toBeInTheDocument();
  });

  it("ayarlar ekranından çalışma klasörü seçildikten sonra çalışma alanına geçer", async () => {
    let healthCalls = 0;
    installFetchMock({
      "GET /health": () => {
        healthCalls += 1;
        return {
          ok: true,
          service: "lawcopilot-api",
          app_name: "LawCopilot",
          version: "0.7.0-pilot.1",
          office_id: "default-office",
          deployment_mode: "local-only",
          connector_dry_run: true,
          workspace_configured: healthCalls > 1,
          workspace_root_name: healthCalls > 1 ? "Dava Belgeleri" : "",
          rag_backend: "inmemory",
          rag_runtime: { backend: "inmemory", mode: "default" },
        };
      },
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: { hybrid: { provider: "router", policy: "sensitive->local" } },
      },
      "GET /telemetry/health": {
        ok: true,
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        release_channel: "pilot",
        environment: "pilot",
        deployment_mode: "local-only",
        desktop_shell: "electron",
        office_id: "default-office",
        structured_log_path: "/tmp/events.log.jsonl",
        audit_log_path: "/tmp/audit.log.jsonl",
        db_path: "/tmp/lawcopilot.db",
        connector_dry_run: true,
        provider_configured: false,
        telegram_configured: false,
        recent_events: [],
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

    await waitFor(() => expect(screen.getByRole("button", { name: /İlk kurulum/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /İlk kurulum/i }));

    await waitFor(() => expect(screen.getAllByRole("button", { name: /Çalışma klasör/i }).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: /Çalışma klasör/i })[0]);

    await waitFor(() => expect(screen.getAllByText("Dava Belgeleri").length).toBeGreaterThan(0));
    expect(screen.getByText("Çalışma alanına git")).toBeInTheDocument();
  });
});
