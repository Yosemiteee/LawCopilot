export function dagitimKipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "local-only":
      return "Yalnız yerel";
    case "local-first-hybrid":
      return "Yerel öncelikli hibrit";
    case "cloud-assisted":
      return "Bulut destekli";
    default:
      return value || "Belirsiz";
  }
}

export function modelProfilEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "local":
      return "Yerel";
    case "hybrid":
      return "Hibrit";
    case "cloud":
      return "Bulut";
    default:
      return value || "Belirsiz";
  }
}

export function saglayiciTuruEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "openai-codex":
      return "OpenAI hesabı (Codex)";
    case "openai":
      return "OpenAI API";
    case "openai-compatible":
      return "OpenAI uyumlu sağlayıcı";
    case "ollama":
      return "Yerel Ollama";
    default:
      return value || "Belirsiz";
  }
}

export function surumKanaliEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "pilot":
      return "Pilot";
    case "stable":
      return "Kararlı";
    case "nightly":
      return "Gece sürümü";
    default:
      return value || "Belirsiz";
  }
}

export function ortamEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "pilot":
      return "Pilot ortamı";
    case "production":
      return "Üretim ortamı";
    case "development":
      return "Geliştirme ortamı";
    default:
      return value || "Belirsiz";
  }
}

export function masaustuKabukEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "electron":
      return "Electron";
    case "tauri":
      return "Tauri";
    default:
      return value || "Belirsiz";
  }
}

export function oncelikEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "high":
      return "Yüksek";
    case "medium":
      return "Orta";
    case "low":
      return "Düşük";
    default:
      return value || "Belirsiz";
  }
}

export function dosyaDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "active":
      return "Açık";
    case "on_hold":
      return "Beklemede";
    case "closed":
      return "Kapalı";
    default:
      return value || "Belirsiz";
  }
}

export function gorevDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "open":
      return "Açık";
    case "in_progress":
      return "Devam ediyor";
    case "completed":
      return "Tamamlandı";
    default:
      return value || "Belirsiz";
  }
}

export function sistemKaynagiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "openclaw_runtime+rag":
      return "Codex destekli genel arama";
    case "direct_provider+rag":
      return "Doğrudan sağlayıcı ile genel arama";
    case "openclaw_runtime+matter_document_memory":
      return "Codex destekli dosya araması";
    case "direct_provider+matter_document_memory":
      return "Doğrudan sağlayıcı ile dosya araması";
    case "direct_provider+assistant_actions":
      return "Doğrudan sağlayıcı ile taslak aksiyon";
    case "direct_provider+assistant_thread":
      return "Doğrudan sağlayıcı ile asistan yanıtı";
    case "openclaw_runtime+matter_workflow_engine":
      return "Codex destekli iş akışı";
    case "direct_provider+matter_workflow_engine":
      return "Doğrudan sağlayıcı ile iş akışı";
    case "openclaw_runtime+workspace_document_memory":
      return "Codex destekli çalışma alanı araması";
    case "direct_provider+workspace_document_memory":
      return "Doğrudan sağlayıcı ile çalışma alanı araması";
    case "openclaw_runtime+workspace_similarity":
      return "Codex destekli benzerlik";
    case "direct_provider+workspace_similarity":
      return "Doğrudan sağlayıcı ile benzerlik";
    case "workflow_engine":
      return "İş akışı motoru";
    case "matter_record":
      return "Dosya kaydı";
    case "matter_record_and_counts":
      return "Dosya kaydı ve sayımlar";
    case "matter_documents_notes_tasks":
      return "Belge, not ve görev akışı";
    case "matter_workflow_engine":
      return "Dosya iş akışı motoru";
    case "matter_activity_stream":
      return "Dosya hareket akışı";
    case "matter_document_memory":
      return "Dosya belge hafızası";
    default:
      return value || "Belirsiz";
  }
}

export function uretimDurumuEtiketi(value?: string | null) {
  if ((value || "").toLowerCase().includes("openclaw_runtime")) {
    return "Codex ile üretildi";
  }
  if ((value || "").toLowerCase().includes("direct_provider")) {
    return "Doğrudan sağlayıcı ile üretildi";
  }
  if (value) {
    return "Yerleşik fallback";
  }
  return "Belirsiz";
}

export function runtimeDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "codex":
    case "openclaw_runtime_used":
      return "Codex etkin";
    case "fallback":
    case "openclaw_runtime_fallback":
      return "Fallback kullanıldı";
    case "direct-provider":
    case "direct_provider_runtime_used":
      return "Doğrudan sağlayıcı etkin";
    case "direct-fallback":
    case "direct_provider_runtime_fallback":
      return "Sağlayıcı fallback";
    default:
      return "Henüz çağrı yok";
  }
}

export function olayTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "matter_created":
      return "Dosya oluşturuldu";
    case "note_added":
      return "Not eklendi";
    case "draft_created":
      return "Taslak oluşturuldu";
    case "draft_generated":
      return "Taslak üretildi";
    case "document_registered":
      return "Belge kaydedildi";
    case "document_indexed":
      return "Belge indekslendi";
    case "document_ingest_failed":
      return "Belge işleme hatası";
    case "task_status_updated":
      return "Görev durumu değişti";
    case "task_due_updated":
      return "Görev tarihi değişti";
    case "task_completed":
      return "Görev tamamlandı";
    case "workspace_document_attached":
    case "workspace_document_attached_to_matter":
      return "Çalışma alanı belgesi bağlandı";
    default:
      return value || "Belirsiz";
  }
}

export function hareketTuruEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "timeline":
      return "Zaman çizelgesi";
    case "note":
      return "Not";
    case "draft_event":
      return "Taslak olayı";
    case "ingestion":
      return "İçe aktarma";
    default:
      return value || "Belirsiz";
  }
}

export function belgeDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "queued":
      return "Sırada";
    case "processing":
      return "İşleniyor";
    case "indexed":
      return "İndekslendi";
    case "completed":
      return "Tamamlandı";
    case "parsed":
      return "Ayrıştırıldı";
    case "failed":
      return "Başarısız";
    case "missing":
      return "Kayıp";
    case "inactive":
      return "Pasif";
    case "active":
      return "Aktif";
    default:
      return value || "Belirsiz";
  }
}

export function destekSeviyesiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "high":
    case "yuksek":
      return "Yüksek dayanak";
    case "medium":
    case "orta":
      return "Orta dayanak";
    case "low":
    case "dusuk":
      return "Düşük dayanak";
    default:
      return value || "Belirsiz";
  }
}

export function guvenEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "high":
      return "Yüksek güven";
    case "medium":
      return "Orta güven";
    case "low":
      return "Düşük güven";
    default:
      return value || "Belirsiz";
  }
}

export function kaynakTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "upload":
      return "Yükleme";
    case "email":
      return "E-posta";
    case "portal":
      return "Portal";
    case "internal_note":
      return "İç not";
    case "workspace":
      return "Çalışma alanı";
    default:
      return value || "Belirsiz";
  }
}

export function taslakTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "client_update":
      return "Müvekkil durum güncellemesi";
    case "internal_summary":
      return "İç ekip özeti";
    case "first_case_assessment":
    case "intake_summary":
      return "İlk dosya değerlendirmesi";
    case "missing_document_request":
      return "Belge talep listesi";
    case "meeting_summary":
    case "meeting_recap":
      return "Toplantı özeti";
    case "question_list":
      return "Soru listesi";
    case "general":
      return "Genel taslak";
    default:
      return value || "Belirsiz";
  }
}

export function kanalEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "internal":
      return "İç kullanım";
    case "email":
      return "E-posta";
    case "telegram":
      return "Telegram";
    case "client_portal":
      return "Müvekkil portalı";
    default:
      return value || "Belirsiz";
  }
}

export function ajandaTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "overdue_task":
      return "Geciken iş";
    case "due_today":
      return "Bugün";
    case "reply_needed":
      return "Yanıt bekliyor";
    case "calendar_prep":
      return "Takvim hazırlığı";
    case "personal_date":
      return "Önemli tarih";
    default:
      return value || "Ajanda";
  }
}

export function asistanAksiyonTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "prepare_client_update":
      return "Müvekkil güncellemesi";
    case "prepare_internal_summary":
      return "İç ekip özeti";
    case "send_email":
      return "E-posta hazırla";
    case "reply_email":
      return "E-posta yanıtı";
    case "send_telegram_message":
      return "Telegram yanıtı";
    case "create_task":
      return "Görev önerisi";
    default:
      return value || "Aksiyon";
  }
}

export function asistanAksiyonDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "suggested":
      return "Önerildi";
    case "pending_review":
      return "İnceleme bekliyor";
    case "approved":
      return "Onaylandı";
    case "dismissed":
      return "Kapatıldı";
    default:
      return value || "Belirsiz";
  }
}

export function disIletisimDurumuEtiketi(approvalStatus?: string | null, deliveryStatus?: string | null) {
  if ((deliveryStatus || "").toLowerCase() === "sent") {
    return "Gönderildi";
  }
  if ((deliveryStatus || "").toLowerCase() === "ready_to_send") {
    return "Gönderime hazır";
  }
  if ((deliveryStatus || "").toLowerCase() === "manual_review_only") {
    return "Manuel inceleme";
  }
  if ((approvalStatus || "").toLowerCase() === "approved") {
    return "Onaylandı";
  }
  if ((approvalStatus || "").toLowerCase() === "dismissed") {
    return "İptal edildi";
  }
  return "Onay bekliyor";
}

export function gerceklikEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "factual":
      return "Olgusal";
    case "inferred":
      return "Çıkarımsal";
    default:
      return value || "Belirsiz";
  }
}

export function belirsizlikEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "none":
      return "Net";
    case "approximate":
      return "Yaklaşık";
    case "conflicting_date":
      return "Tarih çelişkisi";
    default:
      return value || "Belirsiz";
  }
}

export function riskKategoriEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "missing_document":
      return "Eksik belge";
    case "conflicting_information":
      return "Çelişkili bilgi";
    case "follow_up_date":
      return "Tarih takibi";
    case "deadline_watch":
      return "Süre takibi";
    case "verify_claim":
      return "Doğrulanacak iddia";
    default:
      return value || "Belirsiz";
  }
}

export function baglayiciDurumuEtiketi(value: boolean) {
  return value ? "Kuru çalışma" : "Canlı";
}

export function kisaDosyaBoyutu(value: number) {
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (value >= 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${value} B`;
}

export function notTipiEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "working_note":
      return "Çalışma notu";
    case "client_note":
      return "Müvekkil notu";
    case "internal_note":
      return "İç not";
    case "risk_note":
      return "Risk notu";
    default:
      return value || "Belirsiz";
  }
}

export function epostaTaslakDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "draft":
      return "Taslak";
    case "approved":
      return "Onaylandı";
    case "retracted":
      return "Geri çekildi";
    case "sent":
      return "Gönderildi";
    default:
      return value || "Belirsiz";
  }
}

export function sosyalMedyaKaynakEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "x":
      return "X (Twitter)";
    case "linkedin":
      return "LinkedIn";
    case "instagram":
      return "Instagram";
    case "news":
      return "Haber";
    default:
      return value || "Belirsiz";
  }
}

export function riskSkoruEtiketi(score: number): { label: string; tone: "accent" | "warning" | "danger" } {
  if (score >= 0.7) return { label: "Yüksek risk", tone: "danger" };
  if (score >= 0.4) return { label: "Orta risk", tone: "warning" };
  return { label: "Düşük risk", tone: "accent" };
}

export function atifKaliteEtiketi(grade?: string | null) {
  switch ((grade || "").toUpperCase()) {
    case "A":
      return "Güçlü kaynak";
    case "B":
      return "Yeterli kaynak";
    case "C":
      return "Zayıf kaynak";
    default:
      return grade || "Belirsiz";
  }
}

export function sorguIsleviDurumuEtiketi(value?: string | null) {
  switch ((value || "").toLowerCase()) {
    case "pending":
      return "Bekliyor";
    case "running":
      return "Çalışıyor";
    case "completed":
      return "Tamamlandı";
    case "failed":
      return "Başarısız";
    case "cancelled":
      return "İptal edildi";
    default:
      return value || "Belirsiz";
  }
}
