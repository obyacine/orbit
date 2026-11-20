"""Text extraction from the documents a PM brings (specifications, briefs, meeting notes).

The extracted text goes back to the PM's brief field, where it stays visible and editable:
the PM sees exactly what will be sent to the LLM. Nothing is stored here.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import PurePath

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CHARS = 60_000  # ~15k tokens: plenty for a brief or a specification, keeps the prompt fast
SUPPORTED = {".pdf": "PDF", ".docx": "Word", ".txt": "texte", ".md": "Markdown"}


class DocumentError(ValueError):
    pass


@dataclass
class ExtractedDocument:
    filename: str
    kind: str
    pages: int | None
    text: str
    truncated: bool

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "kind": self.kind,
            "pages": self.pages,
            "characters": len(self.text),
            "truncated": self.truncated,
            "text": self.text,
        }


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("Ce PDF est protégé par un mot de passe : enregistrez une version sans protection.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise DocumentError("Ce PDF est illisible ou endommagé.") from exc
    return "\n\n".join(pages), len(pages)


def _docx(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises various errors on bad files
        raise DocumentError("Ce fichier Word est illisible (seul le format .docx est pris en charge).") from exc
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:  # requirements often live in tables
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(parts)


def _plain(data: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError("Encodage du fichier texte non reconnu.")


def extract(filename: str, data: bytes) -> ExtractedDocument:
    name = PurePath(filename or "document").name
    ext = PurePath(name).suffix.lower()
    if ext not in SUPPORTED:
        raise DocumentError(f"Format non pris en charge ({ext or 'sans extension'}) : utilisez PDF, Word (.docx), .txt ou .md.")
    if not data:
        raise DocumentError("Le fichier est vide.")
    if len(data) > MAX_BYTES:
        raise DocumentError("Le fichier dépasse 10 Mo.")

    pages = None
    if ext == ".pdf":
        raw, pages = _pdf(data)
    elif ext == ".docx":
        raw = _docx(data)
    else:
        raw = _plain(data)

    text = _clean(raw)
    if len(text) < 30:
        hint = " Il s'agit probablement d'un scan : exportez un PDF avec du texte sélectionnable." if ext == ".pdf" else ""
        raise DocumentError(f"Aucun texte exploitable dans ce document.{hint}")
    truncated = len(text) > MAX_CHARS
    return ExtractedDocument(name, SUPPORTED[ext], pages, text[:MAX_CHARS], truncated)
