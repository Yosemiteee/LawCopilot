# LawCopilot

Global rules:
- Do not commit, push, or merge unless explicitly asked.
- Work in the current repository only.
- Prefer minimal cohesive changes.
- If a task spans multiple areas, split it across the correct sub-agents.
- Avoid editing the same file from multiple sub-agents unless absolutely necessary.
- For external APIs, SDK behavior, release-note checks, or "latest" questions, verify against primary documentation before changing code.
- For explicit review requests, prioritize findings first: correctness, regressions, security, and missing tests.
- Before wrapping up, run the narrowest verification that matches the changed surface; use `scripts/verify_surface.sh` for scoped checks and `scripts/check.sh` for full validation.
- After finishing, always report:
  1. changed files
  2. risks
  3. how to test

Project structure:
- Backend: apps/api/lawcopilot_api
- Frontend: apps/ui/src
- Desktop: apps/desktop

Roles:
- backend_platform
- intelligence_core
- product_ui
- desktop_validation
- reviewer
- docs_researcher
