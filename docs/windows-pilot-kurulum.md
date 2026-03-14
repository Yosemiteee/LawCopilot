# LawCopilot Windows Pilot Kurulum Rehberi

Bu rehber, teknik olmayan bir test kullanıcısının LawCopilot'ı Windows masaüstünde gerçek uygulama gibi kurup denemesi içindir.

## Önerilen dağıtım şekli

Windows kullanıcısına `git clone` yaptırmayın. En doğru yol:

1. GitHub Actions ile Windows `.exe` kurulum paketini üretin.
2. Oluşan `.exe` dosyasını kullanıcıya gönderin.
3. Kullanıcı normal program kurar gibi kurup çalıştırsın.

Bu yöntem müşteri denemesi için en temiz yoldur.

## Windows paketi nasıl üretilir

Depoda hazır workflow vardır:

- `.github/workflows/build-desktop.yml`

İzlenecek adımlar:

1. Projeyi GitHub'daki private repoya push edin.
2. GitHub'da `Actions` sekmesini açın.
3. `build-desktop` workflow'unu seçin.
4. `Run workflow` deyin.
5. İş bitince `lawcopilot-windows` artifact'ını indirin.
6. Zip içinden `.exe` kurulum dosyasını çıkarın.
7. Bu `.exe` dosyasını test kullanıcısına gönderin.

## Test kullanıcısı ne yapacak

1. Gönderdiğiniz `.exe` dosyasını çalıştıracak.
2. Kurulumu tamamlayacak.
3. LawCopilot'ı açacak.
4. İlk açılışta:
   - model sağlayıcısını seçecek
   - gerekiyorsa OpenAI API anahtarını girecek
   - Google hesabını bağlayacak
5. Sonra sohbet, taslaklar, takvim, belgeler ve araçlar akışını kullanarak deneme yapacak.

## Test kullanıcısı için minimum gerekli kurulum

Tam deneme için en az şunlar gerekir:

### 1. AI sağlayıcısı

Kullanıcı şunlardan birini girmeli:

- OpenAI API anahtarı
- veya sizin pilot için verdiğiniz başka sağlayıcı bilgisi

### 2. Google bağlantısı

Google tarafı iki aşamalıdır:

#### Ofiste bir kez yapılır

Bir yönetici veya teknik kurulum yapan kişi:

1. Google Cloud Console'da proje açar.
2. Gmail API, Calendar API ve Drive API'yi etkinleştirir.
3. Desktop OAuth istemcisi üretir.
4. `Client ID` ve `Client Secret` bilgisini LawCopilot içindeki Google altyapı alanına kaydeder.

#### Kullanıcı kendi hesabını bağlar

1. `Google hesabını bağla` düğmesine basar.
2. Tarayıcıda Google oturumu açar.
3. İzinleri onaylar.
4. Uygulamaya geri döner.

Bağlantı kurulduktan sonra asistan Gmail, Takvim ve Drive verisini görebilir.

## Test senaryoları

Kullanıcıya aşağıdaki senaryoları uygulatın:

### Sohbet ve genel asistan

1. `Bugün ne yapmam gerekiyor?`
2. `Takvimimde bugün ne var?`
3. `Belgelerimde hangi dosyalar var?`

### Gmail ve taslak

1. `ornek@alan.com adresine selamımı ileten kısa bir mail hazırla`
2. `taslağa ekle maili`
3. `Taslaklar` sekmesinde taslağın göründüğünü kontrol etsin
4. `Onayla ve gönder` ile mail gönderimini denesin

### Google takvim

1. `Yarın 14:00 için müvekkil görüşmesi ekle`
2. Asistan onay istesin
3. Onay sonrası takvime düştüğünü kontrol etsin

### Google Drive / belgeler

1. `Drive'da son değişen dosyalarımı göster`
2. `Elimde hangi belgeler var?`

### Proaktif öneri

1. Açılışta asistanın günlük özet verip vermediğini kontrol etsin
2. Takvim boşluklarına göre öneri sunup sunmadığına baksın

## Kullanıcıdan istenecek geri bildirim

Pilot kullanıcıdan özellikle şunları isteyin:

1. Kurulum sırasında nerede takıldı?
2. Google hesabını bağlamak kolay mıydı?
3. Taslak oluşturma ve gönderme akışı anlaşılır mıydı?
4. Sohbet yanıtları gerçekten işe yarıyor mu?
5. Arayüzde karışık veya gereksiz gördüğü alanlar var mı?

## Not

Windows paketini Linux makinede güvenilir biçimde çapraz üretemiyoruz. Windows `.exe` üretimi için:

- ya GitHub Actions Windows job'unu kullanın
- ya da gerçek bir Windows makinede paket alın

Müşteri benzeri test için önerilen yol GitHub Actions artifact'ıdır.
