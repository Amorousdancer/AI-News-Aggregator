"""Main API router — aggregates all sub-routers."""

from fastapi import APIRouter

from src.api.articles import router as articles_router
from src.api.health import router as health_router
from src.api.reports import router as reports_router
from src.api.sources import router as sources_router

api_router = APIRouter(prefix="/api")
api_router.include_router(sources_router, prefix="/sources", tags=["新闻源管理"])
api_router.include_router(articles_router, prefix="/articles", tags=["文章"])
api_router.include_router(reports_router, prefix="/reports", tags=["每日报告"])
api_router.include_router(health_router, tags=["系统状态"])
