# Desktop Auto Update

LawCopilot masaüstü uygulaması artık tek seferlik kurulumdan sonra yerinde güncelleme akışına hazırdır.

## Ne çalışıyor

- Electron ana sürecinde `electron-updater` tabanlı update controller var.
- Ayarlar ekranında update feed URL, kanal, açılışta kontrol ve otomatik indirme ayarları yönetiliyor.
- Kullanıcı uygulama içinden:
  - yeni sürüm kontrolü başlatabilir
  - bulunan sürümü indirebilir
  - indirilen sürümü yeniden başlatıp kurabilir
- Update durumu preload bridge ile UI’a canlı aktarılıyor.

## Paket desteği

- Windows: `NSIS` hedefi update için uygundur.
- Linux: `AppImage` hedefi gerekir.
- macOS: paketli sürüm gerekir; `dmg + zip` üretimi korunur.
- `dir` / unpacked geliştirme paketleri auto-update almaz.

## Nasıl publish edilir

Uygulama generic HTTP update feed kullanacak şekilde hazırlandı.

Beklenen yaklaşım:

1. Yeni sürüm için uygun paketleri üret:
   - Linux: `npm run package:linux`
   - Windows: `npm run package:windows`
   - macOS: `npm run package:macos`
2. Oluşan update metadata ve paket dosyalarını bir HTTP dizinine yükle.
3. Son kullanıcı makinesinde bir kez `Güncelleme sunucusu` alanına bu dizinin URL’i kaydedilsin.
4. Sonraki sürümlerde kullanıcı uygulama içinden yeni sürümü alır.

## Dikkat edilmesi gerekenler

- Linux kullanıcısı unpacked klasörden değil `AppImage` üzerinden kurulum yapmalı.
- Update feed URL boşsa uygulama sürüm kontrolü yapmaz.
- Bu yapı client tarafını çözer; release hosting hâlâ sizin yayın altyapınıza bağlıdır.

## Test

- Desktop updater smoke:
  - `node apps/desktop/scripts/updater-smoke.cjs`
- UI:
  - `npm --prefix apps/ui run test -- src/pages/SettingsPage.test.tsx`
