# RAG Redesign Plan

Last updated: 2026-03-09
Status: Approved target architecture

## Goal

Move LawCopilot retrieval from prototype-grade in-memory search to a production-adjacent legal document memory system.

## Current State

Current retrieval:
- legacy `/query` path still uses in-memory retrieval
- matter-scoped retrieval now uses persisted `documents` + `document_chunks` + `ingestion_jobs`
- scoring is still token-overlap based
- results now return richer citation objects and matter scope metadata
- pgvector path is still transition metadata, not active production vector retrieval

This is useful for prototype-grade source-backed search, but not enough for pilot-grade legal trust.

## Target Principles

- matter-scoped by default
- citation-first output
- hybrid retrieval
- persistent indexes
- local-first data path
- explainable support strength

## Canonical Metadata Schema

- `office_id`
- `matter_id`
- `client_id` nullable
- `document_id`
- `document_title`
- `document_type`
- `source_type`
- `uploaded_by`
- `captured_at`
- `document_date`
- `tags`
- `confidentiality_level`
- `language`
- `parse_status`
- `hash_sha256`

## Ingestion Pipeline

Stages:
1. upload accepted
2. job queued
3. parsing
4. normalization
5. chunking
6. metadata extraction
7. embedding/index write
8. indexed or failed

Current implementation status:
- upload registration: done
- ingestion jobs: done
- persisted chunks: done
- matter-scoped retrieval: done
- hybrid vector backend: not yet
- parsing reliability across file types: not yet

Job states:
- `queued`
- `processing`
- `parsed`
- `indexed`
- `failed`
- `retrying`

## Retrieval Modes

### Dev mode
- in-memory fallback
- SQLite allowed
- sample documents only

### Pilot/prod mode
- PostgreSQL transactional store
- pgvector embeddings
- keyword search support
- matter filters
- document metadata filters

## Hybrid Retrieval Design

Signal inputs:
- keyword relevance
- vector similarity
- metadata fit
- matter match
- recency/date hints
- duplicate suppression

Output features:
- top citations
- related documents
- support level
- weak-support warning when evidence is sparse

## Citation Schema Upgrade

Each citation should include:
- document title
- matter label
- logical page/section
- chunk id
- excerpt
- retrieval score
- support type: `document_backed` or `weak_support`

Response-level provenance fields:
- `support_level`
- `manual_review_required`
- `citation_count`
- `source_coverage`
- `generated_from`

## Evaluation Plan

Add legal-style sample fixtures covering:
- landlord/tenant
- labor dispute
- traffic compensation
- collection/enforcement
- custody/family law

Measure:
- citation precision
- matter filter correctness
- duplicate suppression quality
- low-support answer rate
- retrieval stability across reruns

## Migration Sequence

1. matter/document metadata schema
2. ingestion jobs
3. richer citation schema
4. PostgreSQL + pgvector adapter
5. hybrid ranking
6. evaluation fixtures and regression tests

## Current Slice Output

The current slice delivered:
- `documents`, `document_chunks`, `ingestion_jobs` persistence
- `POST /matters/{matter_id}/documents`
- `GET /matters/{matter_id}/documents`
- `POST /matters/{matter_id}/search`
- `GET /matters/{matter_id}/ingestion-jobs`
- `GET /documents/{document_id}/chunks`
- `GET /documents/{document_id}/citations`

This is the intended stepping stone toward pgvector-backed hybrid retrieval, not the final retrieval architecture.

## Explicit Non-Goal

Do not market retrieval as legally authoritative reasoning. V1 retrieval is evidence discovery and source-backed assistance, not legal judgment automation.
