"""文章列表和搜索 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.ai_analysis import AIAnalysisScore
from src.models.article import Article

router = APIRouter()


@router.post("/analyze")
async def trigger_analyze():
    """手动触发 AI 分析所有待处理的文章。"""
    from src.scheduler.tasks import analyze_pending_articles
    result = await analyze_pending_articles()
    return result


@router.get("")
async def list_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    source_id: str | None = None,
    category: str | None = None,
    min_score: float | None = None,
    language: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """列出文章，支持筛选、分页和搜索。"""
    # Build base query with optional analysis join
    stmt = select(Article).outerjoin(AIAnalysisScore)

    # Apply filters
    if source_id:
        stmt = stmt.where(Article.source_id == source_id)
    if language:
        stmt = stmt.where(Article.language == language)
    if min_score is not None:
        stmt = stmt.where(AIAnalysisScore.overall_score >= min_score)
    if category:
        stmt = stmt.where(AIAnalysisScore.primary_category == category)
    if search:
        # Basic ILIKE search on title
        stmt = stmt.where(Article.title.ilike(f"%{search}%"))

    # Exclude known duplicates
    stmt = stmt.where(Article.is_duplicate_of.is_(None))

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    # Order and paginate
    stmt = stmt.order_by(Article.published_at.desc().nulls_last())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(stmt)
    articles = result.unique().scalars().all()

    return {
        "articles": [
            {
                "id": str(a.id),
                "title": a.title,
                "url": a.url,
                "summary": a.summary,
                "author": a.author,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "language": a.language,
                "image_url": a.image_url,
                "categories": a.categories,
                "source": {"id": str(a.source.id), "name": a.source.name} if a.source else None,
                "analysis": {
                    "overall_score": a.analysis.overall_score,
                    "ai_summary": a.analysis.ai_summary,
                    "primary_category": a.analysis.primary_category,
                    "sentiment": a.analysis.sentiment,
                    "key_points": a.analysis.key_points,
                } if a.analysis else None,
            }
            for a in articles
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/{article_id}")
async def get_article(
    article_id: str,
    session: AsyncSession = Depends(get_session),
):
    """查看单篇文章的完整详情和 AI 分析结果。"""
    from fastapi import HTTPException

    article = await session.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Article not found")

    return {
        "id": str(article.id),
        "title": article.title,
        "url": article.url,
        "canonical_url": article.canonical_url,
        "content": article.content,
        "summary": article.summary,
        "author": article.author,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat(),
        "language": article.language,
        "image_url": article.image_url,
        "categories": article.categories,
        "metadata": article.extra_metadata,
        "is_duplicate_of": str(article.is_duplicate_of) if article.is_duplicate_of else None,
        "source": {
            "id": str(article.source.id),
            "name": article.source.name,
        } if article.source else None,
        "analysis": _serialize_analysis(article.analysis) if article.analysis else None,
    }


def _serialize_analysis(analysis: AIAnalysisScore) -> dict:
    return {
        "id": str(analysis.id),
        "model_name": analysis.model_name,
        "model_provider": analysis.model_provider,
        "scores": {
            "relevance": analysis.relevance_score,
            "credibility": analysis.credibility_score,
            "freshness": analysis.freshness_score,
            "novelty": analysis.novelty_score,
            "depth": analysis.depth_score,
            "overall": analysis.overall_score,
        },
        "ai_summary": analysis.ai_summary,
        "key_points": analysis.key_points,
        "sentiment": analysis.sentiment,
        "primary_category": analysis.primary_category,
        "secondary_categories": analysis.secondary_categories,
        "entities": analysis.entities,
        "reading_level": analysis.reading_level,
        "is_cached_result": analysis.is_cached_result,
    }
