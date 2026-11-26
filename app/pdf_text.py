"""Checks that an upload is a real PDF and extracts the text of each page with PyMuPDF."""

import pymupdf


class NotAPdfError(ValueError):
    """The file is not a PDF at all."""


class UnreadablePdfError(ValueError):
    """The file is a PDF but cannot be read (password-protected, damaged, or empty)."""


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
