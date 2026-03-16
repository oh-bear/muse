from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.analyzer.ai_client import AIClient
from muse.analyzer.signal import SignalDetector
from muse.collector.filter import pre_filter
from muse.collector.miniflux import MinifluxCollector
from muse.config import FocusConfig, Settings
from muse.db import Signal, State
from muse.publisher.telegram import TelegramPublisher

logger = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent / "analyzer" / "prompts"


async def _get_state(session: AsyncSession, key: str, default: str = "0") -> str:
    result = await session.execute(select(State.value).where(State.key == key))
    row = result.scalar_one_or_none()
    return row if row is not None else default


async def _set_state(session: AsyncSession, key: str, value: str) -> None:
    existing = await session.execute(select(State).where(State.key == key))
    state = existing.scalar_one_or_none()
    if state:
        state.value = value
        state.updated_at = datetime.now(timezone.utc)
    else:
        session.add(State(key=key, value=value))
    await session.commit()


async def collect_signals_job(settings: Settings, focus: FocusConfig, session_factory) -> None:
    """Daily job: fetch → filter → AI → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="collect_signals", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    # 1. Read watermark
    async with session_factory() as session:
        last_id = int(await _get_state(session, "last_processed_entry_id"))

    # 2. Collect from Miniflux
    collector = MinifluxCollector(
        base_url=settings.miniflux_url,
        api_key=settings.miniflux_api_key,
        source_mapping=focus.source_mapping,
    )
    try:
        entries = await collector.fetch_new_entries(after_entry_id=last_id)
    except httpx.HTTPStatusError as e:
        logger.error("miniflux_unreachable", status=e.response.status_code)
        await telegram.send_alert(f"Miniflux API error: HTTP {e.response.status_code}")
        return
    except httpx.ConnectError:
        logger.error("miniflux_unreachable", error="connection refused")
        await telegram.send_alert("Miniflux unreachable: connection refused")
        return

    if not entries:
        logger.info("no_new_entries", job_id=job_id)
        return

    # 3. Pre-filter
    filtered = pre_filter(entries, exclude=focus.exclude)

    # 4. AI signal detection
    api_key = settings.anthropic_api_key if settings.ai_provider == "claude" else settings.openai_api_key
    ai_client = AIClient(provider=settings.ai_provider, api_key=api_key)
    detector = SignalDetector(
        ai_client=ai_client,
        system_prompt_path=str(PROMPTS_DIR / "signal_detection_system.txt"),
        user_prompt_path=str(PROMPTS_DIR / "signal_detection_user.txt"),
        focus_areas=focus.focus_areas,
        exclude_areas=focus.exclude,
        score_threshold=focus.score_threshold,
        indie_criteria=focus.indie_criteria,
    )
    result = await detector.detect(filtered)

    # 5. Alert if majority of batches failed
    if result.total_batches > 0 and result.failed_batches / result.total_batches > 0.5:
        await telegram.send_alert(
            f"Signal detection: {result.failed_batches}/{result.total_batches} batches failed"
        )

    # 6. Store signals
    entry_map = {e.entry_id: e for e in entries}
    async with session_factory() as session:
        for s in result.signals:
            entry = entry_map.get(s["entry_id"])
            if not entry:
                continue
            # Dedup check
            exists = await session.execute(
                select(Signal.id).where(Signal.miniflux_entry_id == s["entry_id"])
            )
            if exists.scalar_one_or_none():
                continue

            session.add(Signal(
                miniflux_entry_id=s["entry_id"],
                title=entry.title,
                url=entry.url,
                source=entry.source,
                raw_summary=entry.content[:2000],
                ai_summary=s.get("summary", ""),
                ai_tags=s.get("tags", []),
                ai_score=s.get("score", 0),
                ai_reason=s.get("reason", ""),
            ))

        # Update watermark
        max_id = max(e.entry_id for e in entries)
        await _set_state(session, "last_processed_entry_id", str(max_id))
        await session.commit()

    # 7. Push to Telegram (chained — event-driven, not clock-driven)
    try:
        await telegram.send_daily_summary(result.signals, total_processed=len(entries))
    except Exception as e:
        logger.error("telegram_push_failed", error=str(e))

    logger.info("job_completed", job="collect_signals", job_id=job_id,
               entries=len(entries), filtered=len(filtered), signals=len(result.signals))
