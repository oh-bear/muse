from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # Miniflux
    miniflux_url: str
    miniflux_api_key: str

    # AI
    ai_provider: str = "claude"  # claude | openai
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # Scheduler (configurable schedule times)
    timezone: str = "Asia/Singapore"
    schedule_hour: int = 8
    schedule_minute: int = 0

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_recipients: str = ""  # comma-separated

    # Notion
    notion_api_key: str = ""
    notion_ideas_database_id: str = ""

    # Weekly schedule (Monday)
    weekly_schedule_day: str = "mon"
    weekly_schedule_hour: int = 10
    weekly_schedule_minute: int = 0

    class Config:
        env_file = ".env"


@dataclass
class FocusConfig:
    focus_areas: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    score_threshold: int = 3
    languages: list[str] = field(default_factory=lambda: ["en"])
    source_mapping: dict[str, str] = field(default_factory=dict)
    indie_criteria: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> FocusConfig:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(
            focus_areas=data.get("focus_areas", []),
            exclude=data.get("exclude", []),
            score_threshold=data.get("score_threshold", 3),
            languages=data.get("languages", ["en"]),
            source_mapping=data.get("source_mapping", {}),
            indie_criteria=data.get("indie_criteria", {}),
        )
