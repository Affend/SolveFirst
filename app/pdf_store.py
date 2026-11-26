"""Where uploaded PDFs are kept.

TiDB is the real storage. Free hosting servers (like Render's free tier) wipe their disk on
every restart and every sleep, so a PDF only on disk would disappear. Each PDF is therefore
saved in the database, split into pieces of 2 MB, because a TiDB row must stay under 6 MB.

The uploads/ folder is only a cache: PyMuPDF needs a file to open, and reading from disk is
faster than fetching the PDF from TiDB on every slide image. If the cached file is missing,
it is rebuilt from TiDB.
"""

import hashlib
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import Engine, exists, select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models import Document, DocumentFile

logger = logging.getLogger("solvefirst.pdf_store")

PIECE_SIZE = 2 * 1024 * 1024  # 2 MB


def split_into_pieces(data: bytes) -> list[bytes]:
    """Cut the PDF into pieces of at most PIECE_SIZE bytes."""
    return [data[start:start + PIECE_SIZE] for start in range(0, len(data), PIECE_SIZE)]


def file_rows(pdf_bytes: bytes) -> list[DocumentFile]:
    """Database rows for a PDF, ready to attach to a document: document.files = file_rows(...)."""
    return [DocumentFile(piece=number, data=piece) for number, piece in enumerate(split_into_pieces(pdf_bytes))]


def is_stored(db: Session, document: Document) -> bool:
    """True if this document's PDF is saved in TiDB."""
    return bool(db.scalar(select(exists().where(DocumentFile.document_id == document.id))))


def cached_pdf_path(db: Session, document: Document) -> Path | None:
    """Path to the PDF on disk, rebuilt from TiDB if the disk copy is gone. None if it's lost."""
    path = PROJECT_ROOT / document.stored_path
    if path.exists():
        return path

    pieces = db.scalars(
        select(DocumentFile.data).where(DocumentFile.document_id == document.id).order_by(DocumentFile.piece)
    ).all()
    pdf_bytes = b"".join(pieces)
    if not pdf_bytes or hashlib.sha256(pdf_bytes).hexdigest() != document.file_sha256:
        return None  # nothing stored, or the pieces don't add up to the original file

    # Write to a temporary name first, then rename: if several slide images are requested at
    # the same time, none of them can see a half-written file.
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(pdf_bytes)
    os.replace(temporary, path)
    return path


def copy_disk_pdfs_to_database(engine: Engine) -> int:
    """At startup: save in TiDB any PDF that so far exists only in uploads/. Returns how many."""
    copied = 0
    with Session(engine) as db:
        for document in db.scalars(select(Document)).all():
            path = PROJECT_ROOT / document.stored_path
            if path.exists() and not is_stored(db, document):
                document.files = file_rows(path.read_bytes())
                db.commit()
                copied += 1
    if copied:
        logger.info("Copied %s PDF(s) from uploads/ into TiDB.", copied)
    return copied
