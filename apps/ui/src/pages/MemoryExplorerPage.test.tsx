import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/test-utils";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("MemoryExplorerPage", () => {
  it("renders explorer surfaces and sends edit actions back to the KB", async () => {
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
      "GET /memory/pages": {
        generated_at: "2026-04-11T10:00:00Z",
        summary: { total_items: 4, wiki_pages: 2, concept_articles: 1, records: 3 },
        transparency: {
          root_path: "/tmp/personal-kb/default-office",
          wiki_dir: "/tmp/personal-kb/default-office/wiki",
          reports_dir: "/tmp/personal-kb/default-office/system/reports",
        },
        items: [
          {
            id: "page:preferences",
            kind: "wiki_page",
            title: "Preferences",
            summary: "Tercih kayıtları",
            record_count: 2,
            active_record_count: 1,
            scope: "personal",
            backlink_count: 2,
            claim_summary: { bound_records: 1, status_counts: { current: 1 } },
            last_updated: "2026-04-11T09:50:00Z",
          },
          {
            id: "concept:topic:communication-style",
            kind: "concept",
            title: "Communication Style",
            summary: "Ton ve dil article’ı",
            record_count: 2,
            scope: "personal",
            backlink_count: 2,
            last_updated: "2026-04-11T09:50:00Z",
          },
          {
            id: "system:AGENTS.md",
            kind: "system_file",
            title: "AGENTS.md",
            summary: "Sistem kontratı",
            scope: "global",
          },
        ],
      },
      "GET /memory/page/page%3Apreferences": {
        id: "page:preferences",
        kind: "wiki_page",
        page_key: "preferences",
        title: "Preferences",
        summary: "Tercih kayıtları",
        path: "/tmp/personal-kb/default-office/wiki/preferences.md",
        content_markdown: "# Preferences\n\n- Anneye mesaj tonu sıcak ve kısa.\n\n## Claim Sentence Bindings\n- [Anneye mesaj tonu] Sıcak, kısa ve düşünceli ton. | claims=ec-1",
        confidence: 0.84,
        scope_summary: { personal: 1 },
        backlinks: [{ id: "concept:topic:communication-style", title: "Communication Style", reason: "record_backlink" }],
        linked_pages: [{ id: "page:contacts", title: "Contacts", shared_backlinks: 1 }],
        claim_bindings: [
          {
            record_id: "pref-1",
            record_title: "Anneye mesaj tonu",
            current_claim_id: "ec-1",
            subject_key: "user",
            predicate: "communication_style",
            status: "current",
            basis: "user_explicit",
            retrieval_eligibility: "eligible",
            support_strength: "grounded",
            memory_tier: "hot",
            salience_score: 0.88,
            age_days: 2,
            supporting_claim_ids: ["ec-support-1"],
          },
        ],
        article_claim_bindings: [
          {
            section: "Anneye mesaj tonu",
            anchor: "- Summary: Sıcak, kısa ve düşünceli ton.",
            offset_start: 18,
            offset_end: 57,
            text: "Sıcak, kısa ve düşünceli ton.",
            claim_ids: ["ec-1"],
            subjects: ["user"],
            predicates: ["communication_style"],
            support_strengths: ["grounded"],
          },
        ],
        claim_summary: {
          bound_records: 1,
          status_counts: { current: 1 },
        },
        records: [
          {
            id: "pref-1",
            key: "communication_style:mother",
            title: "Anneye mesaj tonu",
            summary: "Sıcak, kısa ve düşünceli ton.",
            status: "active",
            confidence: 0.84,
            updated_at: "2026-04-11T09:50:00Z",
            record_type: "conversation_style",
            scope: "personal",
            source_refs: ["assistant-feedback:1"],
            source_basis: [{ type: "assistant_feedback", value: "beğendi" }],
            correction_history: [{ action: "note", note: "İlk öğrenim", timestamp: "2026-04-11T09:40:00Z" }],
            relations: [{ relation_type: "prefers", target: "communication_style:mother" }],
            backlinks: [{ title: "Communication Style", key: "topic:communication-style" }],
            epistemic: {
              status: "current",
              subject_key: "user",
              predicate: "communication_style",
              current_basis: "user_explicit",
              retrieval_eligibility: "eligible",
              support_strength: "grounded",
              memory_tier: "hot",
              salience_score: 0.88,
              age_days: 2,
              external_support_count: 1,
              self_generated_support_count: 0,
            },
          },
        ],
        transparency: {
          wiki_dir: "/tmp/personal-kb/default-office/wiki",
        },
      },
      "GET /memory/page/concept%3Atopic%3Acommunication-style": {
        id: "concept:topic:communication-style",
        kind: "concept",
        title: "Communication Style",
        summary: "Ton ve dil article’ı",
        path: "/tmp/personal-kb/default-office/wiki/concepts/topic-communication-style.md",
        content_markdown: "# Communication Style\n\n## Claim Sentence Bindings\n- [summary] Bu article kısa ve net ton tercihine dayanır. | claims=ec-1",
        confidence: 0.9,
        scope_summary: { personal: 2 },
        backlinks: [{ id: "page:preferences", title: "Preferences", reason: "pref-1 supporting record" }],
        linked_pages: [{ id: "page:preferences", title: "Preferences", shared_backlinks: 2 }],
        claim_bindings: [
          {
            record_id: "pref-1",
            record_title: "Anneye mesaj tonu",
            current_claim_id: "ec-1",
            subject_key: "user",
            predicate: "communication_style",
            status: "current",
            basis: "user_explicit",
            retrieval_eligibility: "eligible",
            support_strength: "grounded",
          },
        ],
        article_claim_bindings: [
          {
            section: "summary",
            text: "Bu article kısa ve net ton tercihine dayanır.",
            claim_ids: ["ec-1"],
            subjects: ["user"],
            predicates: ["communication_style"],
            support_strengths: ["grounded"],
          },
        ],
        claim_summary: {
          bound_records: 1,
          status_counts: { current: 1 },
        },
        records: [
          {
            page_key: "preferences",
            record_id: "pref-1",
            title: "Anneye mesaj tonu",
            summary: "Sıcak, kısa ve düşünceli ton.",
          },
        ],
        article_sections: {
          summary: "Bu article kısa ve net ton tercihine dayanır.",
        },
        transparency: {
          wiki_dir: "/tmp/personal-kb/default-office/wiki",
        },
      },
      "GET /memory/graph": {
        backend: "file_graph_v2",
        summary: { node_count: 3, edge_count: 2 },
        nodes: [
          { id: "topic:communication-style", title: "Communication Style", kind: "topic", entity_type: "concept" },
          { id: "record:preferences:pref-1", title: "Anneye mesaj tonu", kind: "conversation_style", entity_type: "record" },
          { id: "relation:communication-style-mother", title: "communication style mother", kind: "relation_target", entity_type: "reference" },
        ],
        edges: [
          { source: "record:preferences:pref-1", target: "topic:communication-style", relation_type: "inferred_from" },
          { source: "record:preferences:pref-1", target: "relation:communication-style-mother", relation_type: "prefers" },
        ],
      },
      "GET /memory/timeline": {
        summary: { total_events: 2 },
        items: [
          {
            id: "reflection:1",
            timestamp: "2026-04-11T09:55:00Z",
            event_type: "reflection_output",
            title: "Knowledge reflection",
            summary: "{\"contradictions\":1}",
          },
          {
            id: "memory:1",
            timestamp: "2026-04-11T09:45:00Z",
            event_type: "memory_correct",
            title: "Anneye mesaj tonu · correct",
            summary: "Semantic correction",
          },
        ],
      },
      "GET /memory/health": {
        summary: { contradictions: 1, stale_items: 0, knowledge_gaps: 1 },
        health_status: "attention_required",
        claim_summary: {
          total_claims: 3,
          validation_state_counts: { user_confirmed: 2 },
          memory_tier_counts: { hot: 2, cold: 1 },
        },
        suspicious_claims: [],
        reflection_output: {
          user_model_summary: ["preferences: Anneye mesajlarda sıcak ton."],
        },
        recommended_kb_actions: [
          { action: "review_contradiction", reason: "preferences içinde çelişki bulundu." },
        ],
        low_confidence_records: [],
        contradictions: [{ title: "Anneye mesaj tonu", count: 1 }],
        stale_records: [],
        recommendation_spam_risk: [],
        knowledge_gaps: [{ title: "Communication Style", reason: "Thin article" }],
        research_topics: [],
        transparency: {
          reports_dir: "/tmp/personal-kb/default-office/system/reports",
        },
      },
      "POST /memory/edit": {
        status: "updated",
        record_id: "pref-1",
        page_key: "preferences",
      },
    });

    renderApp(["/memory"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Belge Havuzu",
      },
    });

    await waitFor(() => expect(screen.getByText(/Nasıl kullanılır\?/i)).toBeInTheDocument());
    expect(screen.getByText("Gelişmiş Hafıza")).toBeInTheDocument();
    expect(screen.getAllByText("Tercihler").length).toBeGreaterThan(0);
    expect(screen.queryByText("Preferences")).not.toBeInTheDocument();
    expect(screen.queryByText("# Preferences")).not.toBeInTheDocument();
    expect(screen.getByText("Anneye mesaj tonu sıcak ve kısa.")).toBeInTheDocument();
    expect(screen.getByText("Bu sayfayı destekleyen kayıt")).toBeInTheDocument();
    expect(screen.queryByText("record_backlink")).not.toBeInTheDocument();
    expect(screen.getByText("1 ortak bağlantı")).toBeInTheDocument();
    expect(screen.queryByText(/shared_backlinks/i)).not.toBeInTheDocument();
    expect(screen.getByText("Çözüm bağları")).toBeInTheDocument();
    expect(screen.getByText(/claim ec-1/i)).toBeInTheDocument();
    expect(screen.getByText("Yazı dayanakları")).toBeInTheDocument();
    expect(screen.getByText(/Bağ: - Summary: Sıcak, kısa ve düşünceli ton\./i)).toBeInTheDocument();
    expect(screen.getByText("Sıcak bellek")).toBeInTheDocument();
    expect(screen.getByText("Önem skoru: 88% · Yaş: 2 gün")).toBeInTheDocument();
    expect(screen.getAllByText("wiki sayfası").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Şu an geçerli: 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/2 kayıt · 2 bağlantı · güncellendi:/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("wiki_page")).not.toBeInTheDocument();
    expect(screen.queryByText(/records=/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dayanak" }));

    await waitFor(() => expect(screen.getByText("Bellek kontrolü")).toBeInTheDocument());
    expect(screen.getByText("Çözüm durumu")).toBeInTheDocument();
    expect(screen.getByText("Şu an geçerli")).toBeInTheDocument();
    expect(screen.getByText("Kullanıcı açıkça söyledi · Yanıtlarda kullanılabilir")).toBeInTheDocument();
    expect(screen.getByText("Sağlam dayanak")).toBeInTheDocument();
    expect(screen.getByText("Sıcak bellek · önem 88% · 2 gün")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("Sıcak, kısa ve düşünceli ton."), {
      target: { value: "Sıcak ama hediye baskısı yapmayan kısa ton." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Düzelt" }));

    await waitFor(() => {
      const editCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input.toString());
        return url.pathname === "/memory/edit" && String(init?.method || "GET").toUpperCase() === "POST";
      });
      expect(editCall).toBeTruthy();
      expect(JSON.parse(String(editCall?.[1]?.body || "{}"))).toMatchObject({
        action: "correct",
        page_key: "preferences",
        target_record_id: "pref-1",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Harita" }));
    await waitFor(() => expect(screen.getByText("Bellek haritası")).toBeInTheDocument());
    expect(screen.getAllByText(/Anneye mesaj tonu → İletişim tarzı/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/record:preferences:pref-1/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dizin" }));
    const conceptButton = screen
      .getAllByText("İletişim tarzı")
      .map((node) => node.closest("button"))
      .find((node): node is HTMLButtonElement => node instanceof HTMLButtonElement);
    expect(conceptButton).toBeTruthy();
    fireEvent.click(conceptButton as HTMLButtonElement);
    await waitFor(() => expect(screen.getByText("Yazı dayanakları")).toBeInTheDocument());
    expect(screen.getByText("Bu article kısa ve net ton tercihine dayanır.")).toBeInTheDocument();
    expect(screen.getByText(/Claimler: ec-1/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Riskler" }));
    await waitFor(() => expect(screen.getByText("Bilgi sağlığı")).toBeInTheDocument());
    expect(screen.getByText(/Çelişkiyi gözden geçir/i)).toBeInTheDocument();
    expect(screen.getByText("Sıcak bellek: 2")).toBeInTheDocument();
    expect(screen.getByText("Soğuk bellek: 1")).toBeInTheDocument();
    expect(screen.queryByText(/review_contradiction/i)).not.toBeInTheDocument();
  });
});
