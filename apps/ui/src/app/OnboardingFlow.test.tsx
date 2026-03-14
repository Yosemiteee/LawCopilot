import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Onboarding flow", () => {
  it("renders a real onboarding surface with provider and chat kickoff guidance", async () => {
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
        workspace_configured: false,
        workspace_root_name: "",
        provider_type: "gemini",
        provider_model: "gemini-2.5-flash",
        provider_configured: true,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/onboarding/state": {
        complete: false,
        workspace_ready: false,
        provider_ready: true,
        model_ready: true,
        assistant_ready: false,
        user_ready: false,
        provider_type: "gemini",
        provider_model: "gemini-2.5-flash",
        summary: "Asistan önce persona ayarlarını, sonra kullanıcı profilini sohbetten çıkaracak.",
        next_question: "Önce ben kimim, sonra sen kimsin diye konuşalım mı?",
        interview_intro: "Asistan ilk açılışta seninle kısa bir tanışma röportajı yapar.",
        interview_topics: [
          "Asistanın adı, tonu ve çalışma tarzı",
          "Size nasıl hitap edeceği",
        ],
        suggested_prompts: [
          "Sen kimsin ve bana nasıl yardımcı olacaksın?",
          "Ben kimim, hakkımda neleri bilmek istiyorsun?",
        ],
        questions: [
          {
            id: "assistant-name",
            field: "assistant_name",
            target: "assistant",
            question: "Nasıl bir asistan olmamı istersin?",
            reason: "Persona tonunu belirlemek için",
          },
        ],
        profile: {
          display_name: "Sami",
          favorite_color: "Yeşil",
        },
        assistant_profile: {
          assistant_name: "Dava Dostu",
          tone: "Net ama sıcak",
          role_summary: "Hukuk çalışma asistanı",
        },
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
    });

    renderApp(["/onboarding"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({
          provider: {
            type: "gemini",
            baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
            model: "gemini-2.5-flash",
            validationStatus: "valid",
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByText("Başlangıç")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Hesaplarını bağla" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Asistan stilini başlatın" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sohbetle kişiselleştirme" })).toBeInTheDocument();
    expect(screen.getAllByText("gemini-2.5-flash").length).toBeGreaterThan(0);
    expect(screen.getByText("Asistan ilk açılışta seninle kısa bir tanışma röportajı yapar.")).toBeInTheDocument();
    expect(screen.getByText("Google hesabını bağladığınızda Gmail, Takvim ve Drive birlikte gelir. Sağlayıcı, Google ve Telegram bağlantıları aynı kurulum alanında tutulur.")).toBeInTheDocument();
    expect(screen.getByText("İlk soru")).toBeInTheDocument();
  });

  it("updates workspace state when a desktop folder is selected from onboarding", async () => {
    let healthCalls = 0;
    installFetchMock({
      "GET /health": () => {
        healthCalls += 1;
        return {
          ok: true,
          service: "lawcopilot-api",
          app_name: "LawCopilot",
          version: "0.7.0-pilot.1",
          office_id: "default-office",
          deployment_mode: "local-only",
          release_channel: "pilot",
          connector_dry_run: true,
          workspace_configured: healthCalls > 2,
          workspace_root_name: healthCalls > 2 ? "Dava Belgeleri" : "",
          provider_configured: false,
          rag_backend: "inmemory",
          rag_runtime: { backend: "inmemory", mode: "default" },
        };
      },
      "GET /assistant/onboarding/state": () => ({
        complete: false,
        workspace_ready: healthCalls > 2,
        provider_ready: false,
        assistant_ready: false,
        user_ready: false,
        workspace_root_name: healthCalls > 2 ? "Dava Belgeleri" : "",
      }),
      "GET /profile": {
        office_id: "default-office",
        display_name: "",
        favorite_color: "",
        food_preferences: "",
        transport_preference: "",
        weather_preference: "",
        travel_preferences: "",
        communication_style: "",
        assistant_notes: "",
        important_dates: [],
        created_at: null,
        updated_at: null,
      },
      "GET /assistant/runtime/profile": {
        office_id: "default-office",
        assistant_name: "",
        role_summary: "Kaynak dayanaklı hukuk çalışma asistanı",
        tone: "Net ve profesyonel",
        avatar_path: "",
        soul_notes: "",
        tools_notes: "",
        heartbeat_extra_checks: [],
        created_at: null,
        updated_at: null,
      },
    });

    renderApp(["/onboarding"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({ provider: {} }),
        chooseWorkspaceRoot: async () => ({
          canceled: false,
          workspace: {
            workspaceRootPath: "/tmp/dava-belgeleri",
            workspaceRootName: "Dava Belgeleri",
            workspaceRootHash: "hash",
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByRole("button", { name: /Çalışma klasörü seç/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Çalışma klasörü seç/i }));

    await waitFor(() => expect(screen.getAllByText("Dava Belgeleri").length).toBeGreaterThan(0));
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

    renderApp(["/matters"], {
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
