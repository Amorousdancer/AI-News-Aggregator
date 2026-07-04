"""每日报告 API。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.daily_report import DailyReport

router = APIRouter()


@router.get("")
async def list_reports(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """列出所有每日报告，最新的在前。"""
    from sqlalchemy import func

    stmt = select(DailyReport).order_by(DailyReport.report_date.desc())
    count_stmt = select(func.count(DailyReport.id))

    result = await session.execute(stmt.offset((page - 1) * per_page).limit(per_page))
    reports = result.scalars().all()

    total = await session.scalar(count_stmt) or 0

    return {
        "reports": [
            {
                "id": str(r.id),
                "report_date": r.report_date.isoformat() if r.report_date else None,
                "title": r.title,
                "articles_covered": r.articles_covered,
                "status": r.status,
                "generated_at": r.generated_at.isoformat(),
                "statistics": r.statistics,
            }
            for r in reports
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
        },
    }


@router.get("/{report_date}")
async def get_report(
    report_date: str,  # ISO format: YYYY-MM-DD
    session: AsyncSession = Depends(get_session),
):
    """按日期查看指定的每日报告。"""
    try:
        parsed_date = date.fromisoformat(report_date)
    except ValueError as err:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.") from err

    stmt = select(DailyReport).where(DailyReport.report_date == parsed_date)
    result = await session.execute(stmt)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(404, f"No report found for {report_date}")

    return {
        "id": str(report.id),
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "title": report.title,
        "executive_summary": report.executive_summary,
        "report_markdown": report.report_markdown,
        "report_html": report.report_html,
        "top_articles": report.top_articles,
        "category_breakdown": report.category_breakdown,
        "statistics": report.statistics,
        "articles_covered": report.articles_covered,
        "generation_duration_seconds": report.generation_duration_seconds,
        "estimated_cost_usd": report.estimated_cost_usd,
        "status": report.status,
        "generated_at": report.generated_at.isoformat(),
    }


@router.get("/{report_date}/html", response_class=HTMLResponse)
async def get_report_html(
    report_date: str,
    session: AsyncSession = Depends(get_session),
):
    """以网页形式查看指定日期的每日报告。"""
    try:
        parsed_date = date.fromisoformat(report_date)
    except ValueError as err:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.") from err

    stmt = select(DailyReport).where(DailyReport.report_date == parsed_date)
    result = await session.execute(stmt)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(404, f"No report found for {report_date}")

    if report.report_html:
        return HTMLResponse(content=report.report_html)

    # Render markdown to HTML on the fly if not pre-rendered
    from src.reports.renderer import markdown_to_html
    html = markdown_to_html(report.report_markdown)
    return HTMLResponse(content=html)
