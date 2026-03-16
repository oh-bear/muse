"""
Integration test — verifies the full collect_signals pipeline
with a real PostgreSQL (via testcontainers) and mocked external APIs.
"""
import json

import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch
from testcontainers.postgres import PostgresContainer

from sqlalchemy import select, text

from muse.config import FocusConfig, Settings
from muse.db import Base, Signal, State, make_engine, make_session_factory


@pytest.fixture(scope="module")
def postgres():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db(postgres):
    url = postgres.get_connection_url().replace("psycopg2", "asyncpg")
    engine = make_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS muse"))
        await conn.run_sync(Base.metadata.create_all)
    session_factory = make_session_factory(engine)
    # Seed initial state
    async with session_factory() as session:
        session.add(State(key="last_processed_entry_id", value="0"))
        await session.commit()
    yield url, engine, session_factory
    await engine.dispose()


@pytest.fixture
def settings(db):
    url, _, _ = db
    return Settings(
        database_url=url,
        miniflux_url="http://miniflux:8080",
        miniflux_api_key="test-key",
        ai_provider="claude",
        anthropic_api_key="sk-test",
        telegram_bot_token="123:abc",
        telegram_chat_id="-100test",
    )


@pytest.fixture
def focus():
    return FocusConfig(
        focus_areas=["ai-tools"],
        exclude=["crypto"],
        score_threshold=3,
        source_mapping={"PH Feed": "producthunt"},
        indie_criteria={"max_team_size": 5, "prefer_low_infra": True, "prefer_digital_product": True},
    )


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline(settings, focus, db):
    """Entries flow through collect → filter → AI → store → push."""
    _, _, session_factory = db

    # Mock Miniflux API
    respx.get("http://miniflux:8080/v1/entries").mock(
        return_value=httpx.Response(200, json={
            "total": 2,
            "entries": [
                {"id": 1, "title": "AI Code Editor", "url": "https://x.com/1",
                 "content": "AI-powered editor", "feed": {"title": "PH Feed"}},
                {"id": 2, "title": "Crypto Exchange", "url": "https://x.com/2",
                 "content": "New crypto exchange", "feed": {"title": "PH Feed"}},
            ],
        })
    )

    # Mock Claude API — only entry 1 passes (entry 2 filtered by keyword)
    ai_result = json.dumps({
        "entries": [
            {"entry_id": 1, "score": 4, "tags": ["ai-tool"], "summary": "Good AI editor", "reason": "Real pain"}
        ]
    })
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": ai_result}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        })
    )

    # Mock Telegram
    bot_instance = AsyncMock()
    bot_instance.send_message = AsyncMock()
    bot_instance.__aenter__ = AsyncMock(return_value=bot_instance)
    bot_instance.__aexit__ = AsyncMock(return_value=False)

    from muse.scheduler import collect_signals_job

    with patch("muse.publisher.telegram.Bot", return_value=bot_instance):
        await collect_signals_job(settings, focus, session_factory)

    # Verify: signal stored
    async with session_factory() as session:
        signals = (await session.execute(select(Signal))).scalars().all()
        assert len(signals) == 1
        assert signals[0].title == "AI Code Editor"
        assert signals[0].source == "producthunt"
        assert signals[0].ai_score == 4

    # Verify: watermark updated
    async with session_factory() as session:
        state = (await session.execute(
            select(State.value).where(State.key == "last_processed_entry_id")
        )).scalar_one()
        assert state == "2"  # max entry ID

    # Verify: Telegram push called
    bot_instance.send_message.assert_called_once()
