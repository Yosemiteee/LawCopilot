import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

const scrollIntoViewMock = vi.fn();
const scrollToMock = vi.fn();

class MockIntersectionObserver {
  disconnect = vi.fn();
  observe = vi.fn();
  unobserve = vi.fn();
  takeRecords = vi.fn(() => []);
  root = null;
  rootMargin = "0px";
  thresholds = [];
}

class MockSpeechRecognition {
  continuous = false;
  interimResults = false;
  lang = "tr-TR";
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn(() => {
    this.onend?.();
  });
}

Object.defineProperty(globalThis, "IntersectionObserver", {
  configurable: true,
  writable: true,
  value: MockIntersectionObserver,
});

Object.defineProperty(globalThis, "SpeechRecognition", {
  configurable: true,
  writable: true,
  value: MockSpeechRecognition,
});

Object.defineProperty(globalThis, "webkitSpeechRecognition", {
  configurable: true,
  writable: true,
  value: MockSpeechRecognition,
});

Object.defineProperty(window, "speechSynthesis", {
  configurable: true,
  writable: true,
  value: {
    cancel: vi.fn(),
    speak: vi.fn(),
    getVoices: vi.fn(() => []),
  },
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  writable: true,
  value: scrollIntoViewMock,
});

Object.defineProperty(HTMLElement.prototype, "scrollTo", {
  configurable: true,
  writable: true,
  value: scrollToMock,
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

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

  it("opens the thread pinned to the latest messages", async () => {
    scrollToMock.mockClear();

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
        messages: [
          {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "İlk mesaj",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
          {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Son mesaj",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:01:00Z",
          },
        ],
        has_more: false,
        total_count: 2,
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Son mesaj")).toBeInTheDocument());
    await waitFor(() => expect(scrollToMock).toHaveBeenCalled());
  });

  it("shows proactive greeting cards and can trigger a prepared assistant action", async () => {
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
      "GET /assistant/home": {
        greeting_title: "Selam Sami",
        greeting_message: "Sami, takvimini ve açık işleri taradım.",
        today_summary: "Selam Sami. Bugün 1 ajanda maddesi var. İstersen hemen şunu başlatabilirim: Müvekkil teyidi hazırlanabilir.",
        counts: {
          agenda: 1,
          inbox: 0,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [
          {
            id: "proactive-1",
            kind: "draft_client_update",
            title: "Müvekkil teyidi hazırlanabilir",
            details: "Yarınki görüşme için müvekkile kısa bir teyit e-postası hazırlayabilirim.",
            action_label: "Taslak hazırla",
            prompt: "E-posta hazırla: yarınki görüşme için müvekkile kısa teyit mesajı oluştur.",
            matter_id: 42,
            tool: "drafts",
            priority: "high",
          },
        ],
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
      "POST /assistant/thread/messages": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        expect(payload.content).toContain("E-posta hazırla");
        expect(payload.matter_id).toBe(42);
        return {
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          messages: [
            {
              id: 99,
              thread_id: 1,
              office_id: "default-office",
              role: "assistant",
              content: "Taslak hazır. Göndermeden önce inceleyebilirsin.",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {},
              requires_approval: false,
              created_at: "2026-03-14T10:00:00Z",
            },
          ],
          has_more: false,
          total_count: 1,
        };
      },
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Selam Sami")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Taslak hazırla" }));

    await waitFor(() => expect(screen.getByText("Taslak hazır. Göndermeden önce inceleyebilirsin.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalled();
  });

  it("shows Google access state on the welcome screen when Google is connected", async () => {
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
        greeting_title: "Selam Sami",
        greeting_message: "Sami, bağlantılarını gözden geçirdim.",
        today_summary: "Bugün için kısa bir özet hazır.",
        counts: {
          agenda: 1,
          inbox: 2,
          calendar_today: 3,
          drafts_pending: 1,
        },
        priority_items: [],
        proactive_suggestions: [],
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
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
        google_connected: true,
        items: [],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        account_label: "Sami Google",
        scopes: [
          "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/calendar.readonly",
          "https://www.googleapis.com/auth/drive.metadata.readonly",
        ],
        gmail_connected: true,
        calendar_connected: true,
        drive_connected: true,
        calendar_write_ready: false,
        status: "connected",
        email_thread_count: 12,
        calendar_event_count: 20,
        drive_file_count: 8,
        last_sync_at: "2026-03-15T09:30:00Z",
        connected_account: null,
        desktop_managed: true,
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Sami Google")).toBeInTheDocument());
    expect(screen.getByText("Gmail, Takvim ve Drive verileri asistanın kullanımına açık. Sorularınızda bu kaynaklara da bakabilirim.")).toBeInTheDocument();
    expect(screen.getByText("12 Gmail konuşması")).toBeInTheDocument();
    expect(screen.getByText("20 Takvim kaydı")).toBeInTheDocument();
    expect(screen.getByText("8 Drive dosyası")).toBeInTheDocument();
  });

  it("dismisses the session summary after triggering its quick action", async () => {
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
      "GET /assistant/home": {
        greeting_title: "Selam Sami",
        greeting_message: "Sami, takvimini ve iletilerini taradım.",
        today_summary: "Selam Sami. İstersen hemen şunu başlatabilirim: iletişimleri önceliklendir.",
        counts: {
          agenda: 1,
          inbox: 1,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [
          {
            id: "proactive-talk",
            kind: "conversation",
            title: "İletişimleri önceliklendir",
            details: "Önce cevap bekleyen iletişimleri özetleyebilirim.",
            action_label: "Bunu konuşalım",
            prompt: "Cevap bekleyen iletişimleri özetle ve önceliklendir.",
            tool: "inbox",
            priority: "high",
          },
        ],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 11,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Merhaba Sami, hazırsan başlayalım.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "POST /assistant/thread/messages": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        expect(payload.content).toContain("iletişimleri özetle");
        return {
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          messages: [
            {
              id: 12,
              thread_id: 1,
              office_id: "default-office",
              role: "assistant",
              content: "İletişimleri özetledim.",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {},
              requires_approval: false,
              created_at: "2026-03-14T10:01:00Z",
            },
          ],
          has_more: false,
          total_count: 2,
        };
      },
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Bunu konuşalım" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Bunu konuşalım" }));

    await waitFor(() => expect(screen.queryByLabelText("Özet panelini kapat")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalled();
  });

  it("can close the session summary without sending a reply", async () => {
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
      "GET /assistant/home": {
        greeting_title: "Selam Sami",
        greeting_message: "Sami, gününü özetledim.",
        today_summary: "Selam Sami. Bugün için kısa bir özet hazırladım.",
        counts: {
          agenda: 1,
          inbox: 0,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [
          {
            id: "proactive-close",
            kind: "conversation",
            title: "Günü planla",
            details: "İstersen birlikte planlayabiliriz.",
            action_label: "Bunu konuşalım",
            prompt: "Bugünü birlikte planlayalım.",
            tool: "today",
            priority: "medium",
          },
        ],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 21,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Kısa bir giriş mesajı.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByLabelText("Özet panelini kapat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Özet panelini kapat"));

    await waitFor(() => expect(screen.queryByLabelText("Özet panelini kapat")).not.toBeInTheDocument());
    expect(screen.queryByText("Sami, gününü özetledim.")).not.toBeInTheDocument();
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

  it("renders assistant markdown emphasis without showing raw stars", async () => {
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
        messages: [
          {
            id: 11,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Merhaba **Sami**\n**Bugün** plan hazır.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-11T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Sami", { selector: "strong" })).toBeInTheDocument());
    expect(screen.getByText("Bugün", { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByText("**Sami**")).not.toBeInTheDocument();
  });

  it("hides duplicated navigation actions when they repeat suggested directions", async () => {
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
        messages: [
          {
            id: 31,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Taslakları önce burada takip edebiliriz.",
            linked_entities: [],
            tool_suggestions: [
              {
                tool: "drafts",
                label: "Taslaklar",
                reason: "Taslaklar ve onay bekleyen dış aksiyonlar burada görünür.",
              },
            ],
            draft_preview: null,
            source_context: {
              proposed_actions: [
                {
                  tool: "drafts",
                  label: "Taslaklar",
                  reason: "Aynı yönlendirme ikinci kez gelmemeli.",
                  type: "navigation",
                },
              ],
            },
            requires_approval: false,
            created_at: "2026-03-11T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Taslakları önce burada takip edebiliriz.")).toBeInTheDocument());
    expect(screen.getByText("Önerilen yönlendirmeler")).toBeInTheDocument();
    expect(screen.queryByText("Önerilen aksiyonlar")).not.toBeInTheDocument();
  });

  it("opens voice conversation mode from the composer", async () => {
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

    expect(screen.getByText("Sesli görüşme")).toBeInTheDocument();
    expect(screen.getByText("Sizi dinliyorum...")).toBeInTheDocument();
    expect(screen.getByText("Henüz konuşma algılanmadı.")).toBeInTheDocument();
  });

  it("allows the tools drawer to enter fullscreen mode", async () => {
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
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: {
          agenda: 1,
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
      "GET /assistant/agenda": {
        items: [
          {
            id: "agenda-1",
            kind: "task",
            title: "Duruşma notları",
            details: "Ön hazırlık",
            priority: "medium",
            due_at: "2026-03-11T09:30:00Z",
            source_type: "task",
            source_ref: "task-1",
          },
        ],
        generated_from: "assistant_agenda_engine",
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
    });

    renderApp(["/assistant?tool=today"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByLabelText("Araçları tam ekrana al").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Araçları tam ekrana al")[0]);

    await waitFor(() => expect(screen.getByLabelText("Araçları normal boyuta döndür")).toBeInTheDocument());
  });

  it("shows Google Drive files together with workspace documents in the documents drawer", async () => {
    const openPathInOS = vi.fn().mockResolvedValue({ ok: true });
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
        today_summary: "Google verileri senkron durumda.",
        counts: {
          agenda: 1,
          inbox: 1,
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
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        account_label: "Sami Google",
        scopes: ["https://www.googleapis.com/auth/drive.readonly"],
        gmail_connected: true,
        calendar_connected: true,
        drive_connected: true,
        status: "connected",
        drive_file_count: 1,
        last_sync_at: "2026-03-14T09:30:00Z",
        desktop_managed: true,
      },
      "GET /workspace/documents": {
        configured: true,
        workspace_root_id: 1,
        items: [
          {
            id: 7,
            office_id: "default-office",
            workspace_root_id: 1,
            relative_path: "dilekceler/kira_ihtar.txt",
            display_name: "kira_ihtar.txt",
            extension: ".txt",
            content_type: "text/plain",
            size_bytes: 1200,
            mtime: 1710000000,
            checksum: "abc",
            parser_status: "parsed",
            indexed_status: "indexed",
            document_language: "tr",
            created_at: "2026-03-14T08:00:00Z",
            updated_at: "2026-03-14T08:00:00Z",
          },
        ],
      },
      "GET /integrations/google/drive-files?limit=30": {
        configured: true,
        connected: true,
        generated_from: "google_drive_mirror",
        items: [
          {
            id: 21,
            office_id: "default-office",
            provider: "google",
            external_id: "drive-21",
            name: "vekalet_taslagi.docx",
            mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            web_view_link: "https://drive.google.com/file/d/drive-21/view",
            modified_at: "2026-03-14T09:30:00Z",
            matter_id: null,
            created_at: "2026-03-14T09:30:00Z",
            updated_at: "2026-03-14T09:30:00Z",
          },
        ],
      },
    });

    renderApp(["/assistant?tool=documents"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: { openPathInOS },
    });

    await waitFor(() => expect(screen.getAllByText("Google Drive").length).toBeGreaterThan(0));
    expect(screen.getByText("vekalet_taslagi.docx")).toBeInTheDocument();
    expect(screen.getByText("kira_ihtar.txt")).toBeInTheDocument();
    expect(screen.getByText("İndekslendi")).toBeInTheDocument();
    expect(screen.queryByText("indexed")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Belgeyi aç" }));
    await waitFor(() => expect(openPathInOS).toHaveBeenCalledWith("dilekceler/kira_ihtar.txt"));
    expect(screen.getByRole("link", { name: "Drive'da aç" })).toBeInTheDocument();
  });

  it("renders file drawer cards with Turkish labels instead of raw English values", async () => {
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
      "GET /assistant/home": {
        today_summary: "Dosya bağlamları hazır.",
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
      "GET /integrations/google/status": {
        provider: "google",
        configured: false,
        enabled: false,
        scopes: [],
        gmail_connected: false,
        calendar_connected: false,
        drive_connected: false,
        status: "pending",
        desktop_managed: true,
      },
      "GET /matters": {
        items: [
          {
            id: 17,
            office_id: "default-office",
            title: "Activity matter",
            client_name: "Deneme Müvekkil",
            status: "active",
            practice_area: null,
            opened_at: "2026-03-14T08:00:00Z",
            created_at: "2026-03-14T08:00:00Z",
            updated_at: "2026-03-14T08:00:00Z",
          },
          {
            id: 18,
            office_id: "default-office",
            title: "Task recommendation matter",
            client_name: null,
            status: "on_hold",
            practice_area: null,
            opened_at: "2026-03-14T08:00:00Z",
            created_at: "2026-03-14T08:00:00Z",
            updated_at: "2026-03-14T08:00:00Z",
          },
        ],
      },
    });

    renderApp(["/assistant?tool=matters"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Etkinlik dosyası")).toBeInTheDocument());
    expect(screen.getByText("Görev öneri dosyası")).toBeInTheDocument();
    expect(screen.getByText("Açık")).toBeInTheDocument();
    expect(screen.getByText("Beklemede")).toBeInTheDocument();
    expect(screen.queryByText("Activity matter")).not.toBeInTheDocument();
    expect(screen.queryByText("active")).not.toBeInTheDocument();
  });

  it("shows web and seyahat sonuçları and lets the user approve a prepared action inside the chat", async () => {
    const dispatchApprovedAction = vi.fn(async () => ({ ok: true, message: "Gönderildi." }));

    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: false,
        workspace_configured: true,
        workspace_root_name: "Belge Havuzu",
        google_configured: false,
        calendar_connected: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        today_summary: "Hazır.",
        counts: {
          agenda: 0,
          inbox: 0,
          calendar_today: 0,
          drafts_pending: 1,
        },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 201,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "İlk seçenekleri topladım ve istersen rezervasyonu da hazırlayabilirim.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: {
              id: 88,
              office_id: "default-office",
              matter_id: null,
              draft_type: "reserve_travel_ticket",
              channel: "travel",
              to_contact: null,
              subject: "İstanbul Ankara tren bileti",
              body: "Rezervasyon bağlantısını açmaya hazırım.",
              approval_status: "pending_review",
              delivery_status: "draft",
              source_context: {
                booking_url: "https://example.com/booking",
              },
              generated_from: "assistant_actions",
              created_by: "tester",
              created_at: "2026-03-14T10:00:00Z",
              updated_at: "2026-03-14T10:00:00Z",
            },
            source_context: {
              web_search_results: [
                {
                  title: "Güncel tren saatleri",
                  url: "https://example.com/tren",
                  snippet: "İstanbul Ankara arasında güncel saatler.",
                },
              ],
              travel_options: [
                {
                  title: "Hızlı tren seçeneği",
                  url: "https://example.com/booking",
                  snippet: "Sabah 09:00 kalkış, 4 saat 20 dakika.",
                },
              ],
              approval_requests: [
                {
                  id: "assistant-action-55",
                  action_id: 55,
                  draft_id: 88,
                  tool: "travel",
                  title: "İstanbul Ankara tren bileti",
                  reason: "Onay verirsen rezervasyon bağlantısını açarım.",
                  status: "pending_review",
                },
              ],
              assistant_action: {
                id: 55,
                target_channel: "travel",
              },
            },
            requires_approval: true,
            created_at: "2026-03-14T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "POST /assistant/approvals/assistant-action-55/approve": {
        action: {
          id: 55,
          target_channel: "travel",
        },
        draft: {
          id: 88,
          channel: "travel",
          subject: "İstanbul Ankara tren bileti",
          body: "Rezervasyon bağlantısını açmaya hazırım.",
          source_context: {
            booking_url: "https://example.com/booking",
          },
        },
        dispatch_mode: "ready_to_send",
      },
      "GET /assistant/agenda": {
        items: [],
        generated_from: "assistant_agenda_engine",
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
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: {
        dispatchApprovedAction,
      },
    });

    await waitFor(() => expect(screen.getByText("Bulduğum bağlantılar")).toBeInTheDocument());
    expect(screen.getByText("Seyahat seçenekleri")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Onayla ve gönder" }));
    await waitFor(() => expect(dispatchApprovedAction).toHaveBeenCalled());
  });

  it("lets the user approve and send a draft directly from the drafts tool", async () => {
    const dispatchApprovedAction = vi.fn(async () => ({ ok: true, message: "Gönderildi." }));
    let draftState = {
      id: 14,
      draft_type: "send_email",
      channel: "email",
      to_contact: "samiyusuf178@gmail.com",
      subject: "Selam",
      body: "Merhaba, sana selamımı iletmek istedim.",
      approval_status: "pending_review",
      delivery_status: "not_sent",
      dispatch_state: "idle",
      created_at: "2026-03-15T09:00:00Z",
      updated_at: "2026-03-15T09:00:00Z",
    };

    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: false,
        workspace_configured: true,
        workspace_root_name: "Belge Havuzu",
        google_configured: true,
        calendar_connected: true,
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
          drafts_pending: 1,
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
      "GET /assistant/drafts": () => ({
        items: [draftState],
        matter_drafts: [],
        generated_from: "assistant_agenda_engine",
      }),
      "POST /assistant/drafts/14/send": () => {
        draftState = {
          ...draftState,
          approval_status: "approved",
          delivery_status: "ready_to_send",
          dispatch_state: "ready",
          updated_at: "2026-03-15T09:01:00Z",
        };
        return {
          draft: draftState,
          action: {
            id: 91,
            target_channel: "email",
          },
          message: "Taslak gönderime hazırlandı.",
          dispatch_mode: "ready_to_send",
        };
      },
      "GET /assistant/calendar": {
        today: "2026-03-15",
        generated_from: "assistant_calendar_engine",
        google_connected: true,
        items: [],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        scopes: [],
        gmail_connected: true,
        calendar_connected: true,
        drive_connected: true,
        email_thread_count: 3,
        calendar_event_count: 2,
        drive_file_count: 4,
        status: "connected",
        desktop_managed: true,
      },
    });

    renderApp(["/assistant?tool=drafts"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: {
        dispatchApprovedAction,
      },
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Onayla ve gönder" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Onayla ve gönder" }));
    await waitFor(() =>
      expect(dispatchApprovedAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionId: 91,
          draftId: 14,
          channel: "email",
        }),
      ),
    );
  });
});
