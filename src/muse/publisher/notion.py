from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from muse.db import Idea

logger = structlog.get_logger()


@dataclass
class NotionPublisher:
    api_key: str
    ideas_database_id: str

    def is_configured(self) -> bool:
        return bool(self.api_key and self.ideas_database_id)

    async def health_check(self) -> bool:
        """Verify Notion API connectivity and database access."""
        if not self.is_configured():
            logger.info("notion_skipped", reason="not configured")
            return False

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        try:
            await client.databases.retrieve(database_id=self.ideas_database_id)
            logger.info("notion_health_ok", database_id=self.ideas_database_id)
            return True
        except Exception as e:
            logger.error("notion_health_failed", error=str(e))
            return False

    async def push_ideas(self, ideas: list[Idea]) -> list[tuple[UUID, str]]:
        """Push ideas to Notion database. Returns list of (idea_id, notion_page_id)."""
        if not self.is_configured():
            return []

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        pushed: list[tuple[UUID, str]] = []

        for idea in ideas:
            properties = {
                "Name": {"title": [{"text": {"content": idea.title}}]},
                "One-Liner": {"rich_text": [{"text": {"content": idea.one_liner or ""}}]},
                "Target Users": {"rich_text": [{"text": {"content": idea.target_users or ""}}]},
                "Pain Point": {"rich_text": [{"text": {"content": idea.pain_point or ""}}]},
                "Differentiation": {"rich_text": [{"text": {"content": idea.differentiation or ""}}]},
                "Channels": {"rich_text": [{"text": {"content": ", ".join(idea.channels) if idea.channels else ""}}]},
                "Revenue Model": {"rich_text": [{"text": {"content": idea.revenue_model or ""}}]},
                "Key Resources": {"rich_text": [{"text": {"content": idea.key_resources or ""}}]},
                "Cost Estimate": {"rich_text": [{"text": {"content": idea.cost_estimate or ""}}]},
                "Validation Method": {"rich_text": [{"text": {"content": idea.validation_method or ""}}]},
                "Difficulty": {"number": idea.difficulty},
                "Status": {"select": {"name": idea.status or "pending"}},
            }
            try:
                page = await client.pages.create(
                    parent={"database_id": self.ideas_database_id},
                    properties=properties,
                )
                pushed.append((idea.id, page["id"]))
                logger.info("notion_idea_pushed", idea=idea.title, page_id=page["id"])
            except Exception as e:
                logger.error("notion_push_failed", idea=idea.title, error=str(e))

        return pushed

    async def pull_status_updates(self) -> list[tuple[str, str, datetime]]:
        """Pull status updates from Notion. Returns list of (page_id, status, edited_time)."""
        if not self.is_configured():
            return []

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        updates: list[tuple[str, str, datetime]] = []

        try:
            response = await client.databases.query(
                database_id=self.ideas_database_id,
            )
            for page in response.get("results", []):
                page_id = page["id"]
                props = page.get("properties", {})
                status_prop = props.get("Status", {})
                select_val = status_prop.get("select")
                if not select_val:
                    continue
                status = select_val.get("name", "")
                edited_time = datetime.fromisoformat(
                    page["last_edited_time"].replace("Z", "+00:00")
                )
                updates.append((page_id, status, edited_time))
        except Exception as e:
            logger.error("notion_pull_failed", error=str(e))

        return updates
