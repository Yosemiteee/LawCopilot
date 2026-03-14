import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DocumentsPage", () => {
  it("opens similar workspace document in the system app", async () => {
    const openPathInOS = vi.fn().mockResolvedValue({ ok: true });
    installFetchMock({
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
      "GET /workspace/documents": {
        configured: true,
        workspace_root_id: 4,
        items: [
          {
            id: 31,
            office_id: "default-office",
            workspace_root_id: 4,
            relative_path: "tahliye/kira_ihtari.txt",
            display_name: "Kira İhtarı",
            extension: ".txt",
            size_bytes: 245,
            mtime: 1,
            checksum: "abc",
            parser_status: "parsed",
            indexed_status: "indexed",
            document_language: "tr",
            created_at: "2026-03-09T00:00:00Z",
            updated_at: "2026-03-09T00:00:00Z"
          }
        ]
      },
      "GET /workspace/documents/31/chunks": {
        document_id: 31,
        items: [
          {
            id: 91,
            workspace_document_id: 31,
            office_id: "default-office",
            workspace_root_id: 4,
            chunk_index: 0,
            text: "01.02.2026 tarihinde kira ihtarı gönderildi.",
            token_count: 10,
            display_name: "Kira İhtarı",
            relative_path: "tahliye/kira_ihtari.txt",
            extension: ".txt",
            metadata: { line_anchor: "Kira İhtarı#L1" }
          }
        ]
      },
      "POST /workspace/similar-documents": {
        explanation: "Yerel benzer dosya analizi tamamlandı.",
        signals: ["ortak_terim"],
        top_terms: ["tahliye"],
        manual_review_required: true,
        items: [
          {
            workspace_document_id: 72,
            belge_adi: "Tahliye davası emsali",
            goreli_yol: "emsal/tahliye_davasi.txt",
            klasor_baglami: "emsal",
            benzerlik_puani: 0.74,
            neden_benzer: "Aynı ihtar ve tahliye terimleri yoğun biçimde tekrar ediyor.",
            skor_bilesenleri: {
              dosya_adi: 0.62,
              icerik: 0.81,
              belge_turu: 1,
              checksum: 0,
              klasor_baglami: 0.4,
              hukuk_terimleri: 0.5,
              genel_skor: 0.74
            },
            ortak_terimler: ["tahliye", "ihtar"],
            dikkat_notlari: ["İçerik benzerliği yüksek ama klasör bağlamı ayrıca kontrol edilmeli."],
            taslak_onerileri: ["İç ekip özeti taslağı", "Belge talep listesi taslağı"],
            manuel_inceleme_gerekir: true,
            sinyaller: ["ortak_terim"],
            destekleyici_pasajlar: [
              {
                workspace_document_id: 72,
                scope: "workspace",
                document_name: "Tahliye davası emsali",
                excerpt: "Tahliye istemi ihtar sonrası süresinde ileri sürülmüştür.",
                relevance_score: 0.74,
                source_type: "workspace",
                support_type: "document_backed",
                confidence: "high",
                chunk_id: 205,
                chunk_index: 0,
                relative_path: "emsal/tahliye_davasi.txt"
              }
            ]
          }
        ]
      },
      "GET /workspace/documents/72": {
        id: 72,
        office_id: "default-office",
        workspace_root_id: 4,
        relative_path: "emsal/tahliye_davasi.txt",
        display_name: "Tahliye davası emsali",
        extension: ".txt",
        size_bytes: 280,
        mtime: 2,
        checksum: "xyz",
        parser_status: "parsed",
        indexed_status: "indexed",
        document_language: "tr",
        created_at: "2026-03-09T00:00:00Z",
        updated_at: "2026-03-09T00:00:00Z"
      },
      "GET /workspace/documents/72/chunks": {
        document_id: 72,
        items: [
          {
            id: 205,
            workspace_document_id: 72,
            office_id: "default-office",
            workspace_root_id: 4,
            chunk_index: 0,
            text: "Tahliye istemi ihtar sonrası süresinde ileri sürülmüştür ve dayanak pasaj burada yer alır.",
            token_count: 16,
            display_name: "Tahliye davası emsali",
            relative_path: "emsal/tahliye_davasi.txt",
            extension: ".txt",
            metadata: { line_anchor: "Tahliye Emsali#L1" }
          }
        ]
      }
    });

    renderApp(["/_embedded/documents"], {
      storedSettings: { workspaceConfigured: true, workspaceRootName: "Deneme Belgeleri" },
      desktop: { openPathInOS },
    });

    await waitFor(() => expect(screen.getByText("Kira İhtarı")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Benzer dosyaları bul"));
    await waitFor(() => expect(screen.getByText("Tahliye davası emsali")).toBeInTheDocument());
    expect(screen.getByText("Dikkat edilmesi gereken noktalar")).toBeInTheDocument();
    expect(screen.getByText("Taslak önerileri")).toBeInTheDocument();
    expect(screen.getByText(/Klasör bağlamı:/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Belgeyi aç")[1]);
    await waitFor(() => expect(openPathInOS).toHaveBeenCalledWith("emsal/tahliye_davasi.txt"));
  });
});
