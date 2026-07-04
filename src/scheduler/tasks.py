"""Four core scheduled task functions.

1. fetch_all_sources() — Fetch articles from all enabled sources
2. analyze_pending_articles() — Analyze articles awaiting AI scoring
3. generate_daily_report() — Create daily news report
4. cleanup_old_articles() — Remove old articles and reclaim space
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import structlog
from sqlalchemy import delete, select

from src.analyzer.cost_tracker import CostTracker
from src.analyzer.llm_client import LLMClient
from src.analyzer.scorer import ArticleScorer
from src.config import settings
from src.database import async_session_factory
from src.fetchers.rate_limiter import RateLimiter
from src.fetchers.rss_fetcher import RSSFetcher
from src.models.article import Article
from src.models.source import Source
from src.reports.generator import ReportGenerator

logger = structlog.get_logger(__name__)

# Global cost tracker shared across tasks
cost_tracker = CostTracker(daily_budget_usd=settings.daily_cost_limit_usd)


async def fetch_all_sources() -> dict:
    """Fetch articles from all enabled sources.

    Runs concurrently with a global semaphore to limit simultaneous fetches.
    Returns a summary dict with counts.
    """
    logger.info("Starting fetch_all_sources task")

    semaphore = asyncio.Semaphore(settings.max_concurrent_fetches)
    total_added = 0
    total_skipped = 0
    sources_processed = 0
    sources_failed = 0

    async with async_session_factory() as session:
        async with httpx.AsyncClient(timeout=30) as http_client:
            try:
                # Get all enabled sources
                stmt = select(Source).where(Source.enabled.is_(True))
                result = await session.execute(stmt)
                sources = list(result.scalars().all())

                if not sources:
                    logger.info("No enabled sources found")
                    return {"added": 0, "skipped": 0, "sources": 0, "failed": 0}

                async def _fetch_one(source: Source):
                    nonlocal total_added, total_skipped, sources_processed, sources_failed
                    async with semaphore:
                        try:
                            rate_limiter = RateLimiter(
                                max_requests=source.rate_limit_requests,
                                window_seconds=source.rate_limit_window_seconds,
                            )

                            # Select the right fetcher for the source type
                            source_type = source.source_type
                            if source_type == "rss":
                                fetcher = RSSFetcher(source, session, rate_limiter, http_client)
                            else:
                                logger.warning(
                                    "Unsupported source type, skipping",
                                    source=source.name,
                                    type=source_type,
                                )
                                sources_failed += 1
                                return

                            added = await fetcher.run()
                            total_added += added
                            sources_processed += 1
                            await session.commit()

                        except Exception as exc:
                            sources_failed += 1
                            logger.error(
                                "Source fetch failed",
                                source=source.name,
                                error=str(exc),
                                exc_info=True,
                            )
                            await session.rollback()

                # Fetch all sources concurrently (limited by semaphore)
                await asyncio.gather(*(_fetch_one(s) for s in sources))

            finally:
                await session.commit()

    summary = {
        "added": total_added,
        "skipped": total_skipped,
        "sources": sources_processed,
        "failed": sources_failed,
    }
    logger.info("fetch_all_sources complete", **summary)
    return summary


async def analyze_pending_articles(batch_size: int | None = None) -> dict:
    """Analyze articles that haven't been scored yet.

    Uses the configured batch size. Stops early if the daily cost budget is exceeded.
    Returns a summary dict.
    """
    if batch_size is None:
        batch_size = settings.analysis_batch_size

    logger.info("Starting analyze_pending_articles task", batch_size=batch_size)

    async with async_session_factory() as session:
        try:
            llm_client = LLMClient(cost_tracker=cost_tracker)
            scorer = ArticleScorer(session, llm_client=llm_client, cost_tracker=cost_tracker)

            articles = await scorer.get_pending_articles(limit=batch_size)
            if not articles:
                logger.info("No pending articles to analyze")
                return {"analyzed": 0, "skipped": 0}

            results = await scorer.analyze_batch(articles)
            await session.commit()

            summary = {
                "analyzed": len(results),
                "skipped": len(articles) - len(results),
                "daily_cost": round(cost_tracker.daily_cost_usd, 4),
                "remaining_budget": round(cost_tracker.remaining_budget_usd, 2),
            }
            logger.info("analyze_pending_articles complete", **summary)
            return summary

        except Exception as exc:
            await session.rollback()
            logger.error("analyze_pending_articles failed", error=str(exc), exc_info=True)
            raise


async def generate_daily_report() -> dict:
    """Generate the daily news report for yesterday."""
    report_date = date.today() - timedelta(days=1)
    logger.info("Starting generate_daily_report task", date=str(report_date))

    async with async_session_factory() as session:
        try:
            llm_client = LLMClient(cost_tracker=cost_tracker)
            generator = ReportGenerator(session, llm_client=llm_client, cost_tracker=cost_tracker)

            report = await generator.generate_for_date(report_date)
            await session.commit()

            summary = {
                "date": str(report_date),
                "articles_covered": report.articles_covered,
                "model": report.model_name,
                "cost": round(report.estimated_cost_usd or 0, 4),
            }
            logger.info("generate_daily_report complete", **summary)
            return summary

        except Exception as exc:
            await session.rollback()
            logger.error("generate_daily_report failed", error=str(exc), exc_info=True)
            raise


async def cleanup_old_articles(retention_days: int | None = None) -> dict:
    """Remove articles older than the retention period.

    CASCADE delete also removes associated AI analysis scores.
    Runs VACUUM to reclaim disk space (requires autocommit).
    """
    if retention_days is None:
        retention_days = settings.article_retention_days

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    logger.info("Starting cleanup_old_articles task", cutoff=str(cutoff))

    async with async_session_factory() as session:
        try:
            stmt = delete(Article).where(Article.fetched_at < cutoff)
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount

            summary = {
                "deleted_articles": deleted_count,
                "retention_days": retention_days,
                "cutoff_date": cutoff.isoformat(),
            }
            logger.info("cleanup_old_articles complete", **summary)
            return summary

        except Exception as exc:
            await session.rollback()
            logger.error("cleanup_old_articles failed", error=str(exc), exc_info=True)
            raise
