"""Daily report model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)

    executive_summary: Mapped[str | None] = mapped_column(Text)
    report_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    report_html: Mapped[str | None] = mapped_column(Text)

    top_articles: Mapped[dict | None] = mapped_column(JSONB)
    category_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    statistics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    articles_covered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation_duration_seconds: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("report_date", name="uq_report_date"),
        Index("idx_reports_report_date", "report_date"),
        Index("idx_reports_status", "status"),
    )
