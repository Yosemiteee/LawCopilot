# Personal Assistant Memory

LawCopilot backend içinde yeni bir local-first `knowledge base` katmanı eklendi.

## Amaç

Bu katman anlık sohbet cevabı üretmek yerine kullanıcıya ait kalıcı, explainable ve provenance-aware bir bilgi tabanı oluşturur.

## Klasör Yapısı

Varsayılan kök:

- `artifacts/runtime/personal-kb/<office-id>/`

Alt klasörler:

- `raw/`: immutable ham kaynak kayıtları
- `wiki/`: derlenmiş markdown knowledge sayfaları
- `wiki/concepts/`: concept-based knowledge article sayfaları ve backlink index
- `wiki/decision-records/`: önemli öneri ve otomasyon karar kayıtları
- `system/`: şema, kural, index, log ve reflection raporları

## Başlıca Bileşenler

- `KnowledgeBaseService`: orchestration katmanı
- `IngestAgent`: raw write + normalize + compile akışı
- `WikiMaintainerAgent`: page upsert, supersede ve contradiction mantığı
- `ReflectionAgent`: health/lint raporu
- `RecommenderAgent`: explainable recommendation engine
- `TriggerEngineAgent`: cooldown/suppression mantığı ile proactive trigger üretimi
- `ActionAgent`: suggest-only proactive hooks
- `SafetyPolicyAgent`: risk seviyesi ve confirmation kuralları
- `knowledge_base.connectors`: email/calendar/messages/tasks/notes/files/location için local connector abstraction katmanı
- `knowledge_base.location`: current place, frequent pattern ve nearby suggestion foundation
- `knowledge_base.models`: typed record, relation, scope ve sensitivity sabitleri
- `memory_overview`: scope/type/shareability bazlı görünür knowledge özeti
- `wiki_brain`: concept article, topic cluster, backlink ve graph summary yüzeyi

## Assistant Core

Bu katman LawCopilot'u sabit tek kişilik bir ürün olmaktan çıkarır. Aynı uygulama herkese aynı çekirdek ile gider; kullanıcı sohbet ederek veya ayarlardan açarak onu farklı formlara evirebilir.

Desteklenen preset formlar:

- `life_coach`
- `legal_copilot`
- `personal_ops`
- `device_companion`
- `study_mentor`
- `travel_planner`

Ama sistem bununla sınırlı değildir. Sohbet içinde:

- "sen artık benim yaşam koçum ol"
- "bundan sonra telefon asistanım gibi davran"
- "benim kitap okuma koçum ol"

gibi yönlendirmeler assistant runtime profile içine yazılır. Böylece:

- `assistant_forms`
- `behavior_contract`
- `evolution_history`

alanları güncellenir ve sonraki konuşmalarda prompt/runtime/KB aynı yeni formu kullanır.

Bu akış artık yalnız sohbetten öğrenmeye bağlı da değil. Settings içindeki assistant core yüzeyi:

- preset form açma/kapatma
- konuşmalardan öğrenilen özel formları aktive etme
- sıfırdan özel form yaratma
- doğal dil ile "beni şu tip asistana çevir" tarifinden blueprint çıkarma
- özel forma scope, capability ve UI surface atama

özelliklerini de destekler.

Yeni blueprint akışı ile kullanıcı preset seçmek zorunda değildir. Örneğin:

- "Beni kitap okuma koçuna çevir. Her akşam takip et."
- "Telefonumu yöneten kişisel asistan gibi davran."
- "Bana hukuk çalışma asistanı ol; belge ve taslakları öne çıkar."

gibi tarifler `POST /assistant/runtime/core/blueprint` üzerinden yapılandırılmış bir assistant form taslağına çevrilir. Bu taslak:

- form adı
- kategori
- önerilen capability'ler
- açılması gereken UI surface'ler
- scope sınırları
- behavior contract patch önerileri

taşır. UI bu taslağı özel form oluşturucuya doldurur; kullanıcı isterse düzenleyip kaydeder.

Assistant core artık yalnız “aktif form listesi” de değildir. Runtime `assistant_core` payload'ı ayrıca bir `operating_contract` da taşır:

- aktif capability sözleşmeleri
- görünmesi gereken UI surface'ler
- davranış stili özeti
- sonraki mantıklı kurulum adımları

Böylece kullanıcı bir form seçtiğinde sistem sadece etiketi değil, o formun gerçekten neyi açtığını da bilir ve görünür kılar.

`behavior_contract` şu alanları taşır:

- `initiative_level`
- `planning_depth`
- `accountability_style`
- `follow_up_style`
- `explanation_style`

Özel formlar için de trait inference çalışır. Örneğin:

- `koç / mentor / rehber` içeren özel formlar koçluk destekli sayılır
- `kitap / okuma / çalışma` içeren özel formlar progress tracking yüzeyleri kazanır
- `hukuk / avukat / dava` içeren özel formlar professional scope'a yaklaşır
- `telefon / cihaz` içeren özel formlar device-oriented capabilities kazanır

Bu yüzden uygulama içine sabit bir life coach veya tek tip hukuk modu gömülmez; çekirdek kullanıcı mesajları ve ayarlarıyla evrilir.

## Wiki Brain Layer

Bu turla birlikte KB sadece page-level record deposu olmaktan çıktı; active records artık concept/article seviyesinde de derleniyor.

`LLM Wiki Brain v2` ile ek olarak:

- concept article'lar deterministic fallback + opsiyonel LLM authoring ile zenginleşir
- her concept için `priority_score`, `importance_score`, `decay_score`, `frequency_weight` üretilir
- knowledge graph artık co-occurrence + relation weight skorlarını birlikte taşır
- synthesis loop insight yanında strategy ve hypothesis üretir
- reflection raporu `prunable_records` ve `inconsistency_hotspots` çıkarır
- retrieval katmanı SQLite FTS + semantic embedding/rerank foundation kullanır

Derlenen yeni artifact'lar:

- `system/normalized/wiki-brain.json`
- `system/normalized/knowledge-graph.json`
- `system/reports/wiki-brain-latest.md`
- `system/reports/knowledge-synthesis-latest.json`
- `system/reports/knowledge-synthesis-latest.md`
- `wiki/concepts/INDEX.md`
- `wiki/concepts/*.md`

Her concept article şunları taşır:

- concept key
- concept kind
- kısa derlenmiş özet
- detailed explanation
- patterns
- inferred insights
- strategy notes
- cross-links
- scope summary
- supporting records
- related concepts
- backlink count

Bu katman query ve thread flow'larda `knowledge_articles` / `supporting_concepts` olarak geri döner.

## Semantic Retrieval v2

Varsayılan arama backend'i:

- `sqlite_hybrid_fts_v1`

Bu backend artık şu katmanları birleştirir:

- SQLite FTS5 lexical arama
- query expansion / synonym bridge
- local semantic embedding cache (`embedding_json`)
- cosine benzeri semantic rerank
- scope, page type, confidence, freshness, priority ve correction history ağırlıkları

Selection reason örnekleri:

- `fts_primary_hit`
- `semantic_vector_match`
- `semantic_reranker`
- `priority_weight`
- `page_intent_match`
- `query_intent_match`

Not:

- Bu katman production-grade local retrieval foundation'dır.
- Harici vector DB veya cloud embedding şart değildir.
- Tam model-embedding/vector DB katmanı hâlâ future extension olarak açıktır.

## LLM-authored Article Generation

Article authoring için KB service opsiyonel olarak LLM runtime kullanır.

Kural:

- düşük hassasiyetli ve exportable concept'lerde runtime authoring kullanılabilir
- high/restricted kayıtlar için privacy-first deterministic fallback sürer
- runtime yoksa veya geçersiz çıktı verirse fallback article render kullanılır

Her concept article içinde `authoring.mode` tutulur:

- `llm_runtime`
- `cached`
- `deterministic_fallback`

## Autonomous Knowledge Improvement

`run_knowledge_synthesis()` artık:

- acceptance/rejection pattern'lerinden insight üretir
- insight -> strategy dönüşümü yapar
- düşük confidence hypothesis listesi üretir
- wiki brain raporlarına ve markdown report'lara bunları yazar

Örnek strategy türleri:

- evening planning focus
- reminder fatigue reduction
- place/time bucket recommendation bias

## Knowledge Quality Control v2

Reflection raporu artık şunları da üretir:

- `knowledge_gaps`
- `research_topics`
- `potential_wiki_pages`
- `prunable_records`
- `inconsistency_hotspots`

Amaç:

- eski / düşük confidence / çok düzeltilmiş knowledge kayıtlarını görünür yapmak
- contradiction ve drift alanlarını açıkça işaretlemek
- yeni wiki article ihtiyacını sistemin kendisinin önermesi

## Autonomy Hardening

Bu turla birlikte KB artık yalnız ingest + query katmanı değil, düzenli health ve autonomy pulse üreten bir operating layer haline getirildi.

Yeni/sertleştirilen katmanlar:

- `reflection_status`: son başarılı reflection zamanı, retry/backoff, next_due ve health summary
- `recommended_kb_actions`: contradiction, stale record, concept gap ve prune adayları için first-class aksiyon listesi
- `autonomy_status`: suggestion budget, interruption/reminder tolerance, open loop sayısı ve `matters_now` listesi
- `connector freshness`: her connector için `freshness_status`, `freshness_minutes`, `stale_sync`
- `run_orchestration()` sonunda güncel autonomy snapshot state içine yazılır
- bozuk/invalid UTF-8 KB state dosyaları artık güvenli fallback ile açılır; packaged runtime health yüzeyi tek bir bozuk dosya yüzünden kırılmaz

Bu sayede ürün şunları daha görünür yapar:

- ne zaman reflection bekliyor
- knowledge health hangi seviyede
- hangi KB action'ları mantıklı sırada
- hangi açık döngüler şu an gerçekten önemli
- neden sistem daha az veya daha çok proaktif davranıyor

## Consumer Context Foundation

Life OS yönü için iki yeni connector foundation eklendi:

- `browser_context`
- `consumer_signals`

Bu connector'lar şu local-first damarları normalize eder:

- browser session artifact'ları
- bookmark / reading list benzeri link kayıtları
- YouTube / video watch-history benzeri external event'ler
- shopping / food / travel sinyalleri
- weather / places / web research sinyalleri
- assistant thread ve runtime tool kullanımı sırasında oluşan harici araştırma izleri

Durum:

- local store / mirror / artifact tabanlı foundation: hazır
- assistant route ve tool usage -> external event -> KB learning hattı: hazır
- gerçek native browser history ve gerçek YouTube account sync: partial / adapter seviyesi

Bu yüzden sistem artık consumer-world tercih sinyallerini KB'ye yazabilecek temel omurgaya sahip, ancak tüm provider'lar production-native seviyede değildir.

## Semantic Learning Pass

`sync_from_store()` ve scheduler içindeki `preference_consolidation` artık sadece profil snapshot'ı okumaz. Aynı pass şunları da toplar:

- assistant message like/dislike + açıklama notları
- recommendation acceptance/rejection geçmişi
- browser/read/watch/shopping/travel consumer sinyalleri
- weather / places / web research sorgu ve kullanım sinyalleri
- location `frequent_patterns`

Bu pass:

- typed `preference` / `routine` kayıtları üretir
- `learning_source_category` ve `source_basis` ile provenance korur
- aynı logical summary tekrarlandığında duplicate record üretmez
- `memory_overview.learned_topics` içinde kullanıcıya görünür hale gelir

Örnek semantic kayıtlar:

- `consumer-interest:habit_systems:personal`
- `consumer-interest:food_light_meal:personal`
- `consumer-interest:weather_planning:personal`
- `consumer-interest:local_place_context:personal`
- `consumer-interest:web_research_orientation:personal`
- `location-pattern:evening:cafe`

Bu sayede sistem artık “ham event topluyor” seviyesinden çıkıp, tekrar eden davranışları profile/wiki üzerinde daha kararlı şekilde derleyen bir öğrenme döngüsüne yaklaşıyor.

## Location & Device Context

Location snapshot katmanı artık yalnız current place döndürmez; ayrıca:

- `device_context`
- `context_composition`
- `lifecycle_stage`
- `route_available`
- `activity_state`
- `idle_minutes`

alanlarını da taşır.

Bu, permission denied / privacy mode / stale snapshot / capture failure durumlarında UI ve trigger engine'in daha kontrollü degrade olmasını sağlar.

## Desteklenen Sayfalar

- `persona`
- `preferences`
- `routines`
- `contacts`
- `projects`
- `legal`
- `places`
- `decisions`
- `reflections`
- `recommendations`

## API Yüzeyi

- `GET /assistant/knowledge-base`
- `GET /assistant/memory/overview`
- `GET /assistant/home`
- `GET /assistant/runtime/core`
- `POST /assistant/runtime/core/blueprint`
- `POST /assistant/knowledge-base/ingest`
- `POST /assistant/knowledge-base/search`
- `GET /assistant/knowledge-base/wiki`
- `POST /assistant/knowledge-base/wiki/compile`
- `POST /assistant/knowledge-base/synthesis`
- `POST /assistant/memory/corrections`
- `GET /assistant/connectors/sync-status`
- `GET /assistant/orchestration/status`
- `POST /assistant/orchestration/run`
- `GET /assistant/knowledge-base/reflection`
- `POST /assistant/knowledge-base/reflection`

## Production Readiness Özeti

Production-ready'e yakın:

- persistent KB / scoped memory / correction loop
- wiki brain compilation
- local hybrid + SQLite FTS semantic retrieval
- explainability payload'ları
- proactive trigger engine foundation
- connector orchestration + retry/backoff + stale visibility
- packaged desktop içinde home/chat operational surfaces

Partial:

- consumer connector provider derinliği
- native OS/device context breadth
- external semantic reranker / gerçek vector backend

Adapter / stub kalan alanlar:

- gerçek browser history native provider
- gerçek YouTube account watch-history connector
- tam native desktop idle/activity telemetry
- `POST /assistant/connectors/sync`

`GET /assistant/runtime/core` şu alanları da sağlar:

- `form_catalog`
- `capability_catalog`
- `surface_catalog`
- `defaults.role_summary`
- `defaults.tone`
- `transformation_examples`
- `GET /assistant/location/context`
- `POST /assistant/location/context`
- `POST /assistant/triggers/evaluate`
- `GET /assistant/orchestration/status`
- `POST /assistant/orchestration/run`
- `GET /assistant/knowledge-base/reflection`
- `POST /assistant/knowledge-base/reflection`
- `POST /assistant/decision-records`
- `POST /assistant/recommendations`
- `POST /assistant/recommendations/{recommendation_id}/feedback`
- `POST /assistant/proactive-hooks/{hook_name}`

## Profile Sync

Şu akışlar knowledge base ile senkronlanır:

- kullanıcı profili kaydı
- assistant runtime profili kaydı
- chat-memory ile yakalanan preference/persona sinyalleri
- assistant home üretimi öncesi profil snapshot senkronu
- recent assistant action kayıtları
- approval / dispatch lifecycle event kayıtları
- connector abstraction üzerinden email/calendar/messages/tasks/files/location kayıtları
- query ve assistant-thread çağrıları öncesi incremental KB sync

Assistant core sync ile ek olarak:

- aktif asistan formları `persona` kayıtlarına yazılır
- behavior contract ayrı bir KB record olarak derlenir
- home payload `assistant_core` yüzeyi döner
- koçluk dashboard sadece koçluk destekli form veya açık hedef varsa görünür

## Live Connector Sync

Bu turda connector sistemi store-backed fixture seviyesinden production-benzeri sync orchestration seviyesine çıkarıldı.

Gerçek çalışan mirror akışlar:

- `POST /integrations/google/sync`
- `POST /integrations/outlook/sync`
- `POST /integrations/whatsapp/sync`
- `POST /integrations/telegram/sync`

Bu endpoint’ler artık sadece store’a yazmıyor:

- provider checkpoint ve cursor bilgisini KB `connector_sync` state’ine işler
- ilgili connector’lar için incremental KB sync tetikler
- response içinde `knowledge_base_sync` döner

Her connector için status yüzeyi:

- `connector`
- `sync_mode`
- `providers`
- `last_synced_at`
- `cursor`
- `checkpoint`
- `record_count`
- `synced_record_count`
- `dedupe_key_count`
- `last_reason`
- `last_trigger`
- `health_status`
- `sync_status`
- `sync_status_message`
- `last_error`
- `consecutive_failures`
- `next_retry_at`
- `last_duration_ms`
- `provider_mode`
- `summary.attention_required`
- `summary.retry_scheduled`
- `summary.connected_providers`

Connector sync artık per-connector error isolation ile çalışır:

- tek connector patladığında tüm sync zinciri düşmez
- checkpoint/cursor state korunur
- exponential retry penceresi (`next_retry_at`) yazılır
- job status `completed_with_errors` olabilir
- top-level summary alanı UI’nin dikkat gerektiren connector’ları tek bakışta göstermesini sağlar

`location_events` artık fixture/stub değil. Profile, home-base, location preference ve calendar location kayıtlarından local context scan üretir. Buna ek olarak desktop/local snapshot provider contract’i de vardır; `LAWCOPILOT_LOCATION_SNAPSHOT_PATH` altındaki JSON snapshot’tan current/recent place yüklenebilir.

Launch hardening ile eklenen local capture akışı:

- renderer tarafında `navigator.geolocation` üzerinden cihaz konumu alınabilir
- Electron preload `saveLocationSnapshot` ile snapshot runtime içine yazılır
- aynı payload `POST /assistant/location/context` ile KB state’ine işlenir
- trigger engine isterse hemen `location_context` tetiklerini yeniden değerlendirebilir

## Launch Readiness Durumu

Production-ready'e yakın:

- persistent KB core
- scoped memory + correction loop
- wiki brain compiler
- local semantic retrieval foundation
- reflection / synthesis / file-back loop
- packaged desktop sync + embedded API health doğrulaması

Partial:

- true native OS location sensor integration
- external vector DB / model embedding backend
- ayrı daemon/worker topology

Stub / adapter kalan:

- native geolocation provider abstraction'ın gerçek OS adapter'ı
- bazı harici provider'larda full autonomous long-running sync

## Desktop Runtime Sync

Desktop-facing değişiklikler için packaged runtime sync script’i:

- `scripts/update_desktop_runtime.sh --if-needed --restart-running --launch`

Bu script artık:

- backend/ui/browser-worker değişimini ayrı algılar
- packaged runtime içine sync eder
- stale `whatsapp-web-auth` Chromium session süreçlerini temizler
- desktop’u yeniden başlatır
- embedded API health check ile launch doğrular
- başarısız launch’ta startup/backend log tail’i verir
- desktop runtime hydrate olmadan eski shell chrome'unu göstermeyen startup splash akışını taşır

WhatsApp Web tarafında aynı session için açık bir headless Chromium süreci varsa durum `session_busy` olarak işaretlenir; bu artık startup’ı bloklayan fatal bir hata değildir.

## Proactive Trigger Engine

Trigger engine suggest-only çalışır ve şu tipleri destekler:

- `time_based`
- `calendar_load`
- `incoming_communication`
- `routine_deviation`
- `missed_obligation`
- `location_context`
- `inactivity_follow_up`
- `daily_planning`
- `end_of_day_reflection`

Her trigger kaydı şu alanlarla döner:

- `trigger_type`
- `why_now`
- `why_this_user`
- `confidence`
- `urgency`
- `scope`
- `source_basis`
- `recommended_action`
- `suppression_reason`
- `requires_confirmation`

Cooldown ve suppression kaynakları:

- trigger history
- recommendation suppression tercihleri
- KB scope filtresi
- per-trigger cooldown pencereleri

Trigger üretildiğinde:

- decision record oluşturulur
- trigger history güncellenir
- home payload içinde `proactive_triggers` ve `proactive_suggestions` alanlarına yansır

## Location Context

Location foundation şu dosyada yaşar:

- `apps/api/lawcopilot_api/knowledge_base/location.py`

Bu katman:

- current place normalize eder
- recent places örüntüsü çıkarır
- frequent place patterns hesaplar
- nearby suggestion candidate listesi üretir
- place-category aware explainability sağlar

Production-grade foundation artık iki mod içerir:

- `mock_memory`: mevcut KB/location memory üzerinden nearby reasoning
- `desktop_file_snapshot`: masaüstü veya local agent tarafından yazılan JSON snapshot’tan current/recent place okuma

Desktop capture zinciri ayrıca `desktop_renderer_geolocation` provider mode’unu üretir; bu mod browser/device capture ile snapshot fallback’i ayrıştırır.

Config:

- `LAWCOPILOT_LOCATION_PROVIDER_MODE`
- `LAWCOPILOT_LOCATION_SNAPSHOT_PATH`

Location response artık şu alanları da taşır:

- `provider`
- `provider_mode`
- `provider_status`
- `capture_mode`
- `observed_at`
- `navigation_handoff`
- `snapshot_path`
- `scope`
- `sensitivity`

API contract:

- `POST /assistant/location/context`
- `GET /assistant/location/context`

Home payload ve trigger engine bu context’i kullanır.

## Wiki-Centric Reasoning

Şu akışlar artık KB context kullanır:

- `POST /query`
- `POST /query/jobs`
- `POST /assistant/thread/messages`
- `POST /assistant/thread/messages/stream`
- action generation / approval / dispatch lifecycle response’ları

Bu response’larda minimum şu alanlar döner:

- `knowledge_context`
- `explainability`
- `file_back` veya `decision_record`
- `action_ladder` (action response’larında)
- `knowledge_context.supporting_concepts`
- `knowledge_context.knowledge_articles`
- `knowledge_context.context_selection_reasons`

## Knowledge Synthesis Loop

`run_knowledge_synthesis()` ve orchestration içindeki `knowledge_synthesis` işi şu pattern'leri explicit knowledge'a dönüştürür:

- accepted planning / evening recommendation patterns
- reminder fatigue / rejection patterns
- end-of-day trigger ritimleri
- frequent place/category patterns

Bu insight kayıtları `record_type=insight` ile normal KB state içine yazılır ve concept/article compilation tarafından tekrar wiki'ye bağlanır.

## Reflection 2.0

Reflection raporu artık yalnız teknik lint değil:

- `knowledge_gaps`
- `research_topics`
- `potential_wiki_pages`
- `wiki_brain_summary`

üretir. Bu sayede sistem kendi bilgi boşluklarını ve yeni article ihtiyacını raporlar.

## Operational Status

Launch-aday çalışma durumu:

- Production-ready'e yakın: persistent KB, scoped memory, correction loop, wiki compilation, synthesis loop, reflection, retrieval, proactive foundation
- Partial: native OS geolocation, vector/reranker retrieval
- Stub/adapter: bazı provider'ların tam autonomous sync worker davranışı

`knowledge_context` içinde:

- `supporting_records`
- `supporting_pages`
- `decision_records`
- `reflections`
- `recent_related_feedback`
- `scopes`
- `context_selection_reasons`
- `record_type_counts`
- `supporting_relations`

## Retrieval

Default search backend artık `sqlite_hybrid_fts_v1`.

Özellikler:

- local SQLite FTS5 index
- lexical + BM25-benzeri fallback skor
- FTS match bonusu ile hybrid reranking
- query-expansion / synonym bridge
- Turkish accent folding ile daha dayanıklı local search
- page-type aware ranking
- freshness bonus
- scope bonus
- decision/reflection intent bonus
- recent-activity intent bonus
- feedback/history intent bonus
- confidence bonus
- correction-history penalty
- intent-seeded result diversification
- `selection_reasons`
- `context_selection_reasons`
- `metadata_filters`
- `record_types`
- scope-aware filtering

Bu katman `retrieval` abstraction üstüne kuruldu. Vector/reranker backend ileride eklenebilir; ama mevcut local foundation artık production-grade local search için yeterli omurgaya sahiptir.

## Assistant Action Provenance

Şu lifecycle noktalarında decision record üretilir:

- action draft üretimi
- action approval
- action dismissal
- draft removal
- dispatch request
- dispatch complete
- dispatch failed

Bu kayıtlar response payload içinde `decision_record` olarak da döner. Aynı anda son store durumu `assistant_action` ve `approval_event` raw kaynakları olarak backfill edilir.

Action response contract ayrıca:

- `policy_guardrails`
- `explainability`
- `knowledge_context`
- `action_ladder`

alanlarını taşır. Böylece UI tarafı suggest → draft → preview → approve → execute basamaklarını görselleştirebilir.

`action_ladder` artık ek olarak şunları da taşır:

- `trusted_low_risk_available`
- `reversible`
- `preview_required_before_execute`
- `preview_summary`
- `audit_label`
- `undo_strategy`
- `trusted_execution_note`

## File-Back Loop

Sistemden çıkan değerli çıktılar chat içinde kaybolmasın diye düşük riskli file-back mantığı eklendi.

Şu tipler desteklenir:

- `query_answer`
- `assistant_reply`
- `accepted_recommendation`
- `rejected_recommendation`
- `preference_correction`
- `daily_planning_output`
- `reflection_output`
- `draft_style_learning`
- `relationship_note`

Scope ve sensitivity bilgisi response’tan türetilir; matter bağlı cevaplar `project:matter-*` ve `restricted` olarak yazılır.

## Memory Correction

Kullanıcı hafızayı görünür biçimde düzeltebilir.

`POST /assistant/memory/corrections` şu aksiyonları destekler:

- `correct`
- `forget`
- `change_scope`
- `reduce_confidence`
- `suppress_recommendation`
- `boost_proactivity`

Bu endpoint:

- hedef kaydı supersede/forget eder
- gerekiyorsa yeni active record yazar
- preference learning state’ini günceller
- `knowledge_context` ve `connector_sync_status` ile cevap verir
- low-risk durumlarda `file_back` oluşturur

Recommendation feedback de artık preference modelini etkiler:

- accepted feedback benzer önerileri güçlendirir
- repeated rejected feedback ilgili recommendation kind’i baskılar
- proactivity tercihleri cooldown’u gevşetebilir

Assistant message feedback de artık sadece local UI state değildir:

- `PATCH /assistant/thread/messages/{message_id}/feedback`
- `liked` / `disliked` sinyali assistant message üstünde kalıcı tutulur
- thumbs verildikten sonra chat içinde açıklama alanı açılabilir; kullanıcı neden beğendiğini veya beğenmediğini yazabilir
- KB içinde `preferences` ve gerektiğinde `routines` sayfalarına learning record yazar
- açıklama notu varsa bunu message content + source context ile birlikte semantik sinyale çevirir
- kişi hedefi güvenilir biçimde çıkarılabilirse `contacts` sayfasına ve `user_profile.related_profiles` alanına öğrenim yazar
- örnek: anne için sıcak tonun olumlu olduğu veya çikolata önerisinden kaçınılması gerektiği gibi sinyaller profile işlenebilir
- runtime `behavior_contract` alanlarını kontrollü biçimde rafine eder
- özellikle açıklama yoğunluğu, takip sıklığı ve planlama tonu için güçlü sinyal üretir
- tek bir thumbs sinyaliyle agresif kişilik değişimi yapmaz; muhafazakâr davranır

Chat reply explainability drawer da aynı endpoint’i kullanır:

- düzelt
- unut
- scope taşı
- güveni düşür
- bu konuda daha az öner
- bu konuda daha proaktif ol

Ek olarak:

- `forget` aksiyonu `do_not_infer_again_easily` koruması bırakır
- correction history ve repeated contradiction sinyalleri overview yüzeyine yansır

## Memory Overview

`GET /assistant/memory/overview` ve `GET /assistant/home` artık şu özetleri taşır:

- `counts`
- `by_scope`
- `by_type`
- `by_shareability`
- `recent_corrections`
- `do_not_reinfer`
- `repeated_contradictions`
- `suppressed_topics`
- `boosted_topics`

Bu yüzey chat drawer ve home knowledge cards ile birlikte çalışır.

## Preference Consolidation

Orchestration zinciri artık `preference_consolidation` job’unu da çalıştırabilir.

Bu job:

- `communication_style`
- `assistant_notes`
- `travel_preferences`
- recommendation acceptance/rejection history
- trigger history

üzerinden typed kayıtlar üretir.

Üretilen typed kayıt örnekleri:

- `conversation_style`
- `goal`
- `preference`
- `constraint`
- `routine`

## Orchestration

Scheduler foundation iki katmanlı kuruldu:

- manual/dev orchestration API
- opsiyonel background runner thread

Job aileleri:

- `connector_sync`
- `reflection_pass`
- `trigger_evaluation`
- `stale_knowledge_check`
- `suppression_cleanup`
- `preference_consolidation`
- `daily_summary_candidates`

Config flag’leri:

- `LAWCOPILOT_PERSONAL_KB_SCHEDULER_ENABLED`
- `LAWCOPILOT_PERSONAL_KB_SCHEDULER_POLL_SECONDS`
- `LAWCOPILOT_PERSONAL_KB_SCHEDULER_TRIGGER_INTERVAL_SECONDS`
- `LAWCOPILOT_PERSONAL_KB_SCHEDULER_REFLECTION_INTERVAL_SECONDS`
- `LAWCOPILOT_PERSONAL_KB_SCHEDULER_CONNECTOR_SYNC_INTERVAL_SECONDS`

Scheduler artık FastAPI `lifespan` içinde başlatılır; deprecated `on_event` kullanılmaz. Varsayılan olarak kapalıdır.

Job status yüzeyi artık:

- `cadence_seconds`
- `next_due_at`
- `is_due`
- `failure_count`
- `last_duration_ms`
- `summary.failed_jobs`
- `summary.due_jobs`

## Güvenlik

- kaynaklar önce raw katmana immutable olarak yazılır
- external/sensitive kaynaklar `LAWCOPILOT_PERSONAL_KB_EXCLUDED_PATTERNS` ile hariç tutulabilir
- önerilerde `confidence`, `source_basis`, `risk_level`, `requires_confirmation` alanları zorunludur
- `Level D` aksiyonlar never-auto kalır
- typed metadata içinde `scope`, `sensitivity`, `exportability`, `model_routing_hint`, `relations` alanları tutulur

## Test

Backend:

```bash
cd apps/api
.venv/bin/python -m compileall -q lawcopilot_api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_knowledge_base.py tests/test_assistant_logic.py::test_memory_capture_updates_assistant_name_from_correction_sentence
```

UI:

```bash
cd apps/ui
npm run test -- AssistantExplainabilityDrawer.test.tsx AssistantMemoryOverview.test.tsx AssistantOperationalSurface.test.tsx
```

Desktop:

```bash
cd apps/desktop
node scripts/whatsapp-runtime-smoke.cjs
```

## Öneri Motoru

Motor şu sinyalleri kullanır:

- takvim yükü
- açık görevler
- reply-needed iletişimler
- ulaşım ve yemek tercihleri
- current context
- location context

Frequency control:

- aynı recommendation kind için cooldown uygulanır
- varsayılan cooldown: `180` dakika

## Reflection/Lint

Health report şu kontrolleri üretir:

- contradiction scan
- stale knowledge detection
- orphan page detection
- missing page suggestion
- repeated rejected recommendation detection
- schema drift detection
- source/page mismatch detection
- low-confidence knowledge buckets
- preference drift summary
- user model summary
- scope summary

Çıktılar:

- `system/reports/knowledge-health-latest.json`
- `system/reports/knowledge-health-latest.md`

## Koçluk ve Hedef Takibi

Bu turda LawCopilot’un mevcut KB çekirdeğinin üstüne yapılandırılmış bir `coach / habit / progress` katmanı eklendi.

Yeni backend yüzeyleri:

- `GET /assistant/coaching`
- `POST /assistant/coaching/goals`
- `POST /assistant/coaching/goals/{goal_id}/progress`

Sistem artık:

- kişisel hedef oluşturur
- günlük/haftalık alışkanlık check-in’leri tutar
- ilerleme loglarını KB’ye event record olarak yazar
- active goal / due check-in / recent progress / notification candidate üretir
- koçluk planı ve risk/strategy özeti çıkarır
- due goal’ları proactive trigger ve recommendation akışına besler

Home yüzeyinde artık:

- `Koçluk düzeni`
- aktif hedefler
- due check-in’ler
- inline progress logging
- yeni hedef oluşturma
- notification adayları

örünür.

Not:

- Bu katman mevcut KB’yi extend eder; ayrı paralel planner/memory sistemi değildir.
- Goal record’ları `routines` ve `projects` sayfalarına typed record olarak düşer.
- Progress update’leri `event` record olarak file-back edilir ve future retrieval/synthesis içinde görünür.

## Gerçek Kaynak Kapsamı

Şu an gerçekten çalışan kaynak aileleri:

- email threads
- calendar events
- WhatsApp/Telegram mirror messages
- local tasks/reminders
- matter notes
- local/drive documents
- assistant recommendation feedback
- assistant action/approval history
- manual/browser/desktop location context
- user profile + runtime profile

Kısmi/adapter seviyesinde kalanlar:

- YouTube / browser history / watch history
- native OS geolocation sensor
- tam autonomous external provider worker topology
- gerçek weather/provider sync ve her consumer app için native account bridge

Yani sistem “çok kaynaktan öğrenen LLM wiki” yönüne güçlü şekilde girdi; ama `YouTube geçmişi gibi her dijital davranışı native ingest eden kusursuz universal life OS` seviyesinde henüz değil. Bu alanlar bir sonraki entegrasyon dalgası olarak kalıyor.

## Test

Backend içinden:

```bash
.venv/bin/python -m compileall -q lawcopilot_api
.venv/bin/python -m pytest -q tests/test_knowledge_base.py tests/test_assistant_logic.py::test_memory_capture_updates_assistant_name_from_correction_sentence
```

UI smoke:

```bash
cd apps/ui
npm run test -- AssistantExplainabilityDrawer.test.tsx AssistantMemoryOverview.test.tsx AssistantOperationalSurface.test.tsx
```

Desktop smoke:

```bash
cd apps/desktop
node scripts/whatsapp-runtime-smoke.cjs
```

## Launch Readiness

Production-ready’e yakın:

- persistent KB + scoped memory + correction loop
- sqlite-backed local retrieval
- browser-worker bundled Chromium seed + system Chrome fallback
- connector sync observability / retry surface
- proactive trigger suppression / cooldown
- home/chat explainability ve memory controls
- packaged desktop runtime sync + embedded API health doğrulaması

Partial:

- desktop/browser geolocation capture zinciri
- file-backed location snapshot provider
- orchestration runner ve periodic jobs

Stub / adapter:

- native OS geolocation sensor adapter
- vector/reranker retrieval backend
- ayrı process/daemon worker topology

Kapsanan yeni davranışlar:

- mirror sync checkpoint + connector status
- stronger retrieval backend contract
- sqlite-backed local hybrid retrieval
- metadata/record-type aware search
- memory correction flow
- memory overview + reduce confidence flow
- scope separation
- explainability/home surface rendering
- UI memory correction wiring
- connector health / retry surface
- location snapshot fallback + navigation handoff surface
- browser geolocation capture + desktop snapshot persistence
- orchestration due/failure visibility
- low-risk action ladder preview metadata
- semantic query expansion on local retrieval
- bundled Chromium cache-first packaging
- browser worker system Chrome fallback
- WhatsApp session-busy guard
- desktop runtime sync verification
- desktop startup hydration gate + production-only React StrictMode render

Not:

- Bu sandbox ortamında `fastapi.testclient.TestClient` kararsız davrandığı için yeni endpoint doğrulamaları route-level ve service-level testlerle yapıldı.
- `scripts/update_desktop_runtime.sh --if-needed --restart-running --launch` host tarafinda packaged desktop + embedded API health dogrulamasini basariyla geciyor.
- `npm run test:packaged` ise bu kisitli sandbox icinde Electron GUI/sandbox politikalari nedeniyle temsil gucu dusuk olabilir; launch icin esas referans host-side packaged health akisidir.
