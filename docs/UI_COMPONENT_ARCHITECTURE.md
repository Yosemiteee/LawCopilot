# LawCopilot UI Production Bileşen Mimarisi (v1 Taslak)

Bu doküman, mevcut tek dosya `apps/ui/index.html` yapısını üretim seviyesinde sürdürülebilir bir bileşen mimarisine parçalamak için hedef tasarımı tanımlar.

## 1) Hedefler

- Tek dosya/inline script yaklaşımını modüler yapıya dönüştürmek
- Ekran (page), bileşen (component), servis (api/auth), state ve güvenlik sorumluluklarını ayırmak
- Test edilebilirlik (unit + smoke) ve erişilebilirlik (a11y) tabanını hazırlamak
- API sözleşmelerini typed bir katmanla (en azından JSDoc/TS tipi) güvenceye almak

## 2) Önerilen Klasör Yapısı

```text
apps/ui/
  public/
    index.html
  src/
    app/
      AppShell.tsx
      Router.tsx
      GuardedRoute.tsx
    pages/
      DashboardPage.tsx
      DocumentsPage.tsx
      AssistantPage.tsx
      ConnectorsPage.tsx
      SettingsPage.tsx
    components/
      layout/
        SidebarNav.tsx
        TopBar.tsx
      common/
        Card.tsx
        StatusBadge.tsx
        JsonPreview.tsx
        FormField.tsx
      dashboard/
        HealthKpis.tsx
      documents/
        IngestForm.tsx
        SearchPanel.tsx
      assistant/
        AskPanel.tsx
      connectors/
        EmailDraftForm.tsx
        SocialIngestForm.tsx
      settings/
        ApiSettingsForm.tsx
    services/
      apiClient.ts
      authService.ts
      healthService.ts
      documentService.ts
      queryService.ts
      emailService.ts
      socialService.ts
    state/
      sessionStore.ts
      settingsStore.ts
      uiStore.ts
    hooks/
      useHealth.ts
      useAuthToken.ts
      useAsyncAction.ts
    types/
      api.ts
      auth.ts
      domain.ts
    security/
      inputSanitizer.ts
      safeLogger.ts
    styles/
      tokens.css
      globals.css
  tests/
    unit/
    e2e/
```

## 3) Bileşen Sınırları (Component Boundaries)

- **Pages**: Sadece orkestrasyon + route-level state.
- **Components**: Yeniden kullanılabilir UI parçaları, iş kuralı içermez.
- **Services**: HTTP çağrıları, hata normalize etme, header/token yönetimi.
- **State**: Oturum, API base URL, aktif model/rol gibi uygulama durumu.
- **Security**: Input temizleme, istemci tarafı güvenli loglama, PII maskesi.

Kural: Bileşenler doğrudan `fetch` çağırmaz; sadece `services/*` üzerinden konuşur.

## 4) Sayfa Bazlı Parçalama

### Dashboard
- `HealthKpis`: rol/model/sağlık KPI kartları
- `HealthStatusPanel`: JSON health çıktısı + loading/error state

### Documents
- `IngestForm`: dosya seçimi + rol seçimi + upload lifecycle
- `SearchPanel`: query validation + source listesi gösterimi

### Assistant
- `AskPanel`: soru, rol/model seçimi, cevap ve hata durumları

### Connectors
- `EmailDraftForm`: alıcı/konu/içerik doğrulama + draft sonucu
- `SocialIngestForm`: kaynak/handle/içerik + read-only ingest akışı

### Settings
- `ApiSettingsForm`: API URL persist (`localStorage`) + doğrulama

## 5) API Sözleşme Katmanı

`services/apiClient.ts` için minimum kontrat:

- Timeout (örn. 10s)
- JSON parse guard (text -> safe parse)
- Hata normalize (`{code,message,details?}`)
- Otomatik `Authorization` header ekleme
- 401 için kontrollü token yenileme/redirect akışı

## 6) Üretim Hazırlığı Checklist

- [ ] UI build pipeline (Vite) + lint + typecheck
- [ ] Component testleri (form validation, loading/error state)
- [ ] E2E smoke: auth token al -> health -> query -> email draft
- [ ] CSP ve güvenli header’lar (deploy katmanında)
- [ ] `console.log` yerine sanitize edilmiş logger
- [ ] Hata mesajlarında teknik detay sızıntısı engeli

## 7) Geçiş Planı (Incremental)

1. `index.html` içindeki API ve auth çağrılarını `services/` katmanına çıkar.
2. Navigation ve ortak card/status bileşenlerini ayır.
3. Her sayfayı tek tek `pages/*` altına taşı (Documents -> Assistant -> Connectors).
4. Son aşamada framework migration (React/Vue) + test pipeline devreye al.

Bu yaklaşım, riskli “big bang” değişim yerine kontrollü ve geri alınabilir geçiş sağlar.
