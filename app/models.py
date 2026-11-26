"""The database tables.

documents 1──* document_files (the uploaded PDF itself, in pieces of at most 2 MB)
documents 1──* pages          (the text of each PDF page, used by the quote check)
documents 1──* problems       (example problems found in the deck)
problems  1──* steps          (numbered solution steps, each linked to a page)
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import Engine, ForeignKey, String, Text, UniqueConstraint, false, inspect, text
from sqlalchemy.dialects.mysql import MEDIUMBLOB, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Current time in UTC. MySQL DATETIME has no time zone, so we always store UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_public_id() -> str:
    """A random, unguessable id for web addresses, e.g. "x7Qk2bE9...": 22 characters."""
    return secrets.token_urlsafe(16)


class Document(Base):
    __tablename__ = "documents"

    # Internal number, used only inside the database (links between tables).
    id: Mapped[int] = mapped_column(primary_key=True)
    # The id shown in web addresses. Random, so nobody can list other people's uploads
    # by counting 1, 2, 3 ...
    public_id: Mapped[str] = mapped_column(String(32), unique=True, default=new_public_id)
    # Demo samples: stored results that open instantly and can't be re-processed.
    is_sample: Mapped[bool] = mapped_column(default=False, server_default=false())
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))  # e.g. uploads/<sha256>.pdf
    # Same file uploaded twice -> same document, so we never pay Gemini twice for it.
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    page_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # "uploaded" or "processed"
    message: Mapped[str | None] = mapped_column(String(500))
    model_name: Mapped[str | None] = mapped_column(String(100))  # which Gemini model made the result
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    processed_at: Mapped[datetime | None]

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.page_number"
    )
    problems: Mapped[list["Problem"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Problem.position"
    )
    files: Mapped[list["DocumentFile"]] = relationship(
        cascade="all, delete-orphan", order_by="DocumentFile.piece"
    )


class DocumentFile(Base):
    """The uploaded PDF, stored in TiDB in pieces (see app/pdf_store.py for why)."""

    __tablename__ = "document_files"
    __table_args__ = (UniqueConstraint("document_id", "piece"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    piece: Mapped[int]  # 0, 1, 2 ... joined in this order to rebuild the PDF
    data: Mapped[bytes] = mapped_column(MEDIUMBLOB)  # at most 2 MB per piece


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_number: Mapped[int]  # 1-based physical PDF page, as a PDF viewer counts
    text: Mapped[str] = mapped_column(MEDIUMTEXT)  # plain TEXT is limited to 64 KB

    document: Mapped[Document] = relationship(back_populates="pages")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]  # order in the deck: 1, 2, 3 ...
    title: Mapped[str] = mapped_column(String(255))
    page_number: Mapped[int | None]  # page where the problem statement is shown
    given: Mapped[str] = mapped_column(Text)
    asked: Mapped[str] = mapped_column(Text)
    concept: Mapped[str] = mapped_column(Text)
    final_answer: Mapped[str | None] = mapped_column(Text)  # one sentence; math inside $...$

    document: Mapped[Document] = relationship(back_populates="problems")
    steps: Mapped[list["Step"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan", order_by="Step.step_number"
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    step_number: Mapped[int]  # 1, 2, 3 ...
    text: Mapped[str] = mapped_column(Text)
    formula: Mapped[str | None] = mapped_column(Text)  # LaTeX
    work: Mapped[str | None] = mapped_column(Text)  # LaTeX, one calculation line per text line
    result: Mapped[str | None] = mapped_column(Text)  # value with units; math inside $...$
    reason: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int]  # AI-derived steps point at the page of their problem
    source_quote: Mapped[str] = mapped_column(Text)  # verbatim slide text, or "" when AI-derived
    ai_derived: Mapped[bool]  # Gemini: neither this step nor its result is in the slides
    quote_verified: Mapped[bool]  # our check found source_quote on page_number

    problem: Mapped[Problem] = relationship(back_populates="steps")


# Columns added after the tables were first created: (table, column, SQL type).
# These are fixed names written here in the code, never user input, so building SQL is safe.
NEW_COLUMNS = [
    ("problems", "page_number", "INT NULL"),  # Milestone 2: page of the problem statement
    ("problems", "final_answer", "TEXT NULL"),  # worked calculations
    ("steps", "formula", "TEXT NULL"),
    ("steps", "work", "TEXT NULL"),
    ("steps", "result", "TEXT NULL"),
    ("documents", "is_sample", "BOOLEAN NOT NULL DEFAULT FALSE"),  # Milestone 3: demo samples
    ("documents", "public_id", "VARCHAR(32) NULL"),  # Milestone 3: unguessable web id
]


def upgrade_old_tables(engine: Engine) -> None:
    """Add columns that newer code needs to tables made by older code. Runs at every startup.

    create_all() only creates missing tables and never changes existing ones, so new
    columns are added here. A column that already exists is skipped, so once everything
    is added, this function does nothing.
    """
    inspector = inspect(engine)
    tables = {table for table, _, _ in NEW_COLUMNS}
    existing = {table: {c["name"] for c in inspector.get_columns(table)} for table in tables}
    with engine.begin() as connection:
        for table, column, sql_type in NEW_COLUMNS:
            if column in existing[table]:
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
            if (table, column) == ("problems", "page_number"):
                # Problems saved before this column existed: use the lowest page of their steps.
                connection.execute(text(
                    "UPDATE problems p "
                    "JOIN (SELECT problem_id, MIN(page_number) AS first_page FROM steps GROUP BY problem_id) s "
                    "ON s.problem_id = p.id "
                    "SET p.page_number = s.first_page"
                ))
            if (table, column) == ("documents", "public_id"):
                # Give every existing document its own random id, then make the ids unique.
                old_ids = connection.execute(text("SELECT id FROM documents WHERE public_id IS NULL")).all()
                for (document_id,) in old_ids:
                    connection.execute(
                        text("UPDATE documents SET public_id = :public_id WHERE id = :id"),
                        {"public_id": new_public_id(), "id": document_id},
                    )
                connection.execute(text("CREATE UNIQUE INDEX uq_documents_public_id ON documents (public_id)"))
