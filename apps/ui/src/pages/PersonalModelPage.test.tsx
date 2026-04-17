import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("PersonalModelPage", () => {
  it("assistant profil sinyali geldiğinde profil yüzeyini yeniden yükler", async () => {
    let overviewFetchCount = 0;
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
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/personal-model": () => {
        overviewFetchCount += 1;
        return {
          generated_at: "2026-04-16T12:00:00Z",
          active_session: null,
          sessions: [],
          modules: [],
          facts: [],
          raw_entries: [],
          pending_suggestions: [],
          profile_summary: {
            fact_count: 0,
            markdown: overviewFetchCount >= 2 ? "# Bana Dair\n\n- Güncellendi" : "# Bana Dair",
            sections: [],
            assistant_guidance: [],
          },
          usage_policy: {},
        };
      },
      "GET /profile": {
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
        inbox_watch_rules: [],
        inbox_keyword_rules: [],
        inbox_block_rules: [],
        source_preference_rules: [],
        created_at: null,
        updated_at: null,
      },
    });

    renderApp(["/personal-model"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => {
      expect(overviewFetchCount).toBeGreaterThanOrEqual(1);
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent("lawcopilot:memory-updates", {
        detail: {
          kinds: ["profile_signal"],
        },
      }));
    });

    await waitFor(() => {
      expect(overviewFetchCount).toBeGreaterThanOrEqual(2);
    });
  });

  it("surfaces learned profile highlights from connected accounts near the top", async () => {
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
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/personal-model": {
        generated_at: "2026-04-16T12:00:00Z",
        active_session: null,
        sessions: [],
        modules: [],
        facts: [
          {
            id: "pmf-career",
            category: "career",
            fact_key: "career.profile_summary",
            title: "Profesyonel profil",
            value_text: "Python, FastAPI ve PostgreSQL tarafı belirgin.",
            confidence: 0.81,
            confidence_type: "inferred",
            scope: "global",
            sensitive: false,
            enabled: true,
            never_use: false,
            source_summary: "Bağlı hesaplardan gözlemlendi: Gmail e-postası, Belge: cv-sami.pdf",
            metadata: { source_kind: "connector_profile_learning" },
          },
        ],
        raw_entries: [],
        pending_suggestions: [],
        profile_summary: {
          fact_count: 1,
          markdown: "# Bana Dair\n\n## Profesyonel Profil\n- Profesyonel profil: Python, FastAPI ve PostgreSQL tarafı belirgin.",
          sections: [],
          assistant_guidance: [],
        },
        usage_policy: {},
      },
      "GET /profile": {
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
        inbox_watch_rules: [],
        inbox_keyword_rules: [],
        inbox_block_rules: [],
        source_preference_rules: [],
        created_at: null,
        updated_at: null,
      },
    });

    renderApp(["/personal-model"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    expect(await screen.findByText("Şu ana kadar senden öğrendiklerim")).toBeInTheDocument();
    expect(screen.getByText("Python, FastAPI ve PostgreSQL tarafı belirgin.")).toBeInTheDocument();
    expect(screen.getByText(/Gmail e-postası/i)).toBeInTheDocument();
  });

  it("runs interview, updates facts, reviews suggestions, and previews retrieval", async () => {
    const overviewPayload = {
      generated_at: "2026-04-11T12:00:00Z",
      active_session: null,
      sessions: [],
      modules: [
        {
          key: "communication",
          title: "Communication",
          description: "Ton ve yazım tercihleri",
          question_count: 2,
          answered_count: 0,
          complete: false,
        },
      ],
      facts: [
        {
          id: "pmf-1",
          category: "communication",
          fact_key: "communication.style",
          title: "İletişim tonu",
          value_text: "Kısa ve net",
          confidence: 0.98,
          confidence_type: "explicit",
          scope: "personal",
          sensitive: false,
          enabled: true,
          never_use: false,
          metadata: {},
        },
      ],
      raw_entries: [],
      pending_suggestions: [
        {
          id: "pmsug-1",
          title: "Sohbetten olası tercih",
          prompt: "Şunu hatırlamamı ister misin?",
          proposed_value_text: "Gece çalışmayı seviyorum.",
          confidence: 0.68,
          confidence_label: "Bu çıkarımdan %68 eminiz.",
          scope: "personal",
          status: "pending",
          evidence: {},
          learning_reason: "Mesajından gece çalışmayı sevdiğini anlamış olabilirim.",
          why_asked: "Kalıcı hale getirmeden önce onayını istiyoruz.",
          metadata: {},
        },
      ],
      profile_summary: {
        fact_count: 1,
        markdown: "# Benim Bilgilerim\n\n## İletişim\n- İletişim tonu: Kısa ve net",
        sections: [],
        assistant_guidance: [],
      },
      usage_policy: {
        sensitive_facts_auto_used: false,
      },
    };

    const activeOverviewPayload = {
      ...overviewPayload,
      active_session: {
        id: "pms-1",
        scope: "personal",
        status: "active",
        progress: { answered: 0, skipped: 0, total: 2 },
        current_question: {
          id: "communication_style",
          module_key: "communication",
          prompt: "Benim sana yazarken nasıl bir ton kullanmamı istersin?",
          title: "İletişim tonu",
          input_mode: "choice",
          choices: [
            { value: "concise", label: "Kısa ve net" },
            { value: "balanced", label: "Dengeli" },
          ],
          skippable: true,
        },
      },
    };

    const answeredOverviewPayload = {
      ...overviewPayload,
      raw_entries: [
        {
          id: 11,
          question_text: "Benim sana yazarken nasıl bir ton kullanmamı istersin?",
          answer_text: "Kısa ve net",
          source: "interview",
          confidence_type: "explicit",
          created_at: "2026-04-11T12:10:00Z",
        },
      ],
      facts: [
        {
          id: "pmf-1",
          category: "communication",
          fact_key: "communication.style",
          title: "İletişim tonu",
          value_text: "Kısa ve net",
          confidence: 0.98,
          confidence_type: "explicit",
          scope: "personal",
          sensitive: false,
          enabled: true,
          never_use: false,
          metadata: {},
        },
      ],
      pending_suggestions: overviewPayload.pending_suggestions,
    };

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
        rag_backend: "inmemory",
        rag_runtime: { backend: "inmemory", mode: "default" },
      },
      "GET /assistant/personal-model": overviewPayload,
      "GET /profile": {
        office_id: "default-office",
        display_name: "Sami",
        favorite_color: "Lacivert",
        food_preferences: "Sessiz kahveciler",
        transport_preference: "Tren",
        weather_preference: "Serin hava",
        travel_preferences: "Akşam seferlerini seviyorum.",
        home_base: "İstanbul / Kadıköy",
        current_location: "Kadıköy",
        location_preferences: "Yakın ve sakin yerler",
        maps_preference: "Google Maps",
        prayer_notifications_enabled: false,
        prayer_habit_notes: "",
        communication_style: "Kısa ve net",
        assistant_notes: "Önemli tarihlerde erken haber ver.",
        important_dates: [],
        related_profiles: [],
        inbox_watch_rules: [],
        inbox_keyword_rules: [],
        inbox_block_rules: [],
        source_preference_rules: [],
        created_at: null,
        updated_at: null,
      },
      "PUT /profile": (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body || "{}"));
        return {
          profile: {
            office_id: "default-office",
            display_name: String(payload.display_name || "Sami"),
            favorite_color: String(payload.favorite_color || ""),
            food_preferences: String(payload.food_preferences || ""),
            transport_preference: String(payload.transport_preference || ""),
            weather_preference: String(payload.weather_preference || ""),
            travel_preferences: String(payload.travel_preferences || ""),
            home_base: String(payload.home_base || ""),
            current_location: String(payload.current_location || ""),
            location_preferences: String(payload.location_preferences || ""),
            maps_preference: String(payload.maps_preference || "Google Maps"),
            prayer_notifications_enabled: Boolean(payload.prayer_notifications_enabled),
            prayer_habit_notes: String(payload.prayer_habit_notes || ""),
            communication_style: String(payload.communication_style || ""),
            assistant_notes: String(payload.assistant_notes || ""),
            important_dates: payload.important_dates || [],
            related_profiles: payload.related_profiles || [],
            inbox_watch_rules: [],
            inbox_keyword_rules: [],
            inbox_block_rules: [],
            source_preference_rules: payload.source_preference_rules || [],
            created_at: null,
            updated_at: null,
          },
          message: "Bilgiler kaydedildi.",
          profile_reconciliation: {
            changed: true,
            authority_model: "predicate_family_split",
            claim_projection_fields: [{ field: "communication_style", title: "iletişim tonu" }],
            settings_fields: [{ field: "maps_preference", title: "harita tercihi" }],
            synced_facts: [],
            hydrated_fields: [],
          },
        };
      },
      "POST /assistant/personal-model/interviews/start": {
        session: activeOverviewPayload.active_session,
        overview: activeOverviewPayload,
      },
      "POST /assistant/personal-model/interviews/pms-1/answer": {
        session: {
          ...activeOverviewPayload.active_session,
          progress: { answered: 1, skipped: 0, total: 2 },
          current_question: null,
        },
        raw_entry: answeredOverviewPayload.raw_entries[0],
        stored_facts: [answeredOverviewPayload.facts[0]],
        next_question: null,
        profile_summary: answeredOverviewPayload.profile_summary,
        profile_reconciliation: {
          changed: true,
          authority: "fact",
          hydrated_fields: [{ field: "communication_style", fact_key: "communication.style", direction: "fact_to_profile" }],
          synced_facts: [],
        },
        overview: answeredOverviewPayload,
      },
      "PUT /assistant/personal-model/facts/pmf-1": {
        fact: {
          ...answeredOverviewPayload.facts[0],
          value_text: "Kısa, sıcak ve direkt",
          profile_reconciliation: {
            changed: true,
            authority: "fact",
            hydrated_fields: [{ field: "communication_style", fact_key: "communication.style", direction: "fact_to_profile" }],
            synced_facts: [],
          },
        },
        overview: {
          ...answeredOverviewPayload,
          facts: [
            {
              ...answeredOverviewPayload.facts[0],
              value_text: "Kısa, sıcak ve direkt",
            },
          ],
        },
      },
      "POST /assistant/personal-model/suggestions/pmsug-1/review": {
        decision: "accepted",
        fact: {
          id: "pmf-2",
          category: "preferences",
          fact_key: "user.preference.general",
          title: "Sohbetten olası tercih",
          value_text: "Gece çalışmayı seviyorum.",
        },
        profile_reconciliation: {
          changed: true,
          authority: "fact",
          hydrated_fields: [{ field: "transport_preference", fact_key: "transport.preference", direction: "fact_to_profile" }],
          synced_facts: [],
        },
        overview: answeredOverviewPayload,
      },
      "POST /assistant/personal-model/retrieval/preview": {
        query: "Bugün planımı nasıl yönetmeliyim?",
        intent: { name: "planning", categories: ["goals", "routines"] },
        selected_categories: ["goals", "routines"],
        usage_note: "Yalnız ilgili bilgiler kullanıldı.",
        assistant_context_pack: [
          {
            id: "pm:pmf-1",
            family: "personal_model",
            title: "İletişim tonu",
            summary: "Kısa, sıcak ve direkt",
            scope: "personal",
            freshness: "stable",
            assistant_visibility: "visible",
            why_visible: "Kullanıcı tarafından verilmiş ve bu istekte ilgili.",
          },
        ],
        summary_lines: ["- [communication] İletişim tonu: Kısa, sıcak ve direkt"],
        facts: [
          {
            id: "pmf-1",
            title: "İletişim tonu",
            value_text: "Kısa, sıcak ve direkt",
            selection_reasons: ["explicit_memory"],
            selection_reason_labels: ["Bunu sen açıkça söyledin"],
          },
        ],
      },
    });

    renderApp(["/personal-model"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText("Benim Bilgilerim")).toBeInTheDocument());
    expect(screen.getAllByText(/kişisel bilgi merkezi/i).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByDisplayValue("Sami"), { target: { value: "Samet" } });
    fireEvent.click(screen.getByRole("button", { name: "Bilgileri kaydet" }));
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/profile" && String(init?.method || "GET").toUpperCase() === "PUT";
      });
      expect(saveCall).toBeTruthy();
    });
    expect(screen.getByText("Bilgiler kaydedildi.")).toBeInTheDocument();
    expect(screen.getByText("Profil eşitlemesi")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Buradan başla" }));
    await waitFor(() => expect(screen.getByText(/Benim sana yazarken nasıl bir ton kullanmamı istersin/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Kısa ve net" }));
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() => {
      const answerCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/assistant/personal-model/interviews/pms-1/answer" && String(init?.method || "GET").toUpperCase() === "POST";
      });
      expect(answerCall).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Öğrenilmiş bilgiler" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Öğrenilmiş Bilgiler" })).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue("Kısa ve net"), { target: { value: "Kısa, sıcak ve direkt" } });
    fireEvent.click(screen.getByRole("button", { name: "Düzelt" }));

    await waitFor(() => {
      const updateCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/assistant/personal-model/facts/pmf-1" && String(init?.method || "GET").toUpperCase() === "PUT";
      });
      expect(updateCall).toBeTruthy();
    });
    expect(screen.getByText("Profil eşitlemesi")).toBeInTheDocument();
    expect(screen.getByText("iletişim tonu profile geri yazıldı")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Benim bilgilerim" }));
    expect(screen.getByText(/Mesajından gece çalışmayı sevdiğini anlamış olabilirim/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Evet, kaydet" }));
    await waitFor(() => {
      const reviewCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/assistant/personal-model/suggestions/pmsug-1/review" && String(init?.method || "GET").toUpperCase() === "POST";
      });
      expect(reviewCall).toBeTruthy();
    });
    expect(screen.getByText("ulaşım tercihi profile geri yazıldı")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Asistan neyi kullanır?" }));
    fireEvent.click(screen.getByRole("button", { name: "Göster" }));
    await waitFor(() => expect(screen.getByText(/İstek türü:/i)).toBeInTheDocument());
    expect(screen.getByText(/Yalnız ilgili bilgiler kullanıldı/i)).toBeInTheDocument();
    expect(screen.getByText(/Bunu sen açıkça söyledin/i)).toBeInTheDocument();
    expect(screen.getByText(/Asistanın bu istekte gerçekten gördüğü bağlam/i)).toBeInTheDocument();
    expect(screen.getByText(/Kullanıcı tarafından verilmiş ve bu istekte ilgili\./i)).toBeInTheDocument();
  });
});
