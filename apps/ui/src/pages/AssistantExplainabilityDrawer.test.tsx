import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
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

describe("Assistant explainability drawer", () => {
  it("shows per-message explainability and wires memory actions from chat", async () => {
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
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: {
          agenda: 1,
          inbox: 0,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        assistant_known_profile: {
          preferences: [
            {
              id: "pref-1",
              title: "Ton tercihi",
              summary: "Kısa ve nazik ton tercih ediliyor.",
              scope: "personal",
              source_basis: ["profile"],
            },
          ],
        },
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 41,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Sana kısa ve nazik bir yanıt tonu önerdim.",
            linked_entities: [],
            tool_suggestions: [],
            source_context: {
              assistant_context_pack: [
                {
                  family: "personal_model",
                  title: "İletişim tonu",
                  summary: "Kısa ve nazik ton tercih ediliyor.",
                  scope: "personal",
                  freshness: "stable",
                  assistant_visibility: "visible",
                },
              ],
              onboarding: {
                current_question: {
                  quick_replies: ["Bana ismimle hitap et."],
                },
              },
              explainability_drawer: {
                why_this: "Bu yanıt ton tercihi ve son düzeltme kayıtlarına dayanıyor.",
                confidence: 0.84,
                risk_level: "A",
                requires_confirmation: false,
                memory_scope: ["personal"],
                source_basis: [
                  {
                    type: "knowledge_record",
                    page_key: "preferences",
                    record_id: "pref-1",
                    title: "Ton tercihi",
                  },
                ],
                supporting_pages_or_records: [
                  {
                    page_key: "preferences",
                    record_id: "pref-1",
                    title: "Ton tercihi",
                    summary: "Kısa ve nazik ton tercih ediliyor.",
                    scope: "personal",
                  },
                ],
                claim_summary_lines: [
                  "- [kullanıcı bilgisi] Ton tercihi: Kısa ve nazik ton tercih ediliyor.",
                ],
                resolved_claims: [
                  {
                    predicate: "communication_style",
                    value_text: "Kısa ve nazik ton tercih ediliyor.",
                  },
                ],
                context_selection_reasons: ["token_overlap", "scope_match"],
                recent_related_feedback: [
                  {
                    kind: "message_draft",
                    outcome: "accepted",
                  },
                ],
              },
            },
            requires_approval: false,
            starred: false,
            created_at: "2026-04-08T09:30:00+00:00",
          },
        ],
        has_more: false,
        total_count: 1,
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
        status: "forgotten",
        page_key: "preferences",
        record_id: "pref-1",
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByText("Sana kısa ve nazik bir yanıt tonu önerdim.").length).toBeGreaterThan(0));

    expect(screen.queryByText("Hızlı yanıt seçenekleri")).not.toBeInTheDocument();
    expect(screen.queryByText("Bana ismimle hitap et.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Yanıt açıklamasını aç"));

    expect(screen.getByText("Bu yanıt ton tercihi ve son düzeltme kayıtlarına dayanıyor.")).toBeInTheDocument();
    expect(screen.getByText("kişisel")).toBeInTheDocument();
    expect(screen.getByText("Dayanak iyi")).toBeInTheDocument();
    expect(screen.getByText("Doğrulanmış bilgiler")).toBeInTheDocument();
    expect(screen.getByText(/\[kullanıcı bilgisi\].*Ton tercihi: Kısa ve nazik ton tercih ediliyor\./i)).toBeInTheDocument();
    expect(screen.getByText("Asistanın o anda gördüğü bağlam")).toBeInTheDocument();
    expect(screen.getByText(/İletişim tonu/i)).toBeInTheDocument();
    expect(screen.getByText("Dayandığı kayıtlar")).toBeInTheDocument();
    expect(screen.getByText("Bu yanıt hazırlanırken mesajındaki ifadelerle doğrudan örtüşen kayıtlar ve konuya ve doğru bağlama uyan kayıtlar öne alındı.")).toBeInTheDocument();
    expect(screen.queryByText("Risk A")).not.toBeInTheDocument();
    expect(screen.queryByText(/token_overlap/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/scope_match/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Bunu unut"));

    await waitFor(() => {
      const correctionCall = fetchMock.mock.calls.find(([input]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/assistant/memory/corrections";
      });
      expect(correctionCall).toBeTruthy();
      expect(JSON.parse(String(correctionCall?.[1]?.body || "{}"))).toMatchObject({
        action: "forget",
        page_key: "preferences",
        target_record_id: "pref-1",
      });
    });
  });

  it("hides confidence label when explainability has no grounded evidence", async () => {
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
          agenda: 1,
          inbox: 0,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        assistant_known_profile: { preferences: [] },
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 42,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "İstersen bu yanıtı nasıl ürettiğimi gösterebilirim.",
            linked_entities: [],
            tool_suggestions: [],
            source_context: {
              explainability_drawer: {
                why_this: "Bu yanıt sadece mevcut mesajın içeriğine göre üretildi.",
                confidence: 0.67,
                risk_level: "A",
                requires_confirmation: false,
                memory_scope: ["personal"],
                source_basis: [],
                supporting_pages_or_records: [],
                context_selection_reasons: [],
                recent_related_feedback: [],
              },
            },
            requires_approval: false,
            starred: false,
            created_at: "2026-04-08T09:30:00+00:00",
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/threads": { items: [] },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": {
        items: [],
        generated_from: "assistant_agenda_engine",
        manual_review_required: true,
      },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-08",
        generated_from: "assistant_calendar_engine",
        google_connected: false,
        items: [],
      },
      "GET /assistant/approvals": { items: [] },
      "GET /assistant/thread/starred": { items: [] },
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
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByText("İstersen bu yanıtı nasıl ürettiğimi gösterebilirim.").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByLabelText("Yanıt açıklamasını aç"));

    expect(screen.getByText("Bu yanıt sadece mevcut mesajın içeriğine göre üretildi.")).toBeInTheDocument();
    expect(screen.queryByText("Dayanak güçlü")).not.toBeInTheDocument();
    expect(screen.queryByText("Dayanak iyi")).not.toBeInTheDocument();
    expect(screen.queryByText("Dayanak sınırlı")).not.toBeInTheDocument();
    expect(screen.queryByText("Dayanak zayıf")).not.toBeInTheDocument();
  });
});
