import { cleanup, screen, waitFor, within } from "@testing-library/react";
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
  whatsapp_configured: true,
  whatsapp_account_label: "+90 555 111 22 33",
  x_configured: true,
  x_account_label: "@lawcopilot",
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
  it("renders standalone workspace page instead of assistant drawer", async () => {
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
      "GET /assistant/drafts": {
        items: [
          {
            id: 42,
            draft_type: "message",
            channel: "whatsapp",
            to_contact: "905551112233",
            body: "Merhaba, belgeyi paylaşıyorum.",
            approval_status: "pending",
            delivery_status: "draft",
            created_at: "2026-03-11T10:30:00Z",
            updated_at: "2026-03-11T10:35:00Z",
          },
        ],
        matter_drafts: [],
        generated_from: "assistant_drafts_engine",
      },
    });

    renderApp(["/workspace"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Tahliye Belgeleri",
      },
    });

    await waitFor(() => expect(screen.getByText("Çalışma klasörünüzdeki belgeleri, taslakları ve ek veri kaynaklarını burada birlikte izleyin.")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "Asistana dön" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Kurulumu aç" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("İletişim Taslakları")).toBeInTheDocument());
    expect(screen.getByText("Sosyal Medya")).toBeInTheDocument();
    expect(screen.getByText("Google Drive Dosyaları")).toBeInTheDocument();
    const draftsCard = screen.getByText("İletişim Taslakları").closest(".hub-source-item");
    expect(draftsCard).not.toBeNull();
    expect(within(draftsCard as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Çalışma Paneli" })).not.toBeInTheDocument();
  });
});
