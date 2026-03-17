from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.analyzer.ai_client import AIClient
from muse.analyzer.idea import IdeaGenerator
from muse.analyzer.opportunity import OpportunityExtractor
from muse.analyzer.signal import SignalDetector
from muse.collector.filter import pre_filter
from muse.collector.miniflux import MinifluxCollector
from muse.config import FocusConfig, Settings
from muse.db import VALID_IDEA_STATUSES, Idea, Opportunity, Signal, State
from muse.publisher.email import EmailPublisher
from muse.publisher.notion import NotionPublisher
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


async def collect_signals_job(
    settings: Settings, focus: FocusConfig, session_factory
) -> None:
    """Daily job: fetch → filter → AI → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="collect_signals", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        topic_id=settings.telegram_topic_id or None,
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
    api_key = (
        settings.anthropic_api_key
        if settings.ai_provider == "claude"
        else settings.openai_api_key
    )
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

            session.add(
                Signal(
                    miniflux_entry_id=s["entry_id"],
                    title=entry.title,
                    url=entry.url,
                    source=entry.source,
                    raw_summary=entry.content[:2000],
                    ai_summary=s.get("summary", ""),
                    ai_tags=s.get("tags", []),
                    ai_score=s.get("score", 0),
                    ai_reason=s.get("reason", ""),
                )
            )

        # Update watermark
        max_id = max(e.entry_id for e in entries)
        await _set_state(session, "last_processed_entry_id", str(max_id))
        await session.commit()

    # 7. Push to Telegram (chained — event-driven, not clock-driven)
    try:
        await telegram.send_daily_summary(result.signals, total_processed=len(entries))
    except Exception as e:
        logger.error("telegram_push_failed", error=str(e))

    logger.info(
        "job_completed",
        job="collect_signals",
        job_id=job_id,
        entries=len(entries),
        filtered=len(filtered),
        signals=len(result.signals),
    )


async def extract_opportunities_job(
    settings: Settings, focus: FocusConfig, session_factory
) -> None:
    """Weekly job: query week's signals → AI opportunity extraction → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="extract_opportunities", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        topic_id=settings.telegram_topic_id or None,
    )

    # 1. Query signals from the past 7 days
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.created_at >= one_week_ago)
        )
        db_signals = result.scalars().all()

    if not db_signals:
        logger.info("no_signals_for_opportunities", job_id=job_id)
        return

    # Convert to dicts for AI
    signals_data = [
        {
            "id": str(s.id),
            "title": s.title,
            "ai_summary": s.ai_summary,
            "ai_tags": s.ai_tags,
            "ai_score": s.ai_score,
            "source": s.source,
        }
        for s in db_signals
    ]

    # 2. Run opportunity extraction
    api_key = (
        settings.anthropic_api_key
        if settings.ai_provider == "claude"
        else settings.openai_api_key
    )
    ai_client = AIClient(provider=settings.ai_provider, api_key=api_key)
    extractor = OpportunityExtractor(
        ai_client=ai_client,
        system_prompt_path=str(PROMPTS_DIR / "opportunity_extraction_system.txt"),
        user_prompt_path=str(PROMPTS_DIR / "opportunity_extraction_user.txt"),
        focus_areas=focus.focus_areas,
        indie_criteria=focus.indie_criteria,
    )
    extraction = await extractor.extract(signals_data)

    if extraction.failed:
        await telegram.send_alert(f"Opportunity extraction failed: {extraction.error}")
        return

    # 3. Store opportunities
    today = datetime.now(timezone.utc).date()
    signal_id_map = {str(s.id): s.id for s in db_signals}

    async with session_factory() as session:
        for opp in extraction.opportunities:
            evidence_uuids = []
            for eid in opp.get("evidence_ids", []):
                sid_str = str(eid)
                if sid_str in signal_id_map:
                    evidence_uuids.append(signal_id_map[sid_str])

            session.add(
                Opportunity(
                    title=opp["title"],
                    description=opp.get("description", ""),
                    trend_category=opp.get("trend_category", ""),
                    unmet_need=opp.get("unmet_need", ""),
                    market_gap=opp.get("market_gap", ""),
                    geo_opportunity=opp.get("geo_opportunity", ""),
                    confidence=opp.get("confidence", "medium"),
                    signal_ids=evidence_uuids,
                    week_of=today,
                )
            )
        await session.commit()

    # 4. Calculate week label
    week_label = datetime.now(timezone.utc).strftime("%G-W%V")

    # 5. Push via Telegram
    try:
        await telegram.send_weekly_brief(
            opportunities=extraction.opportunities,
            weekly_summary=extraction.weekly_summary,
            signal_count=len(db_signals),
            week_label=week_label,
        )
    except Exception as e:
        logger.error("telegram_weekly_failed", error=str(e))

    # 6. Push via Email
    email = EmailPublisher(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        recipients=[
            r.strip() for r in settings.email_recipients.split(",") if r.strip()
        ],
    )
    try:
        await email.send_weekly_digest(
            opportunities=extraction.opportunities,
            weekly_summary=extraction.weekly_summary,
            signal_count=len(db_signals),
            week_label=week_label,
        )
    except Exception as e:
        logger.error("email_weekly_failed", error=str(e))

    logger.info(
        "job_completed",
        job="extract_opportunities",
        job_id=job_id,
        signals=len(db_signals),
        opportunities=len(extraction.opportunities),
    )


async def generate_ideas_job(
    settings: Settings, focus: FocusConfig, session_factory
) -> None:
    """Monthly job: query month's opportunities → AI idea generation → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="generate_ideas", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        topic_id=settings.telegram_topic_id or None,
    )

    # 1. Query opportunities from the past 30 days
    one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    async with session_factory() as session:
        result = await session.execute(
            select(Opportunity).where(Opportunity.created_at >= one_month_ago)
        )
        db_opps = result.scalars().all()

    if not db_opps:
        logger.info("no_opportunities_for_ideas", job_id=job_id)
        return

    # 2. Convert to dicts for AI
    opps_data = [
        {
            "id": str(o.id),
            "title": o.title,
            "description": o.description,
            "trend_category": o.trend_category,
            "unmet_need": o.unmet_need,
            "market_gap": o.market_gap,
            "geo_opportunity": o.geo_opportunity,
            "confidence": o.confidence,
        }
        for o in db_opps
    ]

    # 3. Run IdeaGenerator
    api_key = (
        settings.anthropic_api_key
        if settings.ai_provider == "claude"
        else settings.openai_api_key
    )
    ai_client = AIClient(provider=settings.ai_provider, api_key=api_key)
    generator = IdeaGenerator(
        ai_client=ai_client,
        system_prompt_path=str(PROMPTS_DIR / "idea_generation_system.txt"),
        user_prompt_path=str(PROMPTS_DIR / "idea_generation_user.txt"),
        focus_areas=focus.focus_areas,
        indie_criteria=focus.indie_criteria,
    )
    generation = await generator.generate(opps_data)

    if generation.failed and not generation.ideas:
        await telegram.send_alert(f"Idea generation failed: {generation.error}")
        return

    # 4. Store ideas
    opp_id_map = {str(o.id): o.id for o in db_opps}
    async with session_factory() as session:
        for idea in generation.ideas:
            opp_id = opp_id_map.get(idea.get("source_opportunity_id"))
            session.add(
                Idea(
                    title=idea["title"],
                    one_liner=idea.get("one_liner", ""),
                    target_users=idea.get("target_users", ""),
                    pain_point=idea.get("pain_point", ""),
                    differentiation=idea.get("differentiation", ""),
                    channels=idea.get("channels", []),
                    revenue_model=idea.get("revenue_model", ""),
                    key_resources=idea.get("key_resources", ""),
                    cost_estimate=idea.get("cost_estimate", ""),
                    validation_method=idea.get("validation_method", ""),
                    difficulty=idea.get("difficulty", 3),
                    opportunity_id=opp_id,
                )
            )
        await session.commit()

    # 5. Calculate month label
    month_label = datetime.now(timezone.utc).strftime("%Y-%m")

    # 6. Push via Telegram
    try:
        await telegram.send_monthly_ideas(
            ideas=generation.ideas,
            monthly_summary=generation.monthly_summary,
            opportunity_count=len(db_opps),
            month_label=month_label,
        )
    except Exception as e:
        logger.error("telegram_monthly_failed", error=str(e))

    # 7. Push via Email
    email = EmailPublisher(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        recipients=[
            r.strip() for r in settings.email_recipients.split(",") if r.strip()
        ],
    )
    try:
        await email.send_monthly_ideas(
            ideas=generation.ideas,
            monthly_summary=generation.monthly_summary,
            opportunity_count=len(db_opps),
            month_label=month_label,
        )
    except Exception as e:
        logger.error("email_monthly_failed", error=str(e))

    logger.info(
        "job_completed",
        job="generate_ideas",
        job_id=job_id,
        opportunities=len(db_opps),
        ideas=len(generation.ideas),
    )


async def notion_sync_job(settings: Settings, session_factory) -> None:
    """Sync ideas with Notion — push new, pull status updates."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="notion_sync", job_id=job_id)

    notion = NotionPublisher(
        api_key=settings.notion_api_key,
        ideas_database_id=settings.notion_ideas_database_id,
    )
    if not notion.is_configured():
        logger.info("notion_sync_skipped", reason="not configured")
        return

    # Push: new ideas → Notion
    async with session_factory() as session:
        result = await session.execute(
            select(Idea).where(Idea.notion_page_id.is_(None))
        )
        new_ideas = result.scalars().all()

    if new_ideas:
        pushed = await notion.push_ideas(new_ideas)
        async with session_factory() as session:
            for idea_id, page_id in pushed:
                await session.execute(
                    update(Idea)
                    .where(Idea.id == idea_id)
                    .values(notion_page_id=page_id)
                )
            await session.commit()
        logger.info("notion_pushed", count=len(pushed))

    # Pull: updated statuses from Notion → DB
    updates = await notion.pull_status_updates()
    if updates:
        async with session_factory() as session:
            for page_id, new_status, edited_time in updates:
                if new_status not in VALID_IDEA_STATUSES:
                    logger.warning(
                        "notion_invalid_status", page_id=page_id, status=new_status
                    )
                    continue
                await session.execute(
                    update(Idea)
                    .where(
                        Idea.notion_page_id == page_id, Idea.updated_at < edited_time
                    )
                    .values(status=new_status, updated_at=edited_time)
                )
            await session.commit()
        logger.info("notion_pulled", count=len(updates))

    logger.info("job_completed", job="notion_sync", job_id=job_id)
