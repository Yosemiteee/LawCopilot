# Personal Model

LawCopilot içindeki `Personal Model`, klasik bir profil formu değildir. Kullanıcının kontrollü interview oturumları ve açık onaylı chat sinyalleri üzerinden oluşan, izinli ve yapılandırılmış bir kullanıcı anlama katmanıdır.

## Ne tutar

Sistem iki katmanlı çalışır:

1. `raw entries`
   Interview veya onaylı chat sinyalinden gelen ham soru/cevap kayıtları.

2. `normalized facts`
   Assistant tarafından seçici biçimde kullanılabilen yapılandırılmış fact kayıtları.

Her fact şu ayrımları korur:

- `confidence_type`: `explicit` veya `inferred`
- `scope`: `global`, `personal`, `project:*`
- `enabled`
- `sensitive`
- `never_use`

## Interview sistemi

Interview modülleri:

- goals
- work_style
- preferences
- communication

Desteklenen davranışlar:

- başlat
- duraklat
- devam et
- soru atla
- adaptif follow-up üret

Örnek:

- `preferred_work_time = flexible`
- follow-up: `preferred_work_time_flex`

## Chatten öğrenme

Normal sohbet içinde sistem bazı aday fact’leri fark eder ama otomatik kaydetmez.

Akış:

1. Chat sinyali doğal dilden çıkarılır
2. `personal_model_suggestions` kaydı oluşturulur
3. Assistant kullanıcıya sorar
4. Kullanıcı `evet` derse fact `inferred + user_confirmed`
5. Kullanıcı `hayır` derse suggestion reddedilir

Bu tasarım, sessiz memory injection yerine açık izin modelini korur.

Ek davranışlar:

- Aynı öğrenme birkaç kez reddedildiyse sistem bunu tekrar zorlamaz
- Aynı tip öğrenmeler sık kabul ediliyorsa confidence hafifçe artar
- Hassas sinyaller redakte edilerek tutulur; ham metin event log’a düşmez
- Onaylanan chat öğrenmesi `raw entry` olarak da kayda geçer, böylece explainability zinciri korunur

## Retrieval

Assistant tüm fact’leri prompt’a taşımaz.

`retrieve_relevant_facts(...)` şu kurallarla çalışır:

- intent tespiti yapar
- kategori seçer
- scope filtreler
- `sensitive` ve `never_use` fact’leri çıkarır
- yalnız etkin fact’leri döndürür
- explicit fact’lere ek ağırlık verir

Bu preview yüzeyi UI içinde `Kullanım Önizlemesi` bölümünden görülebilir.

## UI

Yeni sayfa:

- `/personal-model`
- `/profile-model` -> redirect

Yüzeyler:

- interview başlatma ve ilerleme
- fact listesi ve hızlı kontrol düğmeleri
- pending learning suggestion listesi
- profile summary
- retrieval preview
- raw entry feed

UI dili teknik terimlerden uzaklaştırılmıştır:

- `explicit / inferred` yerine insan dilinde durum etiketi
- `confidence` yerine yüzdeyle açıklama
- `scope` yerine kullanım alanı açıklaması
- her kayıt için `neden biliyorum` ve `nasıl kullanırım` özeti
- retrieval preview artık varsa canonical `claim_summary_lines` üretir; düz summary satırları yalnız fallback olarak kalır

## API

- `GET /assistant/personal-model`
- `POST /assistant/personal-model/interviews/start`
- `POST /assistant/personal-model/interviews/{session_id}/answer`
- `POST /assistant/personal-model/interviews/{session_id}/pause`
- `POST /assistant/personal-model/interviews/{session_id}/resume`
- `POST /assistant/personal-model/interviews/{session_id}/skip`
- `GET /assistant/personal-model/facts`
- `PUT /assistant/personal-model/facts/{fact_id}`
- `DELETE /assistant/personal-model/facts/{fact_id}`
- `POST /assistant/personal-model/suggestions/{suggestion_id}/review`
- `POST /assistant/personal-model/retrieval/preview`

## Güvenlik kuralları

- Hassas fact otomatik prompt’a girmez
- Hassas suggestion kanıtı redakte edilir
- `never_use=true` fact hiçbir cevapta kullanılmaz
- `explicit` ve `inferred` ayrı tutulur
- Chatten çıkan sinyal kullanıcı onayı olmadan kalıcı fact olmaz

## Testler

Backend:

- `apps/api/tests/test_personal_model.py`

UI:

- `apps/ui/src/pages/PersonalModelPage.test.tsx`

## Bilinen sınır

Bu katman mevcut knowledge base’in yerine geçmez. KB, wiki-merkezli geniş hafıza sistemi olarak kalır. `Personal Model`, onun yanında çalışan, daha sıkı izin kontrollü ve daha dar kapsamlı kullanıcı-anlama katmanıdır.
