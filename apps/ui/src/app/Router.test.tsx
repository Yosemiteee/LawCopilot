import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFetchMock } from "../test/mockFetch";
import { renderApp } from "../test/test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppRouter", () => {
  it("renders dashboard shell", async () => {
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
      "GET /settings/model-profiles": {
        default: "hybrid",
        deployment_mode: "local-only",
        office_id: "default-office",
        profiles: { hybrid: { provider: "router", policy: "sensitive->local" } }
      },
      "GET /matters": { items: [] }
    });

    renderApp(["/dashboard"]);

    await waitFor(() => expect(screen.getByText("LawCopilot çalışma masası")).toBeInTheDocument());
    expect(screen.getByText("Genel Bakış")).toBeInTheDocument();
    expect(screen.getByText("Henüz dosya yok")).toBeInTheDocument();
  });
});
