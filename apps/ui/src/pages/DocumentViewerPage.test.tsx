import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DocumentViewerPage", () => {
  it("renders workspace document and highlights excerpt", async () => {
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
      "GET /workspace/documents/31": {
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
            text: "01.02.2026 tarihinde kira ihtarı gönderildi ve tahliye istemi açıkça kayda geçti.",
            token_count: 16,
            display_name: "Kira İhtarı",
            relative_path: "tahliye/kira_ihtari.txt",
            extension: ".txt",
            metadata: { line_anchor: "Kira İhtarı#L1", line_start: 1, line_end: 3 }
          },
          {
            id: 92,
            workspace_document_id: 31,
            office_id: "default-office",
            workspace_root_id: 4,
            chunk_index: 1,
            text: "Kiracıya üç gün içinde ödeme yapması ve eksiklerin giderilmesi ihtar edildi.",
            token_count: 15,
            display_name: "Kira İhtarı",
            relative_path: "tahliye/kira_ihtari.txt",
            extension: ".txt",
            metadata: { line_anchor: "Kira İhtarı#L4", line_start: 4, line_end: 6 }
          }
        ]
      }
    });

    renderApp(["/belge/calisma-alani/31?parca=0&alinti=tahliye%20istemi"], {
      storedSettings: { workspaceConfigured: true, workspaceRootName: "Deneme Belgeleri" }
    });

    await waitFor(() => expect(screen.getAllByText("Belge görüntüleyici").length).toBeGreaterThan(0));
    expect(screen.getByText("Kira İhtarı")).toBeInTheDocument();
    expect(screen.getAllByText("Seçili pasaj").length).toBeGreaterThan(0);
    expect(screen.getByText("Dayanak pasajı vurgulandı. Metin eşleşmesi yaklaşık ise en yakın parça seçildi.")).toBeInTheDocument();
  });
});
