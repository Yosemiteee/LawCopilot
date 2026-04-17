import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

class MockIntersectionObserver {
  disconnect = vi.fn();
  observe = vi.fn();
  unobserve = vi.fn();
  takeRecords = vi.fn(() => []);
  root = null;
  rootMargin = "0px";
  thresholds = [];
}

Object.defineProperty(globalThis, "IntersectionObserver", {
  configurable: true,
  writable: true,
  value: MockIntersectionObserver,
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  writable: true,
  value: vi.fn(),
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("Assistant memory overview", () => {
  it("keeps assistant landing focused even when memory payload is available", async () => {
    const fetchMock = installFetchMock({
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
        today_summary: "Bugün için memory ve trigger yüzeyi güncel.",
        counts: {
          agenda: 2,
          inbox: 1,
          calendar_today: 2,
          drafts_pending: 0,
        },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        proactive_triggers: [
          {
            id: "trigger-1",
            trigger_type: "daily_planning",
            title: "Günlük plan önerisi",
            why_now: "Günün planlama bandındasın.",
            why_this_user: "Yoğunluk var.",
            urgency: "medium",
            scope: "personal",
            recommended_action: { title: "Taslak günlük plan çıkar", stage: "suggest" },
          },
        ],
        assistant_known_profile: {
          preferences: [
            {
              id: "pref-1",
              title: "Ton tercihi",
              summary: "Kısa ve nazik ton tercih ediliyor.",
              scope: "personal",
              record_type: "conversation_style",
              sensitivity: "high",
              shareability: "private",
              confidence: 0.84,
              source_basis: ["profile"],
            },
          ],
        },
        memory_overview: {
          counts: { records: 6, pages: 5, decisions: 2 },
          suppressed_topics: ["food_suggestion"],
          boosted_topics: ["daily_plan"],
          repeated_contradictions: [
            { title: "Ton tercihi", count: 2 },
          ],
        },
        proactive_control_state: {
          suppressed_topics: ["food_suggestion"],
          boosted_topics: ["daily_plan"],
        },
        recommendation_history_summary: [
          {
            id: "rec-1",
            kind: "daily_plan",
            suggestion: "Akşam için hafifletilmiş plan öner.",
            outcome: "accepted",
          },
        ],
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/threads": {
        items: [],
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
        today: "2026-04-08",
        generated_from: "assistant_calendar_engine",
        google_connected: false,
        items: [],
      },
      "GET /assistant/approvals": {
        items: [],
      },
      "GET /assistant/thread/starred": {
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
      },
      "POST /assistant/memory/corrections": {
        status: "updated",
        page_key: "preferences",
        record_id: "pref-1",
        confidence: 0.64,
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.queryByText("Asistanın bildikleri")).not.toBeInTheDocument();
    expect(screen.queryByText("Bilgi sağlığı")).not.toBeInTheDocument();
    expect(screen.queryByText("Bağlayıcı eşitleme")).not.toBeInTheDocument();
    expect(screen.queryByText("Güveni düşür")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });
});
