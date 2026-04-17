export type BrowserActionType =
  | "navigate"
  | "extract"
  | "screenshot"
  | "click"
  | "type"
  | "select"
  | "download-plan";

export interface BaseBrowserAction {
  type: BrowserActionType;
  timeoutMs?: number;
  url?: string;
}

export interface NavigateAction extends BaseBrowserAction {
  type: "navigate";
  url: string;
  waitUntil?: "load" | "domcontentloaded" | "networkidle" | "commit";
}

export interface ExtractAction extends BaseBrowserAction {
  type: "extract";
  selector?: string;
  includeHtml?: boolean;
  includeLinks?: boolean;
}

export interface ScreenshotAction extends BaseBrowserAction {
  type: "screenshot";
  selector?: string;
  fullPage?: boolean;
  fileName?: string;
}

export interface ClickAction extends BaseBrowserAction {
  type: "click";
  selector: string;
}

export interface TypeAction extends BaseBrowserAction {
  type: "type";
  selector: string;
  text: string;
  clearFirst?: boolean;
}

export interface SelectAction extends BaseBrowserAction {
  type: "select";
  selector: string;
  values: string[];
}

export interface DownloadPlanAction extends BaseBrowserAction {
  type: "download-plan";
  selector?: string;
  url?: string;
  suggestedFileName?: string;
}

export type BrowserAction =
  | NavigateAction
  | ExtractAction
  | ScreenshotAction
  | ClickAction
  | TypeAction
  | SelectAction
  | DownloadPlanAction;

export interface BrowserWorkerRequest {
  requestId?: string;
  headless?: boolean;
  baseUrl?: string;
  profileDir?: string;
  artifactsDir?: string;
  downloadsDir?: string;
  allowedDomains?: string[];
  timeoutMs?: number;
  action?: BrowserAction;
  actions?: BrowserAction[];
}

export interface BrowserActionResult {
  action: BrowserActionType;
  ok: boolean;
  url?: string;
  data?: Record<string, unknown>;
  artifactPaths?: string[];
  error?: string;
}

export interface BrowserWorkerResponse {
  ok: boolean;
  requestId?: string;
  startedAt: string;
  finishedAt: string;
  results: BrowserActionResult[];
  warnings: string[];
}

export interface WorkerPolicy {
  allowedDomains: string[];
  profileDir: string;
  artifactsDir: string;
  downloadsDir: string;
  headless: boolean;
  timeoutMs: number;
}
