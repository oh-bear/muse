import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from muse.publisher.notion import NotionPublisher


@pytest.fixture
def publisher():
    return NotionPublisher(
        api_key="ntn_test",
        ideas_database_id="db-123",
    )


def test_notion_skips_when_no_api_key():
    pub = NotionPublisher(api_key="", ideas_database_id="db-123")
    assert not pub.is_configured()


def test_notion_is_configured(publisher):
    assert publisher.is_configured()


@pytest.mark.asyncio
async def test_health_check(publisher):
    with patch("notion_client.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.databases.retrieve = AsyncMock(return_value={"id": "db-123", "title": [{"plain_text": "Ideas"}]})
        mock_cls.return_value = mock_client

        result = await publisher.health_check()
        assert result is True
        mock_client.databases.retrieve.assert_called_once_with(database_id="db-123")
