from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

import structlog

from muse.analyzer.ai_client import AIClient, AIRequestError

logger = structlog.get_logger()


@dataclass
class IdeaGenerationResult:
    ideas: list[dict[str, Any]] = field(default_factory=list)
    monthly_summary: str = ""
    failed: bool = False
    error: str = ""


@dataclass
class IdeaGenerator:
    ai_client: AIClient
    system_prompt_path: str
    user_prompt_path: str
    focus_areas: list[str]
    indie_criteria: dict[str, Any]
    max_opportunities_per_call: int = 20

    def _format_opportunities(self, opportunities: list[dict[str, Any]]) -> str:
        lines = []
        for opp in opportunities:
            lines.append(
                f"- Opportunity ID: {opp['id']}\n"
                f"  Title: {opp['title']}\n"
                f"  Description: {opp.get('description', '')}\n"
                f"  Category: {opp.get('trend_category', '')}\n"
                f"  Unmet Need: {opp.get('unmet_need', '')}\n"
                f"  Market Gap: {opp.get('market_gap', '')}\n"
                f"  Geo Opportunity: {opp.get('geo_opportunity', '')}\n"
                f"  Confidence: {opp.get('confidence', 'unknown')}\n"
            )
        return "\n".join(lines)

    def _build_prompts(self, opportunities: list[dict[str, Any]]) -> tuple[str, str]:
        sys_template = Template(Path(self.system_prompt_path).read_text())
        user_template = Template(Path(self.user_prompt_path).read_text())

        system_prompt = sys_template.safe_substitute(
            focus_areas=", ".join(self.focus_areas),
            max_team_size=self.indie_criteria.get("max_team_size", 5),
        )
        user_prompt = user_template.safe_substitute(
            opportunities=self._format_opportunities(opportunities),
        )
        return system_prompt, user_prompt

    async def generate(self, opportunities: list[dict[str, Any]]) -> IdeaGenerationResult:
        if not opportunities:
            return IdeaGenerationResult()

        result = IdeaGenerationResult()

        chunks = [opportunities[i:i + self.max_opportunities_per_call]
                  for i in range(0, len(opportunities), self.max_opportunities_per_call)]

        all_summaries = []

        for chunk_idx, chunk in enumerate(chunks):
            try:
                system_prompt, user_prompt = self._build_prompts(chunk)
                ai_result, usage = await self.ai_client.call(system_prompt, user_prompt)

                for idea in ai_result.get("ideas", []):
                    result.ideas.append(idea)

                summary = ai_result.get("monthly_summary", "")
                if summary:
                    all_summaries.append(summary)

                logger.info(
                    "idea_chunk_processed",
                    chunk=chunk_idx + 1,
                    total_chunks=len(chunks),
                    ideas=len(ai_result.get("ideas", [])),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )

            except AIRequestError as e:
                result.failed = True
                result.error = str(e)
                logger.error("idea_generation_failed", chunk=chunk_idx + 1, error=str(e))

        result.monthly_summary = " ".join(all_summaries) if all_summaries else ""

        logger.info("idea_generation_complete",
                    opportunities=len(opportunities), ideas=len(result.ideas))
        return result
