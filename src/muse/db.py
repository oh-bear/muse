from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    miniflux_entry_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    raw_summary: Mapped[str] = mapped_column(Text, default="")
    ai_summary: Mapped[str] = mapped_column(Text)
    ai_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    ai_score: Mapped[int] = mapped_column(SmallInteger)
    ai_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class State(Base):
    """Key-value store for worker state (e.g. last_processed_entry_id)."""
    __tablename__ = "state"
    __table_args__ = {"schema": "muse"}

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    trend_category: Mapped[str] = mapped_column(String(64))
    unmet_need: Mapped[str] = mapped_column(Text)
    market_gap: Mapped[str] = mapped_column(Text)
    geo_opportunity: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    signal_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    week_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


VALID_IDEA_STATUSES = {"pending", "promising", "validated", "abandoned"}


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text)
    one_liner: Mapped[str] = mapped_column(Text)
    target_users: Mapped[str] = mapped_column(Text)
    pain_point: Mapped[str] = mapped_column(Text)
    differentiation: Mapped[str] = mapped_column(Text)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    revenue_model: Mapped[str] = mapped_column(String(32))
    key_resources: Mapped[str] = mapped_column(Text)
    cost_estimate: Mapped[str] = mapped_column(Text)
    validation_method: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("muse.opportunities.id"), nullable=True
    )
    notion_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def make_engine(database_url: str):
    return create_async_engine(database_url, echo=False)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_schema(engine) -> None:
    """Create the muse schema if it doesn't exist."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS muse"))
