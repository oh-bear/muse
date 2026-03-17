import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

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
async def test_generate_ideas_job_full_flow(settings, focus):
    """Verify the job fetches opportunities, calls AI, stores ideas, and pushes."""
    from muse.scheduler import generate_ideas_job

    mock_opp = MagicMock()
    mock_opp.id = uuid.uuid4()
    mock_opp.title = "AI Code Review Gap"
    mock_opp.description = "Multiple signals"
    mock_opp.trend_category = "developer-tools"
    mock_opp.unmet_need = "Logic review"
    mock_opp.market_gap = "No indie solution"
    mock_opp.geo_opportunity = ""
    mock_opp.confidence = "high"
    mock_opp.created_at = datetime.now(timezone.utc)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_opp]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.scheduler.IdeaGenerator") as mock_gen_cls, \
         patch("muse.scheduler.TelegramPublisher") as mock_tg_cls, \
         patch("muse.scheduler.EmailPublisher") as mock_email_cls:

        mock_gen = AsyncMock()
        mock_gen.generate.return_value = MagicMock(
            ideas=[{
                "title": "CodeReview.ai",
                "one_liner": "AI code review",
                "target_users": "Dev teams",
                "pain_point": "Slow review",
                "differentiation": "Logic focus",
                "channels": ["GitHub"],
                "revenue_model": "freemium",
                "key_resources": "AI",
                "cost_estimate": "Low",
                "validation_method": "MVP",
                "difficulty": 3,
                "source_opportunity_id": str(mock_opp.id),
            }],
            monthly_summary="AI dominated.",
            failed=False,
        )
        mock_gen_cls.return_value = mock_gen

        mock_tg = AsyncMock()
        mock_tg_cls.return_value = mock_tg

        mock_email = AsyncMock()
        mock_email_cls.return_value = mock_email

        await generate_ideas_job(settings, focus, mock_session_factory)

        mock_gen.generate.assert_called_once()
        mock_session.add.assert_called()
        mock_tg.send_monthly_ideas.assert_called_once()
        mock_email.send_monthly_ideas.assert_called_once()
