"""Health check helpers for the scheduler and overall system status."""

from __future__ import annotations

from sqlalchemy import func, select

from src.analyzer.cost_tracker import cost_tracker
from src.database import async_session_factory
from src.models.ai_analysis import AIAnalysisScore
from src.models.article import Article
from src.models.source import Source


async def get_system_health(scheduler_manager) -> dict:
    """Collect comprehensive system health metrics."""
    async with async_session_factory() as session:
        # Source counts
        total_sources = await session.scalar(
            select(func.count(Source.id))
        ) or 0
        enabled_sources = await session.scalar(
            select(func.count(Source.id)).where(Source.enabled.is_(True))
        ) or 0

        # Article counts
        total_articles = await session.scalar(
            select(func.count(Article.id))
        ) or 0

        # Pending analysis count
        analyzed_ids = select(AIAnalysisScore.article_id)
        pending_analysis = await session.scalar(
            select(func.count(Article.id)).where(
                Article.id.not_in(analyzed_ids),
                Article.is_duplicate_of.is_(None),
            )
        ) or 0

    scheduler_health = scheduler_manager.get_health()

    return {
        "status": "healthy" if scheduler_health["scheduler_running"] else "degraded",
        "scheduler": scheduler_health,
        "sources": {
            "total": total_sources,
            "enabled": enabled_sources,
            "disabled": total_sources - enabled_sources,
        },
        "articles": {
            "total": total_articles,
            "pending_analysis": pending_analysis,
        },
        "costs": {
            "daily_usd": round(cost_tracker.daily_cost_usd, 4),
            "remaining_budget_usd": round(cost_tracker.remaining_budget_usd, 2),
            "total_usd": round(cost_tracker.total_cost_usd, 4),
        },
    }
