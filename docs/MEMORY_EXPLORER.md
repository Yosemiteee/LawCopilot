# Memory Explorer

LawCopilot `Memory Explorer`, mevcut personal knowledge base katmanını kullanıcıya şeffaf biçimde açar. Amaç yeni bir memory sistemi kurmak değil; halihazırda çalışan LLM wiki/KB altyapısını görünür, gezilebilir ve düzenlenebilir hale getirmektir.

## Ne Gösterir

`/memory` sayfası şu katmanları tek yüzeyde toplar:

- Wiki sayfaları: `persona`, `preferences`, `routines`, `contacts`, `places`, `projects`, `decisions`, `recommendations`, `reflections`
- Concept article dosyaları: `concepts/` altında üretilen derlenmiş bilgi makaleleri
- System markdown dosyaları: `AGENTS.md`, `SCHEMA.md`, `CONTROL.md`, `INDEX.md`, `LOG.md`, `RULES.md` ve `system/` içine sonradan düşen ek `.md` dosyaları
- Report dosyaları: `wiki-brain-latest.md`, `knowledge-health-latest.md` ve `reports/` içine sonradan eklenen ek `.md` raporlar
- Typed memory records: preference, routine, person, place, decision, recommendation, reflection ve ilgili relation metadata

Bu sayede runtime profil, soul/heartbeat notları, rutinler, profil öğrenimleri, öneri geri bildirimleri ve reflection çıktıları aynı explorer içinde izlenebilir olur.

## Görünümler

### 1. Sayfalar

- Sayfa listesi
- Markdown içerik
- Confidence
- Scope özeti
- Kayıt listesi
- Çözüm bağları
- Yazı dayanakları
- Backlinkler
- İlişkili sayfalar

### 2. Graph

- Concept, record ve relation-target node’ları
- Edge relation tipleri:
  - `prefers`
  - `related_to`
  - `inferred_from`
  - `supports`
  - `contradicts`
  - `supersedes`

### 3. Zaman Akışı

- Yeni bilgi kaydı
- Correction
- Recommendation feedback
- Decision record
- Trigger geçmişi
- Reflection output

### 4. Kanıt

Seçili kayıt için:

- `source_refs`
- `source_basis`
- correction history
- relation listesi
- backlinkler
- `claim_bindings`
- `article_claim_bindings`

Bu iki yüzey şu farkı gösterir:

- `claim_bindings`: kayıt -> claim -> çözüm durumu
- `article_claim_bindings`: derlenmiş metindeki özet/paragraf anchor'ı -> hangi claim'lerden üretildi

### 5. Sağlık

- düşük confidence kayıtlar
- stale kayıtlar
- contradiction yüzeyi
- trigger spam riski
- knowledge gaps
- research topics
- recommended KB actions

## Düzenleme Aksiyonları

Explorer, mevcut correction loop’u kullanır. Ayrı bir edit sistemi yoktur.

Desteklenen aksiyonlar:

- `correct`
- `forget`
- `change_scope`
- `reduce_confidence`

Bu aksiyonların hepsi:

- KB state’e yazılır
- correction history üretir
- sonraki retrieval ve assistant davranışını etkiler
- explainability ve provenance zincirini korur

## API

- `GET /memory/pages`
- `GET /memory/page/{id}`
- `GET /memory/graph`
- `GET /memory/timeline`
- `GET /memory/health`
- `POST /memory/edit`
- `POST /memory/forget`
- `POST /memory/change-scope`

Bu endpoint’ler mevcut KB compile/sync hattına bağlıdır. Sayfa veya sağlık verisi okunmadan önce personal KB güvenli biçimde sync edilir.

## Dosya Şeffaflığı

Explorer response’ları şu klasörleri açıkça döndürür:

- `raw/`
- `wiki/`
- `concepts/`
- `system/reports/`
- `normalized/`
- `system/`

Bu yapı Obsidian-benzeri dış incelemeyi kolaylaştırır. Kullanıcı isterse generated markdown dosyalarını doğrudan açabilir.

## Sınırlar

- Explorer, ayrı bir graph backend kurmaz; mevcut file-based wiki brain graph’ı açığa çıkarır.
- Scope ve privacy guardrail’leri aynı kalır; edit aksiyonları scope-aware yürür.
- `system/` veya `reports/` altına yeni markdown dosyaları düştüğünde explorer bunları otomatik listeler.

## Doğrulama

Temel kontrol komutları:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q apps/api/tests/test_knowledge_base.py -k "memory_explorer"
npm --prefix apps/ui run test -- src/pages/MemoryExplorerPage.test.tsx
npm --prefix apps/ui run build
```
