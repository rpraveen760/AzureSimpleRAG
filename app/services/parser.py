"""
Document parsing service.

Extracts plain text from uploaded files (PDF, Markdown, HTML, plain text).
Each parser returns a clean string ready for the chunking pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

from app.models.schemas import DocumentType

logger = logging.getLogger(__name__)


def detect_type(filename: str) -> DocumentType:
    """Infer document type from file extension."""
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": DocumentType.PDF,
        ".md": DocumentType.MARKDOWN,
        ".markdown": DocumentType.MARKDOWN,
        ".txt": DocumentType.TEXT,
        ".html": DocumentType.HTML,
        ".htm": DocumentType.HTML,
    }
    return mapping.get(ext, DocumentType.TEXT)


def parse_pdf(content: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=content, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            pages.append(text.strip())
    doc.close()
    return "\n\n".join(pages)


def parse_markdown(content: bytes) -> str:
    """Convert Markdown to plain text via intermediate HTML."""
    html = markdown.markdown(content.decode("utf-8", errors="replace"))
    return _html_to_text(html)


def parse_html(content: bytes) -> str:
    """Strip HTML tags, keeping readable text."""
    return _html_to_text(content.decode("utf-8", errors="replace"))


def parse_text(content: bytes) -> str:
    """Decode raw text."""
    return content.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script / style blocks
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


# ── Unified entry point ─────────────────────────────────────────────────────

_PARSERS = {
    DocumentType.PDF: parse_pdf,
    DocumentType.MARKDOWN: parse_markdown,
    DocumentType.HTML: parse_html,
    DocumentType.TEXT: parse_text,
}


def parse_document(content: bytes, filename: str) -> str:
    """
    Parse an uploaded document into plain text.

    Raises ValueError if the file cannot be parsed.
    """
    doc_type = detect_type(filename)
    parser = _PARSERS.get(doc_type, parse_text)
    logger.info("Parsing %s as %s (%d bytes)", filename, doc_type.value, len(content))

    try:
        text = parser(content)
    except Exception as exc:
        raise ValueError(f"Failed to parse {filename}: {exc}") from exc

    if not text.strip():
        raise ValueError(f"No extractable text found in {filename}")

    return text
