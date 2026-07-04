"""Daily report generation using LLM."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analyzer.cost_tracker import CostTracker
from src.analyzer.llm_client import LLMClient
from src.analyzer.prompts import REPORT_SYSTEM_PROMPT, REPORT_USER_TEMPLATE
from src.models.ai_analysis import AIAnalysisScore
from src.models.article import Article
from src.models.daily_report import DailyReport
from src.reports.renderer import markdown_to_html

logger = structlog.get_logger(__name__)

# Number of top articles to include in the LLM context for report generation
TOP_ARTICLES_CONTEXT = 30


class ReportGenerator:
    """Generates daily news reports using LLM summarization."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.session = session
        self.llm_client = llm_client or LLMClient(cost_tracker=cost_tracker)
        self.cost_tracker = cost_tracker or self.llm_client.cost_tracker

    async def generate_for_date(
        self,
        report_date: date | None = None,
    ) -> DailyReport:
        """Generate (or regenerate) a daily report for the given date.

        Defaults to yesterday's date.
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        start = time.monotonic()

        # Gather data for the report date
        report_data = await self._gather_report_data(report_date)

        if not report_data["articles"]:
            logger.warning("No articles found for report", date=str(report_date))
            # Create a placeholder report
            return await self._create_empty_report(report_date)

        # Build the LLM prompt
        user_message = self._build_report_prompt(report_data, report_date)

        # Generate report via LLM
        response = await self.llm_client.generate_report(
            system_prompt=REPORT_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.4,
            max_tokens=4096,
        )

        duration = time.monotonic() - start

        # Render markdown to HTML
        html = markdown_to_html(response.content)

        # Build statistics
        articles = report_data["articles"]
        stats = {
            "total_fetched": report_data["total_fetched"],
            "analyzed": len(articles),
            "avg_score": round(report_data["avg_overall"], 3),
            "top_category": report_data["top_category"],
        }

        # Build top articles list
        top_articles = [
            {
                "id": str(a.id),
                "title": a.title,
                "analysis": {
                    "overall_score": a.analysis.overall_score,
                    "primary_category": a.analysis.primary_category,
                } if a.analysis else None,
            }
            for a in articles[:20]
        ]

        # Create or update the report
        report = DailyReport(
            report_date=report_date,
            title=f"Daily News Report — {report_date.isoformat()}",
            model_name=response.model_name,
            executive_summary=self._extract_executive_summary(response.content),
            report_markdown=response.content,
            report_html=html,
            top_articles=top_articles,
            category_breakdown=report_data["category_breakdown"],
            statistics=stats,
            articles_covered=len(articles),
            generation_duration_seconds=round(duration, 2),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost_usd=self.cost_tracker.total_cost_usd,
            status="published",
        )

        self.session.add(report)
        await self.session.flush()

        logger.info(
            "Daily report generated",
            date=str(report_date),
            articles=len(articles),
            duration_seconds=round(duration, 1),
            model=response.model_name,
        )

        return report

    async def _gather_report_data(self, report_date: date) -> dict:
        """Collect all data needed to generate a report for a given date."""
        start_dt = datetime(report_date.year, report_date.month, report_date.day, tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)

        # Get analyzed articles published on this date
        stmt = (
            select(Article)
            .join(AIAnalysisScore, Article.id == AIAnalysisScore.article_id)
            .where(
                Article.published_at >= start_dt,
                Article.published_at < end_dt,
                Article.is_duplicate_of.is_(None),
            )
            .order_by(AIAnalysisScore.overall_score.desc())
        )
        result = await self.session.execute(stmt)
        articles = list(result.unique().scalars().all())

        # Count total fetched articles (including unanalyzed)
        total_stmt = (
            select(func.count(Article.id))
            .where(
                Article.published_at >= start_dt,
                Article.published_at < end_dt,
            )
        )
        total_result = await self.session.execute(total_stmt)
        total_fetched = total_result.scalar() or 0

        # Calculate category breakdown
        category_breakdown: dict[str, int] = {}
        for article in articles:
            if article.analysis and article.analysis.primary_category:
                cat = article.analysis.primary_category
                category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

        top_category = (
            max(category_breakdown, key=category_breakdown.get)
            if category_breakdown
            else "N/A"
        )

        # Calculate average scores
        if articles:
            avg_overall = sum(
                a.analysis.overall_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
            avg_relevance = sum(
                a.analysis.relevance_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
            avg_credibility = sum(
                a.analysis.credibility_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
            avg_freshness = sum(
                a.analysis.freshness_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
            avg_novelty = sum(
                a.analysis.novelty_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
            avg_depth = sum(
                a.analysis.depth_score or 0 for a in articles if a.analysis
            ) / max(1, sum(1 for a in articles if a.analysis))
        else:
            avg_overall = avg_relevance = avg_credibility = 0.0
            avg_freshness = avg_novelty = avg_depth = 0.0

        # Build top articles text for the prompt
        top_articles_text = self._format_top_articles(articles[:TOP_ARTICLES_CONTEXT])

        # Build source stats
        source_counts: dict[str, int] = {}
        for article in articles:
            source_name = article.source.name if article.source else "Unknown"
            source_counts[source_name] = source_counts.get(source_name, 0) + 1
        source_stats_text = "\n".join(
            f"- {name}: {count} articles" for name, count in source_counts.items()
        )

        return {
            "articles": articles,
            "total_fetched": total_fetched,
            "category_breakdown": category_breakdown,
            "top_category": top_category,
            "avg_overall": avg_overall,
            "avg_relevance": avg_relevance,
            "avg_credibility": avg_credibility,
            "avg_freshness": avg_freshness,
            "avg_novelty": avg_novelty,
            "avg_depth": avg_depth,
            "top_articles_text": top_articles_text,
            "source_stats_text": source_stats_text,
        }

    def _build_report_prompt(self, data: dict, report_date: date) -> str:
        """Build the LLM prompt for report generation."""
        formatted_breakdown = "\n".join(
            f"- {cat}: {count} articles" for cat, count in data["category_breakdown"].items()
        ) or "No categories"

        return REPORT_USER_TEMPLATE.format(
            report_date=report_date.isoformat(),
            top_articles=data["top_articles_text"],
            category_breakdown=formatted_breakdown,
            source_stats=data["source_stats_text"],
            avg_relevance=data["avg_relevance"],
            avg_credibility=data["avg_credibility"],
            avg_freshness=data["avg_freshness"],
            avg_novelty=data["avg_novelty"],
            avg_depth=data["avg_depth"],
            avg_overall=data["avg_overall"],
            total_analyzed=len(data["articles"]),
        )

    @staticmethod
    def _format_top_articles(articles: list[Article]) -> str:
        """Format top articles as text for the LLM prompt."""
        lines = []
        for i, article in enumerate(articles, 1):
            title = article.title[:120]
            score = article.analysis.overall_score if article.analysis else "N/A"
            summary = article.analysis.ai_summary or article.summary or "No summary"
            summary = summary[:300]
            category = (
                article.analysis.primary_category if article.analysis else "N/A"
            )
            lines.append(
                f"{i}. [{title}]({article.url})\n"
                f"   Score: {score} | Category: {category}\n"
                f"   Summary: {summary}\n"
            )
        return "\n".join(lines) if lines else "No articles found for this date."

    @staticmethod
    def _extract_executive_summary(markdown: str) -> str | None:
        """Extract the executive summary paragraph from the generated markdown."""
        # Look for "Executive Summary" heading and the paragraph after it
        import re
        match = re.search(
            r"(?:Executive Summary|executive summary|## Executive)[:\s]*\n+(.*?)(?:\n##|\n#|\Z)",
            markdown,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        # Fallback: use the first non-heading paragraph
        for line in markdown.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 50:
                return stripped
        return None

    async def _create_empty_report(self, report_date: date) -> DailyReport:
        """Create a placeholder report when no articles are available."""
        empty_md = (
            f"# Daily News Report — {report_date.isoformat()}\n\n"
            "No articles were found for this date.\n"
        )
        report = DailyReport(
            report_date=report_date,
            title=f"Daily News Report — {report_date.isoformat()}",
            model_name="placeholder",
            executive_summary="No articles available for this date.",
            report_markdown=empty_md,
            report_html=markdown_to_html(empty_md),
            articles_covered=0,
            statistics={"total_fetched": 0, "analyzed": 0, "avg_score": 0},
            status="draft",
        )
        self.session.add(report)
        await self.session.flush()
        return report
