"""Text extraction from the PM's documents (PDF, Word, text)."""

import io

import pytest
from docx import Document

from app.module1 import documents

BRIEF = "Portail RH en libre-service pour 1200 salaries, livraison fin mars 2027, budget 180 kEUR."


def make_pdf(text: str) -> bytes:
    """Minimal one-page PDF with a text layer (what an exported Word document produces)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx() -> bytes:
    doc = Document()
    doc.add_heading("Cahier des charges", level=1)
    doc.add_paragraph(BRIEF)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Exigence", "Priorite"
    table.cell(1, 0).text, table.cell(1, 1).text = "SSO Azure AD", "Must"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_pdf_text_and_page_count():
    d = documents.extract("brief.pdf", make_pdf(BRIEF))
    assert d.kind == "PDF" and d.pages == 1
    assert "1200 salaries" in d.text and not d.truncated


def test_docx_paragraphs_and_tables():
    d = documents.extract("CDC.DOCX", make_docx())
    assert d.kind == "Word"
    assert BRIEF in d.text
    assert "SSO Azure AD | Must" in d.text


def test_plain_text_any_encoding_and_cleanup():
    d = documents.extract("notes.txt", ("Réunion de lancement\r\n\r\n\r\n\r\n" + BRIEF).encode("cp1252"))
    assert d.text.startswith("Réunion de lancement\n\n" + BRIEF[:10])


def test_long_documents_are_truncated():
    d = documents.extract("long.md", ("x" * 100 + "\n").encode() * 1000)
    assert d.truncated and len(d.text) == documents.MAX_CHARS


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("plan.xlsx", b"whatever", "Format non pris en charge"),
        ("vide.txt", b"", "vide"),
        ("scan.pdf", make_pdf(""), "scan"),
        ("casse.pdf", b"%PDF-1.4 garbage", "PDF"),
        ("faux.docx", b"not a zip", "Word"),
    ],
)
def test_clear_errors(name, data, message):
    with pytest.raises(documents.DocumentError, match=message):
        documents.extract(name, data)


def test_extract_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("ORBIT_INTERNAL_TOKEN", "t")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        ok = client.post("/documents/extract", headers={"X-Orbit-Token": "t"},
                         files={"file": ("brief.docx", make_docx())})
        assert ok.status_code == 200 and "SSO Azure AD" in ok.json()["text"]
        bad = client.post("/documents/extract", headers={"X-Orbit-Token": "t"}, files={"file": ("x.exe", b"MZ")})
        assert bad.status_code == 422
        assert client.post("/documents/extract", files={"file": ("a.txt", b"a" * 50)}).status_code == 401
    finally:
        get_settings.cache_clear()
