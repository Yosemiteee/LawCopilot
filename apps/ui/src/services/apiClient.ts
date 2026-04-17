import type { AppSettings } from "../app/AppContext";

const SETTINGS_STORAGE_KEY = "lawcopilot.ui.settings";
let recoveredDesktopRuntime: Partial<Pick<AppSettings, "baseUrl" | "token">> = {};
let desktopRecoveryPromise: Promise<Partial<Pick<AppSettings, "baseUrl" | "token">>> | null = null;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function buildUrl(baseUrl: string, path: string) {
  const normalizedBase = String(recoveredDesktopRuntime.baseUrl || baseUrl).replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function buildHeaders(settings: AppSettings, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {});
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = String(recoveredDesktopRuntime.token || settings.token || "");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch (e) {
    console.error("Failed to parse JSON response:", text);
    throw new Error("Sunucudan geçerli yanıt alınamadı.");
  }
  if (!response.ok) {
    throw new ApiError(data.detail || data.message || "API isteği başarısız oldu.", response.status);
  }
  return data as T;
}

function persistRecoveredRuntime(runtime: Partial<Pick<AppSettings, "baseUrl" | "token">>) {
  recoveredDesktopRuntime = { ...recoveredDesktopRuntime, ...(runtime || {}) };
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    window.localStorage.setItem(
      SETTINGS_STORAGE_KEY,
      JSON.stringify({
        ...parsed,
        ...(recoveredDesktopRuntime.baseUrl ? { baseUrl: recoveredDesktopRuntime.baseUrl } : {}),
      }),
    );
  } catch {
    return;
  }
}

async function ensureDesktopBackend(options: { forceRestart?: boolean } = {}): Promise<Partial<Pick<AppSettings, "baseUrl" | "token">>> {
  if (!window.lawcopilotDesktop?.ensureBackend) {
    throw new Error("Yerel servis erişilemiyor.");
  }
  if (desktopRecoveryPromise) {
    return desktopRecoveryPromise;
  }
  desktopRecoveryPromise = window.lawcopilotDesktop.ensureBackend({ forceRestart: Boolean(options.forceRestart) })
    .then((info) => {
      const runtime = {
        baseUrl: String((info as Record<string, unknown>)?.apiBaseUrl || ""),
        token: String((info as Record<string, unknown>)?.sessionToken || ""),
      };
      persistRecoveredRuntime(runtime);
      return runtime;
    })
    .finally(() => {
      desktopRecoveryPromise = null;
    });
  return desktopRecoveryPromise;
}

export async function apiRequest<T>(settings: AppSettings, path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    const headers = buildHeaders(settings, init);
    const url = buildUrl(settings.baseUrl, path);
    response = await fetch(url, {
      ...init,
      headers
    });
  } catch {
    try {
      await ensureDesktopBackend();
      const headers = buildHeaders(settings, init);
      const url = buildUrl(settings.baseUrl, path);
      response = await fetch(url, {
        ...init,
        headers
      });
    } catch {
      throw new Error("Yerel servis erişilemiyor. Uygulamayı yeniden açın veya Çekirdek ekranından durumu yenileyin.");
    }
  }
  if (response.status === 401 && window.lawcopilotDesktop?.ensureBackend) {
    try {
      await ensureDesktopBackend();
      const headers = buildHeaders(settings, init);
      const url = buildUrl(settings.baseUrl, path);
      response = await fetch(url, {
        ...init,
        headers,
      });
    } catch {
      throw new Error("Yerel servis erişilemiyor. Uygulamayı yeniden açın veya Çekirdek ekranından durumu yenileyin.");
    }
  }
  return parseResponse<T>(response);
}

export async function streamApiRequest(
  settings: AppSettings,
  path: string,
  init: RequestInit = {},
  onLine?: (line: string) => void | Promise<void>,
): Promise<void> {
  let response: Response;
  try {
    const headers = buildHeaders(settings, init);
    const url = buildUrl(settings.baseUrl, path);
    response = await fetch(url, {
      ...init,
      headers,
    });
  } catch {
    try {
      await ensureDesktopBackend();
      const headers = buildHeaders(settings, init);
      const url = buildUrl(settings.baseUrl, path);
      response = await fetch(url, {
        ...init,
        headers,
      });
    } catch {
      if (init.signal?.aborted) {
        throw new DOMException("İstek iptal edildi.", "AbortError");
      }
      throw new Error("Yerel servis erişilemiyor. Uygulamayı yeniden açın veya Çekirdek ekranından durumu yenileyin.");
    }
  }
  if (response.status === 401 && window.lawcopilotDesktop?.ensureBackend) {
    try {
      await ensureDesktopBackend();
      const headers = buildHeaders(settings, init);
      const url = buildUrl(settings.baseUrl, path);
      response = await fetch(url, {
        ...init,
        headers,
      });
    } catch {
      if (init.signal?.aborted) {
        throw new DOMException("İstek iptal edildi.", "AbortError");
      }
      throw new Error("Yerel servis erişilemiyor. Uygulamayı yeniden açın veya Çekirdek ekranından durumu yenileyin.");
    }
  }
  if (!response.ok) {
    await parseResponse(response);
    return;
  }
  if (!response.body) {
    throw new Error("Sunucudan akış yanıtı alınamadı.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (line && onLine) {
        await onLine(line);
      }
      newlineIndex = buffer.indexOf("\n");
    }
    if (done) {
      break;
    }
  }
  const trailing = buffer.trim();
  if (trailing && onLine) {
    await onLine(trailing);
  }
}
