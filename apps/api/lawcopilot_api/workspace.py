from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .parsers import ParseError, SUPPORTED_EXTENSIONS, guess_content_type, parse_document, supported_extension
from .rag import build_persisted_chunks, score_chunk_records

WINDOWS_SYSTEM_ROOTS = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "users",
}
MAC_SYSTEM_ROOTS = {
    "applications",
    "library",
    "system",
    "users",
}
LINUX_SYSTEM_ROOTS = {
    "bin",
    "boot",
    "dev",
    "etc",
    "lib",
    "lib64",
    "opt",
    "proc",
    "root",
    "run",
    "sbin",
    "srv",
    "sys",
}
# These roots are blocked at shallow depth only (e.g. /home itself, /home/sami)
# but deeper paths like /home/sami/belgelerim are allowed.
LINUX_SHALLOW_ROOTS = {"home", "usr", "var"}


def _contains_turkish_chars(text: str) -> bool:
    return any(char in text for char in "çğıöşüÇĞİÖŞÜ")


def detect_language(text: str) -> str:
    return "tr" if _contains_turkish_chars(text) else "belirsiz"


def root_hash(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _iter_workspace_files(root_path: Path):
    for current_root, dirnames, filenames in os.walk(root_path, followlinks=False):
        current_path = Path(current_root)
        dirnames[:] = [name for name in sorted(dirnames) if not (current_path / name).is_symlink()]
        for filename in sorted(filenames):
            yield current_path / filename


def _file_checksum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_workspace_root(raw_path: str, *, platform: str | None = None) -> Path:
    if not raw_path or not raw_path.strip():
        raise ValueError("Çalışma klasörü boş olamaz.")
    candidate = Path(raw_path).expanduser()
    if not candidate.exists():
        raise ValueError("Seçilen klasör bulunamadı.")
    if not candidate.is_dir():
        raise ValueError("Seçilen yol bir klasör olmalı.")

    resolved = candidate.resolve()
    if resolved == Path.home().resolve():
        raise ValueError("Kullanıcı klasörünün tamamı seçilemez.")
    active_platform = (platform or sys_platform()).lower()

    if active_platform.startswith("win"):
        drive_root = resolved.anchor.rstrip("\\/")
        if str(resolved).rstrip("\\/") == drive_root:
            raise ValueError("Disk kökleri çalışma klasörü olarak seçilemez.")
        first = resolved.parts[1].lower() if len(resolved.parts) > 1 else ""
        if first in WINDOWS_SYSTEM_ROOTS:
            # Allow Users/username/subfolder (depth >= 4)
            if first == "users" and len(resolved.parts) >= 4:
                pass  # e.g. C:\Users\sami\Documents — allowed
            else:
                raise ValueError("Sistem klasörleri çalışma klasörü olarak seçilemez.")
        if str(resolved).startswith("\\\\"):
            raise ValueError("Ağ paylaşımları ilk sürümde desteklenmiyor.")
    elif active_platform == "darwin":
        if str(resolved) == "/":
            raise ValueError("Disk kökleri çalışma klasörü olarak seçilemez.")
        first = resolved.parts[1].lower() if len(resolved.parts) > 1 else ""
        if first in MAC_SYSTEM_ROOTS:
            # Allow /Users/username/subfolder (depth >= 4)
            if first == "users" and len(resolved.parts) >= 4:
                pass
            else:
                raise ValueError("Sistem klasörleri çalışma klasörü olarak seçilemez.")
    else:
        if str(resolved) == "/":
            raise ValueError("Disk kökleri çalışma klasörü olarak seçilemez.")
        first = resolved.parts[1].lower() if len(resolved.parts) > 1 else ""
        if first in LINUX_SYSTEM_ROOTS:
            raise ValueError("Sistem klasörleri çalışma klasörü olarak seçilemez.")
        if first in LINUX_SHALLOW_ROOTS:
            # /home → blocked, /home/sami → blocked (user home, already caught above)
            # /home/sami/Documents → allowed (depth >= 4: /, home, sami, Documents)
            if len(resolved.parts) < 4:
                raise ValueError("Sistem klasörleri çalışma klasörü olarak seçilemez.")

    return resolved


def sys_platform() -> str:
    return os.sys.platform


def resolve_workspace_child(root_path: str | Path, relative_path: str) -> Path:
    root = Path(root_path).expanduser().resolve()
    child = (root / relative_path).resolve()
    if not _is_relative_to(child, root):
        raise ValueError("Seçilen klasör dışına erişim engellendi.")
    return child


def scan_workspace_tree(*, root_path: Path, office_id: str, workspace_root_id: int, max_bytes: int, extensions: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    allowed = {ext.lower() for ext in (extensions or SUPPORTED_EXTENSIONS.keys())}
    items: list[dict[str, Any]] = []
    stats = {"files_seen": 0, "files_indexed": 0, "files_skipped": 0, "files_failed": 0}
    for file_path in _iter_workspace_files(root_path):
        if file_path.is_symlink() or not file_path.is_file():
            continue
        try:
            resolved = file_path.resolve()
        except OSError:
            stats["files_failed"] += 1
            continue
        if not _is_relative_to(resolved, root_path):
            stats["files_skipped"] += 1
            continue
        stats["files_seen"] += 1
        extension = file_path.suffix.lower()
        if extension not in allowed or not supported_extension(file_path):
            stats["files_skipped"] += 1
            continue
        relative_path = resolved.relative_to(root_path).as_posix()
        stat = resolved.stat()
        if stat.st_size > max_bytes:
            stats["files_failed"] += 1
            items.append(
                {
                    "relative_path": relative_path,
                    "display_name": resolved.stem,
                    "extension": extension,
                    "content_type": guess_content_type(resolved),
                    "size_bytes": int(stat.st_size),
                    "mtime": int(stat.st_mtime),
                    "checksum": hashlib.sha256(f"oversize:{relative_path}:{stat.st_size}".encode("utf-8")).hexdigest(),
                    "parser_status": "failed",
                    "indexed_status": "failed",
                    "document_language": "belirsiz",
                    "text": "",
                    "error": "Dosya boyutu izin verilen sınırı aşıyor.",
                }
            )
            continue
        try:
            text, content_type = parse_document(resolved)
            parser_status = "parsed"
            indexed_status = "indexed"
            error = None
            stats["files_indexed"] += 1
        except ParseError as exc:
            text = ""
            content_type = guess_content_type(resolved)
            parser_status = "failed"
            indexed_status = "failed"
            error = str(exc)
            stats["files_failed"] += 1
        checksum = _file_checksum(resolved)
        items.append(
            {
                "relative_path": relative_path,
                "display_name": resolved.stem,
                "extension": extension,
                "content_type": content_type,
                "size_bytes": int(stat.st_size),
                "mtime": int(stat.st_mtime),
                "checksum": checksum,
                "parser_status": parser_status,
                "indexed_status": indexed_status,
                "document_language": detect_language(text),
                "text": text,
                "error": error,
            }
        )
    return items, stats


def build_workspace_chunks(*, office_id: str, workspace_root_id: int, workspace_document_id: int, document_name: str, relative_path: str, text: str) -> list[dict[str, Any]]:
    chunks = build_persisted_chunks(
        office_id=office_id,
        matter_id=workspace_root_id,
        document_id=workspace_document_id,
        document_name=document_name,
        source_type="workspace",
        text=text,
    )
    for chunk in chunks:
        metadata = json.loads(chunk["metadata_json"])
        metadata["relative_path"] = relative_path
        chunk["metadata_json"] = json.dumps(metadata, ensure_ascii=False)
    return chunks


def build_workspace_search_result(*, query: str, rows: list[dict[str, Any]], limit: int = 5) -> dict[str, Any]:
    citations = score_chunk_records(query, rows, k=limit)
    for citation in citations:
        citation["workspace_document_id"] = citation.get("document_id")
        citation["scope"] = "workspace"
        citation["relative_path"] = citation.get("metadata", {}).get("relative_path")
    support_level = "yuksek" if citations and max(float(item.get("relevance_score", 0.0)) for item in citations) >= 0.26 else "orta" if citations else "dusuk"
    manual_review_required = not citations or support_level != "yuksek"
    coverage = round(min(1.0, sum(float(c["relevance_score"]) for c in citations[:3])), 2) if citations else 0.0
    attention_points: list[str] = []
    missing_document_signals: list[str] = []
    draft_suggestions: list[str] = []
    related_documents: dict[int, dict[str, Any]] = {}
    for citation in citations:
        document_id = int(citation.get("document_id") or 0)
        current = related_documents.get(document_id)
        relative_path = str(citation.get("relative_path") or "")
        folder_label = str(Path(relative_path).parent) if relative_path else ""
        if folder_label in {".", ""}:
            folder_reason = "Kök klasör düzeyi"
        else:
            folder_reason = folder_label
        if current is None or float(citation["relevance_score"]) > float(current["max_score"]):
            related_documents[document_id] = {
                "workspace_document_id": document_id,
                "document_name": citation.get("document_name"),
                "relative_path": citation.get("relative_path"),
                "max_score": citation.get("relevance_score"),
                "reason": f"İlgili pasaj {folder_reason} bağlamında bulundu.",
            }
    if not citations:
        attention_points.append("Bu sorgu için güçlü dayanak bulunamadı; sonucu kullanmadan önce ek belge arayın.")
        missing_document_signals.append("İlgili sözleşme, dilekçe, yazışma veya dekont çalışma klasöründe bulunmuyor olabilir.")
        draft_suggestions.extend(["Belge talep listesi taslağı", "İnceleme notu taslağı"])
    else:
        if len(related_documents) == 1:
            attention_points.append("Sonuç şu an tek bir belgeye dayanıyor; ikinci bir dayanak belge arayın.")
        if coverage < 0.55:
            attention_points.append("Kaynak kapsaması sınırlı; arama sorgusunu daraltın veya ek belge ekleyin.")
        if manual_review_required:
            attention_points.append("Sonuç destekleyici pasajlarla geldi ama insan incelemesi hâlâ gerekli.")
        top_paths = [str(item.get("relative_path") or "") for item in related_documents.values() if item.get("relative_path")]
        if top_paths and len({Path(path).parent.as_posix() for path in top_paths}) == 1:
            folder_name = Path(top_paths[0]).parent.as_posix()
            missing_document_signals.append(
                f"Dayanaklar büyük ölçüde tek klasörde toplandı: {folder_name if folder_name not in {'.', ''} else 'kök klasör'}. Karşı belge veya yazışma eksik olabilir."
            )
        if any("sozlesme" in str(item.get("document_name") or "").lower() for item in related_documents.values()):
            draft_suggestions.append("İç ekip özeti taslağı")
        draft_suggestions.extend(["Müvekkil durum güncellemesi taslağı", "İlk dosya değerlendirmesi taslağı"])
    # preserve order / uniqueness
    seen_points: set[str] = set()
    attention_points = [item for item in attention_points if not (item in seen_points or seen_points.add(item))]
    seen_missing: set[str] = set()
    missing_document_signals = [item for item in missing_document_signals if not (item in seen_missing or seen_missing.add(item))]
    seen_drafts: set[str] = set()
    draft_suggestions = [item for item in draft_suggestions if not (item in seen_drafts or seen_drafts.add(item))]
    return {
        "answer": (
            f"Seçilen çalışma klasöründe {len(related_documents)} belge ve {len(citations)} destekleyici pasaj bulundu."
            if citations
            else "Seçilen çalışma klasöründe sorguyu destekleyen bir belge bulunamadı."
        ),
        "support_level": support_level,
        "manual_review_required": manual_review_required,
        "citation_count": len(citations),
        "source_coverage": coverage,
        "attention_points": attention_points,
        "missing_document_signals": missing_document_signals,
        "draft_suggestions": draft_suggestions[:4],
        "citations": citations,
        "related_documents": sorted(related_documents.values(), key=lambda item: item["max_score"], reverse=True)[:5],
        "scope": "workspace",
    }
