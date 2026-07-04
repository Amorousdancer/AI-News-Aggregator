"""Shared test fixtures and API testing utilities."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def sample_rss_entry():
    """A mock RSS feed entry."""
    return {
        "title": "Test Article Title",
        "link": "https://example.com/article/1",
        "summary": "This is a test article summary.",
        "author": "Test Author",
        "published_parsed": (2026, 6, 10, 12, 0, 0, 3, 161, 0),
        "tags": [{"term": "Technology"}, {"term": "AI"}],
    }


@pytest.fixture
def sample_article_candidate():
    """A mock article candidate."""
    from src.dedup.pipeline import ArticleCandidate
    return ArticleCandidate(
        title="Test Article Title",
        url="https://example.com/article/1",
        content="This is the full content of the test article. It has enough text.",
        summary="This is a test article summary.",
        author="Test Author",
        published_at="2026-06-10T12:00:00+00:00",
        language="en",
        categories=["Technology", "AI"],
    )


@pytest.fixture
def sample_llm_response():
    """A mock LLM analysis response."""
    return {
        "scores": {
            "relevance": 0.85,
            "credibility": 0.90,
            "freshness": 0.80,
            "novelty": 0.70,
            "depth": 0.75,
            "overall": 0.81,
            "rationale": "Well-sourced tech news with original analysis.",
        },
        "summary": "A comprehensive test article about technology trends.",
        "key_points": ["Key finding 1", "Key finding 2", "Key finding 3"],
        "sentiment": "positive",
        "primary_category": "Technology",
        "secondary_categories": ["AI/ML"],
        "entities": {
            "people": ["Jane Doe"],
            "organizations": ["Acme Corp"],
            "locations": ["San Francisco"],
        },
        "reading_level": "intermediate",
    }


@pytest.fixture
def sample_article_id():
    return uuid.uuid4()


@pytest.fixture
def sample_source_id():
    return uuid.uuid4()


# --- API test fixtures ---

@pytest.fixture
def mock_db_session():
    """Create a mock AsyncSession for API testing."""
    session = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest_asyncio.fixture
async def test_app(mock_db_session):
    """Create a FastAPI test app with mocked database dependency (no scheduler)."""
    from fastapi import FastAPI

    from src.api.router import api_router
    from src.database import get_session

    app = FastAPI()

    @app.get("/")
    async def root():
        return {"name": "test"}

    app.include_router(api_router)

    async def override_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest_asyncio.fixture
async def api_client(test_app):
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
