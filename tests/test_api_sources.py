"""Integration tests for the Sources API endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _setup_mock_scalars(mock_db_session, return_rows):
    """Setup the mock execute chain for source queries (.scalars().all())."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = return_rows
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db_session.execute.return_value = mock_result


class TestListSources:
    @pytest.mark.asyncio
    async def test_list_sources_empty(self, api_client, mock_db_session):
        _setup_mock_scalars(mock_db_session, [])
        response = await api_client.get("/api/sources")
        assert response.status_code == 200
        data = response.json()
        assert data["sources"] == []

    @pytest.mark.asyncio
    async def test_list_sources_filter_enabled(self, api_client, mock_db_session):
        _setup_mock_scalars(mock_db_session, [])
        response = await api_client.get("/api/sources?enabled_only=true")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_sources_invalid_bool(self, api_client, mock_db_session):
        """Invalid bool on enabled_only returns 422."""
        response = await api_client.get("/api/sources?enabled_only=notabool")
        assert response.status_code == 422


class TestAddSource:
    @pytest.mark.asyncio
    async def test_add_source_missing_required_fields(self, api_client, mock_db_session):
        response = await api_client.post("/api/sources", json={"name": "Test Source"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_add_source_minimal(self, api_client, mock_db_session):
        """Adding a valid source returns 201 with id."""
        response = await api_client.post("/api/sources", json={
            "name": "Hacker News",
            "feed_url": "https://hnrss.org/frontpage",
            "source_type": "rss",
        })
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == "Hacker News"

    @pytest.mark.asyncio
    async def test_add_source_invalid_type(self, api_client, mock_db_session):
        """Invalid source_type returns 400."""
        response = await api_client.post("/api/sources", json={
            "name": "Bad Source",
            "source_type": "invalid_type",
            "feed_url": "https://example.com/rss",
        })
        assert response.status_code == 400


class TestDeleteSource:
    @pytest.mark.asyncio
    async def test_delete_source_not_found(self, api_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await api_client.delete(f"/api/sources/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_source_success(self, api_client, mock_db_session):
        from src.models.source import Source

        source_id = uuid.uuid4()
        mock_source = MagicMock(spec=Source)
        mock_source.id = source_id
        mock_db_session.get = AsyncMock(return_value=mock_source)

        response = await api_client.delete(f"/api/sources/{source_id}")
        assert response.status_code == 204
