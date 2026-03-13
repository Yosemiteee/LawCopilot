import type { AppSettings } from "../app/AppContext";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function buildUrl(baseUrl: string, path: string) {
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
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

async function ensureDesktopBackend(): Promise<void> {
  if (!window.lawcopilotDesktop?.ensureBackend) {
    throw new Error("Yerel servis erişilemiyor.");
  }
  await window.lawcopilotDesktop.ensureBackend({ forceRestart: true });
}

export async function apiRequest<T>(settings: AppSettings, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (settings.token) {
    headers.set("Authorization", `Bearer ${settings.token}`);
  }
  const url = buildUrl(settings.baseUrl, path);
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers
    });
  } catch (error) {
    try {
      await ensureDesktopBackend();
      response = await fetch(url, {
        ...init,
        headers
      });
    } catch {
      throw new Error("Yerel servis erişilemiyor. Uygulamayı yeniden açın veya Çekirdek ekranından durumu yenileyin.");
    }
  }
  return parseResponse<T>(response);
}
