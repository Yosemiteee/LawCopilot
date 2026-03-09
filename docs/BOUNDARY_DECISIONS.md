# Sınır Kararları

Son güncelleme: 2026-03-09
Durum: kilitli kararlar

## 1. Ürün kimliği
- Müşteriye görünen ürün `LawCopilot`tır
- İç runtime bileşenleri müşteri tarafından ayrı kurulmaz
- Müşteri akışında OpenClaw adı ve komutları görünmez

## 2. Masaüstü stratejisi
- Pilot dağıtım masaüstü kabuğu Electron’dur
- Hafifletme veya Tauri geçişi V1 önceliği değildir
- Öncelik: çalışan kurulum, güvenli klasör sınırı, yerel backend orchestration

## 3. Çalışma alanı sınırı
- Uygulama tek bir aktif çalışma klasörü ile çalışır
- Bu klasör dışındaki belgelere erişim yoktur
- Kullanıcı profilinin tamamı, disk kökü ve sistem klasörleri reddedilir
- İlk açılışta kullanıcı doğrudan çalışma klasörü seçme akışına girer
- Çalışma klasörü seçilmeden ana workbench yüzeyleri açılmaz
- Çoklu klasör desteği V1 kapsamı dışındadır

## 4. Veri duruşu
- Varsayılan çalışma modu `local-only`
- Hassas dosyalar yerelde taranır, indekslenir ve aranır
- Hibrit ve bulut modları ayarlarda görünür, ancak varsayılan değildir

## 5. Dosya modeli
- `matter` yapısı korunur
- Bunun üstüne `workspace` katmanı eklenir
- Çalışma alanı belgesi dosyaya bağlanır; belge kopyalanmaz
- Benzer belge arama ve genel arama önce çalışma alanında çalışır

## 6. Paketleme sınırı
- Paketli uygulama harici Python istemez
- Backend gömülü ikili olarak gelir
- Paketli uygulama binary bulamazsa kaynak çalışma zamanına geri düşmez

## 7. İnsan denetimi
- Taslaklar ve öneriler nihai kayıt değildir
- Otomatik dış gönderim varsayılan değildir
- Benzer dosya sonucu “kesin aynı dosya” diye sunulmaz
- Öneriler açıklamalı gelir ve manuel inceleme ister
