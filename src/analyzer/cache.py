"""Analysis result cache — reuse results for articles with the same content hash."""

from __future__ import annotations

import structlog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ai_analysis import AIAnalysisScore

logger = structlog.get_logger(__name__)


async def find_cached_analysis(
    session: AsyncSession,
    content_hash: str,
) -> AIAnalysisScore | None:
    """Look up an existing analysis by content hash for caching.

    If the same content hash has been analyzed before, we can reuse the result
    without making another LLM call.
    """
    stmt = (
        select(AIAnalysisScore)
        .where(AIAnalysisScore.content_hash_at_analysis == content_hash)
        .order_by(AIAnalysisScore.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        logger.debug("Analysis cache hit", content_hash=content_hash[:16])
        return existing

    logger.debug("Analysis cache miss", content_hash=content_hash[:16])
    return None
