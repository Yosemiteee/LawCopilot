import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";
import { invalidateEmbeddedPersonalModelCache } from "./PersonalModelPage";

const scrollIntoViewMock = vi.fn();

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  writable: true,
  value: scrollIntoViewMock,
});

afterEach(() => {
  cleanup();
  scrollIntoViewMock.mockClear();
  window.localStorage.clear();
  window.sessionStorage.clear();
  invalidateEmbeddedPersonalModelCache();
});

function installSettingsCoreFetches(overrides: Record<string, unknown> = {}) {
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
      favorite_color: "",
      food_preferences: "",
      transport_preference: "",
      weather_preference: "",
      travel_preferences: "",
      communication_style: "",
      assistant_notes: "",
      important_dates: [],
      related_profiles: [],
      contact_profile_overrides: [],
      created_at: null,
      updated_at: null,
    },
    "GET /assistant/personal-model": {
      generated_at: "2026-04-14T10:00:00Z",
      active_session: null,
      sessions: [],
      modules: [],
      facts: [],
      raw_entries: [],
      pending_suggestions: [],
      profile_summary: {
        fact_count: 0,
        markdown: "",
        sections: [],
        assistant_guidance: [],
      },
      usage_policy: {
        sensitive_facts_auto_used: false,
      },
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
      summary: "Temel kurulum tamamlandı.",
      next_question: "Sana nasıl hitap etmemi istersin?",
    },
    "GET /assistant/runtime/profile": {
      office_id: "default-office",
      assistant_name: "",
      role_summary: "Kullanıcının istediğine göre şekillenen çekirdek asistan",
      tone: "Net ve profesyonel",
      avatar_path: "",
      soul_notes: "",
      tools_notes: "",
      assistant_forms: [],
      behavior_contract: {
        initiative_level: "balanced",
        planning_depth: "structured",
        accountability_style: "supportive",
        follow_up_style: "check_in",
        explanation_style: "balanced",
      },
      evolution_history: [],
      heartbeat_extra_checks: [],
      created_at: null,
      updated_at: null,
    },
    "GET /assistant/runtime/core": {
      summary: {
        active_forms: 0,
        available_forms: 0,
        supports_coaching: false,
        capability_count: 0,
      },
      active_forms: [],
      available_forms: [],
      form_catalog: [],
      capability_catalog: [],
      surface_catalog: [],
      defaults: {
        role_summary: "Kullanıcının istediğine göre şekillenen çekirdek asistan",
        tone: "Net ve profesyonel",
      },
      core_summary: "",
      behavior_contract: {
        initiative_level: "balanced",
        planning_depth: "structured",
        accountability_style: "supportive",
        follow_up_style: "check_in",
        explanation_style: "balanced",
      },
      capabilities: [],
      scopes: [],
      ui_surfaces: [],
      supports_coaching: false,
      evolution_history: [],
      updated_at: null,
    },
    "GET /assistant/runtime/workspace": {
      enabled: true,
      workspace_ready: true,
      bootstrap_required: false,
      last_sync_at: "2026-03-15T00:00:00Z",
      workspace_path: "/tmp/openclaw-state/workspace",
      curated_skill_count: 0,
      curated_skills: [],
      files: [],
      daily_log_path: null,
    },
    "GET /assistant/tools/status": {
      items: [],
      generated_from: "connector_registry",
    },
    "GET /integrations/catalog": {
      items: [
        {
          connector: {
            id: "elastic",
            name: "Elastic",
            description: "Elastic veya Elasticsearch cluster baglantisi.",
            category: "search-engine",
            auth_type: "api_key",
            resources: [],
            actions: [],
            triggers: [],
            sync_policies: [],
            pagination_strategy: { type: "cursor" },
            webhook_support: { supported: false },
            rate_limit: { strategy: "unknown" },
            ui_schema: [],
            permissions: [],
            capability_flags: { read: true },
            management_mode: "platform",
            default_access_level: "read_only",
            scopes: ["indices:read", "documents:read"],
            tags: ["search"],
          },
          connections: [],
          installed: true,
          primary_status: "available",
          source: "catalog",
        },
      ],
      categories: ["search-engine"],
      security: {
        storage_posture: "sealed",
        connector_dry_run: false,
        human_review_gate: true,
        allowed_domains: [],
      },
      generated_from: "connector_registry",
    },
    ...overrides,
  });
}

describe("SettingsPage", () => {
  it("assistant profil güncellemesi geldiğinde ayarlar yüzeyini yeniden yükler", async () => {
    let profileFetchCount = 0;
    installSettingsCoreFetches({
      "GET /profile": () => {
        profileFetchCount += 1;
        return {
          office_id: "default-office",
          display_name: profileFetchCount >= 2 ? "Kenan" : "Sami",
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
        };
      },
    });

    renderApp(["/settings?tab=profil"], {
      desktop: {
        getStoredConfig: vi.fn(async () => ({})),
        getUpdateStatus: vi.fn(async () => ({})),
      },
    });

    await waitFor(() => {
      expect(profileFetchCount).toBeGreaterThanOrEqual(1);
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent("lawcopilot:memory-updates", {
        detail: {
          kinds: ["profile_signal"],
        },
      }));
    });

    await waitFor(() => {
      expect(profileFetchCount).toBeGreaterThanOrEqual(2);
    });
  });

  it("saves Gemini anahtarını hemen kaydedip arka planda backend yeniler", async () => {
    installSettingsCoreFetches();
    let resolveBackend: ((value: Record<string, unknown>) => void) | null = null;
    const validateProviderConfig = vi.fn(async () => ({
      message: "Sağlayıcı bağlantısı doğrulandı.",
      provider: {
        baseUrl: "https://generativelanguage.googleapis.com/v1beta",
        model: "gemini-2.5-flash",
        validationStatus: "valid",
        availableModels: ["gemini-2.5-flash"],
      },
    }));
    const saveIntegrationConfigFast = vi.fn(async () => ({
      provider: {
        type: "gemini",
        baseUrl: "https://generativelanguage.googleapis.com/v1beta",
        model: "gemini-2.5-flash",
        validationStatus: "valid",
        apiKeyMasked: "AIz********1234",
      },
    }));
    const ensureBackend = vi.fn(
      () =>
        new Promise<Record<string, unknown>>((resolve) => {
          resolveBackend = resolve;
        }),
    );

    renderApp(["/settings?tab=kurulum"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({
          provider: {
            type: "gemini",
            baseUrl: "https://generativelanguage.googleapis.com/v1beta",
            model: "gemini-2.5-flash",
            validationStatus: "pending",
          },
          google: { enabled: false, oauthConnected: false, validationStatus: "pending", clientIdConfigured: false },
          outlook: { enabled: false, oauthConnected: false, validationStatus: "pending", clientIdConfigured: false },
          telegram: { enabled: false, validationStatus: "pending" },
        }),
        getGoogleAuthStatus: async () => ({ configured: false, clientReady: false, scopes: [] }),
        validateProviderConfig,
        saveIntegrationConfigFast,
        ensureBackend,
      },
    });

    await waitFor(() => expect(screen.getByText("Bağlantı yönetimi")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Yapay zekâ sağlayıcısı/i }));
    await waitFor(() => expect(screen.getByLabelText("Sağlayıcı türü")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("API anahtarı"), { target: { value: "gemini-test-key" } });
    const providerSection = screen.getByLabelText("API anahtarı").closest("section") || document.body;
    fireEvent.click(within(providerSection).getByRole("button", { name: "Hesabı bağla" }));

    await waitFor(() => expect(saveIntegrationConfigFast).toHaveBeenCalled());
    expect(ensureBackend).toHaveBeenCalledWith({ forceRestart: true });
    expect(screen.getByText("Sağlayıcı anahtarı kaydedildi. Arka plan servisi yenileniyor.")).toBeInTheDocument();

    await act(async () => {
      resolveBackend?.({
        provider: {
          type: "gemini",
          baseUrl: "https://generativelanguage.googleapis.com/v1beta",
          model: "gemini-2.5-flash",
          validationStatus: "valid",
          apiKeyMasked: "AIz********1234",
          availableModels: ["gemini-2.5-flash"],
        },
      });
    });

    await waitFor(() => expect(screen.getByText("Sağlayıcı bağlandı ve kullanıma hazır.")).toBeInTheDocument());
  });

  it("allows removing a configured AI provider connection", async () => {
    installSettingsCoreFetches();
    let resolveBackend: ((value: Record<string, unknown>) => void) | null = null;
    const saveIntegrationConfigFast = vi.fn(async (patch: Record<string, unknown>) => patch);
    const ensureBackend = vi.fn(
      () =>
        new Promise<Record<string, unknown>>((resolve) => {
          resolveBackend = resolve;
        }),
    );

    renderApp(["/settings?tab=kurulum"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({
          provider: {
            type: "gemini",
            baseUrl: "https://generativelanguage.googleapis.com/v1beta",
            model: "gemini-2.5-flash",
            validationStatus: "valid",
            apiKeyMasked: "AIz********1234",
            apiKeyConfigured: true,
          },
          google: { enabled: false, oauthConnected: false, validationStatus: "pending", clientIdConfigured: false },
          outlook: { enabled: false, oauthConnected: false, validationStatus: "pending", clientIdConfigured: false },
          telegram: { enabled: false, validationStatus: "pending" },
        }),
        getGoogleAuthStatus: async () => ({ configured: false, clientReady: false, scopes: [] }),
        saveIntegrationConfigFast,
        ensureBackend,
      },
    });

    await waitFor(() => expect(screen.getByText("Bağlantı yönetimi")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Yapay zekâ sağlayıcısı/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Bağlantıyı kaldır" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kaldır" }));

    await waitFor(() => expect(saveIntegrationConfigFast).toHaveBeenCalled());
    const firstCall = saveIntegrationConfigFast.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(firstCall).toMatchObject({
      provider: expect.objectContaining({
        type: "gemini",
        apiKey: "",
        oauthConnected: false,
        validationStatus: "pending",
      }),
    });
    expect(screen.getByText("Sağlayıcı bağlantısı kaldırıldı.")).toBeInTheDocument();

    await act(async () => {
      resolveBackend?.({});
    });
  });

  it("redirects personal information edits into the unified personal knowledge page", async () => {
    installSettingsCoreFetches({
      "GET /assistant/contact-profiles": {
        items: [
          {
            id: "person:baran",
            kind: "person",
            display_name: "Baran",
            relationship_hint: "İletişim kişisi",
            persona_summary: "Birden fazla kanalda görülen iletişim profili.",
            channels: ["email", "whatsapp"],
            emails: ["baran@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: true,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-03-11T00:00:00Z",
            source_count: 2,
          },
        ],
        generated_from: "assistant_contact_profiles",
      },
    });

    renderApp(["/settings?tab=iletisim"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "case_samples",
      },
    });

    await waitFor(() => expect(screen.getByRole("heading", { name: "İletişim ve bildirim kuralları" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Kuralları kaydet" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "İletişim rehberi" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "İzlenen Kişi ve Gruplar" })).toBeInTheDocument();
  });

  it("profil sekmesinde kişisel bilgileri doğrudan gösterir", async () => {
    installSettingsCoreFetches({
      "GET /profile": {
        office_id: "default-office",
        display_name: "Sami",
        favorite_color: "Mavi",
        food_preferences: "",
        transport_preference: "Tren",
        weather_preference: "",
        travel_preferences: "",
        home_base: "İstanbul / Kadıköy",
        current_location: "",
        location_preferences: "",
        maps_preference: "Google Maps",
        prayer_notifications_enabled: false,
        prayer_habit_notes: "",
        communication_style: "",
        assistant_notes: "Sevdiği renk: Mavi.\nAna yaşam / dönüş noktası: İstanbul / Kadıköy.\nDuruşma günleri kısa özet isterim.",
        important_dates: [],
        related_profiles: [],
        inbox_watch_rules: [],
        inbox_keyword_rules: [],
        inbox_block_rules: [],
        created_at: null,
        updated_at: null,
      },
      "GET /assistant/contact-profiles": {
        items: [],
        generated_from: "assistant_contact_profiles",
      },
    });

    renderApp(["/settings?tab=profil"]);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Profil" })).toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "Hitap / isim" })).toHaveValue("Sami");
    expect(screen.getByRole("textbox", { name: "Ana yaşam noktası" })).toHaveValue("İstanbul / Kadıköy");
    expect(screen.getByRole("combobox", { name: "Harita tercihi" })).toHaveValue("Google Maps");
    expect(screen.queryByRole("heading", { name: "İletişim rehberi" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Yakın kişiler" })).not.toBeInTheDocument();
  });

  it("iletişim rehberinden kişiyi yakın kişiler listesine ekleyip yakınlık derecesiyle kaydeder", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    installSettingsCoreFetches({
      "GET /assistant/contact-profiles": {
        items: [
          {
            id: "person:baran",
            kind: "person",
            display_name: "Baran",
            relationship_hint: "Arkadaş",
            related_profile_id: null,
            closeness: null,
            persona_summary: "WhatsApp ve e-postada sık görülen kişi.",
            channels: ["email", "whatsapp"],
            emails: ["baran@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-03-11T00:00:00Z",
            source_count: 2,
          },
        ],
        generated_from: "assistant_contact_profiles",
      },
      "PUT /profile": (_input: RequestInfo | URL, init?: RequestInit) => {
        capturedBody = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        return {
          profile: {
            office_id: "default-office",
            display_name: "Sami",
            favorite_color: "",
            food_preferences: "",
            transport_preference: "",
            weather_preference: "",
            travel_preferences: "",
            home_base: "",
            current_location: "",
            location_preferences: "",
            maps_preference: "Google Maps",
            prayer_notifications_enabled: false,
            prayer_habit_notes: "",
            communication_style: "",
            assistant_notes: "",
            important_dates: [],
            related_profiles: (capturedBody?.related_profiles as unknown[]) || [],
            inbox_watch_rules: [],
            inbox_keyword_rules: [],
            inbox_block_rules: [],
            source_preference_rules: [],
            created_at: null,
            updated_at: null,
          },
          profile_reconciliation: {
            authority: "profile",
            authority_model: "predicate_family_split",
            changed: true,
            synced_facts: [],
            settings_fields: [],
            claim_projection_fields: [],
          },
        };
      },
    });

    renderApp(["/settings?tab=iletisim"]);

    await waitFor(() => expect(screen.getByRole("heading", { name: "İletişim rehberi" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("Baran").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Yakın kişilere ekle" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Yakın kişiler" })).toBeInTheDocument());
    expect(screen.getAllByText("Baran").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByRole("combobox", { name: "Baran yakınlık derecesi" }), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Kuralları kaydet" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    const payload = capturedBody as { related_profiles?: Array<Record<string, unknown>> } | null;
    const relatedProfiles = payload?.related_profiles || [];
    expect(relatedProfiles[0]?.name).toBe("Baran");
    expect(relatedProfiles[0]?.relationship).toBe("Arkadaş");
    expect(relatedProfiles[0]?.closeness).toBe(4);
  });

  it("iletişim açıklamasını düzenleyip profile kaydeder", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    installSettingsCoreFetches({
      "GET /assistant/contact-profiles": {
        items: [
          {
            id: "person:baran",
            kind: "person",
            display_name: "Baran",
            relationship_hint: "Arkadaş",
            related_profile_id: null,
            closeness: null,
            persona_summary: "WhatsApp ve e-postada sık görülen kişi.",
            persona_detail: "Mesaj geçmişinden oluşan ilk açıklama.",
            generated_persona_detail: "Mesaj geçmişinden oluşan ilk açıklama.",
            persona_detail_source: "generated",
            channels: ["email", "whatsapp"],
            emails: ["baran@example.com"],
            phone_numbers: [],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-03-11T00:00:00Z",
            source_count: 2,
          },
        ],
        generated_from: "assistant_contact_profiles",
      },
      "PUT /profile": (_input: RequestInfo | URL, init?: RequestInit) => {
        capturedBody = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        return {
          profile: {
            office_id: "default-office",
            display_name: "Sami",
            favorite_color: "",
            food_preferences: "",
            transport_preference: "",
            weather_preference: "",
            travel_preferences: "",
            home_base: "",
            current_location: "",
            location_preferences: "",
            maps_preference: "Google Maps",
            prayer_notifications_enabled: false,
            prayer_habit_notes: "",
            communication_style: "",
            assistant_notes: "",
            important_dates: [],
            related_profiles: [],
            contact_profile_overrides: (capturedBody?.contact_profile_overrides as unknown[]) || [],
            inbox_watch_rules: [],
            inbox_keyword_rules: [],
            inbox_block_rules: [],
            source_preference_rules: [],
            created_at: null,
            updated_at: null,
          },
          profile_reconciliation: {
            authority: "profile",
            authority_model: "predicate_family_split",
            changed: true,
            synced_facts: [],
            settings_fields: [],
            claim_projection_fields: [],
          },
        };
      },
    });

    renderApp(["/settings?tab=iletisim"]);

    await waitFor(() => expect(screen.getByText("Mesaj geçmişinden oluşan ilk açıklama.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Baran açıklaması" }), {
      target: { value: "Baran ile iş ve plan koordinasyonunu buradan takip ediyoruz." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({
      contact_profile_overrides: [
        expect.objectContaining({
          contact_id: "person:baran",
          description: "Baran ile iş ve plan koordinasyonunu buradan takip ediyoruz.",
        }),
      ],
    });
    expect(screen.getByText("Baran ile iş ve plan koordinasyonunu buradan takip ediyoruz.")).toBeInTheDocument();
    expect(screen.getByText("Açıklama elle düzenlendi")).toBeInTheDocument();
  });

  it("iletişim kartında çıkarılan notlar, tercihler ve son örneği gösterir", async () => {
    installSettingsCoreFetches({
      "GET /assistant/contact-profiles": {
        items: [
          {
            id: "person:abla",
            kind: "person",
            display_name: "Ablam",
            relationship_hint: "Kardeş",
            related_profile_id: null,
            closeness: null,
            persona_summary: "WhatsApp üzerinden sık görülen kişi.",
            persona_detail: "Açıklama 5 mesaj örneğine dayanıyor.",
            generated_persona_detail: "Açıklama 5 mesaj örneğine dayanıyor.",
            persona_detail_source: "generated",
            channels: ["whatsapp"],
            emails: [],
            phone_numbers: ["905555555555"],
            handles: [],
            watch_enabled: false,
            blocked: false,
            blocked_until: null,
            last_message_at: "2026-03-11T00:00:00Z",
            source_count: 5,
            inference_signals: [
              "Mesajların çoğu kısa ve hızlı ilerliyor; daha çok anlık koordinasyon ve tepki dili var.",
              "Planlama, saat, buluşma ve günlük koordinasyon dili baskın görünüyor.",
            ],
            preference_signals: [],
            gift_ideas: [],
            last_inbound_preview: "Yarın saat 7 gibi çıkar mısın?",
          },
        ],
        generated_from: "assistant_contact_profiles",
      },
    });

    renderApp(["/settings?tab=iletisim"]);

    await waitFor(() => expect(screen.getByText("Çıkarılan notlar")).toBeInTheDocument());
    expect(screen.getByText("Tercihler ve sevdikleri")).toBeInTheDocument();
    expect(screen.getByText("Bu kişi için henüz güçlü tercih sinyali çıkmadı.")).toBeInTheDocument();
    expect(screen.getByText("Son mesaj örneği")).toBeInTheDocument();
    expect(screen.getByText("Yarın saat 7 gibi çıkar mısın?")).toBeInTheDocument();
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
        outlook_configured: false,
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

    renderApp(["/settings?tab=kurulum&section=integration-google"]);

    await waitFor(() => expect(screen.getAllByText("Bağlantı yönetimi").length).toBeGreaterThan(0));
    expect(screen.getByText("Bağlantıları burada yönetin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /E-posta ve takvim/i, expanded: true })).toBeInTheDocument();
    expect(screen.getByText("Masaüstü uygulaması gerekli")).toBeInTheDocument();
    expect(screen.queryByText("Çalışma modu")).not.toBeInTheDocument();
    expect(screen.queryByText("Varsayılan model profili")).not.toBeInTheDocument();
  });

  it("explains that local workspace files need no extra data-source setup and only surfaces Elastic here", async () => {
    installSettingsCoreFetches();

    renderApp(["/settings?tab=kurulum"]);

    await waitFor(() => expect(screen.getAllByText("Bağlantı yönetimi").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: /Veri kaynaklari/i }));

    await waitFor(() => expect(screen.getByText("Yerel klasor icin ek kurulum gerekmez")).toBeInTheDocument());
    expect(screen.getByText("Elastic Cloud veya self-hosted Elasticsearch cluster bağlayın.")).toBeInTheDocument();
    expect(screen.getByLabelText("Elastic Cloud ID")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Elastic bağlantısını kaydet" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "PostgreSQL kurulumunu ac" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "MySQL kurulumunu ac" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "SQL Server kurulumunu ac" })).not.toBeInTheDocument();
  });

  it("does not jump back to the query-targeted setup section after the first guided scroll", async () => {
    const requestAnimationFrameSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    const cancelAnimationFrameSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const desktop = {
      getIntegrationConfig: vi.fn(async () => ({
        provider: {
          type: "openai",
          baseUrl: "https://api.openai.com/v1",
          model: "gpt-5.4",
          validationStatus: "pending",
          availableModels: ["gpt-5.4"],
        },
        google: {
          enabled: false,
          oauthConnected: false,
          clientIdConfigured: false,
          clientSecretConfigured: false,
          scopes: [],
          validationStatus: "pending",
        },
        outlook: {
          enabled: false,
          oauthConnected: false,
          clientIdConfigured: false,
          scopes: [],
          validationStatus: "pending",
        },
      })),
      getGoogleAuthStatus: vi.fn(async () => ({ configured: false, message: "" })),
      getOutlookAuthStatus: vi.fn(async () => ({ configured: false, message: "" })),
    };

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
        outlook_configured: false,
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

    renderApp(["/settings?tab=kurulum&section=integration-google"], { desktop });

    try {
      await waitFor(() => expect(screen.getByRole("button", { name: /E-posta ve takvim/i, expanded: true })).toBeInTheDocument());
      await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledTimes(1));

      fireEvent.click(screen.getByRole("button", { name: /Mesajlaşma/i }));

      await waitFor(() => expect(screen.getAllByText("Telegram").length).toBeGreaterThan(0));
      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
    } finally {
      requestAnimationFrameSpy.mockRestore();
      cancelAnimationFrameSpy.mockRestore();
    }
  });

  it("shows Telegram personal web session controls in setup", async () => {
    installSettingsCoreFetches();

    renderApp(["/settings?tab=kurulum&section=integration-telegram"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({
          workspaceRootPath: "/tmp/case_samples",
          workspaceRootName: "case_samples",
          scanOnStartup: true,
          locale: "tr",
        }),
        getIntegrationConfig: async () => ({
          telegram: {
            enabled: false,
            mode: "bot",
            validationStatus: "pending",
          },
        }),
      },
    });

    await waitFor(() => expect(screen.getByRole("button", { name: /Mesajlaşma/i, expanded: true })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Kişisel web oturumu" }));

    expect(screen.getByRole("button", { name: "Telegram Web oturumunu aç" })).toBeEnabled();
    expect(screen.getByText("Giriş yardımı")).toBeInTheDocument();
    expect(screen.getAllByText(/Masaüstü cihaz bağla/i).length).toBeGreaterThan(0);
  });

  it("shows a clear success state after choosing a workspace folder", async () => {
    let workspaceConfigured = false;
    const desktop = {
      getRuntimeInfo: async () => ({}),
      getStoredConfig: async () => ({}),
      getWorkspaceConfig: async () => ({
        workspaceRootPath: workspaceConfigured ? "/tmp/musteri-dosyalari" : "",
        workspaceRootName: workspaceConfigured ? "Musteri Dosyalari" : "",
        workspaceRootHash: workspaceConfigured ? "hash-123" : "",
        scanOnStartup: true,
        locale: "tr",
      }),
      chooseWorkspaceRoot: vi.fn(async () => {
        workspaceConfigured = true;
        return {
          canceled: false,
          workspace: {
            workspaceRootPath: "/tmp/musteri-dosyalari",
            workspaceRootName: "Musteri Dosyalari",
            workspaceRootHash: "hash-123",
          },
        };
      }),
    };

    installFetchMock({
      "GET /health": () => ({
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-first-hybrid",
        release_channel: "pilot",
        connector_dry_run: true,
        workspace_configured: workspaceConfigured,
        workspace_root_name: workspaceConfigured ? "Musteri Dosyalari" : "",
        google_configured: true,
        outlook_configured: false,
        telegram_configured: false,
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      }),
      "GET /telemetry/health": {
        ok: true,
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        release_channel: "pilot",
        environment: "pilot",
        deployment_mode: "local-first-hybrid",
        desktop_shell: "electron",
        office_id: "default-office",
        structured_log_path: "artifacts/events.log.jsonl",
        audit_log_path: "artifacts/audit.log.jsonl",
        db_path: "artifacts/lawcopilot.db",
        connector_dry_run: true,
        recent_events: [],
      },
      "GET /workspace": () => (
        workspaceConfigured
          ? {
              configured: true,
              workspace: {
                id: 1,
                office_id: "default-office",
                display_name: "Musteri Dosyalari",
                root_path: "/tmp/musteri-dosyalari",
                root_path_hash: "hash-123",
                status: "active",
                created_at: "2026-03-11T00:00:00Z",
                updated_at: "2026-03-11T00:00:00Z",
              },
              documents: { items: [], count: 0 },
              scan_jobs: { items: [] },
            }
          : {
              configured: false,
              workspace: null,
              documents: { items: [], count: 0 },
              scan_jobs: { items: [] },
            }
      ),
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
        workspace_ready: workspaceConfigured,
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

    renderApp(["/settings?tab=kurulum"], { desktop });

    await waitFor(() => expect(screen.getAllByText("Çalışma klasörü erişimi").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "Çalışma klasörü seç" })[0]);

    await waitFor(() => expect(screen.getByText("Çalışma klasörü bağlandı: Musteri Dosyalari.")).toBeInTheDocument());
    expect(screen.getAllByText("/tmp/musteri-dosyalari").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bilgisayarınızdaki çalışma klasörü ile bağladığınız Drive, Mail ve Takvim hesapları aynı çalışma düzeninde birlikte kullanılır.").length).toBeGreaterThan(0);
  });

  it("shows desktop update controls and saves updater configuration", async () => {
    const saveStoredConfig = vi.fn(async (patch: Record<string, unknown>) => ({
      updater: {
        enabled: true,
        feedUrl: String((patch.updater as Record<string, unknown> | undefined)?.feedUrl || ""),
        channel: String((patch.updater as Record<string, unknown> | undefined)?.channel || "latest"),
        autoCheckOnLaunch: true,
        autoDownload: false,
        allowPrerelease: true,
      },
    }));
    const checkForUpdates = vi.fn(async () => ({
      status: "available",
      configured: true,
      supported: true,
      current_version: "0.7.0-pilot.1",
      available_version: "0.8.0-pilot.1",
      downloaded_version: "",
      channel: "pilot",
      feed_url: "https://updates.example.com/lawcopilot",
      auto_check_on_launch: true,
      auto_download: false,
      allow_prerelease: true,
      last_checked_at: "2026-04-11T10:00:00Z",
      last_error: "",
      release_notes: "Yeni sürüm hazır.",
      download_percent: 0,
    }));
    const desktop = {
      getStoredConfig: async () => ({
        updater: {
          enabled: true,
          feedUrl: "https://updates.example.com/lawcopilot",
          channel: "pilot",
          autoCheckOnLaunch: true,
          autoDownload: false,
          allowPrerelease: true,
        },
      }),
      saveStoredConfig,
      getUpdateStatus: async () => ({
        status: "idle",
        configured: true,
        supported: true,
        current_version: "0.7.0-pilot.1",
        available_version: "",
        downloaded_version: "",
        channel: "pilot",
        feed_url: "https://updates.example.com/lawcopilot",
        auto_check_on_launch: true,
        auto_download: false,
        allow_prerelease: true,
        last_checked_at: "",
        last_error: "",
        release_notes: "",
        download_percent: 0,
      }),
      checkForUpdates,
      onUpdateStatus: vi.fn(() => () => {}),
    };

    installFetchMock({
      "GET /health": {
        ok: true,
        service: "lawcopilot-api",
        app_name: "LawCopilot",
        version: "0.7.0-pilot.1",
        office_id: "default-office",
        deployment_mode: "local-first-hybrid",
        release_channel: "pilot",
        connector_dry_run: true,
        workspace_configured: true,
        workspace_root_name: "case_samples",
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
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
    });

    renderApp(["/settings?tab=kurulum"], { desktop });

    await screen.findByText("Masaüstü uygulama sürümü");
    expect(screen.queryByRole("button", { name: "Güncellemeyi indir" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yeniden başlat ve kur" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Teknik ayarları göster"));
    fireEvent.click(screen.getByText("Sunucu ayrıntılarını göster"));
    const updateUrlInput = screen.getByPlaceholderText("https://updates.ornek.com/lawcopilot");
    fireEvent.change(updateUrlInput, { target: { value: "https://updates.example.com/lawcopilot" } });
    fireEvent.click(screen.getByRole("button", { name: "Güncelleme ayarlarını kaydet" }));

    await waitFor(() => expect(saveStoredConfig).toHaveBeenCalledWith(expect.objectContaining({
      updater: expect.objectContaining({
        feedUrl: "https://updates.example.com/lawcopilot",
      }),
    })));

    fireEvent.click(screen.getByRole("button", { name: "Yeni sürümü kontrol et" }));
    await waitFor(() => expect(checkForUpdates).toHaveBeenCalled());
    await screen.findByText("Bulunan sürüm: 0.8.0-pilot.1");
    await screen.findByText("Güncelleme var");
    await screen.findByRole("button", { name: "Güncellemeyi indir" });
    expect(screen.queryByRole("button", { name: "Yeniden başlat ve kur" })).not.toBeInTheDocument();
    expect(screen.getByText("Bulunan sürüm: 0.8.0-pilot.1")).toBeInTheDocument();
  });

  it("keeps Outlook client fields visible after saving so the user can correct a wrong client ID", async () => {
    installSettingsCoreFetches();
    const saveIntegrationConfig = vi.fn(async (patch: Record<string, unknown>) => patch);
    const startOutlookAuth = vi.fn(async () => ({
      configured: false,
      clientReady: true,
      clientId: "correct-client-id",
      tenantId: "common",
      scopes: [],
      message: "Outlook hesabı henüz bağlanmadı.",
    }));

    renderApp(["/settings?tab=kurulum"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({}),
        getWorkspaceConfig: async () => ({}),
        getIntegrationConfig: async () => ({
          provider: {
            type: "openai",
            baseUrl: "https://api.openai.com/v1",
            model: "gpt-5.4",
            validationStatus: "pending",
            availableModels: ["gpt-5.4"],
          },
          google: { enabled: false, oauthConnected: false, validationStatus: "pending", clientIdConfigured: false },
          outlook: {
            enabled: false,
            oauthConnected: false,
            validationStatus: "pending",
            clientIdConfigured: true,
            clientId: "wrong-client-id",
            tenantId: "common",
            scopes: [],
          },
        }),
        getGoogleAuthStatus: async () => ({ configured: false, message: "" }),
        getOutlookAuthStatus: async () => ({ configured: false, clientReady: true, clientId: "wrong-client-id", tenantId: "common", scopes: [], message: "" }),
        saveIntegrationConfig,
        startOutlookAuth,
      },
    });

    await waitFor(() => expect(screen.getByText("Bağlantı yönetimi")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /E-posta ve takvim/i }));

    const clientIdInput = await screen.findByLabelText("Outlook istemci kimliği");
    expect(clientIdInput).toHaveValue("wrong-client-id");
    fireEvent.change(clientIdInput, { target: { value: "correct-client-id" } });

    expect(screen.getByLabelText("Tenant kimliği")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bağlantıyı güncelle" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Outlook hesabını bağla" }));

    await waitFor(() => expect(saveIntegrationConfig).toHaveBeenCalledWith({
      outlook: {
        clientId: "correct-client-id",
        tenantId: "common",
      },
    }));
    await waitFor(() => expect(startOutlookAuth).toHaveBeenCalled());
    expect(screen.getByLabelText("Outlook istemci kimliği")).toHaveValue("correct-client-id");
  });

  it("lets the user edit and save reminder automation rules manually", async () => {
    installSettingsCoreFetches();
    const saveStoredConfig = vi.fn(async (patch: Record<string, unknown>) => patch);

    renderApp(["/settings?tab=automation"], {
      desktop: {
        getRuntimeInfo: async () => ({}),
        getStoredConfig: async () => ({
          automation: {
            enabled: true,
            autoSyncConnectedServices: true,
            desktopNotifications: true,
            automationRules: [
              {
                id: "rule-water",
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
            ],
          },
        }),
        saveStoredConfig,
      },
    });

    await screen.findByDisplayValue("Su iç");
    fireEvent.change(screen.getByLabelText("Kısa başlık"), { target: { value: "Su içmeyi unutma" } });
    fireEvent.change(screen.getByLabelText("Açıklama"), { target: { value: "12 50 de su içmeyi hatırlat" } });
    fireEvent.change(screen.getByDisplayValue("2026-04-17T12:48"), { target: { value: "2026-04-17T12:50" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Aktif" }));
    fireEvent.click(screen.getByRole("button", { name: "Otomasyonu kaydet" }));

    await waitFor(() => expect(saveStoredConfig).toHaveBeenCalledWith(expect.objectContaining({
      automation: expect.objectContaining({
        enabled: true,
        automationRules: [
          expect.objectContaining({
            id: "rule-water",
            summary: "Su içmeyi unutma",
            instruction: "12 50 de su içmeyi hatırlat",
            reminder_at: "2026-04-17T12:50:00+03:00",
            active: false,
          }),
        ],
      }),
    })));
  });

});
