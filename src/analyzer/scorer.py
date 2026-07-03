"""Article scoring orchestrator — LLM analysis, JSON parsing, validation, caching."""

from __future__ import annotations

import json
import structlog
import re
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analyzer.cache import find_cached_analysis
from src.analyzer.cost_tracker import CostTracker
from src.analyzer.llm_client import LLMClient
from src.analyzer.prompts import ANALYSIS_SYSTEM_PROMPT, ANALYSIS_USER_TEMPLATE
from src.models.ai_analysis import AIAnalysisScore
from src.models.article import Article

logger = structlog.get_logger(__name__)

# Minimum content length (chars) to trigger LLM analysis.
# Articles shorter than this get auto-scored as low-quality without an API call.
MIN_CONTENT_LENGTH_FOR_LLM = 200

# Maximum content length sent to the LLM (chars). Truncation saves tokens.
MAX_CONTENT_LENGTH = 8000

# Default score for articles too short to analyze
AUTO_LOW_SCORE = 0.2


class ArticleScorer:
    """Analyzes articles using LLMs and persists scores to the database."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.session = session
        self.llm_client = llm_client or LLMClient(cost_tracker=cost_tracker)
        self.cost_tracker = cost_tracker or self.llm_client.cost_tracker

    async def analyze_article(self, article: Article) -> AIAnalysisScore:
        """Analyze a single article and return the score record.

        Handles: cache check, content-too-short skip, LLM call, JSON parse, and persistence.
        """
        # Check content length — skip LLM for very short articles
        if not article.content or len(article.content.strip()) < MIN_CONTENT_LENGTH_FOR_LLM:
            return await self._auto_score_low(article, "too_short")

        # Check analysis cache
        existing = await find_cached_analysis(self.session, article.content_hash)
        if existing:
            return await self._copy_cached_result(article, existing)

        # Run LLM analysis
        start = time.monotonic()
        system_prompt = ANALYSIS_SYSTEM_PROMPT
        user_message = self._build_user_message(article)

        response = await self.llm_client.analyze(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.1,
            max_tokens=8192,
        )

        duration = time.monotonic() - start

        # Parse and validate the JSON response
        data = self._parse_response(response.content)
        validated = self._validate_and_fix(data)

        # Build the score record
        score = AIAnalysisScore(
            article_id=article.id,
            model_name=response.model_name,
            model_provider=response.model_provider,
            **validated["scores"],
            ai_summary=validated.get("summary"),
            key_points=validated.get("key_points", []),
            sentiment=validated.get("sentiment"),
            primary_category=validated.get("primary_category"),
            secondary_categories=validated.get("secondary_categories", []),
            entities=validated.get("entities", {}),
            reading_level=validated.get("reading_level"),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost_usd=self.cost_tracker.total_cost_usd,
            content_hash_at_analysis=article.content_hash,
            raw_response={"content": response.content},
        )

        self.session.add(score)
        await self.session.flush()

        logger.info(
            "Article analyzed",
            article_id=str(article.id),
            title=article.title[:60],
            model=response.model_name,
            overall=validated["scores"].get("overall_score"),
            duration_ms=round(duration * 1000),
        )

        return score

    async def analyze_batch(
        self,
        articles: list[Article],
    ) -> list[AIAnalysisScore]:
        """Analyze a batch of articles sequentially.

        Returns a list of score records (some may be skipped/auto-scored).
        """
        results = []
        for article in articles:
            if self.cost_tracker.is_over_budget():
                logger.warning(
                    "Daily cost budget exceeded, stopping batch analysis",
                    daily_cost=self.cost_tracker.daily_cost_usd,
                )
                break

            try:
                score = await self.analyze_article(article)
                results.append(score)
            except Exception as exc:
                logger.error(
                    "Failed to analyze article, skipping",
                    article_id=str(article.id),
                    title=article.title[:60],
                    error=str(exc),
                )
                # Don't let one failed article block the batch
                continue

        return results

    async def get_pending_articles(self, limit: int = 50) -> list[Article]:
        """Get articles that haven't been analyzed yet."""
        subquery = select(AIAnalysisScore.article_id)
        stmt = (
            select(Article)
            .where(
                Article.id.not_in(subquery),
                Article.is_duplicate_of.is_(None),  # Skip known duplicates
            )
            .order_by(Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _auto_score_low(self, article: Article, reason: str) -> AIAnalysisScore:
        """Assign a low auto-score to articles that aren't worth LLM analysis."""
        score = AIAnalysisScore(
            article_id=article.id,
            model_name="auto-scorer",
            model_provider="local",
            relevance_score=AUTO_LOW_SCORE,
            credibility_score=AUTO_LOW_SCORE,
            freshness_score=AUTO_LOW_SCORE,
            novelty_score=AUTO_LOW_SCORE,
            depth_score=AUTO_LOW_SCORE,
            overall_score=AUTO_LOW_SCORE,
            ai_summary=article.summary or article.title,
            key_points=[],
            sentiment="neutral",
            primary_category="Other",
            secondary_categories=[],
            entities={},
            reading_level="basic",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            content_hash_at_analysis=article.content_hash,
            raw_response={"reason": reason},
        )
        self.session.add(score)
        await self.session.flush()
        return score

    async def _copy_cached_result(
        self,
        article: Article,
        cached: AIAnalysisScore,
    ) -> AIAnalysisScore:
        """Copy a cached analysis result for a new article with the same content hash."""
        score = AIAnalysisScore(
            article_id=article.id,
            model_name=cached.model_name,
            model_provider=cached.model_provider,
            relevance_score=cached.relevance_score,
            credibility_score=cached.credibility_score,
            freshness_score=cached.freshness_score,
            novelty_score=cached.novelty_score,
            depth_score=cached.depth_score,
            overall_score=cached.overall_score,
            ai_summary=cached.ai_summary,
            key_points=cached.key_points,
            sentiment=cached.sentiment,
            primary_category=cached.primary_category,
            secondary_categories=cached.secondary_categories,
            entities=cached.entities,
            reading_level=cached.reading_level,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            content_hash_at_analysis=article.content_hash,
            is_cached_result=True,
            raw_response={"cached_from": str(cached.article_id)},
        )
        self.session.add(score)
        await self.session.flush()
        return score

    def _build_user_message(self, article: Article) -> str:
        """Build the user message with article data for the LLM."""
        source_name = article.source.name if article.source else "Unknown"
        published = article.published_at.isoformat() if article.published_at else "Unknown"
        content = (article.content or article.summary or "")[:MAX_CONTENT_LENGTH]

        return ANALYSIS_USER_TEMPLATE.format(
            title=article.title,
            source_name=source_name,
            published_at=published,
            content=content,
        )

    def _parse_response(self, raw: str) -> dict:
        """Parse the LLM response as JSON, with error handling.

        Tries direct JSON parse, then regex extraction of JSON block.
        """
        # Remove markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try extracting JSON object with regex
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Failed to parse LLM response as JSON: {raw[:200]}")

    def _validate_and_fix(self, data: dict) -> dict:
        """Validate score ranges and structure, fixing minor issues."""
        scores = data.get("scores", {})

        # Validate and clamp score values to [0, 1]
        score_keys = ["relevance", "credibility", "freshness", "novelty", "depth", "overall"]
        for key in score_keys:
            if key in scores:
                val = scores[key]
                if isinstance(val, (int, float)):
                    scores[key] = max(0.0, min(1.0, float(val)))
                else:
                    scores[key] = 0.5  # Default if malformed

        # Map score keys to DB column names
        normalized_scores = {
            "relevance_score": scores.get("relevance"),
            "credibility_score": scores.get("credibility"),
            "freshness_score": scores.get("freshness"),
            "novelty_score": scores.get("novelty"),
            "depth_score": scores.get("depth"),
            "overall_score": scores.get("overall"),
            "rationale": scores.get("rationale"),
        }

        # Validate sentiment
        valid_sentiments = {"positive", "negative", "neutral", "mixed"}
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in valid_sentiments:
            sentiment = "neutral"

        return {
            "scores": normalized_scores,
            "summary": data.get("summary"),
            "key_points": data.get("key_points", []),
            "sentiment": sentiment,
            "primary_category": data.get("primary_category", "Other"),
            "secondary_categories": data.get("secondary_categories", []),
            "entities": data.get("entities", {}),
            "reading_level": data.get("reading_level", "intermediate"),
        }
