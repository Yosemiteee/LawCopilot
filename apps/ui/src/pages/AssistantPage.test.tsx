import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

describe("AssistantPage", () => {
  it("renders assistant calendar and command surface", async () => {
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
        workspace_root_name: "Belge Havuzu",
        google_configured: false,
        calendar_connected: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/inbox": {
        items: [],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/suggested-actions": {
        items: [],
        generated_from: "assistant_agenda_engine",
        manual_review_required: true,
      },
      "GET /assistant/drafts": {
        items: [],
        matter_drafts: [],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/calendar": {
        today: "2026-03-11",
        generated_from: "assistant_calendar_engine",
        google_connected: false,
        items: [],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: false,
        enabled: false,
        scopes: [],
        gmail_connected: false,
        calendar_connected: false,
        status: "pending",
        desktop_managed: true,
      }
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bugün için öncelikli işler hazır.")).toBeInTheDocument());
    expect(screen.getByText("Bugün ne yapmalıyım?")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument();
    expect(screen.getByText("Hızlı başlangıçlar")).toBeInTheDocument();
  });

  it("renders month calendar view and planner inside tools drawer", async () => {
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
        workspace_root_name: "Belge Havuzu",
        google_configured: true,
        calendar_connected: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: {
          agenda: 0,
          inbox: 0,
          calendar_today: 1,
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
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/calendar": {
        today: "2026-03-11",
        generated_from: "assistant_calendar_engine",
        google_connected: true,
        items: [
          {
            id: "calendar-1",
            kind: "calendar_event",
            title: "Duruşma hazırlığı",
            details: "İcra dosyasını gözden geçir",
            starts_at: "2026-03-11T09:30:00Z",
            ends_at: "2026-03-11T10:30:00Z",
            location: "Ofis",
            source_type: "calendar_event",
            source_ref: "event-1",
            matter_id: 14,
            priority: "medium",
            all_day: false,
            needs_preparation: true,
            provider: "google",
            status: "confirmed",
            attendees: [],
            metadata: {},
          },
        ],
      },
    });

    renderApp(["/assistant?tool=calendar"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
        currentMatterId: 14,
      },
    });

    await waitFor(() => expect(screen.getByText("Plan ekle")).toBeInTheDocument());
    expect(screen.getByText("Duruşma hazırlığı")).toBeInTheDocument();
    expect(screen.getAllByText("Google yalnız görüntüleme izninde")).toHaveLength(2);
    expect(screen.getByText("Başlık")).toBeInTheDocument();
  });
});
