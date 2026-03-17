from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

import structlog

from muse.config import FocusConfig, Settings
from muse.db import make_engine, make_session_factory, init_schema
from muse.logging import setup_logging
from muse.scheduler import collect_signals_job, extract_opportunities_job, generate_ideas_job, notion_sync_job

logger = structlog.get_logger()


async def run_job(job_name: str, settings: Settings, focus: FocusConfig, session_factory) -> None:
    """Run a specific job by name (CLI mode)."""
    # notion_sync has different signature (no focus)
    if job_name == "notion_sync":
        await notion_sync_job(settings, session_factory)
        return

    jobs = {
        "collect_signals": collect_signals_job,
        "extract_opportunities": extract_opportunities_job,
        "generate_ideas": generate_ideas_job,
    }
    if job_name not in jobs:
        logger.error("unknown_job", name=job_name, available=list(jobs.keys()))
        return
    await jobs[job_name](settings, focus, session_factory)


async def main() -> None:
    setup_logging()
    settings = Settings()
    focus = FocusConfig.from_yaml(Path("config/focus.yaml"))

    engine = make_engine(settings.database_url)
    await init_schema(engine)
    session_factory = make_session_factory(engine)

    # CLI mode: python -m muse.main run <job_name>
    if len(sys.argv) >= 3 and sys.argv[1] == "run":
        await run_job(sys.argv[2], settings, focus, session_factory)
        await engine.dispose()
        return

    # Scheduler mode
    sync_url = settings.database_url.replace("+asyncpg", "")
    jobstores = {"default": SQLAlchemyJobStore(url=sync_url, tableschema="muse")}
    scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=settings.timezone)

    scheduler.add_job(
        collect_signals_job,
        "cron",
        hour=settings.schedule_hour,
        minute=settings.schedule_minute,
        args=[settings, focus, session_factory],
        id="collect_signals",
        replace_existing=True,
        misfire_grace_time=7200,  # 2 hours — run missed jobs on restart
    )

    scheduler.add_job(
        extract_opportunities_job,
        "cron",
        day_of_week=settings.weekly_schedule_day,
        hour=settings.weekly_schedule_hour,
        minute=settings.weekly_schedule_minute,
        args=[settings, focus, session_factory],
        id="extract_opportunities",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    scheduler.add_job(
        generate_ideas_job,
        "cron",
        day=settings.monthly_schedule_day,
        hour=settings.monthly_schedule_hour,
        minute=settings.monthly_schedule_minute,
        args=[settings, focus, session_factory],
        id="generate_ideas",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    # Notion sync (only if configured)
    active_jobs = ["collect_signals", "extract_opportunities", "generate_ideas"]
    if settings.notion_api_key and settings.notion_ideas_database_id:
        scheduler.add_job(
            notion_sync_job,
            "interval",
            hours=settings.notion_sync_interval_hours,
            args=[settings, session_factory],
            id="notion_sync",
            replace_existing=True,
        )
        active_jobs.append("notion_sync")

    logger.info("scheduler_started", timezone=settings.timezone,
               schedule=f"daily={settings.schedule_hour:02d}:{settings.schedule_minute:02d}, "
                       f"weekly={settings.weekly_schedule_day} {settings.weekly_schedule_hour:02d}:{settings.weekly_schedule_minute:02d}, "
                       f"monthly=day {settings.monthly_schedule_day} {settings.monthly_schedule_hour:02d}:{settings.monthly_schedule_minute:02d}",
               jobs=active_jobs)
    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        await engine.dispose()
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    asyncio.run(main())
