import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Paper(Base, UUIDMixin, TimestampMixin):
    """PubMed paper metadata. `pmid` is unique so re-running a search upserts
    instead of duplicating — ingestion must be idempotent because users will
    search overlapping topics."""

    __tablename__ = "papers"

    pmid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    # Author lists are ragged (1..500+ names) and only ever read whole —
    # JSONB list of names beats a normalized authors table we'd never query.
    authors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    abstract: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(String(500))
    publication_date: Mapped[date | None] = mapped_column(Date)

    chunks: Mapped[list["PaperChunk"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class Document(Base, UUIDMixin, TimestampMixin):
    """A user-uploaded PDF. Separate from papers: it has an owner, a filename,
    and a processing lifecycle; a PubMed paper has none of those."""

    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(Text)
    # pending -> processing -> ready | failed. A string (not a DB enum) because
    # ALTER TYPE for enum changes is painful in Postgres migrations.
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)

    chunks: Mapped[list["PaperChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class PaperChunk(Base, UUIDMixin, TimestampMixin):
    """The unit of retrieval. Postgres keeps the text (source of truth);
    ChromaDB keeps the embedding, linked by chroma_id. A chunk comes from
    exactly one of (paper, document) — enforced by a CHECK constraint, because
    'trust the application code' is not an integrity strategy."""

    __tablename__ = "paper_chunks"
    __table_args__ = (
        CheckConstraint(
            "(paper_id IS NULL) != (document_id IS NULL)",
            name="exactly_one_source",
        ),
        UniqueConstraint("paper_id", "chunk_index"),
        UniqueConstraint("document_id", "chunk_index"),
    )

    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    chroma_id: Mapped[str] = mapped_column(String(64), unique=True)

    paper: Mapped[Paper | None] = relationship(back_populates="chunks")
    document: Mapped[Document | None] = relationship(back_populates="chunks")
