# PGVector Geçiş Planı (RAG Kalıcılığı)

## Amaç
In-memory RAG katmanını tenant-aware, kalıcı ve üretime uygun pgvector tabanına geçirmek.

## Aşamalar
1. **Stage 0 (mevcut)**: `InMemoryRAGStore`.
2. **Stage 1 (bu commit)**: `PgVectorTransitionStore` ile API sözleşmesinde backend/tenant metadata’sını taşıyan geçiş katmanı.
3. **Stage 2**: Gerçek PostgreSQL + pgvector bağlantısı (dual-write: in-memory + pgvector).
4. **Stage 3**: Read path’i pgvector’a geçirmek.
5. **Stage 4**: In-memory fallback’i sadece DR modu olarak bırakmak.

## Ortam Değişkenleri
- `LAWCOPILOT_RAG_BACKEND=inmemory|pgvector`
- `LAWCOPILOT_RAG_TENANT_ID=<tenant>`

## Başlangıç SQL
`lawcopilot_api.rag.PgVectorTransitionStore.bootstrap_sql()` çıktısı kullanılır:
- `CREATE EXTENSION IF NOT EXISTS vector;`
- `rag_chunks` tablosu
- tenant ve embedding indexleri

## Güvenlik Notları
- Tüm sorgularda `tenant_id` zorunlu filtre olacak.
- Chunk benzersizliği `(tenant_id, chunk_id)` ile enforced.
- İleride row-level security (RLS) eklenecek.
