import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WorkspacePage", () => {
  it("renders Turkish review signals and clarifies workspace to matter relation", async () => {
    installFetchMock({
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
        rag_runtime: { backend: "inmemory", mode: "default" }
      },
      "GET /workspace": {
        configured: true,
        workspace: {
          id: 4,
          office_id: "default-office",
          display_name: "Tahliye Belgeleri",
          root_path: "/tmp/tahliye-belgeleri",
          root_path_hash: "hash",
          status: "active",
          created_at: "2026-03-09T00:00:00Z",
          updated_at: "2026-03-09T00:00:00Z"
        },
        documents: {
          count: 2,
          items: []
        },
        scan_jobs: {
          items: [
            {
              id: 17,
              office_id: "default-office",
              workspace_root_id: 4,
              status: "completed",
              files_seen: 2,
              files_indexed: 2,
              files_skipped: 0,
              files_failed: 0,
              created_at: "2026-03-09T00:00:00Z",
              updated_at: "2026-03-09T00:10:00Z"
            }
          ]
        }
      },
      "POST /workspace/search": {
        answer: "Seçilen çalışma klasöründe 2 belge ve 2 destekleyici pasaj bulundu.",
        support_level: "orta",
        manual_review_required: true,
        citation_count: 2,
        source_coverage: 0.48,
        attention_points: [
          "Sonuç şu an tek bir belgeye dayanıyor; ikinci bir dayanak belge arayın."
        ],
        missing_document_signals: [
          "Dayanaklar büyük ölçüde tek klasörde toplandı: tahliye. Karşı belge veya yazışma eksik olabilir."
        ],
        draft_suggestions: [
          "Müvekkil durum güncellemesi taslağı",
          "İlk dosya değerlendirmesi taslağı"
        ],
        citations: [
          {
            workspace_document_id: 91,
            scope: "workspace",
            document_name: "Tahliye İhtarı",
            excerpt: "Tahliye ihtarı noter kanalıyla gönderildi.",
            relevance_score: 0.31,
            source_type: "workspace",
            support_type: "document_backed",
            confidence: "high",
            chunk_id: 501,
            chunk_index: 0,
            relative_path: "tahliye/ihtar.txt"
          }
        ],
        related_documents: [
          {
            workspace_document_id: 91,
            document_name: "Tahliye İhtarı",
            relative_path: "tahliye/ihtar.txt",
            max_score: 0.31,
            reason: "İlgili pasaj tahliye bağlamında bulundu."
          }
        ],
        scope: "workspace"
      }
    });

    renderApp(["/workspace"], {
      storedSettings: {
        workspaceConfigured: true,
        workspaceRootName: "Tahliye Belgeleri",
        currentMatterId: 7,
        currentMatterLabel: "Kira Tahliye Dosyası"
      }
    });

    await waitFor(() => expect(screen.getAllByText("Tahliye Belgeleri").length).toBeGreaterThan(0));
    expect(screen.getByText(/Kira Tahliye Dosyası açık\./)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Örneğin: benzer tahliye dosyaları, kira bedeli ihtilafı, fesih bildirimi"), {
      target: { value: "tahliye ihtarı" }
    });
    fireEvent.click(screen.getByText("Aramayı çalıştır"));

    await waitFor(() => expect(screen.getByText("Dikkat edilmesi gereken noktalar")).toBeInTheDocument());
    expect(screen.getByText("Eksik belge sinyalleri")).toBeInTheDocument();
    expect(screen.getByText("Taslak önerileri")).toBeInTheDocument();
    expect(screen.getByText("Müvekkil durum güncellemesi taslağı")).toBeInTheDocument();
  });
});
