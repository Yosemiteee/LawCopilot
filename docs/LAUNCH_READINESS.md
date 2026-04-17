# Launch Readiness

Tarih: 2026-04-08

Bu not, LawCopilot'un launch öncesi son hardening turundan sonra gerçek durumunu özetler.
Amaç, tamamlanan alanları, hâlâ partial kalan katmanları ve bilinçli stub sınırlarını tek yerde görmek.

## Pilot Observability Hardening

2026-04-11 itibarıyla launch hazırlığı için ek operasyon yüzeyleri eklendi.

Yeni doğrulananlar:
- `GET /telemetry/pilot-summary` ile recommendation feedback, memory correction, reflection, connector ve runtime recovery özetleri tek payload içinde alınabiliyor.
- Desktop runtime artık `desktop main log` ve `desktop backend log` yollarını API'ye geçiriyor; packaged runtime recovery sinyalleri pilot summary içinde görülebiliyor.
- Dashboard üzerinde `Pilot durumu` ve `Operasyon sinyalleri` kartları var:
  - onboarding hints
  - degrade mode mesajları
  - launch blocker notları
  - runtime recovery göstergeleri
- `scripts/pilot_diagnostics.sh` ve `scripts/pilot_soak.sh` ile pilot öncesi snapshot ve uzun süreli soak alınabiliyor.

Bu katman launch kararını kolaylaştırır ama tek başına production-ready garantisi değildir. Özellikle Windows/macOS packaged smoke hâlâ ayrı runbook ile tekrar koşulmalıdır.

## Dis Validation Sonucu

2026-04-08 tarihinde gerçek Linux packaged artifact ustunde ek bir dis validation kosuldu.

Dogrulananlar:
- `apps/desktop/dist/linux-unpacked/lawcopilot-desktop` artifact'i tekrar acildi ve `node apps/desktop/scripts/packaged-runtime-smoke.cjs apps/desktop/dist/linux-unpacked/lawcopilot-desktop` yeniden gecti.
- Calisan packaged runtime'ta `GET /health` basarili dondu.
- Canli packaged runtime'ta Google ve Outlook entegrasyonlari gercek bagli hesap olarak goruldu:
  - Google: `samiyusuf178@gmail.com`
  - Outlook: `samiyusuf_1453@hotmail.com`
- `GET /assistant/inbox` ve `GET /assistant/calendar` packaged runtime ustunde gercek provider verisi dondu.
- Ana sohbet uzerinden `Connect Slack` denendiginde assistant setup gercekten basladi ve bir sonraki zorunlu alan olarak `Client ID` istedi.

Bu turda cikan launch gate:
- `GET /integrations/ops/summary` packaged runtime icin `ready_for_launch=false` dondu.
- Kritik neden: `default_jwt_secret`
- Uyari nedeni: `local_secret_posture`

Yani bugunun gercek sonucu su:
- paketlenmis uygulama ve entegrasyon runtime'i calisiyor
- gercek bagli provider kullanimi goruluyor
- ama bu packaged runtime mevcut haliyle production secret posture'a gecmis degil

## Desktop Runtime Lifecycle Stabilization

2026-04-11 tarihinde packaged desktop runtime lifecycle zinciri ayrica sertlestirildi.

Eklenen runtime davranislari:
- Electron main process artik `desktop-main.pid` ve backend tarafinda `desktop-backend.pid` yazarak tekil process durumunu izliyor.
- Embedded API health poll mekanizmasi surekli calisiyor; arka arkaya health hatasi gorulurse kontrollu recovery akisi devreye giriyor.
- Backend child beklenmedik sekilde cikarsa supervisor yeniden baslatma planliyor; app kapanirken ayni mekanizma devreye girmiyor.
- Quit akisi artik backend kapanisini bekleyip pid dosyalarini temizliyor; stale process ve stale pid artifakti azaltildi.
- Tek-instance fallback daha siki hale getirildi; normal kullanicida stale lock yuzunden ikinci instance acilmasi daha zor.
- Backend logu health hazir oldugu anda `health_ready elapsed_ms=...` satiri yaziyor; startup sureleri artik runtime logundan okunabiliyor.
- Backend refresh artik fingerprint guard kullaniyor; backend env'i gercekten degismediyse config write sonrasi gereksiz force-restart yapilmiyor.
- `scripts/update_desktop_runtime.sh --if-needed --restart-running --launch` artik runtime guncel olsa bile calisan packaged instance'i gercekten yeniden baslatip health dogruluyor.

Paketli runtime uzerinde dogrulanan senaryolar:
- `fresh_launch`
- `long_running_health`
- `backend_crash_recovery`
- `duplicate_launch_guard`
- `graceful_restart`
- `crash_relaunch`

Yeni dogrulama komutlari:
1. `cd apps/desktop && npm run package:dir`
2. `cd apps/desktop && npm run test:packaged`
3. `cd apps/desktop && npm run test:lifecycle`
4. `bash scripts/update_desktop_runtime.sh --if-needed --restart-running --launch`

Beklenen sonuc:
- packaged smoke `packaged-runtime-smoke-ok`
- lifecycle smoke butun senaryolar icin `scenario_ok:*` ve finalde `packaged-lifecycle-smoke-ok`
- desktop runtime sync script sonunda `Desktop API is healthy at http://127.0.0.1:18731.`

## Bu Turda Tamamlananlar

### 1. Location hardening
- Native-grade adapter sözleşmesi netleştirildi.
- Desktop snapshot fallback artık permission-denied, capture-failed, privacy-mode ve stale/expired durumlarını ayırt ediyor.
- `browser_geolocation` akışı başarısız olduğunda UI sadece hata göstermiyor; degrade location state backend'e kalıcı olarak yazılıyor.
- Nearby candidates confidence ve navigation handoff, freshness ve privacy durumuna göre düşürülüyor.
- Location explainability kartı:
  - provider status
  - freshness
  - permission state
  - capture failure reason
  - fallback explanation
  gösteriyor.

### 2. Retrieval hardening
- `sqlite_hybrid_fts_v1` backend'i launch hardening sonrası `sqlite_hybrid_fts_v2` ranking profile ile çalışıyor.
- Query synonym coverage genişletildi.
- Metadata-aware ranking eklendi.
- Scope weighting daha güçlü hale getirildi.
- Low-confidence penaltisi eklendi.
- FTS query builder prefix yakalama ile genişletildi.
- Search sonucu artık ranking profile ve vector/reranker hook readiness bilgisi döndürüyor.

### 3. Orchestration / worker hardening
- Orchestration çalıştırıcısına process-level mutex eklendi.
- Fresh running job tekrar tetiklenmiyor.
- Stale running job recover edilip retry çizgisine alınıyor.
- Retry/backoff metadatası:
  - `retry_delay_seconds`
  - `next_due_at`
  - `consecutive_failures`
  - `status_message`
  ile daha görünür.
- Operational summary artık:
  - running job count
  - retry scheduled count
  - attention required count
  - next due at
  - last error
  bilgilerini veriyor.

### 4. User-facing polish
- Assistant home içindeki location card daha explainable hale geldi.
- Operational cards retry ve degradation bilgilerini daha net gösteriyor.
- Memory control yüzeyi son düzeltmeleri de özetliyor.
- Low-risk/proactive action kartlarında:
  - approval reason
  - undo strategy
  - preview policy
  daha açık gösteriliyor.

### 5. Launch safety polish
- Action ladder metadata daha tutarlı hale getirildi:
  - `execution_policy`
  - `approval_reason`
  - `irreversible`
- Silent irreversible action çizgisi korunuyor.
- Düşük riskli akışlarda dahi preview-before-confirm varsayımı korunuyor.

### 6. Integrations launch hardening
- Duplicate OAuth callback idempotent hale getirildi; aynı `state` ikinci kez gelirse yeni token exchange denenmiyor.
- Assistant setup timeout ile stale entegrasyon kurulumları `abandoned` durumuna taşınıyor.
- `GET /integrations/ops/summary` ile rollout/support görünürlüğü eklendi.
- Ops summary artık rollout posture uyarıları da veriyor:
  - dry-run halen acik mi
  - header auth acik mi
  - varsayilan JWT secret kullaniliyor mu
  - env-managed integration secret key eksik mi
  - OAuth drop-off veya sync failure spike var mi
- Connector request analytics generated connector kayıtlarını da sayıyor.
- Office bazlı izolasyon için launch-kritik regresyon eklendi.
- Packaged runtime smoke script gerçek packaged desktop runtime üstünde KB, location, connector sync, orchestration ve low-risk action preview akışlarını koşturabilecek hale getirildi.

## Production-ready'e Yakın

Bu alanlar launch için güçlü durumda, fakat ilk production kullanımından sonra ek telemetry ile izlenmeli:

- Personal knowledge base retrieval
- Explainability surfaces
- Memory correction flow
- Connector sync operational visibility
- Chat/home operational cards
- Device-capture destekli location fallback

## Partial

Bu alanlar çalışıyor, fakat enterprise veya yüksek trafik şartları için daha ileri hardening isteyebilir:

- Knowledge-base orchestration halen local JSON/state üstünden ilerliyor.
- Desktop packaged runtime smoke bu ortamda gerçek Linux artifact üzerinde geçti; yine de release makinesinde tekrar koşulmalı.
- Retrieval tarafındaki vector/reranker hook'ları hazırlık seviyesinde; aktif vector/reranker pipeline bağlı değil.

## Bilinçli Stub Sınırları

Bu turda stub'lar gerçekmiş gibi sunulmadı:

- Vector retrieval aktif değil.
- Reranker aktif değil.
- Native OS-level location provider tam anlamıyla ayrı bir sistem servisinden gelmiyor; mevcut desktop snapshot + browser/device capture hattı sertleştirildi.
- Desktop full packaged install smoke tüm hedef işletim sistemi varyantlarında henüz doğrulanmadı.

## Release Smoke Checklist

Minimum release-aday smoke:

1. `cd apps/api && .venv/bin/python -m pytest -q tests/test_knowledge_base.py`
2. `cd apps/api && .venv/bin/python -m pytest -q tests/test_integrations_platform.py tests/test_assistant_integration_chat.py tests/test_launch_stability.py`
3. `cd apps/ui && npm run test -- --run src/pages/IntegrationsPage.test.tsx src/pages/AssistantOperationalSurface.test.tsx`
4. `cd apps/ui && npm run build`
5. `node --check apps/desktop/main.cjs`
6. `node --check apps/desktop/scripts/packaged-runtime-smoke.cjs`
7. Package artifact hazirsa:
   - `cd apps/desktop && npm run package:linux`
   - `node apps/desktop/scripts/packaged-runtime-smoke.cjs apps/desktop/dist/linux-unpacked/lawcopilot-desktop`
8. Desktop üzerinde manuel smoke:
   - konum izni verildiğinde refresh
   - konum izni reddedildiğinde degrade kart
   - proactive suggestion preview
   - low-risk task/calendar preview
   - orchestration kartında retry görünürlüğü
   - Integrations sayfasında `Rollout ve destek ozeti`
   - ana sohbette `Connect Slack`

## Manual Launch Checks

### Location
- Konum izni verildiğinde `device_capture` state'i görünmeli.
- Konum izni reddedildiğinde current place uydurulmamalı.
- Stale snapshot durumunda navigation handoff false veya temkinli görünmeli.

### Retrieval
- Aynı sorguda personal/professional scope farkı korunmalı.
- Karar/gerekçe sorularında decisions/reflections öne gelmeli.
- Memory/preferences sorgularında preferences/persona kayıtları öne gelmeli.

### Operations
- Scheduler açıkken aynı iş üst üste bindirilmemeli.
- Hata alan job için retry zamanı görünmeli.
- Last error operational card üzerinde görünmeli.
- Integrations ops summary içinde stale setup, degraded connection ve review backlog görünmeli.

### Integrations
- Sohbette `Connect Slack` denince assistant setup başlamalı.
- Setup yarıda bırakılıp uzun süre beklendikten sonra `Durumu kontrol et` dendiğinde eski setup kapatılıp restart önerilmeli.
- Aynı OAuth callback iki kez gelirse sistem ikinci callback'te stabilize kalmalı.
- Farklı office / tenant altında başka kullanıcının connector veya event kaydı görünmemeli.

### UX / Safety
- Proaktif öneriler preview metni ile gelmeli.
- Kritik aksiyonlarda manual review korunmalı.
- Known profile kartlarında scope/shareability görünmeli.
- Memory düzeltmeleri son değişikliklerde görünmeli.

## Sonuç

Bu hardening turu sonrasında LawCopilot:

- daha explainable
- daha operational
- daha güvenilir
- launch'a daha yakın

hale geldi.

Ama dürüst durum şu:
- launch-ready foundation: evet
- tamamen risksiz production rollout: hayır

En büyük kalan riskler:
- packaged desktop end-to-end smoke'ın release günü öncesi gerçek makinede tekrar edilmesi
- local state/orchestration yükü arttığında operational telemetry'nin gözlenmesi
- vector/reranker hattı aktive edilmeden büyük KB büyümesinde retrieval davranışının tekrar benchmark edilmesi
- gerçek provider credential'ları ile release-aday ortamında bir son kullanıcı smoke'ının ayrıca koşulması
- release artifact veya hedef environment icin varsayilan JWT secret ve local-only integration secret posture'un kapatilmasi
