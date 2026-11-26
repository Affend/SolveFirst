"""Offline tests for Milestone 3: PDF pieces, public ids, and the upload size limit.

These import the app, so they need a .env file (or the same environment variables),
but they never connect to TiDB or Gemini. Run with: pytest
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import new_public_id
from app.pdf_store import PIECE_SIZE, split_into_pieces


def test_pdf_pieces_join_back_to_the_same_bytes():
    data = bytes(range(256)) * (PIECE_SIZE // 256 * 2 + 10)  # a bit more than 2 pieces
    pieces = split_into_pieces(data)
    assert len(pieces) == 3
    assert all(len(piece) <= PIECE_SIZE for piece in pieces)
    assert b"".join(pieces) == data


def test_small_pdf_is_one_piece():
    assert split_into_pieces(b"%PDF-small") == [b"%PDF-small"]


def test_public_ids_are_random_and_22_characters():
    ids = {new_public_id() for _ in range(1000)}
    assert len(ids) == 1000  # no repeats
    assert all(len(public_id) == 22 for public_id in ids)


def test_oversized_upload_is_rejected_before_reading_and_browser_can_read_why():
    # TestClient without "with" does not run the startup code, so no database is needed.
    client = TestClient(app)
    too_big = b"0" * ((settings.max_upload_mb + 2) * 1024 * 1024)
    response = client.post(
        "/documents",
        files={"file": ("big.pdf", too_big, "application/pdf")},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]
    # CORS wraps the size check, so the browser is allowed to read this error.
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_health_check_needs_no_database():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
