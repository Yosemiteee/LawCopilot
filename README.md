# LawCopilot

LawCopilot, yerel-oncelikli, kaynak dayanakli, insan denetimli ve uyarlanabilir bir kisisel + is asistanidir.

Bugünkü durum:
- indirilebilir masaüstü kabuğu vardır
- yerel backend gömülü ikili olarak paketlenebilir
- kullanıcı bir çalışma klasörü seçer
- uygulama yalnız bu klasör ve alt klasörlerine erişir
- belge tarama, arama, benzer içerik bulma ve kaynak bağlama yerelde çalışır
- günlük ajanda, önerilen aksiyonlar ve taslak + onay akışı aynı asistan yüzeyinde toplanır
- Google Gmail, Google Takvim, Telegram ve Codex/OpenClaw hesap bağlantıları Ayarlar ekranından yönetilir
- yeni `Integrations` yüzeyi platform-managed connector katalogu ve legacy baglanti envanterini birlikte gösterir
- kullanıcıya görünen arayüz Türkçedir

## Ana özellikler
- Çalışma alanı odaklı yerel hafıza
- Çalışma klasörü kapsamlı yerel belge hafızası
- Kaynak dayanaklı arama ve atıf görünümü
- Tek tıkla belge görüntüleyici, alıntı atlama ve pasaj vurgulama
- Dosya adı, içerik, belge türü, checksum ve klasör bağlamı ile açıklanabilir benzer içerik tespiti
- Ajanda, görev, taslak ve takip akışları
- Günlük ajanda, gelen iş sinyalleri ve önerilen aksiyonlar
- Gmail/Takvim/Telegram sinyallerini görev ve çalışma verisiyle birleştiren asistan yüzeyi
- Integrations katalogu, connector lifecycle, sync ve action yönetimi
- Dikkat edilmesi gereken noktalar, eksik bilgi sinyalleri ve taslak önerileri
- Taslak öncelikli, insan onaylı kullanım modeli
- Windows ve macOS paketleme hattı

## Klasörler
- `apps/api`: FastAPI tabanlı yerel backend
- `apps/ui`: React + Vite tabanlı Türkçe çalışma masası
- `apps/desktop`: Electron tabanlı masaüstü kabuğu
- `apps/api/packaging`: PyInstaller tabanlı backend bundling araçları
- `docs`: mimari, güvenlik, pilot kurulum ve kapsam belgeleri
- `scripts`: test, smoke, paketleme ve release doğrulama scriptleri
- `artifacts`: yerel veritabanı, günlükler ve geçici çalışma çıktıları

## Varsayılan güvenlik duruşu
- varsayılan çalışma modu `local-only`
- çalışma klasörü seçmeden belge ekranları kullanılmaz
- disk kökü ve sistem klasörleri reddedilir
- kullanıcı klasörünün tamamı reddedilir
- ağ paylaşımları ve klasör dışı erişim engellenir
- bağlayıcılar varsayılan olarak temkinli modda tutulur
- dış iletişim otomatik gönderilmez

Ayrıntılar için:
- [WORKSPACE_SECURITY_MODEL.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/WORKSPACE_SECURITY_MODEL.md)
- [SECURITY.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/SECURITY.md)

## Geliştirme

### Backend testleri
```bash
cd apps/api
.venv/bin/python -m pytest -q tests
```

### Arayüz testleri
```bash
cd apps/ui
npm test
npm run build
```

`npm test` şunları birlikte çalıştırır:
- Türkçe arayüz guard kontrolü
- route ve onboarding testleri
- temel assistant ve workbench smoke testleri

### Masaüstü smoke testi
```bash
cd apps/desktop
npm test
```

`npm test` şunları birlikte çalıştırır:
- desktop backend boot smoke
- çalışma klasörü güvenlik smoke testi
- packaged runtime config smoke testi

## Yerel pilot hazırlığı
```bash
./scripts/pilot_local.sh --mode local-only
```

Bu komut şunları hazırlar:
- backend sanal ortamı
- arayüz build çıktısı
- masaüstü bağımlılıkları
- `artifacts/runtime/pilot.env`

## Paketleme

İlk açılış davranışı:
1. uygulama doğrudan başlangıç akışına girer
2. kullanıcı çalışma klasörü seçmeden ana workbench açılmaz
3. çalışma klasörü seçildikten sonra giriş ekranı `Çalışma Alanı` olur

### Windows
```bash
./scripts/package_windows.sh
```

Beklenen çıktı:
- `apps/desktop/dist/LawCopilot-<surum>-windows-x64.exe`
- `artifacts/windows-build-artifacts.json` veya CI içindeki Windows build manifesti

GitHub indirilebilir sürüm:
- Etiketli release'lerde Windows kurulum dosyası GitHub `Releases` sayfasına yüklenir.
- İndirilebilir son kurulum için repo içindeki `Releases` bölümünü kullanın.

### macOS
```bash
./scripts/package_macos.sh
```

Beklenen çıktılar:
- `apps/desktop/dist/LawCopilot-<surum>-mac-universal.dmg`
- `apps/desktop/dist/LawCopilot-<surum>-mac-universal.zip`
- `artifacts/macos-build-artifacts.json` veya CI içindeki macOS build manifesti

Not:
- macOS tarafında gerçek notarization ve imzalama bu repoda yapılandırılabilir, ancak kimlik bilgileri gerektirir
- Windows tarafında kod imzası yoksa SmartScreen uyarısı görülebilir

## Önemli API yüzeyleri
- `GET /workspace`
- `PUT /workspace`
- `POST /workspace/scan`
- `GET /workspace/scan-jobs`
- `GET /workspace/documents`
- `POST /workspace/search`
- `POST /workspace/similar-documents`
- `POST /matters/{matter_id}/documents/attach-from-workspace`
- `GET /matters/{matter_id}/workspace-documents`
- `GET /integrations/catalog`
- `POST /integrations/connections`
- `POST /integrations/connections/{id}/sync`
- `POST /integrations/scaffold`

## Kısa ürün akışı
1. Masaüstü uygulamayı aç
2. Çalışma klasörü seç
3. Klasörü tara
4. Belgeleri listele, klasör bazlı arama yap ve benzer içerikleri bul
5. Ayarlar ekranindan legacy OAuth baglantilarini, `Integrations` ekranindan ise yeni connector katalogunu yonet
6. Asistan ekranında günün ajandasını ve önerilen aksiyonları incele
7. Dikkat edilmesi gereken noktaları, eksik bilgi sinyallerini ve taslak önerilerini incele
8. Gerekli belgeleri veya notları çalışma bağlamına ekle
9. Arama sonucu, benzer içerik sonucu veya taslak bağlamından ilgili belgeye tek tıkla git
10. Görev, taslak, takip ve bilgi derleme akışlarını yürüt

## Çalışma alanı ve bağlam ilişkisi
- Çalışma alanı, seçilen klasör altındaki yerel belge havuzudur.
- Legacy `matter/dosya` yüzeyleri hâlâ repoda vardır; bunlar proje veya iş bağlamı gibi düşünülebilir.
- Bir çalışma alanı belgesi bir veya daha fazla bağlama bağlanabilir.
- Benzer içerik tespiti ve klasör bazlı arama önce çalışma alanında yapılır; daha derin çalışma bağlı kayıtlar üzerinden devam eder.

## Kaynak dayanaklı inceleme akışı
1. Çalışma Alanı veya Belgeler ekranında arama yapın.
2. Dayanak pasaj veya benzer dosya sonucundaki `Belgedeki yeri aç` eylemini kullanın.
3. Belge görüntüleyici seçili parçayı vurgular, yakın bağlamı gösterir ve parça gezgini ile ilerlemenizi sağlar.
4. Masaüstü uygulamasında çalışıyorsanız aynı ekrandan belgeyi sistem uygulamasında açabilir veya klasörde gösterebilirsiniz.

## İlk kurulum için kısa kullanıcı metni
- Uygulamayı açın.
- İstediğiniz alt klasörü seçin.
- Başlangıç model profilini seçin.
- İsterseniz Codex sağlayıcısını, Google Gmail/Takvim bağlantısını ve Telegram bot bağlantısını kaydedin.
- Disk kökü, sistem klasörleri ve kullanıcı klasörünün tamamı güvenlik nedeniyle kabul edilmez.
- İlk tarama bitince `Çalışma Alanı` ekranı açılır.
- Günün öncelikleri, açık onay isteyen taslaklar ve bekleyen iletişimler `Asistan` ekranında görünür.

## Pilot sınırı
- Başlangıç model profili masaüstü yapılandırmasına kaydedilir ve uygulama açılışında varsayılan yönlendirme politikası olarak kullanılır.
- OpenAI hesabı için tarayıcı tabanlı Codex oturumu, OpenAI API, OpenAI uyumlu uç nokta ve yerel Ollama için masaüstü onboarding vardır; ayarlar yerel masaüstü yapılandırmasına kaydedilir.
- Google Gmail ve Google Takvim için masaüstü OAuth onboarding vardır; bağlantı durumları Ayarlar ve Çekirdek ekranında görünür.
- `Integrations` ekranı legacy masaustu baglantilarini katalogta gorunur kilarken yeni platform-managed connector'lar icin ortak lifecycle sunar.
- Telegram bot tokeni ve izinli kullanıcı kimliği için masaüstü onboarding vardır; istenirse test mesajı atılabilir.
- OpenAI hesabınız Google ile bağlıysa tarayıcıda açılan giriş ekranında Google seçeneğiyle devam edebilirsiniz. Codex oturumu seçilen modeli yerel masaüstü ayarına kaydeder.
- Ayrı `E-posta Taslakları` ve `Sosyal Medya` ürün yüzeyi kaldırılmıştır; dış aksiyonlar `Asistan` ve `Taslaklar` ekranlarından yürür.

## Not
- Repo içinde hâlâ hukuk odaklı veya `matter/dosya` isimleri taşıyan legacy yüzeyler vardır.
- Bu branch'teki yön artık daha genel amaçlı, uyarlanabilir bir asistana doğrudur; yeni değişiklikler assistant-first yaklaşımı izlemelidir.

## İlgili belgeler
- [ARCHITECTURE.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/ARCHITECTURE.md)
- [INTEGRATIONS_PLATFORM.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/INTEGRATIONS_PLATFORM.md)
- [BOUNDARY_DECISIONS.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/BOUNDARY_DECISIONS.md)
- [PILOT_INSTALL_GUIDE.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/PILOT_INSTALL_GUIDE.md)
- [V1_RELEASE_CRITERIA.md](/home/sami/openclaw-safe/openclaw-docker-secure/workspace/lawcopilot/docs/V1_RELEASE_CRITERIA.md)
