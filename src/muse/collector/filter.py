from __future__ import annotations

import structlog

from muse.collector.miniflux import MinifluxEntry

logger = structlog.get_logger()


def pre_filter(
    entries: list[MinifluxEntry],
    exclude: list[str],
) -> list[MinifluxEntry]:
    if not exclude:
        return entries

    exclude_lower = [kw.lower() for kw in exclude]
    result = []

    for entry in entries:
        text = f"{entry.title} {entry.content}".lower()
        if any(kw in text for kw in exclude_lower):
            continue
        result.append(entry)

    filtered_count = len(entries) - len(result)
    logger.info("pre_filter", total=len(entries), passed=len(result), filtered=filtered_count)
    return result
