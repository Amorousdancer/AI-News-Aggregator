"""Article / news item model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    simhash: Mapped[str | None] = mapped_column(String(16))

    content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), default="en")

    image_url: Mapped[str | None] = mapped_column(String(2048))
    categories: Mapped[dict] = mapped_column(JSONB, default=list, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    is_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    source = relationship("Source", lazy="selectin")
    duplicate_of = relationship("Article", remote_side=[id], lazy="selectin")
    analysis = relationship("AIAnalysisScore", back_populates="article", uselist=False, lazy="selectin")

    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        Index("idx_articles_source_id", "source_id"),
        Index("idx_articles_published_at", "published_at"),
        Index("idx_articles_fetched_at", "fetched_at"),
        Index("idx_articles_content_hash", "content_hash"),
        Index("idx_articles_simhash", "simhash"),
        Index("idx_articles_language", "language"),
    )
