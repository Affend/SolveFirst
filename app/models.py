"""The four database tables.

documents 1──* pages      (the text of each PDF page, used by the quote check)
documents 1──* problems   (example problems found in the deck)
problems  1──* steps      (numbered solution steps, each linked to a page)
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Current time in UTC. MySQL DATETIME has no time zone, so we always store UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    given: Mapped[str] = mapped_column(Text)
    asked: Mapped[str] = mapped_column(Text)
    concept: Mapped[str] = mapped_column(Text)

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
    reason: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int]  # AI-derived steps point at the page of their problem
    source_quote: Mapped[str] = mapped_column(Text)  # verbatim slide text, or "" when AI-derived
    ai_derived: Mapped[bool]  # final label, after the quote check
    quote_verified: Mapped[bool]  # True only if source_quote was found on page_number

    problem: Mapped[Problem] = relationship(back_populates="steps")
