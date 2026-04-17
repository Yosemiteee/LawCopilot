# Single-Writer Authority

LawCopilot local-first desktop olarak calisiyor ama SQLite WAL ve uzun yasayan runtime nedeniyle yazma otoritesi dagitilmiyor.

## Varsayilan karar

- backend process yazma otoritesidir
- worker'lar crash-isolated olabilir
- worker sonucu dogrudan domain tablosuna yazmamalidir
- worker sonucu once runtime job sonucu olarak geri doner
- gerekli domain mutasyonu backend tarafinda uygulanir

## Neden

Bu model su riskleri dusurur:

- `SQLITE_BUSY`
- WAL checkpoint starvation
- stale worker yazisi
- connector / compile / retrieval worker'larin ayni anda domain truth'e girmesi

## Ilk substrate

Bu karar artik kodda ilk omurgaya sahip:

- `runtime_jobs` tablosu
- `BackendJobQueue`
- `BackendJobProcessor`
- `WorkerJobEnvelope`
- `WorkerExecutionResult`

Kaynaklar:

- `apps/api/lawcopilot_api/persistence.py`
- `apps/api/lawcopilot_api/runtime/job_queue.py`
- `apps/api/lawcopilot_api/runtime/processor.py`
- `apps/api/lawcopilot_api/runtime/worker_protocol.py`

## Su an ne sagliyor

- backend, worker'a queue uzerinden is verir
- worker bir isi yalniz bir kez claim edebilir
- sonuc backend tarafina structured result olarak geri gelir
- `backend_apply_required` bayragi ile write-intent ayrimi tasinir
- knowledge maintenance isleri backend-owned processor uzerinden kuyruktan calisabilir
- manuel wiki compile / synthesis / reflection / orchestration isleri arka plan kuyruguna alinabilir
- telemetry health ve pilot summary runtime job ozetini gosterir
- `GET /assistant/runtime/jobs`
- `POST /assistant/runtime/jobs/process`

## Su an ne saglamiyor

Bu katman henuz tum agir isleri worker process'e tasimaz.
Su an yalniz contract ve queue substrate'i vardir.

## Worker modu

- varsayilan mod `inline` olarak kalir
- kaynak koddan calisan gelistirme/pilot ortami icin `process` modu acilabilir
- `process` modunda knowledge maintenance isleri ayri Python subprocess ile kosar
- packaged / frozen desktop runtime su an guvenli fallback olarak `inline` modda kalir
- write authority yine backend'dedir; subprocess yalniz sonucu geri dondurur

Hala yapilacaklar:

- reflection / compile / sync islerini bu queue ustune tasimak
- worker supervision / retry budget
- backend apply pipeline
- health ve pilot telemetry icinde runtime job yuzeyleri
