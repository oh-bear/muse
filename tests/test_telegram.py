import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from muse.publisher.telegram import TelegramPublisher


@pytest.fixture
def publisher():
    return TelegramPublisher(bot_token="123:abc", chat_id="-100123")


@pytest.fixture
def mock_bot():
    """Mock the Bot class to handle context manager protocol."""
    bot_instance = AsyncMock()
    bot_instance.send_message = AsyncMock()
    bot_instance.__aenter__ = AsyncMock(return_value=bot_instance)
    bot_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.publisher.telegram.Bot", return_value=bot_instance) as mock_cls:
        yield bot_instance


@pytest.mark.asyncio
async def test_send_daily_summary(publisher, mock_bot):
    signals = [
        {"entry_id": 1, "score": 5, "tags": ["ai"], "summary": "Amazing AI tool", "reason": "Strong signal"},
        {"entry_id": 2, "score": 4, "tags": ["saas"], "summary": "New SaaS thing", "reason": "Good timing"},
        {"entry_id": 3, "score": 3, "tags": ["dev"], "summary": "Dev tool", "reason": "Decent"},
        {"entry_id": 4, "score": 4, "tags": ["ai"], "summary": "Another AI", "reason": "Promising"},
    ]

    await publisher.send_daily_summary(signals, total_processed=100)

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "100" in message
    assert "4" in message
    assert "Amazing AI tool" in message


@pytest.mark.asyncio
async def test_send_alert(publisher, mock_bot):
    await publisher.send_alert("AI API is down")

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "AI API is down" in message


@pytest.mark.asyncio
async def test_send_weekly_brief(publisher, mock_bot):
    opportunities = [
        {
            "title": "AI Code Review Gap",
            "description": "Multiple signals show demand",
            "trend_category": "developer-tools",
            "unmet_need": "Automated logic review",
            "market_gap": "No indie solution",
            "confidence": "high",
        },
        {
            "title": "SEA SaaS Localization",
            "description": "EN tools missing in SEA",
            "trend_category": "saas",
            "unmet_need": "Local payment integration",
            "market_gap": "No localized version",
            "confidence": "medium",
        },
    ]

    await publisher.send_weekly_brief(
        opportunities=opportunities,
        weekly_summary="AI tools and localization dominated this week.",
        signal_count=35,
        week_label="2026-W12",
    )

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "2026-W12" in message
    assert "AI Code Review Gap" in message
    assert "35" in message


@pytest.mark.asyncio
async def test_send_monthly_ideas(publisher, mock_bot):
    ideas = [
        {"title": "CodeReview.ai", "one_liner": "AI code review", "revenue_model": "freemium", "difficulty": 3},
        {"title": "LocalPay SEA", "one_liner": "Payment integration", "revenue_model": "marketplace", "difficulty": 4},
    ]

    await publisher.send_monthly_ideas(
        ideas=ideas,
        monthly_summary="AI tools dominated this month.",
        opportunity_count=5,
        month_label="2026-03",
    )

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "2026-03" in message
    assert "CodeReview.ai" in message
    assert "5" in message


@pytest.mark.asyncio
async def test_send_daily_summary_empty_signals(publisher, mock_bot):
    await publisher.send_daily_summary([], total_processed=50)

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "0" in message
