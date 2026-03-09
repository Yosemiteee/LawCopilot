# Çalışma Alanı Güvenlik Modeli

Son güncelleme: 2026-03-09

## Amaç
LawCopilot’ın belge erişimini kullanıcı tarafından seçilen tek bir kök klasör ile sınırlamak.

## Temel kural
Uygulama yalnız seçilen çalışma klasörü ve onun alt klasörlerine erişir.

## Ürün kararı
- V1’de yalnız alt klasör seçimi desteklenir
- disk kökü serbest değildir
- kullanıcı klasörünün tamamı serbest değildir
- güvenli varsayılan: yalnız işlenecek belge ağacını içeren çalışma klasörü verilir

## Yasaklı seçimler
V1’de reddedilir:
- disk kökü
- işletim sistemi sistem klasörleri
- kullanıcı klasörünün tamamı
- ağ paylaşımları
- klasör dışına taşıyan symlink zincirleri

## Platform davranışı
### Windows
- `C:\`, `D:\` gibi disk kökleri reddedilir
- `Windows`, `Program Files`, `Program Files (x86)`, `ProgramData`, `Users` kökleri reddedilir

### macOS
- `/` kökü reddedilir
- `Applications`, `Library`, `System`, `Users` kökleri reddedilir

### Linux
- `/` kökü reddedilir
- `bin`, `etc`, `usr`, `var`, `home` gibi sistem kökleri reddedilir

## Kullanıcıya gösterilen ret gerekçeleri
- `Disk kökleri çalışma klasörü olarak seçilemez.`
- `Sistem klasörleri çalışma klasörü olarak seçilemez.`
- `Kullanıcı klasörünün tamamı seçilemez.`
- `Ağ paylaşımları ilk sürümde desteklenmiyor.`
- `Seçilen klasör dışına erişim engellendi.`

## Doğrulama katmanları
### Masaüstü katmanı
- kullanıcı klasör seçimini native dialog ile yapar
- seçim `realpath` ile normalize edilir
- sistem yolu ve kök kontrolleri burada yapılır
- dosya açma / gösterme istekleri göreli yol ile çözülür

### Backend katmanı
- `PUT /workspace` sırasında kök klasör tekrar doğrulanır
- tarama sırasında kök dışına çıkan yollar atılır
- `..` kaçışları kabul edilmez
- symlink ile kök dışına çıkan yol reddedilir
- belge ayrıntı ve parça endpointleri yalnız aktif çalışma klasöründeki belge kimliklerini kabul eder
- eski çalışma klasörüne ait belge kimliği verilirse istek Türkçe hata ile reddedilir

## Saklama ilkeleri
- tam yol yalnız yapılandırma ve kök kaydında tutulur
- mümkün olduğunda göreli yol kullanılır
- günlüklerde tam yol yerine göreli yol tercih edilir

## Günlük olayları
- `workspace_root_selected`
- `workspace_root_rejected`
- `workspace_scan_started`
- `workspace_scan_completed`
- `workspace_scan_failed`
- `workspace_search_executed`
- `workspace_similarity_executed`
- `workspace_scope_violation_blocked`
- `workspace_document_attached_to_matter`

## Gizlilik ilkesi
- varsayılan mod `local-only`
- kullanıcı açıkça açmadıkça çalışma klasörü belgeleri bulut akışına girmez
- benzer dosya tespiti ve arama yerel veri üzerinde çalışır

## Tehdit modeli özeti
Bu tasarım şu riskleri azaltmayı hedefler:
- tüm diskin yanlışlıkla taranması
- sistem klasörlerinin indekslenmesi
- symlink ile kök dışına çıkılması
- uygulamanın keyfi tam yol erişimi yapması
- kullanıcı onayı olmadan hassas belgelerin dış modele gitmesi
