# Güvenlik İlkeleri

Son güncelleme: 2026-03-09

## Varsayılanlar
- çalışma modu varsayılanı `local-only`
- çalışma klasörü sınırı zorunludur
- dış gönderim otomatik değildir
- bağlayıcılar kontrollü davranır
- audit ve structured event log açıktır

## Erişim sınırları
- `office_id` tüm ana kayıtlarda açık tutulur
- dosya, belge ve çalışma alanı erişimi backend tarafından doğrulanır
- bağlanan çalışma alanı belgeleri yalnız ilgili dosya akışına taşınır

## Bağlayıcı güvenliği
- allowlist kontrollüdür
- PII redaction uygulanır
- prompt injection ve secret exfiltration kalıpları bloklanır
- riskli içerik preview seviyesinde durdurulur

## Masaüstü güvenliği
- packaged modda backend binary zorunludur
- sistem Python’una geri dönüş yoktur
- kullanıcı verisi paket içinden değil kullanıcı veri alanından çalışır

## İnsan denetimi
- kronoloji ve risk notları çalışma çıktısıdır
- taslaklar dış kullanımdan önce incelenir
- benzer dosya sonucu kesin hüküm değildir
