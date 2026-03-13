import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const healthPayload = {
  ok: true,
  service: "lawcopilot-api",
  version: "0.7.0",
  office_id: "default-office",
  deployment_mode: "local-only",
  connector_dry_run: true,
  workspace_configured: true,
  workspace_root_name: "Tahliye Belgeleri",
  rag_backend: "inmemory",
  rag_runtime: { backend: "inmemory", mode: "default" },
  provider_configured: true,
  provider_type: "openai",
  provider_model: "gpt-4o",
  gmail_connected: true,
  google_account_label: "sami@gmail.com",
  calendar_connected: true,
  telegram_configured: true,
  telegram_bot_username: "lawcopilot_bot",
};

const workspacePayload = {
  configured: true,
  workspace: {
    id: 4,
    office_id: "default-office",
    display_name: "Tahliye Belgeleri",
    root_path: "/tmp/tahliye-belgeleri",
    root_path_hash: "hash",
    status: "active",
    created_at: "2026-03-09T00:00:00Z",
    updated_at: "2026-03-09T00:00:00Z",
  },
  documents: { count: 2, items: [] },
  scan_jobs: {
    items: [
      {
        id: 17,
        office_id: "default-office",
        workspace_root_id: 4,
        status: "completed",
        files_seen: 2,
        files_indexed: 2,
        files_skipped: 0,
        files_failed: 0,
        created_at: "2026-03-09T00:00:00Z",
        updated_at: "2026-03-09T00:10:00Z",
      },
    ],
  },
};

describe("WorkspacePage", () => {
  it("renders workspace tool drawer content inside assistant shell", async () => {
    installFetchMock({
      "GET /health": healthPayload,
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: { agenda: 1, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
      },
      "GET /workspace": workspacePayload,
      "GET /assistant/agenda": {
        items: [
          {
            id: "task-soon-1",
            kind: "due_today",
            title: "Bugün takip et: Belge incelemesi",
            priority: "high",
            due_at: "2026-03-11T17:00:00Z",
            source_type: "task",
            source_ref: "1",
            manual_review_required: true,
          },
        ],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/inbox": {
        items: [],
        generated_from: "assistant_inbox_engine",
      },
    });

    renderApp(["/assistant?tool=workspace"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Tahliye Belgeleri",
      },
    });

    await waitFor(() => expect(screen.getAllByText("Çalışma Alanı").length).toBeGreaterThan(0));
    expect(screen.getByText("Çalışma alanı araması")).toBeInTheDocument();
    expect(screen.getByText("Çalışma alanı araması")).toBeInTheDocument();
  });

  it("runs a workspace search from the embedded panel", async () => {
    installFetchMock({
      "GET /health": healthPayload,
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
      },
      "GET /workspace": workspacePayload,
      "GET /assistant/agenda": { items: [], generated_from: "test" },
      "GET /assistant/inbox": { items: [], generated_from: "test" },
      "POST /workspace/search": {
        answer: "Kira ihtarına dair dayanak bulundu.",
        support_level: "yuksek",
        manual_review_required: false,
        citation_count: 1,
        source_coverage: 0.6,
        generated_from: "workspace_document_memory",
        citations: [],
        related_documents: [],
        attention_points: [],
        workflow_notes: [],
        missing_document_signals: [],
        draft_suggestions: [],
      },
    });

    renderApp(["/_embedded/workspace"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Tahliye Belgeleri",
      },
    });

    await waitFor(() => expect(screen.getByText("Çalışma Alanı Araması ve Tarama")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Çalışma Alanı Araması ve Tarama"));
    await waitFor(() => expect(screen.getAllByText("Çalışma alanı araması").length).toBeGreaterThan(0));
    fireEvent.change(screen.getByPlaceholderText("Örneğin: benzer tahliye dosyaları, kira bedeli ihtilafı, fesih bildirimi"), {
      target: { value: "kira" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aramayı çalıştır" }));
    await waitFor(() => expect(screen.getByText("Kira ihtarına dair dayanak bulundu.")).toBeInTheDocument());
  });
});
