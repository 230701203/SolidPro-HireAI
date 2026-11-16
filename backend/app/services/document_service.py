"""Resume file validation and text extraction (PDF via PyMuPDF, DOCX via python-docx)."""

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_TEXT_CHARS = 200_000
MAX_DOCX_UNCOMPRESSED = 60 * 1024 * 1024  # zip-bomb guard


@dataclass
class ParsedDocument:
    content_type: str
    text: str
    page_count: int | None


def safe_filename(name: str) -> str:
    name = Path((name or "resume").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE).strip(" .") or "resume"
    return name[-200:]


def _bad(message: str, status: int = 422) -> AppError:
    return AppError(status, "invalid_file", message)


def validate_and_extract(filename: str, data: bytes) -> ParsedDocument:
    s = get_settings()
    ext = Path(filename or "").suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise _bad("Only PDF and DOCX resumes are accepted.", 415)
    if len(data) == 0:
        raise _bad("The file is empty.")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise _bad(f"The file is larger than the {s.max_upload_mb} MB limit.", 413)

    # Check the real content, not just the extension (stops renamed executables etc.).
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise _bad("This file is not a valid PDF.")
        return _parse_pdf(data)
    if not data.startswith(b"PK"):
        raise _bad("This file is not a valid DOCX document.")
    return _parse_docx(data)


def _parse_pdf(data: bytes) -> ParsedDocument:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise _bad("The PDF is damaged or unreadable.") from exc
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise _bad("Password-protected PDFs are not supported.")
        if doc.page_count == 0:
            raise _bad("The PDF has no pages.")
        if doc.page_count > 30:
            raise _bad("The PDF has too many pages for a resume (max 30).")
        text = "\n".join(page.get_text() for page in doc)
    except AppError:
        raise
    except Exception as exc:
        raise _bad("The PDF is damaged or unreadable.") from exc
    finally:
        doc.close()
    text = text.strip()
    if not text:
        raise _bad("No readable text was found. Scanned/image-only PDFs are not supported yet; upload a text-based PDF or a DOCX.")
    return ParsedDocument(PDF_TYPE, text[:MAX_TEXT_CHARS], None)


def _parse_docx(data: bytes) -> ParsedDocument:
    from docx import Document

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "word/document.xml" not in names:
                raise _bad("This file is not a valid DOCX document.")
            if sum(i.file_size for i in zf.infolist()) > MAX_DOCX_UNCOMPRESSED:
                raise _bad("The document is too large once unpacked.")
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
    except AppError:
        raise
    except Exception as exc:
        raise _bad("The DOCX is damaged or unreadable.") from exc
    text = "\n".join(p for p in parts if p and p.strip()).strip()
    if not text:
        raise _bad("No readable text was found in the document.")
    return ParsedDocument(DOCX_TYPE, text[:MAX_TEXT_CHARS], None)
