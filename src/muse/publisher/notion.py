from __future__ import annotations

from dataclasses import dataclass

import structlog

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
