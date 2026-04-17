# LawCopilot

LawCopilot, yerel öncelikli, insan denetimli ve çok kaynaklı çalışan bir masaüstü asistandır. Amaç; kullanıcının belgelerine, kişisel tercihlerine, iletişim akışlarına ve bağlı servislerine kontrollü şekilde erişip tek bir asistan yüzeyinden iş yürütmektir.

Bugünkü ürün yönü `assistant-first` modelidir:
- ana çalışma yüzeyi `Asistan`
- kişisel bilgiler `Ayarlar > Profil`
- iletişim rehberi ve bildirim kuralları `Ayarlar > İletişim`
- asistanın tonu ve davranışı `Ayarlar > Asistan`
- hesaplar, sağlayıcılar ve entegrasyonlar `Ayarlar > Kurulum`

## Ürün Özeti

LawCopilot şu işleri birlikte yapar:
- çalışma alanındaki belgeleri tarar, indeksler, arar ve benzer belge bulur
- kullanıcı profili, tercihler ve kaynak kuralları gibi kalıcı bilgileri saklar
- WhatsApp, Telegram, e-posta, takvim ve sosyal medya gibi bağlı kaynaklardan canlı veri okuyabilir
- taslak, görev, takip, araştırma ve onay akışlarını tek asistan yüzeyinde yürütür
- öneriyi doğrudan aksiyona bağlamaya çalışır: taslak hazırla, mesaj öner, rota çıkar, araştırma yap, benzer belge bul

## Bugünkü Bilgi Mimarisi

Sistemde birden fazla bilgi yolu vardır. Bunlar aynı şey değildir ve farklı işlerde kullanılır.

### 1. Canlı araçlar ve senkron veriler

Güncel mesaj, e-posta, takvim, sosyal medya ve dış kaynak verileri için kullanılır.

Örnek:
- WhatsApp'ta son mesajlar
- Telegram'da belirli kişiyle son konuşma
- X mention veya DM durumu
- bağlı veri kaynaklarında güncel kayıtlar

Bu katman tazelik ister. Burada amaç eski hafızayı değil, güncel snapshot veya canlı sync verisini kullanmaktır.

### 2. Profil ve kişisel hafıza

Kullanıcının kendisiyle ilgili kalıcı bilgiler burada tutulur.

Örnek:
- sana nasıl hitap edilsin
- nerede yaşıyorsun
- ulaşım, seyahat, yemek, alışveriş tercihlerin
- hangi site veya sağlayıcıları tercih ettiğin
- önemli tarihler

Bu bilgiler `Ayarlar > Profil` içinde yönetilir.

### 3. İletişim hafızası

Kişiler ve gruplar için ayrı bir rehber tutulur. Bu katman kullanıcı profiliyle aynı şey değildir.

Burada şu tür bilgiler tutulur:
- kişi adı, kayıtlı isim, numara, e-posta, handle
- hangi kanallarda görüldüğü
- detaylı açıklama ve çıkarılan notlar
- izleme, engelleme ve anahtar kelime uyarıları
- kullanıcı isterse manuel düzenlenen iletişim açıklamaları

Bu bilgiler `Ayarlar > İletişim` içindedir.

### 4. Workspace belge retrieval

Belgeler ve eski işler için belge tabanlı erişim yolu kullanılır.

Örnek:
- buna benzer bir dilekçe var mı
- şu belge içinde bu konu geçiyor mu
- aynı klasörde benzer içerikler neler

Bu katman klasik sohbet hafızasından ayrı çalışır; belge parçaları, benzerlik ve dayanak odaklıdır.

### 5. Gelişmiş bilgi tabanı

Sistemde claim, artifact, dayanak ve derlenmiş bilgi katmanları vardır. Bu katman asistanın iç karar mekanizmasına destek verir. Günlük kullanıcı yüzeyinde ana navigasyon parçası değildir; daha çok sistemsel ve ileri düzey inceleme içindir.

## Kullanıcı Yüzeyleri

### Asistan

Ana yüzeydir. Kullanıcı burada:
- sohbet eder
- soru sorar
- belge, görev, taslak ve araştırma akışlarını tetikler
- canlı araçlardan gelen bilgiyi ister
- onay gerektiren taslak ve aksiyonları yönetir

### Çalışma Alanı

Seçilen klasör altındaki belge havuzunu gösterir.

Burada:
- klasör tarama
- belge listesi
- arama
- benzer belge bulma
- belge içeriğine atlama
- dosya bağlamı üzerinden çalışma
yapılır.

### Ayarlar > Profil

Kullanıcının kişisel ve kalıcı bilgileri burada tutulur.

Örnek alanlar:
- ad / hitap bilgisi
- konum ve yaşam noktası
- ulaşım, seyahat, yemek ve hava tercihleri
- kaynak ve site tercihleri
- önemli tarihler

### Ayarlar > İletişim

İletişim yönetiminin merkezi burasıdır.

İçerik:
- iletişim rehberi
- yakın kişiler
- izlenen kişi ve gruplar
- anahtar kelime uyarıları
- engellenen kişi ve gruplar

Kural:
- yakın kişiler artık otomatik yaratılmaz
- kullanıcı manuel ekler
- sistem mevcut iletişim profillerini veri geldikçe zenginleştirir

### Ayarlar > Asistan

Bu sekme hafıza yönetmez; asistan davranışını yönetir.

Burada:
- asistan adı
- ton
- çekirdek rol özeti
- davranış notları
- çalışma biçimi
tanımlanır.

Örnek:
- `Kısa ve net ol`
- `Daha proaktif davran`
- `Bana esprili hitap et`

Bu tür veriler kullanıcı profiline değil, asistan runtime profiline yazılır.

### Ayarlar > Kurulum

Kurulum ve entegrasyonların merkezi burasıdır.

Bugünkü kurulum grupları:
- yapay zeka sağlayıcısı
- Google ve Outlook
- Telegram ve WhatsApp
- X, Instagram ve LinkedIn
- Elastic ve diğer veri kaynakları
- masaüstü güncelleme ve workspace seçimi

## Entegrasyonlar

Repo ve ürün yüzeyinde şu bağlantılar bulunur:
- OpenAI / Codex / OpenAI uyumlu API / Ollama
- Google Gmail
- Google Takvim
- Outlook
- Telegram
- WhatsApp
- X
- Instagram
- LinkedIn
- Elastic
- PostgreSQL
- MySQL
- MSSQL

Not:
- Her entegrasyon aynı derinlikte değildir.
- Bazıları tam okuma/yazma akışına sahiptir, bazıları daha çok senkron veya snapshot odaklıdır.
- Canlı veri yetkileri sağlayıcı izinlerine ve hesap kapsamlarına bağlıdır.

## Güvenlik Duruşu

Varsayılan güvenlik modeli temkinlidir:
- varsayılan mod `local-only`
- çalışma klasörü seçmeden belge odaklı yüzeyler açılmaz
- disk kökü, sistem klasörleri ve kullanıcı klasörünün tamamı reddedilir
- klasör dışı erişim engellenir
- dış iletişim otomatik gönderilmez
- taslak ve onay akışları insan denetimli çalışır

Ayrıntılar:
- [WORKSPACE_SECURITY_MODEL.md](docs/WORKSPACE_SECURITY_MODEL.md)
- [SECURITY.md](docs/SECURITY.md)

## Mimari Bileşenler

- `apps/api`: FastAPI tabanlı yerel backend
- `apps/ui`: React + Vite tabanlı kullanıcı arayüzü
- `apps/desktop`: Electron tabanlı masaüstü kabuğu
- `apps/api/packaging`: backend bundling araçları
- `docs`: mimari, güvenlik, sınırlar ve release belgeleri
- `scripts`: test, smoke, paketleme ve pilot scriptleri
- `artifacts`: yerel runtime çıktıları, loglar ve geçici veriler

## Nasıl Çalışır

Tipik karar akışı şudur:
1. Kullanıcının niyeti çözülür.
2. İstenen şeyin canlı veri mi, kalıcı hafıza mı, yoksa belge retrieval mı olduğu belirlenir.
3. Gerekirse doğru araç veya veri kaynağı çağrılır.
4. Profil, iletişim hafızası ve workspace bağlamı yardımcı veri olarak eklenir.
5. Sonuç sentezlenir ve gerekirse taslak / aksiyon önerisine çevrilir.

Bu nedenle sistem yalnız klasik RAG mantığına dayanmaz. Canlı araçlar, profil hafızası, iletişim hafızası ve belge retrieval birlikte kullanılır.

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

### Masaüstü smoke testleri

```bash
cd apps/desktop
npm test
```

## Yerel Pilot Hazırlığı

```bash
./scripts/pilot_local.sh --mode local-only
```

Bu akış:
- backend sanal ortamını
- arayüz build çıktısını
- masaüstü bağımlılıklarını
- pilot runtime ortamını
hazırlar.

## Paketleme

### Windows

```bash
./scripts/package_windows.sh
```

Beklenen çıktı:
- `apps/desktop/dist/LawCopilot-<surum>-windows-x64.exe`

### macOS

```bash
./scripts/package_macos.sh
```

Beklenen çıktılar:
- `apps/desktop/dist/LawCopilot-<surum>-mac-universal.dmg`
- `apps/desktop/dist/LawCopilot-<surum>-mac-universal.zip`

Not:
- macOS notarization ve imzalama ayrı kimlik bilgileri ister
- Windows tarafında kod imzası yoksa SmartScreen uyarısı görülebilir

## Kısa Kullanım Akışı

1. Masaüstü uygulamayı aç.
2. Workspace seç.
3. `Ayarlar > Kurulum` içinden sağlayıcı ve bağlantıları tamamla.
4. `Ayarlar > Profil` içinden kişisel bilgilerini ve tercihlerini gir.
5. `Ayarlar > İletişim` içinden izleme/engel/keyword kurallarını düzenle.
6. `Asistan` ekranında soru sor, araştırma yap, taslak oluştur veya belge bul.
7. Gerekirse `Çalışma Alanı` ekranından belgeye in, benzer içeriği aç veya dosyayı bağlama ekle.

## Sınırlar ve Tasarım Kararları

- Sistem `assistant-first` ilerler; legacy hukuk/matter yüzeyleri repoda bulunabilir ama ana ürün yönü bunlar değildir.
- Gelişmiş hafıza ve epistemik katman sistemde vardır; ancak günlük kullanıcı navigasyonunda ana yüzey yapılmamıştır.
- İletişim ve kişisel profil ayrı tutulur; biri kullanıcının kendisi, diğeri çevresindeki kişi ve gruplardır.
- Araç kullanımı ile hafıza kullanımı aynı şey değildir. Güncel mesaj ve güncel sosyal medya verisi için doğrudan araç/snapshot yolu tercih edilir.

## İlgili Belgeler

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [INTEGRATIONS_PLATFORM.md](docs/INTEGRATIONS_PLATFORM.md)
- [BOUNDARY_DECISIONS.md](docs/BOUNDARY_DECISIONS.md)
- [PILOT_INSTALL_GUIDE.md](docs/PILOT_INSTALL_GUIDE.md)
- [V1_RELEASE_CRITERIA.md](docs/V1_RELEASE_CRITERIA.md)
