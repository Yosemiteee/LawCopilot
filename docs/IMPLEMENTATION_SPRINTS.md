# Sprint Plan

## Sprint 1
- DB schema (firms, users, roles, documents, chunks, audits)
- Ingestion pipeline stub -> real pipeline
- Query with citations
- Desktop shell screens

## Sprint 2
- Auth (JWT + refresh)
- RBAC middleware
- Audit immutability hash-chain
- Model router & settings screen

## Sprint 3
- Email draft workflow
- Social monitor jobs
- Installer packaging
- Download site + release artifacts

## Sprint 4
- Connector domain allowlist + PII redaction + dry-run preview endpoint
- Task and social event lightweight case ops workflow
- Token/session revoke endpoint and session persistence baseline

## Sprint 5 (2026-03-07 hardening)
- JWT parse hardening: header `alg=HS256` + `typ=JWT` validation
- Session checks now enforce expiry (`expires_at`) besides revoke status
- Ingest file-size guard (`LAWCOPILOT_MAX_INGEST_BYTES`, default 5MB)
- Audit log tamper-evident chain (`prev_hash`, `record_hash`)
- Expanded API tests: `8 passed`
