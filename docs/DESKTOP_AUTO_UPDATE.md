# Desktop Auto Update

LawCopilot masaüstü uygulaması artık varsayılan olarak **GitHub Releases** üzerinden uygulama içi güncelleme alacak şekilde hazırdır.

## Ne çalışıyor

- Electron ana sürecinde `electron-updater` tabanlı update controller var.
- Varsayılan update provider `github`:
  - owner: `Yosemiteee`
  - repo: `LawCopilot`
- Kullanıcı uygulama içinden:
  - yeni sürüm kontrolü başlatabilir
  - bulunan sürümü indirebilir
  - indirilen sürümü yeniden başlatıp kurabilir
- Update durumu preload bridge ile UI'a canlı aktarılır.
- İleri seviye ayarlarda özel bir update sunucusuna geçmek hâlâ mümkündür, ama normal kullanımda gerekmez.

## Paket desteği

- Windows: `NSIS` hedefi update için uygundur.
- Linux: `AppImage` hedefi gerekir.
- macOS: paketli sürüm gerekir; `dmg + zip` üretimi korunur.
- `dir` / unpacked geliştirme paketleri auto-update almaz.

## Nasıl publish edilir

Beklenen yaklaşım GitHub release tag akışıdır:

1. Yeni sürüm numarasını güncelle.
2. İlgili değişiklikleri `main` branch'ine push et.
3. Release tag oluştur ve push et:
   - `git tag v0.7.0-pilot.3`
   - `git push origin v0.7.0-pilot.3`
4. GitHub Actions `release-desktop` workflow'u:
   - Windows `.exe`
   - `.blockmap`
   - `latest*.yml`
   dosyalarını release'e yükler.
5. Test kullanıcıları uygulama içinden `Yeni sürümü kontrol et > Güncellemeyi indir > Yeniden başlat ve kur` ile geçer.

## Dikkat edilmesi gerekenler

- Windows auto-update için GitHub Release artefact'larında `.exe + .blockmap + latest*.yml` birlikte bulunmalıdır.
- Linux kullanıcısı unpacked klasörden değil `AppImage` üzerinden kurulum yapmalıdır.
- GitHub provider kullanıldığı için son kullanıcıdan update URL girilmesi beklenmez.
- Özel feed URL alanı yalnız override ihtiyacı olan dağıtımlar içindir.

## Test

- Desktop updater smoke:
  - `node apps/desktop/scripts/updater-smoke.cjs`
- UI:
  - `npm --prefix apps/ui run test -- src/pages/SettingsPage.test.tsx`
