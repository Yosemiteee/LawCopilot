import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

describe("SettingsPage", () => {
  it("renders personal profile form and saves changes", async () => {
    let savedBody = "";
    let runtimeSavedBody = "";

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
        workspace_root_name: "case_samples",
        openclaw_workspace_ready: true,
        openclaw_bootstrap_required: true,
        openclaw_last_sync_at: "2026-03-11T00:00:00Z",
        openclaw_curated_skill_count: 1,
        google_configured: false,
        telegram_configured: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: {
          local: {},
          hybrid: {},
          cloud: {},
        },
      },
      "GET /telemetry/health": {
        ok: true,
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
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
        openclaw_bootstrap_required: true,
        openclaw_last_sync_at: "2026-03-11T00:00:00Z",
        openclaw_curated_skill_count: 1,
        recent_events: [],
      },
      "GET /workspace": {
        configured: true,
        workspace: {
          id: 1,
          office_id: "default-office",
          display_name: "case_samples",
          root_path: "/tmp/case_samples",
          root_path_hash: "abc",
          status: "active",
          created_at: "2026-03-11T00:00:00Z",
          updated_at: "2026-03-11T00:00:00Z",
        },
        documents: { items: [], count: 0 },
        scan_jobs: { items: [] },
      },
      "GET /profile": {
        office_id: "default-office",
        display_name: "Sami",
        favorite_color: "Mavi",
        food_preferences: "Burger King tercih eder.",
        transport_preference: "Tren",
        weather_preference: "Serin hava",
        travel_preferences: "",
        communication_style: "",
        assistant_notes: "",
        important_dates: [],
        related_profiles: [],
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
      "GET /assistant/onboarding/state": {
        complete: false,
        workspace_ready: true,
        provider_ready: true,
        model_ready: true,
        assistant_ready: false,
        user_ready: true,
        summary: "Persona ve kullanıcı profili sohbetle tamamlanacak.",
        next_question: "Ben nasıl bir asistan olayım?",
        interview_intro: "Asistan ilk açılışta kendi kimliğini ve sizi tanımak için soruları tek tek sorar.",
        interview_topics: [
          "Asistanın adı, tonu ve çalışma tarzı",
          "Size nasıl hitap edeceği",
        ],
        suggested_prompts: [
          "Sen kimsin ve bana nasıl yardımcı olacaksın?",
          "Ben kimim, hakkımda neleri bilmek istiyorsun?",
        ],
        profile: {
          display_name: "Sami",
          favorite_color: "Mavi",
          transport_preference: "Tren",
        },
      },
      "GET /assistant/runtime/workspace": {
        enabled: true,
        workspace_ready: true,
        bootstrap_required: true,
        last_sync_at: "2026-03-11T00:00:00Z",
        workspace_path: "/tmp/openclaw-state/workspace",
        curated_skill_count: 1,
        curated_skills: [
          {
            slug: "proactive-tasks",
            title: "Proaktif Görevler",
            summary: "Takip maddeleri ve ajanda sinyalleri.",
            enabled: true,
          },
        ],
        files: [
          {
            name: "AGENTS.md",
            path: "/tmp/openclaw-state/workspace/AGENTS.md",
            exists: true,
            preview: "# LawCopilot Runtime",
          },
        ],
        daily_log_path: "/tmp/openclaw-state/workspace/memory/daily-logs/2026-03-11.md",
      },
      "GET /assistant/tools/status": {
        items: [
          {
            provider: "gmail",
            account_label: "Google Mail",
            connected: false,
            status: "pending",
            scopes: [],
            capabilities: ["read_threads", "draft_reply", "send_after_approval"],
            write_enabled: true,
            approval_required: true,
            connected_account: null,
          },
          {
            provider: "workspace",
            account_label: "case_samples",
            connected: true,
            status: "connected",
            scopes: [],
            capabilities: ["search", "summarize", "similarity", "matter_linking"],
            write_enabled: false,
            approval_required: false,
            connected_account: null,
          },
        ],
        generated_from: "connector_registry",
      },
      "PUT /profile": (_input: RequestInfo | URL, init?: RequestInit) => {
        savedBody = String(init?.body || "");
        return {
          profile: {
            office_id: "default-office",
            display_name: "Sami",
            favorite_color: "Mavi",
            food_preferences: "Burger King tercih eder.",
            transport_preference: "Tren",
            weather_preference: "Serin hava",
            travel_preferences: "",
          communication_style: "",
          assistant_notes: "Duruşma günleri kısa özet isterim. Ankara seyahatlerinde tren önersin.",
          important_dates: [],
          related_profiles: [
            {
              id: "related-1",
              name: "Ece",
              relationship: "Eşi",
              preferences: "Deniz kenarı ve sakin planları sever.",
              notes: "Özel günleri önceden planla.",
              important_dates: [
                {
                  label: "Yıldönümü",
                  date: "2026-05-18",
                  recurring_annually: true,
                  notes: "Mesaj taslağı ve rezervasyon notu çıkar.",
                },
              ],
            },
          ],
          created_at: null,
          updated_at: "2026-03-11T00:00:00Z",
        },
        message: "Kişisel profil kaydedildi.",
      };
      },
      "PUT /assistant/runtime/profile": (_input: RequestInfo | URL, init?: RequestInit) => {
        runtimeSavedBody = String(init?.body || "");
        return {
          profile: {
            office_id: "default-office",
            assistant_name: "Hukuk Motoru",
            role_summary: "Dava odaklı hukuk çalışma asistanı",
            tone: "Sade ve net",
            avatar_path: "avatars/lawcopilot.png",
            soul_notes: "Kaynak dayanaklı ilerle.",
            tools_notes: "Google ve Telegram durumunu özetle.",
            heartbeat_extra_checks: ["Açık onay bekleyen taslakları sabah kontrol et."],
            created_at: null,
            updated_at: "2026-03-11T00:00:00Z",
          },
          message: "Asistan kimliği ve bellek ayarları kaydedildi.",
          workspace: {
            enabled: true,
            workspace_ready: true,
            bootstrap_required: false,
            last_sync_at: "2026-03-11T00:10:00Z",
            workspace_path: "/tmp/openclaw-state/workspace",
            curated_skill_count: 1,
            curated_skills: [
              {
                slug: "proactive-tasks",
                title: "Proaktif Görevler",
                summary: "Takip maddeleri ve ajanda sinyalleri.",
                enabled: true,
              },
            ],
            files: [
              {
                name: "IDENTITY.md",
                path: "/tmp/openclaw-state/workspace/IDENTITY.md",
                exists: true,
                preview: "# IDENTITY.md\n\n- Asistan adı: Hukuk Motoru",
              },
            ],
            daily_log_path: "/tmp/openclaw-state/workspace/memory/daily-logs/2026-03-11.md",
          },
        };
      },
    });

    renderApp(["/settings"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "case_samples",
        themeMode: "dark",
      },
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({
          provider: {
            type: "openai",
            baseUrl: "https://api.openai.com/v1",
            model: "gpt-4.1-mini",
            validationStatus: "pending",
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
      },
    });

    await waitFor(() => expect(screen.getAllByText(/Kişisel profil/i).length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: "Ayarları Kapat" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Asistana dön" })).toBeInTheDocument();
    expect(screen.getByText("İlk kurulum görünürlüğü")).toBeInTheDocument();
    expect(screen.getByText("Asistan ilk açılışta kendi kimliğini ve sizi tanımak için soruları tek tek sorar.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Arayüz & Tema"));
    await waitFor(() => expect(screen.getAllByText("Arayüz görünümü").length).toBeGreaterThan(0));
    expect(screen.getByRole("button", { name: /Karanlık/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Kişisel profil/i }));
    await waitFor(() => expect(screen.getByLabelText("Kendiniz ve tercihlerinizi anlatın")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Kendiniz ve tercihlerinizi anlatın"), {
      target: { value: "Duruşma günleri kısa özet isterim. Ankara seyahatlerinde tren önersin." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Profil ekle" }));
    fireEvent.change(screen.getByLabelText("İsim"), {
      target: { value: "Ece" },
    });
    fireEvent.change(screen.getByLabelText("Yakınlık / ilişki"), {
      target: { value: "Eşi" },
    });
    fireEvent.change(screen.getByLabelText("Tercihler ve sevdikleri"), {
      target: { value: "Deniz kenarı ve sakin planları sever." },
    });
    fireEvent.change(screen.getByLabelText("Notlar"), {
      target: { value: "Özel günleri önceden planla." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tarih ekle" }));
    fireEvent.change(screen.getByLabelText("Başlık"), {
      target: { value: "Yıldönümü" },
    });
    fireEvent.change(screen.getByLabelText("Tarih"), {
      target: { value: "2026-05-18" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Profili kaydet" }));

    await waitFor(() => expect(screen.getByText("Kişisel profil kaydedildi.")).toBeInTheDocument());
    expect(savedBody).toContain("Duruşma günleri kısa özet isterim.");
    expect(savedBody).toContain("\"favorite_color\":\"Mavi\"");
    expect(savedBody).toContain("\"transport_preference\":\"Tren\"");
    expect(savedBody).toContain("\"important_dates\":[]");
    expect(savedBody).toContain("\"related_profiles\":[");
    expect(savedBody).toContain("\"name\":\"Ece\"");

    await waitFor(() => expect(screen.getByLabelText("Asistan adı")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Asistan adı"), {
      target: { value: "Hukuk Motoru" },
    });
    fireEvent.change(screen.getByLabelText("Asistan nasıl davransın?"), {
      target: { value: "Kaynak dayanaklı ilerle." },
    });
    fireEvent.change(screen.getByLabelText("Araçlar ve rutinler"), {
      target: { value: "Açık onay bekleyen taslakları sabah kontrol et.\nGoogle Takvim'i kontrol et." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Asistan ayarlarını kaydet" }));

    await waitFor(() => expect(screen.getByText("Asistan kimliği ve bellek ayarları kaydedildi.")).toBeInTheDocument());
    expect(runtimeSavedBody).toContain("Hukuk Motoru");
    expect(runtimeSavedBody).toContain("Kaynak dayanaklı ilerle.");
    expect(runtimeSavedBody).toContain("Açık onay bekleyen taslakları sabah kontrol et.");
    
    expect(screen.queryByRole("button", { name: "Bağlantılar" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Kurulum" }));
    await waitFor(() => expect(screen.getAllByText("Hesaplarını bağla").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Google hesabı").length).toBeGreaterThan(0);
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Google hesabını bağla" })).toBeInTheDocument();
    expect(screen.getByText("WhatsApp")).toBeInTheDocument();
    expect(screen.getByLabelText("Kurulum metni")).toBeInTheDocument();
    expect(screen.getByLabelText("WhatsApp hat kimliği")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "WhatsApp'ı kaydet" })).toBeInTheDocument();
    expect(screen.getByText("X hesabı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "X hesabını bağla" })).toBeInTheDocument();
  });

  it("opens kurulum sekmesi directly from query params", async () => {
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
        google_configured: false,
        telegram_configured: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: { hybrid: {} },
      },
      "GET /telemetry/health": {
        ok: true,
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        release_channel: "pilot",
        environment: "pilot",
        deployment_mode: "local-only",
        desktop_shell: "electron",
        office_id: "default-office",
        structured_log_path: "artifacts/events.log.jsonl",
        audit_log_path: "artifacts/audit.log.jsonl",
        db_path: "artifacts/lawcopilot.db",
        connector_dry_run: true,
        recent_events: [],
      },
      "GET /workspace": {
        configured: false,
        workspace: null,
        documents: { items: [], count: 0 },
        scan_jobs: { items: [] },
      },
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
        related_profiles: [],
        created_at: null,
        updated_at: null,
      },
      "GET /assistant/runtime/profile": {
        office_id: "default-office",
        assistant_name: "",
        role_summary: "",
        tone: "",
        avatar_path: "",
        soul_notes: "",
        tools_notes: "",
        heartbeat_extra_checks: [],
        created_at: null,
        updated_at: null,
      },
      "GET /assistant/runtime/workspace": null,
      "GET /assistant/onboarding/state": {
        complete: false,
        workspace_ready: false,
        provider_ready: false,
        model_ready: false,
        assistant_ready: false,
        user_ready: false,
        summary: "Kurulum eksik.",
        next_question: "",
        interview_intro: "",
        interview_topics: [],
        suggested_prompts: [],
        profile: {},
      },
      "GET /assistant/tools/status": {
        items: [],
        generated_from: "connector_registry",
      },
    });

    renderApp(["/settings?tab=workspace&section=integration-google"]);

    await waitFor(() => expect(screen.getAllByText("Hesaplarını bağla").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Google hesabı").length).toBeGreaterThan(0);
  });
});
