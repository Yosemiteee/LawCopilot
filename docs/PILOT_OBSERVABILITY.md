# Pilot Observability ve Runbook

Son güncelleme: 2026-04-11

## Amaç
Bu not, LawCopilot'un ilk pilot kullanıcılarla güvenli şekilde test edilmesi için hangi telemetry yüzeylerinin bulunduğunu, hangi komutların çalıştırılacağını ve hangi durumların launch blocker sayılacağını özetler.

## Yeni telemetry yüzeyleri

### API endpoint'leri
- `GET /telemetry/health`
  Runtime, workspace ve connector durumunun kısa özeti.
  Not:
  - `lawyer` rolü restricted görünüm alır
  - `admin` rolü tam diagnostic yol ve event yüzeyi görür
- `GET /telemetry/events/recent`
  Son structured app event'leri.
  Not: bu endpoint artık yalnız `admin` erişimine açıktır.
- `GET /telemetry/pilot-summary`
  Pilot için derlenmiş güvenli özet:
  - recommendation accepted/rejected
  - memory correction sayıları
  - KB search diagnostics
  - connector attention/retry/stale özetleri
  - reflection run health
  - desktop runtime recovery sinyalleri
  - onboarding hints
  - known limitations / launch blockers
- `GET /assistant/runtime/jobs`
  Runtime job queue özeti ve son background knowledge bakım işleri.
- `POST /assistant/runtime/jobs/process`
  Kuyruktaki knowledge background işlerini backend single-writer authority altında işler.

### Structured event'ler
Sensitive içerik loglanmaz. Aşağıdaki alanlar metadata-only yazılır:
- `pilot_kb_search`
- `pilot_memory_correction`
- `pilot_recommendations_requested`
- `pilot_recommendation_feedback`
- `pilot_assistant_message_feedback`
- `personal_kb_reflection_completed`
- `personal_kb_reflection_failed`
- `personal_kb_connector_sync_completed`
- `personal_kb_orchestration_completed`

Structured logger artık şu davranışı zorunlu uygular:
- `prompt`, `content`, `body`, `response_text`, `message_text`, `token`, `secret`, `authorization`, `oauth_*` gibi alanlar otomatik redakte edilir
- redakte edilen alanlarda yalnız `*_size` ve `*_redacted=true` gibi operasyonel metadata bırakılır
- nested payload içinde geçen hassas anahtarlar da aynı kuraldan geçer

### Desktop runtime diagnostics
Packaged desktop çalışırken API artık şu logları da okuyabilir:
- `LAWCOPILOT_DESKTOP_MAIN_LOG`
- `LAWCOPILOT_DESKTOP_BACKEND_LOG`

Özetlenen sinyaller:
- son backend hazır olma süresi
- recovery start / fail sayıları
- backend exit detect sayıları
- son runtime issue girdileri

Restricted telemetry görünümünde:
- log path'leri saklanır
- raw recent event listesi dönmez
- runtime issue detail alanları gizlenir
- runtime job son kayıt listesi saklanır, yalnız sayaçlar görünür

## Pilot komutları

### Hızlı tanı
```bash
./scripts/pilot_diagnostics.sh
```

Not:
- Eğer çalışan runtime `auth/token` bootstrap'ını kapatmışsa `LAWCOPILOT_PILOT_TOKEN` veya geçerli `LAWCOPILOT_BOOTSTRAP_ADMIN_KEY` verilmelidir.

Çıktı:
- `artifacts/pilot-diagnostics/health-*.json`
- `artifacts/pilot-diagnostics/telemetry-health-*.json`
- `artifacts/pilot-diagnostics/pilot-summary-*.json`

### Uzun süreli soak
```bash
LAWCOPILOT_PILOT_SOAK_DURATION_SECONDS=7200 \
LAWCOPILOT_PILOT_SOAK_INTERVAL_SECONDS=30 \
./scripts/pilot_soak.sh
```

Gerekirse:
```bash
LAWCOPILOT_PILOT_TOKEN="<mevcut_token>" ./scripts/pilot_soak.sh
```

Çıktı:
- `artifacts/pilot-soak/soak-*.jsonl`

Her satırda:
- health erişilebilir mi
- pilot summary status
- connector attention/retry
- reflection due
- runtime recovery counters
- runtime job queued/failed sayıları
- orchestration attention
- launch blocker / degraded mode bilgisi

### API smoke
```bash
./scripts/smoke_api.sh
```

Bu smoke artık şunları doğrular:
- `/health`
- `/telemetry/health`
- `/telemetry/pilot-summary`

## Launch blocker sayılacak durumlar
- `pilot-summary.overall_status == launch_blocked`
- desktop runtime recovery failure sayısı > 0
- runtime job failed sayısı > 0 ve tekrar eden failure nedeni çözülmemişse
- repeated health request failure
- connector attention gerektiren kritik hata artışı
- reflection health `critical`
- packaged runtime açılışında health endpoint stabil dönmüyor

## Yakın izlenecek ama blocker olmayan durumlar
- `reflection_due == true`
- `connector_retry_scheduled > 0`
- `retrieval_quality.low_result_searches` artışı
- `runtime_recent_recoveries > 0`
- onboarding hints hâlâ dolu olması

## Cross-platform smoke notları

### Linux
- packaged lifecycle smoke gerçek artifact üzerinde koşulmuş durumda
- `npm --prefix apps/desktop run test:lifecycle`
- `bash scripts/update_desktop_runtime.sh --if-needed --restart-running --launch`

### Windows
Pilot öncesi ayrıca koş:
1. `scripts/package_windows.sh`
2. installer ile temiz kurulum
3. ilk açılışta `/health` ve `/telemetry/pilot-summary`
4. uygulama içi restart
5. ikinci açılışta health continuity
6. `%APPDATA%` altındaki artifacts ve log yolları doğrulama

### macOS
Pilot öncesi ayrıca koş:
1. `scripts/package_macos.sh`
2. temiz kurulum / Gatekeeper davranışı
3. ilk açılışta `/health` ve `/telemetry/pilot-summary`
4. app relaunch
5. `~/Library/Application Support` altındaki runtime/log yolları doğrulama
6. notarization yoksa kullanıcı uyarı metni not edilmesi

## Pilot sırasında izlenecek ana metrikler
- recommendation accept/reject oranı
- assistant message like/dislike oranı
- memory correction toplamı ve dağılımı
- KB manual search sonuç kalitesi
- connector attention / retry / stale sayaçları
- reflection completed / failed sayısı
- runtime recovery count

## Production-ready vs partial vs stub

### Production-ready'e yakın
- Linux packaged desktop lifecycle
- structured pilot summary endpoint
- Memory Explorer + correction telemetry
- connector/reflection/orchestration health visibility

### Partial
- Windows/macOS packaged smoke manuel runbook aşamasında
- connector coverage provider'lar arasında eşit değil
- retrieval kalite diagnostikleri var ama gerçek pilot verisiyle tuning sürmeli

### Stub / foundation
- bazı consumer-world connector adapter'ları
- cross-platform installer imza/notarization operational katmanı
