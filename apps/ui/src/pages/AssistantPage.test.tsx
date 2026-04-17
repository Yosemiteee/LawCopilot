import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

const scrollIntoViewMock = vi.fn();
const scrollToMock = vi.fn();
const createObjectUrlMock = vi.fn(() => "blob:lawcopilot-preview");
const revokeObjectUrlMock = vi.fn();
const clipboardWriteTextMock = vi.fn(() => Promise.resolve());

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
  static instances: MockSpeechRecognition[] = [];
  continuous = false;
  interimResults = false;
  lang = "tr-TR";
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  constructor() {
    MockSpeechRecognition.instances.push(this);
  }
  start = vi.fn();
  stop = vi.fn(() => {
    this.onend?.();
  });
  emitResult(transcript: string, isFinal = false) {
    this.onresult?.({
      results: [
        {
          0: { transcript },
          isFinal,
        },
      ],
    });
  }
  static reset() {
    MockSpeechRecognition.instances = [];
  }
}

class MockSpeechSynthesisUtterance {
  text: string;
  lang = "";
  voice: SpeechSynthesisVoice | null = null;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

class MockMediaRecorder {
  static instances: MockMediaRecorder[] = [];
  static isTypeSupported = vi.fn((mimeType: string) => mimeType.includes("webm") || mimeType.includes("ogg"));
  stream: MediaStream;
  mimeType: string;
  state: "inactive" | "recording" = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(stream: MediaStream, options?: { mimeType?: string }) {
    this.stream = stream;
    this.mimeType = String(options?.mimeType || "audio/webm");
    MockMediaRecorder.instances.push(this);
  }
  start = vi.fn(() => {
    this.state = "recording";
  });
  stop = vi.fn(() => {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["lawcopilot-audio"], { type: this.mimeType }) });
    this.onstop?.();
  });
  static reset() {
    MockMediaRecorder.instances = [];
  }
}

let mockSpeechVoices: SpeechSynthesisVoice[] = [];
const speechSynthesisMock = {
  cancel: vi.fn(),
  speak: vi.fn((utterance: MockSpeechSynthesisUtterance) => {
    utterance.onstart?.();
    utterance.onend?.();
  }),
  getVoices: vi.fn(() => mockSpeechVoices),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};

function ndjsonResponse(events: unknown[]) {
  return new Response(
    events.map((item) => JSON.stringify(item)).join("\n"),
    {
      status: 200,
      headers: { "Content-Type": "application/x-ndjson" },
    },
  );
}

function delayedNdjsonResponse(events: unknown[], delayMs = 40) {
  const encoder = new TextEncoder();
  let index = 0;
  return new Response(
    new ReadableStream({
      start(controller) {
        const push = () => {
          if (index >= events.length) {
            controller.close();
            return;
          }
          controller.enqueue(encoder.encode(`${JSON.stringify(events[index])}\n`));
          index += 1;
          setTimeout(push, delayMs);
        };
        push();
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "application/x-ndjson" },
    },
  );
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
  value: speechSynthesisMock,
});

Object.defineProperty(globalThis, "SpeechSynthesisUtterance", {
  configurable: true,
  writable: true,
  value: MockSpeechSynthesisUtterance,
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

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  writable: true,
  value: createObjectUrlMock,
});

Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  writable: true,
  value: revokeObjectUrlMock,
});

Object.defineProperty(globalThis.navigator, "clipboard", {
  configurable: true,
  writable: true,
  value: {
    writeText: clipboardWriteTextMock,
  },
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  MockSpeechRecognition.reset();
  MockMediaRecorder.reset();
  mockSpeechVoices = [];
  window.localStorage.clear();
  window.sessionStorage.clear();
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

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument();
    expect(screen.getByTitle("Sohbetlerde ara")).toBeInTheDocument();
    expect(screen.getByLabelText("Yeni sohbet")).toBeInTheDocument();
    expect(screen.queryByTitle("Takvim")).not.toBeInTheDocument();
    expect(screen.getByText("Google hesabımı bağla")).toBeInTheDocument();
    expect(screen.queryByText("Bugün özeti")).not.toBeInTheDocument();
    expect(screen.queryByText("Asistanın bildikleri")).not.toBeInTheDocument();
    expect(screen.queryByText("İletişim hafızası")).not.toBeInTheDocument();
  });

  it("renames and deletes threads from the sidebar overflow menu", async () => {
    let threads = [
      {
        id: 1,
        office_id: "default-office",
        title: "İlk sohbet",
        updated_at: "2026-04-08T10:00:00Z",
        last_message_at: "2026-04-08T10:00:00Z",
        last_message_preview: "İlk sohbet özeti",
      },
      {
        id: 2,
        office_id: "default-office",
        title: "İkinci sohbet",
        updated_at: "2026-04-08T09:30:00Z",
        last_message_at: "2026-04-08T09:30:00Z",
        last_message_preview: "İkinci sohbet özeti",
      },
    ];
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": (input: RequestInfo | URL) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        const threadId = Number(url.searchParams.get("thread_id") || 1);
        const thread = threads.find((item) => item.id === threadId) || threads[0];
        return {
          thread: { id: thread.id, office_id: "default-office", title: thread.title, status: "active" },
          messages: [],
          has_more: false,
          total_count: 0,
        };
      },
      "GET /assistant/threads": () => ({
        items: threads,
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      }),
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-08",
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
      "PATCH /assistant/threads/1": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}")) as { title?: string };
        threads = threads.map((item) => (
          item.id === 1 ? { ...item, title: String(payload.title || item.title) } : item
        ));
        return {
          thread: { id: 1, office_id: "default-office", title: threads[0].title, status: "active" },
          generated_from: "assistant_thread_memory",
        };
      },
      "DELETE /assistant/threads/2": () => {
        threads = threads.filter((item) => item.id !== 2);
        return {
          deleted_thread_id: 2,
          selected_thread_id: 1,
          items: threads,
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

    await waitFor(() => expect(screen.getByText("İlk sohbet")).toBeInTheDocument());

    const firstThreadRow = screen.getByText("İlk sohbet").closest(".assistant-history-row");
    expect(firstThreadRow).not.toBeNull();
    const firstMenuTrigger = firstThreadRow?.querySelector<HTMLButtonElement>(".assistant-history-row__menu-trigger");
    expect(firstMenuTrigger).not.toBeNull();
    fireEvent.click(firstMenuTrigger!);
    await screen.findByRole("menuitem", { name: "Yeniden adlandır" });
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(screen.queryByRole("menuitem", { name: "Yeniden adlandır" })).not.toBeInTheDocument());

    fireEvent.click(firstMenuTrigger!);
    const renameMenuItem = await screen.findByRole("menuitem", { name: "Yeniden adlandır" });
    fireEvent.click(renameMenuItem);

    const renameInput = screen.getByDisplayValue("İlk sohbet");
    fireEvent.change(renameInput, { target: { value: "Müvekkil görüşmesi" } });
    fireEvent.keyDown(renameInput, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("Müvekkil görüşmesi")).toBeInTheDocument());

    const secondThreadRow = screen.getByText("İkinci sohbet").closest(".assistant-history-row");
    expect(secondThreadRow).not.toBeNull();
    const secondMenuTrigger = secondThreadRow?.querySelector<HTMLButtonElement>(".assistant-history-row__menu-trigger");
    expect(secondMenuTrigger).not.toBeNull();
    fireEvent.click(secondMenuTrigger!);
    const deleteMenuItem = await screen.findByRole("menuitem", { name: "Sil" });
    fireEvent.click(deleteMenuItem);

    await waitFor(() => expect(screen.getByRole("dialog", { name: "Sohbet silinsin mi?" })).toBeInTheDocument());
    expect(screen.getByText(/kalıcı olarak sohbet listesinden kaldırılacak/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vazgeç" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sohbeti sil" }));

    await waitFor(() => expect(screen.queryByText("İkinci sohbet")).not.toBeInTheDocument());
  });

  it("renders chat-driven integration setup cards with deep links and oauth handoff", async () => {
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Slack kurulumu sohbette devam ediyor.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Slack kurulumu", status: "active" },
        messages: [
          {
            id: 11,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Slack bağlantısını kaydettim. OAuth yetkilendirmesini tamamlaman gerekiyor.",
            requires_approval: false,
            generated_from: "assistant_integration_orchestration",
            ai_provider: null,
            ai_model: null,
            created_at: "2026-04-08T10:00:00Z",
            starred: false,
            starred_at: null,
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: {},
            source_context: {
              integration_setup: {
                service_name: "Slack",
                connector_id: "slack",
                status: "oauth_pending",
                access_level: "read_only",
                next_step: "Son adım: izin ekranını açıp bağlantıyı onayla.",
                review_summary: ["Istenen izinler: channels:read, channels:history"],
                capabilities: ["Kanalları listele", "Mesajları oku"],
                skill: {
                  summary: "Slack ile mesajlari ve kanallari okuyup ozetleyebilirim.",
                },
                deep_link_path: "/integrations?connector=slack&setup=1",
                authorization_url: "https://slack.com/oauth/v2/authorize?state=test",
                suggested_replies: ["Baglandim", "Durumu kontrol et"],
              },
            },
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-08",
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

    await waitFor(() => expect(screen.getByText("Bağlantı yardımcısı")).toBeInTheDocument());
    expect(screen.getByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("Slack ile mesajlari ve kanallari okuyup ozetleyebilirim.")).toBeInTheDocument();
    expect(screen.getByText("Son adım: izin ekranını açıp bağlantıyı onayla.")).toBeInTheDocument();
    expect(screen.getByText("Kanalları listele")).toBeInTheDocument();
    expect(screen.getByText("Mesajları oku")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kurulum ekranını aç" })).toHaveAttribute("href", "/integrations?connector=slack&setup=1");
    expect(screen.getByRole("link", { name: "İzin ekranını aç" })).toHaveAttribute("href", "https://slack.com/oauth/v2/authorize?state=test");
    expect(screen.getByRole("button", { name: "Baglandim" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Durumu kontrol et" })).toBeInTheDocument();
  });

  it("runs legacy setup actions directly from the chat card", async () => {
    const runAssistantLegacySetup = vi.fn(() => Promise.resolve({ ok: true }));
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Kuruluma sohbetten devam edebilirsin.",
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
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Google kurulumu",
            created_by: "tester",
            created_at: "2026-04-08T08:00:00Z",
            updated_at: "2026-04-08T08:01:00Z",
            message_count: 1,
            last_message_preview: "Google kurulumu devam ediyor.",
            last_message_at: "2026-04-08T08:01:00Z",
          },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Google kurulumu", status: "active" },
        messages: [
          {
            id: 10,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Google kurulumu için son adıma geçebiliriz.",
            created_at: "2026-04-08T08:01:00Z",
            feedback_value: null,
            feedback_note: null,
            source_context: {
              integration_setup: {
                id: 22,
                service_name: "Google",
                connector_id: "gmail",
                status: "ready_for_desktop_action",
                setup_mode: "legacy_desktop",
                access_level: "read_only",
                next_step: "Google izin ekranını açmaya hazırım.",
                review_summary: ["Client ID ve Client secret güvenli şekilde kaydedildi."],
                capabilities: ["E-postaları oku", "Takvimi görüntüle"],
                skill: {
                  summary: "Google ile e-postaları ve takvim kayıtlarını birlikte yönetebilirim.",
                },
                deep_link_path: "/settings?tab=kurulum&section=integration-google",
                desktop_action: "start_google_auth",
                desktop_cta_label: "Google izin ekranını aç",
                suggested_replies: ["Durumu kontrol et"],
              },
            },
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-08",
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
      desktop: {
        runAssistantLegacySetup,
      },
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bağlantı yardımcısı")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Google izin ekranını aç" }));
    await waitFor(() => expect(runAssistantLegacySetup).toHaveBeenCalledWith({ setupId: 22 }));
    expect(screen.getAllByRole("link", { name: "Kurulum ekranını aç" })[0]).toHaveAttribute("href", "/settings?tab=kurulum&section=integration-google");
  });

  it("auto-runs a legacy setup action when the assistant explicitly advances the active setup", async () => {
    const runAssistantLegacySetup = vi.fn(() => Promise.resolve({
      ok: true,
      desktopAction: "start_outlook_auth",
      message: "Microsoft izin ekranı açıldı.",
      status: {
        message: "Microsoft izin ekranı açıldı.",
      },
    }));

    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
      },
      "GET /assistant/threads?limit=40": {
        items: [{ id: 2, title: "Outlook kurulumu", starred: false, updated_at: new Date().toISOString() }],
        total_count: 1,
      },
      "GET /assistant/home": {
        today_summary: "",
        agenda: [],
        priority_items: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 2, office_id: "default-office", title: "Outlook kurulumu", status: "active" },
        messages: [
          {
            id: 20,
            thread_id: 2,
            office_id: "default-office",
            role: "assistant",
            content: "Son adım hazır, şimdi bağlayabilirsin.",
            created_at: new Date().toISOString(),
            feedback_value: null,
            feedback_note: null,
            source_context: {
              integration_setup: {
                id: 44,
                service_name: "Outlook",
                connector_id: "outlook-mail",
                status: "ready_for_desktop_action",
                setup_mode: "legacy_desktop",
                next_step: "Microsoft izin ekranını açmaya hazırım.",
                desktop_action: "start_outlook_auth",
                desktop_cta_label: "Microsoft izin ekranını aç",
                auto_run_desktop_action: true,
                deep_link_path: "/settings?tab=kurulum&section=integration-outlook",
              },
            },
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
    });

    renderApp(["/assistant"], {
      desktop: {
        runAssistantLegacySetup,
      },
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(runAssistantLegacySetup).toHaveBeenCalledWith({ setupId: 44 }));
  });

  it("shows live WhatsApp QR setup state inside the chat card", async () => {
    const runAssistantLegacySetup = vi.fn(() => Promise.resolve({
      ok: true,
      desktopAction: "start_whatsapp_web_link",
      message: "QR kodunu telefondaki WhatsApp ile tarayın.",
      status: {
        webStatus: "qr_required",
        webQrDataUrl: "data:image/png;base64,qr",
        webAccountLabel: "",
        message: "QR kodunu telefondaki WhatsApp ile tarayın.",
      },
    }));
    const getWhatsAppStatus = vi.fn(() => Promise.resolve({
      configured: false,
      enabled: true,
      mode: "web",
      webStatus: "qr_required",
      webQrDataUrl: "data:image/png;base64,qr",
      message: "QR kodunu telefondaki WhatsApp ile tarayın.",
    }));
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Kuruluma sohbetten devam edebilirsin.",
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
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "WhatsApp kurulumu",
            created_by: "tester",
            created_at: "2026-04-13T08:00:00Z",
            updated_at: "2026-04-13T08:01:00Z",
            message_count: 1,
            last_message_preview: "WhatsApp kurulumu devam ediyor.",
            last_message_at: "2026-04-13T08:01:00Z",
          },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "WhatsApp kurulumu", status: "active" },
        messages: [
          {
            id: 10,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "WhatsApp kişisel hesabını QR ile bağlayabiliriz.",
            created_at: "2026-04-13T08:01:00Z",
            feedback_value: null,
            feedback_note: null,
            source_context: {
              integration_setup: {
                id: 44,
                service_name: "WhatsApp",
                connector_id: "whatsapp",
                status: "ready_for_desktop_action",
                setup_mode: "legacy_desktop",
                access_level: "read_write",
                next_step: "QR kurulumunu başlatmaya hazırım.",
                review_summary: ["Kişisel WhatsApp hesabını QR ile bağlayacağız."],
                capabilities: ["Mesajları oku", "Mesaj gönder"],
                skill: {
                  summary: "WhatsApp mesajlarını görebilir ve yanıt hazırlayabilirim.",
                },
                deep_link_path: "/settings?tab=kurulum&section=integration-whatsapp",
                desktop_action: "start_whatsapp_web_link",
                desktop_cta_label: "WhatsApp QR kurulumunu aç",
                suggested_replies: ["Durumu kontrol et"],
              },
            },
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-13",
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
      desktop: {
        runAssistantLegacySetup,
        getWhatsAppStatus,
      },
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bağlantı yardımcısı")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "WhatsApp QR kurulumunu aç" }));

    await waitFor(() => expect(runAssistantLegacySetup).toHaveBeenCalledWith({ setupId: 44 }));
    await waitFor(() => expect(screen.getByText("Canlı kurulum durumu")).toBeInTheDocument());
    expect(screen.getAllByText("QR kodunu telefondaki WhatsApp ile tarayın.").length).toBeGreaterThan(0);
    expect(screen.getByAltText("WhatsApp QR kodu")).toHaveAttribute("src", "data:image/png;base64,qr");
    await waitFor(() => expect(getWhatsAppStatus).toHaveBeenCalled());
  });

  it("renders map preview cards in chat and opens them fullscreen", async () => {
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
        calendar_connected: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Harita kartı hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 1, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Kadıköy toplantısı", created_by: "tester", created_at: "2026-04-08T09:00:00Z", updated_at: "2026-04-08T09:05:00Z", message_count: 1, last_message_preview: "Haritayı açtım", last_message_at: "2026-04-08T09:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Kadıköy toplantısı", status: "active" },
        messages: [
          {
            id: 10,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Toplantı konumunu aşağıda açtım.",
            requires_approval: false,
            generated_from: "assistant_calendar_map",
            ai_provider: null,
            ai_model: null,
            created_at: "2026-04-08T10:00:00Z",
            starred: false,
            starred_at: null,
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {
              map_preview: {
                title: "Kadıköy toplantısı",
                subtitle: "9 Nisan 14:30 · Moda Sahili, Kadıköy",
                destination_label: "Moda Sahili, Kadıköy",
                destination_query: "Moda Sahili, Kadıköy",
                origin_label: "Ev",
                route_mode: "transit",
                maps_url: "https://maps.google.com/?q=Moda%20Sahili%2C%20Kadikoy",
                directions_url: "https://www.google.com/maps/dir/?api=1&destination=Moda%20Sahili%2C%20Kadikoy",
                embed_url: "https://www.google.com/maps?q=Moda%20Sahili%2C%20Kadikoy&output=embed",
                source_kind: "calendar_event",
                starts_at: "2026-04-09T14:30:00+03:00",
              },
            },
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-08",
        generated_from: "assistant_calendar_engine",
        google_connected: true,
        items: [],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        scopes: [],
        gmail_connected: false,
        calendar_connected: true,
        status: "connected",
        desktop_managed: true,
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Konum ve rota")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Yol tarifi" })).toHaveAttribute(
      "href",
      "https://www.google.com/maps/dir/?api=1&destination=Moda%20Sahili%2C%20Kadikoy",
    );
    expect(screen.getByRole("link", { name: "Haritada aç" })).toHaveAttribute(
      "href",
      "https://maps.google.com/?q=Moda%20Sahili%2C%20Kadikoy",
    );

    fireEvent.click(screen.getByLabelText("Kadıköy toplantısı haritasını büyüt"));
    const dialog = await screen.findByRole("dialog", { name: "Kadıköy toplantısı" });
    expect(within(dialog).getByText("Moda Sahili, Kadıköy")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Haritayı kapat" })).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Haritayı kapat" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Kadıköy toplantısı" })).not.toBeInTheDocument());
  });

  it("keeps advanced knowledge surfaces out of the empty welcome state", async () => {
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/home": {
        today_summary: "Asistan hafıza yüzeyi hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        proactive_suggestions: [
          {
            id: "rec-1",
            kind: "daily_plan",
            title: "Günü sadeleştir",
            details: "Takvim yoğun, akşam bloklarını hafifletebilirim.",
            action_label: "Planı aç",
            priority: "medium",
          },
        ],
        knowledge_health_summary: {
          contradictions: 0,
          stale_items: 1,
        },
        decision_timeline: [
          {
            id: "decision-1",
            title: "Akşam planı önerisi",
            summary: "Yoğun takvim nedeniyle akşam bloklarının hafifletilmesi önerildi.",
            risk_level: "A",
          },
        ],
        assistant_known_profile: {
          preferences: [
            {
              id: "pref-1",
              title: "İletişim tonu",
              summary: "Kısa, nazik ve net bir ton tercih ediliyor.",
              scope: "personal",
              record_type: "preference",
              sensitivity: "high",
              source_basis: ["profile:communication_style"],
            },
          ],
        },
        connector_sync_status: {
          items: [
            {
              connector: "email_threads",
              description: "E-posta mirror akışı",
              sync_mode: "mirror_pull",
              last_synced_at: "2026-04-07T18:00:00Z",
              record_count: 3,
              synced_record_count: 2,
              providers: [{ provider: "google", connected: true, account_label: "Google" }],
            },
          ],
        },
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
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
      "POST /assistant/memory/corrections": {
        action: "forget",
        page_key: "preferences",
        record_id: "pref-1",
        status: "forgotten",
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
  });

  it("shows only actionable work items in today drawer without priority badges", async () => {
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
        calendar_connected: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/agenda": {
        items: [
          {
            id: "follow-up-1",
            kind: "communication_follow_up",
            title: "Gmail: Ayse Kaya icin yanit hazirla",
            details: "Kira tahliye dosyasindaki son mesaji kisa ve net yanitla.",
            priority: "medium",
            due_at: "2026-03-14T10:30:00Z",
            source_type: "email_thread",
            source_ref: "gmail-thread-1",
            provider: "google",
            matter_id: 5,
            recommended_action_ids: [],
            manual_review_required: true,
          },
          {
            id: "draft-review-1",
            kind: "draft_review",
            title: "Dilekce taslagini son kez kontrol et",
            details: "Tahliye dilekcesi bugun cikacak, once son paragrafi gozden gecir.",
            priority: "high",
            due_at: "2026-03-14T13:00:00Z",
            source_type: "outbound_draft",
            source_ref: "draft-9",
            provider: null,
            matter_id: 5,
            recommended_action_ids: [],
            manual_review_required: true,
          },
        ],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/home": {
        today_summary: "Bugun icin 2 net is maddesi var.",
        counts: {
          agenda: 2,
          inbox: 1,
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
        items: [
          {
            id: "inbox-spam-1",
            kind: "reply_needed",
            title: "Bulten: Nisan kampanyalari",
            details: "Bu ham inbox kaydi Today sekmesinde gorunmemeli.",
            priority: "high",
            due_at: "2026-03-14T09:00:00Z",
            source_type: "email_thread",
            source_ref: "gmail-thread-spam",
            provider: "google",
            matter_id: null,
            recommended_action_ids: [],
            manual_review_required: false,
          },
        ],
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
        today: "2026-03-14",
        generated_from: "assistant_calendar_engine",
        google_connected: false,
        items: [],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
        gmail_connected: true,
        calendar_connected: false,
        status: "connected",
        desktop_managed: true,
      },
    });

    renderApp(["/assistant?tool=today"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bugün yapılması gerekenler")).toBeInTheDocument());
    expect(screen.getByText("Gmail: Ayse Kaya icin yanit hazirla")).toBeInTheDocument();
    expect(screen.getByText("Dilekce taslagini son kez kontrol et")).toBeInTheDocument();
    expect(screen.queryByText("Bulten: Nisan kampanyalari")).not.toBeInTheDocument();
    expect(screen.queryByText("Yüksek")).not.toBeInTheDocument();
    expect(screen.getByText("Gmail")).toBeInTheDocument();
    expect(screen.getByText("Taslak")).toBeInTheDocument();
    expect(screen.queryByText("Hafıza adayı yap")).not.toBeInTheDocument();
    expect(screen.queryByText("Kalıcı hafıza yap")).not.toBeInTheDocument();
    expect(screen.queryByText("Sadece operasyonel kalsın")).not.toBeInTheDocument();
  });

  it("closes the workbench drawer when the user sends a new chat message", async () => {
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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
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
        today: "2026-03-14",
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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 1,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Bugüne bakma, direkt bunu cevapla",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T09:59:59Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Tamam, sohbetten ilerleyelim.", content: "Tamam, sohbetten ilerleyelim." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Tamam, sohbetten ilerleyelim.",
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
        },
      ]),
    });

    renderApp(["/assistant?tool=today"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Bugün yapılması gerekenler")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Bugüne bakma, direkt bunu cevapla" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(screen.getByText("Tamam, sohbetten ilerleyelim.")).toBeInTheDocument());
    await waitFor(() => expect(screen.queryByText("Bugün yapılması gerekenler")).not.toBeInTheDocument());
  });

  it("shows sent image attachments as image previews instead of filename-only chips", async () => {
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
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
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Asistan",
            status: "active",
            created_at: "2026-04-03T19:00:00Z",
            updated_at: "2026-04-03T19:00:05Z",
            message_count: 2,
          },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-03",
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
      "POST /assistant/attachments/analyze": {
        source_ref: {
          type: "image_attachment",
          label: "Screenshot from 2026-04-03.png",
          content_type: "image/png",
          size_bytes: 4,
          uploaded: false,
        },
      },
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        { type: "thread_ready" },
        { type: "assistant_start" },
        { type: "assistant_chunk", content: "Görseli inceledim." },
        {
          type: "assistant_complete",
          response: {
            thread: {
              id: 1,
              office_id: "default-office",
              title: "Asistan",
              created_by: "tester",
              created_at: "2026-04-03T19:00:00Z",
              updated_at: "2026-04-03T19:00:05Z",
            },
            messages: [
              {
                id: 1,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "resmi inceleyebiliyor musun neler yazıyor",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  source_refs: [
                    {
                      type: "image_attachment",
                      label: "Screenshot from 2026-04-03.png",
                      content_type: "image/png",
                      size_bytes: 4,
                      uploaded: false,
                    },
                  ],
                },
                requires_approval: false,
                generated_from: "assistant_thread_user",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:00Z",
              },
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Görseli inceledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                generated_from: "assistant_thread_message",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
    });

    const { container } = renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["png!"], "Screenshot from 2026-04-03.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), { target: { value: "resmi inceleyebiliyor musun neler yazıyor" } });
    fireEvent.submit(screen.getByPlaceholderText(/Sorunuzu yazın/).closest("form") as HTMLFormElement);

    await waitFor(() => expect(screen.getByAltText("Screenshot from 2026-04-03.png")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("Görseli inceledim.").length).toBeGreaterThan(0));
  });

  it("clears composer attachments immediately after sending an image", async () => {
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
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
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Asistan",
            status: "active",
            created_at: "2026-04-03T19:00:00Z",
            updated_at: "2026-04-03T19:00:05Z",
            message_count: 2,
          },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-03",
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
      "POST /assistant/attachments/analyze": {
        source_ref: {
          type: "image_attachment",
          label: "Screenshot from 2026-04-03.png",
          content_type: "image/png",
          size_bytes: 4,
          uploaded: false,
        },
      },
      "POST /assistant/thread/messages/stream": delayedNdjsonResponse([
        { type: "thread_ready" },
        { type: "assistant_start" },
        { type: "assistant_chunk", content: "Görseli inceledim." },
        {
          type: "assistant_complete",
          response: {
            thread: {
              id: 1,
              office_id: "default-office",
              title: "Asistan",
              created_by: "tester",
              created_at: "2026-04-03T19:00:00Z",
              updated_at: "2026-04-03T19:00:05Z",
            },
            messages: [
              {
                id: 1,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "resmi incele",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  source_refs: [
                    {
                      type: "image_attachment",
                      label: "Screenshot from 2026-04-03.png",
                      content_type: "image/png",
                      size_bytes: 4,
                      uploaded: false,
                    },
                  ],
                },
                requires_approval: false,
                generated_from: "assistant_thread_user",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:00Z",
              },
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Görseli inceledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                generated_from: "assistant_thread_message",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ], 80),
    });

    const { container } = renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["png!"], "Screenshot from 2026-04-03.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(container.querySelector(".wa-attachments__list--composer")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), { target: { value: "resmi incele" } });
    fireEvent.submit(screen.getByPlaceholderText(/Sorunuzu yazın/).closest("form") as HTMLFormElement);

    await waitFor(() => expect(container.querySelector(".wa-attachments__list--composer")).toBeNull());
    await waitFor(() => expect(screen.getAllByText("Görseli inceledim.").length).toBeGreaterThan(0));
  });

  it("renders a sent pdf only on the user bubble and opens it in the preview modal", async () => {
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
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
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
        has_more: false,
        total_count: 0,
      },
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Asistan",
            status: "active",
            created_at: "2026-04-03T19:00:00Z",
            updated_at: "2026-04-03T19:00:05Z",
            message_count: 2,
          },
        ],
        selected_thread_id: 1,
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": {
        today: "2026-04-03",
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
      "POST /assistant/attachments/analyze": {
        source_ref: {
          type: "file_attachment",
          label: "Cv.pdf",
          content_type: "application/octet-stream",
          size_bytes: 4,
          uploaded: false,
        },
      },
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        { type: "thread_ready" },
        { type: "assistant_start" },
        { type: "assistant_chunk", content: "CV dosyasını inceledim." },
        {
          type: "assistant_complete",
          response: {
            thread: {
              id: 1,
              office_id: "default-office",
              title: "Asistan",
              created_by: "tester",
              created_at: "2026-04-03T19:00:00Z",
              updated_at: "2026-04-03T19:00:05Z",
            },
            messages: [
              {
                id: 1,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "bu belgeyi incele",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  source_refs: [
                    {
                      type: "file_attachment",
                      label: "Cv.pdf",
                      content_type: "application/octet-stream",
                      size_bytes: 4,
                      uploaded: false,
                    },
                  ],
                },
                requires_approval: false,
                generated_from: "assistant_thread_user",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:00Z",
              },
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "CV dosyasını inceledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  source_refs: [
                    {
                      type: "file_attachment",
                      label: "Cv.pdf",
                      content_type: "application/octet-stream",
                      size_bytes: 4,
                      uploaded: false,
                    },
                  ],
                },
                requires_approval: false,
                generated_from: "assistant_thread_message",
                ai_provider: null,
                ai_model: null,
                created_at: "2026-04-03T19:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
    });

    const { container } = renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["%PDF"], "Cv.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), { target: { value: "bu belgeyi incele" } });
    fireEvent.submit(screen.getByPlaceholderText(/Sorunuzu yazın/).closest("form") as HTMLFormElement);

    await waitFor(() => expect(screen.getAllByText("CV dosyasını inceledim.").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Cv.pdf" })).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Cv.pdf" }));

    await waitFor(() => expect(screen.getByRole("dialog", { name: "Cv.pdf" })).toBeInTheDocument());
    expect(screen.getByTitle("Cv.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kapat" })).toBeInTheDocument();
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

    await waitFor(() => expect(screen.getAllByText("Son mesaj").length).toBeGreaterThan(0));
    await waitFor(() => expect(scrollToMock).toHaveBeenCalled());
  });

  it("shows the setup shortcut instead of proactive actions while first-run setup is still pending", async () => {
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

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Kurulumu aç" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Taslak hazırla" })).not.toBeInTheDocument();
  });

  it("shows the session brief only once per app session", async () => {
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
        greeting_message: "Sami, takvimini ve açık işlerini taradım.",
        today_summary: "Selam Sami. Bugün 1 ajanda maddesi var.",
        counts: {
          agenda: 1,
          inbox: 0,
          calendar_today: 1,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [
          {
            id: 9,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Hazırım.",
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

    const firstRender = renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByText("Selam Sami").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Özet panelini kapat" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Özet panelini kapat" })).not.toBeInTheDocument());

    firstRender.unmount();

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByText("Hazırım.").length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: "Özet panelini kapat" })).not.toBeInTheDocument();
  });

  it("starts the onboarding interview directly in chat after provider connection", async () => {
    let agentRunCalls = 0;
    const fetchMock = installFetchMock({
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
        provider_type: "gemini",
        provider_model: "gemini-2.5-flash",
        provider_configured: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        greeting_title: "Selam",
        greeting_message: "Takvimini ve açık işlerini gözden geçirdim.",
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: {
          agenda: 0,
          inbox: 0,
          calendar_today: 0,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [],
        requires_setup: [
          {
            id: "setup-workspace",
            title: "Çalışma klasörünü seçin",
            details: "Masaüstü uygulaması yalnız seçilen klasör ve alt klasörlerinde çalışır.",
            action: "open_settings",
          },
        ],
        onboarding: {
          complete: false,
          blocked_by_setup: false,
          workspace_ready: false,
          provider_ready: true,
          model_ready: true,
          assistant_ready: false,
          user_ready: false,
          starter_prompts: ["Kısa bir tanışma yapalım."],
        },
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
        has_more: false,
        total_count: 0,
      },
      "POST /assistant/thread/messages/stream": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        expect(payload.content).toContain("Kısa bir tanışma yapalım.");
        const response = {
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          messages: [
            {
              id: 10,
              thread_id: 1,
              office_id: "default-office",
              role: "assistant",
              content: "Bunu kısa tutacağım. Önce çalışma tarzını netleştireceğim; ardından hangi hesapları ve servisleri bağlamak istediğini sohbetten birlikte kuracağız.\n\nİlk sorum: Sana nasıl hitap etmemi istersin?\nBunu şöyle kullanacağım: Bundan sonra konuşurken bu hitabı kullanacağım.\nNasıl cevap verebilirsin: Kısa bir cevap yeterli. İsmini ya da tercih ettiğin hitabı yazman yeterli.\n\nÖrnek yanıtlar:\n- Bana Ahmet diye hitap et.\n- Ahmet yeterli.\n- İsmimle seslen.",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {
                onboarding: {
                  current_question: {
                    id: "user-name",
                    field: "display_name",
                    target: "user",
                    question: "Sana nasıl hitap etmemi istersin?",
                    reason: "Bundan sonra konuşurken bu hitabı kullanacağım.",
                    quick_replies: ["Bana Ahmet diye hitap et.", "Ahmet yeterli."],
                  },
                },
              },
              requires_approval: false,
              generated_from: "assistant_onboarding_guide",
              created_at: "2026-03-15T10:00:00Z",
            },
          ],
          has_more: false,
          total_count: 1,
        };
        return ndjsonResponse([
          { type: "thread_ready", thread: response.thread, user_message: { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: payload.content, linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-15T09:59:59Z" } },
          { type: "assistant_start" },
          { type: "assistant_complete", response },
        ]);
      },
      "POST /agent/runs": () => {
        agentRunCalls += 1;
        return { detail: "unexpected-agent-run" };
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
        workspaceConfigured: false,
        workspaceRootName: "",
      },
    });

    await waitFor(() => expect(screen.getByText(/İlk sorum:/)).toBeInTheDocument());
    expect(screen.queryByText("Kullanılan araçlar")).not.toBeInTheDocument();
    expect(screen.queryByText("Tanışma röportajı")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
    expect(agentRunCalls).toBe(0);
  });

  it("does not auto-start the onboarding interview before provider setup is finished", async () => {
    let streamCalls = 0;
    let threadCalls = 0;
    const fetchMock = installFetchMock({
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
        provider_type: "",
        provider_model: "",
        provider_configured: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        greeting_title: "Selam",
        greeting_message: "Takvimini ve açık işlerini gözden geçirdim.",
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: {
          agenda: 0,
          inbox: 0,
          calendar_today: 0,
          drafts_pending: 0,
        },
        priority_items: [],
        proactive_suggestions: [],
        requires_setup: [
          {
            id: "setup-provider",
            title: "Asistan modelini bağlayın",
            details: "OpenAI, Gemini, Codex veya yerel Ollama ile başlayabilirsiniz.",
            action: "open_settings",
          },
        ],
        onboarding: {
          complete: false,
          blocked_by_setup: true,
          workspace_ready: false,
          provider_ready: false,
          model_ready: false,
          assistant_ready: false,
          user_ready: false,
          interview_intro: "İlk açılışta asistan seninle kısa bir tanışma yapar.",
          summary: "Önce kısa bir tanışma, sonra bağlamak istediğin ilk hesabı birlikte kuracağız.",
          starter_prompts: ["Kısa bir tanışma yapalım."],
        },
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [],
        selected_thread_id: 0,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": () => {
        threadCalls += 1;
        return {
        thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
        messages: [],
        has_more: false,
        total_count: 0,
        };
      },
      "POST /assistant/thread/messages/stream": () => {
        streamCalls += 1;
        return ndjsonResponse([]);
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
        workspaceConfigured: false,
        workspaceRootName: "",
      },
    });

    await waitFor(() => expect(screen.getByText("Önce modeli bağla")).toBeInTheDocument());
    expect(screen.queryByText("Çalışma klasörünü seçin")).not.toBeInTheDocument();
    expect(screen.queryByText("Asistan modelini bağlayın")).not.toBeInTheDocument();
    expect(screen.queryByText(/İlk sorum:/)).not.toBeInTheDocument();
    expect(threadCalls).toBe(0);
    expect(streamCalls).toBe(0);
    expect(fetchMock).toHaveBeenCalled();
  });

  it("renders assistant bullet lines as a proper list", async () => {
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
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Belgeleri özetledim:\n* İlk dosya kısa özet\n* İkinci dosya kısa özet",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:01:00Z",
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

    const { container } = renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Belgeleri özetledim:")).toBeInTheDocument());
    const listItems = container.querySelectorAll(".wa-bubble__list-item");
    expect(listItems).toHaveLength(2);
    expect(screen.queryByText("* İlk dosya kısa özet")).not.toBeInTheDocument();
  });

  it("shows a compact connected-resources card on the welcome screen when Google is connected", async () => {
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

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.getByText("Bağlı kaynaklar hazır")).toBeInTheDocument();
    expect(screen.getByText("Gmail, Takvim, Drive ve YouTube oynatma listesi verileri asistanın kullanımına açık. Sorularınızda bu kaynaklara da bakabilirim.")).toBeInTheDocument();
    expect(screen.queryByText("12 Gmail konuşması")).not.toBeInTheDocument();
    expect(screen.queryByText("20 Takvim kaydı")).not.toBeInTheDocument();
    expect(screen.queryByText("8 Drive dosyası")).not.toBeInTheDocument();
  });

  it("renders Google and Outlook calendar entries with separate source markers", async () => {
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
        outlook_configured: true,
        outlook_calendar_connected: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        today_summary: "Takvim kaynakları hazır.",
        counts: {
          agenda: 0,
          inbox: 0,
          calendar_today: 2,
          drafts_pending: 0,
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
        today: "2026-04-07",
        generated_from: "assistant_calendar_engine",
        google_connected: true,
        outlook_connected: true,
        items: [
          {
            id: "calendar-google-1",
            kind: "calendar_event",
            title: "Google duruşma planı",
            details: "Müvekkil görüşmesi",
            starts_at: "2026-04-07T09:00:00Z",
            ends_at: "2026-04-07T10:00:00Z",
            location: "Google Meet",
            source_type: "calendar_event",
            source_ref: "google-1",
            all_day: false,
            needs_preparation: true,
            provider: "google",
            attendees: [],
            metadata: {},
          },
          {
            id: "calendar-outlook-1",
            kind: "calendar_event",
            title: "Outlook ekip görüşmesi",
            details: "Haftalık durum",
            starts_at: "2026-04-07T11:00:00Z",
            ends_at: "2026-04-07T12:00:00Z",
            location: "Teams",
            source_type: "calendar_event",
            source_ref: "outlook-1",
            all_day: false,
            needs_preparation: false,
            provider: "outlook",
            attendees: [],
            metadata: {},
          },
        ],
      },
      "GET /integrations/google/status": {
        provider: "google",
        configured: true,
        enabled: true,
        account_label: "sami@gmail.com",
        scopes: ["https://www.googleapis.com/auth/calendar.events"],
        gmail_connected: true,
        calendar_connected: true,
        drive_connected: false,
        calendar_write_ready: true,
        status: "connected",
        desktop_managed: true,
      },
    });

    renderApp(["/assistant?tool=calendar"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: {
        getIntegrationConfig: async () => ({
          google: {
            enabled: true,
            oauthConnected: true,
            accountLabel: "sami@gmail.com",
            scopes: ["https://www.googleapis.com/auth/calendar.events"],
          },
          outlook: {
            enabled: true,
            oauthConnected: true,
            accountLabel: "sami@outlook.com",
            scopes: ["Calendars.Read"],
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByText("Google planlaması hazır")).toBeInTheDocument());
    expect(screen.getByText("Outlook takvimi bağlı")).toBeInTheDocument();
    expect(screen.getAllByText("sami@gmail.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sami@outlook.com").length).toBeGreaterThan(0);
    expect(screen.getByText("Google duruşma planı")).toBeInTheDocument();
    expect(screen.getByText("Outlook ekip görüşmesi")).toBeInTheDocument();
    expect(document.querySelector('.calendar-tool__mini-item[data-provider="google"]')).toBeTruthy();
    expect(document.querySelector('.calendar-tool__mini-item[data-provider="outlook"]')).toBeTruthy();
    expect(document.querySelector('.calendar-tool__source-badge[data-provider="google"]')).toBeTruthy();
    expect(document.querySelector('.calendar-tool__source-badge[data-provider="outlook"]')).toBeTruthy();
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
      "POST /assistant/thread/messages/stream": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        expect(payload.content).toContain("iletişimleri özetle");
        const response = {
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
        return ndjsonResponse([
          { type: "thread_ready", thread: response.thread, user_message: { id: 10, thread_id: 1, office_id: "default-office", role: "user", content: payload.content, linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T10:00:30Z" } },
          { type: "assistant_start" },
          { type: "assistant_complete", response },
        ]);
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
    expect(document.querySelector('.calendar-tool__source-badge[data-provider="google"]')).toBeTruthy();
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

    await waitFor(() => expect(screen.getAllByText("Taslakları önce burada takip edebiliriz.").length).toBeGreaterThan(0));
    expect(screen.queryByText("Önerilen yönlendirmeler")).not.toBeInTheDocument();
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
    const voiceLaunch = screen.getAllByLabelText("Sesli görüşmeyi başlat")[0];
    expect(voiceLaunch).toHaveAttribute("title", "Sesli konuş");
    expect(voiceLaunch.querySelector("span")).toBeNull();
    fireEvent.click(voiceLaunch);

    expect(screen.getByRole("button", { name: "Bitir" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Sizi dinliyorum...")).toBeInTheDocument();
    expect(screen.getByLabelText("Ses seçeneklerini aç")).toBeInTheDocument();
  });

  it("shows the live voice transcript inside the composer while listening", async () => {
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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Dosyayı özetle",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Dosyayı özetledim.", content: "Dosyayı özetledim." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "Dosyayı özetle",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:00Z",
              },
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Dosyayı özetledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

    const recognition = MockSpeechRecognition.instances.at(-1);
    expect(recognition).toBeTruthy();
    recognition?.emitResult("Dosyayı özetle");

    await waitFor(() => {
      expect(screen.getByDisplayValue("Dosyayı özetle")).toBeInTheDocument();
    });
  });

  it("auto-submits a voice transcript after a short silence without pressing the mic again", async () => {
    const originalMediaRecorder = globalThis.MediaRecorder;
    const originalMediaDevices = globalThis.navigator.mediaDevices;
    Object.defineProperty(globalThis, "MediaRecorder", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    Object.defineProperty(globalThis.navigator, "mediaDevices", {
      configurable: true,
      writable: true,
      value: undefined,
    });

    try {
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
        "POST /assistant/thread/messages/stream": ndjsonResponse([
          {
            type: "thread_ready",
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            user_message: {
              id: 2,
              thread_id: 1,
              office_id: "default-office",
              role: "user",
              content: "Bugünü özetle",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {},
              requires_approval: false,
              created_at: "2026-03-14T10:00:00Z",
            },
          },
          { type: "assistant_start" },
          { type: "assistant_chunk", delta: "Bugünü özetledim.", content: "Bugünü özetledim." },
          {
            type: "assistant_complete",
            response: {
              thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
              messages: [
                {
                  id: 2,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "user",
                  content: "Bugünü özetle",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:00Z",
                },
                {
                  id: 3,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "assistant",
                  content: "Bugünü özetledim.",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:05Z",
                },
              ],
              has_more: false,
              total_count: 2,
            },
          },
        ]),
      });

      renderApp(["/assistant"], {
        storedSettings: {
          workspaceConfigured: true,
          workspaceRootName: "Belge Havuzu",
        },
      });

      await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
      fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

      const recognition = MockSpeechRecognition.instances.at(-1);
      expect(recognition).toBeTruthy();
      recognition?.emitResult("Bugünü özetle");

      await new Promise((resolve) => setTimeout(resolve, 2200));

      await waitFor(() => expect(screen.getByText("Bugünü özetledim.")).toBeInTheDocument());
      expect(speechSynthesisMock.speak).toHaveBeenCalled();
    } finally {
      Object.defineProperty(globalThis, "MediaRecorder", {
        configurable: true,
        writable: true,
        value: originalMediaRecorder,
      });
      Object.defineProperty(globalThis.navigator, "mediaDevices", {
        configurable: true,
        writable: true,
        value: originalMediaDevices,
      });
    }
  });

  it("routes recorded microphone audio through the active model before submitting in voice mode", async () => {
    const originalMediaRecorder = globalThis.MediaRecorder;
    const originalMediaDevices = globalThis.navigator.mediaDevices;
    const stopTrack = vi.fn();
    const mockStream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream;

    Object.defineProperty(globalThis, "MediaRecorder", {
      configurable: true,
      writable: true,
      value: MockMediaRecorder,
    });
    Object.defineProperty(globalThis.navigator, "mediaDevices", {
      configurable: true,
      writable: true,
      value: {
        getUserMedia: vi.fn(() => Promise.resolve(mockStream)),
      },
    });

    try {
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
        "POST /assistant/attachments/analyze": {
          source_ref: {
            type: "audio_attachment",
            label: "ses-kaydi.webm",
            content_type: "audio/webm",
            size_bytes: 128,
            uploaded: false,
            attachment_context: "Bugün ne var?",
            analysis_available: true,
            analysis_mode: "direct-provider-audio",
          },
          analysis_text: "Bugün ne var?",
          ai_provider: "gemini",
          ai_model: "gemini-3.1",
          generated_from: "direct-provider-audio",
        },
        "POST /assistant/thread/messages/stream": ndjsonResponse([
          {
            type: "thread_ready",
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            user_message: {
              id: 2,
              thread_id: 1,
              office_id: "default-office",
              role: "user",
              content: "Bugün ne var?",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {},
              requires_approval: false,
              created_at: "2026-03-14T10:00:00Z",
            },
          },
          { type: "assistant_start" },
          { type: "assistant_chunk", delta: "Bugün sakin.", content: "Bugün sakin." },
          {
            type: "assistant_complete",
            response: {
              thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
              messages: [
                {
                  id: 2,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "user",
                  content: "Bugün ne var?",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:00Z",
                },
                {
                  id: 3,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "assistant",
                  content: "Bugün sakin.",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:05Z",
                },
              ],
              has_more: false,
              total_count: 2,
            },
          },
        ]),
      });

      renderApp(["/assistant"], {
        storedSettings: {
          workspaceConfigured: true,
          workspaceRootName: "Belge Havuzu",
        },
      });

      await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
      fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

      await waitFor(() => expect(screen.getByRole("button", { name: "Bitir" })).toBeInTheDocument());
      await waitFor(() => expect(screen.getByText("Sizi dinliyorum...")).toBeInTheDocument());

      const recorder = MockMediaRecorder.instances.at(-1);
      expect(recorder).toBeTruthy();
      fireEvent.click(screen.getAllByLabelText("Dinlemeyi durdur").at(-1) as HTMLElement);

      await waitFor(() => expect(screen.getByText("Bugün sakin.")).toBeInTheDocument());
      expect(stopTrack).toHaveBeenCalled();
    } finally {
      Object.defineProperty(globalThis, "MediaRecorder", {
        configurable: true,
        writable: true,
        value: originalMediaRecorder,
      });
      Object.defineProperty(globalThis.navigator, "mediaDevices", {
        configurable: true,
        writable: true,
        value: originalMediaDevices,
      });
    }
  });

  it("lets the user choose an assistant voice before speaking", async () => {
    mockSpeechVoices = [
      { voiceURI: "tr-ada", name: "Ada", lang: "tr-TR", localService: true, default: true } as SpeechSynthesisVoice,
      { voiceURI: "tr-ece", name: "Ece", lang: "tr-TR", localService: true, default: false } as SpeechSynthesisVoice,
    ];

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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Bugünü özetle",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Bugünün özetini hazırladım.", content: "Bugünün özetini hazırladım." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "Bugünü özetle",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:00Z",
              },
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Bugünün özetini hazırladım.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

    fireEvent.click(screen.getByLabelText("Ses seçeneklerini aç"));
    await waitFor(() => expect(screen.getByRole("option", { name: "Ece (tr-TR)" })).toBeInTheDocument());
    const voiceSelect = screen.getByRole("combobox", { name: "Asistan sesi" });
    fireEvent.change(voiceSelect, { target: { value: "tr-ece" } });
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Asistan sesi" }) as HTMLSelectElement).value).toBe("tr-ece"));

    const recognition = MockSpeechRecognition.instances.at(-1);
    expect(recognition).toBeTruthy();
    recognition?.emitResult("Bugünü özetle");
    recognition?.stop();

    await waitFor(() => expect(speechSynthesisMock.speak).toHaveBeenCalled());
    const utterance = speechSynthesisMock.speak.mock.calls.at(-1)?.[0] as MockSpeechSynthesisUtterance | undefined;
    expect(utterance?.voice?.voiceURI).toBe("tr-ece");
  });

  it("prefers browser speech voices over desktop fallback when both are available", async () => {
    mockSpeechVoices = [
      { voiceURI: "tr-natural", name: "Natural Turkish", lang: "tr-TR", localService: true, default: true } as SpeechSynthesisVoice,
    ];
    const desktopSpeakTextMock = vi.fn(() => Promise.resolve({ ok: true }));

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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Bugünü özetle",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-14T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Bugünün özetini hazırladım.", content: "Bugünün özetini hazırladım." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "Bugünü özetle",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:00Z",
              },
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Bugünün özetini hazırladım.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-14T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
    });

    renderApp(["/assistant"], {
      desktop: {
        getDesktopTtsVoices: () => Promise.resolve([{ id: "desktop:Turkish", name: "Turkish", lang: "tr" }]),
        speakText: desktopSpeakTextMock,
        stopSpeaking: () => Promise.resolve({ ok: true }),
      },
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

    const recognition = MockSpeechRecognition.instances.at(-1);
    expect(recognition).toBeTruthy();
    recognition?.emitResult("Bugünü özetle");
    recognition?.stop();

    await waitFor(() => expect(speechSynthesisMock.speak).toHaveBeenCalled());
    expect(desktopSpeakTextMock).not.toHaveBeenCalled();
  });

  it("uses desktop TTS fallback in voice mode when desktop speech is available", async () => {
    const originalSpeechSynthesis = window.speechSynthesis;
    const desktopSpeakTextMock = vi.fn(() => Promise.resolve({ ok: true }));
    const desktopStopSpeakingMock = vi.fn(() => Promise.resolve({ ok: true }));
    try {
      Object.defineProperty(window, "speechSynthesis", {
        configurable: true,
        writable: true,
        value: undefined,
      });

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
        "POST /assistant/thread/messages/stream": ndjsonResponse([
          {
            type: "thread_ready",
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            user_message: {
              id: 2,
              thread_id: 1,
              office_id: "default-office",
              role: "user",
              content: "Bugünü özetle",
              linked_entities: [],
              tool_suggestions: [],
              draft_preview: null,
              source_context: {},
              requires_approval: false,
              created_at: "2026-03-14T10:00:00Z",
            },
          },
          { type: "assistant_start" },
          { type: "assistant_chunk", delta: "Bugünün özetini hazırladım.", content: "Bugünün özetini hazırladım." },
          {
            type: "assistant_complete",
            response: {
              thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
              messages: [
                {
                  id: 2,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "user",
                  content: "Bugünü özetle",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:00Z",
                },
                {
                  id: 3,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "assistant",
                  content: "Bugünün özetini hazırladım.",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-14T10:00:05Z",
                },
              ],
              has_more: false,
              total_count: 2,
            },
          },
        ]),
      });

      renderApp(["/assistant"], {
        desktop: {
          getDesktopTtsVoices: () => Promise.resolve([{ id: "desktop:Turkish", name: "Turkish", lang: "tr" }]),
          speakText: desktopSpeakTextMock,
          stopSpeaking: desktopStopSpeakingMock,
        },
        storedSettings: {
          workspaceConfigured: true,
          workspaceRootName: "Belge Havuzu",
        },
      });

      await waitFor(() => expect(screen.getAllByLabelText("Sesli görüşmeyi başlat").length).toBeGreaterThan(0));
      fireEvent.click(screen.getAllByLabelText("Sesli görüşmeyi başlat")[0]);

      const recognition = MockSpeechRecognition.instances.at(-1);
      expect(recognition).toBeTruthy();
      recognition?.emitResult("Bugünü özetle");
      recognition?.stop();

      await waitFor(() => expect(desktopSpeakTextMock).toHaveBeenCalled());
      const desktopSpeechCalls = desktopSpeakTextMock.mock.calls as unknown as Array<[Record<string, unknown>]>;
      expect(desktopSpeechCalls.at(-1)?.[0]).toMatchObject({
        text: "Bugünün özetini hazırladım.",
      });
    } finally {
      Object.defineProperty(window, "speechSynthesis", {
        configurable: true,
        writable: true,
        value: originalSpeechSynthesis,
      });
    }
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

    await waitFor(() => expect(screen.getAllByLabelText("Çalışma panelini tam ekrana al").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText("Çalışma panelini tam ekrana al")[0]);

    await waitFor(() => expect(screen.getByLabelText("Çalışma panelini normal boyuta döndür")).toBeInTheDocument());
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
      "GET /assistant/approvals": {
        items: [
          {
            id: "assistant-action-55",
            action_id: 55,
            draft_id: 88,
            status: "pending_review",
            title: "İstanbul Ankara tren bileti",
            action_type: "reserve_travel",
            target_channel: "travel",
            manual_review_required: true,
            approval_required: true,
          },
        ],
        generated_from: "approval_registry",
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

  it("hides chat approval cards when the related approval is no longer active", async () => {
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
            id: 9,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Taslak daha önce oluşturulmuştu.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: {
              id: 41,
              channel: "whatsapp",
              subject: "Tamam için mesaj",
              body: "Tamam, 12'de arayacağım.",
              approval_status: "approved",
              delivery_status: "sent",
              dispatch_state: "completed",
              created_at: "2026-03-15T10:00:00Z",
              updated_at: "2026-03-15T10:02:00Z",
            },
            source_context: {
              approval_requests: [
                {
                  id: "assistant-action-41",
                  action_id: 41,
                  draft_id: 41,
                  tool: "whatsapp",
                  title: "Tamam için mesaj",
                  reason: "Onay verirsen gönderirim.",
                  status: "pending_review",
                },
              ],
            },
            requires_approval: true,
            created_at: "2026-03-15T10:00:00Z",
          },
        ],
        has_more: false,
        total_count: 1,
      },
      "GET /assistant/approvals": {
        items: [],
        generated_from: "approval_registry",
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
      "GET /assistant/calendar": {
        today: "2026-03-15",
        generated_from: "assistant_calendar_engine",
        google_connected: false,
        items: [],
      },
      "GET /assistant/drafts": {
        items: [],
        matter_drafts: [],
        generated_from: "assistant_agenda_engine",
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

    await waitFor(() => expect(screen.getAllByText("Taslak daha önce oluşturulmuştu.").length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: "Onayla ve gönder" })).not.toBeInTheDocument();
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

  it("removes external drafts from the drafts tool", async () => {
    let draftState = {
      id: 14,
      office_id: "default-office",
      matter_id: null,
      draft_type: "send_email",
      channel: "email",
      to_contact: "samiyusuf178@gmail.com",
      subject: "Kısa mesaj",
      body: "Sayın Sami,\n\nMerhaba.",
      source_context: {},
      generated_from: "assistant_actions",
      ai_model: null,
      ai_provider: null,
      approval_status: "pending_review",
      delivery_status: "not_sent",
      created_by: "intern",
      approved_by: null,
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
        items: draftState && draftState.delivery_status !== "cancelled" ? [draftState] : [],
        matter_drafts: [],
        generated_from: "assistant_agenda_engine",
      }),
      "POST /assistant/drafts/14/remove": () => {
        draftState = {
          ...draftState,
          approval_status: "dismissed",
          delivery_status: "cancelled",
          dispatch_state: "idle",
          updated_at: "2026-03-15T09:01:00Z",
        };
        return {
          draft: draftState,
          action: null,
          message: "Taslak kaldırıldı.",
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
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Kaldır" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Kaldır" }));
    await waitFor(() => expect(screen.queryByText("Kısa mesaj")).not.toBeInTheDocument());
  });

  it("shows pause and resume controls for linked action cases in the drafts tool", async () => {
    let draftState = {
      id: 14,
      office_id: "default-office",
      matter_id: null,
      draft_type: "send_email",
      channel: "email",
      to_contact: "musteri@example.com",
      subject: "Durum özeti",
      body: "Sayın müvekkil, kısa durumu iletiyorum.",
      source_context: {},
      generated_from: "assistant_actions",
      ai_model: null,
      ai_provider: null,
      approval_status: "approved",
      delivery_status: "ready_to_send",
      created_by: "intern",
      approved_by: "lawyer",
      dispatch_state: "ready",
      created_at: "2026-03-15T09:00:00Z",
      updated_at: "2026-03-15T09:00:00Z",
      action_id: 91,
      action_case: {
        id: 301,
        case_type: "assistant_action",
        title: "Durum özetini gönder",
        status: "approved",
        current_step: "dispatch_ready",
        action_id: 91,
        draft_id: 14,
        created_at: "2026-03-15T09:00:00Z",
        updated_at: "2026-03-15T09:00:00Z",
      },
      dispatch_attempts: [],
      case_steps: [
        { step_key: "draft", title: "Taslak", status: "done", detail: "Taslak hazır." },
        { step_key: "approval", title: "Onay", status: "done", detail: "Onay tamamlandı." },
        { step_key: "dispatch", title: "Gönderim", status: "active", detail: "Gönderim için hazırlık yapılıyor." },
        { step_key: "confirmation", title: "Dış onay", status: "pending", detail: "Dış sistemden onay bekleniyor." },
        { step_key: "completion", title: "Sonuç", status: "pending", detail: "Henüz sonuca ulaşılmadı." },
      ],
      available_controls: {
        can_pause: true,
        can_resume: false,
        can_retry_dispatch: false,
        can_schedule_compensation: false,
      },
      linked_action: {
        id: 91,
        action_type: "prepare_client_update",
        title: "Durum özetini gönder",
        status: "approved",
        dispatch_state: "ready",
        manual_review_required: true,
        source_refs: [],
        created_at: "2026-03-15T09:00:00Z",
        updated_at: "2026-03-15T09:00:00Z",
        action_case: {
          id: 301,
          case_type: "assistant_action",
          title: "Durum özetini gönder",
          status: "approved",
          current_step: "dispatch_ready",
          action_id: 91,
          draft_id: 14,
          created_at: "2026-03-15T09:00:00Z",
          updated_at: "2026-03-15T09:00:00Z",
        },
        dispatch_attempts: [],
        case_steps: [
          { step_key: "draft", title: "Taslak", status: "done", detail: "Taslak hazır." },
          { step_key: "approval", title: "Onay", status: "done", detail: "Onay tamamlandı." },
          { step_key: "dispatch", title: "Gönderim", status: "active", detail: "Gönderim için hazırlık yapılıyor." },
          { step_key: "confirmation", title: "Dış onay", status: "pending", detail: "Dış sistemden onay bekleniyor." },
          { step_key: "completion", title: "Sonuç", status: "pending", detail: "Henüz sonuca ulaşılmadı." },
        ],
        available_controls: {
          can_pause: true,
          can_resume: false,
          can_retry_dispatch: false,
          can_schedule_compensation: false,
        },
      },
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
      "POST /assistant/actions/91/pause": () => {
        draftState = {
          ...draftState,
          dispatch_state: "paused",
          action_case: {
            ...draftState.action_case,
            status: "paused",
            current_step: "paused",
          },
          available_controls: {
            can_pause: false,
            can_resume: true,
            can_retry_dispatch: false,
            can_schedule_compensation: false,
          },
          linked_action: {
            ...draftState.linked_action,
            dispatch_state: "paused",
            action_case: {
              ...draftState.linked_action.action_case,
              status: "paused",
              current_step: "paused",
            },
            available_controls: {
              can_pause: false,
              can_resume: true,
              can_retry_dispatch: false,
              can_schedule_compensation: false,
            },
          },
        };
        return {
          action: draftState.linked_action,
          draft: draftState,
          action_case: draftState.action_case,
          message: "Aksiyon duraklatıldı.",
        };
      },
      "POST /assistant/actions/91/resume": () => {
        draftState = {
          ...draftState,
          dispatch_state: "ready",
          action_case: {
            ...draftState.action_case,
            status: "approved",
            current_step: "dispatch_ready",
          },
          available_controls: {
            can_pause: true,
            can_resume: false,
            can_retry_dispatch: false,
            can_schedule_compensation: false,
          },
          linked_action: {
            ...draftState.linked_action,
            dispatch_state: "ready",
            action_case: {
              ...draftState.linked_action.action_case,
              status: "approved",
              current_step: "dispatch_ready",
            },
            available_controls: {
              can_pause: true,
              can_resume: false,
              can_retry_dispatch: false,
              can_schedule_compensation: false,
            },
          },
        };
        return {
          action: draftState.linked_action,
          draft: draftState,
          action_case: draftState.action_case,
          message: "Aksiyon yeniden başlatıldı.",
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
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Duraklat" })).toBeInTheDocument());
    expect(screen.getByText("Gönderim")).toBeInTheDocument();
    expect(screen.getByText("Dış onay")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Duraklat" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Devam ettir" })).toBeInTheDocument());
    expect(screen.getAllByText(/Duraklatıldı/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Devam ettir" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Duraklat" })).toBeInTheDocument());
    expect(screen.getAllByText(/Hazır/i).length).toBeGreaterThan(0);
  });

  it("filters external drafts by channel in the drafts tool", async () => {
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
          drafts_pending: 2,
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
        items: [
          {
            id: 21,
            draft_type: "send_email",
            channel: "email",
            to_contact: "samiyusuf178@gmail.com",
            subject: "E-posta taslağı",
            body: "Merhaba, e-posta taslağı burada.",
            approval_status: "pending_review",
            delivery_status: "not_sent",
            dispatch_state: "idle",
            created_at: "2026-03-15T09:00:00Z",
            updated_at: "2026-03-15T09:00:00Z",
          },
          {
            id: 22,
            draft_type: "send_whatsapp_message",
            channel: "whatsapp",
            to_contact: "905551112233",
            subject: "WhatsApp taslağı",
            body: "Merhaba, WhatsApp taslağı burada.",
            approval_status: "pending_review",
            delivery_status: "not_sent",
            dispatch_state: "idle",
            created_at: "2026-03-15T10:00:00Z",
            updated_at: "2026-03-15T10:00:00Z",
          },
        ],
        matter_drafts: [],
        generated_from: "assistant_agenda_engine",
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
    });

    await waitFor(() => expect(screen.getByText("WhatsApp (1)")).toBeInTheDocument());
    expect(screen.getByText("WhatsApp taslağı")).toBeInTheDocument();
    expect(screen.getByText("E-posta taslağı")).toBeInTheDocument();

    fireEvent.click(screen.getByText("WhatsApp (1)"));

    await waitFor(() => expect(screen.getByText("WhatsApp taslağı")).toBeInTheDocument());
    expect(screen.queryByText("E-posta taslağı")).not.toBeInTheDocument();
  });

  it("writes assistant-managed automation rules into desktop automation config", async () => {
    const getStoredConfig = vi.fn(async () => ({
      automation: {
        enabled: true,
        autoSyncConnectedServices: true,
        automationRules: [
          {
            id: "rule-ceo",
            summary: "E-posta tarafında CEO iletilerini bana bildir.",
            instruction: "CEO iletilerini takip et.",
            mode: "notify",
            channels: ["email"],
            targets: ["CEO"],
            match_terms: [],
            reply_text: "",
            active: true,
          },
        ],
        desktopNotifications: false,
      },
    }));
    const saveStoredConfig = vi.fn(async (patch: Record<string, unknown>) => patch);

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
        today: "2026-03-15",
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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Ahmet Yılmaz'dan gelen mailler önemli. Otomatik cevaplama, bana WhatsApp'tan haber ver.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-15T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Kuralları güncelledim.", content: "Kuralları güncelledim." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "Ahmet Yılmaz'dan gelen mailler önemli. Otomatik cevaplama, bana WhatsApp'tan haber ver.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-15T10:00:00Z",
              },
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Kuralları güncelledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  automation_updates: [
                    {
                      summary: "Otomasyon kuralı kaydedildi.",
                      operations: [
                        { op: "set", path: "desktopNotifications", value: true },
                        {
                          op: "add_rule",
                          rule: {
                            summary: "E-posta / WhatsApp'ta Ahmet Yılmaz kaynaklı iletileri bana bildir.",
                            instruction: "Ahmet Yılmaz'dan gelen mailler çok önemli. Otomatik cevaplama, bana WhatsApp'tan haber ver.",
                            mode: "notify",
                            channels: ["email", "whatsapp"],
                            targets: ["Ahmet Yılmaz"],
                            match_terms: [],
                            reply_text: "",
                            active: true,
                          },
                        },
                      ],
                    },
                  ],
                },
                requires_approval: false,
                created_at: "2026-03-15T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
            automation_updates: [
              {
                summary: "Otomasyon kuralı kaydedildi.",
                operations: [
                  { op: "set", path: "desktopNotifications", value: true },
                  {
                    op: "add_rule",
                    rule: {
                      summary: "E-posta / WhatsApp'ta Ahmet Yılmaz kaynaklı iletileri bana bildir.",
                      instruction: "Ahmet Yılmaz'dan gelen mailler çok önemli. Otomatik cevaplama, bana WhatsApp'tan haber ver.",
                      mode: "notify",
                      channels: ["email", "whatsapp"],
                      targets: ["Ahmet Yılmaz"],
                      match_terms: [],
                      reply_text: "",
                      active: true,
                    },
                  },
                ],
              },
            ],
          },
        },
      ]),
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: {
        getStoredConfig,
        saveStoredConfig,
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Ahmet Yılmaz'dan gelen mailler önemli. Otomatik cevaplama, bana WhatsApp'tan haber ver." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() =>
      expect(saveStoredConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          automation: expect.objectContaining({
            desktopNotifications: true,
            automationRules: expect.arrayContaining([
              expect.objectContaining({
                summary: "E-posta tarafında CEO iletilerini bana bildir.",
                mode: "notify",
              }),
              expect.objectContaining({
                summary: "E-posta / WhatsApp'ta Ahmet Yılmaz kaynaklı iletileri bana bildir.",
                mode: "notify",
                channels: ["email", "whatsapp"],
                targets: ["Ahmet Yılmaz"],
                thread_id: 1,
              }),
            ]),
          }),
        }),
      ),
    );
    await waitFor(() => expect(screen.getByText("Bellek güncellemesi")).toBeInTheDocument());
    const settingsLinks = screen.getAllByRole("link", { name: "Ayarları aç" });
    expect(settingsLinks).toHaveLength(1);
    expect(settingsLinks.some((item) => item.getAttribute("href") === "/settings?tab=automation&section=automation-panel")).toBe(true);
    expect(screen.queryByRole("link", { name: "Ayarı aç" })).not.toBeInTheDocument();
  });

  it("replaces an existing reminder rule when the same reminder gets a newer time", async () => {
    const saveStoredConfig = vi.fn(async (patch: Record<string, unknown>) => patch);

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
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-03-15", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 3,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "12 48 de bana su içmeyi hatırlat",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-15T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "Hatırlatmayı güncelledim.", content: "Hatırlatmayı güncelledim." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "12 48 de bana su içmeyi hatırlat",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-15T10:00:00Z",
              },
              {
                id: 4,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "Hatırlatmayı güncelledim.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {
                  automation_updates: [
                    {
                      summary: "Su iç hatırlatmasını kurdum.",
                      operations: [
                        { op: "set", path: "desktopNotifications", value: true },
                        {
                          op: "add_rule",
                          rule: {
                            summary: "Su iç",
                            instruction: "12 48 de bana su içmeyi hatırlat",
                            mode: "reminder",
                            channels: ["generic"],
                            targets: [],
                            match_terms: [],
                            reply_text: "Su iç",
                            reminder_at: "2026-04-17T12:48:00+03:00",
                            active: true,
                          },
                        },
                      ],
                    },
                  ],
                },
                requires_approval: false,
                created_at: "2026-03-15T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
            automation_updates: [
              {
                summary: "Su iç hatırlatmasını kurdum.",
                operations: [
                  { op: "set", path: "desktopNotifications", value: true },
                  {
                    op: "add_rule",
                    rule: {
                      summary: "Su iç",
                      instruction: "12 48 de bana su içmeyi hatırlat",
                      mode: "reminder",
                      channels: ["generic"],
                      targets: [],
                      match_terms: [],
                      reply_text: "Su iç",
                      reminder_at: "2026-04-17T12:48:00+03:00",
                      active: true,
                    },
                  },
                ],
              },
            ],
          },
        },
      ]),
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
      desktop: {
        getStoredConfig: vi.fn(async () => ({
          automation: {
            enabled: true,
            autoSyncConnectedServices: true,
            desktopNotifications: false,
            automationRules: [
              {
                id: "rule-water-old",
                summary: "Su iç",
                instruction: "12 47 de bana su içmeyi hatırlat",
                mode: "reminder",
                channels: ["generic"],
                targets: [],
                match_terms: [],
                reply_text: "Su iç",
                reminder_at: "2026-04-17T12:47:00+03:00",
                active: true,
              },
            ],
          },
        })),
        saveStoredConfig,
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "12 48 de bana su içmeyi hatırlat" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(saveStoredConfig).toHaveBeenCalled());
    const savedAutomation = (saveStoredConfig.mock.calls.at(-1)?.[0] as Record<string, any>).automation;
    const reminderRules = (savedAutomation.automationRules as Array<Record<string, any>>).filter((rule) => rule.mode === "reminder");
    expect(reminderRules).toHaveLength(1);
    expect(reminderRules[0]).toEqual(expect.objectContaining({
      summary: "Su iç",
      reminder_at: "2026-04-17T12:48:00+03:00",
      thread_id: 1,
    }));
  });

  it("keeps agent run tracking in the background without opening the panel inline", async () => {
    let agentRunReads = 0;

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
        today: "2026-03-15",
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
      "POST /assistant/thread/messages/stream": ndjsonResponse([
        {
          type: "thread_ready",
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          user_message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "user",
            content: "Web sitesini incele ve özet çıkar.",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            created_at: "2026-03-15T10:00:00Z",
          },
        },
        { type: "assistant_start" },
        { type: "assistant_chunk", delta: "İlk sonuçları çıkardım.", content: "İlk sonuçları çıkardım." },
        {
          type: "assistant_complete",
          response: {
            thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
            messages: [
              {
                id: 2,
                thread_id: 1,
                office_id: "default-office",
                role: "user",
                content: "Web sitesini incele ve özet çıkar.",
                linked_entities: [],
                tool_suggestions: [],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-15T10:00:00Z",
              },
              {
                id: 3,
                thread_id: 1,
                office_id: "default-office",
                role: "assistant",
                content: "İlk sonuçları çıkardım.",
                linked_entities: [],
                tool_suggestions: [
                  {
                    tool: "documents",
                    label: "Belgeler",
                    reason: "İncelenen kaynakları burada görebilirsin.",
                  },
                ],
                draft_preview: null,
                source_context: {},
                requires_approval: false,
                created_at: "2026-03-15T10:00:05Z",
              },
            ],
            has_more: false,
            total_count: 2,
          },
        },
      ]),
      "POST /agent/runs": {
        id: 77,
        title: "Web sitesini incele ve özet çıkar.",
        goal: "Web sitesini incele ve özet çıkar.",
        status: "running",
        summary: "Web ve belge kaynaklarını toplayıp denetliyorum.",
        created_at: "2026-03-15T10:00:00Z",
        updated_at: "2026-03-15T10:00:01Z",
      },
      "GET /tools": {
        items: [
          { name: "web-search", label: "Web arama" },
          { name: "website-inspect", label: "Site inceleme" },
        ],
      },
      "GET /agent/runs/77": () => {
        agentRunReads += 1;
        return {
          id: 77,
          title: "Web sitesini incele ve özet çıkar.",
          goal: "Web sitesini incele ve özet çıkar.",
          status: agentRunReads >= 2 ? "completed" : "running",
          summary: "Web ve belge kaynaklarını toplayıp denetliyorum.",
          citations: [
            {
              document_id: 15,
              document_name: "Site Özeti",
              matter_id: 2,
              chunk_id: 4,
              chunk_index: 1,
              excerpt: "Hizmet sayfası ve iletişim bilgileri çıkarıldı.",
              relevance_score: 0.88,
              source_type: "website",
              support_type: "document_backed",
              confidence: "high",
            },
          ],
          artifacts: [
            {
              id: "artifact-1",
              kind: "screenshot",
              label: "Ana sayfa ekran görüntüsü",
              text_excerpt: "Sayfa DOM özeti ve başlık bilgileri kaydedildi.",
            },
          ],
          tool_invocations: [
            { id: "tool-1", tool_name: "web-search", status: "completed" },
            { id: "tool-2", tool_name: "website-inspect", status: "completed" },
          ],
          approval_requests: [
            { id: "approval-1", title: "Tarayıcı aksiyonu gerekirse onay iste", status: "pending_review" },
          ],
          updated_at: "2026-03-15T10:00:03Z",
        };
      },
      "GET /agent/runs/77/events": {
        items: [
          {
            id: "event-1",
            type: "tool_completed",
            summary: "Site inceleme adımı tamamlandı.",
          },
        ],
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Web sitesini incele ve özet çıkar." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(screen.getByText("İlk sonuçları çıkardım.")).toBeInTheDocument());
    expect(screen.queryByText("Kullanılan araçlar")).not.toBeInTheDocument();
    expect(screen.queryByText("Kanıt ve çıktılar")).not.toBeInTheDocument();
    expect(screen.queryByText("Onay özeti")).not.toBeInTheDocument();
    expect(screen.queryByText("Bugün için ajanda boş")).not.toBeInTheDocument();
  });

  it("can cancel a pending streamed assistant reply", async () => {
    const routeFetch = installFetchMock({
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
        today_summary: "Hazırım.",
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
        today: "2026-03-15",
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
      "GET /agent/tools": {
        items: [],
      },
    });

    const abortAwareFetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input.toString());
      if (url.pathname === "/assistant/thread/messages/stream") {
        return new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          if (signal?.aborted) {
            reject(new DOMException("İstek iptal edildi.", "AbortError"));
            return;
          }
          signal?.addEventListener("abort", () => reject(new DOMException("İstek iptal edildi.", "AbortError")), { once: true });
        });
      }
      return routeFetch(input, init);
    });
    vi.stubGlobal("fetch", abortAwareFetch);

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Yanıtı iptal et" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "İptal et" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yanıtı iptal et" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Yanıtı iptal et" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Gönder" })).toBeInTheDocument();
  });

  it("shows typing dots until the first chunk and renders assistant output incrementally", async () => {
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
        today_summary: "Hazırım.",
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
        today: "2026-03-15",
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
      "GET /agent/tools": {
        items: [],
      },
      "POST /assistant/thread/messages/stream": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        const response = {
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
        return delayedNdjsonResponse([
          { type: "thread_ready", thread: response.thread, user_message: { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: payload.content, linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T09:59:59Z" } },
          { type: "assistant_start" },
          { type: "assistant_chunk", delta: "Taslak hazır.", content: "Taslak hazır." },
          { type: "assistant_chunk", delta: " Göndermeden önce inceleyebilirsin.", content: "Taslak hazır. Göndermeden önce inceleyebilirsin." },
          { type: "assistant_complete", response },
        ]);
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(document.querySelectorAll(".wa-typing__dot").length).toBe(3));
    expect(screen.queryByRole("button", { name: "İptal et" })).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Taslak hazır.")).toBeInTheDocument());
    expect(screen.queryByText("Taslak hazır. Göndermeden önce inceleyebilirsin.")).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Taslak hazır. Göndermeden önce inceleyebilirsin.")).toBeInTheDocument());
  });

  it("clears typing indicators as soon as the assistant message completes", async () => {
    const homePayload = {
      today_summary: "Hazırım.",
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
    };
    let homeCalls = 0;
    let resolveHomeRefresh = () => {};
    const pendingHomeRefresh = new Promise<void>((resolve) => {
      resolveHomeRefresh = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input.toString());
      const method = (init?.method || "GET").toUpperCase();
      const key = `${method} ${url.pathname}`;
      if (key === "GET /health") {
        return new Response(JSON.stringify({
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
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/home") {
        homeCalls += 1;
        if (homeCalls > 1) {
          await pendingHomeRefresh;
        }
        return new Response(JSON.stringify(homePayload), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/thread") {
        return new Response(JSON.stringify({
          thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
          messages: [],
          has_more: false,
          total_count: 0,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/threads") {
        return new Response(JSON.stringify({
          items: [
            {
              id: 1,
              office_id: "default-office",
              title: "Asistan",
              status: "active",
              created_at: "2026-03-15T09:00:00Z",
              updated_at: "2026-03-15T09:00:10Z",
              message_count: 2,
            },
          ],
          selected_thread_id: 1,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/agenda") {
        return new Response(JSON.stringify({ items: [], generated_from: "assistant_agenda_engine" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/inbox") {
        return new Response(JSON.stringify({ items: [], generated_from: "assistant_agenda_engine" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/suggested-actions") {
        return new Response(JSON.stringify({ items: [], generated_from: "assistant_agenda_engine", manual_review_required: true }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/drafts") {
        return new Response(JSON.stringify({ items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /assistant/calendar") {
        return new Response(JSON.stringify({
          today: "2026-03-15",
          generated_from: "assistant_calendar_engine",
          google_connected: false,
          items: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /integrations/google/status") {
        return new Response(JSON.stringify({
          provider: "google",
          configured: false,
          enabled: false,
          scopes: [],
          gmail_connected: false,
          calendar_connected: false,
          status: "pending",
          desktop_managed: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "GET /agent/tools") {
        return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (key === "POST /assistant/thread/messages/stream") {
        return ndjsonResponse([
          { type: "thread_ready", thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" } },
          { type: "assistant_start" },
          { type: "assistant_chunk", content: "Yanıt tamamlandı." },
          {
            type: "assistant_complete",
            response: {
              thread: { id: 1, office_id: "default-office", title: "Asistan", status: "active" },
              messages: [
                {
                  id: 1,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "user",
                  content: "Kontrol et",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-15T09:00:00Z",
                },
                {
                  id: 2,
                  thread_id: 1,
                  office_id: "default-office",
                  role: "assistant",
                  content: "Yanıt tamamlandı.",
                  linked_entities: [],
                  tool_suggestions: [],
                  draft_preview: null,
                  source_context: {},
                  requires_approval: false,
                  created_at: "2026-03-15T09:00:03Z",
                },
              ],
              has_more: false,
              total_count: 2,
            },
          },
        ]);
      }
      return new Response(JSON.stringify({ detail: `Unhandled route: ${method} ${url.pathname}` }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Sorunuzu yazın/), {
      target: { value: "Kontrol et" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Yanıtı iptal et" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Yanıt tamamlandı.")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: "Yanıtı iptal et" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".wa-typing__dot").length).toBe(0);

    resolveHomeRefresh();
    await waitFor(() => expect(homeCalls).toBeGreaterThan(1));
  });

  it("keeps messages isolated when switching assistant sessions", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspaceConfigured: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": {
        today_summary: "Bugün için öncelikli işler hazır.",
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Belge işi", created_by: "tester", created_at: "2026-03-14T09:00:00Z", updated_at: "2026-03-14T10:00:00Z", message_count: 2, last_message_preview: "Belge özeti hazır.", last_message_at: "2026-03-14T10:00:00Z" },
          { id: 2, office_id: "default-office", title: "Mail görevi", created_by: "tester", created_at: "2026-03-14T11:00:00Z", updated_at: "2026-03-14T11:05:00Z", message_count: 2, last_message_preview: "Mail taslağı hazır.", last_message_at: "2026-03-14T11:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread?limit=30&thread_id=1": {
        thread: { id: 1, office_id: "default-office", title: "Belge işi", created_by: "tester", created_at: "2026-03-14T09:00:00Z", updated_at: "2026-03-14T10:00:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Belgeyi özetle", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T09:59:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Belge özeti hazır.", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T10:00:00Z" },
        ],
        has_more: false,
        total_count: 2,
      },
      "GET /assistant/thread?limit=30&thread_id=2": {
        thread: { id: 2, office_id: "default-office", title: "Mail görevi", created_by: "tester", created_at: "2026-03-14T11:00:00Z", updated_at: "2026-03-14T11:05:00Z" },
        messages: [
          { id: 3, thread_id: 2, office_id: "default-office", role: "user", content: "Müvekkile yaz", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T11:04:00Z" },
          { id: 4, thread_id: 2, office_id: "default-office", role: "assistant", content: "Mail taslağı hazır.", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T11:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-03-11", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getAllByText("Belge özeti hazır.").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByTitle("Sohbetlerde ara"));
    await waitFor(() => expect(screen.getByPlaceholderText("Sohbet ara")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Mail görevi"));
    await waitFor(() => expect(screen.getAllByText("Müvekkile yaz").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("Mail taslağı hazır.").length).toBeGreaterThan(0));
    expect(screen.queryByText("Belgeyi özetle")).not.toBeInTheDocument();
  });

  it("opens a new thread immediately without waiting for home refresh", async () => {
    let homeCalls = 0;
    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-only",
        connector_dry_run: true,
        workspaceConfigured: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/home": () => {
        homeCalls += 1;
        return {
          today_summary: "Bugün için öncelikli işler hazır.",
          counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
          priority_items: [],
          requires_setup: [],
          connected_accounts: [],
          generated_from: "assistant_home_engine",
        };
      },
      "GET /assistant/threads": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Önceki sohbet",
            created_by: "tester",
            created_at: "2026-03-14T09:00:00Z",
            updated_at: "2026-03-14T10:00:00Z",
            message_count: 2,
            last_message_preview: "Eski yanıt",
            last_message_at: "2026-03-14T10:00:00Z",
          },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Önceki sohbet", created_by: "tester", created_at: "2026-03-14T09:00:00Z", updated_at: "2026-03-14T10:00:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Eski mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T09:59:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Eski yanıt", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, created_at: "2026-03-14T10:00:00Z" },
        ],
        has_more: false,
        total_count: 2,
      },
      "GET /assistant/thread?limit=30&thread_id=2": {
        thread: { id: 2, office_id: "default-office", title: "Yeni görev", created_by: "tester", created_at: "2026-03-14T11:00:00Z", updated_at: "2026-03-14T11:00:00Z" },
        messages: [],
        has_more: false,
        total_count: 0,
      },
      "POST /assistant/threads": {
        thread: { id: 2, office_id: "default-office", title: "Yeni görev", created_by: "tester", created_at: "2026-03-14T11:00:00Z", updated_at: "2026-03-14T11:00:00Z" },
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/approvals": { items: [], generated_from: "assistant_approval_center" },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-03-11", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Eski mesaj")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Yeni sohbet"));

    await waitFor(() => expect(screen.queryByText("Eski mesaj")).not.toBeInTheDocument());
    expect(homeCalls).toBe(1);
  });

  it("still shows thread history when assistant home fails", async () => {
    installFetchMock({
      "GET /health": {
        ok: true,
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
      "GET /assistant/home": () => new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
      "GET /assistant/threads": {
        items: [
          { id: 9, office_id: "default-office", title: "naber", created_by: "tester", created_at: "2026-04-06T12:16:40Z", updated_at: "2026-04-06T12:17:56Z", message_count: 14, last_message_preview: "Son mesaj", last_message_at: "2026-04-06T12:17:56Z" },
          { id: 8, office_id: "default-office", title: "eski sohbet", created_by: "tester", created_at: "2026-04-04T09:49:24Z", updated_at: "2026-04-04T09:51:48Z", message_count: 8, last_message_preview: "Önceki içerik", last_message_at: "2026-04-04T09:51:48Z" },
        ],
        selected_thread_id: 9,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 9, office_id: "default-office", title: "naber", created_by: "tester", created_at: "2026-04-06T12:16:40Z", updated_at: "2026-04-06T12:17:56Z" },
        messages: [
          { id: 1, thread_id: 9, office_id: "default-office", role: "user", content: "merhaba", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-06T12:16:40Z" },
        ],
        has_more: false,
        total_count: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/approvals": { items: [], generated_from: "approval_registry" },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("naber")).toBeInTheDocument());
    expect(screen.getByText("eski sohbet")).toBeInTheDocument();
    expect(screen.getByText("merhaba")).toBeInTheDocument();
  });

  it("shows starred messages from all threads and jumps to the selected thread", async () => {
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
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z", message_count: 2, last_message_preview: "Önemli mesaj", last_message_at: "2026-04-07T09:05:00Z" },
          { id: 2, office_id: "default-office", title: "İkinci sohbet", created_by: "tester", created_at: "2026-04-07T10:00:00Z", updated_at: "2026-04-07T10:06:00Z", message_count: 1, last_message_preview: "Başka önemli mesaj", last_message_at: "2026-04-07T10:06:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu sakla", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Önemli mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "PATCH /assistant/thread/messages/2/starred": {
        message: { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Önemli mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: true, starred_at: "2026-04-07T09:06:00Z", created_at: "2026-04-07T09:05:00Z" },
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/starred-messages": {
        thread: null,
        items: [
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Önemli mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: true, starred_at: "2026-04-07T09:06:00Z", thread_title: "Asistan", created_at: "2026-04-07T09:05:00Z" },
          { id: 5, thread_id: 2, office_id: "default-office", role: "assistant", content: "Başka önemli mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: true, starred_at: "2026-04-07T10:06:00Z", thread_title: "İkinci sohbet", created_at: "2026-04-07T10:05:00Z" },
        ],
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread?thread_id=2": {
        thread: { id: 2, office_id: "default-office", title: "İkinci sohbet", created_by: "tester", created_at: "2026-04-07T10:00:00Z", updated_at: "2026-04-07T10:06:00Z" },
        messages: [
          { id: 4, thread_id: 2, office_id: "default-office", role: "user", content: "Diğer sohbetteki soru", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T10:04:00Z" },
          { id: 5, thread_id: 2, office_id: "default-office", role: "assistant", content: "Başka önemli mesaj", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: true, starred_at: "2026-04-07T10:06:00Z", created_at: "2026-04-07T10:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getAllByText("Önemli mesaj").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByLabelText("Mesajı yıldızla"));
    fireEvent.click(screen.getByTitle("Yıldızlı mesajlar"));
    await waitFor(() => expect(screen.getByPlaceholderText("Yıldızlı mesaj ara")).toBeInTheDocument());
    expect(screen.getByText("Tüm sohbetlerde yıldızlananlar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /İkinci sohbet.*Başka önemli mesaj/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /İkinci sohbet.*Başka önemli mesaj/i }));
    await waitFor(() => expect(screen.getAllByText("Başka önemli mesaj").length).toBeGreaterThan(0));
  });

  it("renders user and assistant message actions with edit copy and feedback controls", async () => {
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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z", message_count: 2, last_message_preview: "Önemli mesaj", last_message_at: "2026-04-07T09:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu düzenle", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Bu yanıtı değerlendir", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "PATCH /assistant/thread/messages/2/feedback": (_input: RequestInfo | URL, init?: RequestInit) => {
        const parsed = JSON.parse(String(init?.body || "{}")) as { feedback_value?: string };
        const feedbackValue = parsed.feedback_value === "liked" || parsed.feedback_value === "disliked" ? parsed.feedback_value : null;
        return {
          message: {
            id: 2,
            thread_id: 1,
            office_id: "default-office",
            role: "assistant",
            content: "Bu yanıtı değerlendir",
            linked_entities: [],
            tool_suggestions: [],
            draft_preview: null,
            source_context: {},
            requires_approval: false,
            generated_from: "assistant_thread_message",
            ai_provider: null,
            ai_model: null,
            starred: false,
            starred_at: null,
            feedback_value: feedbackValue,
            feedback_note: null,
            feedback_at: feedbackValue ? "2026-04-07T09:06:00Z" : null,
            created_at: "2026-04-07T09:05:00Z",
          },
          generated_from: "assistant_thread_memory",
        };
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Bunu düzenle")).toBeInTheDocument());

    expect(screen.getByLabelText("Mesajı düzenle")).toBeInTheDocument();
    expect(screen.getByLabelText("Mesajı kopyala")).toBeInTheDocument();
    expect(screen.getByLabelText("Mesajı paylaş")).toBeInTheDocument();
    expect(screen.getByLabelText("Yanıtı beğen")).toBeInTheDocument();
    expect(screen.getByLabelText("Yanıtı beğenme")).toBeInTheDocument();
    expect(screen.getByLabelText("Yanıtı kopyala")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Mesajı düzenle"));
    const inlineEditor = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    expect(inlineEditor).toHaveValue("Bunu düzenle");
    const editShell = inlineEditor.closest(".wa-bubble__edit-shell");
    expect(editShell).not.toBeNull();
    expect(inlineEditor.tagName).toBe("TEXTAREA");
    expect(within(editShell as HTMLElement).getByRole("button", { name: "İptal" })).toBeInTheDocument();
    expect(within(editShell as HTMLElement).getByRole("button", { name: "Gönder" })).toBeInTheDocument();

    fireEvent.click(within(editShell as HTMLElement).getByRole("button", { name: "İptal" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "İptal" })).not.toBeInTheDocument());
    expect(screen.getByText("Bunu düzenle")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Yanıtı beğen"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(screen.getByLabelText("Yanıtı beğenme"));
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğenme")).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByLabelText("Yanıtı kopyala"));
    await waitFor(() => expect(clipboardWriteTextMock).toHaveBeenCalledWith("Bu yanıtı değerlendir"));
  });

  it("does not revive cleared feedback from stale local storage", async () => {
    window.localStorage.setItem("lawcopilot.assistant.message.feedback", JSON.stringify({ "1:2": "liked" }));

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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z", message_count: 2, last_message_preview: "Önemli mesaj", last_message_at: "2026-04-07T09:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu düzenle", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Bu yanıtı değerlendir", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, feedback_value: null, feedback_note: null, feedback_at: null, created_at: "2026-04-07T09:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Bu yanıtı değerlendir")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByLabelText("Yanıtı beğen")).toHaveAttribute("aria-pressed", "false"));
    window.localStorage.removeItem("lawcopilot.assistant.message.feedback");
  });

  it("edits a user message in place instead of appending a duplicate", async () => {
    let streamPayload: any = null;
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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z", message_count: 2, last_message_preview: "Eski yanıt", last_message_at: "2026-04-07T09:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu düzenle", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Eski yanıt", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "POST /assistant/thread/messages/stream": (_input: RequestInfo | URL, init?: RequestInit) => {
        streamPayload = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        const response = {
          thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:06:00Z" },
          messages: [
            { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu düzelttim", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
            { id: 3, thread_id: 1, office_id: "default-office", role: "assistant", content: "Yeni yanıt", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:06:00Z" },
          ],
          has_more: false,
          total_count: 2,
          generated_from: "assistant_thread_message",
        };
        return ndjsonResponse([
          { type: "thread_ready", thread: response.thread, user_message: response.messages[0] },
          { type: "assistant_start" },
          { type: "assistant_chunk", delta: "Yeni yanıt", content: "Yeni yanıt" },
          { type: "assistant_complete", response },
        ]);
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Bunu düzenle")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Mesajı düzenle"));
    fireEvent.change(screen.getByDisplayValue("Bunu düzenle"), { target: { value: "Bunu düzelttim" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));

    await waitFor(() => expect(streamPayload).not.toBeNull());
    if (!streamPayload) {
      throw new Error("Beklenen düzenleme payload'ı oluşmadı.");
    }
    const submittedPayload = streamPayload;
    expect(submittedPayload.edit_message_id).toBe(1);
    expect(submittedPayload.content).toBe("Bunu düzelttim");

    await waitFor(() => expect(screen.getByText("Yeni yanıt")).toBeInTheDocument());
    expect(screen.getByText("Bunu düzelttim")).toBeInTheDocument();
    expect(screen.getAllByText("Bunu düzelttim")).toHaveLength(1);
    expect(screen.getAllByText("Yeni yanıt")).toHaveLength(1);
  });

  it("opens share dialog from assistant messages and creates a whatsapp draft", async () => {
    let createdShareDraft: Record<string, unknown> | null = null;
    let sendRequested = false;
    let draftItems: Array<Record<string, unknown>> = [];
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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": {
        items: [
          { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z", message_count: 2, last_message_preview: "Paylaşılacak özet", last_message_at: "2026-04-07T09:05:00Z" },
        ],
        selected_thread_id: 1,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [
          { id: 1, thread_id: 1, office_id: "default-office", role: "user", content: "Bunu grupla paylaş", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_user", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:04:00Z" },
          { id: 2, thread_id: 1, office_id: "default-office", role: "assistant", content: "Paylaşılacak özet", linked_entities: [], tool_suggestions: [], draft_preview: null, source_context: {}, requires_approval: false, generated_from: "assistant_thread_message", ai_provider: null, ai_model: null, starred: false, starred_at: null, created_at: "2026-04-07T09:05:00Z" },
        ],
        has_more: false,
        total_count: 2,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/contact-profiles": {
        items: [
          {
            id: "group:aile",
            kind: "group",
            display_name: "Aile Grubu",
            relationship_hint: "Yakın çevre",
            persona_summary: "WhatsApp aile grubu",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: [],
            handles: [],
            watch_enabled: true,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-07T09:01:00Z",
            source_count: 2,
          },
        ],
        generated_from: "assistant_contact_profiles",
      },
      "POST /assistant/share-drafts": (_input: RequestInfo | URL, init?: RequestInit) => {
        createdShareDraft = JSON.parse(String(init?.body || "{}"));
        draftItems = [
          {
            id: 31,
            draft_type: "send_whatsapp_message",
            channel: "whatsapp",
            to_contact: "Aile Grubu",
            subject: null,
            body: "Paylaşılacak özet",
            source_context: { message_id: 2, thread_id: 1 },
            generated_from: "assistant_share_actions",
            approval_status: "pending_review",
            delivery_status: "not_sent",
            created_at: "2026-04-07T09:06:00Z",
            updated_at: "2026-04-07T09:06:00Z",
          },
        ];
        return {
          draft: draftItems[0],
          message: "Paylaşım taslağı oluşturuldu.",
          generated_from: "assistant_share_actions",
        };
      },
      "POST /assistant/drafts/31/send": () => {
        sendRequested = true;
        draftItems = [
          {
            ...draftItems[0],
            approval_status: "approved",
            delivery_status: "manual_review_only",
            dispatch_state: "idle",
            updated_at: "2026-04-07T09:07:00Z",
          },
        ];
        return {
          draft: draftItems[0],
          action: {
            id: 93,
            target_channel: "whatsapp",
          },
          message: "Taslak güvenlik nedeniyle inceleme modunda bırakıldı.",
          dispatch_mode: "manual_review_only",
        };
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": () => ({ items: draftItems, matter_drafts: [], generated_from: "assistant_agenda_engine" }),
      "GET /assistant/calendar": { today: "2026-04-07", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getAllByText("Paylaşılacak özet").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByLabelText("Mesajı paylaş"));
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Mesajı paylaş" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Aile Grubu/i }));
    const recipientInput = screen.getByPlaceholderText("Kişi adı, grup adı veya numara");
    expect(recipientInput).toHaveValue("Aile Grubu");

    fireEvent.click(screen.getByRole("button", { name: "Paylaşımı hazırla" }));

    await waitFor(() => expect(createdShareDraft).not.toBeNull());
    await waitFor(() => expect(sendRequested).toBe(true));
    expect(createdShareDraft).toMatchObject({
      channel: "whatsapp",
      to_contact: "Aile Grubu",
      message_id: 2,
      thread_id: 1,
      content: "Paylaşılacak özet",
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Mesajı paylaş" })).not.toBeInTheDocument());
  });

  it("does not render people and account-management panels on the empty welcome state", async () => {
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
        counts: { agenda: 0, inbox: 0, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        relationship_profiles: [
          {
            id: "person:annem",
            display_name: "Annem",
            relationship_hint: "Anne",
            profile_strength: "yüksek",
            selection_score: 16,
            selection_reason: "ilişki sinyali: anne, son dönemde aktif",
            summary: "Anne olarak öne çıkıyor. Çikolatayı seviyor.",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: [],
            handles: [],
            watch_enabled: true,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-08T08:00:00Z",
            source_count: 5,
            preference_signals: ["Çikolatayı seviyor."],
            gift_ideas: ["Küçük bir çikolata"],
            important_dates: [],
            notes: "",
            auto_selected: true,
          },
        ],
        contact_directory: [
          {
            id: "person:annem",
            kind: "person",
            display_name: "Annem",
            relationship_hint: "Anne",
            persona_summary: "WhatsApp üzerinden görülen iletişim profili.",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: ["+905551112233"],
            handles: [],
            watch_enabled: true,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-08T08:00:00Z",
            source_count: 5,
          },
          {
            id: "person:kampanya-bulteni",
            kind: "person",
            display_name: "Kampanya Bülteni",
            relationship_hint: "İletişim kişisi",
            persona_summary: "E-posta üzerinden görülen iletişim profili.",
            channels: ["email"],
            emails: ["newsletter@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-08T07:30:00Z",
            source_count: 2,
          },
        ],
        contact_directory_summary: {
          total_accounts: 2,
          priority_profiles: 1,
          blocked_accounts: 0,
          watch_enabled_accounts: 1,
        },
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": { items: [], selected_thread_id: null, generated_from: "assistant_thread_memory" },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [],
        has_more: false,
        total_count: 0,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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
    expect(screen.queryByText("Önemli kişiler")).not.toBeInTheDocument();
    expect(screen.queryByText("Hesaplar ve adresler")).not.toBeInTheDocument();
    expect(screen.queryByText((content) => content.includes("Çikolatayı seviyor."))).not.toBeInTheDocument();
  });

  it("keeps channel memory cards out of the empty welcome state", async () => {
    let postedPayload: Record<string, unknown> | null = null;
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
        today_summary: "İletişim kayıtları hazır.",
        counts: { agenda: 0, inbox: 1, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": { items: [], selected_thread_id: null, generated_from: "assistant_thread_memory" },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [],
        has_more: false,
        total_count: 0,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": {
        items: [
          {
            id: "whatsapp-12",
            kind: "reply_needed",
            title: "Annem mesaj attı",
            details: "WhatsApp · Son mesaj bugün",
            priority: "medium",
            due_at: "2026-04-08T08:00:00Z",
            source_type: "whatsapp_message",
            source_ref: "msg-12",
            provider: "whatsapp",
            memory_state: "operational_only",
            manual_review_required: true,
            recommended_action_ids: [],
          },
        ],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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
      "POST /memory/channel-state": (_input: RequestInfo | URL, init?: RequestInit) => {
        postedPayload = JSON.parse(String(init?.body || "{}"));
        return {
          item: {
            id: 12,
            memory_state: "candidate_memory",
          },
          memory_overview: {
            counts: { records: 1 },
            learned_topics: [],
            recent_corrections: [],
          },
          health: {},
        };
      },
    });

    renderApp(["/assistant"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Başlamak için yeterli olanlar")).toBeInTheDocument());
    expect(screen.queryByText("İletişim hafızası")).not.toBeInTheDocument();
    expect(postedPayload).toBeNull();
  });

  it("expands the contact directory and shows inferred communication signals", async () => {
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
        today_summary: "İletişim rehberi hazır.",
        counts: { agenda: 0, inbox: 1, calendar_today: 0, drafts_pending: 0 },
        priority_items: [],
        requires_setup: [],
        connected_accounts: [],
        relationship_profiles: [
          {
            id: "mother",
            display_name: "Annem",
            relationship_hint: "Anne",
            profile_strength: "yüksek",
            selection_score: 18,
            selection_reason: "yakın çevre",
            summary: "Anne olarak öne çıkıyor.",
            channels: ["whatsapp", "email"],
            emails: ["annem@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T09:00:00Z",
            source_count: 8,
            preference_signals: ["Çikolatayı seviyor."],
            gift_ideas: ["Küçük bir çikolata kutusu"],
            inference_signals: ["Çikolatayı seviyor.", "WhatsApp, E-posta üzerinden düzenli temas var."],
            channel_summary: "WhatsApp 5, E-posta 3",
            last_inbound_preview: "Çikolatayı çok severim, gelirken unutma.",
            last_inbound_channel: "WhatsApp",
            important_dates: [],
            notes: "",
            auto_selected: false,
          },
        ],
        contact_directory: [
          {
            id: "1",
            kind: "person",
            display_name: "Annem",
            relationship_hint: "Anne",
            persona_summary: "Birden fazla kanalda görülen iletişim profili.",
            channels: ["whatsapp", "email"],
            emails: ["annem@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: true,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T09:00:00Z",
            source_count: 8,
            inference_signals: ["Çikolatayı seviyor.", "WhatsApp, E-posta üzerinden düzenli temas var."],
            channel_summary: "WhatsApp 5, E-posta 3",
            last_inbound_preview: "Çikolatayı çok severim, gelirken unutma.",
            last_inbound_channel: "WhatsApp",
          },
          {
            id: "2",
            kind: "person",
            display_name: "Babam",
            relationship_hint: "Baba",
            persona_summary: "WhatsApp üzerinden görülen iletişim profili.",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T08:00:00Z",
            source_count: 4,
            inference_signals: ["Sık temas kurulan kişi / hesap."],
            channel_summary: "WhatsApp 4",
            last_inbound_preview: "Akşam konuşalım.",
            last_inbound_channel: "WhatsApp",
          },
          {
            id: "3",
            kind: "person",
            display_name: "Müvekkil",
            relationship_hint: "Muhtemel müvekkil / müşteri",
            persona_summary: "E-posta üzerinden görülen iletişim profili.",
            channels: ["email"],
            emails: ["musteri@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T07:00:00Z",
            source_count: 2,
            inference_signals: ["E-posta üzerinden düzenli temas var."],
            channel_summary: "E-posta 2",
            last_inbound_preview: "Dosya hazır.",
            last_inbound_channel: "E-posta",
          },
          {
            id: "4",
            kind: "group",
            display_name: "Aile Grubu",
            relationship_hint: "Mesaj grubu",
            persona_summary: "Takip edilen grup konuşması.",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T06:00:00Z",
            source_count: 2,
            inference_signals: ["İletişim çoğunlukla WhatsApp üzerinden ilerliyor."],
            channel_summary: "WhatsApp 2",
            last_inbound_preview: "Pazar kahvaltısı bizde.",
            last_inbound_channel: "WhatsApp",
          },
          {
            id: "5",
            kind: "person",
            display_name: "Muhasebe",
            relationship_hint: "İletişim kişisi",
            persona_summary: "E-posta üzerinden görülen iletişim profili.",
            channels: ["email"],
            emails: ["muhasebe@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-04-10T05:00:00Z",
            source_count: 1,
            inference_signals: ["Bülten veya otomatik hesap gibi görünüyor."],
            channel_summary: "E-posta",
            last_inbound_preview: "Aylık ekstre hazır.",
            last_inbound_channel: "E-posta",
          },
        ],
        contact_directory_summary: {
          total_accounts: 5,
          priority_profiles: 1,
          blocked_accounts: 0,
          watch_enabled_accounts: 1,
          channels: { whatsapp: 3, email: 3 },
        },
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": { items: [], selected_thread_id: null, generated_from: "assistant_thread_memory" },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [],
        has_more: false,
        total_count: 0,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": { items: [], generated_from: "assistant_agenda_engine", manual_review_required: true },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-08", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByText("Önemli kişiler")).toBeInTheDocument());
    expect(screen.getAllByText((content) => content.includes("Çikolatayı seviyor.")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Muhasebe")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tüm kayıtları göster (5)" }));

    expect(screen.getByText("Muhasebe")).toBeInTheDocument();
    expect(screen.getByText("WhatsApp 3 · E-posta 3")).toBeInTheDocument();
  });

  it("groups today items into sections and filters by the selected section", async () => {
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
        greeting_title: "Selam Sami",
        greeting_message: "Sami, bugünün önceliklerini toparladım.",
        counts: { agenda: 5, inbox: 2, calendar_today: 1, drafts_pending: 1 },
        priority_items: [],
        proactive_suggestions: [],
        requires_setup: [],
        connected_accounts: [],
        generated_from: "assistant_home_engine",
      },
      "GET /assistant/threads": { items: [], selected_thread_id: null, generated_from: "assistant_thread_memory" },
      "GET /assistant/thread": {
        thread: { id: 1, office_id: "default-office", title: "Asistan", created_by: "tester", created_at: "2026-04-07T09:00:00Z", updated_at: "2026-04-07T09:05:00Z" },
        messages: [],
        has_more: false,
        total_count: 0,
        generated_from: "assistant_thread_memory",
      },
      "GET /assistant/agenda": {
        items: [
          {
            id: "task-1",
            kind: "overdue_task",
            title: "Geciken görev: Dilekçeyi tamamla",
            details: "Bu görev için son tarih geçti.",
            priority: "high",
            due_at: "2026-04-13T08:00:00Z",
            source_type: "task",
            source_ref: "1",
            manual_review_required: true,
          },
          {
            id: "wa-1",
            kind: "communication_follow_up",
            title: "WhatsApp: Babam için mesaj hazırla",
            details: "Babam ile konuşma yaklaşık 20 dakikadır yanıt bekliyor.",
            priority: "high",
            due_at: "2026-04-13T09:00:00Z",
            source_type: "whatsapp_message",
            source_ref: "wa-1",
            provider: "whatsapp",
            manual_review_required: true,
          },
          {
            id: "mail-1",
            kind: "communication_follow_up",
            title: "Outlook e-postası: Ayşe Kaya için yanıt hazırla",
            details: "Ayşe Kaya başlıklı ileti yanıt bekliyor.",
            priority: "high",
            due_at: "2026-04-13T09:10:00Z",
            source_type: "email_thread",
            source_ref: "mail-1",
            provider: "outlook",
            manual_review_required: true,
          },
          {
            id: "calendar-1",
            kind: "calendar_prep",
            title: "Duruşma hazırlığı",
            details: "Yarınki kayıt için hazırlık gerekebilir.",
            priority: "medium",
            due_at: "2026-04-14T08:00:00Z",
            source_type: "calendar_event",
            source_ref: "cal-1",
            manual_review_required: true,
          },
          {
            id: "draft-1",
            kind: "draft_review",
            title: "Taslağı gözden geçir: Durum özeti",
            details: "E-posta için hazırlanan taslak onay bekliyor.",
            priority: "high",
            due_at: "2026-04-13T09:15:00Z",
            source_type: "outbound_draft",
            source_ref: "draft-1",
            manual_review_required: true,
          },
        ],
        generated_from: "assistant_agenda_engine",
      },
      "GET /assistant/inbox": { items: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/suggested-actions": {
        items: [
          {
            id: 1,
            title: "Ayşe Kaya için taslak oluştur",
            description: "Yanıt taslağı hazırlanabilir.",
            rationale: "Müvekkil dönüş bekliyor.",
            manual_review_required: true,
          },
        ],
        generated_from: "assistant_agenda_engine",
        manual_review_required: true,
      },
      "GET /assistant/drafts": { items: [], matter_drafts: [], generated_from: "assistant_agenda_engine" },
      "GET /assistant/calendar": { today: "2026-04-13", generated_from: "assistant_calendar_engine", google_connected: false, items: [] },
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

    await waitFor(() => expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Çalışma Paneli" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Bugün" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Bugün" }));

    await waitFor(() => expect(screen.getByRole("tab", { name: "Mesajlar (1)" })).toBeInTheDocument());
    expect(screen.getByText("WhatsApp: Babam için mesaj hazırla")).toBeInTheDocument();
    expect(screen.getByText("Outlook e-postası: Ayşe Kaya için yanıt hazırla")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Mesajlar (1)" }));
    expect(screen.getByText("WhatsApp: Babam için mesaj hazırla")).toBeInTheDocument();
    expect(screen.queryByText("Outlook e-postası: Ayşe Kaya için yanıt hazırla")).not.toBeInTheDocument();
    expect(screen.queryByText("Taslağı gözden geçir: Durum özeti")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "E-posta (1)" }));
    expect(screen.getByText("Outlook e-postası: Ayşe Kaya için yanıt hazırla")).toBeInTheDocument();
    expect(screen.queryByText("WhatsApp: Babam için mesaj hazırla")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Taslaklar (1)" }));
    expect(screen.getByText("Taslağı gözden geçir: Durum özeti")).toBeInTheDocument();
    expect(screen.queryByText("Outlook e-postası: Ayşe Kaya için yanıt hazırla")).not.toBeInTheDocument();
  });
});
