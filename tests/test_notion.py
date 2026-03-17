from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from muse.publisher.notion import NotionPublisher


@pytest.fixture
def publisher():
    return NotionPublisher(
        api_key="ntn_test",
        ideas_database_id="db-123",
    )


def _make_idea(title="Test Idea", status="pending"):
    """Create a mock Idea ORM object."""
    idea = MagicMock()
    idea.id = uuid4()
    idea.title = title
    idea.one_liner = "A short description"
    idea.target_users = "Developers"
    idea.pain_point = "Slow workflows"
    idea.differentiation = "AI-powered"
    idea.channels = ["GitHub Marketplace"]
    idea.revenue_model = "freemium"
    idea.key_resources = "AI expertise"
    idea.cost_estimate = "Low"
    idea.validation_method = "MVP launch"
    idea.difficulty = 3
    idea.status = status
    return idea


def test_notion_skips_when_no_api_key():
    pub = NotionPublisher(api_key="", ideas_database_id="db-123")
    assert not pub.is_configured()


def test_notion_is_configured(publisher):
    assert publisher.is_configured()


@pytest.mark.asyncio
async def test_health_check(publisher):
    with patch("notion_client.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.databases.retrieve = AsyncMock(
            return_value={"id": "db-123", "title": [{"plain_text": "Ideas"}]}
        )
        mock_cls.return_value = mock_client

        result = await publisher.health_check()
        assert result is True
        mock_client.databases.retrieve.assert_called_once_with(database_id="db-123")


@pytest.mark.asyncio
async def test_push_ideas_creates_pages(publisher):
    idea = _make_idea()
    mock_page = {"id": "page-abc-123"}

    with patch("notion_client.AsyncClient") as MockClient:
        client = AsyncMock()
        client.pages.create = AsyncMock(return_value=mock_page)
        MockClient.return_value = client

        pushed = await publisher.push_ideas([idea])

        assert len(pushed) == 1
        assert pushed[0] == (idea.id, "page-abc-123")
        client.pages.create.assert_called_once()
        call_kwargs = client.pages.create.call_args[1]
        assert call_kwargs["parent"] == {"database_id": "db-123"}
        props = call_kwargs["properties"]
        assert props["Name"]["title"][0]["text"]["content"] == idea.title
        assert props["Difficulty"]["number"] == 3
        assert props["Status"]["select"]["name"] == "pending"


@pytest.mark.asyncio
async def test_push_ideas_handles_partial_failure(publisher):
    idea1 = _make_idea("Good Idea")
    idea2 = _make_idea("Bad Idea")

    with patch("notion_client.AsyncClient") as MockClient:
        client = AsyncMock()
        client.pages.create = AsyncMock(
            side_effect=[{"id": "page-1"}, Exception("API error")]
        )
        MockClient.return_value = client

        pushed = await publisher.push_ideas([idea1, idea2])

        assert len(pushed) == 1
        assert pushed[0] == (idea1.id, "page-1")


@pytest.mark.asyncio
async def test_push_ideas_skips_when_not_configured():
    pub = NotionPublisher(api_key="", ideas_database_id="")
    pushed = await pub.push_ideas([_make_idea()])
    assert pushed == []


@pytest.mark.asyncio
async def test_pull_status_updates(publisher):
    mock_response = {
        "results": [
            {
                "id": "page-1",
                "properties": {"Status": {"select": {"name": "promising"}}},
                "last_edited_time": "2026-03-15T10:00:00.000Z",
            },
            {
                "id": "page-2",
                "properties": {"Status": {"select": {"name": "validated"}}},
                "last_edited_time": "2026-03-16T08:30:00.000Z",
            },
        ]
    }

    with patch("notion_client.AsyncClient") as MockClient:
        client = AsyncMock()
        client.databases.query = AsyncMock(return_value=mock_response)
        MockClient.return_value = client

        updates = await publisher.pull_status_updates()

        assert len(updates) == 2
        assert updates[0] == (
            "page-1",
            "promising",
            datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        )
        assert updates[1][1] == "validated"


@pytest.mark.asyncio
async def test_pull_skips_pages_without_status_select(publisher):
    mock_response = {
        "results": [
            {
                "id": "page-no-status",
                "properties": {"Status": {}},
                "last_edited_time": "2026-03-15T10:00:00.000Z",
            },
        ]
    }

    with patch("notion_client.AsyncClient") as MockClient:
        client = AsyncMock()
        client.databases.query = AsyncMock(return_value=mock_response)
        MockClient.return_value = client

        updates = await publisher.pull_status_updates()
        assert len(updates) == 0


@pytest.mark.asyncio
async def test_pull_status_updates_handles_api_error(publisher):
    with patch("notion_client.AsyncClient") as MockClient:
        client = AsyncMock()
        client.databases.query = AsyncMock(side_effect=Exception("Network error"))
        MockClient.return_value = client

        updates = await publisher.pull_status_updates()
        assert updates == []
