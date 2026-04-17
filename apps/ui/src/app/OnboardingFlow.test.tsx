import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function installSettingsSurfaceMocks() {
  installFetchMock({
    "GET /health": {
      ok: true,
      service: "lawcopilot-api",
      app_name: "LawCopilot",
      version: "0.7.0-pilot.1",
      office_id: "default-office",
      deployment_mode: "local-only",
      release_channel: "pilot",
      connector_dry_run: true,
      workspace_configured: true,
      workspace_root_name: "Dava Belgeleri",
      provider_type: "gemini",
      provider_model: "gemini-2.5-flash",
      provider_configured: true,
      rag_backend: "inmemory",
      rag_runtime: { backend: "inmemory", mode: "default" },
    },
    "GET /settings/model-profiles": {
      default: "hybrid",
      deployment_mode: "local-only",
      office_id: "default-office",
      profiles: { hybrid: { provider: "gemini", policy: "default" } },
    },
    "GET /telemetry/health": {
      service: "lawcopilot-api",
      office_id: "default-office",
      deployment_mode: "local-only",
      provider_status: "ready",
      runtime_status: "ready",
    },
    "GET /workspace": {
      configured: true,
      workspace: {
        id: 1,
        display_name: "Dava Belgeleri",
        root_path: "/tmp/dava-belgeleri",
        root_path_hash: "hash",
      },
      documents: { items: [], count: 0 },
      scan_jobs: { items: [] },
    },
    "GET /assistant/onboarding/state": {
      complete: false,
      workspace_ready: true,
      provider_ready: true,
      model_ready: true,
      assistant_ready: false,
      user_ready: false,
      provider_type: "gemini",
      provider_model: "gemini-2.5-flash",
      summary: "Temel kurulum tamamlandı. Şimdi kısa bir tanışma ile sana nasıl hitap edeceğimi ve benim hangi adla yanında olacağımı netleştireceğiz.",
      next_question: "Sen kimsin, sana nasıl hitap etmemi istersin?",
      interview_intro: "Asistan ilk açılışta soruları tek tek sorar ve verdiğiniz cevaplara göre çalışma tarzını ayarlar.",
      interview_topics: [
        "Size nasıl hitap edeceği",
        "Kendi adını nasıl kullanacağı",
        "Asistanın tonu ve çalışma tarzı",
      ],
    },
    "GET /profile": {
      office_id: "default-office",
      display_name: "Sami",
      favorite_color: "Yeşil",
      food_preferences: "",
      transport_preference: "Tren",
      weather_preference: "",
      travel_preferences: "",
      communication_style: "Direkt",
      assistant_notes: "",
      important_dates: [],
      related_profiles: [],
      created_at: null,
      updated_at: null,
    },
    "GET /assistant/runtime/profile": {
      office_id: "default-office",
      assistant_name: "Dava Dostu",
      role_summary: "Hukuk çalışma asistanı",
      tone: "Net ama sıcak",
      avatar_path: "",
      soul_notes: "",
      tools_notes: "",
      heartbeat_extra_checks: [],
      created_at: null,
      updated_at: null,
    },
    "GET /assistant/runtime/workspace": {
      enabled: true,
      workspace_ready: true,
      bootstrap_required: false,
      last_sync_at: "2026-03-15T00:00:00Z",
      workspace_path: "/tmp/openclaw-state/workspace",
      curated_skill_count: 1,
      curated_skills: [],
      files: [],
      daily_log_path: null,
    },
    "GET /assistant/tools/status": {
      items: [],
      generated_from: "connector_registry",
    },
  });
}

function createDesktopMocks() {
  return {
    getRuntimeInfo: async () => ({}),
    getStoredConfig: async () => ({}),
    getWorkspaceConfig: async () => ({
      workspaceRootPath: "/tmp/dava-belgeleri",
      workspaceRootName: "Dava Belgeleri",
    }),
    getIntegrationConfig: async () => ({
      provider: {
        type: "gemini",
        baseUrl: "https://generativelanguage.googleapis.com/v1beta",
        model: "gemini-2.5-flash",
        validationStatus: "valid",
      },
      google: {
        enabled: false,
        oauthConnected: false,
        validationStatus: "pending",
        clientIdConfigured: false,
      },
      telegram: {
        enabled: false,
        validationStatus: "pending",
      },
    }),
    getGoogleAuthStatus: async () => ({
      configured: false,
      clientReady: false,
      scopes: [],
    }),
  };
}

describe("Onboarding flow", () => {
  it("redirects onboarding route into settings setup tab", async () => {
    installSettingsSurfaceMocks();

    renderApp(["/onboarding"], {
      desktop: createDesktopMocks(),
    });

    await waitFor(() => expect(screen.getByText("Çalışma klasörü erişimi")).toBeInTheDocument());
    expect(screen.getByText("Dava Belgeleri")).toBeInTheDocument();
    expect(screen.queryByText("Başlangıç")).not.toBeInTheDocument();
  });

  it("opens the settings setup tab instead of a separate onboarding page", async () => {
    installSettingsSurfaceMocks();

    renderApp(["/settings?tab=kurulum"], {
      desktop: createDesktopMocks(),
    });

    await waitFor(() => expect(screen.getByText("Çalışma klasörü erişimi")).toBeInTheDocument());
    expect(screen.queryByText("İlk kurulum görünürlüğü")).not.toBeInTheDocument();
  });

  it("shows the setup banner on protected surfaces before onboarding is complete", async () => {
    installFetchMock({
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
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /matters": { items: [] },
    });

    renderApp(["/_embedded/matters"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
      },
    });

    await waitFor(() => expect(screen.getByText("Önce kurulum tamamlanmalı")).toBeInTheDocument());
    expect(screen.getByText("Ayarları aç")).toBeInTheDocument();
  });
});
