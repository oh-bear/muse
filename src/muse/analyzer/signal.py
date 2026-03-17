from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

import structlog

from muse.analyzer.ai_client import AIClient, AIRequestError
from muse.collector.miniflux import MinifluxEntry

logger = structlog.get_logger()


@dataclass
class DetectionResult:
    signals: list[dict[str, Any]] = field(default_factory=list)
    failed_batches: int = 0
    total_batches: int = 0


@dataclass
class SignalDetector:
    ai_client: AIClient
    system_prompt_path: str
    user_prompt_path: str
    focus_areas: list[str]
    exclude_areas: list[str]
    score_threshold: int
    indie_criteria: dict[str, Any]
    batch_size: int = 15

    def _format_entries(self, entries: list[MinifluxEntry]) -> str:
        lines = []
        for e in entries:
            lines.append(
                f"- Entry ID: {e.entry_id}\n"
                f"  Title: {e.title}\n"
                f"  URL: {e.url}\n"
                f"  Content: {e.content[:500]}\n"
            )
        return "\n".join(lines)

    def _build_prompts(self, entries: list[MinifluxEntry]) -> tuple[str, str]:
        sys_template = Template(Path(self.system_prompt_path).read_text())
        user_template = Template(Path(self.user_prompt_path).read_text())

        system_prompt = sys_template.safe_substitute(
            focus_areas=", ".join(self.focus_areas),
            exclude_areas=", ".join(self.exclude_areas),
            max_team_size=self.indie_criteria.get("max_team_size", 5),
        )
        user_prompt = user_template.safe_substitute(
            entries=self._format_entries(entries),
        )
        return system_prompt, user_prompt

    async def detect(self, entries: list[MinifluxEntry]) -> DetectionResult:
        result = DetectionResult()
        batches = [
            entries[i : i + self.batch_size]
            for i in range(0, len(entries), self.batch_size)
        ]
        result.total_batches = len(batches)

        for batch_idx, batch in enumerate(batches):
            try:
                system_prompt, user_prompt = self._build_prompts(batch)
                ai_result, usage = await self.ai_client.call(system_prompt, user_prompt)

                for entry_result in ai_result.get("entries", []):
                    if entry_result.get("score", 0) >= self.score_threshold:
                        result.signals.append(entry_result)

                logger.info(
                    "signal_batch_processed",
                    batch=batch_idx + 1,
                    total_batches=len(batches),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )

            except AIRequestError as e:
                result.failed_batches += 1
                logger.error("signal_batch_failed", batch=batch_idx + 1, error=str(e))

        if batches and result.failed_batches / len(batches) > 0.5:
            logger.critical(
                "majority_batches_failed",
                failed=result.failed_batches,
                total=len(batches),
            )

        logger.info(
            "signal_detection_complete",
            total_entries=len(entries),
            signals=len(result.signals),
        )
        return result
