# LawCopilot Product Audit

Last updated: 2026-03-09
Owner: Product Engineering
Status: Source of truth for the current codebase

## Executive Summary

LawCopilot is currently a pre-product advanced prototype.

What is real today:
- A functioning FastAPI backend exists under `apps/api/lawcopilot_api`.
- Local persistence exists and is exercised by tests.
- Retrieval exists, but is still prototype-grade and in-memory by default.
- Security posture is materially better than a typical demo: bearer auth, role checks, session revoke, connector allowlist, PII masking, audit chain, ingest size guard.
- A substantial UI prototype exists in `apps/ui/index.html`.

What is not yet true:
- There is no real desktop shell in the repository.
- There is no pilot-ready installer or packaged desktop application.
- Retrieval is not yet production-grade semantic search.
- The product is not yet matter-first in its data model.
- OpenClaw is still visible as an external dependency in scripts and docs.

## Classification by Area

| Area | Path | Status | Notes |
| --- | --- | --- | --- |
| API app | `apps/api/lawcopilot_api/app.py` | Working | Real endpoints for auth, query, tasks, drafts, social ingest. Not matter-first yet. |
| Auth/RBAC | `apps/api/lawcopilot_api/auth.py` | Production candidate | HMAC bearer tokens, role hierarchy, expiry validation, session binding. |
| Persistence | `apps/api/lawcopilot_api/persistence.py` | Partial | Works for current prototype tables. Needs matter-first schema and PostgreSQL path. |
| Retrieval | `apps/api/lawcopilot_api/rag.py` | Scaffold/partial | In-memory token-set retrieval. Pgvector path is transition metadata only. |
| Connector safety | `apps/api/lawcopilot_api/connectors/safety.py` | Production candidate | Allowlist, dry-run, PII masking are real and useful. |
| Backend tests | `apps/api/tests` | Working | Useful baseline, but coverage is prototype-centric. |
| UI prototype | `apps/ui/index.html` | Working but monolithic | Feature-rich prototype, not maintainable as a product surface. |
| Desktop shell | `apps/desktop` | Missing | Referenced in docs but does not exist. |
| Installer/bootstrap | `deployment/installer/*`, `scripts/bootstrap_openclaw.sh` | Partial/misleading | Hardened download logic exists, but still assumes user-visible OpenClaw dependency. |
| Release checks | `scripts/release_check.sh` | Partial | Useful sanity script, but still tied to external OpenClaw assumptions. |
| Product docs | `README.md`, `docs/*` | Mixed | Strong intent, but several claims are ahead of current code. |

## Key Findings

### 1. The product boundary is still blurry

The repository mixes:
- LawCopilot customer-facing product concerns
- OpenClaw runtime assumptions
- local workspace automation notes
- prototype artifacts and progress logs

Result:
- engineers can still understand the repo
- pilot customers cannot cleanly consume it as a product

### 2. The UI is rich but structurally fragile

`apps/ui/index.html` contains almost the entire product surface in one file. This accelerated prototyping, but it is now blocking:
- maintainability
- reusable components
- route-level testing
- state isolation
- product polish that can survive iteration

### 3. Retrieval is not sellable yet

The current retrieval layer is enough for demos and developer tests, but not for legal trust:
- no persistent vector backend in active use
- no matter-scoped retrieval model
- no ingestion job lifecycle
- limited metadata
- limited citation fidelity

### 4. The data model is not matter-first

Current tables center on:
- sessions
- tasks
- email drafts
- social events
- query jobs

This is useful groundwork, but it is not the right core for a legal workbench. The product needs matters as the first-class organizing entity.

### 5. Documentation overstates some capabilities

Confirmed mismatches:
- `README.md` references `apps/desktop`, but that directory does not exist.
- `MASTER_PLAN.md` and related docs imply product packaging that is not yet present in code.
- `PGVECTOR_TRANSITION_PLAN.md` is a valid plan, but not evidence that pgvector is already active.
- release assets exist, but they do not amount to a pilot-ready release process yet.

### 6. Security thinking is ahead of product packaging

This is a positive finding. Security controls are already more mature than the packaging/distribution story. That should be preserved during the product rewrite:
- draft-first outbound policy
- audit trail
- connector allowlist
- bearer-only default
- session revocation
- PII masking

## Customer-Facing Reality Check

Today, LawCopilot can credibly be shown as:
- a sophisticated legal workbench prototype
- a functional local API plus UI proof-of-concept
- a strong foundation for a pilot product

Today, LawCopilot cannot credibly be sold as:
- a turnkey desktop application
- a fully packaged law-firm product
- a robust semantic legal memory system
- a multi-user office deployment product

## What Must Change Before Pilot

P0:
- clarify product/runtime boundary
- lock V1 scope
- add matter-first domain model
- modularize the UI
- redesign retrieval for matter-scoped citations

P1:
- add pilot-ready packaging path
- add deployment mode visibility
- remove customer-facing OpenClaw terminology
- formalize release criteria

## Audit Conclusion

LawCopilot is not a fake demo. It contains real product-quality instincts and meaningful backend/security work.

The primary problem is not lack of ambition. The primary problem is that the architecture still reflects prototype speed rather than product boundaries.

The correct next move is not more demo polish. The correct next move is:
- matter-first foundation
- modular UI shell
- retrieval redesign
- product/runtime boundary cleanup
