function nowIso() {
  return new Date().toISOString();
}

function normalizeFeedUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function summarizeReleaseNotes(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => summarizeReleaseNotes(item))
      .filter(Boolean)
      .join("\n\n")
      .trim();
  }
  if (value && typeof value === "object") {
    return summarizeReleaseNotes(value.note || value.body || value.text || "");
  }
  return String(value || "").trim();
}

function describeUpdateSupport(options = {}) {
  const isPackaged = Boolean(options.isPackaged);
  const platform = String(options.platform || process.platform);
  const appImagePath = String(options.appImagePath || process.env.APPIMAGE || "").trim();
  if (!isPackaged) {
    return {
      supported: false,
      reason: "not_packaged",
      message: "Otomatik güncelleme yalnız kurulu masaüstü paketlerinde çalışır.",
    };
  }
  if (platform === "linux" && !appImagePath) {
    return {
      supported: false,
      reason: "linux_non_appimage",
      message: "Linux otomatik güncelleme için AppImage kurulum paketi gerekir.",
    };
  }
  return {
    supported: true,
    reason: "",
    message: "",
  };
}

function buildDefaultStatus(currentVersion = "") {
  return {
    status: "idle",
    configured: false,
    supported: false,
    support_reason: "",
    support_message: "",
    current_version: String(currentVersion || "").trim(),
    available_version: "",
    downloaded_version: "",
    channel: "latest",
    feed_url: "",
    auto_check_on_launch: true,
    auto_download: false,
    allow_prerelease: false,
    last_checked_at: "",
    last_error: "",
    release_notes: "",
    download_percent: 0,
    update_downloaded_at: "",
  };
}

function applyUpdaterConfigToStatus(status, config, support) {
  return {
    ...status,
    configured: Boolean(config.enabled && config.feedUrl),
    supported: Boolean(support.supported),
    support_reason: String(support.reason || ""),
    support_message: String(support.message || ""),
    feed_url: normalizeFeedUrl(config.feedUrl),
    channel: String(config.channel || "latest"),
    auto_check_on_launch: Boolean(config.autoCheckOnLaunch),
    auto_download: Boolean(config.autoDownload),
    allow_prerelease: Boolean(config.allowPrerelease),
    last_checked_at: String(config.lastCheckedAt || status.last_checked_at || ""),
    last_error: String(config.lastError || status.last_error || ""),
    available_version: String(config.lastAvailableVersion || status.available_version || ""),
    downloaded_version: String(config.lastDownloadedVersion || status.downloaded_version || ""),
  };
}

function createDesktopUpdater(options = {}) {
  const appRef = options.app;
  const updater = options.autoUpdater || require("electron-updater").autoUpdater;
  const loadConfig = typeof options.loadConfig === "function" ? options.loadConfig : () => ({});
  const saveConfig = typeof options.saveConfig === "function" ? options.saveConfig : null;
  const getMainWindow = typeof options.getMainWindow === "function" ? options.getMainWindow : () => null;
  const notify = typeof options.notify === "function" ? options.notify : null;
  const log = typeof options.log === "function" ? options.log : () => {};
  let listenersBound = false;
  let state = buildDefaultStatus(appRef?.getVersion?.() || "");

  function persistUpdaterPatch(patch) {
    if (!saveConfig) {
      return;
    }
    try {
      saveConfig({ updater: patch || {} });
    } catch (error) {
      log("persist_failed", error);
    }
  }

  function broadcast() {
    const targetWindow = getMainWindow();
    if (!targetWindow || targetWindow.isDestroyed()) {
      return;
    }
    targetWindow.webContents.send("lawcopilot:update-status", state);
  }

  function updateState(patch) {
    state = {
      ...state,
      ...patch,
      current_version: String(appRef?.getVersion?.() || state.current_version || "").trim(),
    };
    broadcast();
    return state;
  }

  function refreshFromConfig() {
    const config = loadConfig() || {};
    const updaterConfig = config.updater && typeof config.updater === "object" ? config.updater : {};
    const support = describeUpdateSupport({
      isPackaged: appRef?.isPackaged,
      platform: process.platform,
      appImagePath: process.env.APPIMAGE,
    });
    const nextConfig = {
      enabled: updaterConfig.enabled ?? true,
      feedUrl: normalizeFeedUrl(updaterConfig.feedUrl),
      channel: String(updaterConfig.channel || "latest").trim() || "latest",
      autoCheckOnLaunch: updaterConfig.autoCheckOnLaunch ?? true,
      autoDownload: updaterConfig.autoDownload ?? false,
      allowPrerelease: updaterConfig.allowPrerelease ?? String(config.releaseChannel || "").trim().toLowerCase() === "pilot",
      lastCheckedAt: String(updaterConfig.lastCheckedAt || "").trim(),
      lastAvailableVersion: String(updaterConfig.lastAvailableVersion || "").trim(),
      lastDownloadedVersion: String(updaterConfig.lastDownloadedVersion || "").trim(),
      lastError: String(updaterConfig.lastError || "").trim(),
    };

    updater.autoDownload = Boolean(nextConfig.autoDownload);
    updater.autoInstallOnAppQuit = false;
    if (Object.prototype.hasOwnProperty.call(updater, "allowPrerelease")) {
      updater.allowPrerelease = Boolean(nextConfig.allowPrerelease);
    }

    if (support.supported && nextConfig.enabled && nextConfig.feedUrl) {
      updater.setFeedURL({
        provider: "generic",
        url: nextConfig.feedUrl,
        channel: nextConfig.channel,
        useMultipleRangeRequest: false,
      });
    }

    state = applyUpdaterConfigToStatus(state, nextConfig, support);
    state.current_version = String(appRef?.getVersion?.() || state.current_version || "").trim();
    broadcast();
    return { config: nextConfig, support };
  }

  function bindListeners() {
    if (listenersBound) {
      return;
    }
    listenersBound = true;

    updater.on("checking-for-update", () => {
      updateState({
        status: "checking",
        last_error: "",
        download_percent: 0,
      });
    });

    updater.on("update-available", (info) => {
      const checkedAt = nowIso();
      const availableVersion = String(info?.version || "").trim();
      const releaseNotes = summarizeReleaseNotes(info?.releaseNotes);
      persistUpdaterPatch({
        lastCheckedAt: checkedAt,
        lastAvailableVersion: availableVersion,
        lastError: "",
      });
      updateState({
        status: "available",
        available_version: availableVersion,
        last_checked_at: checkedAt,
        last_error: "",
        release_notes: releaseNotes,
      });
    });

    updater.on("update-not-available", () => {
      const checkedAt = nowIso();
      persistUpdaterPatch({
        lastCheckedAt: checkedAt,
        lastAvailableVersion: "",
        lastError: "",
      });
      updateState({
        status: "no_update",
        available_version: "",
        downloaded_version: "",
        last_checked_at: checkedAt,
        last_error: "",
        release_notes: "",
        download_percent: 0,
      });
    });

    updater.on("download-progress", (progress) => {
      updateState({
        status: "downloading",
        download_percent: Number(progress?.percent || 0),
      });
    });

    updater.on("update-downloaded", (info) => {
      const downloadedAt = nowIso();
      const downloadedVersion = String(info?.version || state.available_version || "").trim();
      const releaseNotes = summarizeReleaseNotes(info?.releaseNotes || state.release_notes);
      persistUpdaterPatch({
        lastCheckedAt: downloadedAt,
        lastAvailableVersion: downloadedVersion,
        lastDownloadedVersion: downloadedVersion,
        lastError: "",
      });
      updateState({
        status: "downloaded",
        downloaded_version: downloadedVersion,
        available_version: downloadedVersion,
        update_downloaded_at: downloadedAt,
        last_checked_at: downloadedAt,
        last_error: "",
        release_notes: releaseNotes,
        download_percent: 100,
      });
      if (notify) {
        notify(
          "Yeni sürüm hazır",
          "LawCopilot güncellemesi indirildi. Uygulamayı yeniden başlatıp kurabilirsiniz.",
        );
      }
    });

    updater.on("error", (error) => {
      const checkedAt = nowIso();
      const detail = String(error?.message || error || "unknown_update_error").trim();
      persistUpdaterPatch({
        lastCheckedAt: checkedAt,
        lastError: detail,
      });
      updateState({
        status: "error",
        last_checked_at: checkedAt,
        last_error: detail,
      });
    });
  }

  async function checkForUpdates(trigger = "manual") {
    bindListeners();
    const { config, support } = refreshFromConfig();
    if (!config.enabled) {
      return updateState({
        status: "disabled",
        last_error: "",
        download_percent: 0,
      });
    }
    if (!support.supported) {
      return updateState({
        status: "unsupported",
        last_error: "",
        download_percent: 0,
      });
    }
    if (!config.feedUrl) {
      return updateState({
        status: "unconfigured",
        last_error: "",
        download_percent: 0,
      });
    }
    log("check_for_updates", trigger);
    try {
      await updater.checkForUpdates();
      return state;
    } catch (error) {
      const detail = String(error?.message || error || "update_check_failed").trim();
      persistUpdaterPatch({
        lastCheckedAt: nowIso(),
        lastError: detail,
      });
      return updateState({
        status: "error",
        last_checked_at: nowIso(),
        last_error: detail,
      });
    }
  }

  async function downloadUpdate() {
    bindListeners();
    const { config, support } = refreshFromConfig();
    if (!config.enabled) {
      return updateState({ status: "disabled" });
    }
    if (!support.supported) {
      return updateState({ status: "unsupported" });
    }
    if (!config.feedUrl) {
      return updateState({ status: "unconfigured" });
    }
    try {
      updateState({
        status: "downloading",
        last_error: "",
        download_percent: 0,
      });
      await updater.downloadUpdate();
      return state;
    } catch (error) {
      const detail = String(error?.message || error || "update_download_failed").trim();
      persistUpdaterPatch({ lastError: detail });
      return updateState({
        status: "error",
        last_error: detail,
      });
    }
  }

  function quitAndInstall() {
    if (state.status !== "downloaded") {
      return {
        ok: false,
        status: state,
      };
    }
    setImmediate(() => {
      updater.quitAndInstall(false, true);
    });
    return {
      ok: true,
      status: state,
    };
  }

  function getStatus() {
    refreshFromConfig();
    return state;
  }

  async function maybeAutoCheckOnLaunch() {
    const { config, support } = refreshFromConfig();
    if (!config.enabled || !config.autoCheckOnLaunch || !config.feedUrl || !support.supported) {
      return state;
    }
    return checkForUpdates("launch");
  }

  refreshFromConfig();

  return {
    checkForUpdates,
    downloadUpdate,
    getStatus,
    maybeAutoCheckOnLaunch,
    quitAndInstall,
    refreshFromConfig,
  };
}

module.exports = {
  buildDefaultStatus,
  createDesktopUpdater,
  describeUpdateSupport,
  summarizeReleaseNotes,
};
