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
- A substantial React + Vite UI and Electron desktop shell exist in the repository.

What is not yet true:
- Retrieval is not yet production-grade semantic search.
- The product is not yet a fully coherent assistant-first data model.
- OpenClaw is still visible as an external dependency in scripts and docs.

## Classification by Area

| Area | Path | Status | Notes |
| --- | --- | --- | --- |
| API app | `apps/api/lawcopilot_api/app.py` | Working | Real endpoints for auth, query, tasks, drafts, assistant and workspace flows. |
| Auth/RBAC | `apps/api/lawcopilot_api/auth.py` | Production candidate | HMAC bearer tokens, role hierarchy, expiry validation, session binding. |
| Persistence | `apps/api/lawcopilot_api/persistence.py` | Partial | Works for current prototype tables. Needs assistant-first cleanup and PostgreSQL path. |
| Retrieval | `apps/api/lawcopilot_api/rag.py` | Scaffold/partial | In-memory token-set retrieval. Pgvector path is transition metadata only. |
| Connector safety | `apps/api/lawcopilot_api/connectors/safety.py` | Production candidate | Allowlist, dry-run, PII masking are real and useful. |
| Backend tests | `apps/api/tests` | Working | Useful baseline, but coverage is prototype-centric. |
| UI shell | `apps/ui` | Working | React + Vite shell exists, but the product surface is still broad and uneven. |
| Desktop shell | `apps/desktop` | Working | Electron shell exists and packages, but hardening and posture work remain. |
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

The current retrieval layer is enough for demos and developer tests, but not for a trustworthy general assistant:
- no persistent vector backend in active use
- retrieval scope is still fragmented across legacy surfaces
- no ingestion job lifecycle
- limited metadata
- limited citation fidelity

### 4. The data model is not assistant-first

Current tables center on:
- sessions
- tasks
- email drafts
- social events
- query jobs

This is useful groundwork, but it is not yet the right core for a broad assistant. The product needs a clearer assistant-first center around workspace, memory, tools, approvals and user context.

### 5. Documentation overstates some capabilities

Confirmed mismatches:
- Some docs still describe the product as lawyer-first, while the codebase already contains broader assistant surfaces.
- `MASTER_PLAN.md` and related docs still over-index on matter-first/legal framing.
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
- a functional local-first assistant prototype
- a working desktop + API + UI stack
- a strong foundation for a pilot product

Today, LawCopilot cannot credibly be sold as:
- a turnkey desktop application
- a fully polished adaptive assistant
- a robust semantic memory system
- a multi-user office deployment product

## What Must Change Before Pilot

P0:
- clarify product/runtime boundary
- lock V1 scope
- add assistant-first domain model
- modularize the UI
- redesign retrieval for assistant-grade citations and memory ranking

P1:
- add pilot-ready packaging path
- add deployment mode visibility
- remove customer-facing OpenClaw terminology
- formalize release criteria

## Audit Conclusion

LawCopilot is not a fake demo. It contains real product-quality instincts and meaningful backend/security work.

The primary problem is not lack of ambition. The primary problem is that the architecture still reflects prototype speed rather than product boundaries.

The correct next move is not more demo polish. The correct next move is:
- assistant-first foundation
- modular UI shell
- retrieval redesign
- product/runtime boundary cleanup
