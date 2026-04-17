import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

function commonMatterRoutes() {
  return {
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
      rag_runtime: { backend: "inmemory", mode: "default" }
    },
    "GET /matters/7": {
      id: 7,
      office_id: "default-office",
      title: "Trafik tazminat dosyası",
      status: "active",
      created_by: "lawyer",
      created_at: "2026-03-09T00:00:00Z",
      updated_at: "2026-03-09T00:00:00Z"
    },
    "GET /matters/7/summary": {
      matter: {
        id: 7,
        office_id: "default-office",
        title: "Trafik tazminat dosyası",
        status: "active",
        created_by: "lawyer",
        created_at: "2026-03-09T00:00:00Z",
        updated_at: "2026-03-09T00:00:00Z"
      },
      summary: "Dosya özeti",
      counts: { notes: 1, tasks: 2, drafts: 1 },
      latest_timeline: [],
      generated_from: "matter_record",
      manual_review_required: false
    }
  };
}

describe("MatterDetailPage", () => {
  it("renders documents tab", async () => {
    installFetchMock({
      ...commonMatterRoutes(),
      "GET /matters/7/documents": {
        items: [
          {
            id: 11,
            matter_id: 7,
            office_id: "default-office",
            filename: "petition.txt",
            display_name: "İlk Dilekçe",
            source_type: "upload",
            checksum: "abc",
            size_bytes: 120,
            ingest_status: "indexed",
            created_at: "2026-03-09T00:00:00Z",
            updated_at: "2026-03-09T00:00:00Z",
            chunk_count: 2
          }
        ]
      },
      "GET /matters/7/ingestion-jobs": {
        items: [
          {
            id: 90,
            office_id: "default-office",
            matter_id: 7,
            document_id: 11,
            status: "indexed",
            created_at: "2026-03-09T00:00:00Z",
            updated_at: "2026-03-09T00:00:00Z",
            document_name: "İlk Dilekçe"
          }
        ]
      },
      "GET /matters/7/workspace-documents": { matter_id: 7, items: [] }
    });

    renderApp(["/matters/7?tab=documents"]);

    await waitFor(() => expect(screen.getByText("Dosyaya belge yükle")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("İlk Dilekçe").length).toBeGreaterThan(0));
  });

  it("renders search results", async () => {
    installFetchMock({
      ...commonMatterRoutes(),
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: { hybrid: { provider: "router", policy: "sensitive->local" } }
      },
      "POST /matters/7/search": {
        answer: "İki destekleyici pasaj bulundu.",
        model_profile: "hybrid",
        support_level: "high",
        manual_review_required: false,
        citation_count: 1,
        source_coverage: 0.64,
        generated_from: "matter_document_memory",
        citations: [
          {
            index: 1,
            label: "[1]",
            document_id: 12,
            document_name: "Servis Faturası",
            matter_id: 7,
            chunk_id: 5,
            chunk_index: 1,
            excerpt: "Servis faturası onarım maliyetini kayıt altına alıyor.",
            relevance_score: 0.44,
            source_type: "upload",
            support_type: "document_backed",
            confidence: "high",
            line_anchor: "Service Invoice#L1"
          }
        ],
        related_documents: [],
        retrieval_summary: {
          scope: "matter",
          matter_id: 7,
          document_count: 1,
          citation_count: 1
        }
      },
      "GET /matters/7/documents/12": {
        id: 12,
        matter_id: 7,
        office_id: "default-office",
        filename: "servis_faturasi.txt",
        display_name: "Servis Faturası",
        source_type: "upload",
        checksum: "def",
        size_bytes: 320,
        ingest_status: "indexed",
        created_at: "2026-03-09T00:00:00Z",
        updated_at: "2026-03-09T00:00:00Z",
      },
      "GET /documents/12/chunks": {
        document_id: 12,
        items: [
          {
            id: 5,
            document_id: 12,
            office_id: "default-office",
            matter_id: 7,
            chunk_index: 1,
            text: "Servis faturası onarım maliyetini kayıt altına alıyor ve toplam 48.000 TL gider bildiriyor.",
            token_count: 18,
            metadata: { line_anchor: "Servis Faturası#L1", line_start: 1, line_end: 4 }
          }
        ]
      },
    });

    renderApp(["/matters/7?tab=search"]);

    await waitFor(() => expect(screen.getByText("Kaynak dayanaklı dosya araması")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("Örneğin: risk noktaları, zaman çizelgesi ipuçları, belge dayanaklı cevaplar"), {
      target: { value: "onarım maliyeti" }
    });
    fireEvent.click(screen.getByText("Aramayı çalıştır"));
    await waitFor(() => expect(screen.getByText("İki destekleyici pasaj bulundu.")).toBeInTheDocument());
    expect(screen.getAllByText("Servis Faturası").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("Belgedeki yeri aç"));
    await waitFor(() => expect(screen.getAllByText("Belge görüntüleyici").length).toBeGreaterThan(0));
  });

  it("renders drafts tab", async () => {
    installFetchMock({
      ...commonMatterRoutes(),
      "GET /matters/7/drafts": {
        items: [
          {
            id: 22,
            matter_id: 7,
            office_id: "default-office",
            draft_type: "client_update",
            title: "Müvekkil durum güncellemesi",
            body: "Taslak gövdesi",
            status: "draft",
            target_channel: "email",
            created_by: "lawyer",
            created_at: "2026-03-09T00:00:00Z",
            updated_at: "2026-03-09T00:00:00Z"
          }
        ]
      }
    });

    renderApp(["/matters/7?tab=drafts"]);

    await waitFor(() => expect(screen.getByText("Taslak inceleme")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("Göndermeden önce inceleyin").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("Müvekkil durum güncellemesi").length).toBeGreaterThan(0));
  });

  it("renders summary risk notes", async () => {
    installFetchMock({
      ...commonMatterRoutes(),
      "GET /matters/7/documents": { items: [] },
      "GET /matters/7/workspace-documents": { matter_id: 7, items: [] },
      "GET /matters/7/risk-notes": {
        matter_id: 7,
        label: "working_notes",
        manual_review_required: true,
        generated_from: "matter_workflow_engine",
        items: [
          {
            category: "missing_document",
            title: "Eksik bordro kayıtları",
            details: "Bordro belgeleri hâlâ inceleme bekliyor.",
            severity: "high",
            manual_review_required: true,
            signals: ["missing_document_signal"],
            source_labels: ["Not #1"]
          }
        ]
      }
    });

    renderApp(["/matters/7?tab=summary"]);

    await waitFor(() => expect(screen.getAllByText("Dosya özeti").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("Risk notları")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Eksik bordro kayıtları")).toBeInTheDocument());
  });

  it("renders task recommendations", async () => {
    installFetchMock({
      ...commonMatterRoutes(),
      "GET /matters/7/tasks": {
        matter_id: 7,
        items: [
          {
            id: 41,
            matter_id: 7,
            title: "Fatura kopyalarını topla",
            priority: "medium",
            status: "open",
            owner: "lawyer",
            explanation: "Mevcut dosya görevi.",
            created_at: "2026-03-09T00:00:00Z"
          }
        ]
      },
      "GET /matters/7/task-recommendations": {
        matter_id: 7,
        manual_review_required: true,
        generated_from: "matter_workflow_engine",
        items: [
          {
            title: "Çelişkili kronoloji tarihlerini netleştir",
            priority: "high",
            recommended_by: "workflow_engine",
            origin_type: "timeline",
            manual_review_required: true,
            signals: ["chronology_conflict"],
            explanation: "Birden fazla kaynak aynı olayı farklı tarihlerle anlattığı için önerildi."
          }
        ]
      }
    });

    renderApp(["/matters/7?tab=tasks"]);

    await waitFor(() => expect(screen.getByText("Önerilen görevler")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Çelişkili kronoloji tarihlerini netleştir")).toBeInTheDocument());
    expect(screen.getByText("Fatura kopyalarını topla")).toBeInTheDocument();
  });
});
