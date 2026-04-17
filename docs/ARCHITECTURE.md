# LawCopilot Mimari

Son güncelleme: 2026-03-09

## Katmanlar

### 1. Masaüstü kabuk `apps/desktop`
Sorumluluklar:
- ilk açılışta çalışma klasörü seçtirmek
- çalışma klasörü yapılandırmasını saklamak
- gömülü backend ikilisini başlatmak
- arayüz dist çıktısını yüklemek
- işletim sistemi seviyesinde güvenli klasör açma / gösterme işlemleri yapmak
- Codex ve Google OAuth akışlarını tarayıcıda başlatmak
- Google Gmail/Takvim sinyallerini yerel backend'e eşitlemek

Temel kararlar:
- Electron kullanılır
- paketlenmiş uygulama sistem Python’una düşmez
- backend binary yoksa paketli uygulama hata verir; kaynak koda dönmez
- paketli uygulama veriyi kullanıcı alanında saklar

### 2. Yerel API `apps/api`
Sorumluluklar:
- kimlik doğrulama ve ofis kapsamı
- dosya, görev, taslak, zaman çizelgesi ve belge belleği
- çalışma klasörü kökü doğrulama
- klasör tarama ve indeksleme
- kaynak dayanaklı arama
- dosya adı, içerik, belge türü, checksum ve klasör bağlamı ile açıklanabilir benzer dosya tespiti
- dosyaya çalışma alanı belgesi bağlama
- telemetri ve yapılandırılmış olay günlüğü
- Gmail thread mirror, takvim mirror, asistan ajandası ve önerilen aksiyonlar
- açık onaylı dış iletişim dispatch akışları

### 3. Arayüz `apps/ui`
Sorumluluklar:
- tamamen Türkçe çalışma masası
- dosya odaklı gezinme
- çalışma alanı görünümü
- belge listesi ve benzer dosya görünümü
- belge görüntüleyici, alıntı atlama ve pasaj vurgulama
- kaynak dayanaklı arama
- günlük ajanda, gelen iş sinyalleri ve önerilen aksiyonlar
- kanal bağımsız taslak merkezi
- dikkat edilmesi gereken noktalar, eksik belge sinyalleri ve taslak önerileri
- görev, taslak, risk notu ve kronoloji yüzeyleri
- çalışma modu ve güvenlik görünürlüğü

## Entegrasyon ve ajanda modeli

LawCopilot entegrasyonları iki katmanda yonetir:
- `Ayarlar`: mevcut masaustu onboarding ve OAuth akislari
- `Integrations`: generic connector katalogu, platform-managed baglantilar ve legacy status envanteri

Platform katmanlari:
- connector DSL: typed spec, auth metadata, resources, actions, triggers, sync policy
- runtime engine: preview, save, validate, sync, action execution, disconnect
- persistence: `integration_connections`, `integration_sync_runs`, `integration_records`, `integration_action_runs`
- security: sealed secret blob, scope/access model, human review gate, domain validation

Legacy baglantilar:
- Codex/OpenClaw hesap bağlantısı
- Google Gmail
- Google Takvim
- Google Drive
- Outlook Mail / Takvim
- Telegram
- WhatsApp
- X
- LinkedIn

Platform-managed ornek connectorlar:
- Notion
- Generic REST API
- PostgreSQL
- Elastic

Ürün yüzeyi:
- `Asistan` günlük ajanda, gelen iş sinyalleri ve önerilen aksiyonları gösterir
- `Taslaklar` kanal bağımsız dış iletişim ve çalışma çıktısı merkezidir
- `Integrations` yeni connector lifecycle, sync durumu ve scaffold generator yüzeyidir

Yerel mirror tabloları:
- `connected_accounts`
- `email_threads`
- `calendar_events`
- `assistant_actions`
- `outbound_drafts`
- `approval_events`
- `integration_connections`
- `integration_sync_runs`
- `integration_records`
- `integration_action_runs`

Karar akışı:
1. çalışma alanı ve dosya verisi
2. görev, risk notu ve taslaklar
3. legacy mirror kaynakları
4. platform-managed connector sync kayıtları
5. ajanda ve önerilen aksiyon üretimi
6. Codex/OpenClaw runtime ile özetleme ve aksiyon önerisi

Güvenlik kuralı:
- tüm dış iletişimler `taslak + onay` akışıyla yürür
- gönderim, kullanıcı onayı olmadan otomatikleşmez
- connector yazma/silme aksiyonları açık onay ister

## Çalışma alanı modeli

Yeni üst kavram `Çalışma Alanı`dır.

İlişkiler:
- bir ofisin tek bir aktif çalışma klasörü vardır
- çalışma alanı, seçilen kök klasör ve alt klasörlerini temsil eder
- çalışma alanı belgeleri ayrı tabloda tutulur
- çalışma alanı belgeleri bir veya daha fazla dosyaya bağlanabilir
- çalışma alanı belge havuzudur; dosya ise seçili hukuk işi için kürasyon ve iş akışı yüzeyidir
- dosya içi arama, bağlı çalışma alanı belgelerini de kullanabilir
- arama sonucu, benzer dosya sonucu, kronoloji ve taslak bağlamı belge görüntüleyiciye atlayabilir

Benzer dosya motoru:
- checksum eşleşmesini en güçlü sinyal olarak kullanır
- dosya adı ve başlık terimlerini puanlar
- chunk bazlı içerik örtüşmesini puanlar
- belge türü uyumunu hesaba katar
- klasör bağlamını sinyal olarak kullanır
- ortak hukuk terimlerinden açıklanabilir neden üretir
- sonuçları kör skor yerine dikkat notu ve taslak önerisi ile döndürür

Temel tablolar:
- `workspace_roots`
- `workspace_scan_jobs`
- `workspace_documents`
- `workspace_document_chunks`
- `workspace_matter_links`

## Çalışma modu
Varsayılan mod `local-only` olarak kilitlenmiştir.

Desteklenen modlar:
- `local-only`
- `local-first-hybrid`
- `cloud-assisted`

Kural:
- kullanıcı hangi modda olduğunu arayüzde açıkça görür
- çalışma klasörü belgeleri varsayılan olarak buluta gönderilmez

## Paketleme akışı

### Backend bundling
- PyInstaller ile tek ikili üretilir
- Linux: `lawcopilot-api`
- Windows: `lawcopilot-api.exe`
- macOS: `lawcopilot-api-x64`, `lawcopilot-api-arm64`

### Desktop packaging
- Windows: NSIS
- macOS: DMG + ZIP
- macOS masaüstü kabuğu hedefi: Universal

### CI akışı
- Windows paket işi
- macOS x64 backend işi
- macOS arm64 backend işi
- macOS universal paket işi

Tanım dosyası:
- [.github/workflows/build-desktop.yml](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/.github/workflows/build-desktop.yml)

## Güvenlik sınırları
- çalışma klasörü seçimi hem masaüstü IPC hem backend katmanında doğrulanır
- symlink ile kök dışına çıkış engellenir
- göreli yol kaçışları engellenir
- disk kökü ve sistem klasörleri reddedilir
- kullanıcı arayüzü keyfi tam yol okuyamaz
- dosya açma işlemi yalnız seçili kök altında göreli yol ile yapılır
- belge ayrıntı ve parça endpointleri aktif çalışma klasörü dışında kalan eski kayıtları açmaz

## Bilinen sınırlar
- Windows ve macOS kurulum hattı hazırdır, ancak gerçek imza / notarization kimlik bilgisi gerektirir
- similarity motoru yerel sinyal tabanlıdır; ağır embedding motoru değildir
- PDF/DOCX kalitesi belge içeriğine göre değişebilir
- canlı dosya izleme yoktur; V1'de manuel yeniden tarama vardır
