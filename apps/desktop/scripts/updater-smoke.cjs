#!/usr/bin/env node
const assert = require("assert");
const { EventEmitter } = require("events");

const { normalizeUpdaterConfigForWrite } = require("../lib/config.cjs");
const { createDesktopUpdater, describeUpdateSupport, summarizeReleaseNotes } = require("../lib/updater.cjs");

class FakeAutoUpdater extends EventEmitter {
  constructor() {
    super();
    this.feedOptions = null;
    this.autoDownload = false;
    this.autoInstallOnAppQuit = false;
    this.allowPrerelease = false;
    this.quitAndInstallCalls = 0;
  }

  setFeedURL(options) {
    this.feedOptions = options;
  }

  async checkForUpdates() {
    this.emit("checking-for-update");
    this.emit("update-available", {
      version: "0.8.0-pilot.1",
      releaseNotes: "Yeni otomatik güncelleme testi",
    });
    return {
      updateInfo: {
        version: "0.8.0-pilot.1",
      },
    };
  }

  async downloadUpdate() {
    this.emit("download-progress", { percent: 42.5 });
    this.emit("update-downloaded", {
      version: "0.8.0-pilot.1",
      releaseNotes: "Yeni otomatik güncelleme testi",
    });
    return ["LawCopilot-0.8.0-pilot.1.AppImage"];
  }

  quitAndInstall() {
    this.quitAndInstallCalls += 1;
  }
}

async function main() {
  const notPackaged = describeUpdateSupport({ isPackaged: false, platform: "linux" });
  assert.strictEqual(notPackaged.supported, false);
  assert.strictEqual(notPackaged.reason, "not_packaged");

  const linuxWithoutAppImage = describeUpdateSupport({ isPackaged: true, platform: "linux", appImagePath: "" });
  assert.strictEqual(linuxWithoutAppImage.supported, false);
  assert.strictEqual(linuxWithoutAppImage.reason, "linux_non_appimage");

  const normalizedUpdater = normalizeUpdaterConfigForWrite({
    enabled: true,
    feedUrl: " https://updates.example.com/lawcopilot/ ",
    channel: "pilot",
    autoCheckOnLaunch: true,
    autoDownload: false,
    allowPrerelease: true,
  }, "pilot");
  assert.strictEqual(normalizedUpdater.feedUrl, "https://updates.example.com/lawcopilot/");
  assert.strictEqual(normalizedUpdater.channel, "pilot");

  assert.strictEqual(
    summarizeReleaseNotes([{ note: "Madde 1" }, { body: "Madde 2" }]),
    "Madde 1\n\nMadde 2",
  );

  const fakeAutoUpdater = new FakeAutoUpdater();
  const events = [];
  const previousAppImage = process.env.APPIMAGE;
  process.env.APPIMAGE = "/tmp/LawCopilot.AppImage";
  const configStore = {
    releaseChannel: "pilot",
    updater: {
      enabled: true,
      provider: "github",
      githubOwner: "Yosemiteee",
      githubRepo: "LawCopilot",
      feedUrl: "",
      channel: "pilot",
      autoCheckOnLaunch: true,
      autoDownload: false,
      allowPrerelease: true,
      lastCheckedAt: "",
      lastAvailableVersion: "",
      lastDownloadedVersion: "",
      lastError: "",
    },
  };

  const desktopUpdater = createDesktopUpdater({
    app: {
      isPackaged: true,
      getVersion: () => "0.7.0-pilot.3",
    },
    autoUpdater: fakeAutoUpdater,
    loadConfig: () => configStore,
    saveConfig: (patch) => {
      configStore.updater = {
        ...configStore.updater,
        ...(patch.updater || {}),
      };
      return configStore;
    },
    getMainWindow: () => ({
      isDestroyed: () => false,
      webContents: {
        send: (_channel, payload) => {
          events.push(payload);
        },
      },
    }),
  });

  const initialStatus = desktopUpdater.getStatus();
  assert.strictEqual(initialStatus.configured, true);
  assert.strictEqual(initialStatus.supported, true);
  assert.strictEqual(fakeAutoUpdater.feedOptions.provider, "github");
  assert.strictEqual(fakeAutoUpdater.feedOptions.owner, "Yosemiteee");
  assert.strictEqual(fakeAutoUpdater.feedOptions.repo, "LawCopilot");
  assert.strictEqual(fakeAutoUpdater.feedOptions.releaseType, "prerelease");

  const availableStatus = await desktopUpdater.checkForUpdates("manual");
  assert.strictEqual(availableStatus.status, "available");
  assert.strictEqual(availableStatus.available_version, "0.8.0-pilot.1");
  assert.strictEqual(configStore.updater.lastAvailableVersion, "0.8.0-pilot.1");

  const downloadedStatus = await desktopUpdater.downloadUpdate();
  assert.strictEqual(downloadedStatus.status, "downloaded");
  assert.strictEqual(downloadedStatus.downloaded_version, "0.8.0-pilot.1");
  assert.strictEqual(configStore.updater.lastDownloadedVersion, "0.8.0-pilot.1");

  const installResponse = desktopUpdater.quitAndInstall();
  assert.strictEqual(installResponse.ok, true);
  await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(fakeAutoUpdater.quitAndInstallCalls, 1);
  assert(events.some((payload) => payload.status === "available"));
  assert(events.some((payload) => payload.status === "downloaded"));
  process.env.APPIMAGE = previousAppImage;

  console.log("desktop updater smoke ok");
}

main().catch((error) => {
  console.error("desktop updater smoke failed", error);
  process.exitCode = 1;
});
