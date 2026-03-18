from __future__ import annotations

import re
from dataclasses import dataclass

import miniflux as miniflux_client
import structlog

logger = structlog.get_logger()


@dataclass
class MinifluxEntry:
    entry_id: int
    title: str
    url: str
    content: str
    source: str


class MinifluxCollector:
    PAGE_SIZE = 100

    def __init__(self, base_url: str, api_key: str, source_mapping: dict[str, str]):
        self.client = miniflux_client.Client(base_url, api_key=api_key)
        self.source_mapping = source_mapping

    def _resolve_source(self, feed_title: str) -> str:
        if feed_title in self.source_mapping:
            return self.source_mapping[feed_title]
        return re.sub(r"[^a-z0-9]+", "-", feed_title.lower()).strip("-")

    async def fetch_new_entries(self, after_entry_id: int) -> list[MinifluxEntry]:
        entries: list[MinifluxEntry] = []
        offset = 0

        while True:
            response = self.client.get_entries(
                after_entry_id=after_entry_id,
                order="id",
                direction="asc",
                limit=self.PAGE_SIZE,
                offset=offset,
            )
            batch = response.get("entries", [])

            for e in batch:
                feed_title = e.get("feed", {}).get("title", "unknown")
                entries.append(
                    MinifluxEntry(
                        entry_id=e["id"],
                        title=e["title"],
                        url=e["url"],
                        content=e.get("content", ""),
                        source=self._resolve_source(feed_title),
                    )
                )

            if len(batch) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE

        logger.info("fetched_entries", count=len(entries), after_id=after_entry_id)
        return entries
