from __future__ import annotations

import mimetypes
from pathlib import Path

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - optional import until dependency exists
    DocxDocument = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional import until dependency exists
    PdfReader = None

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ParseError(ValueError):
    pass


def supported_extension(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[ext]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _decode_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="ignore").strip()
    if text:
        return text
    text = content.decode("latin-1", errors="ignore").strip()
    if text:
        return text
    raise ParseError("Belge metni okunamadi.")


def _parse_pdf(path: Path) -> str:
    if PdfReader is None:
        raise ParseError("PDF okuma bileseni kurulu degil.")
    try:
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            if extracted:
                parts.append(extracted)
        text = "\n\n".join(parts).strip()
    except Exception as exc:  # pragma: no cover - library specific failures
        raise ParseError(f"PDF ayrışımı başarısız: {exc}") from exc
    if not text:
        raise ParseError("PDF içinde metin bulunamadı.")
    return text


def _parse_docx(path: Path) -> str:
    if DocxDocument is None:
        raise ParseError("DOCX okuma bileşeni kurulu değil.")
    try:
        document = DocxDocument(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()).strip()
    except Exception as exc:  # pragma: no cover - library specific failures
        raise ParseError(f"DOCX ayrışımı başarısız: {exc}") from exc
    if not text:
        raise ParseError("DOCX içinde metin bulunamadı.")
    return text


def parse_document(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ParseError("Dosya turu desteklenmiyor.")
    if ext in {".txt", ".md"}:
        return _decode_text(path.read_bytes()), guess_content_type(path)
    if ext == ".pdf":
        return _parse_pdf(path), guess_content_type(path)
    if ext == ".docx":
        return _parse_docx(path), guess_content_type(path)
    raise ParseError("Dosya turu desteklenmiyor.")
