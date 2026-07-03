"""AI analysis score model — one row per analyzed article."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class AIAnalysisScore(Base):
    __tablename__ = "ai_analysis_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(50), default="anthropic", nullable=False)

    # Five scoring dimensions, all normalized 0.0 to 1.0
    relevance_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("relevance_score >= 0 AND relevance_score <= 1")
    )
    credibility_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("credibility_score >= 0 AND credibility_score <= 1")
    )
    freshness_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("freshness_score >= 0 AND freshness_score <= 1")
    )
    novelty_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("novelty_score >= 0 AND novelty_score <= 1")
    )
    depth_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("depth_score >= 0 AND depth_score <= 1")
    )
    overall_score: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("overall_score >= 0 AND overall_score <= 1")
    )
    rationale: Mapped[str | None] = mapped_column(Text)

    # AI-generated enrichment
    ai_summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[dict] = mapped_column(JSONB, default=list, nullable=False)
    sentiment: Mapped[str | None] = mapped_column(String(20))
    primary_category: Mapped[str | None] = mapped_column(String(100))
    secondary_categories: Mapped[dict] = mapped_column(JSONB, default=list, nullable=False)
    entities: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reading_level: Mapped[str | None] = mapped_column(String(20))

    # Cost tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)

    # Cache support
    content_hash_at_analysis: Mapped[str | None] = mapped_column(String(64))
    is_cached_result: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Raw LLM response for debugging
    raw_response: Mapped[dict] = mapped_column(JSONB, default=None, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    article = relationship("Article", back_populates="analysis")

    __table_args__ = (
        UniqueConstraint("article_id", name="uq_article_analysis"),
        Index("idx_analysis_overall_score", "overall_score"),
        Index("idx_analysis_primary_category", "primary_category"),
        Index("idx_analysis_created_at", "created_at"),
    )
