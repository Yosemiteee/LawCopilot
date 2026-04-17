# LawCopilot Browser Worker

Minimal Playwright worker skeleton for future LawCopilot integration.

## Capabilities
- `navigate`
- `extract`
- `screenshot`
- `click`
- `type`
- `select`
- `download-plan`

## Usage

One-shot JSON via stdin:

```bash
echo '{"actions":[{"type":"navigate","url":"https://example.com"},{"type":"extract"}]}' \
  | node dist/index.js
```

Simple CLI args:

```bash
node dist/index.js --action extract --url https://example.com
```

Line-delimited server mode:

```bash
node dist/index.js --server
```

Each line on stdin should be a JSON request. Each response is written as a single JSON line on stdout.

## Notes
- Chromium must be available for Playwright. If needed run `npx playwright install chromium`.
- Repo içinde hazır komut: `npm run install:chromium`
- Packaged desktop build, kilit dosyasi yarisi yasamamak icin bundled Chromium'u `apps/browser-worker/.bundled-browsers` altina indirir.
- Domain allowlist, profile directory, downloads directory, and artifacts directory can be passed in the request body or via env vars:
  - `LAW_BROWSER_ALLOWED_DOMAINS`
  - `LAW_BROWSER_PROFILE_DIR`
  - `LAW_BROWSER_ARTIFACTS_DIR`
  - `LAW_BROWSER_DOWNLOADS_DIR`
