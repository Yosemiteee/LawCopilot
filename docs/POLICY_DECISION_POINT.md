# Policy Decision Point

LawCopilot artık karar politikasını tek bir modülde topluyor:

- `artifact / claim / resolution` epistemic doğruluğu belirler
- `policy decision point` ise bunun üstünde ne yapılacağını belirler

Kaynak:

- `apps/api/lawcopilot_api/policies/decision.py`
- `apps/api/lawcopilot_api/policies/gateway.py`

## İki ayrı karar

### 1. Action policy

`resolve_action_policy(...)`

ve bunu action ladder ile birlikte saran:

`evaluate_execution_gateway(...)`

Şunları belirler:

- risk seviyesi
- onay gerekip gerekmediği
- preview zorunluluğu
- low-risk trusted path var mı
- bir aksiyonun `execute / preview / ask_confirm / draft` çizgisi

Bu karar artık şuralarda kullanılıyor:

- proactive recommendation payload
- proactive trigger payload
- assistant action ladder
- assistant komutu ile üretilen draft/action akışları
- sohbet mesajı paylaşım paneli draft akışı
- assistant tarafinda önerilen müvekkil güncellemesi / risk draft'ları
- agent runtime tool approval gating
- integration connector action gating

Bu sayede policy karari ile action ladder ayri yerlerde tekrar tekrar kurulmaz; ayni girdiden tek gateway sonucu uretilir.

### 2. Proactive governor

`resolve_proactive_policy(...)`

Şunları belirler:

- öneri şu an gösterilmeli mi
- yoksa sessiz kalınmalı mı
- suppression reason nedir

Kullandığı ana sinyaller:

- confidence
- urgency
- reminder fatigue
- interruption tolerance
- recent rejection count
- connector health
- reflection health
- suggestion budget

## Neden gerekli

Önceki durumda aynı karar mantığı farklı yerlere dağılmıştı:

- trigger suppression
- recommendation gating
- tool approval
- action ladder

Bu da aynı risk sınıfındaki iki akışın farklı davranmasına yol açabiliyordu.

Artık amaç şu:

- `aynı risk + aynı onay politikası -> aynı karar`
- `aynı düşük güven + aynı fatigue sinyali -> aynı suppression`

## Bilinçli sınırlar

Bu katman henüz final policy engine değil.

Hâlâ açık kalan işler:

- legal / workspace / personal scope için daha zengin predicate-level policy
- connector trust score’larının daha ayrıntılı kullanımı
- full PDP/PIP/PEP ayrımı
- UI’da policy reason’ların daha görünür taşınması

Ama mevcut halde en kritik boşluk kapanmıştır:

- proactive kararlar
- preview / approval çizgisi
- tool gating
- connector action gating

artık aynı merkezi karar omurgasına bağlıdır.
