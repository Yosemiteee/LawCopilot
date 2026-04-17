import { vi } from "vitest";

type MockPayload = unknown | ((input: RequestInfo | URL, init?: RequestInit) => unknown);

function responseFromPayload(payload: unknown, status = 200) {
  if (payload instanceof Response) {
    return payload;
  }
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

export function installFetchMock(routes: Record<string, MockPayload>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.toString());
    const method = (init?.method || "GET").toUpperCase();
    const exactKey = `${method} ${url.pathname}${url.search}`;
    const pathKey = `${method} ${url.pathname}`;
    const handler = routes[exactKey] || routes[pathKey];
    if (!handler) {
      return responseFromPayload({ detail: `Unhandled route: ${exactKey}` }, 500);
    }
    const payload = typeof handler === "function" ? handler(input, init) : handler;
    return responseFromPayload(payload);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
