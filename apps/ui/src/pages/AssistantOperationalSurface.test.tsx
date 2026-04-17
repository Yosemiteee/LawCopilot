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

describe("Assistant operational surface", () => {
  it("keeps assistant landing focused when operational payload is available", async () => {
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
        today_summary: "Canlı bağlayıcı ve konum durumu hazır.",
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
        connector_sync_status: {
          summary: {
            attention_required: 1,
            retry_scheduled: 1,
            connected_providers: 1,
          },
          items: [
            {
              connector: "email_threads",
              description: "Google/Outlook mirror edilen e-posta thread kayıtları.",
              sync_mode: "mirror_pull",
              health_status: "invalid",
              sync_status: "retry_scheduled",
              sync_status_message: "Connector sync başarısız oldu, 2 dakika sonra yeniden denenecek.",
              next_retry_at: "2026-04-08T12:32:00+00:00",
              consecutive_failures: 1,
              record_count: 5,
              synced_record_count: 3,
              providers: [
                {
                  provider: "google",
                  connected: true,
                  health_status: "valid",
                },
              ],
            },
          ],
        },
        location_context: {
          provider: "desktop_location_snapshot_v1",
          provider_mode: "desktop_file_snapshot",
          provider_status: "fresh",
          freshness_label: "fresh",
          capture_mode: "snapshot_fallback",
          permission_state: "granted",
          scope: "personal",
          sensitivity: "high",
          observed_at: "2026-04-08T12:30:00+00:00",
          current_place: {
            label: "Kadikoy Rihtim",
            category: "transit",
            area: "Kadikoy",
          },
          location_explainability: {
            status_reason: "Cihaz konum anlık görüntüsü kullanılabilir görünüyor.",
          },
          nearby_candidates: [
            {
              title: "Yakındaki tarihi nokta",
              category: "historic_site",
              reason: "Bu bölgede tarihi ilgi alanı sinyali veya area tag bulundu.",
              confidence: 0.84,
              navigation_prep: {
                maps_url: "https://maps.example/historic",
                route_mode: "walking",
              },
            },
          ],
        },
        orchestration_status: {
          summary: {
            due_jobs: 1,
            failed_jobs: 1,
            retry_scheduled: 1,
            },
          jobs: [
            {
              job: "trigger_evaluation",
              status: "retry_scheduled",
              is_due: true,
              next_due_at: "2026-04-08T12:35:00+00:00",
              last_error: "timeout",
              status_message: "trigger_evaluation başarısız oldu; yeniden denenecek.",
              retry_delay_seconds: 120,
            },
          ],
        },
        reflection_status: {
          status: "completed",
          health_status: "attention_required",
          next_due_at: "2026-04-08T13:00:00+00:00",
          recommended_kb_actions: [
            {
              action: "refresh_record",
              priority: "high",
              reason: "Kayıt 240 gündür güncellenmedi.",
            },
          ],
        },
        autonomy_status: {
          status: "guarded",
          open_loop_count: 3,
          policy: {
            suggestion_budget: 2,
          },
          silence_reasons: [
            "Interruption tolerance ve reminder fatigue nedeniyle aynı anda az öneri gösterilecek.",
          ],
          matters_now: [
            {
              title: "Bağlayıcı sağlığı dikkat istiyor",
              summary: "1 connector dikkat gerektiriyor.",
              priority: "high",
              scope: "global",
            },
          ],
        },
        proactive_suggestions: [
          {
            id: "1",
            kind: "daily_plan",
            title: "Aksam plani",
            details: "Yogun takvim icin hafifletilmis plan onerisi.",
            action_label: "Plani goster",
            action_ladder: {
              current_stage: "suggest",
              trusted_low_risk_available: true,
              preview_summary: "Görev ve takvim öncesi hafifletilmiş önizleme.",
              approval_reason: "Kullanmadan önce önizleme gösterilir.",
              undo_strategy: "Onay öncesi öneri geri çekilebilir.",
            },
          },
        ],
        assistant_core: {
          summary: {
            active_forms: 1,
            supports_coaching: true,
            capability_count: 4,
          },
          core_summary: "Asistan çekirdeği şu anda Yaşam koçu odağıyla çalışıyor. Hedef ve alışkanlık takibi aktif hale gelebilir.",
          capability_contracts: [
            {
              slug: "goal_tracking",
              title: "Hedef takibi",
              operating_hint: "Bu yetenek açık olduğunda sistem hedef, ilerleme ve check-in dilini daha aktif kullanır.",
            },
          ],
          surface_contracts: [
            {
              slug: "coaching_dashboard",
              title: "Koçluk paneli",
            },
          ],
          suggested_setup_actions: [
            {
              id: "create-first-goal",
              title: "İlk hedefi oluştur",
              why: "Koçluk ve ilerleme yetenekleri hedef olmadan tam çalışmaz.",
              priority: "high",
            },
          ],
          active_forms: [
            {
              slug: "life_coach",
              title: "Yaşam koçu",
              summary: "Hedef, alışkanlık ve takip düzeni kurar.",
              category: "personal",
              active: true,
              scopes: ["personal"],
            },
          ],
          available_forms: [
            {
              slug: "legal_copilot",
              title: "Hukuk asistanı",
            },
          ],
          evolution_history: [
            {
              id: "evo-1",
              summary: "Asistan formları güncellendi: Yaşam koçu aktif.",
            },
          ],
        },
        assistant_known_profile: {},
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/threads": { items: [] },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.queryByText("Bağlayıcı eşitleme")).not.toBeInTheDocument();
    expect(screen.queryByText("Konum bağlamı")).not.toBeInTheDocument();
    expect(screen.queryByText("Asistan etkinliği")).not.toBeInTheDocument();
    expect(screen.queryByText("Otonomi durumu")).not.toBeInTheDocument();
    expect(screen.queryByText("Asistan çekirdeği")).not.toBeInTheDocument();
    expect(screen.queryByText("Yaşam koçu")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Konumu güncelle" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hedefi başlat" })).not.toBeInTheDocument();
  });

  it("persists assistant message likes and dislikes through the feedback API", async () => {
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
      },
      "GET /assistant/home": {
        today_summary: "Feedback yüzeyi hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        connector_sync_status: { items: [] },
        assistant_known_profile: {},
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
      "GET /assistant/approvals": { items: [] },
      "GET /assistant/thread/starred": { items: [] },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-08T11:00:00Z", updated_at: "2026-04-08T11:05:00Z" },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Bu plan işine yararsa benzerlerini sürdürebilirim.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            generated_from: "daily_plan",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: null,
            feedback_note: null,
            feedback_at: null,
            created_at: "2026-04-08T11:05:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
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
      "PATCH /assistant/thread/messages/1/feedback": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}")) as { feedback_value?: string };
        const feedbackValue = payload.feedback_value === "liked" || payload.feedback_value === "disliked" ? payload.feedback_value : null;
        return {
          message: {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Bu plan işine yararsa benzerlerini sürdürebilirim.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            generated_from: "daily_plan",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: feedbackValue,
            feedback_note: null,
            feedback_at: feedbackValue ? "2026-04-08T11:06:00Z" : null,
            created_at: "2026-04-08T11:05:00Z",
          },
          generated_from: "assistant_thread_memory",
        };
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bu plan işine yararsa benzerlerini sürdürebilirim.")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Yanıtı beğen"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "true"));

    fireEvent.click(screen.getByLabelText("Yanıtı beğenme"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğenme")).toHaveAttribute("aria-pressed", "true"));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/assistant/thread/messages/1/feedback"),
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("clears assistant message feedback when the same reaction is tapped twice", async () => {
    const feedbackPayloads: Array<{ feedback_value?: string }> = [];
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
      },
      "GET /assistant/home": {
        today_summary: "Feedback yüzeyi hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        connector_sync_status: { items: [] },
        assistant_known_profile: {},
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
      "GET /assistant/approvals": { items: [] },
      "GET /assistant/thread/starred": { items: [] },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-08T11:00:00Z", updated_at: "2026-04-08T11:05:00Z" },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Bu plan işine yararsa benzerlerini sürdürebilirim.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            generated_from: "daily_plan",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: null,
            feedback_note: null,
            feedback_at: null,
            created_at: "2026-04-08T11:05:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
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
      "PATCH /assistant/thread/messages/1/feedback": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}")) as { feedback_value?: string };
        feedbackPayloads.push(payload);
        const feedbackValue = payload.feedback_value === "liked" || payload.feedback_value === "disliked" ? payload.feedback_value : null;
        return {
          message: {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Bu plan işine yararsa benzerlerini sürdürebilirim.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            generated_from: "daily_plan",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: feedbackValue,
            feedback_note: null,
            feedback_at: feedbackValue ? "2026-04-08T11:06:00Z" : null,
            created_at: "2026-04-08T11:05:00Z",
          },
          generated_from: "assistant_thread_memory",
        };
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bu plan işine yararsa benzerlerini sürdürebilirim.")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Yanıtı beğen"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "true"));

    fireEvent.click(screen.getByLabelText("Yanıtı beğen"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "false"));
    expect(feedbackPayloads.at(-1)?.feedback_value).toBe("none");
  });

  it("opens a feedback reason composer and persists the explanation note", async () => {
    const feedbackPayloads: Array<{ feedback_value?: string; note?: string }> = [];
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
      },
      "GET /assistant/home": {
        today_summary: "Feedback yüzeyi hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
        proactive_suggestions: [],
        connector_sync_status: { items: [] },
        assistant_known_profile: {},
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
      "GET /assistant/approvals": { items: [] },
      "GET /assistant/thread/starred": { items: [] },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-08T11:00:00Z", updated_at: "2026-04-08T11:05:00Z" },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Annene sıcak bir mesaj ve küçük bir çiçek önerisi hazırladım.",
            linked_entities: [{ type: "contact", id: "mother", label: "Anne" }],
            tool_suggestions: [],
            draft_preview: null,
            source_context: { recipient: "Anne" },
            requires_approval: false,
            generated_from: "message_draft",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: null,
            feedback_note: null,
            feedback_at: null,
            created_at: "2026-04-08T11:05:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
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
      "PATCH /assistant/thread/messages/1/feedback": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}")) as { feedback_value?: string; note?: string };
        feedbackPayloads.push(payload);
        const feedbackValue = payload.feedback_value === "liked" || payload.feedback_value === "disliked" ? payload.feedback_value : null;
        return {
          message: {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Annene sıcak bir mesaj ve küçük bir çiçek önerisi hazırladım.",
            linked_entities: [{ type: "contact", id: "mother", label: "Anne" }],
            tool_suggestions: [],
            draft_preview: null,
            source_context: { recipient: "Anne" },
            requires_approval: false,
            generated_from: "message_draft",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: feedbackValue,
            feedback_note: payload.note || null,
            feedback_at: feedbackValue ? "2026-04-08T11:06:00Z" : null,
            created_at: "2026-04-08T11:05:00Z",
          },
          generated_from: "assistant_thread_memory",
        };
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Annene sıcak bir mesaj ve küçük bir çiçek önerisi hazırladım.")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Yanıtı beğen"));
    await waitFor(() => expect(screen.getByText("Neyi beğendin?")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("Örneğin: Anneme sıcak yazman iyiydi, çiçek önerin de uygundu."), {
      target: { value: "Anneme sıcak yazman ve çiçek önermen tam istediğim gibi." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() => expect(feedbackPayloads.at(-1)?.note).toBe("Anneme sıcak yazman ve çiçek önermen tam istediğim gibi."));
    await waitFor(() => expect(screen.getByText("Anneme sıcak yazman ve çiçek önermen tam istediğim gibi.")).toBeInTheDocument());
  });
});
