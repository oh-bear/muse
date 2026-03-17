import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.config import FocusConfig, Settings


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        miniflux_url="http://localhost:8080",
        miniflux_api_key="test",
        ai_provider="claude",
        anthropic_api_key="sk-test",
        telegram_bot_token="123:abc",
        telegram_chat_id="-100test",
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="bot@test.com",
        smtp_password="secret",
        email_recipients="user@test.com",
    )


@pytest.fixture
def focus():
    return FocusConfig(
        focus_areas=["ai-tools"],
        exclude=["crypto"],
        score_threshold=3,
        indie_criteria={"max_team_size": 5},
    )


@pytest.mark.asyncio
async def test_extract_opportunities_job_queries_week_signals(settings, focus):
    """Verify the job fetches signals from the past week and calls AI."""
    from muse.scheduler import extract_opportunities_job

    mock_signal = MagicMock()
    mock_signal.id = uuid.uuid4()
    mock_signal.title = "AI Tool"
    mock_signal.ai_summary = "Summary"
    mock_signal.ai_tags = ["ai"]
    mock_signal.ai_score = 4
    mock_signal.source = "producthunt"

    # Mock session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_signal]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("muse.scheduler.OpportunityExtractor") as mock_extractor_cls,
        patch("muse.scheduler.TelegramPublisher") as mock_tg_cls,
        patch("muse.scheduler.EmailPublisher") as mock_email_cls,
    ):
        mock_extractor = AsyncMock()
        mock_extractor.extract.return_value = MagicMock(
            opportunities=[
                {
                    "title": "Test Opp",
                    "description": "desc",
                    "trend_category": "ai",
                    "unmet_need": "need",
                    "market_gap": "gap",
                    "geo_opportunity": "",
                    "evidence_ids": [1],
                    "confidence": "high",
                }
            ],
            weekly_summary="Summary",
            failed=False,
        )
        mock_extractor_cls.return_value = mock_extractor

        mock_tg = AsyncMock()
        mock_tg_cls.return_value = mock_tg

        mock_email = AsyncMock()
        mock_email_cls.return_value = mock_email

        await extract_opportunities_job(settings, focus, mock_session_factory)

        # Verify AI was called
        mock_extractor.extract.assert_called_once()

        # Verify opportunity was stored
        mock_session.add.assert_called()

        # Verify push
        mock_tg.send_weekly_brief.assert_called_once()
        mock_email.send_weekly_digest.assert_called_once()
