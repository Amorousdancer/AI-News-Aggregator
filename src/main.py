"""FastAPI application entry point.

Starts the API server and the background scheduler.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.config import settings
from src.scheduler.scheduler import get_scheduler_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global scheduler manager singleton
scheduler_manager = get_scheduler_manager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI application."""
    # Startup
    logger.info("Starting AI News Aggregator")
    scheduler_manager.start()
    logger.info("Application started successfully")
    yield
    # Shutdown
    logger.info("Shutting down AI News Aggregator")
    scheduler_manager.shutdown(wait=True)
    logger.info("Application shut down")


app = FastAPI(
    title="AI 新闻聚合器",
    description="AI 驱动的新闻聚合、分析和每日报告生成系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — allows all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """首页 — 跳转到 API 文档。"""
    return {
        "name": "AI News Aggregator",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
