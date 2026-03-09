import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MattersPage", () => {
  it("renders matter list and creation form", async () => {
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
      "GET /matters": {
        items: [
          {
            id: 1,
            office_id: "default-office",
            title: "Kira uyuşmazlığı",
            status: "active",
            created_by: "lawyer",
            created_at: "2026-03-09T00:00:00Z",
            updated_at: "2026-03-09T00:00:00Z"
          }
        ]
      }
    });

    renderApp(["/matters"]);

    await waitFor(() => expect(screen.getByText("Kira uyuşmazlığı")).toBeInTheDocument());
    expect(screen.getByText("Yeni dosya oluştur")).toBeInTheDocument();
  });
});
