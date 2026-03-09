from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any


DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4})\b"),
]
DATE_EVENT_HINTS = {
    "duruşma",
    "durusma",
    "hearing",
    "ihtar",
    "deadline",
    "son tarih",
    "ödeme",
    "odeme",
    "teslim",
    "toplantı",
    "toplanti",
    "görüşme",
    "gorusme",
    "başvuru",
    "basvuru",
    "itiraz",
    "fesih",
    "tahliye",
    "inceleme",
}
UNCERTAIN_HINTS = {"tahmini", "muhtemel", "olabilir", "yaklaşık", "yaklasik", "beklenen", "expected"}
CLAIM_HINTS = {"iddia", "öne sür", "one sur", "belirtiyor", "beyan", "alleged", "savunuyor"}
MISSING_DOC_HINTS = {"eksik", "missing", "beklen", "temin", "sunulacak", "toplanacak", "henüz", "henuz"}
STOP_WORDS = {
    "ve",
    "ile",
    "icin",
    "this",
    "that",
    "dosya",
    "matter",
    "note",
    "document",
    "belge",
    "tarihli",
    "mahkeme",
    "muvekkil",
    "müvekkil",
    "oldu",
    "olacak",
    "olustu",
    "olusturuldu",
}
WORD_RE = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]{2,}")


def _to_iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
    except ValueError:
        return None


def _excerpt(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].strip().split())


def _normalized_signature(text: str) -> str:
    cleaned = re.sub(r"\b\d{2}[./]\d{2}[./]\d{4}\b", " ", text.lower())
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", cleaned)
    tokens = [token for token in WORD_RE.findall(cleaned) if token not in STOP_WORDS]
    return " ".join(tokens[:6])


def _human_label(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def extract_date_mentions(text: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups[0]) == 4:
                iso_date = _to_iso_date(int(groups[0]), int(groups[1]), int(groups[2]))
            else:
                iso_date = _to_iso_date(int(groups[2]), int(groups[1]), int(groups[0]))
            if not iso_date:
                continue
            snippet = _excerpt(text, match.start(), match.end())
            lower = snippet.lower()
            mentions.append(
                {
                    "date": iso_date,
                    "raw": match.group(0),
                    "snippet": snippet,
                    "signature": _normalized_signature(snippet),
                    "factuality": "inferred" if any(word in lower for word in UNCERTAIN_HINTS) else "factual",
                    "confidence": "medium" if any(word in lower for word in UNCERTAIN_HINTS) else "high",
                }
            )
    mentions.sort(key=lambda item: (item["date"], item["raw"]))
    return mentions


def build_chronology(
    *,
    matter: dict[str, Any],
    notes: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    if matter.get("opened_at"):
        items.append(
            {
                "id": f"matter-opened-{matter['id']}",
                "date": str(matter["opened_at"])[:10],
                "event": f"{matter['title']} dosyası açıldı",
                "source_kind": "matter",
                "source_id": matter["id"],
                "source_label": matter["title"],
                "factuality": "factual",
                "uncertainty": "none",
                "confidence": "high",
                "signals": ["matter_metadata"],
                "citation": None,
            }
        )

    for note in notes:
        body = str(note.get("body") or "")
        mentions = extract_date_mentions(body)
        if mentions:
            for idx, mention in enumerate(mentions, start=1):
                items.append(
                    {
                        "id": f"note-{note['id']}-{idx}",
                        "date": mention["date"],
                        "event": mention["snippet"],
                        "source_kind": "note",
                        "source_id": note["id"],
                        "source_label": f"{_human_label(str(note.get('note_type') or 'note'))} #{note['id']}",
                        "factuality": mention["factuality"],
                        "uncertainty": "none" if mention["factuality"] == "factual" else "approximate",
                        "confidence": mention["confidence"],
                        "signals": ["matter_note", mention["raw"]],
                        "citation": None,
                    }
                )
        elif any(hint in body.lower() for hint in DATE_EVENT_HINTS):
            issues.append(
                {
                    "type": "missing_date",
                    "severity": "medium",
                    "title": "Zaman çizelgesine giren notta açık tarih yok",
                    "details": body[:240],
                    "source_labels": [f"Not #{note['id']}"],
                }
            )

    for chunk in chunks:
        text = str(chunk.get("text") or "")
        mentions = extract_date_mentions(text)
        meta = chunk.get("metadata") or {}
        citation = {
            "document_id": chunk.get("document_id"),
            "document_name": chunk.get("display_name") or chunk.get("filename"),
            "matter_id": chunk.get("matter_id"),
            "chunk_id": chunk.get("id"),
            "chunk_index": chunk.get("chunk_index"),
            "excerpt": text[:320],
            "relevance_score": 1.0,
            "source_type": chunk.get("source_type") or meta.get("source_type") or "upload",
            "support_type": "document_backed",
            "confidence": "high",
            "line_anchor": meta.get("line_anchor"),
            "page": meta.get("page"),
            "line_start": meta.get("line_start"),
            "line_end": meta.get("line_end"),
        }
        if mentions:
            for idx, mention in enumerate(mentions, start=1):
                items.append(
                    {
                        "id": f"chunk-{chunk['id']}-{idx}",
                        "date": mention["date"],
                        "event": mention["snippet"],
                        "source_kind": "document",
                        "source_id": chunk.get("document_id"),
                        "source_label": chunk.get("display_name") or chunk.get("filename"),
                        "factuality": mention["factuality"],
                        "uncertainty": "none" if mention["factuality"] == "factual" else "approximate",
                        "confidence": mention["confidence"],
                        "signals": ["document_chunk", mention["raw"]],
                        "citation": citation,
                    }
                )
        elif any(hint in text.lower() for hint in DATE_EVENT_HINTS):
            issues.append(
                {
                    "type": "missing_date",
                    "severity": "medium",
                    "title": "Bir belge olaydan söz ediyor ancak açık tarih içermiyor",
                    "details": text[:240],
                    "source_labels": [chunk.get("display_name") or chunk.get("filename") or "Belge"],
                }
            )

    for task in tasks:
        if task.get("due_at"):
            items.append(
                {
                    "id": f"task-{task['id']}",
                    "date": str(task["due_at"])[:10],
                    "event": f"Görev vadesi: {task['title']}",
                    "source_kind": "task",
                    "source_id": task["id"],
                    "source_label": task["title"],
                    "factuality": "factual",
                    "uncertainty": "none",
                    "confidence": "high",
                    "signals": ["task_due"],
                    "citation": None,
                }
            )

    groups: dict[str, set[str]] = {}
    for item in items:
        signature = _normalized_signature(item["event"])
        if not signature:
            continue
        groups.setdefault(signature, set()).add(item["date"])

    conflicting_signatures = {signature for signature, dates in groups.items() if len(dates) > 1}
    if conflicting_signatures:
        for item in items:
            if _normalized_signature(item["event"]) in conflicting_signatures:
                item["uncertainty"] = "conflicting_date"
                item["confidence"] = "low"
                if "conflicting_dates" not in item["signals"]:
                    item["signals"].append("conflicting_dates")
        for signature in sorted(conflicting_signatures):
            related = [item for item in items if _normalized_signature(item["event"]) == signature]
            issues.append(
                {
                    "type": "conflicting_date",
                    "severity": "high",
                    "title": "Çelişkili tarihler bulundu",
                    "details": "Birden fazla kayıt aynı olayı farklı tarihlerle anlatıyor görünüyor.",
                    "source_labels": [item["source_label"] for item in related[:4]],
                }
            )

    items.sort(key=lambda item: (item["date"], item["factuality"] != "factual", item["source_label"]))
    return {
        "matter_id": matter["id"],
        "items": items,
        "issues": issues,
        "generated_from": "matter_documents_notes_tasks",
        "manual_review_required": bool(issues) or any(item["factuality"] == "inferred" for item in items),
    }


def build_risk_notes(
    *,
    matter: dict[str, Any],
    documents: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    chronology: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).date()
    items: list[dict[str, Any]] = []

    def add_item(category: str, title: str, details: str, severity: str, signals: list[str], source_labels: list[str]) -> None:
        if any(existing["title"] == title for existing in items):
            return
        items.append(
            {
                "category": category,
                "title": title,
                "details": details,
                "severity": severity,
                "manual_review_required": True,
                "signals": signals,
                "source_labels": source_labels,
            }
        )

    if not documents:
        add_item(
            "missing_document",
            "İndekslenmiş dosya belgesi bulunmuyor",
            "Bu dosyada henüz indekslenmiş kaynak belge yok. Kaynak malzeme eklenene kadar arama ve kronoloji çıktıları zayıf kalacaktır.",
            "high",
            ["no_documents"],
            [matter["title"]],
        )

    for issue in chronology.get("issues", []):
        if issue.get("type") == "conflicting_date":
            add_item(
                "conflicting_information",
                "Çelişkili kronoloji tarihleri doğrulanmalı",
                issue.get("details") or "Aynı olay, dosya kayıtlarında farklı tarihlerle görünüyor.",
                "high",
                ["chronology_conflict"],
                issue.get("source_labels", []),
            )
        elif issue.get("type") == "missing_date":
            add_item(
                "follow_up_date",
                "Bir olay açık tarih olmadan anılıyor",
                issue.get("details") or "Zaman çizelgesine girmesi gereken bir olay açık tarih olmadan geçiyor.",
                "medium",
                ["missing_event_date"],
                issue.get("source_labels", []),
            )

    for task in tasks:
        if not task.get("due_at") or task.get("status") == "completed":
            continue
        try:
            due_date = datetime.fromisoformat(str(task["due_at"]).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        days = (due_date - now).days
        if days <= 7:
            add_item(
                "deadline_watch",
                "Bir görev vadesi yaklaşıyor",
                f"'{task['title']}' görevinin vadesi {due_date.isoformat()} tarihinde doluyor. Sorumluyu ve dayanak belgeleri teyit edin.",
                "high" if days <= 3 else "medium",
                ["task_due_soon", f"days_until_due:{days}"],
                [task["title"]],
            )

    for note in notes:
        lower = str(note.get("body") or "").lower()
        if any(term in lower for term in MISSING_DOC_HINTS):
            add_item(
                "missing_document",
                "Bir not eksik dayanak belgeye işaret ediyor",
                str(note.get("body") or "")[:240],
                "medium",
                ["missing_document_signal", f"note:{note['id']}"],
                [f"Not #{note['id']}"],
            )
        if any(term in lower for term in CLAIM_HINTS):
            add_item(
                "verify_claim",
                "Bir iddia kaynak belgeyle doğrulanmalı",
                str(note.get("body") or "")[:240],
                "medium",
                ["claim_language_detected", f"note:{note['id']}"],
                [f"Not #{note['id']}"],
            )

    for chunk in chunks:
        text = str(chunk.get("text") or "")
        lower = text.lower()
        source_label = chunk.get("display_name") or chunk.get("filename") or "Belge"
        if any(term in lower for term in MISSING_DOC_HINTS):
            add_item(
                "missing_document",
                "Belge metni eksik delil veya bekleyen evraka işaret ediyor",
                text[:240],
                "medium",
                ["missing_document_signal", f"document:{chunk.get('document_id')}"],
                [source_label],
            )
        if any(term in lower for term in CLAIM_HINTS):
            add_item(
                "verify_claim",
                "Belgede incelemede doğrulanması gereken bir ifade var",
                text[:240],
                "medium",
                ["claim_language_detected", f"document:{chunk.get('document_id')}"],
                [source_label],
            )

    return {
        "matter_id": matter["id"],
        "label": "working_notes",
        "manual_review_required": True,
        "items": items,
        "generated_from": "matter_workflow_engine",
    }


def build_task_recommendations(
    *,
    matter: dict[str, Any],
    chronology: dict[str, Any],
    risk_notes: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_titles = {str(task.get("title") or "").lower() for task in tasks}
    recommendations: list[dict[str, Any]] = []

    def add_rec(title: str, priority: str, explanation: str, signals: list[str], due_at: str | None = None) -> None:
        if title.lower() in existing_titles or any(item["title"] == title for item in recommendations):
            return
        recommendations.append(
            {
                "title": title,
                "priority": priority,
                "due_at": due_at,
                "recommended_by": "workflow_engine",
                "origin_type": "timeline",
                "manual_review_required": True,
                "signals": signals,
                "explanation": explanation,
            }
        )

    for note in risk_notes.get("items", []):
        category = str(note.get("category") or "")
        if category == "missing_document":
            add_rec(
                "Eksik dayanak belgeleri gözden geçir ve talep et",
                "high",
                "Dosya notları veya belge metni eksik ya da bekleyen dayanak malzemeye işaret ettiği için önerildi. Herhangi bir iletişimden önce insan incelemesi gerekir.",
                list(note.get("signals") or []) + ["source:missing_document"],
            )
        if category == "conflicting_information":
            add_rec(
                "Çelişkili kronoloji tarihlerini netleştir",
                "high",
                "Birden fazla kaynak aynı olayı farklı tarihlerle anlattığı için önerildi. Bu zaman çizelgesine güvenmeden önce yetkili tarihi doğrulayın.",
                list(note.get("signals") or []) + ["source:chronology_conflict"],
            )
        if category == "deadline_watch":
            add_rec(
                "Yaklaşan vadeyi gözden geçir ve sorumluyu doğrula",
                "high",
                "Dosyaya bağlı bir görevin vadesi yaklaştığı için önerildi. Hazırlık durumunu ve dayanak delilleri doğrulayın.",
                list(note.get("signals") or []) + ["source:deadline_watch"],
            )
        if category == "verify_claim":
            add_rec(
                "Dayanaksız veya çekişmeli ifadeleri doğrula",
                "medium",
                "Dosya kayıtlarında iddia niteliğinde ifadeler bulunduğu için önerildi. Bu ifadeyi taslakta veya başvuruda yeniden kullanmadan önce kaynağa bağlayın.",
                list(note.get("signals") or []) + ["source:verify_claim"],
            )

    now = datetime.now(timezone.utc).date()
    for item in chronology.get("items", []):
        if item.get("factuality") != "factual":
            continue
        try:
            event_date = datetime.fromisoformat(str(item["date"])).date()
        except ValueError:
            continue
        days = (event_date - now).days
        if 0 <= days <= 14:
            add_rec(
                f"{item['source_label']} için hazırlık incelemesi yap",
                "medium" if days > 3 else "high",
                f"Kronoloji {item['date']} tarihinde yaklaşan bir olay gösterdiği için önerildi. Atıf yapılan malzemeyi inceleyin ve sonraki adımı doğrulayın.",
                list(item.get("signals") or []) + [f"days_until_event:{days}"],
                due_at=item["date"],
            )

    return {
        "matter_id": matter["id"],
        "manual_review_required": True,
        "generated_from": "matter_workflow_engine",
        "items": recommendations,
    }


def generate_matter_draft(
    *,
    matter: dict[str, Any],
    draft_type: str,
    chronology: dict[str, Any],
    risk_notes: dict[str, Any],
    documents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    target_channel: str,
    to_contact: str | None,
    instructions: str | None = None,
) -> dict[str, Any]:
    chronology_lines = [
        f"- {item['date']}: {item['event']}"
        for item in chronology.get("items", [])
        if item.get("factuality") == "factual"
    ][:3]
    risk_lines = [f"- {item['title']}: {item['details']}" for item in risk_notes.get("items", [])][:3]
    document_lines = [f"- {doc['display_name']} ({doc['source_type']})" for doc in documents[:4]]
    open_task_lines = [f"- {task['title']}" for task in tasks if task.get("status") != "completed"][:3]

    context_summary = [
        f"Dosya: {matter['title']}",
        f"Durum: {matter.get('status', 'active')}",
        f"Müvekkil: {matter.get('client_name') or 'Belirtilmedi'}",
    ]
    if matter.get("summary"):
        context_summary.append(f"Kayıtlı özet: {matter['summary']}")

    instructions_line = f"\nİnceleyen notu: {instructions}" if instructions else ""

    templates = {
        "client_update": (
            f"Müvekkil durum güncellemesi: {matter['title']}",
            "Müvekkile dönük çalışma taslağı",
            "Dosyanın mevcut durumu",
            "Müvekkile iletilebilecek sonraki başlıklar",
        ),
        "internal_summary": (
            f"İç ekip özeti: {matter['title']}",
            "İç ekip özet taslağı",
            "Bilinen olgusal çerçeve",
            "İç takip başlıkları",
        ),
        "first_case_assessment": (
            f"İlk dosya değerlendirmesi: {matter['title']}",
            "İlk dosya değerlendirme taslağı",
            "Ön olgusal çerçeve",
            "İlk hukuki çalışma takip başlıkları",
        ),
        "missing_document_request": (
            f"Belge talep listesi: {matter['title']}",
            "Dayanak belge talep taslağı",
            "Hâlâ net olmayan belge ve tarihler",
            "Önerilen talep kontrol listesi",
        ),
        "meeting_summary": (
            f"Toplantı özeti: {matter['title']}",
            "Toplantı özet taslağı",
            "Görüşülen temel olgular",
            "Toplantı sonrası takip başlıkları",
        ),
        "meeting_recap": (
            f"Toplantı özeti: {matter['title']}",
            "Toplantı özet taslağı",
            "Görüşülen temel olgular",
            "Toplantı sonrası takip başlıkları",
        ),
        "question_list": (
            f"Soru listesi: {matter['title']}",
            "Soru listesi taslağı",
            "Hâlihazırda dayanaklanan noktalar",
            "İncelenmesi gereken sorular",
        ),
        "intake_summary": (
            f"İlk dosya değerlendirmesi: {matter['title']}",
            "İlk dosya değerlendirme taslağı",
            "Ön olgusal çerçeve",
            "İlk hukuki çalışma takip başlıkları",
        ),
    }
    title, intro, facts_heading, action_heading = templates.get(
        draft_type,
        (f"Çalışma taslağı: {matter['title']}", "Genel çalışma taslağı", "Olgusal bağlam", "Önerilen sonraki adımlar"),
    )

    body = "\n".join(
        [
            intro,
            "",
            *context_summary,
            instructions_line.strip(),
            "",
            facts_heading,
            *(chronology_lines or ["- Henüz açık bir kronoloji kaydı çıkarılamadı."]),
            "",
            "Dayanak belgeler",
            *(document_lines or ["- Henüz indekslenmiş dosya belgesi yok."]),
            "",
            "Çalışma notları / inceleme işaretleri",
            *(risk_lines or ["- Henüz workflow kaynaklı risk notu tespit edilmedi."]),
            "",
            action_heading,
            *(open_task_lines or ["- Henüz açık dosya görevi kaydedilmedi."]),
            "",
            "İnceleme notu",
            "- Bu taslak bir çalışma çıktısıdır. Yeniden kullanmadan önce tarihleri, iddiaları ve belge atıflarını doğrulayın.",
        ]
    ).strip()

    return {
        "title": title,
        "body": body,
        "target_channel": target_channel,
        "to_contact": to_contact,
        "generated_from": "matter_workflow_engine",
        "manual_review_required": True,
        "source_context": {
            "documents": document_lines,
            "chronology": chronology_lines,
            "risk_notes": risk_lines,
            "open_tasks": open_task_lines,
        },
    }


def build_activity_stream(
    *,
    matter: dict[str, Any],
    timeline: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    draft_events: list[dict[str, Any]],
    ingestion_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for event in timeline:
        items.append(
            {
                "kind": "timeline",
                "title": event.get("title") or _human_label(str(event.get("event_type") or "timeline")),
                "details": event.get("details"),
                "created_at": event.get("event_at") or event.get("created_at"),
                "actor": event.get("created_by"),
                "badge": event.get("event_type"),
                "source_ref": f"timeline:{event['id']}",
                "requires_review": event.get("event_type") in {"task_due_updated", "task_status_updated"},
            }
        )

    for note in notes:
        items.append(
            {
                "kind": "note",
                "title": f"{_human_label(str(note.get('note_type') or 'note'))} eklendi",
                "details": str(note.get("body") or "")[:240],
                "created_at": note.get("event_at") or note.get("created_at"),
                "actor": note.get("created_by"),
                "badge": note.get("note_type"),
                "source_ref": f"note:{note['id']}",
                "requires_review": note.get("note_type") == "risk_note",
            }
        )

    for event in draft_events:
        draft_title = event.get("draft_title") or f"Taslak #{event.get('draft_id')}"
        items.append(
            {
                "kind": "draft_event",
                "title": f"Taslak olayı: {draft_title}",
                "details": event.get("note") or _human_label(str(event.get("event_type") or "draft_event")),
                "created_at": event.get("created_at"),
                "actor": event.get("actor"),
                "badge": event.get("event_type"),
                "source_ref": f"draft-event:{event['id']}",
                "requires_review": True,
            }
        )

    for job in ingestion_jobs:
        document_title = job.get("document_name") or f"Belge #{job.get('document_id')}"
        items.append(
            {
                "kind": "ingestion",
                "title": f"İçe aktarma {job.get('status')}: {document_title}",
                "details": job.get("error") or "Belge ayrıştırma ve parça kaydı güncellendi.",
                "created_at": job.get("updated_at"),
                "actor": None,
                "badge": job.get("status"),
                "source_ref": f"ingestion:{job['id']}",
                "requires_review": job.get("status") == "failed",
            }
        )

    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "matter_id": matter["id"],
        "generated_from": "matter_activity_stream",
        "items": items,
    }
