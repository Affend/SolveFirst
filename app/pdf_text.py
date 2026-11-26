"""PyMuPDF helpers: check an upload is a real PDF, extract page text, render a page as an image."""

from pathlib import Path

import pymupdf

# Every page image is rendered this many pixels wide, so all slides look the same size.
PAGE_IMAGE_WIDTH = 1200


class NotAPdfError(ValueError):
    """The file is not a PDF at all."""


class UnreadablePdfError(ValueError):
    """The file is a PDF but cannot be read (password-protected, damaged, or empty)."""


class PageNotFoundError(ValueError):
    """The requested page number is not in the PDF."""


def extract_page_texts(pdf_bytes: bytes) -> list[str]:
    """Return one string per page: index 0 is page 1, index 1 is page 2, and so on."""
    # Every PDF starts with "%PDF-" near the top. This catches renamed .txt or .docx files.
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise NotAPdfError()

    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several error types for broken files
        raise UnreadablePdfError() from exc

    with document:
        if document.needs_pass or document.page_count == 0:
            raise UnreadablePdfError()
        return [page.get_text("text") for page in document]


def render_page_png(pdf_path: Path, page_number: int) -> bytes:
    """Render one page (page_number counts from 1) as a PNG image, PAGE_IMAGE_WIDTH pixels wide."""
    with pymupdf.open(pdf_path) as document:
        if not 1 <= page_number <= document.page_count:
            raise PageNotFoundError()
        page = document[page_number - 1]
        zoom = PAGE_IMAGE_WIDTH / page.rect.width  # scale factor from PDF points to pixels
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return pixmap.tobytes("png")
