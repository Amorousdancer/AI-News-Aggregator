"""Information source configuration model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("source_type IN ('rss', 'web_api', 'web_scrape')"),
        nullable=False,
    )
    feed_url: Mapped[str | None] = mapped_column(String(2048))
    base_url: Mapped[str | None] = mapped_column(String(2048))
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
