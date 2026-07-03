"""Initial schema — all core tables.

Revision ID: 001
Revises:
Create Date: 2026-06-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- sources ---
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "source_type",
            sa.String(20),
            sa.CheckConstraint("source_type IN ('rss', 'web_api', 'web_scrape')"),
            nullable=False,
        ),
        sa.Column("feed_url", sa.String(2048)),
        sa.Column("base_url", sa.String(2048)),
        sa.Column("config", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("fetch_interval_minutes", sa.Integer, default=30, nullable=False),
        sa.Column("rate_limit_requests", sa.Integer, default=10, nullable=False),
        sa.Column("rate_limit_window_seconds", sa.Integer, default=60, nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_message", sa.Text),
        sa.Column("consecutive_failures", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_sources_enabled", "sources", ["enabled"], postgresql_where=sa.text("enabled = TRUE"))
    op.create_index("idx_sources_source_type", "sources", ["source_type"])
    op.create_index("idx_sources_last_fetched", "sources", ["last_fetched_at"])

    # --- articles ---
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("simhash", sa.String(16)),
        sa.Column("content", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("author", sa.String(255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("image_url", sa.String(2048)),
        sa.Column("categories", postgresql.JSONB, default=list, nullable=False),
        sa.Column("metadata", postgresql.JSONB, default=dict, nullable=False),
        sa.Column(
            "is_duplicate_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url", name="uq_articles_url"),
        sa.UniqueConstraint("content_hash", name="uq_articles_content_hash"),
    )
    op.create_index("idx_articles_source_id", "articles", ["source_id"])
    op.create_index("idx_articles_published_at", "articles", ["published_at"])
    op.create_index("idx_articles_fetched_at", "articles", ["fetched_at"])
    op.create_index("idx_articles_content_hash", "articles", ["content_hash"])
    op.create_index("idx_articles_simhash", "articles", ["simhash"])
    op.create_index("idx_articles_language", "articles", ["language"])

    # Full-text search column (requires superuser, run manually if needed)
    # op.execute(
    #     "ALTER TABLE articles ADD COLUMN search_vector tsvector "
    #     "GENERATED ALWAYS AS ("
    #     "  setweight(to_tsvector('english', COALESCE(title, '')), 'A') || "
    #     "  setweight(to_tsvector('english', COALESCE(summary, '')), 'B')"
    #     ") STORED"
    # )
    # op.create_index("idx_articles_search", "articles", ["search_vector"], postgresql_using="gin")

    # --- ai_analysis_scores ---
    op.create_table(
        "ai_analysis_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_provider", sa.String(50), default="anthropic", nullable=False),
        sa.Column("relevance_score", sa.Float),
        sa.Column("credibility_score", sa.Float),
        sa.Column("freshness_score", sa.Float),
        sa.Column("novelty_score", sa.Float),
        sa.Column("depth_score", sa.Float),
        sa.Column("overall_score", sa.Float),
        sa.Column("ai_summary", sa.Text),
        sa.Column("key_points", postgresql.JSONB, default=list, nullable=False),
        sa.Column("sentiment", sa.String(20)),
        sa.Column("primary_category", sa.String(100)),
        sa.Column("secondary_categories", postgresql.JSONB, default=list, nullable=False),
        sa.Column("entities", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("reading_level", sa.String(20)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("estimated_cost_usd", sa.Float),
        sa.Column("content_hash_at_analysis", sa.String(64)),
        sa.Column("is_cached_result", sa.Boolean, default=False, nullable=False),
        sa.Column("raw_response", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", name="uq_article_analysis"),
    )
    op.create_index("idx_analysis_overall_score", "ai_analysis_scores", ["overall_score"])
    op.create_index("idx_analysis_primary_category", "ai_analysis_scores", ["primary_category"])
    op.create_index("idx_analysis_created_at", "ai_analysis_scores", ["created_at"])

    # --- daily_reports ---
    op.create_table(
        "daily_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("executive_summary", sa.Text),
        sa.Column("report_markdown", sa.Text, nullable=False),
        sa.Column("report_html", sa.Text),
        sa.Column("top_articles", postgresql.JSONB),
        sa.Column("category_breakdown", postgresql.JSONB),
        sa.Column("statistics", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("articles_covered", sa.Integer, default=0, nullable=False),
        sa.Column("generation_duration_seconds", sa.Float),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("estimated_cost_usd", sa.Float),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_date", name="uq_report_date"),
    )
    op.create_index("idx_reports_report_date", "daily_reports", ["report_date"])
    op.create_index("idx_reports_status", "daily_reports", ["status"])


def downgrade() -> None:
    op.drop_table("daily_reports")
    op.drop_table("ai_analysis_scores")
    op.drop_table("articles")
    op.drop_table("sources")
