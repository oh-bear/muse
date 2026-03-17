from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class AIRequestError(Exception):
    pass


@dataclass
class AIClient:
    provider: str  # "claude" | "openai"
    api_key: str
    model: str = ""
    max_retries: int = 3
    base_delay: float = 2.0

    def __post_init__(self):
        if not self.model:
            self.model = "claude-sonnet-4-20250514" if self.provider == "claude" else "gpt-4o-mini"

    async def call(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], dict]:
        last_error: Exception | None = None
        current_user_prompt = user_prompt

        for attempt in range(self.max_retries):
            try:
                raw_text, usage = await self._api_call(system_prompt, current_user_prompt)
                return json.loads(raw_text), usage
            except json.JSONDecodeError:
                logger.warning("invalid_json_response", attempt=attempt + 1)
                if attempt < self.max_retries - 1:
                    current_user_prompt = f"{user_prompt}\n\nIMPORTANT: Respond with valid JSON only."
                    await asyncio.sleep(self.base_delay * (2 ** attempt))
                else:
                    last_error = AIRequestError(f"Failed to get valid JSON after {self.max_retries} attempts")
            except httpx.HTTPStatusError as e:
                logger.warning("ai_api_error", status=e.response.status_code, attempt=attempt + 1)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))
                else:
                    last_error = AIRequestError(f"AI API failed after {self.max_retries} retries: {e}")

        raise last_error  # type: ignore[misc]

    async def _api_call(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        if self.provider == "claude":
            return await self._call_claude(system_prompt, user_prompt)
        return await self._call_openai(system_prompt, user_prompt)

    async def _call_claude(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            logger.info("ai_call", provider="claude", model=self.model,
                       input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))
            return text, usage

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            logger.info("ai_call", provider="openai", model=self.model,
                       input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))
            return text, usage
