const fs = require("fs");
const crypto = require("crypto");
const os = require("os");
const path = require("path");
const { providerDefaults } = require("./provider-model-catalog.cjs");
const bootstrapKeyCache = new Map();

function repoRootFrom(baseDir) {
  return path.resolve(baseDir, "..", "..", "..");
}

function generateBootstrapKey() {
  return crypto.randomBytes(24).toString("base64url");
}

const DEFAULT_GOOGLE_SCOPES = [
  "openid",
  "email",
  "profile",
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/drive.readonly",
  "https://www.googleapis.com/auth/youtube.readonly",
];

const DEFAULT_GOOGLE_PORTABILITY_SCOPES = [
  "https://www.googleapis.com/auth/dataportability.myactivity.youtube",
  "https://www.googleapis.com/auth/dataportability.chrome.history",
];

const DEFAULT_OUTLOOK_SCOPES = [
  "openid",
  "email",
  "profile",
  "offline_access",
  "User.Read",
  "Mail.Read",
  "Calendars.Read",
];

const DEFAULT_LINKEDIN_SCOPES = [
  "openid",
  "profile",
  "email",
  "w_member_social",
  "r_member_social",
];

const DEFAULT_INSTAGRAM_SCOPES = [
  "instagram_basic",
  "instagram_manage_messages",
  "pages_manage_metadata",
  "pages_show_list",
];

function normalizeGoogleScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_GOOGLE_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeGooglePortabilityScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_GOOGLE_PORTABILITY_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (
      !value
      || merged.includes(value)
      || !value.startsWith("https://www.googleapis.com/auth/dataportability.")
    ) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeOutlookScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_OUTLOOK_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeLinkedInScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_LINKEDIN_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeInstagramScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_INSTAGRAM_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeStringList(values) {
  const merged = [];
  for (const raw of Array.isArray(values) ? values : []) {
    const value = String(raw || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function normalizeProviderModelValue(type, model, fallback = "") {
  const normalizedType = String(type || "openai").trim() || "openai";
  const normalizedModel = String(model || "").trim();
  const defaults = providerDefaults(normalizedType);
  if (normalizedType === "openai-codex") {
    if (normalizedModel.startsWith("openai-codex/")) {
      return normalizedModel;
    }
    return String(fallback || defaults.model || "openai-codex/gpt-5.4");
  }
  return normalizedModel || String(fallback || defaults.model || "");
}

function clampInteger(value, min, max, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function normalizeClockTime(value, fallback = "08:30") {
  const text = String(value || "").trim();
  const match = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(text);
  if (!match) {
    return fallback;
  }
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

function normalizeAutomationText(value, maxLength = 240) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function normalizeAutomationMode(value) {
  const mode = String(value || "").trim().toLowerCase();
  if (["auto_reply", "notify", "custom", "reminder"].includes(mode)) {
    return mode;
  }
  return "custom";
}

function normalizeAutomationChannels(values) {
  return normalizeStringList(Array.isArray(values) ? values : [])
    .map((item) => item.toLowerCase())
    .filter((item) => ["whatsapp", "telegram", "email", "outlook", "x", "generic"].includes(item))
    .slice(0, 6);
}

function normalizeWhatsAppMode(value, fallback = "web") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "business_cloud" || mode === "web") {
    return mode;
  }
  return fallback;
}

function normalizeTelegramMode(value, fallback = "bot") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "bot" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveTelegramMode(value, fallback = "bot") {
  const raw = value && typeof value === "object" ? value : {};
  if (String(raw.mode || "").trim()) {
    return normalizeTelegramMode(raw.mode, fallback);
  }
  if (raw.botToken || raw.allowedUserId) {
    return "bot";
  }
  return fallback;
}

function normalizeLinkedInMode(value, fallback = "official") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "official" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveLinkedInMode(value, fallback = "official") {
  const raw = value && typeof value === "object" ? value : {};
  if (String(raw.mode || "").trim()) {
    return normalizeLinkedInMode(raw.mode, fallback);
  }
  if (raw.oauthConnected || raw.accessToken) {
    return "official";
  }
  return fallback;
}

function resolveWhatsAppMode(value, fallback = "web") {
  const raw = value && typeof value === "object" ? value : {};
  if (String(raw.mode || "").trim()) {
    return normalizeWhatsAppMode(raw.mode, fallback);
  }
  if (raw.phoneNumberId || raw.accessToken) {
    return "business_cloud";
  }
  return fallback;
}

function normalizeAutomationRule(rule, index = 0) {
  const value = rule && typeof rule === "object" ? rule : {};
  const summary = normalizeAutomationText(value.summary || value.label || value.instruction || "");
  const instruction = normalizeAutomationText(value.instruction || value.summary || "", 400);
  if (!summary) {
    return null;
  }
  return {
    id: normalizeAutomationText(value.id || `rule-${index + 1}`, 80) || `rule-${index + 1}`,
    summary,
    instruction,
    mode: normalizeAutomationMode(value.mode),
    channels: normalizeAutomationChannels(value.channels),
    targets: normalizeStringList(Array.isArray(value.targets) ? value.targets : []).slice(0, 12),
    matchTerms: normalizeStringList(
      Array.isArray(value.matchTerms)
        ? value.matchTerms
        : Array.isArray(value.match_terms)
          ? value.match_terms
          : [],
    ).slice(0, 12),
    replyText: normalizeAutomationText(value.replyText || value.reply_text || "", 280),
    reminderAt: String(value.reminderAt || value.reminder_at || ""),
    threadId: Number.parseInt(String(value.threadId || value.thread_id || 0), 10) || 0,
    active: value.active !== false,
    createdAt: String(value.createdAt || value.created_at || ""),
    updatedAt: String(value.updatedAt || value.updated_at || ""),
  };
}

function normalizeAutomationRules(rules) {
  const normalized = [];
  const seen = new Set();
  for (const [index, raw] of (Array.isArray(rules) ? rules : []).entries()) {
    const item = normalizeAutomationRule(raw, index);
    if (!item) {
      continue;
    }
    const key = `${item.mode}:${item.summary.toLocaleLowerCase("tr-TR")}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    normalized.push(item);
  }
  return normalized.slice(0, 40);
}

function legacyAutomationRules(value) {
  const rules = [];
  const summary = normalizeAutomationText(value?.assistantManagedSummary || "");
  if (summary) {
    rules.push({
      id: "legacy-summary",
      summary,
      instruction: summary,
      mode: "custom",
      channels: ["generic"],
      targets: [],
      matchTerms: [],
      replyText: "",
      active: true,
      createdAt: "",
      updatedAt: "",
    });
  }
  return rules;
}

function defaultAutomationConfig() {
  return {
    enabled: true,
    autoSyncConnectedServices: true,
    desktopNotifications: false,
    importantContacts: [],
    doNotAutoReplyContacts: [],
    followUpReminderHours: 24,
    calendarReminderLeadMinutes: 30,
    morningGreetingEnabled: false,
    morningGreetingTime: "08:30",
    morningGreetingRecipients: [],
    morningGreetingMessage: "Günaydın. Müsait olduğunda bugünün önceliklerini birlikte gözden geçirebiliriz.",
    holidayAutoReplyEnabled: false,
    holidayAutoReplyMessage: "Teşekkür ederim, iyi bayramlar dilerim.",
    alertViaWhatsApp: false,
    alertWhatsAppRecipients: [],
    assistantManagedSummary: "",
    automationRules: [],
    automationLedger: {
      entries: {},
      lastRunAt: "",
    },
  };
}

function mergeAutomationConfig(current, patch) {
  const base = defaultAutomationConfig();
  const currentValue = current && typeof current === "object" ? current : {};
  const patchValue = patch && typeof patch === "object" ? patch : {};
  const currentLedger = currentValue.automationLedger && typeof currentValue.automationLedger === "object"
    ? currentValue.automationLedger
    : {};
  const patchLedger = patchValue.automationLedger && typeof patchValue.automationLedger === "object"
    ? patchValue.automationLedger
    : {};
  return {
    ...base,
    ...currentValue,
    ...patchValue,
    importantContacts: normalizeStringList(
      Array.isArray(patchValue.importantContacts) ? patchValue.importantContacts : currentValue.importantContacts,
    ).slice(0, 32),
    doNotAutoReplyContacts: normalizeStringList(
      Array.isArray(patchValue.doNotAutoReplyContacts)
        ? patchValue.doNotAutoReplyContacts
        : currentValue.doNotAutoReplyContacts,
    ).slice(0, 32),
    followUpReminderHours: clampInteger(
      patchValue.followUpReminderHours ?? currentValue.followUpReminderHours,
      1,
      168,
      base.followUpReminderHours,
    ),
    calendarReminderLeadMinutes: clampInteger(
      patchValue.calendarReminderLeadMinutes ?? currentValue.calendarReminderLeadMinutes,
      5,
      240,
      base.calendarReminderLeadMinutes,
    ),
    morningGreetingEnabled: patchValue.morningGreetingEnabled ?? currentValue.morningGreetingEnabled ?? base.morningGreetingEnabled,
    morningGreetingTime: normalizeClockTime(
      patchValue.morningGreetingTime ?? currentValue.morningGreetingTime,
      base.morningGreetingTime,
    ),
    morningGreetingRecipients: normalizeStringList(
      Array.isArray(patchValue.morningGreetingRecipients)
        ? patchValue.morningGreetingRecipients
        : currentValue.morningGreetingRecipients,
    ).slice(0, 24),
    morningGreetingMessage: normalizeAutomationText(
      patchValue.morningGreetingMessage ?? currentValue.morningGreetingMessage,
      280,
    ),
    holidayAutoReplyEnabled: patchValue.holidayAutoReplyEnabled ?? currentValue.holidayAutoReplyEnabled ?? base.holidayAutoReplyEnabled,
    holidayAutoReplyMessage: normalizeAutomationText(
      patchValue.holidayAutoReplyMessage ?? currentValue.holidayAutoReplyMessage,
      280,
    ),
    alertViaWhatsApp: patchValue.alertViaWhatsApp ?? currentValue.alertViaWhatsApp ?? base.alertViaWhatsApp,
    alertWhatsAppRecipients: normalizeStringList(
      Array.isArray(patchValue.alertWhatsAppRecipients)
        ? patchValue.alertWhatsAppRecipients
        : currentValue.alertWhatsAppRecipients,
    ).slice(0, 24),
    assistantManagedSummary: normalizeAutomationText(
      patchValue.assistantManagedSummary ?? currentValue.assistantManagedSummary,
      400,
    ),
    automationRules: normalizeAutomationRules(
      Array.isArray(patchValue.automationRules)
        ? patchValue.automationRules
        : Array.isArray(currentValue.automationRules)
          ? currentValue.automationRules
          : legacyAutomationRules(patchValue).length
            ? legacyAutomationRules(patchValue)
            : legacyAutomationRules(currentValue),
    ),
    automationLedger: {
      ...base.automationLedger,
      ...currentLedger,
      ...patchLedger,
      entries: {
        ...(currentLedger.entries && typeof currentLedger.entries === "object" ? currentLedger.entries : {}),
        ...(patchLedger.entries && typeof patchLedger.entries === "object" ? patchLedger.entries : {}),
      },
    },
  };
}

function sanitizeAutomationConfig(automation) {
  const normalized = mergeAutomationConfig(defaultAutomationConfig(), automation || {});
  return {
    enabled: Boolean(normalized.enabled),
    autoSyncConnectedServices: Boolean(normalized.autoSyncConnectedServices),
    desktopNotifications: Boolean(normalized.desktopNotifications),
    importantContacts: normalizeStringList(normalized.importantContacts).slice(0, 32),
    doNotAutoReplyContacts: normalizeStringList(normalized.doNotAutoReplyContacts).slice(0, 32),
    followUpReminderHours: clampInteger(normalized.followUpReminderHours, 1, 168, 24),
    calendarReminderLeadMinutes: clampInteger(normalized.calendarReminderLeadMinutes, 5, 240, 30),
    morningGreetingEnabled: Boolean(normalized.morningGreetingEnabled),
    morningGreetingTime: normalizeClockTime(normalized.morningGreetingTime, "08:30"),
    morningGreetingRecipients: normalizeStringList(normalized.morningGreetingRecipients).slice(0, 24),
    morningGreetingMessage: normalizeAutomationText(normalized.morningGreetingMessage, 280),
    holidayAutoReplyEnabled: Boolean(normalized.holidayAutoReplyEnabled),
    holidayAutoReplyMessage: normalizeAutomationText(normalized.holidayAutoReplyMessage, 280),
    alertViaWhatsApp: Boolean(normalized.alertViaWhatsApp),
    alertWhatsAppRecipients: normalizeStringList(normalized.alertWhatsAppRecipients).slice(0, 24),
    assistantManagedSummary: normalizeAutomationText(normalized.assistantManagedSummary, 400),
    automationRules: normalizeAutomationRules(normalized.automationRules),
    lastRunAt: String(normalized.automationLedger?.lastRunAt || ""),
  };
}

function normalizeAutomationConfigForWrite(automation) {
  const normalized = mergeAutomationConfig(defaultAutomationConfig(), automation || {});
  const ledgerEntries = normalized.automationLedger?.entries && typeof normalized.automationLedger.entries === "object"
    ? normalized.automationLedger.entries
    : {};
  const cleanLedgerEntries = {};
  for (const [key, value] of Object.entries(ledgerEntries).slice(0, 1500)) {
    const normalizedKey = String(key || "").trim();
    const normalizedValue = String(value || "").trim();
    if (!normalizedKey || !normalizedValue) {
      continue;
    }
    cleanLedgerEntries[normalizedKey] = normalizedValue;
  }
  return {
    enabled: Boolean(normalized.enabled),
    autoSyncConnectedServices: Boolean(normalized.autoSyncConnectedServices),
    desktopNotifications: Boolean(normalized.desktopNotifications),
    importantContacts: normalizeStringList(normalized.importantContacts).slice(0, 32),
    doNotAutoReplyContacts: normalizeStringList(normalized.doNotAutoReplyContacts).slice(0, 32),
    followUpReminderHours: clampInteger(normalized.followUpReminderHours, 1, 168, 24),
    calendarReminderLeadMinutes: clampInteger(normalized.calendarReminderLeadMinutes, 5, 240, 30),
    morningGreetingEnabled: Boolean(normalized.morningGreetingEnabled),
    morningGreetingTime: normalizeClockTime(normalized.morningGreetingTime, "08:30"),
    morningGreetingRecipients: normalizeStringList(normalized.morningGreetingRecipients).slice(0, 24),
    morningGreetingMessage: normalizeAutomationText(normalized.morningGreetingMessage, 280),
    holidayAutoReplyEnabled: Boolean(normalized.holidayAutoReplyEnabled),
    holidayAutoReplyMessage: normalizeAutomationText(normalized.holidayAutoReplyMessage, 280),
    alertViaWhatsApp: Boolean(normalized.alertViaWhatsApp),
    alertWhatsAppRecipients: normalizeStringList(normalized.alertWhatsAppRecipients).slice(0, 24),
    assistantManagedSummary: normalizeAutomationText(normalized.assistantManagedSummary, 400),
    automationRules: normalizeAutomationRules(normalized.automationRules),
    automationLedger: {
      entries: cleanLedgerEntries,
      lastRunAt: String(normalized.automationLedger?.lastRunAt || ""),
    },
  };
}

function defaultUpdaterConfig(releaseChannel = "") {
  const normalizedReleaseChannel = String(releaseChannel || "").trim().toLowerCase();
  return {
    enabled: true,
    feedUrl: String(process.env.LAWCOPILOT_UPDATE_FEED_URL || "").trim(),
    channel: String(process.env.LAWCOPILOT_UPDATE_CHANNEL || "latest").trim() || "latest",
    autoCheckOnLaunch: process.env.LAWCOPILOT_UPDATE_AUTO_CHECK !== "0",
    autoDownload: process.env.LAWCOPILOT_UPDATE_AUTO_DOWNLOAD === "1",
    allowPrerelease: process.env.LAWCOPILOT_UPDATE_ALLOW_PRERELEASE === "1" || normalizedReleaseChannel === "pilot",
    lastCheckedAt: "",
    lastAvailableVersion: "",
    lastDownloadedVersion: "",
    lastError: "",
  };
}

function normalizeUpdaterConfigForWrite(updater, releaseChannel = "") {
  const defaults = defaultUpdaterConfig(releaseChannel);
  const value = updater && typeof updater === "object" ? updater : {};
  return {
    enabled: value.enabled ?? defaults.enabled,
    feedUrl: String(value.feedUrl || "").trim(),
    channel: String(value.channel || defaults.channel).trim() || defaults.channel,
    autoCheckOnLaunch: value.autoCheckOnLaunch ?? defaults.autoCheckOnLaunch,
    autoDownload: value.autoDownload ?? defaults.autoDownload,
    allowPrerelease: value.allowPrerelease ?? defaults.allowPrerelease,
    lastCheckedAt: String(value.lastCheckedAt || "").trim(),
    lastAvailableVersion: String(value.lastAvailableVersion || "").trim(),
    lastDownloadedVersion: String(value.lastDownloadedVersion || "").trim(),
    lastError: String(value.lastError || "").trim(),
  };
}

function defaultDesktopConfig(repoRoot, options = {}) {
  const artifactsRoot = options.storagePath || path.join(repoRoot, "artifacts");
  const releaseChannel = process.env.LAWCOPILOT_RELEASE_CHANNEL || "pilot";
  const openAiDefaults = providerDefaults("openai");
  return {
    appName: "LawCopilot",
    appVersion: "0.7.0-pilot.2",
    officeId: process.env.LAWCOPILOT_OFFICE_ID || "default-office",
    deploymentMode: process.env.LAWCOPILOT_DEPLOYMENT_MODE || "local-first-hybrid",
    releaseChannel,
    locale: "tr",
    themeMode: "system",
    themeAccent: "default",
    chatFontSize: "medium",
    chatWallpaper: "default",
    customWallpaper: "",
    selectedModelProfile: process.env.LAWCOPILOT_DEFAULT_MODEL_PROFILE || "cloud",
    apiHost: "127.0.0.1",
    apiPort: 18731,
    apiBaseUrl: "http://127.0.0.1:18731",
    logLevel: "info",
    storagePath: artifactsRoot,
    runtimeBootstrapKey: defaultRuntimeBootstrapKey(options),
    envFile: path.join(artifactsRoot, "runtime", "pilot.env"),
    scanOnStartup: true,
    workspaceRootPath: "",
    workspaceRootName: "",
    workspaceRootHash: "",
    provider: {
      type: "openai",
      authMode: "api-key",
      baseUrl: openAiDefaults.baseUrl,
      model: openAiDefaults.model,
      apiKey: "",
      accountLabel: "OpenAI API",
      availableModels: [],
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
    },
    google: {
      enabled: false,
      accountLabel: "",
      scopes: [...DEFAULT_GOOGLE_SCOPES],
      clientId: "",
      clientSecret: "",
      redirectUri: "",
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      refreshToken: "",
      tokenType: "",
      expiryDate: "",
    },
    googlePortability: {
      enabled: false,
      accountLabel: "",
      scopes: [...DEFAULT_GOOGLE_PORTABILITY_SCOPES],
      clientId: "",
      clientSecret: "",
      redirectUri: "",
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      refreshToken: "",
      tokenType: "",
      expiryDate: "",
      archiveJobId: "",
      archiveState: "",
      archiveStartedAt: "",
      archiveExportTime: "",
      lastSyncAt: "",
      lastImportedAt: "",
    },
    outlook: {
      enabled: false,
      accountLabel: "",
      tenantId: "common",
      scopes: [...DEFAULT_OUTLOOK_SCOPES],
      clientId: "",
      redirectUri: "",
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      refreshToken: "",
      tokenType: "",
      expiryDate: "",
      lastSyncAt: "",
    },
    telegram: {
      enabled: false,
      mode: "bot",
      botToken: "",
      botUsername: "",
      allowedUserId: "",
      webSessionName: "default",
      webStatus: "idle",
      webAccountLabel: "",
      webLastReadyAt: "",
      webLastSyncAt: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
    },
    whatsapp: {
      enabled: false,
      mode: "web",
      accessToken: "",
      phoneNumberId: "",
      businessLabel: "",
      displayPhoneNumber: "",
      verifiedName: "",
      webSessionName: "default",
      webStatus: "idle",
      webAccountLabel: "",
      webLastReadyAt: "",
      webLastSyncAt: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      lastSyncAt: "",
    },
    x: {
      enabled: false,
      accountLabel: "",
      userId: "",
      clientId: "",
      clientSecret: "",
      redirectUri: "",
      scopes: ["tweet.read", "tweet.write", "users.read", "dm.read", "dm.write", "offline.access"],
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      refreshToken: "",
      tokenType: "",
      expiryDate: "",
      lastSyncAt: "",
    },
    linkedin: {
      enabled: false,
      mode: "official",
      accountLabel: "",
      userId: "",
      personUrn: "",
      email: "",
      clientId: "",
      clientSecret: "",
      redirectUri: "",
      scopes: [...DEFAULT_LINKEDIN_SCOPES],
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      tokenType: "",
      expiryDate: "",
      webSessionName: "default",
      webStatus: "idle",
      webAccountLabel: "",
      webLastReadyAt: "",
      webLastSyncAt: "",
      lastSyncAt: "",
    },
    instagram: {
      enabled: false,
      accountLabel: "",
      username: "",
      pageId: "",
      pageName: "",
      pageNameHint: "",
      instagramAccountId: "",
      clientId: "",
      clientSecret: "",
      redirectUri: "",
      scopes: [...DEFAULT_INSTAGRAM_SCOPES],
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
      accessToken: "",
      pageAccessToken: "",
      tokenType: "",
      expiryDate: "",
      lastSyncAt: "",
    },
    automation: defaultAutomationConfig(),
    updater: defaultUpdaterConfig(releaseChannel),
  };
}

function mergeDesktopConfig(current, patch) {
  const next = { ...current, ...patch };
  next.provider = { ...(current.provider || {}), ...(patch.provider || {}) };
  next.google = { ...(current.google || {}), ...(patch.google || {}) };
  next.googlePortability = { ...(current.googlePortability || {}), ...(patch.googlePortability || {}) };
  next.outlook = { ...(current.outlook || {}), ...(patch.outlook || {}) };
  next.telegram = { ...(current.telegram || {}), ...(patch.telegram || {}) };
  next.whatsapp = { ...(current.whatsapp || {}), ...(patch.whatsapp || {}) };
  next.x = { ...(current.x || {}), ...(patch.x || {}) };
  next.linkedin = { ...(current.linkedin || {}), ...(patch.linkedin || {}) };
  next.instagram = { ...(current.instagram || {}), ...(patch.instagram || {}) };
  next.automation = mergeAutomationConfig(current.automation, patch.automation);
  next.updater = {
    ...(current.updater || defaultUpdaterConfig(next.releaseChannel || current.releaseChannel || "")),
    ...(patch.updater || {}),
  };
  if (String(next.provider?.type || "") === "gemini") {
    next.provider.baseUrl = String(next.provider.baseUrl || "https://generativelanguage.googleapis.com/v1beta")
      .trim()
      .replace(/\/+$/, "")
      .replace(/\/openai$/i, "");
  }
  return next;
}

function maskSecret(value) {
  const text = String(value || "");
  if (!text) {
    return "";
  }
  if (text.length <= 8) {
    return `${"*".repeat(Math.max(0, text.length - 2))}${text.slice(-2)}`;
  }
  return `${text.slice(0, 3)}${"*".repeat(Math.max(0, text.length - 7))}${text.slice(-4)}`;
}

function sanitizeDesktopConfig(config) {
  const defaults = defaultDesktopConfig(repoRootFrom(__dirname), {
    storagePath: String(config?.storagePath || ""),
  });
  const normalized = mergeDesktopConfig(defaults, config || {});
  const provider = normalized.provider || {};
  const normalizedProviderModel = normalizeProviderModelValue(provider.type, provider.model, defaults.provider.model);
  const google = normalized.google || {};
  const googlePortability = normalized.googlePortability || {};
  const outlook = normalized.outlook || {};
  const telegram = normalized.telegram || {};
  const whatsapp = normalized.whatsapp || {};
  const x = normalized.x || {};
  const linkedin = normalized.linkedin || {};
  const instagram = normalized.instagram || {};
  const automation = normalized.automation || {};
  const whatsappMode = resolveWhatsAppMode(whatsapp, "web");
  const telegramMode = resolveTelegramMode(telegram, "bot");
  const linkedinMode = resolveLinkedInMode(linkedin, "official");
  return {
    appName: normalized.appName || defaults.appName,
    appVersion: normalized.appVersion || defaults.appVersion,
    officeId: normalized.officeId || defaults.officeId,
    deploymentMode: normalized.deploymentMode || defaults.deploymentMode,
    releaseChannel: normalized.releaseChannel || defaults.releaseChannel,
    locale: normalized.locale || defaults.locale,
    themeMode: normalized.themeMode || defaults.themeMode,
    themeAccent: normalized.themeAccent || defaults.themeAccent,
    chatFontSize: normalized.chatFontSize || defaults.chatFontSize,
    chatWallpaper: normalized.chatWallpaper || defaults.chatWallpaper,
    customWallpaper: normalized.customWallpaper || defaults.customWallpaper,
    selectedModelProfile: normalized.selectedModelProfile || defaults.selectedModelProfile,
    apiHost: normalized.apiHost || defaults.apiHost,
    apiPort: clampInteger(normalized.apiPort, 1, 65535, defaults.apiPort),
    apiBaseUrl: normalized.apiBaseUrl || defaults.apiBaseUrl,
    logLevel: normalized.logLevel || defaults.logLevel,
    storagePath: normalized.storagePath || defaults.storagePath,
    runtimeBootstrapKey: String(normalized.runtimeBootstrapKey || defaults.runtimeBootstrapKey || generateBootstrapKey()),
    envFile: normalized.envFile || defaults.envFile,
    scanOnStartup: Boolean(normalized.scanOnStartup),
    workspaceRootPath: normalized.workspaceRootPath || "",
    workspaceRootName: normalized.workspaceRootName || "",
    workspaceRootHash: normalized.workspaceRootHash || "",
    provider: {
      type: provider.type || "openai",
      authMode: provider.authMode || (provider.type === "openai-codex" ? "oauth" : "api-key"),
      baseUrl: provider.baseUrl || "",
      model: normalizedProviderModel,
      accountLabel: provider.accountLabel || "",
      availableModels: Array.isArray(provider.availableModels) ? provider.availableModels : [],
      oauthConnected: Boolean(provider.oauthConnected),
      oauthLastError: provider.oauthLastError || "",
      configuredAt: provider.configuredAt || "",
      lastValidatedAt: provider.lastValidatedAt || "",
      validationStatus: provider.validationStatus || "pending",
      apiKeyConfigured: Boolean(provider.apiKey),
      apiKeyMasked: maskSecret(provider.apiKey),
    },
    google: {
      enabled: Boolean(google.enabled),
      accountLabel: google.accountLabel || "",
      scopes: normalizeGoogleScopes(google.scopes),
      oauthConnected: Boolean(google.oauthConnected),
      oauthLastError: google.oauthLastError || "",
      configuredAt: google.configuredAt || "",
      lastValidatedAt: google.lastValidatedAt || "",
      validationStatus: google.validationStatus || "pending",
      accessTokenConfigured: Boolean(google.accessToken),
      refreshTokenConfigured: Boolean(google.refreshToken),
      clientIdConfigured: Boolean(google.clientId || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID),
      clientSecretConfigured: Boolean(google.clientSecret || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET),
    },
    googlePortability: {
      enabled: Boolean(googlePortability.enabled),
      accountLabel: googlePortability.accountLabel || "",
      scopes: normalizeGooglePortabilityScopes(googlePortability.scopes),
      oauthConnected: Boolean(googlePortability.oauthConnected),
      oauthLastError: googlePortability.oauthLastError || "",
      configuredAt: googlePortability.configuredAt || "",
      lastValidatedAt: googlePortability.lastValidatedAt || "",
      validationStatus: googlePortability.validationStatus || "pending",
      lastSyncAt: googlePortability.lastSyncAt || "",
      lastImportedAt: googlePortability.lastImportedAt || "",
      archiveJobId: googlePortability.archiveJobId || "",
      archiveState: googlePortability.archiveState || "",
      archiveStartedAt: googlePortability.archiveStartedAt || "",
      archiveExportTime: googlePortability.archiveExportTime || "",
      accessTokenConfigured: Boolean(googlePortability.accessToken),
      refreshTokenConfigured: Boolean(googlePortability.refreshToken),
      clientIdConfigured: Boolean(
        googlePortability.clientId
        || google.clientId
        || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID
        || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_ID,
      ),
      clientSecretConfigured: Boolean(
        googlePortability.clientSecret
        || google.clientSecret
        || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET
        || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_SECRET,
      ),
    },
    outlook: {
      enabled: Boolean(outlook.enabled),
      accountLabel: outlook.accountLabel || "",
      clientId: outlook.clientId || "",
      tenantId: outlook.tenantId || "common",
      scopes: normalizeOutlookScopes(outlook.scopes),
      oauthConnected: Boolean(outlook.oauthConnected),
      oauthLastError: outlook.oauthLastError || "",
      configuredAt: outlook.configuredAt || "",
      lastValidatedAt: outlook.lastValidatedAt || "",
      validationStatus: outlook.validationStatus || "pending",
      lastSyncAt: outlook.lastSyncAt || "",
      accessTokenConfigured: Boolean(outlook.accessToken),
      refreshTokenConfigured: Boolean(outlook.refreshToken),
      clientIdConfigured: Boolean(outlook.clientId || process.env.LAWCOPILOT_OUTLOOK_CLIENT_ID),
    },
    telegram: {
      enabled: Boolean(telegram.enabled),
      mode: telegramMode,
      botUsername: telegram.botUsername || "",
      allowedUserId: telegram.allowedUserId || "",
      webSessionName: telegram.webSessionName || "default",
      webStatus: telegram.webStatus || (telegramMode === "web" && telegram.enabled ? "idle" : "pending"),
      webAccountLabel: telegram.webAccountLabel || "",
      webLastReadyAt: telegram.webLastReadyAt || "",
      webLastSyncAt: telegram.webLastSyncAt || "",
      configuredAt: telegram.configuredAt || "",
      lastValidatedAt: telegram.lastValidatedAt || "",
      validationStatus: telegram.validationStatus || "pending",
      botTokenConfigured: Boolean(telegram.botToken),
      botTokenMasked: maskSecret(telegram.botToken),
    },
    whatsapp: {
      enabled: Boolean(whatsapp.enabled),
      mode: whatsappMode,
      businessLabel: whatsapp.businessLabel || "",
      displayPhoneNumber: whatsapp.displayPhoneNumber || "",
      verifiedName: whatsapp.verifiedName || "",
      phoneNumberId: whatsapp.phoneNumberId || "",
      webSessionName: whatsapp.webSessionName || "default",
      webStatus: whatsapp.webStatus || (whatsappMode === "web" && whatsapp.enabled ? "idle" : "pending"),
      webAccountLabel: whatsapp.webAccountLabel || "",
      webLastReadyAt: whatsapp.webLastReadyAt || "",
      webLastSyncAt: whatsapp.webLastSyncAt || "",
      configuredAt: whatsapp.configuredAt || "",
      lastValidatedAt: whatsapp.lastValidatedAt || "",
      validationStatus: whatsapp.validationStatus || "pending",
      lastSyncAt: whatsapp.lastSyncAt || "",
      accessTokenConfigured: Boolean(whatsapp.accessToken),
      accessTokenMasked: maskSecret(whatsapp.accessToken),
    },
    x: {
      enabled: Boolean(x.enabled),
      accountLabel: x.accountLabel || "",
      userId: x.userId || "",
      scopes: Array.isArray(x.scopes) ? x.scopes : [],
      oauthConnected: Boolean(x.oauthConnected),
      oauthLastError: x.oauthLastError || "",
      configuredAt: x.configuredAt || "",
      lastValidatedAt: x.lastValidatedAt || "",
      validationStatus: x.validationStatus || "pending",
      lastSyncAt: x.lastSyncAt || "",
      accessTokenConfigured: Boolean(x.accessToken),
      refreshTokenConfigured: Boolean(x.refreshToken),
      clientIdConfigured: Boolean(x.clientId || process.env.LAWCOPILOT_X_CLIENT_ID),
      clientSecretConfigured: Boolean(x.clientSecret || process.env.LAWCOPILOT_X_CLIENT_SECRET),
    },
    linkedin: {
      enabled: Boolean(linkedin.enabled),
      mode: linkedinMode,
      accountLabel: linkedin.accountLabel || "",
      userId: linkedin.userId || "",
      personUrn: linkedin.personUrn || "",
      email: linkedin.email || "",
      scopes: normalizeLinkedInScopes(linkedin.scopes),
      oauthConnected: Boolean(linkedin.oauthConnected),
      oauthLastError: linkedin.oauthLastError || "",
      configuredAt: linkedin.configuredAt || "",
      lastValidatedAt: linkedin.lastValidatedAt || "",
      validationStatus: linkedin.validationStatus || "pending",
      lastSyncAt: linkedin.lastSyncAt || "",
      webSessionName: linkedin.webSessionName || "default",
      webStatus: linkedin.webStatus || (linkedinMode === "web" && linkedin.enabled ? "idle" : "pending"),
      webAccountLabel: linkedin.webAccountLabel || "",
      webLastReadyAt: linkedin.webLastReadyAt || "",
      webLastSyncAt: linkedin.webLastSyncAt || "",
      accessTokenConfigured: Boolean(linkedin.accessToken),
      clientIdConfigured: Boolean(linkedin.clientId || process.env.LAWCOPILOT_LINKEDIN_CLIENT_ID),
      clientSecretConfigured: Boolean(linkedin.clientSecret || process.env.LAWCOPILOT_LINKEDIN_CLIENT_SECRET),
    },
    instagram: {
      enabled: Boolean(instagram.enabled),
      accountLabel: instagram.accountLabel || "",
      username: instagram.username || "",
      pageId: instagram.pageId || "",
      pageName: instagram.pageName || "",
      pageNameHint: instagram.pageNameHint || "",
      instagramAccountId: instagram.instagramAccountId || "",
      scopes: normalizeInstagramScopes(instagram.scopes),
      oauthConnected: Boolean(instagram.oauthConnected),
      oauthLastError: instagram.oauthLastError || "",
      configuredAt: instagram.configuredAt || "",
      lastValidatedAt: instagram.lastValidatedAt || "",
      validationStatus: instagram.validationStatus || "pending",
      lastSyncAt: instagram.lastSyncAt || "",
      accessTokenConfigured: Boolean(instagram.accessToken || instagram.pageAccessToken),
      clientIdConfigured: Boolean(instagram.clientId || process.env.LAWCOPILOT_INSTAGRAM_CLIENT_ID),
      clientSecretConfigured: Boolean(instagram.clientSecret || process.env.LAWCOPILOT_INSTAGRAM_CLIENT_SECRET),
    },
    automation: sanitizeAutomationConfig(automation),
    updater: normalizeUpdaterConfigForWrite(normalized.updater, normalized.releaseChannel),
  };
}

function resolveConfigDir(options = {}) {
  if (options.overrideDir) {
    return options.overrideDir;
  }
  if (process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR) {
    return process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR;
  }
  return path.join(os.homedir(), ".config", "LawCopilot");
}

function defaultRuntimeBootstrapKey(options = {}) {
  const configDir = resolveConfigDir(options);
  const cached = bootstrapKeyCache.get(configDir);
  if (cached) {
    return cached;
  }
  const generated = String(process.env.LAWCOPILOT_BOOTSTRAP_ADMIN_KEY || "").trim() || generateBootstrapKey();
  bootstrapKeyCache.set(configDir, generated);
  return generated;
}

function configFilePath(options = {}) {
  return path.join(resolveConfigDir(options), "desktop-config.json");
}

function loadDesktopConfig(options = {}) {
  const repoRoot = options.repoRoot || repoRootFrom(__dirname);
  const defaults = defaultDesktopConfig(repoRoot, options);
  const filePath = configFilePath(options);
  if (!fs.existsSync(filePath)) {
    return defaults;
  }
  try {
    const merged = mergeDesktopConfig(defaults, JSON.parse(fs.readFileSync(filePath, "utf-8")));
    bootstrapKeyCache.set(resolveConfigDir(options), String(merged.runtimeBootstrapKey || defaults.runtimeBootstrapKey || ""));
    return merged;
  } catch {
    return defaults;
  }
}

function saveDesktopConfig(patch, options = {}) {
  const dir = resolveConfigDir(options);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const repoRoot = options.repoRoot || repoRootFrom(__dirname);
  const defaults = defaultDesktopConfig(repoRoot, options);
  const current = mergeDesktopConfig(defaults, loadDesktopConfig(options));
  const next = mergeDesktopConfig(current, patch || {});
  if (next.storagePath && (!next.envFile || next.envFile.startsWith(path.join(current.storagePath || "", "runtime")))) {
    next.envFile = path.join(next.storagePath, "runtime", "pilot.env");
  }
  const normalized = {
    appName: String(next.appName || defaults.appName),
    appVersion: String(next.appVersion || defaults.appVersion),
    officeId: String(next.officeId || defaults.officeId),
    deploymentMode: String(next.deploymentMode || defaults.deploymentMode),
    releaseChannel: String(next.releaseChannel || defaults.releaseChannel),
    locale: String(next.locale || defaults.locale),
    themeMode: String(next.themeMode || defaults.themeMode),
    themeAccent: String(next.themeAccent || defaults.themeAccent),
    chatFontSize: String(next.chatFontSize || defaults.chatFontSize),
    chatWallpaper: String(next.chatWallpaper || defaults.chatWallpaper),
    customWallpaper: String(next.customWallpaper || defaults.customWallpaper),
    selectedModelProfile: String(next.selectedModelProfile || defaults.selectedModelProfile),
    apiHost: String(next.apiHost || defaults.apiHost),
    apiPort: clampInteger(next.apiPort, 1, 65535, defaults.apiPort),
    apiBaseUrl: String(next.apiBaseUrl || defaults.apiBaseUrl),
    logLevel: String(next.logLevel || defaults.logLevel),
    storagePath: String(next.storagePath || defaults.storagePath),
    runtimeBootstrapKey: String(next.runtimeBootstrapKey || defaults.runtimeBootstrapKey || generateBootstrapKey()),
    envFile: String(next.envFile || defaults.envFile),
    scanOnStartup: Boolean(next.scanOnStartup),
    workspaceRootPath: String(next.workspaceRootPath || ""),
    workspaceRootName: String(next.workspaceRootName || ""),
    workspaceRootHash: String(next.workspaceRootHash || ""),
    provider: {
      type: String(next.provider?.type || defaults.provider.type),
      authMode: String(next.provider?.authMode || defaults.provider.authMode),
      baseUrl: String(next.provider?.baseUrl || defaults.provider.baseUrl),
      model: normalizeProviderModelValue(
        String(next.provider?.type || defaults.provider.type),
        String(next.provider?.model || ""),
        defaults.provider.model,
      ),
      apiKey: String(next.provider?.apiKey || ""),
      accountLabel: String(next.provider?.accountLabel || defaults.provider.accountLabel),
      availableModels: Array.isArray(next.provider?.availableModels) ? next.provider.availableModels : [],
      oauthConnected: Boolean(next.provider?.oauthConnected),
      oauthLastError: String(next.provider?.oauthLastError || ""),
      configuredAt: String(next.provider?.configuredAt || ""),
      lastValidatedAt: String(next.provider?.lastValidatedAt || ""),
      validationStatus: String(next.provider?.validationStatus || "pending"),
    },
    google: {
      enabled: Boolean(next.google?.enabled),
      accountLabel: String(next.google?.accountLabel || ""),
      scopes: normalizeGoogleScopes(next.google?.scopes),
      clientId: String(next.google?.clientId || ""),
      clientSecret: String(next.google?.clientSecret || ""),
      redirectUri: String(next.google?.redirectUri || ""),
      oauthConnected: Boolean(next.google?.oauthConnected),
      oauthLastError: String(next.google?.oauthLastError || ""),
      configuredAt: String(next.google?.configuredAt || ""),
      lastValidatedAt: String(next.google?.lastValidatedAt || ""),
      validationStatus: String(next.google?.validationStatus || "pending"),
      accessToken: String(next.google?.accessToken || ""),
      refreshToken: String(next.google?.refreshToken || ""),
      tokenType: String(next.google?.tokenType || ""),
      expiryDate: String(next.google?.expiryDate || ""),
    },
    googlePortability: {
      enabled: Boolean(next.googlePortability?.enabled),
      accountLabel: String(next.googlePortability?.accountLabel || ""),
      scopes: normalizeGooglePortabilityScopes(next.googlePortability?.scopes),
      clientId: String(next.googlePortability?.clientId || ""),
      clientSecret: String(next.googlePortability?.clientSecret || ""),
      redirectUri: String(next.googlePortability?.redirectUri || ""),
      oauthConnected: Boolean(next.googlePortability?.oauthConnected),
      oauthLastError: String(next.googlePortability?.oauthLastError || ""),
      configuredAt: String(next.googlePortability?.configuredAt || ""),
      lastValidatedAt: String(next.googlePortability?.lastValidatedAt || ""),
      validationStatus: String(next.googlePortability?.validationStatus || "pending"),
      accessToken: String(next.googlePortability?.accessToken || ""),
      refreshToken: String(next.googlePortability?.refreshToken || ""),
      tokenType: String(next.googlePortability?.tokenType || ""),
      expiryDate: String(next.googlePortability?.expiryDate || ""),
      archiveJobId: String(next.googlePortability?.archiveJobId || ""),
      archiveState: String(next.googlePortability?.archiveState || ""),
      archiveStartedAt: String(next.googlePortability?.archiveStartedAt || ""),
      archiveExportTime: String(next.googlePortability?.archiveExportTime || ""),
      lastSyncAt: String(next.googlePortability?.lastSyncAt || ""),
      lastImportedAt: String(next.googlePortability?.lastImportedAt || ""),
    },
    outlook: {
      enabled: Boolean(next.outlook?.enabled),
      accountLabel: String(next.outlook?.accountLabel || ""),
      tenantId: String(next.outlook?.tenantId || defaults.outlook.tenantId),
      scopes: normalizeOutlookScopes(next.outlook?.scopes),
      clientId: String(next.outlook?.clientId || ""),
      redirectUri: String(next.outlook?.redirectUri || ""),
      oauthConnected: Boolean(next.outlook?.oauthConnected),
      oauthLastError: String(next.outlook?.oauthLastError || ""),
      configuredAt: String(next.outlook?.configuredAt || ""),
      lastValidatedAt: String(next.outlook?.lastValidatedAt || ""),
      validationStatus: String(next.outlook?.validationStatus || "pending"),
      accessToken: String(next.outlook?.accessToken || ""),
      refreshToken: String(next.outlook?.refreshToken || ""),
      tokenType: String(next.outlook?.tokenType || ""),
      expiryDate: String(next.outlook?.expiryDate || ""),
      lastSyncAt: String(next.outlook?.lastSyncAt || ""),
    },
    telegram: {
      enabled: Boolean(next.telegram?.enabled),
      mode: resolveTelegramMode(next.telegram, defaults.telegram.mode),
      botToken: String(next.telegram?.botToken || ""),
      botUsername: String(next.telegram?.botUsername || ""),
      allowedUserId: String(next.telegram?.allowedUserId || ""),
      webSessionName: String(next.telegram?.webSessionName || defaults.telegram.webSessionName || "default"),
      webStatus: String(next.telegram?.webStatus || defaults.telegram.webStatus || "idle"),
      webAccountLabel: String(next.telegram?.webAccountLabel || ""),
      webLastReadyAt: String(next.telegram?.webLastReadyAt || ""),
      webLastSyncAt: String(next.telegram?.webLastSyncAt || ""),
      configuredAt: String(next.telegram?.configuredAt || ""),
      lastValidatedAt: String(next.telegram?.lastValidatedAt || ""),
      validationStatus: String(next.telegram?.validationStatus || "pending"),
    },
    whatsapp: {
      enabled: Boolean(next.whatsapp?.enabled),
      mode: resolveWhatsAppMode(next.whatsapp, defaults.whatsapp.mode),
      accessToken: String(next.whatsapp?.accessToken || ""),
      phoneNumberId: String(next.whatsapp?.phoneNumberId || ""),
      businessLabel: String(next.whatsapp?.businessLabel || ""),
      displayPhoneNumber: String(next.whatsapp?.displayPhoneNumber || ""),
      verifiedName: String(next.whatsapp?.verifiedName || ""),
      webSessionName: String(next.whatsapp?.webSessionName || defaults.whatsapp.webSessionName),
      webStatus: String(next.whatsapp?.webStatus || defaults.whatsapp.webStatus),
      webAccountLabel: String(next.whatsapp?.webAccountLabel || ""),
      webLastReadyAt: String(next.whatsapp?.webLastReadyAt || ""),
      webLastSyncAt: String(next.whatsapp?.webLastSyncAt || ""),
      configuredAt: String(next.whatsapp?.configuredAt || ""),
      lastValidatedAt: String(next.whatsapp?.lastValidatedAt || ""),
      validationStatus: String(next.whatsapp?.validationStatus || "pending"),
      lastSyncAt: String(next.whatsapp?.lastSyncAt || ""),
    },
    x: {
      enabled: Boolean(next.x?.enabled),
      accountLabel: String(next.x?.accountLabel || ""),
      userId: String(next.x?.userId || ""),
      clientId: String(next.x?.clientId || ""),
      clientSecret: String(next.x?.clientSecret || ""),
      redirectUri: String(next.x?.redirectUri || ""),
      scopes: normalizeStringList(Array.isArray(next.x?.scopes) ? next.x.scopes : []),
      oauthConnected: Boolean(next.x?.oauthConnected),
      oauthLastError: String(next.x?.oauthLastError || ""),
      configuredAt: String(next.x?.configuredAt || ""),
      lastValidatedAt: String(next.x?.lastValidatedAt || ""),
      validationStatus: String(next.x?.validationStatus || "pending"),
      accessToken: String(next.x?.accessToken || ""),
      refreshToken: String(next.x?.refreshToken || ""),
      tokenType: String(next.x?.tokenType || ""),
      expiryDate: String(next.x?.expiryDate || ""),
      lastSyncAt: String(next.x?.lastSyncAt || ""),
    },
    linkedin: {
      enabled: Boolean(next.linkedin?.enabled),
      mode: resolveLinkedInMode(next.linkedin, defaults.linkedin.mode),
      accountLabel: String(next.linkedin?.accountLabel || ""),
      userId: String(next.linkedin?.userId || ""),
      personUrn: String(next.linkedin?.personUrn || ""),
      email: String(next.linkedin?.email || ""),
      clientId: String(next.linkedin?.clientId || ""),
      clientSecret: String(next.linkedin?.clientSecret || ""),
      redirectUri: String(next.linkedin?.redirectUri || ""),
      scopes: normalizeLinkedInScopes(next.linkedin?.scopes),
      oauthConnected: Boolean(next.linkedin?.oauthConnected),
      oauthLastError: String(next.linkedin?.oauthLastError || ""),
      configuredAt: String(next.linkedin?.configuredAt || ""),
      lastValidatedAt: String(next.linkedin?.lastValidatedAt || ""),
      validationStatus: String(next.linkedin?.validationStatus || "pending"),
      accessToken: String(next.linkedin?.accessToken || ""),
      tokenType: String(next.linkedin?.tokenType || ""),
      expiryDate: String(next.linkedin?.expiryDate || ""),
      webSessionName: String(next.linkedin?.webSessionName || defaults.linkedin.webSessionName || "default"),
      webStatus: String(next.linkedin?.webStatus || defaults.linkedin.webStatus || "idle"),
      webAccountLabel: String(next.linkedin?.webAccountLabel || ""),
      webLastReadyAt: String(next.linkedin?.webLastReadyAt || ""),
      webLastSyncAt: String(next.linkedin?.webLastSyncAt || ""),
      lastSyncAt: String(next.linkedin?.lastSyncAt || ""),
    },
    instagram: {
      enabled: Boolean(next.instagram?.enabled),
      accountLabel: String(next.instagram?.accountLabel || ""),
      username: String(next.instagram?.username || ""),
      pageId: String(next.instagram?.pageId || ""),
      pageName: String(next.instagram?.pageName || ""),
      pageNameHint: String(next.instagram?.pageNameHint || ""),
      instagramAccountId: String(next.instagram?.instagramAccountId || ""),
      clientId: String(next.instagram?.clientId || ""),
      clientSecret: String(next.instagram?.clientSecret || ""),
      redirectUri: String(next.instagram?.redirectUri || ""),
      scopes: normalizeInstagramScopes(next.instagram?.scopes),
      oauthConnected: Boolean(next.instagram?.oauthConnected),
      oauthLastError: String(next.instagram?.oauthLastError || ""),
      configuredAt: String(next.instagram?.configuredAt || ""),
      lastValidatedAt: String(next.instagram?.lastValidatedAt || ""),
      validationStatus: String(next.instagram?.validationStatus || "pending"),
      accessToken: String(next.instagram?.accessToken || ""),
      pageAccessToken: String(next.instagram?.pageAccessToken || ""),
      tokenType: String(next.instagram?.tokenType || ""),
      expiryDate: String(next.instagram?.expiryDate || ""),
      lastSyncAt: String(next.instagram?.lastSyncAt || ""),
    },
    automation: normalizeAutomationConfigForWrite(next.automation),
    updater: normalizeUpdaterConfigForWrite(next.updater, next.releaseChannel || defaults.releaseChannel),
  };
  bootstrapKeyCache.set(dir, normalized.runtimeBootstrapKey);
  fs.writeFileSync(configFilePath(options), JSON.stringify(normalized, null, 2), { mode: 0o600 });
  return normalized;
}

function resolveRuntimePaths(options = {}) {
  const repoRoot = options.repoRoot || repoRootFrom(__dirname);
  const isPackaged = Boolean(options.isPackaged);
  const resourcesPath = options.resourcesPath || path.join(repoRoot, "apps", "desktop");
  const artifactsRoot =
    options.artifactsRoot
    || (isPackaged ? path.join(options.userDataPath || path.join(os.homedir(), ".config", "LawCopilot"), "artifacts") : path.join(repoRoot, "artifacts"));
  return {
    repoRoot,
    uiDist: isPackaged ? path.join(resourcesPath, "ui-dist") : path.join(repoRoot, "apps", "ui", "dist"),
    apiRoot: isPackaged ? path.join(resourcesPath, "api-bin") : path.join(repoRoot, "apps", "api"),
    backendBinRoot: isPackaged ? path.join(resourcesPath, "api-bin") : path.join(repoRoot, "apps", "api", "dist"),
    browserWorkerRoot: isPackaged ? path.join(resourcesPath, "browser-worker") : path.join(repoRoot, "apps", "browser-worker"),
    artifactsRoot,
    isPackaged,
  };
}

module.exports = {
  configFilePath,
  defaultAutomationConfig,
  defaultDesktopConfig,
  loadDesktopConfig,
  mergeAutomationConfig,
  normalizeAutomationConfigForWrite,
  normalizeGooglePortabilityScopes,
  normalizeInstagramScopes,
  normalizeUpdaterConfigForWrite,
  normalizeOutlookScopes,
  resolveConfigDir,
  resolveRuntimePaths,
  sanitizeAutomationConfig,
  sanitizeDesktopConfig,
  saveDesktopConfig
};
