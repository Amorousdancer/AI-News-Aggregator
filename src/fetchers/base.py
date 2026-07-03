"""Abstract base class for all fetchers."""

from __future__ import annotations

import structlog
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dedup.pipeline import ArticleCandidate, DedupPipeline
from src.fetchers.rate_limiter import RateLimiter
from src.models.article import Article
from src.models.source import Source

logger = structlog.get_logger(__name__)


class BaseFetcher(ABC):
    """Abstract fetcher for a specific source type (RSS, API, scrape)."""

    def __init__(self, source: Source, session: AsyncSession, rate_limiter: RateLimiter):
        self.source = source
        self.session = session
        self.rate_limiter = rate_limiter
        self.dedup = DedupPipeline(session)
        self._articles_added = 0
        self._articles_skipped = 0

    @abstractmethod
    async def fetch(self) -> list[ArticleCandidate]:
        """Fetch candidate articles from the source.

        Returns a list of raw article candidates (before dedup).
        """
        ...

    async def run(self) -> int:
        """Execute the full fetch → dedup → insert pipeline for this source.

        Returns the number of new articles added.
        """
        self._articles_added = 0
        self._articles_skipped = 0

        try:
            # Check rate limit
            if not await self.rate_limiter.acquire():
                logger.warning(
                    "Rate limit exceeded for source",
                    source=self.source.name,
                    source_id=str(self.source.id),
                )
                return 0

            # Fetch candidates
            candidates = await self.fetch()
            logger.info(
                "Fetched candidates",
                source=self.source.name,
                count=len(candidates),
            )

            # Dedup and insert each candidate
            for candidate in candidates:
                candidate.source_id = self.source.id
                result = await self.dedup.check(candidate)

                if result.is_new:
                    article = Article(
                        source_id=self.source.id,
                        title=candidate.title,
                        url=result.url,
                        canonical_url=result.url,
                        content_hash=result.content_hash,
                        simhash=result.simhash,
                        content=candidate.content,
                        summary=candidate.summary,
                        author=candidate.author,
                        published_at=_parse_iso(candidate.published_at),
                        language=candidate.language or "en",
                        image_url=candidate.image_url,
                        categories=candidate.categories or [],
                        extra_metadata=candidate.metadata or {},
                    )
                    self.session.add(article)
                    self._articles_added += 1
                else:
                    self._articles_skipped += 1
                    logger.debug(
                        "Duplicate article skipped",
                        url=candidate.url,
                        tier=result.match_tier,
                    )

            await self.session.flush()

            # Update source status on success
            await self._update_source_success()

            logger.info(
                "Fetch complete",
                source=self.source.name,
                added=self._articles_added,
                skipped=self._articles_skipped,
            )

            return self._articles_added

        except Exception as exc:
            await self._update_source_error(str(exc))
            logger.error(
                "Fetch failed",
                source=self.source.name,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def _update_source_success(self) -> None:
        """Update source metadata after a successful fetch."""
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(Source)
            .where(Source.id == self.source.id)
            .values(
                last_fetched_at=now,
                consecutive_failures=0,
                updated_at=now,
            )
        )

    async def _update_source_error(self, error_message: str) -> None:
        """Update source metadata after a fetch error."""
        now = datetime.now(timezone.utc)
        new_failures = self.source.consecutive_failures + 1
        enabled = new_failures < 5  # Circuit breaker at 5 consecutive failures

        await self.session.execute(
            update(Source)
            .where(Source.id == self.source.id)
            .values(
                last_error_at=now,
                last_error_message=error_message,
                consecutive_failures=new_failures,
                enabled=enabled,
                updated_at=now,
            )
        )

        if not enabled:
            logger.warning(
                "Circuit breaker tripped — source disabled",
                source=self.source.name,
                failures=new_failures,
            )


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-format datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
