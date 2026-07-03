"""Three-tier deduplication pipeline orchestrator.

Tier 1: Exact URL match (after normalization)
Tier 2: Content hash match (SHA-256 of normalized title + first 1000 chars)
Tier 3: SimHash near-duplicate detection (Hamming distance < 3)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dedup.content_hash import compute_content_hash
from src.dedup.normalizer import normalize_url
from src.dedup.simhash import compute_simhash, hamming_distance
from src.models.article import Article


@dataclass
class DedupResult:
    """Result of deduplication check."""

    is_new: bool
    url: str
    content_hash: str
    simhash: str | None = None
    duplicate_of_id: uuid.UUID | None = None
    duplicate_of_url: str | None = None
    match_tier: int | None = None  # 1=URL, 2=content_hash, 3=simhash


@dataclass
class ArticleCandidate:
    """A candidate article before deduplication and insertion."""

    title: str
    url: str
    content: str | None = None
    summary: str | None = None
    author: str | None = None
    published_at: str | None = None  # ISO format string
    language: str = "en"
    image_url: str | None = None
    categories: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source_id: uuid.UUID | None = None


class DedupPipeline:
    """Orchestrates the three-tier deduplication process."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check(self, candidate: ArticleCandidate) -> DedupResult:
        """Run the candidate through all three dedup tiers.

        Returns a DedupResult indicating whether the article is new and, if not,
        which existing article it duplicates.
        """
        # Tier 1: Normalize URL and check for exact match
        canonical_url = normalize_url(candidate.url)

        result = await self._check_url(canonical_url)
        if result is not None:
            return result

        # Tier 2: Compute content hash and check
        content_hash = compute_content_hash(candidate.title, candidate.content)

        result = await self._check_content_hash(content_hash)
        if result is not None:
            return result

        # Tier 3: Compute SimHash and check for near-duplicates
        simhash = compute_simhash(candidate.title, candidate.content)
        result = await self._check_simhash(simhash)
        if result is not None:
            return result

        # All three tiers passed — this is a new article
        return DedupResult(
            is_new=True,
            url=canonical_url,
            content_hash=content_hash,
            simhash=simhash,
        )

    async def _check_url(self, canonical_url: str) -> DedupResult | None:
        """Tier 1: Check for exact URL match."""
        stmt = select(Article).where(Article.url == canonical_url).limit(1)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            return DedupResult(
                is_new=False,
                url=canonical_url,
                content_hash="",
                duplicate_of_id=existing.id,
                duplicate_of_url=existing.url,
                match_tier=1,
            )
        return None

    async def _check_content_hash(self, content_hash: str) -> DedupResult | None:
        """Tier 2: Check for content hash match."""
        stmt = (
            select(Article)
            .where(Article.content_hash == content_hash)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            return DedupResult(
                is_new=False,
                url="",
                content_hash=content_hash,
                duplicate_of_id=existing.id,
                duplicate_of_url=existing.url,
                match_tier=2,
            )
        return None

    async def _check_simhash(self, simhash: str) -> DedupResult | None:
        """Tier 3: Check for SimHash near-duplicate matches.

        Queries for all articles with a simhash, then computes Hamming distance.
        For efficiency, we use a rough SQL LIKE prefix match as a pre-filter
        (articles with the same first 4 hex chars are candidates).
        """
        prefix = simhash[:4]

        stmt = select(Article).where(Article.simhash.like(f"{prefix}%")).limit(50)
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()

        for existing in candidates:
            if existing.simhash and hamming_distance(simhash, existing.simhash) < 3:
                return DedupResult(
                    is_new=False,
                    url="",
                    content_hash="",
                    simhash=simhash,
                    duplicate_of_id=existing.id,
                    duplicate_of_url=existing.url,
                    match_tier=3,
                )

        return None
