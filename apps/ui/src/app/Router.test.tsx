import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BASE_MOCKS = {
  "GET /health": {
    ok: true,
    service: "lawcopilot-api",
    version: "0.6.1",
    office_id: "default-office",
    deployment_mode: "local-only",
    connector_dry_run: true,
    workspace_configured: true,
    workspace_root_name: "Deneme Belgeleri",
    rag_backend: "inmemory",
    rag_runtime: { backend: "inmemory", mode: "default" },
  },
  "GET /settings/model-profiles": {
    default: "hybrid",
    deployment_mode: "local-only",
    office_id: "default-office",
    profiles: { hybrid: { provider: "router", policy: "sensitive->local" } },
  },
  "GET /assistant/home": {
    today_summary: "Bugün için öncelikli işler hazır.",
    counts: {
      agenda: 0,
      inbox: 0,
      calendar_today: 0,
      drafts_pending: 0,
    },
    priority_items: [],
    requires_setup: [],
    connected_accounts: [],
    generated_from: "assistant_home_engine",
  },
  "GET /assistant/thread": {
    thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
    messages: [],
  },
  "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
  "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
  "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
  "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
  "GET /assistant/calendar": { today: "2026-03-11", items: [], generated_from: "assistant_calendar_engine", google_connected: false },
  "GET /integrations/google/status": {
    provider: "google",
    configured: false,
    enabled: false,
    scopes: [],
    gmail_connected: false,
    calendar_connected: false,
    status: "pending",
    desktop_managed: true,
  },
};

describe("AppRouter", () => {
  it("renders assistant workbench as primary home", async () => {
    installFetchMock(BASE_MOCKS);

    renderApp(["/assistant"]);

    await waitFor(() => expect(screen.getByText("Bugün için öncelikli işler hazır.")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Araçlar" })).toBeInTheDocument();
    expect(screen.getByText("Bugün ne yapmalıyım?")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument();
  });

  it("redirects dashboard into assistant today drawer", async () => {
    installFetchMock({
      ...BASE_MOCKS,
    });

    renderApp(["/dashboard"]);

    await waitFor(() => expect(screen.getByText("Kapat")).toBeInTheDocument());
    expect(screen.getAllByText("Bugün").length).toBeGreaterThan(0);
    expect(screen.getByText("Bugün için ajanda boş")).toBeInTheDocument();
  });

  it("redirects workspace route into assistant tool drawer and prefers workspace context", async () => {
    installFetchMock({
      ...BASE_MOCKS,
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        version: "0.6.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspace_configured: true,
        workspace_root_name: "Tahliye Belgeleri",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /workspace": {
        configured: true,
        workspace: {
          id: 1,
          display_name: "Tahliye Belgeleri",
          root_path: "/tmp/tahliye",
          root_path_hash: "hash",
        },
        documents: { items: [], count: 0 },
        scan_jobs: { items: [] },
      },
    });

    renderApp(["/workspace"], {
      storedSettings: {
        currentMatterId: 999,
        currentMatterLabel: "Eski Seçili Dosya",
        workspaceRootName: "Tahliye Belgeleri",
        workspaceRootPath: "/tmp/tahliye",
        workspaceConfigured: true,
      },
    });

    await waitFor(() => expect(screen.getAllByText("Çalışma Alanı").length).toBeGreaterThan(0));
    expect(screen.getByText("Çalışma alanı araması")).toBeInTheDocument();
    expect(screen.queryByText("Eski Seçili Dosya")).not.toBeInTheDocument();
  });
});
