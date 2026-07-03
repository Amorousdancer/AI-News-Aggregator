"""Integration tests for the Articles API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def _setup_mock_execute(mock_db_session, return_rows, total_count=0):
    """Setup the mock execute chain for article queries (with .unique().scalars().all())."""
    mock_unique = MagicMock()
    mock_unique.scalars.return_value = mock_unique
    mock_unique.all.return_value = return_rows
    mock_result = MagicMock()
    mock_result.unique.return_value = mock_unique
    mock_db_session.execute.return_value = mock_result
    mock_db_session.scalar.return_value = total_count


class TestArticlesList:
    @pytest.mark.asyncio
    async def test_list_articles_empty(self, api_client, mock_db_session):
        _setup_mock_execute(mock_db_session, [], 0)
        response = await api_client.get("/api/articles")
        assert response.status_code == 200
        data = response.json()
        assert data["articles"] == []
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_articles_with_pagination(self, api_client, mock_db_session):
        _setup_mock_execute(mock_db_session, [], 42)
        response = await api_client.get("/api/articles?page=2&per_page=10")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["per_page"] == 10
        assert data["pagination"]["total"] == 42

    @pytest.mark.asyncio
    async def test_list_articles_invalid_page_clamped(self, api_client, mock_db_session):
        response = await api_client.get("/api/articles?page=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_articles_per_page_limit(self, api_client, mock_db_session):
        response = await api_client.get("/api/articles?per_page=200")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_articles_filter_by_language(self, api_client, mock_db_session):
        _setup_mock_execute(mock_db_session, [], 5)
        response = await api_client.get("/api/articles?language=zh")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_articles_filter_by_source(self, api_client, mock_db_session):
        _setup_mock_execute(mock_db_session, [], 3)
        response = await api_client.get("/api/articles?source_id=f47ac10b-58cc-4372-a567-0e02b2c3d479")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_articles_search(self, api_client, mock_db_session):
        _setup_mock_execute(mock_db_session, [], 1)
        response = await api_client.get("/api/articles?search=AI")
        assert response.status_code == 200


class TestGetArticle:
    @pytest.mark.asyncio
    async def test_get_article_not_found(self, api_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await api_client.get("/api/articles/f47ac10b-58cc-4372-a567-0e02b2c3d479")
        assert response.status_code == 404
