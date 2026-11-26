"""Offline tests for the PyMuPDF helpers. Run with: pytest"""

import pymupdf
import pytest

from app.pdf_text import (
    PAGE_IMAGE_WIDTH,
    NotAPdfError,
    PageNotFoundError,
    extract_page_texts,
    render_page_png,
)


def make_pdf(path, page_texts):
    document = pymupdf.open()
    for text in page_texts:
        document.new_page(width=842, height=595).insert_text((50, 80), text)
    document.save(path)


def test_extract_page_texts_returns_one_string_per_page(tmp_path):
    pdf = tmp_path / "deck.pdf"
    make_pdf(pdf, ["First slide", "Second slide"])
    texts = extract_page_texts(pdf.read_bytes())
    assert len(texts) == 2
    assert "Second slide" in texts[1]


def test_non_pdf_is_rejected():
    with pytest.raises(NotAPdfError):
        extract_page_texts(b"just some text")


def test_render_page_png_returns_png_of_fixed_width(tmp_path):
    pdf = tmp_path / "deck.pdf"
    make_pdf(pdf, ["First slide", "Second slide"])
    png = render_page_png(pdf, 2)
    assert png.startswith(b"\x89PNG")
    assert pymupdf.Pixmap(png).width == PAGE_IMAGE_WIDTH


def test_render_page_png_rejects_pages_outside_the_deck(tmp_path):
    pdf = tmp_path / "deck.pdf"
    make_pdf(pdf, ["Only slide"])
    for page_number in (0, 2):
        with pytest.raises(PageNotFoundError):
            render_page_png(pdf, page_number)
