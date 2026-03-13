# Pilot Kurulum Rehberi

Son güncelleme: 2026-03-09

## Amaç
LawCopilot’ı kontrollü pilot dağıtıma hazırlamak:
- yerel backend
- Türkçe arayüz
- masaüstü kabuğu
- çalışma klasörü kısıtı
- Windows ve macOS paket yolu

## Yerel pilot hazırlığı
```bash
./scripts/pilot_local.sh --mode local-only
```

Hazırlananlar:
- `apps/api/.venv`
- `apps/ui/dist`
- `apps/desktop/node_modules`
- `artifacts/runtime/pilot.env`

## Geliştirme amaçlı masaüstü açılışı
```bash
cd apps/desktop
npm run dev
```

## Windows paketi
```bash
./scripts/package_windows.sh
```

Beklenen çıktı:
- `apps/desktop/dist/LawCopilot-<sürüm>-windows-x64.exe`

## macOS paketi
```bash
./scripts/package_macos.sh
```

Beklenen çıktılar:
- `apps/desktop/dist/LawCopilot-<sürüm>-mac-universal.dmg`
- `apps/desktop/dist/LawCopilot-<sürüm>-mac-universal.zip`

## İlk açılış akışı
1. Uygulama açılır
2. Kullanıcı doğrudan başlangıç ekranına düşer
3. Çalışma klasörü seçilmeden ana çalışma yüzeyleri açılmaz
4. Kullanıcı çalışma klasörü seçer
5. Kullanıcı isterse sağlayıcı kurulumunu, Google Gmail/Takvim bağlantısını ve Telegram bot doğrulamasını yapar
6. Disk kökü, kullanıcı klasörünün tamamı veya sistem klasörü seçilirse işlem reddedilir
7. İlk tarama başlatılır
8. Kullanıcı doğrudan çalışma alanı ekranına geçer
9. `Asistan` ekranı günlük ajanda, önerilen aksiyonlar ve taslak + onay akışı ile açılır

## Platform farkları
### Windows
- disk kökleri `C:\`, `D:\` gibi yollarla reddedilir
- `Windows`, `Program Files`, `ProgramData`, `Users` kökleri çalışma klasörü olarak kabul edilmez
- imzasız pilot paketlerde SmartScreen uyarısı görülebilir

### macOS
- `/` kökü reddedilir
- `Applications`, `Library`, `System`, `Users` kökleri çalışma klasörü olarak kabul edilmez
- notarization yoksa Gatekeeper uyarısı görülebilir

### Linux geliştirme ortamı
- `/` kökü reddedilir
- `bin`, `etc`, `usr`, `var`, `home` gibi sistem kökleri çalışma klasörü olarak kabul edilmez

## Saklama konumları
### Geliştirme
- veritabanı: `artifacts/lawcopilot.db`
- olay günlüğü: `artifacts/events.log.jsonl`
- denetim günlüğü: `artifacts/audit.log.jsonl`

### Paketli uygulama
- yapılandırma: kullanıcı yapılandırma dizini altında `desktop-config.json`
- veri ve loglar: kullanıcı uygulama verisi altında `artifacts/`

## Smoke doğrulama
```bash
./scripts/smoke_api.sh
./scripts/smoke_desktop.sh
./scripts/release_check.sh
```

CI ve paket raporları:
- Windows build sonunda `artifacts/windows-build-artifacts.json`
- macOS build sonunda `artifacts/macos-build-artifacts.json`
- yerel Linux paket doğrulamasında `artifacts/linux-build-artifacts.json`

## Geri alma
- uygulamayı kapat
- masaüstü çıktı klasörünü sil
- kullanıcı yapılandırma dizinindeki `desktop-config.json` dosyasını sil
- kullanıcı uygulama verisi altındaki `artifacts/` klasörünü sil
- veri korunacaksa `lawcopilot.db` ayrı yedeklenmelidir

## Bilinen pilot sınırlamaları
- kod imzası ve notarization kimlik bilgisi gerektirir
- canlı dosya izleme yoktur
- OCR yoktur
- benzerlik motoru yerel sinyal tabanlıdır
- OpenAI hesabı için tarayıcı tabanlı Codex oturumu masaüstü arayüzünden başlatılabilir
- Gmail ve Takvim bağlantıları masaüstü OAuth ile kurulur; ayrı e-posta veya sosyal medya modülü yerine Asistan ajandasına yansır
