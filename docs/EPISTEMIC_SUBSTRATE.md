# Epistemic Substrate

LawCopilot artik farkli truth katmanlarini birbirine karistirmamak icin ortak bir epistemic substrate kullanir.

## Temel model

Sistem uc ayri katmana dayanir:

- `Artifact`
  Immutable ham kayit. Ornek: interview cevabi, chat sinyali, assistant output, connector girdisi.
- `Claim`
  Belirli bir ozne/predicate/scope icin yapilan atomik iddia. Ornek: `user -> communication.style -> Kisa ve net`.
- `Resolution`
  Aynı `subject + predicate + scope` icin aktif claim setinden bugun hangi bilginin gecerli sayildigini hesaplayan cozum.

## Neden eklendi

Uzun vadeli risk, compiled wiki ve assistant-generated narrative kayitlarin "kanaat" yerine "gercek" gibi davranmasiydi.

Bu substrate ile:

- assistant output artik otomatik truth sayilmaz
- explicit user statements inferred claim'lerden ustun gelir
- Personal Model ayri bir truth engine degil, ayni substrate'in izinli alt gorunumu olur
- file-back contamination riski dusurulur

## Mevcut precedence

Claim resolver artik tek bir global siraya degil, declarative predicate-family tablosuna bakar.

Mevcut aileler:

- `user_preference`
- `contact_preference`
- `workspace_fact`
- `task_state`
- `action_outcome`
- `location_context`
- `recommendation_feedback`
- `default`

Bu tablo su kararlari aile bazli verir:

- basis agirliklari
- validation agirliklari
- contested threshold
- self-generated / preview-only / quarantined cezalar

Ornek:

- `user_preference` icin `user_explicit`, `connector_observed` veya `inferred` kayittan ustundur
- `workspace_fact` icin `connector_observed` ve `document_extracted`, assistant narrative'den ustundur
- `task_state` icin connector status ve event state bilgisi inferred narrative'den ustundur

Resolver sonucunda claim su durumlardan birini alir:

- `current`
- `contested`
- `contaminated`
- `unknown`

Kaynak modül:

- `apps/api/lawcopilot_api/epistemic/precedence.py`

## Personal Model entegrasyonu

Guided interview ve consent-based chat learning sonucunda kaydedilen fact'ler artik:

1. `personal_model_raw_entries` tablosuna ham entry olarak yazilir
2. `personal_model_facts` tablosuna normalized fact olarak yazilir
3. ayni anda `epistemic_artifacts` ve `epistemic_claims` tablolarina da kaydedilir

Boylece kullanici modeli tek basina ayri truth store degil, ortak claim substrate ustunde calisir.

## KB/Profile promotion

Ilk promotion kurallari su an su kaynaklari kapsar:

- `Personal Model` explicit interview cevaplari
- `Personal Model` user-confirmed chat learning kayitlari
- `user_preferences` raw ingest sinyalleri
- `sync_from_store()` sirasinda gelen explicit profile alanlari
- `related_profiles` icindeki kisi iliski / tercih notlari
- guvenli `connector_observed` claim hint'leri

## Connector claim hints

Generic connector metnini dogrudan truth'e cevirmiyoruz.

Bunun yerine connector katmani artik istege bagli `epistemic_claim_hints` tasiyabiliyor. Bu hint'ler:

- atomic subject / predicate / value iddialari verir
- basis olarak `connector_observed` veya `document_extracted` sinifi kullanir
- retrieval ve sensitivity kurallarini acikca tasir
- generic contact/place summary gibi riskli otomatik truth promotion'i yerine gecer

Bugun guvenli hint coverage olan alanlar:

- email/message thread reply-needed sinyalleri
- calendar event status / location / preparation-needed
- task status / priority
- matter note `note_type`
- location profile current_place / home_base / location_preferences
- browser context ve external consumer signal'lari icin short-lived recent activity claim'leri
  - `query`
  - `topic_title`
  - `category`
  - `url_host`

Bu sayede connector breadth artisinda truth modeli gevsemez; yeni connector ancak acik claim contract'i ile canonical substrate'e girer.

Bu sayede yalniz Personal Model degil, explicit profil kayitlari da resolver tarafinda ortak sekilde cozulebilir.

## Assistant output quarantine

Assistant file-back kayitlari tutulur ama default olarak canonical retrieval objesi sayilmaz.

Kurallar:

- assistant output `artifact` olarak kaydedilir
- ayni anda `assistant_generated` basis ile claim uretilir
- bu claim `quarantined` retrieval eligibility ile isaretlenir
- generic KB search bu kayitlari default olarak disarida birakir
- explainability confidence bu kayitlari tek basina dayanak saymaz

Bu sayede sistem kendi urettigi anlatilari kendi gercegi gibi geri cagirmamaya calisir.

## Contamination firewall

Resolver artik yalniz basis/validation siralamasi yapmaz; destek zincirini de inceler.

Bakilan ana sinyaller:

- `supporting_claim_ids`
- `source_claim_ids`
- `derived_from_claim_ids`
- self-generated / quarantined lineage
- cycle detection

Bir claim su durumlarda `contaminated` sayilir:

- destek zincirinde cycle varsa
- claim dogrudan assistant-generated ise ve harici dayanak yoksa
- destek zinciri yalniz assistant-generated kayitlardan olusuyorsa
- claim kirli bir destek zincirine bagliysa ve harici dayanak yoksa

Bu durumda:

- resolver status `contaminated` doner
- claim ranking agir ceza alir
- Memory Explorer dayanak gorunumunde uyarı olarak gorunur
- health panel bu claim'i epistemik risk olarak listeler

## Retrieval gating

Search ve context assembly artik resolver sonucunu da dikkate alir.

Temel kurallar:

- `blocked` ve `quarantined` claim'lere bagli kayitlar default retrieval havuzuna girmez
- `contaminated` support chain tasiyan kayitlar default retrieval havuzundan cikarilir
- `grounded` ve `supported` claim'ler ranking tarafinda bonus alir
- `contested` ve `weak` dayanakli kayitlar ceza alir

Context assembly de artik yalniz record summary tasimaz. Mümkün oldugunda:

- resolver'dan gelen current claim secilir
- `grounded` / `supported` claim'ler icin claim-backed summary line uretilir
- prompt'a giden baglamda narrative yerine canonical ifade kullanilir

Boylece retrieval yalniz lexical benzerlige degil, epistemic kaliteye de bakar.

## Retrieval pipeline abstraction

Retrieval secimi artik service constructor icindeki if/else yerine factory arkasinda yapilir.

Kaynak modül:

- `apps/api/lawcopilot_api/knowledge_base/retrieval_factory.py`

Bu katman bugun su bilgiyi merkezileştirir:

- hangi backend secildi
- pipeline adi
- dense candidate generation acik mi
- hangi local reranker modu hedefleniyor
- vector / reranker hook readiness

Su an semantic kaliteyi tamamen degistiren agir bir external backend eklenmedi; ama dense candidate generation ve local reranker icin config + abstraction yolu artik calisan bir pipeline halinde acik.

Varsayilan retrieval sirasi:

- FTS candidate generation
- optional dense candidate union
- local reranker
- epistemic + lifecycle aware final scoring

Varsayilan semantic backend hala heuristic projection'dir. Ek olarak opsiyonel `model_local` modu eklendi:

- `LAWCOPILOT_PERSONAL_KB_SEMANTIC_BACKEND=model_local`
- `LAWCOPILOT_PERSONAL_KB_EMBEDDING_MODEL_NAME=...`
- `LAWCOPILOT_PERSONAL_KB_RERANKER_MODE=model_cross_encoder`
- `LAWCOPILOT_PERSONAL_KB_CROSS_ENCODER_MODEL_NAME=...`

Bu modda `sentence-transformers` kuruluysa:

- dense semantic scores local embedding modeliyle uretilir
- rerank step local cross-encoder ile calisir
- yoksa sistem sessizce heuristic fallback'e doner

Bu sayede lexical temel korunurken semantic eslesme ve claim kalitesi ayni secim zincirine girebilir.

## Memory Explorer claim bindings

Memory Explorer wiki sayfalari ve concept article'lar artik hem record-level `claim_bindings`, hem de compiled narrative icin `article_claim_bindings` expose eder.

Bu yuzeyle kullanici:

- bir sayfanin hangi record -> claim baglariyla derlendigini gorebilir
- narrative metindeki ozet/paragraf anchor'larinin hangi claim'lerden geldigini gorebilir
- claim status / basis / retrieval eligibility / support quality ozetini gorur
- support/source/derived claim referanslarini inceleyebilir
- graph gorunumunde `record -> claim -> subject` zincirini gorebilir

Ayrica wiki page ve concept detail ekranlari diskteki eski markdown'a degil, o anki state'ten uretilen current compiled view'a bakar.
Bu sayede stale export dosyasi olsa bile UI en guncel claim baglarini gosterir.

Span binding tarafinda explicit sentence node olusturulmadi. Bunun yerine compiler span-annotation + section/paragraph anchoring kullaniliyor.
Bu, graph'i sisirmeden explainability veren varsayilan yon.

Personal Model retrieval'i de ayni kurala baglidir: prompt'a giden kişisel bağlam, varsa `claim_summary_lines` üzerinden canonical claim ifadelerini once kullanir; duz summary satirlari yalniz fallback olarak kalir.

## Su anki sinirlar

Bu ilk sertlestirme adimidir. Hala yapilacaklar:

- daha zengin predicate-level precedence policy
- daha genis connector claim hint coverage
- resolution status'un daha fazla UI surface'a tasinmasi
- policy engine ile daha siki retrieval/execution gating
- tam sentence-level compiled wiki -> claim binding
- dense retrieval + local reranker'in feature-flag altinda gercek entegrasyonu
- eval harness'in release gate olarak daha da zenginlestirilmesi
