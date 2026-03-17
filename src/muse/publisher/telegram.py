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
    topic_id: int | None = None

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

    async def send_weekly_brief(
        self,
        opportunities: list[dict[str, Any]],
        weekly_summary: str,
        signal_count: int,
        week_label: str,
    ) -> None:
        lines = [
            "🎯 *Muse Weekly Insights*",
            f"_{week_label} · {signal_count} signals analyzed_",
        ]

        if weekly_summary:
            lines.append("")
            lines.append(weekly_summary)

        if opportunities:
            lines.append("")
            for i, opp in enumerate(opportunities, 1):
                conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
                    opp.get("confidence", ""), "⚪"
                )
                lines.append(f"{i}\\. *{opp['title']}* {conf}")
                lines.append(f"   {opp.get('description', '')}")
                lines.append("")
        else:
            lines.append("")
            lines.append("No significant opportunities this week\\.")

        message = "\n".join(lines)
        await self._send(message)
        logger.info("telegram_weekly_sent", opportunities=len(opportunities))

    async def send_monthly_ideas(
        self,
        ideas: list[dict[str, Any]],
        monthly_summary: str,
        opportunity_count: int,
        month_label: str,
    ) -> None:
        lines = [
            "💡 *Muse Monthly Ideas*",
            f"_{month_label} · {opportunity_count} opportunities → {len(ideas)} ideas_",
        ]

        if monthly_summary:
            lines.append("")
            lines.append(monthly_summary)

        if ideas:
            lines.append("")
            for i, idea in enumerate(ideas, 1):
                diff = idea.get("difficulty", 3)
                stars = "⭐" * diff
                lines.append(f"{i}\\. *{idea['title']}* {stars}")
                lines.append(f"   {idea.get('one_liner', '')}")
                lines.append(f"   Revenue: {idea.get('revenue_model', '')} | Difficulty: {diff}/5")
                lines.append("")
        else:
            lines.append("")
            lines.append("No ideas generated this month\\.")

        message = "\n".join(lines)
        await self._send(message)
        logger.info("telegram_monthly_sent", ideas=len(ideas))

    async def send_alert(self, message: str) -> None:
        text = f"🚨 *Muse Alert*\n\n{message}"
        await self._send(text)
        logger.warning("telegram_alert_sent", message=message)

    async def _send(self, text: str) -> None:
        async with Bot(token=self.bot_token) as bot:
            kwargs: dict[str, Any] = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }
            if self.topic_id:
                kwargs["message_thread_id"] = self.topic_id
            await bot.send_message(**kwargs)
