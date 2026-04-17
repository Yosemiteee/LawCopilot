# V1 Release Criteria

Last updated: 2026-03-09
Status: Pilot release gate

## Product Readiness

- Assistant home, inbox, calendar and proactive surfaces are usable
- Workspace and personal knowledge inputs can be ingested and searched
- AI responses expose citations and support status
- Draft workflows are reviewable and not auto-sent
- Tasks, reminders and follow-up suggestions are usable
- Deployment mode is visible in UI

## Security Readiness

- strong JWT secret required outside dev
- token bootstrap path is explicitly configured
- session revoke verified
- connector allowlist enforced
- PII masking verified
- audit chain enabled
- workspace/document access rules tested
- no customer-facing requirement to manually install OpenClaw

## Retrieval Readiness

- ingestion jobs visible
- retrieval is workspace- and context-aware
- citation metadata includes excerpt and source anchor
- low-support outputs are labeled
- evaluation fixtures exist and run in CI/local check

## Packaging Readiness

- desktop shell exists
- pilot bootstrap path documented
- unpacked desktop package path validated
- first-run onboarding defined
- local storage path documented
- upgrade/rollback notes exist
- offline/local-first behavior documented

## Testing Readiness

- backend API tests pass
- assistant workflow tests pass
- retrieval tests pass
- UI smoke tests pass
- install smoke path verified
- desktop smoke path verified

## Documentation Readiness

- README reflects actual repository state
- V1 scope and product audit are current
- boundary decisions are current
- release notes and known risks are documented
- pilot install guide exists

## Must-Not-Ship Conditions

- uncited answers presented as authoritative
- auto-send enabled by default
- customer docs still require raw OpenClaw operation
- workspace/document boundaries untested
- packaging path absent or misleading
