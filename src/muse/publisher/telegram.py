from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from telegram import Bot

logger = structlog.get_logger()


@dataclass
class TelegramPublisher:
    bot_token: str
    chat_id: str

    async def send_daily_summary(self, signals: list[dict[str, Any]], total_processed: int) -> None:
        top_signals = sorted(signals, key=lambda s: s.get("score", 0), reverse=True)[:3]

        lines = [
            "📡 *Muse Daily Signal Report*",
            "",
            f"Processed: {total_processed} entries",
            f"Signals found: {len(signals)}",
        ]

        if top_signals:
            lines.append("")
            lines.append("*Top Signals:*")
            for i, s in enumerate(top_signals, 1):
                score = "⭐" * s.get("score", 0)
                tags = ", ".join(s.get("tags", []))
                lines.append("")
                lines.append(f"{i}\\. {s['summary']}")
                lines.append(f"   {score} | {tags}")
                lines.append(f"   _{s.get('reason', '')}_")

        message = "\n".join(lines)
        await self._send(message)
        logger.info("telegram_daily_sent", signals=len(signals))

    async def send_alert(self, message: str) -> None:
        text = f"🚨 *Muse Alert*\n\n{message}"
        await self._send(text)
        logger.warning("telegram_alert_sent", message=message)

    async def _send(self, text: str) -> None:
        async with Bot(token=self.bot_token) as bot:
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
            )
