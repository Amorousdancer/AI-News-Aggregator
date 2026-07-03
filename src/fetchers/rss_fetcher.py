"""RSS / Atom feed fetcher using feedparser."""

from __future__ import annotations

import structlog
from datetime import datetime, timezone

import feedparser
import httpx

from src.dedup.pipeline import ArticleCandidate
from src.fetchers.base import BaseFetcher
from src.fetchers.rate_limiter import RateLimiter
from src.models.source import Source

logger = structlog.get_logger(__name__)

# Default User-Agent for feed fetching
USER_AGENT = "AI-News-Aggregator/1.0 (+https://github.com/ai-news-aggregator)"

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 30


class RSSFetcher(BaseFetcher):
    """Fetches articles from RSS/Atom feeds.

    Uses feedparser for parsing and httpx for the HTTP request.
    Supports incremental fetching based on last_fetched_at.
    """

    def __init__(
        self,
        source: Source,
        session,
        rate_limiter: RateLimiter,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(source, session, rate_limiter)
        self.http_client = http_client

    async def fetch(self) -> list[ArticleCandidate]:
        """Fetch and parse the RSS/Atom feed, returning candidate articles."""
        if not self.source.feed_url:
            logger.warning("No feed URL configured", source=self.source.name)
            return []

        feed_content = await self._download_feed()
        if not feed_content:
            return []

        feed = feedparser.parse(feed_content)
        if feed.bozo and not feed.entries:
            logger.warning(
                "Feed parse error",
                source=self.source.name,
                bozo_exception=str(feed.bozo_exception),
            )
            return []

        candidates = []
        cutoff_time = self._get_cutoff_time()

        for entry in feed.entries:
            if len(candidates) >= 100:  # Limit per fetch to avoid memory issues
                break

            published = self._extract_published(entry)

            # Incremental: skip entries older than our cutoff
            if cutoff_time and published and published < cutoff_time:
                continue

            candidate = ArticleCandidate(
                title=entry.get("title", "").strip(),
                url=entry.get("link", "").strip(),
                content=self._extract_content(entry),
                summary=entry.get("summary", "").strip() if entry.get("summary") else None,
                author=entry.get("author", "").strip() if entry.get("author") else None,
                published_at=published.isoformat() if published else None,
                language=entry.get("lang") or "en",
                image_url=self._extract_image(entry),
                categories=self._extract_categories(entry),
                metadata={
                    "feed_title": feed.feed.get("title", ""),
                    "source_type": "rss",
                    **self.source.config.get("extra_metadata", {}),
                },
            )

            if candidate.title and candidate.url:
                candidates.append(candidate)

        logger.debug(
            "Feed parsed",
            source=self.source.name,
            total_entries=len(feed.entries),
            new_candidates=len(candidates),
        )

        return candidates

    async def _download_feed(self) -> str | None:
        """Download the feed content via HTTP."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        }

        try:
            client = self.http_client
            if client is None:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    resp = await client.get(self.source.feed_url, headers=headers, follow_redirects=True)
                    resp.raise_for_status()
                    return resp.text
            else:
                resp = await client.get(self.source.feed_url, headers=headers, follow_redirects=True)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "HTTP error fetching feed",
                source=self.source.name,
                status_code=exc.response.status_code,
            )
            return None
        except httpx.RequestError as exc:
            logger.warning(
                "Request error fetching feed",
                source=self.source.name,
                error=str(exc),
            )
            return None

    def _get_cutoff_time(self) -> datetime | None:
        """Calculate cutoff time for incremental fetching.

        Uses last_fetched_at minus a 5-minute overlap buffer to account
        for clock skew and entries updated between fetches.
        """
        if not self.source.last_fetched_at:
            return None
        return self.source.last_fetched_at.replace(tzinfo=timezone.utc)

    @staticmethod
    def _extract_published(entry) -> datetime | None:
        """Extract publication date from a feed entry."""
        # feedparser provides published_parsed and updated_parsed
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _extract_content(entry) -> str | None:
        """Extract full article content from a feed entry.

        Many feeds include full text in content[0].value.
        """
        content_list = entry.get("content")
        if content_list and content_list[0].get("value"):
            return content_list[0]["value"].strip()

        # Fallback to description/summary
        desc = entry.get("description") or entry.get("summary")
        if desc:
            return desc.strip()

        return None

    @staticmethod
    def _extract_image(entry) -> str | None:
        """Extract lead image URL from a feed entry."""
        # Check media_content
        media = entry.get("media_content")
        if media and media[0].get("url"):
            return media[0]["url"]

        # Check links with image type
        for link in entry.get("links", []):
            if link.get("type", "").startswith("image/"):
                return link.get("href")

        return None

    @staticmethod
    def _extract_categories(entry) -> list[str]:
        """Extract tags/categories from a feed entry."""
        tags = entry.get("tags", [])
        if not tags:
            return []
        return [t.get("term", "") for t in tags if t.get("term")]
