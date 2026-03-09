# LawCopilot Technical Debt Register

Last updated: 2026-03-09
Status: Active remediation register

| ID | Area | Severity | Current state | User/Product impact | Planned fix |
| --- | --- | --- | --- | --- | --- |
| TD-001 | UI monolith | Critical | `apps/ui/index.html` contains most product logic in one file | Slows shipping, increases regression risk, blocks modular workbench | Replace with React + Vite shell and incremental page migration |
| TD-002 | Missing desktop shell | Critical | `apps/desktop` is referenced but absent | Packaging story is not real | Add Tauri Windows-first shell |
| TD-003 | Retrieval quality | Critical | In-memory token-set retrieval only | Low legal trust, weak citations | Introduce PostgreSQL + pgvector hybrid retrieval |
| TD-004 | Non-matter-first schema | Critical | Persistence centers on tasks/drafts/social/query jobs | Core product cannot organize work around cases | Add matter-first schema and APIs |
| TD-005 | Product/runtime boundary | Critical | OpenClaw still visible in scripts/docs | Customer experience is confusing and not sellable | Make runtime internal and reframe customer-facing product docs |
| TD-006 | Release discipline gap | High | Release checklist exists but is not pilot-grade | Risky installations and unverifiable releases | Create V1 release criteria and package validation path |
| TD-007 | PostgreSQL absence | High | SQLite is the only active transactional store | Limits growth, migrations, retrieval cohesion | Keep SQLite for dev only, add PostgreSQL pilot path |
| TD-008 | Citation fidelity | High | Search responses expose limited source metadata | Low trust in AI outputs | Add richer citation schema with support level and source coverage |
| TD-009 | Connector governance | High | Draft-first is present, but matter-aware review flow is not | Draft workflows feel detached from legal context | Attach drafts and approvals to matters |
| TD-010 | Tenant/office model | High | `tenant_id` exists only as retrieval plan metadata | Future isolation strategy is unclear | Design office-first model now, implement single-office V1 |
| TD-011 | Installer assumptions | Medium | bootstrap scripts still assume external OpenClaw | Incorrect setup path for product buyers | Rework packaging/install docs around bundled runtime |
| TD-012 | UI test posture | Medium | No modular frontend test stack exists | UI migration could regress silently | Add React/Vite test harness during UI migration |
| TD-013 | Retrieval evaluation | Medium | No legal relevance benchmark fixtures in active use | Hard to measure hallucination/citation quality | Add sample matters and retrieval eval suite |
| TD-014 | Social ingestion scope | Medium | Real endpoints exist but V1 value is unclear | Scope dilution | Mark as V1.5 unless pilot need appears |
| TD-015 | Artifact/progress sprawl | Low | Artifacts and logs are mixed with product repo | Repo signal-to-noise is reduced | Keep artifacts but stop treating them as source of truth |

## Remediation Order

1. TD-005 Product/runtime boundary
2. TD-004 Non-matter-first schema
3. TD-001 UI monolith
4. TD-003 Retrieval quality
5. TD-002 Missing desktop shell
6. TD-006 Release discipline gap

## Debt Handling Rules

- Do not hide debt behind optimistic README language.
- If a debt item affects trust, security, or customer installability, it is P0/P1.
- UI polish does not close debt if the underlying structure remains broken.
