import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

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
  "GET /assistant/runtime/profile": {
    office_id: "default-office",
    assistant_name: "Canavar",
    role_summary: "Kaynak dayanaklı hukuk çalışma asistanı",
    tone: "Net ve profesyonel",
    avatar_path: "",
    soul_notes: "",
    tools_notes: "",
    heartbeat_extra_checks: [],
  },
  "GET /assistant/runtime/workspace": {
    enabled: true,
    workspace_ready: true,
    bootstrap_required: false,
    last_sync_at: "2026-03-11T09:45:00Z",
    workspace_path: "/tmp/openclaw/workspace",
    curated_skill_count: 1,
    curated_skills: [{ slug: "proactive-tasks", title: "Proaktif Görevler", summary: "Takip rehberi", enabled: true }],
    files: [],
    daily_log_path: "/tmp/openclaw/workspace/memory/daily-logs/2026-03-11.md",
    tool_count: 4,
    tool_namespace_count: 2,
    resource_count: 6,
    progress_path: "/tmp/openclaw/workspace/PROGRESS.md",
    context_snapshot_path: "/tmp/openclaw/workspace/.openclaw/context-snapshot.json",
    capability_manifest_path: "/tmp/openclaw/workspace/.openclaw/capabilities.json",
    resource_manifest_path: "/tmp/openclaw/workspace/.openclaw/resources.json",
  },
  "GET /telemetry/health": {
    ok: true,
    app_name: "LawCopilot",
    version: "0.6.1",
    release_channel: "pilot",
    environment: "pilot",
    deployment_mode: "local-only",
    desktop_shell: "electron",
    office_id: "default-office",
    structured_log_path: "artifacts/events.log.jsonl",
    audit_log_path: "artifacts/audit.log.jsonl",
    db_path: "artifacts/lawcopilot.db",
    connector_dry_run: true,
    openclaw_workspace_ready: true,
    openclaw_bootstrap_required: false,
    openclaw_last_sync_at: "2026-03-11T09:45:00Z",
    openclaw_curated_skill_count: 1,
    openclaw_tool_count: 4,
    openclaw_resource_count: 6,
    recent_events: [],
  },
  "GET /tools": { items: [] },
  "GET /agent/runs?limit=8": { items: [] },
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

    await waitFor(() => expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument();
  });

  it("keeps the assistant sidebar focused on assistant tools instead of duplicating profile access", async () => {
    installFetchMock(BASE_MOCKS);

    renderApp(["/assistant"]);

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    expect(screen.queryByTitle("Profil")).not.toBeInTheDocument();
    expect(screen.getByTitle("Ayarlar")).toBeInTheDocument();
    expect(screen.queryByTitle("Gelişmiş Hafıza")).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Ana gezinme" })).not.toBeInTheDocument();
  });

  it("hides the workbench button while the assistant workbench drawer is open", async () => {
    installFetchMock(BASE_MOCKS);

    renderApp(["/assistant?tool=today"]);

    await waitFor(() => expect(screen.getByLabelText("Kapat")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Çalışma Paneli" })).not.toBeInTheDocument();
  });

  it("opens the workbench drawer even when onboarding is still incomplete", async () => {
    installFetchMock({
      ...BASE_MOCKS,
      "GET /assistant/home": {
        ...BASE_MOCKS["GET /assistant/home"],
        onboarding: {
          complete: false,
          blocked_by_setup: false,
          starter_prompts: ["Kuruluma sohbetten devam edelim."],
          steps: [
            {
              id: "connect-model",
              title: "Model bağla",
              complete: false,
            },
          ],
        },
      },
    });

    renderApp(["/assistant"]);

    await waitFor(() => expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Çalışma Paneli" }));

    await waitFor(() => expect(screen.getByLabelText("Kenar çubuğunu kapat")).toBeInTheDocument());
    expect(screen.getByText("LawCopilot")).toBeInTheDocument();
  });

  it("redirects the old dashboard route to the assistant", async () => {
    installFetchMock({
      ...BASE_MOCKS,
    });

    renderApp(["/dashboard"]);

    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument();
  });

  it("renders workspace route as standalone workspace page and prefers workspace context", async () => {
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

    await waitFor(() => expect(screen.getByText("Çalışma klasörünüzdeki belgeleri, taslakları ve ek veri kaynaklarını burada birlikte izleyin.")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "Asistana dön" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Çalışma Paneli" })).not.toBeInTheDocument();
    expect(screen.queryByText("Eski Seçili Dosya")).not.toBeInTheDocument();
  });

  it("keeps a dedicated startup splash visible until desktop hydration completes", async () => {
    const fetchMock = installFetchMock(BASE_MOCKS);
    const runtimeInfo = deferred<Record<string, unknown>>();
    const storedConfig = deferred<Record<string, unknown>>();
    const workspaceConfig = deferred<Record<string, unknown>>();

    renderApp(["/dashboard"], {
      desktop: {
        getRuntimeInfo: () => runtimeInfo.promise,
        getStoredConfig: () => storedConfig.promise,
        getWorkspaceConfig: () => workspaceConfig.promise,
      },
    });

    expect(screen.getByText("LawCopilot")).toBeInTheDocument();
    expect(screen.getByText("Çalışma alanı hazırlanıyor...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Asistana dön" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    runtimeInfo.resolve({
      apiBaseUrl: "http://127.0.0.1:18731",
      sessionToken: "",
      deploymentMode: "local-only",
      officeId: "default-office",
      releaseChannel: "pilot",
      default_model_profile: "hybrid",
    });
    storedConfig.resolve({});
    workspaceConfig.resolve({ workspaceRootPath: "/tmp/workspace", workspaceRootName: "Deneme Belgeleri" });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByPlaceholderText(/Sorunuzu yazın/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Çalışma Paneli" })).toBeInTheDocument();
  });
});
