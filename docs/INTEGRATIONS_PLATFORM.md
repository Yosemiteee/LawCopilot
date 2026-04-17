# Integrations Platform

Son guncelleme: 2026-04-08

## Ozet

LawCopilot entegrasyon katmani artik iki seviyeli calisir:
- `legacy-desktop`: mevcut masaustu OAuth ve bridge akislari katalogta gorunur kalir
- `platform`: typed connector DSL, shared runtime, policy engine ve normalized data modeli ile yonetilir

Bu belge artik sadece MVP katalogunu degil, production-hardening sonrasindaki isletim modelini anlatir.

## Audit Ozeti

Guclu olanlar:
- ortak connector DSL ve katalog yapisi
- legacy uyumlulugunu bozmayan dual-layer model
- sealed secret saklama
- sync/action persistence tablolari
- scaffold generator ve integrations UI

MVP seviyesinde kalan ve bu iterasyonda guclendirilen alanlar:
- OAuth lifecycle ilk versiyonda gercek durum makinesine sahip degildi
- sync sadece anlik cagiriydi; queue, retry ve anti-dup yoktu
- permission/confirmation kurallari merkezi degildi
- normalized resource modeli eksikti
- olay kaydi ve admin-gozlem yetersizdi
- route-level testler `TestClient` ile calismiyordu

## Backend Modulleri

- `apps/api/lawcopilot_api/integrations/models.py`
  Connector DSL, OAuth/sync/job/safety request semalari
- `apps/api/lawcopilot_api/integrations/catalog.py`
  Built-in connector katalogu, permission presetleri, GitHub/Notion/REST/PostgreSQL/Elastic ornekleri
- `apps/api/lawcopilot_api/integrations/repository.py`
  Connection, OAuth session, sync run, normalized resource, action run, generated connector registry, version history ve pattern-memory persistence katmani
- `apps/api/lawcopilot_api/integrations/secret_box.py`
  Rotation-aware secret sealing helper (`v1` back-compat + `v2` key-id format)
- `apps/api/lawcopilot_api/integrations/policy.py`
  Safety settings, capability discovery ve action policy enforcement
- `apps/api/lawcopilot_api/integrations/oauth_runtime.py`
  OAuth state, PKCE, authorization URL, token exchange/refresh/revoke ve auth summary yardimcilari
- `apps/api/lawcopilot_api/integrations/normalization.py`
  `integration_records` -> `integration_resources` normalize donusumu
- `apps/api/lawcopilot_api/integrations/scaffold.py`
  OpenAPI/docs fetch destekli connector draft, validation test ve fixture ureteci
- `apps/api/lawcopilot_api/integrations/runtime.py`
  Gercek HTTP/DB executor katmani, provider adapter'lari, pagination, retry/backoff, rate-limit handling, partial failure metadata ve webhook verification
- `apps/api/lawcopilot_api/integrations/worker.py`
  Queue'daki sync islerini arka planda calistiran worker, heartbeat ve tick telemetry
- `apps/api/lawcopilot_api/integrations/service.py`
  Runtime engine, lifecycle, generated connector request akisi, sync orchestration, policy enforcement, observability
- `apps/api/lawcopilot_api/api/routes/integrations.py`
  HTTP surface

## Frontend Modulleri

- `apps/ui/src/pages/IntegrationsPage.tsx`
  Katalog, connect/configure, OAuth lifecycle, safety settings, sync status, event/resource preview, scaffold UI ve dogal dil entegrasyon istegi
- `apps/ui/src/services/lawcopilotApi.ts`
  Integrations API client
- `apps/ui/src/types/domain.ts`
  Typed catalog/detail/lifecycle response modelleri

## Connector DSL

Her connector en az su alanlari tasir:
- `id`, `name`, `description`, `category`
- `auth_type`, `auth_config`, `scopes`
- `resources`, `actions`, `triggers`
- `sync_policies`, `pagination_strategy`, `webhook_support`
- `rate_limit`, `ui_schema`, `permissions`
- `capability_flags`, `management_mode`, `default_access_level`

`auth_config` icinde artik OAuth lifecycle icin de alanlar vardir:
- `authorization_url`
- `token_url`
- `revocation_url`
- `default_scopes`
- `scope_separator`
- `pkce_required`
- `token_field_map`

`actions` alanlari artik generic executor tarafindan okunabilen operation metadata da tasiyabilir:
- `method`
- `path`
- `response_items_path`
- `response_item_path`
- `cursor_path`
- `query_map`

## Runtime Lifecycle

Platform-managed connector akisi:
1. `save_connection`
   Config, access level, requested scope ve secret seti kaydedilir.
2. `start_oauth_authorization`
   Gerekirse OAuth state + PKCE session olusturulur.
3. `complete_oauth_callback`
   Token exchange sonucu auth summary ve credential metadata guncellenir.
4. `validate_connection` / `health_check_connection`
   Config, auth expiry ve health durumu tek yerde hesaplanir.
5. `refresh_connection_credentials`
   Refresh destekleyen connector'larda token rotasyonu yapilir.
6. `schedule_sync`
   Manual veya scheduled sync isi queue'ya atilir.
7. `dispatch_sync_jobs`
   Due job'lar claim edilir, lock alinir, retry/backoff kurallari uygulanir.
8. `execute_action`
   Capability + policy + confirmation kurallari denetlenir.
9. `revoke_connection`
   Credential kullanimi iptal edilir.
10. `disconnect_connection`
   Baglanti duraklatilir.
11. `reconnect_connection`
   Baglanti tekrar etkinlestirilir; gerekiyorsa auth yeniden istenir.

## Policy ve Permission Engine

Action calistirmadan once sunlar merkezi olarak denetlenir:
- connection enabled mi
- connection status aktif mi
- auth status uygun mu
- access level ilgili operation'i veriyor mu
- connector capability flag destekliyor mu
- safety setting ilgili operation'i kapatiyor mu
- destructive/write operation acik onay gerektiriyor mu

UI tarafinda gorunen safety ayarlari:
- `read_enabled`
- `write_enabled`
- `delete_enabled`
- `require_confirmation_for_write`
- `require_confirmation_for_delete`

Bu ayarlar `metadata.safety_settings` icinde tutulur; action runner her cagrida bunlari uygular.

## OAuth ve Credential Modeli

Connection kaydi auth lifecycle metadata tasir:
- `auth_status`
- `auth_summary_json`
- `credential_expires_at`
- `credential_refreshed_at`
- `credential_revoked_at`
- `last_health_check_at`

OAuth session tablosu:
- `integration_oauth_sessions`
- state, code_verifier, requested scopes, redirect URI, status, error, metadata

Uygulanan provider profilleri:
- `Slack`: OAuth2 exchange + refresh + revoke, channel/message sync, webhook signature verification
- `Notion`: bearer token ile canli validation, search tabanli sync, page/block aksiyonlari
- `GitHub`: OAuth2 exchange + repo sync + temel read/write aksiyonlari
- `Generic REST`: action metadata veya `resource_path` uzerinden generic HTTP execution
- `Elastic`: `_search`, `_doc`, cluster health ve temel belge yazma aksiyonlari
- `PostgreSQL`: DB adapter uzerinden validation, tablo snapshot sync, query/action abstraction

## Sync Orchestration

`integration_sync_runs` tablosu artik su bilgileri tasir:
- `mode`
- `trigger_type`
- `run_key`
- `attempt_count`
- `max_attempts`
- `scheduled_for`
- `next_retry_at`
- `lock_token`
- `locked_at`

Davranis:
- aktif bir run varsa yeni run force edilmeden acilmaz
- ayni `run_key` ile duplicate queue insert'i repo katmaninda baskilanir
- queue durumlari: `queued`, `running`, `retry_scheduled`, `completed`, `failed`
- failure durumunda exponential backoff benzeri retry planlanir
- stale `running` lock'lari timeout sonrasinda otomatik `retry_scheduled` durumuna geri alinir
- connection bazinda `sync_status` ve `sync_status_message` UI'a yansitilir
- opsiyonel `IntegrationSyncWorker` queue'yu HTTP disi arka plan dongusunde tuketebilir
- worker durumu API ve UI tarafinda gozetlenebilir; `worker_id`, son sure, ardışık hata sayisi ve son tick bilgisi gorulur

## Normalized Veri Modeli

Iki seviye veri tutulur:

1. `integration_records`
- kaynaktan gelen ham veya yarim-normalize kayit
- dedup key: `connection_id + record_type + external_id`

2. `integration_resources`
- agent/search/index tarafina uygun canonical model
- dedup key: `connection_id + resource_kind + external_id`

Canonical resource kind ornekleri:
- `messages`
- `documents`
- `tasks`
- `contacts`
- `events`
- `files`
- `database_records`

Resource alanlari:
- `title`
- `body_text`
- `search_text`
- `source_url`
- `parent_external_id`
- `owner_label`
- `occurred_at`
- `modified_at`
- `checksum`
- `permissions`
- `tags`
- `attributes`
- `sync_metadata`

## Observability

`integration_events` tablosu su olaylari saklar:
- connection saved
- oauth authorization started/completed/failed
- credentials refreshed
- connection revoked/disconnected/reconnected
- sync scheduled/completed/retry_scheduled/failed
- stale lock recovered
- action completed/blocked/failed
- safety settings updated

`integration_webhook_events` tablosu su bilgileri saklar:
- provider event id
- request signature ve request timestamp
- webhook status (`received`, `processed`, `challenge`, `failed`)
- response payload ve error
- replay korumasi icin `office_id + connector_id + event_id` unique key

UI detail ekraninda:
- auth summary
- sync history
- OAuth session history
- normalized resource preview
- event preview
- webhook preview
- capability summary
- safety controls
- connector skill ozeti

Support/release ekibi icin ek operational yuzey:
- `GET /integrations/ops/summary`
- setup completion rate
- OAuth completion rate
- sync success/failure rate
- stale pending setup listesi
- degraded connection listesi
- generated connector review backlog
- son warning/error event'leri

Bu ozet Integrations sayfasinda `Rollout ve destek ozeti` karti olarak gorunur.

## Connector Generator v2

Scaffold pipeline su girdileri kabul eder:
- `service_name`
- `docs_url`
- `openapi_url`
- `openapi_spec`
- `documentation_excerpt`

Urettikleri:
- connector draft spec
- inferred auth type
- inferred resources/actions
- generated UI schema
- suggested validation tests
- mock fixtures
- review checklist

Aktivasyon kuralı:
- scaffold dogrudan production'a acilmaz
- insan incelemesi zorunludur

Generator enrichment:
- `openapi_url` verildiginde URL gercekten cekilir ve JSON OpenAPI ise dogrudan parse edilir
- `docs_url` verildiginde HTML/text icerigi cekilip `documentation_excerpt` uretilir
- fetch ozetleri connector metadata ve scaffold response icinde tutulur
- fetch sirasinda SSRF sinirlari ve allowlist uyarilari uygulanir

## Otomatik Entegrasyon Istegi Akisi

Kullanici artik UI icinden dogrudan:
- "Slack workspace'imi bagla"
- "Jira'yi ekle"
- "Musteri portal API'sini dokuman URL'siyle bagla"

gibi istekler gonderebilir.

Sistem davranisi:
1. UI `POST /integrations/requests` ile dogal dil istegini yollar
2. service katmani prompt, dokuman URL ve bilinen servis ipuclarindan `service_name`, `category`, `auth_type` ve provider seed bilgisini cikarir
3. scaffold generator connector taslagi uretir
4. bilinen provider'lar icin OAuth endpoint, base URL ve default scope bilgileri taslaga merge edilir
5. sonuc `integration_generated_connectors` tablosuna version'li bir registry kaydi olarak `draft_ready` durumu ile kaydedilir
6. generated connector normal katalogta gorunur ve deneme modunda standart form akisi ile baglanabilir
7. canli kullanim icin `POST /integrations/requests/{connector_id}/review` ile acik bir onay karari gerekir
8. gerekirse `POST /integrations/requests/{connector_id}/refresh` ile taslak yeniden uretilir
9. operator `POST /integrations/requests/{connector_id}/state` ile connector'u katalogdan gizleyebilir veya tekrar acabilir
10. baglantisi yoksa `DELETE /integrations/requests/{connector_id}` ile registry kaydi temizlenebilir

Guvenlik siniri:
- bu akis source code'u otomatik degistirmez
- connector bir `generated connector record` olarak yaratilir
- review gate metadata olarak korunur
- kullanici yine UI'da gorunen alanlari doldurur
- write/delete aksiyonlari ayni policy engine'den gecmeye devam eder

Review / governance kurallari:
- `draft_ready`: katalogda gorunur, mock/dry-run baglantiya izin verilir
- `approved`: operator onayi verildi, istenirse canli kullanim acilabilir
- `rejected`: katalogdan efektif olarak dusurulur, yeni baglantiya izin verilmez
- `archived`: gecmis kayit olarak saklanir, aktif katalogdan cikar
- mevcut baglantisi olan generated connector `rejected` veya `archived` durumuna gecirilemez
- her generated connector registry entry'si `version` ve `enabled` alanlari ile tutulur; spec mutasyonlari `integration_generated_connector_versions` tablosuna snapshot olarak yazilir

## Learning Loop ve Pattern Memory

`integration_connector_patterns` tablosu basarili connector desenlerini saklar:
- service name
- category
- auth type
- docs host / base URL
- UI schema, action/resource ozeti
- success count
- source kind (`generated-draft`, `generated-refresh`, `review-approved`)

Davranis:
- generated connector olusturulurken ve onaylanirken pattern memory guncellenir
- yeni kullanici isteginde service/category/docs host benzerligi ile pattern memory taranir
- eslesen pattern'ler yeni taslak metadata'sina `pattern_matches` olarak yazilir
- UI tarafinda operator hangi ogrenilmis pattern'in kullanildigini gorebilir

## Guvenlik Sinirlari

- Secret'ler duz metin saklanmaz; sealed blob olarak tutulur
- Production posture icin `LAWCOPILOT_INTEGRATION_SECRET_KEY` verilmelidir
- Secret blob formati artik `v2` key-id tasir; `LAWCOPILOT_INTEGRATION_SECRET_KEY_ID` ve `LAWCOPILOT_INTEGRATION_SECRET_PREVIOUS_KEYS` ile rotasyon yapilabilir
- Secret key turetimi environment/posture baglamina baglidir; pilot/prod blob'lari birbirinin yerine acilmaz
- `base_url` dogrulamasinda `localhost`, private IP, link-local, reserved ve `.local` hedefleri reddedilir
- allowlist kontrolu `LAWCOPILOT_CONNECTOR_ALLOW_DOMAINS` ile daraltilabilir
- write/delete aksiyonlari confirmation duvarindan gecer
- OAuth summary UI'da gosterilir ama token degerleri asla dondurulmaz
- event/audit trail icinde `secret`, `token`, `password`, `authorization` benzeri anahtarlar otomatik redacted yazilir
- legacy connector secret'leri masaustu secure store'da kalir
- Slack webhook'lari imza ve konfigure replay penceresi ile dogrulanir
- replay korumasi ve duplicate delivery baskilama webhook event store uzerinden uygulanir
- PostgreSQL query runtime'i yalnizca `SELECT`, `WITH`, `INSERT`, `UPDATE`, `DELETE` ile sinirlandirilir; tablo/schema identifier'lari whitelist regex ile denetlenir

## Test Stratejisi

Backend:
- service-level lifecycle testleri
- gercek HTTP executor testleri (`MockTransport` uzerinden)
- scaffold v2 testleri
- docs/OpenAPI fetch enrichment testleri
- generated connector request ve persisted catalog testleri
- generated connector review ve live-use gate testleri
- generated connector refresh / enable-disable / delete testleri
- pattern-memory capture ve reuse testleri
- policy enforcement testleri
- sync queue/dispatch testleri
- stale lock recovery ve duplicate run-key testleri
- duplicate OAuth callback idempotency testleri
- webhook ingestion ve replay testleri
- worker tick testleri
- secret rotation/back-compat testleri
- provider pagination / retry / partial failure testleri
- database adapter path testleri
- route-level wrapper testleri
- launch ops summary ve office isolation testleri

Frontend:
- integrations page katalog/connect/sync akisi
- managed OAuth lifecycle ve safety controls
- dogal dil entegrasyon isteginden generated connector formuna gecis
- generated connector review ve canli-kullanim onay akisi
- generated connector refresh / hide / delete ve pattern-memory gorunurlugu
- rollout/support summary karti
- assistant sohbetindeki entegrasyon setup kartlari, capability preview, deep-link ve OAuth handoff gorunurlugu

Onemli not:
- Bu ortamda `fastapi.testclient.TestClient` ve tam ASGI transport ile POST route testleri guvenilir degil
- Problem minimal FastAPI uygulamasinda da tekrarlandigi icin LawCopilot'a ozel degil
- Bu nedenle route-level coverage, router endpoint invocation + ASGI scope tabanli dogrudan app cagrilari + full app route registration kombinasyonu ile saglanir

## Assistant Sohbet Orkestrasyonu

Integrations UI disinda artik ana asistan sohbeti de ayni platformu kullanir. Hedef davranis:
1. Kullanici "Connect Slack" veya "Integrate my CRM API" yazar
2. Sohbet akisi bunu integration intent olarak siniflandirir
3. Gerekirse generated connector olusturulur veya mevcut connector secilir
4. Eksik alanlar sohbet icinde tek tek toplanir
5. OAuth gerekiyorsa auth URL ve deep-link donulur
6. Callback tamamlandiginda sohbet kaldigi yerden devam eder
7. Basarili baglanti sonrasi asistan yeni capability'leri ve onerebilecegi ilk komutlari ayni sohbette aciklar

Bu akis `app.py` icinde normal assistant reply zincirine ilk-class bir branch olarak baglidir; demo cevap veya local-only mock bir overlay degildir.

### Sohbetten Tetiklenen Lifecycle

- intent detection: `connect`, `add`, `integrate`, `link`, `database`, `API` gibi ifadeler katalog/generator katmanina yonlendirilir
- connector resolution: built-in connector varsa o kullanilir, yoksa generated connector request olusturulur
- field collection: `ui_schema` icindeki zorunlu alanlar sirayla sorulur
- first-time guidance: assistant yaniti teknik alan adlarini tek basina birakmaz; neden istedigini ve sonraki adimda ne olacagini aciklar
- governance: generated connector canli kullanim istiyorsa review gate chat yolunda da korunur
- OAuth handoff: authorization URL ve integrations deep-link ayni assistant message icinde verilir
- resume: callback sonrasinda kullanici "Baglandim" veya "Durumu kontrol et" diyerek setup'i devam ettirebilir
- completion: health check ve ilk sync calistirilir, sonra capability ozeti ve takip onerileri chat'te gosterilir

### Pending Setup Storage

Sohbet setup state'i `integration_assistant_setups` tablosunda tutulur:
- `thread_id`
- `connector_id`
- `connection_id`
- `status`
- `missing_fields`
- `collected_config`
- `secret_blob`
- `metadata`

Bu sayede:
- setup yarida kalirsa sonraki mesajda devam edebilir
- OAuth callback ile baglanti tamamlansa bile sohbet state'i kaybolmaz
- generated connector review / provider secimi / next step bilgileri tek yerde kalir
- stale kalan setup timeout sonunda `abandoned` durumuna cekilir ve tekrar aktif setup olarak yuklenmez

### Gizli Bilgi Koruması

Sohbet uzerinden gelen secret alanlari asla mesaj history'sinde duz metin olarak tutulmaz.

Davranis:
- assistant setup bir `secret` alan bekliyorsa kullanici mesaj icerigi persistence katmanina redacted yazilir
- ornek: `[Gizli deger paylasildi: Client secret]`
- gercek secret degeri `secret_blob` icinde sealed olarak saklanir
- assistant bubble ve audit/event trail token veya secret degerlerini geri yansitmaz
- duplicate OAuth callback ikinci kez gelse bile yeni token exchange yapilmaz; mevcut session ve connection durumu korunur

### Deep-Link ve UI Handoff

Sohbet cevabi minimum gerekli UX'i iki sekilde tasir:
- `deep_link_path`: kullaniciyi dogrudan ilgili connector/setup state'i ile Integrations sayfasina goturur
- `authorization_url`: OAuth saglayici yetkilendirme sayfasini acmak icin kullanilir

Assistant UI bubble karti bu iki linki kullaniciya teknik detay gostermeden sunar:
- `Kurulum ekranini ac`
- `Izin ekranini ac`

Kart ayni zamanda su bilgileri gorunur kilar:
- `Siradaki adim`: kullanicinin su anda yapmasi gereken tek sey
- `Bu baglanti tamamlandiginda yapabileceklerim`: capability preview chip'leri
- `Kurulum notlari`: review gate, istenecek izinler ve dikkat notlari

Integrations sayfasi URL query parametrelerinden `connector`, `connection`, `setup`, `state`, `code`, `error` verilerini okuyup setup state'ini otomatik geri yukler.

### Assistant-Gorunur Integration Tooling

Tool registry tarafinda asistan ve diger orchestration katmanlari icin su araclar bulunur:
- `integrations.request_connector`
- `integrations.get_connector`
- `integrations.review_connector`
- `integrations.preview_connection`
- `integrations.save_connection`
- `integrations.start_oauth`
- `integrations.sync_now`
- `integrations.get_connection_status`

Bu araclar chat branch'i ile ayni service katmanini kullandigi icin policy, audit, permission ve connector lifecycle davranislari tek yerde kalir.

`GET /integrations/assistant-capabilities` cevabi artik dinamik `integration_skills` envanterini de tasir:
- connector id ve skill adi
- auth / health durumu
- izin verilen ve bloklu action'lar
- capability group'lari (`messages`, `documents`, `tasks`, `databases`, `files`, `events`)
- asistanin kullanabilecegi capability ozeti ve onerilen takip prompt'lari

## Yeni Connector Ekleme

Varsayilan tercih:
1. Once `POST /integrations/requests` veya UI dogal dil istegi ile generated connector olustur
2. Gercek provider davranisi kalici olacaksa `catalog.py` icine built-in `ConnectorSpec` tasin
3. O provider icin gerekirse `runtime.py` icinde executor/sync/webhook adapter'i ekle

Kalici built-in connector eklemek icin:
1. `catalog.py` icinde yeni `ConnectorSpec` ekle
2. `auth_config`, `ui_schema`, `permissions`, `actions`, `resources` alanlarini doldur
3. Generic HTTP executor yetmiyorsa `runtime.py` icine provider adapter'i ekle
4. Normalize map gerekiyorsa `normalization.py` tarafina record/resource eslesmesi ekle
5. Service testine connector lifecycle senaryosu ekle
6. Gerekirse UI detail akisi icin ek buton veya preview alanlari ekle

## Yeni Auth Type Ekleme

1. `ConnectorSpec.auth_type` ve `auth_config` sozlesmesini guncelle
2. `service.py` icindeki auth summary ve validation davranisini genislet
3. Secret merge/rotation kurallarini belirle
4. Route + UI mutation akisini ekle
5. Policy engine'in auth-state yorumunu guncelle
6. Test ekle

## Migration Yaklasimi

- Legacy masaustu connector'lar korunur
- Yeni provider'lar platform-managed olarak eklenir
- Gerektiginde legacy provider, ayni DSL ve lifecycle ile kademeli tasinabilir
- Connection persistence back-compat icin repository kolonlari migration-safe `ALTER TABLE ADD COLUMN` mantigi ile genisletilir

## Launch Notlari

Launch oncesi dogrulanmasi gereken en kritik integration akislari:
- ana sohbette `Connect Slack`
- generated connector review gate
- OAuth baslat / callback / duplicate callback
- stale setup abandon + restart
- sync queue / worker recovery
- webhook duplicate delivery
- office isolation

Bu akislarda support ekibinin ilk bakacagi yuzey:
- `Integrations > Rollout ve destek ozeti`
- `Integrations > Olay gunlugu`
- `Integrations > Webhook gunlugu`
