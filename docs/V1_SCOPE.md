# LawCopilot V1 Scope

Last updated: 2026-03-09
Status: Locked scope for sellable V1 planning

## Product Position

LawCopilot V1 is a legal workbench for law firms.

It is not:
- a general AI chat app
- a fully autonomous legal agent
- a consumer messaging bot
- a multi-tenant SaaS platform in its first shipped form

## V1 Must-Have

### Matter-first workbench
- Matter list and matter detail surfaces
- Matter metadata, parties, status, key dates, notes
- Matter summary and recent activity

### Document memory and source-backed search
- Matter-scoped document ingestion
- Document metadata and indexing jobs
- Semantic + keyword retrieval
- Citation-rich answers
- Passage preview and source navigation

### Legal work assistant
- Matter summary
- chronology generation
- risk/issues working notes
- missing-information prompts
- explainable task recommendations
- daily agenda fed by matter, Gmail, calendar, and Telegram signals
- suggested actions with explicit human approval
- client update draft generation
- internal summary / first case assessment / meeting summary / question list draft generation

### Task and workflow layer
- Matter-linked tasks
- due date tracking
- task status
- activity feed
- suggested next tasks with explanation

### Draft-first communication
- Email/client-update drafts
- unified outbound draft center
- review states
- approval states
- clear separation between draft and sent state
- no automatic send by default

### Settings and deployment surface
- Local-only / local-first hybrid / cloud-assisted profile display
- Model profile selection
- Storage path visibility
- Connector enable/disable controls
- Google Gmail / Calendar and Telegram integration setup
- Safety mode visibility

### Security and governance baseline
- role hierarchy
- session revoke
- audit chain
- connector allowlist
- PII masking
- matter/document access boundaries

## V1.5 Later

- Social monitoring features
- separate email and social management modules in main navigation
- Explainable assignment recommendation
- desktop cross-platform expansion beyond Windows-first
- richer analytics and dashboarding
- related matter intelligence beyond simple similarity
- advanced notification center and background job orchestration

## V2 / Later

- multi-office SaaS tenancy
- enterprise SSO
- advanced workflow automation
- more autonomous agent loops
- deeper connector ecosystem
- advanced management analytics

## Explicitly Deferred / Removed from V1

- Full autonomy in legal decisions
- auto-send external communications
- aggressive multi-agent orchestration
- feature-heavy dashboards that do not improve first-week value
- customer-facing dependency on external OpenClaw installation

## Non-Negotiable V1 Principles

- Citation-first
- Human-in-the-loop
- Draft-first
- Security by default
- Explainable suggestions
- Matter-first product organization

## V1 Success Conditions

V1 is successful when a law firm can:
- create and manage matters
- upload matter documents
- search within a matter and inspect citations
- generate a matter summary, chronology view, and workflow risk notes
- create and track matter tasks
- prepare a review-required client update or internal draft with visible source context
- understand the current deployment mode and safety posture

## Out-of-Scope Warning

Any feature that does not improve:
- trust
- matter navigation
- source-backed retrieval
- draft workflows
- pilot install readiness

should not take priority over V1 core work.
