import pytest
from unittest.mock import AsyncMock, patch

from muse.publisher.email import EmailPublisher


@pytest.fixture
def publisher():
    return EmailPublisher(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="bot@example.com",
        smtp_password="secret",
        recipients=["user1@example.com", "user2@example.com"],
    )


@pytest.mark.asyncio
async def test_send_weekly_digest(publisher):
    opportunities = [
        {
            "title": "AI Code Review Gap",
            "description": "Multiple signals show demand",
            "trend_category": "developer-tools",
            "unmet_need": "Automated logic review",
            "market_gap": "No indie solution",
            "geo_opportunity": "Missing in CN market",
            "confidence": "high",
        },
    ]

    with patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await publisher.send_weekly_digest(
            opportunities=opportunities,
            weekly_summary="AI tools dominated this week.",
            signal_count=42,
            week_label="2026-W12",
        )

        mock_smtp.send.assert_called_once()
        call_args = mock_smtp.send.call_args
        message = call_args[0][0]  # first positional arg is the message
        assert "AI Code Review Gap" in message.get_body(preferencelist=("html",)).get_content()
        assert len(message["To"].split(", ")) == 2


@pytest.mark.asyncio
async def test_send_skips_when_no_host(publisher):
    publisher.smtp_host = ""

    with patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await publisher.send_weekly_digest(
            opportunities=[],
            weekly_summary="",
            signal_count=0,
            week_label="2026-W12",
        )

        mock_smtp.send.assert_not_called()
