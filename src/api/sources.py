"""Source management CRUD API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.source import Source

router = APIRouter()


class SourceCreate(BaseModel):
    name: str
    source_type: str  # rss, web_api, web_scrape
    feed_url: str | None = None
    base_url: str | None = None
    config: dict = {}
    fetch_interval_minutes: int = 30
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60


class SourceUpdate(BaseModel):
    name: str | None = None
    feed_url: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    fetch_interval_minutes: int | None = None
    rate_limit_requests: int | None = None
    rate_limit_window_seconds: int | None = None


@router.get("")
async def list_sources(
    enabled_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """列出所有已配置的新闻源。"""
    stmt = select(Source)
    if enabled_only:
        stmt = stmt.where(Source.enabled.is_(True))
    stmt = stmt.order_by(Source.name)

    result = await session.execute(stmt)
    sources = result.scalars().all()

    return {
        "sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "source_type": s.source_type,
                "feed_url": s.feed_url,
                "enabled": s.enabled,
                "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
                "last_error_at": s.last_error_at.isoformat() if s.last_error_at else None,
                "last_error_message": s.last_error_message,
                "consecutive_failures": s.consecutive_failures,
                "config": s.config,
            }
            for s in sources
        ]
    }


@router.post("", status_code=201)
async def create_source(
    data: SourceCreate,
    session: AsyncSession = Depends(get_session),
):
    """添加一个新的新闻源。"""
    valid_types = {"rss", "web_api", "web_scrape"}
    if data.source_type not in valid_types:
        raise HTTPException(400, f"source_type must be one of: {valid_types}")

    source = Source(
        name=data.name,
        source_type=data.source_type,
        feed_url=data.feed_url,
        base_url=data.base_url,
        config=data.config,
        fetch_interval_minutes=data.fetch_interval_minutes,
        rate_limit_requests=data.rate_limit_requests,
        rate_limit_window_seconds=data.rate_limit_window_seconds,
    )
    session.add(source)
    await session.flush()

    return {"id": str(source.id), "name": source.name, "source_type": source.source_type}


@router.get("/{source_id}")
async def get_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
):
    """查看单个新闻源的详情。"""
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")

    return {
        "id": str(source.id),
        "name": source.name,
        "source_type": source.source_type,
        "feed_url": source.feed_url,
        "base_url": source.base_url,
        "config": source.config,
        "enabled": source.enabled,
        "fetch_interval_minutes": source.fetch_interval_minutes,
        "rate_limit_requests": source.rate_limit_requests,
        "rate_limit_window_seconds": source.rate_limit_window_seconds,
        "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
        "last_error_at": source.last_error_at.isoformat() if source.last_error_at else None,
        "last_error_message": source.last_error_message,
        "consecutive_failures": source.consecutive_failures,
        "created_at": source.created_at.isoformat(),
    }


@router.put("/{source_id}")
async def update_source(
    source_id: str,
    data: SourceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """更新新闻源的配置。"""
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")

    if data.name is not None:
        source.name = data.name
    if data.feed_url is not None:
        source.feed_url = data.feed_url
    if data.config is not None:
        source.config = data.config
    if data.enabled is not None:
        source.enabled = data.enabled
    if data.fetch_interval_minutes is not None:
        source.fetch_interval_minutes = data.fetch_interval_minutes
    if data.rate_limit_requests is not None:
        source.rate_limit_requests = data.rate_limit_requests
    if data.rate_limit_window_seconds is not None:
        source.rate_limit_window_seconds = data.rate_limit_window_seconds

    await session.flush()
    return {"id": str(source.id), "name": source.name, "updated": True}


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
):
    """删除新闻源及其所有文章。"""
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")

    await session.delete(source)
    await session.flush()


@router.post("/fetch")
async def trigger_fetch_all():
    """手动触发抓取所有已启用的新闻源。"""
    from src.scheduler.tasks import fetch_all_sources
    result = await fetch_all_sources()
    return result


@router.post("/{source_id}/fetch")
async def trigger_fetch_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
):
    """手动触发抓取指定的新闻源。"""
    import traceback

    import httpx

    from src.fetchers.rate_limiter import RateLimiter
    from src.fetchers.rss_fetcher import RSSFetcher

    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")

    try:
        limiter = RateLimiter(
            max_requests=source.rate_limit_requests,
            window_seconds=source.rate_limit_window_seconds,
        )
        async with httpx.AsyncClient(timeout=30) as client:
            fetcher = RSSFetcher(source, session, limiter, client)
            added = await fetcher.run()
            await session.commit()
        return {"message": f"抓取完成，新增 {added} 篇文章", "added": added}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
